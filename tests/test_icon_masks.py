"""The game's stratagem icon mask convention (research iconShader; docs/custom-stratagems.md, "The panel icon: the game's
mask convention"): the icon shader colours the texture's R (category colour), G (white) and B (shadow) as masks, so a
red-and-white icon picture is converted (sdk/tools/hd2_image.py icon_masks) before it is drawn through it. The shader is
modelled here exactly as its pixel shader composes the layers (R over G over B over A, times the vertex colour), with the
colours the native loadout slot sets, to show that the converted icon draws the artwork's red and white and the
original does not."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sdk'))
from tools.hd2_image import (ICON_MASK_DARK, ICON_MASK_RED, ICON_MASK_WHITE, icon_mask_shares, icon_masks,  # noqa: E402
    read_png)

RESEARCH = json.loads((ROOT / 'research/runtime-stratagem-ui-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


def native_colours():
    """c0 (the orbital colour set 0), c1 and c2 as the research read them from game.dll; c3 zero."""
    colours = list(RESEARCH['snapshots'].values())[0]['iconColours']
    return [colours['table'][0], colours['c1'], colours['c2'], [0.0, 0.0, 0.0, 0.0]]


def shade(pixel, c):
    """The icon pixel shader's layer composition (research iconShader) for one texel (0-255 RGBA): (r, g, b, alpha)."""
    r, g, b, a = (v / 255 for v in pixel)
    s_r, s_g, s_b, s_a = r * c[0][0], g * c[1][0], b * c[2][0], a * c[3][0]
    a_ba = s_b * (1 - s_a) + s_a
    t_b = min(1, max(0, s_b / max(a_ba, 0.001)))
    col = [c[3][i + 1] + t_b * (c[2][i + 1] - c[3][i + 1]) for i in range(3)]
    a_gba = s_g * (1 - a_ba) + a_ba
    t_g = min(1, max(0, s_g / max(a_gba, 0.001)))
    col = [col[i] + t_g * (c[1][i + 1] - col[i]) for i in range(3)]
    a_2 = (1 - s_a) * s_g + a_ba
    a_r = s_r * (1 - a_2) + a_2
    t_r = min(1, max(0, s_r / max(a_r, 0.001)))
    col = [col[i] + t_r * (c[0][i + 1] - col[i]) for i in range(3)]
    return col[0], col[1], col[2], min(1.0, (1 - s_a) * s_r + a_2)


class IconMaskTests(unittest.TestCase):
    def test_the_reference_colours_unmix_exactly(self):
        self.assertEqual(icon_mask_shares(ICON_MASK_DARK), (0.0, 0.0))
        red, white = icon_mask_shares(ICON_MASK_RED)
        self.assertAlmostEqual(red, 1.0)
        self.assertAlmostEqual(white, 0.0)
        red, white = icon_mask_shares(ICON_MASK_WHITE)
        self.assertAlmostEqual(red, 0.0)
        self.assertAlmostEqual(white, 1.0)
        # Half red over dark (an anti-aliased edge): half the red mask, no white.
        half = tuple((d + r) / 2 for d, r in zip(ICON_MASK_DARK, ICON_MASK_RED))
        red, white = icon_mask_shares(half)
        self.assertAlmostEqual(red, 0.5)
        self.assertAlmostEqual(white, 0.0)
        # Shares never add up to more than 1.
        red, white = icon_mask_shares((255, 255, 255))
        self.assertLessEqual(red + white, 1.0 + 1e-9)

    def test_a_picture_becomes_r_and_g_masks_and_the_background_transparent(self):
        pixels = [ICON_MASK_RED + (255,), ICON_MASK_WHITE + (255,), ICON_MASK_DARK + (255,), (200, 50, 50, 0)]
        rgba = bytes(v for p in pixels for v in p)
        out = icon_masks(rgba)
        self.assertEqual(out[0:4], bytes((255, 0, 0, 255)))
        self.assertEqual(out[4:8], bytes((0, 255, 0, 255)))
        self.assertEqual(out[8:12], bytes((0, 0, 0, 255)))
        self.assertEqual(out[12:16], bytes((0, 0, 0, 255)), 'a transparent pixel counts as the background')
        self.assertEqual(rgba, bytes(v for p in pixels for v in p), 'the source is not changed')

    def test_the_proof_icon_follows_the_vanilla_convention(self):
        width, height, rgba = read_png((ROOT / 'proof/PanelIconProof/images/orbital_gas_barrage_masks.png').read_bytes())
        self.assertEqual((width, height), (256, 256))
        both = 0
        for i in range(0, len(rgba), 4):
            r, g, b, a = rgba[i:i + 4]
            self.assertEqual((b, a), (0, 255))
            if r > 64 and g > 64:
                both += 1
        # Like the vanilla icons: each texel is red artwork or white artwork (anti-aliased edges aside).
        self.assertLess(both / (width * height), 0.02)
        # The original picture is unchanged and stays in the proof.
        _, _, original = read_png((ROOT / 'proof/PanelIconProof/images/orbital_gas_barrage.png').read_bytes())
        self.assertNotEqual(original, rgba)

    def test_through_the_icon_shader_the_masks_draw_red_and_white_and_the_original_does_not(self):
        c = native_colours()
        self.assertAlmostEqual(c[0][0], 0.8, places=5)
        _, _, masks = read_png((ROOT / 'proof/PanelIconProof/images/orbital_gas_barrage_masks.png').read_bytes())
        _, _, original = read_png((ROOT / 'proof/PanelIconProof/images/orbital_gas_barrage.png').read_bytes())
        white_ok = red_ok = white_wrong = 0
        for i in range(0, len(original), 4):
            source = original[i:i + 3]
            red, white = icon_mask_shares(source)
            drawn = shade(masks[i:i + 4], c)
            if white > 0.95:
                # White artwork: drawn white (not the category colour) through the masks ...
                if min(drawn[:3]) > 0.9 and drawn[3] > 0.95:
                    white_ok += 1
                # ... but tinted red-orange through the original picture (its R lights the red mask on top).
                plain = shade(original[i:i + 3] + bytes((255,)), c)
                if plain[1] < 0.75:
                    white_wrong += 1
            elif red > 0.95:
                if drawn[0] > 0.95 and drawn[1] < 0.5 and drawn[3] > 0.75:
                    red_ok += 1
        self.assertGreater(white_ok, 5000)
        self.assertGreater(red_ok, 15000)
        self.assertGreater(white_wrong, 5000)


if __name__ == '__main__':
    unittest.main()
