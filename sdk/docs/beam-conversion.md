# Beam conversion: projectile weapons that fire LAS-13 Trident pulses

**Offline-proven; not live-tested through this API yet** (`proof/BeamConversionProof`,
`proof/BeamConversionSyncProof`). The swap layout's mechanism was live-proven on 2026-10-10, solo, with the experiment
proofs: the AR-23 Liberator, LAS-58 Talon and SMG-32 Reprimand fired Trident pulses at their own rates of fire. The add
layout is new and not live-tested.

A beam conversion makes a projectile weapon fire the LAS-13 Trident's pulsed beam in this game. The catalogue picks one
of two layouts for each weapon (`describe().layout`):

- **Add layout** (the default where supported, 42 weapons).
  - The weapon keeps ProjectileWeapon and **gains** BeamWeapon.
  - Its entity map row names a Runtime-owned copy of its component list with BeamWeapon added (sorted). Only the
    row's list pointer and count change.
  - Its own ProjectileWeapon type is set to 0, so every projectile shot ends before it fires anything.
  - Multiplayer is allowed when every player holds the identical conversion. No restart is needed.
- **Swap layout** (the other 24 supported weapons). ProjectileWeapon is swapped for BeamWeapon in place (the same
  count, sorted). Solo only; restart the game after using it.

Either way:

- The weapon gets its own BeamWeapon record, a copy of the Trident's. So it has its own rate of fire, beams per pulse
  and pulse length.
- Optionally it gets its own beam row and damage row, for its own damage, armor penetration and range.

The weapon keeps its own ammunition:

- **Magazine weapons** spend one round per pulse and reload as usual. A chamber magazine has its chamber turned off,
  as the 40-K Meltagun's is.
- **Heat weapons** heat by their own heat-per-shot on every pulse and change heat sinks as usual. Under the add layout,
  the ProjectileWeapon rate is set below the pulse cadence so the kept projectile path adds no heat of its own (below).

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

- `supported`, `layout` (`add`, `swap` or none), and the layout's `verdict` (`supported`, `supported_with_caveats`,
  `refused` or `out_of_scope`), `reasonCode`, `reason` and `caveats`;
- `add` and `swap`: each layout's own verdict, reason and caveats;
- `liveProven`, `liveProvenLayout`, `roots`, `record`, `fields`, `acknowledgements`, `lifecycle`, `multiplayer`,
  `pulse`, `perWeaponRows` and `donor`.

`status()` returns the live state:

- `state`: `vanilla`, `converted`, `orphaned` or `foreign`;
- `layout` (`add` or `swap`) and `multiplayer` (`identical conversions only` or `solo only`);
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
  this game only (either layout). It also needs `allow_unverified_effect=true`, because this API path is not live-tested yet. Helpers
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

`research/docs/beam-conversion-coverage-F5FEE03DCFDB.md` (the swap layout) and
`research/docs/beam-conversion-add-layout-F5FEE03DCFDB.md` (the add layout) classify all 115 player weapons.

- **42 on the add layout.**
  - Most assault rifles, SMGs, marksman rifles and pistols.
  - The Stalwart, the HMG, the Spear and the Speargun.
  - The Hot-Shot and the Scorcher.
  - The LAS-16 Sickle, LAS-12 Sai and LAS-58 Talon.
- **24 on the swap layout only** (solo). The add layout refuses them:
  - `AMMUNITION_SETS_PROJECTILE` (8): an ammunition delta sets the projectile type in the weapon's private copy, so its
    bullets would still fire. The AR-23 Liberator, JAR-5 Dominator, MP-98 Knight, P-19 Redeemer, P-2 Peacemaker,
    R-63 Diligence, SG-225 Breaker and SMG-37 Defender.
  - `NETWORKED_SHOTS` (9): the shot is sent to the other players as an RPC before the type test. The EATs, GL-21,
    GR-8, RL-77, APW-1, SG-8P and LAS-99 Quasar.
  - `FUNCTION_AMMO` (3): weapon-function ammunition with its own type. The P-33, P-92 and W.A.S.P.
  - `ROUND_LIST_MAGAZINE` (2): the MG-43 and the MGX-42.
  - `HEAT_STAGE_PROJECTILES` (1): the LAS-17 Double-Edge Sickle's heat stages fire their own projectiles.
  - `PROJECTILE_HOOK` (1): the MLS-4X Commando.
- **25 refused**, by either layout:
  - `ROUNDS_NO_BEAM_RELOAD`: shotguns fed by rounds, grenade launchers, the autocannon. A beam weapon reloads only by
    heat or magazine, and their fired type comes from their rounds.
  - `LINKED_AMMO_NO_BEAM_RELOAD`: the M-1000 Maxigun and GL-28.
  - `CHARGE_WEAPON`: the Purifier, Loyalist, Accelerator, Epoch and Railgun. Untested on either layout.
- **24 out of scope:** `NO_PROJECTILE_WEAPON` (melee, arc, spray) and `ALREADY_BEAM`.

The projectile LAS weapons:

| Weapon | Layout | Notes |
|---|---|---|
| LAS-16 Sickle | add | 1.15 heat per pulse from its own heat sink. Its wind-up does not apply on the beam path. |
| LAS-17 Double-Edge Sickle | swap | Its heat-stage projectiles no longer fire. The stage statuses on the wielder may still apply. |
| LAS-12 Sai | add | How a semi-automatic trigger drives pulses is untested. With the Blaster Focus attachment, heat steps come at the faster of 950 rpm and the pulse rate. |
| LAS-58 Talon | add | Live-proven in the swap experiment |
| LAS-99 Quasar Cannon | swap | Its heat-per-shot equals its capacity: one pulse, then the cooldown |

Common caveats:

- Single, burst or selectable fire modes are untested on the pulse beam.
- The rate selector is inert: under the add layout it moves only the silent projectile timer.
- Function ammo is inert.
- An underbarrel stays a projectile weapon.
- **Swap layout only: restart after use.** Default or option deltas that patch ProjectileWeapon leave a private copy
  behind. Under the add layout, ProjectileWeapon's destroy frees it.

Mounted, sentry and vehicle weapons are out of scope: no wielder trigger path is proven for them.

### How the add layout keeps the projectile path silent

`research/docs/beam-conversion-add-layout-F5FEE03DCFDB.md` has the code.

- **Two independent paths.** With both components, the beam update and the projectile update each fire from the
  weapon's trigger. The game's trigger dispatch prefers ProjectileWeapon, but it only sets a mode byte, so the beam
  fires anyway.
- **The suppression.** The projectile shot takes its type from the weapon's own ProjectileWeapon record (the chamber
  is filled from it too). The conversion sets that type to 0, and a type-0 shot ends at the game's own empty-magazine
  exit. That is before the bullet, the round spent, the recoil and the sound.
  - No shared projectile row is written. True Lasgun Beam Overhaul zeroes the pellets of a projectile row, which
    silences every weapon of that type.
- **Heat weapons.** Each pulse runs the weapon's heat step once, and so does every projectile-update shot. The
  conversion therefore sets the weapon's own ProjectileWeapon rate to 90 % of the slowest pulse cadence from 30 to
  240 fps.
  - The beam update runs first in the game's update, so each pulse pushes the projectile timer ahead.
  - The projectile path never fires on its own, and heat comes once per pulse.
  - A rate or pulse change on a converted heat weapon rewrites that rate; it takes effect at the next spawn.

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
- **Swap layout: restart the game after using it.** A weapon spawned while swap-converted may leave a ProjectileWeapon
  private copy behind.
- **Add layout: the lists.** One Runtime-owned, never-freed, read-only block per game process holds every add-layout
  root's list with BeamWeapon added.
  - Converting writes only the root's entity map row: the list pointer first, then the count. The restore runs in
    reverse. In between, a reader would see the first N entries of the grown list, never a byte of the next list.
  - The file's own packed list and every other row stay byte-identical.
  - HD2Runtime's catalogue accepts exactly that pointer, count and block content. Another program's relocated list
    (True Lasgun Beam Overhaul grows the Sickles' and the Sai's) is still a stray row: refused, and never chained onto.
- **Add layout: the record writes.** The weapon's own ProjectileWeapon +0 (the type) and, for heat weapons, +8 (the
  rate) are pinned to their vanilla values. Another write's value there is a `CONFLICT`.
- **A loader reload** puts the file's list back (the row names the file's list again). The weapon then reads as
  `orphaned`, and a disable restores the rest.
- **Without the adapter's permanent blocks** the add layout cannot build its list block. The weapon then falls back to
  the swap layout, which is solo only.
- While converted, typed writes reached through the weapon's ProjectileWeapon are refused: its fire rate, projectile,
  ammunition and the rows they link to.

## Multiplayer

`research/docs/beam-conversion-add-layout-F5FEE03DCFDB.md` (the add layout),
`research/docs/beam-conversion-mp-F5FEE03DCFDB.md` and `research/docs/beam-conversion-mp-sync-F5FEE03DCFDB.md` (the
swap layout) have the details.

| Layout | With other players | Why |
|---|---|---|
| Swap | **never** (`NOT_SOLO`) | A remote weapon of a swap-converted type is built without ProjectileWeapon. Its network apply then writes through index -1, and the converted game crashes when it spawns. Identical conversions do not help: the apply is chosen by the network type alone. |
| Add | **only when every other player is a Runtime holding the identical conversion** (`NOT_AGREED` otherwise) | No crash in any combination. But every machine draws every player's beam from the replicated trigger, and the machine that owns a target lowers its zone health and shields from the beams **it** draws. Health itself is applied once, by the shooter's machine. So every machine must convert the weapon the same way. A player without the Runtime would see bullets where you see beams. |

- **An add-layout apply in a lobby** needs every other member's posted set to hold this weapon's identical conversion
  (`ALL_AGREE`). The same holds for a change of its rate, pulse, damage or range.
  - The first player converts solo; a joiner then converts in the lobby.
  - A weapon nobody holds yet waits.
- **A restore** is always allowed (it makes this machine agree with the others).

### The conversion sync (`hd2bc`)

Each Runtime shares its conversions with the lobby, as the synced asset loader shares its packages: one lobby member
property, the key `hd2bc` in the `hd2bc/2` grammar. It uses the same channel and rate limits as `hd2rt` and `hd2as`.

- **Posted** once this machine has applied a conversion in this session:
  - per converted root: the resource, the layout (`a` add, `w` swap), the path (owned table or shared record), a
    digest of its BeamWeapon record (rate, beams, pulse) and one of its own beam and damage rows (range, damage, AP);
  - both digests leave out the locally borrowed slot ids. Two machines that converted a weapon the same way post the
    same entry, whichever spare slots they borrowed;
  - the Runtime version, the game build and the catalogue hash, and one digest of the whole set.
  - After the last restore the empty set is posted, so the lobby never keeps a stale set. At most 11 converted roots
    fit in the 512-byte value.
- **Read** from every other member every 3 s in a lobby of 2 or more. Each member is one of:

  | State | Meaning |
  |---|---|
  | `match` | same version, build, catalogue and digest |
  | `mismatch` | another set of conversions |
  | `incompatible` | another Runtime version, build or catalogue |
  | `malformed` | a value that is not exactly `hd2bc/2` (an older Runtime's `hd2bc/1` included) |
  | `pending` | no value yet, within 30 s of first seeing the member |
  | `no runtime` | no value after 30 s: no Runtime, an older one, or one that has converted nothing |

- **Decisions:**
  - an add apply: `ALL_AGREE`, else `NO_RUNTIME`, `MALFORMED`, `INCOMPATIBLE`, `PENDING` or `MISMATCH`;
  - a swap apply: `NOT_SOLO`;
  - the overall line (`ALL_MATCH`, or the first problem) is logged and shown in a refusal.
- **Log lines** start with `BEAM CONVERSION SYNC:`: the posted set, every member's state change, and the decision while
  this machine has a conversion.

### What the Runtime does when another player is present

| Case | What happens |
|---|---|
| Swap conversions, not in use | Restored at once on the first sight of the other player (the lobby is read every second), long before their weapons spawn. |
| Swap conversion in hand | It cannot be restored (its list cannot change under a live instance). A loud warning and the safety notice appear, and the restore is retried every 5 s. A joiner who carries that type crashes this game. |
| Add conversions, every member holds them identically | Kept. Both players may carry the weapon. |
| Add conversions, a member still pending (30 s), or a Runtime member whose set changed less than 30 s ago | Kept: it may still convert them. |
| Add conversions, a member settled without them (no Runtime, another set, another version) | Restored when not in use. One in use stays: no crash, but the two machines disagree about that weapon until it is put away. |
| Another member's set lists swap conversions | Your Runtime warns you: spawning one of those types crashes that member's game. |
| Blocking the join or the mission start | Not possible: the Runtime has no input blocking and no menu-state hook. |

- The mods' ensures stay registered. Their apply waits (`NOT_SOLO` / `NOT_AGREED`) and converts again once the lobby
  allows it.
- **Still unsafe:** a swap-converted weapon in hand when a player joins, a joiner without the Runtime who carries a
  swap-converted type, and joining a lobby with a swap-converted weapon equipped.
- `proof/BeamConversionSyncProof` has the two-machine test plan, both players carrying the same converted weapon
  included.

## Editor

`sdk/BeamConversionCapabilities.json`:

- `weapons[]`: `name`, `target` (the Lua expression), `layout` (`add`, `swap` or none), `multiplayer`, `verdict`,
  `reasonCode`, `reason`, `caveats` (the layout's), `add` and `swap` (each layout's verdict), `liveProven`,
  `liveProvenLayout`, `roots`, `restartAfterUse`, `chamberFix`, `heatPerPulse`;
- `fields[]`: `id`, `displayName`, `default`, `min`, `max`, `unit`, `note`, `rangeReason`, `row`, `perWeapon`;
- `acknowledgements`, `lifecycle`, `multiplayer`, `pulse`, `perWeaponRows`.

A tool should show:

- the verdict and the caveats;
- the enable toggle;
- rate, beams and pulse, with the pulse/rate note;
- the damage, AP and range fields under a "per-weapon rows (interim, max 6)" heading;
- the layout, with its multiplayer rule (add: identical conversions only; swap: solo only), and "unequip first".
