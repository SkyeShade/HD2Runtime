"""The Gas EAT's two Runtime parts (research/docs/gas-eat-F5FEE03DCFDB.md), offline on the payload world:
  * runtime/projectile_impact.lua: a bound launcher's rocket (type 132) takes the Orbital Gas Strike's explosion 82 on
    impact through ONE guarded 4-byte write of ITS OWN hit record's impact explosion copy (+0x7C), while it flies; a
    vanilla EAT-17's rocket is never touched, a launcher has one round, every guard refuses (the rocket stays vanilla),
    the impact is followed, and no row (the EAT's rocket, the Gas Strike's chain) is ever written;
  * runtime/support_pods.lua: a support beacon's pod (Transport block +0x10 = the beacon's network id, +0xC = the
    dispatched type), its rack (element +0x8) and the rack's exact items (HellpodRack slots, through the network id map),
    read-only; another beacon's pod is never taken, an ambiguous or unexpected one is refused."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD

POOL_RESEARCH = json.loads((ROOT / 'research/projectile-pool-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
DELIVERY_RESEARCH = json.loads((ROOT / 'research/support-delivery-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

IMPACT = r"""
local impacts=require('hd2runtime/runtime/projectile_impact');impacts.reset_for_tests()
local PO=require('hd2runtime/domains/projectile_rows').pool
local H=PO.hit
local EAT_TYPE='80932FA0ED6901D3'
local LOCAL_PEER='1111222233334444'
-- The EAT-17's rocket row (projectile 132): its impact explosion 376, no expiry explosion (the reviewed values).
local rocket=W.projectile_row(132,W.u32(132)..string.rep('\0',0x8C)..W.u32(376)..string.rep('\0',8)..W.u32(0)
    ..string.rep('\0',0x110-0xA0))
local ROCKET=W.read(rocket,0x110)
local function iworld()
    local h=pworld()
    -- The entity map hangs from the component world: back from the bombardment object W.bombardment put there.
    W.write(W.GAME+require('hd2runtime/domains/event_natives').wielder.entities,W.u64(W.ENTITIES))
    W.players({{peer=LOCAL_PEER,avatar=100}},LOCAL_PEER)
    W.add{entity=100,type=W.AVATAR,unit=7100,health=125,owned=true}
    for _,e in ipairs({5001,5002,5003})do       -- the two Gas EAT launchers and a vanilla EAT-17
        W.add{entity=e,type=EAT_TYPE,unit=0,health=1}
        W.register_entity(e,EAT_TYPE)
    end
    return h
end
-- A rocket fired from a launcher: the pool as SpawnProjectile leaves it (its own impact explosion copy, 376).
local function fire(source,opts)
    opts=opts or{}
    local slot=W.spawn_projectile({type=opts.type or 132,source=source,owner=opts.owner or 100,
        creditor=opts.creditor or LOCAL_PEER})
    local hit=W.projectile_system+H.base+slot*H.stride
    W.write(hit+H.impactExplosion,W.u32(opts.impact or 376)..W.u32(opts.expiry or 0))
    W.write(hit+H.impactRequested,string.char(opts.requested or 0))
    return slot,hit
end
local function impact_of(hit)return b.u32(W.read(hit+H.impactExplosion,4),0)end
local function chain()
    local out={}
    for _,item in ipairs(require('hd2runtime/domains/bombardment_payload').gasChainRows)do
        local at=b.pointer(W.read(W.GAME+item.table+item.id*8,8),0)
        out[#out+1]=W.read(at,item.stride)
    end
    return table.concat(out)
end
"""

PODS = r"""
local pods=require('hd2runtime/runtime/support_pods');pods.reset_for_tests()
local SD=require('hd2runtime/domains/support_delivery')
for _,pin in ipairs(SD.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local T,R,HD=SD.transport,SD.rack,SD.handle
local TCOMP,RCOMP=W.alloc(0x100),W.alloc(0x100)
W.write(W.GAME+T.global,W.u64(TCOMP));W.write(W.GAME+R.global,W.u64(RCOMP))
local THANDLES,TELEMENTS,TBLOCKS=W.alloc(0x400),W.alloc(0x1000),W.alloc(0x400)
W.write(TCOMP+T.handles,W.u64(THANDLES));W.write(TCOMP+T.elements,W.u64(TELEMENTS));W.write(TCOMP+T.blocks,W.u64(TBLOCKS))
local RKEYS,RELEMENTS=W.alloc(64*8),W.alloc(0x1000)
for k=0,63 do W.write(RKEYS+k*8,W.u32(4294967295)..W.u32(0))end
W.write(RCOMP+R.keys,W.u64(RKEYS));W.write(RCOMP+R.capacity,W.u32(64));W.write(RCOMP+R.empty,W.u32(4294967295))
W.write(RCOMP+R.multiplier,W.u32(1));W.write(RCOMP+R.elements,W.u64(RELEMENTS))
local npods=0
-- A pod: its handle (entity, network id), element (content, content entity) and block (type, beacon network id).
local function pod(entity,kind,beacon_network)
    local i=npods
    npods=npods+1
    local handle=W.alloc(0x18)
    W.write(handle,W.u64(0x73F8498B)..W.u32(entity)..W.u32(0)..W.u32(600+i)..W.u32(0))
    W.write(THANDLES+i*8,W.u64(handle))
    W.write(TELEMENTS+i*T.stride,string.rep('\0',T.stride))
    W.write(TBLOCKS+i*T.blockStride,string.rep('\0',T.type)..W.u32(kind)..W.u32(beacon_network)..string.rep('\0',4))
    W.write(TCOMP+T.count,W.u32(npods))
    return i
end
-- The authority's content spawn: element +0x8 = +0x24 = the rack; the rack element with its items' network ids.
local nracks=0
local function rack(i,entity,kind,networks)
    W.write(TELEMENTS+i*T.stride+T.contentEntity,W.u32(entity))
    W.write(TELEMENTS+i*T.stride+T.contentEntityCopy,W.u32(entity))
    local index=nracks
    nracks=nracks+1
    local slot=entity%64
    while b.u32(W.read(RKEYS+slot*8,4),0)~=4294967295 do slot=(slot+1)%64 end
    W.write(RKEYS+slot*8,W.u32(entity)..W.u32(index))
    local slots=''
    for s=1,8 do slots=slots..W.u32(networks[s]or R.noItem)end
    W.write(RELEMENTS+index*R.stride,string.char(1)..'\0\0\0'..W.u32(8)..slots..W.u32(kind))
    return index
end
local function capture(spec)
    local events={}
    local w=assert(pods.capture(spec,function(e)events[#events+1]=e end))
    return w,events
end
local function kinds(events)local out={};for _,e in ipairs(events)do out[#out+1]=e.kind end;return table.concat(out,',')end
"""


def lua(body):
    return run(WORLD + SLOT + PAYLOAD + IMPACT + body)


def pods_lua(body):
    # Not the payload world: its bombardment object takes the component-world global the network id map hangs from.
    return run(WORLD + SLOT + PODS + body)


class GasEatResearchTests(unittest.TestCase):
    def test_the_impact_explosion_copy_is_the_projectiles_own(self):
        self.assertEqual((POOL_RESEARCH['writes'], POOL_RESEARCH['protectionChanges']), (0, 0))
        hit = POOL_RESEARCH['pool']['hit']
        self.assertEqual((hit['impactExplosion'], hit['expiryExplosion'], hit['impactRequested']), (0x7C, 0x80, 0xB9))
        impact = {p['rva']: p for p in POOL_RESEARCH['proofs']['impact']}
        self.assertEqual(impact[0x13B0736]['asm'], 'mov esi, dword ptr [rdi + rcx + 0x4d0bc]')
        self.assertEqual(impact[0x13B073D]['asm'], 'mov byte ptr [rdi + rcx + 0x4d0f9], 1')
        # The census: SpawnProjectile is the only store to a +0x7C member in the projectile system's code.
        self.assertEqual([s['rva'] for s in POOL_RESEARCH['census']['stores']], [0x13AA64C])
        self.assertEqual({p['rva'] for p in POOL_RESEARCH['census']['pool'] if 'write' in p['role']}, {0x13B073D})

    def test_the_support_delivery_research(self):
        r = DELIVERY_RESEARCH
        self.assertEqual((r['writes'], r['protectionChanges']), (0, 0))
        self.assertFalse(any(r['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(r['eat17']['type'], 147)
        self.assertIn(r['eat17']['rack'], r['eat17']['payload'])
        self.assertEqual(r['eat17Rocket'], {'projectile': 132, 'impactExplosion': 376,
            'source': r['eat17Rocket']['source']})
        self.assertEqual(r['layout']['transport']['beaconNetwork'], 0x10)
        self.assertEqual(r['layout']['rack']['stride'], 0x2C)


class ProjectileImpactTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_only_the_bound_launchers_rockets_take_the_gas_explosion(self):
        self.check(r'''
iworld()
local before_chain=chain()
local events={}
local binding,code,why=impacts.bind({sources={5001,5002},projectile=132,donor='Orbital Gas Strike',
    entity_type=EAT_TYPE,label='Gas EAT #1'},function(e)events[#events+1]=e end)
assert(binding,tostring(code)..' '..tostring(why))
assert(binding.from==376 and binding.to==82)
tick()
local writes=#W.runtime.writes
-- A vanilla EAT-17 fires first: its rocket is never touched.
local _,vanilla_hit=fire(5003)
tick()
assert(impact_of(vanilla_hit)==376 and#W.runtime.writes==writes and#events==0,'a vanilla rocket was touched')
-- Each Gas EAT launcher fires its one rocket: ONE 4-byte write of that rocket's own copy, 376 -> 82.
local slot1,hit1=fire(5001)
local slot2,hit2=fire(5002)
tick()
assert(impact_of(hit1)==82 and impact_of(hit2)==82,'not converted: '..impact_of(hit1)..', '..impact_of(hit2))
assert(#W.runtime.writes==writes+2,'writes '..(#W.runtime.writes-writes))
assert(events[1].kind=='converted'and events[1].slot==slot1 and events[1].source==5001 and events[1].from==376
    and events[1].to==82 and events[1].writes==1 and events[1].verify.readBack and events[1].verify.nonTarget
    and events[1].creditor==LOCAL_PEER,'event 1')
assert(events[2].kind=='converted'and events[2].source==5002)
assert(count('projectile impact CONVERTED (Gas EAT #1): projectile 132 in pool slot '..slot1..' from source 5001: '
    ..'impact explosion 376 -> 82 (1 write; read back true; non-target bytes unchanged true; protection restored true); '
    ..'creditor '..LOCAL_PEER..', owner 100')==1,table.concat(logged,' | '))
-- One round per launcher: a second rocket from 5001 stays vanilla (and is reported).
local _,hit3=fire(5001)
tick()
assert(impact_of(hit3)==376 and events[3].kind=='untouched','a second rocket was converted')
-- The impact: the game marks +0xB9 and requests the copy's explosion.
W.write(hit1+H.impactRequested,string.char(1))
tick()
assert(events[4].kind=='impact'and events[4].slot==slot1 and events[4].explosion==82,tostring(events[4]and events[4].kind))
-- No row was ever written: the EAT's rocket, the Gas Strike's whole chain.
assert(W.read(rocket,0x110)==ROCKET and chain()==before_chain,'a shared row was written')
assert(impact_of(vanilla_hit)==376)
return 'ok'
''')

    def test_every_guard_leaves_the_rocket_vanilla(self):
        self.check(r'''
iworld()
local events={}
local binding=assert(impacts.bind({sources={5001,5002},projectile=132,donor='Orbital Gas Strike',rounds=4,
    entity_type=EAT_TYPE,label='guards'},function(e)events[#events+1]=e end))
tick()
local function last()return events[#events]end
-- Another impact explosion than the row's: refused.
local _,h1=fire(5001,{impact=377});tick()
assert(last().kind=='refused'and last().code=='UNEXPECTED_EXPLOSION'and impact_of(h1)==377)
-- An expiry explosion pending: refused.
local _,h2=fire(5001,{expiry=12});tick()
assert(last().code=='UNEXPECTED_EXPLOSION'and impact_of(h2)==376)
-- Its impact already requested: refused.
local _,h3=fire(5001,{requested=1});tick()
assert(last().code=='MISSED'and impact_of(h3)==376)
-- Not credited to the local player: refused.
local _,h4=fire(5001,{creditor='9999888877776666'});tick()
assert(last().code=='NOT_LOCAL'and impact_of(h4)==376)
-- Another projectile type from the launcher: not this binding's at all.
local n=#events
fire(5001,{type=148});tick()
assert(#events==n)
-- The launcher gone (its entity removed): refused.
W.remove(5002)
local _,h5=fire(5002);tick()
assert(last().code=='SOURCE_GONE'and impact_of(h5)==376)
-- The donor's chain changed (explosion 82 not as reviewed): refused.
local row82=BOMB.chain_row and BOMB.chain_row('explosion',82)
if row82 then
    local saved=W.read(row82+4,4)
    W.write(row82+4,W.u32(999))
    local _,h6=fire(5001);tick()
    assert(last().code=='DONOR_CHANGED'and impact_of(h6)==376,tostring(last().code))
    W.write(row82+4,saved)
end
-- A rocket that is not in flight any more: refused.
local slot7,h7=fire(5001)
W.write(W.projectile_system+PO.flags.base+slot7*PO.flags.stride,string.char(0,0))
tick()
assert(last().code=='MISSED'and impact_of(h7)==376)
-- Every refusal is an event; the log names each reason once and counts the rest when the binding ends.
assert(count('stays vanilla')==(row82 and 5 or 4),table.concat(logged,' | '))
binding.cancel()
assert(count('projectile impact REFUSED (guards): 2 more projectiles stayed vanilla (MISSED x 1, UNEXPECTED_EXPLOSION '
    ..'x 1)')==1,table.concat(logged,' | '))
return 'ok'
''')

    def test_a_binding_is_refused_before_it_starts(self):
        self.check(r'''
iworld()
local function refused(spec,code)
    local b_,c,why=impacts.bind(spec)
    assert(not b_ and c==code,tostring(c)..' '..tostring(why))
end
refused({sources={5001},projectile=132,donor='Orbital 120mm HE Barrage'},'UNREVIEWED_DONOR')
refused({sources={5001},projectile=132,donor='Orbital Gas Strike',entity_type='0000000000000001'},'SOURCE_CHANGED')
-- An id the entity map does not name (the fixture's generation table calls every unused index alive): refused.
refused({sources={9999},projectile=132,donor='Orbital Gas Strike'},'SOURCE_UNREADABLE')
refused({sources={},projectile=132,donor='Orbital Gas Strike'},'INVALID')
-- A projectile whose row has an expiry explosion, or none: refused.
W.projectile_row(150,W.u32(150)..string.rep('\0',0x8C)..W.u32(376)..string.rep('\0',8)..W.u32(5)..string.rep('\0',0x110-0xA0))
refused({sources={5001},projectile=150,donor='Orbital Gas Strike'},'EXPIRY_EXPLOSION')
-- Outside a mission and as a client: refused.
W.state(3);tick()
refused({sources={5001},projectile=132,donor='Orbital Gas Strike'},'NOT_IN_MISSION')
W.state(4,{host=false});tick()
refused({sources={5001},projectile=132,donor='Orbital Gas Strike'},'NOT_HOST')
-- Bound once only.
W.state(4);tick()
assert(impacts.bind({sources={5001},projectile=132,donor='Orbital Gas Strike'}))
refused({sources={5001},projectile=132,donor='Orbital Gas Strike'},'ALREADY_BOUND')
-- The mission ends: every binding ends.
W.state(3);tick(2)
assert(#impacts.active()==0)
return 'ok'
''')


class SupportPodTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(pods_lua(body), b'ok')

    def test_the_exact_launchers_of_the_beacons_own_pod(self):
        self.check(r'''
mission({host=true})
-- The beacon (entity 7001, network id 801) and its handle; the launchers' network ids.
W.network_id(801,7001,20);W.network_id(901,5001,21);W.network_id(902,5002,22);W.network_id(903,5003,23)
for _,e in ipairs({5001,5002,5003})do W.add{entity=e,type='80932FA0ED6901D3',unit=0,health=1}
    W.register_entity(e,'80932FA0ED6901D3')end
local handle=W.alloc(0x18)
W.write(handle,W.u64(0)..W.u32(7001)..W.u32(0)..W.u32(801)..W.u32(0))
local slot_ptr=W.alloc(8);W.write(slot_ptr,W.u64(handle))
assert(pods.beacon_network(require('hd2runtime/runtime/event_world').open(),{entity=7001,handle_slot=slot_ptr})==801)
-- A vanilla EAT-17 pod (another beacon) and ours.
local vanilla=pod(8100,147,777)
local w,events=capture({beacon_network=801,type=147,item_type='80932FA0ED6901D3',label='Gas EAT #1'})
tick(2)
assert(kinds(events)=='','nothing yet: '..kinds(events))
local mine=pod(8200,147,801)
tick()
assert(kinds(events)=='pod'and events[1].pod==8200)
-- The vanilla pod's rack lands first: never taken.
rack(vanilla,8101,147,{903})
tick(2)
assert(kinds(events)=='pod')
-- Ours: the rack and its two items.
rack(mine,8201,147,{901,902})
tick()
assert(kinds(events)=='pod,captured,ended',kinds(events))
local c=events[2]
assert(c.pod==8200 and c.rack==8201 and#c.items==2 and c.items[1]==5001 and c.items[2]==5002
    and c.slots[1]==0 and c.slots[2]==1)
assert(count('support pod CAPTURED (Gas EAT #1): pod 8200 -> rack 8201 (type 147): 2 items 5001, 5002 in slots 0, 1')==1,
    table.concat(logged,' | '))
return 'ok'
''')

    def test_an_ambiguous_or_unexpected_delivery_is_refused(self):
        self.check(r'''
mission({host=true})
W.network_id(901,5001,21);W.add{entity=5001,type='0000000000000042',unit=0,health=1}
W.register_entity(5001,'0000000000000042')
-- Two pods naming the beacon: refused.
pod(8100,147,801);pod(8200,147,801)
local _,e1=capture({beacon_network=801,type=147,item_type='80932FA0ED6901D3',label='a'})
tick()
assert(kinds(e1)=='refused,ended'and e1[1].code=='AMBIGUOUS',kinds(e1))
-- The right pod with an unexpected item type: refused (the item stays vanilla).
npods=0;W.write(TCOMP+T.count,W.u32(0))
local p=pod(8300,147,802)
local _,e2=capture({beacon_network=802,type=147,item_type='80932FA0ED6901D3',label='b'})
tick()
rack(p,8301,147,{901})
tick()
assert(kinds(e2)=='pod,refused,ended'and e2[2].code=='ITEM_UNEXPECTED',kinds(e2))
-- No pod within the deadline: refused.
local _,e3=capture({beacon_network=999,type=147,item_type='80932FA0ED6901D3',label='c'})
tick(math.ceil(pods.POD_SECONDS/0.125)+2)
assert(kinds(e3)=='refused,ended'and e3[1].code=='NO_POD',kinds(e3))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
