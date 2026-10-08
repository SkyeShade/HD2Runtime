# GameIconProbe 0.2.0 (development only, visual only): the game's own HUD icons in a screen GUI

**Nothing is written** to game memory or game files, and no game resource is loaded, created or replaced.

## The question

Can a mod's screen GUI show the game's own stratagem and booster icons, with no artwork shipped?

Every HUD icon is a 256 x 256 sprite on one of three `texture_atlas` pages the game keeps loaded:

| Page | Holds | Format |
|---|---|---|
| `5207684C3952B0CC` | 82 stratagem icons | 4096 x 4096 BC1 (masks) |
| `6E09D5A15DEC6F79` | 12 stratagem icons | 2048 x 2048 BC1 (masks) |
| `18EDBED388A3D706` | 20 booster icons | 4096 x 2048 BC3 (colour + alpha) |

A `Gui.bitmap` draws a material, never a texture or a sprite. The probe:
1. draws the stratagem's own vanilla icon material, named by the icon hash (the sprite's own name), so this GUI gets its
   own instance of it; the game's UI keeps its instance untouched;
2. points that instance's texture slot at the atlas page: `Material.set_texture(instance, 'diffuse_map', IdString64 page)`
   (exe `0x4A0460`; the icon material's one slot is `0x3AA8B87E`, `murmur64('diffuse_map') >> 32`);
3. draws only the sprite's rectangle with `Gui.bitmap_uv(gui, material, uv00, uv11, position, size, color)` (exe
   `0x3E2F10`: uv00 is Lua argument 3, uv11 argument 4; `0x3E31D0` is `Gui.update_bitmap_uv`, the id second).

Both argument orders were read from the game executable, not guessed. `set_texture` is only called once the page texture
is proven loaded.

## Live test

Install this probe next to HD2Runtime. Solo, aboard the ship.

1. Open the loadout screen (so the HUD atlases are surely loaded), then press **F7**. Shift+F7 closes the panel; F7
   again rebuilds it.
2. Take a screenshot of the panel. Three rows, four columns:
   - rows: **1** EXO-45 Patriot Exosuit (page 1), **2** B/MD C4 Pack (page 2), **3** Vitality Enhancement (booster page,
     through the Eagle 500kg Bomb's icon material as the carrier);
   - columns: **A** the sprite, `uv00 = (u0, v0)`; **B** the sprite, `uv00 = (u0, v0 + dv)` (one of A and B is upside
     down); **C** the whole atlas page; **D** a control: the Resupply icon material with nothing changed.
3. For each cell, note what you see (the right icon, upright or upside down, a squashed page, blank).

Send the screenshot, your notes and every `GameIconProbe` line of `HD2Runtime.log`.

## Result (2026-10-08, 3840 x 2160, aboard the ship)

Every step succeeded, both times the panel was built. Columns A drew the Patriot, the C4 Pack and the Vitality
Enhancement upright and as the game shows them (red category layer and white; the booster's yellow plate with its dark
glyph); B drew them upside down, so `uv00 = (u, v)` is the top-left. C drew each whole page, proving `set_texture`; D,
an untouched vanilla icon material, drew the game's "?" placeholder. hd2.resources.game_icon is built on this
(docs/game-icons.md).

## 0.2.0: which UI material draws a booster as the game shows it

Through the stratagem icon material a booster shows as a square: its sprite is a full-colour picture whose hexagon is
its alpha, and the icon shader stacks R, G, B and A as colour masks, so the colour left outside the hexagon is drawn
too (live r59). The game's UI image shader family has the same `diffuse_map` slot and no mask layers. 0.2.0 draws the
Vitality Enhancement booster through one always-loaded material of six of those shaders (columns 1-6: `BA25DE35`,
`09057911`, `50C4CF1C`, `40600CA5`, `AAA07776`, `DB4D723D`), row 1 as they are, row 2 with `c0` white (a second GUI).
Needs HD2Runtime with `hd2.resources.game_icon` (game-icons r59 or later).

**Live test:** aboard the ship, **Ctrl+F7** (Ctrl+Shift+F7 closes). Screenshot the panel: which cells show the yellow
hexagon with its dark glyph and nothing around it? Send it with every `GameIconProbe` line of `HD2Runtime.log`.
