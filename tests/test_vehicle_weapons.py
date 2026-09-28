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
        self.assertEqual((summary['vehicles'], summary['weaponMounts']), (11, 18))
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

    def test_snapshot_overlay_validation(self):
        result = json.loads((ROOT / 'validation/vehicle-weapon-authoring-snapshot.json').read_text())
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertEqual(result['vehicleFields'], self.catalog['summary']['writableFieldInstances'])
        for key in ('noOps', 'changedWrites', 'rollbacks', 'conflictRejections'):
            self.assertEqual(result[key], result['vehicleFields'], key)
        self.assertEqual(result['sharedRejections'], self.catalog['summary']['sharedFields'])
        self.assertEqual(result['acknowledgementRejections'], self.catalog['summary']['unverifiedEffectFields'])
        self.assertEqual(result['mountChainRejections'], result['vehicleWeapons'])
        self.assertTrue(result['independentArms'])
        uses = result['stratagemUses']
        self.assertEqual(uses['checked'], 85)
        self.assertEqual(uses['transitions'], {'finite_to_finite': 5, 'finite_to_unlimited': 4, 'unlimited_to_finite': 80})
        scenarios = result['scenarios']
        self.assertEqual(scenarios['frv_gun_capacity']['before'], '78000000')
        self.assertEqual(scenarios['frv_gun_capacity']['after'], '58020000')
        self.assertEqual(scenarios['exosuit_unlimited_uses']['after'], 'ffffffff')
        self.assertEqual(scenarios['unlimited_to_finite_uses']['before'], 'ffffffff')
        for key in ('bastion_cannon_damage', 'bastion_mg_capacity', 'emancipator_left_capacity',
                    'patriot_hmg_fire_rate', 'finite_to_finite_uses'):
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
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
