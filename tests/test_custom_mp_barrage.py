"""The native Orbital Gas Barrage across machines (runtime/custom_barrages.lua; runtime/custom_mp_items.lua barrage
handler; runtime/custom_stratagems.lua start_barrage; docs/research/runtime-peer-messaging-F5FEE03DCFDB.md section 15),
each test ONE machine of a two-player lobby on the offline payload world (the projectile pool with the 120mm's shell rows
194 and 137, the Gas Strike's chain, the network id map, the bombardment manager), with the synced view stubbed as the
other machine's Runtime published it:
  * the caller (host or client): its beacon's delivery becomes the 120mm's own; the ONE new 120mm barrage after its
    activation is its call's (two refuse); that barrage's shells (and no other's) explode as the Gas Strike's on this
    machine's own copies (credit the game's own); its network id is published;
  * every other machine: the published barrage is correlated through ITS network id map and checked against its own
    bombardment instances, then its own copies of that barrage's shells convert; a vanilla 120mm barrage stays vanilla;
  * the Gas EAT (live-proven r3) keeps exactly its behaviour with the barrage and the Pelican registered beside it."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_gas_eat import IMPACT
from test_custom_mp_mission import example_addon
import test_custom_mp_items as items

HARNESS = items.HARNESS.replace(
    "assert(loadstring(EAT_ADDON,'@'..EAT_RESOURCE))()",
    "assert(loadstring(EAT_ADDON,'@'..EAT_RESOURCE))()\nassert(loadstring(GAS_ADDON,'@'..GAS_RESOURCE))()\n"
    "assert(loadstring(PELICAN_ADDON,'@'..PELICAN_RESOURCE))()").replace(
    "selector.set_virtual_slots_for_tests({slots={[0]={definition='eat17_gas',token=PRECISION,type=118}},\n"
    "    pairs={PRECISION,1}})",
    "selector.set_virtual_slots_for_tests({slots={[0]={definition='eat17_gas',token=PRECISION,type=118},\n"
    "    [1]={definition='orbital_gas_barrage',token=PRECISION,type=118}},pairs={PRECISION,PRECISION,1}})").replace(
    """        if d.id=='eat17_gas'then""",
    """        if d.id=='orbital_gas_barrage'then
            a.assignments[d.id]={label='Gas Barrage',carrier='Orbital Airburst Strike',stable_id=1560416221,type=83,
                family='orbital',owned=true}
        end
        if d.id=='eat17_gas'then""").replace(
    "        table={[me]={[0]='eat17_gas',[1]=false,[2]=false,[3]=false},[other]={[0]='eat17_gas',[1]=false,[2]=false,\n"
    "        [3]=false}},local_seq=1,local_posted=true,\n"
    "        peers={[other]={state='compatible',seq=1,slots={[0]='eat17_gas',[1]=false,[2]=false,[3]=false},items={}}}}",
    "        table={[me]={[0]='eat17_gas',[1]='orbital_gas_barrage',[2]=false,[3]=false},[other]={[0]='eat17_gas',\n"
    "        [1]='orbital_gas_barrage',[2]=false,[3]=false}},local_seq=1,local_posted=true,\n"
    "        peers={[other]={state='compatible',seq=1,slots={[0]='eat17_gas',[1]='orbital_gas_barrage',[2]=false,\n"
    "        [3]=false},items={}}}}").replace(
    "    cmp.first_records=function()return {rec(me,{118,22}),rec(other,{118,41})}end",
    "    cmp.first_records=function()return {rec(me,{118,118,22}),rec(other,{118,118,41})}end")
for marker in ("GAS_ADDON", "orbital_gas_barrage'then", "[1]='orbital_gas_barrage',[2]=false,\n        [3]=false},items",
        "rec(me,{118,118,22})"):
    assert marker in HARNESS, marker

BARRAGE = r"""
local barrages=require('hd2runtime/runtime/custom_barrages');barrages.reset_for_tests()
local BR=require('hd2runtime/domains/peer_messaging').barrage
for _,pin in ipairs(BR.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local PAYLOAD120=barrages.payload_of('Orbital 120mm HE Barrage')
local BARRAGE_TYPE='0000000000005A5A'
local function f32(v)return b.encode(v,'f32')end
local function peer8(hex)return b.unhex(hex):reverse()end
-- The bombardment manager as the research found it (research/peer-messaging "barrage"): its counts, its entity map
-- (+0x30), its handles (+0x48: the entity handles) and blocks (+0x60: target at +8); components 28 (creator peers,
-- +0xC0) and 131 (creation types, +0x50), each with its own entity map.
local PDM=require('hd2runtime/domains/bombardment_payload').manager
local MGR=W.alloc(0x200)
W.write(W.GAME+PDM.global,W.u64(MGR))
local function map(at_object,at)
    local keys=W.alloc(64*8)
    for k=0,63 do W.write(keys+k*8,W.u32(4294967295)..W.u32(0))end
    W.write(at_object+at,W.u64(keys)..W.u32(64)..W.u32(4294967295)..W.u32(1))
    return keys
end
local function put(keys,entity,index)
    local slot=entity%64
    while b.u32(W.read(keys+slot*8,4),0)~=4294967295 do slot=(slot+1)%64 end
    W.write(keys+slot*8,W.u32(entity)..W.u32(index))
end
local MKEYS=map(MGR,BR.manager.map)
local MHANDLES,MBLOCKS=W.alloc(64*8),W.alloc(64*0x1C)
W.write(MGR+BR.manager.handles,W.u64(MHANDLES));W.write(MGR+BR.manager.block,W.u64(MBLOCKS))
local function component(global,map_at,array_at,stride)
    local comp=W.alloc(0x200);W.write(W.GAME+global,W.u64(comp))
    local keys=map(comp,map_at)
    local arr=W.alloc(64*stride);W.write(comp+array_at,W.u64(arr))
    return {keys=keys,arr=arr}
end
local C28=component(BR.creator.global,BR.creator.map,BR.creator.peers,8)
local C131=component(BR.carrier.global,BR.carrier.map,BR.carrier.types,4)
local NB,NOWNED=0,0
-- A barrage as the game makes one: spec = {entity, network, here (created here), carrier (the beacon's creation type),
-- creator (peer hex), at = {x, y, z} (its target)}.
local function barrage(spec)
    local i=NB;NB=NB+1
    if spec.here then NOWNED=NOWNED+1 end
    local h=W.alloc(0x18)
    W.write(h,b.unhex(PAYLOAD120:gsub('^0x','')):reverse()..W.u32(spec.entity)..W.u32(0)..W.u32(spec.network or 0x7FFF)
        ..W.u32(spec.here and 1 or 0))
    W.write(MHANDLES+i*8,W.u64(h))
    put(MKEYS,spec.entity,i)
    local at=spec.at or{x=40,y=30,z=2}
    W.write(MBLOCKS+i*0x1C+8,f32(at.x)..f32(at.y)..f32(at.z))
    W.write(MGR+BR.manager.networkCount,W.u32(NB));W.write(MGR+BR.manager.ownerCount,W.u32(NOWNED))
    put(C28.keys,spec.entity,i);W.write(C28.arr+i*8,peer8(spec.creator))
    put(C131.keys,spec.entity,i);W.write(C131.arr+i*4,W.u32(spec.carrier or 83))
    W.add{entity=spec.entity,type=BARRAGE_TYPE,unit=0,health=1}
    W.register_entity(spec.entity,BARRAGE_TYPE,0,spec.network)
    if spec.network then W.network_id(spec.network,spec.entity,30+i)end
end
-- A 120mm shell from barrage `source`: the pool as SpawnProjectile leaves it (its own impact copy: the row's).
local function shell(source,kind,creditor)
    return fire(source,{type=kind,impact=kind==194 and 213 or 176,creditor=creditor})
end
require('hd2runtime/runtime/beacons').position=function(world,entity)return {x=40,y=30,z=2}end
-- This machine's own Gas Barrage call, activated over (40, 30).
local function own_barrage(M,beacon_network)
    local d=custom.get('orbital_gas_barrage')
    local item
    for _,q in ipairs(M.queue)do if q.definition==d then item=q end end
    local ctx=I.new_call(d,item.assignment,1)
    ctx.beacon={entity=7100+beacon_network%100,network=beacon_network}
    ctx.landing={x=40,y=30,z=2};ctx.state='activated'
    I.start_barrage(ctx,d)
    return ctx
end
"""


def machine_lua(body):
    from support import lua as lua_literal
    eat, eat_addon = example_addon('GasEatExample')
    gas, gas_addon = example_addon('GasBarrageExample')
    pelican, pelican_addon = example_addon('PelicanCasExample')
    return run(WORLD + SLOT + PAYLOAD + IMPACT + 'local EAT_ADDON=' + lua_literal(eat_addon) + '\nlocal EAT_RESOURCE='
        + lua_literal(eat) + '\nlocal GAS_ADDON=' + lua_literal(gas_addon) + '\nlocal GAS_RESOURCE=' + lua_literal(gas)
        + '\nlocal PELICAN_ADDON=' + lua_literal(pelican_addon) + '\nlocal PELICAN_RESOURCE=' + lua_literal(pelican)
        + HARNESS + BARRAGE + body + "\nreturn 'ok'")


class CallerBarrageTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(machine_lua(body), b'ok')

    def test_the_callers_own_barrage_is_taken_at_its_first_shell_and_only_its_shells_turn_to_gas(self):
        self.lua(r"""
local world,M=machine(P1,true)
I.barrage_watch_step();tick()
-- Its beacon: the 120mm's own delivery (the decision the beacon watch applies in its first update).
for _,q in ipairs(M.queue)do if q.definition.id=='orbital_gas_barrage'then M.by_type[83]=q end end
local change=I.decide({type=83})
assert(change.delivery=='Orbital 120mm HE Barrage'and change.client==false,tostring(change and change.delivery))
local ctx=own_barrage(M,4114)
-- A vanilla 120mm barrage (its own creation type, 136) and this call's (carrier type 83, this machine, at its beacon).
barrage({entity=4243,network=4299,here=true,carrier=136,creator=P1})
barrage({entity=4244,network=4300,here=true,carrier=83,creator=P1})
tick()
local writes=#W.runtime.writes
-- Its first shell: recognised and converted in the same pass; the vanilla barrage's stay the 120mm's.
local _,a=shell(4244,194,P1);local _,v=shell(4243,194,P1)
tick()
assert(impact_of(a)==82 and impact_of(v)==213,('%d %d'):format(impact_of(a),impact_of(v)))
assert(ctx.barrage_entity==4244 and ctx.barrage_network==4300,tostring(ctx.barrage_entity))
assert(count('orbital_gas_barrage#1: DELIVERED: the native Orbital 120mm HE Barrage barrage, entity 4244 (network id '
    ..'4300), the only one, its target 0.0 m from the beacon')==1 and count('CUSTOM MP ITEMS: barrage network id 4300 (call beacon network id '
    ..'4114) published')==1,table.concat(logged,' | '))
assert(count('BARRAGE SHELLS: CONVERTED its first shell (projectile 194')==1,table.concat(logged,' | '))
-- Every shell of it: one write each (15 here).
for k=1,14 do shell(4244,k%3==0 and 194 or 137,P1)end
tick()
only_copy_writes(writes,15)
-- The vanilla barrage was judged once, never taken.
local _,v2=shell(4243,137,P1);tick()
assert(impact_of(v2)==176)
""")

    def test_the_barrage_watch_waits_for_its_donor_and_the_first_shell_after_readiness_converts(self):
        # Live r4: BARRAGE WATCH REFUSED: DONOR_NOT_RESIDENT (Orbital Gas Strike's call-in package not resident), then
        # CUSTOM MP ASSETS: orbital_gas_barrage resident one update later; the refusal was final, every shell vanilla.
        self.lua(r"""
local donors=require('hd2runtime/runtime/explosion_donors')
local GAS=donors.dependency('Orbital Gas Strike').package
local real_state=assets.state
local loading=false
assets.state=function(rt,pkg)if loading and pkg==GAS then return 'loading'end;return real_state(rt,pkg)end
local world,M=machine(P1,true)
local item
for _,q in ipairs(M.queue)do if q.definition.id=='orbital_gas_barrage'then item=q end end
assert(item and item.state=='checks',tostring(item and item.state))
-- The watch's first try: the donor still loading. It WAITS (never a final refusal).
loading=true
I.barrage_watch_step()
assert(count('BARRAGE WATCH WAITING (')==1 and count('BARRAGE WATCH REFUSED')==0,table.concat(logged,' | '))
assert(I.barrage_watch_state(item.definition)=='waiting')
-- The package becomes resident; the definition's own steps reach the watch gate before the watch's next try: it is
-- NOT READY there (its slot never converts while its shells would explode vanilla).
loading=false
-- (Its code checks are tested elsewhere: it starts at its own asset gate, resident.)
item.state,item.waited,item.gate='assets',0,{tick=function()return'ready'end}
I.advance(world,item)
assert(item.state=='barrage_watch',tostring(item.state))
I.advance(world,item)
assert(item.state=='barrage_watch'and count('MISSION (orbital_gas_barrage): NOT READY: waiting for its barrage watch')==1,
    tostring(item.state))
assert(count('READY TO CALL: loadout slot 1')==0)
-- The next step arms it (once), and then the definition goes on.
I.barrage_watch_step();I.barrage_watch_step()
assert(count('BARRAGE WATCH ARMED (')==1 and count('its donor became resident after')==1,table.concat(logged,' | '))
I.advance(world,item)
assert(item.state~='barrage_watch'and item.state~='refused',tostring(item.state))
-- The first shell of its call after readiness converts on this machine.
for _,q in ipairs(M.queue)do if q.definition.id=='orbital_gas_barrage'then M.by_type[83]=q end end
own_barrage(M,4114)
barrage({entity=4244,network=4300,here=true,carrier=83,creator=P1})
tick()
local _,a=shell(4244,194,P1)
tick()
assert(impact_of(a)==82,tostring(impact_of(a)))
""")

    def test_a_final_barrage_watch_refusal_refuses_its_definition_loudly(self):
        self.lua(r"""
local impacts=require('hd2runtime/runtime/projectile_impact')
local bind=impacts.bind
impacts.bind=function(spec,cb)if spec.accept then return nil,'UNSUPPORTED_BUILD','test'end;return bind(spec,cb)end
local world,M=machine(P1,true)
local item
for _,q in ipairs(M.queue)do if q.definition.id=='orbital_gas_barrage'then item=q end end
I.barrage_watch_step()
assert(count('BARRAGE WATCH REFUSED (native custom barrages stay vanilla on this machine): UNSUPPORTED_BUILD: test')==1)
item.state,item.waited,item.gate='assets',0,{tick=function()return'ready'end}
for _=1,3 do if item.state~='refused'then I.advance(world,item)end end
assert(item.state=='refused'and count('its barrage watch was refused')==1,tostring(item.state))
I.barrage_watch_step()
assert(count('BARRAGE WATCH REFUSED')==1,'a final refusal is not retried')
""")

    def test_live_r5_its_own_barrage_is_taken_although_its_target_is_not_at_the_beacon(self):
        # Live r5 (host): BARRAGE NOT TAKEN: this machine's orbital_gas_barrage barrage matches 0 of its own calls at its
        # target. The custom identity was right; the 3 m target test was the only discriminator. Now the only unbound
        # recent call of that id by this machine takes it, its distance only logged.
        self.lua(r"""
local world,M=machine(P1,true)
I.barrage_watch_step();tick()
local ctx=own_barrage(M,4114)
-- A vanilla 120mm barrage at the SAME target (its own creation type 136) and this call's, 25 m off its beacon.
barrage({entity=4243,network=4299,here=true,carrier=136,creator=P1,at={x=40,y=30,z=2}})
barrage({entity=4244,network=4300,here=true,carrier=83,creator=P1,at={x=60,y=45,z=2}})
tick()
local writes=#W.runtime.writes
local _,a=shell(4244,194,P1);local _,v=shell(4243,194,P1)
tick()
assert(impact_of(a)==82 and impact_of(v)==213 and ctx.barrage_entity==4244,table.concat(logged,' | '))
assert(count('DELIVERED: the native Orbital 120mm HE Barrage barrage, entity 4244 (network id 4300), the only one, its '
    ..'target 25.0 m from the beacon')==1,table.concat(logged,' | '))
for k=1,9 do shell(4244,k%2==0 and 194 or 137,P1);shell(4243,137,P1)end
tick()
only_copy_writes(writes,10)
-- One-to-one: a second custom barrage of this machine finds its call already bound: never the same call twice.
barrage({entity=4245,network=4301,here=true,carrier=83,creator=P1})
tick()
local _,b2=shell(4245,194,P1);tick()
assert(impact_of(b2)==213 and count('REJECTED: already bound to barrage 4244')==1,table.concat(logged,' | '))
""")

    def test_the_first_shell_judged_before_the_activation_event_converts_by_its_exact_beacon(self):
        # Research section 18: the barrage is created and its first shell exists in the activation update, which can be
        # judged before this machine's beacon watch reports the activation (start_barrage). r5 matched 0 calls then and
        # never retried. The barrage names the beacon whose dispatcher spawned it (inst.beacon_entity): exact.
        self.lua(r"""
local world,M=machine(P1,true)
I.barrage_watch_step();tick()
local d=custom.get('orbital_gas_barrage')
local item
for _,q in ipairs(M.queue)do if q.definition==d then item=q end end
local ctx=I.new_call(d,item.assignment,1)
ctx.beacon={entity=7114,network=4114};ctx.neutralized=true;ctx.state='beacon'
-- Its barrage, linked to beacon 7114 by the research's exact relation; another custom barrage linked to another beacon.
local instance=barrages.instance
barrages.instance=function(w,e)
    local i=instance(w,e)
    if i and e==4244 then i.beacon_entity=7114 elseif i and e==4246 then i.beacon_entity=7199 end
    return i
end
barrage({entity=4244,network=4300,here=true,carrier=83,creator=P1})
barrage({entity=4246,network=4302,here=true,carrier=83,creator=P1})
tick()
local _,o=shell(4246,194,P1);tick()
local _,a=shell(4244,194,P1);tick()
assert(impact_of(a)==82 and ctx.barrage_entity==4244,'the FIRST shell converts: '..table.concat(logged,' | '))
assert(count('DELIVERED: the native Orbital 120mm HE Barrage barrage, entity 4244 (network id 4300), its exact beacon')==1,
    table.concat(logged,' | '))
assert(impact_of(o)==213 and count('REJECTED: the barrage was dispatched by beacon 7199 (its exact beacon)')==1,
    table.concat(logged,' | '))
-- The activation event after: nothing more to await.
I.start_barrage(ctx,d)
assert(not ctx.awaiting_barrage and count('BARRAGE: the native')==0)
""")

    def test_a_barrage_that_does_not_match_exactly_one_call_is_never_taken(self):
        self.lua(r"""
local world,M=machine(P1,true)
I.barrage_watch_step();tick()
-- Two of its own calls at the same target: never a guess.
own_barrage(M,4114);own_barrage(M,4115)
barrage({entity=4244,network=4300,here=true,carrier=83,creator=P1})
tick()
local _,a=shell(4244,194,P1);tick()
assert(impact_of(a)==213 and count('BARRAGE MATCH DEBUG: barrage 4244 (network id 4300)')==1
    and count('BARRAGE MATCH DEBUG:   own call: peer '..P1)==2 and count('REJECTED: ambiguous: 2 calls fit, 2 at its '
    ..'target')==2,table.concat(logged,' | '))
-- Retried on later shells for a while (the evidence may still arrive), then refused once: never a guess.
for _=1,(custom.BARRAGE_RETRY/custom.STEP)+4 do tick(4)end
local _,a2=shell(4244,137,P1);tick()
assert(impact_of(a2)==176 and count('BARRAGE NOT TAKEN: this machine\'s orbital_gas_barrage barrage 4244 matches 2 of its '
    ..'own calls (ambiguous')==1 and count('BARRAGE MATCH DEBUG: barrage')==1,table.concat(logged,' | '))
""")

    def test_a_client_runs_its_own_native_barrage_inside_the_proof(self):
        self.lua(r"""
local world,M=machine(P2,false)
assert(mpm.client_proof())
local queued={}
for _,q in ipairs(M.queue)do queued[q.definition.id]=q.client end
assert(queued.orbital_gas_barrage==true and queued.eat17_gas==true,'the native orbital runs on a client')
assert(count('MISSION (orbital_gas_barrage): REFUSED on this client')==0)
I.barrage_watch_step();tick()
local ctx=own_barrage(M,4137)
barrage({entity=4243,network=4301,here=true,carrier=83,creator=P2})
tick()
local writes=#W.runtime.writes
local _,a=shell(4243,194,P2)
tick()
assert(impact_of(a)==82 and ctx.barrage_entity==4243,table.concat(logged,' | '))
only_copy_writes(writes,1)
""")


class ObserverBarrageTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(machine_lua(body), b'ok')

    def test_another_machines_barrage_is_derived_from_its_beacon_and_gas_on_this_copy(self):
        self.lua(r"""
local world,M=machine(P2,false)
I.barrage_watch_step();tick()
assert(count('CUSTOM MP ASSETS: orbital_gas_barrage resident for remote presentation/payload')==1,
    table.concat(logged,' | '))
remote_call(8101,4114,P1,83)
-- Here: a vanilla 120mm barrage (136) and P1's copy (carrier 83, creator P1, at its beacon): no list needed.
barrage({entity=4243,network=4299,here=false,carrier=136,creator=P1})
barrage({entity=4244,network=4300,here=false,carrier=83,creator=P1})
tick()
local writes=#W.runtime.writes
local _,a=shell(4244,194,P1);local _,c=shell(4244,137,P1);local _,v=shell(4243,137,P1)
tick()
assert(impact_of(a)==82 and impact_of(c)==82 and impact_of(v)==176,table.concat(logged,' | '))
assert(count('REMOTE CUSTOM BARRAGE: peer '..P1..', custom orbital_gas_barrage, barrage network id 4300 (entity 4244 on '
    ..'this machine), call beacon network id 4114: derived from its carrier type (83), its creator and its call (the '
    ..'only one')==1,
    table.concat(logged,' | '))
assert(count('REMOTE CUSTOM BARRAGE: peer '..P1..'\'s custom orbital_gas_barrage barrage network id 4300 (entity 4244 '
    ..'here): CONVERTED its first shell')==1,table.concat(logged,' | '))
assert(require('hd2runtime/runtime/custom_provenance').get(4300).role=='barrage','its provenance: a barrage')
only_copy_writes(writes,2)
-- The caller's published network id arrives later: a confirmation, nothing bound twice.
V.peers[P1].items={{id='orbital_gas_barrage',beacon=4114,items={4300}}}
I.items_step(world)
assert(count('REMOTE CUSTOM BARRAGE CONFIRMED: peer '..P1..', custom orbital_gas_barrage, barrage network id 4300 (entity '
    ..'4244 on this machine)')==1,table.concat(logged,' | '))
""")

    def test_live_r5_another_machines_barrage_is_taken_when_its_beacon_copy_is_gone(self):
        # Live r5 (other machine): REMOTE CUSTOM BARRAGE NOT TAKEN ... matches 0 of its beacons seen here. The beacon copy
        # can be gone by the first shell (its position then unreadable); the call is still that creator's only unbound
        # recent call of that id: its own evidence (thrown ball, observed position) associates it.
        self.lua(r"""
local world,M=machine(P2,false)
I.barrage_watch_step();tick()
remote_call(8101,4114,P1,83)
-- The beacon copy is gone before the first shell; the barrage's target is 12 m off the beacon.
BR.beacons=function()return {}end
require('hd2runtime/runtime/beacons').position=function()return nil end
barrage({entity=4244,network=4300,here=false,carrier=83,creator=P1,at={x=52,y=30,z=2}})
tick()
local _,a=shell(4244,194,P1);tick()
assert(impact_of(a)==82,table.concat(logged,' | '))
assert(count('REMOTE CUSTOM BARRAGE: peer '..P1..', custom orbital_gas_barrage, barrage network id 4300 (entity 4244 on '
    ..'this machine), call beacon network id 4114: derived from its carrier type (83), its creator and its call (the '
    ..'only one; target 12.0 m from that beacon)')==1,table.concat(logged,' | '))
""")

    def test_simultaneous_calls_of_two_players_bind_one_to_one_and_a_vanilla_barrage_stays_vanilla(self):
        self.lua(r"""
local world,M=machine(P1,true)
I.barrage_watch_step();tick()
-- Both players call Gas Barrage at the same moment at nearly the same place; another player calls a vanilla 120mm.
local ctx=own_barrage(M,4114)
remote_call(8102,4137,P2,83)
barrage({entity=4243,network=4299,here=false,carrier=136,creator=P2,at={x=41,y=30,z=2}})
barrage({entity=4244,network=4300,here=true,carrier=83,creator=P1,at={x=40,y=30,z=2}})
barrage({entity=4245,network=4301,here=false,carrier=83,creator=P2,at={x=41,y=31,z=2}})
tick()
local _,mine=shell(4244,194,P1);local _,theirs=shell(4245,194,P2);local _,vanilla=shell(4243,194,P2)
tick()
assert(impact_of(mine)==82 and impact_of(theirs)==82 and impact_of(vanilla)==213,('%d %d %d'):format(impact_of(mine),
    impact_of(theirs),impact_of(vanilla)))
assert(ctx.barrage_entity==4244 and count('REMOTE CUSTOM BARRAGE: peer '..P2..', custom orbital_gas_barrage, barrage '
    ..'network id 4301 (entity 4245 on this machine), call beacon network id 4137')==1,table.concat(logged,' | '))
""")

    def test_evidence_arriving_after_the_first_shell_still_binds_the_barrage(self):
        self.lua(r"""
local world,M=machine(P2,false)
I.barrage_watch_step();tick()
-- The barrage's first shell comes before this machine saw that call's beacon (replication order).
barrage({entity=4244,network=4300,here=false,carrier=83,creator=P1})
tick()
local _,a=shell(4244,194,P1);tick()
assert(impact_of(a)==213 and count('BARRAGE MATCH DEBUG: barrage 4244 (network id 4300), creator '..P1)==1
    and count('0 candidate calls; no call fits')==1,table.concat(logged,' | '))
-- Its beacon is seen now: a later shell of the same barrage binds it (retried within the window).
remote_call(8101,4114,P1,83)
tick(4)
local _,b=shell(4244,137,P1);tick()
assert(impact_of(b)==82 and count('REMOTE CUSTOM BARRAGE NOT TAKEN')==0,table.concat(logged,' | '))
""")

    def test_a_remote_beacon_copy_has_no_owned_position_and_its_creation_position_is_used(self):
        # Research section 18: runtime/beacons.lua position reads owned beacons only (nil for every copy); a copy's
        # creation position (custom_barrages.beacon_position, element +0x10) is the call's place on this machine.
        self.lua(r"""
local world,M=machine(P2,false)
I.barrage_watch_step();tick()
require('hd2runtime/runtime/beacons').position=function()return nil end
barrages.beacon_position=function(w,e)
    if e==8101 then return {x=40,y=30,z=2,owned=false,source='element'}end
    if e==8102 then return {x=140,y=30,z=2,owned=false,source='element'}end
end
-- Two calls of P1 (two Gas Barrage slots) a few seconds apart, 100 m apart: each barrage binds to the one at its target.
remote_call(8101,4114,P1,83)
remote_call(8102,4115,P1,83)
barrage({entity=4244,network=4300,here=false,carrier=83,creator=P1,at={x=140,y=30,z=2}})
barrage({entity=4245,network=4301,here=false,carrier=83,creator=P1,at={x=40,y=30,z=2}})
tick()
local _,a=shell(4244,194,P1);local _,c=shell(4245,194,P1)
tick()
assert(impact_of(a)==82 and impact_of(c)==82,table.concat(logged,' | '))
assert(count('barrage network id 4300 (entity 4244 on this machine), call beacon network id 4115')==1
    and count('barrage network id 4301 (entity 4245 on this machine), call beacon network id 4114')==1,
    table.concat(logged,' | '))
""")

    def test_a_remote_barrage_without_its_beacons_thrower_is_never_taken(self):
        self.lua(r"""
local world,M=machine(P1,true)
I.barrage_watch_step();tick()
-- The beacon was thrown by another player than the barrage's creator; and a creator whose picks do not select it.
remote_call(8101,4114,'9999999999999999',83)
barrage({entity=4244,network=4300,here=false,carrier=83,creator=P2})
barrage({entity=4245,network=4302,here=false,carrier=83,creator='7777777777777777'})
tick()
local _,a=shell(4244,194,P2);local _,c=shell(4245,194,P2)
tick()
assert(impact_of(a)==213 and impact_of(c)==213)
assert(count('REMOTE CUSTOM BARRAGE NOT TAKEN: barrage 4245 (network id 4302) names creator 7777777777777777, whose '
    ..'synced picks do not select orbital_gas_barrage')==1,table.concat(logged,' | '))
-- The debug block names the beacon and why it was rejected; after the retry window, refused once.
assert(count('BARRAGE MATCH DEBUG: barrage 4244 (network id 4300), creator '..P2)==1 and count('remote call: peer '
    ..'9999999999999999, beacon network id 4114')==1 and count('REJECTED: its caller is 9999999999999999, not the '
    ..'barrage\'s creator')==1,table.concat(logged,' | '))
for _=1,(custom.BARRAGE_RETRY/custom.STEP)+4 do tick(4)end
local _,a2=shell(4244,137,P2);tick()
assert(impact_of(a2)==176 and count('REMOTE CUSTOM BARRAGE NOT TAKEN: barrage 4244 (network id 4300) of '..P2..' matches 0 '
    ..'of its beacons seen here (no call fits')==1,table.concat(logged,' | '))
""")


class GasEatUnchangedTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(machine_lua(body), b'ok')

    def test_the_gas_eat_keeps_its_r3_behaviour_beside_the_barrage_and_the_pelican(self):
        self.lua(r"""
-- The caller (P1): its own and a cross-picked shot are gas; a vanilla EAT-17 stays vanilla; the credit is the game's.
local world,M=machine(P1,true)
I.barrage_watch_step();tick()
launcher(5001,4117,21);launcher(5002,4118,22)
local writes=#W.runtime.writes
own_call(M,4114,{5001,5002},{4117,4118})
local _,h1=fire(5001,{creditor=P1});tick()
local _,h2=fire(5002,{creditor=P2});tick()
local _,v1=fire(5003,{creditor=P2});tick()
assert(impact_of(h1)==82 and impact_of(h2)==82 and impact_of(v1)==376)
assert(count('PROJECTILE CONVERTED: launcher 5002 (network id 4118)')==1 and count('fired by another player who picked it '
    ..'up, '..P2..'; creditor '..P2..', the game\'s own')==1,table.concat(logged,' | '))
only_copy_writes(writes,2)
-- Another machine's launchers (P2's call): correlated by network id, its own copies converted, whoever fires.
remote_call(8102,4137,P2)
launcher(6101,4139,43);launcher(6102,4140,44)
V.peers[P2].items={{id='eat17_gas',beacon=4137,items={4139,4140}}}
I.items_step(world)
assert(count('REMOTE CUSTOM ITEM: peer '..P2..', custom eat17_gas, launcher network id 4139 (entity 6101 on this machine), '
    ..'call beacon network id 4137: its rockets explode as Orbital Gas Strike\'s (explosion 82 instead of 376) on this '
    ..'machine\'s own copy, whoever fires it')==1,table.concat(logged,' | '))
tick()
local _,r1=fire(6101,{creditor=P2});local _,r2=fire(6102,{creditor=P1});tick()
assert(impact_of(r1)==82 and impact_of(r2)==82)
""")


if __name__ == '__main__':
    unittest.main()
