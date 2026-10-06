"""Slow payloads for the Pelican gunship: a damage-over-time volume a round (an EMS field, a gas cloud) at an explicit low
rate (research/custom-payloads slowDonors; runtime/explosion_donors.lua slow donors, runtime/projectile_impact.lua
RATE_EXCEEDED, runtime/pelican_weapon.lua hold_rate / release_window / the mirror's explicit rate, runtime/pelican_gunship.lua
gun.rpm, gun.casing and round 'native'; build/test-artifacts/payload-research/payload-donors.md,
build/test-artifacts/mortar-fire-research/mortar-fire.md):
  * the research: the EMS Mortar Sentry's field 180, the G-4 Gas grenade's cloud 177 and the Gas Mortar Sentry's 185,
    each chain reviewed, at most 60 a minute;
  * a slow donor reaches a gun only at or below its max_rpm, never the launcher, Eagle or orbital families, and its
    binding converts at most that many rounds a minute (RATE_EXCEEDED: the round stays vanilla);
  * an explicit rate is held on the turret's own copy's rate slot (as the Gatling rate is) and on every other machine's
    mirror; the not-hittable window covers three shots at a slow rate;
  * the casing may stay the chin turret's own, and the round may be the chin turret's own (120)."""
import unittest

from support import ROOT, run
from support import lua as lua_literal
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_gas_eat import IMPACT
from test_pelicans import PELICANS
from test_pelican_gatling import GATLING
from test_pelican_weapon import WEAPON
from test_pelican_ai import AI
from test_pelican_heading import HEADING
from test_pelican_readonly_probes import HARNESS
from test_pelican_gatling_proof import PROOF
from test_pelican_gunship import GUNSHIP
from test_custom_mp_pelican import MIRROR
from test_custom_stratagem_api import REGISTRATION
from test_pelican_explosive_rounds import EXPLOSIVE, RESEARCH

# The EMS mortar field's chain exactly as reviewed, and the chin turret's own round 120 (impact 234, no expiry).
SLOW = r"""
local SD=CP.explosionDonors['EMS mortar field']
for _,item in ipairs(SD.rows)do
    local at=W.alloc(item.stride);W.write(at,b.unhex(item.reviewed))
    W.write(W.GAME+tonumber(item.table:sub(3),16)+item.id*8,W.u64(at))
end
local row120=W.projectile_row(120,W.u32(120)..string.rep('\0',0x8C)..W.u32(234)..string.rep('\0',8)..W.u32(0)
    ..string.rep('\0',0x110-0xA0))
"""


class ResearchTests(unittest.TestCase):
    def test_the_slow_donors(self):
        donors = {name: d for name, d in RESEARCH['explosionDonors'].items() if d.get('slow')}
        facts = {name: (d['round'], d['roundRole'], d['explosion'], d['maxRpm'], d['volume'], d['radii'],
            d['damage']['standard'], d['asset'] or d['assetKey']) for name, d in donors.items()}
        self.assertEqual(facts, {
            'EMS mortar field': (154, 'expiry', 180, 60, {'template': 15, 'seconds': 7.0, 'statuses': [38]},
                [1.0, 10.0, 12.0], 0, 'A/M-23 EMS Mortar Sentry'),
            'Gas grenade cloud': (None, None, 177, 60, {'template': 16, 'seconds': 15.0, 'statuses': [42, 44]},
                [2.0, 7.0, 7.0], 3, 'throwable/G-4 Gas'),
            'Gas mortar cloud': (342, 'impact', 185, 60, {'template': 16, 'seconds': 15.0, 'statuses': [42, 44]},
                [2.0, 7.0, 7.0], 0, 'A/GM-17 Gas Mortar Sentry')})
        names = {name: {p['name'] for p in d['packages']} for name, d in donors.items()}
        self.assertEqual(names['EMS mortar field'], {'packages/generated/loadout/mortar_turret_staticfield'})
        self.assertIn('packages/generated/loadout/gas_grenade', names['Gas grenade cloud'])
        self.assertIn('packages/generated/loadout/mortar_turret_gas', names['Gas mortar cloud'])
        # The same volume templates as the reviewed orbital donors (the EMS Strike's StaticField, the Gas Strike's cloud).
        self.assertEqual(RESEARCH['explosionDonors']['Orbital EMS Strike']['links']['template'], 15)
        for name, d in donors.items():
            self.assertEqual([r['kind'] for r in d['rows']][:2], ['explosion', 'damage'], name)
            self.assertIn('template', [r['kind'] for r in d['rows']], name)
        self.assertIn('4096 status volumes', RESEARCH['semantics']['slowDonors'])


class DonorTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + IMPACT + EXPLOSIVE + SLOW + body + "\nreturn 'ok'"), b'ok')

    def test_a_slow_donor_reaches_a_slow_gun_only(self):
        self.check(r"""
local d=donors.DONORS['EMS mortar field']
assert(d.slow and d.max_rpm==60 and d.explosion==180 and d.key=='ems_mortar_field'and not d.automatic)
assert(donors.resolve('ems_mortar_field',{gun=true,rpm=30})=='EMS mortar field')
assert(donors.resolve('gas_grenade_cloud',{gun=true,rpm=60})=='Gas grenade cloud')
assert(donors.resolve('EMS mortar field',{gun=true,rpm=61})==nil,'above its rate')
assert(donors.resolve('EMS mortar field',{gun=true,rpm=math.huge})==nil,'a gun without an explicit rate')
assert(donors.resolve('EMS mortar field',{automatic=true})==nil,'not an automatic donor')
assert(donors.resolve('EMS mortar field')==nil,'never a launcher\'s, an Eagle\'s or an orbital\'s')
-- An automatic donor still fits any gun.
assert(donors.resolve('pelican_chin_autocannon',{gun=true,rpm=30})=='Pelican chin autocannon')
assert(table.concat(donors.names({gun=true,rpm=30}),', ')=='66mm Missile Mk2, Assault walker cannon, Automaton '
    ..'explosion 27, EMS mortar field, Exploding crossbow, Gas grenade cloud, Gas mortar cloud, Illuminate explosion 392, '
    ..'Pelican chin autocannon, Strafing run cannon')
assert(table.concat(donors.names(),', ')=='Orbital EMS Strike, Orbital Gas Strike')
-- Their packages: the EMS Mortar Sentry's call-in package, the G-4 Gas grenade's own.
local de,dg=donors.dependency('EMS mortar field'),donors.dependency('Gas grenade cloud')
assert(de and de.package=='0x4666692B63185121',tostring(de and de.package))
assert(dg and dg.package=='0x25A04F6D9707D2CC',tostring(dg and dg.package))
-- Ready: its chain exactly as reviewed; a changed row is refused.
iworld()
donors.READY_CALLS=0
assert(donors.ready(world_module.open(),'EMS mortar field'))
""")

    def test_a_slow_binding_converts_at_most_its_rate(self):
        self.check(r"""
iworld()
donors.READY_CALLS=0
local function refused(spec,code,text)
    local b_,c,why=impacts.bind(spec)
    assert(not b_ and c==code and(not text or tostring(why):find(text,1,true)),tostring(c)..' '..tostring(why))
end
-- Only a continuous binding (a gun) takes it.
refused({sources={5001},projectile=120,donor='EMS mortar field'},'UNSUITABLE_DONOR','reviewed for a gun only')
local events={}
local binding,code,why=impacts.bind({sources={5001},projectiles={120},donor='EMS mortar field',continuous=true,
    provenance=true,label='EMS rounds'},function(e)events[#events+1]=e end)
assert(binding,tostring(code)..' '..tostring(why))
assert(binding.from==234 and binding.to==180 and binding.max_rpm==60 and math.abs(binding.min_gap-0.8)<1e-9)
tick()
local _,h1=fire(5001,{type=120,impact=234})
tick()
local seen={}
for _,e in ipairs(events)do seen[#seen+1]=tostring(e.kind)..' '..tostring(e.code)..' '..tostring(e.reason)end
assert(impact_of(h1)==180,'the first round: '..impact_of(h1)..' | '..table.concat(seen,' | '))
-- A round 0.125 s later: faster than 60 a minute; it keeps its own explosion.
local _,h2=fire(5001,{type=120,impact=234})
tick()
assert(impact_of(h2)==234,'too soon: '..impact_of(h2))
local rate
for _,e in ipairs(events)do if e.kind=='refused'and e.code=='RATE_EXCEEDED'then rate=e end end
assert(rate and rate.reason:find('EMS mortar field makes at most 60 volumes a minute',1,true),tostring(rate and rate.reason))
-- 1 s after the first: converted again.
for _=1,6 do tick()end
local _,h3=fire(5001,{type=120,impact=234})
tick()
assert(impact_of(h3)==180,'a second later: '..impact_of(h3))
assert(binding.converted==2)
""")


class WeaponTests(unittest.TestCase):
    def weapon(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + body
            + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_an_explicit_rate_is_held_on_its_own_copys_rate_slot(self):
        self.weapon(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local function cfg(spec)return in_update(function()return weapon.configure(world,9501,spec,'test')end)end
assert(select(2,cfg({projectile=120,rpm='gatling',hold_rate=true}))=='INVALID')
assert(select(2,cfg({projectile=120,rpm=30,hold_rate=1}))=='INVALID')
local w0=weapon.release_window(8102)
assert(w0==weapon.RELEASE_SECONDS)
local r,code,reason=cfg({projectile=120,rpm=30,hold_rate=true})
assert(r and r.verified,tostring(code)..' '..tostring(reason))
assert(r.verify.rate_slot==true and r.spec.slot_rpm==30 and r.spec.rpm==30,tostring(r.spec.rpm))
local w=pelicans.weapon_config(world,8102)
assert(w.copy.projectileType==120 and w.currentRpm==30,tostring(w.currentRpm))
assert(n('rate slot 300 -> 30')==1 and n('the requested 30 RPM x 1.00 (the factor the game applied to this turret)')>=1,
    table.concat(logged,' | '))
-- Three shots and a half second at 30 RPM before an unhittable target is let go.
assert(math.abs(weapon.release_window(8102)-6.5)<1e-9,weapon.release_window(8102))
""")

    def test_the_mirror_holds_the_explicit_rate_its_own_casing_and_round(self):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + MIRROR
            + r"""
local world=client_copy()
local spec={}
for k,v in pairs(SPEC)do spec[k]=v end
spec.round,spec.rpm,spec.casing,spec.rate_factor='native',30,'own',nil
local r,code,reason=in_update(function()return weapon.mirror_configure(world,8102,spec,'mirror')end)
assert(r and r.projectile==120 and r.rpm==30,tostring(code)..' '..tostring(reason))
assert(not r.casing.wanted and r.verify.casing==nil,'its own casing')
assert(n('rate slot 30')==1,table.concat(logged,' | '))
-- Its cadence: the explicit rate times the factor read from the entry (the seed, or the host's rate).
local rpm,interval,basis,f=weapon.mirror_expected(300,1,30)
assert(rpm==30 and interval==2 and basis=='seed'and f==1,tostring(rpm)..' '..tostring(interval))
rpm,interval,basis=weapon.mirror_expected(30,1,30)
assert(rpm==30 and basis=='gatling')
rpm,interval,basis,f=weapon.mirror_expected(270,1,30)
assert(math.abs(rpm-27)<1e-4 and math.abs(interval-60/27)<1e-4 and basis=='seed'and f~=1)
assert(weapon.mirror_expected(1600,1,30)==nil,'neither the seed nor the explicit rate')
-- Without the explicit rate: the Gatling rate as before.
assert(weapon.mirror_expected(300,1)==1600)
return 'ok'
end)()
"""), b'ok')


class GunshipTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + "\nlocal PROOF_ADDON=''\nlocal PROOF_RESOURCE="
            + lua_literal('mods/test/gunship') + '\n' + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI
            + HEADING + PROOF + GUNSHIP + body + '\nend)()\n'), b'ok')

    def test_the_rate_casing_and_round_options(self):
        self.lua(r"""
local function bad(gun,text)
    local ok,why=gunship.check_gun(gun)
    assert(not ok and why==text,tostring(why))
end
local G='gatling_sentry'
bad({rpm=30},'gun.rpm is the Gatling AI\'s rate: it needs behave_as = \'gatling_sentry\'')
bad({behave_as=G,rpm=10},'gun.rpm is rounds a minute, 30 to 3000')
bad({behave_as=G,rpm=30,rate_multiplier=2},'gun.rpm replaces the Gatling rate: no rate_multiplier')
bad({casing='mortar'},'gun.casing must be \'gatling\' or \'own\'')
bad({casing='gatling'},'gun.casing = \'gatling\' goes with behave_as = \'gatling_sentry\'')
-- A slow donor needs an explicit rate at most its max_rpm.
local ok,why=gunship.check_gun({behave_as=G,impact_explosion='ems_mortar_field'})
assert(not ok and why:find('reviewed for its rate (a slow donor needs gun.rpm)',1,true),tostring(why))
ok,why=gunship.check_gun({behave_as=G,rpm=120,impact_explosion='EMS mortar field'})
assert(not ok and why:find('reviewed for 120 RPM',1,true)and not why:find('EMS mortar field',1,true),tostring(why))
local g=assert(gunship.check_gun({behave_as=G,rpm=30,round='native',casing='own',impact_explosion='ems_mortar_field',
    sound='sentry/ems_mortar'}))
assert(g.rpm==30 and g.round=='native'and g.casing=='own'and g.impact=='EMS mortar field'and g.sound=='sentry/ems_mortar')
assert(gunship.check_gun({behave_as=G}).casing=='gatling'and gunship.check_gun({}).casing==nil)
-- The donor and its assets as the registry hash and the definition see them.
assert(gunship.impact_now('gas_grenade_cloud',60)=='Gas grenade cloud'and gunship.impact_now('gas_grenade_cloud')=='none')
assert(table.concat(gunship.impact_assets('ems_mortar_field',30),',')=='A/M-23 EMS Mortar Sentry')
assert(#gunship.impact_assets('gas_grenade_cloud',60)==0,'a throwable: loaded by its asset key when armed')
assert(#gunship.round_assets('native')==0)
assert(gunship.gun_now({behave_as=G,rpm=60,impact_explosion='gas_grenade_cloud'}).impact_explosion=='gas_grenade_cloud')
return 'ok'
""")

    def test_the_gunship_passes_the_rate_casing_and_its_own_round(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
tick(4)
scene()
controller()
stage(0,2,0)
ai(4)
local captured
weapon.configure=function(world,pelican,spec)captured=spec;return nil,'TEST','stopped here'end
local gun={behave_as='gatling_sentry',rpm=30,round='native',casing='own',recoil=false,unlimited_ammo=true}
assert(gunship.arm(9501,{gun=gun,label='cas'},function()end))
tick(16)
assert(captured,'configured')
assert(captured.projectile==120 and captured.rpm==30 and captured.hold_rate==true and captured.rate_factor==nil
    and captured.casing==nil,tostring(captured.projectile)..' '..tostring(captured.rpm)..' '..tostring(captured.casing))
-- The Gatling rate and casing stay the default without them.
captured=nil
gunship.reset_for_tests()
assert(gunship.arm(9501,{gun={behave_as='gatling_sentry'},label='cas2'},function()end))
tick(16)
assert(captured and captured.rpm=='gatling'and captured.hold_rate==nil and captured.rate_factor==1
    and captured.casing==true and captured.projectile==148)
return 'ok'
""")


class RegistrationTests(unittest.TestCase):
    def test_a_slow_pelican_definition(self):
        out = run(REGISTRATION + r"""
local d=custom.register(spec({pelican={hover=90,gun={behave_as='gatling_sentry',rpm=30,round='native',casing='own',
    impact_explosion='ems_mortar_field',sound='sentry/ems_mortar',unlimited_ammo=true,recoil=false}}}),'mods/test/one')
assert(d.pelican.gun.impact_explosion=='EMS mortar field')
local assets=table.concat(d.assets or{},',')
assert(assets:find('A/M-23 EMS Mortar Sentry',1,true),assets)
local h30=custom.registry_hash()
custom.reset_for_tests();images.reset_for_tests();texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
custom.register(spec({pelican={hover=90,gun={behave_as='gatling_sentry',rpm=60,round='native',casing='own',
    impact_explosion='ems_mortar_field',sound='sentry/ems_mortar',unlimited_ammo=true,recoil=false}}}),'mods/test/one')
assert(custom.registry_hash()~=h30,'the rate is part of the registry hash')
-- A slow donor without its rate is refused at registration.
custom.reset_for_tests();images.reset_for_tests();texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
local ok,why=pcall(custom.register,spec({pelican={hover=90,gun={behave_as='gatling_sentry',
    impact_explosion='gas_grenade_cloud'}}}),'mods/test/one')
assert(not ok and tostring(why):find('a slow donor needs gun.rpm',1,true),tostring(why))
return 'ok'
""")
        self.assertEqual(out, b'ok')


if __name__ == '__main__':
    unittest.main()
