"""Per-shot modification (runtime/projectile_shots.lua, api/shots.lua; research/projectile-ballistics-F5FEE03DCFDB.json):
the local player's own shot of a configured weapon (its projectile type fired by its entity type) has its own copies
written once, in one guarded transaction: the damage and penetration multipliers (hit +0x34, +0x38), the velocity and
reference speed together, the gravity and the drag constant, each multiplied; another weapon firing the same projectile
type (the Liberator Carbine), another player's shot and every row stay vanilla; every guard leaves the shot vanilla;
on_shot reports the shot's before and after values and its DamageInfo; the domain is the research's."""
import unittest

from support import ROOT, run
from test_gas_eat import lua as gas_lua

SHOTS = r"""
local api=require('hd2runtime/api/shots')
local shots=require('hd2runtime/runtime/projectile_shots');shots.reset_for_tests()
local DB=require('hd2runtime/domains/projectile_ballistics')
local DD=require('hd2runtime/domains/direct_damage')
for _,pin in ipairs(DB.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local LIB,CARBINE='968211C0033DCE64','A7EE1EBF58FCDF1F'
-- The Liberator's direct hit, DamageInfo 108 (90 / 22, AP 2/2/2/0), in the DamageInfo table.
local row108=W.alloc(DD.stride)
W.write(row108,W.u32(108)..W.u32(90)..W.u32(22)..W.u32(2)..W.u32(2)..W.u32(2)..W.u32(0)..string.rep('\0',DD.stride-28))
W.write(W.GAME+tonumber(DD.table:sub(3),16)+108*8,W.u64(row108))
local liberator_row=W.projectile_row(276,W.u32(276)..string.rep('\0',0x10C))
local LIBROW=W.read(liberator_row,0x110)
local function sworld()
    local h=iworld()
    for _,e in ipairs({{6001,LIB},{6002,CARBINE}})do
        W.add{entity=e[1],type=e[2],unit=0,health=1};W.register_entity(e[1],e[2])
    end
    return h
end
local function f(v)return b.encode(v,'f32')end
local function rf(at)return b.value(W.read(at,4),0,'f32')end
-- A shot as SpawnProjectile leaves it: velocity 900 m/s along +X, reference 900, gravity 1, drag 0.002, multipliers 1.
local function shoot(source,opts)
    opts=opts or{}
    local slot,hit=fire(source,{type=276,creditor=opts.creditor})
    local flight=W.projectile_system+DB.flight.base+slot*DB.flight.stride
    W.write(flight+DB.flight.velocity,f(900)..f(0)..f(0))
    W.write(flight+DB.flight.gravity,f(1))
    W.write(flight+DB.flight.drag,f(0.002))
    W.write(flight+DB.flight.speed,f(opts.reference or 900))
    W.write(flight+DB.flight.distance,f(0))
    W.write(flight+DB.flight.unit,W.u32(opts.unit or 0))
    W.write(hit+DB.hit.directDamage,W.u32(108))
    W.write(hit+DB.hit.armorPenetration,string.char(2,0,2,0,2,0,0,0))
    W.write(hit+DB.hit.damageMultiplier,f(opts.multiplier or 1)..f(1))
    return slot,hit,flight
end
"""


def lua(body):
    return gas_lua(SHOTS + body)


class ProjectileShotsTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_liberators_own_shot_is_modified_and_nothing_else(self):
        self.check(r'''
sworld()
local events={}
local h=api.modify_shots('AR-23 Liberator',{damage=0.5,armor_penetration=2,speed=0.5,gravity=0.25,drag=2,
    on_shot=function(e)events[#events+1]=e end})
assert(h.status=='active',tostring(h.code)..' '..tostring(h.reason))
tick()
local writes=#W.runtime.writes
-- The Liberator Carbine fires the same projectile 276: vanilla.
local _,chit,cflight=shoot(6002)
tick()
assert(#W.runtime.writes==writes and rf(chit+DB.hit.damageMultiplier)==1 and rf(cflight+DB.flight.velocity)==900,
    'the Carbine was touched')
-- Another player's Liberator shot: vanilla.
shoot(6001,{creditor='9999888877776666'});tick()
assert(#W.runtime.writes==writes and#events==0)
-- This player's Liberator shot: each copy written once.
local slot,hit,flight=shoot(6001)
tick()
assert(rf(hit+DB.hit.damageMultiplier)==0.5 and rf(hit+DB.hit.penetrationMultiplier)==2,'multipliers')
assert(rf(flight+DB.flight.velocity)==450 and rf(flight+DB.flight.speed)==450,'speed and reference together')
assert(rf(flight+DB.flight.gravity)==0.25 and math.abs(rf(flight+DB.flight.drag)-0.004)<1e-7,'gravity and drag')
local e=events[1]
assert(e.kind=='modified'and e.slot==slot and e.source==6001 and e.verify.readBack and e.verify.nonTarget,'event')
assert(e.before.damage_multiplier==1 and e.after.damage_multiplier==0.5 and e.before.speed==900 and e.after.speed==450)
assert(e.before.damage.id==108 and e.before.damage.standard==90 and e.before.damage.durable==22
    and e.before.damage.armor_penetration[1]==2 and e.before.armor_penetration[1]==2,'its DamageInfo')
assert(count('shots (')>=1 and count('first AR-23 Liberator shot modified: pool slot '..slot)==1,
    table.concat(logged,' | '))
-- Written once: a second update leaves it.
local n=#W.runtime.writes
tick()
assert(#W.runtime.writes==n)
-- The rows stay vanilla.
assert(W.read(liberator_row,0x110)==LIBROW and W.read(row108,8)==W.u32(108)..W.u32(90))
-- New multipliers for the next shots; the stats count it all.
assert(h:set({damage=2}))
local _,hit2=shoot(6001);tick()
assert(rf(hit2+DB.hit.damageMultiplier)==2 and rf(hit+DB.hit.damageMultiplier)==0.5)
local s=h:stats()
assert(s.shots==2 and s.modified==2 and s.other_sources==1 and s.others==1,tostring(s.shots)..' '..s.modified)
-- Multipliers of 1: untouched, reported.
assert(h:set({}))
local _,hit3=shoot(6001);tick()
assert(rf(hit3+DB.hit.damageMultiplier)==1 and events[#events].kind=='untouched')
h:stop()
assert(h.status=='stopped')
return 'ok'
''')

    def test_every_guard_leaves_the_shot_vanilla(self):
        self.check(r'''
sworld()
local h=api.modify_shots('AR-23 Liberator',{damage=0.5})
tick()
-- A unit drives it.
local _,h1=shoot(6001,{unit=77});tick()
assert(rf(h1+DB.hit.damageMultiplier)==1 and h:stats().refused.UNIT_DRIVEN==1)
-- An unexpected state (no reference speed).
local _,h2=shoot(6001,{reference=0});tick()
assert(rf(h2+DB.hit.damageMultiplier)==1 and h:stats().refused.UNEXPECTED_STATE==1)
-- Several players: solo only.
W.players({{peer=LOCAL_PEER,avatar=100},{peer='9999888877776666',avatar=101}},LOCAL_PEER)
local _,h3=shoot(6001);tick()
assert(rf(h3+DB.hit.damageMultiplier)==1 and h:stats().refused.NOT_SOLO==1,tostring(h:stats().refused.NOT_SOLO))
W.players({{peer=LOCAL_PEER,avatar=100}},LOCAL_PEER)
-- A pin changed: unavailable, nothing written.
shots.reset_for_tests()
require('hd2runtime/runtime/event_world').open().projectile_shots_proven=nil   -- the proof is cached per world
local pin=DB.pins[1]
W.write(W.GAME+pin.rva,string.rep('\144',#pin.hex/2))
local h4=api.modify_shots('AR-23 Liberator',{damage=0.5})
tick()
local _,h5=shoot(6001);tick()
assert(rf(h5+DB.hit.damageMultiplier)==1 and count('shots UNAVAILABLE: every shot stays vanilla')==1,
    table.concat(logged,' | '))
return 'ok'
''')

    def test_the_options_and_refusals(self):
        self.check(r'''
local function refused(handle,code)
    assert(handle.status=='refused'and handle.code==code,tostring(handle.code)..': '..tostring(handle.reason))
end
refused(api.modify_shots('Nonexistent Gun',{damage=0.5}),'UNKNOWN_WEAPON')
refused(api.modify_shots('AR-23 Liberator',{damage=0}),'INVALID_OPTION')
refused(api.modify_shots('AR-23 Liberator',{damage=0.5,colour='red'}),'INVALID_OPTION')
refused(api.modify_shots('AR-23 Liberator',{on_shot=5}),'INVALID_OPTION')
local a=api.modify_shots('AR-23 Liberator',{damage=0.5,owner='mods/a'})
assert(a.status=='active')
refused(api.modify_shots('AR-23 Liberator',{damage=0.5,owner='mods/b'}),'ALREADY_MODIFIED')
-- The same owner replaces its own.
local a2=api.modify_shots('AR-23 Liberator',{damage=2,owner='mods/a'})
assert(a2.status=='active'and#api.status()==1 and api.status()[1].changes.damage==2)
assert(select(2,a2:set({speed=50}))=='INVALID_OPTION')
local hd2=require('hd2runtime/api/hd2')
assert(hd2.projectiles.modify_shots==api.modify_shots and hd2.projectiles.modify_shots_status==api.status)
return 'ok'
''')


class ProjectileShotsDomainTests(unittest.TestCase):
    def test_the_domain_is_the_research(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('g', ROOT / 'scripts/generate_projectile_ballistics.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.generate(check=True), [])
        d = module.build()
        self.assertEqual(d['hit']['damageMultiplier'], 0x34)
        self.assertEqual(d['hit']['penetrationMultiplier'], 0x38)
        self.assertEqual((d['flight']['velocity'], d['flight']['speed'], d['flight']['gravity'], d['flight']['drag']),
            (0x0C, 0x2C, 0x1C, 0x28))
        self.assertEqual(len(d['pins']), 178)
        self.assertIn(0x13AD524, [p['rva'] for p in d['pins']])


if __name__ == '__main__':
    unittest.main()
