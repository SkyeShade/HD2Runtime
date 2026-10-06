# SlotOverlayProof 0.1.0 (development only, visual only): the custom icon over native slot icons

**Nothing is selected, converted or written.** This proof draws the masked Orbital Gas Barrage icon over native
stratagem slot icons. It draws in a Runtime screen GUI in the Ui World, the world the game draws the loadout screen and
the mission HUD in, at layer 940, above the slot icons.

- **The fake virtual identity** is the proof's own table. The selector, the saved order and the mission conversion
  never see it.
- **The native slot is only read:** its type, icon element, material and texture. The native Precision Strike icon is
  not changed anywhere.

See `docs/custom-stratagems.md`, "Slot icon overlays".

**Which build is running:**
- the first log line is `SlotOverlayProof 0.1.0 SLOT ICON OVERLAY BUILD: ...`;
- End prints `End [0.1.0 SLOT ICON OVERLAY]: ...`.

## Keys

| Key | Action |
| --- | --- |
| F5 / F6 / F7 / F8 | Toggle a fake virtual identity on slot 0 / 1 / 2 / 3 |
| F9 | virtual / native / virtual / native (slots 0 and 2); pressed again: all native |
| Home | Backing plate under each overlay on/off (off at start). It hides the native icon where the Gas Barrage art is transparent |
| End | Status: the fake slots, the Ui World, the colours and what is shown |

## Live test

**Setup:**
- install the HD2Runtime runtime ZIP handed out with this proof, and `SlotOverlayProof-0.1.0.zip` only;
- remove every other proof (CustomStratagemPanelProof, SlotHighlightProof, PanelIconProof, SelectionSoundProof,
  SlotTextureProbe and the rest);
- play solo.

**Aboard the ship:**
1. **Before the loadout screen.** Press F5. Is anything drawn anywhere? Expected: nothing, because no slot icon is
   shown. Press F5 again to clear.
2. **Open the loadout screen** (the four stratagem slots visible, no selector open).
3. **Each slot in turn.** Press F5 and take a screenshot. Does the Gas Barrage icon appear over slot 0's icon? Is it
   **above** the native icon, at the same place and size? Press F5 again: is it gone at once? Repeat with F6 (slot 1),
   F7 (slot 2) and F8 (slot 3).
4. **The pattern.** Press F9 and take a screenshot. Expected: overlays on slots 0 and 2 only, slots 1 and 3 native.
5. **The backing plate.** Press Home and take a screenshot. Is the native Precision Strike art now hidden under the
   overlays? Press Home again to switch it off.
6. **Following the native icon.** Open and close a stratagem selector on a slot, and move the focus. Does each overlay
   stay on its slot icon? Does it follow fades?
7. **Leaving the screen.** Close the loadout screen. Does every overlay disappear with the slots?
8. **Status.** Press End.

**Optional, in a mission:** keep F9's pattern and start a mission. This changes no gameplay: the fake identities are
never converted. Do overlays appear on the HUD's stratagem list on the entries of loadout slots 0 and 2? Press End.

**Send:**
- the screenshots;
- what you saw for steps 1–8 (and the mission step, if done);
- the log lines containing `slot overlay`, `SlotOverlayProof` or `End [`.
