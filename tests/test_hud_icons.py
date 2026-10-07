import importlib.util
import json
import struct
import unittest

from support import ROOT


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load('generate_hud_icons', 'scripts/generate_hud_icons.py')
icons = load('hd2_hud_icons', 'sdk/tools/hd2_hud_icons.py')
image = icons.hd2_image


class FakeData:
    """The resource tables of hd2_game_data.Data for a handful of resources."""

    def __init__(self, resources):
        self.parts = {}
        self.rows = []
        for index, (name, kind, main, gpu) in enumerate(resources):
            archive = 'a%015d' % index
            self.parts[(archive, '')] = main
            self.parts[(archive, '.gpu_resources')] = gpu
            self.rows.append((archive, name, kind, (0, len(main)), (0, 0), (0, len(gpu))))

    def tables(self):
        return iter(self.rows)

    def read(self, archive, part, suffix=''):
        offset, size = part
        return self.parts[(archive, suffix)][offset:offset + size] if size else b''


def atlas(*records):
    return struct.pack('<I', len(records)) + b''.join(icons.RECORD.pack(*r) for r in records) + bytes(4)


class HudIconSpriteCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/HudIconSprites.json').read_text(encoding='utf-8'))

    def test_generated_catalog_is_current(self):
        self.assertEqual(generator.generate(check=True), [])

    def test_every_stratagem_with_a_call_in_and_every_booster_names_a_sprite(self):
        stratagems = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())['stratagems']
        boosters = json.loads((ROOT / 'sdk/BoosterAuthoringCapabilities.json').read_text())['boosters']
        self.assertEqual(len(self.catalog['stratagems']), 94)
        self.assertEqual(len(self.catalog['boosters']), len(boosters))
        self.assertEqual(sorted(self.catalog['missing']), sorted(
            x['name'] for x in stratagems if x['rootResolution'] != 'UNIQUE'))
        self.assertEqual(sorted(self.catalog['missing']), ['CQC-72 Entrenchment Tool', 'SG-88 Break-Action Shotgun'])
        # including those the loadout screen's vector library leaves unbound or empty
        unbound = [x['name'] for x in stratagems if x['uiIcon']['state'] in ('unbound', 'empty_template')]
        self.assertEqual(len(unbound), 10)
        for name in unbound + ['40-K Meltagun', 'Resupply']:
            self.assertIn(name, self.catalog['stratagems'])
        for name in ('Integrated Extinguishers', 'Surplus EAT Allocation'):
            self.assertIn(name, self.catalog['boosters'])
        sprites = [e['sprite'] for e in list(self.catalog['stratagems'].values()) + list(self.catalog['boosters'].values())]
        self.assertEqual(len(sprites), len(set(sprites)))
        self.assertTrue(all(len(s) == 18 and s.startswith('0x') for s in sprites))
        self.assertEqual(self.catalog['boosters']['Surplus EAT Allocation'],
                         {'sprite': '0x13E43CADFA5C61AE', 'nativeName': 'FreeEAT'})


class HudIconDecoderTests(unittest.TestCase):
    def test_bc1_page_round_trip_through_an_atlas_record(self):
        # an 8 x 8 page of four flat quadrants; the sprite is the 4 x 4 lower-right one at a non-zero offset
        colours = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 255, 255)]
        rgba = b''.join(bytes(colours[(y // 4) * 2 + x // 4]) for y in range(8) for x in range(8))
        pixels = image.bc1_mips(8, 8, rgba)
        page_name, sprite_name = 0x1111, 0x2222
        data = FakeData([
            (page_name, icons.TEXTURE, image.texture_main(8, 8, 4), pixels),
            (0x3333, icons.TEXTURE_ATLAS, atlas((sprite_name, page_name, 4, 4, 0.5, 0.5, 0.5, 0.5)), b'')])
        hud = icons.HudIcons(data, {'stratagems': {'X': {'sprite': '0x2222'}}, 'boosters': {}})
        w, h, out = hud.icon('stratagem', 'X')
        self.assertEqual((w, h), (4, 4))
        self.assertEqual(out, bytes(colours[3]) * 16)
        self.assertIsNone(hud.sprite(0x9999))
        self.assertIsNone(hud.icon('stratagem', 'Y'))

    def test_unaligned_sprites_and_block_formats(self):
        # BC1 three-colour mode with transparent black (c0 <= c1, index 3)
        block = struct.pack('<HHI', 0x0000, 0xFFFF, 0xFFFFFFFF)
        page = {'width': 4, 'height': 4, 'format': 71}
        self.assertEqual(icons.decode(block, page, 1, 1, 2, 2), bytes(16))
        # BC3: alpha 0/255 endpoints (index 1 = 255 everywhere) over a white four-colour block
        bc3 = bytes([0, 255]) + (0o1111111111111111).to_bytes(6, 'little') + struct.pack('<HHI', 0xFFFF, 0, 0)
        self.assertEqual(icons.decode(bc3, {'width': 4, 'height': 4, 'format': 77}, 0, 0, 1, 1), b'\xff\xff\xff\xff')
        # BC4: grey from one channel
        bc4 = bytes([200, 0]) + bytes(6)
        self.assertEqual(icons.decode(bc4, {'width': 4, 'height': 4, 'format': 80}, 3, 3, 1, 1), bytes([200, 200, 200, 255]))
        # uncompressed BGRA: channels swapped into RGBA
        bgra = bytes([1, 2, 3, 4]) * 4
        self.assertEqual(icons.decode(bgra, {'width': 2, 'height': 2, 'format': 87}, 1, 1, 1, 1), bytes([3, 2, 1, 4]))
        with self.assertRaises(ValueError):
            icons.decode(block, page, 2, 2, 4, 4)

    def test_texture_and_atlas_parsing_refuse_what_they_do_not_read(self):
        self.assertEqual(icons.parse_texture(image.texture_main(256, 128, 9)), {'width': 256, 'height': 128, 'format': 71})
        with self.assertRaises(ValueError):
            icons.parse_texture(image.texture_main(4, 4, 1, dxgi=98))      # BC7
        with self.assertRaises(ValueError):
            icons.parse_texture(bytes(400))
        with self.assertRaises(ValueError):
            icons.parse_atlas(struct.pack('<I', 3) + bytes(40))
        self.assertEqual(icons.parse_atlas(atlas((1, 2, 3, 4, 0.0, 0.0, 1.0, 1.0)))[0][:4], (1, 2, 3, 4))

    def test_sprites_must_be_whole_pixel_rectangles(self):
        data = FakeData([
            (0x10, icons.TEXTURE, image.texture_main(8, 8, 1), bytes(32)),
            (0x20, icons.TEXTURE_ATLAS, atlas((0x30, 0x10, 4, 4, 0.3, 0.0, 0.5, 0.5)), b'')])
        hud = icons.HudIcons(data, {'stratagems': {}, 'boosters': {}})
        with self.assertRaises(ValueError):
            hud.sprite(0x30)

    def test_png_output_reads_back(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'x.png'
            icons.write_png(path, 2, 1, bytes([255, 0, 0, 255, 0, 255, 0, 128]))
            self.assertEqual(image.read_png(path.read_bytes()), (2, 1, bytes([255, 0, 0, 255, 0, 255, 0, 128])))


if __name__ == '__main__':
    unittest.main()
