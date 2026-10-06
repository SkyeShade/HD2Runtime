"""What the game does with a stratagem's icon value (StratagemInfo +0xB0), and why a Runtime-owned custom image crashed
the loadout screen (CustomStratagemP0Proof 0.9.0, 2026-10-01). Read-only.

Proves on build F5FEE03DCFDB, from the game.dll and helldivers2.exe images, the seven retained snapshots and the game's
archives:

1. Every direct reader of +0xB0 (a row loaded from the StratagemInfo table game+0x37CB600, then +0xB0 read) and what it
   does with the value:
   * image: an image widget's image (0x1450160, or the GUI API +0x28/+0xD8 path): an atlas sprite of that name, else a
     texture of that name, else the engine's fallback texture;
   * material: a widget style descriptor {name = +0xB0, kind 2} (the loadout grid entries 0x18CB541 / 0x18CBE2B, and
     the same descriptor shape at 0xFFC703 and 0x13D14E4): kind 2 draws a GUI material named by the value;
   * a plain getter (0x18DCF27).
2. The material path has no fallback. The descriptor reaches 0x144F800 (set material by name) -> 0x143F210 -> 0x12EE1E0
   (the GUI's material cache; on a miss GUI API +0x230 = exe 0x341CA0 -> 0x264620, which looks the name up as a
   material resource and returns null with "Material not found.") -> 0x143F0B0, which calls 0x1449400 with that
   pointer even when it is null -> GUI API +0x240 = exe 0x341CE0 (clone a material instance), which reads
   material+0x38 without a null check.
3. Every vanilla icon value is three resources of one name: a resident GUI material, a resident atlas sprite, and (in
   the archives) a standalone texture that is not loaded in game. All 111 non-zero icon values are resident as a
   material and an atlas sprite in every snapshot.
4. The vanilla icon materials (package 007e093ca718ca1a) are one 160-byte UI material: all identical except the value
   of property 0x3AA8B87E (the widget image property) at +0x8C, which is the icon's own name.
5. The live crash (recorded from the game's minidump of 2026-10-01 23:18): access violation reading 0x38 at
   helldivers2.exe+0x341D1A, with the call chain below, while the loadout grid was rebuilt after a slot click
   (0x146ED65 -> 0x18D8710). The custom image's name hash was on that stack. A custom image provides a texture only,
   so the material lookup returned null.

Output: research/stratagem-icon-consumers-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import hd2_game_data  # noqa: E402
import research_event_state as base  # noqa: E402
import research_image_resources as images  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/stratagem-icon-consumers-F5FEE03DCFDB.json'
CALLDOWN = ROOT / 'research/stratagem-calldown-F5FEE03DCFDB.json'
MATERIAL = 0xEAC0B497876ADEDF
IMAGE_PROPERTY = 0x3AA8B87E
ICON_MATERIALS = '007e093ca718ca1a'

READERS = [
    # (rva, asm, target, role, consumer)
    (0x18CB488, 'mov r10, qword ptr [r12 + rbx*8 + 0x37cb600]', None, 'loadout grid entry: the StratagemInfo row', None),
    (0x18CB497, 'cmp qword ptr [r10 + 0xb0], rdi', None, 'loadout grid entry: an icon is set', None),
    (0x18CB533, 'mov dword ptr [rax + 8], 2', None, 'style descriptor kind 2 (material)', None),
    (0x18CB541, 'mov rax, qword ptr [r10 + 0xb0]', None, 'descriptor name = +0xB0', 'material'),
    (0x18CB590, 'call 0x18dc5d0', None, 'apply the descriptor', None),
    (0x18CBE1D, 'mov dword ptr [rax + 8], 2', None, 'loadout grid entry (variant): descriptor kind 2 (material)', None),
    (0x18CBE2B, 'mov rax, qword ptr [r10 + 0xb0]', None, 'descriptor name = +0xB0', 'material'),
    (0xFFC703, 'mov rax, qword ptr [rax + 0xb0]', None, 'a {name, kind} pair: name = +0xB0', 'material_descriptor_shape'),
    (0xFFC71E, 'mov dword ptr [r15 + r12 + 0x18], 2', None, '... kind 2', None),
    (0x13D14E4, 'mov rax, qword ptr [rdi + 0xb0]', None, 'a {name, kind} pair: name = +0xB0', 'material_descriptor_shape'),
    (0x13D14EF, 'mov dword ptr [rsi + 0x40], 2', None, '... kind 2', None),
    (0x1893650, 'mov rdx, qword ptr [rdi + 0xb0]', None, 'image widget', 'image'),
    (0x1893657, 'call 0x1450160', None, 'set image (atlas sprite, else texture)', None),
    (0x1922F43, 'mov rdx, qword ptr [rsi + 0xb0]', None, 'image widget', 'image'),
    (0x19242EB, 'mov rdx, qword ptr [rbp + 0xb0]', None, 'image widget', 'image'),
    (0x19B9779, 'mov rdx, qword ptr [rdi + 0xb0]', None, 'image widget', 'image'),
    (0x17EF941, 'mov rcx, qword ptr [r14 + 0xb0]', None, 'image via GUI API +0x28/+0xD8', 'image'),
    (0x17EFBD6, 'mov rcx, qword ptr [r15 + 0xb0]', None, 'image via GUI API +0x28/+0xD8', 'image'),
    (0x18277AB, 'mov rbx, qword ptr [rbx + 0xb0]', None, 'image via GUI API +0x28/+0xD8', 'image'),
    (0x18DCF27, 'mov rdx, qword ptr [rax + 0xb0]', None, 'getter: returns +0xB0', 'getter'),
]
CHAIN_GAME = [
    (0x146ED65, 'call 0x18d8710', None, 'a loadout slot click rebuilds the grid'),
    (0x18D8C8B, 'call 0x18d44b0', None, 'grid -> entries'),
    (0x18D3801, 'call 0x18cafb0', None, 'entry builder'),
    (0x18DC5D9, 'call 0x1943650', None, 'descriptor -> widget'),
    (0x1943E4F, 'call 0x144f800', None, 'kind 2: set material by name'),
    (0x143F228, 'call 0x12ee1e0', None, 'name -> GUI material (cache, else GUI API +0x230)'),
    (0x143F241, 'jmp 0x143f0b0', None, 'apply the material'),
    (0x143F13A, 'call 0x1449400', None, 'called with the material pointer, also when it is null'),
    (0x144944A, 'mov rax, qword ptr [rdx + 0x240]', None, 'GUI API +0x240: clone a material instance'),
    (0x12EE296, 'mov rax, qword ptr [rcx + 0x230]', None, 'GUI API +0x230: material by name'),
]
CHAIN_EXE = [
    (0x2646C5, 'movabs rax, 0xeac0b497876adedf', None, 'material by name: the material resource type'),
    (0x2646E8, 'lea rax, [rip + {rip}]', 0x1675000, '"Material not found." -> null'),
    (0x341D1A, 'mov rbx, qword ptr [rdx + 0x38]', None, 'clone: material+0x38 read without a null check (the crash)'),
]
LIVE_CRASH = {
    'date': '2026-10-01', 'proof': 'CustomStratagemP0Proof 0.9.0 (runtime 66EEC763)',
    'minidump': '%APPDATA%/Arrowhead/Helldivers2/dumps/dump-2026-10-01-23.17.20-f812699e-...dmp',
    'exception': {'code': '0xC0000005', 'read': '0x38', 'at': 'helldivers2.exe+0x341D1A', 'rdx': '0x0',
        'rax': '0xEAC0B497876ADEDF (material type)'},
    'windowsEvent': 'Application Error 1000: ntdll.dll+0x7E907, 0xC000000D (the game crash handler terminating after '
        'it wrote the minidump; the same signature closes earlier sessions with unrelated exit-time faults)',
    'unwound': ['helldivers2.exe+0x341D1A', 'game.dll+0x1449456', 'game.dll+0x143F13F', 'game.dll+0x1943E54',
        'game.dll+0x19437A5', 'game.dll+0x1943689', 'game.dll+0x18DC5DE', 'game.dll+0x18CB595', 'game.dll+0x18D3806',
        'game.dll+0x18D8C90', 'game.dll+0x146ED6A', 'game.dll+0x146DD09', 'game.dll+0x146D58C'],
    'customImageHashOnStack': True, 'nativeIconHashOnStack': False,
    'runtimeLog': 'ensure custom-icon-120mm APPLIED at 23:17:31 (1 write, identity unchanged); crash 23:18:15',
}


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    exe_name = [k for k in snap.modules if k.endswith('.exe')][0]
    exe_base, exe_data = snap.module_image(exe_name)
    snap.close()
    game, exe = base.Image(game_data, game_base, base.TEXT), base.Image(exe_data, exe_base, base.EXE_TEXT)
    readers = [dict(game.prove(rva, asm, target, role), consumer=consumer) for rva, asm, target, role, consumer in READERS]
    chain = [game.prove(*row) for row in CHAIN_GAME]
    exe_chain = [exe.prove(*row) for row in CHAIN_EXE]
    if exe_data[0x1675000:0x1675013] != b'Material not found.':
        raise ValueError('the material lookup message moved')
    relocation = {name: base.verify_pins_live(name, readers + chain, exe_chain) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    rows = json.loads(CALLDOWN.read_text(encoding='utf-8'))['presentation']['rows']
    icons = sorted({int(row['icon'], 16) for row in rows} - {0})
    residency = []
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        rm = images.Manager(mem)
        materials, textures = rm.names(MATERIAL), rm.names(images.TEXTURE)
        atlas, buckets = mem.ptr(rm.rm + 0x2A0), mem.u32(rm.rm + 0x2B4)
        sprites = sum(1 for icon in icons if images.resolve(mem, atlas, buckets, 24, 0x10, 0, icon) is not None)
        residency.append({'snapshot': name, 'icons': len(icons), 'material': sum(i in materials for i in icons),
            'atlasSprite': sprites, 'standaloneTexture': sum(i in textures for i in icons)})
        mem.close()
    if any(r['material'] != len(icons) or r['atlasSprite'] != len(icons) or r['standaloneTexture'] for r in residency):
        raise ValueError('a vanilla icon is not a resident material and atlas sprite: %r' % residency)

    data = hd2_game_data.Data()
    found = data.find({(icon, MATERIAL) for icon in icons})
    bodies = {icon: data.read(found[(icon, MATERIAL)][0], found[(icon, MATERIAL)][1]) for icon in icons
        if (icon, MATERIAL) in found}
    template = None
    for icon, body in bodies.items():
        if len(body) != 160 or struct.unpack_from('<IQ', body, 0x88) != (IMAGE_PROPERTY, icon):
            raise ValueError('icon material 0x%016X differs from the icon material layout' % icon)
        masked = body[:0x8C] + bytes(8) + body[0x94:]
        if template is None:
            template = masked
        elif masked != template:
            raise ValueError('icon material 0x%016X differs from the others outside its name' % icon)
    packages = sorted({found[(icon, MATERIAL)][0] for icon in bodies})

    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0,
        'readers': readers, 'consumers': {kind: sorted('0x%X' % r['rva'] for r in readers if r['consumer'] == kind)
            for kind in ('material', 'material_descriptor_shape', 'image', 'getter')},
        'materialPath': {'game': chain, 'exe': exe_chain},
        'pinnedBytesMismatchPerSnapshot': relocation,
        'vanillaIcons': {'values': len(icons), 'residency': residency,
            'materials': {'found': len(bodies), 'packages': packages, 'size': 160,
                'imageProperty': '0x%08X' % IMAGE_PROPERTY, 'nameOffset': 0x8C,
                'identicalOutsideName': True, 'template': template.hex()}},
        'liveCrash': LIVE_CRASH,
        'conclusion': ('A stratagem icon value names three vanilla resources of one name: a GUI material (whose image '
            'property is that same name), an atlas sprite and a texture. The loadout grid draws the icon as the GUI '
            'material, and the material path has no fallback: a name without a material crashes the game. A custom '
            'image that is only a texture is not safe for the stratagem icon; presentation_icon refuses custom images.')}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; readers', len(readers), '; vanilla icon materials', len(bodies),
        'identical outside the name; residency', [(r['material'], r['atlasSprite']) for r in residency][:1])


if __name__ == '__main__':
    main()
