# Status effects on weapon attacks

Since the coverage pass, any mapped player, support or mounted-weapon attack can change which status its hits
apply, or gain one, through typed status references. The research is `scripts/research_status_effects.py` →
`research/status-effects-F5FEE03DCFDB.json`. The public catalog is `sdk/StatusEffectCatalog.json`.

## Native model

A status is applied by the **damage definition** (DamageInfo) that a hit uses. It is not a property of the weapon or
the projectile.

- Every DamageInfo row has four inline status slots at +44+8n. Each slot is a StatusEffectType (u32) followed by a
  strength (f32).
- An unused slot has type 0. Used slots are packed from slot 1: none of the 649 live rows has a gap.
- 500 rows use no slot, 127 use one, 18 use two and 4 use three. None uses all four.
- Every hit that reaches a DamageInfo row applies its statuses:
  - a projectile's direct hit;
  - each explosion;
  - each beam, arc or spray tick;
  - each melee strike.
- A projectile's direct-hit damage and its explosion damage are separate rows, so they have separate slots.
- Several statuses per row are normal. For example, the flamethrowers apply `fire`, `flamer_slowed` and
  `fire_panic` from one row.
- The status definitions are global (StatusEffectSettings, one 152-byte row per status):
  - `status.duration` (+40), which is already authorable;
  - the status's own tick DamageInfo (+44);
  - a string the game stores with the row: its name ("Fire", "Stun Medium", …).

The catalog takes each status's semantic identity from that stored name. The numeric type is not identity: this
build stores "Stun Small" at 37, while filediver's older enum lists it at 36.

## Catalog

The catalog has 71 statuses. A status is **attachable** only when a player-side attack Runtime maps already applies
it through a DamageInfo slot. That proves both the slot mechanism and the status's behaviour on player attacks.
These 11 are attachable:

| Status | Duration | Applied today by (examples) |
| --- | --- | --- |
| `fire` | 3 s | AR-2 Coyote, flamethrowers, Breaker Incendiary, napalm, Orbital Laser |
| `fire_panic` | 1 s | flamethrowers, Crisper, Meltagun |
| `burning_heavy` | 1 s | napalm Eagle / barrage, EAT-700 |
| `flamer_slowed` | 0.5 s | flamethrowers |
| `stun_small` | 1.5 s | Arc Thrower, Blitzer, Tesla Tower |
| `stun_medium` | 3 s | AR-32 Pacifier, SMG-72 Pummeler, EMS mortar and strike |
| `stun_large` | 5 s | Stun Lance, Stun Baton, SG-20 Halt, stun grenade |
| `gas`, `gas_confusion` | 6 s / 5 s | gas grenade, gas mines / mortar / strikes, Re-Educator |
| `gas_2`, `gas_confusion_2` | 10 s / 9 s | TX-41 Sterilizer |

Everything else is catalogued read-only:
- `electric`, acid, bleed and stun massive (only enemies, hazards or other systems apply them);
- stims, terrain and weather;
- character-state statuses.

## API

Each damage object has `damage.status_<k>_type` for every used slot, plus `damage.status_<k>_type` and
`damage.status_<k>_strength` for its first empty slot. Explosion damage objects have the same fields as
`explosion.damage.status_<k>_*`. Player-weapon explosions have them since 0.30.2 (before, only support-weapon
explosions did): for example the PLAS-101 Purifier's charged-shot blast, through its explosion handle.

```lua
-- Charged Purifier shots set what their blast hits on fire (no bigger blast, nothing lingers on the ground).
local blast=hd2.weapon('PLAS-101 Purifier'):attack('primary'):projectile():terminal_action('impact'):explosion()
hd2.ensure({plan={id='purifier-incendiary-charge',operations={
    {id='fire',target=blast,allow_unverified_effect=true,changes={
        {field=hd2.fields.explosion.damage_status_1_type,expect='none',value='fire'},
        {field=hd2.fields.explosion.damage_status_1_strength,expect=0,value=2}}},
}}})
```

```lua
local bullets=hd2.support_weapon('M-1000 Maxigun'):attack('primary'):projectile()
hd2.ensure({plan={id='maxigun-stun',operations={
    {id='stun',target=bullets,allow_shared=true,changes={
        {field=hd2.fields.damage.status_1_type,expect='none',value='stun_medium'},
        {field=hd2.fields.damage.status_1_strength,expect=0,value=2}}},
}}})
```

- **Values.** A status reference takes catalog semantic IDs, or `'none'`. Only attachable statuses are accepted,
  plus the slot's current status. 34 of the 71 statuses are attachable (`attachTier` in `StatusEffectCatalog.json`):
  - `player_attack` (11): a player-side attack already applies it (fire, fire_panic, burning_heavy, the stuns, the
    gases, flamer_slowed);
  - `enemy_slot` (8, 0.30.2): the game applies it through DamageInfo slots of enemy or hazard attacks (confusion,
    lava, acid_splash, choked, stun_massive, inverted_aim_assist, tremor, tornado_stun);
  - `other_system` (15, 0.30.2, **experimental**): an attack effect the game applies by other means, never through a
    slot (acid_stream, thermite, cyborg_fire, burning_light, radiation_light/heavy, electric, bleed, poison, gloom,
    slowed, rooted, blind, deaf, stun_illuminate). Whether a slot-applied instance behaves like the game's own is
    unknown; `bleed` lasts 9999 s by definition.

  Terrain, stim, weather (including `acid_storm`, the acid-rain weather marker, which carries no damage) and system
  statuses are never attachable (`schemas/status_attachment_policy.json`). For acid on enemies use `acid_splash` or
  `acid_stream`.
- **The extended statuses always need `allow_unverified_effect`**, on every row, live-proven direct-hit rows
  included: no attack has been live-tested with them.
- **Clearing.** `'none'` clears only the last used slot, so the slots stay packed.
- **Strength.** Strengths range from 0 to 1000. Use the strength an existing user applies; the catalog lists the
  observed range for each status.
- **Duration.** Editing a status's definition (`status.duration`) is a different operation from choosing which
  status an attack applies. Duration edits are shared by every attack that applies the status.
- **Acknowledgements.**
  - **Player and support weapon projectile (direct-hit) rows need no `allow_unverified_effect`.** Attaching,
    swapping and clearing statuses there is live-proven (see below). These fields carry a `liveEvidence` reference.
  - Every other row still needs `allow_unverified_effect`:
    - explosion, spray, beam, arc and melee DamageInfo rows;
    - vehicle mounted weapons.

    The slot mechanism is the same, but no live test has exercised those rows.
  - Rows shared by several weapons also need `allow_shared`, like every other settings write.

## Status effect stats (0.30.4)

`hd2.status_effect(id)` edits a status itself, for every attack that applies it: how long it lasts, and how much
damage it deals while active (fire, gas, acid, bleed, electric and the others). Ids are the catalog's
(`sdk/StatusEffectCatalog.json`); `hd2.status_effects()` lists all 71.

```lua
-- Fire lasts 6 s instead of 3 and deals 150 per tick instead of 100, for every attack that sets enemies on fire.
hd2.ensure({patch={id='fire-duration',target=hd2.status_effect('fire'),allow_shared=true,
    field=hd2.fields.status.duration,expect=3,value=6}})
hd2.ensure({transaction={id='fire-damage',target=hd2.status_effect('fire'):damage(),allow_shared=true,
    allow_unverified_effect=true,changes={
        {field='damage.standard_damage',expect=100,value=150},
        {field='damage.durable_damage',expect=100,value=150}}}})
```

| Target | Native row | Fields |
|---|---|---|
| `hd2.status_effect(id)` | the status's StatusEffectSettings row (152-byte StatusEffectInfo) | `status.duration` (+40, seconds, 0 to 100000) |
| `hd2.status_effect(id):damage()` | the DamageInfo row the status deals while active (StatusEffectInfo +44 names it) | `damage.standard_damage`, `damage.durable_damage` (per tick), `damage.ap_direct`/`ap_slight`/`ap_large`/`ap_extreme` (0 to 10), `damage.demolition`, `damage.stagger`, `damage.push_force` |

Things to know:
- **Shared by design.** Every write needs `allow_shared`: a status definition is global. Editing fire's duration
  changes the AR-2 Coyote, the Flame Sentry and every enemy that sets you on fire. Some statuses also deal one
  DamageInfo row together: gas, gas_2 and gloom share theirs. `describe()` and
  `sdk/StatusEffectAuthoringCapabilities.json` name the statuses sharing a row (`sharedWithStatuses`) and any weapon
  using the same row directly (`otherUsers`). A conflict between two mods names the other user, like every other
  shared row (`core/shared_records.lua`).
- **Tick damage needs `allow_unverified_effect`.** How often a status deals its row (the tick rate) is not located,
  and no in-game test has measured an edit yet. 25 of the 71 statuses deal damage; the others (stuns, slows,
  confusion) have no `:damage()` target.
- **Duration** is the same field the weapon, stratagem and throwable catalogues already write through their attacks.
  As there, only `allow_shared` is required. The effective time on a target can be shorter; see "Live tests" below.
- **Not exposed:** StatusEffectInfo +36 (an unnamed FP32, e.g. fire 5, gas 0.25; its meaning is not established),
  the tick rate, and the per-enemy susceptibility tables.
- **Guards.** Every write re-proves, live, the status row's identity (type, group, row). A damage write also
  re-proves the row's link at +44 to the reviewed DamageInfo type, and that row's identity. Then the shared conflict
  rule applies. A tick link another mod changed refuses that status's damage target only (`tick damage link
  changed`).
- **Source.** `scripts/research_status_effects.py` records each row's group and row and the full tick DamageInfo
  values; `scripts/generate_status_effect_authoring.py` builds `domains/status_effect_authoring.lua` and the SDK
  catalogue. Tests: `tests/test_status_effect_authoring.py`, which includes a write on the retained snapshot.

## Guards

At write time the runtime re-proves:
- the damage row's identity and ownership chain;
- that the earlier slots are still used (and, when clearing, that the later slots are empty);
- that the live status table still stores the catalogued name for both the current and the desired status.

A renumbered or edited status table therefore can never be written through a stale catalog.

## Migration

A status slot migrates only when both builds' status tables are available and identical, row for row, with
pointers masked.
- **Same build:** every status field is EXACT.
- **Previous build (datalibrary only, no status table):** all 197 status type slots are UNCHECKED and become
  read-only, with no stale writes.
- **Changed status table:** the fields are BLOCKED until the research is re-run and the catalog regenerated.

## Not supported

- A fifth status: the slot array is fixed at four, and growing it would need object cloning.
- Stratagem, throwable and booster attacks: their DamageInfo rows have the same slots, but their write domains do not
  yet accept status references.
- Terrain, stim, weather and system statuses (see Values).

## Live tests (2026-09-29, [live evidence](live-evidence.md))

- **`LiberatorFireStatus` passed.** Liberator bullets apply `fire` (strength 2, the Coyote value) and set enemies on
  fire, while the ballistic attack otherwise behaves normally. The row is shared with the Liberator Carbine and
  StA-52.
- **`MaxigunStun` passed.** Maxigun bullets apply `stun_medium` (strength 2, the Pacifier/Pummeler value) and stun
  enemies.
- **Observed duration.** The Maxigun stun held Hunters, Berserkers and Devastators for about 1-2 s, not the 3 s that
  Stun Medium's definition stores. The observation is recorded as reported; its cause is not established.

The offline follow-up (`scripts/research_status_susceptibility.py` → `research/status-susceptibility-F5FEE03DCFDB.json`)
found that target-side status processing exists:
- Every enemy class's StatusEffectReceiverComponent holds, per status zone, a table of 33 `StatusEffectSusceptibility`
  entries. Each entry is keyed by a susceptibility type and holds a value pair.
- The pairs scale with the enemy. For one type: Warrior 2.1/3.3, Hunter 1/2, Devastator 6.2/8, Charger 8.5/10,
  Hulk 9/13.
- The type names are stripped, so which entry governs stun, and whether a pair is a duration range, a strength
  threshold or a resistance, is not identified.

So a shorter effective stun is consistent with target-side processing, but nothing is proven. `status.duration` keeps
its meaning: the duration the status definition stores.

No explosion status has been live-tested yet. Explosions apply statuses through the same slots of their own
DamageInfo row, so the mechanism is the same; the pending live test is `PurifierIncendiaryCharge` (0.30.2).
