"""Generate guarded stratagem authoring metadata from retained native research."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'build/offensive-stratagem-research.json'
FIELDS = ROOT / 'schemas/stratagem_fields.json'
PLAYER_FIELDS = ROOT / 'schemas/player_weapon_fields.json'
INTERNAL = ROOT / 'schemas/stratagem_authoring_catalog.json'
LUA = ROOT / 'domains/stratagem_authoring.lua'
PUBLIC = ROOT / 'sdk/StratagemAuthoringCapabilities.json'
RESEARCH = ROOT / 'research/offensive-stratagem-runtime-F5FEE03DCFDB.json'


def lua(value):
    if isinstance(value, dict):
        return '{' + ','.join('[' + lua(k) + ']=' + lua(v) for k, v in value.items()) + '}'
    if isinstance(value, list):
        return '{' + ','.join(lua(v) for v in value) + '}'
    if isinstance(value, bool): return 'true' if value else 'false'
    if value is None: return 'nil'
    if isinstance(value, (int, float)): return repr(value)
    return json.dumps(str(value), ensure_ascii=False)


def slug(value):
    return re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')


def opaque(kind, native):
    digest = hashlib.sha256(f'{kind}:{native}'.encode()).hexdigest()[:16]
    return f'{kind.lower()}:{digest}'


def api_constant(field_id):
    domain,name=field_id.split('.',1);constant=name.replace('.','_')
    if field_id=='stratagem.cooldown': constant='definition_cooldown'
    if field_id in ('damage.standard_damage','damage.durable_damage'):
        constant='player_'+constant
    return f'hd2.fields.{domain}.{constant}'


def build():
    source = json.loads((INPUT if INPUT.exists() else RESEARCH).read_text())
    defs = {x['id']: x for path in (FIELDS, PLAYER_FIELDS)
            for x in json.loads(path.read_text())['fields']}
    internal = {'schemaVersion': 1, 'sourceSnapshot': source['source']['snapshot'],
        'safety': {k: source['source'][k] for k in ('mode','writes','protectionChanges','fixtureFallback')},
        'stratagems': {}, 'eagleRearm': source['systemRoots']['eagleRearm']}

    consumers = defaultdict(list)
    for item in source['stratagems']:
        for node in item['nativeGraph']:
            native = node.get('recordType')
            if native is not None:
                consumers[(node['kind'], native)].append({'stratagem': item['name'], 'path': node['path']})

    public_stratagems = []
    field_instances = []
    attack_instances = []
    semantic_branches = []
    eagle_names = [x['name'] for x in source['stratagems'] if x['family'] == 'Eagle']

    def add_field(entry, field_id, baseline, backing, target, writable=True, reason=None,
                  provenance='current-build retained snapshot plus schema-labelled native ownership'):
        definition = defs[field_id]
        target_identity = target['path'] + (':' + target['attack'] if target.get('attack') else '')
        instance_key = f"stratagem:{slug(entry['name'])}:{slug(target_identity)}:{field_id}"
        native_identity = backing['nativeIdentity']
        object_key = opaque(backing['kind'], native_identity)
        scope = backing.get('consumers', [{'stratagem': entry['name'], 'path': target['path']}])
        settings_object = backing['kind'] in ('ProjectileSettings','DamageInfo',
            'ExplosionSettings','StatusEffectSettings')
        shared = len(scope) > 1 or settings_object
        descriptor = {'instanceKey': instance_key, 'semanticFieldId': field_id,
            'displayName': definition['display_name'], 'type': definition['type'],
            'unit': definition.get('unit'), 'currentDefault': baseline,
            'editable': writable and definition.get('writable', False),
            'reason': reason or definition.get('reason'), 'target': target,
            'backing': dict(backing), 'backingObjectId': object_key,
            'operationGroup': object_key, 'planGroup': f"plan:stratagem:{slug(entry['name'])}",
            'requires': 'patch_or_transaction',
            'allowSharedRequired': shared, 'shared': shared, 'sharedConsumers': scope,
            'reviewedScopeComplete': True, 'dynamicConsumersPossible': settings_object,
            'provenance': provenance}
        entry['fields'].append(descriptor)
        public = {k: descriptor[k] for k in ('instanceKey','semanticFieldId','displayName','type','unit',
            'currentDefault','editable','reason','target','backingObjectId','operationGroup','planGroup',
            'requires','allowSharedRequired','shared','sharedConsumers','reviewedScopeComplete',
            'dynamicConsumersPossible','provenance')}
        public['backingObjectKind'] = backing['kind']
        public['apiFieldConstant'] = api_constant(field_id)
        public['domain'] = field_id.split('.')[0]
        public['planPhase'] = backing.get('phase', 1)
        public['dependsOn'] = backing.get('dependsOn', [])
        field_instances.append(public)

    for item in source['stratagems']:
        root = item['currentRoot']; entry = {'name': item['name'], 'family': item['family'].lower(),
            'rootResolution': 'UNIQUE', 'root': {'id': root['id'], 'package': root['package'],
                'payloads': root['payloads'], 'group': root['group'], 'row': root['row']},
            'fields': [], 'attacks': {}, 'rootProjectiles': item['rootProjectiles'],
            'graph': item['nativeGraph']}
        components = [component for report in item['payloadReports'] for component in report['components']]
        for branch in item.get('importedBranches',[]):
            semantic_branches.append(dict(branch,stratagem=item['name'],family=item['family'].lower(),
                correlation='descriptive branch preserved; writable fields are declared only by nativeGraph objects'))
        preferred = ('OrbitalAbilityComponentData' if item['name'].startswith('Orbital Laser')
            or item['name'].startswith('Orbital Railcannon') else
            'ProjectileWeaponComponentData' if item['name'] == 'Eagle Strafing Run' else
            'EagleComponentData' if item['family'] == 'Eagle' else 'BombardmentComponentData')
        component = next(component for component in components if component['name'] == preferred)
        entry['rootLink'] = {'payload':item['currentRoot']['payloads'][0], 'component':preferred,
            'recordIndex':component['recordIndex'],'indexRow':component['indexRow']}
        root_scope = [{'stratagem': item['name'], 'path': 'stratagem'}]
        add_field(entry, 'stratagem.cooldown', root['cooldown'],
            {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':104,'storage':'f32',
             'width':4,'consumers':root_scope},
            {'resource':'stratagem','stratagem':item['name'],'path':'stratagem'})
        max_value = None if root['use_count'] == 4294967295 else root['use_count']
        add_field(entry, 'stratagem.max_uses', max_value,
            {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':80,'storage':'u32',
             'width':4,'consumers':root_scope},
            {'resource':'stratagem','stratagem':item['name'],'path':'stratagem'}, False)
        if item['family'] == 'Eagle':
            add_field(entry, 'eagle.uses_per_rearm', root['use_count'],
                {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':80,'storage':'u32',
                 'width':4,'consumers':root_scope},
                {'resource':'stratagem','stratagem':item['name'],'path':'stratagem'})
            rearm = source['systemRoots']['eagleRearm']['currentRoot']
            rearm_scope = [{'stratagem': name, 'path':'eagle_rearm'} for name in eagle_names]
            add_field(entry, 'eagle.rearm_time', rearm['cooldown'],
                {'kind':'StratagemDefinition','nativeIdentity':rearm['id'],'offset':104,'storage':'f32',
                 'width':4,'consumers':rearm_scope},
                {'resource':'stratagem','stratagem':item['name'],'path':'eagle_rearm'})

        for index, node in enumerate(item['nativeGraph'], 1):
            role = slug(node['path'])
            if role in entry['attacks']:
                role += '_' + str(index)
            attack = {'role': role, 'path': node['path'], 'kind': node['kind'],
                'parentRole': slug(node['path'].rsplit('/',1)[0]) if '/' in node['path'] else None,
                'fields': []}
            entry['attacks'][role] = attack
            attack_instances.append({'stratagem':item['name'],'family':item['family'].lower(),
                'role':role,'path':node['path'],'kind':node['kind'],'parentRole':attack['parentRole']})
            for original_id, baseline in node.get('fields', {}).items():
                field_id = original_id
                if node['linkage'] == 'explosion_damage' and field_id.startswith('damage.'):
                    field_id = 'explosion.damage.' + field_id[len('damage.'):]
                native = node.get('recordType', item['currentRoot']['id'])
                kind = node['kind'] if node['kind'] != 'Beam' else 'OrbitalAbilityComponentData'
                backing_group,backing_row=node.get('group'),node.get('row')
                consumer_kind=node['kind']
                if field_id=='status.strength':
                    kind='DamageInfo';native=node['parentDamageType']
                    backing_group,backing_row=node['parentDamageGroup'],node['parentDamageRow']
                    consumer_kind='DamageInfo'
                offsets = {
                    'projectile.pellet_count':28,'projectile.velocity':32,'projectile.mass':36,
                    'projectile.drag':40,'projectile.gravity':44,
                    'damage.standard_damage':4,'damage.durable_damage':8,'damage.ap_direct':12,
                    'damage.ap_slight':16,'damage.ap_large':20,'damage.ap_extreme':24,
                    'damage.demolition':28,'damage.stagger':32,'damage.push_force':36,
                    'explosion.inner_radius':16,'explosion.outer_radius':20,
                    'explosion.shockwave_radius':24,'explosion.damage.standard_damage':4,
                    'explosion.damage.durable_damage':8,'explosion.damage.ap_direct':12,
                    'explosion.damage.ap_slight':16,'explosion.damage.ap_large':20,
                    'explosion.damage.ap_extreme':24,'explosion.damage.demolition':28,
                    'explosion.damage.stagger':32,'explosion.damage.push_force':36,
                    'status.strength':44 + (node.get('slot',1)-1)*8 + 4,
                    'status.duration':40,'orbital.duration':460,'orbital.movement_speed':468,
                    'orbital.search_radius':472,'orbital.tick_interval':480}
                storage = defs[field_id].get('storage') or ('i32' if field_id.endswith(('standard_damage','durable_damage')) else
                    'u32' if defs[field_id]['type'] == 'integer' else 'f32')
                scope = consumers.get((consumer_kind, native), [])
                if node['kind'] == 'Beam': scope = [{'stratagem':item['name'],'path':'beam'}]
                backing = {'kind':kind,'nativeIdentity':native,'offset':offsets[field_id],
                    'storage':storage,'width':4,'group':backing_group,'row':backing_row,
                    'consumers':scope,'phase':1}
                target = {'resource':'stratagem','stratagem':item['name'],'path':'attack','attack':role}
                add_field(entry, field_id, baseline, backing, target)
                attack['fields'].append(field_id)
        internal['stratagems'][item['name']] = entry
        public_stratagems.append({'name':item['name'],'family':item['family'].lower(),
            'rootResolution':'UNIQUE','attackRoles':list(entry['attacks']),
            'cooldown':root['cooldown'],
            'cooldownCapability':{'value':root['cooldown'],'writable':True,
                'field':'hd2.fields.stratagem.definition_cooldown','unit':'seconds'},
            'maxUses':{'value':max_value,'writable':False,
                'reason':defs['stratagem.max_uses']['reason']},
            'callInTime':{'value':None,'writable':False,
                'reason':'The resolved spawn-time scalar does not reproduce the semantic call-in time across families.'},
            'usesPerRearm':root['use_count'] if item['family']=='Eagle' else None,
            'rearmTime':source['systemRoots']['eagleRearm']['currentRoot']['cooldown']
                if item['family']=='Eagle' else None,
            'barrageScheduling':{'writable':False,
                'reason':'Native projectile delivery arrays are preserved; scalar shell, volley, and interval semantics are not proven.'}
                if len(item['rootProjectiles'])>1 else None})

    for support in source['supportRoots']:
        if support['resolution'] != 'UNIQUE':
            public_stratagems.append({'name':support['name'],'family':'support',
                'rootResolution':support['resolution'],'blockedReason':support['reason'],
                'attackRoles':[],
                'cooldownCapability':{'value':None,'writable':False,'reason':support['reason']},
                'maxUses':{'value':None,'writable':False,'reason':support['reason']},
                'callInTime':{'value':None,'writable':False,'reason':support['reason']}})
            continue
        root = support['currentRoot']; entry={'name':support['name'],'family':'support',
            'rootResolution':'UNIQUE','root':{'id':root['id'],'package':root['package'],
                'payloads':root['payloads'],'group':root['group'],'row':root['row']},
            'fields':[],'attacks':{}}
        add_field(entry,'stratagem.cooldown',root['cooldown'],
            {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':104,'storage':'f32',
             'width':4,'consumers':[{'stratagem':support['name'],'path':'stratagem'}]},
            {'resource':'stratagem','stratagem':support['name'],'path':'stratagem'})
        add_field(entry,'stratagem.max_uses',None if root['use_count']==4294967295 else root['use_count'],
            {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':80,'storage':'u32',
             'width':4,'consumers':[{'stratagem':support['name'],'path':'stratagem'}]},
            {'resource':'stratagem','stratagem':support['name'],'path':'stratagem'},False)
        internal['stratagems'][support['name']]=entry
        public_stratagems.append({'name':support['name'],'family':'support','rootResolution':'UNIQUE',
            'attackRoles':[],'cooldown':root['cooldown'],
            'cooldownCapability':{'value':root['cooldown'],'writable':True,
                'field':'hd2.fields.stratagem.definition_cooldown','unit':'seconds'},
            'maxUses':{'value':None if root['use_count']==4294967295 else root['use_count'],
                'writable':False,'reason':defs['stratagem.max_uses']['reason']},
            'callInTime':{'value':None,'writable':False,
                'reason':'No call-in-time owner is proven for this definition.'}})

    public={'contract':'hd2runtime.stratagem.guarded_authoring.v1','schemaVersion':1,
        'canonicalCollection':'fieldInstances','source':{'wikiCommit':source['source']['wikiCommit'],
            'snapshot':source['source']['snapshot']},'safety':internal['safety'],
        'stratagems':public_stratagems,'semanticBranches':semantic_branches,
        'attacks':attack_instances,'fieldInstances':field_instances}
    counts=Counter(x['semanticFieldId'].split('.')[0] for x in field_instances if x['editable'])
    attack_counts=Counter(x['kind'] for x in attack_instances)
    public['summary']={'offensiveRootsResolved':20,'orbitalRootsResolved':12,'eagleRootsResolved':8,
        'supportRootsResolved':sum(x['resolution']=='UNIQUE' for x in source['supportRoots']),
        'cooldownWritable':sum(x['semanticFieldId']=='stratagem.cooldown' and x['editable'] for x in field_instances),
        'maxUsesWritable':0,'eagleUsesPerRearmWritable':8,'eagleRearmTimeWritable':8,
        'fieldInstances':len(field_instances),'writableFieldInstances':sum(x['editable'] for x in field_instances),
        'backingObjectCount':len({x['backingObjectId'] for x in field_instances}),
        'sharedBackingObjectCount':len({x['backingObjectId'] for x in field_instances if x['shared']}),
        'sharedConsumerScopeCount':len({x['backingObjectId'] for x in field_instances if x['shared']}),
        'importedAttackBranches':len(semantic_branches),'nativeBackingBranches':len(attack_instances),
        'importedProjectileBranches':sum(x.get('wikiKind')=='Projectile' for x in semantic_branches),
        'importedExplosionBranches':sum(x.get('wikiKind')=='Explosion' for x in semantic_branches),
        'importedStatusBranches':sum(x.get('wikiKind')=='Status' for x in semantic_branches),
        'importedBeamBranches':sum('Beam' in x.get('semanticRoles',[]) for x in semantic_branches),
        'nativeBranchInstancesByKind':dict(sorted(attack_counts.items())),
        'writableByDomain':dict(sorted(counts.items())),
        'researchWrites':0,'protectionChanges':0,'fixtureFallback':'disabled'}
    return internal, public, source


def generate(check=False):
    internal, public, source = build()
    outputs={INTERNAL:json.dumps(internal, indent=2) + '\n',
        LUA:'-- Generated by scripts/generate_stratagem_authoring.py.\nreturn ' + lua(internal) + '\n',
        PUBLIC:json.dumps(public, indent=2) + '\n'}
    compact={'schemaVersion':1,'source':source['source'],'systemRoots':source['systemRoots'],
        'stratagems':[{'name':x['name'],'family':x['family'],'historicalIdentity':x['historicalIdentity'],
            'currentRoot':x['currentRoot'],'payloadReports':x['payloadReports'],
            'rootProjectiles':x['rootProjectiles'],'nativeGraph':x['nativeGraph'],
            'importedBranches':x.get('importedBranches',[])}
            for x in source['stratagems']], 'supportRoots':source['supportRoots']}
    outputs[RESEARCH]=json.dumps(compact, indent=2) + '\n'
    stale=[]
    for path,body in outputs.items():
        if not path.exists() or path.read_text()!=body:
            stale.append(path)
            if not check:path.write_text(body)
    if check and stale:raise RuntimeError('Stale stratagem authoring outputs: '+', '.join(map(str,stale)))
    return stale,public['summary']

def main():
    stale,summary=generate(False)
    print(json.dumps(summary,indent=2))

if __name__ == '__main__': main()
