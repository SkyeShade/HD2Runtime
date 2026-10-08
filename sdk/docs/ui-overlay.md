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
| `d:image(image, x, y, w, h, {colours, colour, z})` | one of the mod's own images (`hd2.resources.image`), or one of the game's own HUD icons (`hd2.resources.game_icon`, docs/game-icons.md); `(x, y)` is its top-left corner (r50) |

- **Coordinates** are GUI pixels with the origin at the **top-left**, y down (the same corner as
  `hd2.input.mouse()`; `overlay:mouse()` maps the cursor into overlay coordinates). `d.width`, `d.height` are the
  screen; `d.scale` = min(width / 1920, height / 1080) sizes a layout made at 1080p.
- **Colours**: `{r, g, b[, a]}` 0-255 (alpha defaults to 255) or `'#RRGGBB'` / `'#RRGGBBAA'`; default white.
- **Fonts**: `'body'` (FS Sinclair, the loadout screen's typeface) and `'title'` (FS Sinclair Medium), shipped in the
  Runtime's archive; `'mono'` is the engine's `monaco`. A role whose font is not loaded falls back to `monaco`.
  Text is 1-160 printable bytes (UTF-8 accepted), size 4-256 px.
- **Text placement (r50 calibration).** The Runtime's FS Sinclair fonts draw their glyphs 0.41 x size below the
  baseline `Gui.text` is given. Measured live on 2026-10-07 (HD2Runtime Editor at 3838 x 2158): text at sizes 12-22
  landed 0.37-0.45 x size low. The font build measures glyph records from the baseline but writes the header offset
  -descent x 0.75, the monaco convention for records measured from the line bottom (`scripts/hd2_font.py`); the rest
  is likely the distance-field padding. The overlay lifts FS Sinclair text by `0.41 x size`
  (`runtime/mod_overlay.lua` `M.TEXT_DROP`), so `(x, y)` is the line's top-left as documented. The custom stratagem
  panel and the other Runtime GUIs pass baselines directly and are not corrected yet.
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
- **Images are icon masks.** `d:image` draws through the game's icon material: R, G and B masks coloured by
  `colours`, never true colour (a raw picture shows as a silhouette; docs/custom-images.md). Vanilla stratagem icons
  are atlas sprites that `Gui.bitmap` most likely cannot show, and booster icons exist only as Noesis XAML: neither is
  offered.
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
- `overlay:free_cursor(on, {camera = true})` and `hd2.ui.cursor()`: see [The cursor](#the-cursor-experimental-r50).
  `status()` also reports `waiting_images`, `image_reason` and `cursor`.

## Images (r50)

```lua
local logo = hd2.resources.image('logo')           -- images/logo.png in the mod project (256 x 256)
overlay:draw(function(d)
    d:image(logo, 40 * d.scale, 40 * d.scale, 64 * d.scale, 64 * d.scale,
        {colours = {r = '#45ACC8', g = {255, 255, 255, 238}}})
end)
```

- An image is drawn only when its texture, material and sprite are proven loaded (`image_resources.family`; checked
  again every 60 frames until it is). Until then it is skipped and `status().waiting_images` counts it.
- `colours = {r, g, b}`: the colours of its R, G and B masks (the icon material's c0-c2; the alpha is the layer's
  strength). The default is white R and G and the native 0.2 black shadow on B; c3 is always zero (the BC1 texture's
  alpha is about 1 everywhere, so a non-zero c3 would flood the quad). `colour` is the vertex colour (tint, alpha).
- One material instance per image per GUI: every draw of one image in one overlay shares one colour set. A second
  set in the same frame is refused (`one colour set per image per overlay`); a new set in a later frame recolours it.
- An image partly off screen is dropped (a bitmap is never squashed).

### The game's own HUD icons

```lua
local patriot = hd2.resources.game_icon('stratagem', 'EXO-45 Patriot Exosuit')
overlay:draw(function(d) d:image(patriot, 40, 40, 64, 64, {colours = {r = '#FF6E5C'}}) end)
```

Every stratagem and booster HUD icon, drawn from the game's own atlas pages with the game's own materials: nothing is
shipped and nothing is written (docs/game-icons.md). Stratagem icons take the same `colours`; booster icons are drawn
in their own colours. Differences from a mod image:
- one icon may be drawn in several colour sets in one overlay (each extra set borrows another icon material);
- an icon is drawn only while its atlas page is loaded: booster icons are not during a mission;
- when a page or material in use unloads, the overlay closes its GUI and draws again without that icon.

## The cursor (experimental, r50)

`overlay:free_cursor(true)` frees the mouse cursor from the camera while the overlay is shown: through the engine's
own Lua Window API it shows the cursor (`Window.set_show_cursor(true)`), stops clipping it to the window
(`set_clip_cursor(false)`) and drops the mouse focus (`set_mouse_focus(false)`), the raw mouse input the camera turns
from. `{camera = false}` keeps the focus. Hiding or closing the overlay, or `free_cursor(false)`, gives it back: the
values the getters reported before the first hold are restored (`runtime/mod_cursor.lua`).

- Each setter is called only when its getter (`Window.show_cursor()` etc., no argument) reports otherwise, so a quiet
  frame costs three getter calls. Every value passed is a boolean; the first engine error turns capture off for the
  session (logged once, `hd2.ui.cursor().disabled`).
- **Not live-tested.** The functions are registered (their names are in the engine's Window string table of the
  retained snapshot), but no build called them before r50. The live test checks: is the cursor visible and free in a
  mission and on the ship; does the camera stop; does a click still fire the weapon (keys and clicks are still not
  taken from the game); is everything restored after closing, alt-tab and a mission change.

Tests: `tests/test_ui_overlay.py` (a recording fake of the engine GUI API).

## The mouse wheel (experimental, r51)

`hd2.input.wheel()` is the wheel this update tick in notches (+ up, - down; fractions for smooth wheels), 0 when it
did not move. The editor's scroll lists read it once per frame.

- `GetAsyncKeyState` cannot see the wheel, and the engine's `stingray.Mouse` `wheel` axis read nothing while the
  overlay held the mouse focus (live test of r50). Two sources are sampled once per tick while someone queries:
  the engine axis, and a `WH_GETMESSAGE` hook on the game window's thread counting `WM_MOUSEWHEEL` and the wheel
  of `WM_INPUT` raw mouse input (`runtime/mouse_wheel.lua`).
- **The hook procedure is native code, not Lua.** The game pumps its window messages on another thread than the one
  running Lua (live r51: window thread 65780, Lua thread 51232), so a Lua callback there would run Lua on a foreign
  thread. `M.hook_code` assembles about 200 bytes of x64 into a page the Runtime allocates once and never frees: it
  adds `WM_MOUSEWHEEL` deltas to one counter and raw-input wheel deltas to another (`GetRawInputData` on the
  message's own handle, read-only), and always returns `CallNextHookEx`. Lua reads the counters once per tick (raw
  input wins when both saw the same turn). Nothing is consumed, so the game still scrolls its own menus.
- It is removed one second after the last query (the pages stay); a failed install is retried at most every two
  seconds (r51 retried every frame and filled LuaJIT's ctype table: `table overflow`); any error turns it off for the
  session (logged once).
  `hd2.input.wheel_status()` reports `{hooked, disabled, source, engine}`; the first source that delivers a notch is
  logged (`wheel: first wheel input from ...`), so a live test tells which one works.

Tests: `tests/test_editor_services.py` (`WheelTests`).
