"""Generate runtime and GUI weapon authoring metadata from one reviewed schema and snapshot report."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_REPORT=ROOT/'build/snapshot-results-authoring/PlayerWeaponRuntimeMap.json'
DEFAULT_IDENTITIES=ROOT/'build/snapshot-results-authoring/PlayerWeaponRuntimeMap.identity-candidates.json'
SCHEMA=ROOT/'schemas/player_weapon_fields.json'
VERSION_FILE=ROOT/'VERSION'
CATALOG=ROOT/'schemas/player_weapon_authoring_catalog.json'
AMMO_CATALOG=ROOT/'schemas/player_weapon_ammo_catalog.json'
COMPOSITION_CATALOG=ROOT/'schemas/player_weapon_composition_catalog.json'
JSON_OUTPUT=ROOT/'sdk/PlayerWeaponAuthoringCapabilities.json'
AMMO_JSON_OUTPUT=ROOT/'sdk/PlayerWeaponAmmoCapabilities.json'
LUA_OUTPUT=ROOT/'domains/player_weapon_authoring.lua'


def lua(value):
    if isinstance(value,dict):
        return '{'+','.join('['+lua(k)+']='+lua(v) for k,v in sorted(value.items()))+'}'
    if isinstance(value,list):return '{'+','.join(lua(v) for v in value)+'}'
    if isinstance(value,bool):return 'true' if value else 'false'
    if value is None:return 'nil'
    if isinstance(value,(int,float)):return repr(value)
    return json.dumps(str(value),ensure_ascii=True)


def refresh_catalog(report_path=DEFAULT_REPORT,identities_path=DEFAULT_IDENTITIES,catalog_path=CATALOG):
    report=json.loads(Path(report_path).read_text());identities=json.loads(Path(identities_path).read_text())
    candidates={item['resourceHash']:item for item in report['runtimeCandidates']}
    value={'schemaVersion':1,'sourceSnapshot':'F5FEE03DCFDB-20260926T222226Z.hd2snap',
        'gameFingerprints':report['gameFingerprints'],'candidates':{},'weapons':[]}
    for name in sorted(identities):
        identity=identities[name];resources=[]
        if identity.get('bestCandidate'):resources.append(identity['bestCandidate']['resourceHash'])
        resources.extend(item['resourceHash'] for item in identity.get('competingCandidates') or [])
        for resource in resources:
            if resource not in value['candidates']:
                candidate=candidates[resource]
                value['candidates'][resource]={'resourceHash':candidate['resourceHash'],
                    'ownership':candidate['ownership'],
                    'resolvedFields':{key:item['value'] for key,item in candidate['resolvedFields'].items()},
                    'capacity':candidate.get('capacity'),'attacks':candidate.get('attacks'),
                    'implementationFamilies':candidate.get('implementationFamilies')}
        value['weapons'].append({'name':name,'slot':identity.get('slot'),'category':identity.get('category'),
            'resolution':identity['resolution'],'resources':resources})
    Path(catalog_path).write_text(json.dumps(value,indent=2)+'\n')


def build(catalog_path=CATALOG):
    source=json.loads(Path(catalog_path).read_text())
    ammo_source=json.loads(AMMO_CATALOG.read_text())
    composition_source=json.loads(COMPOSITION_CATALOG.read_text())
    ammo_by_name={item['name']:item for item in ammo_source['weapons']}
    assert len(ammo_by_name)==80 and set(ammo_by_name)=={item['name'] for item in source['weapons']}, \
        'ammo capability catalog must cover the same 80 player weapons'
    report={'gameFingerprints':source['gameFingerprints']};identities={};candidates=source['candidates']
    for entry in source['weapons']:
        resources=entry['resources']
        identities[entry['name']]={'resolution':entry['resolution'],'slot':entry.get('slot'),
            'category':entry.get('category'),'bestCandidate':{'resourceHash':resources[0]},
            'competingCandidates':[{'resourceHash':resource}for resource in resources[1:]]}
    schema=json.loads(SCHEMA.read_text())
    definitions={item['id']:item for item in schema['fields']}
    alias_rules=schema.get('alias_rules',[])

    weapon_candidates={}
    for name,entry in identities.items():
        values=[]
        if entry.get('bestCandidate'):values.append(entry['bestCandidate']['resourceHash'])
        values.extend(item['resourceHash'] for item in entry.get('competingCandidates') or [])
        weapon_candidates[name]=values

    component_consumers={}
    settings_consumers={}
    for name,resources in weapon_candidates.items():
        for resource in resources:
            candidate=candidates[resource]
            for component,identity in candidate['ownership'].items():
                key=f"component:{component}:{identity['recordIndex']}"
                component_consumers.setdefault(key,set()).add(name)
            for attack in candidate.get('attacks') or []:
                for label,kind in (('projectileSettings','projectile'),('arcSettings','arc'),('beamSettings','beam')):
                    record=attack.get(label)
                    if record:
                        key=f"settings:{kind}:{record['group']}:{record['row']}:{record['recordType']}"
                        settings_consumers.setdefault(key,set()).add(name)
                record=attack.get('damageInfo')
                if record:
                    key=f"settings:damage:{record['group']}:{record['row']}:{record['recordType']}"
                    settings_consumers.setdefault(key,set()).add(name)

    provenance={
        'structural_candidate':True,'schema_labelled':True,'correlation_proven':True,
        'current_live_ownership_proven':False,'gameplay_proven':False,
        'native_consumer_proven':False,'pending_gameplay_confirmation':True,
        'source':'schemas/player_weapon_fields.json + F5FEE03DCFDB snapshot'}

    def definition(field_id):
        base=field_id
        if base.startswith('attack.') and base.endswith('.projectile'):base='attack.projectile'
        for branch in ('.primary.','.alternate.'):
            if branch in base:base=base.replace(branch,'.')
        base=re.sub(r'\.status_\d+_type$','.status_type',base)
        base=re.sub(r'\.status_\d+_strength$','.status_strength',base)
        return definitions[base]

    def make_field(field_id,current,backend=None,editable=None,reason=None,derived=None):
        spec=definition(field_id)
        result={'displayName':spec['display_name'],'semanticFieldId':field_id,
            'type':spec['type'],'unit':spec.get('unit'),'currentDefault':current,
            'editable':spec['writable'] if editable is None else editable,
            'derivedReadOnly':spec['derived'] if derived is None else derived,
            'semanticTarget':spec.get('semantic_target',spec['id']),
            'canonical':True,'preferred':True,'deprecated':False,'aliasOf':None,
            'provenance':provenance.copy(),'min':None,'max':None,'enumValues':None}
        if backend:
            result['backing']=backend
            if backend['kind']=='component':
                identity_key=f"component:{backend['component']}:{backend['recordIndex']}"
                affected=sorted(component_consumers.get(identity_key,set())-{name})
                shared=backend.get('ownerCount',1)>1 or bool(affected)
                scope='shared_settings' if shared else 'weapon_local'
            else:
                identity_key=f"settings:{backend['settings']}:{backend['group']}:{backend['row']}:{backend['recordType']}"
                affected=sorted(settings_consumers.get(identity_key,set())-{name})
                shared=bool(affected)or backend.get('consumerCount',1)>1
                scope={'projectile':'shared_projectile','damage':'shared_damage'}.get(
                    backend['settings'],'shared_settings') if shared else 'weapon_local'
            result['writeScope']=scope
            result['sharedWithWeapons']=affected
            result['affectsMultipleWeapons']=shared
        else:
            result['writeScope']='unknown';result['sharedWithWeapons']=[]
            result['affectsMultipleWeapons']=False
        result['reason']=reason or spec.get('reason')
        if result['derivedReadOnly']:result['editable']=False
        result['acceptedForWrites']=result['editable']
        return result

    def backing_signature(field):
        backend=field.get('backing')
        if not backend:return None
        if backend['kind']=='component':
            owner=('component',backend['component'],backend['recordIndex'],backend['indexRow'])
        else:
            owner=('settings',backend['settings'],backend['group'],backend['row'],
                backend['recordType'],backend['settingsType'])
        return owner+(backend['offset'],backend['width'],backend['storage'])

    alias_instance_counts=Counter();alias_write_counts=Counter()

    def apply_alias_rules(fields):
        by_id={field['semanticFieldId']:field for field in fields}
        for rule in alias_rules:
            alias=by_id.get(rule['alias']);canonical=by_id.get(rule['canonical'])
            if not alias or not canonical:continue
            alias_backing=backing_signature(alias);canonical_backing=backing_signature(canonical)
            if rule.get('requires_identical_backing') and (
                    alias_backing is None or alias_backing!=canonical_backing):continue
            assert alias['semanticTarget']==canonical['semanticTarget'], \
                f"Alias semantic target differs: {rule['alias']} -> {rule['canonical']}"
            write_accepted=alias['editable'] and canonical['editable']
            previous_reason=alias.get('reason')
            alias.update(aliasOf=canonical['semanticFieldId'],canonical=False,preferred=False,
                deprecated=rule.get('deprecated',True),editable=False,
                acceptedForWrites=write_accepted)
            alias['reason']='Deprecated compatibility alias; use '+canonical['semanticFieldId']+'.'
            if previous_reason:alias['reason']+=' '+previous_reason
            canonical.update(canonical=True,preferred=True,deprecated=False,aliasOf=None)
            alias_instance_counts[(rule['alias'],rule['canonical'])]+=1
            if write_accepted:alias_write_counts[(rule['alias'],rule['canonical'])]+=1

    def component_backend(candidate,name,offset,storage):
        identity=candidate['ownership'][name]
        return {'kind':'component','component':name,'offset':offset,'storage':storage,
            'width':1 if storage=='u8' else 4,'recordIndex':identity['recordIndex'],
            'indexRow':identity['indexRow'],'ownerCount':identity['ownerCount'],
            'uniqueOwner':identity['uniqueOwner']}

    def settings_backend(kind,record,offset,storage,branch):
        return {'kind':'settings','settings':kind,'offset':offset,'storage':storage,
            'width':4,'group':record['group'],'row':record['row'],
            'recordType':record['recordType'],'settingsType':record['settingsType'],'branch':branch,
            **({'consumerCount':record['projectileConsumerCount']}
                if record.get('projectileConsumerCount')is not None else{})}

    weapons=[]
    for name in sorted(identities):
        identity=identities[name];candidate=candidates[identity['bestCandidate']['resourceHash']]
        unique=identity['resolution']=='UNIQUE'
        blocked=None if unique else 'Ambiguous runtime identity; ordinary hd2.weapon(name) writes fail closed.'
        fields=[];resolved=candidate['resolvedFields']
        ownership=candidate['ownership']

        slot_backend=component_backend(candidate,'LoadoutPackageComponentData',0,'u32') \
            if 'LoadoutPackageComponentData'in ownership else None
        fields.append(make_field('weapon.slot',resolved.get('weapon_slot'),slot_backend,editable=False,
            reason='Identity/classification metadata; changing loadout classification is not supported.'))
        weapon_values={
            'weapon.ergonomics':('ergonomics',356,'f32'),'weapon.sway':('sway',104,'f32'),
            'weapon.horizontal_spread':('spread_horizontal',84,'f32'),
            'weapon.vertical_spread':('spread_vertical',88,'f32'),
            'weapon.recoil_drift_horizontal':('recoil_drift_horizontal',0,'f32'),
            'weapon.recoil_drift_vertical':('recoil_drift_vertical',4,'f32'),
            'weapon.recoil_climb_horizontal':('recoil_climb_horizontal',28,'f32'),
            'weapon.recoil_climb_vertical':('recoil_climb_vertical',32,'f32'),
            'weapon.suppressed':('is_suppressed',112,'u8')}
        for field_id,(value_key,offset,storage) in weapon_values.items():
            backend=component_backend(candidate,'WeaponDataComponentData',offset,storage)
            fields.append(make_field(field_id,resolved.get(value_key),backend,unique,blocked))
        fields.append(make_field('weapon.crosshair_type',resolved.get('crosshair_type'),
            component_backend(candidate,'WeaponDataComponentData',400,'u32'),editable=False,
            reason=definitions['weapon.crosshair_type']['reason']))
        fields.append(make_field('weapon.primary_fire_mode',resolved.get('primary_fire_mode'),
            component_backend(candidate,'WeaponDataComponentData',144,'u32'),editable=False,
            reason=definitions['weapon.primary_fire_mode']['reason']))
        for field_id,value_key in (('weapon.recoil','recoil'),
                ('weapon.horizontal_recoil','horizontal_recoil'),('weapon.vertical_recoil','vertical_recoil')):
            fields.append(make_field(field_id,resolved.get(value_key),editable=False,
                reason=definitions[field_id]['reason'],derived=True))

        if 'fire_rate' in resolved:
            if 'ProjectileWeaponComponentData' in ownership:
                backend=component_backend(candidate,'ProjectileWeaponComponentData',8,'f32')
            elif 'ArcWeaponComponentData' in ownership:
                backend=component_backend(candidate,'ArcWeaponComponentData',4,'f32')
            else:backend=None
            fields.append(make_field('weapon.fire_rate',resolved['fire_rate'],backend,
                unique and backend is not None,blocked or (None if backend else 'No reviewed direct fire-rate backing field.')))

        capacity=candidate.get('capacity') or {}
        ammo=ammo_by_name[name]
        if 'WeaponRoundsComponentData' in ownership:
            feeds=capacity.get('feedValues') or []
            fields.append(make_field('weapon.capacity',resolved.get('capacity'),editable=False,
                reason='Derived sum of the two independently writable feed capacities.',derived=True))
            fields.append(make_field('weapon.base_capacity',capacity.get('baseValue'),editable=False,
                reason='Derived sum of the two feed capacities.',derived=True))
            for index,field_id in enumerate(('weapon.feed_capacity_1','weapon.feed_capacity_2')):
                backend=component_backend(candidate,'WeaponRoundsComponentData',72+index*4,'f32')
                fields.append(make_field(field_id,feeds[index] if index<len(feeds) else None,
                    backend,unique,blocked))
            rounds_values=ammo['fields']
            fields.append(make_field('rounds.capacity',rounds_values['capacity']['value'],editable=False,
                reason=definitions['rounds.capacity']['reason'],derived=True))
            for index,field_id in enumerate(('rounds.feed_capacity_1','rounds.feed_capacity_2')):
                backend=component_backend(candidate,'WeaponRoundsComponentData',72+index*4,'f32')
                fields.append(make_field(field_id,rounds_values['feedCapacity'+str(index+1)]['value'],
                    backend,unique,blocked))
            for field_id,key,offset in (
                    ('rounds.spare_rounds','spareRounds',80),
                    ('rounds.rounds_from_supply','roundsFromSupply',84),
                    ('rounds.starting_rounds','startingRounds',88)):
                backend=component_backend(candidate,'WeaponRoundsComponentData',offset,'u32')
                fields.append(make_field(field_id,rounds_values[key]['value'],backend,unique,blocked))
            fields.append(make_field('rounds.rounds_from_ammo_box',
                rounds_values['roundsFromAmmoBox']['value'],editable=False,
                reason=definitions['rounds.rounds_from_ammo_box']['reason'],derived=True))
        elif 'WeaponMagazineComponentData' in ownership:
            magazine_backend=component_backend(candidate,'WeaponMagazineComponentData',136,'u32')
            if capacity.get('status')=='RESOLVED':
                fields.append(make_field('weapon.capacity',capacity.get('value'),magazine_backend,unique,blocked))
            else:
                fields.append(make_field('weapon.capacity',None,editable=False,
                    reason=blocked or capacity.get('reason') or 'Effective capacity is unresolved.'))
            fields.append(make_field('weapon.base_capacity',capacity.get('baseValue'),magazine_backend,
                editable=False,reason=definitions['weapon.base_capacity']['reason']))
            custom='defaultMagazineOption'in ammo
            magazine_values=ammo['fields']
            for field_id,key,offset in (
                    ('magazine.capacity','capacity',136),
                    ('magazine.starting_magazines','startingMagazines',140),
                    ('magazine.magazines_from_supply','magazinesFromSupply',144),
                    ('magazine.spare_magazines','spareMagazines',148)):
                value=magazine_values.get(key,{}).get('value')
                if custom:
                    fields.append(make_field(field_id,value,editable=False,
                        reason='Default customization option owns the effective value; its override record is not approved for writes.'))
                else:
                    fields.append(make_field(field_id,value,
                        component_backend(candidate,'WeaponMagazineComponentData',offset,'u32'),
                        unique,blocked))
            ammo_box=magazine_values.get('magazinesFromAmmoBox',{}).get('value')
            fields.append(make_field('magazine.magazines_from_ammo_box',ammo_box,editable=False,
                reason=definitions['magazine.magazines_from_ammo_box']['reason'],derived=True))

        attacks=candidate.get('attacks') or []
        composition=composition_source['weapons'][name]
        for attack in composition['attacks']:
            backing=attack.get('targetBacking')
            if not backing:continue
            field_id='attack.'+attack['role']+'.projectile'
            backend=component_backend(candidate,backing['component'],backing['offset'],'u32')
            current={'weapon':name,'attack':attack['role'],'projectileType':attack['projectileType']}
            reason=attack.get('reason')
            field=make_field(field_id,current,backend,
                editable=unique and attack['writableReferenceSwap'],reason=blocked or reason)
            field['referenceKind']='projectile'
            field['compatibilityClass']=attack['compatibilityClass']
            field['referenceRole']=attack['role']
            field['referenceSettings']=attack['projectileSettings']
            fields.append(field)
        projectiles=[attack for attack in attacks if attack.get('kind')=='Projectile']
        for position,attack in enumerate(projectiles):
            role='primary' if position==0 else 'alternate'
            prefix='projectile' if len(projectiles)==1 else f'projectile.{role}'
            record=attack['projectileSettings'];values=attack['resolvedFields']
            if 'WeaponRoundsComponentData'in ownership:
                reference_backend=component_backend(candidate,'WeaponRoundsComponentData',
                    68 if role=='alternate'else 64,'u32')
            else:reference_backend=component_backend(candidate,'ProjectileWeaponComponentData',0,'u32')
            fields.append(make_field(prefix+'.type',attack.get('projectileType'),reference_backend,
                editable=False,reason=definitions['projectile.type']['reason']))
            for suffix,key,offset,storage in (
                ('velocity','projectile_velocity',32,'f32'),('mass','projectile_mass',36,'f32'),
                ('drag','drag',40,'f32'),('gravity','gravity',44,'f32'),
                ('pellet_count','pellet_count',28,'u32')):
                backend=settings_backend('projectile',record,offset,storage,role)
                fields.append(make_field(prefix+'.'+suffix,values.get(key),backend,unique,blocked))

        damage_attacks=[attack for attack in attacks if attack.get('damageInfo')]
        for position,attack in enumerate(damage_attacks):
            role='primary' if position==0 else 'alternate'
            prefix='damage' if len(damage_attacks)==1 else f'damage.{role}'
            record=attack['damageInfo'];values=attack['resolvedFields']
            kind=attack.get('kind')
            if kind=='Projectile':
                reference_backend=settings_backend('projectile',attack['projectileSettings'],60,'u32',role)
            elif kind=='Arc':reference_backend=settings_backend('arc',attack['arcSettings'],36,'u32',role)
            elif kind=='Beam':reference_backend=settings_backend('beam',attack['beamSettings'],12,'u32',role)
            elif kind=='Spray':reference_backend=component_backend(candidate,'SprayWeaponComponentData',200,'u32')
            elif kind=='Melee':reference_backend=component_backend(candidate,'MeleeWeaponComponentData',12,'u32')
            else:reference_backend=None
            fields.append(make_field(prefix+'.type',record['recordType'],reference_backend,editable=False,
                reason=definitions['damage.type']['reason']))
            for suffix,key,offset,storage in (
                ('standard_damage','standard_damage',4,'i32'),('durable_damage','durable_damage',8,'i32'),
                ('ap_direct','ap_direct',12,'u32'),('ap_slight','ap_slight',16,'u32'),
                ('ap_large','ap_large',20,'u32'),('ap_extreme','ap_extreme',24,'u32'),
                ('demolition','demolition',28,'u32'),('stagger','stagger',32,'u32'),
                ('push_force','push_force',36,'u32')):
                backend=settings_backend('damage',record,offset,storage,role)
                fields.append(make_field(prefix+'.'+suffix,values.get(key),backend,unique,blocked))
            status=attack.get('statusEffects')
            if isinstance(status,list):
                for index,effect in enumerate(status,1):
                    status_prefix=prefix+f'.status_{index}'
                    type_backend=settings_backend('damage',record,44+(index-1)*8,'u32',role)
                    fields.append(make_field(status_prefix+'_type',effect['type'],type_backend,editable=False,
                        reason=definitions['damage.status_type']['reason']))
                    backend=settings_backend('damage',record,44+(index-1)*8+4,'f32',role)
                    fields.append(make_field(status_prefix+'_strength',effect['strength'],backend,
                        unique,blocked))

        if 'arc_type' in resolved:
            attack=next(a for a in attacks if a.get('kind')=='Arc');record=attack['arcSettings']
            for field_id,key,offset,storage in (
                ('arc.velocity','arc_velocity',4,'f32'),('arc.range','arc_range',8,'f32'),
                ('arc.distance_at_max_spread','arc_distance_at_max_spread',12,'f32'),
                ('arc.distance_at_max_spread_first_shot','arc_distance_at_max_spread_first_shot',16,'f32'),
                ('arc.max_angle_spread','arc_max_angle_spread',20,'f32'),
                ('arc.max_angle_spread_first_shot','arc_max_angle_spread_first_shot',24,'f32'),
                ('arc.chain_count','arc_chain_count',28,'u32'),('arc.max_split','arc_max_split',32,'u32')):
                fields.append(make_field(field_id,resolved.get(key),
                    settings_backend('arc',record,offset,storage,'primary'),unique,blocked))
        if 'beam_type' in resolved:
            attack=next(a for a in attacks if a.get('kind')=='Beam');record=attack['beamSettings']
            for field_id,key,offset in (('beam.radius','beam_radius',4),('beam.length','beam_range',8)):
                fields.append(make_field(field_id,resolved.get(key),
                    settings_backend('beam',record,offset,'f32','primary'),unique,blocked))

        apply_alias_rules(fields)
        weapons.append({'name':name,'slot':identity['slot'],'category':identity.get('category'),
            'resolution':identity['resolution'],'ordinaryWritesBlocked':not unique,
            'blockReason':blocked,'resources':weapon_candidates[name],
            'implementationFamilies':candidate['implementationFamilies'],'fields':fields})

    collision_groups=0;alias_pair_instances=0;distinct_pair_instances=0;unclassified=[]
    for weapon in weapons:
        by_backing={}
        for field in weapon['fields']:
            signature=backing_signature(field)
            if signature:by_backing.setdefault(signature,[]).append(field)
        for signature,fields in by_backing.items():
            if len(fields)<2:continue
            collision_groups+=1
            for left,right in combinations(fields,2):
                if left['semanticTarget']==right['semanticTarget']:
                    if left.get('aliasOf')==right['semanticFieldId'] or right.get('aliasOf')==left['semanticFieldId']:
                        alias_pair_instances+=1
                    else:
                        unclassified.append({'weapon':weapon['name'],'fields':sorted(
                            (left['semanticFieldId'],right['semanticFieldId']))})
                else:distinct_pair_instances+=1
    assert not unclassified, 'Unclassified identical-backing semantic fields: '+repr(unclassified)
    semantic_aliases=[]
    for rule in alias_rules:
        key=(rule['alias'],rule['canonical'])
        semantic_aliases.append({**rule,'instanceCount':alias_instance_counts[key],
            'writeAcceptedInstanceCount':alias_write_counts[key]})
    collision_audit={'fieldInstancesAudited':sum(len(w['fields'])for w in weapons),
        'exactBackingCollisionGroups':collision_groups,'aliasPairInstances':alias_pair_instances,
        'distinctSemanticPairInstances':distinct_pair_instances,'unclassifiedCollisionPairs':0,
        'distinctSemanticExample':{'fields':['weapon.base_capacity','magazine.capacity'],
            'reason':'Underlying base capacity is a read-only native view; effective magazine capacity is a separate semantic target.'}}

    family_coverage={}
    for weapon in weapons:
        for family in weapon['implementationFamilies']:
            item=family_coverage.setdefault(family,{'weapons':0,'weaponsWithWritableFields':0,
                'weaponsWithProjectileOrDamageWrites':0})
            item['weapons']+=1
            if any(field['editable']for field in weapon['fields']):item['weaponsWithWritableFields']+=1
            if any(field['editable']and(field['semanticFieldId'].startswith('projectile.')or
                    field['semanticFieldId'].startswith('damage.'))for field in weapon['fields']):
                item['weaponsWithProjectileOrDamageWrites']+=1
    summary={'weapons':len(weapons),'uniqueWeapons':sum(not w['ordinaryWritesBlocked'] for w in weapons),
        'duplicateWeapons':sum(w['ordinaryWritesBlocked'] for w in weapons),
        'semanticFieldDefinitions':len(definitions),
        'writableSemanticFieldDefinitions':sum(item['writable']for item in definitions.values()),
        'readOnlySemanticFieldDefinitions':sum(not item['writable']for item in definitions.values()),
        'derivedSemanticFieldDefinitions':sum(item['derived']for item in definitions.values()),
        'fieldInstances':sum(len(w['fields'])for w in weapons),
        'writableFieldInstances':sum(sum(field['editable']for field in w['fields'])for w in weapons),
        'weaponsWithWritableFields':sum(any(f['editable'] for f in w['fields']) for w in weapons),
        'weaponsWithProjectileDamageWrites':sum(any(f['editable'] and
            (f['semanticFieldId'].startswith('projectile.') or f['semanticFieldId'].startswith('damage.'))
            for f in w['fields']) for w in weapons),
        'weaponsRestrictedToWeaponLevelWrites':sum(any(f['editable']for f in w['fields'])and not any(
            f['editable']and not f['semanticFieldId'].startswith('weapon.')for f in w['fields'])for w in weapons),
        'semanticAliasRules':len(semantic_aliases),'semanticAliasInstances':alias_pair_instances,
        'familyCoverage':family_coverage}
    summary['ammo']=ammo_source['summary']
    summary['composition']=composition_source['summary']
    return {'schemaVersion':schema['schema_version'],'hd2RuntimeVersion':VERSION_FILE.read_text().strip(),
        'buildFingerprints':report['gameFingerprints'],'sourceSnapshot':
            'F5FEE03DCFDB-20260926T222226Z.hd2snap','summary':summary,
        'fieldDefinitions':schema['fields'],'semanticAliases':semantic_aliases,
        'backingCollisionAudit':collision_audit,'weapons':weapons,
        'safety':{'addressesInPublicMetadata':False,'writes':0,'protectionChanges':0,
            'fixtureFallback':'disabled'}}


def outputs(catalog_path=CATALOG):
    value=build(catalog_path)
    ammo_source=json.loads(AMMO_CATALOG.read_text())
    constants={}
    for weapon in value['weapons']:
        for field in weapon['fields']:
            field_id=field['semanticFieldId'];domain=field_id.split('.')[0]
            key=field_id[len(domain)+1:].replace('.','_')
            constants.setdefault(domain,{})[key]=field_id
    constants.setdefault('attack',{})['projectile']='attack.projectile'
    constants.setdefault('terminal',{})['explosion']='terminal.explosion'
    runtime={'version':value['hd2RuntimeVersion'],'weapons':{w['name']:w for w in value['weapons']},
        'summary':value['summary'],'fields':constants,'semanticAliases':value['semanticAliases'],
        'backingCollisionAudit':value['backingCollisionAudit']}
    ammo={'schemaVersion':1,'hd2RuntimeVersion':value['hd2RuntimeVersion'],
        'buildFingerprints':value['buildFingerprints'],'sourceSnapshot':value['sourceSnapshot'],
        'summary':value['summary']['ammo'],'fieldLayout':ammo_source['fieldLayout'],
        'ownershipFindings':ammo_source['ownershipFindings'],
        'evidenceCounts':ammo_source['evidenceCounts'],
        'nativeMagazineOptions':ammo_source['nativeMagazineOptions'],
        'discrepancies':ammo_source['discrepancies'],
        'weapons':ammo_source['weapons'],
        'safety':value['safety']}
    return {JSON_OUTPUT:json.dumps(value,indent=2)+'\n',
        AMMO_JSON_OUTPUT:json.dumps(ammo,indent=2)+'\n',
        LUA_OUTPUT:'-- Generated from schemas/player_weapon_fields.json and reviewed snapshot output; do not edit.\nreturn '+lua(runtime)+'\n'}


def generate(check=False,catalog_path=CATALOG):
    stale=[]
    for path,body in outputs(catalog_path).items():
        if not path.exists() or path.read_text()!=body:
            stale.append(path)
            if not check:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
    if check and stale:raise RuntimeError('Stale weapon authoring outputs: '+', '.join(str(p) for p in stale))
    return stale


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true');parser.add_argument('--catalog',type=Path,default=CATALOG)
    parser.add_argument('--refresh-catalog',action='store_true')
    parser.add_argument('--report',type=Path,default=DEFAULT_REPORT)
    parser.add_argument('--identities',type=Path,default=DEFAULT_IDENTITIES)
    args=parser.parse_args()
    if args.refresh_catalog:refresh_catalog(args.report,args.identities,args.catalog)
    print('\n'.join(str(p) for p in generate(args.check,args.catalog)) or'up to date')
