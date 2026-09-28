import json
import re
import sys
import unittest

from support import ROOT, run
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_booster_authoring


class BoosterAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/BoosterAuthoringCapabilities.json').read_text())
        cls.research = json.loads((ROOT / 'research/booster-authoring-F5FEE03DCFDB.json').read_text())
        cls.native = json.loads((ROOT / 'research/booster-native-F5FEE03DCFDB.json').read_text())
        cls.boosters = {item['name']: item for item in cls.catalog['boosters']}

    def test_generated_outputs_are_fresh_and_sanitized(self):
        self.assertFalse(generate_booster_authoring.generate(check=True))
        text = json.dumps(self.catalog).lower()
        self.assertNotIn('0x', text)
        for token in ('recordindex', 'dataoffset', 'arrayoffset', 'entityrow', 'hashmapslot', 'rva', 'tablerva'):
            self.assertNotIn(token, text)
        self.assertEqual(self.catalog['contract'], 'hd2runtime.booster.guarded_authoring.v2')
        summary = self.catalog['summary']
        self.assertEqual((summary['boosters'], summary['writableBoosters'], summary['fieldInstances']), (20, 19, 42))
        self.assertEqual(summary['identityStatus'], {'RESOLVED': 20, 'CANDIDATES': 0,
            'EFFECT_CATEGORY': 0, 'ELIMINATION': 0, 'UNRESOLVED': 0})
        self.assertEqual(summary['fieldsByTarget'], {'tuning': 13, 'explosion': 21, 'status_effect': 3,
            'status_damage': 2, 'granted_stratagem': 1, 'deployed_entity': 2})
        self.assertEqual((summary['boosterTableStores'], summary['codeWrites']), (0, 0))

    def test_identity_comes_from_the_native_name_table(self):
        names = self.native['boosterNames']['names']
        self.assertEqual((names[0], names[-1], len(names)), ('None', 'Count', 22))
        lengths = self.native['boosterNames']['typeLibraryAliasLengths']
        self.assertTrue(all(len('Booster_' + name) == lengths[str(value)] for value, name in enumerate(names)))
        expected = {'Vitality Enhancement': 1, 'UAV Recon Booster': 4, 'Stamina Enhancement': 2,
            'Localization Confusion': 8, 'Expert Extraction Pilot': 9, 'Motivational Shocks': 10,
            'Firebomb Hellpods': 12, 'Sample Scanner': 13, 'Sample Extricator': 16, 'Stun Pods': 17,
            'Concealed Insertion': 18, 'Integrated Extinguishers': 19, 'Surplus EAT Allocation': 20,
            'Armed Resupply Pods': 15, 'Experimental Infusion': 11}
        for name, value in expected.items():
            identity = self.boosters[name]['identity']
            self.assertEqual((identity['status'], identity['enumValue']), ('RESOLVED', value), name)
            self.assertEqual(identity['nativeName'], names[value])
            if identity['aliasLengthCandidates']:
                self.assertIn(value, identity['aliasLengthCandidates'])
        for booster in self.catalog['boosters']:
            icon = booster['identity']['uiIcon']
            if icon:
                wiki = re.sub('[^a-z]', '', booster['name'].lower())
                it = iter(wiki)
                self.assertTrue(all(ch in it for ch in icon[len('Booster'):].lower()), booster['name'])
            if not booster['writable']:
                self.assertTrue(booster['blockedFields'], booster['name'])
                self.assertFalse(booster['fieldInstanceKeys'])
        self.assertEqual([b['name'] for b in self.catalog['boosters'] if not b['writable']],
            ['Hellpod Space Optimization'])

    def test_native_booster_system(self):
        table = self.native['boosterTable']
        self.assertEqual((len(table['rows']), table['stride'], table['directStores']), (21, 0x38, 0))
        self.assertFalse([r for r in table['references'] if r['kind'] == 'store'])
        calls = self.native['isBoosterActive']['calls']
        self.assertEqual(len(calls), 38)
        literal = {c['booster'] for c in calls if c['booster'] is not None}
        self.assertEqual(literal, set(range(1, 20)) - {15})
        for name, entry in self.native['tuning'].items():
            self.assertTrue(entry['gates'] and entry['readers'], name)
            for reader in entry['readers']:
                self.assertIn('rip', reader['asm'])
        self.assertEqual(self.native['grant']['granted'], [{'booster': 'FreeEAT', 'value': 20, 'stratagemType': 15,
            'stratagemTypeName': 'LATOneshot_Booster'}])
        self.assertEqual(self.native['grantedStratagemRecord']['use_count'], 2)
        self.assertEqual({k: v['nativeType'] for k, v in self.native['selectors'].items()},
            {'FieryDrop': 83, 'ShockPods': 335, 'SmokePods': 400, 'CombatDrugs': 29, 'DeathMarch': 59})
        self.assertEqual(self.native['dataCarriers']['hits'], {'explosion': [], 'status': []})
        self.assertEqual(self.native['literalSelectorSites']['DeathMarch']['literalCallSites'],
            [0xA6CD69, 0xA8B5B4, 0xA8B5D3, 0xA8B5E8])
        # The type library still references the Booster enum from only two data places.
        self.assertEqual(len(self.research['typeLibraryBoosterReferences']), 2)
        self.assertEqual({gate['booster'] for gate in self.research['susceptibilityGates']}, {19})

    def test_fields_and_acknowledgements(self):
        by_path = {}
        for field in self.catalog['fieldInstances']:
            self.assertIn('allow_unverified_effect', field['acknowledgements'])
            by_path.setdefault((field['booster'], field['target']['path']), {})[field['semanticFieldId']] = field
        tuning = {booster: next(iter(fields.values()))['value']['baseline'] for (booster, path), fields
            in by_path.items() if path == 'tuning'}
        self.assertEqual(tuning, {'Vitality Enhancement': 0.9, 'Stamina Enhancement': 1.3, 'Muscle Enhancement': 0.35,
            'UAV Recon Booster': 1.5, 'Increased Reinforcement Budget': 1.0, 'Flexible Reinforcement Budget': 0.75,
            'Localization Confusion': 0.9, 'Expert Extraction Pilot': 0.7, 'Motivational Shocks': 0.5,
            'Sample Scanner': 0.15, 'Dead Sprint': 0.05, 'Sample Extricator': 10.0, 'Integrated Extinguishers': 0.5})
        for (booster, path), fields in by_path.items():
            for field in fields.values():
                self.assertEqual('allow_shared' in field['acknowledgements'],
                    path in ('explosion', 'status_effect', 'status_damage'), (booster, path))
                if path == 'tuning':
                    self.assertIn('range', field)
        burn = by_path[('Integrated Extinguishers', 'tuning')]['booster.burn_decay_bonus']
        self.assertLess(burn['range']['max'], 1)
        firebomb = by_path[('Firebomb Hellpods', 'explosion')]
        self.assertEqual({k: v['value']['baseline'] for k, v in firebomb.items()}, {
            'explosion.inner_radius': 2.0, 'explosion.outer_radius': 4.0, 'explosion.shockwave_radius': 4.0,
            'explosion.damage.standard_damage': 200, 'explosion.damage.durable_damage': 200,
            'explosion.damage.ap_direct': 10, 'explosion.damage.demolition': 40, 'explosion.damage.stagger': 15,
            'explosion.damage.push_force': 20, 'status.strength': 20.0})
        self.assertNotIn('explosion.damage.push_force', by_path[('Stun Pods', 'explosion')])
        self.assertEqual(by_path[('Surplus EAT Allocation', 'granted_stratagem')]['stratagem.max_uses']
            ['value']['baseline'], 2)
        self.assertEqual({k: v['value']['baseline'] for k, v in by_path[('Dead Sprint', 'status_damage')].items()},
            {'damage.standard_damage': 5, 'damage.durable_damage': 5})
        status = by_path[('Experimental Infusion', 'status_effect')]
        self.assertEqual({k: v['value']['baseline'] for k, v in status.items()},
            {'status.strength': 1.1, 'status.duration': 10.0, 'status.incoming_damage_scale': 0.9})
        self.assertEqual(status['status.strength']['evidence']['tier'], 'structural_code_selector_exact_fingerprint')
        turret = by_path[('Armed Resupply Pods', 'deployed_entity')]
        self.assertEqual({k: v['value']['baseline'] for k, v in turret.items()},
            {'weapon.fire_rate': 640.0, 'magazine.capacity': 140})

    def test_public_api_guards(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/booster_writes')
local plans=require('hd2runtime/domains/composition_plans')
local pods=hd2.booster('Armed Resupply Pods')
assert(pods:describe().enumValue==15 and pods:describe().targets[1]=='deployed_entity')
local turret=pods:deployed_entity()
local ok,why=pcall(writes.validate_patch,{id='root',target=pods,field=hd2.fields.weapon.fire_rate,
 expect=640,value=900,allow_unverified_effect=true})
assert(not ok and tostring(why):find('booster root has no fields',1,true))
ok,why=pcall(writes.validate_patch,{id='ack',target=turret,field=hd2.fields.weapon.fire_rate,expect=640,value=900})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true))
local spec=writes.validate_patch{id='rate',target=turret,allow_unverified_effect=true,
 field=hd2.fields.weapon.fire_rate,expect=640,value=900}
assert(spec.kind=='booster'and spec.changes[1].descriptor.backing.component=='ProjectileWeaponComponentData')
ok,why=pcall(writes.validate_patch,{id='expect',target=turret,allow_unverified_effect=true,
 field=hd2.fields.weapon.fire_rate,expect=600,value=900})
assert(not ok and tostring(why):find('expect differs',1,true))
ok,why=pcall(writes.validate_transaction,{id='span',target=turret,allow_unverified_effect=true,changes={
 {field=hd2.fields.weapon.fire_rate,expect=640,value=900},{field=hd2.fields.magazine.capacity,expect=140,value=300}}})
assert(not ok and tostring(why):find('use hd2.plan',1,true))
local stim=hd2.booster('Experimental Infusion'):status_effect()
ok,why=pcall(writes.validate_patch,{id='shared',target=stim,allow_unverified_effect=true,
 field=hd2.fields.status.strength,expect=1.1,value=1.2})
assert(not ok and tostring(why):find('allow_shared',1,true))
-- Native table scalars: booster-local, range-checked.
local vitality=hd2.booster('Vitality Enhancement')
assert(vitality:describe().nativeName=='Vitality'and vitality:describe().enumValue==1)
local v=writes.validate_patch{id='vit',target=vitality:tuning(),allow_unverified_effect=true,
 field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=0.5}
assert(v.changes[1].descriptor.backing.kind=='booster_table'and v.changes[1].descriptor.backing.row==1)
ok,why=pcall(writes.validate_patch,{id='range',target=hd2.booster('Integrated Extinguishers'):tuning(),
 allow_unverified_effect=true,field=hd2.fields.booster.burn_decay_bonus,expect=0.5,value=1})
assert(not ok and tostring(why):find('reviewed range',1,true))
ok,why=pcall(writes.validate_patch,{id='int',target=hd2.booster('Increased Reinforcement Budget'):tuning(),
 allow_unverified_effect=true,field=hd2.fields.booster.reinforcements_per_player,expect=1,value=1.5})
assert(not ok and tostring(why):find('integer',1,true))
ok,why=pcall(writes.validate_patch,{id='wrong',target=vitality:tuning(),allow_unverified_effect=true,
 field=hd2.fields.booster.stamina_scale,expect=1.3,value=1.5})
assert(not ok and tostring(why):find('not exposed',1,true))
-- Explosion rows: shared, and explosion vs damage are separate backing objects.
local firebomb=hd2.booster('Firebomb Hellpods'):explosion()
ok,why=pcall(writes.validate_patch,{id='fb',target=firebomb,allow_unverified_effect=true,
 field=hd2.fields.explosion.inner_radius,expect=2,value=3})
assert(not ok and tostring(why):find('allow_shared',1,true))
ok,why=pcall(writes.validate_transaction,{id='fb2',target=firebomb,allow_shared=true,allow_unverified_effect=true,
 changes={{field=hd2.fields.explosion.inner_radius,expect=2,value=3},
  {field=hd2.fields.explosion.damage_standard_damage,expect=200,value=300}}})
assert(not ok and tostring(why):find('use hd2.plan',1,true))
local plan=plans.validate{id='mixed',operations={
 {id='vit',target=vitality:tuning(),allow_unverified_effect=true,field=hd2.fields.booster.damage_taken_scale,
  expect=0.9,value=0.8},
 {id='eat',target=hd2.booster('Surplus EAT Allocation'):granted_stratagem(),allow_unverified_effect=true,
  field=hd2.fields.stratagem.max_uses,expect=2,value=3},
 {id='fb',target=firebomb,allow_shared=true,allow_unverified_effect=true,
  field=hd2.fields.explosion.outer_radius,expect=4,value=5}}}
assert(#plan.operations==3)
ok,why=pcall(function()return hd2.booster('Hellpod Space Optimization'):tuning()end)
assert(not ok and tostring(why):find('no reviewed tuning target',1,true))
ok=pcall(hd2.booster,'Nonexistent Booster')
assert(not ok)
return 'ok'
'''), b'ok')

    def test_snapshot_validation_exercises_every_field(self):
        result = json.loads((ROOT / 'validation/booster-authoring-snapshot.json').read_text())
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertEqual((result['boosters'], result['targets'], result['fieldChecks'], result['alreadyDesired']),
            (19, 20, 42, 42))
        self.assertEqual((result['changedWrites'], result['rollbacks'], result['conflictRejections']), (42, 42, 42))
        self.assertEqual(result['dataSectionProtectionChanges'], 0)
        self.assertEqual(set(result['proofRejections']), {'instructionByte', 'enumName', 'tableRowIdentity',
            'gateFunction', 'relocatedModule', 'wrongBuild'})
        self.assertEqual(result['proofRejections']['wrongBuild'], 20)
        self.assertEqual(result['rangeRejections'], 37)


if __name__ == '__main__':
    unittest.main()
