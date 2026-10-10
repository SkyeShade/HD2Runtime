import importlib.util
import json
import re
import unittest

from support import ROOT, run


spec = importlib.util.spec_from_file_location(
    'generate_vehicle_weapon_authoring', ROOT / 'scripts/generate_vehicle_weapon_authoring.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class VehicleWeaponTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/VehicleWeaponCapabilities.json').read_text())
        cls.by_key = {m['weapon']['key']: m['weapon'] for v in cls.catalog['vehicles']
            for m in v['mounts'] if m['weapon']}
        cls.fields = {(x['weapon'], x['semanticFieldId']): x for x in cls.catalog['fieldInstances']}

    def test_generated_outputs_are_fresh(self):
        self.assertFalse(generator.generate(check=True))

    def test_mount_coverage_and_scopes(self):
        summary = self.catalog['summary']
        # 11 vehicles plus the five Guard Dog drones (carrier: their backpack).
        self.assertEqual((summary['vehicles'], summary['weaponMounts']), (16, 23))
        self.assertEqual(summary['fieldInstances'], len(self.catalog['fieldInstances']))
        self.assertEqual(summary['gameplayProvenFields'], 27)
        self.assertNotRegex(json.dumps(self.catalog).lower(), re.compile(r'0x[0-9a-f]{8,}'))
        # Maelstrom: main gun, missile pod and the twin launchers stay separate weapons.
        self.assertIn('TD-110 Maelstrom / attach_tank_gun', self.by_key)
        self.assertIn('TD-110 Maelstrom / slot_2', self.by_key)
        self.assertEqual(self.by_key['TD-110 Maelstrom / slot_3']['ownership']['alsoMountedAt'],
            ['TD-110 Maelstrom / slot_4'])
        # Two FRV variants share one mounted gun entity: its own records need allow_shared.
        gun = self.fields[('M-102 Gunner FRV / gun', 'weapon.capacity')]
        self.assertEqual(gun['scope'], 'shared_mounted_weapon')
        self.assertTrue(gun['allowSharedRequired'])
        # Exosuit arms are independent weapons with their own magazine records.
        for arm in ('left_gun', 'right_gun'):
            field = self.fields[('EXO-49 Emancipator Exosuit / ' + arm, 'weapon.capacity')]
            self.assertEqual((field['baseline'], field['scope'], field['acknowledgement']), (100, 'weapon_local', None))
            self.assertEqual(field['gameplayEvidence'], 'Emancipator Ammo v1')
        # The Patriot HMG round is shared; its magazine and fire rate are the arm's own.
        self.assertEqual(self.fields[('EXO-45 Patriot Exosuit / right_gun', 'weapon.capacity')]['baseline'], 1350)
        self.assertEqual(self.fields[('EXO-45 Patriot Exosuit / right_gun', 'weapon.fire_rate')]['baseline'], 1200)
        self.assertTrue(self.fields[('EXO-45 Patriot Exosuit / right_gun', 'damage.primary.standard_damage')]
            ['allowSharedRequired'])
        # Addends stay blocked until an in-game test separates damage and armor penetration.
        blocked = [b['field'] for b in self.by_key['M-103 Supply FRV / gun']['blocked']]
        self.assertIn('weapon damage/armor-penetration addends', blocked)
        unproven = self.fields[('TD-220 Bastion MK XVI / attach_tank_gun_mg', 'weapon.capacity')]
        self.assertEqual(unproven['acknowledgement'], 'allow_unverified_effect')

    def test_spread_and_breakthrough_shield(self):
        # 0.31.0 (research/mounted-spread-shield): every projectile mount exposes its WeaponData spread pair (the
        # member the shot reads for every shot and pellet); spray, beam and arc mounts list it as blocked.
        by_field = self.catalog['summary']['byField']
        self.assertEqual((by_field['weapon.horizontal_spread'], by_field['weapon.vertical_spread']), (17, 17))
        flak = self.fields[('EXO-55 Breakthrough Exosuit / right_gun', 'weapon.horizontal_spread')]
        self.assertEqual((flak['baseline'], flak['min'], flak['max'], flak['scope'], flak['acknowledgement']),
            (200, 0, 1000, 'weapon_local', 'allow_unverified_effect'))
        self.assertEqual(flak['apiFieldConstant'], 'hd2.fields.weapon.horizontal_spread')
        self.assertEqual(flak['appliesWhen'], 'entity_spawn')
        frv = self.fields[('M-102 Gunner FRV / gun', 'weapon.vertical_spread')]
        self.assertEqual((frv['baseline'], frv['scope']), (5, 'shared_mounted_weapon'))
        for other in ('EXO-51 Lumberer Exosuit / left_gun', 'AX/LAS-5 Rover / gun', 'AX/ARC-3 K-9 / gun'):
            self.assertNotIn((other, 'weapon.horizontal_spread'), self.fields)
            self.assertIn('weapon.horizontal_spread / weapon.vertical_spread',
                [b['field'] for b in self.by_key[other]['blocked']])
        # The left mount is the shield arm: no weapon, its own health record (arm pool and plate zone).
        mounts = {m['label']: m for v in self.catalog['vehicles'] if v['vehicle'] == 'EXO-55 Breakthrough Exosuit'
            for m in v['mounts']}
        shield = mounts['left_gun']['shield']
        self.assertIsNone(mounts['left_gun']['weapon'])
        self.assertEqual(self.catalog['summary']['shieldMounts'], 1)
        self.assertFalse(shield['shieldComponent'])
        self.assertEqual(shield['values'], {'armHealth': 800, 'armArmor': 3, 'plateHealth': 5000, 'plateArmor': 4})
        key = 'EXO-55 Breakthrough Exosuit / left_gun'
        expected = {'entity.health': (800, 1, None), 'zone.health': (5000, 1, None), 'zone.armor': (4, 0, 10)}
        found = {f: (x['baseline'], x['min'], x['max']) for (w, f), x in self.fields.items() if w == key}
        self.assertEqual(found, expected)
        for field in expected:
            self.assertEqual(self.fields[(key, field)]['acknowledgement'], 'allow_unverified_effect')
            self.assertEqual(self.fields[(key, field)]['backingComponent'], 'HealthComponentData')
        self.assertIn('entity.armor', [b['field'] for b in shield['blocked']])
        self.assertIn('shield.*', [b['field'] for b in shield['blocked']])

    def test_snapshot_overlay_validation(self):
        result = json.loads((ROOT / 'validation/vehicle-weapon-authoring-snapshot.json').read_text())
        self.assertEqual(result['status'], 'VALIDATED')
        # 0.30.2: the sentry and emplacement hosts (stratagemHosts) are validated too: their projectile swaps, each
        # needing the acknowledgement; they have no mount chain.
        hosts = self.catalog['stratagemHostSummary']
        # 0.31.0: the sentry beam host (the A/LAS-98 Laser Sentry: its beam reference and fire mode / pulse fields,
        # stratagemBeamHosts) is validated the same way, its beam swap with a catalogued beam donor.
        beam_hosts = self.catalog['stratagemBeamHosts']
        beam_fields = sum(len(h['fields']) for h in beam_hosts)
        self.assertEqual(result['vehicleFields'], self.catalog['summary']['writableFieldInstances'] + hosts['writable']
            + beam_fields)
        # 0.31.0: the Breakthrough shield arm (shieldMounts) is a mount target too, with its own mount chain.
        mounts = self.catalog['summary']['weaponMounts'] + self.catalog['summary']['shieldMounts']
        self.assertEqual(result['vehicleWeapons'], mounts + hosts['hosts'] + len(beam_hosts))
        for key in ('noOps', 'changedWrites', 'rollbacks', 'conflictRejections'):
            self.assertEqual(result[key], result['vehicleFields'], key)
        self.assertEqual(result['sharedRejections'], self.catalog['summary']['sharedFields'])
        # Only writable fields are rejected without the acknowledgement: the Rover gun's beam reference is listed
        # read-only (its beam source is AMBIGUOUS) and still carries allow_unverified_effect.
        read_only = sum(1 for item in self.catalog['fieldInstances']
            if not item['writable'] and item['acknowledgement'] == 'allow_unverified_effect')
        self.assertEqual(result['acknowledgementRejections'],
            self.catalog['summary']['unverifiedEffectFields'] - read_only + hosts['writable'] + beam_fields)
        self.assertEqual(result['mountChainRejections'], mounts)
        self.assertTrue(result['independentArms'])
        uses = result['stratagemUses']
        self.assertEqual(uses['checked'], 86)  # every writable use count, Resupply included
        self.assertEqual(uses['transitions'], {'finite_to_finite': 5, 'finite_to_unlimited': 4, 'unlimited_to_finite': 81})
        scenarios = result['scenarios']
        self.assertEqual(scenarios['frv_gun_capacity']['before'], '78000000')
        self.assertEqual(scenarios['frv_gun_capacity']['after'], '58020000')
        self.assertEqual(scenarios['exosuit_unlimited_uses']['after'], 'ffffffff')
        self.assertEqual(scenarios['breakthrough_flak_spread']['before'], '00004843')            # 200.0
        self.assertEqual(scenarios['breakthrough_shield_plate_health']['before'], '88130000')    # 5000 (zone 1)
        self.assertEqual(scenarios['breakthrough_shield_plate_health']['after'], 'a8610000')     # 25000
        self.assertEqual(scenarios['unlimited_to_finite_uses']['before'], 'ffffffff')
        for key in ('bastion_cannon_damage', 'bastion_mg_capacity', 'emancipator_left_capacity',
                    'patriot_hmg_fire_rate', 'finite_to_finite_uses', 'breakthrough_flak_spread',
                    'breakthrough_shield_arm_health', 'breakthrough_shield_plate_armor'):
            self.assertIn(key, scenarios)

    def test_lua_api_and_guards(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local function rejects(request,text)
 local ok,why=pcall(patches.validate,request)
 assert(not ok and tostring(why):find(text,1,true),tostring(why))
end
local patriot=hd2.vehicle('EXO-45 Patriot Exosuit')
assert(#patriot:weapons()==2)
local hmg=patriot:weapon('right_gun')
assert(hmg.weapon=='EXO-45 Patriot Exosuit / right_gun')
patches.validate{id='hmg_cap',target=hmg,field=hd2.fields.weapon.capacity,expect=1350,value=2000}
patches.validate{id='hmg_rpm',target=hmg,field=hd2.fields.weapon.fire_rate,expect=1200,value=600}
rejects({id='hmg_dmg',target=hmg:projectile(),field=hd2.fields.damage.player_standard_damage,expect=90,value=500},
 'allow_shared')
patches.validate{id='hmg_dmg',allow_shared=true,target=hmg:projectile(),
 field=hd2.fields.damage.player_standard_damage,expect=90,value=500}
local missiles=patriot:weapon('left_gun')
patches.validate{id='missile',allow_shared=true,target=missiles:projectile(),
 field=hd2.fields.damage.player_standard_damage,expect=1250,value=2000}
patches.validate{id='arm',target=missiles,field=hd2.fields.entity.health,expect=800,value=8000}
-- Unproven fields need the effect acknowledgement.
rejects({id='radius',allow_shared=true,target=missiles:explosion(),field=hd2.fields.explosion.outer_radius,
 expect=2,value=1},'allow_unverified_effect')
local mael=hd2.vehicle('TD-110 Maelstrom')
assert(mael:weapon(0).weapon~=mael:weapon(2).weapon)
local bastion=hd2.vehicle('TD-220 Bastion MK XVI')
rejects({id='mg',target=bastion:weapon('attach_tank_gun_mg'),field=hd2.fields.weapon.capacity,expect=2000,value=3000},
 'allow_unverified_effect')
patches.validate{id='mg',allow_unverified_effect=true,target=bastion:weapon('attach_tank_gun_mg'),
 field=hd2.fields.weapon.capacity,expect=2000,value=3000}
rejects({id='frv',allow_unverified_effect=true,target=hd2.vehicle('M-102 Gunner FRV'):weapon('gun'),
 field=hd2.fields.weapon.capacity,expect=100,value=200},'allow_shared')
patches.validate{id='frv',allow_shared=true,allow_unverified_effect=true,
 target=hd2.vehicle('M-102 Gunner FRV'):weapon('gun'),field=hd2.fields.weapon.capacity,expect=100,value=200}
patches.validate{id='m103',target=hd2.vehicle('M-103 Supply FRV'):mount('gun'):weapon(),
 field=hd2.fields.weapon.capacity,expect=120,value=600}
local lumberer=hd2.vehicle('EXO-51 Lumberer Exosuit')
patches.validate{id='flamer',target=lumberer:weapon('left_gun'),field=hd2.fields.weapon.capacity,expect=500,value=1000}
patches.validate{id='cannon',target=lumberer:weapon('right_gun'),field=hd2.fields.weapon.capacity,expect=25,value=35}
rejects({id='stale',target=lumberer:weapon('right_gun'),field=hd2.fields.weapon.capacity,expect=26,value=35},
 'expect')
-- 0.31.0: mounted spread (projectile mounts) and the Breakthrough shield arm.
local breakthrough=hd2.vehicle('EXO-55 Breakthrough Exosuit')
assert(#breakthrough:weapons()==1,'the shield arm is not a weapon')
local flak=breakthrough:weapon('right_gun')
rejects({id='spread',target=flak,field=hd2.fields.weapon.horizontal_spread,expect=200,value=1000},
 'allow_unverified_effect')
patches.validate{id='spread',allow_unverified_effect=true,target=flak,field=hd2.fields.weapon.horizontal_spread,
 expect=200,value=1000}
patches.validate{id='vspread',allow_unverified_effect=true,target=flak,field=hd2.fields.weapon.vertical_spread,
 expect=200,value=1000}
rejects({id='wide',allow_unverified_effect=true,target=flak,field=hd2.fields.weapon.horizontal_spread,expect=200,
 value=1001},'maximum')
rejects({id='frvspread',allow_unverified_effect=true,target=hd2.vehicle('M-102 Gunner FRV'):weapon('gun'),
 field=hd2.fields.weapon.horizontal_spread,expect=5,value=10},'allow_shared')
assert(not pcall(patches.validate,{id='flamer',allow_unverified_effect=true,target=lumberer:weapon('left_gun'),
 field=hd2.fields.weapon.horizontal_spread,expect=10,value=20}),'spray mount spread must be refused')
local shield=breakthrough:shield()
assert(shield.weapon=='EXO-55 Breakthrough Exosuit / left_gun')
rejects({id='plate',target=shield,field=hd2.fields.zone.health,expect=5000,value=25000},'allow_unverified_effect')
patches.validate{id='plate',allow_unverified_effect=true,target=shield,field=hd2.fields.zone.health,expect=5000,
 value=25000}
patches.validate{id='plate_armor',allow_unverified_effect=true,target=shield,field=hd2.fields.zone.armor,expect=4,
 value=5}
patches.validate{id='arm',allow_unverified_effect=true,target=shield,field=hd2.fields.entity.health,expect=800,
 value=4000}
rejects({id='zero',allow_unverified_effect=true,target=shield,field=hd2.fields.zone.health,expect=5000,value=0},
 'minimum')
rejects({id='armor11',allow_unverified_effect=true,target=shield,field=hd2.fields.zone.armor,expect=4,value=11},
 'maximum')
assert(not pcall(patches.validate,{id='fallback',allow_unverified_effect=true,target=shield,
 field=hd2.fields.entity.armor,expect=3,value=5}),'the default-zone armor must stay read-only')
assert(not pcall(function()return hd2.vehicle('EXO-45 Patriot Exosuit'):shield()end),'Patriot has no shield')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
