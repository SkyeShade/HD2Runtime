"""Runtime-owned engine FONTS of the game's own typeface (docs/custom-stratagem-panel.md "Fonts"): FS Sinclair, the font
the native loadout screen draws, rebuilt at build time from the installed game into the engine's distance-field font
format so the Lua GUI (Gui.text) can draw it. The game draws FS Sinclair through its own runtime glyph system, which the
Lua GUI cannot reach; the engine fonts the GUI can name (core/performance_hud/monaco and the others) are MTSDF atlases.

What the build makes, per font (research: the engine font format, decoded from core/performance_hud/monaco and the
game's other fonts; scripts/research_ui_fonts.py):
* a FONT resource <name>: the header (an id, the em size in atlas pixels, the line height, a vertical offset, the atlas
  texel size, the distance encoding -255/64 and 0.4 x 255/64, the cell padding 8, the fallback glyph), then the
  codepoints (u32 each) and one record per codepoint (7 floats: atlas x, y, w, h, bearing x, bearing y above the
  baseline, advance), every value in atlas pixels at the em size;
* a MATERIAL resource <name>: the monaco font material's exact bytes with its glyph texture (+0x8C) naming the atlas
  below (the same shader and distance range: 4 atlas pixels from 0 to 255);
* a TEXTURE resource <name>/atlas: R8G8B8A8 with its full mip chain; every channel the same true signed distance,
  encoded as monaco's: 0.4 at the edge, 64 levels a pixel (so its multi-channel median and its alpha agree).
The glyphs come from the TTF the game ships in package 6728ac296c9eab7b (FS Sinclair, FS Sinclair Medium), read-only
from the installed game; nothing is written to the game folder.
"""
from __future__ import annotations

import hashlib
import io
import math
import struct

import numpy as np

FONT_TYPE, MATERIAL_TYPE, TEXTURE_TYPE = 0x9EFE0A916AAE7880, 0xEAC0B497876ADEDF, 0xCD4238C6A0C69E32
TTF_TYPE = 0xCBAE3394881E3D1B
FONT_ARCHIVE = '6728ac296c9eab7b'
SOURCES = {'regular': 0xA4EA96E59644F60D, 'medium': 0x6DECA49EA82C82EC}      # FS Sinclair, FS Sinclair Medium (TTF)
MONACO = 0x3DC65B5A76FCE8F9                                                   # core/performance_hud/monaco
MONACO_ATLAS = 0x35FCB2056C9C789E                                             # its material's atlas texture
NAMES = {'regular': 'hd2runtime_fonts/fs_sinclair', 'medium': 'hd2runtime_fonts/fs_sinclair_medium'}
EM = 56                      # the em size in atlas pixels
PAD = 4                      # cell padding in atlas pixels (the header's 8 = both sides)
SCALE = 4                    # supersampling of the glyph masks
ATLAS = (1024, 512)
SLOPE, EDGE = 64 / 255, 0.4  # the distance encoding: levels per atlas pixel, the value at the edge
# ASCII, Latin-1, a few punctuation marks when the font has them, and the four arrows of the call-in code.
CODEPOINTS = list(range(32, 127)) + list(range(160, 256)) + [0x2190, 0x2191, 0x2192, 0x2193, 0x2013, 0x2014, 0x2019,
    0x201C, 0x201D, 0x2022, 0x2026]
ARROWS = {0x2190: 'left', 0x2191: 'up', 0x2192: 'right', 0x2193: 'down'}
# The arrow's shape, as fractions of the cap height: the game's stratagem code arrows are a broad triangular head about
# half their length and a straight stem under half the head's width.
ARROW = {'length': 1.0, 'width': 0.96, 'head': 0.52, 'stem': 0.42, 'side': 0.1}


def arrow_polygon(direction: str, cap: float) -> tuple[list, float]:
    """The arrow glyph pointing `direction`, cap pixels tall (a horizontal one as long): its outline from the pen at
    the baseline (y down) and its advance."""
    length, width = ARROW['length'] * cap, ARROW['width'] * cap
    head, stem = ARROW['head'] * cap, ARROW['stem'] * width
    # Pointing up in a width x length box: the tip at the top, the stem down to the bottom.
    up = [(width / 2, 0), (width, head), ((width + stem) / 2, head), ((width + stem) / 2, length),
        ((width - stem) / 2, length), ((width - stem) / 2, head), (0, head)]
    turn = {'up': lambda x, y: (x, y), 'down': lambda x, y: (x, length - y),
        'left': lambda x, y: (y, x), 'right': lambda x, y: (length - y, x)}[direction]
    points = [turn(x, y) for x, y in up]
    box_w = width if direction in ('up', 'down') else length
    box_h = length if direction in ('up', 'down') else width
    side = ARROW['side'] * cap
    # On the baseline, centred on the cap height.
    lift = -cap + (cap - box_h) / 2
    return [(x + side, y + lift) for x, y in points], box_w + 2 * side


def ttf_of(resource_main: bytes) -> bytes:
    """The TrueType file inside the game's ttf resource (a 16-byte resource header, then the sfnt)."""
    if resource_main[16:20] not in (b'\x00\x01\x00\x00', b'true', b'OTTO'):
        raise ValueError('not a TrueType resource')
    return resource_main[16:]


def _window_min(a, axis, radius, add):
    """min over shifts k in [-radius, radius] of a shifted by k along axis, plus add(k)."""
    out = np.full(a.shape, np.inf)
    n = a.shape[axis]
    for k in range(-radius, radius + 1):
        shifted = np.full(a.shape, np.inf)
        src = [slice(None)] * a.ndim
        dst = [slice(None)] * a.ndim
        if k >= 0:
            src[axis], dst[axis] = slice(0, n - k), slice(k, n)
        else:
            src[axis], dst[axis] = slice(-k, n), slice(0, n + k)
        shifted[tuple(dst)] = a[tuple(src)]
        out = np.minimum(out, shifted + add(k))
    return out


def edt(features: np.ndarray, radius: int) -> np.ndarray:
    """The Euclidean distance from every pixel to the nearest feature pixel, exact up to radius (inf beyond)."""
    base = np.where(features, 0.0, np.inf)
    rows = _window_min(base, 1, radius, lambda k: k * k)
    return np.sqrt(_window_min(rows, 0, radius, lambda k: k * k))


def glyph_sdf(mask: np.ndarray) -> np.ndarray:
    """The signed distance (outside positive) of a supersampled mask, down to atlas pixels (SCALE x SCALE blocks)."""
    radius = SCALE * (PAD + 1)
    inside = mask >= 128
    d_out = edt(inside, radius)
    d_in = edt(~inside, radius)
    signed = np.where(inside, -(d_in - 0.5), d_out - 0.5) / SCALE
    signed = np.nan_to_num(signed, posinf=PAD + 1, neginf=-(PAD + 1))
    h, w = signed.shape[0] // SCALE, signed.shape[1] // SCALE
    return signed[:h * SCALE, :w * SCALE].reshape(h, SCALE, w, SCALE).mean(axis=(1, 3))


def encode(signed: np.ndarray) -> np.ndarray:
    return np.clip(np.round((EDGE - signed * SLOPE) * 255), 0, 255).astype(np.uint8)


def build_font(ttf: bytes, name: str, monaco_material: bytes) -> dict:
    """{(type, name hash): (main, gpu)} for one font, and its report."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        from hd2_archive import resource_hash
    except ImportError:
        from tools.hd2_archive import resource_hash
    font = ImageFont.truetype(io.BytesIO(ttf), size=EM * SCALE)
    def rendered(ch):
        img = Image.new('L', (EM * SCALE * 2, EM * SCALE * 2), 0)
        ImageDraw.Draw(img).text((EM * SCALE // 2, EM * SCALE * 3 // 2), ch, fill=255, font=font, anchor='ls')
        return img.tobytes()
    notdef = rendered(chr(0xFFFF))
    cap = font.getbbox('H', anchor='ls')
    cap = cap[3] - cap[1]
    glyphs, synthesized = [], []
    for cp in CODEPOINTS:
        ch = chr(cp)
        x0, y0, x1, y1 = font.getbbox(ch, anchor='ls')
        advance = font.getlength(ch) / SCALE
        missing = (cp != 32 and (x1 <= x0 or y1 <= y0)) or (cp > 127 and rendered(ch) == notdef)
        if missing and cp in ARROWS:
            # Not in the font: the call-in code's arrow, drawn as the game's own (see arrow_polygon).
            points, advance = arrow_polygon(ARROWS[cp], cap)
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            glyphs.append((cp, (min(xs), min(ys), max(xs), max(ys)), advance / SCALE,
                lambda draw, ox, oy, points=points: draw.polygon([(ox + x, oy + y) for x, y in points], fill=255)))
            synthesized.append(cp)
            continue
        if missing:
            continue                                       # not in the font: its .notdef box
        glyphs.append((cp, (x0, y0, x1, y1), advance,
            lambda draw, ox, oy, ch=ch: draw.text((ox, oy), ch, fill=255, font=font, anchor='ls')))
    # Cells: the glyph's box plus the padding, in supersampled pixels (multiples of SCALE).
    cells = []
    for cp, (x0, y0, x1, y1), advance, paint in glyphs:
        if cp == 32:
            cells.append((cp, None, 2 * PAD, 2 * PAD, -PAD, -PAD, advance))
            continue
        gx0, gy0 = math.floor(x0 / SCALE) * SCALE, math.floor(y0 / SCALE) * SCALE
        gx1, gy1 = math.ceil(x1 / SCALE) * SCALE, math.ceil(y1 / SCALE) * SCALE
        w_hi, h_hi = gx1 - gx0 + 2 * PAD * SCALE, gy1 - gy0 + 2 * PAD * SCALE
        img = Image.new('L', (w_hi, h_hi), 0)
        paint(ImageDraw.Draw(img), PAD * SCALE - gx0, PAD * SCALE - gy0)
        sdf = encode(glyph_sdf(np.array(img)))
        cells.append((cp, sdf, sdf.shape[1], sdf.shape[0], gx0 / SCALE - PAD, gy0 / SCALE - PAD, advance))
    # Shelf packing, tallest first, top-down rows of the atlas.
    W, H = ATLAS
    atlas = np.zeros((H, W), dtype=np.uint8)
    placed = {}
    x = y = row_h = 1
    for cp, sdf, w, h, bx, by, adv in sorted(cells, key=lambda c: (-c[3], c[0])):
        if x + w + 1 > W:
            x, y, row_h = 1, y + row_h + 1, 1
        if y + h + 1 > H:
            raise ValueError('the font atlas is full')
        if sdf is not None:
            atlas[y:y + h, x:x + w] = sdf
        placed[cp] = (float(x), float(y), float(w), float(h), float(bx), float(by), float(adv))
        x, row_h = x + w + 1, max(row_h, h)
    order = [c[0] for c in cells]
    fallback = placed.get(ord('?'))
    # The font resource.
    name_hash = resource_hash(name)
    ascent, descent = font.getmetrics()
    header = struct.pack('<Q', name_hash) + struct.pack('<8f', EM, EM, -descent / SCALE * 0.75, 1 / W, 1 / H,
        -1 / SLOPE, EDGE / SLOPE, 2.0 * PAD)
    header += struct.pack('<7f', *fallback)
    n = len(order)
    codepoints_at = 0x58
    end = codepoints_at + 4 * n + 28 * n
    header += struct.pack('<5I', n, codepoints_at, 0, end, 0)
    assert len(header) == codepoints_at, len(header)
    body = struct.pack('<%dI' % n, *order) + b''.join(struct.pack('<7f', *placed[cp]) for cp in order)
    font_main = header + body
    # The atlas: every channel the distance; the full mip chain (2 x 2 means).
    rgba = np.repeat(atlas[:, :, None], 4, axis=2)
    levels, img = [], rgba.astype(np.float32)
    while True:
        levels.append(np.clip(np.round(img), 0, 255).astype(np.uint8).tobytes())
        if img.shape[0] == 1 and img.shape[1] == 1:
            break
        h2, w2 = max(1, img.shape[0] // 2), max(1, img.shape[1] // 2)
        img = img[:h2 * 2, :w2 * 2].reshape(h2, 2, w2, 2, 4).mean(axis=(1, 3)) if img.shape[0] > 1 and img.shape[1] > 1 \
            else img.reshape(h2, -1, w2, 1, 4).mean(axis=(1, 3))
    texture_name = name + '/atlas'
    texture_main = texture_header(W, H, len(levels))
    # The material: monaco's, with its glyph texture naming this atlas.
    if monaco_material[0x8C:0x94] != struct.pack('<Q', 0x35FCB2056C9C789E):
        raise ValueError('the monaco font material is not the reviewed one (+0x8C its glyph texture)')
    material = monaco_material[:0x8C] + struct.pack('<Q', resource_hash(texture_name)) + monaco_material[0x94:]
    resources = {(FONT_TYPE, name_hash): (font_main, b''), (MATERIAL_TYPE, name_hash): (material, b''),
        (TEXTURE_TYPE, resource_hash(texture_name)): (texture_main, b''.join(levels))}
    report = {'name': name, 'glyphs': n, 'em': EM, 'atlas': [W, H], 'ascent': ascent / SCALE, 'descent': descent / SCALE,
        'capHeight': (font.getbbox('H', anchor='ls')[3] - font.getbbox('H', anchor='ls')[1]) / SCALE,
        'sha256': {'font': hashlib.sha256(font_main).hexdigest(), 'atlas': hashlib.sha256(b''.join(levels)).hexdigest()},
        'missing': [cp for cp in CODEPOINTS if cp not in placed], 'synthesized': synthesized}
    return {'resources': resources, 'report': report, 'atlas': atlas, 'records': placed}


def texture_header(width: int, height: int, mips: int) -> bytes:
    """The main part of an R8G8B8A8 texture, exactly as the game's font atlases have it (monaco's: header, DDS with the
    DX10 extension, the row pitch)."""
    header = struct.pack('<4I', 0, 0, 0xFFFFFFFF, 0).ljust(0xC0, b'\0')
    dds = struct.pack('<7I', 124, 0x21007, height, width, width * 4, 0, mips) + bytes(44) \
        + struct.pack('<8I', 32, 4, 0x30315844, 0, 0, 0, 0, 0) + struct.pack('<5I', 0x401008, 0, 0, 0, 0)
    return header + b'DDS ' + dds + struct.pack('<5I', 28, 3, 0, 1, 0)


def parse_font(main: bytes) -> dict:
    """A font resource read back: {em, line, atlas texel, glyphs = {codepoint: (x, y, w, h, bx, by, advance)}}."""
    em, line, offset, tu, tv, scale, bias, pad = struct.unpack_from('<8f', main, 8)
    n, at, _z, end, _k = struct.unpack_from('<5I', main, 0x44)
    cps = struct.unpack_from('<%dI' % n, main, at)
    recs = [struct.unpack_from('<7f', main, at + 4 * n + 28 * i) for i in range(n)]
    return {'em': em, 'line': line, 'offset': offset, 'texel': (tu, tv), 'scale': scale, 'bias': bias, 'pad': pad,
        'end': end, 'glyphs': dict(zip(cps, recs))}


def preview(font: dict, atlas: np.ndarray, text: str, size: float) -> np.ndarray:
    """An offline rendering of `text` at `size` pixels (the engine's quads, a smoothstep at the edge): for review."""
    g = font['glyphs']
    k = size / font['em']
    width = int(sum(g.get(ord(c), g[ord('?')])[6] for c in text) * k) + 16
    height = int(font['line'] * k * 1.6) + 8
    out = np.zeros((height, width))
    pen, base = 8.0, height * 0.75
    for c in text:
        x, y, w, h, bx, by, adv = g.get(ord(c), g[ord('?')])
        if w > 0 and h > 0:
            cell = atlas[int(y):int(y + h), int(x):int(x + w)].astype(np.float32) / 255
            qw, qh = max(1, int(round(w * k))), max(1, int(round(h * k)))
            ys = (np.arange(qh) + 0.5) / qh * h - 0.5
            xs = (np.arange(qw) + 0.5) / qw * w - 0.5
            y0, x0 = np.clip(np.floor(ys).astype(int), 0, int(h) - 1), np.clip(np.floor(xs).astype(int), 0, int(w) - 1)
            y1, x1 = np.clip(y0 + 1, 0, int(h) - 1), np.clip(x0 + 1, 0, int(w) - 1)
            fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
            v = (cell[y0][:, x0] * (1 - fy) * (1 - fx) + cell[y1][:, x0] * fy * (1 - fx) + cell[y0][:, x1] * (1 - fy) * fx
                + cell[y1][:, x1] * fy * fx)
            px = 0.5 / (SLOPE * 255 * k) * 255 / 255
            alpha = np.clip((v - EDGE) / max(px, 1e-3) + 0.5, 0, 1)
            top, left = int(round(base + by * k)), int(round(pen + bx * k))
            region = out[max(0, top):top + qh, max(0, left):left + qw]
            region[:] = np.maximum(region, alpha[:region.shape[0], :region.shape[1]])
        pen += adv * k
    return (out * 255).astype(np.uint8)


# ------------------------------------------------------------------------------------------------ the game's fonts
# The game's own language fonts (research/docs/game-font-text.md): one engine FONT resource per language font package,
# the regular weight of each pair, with the atlas texture its glyph records were proven to sample (every glyph cell's
# border lies outside the glyph in that atlas and inside glyphs in the other one). The game loads exactly one of these
# packages, the selected language's (game.dll 0x37C4B70[language] + 0x18, research languagePackages). Each entry:
# key, label, the font package (archive), the game language codes that load it, the FONT and its atlas TEXTURE.
GAME_FONTS = [
    ('default', 'Latin (the European game languages)', 0x41C8EFF8188E4862,
        ['us', 'gb', 'bp', 'de', 'es', 'fr', 'it', 'ms', 'pl', 'pt'], 0x5E83C5F2A9B02110, 0xE732CCB97E7E201A),
    ('ru', 'Russian', 0x0DE4B81E19A79AA8, ['ru'], 0xE6944ADE8A140216, 0x529A0FF67A1C8A0B),
    ('zh_hans', 'Simplified Chinese', 0x09CAA46BC556E38F, ['cn'], 0xFBB35BEE675F2295, 0xF14DAED0A7D38271),
    ('zh_hant', 'Traditional Chinese', 0xC0B7644CC5C4AAA8, ['tc'], 0x7C63FEA1F706EEC4, 0x3454C1D97F395663),
    ('ja', 'Japanese', 0xF7B9C03FFF72FFD3, ['jp'], 0xD5A757787D7DCB0F, 0x9C753F055238D29A),
    ('ko', 'Korean', 0x9212D7034DC5D55A, ['ko'], 0xE007454455E2D2BB, 0x8D346DCDD08459D5),
]
GAME_FONT_MATERIAL = 'hd2runtime_fonts/game/'                # + key: the Runtime-owned material of each game font
GAME_FONT_PLACEHOLDER = 'hd2runtime_fonts/game/placeholder'   # its texture until the overlay points it at the atlas
# What every game font must be for the overlay's measuring and placement to hold (else the build refuses it): em 32,
# the cell padding 8 and the msdfgen distance encoding -3.2 / 1.6 (0.5 at the edge, 3.2 atlas pixels of range).
GAME_FONT_SHAPE = {'em': 32.0, 'pad': 8.0, 'scale': -3.2, 'bias': 1.6}


def font_header(main: bytes) -> dict:
    """A font resource's header fields (scripts/hd2_font.py layout) and its kerning pair count."""
    f = parse_font(main)
    kerning = struct.unpack_from('<I', main, 0x4C)[0]
    return {'self': struct.unpack_from('<Q', main, 0)[0], 'em': f['em'], 'line': f['line'], 'offset': f['offset'],
        'texel': f['texel'], 'scale': f['scale'], 'bias': f['bias'], 'pad': f['pad'], 'kerning': kerning,
        'glyphs': f['glyphs'], 'atlas': (round(1 / f['texel'][0]), round(1 / f['texel'][1]))}


def atlas_top_mip(texture_main: bytes, texture_gpu: bytes) -> np.ndarray:
    """The top mip level of an R8G8B8A8 atlas texture (H x W x 4)."""
    dds = texture_main.find(b'DDS ')
    if dds < 0:
        raise ValueError('not a texture resource')
    height, width = struct.unpack_from('<II', texture_main, dds + 12)
    if texture_main[dds + 84:dds + 88] != b'DX10' or struct.unpack_from('<I', texture_main, dds + 128)[0] != 28:
        raise ValueError('the atlas is not R8G8B8A8')
    if len(texture_gpu) < width * height * 4:
        raise ValueError('the atlas pixels are missing')
    return np.frombuffer(texture_gpu[:width * height * 4], dtype=np.uint8).reshape(height, width, 4)


def msdf_median(rgba: np.ndarray) -> np.ndarray:
    return np.sort(rgba[:, :, :3], axis=2)[:, :, 1]


def atlas_fit(font: dict, rgba: np.ndarray, limit: int = 400) -> dict:
    """How well a font's glyph records fit an atlas: the share of glyph-cell border pixels inside a glyph (0 for the
    font's own atlas: the padding surrounds every glyph) and of cell pixels inside one."""
    if rgba.shape[1] != round(1 / font['texel'][0]) or rgba.shape[0] != round(1 / font['texel'][1]):
        return {'size': False}
    med = msdf_median(rgba)
    border = inside = cells = 0
    for cp in sorted(font['glyphs'])[:limit]:
        x, y, w, h = font['glyphs'][cp][:4]
        if w < 4 or h < 4:
            continue
        x0, y0, x1, y1 = int(x), int(y), int(x + w) - 1, int(y + h) - 1
        edge = np.concatenate([med[y0, x0:x1 + 1], med[y1, x0:x1 + 1], med[y0:y1 + 1, x0], med[y0:y1 + 1, x1]])
        border += float((edge > 140).mean())
        inside += float((med[y0:y1 + 1, x0:x1 + 1] > 128).mean())
        cells += 1
    return {'size': True, 'borderInside': round(border / max(cells, 1), 4), 'cellInside': round(inside / max(cells, 1), 4),
        'cells': cells}


def ink_rows(font: dict, rgba: np.ndarray, cp: int) -> tuple[float, float]:
    """The ink top and bottom of a glyph in its atlas cell, in atlas pixels from the cell top (the 0.5 crossing of the
    MSDF median, the row maxima interpolated)."""
    x, y, w, h = font['glyphs'][cp][:4]
    med = msdf_median(rgba)[int(y):int(y + h), int(x):int(x + w)].astype(np.float64) / 255
    rows = med.max(axis=1)
    edge = font['bias'] / -font['scale'] if font['scale'] else 0.5   # the encoded value at the glyph edge
    ink = np.nonzero(rows > edge)[0]
    if not len(ink):
        raise ValueError('glyph %d has no ink' % cp)
    top, bottom = int(ink[0]), int(ink[-1])
    def crossing(inner, outer):
        a, b = rows[inner], rows[outer] if 0 <= outer < len(rows) else 0.0
        return (a - edge) / (a - b) if a != b else 0.5
    return top + 0.5 - crossing(top, top - 1), bottom + 0.5 + crossing(bottom, bottom + 1)


def baseline_drop(font: dict, rgba: np.ndarray, cp: int = ord('H')) -> dict:
    """Where Gui.text draws a font's baseline against the y it is given, from the engine's glyph placement (exe
    0x173310: scale = size / em; a cell's top at y + (offset - by - pad) x scale, y up) and the ink of a glyph that
    sits on the baseline: {drop (the baseline's distance below y, a fraction of the size), cap (the glyph's ink height,
    a fraction of the size)}."""
    top, bottom = ink_rows(font, rgba, cp)
    by = font['glyphs'][cp][5]
    cell_top = font['offset'] - by - font['pad']                      # above y, in font units (y up)
    return {'drop': round((bottom - cell_top) / font['em'], 4), 'cap': round((bottom - top) / font['em'], 4)}


def game_font_material(key: str, monaco_material: bytes) -> tuple[str, bytes]:
    """The Runtime-owned material of a game font: monaco's font material (the MSDF text shader the game's own font
    materials compile to, research fontShaders) with its msdf_texture naming the Runtime placeholder; the overlay
    points this GUI's instance at the game atlas (Material.set_texture) once the atlas is proven loaded."""
    try:
        from hd2_archive import resource_hash
    except ImportError:
        from tools.hd2_archive import resource_hash
    if monaco_material[0x8C:0x94] != struct.pack('<Q', 0x35FCB2056C9C789E) \
            or monaco_material[0x88:0x8C] != struct.pack('<I', 0x88BAC99B):
        raise ValueError('the monaco font material is not the reviewed one (+0x88 msdf_texture, +0x8C its texture)')
    name = GAME_FONT_MATERIAL + key
    return name, monaco_material[:0x8C] + struct.pack('<Q', resource_hash(GAME_FONT_PLACEHOLDER)) + monaco_material[0x94:]


def placeholder_texture() -> tuple[bytes, bytes]:
    """The game font materials' own texture: 4 x 4 R8G8B8A8, every texel 0 (outside every glyph: nothing is drawn
    through a material whose instance was never pointed at a game atlas)."""
    levels = [bytes(4 * 4 * 4), bytes(2 * 2 * 4), bytes(4)]
    return texture_header(4, 4, len(levels)), b''.join(levels)


def read_game_fonts(data) -> dict:
    """{key: {font main, atlas main, atlas gpu, archive}} of GAME_FONTS from the installed game (read-only)."""
    want = set()
    for _key, _label, _package, _langs, font, atlas in GAME_FONTS:
        want |= {(font, FONT_TYPE), (atlas, TEXTURE_TYPE)}
    found = data.find(want)
    out = {}
    for key, _label, package, _langs, font, atlas in GAME_FONTS:
        if (font, FONT_TYPE) not in found or (atlas, TEXTURE_TYPE) not in found:
            raise ValueError('the installed game lacks the %s font or its atlas' % key)
        archive, main, _s, _g = found[(font, FONT_TYPE)]
        t_archive, t_main, _ts, t_gpu = found[(atlas, TEXTURE_TYPE)]
        if archive != '%016x' % package or t_archive != archive:
            raise ValueError('the %s font is no longer in its language package %016x' % (key, package))
        out[key] = {'font': data.read(archive, main), 'atlasMain': data.read(t_archive, t_main),
            'atlasGpu': data.read(t_archive, t_gpu, '.gpu_resources'), 'archive': archive}
    return out


def game_font_metrics(key: str, src: dict) -> dict:
    """One game font's checked metrics: the header, its fit to its atlas, its baseline drop and every advance."""
    header = font_header(src['font'])
    for field, value in GAME_FONT_SHAPE.items():
        if abs(header[field] - value) > 1e-4:
            raise ValueError('the %s font has %s %r, not %r' % (key, field, header[field], value))
    font = parse_font(src['font'])
    rgba = atlas_top_mip(src['atlasMain'], src['atlasGpu'])
    fit = atlas_fit(font, rgba)
    if not fit['size'] or fit['borderInside'] > 0.002 or fit['cellInside'] < 0.05:
        raise ValueError('the %s font does not fit its atlas: %r' % (key, fit))
    placement = baseline_drop(font, rgba)
    return {'header': header, 'fit': fit, 'drop': placement['drop'], 'cap': placement['cap'],
        'advances': {cp: round(rec[6], 3) for cp, rec in sorted(font['glyphs'].items())},
        'kerning': kerning_pairs(src['font'])}


def kerning_pairs(main: bytes) -> dict:
    """A font resource's kerning pairs {(previous, codepoint): font units}: +0x4C their count, +0x50 the offset of the
    keys (u64, the previous codepoint in the high half: exe 0x173250 builds (edx << 32) | r8d, r8d the codepoint the
    glyph lookup 0x173310 searches) followed by the values (f32). The engine adds the value to the glyph's position and
    to the pen advance (0x173485..0x1734A1)."""
    n, at = struct.unpack_from('<2I', main, 0x4C)
    if not n:
        return {}
    if at + 12 * n > len(main):
        raise ValueError('the kerning table runs past the font resource')
    keys = struct.unpack_from('<%dQ' % n, main, at)
    values = struct.unpack_from('<%df' % n, main, at + 8 * n)
    return {(k >> 32, k & 0xFFFFFFFF): round(v, 6) for k, v in zip(keys, values)}


def game_fonts(folder=None) -> dict:
    """{'ttf': {role: bytes}, 'monaco_material': bytes} from the installed game (read-only)."""
    try:
        import hd2_game_data
    except ImportError:
        from tools import hd2_game_data
    data = hd2_game_data.Data(folder) if folder else hd2_game_data.Data()
    want = {(h, TTF_TYPE) for h in SOURCES.values()} | {(MONACO, MATERIAL_TYPE)}
    found = data.find(want)
    if len(found) != len(want):
        raise ValueError('the installed game lacks the FS Sinclair fonts or the monaco font material')
    out = {'ttf': {}}
    for role, h in SOURCES.items():
        archive, main, _s, _g = found[(h, TTF_TYPE)]
        out['ttf'][role] = ttf_of(data.read(archive, main))
    archive, main, _s, _g = found[(MONACO, MATERIAL_TYPE)]
    out['monaco_material'] = data.read(archive, main)
    return out
