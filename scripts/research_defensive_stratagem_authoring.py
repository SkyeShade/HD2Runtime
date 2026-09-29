"""Capture retained native evidence for defensive stratagem authoring."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402  central build identity (schemas/build_profile.json)

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = build_profile.SNAPSHOT
WIKI = ROOT.parent / 'HD2WikiImporter/output/wiki_non_offensive_stratagems.json'
NAMED_REFERENCE = ROOT.parent / 'StrongerOrbitalLaser/local_research/external_audit/generated_stratagem_settings.json'
FILEDIVER = ROOT.parent / 'StrongerOrbitalLaser/local_research/dependencies/filediver-reference'
OUTPUT = ROOT / 'build/non-offensive-stratagem-research.json'
RETAINED_OUTPUT = ROOT / 'research/defensive-stratagem-runtime-F5FEE03DCFDB.json'

DEBUG_NAMES = {
    'A/MG-43 Machine Gun Sentry': 'SENTRYS. MACHINEGUN',
    'A/G-16 Gatling Sentry': 'SENTRYS. GATLING',
    'A/M-12 Mortar Sentry': 'SENTRYS. MORTAR',
    'A/M-23 EMS Mortar Sentry': 'SENTRYS. MORTAR STATICFIELD',
    'A/GM-17 Gas Mortar Sentry': 'SENTRYS. MORTAR GAS',
    'A/MLS-4X Rocket Sentry': 'SENTRYS. ROCKET',
    'A/AC-8 Autocannon Sentry': 'SENTRYS. AUTOCANNON',
    'A/FLAM-40 Flame Sentry': 'SENTRYS. FLAMETHROWER',
    'A/ARC-3 Tesla Tower': 'EMPLACEMENTS. TESLA TOWER',
    'A/LAS-98 Laser Sentry': 'SENTRIES. LASER CANNON SENTRY',
    'FX-12 Shield Generator Relay': 'EMPLACEMENTS. SHIELD GENERATOR RELAY',
    'E/MG-101 HMG Emplacement': 'EMPLACEMENTS. HEAVY MACHINEGUN EMPLACEMENT',
    'E/GL-21 Grenadier Battlement': 'EMPLACEMENTS. DEFENSE WALL GRENADE LAUNCHER',
    'E/AT-12 Anti-Tank Emplacement': 'EMPLACEMENTS. ANTI TANK EMPLACEMENT',
    'MD-6 Anti-Personnel Minefield': 'EMPLACEMENTS. ANTI-PERSONNEL MINE DEPLOYER',
    'MD-I4 Incendiary Mines': 'EMPLACEMENTS. INCENDIARY MINE DEPLOYER',
    'MD-17 Anti-Tank Mines': 'EMPLACEMENTS. ANTI-TANK MINE DEPLOYER',
    'MD-8 Gas Mines': 'EMPLACEMENTS. GAS MINE DEPLOYER',
}


# TurretComponent members proven by exact per-sentry agreement with the wiki's detailed weapon tables (which name
# them "Horizontal Turn Speed", "Vertical Turn Speed" and "Vertical Limit"); hidden member-name lengths agree with
# those labels in snake case. (offset, size, storage, hidden-name length) is the layout fingerprint every run checks.
TURRET_FINGERPRINT = ((8, 4, 'FP32', 19), (12, 4, 'FP32', 21), (20, 4, 'FP32', 18), (24, 4, 'FP32', 18),
    (28, 4, 'FP32', 20), (32, 4, 'FP32', 20))
SENSOR_FINGERPRINT = ((0, 4, 'FP32', 8),)
PAYLOAD_FINGERPRINT = ((4, 4, 'FP32', 9),)
# Reviewed wiki sentences stating a sentry's targeting range. Each must still appear verbatim in the imported page;
# SensorEyeComponent +0 must equal the stated value. Sentries whose engagement distance is set by their weapon (the
# Flame Sentry's spray, the Tesla Tower's arc) have no sentence here.
SENSOR_RANGE_STATEMENTS = {
    'A/MG-43 Machine Gun Sentry': ('Like most direct fire sentries, the MG-43 Sentry has a range of 75m', 75),
    'A/G-16 Gatling Sentry': ('The Gatling Sentry has a range of 75m', 75),
    'A/AC-8 Autocannon Sentry': ('The Autocannon Sentry has a maximum range of 100m', 100),
    'A/MLS-4X Rocket Sentry': ('with a 100m engagement distance', 100),
    'A/M-23 EMS Mortar Sentry': ('The EMS mortar has a range of 125 meters', 125),
    'A/LAS-98 Laser Sentry': ('The Laser Sentry has a targeting range of 50m', 50),
    'A/GM-17 Gas Mortar Sentry': ('potential maximum targeting range of 125-meters', 125),
}


def wiki_turret_table(imported: dict) -> dict:
    """The deployed weapon's detailed-table turret rows (horizontal/vertical turn speed, vertical limit, lifetime)."""
    rows = {}
    for field in imported.get('rawStructuredFields') or []:
        section = field.get('section') or ''
        if 'Detailed Weapon Statistics' in section and section.endswith('> Weapon'):
            rows[field['label']] = field['raw']
    result = {}
    for label, key in (('Horizontal Turn Speed', 'horizontalTurnSpeed'), ('Vertical Turn Speed', 'verticalTurnSpeed')):
        if label in rows:
            result[key] = float(rows[label])
    if 'Vertical Limit' in rows:
        low, high = [float(value) for value in
            __import__('re').findall(r'\((-?[\d.]+)\)', rows['Vertical Limit'])]
        result['verticalLimit'] = [low, high]
    if 'Lifetime' in rows:
        result['lifetime'] = float(rows['Lifetime'].split()[0])
    return result


def record_fingerprint(component: str) -> set:
    from migration import build_view
    library = build_view.TypeLibrary((FILEDIVER / 'datalibrary/dl_library.dl_typelib').read_bytes())
    record_type = library.layout(component)['members'][1]['type_hash']
    return {(m['offset'], m['size'], m['storage'], m['nameLength'])
        for m in build_view._record_layout(library, record_type).members}


def component_scalar(component: dict, offset: int):
    for item in component.get('fields', []):
        if item['offset'] == offset:
            return item['value'][0]
    return None


def deployment_proofs(imported: dict, components: list) -> dict:
    """Turret motion, sensor range and deployed lifetime, each tied to wiki evidence or recorded as unproven."""
    by_name = {component['name']: component for component in components}
    table = wiki_turret_table(imported)
    proofs = {'wikiTable': table}
    turret = by_name.get('TurretComponentData')
    if turret:
        native = {'verticalTurnSpeed': component_scalar(turret, 8), 'horizontalTurnSpeed': component_scalar(turret, 12),
            'verticalLimit': [component_scalar(turret, 20), component_scalar(turret, 24)],
            'horizontalLimit': [component_scalar(turret, 28), component_scalar(turret, 32)]}
        checks = {key: native[key] == table[key] for key in ('horizontalTurnSpeed', 'verticalTurnSpeed',
            'verticalLimit') if key in table}
        proofs['turret'] = {'native': native, 'wikiChecks': checks,
            'exact': bool(checks) and all(checks.values())}
    sensor = by_name.get('SensorEyeComponentData')
    if sensor:
        statement = SENSOR_RANGE_STATEMENTS.get(imported['name'])
        text = ' '.join((section.get('text') or '') for section in imported.get('rawSections') or [])
        native_range = component_scalar(sensor, 0)
        item = {'native': native_range, 'statement': None}
        if statement:
            sentence, stated = statement
            if sentence not in text:
                raise ValueError('reviewed sensor range statement no longer on the wiki page: ' + imported['name'])
            item['statement'] = {'text': sentence, 'value': stated, 'exact': native_range == stated}
        proofs['sensor'] = item
    payload = by_name.get('HellpodPayloadComponentData')
    if payload:
        lifetime = component_scalar(payload, 4)
        proofs['lifetime'] = {'native': lifetime, 'wiki': table.get('lifetime'),
            'exact': table.get('lifetime') is not None and lifetime == table['lifetime']}
    return proofs


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def scalar(raw: bytes, offset: int, storage: str):
    return struct.unpack_from({'u32': '<I', 'i32': '<i', 'f32': '<f'}[storage], raw, offset)[0]


def compact_fields(fields, base=0):
    result = []
    for field in fields or []:
        offset = base + field['offset32']
        if 'value' in field:
            result.append({'offset': offset, 'storage': field['storage'].removeprefix('ENUM_'),
                'value': field['value']})
        for records in field.get('records', []):
            result.extend(compact_fields(records, offset))
    dedup = {}
    for item in result:
        dedup.setdefault((item['offset'], item['storage']), item)
    return list(dedup.values())


def compact_component(component):
    item = {key: component.get(key) for key in (
        'name', 'record_type', 'record_index', 'index_row', 'instance_offset',
        'instance_size', 'record_size', 'record_offset_in_instance', 'index_capacity')}
    item['typedReferences'] = component.get('typedReferences', [])
    item['fields'] = compact_fields(component.get('fields'))
    return item


def component_value(component, offset):
    for item in component.get('fields', []):
        if item['offset'] == offset and item['value']:
            return item['value'][0]
    raise ValueError(f"missing component scalar at offset {offset}")


def component_ownership(entities: bytes, probe, component: dict) -> dict:
    """Retain exact record ownership without relying on the target entity alone."""
    _, body, _, _, _ = probe.find_component(entities, component['name'])
    capacity = component['index_capacity']
    record_index = component['record_index']
    owners = []
    for row in range(capacity):
        resource, index, _ = struct.unpack_from('<QII', body, row * 16)
        if resource and index == record_index:
            owners.append(f'0x{resource:016X}')
    if not owners:
        raise ValueError(f"{component['name']} record {record_index} has no owners")
    return {
        'ownerCount': len(owners),
        'ownerResources': sorted(owners),
        'uniqueOwner': len(owners) == 1,
        'recordSha256': component.get('record_sha256'),
    }


def native_graph(settings, components, source):
    projectiles = settings['projectile']
    damages = settings['damage']
    explosions = settings['explosion']
    statuses = settings['status']
    result = []

    def add_damage(damage_type, path, linkage):
        if not damage_type:
            return
        record = damages[damage_type]
        raw = record['raw']
        node = {'kind': 'DamageInfo', 'path': path, 'linkage': linkage,
            'recordType': damage_type, 'group': record['group'], 'row': record['row'],
            'fields': {name: scalar(raw, offset, storage) for name, offset, storage in (
                ('damage.standard_damage', 4, 'i32'), ('damage.durable_damage', 8, 'i32'),
                ('damage.ap_direct', 12, 'u32'), ('damage.ap_slight', 16, 'u32'),
                ('damage.ap_large', 20, 'u32'), ('damage.ap_extreme', 24, 'u32'),
                ('damage.demolition', 28, 'u32'), ('damage.stagger', 32, 'u32'),
                ('damage.push_force', 36, 'u32'))}, 'statuses': []}
        result.append(node)
        for slot, offset in enumerate((44, 52, 60, 68), 1):
            status_type = scalar(raw, offset, 'u32')
            if not status_type:
                continue
            status = statuses[status_type]
            status_path = f'{path}/status:{slot}'
            status_node = {'kind': 'StatusEffectSettings', 'path': status_path,
                'linkage': 'damage_status', 'slot': slot, 'recordType': status_type,
                'group': status['group'], 'row': status['row'],
                'parentDamageType': damage_type, 'parentDamageGroup': record['group'],
                'parentDamageRow': record['row'],
                'fields': {'status.strength': scalar(raw, offset + 4, 'f32'),
                    'status.duration': scalar(status['raw'], 40, 'f32')}}
            result.append(status_node)
            node['statuses'].append(status_path)

    def add_explosion(explosion_type, path, linkage):
        if not explosion_type:
            return
        record = explosions[explosion_type]
        raw = record['raw']
        node = {'kind': 'ExplosionSettings', 'path': path, 'linkage': linkage,
            'recordType': explosion_type, 'group': record['group'], 'row': record['row'],
            'fields': {'explosion.inner_radius': scalar(raw, 16, 'f32'),
                'explosion.outer_radius': scalar(raw, 20, 'f32'),
                'explosion.shockwave_radius': scalar(raw, 24, 'f32')}}
        result.append(node)
        damage_type = scalar(raw, 4, 'u32')
        if damage_type:
            node['damage'] = f'{path}/damage'
            add_damage(damage_type, node['damage'], 'explosion_damage')

    def add_projectile(projectile_type, path, linkage):
        record = projectiles[projectile_type]
        raw = record['raw']
        node = {'kind': 'ProjectileSettings', 'path': path, 'linkage': linkage,
            'recordType': projectile_type, 'group': record['group'], 'row': record['row'],
            'fields': {'projectile.pellet_count': scalar(raw, 28, 'u32'),
                'projectile.velocity': scalar(raw, 32, 'f32'),
                'projectile.mass': scalar(raw, 36, 'f32'),
                'projectile.drag': scalar(raw, 40, 'f32'),
                'projectile.gravity': scalar(raw, 44, 'f32')}}
        result.append(node)
        damage_type = scalar(raw, 60, 'u32')
        if damage_type:
            node['damage'] = f'{path}/damage'
            add_damage(damage_type, node['damage'], 'projectile_damage')
        for phase, offset in (('impact', 144), ('expiry', 156)):
            explosion_type = scalar(raw, offset, 'u32')
            if explosion_type:
                child = f'{path}/{phase}'
                node[phase] = child
                add_explosion(explosion_type, child, f'projectile_{phase}')

    projectile_component = next((c for c in components
        if c['name'] == 'ProjectileWeaponComponentData'), None)
    if projectile_component:
        for ref in projectile_component['typedReferences']:
            if ref['referenceClass'] == 'ProjectileType':
                for projectile_type in dict.fromkeys(ref['values']):
                    add_projectile(projectile_type, 'weapon:primary/attack:primary/projectile',
                        'weapon_projectile')
                break

    def add_component_attack(component_name, settings_name, type_offset, damage_offset, kind):
        component = next((c for c in components if c['name'] == component_name), None)
        if not component:
            return
        settings_type = component_value(component, type_offset)
        record = settings[settings_name][settings_type]
        path = 'weapon:primary/attack:primary'
        node = {'kind': kind, 'path': path, 'linkage': 'weapon_' + settings_name,
            'recordType': settings_type, 'group': record['group'], 'row': record['row']}
        if kind == 'ArcSettings':
            node['fields'] = {name: scalar(record['raw'], offset, storage) for name, offset, storage in (
                ('arc.velocity', 4, 'f32'), ('arc.range', 8, 'f32'),
                ('arc.distance_at_max_spread', 12, 'f32'),
                ('arc.max_angle_spread', 20, 'f32'), ('arc.chain_count', 28, 'u32'),
                ('arc.max_split', 32, 'u32'))}
        else:
            node['fields'] = {'beam.radius': scalar(record['raw'], 4, 'f32'),
                'beam.length': scalar(record['raw'], 8, 'f32')}
        result.append(node)
        damage_type = scalar(record['raw'], damage_offset, 'u32')
        if damage_type:
            add_damage(damage_type, path + '/damage', settings_name + '_damage')

    add_component_attack('ArcWeaponComponentData', 'arc', 0, 36, 'ArcSettings')
    add_component_attack('BeamWeaponComponentData', 'beam', 0, 12, 'BeamSettings')
    spray = next((c for c in components if c['name'] == 'SprayWeaponComponentData'), None)
    if spray:
        add_damage(component_value(spray, 200), 'weapon:primary/attack:primary/damage', 'spray_damage')
    # Mine deployer: MinefieldComponentData +24 (14-character member, ExplosionType enum) is the explosion every
    # deployed mine detonates with; see mine_chain() for the proof that it is the mines' own explosion.
    minefield = next((c for c in components if c['name'] == 'MinefieldComponentData'), None)
    if minefield:
        add_explosion(component_value(minefield, MINEFIELD_EXPLOSION_OFFSET), 'mine:primary/attack:mine',
            'minefield_explosion')
    return result


MINEFIELD_EXPLOSION_OFFSET = 24
# MinefieldComponent layout fingerprint (offset, size, storage, hidden-name length) the proof relies on.
MINEFIELD_FINGERPRINT = [(0, 4, 'UINT32', 25), (4, 4, 'UINT32', 29), (8, 4, 'FP32', 12), (12, 4, 'FP32', 19),
    (16, 4, 'FP32', 8), (20, 4, 'UINT32', 13), (24, 4, 'ENUM_UINT32', 14), (28, 4, 'FP32', 19), (32, 1, 'UINT8', 16),
    (36, 4, 'ENUM_INT32', 28), (40, 1, 'UINT8', 31)]


def mine_chain(native, launcher):
    """Stratagem mine deployer -> thrown mine -> explosion. Read-only evidence.

    The deployer's ThrowerComponent throw slot 0 names the mine unit it launches (+0, u64 resource). Where that unit
    has entity settings (the contact, gas and incendiary mines) its own ExplosiveComponent (+0 mode, +8 arming
    delay, +12 explosion delay, +36 ExplosionType; layout reviewed by the throwable research) must name the same
    explosion row as the deployer's MinefieldComponent +24. The anti-tank mine unit has no entity settings of its
    own, so the deployer's MinefieldComponent is the only native definition of its explosion.
    """
    hexid = lambda value: f'0x{value:016X}'
    minefield = native.component(launcher, 'MinefieldComponentData')
    thrower = native.component(launcher, 'ThrowerComponentData')
    if not minefield or not thrower:
        raise ValueError('mine deployer without MinefieldComponent/ThrowerComponent: ' + launcher)
    field_raw = native.record('MinefieldComponentData', minefield['record_index'])
    explosion_type = struct.unpack_from('<I', field_raw, MINEFIELD_EXPLOSION_OFFSET)[0]
    throw_raw = native.record('ThrowerComponentData', thrower['record_index'])
    unit = struct.unpack_from('<Q', throw_raw, 0)[0]
    nodes = sum(1 for i in range(48) if struct.unpack_from('<I', throw_raw, 48 + 4 * i)[0])
    mine = {'resource': hexid(unit), 'path': native.path(unit), 'entityDefined': False}
    try:
        explosive = native.component(hexid(unit), 'ExplosiveComponentData') if unit else None
    except ValueError as error:
        if 'absent from EntitySettingsHashmap' not in str(error):
            raise
        explosive = None                                  # the unit has no entity settings of its own
    if explosive:
        raw = native.record('ExplosiveComponentData', explosive['record_index'])
        mine.update({'entityDefined': True, 'explosive': {
            'mode': struct.unpack_from('<i', raw, 0)[0],
            'armingDelay': round(struct.unpack_from('<f', raw, 8)[0], 6),
            'explosionDelay': round(struct.unpack_from('<f', raw, 12)[0], 6),
            'explosionType': struct.unpack_from('<I', raw, 36)[0],
            'impactExplosionType': struct.unpack_from('<I', raw, 40)[0]}})
        if mine['explosive']['explosionType'] != explosion_type:
            raise ValueError('mine explosion disagrees with its deployer: ' + launcher)
    ownership = native.ownership(minefield)
    return {'deployer': launcher, 'deployerPath': native.path(int(launcher, 16)),
        'minefield': {'recordIndex': minefield['record_index'], 'indexRow': minefield['index_row'],
            'ownerCount': ownership['ownerCount'], 'uniqueOwner': ownership['uniqueOwner'],
            'explosionOffset': MINEFIELD_EXPLOSION_OFFSET, 'explosionType': explosion_type},
        'thrownMine': mine,
        'explosionAgreement': 'mine entity ExplosiveComponent +36 == deployer MinefieldComponent +24'
            if mine['entityDefined'] else 'deployer MinefieldComponent +24 only (mine unit has no entity settings)',
        'readOnlyObservations': {
            'thrower.launchNodes': nodes,
            'thrower.slot0Counts': [struct.unpack_from('<I', throw_raw, 40)[0], struct.unpack_from('<I', throw_raw, 44)[0]],
            'thrower.slot0Floats': [round(struct.unpack_from('<f', throw_raw, 240 + 4 * i)[0], 4) for i in range(11)],
            'minefield.floats': {str(o): round(struct.unpack_from('<f', field_raw, o)[0], 4) for o in (8, 12, 16, 28)},
            'reason': ('Mine count, spacing, trigger radius, arming and lifetime candidates have no independent '
                'fingerprint (no scraped values, no reviewed code reader), so they are published read-only.')}}


def minefield_layout():
    """MinefieldComponent record members from the pinned type library (hidden names: lengths only)."""
    from migration import build_view
    library = build_view.TypeLibrary((FILEDIVER / 'datalibrary/dl_library.dl_typelib').read_bytes())
    record_type = library.layout('MinefieldComponentData')['members'][1]['type_hash']
    return build_view._record_layout(library, record_type).members


def build() -> dict:
    if not WIKI.exists():
        raise FileNotFoundError(WIKI)
    source = load_module('offensive_research', ROOT / 'scripts/research_stratagem_authoring.py')
    wiki = json.loads(WIKI.read_text(encoding='utf-8'))
    named = source.named_rows(NAMED_REFERENCE)
    snapshot = source.snapshot_evidence(SNAPSHOT)
    by_id = {row['id']: row for row in snapshot['stratagems']}
    settings = {kind: {int(key): dict(value, raw=bytes.fromhex(value['raw']))
        for key, value in records.items()} for kind, records in snapshot['settings'].items()}

    helper_dir = ROOT.parent / 'StrongerOrbitalLaser/scripts/research'
    sys.path.insert(0, str(helper_dir))
    entity_report = load_module('stratagem_entity_report_defensive', helper_dir / 'entity_report.py')
    probe = load_module('probe_components_defensive', helper_dir / 'probe_components.py')
    entities = (FILEDIVER / 'datalibrary/generated_entities.dl_bin').read_bytes()
    typelib = (FILEDIVER / 'datalibrary/dl_library.dl_typelib').read_bytes()
    names = {probe.dl_hash(name): name for name in
        (FILEDIVER / 'hashes/dl_type_names.txt').read_text(encoding='utf-8').splitlines() if name}
    type_hashes = {probe.dl_hash(name): name for name in
        ('ProjectileType', 'ExplosionInfoType', 'DamageInfoType',
         'StatusEffectInfoType', 'BeamInfoType', 'ArcInfoType')}

    import research_entity_authoring
    native = research_entity_authoring.Native()
    layout = {(m['offset'], m['size'], m['storage'], m['nameLength']) for m in minefield_layout()}
    if set(MINEFIELD_FINGERPRINT) - layout:
        raise ValueError('MinefieldComponent layout fingerprint changed')
    for component, fingerprint in (('TurretComponentData', TURRET_FINGERPRINT),
            ('SensorEyeComponentData', SENSOR_FINGERPRINT), ('HellpodPayloadComponentData', PAYLOAD_FINGERPRINT)):
        if set(fingerprint) - record_fingerprint(component):
            raise ValueError(component + ' layout fingerprint changed')
    entries = []
    for imported in wiki['stratagems']:
        if imported['name'] not in DEBUG_NAMES:
            continue
        debug_name = DEBUG_NAMES[imported['name']]
        historical = named[debug_name]
        current = by_id.get(historical['id'])
        if not current:
            raise ValueError(f"current stratagem identity absent: {imported['name']}")
        expected_package = f"0x{int(historical['package']):016X}"
        expected_payloads = [f"0x{int(value):016X}" for value in historical['payload']]
        if current['package'] != expected_package or current['payloads'] != expected_payloads:
            raise ValueError(f"current stratagem ownership changed: {imported['name']}")
        payload_reports = []
        for payload in current['payloads']:
            report = entity_report.report(entities, typelib, payload, names)
            resolved = []
            for component in report['components']:
                if not component['resolved']:
                    continue
                item = {key: component.get(key) for key in (
                    'name', 'record_type', 'record_index', 'index_row', 'instance_offset',
                    'instance_size', 'record_size', 'record_offset_in_instance',
                    'index_capacity')}
                item.update(component_ownership(entities, probe, component))
                item['typedReferences'] = source.typed_references(component, type_hashes)
                if component['name'] in {
                    'HealthComponentData', 'WeaponDataComponentData',
                    'WeaponMagazineComponentData', 'WeaponRoundsComponentData',
                    'WeaponHeatComponentData', 'WeaponChargeComponentData',
                    'ProjectileWeaponComponentData', 'ArcWeaponComponentData',
                    'BeamWeaponComponentData', 'SprayWeaponComponentData',
                    'ExplosiveComponentData', 'MinefieldComponentData',
                    'TurretComponentData', 'SensorEyeComponentData', 'HellpodPayloadComponentData',
                }:
                    item['fields'] = compact_fields(component.get('fields'))
                resolved.append(item)
            payload_reports.append({
                'payload': payload,
                'components': resolved,
            })
        graph = imported['graph']['nodes']
        entity_components = payload_reports[0]['components']
        imported_entity = next(node for node in graph if node['id'] == 'entity.main')
        imported_health = imported_entity['entity']['mainHealth']['value']
        imported_armor = imported_entity['entity']['mainArmor']['value']
        health_component = next((component for component in entity_components
            if component['name'] == 'HealthComponentData'), None)
        if not health_component:
            raise ValueError(f"missing deployed health owner: {imported['name']}")
        native_health = component_value(health_component, 0)
        native_armor = component_value(health_component, 280)
        if native_health != imported_health or native_armor != imported_armor:
            raise ValueError(f"deployed health/armor correlation changed: {imported['name']}")
        entries.append({
            'name': imported['name'],
            'family': imported['normalizedFamily'],
            'wiki': {'name': imported['name'], 'family': imported['family'],
                'normalizedFamily': imported['normalizedFamily'],
                'wikiPage': imported['wikiPage'], 'traits': imported['traits']},
            'historicalIdentity': {'debugName': debug_name, 'id': historical['id'],
                'package': expected_package, 'payloads': expected_payloads},
            'currentRoot': current,
            'payloadReports': payload_reports,
            'deployedEntity': {
                'resource': current['payloads'][0],
                'kind': next((node['kind'] for node in graph if node['id'] == 'entity.main'),
                    imported['normalizedFamily']),
                'componentNames': [component['name'] for component in entity_components],
                'nativeGraph': native_graph(settings, entity_components, source),
                'healthArmorProof': {
                    'nativeHealth': native_health,
                    'nativeArmor': native_armor,
                    'importedHealth': imported_health,
                    'importedArmor': imported_armor,
                    'exactCorrelation': True,
                    'layoutAnchor': 'HealthComponentData reviewed main health/default armor layout',
                },
            },
            'deploymentProofs': deployment_proofs(imported, entity_components),
            'mineChain': mine_chain(native, current['payloads'][0])
                if imported['normalizedFamily'].lower() == 'mine' else None,
            'importedBranches': [{key: node.get(key) for key in
                ('id', 'name', 'kind', 'parentId', 'childIds', 'sourcePath',
                 'relationshipEvidence', 'relationshipVerified')}
                for node in graph],
        })

    return {
        'schemaVersion': 1,
        'source': {'wikiCommit': '0b0c9fca9866be5f0841dc4aec19d01ece134db9',
            'snapshot': SNAPSHOT.name, 'mode': 'snapshot', 'writes': 0,
            'protectionChanges': 0, 'fixtureFallback': 'disabled'},
        'stratagems': entries,
        'scope': {'sentries': 10, 'emplacements': 4, 'mines': 4},
    }


def main() -> None:
    report = build()
    body = json.dumps(report, indent=2, allow_nan=False) + '\n'
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    RETAINED_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(body, encoding='utf-8')
    RETAINED_OUTPUT.write_text(body, encoding='utf-8')
    print(json.dumps({'stratagems': len(report['stratagems']), 'writes': 0,
        'protectionChanges': 0, 'fixtureFallback': 'disabled'}, indent=2))


if __name__ == '__main__':
    main()
