# Throwable authoring

Throwables are their own authoring domain: `hd2.throwable(name)`. The domain covers all 23 throwable-slot items
in the armory. The catalog is `sdk/ThrowableAuthoringCapabilities.json`. The evidence is in
`research/throwable-authoring-F5FEE03DCFDB.json`, produced by `scripts/research_throwable_authoring.py`.

The wiki throwable catalog is used only as value fingerprints. No field is writable because the wiki
says so; every field sits on a typed native member that the research reads directly.

## Identity

Every throwable is an entity that owns a `ThrowableComponent`. The retained snapshot has 46 of them:

- the 23 armory items;
- unreleased or test items such as `emp_grenade`, `antitank_grenade` and `caltrops_grenade`;
- AI-thrown variants;
- enemy grenades.

Only player armory equipment qualifies as a candidate. An armory item owns a `ThrowableComponent`, a
`LoadoutPackage` and an `EncyclopediaEntry`, and 29 entities meet that bar.

Each wiki item is compared, fact by fact, with every candidate:

- inventory counts;
- detonation mode, fuse and cookability;
- explosion radii;
- explosion damage, durable damage, penetration, demolition, stagger and push;
- shrapnel and bomblet counts;
- direct-hit damage;
- shield capacity and radius;
- mine health.

An item resolves only when exactly one candidate agrees with every published fact, and no other item
claims that candidate. **All 23 resolve** (7 to 16 facts each). Resource path names such as `he_grenade`
or `energy_shield_grenade` are recorded as supporting evidence only.

The G-123 Thermite has an AI-thrown twin with identical values. The twin owns a `BehaviorComponent` and no
encyclopedia entry, so the armory filter excludes it.

## Native model

| Record | Owner | Members used |
| --- | --- | --- |
| `ThrowableComponent` | throwable entity | `+100` start amount, `+104` max amount, `+108` refill amount (hidden name lengths 12 / 10 / 13) |
| `ExplosiveComponent` | throwable entity | `+0` ExplosiveMode, `+8` arming delay, `+12` explosion delay, `+36` ExplosionType, `+40` impact ExplosionType, `+252` timed status template |
| `StickyComponent` | throwable entity | `+44` DamageInfoType (direct hit, throwing knife) |
| `HealthComponent` / `ShieldComponent` | the thrown entity itself | health `+0`; shield radius `+0`, durability `+76` |
| `ExplosionSettings` | settings row | `+4` DamageInfoType, `+16/+20/+24` radii, `+80` shrapnel count, `+84` shrapnel ProjectileType |
| `ProjectileSettings` | settings row | `+32..+44` ballistics, `+60` DamageInfoType, `+144/+156` impact / expiry ExplosionType |
| `DamageInfo` | settings row | damage, penetration, forces; status slots `+44 + 8n` (StatusEffectType) and `+48 + 8n` (strength) |
| `StatusEffectSettings` | settings row | `+40` duration |

The detonation modes correlate 23/23 with the wiki's trigger and cookable columns:

| Mode | Meaning | Used by |
| --- | --- | --- |
| 0 | timed, cookable | HE, Frag, Incendiary, Dynamite, Pineapple, Smoke, Stun, Gas |
| 2 | armed on throw | impact throwables, and the non-cookable timed Arc, Pyrotech and Urchin |
| 3 | sticky, timed, cookable | Thermite, Shield |
| 4 | proximity | the two mines |

## Targets and accessors

```lua
local frag = hd2.throwable('G-6 Frag')
frag                                 -- inventory counts (ThrowableComponent)
frag:detonation()                    -- fuse (ExplosiveComponent)
frag:explosion()                     -- ExplosionSettings + its DamageInfo
frag:explosion():shrapnel()          -- the shrapnel projectile (also frag:shrapnel())
hd2.throwable('G-10 Incendiary'):explosion():status_effect('fire')
hd2.throwable('G-7 Pineapple'):bomblets():explosion()
hd2.throwable('K-2 Throwing Knife'):damage()
hd2.throwable('TM-1 Lure Mine'):entity()
hd2.throwable('G/SH-39 Shield'):shield()
```

An accessor exists only where the native relationship exists. For example, `hd2.throwable('G-12 High
Explosive'):shrapnel()` errors, because the G-12's explosion spawns no shrapnel.

The only new field constants are the four concepts no other domain models:

- `hd2.fields.throwable.starting_count`
- `hd2.fields.throwable.max_count`
- `hd2.fields.throwable.count_from_supply`
- `hd2.fields.throwable.explosion_delay`

Everything else reuses the existing `explosion.*`, `explosion.damage.*`, `damage.*`, `projectile.*`,
`status.*`, `entity.health` and `shield.*` fields.

## Scope and acknowledgements

Every write requires `allow_unverified_effect=true`. The owner and value are proven, but no changed value
has been tested in game.

- **Throwable-local records.** The inventory counts, fuse, mine health and shield records each belong to one
  entity (unique owner), so no `allow_shared` is needed.
- **Settings rows.** These are global definitions and always require `allow_shared=true`. The research
  indexes every typed reference in every component and settings layout, and publishes each row's known
  consumers. Examples:
  - The G-12 explosion is used by the G-12 only.
  - The frag shrapnel projectile is shared by 11 entities, including the TM-1 Lure Mine and the G/SH-39
    Shield.
  - The fire status definition is reached from 65 entities.
- **Status effects.** Each status has two parts:
  - `status.strength` is the amount **applied per hit**. It lives in the throwable's own DamageInfo row.
  - `status.duration` is the **shared status definition**, which every source of that status uses.

  Fire (type 5) and Stun Large (type 39) are named by correlation across several throwables. The gas labels
  ("Gas", "Gas Confusion") rest on slot order only and are marked unconfirmed. The status fields themselves
  are native-proven either way.
- **Submunitions.** The G-7 Pineapple's bomblet projectile reuses the grenade's own explosion DamageInfo for
  its direct hit. That row is published once, under the grenade's explosion. Each bomblet's own explosion is
  `:bomblets():explosion()`.

## Read-only, and why

| Field | Reason |
| --- | --- |
| TED-63 fuse | The 5 / 15 / 60 s settings are not flattened. Only the 5 s default is this native `ExplosionDelay`; the other two have no resolved owner. |
| Impact throwables' explosion delay | It is a zero minimum timer, not a fuse. |
| Mine explosion delay | It is the trigger-to-detonation time, which the wiki does not publish. |
| G/SH-39 explosion delay and expiry explosion | The wiki's 0 s fuse is the deploy-on-contact behaviour. Natively the device ends with a 20 s explosion delay and a small explosion; neither is fingerprinted. |

## Not exposed (no proven native owner)

- The thermite's timed burn template (status types published read-only).
- The G-31 Arc's arc child ("Stun Small").
- The G-142 Pyrotech's spray.
- The G/40-K Melta Mine's flame wall.
- The smoke-cloud lifetime (ExplosionSettings `+104` = 30 is only a candidate).
- The Seekers' seek radius and lifetime (wiki prose only).
- The Urchin's pulse count.
- A throw speed (ThrowableComponent `+16` = 20 is consistent but unproven).
- Numeric armor for mines (the wiki gives only "Unarmored").

## Validation

`scripts/validate_throwable_authoring_snapshot.py` runs every writable field (388 of 411) on a
copy-on-write overlay of the retained snapshot. For each field it checks:

- the live baseline;
- a guarded no-op;
- a changed write with read-back;
- a guarded rollback;
- rejection of a third-party value, a stale expect, missing acknowledgements, and out-of-range values
  on both sides.

For each target it also rejects every changed chain link, a changed component ownership, and a wrong build
fingerprint. Packaged-runtime scenarios apply the example projects from the shipped ZIP and re-apply them
after a simulated reset.

## Remaining in-game confirmation

None of these edits has been observed in game yet:

- inventory counts at mission start and resupply;
- a changed fuse;
- explosion radii and damage;
- status strength and duration;
- shrapnel and bomblet counts;
- knife damage;
- mine health;
- shield radius and health.

That is why every write requires `allow_unverified_effect=true`.
