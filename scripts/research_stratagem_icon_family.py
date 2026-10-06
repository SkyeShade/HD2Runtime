"""The complete resource family a stratagem icon value needs, and whether a mod can provide it for a custom icon
(docs/custom-images.md). Read-only, offline. Follows research/stratagem-icon-consumers-F5FEE03DCFDB.json (the 0.9.0
crash).

Proves on build F5FEE03DCFDB, from the helldivers2.exe and game.dll images, the seven retained snapshots and the game's
archives:

1. The GUI material format (the material resource type's own handlers, read from the resource manager's type handler
   table: load 0x168100, online 0x168700 -> 0x4F2F60). Main part = a 0x18-byte header {0x120, kind, body offset 0x18,
   0x7C, ..., +0x10 dependent count} and the body: +0x00 parent material name (0 = none), +0x08 the material object
   (loader fix-up), +0x18 / +0x20 pointers to the slot ids (u32[]) and slot names (u64[]) that follow at +0x70 (loader
   fix-ups), +0x28 slot count, three more counted arrays (+0x40, +0x50, +0x60), +0x68 the shader id. A GUI can only
   use kind 1 ("Material sets are not supported for GUIs."). Every vanilla icon material is kind 1, shader 0x3461FF0D,
   no parent, no dependents, one slot: id 0x3AA8B87E (the widget image property) = the icon's own name; byte for byte
   the same 160 bytes apart from that name, in the archives and, apart from the three loader fix-ups, in memory.
2. How a slot name becomes pixels. A material instance (0x4F2DD0) resolves each slot name as a TEXTURE by name (the
   generic lookup, with the missing_texture fallback). A widget that sets a material by name (0x144F800, 850 callers;
   eight widget-kind handlers) resolves the material through the GUI material cache (GUI API +0x230 -> 0x264620: no
   fallback, null when absent) and clones it (GUI API +0x240: no null check). Two handlers (0x143F0B0, 0x143FA20) then
   ask whether a slot name of that material is an atlas sprite (GUI API +0x350): yes -> the atlas page with the
   sprite's UV rect; no -> the full rect (0,0)-(1,1) and the material's own slot texture (GUI API +0x28/+0xC8) bound
   by name (0x30F1B0: atlas sprite redirect, else the texture by name, else missing_texture). The other six use the
   clone's slot texture. Image widgets (0x1450160) ask for an atlas sprite of the name (GUI API +0x348): yes -> atlas;
   no -> the full rect and the texture by name (0x30F1B0).
3. So for a value N: a GUI material named N is REQUIRED (no fallback on the material path); a texture named N gives
   the pixels when N is no atlas sprite; an atlas sprite named N is OPTIONAL (every path that asks for one handles its
   absence). A vanilla icon is material + sprite (its standalone texture is never loaded); a custom icon can be
   material + texture, both under the mod's own name, both loaded with the mod's archive at startup like the boot
   package's own 28 materials and 23 textures.
4. The family a mod can ship: the texture (scripts/hd2_image.py, the vanilla icon texture layout) and a material that
   is the vanilla icon material with the slot name N (scripts/hd2_image.py icon_material). make_resource_archive
   reproduces the vanilla icon-material package's archive table, materials included.

Output: research/stratagem-icon-family-F5FEE03DCFDB.json.
"""
from __future__ import annotations

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
import research_image_resources as images  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402
from research_stratagem_icon_consumers import READERS  # noqa: E402

OUTPUT = ROOT / 'research/stratagem-icon-family-F5FEE03DCFDB.json'
CALLDOWN = ROOT / 'research/stratagem-calldown-F5FEE03DCFDB.json'
MATERIAL = hd2_image.MATERIAL_TYPE
ICON_MATERIALS = '007e093ca718ca1a'
PROOF_IMAGE = ('mods/skyeshade/hd2runtime_custom_stratagem_p0_proof', 'orbital_gas_barrage_icon')
HANDLER_TABLE = {'texture': (0x4D6310,), 'material': (0x168100, 0x168700), 'texture_atlas': (0x4C0FA0, 0x4C1010)}

EXE = {
    'materialLoader': [
        (0x168161, 'cmp dword ptr [rdx + 4], ebp', None, 'header +4: the kind (0 = material set, else one material)'),
        (0x168213, 'mov edx, dword ptr [rbx + 0x28]', None, 'body +0x28: slot count'),
        (0x16821F, 'lea rax, [rbx + 0x70]', None, 'the slot ids follow at body +0x70 ...'),
        (0x16822A, 'mov qword ptr [rbx + 0x18], rax', None, '... body +0x18 = pointer to them (fix-up)'),
        (0x168236, 'mov qword ptr [rbx + 0x20], rax', None, 'body +0x20 = pointer to the slot names after them (fix-up)'),
        (0x1682BD, 'mov dword ptr [rcx], 0xd92a8333', None, 'the material object'),
        (0x1682C3, 'mov qword ptr [rbx + 8], rcx', None, 'body +0x08 = the object (fix-up)'),
        (0x1682CC, 'mov qword ptr [rcx + 0x38], rax', None, 'object +0x38 = the material name'),
        (0x1682D5, 'mov qword ptr [rcx + 0x10], rbx', None, 'object +0x10 = the body'),
        (0x1682D9, 'cmp dword ptr [rax + 0x10], ebp', None, 'header +0x10: dependent objects (none for icons)'),
        (0x4F2FC2, 'lea rdx, [rip + {rip}]', 0x1688168, '"Initializing material" (online)'),
        (0x4F2FF0, 'mov eax, dword ptr [rsi + 0x68]', None, 'body +0x68: the shader id ...'),
        (0x4F2FF7, 'mov dword ptr [rdi + 0x30], eax', None, '... object +0x30'),
    ],
    'materialInstance': [
        (0x4F2E33, 'cmp dword ptr [rbp + 0x28], r12d', None, 'each slot ...'),
        (0x4F2E50, 'mov rax, qword ptr [rbp + 0x20]', None, '... its name'),
        (0x4F2E54, 'mov rcx, qword ptr [rbp + 0x18]', None, '... its id'),
        (0x4F2E83, 'lea rdx, [rip + {rip}]', 0x190E050, 'resolved as a TEXTURE by name ...'),
        (0x4F2E8A, 'call 0x5f2290', None, '... with the missing_texture fallback'),
    ],
    'guiMaterial': [
        (0x2646DC, 'call 0x5f2160', None, 'GUI material by name: present as a material resource'),
        (0x2646E8, 'lea rax, [rip + {rip}]', 0x1675000, '"Material not found." -> null'),
        (0x264743, 'cmp dword ptr [rax + 4], 0', None, 'kind 0 refused ...'),
        (0x26474C, 'lea rax, [rip + {rip}]', 0x1675018, '"Material sets are not supported for GUIs."'),
        (0x341D1A, 'mov rbx, qword ptr [rdx + 0x38]', None, 'clone: material+0x38 read without a null check'),
    ],
    'spriteByName': [
        (0x3438FC, 'mov r8, qword ptr [rax + 0x3f8]', None, 'GUI API +0x348: the resource manager'),
        (0x343903, 'cmp dword ptr [r8 + 0x2b0], ebx', None, 'sprite map count (+0x2B0)'),
        (0x343915, 'div dword ptr [r8 + 0x2b4]', None, 'sprite map buckets (+0x2B4)'),
        (0x34391C, 'mov r8, qword ptr [r8 + 0x2a0]', None, 'sprite map entries (+0x2A0)'),
        (0x343966, 'mov rax, qword ptr [rcx + 8]', None, 'found: the atlas texture name'),
        (0x3439B0, 'mov dword ptr [r9 + 8], 0x3f800000', None, 'not found: the full rect'),
    ],
    'spriteOfMaterial': [
        (0x3439E3, 'movabs rax, 0xeac0b497876adedf', None, 'GUI API +0x350: the material by name'),
        (0x343A27, 'mov r11d, dword ptr [rcx + 0x28]', None, 'its slots ...'),
        (0x343A34, 'mov rdi, qword ptr [rcx + 0x20]', None, '... names, each looked up as a sprite'),
        (0x343AC6, 'mov dword ptr [rbx + 8], 0x3f800000', None, 'no sprite: the full rect, result 0'),
    ],
    'slotTextureName': [
        (0x30F902, 'mov rcx, qword ptr [rax + 0x20]', None, 'GUI API +0x28/+0xC8: the material ...'),
        (0x30F908, 'mov r9, qword ptr [rcx + 0x10]', None, '... its body'),
        (0x30F90C, 'mov r8d, dword ptr [r9 + 0x28]', None, '... slot count'),
        (0x30F936, 'mov rax, qword ptr [r9 + 0x20]', None, '... the slot name'),
    ],
    'textureByName': [
        (0x30F1D7, 'cmp dword ptr [r9 + 0x2b0], 0', None, 'GUI API +0x28/+0x78: sprite redirect map ...'),
        (0x30F1E1, 'mov r8, qword ptr [r9 + 0x2a0]', None, '... entries'),
        (0x30F238, 'mov rbx, qword ptr [rdx + 8]', None, 'a sprite: its atlas texture name'),
        (0x30F241, 'movabs rax, 0xcd4238c6a0c69e32', None, 'else the texture by name ...'),
        (0x30F289, 'call 0x5f2290', None, '... with the missing_texture fallback'),
    ],
}
GAME = {
    'materialWidgets': [
        (0x1943D94, 'mov edx, dword ptr [rcx + 8]', None, 'style descriptor kind'),
        (0x1943E4F, 'call 0x144f800', None, 'kind 2: set material by name'),
        (0x143F163, 'mov rax, qword ptr [rcx + 0x350]', None, 'handler A: sprite of the material?'),
        (0x143F16F, 'test eax, eax', None, '... no sprite:'),
        (0x143F18B, 'mov rcx, qword ptr [rdi + 0x148]', None, '... the material'),
        (0x143F1D4, 'mov rax, qword ptr [rdx + 0xc8]', None, '... its slot texture name'),
        (0x143FACB, 'mov rax, qword ptr [rcx + 0x350]', None, 'handler B: sprite of the material?'),
        (0x143FAD7, 'test eax, eax', None, '... no sprite:'),
        (0x143FAFE, 'mov rcx, qword ptr [rdi + 0x148]', None, '... the material'),
        (0x1445479, 'mov rax, qword ptr [r8 + 0x240]', None, 'handler: clone'),
        (0x143C350, 'mov rax, qword ptr [rdx + 0x240]', None, 'handler: clone'),
        (0x143E820, 'mov rax, qword ptr [rdx + 0x240]', None, 'handler: clone'),
        (0x1441AD0, 'mov rax, qword ptr [rdx + 0x240]', None, 'handler: clone'),
        (0x1443D70, 'mov rax, qword ptr [rdx + 0x240]', None, 'handler: clone'),
        (0x14467A0, 'mov rax, qword ptr [rdx + 0x240]', None, 'handler: clone'),
    ],
    'imageWidgets': [
        (0x14501DE, 'mov rax, qword ptr [rcx + 0x348]', None, 'image widget: sprite by name?'),
        (0x1450208, 'mov r8, rbx', None, 'no sprite: the name itself as the texture name'),
        (0x1449B45, 'mov rax, qword ptr [rcx + 0x28]', None, 'image property ...'),
        (0x1449B4C, 'call qword ptr [rax + 0x78]', None, '... bound by name (GUI API +0x28/+0x78)'),
    ],
    'materialSlotImages': [
        (0x17EF93A, 'mov rax, qword ptr [rcx + 0xd8]', None, 'the icon material\'s slot texture name (with fallback)'),
        (0x17EFBCF, 'mov rax, qword ptr [rcx + 0xd8]', None, 'the icon material\'s slot texture name (with fallback)'),
        (0x18277F5, 'mov rax, qword ptr [rcx + 0xd8]', None, 'the icon material\'s slot texture name (with fallback)'),
    ],
    'descriptorKind2': [
        (0x13D14EF, 'mov dword ptr [rsi + 0x40], 2', None, 'notification {name, kind 2 = material}'),
        (0xFFC71E, 'mov dword ptr [r15 + r12 + 0x18], 2', None, 'list entry {name, kind 2 = material}'),
    ],
}
CONSUMERS = {
    'material_required': {'readers': ['0x18CB541', '0x18CBE2B', '0xFFC703', '0x13D14E4'],
        'needs': 'a GUI material named N (no fallback: a missing material crashes); the pixels come from an atlas '
            'sprite N if there is one, else the material\'s slot texture'},
    'material_with_fallback': {'readers': ['0x17EF941', '0x17EFBD6', '0x18277AB'],
        'needs': 'a material named N for the right image (missing: the missing_material fallback\'s texture); its slot '
            'texture name is then bound by name'},
    'image': {'readers': ['0x1893650', '0x1922F43', '0x19242EB', '0x19B9779'],
        'needs': 'an atlas sprite N, else a texture N (missing: the missing_texture fallback)'},
    'getter': {'readers': ['0x18DCF27'], 'needs': 'none (returns the value; no static caller in game.dll)'},
}


def manager_maps(mem, rm):
    sprite = (mem.ptr(rm.rm + 0x2A0), mem.u32(rm.rm + 0x2B4))
    return sprite


def material_report(mem, rm, name, expected):
    """A resident material's bytes against the expected 160 bytes, with the loader's three fix-ups checked."""
    record = rm.record(MATERIAL)
    entries, buckets = mem.ptr(record + 0x28), mem.u32(record + 0x3C)
    index = images.resolve(mem, entries, buckets, 24, 0x10, 0, name)
    if index is None:
        return {'present': False}
    slot = mem.u32(entries + index * 24 + 8)
    resource = mem.ptr(mem.ptr(record + 0x10) + slot * 0xA0)
    data = mem.read(resource, 160)
    obj = struct.unpack_from('<Q', data, 0x20)[0]
    fixups = {0x20: obj, 0x30: resource + 0x88, 0x38: resource + 0x8C}
    masked = bytearray(data)
    for offset in fixups:
        masked[offset:offset + 8] = bytes(8)
    o = mem.read(obj, 0x48) if obj else None
    return {'present': True, 'stableBytesMatch': bytes(masked) == expected,
        'fixups': struct.unpack_from('<Q', data, 0x30)[0] == fixups[0x30] and struct.unpack_from('<Q', data, 0x38)[0] == fixups[0x38],
        'object': bool(o) and struct.unpack_from('<I', o, 0)[0] == 0xD92A8333 and struct.unpack_from('<Q', o, 0x10)[0] == resource + 0x18
            and struct.unpack_from('<I', o, 0x30)[0] == 0x3461FF0D and struct.unpack_from('<Q', o, 0x38)[0] == name}


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    exe_name = [k for k in snap.modules if k.endswith('.exe')][0]
    exe_base, exe_data = snap.module_image(exe_name)
    snap.close()
    exe, game = base.Image(exe_data, exe_base, base.EXE_TEXT), base.Image(game_data, game_base, base.TEXT)
    exe_pins = {group: [exe.prove(*row) for row in rows] for group, rows in EXE.items()}
    game_pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    for rva, text in ((0x1675000, b'Material not found.'), (0x1675018, b'Material sets are not supported for GUIs.'),
            (0x1688168, b'Initializing material')):
        if exe_data[rva:rva + len(text)] != text:
            raise ValueError('a message moved: %r' % text)
    if struct.unpack_from('<Q', exe_data, 0x190E050)[0] != hd2_image.TEXTURE_TYPE:
        raise ValueError('the material instance does not resolve slots as textures')
    flat_exe = [p for rows in exe_pins.values() for p in rows]
    flat_game = [p for rows in game_pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat_game, flat_exe) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    rows = json.loads(CALLDOWN.read_text(encoding='utf-8'))['presentation']['rows']
    icons = sorted({int(row['icon'], 16) for row in rows} - {0})
    proof_name = hd2_archive.resource_hash(hd2_image.image_name(*PROOF_IMAGE))
    handlers, snapshots = None, []
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        rm = images.Manager(mem)
        table, count = mem.ptr(rm.rm + 0x2C8), mem.u32(rm.rm + 0x2C0)
        found = {}
        for i in range(count):
            row = mem.read(table + 0x50 * i, 0x50)
            found[struct.unpack_from('<Q', row, 0)[0]] = ['0x%X' % (v - mem.exe) if mem.exe <= v < mem.exe + 0x39E8000
                else None for v in struct.unpack_from('<9Q', row, 8)]
        handlers = {'texture': found[hd2_image.TEXTURE_TYPE], 'material': found[MATERIAL],
            'texture_atlas': found[0x9199BB50B6896F02]}
        if handlers['texture'][1] != '0x4D6310' or handlers['material'][1] != '0x168100' \
                or handlers['material'][5] != '0x168700':
            raise ValueError('resource type handlers moved: %r' % handlers)
        sprites, buckets = manager_maps(mem, rm)
        report = {'snapshot': name, 'icons': len(icons), 'materialExact': 0, 'sprite': 0, 'texture': 0}
        for icon in icons:
            r = material_report(mem, rm, icon, hd2_image.icon_material(icon))
            report['materialExact'] += bool(r.get('stableBytesMatch') and r.get('fixups') and r.get('object'))
            report['sprite'] += images.resolve(mem, sprites, buckets, 24, 0x10, 0, icon) is not None
            report['texture'] += rm.lookup(hd2_image.TEXTURE_TYPE, icon)[0] == 'present'
        report['proofImage'] = {'material': rm.lookup(MATERIAL, proof_name)[0],
            'texture': rm.lookup(hd2_image.TEXTURE_TYPE, proof_name)[0],
            'sprite': images.resolve(mem, sprites, buckets, 24, 0x10, 0, proof_name) is not None}
        snapshots.append(report)
        mem.close()
    if any(r['materialExact'] != len(icons) or r['sprite'] != len(icons) or r['texture'] for r in snapshots):
        raise ValueError('a vanilla icon is not an exact icon material + sprite: %r' % snapshots)

    data = hd2_game_data.Data()
    head = data.item_bytes(ICON_MATERIALS, 0, 72)
    types, files = struct.unpack_from('<II', head, 4)
    table = data.item_bytes(ICON_MATERIALS, 0, 72 + 32 * types + 80 * files)
    entries = [struct.unpack_from('<7Q6I', table, 72 + 32 * types + 80 * i) for i in range(files)]
    materials = [e for e in entries if e[1] == MATERIAL and e[0] in set(icons)]
    sample = materials[0]
    archive_entry = {'type': '0x%016X' % MATERIAL, 'mainBytes': sample[7], 'streamBytes': sample[8], 'gpuBytes': sample[9],
        'alignment': [sample[10], sample[11]]}
    if any((e[7], e[8], e[9], e[10], e[11]) != (160, 0, 0, 16, 64) for e in materials):
        raise ValueError('an icon material entry is not a 160-byte main-only resource')
    layout = images.archive_layout(data, ICON_MATERIALS)
    if layout['differences']:
        raise ValueError('make_resource_archive differs from the icon material package: %r' % layout)
    bodies = {e[0]: data.read(ICON_MATERIALS, (e[2], e[7])) for e in materials}
    mismatched = [hex(n) for n, body in bodies.items() if body != hd2_image.icon_material(n)]
    if mismatched or len(bodies) != len(icons):
        raise ValueError('hd2_image.icon_material differs from vanilla icon materials: %r' % mismatched[:5])

    # The custom family, built offline: texture + material under the mod's own name, and its archive.
    png = (ROOT / 'proof/CustomStratagemP0Proof/images/orbital_gas_barrage_icon.png').read_bytes()
    family = hd2_image.icon_family(png, proof_name)
    archive, gpu = hd2_archive.make_resource_archive({(kind, proof_name): parts for kind, parts in family.items()})
    back = hd2_archive.read_archive(archive, gpu)
    collisions = sorted({'%s:0x%016X' % (archive_name, t) for archive_name, n, t, *_ in data.tables() if n == proof_name})
    other = hd2_archive.resource_hash(hd2_image.image_name('mods/someone/other_mod', PROOF_IMAGE[1]))

    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0,
        'pins': {'exe': exe_pins, 'game': game_pins}, 'pinnedBytesMismatchPerSnapshot': relocation,
        'typeHandlers': handlers,
        'materialFormat': {'header': {'size': 0x18, 'kindOffset': 4, 'bodyOffset': 0x18, 'dependentsOffset': 0x10},
            'body': {'parent': 0x00, 'object': 0x08, 'slotIds': 0x18, 'slotNames': 0x20, 'slotCount': 0x28,
                'shader': 0x68, 'arrays': 0x70},
            'loaderFixups': ['body+0x08 object', 'body+0x18 slot ids', 'body+0x20 slot names'],
            'iconMaterial': {'size': 160, 'kind': 1, 'shader': '0x3461FF0D', 'parent': 0, 'dependents': 0,
                'slots': [{'id': '0x3AA8B87E', 'name': 'the icon value itself'}]},
            'archiveEntry': archive_entry},
        'consumers': CONSUMERS,
        'family': {'materialNamedN': 'required', 'textureNamedN': 'required for a custom icon (gives the pixels when N '
                'is no atlas sprite; missing -> missing_texture)', 'atlasSpriteNamedN': 'optional (vanilla icons only)'},
        'vanilla': {'iconValues': len(icons), 'materialsInArchives': len(bodies), 'templateMatches': True,
            'snapshots': snapshots},
        'archiveLayout': layout,
        'customFamily': {'resource': PROOF_IMAGE[0], 'id': PROOF_IMAGE[1], 'name': '0x%016X' % proof_name,
            'resources': sorted('0x%016X' % kind for kind in family), 'roundTrip': back == {(k, proof_name): v
                for k, v in family.items()}, 'materialSlotName': '0x%016X' % struct.unpack_from('<Q',
                family[MATERIAL][0], 0x8C)[0], 'gameResourceCollisions': collisions,
            'otherModSameId': '0x%016X' % other, 'distinctFromOtherMod': other != proof_name},
        'conclusion': ('A custom icon is representable without native registration: the mod archive ships a texture '
            'and a GUI material named N (the vanilla icon material with its slot name N); no atlas sprite is needed. '
            'Every +0xB0 consumer resolves that family: material paths find the material and, with no sprite, bind its '
            'slot texture N; image paths bind texture N. presentation_icon still refuses custom images until a live '
            'proof shows it in game.')}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; vanilla', [(r['materialExact'], r['sprite'], r['texture'])
        for r in snapshots][:1], '; package layout', layout['differences'], '; custom round trip',
        result['customFamily']['roundTrip'], '; collisions', collisions)


if __name__ == '__main__':
    main()
