# RenderOrderProof 0.1.0 (development only): can a Runtime GUI appear above the native loadout UI?

VirtualSelectorProof 0.6.0 placed the Runtime card correctly in X and size, but it was not visible over the native
stratagem grid, while the same GUI was visible in an empty part of the screen. This proof tests the **render order**
directly. It does not place a stratagem card, select anything or change the loadout.

This build **only draws**: nothing is written to the game. Aboard the ship only, with no mission.

**What the research predicts** (docs/custom-stratagems.md, "Render order"): no rectangle drawn through a screen GUI
appears over the native cards, at any layer. The game draws every world GUI first, then the Noesis UI on top of it in
the same pass. The overlay-world test is also predicted to stay hidden. The live test checks both predictions.

## What is drawn

While a stratagem grid is open and the list is still, it draws over **four native cards** (N0 to N3, the first fully
visible row) and in an **empty area to the right** of the loadout panels, labelled `RENDER ORDER PROBE: outside the
native UI`:

| Where | Test | What you should see if the Runtime GUI is above the native UI |
| --- | --- | --- |
| N0 | **TEST RECTANGLE**: red with a white edge, the text TEST RECTANGLE (layers 998-999) | A red card |
| N1 | **Layers**: one strip per layer, bottom to top: 0 red, 21 orange, 100 yellow, 900 green, 990 cyan | The coloured strips that are above the card |
| N2 | **GUI order**: four GUIs created in the order A, B, C, D, all at layer 500. Top half: A magenta, then B cyan. Bottom half: C cyan, then D magenta | Where the two squares overlap, the later GUI's colour shows if later GUIs draw on top |
| N3 | **Immediate GUI**: a white rectangle drawn again every frame | A white card |

The empty area shows the same tests with labels, so you can see that each one is drawn at all.

**Keys:**
- **F8:** adds layers **2000** (blue) and **10000** (purple). The engine stores the layer as a 32-bit integer, but how
  its renderer uses values above 999 is not proven. If the game crashes right after F8, that is why.
- **F6:** the **overlay world** test. It creates a separate script world rendered through the render config's
  `overlay` viewport, which draws straight into the back buffer, and renders it from the engine's Lua render
  callback. It shows a green rectangle over N0's lower half and a green `OVERLAY WORLD` box in the empty area. It is
  released after 30 s, on F6 again, or when the list moves or the grid closes.
- **F9:** status.

Everything closes while the list scrolls and is drawn again when it is still. Closing the grid removes everything.

**Which build is running:**
- the first log line is `RenderOrderProof 0.1.0 RENDER-ORDER BUILD: ...`;
- F9 prints `F9 [0.1.0 RENDER-ORDER]`.

Build with `py scripts/build_custom_projectile_proof.py --only RenderOrderProof`.

## Live test (rendering only)

Solo, aboard the ship. Do not start a mission. **Remove VirtualSelectorProof** (it also uses F8), and disable
Stratagem MultiSelect and Vanilla Plus Megapack (Know Your Constellation also draws a screen GUI).

1. Install the HD2Runtime runtime ZIP and `RenderOrderProof-0.1.0.zip`.
2. **Open the loadout screen**, then **a stratagem grid** for a slot. Hold still for a moment.
3. **Check the empty area on the right:** the `RENDER ORDER PROBE` label, the five layer squares, the A/B and C/D
   pairs, `TEST RECTANGLE` and the white `IMMEDIATE` square. Take a screenshot.
4. **Check the native cards** of the first fully visible row:
   - Is the **TEST RECTANGLE** (N0) visibly above the card?
   - Which **layer strips** (N1), if any, are visible over the card?
   - Over the card (N2) and in the empty area: in the A/B overlap, is **cyan (B) or magenta (A)** on top? In the
     C/D overlap, is **magenta (D) or cyan (C)** on top?
   - Is the **white immediate rectangle** (N3) visible?
5. **Scroll** a little and hold still. Check that everything is drawn again at the new cards.
6. Press **F6** (overlay world) and hold still. Is the **green** rectangle visible over N0's lower half? Is the green
   `OVERLAY WORLD` box visible in the empty area? Take a screenshot. Press F6 again to release it.
7. Optional, last: press **F8** (layers 2000 and 10000), hold still, and check N1 and the squares again.
8. **Close the grid:** everything must disappear.

**If the game crashes:** stop and do not retry. Send:
- the newest `.dmp` from `%APPDATA%\Arrowhead\Helldivers2\dumps\`;
- `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\HD2Runtime.log`;
- the last step you did (especially F6 or F8).

Send:
- every `RenderOrderProof` and `[HD2Runtime] render probe` line;
- an F9 line;
- the screenshots (steps 3, 4 and 6).
