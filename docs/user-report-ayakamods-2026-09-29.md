# User report: "APPLIED, but weapons do not change" (AyakaMods, 2026-09-29)

A ModBuilder user (project "Nephelym's Weaponry Rebalance", SDK 0.27.0) reported that the SG-20 Halt, SG-225SP Breaker
Spray&Pray, LAS-12 Sai, R/40-K Hot-Shot, SMG-32 Reprimand, LAS-16 Sickle, LAS-17 Double-Edge Sickle and M-1000 Maxigun
were not receiving changes, that the MA5C magazine (32 to 60) stopped working after they added stratagem and support
weapon edits, that the Orbital Precision Strike cooldown did not change, and that adding Maxigun backpack ammo made
nothing apply. Their `HD2Runtime.log` showed every logged operation resolving and `APPLIED`, with no rejection.

The project, the log and the exact ModBuilder exports are fixtures in
`tests/fixtures/user-reports/ayakamods-weaponry-rebalance/`.

## Reproduction

`scripts/modbuilder_export_harness` runs ModBuilder 1.3.1's own `LuaGenerator` and `ModExporter.Wrap` on the project
(ModBuilder is referenced read-only, never modified). The export has **133 operations**. Their generated ids match the
user's log byte for byte.

The user's log schedules **exactly the first 42, in order**, then nothing. Replaying the wrapped export on the published
`HD2Runtime-0.27.0-runtime.zip` (the same bytes as the user's download, SHA-256 `d1b751f9…`) reproduces it: 42
ensures register, then the addon stops with

```
field is not exposed for SG-20 Halt: damage.durable_damage
```

Operation 42 is the Halt's primary-feed damage transaction. `hd2.ensure` raised, which aborted the addon's startup
function, so operations 42 to 132 never registered. Nothing in `HD2Runtime.log` says so: the error went to the Bingus
log.

**Not a version mismatch.** The export requires 0.27.0 twice: `hd2runtime.json` `requires.hd2runtime.min_version` is
the project's SDK version, and ModBuilder's wrapper asserts `runtime.version >= 0.27.0` before any operation. A 0.26.x
Runtime fails that assert and nothing registers at all; it cannot start partway. The user's Runtime was the published
0.27.0.

## Root causes

1. **Runtime defect: the Halt's feed fields did not resolve.** The Halt is the only player weapon with two feeds. Its
   projectile-object fields are named per branch (`damage.primary.*`, `damage.alternate.*`, backing branches `primary`
   / `alternate`). Its attacks are `feed_primary` / `feed_alternate`. The Runtime mapped a generic field
   (`hd2.fields.damage.player_durable_damage`) on `attack('feed_primary'):projectile()` to `damage.feed_primary.*`,
   which does not exist. Single-feed weapons use unqualified ids, so the Punisher (operation 41) worked. Fixed: a feed
   role also tries its branch name, and only a field whose backing branch is that feed is accepted.
2. **Registration was not isolated.** One invalid operation aborted every operation declared after it, silently in
   `HD2Runtime.log`. Fixed: `hd2.patch`, `hd2.transaction`, `hd2.plan` and `hd2.ensure` log
   `[HD2Runtime] <kind> <id> rejected: <reason>` and return a rejected handle instead of raising.
3. **Order dependence explains the MA5C.** ModBuilder orders operations by backing object kind, so the MA5C magazine
   (operation 104) comes after the damage rows. It worked while no earlier operation failed. Once the Halt edits were in
   the project, it never registered. The stratagem and support edits the user remembered adding were never the cause:
   they sit after operation 42 too.
4. **Apply latency.** Component values are copied into a weapon when the game builds it (see below). Operations
   resolve one at a time; the full project needs about 220 seconds of game time at 60 fps (13,172 frames: 19 address
   walks, 112 reuses) before the last operation applies. A weapon built before its operation applied keeps its old
   copy until it is rebuilt. A new log line reports when a burst of operations has settled.

With the fixes, the exact project registers 133 operations and applies 132. The one refused is the PLAS-101 Purifier
drag edit: its charge levels fire projectile 129 uncharged and 296 charged, so the edited row 296 only affects charged
shots. It is now marked AMBIGUOUS and needs `allow_unverified_effect`. ModBuilder emits that flag when its SDK catalog asks for it, so a re-export adds it once ModBuilder uses an SDK that carries this change; with the published 0.27.0 SDK the edit stays refused (and logged).

| Reported | In the published 0.27.0 run | With this pass |
| --- | --- | --- |
| SG-20 Halt | never registered (operation 42 raised) | registers and applies; feed fields resolve |
| SG-225SP Spray&Pray | never registered | applies |
| LAS-12 Sai | never registered | applies. Heat and spread are overwritten if an Improved heatsink or the Blaster Focus muzzle is equipped. |
| R/40-K Hot-Shot | never registered | applies |
| SMG-32 Reprimand | damage applied (operation 6); handling never registered (operation 79) | applies |
| LAS-16 Sickle | never registered | applies |
| LAS-17 Double-Edge Sickle | not in this project | Its projectile fields write projectile 149, the **LAS-16 Sickle's** row; the Double-Edge fires its heat-level projectiles 185, 219 and 25. Those fields are DORMANT_OR_METADATA and need `allow_unverified_effect`. Its heat fields work. |
| M-1000 Maxigun | never registered (support operations follow 42) | applies |
| MA5C magazine 32→60 | damage applied (operation 5); handling and magazine never registered (65, 104) | applies |
| Orbital Precision Strike cooldown | never registered (operation 128) | applies. It is the member the Shield Relay cooldown proof used; timing is tested live. |
| Maxigun backpack | not in this project; the backpack operation is last, so it cannot abort anything | a Maxigun and backpack project applies both. Not reproduced as a Runtime failure. |

The project itself is clean: 408 changes on 408 distinct backing members, no member written by two operations, no
plan that spans two weapons, and no later write restoring an earlier one.

## Which definition gameplay uses

`scripts/research_field_ownership.py` → `research/field-ownership-F5FEE03DCFDB.json` decodes, for every catalogued
component field of all 80 player weapons, the default customization items, the options the runtime unlock list lets
the player equip, and every entity delta that patches the field's bytes.

**Built weapons carry their own copy.** Two retained snapshots hold a private read-write heap copy of the AR-23C
Liberator Concussive's WeaponData record. It equals the base record with its eight default delta entries applied
(its stat-modifier block is merged). A third snapshot holds the JAR-5's composed ProjectileWeapon record. So the game
composes a weapon's component data (base plus customization deltas) when it builds the weapon. Runtime writes the
definition: weapons built afterwards use it; one already built does not change until it is rebuilt.

| Class | Meaning | Player fields (editable) |
| --- | --- | ---: |
| ACTIVE_DIRECT | a settings row read when used (projectile, damage, explosion, status) | 1330 |
| ACTIVE_AT_INSTANTIATION | a component member copied into the weapon at build | 1226 |
| AMBIGUOUS | depends on what is equipped, or on a charge level or spawned entity | 135 |
| DORMANT_OR_METADATA | this weapon never fires the row (Double-Edge Sickle, Loyalist) | 51 |
| OVERRIDDEN | a default customization overwrites it at build | 0 (42 read-only) |

No editable field is overwritten by a default customization. 21 component fields are overwritten only when the
player equips a specific option (Sai heatsinks and muzzle, the Liberator and Carbine recoil-spring internals, magazines
of the JAR-5, Scorcher and Diligence). They stay writable, and `effect.overriddenWhenEquipped` names the options. Support weapon
defaults only patch optics and stat modifiers, never a catalogued support field.

Every player field in `sdk/PlayerWeaponAuthoringCapabilities.json` now carries `effect`: `activeSource`,
`appliesWhen` (`weapon_build` or `use`), `instantiationOnly`, `activeSourceProven`, `gameplayEffectProven`,
`unverifiedEffect` and `writeVerifiedOnApply`. `APPLIED` keeps meaning only that the guarded write was verified.

## For ModBuilder (not changed here)

1. **Isolate every generated operation.** Older Runtimes raise on an invalid operation, and the generated addon calls
   them in sequence, so one failure silences everything after it. Wrap each call (for example
   `pcall`, logging the error) so every other operation still registers.
2. **Emit the exact field constant a target publishes.** The planner strips branch names (`Generic`) and relies on
   Runtime mapping them back. That fails on 0.27.0 for the SG-20 Halt. Use the branch-qualified constants the SDK
   already publishes (`hd2.fields.damage.primary_standard_damage`, `...alternate_*`). They work on 0.27.0 and later.
3. **Validate the export against the Runtime before packaging** (the `--runtime-validate` sample mode): every
   operation should validate, so this class of error is caught at export time.
4. **Surface apply timing:** tell users that weapon values apply to weapons built after the operation applied, and to
   wait for `N registered operations settled` in `HD2Runtime.log` before deploying.
5. The minimum-version logic is correct: `min_version` equals the project's SDK version, and the wrapper enforces it.

## Fixtures and checks

- `tests/fixtures/user-reports/ayakamods-weaponry-rebalance/`: the project (local path redacted), the user's log, and
  the ModBuilder exports: the original, without stratagem or support edits, plus a Maxigun backpack edit, MA5C only,
  MA5C capacity only, MA5C plus stratagem, MA5C plus support, Maxigun only, Maxigun plus backpack, backpack only,
  Orbital Precision Strike only, and each reported weapon alone.
- `tests/test_user_reports.py` checks that the log equals the export's first 42 operations and that every variant
  validates. It also checks that no backing member is written by two operations and that no operation spans weapons.
- Packaged runtime scenarios (`scripts/validate_packaged_runtime.py`) run on the built ZIP: the full project (132
  applied, the Purifier drag refused and logged), MA5C capacity only, MA5C plus stratagem, Maxigun, Maxigun plus
  backpack, the Halt dual feed, Spray&Pray damage, Sai heat, Sickle heat, the Orbital cooldown, and
  `registration-isolation` (a failing operation between two good ones).
- `examples/projects/RuntimeEffectDiagnostics`: the live test for what cannot be proven offline (see its README).
