# The game's own HUD icons in mod overlays

`hd2.resources.game_icon(kind, name)` names one of the game's own stratagem or booster HUD icons. A mod draws it with
`d:image`, exactly like one of its own images:

```lua
local hd2 = require('mods/skyeshade/hd2runtime')
local patriot = hd2.resources.game_icon('stratagem', 'EXO-45 Patriot Exosuit')
local vitality = hd2.resources.game_icon('booster', 'Vitality Enhancement')
local overlay = hd2.ui.overlay()
overlay:draw(function(d)
    d:image(patriot, 40, 40, 64, 64, {colours = {r = '#FF6E5C'}})   -- the category layer red, the rest white
    d:image(vitality, 120, 40, 64, 64)                               -- a booster in its own colours
end)
```

- `kind` is `'stratagem'` or `'booster'`; `name` is the name the Runtime's catalogues use.
  `hd2.resources.game_icons(kind)` lists every name (94 stratagems, 20 boosters in build F5FEE03DCFDB).
- Unknown names return `nil, 'UNKNOWN_ICON', reason`, and so do the two items the game has no HUD icon for
  (CQC-72 Entrenchment Tool, SG-88 Break-Action Shotgun).
- **Nothing is shipped and nothing is written.** The pixels never leave the game: the overlay draws the game's own
  texture with the game's own material. No game memory, file or resource is written, loaded, created or replaced.
- An icon is drawn only while its atlas page is loaded. The stratagem pages are loaded aboard the ship and in missions;
  **the booster page is not loaded during a mission** (all seven retained snapshots), so booster icons wait there
  (`overlay:status().waiting_images`) and come back when it is.
- **Stratagem icons** are masks (R the category layer, G white), coloured as a mod image is (`docs/custom-images.md`):
  `colours = {r, g, b}` colour the R, G and B masks; the default is R and G white with the native 20 % shadow on B.
- **Booster icons** are full-colour pictures and are drawn in their own colours, their yellow hexagon cut out by their
  alpha exactly as the game shows them; `colours` does not apply to them. `colour` (the vertex colour) tints or fades
  either kind.

## How it is drawn

Every HUD icon is a 256 x 256 sprite on one of three `texture_atlas` pages:

| Page | Holds | Format |
|---|---|---|
| page 1 | 82 stratagem icons | 4096 x 4096 BC1 (masks) |
| page 2 | 12 stratagem icons | 2048 x 2048 BC1 (masks) |
| page 3 | 20 booster icons | 4096 x 2048 BC3 (colour and alpha) |

A screen GUI draws a **material**, never a texture or a sprite (`docs/custom-stratagems.md`, the bitmap contract). So:

1. **The material.** Each stratagem has a vanilla GUI icon material named by its icon, exactly the sprite's name, loaded
   with the sprite (`runtime/image_resources.lua` `icon_material` checks it is exactly the icon material). A bitmap of it
   gives this GUI its own instance of that material; the game's UI keeps its own instance untouched.
2. **The page.** `Material.set_texture(instance, 'diffuse_map', IdString64(page))` points this GUI's instance at the
   sprite's atlas page. Exe `0x4A0460`: Lua argument 2, the slot name, is hashed to its upper 32 bits; argument 3 is an
   `IdString64` whose value is read at +8. The icon material's one texture slot is `0x3AA8B87E`,
   `murmur64('diffuse_map') >> 32` (research image-resources, `imageSlot`).
3. **The rectangle.** `Gui.bitmap_uv(gui, material, uv00, uv11, position, size, color)` draws only the sprite's part of
   the page. Exe `0x3E2F10`: the material is Lua argument 2, uv00 argument 3, uv11 argument 4, then the position, size
   and colour. `uv00` is the texture coordinate at the bitmap's top-left corner. `Gui.update_bitmap_uv(gui, id, material,
   uv00, uv11, position, size, color)` (exe `0x3E31D0`) moves one.

The UVs are inset so texture filtering never reaches a neighbouring sprite. Sprites are packed edge to edge, and an
icon drawn smaller than its 256 pixels is sampled from a smaller mip level of the page, whose texels at the sprite's
edge already average in its neighbours: the booster plates, which fill their whole square, showed strips of their
neighbours at their edges with a half-pixel inset (0.30.0-dev r58). The inset is one texel of the mip level the box
samples: 2^k page pixels with k = ceil(log2(sprite / box)), half a page pixel at full size or larger, at most 16 page
pixels (an icon drawn at a quarter of its size loses 4 of its 256 pixels on each side, about 1.5 %).

**The sprite's page and rectangle are read from the running game** (`runtime/image_resources.lua` `atlas_sprite`):
the resource manager's atlas sprite map (+0x2A0, the map the image setter's GUI API +0x348 reads) holds, per sprite
name, a pointer to its 40-byte record: +0 the sprite name, +8 its atlas page texture name, +0x10 its size in pixels (two
u32), +0x18 its rectangle on the page (four f32: u, v, width, height). Validated before use: the record names the
sprite, the size is 1..4096, the rectangle lies on the page and is a whole number of page pixels. The repository holds
only the sprite names (`domains/hud_icons.lua`, generated by `scripts/generate_game_icons.py` from
`sdk/HudIconSprites.json`): no artwork, texture name or archive detail.

Verified on all seven retained snapshots of build F5FEE03DCFDB (ship, lobby, mission, mission end): every sprite map
record matches the game files' atlas record byte for byte, and the stratagem pages are loaded in all of them.

### Boosters: a UI image material

A booster sprite is a full-colour picture whose hexagon is its **alpha**; outside the hexagon its colour channels hold
whatever the texture compression left (the plate's yellow, darker blocks). The icon shader stacks R, G, B and A as four
colour masks (research iconShader) and cannot cut a shape out by the alpha: through it a booster drew as a square with
those leftovers (live 0.30.0-dev r59). So boosters are drawn through a **UI image material** instead: the game's UI image
shader (template `0xBA25DE35`, the most used GUI material shader: 664 materials aboard the ship, 259 loaded in every
retained snapshot) has the same `diffuse_map` slot and no mask layers, and draws the texture's own colours with its
alpha. GameIconProbe 0.2.0 drew the Vitality Enhancement booster through six UI shaders: `0xBA25DE35`, `0x09057911` and
`0x40600CA5` drew its hexagon exactly; `0x50C4CF1C` drew nothing; `0xAAA07776` and `0xDB4D723D` drew a white square.

No material is named in the repository: `runtime/image_resources.lua` `ui_image_materials` reads the game's loaded
materials as its lookups do and keeps those whose shader is `0xBA25DE35` with exactly one `diffuse_map` slot (not a
material set), sorted; `runtime/game_icons.lua` keeps up to eight, found again every 10 s. All boosters share one page,
so one of them serves every booster in an overlay.

### Materials per frame

One material instance holds one texture and one colour set. Each frame the overlay gives every game icon a material
(`runtime/mod_overlay.lua` `assign_materials`):
- a stratagem first gets its own icon material; a stratagem whose own material already holds another colour set this
  frame gets a **carrier**: another stratagem's icon material that this overlay does not use this frame;
- a booster gets a UI image material (one per page);
- the material that served the same page and colours last frame is kept if still free, else the first free loaded one
  of its pool in sorted order, so choices are stable;
- no two (page, colours) pairs ever share a material in one frame. With every icon material in use, an icon is refused
  (`overlay:status().first_refusal`).

So, unlike a mod image, one game icon may appear in several colour sets in one overlay.

### Safety

- **`set_texture` only ever names a page proven loaded in the same frame.** The engine resolves the name itself and is
  never handed one that is not loaded.
- **Every page in use is checked every frame, and every material in use every 15 frames.** When one unloads, the GUI is
  closed first, so its material instances (which name the page) go with it, and it is opened again without that icon.
- An icon whose sprite, page or (for a stratagem) icon material is not loaded is not drawn; the reason is
  `overlay:status().image_reason`.
- Every value is validated before it reaches the engine: a 16-digit hex material and page, UVs in 0..1, the usual
  pixel box, layer and colour checks.

## Live evidence

GameIconProbe 0.1.0 (`proof/GameIconProbe`), aboard the ship, 3840 x 2160:
- the EXO-45 Patriot (page 1) and the B/MD C4 Pack (page 2) drew as the game shows them, red category layer and white;
- the Vitality Enhancement booster (page 3, through the Eagle 500kg Bomb's icon material as the carrier) drew as its
  yellow plate with the dark glyph, but as a square: the icon shader cannot cut out its alpha (0.2.0 and the UI image
  material above fixed it);
- `uv00 = (u, v)` drew the icons upright, the swapped V upside down;
- the whole page drawn through the instance proved `set_texture` took effect; an untouched vanilla icon material draws
  the game's "?" placeholder texture;
- the panel was closed and opened again with no failure logged.
