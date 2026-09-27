import json
import sys
import unittest

from support import ROOT,run
sys.path.insert(0,str(ROOT/'scripts'))
import generate_support_weapon_authoring


class SupportWeaponAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capabilities=json.loads((ROOT/'sdk/SupportWeaponAuthoringCapabilities.json').read_text())

    def test_generated_capability_is_current_and_sanitized(self):
        self.assertFalse(generate_support_weapon_authoring.generate(check=True))
        self.assertEqual(self.capabilities['contract'],
            'hd2runtime.support_weapon.guarded_authoring.v2')
        self.assertEqual(self.capabilities['schemaVersion'],2)
        self.assertEqual(self.capabilities['summary']['catalogWeapons'],35)
        self.assertEqual(self.capabilities['summary']['uniqueSupportIdentities'],27)
        self.assertEqual(self.capabilities['summary']['writableSupportWeapons'],27)
        self.assertEqual(self.capabilities['summary']['duplicateGroupsBlocked'],8)
        self.assertEqual(self.capabilities['summary']['writableProjectileBranches'],16)
        self.assertEqual(self.capabilities['summary']['writableExplosionBranches'],17)
        self.assertEqual(self.capabilities['summary']['internalSupportAuthoringInstances'],828)
        self.assertEqual(self.capabilities['summary']['publishedSupportFieldInstances'],828)
        self.assertEqual(self.capabilities['summary']['legacyFlattenedFieldEntries'],812)
        self.assertEqual(self.capabilities['summary']['deduplicationLossPrevented'],16)
        self.assertEqual(self.capabilities['summary']['duplicateSemanticFieldGroups'],16)
        self.assertEqual(self.capabilities['summary']['duplicateSemanticFieldInstances'],32)
        self.assertEqual(self.capabilities['summary']['intentionallyOmittedInstances'],0)
        self.assertEqual(self.capabilities['referenceContract']['currentReferenceFieldInstances'],0)
        self.assertTrue(self.capabilities['referenceContract']['typedIdentityOnly'])
        required={'identityStatus','family','attackBranches','writableFieldsByDomain',
            'sharedScopes','blockedFields','backpackDependency','linkedStratagem'}
        self.assertEqual(len(self.capabilities['weapons']),35)
        for weapon in self.capabilities['weapons']:
            self.assertTrue(required.issubset(weapon),weapon['name'])
        encoded=json.dumps(self.capabilities)
        for token in ('resourceHash','recordIndex','recordType','settingsType',
                'projectileType','explosionType','offset','0x'):
            self.assertNotIn(token,encoded)
        self.assertEqual(self.capabilities['safety']['writesDuringGeneration'],0)
        self.assertEqual(self.capabilities['safety']['protectionChangesDuringGeneration'],0)
        self.assertEqual(self.capabilities['safety']['fixtureFallback'],'disabled')

    def test_canonical_instances_exactly_cover_internal_descriptors(self):
        runtime,generated=generate_support_weapon_authoring.build()
        audit=generate_support_weapon_authoring.audit_instance_coverage(runtime,generated)
        self.assertEqual(audit,{'internalInstances':828,'publishedInstances':828,
            'missingInstances':0,'unexpectedInstances':0,'identityCoverage':'exact'})
        instances=self.capabilities['fieldInstances']
        self.assertEqual(len(instances),828)
        self.assertEqual(len({item['instanceKey'] for item in instances}),828)
        objects={item['objectKey']:item for item in self.capabilities['backingObjects']}
        operations={item['operationGroupingKey']:item
            for item in self.capabilities['operationGroups']}
        self.assertEqual(len(objects),146)
        self.assertEqual(len(operations),155)
        required={'instanceKey','supportWeapon','supportWeaponIdentity','target','semanticFieldId',
            'qualifiedSemanticFieldId','apiFieldConstant','display','value','writable',
            'readOnly','blockedReason','backing','sharedScope','operation','resolution',
            'provenance'}
        for instance in instances:
            self.assertTrue(required.issubset(instance),instance['instanceKey'])
            self.assertIn(instance['backing']['objectKey'],objects)
            self.assertIn(instance['operation']['transactionGroupingKey'],operations)
            self.assertEqual(instance['supportWeaponIdentity']['name'],instance['supportWeapon'])
            self.assertEqual(instance['supportWeaponIdentity']['identityStatus'],'UNIQUE')
            self.assertEqual(instance['value']['baseline'],instance['value']['expected'])
            self.assertEqual(instance['operation']['phase'],1)
            self.assertEqual(instance['target']['accessor'][0],'support_weapon')
        self.assertEqual(sum(len(weapon['fieldInstanceKeys'])
            for weapon in self.capabilities['weapons']),828)

    def test_gui_can_group_recoilless_instances_without_native_layout_knowledge(self):
        instances=[item for item in self.capabilities['fieldInstances']
            if item['supportWeapon']=='GR-8 Recoilless Rifle']
        def field(field_id):
            return next(item for item in instances if item['semanticFieldId']==field_id)
        projectile=field('projectile.velocity');direct=field('damage.standard_damage')
        radius=field('explosion.outer_radius');blast=field('explosion.damage.standard_damage')
        self.assertEqual(projectile['value']['baseline'],250)
        self.assertEqual(direct['value']['baseline'],3200)
        self.assertEqual(radius['value']['baseline'],3)
        self.assertEqual(blast['value']['baseline'],150)
        self.assertEqual({item['target']['attackRole']for item in
            (projectile,direct)}, {'primary'})
        self.assertEqual({item['target']['attackRole']for item in
            (radius,blast)}, {'primary_impact'})
        self.assertEqual(len({item['backing']['objectKey']for item in
            (projectile,direct,radius,blast)}),4)
        self.assertEqual(len({item['operation']['planGroupingKey']for item in
            (projectile,direct,radius,blast)}),1)
        self.assertEqual(direct['resolution']['parentObjectKey'],
            projectile['backing']['objectKey'])
        self.assertEqual(blast['resolution']['parentObjectKey'],
            radius['backing']['objectKey'])
        self.assertEqual(direct['apiFieldConstant'],
            'hd2.fields.damage.player_standard_damage')
        self.assertTrue(all(item['sharedScope']['requiresAcknowledgement']
            for item in (projectile,direct,radius,blast)))

    def test_shared_scope_lists_every_reviewed_semantic_consumer(self):
        scopes=[item for item in self.capabilities['backingObjects']
            if item['semanticType']=='StatusEffectSettings'
            and item['reviewedConsumerCount']==4]
        self.assertEqual(len(scopes),1)
        consumers={(item['weapon'],item['attackRole'])
            for item in scopes[0]['affectedSemanticConsumers']}
        self.assertEqual(consumers,{('B/FLAM-80 Cremator','primary_status_5'),
            ('EAT-700 Expendable Napalm','primary_impact_status_5'),
            ('FLAM-40 Flamethrower','primary_status_5'),
            ('LAS-98 Laser Cannon','primary_status_5')})
        self.assertTrue(scopes[0]['requiresSharedAcknowledgement'])
        self.assertTrue(scopes[0]['reviewedScopeComplete'])

    def test_representative_capabilities_and_fail_closed_groups(self):
        by_name={weapon['name']:weapon for weapon in self.capabilities['weapons']}
        self.assertFalse(by_name['MG-43 Machine Gun']['writable'])
        self.assertFalse(by_name['EAT-17 Expendable Anti-Tank']['writable'])
        self.assertFalse(by_name['LAS-98 Laser Cannon']['writable'])
        self.assertEqual(by_name['LAS-98 Laser Cannon']['family'],['Beam','Status'])
        self.assertTrue(any(item['field']=='heat.* / heatsink.*' for item in
            by_name['LAS-98 Laser Cannon']['blockedFields']))
        self.assertIn('charge',by_name['ARC-3 Arc Thrower']['writableFieldsByDomain'])
        self.assertIn('arc',by_name['ARC-3 Arc Thrower']['writableFieldsByDomain'])
        self.assertNotIn('weapon.fire_rate',
            by_name['ARC-3 Arc Thrower']['writableFieldsByDomain'].get('weapon',[]))
        self.assertIn('explosion',by_name['B/MD C4 Pack']['writableFieldsByDomain'])
        self.assertEqual(sum(branch['writable'] for branch in
            by_name['MS-11 Solo Silo']['attackBranches']),2)
        self.assertTrue(by_name['GR-8 Recoilless Rifle']['backpackDependency'])
        self.assertTrue(any(item['field']=='backpack storage' for item in
            by_name['GR-8 Recoilless Rifle']['blockedFields']))

    def test_public_targets_validate_shared_domains_and_duplicates(self):
        run(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local gr8=hd2.support_weapon('GR-8 Recoilless Rifle')
local projectile=gr8:attack('primary'):projectile()
local physics=writes.validate_transaction{id='gr8-physics',target=projectile,
 allow_shared=true,changes={
  {field=hd2.fields.projectile.velocity,expect=250,value=500},
  {field=hd2.fields.projectile.gravity,expect=1,value=.5}}}
assert(physics.kind=='support_weapon'and physics.weapon=='GR-8 Recoilless Rifle')
assert(physics.changes[1].descriptor.backing.linkage=='projectile')
local damage=writes.validate_patch{id='gr8-damage',target=projectile,allow_shared=true,
 field=hd2.fields.damage.ap_direct,expect=6,value=7}
assert(damage.changes[1].descriptor.backing.linkage=='projectile_damage')
local explosion=gr8:attack('primary_impact'):explosion()
local radius=writes.validate_patch{id='gr8-radius',target=explosion,allow_shared=true,
 field=hd2.fields.explosion.outer_radius,expect=3,value=12}
assert(radius.changes[1].descriptor.backing.linkage=='projectile_explosion')
local arc=hd2.support_weapon('ARC-3 Arc Thrower'):attack('primary')
local range=writes.validate_patch{id='arc-range',target=arc,allow_shared=true,
 field=hd2.fields.arc.range,expect=55,value=80}
assert(range.changes[1].descriptor.backing.linkage=='arc')
local charge=writes.validate_patch{id='arc-charge',target=hd2.support_weapon('ARC-3 Arc Thrower'),
 field=hd2.fields.charge.minimum_seconds,expect=.699999988079071,value=.35}
assert(charge.changes[1].descriptor.backing.component=='WeaponChargeComponentData')
local ok,why=pcall(writes.validate_patch,{id='mg43-blocked',
 target=hd2.support_weapon('MG-43 Machine Gun'),field=hd2.fields.weapon.fire_rate,
 expect=760,value=1000})
assert(not ok and tostring(why):find('Duplicate runtime roots',1,true))
ok,why=pcall(writes.validate_patch,{id='arc-sentinel',target=hd2.support_weapon('ARC-3 Arc Thrower'),
 field=hd2.fields.weapon.fire_rate,expect=-1,value=60})
assert(not ok and tostring(why):find('not exposed',1,true))
return'ok'
''')

    def test_plan_separates_support_backing_objects(self):
        run(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local plans=require('hd2runtime/domains/composition_plans')
local gr8=hd2.support_weapon('GR-8 Recoilless Rifle')
local projectile=gr8:attack('primary'):projectile()
local explosion=gr8:attack('primary_impact'):explosion()
assert(projectile.path=='projectile_reference'and explosion.path=='explosion',
 tostring(projectile.path)..'/'..tostring(explosion.path))
assert(hd2.fields.explosion.damage_standard_damage=='explosion.damage.standard_damage',
 tostring(hd2.fields.explosion.damage_standard_damage))
local function check(label,value)assert(value,label)end
local ok,why=pcall(plans.validate,{id='physics-only',operations={{id='physics',target=projectile,allow_shared=true,
 field=hd2.fields.projectile.velocity,expect=250,value=500}}});check('physics '..tostring(why),ok)
ok,why=pcall(plans.validate,{id='direct-only',operations={{id='direct',target=projectile,allow_shared=true,
 field=hd2.fields.damage.player_standard_damage,expect=3200,value=5000}}});check('direct '..tostring(why),ok)
ok,why=pcall(plans.validate,{id='radius-only',operations={{id='radius',target=explosion,allow_shared=true,
 field=hd2.fields.explosion.outer_radius,expect=3,value=12}}});check('radius '..tostring(why),ok)
ok,why=pcall(plans.validate,{id='blast-only',operations={{id='blast',target=explosion,allow_shared=true,
 field=hd2.fields.explosion.damage_standard_damage,expect=150,value=1000}}});check('blast '..tostring(why),ok)
local spec=plans.validate{id='recoilless-proof',operations={
 {id='physics',target=projectile,allow_shared=true,
  field=hd2.fields.projectile.velocity,expect=250,value=500},
 {id='direct-damage',target=projectile,allow_shared=true,
  field=hd2.fields.damage.player_standard_damage,expect=3200,value=5000},
 {id='radius',target=explosion,allow_shared=true,
  field=hd2.fields.explosion.outer_radius,expect=3,value=12},
 {id='blast-damage',target=explosion,allow_shared=true,
  field=hd2.fields.explosion.damage_standard_damage,expect=150,value=1000}}}
assert(spec.kind=='composition_plan'and#spec.operations==4)
assert(spec.operations[1].backing_scope=='settings:projectile')
assert(spec.operations[2].backing_scope=='settings:damage')
assert(spec.operations[3].backing_scope=='settings:explosion')
assert(spec.operations[4].backing_scope=='settings:explosion_damage')
return'ok'
''')


if __name__=='__main__':unittest.main()
