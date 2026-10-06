"""The Runtime-owned FS Sinclair engine fonts (scripts/hd2_font.py, scripts/generate_ui_fonts.py, domains/ui_fonts.lua,
runtime/ui_fonts.lua; scripts/build_release.py runtime_fonts):
  * the engine font format as decoded from the game's own fonts: header (id, em, line, offset, texel size, the
    distance encoding -255/64 and 0.4 x 255/64, padding 8, the fallback glyph), codepoints, 7-float glyph records;
    monaco itself parses with it;
  * a font built from a TrueType file: its glyphs' records inside the atlas, the atlas encoding (0.4 at the edge, 64
    levels a pixel, every channel the same), the full mip chain, the texture's main part in the game's font atlas
    layout, the material the monaco material with only its glyph texture renamed;
  * the domain is current with the installed game's FS Sinclair, and the Runtime ZIP carries exactly its resources."""
import hashlib
import struct
import sys
import unittest
from pathlib import Path

from support import ROOT

sys.path.insert(0, str(ROOT / 'scripts'))
import hd2_font  # noqa: E402

GAME = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2\data\bundles.nxa')
SYSTEM_TTF = Path(r'C:\Windows\Fonts\arial.ttf')


def fake_monaco_material():
    m = bytearray(288)
    struct.pack_into('<Q', m, 0x8C, 0x35FCB2056C9C789E)
    m[0:8] = bytes.fromhex('2001000001000000')
    return bytes(m)


class FontFormatTests(unittest.TestCase):
    @unittest.skipUnless(SYSTEM_TTF.is_file(), 'no system TrueType font to build from')
    def test_a_font_built_from_a_truetype_file(self):
        from hd2_archive import resource_hash
        out = hd2_font.build_font(SYSTEM_TTF.read_bytes(), 'hd2runtime_fonts/test', fake_monaco_material())
        name = resource_hash('hd2runtime_fonts/test')
        main, gpu = out['resources'][(hd2_font.FONT_TYPE, name)]
        self.assertEqual(gpu, b'')
        f = hd2_font.parse_font(main)
        self.assertEqual((f['em'], f['pad']), (hd2_font.EM, 8.0))
        self.assertAlmostEqual(f['scale'], -255 / 64, places=4)
        self.assertAlmostEqual(f['bias'], 0.4 * 255 / 64, places=4)
        self.assertEqual(f['texel'], (struct.unpack('<f', struct.pack('<f', 1 / 1024))[0],
            struct.unpack('<f', struct.pack('<f', 1 / 512))[0]))
        self.assertEqual(f['end'], len(main))
        g = f['glyphs']
        self.assertIn(ord('A'), g)
        x, y, w, h, bx, by, adv = g[ord('A')]
        self.assertTrue(0 <= x and x + w <= 1024 and 0 <= y and y + h <= 512 and adv > 0 and by < 0)
        # the space: an empty 8 x 8 cell at -4, -4 (as the game's fonts have it)
        self.assertEqual(g[32][2:6], (8.0, 8.0, -4.0, -4.0))
        # the atlas: 0.4 (102) at the edge, so the glyph's cell holds values on both sides of it
        atlas = out['atlas']
        cell = atlas[int(y):int(y + h), int(x):int(x + w)]
        self.assertTrue(cell.max() == 255 and cell.min() == 0)
        # every channel the same; the full mip chain
        tmain, tgpu = out['resources'][(hd2_font.TEXTURE_TYPE, resource_hash('hd2runtime_fonts/test/atlas'))]
        self.assertEqual(tgpu[:16], bytes([atlas[0, 0]] * 4) + bytes([atlas[0, 1]] * 4) + bytes([atlas[0, 2]] * 4)
            + bytes([atlas[0, 3]] * 4))
        self.assertEqual(len(tgpu), sum(max(1, 1024 >> k) * max(1, 512 >> k) * 4 for k in range(11)))
        self.assertEqual(tmain, hd2_font.texture_header(1024, 512, 11))
        self.assertEqual(struct.unpack_from('<4I', tmain, 0xC0 + 4 + 8), (512, 1024, 4096, 0))
        # the material: only its glyph texture renamed
        mat, _ = out['resources'][(hd2_font.MATERIAL_TYPE, name)]
        self.assertEqual(struct.unpack_from('<Q', mat, 0x8C)[0], resource_hash('hd2runtime_fonts/test/atlas'))
        self.assertEqual(mat[:0x8C] + mat[0x94:], fake_monaco_material()[:0x8C] + fake_monaco_material()[0x94:])

    @unittest.skipUnless(SYSTEM_TTF.is_file(), 'no system TrueType font to build from')
    def test_a_material_that_is_not_monacos_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'not the reviewed one'):
            hd2_font.build_font(SYSTEM_TTF.read_bytes(), 'x', bytes(288))

    def test_the_arrow_glyphs(self):
        # Up: a cap height tall on the baseline, the tip at the top centre, the stem under half the head's width.
        points, advance = hd2_font.arrow_polygon('up', 100)
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        self.assertEqual((min(xs), max(xs), min(ys), max(ys)), (10, 106, -100, 0))
        self.assertEqual(points[0], (58, -100))
        self.assertAlmostEqual(advance, 116)
        stem = [p for p in points if p[1] == 0]
        self.assertAlmostEqual(max(p[0] for p in stem) - min(p[0] for p in stem), 0.42 * 96)
        # Down mirrors it; left and right lie centred on the cap height, the tip at the side.
        down, _ = hd2_font.arrow_polygon('down', 100)
        self.assertEqual(down[0], (58, 0))
        for direction, tip_x in (('left', 10), ('right', 110)):
            points, advance = hd2_font.arrow_polygon(direction, 100)
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            self.assertEqual((min(xs), max(xs)), (10, 110))
            self.assertAlmostEqual(min(ys), -98)
            self.assertAlmostEqual(max(ys), -2)
            self.assertEqual(points[0][0], tip_x)
            self.assertAlmostEqual(advance, 120)

    def test_the_edt_and_the_encoding(self):
        import numpy as np
        mask = np.zeros((40, 40), dtype=np.uint8)
        mask[12:28, 12:28] = 255
        sdf = hd2_font.glyph_sdf(mask)
        self.assertEqual(sdf.shape, (10, 10))
        self.assertLess(sdf[5, 5], 0)        # inside
        self.assertGreater(sdf[0, 0], 0)     # outside
        enc = hd2_font.encode(np.array([[0.0, -1.0, 1.0]]))
        self.assertEqual(enc.tolist(), [[102, 166, 38]])


@unittest.skipUnless(GAME.is_file(), 'the installed game is absent')
class GameFontTests(unittest.TestCase):
    def test_monaco_parses_and_the_domain_is_current(self):
        import generate_ui_fonts
        src = generate_ui_fonts.game_sources()
        mono = hd2_font.parse_font(src['monaco_font'])
        self.assertEqual((mono['em'], len(mono['glyphs']), mono['end']), (43.0, 143, 4664))
        self.assertEqual(generate_ui_fonts.generate(check=True), [])
        # FS Sinclair has no arrows: both of its fonts carry the drawn ones (the call-in code); monaco has none.
        text = (ROOT / 'domains/ui_fonts.lua').read_text(encoding='utf-8')
        for cp in hd2_font.ARROWS:
            self.assertEqual(text.count('[%d]=' % cp), 2, cp)

    def test_the_runtime_zip_carries_the_fonts(self):
        import re
        import tempfile
        import zipfile
        import build_release
        from hd2_archive import read_archive, resource_hash
        text = (ROOT / 'domains/ui_fonts.lua').read_text(encoding='utf-8')
        digest = re.search(r'\["resources"\]="([0-9a-f]{64})"', text).group(1)
        with tempfile.TemporaryDirectory() as folder:
            path = build_release.build_runtime((ROOT / 'VERSION').read_text().strip(), folder=folder)
            with zipfile.ZipFile(path) as z:
                arc = read_archive(z.read('runtime/9ba626afa44a3aa3.patch_0'),
                    z.read('runtime/9ba626afa44a3aa3.patch_0.gpu_resources'))
        for name in hd2_font.NAMES.values():
            self.assertIn((hd2_font.FONT_TYPE, resource_hash(name)), arc)
            self.assertIn((hd2_font.MATERIAL_TYPE, resource_hash(name)), arc)
            self.assertIn((hd2_font.TEXTURE_TYPE, resource_hash(name + '/atlas')), arc)
        import generate_ui_fonts
        fonts = {k: v for k, v in arc.items() if k[0] != 0xA14E8DFA2CD117E2}
        self.assertEqual(generate_ui_fonts._digest(fonts), digest)


if __name__ == '__main__':
    unittest.main()
