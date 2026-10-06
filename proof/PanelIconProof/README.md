# PanelIconProof 0.1.0 (development only, visual only): the panel icon as the game's icon masks

**Nothing is selected or written.** This proof only draws the Runtime's CUSTOM STRATAGEMS panel, with the 0.3–0.6 layout
and lifecycle, while a native stratagem selector is open.

## Why the 0.6.0 icon looked wrong

The vanilla stratagem icon shader does not draw a picture's colours. It treats the texture's channels as masks and
colours each with a value the UI sets for that draw:

| Channel | Colour (as the native loadout slot sets it) |
| --- | --- |
| R | the category colour; orbital: red-orange (1.0, 0.43, 0.36) at 80 % |
| G | white (1, 1, 0.93) |
| B | a 20 % shadow (unused by stratagem icons) |
| 0 everywhere | transparent |

The game's own icons are made that way. For example, the 120mm icon's red globe is in R and its white shells are in G.
`orbital_gas_barrage.png` is a full-colour picture, so its white areas also light the red mask, which is drawn on top.

`orbital_gas_barrage_masks.png` is the same artwork converted to the game's convention:
- the red artwork goes in R;
- the white artwork goes in G;
- the dark background becomes 0.

The conversion is `sdk/tools/hd2_image.py` `icon_masks`, run by
`py proof/CustomStratagemPanelProof/prepare_icons.py <source> orbital_gas_barrage_masks --mask --out proof/PanelIconProof/images`.
The original PNG is unchanged and is in this proof as the comparison.

Offline previews of what the icon shader should produce, over the panel's tile colour, are in
`build/test-artifacts/panel-icon-previews/`:
- `masks_through_icon_shader.png`;
- `original_through_icon_shader.png`;
- `vanilla_120mm_through_icon_shader.png`.

**Which build is running:**
- the first log line is `PanelIconProof 0.1.0 MASKED ICON BUILD: ...`;
- F9 prints `F9 [0.1.0 MASKED ICON]`.

## Live test

Install the HD2Runtime runtime ZIP and `PanelIconProof-0.1.0.zip` only. Remove every other proof (CustomStratagemPanelProof,
SlotHighlightProof and the rest). Solo, aboard the ship, no mission.

1. **The tile.** Open the loadout screen, then the stratagem selector on any slot. Take a screenshot of the panel. Does
   the Orbital Gas Barrage tile show red and white artwork on a dark background?
2. **F8, the diagnostics.** Take a screenshot, then press F8 again.
   - **Row 1 (coloured):**
     - `A font`;
     - `A vanilla`: the vanilla 120mm icon, the reference for how a game icon looks in a Runtime GUI;
     - `B name` / `B hash`: the masked icon;
     - `E original`: the unconverted picture;
     - `C texture` (empty).
   - **Row 2 (plain):** the same with no colours set, expected invisible.
   - **Last row:** the masked icon at four sizes.

   For each cell, note what you see on the dark half and on the light half.
3. **F6** shows the tooltip. Clicking does nothing in this build.

Send:
- every `PanelIconProof` and `[HD2Runtime] custom stratagem panel` line, especially `custom icon colours` and
  `icon diagnostics`;
- the two screenshots and your notes;
- your resolution and UI scale.
