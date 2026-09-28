import json
import sys
import unittest

from support import ROOT, run
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_attachment_authoring


class MagazineAttachmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/MagazineAttachmentCapabilities.json').read_text())
        cls.research = json.loads((ROOT / 'research/magazine-attachments-F5FEE03DCFDB.json').read_text())
        cls.attachments = {item['name']: item for item in cls.catalog['attachments']}
        cls.weapons = {item['weapon']: item for item in cls.catalog['weapons']}

    def test_generated_outputs_are_fresh_and_sanitized(self):
        self.assertFalse(generate_attachment_authoring.generate(check=True))
        text = json.dumps(self.catalog).lower()
        self.assertNotIn('0x', text)
        for item in self.research['magazineAttachments']:
            self.assertNotIn(item['addPath'][2:].lower(), text)
            self.assertNotIn(item['optionId'][2:].lower(), text)
        self.assertFalse(self.catalog['summary']['selectionWritable'])

    def test_native_delta_table_proof(self):
        table = self.research['deltaTable']
        self.assertTrue(table['live']['dataIdenticalToFile'])
        self.assertTrue(table['live']['uniqueAllocation'])
        self.assertEqual(table['live']['protect'], 2)
        self.assertFalse(table['dataOffsetsShared'])
        self.assertEqual(self.catalog['summary']['magazineAttachments'], 43)
        self.assertEqual(self.catalog['summary']['fieldInstances'], 233)
        self.assertEqual(self.catalog['summary']['fieldInstancesByField'], {
            'attachment.ergonomics_modifier': 24, 'attachment.magazine_capacity': 43,
            'attachment.magazines_from_supply': 43, 'attachment.reload_duration': 37,
            'attachment.spare_magazines': 43, 'attachment.starting_magazines': 43})

    def test_concussive_drum_is_the_native_owner_of_60_rounds(self):
        weapon = self.weapons['AR-23C Liberator Concussive']['magazineSlot']
        drum = self.attachments['Rifle 5,5x50mm. Drum']
        self.assertEqual(weapon['defaultAttachment'], drum['semanticId'])
        self.assertEqual(weapon['defaultConsistency'], 'delta_matches_published_base_differs')
        self.assertTrue(weapon['baseRecordCapacityIsPlaceholder'])
        self.assertEqual(drum['values']['capacity'], 60)
        self.assertEqual(drum['evidence']['tier'], 'native_owner_effect_consistent')
        self.assertIn('AR-23C Liberator Concussive', drum['consumers']['nativeDefaultOf'])
        self.assertFalse(drum['consumers']['scopeComplete'])
        options = {option['name']: option for option in weapon['options']}
        # Reload and ergonomics separate Standard from Standard Fastreload (2.5 s vs 2.0 s).
        short = options['Short Magazine']
        self.assertEqual(short['relationship'], 'catalog_effects_unique')
        self.assertEqual(short['attachment'], self.attachments['Rifle 5,5x50mm. Standard']['semanticId'])
        self.assertEqual(short['candidates'], [short['attachment']])

    def test_effect_consistency_across_weapons(self):
        consistent = [item for item in self.weapons.values()
            if item['magazineSlot']['defaultConsistency'] == 'delta_matches_published_base_differs']
        self.assertEqual(len(consistent), 14)
        for weapon in self.research['weapons']:
            if weapon.get('defaultConsistency') == 'delta_matches_published_base_differs':
                self.assertEqual(weapon['baseRecordCapacity'], 30, weapon['weapon'])
        breaker = self.weapons['SG-225 Breaker']['magazineSlot']
        self.assertEqual(sum(option['attachment'] is not None for option in breaker['options']), 3)

    def test_attachment_capacity_is_not_aliased_to_weapon_capacity(self):
        player = json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())
        for weapon in player['weapons']:
            if weapon['name'] in ('AR-23C Liberator Concussive', 'SG-225 Breaker', 'P-2 Peacemaker'):
                capacity = [field for field in weapon['fields'] if field['semanticFieldId'] == 'weapon.capacity']
                self.assertTrue(capacity and not capacity[0]['editable'])
        for field in self.catalog['fieldInstances']:
            self.assertTrue(field['semanticFieldId'].startswith('attachment.'))
            self.assertTrue(field['allowSharedRequired'])
            self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
            self.assertFalse(field['reviewedScopeComplete'])

    def test_lua_api_guards(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local w=hd2.weapon('AR-23C Liberator Concussive')
local drum=w:magazine_attachment()
assert(drum:describe().name=='Rifle 5,5x50mm. Drum' and #drum:describe().fields==6)
assert(#w:magazine_attachments()==3)
local short=w:magazine_attachment('Short Magazine')
assert(short:describe().name=='Rifle 5,5x50mm. Standard' and short.attachment~=drum.attachment)
assert(not pcall(function()w:magazine_attachment('Missing Magazine')end))
patches.validate{id='drum-reload',target=drum,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.attachment.reload_duration,expect=3.5,value=3}
assert(not pcall(function()patches.validate{id='drum-reload',target=drum,allow_shared=true,
 allow_unverified_effect=true,field=hd2.fields.attachment.reload_duration,expect=3.5,value=0}end))
assert(not pcall(function()patches.validate{id='drum-ergo',target=drum,allow_shared=true,
 allow_unverified_effect=true,field=hd2.fields.attachment.ergonomics_modifier,expect=-15,value=500}end))
local request={id='drum',target=drum,field=hd2.fields.attachment.magazine_capacity,expect=60,value=90}
assert(not pcall(function()patches.validate(request)end))
request.allow_shared=true
assert(not pcall(function()patches.validate(request)end))
request.allow_unverified_effect=true
patches.validate(request)
request.expect=30;assert(not pcall(function()patches.validate(request)end))
request.expect=60;request.value=-1;assert(not pcall(function()patches.validate(request)end))
transactions.validate{id='drum-ammo',target=drum,allow_shared=true,allow_unverified_effect=true,changes={
 {field=hd2.fields.attachment.magazine_capacity,expect=60,value=90},
 {field=hd2.fields.attachment.spare_magazines,expect=6,value=8}}}
assert(hd2.weapon_attachment('Rifle 5,5x50mm. Drum').attachment==drum.attachment)
assert(not pcall(function()hd2.weapon_attachment('0xE8DE5E95B9635C21')end))
return 'ok'
''')

    def test_snapshot_validation_and_recreation(self):
        snapshot = json.loads((ROOT / 'validation/magazine-attachment-snapshot.json').read_text())
        self.assertEqual(snapshot['status'], 'VALIDATED')
        self.assertEqual((snapshot['fieldChecks'], snapshot['alreadyDesired']), (233, 233))
        for key in ('changedWrites', 'rollbacks', 'isolationChecks', 'conflictRejections'):
            self.assertEqual(snapshot[key], 233, key)
        self.assertEqual(snapshot['guardRejections'], 24)
        self.assertEqual(snapshot['unalignedPackedFields'], 70)
        self.assertEqual(snapshot['multiVariant'], {'weapon': 'AR-23 Liberator', 'options': 3,
            'distinctRecords': 3, 'independentEdits': True})
        recreations = json.loads((ROOT / 'validation/reference-mod-recreations.json').read_text())
        drum = recreations['recreations']['ConcussiveDrumMagazine']
        self.assertEqual((drum['status'], drum['physicalWrites']), ('EXACT_MATCH', 1))
        audit = json.loads((ROOT / 'validation/steady-state-audit.json').read_text())
        scenario = next(item for item in audit['scenarios'] if item['mods'] == ['ConcussiveDrumMagazine'])
        self.assertEqual(scenario['watches'][0]['result'], 'APPLIED')
        self.assertEqual(scenario['startup']['adapter']['writes'], 1)
        self.assertEqual(scenario['steady']['adapter']['writes'], 0)
        self.assertTrue(scenario['reinitialize']['detected_and_reapplied'])


if __name__ == '__main__':
    unittest.main()
