"""Generate guarded support-weapon authoring metadata from retained snapshot evidence."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import support_callin_linkage

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'schemas/support_weapon_authoring_catalog.json'
FIELDS=ROOT/'schemas/player_weapon_fields.json'
LEGACY=ROOT/'research/support-weapon-runtime-F5FEE03DCFDB.json'
JSON_OUTPUT=ROOT/'sdk/SupportWeaponAuthoringCapabilities.json'
LUA_OUTPUT=ROOT/'domains/support_weapon_authoring.lua'


BACKING_TYPES={
    'projectile':'ProjectileSettings',
    'damage':'DamageInfo',
    'explosion_damage':'DamageInfo',
    'explosion':'ExplosionSettings',
    'arc':'ArcSettings',
    'beam':'BeamSettings',
    'status':'StatusEffectSettings',
}


def digest(value,length=20):
    encoded=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(encoded).hexdigest()[:length]


def slug(value):
    return re.sub(r'[^a-z0-9]+','-',str(value).lower()).strip('-')or'root'


def weapon_key(name):
    return support_callin_linkage.support_weapon_key(name)


def backing_identity(backing):
    if backing['kind']=='component':
        return ('component',backing['component'],backing['recordIndex'],backing['indexRow'])
    semantic_type=BACKING_TYPES[backing['settings']]
    return ('settings',semantic_type,backing['settingsType'],backing['group'],
        backing['row'],backing['recordType'])


def backing_object_key(backing):
    semantic_type=(backing['component']if backing['kind']=='component'
        else BACKING_TYPES[backing['settings']])
    return 'support-object/v1/'+slug(semantic_type)+'/'+digest(backing_identity(backing))


def canonical_public_field_id(qualified):
    parts=qualified.split('.')
    if parts[0]in('projectile','damage','arc','beam','status')and len(parts)>2:
        return parts[0]+'.'+'.'.join(parts[2:])
    if parts[0]=='explosion'and len(parts)>2:
        return 'explosion.'+'.'.join(parts[2:])
    return qualified


def descriptor_instance_key(weapon_name,field,public_field_id=None):
    public_field_id=public_field_id or canonical_public_field_id(field['semanticFieldId'])
    target=field['target']
    identity={'weapon':weapon_name,'path':target['path'],'attack':target.get('attack'),
        'qualifiedField':field['semanticFieldId'],'field':public_field_id,
        'object':backing_object_key(field['backing'])}
    readable='/'.join((slug(weapon_name),slug(target['path']),
        slug(target.get('attack')or'root'),slug(public_field_id)))
    return 'support-field/v1/'+readable+'/'+digest(identity,16)


def audit_instance_coverage(runtime,public):
    expected=[descriptor_instance_key(name,field)
        for name,weapon in runtime['weapons'].items()for field in weapon['fields']]
    published=[field['instanceKey']for field in public['fieldInstances']]
    assert len(expected)==len(set(expected)),'internal support field instance keys are not unique'
    assert len(published)==len(set(published)),'published support field instance keys are not unique'
    assert set(expected)==set(published),'published support field instance identity coverage diverged'
    return {'internalInstances':len(expected),'publishedInstances':len(published),
        'missingInstances':len(set(expected)-set(published)),
        'unexpectedInstances':len(set(published)-set(expected)),
        'identityCoverage':'exact'}


def lua(value):
    if isinstance(value,dict):
        return '{'+','.join('['+lua(k)+']='+lua(v) for k,v in sorted(value.items()))+'}'
    if isinstance(value,list):return '{'+','.join(lua(item) for item in value)+'}'
    if isinstance(value,bool):return'true'if value else'false'
    if value is None:return'nil'
    if isinstance(value,(int,float)):return repr(value)
    return json.dumps(str(value),ensure_ascii=False)


def refresh_catalog(base_path,legacy_path=LEGACY,catalog_path=CATALOG):
    base=json.loads(Path(base_path).read_text());legacy=json.loads(Path(legacy_path).read_text())
    runtime={item['resourceHash']:item for item in base['runtimeCandidates']}
    explosive={item['resourceHash']:item for item in base['supportGraph']['explosiveEntities']}
    racks={item['resourceHash']:item for item in base['supportGraph']['hellpodRacks']}
    weapons=[];candidates={}
    for weapon in legacy['weapons']:
        resources=weapon['resourceHashes'];attack_resource=weapon.get('attackOwnerResourceHash')
        for resource in resources:
            if resource in runtime:
                item=runtime[resource]
                candidates[resource]={'resourceHash':resource,'ownership':item['ownership'],
                    'resolvedFields':{key:value['value'] for key,value in item['resolvedFields'].items()},
                    'ammo':item.get('ammo'),'attacks':item.get('attacks') or [],
                    'chargeCadence':item.get('chargeCadence'),
                    'implementationFamilies':item.get('implementationFamilies') or []}
        if attack_resource and attack_resource in explosive:
            item=explosive[attack_resource]
            candidates[attack_resource]={'resourceHash':attack_resource,'ownership':item['ownership'],
                'resolvedFields':{},'ammo':None,'attacks':item['attacks'],'chargeCadence':None,
                'implementationFamilies':['placed_explosive']}
        root_chain=[]
        for node in weapon.get('ownershipChain') or []:
            clean={key:node.get(key) for key in ('kind','resourceHash','component','recordKind','id','package')
                   if node.get(key)is not None}
            root_chain.append(clean)
        fire=weapon.get('fireRateDiagnostics') or []
        weapons.append({'name':weapon['catalogIdentity'],'resolution':weapon['identityResolution'],
            'confidence':weapon['confidence'],'resources':resources,
            'canonicalResource':weapon.get('canonicalResourceHash'),
            'attackResource':attack_resource or weapon.get('canonicalResourceHash'),
            'ownershipChain':root_chain,'attackGraph':weapon['attackGraph'],
            'unresolvedLinks':weapon.get('unresolvedLinks') or [],
            'backpackDependent':weapon['backpackDependent'],
            'linkedAmmoOwned':any(item.get('weaponLinkedAmmoComponentOwned')
                for item in weapon.get('ammoFeedMagazine') or []),
            'fireRateDiagnosticOnly':bool(fire and fire[0].get('diagnosticOnly')),
            'sourceSection':weapon.get('sourceSection'),'weaponType':weapon.get('weaponType'),
            'rootRack':next((rack for rack in base['supportGraph']['hellpodRacks']
                if rack['resourceHash']==weapon.get('canonicalResourceHash')),None)})
    value={'schemaVersion':1,'sourceSnapshot':'F5FEE03DCFDB-20260926T222226Z.hd2snap',
        'gameFingerprints':base['gameFingerprints'],'safety':{'writes':0,'protectionChanges':0,
            'fixtureFallback':'disabled','mode':'snapshot'},'candidates':candidates,'weapons':weapons}
    Path(catalog_path).write_text(json.dumps(value,indent=2)+'\n')


def build(catalog_path=CATALOG):
    source=json.loads(Path(catalog_path).read_text())
    schema=json.loads(FIELDS.read_text());definitions={item['id']:item for item in schema['fields']}
    candidates=source['candidates'];weapon_names={item['name'] for item in source['weapons']}
    assert len(source['weapons'])==35 and len(weapon_names)==35
    call_in_linkage=support_callin_linkage.build()
    assert set(call_in_linkage['supportWeapons'])==weapon_names,'call-in linkage weapon coverage diverged'
    consumers=defaultdict(set)
    for weapon in source['weapons']:
        for resource in weapon['resources']:
            candidate=candidates.get(resource)
            if not candidate:continue
            for attack in candidate['attacks']:
                for key,kind in (('projectileSettings','projectile'),('damageInfo','damage'),
                        ('explosionSettings','explosion'),('arcSettings','arc'),
                        ('beamSettings','beam'),('statusSettings','status')):
                    record=attack.get(key)
                    if record:consumers[(kind,record['settingsType'],record['group'],record['row'],
                        record['recordType'])].add(weapon['name'])

    def definition(field_id):
        parts=field_id.split('.')
        if parts[0]in('projectile','damage','arc','beam','status')and len(parts)>2:
            return definitions[parts[0]+'.'+'.'.join(parts[2:])]
        if parts[0]=='explosion'and len(parts)>2:
            return definitions['explosion.'+'.'.join(parts[2:])]
        return definitions[field_id]

    def component(candidate,name,offset,storage):
        owner=candidate['ownership'][name]
        return {'kind':'component','component':name,'offset':offset,'storage':storage,
            'width':1 if storage=='u8'else 4,'recordIndex':owner['recordIndex'],
            'indexRow':owner['indexRow'],'ownerCount':owner['ownerCount'],
            'uniqueOwner':owner['uniqueOwner']}

    def settings(kind,record,offset,storage,role,linkage,**extra):
        result={'kind':'settings','settings':kind,'offset':offset,'storage':storage,'width':4,
            'group':record['group'],'row':record['row'],'recordType':record['recordType'],
            'settingsType':record['settingsType'],'branch':role,'linkage':linkage}
        result.update(extra);return result

    def make_field(field_id,current,backing,target,editable=True,reason=None):
        spec=definition(field_id);shared=[];affects=False
        if backing['kind']=='component':affects=backing.get('ownerCount',1)>1
        else:
            key=(backing['settings'],backing['settingsType'],backing['group'],backing['row'],
                backing['recordType']);shared=sorted(consumers[key]-{target['weapon']});affects=True
        return {'semanticFieldId':field_id,'semanticTarget':spec.get('semantic_target',spec['id']),
            'displayName':spec['display_name'],'type':spec['type'],'unit':spec.get('unit'),
            'currentDefault':current,'editable':editable,'acceptedForWrites':editable,
            'derivedReadOnly':spec.get('derived',False),'backing':backing,'target':target,
            'writeScope':('shared_'+backing.get('settings','component') if affects else'weapon_local'),
            'sharedWithWeapons':shared,'affectsMultipleWeapons':affects,
            'dynamicConsumersPossible':backing['kind']=='settings','reason':reason}

    def damage_fields(fields,candidate,attack,target,role,linkage,extra=None,prefix='damage'):
        record=attack['damageInfo'];values=attack['resolvedFields'];extra=extra or{}
        for suffix,key,offset,storage in (
            ('standard_damage','standard_damage',4,'i32'),('durable_damage','durable_damage',8,'i32'),
            ('ap_direct','ap_direct',12,'u32'),('ap_slight','ap_slight',16,'u32'),
            ('ap_large','ap_large',20,'u32'),('ap_extreme','ap_extreme',24,'u32'),
            ('demolition','demolition',28,'u32'),('stagger','stagger',32,'u32'),
            ('push_force','push_force',36,'u32')):
            field_id=('explosion.'+role+'.damage.'+suffix if prefix=='explosion'
                else prefix+'.'+role+'.'+suffix)
            fields.append(make_field(field_id,values.get(key),
                settings('explosion_damage'if prefix=='explosion'else'damage',record,
                    offset,storage,role,linkage,**extra),target))

    runtime_weapons={};public_weapons=[]
    for weapon in source['weapons']:
        unique=weapon['resolution']=='UNIQUE';block=None if unique else(
            'Duplicate runtime roots remain after downstream graph audit; no root is selected heuristically.')
        candidate=candidates.get(weapon['attackResource']) or(
            candidates.get(weapon['canonicalResource']) if weapon['canonicalResource'] else None)
        fields=[];attacks={};blocked=[]
        resolved_roles={branch.get('runtimeMatch',{}).get('runtimeAttackRole')
            for branch in weapon['attackGraph']if branch.get('state')=='RESOLVED'}
        if not unique:
            blocked.append({'field':'ordinary writes','reason':block})
            if weapon['name']=='LAS-98 Laser Cannon':
                blocked.extend((
                    {'field':'heat.* / heatsink.*','reason':
                        'WeaponHeatComponentData is present on the reviewed runtime candidates, but three duplicate weapon roots remain.'},
                    {'field':'beam.* / damage.*','reason':
                        'BeamSettings and linked DamageInfo are structurally proven, but their owning LAS-98 root remains ambiguous.'}))
        if candidate and unique:
            resolved=candidate['resolvedFields'];ownership=candidate['ownership']
            target={'resource':'support_weapon','path':'weapon','weapon':weapon['name']}
            for field_id,key,offset,storage in (
                ('weapon.ergonomics','ergonomics',356,'f32'),('weapon.sway','sway',104,'f32'),
                ('weapon.horizontal_spread','spread_horizontal',84,'f32'),
                ('weapon.vertical_spread','spread_vertical',88,'f32'),
                ('weapon.recoil_drift_horizontal','recoil_drift_horizontal',0,'f32'),
                ('weapon.recoil_drift_vertical','recoil_drift_vertical',4,'f32'),
                ('weapon.recoil_climb_horizontal','recoil_climb_horizontal',28,'f32'),
                ('weapon.recoil_climb_vertical','recoil_climb_vertical',32,'f32')):
                if key in resolved and'WeaponDataComponentData'in ownership:
                    fields.append(make_field(field_id,resolved[key],
                        component(candidate,'WeaponDataComponentData',offset,storage),target))
            if 'ProjectileWeaponComponentData'in ownership and not weapon['fireRateDiagnosticOnly']:
                fields.append(make_field('weapon.fire_rate',resolved['fire_rate'],
                    component(candidate,'ProjectileWeaponComponentData',8,'f32'),target))
            elif weapon['fireRateDiagnosticOnly']:
                blocked.append({'field':'weapon.fire_rate','reason':
                    'Charge-controlled or diagnostic selector; native sentinel/default is not exposed as ordinary RPM.'})
            ammo=candidate.get('ammo')or{};kind=ammo.get('kind')
            if kind=='magazine'and'WeaponMagazineComponentData'in ownership:
                for field_id,key,offset in (
                    ('weapon.capacity','capacity_value',136),
                    ('magazine.starting_magazines','starting_magazines',140),
                    ('magazine.magazines_from_supply','magazines_from_supply',144),
                    ('magazine.spare_magazines','spare_magazines',148)):
                    fields.append(make_field(field_id,ammo.get(key),
                        component(candidate,'WeaponMagazineComponentData',offset,'u32'),target))
            elif kind=='rounds'and'WeaponRoundsComponentData'in ownership:
                for field_id,key,offset,storage in (
                    ('rounds.feed_capacity_1','feed_capacity_1',72,'f32'),
                    ('rounds.feed_capacity_2','feed_capacity_2',76,'f32'),
                    ('rounds.spare_rounds','spare_rounds',80,'u32'),
                    ('rounds.rounds_from_supply','rounds_from_supply',84,'u32'),
                    ('rounds.starting_rounds','starting_rounds',88,'u32')):
                    fields.append(make_field(field_id,ammo.get(key),
                        component(candidate,'WeaponRoundsComponentData',offset,storage),target))
            charge=candidate.get('chargeCadence')
            if charge and'WeaponChargeComponentData'in ownership:
                for field_id,value,offset in (
                    ('charge.level_1',charge['levels'][0],0),('charge.level_2',charge['levels'][1],24),
                    ('charge.level_3',charge['levels'][2],48),
                    ('charge.minimum_seconds',charge['minimumSeconds'],72),
                    ('charge.maximum_seconds',charge['maximumSeconds'],76)):
                    fields.append(make_field(field_id,value,
                        component(candidate,'WeaponChargeComponentData',offset,'f32'),target))
            if 'WeaponHeatComponentData'in ownership:
                for field_id,key,offset,storage in (
                    ('heat.capacity','heat_capacity',96,'f32'),('heat.heat_per_shot','heat_per_shot',116,'f32'),
                    ('heat.heat_per_second','heat_per_second',120,'f32'),
                    ('heat.cool_per_second','heat_cool_per_second',128,'f32'),
                    ('heatsink.starting','heatsink_starting',84,'u32'),
                    ('heatsink.from_supply','heatsink_from_supply',88,'u32'),
                    ('heatsink.spare','heatsink_spare',92,'u32')):
                    if key in resolved:fields.append(make_field(field_id,resolved[key],
                        component(candidate,'WeaponHeatComponentData',offset,storage),target))

            for attack in candidate['attacks']:
                role=attack['role'];kind=attack['kind']
                if role not in resolved_roles:continue
                target_path={'Projectile':'projectile_reference','Explosion':'explosion'}.get(kind,'attack')
                attack_target={'resource':'support_weapon','path':target_path,'weapon':weapon['name'],'attack':role}
                attacks[role]={'role':role,'kind':kind,'parentRole':attack.get('parentRole'),
                    'targetPath':target_path}
                if kind=='Projectile':
                    record=attack['projectileSettings'];values=attack['resolvedFields']
                    for suffix,key,offset,storage in (
                        ('velocity','projectile_velocity',32,'f32'),('mass','projectile_mass',36,'f32'),
                        ('drag','drag',40,'f32'),('gravity','gravity',44,'f32'),
                        ('pellet_count','pellet_count',28,'u32')):
                        fields.append(make_field('projectile.'+role+'.'+suffix,values.get(key),
                            settings('projectile',record,offset,storage,role,'projectile'),attack_target))
                    damage_fields(fields,candidate,attack,attack_target,role,'projectile_damage')
                    blocked.extend({'attack':role,'field':name,'reason':'No shared schema-labelled native field is proven.'}
                        for name in ('projectile.lifetime','projectile.penetration_slowdown'))
                elif kind in('Arc','Beam'):
                    settings_name=kind.lower();record=attack[settings_name+'Settings']
                    values=candidate['resolvedFields']if kind=='Beam'else attack['resolvedFields']
                    layout=(
                        (('velocity','arc_velocity',4,'f32'),('range','arc_range',8,'f32'),
                         ('distance_at_max_spread','arc_spread',12,'f32'),
                         ('max_angle_spread','arc_chain_spread',20,'f32'),
                         ('chain_count','arc_chain_count',28,'u32'),('max_split','arc_max_split',32,'u32'))
                        if kind=='Arc'else(('radius','beam_radius',4,'f32'),('length','beam_range',8,'f32')))
                    for suffix,key,offset,storage in layout:
                        fields.append(make_field(settings_name+'.'+role+'.'+suffix,values.get(key),
                            settings(settings_name,record,offset,storage,role,settings_name),attack_target))
                    damage_fields(fields,candidate,attack,attack_target,role,settings_name+'_damage')
                elif kind in('Spray','Melee'):
                    damage_fields(fields,candidate,attack,attack_target,role,kind.lower()+'_damage')
                elif kind=='Explosion':
                    standalone='ExplosiveComponentData'in ownership
                    parent=attack.get('parentRole');phase='impact' if role.endswith('impact')else'detonation'
                    linkage='explosive_explosion'if standalone else'projectile_explosion'
                    extra={'selectorOffset':40 if role=='impact'and standalone else 36}if standalone else{
                        'parentRole':parent,'phase':'expiry'if role.endswith('expiry')else'impact'}
                    record=attack['explosionSettings'];values=attack['resolvedFields']
                    for suffix,key,offset in (('inner_radius','explosion_inner_radius',16),
                            ('outer_radius','explosion_outer_radius',20),
                            ('shockwave_radius','explosion_shockwave_radius',24)):
                        fields.append(make_field('explosion.'+role+'.'+suffix,values.get(key),
                            settings('explosion',record,offset,'f32',role,linkage,**extra),attack_target))
                    damage_fields(fields,candidate,attack,attack_target,role,linkage+'_damage',extra,
                        prefix='explosion')
                elif kind=='Status':
                    parent=next((item for item in candidate['attacks'] if item['role']==attack.get('parentRole')),None)
                    if parent and parent.get('damageInfo'):
                        effects=parent.get('statusEffects')or[]
                        index=next((i for i,item in enumerate(effects)if item['type']==attack['statusType']),None)
                        status_extra={'parentRole':parent['role']}
                        if parent['kind']=='Explosion':
                            standalone='ExplosiveComponentData'in ownership
                            parent_linkage='explosive_explosion_damage'if standalone else'projectile_explosion_damage'
                            if standalone:status_extra['selectorOffset']=40 if parent['role']=='impact'else 36
                            else:
                                status_extra['parentRole']=parent.get('parentRole')
                                status_extra['phase']='expiry'if parent['role'].endswith('expiry')else'impact'
                        else:parent_linkage=parent['kind'].lower()+'_damage'
                        if index is not None:
                            fields.append(make_field('status.'+role+'.strength',
                                attack['resolvedFields']['status_strength'],settings('damage',parent['damageInfo'],
                                48+index*8,'f32',role,parent_linkage,**status_extra),attack_target))
                    fields.append(make_field('status.'+role+'.duration',attack['resolvedFields']['status_duration'],
                        settings('status',attack['statusSettings'],40,'f32',role,'status',
                            statusType=attack['statusType'],
                            parentLinkage=parent_linkage if parent and parent.get('damageInfo')else None,
                            **(status_extra if parent and parent.get('damageInfo')else{})),attack_target))
        if weapon['backpackDependent']:
            blocked.append({'field':'backpack storage','reason':
                'Backpack entity/package storage ownership is unresolved; weapon-side fields remain independent.'})
        if weapon['linkedAmmoOwned']:
            blocked.append({'field':'linked backpack ammo','reason':
                'WeaponLinkedAmmo ownership is classified, but storage semantics are not proven.'})
        if weapon['ownershipChain']and any(x['kind']=='stratagem_payload'for x in weapon['ownershipChain']):
            blocked.append({'field':'linked stratagem scalars','reason':
                'Cooldown and uses are owned by the linked stratagem view (linkedStratagem.semanticId); '
                'call-in scalar ownership through the support weapon is not reviewed.'})
        for reason in weapon['unresolvedLinks']:blocked.append({'field':'unresolved branch','reason':reason})

        runtime_weapons[weapon['name']]={'name':weapon['name'],'resolution':weapon['resolution'],
            'supportWeapon':True,
            'ordinaryWritesBlocked':not unique,'blockReason':block,'resources':weapon['resources'],
            'identityResource':weapon['canonicalResource'],'attackResource':weapon['attackResource'],
            'ownershipChain':weapon['ownershipChain'],'rootRack':weapon.get('rootRack'),
            'fields':fields,'attacks':attacks}
        categorized=defaultdict(list)
        for field in fields:
            generic=definition(field['semanticFieldId'])['id'];categorized[generic.split('.')[0]].append(generic)
        for key in categorized:categorized[key]=sorted(set(categorized[key]))
        public_branches=[]
        for branch in weapon['attackGraph']:
            runtime_role=(branch.get('runtimeMatch')or{}).get('runtimeAttackRole')
            public_branches.append({'name':branch['name'],'kind':branch['kind'],
                'parentAttack':branch.get('parentAttack'),'runtimeRole':runtime_role,
                'state':branch['state'],'writable':unique and branch['state']=='RESOLVED'
                    and runtime_role in attacks,
                'blockedReason':block if not unique else branch.get('unresolvedReason')})
        public_weapons.append({'name':weapon['name'],'semanticId':weapon_key(weapon['name']),
            'identityStatus':weapon['resolution'],
            'confidence':weapon['confidence'],'family':sorted(set(
                branch['kind'] for branch in weapon['attackGraph'] if branch['kind']!='Unknown')),
            'attackBranches':public_branches,
            'writableFieldsByDomain':dict(sorted(categorized.items())),
            'sharedScopes':sorted(set(f['writeScope']for f in fields if f['affectsMultipleWeapons'])),
            'blockedFields':blocked,'backpackDependency':weapon['backpackDependent'],
            'linkedAmmoOwnership':weapon['linkedAmmoOwned'],
            'linkedStratagem':call_in_linkage['supportWeapons'][weapon['name']],
            'writable':unique and bool(fields),'writableFieldCount':len(fields)if unique else 0})

    # Build the canonical public instance/object model only after every internal
    # descriptor exists. Raw native record coordinates are used solely to join
    # evidence here; public keys are opaque semantic digests and expose none of
    # those coordinates.
    source_weapons={weapon['name']:weapon for weapon in source['weapons']}
    public_weapon_by_name={weapon['name']:weapon for weapon in public_weapons}
    reviewed_consumers=defaultdict(dict)

    def branch_aliases(weapon_name,role):
        weapon=source_weapons[weapon_name]
        return [{'name':branch['name'],'kind':branch['kind'],'state':branch['state']}
            for branch in weapon['attackGraph']
            if (branch.get('runtimeMatch')or{}).get('runtimeAttackRole')==role]

    def semantic_consumer(weapon_name,path,role=None,kind=None,parent_role=None):
        aliases=branch_aliases(weapon_name,role)if role else[]
        value={'weapon':weapon_name,'targetPath':path,'attackRole':role,
            'attackKind':kind,'parentAttackRole':parent_role,
            'catalogBranches':aliases,
            'writableCatalogBranches':[branch for branch in aliases if branch['state']=='RESOLVED']}
        value['consumerKey']='support-consumer/v1/'+slug(weapon_name)+'/'+slug(path)+'/'+slug(role or'root')+'/'+digest(value,16)
        return value

    def register_consumer(backing,consumer):
        reviewed_consumers[backing_object_key(backing)][consumer['consumerKey']]=consumer

    def record_backing(settings_name,record):
        return {'kind':'settings','settings':settings_name,'settingsType':record['settingsType'],
            'group':record['group'],'row':record['row'],'recordType':record['recordType']}

    for weapon in source['weapons']:
        resources=list(weapon['resources'])
        if weapon.get('attackResource')and weapon['attackResource']not in resources:
            resources.append(weapon['attackResource'])
        for resource in resources:
            candidate=candidates.get(resource)
            if not candidate:continue
            for component_name,owner in candidate['ownership'].items():
                register_consumer({'kind':'component','component':component_name,
                    'recordIndex':owner['recordIndex'],'indexRow':owner['indexRow']},
                    semantic_consumer(weapon['name'],'weapon'))
            for attack in candidate['attacks']:
                role=attack['role'];kind=attack['kind'];parent=attack.get('parentRole')
                if attack.get('projectileSettings'):
                    register_consumer(record_backing('projectile',attack['projectileSettings']),
                        semantic_consumer(weapon['name'],'projectile_reference',role,kind,parent))
                if attack.get('damageInfo'):
                    path=('projectile_reference'if kind=='Projectile'else
                        'explosion'if kind=='Explosion'else'attack')
                    register_consumer(record_backing('damage',attack['damageInfo']),
                        semantic_consumer(weapon['name'],path,role,kind,parent))
                for record_name,settings_name,path in (
                        ('explosionSettings','explosion','explosion'),
                        ('arcSettings','arc','attack'),('beamSettings','beam','attack'),
                        ('statusSettings','status','attack')):
                    record=attack.get(record_name)
                    if record:register_consumer(record_backing(settings_name,record),
                        semantic_consumer(weapon['name'],path,role,kind,parent))

    for weapon_name,weapon in runtime_weapons.items():
        for field in weapon['fields']:
            target=field['target'];role=target.get('attack');attack=weapon['attacks'].get(role)or{}
            register_consumer(field['backing'],semantic_consumer(weapon_name,target['path'],role,
                attack.get('kind'),attack.get('parentRole')))

    sdk_schema=json.loads((ROOT/'schemas/sdk.json').read_text())
    api_constants=defaultdict(dict)
    for resource in sdk_schema['resources'].values():
        for name,field in resource['fields'].items():
            api_constants[field['domain']][name.replace('.','_')]=name
    for field_id in sorted(definitions):
        domain,name=field_id.split('.',1);constant=name.replace('.','_')
        if constant in api_constants[domain]and api_constants[domain][constant]!=field_id:
            constant='player_'+constant
        api_constants[domain][constant]=field_id

    def api_constant(field_id):
        domain=field_id.split('.',1)[0]
        constant=next(name for name,value in api_constants[domain].items()if value==field_id)
        return 'hd2.fields.'+domain+'.'+constant

    object_fields=defaultdict(list)
    for weapon_name,weapon in runtime_weapons.items():
        for field in weapon['fields']:
            object_fields[backing_object_key(field['backing'])].append((weapon_name,field))

    backing_objects={}
    for object_key,entries in object_fields.items():
        backing=entries[0][1]['backing'];consumers=sorted(
            reviewed_consumers[object_key].values(),key=lambda item:item['consumerKey'])
        requires_shared=any(field['affectsMultipleWeapons']for _,field in entries)
        scope_key='support-scope/v1/'+digest({'object':object_key,
            'consumers':[item['consumerKey']for item in consumers]},20)
        semantic_type=(backing['component']if backing['kind']=='component'
            else BACKING_TYPES[backing['settings']])
        backing_objects[object_key]={'objectKey':object_key,'kind':backing['kind'],
            'semanticType':semantic_type,
            'domains':sorted(set(definition(field['semanticFieldId'])['id'].split('.')[0]
                for _,field in entries)),
            'shared':requires_shared,'requiresSharedAcknowledgement':requires_shared,
            'sharedScopeKey':scope_key,'reviewedConsumerCount':len(consumers),
            'affectedSemanticConsumers':consumers,'reviewedScopeComplete':True,
            'dynamicConsumersPossible':any(field['dynamicConsumersPossible']for _,field in entries),
            'fieldInstanceKeys':[]}

    def find_parent_object(weapon_name,field):
        backing=field['backing'];linkage=backing.get('linkage')or''
        fields=runtime_weapons[weapon_name]['fields'];target=field['target']
        wanted=None;role=target.get('attack')
        if backing.get('settings')=='status':
            for candidate in fields:
                if candidate['target']==target and candidate['backing'].get('settings')in(
                        'damage','explosion_damage'):
                    return backing_object_key(candidate['backing'])
            return None
        if linkage in('projectile_damage','projectile_explosion'):
            wanted='projectile'
            role=backing.get('parentRole')or role
        elif linkage in('arc_damage','beam_damage'):
            wanted=linkage.split('_',1)[0]
            role=backing.get('parentRole')or role
        elif linkage.endswith('explosion_damage'):
            wanted='explosion'
        if not wanted:return None
        for candidate in fields:
            candidate_backing=candidate['backing']
            if candidate_backing.get('settings')==wanted and candidate['target'].get('attack')==role:
                return backing_object_key(candidate_backing)
        return None

    def resolution_metadata(weapon_name,field):
        backing=field['backing'];linkage=backing.get('linkage')
        source_weapon=source_weapons[weapon_name]
        root_chain=[node['kind']for node in source_weapon.get('ownershipChain')or[]]
        parent=find_parent_object(weapon_name,field)
        return {'rootChain':root_chain or['weapon_entity'],
            'linkage':linkage or'owned_component','parentObjectKey':parent,
            'terminalPhase':backing.get('phase'),
            'planPhase':1,'planDependencies':[],
            'requiresLaterPlanPhase':False,'targetFrom':None}

    instances=[];operation_groups=defaultdict(list)
    for weapon_name,weapon in runtime_weapons.items():
        public_weapon=public_weapon_by_name[weapon_name];public_weapon['fieldInstanceKeys']=[]
        for field in weapon['fields']:
            field_id=definition(field['semanticFieldId'])['id'];target=field['target']
            role=target.get('attack');attack=weapon['attacks'].get(role)or{}
            object_key=backing_object_key(field['backing']);object_meta=backing_objects[object_key]
            instance_key=descriptor_instance_key(weapon_name,field,field_id)
            backing_scope=(field['backing']['kind']+':'
                +(field['backing'].get('settings')or field['backing'].get('component')))
            target_identity={'weapon':weapon_name,'targetPath':target['path'],'attackRole':role}
            operation_key='support-operation/v1/'+digest({'object':object_key,
                'scope':backing_scope,'target':target_identity},20)
            plan_key='support-plan/v1/'+slug(weapon_name)+'/'+digest(weapon_name,12)
            consumers=object_meta['affectedSemanticConsumers']
            reference=None
            if field['type'].endswith('_reference'):
                reference={'expectedSemanticReference':field['currentDefault'],
                    'sourceClass':field['type'],'typedIdentityOnly':True}
            accessor=['support_weapon']
            if target['path']!='weapon':
                accessor.append('attack')
                if target['path']=='projectile_reference':accessor.append('projectile')
                elif target['path']=='explosion':accessor.append('explosion')
            instance={'instanceKey':instance_key,'supportWeapon':weapon_name,
                'supportWeaponIdentity':{'weaponKey':weapon_key(weapon_name),
                    'name':weapon_name,'identityStatus':public_weapon['identityStatus']},
                'target':{'resource':'support_weapon','path':target['path'],
                    'attackRole':role,'attackKind':attack.get('kind'),
                    'parentAttackRole':attack.get('parentRole'),
                    'accessor':accessor,
                    'catalogBranches':branch_aliases(weapon_name,role)if role else[],
                    'writableCatalogBranches':[branch for branch in branch_aliases(weapon_name,role)
                        if branch['state']=='RESOLVED']if role else[]},
                'semanticFieldId':field_id,
                'qualifiedSemanticFieldId':field['semanticFieldId'],
                'apiFieldConstant':api_constant(field_id),
                'display':{'name':field['displayName'],'domain':field_id.split('.')[0],
                    'group':object_meta['semanticType']},
                'value':{'kind':'reference'if reference else'scalar','type':field['type'],
                    'baseline':field['currentDefault'],'expected':field['currentDefault'],
                    'unit':field['unit'],'reference':reference},
                'writable':field['acceptedForWrites'],'readOnly':not field['acceptedForWrites'],
                'blockedReason':field['reason'],
                'backing':{'objectKey':object_key,'kind':object_meta['kind'],
                    'semanticType':object_meta['semanticType'],
                    'domain':field['backing'].get('settings')or field['backing'].get('component'),
                    'operationGroupingKey':operation_key,'runtimeBackingScope':backing_scope},
                'sharedScope':{'scopeKey':object_meta['sharedScopeKey'],
                    'shared':object_meta['shared'],
                    'requiresAcknowledgement':object_meta['requiresSharedAcknowledgement'],
                    'reviewedConsumerCount':object_meta['reviewedConsumerCount'],
                    'affectedSemanticConsumers':consumers,
                    'reviewedScopeComplete':object_meta['reviewedScopeComplete'],
                    'dynamicConsumersPossible':object_meta['dynamicConsumersPossible']},
                'operation':{'minimumApi':'hd2.patch','patchSupported':True,
                    'transactionSupported':True,'transactionRequired':False,
                    'transactionGroupingKey':operation_key,'planSupported':True,
                    'planRequired':False,'planRequiredForMultipleBackingObjects':True,
                    'planGroupingKey':plan_key,'phase':1,'dependencies':[],
                    'allowSharedRequired':object_meta['requiresSharedAcknowledgement']},
                'resolution':resolution_metadata(weapon_name,field),
                'provenance':{'identity':'unique reviewed support-weapon runtime identity',
                    'semantics':'shared player/support field schema',
                    'ownership':'typed retained-snapshot ownership chain',
                    'baseline':'exact retained-snapshot value',
                    'validation':'production resolver guarded ALREADY_DESIRED no-op',
                    'evidenceArtifact':'support-weapon-authoring-validation-F5FEE03DCFDB.json'}}
            instances.append(instance);operation_groups[operation_key].append(instance_key)
            object_meta['fieldInstanceKeys'].append(instance_key)
            public_weapon['fieldInstanceKeys'].append(instance_key)

    operation_group_entries=[]
    instance_by_key={instance['instanceKey']:instance for instance in instances}
    for operation_key,instance_keys in sorted(operation_groups.items()):
        first=instance_by_key[instance_keys[0]]
        operation_group_entries.append({'operationGroupingKey':operation_key,
            'backingObjectKey':first['backing']['objectKey'],
            'runtimeBackingScope':first['backing']['runtimeBackingScope'],
            'target':first['target'],'fieldInstanceKeys':instance_keys,
            'recommendedApi':'hd2.transaction'if len(instance_keys)>1 else'hd2.patch',
            'allowSharedRequired':first['operation']['allowSharedRequired'],
            'planGroupingKey':first['operation']['planGroupingKey'],'phase':1,
            'dependencies':[]})

    duplicate_groups=[];by_semantic=defaultdict(list)
    for instance in instances:
        by_semantic[(instance['supportWeapon'],instance['semanticFieldId'])].append(instance)
    for (weapon_name,field_id),entries in sorted(by_semantic.items()):
        if len(entries)>1:
            duplicate_groups.append({'supportWeapon':weapon_name,'semanticFieldId':field_id,
                'count':len(entries),'instanceKeys':[entry['instanceKey']for entry in entries],
                'attackRoles':[entry['target']['attackRole']for entry in entries],
                'backingObjectKeys':[entry['backing']['objectKey']for entry in entries]})

    domain_counts=defaultdict(int);weapons_by_domain=defaultdict(int)
    for weapon in public_weapons:
        for domain,field_ids in weapon['writableFieldsByDomain'].items():
            domain_counts[domain]+=sum(1 for field in runtime_weapons[weapon['name']]['fields']
                if field['semanticFieldId'].split('.')[0]==domain)
            if field_ids:weapons_by_domain[domain]+=1
    summary={'catalogWeapons':35,'uniqueSupportIdentities':sum(w['resolution']=='UNIQUE'for w in source['weapons']),
        'duplicateGroupsBlocked':sum(w['resolution']=='DUPLICATE'for w in source['weapons']),
        'duplicateGroupNames':[w['name']for w in source['weapons']if w['resolution']=='DUPLICATE'],
        'writableSupportWeapons':sum(w['writable']for w in public_weapons),
        'writableFieldInstances':sum(w['writableFieldCount']for w in public_weapons),
        'fieldInstancesByDomain':dict(sorted(domain_counts.items())),
        'weaponsWithDomain':dict(sorted(weapons_by_domain.items())),
        'writableProjectileBranches':len({(w['name'],a['runtimeRole'])for w in public_weapons
            for a in w['attackBranches']if a['kind']=='Projectile'and a['writable']}),
        'writableExplosionBranches':len({(w['name'],a['runtimeRole'])for w in public_weapons
            for a in w['attackBranches']if a['kind']=='Explosion'and a['writable']}),
        'writableBranchesByFamily':{kind:len({(w['name'],a['runtimeRole'])
            for w in public_weapons for a in w['attackBranches']
            if a['kind']==kind and a['writable']})
            for kind in ('Projectile','Explosion','Arc','Beam','Spray','Melee','Status')},
        'weaponsWithHeatFields':weapons_by_domain['heat'],
        'weaponsWithChargeFields':weapons_by_domain['charge'],
        'weaponsWithDirectAmmoFields':sum(any(domain in w['writableFieldsByDomain']
            for domain in ('magazine','rounds'))for w in public_weapons),
        'linkedStratagemIdentities':sum(w['linkedStratagem']['known']for w in public_weapons),
        'linkedStratagemScalarValues':0,
        'supportCallInLinkage':call_in_linkage['audit'],
        'sharedFieldInstances':sum(field['affectsMultipleWeapons']
            for weapon in runtime_weapons.values()for field in weapon['fields']),
        'internalSupportAuthoringInstances':sum(len(weapon['fields'])for weapon in runtime_weapons.values()),
        'publishedSupportFieldInstances':len(instances),
        'legacyFlattenedFieldEntries':sum(sum(len(fields)for fields in weapon['writableFieldsByDomain'].values())
            for weapon in public_weapons),
        'branchSpecificFieldInstances':sum(instance['target']['attackRole']is not None
            for instance in instances),
        'backingObjectCount':len(backing_objects),
        'operationGroupingCount':len(operation_group_entries),
        'sharedBackingObjectCount':sum(value['shared']for value in backing_objects.values()),
        'sharedConsumerScopeCount':len({value['sharedScopeKey']for value in backing_objects.values()
            if value['shared']}),
        'duplicateSemanticFieldGroups':len(duplicate_groups),
        'duplicateSemanticFieldInstances':sum(group['count']for group in duplicate_groups),
        'deduplicationLossPrevented':len(instances)-sum(sum(len(fields)
            for fields in weapon['writableFieldsByDomain'].values())for weapon in public_weapons),
        'referenceFieldInstances':sum(instance['value']['kind']=='reference'for instance in instances),
        'readOnlyFieldInstances':sum(instance['readOnly']for instance in instances),
        'blockedFieldDeclarations':sum(len(weapon['blockedFields'])for weapon in public_weapons),
        'intentionallyOmittedInstances':0,
        'safety':source['safety']}
    constants={}
    for definition_item in schema['fields']:
        domain,_,name=definition_item['id'].partition('.')
        if domain in('charge','status'):constants.setdefault(domain,{})[name.replace('.','_')]=definition_item['id']
    runtime={'version':(ROOT/'VERSION').read_text().strip(),'weapons':runtime_weapons,
        'fields':constants,'summary':summary}
    public={'schemaVersion':2,'contract':'hd2runtime.support_weapon.guarded_authoring.v2',
        'hd2RuntimeVersion':runtime['version'],'summary':summary,'weapons':public_weapons,
        'fieldInstances':instances,
        'backingObjects':[backing_objects[key]for key in sorted(backing_objects)],
        'operationGroups':operation_group_entries,
        'duplicateSemanticFieldInstances':duplicate_groups,
        'compatibility':{'legacyWeaponViewsRetained':True,
            'legacyView':'weapons[].writableFieldsByDomain',
            'legacyViewSemantics':'Deduplicated lookup only; use fieldInstances for authoring.',
            'canonicalAuthoringCollection':'fieldInstances'},
        'planContract':{'api':'hd2.plan','currentPhase':1,
            'currentInstancesRequireTargetFrom':False,
            'oneOperationPerOperationGroupingKey':True,
            'multipleBackingObjectsRequirePlan':True},
        'referenceContract':{'typedIdentityOnly':True,
            'expectedValueProperty':'value.reference.expectedSemanticReference',
            'sourceClassProperty':'value.reference.sourceClass',
            'rawNativeIdentifiersPublished':False,
            'currentReferenceFieldInstances':summary['referenceFieldInstances']},
        'supportCallInLinks':{key:call_in_linkage[key]for key in
            ('contract','schemaVersion','joinContract','relationships','audit')},
        'safety':{'runtimeAddresses':False,'rawResourceIdentifiers':False,
            'writesDuringGeneration':0,'protectionChangesDuringGeneration':0,'fixtureFallback':'disabled'}}
    public['instanceAudit']=audit_instance_coverage(runtime,public)
    return runtime,public


def outputs(catalog_path=CATALOG):
    runtime,public=build(catalog_path)
    return {LUA_OUTPUT:'-- Generated guarded support-weapon authoring contract; do not edit.\nreturn '+lua(runtime)+'\n',
        JSON_OUTPUT:json.dumps(public,indent=2)+'\n'}


def generate(check=False,catalog_path=CATALOG):
    stale=[]
    for path,body in outputs(catalog_path).items():
        if not path.exists()or path.read_text()!=body:
            stale.append(path)
            if not check:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
    if check and stale:raise RuntimeError('Stale support authoring outputs: '+', '.join(map(str,stale)))
    return stale


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-catalog',type=Path)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if args.refresh_catalog:refresh_catalog(args.refresh_catalog)
    print(', '.join(str(path.relative_to(ROOT))for path in generate(args.check))or'up to date')
