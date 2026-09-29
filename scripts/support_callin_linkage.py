"""Derive reviewed support-weapon <-> call-in stratagem linkage from retained native evidence.

The relationship is proven structurally: a support StratagemDefinition's primary
payload is either the support weapon's own runtime root (a spawned silo) or a
hellpod rack whose attached resources include one of the support weapon's
runtime resources. Display names never establish a link; the historical
stratagem debug-name table is only cross-checked after the structural join.

Native hashes are used solely to join evidence here. Every public value is a
semantic key, display name, or classification.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
STRATAGEM_RESEARCH=ROOT/'research/offensive-stratagem-runtime-F5FEE03DCFDB.json'
SUPPORT_RESEARCH=ROOT/'research/support-weapon-runtime-F5FEE03DCFDB.json'
COVERAGE_RESEARCH=ROOT/'research/support-weapon-coverage-F5FEE03DCFDB.json'
EQUIPMENT_RESEARCH=ROOT/'research/support-equipment-links-F5FEE03DCFDB.json'
RESOLVED_STATES=('UNIQUE','DELIVERY_RESOLVED')
CONTRACT='hd2runtime.support_callin_linkage.v1'
SCHEMA_VERSION=1


def digest(value,length=16):
    encoded=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(encoded).hexdigest()[:length]


def slug(value):
    return re.sub(r'[^a-z0-9]+','-',str(value).lower()).strip('-')or'root'


def support_weapon_key(name):
    return 'support-weapon/v1/'+slug(name)+'/'+digest(name)


def stratagem_key(name):
    return 'stratagem/v1/'+slug(name)+'/'+digest(name)


def relationship_key(stratagem,weapon):
    return ('support-callin/v1/'+slug(weapon)+'/'
        +digest({'stratagem':stratagem_key(stratagem),'supportWeapon':support_weapon_key(weapon)}))


EVIDENCE={
    'stratagem_payload_is_support_root':
        'The call-in StratagemDefinition primary payload is the support weapon runtime root.',
    'hellpod_rack_attaches_support_weapon':
        'The call-in StratagemDefinition primary payload is a hellpod rack that attaches a runtime resource of the support weapon.',
    'hellpod_rack_attaches_attack_entity':
        'The call-in delivery rack attaches the support weapon attack-owner entity.',
    'loadout_item_id_is_call_in_id':
        'The support weapon LoadoutEntryComponent item id is the call-in StratagemDefinition id.',
    'call_in_package_owns_support_weapon':
        ('The call-in StratagemDefinition resource package is the support weapon loadout package, and that '
         'package is owned only by the call-in rack, the entities the rack attaches, and the support weapon.'),
}
NO_CALL_IN_EVIDENCE={
    'loadout_item_roots':
        'Every catalog root of the item is a native loadout item (LoadoutEntryComponent present).',
    'loadout_item_id_matches_no_stratagem':
        'No StratagemDefinition carries the loadout item id of any of its roots.',
    'loadout_package_named_by_no_stratagem':
        'No StratagemDefinition names the loadout package of any of its roots.',
    'no_native_delivery_reference':
        ('No hellpod rack, deposit, entity delta, or other entity record references any of its roots; '
         'the only occurrences are the roots\' own registry and component rows.'),
}
NO_CALL_IN_REASON=('The game defines no call-in StratagemDefinition for this item: no stratagem carries its loadout '
    'item id or names its loadout package, and no rack or other native record delivers it. It is not a '
    'player-callable stratagem; the catalog lists it as equipment found during missions.')


def placed_item_graph(stratagem,weapon,companions):
    """Call-in -> rack items -> the placed item the support-weapon view owns, by reference.

    The rack-delivered thrower and backpack have no authoring view of their own; they stay
    separate native-only nodes so the placed item is never flattened into its delivery.
    """
    name=weapon['catalogIdentity'];stratagem_id=stratagem_key(stratagem)
    weapon_id=support_weapon_key(name)
    nodes=[{'node':'call_in','parent':None,'view':'stratagem','semanticId':stratagem_id,
        'targetPath':'stratagem','attackRole':None,'object':'stratagem_definition',
        'fields':['stratagem.cooldown','stratagem.max_uses']}]
    for kind in companions:
        nodes.append({'node':'delivery:'+kind,'parent':'call_in','view':None,'semanticId':None,
            'targetPath':None,'attackRole':None,'object':kind,'nativeRole':'hellpod_rack_item','fields':None})
    nodes.append({'node':'placed_item','parent':'delivery:thrower'if'thrower'in companions else'call_in',
        'view':'support_weapon','semanticId':weapon_id,'targetPath':'weapon','attackRole':None,
        'object':'placed_charge','nativeRole':'loadout_item_of_call_in','fields':None})
    for branch in weapon['attackGraph']:
        role=(branch.get('runtimeMatch')or{}).get('runtimeAttackRole')
        path={'Projectile':'projectile_reference','Explosion':'explosion'}.get(branch['kind'],'attack')
        nodes.append({'node':'branch:'+slug(branch['name']),
            'parent':('branch:'+slug(branch['parentAttack'])if branch.get('parentAttack')else'placed_item'),
            'view':'support_weapon','semanticId':weapon_id,'targetPath':path if role else None,
            'attackRole':role,'object':branch['kind'].lower(),'catalogBranch':branch['name'],
            'state':branch['state'],'fields':None})
    ids=[node['node']for node in nodes]
    assert len(ids)==len(set(ids)),'delivery graph node identities collide: '+name
    return {'composition':'reference','duplicatesFields':False,'nodes':nodes}


def delivery_graph(stratagem,weapon,delivery_object):
    """Compose the two existing semantic views by reference; no fields are copied.

    Each node names the view that owns it (``stratagem`` or ``support_weapon``)
    and the target path/attack role an editor uses to select that view's
    canonical field instances.
    """
    name=weapon['catalogIdentity'];stratagem_id=stratagem_key(stratagem)
    weapon_id=support_weapon_key(name)
    nodes=[{'node':'call_in','parent':None,'view':'stratagem','semanticId':stratagem_id,
            'targetPath':'stratagem','attackRole':None,'object':'stratagem_definition',
            'fields':['stratagem.cooldown','stratagem.max_uses']},
        {'node':'delivery','parent':'call_in','view':'support_weapon','semanticId':weapon_id,
            'targetPath':'weapon','attackRole':None,'object':delivery_object,'fields':None}]
    parent='delivery'
    chain=weapon.get('ownershipChain')or[]
    root_resources=set(weapon['resourceHashes'])
    if any(node['kind']=='placed_or_attack_entity'and node.get('resourceHash')not in root_resources
            for node in chain):
        # The delivered root spawns a separate attack-owner entity (Solo Silo's missile).
        nodes.append({'node':'attack_entity','parent':'delivery','view':'support_weapon',
            'semanticId':weapon_id,'targetPath':None,'attackRole':None,
            'object':'missile'if delivery_object=='deployable_silo'else'attack_entity',
            'fields':None})
        parent='attack_entity'
    for branch in weapon['attackGraph']:
        role=(branch.get('runtimeMatch')or{}).get('runtimeAttackRole')
        path={'Projectile':'projectile_reference','Explosion':'explosion'}.get(branch['kind'],'attack')
        nodes.append({'node':'branch:'+slug(branch['name']),
            'parent':('branch:'+slug(branch['parentAttack'])if branch.get('parentAttack')else parent),
            'view':'support_weapon','semanticId':weapon_id,'targetPath':path if role else None,
            'attackRole':role,'object':branch['kind'].lower(),'catalogBranch':branch['name'],
            'state':branch['state'],'fields':None})
    ids=[node['node']for node in nodes]
    assert len(ids)==len(set(ids)),'delivery graph node identities collide: '+name
    return {'composition':'reference','duplicatesFields':False,'nodes':nodes}


def build(support_roots=None,support_research_path=SUPPORT_RESEARCH,
          stratagem_research_path=STRATAGEM_RESEARCH,equipment_research_path=EQUIPMENT_RESEARCH):
    """Return the canonical linkage document shared by both capability catalogs."""
    if support_roots is None:
        support_roots=json.loads(Path(stratagem_research_path).read_text())['supportRoots']
    research=json.loads(Path(support_research_path).read_text())
    equipment=json.loads(Path(equipment_research_path).read_text())
    loadout={name:{item['resource']:item for item in items}for name,items in equipment['supportWeapons'].items()}
    rack_items={rack:{item['resource']:item for item in items}for rack,items in equipment['rackItems'].items()}
    deposits={(link['deposit'],link['refills'])for link in equipment['depositLinks']}
    focus={name:{item['resource']:item for item in items}for name,items in equipment['focus'].items()}

    def item_ids(weapon):
        return {entry['loadoutEntry']['itemId']for entry in loadout[weapon['catalogIdentity']].values()
            if entry['loadoutEntry']}
    graph=research['nativeSupportGraph']
    racks={rack['resourceHash']:rack for rack in graph['hellpodRacks']}
    backpacks={item['resourceHash']for item in graph['backpackEntities']}
    linkers={item['resourceHash']for item in graph['weaponLinkers']}
    explosives={item['resourceHash']for item in graph['explosiveEntities']}
    weapons=research['weapons']
    assert len(weapons)==35 and len({w['catalogIdentity']for w in weapons})==35

    def weapon_resources(weapon):
        chain={node.get('resourceHash')for node in weapon.get('ownershipChain')or[]
            if node['kind']in('stratagem_payload','spawned_silo')}
        return (set(weapon['resourceHashes'])|chain)-{None}

    def classify(resource):
        # Public delivery composition is described semantically, never by hash.
        for weapon in weapons:
            if resource in weapon_resources(weapon):return 'support_weapon'
            if resource==weapon.get('attackOwnerResourceHash'):return 'attack_entity'
        if resource in backpacks:return 'backpack'
        if resource in linkers:return 'weapon_linker'
        if resource in explosives:return 'explosive_entity'
        return 'unmapped_entity'

    def classify_rack_item(rack,resource,attached):
        # A support loadout item that the delivered backpack's deposit refills is the pack's thrower.
        kind=classify(resource)
        entry=rack_items.get(rack,{}).get(resource)
        if (kind=='unmapped_entity'and entry and entry['loadoutEntry']
                and entry['loadoutEntry']['itemType']=='SupportWeapon'
                and any((other,resource)in deposits for other in attached if classify(other)=='backpack')):
            return 'thrower'
        return kind

    by_root={}
    for root in support_roots:
        if root['resolution']!='UNIQUE':continue
        primary=root['currentRoot']['payloads'][0];rack=racks.get(primary)
        attached=set(rack['attachedResources'])if rack else set()
        matches={}
        for weapon in weapons:
            evidence=[]
            if primary in weapon_resources(weapon):evidence.append('stratagem_payload_is_support_root')
            if attached&weapon_resources(weapon):evidence.append('hellpod_rack_attaches_support_weapon')
            if weapon.get('attackOwnerResourceHash')in attached:
                evidence.append('hellpod_rack_attaches_attack_entity')
            if evidence and root['currentRoot']['id']in item_ids(weapon):
                evidence.append('loadout_item_id_is_call_in_id')
            if evidence:matches[weapon['catalogIdentity']]=evidence
        placed=False
        if not matches and rack:
            # A placed item the rack does not attach. Both must hold: the call-in id is its loadout
            # item id, and the call-in package is its package, owned only by the rack, the rack's
            # items, and the item itself (every rack item also carries that package).
            package=root['currentRoot']['package']
            for weapon in weapons:
                name=weapon['catalogIdentity']
                if root['currentRoot']['id']not in item_ids(weapon)or name not in focus:continue
                entries=focus[name]
                owners={tuple(item['packageOwners'])for item in entries.values()}
                expected=tuple(sorted({primary}|attached|set(entries)))
                if (int(package,16)and all(item['package']==package for item in entries.values())
                        and owners=={expected}
                        and all(rack_items[primary][item]['package']==package for item in attached)):
                    matches[name]=['loadout_item_id_is_call_in_id','call_in_package_owns_support_weapon']
                    placed=True
        # Deterministic, hash-free description of what the call-in delivers.
        delivered=sorted({classify_rack_item(primary,resource,attached)for resource in attached})
        by_root[root['name']]={'matches':matches,'delivered':delivered,
            'rackResolved':rack is not None,'placedItem':placed,
            'primaryIsSupportRoot':any('stratagem_payload_is_support_root'in value
                for value in matches.values())}

    delivered={name for name,item in json.loads(COVERAGE_RESEARCH.read_text())['deliveryResolution'].items()
        if item['decision']=='RESOLVED'}

    def identity_status(weapon):
        # Research-proven call-in delivery plus an exact scraped fingerprint resolves a duplicate group.
        if weapon['identityResolution']=='DUPLICATE'and weapon['catalogIdentity']in delivered:
            return 'DELIVERY_RESOLVED'
        return weapon['identityResolution']

    links=[];weapon_links={};stratagem_links={}
    unresolved_roots={root['name']:root.get('reason')for root in support_roots
        if root['resolution']!='UNIQUE'}
    call_in_ids={root['currentRoot']['id']:root['name']for root in support_roots if root['resolution']=='UNIQUE'}
    all_stratagem_ids={row['id']for row in equipment['stratagemDefinitions']}
    stratagem_packages={row['package']for row in equipment['stratagemDefinitions']}
    no_call_in={}
    for weapon in sorted(weapons,key=lambda item:item['catalogIdentity']):
        name=weapon['catalogIdentity']
        linked=[stratagem for stratagem,entry in by_root.items()if name in entry['matches']]
        if len(linked)>1:
            raise ValueError('support weapon is delivered by more than one call-in: '+name)
        # Independent consistency guard: a loadout item id that names a support call-in must agree
        # with the structural link, or one of the two evidence chains is wrong. A loadout id alone
        # never creates a link.
        for item_id in item_ids(weapon):
            if item_id in call_in_ids and linked and linked!=[call_in_ids[item_id]]:
                raise ValueError('loadout item id names a different call-in than the structural link: '+name)
        if not linked and name in unresolved_roots and name in focus:
            roots=list(focus[name].values())
            if (roots and all(item['loadoutEntry']for item in roots)
                    and all(item['loadoutEntry']['itemId']not in all_stratagem_ids for item in roots)
                    and all(item['package']not in stratagem_packages for item in roots)
                    and all(not item['racksAttaching']and not item['depositsRefilling']
                        and not item['entityLibraryReferences']['external']
                        and item['entityDeltaOccurrences']==0 for item in roots)):
                types=sorted({item['loadoutEntry']['itemType']for item in roots})
                shared=len({item['package']for item in roots})==1 and len(roots)>1
                provenance={'basis':'native_loadout_identity','evidence':sorted(NO_CALL_IN_EVIDENCE),
                    'evidenceDescriptions':[NO_CALL_IN_EVIDENCE[item]for item in sorted(NO_CALL_IN_EVIDENCE)],
                    'displayNameEquality':'not used as evidence',
                    'evidenceArtifacts':[EQUIPMENT_RESEARCH.name]}
                acquisition={'kind':'world_pickup','source':'catalog','nativeDeliveryProven':False,
                    'note':('The catalog procurement text lists it as equipment found at mission points of interest; '
                        'world placement data is not part of the native evidence, so only the absence of a '
                        'call-in is native.')}
                no_call_in[name]={'loadoutItemTypes':types,'sharedLoadoutPackage':shared,
                    'provenance':provenance,'acquisition':acquisition}
                weapon_links[name]={'known':False,'state':'no_call_in','semanticId':None,
                    'relationshipId':None,'relationship':'call_in','stratagemName':None,
                    'confidence':'reviewed','provenance':provenance,'blocker':None,
                    'noCallIn':{'reason':NO_CALL_IN_REASON,'acquisition':acquisition,
                        'loadoutItemTypes':types,'sharedLoadoutPackage':shared}}
                continue
        if not linked:
            if name in unresolved_roots:
                state='unresolved_call_in'
                blocker=('No uniquely correlated call-in StratagemDefinition exists in the retained '
                    'snapshot; the call-in is not guessed.')
            else:
                state='unresolved_delivery'
                blocker=('No resolved call-in StratagemDefinition delivers a runtime resource proven to '
                    'belong to this support weapon; the link is not inferred from display names.')
            weapon_links[name]={'known':False,'state':state,'semanticId':None,
                'relationshipId':None,'relationship':'call_in','stratagemName':None,
                'confidence':None,'provenance':None,'blocker':blocker}
            continue
        stratagem=linked[0];entry=by_root[stratagem]
        if len(entry['matches'])!=1:
            raise ValueError('call-in rack attaches more than one support weapon: '+stratagem)
        evidence=entry['matches'][name]
        # Cross-check the independent historical debug-name correlation; a
        # disagreement means one of the two evidence chains is wrong.
        if stratagem!=name:
            raise ValueError('structural call-in link disagrees with the reviewed stratagem '
                'debug-name correlation: '+stratagem+' -> '+name)
        special=('deployable_silo'if entry['primaryIsSupportRoot']
            else'placed_item'if entry['placedItem']else None)
        relationship_id=relationship_key(stratagem,name)
        provenance={'basis':'native_loadout_identity'if entry['placedItem']else'native_payload_graph',
            'evidence':evidence,'evidenceDescriptions':[EVIDENCE[item]for item in evidence],
            'crossCheck':'historical stratagem debug-name correlation agrees',
            'displayNameEquality':'not used as link evidence',
            'evidenceArtifacts':[STRATAGEM_RESEARCH.name,SUPPORT_RESEARCH.name,EQUIPMENT_RESEARCH.name]}
        delivery_object=('deployable_silo'if special=='deployable_silo'
            else'placed_charge'if special=='placed_item'else'hellpod_support_weapon')
        companions=[{'kind':kind}for kind in entry['delivered']
            if kind not in('support_weapon','attack_entity','weapon_linker')]
        graph=(placed_item_graph(stratagem,weapon,[item['kind']for item in companions])
            if special=='placed_item'else delivery_graph(stratagem,weapon,delivery_object))
        link={'relationshipId':relationship_id,'kind':'support_weapon_callin',
            'relationship':'call_in','stratagem':stratagem_key(stratagem),
            'stratagemName':stratagem,'supportWeapon':support_weapon_key(name),
            'supportWeaponName':name,'deliveryObject':delivery_object,
            'companionDeliveries':companions,'special':special,
            'weaponIdentityStatus':identity_status(weapon),
            'deliveryGraph':graph,
            'confidence':'reviewed','provenance':provenance}
        links.append(link)
        weapon_links[name]={'known':True,'state':'linked','semanticId':stratagem_key(stratagem),
            'relationshipId':relationship_id,'relationship':'call_in',
            'kind':'support_weapon_delivery','stratagemName':stratagem,
            'deliveryObject':delivery_object,'special':special,
            'confidence':'reviewed','provenance':provenance,'blocker':None}
        stratagem_links[stratagem]={'kind':'support_weapon','known':True,'state':'linked',
            'semanticId':support_weapon_key(name),'relationshipId':relationship_id,
            'supportWeaponName':name,'deliveryObject':delivery_object,
            'companionDeliveries':companions,'special':special,
            'confidence':'reviewed','provenance':provenance,'blocker':None}

    for root in support_roots:
        name=root['name']
        if name in stratagem_links:continue
        if name in no_call_in:
            item=no_call_in[name]
            stratagem_links[name]={'kind':'none','known':False,'state':'no_call_in',
                'rootResolution':'NO_CALL_IN','semanticId':None,'relationshipId':None,
                'supportWeaponName':None,'deliveryObject':None,'companionDeliveries':[],'special':None,
                'confidence':'reviewed','provenance':item['provenance'],'blocker':None,
                'noCallIn':{'reason':NO_CALL_IN_REASON,'acquisition':item['acquisition'],
                    'loadoutItemTypes':item['loadoutItemTypes'],
                    'sharedLoadoutPackage':item['sharedLoadoutPackage']}}
            continue
        if root['resolution']!='UNIQUE':
            stratagem_links[name]={'kind':'unresolved','known':False,'state':'unresolved_call_in',
                'semanticId':None,'relationshipId':None,'supportWeaponName':None,
                'deliveryObject':None,'companionDeliveries':[],'special':None,
                'confidence':None,'provenance':None,
                'blocker':'No uniquely correlated call-in StratagemDefinition; delivered object is unknown.'}
            continue
        entry=by_root[name]
        stratagem_links[name]={'kind':'unresolved','known':False,'state':'unresolved_delivery',
            'semanticId':None,'relationshipId':None,'supportWeaponName':None,
            'deliveryObject':None,
            'companionDeliveries':[{'kind':kind}for kind in entry['delivered']],'special':None,
            'confidence':None,'provenance':None,
            'blocker':('The delivery rack attaches no runtime resource proven to belong to a catalog '
                'support weapon; the delivered object is not inferred from display names.')}

    audit=audit_links(links,weapon_links,stratagem_links)
    return {'contract':CONTRACT,'schemaVersion':SCHEMA_VERSION,
        'joinContract':{'supportWeaponKeyProperty':'weapons[].semanticId',
            'stratagemKeyProperty':'stratagems[].semanticId',
            'forwardLinkProperty':'weapons[].linkedStratagem',
            'reverseLinkProperty':'stratagems[].delivers',
            'relationshipCollection':'supportCallInLinks.relationships',
            'mergeKey':'relationshipId',
            'displayNameMatchingRequired':False,
            'rawNativeIdentifiersPublished':False,
            'writeTargetsRemainSeparate':True,
            'writeGuardsUnchanged':('A known relationship alone never lifts support-weapon write blocking. '
                'A duplicate group is resolved only when its call-in rack attaches exactly one candidate root '
                'and an independent proof identifies that same root: scraped magazine values, the call-in '
                'package equal to the root\'s own loadout package, or its hash-verified support-weapon resource '
                'path (DELIVERY_RESOLVED); ambiguous runtime weapon roots stay blocked.')},
        'relationships':links,'supportWeapons':dict(sorted(weapon_links.items())),
        'stratagems':dict(sorted(stratagem_links.items())),'audit':audit}


def audit_links(links,weapon_links,stratagem_links):
    """Require every known link to be exactly bidirectional."""
    mismatches=[]
    by_weapon={link['supportWeaponName']:link for link in links}
    by_stratagem={link['stratagemName']:link for link in links}
    for name,value in weapon_links.items():
        if not value['known']:continue
        reverse=stratagem_links.get(value['stratagemName'])
        if not reverse or not reverse['known']or reverse['semanticId']!=support_weapon_key(name)\
                or reverse['relationshipId']!=value['relationshipId']:
            mismatches.append({'direction':'forward','supportWeapon':name})
    for name,value in stratagem_links.items():
        if not value['known']:continue
        forward=weapon_links.get(value['supportWeaponName'])
        if not forward or not forward['known']or forward['semanticId']!=stratagem_key(name)\
                or forward['relationshipId']!=value['relationshipId']:
            mismatches.append({'direction':'reverse','stratagem':name})
    if len(by_weapon)!=len(links)or len(by_stratagem)!=len(links):
        mismatches.append({'direction':'relationship','reason':'non one-to-one relationship'})
    if mismatches:raise ValueError('support call-in linkage is not bidirectional: '+json.dumps(mismatches))
    ambiguous=[link['supportWeaponName']for link in links if link['weaponIdentityStatus']not in RESOLVED_STATES]
    return {'supportWeapons':len(weapon_links),
        'knownLinks':sum(value['known']for value in weapon_links.values()),
        'unresolvedLinks':sum(value['state'].startswith('unresolved')for value in weapon_links.values()),
        'noCallInItems':sorted(name for name,value in weapon_links.items()if value['state']=='no_call_in'),
        'placedItemLinks':sorted(link['supportWeaponName']for link in links if link['special']=='placed_item'),
        'loadoutIdentityCorroboratedLinks':sum('loadout_item_id_is_call_in_id'in link['provenance']['evidence']
            for link in links),
        'unresolvedCallIns':sorted(name for name,value in weapon_links.items()
            if value['state']=='unresolved_call_in'),
        'unresolvedDeliveries':sorted(name for name,value in weapon_links.items()
            if value['state']=='unresolved_delivery'),
        'supportStratagems':len(stratagem_links),
        'reverseLinksKnown':sum(value['known']for value in stratagem_links.values()),
        'relationships':len(links),
        'bidirectionalMismatches':0,
        'linksRelyingOnDisplayNameOnly':0,
        'ambiguousWeaponIdentityLinks':len(ambiguous),
        'ambiguousWeaponIdentityNames':sorted(ambiguous),
        'specialLinks':sorted(link['supportWeaponName']for link in links if link['special'])}
