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
}


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
          stratagem_research_path=STRATAGEM_RESEARCH):
    """Return the canonical linkage document shared by both capability catalogs."""
    if support_roots is None:
        support_roots=json.loads(Path(stratagem_research_path).read_text())['supportRoots']
    research=json.loads(Path(support_research_path).read_text())
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
            if evidence:matches[weapon['catalogIdentity']]=evidence
        # Deterministic, hash-free description of what the call-in delivers.
        delivered=sorted({classify(resource)for resource in attached})
        by_root[root['name']]={'matches':matches,'delivered':delivered,
            'rackResolved':rack is not None,
            'primaryIsSupportRoot':any('stratagem_payload_is_support_root'in value
                for value in matches.values())}

    links=[];weapon_links={};stratagem_links={}
    unresolved_roots={root['name']:root.get('reason')for root in support_roots
        if root['resolution']!='UNIQUE'}
    for weapon in sorted(weapons,key=lambda item:item['catalogIdentity']):
        name=weapon['catalogIdentity']
        linked=[stratagem for stratagem,entry in by_root.items()if name in entry['matches']]
        if len(linked)>1:
            raise ValueError('support weapon is delivered by more than one call-in: '+name)
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
        special='deployable_silo'if entry['primaryIsSupportRoot']else None
        relationship_id=relationship_key(stratagem,name)
        provenance={'basis':'native_payload_graph','evidence':evidence,
            'evidenceDescriptions':[EVIDENCE[item]for item in evidence],
            'crossCheck':'historical stratagem debug-name correlation agrees',
            'displayNameEquality':'not used as link evidence',
            'evidenceArtifacts':[STRATAGEM_RESEARCH.name,SUPPORT_RESEARCH.name]}
        delivery_object='deployable_silo'if special else'hellpod_support_weapon'
        companions=[{'kind':kind}for kind in entry['delivered']
            if kind not in('support_weapon','attack_entity','weapon_linker')]
        link={'relationshipId':relationship_id,'kind':'support_weapon_callin',
            'relationship':'call_in','stratagem':stratagem_key(stratagem),
            'stratagemName':stratagem,'supportWeapon':support_weapon_key(name),
            'supportWeaponName':name,'deliveryObject':delivery_object,
            'companionDeliveries':companions,'special':special,
            'weaponIdentityStatus':weapon['identityResolution'],
            'deliveryGraph':delivery_graph(stratagem,weapon,delivery_object),
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
            'writeGuardsUnchanged':('A known relationship never lifts support-weapon write blocking; '
                'ambiguous runtime weapon roots stay blocked.')},
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
    ambiguous=[link['supportWeaponName']for link in links if link['weaponIdentityStatus']!='UNIQUE']
    return {'supportWeapons':len(weapon_links),
        'knownLinks':sum(value['known']for value in weapon_links.values()),
        'unresolvedLinks':sum(not value['known']for value in weapon_links.values()),
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
