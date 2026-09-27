import json
import sys
import unittest

from support import ROOT, execute, modules
sys.path.insert(0,str(ROOT/'scripts'))
import generate_weapon_authoring


CAPABILITIES = json.loads((ROOT/'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())


class PlayerWeaponAuthoringTests(unittest.TestCase):
    def test_generated_capabilities_are_current(self):
        generate_weapon_authoring.generate(check=True)

    def test_matrix_covers_catalog_without_runtime_addresses(self):
        self.assertEqual(CAPABILITIES['summary']['weapons'], 80)
        self.assertEqual(CAPABILITIES['summary']['uniqueWeapons'], 73)
        self.assertEqual(CAPABILITIES['summary']['duplicateWeapons'], 7)
        encoded=json.dumps(CAPABILITIES).lower()
        self.assertNotIn('absoluteaddress', encoded)
        self.assertNotIn('baseaddress', encoded)
        for weapon in CAPABILITIES['weapons']:
            self.assertTrue(weapon['implementationFamilies'])
            for field in weapon['fields']:
                for key in ('displayName','semanticFieldId','type','unit','currentDefault','editable',
                            'derivedReadOnly','provenance','writeScope','sharedWithWeapons'):
                    self.assertIn(key,field)
                self.assertIsNone(field['min']);self.assertIsNone(field['max'])
                self.assertIsNone(field['enumValues'])

    def test_duplicates_and_customization_projectiles_fail_closed(self):
        blocked={w['name'] for w in CAPABILITIES['weapons'] if w['ordinaryWritesBlocked']}
        self.assertEqual(blocked,{'CQC-42 Machete','CQC-73 Entrenchment Tool',
            'GP-31 Grenade Pistol','LAS-5 Scythe','LAS-7 Dagger','P-72 Crisper','SMG-37 Defender'})
        by_name={w['name']:w for w in CAPABILITIES['weapons']}
        for name in ('P-2 Peacemaker','P-19 Redeemer'):
            editable=[f['semanticFieldId'] for f in by_name[name]['fields'] if f['editable']]
            self.assertTrue(editable)
            self.assertTrue(all(field.startswith('weapon.') for field in editable))

    def test_derived_and_shared_metadata_are_explicit(self):
        fields=[field for weapon in CAPABILITIES['weapons'] for field in weapon['fields']]
        self.assertTrue(any(f['derivedReadOnly'] and not f['editable'] for f in fields))
        self.assertTrue(any(f['writeScope']=='shared_projectile' and f['affectsMultipleWeapons'] for f in fields))
        self.assertTrue(any(f['writeScope']=='shared_damage' and f['affectsMultipleWeapons'] for f in fields))
        for field in fields:
            if field['editable']:
                self.assertIn('backing',field)
                self.assertIn(field['backing']['width'],(1,4))

    def test_every_reviewed_descriptor_passes_public_shape_validation(self):
        script=modules()+r'''
local db=require('hd2runtime/domains/player_weapon_authoring')
local writes=require('hd2runtime/domains/player_weapon_writes')
for name,weapon in pairs(db.weapons)do
    local changes={}
    for _,field in ipairs(weapon.fields)do
        if field.editable then
            changes[#changes+1]={field=field.semanticFieldId,
                expect=field.currentDefault,value=field.currentDefault}
        end
    end
    if weapon.ordinaryWritesBlocked then
        local ok=pcall(writes.validate_patch,{id='blocked',
            target={resource='player_weapon',path='weapon',weapon=name},
            field='weapon.fire_rate',expect=1,value=2})
        assert(not ok)
    elseif #changes>0 then
        for first=1,#changes,32 do
            local part={};for index=first,math.min(first+31,#changes)do part[#part+1]=changes[index]end
            local spec=writes.validate_transaction({id='descriptor-audit',
                target={resource='player_weapon',path='weapon',weapon=name},
                changes=part,allow_shared=true})
            assert(spec.weapon==name and #spec.changes==#part)
        end
    end
end
return 'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')

    def test_acceptance_declarations_and_constants(self):
        script=modules()+r'''
local session=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local function validate(request)return writes.validate_patch(request)end
local concussive=session.weapon('AR-23C Liberator Concussive')
assert(concussive.resource=='player_weapon')
assert(validate({id='concussive-1100-rpm',target=concussive,
    field=session.fields.weapon.fire_rate,expect=400,value=1100}).changes[1].field=='weapon.fire_rate')
local verdict=session.weapon('P-113 Verdict')
assert(validate({id='verdict-gravity',target=verdict,
    field=session.fields.projectile.gravity,expect=1,value=0.25}).changes[1].field=='projectile.gravity')
assert(validate({id='verdict-damage',target=verdict,
    field=session.fields.damage.player_standard_damage,expect=140,value=150}).changes[1].field=='damage.standard_damage')
local arc=session.weapon('ARC-12 Blitzer')
local described=arc:describe();assert(described.name=='ARC-12 Blitzer')
assert(validate({id='blitzer-range',target=arc,
    field=session.fields.arc.range,expect=25,value=30}).changes[1].field=='arc.range')
-- JAR root is the generic authoring identity while the proven chain remains compatible.
local jar=session.weapon('JAR-5 Dominator');assert(jar.resource=='player_weapon')
assert(jar:projectile():damage().resource=='jar5')
return 'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')

    def test_exact_storage_encoding_including_one_byte_boolean(self):
        script=modules()+r'''
local b=require('hd2runtime/core/bytes')
assert(#b.encode(1,'u8')==1 and b.value(b.encode(1,'u8'),0,'u8')==1)
assert(#b.encode(4294967295,'u32')==4 and b.value(b.encode(4294967295,'u32'),0,'u32')==4294967295)
assert(#b.encode(-125,'i32')==4 and b.value(b.encode(-125,'i32'),0,'i32')==-125)
local raw=b.encode(1.2,'f32');assert(#raw==4 and math.abs(b.value(raw,0,'f32')-1.2)<0.000001)
return 'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')

    def test_generic_one_and_four_byte_plans_use_guarded_transaction(self):
        script=modules()+r'''
local b=require('hd2runtime/core/bytes')
local guard=require('hd2runtime/core/guarded_transaction')
local owner={base=0x200000,size=8192,type=0x20000,protect=2}
local memory=string.rep('\0',8192)
local protection,writes=2,{}
local function replace(offset,value)memory=memory:sub(1,offset)..value..memory:sub(offset+#value+1)end
replace(100,b.encode(0,'u8'));replace(104,b.encode(400,'f32'))
local runtime={}
function runtime.system_info()return 4096,0x1000000 end
function runtime.query(address)return {base=owner.base,size=owner.size,allocation_base=owner.base,
    state=0x1000,type=owner.type,protect=protection}end
function runtime.read(address,length)local offset=address-owner.base;return memory:sub(offset+1,offset+length)end
function runtime.protect(address,length,value)local old=protection;protection=value;return old end
function runtime.write(address,value)
    writes[#writes+1]={address=address,length=#value};replace(address-owner.base,value);return true,nil,#value
end
local context=memory:sub(97,112)
local result=guard.apply(runtime,{snapshots={{owner=owner,offset=96,bytes=context}},changes={
    {label='weapon.suppressed',owner=owner,offset=100,expected=b.encode(0,'u8'),
        desired=b.encode(1,'u8'),before=b.encode(0,'u8')},
    {label='weapon.fire_rate',owner=owner,offset=104,expected=b.encode(400,'f32'),
        desired=b.encode(1100,'f32'),before=b.encode(400,'f32')},
}})
assert(result.status=='APPLIED'and result.writes==2 and result.bytes_written==5)
assert(writes[1].length==1 and writes[2].length==4 and protection==2)
assert(result.protection_restored and result.non_target_bytes_unchanged)
return 'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')


if __name__=='__main__':unittest.main()
