"""Gas EAT payload provenance across machines (runtime/custom_mp_items.lua; runtime/projectile_impact.lua provenance;
runtime/custom_stratagems.lua; docs/research/runtime-peer-messaging-F5FEE03DCFDB.md section 14). Each test runs ONE
machine of a two-player lobby on the offline payload world (the projectile pool, the Gas Strike's chain, the network
id map), with the synced view stubbed as the other machine's Runtime published it. Every machine has its OWN entity ids
for the same launchers; network ids are the same everywhere.
  * the caller: its call's two launchers are bound with payload provenance (any wielder's rocket converts on this
    machine's own copy; the creditor is reported, never a gate) and their network ids published;
  * every other machine: the published launchers are correlated through ITS network id map (checked against its own
    registered definition, the call's beacon seen here, its thrower) and bound the same way: its own copy converts;
  * a vanilla EAT-17 stays vanilla everywhere; two calls are tracked independently; every write is one projectile
    copy's impact explosion in this machine's own pool; the synced selection's assets are requested once here;
  * a member leaving or the mission's end forgets the tracked launchers."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_gas_eat import IMPACT
from test_custom_mp_mission import example_addon

P1, P2 = '1111222233334444', '5555666677778888'

HARNESS = r"""
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
require('hd2runtime/runtime/spawned_instances').reset_for_tests()
assert(loadstring(EAT_ADDON,'@'..EAT_RESOURCE))()
local I=custom.internals_for_tests()
local mpm=require('hd2runtime/runtime/multiplayer');mpm.reset_for_tests()
local cmp=require('hd2runtime/runtime/custom_multiplayer');cmp.reset_for_tests()
local sync=require('hd2runtime/runtime/custom_mp_sync')
local mp_items=require('hd2runtime/runtime/custom_mp_items')
local P=require('hd2runtime/runtime/peer_protocol')
local pods=require('hd2runtime/runtime/support_pods')
local call_ins=require('hd2runtime/runtime/call_ins')
local BR=require('hd2runtime/runtime/beacon_redirect')
local selector=require('hd2runtime/runtime/stratagem_selector')
local assets=require('hd2runtime/core/assets')
local P1,P2='1111222233334444','5555666677778888'
local CARRIER=9
local PRECISION=require('hd2runtime/domains/stratagem_authoring').stratagems['Orbital Precision Strike'].root.id
-- This player selects the Gas EAT in loadout slot 0.
selector.set_virtual_slots_for_tests({slots={[0]={definition='eat17_gas',token=PRECISION,type=118}},
    pairs={PRECISION,1}})
require('hd2runtime/runtime/carrier_allocator').allocate_lobby=function(world,defs)
    local a={ready=true,refused={},order={},assignments={},verdicts={},candidates={},line='CUSTOM CARRIERS: test',
        reservations={}}
    for _,d in ipairs(defs)do
        a.order[#a.order+1]=d.id
        if d.id=='eat17_gas'then
            a.assignments[d.id]={label='Gas EAT',carrier='M-105 Stalwart',stable_id=902,type=CARRIER,family='support',
                owned=true}
        end
    end
    return a
end
-- The package system: requests recorded, every package resident once requested.
local RM=require('hd2runtime/domains/package_residency').loader.refcountMap
local map_header,map_entries=W.alloc(0x1000),W.alloc(0x1000)
W.write(map_header+RM.entries,W.u64(map_entries))
assets.reset()
assets.prove=function()return {instance=map_header,request=2,capacity=16}end
local REQUESTS=0
W.runtime.package_request=function()REQUESTS=REQUESTS+1 end
local function rec(peer,types)
    local e={{index=0,type=124,granted=1}}
    for k,t in ipairs(types)do e[#e+1]={index=k,type=t,granted=0}end
    return {peer=peer,entries=e}
end
local V
-- A launcher on THIS machine: its own entity id, the lobby-wide network id (k: its map entry, >= 8).
local function launcher(entity,network,k)
    W.add{entity=entity,type=EAT_TYPE,unit=0,health=1}
    W.register_entity(entity,EAT_TYPE)
    W.network_id(network,entity,k)
end
-- One machine of the lobby: `me` with the other player, host or client; both select the Gas EAT (slot 0). The mission
-- starts with custom multiplayer running (a client agreeing with the host's hashes).
local function machine(me,host)
    iworld()
    local other=me==P1 and P2 or P1
    W.players({{peer=me,avatar=100},{peer=other}},me)
    W.state(4,{host=host})
    local members={P1,P2}
    V={status='enabled',members=members,local_peer=me,host_peer=host and me or other,is_host=host,lobby='cv2:test',
        table={[me]={[0]='eat17_gas',[1]=false,[2]=false,[3]=false},[other]={[0]='eat17_gas',[1]=false,[2]=false,
        [3]=false}},local_seq=1,local_posted=true,
        peers={[other]={state='compatible',seq=1,slots={[0]='eat17_gas',[1]=false,[2]=false,[3]=false},items={}}}}
    V.table_hash=P.table_hash(V.table)
    sync.view=function()return V end
    cmp.first_records=function()return {rec(me,{118,22}),rec(other,{118,41})}end
    local world=assert(world_module.open())
    I.start_mission(world)
    local M=I.mission()
    if not host then
        V.host_hashes={table=V.table_hash,carrier=M.mp.carrier_hash}
        I.mp_step(world)
    end
    assert(M.mp.state=='running',tostring(M.mp.state))
    for _=1,3 do I.remote_assets_step()end
    tick()
    return world,M,other
end
-- The EAT-17's row (the delivery's type, resolved by its stable id): 147.
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local EAT17=custom.get('eat17_gas').delivery.id
local type_of=loadout.type_of
loadout.type_of=function(world,id)if id==EAT17 then return 147 end;return type_of(world,id)end
-- This machine's own Gas EAT call: its beacon (network id), then its pod's rack with the two launchers.
local function own_call(M,beacon_network,entities,networks)
    local d=custom.get('eat17_gas')
    local ctx=I.new_call(d,M.queue[1].assignment,0)
    ctx.beacon={entity=7000+beacon_network%100,network=beacon_network}
    pods.capture=function(spec,cb)
        cb({kind='pod',pod=501})
        cb({kind='captured',pod=501,rack=502,items=entities,types={EAT_TYPE,EAT_TYPE},slots={0,1},networks=networks,
            pod_network=beacon_network+1,rack_network=beacon_network+5})
        return {status='complete'}
    end
    I.start_capture(ctx,d)
    tick()
    return ctx
end
-- Another machine's Gas EAT call seen here: its carrier beacon (no state here) thrown by `thrower`.
local function remote_call(beacon_entity,beacon_network,thrower,kind,slot)
    kind=kind or CARRIER
    local beacons={}
    beacons[beacon_entity]={type=kind}
    BR.beacons=function()return beacons end
    pods.beacon_network=function(world,it)return beacon_network end
    require('hd2runtime/runtime/custom_mp_observer').remote_support=function()end
    call_ins.thrower=function()return {peer=thrower,entry=1+(slot or 0),slot=slot or 0,type=kind}end
    I.beacon_event({kind='created',beacon={entity=beacon_entity,type=kind,landed=false,timing={}}})
end
-- Every write since `from` is ONE projectile copy's impact explosion (+0x7C) in this machine's own pool.
local function only_copy_writes(from,n)
    local count=0
    for k=from+1,#W.runtime.writes do
        local w=W.runtime.writes[k]
        local rel=w.address-(W.projectile_system+H.base)
        assert(rel>=0 and rel%H.stride==H.impactExplosion and#w.bytes==4,'a write outside a projectile copy: '..w.address)
        count=count+1
    end
    assert(count==n,'writes: '..count..', expected '..n)
end
"""


def machine_lua(body):
    from support import lua as lua_literal
    eat, eat_addon = example_addon('GasEatExample')
    return run(WORLD + SLOT + PAYLOAD + IMPACT + 'local EAT_ADDON=' + lua_literal(eat_addon) + '\nlocal EAT_RESOURCE='
        + lua_literal(eat) + HARNESS + body + "\nreturn 'ok'")


class CallerMachineTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(machine_lua(body), b'ok')

    def test_the_callers_launchers_are_gas_whoever_fires_them_and_are_published(self):
        # P1 calls Gas EAT: P1's shot and P2's shot (P2 picked up P1's launcher) are both gas on P1's machine.
        self.lua(r"""
local world,M=machine(P1,true)
launcher(5001,4117,21);launcher(5002,4118,22)
local writes=#W.runtime.writes
local ctx=own_call(M,4114,{5001,5002},{4117,4118})
assert(#ctx.weapons==2 and count('eat17_gas#1: CUSTOM MP ITEMS: launcher network ids 4117, 4118 (call beacon network id '
    ..'4114) published to every compatible Runtime')==1,table.concat(logged,' | '))
-- Published: the call's items, ids and network ids only.
local out=mp_items.published(world)
assert(#out==1 and out[1].id=='eat17_gas'and out[1].beacon==4114 and out[1].items[1]==4117 and out[1].items[2]==4118)
assert(P.encode({version='0.30.0-dev',registry='0A1B2C3D',seq=2,slots={'eat17_gas'},items=out}):find(
    ';items:eat17_gas@4114=4117+4118',1,true))
-- P1 fires launcher 5001: gas.
local _,h1=fire(5001,{creditor=P1})
tick()
-- P2 picked up launcher 5002 and fires it: its rocket (P1's copy here, credited to P2) is gas too.
local _,h2=fire(5002,{creditor=P2})
tick()
assert(impact_of(h1)==82 and impact_of(h2)==82,'not gas: '..impact_of(h1)..', '..impact_of(h2))
assert(count('PROJECTILE CONVERTED: launcher 5001 (network id 4117)')==1 and count('fired by this machine\'s player')==1)
assert(count('PROJECTILE CONVERTED: launcher 5002 (network id 4118)')==1 and count('fired by another player who picked it '
    ..'up, '..P2..'; creditor '..P2..', the game\'s own')==1,table.concat(logged,' | '))
assert(count('creditor '..P2..', owner 100 (another player fired it: the payload follows its exact source')==1)
-- A vanilla EAT-17 fired by either player: vanilla.
local _,v1=fire(5003,{creditor=P1});local _,v2=fire(5003,{creditor=P2})
tick()
assert(impact_of(v1)==376 and impact_of(v2)==376)
only_copy_writes(writes,2)
""")

    def test_a_client_caller_converts_the_hosts_shot_from_its_launcher(self):
        # P2 (a client) calls Gas EAT, P1 (the host) picks up its launcher and fires: gas on the client's own copy.
        self.lua(r"""
local world,M=machine(P2,false)
assert(mpm.client_proof())
launcher(5001,4139,43);launcher(5002,4140,44)
local writes=#W.runtime.writes
own_call(M,4137,{5001,5002},{4139,4140})
local _,h=fire(5001,{creditor=P1})
tick()
assert(impact_of(h)==82,'the host\'s shot from the client\'s launcher: '..impact_of(h))
assert(count('PROJECTILE CONVERTED: launcher 5001 (network id 4139): its projectile')==1 and count('(a client; fired by '
    ..'another player who picked it up, '..P1)==1,table.concat(logged,' | '))
only_copy_writes(writes,1)
""")


class ObserverMachineTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(machine_lua(body), b'ok')

    def test_another_machines_launchers_are_correlated_by_network_id_and_gas_on_this_copy(self):
        # P1 (host) called Gas EAT; this is P2's machine (a client): other entity ids, the same network ids.
        self.lua(r"""
local world,M=machine(P2,false)
assert(REQUESTS>0 and count('CUSTOM MP ASSETS: eat17_gas resident for remote presentation/payload')==1,
    table.concat(logged,' | '))
local requested=REQUESTS
remote_call(8101,4114,P1)
launcher(6101,4117,21);launcher(6102,4118,22)
V.peers[P1].items={{id='eat17_gas',beacon=4114,items={4117,4118}}}
I.items_step(world)
assert(count('REMOTE CUSTOM ITEM: peer '..P1..', custom eat17_gas, launcher network id 4117 (entity 6101 on this machine), '
    ..'call beacon network id 4114: its rockets explode as Orbital Gas Strike\'s (explosion 82 instead of 376) on this '
    ..'machine\'s own copy, whoever fires it')==1,table.concat(logged,' | '))
assert(count('launcher network id 4118 (entity 6102 on this machine)')==1)
local s=mp_items.status()
assert(#s.tracked==2 and s.tracked[1].entity==6101 and s.tracked[2].entity==6102 and s.tracked[1].peer==P1)
-- Correlated once: the same items again bind nothing more.
I.items_step(world);I.items_step(world)
assert(count('REMOTE CUSTOM ITEM: peer '..P1..', custom eat17_gas, launcher network id 4117')==1)
tick()
local writes=#W.runtime.writes
-- P1 fires its launcher: this machine's copy (credited to P1) is gas.
local _,h1=fire(6101,{creditor=P1})
-- P2 (this machine's player) picked up P1's other launcher and fires it: its own rocket is gas.
local _,h2=fire(6102,{creditor=P2})
tick()
assert(impact_of(h1)==82 and impact_of(h2)==82,'not gas: '..impact_of(h1)..', '..impact_of(h2))
assert(count('REMOTE CUSTOM ITEM: peer '..P1..'\'s custom eat17_gas launcher network id 4117 (entity 6101 here): CONVERTED '
    ..'its projectile')==1 and count('(fired by '..P1..'; creditor '..P1)==1,table.concat(logged,' | '))
assert(count('launcher network id 4118 (entity 6102 here): CONVERTED its projectile')==1
    and count('fired by this machine\'s player, who picked it up')==1)
-- A vanilla EAT-17 here: vanilla, whoever fires it.
local _,v1=fire(5003,{creditor=P1});local _,v2=fire(5003,{creditor=P2})
tick()
assert(impact_of(v1)==376 and impact_of(v2)==376)
only_copy_writes(writes,2)
-- The assets were requested once (at the mission start), never again.
assert(REQUESTS==requested)
""")

    def test_two_calls_are_tracked_independently(self):
        self.lua(r"""
local world,M=machine(P1,true)
remote_call(8101,4114,P2)
remote_call(8102,4137,P2)
launcher(6101,4117,21);launcher(6102,4118,22);launcher(6201,4139,43);launcher(6202,4140,44)
V.peers[P2].items={{id='eat17_gas',beacon=4114,items={4117,4118}}}
I.items_step(world)
assert(#mp_items.status().tracked==2)
-- The second call arrives later (a new published state lists both).
V.peers[P2].items={{id='eat17_gas',beacon=4114,items={4117,4118}},{id='eat17_gas',beacon=4137,items={4139,4140}}}
I.items_step(world)
local s=mp_items.status()
assert(#s.tracked==4 and s.tracked[3].beacon==4137 and s.tracked[1].beacon==4114)
tick()
-- Each launcher has its own round: the first call's launchers fired, the second call's still bound.
local _,a=fire(6101,{creditor=P2});local _,b_=fire(6202,{creditor=P1})
tick()
assert(impact_of(a)==82 and impact_of(b_)==82)
local _,again=fire(6101,{creditor=P2})
tick()
assert(impact_of(again)==376,'one round per launcher')
""")

    def test_an_entry_that_does_not_check_out_is_refused_and_never_bound(self):
        self.lua(r"""
local world,M=machine(P2,false)
launcher(6101,4117,21);launcher(6102,4118,22)
-- No such call seen here (its beacon never observed): waits, then refused.
V.peers[P1].items={{id='eat17_gas',beacon=4114,items={4117}}}
I.items_step(world)
assert(#mp_items.status().tracked==0 and count('waiting for its beacon')==1,table.concat(logged,' | '))
-- The thrown ball names another thrower: refused.
remote_call(8101,4114,'9999999999999999')
I.items_step(world)
assert(count('REMOTE CUSTOM ITEM REFUSED: peer '..P1..', custom eat17_gas, call beacon network id 4114: the thrown ball '
    ..'names another thrower (9999999999999999)')==1,table.concat(logged,' | '))
-- A network id that names an entity of another type: refused, nothing bound.
remote_call(8102,4137,P1)
W.add{entity=6301,type='0000000000000042',unit=0,health=1};W.register_entity(6301,'0000000000000042')
W.network_id(4139,6301,43)
V.peers[P1].items={{id='eat17_gas',beacon=4137,items={4139}}}
I.items_step(world)
assert(count('launcher network id 4139: it names entity 6301 of type 0000000000000042 here, not the delivery\'s launcher')
    ==1,table.concat(logged,' | '))
-- A launcher that never replicates: refused after the wait.
remote_call(8103,4150,P1)
V.peers[P1].items={{id='eat17_gas',beacon=4150,items={4151}}}
I.items_step(world)
assert(count('waiting for its launchers\' replication')==1)
for _=1,(mp_items.WAIT/custom.STEP)+4 do tick(4)I.items_step(world)end
assert(count('launcher network id 4151: it never resolved through this machine\'s network id map')==1,
    table.concat(logged,' | '))
-- A player whose synced picks do not select the id: refused.
V.table[P1]={[0]=false,[1]=false,[2]=false,[3]=false}
remote_call(8104,4160,P1)
V.peers[P1].items={{id='eat17_gas',beacon=4160,items={4117}}}
I.items_step(world)
assert(count('call beacon network id 4160: that player\'s synced picks (frozen at the mission start) do not select it')==1,
    table.concat(logged,' | '))
assert(#mp_items.status().tracked==0,'nothing bound')
""")

    def test_a_member_leaving_and_the_missions_end_forget_the_tracked_launchers(self):
        self.lua(r"""
local world,M=machine(P2,false)
remote_call(8101,4114,P1)
launcher(6101,4117,21);launcher(6102,4118,22)
V.peers[P1].items={{id='eat17_gas',beacon=4114,items={4117,4118}}}
I.items_step(world)
assert(#mp_items.status().tracked==2)
tick()
-- P1 leaves: its launchers are forgotten here; their rockets stay vanilla on this machine.
V.members={P2};V.peers={}
I.items_step(world)
assert(#mp_items.status().tracked==0 and count('REMOTE CUSTOM ITEM: peer '..P1..' left the lobby: its 2 tracked '
    ..'launchers forgotten on this machine')==1,table.concat(logged,' | '))
tick()
local _,h=fire(6101,{creditor=P2})
tick()
assert(impact_of(h)==376)
-- Back in a new state: re-correlated; then the mission ends: everything forgotten, nothing published.
V.members={P1,P2};V.peers={[P1]={state='compatible',seq=2,slots={[0]='eat17_gas'},items={{id='eat17_gas',beacon=4114,
    items={4118}}}}}
I.items_step(world)
assert(#mp_items.status().tracked==1)
launcher(5001,4139,43)
own_call(M,4137,{5001},{4139})
assert(#mp_items.published(world)==1)
I.mission_end(world)
local s=mp_items.status()
assert(#s.tracked==0 and#s.entries==0 and#mp_items.published(world)==0)
W.state(3);tick(2)
assert(#require('hd2runtime/runtime/projectile_impact').active()==0)
""")


class CondensedExpendableTests(unittest.TestCase):
    """The condensed expendable carrier (EAT-17G on the EAT-700 / EAT-411: one vanilla stratagem as beacon, clone and
    pod; live-proven solo) across machines through the SAME launcher provenance as the live-proven r3 Gas EAT: the
    caller publishes its pod's launchers by network id, every other compatible Runtime (which cloned the same carrier
    weapon for the same synced id) correlates them and converts its OWN copy of their rockets, whoever fires them."""
    def lua(self, body):
        self.assertEqual(machine_lua(body), b'ok')

    def test_another_players_condensed_eat17g_launchers_are_gas_on_this_machines_copy(self):
        self.lua(r"""
local catalog=require('hd2runtime/domains/stratagem_authoring')
local EAT17,EAT411='EAT-17 Expendable Anti-Tank','EAT-411 Leveller'
local ID411=catalog.stratagems[EAT411].root.id
local d=custom.register({id='eat17g',name='EAT-17G GAS',name_cased='EAT-17G Gas',description='Two launchers.',
    icon='eat17g',code={'down','down','up','up','left','right'},cooldown=70,
    carrier={beacon='support',prefer_families={'support','backpack'}},
    delivery={family='expendable',weapon={weapon=EAT17},modify={impact_explosion='Orbital Gas Strike'}}},'mods/test/eat17g')
assert(custom.mirrored(d)and custom.remote_handler(d)~=nil,'an expendable payload is mirrored by the launcher handler')
local world,M=machine(P1,true)
-- This machine clones the same carrier weapon for the synced id (every machine does: runtime/custom_stratagems.lua
-- mp_queue), here EAT-411 Leveller (condensed).
local clone=require('hd2runtime/runtime/weapon_clone')
local cp=require('hd2runtime/runtime/carrier_presentation')
clone.apply=function(s,cb)cb({status='applied'});return {status='applied'}end
cp.apply=function(s,cb)cb({status='applied'});return {status='applied'}end
assets.gate=function()return {tick=function()return'ready'end}end
I.add_clone(d,{weapon={weapon=EAT411,stable_id=ID411},condensed=true})
for _=1,3 do I.clone_step(world)end
assert(M.clones.eat17g.state=='ready',tostring(M.clones.eat17g.state))
-- The frozen carrier map names the EAT-411's own stratagem (condensed) as eat17g's carrier; P2 selects it in slot 1.
M.carrier_types[16]='eat17g'
V.table[P2][1]='eat17g'
M.remote_assets.eat17g={state='ready'}
-- P2 calls it: its beacon (the EAT-411's own beam), its pod's two launchers (the EAT-411 type: the clone).
remote_call(8301,4337,P2,16,1)
local LEV='7617642765AC38C7'
for k,e in ipairs({6301,6302})do
    W.add{entity=e,type=LEV,unit=0,health=1};W.register_entity(e,LEV);W.network_id(4338+k,e,50+k)
end
V.peers[P2].items={{id='eat17g',beacon=4337,items={4339,4340}}}
I.items_step(world)
assert(count('REMOTE CUSTOM ITEM: peer '..P2..', custom eat17g, launcher network id 4339 (entity 6301 on this machine), '
    ..'call beacon network id 4337: its rockets explode as Orbital Gas Strike\'s (explosion 82 instead of 376) on this '
    ..'machine\'s own copy, whoever fires it')==1,table.concat(logged,' | '))
tick()
local writes=#W.runtime.writes
-- P2's own shot and this player's (who picked the second launcher up): gas on this copy; a vanilla EAT-17: vanilla.
local _,r1=fire(6301,{creditor=P2});local _,r2=fire(6302,{creditor=P1});local _,v=fire(5003,{creditor=P1})
tick()
assert(impact_of(r1)==82 and impact_of(r2)==82 and impact_of(v)==376,('%d %d %d'):format(impact_of(r1),impact_of(r2),
    impact_of(v)))
only_copy_writes(writes,2)
-- Their provenance (runtime/custom_provenance.lua): two launchers of eat17g, realized on this machine.
local prov=require('hd2runtime/runtime/custom_provenance').list({custom_id='eat17g'})
assert(#prov==2 and prov[1].role=='launcher'and prov[1].network_id==4339 and prov[1].realized and prov[1].entity==6301)
-- A real EAT-17 published as one of its items is never this call's launcher.
V.peers[P2].items={{id='eat17g',beacon=4337,items={4339,4340}},{id='eat17g',beacon=4441,items={4442}}}
W.network_id(4442,5003,60)
remote_call(8302,4441,P2,16,1)
I.items_step(world)
assert(count('launcher network id 4442: it names entity 5003 of type '..EAT_TYPE..' here, not the delivery\'s launcher')==1,
    table.concat(logged,' | '))
""")


if __name__ == '__main__':
    unittest.main()
