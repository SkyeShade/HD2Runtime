# Generic decoded DL readers extracted from Jar-5_buff; see docs/provenance.json.
import json
"""Small decoded entity/type helpers used by the JAR-5 ownership audit."""


from pathlib import Path
import struct

HEADER_SIZE = 28
COMPONENT_HEADER = struct.Struct('<I4sIIIB')


def dl_hash(name: str) -> int:
    value = 5381
    for char in name:
        value = (value * 33 + ord(char)) & 0xFFFFFFFF
    return (value - 5381) & 0xFFFFFFFF


def find_component(data: bytes, name: str) -> tuple[bytes, bytes, int, bool, int]:
    type_hash = dl_hash(name)
    needle = struct.pack('<I', type_hash)
    start, matches = 0, []
    while (position := data.find(needle, start)) >= 0:
        start = position + 1
        if position + HEADER_SIZE > len(data):
            continue
        prefix, magic, version, actual, size, is64 = COMPONENT_HEADER.unpack_from(data, position)
        end = position + HEADER_SIZE + size
        if prefix == actual == type_hash and magic == b'LDLD' and end <= len(data):
            matches.append((data[position:end], data[position + HEADER_SIZE:end],
                            version, bool(is64), position))
    if len(matches) != 1:
        raise ValueError(f'{name}: expected one decoded instance, got {len(matches)}')
    return matches[0]



"""Read named 64-bit layouts from a decoded HD2 DL type library."""


import struct



HEADER = struct.Struct('<4s8I')
TYPE_SIZE = 36
ENUM_SIZE = 32
MEMBER_SIZE = 72
STORAGE = ('INT8','INT16','INT32','INT64','UINT8','UINT16','UINT32','UINT64',
           'FP32','FP64','ENUM_INT8','ENUM_INT16','ENUM_INT32','ENUM_INT64',
           'ENUM_UINT8','ENUM_UINT16','ENUM_UINT32','ENUM_UINT64','STR','PTR','STRUCT')
ATOM = ('POD','ARRAY','INLINE_ARRAY','BITFIELD')


def layout(data: bytes, name: str | int) -> dict:
    if len(data) < HEADER.size:
        raise ValueError('type library shorter than header')
    magic, version, types, enums, members, enum_values, enum_aliases, defaults, strings = HEADER.unpack_from(data)
    if magic != b'LTLD':
        raise ValueError('expected decoded LTLD type library')
    hashes_start = HEADER.size
    enum_hashes_start = hashes_start + 4 * types
    desc_start = enum_hashes_start + 4 * enums
    member_start = desc_start + TYPE_SIZE * types + ENUM_SIZE * enums
    remaining_start = member_start + MEMBER_SIZE * members + 16 * enum_values + 8 * enum_aliases
    strings_start = remaining_start + defaults
    if strings_start + strings > len(data):
        raise ValueError('type library tables exceed file')
    target_hash = name if isinstance(name, int) else dl_hash(name)
    target = None
    offsets = set()
    for index in range(types):
        kind, = struct.unpack_from('<I', data, hashes_start + 4 * index)
        at = desc_start + TYPE_SIZE * index
        values = struct.unpack_from('<9I', data, at)
        offsets.add(values[0])
        if values[8] != 0xFFFFFFFF:
            offsets.add(values[8])
        if kind == target_hash:
            target = values[1:8]
    for index in range(members):
        at = member_start + MEMBER_SIZE * index
        for offset in struct.unpack_from('<2I', data, at):
            if offset != 0xFFFFFFFF:
                offsets.add(offset)
    if target is None:
        raise ValueError(f'type 0x{target_hash:08X} absent')
    flags, size32, size64, align32, align64, count, first = target
    if first + count > members:
        raise ValueError('type member range out of bounds')
    ordered = sorted(offsets)

    def member_name(offset: int) -> str:
        if strings:
            start = strings_start + offset
            if start >= strings_start + strings:
                raise ValueError('member name out of bounds')
            return data[start:data.index(0, start, strings_start + strings)].decode('utf-8','replace')
        position = ordered.index(offset)
        length = ordered[position + 1] - offset - 1 if position + 1 < len(ordered) else None
        return f'hidden_name_offset=0x{offset:x}, inferred_length={length}'

    descriptions = []
    for index in range(first, first + count):
        at = member_start + MEMBER_SIZE * index
        name_offset = struct.unpack_from('<I', data, at)[0]
        atom, storage, array_len, type_id = struct.unpack_from('<BBHI', data, at + 12)
        field_size32, field_size64, field_align32, field_align64, offset32, offset64 = \
            struct.unpack_from('<6I', data, at + 20)
        descriptions.append({
            'name': member_name(name_offset), 'name_offset': name_offset,
            'offset32': offset32, 'offset64': offset64,
            'size32': field_size32, 'size64': field_size64,
            'align32': field_align32, 'align64': field_align64,
            'atom': ATOM[atom], 'storage': STORAGE[storage],
            'type_hash': type_id, 'array_or_bits': array_len,
        })
    return {'type_name': name, 'type_hash': target_hash, 'version': version,
            'size32': size32, 'size64': size64, 'align32': align32,
            'align64': align64, 'flags': flags, 'members': descriptions}

"""Strict reader for decoded grouped DL settings files."""
import struct


def groups(data: bytes) -> list[dict]:
    if len(data) < 4:
        raise ValueError('truncated group count')
    count, = struct.unpack_from('<I', data)
    if not 1 <= count <= 1024:
        raise ValueError('invalid group count (input may be encoded)')
    at, result = 4, []
    for index in range(count):
        if at + 24 > len(data):
            raise ValueError('truncated group header')
        magic, version, kind, size, is64, reserved = struct.unpack_from('<4s5I', data, at)
        root, end = at + 24, at + 24 + size
        if magic != b'LDLD' or version != 1 or is64 != 1 or reserved or end > len(data):
            raise ValueError('invalid decoded group framing')
        result.append({'group': index, 'type': kind, 'root': root, 'end': end})
        at = end
    if at != len(data):
        raise ValueError('trailing bytes outside groups')
    return result


def rows(data: bytes, group: dict, stride: int) -> list[tuple[int, int, bytes]]:
    root, end = group['root'], group['end']
    if root + 16 > end or stride <= 0:
        raise ValueError('invalid settings root or stride')
    offset, count = struct.unpack_from('<QQ', data, root)
    start = root + offset
    if offset < 16 or count > 100000 or start + count * stride > end:
        raise ValueError('record array outside owning group')
    return [(i, start + i * stride, data[start + i * stride:start + (i + 1) * stride])
            for i in range(count)]

_BYTE_ESCAPES = ['\\%03d' % b for b in range(256)]


def lua(value):
    if isinstance(value, dict):
        return '{' + ','.join('['+lua(k)+']='+lua(v) for k, v in value.items()) + '}'
    if isinstance(value, (list, tuple)):
        return '{' + ','.join(lua(v) for v in value) + '}'
    if isinstance(value, bool): return 'true' if value else 'false'
    if value is None: return 'nil'
    if isinstance(value, (int, float)): return str(value)
    if isinstance(value, bytes):
        return '"' + ''.join(map(_BYTE_ESCAPES.__getitem__, value)) + '"'
    return json.dumps(str(value), ensure_ascii=True)
