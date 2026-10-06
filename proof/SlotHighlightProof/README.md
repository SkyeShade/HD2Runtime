# SlotHighlightProof 0.1.0 (development only): move the native loadout slot highlight by data

**This build writes**, but only the loadout panel's highlight state:
- **the panel's focused slot** and the previous one;
- **the "focused" bit** of the old and new slot widgets;
- **one frame-flash byte on each of the two widgets.** The game's own panel update clears it on the next frame and
  redraws the widget from its flags, exactly as it does at the end of a native frame flash.
- **Optionally, the edited slot** (where the next pick lands), with Ctrl.

No loadout record, save, account, catalogue, inventory, mission record or StratagemInfo write. No custom stratagem. No
native call, no hook, no input injection.

Aboard the ship, **solo**, **no mission**.

**Which build is running:**
- the first log line is `SlotHighlightProof 0.1.0 NATIVE HIGHLIGHT BUILD: ...`;
- F9 prints `F9 [0.1.0 NATIVE HIGHLIGHT]`.

Build with `py scripts/build_custom_projectile_proof.py --only SlotHighlightProof`.

## Keys

| Key | Effect |
| --- | --- |
| F7 | The highlight moves to the next slot (0 -> 1 -> 2 -> 3). The edited slot does **not** move. |
| Ctrl+F7 | The highlight **and** the edited slot move to the next slot. Only while a stratagem selector is open. |
| F8 / Ctrl+F8 | The same, towards the previous slot. |
| F9 | Status: the focus, the edited slot, and each slot widget's flags, flash byte and frame. |

## Live test

Install the HD2Runtime runtime ZIP and `SlotHighlightProof-0.1.0.zip` only. Remove CustomStratagemPanelProof,
VirtualSelectorProof and RenderOrderProof. Disable Stratagem MultiSelect and Vanilla Plus Megapack.

1. **Highlight only, with the selector open.**
   - Open the loadout screen, then the stratagem selector on **slot 1** (the leftmost).
   - Press **F7** three times: 0 -> 1 -> 2 -> 3. After each press, take a screenshot and note which slot shows the
     native highlight.
   - Press F9.
2. **The next pick lands on the edited slot.**
   - Pick a stratagem in the native grid. Because F7 does not move the edited slot, it should go into **slot 1** (where
     the selector was opened), not into the highlighted slot.
   - Note where it went and where the highlight is afterwards.
3. **Highlight and edited slot together.**
   - Make sure slot 1 holds a stratagem, then open the stratagem selector on slot 1 again.
   - Press **Ctrl+F7**: the highlight and the edited slot move to slot 2.
   - Pick a stratagem natively. It should go into **slot 2**.
4. **Highlight only, with the selector closed.** Close the selector (Back), then press F7 and F8 a few times. Does the
   highlight move? Do the arrow keys then continue from the new slot?

**If the game crashes:** stop and do not retry. Send:
- the newest `.dmp` from `%APPDATA%\Arrowhead\Helldivers2\dumps\`;
- `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\HD2Runtime.log`;
- the last step you did.

Send:
- every `SlotHighlightProof` and `[HD2Runtime] slot focus` line (`MOVED`, `REFUSED`, `NOT CONSUMED`);
- the F9 lines;
- the screenshots with your notes per step.
