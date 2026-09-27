"""Graph-aware support-weapon report built from the shared read-only mapper."""
from __future__ import annotations

from collections import Counter,defaultdict
from copy import deepcopy
import json
from pathlib import Path

KINDS=('Projectile','Explosion','Beam','Arc','Spray','Melee','Status','Unknown')
FIELDS=('standard_damage','durable_damage','ap_direct','ap_slight','ap_large','ap_extreme',
        'demolition','stagger','push_force','projectile_velocity','projectile_mass','drag',
        'gravity','pellet_count','explosion_inner_radius','explosion_outer_radius',
        'explosion_shockwave_radius','arc_range','arc_velocity','arc_spread','arc_chain_spread',
        'arc_chain_count','arc_max_split','status_strength','status_duration')
TOLERANCE={'projectile_velocity':2,'projectile_mass':.1,'drag':.01,'gravity':.01,
    'explosion_inner_radius':.01,'explosion_outer_radius':.01,'explosion_shockwave_radius':.01,
    'arc_range':.01,'arc_velocity':.01,'arc_spread':.01,'arc_chain_spread':.01,
    'status_strength':.01,'status_duration':.01}


def _compare(runtime,attack):
    if runtime.get('kind') != attack.get('kind'):return None
    values=runtime.get('resolvedFields') or {};matched=[];mismatched=[]
    for field in FIELDS:
        actual,want=values.get(field),attack.get(field)
        if not isinstance(actual,(int,float)) or not isinstance(want,(int,float)):continue
        tolerance=TOLERANCE.get(field,0)
        (matched if abs(actual-want)<=tolerance else mismatched).append(field)
    return {'runtimeAttackRole':runtime.get('role'),'runtimeAttackKind':runtime.get('kind'),
            'runtimeParentRole':runtime.get('parentRole'),
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
        minimum=2 if attack['kind']=='Status'and attack.get('parent_attack')and best and best.get('runtimeParentRole') else 3
        if identity_unique and best and not best['mismatchedFields'] and best['compared']>=minimum:state='RESOLVED'
        elif best:state='PARTIAL' if identity_unique else 'IDENTITY_AMBIGUOUS'
        reason=None
        if state!='RESOLVED'and attack['kind']=='Explosion':reason='no structurally linked ExplosionSettings branch matched this catalog branch'
        elif state!='RESOLVED'and attack['kind']=='Status':reason='no structurally linked StatusEffectSettings branch matched this catalog branch'
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


def _complete_exact_branch_cover(catalog_attacks,runtime_attacks):
    """Return deterministic one-to-one coverage without using scalar-only roots."""
    usable=[attack for attack in catalog_attacks if attack['kind'] not in ('Status','Unknown')]
    choices=[]
    for catalog in usable:
        rows=[]
        for index,runtime in enumerate(runtime_attacks):
            compared=_compare(runtime,catalog)
            if compared and not compared['mismatchedFields'] and compared['compared']>=3:
                rows.append((index,compared))
        if not rows:return None
        choices.append(rows)
    order=sorted(range(len(choices)),key=lambda index:(len(choices[index]),index))
    def assign(at,used,result):
        if at==len(order):return result
        catalog_index=order[at]
        for runtime_index,compared in choices[catalog_index]:
            if runtime_index not in used:
                found=assign(at+1,used|{runtime_index},result|{catalog_index:(runtime_index,compared)})
                if found is not None:return found
        return None
    return assign(0,set(),{})


def _native_explosive_matches(base_report,dataset):
    graph=base_report.get('supportGraph') or {};nodes=graph.get('explosiveEntities') or []
    racks=graph.get('hellpodRacks') or [];stratagems=graph.get('stratagems') or []
    possible=defaultdict(list)
    for weapon in dataset['weapons']:
        material=[attack for attack in weapon['attacks'] if attack['kind'] not in ('Status','Unknown')]
        if not material or any(attack['kind']!='Explosion' for attack in material):continue
        for node in nodes:
            cover=_complete_exact_branch_cover(material,node.get('attacks') or [])
            if cover is not None and len(material)==len(node.get('attacks') or []):
                root=node['resourceHash'];chain=[{'kind':'placed_or_attack_entity','resourceHash':root}]
                for rack in racks:
                    if node['resourceHash'] in (rack.get('attachedResources') or []):
                        root=rack['resourceHash'];chain.insert(0,{'kind':'spawned_silo','resourceHash':root,
                            'component':'HellpodRackComponentData'})
                        owners=[record for record in stratagems if root in (record.get('payloads') or [])]
                        for owner in owners:
                            chain.insert(0,{'kind':'stratagem_payload','recordKind':owner['record_kind'],
                                'id':owner['id'],'package':owner['package'],'resourceHash':root})
                candidate=deepcopy(node);candidate['resourceHash']=root
                candidate['attackOwnerResourceHash']=node['resourceHash'];candidate['ownershipChain']=chain
                possible[weapon['name']].append(candidate)
    # Require a graph node to identify one catalog weapon and a weapon to identify one node.
    node_use=Counter(candidate['attackOwnerResourceHash'] for values in possible.values() for candidate in values)
    return {name:values[0] for name,values in possible.items()
        if len(values)==1 and node_use[values[0]['attackOwnerResourceHash']]==1}


def _promote_linked_graph(weapon,entry,candidate):
    if entry.get('resolution')!='AMBIGUOUS'or entry.get('partialRuntimeCandidateMatches')!=1:return False
    mismatches=(entry.get('bestCandidate') or {}).get('mismatched') or []
    if not mismatches or any(not value.startswith('fire rate ') for value in mismatches):return False
    attacks=candidate.get('attacks') or []
    if not any(attack.get('kind')=='Explosion'and attack.get('parentRole') for attack in attacks):return False
    return _complete_exact_branch_cover(weapon['attacks'],attacks) is not None


def compose(base_report,mapping,dataset,version='offline-snapshot'):
    assert base_report['writes']==0 and base_report['protectionChanges']==0
    assert base_report['fixtureFallback']=='disabled' and base_report['mode']=='snapshot'
    by_resource={item['resourceHash']:item for item in base_report['runtimeCandidates']}
    native_explosives=_native_explosive_matches(base_report,dataset)
    graph=base_report.get('supportGraph') or {}
    linked_ammo={item['resourceHash']:item for item in graph.get('linkedAmmoOwners') or []}
    weapons=[];settings=defaultdict(lambda:{'weapons':set(),'resources':set(),'kind':None})
    catalog_counts=Counter();resolved_counts=Counter()
    for weapon in dataset['weapons']:
        entry=deepcopy(mapping[weapon['name']]);resolution_basis='shared_weapon_mapper'
        native=native_explosives.get(weapon['name'])
        if native and entry['resolution'] in ('UNRESOLVED','AMBIGUOUS'):
            entry.update(resolution='UNIQUE',status='EXACT',runtimeCandidateMatches=1,
                partialRuntimeCandidateMatches=0)
            resources=[native['resourceHash']];candidates=[native]
            resolution_basis='native_explosive_ownership_graph'
        else:
            resources=_candidate_resources(entry)
            candidates=[by_resource[value] for value in resources if value in by_resource]
            material=[attack for attack in weapon['attacks'] if attack['kind'] not in ('Status','Unknown')]
            if entry['resolution']=='DUPLICATE'and material and all(a['kind']=='Melee' for a in material):
                exact=[candidate for candidate in candidates
                    if _complete_exact_branch_cover(material,candidate.get('attacks') or []) is not None]
                if exact:
                    candidates=exact;resources=[candidate['resourceHash'] for candidate in candidates]
                    entry['resolution']='UNIQUE'if len(candidates)==1 else'DUPLICATE'
                    entry['status']='EXACT'if len(candidates)==1 else'AMBIGUOUS'
                    resolution_basis='native_melee_exact_fingerprint'
            if len(candidates)==1 and _promote_linked_graph(weapon,entry,candidates[0]):
                entry['resolution']='UNIQUE';entry['status']='STRONG'
                resolution_basis='linked_projectile_explosion_graph_with_rate_diagnostic'
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
                                  ('explosion','explosionSettings'),('status','statusSettings'),
                                  ('arc','arcSettings'),('beam','beamSettings')):
                    record=attack.get(key)
                    if record:
                        identity=':'.join(map(str,(record.get('settingsType'),record.get('group'),
                                                  record.get('row'),record.get('recordType'))))
                        settings[identity]['kind']=label;settings[identity]['weapons'].add(weapon['name'])
                        settings[identity]['resources'].add(candidate['resourceHash'])
        ammo=[]
        for candidate in candidates:
            linked=linked_ammo.get(candidate['resourceHash'])
            ammo.append({'resourceHash':candidate['resourceHash'],'ownership':candidate.get('ammo'),
                'backpackDependencyCatalogued':weapon.get('backpack_dependent')==True,
                'weaponLinkedAmmoComponentOwned':linked is not None,
                'weaponLinkedAmmo':linked,'backpackRuntimeOwnershipProven':False})
        unresolved=[]
        if weapon.get('backpack_dependent'):
            unresolved.append('backpack entity/package ownership link (weapon-side linked-ammo ownership is reported separately)')
        unresolved.extend(branch['name']+': '+branch['unresolvedReason'] for branch in branches
                          if branch.get('unresolvedReason'))
        weapons.append({'catalogIdentity':weapon['name'],'slot':'support','sourceSection':weapon.get('source_section'),
            'weaponType':weapon.get('weapon_type'),'traits':weapon.get('traits') or [],
            'confidence':entry['status'],'identityResolution':entry['resolution'],
            'identityResolutionBasis':resolution_basis,
            'partialCandidateCount':entry.get('partialRuntimeCandidateMatches',0),
            'resourceHashes':resources,'canonicalResourceHash':resources[0] if unique and resources else None,
            'weaponComponents':components,'catalogAttackCount':len(weapon['attacks']),
            'attackGraph':branches,'runtimeAttacks':runtime_attacks,'relationships':weapon.get('relationships') or [],
            'fireRateDiagnostics':[{'resourceHash':candidate['resourceHash'],
                'runtimeOptions':candidate.get('fireRateOptions'),
                'catalogValue':weapon.get('fire_rate'),
                'matcherDisagreements':(entry.get('bestCandidate') or {}).get('mismatched') or [],
                'diagnosticOnly':candidate.get('chargeCadence') is not None or resolution_basis=='linked_projectile_explosion_graph_with_rate_diagnostic'}
                for candidate in candidates if candidate.get('fireRateOptions') or candidate.get('chargeCadence')],
            'chargeCadence':[{'resourceHash':candidate['resourceHash'],'value':candidate.get('chargeCadence')}
                for candidate in candidates if candidate.get('chargeCadence')],
            'ownershipChain':native.get('ownershipChain') if native else [],
            'attackOwnerResourceHash':native.get('attackOwnerResourceHash') if native else None,
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
    backpack_with_linked_ammo=sum(1 for item in weapons if item['backpackDependent']
        and any(ammo.get('weaponLinkedAmmoComponentOwned') for ammo in item['ammoFeedMagazine']))
    summary={'catalogWeapons':len(weapons),'resolvedIdentities':sum(1 for x in weapons if x['identityResolution'] in ('UNIQUE','DUPLICATE')),
        'uniqueIdentities':resolution['UNIQUE'],'duplicateIdentityGroups':resolution['DUPLICATE'],
        'ambiguousIdentities':resolution['AMBIGUOUS'],'unresolvedIdentities':resolution['UNRESOLVED'],
        'identityStatusCounts':{key:confidence[key] for key in ('EXACT','STRONG','AMBIGUOUS','UNMATCHED')},
        'sourceGroupCounts':dict(sorted(source_groups.items())),
        'catalogBranchCounts':{kind:catalog_counts[kind] for kind in KINDS},
        'resolvedBranchCounts':{kind:resolved_counts[kind] for kind in KINDS},
        'sharedSettingsGroups':len(shared),'backpackDependentWeapons':sum(x['backpackDependent'] for x in weapons),
        'backpackWeaponsWithWeaponLinkedAmmoOwnership':backpack_with_linked_ammo,
        'backpackEntityLinksProven':0,
        'readOnlySemanticResolutionReady':resolution['UNIQUE'],'guardedAuthoringReady':False,
        'unresolvedWeapons':[x['catalogIdentity'] for x in weapons if x['identityResolution'] not in ('UNIQUE','DUPLICATE')]}
    return {'schemaVersion':1,'mode':'snapshot','hd2RuntimeVersion':version,
        'gameFingerprints':base_report['gameFingerprints'],'wikiDataset':base_report['wikiDataset'],
        'scanMetrics':base_report['scanMetrics'],'summary':summary,'sharedSettingsGroups':shared,
        'nativeSupportGraph':graph,
        'structurallyProvenDomains':['WeaponDataComponentData','ProjectileWeaponComponentData',
            'WeaponMagazineComponentData','WeaponRoundsComponentData','WeaponCustomizationComponentData',
            'ProjectileSettings','DamageInfo','ArcWeaponComponentData','ArcSettings',
            'BeamWeaponComponentData','BeamSettings','SprayWeaponComponentData','MeleeWeaponComponentData',
            'WeaponChargeComponentData','ExplosionSettings','StatusEffectSettings',
            'ExplosiveComponentData','HellpodRackComponentData','WeaponLinkedAmmoComponentData'],
        'unmappedDomains':['standalone backblast root ownership',
            'backpack entity/package link from WeaponLinkedAmmoComponentData',
            'charge cadence native consumer semantics','alternate-fire selection ownership'],
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
