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
- Weapon movement restriction while firing (`weapon.stationary_while_firing`, the Maxigun's stationary
  firing) on every resolved player and support weapon (see `docs/weapon-movement.md`)
- Minefield explosions for all four mine stratagems (`hd2.stratagem(name):mine()`), and Cremator, EAT-17 and
  LAS-98 damage authoring
- Sentry turret motion and targeting range (`hd2.stratagem(name):deployed_entity():turret()` / `:targeting()`),
  and every sentry's deployed lifetime (see `docs/stratagem-authoring.md`)
- Status effects as typed references on every player, support and mounted-weapon damage object: swap the
  status an attack applies or attach one to an attack that has none (see `docs/status-effects.md` and
  `sdk/StatusEffectCatalog.json`)
- Enemy and enemy-structure health, armor and damage zones (`hd2.enemy(name)`, `hd2.structure(name)`,
  `:zone(name)`) for 177 hash-verified native classes, named by wiki name only where the anatomy proves it, and
  169 mounted-weapon attacks on 38 classes (`:attack(name)`: their damage, projectile and explosion rows) reached
  through each class's own mount chain (see `docs/enemy-authoring.md` and `sdk/EnemyAuthoringCapabilities.json`)
- Minefield salvo count and mines per salvo (`hd2.stratagem(name):deployed_entity():minefield()`, reductions only)
- Central live-test evidence: every in-game test, its result and the capability families it promoted to
  live-proven (see `docs/live-evidence.md` and `sdk/LiveEvidenceCatalog.json`)
- Attack outputs (`hd2.attack_output(name)`, `attack:output()`): a family-aware catalog of what every weapon attack
  emits. A magazine-fed projectile weapon can fire another weapon's projectile output (for example the EAT-700
  napalm rocket) and keep its own magazine and fire control. Beam and arc outputs are catalogued with the reason no
  projectile weapon can reference them (see `docs/attack-outputs.md` and `sdk/AttackOutputCapabilities.json`)
- Rate-of-fire modes (`hd2.fields.fire_rate.modes`, `weapon:fire_rate_modes()`): the three native rate slots in the
  order the weapon menu lists them (MG-206 `{450, 600, 750}`, starting on the middle one), and up to three
  selectable rates on weapons without a selector, through the game's own ROF weapon function (see
  `docs/fire-rate-modes.md`)
- Weapon feeds (`weapon:feeds()`, `hd2.fields.function_ammo.projectile`): the SG-20 Halt's two magazines as separate
  targets, and a second, player-selectable projectile through the native ProgrammableAmmo function (for example a
  Speargun with a gas mode and an EMS stun-field mode). Each mode's native label and icon can be set
  (`hd2.fields.presentation.mode_label` / `mode_icon` on `hd2.attack_output(...)`; see `docs/weapon-feeds.md`)
- Armory presentation (`hd2.fields.presentation.armor_penetration`, `hd2.fields.presentation.traits`): the trait
  labels the menus show, independent of gameplay (see `docs/weapon-presentation.md`)
- Cross-family output research: why a projectile weapon cannot fire a beam, with the exact native blockers
  (`sdk/OutputCompositionCapabilities.json`)
- Guarded patches, transactions and multi-object plans; `hd2.ensure` can recover by itself when the game's data was
  not ready or moved under a check (`recover`), and report every status change (`on_status`) (see `docs/options.md`)
- In-game options: sliders, choices and toggles on the MODS tab (CowboyBingus Mod Options Menu)
  that drive one ensured operation live, with the same guards
- Services for UI and game mods (development line, not live-tested): screen overlays (`hd2.ui.overlay`, see
  `docs/ui-overlay.md`), game sound events (`hd2.sounds.play`; every Wwise event of the game catalogued by family,
  bank and kind, its bank loadable, pause / resume / is_playing / elapsed and per-sound game parameters and switches,
  see `docs/sounds.md`), any key's state
  (`hd2.input.down` / `pressed` / `released`), a per-frame callback (`hd2.on_frame`), per-mod saved data
  (`hd2.store`, see `docs/mod-store.md`), the game build status (`hd2.build()`) and the live values of the weapon in
  hand (`player:weapon_state()`, see `docs/player-equipment.md`)
- Generated SDK metadata for tools such as HD2RuntimeGUI

Unsupported or ambiguous values remain read-only rather than being modified speculatively.

The development line 0.30.0-dev (not released) turns custom stratagems into a development API
(`docs/custom-stratagem-api.md`; solo host only). It adds a startup progress display and a builder-facing
custom-stratagem schema and project format (`docs/custom-stratagem-builder.md`). See `docs/releases/0.30.0-dev.md`.

Version 0.28.1 is a compatibility and stability release. Mods built with SDK 0.27 keep working: an operation
that leaves out an `allow_unverified_effect` that 0.28.0 added to a field (the PLAS-101 Purifier and five other
weapons, 144 fields; the SH-51 body) is applied as a logged legacy operation when the mod declares an older SDK.
Mods that declare SDK 0.28.0 or later keep the rule. `hd2.diagnostics.operations()` lists every registered
operation, refused ones included, and the packaged validator now fails a scenario when a write it expects is
refused or skipped. See `docs/releases/0.28.1.md` and `docs/legacy-sdk-compatibility.md`.

Version 0.28.0 adds event-driven gameplay scripting and one projectile system:
- **Scripting.** Mods react to missions, players, entities, combat and the weapon in hand (`hd2.events`,
  `hd2.mod`). They can heal the local player and, hosting, spawn catalogued explosions and projectiles or apply
  statuses.
- **Projectiles.** Primary, secondary, support and mounted weapons share one projectile host rule and one donor pool.
  A projectile builder re-points a row's direct hit and explosions. Host swaps and row writes stay separate,
  explicit operations.
- **Coverage.** Rate-of-fire modes, weapon feeds and programmable ammo, armory presentation, Resupply, underbarrel
  weapons, Guard Dogs, shields, packs, sentries, minefields, enemies and structures.
- **Fixes and diagnostics.** It fixes the SG-20 Halt bug that dropped a mod's other edits, isolates every
  operation, and adds write-conflict diagnostics and opt-in telemetry.

Live proof is recorded exactly, per target and value. Custom projectile rows owned by Runtime are later work. See
`docs/releases/0.28.0.md`.

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
