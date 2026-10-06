"""Typed access to every component table of the pinned entity file (research only).

The entity file (generated_entities.dl_bin) is a sequence of decoded DL instances. Each component table instance is
{ComponentIndexData[capacity] index, <Record>[count] records}: an index row is {u64 resource, u32 record, u32 0}, so
several entities can share one record (shared type data). EntitySettingsHashmap maps every entity resource to its
component indices.

Everything here is derived from the pinned type library: member offsets, sizes, storage, inline-array counts,
bitfield positions and hidden-name LENGTHS (the build ships no member names). Nothing is named here; names are a
separate, reviewed step (``golib`` leads, research scripts).

Member paths are decimal byte offsets joined by dots, inline-array elements in brackets: ``160[3].8`` is byte 8 of
element 3 of the inline struct array at +160. ``Member.offset`` is always the absolute offset in the record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import functools
import hashlib
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from hd2_archive import resource_hash  # noqa: E402
from migration.build_view import TypeLibrary  # noqa: E402
from reference_format import dl_hash  # noqa: E402

FRAME = struct.Struct('<I4sIIIB')
FRAME_SIZE = 28
INDEX_ROW = struct.Struct('<QII')
FORMATS = {'INT8': 'b', 'UINT8': 'B', 'INT16': 'h', 'UINT16': 'H', 'INT32': 'i', 'UINT32': 'I', 'INT64': 'q',
    'UINT64': 'Q', 'FP32': 'f', 'FP64': 'd'}
VECTORS = {'CApiVector2': 2, 'CApiVector3': 3, 'CApiVector4': 4, 'CApiQuaternion': 4}
NAME_LENGTH = re.compile(r'inferred_length=(\d+|None)')
MAX_DEPTH = 6


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def hexid(value: int) -> str:
    return f'0x{value:016X}'


@dataclass(frozen=True)
class Member:
    """One leaf of a flattened record layout."""
    path: str
    offset: int          # absolute offset in the record
    size: int            # bytes (whole leaf; an inline scalar array is one leaf)
    storage: str         # type-library storage (FP32, ENUM_UINT32, UINT8, STRUCT for vectors, ...)
    atom: str            # POD, INLINE_ARRAY, BITFIELD, VECTOR
    count: int           # elements (inline scalar arrays, vector components); 1 otherwise
    name_length: int | None
    type_hash: int
    type_name: str | None
    parent: str | None   # path of the enclosing struct member, None at the top level
    parent_type: str | None
    bits: tuple[int, int] | None = None   # (shift, width) for BITFIELD leaves

    @property
    def kind(self) -> str:
        if self.atom == 'VECTOR':
            return 'vector'
        if self.atom == 'BITFIELD':
            return 'bits'
        storage = self.storage
        if storage.startswith('ENUM_'):
            return 'enum'
        if storage in ('FP32', 'FP64'):
            return 'float'
        if storage in ('UINT64', 'INT64'):
            return 'hash64'
        if storage in FORMATS:
            return 'int'
        return 'raw'

    def element_size(self) -> int:
        return self.size // max(self.count, 1)

    def describe(self) -> dict:
        return {'path': self.path, 'offset': self.offset, 'size': self.size, 'storage': self.storage, 'atom': self.atom,
            'count': self.count, 'nameLength': self.name_length, 'type': self.type_name, 'parent': self.parent,
            'parentType': self.parent_type, 'bits': list(self.bits) if self.bits else None, 'kind': self.kind}


def decode(member: Member, raw: bytes, offset: int = 0):
    """The member's value in ``raw`` (a whole record unless ``offset`` rebases it): a scalar, a list for inline
    arrays and vectors, or hex for anything without a scalar storage."""
    at = offset + member.offset
    data = raw[at:at + member.size]
    if len(data) != member.size:
        raise ValueError(f'member {member.path} outside the record')
    if member.atom == 'BITFIELD':
        shift, width = member.bits
        unit = int.from_bytes(data, 'little')
        return (unit >> shift) & ((1 << width) - 1)
    if member.atom == 'VECTOR':
        return list(struct.unpack('<%df' % member.count, data))
    storage = member.storage.removeprefix('ENUM_')
    fmt = FORMATS.get(storage)
    if fmt is None:
        return data.hex()
    width = struct.calcsize(fmt)
    if member.size % width:
        return data.hex()
    values = list(struct.unpack('<' + fmt * (member.size // width), data))
    return values[0] if member.count == 1 and len(values) == 1 else values


def scalars(member: Member, raw: bytes, offset: int = 0):
    """Yield (path, element member kind, value) for every scalar element of a leaf (vectors and arrays expanded)."""
    value = decode(member, raw, offset)
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield f'{member.path}[{index}]', item
    elif not isinstance(value, str):
        yield member.path, value


class Component:
    """One component table: index rows, records and the flattened record layout."""

    def __init__(self, tables: 'EntityTables', name: str, type_hash: int, body: bytes, frame_offset: int):
        self.tables, self.name, self.type_hash, self.body, self.frame_offset = tables, name, type_hash, body, frame_offset
        layout = tables.library.layout(type_hash)
        members = layout['members']
        if (len(members) < 2 or members[0]['atom'] != 'INLINE_ARRAY' or members[1]['atom'] != 'INLINE_ARRAY'
                or members[0]['type_hash'] != dl_hash('ComponentIndexData')):
            raise ValueError(f'{name}: not an index/record component table')
        index, records = members[0], members[1]
        self.capacity = index['array_or_bits']
        if index['size64'] != self.capacity * INDEX_ROW.size:
            raise ValueError(f'{name}: index stride mismatch')
        self.record_type_hash = records['type_hash']
        self.record_type = tables.type_name(self.record_type_hash)
        self.count = records['array_or_bits']
        self.record_size = records['size64'] // max(self.count, 1)
        self.records_offset = records['offset64']
        self.extra = [m for m in members[2:]]   # e.g. LoadoutEntryComponentData has a trailing per-record array
        self._rows = None

    def __repr__(self):
        return f'<Component {self.name} records={self.count} size={self.record_size}>'

    # -- ownership -------------------------------------------------------------------------------------------
    def rows(self) -> list[tuple[int, int, int]]:
        """(row, resource, record) for every occupied index row."""
        if self._rows is None:
            rows = []
            for row in range(self.capacity):
                resource, record, reserved = INDEX_ROW.unpack_from(self.body, row * INDEX_ROW.size)
                if resource:
                    if reserved:
                        raise ValueError(f'{self.name}: index row {row} reserved field is non-zero')
                    if record >= self.count:
                        raise ValueError(f'{self.name}: index row {row} selects record {record} of {self.count}')
                    rows.append((row, resource, record))
            self._rows = rows
        return self._rows

    def owners(self, record: int) -> list[int]:
        return [resource for _, resource, index in self.rows() if index == record]

    def owner_map(self) -> dict[int, list[int]]:
        result: dict[int, list[int]] = {}
        for _, resource, index in self.rows():
            result.setdefault(index, []).append(resource)
        return result

    def record_of(self, resource: int) -> int | None:
        found = [index for _, owner, index in self.rows() if owner == resource]
        if len(found) > 1:
            raise ValueError(f'{self.name}: resource {hexid(resource)} has {len(found)} rows')
        return found[0] if found else None

    # -- records ---------------------------------------------------------------------------------------------
    def raw(self, record: int) -> bytes:
        if not 0 <= record < self.count:
            raise ValueError(f'{self.name}: record {record} out of range')
        start = self.records_offset + record * self.record_size
        return self.body[start:start + self.record_size]

    def members(self) -> list[Member]:
        return self.tables.flatten(self.record_type_hash)

    def member(self, path_or_offset) -> Member:
        for item in self.members():
            if item.path == path_or_offset or item.offset == path_or_offset:
                return item
        raise KeyError(f'{self.name}: no member {path_or_offset}')

    def decode(self, record: int) -> dict[str, object]:
        raw = self.raw(record)
        return {item.path: decode(item, raw) for item in self.members()}

    def describe(self) -> dict:
        owners = self.owner_map()
        return {'component': self.name, 'recordType': self.record_type, 'recordSize': self.record_size,
            'records': self.count, 'indexCapacity': self.capacity, 'occupiedRows': len(self.rows()),
            'sharedRecords': sum(1 for v in owners.values() if len(v) > 1),
            'unownedRecords': sum(1 for index in range(self.count) if index not in owners)}


class EntityTables:
    """The pinned entity file and type library, with names from the Filediver dictionaries (leads, not proof)."""

    def __init__(self, folder: Path | None = None, verify: bool = True):
        self.folder = Path(folder) if folder else build_profile.datalibrary()
        self.entities = (self.folder / 'generated_entities.dl_bin').read_bytes()
        typelib = (self.folder / 'dl_library.dl_typelib').read_bytes()
        if verify and folder is None:
            if sha(self.entities) != build_profile.ENTITY_SHA256 or sha(typelib) != build_profile.TYPELIB_SHA256:
                raise ValueError('pinned decoded entity reference changed')
        self.typelib_bytes = typelib
        self.library = TypeLibrary(typelib)
        hashes = self.folder.parent / 'hashes'
        self.type_names = {}
        if (hashes / 'dl_type_names.txt').is_file():
            for name in (hashes / 'dl_type_names.txt').read_text(encoding='utf-8').splitlines():
                if name:
                    self.type_names.setdefault(dl_hash(name), name)
        self._paths = None
        self._thin = None
        self.frames = self._frames()
        self._components: dict[str, Component] = {}
        self._entity_rows = None

    # -- names (leads) ---------------------------------------------------------------------------------------
    def type_name(self, type_hash: int) -> str | None:
        return self.type_names.get(type_hash)

    @property
    def paths(self) -> dict[int, str]:
        if self._paths is None:
            self._paths = {}
            path = self.folder.parent / 'hashes/hashes.txt'
            if path.is_file():
                for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
                    line = line.strip()
                    if line and not line.startswith('//'):
                        self._paths.setdefault(resource_hash(line), line)
        return self._paths

    @property
    def thin(self) -> dict[int, str]:
        if self._thin is None:
            self._thin = {}
            path = self.folder.parent / 'hashes/thinhashes.txt'
            if path.is_file():
                for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
                    line = line.strip()
                    if line:
                        self._thin.setdefault(resource_hash(line) >> 32, line)
        return self._thin

    def name(self, resource: int) -> str | None:
        return self.paths.get(resource)

    def label(self, resource: int) -> str:
        path = self.name(resource)
        return path.rsplit('/', 1)[-1] if path else hexid(resource)

    # -- framing ---------------------------------------------------------------------------------------------
    def _frames(self) -> dict[int, tuple[int, int]]:
        data, frames, position = self.entities, {}, 0
        while position < len(data):
            prefix, magic, _, type_hash, size, _ = FRAME.unpack_from(data, position)
            end = position + FRAME_SIZE + size
            if magic != b'LDLD' or prefix != type_hash or end > len(data):
                raise ValueError(f'invalid decoded instance at {position}')
            if type_hash in frames:
                raise ValueError(f'duplicate instance of type 0x{type_hash:08X}')
            frames[type_hash] = (position, size)
            if end == len(data):
                break
            if data[end + 4:end + 8] == b'LDLD':
                position = end
            elif data[end + 8:end + 12] == b'LDLD':
                position = end + 4
            else:
                raise ValueError(f'cannot find the instance after {end}')
        return frames

    def component_names(self) -> list[str]:
        result = []
        for type_hash in self.frames:
            name = self.type_name(type_hash) or f'0x{type_hash:08x}'
            if name.endswith('ComponentData') or name.startswith('0x'):
                result.append(name)
        return result

    def component(self, name: str) -> Component:
        if name not in self._components:
            type_hash = int(name, 16) if name.startswith('0x') else dl_hash(name)
            if type_hash not in self.frames:
                raise KeyError(f'component table {name} absent')
            position, size = self.frames[type_hash]
            body = self.entities[position + FRAME_SIZE:position + FRAME_SIZE + size]
            self._components[name] = Component(self, name, type_hash, body, position)
        return self._components[name]

    def components(self):
        for name in self.component_names():
            try:
                yield self.component(name)
            except ValueError:
                continue

    # -- entities --------------------------------------------------------------------------------------------
    def _index_types(self) -> dict[int, int]:
        """Component index (as EntitySettings lists it) -> component table type hash, from the instance framing."""
        data, result, position = self.entities, {}, 0
        while position < len(data):
            _, _, _, _, size, _ = FRAME.unpack_from(data, position)
            end = position + FRAME_SIZE + size
            if end == len(data):
                break
            if data[end + 4:end + 8] == b'LDLD':
                position = end
            else:
                result[struct.unpack_from('<I', data, end)[0]] = struct.unpack_from('<I', data, end + 4)[0]
                position = end + 4
        return result

    def entity_rows(self) -> dict[int, list[int]]:
        """Resource -> its component indices (EntitySettingsHashmap)."""
        if self._entity_rows is None:
            position, size = self.frames[dl_hash('EntitySettingsHashmap')]
            body = self.entities[position + FRAME_SIZE:position + FRAME_SIZE + size]
            layout = self.library.layout(dl_hash('EntitySettingsHashmap'))['members']
            if len(layout) != 1 or layout[0]['atom'] != 'INLINE_ARRAY' or layout[0]['size64'] != 32 * layout[0]['array_or_bits']:
                raise ValueError('unsupported EntitySettingsHashmap layout')
            rows = {}
            for row in range(layout[0]['array_or_bits']):
                resource, offset, count = struct.unpack_from('<QQQ', body, row * 32)
                if not resource:
                    continue
                if count > 1024 or offset + 2 * count > len(body):
                    raise ValueError('entity component list out of bounds')
                if resource in rows:
                    raise ValueError(f'duplicate entity row {hexid(resource)}')
                rows[resource] = list(struct.unpack_from(f'<{count}H', body, offset))
            self._entity_rows = rows
            self._index_type = self._index_types()
        return self._entity_rows

    def resources(self) -> list[int]:
        return sorted(self.entity_rows())

    def entity(self, resource: int) -> dict[str, int]:
        """Component name -> record index for one entity (only components it actually has a row in)."""
        if isinstance(resource, str):
            resource = int(resource, 16) if resource.startswith('0x') else resource_hash(resource)
        indices = self.entity_rows().get(resource)
        if indices is None:
            raise KeyError(f'entity {hexid(resource)} absent')
        result = {}
        for index in indices:
            type_hash = self._index_type.get(index)
            if type_hash is None:
                continue
            name = self.type_name(type_hash) or f'0x{type_hash:08x}'
            try:
                record = self.component(name).record_of(resource)
            except (KeyError, ValueError):
                continue
            if record is not None:
                result[name] = record
        return result

    def find(self, pattern: str) -> list[int]:
        """Entities whose resource path matches a regular expression (case-insensitive)."""
        rx = re.compile(pattern, re.I)
        return sorted(resource for resource in self.entity_rows() if rx.search(self.name(resource) or ''))

    def with_component(self, name: str) -> list[int]:
        return sorted({resource for _, resource, _ in self.component(name).rows()})

    # -- layouts ---------------------------------------------------------------------------------------------
    @functools.lru_cache(maxsize=None)
    def flatten(self, type_hash: int) -> list[Member]:
        return self._flatten(type_hash, 0, '', None, None, 0)

    def _flatten(self, type_hash, base, prefix, parent, parent_type, depth) -> list[Member]:
        if depth > MAX_DEPTH:
            raise ValueError('nested layout exceeds depth limit')
        layout = self.library.layout(type_hash)
        out = []
        for raw in layout['members']:
            match = NAME_LENGTH.search(raw['name'])
            length = int(match.group(1)) if match and match.group(1) != 'None' else None
            type_name = self.type_name(raw['type_hash']) if raw['type_hash'] else None
            offset = base + raw['offset64']
            path = f"{prefix}{raw['offset64']}"
            atom, storage = raw['atom'], raw['storage']
            if atom == 'BITFIELD':
                bits = (raw['array_or_bits'] >> 8, raw['array_or_bits'] & 0xFF)
                out.append(Member(f'{path}:{bits[0]}', offset, raw['size64'], storage, 'BITFIELD', 1, length,
                    raw['type_hash'], type_name, parent, parent_type, bits))
                continue
            count = raw['array_or_bits'] if atom == 'INLINE_ARRAY' else 1
            if storage == 'STRUCT':
                if type_name in VECTORS and atom == 'POD':
                    out.append(Member(path, offset, raw['size64'], storage, 'VECTOR', VECTORS[type_name], length,
                        raw['type_hash'], type_name, parent, parent_type))
                    continue
                stride = raw['size64'] // max(count, 1)
                for element in range(count):
                    element_path = f'{path}[{element}]' if atom == 'INLINE_ARRAY' else path
                    out.extend(self._flatten(raw['type_hash'], offset + element * stride, element_path + '.',
                        element_path, type_name or f"0x{raw['type_hash']:08x}", depth + 1))
                continue
            out.append(Member(path, offset, raw['size64'], storage, atom, count, length, raw['type_hash'], type_name,
                parent, parent_type))
        return out

    def struct_members(self, type_ref) -> list[dict]:
        """The direct (unflattened) members of a type: offset, size, storage, atom, count, nameLength, type."""
        type_hash = type_ref if isinstance(type_ref, int) else dl_hash(type_ref)
        layout = self.library.layout(type_hash)
        result = []
        for raw in layout['members']:
            match = NAME_LENGTH.search(raw['name'])
            result.append({'offset': raw['offset64'], 'size': raw['size64'], 'storage': raw['storage'],
                'atom': raw['atom'], 'count': raw['array_or_bits'],
                'nameLength': int(match.group(1)) if match and match.group(1) != 'None' else None,
                'type': self.type_name(raw['type_hash']) if raw['type_hash'] else None,
                'typeHash': raw['type_hash']})
        return result

    def type_size(self, type_ref) -> int:
        type_hash = type_ref if isinstance(type_ref, int) else dl_hash(type_ref)
        return self.library.layout(type_hash)['size64']

    def fingerprint(self, component: str) -> str:
        """SHA-256 of the record layout signature: a layout guard for research scripts."""
        members = self.component(component).members()
        text = ';'.join(f'{m.path}:{m.size}:{m.storage}:{m.atom}:{m.count}:{m.name_length}' for m in members)
        return sha(text.encode())


@functools.lru_cache(maxsize=1)
def pinned() -> EntityTables:
    """The pinned tables for the active build (cached per process)."""
    return EntityTables()
