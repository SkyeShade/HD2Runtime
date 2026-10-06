"""Runtime-owned custom images (docs/custom-images.md): how a mod's own icon texture reaches the game, and how the
Runtime proves it is loaded before a stratagem's icon names it. Read-only.

Proves on build F5FEE03DCFDB, from the helldivers2.exe and game.dll images, the seven retained snapshots and the
game's own archives:

1. The format. The stratagem icon textures (packages 6a3eecfddce28fe8 and others) are 256 x 256 BC1
   (DXGI_FORMAT_BC1_UNORM) textures with all 9 mip levels. The main part is 340 bytes: a 0xC0-byte header whose first
   word is the icon class (0xFCE7DA44) and whose third is 0xFFFFFFFF (no streamed mips), then "DDS ", the 124-byte DDS
   header and the 20-byte DX10 extension; the 43704-byte mip chain is the GPU part. scripts/hd2_image.py writes this
   main part byte for byte (the Orbital 120mm HE Barrage's icon texture is the reference).
2. The archive. An archive lists its types (sorted by hash) and its entries (sorted by type, then name); main parts are
   16-byte aligned from the first 256-byte boundary after the table, GPU parts 64-byte aligned in .gpu_resources, and
   every entry carries the running sums of the 256-byte-rounded part sizes before it, the header their totals.
   scripts/hd2_archive.py make_resource_archive reproduces the tables of vanilla archives (all fields but the
   streamed parts, which mod images do not use).
3. Residency. A mod archive is a patch of the boot package (9ba626afa44a3aa3). Each installed patch is one part of the
   boot package, loaded at startup with it, and the boot package is never unloaded: in every snapshot (ship, mission,
   mission end) every resource of every boot part is in its type's name map, including the Runtime's own patch.
4. The lookup. The game resolves a texture name through the resource manager (application global +0x3F8): the type
   map at +0x2E8 (entries +0x2F0, bucket count +0x304, 0xD0-byte records, next +0xC8, -2 empty, 0x7FFFFFFF end), then
   the type record's name map (entries +0x28, count +0x38, bucket count +0x3C; 24-byte entries: name, slot +8, next
   +0x10), the bucket being the name's upper 32 bits modulo the bucket count. A name whose slot is 0xFAFEF0F1 is not
   present. A missing name falls back to core/fallback_resources/missing_texture (a placeholder, never a crash).
5. The icon. An image widget first looks the icon hash up among the atlas sprites; any other hash is bound as a
   texture name through that lookup. The vanilla stratagem icons are atlas sprites (their standalone textures are
   not loaded in game), so a custom icon is a standalone texture.

Output: research/image-resources-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import hd2_archive  # noqa: E402
import hd2_game_data  # noqa: E402
import hd2_image  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/image-resources-F5FEE03DCFDB.json'
TEXTURE, LUA = hd2_image.TEXTURE_TYPE, hd2_archive.LUA_TYPE
APPLICATION, MANAGER = 0x1A101C8, 0x3F8
BOOT, ICONS = 0x9BA626AFA44A3AA3, '6a3eecfddce28fe8'
ICON_120MM = 0x9C9B3DCE316F1256
MISSING_TEXTURE = 0x89F7B44D92D2285E
ABSENT = 0xFAFEF0F1
# The proof's development icon (proof/CustomStratagemP0Proof/images): absent from every snapshot (never installed then).
PROOF_IMAGE = ('mods/skyeshade/hd2runtime_custom_stratagem_p0_proof', 'orbital_gas_barrage_icon')

EXE = {
    'bind': [
        (0x30F241, 'movabs rax, 0xcd4238c6a0c69e32', None, 'texture bind: the texture resource type'),
        (0x30F267, 'mov rax, qword ptr [rip + {rip}]', APPLICATION, 'texture bind: the application global'),
        (0x30F282, 'mov rcx, qword ptr [rax + 0x3f8]', None, 'application +0x3F8: the resource manager'),
        (0x30F289, 'call 0x5f2290', None, 'resource lookup by type and name (with fallback)'),
    ],
    'typeMap': [
        (0x5F2313, 'lea rcx, [r15 + 0x2e8]', None, 'resource manager +0x2E8: the type map'),
        (0x5F231A, 'call 0x5fe1d0', None, 'type map lookup'),
        (0x5FE1D0, 'cmp dword ptr [rcx + 0x18], 0', None, 'type map +0x18: count'),
        (0x5FE1DB, 'mov r8, qword ptr [rcx + 8]', None, 'type map +8: records'),
        (0x5FE1E2, 'shr rax, 0x20', None, 'bucket from the upper 32 bits of the type'),
        (0x5FE1E6, 'div dword ptr [rcx + 0x1c]', None, 'type map +0x1C: bucket count'),
        (0x5FE1EB, 'imul rcx, rax, 0xd0', None, 'type records are 0xD0 bytes'),
        (0x5FE1F2, 'cmp dword ptr [rcx + r8 + 0xc8], -2', None, 'record +0xC8 == -2: empty bucket'),
        (0x5FE1FD, 'cmp edx, 0x7fffffff', None, 'chain end'),
        (0x5FE219, 'cmp r9, qword ptr [rcx + r8]', None, 'record +0: the type'),
        (0x5FE21F, 'mov edx, dword ptr [rcx + r8 + 0xc8]', None, 'record +0xC8: next'),
        (0x5F23A2, 'lea rcx, [r15 + 0x2e8]', None, 'the type map again'),
        (0x5F23B8, 'imul rbp, r10, 0xd0', None, 'the type record ...'),
        (0x5F23BF, 'add rbp, qword ptr [r15 + 0x2f0]', None, '... from the records (+0x2F0)'),
    ],
    'nameMap': [
        (0x5F23DF, 'cmp dword ptr [rbp + 0x38], esi', None, 'type record +0x38: name count'),
        (0x5F23E4, 'mov r9, qword ptr [rbp + 0x28]', None, 'type record +0x28: name entries'),
        (0x5F23ED, 'shr rax, 0x20', None, 'bucket from the upper 32 bits of the name'),
        (0x5F23F1, 'div dword ptr [rbp + 0x3c]', None, 'type record +0x3C: bucket count'),
        (0x5F23F4, 'lea rcx, [rdx + rdx*2]', None, 'name entries are 24 bytes'),
        (0x5F23F8, 'cmp dword ptr [r9 + rcx*8 + 0x10], -2', None, 'entry +0x10 == -2: empty bucket'),
        (0x5F2400, 'cmp edx, 0x7fffffff', None, 'chain end'),
        (0x5F2416, 'cmp rbx, qword ptr [r9 + rcx*8]', None, 'entry +0: the name'),
        (0x5F241C, 'mov edx, dword ptr [r9 + rcx*8 + 0x10]', None, 'entry +0x10: next'),
        (0x5F242E, 'lea r9, [rbp + 0x20]', None, 'the name map (type record +0x20)'),
        (0x5F24C2, 'mov rax, qword ptr [r9 + 8]', None, 'its entries'),
        (0x5F24C6, 'mov ecx, dword ptr [rax + rcx*8 + 8]', None, 'entry +8: the resource slot'),
        (0x5F24CA, 'mov rax, qword ptr [rbp + 0x10]', None, 'type record +0x10: the resources'),
        (0x5F24CE, 'lea rdx, [rcx + rcx*4]', None, 'resource records are 0xA0 bytes ...'),
        (0x5F24D2, 'shl rdx, 5', None, '... (slot x 5 x 32)'),
        (0x5F24D6, 'mov rbp, qword ptr [rdx + rax]', None, 'record +0: the resource'),
        (0x5F32E6, 'cmp dword ptr [rax + rcx*8 + 8], 0xfafef0f1', None,
            'has-resource: a name whose slot is 0xFAFEF0F1 is not present'),
    ],
}
GAME = [
    (0x14501DE, 'mov rax, qword ptr [rcx + 0x348]', None, 'image widget: the atlas sprite lookup of the icon hash'),
    (0x14501E8, 'call rax', None, 'atlas sprite lookup'),
    (0x1450205, 'xor r9d, r9d', None, 'not an atlas sprite ...'),
    (0x1450208, 'mov r8, rbx', None, '... the icon hash is the texture name'),
    (0x145020B, 'call 0x1449a70', None, 'bind the texture'),
]


def resolve(mem, chain_head, buckets, stride, next_offset, key, wanted):
    """The slot of `wanted` in an in-array chained map, or None."""
    index = (wanted >> 32) % buckets
    if mem.u32(chain_head + index * stride + next_offset) == 0xFFFFFFFE:
        return None
    for _ in range(1 << 20):
        if mem.u64(chain_head + index * stride + key) == wanted:
            return index
        index = mem.u32(chain_head + index * stride + next_offset)
        if index == 0x7FFFFFFF:
            return None
    raise ValueError('chain does not end')


class Manager:
    def __init__(self, mem):
        self.mem = mem
        self.application = mem.ptr(mem.exe + APPLICATION)
        self.rm = mem.ptr(self.application + MANAGER)
        self.records, self.count, self.buckets = mem.ptr(self.rm + 0x2F0), mem.u32(self.rm + 0x300), mem.u32(self.rm + 0x304)
        self.end = mem.u32(self.rm + 0x2E8)

    def record(self, kind):
        index = resolve(self.mem, self.records, self.buckets, 0xD0, 0xC8, 0, kind)
        return None if index is None else self.records + index * 0xD0

    def lookup(self, kind, name):
        """'present' / 'absent' / 'tombstone' and the resource pointer, exactly as the game's lookup reads it."""
        record = self.record(kind)
        mem = self.mem
        if record is None or not mem.u32(record + 0x38):
            return 'absent', None
        index = resolve(mem, mem.ptr(record + 0x28), mem.u32(record + 0x3C), 24, 0x10, 0, name)
        if index is None:
            return 'absent', None
        slot = mem.u32(mem.ptr(record + 0x28) + index * 24 + 8)
        if slot == ABSENT:
            return 'tombstone', None
        return 'present', mem.ptr(mem.ptr(record + 0x10) + slot * 0xA0)

    def names(self, kind):
        record = self.record(kind)
        mem, out = self.mem, set()
        entries, end = mem.ptr(record + 0x28), mem.u32(record + 0x20)
        raw = mem.read(entries, 24 * end)
        for i in range(end):
            key, slot, _, nxt = struct.unpack_from('<QIIi', raw, 24 * i)
            if nxt != -2 and key and slot != ABSENT:
                out.add(key)
        return out


def boot_parts(mem):
    """Each boot package part: its resources by type (package manager list; evidence only)."""
    manager = mem.ptr(mem.ptr(mem.ptr(mem.exe + 0x1A10238) + 0x400) + 0x208)
    packages = mem.ptr(manager + 0x88)
    for i in range(mem.u32(manager + 0x80)):
        package = mem.ptr(packages + 8 * i)
        if mem.u64(package + 0x10) != BOOT:
            continue
        parts = []
        for k in range(mem.u32(package + 0x18)):
            part = mem.ptr(mem.ptr(package + 0x20) + 8 * k)
            count = mem.u32(part + 0x30)
            raw = mem.read(mem.ptr(part + 0x38), 16 * count)
            parts.append({'state': mem.u32(part + 0x1C),
                'resources': [struct.unpack_from('<QQ', raw, 16 * j) for j in range(count)]})
        return parts
    raise ValueError('boot package not in the package list')


def observe(name, runtime_names, proof_hash):
    mem = base.Mem(name)
    rm = Manager(mem)
    if not rm.records or not 0 < rm.count <= rm.buckets <= rm.end <= 4096:
        raise ValueError('resource manager type map shape in %s' % name)
    textures, lua = rm.names(TEXTURE), rm.names(LUA)
    parts = []
    for part in boot_parts(mem):
        kinds = {}
        for kind, item in part['resources']:
            kinds.setdefault(kind, []).append(item)
        tex, scripts = kinds.get(TEXTURE, []), kinds.get(LUA, [])
        parts.append({'state': part['state'], 'resources': len(part['resources']),
            'textures': len(tex), 'texturesPresent': sum(1 for n in tex if n in textures),
            'lua': len(scripts), 'luaPresent': sum(1 for n in scripts if n in lua),
            'runtimeLua': sum(1 for n in scripts if n in runtime_names)})
    checks = {'missingTexture': rm.lookup(TEXTURE, MISSING_TEXTURE)[0],
        'icon120mmStandalone': rm.lookup(TEXTURE, ICON_120MM)[0],
        'proofImage': rm.lookup(TEXTURE, proof_hash)[0]}
    atlas = mem.ptr(rm.rm + 0x2A0)
    sprite = resolve(mem, atlas, mem.u32(rm.rm + 0x2B4), 24, 0x10, 0, proof_hash) if atlas else None
    result = {'snapshot': name, 'typeMap': {'types': rm.count, 'buckets': rm.buckets, 'capacity': rm.end},
        'texturesPresent': len(textures), 'luaPresent': len(lua), 'bootParts': parts, 'lookups': checks,
        'proofImageAtlasSprite': sprite is not None}
    mem.close()
    return result


def archive_layout(data, archive):
    """Rebuild a vanilla archive's table with make_resource_archive from its own part sizes; differing fields."""
    head = data.item_bytes(archive, 0, 72)
    types, files = struct.unpack_from('<II', head, 4)
    table = data.item_bytes(archive, 0, 72 + 32 * types + 80 * files)
    start = 72 + 32 * types
    rows = [struct.unpack_from('<7Q6I', table, start + 80 * i) for i in range(files)]
    rebuilt, _ = hd2_archive.make_resource_archive({(r[1], r[0]): (bytes(r[7]), bytes(r[9])) for r in rows})
    differences = []
    if rebuilt[0x20:0x30] != table[0x20:0x30] or rebuilt[:12] != table[:12]:
        differences.append('header')
    for i in range(types):
        if rebuilt[72 + 32 * i:104 + 32 * i] != table[72 + 32 * i:104 + 32 * i]:
            differences.append('type %d' % i)
    for i, row in enumerate(rows):
        mine = struct.unpack_from('<7Q6I', rebuilt, start + 80 * i)
        # Stream parts (offset 3, size 8) are not written for mod images; the trailing index (12) is reported apart:
        # some vanilla archives skip indices (a resource removed later), the writer numbers entries in order.
        if [v for k, v in enumerate(mine) if k not in (3, 8, 12)] != [v for k, v in enumerate(row) if k not in (3, 8, 12)]:
            differences.append('entry %d' % i)
    gaps = sum(1 for i, row in enumerate(rows) if row[12] != i)
    return {'archive': archive, 'types': types, 'entries': files,
        'streamedEntries': sum(1 for r in rows if r[8]), 'differences': differences,
        'indicesNotInOrder': gaps, 'ascendingIndices': all(rows[i][12] < rows[i + 1][12] for i in range(files - 1))}


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA or snap.executable_sha256.upper() != base.PROFILE_EXE_SHA:
        raise ValueError('snapshot fingerprints differ from the pinned profile')
    game_base, game_data = snap.module_image('game.dll')
    exe_name = [k for k in snap.modules if k.endswith('.exe')][0]
    exe_base, exe_data = snap.module_image(exe_name)
    snap.close()
    exe, game = base.Image(exe_data, exe_base, base.EXE_TEXT), base.Image(game_data, game_base, base.TEXT)
    exe_pins = {group: [exe.prove(*row) for row in rows] for group, rows in EXE.items()}
    game_pins = [game.prove(*row) for row in GAME]
    flat = [p for rows in exe_pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, game_pins, flat) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    runtime_names = {hd2_archive.resource_hash('hd2runtime/' + path.relative_to(ROOT).with_suffix('').as_posix())
        for folder in ('api', 'core', 'domains', 'runtime', 'primary_mapper') for path in (ROOT / folder).rglob('*.lua')}
    proof_name = hd2_image.image_name(*PROOF_IMAGE)
    proof_hash = hd2_archive.resource_hash(proof_name)
    snapshots = [observe(name, runtime_names, proof_hash) for name in SNAPSHOTS]
    for item in snapshots:
        if item['lookups'] != {'missingTexture': 'present', 'icon120mmStandalone': 'absent', 'proofImage': 'absent'}:
            raise ValueError('unexpected lookups in %s: %r' % (item['snapshot'], item['lookups']))
        if item['proofImageAtlasSprite']:
            raise ValueError('the proof image hash is an atlas sprite')
        for part in item['bootParts']:
            if part['state'] != 4 or part['texturesPresent'] != part['textures'] or part['luaPresent'] != part['lua']:
                raise ValueError('a boot package part is not fully present in %s: %r' % (item['snapshot'], part))
        if not any(part['runtimeLua'] for part in item['bootParts']):
            raise ValueError("the Runtime's own patch is not a fully present boot part in %s" % item['snapshot'])

    data = hd2_game_data.Data()
    head = data.item_bytes(ICONS, 0, 72)
    types, files = struct.unpack_from('<II', head, 4)
    table = data.item_bytes(ICONS, 0, 72 + 32 * types + 80 * files)
    rows = [struct.unpack_from('<7Q6I', table, 72 + 32 * types + 80 * i) for i in range(files)]
    icon = next(r for r in rows if r[0] == ICON_120MM and r[1] == TEXTURE)
    main = data.read(ICONS, (icon[2], icon[7]))
    if main != hd2_image.texture_main(hd2_image.ICON_SIZE, hd2_image.ICON_SIZE, hd2_image.ICON_MIPS):
        raise ValueError("hd2_image.texture_main differs from the 120mm icon texture's main part")
    gpu = data.read(ICONS, (icon[4], icon[9]), '.gpu_resources')
    expected_gpu = sum(max(1, (hd2_image.ICON_SIZE >> level) // 4) ** 2 * 8 for level in range(hd2_image.ICON_MIPS))
    if len(gpu) != expected_gpu or icon[8]:
        raise ValueError('the 120mm icon texture is not a full unstreamed BC1 chain')
    icon_class = 0
    for r in rows:
        if r[1] == TEXTURE and r[7] == 340 and r[8] == 0 and r[9] == expected_gpu:
            icon_class += data.read(ICONS, (r[2], r[7])) == main
    layouts = [archive_layout(data, ICONS), archive_layout(data, '9ba626afa44a3aa3')]
    if any(layout['differences'] for layout in layouts):
        raise ValueError('make_resource_archive differs from a vanilla table: %r' % layouts)
    collisions = sorted({hex(t) for archive, name, t, *_ in data.tables() if name == proof_hash})
    if collisions:
        raise ValueError('the proof image name collides with a game resource: %r' % collisions)

    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    if base.PROFILE_EXE_SHA not in profile:
        raise ValueError('schemas/current.lua is another build')
    result = {'build': 'F5FEE03DCFDB', 'exe': {'sha256': base.PROFILE_EXE_SHA}, 'gameDll': {'sha256': base.PROFILE_DLL_SHA},
        'writes': 0, 'protectionChanges': 0,
        'pins': {'exe': exe_pins, 'game': game_pins}, 'pinnedBytesMismatchPerSnapshot': relocation,
        'manager': {'applicationGlobal': APPLICATION, 'resourceManager': MANAGER},
        'typeMap': {'capacity': 0x2E8, 'records': 0x2F0, 'count': 0x300, 'buckets': 0x304, 'stride': 0xD0,
            'next': 0xC8},
        'record': {'resources': 0x10, 'capacity': 0x20, 'entries': 0x28, 'count': 0x38, 'buckets': 0x3C,
            'resourceStride': 0xA0},
        'names': {'stride': 24, 'slot': 8, 'next': 0x10},
        'markers': {'empty': 0xFFFFFFFE, 'end': 0x7FFFFFFF, 'absent': ABSENT},
        'texture': {'type': '0x%016X' % TEXTURE, 'size': hd2_image.ICON_SIZE, 'mips': hd2_image.ICON_MIPS,
            'format': 'BC1_UNORM', 'dxgi': hd2_image.BC1_UNORM, 'iconClass': '0x%08X' % hd2_image.ICON_CLASS,
            'mainBytes': len(main), 'gpuBytes': expected_gpu,
            'reference': {'archive': ICONS, 'name': '0x%016X' % ICON_120MM, 'mainSha256': hashlib.sha256(main).hexdigest().upper(),
                'iconClassTexturesWithThisMainPart': icon_class}},
        'archiveLayout': layouts,
        'missingTexture': '0x%016X' % MISSING_TEXTURE,
        'proofImage': {'resource': PROOF_IMAGE[0], 'id': PROOF_IMAGE[1], 'name': proof_name,
            'hash': '0x%016X' % proof_hash, 'gameResourceCollisions': collisions},
        'snapshots': snapshots}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; icon-class textures', icon_class, '; snapshots', len(snapshots))


if __name__ == '__main__':
    main()
