import importlib.util
import json
import unittest

from support import ROOT, run


spec = importlib.util.spec_from_file_location(
    'generate_stratagem_authoring', ROOT / 'scripts/generate_stratagem_authoring.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class StratagemAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())

    def test_generated_catalog_is_fresh(self):
        stale, summary = generator.generate(check=True)
        self.assertFalse(stale)
        self.assertEqual(summary, self.catalog['summary'])

    def test_root_and_instance_coverage(self):
        summary = self.catalog['summary']
        self.assertEqual(summary['offensiveRootsResolved'], 20)
        self.assertEqual(summary['orbitalRootsResolved'], 12)
        self.assertEqual(summary['eagleRootsResolved'], 8)
        self.assertEqual(summary['supportRootsResolved'], 33)
        self.assertEqual(summary['cooldownWritable'], 53)
        self.assertEqual(summary['maxUsesWritable'], 0)
        self.assertEqual(summary['eagleUsesPerRearmWritable'], 8)
        self.assertEqual(summary['eagleRearmTimeWritable'], 8)
        instances = self.catalog['fieldInstances']
        self.assertEqual(len(instances), summary['fieldInstances'])
        self.assertEqual(len({x['instanceKey'] for x in instances}), len(instances))
        self.assertEqual(len({x['backingObjectId'] for x in instances}),
            summary['backingObjectCount'])

    def test_public_contract_has_no_native_layout_identity(self):
        text = json.dumps(self.catalog).lower()
        for forbidden in ('recordindex', 'recordtype', 'indexrow', 'resourcehash',
                'nativeidentity', '0xec3575e7a93793bb', '0xfe0db34ac2b9ac61'):
            self.assertNotIn(forbidden, text)
        for field in self.catalog['fieldInstances']:
            self.assertIn('currentDefault', field)
            self.assertIn('backingObjectId', field)
            self.assertIn('operationGroup', field)
            self.assertIn('planGroup', field)
            self.assertIn('sharedConsumers', field)

    def test_eagle_scope_is_exact_and_shared(self):
        rows = [x for x in self.catalog['fieldInstances']
            if x['semanticFieldId'] == 'eagle.rearm_time']
        self.assertEqual(len(rows), 8)
        self.assertEqual(len({x['backingObjectId'] for x in rows}), 1)
        self.assertTrue(all(x['shared'] and x['allowSharedRequired'] for x in rows))
        self.assertTrue(all(len(x['sharedConsumers']) == 8 for x in rows))

    def test_graph_anchors_and_read_only_limits(self):
        by_name = {x['name']: x for x in self.catalog['stratagems']}
        self.assertEqual(by_name['Orbital Laser']['cooldown'], 300)
        self.assertEqual(by_name['Orbital Laser']['maxUses']['value'], 3)
        self.assertFalse(by_name['Orbital Laser']['maxUses']['writable'])
        self.assertEqual(by_name['Orbital Precision Strike']['cooldown'], 80)
        self.assertEqual(by_name['MS-11 Solo Silo']['cooldown'], 180)
        self.assertEqual(by_name['SG-88 Break-Action Shotgun']['rootResolution'], 'UNRESOLVED')
        self.assertEqual(by_name['CQC-72 Entrenchment Tool']['rootResolution'], 'UNRESOLVED')
        kinds = {x['kind'] for x in self.catalog['attacks']}
        self.assertTrue({'ProjectileSettings','DamageInfo','ExplosionSettings',
            'StatusEffectSettings','Beam'} <= kinds)

    def test_lua_api_and_guard_validation(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local plans=require('hd2runtime/domains/composition_plans')
local laser=hd2.stratagem('Orbital Laser')
assert(laser:describe().family=='orbital')
assert(#laser:attacks()>=2)
local damage
for _,attack in ipairs(laser:attacks())do
 local d=attack:describe();if d.kind=='DamageInfo'then damage=attack end
end
assert(damage)
patches.validate{id='laser_damage',target=damage,field=hd2.fields.damage.player_standard_damage,
 expect=60,value=400,allow_shared=true}
local precision=hd2.stratagem('Orbital Precision Strike')
patches.validate{id='precision_cd',target=precision,field=hd2.fields.stratagem.definition_cooldown,
 expect=80,value=40}
local eagle=hd2.stratagem('Eagle Airstrike')
transactions.validate{id='eagle_uses',target=eagle,changes={{
 field=hd2.fields.eagle.uses_per_rearm,expect=2,value=6}}}
assert(not pcall(function()patches.validate{id='max_uses',target=laser,
 field=hd2.fields.stratagem.max_uses,expect=3,value=4}end))
assert(not pcall(function()patches.validate{id='rearm',target=eagle:eagle_rearm(),
 field=hd2.fields.eagle.rearm_time,expect=150,value=30}end))
patches.validate{id='rearm_shared',target=eagle:eagle_rearm(),
 field=hd2.fields.eagle.rearm_time,expect=150,value=30,allow_shared=true}
plans.validate{id='eagle_plan',operations={
 {id='definition',target=eagle,changes={
  {field=hd2.fields.stratagem.definition_cooldown,expect=15,value=5},
  {field=hd2.fields.eagle.uses_per_rearm,expect=2,value=6}}},
 {id='rearm',target=eagle:eagle_rearm(),allow_shared=true,
  field=hd2.fields.eagle.rearm_time,expect=150,value=30},
 {id='payload',target=eagle:attack('delivery_1_projectile_impact'),allow_shared=true,
  field=hd2.fields.explosion.outer_radius,expect=10,value=20}}}
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
