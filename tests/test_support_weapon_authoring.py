import json
import sys
import unittest

from support import ROOT,run
sys.path.insert(0,str(ROOT/'scripts'))
import generate_support_weapon_authoring


class SupportWeaponAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capabilities=json.loads((ROOT/'sdk/SupportWeaponAuthoringCapabilities.json').read_text())

    def test_generated_capability_is_current_and_sanitized(self):
        self.assertFalse(generate_support_weapon_authoring.generate(check=True))
        self.assertEqual(self.capabilities['contract'],
            'hd2runtime.support_weapon.guarded_authoring.v1')
        self.assertEqual(self.capabilities['summary']['catalogWeapons'],35)
        self.assertEqual(self.capabilities['summary']['uniqueSupportIdentities'],27)
        self.assertEqual(self.capabilities['summary']['writableSupportWeapons'],27)
        self.assertEqual(self.capabilities['summary']['duplicateGroupsBlocked'],8)
        self.assertEqual(self.capabilities['summary']['writableProjectileBranches'],16)
        self.assertEqual(self.capabilities['summary']['writableExplosionBranches'],17)
        required={'identityStatus','family','attackBranches','writableFieldsByDomain',
            'sharedScopes','blockedFields','backpackDependency','linkedStratagem'}
        self.assertEqual(len(self.capabilities['weapons']),35)
        for weapon in self.capabilities['weapons']:
            self.assertTrue(required.issubset(weapon),weapon['name'])
        encoded=json.dumps(self.capabilities)
        for token in ('resourceHash','recordIndex','recordType','settingsType',
                'projectileType','explosionType','offset','0x'):
            self.assertNotIn(token,encoded)
        self.assertEqual(self.capabilities['safety']['writesDuringGeneration'],0)
        self.assertEqual(self.capabilities['safety']['protectionChangesDuringGeneration'],0)
        self.assertEqual(self.capabilities['safety']['fixtureFallback'],'disabled')

    def test_representative_capabilities_and_fail_closed_groups(self):
        by_name={weapon['name']:weapon for weapon in self.capabilities['weapons']}
        self.assertFalse(by_name['MG-43 Machine Gun']['writable'])
        self.assertFalse(by_name['EAT-17 Expendable Anti-Tank']['writable'])
        self.assertFalse(by_name['LAS-98 Laser Cannon']['writable'])
        self.assertEqual(by_name['LAS-98 Laser Cannon']['family'],['Beam','Status'])
        self.assertTrue(any(item['field']=='heat.* / heatsink.*' for item in
            by_name['LAS-98 Laser Cannon']['blockedFields']))
        self.assertIn('charge',by_name['ARC-3 Arc Thrower']['writableFieldsByDomain'])
        self.assertIn('arc',by_name['ARC-3 Arc Thrower']['writableFieldsByDomain'])
        self.assertNotIn('weapon.fire_rate',
            by_name['ARC-3 Arc Thrower']['writableFieldsByDomain'].get('weapon',[]))
        self.assertIn('explosion',by_name['B/MD C4 Pack']['writableFieldsByDomain'])
        self.assertEqual(sum(branch['writable'] for branch in
            by_name['MS-11 Solo Silo']['attackBranches']),2)
        self.assertTrue(by_name['GR-8 Recoilless Rifle']['backpackDependency'])
        self.assertTrue(any(item['field']=='backpack storage' for item in
            by_name['GR-8 Recoilless Rifle']['blockedFields']))

    def test_public_targets_validate_shared_domains_and_duplicates(self):
        run(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local gr8=hd2.support_weapon('GR-8 Recoilless Rifle')
local projectile=gr8:attack('primary'):projectile()
local physics=writes.validate_transaction{id='gr8-physics',target=projectile,
 allow_shared=true,changes={
  {field=hd2.fields.projectile.velocity,expect=250,value=500},
  {field=hd2.fields.projectile.gravity,expect=1,value=.5}}}
assert(physics.kind=='support_weapon'and physics.weapon=='GR-8 Recoilless Rifle')
assert(physics.changes[1].descriptor.backing.linkage=='projectile')
local damage=writes.validate_patch{id='gr8-damage',target=projectile,allow_shared=true,
 field=hd2.fields.damage.ap_direct,expect=6,value=7}
assert(damage.changes[1].descriptor.backing.linkage=='projectile_damage')
local explosion=gr8:attack('primary_impact'):explosion()
local radius=writes.validate_patch{id='gr8-radius',target=explosion,allow_shared=true,
 field=hd2.fields.explosion.outer_radius,expect=3,value=12}
assert(radius.changes[1].descriptor.backing.linkage=='projectile_explosion')
local arc=hd2.support_weapon('ARC-3 Arc Thrower'):attack('primary')
local range=writes.validate_patch{id='arc-range',target=arc,allow_shared=true,
 field=hd2.fields.arc.range,expect=55,value=80}
assert(range.changes[1].descriptor.backing.linkage=='arc')
local charge=writes.validate_patch{id='arc-charge',target=hd2.support_weapon('ARC-3 Arc Thrower'),
 field=hd2.fields.charge.minimum_seconds,expect=.699999988079071,value=.35}
assert(charge.changes[1].descriptor.backing.component=='WeaponChargeComponentData')
local ok,why=pcall(writes.validate_patch,{id='mg43-blocked',
 target=hd2.support_weapon('MG-43 Machine Gun'),field=hd2.fields.weapon.fire_rate,
 expect=760,value=1000})
assert(not ok and tostring(why):find('Duplicate runtime roots',1,true))
ok,why=pcall(writes.validate_patch,{id='arc-sentinel',target=hd2.support_weapon('ARC-3 Arc Thrower'),
 field=hd2.fields.weapon.fire_rate,expect=-1,value=60})
assert(not ok and tostring(why):find('not exposed',1,true))
return'ok'
''')

    def test_plan_separates_support_backing_objects(self):
        run(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local plans=require('hd2runtime/domains/composition_plans')
local gr8=hd2.support_weapon('GR-8 Recoilless Rifle')
local projectile=gr8:attack('primary'):projectile()
local explosion=gr8:attack('primary_impact'):explosion()
assert(projectile.path=='projectile_reference'and explosion.path=='explosion',
 tostring(projectile.path)..'/'..tostring(explosion.path))
assert(hd2.fields.explosion.damage_standard_damage=='explosion.damage.standard_damage',
 tostring(hd2.fields.explosion.damage_standard_damage))
local function check(label,value)assert(value,label)end
local ok,why=pcall(plans.validate,{id='physics-only',operations={{id='physics',target=projectile,allow_shared=true,
 field=hd2.fields.projectile.velocity,expect=250,value=500}}});check('physics '..tostring(why),ok)
ok,why=pcall(plans.validate,{id='direct-only',operations={{id='direct',target=projectile,allow_shared=true,
 field=hd2.fields.damage.player_standard_damage,expect=3200,value=5000}}});check('direct '..tostring(why),ok)
ok,why=pcall(plans.validate,{id='radius-only',operations={{id='radius',target=explosion,allow_shared=true,
 field=hd2.fields.explosion.outer_radius,expect=3,value=12}}});check('radius '..tostring(why),ok)
ok,why=pcall(plans.validate,{id='blast-only',operations={{id='blast',target=explosion,allow_shared=true,
 field=hd2.fields.explosion.damage_standard_damage,expect=150,value=1000}}});check('blast '..tostring(why),ok)
local spec=plans.validate{id='recoilless-proof',operations={
 {id='physics',target=projectile,allow_shared=true,
  field=hd2.fields.projectile.velocity,expect=250,value=500},
 {id='direct-damage',target=projectile,allow_shared=true,
  field=hd2.fields.damage.player_standard_damage,expect=3200,value=5000},
 {id='radius',target=explosion,allow_shared=true,
  field=hd2.fields.explosion.outer_radius,expect=3,value=12},
 {id='blast-damage',target=explosion,allow_shared=true,
  field=hd2.fields.explosion.damage_standard_damage,expect=150,value=1000}}}
assert(spec.kind=='composition_plan'and#spec.operations==4)
assert(spec.operations[1].backing_scope=='settings:projectile')
assert(spec.operations[2].backing_scope=='settings:damage')
assert(spec.operations[3].backing_scope=='settings:explosion')
assert(spec.operations[4].backing_scope=='settings:explosion_damage')
return'ok'
''')


if __name__=='__main__':unittest.main()
