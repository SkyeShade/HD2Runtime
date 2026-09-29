# HD2Runtime

HD2Runtime is a modding runtime and API for Helldivers 2 mods using Bingus Shared Loader.

It provides semantic access to mapped game systems so mods can modify weapons, stratagems, deployed entities, projectiles, damage, explosions and other values without manually working with memory addresses, native record offsets or resource IDs.

HD2Runtime is designed to fail safely when a game structure or ownership relationship cannot be verified.

## Features

- Player weapon authoring
- Support weapon authoring
- Orbital and Eagle stratagem authoring
- Support-weapon call-in cooldowns
- Sentry and emplacement authoring
- Vehicle durability, damage zones and mounted-weapon swaps
- Vehicle and Exosuit mounted-weapon stats (fire rate, magazines, reload, mount health/armor, rounds)
- Backpack authoring (Jump Pack, Hover Pack, shields) and backpack-fed ammo (Maxigun, Cremator, GL-28)
- Shield Generator Relay shield radius and health
- Magazine attachments: every resolved magazine option's ammo, reload duration and ergonomics
- Third-person reticles and native fire-mode sets (for example, adding full-auto)
- Stratagem mission uses, including the game's real unlimited value
- Drop-pod contents: replace the items a support, backpack or Resupply pod opens with, and the spawn count
- Deployed entity health and armor
- Projectile, damage and explosion editing
- Ammo, heat, charge, beam, arc and status fields
- Shared-object detection and acknowledgement
- Booster authoring for 19 of 20 boosters: native Booster definition table scalars, hellpod-impact explosions,
  stim and Dead Sprint statuses, the Surplus EAT stratagem, and the Armed Resupply Pods turret
- Throwable authoring for all 23 throwable-slot items (`hd2.throwable`): inventory counts, fuses,
  explosions, per-hit status and shared status definitions, frag shrapnel, Pineapple bomblets, the throwing
  knife's direct hit, mine health and the throwable shield (see `docs/throwable-authoring.md`)
- Automatic asset loading for reference swaps: the packages of pod pickups, mounted weapons and borrowed
  projectiles load through the game's own package system before the write, with no package IDs in mods
  (see `docs/asset-loading.md`)
- Guarded patches, transactions and multi-object plans
- In-game options: sliders, choices and toggles on the MODS tab (CowboyBingus Mod Options Menu)
  that drive one ensured operation live, with the same guards
- Generated SDK metadata for tools such as HD2RuntimeGUI

Unsupported or ambiguous values remain read-only rather than being modified speculatively.

Version 0.27.0 loads assets automatically for cross-package reference swaps. When a swap points at an item
nobody carries (an EAT-700 in a Stalwart pod, Talon projectiles on the Reprimand, a Grenade Box in the MG-43
pod), Runtime loads that item's package through Helldivers 2's own package loader first, waits until it is
resident, and only then writes. If it cannot, the write fails safely with `ASSET_UNAVAILABLE`. These three
cases were live-tested. It also adds throwable authoring for all 23 throwable-slot items. See
`docs/releases/0.27.0.md` and `docs/asset-loading.md`.

Version 0.26.1 is a documentation and example correctness release. The examples, ModTemplate, SDK project
templates and getting-started guide now teach the current typed API (damage on the projectile, per-angle armor
penetration, patch vs transaction vs plan), and every shipped example is validated against the current SDK on
each release. It also adds offline game-update migration tooling: after a Helldivers 2 patch,
`docs/game-update-migration.md` walks through re-proving every mapping, recovering safe ones automatically
and downgrading the rest to read-only. See `docs/releases/0.26.1.md`.

Version 0.26.0 adds every magazine option (reload and ergonomics too), third-person reticles, native
fire-mode sets, vehicle and Exosuit mounted weapons, stratagem mission uses (including unlimited),
backpack-fed support-weapon ammo, and drop-pod payload slots. Most new fields are natively proven but
not yet live-tested, and require the published acknowledgements. See `docs/releases/0.26.0.md`, and
`docs/magazine-attachments.md`, `docs/weapon-reticles.md`, `docs/fire-modes.md`,
`docs/vehicle-weapons.md`, `docs/stratagem-uses.md`, `docs/backpack-ammo.md` and `docs/pod-payloads.md`.

Version 0.25.1 publishes the stratagem icon identity metadata (`uiIcon`) that 0.25.0 omitted.
It also makes Mod Options Menu a true enhancement: without it, option-bound operations run with
their declared defaults (or stay inactive with `fallback='disable'`). See `docs/releases/0.25.1.md`.

Version 0.25.0 makes 19 of 20 Boosters writable through natively traced targets and adds
in-game options (`hd2.options`) bound to ensured operations, confirmed in game, with CowboyBingus
Mod Options Menu as an optional dependency. See `docs/releases/0.25.0.md`.

Version 0.24.0 expands support-weapon authoring to 31 weapons (reload, projectile lifetime and
penetration slowdown, Maxigun wind-up, and four delivery-resolved identities) and adds Booster
authoring (`hd2.booster`). See `docs/releases/0.24.0.md`.

Version 0.23.2 is a critical hotfix. In 0.23.0 and 0.23.1, typed writes could fail in game with
"module not found" once startup had finished. See `docs/releases/0.23.2.md`.

Version 0.23.1 adds guarded magazine-attachment authoring: per-attachment capacity and magazine counts
for weapons whose ammo is owned by selectable magazines (for example, the Liberator Concussive drum).
See `docs/releases/0.23.1.md`.

Version 0.23.0 adds guarded vehicle durability and mount swapping (`hd2.vehicle`), backpack authoring
(`hd2.backpack`), and the Shield Generator Relay's shield as a separate target. Example projects recreate
ShieldRelayImprovements, BastionReArmored, FRVWeaponSwap, and JumpPackImprovements through the public API;
see `docs/releases/0.23.0.md`.

Version 0.22.1 publishes explicit, bidirectional support-weapon <-> call-in stratagem linkage
(stable semantic IDs, `linkedStratagem`, `delivers`, and `supportCallInLinks`) in the SDK capability
catalogs. Runtime write semantics are unchanged; see `docs/releases/0.22.1.md`.

## Requirements

- Helldivers 2
- Bingus Shared Loader v15+
- Optional, only for mods that use in-game options: CowboyBingus Mod Options Menu v1+ (with Bingus
  Shared Loader v18+)

## Installation

Install the HD2Runtime runtime ZIP through the same mod directory used by Bingus Shared Loader.

HD2Runtime is installed once and shared by gameplay mods that depend on it.

Gameplay mods do not need to bundle their own copy of the runtime.

## Creating Mods

The easiest way to create a project is with the included mod template.

1. Extract `HD2Runtime-ModTemplate-<version>.zip`
2. Open the folder in Rider
3. Change the mod name and resource ID
4. Edit `src/addon.lua`
5. Run `build.cmd`

Example:

```lua
local hd2 = require('mods/skyeshade/hd2runtime')

-- Damage belongs to the projectile the weapon fires, not to the weapon itself.
local projectile = hd2.weapon('AR-23 Liberator'):attack('primary'):projectile()

-- Six fields of one DamageInfo record: one transaction. expect values are this weapon's
-- baselines from PlayerWeaponAuthoringCapabilities.json; the record is shared with the
-- AR-23A Liberator Carbine and StA-52, so allow_shared is required.
return hd2.ensure({
    transaction = {
        id = 'liberator-damage',
        target = projectile,
        allow_shared = true,
        changes = {
            {field = hd2.fields.damage.player_standard_damage, expect = 90, value = 120},
            {field = hd2.fields.damage.player_durable_damage,  expect = 22, value = 35},
            {field = hd2.fields.damage.ap_direct,  expect = 2, value = 3},
            {field = hd2.fields.damage.ap_slight,  expect = 2, value = 3},
            {field = hd2.fields.damage.ap_large,   expect = 2, value = 3},
            {field = hd2.fields.damage.ap_extreme, expect = 0, value = 2},
        },
    },
})
```

Weapon-local values such as fire rate are on the weapon itself (`hd2.weapon('AR-23 Liberator')`,
`hd2.fields.weapon.fire_rate`). Armor penetration is four per-angle fields, and baselines differ
between weapons: always take `expect` from the SDK for the exact weapon. See `docs/getting-started.md`
and the `LiberatorDamageTransaction` example project.
