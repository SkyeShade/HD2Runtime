# HD2Runtime

HD2Runtime is a modding runtime and API for Helldivers 2, running on Bingus Shared Loader.

It lets mods change weapons, stratagems, enemies, projectiles, damage, explosions and much more by name, for example
`hd2.weapon('AR-23 Liberator')`, without working with memory addresses, record offsets or resource IDs.

Every change is guarded. If HD2Runtime cannot verify a game structure, or who else shares it, the write is refused
and logged instead of being guessed. Values that are not fully understood stay read-only.

## Requirements

- Helldivers 2
- Bingus Shared Loader v15+
- Optional, only for mods with in-game options: CowboyBingus Mod Options Menu v1+ (with Bingus Shared Loader v18+)

## Installation

1. Download `HD2Runtime-<version>-runtime.zip` from the releases page.
2. Install it through the same mod directory you use for Bingus Shared Loader.

HD2Runtime is installed once and shared by every mod that depends on it. Mods do not bundle their own copy.

## What you can change

**Weapons**

- Primary, secondary and support weapons: fire rate, ammo, reload, heat, charge, beam and arc fields
  (`docs/player-weapon-authoring.md`, `docs/support-weapon-api.md`, `docs/reload-heat-controls.md`)
- Melee: hit volumes, repeat hits, damage and stamina for every melee weapon and gun bash (`docs/knife-melee.md`)
- Projectiles, damage and armor penetration, explosions and status effects (`docs/explosions.md`,
  `docs/status-effects.md`)
- Attachments: magazines, muzzles, optics and underbarrels (`docs/magazine-attachments.md`,
  `docs/weapon-attachments.md`)
- Fire modes, rate-of-fire modes, weapon feeds and selectable ammo (`docs/fire-modes.md`, `docs/fire-rate-modes.md`,
  `docs/weapon-feeds.md`)
- Firing another weapon's projectile, such as the EAT-700 napalm rocket (`docs/attack-outputs.md`)
- Third-person reticles, armory trait labels and stationary firing (`docs/weapon-reticles.md`,
  `docs/weapon-presentation.md`, `docs/weapon-movement.md`)

**Stratagems and equipment**

- Orbital and Eagle stratagems, call-in cooldowns, mission uses (including unlimited) and calldown codes
  (`docs/stratagem-authoring.md`, `docs/stratagem-uses.md`)
- Custom stratagems, with a builder schema and project format (`docs/custom-stratagem-api.md`,
  `docs/custom-stratagem-builder.md`)
- Sentries, emplacements and minefields, including turret motion, targeting range and lifetime
- Drop-pod contents (`docs/pod-payloads.md`)
- Vehicles and Exosuits: durability, damage zones and mounted weapons (`docs/vehicle-authoring.md`,
  `docs/vehicle-weapons.md`)
- Backpacks, shields and backpack-fed ammo (`docs/backpack-authoring.md`, `docs/backpack-ammo.md`)
- Boosters (19 of 20) and all 23 throwables, including launch, spin, four statuses and arming delay
  (`docs/booster-authoring.md`, `docs/throwable-authoring.md`, `docs/throwable-statuses.md`)

**Enemies and players**

- Enemy and structure health, armor, damage zones and mounted attacks (`docs/enemy-authoring.md`), plus size,
  shields, jammers and spawners for all 1,178 enemies and structures (`docs/enemy-controls.md`)
- Spawning and destruction: mission difficulty budgets, spawn rosters and compositions, breach schedules,
  demolition templates (`docs/enemy-controls.md`)
- Missions: timer durations (up to the game's 41:40) and a host-controlled timer freeze (`docs/missions.md`)
- Helldiver movement, stamina and body-zone damage, not live-tested (`docs/helldiver-fields.md`)
- Armor rating, speed, stamina, passives and armor perks, not live-tested (`docs/armor-stats.md`,
  `docs/armor-passives.md`)

**Scripting and services**

- Events: react to missions, players, kills and the weapon in hand (`docs/event-scripting.md`)
- In-game options on the MODS tab through Mod Options Menu (`docs/options.md`)
- Screen overlays, game sounds, key input, per-frame callbacks and saved data, not live-tested (`docs/ui-overlay.md`,
  `docs/sounds.md`, `docs/mod-store.md`)
- Optional pre-fire homing locks, speed-aware steering and configurable lock reticles, generic integration not live-tested (`docs/homing-lock-on.md`)
- Keybinds on the game's own Controls page (MODS tab) through Mod Bindings Menu (`docs/events.md`)
- The game's own item names in the player's language, read-only (`docs/game-text.md`)

**Safety and tooling**

- Guarded patches, transactions and multi-object plans; `hd2.ensure` can recover when game data moves
  (`docs/options.md`, `docs/transaction-ensure.md`)
- Shared-object detection: a change that affects other items needs `allow_shared`
- Automatic asset loading for swaps that point at an item nobody carries (`docs/asset-loading.md`)
- `hd2.inspect` to see values other mods changed
- Live-test evidence for every capability (`docs/live-evidence.md`)
- Generated SDK metadata for tools such as HD2RuntimeGUI

Features marked "not live-tested" are mapped and validated offline but have not been confirmed in game yet. Some of
them require an `allow_unverified_effect` acknowledgement; the SDK capability files list exactly which.

## Creating mods

New to HD2Runtime? Start with `docs/getting-started.md`. It explains which ZIP you need and walks through your
first mod.

The quickest way to start is the mod template:

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
`hd2.fields.weapon.fire_rate`). Armor penetration is four per-angle fields, and baselines differ between weapons:
always take `expect` from the SDK for the exact weapon.

More help:

- `HD2Runtime-<version>-sdk.zip`: the capability files (everything you can edit, with vanilla values and required
  flags), the docs and editor stubs
- `HD2Runtime-<version>-example-projects.zip`: small working mods, such as `LiberatorDamageTransaction`
- Release notes for every version: `docs/releases/`

## License and credit

HD2Runtime is free to use for building mods; see [LICENSE](LICENSE) for the full terms. Copying its code or research
findings (offsets, field names, identities, catalogues) into another project is allowed only with visible credit to
[HD2Runtime by SkyeShade](https://github.com/SkyeShade/HD2Runtime). Redistributing HD2Runtime itself needs
permission.

### Thanks

- [Bans](https://ayakamods.com/members/bans.388863/), author of
  [True Lasgun Beam Overhaul](https://ayakamods.com/mods/true-lasgun-beam-overhaul.4681/) (LAS Beam Enhanced
  Overhaul): his mod was the research lead for the 0.31.0 laser work: the heat weapons' wind-up (firing charge), the
  LAS-13 Trident's pulsed beam and its fire mode, and the pass that made every laser beam swappable. HD2Runtime
  proves each member itself from the game's data; none of his code is used.
