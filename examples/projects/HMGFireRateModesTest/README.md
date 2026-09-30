# HMGFireRateModesTest

Live test: the MG-206 Heavy Machine Gun's three native rates of fire, each edited on its own from the MODS tab (Mod
Options Menu, page **HMG Fire Rate Modes**). Needs this HD2Runtime test build (not the published 0.27.0).

The HMG stores three rates in its own weapon record: slots X / Y / Z = 450 / 600 / 750 rpm, and the weapon menu lists
them in that order. A freshly built HMG starts on the middle one, **600** (slot Y), and each press of its rate-of-fire
selector moves to the next: 600 -> 750 -> 450 -> 600. The sliders follow the menu from top to bottom, and the mod
replaces the rates with clearly different ones:

| Option (menu position) | Slot | Native | Test default | Selector |
| --- | --- | --- | --- | --- |
| Top | X | 450 | **300** | after two presses |
| Middle: the default | Y | 600 | **550** | a fresh HMG |
| Bottom | Z | 750 | **1200** | after one press |

## How to test

1. Install the test runtime and this mod, start the game, and check the log for
   `patch hmg-fire-rate-modes APPLIED` (`fire_rate.modes {450, 600, 750} -> {300, 550, 1200}`).
2. Call in an HMG (a **freshly built** one: the rates are copied into the weapon when the game builds it). Open its
   weapon menu: it should list **300 / 550 / 1200** from top to bottom, the same order as the sliders, with 550
   selected. Fire: a slow pace (550 rpm).
3. Press the rate-of-fire selector once: 1200 rpm (very fast). Once more: 300 (very slow). Once more: back to 550.
4. Move one slider (for example Bottom to 900), APPLY, call in a new HMG, and check that only that menu entry changed.
5. Check reload, magazine size, ammunition and handling are unchanged.
6. Turn **Enabled** off, APPLY, call in a new HMG: 450 / 600 / 750 again.

Report for each step whether the rates **and the menu order** matched the sliders, and anything else that changed. If
the already-held HMG changes at once (without a new call-in), note that too: it tells whether a built weapon re-reads
its rates.

The first live test (with the sliders in selector order) passed: every slot was written and the selector used the
new rates, so `fire_rate.modes` on the MG-206 is live-proven. This build lists the slots in menu order instead; the
bytes written are the same, so this run mainly confirms the menu order.
