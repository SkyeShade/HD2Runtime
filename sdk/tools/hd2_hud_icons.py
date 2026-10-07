"""The game's own HUD icons of stratagems and boosters, extracted locally from the installed game (read-only).

    py sdk/tools/hd2_hud_icons.py OUT_DIR [--game DATA_FOLDER] [--kind stratagem|booster|all]

writes OUT_DIR/stratagem/<name>.png, OUT_DIR/booster/<name>.png and OUT_DIR/index.json. From Python:

    icons = HudIcons()                          # reads every archive's resource table once (~10 s)
    width, height, rgba = icons.icon('stratagem', '40-K Meltagun')
    write_png('meltagun.png', width, height, rgba)

sdk/HudIconSprites.json names each item's sprite (StratagemInfo +0xB0 for a stratagem, the native Booster table
+0x20 for a booster; scripts/generate_hud_icons.py). A sprite is a 40-byte record in one of the game's texture_atlas
resources: u64 sprite name, u64 page texture name, u32 width and height in pixels, f32 u0, v0, du, dv. The page is
a `texture` resource in the same archive: a 0xC0-byte header, then a DDS header with the DX10 extension in the main
part and the pixels (mip 0 first) in the .gpu_resources part. Only the sprite's own blocks are decoded.

Stratagem sprites are icon masks, the convention of the Runtime's mod images (R the category colour layer, G the
white layer, black empty); booster sprites are colour images with alpha. Standard library only: BC1, BC3, BC4 and
uncompressed 8-bit RGBA / BGRA pages (every format a stratagem or booster sprite uses in build F5FEE03DCFDB).

The artwork is Arrowhead's: extract it for your own builds; publish it only if you may redistribute it.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hd2_image  # noqa: E402
SPRITES = HERE.parent / 'HudIconSprites.json'
TEXTURE = 0xCD4238C6A0C69E32                 # murmur64('texture')
TEXTURE_ATLAS = 0x9199BB50B6896F02           # murmur64('texture_atlas')
RECORD = struct.Struct('<QQII4f')
TEXTURE_HEADER = 0xC0
# DXGI format -> (kind, bytes per 4x4 block or per pixel)
FORMATS = {71: ('bc1', 8), 72: ('bc1', 8), 77: ('bc3', 16), 78: ('bc3', 16), 80: ('bc4', 8),
           28: ('rgba', 4), 29: ('rgba', 4), 87: ('bgra', 4), 91: ('bgra', 4)}


# ------------------------------------------------------------------------------------------------ atlases --
def parse_atlas(raw: bytes) -> list[tuple]:
    """Every sprite record of a texture_atlas resource's main part."""
    if len(raw) < 4:
        raise ValueError('texture atlas too short')
    count = struct.unpack_from('<I', raw)[0]
    if 4 + RECORD.size * count > len(raw):
        raise ValueError('texture atlas holds fewer records than it declares')
    return [RECORD.unpack_from(raw, 4 + RECORD.size * i) for i in range(count)]


def parse_texture(main: bytes) -> dict:
    """The page layout from a texture's main part: width, height, DXGI format."""
    dds = main[TEXTURE_HEADER:]
    if dds[:4] != b'DDS ' or len(dds) < 148:
        raise ValueError('not a DDS texture')
    height, width = struct.unpack_from('<II', dds, 12)
    if dds[84:88] != b'DX10':
        raise ValueError('only DX10 DDS headers are read')
    fmt = struct.unpack_from('<I', dds, 128)[0]
    if fmt not in FORMATS:
        raise ValueError('unsupported texture format DXGI %d' % fmt)
    return {'width': width, 'height': height, 'format': fmt}


def _565(c):
    r, g, b = c >> 11 & 31, c >> 5 & 63, c & 31
    return r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2


def _colour_block(block, offset, four):
    c0, c1, bits = struct.unpack_from('<HHI', block, offset)
    a, b = _565(c0), _565(c1)
    if four or c0 > c1:
        palette = [a + (255,), b + (255,), tuple((2 * x + y) // 3 for x, y in zip(a, b)) + (255,),
                   tuple((x + 2 * y) // 3 for x, y in zip(a, b)) + (255,)]
    else:
        palette = [a + (255,), b + (255,), tuple((x + y) // 2 for x, y in zip(a, b)) + (255,), (0, 0, 0, 0)]
    return [palette[(bits >> (2 * i)) & 3] for i in range(16)]


def _alpha_block(block, offset):
    a0, a1 = block[offset], block[offset + 1]
    bits = int.from_bytes(block[offset + 2:offset + 8], 'little')
    if a0 > a1:
        palette = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    else:
        palette = [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
    return [palette[(bits >> (3 * i)) & 7] for i in range(16)]


def decode(pixels: bytes, page: dict, x: int, y: int, w: int, h: int) -> bytes:
    """RGBA bytes of the w x h rectangle at (x, y) of a page's mip 0."""
    kind, size = FORMATS[page['format']]
    width = page['width']
    if x < 0 or y < 0 or x + w > width or y + h > page['height']:
        raise ValueError('sprite outside its page')
    out = bytearray(w * h * 4)
    if kind in ('rgba', 'bgra'):
        for row in range(h):
            start = ((y + row) * width + x) * 4
            line = pixels[start:start + w * 4]
            if kind == 'bgra':
                line = bytes(b for i in range(0, len(line), 4) for b in (line[i + 2], line[i + 1], line[i], line[i + 3]))
            out[row * w * 4:(row + 1) * w * 4] = line
        return bytes(out)
    blocks_wide = (width + 3) // 4
    for by in range(y // 4, (y + h + 3) // 4):
        for bx in range(x // 4, (x + w + 3) // 4):
            offset = (by * blocks_wide + bx) * size
            block = pixels[offset:offset + size]
            if len(block) != size:
                raise ValueError('texture pixels end early')
            if kind == 'bc1':
                texels = _colour_block(block, 0, False)
            elif kind == 'bc3':
                alpha = _alpha_block(block, 0)
                texels = [c[:3] + (a,) for c, a in zip(_colour_block(block, 8, True), alpha)]
            else:
                texels = [(v, v, v, 255) for v in _alpha_block(block, 0)]
            for i, texel in enumerate(texels):
                px, py = bx * 4 + i % 4 - x, by * 4 + i // 4 - y
                if 0 <= px < w and 0 <= py < h:
                    o = (py * w + px) * 4
                    out[o:o + 4] = bytes(texel)
    return bytes(out)


def write_png(path, width: int, height: int, rgba: bytes) -> None:
    """An 8-bit RGBA PNG (hd2_image.write_png)."""
    Path(path).write_bytes(hd2_image.write_png(width, height, rgba))


# ---------------------------------------------------------------------------------------------- the game --
class HudIcons:
    """Sprites of the installed game's texture atlases, by sprite name or by stratagem / booster name."""

    def __init__(self, data=None, sprites=None):
        if data is None:
            import hd2_game_data
            data = hd2_game_data.Data()
        self.data = data
        self.names = sprites if sprites is not None else json.loads(SPRITES.read_text(encoding='utf-8'))
        self.records, self.textures, self.pages = {}, {}, {}
        for archive, name, kind, main, _stream, gpu in data.tables():
            if kind == TEXTURE:
                self.textures.setdefault(name, (archive, main, gpu))
            elif kind == TEXTURE_ATLAS:
                for record in parse_atlas(data.read(archive, main)):
                    self.records.setdefault(record[0], (name, record))

    def page(self, name):
        if name not in self.pages:
            if name not in self.textures:
                raise KeyError('atlas page texture 0x%016X is not in the game data' % name)
            archive, main, gpu = self.textures[name]
            layout = parse_texture(self.data.read(archive, main))
            self.pages[name] = (layout, self.data.read(archive, gpu, '.gpu_resources'))
        return self.pages[name]

    def sprite(self, name: int):
        """(width, height, rgba) of a sprite by name, or None when no atlas has it."""
        hit = self.records.get(name)
        if not hit:
            return None
        _atlas, (_n, page_name, w, h, u0, v0, du, dv) = hit
        layout, pixels = self.page(page_name)
        x, y = round(u0 * layout['width']), round(v0 * layout['height'])
        if abs(u0 * layout['width'] - x) > 0.01 or abs(v0 * layout['height'] - y) > 0.01 \
                or abs(du * layout['width'] - w) > 0.5 or abs(dv * layout['height'] - h) > 0.5:
            raise ValueError('sprite 0x%016X is not a whole-pixel rectangle of its page' % name)
        return w, h, decode(pixels, layout, x, y, w, h)

    def items(self, kind: str) -> dict:
        """{item name: sprite name} for 'stratagem' or 'booster'."""
        return {name: int(entry['sprite'], 16) for name, entry in self.names[kind + 's'].items()}

    def icon(self, kind: str, name: str):
        """(width, height, rgba) of a stratagem's or booster's HUD icon, or None."""
        sprite = self.items(kind).get(name)
        return self.sprite(sprite) if sprite is not None else None


def safe(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', name).strip('_')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('out', help='output folder')
    parser.add_argument('--game', help='the Helldivers 2 data folder (default: the Steam install)')
    parser.add_argument('--kind', choices=('stratagem', 'booster', 'all'), default='all')
    args = parser.parse_args(argv)
    data = None
    if args.game:
        import hd2_game_data
        data = hd2_game_data.Data(args.game)
    icons = HudIcons(data)
    out = Path(args.out)
    index = {'build': icons.names['build'], 'stratagem': {}, 'booster': {}, 'missing': dict(icons.names['missing'])}
    for kind in (('stratagem', 'booster') if args.kind == 'all' else (args.kind,)):
        (out / kind).mkdir(parents=True, exist_ok=True)
        for name, sprite in sorted(icons.items(kind).items()):
            got = icons.sprite(sprite)
            if got is None:
                index['missing'][name] = 'sprite 0x%016X is in no texture atlas of this game build' % sprite
                continue
            file = kind + '/' + safe(name) + '.png'
            write_png(out / file, *got)
            index[kind][name] = {'file': file, 'width': got[0], 'height': got[1]}
    (out / 'index.json').write_text(json.dumps(index, indent=1) + '\n', encoding='utf-8')
    print('%d stratagem and %d booster icons -> %s (missing: %s)' % (len(index['stratagem']), len(index['booster']),
          out, ', '.join(sorted(index['missing'])) or 'none'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
