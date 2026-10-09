import json
import sys
import unittest
from collections import Counter

from support import ROOT, run
sys.path.insert(0, str(ROOT / 'scripts'))
import validate_packaged_runtime

FIELD = 'weapon.third_person_reticle'


class WeaponReticleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = json.loads((ROOT / 'research/weapon-reticles-F5FEE03DCFDB.json').read_text())
        cls.player = json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())
        cls.support = json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text())

    def test_native_owner_and_enum_names(self):
        field = self.research['field']
        self.assertEqual((field['recordType'], field['offset'], field['storage'], field['enum'], field['memberName']),
            ('WeaponDataComponent', 400, 'ENUM_UINT32', 'CrosshairWeaponType', 'crosshair_type'))
        names = self.research['enum']['names']
        self.assertEqual(self.research['enum']['values'], 22)
        self.assertEqual((names['3'], names['4'], names['21']), ('CrosshairDamageIndicatorOnly', 'AssaultRifle', 'Count'))
        self.assertIsNone(names['5'])  # no reference name matches its alias length: stays unnamed
        self.assertEqual(self.research['encoding'], {'hidden': 3, 'shownWhenBaselineHidden': 4})

    def test_coverage_is_derived_from_native_values(self):
        states = Counter((row['kind'], row['reticle']) for row in self.research['weapons'])
        self.assertEqual(states[('player', 'shown')], 75)   # 0.30.2: the seven DUPLICATE weapons resolved to their proven roots
        self.assertEqual(states[('player', 'read_only')], 5)
        self.assertEqual(states[('support', 'hidden')], 1)
        self.assertEqual(states[('support', 'shown')], 14)
        self.assertEqual(states[('support', 'absent')], 2)
        amr = next(row for row in self.research['weapons'] if row['weapon'] == 'APW-1 Anti-Materiel Rifle')
        self.assertEqual((amr['crosshairType'], amr['reticle']), (3, 'hidden'))
        for row in self.research['weapons']:
            if row['reticle'] == 'read_only':
                self.assertTrue(row['reason'])

    def test_player_catalog_fields(self):
        fields = [field for weapon in self.player['weapons'] for field in weapon['fields']
            if field['semanticFieldId'] == FIELD]
        self.assertEqual(len(fields), 80)
        writable = [field for field in fields if field['editable']]
        self.assertEqual(len(writable), 75)   # 0.30.2: the seven DUPLICATE weapons resolved to their proven roots
        for field in writable:
            self.assertIs(field['currentDefault'], True)
            self.assertEqual(field['encoding']['off'], 3)
            self.assertEqual(field['encoding']['on'], field['nativeValue'])
            self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
            self.assertEqual((field['backing']['component'], field['backing']['offset']), ('WeaponDataComponentData', 400))

    def test_support_catalog_fields(self):
        instances = [item for item in self.support['fieldInstances'] if item['semanticFieldId'] == FIELD]
        self.assertEqual(len(instances), 14)
        amr = next(item for item in instances if item['supportWeapon'] == 'APW-1 Anti-Materiel Rifle')
        self.assertIs(amr['value']['baseline'], False)
        self.assertEqual(amr['reticle']['encoding'], {'off': 3, 'on': 4})
        self.assertIsNone(amr['operation']['acknowledgement'])
        self.assertTrue(amr['reticle']['evidence']['gameplayProven'])
        blocked = [item for weapon in self.support['weapons'] for item in weapon['blockedFields'] if item['field'] == FIELD]
        # 15 before the EAT-17, LAS-98 and Cremator were delivery-resolved; they add three reticle blocks (their
        # native roots disagree on crosshair_type, or the EAT's Default crosshair selects no mapped style).
        self.assertEqual(len(blocked), 18)

    def test_lua_guards(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local b=require('hd2runtime/core/bytes')
local amr=hd2.support_weapon('APW-1 Anti-Materiel Rifle')
local spec=patches.validate({id='amr',target=amr,field=hd2.fields.weapon.third_person_reticle,expect=false,value=true})
assert(b.u32(spec.changes[1].expected,0)==3 and b.u32(spec.changes[1].desired,0)==4)
assert(not pcall(patches.validate,{id='amr',target=amr,field=hd2.fields.weapon.third_person_reticle,expect=true,value=false}))
assert(not pcall(patches.validate,{id='amr',target=amr,field=hd2.fields.weapon.third_person_reticle,expect=false,value=1}))
local lib=hd2.weapon('AR-23 Liberator')
local request={id='lib',target=lib,field=hd2.fields.weapon.third_person_reticle,expect=true,value=false}
assert(not pcall(patches.validate,request))
request.allow_unverified_effect=true
local off=patches.validate(request)
assert(b.u32(off.changes[1].expected,0)==4 and b.u32(off.changes[1].desired,0)==3)
local gl=hd2.support_weapon('GR-8 Recoilless Rifle')
assert(not pcall(patches.validate,{id='gl',target=gl,field=hd2.fields.weapon.third_person_reticle,expect=true,
 value=false,allow_unverified_effect=true}))
return 'ok'
'''), b'ok')

    def test_validation_and_recreation(self):
        snapshot = json.loads((ROOT / 'validation/reticle-authoring-snapshot.json').read_text())
        self.assertEqual(snapshot['status'], 'VALIDATED')
        for key in ('fieldChecks', 'changedWrites', 'rollbacks', 'conflictRejections'):
            self.assertEqual(snapshot[key], 89, key)   # 0.30.2: the seven weapons resolved to their proven roots
        self.assertEqual((snapshot['acknowledgementRejections'], snapshot['gameplayProven']), (88, 1))
        recreations = json.loads((ROOT / 'validation/reference-mod-recreations.json').read_text())
        amr = recreations['recreations']['ReticleAmrRecreation']
        self.assertEqual((amr['status'], amr['physicalWrites'], amr['referenceWrites']), ('EXACT_MATCH', 1, 1))
        self.assertIn('support-weapon-reticle', validate_packaged_runtime.SCENARIOS)
        self.assertIn('player-weapon-reticle', validate_packaged_runtime.SCENARIOS)
        addon = (ROOT / 'examples/projects/ReticleAmrRecreation/src/addon.lua').read_text()
        self.assertIn('hd2.fields.weapon.third_person_reticle', addon)
        self.assertNotIn('allow_unverified_effect', addon)


if __name__ == '__main__':
    unittest.main()
