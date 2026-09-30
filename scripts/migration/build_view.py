"""Structural view of one Helldivers 2 build, for migration. Offline research tooling; never used in game.

A BuildView holds the native tables HD2Runtime's mappings rely on, parsed with the build's own type
library (no addresses):

* entities: EntitySettingsHashmap rows and every relied-on component table (index rows, records, owners);
* settings: projectile, damage, explosion, arc, beam (and status, snapshot only) rows keyed by native type;
* entity deltas (magazine attachments);
* stratagem rows (snapshot of a known game.dll only; the table is located through game.dll);
* layouts: member offset, storage and hidden-name length for every relied-on type.

Inputs: a Filediver datalibrary directory (generated_*.dl_bin + dl_library.dl_typelib) and/or a snapshot
(.hd2snap). A snapshot of a build whose type library is not available must be paired with a datalibrary.
Snapshot extraction is cached under build/migration-cache/, keyed by the snapshot header, file size and extractor
version; a key mismatch always re-extracts, and every report records whether the cache was used.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import dl_hash, find_component, groups, rows  # noqa: E402
import build_profile  # noqa: E402

EXTRACTOR_VERSION = 4
CACHE = ROOT / 'build/migration-cache'
SETTINGS_FILES = {'projectile': 'generated_projectile_settings.dl_bin', 'damage': 'generated_damage_settings.dl_bin',
    'explosion': 'generated_explosion_settings.dl_bin', 'arc': 'generated_arc_settings.dl_bin',
    'beam': 'generated_beam_settings.dl_bin'}
ENTITIES_FILE, TYPELIB_FILE, DELTAS_FILE = 'generated_entities.dl_bin', 'dl_library.dl_typelib', 'generated_entity_deltas.dl_bin'
# Components the mappings and relationship checks read (superset of the runtime profile's list).
COMPONENTS = ('ProjectileWeaponComponentData', 'WeaponDataComponentData', 'HealthComponentData',
    'OrbitalAbilityComponentData', 'ShieldComponentData', 'HellpodPayloadComponentData', 'RechargeComponentData',
    'JumppackComponentData', 'LoadoutPackageComponentData', 'WeaponMagazineComponentData', 'WeaponRoundsComponentData',
    'WeaponCustomizationComponentData', 'ArcWeaponComponentData', 'MeleeWeaponComponentData', 'BeamWeaponComponentData',
    'SprayWeaponComponentData', 'WeaponHeatComponentData', 'WeaponChargeComponentData', 'ExplosiveComponentData',
    'HellpodRackComponentData', 'WeaponLinkedAmmoComponentData', 'BackpackComponentData', 'WeaponLinkerComponentData',
    'BombardmentComponentData', 'EagleComponentData', 'MountComponentData', 'WeaponReloadComponentData',
    'WeaponWindUpComponentData', 'DepositComponentData', 'TagComponentData', 'InteractableComponentData',
    'ThrowableComponentData', 'StickyComponentData', 'MinefieldComponentData', 'TurretComponentData',
    'SensorEyeComponentData', 'ThrowerComponentData', 'LoadoutEntryComponentData', 'DisplacementComponentData',
    'ShieldControllerComponentData')
NAME_LENGTH = re.compile(r'inferred_length=(\d+|None)')


# DL type library member descriptors: the 2026-09-26 build uses 72-byte members (an extra offset after the comment
# and 16 trailing bytes); the previous build used 52. Field positions for each format:
MEMBER_FORMATS = {72: {'type': 12, 'sizes': 20}, 52: {'type': 8, 'sizes': 16}}
TL_HEADER = struct.Struct('<4s8I')
STORAGE = ('INT8', 'INT16', 'INT32', 'INT64', 'UINT8', 'UINT16', 'UINT32', 'UINT64', 'FP32', 'FP64', 'ENUM_INT8',
    'ENUM_INT16', 'ENUM_INT32', 'ENUM_INT64', 'ENUM_UINT8', 'ENUM_UINT16', 'ENUM_UINT32', 'ENUM_UINT64', 'STR', 'PTR',
    'STRUCT')
ATOM = ('POD', 'ARRAY', 'INLINE_ARRAY', 'BITFIELD')


class TypeLibrary:
    """Format-aware reader for decoded DL type libraries. Hidden member names have their length inferred from the
    next name offset, exactly as scripts/reference_format.layout does."""

    def __init__(self, data: bytes):
        magic, version, types, enums, members, values, aliases, defaults, strings = TL_HEADER.unpack_from(data)
        if magic != b'LTLD':
            raise ValueError('expected decoded LTLD type library')
        fixed = (TL_HEADER.size + 4 * types + 4 * enums + 36 * types + 32 * enums + 16 * values + 8 * aliases
            + defaults + strings)
        member_size = (len(data) - fixed) // members if members else 0
        if member_size not in MEMBER_FORMATS or fixed + member_size * members != len(data):
            raise ValueError('unsupported type library member format')
        self.data, self.version, self.member_size = data, version, member_size
        self.hashes_start = TL_HEADER.size
        self.desc_start = self.hashes_start + 4 * types + 4 * enums
        self.member_start = self.desc_start + 36 * types + 32 * enums
        self.index = {}
        offsets = set()
        for i in range(types):
            kind = struct.unpack_from('<I', data, self.hashes_start + 4 * i)[0]
            desc = struct.unpack_from('<9I', data, self.desc_start + 36 * i)
            offsets.add(desc[0])
            if desc[8] != 0xFFFFFFFF:
                offsets.add(desc[8])
            self.index[kind] = desc
        for i in range(members):
            for offset in struct.unpack_from('<2I', data, self.member_start + member_size * i):
                if offset != 0xFFFFFFFF:
                    offsets.add(offset)
        self.ordered = sorted(offsets)
        self.position = {offset: i for i, offset in enumerate(self.ordered)}

    def name_length(self, offset):
        i = self.position.get(offset)
        if i is None or i + 1 >= len(self.ordered):
            return None
        return self.ordered[i + 1] - offset - 1

    def layout(self, type_ref) -> dict:
        target = type_ref if isinstance(type_ref, int) else dl_hash(type_ref)
        desc = self.index.get(target)
        if desc is None:
            raise ValueError(f'type 0x{target:08X} absent')
        _, _, _, size64, _, _, count, first, _ = desc
        fmt = MEMBER_FORMATS[self.member_size]
        members = []
        for i in range(first, first + count):
            at = self.member_start + self.member_size * i
            name_offset = struct.unpack_from('<I', self.data, at)[0]
            atom, storage, array_len, type_id = struct.unpack_from('<BBHI', self.data, at + fmt['type'])
            _, member_size64, _, _, _, offset64 = struct.unpack_from('<6I', self.data, at + fmt['sizes'])
            members.append({'name': f'hidden_name_offset=0x{name_offset:x}, inferred_length={self.name_length(name_offset)}',
                'offset64': offset64, 'size64': member_size64, 'atom': ATOM[atom], 'storage': STORAGE[storage],
                'type_hash': type_id, 'array_or_bits': array_len})
        return {'type_name': type_ref, 'type_hash': target, 'size64': size64, 'members': members}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def member_signature(member: dict) -> dict:
    match = NAME_LENGTH.search(str(member['name']))
    length = match.group(1) if match else str(len(member['name']))
    return {'offset': member['offset64'], 'size': member['size64'], 'storage': member['storage'], 'atom': member['atom'],
        'count': member['array_or_bits'], 'nameLength': None if length == 'None' else int(length),
        'typeHash': member.get('type_hash') or 0}


class Layout:
    """Members of one native record type, as (offset, size, storage, atom, count, hidden-name length)."""

    def __init__(self, name: str, size: int, members: list[dict], type_hash: int | None = None):
        self.name, self.size, self.members, self.type_hash = name, size, members, type_hash

    def member_at(self, offset: int) -> dict | None:
        for member in self.members:
            if member['offset'] <= offset < member['offset'] + max(member['size'], 1):
                return member
        return None

    def to_json(self):
        return {'name': self.name, 'typeHash': self.type_hash, 'size': self.size, 'members': self.members}


class ComponentTable:
    def __init__(self, name, type_index, record_layout, owners, records, record_size):
        self.name, self.type_index, self.layout = name, type_index, record_layout
        self.owners = owners                  # resource -> (recordIndex, indexRow)
        self.records = records                # list[bytes]
        self.record_size = record_size
        by_record = {}
        for resource, (record, _) in owners.items():
            by_record.setdefault(record, []).append(resource)
        self.owner_count = {record: len(resources) for record, resources in by_record.items()}
        self.by_record = {record: sorted(resources) for record, resources in by_record.items()}  # record -> owners

    def record(self, resource: int):
        entry = self.owners.get(resource)
        if entry is None:
            return None
        index, row = entry
        return {'recordIndex': index, 'indexRow': row, 'ownerCount': self.owner_count[index], 'bytes': self.records[index]}

    def owners_of(self, record_index: int) -> list[int]:
        return list(self.by_record.get(record_index, ()))


class SettingsTable:
    """One settings group: rows of a single record type, identified by the group's DL type hash (group indices
    can shift between builds; the type hash does not)."""

    def __init__(self, kind, settings_type, group, record_layout, entries):
        self.kind, self.settings_type, self.group, self.layout = kind, settings_type, group, record_layout
        self.rows = entries                   # list of (row, recordType, bytes)
        by_type = {}
        for row, record_type, raw in entries:
            by_type.setdefault(record_type, []).append(row)
        self.by_type = by_type

    def row_for_type(self, record_type: int):
        rows_ = self.by_type.get(record_type, [])
        return [(row, self.rows[row][2]) for row in rows_]


class SettingsKind(SettingsTable):
    """All groups of one settings file. Behaves as its primary group (the group with the most rows, which is the
    group native links point into) and exposes the others through `groups` / `group_by_type`."""

    def __init__(self, kind, tables: list[SettingsTable]):
        primary = max(tables, key=lambda table: len(table.rows))
        super().__init__(kind, primary.settings_type, primary.group, primary.layout, primary.rows)
        self.groups = {table.group: table for table in tables}

    def group_by_type(self, settings_type: int):
        return next((table for table in self.groups.values() if table.settings_type == settings_type), None)


class BuildView:
    def __init__(self):
        self.build = {}
        self.sources = []
        self.entity_rows = {}
        self.components = {}
        self.settings = {}
        self.deltas = None
        self.delta_component_index = {}
        self.stratagems = None
        self.paths = {}
        self.cache = None
        self.library = None
        self._layouts = {}

    # -- lookups ---------------------------------------------------------------------------------
    def component(self, name):
        return self.components.get(name)

    def record(self, name, resource):
        table = self.components.get(name)
        return None if table is None else table.record(resource)

    def settings_table(self, kind):
        return self.settings.get(kind)

    def layout(self, type_hash: int) -> Layout | None:
        """A nested record layout (struct members) from this build's own type library."""
        if type_hash not in self._layouts:
            try:
                self._layouts[type_hash] = _record_layout(self.library, type_hash)
            except (ValueError, TypeError):
                self._layouts[type_hash] = None
        return self._layouts[type_hash]

    def resource_components(self):
        """resource -> sorted component names it owns (built once)."""
        if not hasattr(self, '_resource_components'):
            owned = {}
            for name, table in self.components.items():
                for resource in table.owners:
                    owned.setdefault(resource, []).append(name)
            self._resource_components = {resource: sorted(names) for resource, names in owned.items()}
        return self._resource_components

    def summary(self):
        return {'build': self.build, 'sources': self.sources, 'entities': len(self.entity_rows),
            'components': {name: {'records': len(table.records), 'owners': len(table.owners),
                'recordSize': table.record_size} for name, table in sorted(self.components.items())},
            'settings': {kind: {str(index): len(group.rows) for index, group in sorted(table.groups.items())}
                for kind, table in sorted(self.settings.items())},
            'entityDeltas': None if self.deltas is None else len(self.deltas),
            'stratagems': None if self.stratagems is None else len(self.stratagems), 'cache': self.cache}


def _record_layout(typelib, type_ref) -> Layout:
    desc = typelib.layout(type_ref)
    return Layout(desc['type_name'] if isinstance(desc['type_name'], str) else hex(desc['type_hash']), desc['size64'],
        [member_signature(m) for m in desc['members']], desc['type_hash'])


def parse_entities(view: BuildView, entities: bytes, typelib: bytes):
    _, body, _, _, _ = find_component(entities, 'EntitySettingsHashmap')
    hashmap = typelib.layout('EntitySettingsHashmap')
    rows_member = hashmap['members'][0]
    stride = rows_member['size64'] // max(rows_member['array_or_bits'], 1)
    for row in range(rows_member['array_or_bits']):
        resource = struct.unpack_from('<Q', body, rows_member['offset64'] + row * stride)[0]
        if resource:
            view.entity_rows[resource] = row
    for name in COMPONENTS:
        try:
            _, body, _, _, offset = find_component(entities, name)
        except ValueError:
            continue                                      # component type absent in this build
        outer = typelib.layout(name)
        # LoadoutEntryComponentData carries a third, parallel per-record array after its records.
        index, records = outer['members'][:2]
        record_layout = _record_layout(typelib, records['type_hash'])
        record_size = records['size64'] // max(records['array_or_bits'], 1)
        owners = {}
        for row in range(index['array_or_bits']):
            resource, record, _ = struct.unpack_from('<QII', body, index['offset64'] + row * 16)
            if resource:
                owners[resource] = (record, row)
        blob = [body[records['offset64'] + i * record_size:records['offset64'] + (i + 1) * record_size]
            for i in range(records['array_or_bits'])]
        type_index = struct.unpack_from('<I', entities, offset - 4)[0]
        view.components[name] = ComponentTable(name, type_index, record_layout, owners, blob, record_size)
        view.delta_component_index[type_index] = name


def parse_settings(view: BuildView, kind: str, raw: bytes, typelib: bytes):
    tables = []
    for group in groups(raw):
        try:
            outer = typelib.layout(group['type'])
        except ValueError:
            continue
        arrays = [m for m in outer['members'] if m['atom'] == 'ARRAY' and m['storage'] == 'STRUCT']
        if len(arrays) != 1:
            continue
        record_layout = _record_layout(typelib, arrays[0]['type_hash'])
        entries = [(row, struct.unpack_from('<I', data, 0)[0], data)
            for row, _, data in rows(raw, group, record_layout.size)]
        tables.append(SettingsTable(kind, group['type'], group['group'], record_layout, entries))
    if tables:
        view.settings[kind] = SettingsKind(kind, tables)


def parse_deltas(view: BuildView, raw: bytes):
    import research_magazine_attachments as attachments  # noqa: E402  (shared decoder)
    view.deltas, _ = attachments.entity_deltas(raw)


def from_datalibrary(directory: Path, fingerprints: dict | None = None) -> BuildView:
    directory = Path(directory)
    view = BuildView()
    typelib = (directory / TYPELIB_FILE).read_bytes()
    entities = (directory / ENTITIES_FILE).read_bytes()
    view.build = dict(fingerprints or {}, entitiesSha256=sha(entities), typelibSha256=sha(typelib))
    view.sources.append({'kind': 'datalibrary', 'path': str(directory), 'entitiesSha256': view.build['entitiesSha256'],
        'typelibSha256': view.build['typelibSha256']})
    library = TypeLibrary(typelib)
    view.build['typelibMemberFormat'] = library.member_size
    parse_entities(view, entities, library)
    for kind, name in SETTINGS_FILES.items():
        if (directory / name).is_file():
            parse_settings(view, kind, (directory / name).read_bytes(), library)
    if (directory / DELTAS_FILE).is_file():
        parse_deltas(view, (directory / DELTAS_FILE).read_bytes())
    view.typelib, view.library = typelib, library
    return view


# -- snapshot extraction ---------------------------------------------------------------------------
def snapshot_fingerprints(path: Path) -> dict:
    from datetime import datetime, timezone
    from snapshot_image import Snapshot
    snap = Snapshot(path)
    with open(path, 'rb') as handle:
        captured = struct.unpack_from('<Q', handle.read(72), 64)[0]
    snap.handle.close()
    return {'exeSha256': snap.executable_sha256.upper(), 'gameDllSha256': snap.game_dll_sha256.upper(),
        'snapshot': Path(path).name, 'snapshotBytes': Path(path).stat().st_size,
        'capturedAt': datetime.fromtimestamp(captured, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}


def snapshot_cache_key(path: Path) -> str:
    """Header (fingerprints, capture time, region index) + size + extractor version: unique per capture."""
    with open(path, 'rb') as handle:
        preamble = handle.read(16)
        length = struct.unpack_from('<I', preamble, 12)[0]
        handle.seek(0)
        header = handle.read(length)
    return sha(header + struct.pack('<QI', Path(path).stat().st_size, EXTRACTOR_VERSION))[:24]


def _extract_snapshot(path: Path) -> dict:
    """Relied-on native tables of a snapshot whose game.dll matches a known runtime profile, located through the
    production discovery path. Returns raw table bytes plus stratagem rows."""
    import snapshot_regions
    tables, bases = {}, {}
    for key in ('entity', 'entity_deltas', 'projectile', 'damage', 'explosion', 'arc', 'beam', 'status'):
        bases[key], tables[key] = snapshot_regions.region_bytes(key, path)
    body = r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local Reader=require('hd2runtime/runtime/reader')
local Stratagem=require('hd2runtime/core/stratagem')
local json=require('hd2runtime/primary_mapper/json')
local b=require('hd2runtime/core/bytes')
local worker=coroutine.create(function()
 local reader=Reader.new(source)
 local records,owner=Stratagem.capture_all(source,reader,profile)
 local out={}
 for _,record in ipairs(records)do
  local raw=source.read(owner.base+record.offset,profile.stratagem.stride)
  out[#out+1]={id=record.id,group=record.group,row=record.row,payloads=record.payloads,package=record.package,
   kind=record.record_kind,bytes=b.hex(raw)}
 end
 source.close()
 return json.encode(out)
end)
local ok,result
repeat ok,result=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,result);return result
'''.replace('SNAPSHOT_PATH', json.dumps(str(Path(path).resolve())))
    stratagems = json.loads(snapshot_regions.run_lua(body, path))
    return {'tables': tables, 'bases': bases, 'stratagems': stratagems}


def from_snapshot(path: Path, datalibrary: Path | None = None, use_cache: bool = True) -> BuildView:
    """A snapshot view. Tables come from the snapshot when its build has a runtime profile; otherwise from the
    paired datalibrary (with the snapshot supplying fingerprints only)."""
    path = Path(path)
    fingerprints = snapshot_fingerprints(path)
    known = build_profile.known_build(fingerprints['exeSha256'], fingerprints['gameDllSha256'])
    profile = build_profile.build(known) if known else None
    if not profile or not profile.get('runtimeProfile'):
        if datalibrary is None:
            raise ValueError('snapshot build ' + fingerprints['exeSha256'][:12] + ' has no runtime profile; pass the '
                'new build\'s Filediver datalibrary (--datalibrary) for layouts and tables')
        view = from_datalibrary(datalibrary, fingerprints)
        view.sources.append({'kind': 'snapshot', 'path': str(path), 'usedFor': 'fingerprints only'})
        return view
    key = snapshot_cache_key(path)
    cache_dir = CACHE / (fingerprints['exeSha256'][:12] + '-' + fingerprints['gameDllSha256'][:12]) / key
    provenance_file = cache_dir / 'provenance.json'
    cached = False
    if use_cache and provenance_file.is_file():
        provenance = json.loads(provenance_file.read_text())
        cached = (provenance.get('key') == key and provenance.get('extractorVersion') == EXTRACTOR_VERSION
            and provenance.get('snapshot') == path.name)
    if not cached:
        extracted = _extract_snapshot(path)
        cache_dir.mkdir(parents=True, exist_ok=True)
        for name, data in extracted['tables'].items():
            (cache_dir / (name + '.bin')).write_bytes(data)
        (cache_dir / 'stratagems.json').write_text(json.dumps(extracted['stratagems']), newline='\n')
        provenance = {'key': key, 'extractorVersion': EXTRACTOR_VERSION, 'snapshot': path.name,
            'fingerprints': fingerprints, 'bases': extracted['bases'],
            'tables': {name + '.bin': sha(data) for name, data in extracted['tables'].items()}}
        provenance_file.write_text(json.dumps(provenance, indent=2), newline='\n')
    for name, digest in provenance['tables'].items():
        if sha((cache_dir / name).read_bytes()) != digest:
            raise ValueError('migration cache file changed on disk: ' + str(cache_dir / name))
    typelib_dir = datalibrary or build_profile.datalibrary(known)
    typelib = (Path(typelib_dir) / TYPELIB_FILE).read_bytes()
    if datalibrary is None and sha(typelib) != profile['datalibrary']['typelibSha256']:
        raise ValueError('pinned type library does not match the build profile')
    view = BuildView()
    entities = (cache_dir / 'entity.bin').read_bytes()
    view.build = dict(fingerprints, buildId=known, entitiesSha256=sha(entities), typelibSha256=sha(typelib))
    view.sources.append({'kind': 'snapshot', 'path': str(path), 'usedFor': 'tables, stratagem rows, fingerprints'})
    view.cache = {'used': cached, 'key': key, 'directory': str(cache_dir.relative_to(ROOT))}
    library = TypeLibrary(typelib)
    view.build['typelibMemberFormat'] = library.member_size
    parse_entities(view, entities, library)
    for kind in SETTINGS_FILES:
        raw = (cache_dir / (kind + '.bin')).read_bytes()
        parse_settings(view, kind, _settings_file(raw, provenance['bases'][kind]), library)
    status = (cache_dir / 'status.bin').read_bytes()
    try:
        parse_settings(view, 'status', _settings_file(status, provenance['bases']['status']), library)
    except ValueError:
        pass
    parse_deltas(view, _delta_file((cache_dir / 'entity_deltas.bin').read_bytes(), provenance['bases']['entity_deltas']))
    view.stratagems = {row['id']: row for row in json.loads((cache_dir / 'stratagems.json').read_text())}
    view.typelib, view.library = typelib, library
    return view


def _settings_file(region: bytes, base: int) -> bytes:
    """A live settings allocation laid out as its decoded file: the group count, then the groups, with each group's
    patched (absolute) record-array pointer rebased to the file's root-relative offset."""
    data = bytearray(region)
    count = struct.unpack_from('<I', data, 0)[0]
    at = 4
    for _ in range(count):
        magic, version, _, size, _, _ = struct.unpack_from('<4s5I', data, at)
        if magic != b'LDLD':
            raise ValueError('settings allocation is not group framed')
        root = at + 24
        pointer = struct.unpack_from('<Q', data, root)[0]
        if pointer >= base:
            struct.pack_into('<Q', data, root, pointer - (base + root))
        at = root + size
    return bytes(data[:at])


def _delta_file(region: bytes, base: int) -> bytes:
    """The live entity-delta allocation with its five patched array pointers rebased to root-relative offsets."""
    data = bytearray(region)
    root = 28
    for index in range(0, 10, 2):
        pointer = struct.unpack_from('<Q', data, root + 8 * index)[0]
        if pointer >= base:
            struct.pack_into('<Q', data, root + 8 * index, pointer - (base + root))
    return bytes(data)


def attach_paths(view: BuildView, datalibrary_root: Path | None = None):
    """Resource path names (hashes.txt), used only as supporting evidence in reports."""
    hashes = (datalibrary_root or build_profile.FILEDIVER) / 'hashes/hashes.txt'
    if not hashes.is_file():
        return
    from research_entity_authoring import Native  # reuse the stingray resource hash
    probe = Native.__new__(Native)
    import importlib.util
    spec = importlib.util.spec_from_file_location('probe_components_migration',
        build_profile.ROOT.parent / 'StrongerOrbitalLaser/scripts/research/probe_components.py')
    if spec is None or not Path(spec.origin).is_file():
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wanted = set(view.entity_rows)
    for line in hashes.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = line.strip()
        if line and not line.startswith('//'):
            value = module.resource_hash(line)
            if value in wanted:
                view.paths[value] = line
