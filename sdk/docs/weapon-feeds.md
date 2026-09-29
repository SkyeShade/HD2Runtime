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
magazine pattern: 39 player and 10 support weapons (`programmableAddable` in the catalog).

```lua
-- S-11 Speargun: Gas (normal) and a selectable Stun ammunition (examples/projects/SpeargunGasStunTest).
local spear=hd2.support_weapon('S-11 Speargun')
local source=spear:feed('programmable'):source()
-- {writable=true, target=spear, field='function_ammo.projectile', expect='none',
--  binding={field='weapon_function.left', expect='none', value='programmable_ammo'},
--  acknowledgements={'allow_unverified_effect','allow_unverified_reference'}}
hd2.ensure({transaction={id='speargun-stun',target=source.target,allow_unverified_effect=true,
    allow_unverified_reference=true,changes={
        {field=source.binding.field,expect='none',value='programmable_ammo'},
        {field=hd2.fields.function_ammo.projectile,expect='none',value=hd2.attack_output('GL-52 De-Escalator')}}}})
```

| Field | Values |
| --- | --- |
| `hd2.fields.function_ammo.projectile` | `'none'` (no second feed), `weapon:feed('programmable'):projectile()` (the native projectile: restore), or `hd2.attack_output(name)` of a selectable projectile output |
| `hd2.fields.weapon_function.left` / `.right` | `'programmable_ammo'` on an unbound input |

- **Pairing.** A function projectile on a weapon without the selector needs the binding in the same transaction,
  and the binding needs the projectile (`SELECTOR_REQUIRED` otherwise).
- **Donors.** Only projectile outputs: the donor's owner entity, its ProjectileWeapon record and the ProjectileSettings
  row are re-proven live, and its package is loaded first (the 0.27 asset loader). Beam, arc, spray and melee outputs
  fail closed with `INCOMPATIBLE_OUTPUT_FAMILY`.
- **Host.** The host must still have the shape the research saw (rounds feed or not, no spawned entity, no magazine
  pattern); otherwise `FUNCTION_HOST_CHANGED`.
- **Acknowledgements.** `allow_unverified_effect` and `allow_unverified_reference`: the mechanism is proven, a given
  composition is not gameplay-tested.
- **Native hosts.** The AC-8, GR-8 and RL-77 can swap their own function projectile for a donor, and restore it with
  `weapon:feed('programmable'):projectile()`.
- **When it applies.** The binding is copied into a weapon when it is built; the projectile is read at every shot.
  Call in or rebuild the weapon after a change.
- **In game** the new selector appears in the weapon's function menu as the game's own ProgrammableAmmo entry; its
  label is the game's generic one for that function (not traced).

### Speargun gas / stun result

The Speargun has no WeaponRounds component, so it cannot take a second magazine; the component layout is never
changed. It does have an empty +576 and a free left input, so the programmable-ammunition feed gives it a genuine
player-selectable second ammunition: gas spears when the function is off, the chosen stun projectile when it is on.
The stun choices are projectile outputs with stun: GL-52 De-Escalator (arc on impact; live-proven donor), AR-32
Pacifier and SMG-72 Pummeler stun rounds. A "stun spear" (the spear with a stun explosion) is not offered: it would
need a new projectile row, and settings tables cannot grow.

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
  a changed host, a beam donor and a missing reference acknowledgement are refused. It pins the Speargun write
  (+576 = the GL-52 projectile, left input = ProgrammableAmmo) and its declared GL-52 package.
- The packaged-runtime scenario `example-speargun-gas-stun-test` runs the live test from the built ZIP: one package
  request per donor, one write per donor switch, disable removes both.
- `example-halt-feed-test` applies the Halt feed test from the built ZIP.
