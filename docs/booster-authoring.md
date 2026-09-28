# Booster authoring

Boosters are their own authoring domain: `hd2.booster(name)`. They are not stratagems, and they
have no component or settings type of their own. The catalog is
`sdk/BoosterAuthoringCapabilities.json`; the evidence is
`research/booster-authoring-F5FEE03DCFDB.json` (`scripts/research_booster_authoring.py`).

## Native model

The game has a native `Booster` enum with 20 boosters. In the pinned type library, only two
data types reference it:

| Reference | What it does |
| --- | --- |
| `StratagemInfo` booster list | Per stratagem: when a booster is active, apply an entity delta to a payload and load a package. In the current build only the Resupply stratagem has an entry. |
| `StatusEffectSusceptibility` booster gate | Per status susceptibility: while a booster is active, use an override effect. Only the Helldiver avatar has gated susceptibilities. |

Everything else a booster does (reinforcement budget, extraction time, radar range, stamina,
sample drops, hellpod payloads, and so on) is applied by game code. No data value backs those
effects, so they are published as blocked with that reason rather than mapped to a guessed field.

## Identity

Each booster's native member name comes from the game's own UI template, which binds a member
name (for example `DefensiveAmmoPod`) to a booster icon (`BoosterArmedpods`). A reviewed table
maps wiki names to icon keys, and each key must be a letter subsequence of the wiki name. Names
are matched to enum values by the type library's hidden alias length:

| Status | Boosters |
| --- | --- |
| `RESOLVED` (unique value) | Muscle Enhancement, Increased/Flexible Reinforcement Budget, Hellpod Space Optimization, Experimental Infusion, Dead Sprint, Armed Resupply Pods |
| `CANDIDATES` (values share a name length; not guessed) | Vitality Enhancement, UAV Recon Booster, Stamina Enhancement, Localization Confusion, Expert Extraction Pilot, Motivational Shocks, Firebomb Hellpods, Sample Extricator, Sample Scanner, Stun Pods, Concealed Insertion |
| `EFFECT_CATEGORY` | Integrated Extinguishers: the only value that gates status susceptibilities |
| `ELIMINATION` | Surplus EAT Allocation |

No writable field depends on an unresolved value.

## Writable fields

Every booster field requires `allow_unverified_effect=true`. The native value and its link are
proven, but no booster edit has been gameplay-tested yet.

### Armed Resupply Pods: `booster:deployed_entity()`

The link is structural. The Resupply `StratagemInfo` booster entry names an entity delta; that
delta rewrites the resupply hellpod rack to four supply boxes plus one turret entity. The turret
uniquely owns its weapon components. Every write re-proves the whole chain live.

| Field | Baseline | Evidence |
| --- | --- | --- |
| `hd2.fields.weapon.fire_rate` | 640 rpm | structural chain; exact scraped match |
| `hd2.fields.magazine.capacity` | 140 rounds | structural chain; exact scraped match |

The turret's projectile is a definition shared with player weapons. Edit it through the owning
weapon view with `allow_shared`, not through the booster.

```lua
local turret=hd2.booster('Armed Resupply Pods'):deployed_entity()
hd2.ensure({patch={id='armed-pods-rate',target=turret,allow_unverified_effect=true,
    field=hd2.fields.weapon.fire_rate,expect=640,value=900}})
```

### Experimental Infusion: `booster:status_effect()`

The stim status effect is the only status row whose values equal both published effects
exactly: movement ×1.1 (`strength`) and damage taken ×0.9 (`IncomingDamageScale`). The UI names
the booster `CombatDrugs`. This is a fingerprint link, not a pointer chain. Game code applies the
effect and no weapon damage references it, but other code paths cannot be excluded, so
`allow_shared=true` is also required.

| Field | Baseline | Evidence |
| --- | --- | --- |
| `hd2.fields.status.strength` | 1.1 | exact match (movement +10%) |
| `hd2.fields.status.incoming_damage_scale` | 0.9 | exact match (10% damage resistance) |
| `hd2.fields.status.duration` | 10 s | type-library `duration`; no published value |

`status.incoming_damage_scale` lives in the row's stat-multiplier list. Each write re-proves the
list pointer, count, and stat type.

```lua
local stim=hd2.booster('Experimental Infusion'):status_effect()
hd2.ensure({transaction={id='stim',target=stim,allow_shared=true,allow_unverified_effect=true,
    changes={{field=hd2.fields.status.incoming_damage_scale,expect=0.9,value=0.8}}}})
```

## Relationships only

- **Integrated Extinguishers** gates two avatar susceptibilities. The override is a reference to
  a native effect preset whose semantics are unproven, so nothing is writable.
- **Resupply** is linked from Armed Resupply Pods by `stratagemSemanticId`. Supply stratagems are
  not in the stratagem authoring catalog yet.

## Validation

- `scripts/validate_booster_authoring_snapshot.py` resolves every field through the production
  chain proofs on the retained snapshot and applies it as a guarded no-op.
- The packaged-runtime validator applies `ArmedResupplyTurret` and `CombatStimBoost` from the
  built runtime ZIP with real overlay writes and re-application after a simulated reset.
