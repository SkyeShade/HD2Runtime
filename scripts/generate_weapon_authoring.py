"""Generate runtime and GUI weapon authoring metadata from one reviewed schema and snapshot report."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402  central build identity (schemas/build_profile.json)
from migration import overlay as migration_overlay  # noqa: E402  build-migration hook
import reticle_fields
import weapon_movement_fields
import fire_mode_fields
import weapon_mode_fields
import weapon_sound_fields
import presentation_fields
import status_fields
import equipment_fields

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_REPORT=ROOT/'build/snapshot-results-authoring/PlayerWeaponRuntimeMap.json'
DEFAULT_IDENTITIES=ROOT/'build/snapshot-results-authoring/PlayerWeaponRuntimeMap.identity-candidates.json'
SCHEMA=ROOT/'schemas/player_weapon_fields.json'
VERSION_FILE=ROOT/'VERSION'
CATALOG=ROOT/'schemas/player_weapon_authoring_catalog.json'
AMMO_CATALOG=ROOT/'schemas/player_weapon_ammo_catalog.json'
COMPOSITION_CATALOG=ROOT/'schemas/player_weapon_composition_catalog.json'
# ProjectileSettings +64 penetration slowdown and +52 lifetime of every player projectile row
# (scripts/research_player_projectile_members.py; members proven on support weapons, 67/67 exact here).
PROJECTILE_MEMBERS=ROOT/'research/player-projectile-members-F5FEE03DCFDB.json'
JSON_OUTPUT=ROOT/'sdk/PlayerWeaponAuthoringCapabilities.json'
AMMO_JSON_OUTPUT=ROOT/'sdk/PlayerWeaponAmmoCapabilities.json'
LUA_OUTPUT=ROOT/'domains/player_weapon_authoring.lua'
OWNERSHIP=ROOT/'research/field-ownership-F5FEE03DCFDB.json'
# Underbarrel weapons (research/underbarrel-weapons-F5FEE03DCFDB.json): separate weapon entities a host's default
# underbarrel item names. Published as nested sub-targets with only the members the field schema proves.
UNDERBARREL=ROOT/'research/underbarrel-weapons-F5FEE03DCFDB.json'
# 0.30.2: the proven real root of each weapon the stat-fingerprint mapper resolves to two roots
# (scripts/research_weapon_roots.py: equipped snapshots, underbarrel hosts, a call-in rack).
WEAPON_ROOTS=ROOT/'research/weapon-roots-F5FEE03DCFDB.json'
UNDERBARREL_UNVERIFIED=('The underbarrel is its own weapon entity, created when the host weapon is set up; the member '
    'is proven (the same component member as this field on every weapon), but whether a built underbarrel keeps a '
    'copy of it and the gameplay effect of an edit are not yet shown in game.')
EFFECT_REASON={
    'ACTIVE_DIRECT':'A settings row the game reads when the projectile, explosion or damage is used.',
    'ACTIVE_AT_INSTANTIATION':('A component member the game copies into the weapon when it builds it (base plus '
        'customization deltas, observed in snapshot memory): weapons built after the write use it; a weapon already '
        'built keeps its copy until it is rebuilt (redeploy, reinforce, re-equip).'),
    'AMBIGUOUS':'The effective value depends on state Runtime cannot prove offline.',
    'OVERRIDDEN':'A default customization item overwrites this member when the weapon is built.',
    'DORMANT_OR_METADATA':'Derived or descriptive; the gameplay path does not read this value.'}


def lua(value):
    if isinstance(value,dict):
        return '{'+','.join('['+lua(k)+']='+lua(v) for k,v in sorted(value.items()))+'}'
    if isinstance(value,list):return '{'+','.join(lua(v) for v in value)+'}'
    if isinstance(value,bool):return 'true' if value else 'false'
    if value is None:return 'nil'
    if isinstance(value,(int,float)):return repr(value)
    return json.dumps(str(value),ensure_ascii=True)


def apply_root_corrections(value):
    """Each DUPLICATE weapon with a proven root (WEAPON_ROOTS) resolves to that root alone: resources = [root],
    resolution UNIQUE; the two candidate roots and the evidence kind are kept on the entry. Idempotent."""
    corrections={item['weapon']:item for item in json.loads(WEAPON_ROOTS.read_text())['corrections']}
    for entry in value['weapons']:
        item=corrections.pop(entry['name'],None)
        if not item:continue
        candidates=entry.get('candidateRoots')or entry['resources']
        assert entry['resolution']in('DUPLICATE','UNIQUE')and item['provenRoot']in candidates,entry['name']
        entry['candidateRoots']=candidates
        entry['resources']=[item['provenRoot']]
        entry['resolution']='UNIQUE'
        entry['rootCorrection']={'source':WEAPON_ROOTS.name,'evidence':item['evidence']['kind'],
            'droppedRoots':item['droppedRoots']}
    assert not corrections,'root corrections for weapons not in the catalog: %r'%sorted(corrections)
    return value


def apply_root_corrections_ammo(ammo):
    """The same corrections on the ammo catalog: the proven root's own values (resourceValues, when the two roots
    differed), the identity block lifted (direct fields writable again; customization-owned ones stay read-only).
    Idempotent."""
    corrections={item['weapon']:item for item in json.loads(WEAPON_ROOTS.read_text())['corrections']}
    for entry in ammo['weapons']:
        item=corrections.get(entry['name'])
        if not item:continue
        entry['candidateRoots']=entry.get('candidateRoots')or entry['resources']
        entry['resources']=[item['provenRoot']]
        entry['ordinaryWritesBlocked']=False
        own=next((r['values']for r in entry.pop('resourceValues',[])if r['resource']==item['provenRoot']),None)
        if own:
            entry['diagnostics']=[d for d in entry['diagnostics']if not d.startswith('duplicate runtime resources')]
            for key,value in own.items():entry['fields'][key]['value']=value
            fields=entry['fields']
            if'feedCapacity1'in own:
                capacity=int(own['feedCapacity1']+own['feedCapacity2'])
                fields['capacity']['value']=capacity
                fields['roundsFromAmmoBox']['value']=own['roundsFromSupply']//2   # half the supply, as every feed
                entry['effectiveCapacity']=dict(entry['effectiveCapacity'],status='RESOLVED',value=capacity)
        for field in entry['fields'].values():
            if field.get('direct')and'reason'not in field:field['writable']=True
        entry['writable']=any(f.get('writable')for f in entry['fields'].values())
    weapons=ammo['weapons']
    ammo['summary']['effectiveCapacityResolved']=sum(1 for w in weapons
        if w['effectiveCapacity'].get('status')in('RESOLVED','CORRELATED_CUSTOMIZATION'))
    ammo['summary']['weaponsWithWritableAmmoFields']=sum(1 for w in weapons if w['writable'])
    ammo['evidenceCounts']['roundsFeedAmbiguousIdentities']=sum(1 for w in weapons
        if w['effectiveCapacity'].get('status')=='AMBIGUOUS_RUNTIME_IDENTITY')
    return ammo


def refresh_catalog(report_path=DEFAULT_REPORT,identities_path=DEFAULT_IDENTITIES,catalog_path=CATALOG):
    report=json.loads(Path(report_path).read_text());identities=json.loads(Path(identities_path).read_text())
    candidates={item['resourceHash']:item for item in report['runtimeCandidates']}
    value={'schemaVersion':1,'sourceSnapshot':build_profile.SNAPSHOT_NAME,
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
    apply_root_corrections(value)
    Path(catalog_path).write_text(json.dumps(value,indent=2)+'\n',newline='\n')


def build(catalog_path=CATALOG):
    source=json.loads(Path(catalog_path).read_text())
    ammo_source=json.loads(AMMO_CATALOG.read_text())
    composition_source=json.loads(COMPOSITION_CATALOG.read_text())
    # Active projectile source of every attack (research/active-projectile-sources-F5FEE03DCFDB.json).
    from generate_attack_outputs import active_sources,source_reason
    projectile_sources=active_sources()[1]
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
        if base.startswith('terminal.') and base.endswith('.explosion'):base='terminal.explosion'
        match=re.match(r'^explosion\.[^.]+\.(impact|expiry)\.(.+)$',base)
        if match:base='explosion.'+match.group(2)
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

    projectile_members={(weapon['name'],branch['prefix']):branch for weapon in
        json.loads(PROJECTILE_MEMBERS.read_text())['weapons'] for branch in weapon['branches']}
    reticle_rows,reticle_research=reticle_fields.load()
    movement_rows=weapon_movement_fields.load()
    fire_mode_rows,_=fire_mode_fields.load()
    weapon_mode_rows,_=weapon_mode_fields.load()
    sound_data=weapon_sound_fields.load()
    presentation_rows,presentation_research,trait_values,penetration_values=presentation_fields.load()
    # Duplicate identities whose second root is proven to be another weapon's underbarrel: a precise reason (the
    # weapon stays fail-closed until it is re-mapped on its own root).
    misattributed={item['weapon']:('One of the two catalogued runtime roots ('+item['dropRoot']+') is the '
        +', '.join(item['underbarrelOf'])+' underbarrel weapon (research/underbarrel-weapons-F5FEE03DCFDB.json), not '
        'this weapon; ordinary writes stay closed until it is re-mapped on its own root ('+', '.join(item['keptRoots'])
        +').') for item in json.loads(UNDERBARREL.read_text(encoding='utf-8'))['catalogCorrections']}
    weapons=[]
    for name in sorted(identities):
        identity=identities[name];candidate=candidates[identity['bestCandidate']['resourceHash']]
        unique=identity['resolution']=='UNIQUE'
        blocked=None if unique else(misattributed.get(name)
            or 'Ambiguous runtime identity; ordinary hd2.weapon(name) writes fail closed.')
        fields=[];resolved=candidate['resolvedFields']
        ownership=candidate['ownership']
        composition=composition_source['weapons'][name]

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
        movement=movement_rows.get(('player',name))
        if movement and movement['weaponData'] and unique:
            fields.append(weapon_movement_fields.apply(make_field(weapon_movement_fields.FIELD,None,
                component_backend(candidate,'WeaponDataComponentData',weapon_movement_fields.OFFSET,
                    weapon_movement_fields.STORAGE),unique,blocked),movement,identity['bestCandidate']['resourceHash']))
        fields.append(make_field('weapon.crosshair_type',resolved.get('crosshair_type'),
            component_backend(candidate,'WeaponDataComponentData',400,'u32'),editable=False,
            reason=definitions['weapon.crosshair_type']['reason']))
        reticle=reticle_rows.get(('player',name))
        if reticle and reticle['reticle']!='absent':
            fields.append(reticle_fields.apply(make_field(reticle_fields.FIELD,None,
                component_backend(candidate,'WeaponDataComponentData',reticle_fields.OFFSET,reticle_fields.STORAGE)),
                reticle,reticle_research,unique))
        fire=fire_mode_rows.get(('player',name))
        if fire and fire['state']!='absent':
            fields.append(fire_mode_fields.apply_modes(make_field(fire_mode_fields.MODES_FIELD,None,
                component_backend(candidate,'WeaponDataComponentData',fire_mode_fields.MODES_OFFSET,'fire_mode_set')),
                fire,unique))
            fields.append(fire_mode_fields.apply_burst(make_field(fire_mode_fields.BURST_FIELD,None,
                component_backend(candidate,'WeaponDataComponentData',fire_mode_fields.BURST_OFFSET,'u32')),
                fire,unique))
        # Rate-of-fire modes, weapon-function input bindings and the ProgrammableAmmo projectile
        # (research/weapon-functions-F5FEE03DCFDB.json).
        modes=weapon_mode_rows.get(('player',name)) or {}
        if (modes.get('fireRate') or {}).get('state') not in (None,'absent') and 'ProjectileWeaponComponentData' in ownership:
            fields.append(weapon_mode_fields.apply_rates(make_field(weapon_mode_fields.RATES_FIELD,None,
                component_backend(candidate,'ProjectileWeaponComponentData',weapon_mode_fields.RATES_OFFSET,
                    'fire_rate_set')),modes,unique))
        if modes.get('inputs') and 'WeaponDataComponentData' in ownership:
            for side,field_id in weapon_mode_fields.INPUT_FIELDS.items():
                fields.append(weapon_mode_fields.apply_input(make_field(field_id,None,
                    component_backend(candidate,'WeaponDataComponentData',weapon_mode_fields.INPUT_OFFSETS[side],'u32')),
                    modes,side,unique))
        if (modes.get('functionAmmo') or {}).get('state') not in (None,'absent')                 and 'ProjectileWeaponComponentData' in ownership:
            fields.append(weapon_mode_fields.apply_function_projectile(make_field(
                weapon_mode_fields.FUNCTION_PROJECTILE_FIELD,None,component_backend(candidate,
                    'ProjectileWeaponComponentData',weapon_mode_fields.FUNCTION_PROJECTILE_OFFSET,'u32')),modes,unique))
        # The firing sound: the type's ProjectileWeapon sound events (research/weapon-sounds-F5FEE03DCFDB.json).
        if 'ProjectileWeaponComponentData' in ownership:
            fields.append(weapon_sound_fields.apply(make_field(weapon_sound_fields.FIELD,None,
                component_backend(candidate,'ProjectileWeaponComponentData',weapon_sound_fields.OFFSET,
                    weapon_sound_fields.STORAGE),unique,blocked),sound_data,'player',name,
                identity['bestCandidate']['resourceHash'],fire_mode_rows.get(('player',name)),
                bool(resolved.get('is_suppressed'))))
        else:
            fields.append(make_field(weapon_sound_fields.FIELD,None,None,editable=False,
                reason=weapon_sound_fields.NO_RECORD))
        # Armory presentation: the weapon's own LoadoutEntry trait tags (research/weapon-presentation-F5FEE03DCFDB.json).
        presentation=presentation_rows.get(('player',name))
        presentation_backing=presentation and presentation['state']!='absent' and presentation_fields.backing(
            presentation,identity['bestCandidate']['resourceHash'],'trait_set')
        if presentation_backing:
            fields.append(presentation_fields.apply_traits(make_field(presentation_fields.TRAITS_FIELD,None,
                presentation_backing),presentation,presentation_research,trait_values,unique))
            fields.append(presentation_fields.apply_penetration(make_field(presentation_fields.PENETRATION_FIELD,None,
                dict(presentation_backing,storage='armor_penetration_label')),presentation,presentation_research,
                penetration_values,unique))
        fields.append(make_field('weapon.primary_fire_mode',resolved.get('primary_fire_mode'),
            component_backend(candidate,'WeaponDataComponentData',144,'u32'),editable=False,
            reason=definitions['weapon.primary_fire_mode']['reason']))
        fire_mode=composition_source['weapons'][name]['fireMode']
        default_mode=make_field('weapon.default_fire_mode',fire_mode['nativeValue'],
            component_backend(candidate,'WeaponDataComponentData',144,'u32'),
            editable=unique and fire_mode['writable'],reason=blocked or fire_mode.get('reason'))
        default_mode['enumValues']={'full_auto':1,'semi_auto':2}
        default_mode['allowedValues']=fire_mode['allowedModes']
        default_mode['nativeModeVector']=fire_mode['nativeModeVector']
        default_mode['writeKind']=fire_mode.get('writeKind')
        fields.append(default_mode)
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

        heat = composition.get('heat') or {}
        if heat.get('heatMechanismPresent'):
            for item in heat['fields']:
                field_id = item['id']
                backend = None
                if item.get('offset') is not None and 'WeaponHeatComponentData' in ownership:
                    backend = component_backend(candidate,'WeaponHeatComponentData',
                        item['offset'],item['storage'])
                fields.append(make_field(field_id,item.get('value'),backend,
                    editable=unique and item['writable'],reason=blocked or item.get('reason'),
                    derived=item.get('derived',False)))
        if name==equipment_fields.DOUBLE_EDGE and 'WeaponHeatComponentData' in ownership:
            # Heat levels (research/equipment-coverage): threshold, the status each level applies to the wielder,
            # and the lock-at-maximum-heat flag.
            fields+=equipment_fields.double_edge_fields(
                lambda field_id,value,backend:make_field(field_id,value,backend,editable=unique,reason=blocked),
                lambda offset,storage:component_backend(candidate,'WeaponHeatComponentData',offset,storage))

        # 0.30.4 (research/las-beam-overhaul-comparison): the firing charge (wind-up) of the weapon's own heat record,
        # and the fire mode, rate and pulse of its own beam record (the LAS-13 Trident's pulsed beam).
        def charge_make(field_id,value,backend):
            return make_field(field_id,value,backend,editable=unique,reason=blocked)
        if 'WeaponHeatComponentData' in ownership:
            fields+=equipment_fields.firing_charge_fields(charge_make,
                ownership['WeaponHeatComponentData']['recordIndex'],
                lambda offset,storage:component_backend(candidate,'WeaponHeatComponentData',offset,storage))
        if 'BeamWeaponComponentData' in ownership:
            fields+=equipment_fields.beam_pulse_fields(charge_make,
                ownership['BeamWeaponComponentData']['recordIndex'],
                lambda offset,storage:component_backend(candidate,'BeamWeaponComponentData',offset,storage))

        attacks=candidate.get('attacks') or []
        for attack in composition['attacks']:
            backing=attack.get('targetBacking')
            if not backing:continue
            field_id='attack.'+attack['role']+'.projectile'
            backend=component_backend(candidate,backing['component'],backing['offset'],'u32')
            current={'weapon':name,'attack':attack['role'],'projectileType':attack['projectileType']}
            reason=attack.get('reason')
            # Writable only where the written member is the projectile the attack fires (its active source).
            source=projectile_sources[name][attack['role']]
            direct=source['status']=='ACTIVE_DIRECT'
            field=make_field(field_id,current,backend,
                editable=unique and attack['writableReferenceSwap'] and direct,
                reason=blocked or reason or (None if direct else source_reason(source)))
            field['projectileSource']={'status':source['status'],'mechanism':source['mechanism'],
                'member':source['member']}
            field['referenceKind']='projectile'
            field['compatibilityClass']=attack['compatibilityClass']
            field['referenceRole']=attack['role']
            field['referenceSettings']=attack['projectileSettings']
            field['residency']=attack['residency']
            fields.append(field)
            explosions={item['explosionType']:item for item in attack.get('explosions',[])}
            emitted_explosions=set()
            for action in attack.get('terminalActions',[]):
                phase=action['phase'];terminal_id=f"terminal.{attack['role']}.{phase}.explosion"
                terminal_backend=settings_backend('projectile',attack['projectileSettings'],
                    action['offset'],'u32',attack['role'])
                terminal_backend['phase']=phase
                terminal_current={'weapon':name,'attack':attack['role'],'phase':phase,
                    'explosionType':action['referenceType']}
                terminal=make_field(terminal_id,terminal_current,terminal_backend,
                    editable=unique and action['writable'],reason=blocked or action.get('reason'))
                terminal['referenceKind']='explosion';terminal['referenceRole']=attack['role']
                terminal['referencePhase']=phase;terminal['projectileBacking']=backing
                terminal['projectileSettings']=attack['projectileSettings']
                terminal['referenceSettings']=(explosions[action['referenceType']]['settings']
                    if action['referenceType'] else None)
                terminal['nullSentinel']=action.get('nullSentinel',0)
                resources=sorted({consumer['resourceHash'] for consumer in
                    action.get('projectileSettingsConsumers',[])})
                terminal['sharedWithResources']=resources
                terminal['affectsMultipleWeapons']=len(resources)>1
                terminal['writeScope']='shared_projectile' if len(resources)>1 else 'projectile_terminal_action'
                fields.append(terminal)
                if not action['referenceType']:continue
                explosion=explosions[action['referenceType']]
                if action['referenceType'] in emitted_explosions:continue
                emitted_explosions.add(action['referenceType'])
                for explosion_field in explosion['fields']:
                    suffix=explosion_field['id'][len('explosion.'):]
                    field_id=f"explosion.{attack['role']}.{phase}.{suffix}"
                    settings_kind='explosion_damage' if suffix.startswith('damage.') else 'explosion'
                    record=explosion['damageSettings'] if settings_kind=='explosion_damage' else explosion['settings']
                    backend=settings_backend(settings_kind,record,explosion_field['offset'],
                        explosion_field['storage'],attack['role'])
                    backend['phase']=phase
                    scalar=make_field(field_id,explosion_field['value'],backend,
                        editable=unique and explosion['writable'],reason=blocked or explosion.get('reason'))
                    scalar['sharedWithWeapons']=sorted({consumer['weapon'] for consumer in
                        explosion['playerConsumers'] if consumer['weapon']!=name})
                    scalar['sharedWithResources']=sorted({str(value) for value in
                        explosion['consumers']})
                    scalar['affectsMultipleWeapons']=explosion['shared']
                    scalar['writeScope']=explosion['writeScope']
                    scalar['explosionType']=explosion['explosionType']
                    scalar['terminalPhases']=[candidate['phase'] for candidate in
                        attack['terminalActions'] if candidate['referenceType']==explosion['explosionType']]
                    fields.append(scalar)
                # The explosion's DamageInfo status slots (0.30.2): every used slot's status as a typed reference, and
                # the first empty slot, which can take one. Same native slots and writer as a direct-hit row's; the row
                # is the explosion's own (its sharing travels with it). A status on an explosion is not live-proven.
                record=explosion['damageSettings']
                for spec in status_fields.slot_specs(record['recordType']):
                    if spec['role']=='strength'and not spec['attach']:continue
                    backend=settings_backend('explosion_damage',record,spec['offset'],spec['storage'],attack['role'])
                    backend['phase']=phase
                    backend.update(status_fields.backing_extra(spec))
                    slot_field=make_field(f"explosion.{attack['role']}.{phase}.damage.{spec['suffix']}",spec['current'],
                        backend,editable=unique and explosion['writable'],reason=blocked or explosion.get('reason'))
                    if spec['role']=='type':slot_field['type']='status_reference'
                    slot_field['sharedWithWeapons']=sorted({consumer['weapon'] for consumer in
                        explosion['playerConsumers'] if consumer['weapon']!=name})
                    slot_field['sharedWithResources']=sorted({str(value) for value in explosion['consumers']})
                    slot_field['affectsMultipleWeapons']=explosion['shared']
                    slot_field['writeScope']=explosion['writeScope']
                    slot_field['explosionType']=explosion['explosionType']
                    slot_field.update(status_fields.type_extra(spec))
                    fields.append(slot_field)
                shrapnel=explosion['shrapnel']
                for suffix,value in (('shrapnel_count',shrapnel['count']),
                        ('shrapnel_projectile',shrapnel['projectileType'])):
                    fields.append(make_field(f"explosion.{attack['role']}.{phase}.{suffix}",value,
                        editable=False,reason=shrapnel['reason']))
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
                scalar=make_field(prefix+'.'+suffix,values.get(key),backend,unique,
                    blocked or 'Projectile definitions are shared objects; allow_shared=true is required.')
                scalar['writeScope']='shared_projectile_definition'
                scalar['affectsMultipleWeapons']=True
                scalar['sharedWithWeapons']=sorted(set(scalar.get('sharedWithWeapons',[])))
                scalar['dynamicConsumersPossible']=True
                fields.append(scalar)
            member=projectile_members.get((name,prefix))
            if member and member['resolved'] and (member['group'],member['row'],member['recordType'])==(
                    record['group'],record['row'],record['recordType']):
                for suffix,key,offset in (('penetration_slowdown','penetrationSlowdown',64),('lifetime','lifetime',52)):
                    if suffix=='lifetime'and not member[key]:
                        continue    # 0 = no explicit lifetime; a non-zero value would add a limit, not tune one
                    backend=settings_backend('projectile',record,offset,'f32',role)
                    scalar=make_field(prefix+'.'+suffix,member[key],backend,unique,
                        blocked or 'Projectile definitions are shared objects; allow_shared=true is required.')
                    scalar['writeScope']='shared_projectile_definition'
                    scalar['affectsMultipleWeapons']=True
                    scalar['sharedWithWeapons']=sorted(set(scalar.get('sharedWithWeapons',[])))
                    scalar['dynamicConsumersPossible']=True
                    fields.append(scalar)

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
                scalar=make_field(prefix+'.'+suffix,values.get(key),backend,unique,blocked)
                if kind=='Projectile':
                    scalar['writeScope']='shared_projectile_damage_definition'
                    scalar['affectsMultipleWeapons']=True
                    scalar['dynamicConsumersPossible']=True
                fields.append(scalar)
            # Status slots: every used slot's status is a typed reference, and the first empty slot can take one.
            for spec in status_fields.slot_specs(record['recordType']):
                backend=settings_backend('damage',record,spec['offset'],spec['storage'],role)
                backend.update(status_fields.backing_extra(spec))
                slot_field=make_field(prefix+'.'+spec['suffix'],spec['current'],backend,unique,blocked)
                if spec['role']=='type':slot_field['type']='status_reference'
                if kind=='Projectile':
                    slot_field['writeScope']='shared_projectile_damage_definition'
                    slot_field['affectsMultipleWeapons']=True
                    slot_field['dynamicConsumersPossible']=True
                # Direct-hit projectile rows are live-proven (schemas/live_evidence.json); other rows stay gated.
                slot_field.update(status_fields.type_extra(spec,
                    status_fields.projectile_live_evidence() if kind=='Projectile' else None))
                if spec['role']=='type' or spec['attach']:fields.append(slot_field)
            status=attack.get('statusEffects')
            if isinstance(status,list):
                for index,effect in enumerate(status,1):
                    status_prefix=prefix+f'.status_{index}'
                    backend=settings_backend('damage',record,44+(index-1)*8+4,'f32',role)
                    scalar=make_field(status_prefix+'_strength',effect['strength'],backend,
                        unique,blocked)
                    if kind=='Projectile':
                        scalar['writeScope']='shared_projectile_damage_definition'
                        scalar['affectsMultipleWeapons']=True
                        scalar['dynamicConsumersPossible']=True
                    fields.append(scalar)

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

    subweapons=underbarrel_subweapons(definition,provenance,{w['name'] for w in weapons})
    by_host={}
    for sub in subweapons:by_host.setdefault(sub['subweaponOf'],[]).append({'name':sub['name'],'kind':sub['kind']})
    for weapon in weapons:
        if weapon['name'] in by_host:weapon['subweapons']=by_host[weapon['name']]
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
    # writableTargetAttacks is the structural count; only attacks whose member is their active source stay writable.
    summary['composition']['projectile']['activeSourceWritableTargetAttacks']=sum(1 for w in weapons
        for f in w['fields'] if f['type']=='projectile_reference' and f['editable'])
    return {'schemaVersion':schema['schema_version'],'hd2RuntimeVersion':VERSION_FILE.read_text().strip(),
        'buildFingerprints':report['gameFingerprints'],'sourceSnapshot':
            build_profile.SNAPSHOT_NAME,'summary':summary,
        'fieldDefinitions':schema['fields'],'semanticAliases':semantic_aliases,
        'backingCollisionAudit':collision_audit,'weapons':weapons,'subweapons':subweapons,
        'safety':{'addressesInPublicMetadata':False,'writes':0,'protectionChanges':0,
            'fixtureFallback':'disabled'}}


UNVERIFIED_ROW=('Runtime cannot establish that this weapon fires this projectile row (see effect.reason); the write '
    'lands but may not change this weapon in play.')


def settings_row_sources(value):
    """Whether each settings row a weapon's fields write is a row that weapon fires.

    Rows are read when used (ACTIVE_DIRECT) only if the attack's fired projectile is established. A weapon that fires
    a spawned entity, or whose charge / heat levels select their own projectiles, may never fire the row its
    projectile reference names: rows no level fires are DORMANT_OR_METADATA, rows only some levels fire and entity
    rows are AMBIGUOUS. Both keep writing (the definition may be shared with a weapon that does fire it) but require
    allow_unverified_effect and do not inherit live proof. Applied before the runtime table is generated."""
    from generate_attack_outputs import ACTIVE, active_sources
    sources=active_sources()[1]
    weapons={e['weapon']:e for e in json.loads(ACTIVE.read_text())['weapons']}
    rows={}
    for weapon in value['weapons']:
        entry=weapons.get(weapon['name'])or{}
        roles=sources.get(weapon['name'],{})
        levels=entry.get('heatLevelProjectiles')or entry.get('chargeLevelProjectiles')or[]
        levels=[v for v in levels if v]
        base=(entry.get('base')or{}).get('projType')
        for field in weapon['fields']:
            backing=field.get('backing')or{}
            if backing.get('kind')!='settings':
                continue
            branch=backing.get('branch')
            source=(roles.get(branch)or roles.get('feed_'+str(branch)))if branch else None
            status,reason='ACTIVE_DIRECT',None
            if entry.get('base',{}).get('projectileEntity'):
                status,reason='AMBIGUOUS',('The weapon fires a spawned entity (ProjectileWeapon ProjectileEntity), so this '
                    'projectile row is not established as what it fires.')
            elif levels:
                kind='heat'if entry.get('heatLevelProjectiles')else'charge'
                if base in levels:
                    status,reason='AMBIGUOUS',(f'Only the {kind} levels that name this projectile fire it; the other '
                        f'levels fire their own projectiles ({", ".join(str(v) for v in levels if v!=base)}).')
                else:
                    status,reason='DORMANT_OR_METADATA',(f'Every {kind} level fires another projectile '
                        f'({", ".join(str(v) for v in levels)}); this weapon never fires this row, which it names only '
                        'through its base reference' + (' and shares with ' + ', '.join(field['sharedWithWeapons'])
                        if field.get('sharedWithWeapons') else '') + '.')
            elif source and source['status']=='BLOCKED'and not source.get('candidatesAgree'):
                status,reason='AMBIGUOUS','The attack fires through another selector: '+source['reason']
            elif source and source['status']=='AMBIGUOUS'and not source.get('candidatesAgree'):
                reason=('Fired with the default equipment; '+source['reason'])
            rows[(weapon['name'],field['semanticFieldId'])]=(status,reason)
            if status!='ACTIVE_DIRECT'and field.get('editable'):
                field['acknowledgement']='allow_unverified_effect'
                field['acknowledgementReason']=UNVERIFIED_ROW+' '+reason
                field.pop('liveEvidence',None)
    return rows


OWN_EFFECT_FIELDS={'heat.level_1_threshold','heat.level_2_threshold','heat.level_3_threshold',
    'heat.level_1_self_status','heat.level_2_self_status','heat.level_3_self_status','heat.overheat_lock',
    weapon_mode_fields.RATES_FIELD,*weapon_mode_fields.INPUT_FIELDS.values(),
    weapon_mode_fields.FUNCTION_PROJECTILE_FIELD,presentation_fields.TRAITS_FIELD,presentation_fields.PENETRATION_FIELD,
    weapon_sound_fields.FIELD}


def block_overridden(value):
    """A component field a default customization item overwrites at every build (research/field-ownership
    OVERRIDDEN) is read-only whatever its own research says: a write could never show. 0.30.2: the LAS-5 Scythe's
    heat and heatsinks (its default Laser Heatsink), exposed once its identity was proven. Runs before the runtime
    table is built, so the runtime refuses the same fields the SDK marks read-only."""
    ownership={(row['weapon'],row['field']):row for row in json.loads(OWNERSHIP.read_text())['fields']}
    for weapon in value['weapons']:
        for field in weapon['fields']:
            row=ownership.get((weapon['name'],field['semanticFieldId']))
            if(field.get('editable')and(field.get('backing')or{}).get('kind')=='component'and row
                    and row['status']=='OVERRIDDEN'):
                field['editable']=field['acceptedForWrites']=False
                field['reason']=('A default customization item ('+str(row['owner']['item'])+') overwrites this '
                    'member when the weapon is built, so a write here would not show.')


def annotate_effects(value,rows):
    """Public proof model per field: APPLIED only means the guarded write was verified; `effect` says whether the
    written definition is the one gameplay uses (active source), when it takes effect, and what is live-proven."""
    ownership={(row['weapon'],row['field']):row for row in json.loads(OWNERSHIP.read_text())['fields']}
    import live_evidence
    live_targets=live_evidence.proven_targets()
    for weapon in value['weapons']:
        for field in weapon['fields']:
            # Exact (weapon, field) pairs a live test promoted (schemas/live_evidence.json provenTargets).
            promoted=live_targets.get((weapon['name'],field['semanticFieldId']))
            if promoted and field.get('editable')and not field.get('liveEvidence'):
                field['liveEvidence']=promoted
            backing=field.get('backing')or{}
            if field['semanticFieldId'] in OWN_EFFECT_FIELDS and field.get('effect'):
                # Fields whose own research established the effect (rate slots, bindings, function projectile,
                # presentation) keep it; only the write and live-proof flags are refreshed below.
                effect=dict(field['effect'])
            elif backing.get('kind')=='component':
                row=ownership.get((weapon['name'],field['semanticFieldId']))
                status=row['status']if row else'AMBIGUOUS'
                effect={'activeSource':status,'appliesWhen':'weapon_build','instantiationOnly':True,
                    'activeSourceProven':status=='ACTIVE_AT_INSTANTIATION'}
                if status=='AMBIGUOUS'and row:
                    effect['overriddenWhenEquipped']=row['owner']['options']
                    effect['reason']=('Equipping '+', '.join(row['owner']['options'])+' overwrites this member at '
                        'weapon build; the value applies while an option that does not patch it is equipped.')
                elif status=='OVERRIDDEN':
                    effect['overriddenBy']=row['owner']['item']
            elif backing.get('kind')=='settings':
                status,reason=rows[(weapon['name'],field['semanticFieldId'])]
                effect={'activeSource':status,'appliesWhen':'use','instantiationOnly':False,
                    'activeSourceProven':status=='ACTIVE_DIRECT'}
                if reason:
                    effect['reason']=reason
            elif field.get('derivedReadOnly')or field.get('derived'):
                effect={'activeSource':'DORMANT_OR_METADATA','appliesWhen':None,'instantiationOnly':None,
                    'activeSourceProven':True}
            else:
                continue
            effect.setdefault('reason',EFFECT_REASON[effect['activeSource']])
            effect['writeVerifiedOnApply']=bool(field.get('editable'))
            effect['gameplayEffectProven']=bool(field.get('liveEvidence'))
            effect['unverifiedEffect']=field.get('acknowledgement')=='allow_unverified_effect'
            field['effect']=effect
    counts=Counter(f['effect']['activeSource']for w in value['weapons']for f in w['fields']if f.get('effect'))
    editable=Counter(f['effect']['activeSource']for w in value['weapons']for f in w['fields']
        if f.get('effect')and f['editable'])
    value['summary']['effect']={'fieldInstances':dict(sorted(counts.items())),
        'editableFieldInstances':dict(sorted(editable.items()))}


def underbarrel_subweapons(definition,provenance,hosts):
    """Nested underbarrel targets ('<host> / underbarrel'): the entity's own component members only."""
    research=json.loads(UNDERBARREL.read_text(encoding='utf-8'))
    members={item['field']:item for item in research['members']}
    result=[]
    for item in research['underbarrels']:
        entity=item['underbarrel']
        owners=[host for host in item['hosts'] if host in hosts]
        if len(owners)!=1:continue
        host=owners[0];fields=[]
        for field_id,value in entity['values'].items():
            member=members[field_id];identity=entity['components'].get(member['component'])
            if not identity:continue
            spec=definition(field_id)
            local=identity['ownerCount']==1 and identity['uniqueOwner']
            fields.append({'displayName':spec['display_name'],'semanticFieldId':field_id,'type':spec['type'],
                'unit':spec.get('unit'),'currentDefault':value,'editable':local,'derivedReadOnly':False,
                'semanticTarget':spec.get('semantic_target',spec['id']),'canonical':True,'preferred':True,
                'deprecated':False,'aliasOf':None,'provenance':dict(provenance,
                    source='research/underbarrel-weapons-F5FEE03DCFDB.json'),'min':None,'max':None,'enumValues':None,
                'backing':{'kind':'component','component':member['component'],'offset':member['offset'],
                    'storage':member['storage'],'width':4,'recordIndex':identity['recordIndex'],
                    'indexRow':identity['indexRow'],'ownerCount':identity['ownerCount'],
                    'uniqueOwner':identity['uniqueOwner']},
                'writeScope':'weapon_local' if local else 'shared_component','sharedWithWeapons':[],
                'affectsMultipleWeapons':not local,'reason':None if local else 'The component record is shared.',
                'acceptedForWrites':local,'acknowledgement':'allow_unverified_effect',
                'acknowledgementReason':UNDERBARREL_UNVERIFIED,
                'apiFieldConstant':'hd2.fields.'+field_id,
                'effect':{'activeSource':'AMBIGUOUS','appliesWhen':'weapon_build','instantiationOnly':True,
                    'activeSourceProven':False,'reason':UNDERBARREL_UNVERIFIED,'writeVerifiedOnApply':local,
                    'gameplayEffectProven':False,'unverifiedEffect':True}})
        projectile=entity.get('projectile')or{}
        result.append({'name':host+' / underbarrel','subweaponOf':host,'kind':'underbarrel',
            'slot':'underbarrel','resolution':'UNIQUE','ordinaryWritesBlocked':False,'blockReason':None,
            'resources':[entity['resource']],'implementationFamilies':[entity['family']],
            'linkItem':item['item'],
            'link':('The host\'s default underbarrel item '+item['item']+' names this entity (WeaponCustomization '
                '+192 underbarrel_path); the game creates it as a separate weapon when the host is set up.'),
            'sharedDefinitions':({'projectile':('The underbarrel fires the projectile row its ProjectileWeapon names '
                '(also held by its WeaponRounds); that row and its explosion are shared definitions, edited with '
                'allow_shared on the weapon that owns them in the catalog.'),
                'firedMember':'unproven (ProjectileWeapon +0 and WeaponRounds +64 hold the same projectile)'}
                if projectile else None),
            'notExposed':['reload time (the reload ability duration; WeaponReload +56 is 0)',
                'WeaponRounds +92 / +104 (meaning not proven)','the projectile reference (fired member unproven)'],
            'fields':fields})
    return result


def api_constant(field_id,legacy):
    domain,name=field_id.split('.',1)
    constant=name.replace('.','_')
    if legacy.get(domain,{}).get(constant,field_id)!=field_id:
        constant='player_'+constant
    return 'hd2.fields.'+domain+'.'+constant


def outputs(catalog_path=CATALOG):
    value=build(catalog_path)
    rows=settings_row_sources(value)
    # The Lua constant for each field, so authors never pick a legacy fixed-resource constant by accident.
    legacy={}
    for resource in json.loads((ROOT/'schemas/sdk.json').read_text())['resources'].values():
        for name,spec in resource['fields'].items():
            legacy.setdefault(spec['domain'],{})[name.replace('.','_')]=name
    for weapon in value['weapons']:
        for field in weapon['fields']:
            field['apiFieldConstant']=api_constant(field['semanticFieldId'],legacy)
    ammo_source=json.loads(AMMO_CATALOG.read_text())
    block_overridden(value)
    constants={}
    for weapon in value['weapons']:
        for field in weapon['fields']:
            field_id=field['semanticFieldId'];domain=field_id.split('.')[0]
            key=field_id[len(domain)+1:].replace('.','_')
            constants.setdefault(domain,{})[key]=field_id
    constants.setdefault('attack',{})['projectile']='attack.projectile'
    constants.setdefault('terminal',{})['explosion']='terminal.explosion'
    for definition in value['fieldDefinitions']:
        if definition['id'].startswith('explosion.'):
            constants.setdefault('explosion',{})[
                definition['id'][len('explosion.'):].replace('.','_')]=definition['id']
    runtime={'version':value['hd2RuntimeVersion'],
        'weapons':{w['name']:w for w in value['weapons']+value['subweapons']},
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
    runtime_lua='-- Generated from schemas/player_weapon_fields.json and reviewed snapshot output; do not edit.\nreturn '\
        +lua(migration_overlay.apply('player_weapon_authoring', runtime))+'\n'
    # The effect model is public metadata only; the runtime table carries just the acknowledgements it enforces.
    annotate_effects(value,rows)
    return {JSON_OUTPUT:json.dumps(value,indent=2)+'\n',
        AMMO_JSON_OUTPUT:json.dumps(ammo,indent=2)+'\n',
        LUA_OUTPUT:runtime_lua}


def generate(check=False,catalog_path=CATALOG):
    stale=[]
    for path,body in outputs(catalog_path).items():
        if not path.exists() or path.read_text()!=body:
            stale.append(path)
            if not check:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body,newline='\n')
    if check and stale:raise RuntimeError('Stale weapon authoring outputs: '+', '.join(str(p) for p in stale))
    return stale


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true');parser.add_argument('--catalog',type=Path,default=CATALOG)
    parser.add_argument('--refresh-catalog',action='store_true')
    parser.add_argument('--apply-root-corrections',action='store_true',
        help='apply research/weapon-roots to the existing catalog (no snapshot inputs needed)')
    parser.add_argument('--report',type=Path,default=DEFAULT_REPORT)
    parser.add_argument('--identities',type=Path,default=DEFAULT_IDENTITIES)
    args=parser.parse_args()
    if args.refresh_catalog:refresh_catalog(args.report,args.identities,args.catalog)
    elif args.apply_root_corrections:
        value=apply_root_corrections(json.loads(args.catalog.read_text()))
        args.catalog.write_text(json.dumps(value,indent=2)+'\n',newline='\n')
    if args.refresh_catalog or args.apply_root_corrections:
        AMMO_CATALOG.write_text(json.dumps(apply_root_corrections_ammo(json.loads(AMMO_CATALOG.read_text())),
            indent=2)+'\n',newline='\n')
    print('\n'.join(str(p) for p in generate(args.check,args.catalog)) or'up to date')
