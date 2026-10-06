"""Prepare this proof's icon image from a source picture (development; run once, the PNG is committed with the proof).
Standard library only.

    py proof/CustomStratagemPanelProof/prepare_icons.py <source.png> <image id> [--mask] [--out <images folder>]

The source (any square, 8-bit, non-interlaced PNG, at least 256 x 256) becomes images/<image id>.png at the 256 x 256
the custom image format requires: each output pixel is the exact area average of the source pixels it covers, so any
source size works (0.2.0: orbital_gas_barrage.png, 1254 x 1254, as orbital_gas_barrage).

--mask (used by 0.1.0's gas_barrage_mask, kept for rollback in legacy-images/) writes the picture in the vanilla icon
convention instead (docs/custom-images.md; the game's own icons are red and green masks on black): each source pixel is
split into its share of three colours, dark (empty), salmon (red: the category-coloured part) and cream (green: the
white part), by least squares (sdk/tools/hd2_image.py icon_mask_shares), then reduced the same way. --out writes into
another proof's images folder (PanelIconProof: orbital_gas_barrage_masks).

The image is this proof's own, built by `py scripts/build_custom_projectile_proof.py`; it is never a vanilla resource.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'sdk'))
from tools.hd2_image import icon_mask_shares, read_png, valid_image_id  # noqa: E402

SIZE = 256


def png(width: int, height: int, rgb: bytes) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF)
    raw = b''.join(b'\0' + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def spans(source: int):
    """For each output index, the source indices it covers with their weights (exact area average)."""
    scale = source / SIZE
    out = []
    for i in range(SIZE):
        lo, hi = i * scale, (i + 1) * scale
        cells, k = [], int(lo)
        while k < hi and k < source:
            weight = min(hi, k + 1) - max(lo, k)
            if weight > 1e-12:
                cells.append((k, weight))
            k += 1
        out.append(cells)
    return out


def reduce(source: int, value) -> bytes:
    columns = spans(source)
    out = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            acc, total = [0.0, 0.0, 0.0], 0.0
            for sy, wy in columns[y]:
                for sx, wx in columns[x]:
                    v, w = value(sx, sy), wx * wy
                    for c in range(3):
                        acc[c] += v[c] * w
                    total += w
            out += bytes(min(255, int(a / total + 0.5)) for a in acc)
    return bytes(out)


def main(source: Path, image_id: str, mask: bool, out: Path | None = None) -> None:
    if not valid_image_id(image_id):
        raise SystemExit('invalid image id: ' + image_id)
    width, height, rgba = read_png(source.read_bytes())
    if width != height or width < SIZE:
        raise SystemExit('the source must be square and at least %d px, not %d x %d' % (SIZE, width, height))

    def colour(x, y):
        i = 4 * (y * width + x)
        a = rgba[i + 3] / 255
        return (rgba[i] * a, rgba[i + 1] * a, rgba[i + 2] * a)
    cache = {}

    def masked(x, y):
        c = colour(x, y)
        if c not in cache:
            red, green = icon_mask_shares(c)
            cache[c] = (red * 255, green * 255, 0)
        return cache[c]
    images = out or HERE / 'images'
    images.mkdir(exist_ok=True)
    target = images / (image_id + '.png')
    target.write_bytes(png(SIZE, SIZE, reduce(width, masked if mask else colour)))
    print('wrote', target)


if __name__ == '__main__':
    argv = sys.argv[1:]
    out = None
    if '--out' in argv:
        k = argv.index('--out')
        out = Path(argv[k + 1])
        argv = argv[:k] + argv[k + 2:]
    args = [a for a in argv if a != '--mask']
    if len(args) != 2:
        raise SystemExit(__doc__)
    main(Path(args[0]), args[1], '--mask' in argv, out)
