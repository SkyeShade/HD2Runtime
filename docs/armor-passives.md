# Armor passives (development)

`hd2.passives` lists the game's 32 armor passives, with what follows a swap. `hd2.armor_kits` and `hd2.armor_kit`
list the game's 411 kits by their game names. `hd2.player_passives()` reads the local player's two passive slots and
the modifiers the game reads from them. `hd2.player_passives.set` overrides them for the local player only: it can
swap the armor passive, add a second passive, or do both.

```lua
for _, p in ipairs(hd2.passives.list()) do
    hd2.mod():log(('%d %s: %d modifiers, follows a swap: %s'):format(p.id, p.name, #p.modifiers, p.follows_swap))
end
for _, k in ipairs(hd2.armor_kits({slot = 'armor', weight = 'heavy', passive = 'FORTIFIED'})) do
    hd2.mod():log(k.name .. ' (' .. k.id .. ')')
end
local ravager = hd2.armor_kit('FS-37 Ravager')     -- or an index (0-410) or an id ('0x1F9BFA78')

local mine = hd2.player_passives()          -- nil, code, reason when it cannot be read
hd2.mod():log(mine.armor_kit.id .. ' wears ' .. mine.armor_passive.name)
for _, m in ipairs(mine.effective) do
    hd2.mod():log(('%s %s %g (%s)'):format(m.key_name, m.type, m.value, m.source))
end

local h = hd2.player_passives.set({armor = 'SERVO-ASSISTED', second = 'SCOUT', allow_unverified_effect = true})
if h.status == 'refused' then hd2.mod():log(h.code .. ': ' .. h.reason) end
h:stop()                                    -- the kit's own passives again

-- A passive with an effect package: loaded first ('waiting_for_assets'), then written.
local ie = hd2.player_passives.set({armor = 'INTEGRATED EXPLOSIVES', allow_unverified_effect = true})
```

**Status: development. Solo only.** Live-proven (r54 and r55, `schemas/live_evidence.json` family
`player_armor_passive_swap`): the armor-slot swap alone to SCOUT, ENGINEERING KIT, SERVO-ASSISTED or MED-KIT (r55: more stims). Everything else
is not live-tested. The read APIs are read-only. The live test is `proof/PassiveSwapProbe` (0.2.0: more passives,
the Integrated Explosives package, an Extra Padding control).

## The read API

| Call | Returns |
| --- | --- |
| `hd2.passives.list()` | Every passive, by id: `{id, name, description, modifiers = {{key, key_name, type, value, text, reader, follows, observable, note, armor_slot_only}}, effect_package, package, package_info, armor_kits, follows_swap, note, stats}`. Offline: this is the research's table, byte-for-byte what the game holds in every retained snapshot. |
| `hd2.passives.find(name or id)` | One passive (the name in any case), or `nil, 'UNKNOWN_PASSIVE', reason`. |
| `hd2.armor_kits(filter)` | Every kit matching `{slot, weight, passive, name}` (all optional), by index. See "The kits". |
| `hd2.armor_kit(index or id or name, slot)` | One kit, or `nil, 'UNKNOWN_KIT', reason`. |
| `hd2.player_passives()` | The local player, read now: `{entity, record, armor_kit, helmet_kit, cape_kit, armor_passive, helmet_passive, derived, overridden, runtime, effective}`, or `nil, code, reason`. |

- **Worn kits.** Each is `{id, index, name, slot, weight, passive}`. `index`, `name`, `slot` and `weight` come from
  the kit table (see "The kits"); `name` is nil for the 33 kits the game's text does not name. `passive` is the kit's
  own passive as read now (kit +0x1C), the value the game derives the slot from.
- **Slots.** `armor_passive` and `helmet_passive` are `{id, name}`: the record's two slots as they are now.
- **`derived`** = `{armor, second}`: the kits' own passives.
- **`overridden`**: a slot differs from its kit's passive.
- **`runtime`**: the mod holding an override, if any.
- **`effective`**: the rows a flags = 3 reader finds, in the game's order. First the armor passive's rows, then the
  second passive's rows for keys the armor passive lacks. The first row per key wins. Each row is
  `{key, key_name, type, value, source = 'armor' | 'second', passive, name}`.

A modifier row is `{key, type, value}`:
- **`key`**: 8 hex digits, the key the game looks up.
- **`key_name`**: the research's semantic name, for example `throw_range`, `movement_noise`,
  `enemy_detection_range`, `grenade_capacity`. Keys with no known reader or text are named `unknown_<key>`.
- **`type`**: `Set`, `Add`, `Multiply` or `Time`. The reader's own code combines it with its default value (the
  generic helper uses Set: `v = x`; Add and Time: `v += x`; Multiply: `v *= x`).

In `list()` and `find()`, each row also has (research/passive-effects-F5FEE03DCFDB.json):
- **`reader`**: how the game reads the key.
  - `direct`: a code reader through EntityAttribute. Follows a swap.
  - `data-driven`: a reader whose key comes from game data (the melee damage zones, the Oxygenator's speed tiers).
    Follows a swap.
  - `description-only`: no code or data holds the key. The row is description text; the effect is a stat row the kit
    worn at spawn applies (reload, ammo capacity, sidearm draw and recoil). A swap never changes it.
  - `armor rating`: read through the armor kit's own passive. Follows the worn kit, never the slot.
  - `none found`: Adreno-Defibrillator's revive row (key 0); its mechanism was not located.
  - `no effect`: STANDARD ISSUE.
- **`follows`**: true, false, or nil (unknown or no effect). **`note`** says why when it does not follow.
- **`observable`**: what to look for in play after a swap.
- **`armor_slot_only`**: every reader of the key reads the armor slot only, so a second-slot copy never reaches it.

A passive also has `description` (the game's), `follows_swap` (`'full'`, `'partial'` or `'unknown'`), `note` (what
does not follow), `stats` (its spawn-time stat rows `{stat, name, add, mul, described_by}`) and `package_info` (see
"Effect packages").

## The kits

`hd2.armor_kits(filter)` and `hd2.armor_kit(value, slot)` return the game's 411 kits (135 armor, 158 helmet,
118 cape). They are read-only and offline: the research's table (`research/armor-names-F5FEE03DCFDB.json`,
`scripts/research_armor_names.py`), equal to the game's in all 7 retained snapshots. A kit is:

| Field | Content |
| --- | --- |
| `index` | Its index in the kit table (0-410). |
| `id` | The kit id, `0x` + 8 hex digits (kit +0x00). |
| `slot` | `'armor'`, `'helmet'` or `'cape'` (kit +0x28). |
| `weight` | Armor only: `'light'`, `'medium'` or `'heavy'`, the weight of its armor pieces. |
| `passive`, `passive_name` | Its passive (kit +0x1C). Every helmet and cape has 0, STANDARD ISSUE. |
| `set`, `dlc`, `rarity` | Its set and dlc ids, and `'common'` or `'heroic'`. |
| `name`, `description` | The game's own text in the current language (378 of 411 names; nil for the rest). |
| `same_name` | How many kits carry this name. An armor and its helmet usually share one; B-01 Tactical has 24 kits. |
| `wiki` | Where a community wiki page matched: `{source = 'wiki', name, match, class, armor_rating, speed, stamina_regen, passive, passive_agrees}`. These are **the wiki's values, not read from the game**. `match` is `'exact'`, `'contained'` or `'fuzzy'`. |

- **Filters.** `slot`, `weight`, `passive` (name or id) and `name` (the game name, any case). A bad filter raises.
- **One kit.** By index, by id (any case, `0x` optional) or by game name (any case). For a shared name, `slot`
  picks one; without it the armor comes first, then the lowest index.

```lua
local k = hd2.armor_kit('RS-100 Sanctioner')        -- the armor (index 198); ('RS-100 Sanctioner', 'helmet') = 199
print(k.weight, k.passive_name, k.wiki and k.wiki.armor_rating)   -- light  REDUCED SIGNATURE  50 (the wiki's)
```

## The write API

`hd2.player_passives.set({armor = <name or id>, second = <name or id | false>, allow_unverified_effect = true})` returns a handle
`{kind, owner, status, code, reason, armor, second, notes}` with `stop()` and `describe()`.

- **`allow_unverified_effect = true`** is required for every override except an armor-slot swap alone (no `second`)
  to a live-proven passive: SCOUT, ENGINEERING KIT, SERVO-ASSISTED, MED-KIT.
- **`notes`**: what the chosen passives do not carry over a swap (their `note`, also logged once), for example
  SIEGE-READY's reload and ammo capacity, or ADRENO-DEFIBRILLATOR's unlocated revive.

- **`armor`** replaces the armor passive (applied record +0x3C). nil keeps the kit's own.
- **`second`** puts a passive in the helmet slot (applied record +0x38). nil or false: none, which is the kit's
  value, since no vanilla helmet has a passive.
- **One mod at a time.** A mod's second `set()` replaces its first in place. Another mod is refused
  (`ALREADY_SET`) while one holds an override. `hd2.player_passives.status()` returns the held override, or nil.
- **What is written.** One guarded 4-byte write per slot, on the local player's own applied record only, in one
  transaction. Before the first write:
  - the research's 59 instruction pins are proven on the loaded game.dll;
  - the manager pointer chain is read;
  - the entity map entry names the local player's entity, and the record's descriptor carries it;
  - the record's armor kit is the kit row just read;
  - each slot holds exactly its derived value (kit +0x1C).

  The record, the map entry, the descriptor and the kit rows are the transaction's contexts: if any byte changes,
  nothing is written. The target must be private read-write memory, and every write is read back.
- **Kept in place.** The game's only writer of the slots (0x874520) sets them from the kit's +0x1C when a new kit's
  package is ready. So an override lasts until the player changes armor or helmet; the game then derives that slot
  again. The handle looks at the record every 0.25 s and writes again after such a change, and logs each
  re-application.
- **`stop()`** puts the kit's values back into the slots that still hold the override's values. A slot the game
  already derived again, or that something else wrote, is left alone.

| Status | Meaning |
| --- | --- |
| `active` | The values are in place and kept there. |
| `waiting` | No record or kit yet (`UNAVAILABLE`, `NO_PLAYER`, `NO_RECORD`, `NOT_READY`): written when they appear. |
| `waiting_for_assets` | A passive's effect package is loading through core/assets. Nothing is written until it is resident. A failed load turns the handle `refused` (`ASSET_UNAVAILABLE`). |
| `suspended` | A second player joined (`NOT_SOLO`), or a passive's effect package is not resident at a write (`PACKAGE_NOT_RESIDENT`). The kit's values are back. Resumes on its own. |
| `lost` | Something else wrote a slot (`UNEXPECTED_STATE`). The override never writes again. |
| `replaced` | The same mod called `set()` again. |
| `stopped` | `stop()` was called. |
| `refused` | See below. Nothing was written. |

**Refusals.** A refusal never raises:
- `INVALID_OPTION`: not a table, an unknown option, or neither `armor` nor `second` given.
- `ACKNOWLEDGEMENT_REQUIRED`: an override that is not live-proven, without `allow_unverified_effect = true`.
- `UNKNOWN_PASSIVE`: not a passive name, an unused id (4 and 22-30), or an id the game's table does not hold.
- `SAME_PASSIVE`: the second passive is the armor passive, or the armor kit's own passive.
- `ARMOR_SLOT_ONLY`: INTEGRATED EXPLOSIVES as the second passive. Its death explosion reads the armor slot only
  (0x822140, flags 1), so a helmet-slot copy would never explode.
- `ASSET_UNAVAILABLE`: a passive's effect package could not be loaded (the loader's pins, the reference map, the
  package budget, or a load that did not finish in 90 s). Nothing was written.
- `NOT_SOLO`: there are several players.
- `UNEXPECTED_STATE`: the identity chain failed, or a slot holds neither its kit's value nor this override's.
- `NOT_PRIVATE`: the target is not private read-write memory.
- `GUARD_REJECTED`: the transaction refused the write.
- `UNSUPPORTED_BUILD`: a pin does not match the loaded game.dll.

## What a second passive does, and what it does not

- **It adds; it does not stack.** EntityAttribute (0x11D9DF0) returns the first row with the key: the armor slot is
  searched first, then the helmet slot. For a key both passives carry, the armor's row wins. For example, Servo-Assisted
  armor with a second Desert Stormer keeps throw range x1.3, not 1.3 x 1.2. A merged passive that combines both values
  would need a Runtime-owned passive object, which is not built.
- **Readers that ignore the second slot.** These readers call with flags = 1 (armor slot only):
  - `flinch_prevention` (73734D67, Unflinching): 0x82B327, 0x82DBFD, 0x8355DF, 0xA8C53A.
  - `chest_bleed_prevention` (A68930C2, Democracy Protects and Ballistic Padding): one of its three sites, 0xC2259.
  - `death_explosion` (54A69284, Integrated Explosives: the armor explodes after death): 0x82253C.

  Three sites compute their flags at run time, so the second slot may or may not count there: one of the four enemy
  detection sites (0x64C9D9), one impact-resistance path (0x87A512) and one chest-bleed site (0x69A177).
- **The armor rating follows the armor kit, not the passive.** Armor rating (AFAE3B47, e.g. Extra Padding) is read
  through PassiveValue with the armor kit's own passive (0x878160, 0x12A15E0, 0x14E7430, 0x1915EB0), never through the
  slots.
- **Capacities may wait for the next resupply or spawn (UNPROVEN).** Grenade and stim capacity (`grenade_capacity`
  F6FA9626, `stim_capacity` 2875F44A) are read at 0x9A6990 / 0x9ADDC0 and 0x9ADF00 / 0x9B0570. Whether those run every
  frame or only when the inventory is filled is not proven.
- **Reload, ammo capacity and sidearm stats never follow.** CC530B21, 35F17BEC, B4F88129, 33C9C713, AD5289FE and
  22035F3C exist only in their own passive rows: they are description text. The effects are stat rows that 0x11DA190
  applies from the kits worn at spawn (stat component, SetStat 0xA076C0). GUNSLINGER's real sidearm reload is x1.6
  (its stat row), while its text row says 1.4.
- **Melee damage and the Oxygenator's speed do follow.** 2559B40D is the melee damage zones' key (0x7D01C0) and
  CD79A687 / F6D67313 are the jog and sprint tiers of the Helldiver's locomotion data (0x9C94C0): both are read through
  EntityAttribute.
- **Boosters are not in this store.** The record holds exactly the two passive ids.

## What follows a swap

From `research/passive-effects-F5FEE03DCFDB.json` (`hd2.passives.list()`: `follows_swap`, and per row `reader`,
`follows`). 21 passives follow fully, 10 partly, 1 is unknown. "NO" marks a row that follows the kit worn, never the
slot.

| Id | Passive | Follows a swap | Rows: key name (reader) | Package |
| --- | --- | --- | --- | --- |
| 0 | STANDARD ISSUE | full | none (no effect) |  |
| 1 | EXTRA PADDING | partial | armor_rating (armor rating, NO) |  |
| 2 | SCOUT | full | radar_scan_interval (direct), enemy_detection_range (direct) |  |
| 3 | FORTIFIED | full | crouch_prone_recoil (direct), explosive_resistance (direct) |  |
| 5 | ELECTRICAL CONDUIT | full | arc_resistance (direct), unknown_8933e7f4 (direct) |  |
| 6 | ENGINEERING KIT | full | crouch_prone_recoil (direct), grenade_capacity (direct) |  |
| 7 | MED-KIT | full | stim_capacity (direct), stim_duration (direct) |  |
| 8 | SERVO-ASSISTED | full | throw_range (direct), limb_health (direct) |  |
| 9 | DEMOCRACY PROTECTS | full | lethal_damage_survival (direct), chest_bleed_prevention (direct) |  |
| 10 | REINFORCED EPAULETTES | partial | primary_reload_speed (description-only, NO), limb_injury_avoidance (direct), melee_damage (data-driven) |  |
| 11 | INFLAMMABLE | full | fire_resistance (direct) |  |
| 12 | PEAK PHYSIQUE | full | melee_damage (data-driven), weapon_ergonomics (direct), unknown_0dff0e42 (direct) |  |
| 13 | ADVANCED FILTRATION | full | gas_resistance (direct) |  |
| 14 | UNFLINCHING | partial | flinch_prevention (direct), armor_rating (armor rating, NO), radar_scan_interval (direct), stat 11 x0.05 (stat row, NO) |  |
| 15 | ACCLIMATED | full | elemental_resistance (direct), unknown_8933e7f4 (direct) |  |
| 16 | SIEGE-READY | partial | primary_reload_speed (description-only, NO), ammo_capacity (description-only, NO) |  |
| 17 | INTEGRATED EXPLOSIVES | full | death_explosion (direct, armor slot only), grenade_capacity (direct) | passive/17 |
| 18 | GUNSLINGER | partial | sidearm_reload_speed (description-only, NO), sidearm_draw_speed (description-only, NO), sidearm_recoil (description-only, NO) |  |
| 19 | ADRENO-DEFIBRILLATOR | unknown | none (none found: the revive), stim_duration (direct), arc_resistance (direct), unknown_8933e7f4 (direct) | passive/19 |
| 20 | BALLISTIC PADDING | full | chest_damage_resistance (direct), explosive_resistance (direct), chest_bleed_prevention (direct) |  |
| 21 | DESERT STORMER | full | elemental_resistance (direct), unknown_8933e7f4 (direct), throw_range (direct) |  |
| 31 | FEET FIRST | full | movement_noise (direct), poi_identification_range (direct), leg_injury_immunity (direct) |  |
| 32 | REDUCED SIGNATURE | full | movement_noise (direct), enemy_detection_range (direct) |  |
| 33 | ROCK-SOLID | full | melee_damage (data-driven), unknown_0dff0e42 (direct), knock_prone_resistance (direct) |  |
| 34 | SUPPLEMENTAL ADRENALINE | partial | stamina_when_damaged (direct), armor_rating (armor rating, NO) |  |
| 35 | CONCUSSIVE PADDING, REINFORCED | partial | explosive_resistance (direct), armor_rating (armor rating, NO) |  |
| 36 | CONCUSSIVE PADDING, GRENADIER | full | explosive_resistance (direct), grenade_capacity (direct) |  |
| 37 | CONCUSSIVE PADDING, HAZMAT | partial | explosive_resistance (direct), gas_resistance (direct), sidearm_recoil (description-only, NO) |  |
| 38 | OXYGENATOR | full | movement_speed (data-driven: jog), unknown_f6d67313 (data-driven: sprint), slide_boost (direct) |  |
| 39 | KINETIC DISPLACEMENT MITIGATION | full | fire_resistance (direct), limb_injury_avoidance (direct), impact_resistance (direct) |  |
| 40 | BLUNT-FORCE MITIGATION | partial | knock_prone_resistance (direct), impact_resistance (direct), armor_rating (armor rating, NO) |  |
| 41 | TRUE GRIT | partial | support_reload_speed (description-only, NO), weapon_ergonomics (direct) |  |

"Follows" means the reader looks the key up in the slot when it runs. Capacities (grenades, stims) are read by
direct readers, but probably only when the inventory is filled (resupply, spawn): unproven.

## Effect packages

Passive +0x30 is a 32-bit key the game resolves to a package (0x12689C0: the
`generated_add_resource_dependencies` table, then the `hash_lookup` map). Only two passives have one:

| Passive | Catalogue key | Package | Contents |
| --- | --- | --- | --- |
| 17 INTEGRATED EXPLOSIVES | `passive/17` | 0xC76C97B3DFB67C5C | 4 materials, 3 particles, 1 texture, 1 sound bank: the death explosion |
| 19 ADRENO-DEFIBRILLATOR | `passive/19` | 0x1EEE5C22038560E5 | 1 sound bank (`content/audio/passive_armor_constitution`) |

- **Catalogue.** `scripts/generate_package_residency.py` adds both to `domains/package_residency.lua` from the
  research's replica of that resolver (checked against the passive table's key), never by hand. `core/assets`
  accepts them like every other catalogue package. The synced asset catalogue hash changes with them, so lobby
  peers need the same Runtime build (a different catalogue fails closed, as before).
- **Loaded before the write.** `set()` with such a passive in either slot opens a core/assets gate on its
  catalogue entry with `shared = true`. The handle is `waiting_for_assets` until the engine reports the package
  resident, then the slot is written. A failed gate refuses the handle (`ASSET_UNAVAILABLE`), and nothing is written.
  Every later write of the passive (after a kit change) checks again that the Runtime holds the package and that it
  is resident.
- **Why not the game's own load.** The game's 0x874D80 requests the package on the frame after a slot changes, never
  waits, and loads it on the local peer only. A death inside the load window would fire the explosion with nothing
  resident; what the engine does then is unproven. The game's own paired request and release stay as they are.
  core/assets keeps the Runtime's reference for the session, so the package stays resident after `stop()`.
- **Synced.** `shared = true` puts the package in the synced asset set: `runtime/asset_sync` publishes it to the
  lobby's compatible Runtimes, which load it too (`docs/asset-loading.md`). The override itself stays solo only.
- **Integrated Explosives needs the armor slot.** 0x822140 (avatar death) applies status effect 66 only when the ARMOR
  slot holds 54A69284 (flags 1). As the second passive it is refused (`ARMOR_SLOT_ONLY`).
- **Adreno-Defibrillator's revive is unknown.** Its revive row has key 0 (text only), and no code was found that reads
  it. It is allowed with `allow_unverified_effect`; its stim duration, arc resistance and 8933E7F4 rows follow a
  swap. Whether the revive does is what a live test must show.

## How it works

The research is `research/player-attributes-F5FEE03DCFDB.json`, `scripts/research_player_attributes.py` and
`research/docs/player-attributes-F5FEE03DCFDB.md`. Every pin is identical in all 7 retained snapshots.
`domains/player_passives.lua` is generated from it by `scripts/generate_player_passives.py`, together with the kit
table and the passive names and descriptions (`research/armor-names-F5FEE03DCFDB.json`,
`scripts/research_armor_names.py`) and what follows a swap and the effect packages
(`research/passive-effects-F5FEE03DCFDB.json`, `scripts/research_passive_effects.py`). The generator checks that the
three research files agree: the same build, passive names, ids and modifier key order, every kit's passive in the
table, and the research's own counts.

The store is the customization manager (`[game.dll+0x33264F8]`):

| Offset | Content |
| --- | --- |
| +0x00 | The 411 kit pointers. Kit +0x1C is its passive id. |
| +0x20 | The 32 passive objects every player shares. A passive is {id, name, icon, Modifier *, count, ..., +0x30 package}. A Modifier is 16 bytes: {key, type, f32 value, text id}. |
| +0x30 | The passive id -> object index table (42 ids). |
| +0x930 | The entity -> record map. |
| +0x96C | The applied records, 0x44 bytes each, at most 4: +0x04 helmet kit, +0x08 cape kit, +0x0C armor kit, +0x38 helmet passive, +0x3C armor passive. |

When EntityAttribute receives an avatar, it maps it to the persistent player entity first. The Runtime finds the local
player's record through the same map, from the player list's entity.

The retained snapshots hold one record: entity 5, record 0, RS-100 SANCTIONER armor (kit passive 32 = slot 32,
REDUCED SIGNATURE: movement noise x0.5, enemy detection range x0.6), the RS-100 Sanctioner helmet (slot 0) and the
FALLEN HERO'S VENGEANCE cape. The packaged validation reads exactly that, and writes nothing.

## Limits

- **Solo only.** With several players every peer builds its own applied record from the replicated kits, and which
  peer evaluates each effect is not proven. A running override is suspended and its values restored (`NOT_SOLO`).
  Host or client makes no difference solo. Multiplayer is untested.
- **Mostly not live-tested.** Live-proven: the armor-slot swap to SCOUT, ENGINEERING KIT and SERVO-ASSISTED (r54), and MED-KIT (r55: more stims).
  Everything else is unproven in game: the second slot, the other passives, the capacities' timing, the effect
  package load before the write, and Adreno-Defibrillator's revive. `proof/PassiveSwapProbe` 0.2.0 tests six more
  passives in the armor slot and the Extra Padding control.
- Only the local player's own record is ever written. The shared passive objects, the kits and other players' records
  are never written.
