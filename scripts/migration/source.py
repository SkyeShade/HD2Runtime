"""The previous known-good release as the migration's semantic source of truth.

`load_release(ref)` reads the generated runtime domain tables (domains/*.lua) of a release commit (or the working
tree) and normalizes every field into a FieldRecord: a stable key, the semantic object, the native backing
(component record, settings row, stratagem row, entity delta, or game.dll-resident table), the reviewed baseline,
the write state and the shared scope. `relationships()` lists the cross-object links the release relies on.
Raw addresses are never used; identities are resource hashes, native types, stratagem ids and ownership chains.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'sdk'))

MODULES = ('player_weapon_authoring', 'support_weapon_authoring', 'vehicle_weapon_authoring', 'entity_authoring',
    'stratagem_authoring', 'attachment_authoring', 'booster_authoring', 'pod_payload_authoring',
    'throwable_authoring', 'enemy_authoring')
SETTINGS_KIND = {'ProjectileSettings': 'projectile', 'DamageInfo': 'damage', 'ExplosionSettings': 'explosion',
    'StatusEffectSettings': 'status', 'ArcSettings': 'arc', 'BeamSettings': 'beam'}
DOMAIN_LABEL = {'player_weapon_authoring': 'Player weapons', 'support_weapon_authoring': 'Support weapons',
    'vehicle_weapon_authoring': 'Vehicle weapons', 'entity_authoring': 'Vehicles and backpacks',
    'stratagem_authoring': 'Stratagems', 'attachment_authoring': 'Magazine attachments',
    'booster_authoring': 'Boosters', 'pod_payload_authoring': 'Drop-pod payloads',
    'throwable_authoring': 'Throwables', 'enemy_authoring': 'Enemies and structures'}


def git(*args) -> str:
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True)


def resolve_ref(ref: str | None) -> dict:
    """`current`/None = working tree; a version (0.26.1) = its release commit; anything else = a git revision."""
    if ref in (None, 'current', 'working-tree'):
        return {'ref': 'working-tree', 'commit': git('rev-parse', 'HEAD').strip(), 'dirty': bool(
            git('status', '--porcelain').strip()), 'version': (ROOT / 'VERSION').read_text().strip()}
    commit = None
    if ref[:1].isdigit():
        found = git('log', '--all', '--format=%H', '--grep=^Release HD2Runtime ' + ref.replace('.', r'\.') + '\\b',
            '-E').split()
        commit = found[0] if found else None
    commit = commit or git('rev-parse', ref).strip()
    return {'ref': ref, 'commit': commit, 'dirty': False,
        'version': git('show', commit + ':VERSION').strip()}


def read_file(release: dict, relative: str) -> str:
    if release['ref'] == 'working-tree':
        return (ROOT / relative).read_text(encoding='utf-8')
    return git('show', release['commit'] + ':' + relative)


def lua(text: str) -> str:
    """A Lua long-bracket literal (no escape processing, so any file body round-trips)."""
    level = 0
    while (']' + '=' * level + ']') in text:
        level += 1
    return '[' + '=' * level + '[\n' + text + ']' + '=' * level + ']'


def load_tables(release: dict) -> dict:
    """Evaluate the release's generated domain tables (data-only Lua modules) and return them as JSON data."""
    from tools.lua_runner import execute
    json_module = (ROOT / 'primary_mapper/json.lua').read_text(encoding='utf-8')
    parts = ['package.preload["json"]=function(...) return assert(loadstring(' + lua(json_module) + ',"json"))(...) end',
        'local out={}']
    for module in MODULES:
        try:
            body = read_file(release, 'domains/' + module + '.lua')
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        parts.append('out[' + json.dumps(module) + ']=assert(loadstring(' + lua(body) + ',' + json.dumps(module) + '))()')
    parts.append('return require("json").encode(out)')
    return json.loads(execute('\n'.join(parts).encode()))


def release_profile(release: dict) -> dict:
    text = read_file(release, 'schemas/current.lua')
    import re
    exe = re.search(r'\["exe_sha"\]="([0-9A-F]+)"', text).group(1)
    dll = re.search(r'\["dll_sha"\]="([0-9A-F]+)"', text).group(1)
    return {'exeSha256': exe, 'gameDllSha256': dll, 'buildId': exe[:12]}


# -- field normalization --------------------------------------------------------------------------------------------
# Every record carries a locator: where the field lives in its generated domain table, plus a guard the overlay
# re-checks before patching (so a regenerated table with a different order can never be patched in the wrong place).
def _int(value):
    return int(value, 16) if isinstance(value, str) else value


def _record(module, key, obj, field_id, backing, baseline, editable, shared, locator, reason=None):
    return {'key': key, 'domain': module, 'object': obj, 'field': field_id, 'backing': backing,
        'baseline': baseline, 'editable': bool(editable), 'shared': bool(shared), 'reason': reason, 'locator': locator}


def _anchor(resources, component, record_index, source_view):
    """The object's own resource that owns this component record in the source build."""
    table = source_view.component(component) if source_view else None
    if table is None:
        return resources[0] if len(resources) == 1 else None
    owners = set(table.owners_of(record_index))
    mine = [resource for resource in resources if resource in owners]
    if len(mine) == 1:
        return mine[0]
    if not mine and len(owners) == 1:
        return next(iter(owners))
    return None


def _component(b, resource):
    return {'kind': 'component', 'component': b['component'], 'recordIndex': b['recordIndex'],
        'indexRow': b['indexRow'], 'ownerCount': b['ownerCount'], 'offset': b['offset'], 'storage': b['storage'],
        'width': b['width'], 'resource': resource}


def _settings(kind, b, anchors):
    return {'kind': 'settings', 'settings': 'damage' if kind == 'explosion_damage' else kind,
        'recordType': b['recordType'] if 'recordType' in b else b.get('nativeIdentity'), 'group': b.get('group'),
        'row': b.get('row'), 'offset': b['offset'], 'storage': b['storage'], 'width': b['width'],
        'phase': b.get('phase'), 'anchors': anchors,
        # A status_reference slot: its value is a status identity, not a scalar (see engine._status_table).
        **({'enum': b['enum']} if b.get('enum') else {})}


def _weapon_fields(module, weapons, source_view):
    for name, weapon in sorted(weapons.items()):
        resources = [_int(value) for value in weapon.get('resources') or []]
        attack = _int(weapon.get('attackResource')) if weapon.get('attackResource') else None
        anchors = ([attack] if attack else []) + [value for value in resources if value != attack]
        blocked = bool(weapon.get('ordinaryWritesBlocked'))
        seen = {}
        for index, field in enumerate(weapon.get('fields') or []):
            b = field.get('backing')
            if not isinstance(b, dict):
                continue
            field_id = field['semanticFieldId']
            key = module.split('_authoring')[0] + ':' + name + ':' + field_id
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                key += '#' + str(seen[key])
            if b.get('kind') == 'component':
                backing = _component(b, _anchor(resources, b['component'], b['recordIndex'], source_view))
            elif b.get('kind') == 'settings':
                backing = _settings(b['settings'], b, anchors)
            else:
                continue
            yield _record(module, key, name, field_id, backing, field.get('currentDefault'),
                field.get('editable') and not blocked, field.get('affectsMultipleWeapons'),
                {'path': ['weapons', name, 'fields', index], 'guard': {'semanticFieldId': field_id}},
                field.get('reason'))


def normalize(tables: dict, source_view=None) -> list[dict]:
    records = []
    for module in ('player_weapon_authoring', 'support_weapon_authoring', 'vehicle_weapon_authoring'):
        if module in tables:
            records += list(_weapon_fields(module, tables[module].get('weapons') or {}, source_view))
    entity = tables.get('entity_authoring') or {}
    for family in ('vehicles', 'backpacks'):
        for name, entry in sorted((entity.get(family) or {}).items()):
            for index, field in enumerate(entry.get('fields') or []):
                b = field['backing']
                if 'component' not in b:
                    continue
                records.append(_record('entity_authoring', field['instanceKey'], name, field['semanticFieldId'],
                    _component(b, _int(b['resource'])), field.get('currentDefault'), field.get('editable'),
                    field.get('shared'), {'path': [family, name, 'fields', index],
                        'guard': {'instanceKey': field['instanceKey']}}, field.get('reason')))
    for name, entry in sorted(((tables.get('stratagem_authoring') or {}).get('stratagems') or {}).items()):
        root = entry.get('root') or {}
        for index, field in enumerate(entry.get('fields') or []):
            b = field.get('backing')
            if not isinstance(b, dict):
                continue
            kind = b.get('kind')
            if kind == 'StratagemDefinition':
                backing = {'kind': 'stratagem', 'id': root.get('id'), 'group': root.get('group'),
                    'row': root.get('row'), 'offset': b['offset'], 'storage': b['storage'], 'width': b['width']}
            elif kind in SETTINGS_KIND:
                backing = _settings(SETTINGS_KIND[kind], b, [])
            elif 'component' in b:
                backing = _component(b, _int(b['nativeIdentity']))
            else:
                continue
            records.append(_record('stratagem_authoring', field['instanceKey'], name, field['semanticFieldId'], backing,
                field.get('currentDefault'), field.get('editable'), field.get('shared'),
                {'path': ['stratagems', name, 'fields', index], 'guard': {'instanceKey': field['instanceKey']}},
                field.get('reason')))
    for semantic, attachment in sorted(((tables.get('attachment_authoring') or {}).get('attachments') or {}).items()):
        for field_id, field in sorted((attachment.get('fields') or {}).items()):
            records.append(_record('attachment_authoring', field['instanceKey'], attachment.get('name') or semantic,
                field_id, {'kind': 'delta', 'resource': _int(attachment['resource']),
                    'component': field['backing']['component'], 'componentIndex': field['component'],
                    'componentOffset': field['componentOffset'], 'dataOffset': field['dataOffset'],
                    'storage': field['storage'], 'width': 1 if field['storage'] in ('u8', 'bool') else 4},
                field.get('currentDefault'), field.get('editable', True), True,
                {'path': ['attachments', semantic, 'fields', field_id], 'guard': {'instanceKey': field['instanceKey']}}))
    for name, booster in sorted(((tables.get('booster_authoring') or {}).get('boosters') or {}).items()):
        for path, target in sorted((booster.get('targets') or {}).items()):
            for field_id, field in sorted((target.get('fields') or {}).items()):
                b = field['backing']
                if b['kind'] == 'component':
                    backing = _component(b, _anchor([], b['component'], b['recordIndex'], source_view))
                else:
                    backing = {'kind': 'code', 'code': b['kind'], 'row': b.get('row'), 'offset': b.get('offset'),
                        'storage': b.get('storage'), 'width': b.get('width')}
                records.append(_record('booster_authoring', field['instanceKey'], name, field_id, backing,
                    field.get('currentDefault'), field.get('editable', True), field.get('shared'),
                    {'path': ['boosters', name, 'targets', path, 'fields', field_id],
                     'guard': {'instanceKey': field['instanceKey']}}, field.get('reason')))
    pods = tables.get('pod_payload_authoring') or {}
    for name, rack in sorted((pods.get('racks') or {}).items()):
        base = {'kind': 'component', 'component': 'HellpodRackComponentData', 'recordIndex': rack['recordIndex'],
            'indexRow': rack['indexRow'], 'ownerCount': rack['ownerCount'], 'resource': _int(rack['resource'])}
        locator = {'path': ['racks', name], 'guard': {'semanticId': rack['semanticId']}, 'rackLevel': True}
        for number, slot in sorted((rack.get('slots') or {}).items()):
            records.append(_record('pod_payload_authoring', 'pod:' + name + ':slot:' + number, name, 'payload.entity',
                dict(base, offset=slot['index'] * 64, storage='u64', width=8), _int(slot['resource']),
                rack['writable'], rack['shared'], dict(locator, slot=number), rack.get('reason')))
        records.append(_record('pod_payload_authoring', 'pod:' + name + ':spawn_count', name, 'payload.spawn_count',
            dict(base, offset=556, storage='u32', width=4), rack['spawnCount'], rack['writable'], rack['shared'],
            dict(locator, spawnCount=True), rack.get('reason')))
    for name, throwable in sorted(((tables.get('throwable_authoring') or {}).get('throwables') or {}).items()):
        resource = _int(throwable['resource'])
        for label, owned in sorted((throwable.get('targets') or {}).items()):
            for field_id, field in sorted((owned.get('fields') or {}).items()):
                b = field['backing']
                if b['kind'] == 'component':
                    backing = _component(b, resource)
                else:
                    backing = _settings(b['settings'], b, [resource])
                records.append(_record('throwable_authoring', field['instanceKey'], name, field_id, backing,
                    field.get('currentDefault'), field.get('editable'), field.get('shared'),
                    {'path': ['throwables', name, 'targets', label, 'fields', field_id],
                     'guard': {'instanceKey': field['instanceKey']}}, field.get('reason')))
    # Enemies: the compact table carries the class's HealthComponent identity once; a field's own backing (offset,
    # and after a migration its rebound record coordinates) overrides it, exactly as enemy_writes.descriptor merges.
    for name, entry in sorted(((tables.get('enemy_authoring') or {}).get('enemies') or {}).items()):
        health = entry['health']
        for index, field in enumerate(entry.get('fields') or []):
            b = dict(health, **field['backing'])
            zone = field.get('zone')
            guard = {'id': field['id'], 'path': field['path'], **({'zone': zone} if zone else {})}
            records.append(_record('enemy_authoring', 'enemy:' + name + ':' + (zone or 'entity') + ':' + field['id'],
                name, field['id'], _component(b, _int(entry['resource'])), field.get('currentDefault'),
                field.get('editable', True), not health['uniqueOwner'],
                {'path': ['enemies', name, 'fields', index], 'guard': guard}, field.get('reason')))
    keys = [record['key'] for record in records]
    if len(keys) != len(set(keys)):
        raise ValueError('migration field keys are not unique')
    return records


def relationships(tables: dict) -> list[dict]:
    """Cross-object links the release relies on. `blocks` lists the (domain, object) whose fields depend on it."""
    links = []

    def add(kind, key, obj, blocks=(), **values):
        links.append(dict({'kind': kind, 'key': key, 'object': obj, 'blocks': [list(item) for item in blocks]},
            **values))
    entity = tables.get('entity_authoring') or {}
    mounted = entity.get('mountedWeapons') or {}
    for name, vehicle in sorted((entity.get('vehicles') or {}).items()):
        for label, mount in sorted((vehicle.get('mounts') or {}).items()):
            weapon = mounted.get(mount.get('current'))
            if weapon:
                add('vehicle_mount', 'mount:' + name + ':' + label, name, vehicle=_int(vehicle['resource']),
                    slot=mount['slot'], weapon=_int(weapon['resource']))
    for name, weapon in sorted(((tables.get('vehicle_weapon_authoring') or {}).get('weapons') or {}).items()):
        chain = weapon.get('mountChain')
        if chain:
            add('vehicle_mount', 'vehicle-weapon-mount:' + name, name, [('vehicle_weapon_authoring', name)],
                vehicle=_int(chain['vehicleResource']), slot=chain['slot'], weapon=_int(chain['mountPath']))
    for name, backpack in sorted((entity.get('backpacks') or {}).items()):
        rack = backpack.get('rack') or {}
        if rack.get('resource'):
            add('rack_delivers', 'backpack-rack:' + name, name, rack=_int(rack['resource']),
                item=_int(backpack['resource']))
        feeds = backpack.get('feeds')
        if feeds:
            add('backpack_feed', 'backpack-feed:' + name, name,
                [('entity_authoring', name), ('support_weapon_authoring', feeds['weapon'])],
                backpack=_int(backpack['resource']), weapon=_int(feeds['weaponResource']),
                tag=_int(feeds['tag']['value']))
    pods = tables.get('pod_payload_authoring') or {}
    racks = pods.get('racks') or {}
    for name, rack in sorted(racks.items()):
        for consumer in rack.get('consumers') or []:
            add('stratagem_rack', 'stratagem-rack:' + consumer['name'] + ':' + name, consumer['name'],
                [('pod_payload_authoring', name)], stratagemId=consumer['id'], rack=_int(rack['resource']))
    for booster, identity in sorted((pods.get('boosterGranted') or {}).items()):
        add('booster_granted', 'booster-granted:' + booster, booster, [('booster_authoring', booster)],
            stratagemId=int(identity))
    support = (tables.get('support_weapon_authoring') or {}).get('weapons') or {}
    for name, weapon in sorted(support.items()):
        chain = weapon.get('ownershipChain')
        if isinstance(chain, list):
            for index, step in enumerate(chain):
                if step.get('resourceHash'):
                    add('entity_present', 'support-chain:' + name + ':' + str(index), name,
                        [('support_weapon_authoring', name)], step=step['kind'], resource=_int(step['resourceHash']))
        for resource in weapon.get('resources') or []:
            for rack_name, rack in sorted(racks.items()):
                if any(slot['resource'] == resource for slot in (rack.get('slots') or {}).values()):
                    add('rack_delivers', 'support-rack:' + name + ':' + rack_name, name,
                        rack=_int(rack['resource']), item=_int(resource))
    for name, entry in sorted(((tables.get('stratagem_authoring') or {}).get('stratagems') or {}).items()):
        root, link = entry.get('root'), entry.get('rootLink')
        if root and root.get('payloads'):
            add('stratagem_payload', 'stratagem-root:' + name, name, [('stratagem_authoring', name)],
                stratagemId=root['id'], payload=_int(root['payloads'][0]))
        if link and link.get('payload'):
            add('component_owner', 'stratagem-root-link:' + name, name, [('stratagem_authoring', name)],
                resource=_int(link['payload']), component=link['component'])
        value_link = entry.get('rootComponentLink')
        deployed = entry.get('deployedEntity') or {}
        if value_link and deployed.get('resource'):
            add('component_value', 'stratagem-component-link:' + name, name, [('stratagem_authoring', name)],
                resource=_int(deployed['resource']), component=value_link['component'],
                offset=value_link['offset'], expect=value_link['expect'])
        if entry.get('rootResolution') == 'NO_CALL_IN':
            add('no_call_in', 'no-call-in:' + name, name, [('stratagem_authoring', name)])
        add('stratagem_icon', 'stratagem-icon:' + name, name)
    attachments = tables.get('attachment_authoring') or {}
    by_semantic = attachments.get('attachments') or {}
    player = (tables.get('player_weapon_authoring') or {}).get('weapons') or {}
    for weapon, entry in sorted((attachments.get('weapons') or {}).items()):
        for option in entry.get('options') or []:
            attachment = by_semantic.get(option.get('attachment'))
            if attachment is None:
                continue
            add('attachment_compatibility', 'attachment-compat:' + weapon + ':' + option['attachment'], weapon,
                [('attachment_authoring', attachment.get('name') or option['attachment'])],
                attachment=_int(attachment['resource']),
                weapons=[_int(value) for value in (player.get(weapon) or {}).get('resources') or []],
                relationship=option['relationship'])
    return links


def load_release(ref=None, source_view=None) -> dict:
    release = resolve_ref(ref)
    tables = load_tables(release)
    release['profile'] = release_profile(release)
    release['fields'] = normalize(tables, source_view)
    release['relationships'] = relationships(tables)
    release['tables'] = tables
    return release
