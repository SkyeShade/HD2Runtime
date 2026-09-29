# Rate-of-fire modes

A weapon's rate of fire is not one value. It is three slots in the weapon's own `ProjectileWeaponComponentData`
record, and a weapon whose rate-of-fire selector is bound (the MG-206 Heavy Machine Gun, for example) cycles through
them. Runtime edits those slots directly, and can give a weapon without a selector the same selector the game uses.

```lua
-- MG-206: native 450 / 600 / 750 rpm. Each rate edited on its own (see examples/projects/HMGFireRateModesTest).
local hmg=hd2.support_weapon('MG-206 Heavy Machine Gun')
hd2.ensure({patch={id='hmg-rates',target=hmg,field=hd2.fields.fire_rate.modes,
    expect=hmg:fire_rate_modes().expect,value={200,700,1400},allow_unverified_effect=true}})

-- AR-23 Liberator: one rate (640) -> three selectable rates, one transaction (AddedFireRateModeTest).
local liberator=hd2.weapon('AR-23 Liberator')
local rates=liberator:fire_rate_modes()
hd2.ensure({transaction={id='liberator-rates',target=liberator,allow_unverified_effect=true,changes={
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
  weapon's current rate and is replicated. The record starts zeroed and is seeded when the weapon is built; in every
  mission snapshot it holds the settings' slots with index 1. So the default is Y and **the selector visits Y, Z, X**.
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
| `modes` | `{index, rpm, slot, default, enabled}` in selector order; `modes[1]` is the default |
| `expect` | the reviewed rate list, the `expect` of `fire_rate.modes` |
| `maxModes` | 3 where a selector is bound or bindable, otherwise 1 |
| `selector` | `{bound, input, bindableInputs}` |
| `binding` | for `addable` weapons, the `weapon_function` change to add in the same transaction |
| `writable`, `reason`, `range`, `acknowledgements`, `overriddenWhenEquipped` | |

`weapon:fire_rate_mode(n)` returns one mode.

| Field | Value |
| --- | --- |
| `hd2.fields.fire_rate.modes` | Ordered list of 1 to 3 rates (rpm, 1 to 3000) in selector order; the first is the default |
| `hd2.fields.weapon_function.left` / `.right` | `'none'`, or on an unbound input a selector this weapon can host: `'rate_of_fire'` (or `'programmable_ammo'`, see [weapon feeds](weapon-feeds.md)) |

- **Writing.** The list is written as its three aligned slots in one atomic transaction; every slot is
  conflict-checked and only changed slots are written, so editing one mode never touches the others.
- **Selector pairing.** A weapon without a selector takes more than one rate only in the same transaction as its
  rate-of-fire binding, and the binding only together with two or more rates (`SELECTOR_REQUIRED` otherwise). Nothing
  written is ever dormant. The three fields share one operation group (`weapon_selector`) for plans and tools.
- **Acknowledgement.** `allow_unverified_effect`: the slots, the traversal and the binding are proven, but editing
  and adding rates is not gameplay-tested yet.
- **Scope.** Weapon-local: every record has one owner.
- **When it applies.** The rates and the binding are copied into a weapon when the game builds it; a weapon already
  built keeps its copy until it is rebuilt (call in a fresh one, redeploy or be reinforced).
- **Older field.** `weapon.fire_rate` is unchanged: the default (Y) rate. It covers the same bytes, so it cannot be
  combined with `fire_rate.modes` in one plan.

## Coverage

| State | Player | Support |
| --- | ---: | ---: |
| `selectable` | 1 (AR-61) | 3 (MG-206, MG-43, M-105) |
| `addable` | 48 | 8 |
| `blocked` | 19 | 12 |
| `absent` | 12 | 12 |

60 weapons are writable (`sdk/WeaponFireRateCapabilities.json`). The GL-28 has a bound selector (160/240/320) but
stays read-only, like its `weapon.fire_rate`: the support catalog treats its rate as a diagnostic selector. Blocked weapons are those the fire-mode research
blocks (charge, wind-up, beam, arc, spray and melee triggers, charge or safety modes, special trigger functions such
as Magazine or ProgrammableAmmo on the other input, special fire-control structures) and ambiguous identities.

## Validation

- `scripts/validate_weapon_modes_snapshot.py` (`validation/weapon-modes-snapshot.json`) exercises every writable
  weapon on a copy-on-write overlay of the retained snapshot: guarded no-op, one mode edited alone (one slot written),
  two added rates with the binding (three writes), exact read-back and rollback, CONFLICT on a third-party slot value,
  and the acknowledgement. Adversarial: a fourth rate, zero, negative, non-finite and out-of-range rates, rates
  without their selector and a selector without rates are refused; blocked weapons refuse writes; `fire_rate.modes`
  and `weapon.fire_rate` never share a plan. It pins the MG-206 edit (X 450 -> 1400, Y 600 -> 200, Z 750 -> 700,
  12 bytes) and the Liberator's added modes (X 950, Y 450, Z 700, left input = ROF).
- The packaged-runtime scenarios `example-hmgfire-rate-modes-test` and `example-added-fire-rate-mode-test` run the
  live-test mods from the built runtime ZIP: each slider writes exactly its own slot, disable restores the baseline,
  and a simulated reset re-applies.

## Live tests

`HMGFireRateModesTest` (three sliders, one per native mode) and `AddedFireRateModeTest` (the Liberator gains a
three-rate selector). See their READMEs for what to check.
