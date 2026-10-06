# VirtualSelectorProof 0.6.0 (development only): coordinate diagnostics for the Runtime card in the native grid

0.5.0 logged the card as shown in its cell (`x 550, y 248, 160 px`), but it could not be seen. This build measures
where the Runtime GUI draws against the native cards' own on-screen rectangles. The placement formula is unchanged.

This build **only draws**: F7 selection is off and nothing is written to the game. Aboard the ship only, with no
mission.

- **Diagnostics (on at start, F8 toggles them).** Each time the stratagem list is still, the log gets calibration
  lines and these markers are drawn on top:
  - **N0, N1, N2:** magenta outlines and centre dots on three native cards (different rows and columns), drawn from
    the cards' own transforms;
  - **V:** a green outline and centre dot on the Runtime card's computed cell (also when that cell is off screen or
    outside the viewport);
  - **F:** a cyan outline on the native list frame (the viewport);
  - **BL 0,0 / BR / TL / TR w,h:** yellow squares in the four corners of the Runtime GUI, labelled for a bottom-left
    origin, and a yellow cross **C** at its centre;
  - **L:** small yellow dots at a low layer (21) inside N0 and V. They show whether the native UI covers low layers.
  The markers disappear while the list moves and come back when it is still.
- **The card is the tile alone** (dark background, custom icon, native-proportioned border), with no name or
  description. It sits at a high layer (900) and is drawn only when its cell is inside the viewport.
- **The native cards are never touched.** F9 prints status.

Research and design: [A Runtime-owned custom stratagem selector](../../docs/custom-stratagems.md), section
"Coordinate calibration".

**Which build is running:**
- the first log line is `VirtualSelectorProof 0.6.0 COORDINATE-DIAGNOSTICS BUILD: ...`;
- F9 prints `F9 [0.6.0 COORDINATE-DIAGNOSTICS]`.

Build with `py scripts/build_custom_projectile_proof.py --only VirtualSelectorProof`.

## Live test (rendering only)

Solo, aboard the ship. Do not start a mission. Disable Stratagem MultiSelect and other stratagem mods. Remove older
VirtualSelectorProof versions.

1. Install the HD2Runtime runtime ZIP and `VirtualSelectorProof-0.6.0.zip`.
2. **Open the loadout screen.**
3. **Open the grid:** a stratagem grid for a slot.
4. **Check the debug markers** (on at start; press F8 if they are off). Hold still for a moment. Take a screenshot.
5. **Scroll to several positions:** the top, the middle and two more. At each, hold still, then take a screenshot.
6. **At each position, check:**
   - do the magenta N0, N1, N2 outlines sit exactly on native cards? If not, are they shifted, scaled or mirrored?
   - where are the yellow corner squares (BL, BR, TL, TR) and the centre cross on your screen?
   - is the cyan F outline on the list frame?
   - are the yellow L dots visible?
7. **Scroll to the bottom.** Hold still. Take a screenshot.
8. **Check the tile:** does it visibly occupy the next free cell after the last native card, under the green V
   outline?
9. **Confirm** that it never covers a native card.
10. **Confirm** that it stays inside the grid frame.

**If the game crashes:** stop and do not retry. Send:
- the newest `.dmp` from `%APPDATA%\Arrowhead\Helldivers2\dumps\`;
- `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\HD2Runtime.log`;
- the last step you did.

Send:
- every `VirtualSelectorProof` and `[HD2Runtime]` line, especially every line starting with `calibration`;
- your screen resolution and the game's resolution, render scale and UI scale settings;
- the screenshots, each with its scroll position (top, middle, bottom);
- an F9 line.
