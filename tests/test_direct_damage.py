"""A round's DIRECT DAMAGE override (2026-10-07; runtime/projectile_impact.lua DIRECT DAMAGE, domains/direct_damage.lua,
scripts/research_direct_damage.py): a bound EAT-17 launcher's rocket (type 132) also hits with the reviewed 500 / 500
DamageInfo 238 instead of its row's 227: a second 4-byte change of ITS OWN hit record's DamageInfo copy (+0x0C), in the
same transaction as its impact explosion; its penetration copy (+0x18) untouched; no row (the rocket's, either
DamageInfo) ever written; every guard refuses with nothing written; the domain is the research's."""
import unittest

from support import ROOT, run
from test_gas_eat import lua as gas_lua

DAMAGE = r"""
local DD=require('hd2runtime/domains/direct_damage')
local TABLE=tonumber(DD.table:sub(3),16)
for _,pin in ipairs(DD.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
-- The DamageInfo table: the rocket's own 227 and the override 238, exactly as reviewed.
local R=DD.rounds['132']
local function damage_row(id,hex)
    local at=W.alloc(DD.stride)
    W.write(at,b.unhex(hex))
    W.write(W.GAME+TABLE+id*8,W.u64(at))
    return at
end
local row227=damage_row(R.from,R.fromReviewed)
local row238=damage_row(R.overrides['500'].damage,R.overrides['500'].reviewed)
W.write(rocket+0x3C,W.u32(227))
ROCKET=W.read(rocket,0x110)
local ROW227,ROW238=W.read(row227,DD.stride),W.read(row238,DD.stride)
-- A rocket as SpawnProjectile leaves it: its DamageInfo copy (+0x0C) and penetration copy (+0x18, u16 6).
local function dfire(source,opts)
    opts=opts or{}
    local slot,hit=fire(source,opts)
    W.write(hit+DD.hit.directDamage,W.u32(opts.damage or 227))
    W.write(hit+DD.hit.armorPenetration,string.char(6,0))
    return slot,hit
end
local function damage_of(hit)return b.u32(W.read(hit+DD.hit.directDamage,4),0)end
local function bind(extra)
    local spec={sources={5001,5002},projectile=132,donor='Orbital Gas Strike',entity_type=EAT_TYPE,label='Gas EAT 500',
        direct_damage=500}
    for k,v in pairs(extra or{})do spec[k]=v end
    local events={}
    local binding,code,why=impacts.bind(spec,function(e)events[#events+1]=e end)
    return binding,code,why,events
end
"""


def lua(body):
    return gas_lua(DAMAGE + body)


class DirectDamageTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_rocket_hits_with_the_override_on_its_own_copy(self):
        self.check(r'''
iworld()
local binding,code,why,events=bind()
assert(binding,tostring(code)..' '..tostring(why))
assert(binding.damage[132].from==227 and binding.damage[132].to==238)
tick()
local writes=#W.runtime.writes
local _,vanilla=dfire(5003)
tick()
assert(damage_of(vanilla)==227 and impact_of(vanilla)==376 and#W.runtime.writes==writes,'a vanilla rocket was touched')
local slot,hit=dfire(5001)
tick()
assert(impact_of(hit)==82 and damage_of(hit)==238,'not converted: '..impact_of(hit)..' / '..damage_of(hit))
local e=events[1]
assert(e.kind=='converted'and e.damage_from==227 and e.damage_to==238 and e.verify.readBack and e.ap_kept
    and e.verify.nonTarget,'event')
assert(b.u32(W.read(hit+DD.hit.armorPenetration,2)..'\0\0',0)==6,'the penetration copy changed')
assert(count('impact explosion 376 -> 82, direct damage 227 -> 238 (its own +0x0C; penetration copy kept true) (')==1,
    table.concat(logged,' | '))
-- No shared row was ever written: the rocket's row and both DamageInfo rows.
assert(W.read(rocket,0x110)==ROCKET and W.read(row227,DD.stride)==ROW227 and W.read(row238,DD.stride)==ROW238)
return 'ok'
''')

    def test_every_guard_leaves_the_rocket_vanilla(self):
        self.check(r'''
iworld()
local binding,_,_,events=bind({rounds=4})
assert(binding)
tick()
local function last()return events[#events]end
-- Its DamageInfo copy is not the row's: refused, nothing written (its impact stays too).
local _,h1=dfire(5001,{damage=228});tick()
assert(last().code=='UNEXPECTED_DAMAGE'and impact_of(h1)==376 and damage_of(h1)==228,tostring(last().code))
-- The override row changed since the review: refused.
local saved=W.read(row238+4,4)
W.write(row238+4,W.u32(9999))
local _,h2=dfire(5001);tick()
assert(last().code=='DAMAGE_CHANGED'and impact_of(h2)==376 and damage_of(h2)==227,tostring(last().code))
W.write(row238+4,saved)
-- Intact again: the next rocket converts both.
local _,h3=dfire(5001);tick()
assert(last().kind=='converted'and impact_of(h3)==82 and damage_of(h3)==238)
return 'ok'
''')

    def test_a_binding_with_a_direct_damage_is_refused_before_it_starts(self):
        self.check(r'''
iworld()
-- An unreviewed override.
local b1,c1,w1=bind({direct_damage=400})
assert(not b1 and c1=='UNREVIEWED_DAMAGE'and w1:find('reviewed: 500',1,true),tostring(c1)..' '..tostring(w1))
-- The rocket's row names another DamageInfo now.
W.write(rocket+0x3C,W.u32(383))
local b2,c2=bind()
assert(not b2 and c2=='DAMAGE_CHANGED',tostring(c2))
W.write(rocket+0x3C,W.u32(227))
-- The rocket's own DamageInfo row changed.
local saved=W.read(row227+8,4)
W.write(row227+8,W.u32(1))
local b3,c3=bind()
assert(not b3 and c3=='DAMAGE_CHANGED',tostring(c3))
W.write(row227+8,saved)
-- The spawn copy's code changed.
local pin=DD.pins[2]
W.write(W.GAME+pin.rva,string.rep('\144',#pin.hex/2))
local b4,c4=bind()
assert(not b4 and c4=='UNSUPPORTED_BUILD',tostring(c4))
W.write(W.GAME+pin.rva,b.unhex(pin.hex))
-- Without it: an impact binding as before (no damage change).
local b6,c6=impacts.bind({sources={5001},projectile=132,donor='Orbital Gas Strike',entity_type=EAT_TYPE})
assert(b6 and b6.damage==nil,tostring(c6))
return 'ok'
''')


class DirectDamageDomainTests(unittest.TestCase):
    def test_the_domain_is_the_research(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('generate_direct_damage', ROOT / 'scripts/generate_direct_damage.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.generate(check=True), [])
        d = module.build()
        r = d['rounds']['132']
        self.assertEqual(r['from'], 227)
        self.assertEqual((r['own']['standard'], r['own']['durable']), (2000, 2000))
        o = r['overrides']['500']
        self.assertEqual((o['damage'], o['standard'], o['durable'], o['armorPenetration']), (238, 500, 500, [6, 5, 4, 0]))
        self.assertEqual(d['hit'], {'directDamage': 12, 'armorPenetration': 24})


if __name__ == '__main__':
    unittest.main()
