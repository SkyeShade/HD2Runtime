"""Beam conversion sync (runtime/beam_conversion_sync.lua, runtime/beam_conversion_sync_protocol.lua; docs/beam-
conversion.md "Multiplayer"; research/docs/beam-conversion-mp-sync-F5FEE03DCFDB.md, research/docs/beam-conversion-add-
layout-F5FEE03DCFDB.md): each Runtime publishes its applied beam conversions under the third lobby member key `hd2bc`
(hd2bc/2: layout, path, pair-independent record and rows digests), reads every other member's, and decides:
  * the swap layout is solo only (REMOTE_APPLY_UNSAFE: a remote weapon of a swap-converted type crashes the converted
    machine whatever the other converted);
  * an add-layout conversion is allowed with other players only when every other member is a Runtime of the same
    version, build and catalogue already holding the identical conversion (no player without the Runtime);
  * the lobby watch keeps an add conversion while every member holds it, a member is pending or a Runtime member is
    converging (GRACE), and restores it once a member is settled without it.
Offline: the codec and the decisions are pure; the channel runs on the event world's lobby
(tests/event_world_fixture.lua); joins with live instances run on the retained snapshot's overlay."""
import json
import unittest

from support import run
from test_event_scripting import PRELUDE as EVENT_PRELUDE
from test_beam_conversion import PRELUDE as SNAPSHOT_PRELUDE
from test_multi_mod_composition import snapshot_run

PROTOCOL = r"""
local P=require('hd2runtime/runtime/beam_conversion_sync_protocol')
local fnv1a=require('hd2runtime/runtime/peer_protocol').fnv1a
local A,B='0089BBE3E284FCAA','968211C0033DCE64'
local function e(resource,layout,path,record,rows)return {resource=resource,layout=layout or'a',path=path or'o',
    record=record or'1234ABCD',rows=rows or'00000000'}end
local function state(entries,opts)
    opts=opts or{}
    return {version=opts.version or'0.30.4-dev',build=opts.build or'F5FEE03DCFDB',catalog=opts.catalog or'811C9DC5',
        seq=opts.seq or 1,entries=entries}
end
local function refuses(text,needle)
    local d,why=P.decode(text)
    assert(d==nil and tostring(why):find(needle,1,true),tostring(text)..': '..tostring(why))
end
"""

SYNC = r"""
local S=require('hd2runtime/runtime/beam_conversion_sync')
local P=require('hd2runtime/runtime/beam_conversion_sync_protocol')
local C=require('hd2runtime/domains/beam_conversion')
local b=require('hd2runtime/core/bytes')
S.reset_for_tests()
-- A located beam conversion state as runtime/beam_conversion.lua locate returns it (only what entries_of reads).
local RECORD=string.rep('\1',120)
local function weapon(name)for _,w in ipairs(C.weapons)do if w.name==name then return w end end end
local function located(spec,path)
    local s={weapons={},path_mode=path or'owned',rs={pairs={}}}
    for name,v in pairs(spec)do
        local w=weapon(name)
        local roots={}
        for _,root in ipairs(w.roots)do roots[#roots+1]={root=root,state=v.state or'converted'}end
        s.weapons[name]={w=w,state=v.state or'converted',layout=v.layout or w.layout,record=v.record or RECORD,
            pair=v.pair,roots=roots}
        if v.pair then s.rs.pairs[v.pair]={beam=v.beam or string.rep('\2',112),damage=v.damage or string.rep('\3',76)}end
    end
    return s
end
local function value_of(entries,opts)
    opts=opts or{}
    return assert(P.encode({version=opts.version or S.version(),build=opts.build or S.build(),
        catalog=opts.catalog or S.catalogue_hash(),seq=opts.seq or 1,entries=entries}))
end
"""


class ProtocolTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PROTOCOL + body + "\nreturn 'ok'"), b'ok')

    def test_round_trip_is_canonical_and_order_independent(self):
        self.lua(r"""
local one=assert(P.encode(state({e(B,'a','o','AAAAAAAA','BBBBBBBB'),e(A,'w','s')})))
local two=assert(P.encode(state({e(A,'w','s'),e(B,'a','o','AAAAAAAA','BBBBBBBB')})))
assert(one==two,one)
local entries=A..'.w.s.1234ABCD.00000000,'..B..'.a.o.AAAAAAAA.BBBBBBBB'
assert(one=='hd2bc/2;0.30.4-dev;F5FEE03DCFDB;811C9DC5;1;'..fnv1a(entries)..';'..entries,one)
local d=assert(P.decode(one))
assert(d.version=='0.30.4-dev'and d.build=='F5FEE03DCFDB'and d.catalog=='811C9DC5'and d.seq==1)
assert(d.digest==fnv1a(entries)and#d.entries==2 and d.entries[1].resource==A and d.entries[2].layout=='a')
assert(d.entries[2].rows=='BBBBBBBB'and d.entries[1].path=='s'and d.entries[1].layout=='w')
local none=assert(P.encode(state({})))
assert(none=='hd2bc/2;0.30.4-dev;F5FEE03DCFDB;811C9DC5;1;'..fnv1a('-')..';-',none)
assert(#assert(P.decode(none)).entries==0)
assert(P.same(e(A),e(A))and not P.same(e(A),e(A,'w'))and not P.same(e(A),nil))
""")

    def test_the_digest_changes_with_every_conversion_detail(self):
        self.lua(r"""
local base=select(2,P.canonical({e(B,'a','o','AAAAAAAA','BBBBBBBB')}))
for _,other in ipairs({{e(B,'w','o','AAAAAAAA','BBBBBBBB')},{e(B,'a','s','AAAAAAAA','BBBBBBBB')},
        {e(B,'a','o','AAAAAAAB','BBBBBBBB')},{e(B,'a','o','AAAAAAAA','BBBBBBBC')},{e(A,'a','o','AAAAAAAA','BBBBBBBB')},
        {e(B,'a','o','AAAAAAAA','BBBBBBBB'),e(A)},{}})do
    assert(select(2,P.canonical(other))~=base)
end
assert(select(2,P.canonical({e(B,'a','o','AAAAAAAA','BBBBBBBB')}))==base)
""")

    def test_digests_ignore_the_locally_borrowed_ids(self):
        self.lua(r"""
local rec=string.rep('\9',120)
local r6=b.encode(6,'u32')..rec:sub(5)
local r3=b.encode(3,'u32')..rec:sub(5)
assert(P.record_digest(r6)==P.record_digest(r3))
assert(P.record_digest(r6)~=P.record_digest(r6:sub(1,104)..b.encode(600,'i32')..r6:sub(109)))
local beam=string.rep('\4',112)
local damage=string.rep('\5',76)
local k3=b.encode(3,'u32')..beam:sub(5,12)..b.encode(278,'u32')..beam:sub(17)
local k15=b.encode(15,'u32')..beam:sub(5,12)..b.encode(577,'u32')..beam:sub(17)
assert(P.rows_digest(k3,b.encode(278,'u32')..damage:sub(5))==P.rows_digest(k15,b.encode(577,'u32')..damage:sub(5)))
assert(P.rows_digest(nil,nil)=='00000000'and P.rows_digest(k3,damage)~='00000000')
""".replace("local rec", "local b=require('hd2runtime/core/bytes')\nlocal rec", 1))

    def test_eleven_roots_fit_the_member_value_and_twelve_are_refused(self):
        self.lua(r"""
local list={}
for i=1,11 do list[i]=e(string.format('%016X',i),'a','o','FFFFFFFF','FFFFFFFF')end
local v=assert(P.encode(state(list,{version=string.rep('9',32),seq=P.MAX_SEQ})))
assert(#v<=512,#v)
assert(#assert(P.decode(v)).entries==11)
list[12]=e(string.format('%016X',12))
local none,why=P.encode(state(list))
assert(none==nil and why:find('at most 11',1,true),why)
""")

    def test_encode_refuses_what_the_grammar_cannot_carry(self):
        self.lua(r"""
local function no(s,needle)local v,why=P.encode(s);assert(v==nil and tostring(why):find(needle,1,true),tostring(why))end
no(state({e(A)},{version='0.30 dev'}),'version')
no(state({e(A)},{build='f5fee03dcfdb'}),'build')
no(state({e(A)},{build='F5FEE03DCF'}),'build')
no(state({e(A)},{catalog='811c9dc5'}),'catalogue')
no(state({e(A)},{seq=0}),'sequence')
no(state({e('0x'..A)}),'resource')
no(state({e(A,'q')}),'layout')
no(state({e(A,'a','q')}),'path')
no(state({e(A,'a','o','1234abcd')}),'record')
no(state({e(A,'a','o','1234ABCD','ffffffff')}),'rows digest')
no(state({e(A,'a','x','1234ABCD')}),'orphaned')
no(state({e(A),e(A)}),'duplicate')
""")

    def test_decode_refuses_every_value_not_matching_exactly(self):
        self.lua(r"""
local entries=A..'.a.o.1234ABCD.00000000'
local head='hd2bc/2;0.30.4-dev;F5FEE03DCFDB;811C9DC5;3;'
local ok=head..fnv1a(entries)..';'..entries
assert(P.decode(ok))
refuses(nil,'not text')
refuses('','length')
refuses(string.rep('a',513),'length')
refuses(ok..'\1','printable')
refuses('hd2as/1;0.30.4-dev;811C9DC5;3;'..A,'not hd2bc/2')
-- An older Runtime's hd2bc/1 value is not this protocol.
local old='hd2bc/1;0.30.4-dev;F5FEE03DCFDB;811C9DC5;3;'..fnv1a(A..'.o.1234ABCD.0.00000000')..';'..A..'.o.1234ABCD.0.00000000'
refuses(old,'not hd2bc/2')
refuses(ok..';x','7 fields')
refuses(head..'00000000;'..entries,'digest does not match')
refuses(head..fnv1a(entries):lower()..';'..entries,'invalid digest')
local function with(list)return head..fnv1a(list)..';'..list end
refuses(with(''),'invalid entry')
refuses(with(A:lower()..'.a.o.1234ABCD.00000000'),'invalid entry')
refuses(with(A..'.a.x.1234ABCD.00000000'),'invalid entry')
refuses(with(A..'.b.o.1234ABCD.00000000'),'invalid entry')
refuses(with(entries..','),'invalid entry')
refuses(with(B..'.a.o.1234ABCD.00000000,'..A..'.a.o.1234ABCD.00000000'),'ascending')
refuses(with(entries..','..entries),'ascending')
""")


class DecisionTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(SYNC + body + "\nreturn 'ok'"), b'ok')

    def test_the_overall_decision(self):
        self.lua(r"""
local function d(members,entries,build)return S.decide({members=members,entries=entries or{},build=build})end
assert(d({}).allowed and d({}).code=='SOLO')
local all=d({{peer='A',state='match',host=true},{peer='B',state='match'}})
assert(all.allowed and all.code=='ALL_MATCH',all.code)
-- Swap conversions on this machine: never with others.
local swap=d({{peer='A',state='match'}},{{resource='0',layout='w'}})
assert(not swap.allowed and swap.code=='REMOTE_APPLY_UNSAFE')
-- Another build: the add layout is build-scoped.
assert(d({{peer='A',state='match'}},{},'000000000000').code=='REMOTE_APPLY_UNSAFE')
assert(S.ADD_LAYOUT_SAFE.F5FEE03DCFDB==true)
-- One missing, one different, pending, malformed, incompatible: refused with the member named.
assert(d({{peer='A',state='match'},{peer='B',state='no_runtime'}}).code=='NO_RUNTIME')
local mm=d({{peer='A',state='mismatch',host=true},{peer='B',state='match'}})
assert(mm.code=='MISMATCH'and mm.reason=='mismatch: A (host)',mm.reason)
assert(d({{peer='A',state='pending'}}).code=='PENDING')
assert(d({{peer='A',state='malformed'}}).code=='MALFORMED')
assert(d({{peer='A',state='incompatible'}}).code=='INCOMPATIBLE')
local order=d({{peer='A',state='pending'},{peer='B',state='mismatch'},{peer='C',state='no_runtime'}})
assert(order.code=='NO_RUNTIME'and order.reason=='no runtime: C',order.reason)
assert(d({{peer='H',state='no_runtime',host=true}}).reason=='no runtime: H (host)')
""")

    def test_an_add_apply_needs_every_member_to_hold_the_identical_conversion(self):
        self.lua(r"""
local sickle=weapon('LAS-16 Sickle')
local mine=S.weapon_entries(sickle,'add','o',RECORD,nil,nil)
local other=S.weapon_entries(sickle,'add','o',RECORD:sub(1,104)..b.encode(600,'i32')..RECORD:sub(109),nil,nil)
local dec=function(entries)return P.decode(value_of(entries))end
local function m(peer,state,entries,host)return {peer=peer,state=state,host=host,d=entries and dec(entries)or nil}end
-- Nobody read yet: pending.
assert(S.allow_apply(mine,{members={}}).code=='PENDING')
-- Every member holds it (and maybe more): allowed.
local talon=S.weapon_entries(weapon('LAS-58 Talon'),'add','o',RECORD,nil,nil)
local both={mine[1],talon[1]}
table.sort(both,function(a,c)return a.resource<c.resource end)
local ok=S.allow_apply(mine,{members={m('H','mismatch',both,true),m('C','match',mine)}})
assert(ok.allowed and ok.code=='ALL_AGREE',ok.code)
-- One holds another rate: MISMATCH, naming the member.
local no=S.allow_apply(mine,{members={m('H','mismatch',other,true)}})
assert(not no.allowed and no.code=='MISMATCH'and no.reason:find('H (host)',1,true),no.reason)
-- One holds nothing: MISMATCH (the first mover waits for nobody; it converts solo before joining).
assert(S.allow_apply(mine,{members={m('H','mismatch',{},true)}}).code=='MISMATCH')
-- A member without the Runtime, malformed, incompatible, pending: refused with its code.
assert(S.allow_apply(mine,{members={m('C','no_runtime')}}).code=='NO_RUNTIME')
assert(S.allow_apply(mine,{members={m('C','malformed')}}).code=='MALFORMED')
assert(S.allow_apply(mine,{members={m('C','incompatible',mine)}}).code=='INCOMPATIBLE')
assert(S.allow_apply(mine,{members={m('C','pending')}}).code=='PENDING')
-- The swap layout: never.
local swap=S.weapon_entries(weapon('AR-23 Liberator'),'swap','o',RECORD,nil,nil)
assert(S.allow_apply(swap,{members={m('C','match',swap)}}).code=='REMOTE_APPLY_UNSAFE')
-- Another build: refused.
assert(S.allow_apply(mine,{members={m('C','match',mine)},build='000000000000'}).code=='REMOTE_APPLY_UNSAFE')
""")

    def test_the_watch_keeps_an_add_conversion_only_while_the_lobby_can_agree(self):
        self.lua(r"""
local sickle=weapon('LAS-16 Sickle')
local mine=S.weapon_entries(sickle,'add','o',RECORD,nil,nil)
local by={['LAS-16 Sickle']=mine}
local function m(peer,state,entries,changed)return {peer=peer,state=state,changed=changed,
    d=entries and P.decode(value_of(entries))or nil}end
assert(S.keep(by,{members={m('A','match',mine,0)},clock=100})['LAS-16 Sickle'].keep)
-- Pending: kept.
local p=S.keep(by,{members={m('A','pending')},clock=100})['LAS-16 Sickle']
assert(p.keep and p.code=='PENDING')
-- A Runtime whose set changed recently: converging, kept; after the grace: restored.
local c=S.keep(by,{members={m('A','mismatch',{},90)},clock=100})['LAS-16 Sickle']
assert(c.keep and c.code=='CONVERGING',c.code)
local r=S.keep(by,{members={m('A','mismatch',{},60)},clock=100})['LAS-16 Sickle']
assert(not r.keep and r.code=='MISMATCH',r.code)
-- No Runtime, malformed, incompatible: restored at once.
for _,state in ipairs({'no_runtime','malformed','incompatible'})do
    assert(not S.keep(by,{members={m('A',state)},clock=100})['LAS-16 Sickle'].keep,state)
end
-- One member agrees, another has none: restored.
assert(not S.keep(by,{members={m('A','match',mine,0),m('B','no_runtime')},clock=100})['LAS-16 Sickle'].keep)
""")

    def test_member_states_from_their_values(self):
        self.lua(r"""
S.note(located({['LAS-16 Sickle']={}}))
local mine=assert(S.value())
local digest=S.digest()
assert(S.member_state(nil,digest,0,29.9)=='pending')
local st,why=S.member_state(nil,digest,0,30)
assert(st=='no_runtime'and why:find('no hd2bc value after 30 s',1,true))
assert(S.member_state(mine,digest,0,1)=='match')
assert(S.member_state('hd2bc/2;garbage',digest,0,1)=='malformed')
local d=assert(P.decode(mine))
local other=assert(P.encode({version='0.30.1',build=d.build,catalog=d.catalog,seq=1,entries=d.entries}))
assert(S.member_state(other,digest,0,1)=='incompatible')
local diff=assert(P.encode({version=d.version,build=d.build,catalog=d.catalog,seq=4,entries={}}))
assert(S.member_state(diff,digest,0,1)=='mismatch')
local reseq=assert(P.encode({version=d.version,build=d.build,catalog=d.catalog,seq=9,entries=d.entries}))
assert(S.member_state(reseq,digest,0,1)=='match')
""")

    def test_entries_of_a_located_state(self):
        self.lua(r"""
local s=located({['LAS-16 Sickle']={},['AR-23 Liberator']={pair=2},['SMG-32 Reprimand']={state='orphaned'}})
local entries,names=S.entries_of(s)
assert(table.concat(names,',')=='AR-23 Liberator,LAS-16 Sickle,SMG-32 Reprimand',table.concat(names,','))
local by={}
for _,e in ipairs(entries)do by[S.weapon_of(e.resource)]=e end
assert(by['LAS-16 Sickle'].layout=='a'and by['LAS-16 Sickle'].path=='o'and
    by['LAS-16 Sickle'].record==P.record_digest(RECORD)and by['LAS-16 Sickle'].rows=='00000000')
assert(by['AR-23 Liberator'].layout=='w'and by['AR-23 Liberator'].rows==P.rows_digest(string.rep('\2',112),
    string.rep('\3',76)))
assert(by['SMG-32 Reprimand'].path=='x'and by['SMG-32 Reprimand'].record=='00000000')
for i=2,#entries do assert(entries[i-1].resource<entries[i].resource)end
-- The shared path: the donor record, path s.
local sh=S.entries_of(located({['LAS-16 Sickle']={}},'shared'))
assert(sh[1].path=='s'and sh[1].record==P.record_digest(b.unhex(C.trident.recordHex)))
-- Own rows that hold exactly the Trident's: "no own rows".
local tb,td=b.unhex(C.rows.tridentBeamHex),b.unhex(C.rows.tridentDamageHex)
local keyed=b.encode(3,'u32')..tb:sub(5,12)..b.encode(278,'u32')..tb:sub(17)
assert(S.rows_digest(keyed,b.encode(278,'u32')..td:sub(5))=='00000000')
assert(S.catalogue_hash()==S.catalogue_hash()and#S.catalogue_hash()==8)
assert(S.build()==require('hd2runtime/schemas/current').exe_sha:sub(1,12))
""")


CHANNEL = EVENT_PRELUDE + r"""
local channel=require('hd2runtime/runtime/peer_channel')
channel.reset_for_tests()
""" + SYNC + r"""
local R=W.runtime
W.players({{peer=LOCAL,avatar=100}},LOCAL)
local function seconds(s)tick(math.floor(s/0.125+0.5))end
local function posts()
    local out={}
    for _,p in ipairs(R.lobby_posts)do if p.key=='hd2bc'then out[#out+1]=p.value end end
    return out
end
local NOTICES={}
package.loaded['hd2runtime/runtime/matchmaking_safety']={notice=function(title,detail)
    NOTICES[#NOTICES+1]=title..': '..detail end}
"""


class ChannelTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(CHANNEL + body + "\nreturn 'ok'"), b'ok')

    def test_a_runtime_without_conversions_posts_nothing(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
S.start()
S.note(located({}))
seconds(40)
assert(#posts()==0 and count('BEAM CONVERSION SYNC: posting')==0)
assert(S.status().members[OTHER].state=='no_runtime')
assert(count('BEAM CONVERSION SYNC: member')==0)
""")

    def test_identical_add_sets_are_allowed_and_the_post_follows_every_change(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER},host=OTHER})
S.start()
S.note(located({['LAS-16 Sickle']={}}))
local mine=assert(S.value())
seconds(14)
assert(#posts()==1 and posts()[1]==mine,tostring(posts()[1]))
assert(count('BEAM CONVERSION SYNC: posting seq 1: LAS-16 Sickle')==1)
-- The other member posts the identical set (another seq): match, ALL_MATCH, and no warning (no swap entry, same).
local d=assert(P.decode(mine))
W.lobby_keyed.hd2bc[OTHER]=assert(P.encode({version=d.version,build=d.build,catalog=d.catalog,seq=5,
    entries=d.entries}))
seconds(3.5)
assert(S.status().members[OTHER].state=='match'and S.status().members[OTHER].host)
assert(count('BEAM CONVERSION SYNC: decision ALLOWED (ALL_MATCH)')==1)
assert(count('WARNING: member')==0 and#NOTICES==0)
-- Their set changes (another rate digest): mismatch, a log line naming the weapon (no crash warning).
W.lobby_keyed.hd2bc[OTHER]=assert(P.encode({version=d.version,build=d.build,catalog=d.catalog,seq=6,
    entries={{resource=d.entries[1].resource,layout='a',path='o',record='00C0FFEE',rows='00000000'}}}))
seconds(3.5)
assert(S.status().members[OTHER].state=='mismatch')
assert(count('decision REFUSED (MISMATCH): mismatch: '..OTHER..' (host)')==1)
assert(count('has LAS-16 Sickle converted (add layout) differently')==1 and#NOTICES==0)
-- They swap-convert it: the crash warning and the notice.
W.lobby_keyed.hd2bc[OTHER]=assert(P.encode({version=d.version,build=d.build,catalog=d.catalog,seq=7,
    entries={{resource=d.entries[1].resource,layout='w',path='o',record='00C0FFEE',rows='00000000'}}}))
seconds(3.5)
assert(count('WARNING: member '..OTHER..' has LAS-16 Sickle converted with the SWAP layout')==1)
assert(#NOTICES==1 and NOTICES[1]:find('LAS-16 Sickle',1,true))
-- This machine restores: the empty set is posted (the lobby keeps no stale set), seq 2.
S.note(located({}))
seconds(6)
local p=posts()
assert(#p==2 and P.decode(p[2]).seq==2 and#P.decode(p[2]).entries==0,tostring(p[2]))
-- The member leaves: solo.
W.lobby({members={LOCAL}})
seconds(3.5)
assert(S.decision().code=='SOLO'and count('BEAM CONVERSION SYNC: solo')==1)
""")

    def test_a_member_without_a_value_is_pending_then_no_runtime(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
S.start()
S.note(located({['AR-23 Liberator']={pair=1}}))
seconds(3.5)
assert(S.status().members[OTHER].state=='pending')
assert(count('member '..OTHER..': pending')==1)
assert(count('decision REFUSED (PENDING)')==1)
seconds(30)
assert(S.status().members[OTHER].state=='no_runtime')
assert(count('decision REFUSED (NO_RUNTIME): no runtime: '..OTHER)==1)
W.lobby_keyed.hd2bc={[OTHER]='hd2bc/2;nonsense'}
seconds(3.5)
assert(S.status().members[OTHER].state=='malformed'and count('decision REFUSED (MALFORMED)')==1)
local d=assert(P.decode(S.value()))
W.lobby_keyed.hd2bc[OTHER]=assert(P.encode({version='0.30.1',build=d.build,catalog=d.catalog,seq=1,entries={}}))
seconds(3.5)
assert(S.status().members[OTHER].state=='incompatible'and count('decision REFUSED (INCOMPATIBLE)')==1)
for _,p in ipairs(R.lobby_posts)do assert(p.key=='hd2bc')end
""")


SNAPSHOT = SNAPSHOT_PRELUDE + r'''
local S=require('hd2runtime/runtime/beam_conversion_sync')
local P=require('hd2runtime/runtime/beam_conversion_sync_protocol')
local W=require('hd2runtime/runtime/beam_conversion_watch')
'''


class SnapshotJoinTests(unittest.TestCase):
    def test_joins_and_leaves_follow_the_layout_and_the_posted_sets(self):
        result = snapshot_run(SNAPSHOT + r'''
local sickle,lib=weapon('LAS-16 Sickle'),weapon('AR-23 Liberator')
local out={}
-- Solo: the Sickle (add layout) and the Liberator (swap layout, own rate and rows).
check(enable('sickle','LAS-16 Sickle').status=='complete','sickle')
check(enable('lib','AR-23 Liberator',{{field=F.beam.fire_rate,expect=300,value=600},
  {field=F.damage.player_standard_damage,expect=60,value=600}}).status=='complete','liberator')
local st=S.status()
out.both=table.concat(st.converted,', ')=='AR-23 Liberator, LAS-16 Sickle'and st.seq==2
local d=P.decode(assert(S.value()))
local by={}
for _,e in ipairs(d.entries)do by[S.weapon_of(e.resource)]=e end
out.details=by['AR-23 Liberator'].layout=='w'and by['LAS-16 Sickle'].layout=='a'and by['AR-23 Liberator'].path=='o'
  and by['AR-23 Liberator'].rows~='00000000'and by['LAS-16 Sickle'].rows=='00000000'
local first_digest=d.digest
-- Another player joins (nothing read from the lobby yet): the idle swap Liberator is restored at once; the add
-- Sickle stays (pending).
LOBBY.solo=false
W.tick_for_tests(1)
out.swap_restored_at_once=vanilla_ok(lib)
out.add_kept_pending=converted_ok(sickle)
-- An apply of the swap layout waits NOT_SOLO; of the add layout NOT_AGREED (PENDING).
local h=enable('lib-again','AR-23 Liberator')
out.swap_waits=waiting(h,'NOT_SOLO')
h=enable('talon','LAS-58 Talon')
out.add_waits=waiting(h,'NOT_AGREED')and tostring(h.last_transient):find('PENDING',1,true)~=nil
-- The member posts the identical set (as a Runtime that converted the Sickle the same way): the Sickle stays.
local mine=assert(S.value())
S.set_members_for_tests({PEER={value=mine,host=true}})
W.tick_for_tests(6)
out.kept_on_match=converted_ok(sickle)
-- A settings change of a converted add weapon changes what it posts: refused while the other player holds the old one.
h=tx('sickle-rate','LAS-16 Sickle',{{field=F.beam.fire_rate,expect=300,value=450}})
out.settings_need_agreement=waiting(h,'NOT_AGREED')
-- The other side converted the Talon identically too: this machine may now convert it in the lobby.
local talon_entries=S.weapon_entries(weapon('LAS-58 Talon'),'add','o',require('hd2runtime/runtime/beam_conversion')
  .settings_record({}),nil,nil)
local theirs=P.decode(mine).entries
for _,e in ipairs(talon_entries)do theirs[#theirs+1]=e end
table.sort(theirs,function(a,c)return a.resource<c.resource end)
S.set_members_for_tests({PEER={value=assert(P.encode({version=S.version(),build=S.build(),catalog=S.catalogue_hash(),
  seq=3,entries=theirs})),host=true}})
h=enable('talon2','LAS-58 Talon')
out.add_allowed_when_held=h.status=='complete'
-- A member without the Runtime (settled): the idle add conversions are restored, a live one stays.
LIVE[sickle.roots[1].resource]=1
S.set_members_for_tests({PEER={state='no_runtime',host=true}})
W.tick_for_tests(6)
out.live_add_kept=converted_ok(sickle)
out.idle_add_restored=vanilla_ok(weapon('LAS-58 Talon'))
LIVE[sickle.roots[1].resource]=nil
W.tick_for_tests(6)
out.later_restored=vanilla_ok(sickle)
st=S.status()
out.empty_posted=#st.converted==0
-- Solo again: the same requests give the same digest as before.
LOBBY.solo=true
S.set_members_for_tests({})
W.tick_for_tests(1)
check(enable('sickle2','LAS-16 Sickle').status=='complete','sickle again')
check(enable('lib2','AR-23 Liberator',{{field=F.beam.fire_rate,expect=300,value=600},
  {field=F.damage.player_standard_damage,expect=60,value=600}}).status=='complete','liberator again')
out.deterministic=S.digest()==first_digest
disable('off1','LAS-16 Sickle');disable('off2','AR-23 Liberator')
out.clean=changed()==0
return json.encode(out)''')
        for key, value in result.items():
            self.assertTrue(value, (key, result))


if __name__ == '__main__':
    unittest.main()
