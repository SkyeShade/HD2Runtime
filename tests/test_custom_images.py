"""Runtime-owned custom images (docs/custom-images.md): a mod's own icon family built by the SDK into the mod's archive,
hd2.resources.image(id), and hd2.fields.stratagem.presentation_icon writing it only when the complete family is loaded
(live-proven by CustomStratagemP0Proof 0.11.0; a texture alone crashed the 0.9.0 test,
research/stratagem-icon-consumers-F5FEE03DCFDB.json). Offline: the build side runs in Python, the Runtime side on the
offline event world with the game's resource-manager layout. Nothing here touches a game process."""
import hashlib
import json
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from support import ROOT, run
from test_stratagem_presentation import WORLD, PUBLIC

sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'sdk'))
import hd2_archive  # noqa: E402
import hd2_image  # noqa: E402

RESEARCH = json.loads((ROOT / 'research/image-resources-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
SIZE = hd2_image.ICON_SIZE


def icon_pixels(kind='disc'):
    """A red disc in a green ring on black (the mask convention of the game's icons)."""
    out = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            d = ((x - 128) ** 2 + (y - 128) ** 2) ** 0.5
            if kind == 'disc':
                out += bytes((255 if d < 80 else 0, 255 if 92 < d < 112 else 0, 0, 255))
            else:
                out += bytes((255 if (x // 32 + y // 32) % 2 else 0, 0, 0, 255))
    return bytes(out)


def png(width, height, rows, colour, depth, palette=None, filters=(0,), interlace=0, break_crc=False):
    """A PNG from raw scanlines (bytes per row, unfiltered), each row filtered with filters[row % len(filters)]."""
    bpp = max(1, {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour] * depth // 8)
    raw, previous = bytearray(), bytes(len(rows[0]))
    for index, line in enumerate(rows):
        kind = filters[index % len(filters)]
        out = bytearray()
        for i, value in enumerate(line):
            a = line[i - bpp] if i >= bpp else 0
            b, c = previous[i], previous[i - bpp] if i >= bpp else 0
            if kind == 1:
                value -= a
            elif kind == 2:
                value -= b
            elif kind == 3:
                value -= (a + b) // 2
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                value -= a if pa <= pb and pa <= pc else b if pb <= pc else c
            out.append(value & 255)
        raw += bytes((kind,)) + out
        previous = line

    def chunk(kind, body, broken=False):
        crc = zlib.crc32(kind + body) ^ (1 if broken else 0)
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', crc)
    body = hd2_image.PNG_SIGNATURE + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, colour, 0, 0,
        interlace), break_crc)
    if palette:
        body += chunk(b'PLTE', palette)
    return body + chunk(b'IDAT', zlib.compress(bytes(raw))) + chunk(b'IEND', b'')


def bc1_texel(gpu, x, y):
    """The colour BC1 mip 0 decodes to at (x, y)."""
    block = struct.unpack_from('<HHI', gpu, ((y // 4) * (SIZE // 4) + x // 4) * 8)
    c0, c1, bits = block
    p0, p1 = hd2_image._expand(c0), hd2_image._expand(c1)
    index = bits >> (2 * ((y % 4) * 4 + x % 4)) & 3
    if c0 > c1:
        palette = [p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)), tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))]
    else:
        palette = [p0, p1, tuple((a + b) // 2 for a, b in zip(p0, p1)), (0, 0, 0)]
    return palette[index]


class IdentityTests(unittest.TestCase):
    def test_the_name_is_deterministic_mod_local_and_the_runtime_derives_the_same_hash(self):
        name = hd2_image.image_name('mods/skyeshade/hd2runtime_custom_stratagem_p0_proof', 'orbital_gas_barrage_icon')
        self.assertEqual(name, 'mods/skyeshade/hd2runtime_custom_stratagem_p0_proof/images/orbital_gas_barrage_icon')
        self.assertEqual('0x%016X' % hd2_archive.resource_hash(name), RESEARCH['proofImage']['hash'])
        # The same image id in two mods: two different textures.
        other = hd2_image.image_name('mods/someone/other_mod', 'orbital_gas_barrage_icon')
        self.assertNotEqual(hd2_archive.resource_hash(name), hd2_archive.resource_hash(other))
        names = [name, other, 'mods/a/b/images/x', 'mods/a/b/images/' + 'y' * 64, 'mods/a/b']
        got = run("local images=require('hd2runtime/runtime/image_resources')\nlocal out={}\n" + ''.join(
            "do local h,l=images.hash(%s);out[#out+1]=string.format('%%08X%%08X',h,l)end\n" % json.dumps(n)
            for n in names) + "return table.concat(out,',')").decode().split(',')
        self.assertEqual(got, ['%016X' % hd2_archive.resource_hash(n) for n in names])

    def test_image_ids(self):
        for good in ('a', 'orbital_gas_barrage_icon', 'x' * 64, 'icon_2'):
            self.assertTrue(hd2_image.valid_image_id(good), good)
        for bad in ('', 'Icon', 'x' * 65, 'a-b', 'a/b', 'a.png', ' a', None, 3):
            self.assertFalse(hd2_image.valid_image_id(bad), bad)
            if isinstance(bad, str):
                with self.assertRaises(ValueError):
                    hd2_image.image_name('mods/a/b', bad)


class TextureTests(unittest.TestCase):
    def test_the_main_part_is_the_vanilla_icon_textures_main_part(self):
        main, gpu = hd2_image.icon_texture(hd2_image.write_png(SIZE, SIZE, icon_pixels()))
        reference = RESEARCH['texture']['reference']
        self.assertEqual(hashlib.sha256(main).hexdigest().upper(), reference['mainSha256'])
        self.assertGreater(reference['iconClassTexturesWithThisMainPart'], 100)
        self.assertEqual((len(main), len(gpu)), (RESEARCH['texture']['mainBytes'], RESEARCH['texture']['gpuBytes']))
        dds = struct.unpack_from('<7I', main, 0xC4)
        self.assertEqual((main[0xC0:0xC4], dds[2], dds[3], dds[6]), (b'DDS ', SIZE, SIZE, hd2_image.ICON_MIPS))
        self.assertEqual(struct.unpack_from('<I', main, 0x140)[0], hd2_image.BC1_UNORM)

    def test_the_pixels_survive_bc1_and_every_mip_is_present(self):
        _, gpu = hd2_image.icon_texture(hd2_image.write_png(SIZE, SIZE, icon_pixels()))
        self.assertEqual(bc1_texel(gpu, 128, 128), (255, 0, 0))        # the red disc
        self.assertEqual(bc1_texel(gpu, 128, 128 + 100), (0, 255, 0))  # the green ring
        self.assertEqual(bc1_texel(gpu, 2, 2), (0, 0, 0))              # the empty background
        sizes = [max(1, (SIZE >> level) // 4) ** 2 * 8 for level in range(hd2_image.ICON_MIPS)]
        self.assertEqual(len(gpu), sum(sizes))
        # The 1 x 1 mip is the average colour: dark, with some red.
        last = struct.unpack_from('<HHI', gpu, len(gpu) - 8)
        self.assertTrue(0 < hd2_image._expand(last[0])[0] < 255)
        # Transparent pixels are black (empty), whatever their colour.
        clear = hd2_image.write_png(SIZE, SIZE, bytes((255, 255, 255, 0)) * SIZE * SIZE)
        self.assertEqual(bc1_texel(hd2_image.icon_texture(clear)[1], 7, 7), (0, 0, 0))
        self.assertEqual(hd2_image.icon_texture(hd2_image.write_png(SIZE, SIZE, icon_pixels())),
            hd2_image.icon_texture(hd2_image.write_png(SIZE, SIZE, icon_pixels())))   # deterministic

    def test_png_colour_types_bit_depths_and_filters_decode_alike(self):
        width = 8
        grey = [bytes((x * 30 + y) & 255 for x in range(width)) for y in range(4)]
        reference = hd2_image.read_png(png(width, 4, grey, 0, 8))[2]
        for filters in ((1,), (2,), (3,), (4,), (0, 1, 2, 3, 4)):
            self.assertEqual(hd2_image.read_png(png(width, 4, grey, 0, 8, filters=filters))[2], reference, filters)
        rgb = [bytes(v for x in range(width) for v in (x * 30, y * 50, 7)) for y in range(4)]
        rgba16 = [bytes(v for x in range(width) for c in (x * 30, y * 50, 7, 255) for v in (c, 0x55)) for y in range(4)]
        self.assertEqual(hd2_image.read_png(png(width, 4, rgb, 2, 8, filters=(4,)))[2],
            hd2_image.read_png(png(width, 4, rgba16, 6, 16, filters=(3,)))[2])
        # A 2-bit palette.
        palette = bytes((0, 0, 0, 255, 0, 0, 0, 255, 0, 9, 9, 9))
        packed = [bytes((0b00011011, 0b00011011)) for _ in range(4)]      # indices 0, 1, 2, 3, 0, 1, 2, 3
        decoded = hd2_image.read_png(png(width, 4, packed, 3, 2, palette=palette))[2]
        self.assertEqual(decoded[:16], bytes((0, 0, 0, 255, 255, 0, 0, 255, 0, 255, 0, 255, 9, 9, 9, 255)))

    def test_invalid_images_are_refused(self):
        line = [bytes(SIZE * 4)] * SIZE
        cases = {
            'not a PNG file': b'GIF89a' + bytes(100),
            'must be 256 x 256': hd2_image.write_png(128, 128, bytes(128 * 128 * 4)),
            'interlaced': png(SIZE, SIZE, line, 6, 8, interlace=1),
            'checksum': png(SIZE, SIZE, line, 6, 8, break_crc=True),
            'bit depth': png(4, 4, [bytes(8)] * 4, 3, 16, palette=bytes(3)),
            'without a palette': png(4, 4, [bytes(4)] * 4, 3, 8),
        }
        for reason, data in cases.items():
            with self.assertRaises(ValueError) as caught:
                hd2_image.icon_texture(data)
            self.assertIn(reason, str(caught.exception))
        broken = bytearray(hd2_image.write_png(SIZE, SIZE, bytes(SIZE * SIZE * 4)))
        with self.assertRaises(Exception):
            hd2_image.icon_texture(bytes(broken[:len(broken) // 2]))


class ArchiveTests(unittest.TestCase):
    def test_vanilla_layout_round_trip_and_lua_only_archives_unchanged(self):
        lua = {hd2_archive.resource_hash('mods/a/b'): hd2_archive.lua_resource(b'return 1'),
            hd2_archive.resource_hash('mods/a/b/c'): hd2_archive.lua_resource(b'return 2' * 40)}
        textures = {hd2_archive.resource_hash(hd2_image.image_name('mods/a/b', i)):
            hd2_image.icon_texture(hd2_image.write_png(SIZE, SIZE, icon_pixels(i))) for i in ('disc', 'checker')}
        resources = {(hd2_archive.LUA_TYPE, k): (v, b'') for k, v in lua.items()}
        resources.update({(hd2_archive.TEXTURE_TYPE, k): v for k, v in textures.items()})
        archive, gpu = hd2_archive.make_resource_archive(resources)
        self.assertEqual(hd2_archive.read_archive(archive, gpu), resources)
        types, files = struct.unpack_from('<II', archive, 4)
        rows = [struct.unpack_from('<7Q6I', archive, 72 + 32 * types + 80 * i) for i in range(files)]
        self.assertEqual([(r[1], r[0]) for r in rows], sorted(resources))
        main_sum = gpu_sum = 0
        for index, row in enumerate(rows):
            self.assertEqual((row[2] % 16, row[4] % 64, row[5], row[6], row[10:]), (0, 0, main_sum, gpu_sum,
                (16, 64, index)))
            main_sum += -(-row[7] // 256) * 256
            gpu_sum += -(-row[9] // 256) * 256
        self.assertEqual(struct.unpack_from('<QQ', archive, 0x20), (main_sum, gpu_sum))
        self.assertEqual(RESEARCH['archiveLayout'][0]['differences'], [])   # the vanilla tables are reproduced
        # Lua-only archives keep make_archive's established layout byte for byte.
        self.assertEqual(hashlib.sha256(hd2_archive.make_archive(lua)).hexdigest()[:16],
            hashlib.sha256(LUA_ONLY_REFERENCE(lua)).hexdigest()[:16])


def LUA_ONLY_REFERENCE(resources):
    """The Lua-only writer as released before custom images (frozen copy)."""
    count = len(resources)
    data_offset = (104 + 80 * count + 15) & ~15
    archive, entries = bytearray(data_offset), bytearray()
    for index, (name_hash, resource) in enumerate(sorted(resources.items())):
        entries.extend(struct.pack('<7Q6I', name_hash, hd2_archive.LUA_TYPE, data_offset, 0, 0, 0, 0,
            len(resource), 0, 0, 16, 16, index))
        archive.extend(resource)
        archive.extend(b'\0' * (-len(archive) % 16))
        data_offset = len(archive)
    header = struct.pack('<III20sQQ24s', 0xF0000011, 1, count, b'', data_offset, 0, b'')
    archive[:104 + len(entries)] = header + struct.pack('<IIQIIII', 0, 0, hd2_archive.LUA_TYPE, count, 0, 16, 16) + entries
    return bytes(archive)


class BuildTests(unittest.TestCase):
    def setUp(self):
        import hd2
        self.hd2 = hd2
        self.folder = Path(tempfile.mkdtemp(dir=ROOT / 'build'))
        self.project = self.folder / 'IconMod'
        (self.project / 'src').mkdir(parents=True)
        (self.project / 'src/addon.lua').write_text("local icon=hd2.resources.image('my_icon')\n", encoding='utf-8')
        (self.project / 'VERSION').write_text('1.0.0\n')
        (self.project / 'README.md').write_text('test\n')
        (self.project / 'hd2runtime.json').write_text(json.dumps({'format': 1, 'name': 'IconMod',
            'resource': 'mods/test/icon_mod', 'guid': '0b7f3c3e-6a51-4b8f-9c35-2a8e1f0d4c11',
            'requires': {'bingus': {'min_release': 15, 'api': 1}, 'hd2runtime': {'min_version': '0.28.0', 'api': 1,
                'module': 'mods/skyeshade/hd2runtime'}}}))

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def built(self):
        with zipfile.ZipFile(self.hd2.build_project(self.project)) as package:
            name = 'mod/' + hd2_archive.ARCHIVE_NAME
            return (package.read(name), package.read(name + '.gpu_resources'), package.read(name + '.stream'),
                json.loads(package.read('build-report.json')))

    def test_without_images_the_build_is_unchanged(self):
        archive, gpu, stream, report = self.built()
        self.assertEqual((gpu, stream), (b'', b''))
        self.assertNotIn('images', report)
        self.assertEqual(struct.unpack_from('<I', archive, 4)[0], 1)   # Lua only, make_archive's layout
        (self.project / 'images').mkdir()
        self.assertEqual(self.built()[0], archive)

    def test_images_become_mod_local_textures_in_the_mod_archive(self):
        (self.project / 'images').mkdir()
        (self.project / 'images/my_icon.png').write_bytes(hd2_image.write_png(SIZE, SIZE, icon_pixels()))
        (self.project / 'images/second.png').write_bytes(hd2_image.write_png(SIZE, SIZE, icon_pixels('checker')))
        archive, gpu, stream, report = self.built()
        found = hd2_archive.read_archive(archive, gpu)
        self.assertEqual(report['images'], ['my_icon', 'second'])
        for image_id, kind in (('my_icon', 'disc'), ('second', 'checker')):
            key = (hd2_archive.TEXTURE_TYPE, hd2_archive.resource_hash('mods/test/icon_mod/images/' + image_id))
            self.assertEqual(found[key], hd2_image.icon_texture(hd2_image.write_png(SIZE, SIZE, icon_pixels(kind))))
        lua = sorted(k for k in found if k[0] == hd2_archive.LUA_TYPE)
        # The addon and the icons' build record (the Runtime logs it at load); nothing else.
        self.assertEqual(lua, sorted([(hd2_archive.LUA_TYPE, hd2_archive.resource_hash('mods/test/icon_mod')),
            (hd2_archive.LUA_TYPE, hd2_archive.resource_hash('mods/test/icon_mod/hd2runtime_images'))]))
        self.assertEqual(stream, b'')
        self.assertNotIn('hash', json.dumps(report).lower())

    def red_and_white(self):
        """A red-and-white icon picture on a dark background (the art a mask is prepared from): not masks."""
        out = bytearray()
        for y in range(SIZE):
            for x in range(SIZE):
                d = ((x - 128) ** 2 + (y - 128) ** 2) ** 0.5
                out += bytes(hd2_image.ICON_MASK_RED if d < 80 else hd2_image.ICON_MASK_WHITE if 92 < d < 112
                    else hd2_image.ICON_MASK_DARK) + b'\xff'
        return bytes(out)

    def texture_of(self, archive, gpu, image_id):
        found = hd2_archive.read_archive(archive, gpu)
        return found[(hd2_archive.TEXTURE_TYPE, hd2_archive.resource_hash('mods/test/icon_mod/images/' + image_id))]

    def test_editable_pngs_ship_beside_the_manifest_and_masks_are_prepared_automatically(self):
        (self.project / 'images').mkdir()
        mask_png = hd2_image.write_png(SIZE, SIZE, icon_pixels())
        art_png = hd2_image.write_png(SIZE, SIZE, self.red_and_white())
        (self.project / 'images/my_icon.png').write_bytes(mask_png)
        (self.project / 'images/art.png').write_bytes(art_png)
        path = self.hd2.build_project(self.project)
        with zipfile.ZipFile(path) as package:
            # The editable sources, byte for byte, outside the installed option folder (mod/).
            self.assertEqual(package.read('images/my_icon.png'), mask_png)
            self.assertEqual(package.read('images/art.png'), art_png)
            self.assertFalse([n for n in package.namelist() if n.startswith('mod/') and n.endswith('.png')])
            name = 'mod/' + hd2_archive.ARCHIVE_NAME
            archive, gpu = package.read(name), package.read(name + '.gpu_resources')
            report = json.loads(package.read('build-report.json'))
        # A mask is compiled exactly as before; the red-and-white art is converted to the game's icon masks.
        self.assertEqual(self.texture_of(archive, gpu, 'my_icon'), hd2_image.icon_texture(mask_png))
        converted = hd2_image.write_png(SIZE, SIZE, hd2_image.icon_masks(self.red_and_white()))
        self.assertEqual(self.texture_of(archive, gpu, 'art'), hd2_image.icon_texture(converted))
        self.assertEqual(hd2_image.icon_masks(self.red_and_white()), icon_pixels())   # its masks: the disc and ring
        self.assertEqual(report['images'], ['art', 'my_icon'])
        self.assertEqual(report['image_sources'], {
            'art': {'file': 'images/art.png', 'source_sha256': hashlib.sha256(art_png).hexdigest(),
                'prepared': 'converted to masks', 'resource': 'mods/test/icon_mod/images/art', 'build': 'compiled'},
            'my_icon': {'file': 'images/my_icon.png', 'source_sha256': hashlib.sha256(mask_png).hexdigest(),
                'prepared': 'masks (as given)', 'resource': 'mods/test/icon_mod/images/my_icon', 'build': 'compiled'}})
        # The archive's build record names the same: the Runtime logs it once per icon at load.
        record = hd2_archive.read_archive(archive, gpu)[(hd2_archive.LUA_TYPE,
            hd2_archive.resource_hash('mods/test/icon_mod/hd2runtime_images'))][0][8:].decode()
        self.assertIn('["my_icon"]={source="images/my_icon.png",sha256="' + hashlib.sha256(mask_png).hexdigest()
            + '",prepared="masks (as given)",build="compiled",resource="mods/test/icon_mod/images/my_icon"}', record)

    def test_an_edited_mask_with_a_few_bluish_pixels_stays_a_mask(self):
        pixels = bytearray(icon_pixels())
        for i in range(0, 4 * 400, 4):
            pixels[i:i + 3] = bytes((1, 20, 25))          # stray dark-teal edge pixels of an edited mask
        rgba, prepared = hd2_image.prepare_icon(hd2_image.write_png(SIZE, SIZE, bytes(pixels)))
        self.assertEqual((rgba, prepared), (bytes(pixels), 'masks (as given)'))
        self.assertEqual(hd2_image.prepare_icon(hd2_image.write_png(SIZE, SIZE, self.red_and_white()))[1],
            'converted to masks')
        self.assertEqual(hd2_image.MASKS_CONVERTER, 'icon-masks-2')

    def test_an_image_declared_raw_is_compiled_as_given(self):
        (self.project / 'images').mkdir()
        art_png = hd2_image.write_png(SIZE, SIZE, self.red_and_white())
        (self.project / 'images/art.png').write_bytes(art_png)
        spec = json.loads((self.project / 'hd2runtime.json').read_text())
        spec['images'] = {'art': 'raw'}
        (self.project / 'hd2runtime.json').write_text(json.dumps(spec))
        archive, gpu, _, report = self.built()
        self.assertEqual(self.texture_of(archive, gpu, 'art'), hd2_image.icon_texture(art_png))
        self.assertEqual(report['image_sources']['art']['prepared'], 'raw (as given)')
        for bad, text in (({'missing': 'raw'}, 'not in images/'), ({'art': 'auto'}, 'can only be declared "raw"'),
                (['art'], 'must be {"<image id>": "raw"}')):
            spec['images'] = bad
            (self.project / 'hd2runtime.json').write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError, text):
                self.hd2.build_project(self.project)

    def test_the_compiled_texture_is_cached_by_the_source_hash_until_the_png_changes(self):
        (self.project / 'images').mkdir()
        first = hd2_image.write_png(SIZE, SIZE, icon_pixels())
        (self.project / 'images/my_icon.png').write_bytes(first)
        spec = json.loads((self.project / 'hd2runtime.json').read_text())
        families, _, cache = self.hd2.project_icon_resources(self.project, spec, record=True)
        self.assertEqual(cache, {'my_icon': 'compiled'})
        def bins():
            return sorted(e.name for e in (self.project / 'build' / self.hd2.IMAGE_CACHE).iterdir()
                if e.suffix == '.bin')
        self.assertEqual(bins(), [hd2_image.MASKS_CONVERTER + '-auto-' + hashlib.sha256(first).hexdigest() + '.bin'])
        again, _, cache = self.hd2.project_icon_resources(self.project, spec, record=True)
        self.assertEqual((again, cache), (families, {'my_icon': 'cache hit'}))
        # The PNG content changes (same file, same image id, same resource): recompiled, a new entry, a new texture.
        second = hd2_image.write_png(SIZE, SIZE, icon_pixels('checker'))
        (self.project / 'images/my_icon.png').write_bytes(second)
        changed, _, cache = self.hd2.project_icon_resources(self.project, spec, record=True)
        self.assertEqual(cache, {'my_icon': 'recompiled: source changed'})
        self.assertNotEqual(changed, families)
        self.assertEqual(len(bins()), 2)
        # A damaged cache entry is never used: compiled again, the same bytes.
        entry = self.project / 'build' / self.hd2.IMAGE_CACHE / (hd2_image.MASKS_CONVERTER + '-auto-'
            + hashlib.sha256(second).hexdigest() + '.bin')
        damaged = bytearray(entry.read_bytes())
        damaged[-1] ^= 0xFF
        entry.write_bytes(bytes(damaged))
        repaired, _, cache = self.hd2.project_icon_resources(self.project, spec, record=True)
        self.assertEqual((repaired, cache), (changed, {'my_icon': 'compiled'}))
        # A whole build after an edit: the archive's texture follows the PNG, and its record says so.
        third = hd2_image.write_png(SIZE, SIZE, self.red_and_white())
        (self.project / 'images/my_icon.png').write_bytes(third)
        archive, gpu, _, report = self.built()
        self.assertEqual(self.texture_of(archive, gpu, 'my_icon'), hd2_image.icon_texture(third, 'auto'))
        self.assertEqual(report['image_sources']['my_icon']['build'], 'recompiled: source changed')

    def test_invalid_image_projects_are_refused(self):
        images = self.project / 'images'
        images.mkdir()
        cases = [('Bad-Name.png', hd2_image.write_png(SIZE, SIZE, bytes(SIZE * SIZE * 4)), 'image id'),
            ('small.png', hd2_image.write_png(64, 64, bytes(64 * 64 * 4)), '256 x 256'),
            ('notes.txt', b'x', 'PNG files only'),
            ('fake.png', b'not a png', 'not a PNG file')]
        for name, data, reason in cases:
            (images / name).write_bytes(data)
            with self.assertRaises(ValueError) as caught:
                self.hd2.build_project(self.project)
            self.assertIn(reason, str(caught.exception))
            (images / name).unlink()
        (images / 'nested').mkdir()
        with self.assertRaises(ValueError):
            self.hd2.build_project(self.project)


# The Runtime side on the offline world (the 120mm row, the Gas Strike donor row and the public fields).
IMAGES = r"""
local images=require('hd2runtime/runtime/image_resources')
local IMG=require('hd2runtime/domains/image_resources')
local api=require('mods/skyeshade/hd2runtime')
images.reset_for_tests()
local MOD='mods/test/icon_mod'
local function image(id,mod)return images.handle(id,mod or MOD)end
local function icon_patch(id,value)
    return op_settle(session.patch{id=id,target=session.stratagem(BIGNAME),field=F.presentation_icon,expect=BIGNAME,
        value=value})
end
local function public_image(id,mod)
    return require('hd2runtime/runtime/events').run_as(mod or MOD,function()return api.resources.image(id)end)
end
"""


def images(body):
    return run(WORLD + PUBLIC + IMAGES + body)


class RuntimeImageTests(unittest.TestCase):
    """hd2.resources.image(id) and what presentation_icon accepts at registration."""

    def check(self, body):
        self.assertEqual(images(body), b'ok')

    def test_the_public_image_handle_is_the_calling_mods_own(self):
        self.check(r'''
local icon=public_image('orbital_gas_barrage_icon')
assert(images.issued(icon)and icon==image('orbital_gas_barrage_icon'))       -- one handle per mod and id
assert(public_image('orbital_gas_barrage_icon','mods/other/mod')~=icon)     -- another mod's id is another image
local d=icon:describe()
assert(d.kind=='image'and d.id=='orbital_gas_barrage_icon'and d.mod==MOD)
for key in pairs(icon)do assert(key=='resource'or key=='image'or key=='mod',key)end   -- no hash, no name
assert(tostring(icon)=="image 'orbital_gas_barrage_icon' of "..MOD)
-- Ids are validated; outside a mod there is no owner.
for _,bad in ipairs({'','Icon','a-b','a/b',string.rep('x',65)})do assert(not pcall(public_image,bad),bad)end
local ok,why=pcall(api.resources.image,'x')
assert(not ok and tostring(why):find('must be called by a mod',1,true),tostring(why))
-- The builder constants are still there.
assert(api.resources.bastion=='bastion'and api.resources.amr=='amr')
assert(writes()==0)
return 'ok'
''')

    def test_presentation_icon_accepts_an_image_and_the_text_fields_refuse_it(self):
        self.check(r'''
local icon=public_image('orbital_gas_barrage_icon')
local validate=require('hd2runtime/domains/patches').validate
-- Registration does not read the game: the family is checked before the write.
local ok,why=pcall(validate,{id='a',target=session.stratagem(BIGNAME),field=F.presentation_icon,expect=BIGNAME,value=icon})
assert(ok,tostring(why))
rejects({id='b',target=session.stratagem(BIGNAME),field=F.presentation_name,expect=BIGNAME,value=icon},
    'a custom image is a presentation_icon value only')
rejects({id='c',target=session.stratagem(BIGNAME),field=F.presentation_description,expect=BIGNAME,value=icon},
    'a custom image is a presentation_icon value only')
rejects({id='d',target=session.stratagem(BIGNAME),field=F.presentation_icon,expect=icon,value=BIGNAME},
    'expect must be the stratagem itself')
-- A table that only looks like an image is not one.
rejects({id='e',target=session.stratagem(BIGNAME),field=F.presentation_icon,expect=BIGNAME,
    value={resource='image',image='x',mod=MOD}},'or hd2.resources.image(id)')
assert(writes()==0 and#changed()==0)
return 'ok'
''')

    def test_the_texture_residency_reader_reads_the_game_layout(self):
        # Development infrastructure kept for a future material-backed icon: the reader itself, never a write path.
        self.check(r'''
local icon=image('orbital_gas_barrage_icon')
-- No resource manager yet: not ready.
local ok,why=pcall(images.resident,W.runtime,icon)
assert(not ok and tostring(why):find('TARGET_UNAVAILABLE',1,true),tostring(why))
local textures=W.textures({images.name(MOD,'orbital_gas_barrage_icon'),images.name(MOD,'second')})
assert(images.resident(W.runtime,icon)==true and images.resident(W.runtime,image('second'))==true)
assert(images.resident_name(W.runtime,'core/fallback_resources/missing_texture')==true)
local loaded,reason=images.resident(W.runtime,image('never_shipped'))
assert(loaded==false and reason=="not in the game's textures",reason)
loaded,reason=images.resident(W.runtime,image('orbital_gas_barrage_icon','mods/other/mod'))
assert(loaded==false)                                           -- another mod's id is another texture
textures.set('texture',images.name(MOD,'orbital_gas_barrage_icon'),'unloaded')
loaded,reason=images.resident(W.runtime,icon)
assert(loaded==false and reason=='not loaded yet',reason)
textures.set('texture',images.name(MOD,'orbital_gas_barrage_icon'),'tombstone')
loaded,reason=images.resident(W.runtime,icon)
assert(loaded==false and reason=='unloaded',reason)
-- Another game build: one lookup instruction differs.
images.reset_for_tests()
local pin=IMG.pins[1]
local base=pin.module=='exe'and W.EXE or W.GAME
local original=W.read(base+pin.rva,1)
W.write(base+pin.rva,string.char(0xCC))
loaded,reason=images.resident(W.runtime,image('second'))
assert(loaded==false and reason:find('unavailable on this game build',1,true),reason)
W.write(base+pin.rva,original)
images.reset_for_tests()
-- Handles: one per mod and id; ids validated; the public fields carry no hash.
assert(image('second')==image('second')and image('second')~=image('second','mods/other/mod'))
for _,bad in ipairs({'','Icon','a-b','a/b',string.rep('x',65)})do assert(not pcall(image,bad),bad)end
assert(not pcall(images.handle,'icon','unknown'))
assert(icon:describe().id=='orbital_gas_barrage_icon'and icon:describe().mod==MOD)
assert(writes()==0)
return 'ok'
''')


class ImageRecordLogTests(unittest.TestCase):
    def test_the_runtime_logs_each_icons_source_and_build_once(self):
        self.assertEqual(run(r"""
local images=require('hd2runtime/runtime/image_resources')
images.reset_for_tests()
local lines={}
require('hd2runtime/runtime/log').emit=function(line)lines[#lines+1]=line end
package.preload['mods/test/with_record/hd2runtime_images']=function()
    return {format=1,images={icon={source='images/icon.png',sha256='ab12',prepared='masks (as given)',
        build='recompiled: source changed',resource='mods/test/with_record/images/icon'}}}
end
images.handle('icon','mods/test/with_record')
images.handle('icon','mods/test/with_record')                      -- once per icon
images.handle('typo','mods/test/with_record')
images.handle('icon','mods/test/older_build')
assert(#lines==3,table.concat(lines,' | '))
assert(lines[1]=='[HD2Runtime] custom image mods/test/with_record/images/icon (texture and GUI material of that name, '
    ..'from this mod\'s archive): built from images/icon.png, sha256 ab12, masks (as given); build: recompiled: '
    ..'source changed',lines[1])
assert(lines[2]:find('custom image mods/test/with_record/images/typo: NOT in this mod\'s build',1,true),lines[2])
assert(lines[3]:find('custom image mods/test/older_build/images/icon: no build record in this mod\'s archive',1,true))
return 'ok'
"""), b'ok')


class MetadataTests(unittest.TestCase):
    def test_custom_images_are_published_as_icon_values(self):
        catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text(encoding='utf-8'))
        icons = [x for x in catalog['fieldInstances'] if x['semanticFieldId'] == 'stratagem.presentation.icon']
        self.assertEqual(len(icons), 94)
        self.assertTrue(all(x['customValues'] == 'image' and 'hd2.resources.image(id)' in x['valueSource']
            for x in icons))
        self.assertFalse(any('customValues' in x for x in catalog['fieldInstances']
            if x['semanticFieldId'] != 'stratagem.presentation.icon'))
        custom = catalog['presentationSources']['customImages']
        self.assertEqual((custom['supported'], custom['fields'], custom['api']),
            (True, ['stratagem.presentation.icon'], 'hd2.resources.image(id)'))
        self.assertIn('ASSET_UNAVAILABLE', custom['refusal'])
        self.assertIn('live_proven', custom['liveEvidence'])
        for internal in (RESEARCH['proofImage']['hash'][2:], 'D60606B9', '0xB0', '9ba626afa44a3aa3', 'gpu_resources'):
            self.assertNotIn(internal, json.dumps(custom))
        stub = (ROOT / 'sdk/stubs/mods/skyeshade/hd2runtime.lua').read_text(encoding='utf-8')
        self.assertIn('---@class HD2Image', stub)
        self.assertIn('function HD2Resources.image(id) end', stub)
        self.assertEqual(stub, (ROOT / 'starter/stubs/mods/skyeshade/hd2runtime.lua').read_text(encoding='utf-8'))

    def test_the_recorded_icon_consumers_explain_the_refusal(self):
        research = json.loads((ROOT / 'research/stratagem-icon-consumers-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        self.assertFalse(any(research['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(research['consumers']['material'], ['0x18CB541', '0x18CBE2B'])
        vanilla = research['vanillaIcons']
        self.assertTrue(all(r['material'] == r['atlasSprite'] == vanilla['values'] and r['standaloneTexture'] == 0
            for r in vanilla['residency']))
        self.assertEqual((vanilla['materials']['found'], vanilla['materials']['identicalOutsideName']),
            (vanilla['values'], True))
        self.assertEqual(research['liveCrash']['exception']['at'], 'helldivers2.exe+0x341D1A')


FAMILY = json.loads((ROOT / 'research/stratagem-icon-family-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
CONSUMERS = json.loads((ROOT / 'research/stratagem-icon-consumers-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


class IconFamilyBuildTests(unittest.TestCase):
    """The complete resource family of a custom icon (research/stratagem-icon-family-F5FEE03DCFDB.json): its texture and
    its GUI material, both under the mod's own name; no atlas sprite."""

    def test_the_material_is_the_vanilla_icon_material_with_its_own_name(self):
        template = bytes.fromhex(CONSUMERS['vanillaIcons']['materials']['template'])
        self.assertEqual(hd2_image.icon_material(0), template)            # 111 vanilla icon materials share it
        name = hd2_archive.resource_hash(hd2_image.image_name('mods/a/b', 'icon'))
        material = hd2_image.icon_material(name)
        self.assertEqual(len(material), 160)
        self.assertEqual(struct.unpack_from('<IIII', material, 0), (0x120, 1, 0x18, 0x7C))   # one material, GUI-usable
        self.assertEqual(struct.unpack_from('<I', material, 0x18 + 0x28)[0], 1)              # one slot
        self.assertEqual(struct.unpack_from('<I', material, 0x18 + 0x68)[0], 0x3461FF0D)     # the icon shader
        self.assertEqual(struct.unpack_from('<IQ', material, 0x88), (0x3AA8B87E, name))      # image slot -> own texture
        self.assertEqual(material[:0x8C] + bytes(8) + material[0x94:], template)
        recorded = FAMILY['vanilla']
        self.assertTrue(recorded['templateMatches'] and recorded['materialsInArchives'] == recorded['iconValues'])
        self.assertTrue(all(r['materialExact'] == r['sprite'] == r['icons'] and r['texture'] == 0
            for r in recorded['snapshots']))

    def test_the_family_round_trips_without_a_sprite_or_a_vanilla_name(self):
        png = hd2_image.write_png(SIZE, SIZE, icon_pixels())
        a = hd2_archive.resource_hash(hd2_image.image_name('mods/a/b', 'icon'))
        b = hd2_archive.resource_hash(hd2_image.image_name('mods/c/d', 'icon'))
        self.assertNotEqual(a, b)                                            # same local id, two mods
        resources = {}
        for name in (a, b):
            resources.update({(kind, name): parts for kind, parts in hd2_image.icon_family(png, name).items()})
        archive, gpu = hd2_archive.make_resource_archive(resources)
        back = hd2_archive.read_archive(archive, gpu)
        self.assertEqual(back, resources)
        self.assertEqual({kind for kind, _ in back}, {hd2_image.TEXTURE_TYPE, hd2_image.MATERIAL_TYPE})
        self.assertEqual(struct.unpack_from('<Q', back[(hd2_image.MATERIAL_TYPE, b)][0], 0x8C)[0], b)
        self.assertEqual(back[(hd2_image.MATERIAL_TYPE, a)][1], b'')        # a material has no GPU part
        custom = FAMILY['customFamily']
        self.assertEqual((custom['roundTrip'], custom['gameResourceCollisions'], custom['distinctFromOtherMod']),
            (True, [], True))
        self.assertEqual(FAMILY['archiveLayout']['differences'], [])        # the vanilla icon-material package
        self.assertEqual(FAMILY['family'], {'materialNamedN': 'required', 'textureNamedN': FAMILY['family'][
            'textureNamedN'], 'atlasSpriteNamedN': 'optional (vanilla icons only)'})

    def test_every_consumer_group_is_recorded(self):
        readers = sorted(r for group in FAMILY['consumers'].values() for r in group['readers'])
        self.assertEqual(readers, sorted(['0x' + format(r['rva'], 'X') for r in CONSUMERS['readers']
            if r['consumer']]))
        self.assertFalse(any(FAMILY['pinnedBytesMismatchPerSnapshot'].values()))


class IconFamilyProjectBuildTests(unittest.TestCase):
    setUp, tearDown, built = BuildTests.setUp, BuildTests.tearDown, BuildTests.built

    def test_images_become_complete_icon_families(self):
        (self.project / 'images').mkdir()
        (self.project / 'images/my_icon.png').write_bytes(hd2_image.write_png(SIZE, SIZE, icon_pixels()))
        archive, gpu, stream, report = self.built()
        found = hd2_archive.read_archive(archive, gpu)
        name = hd2_archive.resource_hash('mods/test/icon_mod/images/my_icon')
        self.assertEqual(found[(hd2_image.MATERIAL_TYPE, name)], (hd2_image.icon_material(name), b''))
        self.assertEqual(found[(hd2_image.TEXTURE_TYPE, name)],
            hd2_image.icon_texture(hd2_image.write_png(SIZE, SIZE, icon_pixels())))
        self.assertEqual(sorted({kind for kind, _ in found}), sorted({hd2_archive.LUA_TYPE, hd2_image.TEXTURE_TYPE,
            hd2_image.MATERIAL_TYPE}))
        self.assertEqual(report['images'], ['my_icon'])


FAMILY_LUA = r"""
local b=require('hd2runtime/core/bytes')
local MA=IMG.material
local function icon_bytes(name,patch)
    local h,l=images.hash(name)
    local s=b.unhex(MA.template)
    s=s:sub(1,MA.nameOffset)..W.u32(l)..W.u32(h)..s:sub(MA.nameOffset+9)
    for offset,bytes in pairs(patch or{})do s=s:sub(1,offset)..bytes..s:sub(offset+#bytes+1)end
    return s
end
local N=images.name(MOD,'orbital_gas_barrage_icon')
local icon=image('orbital_gas_barrage_icon')
"""


def family(body):
    return run(WORLD + PUBLIC + IMAGES + FAMILY_LUA + body)


class IconFamilyRuntimeTests(unittest.TestCase):
    """The internal family reader (runtime/image_resources.lua M.family) on the game's resource-manager layout: complete
    only for the texture plus the exact icon material of the name, with no atlas sprite. It never enables a write."""

    def check(self, body):
        self.assertEqual(family(body), b'ok')

    def test_the_complete_family_resolves(self):
        self.check(r'''
W.icon_resources({textures={N},materials={N}})
local f=images.family(W.runtime,icon)
assert(f.complete==true and f.texture==true and f.material==true and f.sprite==false,tostring(f.reason))
-- The same id in another mod is another family: not loaded.
local other=images.family(W.runtime,image('orbital_gas_barrage_icon','mods/other/mod'))
assert(other.complete==false and tostring(other.reason):find("not in the game's materials",1,true),tostring(other.reason))
return 'ok'
''')

    def test_partial_families_are_incomplete(self):
        self.check(r'''
-- Texture only: the 0.9.0 crash condition (the loadout grid finds no material).
W.icon_resources({textures={N}})
local f=images.family(W.runtime,icon)
assert(f.complete==false and f.texture==true and tostring(f.material):find("not in the game's materials",1,true),
    tostring(f.reason))
-- Material only: no pixels.
W.icon_resources({materials={N}})
f=images.family(W.runtime,icon)
assert(f.complete==false and f.material==true and tostring(f.texture):find("not in the game's textures",1,true),
    tostring(f.reason))
-- An atlas sprite of the same name would redirect the pixels: not a custom family.
W.icon_resources({textures={N},materials={N},sprites={N}})
f=images.family(W.runtime,icon)
assert(f.complete==false and f.sprite==true and f.reason=='an atlas sprite has this name',tostring(f.reason))
-- Unloaded or tombstoned material.
local r=W.icon_resources({textures={N},materials={N}})
r.set('material',N,'unloaded')
f=images.family(W.runtime,icon)
assert(f.complete==false and f.material=='not loaded yet',tostring(f.reason))
r.set('material',N,'tombstone')
f=images.family(W.runtime,icon)
assert(f.complete==false and f.material=='unloaded',tostring(f.reason))
return 'ok'
''')

    def test_only_the_exact_icon_material_is_accepted(self):
        self.check(r'''
local cases={
    {bytes=icon_bytes(N,{[0x80]=W.u32(0x12345678)}),why='not the icon material of this name'},      -- another shader
    {bytes=icon_bytes(N,{[4]=W.u32(0)}),why='not the icon material of this name'},                  -- a material set
    {bytes=icon_bytes('mods/other/mod/images/x'),why='not the icon material of this name'},          -- another texture
    {bytes=icon_bytes(N,{[0x18+0x28]=W.u32(2)}),why='not the icon material of this name'},          -- two slots
    {fixups=false,why='not a loaded icon material'},
    {object={magic=0x11111111},why='its material object differs'},
    {object={shader=0x12345678},why='its material object differs'},
    {object={name={high=1,low=2}},why='its material object differs'},
}
for index,case in ipairs(cases)do
    case.name=N
    W.icon_resources({textures={N},materials={case}})
    local f=images.family(W.runtime,icon)
    assert(f.complete==false and f.material==case.why,index..': '..tostring(f.material))
end
return 'ok'
''')

    def test_the_vanilla_icon_pattern_reads_as_material_plus_sprite(self):
        self.check(r'''
-- A vanilla icon value: its material and atlas sprite are loaded, its standalone texture is not.
local VANILLA='content/ui/stratagem_icon_test'
W.icon_resources({materials={VANILLA},sprites={VANILLA}})
local f=images.family_of(W.runtime,images.hash(VANILLA))
assert(f.material==true and f.sprite==true and f.texture~=true and f.complete==false)
return 'ok'
''')

    def test_the_read_only_inspection_reports_the_family_as_the_game_resolves_it(self):
        self.check(r'''
local h,l=images.hash(N)
local NAME=string.format('0x%08X%08X',h,l)
W.icon_resources({textures={N},materials={N}})
local r=images.inspect_handle(W.runtime,icon)
assert(r.available and r.texture.loaded and r.material.loaded and r.material.exact and r.sprite==false)
assert(r.material.kind==1 and r.material.shader=='0x3461FF0D'and r.material.objectShader=='0x3461FF0D')
assert(r.material.objectName==NAME and#r.material.slots==1)
assert(r.imageSlot.id=='0x3AA8B87E'and r.imageSlot.name==NAME and r.imageSlot.sprite==false and r.imageSlot.textureLoaded)
assert(r.imageSlot.resolvesTo=='standalone texture '..NAME,r.imageSlot.resolvesTo)
-- The vanilla pattern: material + atlas sprite, the slot resolves to the atlas page.
local V,PAGE='content/ui/stratagem_icon_test','content/ui/atlas_page_test'
local vh,vl=images.hash(V)
local ph,pl=images.hash(PAGE)
W.icon_resources({materials={V},sprites={{name=V,atlas=PAGE}}})
local v=images.inspect(W.runtime,vh,vl)
assert(v.material.loaded and v.material.exact and v.texture.loaded==false and v.sprite==true)
assert(v.imageSlot.sprite and v.imageSlot.atlasTexture==string.format('0x%08X%08X',ph,pl)and not v.imageSlot.textureLoaded)
assert(v.imageSlot.resolvesTo=='atlas sprite on '..v.imageSlot.atlasTexture)
-- Texture only: no material to inspect.
W.icon_resources({textures={N}})
r=images.inspect_handle(W.runtime,icon)
assert(r.texture.loaded and not r.material.loaded and r.material.reason=="not in the game's materials"and r.imageSlot==nil)
assert(writes()==0)
return 'ok'
''')

    def test_another_build_reads_no_family(self):
        self.check(r'''
W.icon_resources({textures={N},materials={N}})
assert(images.family(W.runtime,icon).complete==true)
images.reset_for_tests()
local pin=IMG.pins[#IMG.pins]
local base=pin.module=='exe'and W.EXE or W.GAME
local original=W.read(base+pin.rva,1)
W.write(base+pin.rva,string.char(0xCC))
local f=images.family(W.runtime,icon)
assert(f.complete==false and tostring(f.reason):find('unavailable on this game build',1,true),tostring(f.reason))
W.write(base+pin.rva,original)
assert(writes()==0)
return 'ok'
''')


class PublicIconWriteTests(unittest.TestCase):
    """hd2.fields.stratagem.presentation_icon with hd2.resources.image(id): the 120mm's icon member only, to the complete
    custom family, after every guard (image_resources.icon_ready, the guards of the live-verified 0.11.0 write); exact
    restore. Anything less is refused before a byte is written."""

    def check(self, body):
        self.assertEqual(family(body), b'ok')

    def test_the_complete_family_is_written_alone(self):
        self.check(r'''
W.icon_resources({textures={N},materials={N}})
local op=icon_patch('icon',public_image('orbital_gas_barrage_icon'))
assert(op.status=='complete',tostring(op.error))
assert(writes()==1 and W.runtime.writes[1].address==ROW+0xB0 and W.read(ROW+0xB0,8)==images.bytes(icon))
for _,at in ipairs(changed())do assert(at>=ROW+0xB0 and at<ROW+0xB8,string.format('byte %X changed',at))end
assert(identity())
for _,member in ipairs({'name','nameCased','description'})do
    assert(field(ROW,member)==presentation.reviewed(BIG,member),member)
end
assert(count("stratagem.presentation.icon Orbital 120mm HE Barrage -> image 'orbital_gas_barrage_icon' of "..MOD)==1)
return 'ok'
''')

    def test_an_ensure_mixes_it_with_vanilla_values_and_its_toggle_restores_exactly(self):
        self.check(r'''
W.icon_resources({textures={N},materials={N}})
local options=require('hd2runtime/api/options')
local ensure_api=require('hd2runtime/api/ensure')
local scheduler=require('hd2runtime/runtime/scheduler')
options.reset()
local page=api.options({id='look',title='Look'})
local on=page:toggle({id='on',label='On',default=true})
local callbacks={}
rawset(_G,'ModOptionsMenu',{api=1,register_option=function()return true end,get=function()return nil end,
    on_change=function(id,fn)callbacks[id]=fn;return true end,ready=function()return true end})
scheduler.attach(ensure_api.start(W.runtime,function(line)logged[#logged+1]=line end,{enabled=on,interval=1,
    startup_delay=0,transaction={id='look',target=session.stratagem(BIGNAME),changes={
        {field=F.presentation_name,expect=BIGNAME,value=GASNAME},
        {field=F.presentation_icon,expect=BIGNAME,value=public_image('orbital_gas_barrage_icon')}}}}))
for _=1,60 do tick()end
assert(field(ROW,'name')==presentation.reviewed(GAS,'name')and W.read(ROW+0xB0,8)==images.bytes(icon)and writes()==2)
assert(identity())
-- The toggle off: the reviewed native values, exactly; the settings byte-identical.
callbacks['look.on'](false,'look.on')
for _=1,60 do tick()end
assert(presents_as('own')and identity()and#changed()==0)
assert(count('restored the reviewed baseline and is disabled')==1)
return 'ok'
''')

    def test_every_failed_guard_refuses_with_nothing_written(self):
        self.check(r'''
local function refused(text)
    images.reset_for_tests()
    local op=icon_patch('icon',icon)
    assert(op.status=='rejected'and tostring(op.error):find(text,1,true),text..' expected, got '..tostring(op.status)
        ..': '..tostring(op.error))
    assert(writes()==0 and#changed()==0,text)
    return op
end
-- The resource family: texture only (the 0.9.0 crash condition), material only, a sprite clash, another material.
W.icon_resources({textures={N}})
local op=refused("ASSET_UNAVAILABLE: image 'orbital_gas_barrage_icon' of "..MOD.." is not ready as a stratagem icon "
    .."(FAMILY_INCOMPLETE: material: not in the game's materials)")
assert(op.result.code=='ASSET_UNAVAILABLE',tostring(op.result.code))
W.icon_resources({materials={N}});refused("texture: not in the game's textures")
W.icon_resources({textures={N},materials={N},sprites={N}});refused('an atlas sprite has this name')
W.icon_resources({textures={N},materials={{name=N,bytes=icon_bytes(N,{[0x80]=W.u32(0x12345678)})}}})
refused('not the icon material of this name')
-- Nothing shipped under this mod's name.
W.icon_resources({textures={N},materials={N}})
op=op_settle(session.patch{id='other',target=session.stratagem(BIGNAME),field=F.presentation_icon,expect=BIGNAME,
    value=image('orbital_gas_barrage_icon','mods/other/mod')})
assert(op.status=='rejected'and tostring(op.error):find("not in the game's materials",1,true),tostring(op.error))
assert(writes()==0)
-- The consumers: one pinned +0xB0 consumer differs (another build).
local pin
for _,item in ipairs(IMG.consumerPins)do if item.module=='game'and item.rva==0x18CB541 then pin=item end end
local original=W.read(W.GAME+pin.rva,1)
W.write(W.GAME+pin.rva,string.char(0xCC))
refused('custom icons are unavailable on this game build')
W.write(W.GAME+pin.rva,original)
-- The carrier holds another writer's icon: a conflict, nothing written.
W.write(ROW+0xB0,presentation.reviewed(GAS,'icon'))
local before=#(W.runtime.writes or{})
images.reset_for_tests()
op=icon_patch('conflict',icon)
assert(op.status=='rejected'and tostring(op.error):find('CONFLICT',1,true)and#(W.runtime.writes or{})==before,
    tostring(op.error))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
