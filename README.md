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
- Backpack authoring (Jump Pack, Hover Pack, shields)
- Shield Generator Relay shield radius and health
- Magazine attachment capacity and magazine counts
- Deployed entity health and armor
- Projectile, damage and explosion editing
- Ammo, heat, charge, beam, arc and status fields
- Shared-object detection and acknowledgement
- Booster authoring where a booster links to native data (Armed Resupply Pods turret, Experimental Infusion stim buff)
- Guarded patches, transactions and multi-object plans
- Generated SDK metadata for tools such as HD2RuntimeGUI

Unsupported or ambiguous values remain read-only rather than being modified speculatively.

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

local weapon = hd2.weapon('JAR-5 Dominator')

hd2.patch({
    target = weapon:projectile():damage(),
    field = hd2.fields.damage.armor_penetration,
    expect = 3,
    value = 4,
})
