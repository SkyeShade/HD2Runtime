"""Generate guarded throwable authoring from the reviewed throwable research.

Inputs: research/throwable-authoring-F5FEE03DCFDB.json (scripts/research_throwable_authoring.py) and
schemas/throwable_fields.json.
Outputs: domains/throwable_authoring.lua (runtime; native coordinates and chain proofs) and
sdk/ThrowableAuthoringCapabilities.json (public; no raw addresses or native IDs).

Every target is a native record the throwable entity owns or reaches through typed members:

- throwable: ThrowableComponent inventory counts;
- detonation: ExplosiveComponent;
- explosion: ExplosionSettings and its DamageInfo;
- status_effect: a DamageInfo status slot and the shared StatusEffectSettings definition;
- shrapnel / bomblets: the explosion's child ProjectileSettings;
- bomblet_explosion: the bomblet's own explosion;
- damage: StickyComponent direct-hit DamageInfo (throwing knife);
- entity: HealthComponent;
- shield: ShieldComponent.

Each target carries the chain links the runtime re-proves before every write.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migration import overlay as migration_overlay  # noqa: E402  build-migration hook
import generate_entity_authoring  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/throwable-authoring-F5FEE03DCFDB.json'
FIELDS = ROOT / 'schemas/throwable_fields.json'
LUA_OUTPUT = ROOT / 'domains/throwable_authoring.lua'
JSON_OUTPUT = ROOT / 'sdk/ThrowableAuthoringCapabilities.json'
CONTRACT = 'hd2runtime.throwable.guarded_authoring.v1'
UNVERIFIED = ('The native owner and value are proven (typed chain plus exact wiki fingerprint where published), '
    'but no in-game test has confirmed the effect of a changed value.')
SHARED_SETTINGS = ('Settings rows are global definitions. Every consumer reached through typed native references '
    'is listed, but code-selected consumers cannot be excluded, so every edit requires allow_shared=true.')
# Status type -> wiki label, proven by elimination across the resolved catalog (single-status items first).
STATUS_BY_ELIMINATION = {12: 'Thermite'}
ORDER_CORRELATED = 'label correlated by slot order only (unconfirmed)'


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def constants():
    known = {value: f'hd2.fields.{domain}.{constant}' for domain, items in
        generate_entity_authoring.api_constants().items() for constant, value in items.items()}
    for definition in json.loads(FIELDS.read_text())['fields']:
        if definition['id'] not in known:
            domain, name = definition['id'].split('.', 1)
            known[definition['id']] = f'hd2.fields.{domain}.{name.replace(".", "_")}'
    return known


def outputs(research_path=RESEARCH):
    research = json.loads(Path(research_path).read_text(encoding='utf-8'))
    definitions = {d['id']: d for d in json.loads(FIELDS.read_text())['fields']}
    api = constants()
    status_names = {int(k): v[0] for k, v in research['statusNames'].items() if len(v) == 1}
    status_names.update(STATUS_BY_ELIMINATION)
    runtime = {'version': 1, 'build': research['build'], 'throwables': {}}
    public = {'contract': CONTRACT, 'schemaVersion': 1, 'build': research['build'],
        'source': 'research/throwable-authoring-F5FEE03DCFDB.json', 'throwables': [],
        'fieldDefinitions': [{k: v for k, v in d.items() if k not in ('offset', 'storage', 'component', 'settings')}
            | {'apiFieldConstant': api[d['id']]} for d in definitions.values()],
        'safety': {'writes': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled', 'mode': 'snapshot'}}
    counters = {'fields': 0, 'writable': 0, 'byTarget': {}, 'writableByTarget': {}, 'shared': 0}

    for entry in research['catalog']:
        name = entry['name']
        identity = entry['identity']
        semantic = 'throwable/v1/' + slug(name) + '/' + digest(identity.get('resource') or name)
        pub = {'name': name, 'semanticId': semantic, 'category': entry['category'], 'family': entry['family'],
            'designation': entry['designation'], 'identity': {'status': identity['status']},
            'targets': [], 'blocked': [], 'leads': []}
        public['throwables'].append(pub)
        if identity['status'] != 'RESOLVED':
            pub['identity']['candidates'] = identity.get('candidates')
            continue
        native = entry['native']
        facts = entry['facts']
        matched = {m['fact'] for m in identity['matchedFacts']}
        pub['identity'].update(method='native_fingerprint', matchedFacts=sorted(matched),
            evidence=['unique player armory equipment (ThrowableComponent + LoadoutPackage + EncyclopediaEntry) '
                'agreeing with every published wiki fact (' + str(len(matched)) + ' facts)',
                'compared against all ' + str(identity['candidatesCompared']) + ' armory throwable entities of '
                + str(identity['throwableComponentOwners']) + ' ThrowableComponent owners',
                'resource path name recorded as supporting evidence only'],
            nearestOtherCandidate=identity.get('nearestOtherCandidate'),
            aiVariantsWithSameValues=len(identity.get('otherPerfectCandidatesOutsideArmory') or []))
        record = {'name': name, 'semanticId': semantic, 'family': entry['family'], 'category': entry['category'],
            'resource': native['resource'], 'entityRow': native['entityRow'], 'identityStatus': 'RESOLVED',
            'components': {}, 'targets': {}}
        runtime['throwables'][name] = record

        def component_backing(key, component, offset, storage):
            rec = native[key]['record']
            record['components'][component] = {'recordIndex': rec['recordIndex'], 'indexRow': rec['indexRow'],
                'ownerCount': rec['ownerCount']}
            return {'kind': 'component', 'component': component, 'recordIndex': rec['recordIndex'],
                'indexRow': rec['indexRow'], 'ownerCount': rec['ownerCount'], 'uniqueOwner': rec['ownerCount'] == 1,
                'offset': offset, 'storage': storage, 'width': 4}

        def settings_backing(node, offset, storage):
            return {'kind': 'settings', 'settings': node['kind'], 'recordType': node['recordType'],
                'group': node['group'], 'row': node['row'], 'offset': offset, 'storage': storage, 'width': 4}

        targets = {}

        def target(path, relationship, chain, scope=None, key=None, accessor=None):
            label = path if key is None else path + ':' + key
            targets[label] = {'path': path, 'key': key, 'chain': chain, 'fields': {}, 'relationship': relationship,
                'scope': scope, 'accessor': accessor or [path]}
            return targets[label]

        def field(tgt, field_id, baseline, backing, editable, reason=None, wiki=None, tier='native_member',
                shared=None, scope_note=None, extra=None):
            spec = definitions[field_id]
            shared = backing['kind'] == 'settings' if shared is None else shared
            instance = 'throwable:' + slug(name) + ':' + tgt['path'] + (':' + tgt['key'] if tgt['key'] else '') \
                + ':' + field_id
            low, high = spec['range']
            entry_field = {'instanceKey': instance, 'semanticFieldId': field_id, 'displayName': spec['display_name'],
                'type': spec['type'], 'unit': spec['unit'], 'currentDefault': baseline, 'editable': editable,
                'reason': reason, 'backing': backing, 'shared': shared,
                'operationGroup': backing['kind'] + ':' + (backing.get('component') or backing['settings']) + ':'
                    + str(backing.get('recordIndex', backing.get('recordType'))),
                'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': UNVERIFIED,
                'range': {'min': low, 'max': high, 'integer': spec['type'] == 'integer'}}
            if extra:
                entry_field.update(extra)
            tgt['fields'][field_id] = entry_field
            fingerprint = ({'status': 'exact', 'wiki': wiki} if wiki is not None and tier == 'wiki_exact'
                else {'status': 'not_published'})
            tgt.setdefault('public', []).append({'instanceKey': instance, 'semanticFieldId': field_id,
                'apiFieldConstant': api[field_id], 'displayName': spec['display_name'], 'type': spec['type'],
                'unit': spec['unit'], 'baseline': baseline, 'editable': editable, 'reason': reason,
                'range': {'min': low, 'max': high, 'integer': spec['type'] == 'integer'},
                'acknowledgements': (['allow_shared'] if shared else []) + (['allow_unverified_effect']
                    if editable else []),
                'acknowledgementReason': UNVERIFIED if editable else None,
                'scope': {'shared': shared, 'kind': 'settings_definition' if backing['kind'] == 'settings'
                    else 'throwable_local', 'note': scope_note or (SHARED_SETTINGS if shared else
                    'Record owned by this throwable only (unique owner).')},
                'evidence': {'tier': tier, 'native': spec.get('native') or ('ExplosionSettings / DamageInfo / '
                    'ProjectileSettings / StatusEffectSettings member' if backing['kind'] == 'settings'
                    else backing['component'] + ' member'), 'wikiFingerprint': fingerprint,
                    'gameplayWriteEffect': 'unproven'}})
            counters['fields'] += 1
            counters['byTarget'][tgt['path']] = counters['byTarget'].get(tgt['path'], 0) + 1
            if editable:
                counters['writable'] += 1
                counters['writableByTarget'][tgt['path']] = counters['writableByTarget'].get(tgt['path'], 0) + 1
            if shared:
                counters['shared'] += 1

        def wiki_value(fact, native_value):
            for item in identity['matchedFacts']:
                if item['fact'] == fact:
                    return item['wiki']
            return None

        # ---- inventory ------------------------------------------------------------------------------------
        inv = target('throwable', 'ThrowableComponent owned by the throwable entity', [])
        for field_id, offset, key, fact in (('throwable.starting_count', 100, 'starting', 'counts.starting'),
                ('throwable.max_count', 104, 'maximum', 'counts.maximum'),
                ('throwable.count_from_supply', 108, 'fromSupply', 'counts.fromSupply')):
            field(inv, field_id, native['throwable'][key],
                component_backing('throwable', 'ThrowableComponentData', offset, 'u32'), True,
                wiki=wiki_value(fact, None), tier='wiki_exact' if fact in matched else 'native_member')

        # ---- detonation -----------------------------------------------------------------------------------
        explosive = native.get('explosive')
        modes = research['modes']
        detonation = {'trigger': facts['trigger'], 'cookable': facts['cookable'], 'sticky': facts['sticky'],
            'wikiFuseSeconds': facts['fuses']}
        if explosive:
            mode = modes.get(str(explosive['mode']), 'unknown')
            detonation.update(nativeMode=mode, armingDelaySeconds=explosive['arming'],
                explosionDelaySeconds=explosive['delay'])
            det = target('detonation', 'ExplosiveComponent owned by the throwable entity', [])
            editable, reason, tier = False, None, 'native_member'
            fuses = facts['fuses']
            if len(fuses) > 1:
                reason = ('Multi-setting fuse: only the first setting (' + str(fuses[0]) + ' s) is this native '
                    'ExplosionDelay; the other selectable settings (' + ', '.join(str(f) + ' s' for f in fuses[1:])
                    + ') have no resolved native owner, so the fuse is not flattened into one writable scalar.')
                detonation['fuseSettings'] = [{'seconds': f, 'native': 'ExplosiveComponent.ExplosionDelay' if i == 0
                    else None, 'status': 'native_default' if i == 0 else 'unresolved'} for i, f in enumerate(fuses)]
            elif explosive['mode'] == 4:
                reason = ('Proximity mine: the native explosion delay is the trigger-to-detonation time, which the '
                    'wiki does not publish.')
            elif fuses and abs(fuses[0] - explosive['delay']) > 1e-3:
                reason = ('The wiki fuse (' + str(fuses[0]) + ' s) is not this native ExplosionDelay ('
                    + str(explosive['delay']) + ' s); for this throwable the delay ends the deployed device.')
            elif explosive['delay'] <= 0:
                reason = 'Impact detonation: the native explosion delay is a zero minimum timer, not a fuse.'
            elif fuses:
                editable, tier = True, 'wiki_exact'
            else:
                reason = 'No published fuse to fingerprint this native delay.'
            field(det, 'throwable.explosion_delay', explosive['delay'],
                component_backing('explosive', 'ExplosiveComponentData', 12, 'f32'), editable, reason,
                wiki=fuses[0] if fuses else None, tier=tier)
        pub['detonation'] = detonation

        # ---- explosion ------------------------------------------------------------------------------------
        explosion = native.get('explosion')
        exp_damage = native.get('explosionDamage')
        explosion_wiki = facts['role'] == 'Explosion'
        if explosion:
            link_explosion = {'from': 'component', 'component': 'ExplosiveComponentData', 'offset': 36,
                'expect': explosion['recordType']}
            scope = entry['scope'].get('explosion')
            ex = target('explosion', 'ExplosiveComponent.ExplosionType -> ExplosionSettings', [link_explosion],
                scope={'explosion': scope, 'damage': entry['scope'].get('explosionDamage')})
            editable = explosion_wiki
            why = None if editable else ('No wiki explosion fingerprint for this throwable; the native explosion '
                'is published read-only.')
            for field_id, key, offset, fact in (('explosion.inner_radius', 'inner', 16, 'explosion.inner_radius'),
                    ('explosion.outer_radius', 'outer', 20, 'explosion.outer_radius'),
                    ('explosion.shockwave_radius', 'shockwave', 24, 'explosion.shockwave_radius')):
                field(ex, field_id, explosion['values'][key], settings_backing(explosion, offset, 'f32'),
                    editable and fact in matched, why if not editable else (None if fact in matched else
                    'Native value does not reproduce the wiki fingerprint.'), wiki=wiki_value(fact, None),
                    tier='wiki_exact' if fact in matched else 'native_member')
            count = explosion['values']['shrapnelCount']
            if count:
                ok = 'explosion.shrapnel_count' in matched
                field(ex, 'explosion.shrapnel_count', count, settings_backing(explosion, 80, 'u32'), ok,
                    None if ok else 'Shrapnel count not fingerprinted by the wiki.',
                    wiki=wiki_value('explosion.shrapnel_count', None), tier='wiki_exact' if ok else 'native_member')
            if exp_damage:
                ex['chain'].append({'from': 'settings', 'settings': 'explosion', 'recordType': explosion['recordType'],
                    'offset': 4, 'expect': exp_damage['recordType']})
                values = exp_damage['values']
                pairs = (('explosion.damage.standard_damage', values['damage'], 4, 'i32', 'explosion.damage.standard_damage'),
                    ('explosion.damage.durable_damage', values['durable'], 8, 'i32', 'explosion.damage.durable_damage'),
                    ('explosion.damage.ap_direct', values['ap'][0], 12, 'u32', 'explosion.damage.ap'),
                    ('explosion.damage.ap_slight', values['ap'][1], 16, 'u32', None),
                    ('explosion.damage.ap_large', values['ap'][2], 20, 'u32', None),
                    ('explosion.damage.ap_extreme', values['ap'][3], 24, 'u32', None),
                    ('explosion.damage.demolition', values['demolition'], 28, 'u32', 'explosion.damage.demolition'),
                    ('explosion.damage.stagger', values['stagger'], 32, 'u32', 'explosion.damage.stagger'),
                    ('explosion.damage.push_force', values['push'], 36, 'u32', 'explosion.damage.push_force'))
                for field_id, baseline, offset, storage, fact in pairs:
                    fingerprinted = fact in matched if fact else explosion_wiki
                    field(ex, field_id, baseline, settings_backing(exp_damage, offset, storage),
                        explosion_wiki and (fact is None or fact in matched),
                        why if not explosion_wiki else (None if fingerprinted else
                            'Native value does not reproduce the wiki fingerprint.'),
                        wiki=wiki_value(fact, None) if fact else None,
                        tier='wiki_exact' if fact and fact in matched else 'native_member')
                # ---- status slots on the explosion DamageInfo ----------------------------------------------
                labels = entry['statusLabels']
                slots = values['status']
                for index, slot in enumerate(slots):
                    status_type = slot['type']
                    label = status_names.get(status_type)
                    confidence = 'correlated' if label else None
                    if not label and len(labels) == len(slots):
                        label, confidence = labels[index], ORDER_CORRELATED
                    key = slug(label) if label else 'slot-' + str(index + 1)
                    definition = (native.get('statusDefinitions') or {}).get(str(status_type))
                    chain = [link_explosion, {'from': 'settings', 'settings': 'explosion',
                        'recordType': explosion['recordType'], 'offset': 4, 'expect': exp_damage['recordType']},
                        {'from': 'settings', 'settings': 'damage', 'recordType': exp_damage['recordType'],
                            'offset': 44 + 8 * slot['slot'], 'expect': status_type}]
                    st = target('status_effect', 'explosion DamageInfo status slot ' + str(slot['slot'] + 1)
                        + ' -> StatusEffectSettings', chain,
                        scope={'damage': entry['scope'].get('explosionDamage'),
                            'definition': entry['scope'].get('status:' + str(status_type))}, key=key,
                        accessor=['explosion', 'status_effect', key])
                    st['label'] = label
                    st['labelConfidence'] = confidence
                    st['slot'] = slot['slot'] + 1
                    field(st, 'status.strength', slot['strength'],
                        settings_backing(exp_damage, 48 + 8 * slot['slot'], 'f32'), explosion_wiki,
                        None if explosion_wiki else why,
                        scope_note='Status applied per hit by this DamageInfo row (local to the row; the row is a '
                            'settings definition). ' + SHARED_SETTINGS)
                    if definition:
                        field(st, 'status.duration', definition['duration'],
                            {'kind': 'settings', 'settings': 'status', 'recordType': status_type,
                                'group': definition['group'], 'row': definition['row'], 'offset': 40,
                                'storage': 'f32', 'width': 4}, explosion_wiki,
                            None if explosion_wiki else why,
                            scope_note='Shared status definition: every source that applies this status type '
                                'uses it (' + str((entry['scope'].get('status:' + str(status_type)) or {}).get(
                                    'rootEntities', 0)) + ' native entities). ' + SHARED_SETTINGS)
            # ---- submunitions ----------------------------------------------------------------------------
            sub = native.get('submunition')
            if sub:
                bomblets = 'submunitionExplosion' in native
                path = 'bomblets' if bomblets else 'shrapnel'
                chain = [link_explosion, {'from': 'settings', 'settings': 'explosion',
                    'recordType': explosion['recordType'], 'offset': 84, 'expect': sub['recordType']}]
                sm = target(path, 'ExplosionSettings shrapnel projectile (' + str(count) + ' spawned per '
                    'detonation)' + ('; each bomblet has its own impact/expiry explosion' if bomblets else ''), chain,
                    scope={'projectile': entry['scope'].get('submunition'),
                        'damage': entry['scope'].get('submunitionDamage')})
                for field_id, key, offset in (('projectile.velocity', 'velocity', 32),
                        ('projectile.mass', 'mass', 36), ('projectile.drag', 'drag', 40),
                        ('projectile.gravity', 'gravity', 44)):
                    field(sm, field_id, sub['values'][key], settings_backing(sub, offset, 'f32'), True)
                sub_damage = native.get('submunitionDamage')
                if sub_damage and exp_damage and sub_damage['recordType'] == exp_damage['recordType']:
                    sm['sharedDamageWithParentExplosion'] = True
                elif sub_damage:
                    sm['chain'].append({'from': 'settings', 'settings': 'projectile', 'recordType': sub['recordType'],
                        'offset': 60, 'expect': sub_damage['recordType']})
                    values = sub_damage['values']
                    for field_id, baseline, offset, storage in (('damage.standard_damage', values['damage'], 4, 'i32'),
                            ('damage.durable_damage', values['durable'], 8, 'i32'),
                            ('damage.ap_direct', values['ap'][0], 12, 'u32'),
                            ('damage.ap_slight', values['ap'][1], 16, 'u32'),
                            ('damage.ap_large', values['ap'][2], 20, 'u32'),
                            ('damage.ap_extreme', values['ap'][3], 24, 'u32'),
                            ('damage.demolition', values['demolition'], 28, 'u32'),
                            ('damage.stagger', values['stagger'], 32, 'u32'),
                            ('damage.push_force', values['push'], 36, 'u32')):
                        field(sm, field_id, baseline, settings_backing(sub_damage, offset, storage), True)
                child = native.get('submunitionExplosion')
                if child:
                    child_damage = native.get('submunitionExplosionDamage')
                    link = [dict(link) for link in chain] + [
                        {'from': 'settings', 'settings': 'projectile', 'recordType': sub['recordType'], 'offset': 144,
                            'expect': child['recordType']},
                        {'from': 'settings', 'settings': 'projectile', 'recordType': sub['recordType'], 'offset': 156,
                            'expect': child['recordType']}]
                    be = target('bomblet_explosion', 'bomblet ProjectileSettings impact/expiry ExplosionType -> '
                        'ExplosionSettings', link, scope={'explosion': entry['scope'].get('submunitionExplosion'),
                            'damage': entry['scope'].get('submunitionExplosionDamage')},
                        accessor=['bomblets', 'explosion'])
                    for field_id, key, offset in (('explosion.inner_radius', 'inner', 16),
                            ('explosion.outer_radius', 'outer', 20), ('explosion.shockwave_radius', 'shockwave', 24)):
                        field(be, field_id, child['values'][key], settings_backing(child, offset, 'f32'), True)
                    if child_damage:
                        be['chain'].append({'from': 'settings', 'settings': 'explosion',
                            'recordType': child['recordType'], 'offset': 4, 'expect': child_damage['recordType']})
                        values = child_damage['values']
                        for field_id, baseline, offset, storage in (
                                ('explosion.damage.standard_damage', values['damage'], 4, 'i32'),
                                ('explosion.damage.durable_damage', values['durable'], 8, 'i32'),
                                ('explosion.damage.ap_direct', values['ap'][0], 12, 'u32'),
                                ('explosion.damage.ap_slight', values['ap'][1], 16, 'u32'),
                                ('explosion.damage.ap_large', values['ap'][2], 20, 'u32'),
                                ('explosion.damage.ap_extreme', values['ap'][3], 24, 'u32'),
                                ('explosion.damage.demolition', values['demolition'], 28, 'u32'),
                                ('explosion.damage.stagger', values['stagger'], 32, 'u32'),
                                ('explosion.damage.push_force', values['push'], 36, 'u32')):
                            field(be, field_id, baseline, settings_backing(child_damage, offset, storage), True)

        # ---- direct hit (throwing knife) ----------------------------------------------------------------------
        direct = native.get('directDamage')
        if direct and facts['role'] == 'Damage':
            chain = [{'from': 'component', 'component': 'StickyComponentData', 'offset': 44,
                'expect': direct['recordType']}]
            record['components']['StickyComponentData'] = {k: native['sticky']['record'][k]
                for k in ('recordIndex', 'indexRow', 'ownerCount')}
            dm = target('damage', 'StickyComponent.DamageInfoType -> DamageInfo (direct hit; no explosion)', chain,
                scope={'damage': entry['scope'].get('directDamage')})
            values = direct['values']
            for field_id, baseline, offset, storage, fact in (
                    ('damage.standard_damage', values['damage'], 4, 'i32', 'damage.standard_damage'),
                    ('damage.durable_damage', values['durable'], 8, 'i32', 'damage.durable_damage'),
                    ('damage.ap_direct', values['ap'][0], 12, 'u32', 'damage.ap_direct'),
                    ('damage.ap_slight', values['ap'][1], 16, 'u32', None),
                    ('damage.ap_large', values['ap'][2], 20, 'u32', None),
                    ('damage.ap_extreme', values['ap'][3], 24, 'u32', None),
                    ('damage.demolition', values['demolition'], 28, 'u32', 'damage.demolition'),
                    ('damage.stagger', values['stagger'], 32, 'u32', 'damage.stagger'),
                    ('damage.push_force', values['push'], 36, 'u32', 'damage.push_force')):
                field(dm, field_id, baseline, settings_backing(direct, offset, storage), True,
                    wiki=wiki_value(fact, None) if fact else None,
                    tier='wiki_exact' if fact and fact in matched else 'native_member')

        # ---- deployed mine health / shield ------------------------------------------------------------------
        if native.get('health'):
            en = target('entity', 'HealthComponent owned by the thrown (deployed) entity itself', [])
            ok = 'entity.health' in matched
            field(en, 'entity.health', native['health']['health'],
                component_backing('health', 'HealthComponentData', 0, 'i32'), ok,
                None if ok else 'Health is not fingerprinted by the wiki for this throwable.',
                wiki=wiki_value('entity.health', None), tier='wiki_exact' if ok else 'native_member')
            pub['leads'].append('Wiki armor is qualitative ("Unarmored"); no numeric armor is inferred.')
        if native.get('shield'):
            sh = target('shield', 'ShieldComponent owned by the thrown (deployed) entity itself', [])
            for field_id, key, offset in (('shield.radius', 'radius', 0), ('shield.durability', 'durability', 76)):
                ok = field_id in matched
                field(sh, field_id, native['shield'][key],
                    component_backing('shield', 'ShieldComponentData', offset, 'f32'), ok,
                    None if ok else 'Not fingerprinted by the wiki.', wiki=wiki_value(field_id, None),
                    tier='wiki_exact' if ok else 'native_member')
            pub['leads'].append('ShieldComponent +88 and +92 (20 s each) reproduce the wiki regen and broken '
                'delays; their member semantics are not proven, so they are not exposed.')
            pub['leads'].append('The wiki 0 s fuse is the deploy-on-contact behaviour; natively the '
                'ExplosiveComponent ends the device after its 20 s explosion delay (published read-only).')

        # ---- blockers and leads ------------------------------------------------------------------------
        children = [kind for _, kind, _ in facts['children']] if facts.get('children') else []
        if native.get('explosive', {}).get('timedStatus'):
            pub['blocked'].append({'what': 'timed status template (thermite burn)',
                'reason': 'ExplosiveComponent StatusEffectTimedSphericalTemplate member semantics are unproven; '
                    'its status types are published read-only.',
                'nativeStatusTypes': [status_names.get(s['type'], 'unnamed') for s in native['explosive']['timedStatus']]})
        if entry['family'] == 'Arc':
            pub['blocked'].append({'what': 'arc child (Stun Small)', 'reason': 'The arc attack is not reached from '
                'the explosion through any typed reference; no arc settings row is linked.'})
        if entry['family'] == 'Seeker':
            pub['blocked'].append({'what': 'seek radius / lifetime', 'reason': 'Wiki prose only (about 50 m, 30 s); '
                'the Detector/Targeting/Boids components have no named layout, so no native owner is proven.'})
        if name == 'G/40-K Melta Mine':
            pub['blocked'].append({'what': 'FLAMEWALL damage', 'reason': 'Secondary flame wall is not reached '
                'from the mine through any typed reference.'})
        if name == 'G-142 Pyrotech':
            pub['blocked'].append({'what': 'spray (G-142 PYROTECH S)', 'reason': 'The spray attack is not reached '
                'through any typed reference.'})
        if entry['family'] == 'Smoke':
            pub['blocked'].append({'what': 'smoke cloud lifetime', 'reason': 'ExplosionSettings +104 holds 30 (a '
                'cloud-lifetime candidate) but its member semantics are unproven; not exposed.'})
        if name == 'G-109 Urchin':
            pub['leads'].append('Wiki prose: one pulse every 2.9 s, 4 pulses. The 2.9 s native explosion delay '
                'is exposed; the pulse count has no proven native owner.')
        pub['leads'].append('ThrowableComponent +16 (FP32, hidden name 18 characters) is 20 for most throwables; it '
            'is consistent with a throw speed but unproven, so no throw-distance field is exposed.')

        # finalize targets
        for label, tgt in targets.items():
            record['targets'][label] = {'path': tgt['path'], 'key': tgt['key'], 'chain': tgt['chain'],
                'fields': tgt['fields'], 'label': tgt.get('label'), 'slot': tgt.get('slot')}
            pub['targets'].append({'path': tgt['path'], 'key': tgt['key'], 'accessor': tgt['accessor'],
                'relationship': tgt['relationship'], 'label': tgt.get('label'),
                'labelConfidence': tgt.get('labelConfidence'), 'scope': tgt['scope'],
                'sharedDamageWithParentExplosion': tgt.get('sharedDamageWithParentExplosion', False),
                'fields': tgt.get('public', [])})

    public['summary'] = {'throwables': len(research['catalog']),
        'resolved': sum(e['identity']['status'] == 'RESOLVED' for e in research['catalog']),
        'writableThrowables': sum(any(f['editable'] for t in r['targets'].values() for f in t['fields'].values())
            for r in runtime['throwables'].values()),
        'fieldInstances': counters['fields'], 'writableFieldInstances': counters['writable'],
        'sharedFieldInstances': counters['shared'], 'fieldsByTarget': dict(sorted(counters['byTarget'].items())),
        'writableByTarget': dict(sorted(counters['writableByTarget'].items())),
        'unmatchedThrowableEntities': len(research['unmatchedThrowableEntities']),
        'researchWrites': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled'}
    runtime['summary'] = public['summary']
    return {LUA_OUTPUT: '-- Generated by scripts/generate_throwable_authoring.py; do not edit.\nreturn '
        + generate_entity_authoring.lua(migration_overlay.apply('throwable_authoring', runtime)) + '\n',
        JSON_OUTPUT: json.dumps(public, indent=2) + '\n'}


def generate(check=False, research_path=RESEARCH):
    stale = []
    for path, body in outputs(research_path).items():
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(path)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale throwable authoring outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
