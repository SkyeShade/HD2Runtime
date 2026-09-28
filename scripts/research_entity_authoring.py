"""Capture retained native evidence for vehicle, backpack, and deployed-shield authoring.

Identity chains are structural:

* vehicle stratagems: StratagemDefinition payload -> vehicle entity (unique owner row)
* backpack stratagems: StratagemDefinition payload -> hellpod rack -> RackAttach.Item
  -> backpack entity
* mounted weapons: MountComponent.Infos[n].Path -> mounted entity owning weapon components

Wiki data is only used as catalog identity and exact-value correlation. Field
semantics come from typed native schema members plus reviewed reference-mod
gameplay evidence recorded with file hashes. Nothing here writes memory.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
SIBLINGS = ROOT.parent
SNAPSHOT = Path(r'C:\Users\Skye\AppData\Local\HD2Runtime\local_research\snapshots\F5FEE03DCFDB-20260926T222226Z.hd2snap')
WIKI_VEHICLES = SIBLINGS / 'HD2WikiImporter/output/wiki_vehicle_stratagems.json'
WIKI_NON_OFFENSIVE = SIBLINGS / 'HD2WikiImporter/output/wiki_non_offensive_stratagems.json'
NAMED_REFERENCE = SIBLINGS / 'StrongerOrbitalLaser/local_research/external_audit/generated_stratagem_settings.json'
FILEDIVER = SIBLINGS / 'StrongerOrbitalLaser/local_research/dependencies/filediver-reference'
HELPERS = SIBLINGS / 'StrongerOrbitalLaser/scripts/research'
OUTPUT = ROOT / 'build/entity-authoring-research.json'
RETAINED_OUTPUT = ROOT / 'research/entity-authoring-runtime-F5FEE03DCFDB.json'
ENTITY_SHA256 = '21377252B81FDBC670EBA1E59A8AB64B170323DF208F175E708992E4C1FB515E'
TYPELIB_SHA256 = '4D04870D0A0D4DC1284998C72CDFA6F8FF6D21ABA0E36B6F758C6F73DD0417A4'

# Reviewed wiki catalog name -> historical StratagemDefinition debug name.
VEHICLE_DEBUG_NAMES = {
    'M-102 Gunner FRV': 'VEHICLES. FAST RECON VEHICLE (FRV)',
    'M-103 Supply FRV': 'VEHICLES. FAST RECON VEHICLE (Resupply Auto Turret)',
    'M-104 Incinerator FRV': 'VEHICLES. FAST RECON VEHICLE (Ramming Flamethrower)',
    'EXO-45 Patriot Exosuit': 'VEHICLES. COMBAT WALKER',
    'EXO-49 Emancipator Exosuit': 'VEHICLES. COMBAT WALKER OBSIDIAN',
    'EXO-51 Lumberer Exosuit': 'VEHICLES. COMBAT WALKER LUMBERER',
    'EXO-55 Breakthrough Exosuit': 'VEHICLES. COMBAT WALKER BREACHER',
    'TD-220 Bastion MK XVI': 'VEHICLES. BASTION(tank)',
}
# No historical debug-name row exists for the Maelstrom. Its current definition is
# the unique stratagem row whose primary payload is this native entity path.
VEHICLE_ENTITY_PATHS = {
    'TD-110 Maelstrom': 'content/fac_helldivers/vehicles/tank_storm/tank_storm',
}
# Vehicles outside the wiki stratagem catalog that the reference FRV swap patches
# or that own discovered mounted weapons.
NATIVE_ONLY_VEHICLES = {
    'FRV (Super Earth variant)': 'content/fac_helldivers/vehicles/frv/frv_superearth',
    'GATER Oil Rig': 'content/fac_helldivers/vehicles/oilrig/oil_rig',
}
BACKPACK_DEBUG_NAMES = {
    'B-1 Supply Pack': 'BACKPACK. SUPPLY BACKPACK',
    'LIFT-850 Jump Pack': 'BACKPACK. JUMPPACK BACKPACK',
    'SH-20 Ballistic Shield Backpack': 'BACKPACK. BALLISTIC SHIELD BACKPACK',
    'AX/AR-23 Guard Dog': 'BACKPACK. GUARD DOG (Drone)',
    'AX/LAS-5 Rover': 'BACKPACK. Laser Rifle (Drone)',
    'SH-32 Shield Generator Pack': 'BACKPACK.  GENERATOR PACK',
    'SH-51 Directional Shield': 'BACKPACK. DIRECTIONAL ENERGY SHIELD',
    'AX/FLAM-75 Hot Dog': 'BACKPACK. GUARD DOG FLAMETHROWER (Drone)',
    'B-100 Portable Hellbomb': 'BACKPACK. HELLBOMB',
    'AX/ARC-3 K-9': 'BACKPACK. GUARD DOG (Drone) Stun',
    'LIFT-860 Hover Pack': 'BACKPACK. HOVERPACK BACKPACK',
    'AX/TX-13 Dog Breath': 'BACKPACK. GUARD DOG GAS PROJECTOR (Drone)',
    'LIFT-182 Warp Pack': 'BACKPACK. DISPLACEMENT BACKPACK',
}
SHIELD_RELAY = 'FX-12 Shield Generator Relay'
WEAPON_FAMILIES = {'ProjectileWeaponComponentData': 'projectile', 'SprayWeaponComponentData': 'spray',
    'BeamWeaponComponentData': 'beam', 'ArcWeaponComponentData': 'arc'}

# Reference mods: exact files whose conclusions justify promotion. Hashes pin the
# evidence; the quoted conclusions are copied verbatim from those files.
REFERENCE_MODS = {
    'ShieldRelayImprovements': {
        'files': ['research/durability-confirmation.json', 'research/gameplay-confirmation-0.1.4.json',
            'research/frozen-gameplay-baseline.json', 'docs/physical-hp-proof.md',
            'scripts/shield_reference.py', 'scripts/research/physical_hp_reference.py',
            'research/findings.md', 'research/remaining-features-audit.md'],
        'gameplayProofs': {
            'shield.radius': 'research/gameplay-confirmation-0.1.4.json: shield_radius_15_to_8_functional',
            'shield.durability': 'research/durability-confirmation.json: 4000 -> 40000 confirmed in gameplay',
            'payload.lifetime': 'research/gameplay-confirmation-0.1.4.json: relay_lifetime_40_to_90',
            'stratagem.cooldown': 'research/frozen-gameplay-baseline.json: 180 s call-in cooldown confirmed',
            'entity.health': 'docs/physical-hp-proof.md: user confirmed the emitter HP increase in gameplay',
            'zone.health': ('docs/physical-hp-proof.md: slot-0 zone HP was written together with main HP '
                'in the gameplay-confirmed preset; its individual effect is not isolated'),
        },
        'recreation': [
            {'target': 'shield', 'field': 'shield.radius', 'expect': 15, 'value': 8},
            {'target': 'shield', 'field': 'shield.durability', 'expect': 4000, 'value': 40000},
            {'target': 'deployed_entity', 'field': 'payload.lifetime', 'expect': 40, 'value': 90},
            {'target': 'stratagem', 'field': 'stratagem.cooldown', 'expect': 90, 'value': 180},
            {'target': 'deployed_entity', 'field': 'entity.health', 'expect': 450, 'value': 4500},
            {'target': 'damage_zone', 'zone': 0, 'field': 'zone.health', 'expect': 450, 'value': 4500},
        ],
        'unpromoted': {
            'shield +88/+92/+96/+100': ('Recharge delay, broken delay, recharge rate, and restart charge '
                'labels come from an external export only; no reference mod wrote them.'),
            'zone explosive damage percentage': 'Gameplay test failed to change grenade damage to the emitter.',
        },
    },
    'BastionReArmored': {
        'files': ['research/armor-proof.md', 'research/lunchbox-transfer-proof.md',
            'research/main-hp-proof.md', 'src/release/validate.lua', 'src/armor_proof/validate.lua',
            'src/lunchbox_proof/validate.lua'],
        'gameplayProofs': {
            'zone.armor': 'research/armor-proof.md: the AP9 experiment succeeded in gameplay (Bastion)',
            'entity.armor': 'research/armor-proof.md: default-zone AP was part of the AP9 gameplay proof (Bastion)',
            'zone.affects_main_health': ('research/lunchbox-transfer-proof.md: zone 3/4 transfer 1.0 -> 0.0 '
                'succeeded in gameplay (Bastion)'),
            'entity.health': 'research/main-hp-proof.md: 100,000 main HP is live (Bastion)',
        },
        'gameplayVehicle': 'TD-220 Bastion MK XVI',
        'presets': [16000, 24000, 32000],
    },
    'FRVWeaponSwap': {
        'files': ['research/frv-gater-mount.md', 'src/current_build.json', 'src/frv_weapon_swap.lua'],
        'liveWriteVerified': ('MountComponent slot 0 Path of the FRV and Super Earth FRV records rewritten '
            'from the FRV HMG to the GATER autocannon; the committed-write log is live, gameplay is unconfirmed'),
    },
    'JumpPackImprovements': {
        'files': ['research/current-build-port.md', 'research/movement.md', 'research/README.md',
            'releases/JumpPackImprovements-0.3.4-build-report.json', 'src/config.lua'],
        'gameplayProofs': {
            'recharge.time': 'research/README.md: the user confirmed the recharge effect in dev-0.8',
            'jump.vertical_launch_velocity': ('releases/JumpPackImprovements-0.3.4-build-report.json: '
                'vertical_launch_gameplay_proven_by_user'),
        },
        'recreation': [
            {'field': 'recharge.time', 'expect': 15, 'value': 8},
            {'field': 'jump.vertical_launch_velocity', 'expect': 40, 'value': 50},
        ],
        'unpromoted': {
            'Jumppack +0x04': 'Experiment profile offset04-x4 was never gameplay-reported.',
            'Jumppack +0x24': 'Experiment profile offset24-x10 was never gameplay-reported.',
            'horizontal impulse': 'No horizontal or forward impulse member has been identified.',
        },
    },
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def hexid(value: int) -> str:
    return f'0x{value:016X}'


class Native:
    """Offline typed access to the pinned decoded entity table."""

    def __init__(self):
        sys.path.insert(0, str(HELPERS))
        self.report_module = load_module('entity_report_entity_authoring', HELPERS / 'entity_report.py')
        self.probe = load_module('probe_entity_authoring', HELPERS / 'probe_components.py')
        self.typelib_module = load_module('inspect_typelib_entity_authoring', HELPERS / 'inspect_typelib.py')
        self.entities = (FILEDIVER / 'datalibrary/generated_entities.dl_bin').read_bytes()
        self.typelib = (FILEDIVER / 'datalibrary/dl_library.dl_typelib').read_bytes()
        if sha(self.entities) != ENTITY_SHA256 or sha(self.typelib) != TYPELIB_SHA256:
            raise ValueError('pinned decoded entity reference changed')
        self.names = {self.probe.dl_hash(name): name for name in
            (FILEDIVER / 'hashes/dl_type_names.txt').read_text(encoding='utf-8').splitlines() if name}
        self.paths = {}
        for line in (FILEDIVER / 'hashes/hashes.txt').read_text(encoding='utf-8', errors='ignore').splitlines():
            line = line.strip()
            if line and not line.startswith('//'):
                self.paths[self.probe.resource_hash(line)] = line
        self.thin = {}
        for line in (FILEDIVER / 'hashes/thinhashes.txt').read_text(encoding='utf-8', errors='ignore').splitlines():
            line = line.strip()
            if line:
                self.thin.setdefault(self.probe.resource_hash(line) >> 32, line)
        self.reports = {}
        self.tables = {}

    def report(self, resource: str) -> dict:
        if resource not in self.reports:
            self.reports[resource] = self.report_module.report(
                self.entities, self.typelib, resource, self.names)
        return self.reports[resource]

    def component(self, resource: str, name: str) -> dict | None:
        found = [c for c in self.report(resource)['components'] if c['name'] == name]
        if len(found) > 1:
            raise ValueError(f'{name} membership ambiguous for {resource}')
        if not found or not found[0]['resolved']:
            return None
        return found[0]

    def table(self, name: str):
        """Return (body, index capacity, record offset, record size) for a component table."""
        if name not in self.tables:
            _, body, _, _, _ = self.probe.find_component(self.entities, name)
            desc = self.typelib_module.layout(self.typelib, name, structured=True)
            index, records = desc['members']
            record_size = records['size64'] // records['array_or_bits']
            self.tables[name] = (body, index['array_or_bits'], records['offset64'],
                record_size, records['array_or_bits'])
        return self.tables[name]

    def owners(self, name: str) -> dict[int, list[int]]:
        body, capacity, _, _, _ = self.table(name)
        result = {}
        for row in range(capacity):
            resource, record, reserved = struct.unpack_from('<QII', body, row * 16)
            if resource:
                if reserved:
                    raise ValueError(f'{name} index reserved field is non-zero')
                result.setdefault(record, []).append(resource)
        return result

    def record(self, name: str, index: int) -> bytes:
        body, _, offset, size, count = self.table(name)
        if index >= count:
            raise ValueError(f'{name} record out of range')
        return body[offset + index * size:offset + (index + 1) * size]

    def ownership(self, component: dict) -> dict:
        owners = self.owners(component['name']).get(component['record_index'], [])
        if not owners:
            raise ValueError(f"{component['name']} record {component['record_index']} has no owners")
        return {'component': component['name'], 'recordIndex': component['record_index'],
            'indexRow': component['index_row'], 'recordSize': component['record_size'],
            'ownerCount': len(owners), 'uniqueOwner': len(owners) == 1,
            'ownerResources': sorted(hexid(value) for value in owners),
            'recordSha256': component['record_sha256']}

    def entity_row(self, resource: int) -> int:
        _, body, _, _, _ = self.probe.find_component(self.entities, 'EntitySettingsHashmap')
        rows = [row for row in range(4096) if struct.unpack_from('<Q', body, row * 32)[0] == resource]
        if len(rows) != 1:
            raise ValueError(f'entity owner absent or ambiguous: {hexid(resource)}')
        return rows[0]

    def path(self, resource: int) -> str | None:
        return self.paths.get(resource)

    def thin_name(self, value: int) -> str | None:
        return self.thin.get(value) if value else None


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def i32(raw, at):
    return struct.unpack_from('<i', raw, at)[0]


def f32(raw, at):
    return round(struct.unpack_from('<f', raw, at)[0], 6)


def health_evidence(native: Native, resource: str) -> dict | None:
    component = native.component(resource, 'HealthComponentData')
    if not component:
        return None
    raw = native.record('HealthComponentData', component['record_index'])
    if len(raw) != 22096 or component['record_type'] != 'HealthComponent':
        raise ValueError('HealthComponent layout changed')
    zones = []
    for index in range(38):
        base = 520 + index * 552
        name = u32(raw, base + 96)
        actors = [value for value in struct.unpack_from('<24I', raw, base + 456) if value]
        children = [value for value in struct.unpack_from('<16I', raw, base + 256) if value]
        zones.append({'index': index, 'nameHash': name, 'name': native.thin_name(name),
            'populated': bool(name), 'actorCount': len(actors),
            'armor': u32(raw, base + 216), 'health': i32(raw, base + 232),
            'constitution': i32(raw, base + 236),
            'affectsMainHealth': f32(raw, base + 248),
            'mainHealthCappedByZone': raw[base + 340],
            'childZoneHashes': children})
    return {'ownership': native.ownership(component),
        'mainHealth': i32(raw, 0), 'defaultArmor': u32(raw, 64 + 216),
        'defaultZoneNameHash': u32(raw, 64 + 96),
        'defaultZoneName': native.thin_name(u32(raw, 64 + 96)), 'zones': zones}


def weapon_identity(native: Native, resource: int) -> dict:
    text = hexid(resource)
    try:
        report = native.report(text)
    except ValueError as error:
        return {'resource': text, 'path': native.path(resource), 'weapon': False,
            'reason': str(error)}
    names = [c['name'] for c in report['components'] if c['name'] and c['resolved']]
    families = sorted({family for component, family in WEAPON_FAMILIES.items() if component in names})
    package = native.component(text, 'LoadoutPackageComponentData')
    package_hash = None
    if package:
        package_hash = struct.unpack_from('<Q', native.record('LoadoutPackageComponentData',
            package['record_index']), 8)[0]
    return {'resource': text, 'path': native.path(resource),
        'weapon': 'WeaponDataComponentData' in names and len(families) == 1,
        'attackFamilies': families, 'turret': 'TurretComponentData' in names,
        'components': sorted(name.removesuffix('ComponentData') for name in names
            if name.startswith('Weapon') or name in WEAPON_FAMILIES or name == 'TurretComponentData'),
        'loadoutPackage': hexid(package_hash) if package_hash else None,
        'entityRow': native.entity_row(resource)}


def mount_survey(native: Native) -> tuple[dict, dict]:
    """Return every MountComponent record and every mounted entity identity."""
    owners = native.owners('MountComponentData')
    records = {}
    mounted = {}
    for record_index in range(native.table('MountComponentData')[4]):
        raw = native.record('MountComponentData', record_index)
        slots = []
        for slot in range(5):
            path, node, side, name, flag_a, flag_b = struct.unpack_from('<QIiIBB', raw, slot * 24)
            if not path and not name:
                continue
            slots.append({'slot': slot, 'path': hexid(path), 'attachNode': node,
                'attachNodeName': native.thin_name(node), 'mountSide': side,
                'nameHash': name, 'name': native.thin_name(name), 'flags': [flag_a, flag_b]})
            if path:
                mounted.setdefault(path, []).append({'record': record_index, 'slot': slot})
        records[record_index] = {'record': record_index,
            'owners': sorted(hexid(value) for value in owners.get(record_index, [])),
            'slots': slots, 'recordSha256': sha(raw)}
    identities = {}
    for resource, uses in mounted.items():
        identity = weapon_identity(native, resource)
        identity['referencedBy'] = uses
        identities[hexid(resource)] = identity
    return records, identities


def vehicle_entry(native, name, resource, root, source, wiki, mount_records):
    entity = int(resource, 16)
    health = health_evidence(native, resource)
    mount = native.component(resource, 'MountComponentData')
    if not health or not mount or not native.component(resource, 'VehicleComponentData'):
        raise ValueError(f'vehicle components absent: {name}')
    record = mount_records[mount['record_index']]
    if resource not in record['owners']:
        raise ValueError(f'mount ownership changed: {name}')
    return {'name': name, 'catalogSource': source, 'resource': resource,
        'nativePath': native.path(entity), 'entityRow': native.entity_row(entity),
        'stratagemRoot': root, 'wiki': wiki, 'health': health,
        'mount': dict(native.ownership(mount), slots=record['slots'])}


def wiki_fact(entry, key):
    return next((fact['value'] for fact in entry['vehicle']['facts']
        if fact['key'] == key and fact['subjectId'] == 'entity.main'), None)


def current_root(by_id, named, debug_name):
    historical = named[debug_name]
    row = by_id.get(historical['id'])
    if not row:
        raise ValueError(f'current stratagem identity absent: {debug_name}')
    package = f"0x{int(historical['package']):016X}"
    payloads = [f"0x{int(value):016X}" for value in historical['payload']]
    if row['package'] != package or row['payloads'] != payloads:
        raise ValueError(f'current stratagem ownership changed: {debug_name}')
    return row


def primary_payload(row):
    payloads = row.get('payloads')
    return payloads[0] if isinstance(payloads, list) and payloads else None


def root_summary(row, debug_name, basis):
    return {'id': row['id'], 'package': row['package'], 'payloads': row['payloads'],
        'group': row['group'], 'row': row['row'], 'cooldown': row['cooldown'],
        'use_count': row['use_count'], 'debugName': debug_name, 'identityBasis': basis}


def reference_mods() -> dict:
    result = {}
    for project, item in REFERENCE_MODS.items():
        files = []
        for relative in item['files']:
            path = SIBLINGS / project / relative
            files.append({'path': f'{project}/{relative}', 'sha256': sha(path.read_bytes())})
        result[project] = dict({key: value for key, value in item.items() if key != 'files'}, files=files)
    return result


def build() -> dict:
    native = Native()
    research = load_module('offensive_research_entity', ROOT / 'scripts/research_stratagem_authoring.py')
    snapshot = research.snapshot_evidence(SNAPSHOT)
    by_id = {row['id']: row for row in snapshot['stratagems']}
    named = research.named_rows(NAMED_REFERENCE)
    wiki_vehicles = json.loads(WIKI_VEHICLES.read_text(encoding='utf-8'))
    wiki_other = json.loads(WIKI_NON_OFFENSIVE.read_text(encoding='utf-8'))
    mount_records, mounted = mount_survey(native)

    vehicles = []
    for item in wiki_vehicles['stratagems']:
        name = item['name']
        if name in VEHICLE_DEBUG_NAMES:
            row = current_root(by_id, named, VEHICLE_DEBUG_NAMES[name])
            root = root_summary(row, VEHICLE_DEBUG_NAMES[name], 'historical debug-name identity')
        else:
            path = VEHICLE_ENTITY_PATHS[name]
            resource = hexid(native.probe.resource_hash(path))
            rows = [row for row in snapshot['stratagems'] if primary_payload(row) == resource]
            if len(rows) != 1:
                raise ValueError(f'current stratagem payload owner absent or ambiguous: {name}')
            row = rows[0]
            root = root_summary(row, None, 'unique current primary-payload owner')
        resource = row['payloads'][0]
        facts = {'mainHealth': wiki_fact(item, 'mainHealth'), 'mainArmor': wiki_fact(item, 'mainArmor'),
            'cooldown': item['stratagem']['cooldownSeconds']['value'],
            'vehicleClass': item['vehicle']['vehicleClass'],
            'mountedWeapons': [weapon['designation'] for weapon in item['vehicle']['mountedWeapons']]}
        entry = vehicle_entry(native, name, resource, root, 'wiki_stratagem', facts, mount_records)
        health = entry['health']
        correlation = {'cooldown': root['cooldown'] == facts['cooldown']}
        if facts['mainHealth'] is not None:
            correlation['mainHealth'] = health['mainHealth'] == facts['mainHealth']
        if facts['mainArmor'] is not None:
            correlation['mainArmor'] = health['defaultArmor'] == facts['mainArmor']
        if not all(correlation.values()):
            raise ValueError(f'wiki/native vehicle correlation failed: {name}: {correlation}')
        entry['correlation'] = correlation
        vehicles.append(entry)
    for name, path in NATIVE_ONLY_VEHICLES.items():
        resource = hexid(native.probe.resource_hash(path))
        if any(primary_payload(row) == resource for row in snapshot['stratagems']):
            raise ValueError(f'native-only vehicle unexpectedly has a stratagem root: {name}')
        entry = vehicle_entry(native, name, resource, None, 'native_only', None, mount_records)
        entry['correlation'] = {'nativePath': entry['nativePath'] == path}
        vehicles.append(entry)

    backpacks = []
    wiki_backpacks = {item['name']: item for item in wiki_other['stratagems']
        if item['normalizedFamily'] == 'Backpack'}
    if set(wiki_backpacks) != set(BACKPACK_DEBUG_NAMES):
        raise ValueError('wiki backpack catalog changed')
    for name, debug_name in BACKPACK_DEBUG_NAMES.items():
        row = current_root(by_id, named, debug_name)
        rack_resource = row['payloads'][0]
        rack = native.component(rack_resource, 'HellpodRackComponentData')
        if not rack:
            raise ValueError(f'backpack call-in rack absent: {name}')
        raw = native.record('HellpodRackComponentData', rack['record_index'])
        items = sorted({hexid(struct.unpack_from('<Q', raw, slot * 64)[0]) for slot in range(8)
            if struct.unpack_from('<Q', raw, slot * 64)[0]})
        if len(items) != 1:
            raise ValueError(f'backpack rack does not attach exactly one item identity: {name}')
        resource = items[0]
        if not native.component(resource, 'BackpackComponentData'):
            raise ValueError(f'rack item is not a backpack entity: {name}')
        components = {}
        for component_name in ('RechargeComponentData', 'JumppackComponentData', 'ShieldComponentData',
                'DepositComponentData', 'HealthComponentData', 'BackpackComponentData'):
            component = native.component(resource, component_name)
            if not component:
                continue
            record = native.record(component_name, component['record_index'])
            value = native.ownership(component)
            if component_name == 'RechargeComponentData':
                value['values'] = {'0': f32(record, 0)}
            elif component_name == 'JumppackComponentData':
                value['values'] = {str(offset): f32(record, offset) for offset in (0, 4, 36)}
            elif component_name == 'ShieldComponentData':
                value['values'] = {str(offset): f32(record, offset) for offset in (0, 76, 88, 92, 96, 100)}
            elif component_name == 'DepositComponentData':
                value['values'] = {'0': u32(record, 0), '4': i32(record, 4), '8': u32(record, 8)}
            elif component_name == 'HealthComponentData':
                value['values'] = {'0': i32(record, 0), '280': u32(record, 280)}
            components[component_name] = value
        wiki = wiki_backpacks[name]
        facts = {'cooldown': wiki['stratagem']['cooldownSeconds']['value']}
        for node in wiki['graph']['nodes']:
            if node['id'] == 'entity.main':
                for key in ('mainHealth', 'mainArmor'):
                    value = (node.get('entity') or {}).get(key)
                    if isinstance(value, dict):
                        facts[key] = value.get('value')
                for key in ('startingRounds', 'maxRounds'):
                    value = (node.get('equipment') or {}).get(key)
                    if isinstance(value, dict):
                        facts[key] = value.get('value')
        correlation = {'cooldown': row['cooldown'] == facts['cooldown']}
        if 'HealthComponentData' in components and facts.get('mainHealth') is not None:
            health = components['HealthComponentData']['values']
            correlation['mainHealth'] = health['0'] == facts['mainHealth']
            correlation['mainArmor'] = health['280'] == facts.get('mainArmor')
        if 'DepositComponentData' in components and facts.get('maxRounds') is not None:
            deposit = components['DepositComponentData']['values']
            correlation['depositCapacity'] = deposit['0'] == facts['maxRounds']
            correlation['depositStart'] = deposit['4'] == facts.get('startingRounds')
        if not correlation['cooldown']:
            raise ValueError(f'backpack cooldown correlation failed: {name}')
        backpacks.append({'name': name, 'debugName': debug_name,
            'stratagemRoot': root_summary(row, debug_name, 'historical debug-name identity'),
            'rack': dict(native.ownership(rack), attachedItems=items),
            'resource': resource, 'nativePath': native.path(int(resource, 16)),
            'entityRow': native.entity_row(int(resource, 16)),
            'components': components, 'wiki': facts, 'correlation': correlation})

    relay_resource = '0xED13DDC480EC6910'
    shield = native.component(relay_resource, 'ShieldComponentData')
    payload = native.component(relay_resource, 'HellpodPayloadComponentData')
    shield_raw = native.record('ShieldComponentData', shield['record_index'])
    payload_raw = native.record('HellpodPayloadComponentData', payload['record_index'])
    relay = {'name': SHIELD_RELAY, 'resource': relay_resource,
        'shield': dict(native.ownership(shield), values={str(offset): f32(shield_raw, offset)
            for offset in (0, 76, 88, 92, 96, 100)}),
        'payload': dict(native.ownership(payload), values={'0': f32(payload_raw, 0),
            '4': f32(payload_raw, 4), '8': u32(payload_raw, 8)}),
        'health': health_evidence(native, relay_resource)}

    defensive = json.loads((ROOT / 'research/defensive-stratagem-runtime-F5FEE03DCFDB.json').read_text())
    deployed_health = {}
    for item in defensive['stratagems']:
        resource = item['deployedEntity']['resource']
        deployed_health[item['name']] = health_evidence(native, resource)

    return {'schemaVersion': 1,
        'source': {'snapshot': SNAPSHOT.name, 'mode': 'snapshot', 'writes': 0, 'protectionChanges': 0,
            'fixtureFallback': 'disabled', 'entitiesSha256': ENTITY_SHA256,
            'typelibSha256': TYPELIB_SHA256,
            'wikiVehicles': wiki_vehicles.get('source'), 'wikiNonOffensive': wiki_other.get('source')},
        'vehicles': vehicles, 'mountRecords': [mount_records[key] for key in sorted(mount_records)],
        'mountedEntities': dict(sorted(mounted.items())), 'backpacks': backpacks,
        'shieldRelay': relay, 'deployedHealth': deployed_health,
        'referenceMods': reference_mods()}


def main() -> None:
    report = build()
    body = json.dumps(report, indent=1, allow_nan=False) + '\n'
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(body)
    RETAINED_OUTPUT.write_text(body)
    print(json.dumps({'vehicles': len(report['vehicles']), 'backpacks': len(report['backpacks']),
        'mountRecords': len(report['mountRecords']), 'mountedEntities': len(report['mountedEntities'])}))


if __name__ == '__main__':
    main()
