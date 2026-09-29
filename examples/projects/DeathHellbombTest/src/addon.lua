local hd2=require('mods/skyeshade/hd2runtime')
-- Death Hellbomb (docs/events.md#explosions). When the local player dies, the death position is captured from the
-- event (a snapshot taken before the avatar can be destroyed) and a Hellbomb detonation at that position is requested.
--
-- The explosion step is BLOCKED in this Runtime build: the Hellbomb's own explosion identity and the arguments of the
-- game's explosion request are not proven, and Runtime neither guesses a native call nor fakes it by editing another
-- explosion's definition. This mod therefore proves everything up to the request and logs exactly why the detonation
-- is not performed.
assert(hd2.events and hd2.mod,'DeathHellbombTest needs an HD2Runtime build with the event system (hd2.events)')
local mod=hd2.mod('mods/hd2runtime_examples/death_hellbomb_test')

local function where(p)
    return p and('(%.2f, %.2f, %.2f)'):format(p.x,p.y,p.z)or'(unknown: the avatar was gone before it was read)'
end
mod:on('player_died',function(event)
    if not event.local_player then
        mod:log('player '..event.peer..' died at '..where(event.position)..' (not the local player: no action)')
        return
    end
    local position=event.position
    local state=hd2.game_state()
    mod:log('local player died at '..where(position)..'; host '..tostring(state and state.host))
    if event.cause.source=='mod'then
        mod:log('this death was caused by '..event.cause.mod..'; not reacting (recursion guard)')
        return
    end
    mod:log('Hellbomb detonation at '..where(position)..' not performed: explosion requests are blocked in this '
        ..'Runtime build (the Hellbomb explosion identity and the game request arguments are not proven)')
    -- The snapshot stays valid after the avatar is destroyed: read it again later.
    mod:after(3,function()mod:log('3 s later the death snapshot still reads '..where(position))end)
end,{id='death'})
mod:on('player_spawned',function(event)
    if event.local_player then mod:log('local player spawned at '..where(event.position))end
end,{id='spawn'})
mod:log('loaded')
