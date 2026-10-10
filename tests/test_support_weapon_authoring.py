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
        self.assertEqual(self.capabilities['summary']['writableSupportWeapons'],34)
        self.assertEqual(self.capabilities['summary']['deliveryResolvedIdentities'],7)
        self.assertEqual(self.capabilities['summary']['duplicateGroupsBlocked'],1)
        # + the PLAS-45 Epoch full-charge shot (research/charge-explosions-F5FEE03DCFDB.json).
        self.assertEqual(self.capabilities['summary']['writableProjectileBranches'],21)
        # + the Epoch full-charge impact explosion and the Epoch and RS-422 overcharge explosions; 0.31.0: + the CQC-20
        # Breaching Hammer's ability explosion (scripts/ability_explosion_fields.py).
        self.assertEqual(self.capabilities['summary']['writableExplosionBranches'],22)
        # +33 charge instances (scripts/charge_fields.py: speed/damage/penetration/arc multipliers, auto fire, overcharge
        # explosion, limit and burst on the RS-422, PLAS-45, ARC-3 and 40-K); +60 charge-level instances (the Epoch
        # full-charge shot 18, its explosion 14 and its overcharge explosion 14, the RS-422 overcharge explosion 14).
        # 0.31.0: +2 beam references (attack.beam on the LAS-98 and the 40-K Meltagun, research/beam-outputs); +34
        # missile fields (research/wasp-rocket: W.A.S.P. 9 missile + 9 function_missile, Spear 8, Commando 8); +14 the
        # Breaching Hammer's ability explosion (3 radii, 9 damage, 2 status slots).
        self.assertEqual(self.capabilities['summary']['internalSupportAuthoringInstances'],1541)   # 0.31.0: +1 the MG-43's left input (fire_mode)
        self.assertEqual(self.capabilities['summary']['publishedSupportFieldInstances'],1541)
        self.assertEqual(self.capabilities['summary']['legacyFlattenedFieldEntries'],1428)   # +12 hammer explosion, +1 the MG-43's left input (0.31.0)
        self.assertEqual(self.capabilities['summary']['deduplicationLossPrevented'],113)
        self.assertEqual(self.capabilities['summary']['duplicateSemanticFieldGroups'],50)
        self.assertEqual(self.capabilities['summary']['duplicateSemanticFieldInstances'],114)
        self.assertEqual(self.capabilities['summary']['intentionallyOmittedInstances'],0)
        # + the two overcharge explosion references (RS-422 Railgun, PLAS-45 Epoch) and the status slots of the four
        # charge-level DamageInfo rows (the Epoch full-charge shot and explosion, the two overcharge explosions).
        # 0.31.0: + the beam references of the LAS-98 and the 40-K Meltagun (attack.beam); + the hammer explosion's
        # status slot.
        self.assertEqual(self.capabilities['referenceContract']['currentReferenceFieldInstances'],98)
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
        self.assertEqual(audit,{'internalInstances':1541,'publishedInstances':1541,   # 0.31.0: +34 missile fields, +1 the MG-43's left input (fire_mode)
            'missingInstances':0,'unexpectedInstances':0,'identityCoverage':'exact'})
        instances=self.capabilities['fieldInstances']
        self.assertEqual(len(instances),1541)
        self.assertEqual(len({item['instanceKey'] for item in instances}),1541)
        objects={item['objectKey']:item for item in self.capabilities['backingObjects']}
        operations={item['operationGroupingKey']:item
            for item in self.capabilities['operationGroups']}
        # + the LAS-98 BeamWeapon record (beam.fire_rate); + 7 charge-level rows (the Epoch full-charge projectile, its
        # damage, its explosion, the overcharge explosion and their shared damage row; the RS-422 overcharge explosion
        # and its damage row).
        # 0.31.0: + the 40-K Meltagun BeamWeapon record (beam fire mode and pulse); + 4 missile SeekingMissile records
        # (the W.A.S.P.'s two, the Spear's, the Commando's: research/wasp-rocket), one operation group each.
        self.assertEqual(len(objects),241)   # 0.31.0: + the Breaching Hammer's ability explosion row and its damage row
        self.assertEqual(len(operations),280)   # 0.31.0: + one operation group per hammer explosion row
        required={'instanceKey','supportWeapon','supportWeaponIdentity','target','semanticFieldId',
            'qualifiedSemanticFieldId','apiFieldConstant','display','value','writable',
            'readOnly','blockedReason','backing','sharedScope','operation','resolution',
            'provenance'}
        for instance in instances:
            self.assertTrue(required.issubset(instance),instance['instanceKey'])
            self.assertIn(instance['backing']['objectKey'],objects)
            self.assertIn(instance['operation']['transactionGroupingKey'],operations)
            self.assertEqual(instance['supportWeaponIdentity']['name'],instance['supportWeapon'])
            self.assertIn(instance['supportWeaponIdentity']['identityStatus'],('UNIQUE','DELIVERY_RESOLVED'))
            self.assertEqual(instance['value']['baseline'],instance['value']['expected'])
            self.assertEqual(instance['operation']['phase'],1)
            self.assertEqual(instance['target']['accessor'][0],'support_weapon')
        self.assertEqual(sum(len(weapon['fieldInstanceKeys'])
            for weapon in self.capabilities['weapons']),1541)

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
        for name in ('MG-43 Machine Gun','M-105 Stalwart','MG-206 Heavy Machine Gun','CQC-20 Breaching Hammer'):
            weapon=by_name[name]
            self.assertTrue(weapon['writable'],name)
            self.assertEqual(weapon['identityStatus'],'DELIVERY_RESOLVED')
            self.assertEqual(weapon['identityResolution']['basis'],'call_in_delivery_and_scraped_fingerprint')
            self.assertFalse(weapon['identityResolution']['nonDeliveredRootsAffected'])
        # Delivered roots identified structurally (no scraped magazine values to fingerprint).
        for name,confirmations in (('EAT-17 Expendable Anti-Tank',['SUPPORT_WEAPON_PATH']),
                ('LAS-98 Laser Cannon',['SUPPORT_WEAPON_PATH']),
                ('B/FLAM-80 Cremator',['LOADOUT_PACKAGE','SUPPORT_WEAPON_PATH'])):
            weapon=by_name[name]
            self.assertTrue(weapon['writable'],name)
            self.assertEqual(weapon['identityStatus'],'DELIVERY_RESOLVED')
            self.assertEqual(weapon['identityResolution']['basis'],'call_in_delivery_and_structural_identity')
            self.assertEqual(weapon['identityResolution']['confirmations'],confirmations)
        self.assertFalse(by_name['CQC-72 Entrenchment Tool']['writable'])
        self.assertEqual(by_name['CQC-72 Entrenchment Tool']['identityStatus'],'DUPLICATE')
        self.assertEqual(by_name['LAS-98 Laser Cannon']['family'],['Beam','Status'])
        self.assertIn('heat',by_name['LAS-98 Laser Cannon']['writableFieldsByDomain'])
        eat={branch['name']:branch for branch in by_name['EAT-17 Expendable Anti-Tank']['attackBranches']}
        self.assertTrue(eat['EAT-17 P']['writable'] and eat['EAT-17 P IE']['writable'])
        self.assertEqual(eat['EAT-17 BACKBLAST E']['state'],'PARTIAL')
        cremator={branch['name']:branch for branch in by_name['B/FLAM-80 Cremator']['attackBranches']}
        self.assertTrue(cremator['B/FLAM-80 CREMATOR S']['writable'] and cremator['Fire']['writable'])
        self.assertEqual((cremator['Fire Panic']['state'],cremator['FlamerSlowed']['state']),('PARTIAL','PARTIAL'))
        self.assertIn('charge',by_name['ARC-3 Arc Thrower']['writableFieldsByDomain'])
        self.assertIn('arc',by_name['ARC-3 Arc Thrower']['writableFieldsByDomain'])
        self.assertNotIn('weapon.fire_rate',
            by_name['ARC-3 Arc Thrower']['writableFieldsByDomain'].get('weapon',[]))
        self.assertIn('explosion',by_name['B/MD C4 Pack']['writableFieldsByDomain'])
        self.assertEqual(sum(branch['writable'] for branch in
            by_name['MS-11 Solo Silo']['attackBranches']),2)
        self.assertTrue(by_name['GR-8 Recoilless Rifle']['backpackDependency'])
        # 0.31.0: the team-reload backpack is resolved (research/team-reload-ammo-F5FEE03DCFDB.json).
        self.assertFalse(any(item['field']=='backpack storage' for item in
            by_name['GR-8 Recoilless Rifle']['blockedFields']))
        self.assertEqual(by_name['GR-8 Recoilless Rifle']['ammoBackpack']['relationship'],'team_reload')

    def test_public_targets_validate_shared_domains_and_duplicates(self):
        gr8=[item for item in self.capabilities['fieldInstances']
            if item['supportWeapon']=='GR-8 Recoilless Rifle'and item['target']['attackRole']=='primary']
        baseline={item['semanticFieldId']:item['value']['baseline']for item in gr8}
        # Native lifetime 0 means no explicit limit, so it is not exposed.
        self.assertNotIn('projectile.lifetime',baseline)
        rl77=next(item for item in self.capabilities['fieldInstances']
            if item['supportWeapon']=='RL-77 Airburst Rocket Launcher'
            and item['semanticFieldId']=='projectile.lifetime')
        self.assertEqual(rl77['value']['baseline'],1.5)
        run('local projectile_lifetime='+repr(rl77['value']['baseline'])
            +' local projectile_penetration='+repr(baseline['projectile.penetration_slowdown'])+r'''
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
local mg43=writes.validate_patch{id='mg43-rate',target=hd2.support_weapon('MG-43 Machine Gun'),
 field=hd2.fields.weapon.fire_rate,expect=760,value=1000}
assert(mg43.identity_resource~=mg43.resource and mg43.root_rack and mg43.ownership_chain[1].kind=='stratagem_payload')
local ok,why=pcall(writes.validate_patch,{id='cqc72-blocked',
 target=hd2.support_weapon('CQC-72 Entrenchment Tool'),field=hd2.fields.weapon.ergonomics,
 expect=0,value=10})
assert(not ok and tostring(why):find('Duplicate runtime roots',1,true),tostring(why))
local eat=writes.validate_patch{id='eat-damage',target=hd2.support_weapon('EAT-17 Expendable Anti-Tank'):attack(2):projectile(),
 allow_shared=true,field=hd2.fields.projectile.velocity,expect=200,value=250}
assert(eat.changes[1].descriptor.backing.kind=='settings')
ok,why=pcall(writes.validate_patch,{id='reload-ack',target=hd2.support_weapon('GR-8 Recoilless Rifle'),
 field=hd2.fields.reload.duration,expect=6,value=3})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true))
local reload=writes.validate_patch{id='reload',target=hd2.support_weapon('GR-8 Recoilless Rifle'),
 allow_unverified_effect=true,field=hd2.fields.reload.duration,expect=6,value=3}
assert(reload.changes[1].descriptor.backing.component=='WeaponReloadComponentData'
 and reload.changes[1].descriptor.backing.offset==56)
local windup=writes.validate_patch{id='windup',target=hd2.support_weapon('M-1000 Maxigun'),
 field=hd2.fields.windup.wind_up_seconds,expect=.5,value=.1}
assert(windup.changes[1].descriptor.backing.component=='WeaponWindUpComponentData')
ok,why=pcall(writes.validate_patch,{id='winddown',target=hd2.support_weapon('M-1000 Maxigun'),
 field=hd2.fields.windup.wind_down_seconds,expect=.5,value=.1})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true))
local life=writes.validate_patch{id='life',allow_shared=true,
 target=hd2.support_weapon('RL-77 Airburst Rocket Launcher'):attack('primary'):projectile(),
 field=hd2.fields.projectile.lifetime,expect=projectile_lifetime,value=5}
assert(life.changes[1].descriptor.backing.offset==52)
local pen=writes.validate_patch{id='pen',target=projectile,allow_shared=true,
 field=hd2.fields.projectile.penetration_slowdown,expect=projectile_penetration,value=.5}
assert(pen.changes[1].descriptor.backing.offset==64)
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
