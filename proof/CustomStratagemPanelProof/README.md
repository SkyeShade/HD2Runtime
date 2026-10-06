# CustomStratagemPanelProof 0.7.0 (development only): slot overlays in the custom stratagem system

**This build writes**, exactly as 0.6.0 did:
- **Selecting Orbital Gas Barrage** in the Runtime's CUSTOM STRATAGEMS panel puts the vanilla **Orbital Precision
  Strike** token into the slot the native stratagem selector is open for, replacing whatever it holds. It uses the
  existing guarded loadout-record write.
- **The slot becomes a virtual Gas Barrage instance.** Several slots can hold it at once.
- **The native selector moves on to the next empty slot.** The native highlight **and** the edited slot move together
  (the live-proven slot-focus write).

What it does not change:
- the save format, the account, the catalogue, the inventory or any mission record;
- the native picker;
- Precision Strike's own presentation (StratagemInfo);
- the calldown or the payload.

Aboard the ship, **solo**, **no mission**.

## What is new in 0.7.0 (visual only; nothing is written for it)

- **Virtual slots show the custom Gas Barrage icon** over their native loadout slot, drawn by the Runtime overlay that
  SlotOverlayProof 0.1.0 proved live:
  - a Runtime GUI in the Ui World at layer 940;
  - an opaque plate one layer below on exactly the icon's area, in that slot's own icon-background grey, so the
    Precision Strike art underneath does not show through;
  - the masked icon, coloured as the native slot colours the Precision Strike.
- **The native slot is never written.** Its type, icon element, material, texture and UV stay the game's: the 0.5/0.6
  borrowed Orbital Gas Strike icon is **not** used any more. Underneath the overlay the slot still shows the native
  Precision Strike icon (Ctrl+F9 turns the overlays off to check).
- **Native slots get no overlay**, including a natively picked Orbital Precision Strike.
- **The panel's tile icon uses the same technique:** the panel is now a Ui World GUI too, and the tile is opaque. Its
  icon is the same masked icon on the same plate with the same colours, so it should look like the slot overlay (only
  smaller), not darker as before.
- **The icon resource:** `images/orbital_gas_barrage_masks.png` (the game's mask convention). It was converted from the
  author's picture `source/orbital_gas_barrage.png`, which is kept but not packed, with
  `prepare_icons.py <source> orbital_gas_barrage_masks --mask`.

Unchanged from 0.6.0:
- the panel's placement, grid, tooltip, focus, mouse and lifecycle;
- several instances, replacement and the advance;
- the full loadout closing the panel (press Back);
- reconstruction from the saved order.

**Which build is running:**
- the first log line is `CustomStratagemPanelProof 0.7.0 SLOT OVERLAYS BUILD: ...`;
- F9 prints `F9 [0.7.0 SLOT OVERLAYS]`, ending with `GUI world ui; slot overlays ...`.

Build with `py scripts/build_custom_projectile_proof.py --only CustomStratagemPanelProof`.

## Keys

| Key | Action |
| --- | --- |
| Mouse | Hover focuses a tile; a left click on Orbital Gas Barrage selects it |
| F6 / Ctrl+F6 | Focus next / clear |
| F7 / Ctrl+F7 | Select the focused tile / undo the newest selection |
| Ctrl+F9 | Slot overlays off / on (off shows the untouched native icons underneath) |
| F8 | Icon diagnostics |
| F9 | Status |

## Live test

**Setup:**
- install the HD2Runtime runtime ZIP and `CustomStratagemPanelProof-0.7.0.zip` only;
- remove SlotOverlayProof, SlotHighlightProof, PanelIconProof, SelectionSoundProof, SlotTextureProbe, older
  CustomStratagemPanelProof ZIPs, VirtualSelectorProof and RenderOrderProof;
- disable Stratagem MultiSelect and Vanilla Plus Megapack;
- play solo, aboard the ship. **Do not start a mission.**

**Steps:**
- **A.** Open the loadout screen and the stratagem selector on a slot.
- **B.** Take a screenshot of the CUSTOM STRATAGEMS panel. Does the Gas Barrage tile icon look right (red and white
  artwork on the dark tile, not darker than SlotOverlayProof's)?
- **C.** Click Orbital Gas Barrage.
- **D.** Does that loadout slot now show the **same Gas Barrage art** over the slot, with no Precision Strike art showing
  through? Take a screenshot. Press Ctrl+F9: the overlays go and the slot shows the native Precision Strike icon. Press
  Ctrl+F9 again.
- **E, F.** Select Gas Barrage into more slots. Does each virtual slot get its own overlay?
- **G.** Natively pick the real Orbital Precision Strike into a slot. Does it keep its own icon, with no overlay?
- **H.** Arrange GAS / PRECISION / GAS / PRECISION (Gas Barrage from the panel, Precision Strike natively). Can you
  tell them apart? Take a screenshot.
- **I.** Natively replace a Gas Barrage slot with another stratagem. Does its overlay disappear at once?
- **J.** Select Gas Barrage into a native slot. Does the overlay appear?
- **K.** Close the loadout screen, then reopen it. Do the overlays come back only on the virtual slots and in the
  right places, with none left behind?

The selection behaviour must be as in 0.6.0:
- a click selects and replaces an occupied slot;
- the native highlight and the edited slot move to the next empty slot, and the panel stays open;
- a full loadout hides the panel, and Back closes the native selector.

**If the game crashes:** stop and do not retry. Send:
- the newest `.dmp` from `%APPDATA%\Arrowhead\Helldivers2\dumps\`;
- `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\HD2Runtime.log`;
- the last step you did.

**Send:**
- the screenshots (the panel tile; the slots after D, H and K) with your notes for A–K;
- every `CustomStratagemPanelProof` and `[HD2Runtime]` line, especially those beginning:
  - `slot overlay`;
  - `SELECTED`, `the native selector`, `hidden: the loadout is full`;
  - `custom icon`;
  - `saved ship loadout`;
- an F9 line.
