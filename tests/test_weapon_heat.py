import json
import unittest

from support import ROOT, execute, modules


HEAT = json.loads((ROOT / 'sdk/PlayerWeaponHeatCapabilities.json').read_text())
CAPABILITIES = json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())


class WeaponHeatAuthoringTests(unittest.TestCase):
    def test_snapshot_heat_matrix_and_disagreements(self):
        summary = HEAT['summary']
        self.assertEqual(summary['weapons'], 80)
        self.assertEqual(summary['weaponsWithHeatMechanism'], 7)
        self.assertEqual(summary['weaponsWithHeatsinkMechanism'], 7)
        self.assertEqual(summary['writableFieldInstances'], 30)
        self.assertEqual(summary['weaponsWithWritableHeatFields'], 5)
        self.assertEqual(summary['sharedComponentGroups'], 0)
        self.assertEqual(summary['heatsinkOptionIdentities'], 9)
        self.assertEqual(HEAT['safety'], {
            'writes': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled',
            'snapshotOnly': True})
        by_name = {weapon['weapon']: weapon for weapon in HEAT['weapons']}
        sickle = {field['id']: field for field in by_name['LAS-16 Sickle']['fields']}
        self.assertEqual(sickle['heat.capacity']['value'], 100)
        self.assertAlmostEqual(sickle['heat.heat_per_shot']['value'], 1.14999998, places=6)
        self.assertEqual(sickle['heat.cool_per_second']['value'], 8)
        self.assertEqual(sickle['heatsink.starting']['value'], 2)
        self.assertEqual(sickle['heatsink.spare']['value'], 3)
        dagger = {field['id']: field for field in by_name['LAS-7 Dagger']['fields']}
        self.assertEqual((dagger['heat.capacity']['value'], dagger['heat.capacity']['wikiValue']),
                         (2000, 100))
        self.assertFalse(dagger['heat.capacity']['writable'])
        self.assertEqual((dagger['heatsink.spare']['value'], dagger['heatsink.spare']['wikiValue']),
                         (12, 3))

    def test_public_fields_and_duplicate_identities_fail_closed(self):
        by_name = {weapon['name']: weapon for weapon in CAPABILITIES['weapons']}
        sickle = {field['semanticFieldId']: field for field in by_name['LAS-16 Sickle']['fields']}
        for field_id in ('heat.capacity', 'heat.heat_per_shot', 'heat.cool_per_second',
                         'heatsink.starting', 'heatsink.from_supply', 'heatsink.spare'):
            self.assertTrue(sickle[field_id]['editable'], field_id)
            self.assertEqual(sickle[field_id]['backing']['component'], 'WeaponHeatComponentData')
            self.assertEqual(sickle[field_id]['writeScope'], 'weapon_local')
        self.assertTrue(sickle['heat.cool_per_second_cold']['derivedReadOnly'])
        self.assertFalse(sickle['heat.warmup']['editable'])
        for name in ('LAS-5 Scythe', 'LAS-7 Dagger'):
            self.assertTrue(by_name[name]['ordinaryWritesBlocked'])
            self.assertFalse(any(field['editable'] and
                (field['semanticFieldId'].startswith('heat.') or
                 field['semanticFieldId'].startswith('heatsink.'))
                for field in by_name[name]['fields']))

    def test_guarded_heat_transaction_uses_owned_exact_width_fields(self):
        script = modules() + r'''
local b=require('hd2runtime/core/bytes')
local writes=require('hd2runtime/domains/player_weapon_writes')
local guard=require('hd2runtime/core/guarded_transaction')
local target={resource='player_weapon',path='weapon',weapon='LAS-16 Sickle'}
local spec=writes.validate_transaction{id='sickle-heat',target=target,changes={
 {field='heat.capacity',expect=100,value=140},
 {field='heat.cool_per_second',expect=8,value=12},
 {field='heatsink.spare',expect=3,value=5}}}
assert(#spec.changes==3)
local backing=spec.changes[1].descriptor.backing
local owner={base=0x400000,size=8192,type=0x20000,protect=2}
local record_offset=96;local record_bytes=string.rep('\0',592)
local function splice(value,offset,bytes)
 return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)
end
record_bytes=splice(record_bytes,96,b.encode(100,'f32'))
record_bytes=splice(record_bytes,128,b.encode(8,'f32'))
record_bytes=splice(record_bytes,92,b.encode(3,'u32'))
local memory=string.rep('\0',owner.size);memory=splice(memory,record_offset,record_bytes)
local record={owner=owner,offset=record_offset,bytes=record_bytes,identity={
 componentType=0x4C981CD9,recordIndex=backing.recordIndex,indexRow=backing.indexRow,
 uniqueOwner=true,ownerCount=1}}
local resolved={candidate={},catalog={record=function(_,component)
 assert(component=='WeaponHeatComponentData');return record end}}
local reader={snapshots={{owner=owner,offset=record_offset,bytes=record_bytes}}}
local plan=writes.prepare(resolved,reader,spec)
assert(#plan.changes==3)
for _,change in ipairs(plan.changes)do assert(#change.desired==4)end
local protection,physical_writes=2,0;local runtime={}
function runtime.system_info()return 4096,0x1000000 end
function runtime.query(address)return {base=owner.base,size=owner.size,
 allocation_base=owner.base,state=0x1000,type=owner.type,protect=protection}end
function runtime.read(address,length)local offset=address-owner.base
 return memory:sub(offset+1,offset+length)end
function runtime.protect(address,length,value)local old=protection;protection=value;return old end
function runtime.write(address,value)physical_writes=physical_writes+1
 memory=splice(memory,address-owner.base,value);return true,nil,#value end
local result=guard.apply(runtime,plan)
assert(result.status=='APPLIED'and result.writes==3 and physical_writes==3)
assert(result.protection_restored and result.non_target_bytes_unchanged and protection==2)
assert(b.value(memory,record_offset+96,'f32')==140)
assert(b.value(memory,record_offset+128,'f32')==12)
assert(b.value(memory,record_offset+92,'u32')==5)
return'ok'
'''
        self.assertEqual(execute(script.encode()), b'ok')

    def test_public_constants_and_read_only_rejections(self):
        script = modules() + r'''
local session=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
assert(session.fields.heat.capacity=='heat.capacity')
assert(session.fields.heat.heat_per_shot=='heat.heat_per_shot')
assert(session.fields.heatsink.spare=='heatsink.spare')
local target=session.weapon('LAS-16 Sickle')
local patch=writes.validate_patch{id='heat',target=target,
 field=session.fields.heat.capacity,expect=100,value=125}
assert(patch.changes[1].descriptor.backing.offset==96)
local ok,why=pcall(writes.validate_patch,{id='warmup',target=target,
 field=session.fields.heat.warmup,expect=0.5,value=0})
assert(not ok and tostring(why):find('field is read-only',1,true))
local duplicate_ok=pcall(writes.validate_patch,{id='scythe',target=session.weapon('LAS-5 Scythe'),
 field=session.fields.heat.capacity,expect=100,value=120})
assert(not duplicate_ok)
return'ok'
'''
        self.assertEqual(execute(script.encode()), b'ok')


if __name__ == '__main__':
    unittest.main()
