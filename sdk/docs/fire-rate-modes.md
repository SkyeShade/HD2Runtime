# Rate-of-fire modes

A weapon's rate of fire is not one value. It is three slots in the weapon's own `ProjectileWeaponComponentData`
record, and a weapon whose rate-of-fire selector is bound (the MG-206 Heavy Machine Gun, for example) cycles through
them. Runtime edits those slots directly, and can give a weapon without a selector the same selector the game uses.

`hd2.fields.fire_rate.modes` is the three slots **in the order the weapon menu lists them**, `{X, Y, Z}`, with 0 for
an empty slot. The middle one (Y) is the rate a weapon is built on; each selector press moves to the next filled
slot, Y -> Z -> X -> Y.

```lua
-- MG-206: native {450, 600, 750} rpm, as its menu lists them; it starts on 600. Each rate edited on its own
-- (see examples/projects/HMGFireRateModesTest). Live-proven on the MG-206: no acknowledgement.
local hmg=hd2.support_weapon('MG-206 Heavy Machine Gun')
hd2.ensure({patch={id='hmg-rates',target=hmg,field=hd2.fields.fire_rate.modes,
    expect=hmg:fire_rate_modes().expect,value={300,550,1200}}})

-- AR-23 Liberator: one rate {0, 640, 0} -> three selectable rates listed 450 / 700 / 950, starting on 700, one
-- transaction (AddedFireRateModeTest). Live-proven on the Liberator's left input: no acknowledgement.
local liberator=hd2.weapon('AR-23 Liberator')
local rates=liberator:fire_rate_modes()
hd2.ensure({transaction={id='liberator-rates',target=liberator,changes={
    {field=hd2.fields.fire_rate.modes,expect=rates.expect,value={450,700,950}},
    {field=rates.binding.field,expect='none',value='rate_of_fire'}}}})
```

## Native model

Proven on build F5FEE03DCFDB (`scripts/research_weapon_functions.py`, `research/weapon-functions-F5FEE03DCFDB.json`),
from the type library, the entity table, game.dll code and the retained snapshots.

| Member | Meaning |
| --- | --- |
| ProjectileWeaponComponent +4 `rounds_per_minute` (three f32: X +4, Y +8, Z +12) | The weapon's rates. Y is the default and the only rate of a weapon without a selector (the existing `weapon.fire_rate`) |
| WeaponDataComponent +184 `function_info {left, right}` | The WeaponFunctionType bound to each weapon-function input; `ROF` (2) is the rate-of-fire selector |

- **The selector** (game.dll 0x617960): each built projectile weapon has a 0x20-byte runtime record in the
  projectile_weapon manager holding a copy of its rate slots and a current index. Each press sets
  `index = (index + 1) mod 3` and skips a slot whose rate is 0.0, at most three times; the chosen rate becomes the
  weapon's current rate and is replicated. The record starts zeroed and is seeded when the weapon is built (game.dll
  0x6117C0: the settings' slots times the mission factor, index 1). Right after, 0x611990 replaces the index with the
  player's saved rate setting for that weapon type (0x878CB0: its customization record, +0x84 block +0xC), or keeps 1
  when the weapon has no saved setting (research 2026-10-06, offline: the VG-70 Variable's record holds a saved 2; no
  retained snapshot has one for the MG-43). So the default is Y unless the player saved another rate, and **the
  selector visits Y, Z, X**.
- **`hd2.fields.weapon.fire_rate` on such a weapon** writes only its Y slot (the middle mode): its X and Z modes stay
  vanilla, and a player whose saved setting is X or Z starts on an unchanged mode. Change every mode with
  `hd2.fields.fire_rate.modes` (all three slots); a custom stratagem's per-call `rpm` is refused for these weapons.
- **The menu order** is the storage order X, Y, Z (filled slots only), with the default in the middle. This is
  inferred, not traced: in the first live tests (MG-206 and Liberator, 2026-09-30) a list in selector order did not
  match what the menu showed, and the only code that reads the slots by index walks them X, Y, Z. The menu reader
  itself was not found.
- **The binding** is read from the built weapon (the weapon-function value reader, 0x755BA0, switches on the bound
  function type: ROF reads the rate index).
- **The storage is fixed.** Three rates is the most a weapon can have; a fourth cannot exist. A 0.0 slot is an absent
  mode. Adding a mode fills an empty slot of the weapon's own record: no array grows, nothing is reallocated, no
  neighbouring record is touched.
- **Customization** can overwrite all three slots when a weapon is built: Recoil Spring Liberator (0/680/0), Recoil
  Spring Patriot, Laser Blaster Focus and one unnamed item. A weapon that can equip one publishes it in
  `overriddenWhenEquipped` (its effect is `AMBIGUOUS`). No customization touches `function_info`.

Native selectors: MG-206 (450/600/750), MG-43 (630/760/900), M-105 Stalwart (700/850/1150), GL-28 (160/240/320),
AR-61 Tenderizer (0/600/850: two modes, left input) and VG-70 Variable (read-only: charge/safety fire modes).

## API and fields

`weapon:fire_rate_modes()` (player and support weapons) returns the view a tool needs:

| Key | Meaning |
| --- | --- |
| `state` | `selectable` (selector bound), `addable` (a free input; rates beyond the default need the binding), `single_rate` (both inputs bound: one rate), `blocked`, `absent` |
| `modes` | the filled slots **in weapon-menu order** (X, Y, Z), each `{slot, index, rpm, enabled, default, menu, presses}`: `menu` is its menu position, `presses` the selector presses from the default (0 = the default) |
| `slots` | all three slots in storage order (the same tables; an empty slot has `enabled=false` and no `menu`) |
| `default` | the Y slot |
| `selectorOrder` | the filled slots in the order the selector visits them, from `y` |
| `expect` | `{X, Y, Z}`: the reviewed slots, the `expect` of `fire_rate.modes` |
| `maxModes` | 3 where a selector is bound or bindable, otherwise 1 |
| `selector` | `{bound, input, bindableInputs}` |
| `binding` | for `addable` weapons, the `weapon_function` change to add in the same transaction |
| `acknowledgements` | what a write of these rates (and, for `addable` weapons, the binding) must acknowledge: empty for a live-proven weapon |
| `liveProven` | the live evidence when this weapon's rates are live-proven |
| `writable`, `reason`, `range`, `overriddenWhenEquipped` | |

`weapon:fire_rate_mode(n)` returns the `n`-th mode of the menu; `weapon:fire_rate_mode('x' | 'y' | 'z')` a slot.

| Field | Value |
| --- | --- |
| `hd2.fields.fire_rate.modes` | The three slots in weapon-menu order `{X, Y, Z}` (rpm, 1 to 3000; 0 = no mode in that slot). Y, the middle one, is the default and is never 0 |
| `hd2.fields.weapon_function.left` / `.right` | `'none'`, or on an unbound input a selector this weapon can host: `'rate_of_fire'` (or `'programmable_ammo'`, see [weapon feeds](weapon-feeds.md); or `'fire_mode'`, see [fire modes](fire-modes.md#adding-the-selector-0304)) |

- **Writing.** The list is written as its three aligned slots in one atomic transaction; every slot is
  conflict-checked and only changed slots are written, so editing one mode never touches the others.
- **Selector pairing.** A weapon without a selector fills X or Z only in the same transaction as its rate-of-fire
  binding, and the binding only together with two or more filled slots (`SELECTOR_REQUIRED` otherwise). Nothing
  written is ever dormant. The three fields share one operation group (`weapon_selector`) for plans and tools.
- **Acknowledgement.** `allow_unverified_effect`, except where a live test proved the exact scope: the MG-206's
  `fire_rate.modes`, and the AR-23 Liberator's `fire_rate.modes` with `weapon_function.left = "rate_of_fire"`
  (`sdk/LiveEvidenceCatalog.json`). Every other weapon, and the Liberator's other bindings, keep it.
- **Scope.** Weapon-local: every record has one owner.
- **When it applies.** The rates and the binding are copied into a weapon when the game builds it; a weapon already
  built keeps its copy until it is rebuilt (call in a fresh one, redeploy or be reinforced).
- **Older field.** `weapon.fire_rate` is unchanged: the default (Y) rate. It covers the same bytes, so it cannot be
  combined with `fire_rate.modes` in one plan.

## Coverage

| State | Player | Support |
| --- | ---: | ---: |
| `selectable` | 1 (AR-61) | 3 (MG-206, MG-43, M-105) |
| `addable` | 48 | 9 (the M-1000 Maxigun among them: see [Wind-up weapons](#wind-up-weapons-the-m-1000-maxigun)) |
| `blocked` | 19 | 11 |
| `absent` | 12 | 12 |

61 weapons are writable (`sdk/WeaponFireRateCapabilities.json`). The GL-28 has a bound selector (160/240/320) but
stays read-only, like its `weapon.fire_rate`: the support catalog treats its rate as a diagnostic selector. Blocked weapons are those the fire-mode research
blocks (charge, beam, arc, spray and melee triggers, charge or safety modes, special trigger functions such
as Magazine or ProgrammableAmmo on the other input, special fire-control structures) and ambiguous identities. A
wind-up trigger alone no longer blocks the rate (below); its fire modes and function projectile stay blocked.

## Wind-up weapons (the M-1000 Maxigun)

A conventional projectile weapon whose only special trigger is a wind-up (`WeaponWindUpComponentData`: of the player
and support weapons, only the M-1000 Maxigun) gets the same rate-of-fire modes and `rate_of_fire` binding as every
other weapon, **always behind `allow_unverified_effect`**. Offline only / not live-tested.

```lua
local maxigun = hd2.support_weapon('M-1000 Maxigun')
local rates = maxigun:fire_rate_modes()   -- state 'addable', expect {1500, 1500, 1500}, binding weapon_function.left
hd2.transaction({
    id = 'maxigun-rate-menu',
    target = maxigun,
    allow_unverified_effect = true,       -- required: the wind-up trigger path is not proven to fire the selected slot
    changes = {
        {field = hd2.fields.fire_rate.modes, expect = {1500, 1500, 1500}, value = {750, 1500, 2500}},
        {field = hd2.fields.weapon_function.left, expect = 'none', value = 'rate_of_fire'},
    },
})
```

- **Dormant slots.** The Maxigun stores its rate in all three slots (1500/1500/1500) with no selector bound, so no menu
  lists X or Z (`fire_rate_modes()` shows Y only and marks X and Z `dormant`). A write sets X and Z explicitly with the
  binding (as above), or clears them (`{0, 1200, 0}` changes the rate alone); writing the reviewed `{1500, 1500, 1500}`
  back is accepted without a binding. Rates in X or Z without the binding are refused (`SELECTOR_REQUIRED`), as on
  every weapon. Other weapons with dormant slots (LAS-99 Quasar Cannon) stay read-only.
- **What is proven offline.** The three rate slots and the ROF selector record (the projectile_weapon manager keeps one
  record per built projectile weapon, seeded from the settings' three slots; the selector and the weapon-function value
  reader are data-driven over it), and the wind-up routine (0x78A420, research/sentry-components) reads only its own
  settings: +0 wind-up time, +4 a spin-down switch (0.30.4: 0 stops the barrels at once, any positive value spins
  down over the +0 wind-up time; research/windup-controls-F5FEE03DCFDB.json), +12 barrel-spin multiplier.
- **What is not.** That the wind-up trigger path fires at the selected slot's rate once spun up: no built wind-up weapon
  is in a retained mission snapshot, and the research shows no reader of the current rate on that path. A third-party
  mod that writes the Maxigun's rate menu is reported to work in game; that is a lead, not proof. Hence the
  acknowledgement on `fire_rate.modes` and on the binding, whatever the values.
- **Unchanged.** Charge, beam, arc, spray and melee weapons stay blocked; the Maxigun's fire modes
  (`fire_mode.modes`) and function projectile are not authored. `weapon.fire_rate` (slot Y) is as before.

## Validation

- `scripts/validate_weapon_modes_snapshot.py` (`validation/weapon-modes-snapshot.json`) exercises every writable
  weapon on a copy-on-write overlay of the retained snapshot: guarded no-op, one mode edited alone (one slot written),
  two added rates with the binding (three writes), exact read-back and rollback, CONFLICT on a third-party slot value,
  and the acknowledgement (or, on a live-proven weapon, the write without it). The Maxigun (wind-up) is exercised
  like the others, with its dormant X and Z: its reviewed slots are a no-op without a binding, its rates without the
  acknowledgement are refused. Adversarial: lists that are not three
  slots, an empty default, negative, non-finite and out-of-range rates, rates without their selector and a selector
  without rates are refused; blocked weapons refuse writes; `fire_rate.modes` and `weapon.fire_rate` never share a
  plan. It pins the MG-206 edit (`{450, 600, 750} -> {1400, 200, 700}`, 12 bytes) and the Liberator's added modes
  (`{0, 640, 0} -> {950, 450, 700}`, left input = ROF).
- The packaged-runtime scenarios `example-hmgfire-rate-modes-test` and `example-added-fire-rate-mode-test` run the
  live-test mods from the built runtime ZIP: each slider writes exactly its own slot, disable restores the baseline,
  and a simulated reset re-applies.

## Live tests

`HMGFireRateModesTest` (three sliders, one per native mode, top to bottom as the menu lists them) and
`AddedFireRateModeTest` (the Liberator gains a three-rate selector). Both passed on 2026-09-30 with the slots in
selector order; this build lists them in menu order (the same bytes), and the next run confirms the menu order. See
their READMEs for what to check.
