# AddedFireRateModeTest

Live test: an AR-23 Liberator with a rate-of-fire selector and three rates, 450 -> 700 -> 950 rpm. Uses the MODS tab
(Mod Options Menu, page **Liberator Fire Rates**). Needs this HD2Runtime test build (not the published 0.27.0).

Natively the Liberator has one rate (640 rpm) in the middle of its three rate slots; the other two are empty, and its
left weapon-function input is unbound. One transaction fills the two empty slots and binds the game's own
rate-of-fire selector (the `ROF` weapon function the AR-61 Tenderizer and the machine guns use) to that input. No
array grows and no new data is created: everything written already exists in the Liberator's own records.

## How to test

1. Check the log for `transaction liberator-fire-rates APPLIED` (three `fire_rate.modes` slots and
   `weapon_function.left none -> rate_of_fire`).
2. Deploy with a Liberator **with the default internal attachment**: the Recoil Spring overwrites all three rate
   slots when the weapon is built. The weapon is built when you deploy, so a Liberator already in hand keeps its old
   data.
3. Fire: 450 rpm (slower than vanilla 640). Open the weapon-function menu: is there a new rate-of-fire entry? Press
   it: 700 rpm; again: 950 rpm; again: 450.
4. Check fire modes (Automatic / Single / Burst) still switch, and that reload, magazine and handling are unchanged.
5. Move a slider, APPLY, get a freshly built Liberator (be reinforced), and check only that rate changed.
6. Turn **Enabled** off, APPLY, get a fresh Liberator: one rate of 640 and no rate-of-fire entry.

Report whether the selector appears, what its label and rates are, and anything unexpected (for example the selector
showing but not changing the rate). The mechanism is proven natively, but binding a selector the weapon does not
have natively is its first live test (`allow_unverified_effect`).
