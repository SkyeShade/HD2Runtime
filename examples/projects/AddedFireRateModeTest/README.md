# AddedFireRateModeTest

Live test: an AR-23 Liberator with a rate-of-fire selector and three rates, listed **450 / 700 / 950** from the top of
its weapon menu, starting on 700. Uses the MODS tab (Mod Options Menu, page **Liberator Fire Rates**). Needs
HD2Runtime 0.28.0.

Natively the Liberator has one rate (640 rpm) in the middle of its three rate slots (Y); the other two (X, Z) are
empty, and its left weapon-function input is unbound. One transaction fills the two empty slots, sets the default and
binds the game's own rate-of-fire selector (the `ROF` weapon function the AR-61 Tenderizer and the machine guns use) to
that input. No array grows and no new data is created: everything written already exists in the Liberator's own
records.

| Option (menu position) | Slot | Native | Test default | Selector |
| --- | --- | --- | --- | --- |
| Top | X | empty | **450** | after two presses |
| Middle: the default | Y | 640 | **700** | a fresh Liberator |
| Bottom | Z | empty | **950** | after one press |

## How to test

1. Check the log for `transaction liberator-fire-rates APPLIED` (`fire_rate.modes {0, 640, 0} -> {450, 700, 950}` and
   `weapon_function.left none -> rate_of_fire`).
2. Deploy with a Liberator **with the default internal attachment**: the Recoil Spring overwrites all three rate
   slots when the weapon is built. The weapon is built when you deploy, so a Liberator already in hand keeps its old
   data.
3. Open the weapon menu: the rate-of-fire entry should list **450 / 700 / 950** from top to bottom (the slider order),
   with 700 selected. Fire: 700 rpm. Press the selector: 950; again: 450; again: 700.
4. Check fire modes (Automatic / Single / Burst) still switch, and that reload, magazine and handling are unchanged.
5. Move a slider, APPLY, get a freshly built Liberator (be reinforced), and check only that menu entry changed.
6. Turn **Enabled** off, APPLY, get a fresh Liberator: one rate of 640 and no rate-of-fire entry.

Report whether the menu order matches the sliders, and anything unexpected. The first live test (sliders in selector
order) passed: the selector appeared and switched between the three new rates, so `fire_rate.modes` with the
`weapon_function.left` binding on the Liberator is live-proven. This build writes the same slots, listed in menu order.
