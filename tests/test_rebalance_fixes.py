"""0.31.0 rebalance reports (proof/RebalanceFixesProof):

1. Hover Pack height (research/docs/hover-height-F5FEE03DCFDB.md): no height member; the lift
   (hover.vertical_acceleration_low_speed) must exceed gravity (9.82) for the pack to climb; hover.duration is the climb
   window in seconds of air time. The descriptors say so, and the write lands in the record the flight code reads.
2. Wind-up (research/docs/windup-controls-F5FEE03DCFDB.md): the firing charge on every heat weapon with a wind-up
   (now also the Rover gun and the Laser Sentry) and the spin-up on every WeaponWindUp weapon (now also the Patriot
   minigun and the Maelstrom tank gun); windup.wind_down_seconds is a switch.
3. The CQC-20 Breaching Hammer's ability explosion on its support weapon target (scripts/ability_explosion_fields.py):
   the same row as hd2.explosion('support_weapon/cqc20_breaching_hammer/ability'), refused when the melee record no
   longer names the reviewed ability.
The snapshot tests write on a copy-on-write overlay of the retained snapshot."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from support import run
from test_multi_mod_composition import build_profile, snapshot_run

ROOT = Path(__file__).resolve().parents[1]
HOVER = json.loads((ROOT / 'research/hover-height-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
WINDUP = json.loads((ROOT / 'research/windup-controls-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
PROOF = ROOT / 'proof/RebalanceFixesProof'


class ResearchTests(unittest.TestCase):
    def test_hover_height_model(self):
        self.assertEqual(HOVER['model']['heightMember'][:4], 'none')
        self.assertAlmostEqual(HOVER['gravity']['value'], -9.82, places=3)
        self.assertTrue(HOVER['gravity']['appliedWhileHovering'])
        by = {s['label']: s for s in HOVER['scenarios']}
        # Vanilla, a higher cap or a longer window: no climb (the lift never beats gravity).
        for label in ('vanilla', 'max_vertical_speed 10 -> 30', 'duration 6 -> 12'):
            self.assertEqual(by[label]['steadyClimb'], 0.0, label)
            self.assertLess(by[label]['heightAtWindowEnd'], 0.5, label)
        self.assertAlmostEqual(by['vertical_acceleration_low_speed 9.8 -> 15']['steadyClimb'], 2.763, places=3)
        self.assertGreater(by['vertical_acceleration_low_speed 9.8 -> 15']['heightAtWindowEnd'], 14)
        self.assertIn('the record HD2Runtime writes is the record the flight code reads',
            HOVER['recordIdentity']['conclusion'])

    def test_windup_controls_name_a_field_for_every_wind_up(self):
        reduce = {c['weapon']: c['reduce'] for c in WINDUP['controls']}
        for weapon in ('LAS-16 Sickle', 'LAS-17 Double-Edge Sickle', 'LAS-5 Scythe', 'LAS-7 Dagger',
                'LAS-98 Laser Cannon', 'LAS-99 Quasar Cannon', 'AX/LAS-5 Rover gun', 'A/LAS-98 Laser Sentry'):
            self.assertIn('heat.firing_charge', reduce[weapon], weapon)
        for weapon in ('M-1000 Maxigun', 'A/G-16 Gatling Sentry', 'EXO-45 Patriot Exosuit minigun',
                'TD-110 Maelstrom tank gun'):
            self.assertIn('windup.wind_up_seconds', reduce[weapon], weapon)
        spin = {r['record']: r for r in WINDUP['spinUp']['records']}
        self.assertEqual((spin[0]['windUpSeconds'], spin[1]['windUpSeconds'], spin[8]['windUpSeconds']), (1, 0.5, 0.5))
        self.assertIn('never read', WINDUP['spinUp']['members']['+4'])

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained snapshot (game.dll image) not available')
    def test_research_outputs_are_current(self):
        for script in ('research_hover_height.py', 'research_windup_controls.py'):
            result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), '--check'], cwd=ROOT,
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, script + ': ' + result.stdout + result.stderr)


class CatalogueTests(unittest.TestCase):
    def test_descriptors(self):
        self.assertEqual(run(r'''
local function field(fields,id)for _,f in ipairs(fields)do if f.semanticFieldId==id then return f end end end
-- 1. Hover Pack: the lift explains gravity; the duration is the climb window.
local E=require('hd2runtime/domains/entity_authoring')
local hover=E.backpacks['LIFT-860 Hover Pack'].fields
local lift=assert(field(hover,'hover.vertical_acceleration_low_speed'))
assert(lift.currentDefault>9.79 and lift.currentDefault<9.81 and lift.acknowledgementReason:find('9.82',1,true))
assert(field(hover,'hover.duration').acknowledgementReason:find('climb window',1,true))
assert(field(hover,'hover.max_vertical_speed').acknowledgementReason:find('changes nothing',1,true))
-- 2. Wind-up: vehicles, the Laser Sentry and the Maxigun.
local V=require('hd2runtime/domains/vehicle_weapon_authoring').weapons
for key,value in pairs({['EXO-45 Patriot Exosuit / right_gun']=1,['TD-110 Maelstrom / attach_tank_gun']=0.5})do
    local f=assert(field(V[key].fields,'windup.wind_up_seconds'),key)
    assert(f.currentDefault==value and f.acknowledgement=='allow_unverified_effect'and f.min==0 and f.max==30,key)
    assert(f.backing.component=='WeaponWindUpComponentData'and f.backing.offset==0,key)
    assert(field(V[key].fields,'windup.wind_down_seconds').acknowledgementReason:find('switch',1,true),key)
end
local rover=V['AX/LAS-5 Rover / gun'].fields
assert(field(rover,'heat.firing_charge').currentDefault==100 and field(rover,'heat.charge_gain_per_second').currentDefault==400)
assert(not field(rover,'heat.reset_charge_after_shot'))
local S=require('hd2runtime/domains/stratagem_authoring')
local sentry=S.stratagems['A/LAS-98 Laser Sentry']
local charge=assert(field(sentry.fields,'heat.firing_charge'))
assert(charge.currentDefault==100 and charge.acknowledgement=='allow_unverified_effect'and charge.backing.offset==148)
assert(field(sentry.fields,'heat.charge_gain_per_second').currentDefault==200)
local W=require('hd2runtime/domains/support_weapon_authoring').weapons
local maxigun=W['M-1000 Maxigun'].fields
assert(field(maxigun,'windup.wind_up_seconds').max==30 and field(maxigun,'windup.wind_down_seconds').min==0)
assert(field(maxigun,'windup.wind_down_seconds').acknowledgementReason:find('switch',1,true))
-- 3. The Breaching Hammer's ability explosion.
local hammer=W['CQC-20 Breaching Hammer']
assert(hammer.branchRoles['CQC-20 BREACHING HAMMER IE']=='ability'and hammer.attacks.ability.kind=='Explosion')
local blast=assert(field(hammer.fields,'explosion.ability.damage.standard_damage'))
assert(blast.currentDefault==2200 and blast.acknowledgement=='allow_unverified_effect')
assert(blast.backing.linkage=='ability_explosion_damage'and blast.backing.abilityId==38 and blast.backing.abilityOffset==160)
assert(blast.backing.explosionType==19 and blast.backing.row==556 and blast.backing.recordType==562)
local radius=assert(field(hammer.fields,'explosion.ability.outer_radius'))
assert(radius.currentDefault==3 and radius.backing.linkage=='ability_explosion'and radius.backing.row==222
    and radius.backing.recordType==19)
assert(field(hammer.fields,'explosion.ability.damage.ap_direct').currentDefault==6)
return 'ok'
'''), b'ok')

    def test_hammer_handle_and_acknowledgements(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local F=hd2.fields
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
local blast=hd2.support_weapon('CQC-20 Breaching Hammer'):attack('ability'):explosion()
assert(blast.path=='explosion'and blast.attack=='ability')
local same=hd2.support_weapon('CQC-20 Breaching Hammer'):explosion('CQC-20 BREACHING HAMMER IE')
assert(same.attack=='ability')
rejects(function()writes.validate_patch{id='a',target=blast,allow_shared=true,field=F.explosion.damage_standard_damage,
 expect=2200,value=5000}end,'allow_unverified_effect')
rejects(function()writes.validate_patch{id='s',target=blast,allow_unverified_effect=true,
 field=F.explosion.damage_standard_damage,expect=2200,value=5000}end,'allow_shared')
rejects(function()writes.validate_patch{id='e',target=blast,allow_shared=true,allow_unverified_effect=true,
 field=F.explosion.damage_standard_damage,expect=300,value=5000}end,'expect differs')
local ok=writes.validate_patch{id='ok',target=blast,allow_shared=true,allow_unverified_effect=true,
 field=F.explosion.outer_radius,expect=3,value=6}
assert(ok.changes[1].descriptor.backing.linkage=='ability_explosion')
-- The melee swing stays its own row.
local melee=writes.validate_patch{id='m',target=hd2.support_weapon('CQC-20 Breaching Hammer'):attack('primary'),allow_shared=true,
 field=F.damage.player_standard_damage,expect=300,value=400}
assert(melee.changes[1].descriptor.backing.linkage=='melee_damage')
return 'ok'
'''), b'ok')

    def test_proof_toggles_are_differentiated(self):
        source = (PROOF / 'src/addon.lua').read_text(encoding='utf-8')
        readme = (PROOF / 'README.md').read_text(encoding='utf-8')
        self.assertEqual((PROOF / 'VERSION').read_text().strip(), '0.1.0')
        for toggle in ('hover_climb', 'hover_long_window', 'hover_cap_only', 'sickle_instant', 'sickle_slow',
                'quasar_fast', 'maxigun_instant', 'maxigun_slow', 'maxigun_hard_stop', 'patriot_instant',
                'rover_instant', 'laser_sentry_slow', 'hammer_big_blast', 'hammer_gentle_blast'):
            self.assertIn("id='" + toggle + "'", source)
        self.assertIn('allow_unverified_effect=true', source)
        self.assertIn('expect no change', source)
        self.assertIn('**no change**', readme)


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class SnapshotTests(unittest.TestCase):
    def test_every_proof_write_applies(self):
        result = snapshot_run(r'''
update=update or function()end
local F=hd2.fields
local hover=hd2.backpack('LIFT-860 Hover Pack')
local hammer=hd2.support_weapon('CQC-20 Breaching Hammer'):attack('ability'):explosion()
local blast={{field=F.explosion.damage_standard_damage,expect=2200,value=5000},
    {field=F.explosion.damage_durable_damage,expect=2200,value=5000},{field=F.explosion.outer_radius,expect=3,value=6}}
-- The support target and the catalogue handle resolve to the same bytes.
local a=resolve('transaction',{id='a',target=hammer,allow_shared=true,allow_unverified_effect=true,changes=blast})
local c=resolve('transaction',{id='c',target=hd2.explosion('support_weapon/cqc20_breaching_hammer/ability'),
    allow_unverified_effect=true,changes=blast})
check(#a==3 and #c==3,'three members each')
for i=1,3 do check(a[i].at==c[i].at,'same address '..i)end
local ops={
    {id='hover',target=hover,changes={{field=F.hover.vertical_acceleration_low_speed,expect=9.8,value=15},
        {field=F.hover.duration,expect=6,value=10}}},
    {id='sickle',target=hd2.weapon('LAS-16 Sickle'),changes={{field=F.heat.firing_charge,expect=100,value=0}}},
    {id='quasar',target=hd2.support_weapon('LAS-99 Quasar Cannon'),
        changes={{field=F.heat.charge_gain_per_second,expect=33,value=100}}},
    {id='maxigun',target=hd2.support_weapon('M-1000 Maxigun'),changes={{field=F.windup.wind_up_seconds,expect=0.5,
        value=0},{field=F.windup.wind_down_seconds,expect=0.5,value=0}}},
    {id='patriot',target=hd2.vehicle('EXO-45 Patriot Exosuit'):weapon('right_gun'),
        changes={{field=F.windup.wind_up_seconds,expect=1,value=0}}},
    {id='rover',target=hd2.backpack('AX/LAS-5 Rover'):drone():weapon(),
        changes={{field=F.heat.firing_charge,expect=100,value=0}}},
    {id='sentry',target=hd2.stratagem('A/LAS-98 Laser Sentry'):deployed_entity():weapon('primary'),
        changes={{field=F.heat.charge_gain_per_second,expect=200,value=50}}},
    {id='hammer',target=hammer,allow_shared=true,changes=blast},
}
local h={}
events.run_as('mods/test/rebalance_fixes',function()
    for _,op in ipairs(ops)do
        h[#h+1]=hd2.ensure({transaction={id='rebalance-'..op.id,target=op.target,allow_unverified_effect=true,
            allow_shared=op.allow_shared,changes=op.changes}})
    end
end)
settle(h)
local expected=0
for i,op in ipairs(ops)do
    check(h[i].runs>=1 and h[i].result and h[i].result.status=='APPLIED',op.id..' '..tostring(h[i].error))
    expected=expected+#op.changes
end
check(runtime.read(a[1].at,4)==b.encode(5000,'i32'),'blast damage written')
local n=0
for _ in pairs(overlay)do n=n+1 end
check(n==expected,'exactly the proof members written: '..n..' of '..expected)
return json.encode({ok=true,writes=n})
''')
        self.assertTrue(result['ok'])
        self.assertEqual(result['writes'], 12)

    def test_a_changed_ability_slot_refuses_the_hammer_blast(self):
        result = snapshot_run(r'''
update=update or function()end
local writes=require('hd2runtime/domains/player_weapon_writes')
local hammer=hd2.support_weapon('CQC-20 Breaching Hammer'):attack('ability'):explosion()
local body={id='h',target=hammer,allow_shared=true,allow_unverified_effect=true,
    changes={{field=hd2.fields.explosion.outer_radius,expect=3,value=6}}}
local slot
local worker=coroutine.create(function()
    local spec=transactions.validate(body)
    local reader=Reader.new(runtime)
    local resolved=writes.capture(runtime,reader,spec)
    local record=resolved.catalog.record(resolved.candidate,'MeleeWeaponComponentData')
    check(b.u32(record.bytes,160)==38,'the hammer names ability 38')
    slot=record.owner.base+record.offset+160
end)
repeat local ok,why=coroutine.resume(worker);assert(ok,why)until coroutine.status(worker)=='dead'
-- Another mod points the hammer at a different ability: the blast fields are refused, nothing is written.
overlay[slot]=b.encode(39,'u32')
local ok,why=pcall(resolve,'transaction',body)
check(not ok and tostring(why):find('ABILITY_CHANGED',1,true),tostring(why))
return json.encode({ok=true})
''')
        self.assertTrue(result['ok'])


if __name__ == '__main__':
    unittest.main()
