# Beam conversion: projectile weapons that fire LAS-13 Trident pulses

**Solo only. Offline-proven; not live-tested through this API yet** (`proof/BeamConversionProof`). The mechanism
was live-proven on 2026-10-10, solo, with the experiment proofs: the AR-23 Liberator, LAS-58 Talon and SMG-32
Reprimand fired Trident pulses with their own rate of fire.

A beam conversion makes a projectile weapon fire the LAS-13 Trident's pulsed beam in this game:

- In its entity's component list, ProjectileWeapon is swapped for BeamWeapon in place (the same count, sorted).
- It gets its own BeamWeapon record, a copy of the Trident's, so it has its own rate of fire, beams per pulse and
  pulse length.
- Optionally it gets its own beam row and damage row, for its own damage, armor penetration and range.

The weapon keeps its own ammunition:

- **Magazine weapons** spend one round per pulse and reload as usual. A chamber magazine has its chamber turned off,
  as the 40-K Meltagun's is.
- **Heat weapons** heat by their own heat-per-shot on every pulse and change heat sinks as usual.

```lua
local sickle = hd2.weapon('LAS-16 Sickle'):beam_conversion()
hd2.ensure({recover = true, transaction = {id = 'sickle-beam', target = sickle,
    allow_component_swap = true, allow_unverified_effect = true, changes = {
        {field = hd2.fields.beam_conversion.enabled, expect = false, value = true},
        {field = hd2.fields.beam.fire_rate, expect = 300, value = 600},           -- the pulse is fitted (0.067 s)
    }}})

local liberator = hd2.weapon('AR-23 Liberator'):beam_conversion()
hd2.ensure({recover = true, transaction = {id = 'liberator-beam', target = liberator,
    allow_component_swap = true, allow_unverified_effect = true, changes = {
        {field = hd2.fields.beam_conversion.enabled, expect = false, value = true},
        {field = hd2.fields.damage.player_standard_damage, expect = 60, value = 600},
        {field = hd2.fields.damage.player_durable_damage, expect = 6, value = 60},
        {field = hd2.fields.damage.ap_direct, expect = 2, value = 4},
        {field = hd2.fields.beam.length, expect = 200, value = 100},
    }}})
```

Support weapons use `hd2.support_weapon(name):beam_conversion()`. `hd2.beam_conversion(name)` returns the same
target, and `hd2.beam_conversions()` returns every catalogued weapon's target.

## The target

`describe()` returns the static catalogue entry:

- `supported`, `verdict` (`supported`, `supported_with_caveats`, `refused` or `out_of_scope`), `reasonCode`,
  `reason` and `caveats`;
- `liveProven`, `roots`, `record`, `fields`, `acknowledgements`, `lifecycle`, `multiplayer`, `pulse`,
  `perWeaponRows` and `donor`.

`status()` returns the live state:

- `state`: `vanilla`, `converted`, `orphaned` or `foreign`;
- `settings`, `rows`, `pair` (its borrowed BeamType / DamageInfo), `live` (instances now);
- `path` (`owned table` or `shared record`), `lobby` and `restart_required`.

`sdk/BeamConversionCapabilities.json` has the same catalogue for tools.

| Field | Default | Range | Notes |
|---|---|---|---|
| `beam_conversion.enabled` | false | true / false | false = the weapon as shipped |
| `beam.fire_rate` | 300 | 1..900 rpm | Its own record (+104). 900 is the fastest rate whose beam was still visible in the live test ("at 1200 it's like a fast yellow projectile"). |
| `beam.pulse_beams` | 2 | 1..8 | Its own record (+108) |
| `beam.pulse_seconds` | 0.15 | 0.0334..2 s | Its own record (+112). **The pulse length limits the rate** (below). |
| `beam.length` | 200 m | 1..1000 m | Its own beam row (+8): the ray length, the sweep end and the drawn beam |
| `damage.standard_damage` (`hd2.fields.damage.player_standard_damage`) | 60 | 0..10000 | Its own damage row (+4), per pulse hit |
| `damage.durable_damage` (`player_durable_damage`) | 6 | 0..10000 | +8 |
| `damage.ap_direct`, `ap_slight`, `ap_large`, `ap_extreme` | 2, 2, 2, 0 | 0..10 | +12..+24 |
| `damage.demolition`, `stagger`, `push_force` | 10, 10, 10 | 0..1000 | +28 / +32 / +36 (the names are leads, as on every weapon) |

### Rules

- **`expect` is always the baseline:** not converted, and the Trident's values.
- **A change on a converted weapon** checks that each named field still holds its `expect` or its `value`. Anything
  else is another operation's value: `CONFLICT`.
- **Settings alone** (no `beam_conversion.enabled` in the request) are accepted only on a converted weapon. On a
  weapon that is not converted they fail with `NOT_CONVERTED`, unless they are the baseline (an ensure's restore).
- **Acknowledgements.** Every request needs `allow_component_swap=true`, because the weapon's component set changes in
  this game only. It also needs `allow_unverified_effect=true`, because this API path is not live-tested yet. Helpers
  never add either acknowledgement.
- **Not a plan operation.** A conversion runs as its own patch or transaction.

### The pulse length limits the rate

A new pulse starts only in the update **after** the previous one ended. So with frame time dt, the number of updates
between pulses is:

`n = max(ceil(60 / (fire_rate x dt)), max(1, ceil(pulse_seconds / dt)) + 1)`

The Trident's 0.15 s pulse caps any rate at about 330 to 360 rpm at 60 fps (`research/docs/beam-pulse-rate-F5FEE03DCFDB.md`).

- **When a request sets `beam.fire_rate` without `beam.pulse_seconds`, the pulse is fitted.** It keeps the Trident's
  0.15 s while that fits the rate. Otherwise it becomes `max(60 / (2 x rate), 60 / rate - 1/30)` s, which never caps
  the rate from 30 fps up, and never less than 0.0334 s. The note is logged.
- **An explicit `beam.pulse_seconds` is kept.** If it caps the rate, a `WARNING` is logged.
- **A pulse no longer than one frame deals no damage.** That is why 0.0334 s is the minimum. At 30 fps a pulse that
  hits allows at most 600 rpm.
- Rates round to whole frames, so expect a little less with a varying frame rate (about 550 for 600 rpm).
- The same applies to the real Trident's own `beam.fire_rate` / `beam.pulse_seconds`. Its pulse field is displayed as
  "Pulse duration (limits the fire rate)" and carries `beamPulse` in the capabilities.

## Coverage

`research/docs/beam-conversion-coverage-F5FEE03DCFDB.md` classifies all 115 player weapons:

- **2 supported:** LAS-16 Sickle, StA-11 SMG.
- **64 supported with caveats:** every other magazine weapon (assault rifles, SMGs, marksman rifles, pistols, the
  Breakers, the machine guns, EATs, Commando, Spear, W.A.S.P., ...), the LAS-17 Double-Edge Sickle, LAS-12 Sai, LAS-58
  Talon and LAS-99 Quasar.
- **25 refused:**
  - `ROUNDS_NO_BEAM_RELOAD`: shotguns fed by rounds, grenade launchers, the autocannon. A beam weapon reloads only by
    heat or magazine, so they would empty and never reload.
  - `LINKED_AMMO_NO_BEAM_RELOAD`: the M-1000 Maxigun and GL-28.
  - `CHARGE_WEAPON`: the Purifier, Loyalist, Accelerator, Epoch and Railgun. Their charge release fires nothing without
    ProjectileWeapon.
- **24 out of scope:** `NO_PROJECTILE_WEAPON` (melee, arc, spray) and `ALREADY_BEAM`.

The projectile LAS weapons:

| Weapon | Verdict | Notes |
|---|---|---|
| LAS-16 Sickle | supported | 1.15 heat per pulse from its own heat sink. Its wind-up does not apply on the beam path. |
| LAS-17 Double-Edge Sickle | with caveats | Its heat-stage projectiles no longer fire. The stage statuses on the wielder may still apply. |
| LAS-12 Sai | with caveats | Its list window crosses a page and is written as two 4-byte changes. How a semi-automatic trigger drives pulses is untested. |
| LAS-58 Talon | with caveats | Live-proven in the experiment |
| LAS-99 Quasar Cannon | with caveats | Its heat-per-shot equals its capacity: one pulse, then the cooldown |

Common caveats:

- **Restart after use.** Default or option deltas that patch ProjectileWeapon leave a private copy behind.
- Single, burst or selectable fire modes are untested on the pulse beam.
- The rate selector and function ammo are inert.
- An underbarrel stays a projectile weapon.

Mounted, sentry and vehicle weapons are out of scope: no wielder trigger path is proven for them.

## Per-weapon damage, armor penetration and range

**Interim, `borrowedVanillaRow`, build-scoped, solo only, not live-tested.**
`research/docs/beam-rows-borrowed-F5FEE03DCFDB.md` has the details.

A beam's damage, armor penetration and range come from the BeamInfo row of its BeamType and the DamageInfo row that row
names. Both are reached through fixed pointer arrays in game.dll, and every slot of those arrays is used. A converted
weapon that needs its own values therefore **borrows** a spare pair. It is one of six, chosen in research order:

- BeamTypes 3, 15, 16, 19, 20, 27;
- DamageInfo ids 278, 577, 233, 637, 434, 564.

On this build, no data, no traced code constant and no live record references these slots. The vanilla rows are never
written:

- each slot is repointed, with one aligned 8-byte store, to a Runtime-owned copy of the Trident's row 6 or 508 in a
  never-freed block;
- the weapon's own BeamWeapon record then names the borrowed BeamType;
- BeamFire copies the weapon's damage id, multipliers and range into every shot, so there is no timing window.

Refusals:

- `ROWS_FULL`: a seventh weapon with its own rows. A plain conversion still works.
- `BORROWED_ROWS_UNVERIFIED_BUILD`: any other game build, until `scripts/research_beam_rows.py` is re-run.
- `SHARED_RECORD_FALLBACK`: the owned table is unavailable.

A restore waits until no live shot uses the borrowed BeamType, which takes one pulse.

**The per-shot route is not used.** The experiment `runtime/experiment_beam_damage.lua` wrote each shot's ring entry.
It was unreliable live: the Reprimand had 91 shots seen, 10 written and 81 `MISSED`, then 150 seen, 75 written and 49
`MISSED`. Most pulses hit in the update they were fired, before Lua saw them.

## Lifecycle

- **Zero live instances, at the write and at the restore.** This covers every instance on this machine: the ship
  preview, the armory, any loadout, pickups, and other players' weapons of that type. Changing the list under a live
  instance corrupts the BeamWeapon destroy of another beam entity.
  - A busy gate is `TARGET_UNAVAILABLE: BUSY`. A transaction retries a few times; an ensure with `recover` keeps
    waiting.
  - In practice: equip other weapons, keep the armory closed, change the option, wait for `APPLIED`, then equip.
- **Settings and row values** of a converted weapon are written at once, even with the weapon in hand. They are read
  at every shot.
- **Assets.** The Trident's package (`laser_shotgun`, the beam effect and sounds) is loaded and held before any write.
- **The table.** A Runtime-owned copy of the BeamWeapon table holds one record per catalogued weapon, made live by one
  8-byte store into its slot. It is never freed, and at most 16 copies are built per game process. Up to 22 roots
  can be converted at once: the table's 23 empty rows, less the one that always stays free (`TABLE_FULL`).
  - Rows go on each root's probe path. A restore removes a row with linear-probing deletion, which moves a later
    conversion's row up if it probed past the removed one.
  - The last restore puts the slot back. It does not if a typed write changed a record in the copy meanwhile, because
    that write would be lost.
- **Foreign changes are refused.** This covers another mod's moved BeamWeapon table (True Lasgun Beam Overhaul),
  another value in any row, list or byte this feature writes, and the experiment proofs' copy (`CONFLICT`). The Runtime
  never chains onto them.
- **The shared fallback.** Without the owned table (a pin, the adapter, the copy budget), the file table's one unowned
  record 23 becomes the Trident's copy, and every converted weapon shares the Trident's own settings.
- **Restart the game after using a conversion.** A weapon spawned while converted may leave a ProjectileWeapon private
  copy behind.
- While converted, typed writes reached through the weapon's ProjectileWeapon are refused: its fire rate, projectile,
  ammunition and the rows they link to.

## Multiplayer

`research/docs/beam-conversion-mp-F5FEE03DCFDB.md` and `research/docs/beam-conversion-mp-sync-F5FEE03DCFDB.md` have the
details.

- **An apply is solo only.** With another player in the game or the lobby it waits (`NOT_SOLO`). A restore is allowed
  with others present.
- **Every machine builds weapons from its own lists.**
  - Your converted weapon fires beams on your machine. Other players see it as shipped (replicated rate 0, no beam;
    no network type replicates BeamWeapon). As host you decide enemy damage, so they see enemies take damage.
  - A weapon of a converted type that **another** player owns is built on your machine without ProjectileWeapon. Its
    network apply then writes through index -1, and **your game crashes** when that weapon spawns. This happens if a
    joiner carries one, and also if you are a client in another lobby.
- **The same conversion on every machine does not help.** The game picks a remote weapon's network apply by its
  network type alone, and every convertible type's apply calls the ProjectileWeapon step unconditionally (pinned for
  all 72 convertible network types). If both players convert the Liberator, **each** game crashes when the other's
  Liberator spawns. So multiplayer stays refused even when every player runs the Runtime with identical options.

### The conversion sync (`hd2bc`)

Each Runtime shares its conversions with the lobby, as the synced asset loader shares its packages: one lobby member
property, the key `hd2bc` in the `hd2bc/1` grammar. It uses the same channel and rate limits as `hd2rt` and `hd2as`.

- **Posted** once this machine has applied a conversion in this session:
  - per converted root: the resource, the path (owned table or shared record), a digest of its BeamWeapon record (rate,
    beams, pulse) and of its borrowed beam and damage rows (range, damage, AP), and the borrowed pair;
  - the Runtime version, the game build and the catalogue hash, and one digest of the whole set.
  - After the last restore the empty set is posted, so the lobby never keeps a stale set. At most 11 converted roots
    fit in the 512-byte value.
- **Read** from every other member every 3 s in a lobby of 2 or more. Each member is one of:

  | State | Meaning |
  |---|---|
  | `match` | same version, build, catalogue and digest |
  | `mismatch` | another set of conversions |
  | `incompatible` | another Runtime version, build or catalogue |
  | `malformed` | a value that is not exactly `hd2bc/1` |
  | `pending` | no value yet, within 30 s of first seeing the member |
  | `no runtime` | no value after 30 s: no Runtime, an older one, or one that has converted nothing |

- **Decision.** Solo: the apply goes ahead (unchanged). With any other member it is `REFUSED`:
  - with the first problem found: `NO_RUNTIME`, `MALFORMED`, `INCOMPATIBLE`, `MISMATCH` or `PENDING`;
  - otherwise `REMOTE_APPLY_UNSAFE`, even when every member, the host included, posts the identical set.
  No build is proven safe, so no member state allows an apply. The `NOT_SOLO` refusal names the decision.
- **Log lines** start with `BEAM CONVERSION SYNC:`: the posted set, every member's state change, and the decision
  while this machine has a conversion.

### What the Runtime does when another player is present

| Case | What happens |
|---|---|
| Someone joins your lobby; your converted weapon is not in use | The lobby is read every second. On the first sight of the new member, every converted weapon with no live instance is restored, long before their weapons spawn. The empty set is posted. |
| Someone joins while your converted weapon is in hand | It cannot be restored: changing its list under a live instance corrupts the BeamWeapon destroy. A loud warning and the safety notice appear, and the restore is retried every 5 s until it is no longer live. If the joiner runs the Runtime, their game reads your set and warns **them** not to carry, call in, drop or pick up that weapon. A joiner without the Runtime who carries it crashes your game. The lobby data holds no loadout, so this cannot be known in advance. |
| You join someone else's lobby with a conversion | The same watch restores idle conversions as soon as the lobby shows the others. If a converted weapon is live on your ship while the join loads, it can be restored only after your ship unloads; whether that happens before the host's weapons spawn is not proven. **Unequip converted weapons before joining.** |
| Another member's set lists conversions | Your Runtime warns you and names the weapons. Spawning one of them crashes that member's game. |
| Blocking the join or the mission start | Not possible: the Runtime has no input blocking and no menu-state hook. |

- The mods' ensures stay registered: their apply waits (`NOT_SOLO`) and converts again once the game is solo.
- **Still unsafe:** a converted weapon in hand when a player joins, a joiner without the Runtime who carries that
  type, and joining a lobby with a converted weapon equipped.
- `proof/BeamConversionSyncProof` has the two-machine test plan.

## Editor

`sdk/BeamConversionCapabilities.json`:

- `weapons[]`: `name`, `target` (the Lua expression), `verdict`, `reasonCode`, `reason`, `caveats`, `liveProven`,
  `roots`, `restartAfterUse`, `chamberFix`, `heatPerPulse`;
- `fields[]`: `id`, `displayName`, `default`, `min`, `max`, `unit`, `note`, `rangeReason`, `row`, `perWeapon`;
- `acknowledgements`, `lifecycle`, `multiplayer`, `pulse`, `perWeaponRows`.

A tool should show:

- the verdict and the caveats;
- the enable toggle;
- rate, beams and pulse, with the pulse/rate note;
- the damage, AP and range fields under a "per-weapon rows (interim, max 6)" heading;
- the solo and "unequip first" rules.
