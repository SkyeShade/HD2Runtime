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
| Injure a limb of the local player | `hd2.actions.injure(player, limb, damage)`, `player:injure(limb, damage)` | Local player only (no host needed), alive and not downed, in a mission; the game's own damage request at the limb (the VG-70 Variable's self-damage path). Not live-tested. |
| Heal a limb of the local player | `hd2.actions.heal_limb(player, limb)`, `hd2.actions.heal_limbs(player)` | Local player only, alive and not downed, in a mission; the game's own zone restore: the limb back to full (no partial limb heal exists). Not live-tested. |
| Push the local player | `hd2.actions.add_velocity(player, {x, y, z})` | Local player only, alive and not downed, in a mission; the game's own movement velocity setter; at most 25 m/s per change. What ground movement does with it is not proven. Not live-tested. |
| Use the worn Supply Pack | `hd2.actions.resupply_from_pack(player)`, `player:resupply_from_pack()` | Local player only, alive and not downed, in a mission; the pack's own self-use ability through the game's own action start (one supply, the game's refill); refused when nothing takes ammunition. Not live-tested. See [player-equipment.md](player-equipment.md). |
| Change a definition | `mod:value(spec)` bound to `hd2.ensure` | Changes the shared definition (every user of it), re-applied about half a second later. |
| Explosion | `hd2.explosions.spawn(name, {position = ...})` | The Hellbombs and the catalogued weapon explosions; host only; in a mission; credited to the local player. |
| Projectile | `hd2.projectiles.spawn(weapon, {position = ..., direction = ...})` | Catalogued weapon projectiles; host only; in a mission; fired and credited by the local player. |
| Homing shots | `hd2.projectiles.homing(weapon, {target = 'enemy' or 'friendly', turn_rate = ...})` | The local player's own shots of a weapon (173 named in `hd2.projectiles.homing_list()`) turn toward an enemy or another player in flight; one guarded write of each shot's own velocity per update; solo unless `multiplayer = true` (experimental). Not live-tested. See [projectile-homing.md](projectile-homing.md). |
| Enemy spawn mix | `hd2.enemies.spawn_weight(enemy, multiplier, {allow_unverified_effect = true})` | Scales an enemy type's weight in the game's spawn rosters: 0 = never picked, k = k times as likely within the groups it shares; not how many spawn. The host's rosters decide; a weight never goes from 0 to positive during a mission. Not live-tested. See [enemy-spawns.md](enemy-spawns.md). |
| Status effect | `hd2.status.apply(entity, status, {buildup = ...})` | Statuses a player weapon applies; buildup, not strength; host only; in a mission. |
| Pelican | `hd2.pelican.spawn({position = ..., hover = ...})` | The game's transport Pelican, empty; hovers over the position, held per instance; host only; in a mission; at most 4. |
| Spawn an entity | none | Blocked: the generic spawn's parameters and network replication are not proven (Runtime does not guess them). Only the transport Pelican is spawned (`hd2.pelican`). |

Every action belongs to the calling mod, carries a cause (the event it reacted to), and is refused past four
mod-caused links. A refusal never raises: the returned handle has `status = 'refused'`, a `code` and a `reason`.

### Explosions

```lua
local action = hd2.explosions.spawn('R-36 Eruptor', {position = event.position})
if action.status == 'refused' then mod:log(action.code .. ': ' .. action.reason) end
```

- The explosion is the game's own: `hd2.explosions.spawn` calls the game's explosion request with the same arguments
  its own callers pass, for an explosion type proven against the game's settings table. `hd2.explosions.list()`
  names the 16 catalogued explosions:
  - three named explosions, `'Hellbomb'` (the NUX-223 Hellbomb detonation), `'B-100 Portable Hellbomb'` and
    `'Cyborg Production Unit'` (the Halt Cyborg Production objective's self-destruct);
  - the 13 weapon explosions, selected by a weapon name or `hd2.explosions.of(weapon)`.

  Raw ids, unknown names and weapons without a catalogued explosion are refused (`UNKNOWN_EXPLOSION`).
- Its assets are loaded first when they are not resident (through the game's own package system, the same way
  reference swaps load them). A weapon explosion needs the weapon's package; a Hellbomb needs its stratagem's
  package. The handle then reads `waiting_for_assets`, then `requested`. A package Runtime cannot identify is refused
  (`ASSET_UNKNOWN`). `hd2.explosions.prepare(name)` at mission start avoids the wait.
- Host only (`HOST_ONLY`): the host owns enemy health, so a client request would be local and overwritten. The
  damage and deaths it causes are host state the game synchronizes itself; what other players see, the results or
  the explosion effect, is not live-tested.
- It is credited to the local player (source and owner = your avatar, creditor = you): its kills count as yours and
  appear in `player_kill_credited` under your avatar type. It needs your avatar to exist (`NO_LOCAL_AVATAR`).
- Chain reactions are bounded: at most 6 explosion requests at once per mod, refilled at 1 per second
  (`RATE_LIMITED`). The game does not say which explosion killed an enemy, so deaths it causes carry no mod cause.
- `'Hellbomb'` is the real NUX-223 detonation (ExplosionType 242, 17 / 25 / 45 m, 10000 damage). Its type is a code
  literal in the Hellbomb's behavior, and Runtime re-proves it at startup. It is live-proven on host (a death
  detonated it at the saved position); the B-100 Portable Hellbomb and the weapon explosions are not live-tested. Type 242 is also used by some mission
  objectives: requesting it is safe, but editing its settings would change them too.
- `'Cyborg Production Unit'` is the production unit's self-destruct (ExplosionType 293, 50 / 100 / 100 m, 10000
  damage, demolition 60: the Hellbomb's, four times its radius). Its type is a code literal of the objective's ability
  (AbilityId 906, at tick 1800), re-proven at startup with the ability explosion wrapper that carries it to the
  request. Its effect and its sound ship only in Automaton objective packages: an effect package (the whole production
  unit, about 217 MB) and an audio package (about 81 MB). Both must be resident before it is requested (its list entry
  says `objective = true`); `hd2.explosions.prepare` loads them. It kills Helldivers within its radius too. Not
  live-tested.

### Projectiles

```lua
local me = hd2.local_player()
local p = me:position()
hd2.projectiles.spawn('R-36 Eruptor', {position = {x = p.x, y = p.y, z = p.z + 2.5}, direction = {x = 1, y = 0, z = 0}})
```

- The projectile is the game's own. `hd2.projectiles.spawn` calls the game's projectile function (`FireProjectile`),
  the one the game's own AI fire helper calls, with the same template: a plain projectile and no target.
- A projectile is named by the weapon that fires it (`hd2.projectiles.list()`, 67 catalogued projectiles). Raw ids
  are refused (`UNKNOWN_PROJECTILE`).
- `direction` may have any non-zero length; Runtime normalises it. Up is `+z`.
- The weapon's package is loaded first when needed (`waiting_for_assets`, then `requested`), because the game
  creates the projectile's effects at once. `hd2.projectiles.prepare(weapon)` at mission start avoids the wait.
- Host only, and only while the game's projectile system is active (a mission).
- Your avatar fires it and is credited with it. Each projectile also counts as a shot in your mission stats
  (`player_fired`), as the game counts it. Only the local player can be the firer (`FIRER_UNSUPPORTED`).
- No network send was found: other players may not see the projectile itself, only its results.
- Live-proven on host for the R-36 Eruptor only.
- At most 12 at once and 4 per second per mod (`RATE_LIMITED`).

### Pelicans

```lua
local mod = hd2.mod()
local p = hd2.local_player():position()
local pelican = hd2.pelican.spawn({position = {x = p.x + 25, y = p.y, z = p.z}, hover = 60, on_event = function(e)
    mod:log('pelican ' .. e.kind)
end})
```

- The Pelican is the game's own transport Pelican (the one a vehicle call-in sends), **empty**: no vehicle, nothing
  attached, associated with nothing. `hd2.pelican.spawn` calls the game's existing spawn request with the descriptor
  the game's beacon dispatcher builds for a vehicle's Pelican, minus the vehicle: a copy of the game's default spawn
  context (no cargo, no associated entity) whose only set member is the hover **anchor**, as a beacon sets it for a
  vehicle drop. Nothing is patched or hooked, and no other entity can be spawned this way.
- `position` is the anchor: the game keeps it in the Pelican's own drop-position record, and its flight hovers over it
  (at a height and free spot of its own). It does not follow anyone.
- `approach` (`{distance, height}`): where it is created, `distance` metres back from `position` along its heading
  (default 250, 0 to 1000) and `height` metres up (default 80, 0 to 500). It flies in from there. The handle's
  `spawn_point` says where that was.
- `hover` (0 to 120 s): the Runtime holds it that many seconds after its release, with one guarded write of that
  Pelican's own release time. Then it leaves and disappears as the game makes it (about 14 s). Without `hover` it leaves
  right after its release.
- `facing` (`{x, y}`): its heading when created. By default, from the local player toward `position`.
- `gun` (development): its chin gun's own configuration ([custom-stratagem-api.md](custom-stratagem-api.md), *Pelican
  gunship*), including `sound`, a firing sound of the catalogue `hd2.sounds` ([weapon-sounds.md](weapon-sounds.md)).
- The call is made by the Runtime in its next update, on the game thread. The handle's `status` follows the Pelican:
  `requested`, `arriving`, `hovering`, `released`, `held`, `departing`, `gone`; or `refused` / `unverified` with a
  `code` and `reason`. `on_event(event)` sees every step, run as your mod. `pelican:state()` reads it now, including
  the `anchor` its record holds.
- Refused (`code`) unless: the game build is the researched one (`UNSUPPORTED_BUILD`), the game is in a mission
  (`NOT_IN_MISSION`) and you are the host (`HOST_ONLY`), the world's default spawn context is the game's neutral one
  (`CONTEXT_UNEXPECTED`), the Pelican's entity is loaded (`PELICAN_UNAVAILABLE`), the position and the spawn point are
  finite world coordinates (`INVALID_POSITION`, `INVALID_APPROACH`), and fewer than 4 Runtime Pelicans are alive
  (`PELICAN_LIMIT`). At most 4 at once and one every 4 s per mod (`RATE_LIMITED`).
- After the call the Runtime checks the entity is a transport Pelican with no cargo, its flight, and the anchor in its
  drop-position record; otherwise the handle is `unverified` (the entity may exist; nothing more is written to it).
- Other players: the Pelican is created as the game creates its own; whether they see it, and the hold, is not
  live-tested yet.
- Live: the empty spawn, the 60 s hold and the departure are live-proven (PelicanSpawnProof 0.1.0, solo host). The
  anchor (where it hovers) is not live-tested yet (PelicanSpawnProof 0.2.0).

### Status effects

```lua
hd2.events.on('entity_damaged', function(event)
    if event.local_attacker and event.enemy then hd2.status.apply(event.entity, 'fire', {buildup = 100}) end
end)
```

- The status is the game's own. `hd2.status.apply` appends one request to the game's status request queue, the one
  the game's own stun callers use. The game then checks that the target can have that status, and applies it here or
  sends it to the machine that owns the target.
- Only statuses that a player weapon already applies through its damage are offered (`hd2.status.list()`): `fire`,
  `fire_panic`, `burning_heavy`, `stun_small`, `stun_medium`, `stun_large`, `gas`, `gas_2`, `gas_confusion`,
  `gas_confusion_2` and `flamer_slowed`. Everything else is refused (`UNKNOWN_STATUS`). The game does not bound the
  type, so an unchecked type could corrupt memory.
- The amount is **buildup** (default 100, as the game's own stun requests pass). Each request adds it, and the status
  starts when the target's buildup reaches its susceptibility threshold. Strength and duration are the status's own:
  `strength` is refused (`INVALID_OPTION`). Applying again refreshes the duration; it does not stack.
- Host only. At most 10 at once and 5 per second per mod, and 4 at once per target (the game keeps at most 32 status
  records per entity).
- The target must still exist (`TARGET_GONE`). Your avatar is the instigator.
- Not proven: that the status's visual effects are always loaded (the same statuses are applied by enemies and
  environments whatever the players carry, so they are expected to be). Live-proven on host for `fire` only.

### Limb injuries

```lua
-- player_fired is checked 10 times per second and can count several shots: 2 damage per shot, at most a full arm.
hd2.events.on('player_fired', function(event)
    local action = hd2.actions.injure(event.player, 'r_hand', math.min(35, 2 * event.shots))
    if not action:requested() then mod:log('injury refused: ' .. action.code .. ': ' .. action.reason) end
end)
```

- The injury is the game's own. `hd2.actions.injure` looks the limb's physics actor up on your avatar's unit through
  the engine's own lookup and appends one damage request at that actor to the game's damage queue, with the template
  of the game's own VG-70 Variable self-damage (its third fire mode hurts the shooter's right shoulder the same way).
  The game applies it later in the same frame like any hit on that limb: the limb's damage zone loses the damage, and
  main health loses the zone's share (roughly head x1.5, chest x1.0, arms and legs x0.85). A zone at 0 health is an injured
  limb, with the game's own effects (arm sway, leg limp, the injury HUD); a stim heals it as usual. Boosters, armour
  passives and mission modifiers apply as they do to any hit, so the zone can lose less than you asked.
- Limbs: `head`, `chest`, `l_hand`, `r_hand`, `l_knee`, `r_knee` (`hd2.actions.limbs()`); anything else is refused
  (`UNKNOWN_LIMB`). `damage` is a whole number from 1 to the limb zone's health: head 85, chest 60, hands 35, knees 45
  (`INVALID_AMOUNT`). One full-zone request injures a healthy limb.
- Injuries also cost main health and can down or kill the Helldiver, exactly like ordinary damage.
- The local player only (`NOT_LOCAL_PLAYER`): each machine injures the avatar it owns, which is how the game itself
  injures (the Warp Pack and the VG-70 run on the avatar's owner). No host needed. In a mission (`NOT_IN_MISSION`),
  alive and not downed (`AVATAR_DOWNED`), from a callback, timer or keybind (`NOT_GAME_THREAD`). At most 12 at once
  and 10 per second per mod (`RATE_LIMITED`).
- Refused when the game's damage request, the engine's actor lookup or the actor API the game's drain uses is not the
  exact function this Runtime was built against (`INJURY_UNAVAILABLE`), when the queue is full this frame
  (`QUEUE_FULL`) or when the avatar's unit has no such actor now (`LIMB_UNAVAILABLE`).
- The injury names your avatar as its dealer and owner (self-inflicted) and keeps its last-hit creditor, as the VG-70
  keeps it. The returned handle's `status` is `'requested'` once queued; `zone_health` and `injured_before` describe
  the limb just before the request. Not live-tested: what the injured limb looks like to other players, and how the
  game's statistics count a self-inflicted hit. See docs/research/player-injury-path-F5FEE03DCFDB.md.

### Limb heals

```lua
hd2.input.bind('my_mod.patch_up', {key = 'Alt+F6', on_press = function()
    local action = hd2.actions.heal_limbs(hd2.local_player())
    if not action:requested() then mod:log(action.code .. ': ' .. action.reason) end
end})
```

- The heal is the game's own one-zone restore (game.dll `RestoreZone`, 0x65B2D0): the limb's damage zone returns to
  its full health and an injured limb is healed, committed the way the game's own heal commits it. Main health is not
  touched (use `hd2.actions.heal` for that; note the game's heal also heals every limb by the same fraction).
- The game has no partial heal of one limb. `amount` is `'full'` (the default) or a whole number that covers what
  the limb is missing; anything smaller is refused (`PARTIAL_UNSUPPORTED`) rather than faked.
- `hd2.actions.heal_limbs(player)` restores all six limbs in one request.
- Same limbs as `injure`. The local player only (`NOT_LOCAL_PLAYER`), in a mission, alive and not downed, from a
  callback, timer or keybind. At most 6 at once and 2 per second per mod. Refused when the game's function changed
  (`LIMB_HEAL_UNAVAILABLE`). Not live-tested.

### Velocity

```lua
hd2.input.bind('my_mod.hop', {key = 'Alt+F5', on_press = function()
    hd2.actions.add_velocity(hd2.local_player(), {x = 0, y = 0, z = 8})   -- m/s, world space, +Z up
end})
```

- The change goes through the game's own movement velocity setter (game.dll `SetVelocity`, 0x4A7550): the avatar's
  current velocity plus the change. It is the velocity the jump pack pushes and the game's own avatar launch sets
  (5.8 m/s forward and 3.3 m/s up).
- At most 25 m/s per change and 50 m/s afterwards (`INVALID_VELOCITY`, `TOO_FAST`). At most 4 at once and 2 per second
  per mod. The local player only, in a mission, alive and not downed.
- Not proven: what the avatar's ground movement does with the new velocity on the next frame (the game's own launch
  also switches the avatar's movement state). An upward change that lifts the avatar is the case most likely to show;
  a sideways change on the ground may be cancelled at once. What other players see is not observed. Not live-tested.

### The weapon in hand

```lua
local weapon, why = hd2.local_player():equipped_weapon()
if weapon then mod:log(weapon.name .. ' in the ' .. weapon.slot .. ' slot') end

hd2.events.on('weapon_changed', function(event)
    mod:log(tostring(event.previous and event.previous.name) .. ' -> ' .. tostring(event.current and event.current.name))
end)
```

- `player:equipped_weapon()` returns what the local player's avatar holds now: `{name, type, entity_id, slot,
  slot_proven, selection, avatar_id}`, or nil and the reason (`nothing in hand`, no avatar, or another player).
  Everything is re-read on every call; nothing is cached.
- `name` is the catalogued weapon, throwable or stratagem item; it is nil for an uncatalogued held item (for example
  a stratagem ball).
- `slot` is `primary` or `secondary` (proven), or `support`, `held_item` or `unknown` (inferred, `slot_proven =
  false`).
- `weapon_equipped`, `weapon_unequipped` (with `reason`: `switched`, `emptied` or `avatar_changed`) and
  `weapon_changed` (`previous`, `current`) report every change, ten checks a second, for the local player only. The
  game's switch writes the selection and the item in hand in one call, so a check never sees half a switch.
- Live-proven: primary and secondary switches and the three events, and uncatalogued items reported without a name.
  Remote players are not read; the inferred slot labels stay `slot_proven = false`.

This is **not** kill attribution. A weapon in hand when a kill is credited did not necessarily make it (grenades,
stratagems and delayed explosions kill while another weapon is held). Use `player_kill_credited.sources` for that.

### Loadout, backpack and the Supply Pack

```lua
local me = hd2.local_player()
local pack = me:backpack()                         -- the worn backpack and its live deposit
local ammo = me:ammo()                             -- the weapon in hand: rounds and spare magazines
if pack and pack.supply_pack and ammo and ammo.feed == 'magazine' and ammo.spare_magazines <= 1 then
    hd2.actions.resupply_from_pack(me)             -- the pack's own self-use, as when its key is pressed
end
```

- `player:loadout()` (primary, secondary, support, backpack, held item, throwable and its count), `player:held_weapon()`,
  `player:backpack()` and `player:ammo([slot])` read the local player's inventory record through the game's own tables;
  items carry the catalog name mods already use (`hd2.weapon`, `hd2.support_weapon`, `hd2.throwable`, `hd2.backpack`).
- `hd2.actions.resupply_from_pack(player)` starts the Supply Pack's own self-use ability through the game's own action
  start; the game spends one supply and refills the wearer. Local player only, in a mission, from a callback, timer or
  keybind; refused (without any call) when there is no Supply Pack, no supply, the avatar is busy or nothing takes
  ammunition. One request per 2 s per mod. Not live-tested.
- Details, refusal codes and limits: [docs/player-equipment.md](player-equipment.md).

## 10. Source attribution: what can and cannot be known

| You want | Use | Precision |
| --- | --- | --- |
| Which entity died and who was credited | `entity_killed` (`killer`, `local_killer`) | Per death. The credited player only, not the weapon. |
| Which weapon, throwable or stratagem earned your kills | `player_kill_credited` (`sources`) | Per source, ten checks a second; the local player only. |
| Which weapon killed a particular enemy | none | Not available: the game records the weapon in a per-player counter, not on the death. |
| What the local player holds | `player:equipped_weapon()`, `weapon_changed` | Exact, ten checks a second. Not attribution: the weapon in hand did not necessarily make a kill. |

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
