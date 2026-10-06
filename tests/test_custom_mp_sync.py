"""Custom stratagem multiplayer state over the peer channel (runtime/custom_mp_sync.lua; docs/research/runtime-peer-
messaging-F5FEE03DCFDB.md sections 3 and 10), on the offline event world with a two-member lobby (tests/event_world_
fixture.lua W.lobby; the channel's two engine calls recorded, the service a table):
  * this machine publishes its current picks (seq + 1 on every change, never an unchanged value) and reads the other
    member's: both semantic ids in one table, not tokens;
  * a clear, a replacement and a reset are just new states; a stale (lower seq) value is ignored;
  * a malformed value, an unregistered id, another Runtime version or registry: that member's custom state is ignored
    and custom multiplayer is unavailable; a member with no value is waited for, then reported;
  * the session host's hashes: a client agrees, differs or waits; a host field from a non-host member is ignored;
  * the canonical table, its hash and the native picks are independent of member, record and slot order."""
import unittest

from support import run
from test_event_scripting import PRELUDE

HARNESS = PRELUDE + r"""
local channel=require('hd2runtime/runtime/peer_channel');channel.reset_for_tests()
local sync=require('hd2runtime/runtime/custom_mp_sync');sync.reset_for_tests()
local P=require('hd2runtime/runtime/peer_protocol')
local scheduler=require('hd2runtime/runtime/scheduler')
local R=W.runtime
W.players({{peer=LOCAL,avatar=100},{peer=OTHER}},LOCAL)
local function in_update(fn)
    local out
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick()out={fn()};watch.status='complete'end
    scheduler.attach(watch);tick()
    return unpack(out)
end
local function seconds(s)tick(math.floor(s/0.125+0.5))end
local KNOWN={eat17_gas=true,orbital_gas_barrage=true,pelican_close_air_support=true}
local VERSION,REGISTRY='0.30.0-dev','0A1B2C3D'
local OPTS={known=KNOWN,version=VERSION,registry=REGISTRY}
local now=0
local function publish(slots,host)
    return in_update(function()return sync.publish({version=VERSION,registry=REGISTRY,slots=slots,host=host})end)
end
local function poll(mission)
    now=now+3
    local o={};for k,v in pairs(OPTS)do o[k]=v end;o.mission=mission
    return in_update(function()return sync.poll(assert(world_module.open()),now,o)end)
end
local function value(seq,slots,host)
    return('hd2rt/1;%s;%s;%d;%s'):format(VERSION,REGISTRY,seq,slots or'-,-,-,-')..(host and(';host:'..host)or'')
end
"""


class SyncTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body + "\nreturn 'ok'"), b'ok')

    def test_both_machines_picks_reach_one_table_with_their_semantic_ids(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER},host=LOCAL})
publish({[1]='pelican_close_air_support',[2]='orbital_gas_barrage',[3]='eat17_gas'})
seconds(11)
assert(#R.lobby_posts==1 and R.lobby_posts[1].value==value(1,'-,pelican_close_air_support,orbital_gas_barrage,eat17_gas'),
    tostring(R.lobby_posts[1]and R.lobby_posts[1].value))
W.lobby_values[OTHER]=value(4,'eat17_gas,-,-,-')
local v=poll()
assert(v.status=='enabled',v.status..': '..tostring(v.reason))
assert(v.is_host and v.host_peer==LOCAL and v.local_peer==LOCAL)
assert(v.table[LOCAL][1]=='pelican_close_air_support'and v.table[LOCAL][3]=='eat17_gas'and v.table[LOCAL][0]==false)
assert(v.table[OTHER][0]=='eat17_gas'and v.table[OTHER][1]==false)
assert(v.table_hash==P.table_hash({[LOCAL]={[1]='pelican_close_air_support',[2]='orbital_gas_barrage',[3]='eat17_gas'},
    [OTHER]={[0]='eat17_gas'}}))
assert(count('CUSTOM MP STATE (aboard the ship, lobby cv2:fixture): P1 '..LOCAL..' (you, host): -,pelican_close_air_support,'
    ..'orbital_gas_barrage,eat17_gas; P2 '..OTHER..': eat17_gas,-,-,-; custom multiplayer ENABLED: 2 compatible '
    ..'Runtimes (0.30.0-dev, registry 0A1B2C3D); table hash '..v.table_hash)==1,table.concat(logged,' | '))
-- Logged on change only.
poll();assert(count('CUSTOM MP STATE')==1)
assert(sync.table_ids(v.table)[1]=='eat17_gas'and#sync.table_ids(v.table)==3)
""")

    def test_a_clear_a_replacement_and_a_reset_are_new_states_and_nothing_repeats(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
publish({[0]='eat17_gas'});seconds(11)
assert(#R.lobby_posts==1)
assert(publish({[0]='eat17_gas'})==nil,'unchanged: not published')
publish({});seconds(6)                                       -- cleared (replaced by a vanilla pick)
assert(#R.lobby_posts==2 and R.lobby_posts[2].value==value(2),R.lobby_posts[2]and R.lobby_posts[2].value)
publish({[0]='orbital_gas_barrage',[1]='orbital_gas_barrage'});seconds(6)   -- a replacement, twice the same id
assert(#R.lobby_posts==3 and R.lobby_posts[3].value==value(3,'orbital_gas_barrage,orbital_gas_barrage,-,-'))
publish({});publish({[2]='eat17_gas'});seconds(6)          -- a reset then a new pick inside one interval
assert(#R.lobby_posts==4 and R.lobby_posts[4].value==value(5,'-,-,eat17_gas,-'),R.lobby_posts[4].value)
assert(sync.mine().seq==5)
""")

    def test_stale_malformed_unregistered_and_incompatible_values_are_never_trusted(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
publish({[0]='eat17_gas'})
W.lobby_values[OTHER]=value(5,'orbital_gas_barrage,-,-,-')
assert(poll().status=='enabled')
-- A lower seq is stale: ignored, the table keeps seq 5.
W.lobby_values[OTHER]=value(3,'eat17_gas,-,-,-')
local v=poll()
assert(v.status=='enabled'and v.table[OTHER][0]=='orbital_gas_barrage')
assert(count('CUSTOM MP: '..OTHER..': a stale value (seq 3 after 5) is ignored')==1)
-- Malformed: that member's custom state is ignored; custom multiplayer unavailable.
W.lobby_values[OTHER]='hd2rt/1;'..VERSION..';'..REGISTRY..';6;0x7ff6086d0000,-,-,-'
v=poll()
assert(v.status=='unavailable'and v.reason:find('invalid (MALFORMED: slot 0)',1,true)and next(v.table)==nil,v.reason)
assert(count('custom multiplayer UNAVAILABLE')==1 and count('can coexist as vanilla-only')==1)
-- An id not registered here.
W.lobby_values[OTHER]=value(7,'zzz_not_registered,-,-,-')
v=poll()
assert(v.status=='unavailable'and v.reason:find('UNKNOWN_ID',1,true),v.reason)
-- Another registry, another Runtime version.
W.lobby_values[OTHER]=('hd2rt/1;%s;%s;8;-,-,-,-'):format(VERSION,'FFFFFFFF')
v=poll()
assert(v.reason:find('incompatible (registry hash differs: theirs FFFFFFFF, mine 0A1B2C3D)',1,true),v.reason)
W.lobby_values[OTHER]=('hd2rt/1;%s;%s;9;-,-,-,-'):format('0.31.0',REGISTRY)
v=poll()
assert(v.reason:find('runtime version differs: theirs 0.31.0, mine 0.30.0-dev',1,true),v.reason)
-- Back to a compatible state.
W.lobby_values[OTHER]=value(10,'eat17_gas,-,-,-')
assert(poll().status=='enabled')
""")

    def test_a_transient_read_error_never_leaves_a_member_invalid(self):
        # The r9 sticky-invalid bug: a read error marked the member invalid but kept its cached value, so the next good
        # read of that same value was skipped as unchanged and the member stayed invalid (under r9: custom stratagems
        # DISABLED lobby-wide) until it posted a new state. A read error is the transport, not the member's state.
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
publish({[0]='eat17_gas'})
local good=value(5,'orbital_gas_barrage,-,-,-')
W.lobby_values[OTHER]=good
local v=poll()
assert(v.status=='enabled'and#v.incompatible==0)
-- One unreadable read (a value read while it is rewritten: not printable ASCII): the member keeps its last state.
W.lobby_values[OTHER]=good..'\1'
v=poll()
assert(v.status=='enabled'and#v.incompatible==0 and v.peers[OTHER].state=='compatible',v.status..' '..tostring(v.reason))
-- The same value reads again: still compatible (it was never invalid).
W.lobby_values[OTHER]=good
v=poll()
assert(v.status=='enabled'and v.table[OTHER][0]=='orbital_gas_barrage')
-- Unreadable for longer than READ_ERROR_GRACE: invalid (fail closed: a state nobody can read is not trusted).
W.lobby_values[OTHER]=good..'\1'
local polls=0
repeat v=poll();polls=polls+1 until v.peers[OTHER].state=='invalid'or polls>10
assert(v.peers[OTHER].state=='invalid'and v.status=='unavailable'and#v.incompatible==1,v.status)
assert(polls*3>=sync.READ_ERROR_GRACE and v.reason:find('not printable ASCII',1,true),v.reason)
-- The member's unchanged value reads again (same seq 5): compatible at once, not stuck invalid.
W.lobby_values[OTHER]=good
v=poll()
assert(v.status=='enabled'and#v.incompatible==0 and v.peers[OTHER].state=='compatible'
    and v.table[OTHER][0]=='orbital_gas_barrage',v.status..' '..tostring(v.reason))
""")

    def test_a_member_without_a_value_is_waited_for_then_reported(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
publish({[0]='eat17_gas'})
local v=poll()
assert(v.status=='waiting'and v.reason:find(OTHER,1,true),v.status)
now=now+sync.MISSING_GRACE
v=poll()
assert(v.status=='unavailable'and v.reason:find('no hd2rt value',1,true),v.reason)
-- Alone in the lobby: solo.
W.lobby({members={LOCAL}})
assert(poll().status=='solo')
""")

    def test_a_client_agrees_differs_or_waits_for_the_session_hosts_hashes(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER},host=OTHER})
publish({[0]='eat17_gas'})
W.lobby_values[OTHER]=value(1,'eat17_gas,-,-,-')
local v=poll()
assert(v.status=='enabled'and not v.is_host and v.host_peer==OTHER)
assert(sync.agreement(v,v.table_hash,'11111111').status=='waiting')
W.lobby_values[OTHER]=value(2,'eat17_gas,-,-,-',v.table_hash..':11111111')
v=poll()
assert(v.host_hashes.table==v.table_hash and v.host_hashes.carrier=='11111111')
assert(sync.agreement(v,v.table_hash,'11111111').status=='agree')
local d=sync.agreement(v,v.table_hash,'22222222')
assert(d.status=='differ'and d.field=='carrier'and d.host=='11111111'and d.mine=='22222222')
d=sync.agreement(v,'33333333','11111111')
assert(d.status=='differ'and d.field=='table')
-- The host itself: nothing to compare.
W.lobby({members={LOCAL,OTHER},host=LOCAL})
v=poll()
assert(v.is_host and sync.agreement(v,v.table_hash,'x').status=='host')
-- A host field from a member that is not the session host is ignored.
assert(count('CUSTOM MP: '..OTHER..' publishes a host field but is not the session host ('..LOCAL..'): ignored')==1)
assert(v.host_hashes==nil,'the host\'s own hashes are only what it publishes')
""")

    def test_this_machines_row_is_its_current_state_inside_one_read_interval(self):
        # The live crash of 2026-10-04: a view cached between reads kept this machine's row from before a publish.
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
publish({})
W.lobby_values[OTHER]=value(1)
assert(poll().status=='enabled')
-- A pick, published in the same Runtime step, with NO new read (inside the 2 s interval): the view has it.
publish({[0]='eat17_gas',[2]='pelican_close_air_support'})
local v=in_update(function()return sync.poll(assert(world_module.open()),now,OPTS)end)
assert(v.table[LOCAL][0]=='eat17_gas'and v.table[LOCAL][2]=='pelican_close_air_support',sync.slots_text(v.table[LOCAL]))
assert(v.table_hash==P.table_hash({[LOCAL]={[0]='eat17_gas',[2]='pelican_close_air_support'},[OTHER]={}}))
-- The view is a snapshot: changing it changes nothing, and the next view is built afresh.
v.table[LOCAL][0]='orbital_gas_barrage';v.peers[OTHER].state='invalid'
local w=in_update(function()return sync.poll(assert(world_module.open()),now,OPTS)end)
assert(w~=v and w.table[LOCAL][0]=='eat17_gas'and w.peers[OTHER].state=='compatible')
""")

    def test_both_peers_changing_before_the_next_post_publish_only_the_newest_state(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
publish({});seconds(11)
assert(#R.lobby_posts==1)
W.lobby_values[OTHER]=value(1)
assert(poll().status=='enabled')
-- Inside one post interval: three local states and two remote ones.
publish({[0]='eat17_gas'});publish({[0]='eat17_gas',[1]='orbital_gas_barrage'});publish({[1]='orbital_gas_barrage'})
W.lobby_values[OTHER]=value(2,'eat17_gas,-,-,-');poll()
W.lobby_values[OTHER]=value(3,'pelican_close_air_support,-,-,-')
seconds(6)
local v=poll()
-- One post: the newest local state (seq 4); the intermediate ones were never posted.
assert(#R.lobby_posts==2 and R.lobby_posts[2].value==value(4,'-,orbital_gas_barrage,-,-'),R.lobby_posts[2].value)
assert(v.table[LOCAL][1]=='orbital_gas_barrage'and v.table[OTHER][0]=='pelican_close_air_support')
assert(count('CUSTOM MP PUBLISH posted seq 4: -,orbital_gas_barrage,-,-')==1,table.concat(logged,' | '))
assert(count('CUSTOM MP PUBLISH posted seq 2')==0 and count('CUSTOM MP PUBLISH posted seq 3')==0)
""")

    def test_a_member_joining_or_leaving_while_a_post_is_pending(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
publish({[0]='eat17_gas'})
W.lobby_values[OTHER]=value(1,'orbital_gas_barrage,-,-,-')
assert(poll().status=='enabled')
-- Not posted yet (the join delay): a third member joins.
local THIRD='9999AAAABBBBCCCC'
W.lobby({members={LOCAL,OTHER,THIRD}})
local v=poll()
assert(v.status=='waiting'and v.reason:find(THIRD,1,true)and v.table[LOCAL]==nil,v.status)
-- It leaves again before posting anything: enabled again, the other member's state kept, this machine's still current.
W.lobby({members={LOCAL,OTHER}})
v=poll()
assert(v.status=='enabled'and v.table[LOCAL][0]=='eat17_gas'and v.table[OTHER][0]=='orbital_gas_barrage')
-- The other member leaves while this machine's post is pending; comes back with a fresh session (seq 1 again).
W.lobby({members={LOCAL}})
assert(poll().status=='solo')
W.lobby({members={LOCAL,OTHER}})
W.lobby_values[OTHER]=value(1,'eat17_gas,-,-,-')
v=poll()
assert(v.status=='enabled'and v.table[OTHER][0]=='eat17_gas','a member that came back is read afresh, not stale')
seconds(11)
assert(#R.lobby_posts>=1 and R.lobby_posts[#R.lobby_posts].value==value(1,'eat17_gas,-,-,-'))
""")

    def test_call_items_are_published_on_change_and_reach_each_compatible_peer_as_copies(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER},host=LOCAL})
local function publish_items(items)
    return in_update(function()return sync.publish({version=VERSION,registry=REGISTRY,slots={[0]='eat17_gas'},
        items=items})end)
end
publish_items(nil);seconds(11)
assert(#R.lobby_posts==1 and R.lobby_posts[1].value==value(1,'eat17_gas,-,-,-'))
-- A delivered call: its items are a new state (seq + 1); the same items again are not.
local items={{id='eat17_gas',beacon=4114,items={4117,4118}}}
publish_items(items);seconds(6)
assert(#R.lobby_posts==2 and R.lobby_posts[2].value==value(2,'eat17_gas,-,-,-')..';items:eat17_gas@4114=4117+4118',
    tostring(R.lobby_posts[2]and R.lobby_posts[2].value))
assert(publish_items({{id='eat17_gas',beacon=4114,items={4117,4118}}})==nil,'unchanged: never posted again')
items[1].items[1]=1   -- the caller's table: never aliased by the published state
assert(sync.mine().items[1].items[1]==4117)
-- More calls than a value lists: the newest are kept.
local many={}
for k=1,6 do many[k]={id='eat17_gas',beacon=5000+k,items={6000+k}}end
publish_items(many)
assert(#sync.mine().items==P.MAX_ITEM_CALLS and sync.mine().items[1].beacon==5003 and sync.mine().items[4].beacon==5006)
-- The other member's items reach the view, copied; an incompatible member's never.
W.lobby_values[OTHER]=value(4,'eat17_gas,-,-,-')..';items:eat17_gas@601=602+603'
local v=poll(true)
local q=v.peers[OTHER]
assert(v.status=='enabled'and#q.items==1 and q.items[1].id=='eat17_gas'and q.items[1].beacon==601
    and q.items[1].items[2]==603)
q.items[1].items[1]=1
assert(poll(true).peers[OTHER].items[1].items[1]==602,'the view is a copy')
W.lobby_values[OTHER]=('hd2rt/1;0.30.1-dev;%s;5;eat17_gas,-,-,-;items:eat17_gas@601=602'):format(REGISTRY)
poll(true);v=poll(true)
assert(v.peers[OTHER].state=='incompatible'and#v.peers[OTHER].items==0)
-- An unregistered id in the items: the whole value is invalid, never partly applied.
W.lobby_values[OTHER]=value(6,'eat17_gas,-,-,-')..';items:zzz_other@601=602'
poll(true);v=poll(true)
assert(v.peers[OTHER].state=='invalid'and#v.peers[OTHER].items==0)
""")

    def test_a_fast_read_follows_a_remote_mirrored_call(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER},host=LOCAL})
publish({[0]='eat17_gas'});seconds(11)
W.lobby_values[OTHER]=value(1,'eat17_gas,-,-,-')
local world=assert(world_module.open())
local reads=0
local read=R.native_lobby_read
R.native_lobby_read=function(...)reads=reads+1;return read(...)end
local function at(t,fast)
    local o={known=KNOWN,version=VERSION,registry=REGISTRY,mission=true,fast=fast}
    in_update(function()return sync.poll(world,t,o)end)
    return reads
end
at(100)
local n=reads
-- In a mission: every POLL_MISSION s; with fast: every POLL_FAST s.
at(101);at(102)
assert(reads==n,'no read inside the mission interval')
at(101.5,true)
assert(reads>n,'a fast read')
n=reads
at(101.7,true)
assert(reads==n,'not faster than POLL_FAST')
at(102.1,true)
assert(reads>n)
""")

    def test_the_table_and_the_native_picks_do_not_depend_on_any_order(self):
        self.lua(r"""
local A,B,C='000000000000000A','000000000000000B','000000000000000C'
local t1={[A]={[0]='eat17_gas',[1]=false,[2]='eat17_gas',[3]=false},[B]={[0]=false,[1]='orbital_gas_barrage'},
    [C]={[3]='eat17_gas'}}
local t2={[C]={[3]='eat17_gas',[0]=false},[B]={[1]='orbital_gas_barrage'},[A]={[2]='eat17_gas',[0]='eat17_gas'}}
assert(P.table_hash(t1)==P.table_hash(t2))
local ids=sync.table_ids(t1)
assert(#ids==2 and ids[1]=='eat17_gas'and ids[2]=='orbital_gas_barrage','one entry per custom id')
-- Records: granted defaults (granted ~= 0), then the loadout slots in order. Types 118 = the token; others native.
local function rec(peer,types,granted)
    local e={}
    for k,t in ipairs(granted or{124})do e[#e+1]={index=k-1,type=t,granted=1}end
    for k,t in ipairs(types)do e[#e+1]={index=#e,type=t,granted=0}end
    return {peer=peer,entries=e}
end
local function id_of(t)return 1000+t end
local r1={rec(A,{118,22,118,130}),rec(B,{41,118}),rec(C,{136,7,9,118})}
-- The same records in another order, with their entries shuffled.
local function shuffled(r)
    local e={};for k=#r.entries,1,-1 do e[#e+1]=r.entries[k]end
    return {peer=r.peer,entries=e}
end
local r2={shuffled(r1[3]),shuffled(r1[1]),shuffled(r1[2])}
local p1,c1=sync.native_present(r1,t1,id_of)
local p2,c2=sync.native_present(r2,t2,id_of)
local function keys(set)local out={};for k in pairs(set)do out[#out+1]=k end;table.sort(out);return table.concat(out,',')end
assert(keys(p1)==keys(p2),keys(p1)..' / '..keys(p2))
-- Custom slots never count as native picks (whatever they hold); every other entry does, granted ones too.
assert(keys(p1)=='1007,1009,1022,1041,1124,1130,1136',keys(p1))
assert(#c1==4 and#c2==4)
assert(c1[1].peer==A and c1[1].slot==0 and c1[1].type==118 and c1[1].id=='eat17_gas')
assert(c1[4].peer==C and c1[4].slot==3 and c1[4].type==118)
""")


if __name__ == '__main__':
    unittest.main()
