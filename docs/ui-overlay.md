# Screen overlays (`hd2.ui.overlay`)

A mod draws rectangles and text over the game through the Runtime's own GUI path: the world, layers, retained
primitives and engine temporaries are handled for it. Implementation: `runtime/mod_overlay.lua` on
`runtime/engine_gui.lua`; API: `api/ui.lua`. **Offline-tested only; not live-tested yet.**

```lua
local hd2 = require('mods/skyeshade/hd2runtime')
local overlay = hd2.ui.overlay()                 -- your mod's overlay 'main'; {id = 'hud2', layer = 1011} for more
local score = 0

overlay:draw(function(d, dt)                     -- every frame while shown: describe the whole frame
    local s = d.scale                            -- the screen against 1920 x 1080
    d:rect(40 * s, 40 * s, 320 * s, 90 * s, {10, 12, 14, 210})
    d:rect(40 * s, 40 * s, 320 * s, 3 * s, '#C8B43C', 1)
    d:text('STRATAGEM HERO', 56 * s, 52 * s, {size = 26 * s, font = 'title', z = 2})
    d:text('SCORE ' .. score, 56 * s, 90 * s, {size = 20 * s, colour = {200, 200, 196}, z = 2})
end)

hd2.input.bind('arcade.toggle', {key = 'Home', on_press = function()
    if overlay:status().visible then overlay:hide() else overlay:show() end
end})
```

## Drawing

| call | draws |
| --- | --- |
| `d:rect(x, y, w, h, colour, z)` | a filled rectangle; `(x, y)` is its top-left corner |
| `d:text(text, x, y, {size, colour, font, align, z})` | one line; `(x, y)` is its top-left corner (top-centre / top-right with `align = 'center' / 'right'`) |
| `d:text_width(text, size, font)` | the width in pixels, with the same metrics |

- **Coordinates** are GUI pixels with the origin at the **top-left**, y down (the same corner as
  `hd2.input.mouse()`; `overlay:mouse()` maps the cursor into overlay coordinates). `d.width`, `d.height` are the
  screen; `d.scale` = min(width / 1920, height / 1080) sizes a layout made at 1080p.
- **Colours**: `{r, g, b[, a]}` 0-255 (alpha defaults to 255) or `'#RRGGBB'` / `'#RRGGBBAA'`; default white.
- **Fonts**: `'body'` (FS Sinclair, the loadout screen's typeface) and `'title'` (FS Sinclair Medium), shipped in the
  Runtime's archive; `'mono'` is the engine's `monaco`. A role whose font is not loaded falls back to `monaco`.
  Text is 1-160 printable bytes (UTF-8 accepted), size 4-256 px.
- **Layers**: every overlay has a band starting at its `layer` (default 1011); an item's `z` (default 0) is added.
  The engine orders all GUIs of one world by layer, and the layer's depth key is `0.1 * (1023 - layer) / 1023`
  (exe 0x2693E3), so 1023 is the top: an item past it is refused. The default band sits above the native HUD's own
  top layers (991-1018 are used by native GUIs; the Runtime's slot overlays use 940, its panel 920-944).
- Items are clipped to the screen; an item entirely off screen is dropped. Invalid items (not finite, a bad colour,
  a control character, a layer past 1023, an unknown font, more than 1024 items a frame) are **refused, never passed
  to the engine**: `overlay:status()` counts them (`refused`, `first_refusal`).

## What the overlay does for you

- **The world.** A screen GUI in the game's **Ui World**, the world the native HUD and loadout screen draw their GUIs
  in, where the Runtime's slot overlays and panel are seen live. `Application.main_world` is the Game World and
  draws under the whole UI composite. The Ui World is found again every frame: when the game replaces it (ship to
  mission and back) or the resolution changes, the GUI is opened again there.
- **Retained primitives.** Each item keeps one engine primitive. A frame calls the engine only for what changed:
  `Gui.update_rect`, `Gui.update_text` for a changed item, `Gui.rect` / `Gui.text` for a new one, `Gui.destroy_*` for
  one that is gone. An unchanged frame makes no engine call. The argument orders are read from the engine's own
  bindings (exe `0x3E5860` -> `0x3E54D0`: `update_text(gui, id, text, font, size, material, position, color)`, the
  parser `Gui.text` uses with the id second; `0x3E2040` / `0x3E58E0` / `0x3E2EB0`: `destroy_rect / destroy_text /
  destroy_bitmap(gui, id)`).
- **Temporaries.** Each pass runs between `Script.temp_count()` and `Script.set_temp_count(n)`, so the `Vector2`,
  `Vector3` and `Color` values it builds never move the engine's temporaries ring on. In this build both take one
  integer (exe `0x490150`: the byte position in a 1 MiB ring; `0x490270` sets it), not the three counts of older
  engines.
- **Validation.** The engine bindings check nothing (a wrong value most likely crashes); every value is checked
  first.
- **Failures.** A draw function that raises is a frame-callback failure of your mod (logged with the mod id; 25 in a
  row disable it) and its items are hidden on that frame. An engine call that fails closes the GUI (logged once per
  reason); the next frame opens it again.

## Limits

- **Native menus draw above.** The game draws its Noesis UI (menus, the map, the loadout grid and cards) after every
  world GUI, so no layer puts an overlay above them.
- **Input is not consumed.** An overlay that takes keys (`hd2.input.pressed`) shares them with the game; see
  [events.md](events.md#input-blocking-not-available).
- **No images yet.** Mod images (`hd2.resources.image`) use the icon shader's mask colours; drawing them in an
  overlay is not offered yet.
- Visibility is the user's observation only: an engine call that succeeds (an id returned) does not prove pixels
  appeared.

## API

- `hd2.ui.overlay(opts)`: the calling mod's overlay `opts.id` (default `'main'`), created on first use and the same
  object afterwards. `opts`: `{id, layer = 1..1023 (default 1011), visible = true, owner}`.
- `overlay:draw(fn)`: `fn(d, dt)` describes every frame. `overlay:show()`, `:hide()`, `:close()` (removes its
  primitives, its GUI and its frame callback), `:mouse()`, `:text_width(text, size, font)`, `:status()` (`{owner, id,
  state = 'waiting' | 'drawing' | 'hidden' | 'error' | 'failed' | 'closed', reason, layer, visible, width, height,
  scale, items, frames, engine_calls, opened, refused, first_refusal}`).
- `hd2.ui.overlays()`: every overlay's status. `hd2.ui.colour(c)`: a colour as `{r, g, b, a}`, or nil.

Tests: `tests/test_ui_overlay.py` (a recording fake of the engine GUI API).
