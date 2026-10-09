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

### Which ZIP do I need?

| You want to | Download |
| --- | --- |
| Play with HD2Runtime mods | `HD2Runtime-<version>-runtime.zip` (and Bingus Shared Loader). Nothing else. |
| Make your first mod | The runtime ZIP (to test in game) and `HD2Runtime-ModTemplate-<version>.zip`. No Python needed. |
| Look up what you can change, read the docs, use the Python CLI | `HD2Runtime-<version>-sdk.zip` |
| Read or build working examples | `HD2Runtime-<version>-example-projects.zip` **and** the SDK ZIP (the examples build with the SDK's `hd2.py`). |

Every mod calls `require('mods/skyeshade/hd2runtime')` and shares one installed
runtime. Your built mod never contains the runtime. The game only needs Bingus
Shared Loader, HD2Runtime, and your built mod ZIP. Never install the template,
its `stubs` folder, or the SDK.

## 2. Set up on Windows

1. A mod manager such as Arsenal or HD2MM.
2. Bingus Shared Loader v15 or newer, imported and enabled. Keep it below other
   startup-replacement mods in the manager's order.
3. `HD2Runtime-<version>-runtime.zip`, imported and enabled once.
4. The mod template, extracted outside the game into a folder you create for
   your mod, for example `C:\HD2Mods\MyFirstMod\` (`MyFirstMod` is your own
   name, not a folder in the ZIP: the ZIP holds the project's files directly).
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

`min_version` is SemVer (`0.28.0`, `0.29.0-rc.1`; a prerelease is older than its
release). A player whose HD2Runtime is older than it gets no gameplay from your mod
(the mod refuses to start, as before). With HD2Runtime 0.28.0 or newer installed,
your mod's wrapper also tells HD2Runtime, which logs the mod and its requirement
and, once per session on the ship, shows one "HD2Runtime update required" message
box naming the highest version any installed mod needs. Mods for the installed or
an older HD2Runtime never trigger it.

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

### Who owns what

The game stores each value on the object that uses it, and HD2Runtime writes it there. Pick the target
by ownership, not by what the value affects:

```
hd2.weapon(name)                       weapon-local: fire rate, spread, recoil, sway, reticle, fire modes
  :attack('primary')                   one of the weapon's attacks
    :projectile()                      the projectile: velocity, mass, drag, pellets
                                       AND its damage: standard, durable, armor penetration, stagger, ...
      :terminal_action('impact')
        :explosion()                   an explosion the projectile causes: radii, explosion damage
    :projectile_source()               where the fired projectile lives, and the target/field that
                                       replaces it (ACTIVE_DIRECT, INDIRECT, AMBIGUOUS, BLOCKED)
  :ammunition()                        default ammunition that owns the fired projectile (Liberator,
                                       Dominator, Diligence, Breaker, Peacemaker, Redeemer)
  :magazine_attachment(option)         a magazine option: capacity, magazines, reload, ergonomics
                                       (weapons with selectable magazines)
hd2.support_weapon(name)               the same tree for support weapons
  :backpack()                          backpack-owned ammunition (Maxigun, Cremator, GL-28)
hd2.vehicle(name):weapon(mount)        a vehicle or Exosuit mounted weapon
hd2.stratagem(name)                    call-in cooldown and mission uses
  :payload()                           the drop pod's item slots
```

So damage is **not** on the weapon: it belongs to `weapon:attack('primary'):projectile()`. Many
projectiles and damage records are shared by several weapons (`sharedWithWeapons` in the capability
file); editing one changes all of them and needs `allow_shared=true`.

### Armor penetration

Player and support weapon armor penetration is four fields, one per impact angle:

| Constant | Meaning |
| --- | --- |
| `hd2.fields.damage.ap_direct` | Head-on hits |
| `hd2.fields.damage.ap_slight` | Slightly angled hits |
| `hd2.fields.damage.ap_large` | Steeply angled hits |
| `hd2.fields.damage.ap_extreme` | Near-glancing hits |

Standard and durable damage are `hd2.fields.damage.player_standard_damage` and
`hd2.fields.damage.player_durable_damage`. `hd2.fields.damage.armor_penetration`, `standard_damage`
and `durable_damage` (without `player_`) belong to the original fixed JAR-5 patch and do not work on
typed targets; the runtime says so if you use them.

Baselines differ between weapons: the AR-23 Liberator is 2 / 2 / 2 / 0, the AR-23C Liberator
Concussive is 2 / 2 / 2 / 2. Never copy `expect` values from a similar weapon.

## 5. Finding what you can edit

| Question | Look in |
| --- | --- |
| Primary and secondary weapons | `PlayerWeaponAuthoringCapabilities.json` |
| Support weapons | `SupportWeaponAuthoringCapabilities.json` |
| Stratagems, sentries, emplacements, Shield Relay, cooldowns | `StratagemAuthoringCapabilities.json` |
| Vehicles: health, damage zones, weapon mounts | `VehicleAuthoringCapabilities.json` |
| Backpacks | `BackpackAuthoringCapabilities.json` |
| Magazine attachments (round counts on weapons with selectable magazines) | `MagazineAttachmentCapabilities.json` |
| Muzzle, optics and underbarrel attachments (ergonomics, sway, recoil, climb, spread) | `WeaponAttachmentModifierCapabilities.json` |
| Boosters | `BoosterAuthoringCapabilities.json` |
| Armor rating, speed and stamina: kit piece weights, weight classes, the damage curve | `ArmorStatsCapabilities.json` |
| Armor passives and the game's armor, helmet and cape kits | `ArmorPassiveCatalog.json` |
| The Lua name of a field | `stubs/mods/skyeshade/hd2runtime.lua`, the `---@class HD2Fields_<domain>` blocks |
| Explanations | the other files in `docs/` |
| Working code | `<Example>/src/addon.lua` in the example-projects ZIP (each top-level folder is one example) |

**Do not guess, and do not copy.** Take the target, field constant and `expect` for *this* weapon
from one of:

- the capability JSON (`currentDefault`, `apiFieldConstant`, `sharedWithWeapons`, `acknowledgement`);
- the Lua stubs (completion lists every constant; legacy constants are labelled as legacy);
- the example projects, which are validated against the current SDK on every release;
- ModBuilder's Lua Preview, which writes the request from the catalog;
- `:describe()` on a target in your addon, which returns its fields, baselines and flags.

Two weapons that look alike rarely share every value.

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

Every capability file, including `PlayerWeaponAuthoringCapabilities.json`, lists the exact
constant for each field in `apiFieldConstant`; copy it from there. Constants marked
"Deprecated compatibility alias" in the stub (for example
`hd2.fields.weapon.capacity`) point to a preferred constant; use that one.

### Two naming systems

HD2Runtime still contains a small original catalog with short names and fixed changes:
`'Bastion'`, `'Shield Relay'`, the JAR-5 `:projectile():damage()` path with
`hd2.fields.damage.armor_penetration`, `hd2.equipment('Jump Pack')`, `hd2.fields.shield.radius`,
and the read-only `hd2.observe`. It is kept so old mods keep working, but it allows only a few exact
changes. **Do not use it for new mods**, and no example teaches it any more.

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

-- Muzzle, optics and underbarrel attachments (their stat modifiers; one definition, every weapon that equips it)
hd2.weapon('AR-23 Liberator'):attachments('muzzle')
hd2.weapon('AR-23 Liberator'):attachment_definition('muzzle','5,5mm. Flash Hider')
hd2.weapon_attachment('Vertical Grip')
```

## 8. patch, transaction, plan, ensure

| Call | Use it for | Not for |
| --- | --- | --- |
| `hd2.patch{...}` | One field. | Several values, or values the game may reset. |
| `hd2.transaction{target=...,changes={...}}` | Several fields on the same backing object, all or nothing. Example: a projectile's standard damage, durable damage and all four AP fields. | Fields on different objects (it tells you to use a plan). |
| `hd2.plan{operations={...}}` | Changes across several objects, all or nothing. | Several fields of one object: use one transaction instead of one plan operation per field. |
| `hd2.ensure{patch=...}` (or `transaction=`, `plan=`) | Keeping a change applied if the game resets it. The usual choice for a released mod. | One-off experiments. |

A transaction on one projectile's damage (`LiberatorDamageTransaction`):

```lua
local projectile=hd2.weapon('AR-23 Liberator'):attack('primary'):projectile()
return hd2.ensure({transaction={id='liberator-damage',target=projectile,allow_shared=true,changes={
    {field=hd2.fields.damage.player_standard_damage,expect=90,value=120},
    {field=hd2.fields.damage.player_durable_damage,expect=22,value=35},
    {field=hd2.fields.damage.ap_direct,expect=2,value=3},
    {field=hd2.fields.damage.ap_slight,expect=2,value=3},
    {field=hd2.fields.damage.ap_large,expect=2,value=3},
    {field=hd2.fields.damage.ap_extreme,expect=0,value=2},
}}})
```

Plan rules (the runtime rejects anything else, with a message saying which rule):

- A plan has `operations={...}` or `phases={...}` (1 to 8 phases), and at most 64 operations.
- Each operation is one patch or one transaction on **one backing object**. An operation whose
  changes span several objects is rejected; split it.
- **One phase cannot mix target families**: stratagems; vehicles and backpacks; weapons (player,
  support, vehicle-mounted); magazine attachments; boosters; drop pods. Put each family in its own
  phase (`phases={{id=...,operations={...}},...}`).
- `target_from` (use an object resolved by an earlier operation) needs that operation in an earlier phase.
- At most 128 writes per phase, and two operations may only touch the same bytes if they write the same value.

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

- `BingusSharedLoader.log`: was your mod found and started? Script errors appear here.
- `HD2Runtime.log`: what the runtime did. Its first line names the Runtime that actually loaded:
  `[HD2Runtime] HD2Runtime 0.30.1 initialized (API 1)`. If the version is not the one you expect, the wrong Runtime
  is installed.

```
[HD2Runtime] HD2Runtime 0.30.1 initialized (API 1)
[HD2Runtime] ensure my-other-id rejected: field is not exposed for SG-20 Halt: damage.no_such_field
[HD2Runtime] patch my-id target resolved
[HD2Runtime] patch my-id target not ready (TARGET_UNAVAILABLE); retry 2/6 in 5 update seconds
[HD2Runtime] patch my-id REJECTED code=CONFLICT reason=...
[HD2Runtime] ensure my-id verified status=APPLIED cycle=1 next=60 ...
[HD2Runtime] ensure my-id drift detected (...); full guarded resolution
[HD2Runtime] 42 registered operations settled in 61 s: 41 applied, 1 rejected, 0 other (see earlier lines)
```

`APPLIED` means your value was written (the guarded write was verified). `ALREADY_DESIRED` means it already had
your value. Neither proves the game uses that value: each field's `effect` in the capability catalog says whether the
written definition is the one gameplay reads, and when.

- **One rejected request does not stop the others.** A request that fails validation logs `<kind> <id> rejected:
  <reason>` and returns a handle with `status='rejected'`; every other operation your mod declares still registers.
- **Weapon values apply to weapons built after the write.** Component values (magazine, heat, handling, fire rate,
  projectile reference, backpack ammo) are copied into a weapon or backpack when the game builds it. A weapon you
  already hold keeps its copy until it is rebuilt: redeploy, reinforce, or call in a new support weapon. Projectile,
  damage and explosion values are read when used.
- **A large mod takes a while to apply.** Operations resolve one at a time, each reading about 1 ms of memory per frame.
  Most take a few frames; the first, and one about every 15 s, also walks the address space, which takes a few dozen
  frames. Wait for `N registered operations settled` before deploying, or weapons built earlier keep the old values.

### Startup progress

While the Runtime's own initial work is still pending, a small panel in the top-right corner shows it:

```
HD2Runtime 0.30
Initializing...
[########----] 63%
Applying mod plans (5/8)
```

The percentage is computed from the actual work, never from a timer. It is the weighted sum of five stages:

| Stage | Weight | Done when |
|---|---|---|
| Loading catalogue data | 10 | The Runtime's data and the mods have loaded (by the first update). |
| Waiting for the game | 10 | The game world is readable, aboard the ship or in a mission. |
| Loading asset packages | 25 | Every asset package gate the mods opened is resident or failed. |
| Applying mod plans | 45 | Every registered operation (`ensure`, `plan`, `patch`, `transaction`) has settled: verified once, or rejected / unavailable / cancelled. |
| Preparing custom stratagems | 10 | The custom stratagems' carriers are allocated aboard the ship (or none is selected). |

- A stage with no work counts as done, so the bar shows 100% only when every stage is done.
- **It never blocks.** The panel is only a display, and nothing waits for it. A quick start never shows it: it appears
  only if work is still pending half a second after the game world exists. It closes one second after everything is
  done.
- A mod that registers late shows it again.
- If a stage makes no progress for 45 s (an operation waiting for something that is not Runtime work, such as a weapon
  not built yet), the display ends and the log names what is still pending.
- If the game's UI cannot be drawn, the display is turned off for the session (logged once) and the Runtime continues.

The log gets one line when the world appears, one per stage, and one at the end, with each stage's time:

```
[HD2Runtime] startup: initializing: 8 mod operations, 2 asset gates; the Runtime and the mods loaded in 0.41 s CPU
[HD2Runtime] startup: stage assets done in 1.20 s (2 of 2)
[HD2Runtime] startup: stage plans done in 9.85 s (8 of 8)
[HD2Runtime] startup: READY in 10.90 s of updates (catalogue 0.41 s CPU, game 0.00 s, assets 1.20 s (2/2), plans 9.85 s (8/8), custom 0.00 s)
```

`hd2.diagnostics.telemetry({enabled=true})` adds timing for the Runtime's own watches (`init_progress.tick`,
`custom_stratagems.tick`, `projectile_impact.tick`, `custom_eagles.rockets_tick`, ...) to its periodic report.

### Version label (0.30.0)

Aboard the ship, a small dim label in the bottom-left corner shows which Runtime and which game build are running:

```text
HD2Runtime 0.30.1
Game F5FEE03DCFDB
```

- **The game build** is the one the Runtime proved on startup: the first 12 hex digits of its pinned executable
  fingerprint, as in the Runtime's log and file names. An unsupported build shows no label.
- **When it shows:** only in the game's Ship state. It is hidden while a mission loads, in a mission and while the
  ship loads again, and shown again aboard the ship.
- **What decides it:** the events engine's `game_state` source, the same state every `hd2.mod()` context follows.
- **How it is drawn:** with the engine font at the lowest layer of a Ui World screen GUI, so any native interface
  drawn in that corner covers it.
- **Size:** 18 px text 14 px from the corner at 1920 x 1080, scaled with the window by the tighter of width/1920
  and height/1080. It is the same share of the screen at every resolution: 36 px at 4K, 12 px at 720p. The GUI is created when the label appears and destroyed when it hides; nothing is
  redrawn while it shows (`runtime/version_label.lua`).

### Settings (F10, 0.30.2)

Press **F10** in game to open the HD2Runtime settings. The window has the HD2R Editor's look and frees the mouse cursor
while it is open; F10 again, Esc or the x close it. Each thing the Runtime shows on screen can be turned off there:

| Setting | What it hides |
|---|---|
| Startup notice | the notice about public lobbies when you first board the ship |
| Custom stratagem alerts | the alert cards: problems before a launch and how to fix them, DISABLED, vanilla names |
| Version label | the HD2Runtime and game build in the bottom-left corner aboard the ship |
| Startup progress | the asset loading panel in the top-right corner while mods load |

- Everything is on by default. A change applies at once and is saved for every later game session (in
  `%LOCALAPPDATA%\HD2Runtime\mod_data\hd2runtime.json`).
- Turning something off only hides it: the log keeps every line.
- F10 is the Runtime's own key. A mod that binds F10 is left unbound and logs the conflict; it can be rebound.
- The startup notice says where to find the panel.

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
| Nothing happens | Check `BingusSharedLoader.log`: mod not found, a script error, or a dependency/version check failure. | Enable Bingus and HD2Runtime; check `min_version` and the version line at the top of `HD2Runtime.log`. |
| `APPLIED` but no change in play | The weapon was built before the write, or the field is not what this weapon uses. | Rebuild the weapon (redeploy); check the field's `effect.activeSource` (AMBIGUOUS / DORMANT_OR_METADATA / OVERRIDDEN explain why). |
| `<id> rejected:` for one operation | That one request failed validation; the reason follows. | Fix or remove that operation; the others still apply. |
| `projectile objects only accept...`, or "legacy fixed-resource field" | A damage field was used on the wrong target, or a legacy constant. | Damage goes on `weapon:attack('primary'):projectile()`, with `player_standard_damage`, `player_durable_damage` and `ap_*`. |
| `transaction spans multiple backing objects` | The changes belong to different objects. | Use a plan: one operation per object. |
| `one plan phase cannot mix ...` | One phase holds, for example, a stratagem and a weapon. | Split them into phases. |

### Lua table pitfalls

Lua reports these only as a script error, before HD2Runtime is ever called. They appear in
`BingusSharedLoader.log`, and `HD2Runtime.log` stays unchanged.

A table keeps only the **last** value of a repeated key. This change silently loses `field_a`:

```lua
{
    field = field_a,
    value = 1,
    field = field_b,   -- replaces field_a
    value = 2,         -- replaces 1
}
```

Write one table per change instead: `changes={{field=field_a,...},{field=field_b,...}}`.

Tables in a list need a comma between them:

```lua
changes={
    {field=hd2.fields.damage.ap_direct,expect=2,value=3},   -- this comma is required
    {field=hd2.fields.damage.ap_slight,expect=2,value=3},
}
```

`},` followed by `{` is correct; `}` followed directly by `{` is a syntax error.

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

C. Several fields of one projectile, as one transaction (`LiberatorDamageTransaction`); see section 8.

D. With acknowledgement flags (`ConcussiveDrumMagazine`):

```lua
local hd2=require('mods/skyeshade/hd2runtime')
-- The round count belongs to the drum attachment, which other weapons can use too.
local drum=hd2.weapon('AR-23C Liberator Concussive'):magazine_attachment()
return hd2.ensure({patch={id='concussive-drum',target=drum,
    field=hd2.fields.attachment.magazine_capacity,expect=60,value=90,
    allow_shared=true,allow_unverified_effect=true}})
```

### Building the example projects

The example projects build with the SDK's Python CLI (Python 3.10+), not with `build.cmd`. Extract the
example-projects ZIP and the SDK ZIP side by side, for example:

```
C:\HD2Mods\
  HD2Runtime-<version>-sdk\                the SDK ZIP (holds hd2.py and metadata.json)
  HD2Runtime-<version>-example-projects\   the example-projects ZIP
    KillHealTest\
      build.py
```

Then run `python build.py` inside an example (or double-click it; the window stays open to show the result). The
result is the example's `build\<Name>-<version>.zip`.

`build.py` finds the SDK by itself, in this order:

1. the `HD2RUNTIME_SDK` environment variable;
2. the `sdk` path in the example's `hd2runtime.json`;
3. the example's folder and every folder above it: the folder itself when it is the SDK, or a subfolder named `sdk`
   or ending in `-sdk`.

With the SDK anywhere else, point the example at it once:
`python <SDK>\hd2.py configure <example folder> --sdk <SDK>`. That also points the editor's autocomplete
(`.luarc.json`) at the SDK's stubs.

## 13. Going further

1. Read the example projects; each is a small, working mod.
2. Browse the capability file for what you want to change.
3. Read the matching doc (`vehicle-authoring.md`, `vehicle-weapons.md`, `backpack-authoring.md`,
   `backpack-ammo.md`, `stratagem-authoring.md`, `stratagem-uses.md`, `stratagem-calldown-code.md`, `stratagem-presentation.md`, `custom-images.md`, `custom-text.md`, `pod-payloads.md`,
   `support-weapon-api.md`, `magazine-attachments.md`, `weapon-attachments.md`, `weapon-reticles.md`, `fire-modes.md`,
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
- [ ] Target chosen by ownership (damage on the projectile, not the weapon).
- [ ] Names, field constants, and `expect` copied from capability files for this exact weapon.
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
