local hd2=require('mods/skyeshade/hd2runtime')
-- Death Hellbomb (docs/event-scripting.md#gameplay-actions). When the local player dies, the death position is taken
-- from the event (a read-only snapshot, valid after the avatar is destroyed) and a Hellbomb detonation at that
-- position is requested through hd2.explosions.
--
-- 'Hellbomb' is the NUX-223 Hellbomb detonation, ExplosionType 242: a code literal in the Hellbomb entity's behavior
-- that Runtime re-proves in game.dll at startup (research/event-actions-F5FEE03DCFDB.json). Its effects come with the
-- Hellbomb stratagem's package, which Runtime loads when a mission starts (hd2.explosions.prepare) so the detonation
-- needs no wait. Host only: a client's request is refused with HOST_ONLY.
assert(hd2.events and hd2.explosions,'DeathHellbombTest needs an HD2Runtime build with hd2.explosions')
local mod=hd2.mod()   -- the SDK wrapper runs this file as the mod's own resource id
local HELLBOMB='Hellbomb'

local function where(p)
    return p and tostring(p)or'(unknown: the avatar was gone before it was read)'
end
hd2.events.on('mission_started',function()
    local warm=hd2.explosions.prepare(HELLBOMB)
    mod:log('mission started: Hellbomb explosion assets '..warm.status
        ..(warm.reason and(' ('..warm.reason..')')or''))
end,{id='warm'})
hd2.events.on('player_died',function(event)
    if not event.local_player then
        mod:log('player '..event.peer..' died at '..where(event.position)..' (not the local player: no action)')
        return
    end
    local position=event.position
    local state=hd2.game_state()
    mod:log('local player died at '..where(position)..' (observed '..tostring(event.observed)..'); host '
        ..tostring(state and state.host))
    if event.cause.source=='mod'then
        mod:log('this death was caused by '..event.cause.mod..'; not reacting (recursion guard)')
        return
    end
    if not position then
        mod:log('no death position: nothing requested')
        return
    end
    local action=hd2.explosions.spawn(HELLBOMB,{position=position})
    mod:log('Hellbomb detonation at '..where(position)..': '..action.status
        ..(action.code and(' '..action.code..': '..action.reason)or''))
    -- The snapshot stays valid after the avatar is destroyed: read it again later.
    hd2.after(3,function()mod:log('3 s later the death snapshot still reads '..where(position))end)
end,{id='death'})
hd2.events.on('player_spawned',function(event)
    if event.local_player then mod:log('local player spawned at '..where(event.position))end
end,{id='spawn'})
mod:log('loaded: die in a mission as host; a Hellbomb detonates where you died')
