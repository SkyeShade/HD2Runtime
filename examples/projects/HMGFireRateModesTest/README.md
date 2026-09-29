# HMGFireRateModesTest

Live test: the MG-206 Heavy Machine Gun's three native rates of fire, each edited on its own from the MODS tab (Mod
Options Menu, page **HMG Fire Rate Modes**). Needs this HD2Runtime test build (not the published 0.27.0).

The HMG stores three rates in its own weapon record (450 / 600 / 750 rpm). A freshly built HMG starts on **600**, and
each press of its rate-of-fire selector (the weapon-function menu) moves to the next: 600 -> 750 -> 450 -> 600. The
mod replaces them with clearly different rates:

| Option | Native | Test default | Selector position |
| --- | --- | --- | --- |
| Mode 1: the default | 600 | **200** | a fresh HMG |
| Mode 2: one press | 750 | **700** | after one press |
| Mode 3: two presses | 450 | **1400** | after two presses |

## How to test

1. Install the test runtime and this mod, start the game, and check the log for
   `patch hmg-fire-rate-modes APPLIED` (with the three `fire_rate.modes` slots).
2. Call in an HMG (a **freshly built** one: the rates are copied into the weapon when the game builds it) and fire:
   it should fire very slowly (200 rpm).
3. Press the rate-of-fire selector once: it should fire at a normal pace (700 rpm). Once more: very fast (1400 rpm).
   Once more: back to 200.
4. Move one slider (for example Mode 2 to 1000), APPLY, call in a new HMG, and check that only that position changed.
5. Check reload, magazine size, ammunition and handling are unchanged.
6. Turn **Enabled** off, APPLY, call in a new HMG: 600 / 750 / 450 again.

Report for each step whether the rate matched, and anything else that changed. If the already-held HMG changes at
once (without a new call-in), note that too: it tells whether a built weapon re-reads its rates.

`allow_unverified_effect` is set: the slots, the selector traversal and the default slot are proven natively (see
`docs/fire-rate-modes.md`), but this is the first live test of editing them.
