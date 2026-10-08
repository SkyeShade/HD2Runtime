# Armor passives (development)

`hd2.passives` lists the game's 32 armor passives. `hd2.player_passives()` reads the local player's two passive slots
and the modifiers the game reads from them. `hd2.player_passives.set` overrides them for the local player only: it
can swap the armor passive, add a second passive, or do both.

```lua
for _, p in ipairs(hd2.passives.list()) do
    hd2.mod():log(('%d %s: %d modifiers'):format(p.id, p.name, #p.modifiers))
end

local mine = hd2.player_passives()          -- nil, code, reason when it cannot be read
hd2.mod():log(mine.armor_kit.id .. ' wears ' .. mine.armor_passive.name)
for _, m in ipairs(mine.effective) do
    hd2.mod():log(('%s %s %g (%s)'):format(m.key_name, m.type, m.value, m.source))
end

local h = hd2.player_passives.set({armor = 'SERVO-ASSISTED', second = 'SCOUT'})
if h.status == 'refused' then hd2.mod():log(h.code .. ': ' .. h.reason) end
h:stop()                                    -- the kit's own passives again
```

**Status: development. Solo only. Not live-tested.** The read API is read-only. The live test is
`proof/PassiveSwapProbe`.

## The read API

| Call | Returns |
| --- | --- |
| `hd2.passives.list()` | Every passive, by id: `{id, name, modifiers = {{key, key_name, type, value, text}}, effect_package, package, armor_kits}`. Offline: this is the research's table, byte-for-byte what the game holds in every retained snapshot. |
| `hd2.passives.find(name or id)` | One passive (the name in any case), or `nil, 'UNKNOWN_PASSIVE', reason`. |
| `hd2.player_passives()` | The local player, read now: `{entity, record, armor_kit, helmet_kit, cape_kit, armor_passive, helmet_passive, derived, overridden, runtime, effective}`, or `nil, code, reason`. |

- **Kits.** Each kit is `{id, name, passive}`. `name` is given only for the kits the research resolved. `passive` is
  the kit's own passive (kit +0x1C), the value the game derives the slot from.
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

## The write API

`hd2.player_passives.set({armor = <name or id>, second = <name or id | false>})` returns a handle
`{kind, owner, status, code, reason, armor, second}` with `stop()` and `describe()`.

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
| `suspended` | A second player joined (`NOT_SOLO`), or a passive's effect package is no longer held (`PACKAGE_NOT_RESIDENT`). The kit's values are back. Resumes on its own. |
| `lost` | Something else wrote a slot (`UNEXPECTED_STATE`). The override never writes again. |
| `replaced` | The same mod called `set()` again. |
| `stopped` | `stop()` was called. |
| `refused` | See below. Nothing was written. |

**Refusals.** A refusal never raises:
- `INVALID_OPTION`: not a table, an unknown option, or neither `armor` nor `second` given.
- `UNKNOWN_PASSIVE`: not a passive name, an unused id (4 and 22-30), or an id the game's table does not hold.
- `SAME_PASSIVE`: the second passive is the armor passive, or the armor kit's own passive.
- `PACKAGE_NOT_RESIDENT`: the passive has an effect package (17 INTEGRATED EXPLOSIVES, 19 ADRENO-DEFIBRILLATOR) and
  no player's record holds that passive now. The asset catalogue (core/assets) does not know the passives' 32-bit
  package field, so the Runtime cannot request the package. Such a passive is accepted only while some record already
  holds it, for example the armor kit's own Integrated Explosives moved to the second slot.
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
- **Keys with no direct reader found.** Reload speeds, ammo capacity, sidearm draw and recoil, melee damage and the
  Oxygenator's speed (CC530B21, 35F17BEC, B4F88129, 33C9C713, AD5289FE, 22035F3C, 2559B40D, CD79A687, F6D67313) are
  probably read through data-driven paths. Whether they follow an override is not known.
- **Boosters are not in this store.** The record holds exactly the two passive ids.

## How it works

The research is `research/player-attributes-F5FEE03DCFDB.json`, `scripts/research_player_attributes.py` and
`research/docs/player-attributes-F5FEE03DCFDB.md`. Every pin is identical in all 7 retained snapshots.
`domains/player_passives.lua` is generated from it by `scripts/generate_player_passives.py`.

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
- **Not live-tested.** Every effect in game is unproven: whether each reader follows the slot at once, and the
  capacities.
- Only the local player's own record is ever written. The shared passive objects, the kits and other players' records
  are never written.
