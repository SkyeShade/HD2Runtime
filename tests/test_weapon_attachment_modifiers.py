import json
import re
import sys
import unittest

from support import ROOT, run
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_attachment_authoring


class WeaponAttachmentModifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/WeaponAttachmentModifierCapabilities.json').read_text())
        cls.research = json.loads((ROOT / 'research/weapon-attachments-F5FEE03DCFDB.json').read_text())
        cls.magazines = json.loads((ROOT / 'sdk/MagazineAttachmentCapabilities.json').read_text())
        cls.attachments = {item['name']: item for item in cls.catalog['attachments']}

    def test_generated_outputs_are_fresh_and_sanitized(self):
        self.assertFalse(generate_attachment_authoring.generate(check=True))
        text = json.dumps(self.catalog).lower()
        self.assertIsNone(re.search(r'\b0x[0-9a-f]{6,}', text))
        for item in self.research['items']:
            if item['hasDelta']:
                self.assertNotIn(item['addPath'][2:].lower(), text)
        self.assertFalse(self.catalog['summary']['selectionWritable'])

    def test_native_slots_and_modifier_rows(self):
        slots = {name: int(value) for value, name in self.research['slots'].items()}
        self.assertEqual((slots['Underbarrel'], slots['Optics'], slots['Muzzle'], slots['Magazine']), (1, 2, 4, 5))
        self.assertEqual(self.research['deltaDataRowsOverlapping'], 0)
        for item in self.research['items']:
            for row in item['statModifierRows'] or []:
                self.assertTrue(row['ownRow'] and row['typeOwnRow'], item['debugName'])
                self.assertEqual(self.research['statModifierTypes'][str(row['type'])], row['typeName'])
                self.assertEqual(row['componentOffset'], 956 + 8 * row['index'] + 4)
        summary = self.catalog['summary']
        self.assertEqual(summary['bySlot'], {'muzzle': 37, 'optics': 17, 'underbarrel': 19})
        self.assertEqual(summary['attachmentsWithWritableModifiersBySlot'],
            {'muzzle': 28, 'optics': 6, 'underbarrel': 10})
        self.assertEqual((summary['fieldInstances'], summary['blockedModifiers']), (132, 1))
        self.assertEqual(summary['fieldInstancesByField'], {
            'attachment.ergonomics_modifier': 38, 'attachment.modifier.climb_horizontal': 15,
            'attachment.modifier.climb_vertical': 14, 'attachment.modifier.recoil_horizontal': 16,
            'attachment.modifier.recoil_vertical': 13, 'attachment.modifier.spread_horizontal': 6,
            'attachment.modifier.spread_vertical': 6, 'attachment.modifier.sway': 24})

    def test_fields_are_shared_definitions_with_type_guards(self):
        for field in self.catalog['fieldInstances']:
            self.assertTrue(field['allowSharedRequired'] and field['shared'])
            self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
            self.assertFalse(field['reviewedScopeComplete'])
            self.assertEqual(field['evidence']['gameplayWriteEffect'], 'unproven')
            self.assertEqual(field['target']['path'], field['slot'])
        flash = self.attachments['5,5mm. Flash Hider']
        self.assertEqual(flash['compatibleWeapons'], ['AR-11 Arbitrator', 'AR-23 Liberator',
            'AR-23A Liberator Carbine', 'AR-23P Liberator Penetrator', 'AR-32 Pacifier'])
        self.assertFalse(flash['consumers']['scopeComplete'])
        self.assertEqual({m['modifier']: m['value'] for m in flash['modifiers']}, {'Add_Ergonomics': -3.0,
            'Mul_Sway': 1.1, 'Mul_ClimbVertical': 0.9, 'Mul_RecoilVertical': 0.9, 'Mul_ClimbHorizontal': 0.8,
            'Mul_RecoilHorizontal': 0.8})
        self.assertTrue(all(not patch['writable'] for item in self.catalog['attachments']
            for patch in item['readOnlyPatches']))
        unproven = {(patch['component'], patch['offset']) for item in self.catalog['attachments']
            for patch in item['readOnlyPatches'] if patch['status'] == 'unproven'}
        for member in (('WeaponDataComponentData', 116), ('WeaponDataComponentData', 340),
                ('WeaponDataComponentData', 352), ('WeaponDataComponentData', 316), ('WeaponDataComponentData', 136),
                ('ProjectileWeaponComponentData', 224), ('WeaponCustomizationComponentData', 4852),
                ('WeaponCustomizationComponentData', 4856), ('WeaponDataComponentData', 156),
                ('MeleeAttackComponentData', 0)):
            self.assertIn(member, unproven)
        brake = {m['modifier']: m for m in self.attachments['8mm. Muzzle break']['modifiers']}
        self.assertFalse(brake['Mul_ClimbHorizontal']['writable'])
        self.assertIn('page boundary', brake['Mul_ClimbHorizontal']['blocker'])

    def test_magazine_fields_are_unchanged(self):
        summary = self.magazines['summary']
        self.assertEqual((summary['magazineAttachments'], summary['fieldInstances']), (43, 233))
        self.assertTrue(all(field['target']['path'] == 'magazine' for field in self.magazines['fieldInstances']))
        generic = json.loads((ROOT / 'sdk/WeaponAttachmentCatalog.json').read_text())
        linked = {item['modifierAuthoring'] for item in generic['attachments'] if item['modifierAuthoring']}
        self.assertEqual(linked, {item['semanticId'] for item in self.catalog['attachments']
            if item['fieldInstanceKeys']})

    def test_lua_api_resolves_every_slot_and_guards_writes(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local database=require('hd2runtime/domains/attachment_authoring')
local function fails(fn,needle)
 local ok,why=pcall(fn);assert(not ok,'not refused: '..needle)
 assert(tostring(why):find(needle,1,true),'refused for another reason: '..tostring(why))
end
local w=hd2.weapon('AR-23 Liberator')
-- Every slot resolves; magazine is the unchanged magazine path.
local magazines=w:attachments('magazine')
assert(#magazines==#w:magazine_attachments()and magazines[1].attachment==w:magazine_attachments()[1].attachment)
assert(w:attachment_definition('magazine','Drum Magazine').attachment==w:magazine_attachment('Drum Magazine').attachment)
assert(w:attachment_definition('magazine').path=='magazine')
for _,slot in ipairs({'muzzle','optics','underbarrel'})do
 local list=w:attachments(slot);assert(#list>1,slot)
 for _,handle in ipairs(list)do
  assert(handle.resource=='weapon_attachment'and handle.path==slot and database.attachments[handle.attachment].slot==slot)
 end
 local default=w:attachment_definition(slot)
 assert(default.attachment==list[1].attachment and default:describe().relationship=='native_resource_default')
end
fails(function()w:attachments('paint')end,'unknown attachment slot')
fails(function()w:attachment_definition('muzzle','REFLEX SIGHT')end,'unknown muzzle attachment')
assert(w:attachment_definition('optics'):describe().name=='TUBE REDDOT 2x')
local flash=w:attachment_definition('muzzle','5,5mm. Flash Hider')
local d=flash:describe()
assert(d.slot=='muzzle'and d.shared and not d.scopeComplete and #d.compatibleWeapons==5 and #d.fields==6)
assert(#d.modifiers==6 and #d.readOnlyPatches==3)
for _,patch in ipairs(d.readOnlyPatches)do assert(patch.writable==false and patch.status)end
for _,field in ipairs(d.fields)do assert(field.statModifier and field.acknowledgements[1]=='allow_shared')end
assert(hd2.weapon_attachment('5,5mm. Flash Hider').attachment==flash.attachment)
assert(hd2.weapon_attachment(flash.attachment).path=='muzzle')
assert(hd2.weapon_attachment('Vertical Grip').path=='underbarrel')
assert(hd2.weapon_attachment('TUBE REDDOT 2x').path=='optics')
assert(hd2.weapon_attachment('Rifle 5,5x50mm. Drum').path=='magazine')
fails(function()hd2.weapon_attachment('0x0000000000000000')end,'unknown reviewed weapon attachment')
-- Acknowledgements, range, absent and blocked modifiers, the slot path.
local request={id='flash',target=flash,field=hd2.fields.attachment.modifier_recoil_horizontal,expect=0.8,value=0.5}
fails(function()patches.validate(request)end,'allow_shared')
request.allow_shared=true
fails(function()patches.validate(request)end,'allow_unverified_effect')
request.allow_unverified_effect=true
patches.validate(request)
request.value=11;fails(function()patches.validate(request)end,'maximum')
request.value=-1;fails(function()patches.validate(request)end,'minimum')
request.value=0.5;request.expect=0.6;fails(function()patches.validate(request)end,'expect differs')
request.expect=0.8
fails(function()patches.validate{id='flash',target=flash,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.attachment.modifier_spread_vertical,expect=1,value=0.5}end,'adding a modifier is not supported')
fails(function()patches.validate{id='flash',target=flash,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.attachment.magazine_capacity,expect=1,value=2}end,'not exposed')
fails(function()patches.validate{id='sight',target=hd2.weapon_attachment('REFLEX SIGHT'),allow_shared=true,
 allow_unverified_effect=true,field=hd2.fields.attachment.ergonomics_modifier,expect=0,value=1}end,'no stat modifiers')
fails(function()patches.validate{id='brake',target=hd2.weapon_attachment('8mm. Muzzle break'),allow_shared=true,
 allow_unverified_effect=true,field=hd2.fields.attachment.modifier_climb_horizontal,expect=0.6,value=0.5}end,
 'page boundary')
fails(function()patches.validate{id='flash',target={resource='weapon_attachment',attachment=flash.attachment,
 path='optics'},allow_shared=true,allow_unverified_effect=true,field=hd2.fields.attachment.modifier_recoil_horizontal,
 expect=0.8,value=0.5}end,'is a muzzle attachment, not optics')
fails(function()patches.validate{id='flash',target={resource='weapon_attachment',attachment=flash.attachment,
 path='magazine'},allow_shared=true,allow_unverified_effect=true,field=hd2.fields.attachment.modifier_recoil_horizontal,
 expect=0.8,value=0.5}end,'is a muzzle attachment, not magazine')
local drum=w:magazine_attachment('Drum Magazine')
fails(function()patches.validate{id='drum',target={resource='weapon_attachment',attachment=drum.attachment,
 path='muzzle'},allow_shared=true,allow_unverified_effect=true,field=hd2.fields.attachment.magazine_capacity,
 expect=60,value=70}end,'is a magazine attachment, not muzzle')
transactions.validate{id='flash-all',target=flash,allow_shared=true,allow_unverified_effect=true,changes={
 {field=hd2.fields.attachment.modifier_recoil_horizontal,expect=0.8,value=0.5},
 {field=hd2.fields.attachment.modifier_recoil_vertical,expect=0.9,value=0.6},
 {field=hd2.fields.attachment.ergonomics_modifier,expect=-3,value=0}}}
-- Every stat modifier field is guarded by its own pair's type word, named by the reviewed modifier.
for id,entry in pairs(database.attachments)do
 for field_id,field in pairs(entry.fields)do
  if entry.slot~='magazine'then
   assert(field.guard and field.guard.componentOffset==field.componentOffset-4 and field.storage=='f32',field_id)
   local named
   for _,m in ipairs(entry.modifiers)do if m.field==field_id then named=m.modifier end end
   assert(database.modifierTypes[tostring(field.guard.u32)]==named,id..' '..field_id)
  end
 end
end
return 'ok'
''')

    def test_snapshot_validation(self):
        snapshot = json.loads((ROOT / 'validation/weapon-attachment-modifier-snapshot.json').read_text())
        self.assertEqual(snapshot['status'], 'VALIDATED')
        self.assertEqual((snapshot['fieldChecks'], snapshot['alreadyDesired']), (132, 132))
        for key in ('changedWrites', 'rollbacks', 'isolationChecks', 'conflictRejections', 'guardRejections'):
            self.assertEqual(snapshot[key], 132, key)
        self.assertEqual(snapshot['isolatedLocations'], 233 + 132)
        self.assertEqual((snapshot['acknowledgementRejections'], snapshot['rangeRejections'],
            snapshot['slotRejections']), (264, 264, 264))
        self.assertEqual((snapshot['attachments'], snapshot['attachmentsWithFields']), (73, 44))
        self.assertEqual(snapshot['blockedModifierRejections'], 1)
        self.assertEqual(snapshot['absentModifierRejections'], 73 * 8 - 132 - 1)
        self.assertEqual(snapshot['bySlot'], {'muzzle': 99, 'optics': 6, 'underbarrel': 27})
        self.assertEqual(snapshot['transaction'], {'attachment': '5,5mm. Flash Hider', 'slot': 'muzzle', 'changes': 6,
            'applied': True, 'rolledBack': True})
        magazine = json.loads((ROOT / 'validation/magazine-attachment-snapshot.json').read_text())
        self.assertEqual((magazine['attachments'], magazine['fieldChecks']), (43, 233))


if __name__ == '__main__':
    unittest.main()
