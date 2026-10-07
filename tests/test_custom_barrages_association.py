"""The native barrage -> call association fields of runtime/custom_barrages.lua (research/docs/runtime-peer-messaging-
F5FEE03DCFDB.md section 18; research/barrage-association-F5FEE03DCFDB.json). Offline, on the payload world with the
beacon manager of tests/test_beacon_redirect.py and a bombardment manager laid out as the research found it:
  * the instance's replicated block (target bytes, shells, salvos, heading, seed) and its copy's shells fired;
  * a barrage created HERE names the owned beacon whose dispatcher spawned it: activated, its creation type the
    barrage's carrier type, its dispatch record naming the payload and a requested spawn, at EXACTLY the target (the
    dispatcher's own position); never a nearest guess;
  * another machine's beacon is a copy without state: runtime/beacons.lua position has nothing for it (the live r5
    remote failure), custom_barrages.beacon_position reads the element +0x10 every machine holds;
  * every existing instance field stays as it was, also when an association pin no longer holds."""
import json
import sys
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_beacon_redirect import BEACONS

RESEARCH = json.loads((ROOT / 'research/barrage-association-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

ASSOCIATION = r"""
local wm=require('hd2runtime/runtime/event_world')
local barrages=require('hd2runtime/runtime/custom_barrages');barrages.reset_for_tests()
local BRD=require('hd2runtime/domains/peer_messaging').barrage
local AS=BRD.association
for _,pin in ipairs(BRD.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
for _,pin in ipairs(AS.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local PAY120='0x2D3BD00B1ED411B1'
local ME,OTHER='32B10D7BA1516C5C','5E2B9B1B15173661'
-- The bombardment manager (research/peer-messaging "barrage" + the association's block and state), components 28 and
-- 131, each with its own entity map (multiplier 1).
local X={}
do
    local PDM=require('hd2runtime/domains/bombardment_payload').manager
    local MGR=W.alloc(0x200)
    W.write(W.GAME+PDM.global,W.u64(MGR))
    local function map(object,at)
        local keys=W.alloc(64*8)
        for k=0,63 do W.write(keys+k*8,W.u32(4294967295)..W.u32(0))end
        W.write(object+at,W.u64(keys)..W.u32(64)..W.u32(4294967295)..W.u32(1))
        return keys
    end
    local function put(keys,entity,index)
        local slot=entity%64
        while b.u32(W.read(keys+slot*8,4),0)~=4294967295 do slot=(slot+1)%64 end
        W.write(keys+slot*8,W.u32(entity)..W.u32(index))
    end
    local MKEYS=map(MGR,BRD.manager.map)
    local HANDLES,BLOCKS,STATES=W.alloc(64*8),W.alloc(64*0x1C),W.alloc(64*AS.state.stride)
    W.write(MGR+BRD.manager.handles,W.u64(HANDLES));W.write(MGR+BRD.manager.block,W.u64(BLOCKS))
    W.write(MGR+AS.state.states,W.u64(STATES))
    local function component(global,map_at,array_at,stride)
        local comp=W.alloc(0x200);W.write(W.GAME+global,W.u64(comp))
        local keys=map(comp,map_at)
        local arr=W.alloc(64*stride);W.write(comp+array_at,W.u64(arr))
        return {keys=keys,arr=arr}
    end
    local C28=component(BRD.creator.global,BRD.creator.map,BRD.creator.peers,8)
    local C131=component(BRD.carrier.global,BRD.carrier.map,BRD.carrier.types,4)
    local n,owned=0,0
    -- spec = {entity, network, here, carrier, creator (peer hex), at = {x, y, z}, shells, salvos, heading, seed, fired}
    function X.barrage(spec)
        local i=n;n=n+1
        if spec.here then owned=owned+1 end
        local h=W.alloc(0x18)
        W.write(h,b.unhex(PAY120:gsub('^0x','')):reverse()..W.u32(spec.entity)..W.u32(0)..W.u32(spec.network or 0x7FFF)
            ..W.u32(spec.here and 1 or 0))
        W.write(HANDLES+i*8,W.u64(h))
        put(MKEYS,spec.entity,i)
        local at=spec.at
        W.write(BLOCKS+i*0x1C,W.u32(spec.shells or 3)..W.u32(spec.salvos or 6)..b.encode(at.x,'f32')..b.encode(at.y,'f32')
            ..b.encode(at.z,'f32')..b.encode(spec.heading or 1.25,'f32')..W.u32(spec.seed or 0xC0FFEE))
        W.write(STATES+i*AS.state.stride+AS.state.fired,W.u32(spec.fired or 1))
        W.write(MGR+BRD.manager.networkCount,W.u32(n));W.write(MGR+BRD.manager.ownerCount,W.u32(owned))
        put(C28.keys,spec.entity,i);W.write(C28.arr+i*8,b.unhex(spec.creator):reverse())
        put(C131.keys,spec.entity,i);W.write(C131.arr+i*4,W.u32(spec.carrier or 83))
        return i
    end
end
-- A beacon of this test (BEACONS' beacon(), then): its state's dispatcher position (+0x30) and creation type (+0x3D8),
-- its handle's network id, its element's position (+0x10, the creation message's).
local function place(i,spec)
    local st=STATE+i*0x8E8
    if spec.at then W.write(st+AS.beacon.statePosition,f32(spec.at.x)..f32(spec.at.y)..f32(spec.at.z))end
    W.write(st+AS.beacon.creationType,W.u32(spec.creation or 83))
    local handle=b.pointer(W.read(HANDLES+i*8,8),0)
    W.write(handle+0x10,W.u32(spec.network or 0x7FFF))
    if spec.element then
        W.write(ELEMENTS+i*0x40+AS.beacon.elementPosition,f32(spec.element.x)..f32(spec.element.y)..f32(spec.element.z))
    end
end
"""


def lua(body):
    return run(WORLD + SLOT + PAYLOAD + BEACONS + ASSOCIATION + body + "\nreturn 'ok'")


class AssociationResearchTests(unittest.TestCase):
    def test_the_research_is_read_only_proven_in_every_snapshot_and_the_domain_is_current(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_peer_messaging
        self.assertEqual(generate_peer_messaging.generate(check=True), [])
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges'], RESEARCH['nativeCalls']), (0, 0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(len(RESEARCH['snapshots']), 7)
        rvas = {p['rva'] for rows in RESEARCH['pins'].values() for p in rows}
        # The dispatcher's position (state +0x30), the spawn position (+ offset), the target (= descriptor +0x38 when
        # the record's +0x88 is 0), the block's +8, a remote copy's verbatim block, a beacon copy's element +0x10.
        self.assertTrue({0x6ABC46, 0x6AD645, 0x6AD64F, 0x8516F9, 0x854A00, 0x854BA5, 0x6AEDF2, 0x6ABB8D} <= rvas)
        self.assertIn('0x2D3BD00B1ED411B1', RESEARCH['exactTargetPayloads'])
        s = RESEARCH['snapshots'][0]
        self.assertEqual(s['row136']['offsetCount'], 0)
        self.assertEqual(s['zeroVector'], '00' * 12)
        donor = s['records']['0x2D3BD00B1ED411B1']
        self.assertEqual((donor['driftStart'], donor['startDelay']), (0.0, 0.0))


class AssociationTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_a_barrage_created_here_names_the_beacon_whose_dispatcher_spawned_it(self):
        self.check(r"""
pworld()
-- Two owned beacons of the carrier (83), both dispatched the 120mm's payload: an earlier call (60, 45) and this one.
beacon(0,7001,136,1.0,8.7);beacon(1,7002,136,1.0,8.7);counts(2,2)
dispatched(0,136,PAY120);dispatched(1,136,PAY120)
place(0,{at={x=60.5,y=45.25,z=2},network=4100})
place(1,{at={x=40.125,y=30.5,z=2.75},network=4114})
X.barrage({entity=4244,network=4300,here=true,carrier=83,creator=ME,at={x=40.125,y=30.5,z=2.75},shells=3,salvos=6,
    heading=1.25,seed=0xC0FFEE,fired=1})
local world=wm.open()
local inst=assert(barrages.instance(world,4244))
-- Every earlier field as before.
assert(inst.payload==PAY120 and inst.network==4300 and inst.created_here and inst.carrier_type==83 and inst.creator==ME)
assert(inst.target.x==40.125 and inst.target.y==30.5 and inst.target.z==2.75)
-- The association fields.
assert(inst.association_why==nil,tostring(inst.association_why))
assert(inst.target_raw==b.hex(f32(40.125)..f32(30.5)..f32(2.75)),inst.target_raw)
assert(inst.shells==3 and inst.salvos==6 and inst.heading==1.25 and inst.seed==0xC0FFEE and inst.fired==1)
assert(inst.exact_target==true)
assert(inst.beacon_entity==7002 and inst.beacon_network==4114 and inst.beacon_why==nil,
    tostring(inst.beacon_entity)..' '..tostring(inst.beacon_why))
""")

    def test_never_a_nearest_guess(self):
        self.check(r"""
pworld()
beacon(0,7001,136,1.0,8.7);beacon(1,7002,136,1.0,8.7);beacon(2,7003,136,1.0,8.7);beacon(3,7004,136,1.0,8.7)
counts(4,4)
-- 7001: this call's beacon, but the barrage's target is 0.5 m off it (a mission scatter effect).
dispatched(0,136,PAY120);place(0,{at={x=40,y=30,z=2},network=4114})
-- At exactly the target, but each fails one structural test: not activated; another creation type (a native 120mm's
-- beacon, 136); another payload; no spawn requested.
place(1,{at={x=40.5,y=30,z=2},network=4115})
dispatched(2,136,PAY120);place(2,{at={x=40.5,y=30,z=2},network=4116,creation=136})
dispatched(3,136,'0xEF66B417EDC3B1D6');place(3,{at={x=40.5,y=30,z=2},network=4117})
X.barrage({entity=4244,network=4300,here=true,carrier=83,creator=ME,at={x=40.5,y=30,z=2}})
local world=wm.open()
local inst=assert(barrages.instance(world,4244))
assert(inst.beacon_entity==nil and inst.beacon_network==nil,tostring(inst.beacon_entity))
assert(inst.beacon_why=='1 owned beacon of its creation type dispatched its payload, none at exactly its target (nearest '
    ..'0.50 m: a mission scatter effect?)',inst.beacon_why)
-- No spawn requested: not a candidate either.
W.write(STATE+0*0x8E8+AS.beacon.dispatchSpawn,W.u32(0))
barrages.reset_for_tests()
inst=assert(barrages.instance(world,4244))
assert(inst.beacon_entity==nil and inst.beacon_why=='no owned activated beacon of its creation type dispatched its payload',
    tostring(inst.beacon_why))
-- Two owned beacons at exactly the target: ambiguous, nothing named.
W.write(STATE+0*0x8E8+AS.beacon.dispatchSpawn,W.u32(10))
place(0,{at={x=40.5,y=30,z=2},network=4114})
W.write(STATE+2*0x8E8+AS.beacon.creationType,W.u32(83))
barrages.reset_for_tests()
inst=assert(barrages.instance(world,4244))
assert(inst.beacon_entity==nil and inst.beacon_why=='2 owned beacons dispatched it at exactly its target',
    tostring(inst.beacon_why))
""")

    def test_another_machines_barrage_and_beacon_copy(self):
        self.check(r"""
pworld()
-- This machine's own beacon (index 0, a state) and another machine's beacon (index 1: a copy, no state).
beacon(0,7001,136,1.0,8.7);beacon(1,7101,83,5.0,8.7);counts(2,1)
place(0,{at={x=12,y=-4,z=1},element={x=12,y=-4,z=3}})
place(1,{element={x=-20.25,y=64.5,z=7},network=345})
X.barrage({entity=4245,network=4301,here=false,carrier=83,creator=OTHER,at={x=-20.25,y=64.5,z=6.5}})
local world=wm.open()
local inst=assert(barrages.instance(world,4245))
assert(not inst.created_here and inst.creator==OTHER and inst.carrier_type==83)
-- The beacon fields are the creating machine's only.
assert(inst.beacon_entity==nil and inst.beacon_network==nil and inst.beacon_why==nil)
-- Live r5: the copy has no state, so runtime/beacons.lua position names no position for it.
assert(require('hd2runtime/runtime/beacons').position(world,7101)==nil)
local copy=assert(barrages.beacon_position(world,7101))
assert(copy.source=='element'and copy.owned==false and copy.x==-20.25 and copy.y==64.5 and copy.z==7)
assert(barrages.distance(inst.target,copy)==0)
-- An owned beacon: the dispatcher's own position (state +0x30), its element beside it.
local own=assert(barrages.beacon_position(world,7001))
assert(own.source=='state'and own.owned and own.x==12 and own.y==-4 and own.z==1 and own.element.z==3)
assert(own.raw==b.hex(f32(12)..f32(-4)..f32(1)))
local none,why=barrages.beacon_position(world,9999)
assert(none==nil and why=='no beacon 9999 here',tostring(why))
""")

    def test_a_changed_association_pin_keeps_every_earlier_field(self):
        self.check(r"""
pworld()
beacon(0,7001,136,1.0,8.7);counts(1,1);dispatched(0,136,PAY120);place(0,{at={x=40,y=30,z=2},network=4114})
X.barrage({entity=4244,network=4300,here=true,carrier=83,creator=ME,at={x=40,y=30,z=2}})
W.write(W.GAME+0x8516F9,'\144')
local world=wm.open()
local inst=assert(barrages.instance(world,4244))
assert(inst.payload==PAY120 and inst.network==4300 and inst.created_here and inst.carrier_type==83 and inst.creator==ME
    and inst.target.x==40)
assert(inst.association_why and inst.association_why:find('game+8516F9 changed',1,true),tostring(inst.association_why))
assert(inst.target_raw==nil and inst.fired==nil and inst.beacon_entity==nil and inst.exact_target==nil)
local p,why=barrages.beacon_position(world,7001)
assert(p==nil and why:find('UNSUPPORTED_BUILD',1,true),tostring(why))
""")


if __name__ == '__main__':
    unittest.main()
