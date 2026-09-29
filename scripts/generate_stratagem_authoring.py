"""Generate guarded stratagem authoring metadata from retained native research."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migration import overlay as migration_overlay  # noqa: E402  build-migration hook
import support_callin_linkage
import live_evidence
import generate_entity_authoring
import generate_pod_payload_authoring

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'build/offensive-stratagem-research.json'
FIELDS = ROOT / 'schemas/stratagem_fields.json'
PLAYER_FIELDS = ROOT / 'schemas/player_weapon_fields.json'
INTERNAL = ROOT / 'schemas/stratagem_authoring_catalog.json'
LUA = ROOT / 'domains/stratagem_authoring.lua'
PUBLIC = ROOT / 'sdk/StratagemAuthoringCapabilities.json'
RESEARCH = ROOT / 'research/offensive-stratagem-runtime-F5FEE03DCFDB.json'
DEFENSIVE_INPUT = ROOT / 'build/non-offensive-stratagem-research.json'
DEFENSIVE_RESEARCH = ROOT / 'research/defensive-stratagem-runtime-F5FEE03DCFDB.json'
DEFENSIVE_FIELDS = ROOT / 'schemas/stratagem_fields.json'
ENTITY_FIELDS = ROOT / 'schemas/entity_fields.json'
ENTITY_RESEARCH = ROOT / 'research/entity-authoring-runtime-F5FEE03DCFDB.json'
ZONE_BASE, ZONE_STRIDE = 520, 552
ICON_RESEARCH = ROOT / 'research/stratagem-icons-F5FEE03DCFDB.json'
RESUPPLY_RESEARCH = ROOT / 'research/resupply-F5FEE03DCFDB.json'
SUPPORT_CATALOG = ROOT / 'data/wiki_support_weapons.json'
UNLIMITED = 4294967295


def add_ui_icons(public_stratagems, internal):
    """Game UI icon identity per root (scripts/research_stratagem_icons.py). Artwork is never published."""
    research = json.loads(ICON_RESEARCH.read_text())
    by_id = {row['id']: row['type'] for row in research['rows']}
    types = {t['value']: t for t in research['types']}
    library = research['iconLibrary']
    for item in public_stratagems:
        entry = internal['stratagems'].get(item['name'])
        if item['rootResolution'] != 'UNIQUE' or entry is None:
            reason = ('The item has no call-in stratagem (rootResolution NO_CALL_IN), so there is no native '
                'stratagem type.' if item['rootResolution'] == 'NO_CALL_IN' else
                'No uniquely resolved StratagemDefinition, so no native stratagem type is known.')
            item['uiIcon'] = {'state':'no_native_root','nativeType':None,'iconKey':None,'reason':reason,
                'provenance':None,'blocker':{'kind':'no_native_root','rootResolution':item['rootResolution'],
                    'reason':reason}}
            continue
        native = types[by_id[entry['root']['id']]]
        state = 'unbound' if native['iconKey'] is None else 'resolved' if native['template'] == 'vector' else 'empty_template'
        item['uiIcon'] = {'state':state,'nativeType':native['name'],'nativeTypeValue':native['value'],
            'iconKey':native['iconKey'],'library':library['resource'] if native['iconKey'] else None}
        if state == 'unbound':
            item['uiIcon']['reason'] = 'The game UI icon library binds no icon to this native stratagem type.'
        elif state == 'empty_template':
            item['uiIcon']['reason'] = 'The bound icon template contains no vector artwork in this game build.'
        item['uiIcon']['provenance'] = {'basis':'native_stratagem_type',
            'evidence':['StratagemInfo.type of the uniquely resolved root','game.dll StratagemType name table']
                + (['StratagemTypeDataTemplate binding in the icon library'] if native['iconKey'] else []),
            'displayNameEquality':'not used','researchArtifact':ICON_RESEARCH.name}
        item['uiIcon']['blocker'] = None if state == 'resolved' else {'kind':state,
            'reason':item['uiIcon']['reason']}
    keys = [x['uiIcon']['iconKey'] for x in public_stratagems if x['uiIcon']['state'] == 'resolved']
    if len(keys) != len(set(keys)):
        raise ValueError('two stratagem roots resolve to one icon template')
    return {'contract':'hd2runtime.stratagem.ui_icon.v1','schemaVersion':1,
        'states':{'resolved':'The bound icon template has vector artwork; iconKey names it.',
            'empty_template':'An icon is bound, but its template has no vector artwork in this game build.',
            'unbound':'The icon library binds no icon to the native stratagem type.',
            'no_native_root':'No uniquely resolved native root, so no native stratagem type is known.'},
        'researchArtifact':ICON_RESEARCH.name,
        'library':library['resource'],'librarySha256':library['sha256'],'nativeTypeEnum':research['enum'],
        'nativeTypeValues':research['enumValues'],'typeBindings':library['typeBindings'],
        'templates':library['templates'],'vectorTemplates':library['vectorTemplates'],
        'emptyTemplates':library['emptyTemplates'],'artworkPublished':False,
        'chain':['StratagemInfo.type (member 0, ENUM_UINT32 StratagemType in the pinned type library)',
            'StratagemType value -> native member name: game.dll enum name table, every entry length equal to '
            'the type library alias length for its value',
            'native member name -> icon key: StratagemTypeDataTemplate DataTrigger in the icon library',
            'icon key -> DataTemplate in the same library (vector artwork or empty)'],
        'note':('Tooling extracts the artwork locally from the installed game. Display names are never used '
            'to select an icon.')}


def add_catalog_equipment(public_stratagems, source, linkage):
    """Presentation association between a support call-in and the equipment of the same catalog record.

    Each support root is generated from one support-weapon catalog record (research_stratagem_authoring
    iterates the catalog and locates the call-in by a reviewed native debug name), so the pair is known
    from the catalog. It is published separately from `delivers`, which stays reserved for structurally
    proven native delivery.
    """
    catalog = {w['name']: w for w in json.loads(SUPPORT_CATALOG.read_text())['weapons']}
    roots = {r['name']: r for r in source['supportRoots']}
    for item in public_stratagems:
        if item['family'] != 'support':
            continue
        record, root = catalog.get(item['name']), roots.get(item['name'])
        if record is None or root is None:
            raise ValueError('support stratagem without its catalog record: ' + item['name'])
        weapon_key = support_callin_linkage.support_weapon_key(item['name'])
        delivers = item.get('delivers') or {}
        stratagem = record['normalizedFields'].get('stratagem') or {}
        corroboration = []
        if root['resolution'] == 'UNIQUE':
            native = root['currentRoot']
            corroboration.append('reviewed native call-in debug name ' + root['historicalIdentity']['debugName'].strip())
            cooldown = (stratagem.get('cooldownSeconds') or {}).get('value')
            if cooldown is not None and float(cooldown) == float(native['cooldown']):
                corroboration.append('catalog cooldown %g s equals the native definition cooldown' % native['cooldown'])
            if stratagem.get('unlimitedUses') and native['use_count'] == UNLIMITED:
                corroboration.append('catalog and native definition both have unlimited uses')
        item['catalogEquipment'] = {'kind':'support_weapon','supportWeapon':weapon_key,
            'supportWeaponName':record['name'],'basis':'catalog_record',
            'catalogRecord':{'page':record['wikiPage'],'revision':record['wikiRevisionId']},
            'nativeCallInResolved':root['resolution'] == 'UNIQUE',
            'nativeDeliveryProven':delivers.get('known') is True and delivers.get('semanticId') == weapon_key,
            'corroboration':corroboration,
            'note':('Presentation association: the call-in and this equipment come from the same catalog record. '
                'It is not native delivery evidence; delivers and linkedStratagem remain the only ownership links.')}


UNLIMITED_USES = 4294967295
USES_RANGE = (1, 100)
# Gameplay evidence: the Exosuit Unlimited Uses reference mod writes 3 -> 0xFFFFFFFF on these four
# StratagemInfo records (matched by name, call-in and cooldown) and removes the three-use limit.
USES_GAMEPLAY_PROVEN = {'EXO-45 Patriot Exosuit', 'EXO-49 Emancipator Exosuit', 'EXO-55 Breakthrough Exosuit',
    'EXO-51 Lumberer Exosuit'}
USES_UNVERIFIED = ('StratagemInfo +80 is the native mission-use count (0xFFFFFFFF = unlimited, the game\'s own value '
    'for the FRV and most stratagems); only Exosuit 3 -> unlimited is gameplay-proven (reference mod).')
EAGLE_USES = ('On Eagle stratagems the same native field is uses per rearm (eagle.uses_per_rearm); Eagles have no '
    'separate mission-use limit.')
TURRET_UNVERIFIED = ('TurretComponent turn speeds and vertical limits equal the wiki detailed tables on all nine turreted '
    'sentries, but no live write has confirmed the gameplay effect yet.')
TURRET_LIMIT_UNVERIFIED = ('Horizontal limits follow the proven vertical-limit layout (every sentry: -180/180, fixed '
    'enemy mounts: narrower arcs) but no published table or live write confirms them.')
MINE_COUNT_UNVERIFIED = ('ThrowerComponent slot-0 salvo count and mines per salvo equal the wiki deployment sentence '
    '("six salvos of eight/three mines") on all four minefields and the launcher one-socket-per-mine array, but no '
    'live write has confirmed the gameplay effect yet.')
RANGE_UNVERIFIED = ('SensorEyeComponent +0 equals the wiki-stated targeting range of seven sentries (75/100/125/50 m), '
    'but no live write has confirmed the gameplay effect yet.')
USES_CAVEAT = ('Use counts are applied by the mission host; the HUD counter may keep its old value until the next '
    'mission (reference mod observation).')


def uses_state(root, family, name):
    """Native mission-use model for one StratagemInfo record."""
    if str(family).lower() == 'eagle':
        return {'value': None, 'writable': False, 'reason': EAGLE_USES,
            'public': {'value': None, 'mode': None, 'writable': False, 'reason': EAGLE_USES, 'transitions': []},
            'extra': {'usesMode': None, 'transitions': []}}
    count = root['use_count']
    value = 'unlimited' if count == UNLIMITED_USES else count
    mode = 'unlimited' if value == 'unlimited' else 'finite'
    proven = ['unlimited'] if name in USES_GAMEPLAY_PROVEN and mode == 'finite' else []
    transitions = (['unlimited_to_finite'] if mode == 'unlimited' else ['finite_to_unlimited', 'finite_to_finite'])
    extra = {'usesMode': mode, 'unlimitedValue': 'unlimited', 'nativeUnlimited': UNLIMITED_USES,
        'min': USES_RANGE[0], 'max': USES_RANGE[1], 'transitions': transitions,
        'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': USES_UNVERIFIED,
        'gameplayProvenValues': proven, 'caveat': USES_CAVEAT}
    return {'value': value, 'writable': True, 'reason': None, 'extra': extra,
        'public': {'value': value, 'mode': mode, 'writable': True, 'field': 'hd2.fields.stratagem.max_uses',
            'range': list(USES_RANGE), 'transitions': transitions, 'gameplayProvenValues': proven,
            'acknowledgement': 'allow_unverified_effect', 'caveat': USES_CAVEAT}}


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


def backing_identity(backing):
    if backing.get('component'):
        return {'kind': 'component', 'component': backing['component'],
            'recordIndex': backing['recordIndex']}
    return {'kind': 'settings', 'settings': backing['kind'],
        'nativeIdentity': backing['nativeIdentity']}


_CONSTANTS = None


def api_constant(field_id):
    # Same allocation as generate_sdk, including definition_/player_/entity_ collision prefixes.
    global _CONSTANTS
    if _CONSTANTS is None:
        _CONSTANTS = {value: f'hd2.fields.{domain}.{constant}' for domain, items in
            generate_entity_authoring.api_constants().items() for constant, value in items.items()}
    return _CONSTANTS[field_id]


def build():
    source = json.loads((INPUT if INPUT.exists() else RESEARCH).read_text())
    defs = {x['id']: x for path in (FIELDS, PLAYER_FIELDS, ENTITY_FIELDS)
            for x in json.loads(path.read_text())['fields']}
    defensive_path = DEFENSIVE_INPUT if DEFENSIVE_INPUT.exists() else DEFENSIVE_RESEARCH
    defensive_source = json.loads(defensive_path.read_text()) if defensive_path.exists() else None
    internal = {'schemaVersion': 1, 'sourceSnapshot': source['source']['snapshot'],
        'safety': {k: source['source'][k] for k in ('mode','writes','protectionChanges','fixtureFallback')},
        'stratagems': {}, 'eagleRearm': source['systemRoots']['eagleRearm']}

    consumers = defaultdict(list)
    for item in source['stratagems']:
        for node in item['nativeGraph']:
            native = node.get('recordType')
            if native is not None:
                consumers[(node['kind'], native)].append({'stratagem': item['name'], 'path': node['path']})
    if defensive_source:
        for item in defensive_source['stratagems']:
            for node in item['deployedEntity']['nativeGraph']:
                native = node.get('recordType')
                if native is not None:
                    consumers[(node['kind'], native)].append(
                        {'stratagem':item['name'],'path':node['path']})

    public_stratagems = []
    field_instances = []
    attack_instances = []
    semantic_branches = []
    eagle_names = [x['name'] for x in source['stratagems'] if x['family'] == 'Eagle']
    linkage = support_callin_linkage.build(source['supportRoots'])

    def add_field(entry, field_id, baseline, backing, target, writable=True, reason=None,
                  provenance='current-build retained snapshot plus schema-labelled native ownership', extra=None):
        definition = defs[field_id]
        target_identity = ':'.join(str(target.get(key, '')) for key in
            ('stratagem', 'path', 'entity', 'weapon', 'attack'))
        if target.get('zone') is not None:
            # Appended only for zone targets so every pre-existing instance key is unchanged.
            target_identity += ':' + str(target['zone'])
        instance_key = f"stratagem:{slug(entry['name'])}:{slug(target_identity)}:{field_id}"
        object_key = opaque('backing', json.dumps(backing_identity(backing), sort_keys=True))
        operation_key = opaque('operation', json.dumps(
            {'object':object_key,'target':target_identity}, sort_keys=True))
        raw_scope = backing.get('consumers', [{'stratagem': entry['name'], 'path': target['path']}])
        scope = list({json.dumps(item, sort_keys=True):item for item in raw_scope}.values())
        scope.sort(key=lambda item: json.dumps(item, sort_keys=True))
        settings_object = backing['kind'] in ('ProjectileSettings','DamageInfo',
            'ExplosionSettings','StatusEffectSettings','ArcSettings','BeamSettings')
        shared = len(scope) > 1 or settings_object
        scope_key = opaque('shared-scope', json.dumps(
            {'object':object_key,'consumers':scope}, sort_keys=True))
        descriptor = {'instanceKey': instance_key, 'semanticFieldId': field_id,
            'displayName': definition['display_name'], 'type': definition['type'],
            'unit': definition.get('unit'), 'currentDefault': baseline,
            'editable': writable and definition.get('writable', False),
            'reason': reason or definition.get('reason'), 'target': target,
            'backing': dict(backing), 'backingObjectId': object_key,
            'operationGroup': operation_key, 'planGroup': f"plan:stratagem:{slug(entry['name'])}",
            'requires': 'patch_or_transaction',
            'allowSharedRequired': shared, 'shared': shared, 'sharedConsumers': scope,
            'sharedScopeKey': scope_key,
            'reviewedScopeComplete': True, 'dynamicConsumersPossible': settings_object,
            'provenance': provenance}
        if extra:
            descriptor.update(extra)
        entry['fields'].append(descriptor)
        public = {k: descriptor[k] for k in ('instanceKey','semanticFieldId','displayName','type','unit',
            'currentDefault','editable','reason','target','backingObjectId','operationGroup','planGroup',
            'requires','allowSharedRequired','shared','sharedConsumers','reviewedScopeComplete',
            'dynamicConsumersPossible','sharedScopeKey','provenance')}
        public['backingObjectKind'] = backing['kind']
        public['apiFieldConstant'] = api_constant(field_id)
        public['domain'] = field_id.split('.')[0]
        public['planPhase'] = backing.get('phase', 1)
        public['dependsOn'] = backing.get('dependsOn', [])
        if extra:
            public.update(extra)
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
        add_field(entry, 'stratagem.max_uses', uses_state(root, item['family'], item['name'])['value'],
            {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':80,'storage':'u32',
             'width':4,'consumers':root_scope},
            {'resource':'stratagem','stratagem':item['name'],'path':'stratagem'}, uses_state(root, item['family'], item['name'])['writable'], uses_state(root, item['family'], item['name'])['reason'], extra=uses_state(root, item['family'], item['name'])['extra'])
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
            'maxUses':uses_state(root, item['family'], item['name'])['public'],
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
            delivers=linkage['stratagems'][support['name']]
            # Native absence of any call-in is published as its own resolution, not as unresolved.
            resolution=delivers.get('rootResolution',support['resolution'])
            reason=delivers['noCallIn']['reason'] if delivers.get('noCallIn') else support['reason']
            public_stratagems.append({'name':support['name'],'family':'support',
                'rootResolution':resolution,'blockedReason':reason,
                'delivers':delivers,
                'attackRoles':[],
                'cooldownCapability':{'value':None,'writable':False,'reason':reason},
                'maxUses':{'value':None,'writable':False,'reason':reason},
                'callInTime':{'value':None,'writable':False,'reason':reason}})
            continue
        root = support['currentRoot']; entry={'name':support['name'],'family':'support',
            'rootResolution':'UNIQUE','root':{'id':root['id'],'package':root['package'],
                'payloads':root['payloads'],'group':root['group'],'row':root['row']},
            'fields':[],'attacks':{}}
        add_field(entry,'stratagem.cooldown',root['cooldown'],
            {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':104,'storage':'f32',
             'width':4,'consumers':[{'stratagem':support['name'],'path':'stratagem'}]},
            {'resource':'stratagem','stratagem':support['name'],'path':'stratagem'})
        add_field(entry,'stratagem.max_uses', uses_state(root, 'support', support['name'])['value'],
            {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':80,'storage':'u32',
             'width':4,'consumers':[{'stratagem':support['name'],'path':'stratagem'}]},
            {'resource':'stratagem','stratagem':support['name'],'path':'stratagem'}, uses_state(root, 'support', support['name'])['writable'], uses_state(root, 'support', support['name'])['reason'], extra=uses_state(root, 'support', support['name'])['extra'])
        internal['stratagems'][support['name']]=entry
        public_stratagems.append({'name':support['name'],'family':'support','rootResolution':'UNIQUE',
            'attackRoles':[],'delivers':linkage['stratagems'][support['name']],
            'cooldown':root['cooldown'],
            'cooldownCapability':{'value':root['cooldown'],'writable':True,
                'field':'hd2.fields.stratagem.definition_cooldown','unit':'seconds'},
            'maxUses':uses_state(root, 'support', support['name'])['public'],
            'callInTime':{'value':None,'writable':False,
                'reason':'No call-in-time owner is proven for this definition.'}})

    # Vehicle and backpack call-in definitions. The delivered entities are authored
    # through hd2.vehicle/hd2.backpack; the definition keeps only its cooldown.
    entity_research = json.loads(ENTITY_RESEARCH.read_text())
    delivered = [(item, 'vehicle', generate_entity_authoring.vehicle_key(item['name']), 'vehicle_entity')
        for item in entity_research['vehicles'] if item['stratagemRoot']]
    delivered += [(item, 'backpack', generate_entity_authoring.backpack_key(item['name']), 'backpack_entity')
        for item in entity_research['backpacks']]
    for item, family, semantic_id, delivery_object in delivered:
        root = item['stratagemRoot']; name = item['name']
        entry = {'name':name,'family':family,'rootResolution':'UNIQUE',
            'root':{'id':root['id'],'package':root['package'],'payloads':root['payloads'],
                'group':root['group'],'row':root['row']},'fields':[],'attacks':{}}
        root_scope = [{'stratagem':name,'path':'stratagem'}]
        add_field(entry,'stratagem.cooldown',root['cooldown'],
            {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':104,'storage':'f32',
             'width':4,'consumers':root_scope},
            {'resource':'stratagem','stratagem':name,'path':'stratagem'})
        max_value = None if root['use_count'] == 4294967295 else root['use_count']
        add_field(entry,'stratagem.max_uses', uses_state(root, family, name)['value'],
            {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':80,'storage':'u32',
             'width':4,'consumers':root_scope},
            {'resource':'stratagem','stratagem':name,'path':'stratagem'}, uses_state(root, family, name)['writable'], uses_state(root, family, name)['reason'], extra=uses_state(root, family, name)['extra'])
        internal['stratagems'][name]=entry
        public_stratagems.append({'name':name,'family':family,'rootResolution':'UNIQUE',
            'attackRoles':[],'cooldown':root['cooldown'],
            'cooldownCapability':{'value':root['cooldown'],'writable':True,
                'field':'hd2.fields.stratagem.definition_cooldown','unit':'seconds'},
            'maxUses':uses_state(root, family, name)['public'],
            'callInTime':{'value':None,'writable':False,
                'reason':'No call-in-time owner is proven for this definition.'},
            'delivers':{'kind':family,'known':True,'state':'linked','semanticId':semantic_id,
                'relationship':'call_in','deliveryObject':delivery_object,
                'deliveryChain':['stratagem_definition','hellpod_rack','backpack_entity']
                    if family == 'backpack' else ['stratagem_definition','vehicle_entity'],
                'provenance':root['identityBasis'],'blocker':None}})

    # Resupply: the mission stratagem available in every mission (scripts/research_resupply.py). Its drop pod
    # is the shared Resupply rack, authored through hd2.pod_rack / :delivery():rack().
    resupply = json.loads(RESUPPLY_RESEARCH.read_text())
    item = resupply['stratagem']; root = item['currentRoot']; name = item['name']; family = item['family']
    entry = {'name':name,'family':family,'rootResolution':'UNIQUE',
        'root':{'id':root['id'],'package':root['package'],'payloads':root['payloads'],
            'group':root['group'],'row':root['row']},'fields':[],'attacks':{}}
    root_scope = [{'stratagem':name,'path':'stratagem'}]
    add_field(entry,'stratagem.cooldown',root['cooldown'],
        {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':104,'storage':'f32',
         'width':4,'consumers':root_scope},
        {'resource':'stratagem','stratagem':name,'path':'stratagem'})
    uses = uses_state(root, family, name)
    add_field(entry,'stratagem.max_uses',uses['value'],
        {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':80,'storage':'u32',
         'width':4,'consumers':root_scope},
        {'resource':'stratagem','stratagem':name,'path':'stratagem'},uses['writable'],uses['reason'],
        extra=uses['extra'])
    internal['stratagems'][name]=entry
    rack_name = 'Resupply pod'
    rack_semantic = ('pod-rack/v1/' + generate_pod_payload_authoring.slug(rack_name) + '/'
        + generate_pod_payload_authoring.digest({'rack':resupply['delivery']['rack']}))
    public_stratagems.append({'name':name,'family':family,'rootResolution':'UNIQUE',
        'attackRoles':[],'cooldown':root['cooldown'],'alwaysAvailable':True,
        'cooldownCapability':{'value':root['cooldown'],'writable':True,
            'field':'hd2.fields.stratagem.definition_cooldown','unit':'seconds'},
        'maxUses':uses['public'],
        'callInTime':{'value':None,'writable':False,
            'reason':'No call-in-time owner is proven for this definition.'},
        'delivers':{'kind':'pod_rack','known':True,'state':'linked','semanticId':rack_semantic,
            'rack':rack_name,'relationship':'call_in','deliveryObject':'pod_rack',
            'deliveryChain':['stratagem_definition','hellpod_rack','supply_box'],
            'payloadPairs':resupply['delivery']['payloadPairs'],
            'spawnCount':resupply['delivery']['spawnPayloadSize'],
            'sharedWith':[resupply['rewardVariant']['nativeType']],
            'provenance':root['identityBasis'],'blocker':None}})

    # Defensive stratagems keep the deployed entity, mounted weapon, and attack
    # branches as separate semantic instances. Native entity components and
    # settings records are still resolved by the guarded stratagem writer.
    defensive_consumers = defaultdict(list)
    if defensive_source:
        known_entities = {item['deployedEntity']['resource']: item['name']
            for item in defensive_source['stratagems']}
        for item in defensive_source['stratagems']:
            entity = item['deployedEntity']
            components = [component for report in item['payloadReports']
                if report['payload'] == entity['resource'] for component in report['components']]
            for component in components:
                key = (component['name'], component['record_index'])
                path = ('deployed_entity' if component['name'] == 'HealthComponentData'
                    else 'deployed_entity/weapon:primary')
                for resource in component['ownerResources']:
                    owner = known_entities.get(resource)
                    consumer = ({'stratagem': owner, 'path': path} if owner else
                        {'externalConsumer':opaque('entity-consumer', resource),
                         'path':path,'semanticStatus':'outside reviewed defensive catalog'})
                    defensive_consumers[key].append(consumer)
            for node in entity['nativeGraph']:
                if 'recordType' in node:
                    defensive_consumers[(node['kind'], node['recordType'])].append(
                        {'stratagem': item['name'], 'path': node['path']})
            for branch in item.get('importedBranches', []):
                semantic_branches.append(dict(branch, stratagem=item['name'],
                    family=item['family'].lower(),
                    correlation='descriptive branch preserved; writable fields are declared only by nativeGraph objects'))

        def scalar_at(component, offset):
            for value in component.get('fields', []):
                if value['offset'] == offset and value.get('value'):
                    return value['value'][0]
            return None

        def add_deployment_fields(entry, item, components, entity, entity_target):
            """Sentry turret motion and targeting range (TurretComponent, SensorEyeComponent) and the deployed
            lifetime (HellpodPayloadComponent), each published only when the research proof holds."""
            proofs = item.get('deploymentProofs') or {}

            def acknowledged(field_id, family, reason):
                """Live-proven families (schemas/live_evidence.json) publish their evidence and need no
                acknowledgement; everything else keeps allow_unverified_effect."""
                evidence = live_evidence.proven(family) if family else None
                if evidence and field_id in live_evidence.family(family)['fields']:
                    return {'liveEvidence': evidence}
                return {'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': reason}

            def component_field(component_name, field_id, offset, target, provenance, extra=None):
                component = components[component_name]
                add_field(entry, field_id, scalar_at(component, offset),
                    {'kind': component_name, 'component': component_name, 'nativeIdentity': entity['resource'],
                     'recordIndex': component['record_index'], 'indexRow': component['index_row'],
                     'offset': offset, 'storage': 'f32', 'width': 4, 'ownerCount': component['ownerCount'],
                     'uniqueOwner': component['uniqueOwner'], 'recordSha256': component.get('recordSha256'),
                     'consumers': defensive_consumers[(component_name, component['record_index'])]},
                    target, provenance=provenance, extra=extra)

            turret_proof = proofs.get('turret') or {}
            if turret_proof.get('exact') and 'TurretComponentData' in components:
                target = dict(entity_target, path='turret')
                proven = ('TurretComponent member equal to the wiki detailed-table value on every one of the nine '
                    'turreted sentries (hidden member-name length matches the table label)')
                for field_id, offset, low, high in (('turret.yaw_speed', 12, 1, 720), ('turret.pitch_speed', 8, 1, 720),
                        ('turret.pitch_min', 20, -90, 90), ('turret.pitch_max', 24, -90, 90)):
                    component_field('TurretComponentData', field_id, offset, target, proven,
                        {'min': low, 'max': high,
                         **acknowledged(field_id, 'sentry_turret_turn_speed', TURRET_UNVERIFIED)})
                for field_id, offset in (('turret.yaw_min', 28), ('turret.yaw_max', 32)):
                    component_field('TurretComponentData', field_id, offset, target,
                        'TurretComponent member paired with the proven vertical limits (same layout pattern, '
                        'constrained arcs on fixed enemy mounts); no published table',
                        {'min': -180, 'max': 180, 'acknowledgement': 'allow_unverified_effect',
                         'acknowledgementReason': TURRET_LIMIT_UNVERIFIED})
                entry['turret'] = {'proof': 'wiki detailed tables (Horizontal/Vertical Turn Speed, Vertical Limit)',
                    'native': turret_proof['native'], 'wikiChecks': turret_proof['wikiChecks']}
            sensor_proof = proofs.get('sensor')
            if sensor_proof and 'SensorEyeComponentData' in components:
                statement = sensor_proof.get('statement')
                component_field('SensorEyeComponentData', 'targeting.range', 0, dict(entity_target, path='targeting'),
                    'SensorEyeComponent member equal to the wiki-stated targeting range of seven sentries'
                    + (' (this sentry: "' + statement['text'] + '")' if statement else
                       ' (this sentry states no range of its own)'),
                    {'min': 1, 'max': 500, **acknowledged('targeting.range', 'sentry_targeting_range',
                        RANGE_UNVERIFIED)})
                entry['targeting'] = {'range': sensor_proof['native'], 'statement': statement,
                    'note': None if statement else ('Engagement distance may be set by the weapon (spray reach, arc '
                        'range); the sensor range bounds target acquisition only.')}
            count = (item.get('mineChain') or {}).get('countProof') or {}
            if count.get('exact') and 'ThrowerComponentData' in components:
                thrower = count['thrower']
                if thrower['recordIndex'] != components['ThrowerComponentData']['record_index']:
                    raise ValueError('mine count proof disagrees with the deployer thrower: ' + item['name'])
                target = dict(entity_target, path='minefield')
                for field_id, key, offset in (('minefield.salvos', 'salvos', thrower['salvosOffset']),
                        ('minefield.mines_per_salvo', 'perSalvo', thrower['perSalvoOffset'])):
                    baseline = count['native'][key]
                    add_field(entry, field_id, baseline,
                        {'kind': 'ThrowerComponentData', 'component': 'ThrowerComponentData',
                         'nativeIdentity': entity['resource'], 'recordIndex': thrower['recordIndex'],
                         'indexRow': thrower['indexRow'], 'offset': offset, 'storage': 'u32', 'width': 4,
                         'ownerCount': thrower['ownerCount'], 'uniqueOwner': thrower['uniqueOwner'],
                         'recordSha256': thrower['recordSha256'],
                         'consumers': [{'stratagem': item['name'], 'path': 'minefield'}]},
                        target, provenance=('ThrowerComponent slot-0 member equal to the wiki deployment sentence and '
                            'structured salvo/capacity fields; salvos x mines per salvo equals the launcher '
                            'distinct launch sockets'),
                        extra={'min': 1, 'max': baseline,
                            **acknowledged(field_id, 'minefield_salvos', MINE_COUNT_UNVERIFIED)})
                entry['minefield'] = {'proof': count['wiki']['statement']['text'],
                    'salvos': count['native']['salvos'], 'minesPerSalvo': count['native']['perSalvo'],
                    'launchSockets': count['native']['distinctLaunchSockets'],
                    'increase': ('blocked: the launcher has one launch socket per mine, so more mines than sockets '
                        'would need nodes the model does not have'),
                    'deploymentPattern': live_evidence.family('minefield_salvos')['behaviour']}
            lifetime = proofs.get('lifetime') or {}
            if lifetime.get('native') and 'HellpodPayloadComponentData' in components \
                    and item['name'] != 'FX-12 Shield Generator Relay':
                component_field('HellpodPayloadComponentData', 'payload.lifetime', 4, entity_target,
                    'HellpodPayload lifetime member gameplay-proven by ShieldRelayImprovements; '
                    + ('equal to the wiki detailed-table lifetime' if lifetime.get('exact') else
                       'this entity has no published lifetime'))

        def attack_role(path):
            marker = '/attack:'
            start = path.index(marker) + len(marker)
            role = path[start:].split('/', 1)[0]
            suffix = path[start + len(role):]
            for part in suffix.split('/'):
                if part == 'impact': role += '_impact'
                elif part == 'expiry': role += '_expiry'
                elif part == 'damage': role += '_damage'
                elif part.startswith('status:'): role += '_status_' + part.split(':', 1)[1]
            return role

        for item in defensive_source['stratagems']:
            root = item['currentRoot']
            entity = item['deployedEntity']
            entry = {'name': item['name'], 'family': item['family'].lower(),
                'rootResolution': 'UNIQUE', 'root': {'id': root['id'], 'package': root['package'],
                    'payloads': root['payloads'], 'group': root['group'], 'row': root['row']},
                'fields': [], 'attacks': {}, 'graph': entity['nativeGraph'],
                'deployedEntity': entity, 'blockedFields': [
                    {'field':'targeting.*', 'reason':'Target range, traverse, tracking speed, and firing arc ownership are not promoted without a native semantic proof.'},
                    {'field':'deployment lifetime', 'reason':'The deployed lifetime owner is not unambiguous across sentry, emplacement, and mine families.'},
                ]}
            if any(node['kind'] == 'ProjectileSettings' for node in entity['nativeGraph']):
                entry['blockedFields'].extend([
                    {'field':'projectile.lifetime','reason':'No shared schema-labelled native field is proven.'},
                    {'field':'projectile.penetration_slowdown','reason':'No shared schema-labelled native field is proven.'},
                ])
            if item['family'].lower() == 'mine':
                chain = item['mineChain']
                if not any(node['path'] == 'mine:primary/attack:mine' for node in entity['nativeGraph']):
                    raise ValueError('mine deployer without a resolved mine explosion: ' + item['name'])
                # Re-proved at write time: the deployer's MinefieldComponent still names the reviewed explosion row.
                entry['rootComponentLink'] = {'component':'MinefieldComponentData',
                    'recordIndex':chain['minefield']['recordIndex'],'indexRow':chain['minefield']['indexRow'],
                    'offset':chain['minefield']['explosionOffset'],'expect':chain['minefield']['explosionType'],
                    'node':'mine:primary/attack:mine'}
                mine_consumers = consumers[('ExplosionSettings', chain['minefield']['explosionType'])]
                if chain['thrownMine']['entityDefined'] and not any(
                        c.get('path') == 'ExplosiveComponentData+36' for c in mine_consumers):
                    mine_consumers.append({'externalConsumer': opaque('entity-consumer',
                        chain['thrownMine']['resource']), 'path': 'ExplosiveComponentData+36',
                        'semanticStatus': 'the deployed mine entity this stratagem throws'})
                entry['mine'] = {'explosionRole':'mine','mineEntityDefined':chain['thrownMine']['entityDefined'],
                    'explosionAgreement':chain['explosionAgreement'],
                    'triggerToDetonationSeconds':(chain['thrownMine'].get('explosive') or {}).get('explosionDelay')}
                entry['blockedFields'].extend([
                    {'field':'mine count / spacing','reason':'The deployer ThrowerComponent carries launch nodes, '
                        'counts and throw floats, but no independent fingerprint proves which is the mine count or '
                        'the spread; published read-only in the research only.'},
                    {'field':'mine trigger radius / arming time','reason':'The MinefieldComponent floats have no '
                        'independent fingerprint and the per-mine arming delay is 0; trigger detection is not '
                        'data-proven.'},
                    {'field':'mine trigger-to-detonation delay','reason':'The mine ExplosiveComponent explosion delay '
                        '(0.002 s) is proven by layout, but the anti-tank mine has no entity of its own, so it is '
                        'not authored uniformly; read-only.'},
                    {'field':'mine lifetime / chain reaction','reason':'No native owner found.'},
                ])
            if any(branch.get('kind') == 'Weapon' for branch in item.get('importedBranches', [])) \
                    and not entity['nativeGraph']:
                entry['blockedFields'].append({'field':'mounted weapon',
                    'reason':'The imported weapon branch has no proven native component-to-attack ownership chain.'})
            root_scope = [{'stratagem': item['name'], 'path': 'stratagem'}]
            add_field(entry, 'stratagem.cooldown', root['cooldown'],
                {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':104,
                 'storage':'f32','width':4,'consumers':root_scope},
                {'resource':'stratagem','stratagem':item['name'],'path':'stratagem'})
            max_value = None if root['use_count'] == 4294967295 else root['use_count']
            add_field(entry, 'stratagem.max_uses', uses_state(root, item['family'], item['name'])['value'],
                {'kind':'StratagemDefinition','nativeIdentity':root['id'],'offset':80,
                 'storage':'u32','width':4,'consumers':root_scope},
                {'resource':'stratagem','stratagem':item['name'],'path':'stratagem'}, uses_state(root, item['family'], item['name'])['writable'], uses_state(root, item['family'], item['name'])['reason'], extra=uses_state(root, item['family'], item['name'])['extra'])

            components = {component['name']: component for report in item['payloadReports']
                if report['payload'] == entity['resource'] for component in report['components']}
            entity_target = {'resource':'stratagem','stratagem':item['name'],
                'path':'deployed_entity','entity':'main'}
            health = components.get('HealthComponentData')
            if health:
                for field_id, offset in (('entity.health', 0), ('entity.armor', 280)):
                    baseline = scalar_at(health, offset)
                    if baseline is not None:
                        backing = {'kind':'HealthComponentData','component':'HealthComponentData',
                            'nativeIdentity':entity['resource'],'recordIndex':health['record_index'],
                            'indexRow':health['index_row'],'offset':offset,'storage':
                            'i32' if field_id == 'entity.health' else 'u32','width':4,
                            'ownerCount':health['ownerCount'],'uniqueOwner':health['uniqueOwner'],
                            'recordSha256':health.get('recordSha256'),
                            'consumers':defensive_consumers[('HealthComponentData', health['record_index'])]}
                        add_field(entry, field_id, baseline, backing, entity_target,
                            provenance='exact importer correlation plus reviewed HealthComponentData main-health/default-armor layout')
                health_consumers = defensive_consumers[('HealthComponentData', health['record_index'])]
                zone_evidence = entity_research['deployedHealth'][item['name']]
                if zone_evidence['ownership']['recordIndex'] != health['record_index']:
                    raise ValueError('deployed zone evidence disagrees with health ownership: ' + item['name'])
                entry['damageZones'] = []
                for zone in zone_evidence['zones']:
                    if not zone['populated']:
                        continue
                    zone_id = 'zone_' + str(zone['index'])
                    zone_target = dict(entity_target, path='damage_zone', zone=zone_id)
                    base = ZONE_BASE + zone['index'] * ZONE_STRIDE
                    for field_id, key, offset, storage in (('zone.armor', 'armor', 216, 'u32'),
                            ('zone.health', 'health', 232, 'i32'),
                            ('zone.affects_main_health', 'affectsMainHealth', 248, 'f32')):
                        combined = item['name'] == 'FX-12 Shield Generator Relay' and field_id == 'zone.health'
                        add_field(entry, field_id, zone[key],
                            {'kind':'HealthComponentData','component':'HealthComponentData',
                             'nativeIdentity':entity['resource'],'recordIndex':health['record_index'],
                             'indexRow':health['index_row'],'offset':base + offset,'storage':storage,
                             'width':4,'ownerCount':health['ownerCount'],'uniqueOwner':health['uniqueOwner'],
                             'recordSha256':health.get('recordSha256'),'consumers':health_consumers},
                            zone_target, provenance=('gameplay-proven with main health in ShieldRelayImprovements '
                                '(individual effect not isolated)' if combined else
                                'shared typed DamageableZone member gameplay-proven on the Bastion (BastionReArmored)'))
                    entry['damageZones'].append({'zoneId': zone_id, 'name': zone['name'],
                        'armor': zone['armor'], 'health': zone['health'],
                        'affectsMainHealth': zone['affectsMainHealth']})
            add_deployment_fields(entry, item, components, entity, entity_target)
            if item['name'] == 'FX-12 Shield Generator Relay':
                relay = entity_research['shieldRelay']
                if relay['resource'] != entity['resource']:
                    raise ValueError('relay shield evidence disagrees with the deployed entity')
                shield, payload = relay['shield'], relay['payload']
                shield_target = dict(entity_target, path='shield')
                for field_id, offset in (('shield.radius', 0), ('shield.durability', 76)):
                    add_field(entry, field_id, shield['values'][str(offset)],
                        {'kind':'ShieldComponentData','component':'ShieldComponentData',
                         'nativeIdentity':entity['resource'],'recordIndex':shield['recordIndex'],
                         'indexRow':shield['indexRow'],'offset':offset,'storage':'f32','width':4,
                         'ownerCount':shield['ownerCount'],'uniqueOwner':shield['uniqueOwner'],
                         'recordSha256':shield['recordSha256'],
                         'consumers':[{'stratagem':item['name'],'path':'shield'}]},
                        shield_target, provenance='ShieldComponent member gameplay-proven by ShieldRelayImprovements')
                add_field(entry, 'payload.lifetime', payload['values']['4'],
                    {'kind':'HellpodPayloadComponentData','component':'HellpodPayloadComponentData',
                     'nativeIdentity':entity['resource'],'recordIndex':payload['recordIndex'],
                     'indexRow':payload['indexRow'],'offset':4,'storage':'f32','width':4,
                     'ownerCount':payload['ownerCount'],'uniqueOwner':payload['uniqueOwner'],
                     'recordSha256':payload['recordSha256'],
                     'consumers':[{'stratagem':item['name'],'path':'deployed_entity'}]},
                    entity_target, provenance='HellpodPayload lifetime gameplay-proven by ShieldRelayImprovements')
                entry['shield'] = {'identityRole': 'shield projector configuration',
                    'component': 'ShieldComponent', 'sameEntityAsBase': True,
                    'runtimeShieldInstance': 'unresolved',
                    'blockedFields': [
                        {'field': 'shield recharge delay / broken delay / recharge rate / restart charge',
                         'reason': 'Labels come from an external export only; no reference mod wrote them.'},
                        {'field': 'zone explosive damage percentage',
                         'reason': 'The reference gameplay test did not change grenade damage to the emitter.'}]}

            weapon_target = {'resource':'stratagem','stratagem':item['name'],
                'path':'weapon','entity':'main','weapon':'primary'}
            component_fields = {
                'weapon.fire_rate': ('ProjectileWeaponComponentData', 8, 'f32'),
            }
            for field_id, (component_name, offset, storage) in component_fields.items():
                component = components.get(component_name)
                baseline = scalar_at(component, offset) if component else None
                if baseline is not None:
                    add_field(entry, field_id, baseline,
                        {'kind':component_name,'component':component_name,
                         'nativeIdentity':entity['resource'],'recordIndex':component['record_index'],
                         'indexRow':component['index_row'],'offset':offset,'storage':storage,'width':4,
                         'ownerCount':component['ownerCount'],'uniqueOwner':component['uniqueOwner'],
                         'recordSha256':component.get('recordSha256'),
                         'consumers':defensive_consumers[(component_name, component['record_index'])]}, weapon_target)
            magazine = components.get('WeaponMagazineComponentData')
            if magazine:
                for field_id, offset in (('weapon.capacity',136),
                        ('magazine.starting_magazines',140),
                        ('magazine.magazines_from_supply',144),
                        ('magazine.spare_magazines',148)):
                    baseline = scalar_at(magazine, offset)
                    if baseline is not None:
                        add_field(entry, field_id, baseline,
                            {'kind':'WeaponMagazineComponentData','component':'WeaponMagazineComponentData',
                             'nativeIdentity':entity['resource'],'recordIndex':magazine['record_index'],
                             'indexRow':magazine['index_row'],'offset':offset,'storage':'u32','width':4,
                             'ownerCount':magazine['ownerCount'],'uniqueOwner':magazine['uniqueOwner'],
                             'recordSha256':magazine.get('recordSha256'),
                             'consumers':defensive_consumers[('WeaponMagazineComponentData', magazine['record_index'])]},
                            weapon_target)
            heat = components.get('WeaponHeatComponentData')
            if heat:
                for field_id, offset, storage in (
                        ('heat.capacity',96,'f32'),('heat.heat_per_shot',116,'f32'),
                        ('heat.heat_per_second',120,'f32'),('heat.cool_per_second',128,'f32'),
                        ('heatsink.starting',84,'u32'),('heatsink.from_supply',88,'u32'),
                        ('heatsink.spare',92,'u32')):
                    baseline = scalar_at(heat, offset)
                    if baseline is not None:
                        add_field(entry, field_id, baseline,
                            {'kind':'WeaponHeatComponentData','component':'WeaponHeatComponentData',
                             'nativeIdentity':entity['resource'],'recordIndex':heat['record_index'],
                             'indexRow':heat['index_row'],'offset':offset,'storage':storage,'width':4,
                             'ownerCount':heat['ownerCount'],'uniqueOwner':heat['uniqueOwner'],
                             'recordSha256':heat.get('recordSha256'),
                             'consumers':defensive_consumers[('WeaponHeatComponentData', heat['record_index'])]},
                            weapon_target)

            for node in entity['nativeGraph']:
                if not node.get('recordType'):
                    continue
                role = attack_role(node['path'])
                kind = node['kind']
                # A mine deployer's attacks belong to its mine launcher, not a mounted weapon.
                weapon_id = 'mine' if node['path'].startswith('mine:') else 'primary'
                entry['attacks'].setdefault(role, {'role':role,'path':node['path'],
                    'kind':kind,'parentRole':role.rsplit('_',1)[0] if '_' in role else None,'fields':[],
                    'weapon':weapon_id})
                if not any(x['stratagem'] == item['name'] and x['role'] == role
                           for x in attack_instances):
                    attack_instances.append({'stratagem':item['name'],'family':item['family'].lower(),
                        'role':role,'path':node['path'],'kind':kind,
                        'parentRole':entry['attacks'][role]['parentRole'],
                        'entity':'main','weapon':weapon_id})
                target = {'resource':'stratagem','stratagem':item['name'],'path':'attack',
                    'entity':'main','weapon':weapon_id,'attack':role}
                for original_id, baseline in node.get('fields', {}).items():
                    field_id = ('explosion.damage.' + original_id[len('damage.'):] if
                        (node.get('linkage') == 'explosion_damage' or
                         '/impact/damage' in node['path'] or '/expiry/damage' in node['path'])
                        and original_id.startswith('damage.')
                        else original_id)
                    if field_id not in defs:
                        continue
                    offsets = {'projectile.pellet_count':28,'projectile.velocity':32,
                        'projectile.mass':36,'projectile.drag':40,'projectile.gravity':44,
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
                        'status.duration':40,'arc.velocity':4,'arc.range':8,
                        'arc.distance_at_max_spread':12,'arc.max_angle_spread':20,
                        'arc.chain_count':28,'arc.max_split':32,'beam.radius':4,'beam.length':8}
                    if field_id not in offsets:
                        continue
                    storage = defs[field_id].get('storage') or ('i32' if defs[field_id]['type'] == 'integer' else 'f32')
                    backing_kind = kind
                    native_identity = node['recordType']
                    backing_group, backing_row = node.get('group'), node.get('row')
                    consumer_kind = backing_kind
                    if field_id == 'status.strength':
                        backing_kind = 'DamageInfo'
                        native_identity = node['parentDamageType']
                        backing_group, backing_row = node['parentDamageGroup'], node['parentDamageRow']
                        consumer_kind = 'DamageInfo'
                    add_field(entry, field_id, baseline,
                        {'kind':backing_kind,'nativeIdentity':native_identity,
                         'offset':offsets[field_id],'storage':storage,'width':4,
                         'group':backing_group,'row':backing_row,
                         'consumers':consumers[(consumer_kind,native_identity)],
                         'phase':1}, target)
                    entry['attacks'][role]['fields'].append(field_id)
            internal['stratagems'][item['name']] = entry
            public_stratagems.append({'name':item['name'],'family':item['family'].lower(),
                'rootResolution':'UNIQUE','attackRoles':list(entry['attacks']),
                'cooldown':root['cooldown'],'cooldownCapability':{'value':root['cooldown'],
                    'writable':True,'field':'hd2.fields.stratagem.definition_cooldown','unit':'seconds'},
                'maxUses':uses_state(root, item['family'], item['name'])['public'],
                'callInTime':{'value':None,'writable':False,
                    'reason':'The resolved spawn-time scalar does not reproduce the semantic call-in time across families.'},
                'deployedEntity':{'kind':entity['kind'],'identityStatus':'UNIQUE',
                    'identityRole':'deployment entity' if item['family'].lower() == 'mine' else 'deployed entity',
                    'fieldCount':sum(field['target'].get('path') == 'deployed_entity' for field in entry['fields']),
                    'weaponBranches':['primary'] if any(field['target'].get('path') == 'weapon' for field in entry['fields']) else [],
                    'blockedFields':entry['blockedFields']},
                'mineScopeDeferred':False if item['family'].lower() == 'mine' else None,
                'mineInstanceResolved':None,
                'mine':({'explosionAttack':'mine','explosionResolved':True,
                    'mineEntityDefined':entry['mine']['mineEntityDefined'],
                    'explosionAgreement':entry['mine']['explosionAgreement'],
                    'triggerToDetonationSeconds':entry['mine']['triggerToDetonationSeconds'],
                    'api':"hd2.stratagem(name):mine()"} if item['family'].lower() == 'mine' else None)})
            public_stratagems[-1]['deployedEntity']['damageZones'] = [
                dict(zone, fieldInstances=[field['instanceKey'] for field in entry['fields']
                    if field['target'].get('zone') == zone['zoneId']]) for zone in entry.get('damageZones', [])]
            if entry.get('shield'):
                public_stratagems[-1]['deployedEntity']['shield'] = dict(entry['shield'],
                    fieldInstances=[field['instanceKey'] for field in entry['fields']
                        if field['target']['path'] == 'shield'])

    # Stable semantic identity for GUI persistence and cross-catalog joins.
    for item in public_stratagems:
        item['semanticId'] = support_callin_linkage.stratagem_key(item['name'])
    semantic_ids = [item['semanticId'] for item in public_stratagems]
    if len(semantic_ids) != len(set(semantic_ids)):
        raise ValueError('stratagem semantic identities are not unique')
    icon_contract = add_ui_icons(public_stratagems, internal)
    add_catalog_equipment(public_stratagems, source, linkage)
    backing_objects = {}
    operation_groups = {}
    for field in field_instances:
        backing_id = field['backingObjectId']
        backing = backing_objects.setdefault(backing_id, {
            'backingObjectId': backing_id, 'kind': field['backingObjectKind'],
            'shared': field['shared'], 'sharedConsumers': field['sharedConsumers'],
            'sharedScopeKey':field['sharedScopeKey'],
            'requiresSharedAcknowledgement':field['allowSharedRequired'],
            'reviewedConsumerCount':len(field['sharedConsumers']),
            'reviewedScopeComplete':field['reviewedScopeComplete'],
            'dynamicConsumersPossible':field['dynamicConsumersPossible'],
            'fieldInstances': []})
        if backing['sharedScopeKey'] != field['sharedScopeKey']:
            raise ValueError('inconsistent reviewed scope for ' + backing_id + ': ' +
                json.dumps({'existing':backing['sharedConsumers'],'incoming':field['sharedConsumers'],
                    'instance':field['instanceKey']}))
        backing['fieldInstances'].append(field['instanceKey'])
        group_id = field['operationGroup']
        group = operation_groups.setdefault(group_id, {
            'operationGroup': group_id, 'backingObjectId': backing_id,
            'runtimeBackingScope':field['backingObjectKind'],
            'target':field['target'],'fieldInstances': [], 'planGroups': [],
            'recommendedApi':'hd2.patch','allowSharedRequired':field['allowSharedRequired'],
            'phase':field['planPhase'],'dependencies':field['dependsOn']})
        if group['backingObjectId'] != backing_id or group['target'] != field['target']:
            raise ValueError('operation group conflates backing objects or semantic targets')
        group['fieldInstances'].append(field['instanceKey'])
        if field['planGroup'] not in group['planGroups']:
            group['planGroups'].append(field['planGroup'])
    for group in operation_groups.values():
        if len(group['fieldInstances']) > 1:
            group['recommendedApi'] = 'hd2.transaction'
    # The cooldown of exactly the stratagems a live test promoted (schemas/live_evidence.json provenTargets).
    for item in public_stratagems:
        capability = item.get('cooldownCapability') or {}
        promoted = capability.get('writable') and live_evidence.proven_target(
            'stratagem_definition_cooldown', item['name'], 'stratagem.definition_cooldown')
        if promoted:
            capability['liveEvidence'] = promoted
    deployed_entities = []
    for item in public_stratagems:
        if item.get('deployedEntity'):
            deployed_entities.append({
                'stratagem': item['name'], 'family': item['family'],
                'identity': item['deployedEntity'],
                'fieldInstances': [field['instanceKey'] for field in field_instances
                    if field['instanceKey'].startswith('stratagem:' + slug(item['name']) + ':')
                    and field['target']['path'] in ('deployed_entity','weapon','attack')],
                'attackRoles': item['attackRoles'],
                'blockedFields': item['deployedEntity']['blockedFields']})
    public={'contract':'hd2runtime.stratagem.guarded_authoring.v2','schemaVersion':2,
        'hd2RuntimeVersion':(ROOT/'VERSION').read_text().strip(),
        'canonicalCollection':'fieldInstances','source':{'wikiCommit':source['source']['wikiCommit'],
            'snapshot':source['source']['snapshot']},'safety':internal['safety'],
        'stratagems':public_stratagems,'semanticBranches':semantic_branches,
        'attacks':attack_instances,'fieldInstances':field_instances,
        'deployedEntities':deployed_entities,'backingObjects':list(backing_objects.values()),
        'operationGroups':list(operation_groups.values()),
        'supportCallInLinks':{key:linkage[key] for key in
            ('contract','schemaVersion','joinContract','relationships','audit')},
        'uiIconContract':icon_contract}
    internal_instance_keys = [field['instanceKey'] for entry in internal['stratagems'].values()
        for field in entry['fields']]
    published_instance_keys = [field['instanceKey'] for field in field_instances]
    missing = sorted(set(internal_instance_keys) - set(published_instance_keys))
    unexpected = sorted(set(published_instance_keys) - set(internal_instance_keys))
    duplicates = len(published_instance_keys) - len(set(published_instance_keys))
    if missing or unexpected or duplicates:
        raise ValueError('canonical stratagem field instance publication is incomplete')
    public['instanceAudit']={'internalPromotedInstances':len(internal_instance_keys),
        'publishedCanonicalInstances':len(published_instance_keys),'missingInstances':missing,
        'unexpectedInstances':unexpected,'duplicateInstanceKeys':duplicates,
        'exactMatch':True,'identityCoverage':'one canonical instance per promoted runtime descriptor'}
    counts=Counter(x['semanticFieldId'].split('.')[0] for x in field_instances if x['editable'])
    attack_counts=Counter(x['kind'] for x in attack_instances)
    defensive = [x for x in public_stratagems if x['family'] in ('sentry','emplacement','mine')]
    sentries = [x for x in defensive if x['family'] == 'sentry']
    emplacements = [x for x in defensive if x['family'] == 'emplacement']
    mines = [x for x in defensive if x['family'] == 'mine']
    defensive_fields = [x for x in field_instances if x['target']['path'] in
        ('deployed_entity','weapon','attack')]
    defensive_attacks = [x for x in attack_instances if x.get('entity') == 'main']
    defensive_attack_counts = Counter(x['kind'] for x in defensive_attacks)
    public['summary']={'offensiveRootsResolved':20,'orbitalRootsResolved':12,'eagleRootsResolved':8,
        'supportRootsResolved':sum(x['resolution']=='UNIQUE' for x in source['supportRoots']),
        'cooldownWritable':sum(x['semanticFieldId']=='stratagem.cooldown' and x['editable'] for x in field_instances),
        'maxUsesWritable':sum(x['semanticFieldId']=='stratagem.max_uses' and x['editable'] for x in field_instances),
        'maxUsesByMode':dict(sorted(Counter(x.get('usesMode') or 'eagle_per_rearm' for x in field_instances
            if x['semanticFieldId']=='stratagem.max_uses').items())),
        'maxUsesGameplayProven':sum(bool(x.get('gameplayProvenValues')) for x in field_instances
            if x['semanticFieldId']=='stratagem.max_uses'),
        'eagleUsesPerRearmWritable':8,'eagleRearmTimeWritable':8,
        'fieldInstances':len(field_instances),'writableFieldInstances':sum(x['editable'] for x in field_instances),
        'backingObjectCount':len({x['backingObjectId'] for x in field_instances}),
        'sharedBackingObjectCount':len({x['backingObjectId'] for x in field_instances if x['shared']}),
        'sharedConsumerScopeCount':len({x['sharedScopeKey'] for x in field_instances if x['shared']}),
        'importedAttackBranches':len(semantic_branches),'nativeBackingBranches':len(attack_instances),
        'importedProjectileBranches':sum(x.get('wikiKind')=='Projectile' for x in semantic_branches),
        'importedExplosionBranches':sum(x.get('wikiKind')=='Explosion' for x in semantic_branches),
        'importedStatusBranches':sum(x.get('wikiKind')=='Status' for x in semantic_branches),
        'importedBeamBranches':sum('Beam' in x.get('semanticRoles',[]) for x in semantic_branches),
        'nativeBranchInstancesByKind':dict(sorted(attack_counts.items())),
        'writableByDomain':dict(sorted(counts.items())),
        'sentryRootsResolved':len(sentries),'emplacementRootsResolved':len(emplacements),
        'mineRootsResolved':len(mines),'deployedEntitiesResolved':len(deployed_entities),
        'mineDeploymentEntitiesResolved':len(mines),'mineInstancesResolved':0,
        'mineExplosionsResolved':sum(bool(x.get('mine')) for x in mines),
        'mineAttackBranchesWritable':sum(sum(role.startswith('mine') for role in x['attackRoles']) for x in mines),
        'healthWritable':sum(x['semanticFieldId']=='entity.health' and x['editable'] for x in defensive_fields),
        'armorWritable':sum(x['semanticFieldId']=='entity.armor' and x['editable'] for x in defensive_fields),
        'mountedWeaponsResolved':len({(x['target'].get('stratagem'),x['target'].get('weapon'))
            for x in defensive_fields if x['target'].get('weapon')}),
        'multiWeaponEntities':0,
        'ammoWritable':sum(x['semanticFieldId'].startswith(('weapon.capacity','magazine.','rounds.'))
            and x['editable'] for x in defensive_fields),
        'mountedWeaponsWithAmmo':len({(x['target'].get('stratagem'),x['target'].get('weapon'))
            for x in defensive_fields if x['semanticFieldId'].startswith(
                ('weapon.capacity','magazine.','rounds.')) and x['editable']}),
        'fireRateWritable':sum(x['semanticFieldId']=='weapon.fire_rate' and x['editable']
            for x in defensive_fields),
        'projectileBranches':sum(x['kind']=='ProjectileSettings' for x in attack_instances),
        'damageBranches':sum(x['kind']=='DamageInfo' for x in attack_instances),
        'explosionBranches':sum(x['kind']=='ExplosionSettings' for x in attack_instances),
        'beamBranches':sum(x['kind'] in ('Beam','BeamSettings') for x in attack_instances),
        'arcBranches':sum(x['kind']=='ArcSettings' for x in attack_instances),
        'sprayBranches':sum(x['kind']=='Spray' for x in attack_instances),
        'statusBranches':sum(x['kind']=='StatusEffectSettings' for x in attack_instances),
        'defensiveNativeBranchInstancesByKind':dict(sorted(defensive_attack_counts.items())),
        'defensiveProjectileBranches':defensive_attack_counts['ProjectileSettings'],
        'defensiveDamageBranches':defensive_attack_counts['DamageInfo'],
        'defensiveExplosionBranches':defensive_attack_counts['ExplosionSettings'],
        'defensiveBeamBranches':defensive_attack_counts['BeamSettings'],
        'defensiveArcBranches':defensive_attack_counts['ArcSettings'],
        'defensiveSprayBranches':defensive_attack_counts['Spray'],
        'defensiveStatusBranches':defensive_attack_counts['StatusEffectSettings'],
        'heatWritable':sum(x['semanticFieldId'].startswith('heat.') and x['editable']
            for x in defensive_fields),
        'canonicalBackingObjects':len(backing_objects),
        'canonicalOperationGroups':len(operation_groups),
        'supportDeliveryLinksKnown':linkage['audit']['reverseLinksKnown'],
        'supportCallInLinkage':linkage['audit'],
        'uiIconStates':{state:sum(x['uiIcon']['state']==state for x in public_stratagems)
            for state in ('resolved','empty_template','unbound','no_native_root')},
        'catalogEquipmentAssociations':sum('catalogEquipment' in x for x in public_stratagems),
        'catalogOnlyEquipment':sorted(x['name'] for x in public_stratagems
            if 'catalogEquipment' in x and not x['catalogEquipment']['nativeDeliveryProven']),
        'vehicleRootsResolved':sum(x['family']=='vehicle' for x in public_stratagems),
        'backpackRootsResolved':sum(x['family']=='backpack' for x in public_stratagems),
        'shieldFieldsWritable':sum(x['target']['path']=='shield' and x['editable'] for x in field_instances),
        'damageZoneFieldsWritable':sum(x['target']['path']=='damage_zone' and x['editable'] for x in field_instances),
        'deployedZonesResolved':len({(x['target']['stratagem'],x['target']['zone']) for x in field_instances
            if x['target']['path']=='damage_zone'}),
        'researchWrites':0,'protectionChanges':0,'fixtureFallback':'disabled'}
    return internal, public, source


def generate(check=False):
    internal, public, source = build()
    outputs={INTERNAL:json.dumps(internal, indent=2) + '\n',
        LUA:'-- Generated by scripts/generate_stratagem_authoring.py.\nreturn ' + lua(migration_overlay.apply('stratagem_authoring', internal)) + '\n',
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
            if not check:path.write_text(body,newline='\n')
    if check and stale:raise RuntimeError('Stale stratagem authoring outputs: '+', '.join(map(str,stale)))
    return stale,public['summary']

def main():
    stale,summary=generate(False)
    print(json.dumps(summary,indent=2))

if __name__ == '__main__': main()
