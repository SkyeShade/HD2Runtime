# Weapon feeds: selectable ammunition and outputs

Some weapons let the player switch what they fire. Helldivers 2 has exactly two native mechanisms for it, and Runtime
publishes both as **feeds**: `weapon:feeds()` and `weapon:feed(id)`.

| Mechanism | Native storage | Selector | Native weapons |
| --- | --- | --- | --- |
| `rounds_magazine` | WeaponRoundsComponent +64 / +68: the primary and alternate magazine projectile; +72 their capacities | the `Magazine` weapon function | SG-20 Halt |
| `programmable_ammo` | ProjectileWeaponComponent +576: fired instead of the normal projectile while the function is on | the `ProgrammableAmmo` weapon function | AC-8 Autocannon (flak), GR-8 Recoilless Rifle, RL-77 Airburst (and P-33, P-92, StA-X3, which spawn entities through it) |

Every weapon with a projectile also has a `primary` feed: its normal projectile.

Not a feed, and never conflated with one:

- **fire modes** (Automatic / Single / Burst) never select projectiles ([fire modes](fire-modes.md));
- **multiple projectiles per shot** are `projectile.pellet_count` on the projectile row;
- **submunitions** hang off the projectile's impact explosion (`explosion.shrapnel_*`);
- **default ammunition** (`weapon:ammunition()`) is the customization that owns the normal projectile of six
  weapons ([attack outputs](attack-outputs.md));
- **output families** (beam, arc, spray, melee) are their own components ([cross-family outputs](#cross-family-outputs)).

## The SG-20 Halt

Proven from the type library, the entity table and deltas, game.dll code and the retained snapshots
(`scripts/research_weapon_functions.py`):

- Both magazines exist on every built Halt. Its default customization patches them at every build: slot 6
  **SHOTGUN 10g. FLECHETTES** sets the primary projectile (+64), slot 7 **SHOTGUN 10g. Stun ALTERNATE** the
  alternate (+68). Each has its own capacity (8 and 8), recoil and spread modifiers, and its own projectile row with
  its own DamageInfo (flechettes AP 3; stun pellets AP 2 with Stun).
- The left weapon-function input binds `Magazine`. The weapon-function value reader returns the selected magazine
  from the built weapon's weapon_rounds record (manager `weapon_rounds`, capacity 64, 20-byte records, +4).
- The armory lists both feeds' penetration: LIGHT and MEDIUM ARMOR PENETRATING.

```lua
local halt=hd2.weapon('SG-20 Halt')
local primary,alternate=halt:feed('primary'),halt:feed('alternate')
primary:describe()    -- {mechanism='rounds_magazine', selector={function='magazine', input='left', bound=true},
                      --  capacityField='rounds.feed_capacity_1', ownedBy='SHOTGUN 10g. FLECHETTES', ...}
primary:projectile()  -- the flechette projectile handle (its projectile.* and damage.* fields)
alternate:source()    -- where the feed projectile lives: read-only, owned by the Stun ALTERNATE delta
```

Each feed is edited on its own: its capacity through `feed:describe().capacityField` on the weapon, its projectile
and damage through `feed:projectile()`. Swapping a rounds feed's projectile (writing its ammunition delta) is not
authored yet: `feed:source()` says so, with the owning customization.

Punisher, Slugger and Cookout also carry a non-zero alternate magazine projectile, but no `Magazine` selector is
bound: they are not selectable (`roundsAlternateWithoutSelector` in the catalog).

## Programmable ammunition

The projectile fire path (game.dll 0x615940) receives the projectile the weapon would fire, resolves the weapon's
ProjectileWeaponComponentData (a per-weapon resolved copy when one exists, else the entity-table record), and when the
weapon's `ProgrammableAmmo` function state is on replaces the projectile with +576 if it is non-zero (and the spawned
entity with +584 if that is non-zero). That is how the AC-8, GR-8 and RL-77 switch between two projectiles.

A weapon can **gain** this second feed when it has the member (every ProjectileWeapon does), a free weapon-function
input, an ordinary projectile trigger (the fire-mode research's constraints), no rounds feed, no spawned entity and no
magazine pattern: 39 player and 10 support weapons (`programmableAddable` in the catalog). The same feed and field
serve player and support weapons; `weapon:programmable_ammo()` is the builder over it
([projectile builder](#projectile-builder)).

```lua
-- S-11 Speargun: Gas (normal) and a selectable EMS stun field (examples/projects/SpeargunGasStunTest).
local spear=hd2.support_weapon('S-11 Speargun')
local source=spear:feed('programmable'):source()
-- {writable=true, target=spear, field='function_ammo.projectile', expect='none',
--  binding={field='weapon_function.left', expect='none', value='programmable_ammo'},
--  acknowledgements={'allow_unverified_effect','allow_unverified_reference'}}
hd2.ensure({transaction={id='speargun-stun',target=source.target,allow_unverified_effect=true,
    allow_unverified_reference=true,changes={
        {field=source.binding.field,expect='none',value='programmable_ammo'},
        {field=hd2.fields.function_ammo.projectile,expect='none',
            value=hd2.attack_output('A/M-23 EMS Mortar Sentry')}}}})
```

| Field | Values |
| --- | --- |
| `hd2.fields.function_ammo.projectile` | `'none'` (no second feed), `weapon:feed('programmable'):projectile()` (the native projectile: restore), or `hd2.attack_output(name)` of a selectable projectile output |
| `hd2.fields.weapon_function.left` / `.right` | `'programmable_ammo'` on an unbound input |

- **Pairing.** A function projectile on a weapon without the selector needs the binding in the same transaction,
  and the binding needs the projectile (`SELECTOR_REQUIRED` otherwise).
- **Donors.** Only projectile outputs: the donor's owner entity, its ProjectileWeapon record and the ProjectileSettings
  row are re-proven live, and its package is loaded first (the 0.27 asset loader). Beam, arc, spray and melee outputs
  fail closed with `INCOMPATIBLE_OUTPUT_FAMILY`. Besides weapon outputs, the catalog has one stratagem-owned donor,
  the A/M-23 EMS Mortar Sentry shell ([stun-field donors](#stun-field-donors)); it is offered for
  `function_ammo.projectile` only (`OUTPUT_SCOPE` elsewhere).
- **Host.** The host must still have the shape the research saw (rounds feed or not, no spawned entity, no magazine
  pattern); otherwise `FUNCTION_HOST_CHANGED`.
- **Acknowledgements.** `allow_unverified_effect` and `allow_unverified_reference`. The mechanism was shown in play
  on the Speargun (2026-09-30: a real two-mode selector, gas in mode A, the donor in mode B), but that run is recorded
  as partial (the GL-52 donor was not the intended stun field), so every composition keeps both.
- **Native hosts.** The AC-8, GR-8 and RL-77 can swap their own function projectile for a donor, and restore it with
  `weapon:feed('programmable'):projectile()`.
- **When it applies.** The binding is copied into a weapon when it is built; the projectile is read at every shot.
  Call in or rebuild the weapon after a change.
- **In game** the new selector appears in the weapon's function menu as the game's own ProgrammableAmmo entry. Each
  mode shows its projectile's own label and icon ([mode labels and icons](#mode-labels-and-icons)).

### Speargun gas / stun

The Speargun has no WeaponRounds component, so it cannot take a second magazine; the component layout is never
changed. It does have an empty +576 and a free left input, so the programmable-ammunition feed gives it a genuine
player-selectable second ammunition: gas spears when the function is off, the function projectile when it is on.

The first live run (2026-09-30) used the GL-52 De-Escalator. The selector worked and gas stayed normal, but the GL-52
arc grenade does heavy electric damage rather than stunning an area. The stun mode now fires the EMS Mortar shell,
which leaves an EMS field where it lands.

### Projectile builder

`weapon:programmable_ammo()` builds a programmable mode from native pieces; see
[the projectile builder](attack-outputs.md#projectile-builder-slots-spare-twins-and-composition-classes) for slots,
spare twins and the composition classes.

- **Speargun, keeping the spear** (examples/projects/SpeargunProjectileBuilderTest).
  - Mode A (GAS) is the Speargun's own spear. Its gas comes from two places: the direct hit applies gas and gas
    confusion, and the expiry explosion leaves the gas cloud. Impact explosion: none.
  - Mode B (STUN) fires the Speargun's spare twin, the same spear on an independent native row, with its expiry
    explosion pointed at the EMS Mortar shell's (a StaticField). The flight, model and direct hit stay the spear's;
    the field forms where the spear expires instead of the gas cloud. No other weapon changes. The EMS turret's
    package is loaded first.
- **HMG special ammunition** (examples/projects/HMGSpecialAmmoTest).
  - The HMG's right input selects its rate of fire; the ProgrammableAmmo function goes on the free left input.
  - Its own bullet row is shared (15 typed references across 6 entities) with no spare twin, so a status on the HMG's
    own bullet would need `allow_shared` and change all of them.
  - The mode fires a same-class donor bullet that already applies the status on hit: R-4 Hyena (fire), AR-32
    Pacifier (Stun Medium) or P-35 Re-Educator (gas), chosen in Mod Options. The flight and damage are the donor's.
  - No catalogued ballistic bullet applies acid on hit.
- **Labels.** Mode labels default to `mode_icon = "auto"`: the exact native icon, else the plain round
  (`ammo_slug`), never the empty placeholder.

## Stun-field donors

`scripts/research_stun_field_donors.py` (`research/stun-field-donors-F5FEE03DCFDB.json`) answers what a stun field
is natively, from the pinned type library and the settings and entity tables of the retained snapshot:

- **A lingering field is part of an explosion**, not a separate entity or status. ExplosionInfo +100 is a
  `StatusEffectTemplateType` (`persistent_status_volume`, hidden name length 24) and +104 its duration in seconds
  (`status_volume_effect_time`, length 25). An explosion with a template leaves a status volume of it. The Speargun's
  gas cloud is exactly this: its spear ends in an explosion with the Gas template for 10 s.
- **The EMS field is the StaticField template.** Every explosion carrying it applies Stun Medium (strength 100) and
  no damage. None spawns a separate object on impact.

| Candidate | What it is | Decision |
| --- | --- | --- |
| A/M-23 EMS Mortar Sentry shell | a projectile; its expiry explosion leaves a StaticField volume, 7 s, radius 10 | **supported**: fired by the turret's own ProjectileWeapon (unique owner), which owns its own loadout package |
| Orbital EMS Strike shell | a projectile; its impact explosion leaves a StaticField volume, 15 s, radius 13 | blocked: owned by the orbital's BombardmentComponent, which the runtime profile does not describe (the source cannot be re-proven live) |
| Mission artillery EMS shell | the same field, 15 s | blocked: owned by a mission objective, no loadout package |
| G-23 Stun grenade | a thrown entity whose explosion applies one Stun Large burst, no field | not a projectile: spawning it would be the function entity member (+584), which Runtime does not write |
| emp_grenade throwable | a thrown entity detonating the Orbital EMS static-field explosion | not a projectile (as the G-23) |
| Environmental stun sources | stun explosions and volumes (a Freezing volume with Stun Medium, a Stun Massive burst) with no owner in the entity or settings tables | not selectable: requested by code or data outside those tables, no package |
| GL-52 De-Escalator | arc on impact, no field | works (the tested donor), but it is not a stun field |

The EMS Mortar shell keeps its own flight (100 m/s with drop) and small impact explosion; the field forms where it
lands. `hd2.attack_output('A/M-23 EMS Mortar Sentry'):describe().fieldEffect` publishes the field
(`{volume='StaticField', seconds=7, radius=10, status={{status='stun_medium', strength=100}}}`). An EMS field can
stun Helldivers too.

## Mode labels and icons

A weapon-function mode shows the **fired projectile's own** label and icon
(`scripts/research_weapon_presentation.py`, `modes`). ProjectileInfo +12 is the short mode label (a localization
string ID) and +16 the HUD icon resource. Every native selectable mode reads as these members: AC-8 APHET / FLAK,
GR-8 HEAT / HE, the Halt's FLECHETTES / STUN magazines, guidance on / off. Their icons are under
`content/ui/mission/hud/weapon_function/`. A projectile no menu shows holds a placeholder label with no string and the
shared placeholder icon (an empty spot in the menu): the Speargun spear and the EMS Mortar shell are two of them. The menu reader itself is not traced.

```lua
-- Mode A (the spear): GAS with the generic ammunition icon ("auto"). Mode B (the EMS shell): STUN with the stun icon.
hd2.ensure({transaction={id='gas-label',target=hd2.attack_output('S-11 Speargun'),
    allow_unverified_effect=true,changes={
        {field=hd2.fields.presentation.mode_label,expect='none',value='gas'},
        {field=hd2.fields.presentation.mode_icon,expect='default',value='auto'}}}})
hd2.ensure({transaction={id='stun-label',target=hd2.attack_output('A/M-23 EMS Mortar Sentry'),
    allow_unverified_effect=true,changes={
        {field=hd2.fields.presentation.mode_label,expect='none',value='stun'},
        {field=hd2.fields.presentation.mode_icon,expect='default',value='ammo_stun'}}}})
```

| Field | Values |
| --- | --- |
| `hd2.fields.presentation.mode_label` | a native mode label: `none`, the labels native modes use (`flak`, `he`, `heat`, `stun`, `flechettes`, `sabot`, ...) and five native strings no mode uses yet (`gas`, `arc`, `incendiary`, `smoke`, `standard`); `output:mode_labels()` lists them |
| `hd2.fields.presentation.mode_icon` | a native weapon-function icon (`ammo_stun`, `ammo_flak`, `ammo_he`, ...), `auto` (see below) or `default` (restores the unlabelled placeholder: an empty spot in the menu); `output:mode_icons()` |

- **Target.** The attack output whose projectile the mode fires (`hd2.attack_output(name)`): a weapon's own output
  for its normal mode, the donor's for a programmable mode. Every selectable projectile output has both fields.
- **Shared definitions.** The label is on the projectile's settings row, so every weapon firing that projectile shows
  it. `allow_shared` is required when other entities fire it (the catalog's `presentation.shared`); the spear and the
  EMS shell are each fired by one entity.
- **Icon fallback.** A mode should never show a blank icon just because its effect has no native one. The native
  set is 14 weapon-function icons in one texture set (`research/weapon-presentation-F5FEE03DCFDB.json`, `modes`:
  `iconTextures`, `iconVisuals`). The unlabelled default is a placeholder (a skull resource from another texture
  set) that the menu shows as an empty spot (the GAS and default-icon live tests, 2026-09-30). `mode_icon = "auto"`
  resolves deterministically:
  1. the **exact** native icon: the one icon every native mode with that label shows (`stun` -> `ammo_stun`,
     `flak` -> `ammo_flak`, `he` -> `ammo_he`, `sabot` -> `ammo_flechettes`, `cluster_bomb` -> `ammo_frag`, ...);
  2. otherwise the **generic fallback** `ammo_slug`: a single plain cartridge, the only native icon that implies
     no effect (every other one shows stun, an explosion, armour piercing, a jet, darts, pellets, guidance, burst
     rounds, C4 or an airstrike). `gas`, `arc`, `incendiary`, `smoke`, `standard` and any label without a native
     icon resolve here.
  `auto` uses the `mode_label` written in the same operation, else the output's current label.
  `output:mode_icon_for(label)` returns `{icon, source}` (`exact_native` / `generic_fallback`), and the catalog
  publishes the same per label (`modePresentation.labels[].icon`, `iconSource`). An explicit native icon always
  wins over `auto`; restoring (disabling the operation) writes the native label and icon back.
- **Custom text and icons** are not supported in this release: labels are native localization strings, icons native
  weapon-function icons. Arbitrary icon assets are a later step.
- **Guards.** `domains/output_writes.lua` re-proves that the output's owner still fires that projectile and the
  settings row identity; the icon is written as two aligned 4-byte halves in one transaction.
- **Acknowledgement.** `allow_unverified_effect`: the members and the native data pattern are proven, but the menu
  reader is not traced and an edited label has not been seen in game yet.
- **Feeds.** `feed:describe().presentation` gives each feed's current `label`, `icon`, `displayName` (the native
  label text, else Primary / Alternate / Programmable) and, for the primary feed, the output that edits it.

## Catalog

`sdk/WeaponFeedCapabilities.json` (contract `hd2runtime.weapon.feeds.v1`) lists every weapon's feeds with mechanism,
selector (function, input, bound, bindable inputs), capacity field, owning customization, projectile source,
writability, acknowledgements, whether the binding is required, and the summary lists (native multiple outputs,
programmable addable, rounds dual feeds).

## Cross-family outputs

A projectile weapon cannot fire a beam. `sdk/OutputCompositionCapabilities.json` and [attack outputs](attack-outputs.md)
record the exact blockers for AR-23 Liberator -> LAS-5 Scythe, LAS-98 Laser Cannon and LAS-13 Trident.

## Validation

- `scripts/validate_weapon_modes_snapshot.py`: every addable host gains the binding and a GL-52 donor (two writes),
  the three native hosts swap and restore their own projectile, all with exact read-back and rollback; a stale donor,
  a changed host, a beam donor and a missing reference acknowledgement are refused. It pins the Speargun GL-52 write
  and the EMS write (+576 = the EMS Mortar shell, the turret's package declared), refuses a stale turret record and
  the EMS donor on an ordinary projectile reference (`OUTPUT_SCOPE`). Every selectable projectile output's mode label
  and icon apply as no-ops, change exactly their bytes and roll back; conflicts, stale owners, a missing shared or
  effect acknowledgement, unknown, unoffered and custom values are refused; the Speargun GAS and EMS STUN writes are
  pinned.
- The packaged-runtime scenario `example-speargun-gas-stun-test` runs the live test from the built ZIP: one package
  request (the EMS turret's), the mode and the two label operations each apply, restore and re-apply only their own
  writes.
- `example-halt-feed-test` applies the Halt feed test from the built ZIP.
