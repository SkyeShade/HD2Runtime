"""Throwable authoring: native identity, public catalog, API guards and snapshot validation."""
import json
import re
import sys
import unittest

from support import ROOT, run
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_throwable_authoring

NAMES = ('G-12 High Explosive', 'G-6 Frag', 'G-10 Incendiary', 'TED-63 Dynamite', 'G-7 Pineapple', 'G-16 Impact',
    'G-3 Smoke', 'G-23 Stun', 'G-123 Thermite', 'G-13 Incendiary Impact', 'K-2 Throwing Knife', 'G-4 Gas',
    'G-50 Seeker', 'G-142 Pyrotech', 'G-109 Urchin', 'G-31 Arc', 'TM-1 Lure Mine', 'G-89 Smokescreen',
    'G/SH-39 Shield', 'G-48 Giga Grenade', 'G/40-K Melta Mine', 'G-8 Immolation', 'G-60 Anti-Tank Seeker')


class ThrowableAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/ThrowableAuthoringCapabilities.json').read_text())
        cls.research = json.loads((ROOT / 'research/throwable-authoring-F5FEE03DCFDB.json').read_text())
        cls.throwables = {item['name']: item for item in cls.catalog['throwables']}
        cls.targets = {(item['name'], t['path'], t['key']): {f['semanticFieldId']: f for f in t['fields']}
            for item in cls.catalog['throwables'] for t in item['targets']}

    def test_generated_outputs_are_fresh_and_sanitized(self):
        self.assertFalse(generate_throwable_authoring.generate(check=True))
        text = json.dumps(self.catalog).lower()
        self.assertNotIn('0x', text)
        for token in ('recordindex', 'indexrow', 'recordtype', 'entityrow', '"row"', 'offset', 'resource"'):
            self.assertNotIn(token, text)
        self.assertEqual(self.catalog['contract'], 'hd2runtime.throwable.guarded_authoring.v1')
        summary = self.catalog['summary']
        self.assertEqual((summary['throwables'], summary['resolved'], summary['writableThrowables']), (23, 23, 23))
        self.assertEqual((summary['fieldInstances'], summary['writableFieldInstances']), (411, 388))

    def test_every_wiki_throwable_resolves_to_one_native_entity(self):
        self.assertEqual(tuple(item['name'] for item in self.research['catalog']), NAMES)
        claimed = set()
        for entry in self.research['catalog']:
            identity = entry['identity']
            self.assertEqual(identity['status'], 'RESOLVED', entry['name'])
            self.assertGreaterEqual(len(identity['matchedFacts']), 7, entry['name'])
            self.assertNotIn(identity['resource'], claimed)
            claimed.add(identity['resource'])
            native = entry['native']
            self.assertTrue(native['armory'] and native['loadout'], entry['name'])
            # Inventory counts are exact wiki fingerprints for every throwable.
            facts = {m['fact'] for m in identity['matchedFacts']}
            self.assertTrue({'counts.starting', 'counts.maximum', 'counts.fromSupply'} <= facts, entry['name'])
        paths = {e['name']: e['native']['path'].rsplit('/', 1)[1] for e in self.research['catalog']}
        self.assertEqual(paths['G-12 High Explosive'], 'he_grenade')
        self.assertEqual(paths['G-7 Pineapple'], 'cluster_frag_grenade')
        self.assertEqual(paths['G-123 Thermite'], 'sticky_grenade')
        self.assertEqual(paths['G-109 Urchin'], 'sticky_stun_grenade')
        self.assertEqual(paths['G/SH-39 Shield'], 'energy_shield_grenade')
        self.assertEqual(paths['G/40-K Melta Mine'], 'mine_shark')
        # The thermite's AI-thrown twin (same values, BehaviorComponent, no armory entry) is excluded.
        thermite = next(e for e in self.research['catalog'] if e['name'] == 'G-123 Thermite')
        self.assertEqual(thermite['identity']['otherPerfectCandidatesOutsideArmory'], ['unnamed AI variant'])

    def test_native_values_and_ownership(self):
        frag = self.targets[('G-6 Frag', 'explosion', None)]
        self.assertEqual(frag['explosion.shrapnel_count']['baseline'], 35)
        self.assertEqual(frag['explosion.damage.standard_damage']['baseline'], 500)
        self.assertTrue(frag['explosion.shrapnel_count']['scope']['shared'])
        inventory = self.targets[('G-6 Frag', 'throwable', None)]
        self.assertEqual({k: v['baseline'] for k, v in inventory.items()}, {'throwable.starting_count': 4,
            'throwable.max_count': 6, 'throwable.count_from_supply': 4})
        self.assertFalse(inventory['throwable.max_count']['scope']['shared'])
        knife = self.targets[('K-2 Throwing Knife', 'damage', None)]
        self.assertEqual((knife['damage.standard_damage']['baseline'], knife['damage.durable_damage']['baseline'],
            knife['damage.stagger']['baseline'], knife['damage.push_force']['baseline']), (300, 150, 35, 5))
        self.assertNotIn(('K-2 Throwing Knife', 'explosion', None), self.targets)
        shield = self.targets[('G/SH-39 Shield', 'shield', None)]
        self.assertEqual((shield['shield.radius']['baseline'], shield['shield.durability']['baseline']), (1.8, 1000.0))
        lure = self.targets[('TM-1 Lure Mine', 'entity', None)]
        self.assertEqual(lure['entity.health']['baseline'], 300)
        bomblet = self.targets[('G-7 Pineapple', 'bomblet_explosion', None)]
        self.assertEqual(bomblet['explosion.damage.standard_damage']['baseline'], 100)
        pineapple = next(t for t in self.throwables['G-7 Pineapple']['targets'] if t['path'] == 'bomblets')
        self.assertTrue(pineapple['sharedDamageWithParentExplosion'])
        shrapnel = next(t for t in self.throwables['G-6 Frag']['targets'] if t['path'] == 'shrapnel')
        self.assertEqual(sorted(shrapnel['scope']['projectile']['throwables']),
            ['G-6 Frag', 'G/SH-39 Shield', 'TM-1 Lure Mine'])
        self.assertGreater(shrapnel['scope']['projectile']['otherEntities'], 0)

    def test_status_effects_split_local_and_shared(self):
        fire = self.targets[('G-10 Incendiary', 'status_effect', 'fire')]
        self.assertEqual(fire['status.strength']['baseline'], 50.0)
        self.assertIn('applied per hit', fire['status.strength']['scope']['note'])
        self.assertIn('Shared status definition', fire['status.duration']['scope']['note'])
        stun = self.targets[('G-23 Stun', 'status_effect', 'stun-large')]
        self.assertEqual(stun['status.strength']['baseline'], 25.0)
        gas = [t for t in self.throwables['G-4 Gas']['targets'] if t['path'] == 'status_effect']
        self.assertEqual([t['key'] for t in gas], ['gas', 'gas-confusion'])
        self.assertTrue(all('unconfirmed' in t['labelConfidence'] for t in gas))

    def test_fuse_is_never_flattened_or_invented(self):
        dynamite = self.throwables['TED-63 Dynamite']['detonation']
        self.assertEqual([s['seconds'] for s in dynamite['fuseSettings']], [5, 15, 60])
        self.assertEqual([s['status'] for s in dynamite['fuseSettings']], ['native_default', 'unresolved', 'unresolved'])
        fuse = self.targets[('TED-63 Dynamite', 'detonation', None)]['throwable.explosion_delay']
        self.assertFalse(fuse['editable'])
        self.assertTrue(self.targets[('G-12 High Explosive', 'detonation', None)]['throwable.explosion_delay']['editable'])
        shield = self.targets[('G/SH-39 Shield', 'detonation', None)]['throwable.explosion_delay']
        self.assertEqual((shield['baseline'], shield['editable']), (20.0, False))
        impact = self.targets[('G-16 Impact', 'detonation', None)]['throwable.explosion_delay']
        self.assertFalse(impact['editable'])
        for item in self.catalog['throwables']:
            for target in item['targets']:
                for field in target['fields']:
                    self.assertNotIn('throw_distance', field['semanticFieldId'])
                    if field['editable']:
                        self.assertIn('allow_unverified_effect', field['acknowledgements'])
                        self.assertEqual('allow_shared' in field['acknowledgements'], field['scope']['shared'])

    def test_public_api_guards(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/throwable_writes')
local plans=require('hd2runtime/domains/composition_plans')
local frag=hd2.throwable('G-6 Frag')
assert(frag:describe().identityStatus=='RESOLVED')
local spec=writes.validate_patch{id='count',target=frag,allow_unverified_effect=true,
 field=hd2.fields.throwable.starting_count,expect=4,value=6}
assert(spec.kind=='throwable'and spec.changes[1].descriptor.backing.component=='ThrowableComponentData')
local ok,why=pcall(writes.validate_patch,{id='ack',target=frag,field=hd2.fields.throwable.starting_count,expect=4,value=6})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true))
ok,why=pcall(writes.validate_patch,{id='stale',target=frag,allow_unverified_effect=true,
 field=hd2.fields.throwable.starting_count,expect=5,value=6})
assert(not ok and tostring(why):find('expect differs',1,true))
ok,why=pcall(writes.validate_patch,{id='range',target=frag,allow_unverified_effect=true,
 field=hd2.fields.throwable.max_count,expect=6,value=500})
assert(not ok and tostring(why):find('reviewed range',1,true))
ok,why=pcall(writes.validate_patch,{id='int',target=frag,allow_unverified_effect=true,
 field=hd2.fields.throwable.max_count,expect=6,value=6.5})
assert(not ok and tostring(why):find('integer',1,true))
-- Settings rows are shared definitions.
ok,why=pcall(writes.validate_patch,{id='shared',target=frag:explosion(),allow_unverified_effect=true,
 field=hd2.fields.explosion.shrapnel_count,expect=35,value=45})
assert(not ok and tostring(why):find('allow_shared',1,true))
-- Explosion row and its DamageInfo are separate backing objects.
ok,why=pcall(writes.validate_transaction,{id='span',target=frag:explosion(),allow_shared=true,
 allow_unverified_effect=true,changes={{field=hd2.fields.explosion.inner_radius,expect=4,value=5},
 {field=hd2.fields.explosion.damage_standard_damage,expect=500,value=600}}})
assert(not ok and tostring(why):find('use hd2.plan',1,true))
-- Accessors follow real native relationships only.
assert(frag:shrapnel():describe().path=='shrapnel')
assert(frag:explosion():shrapnel():describe().fields[1])
ok,why=pcall(function()return hd2.throwable('G-12 High Explosive'):shrapnel()end)
assert(not ok and tostring(why):find('no reviewed shrapnel target',1,true))
ok=pcall(function()return hd2.throwable('K-2 Throwing Knife'):explosion()end)
assert(not ok)
local bomb=hd2.throwable('G-7 Pineapple'):bomblets():explosion()
assert(bomb:describe().path=='bomblet_explosion')
local fire=hd2.throwable('G-10 Incendiary'):explosion():status_effect('fire')
assert(fire.status=='fire'and hd2.throwable('G-10 Incendiary'):status_effect(1).status=='fire')
ok=pcall(function()return hd2.throwable('G-12 High Explosive'):status_effect('fire')end)
assert(not ok)
-- Read-only: the multi-setting dynamite fuse.
ok,why=pcall(writes.validate_patch,{id='fuse',target=hd2.throwable('TED-63 Dynamite'):detonation(),
 allow_unverified_effect=true,field=hd2.fields.throwable.explosion_delay,expect=5,value=8})
assert(not ok and tostring(why):find('read-only',1,true))
-- Target identity is closed: no caller-supplied native identity.
ok,why=pcall(writes.validate_patch,{id='forged',target={resource='throwable',throwable='G-6 Frag',path='throwable',
 record=3},allow_unverified_effect=true,field=hd2.fields.throwable.starting_count,expect=4,value=6})
assert(not ok and tostring(why):find('unsupported throwable target identity',1,true))
local plan=plans.validate{id='mixed',operations={
 {id='count',target=frag,allow_unverified_effect=true,field=hd2.fields.throwable.starting_count,expect=4,value=6},
 {id='knife',target=hd2.throwable('K-2 Throwing Knife'):damage(),allow_shared=true,allow_unverified_effect=true,
  field=hd2.fields.damage.player_standard_damage,expect=300,value=450},
 {id='shield',target=hd2.throwable('G/SH-39 Shield'):shield(),allow_unverified_effect=true,
  field=hd2.fields.shield.entity_durability,expect=1000,value=2000}}}
assert(#plan.operations==3)
ok=pcall(hd2.throwable,'Nonexistent Grenade')
assert(not ok)
return 'ok'
'''), b'ok')

    def test_snapshot_validation_exercises_every_writable_field(self):
        result = json.loads((ROOT / 'validation/throwable-authoring-snapshot.json').read_text())
        self.assertEqual(result['status'], 'VALIDATED')
        writable = self.catalog['summary']['writableFieldInstances']
        self.assertEqual((result['throwables'], result['fieldChecks'], result['changedWrites'], result['rollbacks'],
            result['conflictRejections'], result['staleExpectRejections']), (23, writable, writable, writable,
            writable, writable))
        self.assertEqual(result['rangeRejections'], 2 * writable)
        self.assertEqual(result['readOnlyRejections'],
            self.catalog['summary']['fieldInstances'] - writable)
        # Every family the task names is exercised.
        self.assertTrue({'throwable', 'detonation', 'explosion', 'status_effect', 'shrapnel', 'bomblets',
            'bomblet_explosion', 'damage', 'entity', 'shield'} <= set(result['targetsByPath']))
        self.assertEqual(set(result['proofRejections']), {'chainLink', 'componentOwnership', 'wrongBuild'})
        self.assertEqual(result['snapshot'], 'F5FEE03DCFDB-20260926T222226Z.hd2snap')

    def test_examples_use_the_typed_api(self):
        for name in ('FragShrapnel', 'IncendiaryFire', 'ThrowingKnifeDamage', 'ShieldGrenadeDurability'):
            body = (ROOT / 'examples/projects' / name / 'src/addon.lua').read_text()
            self.assertIn('hd2.throwable(', body)
            self.assertIsNone(re.search(r'0x[0-9A-Fa-f]{6,}', body))


if __name__ == '__main__':
    unittest.main()
