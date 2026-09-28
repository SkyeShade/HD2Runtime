# Getting started: your first HD2Runtime mod

This guide is for people who have never made an HD2Runtime mod. It uses only the
mod template and the SDK files. You never need memory addresses, offsets, hashes,
or scanning.

## 1. The pieces

| Piece | What it is | Installed in the game? |
| --- | --- | --- |
| Bingus Shared Loader | Lets the game run Lua mods. At startup it finds installed mods and starts them. | Yes, once |
| HD2Runtime (`HD2Runtime-<version>-runtime.zip`) | A shared library mod. It finds game data, checks that it is safe to change, and does the change. It does nothing until a mod asks. | Yes, once |
| Your gameplay mod | A small Lua script that says "change this value from A to B". | Yes, one per mod |
| Mod template (`HD2Runtime-ModTemplate-<version>.zip`) | A ready project folder: your script, a build button, and editor autocomplete. | No |
| SDK (`HD2Runtime-<version>-sdk.zip`) | Reference kit: capability files, these docs, editor stubs, optional Python CLI. | No |
| Capability files (`*Capabilities.json` in the SDK) | Generated lists of everything you can edit: names, fields, vanilla values, writable or not, required safety flags, evidence. | No, you read them |

Every mod calls `require('mods/skyeshade/hd2runtime')` and shares one installed
runtime. Your built mod never contains the runtime. The game only needs Bingus
Shared Loader, HD2Runtime, and your built mod ZIP. Never install the template,
its `stubs` folder, or the SDK.

## 2. Set up on Windows

1. A mod manager such as Arsenal or HD2MM.
2. Bingus Shared Loader v15 or newer, imported and enabled. Keep it below other
   startup-replacement mods in the manager's order.
3. `HD2Runtime-<version>-runtime.zip`, imported and enabled once.
4. The mod template, extracted outside the game, for example
   `C:\HD2Mods\MyFirstMod\`.
5. An editor. The template is set up for Rider with a Lua plugin. LuaLS-style
   plugins read `.luarc.json`, which already points at `./stubs`.

You do not need Python, a Lua install, or the HD2Runtime source code to use the
template. Python 3.10+ is only needed for the optional SDK command line
(`hd2.py`).

## 3. Your first project

```
MyFirstMod\
  build.cmd          double-click to build
  build.ps1          the builder (leave alone)
  hd2runtime.json    name, mod ID, dependencies
  VERSION            your mod version, e.g. 0.1.0
  README.md          copied into your built ZIP
  src\addon.lua      YOUR MOD
  stubs\...          autocomplete only (leave alone)
  .luarc.json        editor settings (leave alone)
```

Open the folder itself in your editor, then change:

1. `hd2runtime.json` → `name`: your display name. It also becomes the ZIP name.
2. `hd2runtime.json` → `resource`: your permanent mod ID, `mods/<you>/<mod_id>`.
   Use letters, digits, and underscores only. Never change it after release; the
   mod manager GUID is derived from it.
3. `VERSION`: `major.minor.patch`.
4. `src/addon.lua`: your mod. Give each request its own short `id`.

Leave `build.cmd`, `build.ps1`, `.luarc.json`, `stubs`, the `bingus` block, and
`guid: "auto"` alone. Keep `requires.hd2runtime.min_version` at the template
version unless you know your mod uses nothing newer.

Build with `build.cmd`. The result is `build\<Name>-<VERSION>.zip`. Import that ZIP
into your mod manager and enable it.

The builder checks your work. For example, `src/addon.lua` must require
`'mods/skyeshade/hd2runtime'`, and must not contain a `-- HD2-Addon:` header
(the builder adds it).

## 4. The shape of a change

Every change answers five questions: which object, which field, what it is now,
what you want, and a name for the request.

```lua
local hd2=require('mods/skyeshade/hd2runtime')

return hd2.patch({
    id='concussive-fire-rate',                       -- your label
    target=hd2.weapon('AR-23C Liberator Concussive'), -- which object
    field=hd2.fields.weapon.fire_rate,               -- which value
    expect=400,                                      -- what it is now (vanilla)
    value=1100,                                      -- what you want
})
```

Some values live on a sub-object. For example, a bullet lives under
`weapon:attack('primary'):projectile()`, not on the gun.

## 5. Finding what you can edit

| Question | Look in |
| --- | --- |
| Primary and secondary weapons | `PlayerWeaponAuthoringCapabilities.json` |
| Support weapons | `SupportWeaponAuthoringCapabilities.json` |
| Stratagems, sentries, emplacements, Shield Relay, cooldowns | `StratagemAuthoringCapabilities.json` |
| Vehicles: health, damage zones, weapon mounts | `VehicleAuthoringCapabilities.json` |
| Backpacks | `BackpackAuthoringCapabilities.json` |
| Magazine attachments (round counts on weapons with selectable magazines) | `MagazineAttachmentCapabilities.json` |
| Boosters | `BoosterAuthoringCapabilities.json` |
| The Lua name of a field | `stubs/mods/skyeshade/hd2runtime.lua`, the `---@class HD2Fields_<domain>` blocks |
| Explanations | the other files in `docs/` |
| Working code | `examples/projects/*/src/addon.lua` in the example-projects ZIP |

### Worked trace

In `PlayerWeaponAuthoringCapabilities.json`, find `"AR-23 Liberator"`. One of its
fields is:

```json
{
  "semanticFieldId": "weapon.fire_rate",
  "currentDefault": 640,
  "editable": true,
  "writeScope": "weapon_local",
  "sharedWithWeapons": [],
  "reason": null
}
```

- Target: `hd2.weapon('AR-23 Liberator')`.
- Field: `weapon.fire_rate`, which is `hd2.fields.weapon.fire_rate`.
- `expect`: `640` (from `currentDefault`).
- Writable: `editable: true`. When it is `false`, `reason` says why.
- Scope: `weapon_local` means only this weapon changes. A field like
  `projectile.velocity` on the same weapon lists other weapons in
  `sharedWithWeapons`; editing it changes them too and needs `allow_shared=true`.

```lua
hd2.patch({id='lib-rpm',target=hd2.weapon('AR-23 Liberator'),
    field=hd2.fields.weapon.fire_rate,expect=640,value=800})
```

### Field IDs and Lua constants

Most field IDs map directly: `weapon.fire_rate` is `hd2.fields.weapon.fire_rate`.
When two catalogs use the same name, the newer constant gets a prefix:

| Field ID | Lua constant |
| --- | --- |
| `stratagem.cooldown` | `hd2.fields.stratagem.definition_cooldown` |
| `damage.standard_damage` (player weapons) | `hd2.fields.damage.player_standard_damage` |
| `shield.radius` (relay entity) | `hd2.fields.shield.entity_radius` |
| `payload.lifetime` (relay entity) | `hd2.fields.payload.entity_lifetime` |

The stratagem, support-weapon, vehicle, backpack, and magazine-attachment files
list the exact constant in `apiFieldConstant`. The player-weapon file does not;
search the stub file for the quoted field ID instead. Constants marked
"Deprecated compatibility alias" in the stub (for example
`hd2.fields.weapon.capacity`) point to a preferred constant; use that one.

### Two naming systems

HD2Runtime keeps a small original catalog with short names and fixed changes:
`'Bastion'`, `'Shield Relay'`, `'JAR-5 Dominator'`'s projectile damage,
`hd2.equipment('Jump Pack')`, `hd2.fields.shield.radius`. It still works, but it
only allows a few exact, reviewed changes.

For new mods, use the full catalog names from the capability files:
`'TD-220 Bastion MK XVI'`, `'FX-12 Shield Generator Relay'`,
`hd2.backpack('LIFT-850 Jump Pack')`, `hd2.fields.shield.entity_radius`.

Other useful capability keys:

- `acknowledgement` / `allowSharedRequired`: which safety flags a write needs.
- `evidence.tier`: how the field was proven.
- `blockedFields` / `blocker`: things deliberately not editable, with reasons.

Every target also has `:describe()`, which returns its fields and flags as a Lua
table.

## 6. What `expect` means

`expect` is the value the game should have right now, normally `currentDefault`
from a capability file. Before writing, the runtime checks that the live value
equals `expect` (or already equals your `value`). If not, the game was updated,
another mod changed it, or the wrong thing was found, and nothing is written.
The request ends with `CONFLICT`.

For the typed catalogs, a wrong `expect` is also rejected immediately when your
mod calls `hd2.patch`. Never guess `expect`; copy it.

## 7. Target examples

```lua
-- Player weapon
hd2.weapon('AR-23C Liberator Concussive')

-- A player weapon's projectile and its impact explosion
hd2.weapon('R-36 Eruptor'):attack('primary'):projectile()
    :terminal_action('impact'):explosion()

-- Support weapon
hd2.support_weapon('APW-1 Anti-Materiel Rifle')

-- Stratagem (cooldown: hd2.fields.stratagem.definition_cooldown)
hd2.stratagem('AC-8 Autocannon')

-- Deployed entity (sentry, emplacement, relay)
hd2.stratagem('E/AT-12 Anti-Tank Emplacement'):deployed_entity()

-- Shield Relay: the base and the shield are separate targets
local relay=hd2.stratagem('FX-12 Shield Generator Relay'):deployed_entity()
relay:shield()                  -- shield.entity_radius, shield.entity_durability
relay:damage_zone('body_front') -- zone.health

-- Vehicle: main health, damage zones, weapon mounts
hd2.vehicle('TD-220 Bastion MK XVI')
hd2.vehicle('TD-220 Bastion MK XVI'):damage_zone('zone_3')
hd2.vehicle('M-102 Gunner FRV'):mount('gun')

-- Backpack
hd2.backpack('LIFT-850 Jump Pack')

-- Booster: fields live on the records the booster reaches
hd2.booster('Vitality Enhancement'):tuning()           -- native Booster definition table scalar
hd2.booster('Firebomb Hellpods'):explosion()           -- extra hellpod-impact explosion
hd2.booster('Experimental Infusion'):status_effect()   -- the stim buff
hd2.booster('Dead Sprint'):status_damage()             -- the health-drain damage
hd2.booster('Surplus EAT Allocation'):granted_stratagem()  -- the granted EAT stratagem
hd2.booster('Armed Resupply Pods'):deployed_entity()   -- the resupply-pod turret

-- Magazine attachment (owns the round count on weapons with selectable magazines)
hd2.weapon('AR-23C Liberator Concussive'):magazine_attachment()
hd2.weapon_attachment('Rifle 5,5x50mm. Drum')
```

## 8. patch, transaction, plan, ensure

| Call | Use it for | Not for |
| --- | --- | --- |
| `hd2.patch{...}` | One change. | Several values, or values the game may reset. |
| `hd2.transaction{target=...,changes={...}}` | Several fields on the same object, all or nothing. | Fields on different objects (it tells you to use a plan). |
| `hd2.plan{operations={...}}` | Changes across several objects, all or nothing. Up to 64 operations. | A single simple change. |
| `hd2.ensure{patch=...}` (or `transaction=`, `plan=`) | Keeping a change applied if the game resets it. The usual choice for a released mod. | One-off experiments. |

How they run:

- Work starts about 3 seconds after your mod loads.
- If the game data is not ready yet (`TARGET_UNAVAILABLE`, `TARGET_UNSTABLE`), the
  runtime retries up to 6 attempts, 5 seconds apart, then stops. Time spent
  waiting behind another mod does not count.
- A successful write stops immediately. Permanent problems, such as a conflict or
  an unsupported game build, stop on the first attempt.
- After success, `ensure` only re-checks the bytes it wrote: every 60 seconds,
  backing off to every 600 seconds. If the value was reset, it runs the full
  guarded path again.
- Only one runtime operation works at a time, so mods do not collide at startup.

### In-game options

`hd2.options` puts sliders, choices, and toggles on the in-game MODS tab (CowboyBingus
Mod Options Menu v1+, which needs Bingus Shared Loader v18+). Pass a slider or choice as a
field `value` in `hd2.ensure`, or a toggle as `enabled`:

```lua
local options=hd2.options({id='my_mod',title='My Mod'})
local rate=options:slider({id='rate',label='Fire Rate',min=400,max=1100,step=50,default=900})
return hd2.ensure({patch={id='my-hd2-mod-fire-rate',target=hd2.weapon('AR-23C Liberator Concussive'),
    field=hd2.fields.weapon.fire_rate,expect=400,value=rate}})
```

When the player presses APPLY, the same ensure re-runs the full guarded path with the new
value. `expect` stays the reviewed baseline, and every safety flag is still required.
Turning an `enabled` toggle off restores the baseline. The menu is an optional dependency of
your mod only: without it, one warning is logged and the bound operation runs with the options'
declared defaults (declare the page with `fallback='disable'` to keep it inactive instead). See `docs/options.md`.

## 9. Safety flags

These flags are explicit risk acknowledgements. Add one only when the capability
file or the error message says that field needs it, and after reading why.

| Flag | Meaning | Example |
| --- | --- | --- |
| `allow_shared=true` | The value belongs to an object used by more than one thing, so all of them change. | A projectile shared by several Liberator variants; the Eagle rearm time shared by all Eagles; a magazine attachment used by several weapons. |
| `allow_unverified_effect=true` | Where the value lives is proven; that the game uses your edited value has not been gameplay-tested. | Magazine attachment capacity. |
| `allow_unverified_reference=true` | You are swapping which object something points to, and that swap is not gameplay-confirmed. | Vehicle mount swaps, such as the FRV gun. The new weapon's assets may not be loaded. |

A missing required flag is rejected when your mod calls `hd2.patch`, and the error
names the flag.

## 10. Build, install, test

1. Edit `src/addon.lua`.
2. Run `build.cmd`.
3. Import the new ZIP into your mod manager, replacing the old one. Purge and
   redeploy.
4. Restart Helldivers 2. Bingus Shared Loader finds mods once at startup and has
   no hot reload.
5. Play, then read the logs.

Logs are in `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\`:

- `BingusSharedLoader.log`: was your mod found and started? Script errors,
  including requests the runtime rejects when your mod calls it, appear here.
- `HD2Runtime.log`: what the runtime did.

```
[HD2Runtime] patch my-id target resolved
[HD2Runtime] patch my-id target not ready (TARGET_UNAVAILABLE); retry 2/6 in 5 update seconds
[HD2Runtime] patch my-id REJECTED code=CONFLICT reason=...
[HD2Runtime] ensure my-id verified status=APPLIED cycle=1 next=60 ...
[HD2Runtime] ensure my-id drift detected (...); full guarded resolution
```

`APPLIED` means your value was written. `ALREADY_DESIRED` means it already had
your value.

## 11. Common problems

| You see | Meaning | What to do |
| --- | --- | --- |
| `TARGET_UNAVAILABLE` / `TARGET_UNSTABLE` with retries | The game data is not ready yet. | Usually nothing. If all 6 attempts fail, the data never appeared in that session. |
| `CONFLICT`, "neither expected nor desired" | The live value is neither your `expect` nor your `value`. | Check for another mod changing the same value, or a game update. Do not guess a new `expect`. |
| unsupported build / fingerprint mismatch | Your game version is not the one this runtime supports. | Wait for an HD2Runtime update. |
| `field is read-only` | That field cannot be written; the message gives the reason. | Choose another field. |
| unknown name, or ambiguous candidates | The name does not exist, or several objects match and the runtime will not guess. | Copy exact names from a capability file, or use the semantic ID. |
| `requires allow_shared=true` (or another flag) | See section 9. | Decide deliberately. |
| Missing or broken vehicle weapon after a mount swap | The swapped weapon's assets were not loaded. | A known risk of `allow_unverified_reference`; revert the swap. |
| Nothing happens | Check `BingusSharedLoader.log`: mod not found, a script error, or a dependency/version check failure. | Enable Bingus and HD2Runtime; check `min_version`. |

## 12. Example mods

A. One change:

```lua
local hd2=require('mods/skyeshade/hd2runtime')
return hd2.patch({id='concussive-rpm',target=hd2.weapon('AR-23C Liberator Concussive'),
    field=hd2.fields.weapon.fire_rate,expect=400,value=1100})
```

B. Kept applied, across two objects (`JumpPackRecreation`):

```lua
local hd2=require('mods/skyeshade/hd2runtime')
local jump=hd2.backpack('LIFT-850 Jump Pack')
return hd2.ensure({plan={id='jump-pack-buff',operations={
    {id='recharge',target=jump,field=hd2.fields.recharge.time,expect=15,value=8},
    {id='launch',target=jump,field=hd2.fields.jump.vertical_launch_velocity,expect=40,value=50},
}}})
```

C. With acknowledgement flags (`ConcussiveDrumMagazine`):

```lua
local hd2=require('mods/skyeshade/hd2runtime')
-- The round count belongs to the drum attachment, which other weapons can use too.
local drum=hd2.weapon('AR-23C Liberator Concussive'):magazine_attachment()
return hd2.ensure({patch={id='concussive-drum',target=drum,
    field=hd2.fields.attachment.magazine_capacity,expect=60,value=90,
    allow_shared=true,allow_unverified_effect=true}})
```

## 13. Going further

1. Read the example projects; each is a small, working mod.
2. Browse the capability file for what you want to change.
3. Read the matching doc (`vehicle-authoring.md`, `backpack-authoring.md`,
   `stratagem-authoring.md`, `support-weapon-api.md`, `magazine-attachments.md`,
   `composition-plans.md`).
4. Use `:describe()` on a target.

Normal mod authoring means names, fields, `expect`, and `value`. Raw addresses,
offsets, hashes, signatures, and memory scanning belong to runtime research. If
something is not in a capability file, it is not supported yet; that needs a
runtime update, not memory access from your mod.

## Checklist

- [ ] Bingus Shared Loader v15+ and HD2Runtime imported and enabled.
- [ ] Template extracted outside the game and opened in your editor.
- [ ] `name`, unique `resource`, and `VERSION` set.
- [ ] Names, field constants, and `expect` copied from capability files.
- [ ] Safety flags added only where required.
- [ ] Built, imported, purged and redeployed, game restarted.
- [ ] `HD2Runtime.log` shows `APPLIED` or `ALREADY_DESIRED`.

## First mod in 5 minutes

1. Install Bingus Shared Loader and HD2Runtime in your mod manager.
2. Extract the mod template to `C:\HD2Mods\MyFirstMod\`.
3. In `hd2runtime.json`, set `name` and a unique `resource`.
4. Keep the example in `src\addon.lua` (Concussive fire rate 400 → 1100).
5. Run `build.cmd`, import the ZIP from `build\`, and deploy.
6. Start the game, fire the Concussive, and look for `APPLIED` in `HD2Runtime.log`.
