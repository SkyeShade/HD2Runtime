"""Can a Runtime-drawn mod window show Chinese, Japanese, Korean and Cyrillic text in THE GAME'S OWN fonts
(research/docs/game-font-text.md)? Read-only, offline: the installed game's archives (scripts/hd2_game_data.py), the
helldivers2.exe and game.dll images and the retained snapshots of build F5FEE03DCFDB. Nothing is written to the game.
The third-party Know Your Constellation mod (reading a font atlas from game.dll memory) is a lead only: every claim
here is proven from game data and game code.

Proves:

1. Gui.text's arguments (exe 0x3E5120, Gui.text; 0x3E54D0, update_text). The font (Lua argument 3) is a string,
   hashed with MurmurHash64 (0x5D5840), or else a userdata whose 64-bit value is read at +8: an IdString64 from
   IdString64.from_hex. So a font whose name string is unknown is named by its hash. The material (argument 5) goes
   through the bitmap parser 0x3E0FA0 (a string or an IdString64, research bitmapContract): the GUI's own instance.
2. The font lookup (0x25E630, called for every text 0x26D932): a FONT resource (0x9EFE0A916AAE7880) by that hash, else a
   dynamic font (type 0x05106B81DCD58A13) of that hash. Its result is used with no null check (0x26D947): a font
   that is not loaded must never be passed.
3. Two font classes. A FONT resource is an engine distance-field font (vtable exe 0x1670A68): its glyph records are
   drawn from the texture of the MATERIAL the text names; its +0x18 method returns false (0x173010). A dynamic font
   (vtable 0x1668BC0) embeds a TrueType/OpenType file and renders glyphs at run time into an atlas of its own; its
   +0x18 method returns true (0xB49B0) and Gui.text then binds that atlas into the material's msdf_texture
   (0x88BAC99B) itself (0x26D812..0x26D831, through the material texture setter 0x4F3230).
4. The game's own fonts per language (installed data): every language font package holds two FONT resources (a bold
   and a regular weight, MTSDF atlases of em 32), each with its own R8G8B8A8 atlas TEXTURE (proven by fitting the glyph
   records: every cell border is outside the glyphs in the font's own atlas only), two dynamic fonts (the full
   TrueType/OpenType file) and twelve materials, none named like a font and none naming an atlas.
5. Which package is loaded (game.dll): the language record table 0x37C4B70[language] + 0x18 names the font package of
   each game language; switching the language queues that package (0xAB4802..0xAB4845) and clears the font table
   0x3772260. Read from a retained snapshot's heap: us/gb/bp/de/es/fr/it/ms/pl/pt -> 41C8EFF8188E4862 (Latin),
   jp -> F7B9C03FFF72FFD3, ko -> 9212D7034DC5D55A, ru -> 0DE4B81E19A79AA8, cn -> 09CAA46BC556E38F,
   tc -> C0B7644CC5C4AAA8. In every retained (English) snapshot only the Latin set's fonts and atlases are loaded.
6. The shader. The game's font material templates (0x51C11754 monaco's, 0xC270C8D0 the language fonts', ...) are
   shader libraries in the render package ee6b1ba7e22d71ed whose compiled code is byte-identical but for the ids: one
   MSDF text shader with msdf_texture (0x88BAC99B), px_range, sharpness and a shadow. A Runtime material made of
   monaco's bytes (what scripts/hd2_font.py already ships for FS Sinclair) draws the language fonts' atlases.
7. Placement. The static glyph function (0x173310): scale = size / em; a cell's left at pen x + (bx + kerning) x scale,
   its top at y + (offset - by - pad) x scale (y up); the pen advances (advance + kerning) x scale; kerning pairs at
   +0x4C / +0x50 keyed (previous << 32) | codepoint (0x173250). Measured on the atlases, every language font's baseline
   is exactly the y given (drop 0), and the Runtime's FS Sinclair fonts' is (pad - offset) / em = 0.42 x size below
   it, which the live r50 calibration (0.41) measured independently.

The mechanism the Runtime uses (docs/ui-overlay.md "Other scripts"): Gui.text with the language FONT named by its
hash (IdString64), a Runtime-owned material per font (monaco's bytes, a placeholder texture), and that GUI's instance
of the material pointed at the font's atlas with Material.set_texture once the atlas is proven loaded in the frame -
the technique the game HUD icons proved live (docs/game-icons.md). Output: research/game-font-text-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import hd2_archive  # noqa: E402
import hd2_font  # noqa: E402
import hd2_game_data  # noqa: E402
import research_event_state as base  # noqa: E402
import research_image_resources as resources  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/game-font-text-F5FEE03DCFDB.json'
FONT, DYNAMIC, TEXTURE = hd2_font.FONT_TYPE, 0x05106B81DCD58A13, hd2_font.TEXTURE_TYPE
MATERIAL, SHADER_LIBRARY = hd2_font.MATERIAL_TYPE, hd2_archive.resource_hash('shader_library')
LANGUAGE_RECORDS, LANGUAGE_CODES, LANGUAGES = 0x37C4B70, 0x37C5650, 15   # game.dll: per-language records, codes
FONT_TABLE = 0x3772260
PACKAGES = ['41c8eff8188e4862', '0de4b81e19a79aa8', '09caa46bc556e38f', 'c0b7644cc5c4aaa8', 'f7b9c03fff72ffd3',
    '9212d7034dc5d55a', '6728ac296c9eab7b', '9ba626afa44a3aa3']
FONT_TEMPLATES = [0x51C11754, 0xC270C8D0, 0x19CA6EFC, 0x4AB9271A]
STATIC_VTABLE, DYNAMIC_VTABLE = 0x1670A68, 0x1668BC0
RANGES = {'ascii': (32, 127), 'latin1': (160, 256), 'latinExtA': (256, 384), 'greek': (0x370, 0x400),
    'cyrillic': (0x400, 0x530), 'kana': (0x3040, 0x3100), 'cjk': (0x4E00, 0xA000), 'hangul': (0xAC00, 0xD7A4)}

EXE = {
    'guiTextArguments': [
        (0x3E51A9, 'cmp eax, 4', None, 'Gui.text: the font (Lua argument 3) is a string (lua_type 4) ...'),
        (0x3E51C7, 'call 0x5d5840', None, '... hashed (MurmurHash64) ...'),
        (0x3E51D7, 'mov rbx, qword ptr [rax + 8]', None, '... else a userdata whose 64-bit value is at +8 (IdString64)'),
        (0x3E5202, 'call 0x3e0fa0', None, 'the material (argument 5) through the bitmap parser (string or IdString64)'),
        (0x3E5591, 'call 0x5d5840', None, 'update_text: the same font parse one argument later ...'),
        (0x3E55A1, 'mov rbx, qword ptr [rax + 8]', None, '... (IdString64 value) ...'),
        (0x3E55CC, 'call 0x3e0fa0', None, '... and the same material parser'),
    ],
    'textCreation': [
        (0x26D498, 'cmp al, 0xf0', None, 'the text is decoded as UTF-8, four-byte sequences included'),
        (0x26D7FF, 'call 0x25e630', None, 'each run\'s font is looked up ...'),
        (0x26D812, 'call qword ptr [rdx + 0x18]', None, '... and asked whether it has an atlas of its own (+0x18) ...'),
        (0x26D81D, 'mov edx, 0x88bac99b', None, '... then its atlas is bound to the material\'s msdf_texture ...'),
        (0x26D82A, 'mov r8, qword ptr [r8 + 0xd8]', None, '... (the dynamic font\'s glyph cache +0xD8) ...'),
        (0x26D831, 'call 0x4f3230', None, '... through the material texture setter'),
        (0x26D932, 'call 0x25e630', None, 'the text\'s own font ...'),
        (0x26D947, 'mov rdx, qword ptr [rax]', None, '... is used with no null check: never pass a font not loaded'),
    ],
    'fontLookup': [
        (0x25E642, 'movabs rax, 0x9efe0a916aae7880', None, 'a FONT resource of that name first ...'),
        (0x25E68E, 'movabs rax, 0x5106b81dcd58a13', None, '... else a dynamic font of that name'),
    ],
    'fontClasses': [
        (0x173010, 'xor al, al', None, 'FONT (static distance-field font): no atlas of its own; the material\'s texture'),
        (0xB49B0, 'mov al, 1', None, 'dynamic font: an atlas of its own, bound by Gui.text'),
    ],
    'glyphPlacement': [
        (0x173341, 'divss xmm6, dword ptr [r11 + 8]', None, 'scale = size / em (+8)'),
        (0x173354, 'cmp dword ptr [r10 + rax*4], r8d', None, 'the codepoint searched in the font\'s list (+0x44, +0x48)'),
        (0x1733F5, 'addss xmm0, dword ptr [rax + 0x24]', None, 'the cell padding (+0x24) ...'),
        (0x1733FA, 'movss xmm1, dword ptr [rax + 0x10]', None, '... the vertical offset (+0x10) ...'),
        (0x1733FF, 'subss xmm1, dword ptr [rsp + 0x34]', None, '... minus the record\'s by: the cell\'s place'),
        (0x173490, 'addss xmm0, xmm4', None, 'the pen advance: advance + kerning ...'),
        (0x17349D, 'addss xmm0, dword ptr [rsi]', None, '... times the scale, added to the pen'),
        (0x17325C, 'shl r9, 0x20', None, 'kerning key: (previous << 32) | codepoint ...'),
        (0x173260, 'mov r11d, dword ptr [rax + 0x4c]', None, '... in the pair table: count +0x4C ...'),
        (0x173264, 'mov r10d, dword ptr [rax + 0x50]', None, '... offset +0x50 (keys, then f32 values)'),
    ],
}
GAME = {
    'languageFonts': [
        (0xAB4802, 'mov rax, qword ptr [r8 + rdx*8 + 0x37c4b70]', None, 'a language switch: the language\'s record ...'),
        (0xAB480A, 'mov rcx, qword ptr [rax + 0x18]', None, '... its font package (+0x18) queued (+0x19E98)'),
        (0xAB4816, 'mov rax, qword ptr [r8 + rdx*8 + 0x37c5650]', None, 'the language code string (+8) hashed'),
        (0xAB4949, 'movups xmmword ptr [rip + {rip}], xmm0', FONT_TABLE, 'the game\'s font table cleared'),
        (0x12FF3E4, 'mov rax, qword ptr [rdx + r8 + 0x37c4b70]', None, 'the same at the other switch site'),
    ],
}


def coverage(cps):
    return {k: sum(1 for c in cps if lo <= c < hi) for k, (lo, hi) in RANGES.items()}


def installed_fonts(data):
    """Every font package: its FONT resources (header, coverage, atlas fit), its dynamic fonts and its materials."""
    rows = [r for r in data.tables() if r[0] in PACKAGES]
    out = {}
    for package in PACKAGES:
        mine = [r for r in rows if r[0] == package]
        textures = {r[1]: r for r in mine if r[2] == TEXTURE}
        atlases = {}
        for name, r in textures.items():
            main = data.read(package, r[3])
            dds = main.find(b'DDS ')
            if dds >= 0 and main[dds + 84:dds + 88] == b'DX10' and struct.unpack_from('<I', main, dds + 128)[0] == 28 \
                    and r[5][1] > 100000:
                atlases[name] = hd2_font.atlas_top_mip(main, data.read(package, r[5], '.gpu_resources'))
        fonts = []
        for r in mine:
            if r[2] != FONT:
                continue
            main = data.read(package, r[3])
            header = hd2_font.font_header(main)
            font = hd2_font.parse_font(main)
            fits = {('%016X' % t): hd2_font.atlas_fit(font, img) for t, img in atlases.items()}
            own = [t for t, f in fits.items() if f.get('size') and f['borderInside'] == 0.0]
            entry = {'font': '0x%016X' % r[1], 'sha256': hashlib.sha256(main).hexdigest().upper(),
                'em': header['em'], 'line': header['line'], 'offset': header['offset'], 'pad': header['pad'],
                'distance': [header['scale'], header['bias']], 'kerningPairs': header['kerning'],
                'glyphs': len(font['glyphs']), 'coverage': coverage(font['glyphs']), 'atlasFit': fits,
                'atlas': '0x' + own[0] if len(own) == 1 else None}
            if len(own) == 1:
                img = atlases[int(own[0], 16)]
                chan = img[::7, ::7].astype(int)
                entry['atlasChannels'] = {'rgbDiffer': round(float(np.mean(np.abs(chan[:, :, 0] - chan[:, :, 1]) > 8)), 3),
                    'alphaDiffers': round(float(np.mean(np.abs(chan[:, :, 3] - chan[:, :, 0]) > 8)), 3)}
                if ord('H') in font['glyphs']:
                    try:
                        entry['placement'] = hd2_font.baseline_drop(font, img)
                    except ValueError as error:   # another distance encoding: no ink at the 0.5 crossing
                        entry['placement'] = {'unmeasured': str(error)}
            fonts.append(entry)
        dynamic = []
        for r in mine:
            if r[2] != DYNAMIC:
                continue
            main = data.read(package, r[3], ) if r[3][1] < 64 else data.item_bytes(package, r[3][0], 0x60)
            sfnt = main[0x40:0x44]
            dynamic.append({'font': '0x%016X' % r[1], 'bytes': r[3][1], 'self': '0x%016X' % struct.unpack_from('<Q', main)[0],
                'fallback': '0x%016X' % struct.unpack_from('<Q', main, 0x18)[0],
                'sfnt': {b'\x00\x01\x00\x00': 'TrueType', b'OTTO': 'OpenType CFF'}.get(sfnt, sfnt.hex())})
        materials = []
        for r in mine:
            if r[2] != MATERIAL or r[3][1] < 0x94:
                continue
            main = data.read(package, r[3])
            template = struct.unpack_from('<I', main, 0x80)[0]
            slot, texture = struct.unpack_from('<IQ', main, 0x88)
            if slot == 0x88BAC99B:
                materials.append({'material': '0x%016X' % r[1], 'template': '0x%08X' % template,
                    'msdfTexture': '0x%016X' % texture, 'textureInPackage': texture in textures})
        out[package] = {'fonts': fonts, 'dynamicFonts': dynamic, 'fontMaterials': materials}
    return out


def font_shaders(data):
    """The font material templates' shader libraries: where they are and whether their compiled code is the same."""
    libs = {}
    for archive, name, rtype, main, _stream, gpu in data.tables():
        if rtype != SHADER_LIBRARY or name in libs or not 0 < gpu[1] < 200000:
            continue
        blob = data.read(archive, gpu, '.gpu_resources')
        if len(blob) > 0xE4:
            template = struct.unpack_from('<I', blob, 0xE0)[0]
            if template in FONT_TEMPLATES:
                libs[name] = (archive, template, blob)
    out = {}
    reference = next((b for a, t, b in libs.values() if t == 0x51C11754), None)
    for name, (archive, template, blob) in sorted(libs.items(), key=lambda kv: kv[1][1]):
        diff = [i for i in range(min(len(blob), len(reference))) if blob[i] != reference[i]] if reference else []
        dxbc = [m.start() for m in re.finditer(b'DXBC', blob)]
        same_code = bool(reference) and len(blob) == len(reference) and all(i < min(dxbc) for i in diff) if dxbc else False
        out['0x%08X' % template] = {'library': '0x%016X' % name, 'archive': archive, 'bytes': len(blob),
            'declares': sorted(n for n in ('msdf_texture', 'px_range', 'sharpness', 'shadow_color', 'shadow_offset')
                if n.encode() in blob), 'differingBytes': len(diff), 'compiledCodeIdenticalToMonaco': same_code}
    return out


def language_table(mem):
    out = []
    for i in range(LANGUAGES):
        record = mem.ptr(mem.game + LANGUAGE_RECORDS + 8 * i)
        code = mem.ptr(mem.game + LANGUAGE_CODES + 8 * i)
        name = mem.read(mem.ptr(code + 8), 8).split(b'\0')[0].decode('latin-1')
        out.append({'index': i, 'code': name, 'fontPackage': '%016x' % mem.u64(record + 0x18)})
    return out


def residency(names):
    out = {}
    watch = {}
    for package, label in [('41c8eff8188e4862', 'default'), ('0de4b81e19a79aa8', 'ru'), ('09caa46bc556e38f', 'zh_hans'),
            ('c0b7644cc5c4aaa8', 'zh_hant'), ('f7b9c03fff72ffd3', 'ja'), ('9212d7034dc5d55a', 'ko')]:
        for key, _l, pkg, _langs, font, atlas in hd2_font.GAME_FONTS:
            if '%016x' % pkg == package:
                watch[label] = (font, atlas)
    for name in names:
        mem = base.Mem(name)
        rm = resources.Manager(mem)
        out[name] = {'fontsLoaded': sorted('0x%016X' % f for f in rm.names(FONT)),
            'dynamicFontsLoaded': sorted('0x%016X' % f for f in rm.names(DYNAMIC)),
            'gameFonts': {k: {'font': rm.lookup(FONT, f)[0], 'atlas': rm.lookup(TEXTURE, t)[0]}
                for k, (f, t) in watch.items()},
            'fontTable': ['0x%016X' % mem.u64(mem.game + FONT_TABLE + 8 * k) for k in range(10)]}
        if name == names[0]:
            out[name]['languages'] = language_table(mem)
        mem.close()
    return out


def vtable_check(exe):
    out = {}
    for label, vt, expect in (('static', STATIC_VTABLE, 0x173010), ('dynamic', DYNAMIC_VTABLE, 0xB49B0)):
        entry = exe.pointer_rva(vt + 0x18)
        if entry != expect:
            raise ValueError('the %s font vtable +0x18 is %r' % (label, entry))
        out[label] = {'vtable': '0x%X' % vt, 'plus0x18': '0x%X' % entry}
    return out


def game_font_selection(data):
    src = hd2_font.read_game_fonts(data)
    out = {}
    for key, label, package, langs, font, atlas in hd2_font.GAME_FONTS:
        m = hd2_font.game_font_metrics(key, src[key])
        out[key] = {'label': label, 'package': '%016x' % package, 'languages': langs, 'font': '0x%016X' % font,
            'atlas': '0x%016X' % atlas, 'line': m['header']['line'], 'drop': m['drop'], 'cap': m['cap'],
            'glyphs': len(m['advances']), 'kerningPairs': len(m['kerning']), 'fit': m['fit']}
    return out


def runtime_font_drop():
    """The same placement measured on the Runtime's own FS Sinclair font (built as the release builds it)."""
    import generate_ui_fonts
    src = generate_ui_fonts.game_sources()
    out = {}
    for role, source in generate_ui_fonts.ROLES.items():
        built = hd2_font.build_font(src['ttf'][source], hd2_font.NAMES[source], src['monaco_material'])
        main = next(v[0] for (t, _h), v in built['resources'].items() if t == FONT)
        font = hd2_font.parse_font(main)
        rgba = np.repeat(built['atlas'][:, :, None], 4, axis=2)
        p = hd2_font.baseline_drop(font, rgba)
        out[role] = {'drop': p['drop'], 'formula': round((font['pad'] - font['offset']) / font['em'], 4)}
    return out


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    exe_name = [k for k in snap.modules if k.endswith('.exe')][0]
    exe_base, exe_data = snap.module_image(exe_name)
    snap.close()
    exe, game = base.Image(exe_data, exe_base, base.EXE_TEXT), base.Image(game_data, game_base, base.TEXT)
    exe_pins = {group: [exe.prove(*row) for row in rows] for group, rows in EXE.items()}
    game_pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    flat_exe = [p for rows in exe_pins.values() for p in rows]
    flat_game = [p for rows in game_pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat_game, flat_exe) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    data = hd2_game_data.Data()
    result = {'build': 'F5FEE03DCFDB', 'gameDllSha256': base.PROFILE_DLL_SHA, 'exeSha256': base.PROFILE_EXE_SHA,
        'writes': 0, 'protectionChanges': 0, 'pins': {'exe': exe_pins, 'game': game_pins},
        'pinnedBytesMismatchPerSnapshot': relocation, 'fontClasses': vtable_check(exe),
        'snapshots': residency(SNAPSHOTS), 'packages': installed_fonts(data), 'fontShaders': font_shaders(data),
        'selection': game_font_selection(data), 'runtimeFontPlacement': runtime_font_drop()}
    langs = result['snapshots'][SNAPSHOTS[0]]['languages']
    result['determinations'] = {
        'fontArgument': 'Gui.text and update_text take the font as a string (MurmurHash64) or an IdString64 (its value '
            'at +8): a font is named by its hash (IdString64.from_hex) when its name string is unknown.',
        'fontKinds': 'A name resolves to a FONT resource first, else a dynamic font; the result is not null-checked, '
            'so a font is passed only when proven loaded.',
        'staticFontAtlas': 'A FONT resource draws through the texture of the material the text names (its +0x18 '
            'method is false); no game material names a language atlas, so the Runtime ships its own material per '
            'font and points this GUI\'s instance at the atlas with Material.set_texture.',
        'dynamicFontAtlas': 'A dynamic font\'s run-time atlas is bound into the material by Gui.text itself (full '
            'TrueType coverage), but its advances depend on its run-time rasterisation: not measurable offline. '
            'Not used (a lead).',
        'residency': 'Exactly the selected language\'s font package is loaded: ' + ', '.join(
            '%s %s' % (l['code'], l['fontPackage']) for l in langs) + '.',
        'shader': 'All font material templates compile to the same MSDF shader (msdf_texture, px_range, sharpness, '
            'shadow): monaco\'s material bytes draw the language atlases.',
        'placement': 'Language fonts: baseline at the y given (drop 0), advances and kerning from the resource; FS '
            'Sinclair: (pad - offset) / em below it (0.42, live calibration 0.41).',
        'greek': 'No game font holds Greek beyond one character: Greek cannot be drawn with the game\'s fonts.',
    }
    OUTPUT.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT))


if __name__ == '__main__':
    main()
