"""Graph-aware support-weapon report built from the shared read-only mapper."""
from __future__ import annotations

from collections import Counter,defaultdict
from copy import deepcopy
import json
from pathlib import Path

KINDS=('Projectile','Explosion','Beam','Arc','Spray','Melee','Status','Unknown')
FIELDS=('standard_damage','durable_damage','ap_direct','ap_slight','ap_large','ap_extreme',
        'demolition','stagger','push_force','projectile_velocity','projectile_mass','drag',
        'gravity','pellet_count')
TOLERANCE={'projectile_velocity':2,'projectile_mass':.1,'drag':.01,'gravity':.01}


def _compare(runtime,attack):
    if runtime.get('kind') != attack.get('kind'):return None
    values=runtime.get('resolvedFields') or {};matched=[];mismatched=[]
    for field in FIELDS:
        actual,want=values.get(field),attack.get(field)
        if not isinstance(actual,(int,float)) or not isinstance(want,(int,float)):continue
        tolerance=TOLERANCE.get(field,0)
        (matched if abs(actual-want)<=tolerance else mismatched).append(field)
    return {'runtimeAttackRole':runtime.get('role'),'runtimeAttackKind':runtime.get('kind'),
            'matchedFields':matched,'mismatchedFields':mismatched,'compared':len(matched)+len(mismatched)}


def _branch_graph(weapon,candidates,identity_unique):
    runtime_attacks=[]
    for candidate in candidates:
        for index,attack in enumerate(candidate.get('attacks') or [],1):
            item=deepcopy(attack);item['runtimeAttackIndex']=index;item['resourceHash']=candidate['resourceHash']
            runtime_attacks.append(item)
    branches=[]
    for attack in weapon['attacks']:
        ranked=[]
        for runtime in runtime_attacks:
            compared=_compare(runtime,attack)
            if compared:ranked.append(compared)
        ranked.sort(key=lambda value:(len(value['mismatchedFields']),-len(value['matchedFields']),
                                      str(value['runtimeAttackRole'])))
        best=ranked[0] if ranked else None
        state='UNRESOLVED'
        if identity_unique and best and not best['mismatchedFields'] and best['compared']>=3:state='RESOLVED'
        elif best:state='PARTIAL' if identity_unique else 'IDENTITY_AMBIGUOUS'
        reason=None
        if attack['kind']=='Explosion':reason='ExplosionSettings ownership is not mapped in the current snapshot profile'
        elif attack['kind']=='Status':reason='DamageInfo exposes numeric status entries; the linked status settings record is not mapped'
        elif attack['kind']=='Unknown':reason='catalog intentionally leaves this attack implementation unknown'
        elif not best:reason='no compatible runtime attack branch resolved from the owned root components'
        branches.append({'catalogIndex':attack['index'],'name':attack['name'],'kind':attack['kind'],
            'parentAttack':attack.get('parent_attack'),'childAttacks':attack.get('child_attacks') or [],
            'charge':attack.get('charge'),'state':state,'runtimeMatch':best,'unresolvedReason':reason})
    return branches,runtime_attacks


def _candidate_resources(entry):
    values=[]
    for key in ('bestCandidate',):
        if entry.get(key) and entry[key].get('resourceHash'):values.append(entry[key]['resourceHash'])
    groups=('competingCandidates',) if entry.get('runtimeCandidateMatches',0)>0 else ()
    for group in groups:
        for value in entry.get(group) or []:
            resource=value.get('resourceHash')
            if resource and resource not in values:values.append(resource)
    return values


def compose(base_report,mapping,dataset,version='offline-snapshot'):
    assert base_report['writes']==0 and base_report['protectionChanges']==0
    assert base_report['fixtureFallback']=='disabled' and base_report['mode']=='snapshot'
    by_resource={item['resourceHash']:item for item in base_report['runtimeCandidates']}
    weapons=[];settings=defaultdict(lambda:{'weapons':set(),'resources':set(),'kind':None})
    catalog_counts=Counter();resolved_counts=Counter()
    for weapon in dataset['weapons']:
        entry=mapping[weapon['name']];resources=_candidate_resources(entry)
        candidates=[by_resource[value] for value in resources if value in by_resource]
        unique=entry['resolution']=='UNIQUE'
        branches,runtime_attacks=_branch_graph(weapon,candidates,unique)
        for branch in branches:
            catalog_counts[branch['kind']]+=1
            if branch['state']=='RESOLVED':resolved_counts[branch['kind']]+=1
        components=[]
        for candidate in candidates:
            for name,owner in sorted((candidate.get('ownership') or {}).items()):
                components.append({'resourceHash':candidate['resourceHash'],'component':name,
                    'componentType':owner.get('componentType'),'recordIndex':owner.get('recordIndex'),
                    'uniqueOwner':owner.get('uniqueOwner'),'ownerCount':owner.get('ownerCount')})
            for attack in candidate.get('attacks') or []:
                for label,key in (('projectile','projectileSettings'),('damage','damageInfo'),
                                  ('arc','arcSettings'),('beam','beamSettings')):
                    record=attack.get(key)
                    if record:
                        identity=':'.join(map(str,(record.get('settingsType'),record.get('group'),
                                                  record.get('row'),record.get('recordType'))))
                        settings[identity]['kind']=label;settings[identity]['weapons'].add(weapon['name'])
                        settings[identity]['resources'].add(candidate['resourceHash'])
        ammo=[]
        for candidate in candidates:
            ammo.append({'resourceHash':candidate['resourceHash'],'ownership':candidate.get('ammo'),
                'backpackDependencyCatalogued':weapon.get('backpack_dependent')==True,
                'backpackRuntimeOwnershipProven':False})
        unresolved=[]
        if weapon.get('backpack_dependent'):unresolved.append('backpack ammo/storage component ownership')
        unresolved.extend(branch['name']+': '+branch['unresolvedReason'] for branch in branches
                          if branch.get('unresolvedReason'))
        weapons.append({'catalogIdentity':weapon['name'],'slot':'support','sourceSection':weapon.get('source_section'),
            'weaponType':weapon.get('weapon_type'),'traits':weapon.get('traits') or [],
            'confidence':entry['status'],'identityResolution':entry['resolution'],
            'partialCandidateCount':entry.get('partialRuntimeCandidateMatches',0),
            'resourceHashes':resources,'canonicalResourceHash':resources[0] if unique and resources else None,
            'weaponComponents':components,'catalogAttackCount':len(weapon['attacks']),
            'attackGraph':branches,'runtimeAttacks':runtime_attacks,'relationships':weapon.get('relationships') or [],
            'ammoFeedMagazine':ammo,'backpackDependent':weapon.get('backpack_dependent')==True,
            'expendable':weapon.get('expendable')==True,'firingModes':weapon.get('firing_modes') or [],
            'selectableAmmoModes':weapon.get('selectable_ammo_modes') or [],
            'sharedness':{'componentRecordsShared':any(x.get('ownerCount',1)>1 for x in components)},
            'unresolvedLinks':unresolved,'readOnlyResolutionReady':unique,
            'guardedAuthoringReady':False,
            'authoringReason':'support descriptors are not promoted until live ownership and unresolved attack/feed links are validated'})
    weapons.sort(key=lambda item:item['catalogIdentity'])
    shared=[]
    for identity,value in settings.items():
        if len(value['weapons'])>1:
            shared.append({'settingsIdentity':identity,'kind':value['kind'],
                'weapons':sorted(value['weapons']),'resourceHashes':sorted(value['resources'])})
    shared.sort(key=lambda item:(item['kind'],item['settingsIdentity']))
    resolution=Counter(item['identityResolution'] for item in weapons)
    confidence=Counter(item['confidence'] for item in weapons)
    source_groups=Counter(item['sourceSection'] for item in weapons)
    summary={'catalogWeapons':len(weapons),'resolvedIdentities':sum(1 for x in weapons if x['identityResolution'] in ('UNIQUE','DUPLICATE')),
        'uniqueIdentities':resolution['UNIQUE'],'duplicateIdentityGroups':resolution['DUPLICATE'],
        'ambiguousIdentities':resolution['AMBIGUOUS'],'unresolvedIdentities':resolution['UNRESOLVED'],
        'identityStatusCounts':{key:confidence[key] for key in ('EXACT','STRONG','AMBIGUOUS','UNMATCHED')},
        'sourceGroupCounts':dict(sorted(source_groups.items())),
        'catalogBranchCounts':{kind:catalog_counts[kind] for kind in KINDS},
        'resolvedBranchCounts':{kind:resolved_counts[kind] for kind in KINDS},
        'sharedSettingsGroups':len(shared),'backpackDependentWeapons':sum(x['backpackDependent'] for x in weapons),
        'readOnlySemanticResolutionReady':resolution['UNIQUE'],'guardedAuthoringReady':False,
        'unresolvedWeapons':[x['catalogIdentity'] for x in weapons if x['identityResolution'] not in ('UNIQUE','DUPLICATE')]}
    return {'schemaVersion':1,'mode':'snapshot','hd2RuntimeVersion':version,
        'gameFingerprints':base_report['gameFingerprints'],'wikiDataset':base_report['wikiDataset'],
        'scanMetrics':base_report['scanMetrics'],'summary':summary,'sharedSettingsGroups':shared,
        'structurallyProvenDomains':['WeaponDataComponentData','ProjectileWeaponComponentData',
            'WeaponMagazineComponentData','WeaponRoundsComponentData','WeaponCustomizationComponentData',
            'ProjectileSettings','DamageInfo','ArcWeaponComponentData','ArcSettings',
            'BeamWeaponComponentData','BeamSettings','SprayWeaponComponentData','MeleeWeaponComponentData'],
        'unmappedDomains':['ExplosionSettings','status settings ownership','backblast root ownership',
            'backpack ammo/storage ownership','charge/alternate-fire selection ownership'],
        'apiDirection':{'root':'hd2.support_weapon(name)','branches':['attacks()','attack(role_or_name)',
            'projectile(role_or_name)','explosion(role_or_name)'],'finalized':False},
        'weapons':weapons,'writes':0,'protectionChanges':0,'fixtureFallback':'disabled'}


def write_outputs(report,path):
    path=Path(path);path.write_text(json.dumps(report,indent=2)+'\n')
    identities={item['catalogIdentity']:{'status':item['confidence'],
        'resolution':item['identityResolution'],'resourceHashes':item['resourceHashes'],
        'canonicalResourceHash':item['canonicalResourceHash']} for item in report['weapons']}
    mapping=path.with_name(path.stem+'.identity-candidates.json')
    mapping.write_text(json.dumps(identities,indent=2)+'\n')
    summary=path.with_name('support_weapon_identity_summary.json')
    summary.write_text(json.dumps(report['summary'],indent=2)+'\n')
    log=path.with_suffix('.log')
    lines=[f"SUPPORT_WEAPON_MAP catalog=35 candidates={report['scanMetrics']['candidateCount']} mode=snapshot"]
    for item in report['weapons']:
        lines.append(f"SUPPORT_WEAPON_MAP weapon=\"{item['catalogIdentity']}\" resolution={item['identityResolution']} status={item['confidence']} resources={len(item['resourceHashes'])} branches={item['catalogAttackCount']}")
    lines.append('SUPPORT_WEAPON_MAP complete writes=0 protection_changes=0 fixture_fallback=disabled')
    log.write_text('\n'.join(lines)+'\n')
    return path,mapping,summary,log
