# Completeness research pass (build F5FEE03DCFDB)

This pass covers movement restrictions while firing, the missing B/FLAM-80 Cremator and EAT-17 authoring, and mine
and defensive-stratagem coverage. It is native research first: evidence comes from the retained snapshot, the pinned
type library (hidden member names, lengths only), game.dll code bytes, and hash-verified resource paths. Every
component table in the entity settings (272 instances) was enumerated and named from filediver's `dl_type_names.txt`,
so these domains were searched beyond the 33 components the runtime profile previously knew.

## Movement restrictions

Research: `scripts/research_weapon_movement.py` → `research/weapon-movement-F5FEE03DCFDB.json`.

**Native representation.**
- One data-driven restriction: **WeaponDataComponent +387**, a u8 with a hidden 23-character name added with the
  Maxigun. Only the M-1000 Maxigun sets it.
- game.dll's only reader of that byte (re-found by byte pattern on every run) is reached through the WeaponData
  getter while the wielder fires. When set, it:
  - sends the weapon's firing-start wielder animation event (+388, 42-character name);
  - arms the firing-stop event (+392, 41-character name);
  - raises **bit 55** of the wielder's 192-bit action mask.
- There is no enum of modes and no movement or strafe multiplier in weapon data. There are also no separate
  sprint, dive or crouch bans, and no stance-specific or fire-mode-specific restrictions.
- A differential over every member of every component owned by any resolved player or support weapon found no
  anchor-only scalar that behaves as a speed multiplier.

**Which weapons use what.**

| Weapon | +387 stationary | Firing-start / stop events | Per-shot wielder animation |
| --- | --- | --- | --- |
| M-1000 Maxigun | **true** | `brace` / `brace_exit` | `fire_minigun` |
| GL-28 Belt-Fed Grenade Launcher | false | `brace` / `brace_exit` (not sent by the only reader found) | `fire_minigun` |
| B/FLAM-80 Cremator | false | — | `fire_flamethrower` (same as the FLAM-40) |
| All 102 other resolved weapons | false | — | per family (`fire_rifle`, `fire_mg`, ...) |

The Maxigun and the GL-28 differ in movement-related weapon data only by +387.

**Independently writable.** `weapon.stationary_while_firing` is writable on 105 weapons (73 player, 32 support), each
with its own WeaponData record. Every write requires `allow_unverified_effect`. The firing-stance events and per-shot
animation are published read-only in `sdk/WeaponMovementCapabilities.json`.

**Separate versus bundled.** Movement, sprint and dive are not separate in data. The single flag raises one action bit,
and code decides what that bit blocks.

**Code- or animation-driven.**
- The slowdown magnitude.
- The GL-28's slowdown: it is not produced by any proven data field, and its per-shot `fire_minigun` animation is a
  candidate only.
- The Cremator's slowdown: no data owner was found. Its one exclusive WeaponData flag (+1220) is read only inside the
  weapon audio RTPC update, next to `rounds_remaining` and `weapon_rpm`.
- The helldiver avatar's locomotion states (stand, crouch, prone, stand_limp, crouch_limp, swim, march, land_heavy)
  are not selected by weapon data.

## B/FLAM-80 Cremator

**Why it was missing.** It was an identity problem, not a damage-structure problem. The catalog name matched two
roots, and the magazine fingerprint could not decide between them because the handheld is backpack-fed.

**Identity.**
- The Cremator stratagem's rack places exactly one root: `equipment/support_weapons/heavy_flamethrower`.
- The call-in's package is exactly that root's loadout package.
- The other root is the Exosuit flamethrower mount (`vehicles/combat_walker_flamethrower`), whose package is empty.
- Result: `DELIVERY_RESOLVED` (`LOADOUT_PACKAGE`, `SUPPORT_WEAPON_PATH`).

**Damage chain.** weapon → SprayWeaponComponent → DamageInfo type 17 → fire status (type 5).
- Spray damage: 3 standard / 3 durable, AP 4/4/4/4, demolition 10, stagger 5, push 5.
- Fire status strength per hit: 3.
- The fire status duration (3 s) is the shared fire definition; the FLAM-40, EAT-700 and LAS-98 also use it.
- The spray component's range and cone floats and its `FireTemplate` (3 = Large ground fire) are identical to the
  FLAM-40's. They are recorded here but not authored.
- The catalog's "Fire Panic" and "FlamerSlowed" labels map to the same status row with a mismatched duration, so they
  stay `PARTIAL`.

**Recovered.** 19 fields: 9 spray damage, 2 fire status, 8 weapon handling.

## EAT-17 Expendable Anti-Tank

**Identity.**
- The EAT rack (shared by the EAT-17 stratagem and the Surplus EAT booster) places `equipment/support_weapons/lat_oneshot`.
- The other root has no resource path and no showcase, encyclopedia or customization components.
- Both have identical magazines, so the path is the only proof. Result: `DELIVERY_RESOLVED` (`SUPPORT_WEAPON_PATH`).

**Damage chain.**
- Projectile: velocity 200, mass 2500, penetration slowdown 0.85.
- Direct DamageInfo: 2000 / 2000, AP 6/6/6/3, demolition 30, stagger 50, push 25.
- Impact ExplosionSettings: radii 1.5 / 3 / 6, with its own DamageInfo 150 / 150, AP 3, demolition 30.
- No status.

**Backblast.** `BackblastComponentData` holds two floats (20, 1.15) and an ExplosionType (204). The EAT-700 has the
same values; the Recoilless uses 307. The chain is mapped here but not authored, because it needs a new runtime chain
proof.

**Recovered.** 42 fields: projectile 6, direct damage 9, explosion 12, magazine 3, fire mode 2, weapon 10.

The LAS-98 Laser Cannon was resolved the same way (`SUPPORT_WEAPON_PATH`): 29 fields.

## Defensive stratagems

**Coverage before.**
- 18 deployment entities with health and armor.
- 12 mounted weapons with ammo, fire rate, heat, projectile, damage, explosion, beam, arc and status fields.
- The four mine stratagems exposed only the deployer's health and armor. The mine entity, trigger, distribution and
  explosion were all blocked.

**Coverage after.** All four mines publish their explosion chain: 54 new writable fields. Existing sentry and
emplacement fields are unchanged.
- The chain: MinefieldComponentData +24 (a 14-character member, exactly `explosion_type`) → ExplosionSettings →
  DamageInfo → status.
- The deployer's ThrowerComponent names the thrown mine.
- The contact, gas and incendiary mine entities' own ExplosiveComponent +36 names the same row. Their mode is 2,
  arming delay 0 and trigger-to-detonation 0.002 s.
- The AT mine has no entity settings.
- Every write re-proves the Minefield link.

| Mine | Explosion | Radii | Damage | Status |
| --- | --- | --- | --- | --- |
| MD-6 AP | 366 | 1.2 / 5 / 7 | 700 / 700, AP 3 | — |
| MD-I4 incendiary | 72 | 1.2 / 4 / 7 | 300 / 300, AP 3 | fire (strength 0, 3 s) |
| MD-17 AT | 178 | 3 / 7 / 14 | 2000 / 2000, AP 5 | — |
| MD-8 gas | 270 | 2 / 6 / 6 | 3 / 3, AP 6 | two gas statuses (100, 6 s / 5 s) |

**Major unresolved areas.**
- **Mine count and spacing.** The thrower has 48 launch nodes on the AP, gas and incendiary launchers and 18 on the
  AT launcher, plus counts 6/8 and 6/3 and 11 throw floats. None of these has an independent fingerprint.
- **Trigger radius and arming.** The Minefield floats have no fingerprint.
- **Mine lifetime and chain reaction.** No owner found.
- **Sentry and emplacement targeting, and deployed lifetime.** Still blocked.
- **Enemy world minefields.** The Automaton minefields (`MineSpawnerComponentData` → `cy_mine_01`) are out of scope.

## Safety

- Same-build migration: 8,199 fields, all EXACT.
- Cross-build migration to D8E23968D141:
  - 0 unsafe stale writes;
  - the movement flag is rebound only where its member signature proves it;
  - the four mine root links are reported BROKEN (the explosion IDs differ in that build), and all 54 mine fields are
    blocked.
- The new `component_value` relationship fails closed when a value or member signature changes.
