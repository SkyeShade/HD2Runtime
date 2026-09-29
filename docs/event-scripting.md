# Writing gameplay logic in Lua

HD2Runtime's event API lets a mod's own `src/addon.lua` react to what happens in a mission and act on it:
"when this enemy dies, wait a few seconds, then do something where it died". This guide covers everything a
hand-written mod needs. [events.md](events.md) is the reference for how each event is observed.

```lua
local hd2 = require('mods/skyeshade/hd2runtime')

-- When a heavy machine gun Devastator dies, request an Eruptor explosion where it died, 1 to 10 seconds later.
hd2.events.on('entity_died', function(event)
    if event.semantic_id ~= 'enemy/v1/automatons/soldier_mg' then return end
    local position = event.position                  -- a read-only snapshot: valid after the enemy is gone
    hd2.after(math.random(1, 10), function()
        hd2.explosions.spawn('R-36 Eruptor', {position = position})
    end, {scope = 'mission'})
end)
```

Nothing polls until a mod subscribes, starts a timer or binds a key. Every callback runs isolated: an error in one
never stops another.

## 1. Subscribing to events

```lua
local sub = hd2.events.on('entity_died', function(event) ... end)          -- every time
hd2.events.once('mission_started', function(event) ... end)                -- the next time only
hd2.events.on('entity_killed', callback, {id = 'heal_on_kill', priority = 10, scope = 'mission'})
sub:disable(); sub:enable(); sub:unsubscribe()
```

| Option | Meaning |
| --- | --- |
| `id` | Registering the same id again replaces the callback instead of adding a second one. |
| `priority` | Higher runs first (-1000..1000, default 0); ties run in subscription order. |
| `scope` | `'mission'`: removed automatically when the mission ends. |
| `max_failures` | Consecutive failures before the subscription is disabled (default 25, `0` = never). |

Event names autocomplete in the editor (the SDK stubs type every payload: `HD2EntityDiedEvent`,
`HD2PlayerDiedEvent`, `HD2PlayerKillCreditedEvent`, ...). `hd2.events.names()` lists them and
`hd2.events.status()` says which are available now and why. A mistake (an unknown event, a bad option) is logged
and returns a handle with `state = 'rejected'`; it never aborts your mod.

| Event | When |
| --- | --- |
| `mission_started` / `mission_ended` | A mission begins or ends (`host`, `mode`, `duration`). |
| `player_spawned` / `player_died` | A player's avatar appears or dies (`position`, `observed`). |
| `entity_spawned` / `entity_died` / `entity_killed` | Anything with health appears or dies; `entity_killed` when the game credits a player. |
| `entity_damaged` / `player_damaged` / `player_healed` | Health changes (summed per tick). |
| `player_fired` / `player_kill_credited` | The local player's shots or credited kills grew, per weapon source. |
| `key_down` / `key_up` | A mod keybind. |

## 2. How long an event payload lives

A payload is a **snapshot** taken when Runtime observed the event. You may keep it, or any value from it, for as
long as you like: in a timer, in `mod.mission`, in a table of your own. Nothing in it points into game memory.

- Plain values (numbers, strings, booleans) never change.
- `event.position` is a read-only `HD2Position`: `p.x`, `p.y`, `p.z`, `tostring(p)`, `p:distance(other)`,
  `p:copy()` (a plain table you can change) and `p:unpack()`. Writing `p.x = 0` raises, so one mod can never change
  the position another mod saved.
- The same payload table is passed to every subscriber of that event: read it, do not rewrite it.

Death events carry everything a delayed callback needs as plain fields:

| Field | Meaning |
| --- | --- |
| `semantic_id` | Stable identity: `'enemy/v1/automatons/soldier_mg'`, `'entity/v1/helldivers/avatar_helldiver'`. |
| `name`, `display_name` | Catalogued name; `display_name` is the wiki name only where the catalog proves it. |
| `faction`, `enemy`, `kind`, `avatar` | `enemy`: the game counts its death as a kill. |
| `entity_id`, `unit_id`, `network_id`, `type` | Engine identities (numbers and the type hash). |
| `position` | Where it died (read-only). |
| `observed`, `corpse_id` | `'dead_state'`, or `'corpse'` when the game had already replaced it by its corpse. |
| `killer`, `local_killer`, `killer_peer` | The player the game credits (its last-hit creditor). |
| `mission`, `time`, `frame`, `cause` | When, and what caused it (native gameplay or a mod action). |

`player_died` adds `avatar_id`, `avatar_semantic_id`, `peer` and `observed` (`'dead_state'` or `'avatar_removed'`).

### Identifying an enemy

Use the semantic id. It comes from Runtime's enemy catalog (the same ids `hd2.enemy` uses), is stable across
corpse replacement and builds, and never depends on the entity still existing.

```lua
-- Check ids when the mod loads: a typo returns nil here instead of silently never matching.
local TARGETS = {['enemy/v1/automatons/soldier_mg'] = true, ['enemy/v1/automatons/soldier_rpg'] = true}
for id in pairs(TARGETS) do assert(hd2.entities.describe(id), 'unknown enemy id ' .. id) end

hd2.events.on('entity_died', function(event)
    if TARGETS[event.semantic_id] then ... end           -- or: event.entity:is(TARGETS)
end)
```

`hd2.entities.list({faction = 'automatons', enemy = true})` lists the catalogued ids. Many native classes have no
proven wiki name (the catalog attaches one only for a one-to-one anatomy match), so `display_name` is often `nil`;
the semantic id always exists. An entity whose resource path is unknown gets `entity/v1/unresolved/<type hash>`,
also stable. To learn a class's id, log `event.semantic_id` when it dies.

## 3. Live handles versus snapshot fields

`event.entity` is an `HD2EntityHandle`; `event.killer` and `event.player` are `HD2PlayerHandle`s.

- A handle's **identity fields** (`id`, `semantic_id`, `name`, `faction`, `enemy`, ...) and `entity:is(...)` are
  snapshots too: they work after the entity is gone.
- Its **live queries** (`is_valid`, `is_alive`, `health`, `position`, ...) read the game now. Once the game destroys
  the entity (its generation advances), when its id is reused, or when the mission ends, they return `nil` / `false`
  and `describe().reason` says why. A handle never keeps an address, so a destroyed entity can never be read as if
  it were alive.
- `player:avatar()` always resolves the player's current avatar: after a reinforce it is the new one.

For delayed logic, keep the snapshot fields you need (`event.position`, `event.semantic_id`) rather than asking a
handle later.

## 4. Timers

```lua
local timer = hd2.after(2.5, function(timer) ... end)                 -- once, 2.5 s of game time later
hd2.after(math.random(1, 10), callback)                               -- random delays are ordinary Lua
local repeating = hd2.every(1, function() ... end, {scope = 'mission'})
timer:cancel(); print(repeating:remaining())
```

- Game time: the sum of update ticks. It pauses while the game does not update. Fractions work; `after(0, ...)`
  runs on the next tick; `every` needs at least 0.05 s.
- `scope = 'mission'` (default `'session'`): cancelled when the mission ends, so a delayed action requested in a
  mission can never fire aboard the ship. A mission-scoped timer that expired stays expired: it cannot be revived.
- Missed intervals (a long frame) are skipped, never replayed in a burst.
- `id` replaces an earlier timer with the same id.
- A timer started inside a callback keeps that callback's event as its origin, so actions it performs are
  attributed to it.

## 5. Your mod's context

Everything a mod registers belongs to it: subscriptions, timers, keybinds and actions. Logs, error reports and
action causes name it, and cleanup applies per mod. You do not pass your id: the SDK's addon wrapper runs your
`addon.lua` as your mod's resource id, and a registration made inside a callback, timer or keybind belongs to the
mod that callback belongs to.

```lua
local mod = hd2.mod()               -- this mod's context (the same object on every call)
mod:log('hello')                    -- [HD2Runtime] [mods/author/my_mod] hello
mod.mission.kills = 0               -- cleared when a mission starts and when it ends
mod.session.best = 0                -- kept for the game session
```

`hd2.mod()` with no id refuses to guess when nothing names the mod (for example code run from a console); pass
`hd2.mod('mods/author/my_mod')` there. `hd2.events.run_as(id, fn)` runs `fn` as that mod.

## 6. Keybinds

```lua
hd2.input.bind('my_mod.detonate', {key = 'F6', on_press = function(binding) ... end})
```

Only bound keys are polled, only while the game window has focus. A chord already bound elsewhere leaves the new
binding in state `conflict` (logged) instead of taking it over; `binding:rebind('F7')` fixes it. Chords match their
exact modifiers (`F6` does not fire while Ctrl is held).

## 7. Errors

Every callback (event, timer, keybind) runs through `xpcall`. A failure is logged with the mod, the event and the
error, never stops the other subscribers, and after `max_failures` consecutive failures disables that subscription
(one log line; `sub:enable()` re-arms it).

## 8. Mission cleanup

When a mission ends: `mission_ended` subscribers run first (they can still read `mod.mission`), then mission-scoped
subscriptions and timers end, every mod's `mission` table is cleared, and every handle from that mission becomes
invalid. `hd2.events.mission_id()` returns the current mission id; compare it with a saved `event.mission` to know
a callback still runs in the same mission.

## 9. Gameplay actions

`hd2.actions.status()` lists what event scripts can make the game do in this Runtime:

| Action | API | Limits |
| --- | --- | --- |
| Heal the local player | `hd2.actions.heal(amount)`, `player:heal(amount)` | Local player, alive and not downed; clamped to maximum health; the game's own heal. |
| Change a definition | `mod:value(spec)` bound to `hd2.ensure` | Changes the shared definition (every user of it), re-applied about half a second later. |
| Explosion | `hd2.explosions.spawn(weapon, {position = ...})` | Catalogued weapon explosions; host only; in a mission; credited to the local player. |
| Fire a projectile, apply a status effect, spawn an entity | none | Blocked: no proven native request (Runtime does not guess one). |

Every action belongs to the calling mod, carries a cause (the event it reacted to), and is refused past four
mod-caused links. A refusal never raises: the returned handle has `status = 'refused'`, a `code` and a `reason`.

### Explosions

```lua
local action = hd2.explosions.spawn('R-36 Eruptor', {position = event.position})
if action.status == 'refused' then mod:log(action.code .. ': ' .. action.reason) end
```

- The explosion is the game's own: `hd2.explosions.spawn` calls the game's explosion request with the same arguments
  its own callers pass, for an explosion type proven against the game's settings table. `hd2.explosions.list()`
  names the 13 catalogued weapon explosions; a weapon name or `hd2.explosions.of(weapon)` selects one. Raw ids,
  unknown weapons and explosions without a catalogued one (`B-100 Portable Hellbomb`) are refused
  (`UNKNOWN_EXPLOSION`).
- Its assets are loaded first when nobody carries that weapon (through the game's own package system, the same
  way reference swaps load them); the handle then reads `waiting_for_assets`, then `requested`. A package Runtime
  cannot identify is refused (`ASSET_UNKNOWN`). `hd2.explosions.prepare(weapon)` at mission start avoids the wait.
- Host only (`HOST_ONLY`): the host owns enemy health, so a client request would be local and overwritten. Other
  players see the results (health, deaths); whether they see the explosion effect itself is not proven.
- It is credited to the local player (source and owner = your avatar, creditor = you): its kills count as yours and
  appear in `player_kill_credited` under your avatar type. It needs your avatar to exist (`NO_LOCAL_AVATAR`).
- Chain reactions are bounded: at most 6 explosion requests at once per mod, refilled at 1 per second
  (`RATE_LIMITED`). The game does not say which explosion killed an enemy, so deaths it causes carry no mod cause.
- The Hellbomb is not available: its explosion identity is not proven.

## 10. Source attribution: what can and cannot be known

| You want | Use | Precision |
| --- | --- | --- |
| Which entity died and who was credited | `entity_killed` (`killer`, `local_killer`) | Per death. The credited player only, not the weapon. |
| Which weapon, throwable or stratagem earned your kills | `player_kill_credited` (`sources`) | Per source, ten checks a second; the local player only. |
| Which weapon killed a particular enemy | none | Not available: the game records the weapon in a per-player counter, not on the death. |

`player_kill_credited.sources` lists the growth of the game's own per-source kill counters since the previous check,
largest first: `{type, name, kills}`. Guns are keyed by their weapon, stratagems by their payload, throwables by the
throwable; `unattributed` is growth the game recorded without a source. A source the catalog cannot name uniquely (a
payload many stratagems share, such as the hellpod) has `name = nil`. Counting "Liberator kills" this way is exact
(every +1 is one kill credited to the Liberator); linking a +1 to one dead enemy is not possible.

## Complete examples

### Heal on kill

```lua
local hd2 = require('mods/skyeshade/hd2runtime')
local mod = hd2.mod()

-- Heal the local player by 25 for every enemy the game credits to them.
hd2.events.on('entity_killed', function(event)
    if not (event.local_killer and event.enemy) then return end
    local amount, why = hd2.actions.heal(25)
    mod:log(amount and ('healed +' .. amount) or ('heal refused: ' .. why))
end)
```

### Delayed action after an enemy death

```lua
local hd2 = require('mods/skyeshade/hd2runtime')
local mod = hd2.mod()
local TARGET = 'enemy/v1/automatons/soldier_mg'
assert(hd2.entities.describe(TARGET), 'unknown enemy id')

hd2.events.on('mission_started', function() hd2.explosions.prepare('R-36 Eruptor') end)

hd2.events.on('entity_died', function(event)
    if event.semantic_id ~= TARGET or not event.position then return end
    -- Keep the snapshot, not the entity: the enemy is destroyed long before the timer fires.
    local position = event.position
    hd2.after(math.random(1, 10), function()
        local action = hd2.explosions.spawn('R-36 Eruptor', {position = position})
        if action.status == 'refused' then mod:log('explosion refused: ' .. action.code) end
    end, {scope = 'mission'})
end)
```

### Keybind action

```lua
local hd2 = require('mods/skyeshade/hd2runtime')
local mod = hd2.mod()

-- F6 requests an explosion 10 m from the local player (along the world x axis). It damages you too if you are close.
hd2.input.bind('my_mod.boom', {key = 'F6', on_press = function()
    local player = hd2.local_player()
    local here = player and player:position()
    if not here then mod:log('no position'); return end
    local target = here:copy(); target.x = target.x + 10
    local action = hd2.explosions.spawn('CB-9 Exploding Crossbow', {position = target})
    mod:log('F6: ' .. action.status .. (action.code and (' ' .. action.code) or ''))
end})
```

### Mission-scoped counter

```lua
local hd2 = require('mods/skyeshade/hd2runtime')
local mod = hd2.mod()

hd2.events.on('entity_killed', function(event)
    if not event.local_killer then return end
    mod.mission.kills = (mod.mission.kills or 0) + 1          -- cleared at every mission start and end
    if mod.mission.kills % 25 == 0 then mod:log(mod.mission.kills .. ' kills this mission') end
end)
hd2.events.on('mission_ended', function()
    mod:log('mission over: ' .. (mod.mission.kills or 0) .. ' kills')   -- still readable here
end)
```

### Per-source kill credit

```lua
local hd2 = require('mods/skyeshade/hd2runtime')
local mod = hd2.mod()

-- Logs "player kill credited: +4 (total 37)" followed by one line per weapon, stratagem or throwable.
hd2.events.on('player_kill_credited', function(event)
    mod:log(('player kill credited: +%d (total %d)'):format(event.kills, event.total))
    for _, source in ipairs(event.sources) do
        mod:log(('  %s +%d'):format(source.name or ('unnamed ' .. source.type), source.kills))
    end
end)
```

The shipped example projects run these patterns end to end: `KillHealTest`, `KillStackDamageTest`,
`HeavyDevastatorDelayedExplosionTest`, `PlayerKillCreditedExample`, `DeathHellbombTest` and `EventIsolationTest`.

## Adding events later

Every event comes from a *source* (`runtime/event_sources.lua`) that polls proven game state and queues payloads;
the engine, subscriptions, timers, ownership and dispatch never know which events exist. A new event (weapon
equipped, projectile hit, stratagem called, objective changed, extraction started) is a catalog entry in
`schemas/events.json` plus a source or a new check in an existing one, once its native state is proven. A
pre-damage event needs a proven way to run before the game applies damage, which Runtime does not have
(Runtime patches no game code).
