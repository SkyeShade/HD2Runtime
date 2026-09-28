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
        cls.boosters = {item['name']: item for item in cls.catalog['boosters']}

    def test_generated_outputs_are_fresh_and_sanitized(self):
        self.assertFalse(generate_booster_authoring.generate(check=True))
        text = json.dumps(self.catalog).lower()
        self.assertNotIn('0x', text)
        for token in ('recordindex', 'dataoffset', 'arrayoffset', 'entityrow', 'hashmapslot'):
            self.assertNotIn(token, text)
        self.assertEqual(self.catalog['contract'], 'hd2runtime.booster.guarded_authoring.v1')
        summary = self.catalog['summary']
        self.assertEqual((summary['boosters'], summary['writableBoosters'], summary['fieldInstances']), (20, 2, 5))
        self.assertEqual(summary['identityStatus'], {'RESOLVED': 7, 'CANDIDATES': 11,
            'EFFECT_CATEGORY': 1, 'ELIMINATION': 1, 'UNRESOLVED': 0})

    def test_identity_never_guesses_shared_length_values(self):
        pods = self.boosters['Armed Resupply Pods']['identity']
        self.assertEqual((pods['status'], pods['nativeName'], pods['enumValue']), ('RESOLVED', 'DefensiveAmmoPod', 15))
        infusion = self.boosters['Experimental Infusion']['identity']
        self.assertEqual((infusion['nativeName'], infusion['enumValue']), ('CombatDrugs', 11))
        for name in ('Firebomb Hellpods', 'Stun Pods', 'Concealed Insertion'):
            identity = self.boosters[name]['identity']
            self.assertEqual(identity['status'], 'CANDIDATES')
            self.assertIsNone(identity['enumValue'])
            self.assertEqual(identity['enumValueCandidates'], [12, 17, 18])
        extinguishers = self.boosters['Integrated Extinguishers']['identity']
        self.assertEqual((extinguishers['status'], extinguishers['enumValue']), ('EFFECT_CATEGORY', 19))
        self.assertEqual(self.boosters['Surplus EAT Allocation']['identity']['status'], 'ELIMINATION')
        for booster in self.catalog['boosters']:
            icon = booster['identity']['uiIcon']
            if icon:
                wiki = re.sub('[^a-z]', '', booster['name'].lower())
                it = iter(wiki)
                self.assertTrue(all(ch in it for ch in icon[len('Booster'):].lower()), booster['name'])
            if not booster['writable']:
                self.assertTrue(booster['blockedFields'], booster['name'])
                self.assertFalse(booster['fieldInstanceKeys'])

    def test_native_links_are_the_only_type_library_references(self):
        entries = self.research['stratagemBoosterEntries']
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0]['booster'], entries[0]['referenceDebugName']), (15, 'CONSUMABLES. RESUPPLY'))
        slots = entries[0]['delta']['attachedEntities']
        self.assertEqual([item['weaponEntity'] for item in slots], [False, False, False, False, True])
        self.assertEqual({gate['booster'] for gate in self.research['susceptibilityGates']}, {19})
        self.assertTrue(self.research['liveEquality']['entityDeltas']['identical'])
        self.assertTrue(all(self.research['liveEquality']['entityTables'].values()))
        self.assertEqual(len(self.research['typeLibraryBoosterReferences']), 2)

    def test_every_field_requires_explicit_acknowledgement(self):
        by_path = {}
        for field in self.catalog['fieldInstances']:
            self.assertIn('allow_unverified_effect', field['acknowledgements'])
            by_path.setdefault((field['booster'], field['target']['path']), {})[field['semanticFieldId']] = field
        status = by_path[('Experimental Infusion', 'status_effect')]
        self.assertEqual({k: v['value']['baseline'] for k, v in status.items()},
            {'status.strength': 1.1, 'status.duration': 10.0, 'status.incoming_damage_scale': 0.9})
        self.assertTrue(all('allow_shared' in v['acknowledgements'] for v in status.values()))
        turret = by_path[('Armed Resupply Pods', 'deployed_entity')]
        self.assertEqual({k: v['value']['baseline'] for k, v in turret.items()},
            {'weapon.fire_rate': 640.0, 'magazine.capacity': 140})
        self.assertTrue(all('allow_shared' not in v['acknowledgements'] for v in turret.values()))
        self.assertEqual(status['status.incoming_damage_scale']['apiFieldConstant'],
            'hd2.fields.status.incoming_damage_scale')

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
local plan=plans.validate{id='turret',operations={
 {id='rate',target=turret,allow_unverified_effect=true,field=hd2.fields.weapon.fire_rate,expect=640,value=900},
 {id='mag',target=turret,allow_unverified_effect=true,field=hd2.fields.magazine.capacity,expect=140,value=300}}}
assert(#plan.operations==2)
local stim=hd2.booster('Experimental Infusion'):status_effect()
ok,why=pcall(writes.validate_patch,{id='shared',target=stim,allow_unverified_effect=true,
 field=hd2.fields.status.strength,expect=1.1,value=1.2})
assert(not ok and tostring(why):find('allow_shared',1,true))
local status=writes.validate_transaction{id='stim',target=stim,allow_shared=true,allow_unverified_effect=true,
 changes={{field=hd2.fields.status.strength,expect=1.1,value=1.2},
  {field=hd2.fields.status.incoming_damage_scale,expect=0.9,value=0.8}}}
assert(status.changes[2].descriptor.backing.kind=='status_multiplier')
ok,why=pcall(function()return hd2.booster('Vitality Enhancement'):status_effect()end)
assert(not ok and tostring(why):find('no reviewed status_effect target',1,true))
ok=pcall(hd2.booster,'Nonexistent Booster')
assert(not ok)
return 'ok'
'''), b'ok')

    def test_snapshot_validation_is_a_guarded_no_op(self):
        result = json.loads((ROOT / 'validation/booster-authoring-snapshot.json').read_text())
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertEqual((result['boosters'], result['targets'], result['fieldChecks'], result['alreadyDesired']),
            (2, 3, 5, 5))
        self.assertEqual((result['writes'], result['protectionChanges']), (0, 0))


if __name__ == '__main__':
    unittest.main()
