local hd2=require('mods/skyeshade/hd2runtime')
-- Heal on kill (docs/events.md). When the local player kills an enemy, heal the local player by 25, never above maximum
-- health. Kills by other players, environmental deaths and non-enemy deaths never heal.
assert(hd2.events and hd2.mod,'KillHealTest needs an HD2Runtime build with the event system (hd2.events)')
local mod=hd2.mod('mods/hd2runtime_examples/kill_heal_test')
local HEAL=25

mod:on('entity_killed',function(event)
    -- The game credits every kill to a player (its last-hit creditor); only the local player's kills count.
    if not event.local_killer then return end
    -- The game's own rule for an enemy kill: the victim's KillScore is positive.
    if not event.enemy then
        mod:log('local kill of a non-enemy ('..tostring(event.name or event.type)..'): no heal')
        return
    end
    local player=hd2.local_player()
    if not player then mod:log('no local player found');return end
    local amount,why=player:heal(HEAL)
    if amount then
        mod:log(('killed %s: heal +%d requested (health was %s / %s)'):format(tostring(event.name or event.type),
            amount,tostring(player:health()),tostring(player:max_health())))
    else
        mod:log('killed '..tostring(event.name or event.type)..', heal refused: '..tostring(why))
    end
end,{id='heal_on_kill'})

-- Every observed heal of the local player, with its cause: this mod's heals carry {source='mod', mod=<this mod>}.
mod:on('player_healed',function(event)
    if not event.local_player then return end
    local cause=event.cause.source=='mod'and('mod '..event.cause.mod..' ('..event.cause.action..')')or'native'
    mod:log(('player healed +%d -> %d / %s, cause %s'):format(event.amount,event.health,tostring(event.max_health),cause))
end,{id='heal_log'})

mod:on('mission_started',function(event)
    mod:log('mission started (host '..tostring(event.host)..'); kill an enemy to heal '..HEAL)
end,{id='mission_log'})
mod:log('loaded')
