"""Beam conversion sync (runtime/beam_conversion_sync.lua, runtime/beam_conversion_sync_protocol.lua; docs/beam-
conversion.md "Multiplayer"; research/docs/beam-conversion-mp-sync-F5FEE03DCFDB.md): each Runtime publishes its applied
beam conversions under the third lobby member key `hd2bc`, reads every other member's, and logs a per-member state and
a decision. The research proved that the same conversion on every machine does NOT make multiplayer safe, so the
decision is REFUSED whenever another member is present (REMOTE_APPLY_UNSAFE when every member matches) and the apply
gate stays solo. Offline: the codec and the decision are pure; the channel runs on the event world's lobby
(tests/event_world_fixture.lua); joins and leaves with live instances run on the retained snapshot's overlay."""
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
local function e(resource,path,record,pair,rows)return {resource=resource,path=path or'o',record=record or'1234ABCD',
    pair=pair or 0,rows=rows or'00000000'}end
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
local C=require('hd2runtime/domains/beam_conversion')
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
        s.weapons[name]={w=w,state=v.state or'converted',record=v.record or RECORD,pair=v.pair,roots=roots}
        if v.pair then s.rs.pairs[v.pair]={beam=v.beam or string.rep('\2',112),damage=v.damage or string.rep('\3',76)}end
    end
    return s
end
"""


class ProtocolTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PROTOCOL + body + "\nreturn 'ok'"), b'ok')

    def test_round_trip_is_canonical_and_order_independent(self):
        self.lua(r"""
local one=assert(P.encode(state({e(B,'o','AAAAAAAA',2,'BBBBBBBB'),e(A,'s')})))
local two=assert(P.encode(state({e(A,'s'),e(B,'o','AAAAAAAA',2,'BBBBBBBB')})))
assert(one==two,one)
local entries=A..'.s.1234ABCD.0.00000000,'..B..'.o.AAAAAAAA.2.BBBBBBBB'
assert(one=='hd2bc/1;0.30.4-dev;F5FEE03DCFDB;811C9DC5;1;'..fnv1a(entries)..';'..entries,one)
local d=assert(P.decode(one))
assert(d.version=='0.30.4-dev'and d.build=='F5FEE03DCFDB'and d.catalog=='811C9DC5'and d.seq==1)
assert(d.digest==fnv1a(entries)and#d.entries==2 and d.entries[1].resource==A and d.entries[2].pair==2)
assert(d.entries[2].rows=='BBBBBBBB'and d.entries[1].path=='s')
-- Nothing converted: '-'.
local none=assert(P.encode(state({})))
assert(none=='hd2bc/1;0.30.4-dev;F5FEE03DCFDB;811C9DC5;1;'..fnv1a('-')..';-',none)
assert(#assert(P.decode(none)).entries==0)
""")

    def test_the_digest_changes_with_every_conversion_detail(self):
        self.lua(r"""
local base=select(2,P.canonical({e(B,'o','AAAAAAAA',2,'BBBBBBBB')}))
for _,other in ipairs({{e(B,'s','AAAAAAAA',2,'BBBBBBBB')},{e(B,'o','AAAAAAAB',2,'BBBBBBBB')},
        {e(B,'o','AAAAAAAA',3,'BBBBBBBB')},{e(B,'o','AAAAAAAA',2,'BBBBBBBC')},{e(A,'o','AAAAAAAA',2,'BBBBBBBB')},
        {e(B,'o','AAAAAAAA',2,'BBBBBBBB'),e(A)},{}})do
    assert(select(2,P.canonical(other))~=base)
end
assert(select(2,P.canonical({e(B,'o','AAAAAAAA',2,'BBBBBBBB')}))==base)
""")

    def test_eleven_roots_fit_the_member_value_and_twelve_are_refused(self):
        self.lua(r"""
local list={}
for i=1,11 do list[i]=e(string.format('%016X',i),'o','FFFFFFFF',6,'FFFFFFFF')end
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
no(state({e(A,'q')}),'path')
no(state({e(A,'o','1234abcd')}),'record')
no(state({e(A,'o','1234ABCD',7,'FFFFFFFF')}),'pair')
no(state({e(A,'o','1234ABCD',0,'FFFFFFFF')}),'rows digest')
no(state({e(A,'o','1234ABCD',1,'00000000')}),'rows digest')
no(state({e(A,'x','1234ABCD')}),'orphaned')
no(state({e(A),e(A)}),'duplicate')
""")

    def test_decode_refuses_every_value_not_matching_exactly(self):
        self.lua(r"""
local entries=A..'.o.1234ABCD.0.00000000'
local head='hd2bc/1;0.30.4-dev;F5FEE03DCFDB;811C9DC5;3;'
local ok=head..fnv1a(entries)..';'..entries
assert(P.decode(ok))
refuses(nil,'not text')
refuses('','length')
refuses(string.rep('a',513),'length')
refuses(ok..'\1','printable')
refuses('hd2as/1;0.30.4-dev;811C9DC5;3;'..A,'not hd2bc/1')
refuses(ok..';x','7 fields')
refuses(head..'00000000;'..entries,'digest does not match')
refuses(head..fnv1a(entries):lower()..';'..entries,'invalid digest')
refuses('hd2bc/1;0.30.4-dev;F5FEE03DCFD;811C9DC5;3;'..fnv1a(entries)..';'..entries,'build')
refuses('hd2bc/1;0.30.4-dev;F5FEE03DCFDB;811C9DC5;03;'..fnv1a(entries)..';'..entries,'sequence')
local function with(list)return head..fnv1a(list)..';'..list end
refuses(with(''),'invalid entry')
refuses(with(A:lower()..'.o.1234ABCD.0.00000000'),'invalid entry')
refuses(with(A..'.o.1234ABCD.0.00000001'),'invalid entry')
refuses(with(A..'.o.1234ABCD.00.00000000'),'invalid entry')
refuses(with(entries..','),'invalid entry')
refuses(with(B..'.o.1234ABCD.0.00000000,'..A..'.o.1234ABCD.0.00000000'),'ascending')
refuses(with(entries..','..entries),'ascending')
""")


class DecisionTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(SYNC + body + "\nreturn 'ok'"), b'ok')

    def test_no_member_state_allows_an_apply_on_this_build(self):
        self.lua(r"""
local function d(members,safe)return S.decide({members=members,remote_apply_safe=safe})end
local solo=d({})
assert(solo.allowed and solo.code=='SOLO')
-- Every member matches: still refused, the remote apply is unsafe on this build.
local all=d({{peer='A',state='match',host=true},{peer='B',state='match'}})
assert(not all.allowed and all.code=='REMOTE_APPLY_UNSAFE',all.code)
assert(all.reason:find('network type alone',1,true))
-- The build capability: empty (no build proven); the default decision reads it.
assert(next(S.REMOTE_APPLY_SAFE)==nil)
assert(S.decide({members={{peer='A',state='match'}}}).code=='REMOTE_APPLY_UNSAFE')
-- Only with a remote apply proven safe (none is) would every member matching allow it: the agreement rule.
local proven=d({{peer='A',state='match',host=true},{peer='B',state='match'}},true)
assert(proven.allowed and proven.code=='ALL_MATCH')
-- One missing, one different, pending, malformed, incompatible: refused with the member named.
assert(d({{peer='A',state='match'},{peer='B',state='no_runtime'}},true).code=='NO_RUNTIME')
local mm=d({{peer='A',state='mismatch',host=true},{peer='B',state='match'}},true)
assert(mm.code=='MISMATCH'and mm.reason=='mismatch: A (host)',mm.reason)
assert(d({{peer='A',state='pending'}},true).code=='PENDING')
assert(d({{peer='A',state='malformed'}},true).code=='MALFORMED')
assert(d({{peer='A',state='incompatible'}},true).code=='INCOMPATIBLE')
-- The order: what a member lacks first.
local order=d({{peer='A',state='pending'},{peer='B',state='mismatch'},{peer='C',state='no_runtime'}})
assert(order.code=='NO_RUNTIME'and order.reason=='no runtime: C',order.reason)
-- Host or client: the same rule (every member, the host included, must match).
assert(d({{peer='H',state='no_runtime',host=true}},true).reason=='no runtime: H (host)')
assert(d({{peer='C',state='no_runtime'}},true).code=='NO_RUNTIME')
""")

    def test_member_states_from_their_values(self):
        self.lua(r"""
local P=require('hd2runtime/runtime/beam_conversion_sync_protocol')
S.note(located({['LAS-16 Sickle']={}}))
local mine=assert(S.value())
local digest=S.digest()
assert(S.member_state(nil,digest,0,29.9)=='pending')
local st,why=S.member_state(nil,digest,0,30)
assert(st=='no_runtime'and why:find('no hd2bc value after 30 s',1,true))
assert(S.member_state(mine,digest,0,1)=='match')
assert(S.member_state('hd2bc/1;garbage',digest,0,1)=='malformed')
local d=assert(P.decode(mine))
local other=assert(P.encode({version='0.30.1',build=d.build,catalog=d.catalog,seq=1,entries=d.entries}))
assert(S.member_state(other,digest,0,1)=='incompatible')
local diff=assert(P.encode({version=d.version,build=d.build,catalog=d.catalog,seq=4,entries={}}))
assert(S.member_state(diff,digest,0,1)=='mismatch')
-- seq is not part of the agreement: the same set under another seq matches.
local reseq=assert(P.encode({version=d.version,build=d.build,catalog=d.catalog,seq=9,entries=d.entries}))
assert(S.member_state(reseq,digest,0,1)=='match')
""")

    def test_entries_of_a_located_state(self):
        self.lua(r"""
local fnv1a=require('hd2runtime/runtime/peer_protocol').fnv1a
local s=located({['LAS-16 Sickle']={},['AR-23 Liberator']={pair=2},['SMG-32 Reprimand']={state='orphaned'}})
local entries,names=S.entries_of(s)
assert(table.concat(names,',')=='AR-23 Liberator,LAS-16 Sickle,SMG-32 Reprimand',table.concat(names,','))
local by={}
for _,e in ipairs(entries)do by[S.weapon_of(e.resource)]=e end
assert(by['LAS-16 Sickle'].path=='o'and by['LAS-16 Sickle'].record==fnv1a(RECORD)and by['LAS-16 Sickle'].pair==0)
assert(by['AR-23 Liberator'].pair==2 and by['AR-23 Liberator'].rows==fnv1a(string.rep('\2',112)..string.rep('\3',76)))
assert(by['SMG-32 Reprimand'].path=='x'and by['SMG-32 Reprimand'].record=='00000000')
for i=2,#entries do assert(entries[i-1].resource<entries[i].resource)end
-- The shared path: the donor record, path s.
local sh=S.entries_of(located({['LAS-16 Sickle']={}},'shared'))
assert(sh[1].path=='s'and sh[1].record==fnv1a(C.trident.recordHex))
-- The catalogue hash is stable and the build is the executable's.
assert(S.catalogue_hash()==S.catalogue_hash()and#S.catalogue_hash()==8)
assert(S.build()==require('hd2runtime/schemas/current').exe_sha:sub(1,12))
""")


CHANNEL = EVENT_PRELUDE + r"""
local channel=require('hd2runtime/runtime/peer_channel')
local P=require('hd2runtime/runtime/beam_conversion_sync_protocol')
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
-- A member without a value and this machine with nothing converted: no line, but the state is kept.
assert(S.status().members[OTHER].state=='no_runtime')
assert(count('BEAM CONVERSION SYNC: member')==0)
""")

    def test_matching_members_are_still_refused_and_the_post_follows_every_change(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER},host=OTHER})
S.start()
S.note(located({['LAS-16 Sickle']={}}))
local mine=assert(S.value())
seconds(14)
assert(#posts()==1 and posts()[1]==mine,tostring(posts()[1]))
assert(count('BEAM CONVERSION SYNC: posting seq 1: LAS-16 Sickle')==1)
assert(W.lobby_keyed.hd2bc[LOCAL]==mine)
-- The other member posts the identical set (another seq): match, and the decision is still REFUSED.
local d=assert(P.decode(mine))
W.lobby_keyed.hd2bc[OTHER]=assert(P.encode({version=d.version,build=d.build,catalog=d.catalog,seq=5,
    entries=d.entries}))
seconds(3.5)
assert(S.status().members[OTHER].state=='match'and S.status().members[OTHER].host)
assert(count('BEAM CONVERSION SYNC: member '..OTHER..' (host): match')==1)
assert(count('BEAM CONVERSION SYNC: decision REFUSED (REMOTE_APPLY_UNSAFE)')==1)
assert(S.describe():find('REFUSED (REMOTE_APPLY_UNSAFE',1,true))
-- It has the Sickle converted: this player is warned not to spawn one (their game would crash), once per set.
assert(count('BEAM CONVERSION SYNC: WARNING: member '..OTHER..' has LAS-16 Sickle converted')==1)
assert(#NOTICES==1 and NOTICES[1]:find('LAS-16 Sickle',1,true))
seconds(10)
assert(count('WARNING: member')==1 and#NOTICES==1)
-- Their set changes (a different rate digest): mismatch.
W.lobby_keyed.hd2bc[OTHER]=assert(P.encode({version=d.version,build=d.build,catalog=d.catalog,seq=6,
    entries={{resource=d.entries[1].resource,path='o',record='00C0FFEE',pair=0,rows='00000000'}}}))
seconds(3.5)
assert(S.status().members[OTHER].state=='mismatch')
assert(count('decision REFUSED (MISMATCH): mismatch: '..OTHER..' (host)')==1)
-- This machine restores: the empty set is posted (the lobby keeps no stale set), seq 2, after the 5 s post interval.
S.note(located({}))
seconds(6)
local p=posts()
assert(#p==2 and P.decode(p[2]).seq==2 and#P.decode(p[2]).entries==0,tostring(p[2]))
assert(count('posting seq 2: nothing converted')==1)
-- An unchanged set is never posted again.
S.note(located({}))
seconds(20)
assert(#posts()==2)
-- The member leaves: solo, allowed.
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
-- A malformed value is refused whole.
W.lobby_keyed.hd2bc={[OTHER]='hd2bc/1;nonsense'}
seconds(3.5)
assert(S.status().members[OTHER].state=='malformed'and count('decision REFUSED (MALFORMED)')==1)
-- An older Runtime's value (another version): incompatible.
local d=assert(P.decode(S.value()))
W.lobby_keyed.hd2bc[OTHER]=assert(P.encode({version='0.30.1',build=d.build,catalog=d.catalog,seq=1,entries={}}))
seconds(3.5)
assert(S.status().members[OTHER].state=='incompatible'and count('decision REFUSED (INCOMPATIBLE)')==1)
-- Nothing this module does writes outside the lobby post.
for _,p in ipairs(R.lobby_posts)do assert(p.key=='hd2bc')end
""")


SNAPSHOT = SNAPSHOT_PRELUDE + r'''
local S=require('hd2runtime/runtime/beam_conversion_sync')
local P=require('hd2runtime/runtime/beam_conversion_sync_protocol')
local W=require('hd2runtime/runtime/beam_conversion_watch')
'''


class SnapshotJoinTests(unittest.TestCase):
    def test_joins_and_leaves_with_live_instances_follow_the_posted_set(self):
        result = snapshot_run(SNAPSHOT + r'''
local sickle,lib=weapon('LAS-16 Sickle'),weapon('AR-23 Liberator')
local out={}
-- Solo: both convert (the Liberator with its own rate and rows); the set to publish names both, with their details.
check(enable('sickle','LAS-16 Sickle').status=='complete','sickle')
check(enable('lib','AR-23 Liberator',{{field=F.beam.fire_rate,expect=300,value=600},
  {field=F.damage.player_standard_damage,expect=60,value=600}}).status=='complete','liberator')
local st=S.status()
out.both=table.concat(st.converted,', ')=='AR-23 Liberator, LAS-16 Sickle'and st.seq==2
local d=P.decode(assert(S.value()))
local by={}
for _,e in ipairs(d.entries)do by[S.weapon_of(e.resource)]=e end
out.details=by['AR-23 Liberator'].pair>0 and by['AR-23 Liberator'].path=='o'and by['LAS-16 Sickle'].pair==0
  and by['AR-23 Liberator'].record~=by['LAS-16 Sickle'].record
-- The digest is a pure function of the conversions: the same request on another machine gives the same value.
local first_digest=d.digest
-- Another player joins while the Liberator is in hand: the first read restores the idle Sickle at once.
LIVE[lib.roots[1].resource]=1
LOBBY.solo=false
W.tick_for_tests(1)
out.idle_restored_at_once=vanilla_ok(sickle)and converted_ok(lib)
st=S.status()
out.set_follows=#st.converted==1 and st.converted[1]=='AR-23 Liberator'and st.seq==3
-- The Liberator stays while live; restored on the next retry (RESTORE_EVERY) once it is no longer live.
LIVE[lib.roots[1].resource]=nil
W.tick_for_tests(1)
out.not_before_retry=converted_ok(lib)
W.tick_for_tests(5)
out.later_restored=vanilla_ok(lib)
-- An apply waits, and the refusal names the sync's decision (pending: the sync has not read the lobby yet).
local h=enable('again','LAS-16 Sickle')
local text=tostring(h.last_transient)
out.waits=waiting(h,'NOT_SOLO')and text:find('BEAM CONVERSION SYNC: REFUSED (PENDING',1,true)~=nil
out.even_identical=text:find('even when every player converted it the same way',1,true)~=nil
st=S.status()
out.empty_posted=#st.converted==0 and st.seq==4 and#P.decode(S.value()).entries==0
-- Solo again: the conversions apply again, and the same request gives the same digest as before.
LOBBY.solo=true
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
