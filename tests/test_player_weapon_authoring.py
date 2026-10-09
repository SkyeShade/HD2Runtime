import json
import sys
import unittest

from support import ROOT, execute, modules
sys.path.insert(0,str(ROOT/'scripts'))
import generate_weapon_authoring


CAPABILITIES = json.loads((ROOT/'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())
AMMO_CAPABILITIES = json.loads((ROOT/'sdk/PlayerWeaponAmmoCapabilities.json').read_text())


RANGED_0_30_4={'heat.firing_charge':(0,10000),'heat.charge_gain_per_second':(0,100000),
    'heat.charge_loss_per_second':(0,100000),'beam.fire_mode':(4,6),'beam.fire_rate':(1,6000),
    'beam.pulse_beams':(1,8),'beam.pulse_seconds':(0,10)}

class PlayerWeaponAuthoringTests(unittest.TestCase):
    def test_generated_capabilities_are_current(self):
        generate_weapon_authoring.generate(check=True)

    def test_matrix_covers_catalog_without_runtime_addresses(self):
        self.assertEqual(CAPABILITIES['summary']['weapons'], 80)
        self.assertEqual(CAPABILITIES['summary']['uniqueWeapons'], 80)   # (0.30.2: the seven DUPLICATE weapons resolved to their proven roots, research/weapon-roots)
        self.assertEqual(CAPABILITIES['summary']['duplicateWeapons'], 0)
        encoded=json.dumps(CAPABILITIES).lower()
        self.assertNotIn('absoluteaddress', encoded)
        self.assertNotIn('baseaddress', encoded)
        for weapon in CAPABILITIES['weapons']:
            self.assertTrue(weapon['implementationFamilies'])
            for field in weapon['fields']:
                for key in ('displayName','semanticFieldId','type','unit','currentDefault','editable',
                            'derivedReadOnly','provenance','writeScope','sharedWithWeapons',
                            'semanticTarget','canonical','preferred','deprecated','aliasOf',
                            'acceptedForWrites'):
                    self.assertIn(key,field)
                if field['semanticFieldId']=='fire_mode.burst_rounds':
                    self.assertEqual((field['min'],field['max']),(1,10))
                elif field['semanticFieldId']=='fire_rate.modes':
                    self.assertEqual((field['min'],field['max']),(1,3000))
                elif field.get('statusAttach')and field['type']=='number':
                    self.assertEqual((field['min'],field['max']),(0,1000))
                elif field['semanticFieldId'].startswith('heat.level_')and field['type']=='number':
                    self.assertEqual((field['min'],field['max']),(0,10000))   # LAS-17 heat levels
                elif field['semanticFieldId'] in RANGED_0_30_4:   # 0.30.4 firing charge and beam pulse
                    self.assertEqual((field['min'],field['max']),RANGED_0_30_4[field['semanticFieldId']])
                else:
                    self.assertIsNone(field['min']);self.assertIsNone(field['max'])
                if field['semanticFieldId']=='weapon.default_fire_mode':
                    self.assertEqual(field['enumValues'],{'full_auto':1,'semi_auto':2})
                else:self.assertIsNone(field['enumValues'])

    def test_duplicates_and_customization_projectiles_fail_closed(self):
        # 0.30.2: no weapon is blocked by its identity; each corrected one names its proof.
        blocked={w['name'] for w in CAPABILITIES['weapons'] if w['ordinaryWritesBlocked']}
        self.assertEqual(blocked,set())
        catalog=json.loads((ROOT/'schemas/player_weapon_authoring_catalog.json').read_text())
        corrected={w['name']:w for w in catalog['weapons'] if w.get('rootCorrection')}
        self.assertEqual(set(corrected),{'CQC-42 Machete','CQC-73 Entrenchment Tool',
            'GP-31 Grenade Pistol','LAS-5 Scythe','LAS-7 Dagger','P-72 Crisper','SMG-37 Defender'})
        for name,entry in corrected.items():
            self.assertEqual(len(entry['resources']),1,name)
            self.assertEqual(len(entry['candidateRoots']),2,name)
            self.assertIn(entry['rootCorrection']['evidence'],('equipped_snapshot','underbarrel','call_in_rack'))
        self.assertEqual(corrected['GP-31 Grenade Pistol']['resources'],['0x52E4334E6A128CAF'])
        self.assertEqual(corrected['LAS-7 Dagger']['resources'],['0x7B06196E90154C88'])
        by_name={w['name']:w for w in CAPABILITIES['weapons']}
        for name in ('P-2 Peacemaker','P-19 Redeemer'):
            editable=[f['semanticFieldId'] for f in by_name[name]['fields'] if f['editable']]
            self.assertTrue(editable)
            # Weapon-level fields only: the customization-owned projectile fields fail closed.
            self.assertTrue(all(field.startswith(('weapon.','fire_mode.','fire_rate.','weapon_function.',
                'function_ammo.','presentation.')) for field in editable))

    def test_derived_and_shared_metadata_are_explicit(self):
        fields=[field for weapon in CAPABILITIES['weapons'] for field in weapon['fields']]
        self.assertTrue(any(f['derivedReadOnly'] and not f['editable'] for f in fields))
        self.assertTrue(any(f['writeScope']=='shared_projectile' and f['affectsMultipleWeapons'] for f in fields))
        self.assertTrue(any(f['writeScope']=='shared_projectile_damage_definition'
            and f['affectsMultipleWeapons'] for f in fields))
        for field in fields:
            if field['editable']:
                self.assertIn('backing',field)
                # Native slot lists span their slots: four FireMode slots, three rate slots, five trait tags.
                widths={'fire_mode_set':(16,),'fire_rate_set':(12,),'trait_set':(20,),'armor_penetration_label':(20,),
                    'weapon_sound':(12,)}
                self.assertIn(field['backing']['width'],widths.get(field['type'],(1,4)))

    def test_ammo_capability_matrix_covers_all_player_weapons(self):
        summary=AMMO_CAPABILITIES['summary']
        self.assertEqual(summary['weapons'],80)
        self.assertEqual(summary['roundsFeedWeapons'],15)
        self.assertEqual(summary['directMagazineWeapons'],33)
        self.assertEqual(summary['defaultMagazineOptions'],19)
        self.assertEqual(summary['nativeMagazineOptionsCataloged'],52)
        self.assertEqual(summary['sharedDefaultOptionGroups'],1)
        self.assertEqual(len(AMMO_CAPABILITIES['weapons']),80)
        self.assertEqual(AMMO_CAPABILITIES['safety']['writes'],0)
        self.assertEqual(AMMO_CAPABILITIES['safety']['protectionChanges'],0)
        self.assertEqual(
            {(item['weapon'],item['catalog'],item['runtime'])
             for item in AMMO_CAPABILITIES['discrepancies']},
            {('AR-11 Arbitrator',4,45),('AR/GL-21 One-Two',1,40)})

    def test_detachable_rounds_customization_and_duplicate_semantics(self):
        by_name={w['name']:w for w in CAPABILITIES['weapons']}
        def fields(name):return {f['semanticFieldId']:f for f in by_name[name]['fields']}
        jar=fields('JAR-5 Dominator')
        self.assertTrue(jar['magazine.capacity']['editable'])
        self.assertEqual(jar['magazine.spare_magazines']['currentDefault'],6)
        self.assertEqual(jar['magazine.starting_magazines']['currentDefault'],4)
        self.assertEqual(jar['magazine.magazines_from_supply']['currentDefault'],6)
        self.assertTrue(jar['magazine.magazines_from_ammo_box']['derivedReadOnly'])
        punisher=fields('SG-8 Punisher')
        self.assertTrue(punisher['rounds.spare_rounds']['editable'])
        self.assertEqual(punisher['rounds.spare_rounds']['currentDefault'],60)
        self.assertEqual(punisher['rounds.starting_rounds']['currentDefault'],32)
        self.assertEqual(punisher['rounds.rounds_from_supply']['currentDefault'],60)
        self.assertEqual(punisher['rounds.rounds_from_ammo_box']['currentDefault'],30)
        peacemaker=fields('P-2 Peacemaker')
        self.assertEqual(peacemaker['magazine.capacity']['currentDefault'],15)
        self.assertFalse(peacemaker['magazine.capacity']['editable'])
        ammo_by_name={w['name']:w for w in AMMO_CAPABILITIES['weapons']}
        shared=ammo_by_name['AR-23 Liberator']['defaultMagazineOption']
        self.assertTrue(shared['shared'])
        self.assertEqual(shared['sharedWithWeapons'],
            ['AR-23P Liberator Penetrator','AR-59 Suppressor'])
        self.assertEqual(ammo_by_name['P-2 Peacemaker']['defaultMagazineOption']['name'],
            'Pistol 12x20mm. Standard')
        gp=next(w for w in AMMO_CAPABILITIES['weapons'] if w['name']=='GP-31 Grenade Pistol')
        # 0.30.2: the GP-31's own root (the other was the One-Two underbarrel) and its own values.
        self.assertEqual((gp['effectiveCapacity']['status'],gp['effectiveCapacity']['value']),('RESOLVED',1))
        self.assertNotIn('resourceValues',gp)
        self.assertEqual({k:gp['fields'][k]['value'] for k in ('spareRounds','roundsFromSupply','startingRounds')},
            {'spareRounds':6,'roundsFromSupply':4,'startingRounds':4})

    def test_semantic_alias_metadata_and_complete_backing_audit(self):
        aliases={(item['alias'],item['canonical']):item
                 for item in CAPABILITIES['semanticAliases']}
        self.assertEqual(set(aliases),{
            ('weapon.capacity','magazine.capacity'),
            ('weapon.feed_capacity_1','rounds.feed_capacity_1'),
            ('weapon.feed_capacity_2','rounds.feed_capacity_2'),
            # The mislabelled charge speed ids: published on support weapons only (no player weapon instance).
            ('charge.minimum_seconds','charge.speed_multiplier_min'),
            ('charge.maximum_seconds','charge.speed_multiplier_overcharge')})
        self.assertEqual(aliases[('weapon.capacity','magazine.capacity')]['instanceCount'],32)
        self.assertEqual(aliases[('weapon.feed_capacity_1','rounds.feed_capacity_1')]['instanceCount'],15)
        self.assertEqual(aliases[('weapon.feed_capacity_2','rounds.feed_capacity_2')]['instanceCount'],15)
        audit=CAPABILITIES['backingCollisionAudit']
        self.assertEqual(audit['fieldInstancesAudited'],CAPABILITIES['summary']['fieldInstances'])
        # weapon.third_person_reticle is a distinct boolean view over the crosshair_type bytes.
        self.assertEqual(audit['exactBackingCollisionGroups'],289)
        self.assertEqual(audit['aliasPairInstances'],62)
        self.assertEqual(audit['unclassifiedCollisionPairs'],0)
        jar=next(w for w in CAPABILITIES['weapons'] if w['name']=='JAR-5 Dominator')
        fields={f['semanticFieldId']:f for f in jar['fields']}
        legacy=fields['weapon.capacity'];canonical=fields['magazine.capacity']
        self.assertEqual(legacy['aliasOf'],'magazine.capacity')
        self.assertTrue(legacy['deprecated'] and legacy['acceptedForWrites'])
        self.assertFalse(legacy['editable'] or legacy['preferred'] or legacy['canonical'])
        self.assertTrue(canonical['editable'] and canonical['preferred'] and canonical['canonical'])
        self.assertIsNone(canonical['aliasOf'])
        self.assertEqual(legacy['backing'],canonical['backing'])
        self.assertNotEqual(fields['weapon.base_capacity']['semanticTarget'],canonical['semanticTarget'])
        self.assertFalse(fields['weapon.base_capacity']['editable'])

    def test_legacy_and_canonical_alias_validation_and_coalescing(self):
        script=modules()+r'''
local writes=require('hd2runtime/domains/player_weapon_writes')
local target={resource='player_weapon',path='weapon',weapon='JAR-5 Dominator'}
local function patch(field)return writes.validate_patch{
 id='capacity',target=target,field=field,expect=15,value=20}
end
local legacy=patch('weapon.capacity');local canonical=patch('magazine.capacity')
assert(legacy.changes[1].field=='weapon.capacity')
assert(legacy.changes[1].canonical_field=='magazine.capacity')
assert(canonical.changes[1].canonical_field=='magazine.capacity')
local same=writes.validate_transaction{id='same',target=target,changes={
 {field='weapon.capacity',expect=15,value=20},
 {field='magazine.capacity',expect=15,value=20}}}
assert(#same.changes==1 and same.changes[1].canonical_field=='magazine.capacity')
assert(#same.changes[1].semantic_aliases==2)
local ok,why=pcall(writes.validate_transaction,{id='conflict',target=target,changes={
 {field='weapon.capacity',expect=15,value=20},
 {field='magazine.capacity',expect=15,value=21}}})
assert(not ok and tostring(why):find('SEMANTIC_CONFLICT:',1,true))
local session=require('hd2runtime/api/session').new({write=function()end,protect=function()end},function()end)
local ensured=session.ensure{startup_delay=0,transaction={id='ensured-alias',
 target=session.weapon('JAR-5 Dominator'),changes={
  {field=session.fields.weapon.capacity,expect=15,value=20},
  {field=session.fields.magazine.capacity,expect=15,value=20}}}}
assert(ensured.kind=='transaction'and ensured.status=='waiting');ensured.cancel()
local ensure_ok,ensure_why=pcall(session.ensure,{startup_delay=0,transaction={id='ensured-conflict',
 target=session.weapon('JAR-5 Dominator'),changes={
  {field=session.fields.weapon.capacity,expect=15,value=20},
  {field=session.fields.magazine.capacity,expect=15,value=21}}}})
assert(not ensure_ok and tostring(ensure_why):find('SEMANTIC_CONFLICT:',1,true))
return'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')

    def test_same_value_aliases_produce_one_physical_write(self):
        script=modules()+r'''
local b=require('hd2runtime/core/bytes')
local writes=require('hd2runtime/domains/player_weapon_writes')
local guard=require('hd2runtime/core/guarded_transaction')
local target={resource='player_weapon',path='weapon',weapon='JAR-5 Dominator'}
local spec=writes.validate_transaction{id='coalesced',target=target,changes={
 {field='weapon.capacity',expect=15,value=20},
 {field='magazine.capacity',expect=15,value=20}}}
local descriptor=spec.changes[1].descriptor;local backing=descriptor.backing
local owner={base=0x200000,size=8192,type=0x20000,protect=2}
local record_offset=64;local record_bytes=string.rep('\0',152)
local function splice(value,offset,bytes)return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)end
record_bytes=splice(record_bytes,136,b.encode(15,'u32'))
local memory=string.rep('\0',owner.size);memory=splice(memory,record_offset,record_bytes)
local record={owner=owner,offset=record_offset,bytes=record_bytes,identity={
 componentType=1,recordIndex=backing.recordIndex,indexRow=backing.indexRow,
 uniqueOwner=backing.uniqueOwner,ownerCount=backing.ownerCount}}
local resolved={candidate={},catalog={record=function(_,component)
 assert(component=='WeaponMagazineComponentData');return record end}}
local reader={snapshots={{owner=owner,offset=record_offset,bytes=record_bytes}}}
local plan=writes.prepare(resolved,reader,spec)
assert(#plan.changes==1 and #plan.changes[1].semantic_aliases==2)
local protection,physical_writes=2,0
local runtime={}
function runtime.system_info()return 4096,0x1000000 end
function runtime.query(address)return {base=owner.base,size=owner.size,allocation_base=owner.base,
 state=0x1000,type=owner.type,protect=protection}end
function runtime.read(address,length)local offset=address-owner.base
 return memory:sub(offset+1,offset+length)end
function runtime.protect(address,length,value)local old=protection;protection=value;return old end
function runtime.write(address,value)physical_writes=physical_writes+1
 memory=splice(memory,address-owner.base,value);return true,nil,#value end
local result=guard.apply(runtime,plan)
assert(result.status=='APPLIED'and result.writes==1 and physical_writes==1)
assert(b.value(memory,record_offset+136,'u32')==20 and protection==2)
return'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')

    def test_every_reviewed_descriptor_passes_public_shape_validation(self):
        script=modules()+r'''
local db=require('hd2runtime/domains/player_weapon_authoring')
local writes=require('hd2runtime/domains/player_weapon_writes')
for name,weapon in pairs(db.weapons)do
    local changes={}
    for _,field in ipairs(weapon.fields)do
        if field.editable and field.type~='projectile_reference'
            and field.type~='explosion_reference'and field.type~='function_projectile_reference'
            and not field.semanticFieldId:match('^explosion%.') then
            local value=field.currentDefault
            if field.writeKind=='reorder_native_mode_vector'then
                for _,candidate in ipairs(field.allowedValues)do
                    if candidate~=field.currentDefault then value=candidate end
                end
            end
            changes[#changes+1]={field=field.semanticFieldId,
                expect=field.currentDefault,value=value}
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
                changes=part,allow_shared=true,allow_unverified_effect=true})
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
    field=session.fields.projectile.gravity,expect=1,value=0.25,
    allow_shared=true}).changes[1].field=='projectile.gravity')
assert(validate({id='verdict-damage',target=verdict,
    field=session.fields.damage.player_standard_damage,expect=140,value=150,
    allow_shared=true}).changes[1].field=='damage.standard_damage')
local arc=session.weapon('ARC-12 Blitzer')
local described=arc:describe();assert(described.name=='ARC-12 Blitzer')
assert(validate({id='blitzer-range',target=arc,
    field=session.fields.arc.range,expect=25,value=30}).changes[1].field=='arc.range')
local jar_ammo=session.weapon('JAR-5 Dominator')
assert(validate({id='jar-spares',target=jar_ammo,
    field=session.fields.magazine.spare_magazines,expect=6,value=8}).changes[1].field=='magazine.spare_magazines')
local punisher=session.weapon('SG-8 Punisher')
assert(validate({id='punisher-reserve',target=punisher,
    field=session.fields.rounds.spare_rounds,expect=60,value=80}).changes[1].field=='rounds.spare_rounds')
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
