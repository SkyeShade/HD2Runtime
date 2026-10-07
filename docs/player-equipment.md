# What the Helldiver holds and wears, and the Supply Pack

Read what the local player carries, read the worn backpack's own values, and use a B-1 Supply Pack on its wearer the
way the game does. Research: [research/docs/player-equipment-F5FEE03DCFDB.md](research/player-equipment-F5FEE03DCFDB.md).
Example: `examples/projects/AutoSupplyPackTest` (an auto-consuming Supply Pack).

```lua
local me = hd2.local_player()
local loadout = me:loadout()
mod:log(loadout.primary.name .. ' / ' .. (loadout.backpack and loadout.backpack.name or 'no backpack'))

local pack = me:backpack()
if pack and pack.supply_pack then mod:log('supplies ' .. pack.deposit.amount .. '/' .. pack.deposit.capacity) end

local ammo = me:ammo()                      -- the weapon in hand
if ammo and ammo.feed == 'magazine' and ammo.spare_magazines <= 1 then
    local action = hd2.actions.resupply_from_pack(me)
    if not action:requested() then mod:log(action.code .. ': ' .. action.reason) end
end
```

## Reads

All reads are the **local player's** only (`NOT_LOCAL_PLAYER` otherwise: no retained snapshot proves another
player's records). Every call re-reads the game; nothing is cached. On failure a read returns nil and
`'CODE: reason'` (`NO_AVATAR`, `NO_INVENTORY`, `NO_BACKPACK`, `NOTHING_IN_HAND`, `EQUIPMENT_UNAVAILABLE` when a pinned
structure changed).

An **item** is `{name, kind, api, type, entity_id}`: `kind` is `primary`, `secondary`, `support`, `throwable` or
`backpack`; `name` is the catalog name of `api` (`hd2.weapon`, `hd2.support_weapon`, `hd2.throwable`, `hd2.backpack`),
so `hd2.backpack(item.name)` targets the same backpack. Support-weapon backpacks (the Autocannon's, the Recoilless's,
...) are named `'<weapon> backpack'` with no `api`. An uncatalogued item keeps `name` nil. Items are identified by
their entity type, never by a display name.

| Call | Returns |
| --- | --- |
| `player:loadout()` | `{avatar_id, selection, primary, secondary, support, backpack, held, throwable}`: items (nil when the slot is empty); `backpack` adds `deposit` and `supply_pack`; `throwable` is `{name, type, api, count}` |
| `player:held_weapon()` | the item in hand plus `slot` (`primary`, `secondary`, `support`: the inventory slot holding that same entity, `slot_proven = true`; else `held_item` or `unknown`), `selection`, `avatar_id` |
| `player:backpack()` | the worn backpack: item plus `supply_pack` (true for the B-1 Supply Pack) and `deposit` (below), or nil and `NO_BACKPACK` |
| `player:ammo([slot])` | `{slot, name, type, entity_id, feed, rounds, spare_magazines, capacity, max_spare_magazines}` for `primary`, `secondary`, `support` (default: the weapon in hand) |
| `player:weapon_state()` | what the weapon in hand fires with **now** (below) |

`deposit` (Supply Pack supplies, Guard Dog drone ammunition, the weapon-fed backpacks' ammunition):
`{amount, capacity, start_amount, refill_amount, self_ability, other_ability, definition, owned, drone_network_id}`.
`amount` is the live count the HUD shows; `capacity`, `start_amount`, `refill_amount` and the abilities come from the
definition the game uses for that very backpack (`definition = 'type'`, or `'instance'` for a per-instance one).

`ammo.feed`: `magazine` (rounds in the magazine and spare magazines, read from the weapon's own magazine instance;
`capacity` and `max_spare_magazines` are the catalog's base values) or `backpack` (a weapon fed from its worn backpack:
`rounds` is the backpack's live amount). Heat, rounds-fed and charge weapons return nil and `UNKNOWN_FEED`.

### The weapon in hand, live: `player:weapon_state()`

A template change (`weapon.fire_rate`, the spread, recoil and ergonomics fields) reaches a weapon only when it is
built again: a fresh call-in, a respawn. `player:weapon_state()` reads what the weapon in hand uses now, from its own
instance records, so a mod no longer scans memory to find them:

```lua
local w = hd2.local_player():weapon_state()
-- {name = 'R-36 Eruptor', slot = 'primary', fire_rate = 32, feed = 'magazine', magazine = {rounds = 3,
--  chambered = ..., capacity = 5}, spread = {horizontal = 5, vertical = 5}, recoil = {...}, projectile = 40,
--  own_record = false, rate_slots = {...}, wind_up = false, heat = false}
```

| field | read from |
| --- | --- |
| `fire_rate` | its current rounds-per-minute entry (the rate it fires at now, after any rate-of-fire selection) |
| `rate_slots` | its rate selector's three slots |
| `projectile`, `own_record` | its own ProjectileWeapon copy when it has one, else its type's record |
| `magazine` | its own magazine instance (rounds, the chambered round, the resolved capacity) |
| `spread` | its WeaponData instance's widths (mrad) |
| `recoil` | its WeaponData instance's aim recoil per shot |
| `feed`, `wind_up`, `heat` | which firing path it has |

- Read-only, the local player only, behind the same pins as the Pelican chin gun's live-proven weapon writes (these
  reads are what those writes check). Validated on the retained mission snapshots (the Eruptor above).
- Writing the weapon in hand is not offered. The per-instance writes exist (runtime/custom_weapons.lua) but are
  guarded to entities of a custom stratagem call, as the host; opening them to a vanilla weapon a player holds needs
  its own proof and live test first.

`player:equipped_weapon()` (docs/event-scripting.md) and the `weapon_changed` events stay as they were; there is no
backpack event: poll `player:backpack()` from a timer.

Not read: a shield pack's current charge and a jump pack's recharge (the research has leads, no snapshot wears them),
stim count.

## The Supply Pack: `hd2.actions.resupply_from_pack(player)`

Uses the worn B-1 Supply Pack on its wearer **exactly as when the player presses the pack's key**: the pack's own
self-use ability (from its own deposit definition, 2629) starts on the avatar through the game's own action start
(`try_start_action`). The game then plays its animation, spends one supply and refills the wearer, with its own
network replication. `player:resupply_from_pack()` is the same action.

- Local player only, in a mission, alive and not downed, from a callback, timer or keybind (`NOT_GAME_THREAD`). No host
  needed: each machine uses the pack its own avatar wears.
- Refused without calling anything when the game would refuse: `NO_BACKPACK`, `NOT_A_SUPPLY_PACK`, `NO_SUPPLIES`, `BUSY`
  (already in an action), `CANNOT_ACT` (the avatar may not act now). Runtime also asks the game's own query whether a
  weapon (or a non-Supply-Pack backpack) takes ammunition: `NO_AMMO_NEEDED` otherwise, so a supply is never spent on
  full weapons. This is stricter than the game, which also allows the use when only grenades or stims are missing.
- `NOT_STARTED` when the game did not start the ability; `RESUPPLY_UNAVAILABLE` when a pinned structure changed or
  this is not the live game. One request per 2 s per mod (`RATE_LIMITED`); the usual `CAUSE_DEPTH`, `INVALID_OPTION`,
  `INVALID_TARGET`, `NOT_IN_MISSION`, `NO_LOCAL_AVATAR`, `AVATAR_DOWNED`.
- A `requested` action carries `backpack` (entity id), `supplies` (before the use), `capacity` and `ability`. The
  supply is spent a moment later, on the animation; read `player:backpack().deposit.amount` to see it.
- Runtime writes nothing. There is no "set supplies" write: a direct write would not reach other players (the game
  sends supply changes through its own network field); see the research.
- Not live-tested yet (`examples/projects/AutoSupplyPackTest` is the test).

The "auto" part of an auto-consuming pack belongs in a mod: watch `player:ammo()` and call the action when it is low.
