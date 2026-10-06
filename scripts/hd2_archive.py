"""Minimal Stingray Lua archive writer adapted from Bingus tooling."""
from __future__ import annotations

import struct

ARCHIVE_NAME = "9ba626afa44a3aa3.patch_0"
LUA_TYPE = 0xA14E8DFA2CD117E2
MASK64 = (1 << 64) - 1
MIX = 0xC6A4A7935BD1E995


def resource_hash(name: str) -> int:
    data = name.encode("utf-8")
    result = len(data) * MIX & MASK64
    complete = len(data) // 8 * 8
    for (word,) in struct.iter_unpack("<Q", data[:complete]):
        word = word * MIX & MASK64
        word ^= word >> 47
        result = (result ^ (word * MIX & MASK64)) * MIX & MASK64
    if complete != len(data):
        result = (result ^ int.from_bytes(data[complete:], "little")) * MIX & MASK64
    result ^= result >> 47
    result = result * MIX & MASK64
    return result ^ (result >> 47)


def lua_resource(body: bytes) -> bytes:
    return struct.pack("<II", len(body), 2) + body


def make_archive(resources: dict[int, bytes]) -> bytes:
    if not resources:
        raise ValueError("At least one Lua resource is required")
    count = len(resources)
    data_offset = (104 + 80 * count + 15) & ~15
    archive = bytearray(data_offset)
    entries = bytearray()
    for index, (name_hash, resource) in enumerate(sorted(resources.items())):
        entries.extend(struct.pack(
            "<7Q6I", name_hash, LUA_TYPE, data_offset, 0, 0, 0, 0,
            len(resource), 0, 0, 16, 16, index,
        ))
        archive.extend(resource)
        archive.extend(b"\0" * (-len(archive) % 16))
        data_offset = len(archive)
    header = struct.pack("<III20sQQ24s", 0xF0000011, 1, count, b"", data_offset, 0, b"")
    types = struct.pack("<IIQIIII", 0, 0, LUA_TYPE, count, 0, 16, 16)
    archive[:104 + len(entries)] = header + types + entries
    return bytes(archive)


TEXTURE_TYPE = 0xCD4238C6A0C69E32


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def make_resource_archive(resources: dict[tuple[int, int], tuple[bytes, bytes]]) -> tuple[bytes, bytes]:
    """An archive of any resource types in the layout of the game's own archives: {(type hash, name hash): (main
    part, GPU part)} -> (archive, .gpu_resources). Types and entries are sorted by hash; main parts are 16-byte and
    GPU parts 64-byte aligned (an entry without a GPU part records the current GPU position); every entry carries the
    running sums of the 256-byte-rounded part sizes and the header their totals. Used for mods with images; Lua-only mods keep make_archive's layout."""
    if not resources:
        raise ValueError("At least one resource is required")
    keys = sorted(resources)
    types = sorted({kind for kind, _ in keys})
    table_end = 72 + 32 * len(types) + 80 * len(keys)
    archive, gpu, entries = bytearray(_align(table_end, 256)), bytearray(), bytearray()
    main_sum = gpu_sum = 0
    for index, (kind, name_hash) in enumerate(keys):
        main, data = resources[(kind, name_hash)]
        archive.extend(b"\0" * (_align(len(archive), 16) - len(archive)))
        gpu.extend(b"\0" * (_align(len(gpu), 64) - len(gpu)))
        entries.extend(struct.pack(
            "<7Q6I", name_hash, kind, len(archive), 0, len(gpu), main_sum, gpu_sum,
            len(main), 0, len(data), 16, 64, index,
        ))
        archive.extend(main)
        gpu.extend(data)
        main_sum += _align(len(main), 256)
        gpu_sum += _align(len(data), 256)
    header = struct.pack("<III20sQQ24s", 0xF0000011, len(types), len(keys), b"", main_sum, gpu_sum, b"")
    rows = b"".join(struct.pack("<IIQIIII", 0, 0, kind, sum(1 for k, _ in keys if k == kind), 0, 16, 64)
        for kind in types)
    archive[:table_end] = header + rows + entries
    return bytes(archive), bytes(gpu)


def read_archive(archive: bytes, gpu: bytes = b"") -> dict[tuple[int, int], tuple[bytes, bytes]]:
    """{(type hash, name hash): (main part, GPU part)} of an archive written by either writer."""
    magic, types, files = struct.unpack_from("<III", archive, 0)
    if magic != 0xF0000011:
        raise ValueError("not a resource archive")
    start, found = 72 + 32 * types, {}
    for index in range(files):
        row = struct.unpack_from("<7Q6I", archive, start + 80 * index)
        found[(row[1], row[0])] = (archive[row[2]:row[2] + row[7]], gpu[row[4]:row[4] + row[9]])
    return found
