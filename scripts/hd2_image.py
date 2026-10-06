"""A mod's own icon image as a native Helldivers 2 texture (docs/custom-images.md).

The texture has the layout of the game's own stratagem icon textures (research/image-resources-F5FEE03DCFDB.json):
256 x 256 pixels, BC1 (DXGI_FORMAT_BC1_UNORM) with the full 9-level mip chain, a main part of the icon texture header
followed by a DDS header with the DX10 extension, and the pixel data as the GPU part. Its resource name is the mod's
resource id + '/images/' + the image id: deterministic, local to the mod and never a vanilla name.

PNG input is decoded with the standard library only (8- and 16-bit, every colour type, non-interlaced). Transparent
pixels become black, which the game draws as empty.
"""
from __future__ import annotations

import re
import struct
import zlib

TEXTURE_TYPE = 0xCD4238C6A0C69E32
MATERIAL_TYPE = 0xEAC0B497876ADEDF
ICON_SIZE = 256
ICON_MIPS = 9
BC1_UNORM = 71
# The first word of the vanilla icon textures' header (every stratagem icon texture carries it); the rest of the
# header is the "no streamed mips" form.
ICON_CLASS = 0xFCE7DA44
IMAGE_ID = re.compile(r'[a-z0-9_]{1,64}')
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def valid_image_id(image_id) -> bool:
    return isinstance(image_id, str) and IMAGE_ID.fullmatch(image_id) is not None


def image_name(resource: str, image_id: str) -> str:
    """The texture's resource name: the mod's resource id, then images/<id>."""
    if not valid_image_id(image_id):
        raise ValueError('image id must be 1 to 64 lowercase letters, digits or underscores: %r' % (image_id,))
    return resource + '/images/' + image_id


def read_png(data: bytes) -> tuple[int, int, bytes]:
    """(width, height, RGBA bytes) of a non-interlaced PNG; raises ValueError for anything else."""
    if data[:8] != PNG_SIGNATURE:
        raise ValueError('not a PNG file')
    at, header, palette, alpha, idat = 8, None, None, None, []
    while at + 8 <= len(data):
        length, kind = struct.unpack_from('>I4s', data, at)
        body = data[at + 8:at + 8 + length]
        if len(body) != length:
            raise ValueError('truncated PNG chunk')
        if zlib.crc32(kind + body) != struct.unpack_from('>I', data, at + 8 + length)[0]:
            raise ValueError('PNG chunk checksum mismatch')
        at += 12 + length
        if kind == b'IHDR':
            header = struct.unpack('>IIBBBBB', body)
        elif kind == b'PLTE':
            palette = body
        elif kind == b'tRNS':
            alpha = body
        elif kind == b'IDAT':
            idat.append(body)
        elif kind == b'IEND':
            break
    if not header or not idat:
        raise ValueError('PNG without image data')
    width, height, depth, colour, compression, filtering, interlace = header
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour)
    if channels is None or compression or filtering:
        raise ValueError('unsupported PNG colour type or compression')
    if interlace:
        raise ValueError('interlaced PNGs are not supported; save without interlacing')
    if depth not in ((1, 2, 4, 8) if colour in (0, 3) else (8, 16)) or (colour == 3 and depth == 16):
        raise ValueError('unsupported PNG bit depth %d' % depth)
    if colour == 3 and not palette:
        raise ValueError('palette PNG without a palette')
    raw = zlib.decompress(b''.join(idat))
    bits = channels * depth
    stride, step = (width * bits + 7) // 8, max(1, bits // 8)
    if len(raw) != height * (stride + 1):
        raise ValueError('PNG image data has the wrong size')
    rows, previous = [], bytearray(stride)
    for y in range(height):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if kind == 1:
            for i in range(step, stride):
                line[i] = (line[i] + line[i - step]) & 255
        elif kind == 2:
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 255
        elif kind == 3:
            for i in range(stride):
                line[i] = (line[i] + ((line[i - step] if i >= step else 0) + previous[i]) // 2) & 255
        elif kind == 4:
            for i in range(stride):
                a, b, c = line[i - step] if i >= step else 0, previous[i], previous[i - step] if i >= step else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        elif kind != 0:
            raise ValueError('invalid PNG row filter %d' % kind)
        rows.append(bytes(line))
        previous = line
    out = bytearray()
    for line in rows:
        if depth < 8:
            mask, scale = (1 << depth) - 1, 255 // ((1 << depth) - 1)
            samples = [(line[(x * depth) // 8] >> (8 - depth - (x * depth) % 8)) & mask for x in range(width)]
        elif depth == 16:
            samples = line[::2]
        else:
            samples = line
        for x in range(width):
            if colour == 3:
                index = samples[x]
                if 3 * index + 3 > len(palette):
                    raise ValueError('PNG palette index out of range')
                rgb = palette[3 * index:3 * index + 3]
                out += rgb + bytes([alpha[index] if alpha and index < len(alpha) else 255])
            elif colour == 0:
                g = samples[x] * scale if depth < 8 else samples[x]
                out += bytes((g, g, g, 255))
            elif colour == 4:
                g, a = samples[2 * x], samples[2 * x + 1]
                out += bytes((g, g, g, a))
            elif colour == 2:
                out += bytes(samples[3 * x:3 * x + 3]) + b'\xff'
            else:
                out += bytes(samples[4 * x:4 * x + 4])
    return width, height, bytes(out)


def _over_black(rgba: bytes) -> list[tuple[int, int, int]]:
    return [((rgba[i] * rgba[i + 3] + 127) // 255, (rgba[i + 1] * rgba[i + 3] + 127) // 255,
        (rgba[i + 2] * rgba[i + 3] + 127) // 255) for i in range(0, len(rgba), 4)]


def _565(colour):
    r, g, b = colour
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | (b * 31 + 127) // 255


def _expand(value):
    r, g, b = value >> 11 & 31, value >> 5 & 63, value & 31
    return (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2)


def _block(pixels) -> bytes:
    """One BC1 block (16 RGB pixels): the two most distant colours as endpoints, four-colour mode."""
    distinct = list(dict.fromkeys(pixels))
    if len(distinct) == 1:
        return struct.pack('<HHI', _565(distinct[0]), _565(distinct[0]), 0)
    best, ends = -1, (pixels[0], pixels[0])
    for i in range(len(distinct)):
        for j in range(i + 1, len(distinct)):
            a, b = distinct[i], distinct[j]
            d = (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
            if d > best:
                best, ends = d, (a, b)
    c0, c1 = _565(ends[0]), _565(ends[1])
    if c0 == c1:
        return struct.pack('<HHI', c0, c1, 0)
    if c0 < c1:
        c0, c1 = c1, c0
    p0, p1 = _expand(c0), _expand(c1)
    palette = [p0, p1, tuple((2 * x + y + 1) // 3 for x, y in zip(p0, p1)),
        tuple((x + 2 * y + 1) // 3 for x, y in zip(p0, p1))]
    indices = 0
    for k, p in enumerate(pixels):
        nearest = min(range(4), key=lambda n: sum((p[c] - palette[n][c]) ** 2 for c in range(3)))
        indices |= nearest << (2 * k)
    return struct.pack('<HHI', c0, c1, indices)


def _bc1(width, height, pixels) -> bytes:
    out = bytearray()
    for by in range(0, max(height, 4), 4):
        for bx in range(0, max(width, 4), 4):
            out += _block([pixels[min(by + y, height - 1) * width + min(bx + x, width - 1)]
                for y in range(4) for x in range(4)])
    return bytes(out)


def bc1_mips(width: int, height: int, rgba: bytes) -> bytes:
    """The full BC1 mip chain (box-filtered), largest level first."""
    pixels, data = _over_black(rgba), bytearray()
    while True:
        data += _bc1(width, height, pixels)
        if width == 1 and height == 1:
            return bytes(data)
        w, h = max(1, width // 2), max(1, height // 2)
        pixels = [tuple((sum(pixels[min(2 * y + dy, height - 1) * width + min(2 * x + dx, width - 1)][c]
            for dy in (0, 1) for dx in (0, 1)) + 2) // 4 for c in range(3)) for y in range(h) for x in range(w)]
        width, height = w, h


def texture_main(width: int, height: int, mips: int, dxgi: int = BC1_UNORM) -> bytes:
    """The texture's main part: the icon texture header, then the DDS header with the DX10 extension."""
    header = struct.pack('<4I', ICON_CLASS, 0, 0xFFFFFFFF, 0).ljust(0xC0, b'\0')
    dds = struct.pack('<7I', 124, 0x21007, height, width, 0, 0, mips) + bytes(44) \
        + struct.pack('<8I', 32, 4, 0x30315844, 0, 0, 0, 0, 0) + struct.pack('<5I', 0x401008, 0, 0, 0, 0)
    return header + b'DDS ' + dds + struct.pack('<5I', dxgi, 3, 0, 1, 0)


def icon_pixels(png: bytes) -> bytes:
    """The RGBA pixels of a 256 x 256 PNG icon; raises ValueError for any other image."""
    width, height, rgba = read_png(png)
    if (width, height) != (ICON_SIZE, ICON_SIZE):
        raise ValueError('icon images must be %d x %d pixels (this one is %d x %d)' % (ICON_SIZE, ICON_SIZE,
            width, height))
    return rgba


# Automatic stratagem-mask preparation (docs/custom-images.md, "Editable source images"). The build compiles an
# editable PNG into the icon family. A PNG drawn in the game's icon mask convention (opaque, R and G art on black, no
# pixel with a blue above MASK_BLUE_MAX: an edited mask may keep a few bluish edge pixels) is used exactly as given.
# Any other picture (red-and-white art has white areas, blue near 240, or transparency) is read as a red-and-white icon
# on a dark or transparent background and converted to the masks (icon_masks below). An image a project declares raw
# is used as given whatever it holds. MASKS_CONVERTER names this rule: the build's cache of compiled textures is keyed
# by it and by the source PNG's SHA-256, so a changed rule or a changed PNG compiles again.
MASKS_CONVERTER = 'icon-masks-2'
MASK_BLUE_MAX = 128
PREPARATIONS = ('auto', 'raw')


def is_icon_masks(rgba: bytes) -> bool:
    """Whether RGBA pixels are drawn in the icon mask convention: A = 255 everywhere and no B above MASK_BLUE_MAX."""
    return max(rgba[2::4], default=0) <= MASK_BLUE_MAX and rgba[3::4] == b'\xff' * (len(rgba) // 4)


def prepare_icon(png: bytes, mode: str = 'auto') -> tuple[bytes, str]:
    """(RGBA pixels, what was done) of a 256 x 256 PNG icon. mode 'auto': masks as given, any other picture
    converted to masks; 'raw': as given. Raises ValueError for any other image or mode."""
    if mode not in PREPARATIONS:
        raise ValueError('an image is prepared auto or raw, not %r' % (mode,))
    rgba = icon_pixels(png)
    if mode == 'raw':
        return rgba, 'raw (as given)'
    if is_icon_masks(rgba):
        return rgba, 'masks (as given)'
    return icon_masks(rgba), 'converted to masks'


def icon_texture(png: bytes, mode: str = 'raw') -> tuple[bytes, bytes]:
    """(main part, GPU part) of a 256 x 256 PNG icon; raises ValueError for any other image. mode: 'raw' (default:
    the pixels as given) or 'auto' (prepare_icon: masks as given, any other picture converted to masks)."""
    rgba, _ = prepare_icon(png, mode)
    return texture_main(ICON_SIZE, ICON_SIZE, ICON_MIPS), bc1_mips(ICON_SIZE, ICON_SIZE, rgba)


ICON_SHADER = 0x3461FF0D
IMAGE_SLOT = 0x3AA8B87E


def icon_material(name_hash: int) -> bytes:
    """The GUI icon material of a stratagem icon named `name_hash` (research/stratagem-icon-family-F5FEE03DCFDB.json):
    the vanilla icon material, whose one slot (the widget image property) names the icon's own texture. Header {0x120,
    kind 1 (one material, usable by GUIs), body at 0x18, 0x7C}; body: no parent, one slot, shader 0x3461FF0D; the slot
    id at +0x88 and the slot texture name at +0x8C. Every vanilla icon material is exactly these bytes for its name."""
    data = bytearray(160)
    struct.pack_into('<IIII', data, 0, 0x120, 1, 0x18, 0x7C)
    struct.pack_into('<I', data, 0x18 + 0x28, 1)
    struct.pack_into('<I', data, 0x18 + 0x68, ICON_SHADER)
    struct.pack_into('<IQ', data, 0x88, IMAGE_SLOT, name_hash)
    return bytes(data)


def icon_family(png: bytes, name_hash: int, mode: str = 'raw') -> dict[int, tuple[bytes, bytes]]:
    """{resource type: (main part, GPU part)} of a custom icon named `name_hash`: its texture and its GUI material (no
    atlas sprite; research/stratagem-icon-family-F5FEE03DCFDB.json). mode: as icon_texture."""
    return {TEXTURE_TYPE: icon_texture(png, mode), MATERIAL_TYPE: (icon_material(name_hash), b'')}


# The game's stratagem icon convention (research iconShader; the vanilla icon textures): the icon shader treats the
# texture's channels as masks, each coloured by a material variable the UI sets: R = the category-coloured artwork (c0,
# e.g. the orbital red), G = the white artwork (c1), B = a shadow (c2; unused by the stratagem icons), A opaque; a
# background of 0 in every channel draws transparent. A full-colour picture drawn through that shader lights the red
# mask in its white areas too (R over G), so it must be converted. The reference colours of a red-and-white icon on a
# dark background: dark (empty), red (the R mask), white (the G mask).
ICON_MASK_DARK, ICON_MASK_RED, ICON_MASK_WHITE = (25, 3, 1), (220, 100, 85), (255, 255, 238)


def icon_mask_shares(pixel, dark=ICON_MASK_DARK, red=ICON_MASK_RED, white=ICON_MASK_WHITE) -> tuple[float, float]:
    """(red, white) shares of an RGB pixel over the dark colour: least squares against the red and white reference
    colours, each clamped to [0, 1] and scaled down together when they add up to more than 1. A channel darker than the
    dark colour counts as the dark colour (black is background too)."""
    p = [max(0, pixel[c] - dark[c]) for c in range(3)]
    s = [red[c] - dark[c] for c in range(3)]
    k = [white[c] - dark[c] for c in range(3)]
    ss, kk, sk = sum(x * x for x in s), sum(x * x for x in k), sum(a * b for a, b in zip(s, k))
    ps, pk = sum(a * b for a, b in zip(p, s)), sum(a * b for a, b in zip(p, k))
    det = ss * kk - sk * sk
    if det == 0:
        raise ValueError('the red and white reference colours must differ')
    a, b = min(1.0, max(0.0, (ps * kk - pk * sk) / det)), min(1.0, max(0.0, (pk * ss - ps * sk) / det))
    if a + b > 1:
        a, b = a / (a + b), b / (a + b)
    return a, b


def icon_masks(rgba: bytes, dark=ICON_MASK_DARK, red=ICON_MASK_RED, white=ICON_MASK_WHITE) -> bytes:
    """A red-and-white icon picture (RGBA; transparent pixels count as dark) as the game's icon masks: R = its red
    share, G = its white share, B = 0, A = 255 (the vanilla convention). The source picture is not changed."""
    out = bytearray()
    cache = {}
    for (r, g, b), alpha in zip(_over_black(rgba), rgba[3::4]):
        key = (r, g, b)
        if key not in cache:
            a, w = icon_mask_shares(key, dark, red, white)
            cache[key] = bytes((int(a * 255 + 0.5), int(w * 255 + 0.5), 0, 255))
        out += cache[key]
    return bytes(out)


def write_png(width: int, height: int, rgba: bytes) -> bytes:
    """An RGBA PNG (filter 0), for generated development images and tests."""
    raw = b''.join(b'\0' + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    return PNG_SIGNATURE + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) \
        + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
