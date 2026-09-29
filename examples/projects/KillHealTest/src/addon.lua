local hd2=require('mods/skyeshade/hd2runtime')
-- Heal on kill (docs/event-scripting.md). When the local player kills an enemy, heal the local player by 25, never
-- above maximum health. Kills by other players, environmental deaths and non-enemy deaths never heal.
--
-- Every kill is logged with what the event observed, which is what the live test reports:
--   kill: <semantic id> (<name>) observed=<dead_state|corpse> corpse=<id|nil> killer=<local player|peer ...|nobody>
--        -> heal +25 requested | no heal (...) | heal refused: <reason>
-- observed=corpse means the game had already replaced the enemy by its corpse when Runtime polled; the killer is then
-- the creditor Runtime saw on its last poll before the death.
assert(hd2.events and hd2.actions,'KillHealTest needs an HD2Runtime build with the event system (hd2.events)')
local mod=hd2.mod()   -- the SDK wrapper runs this file as the mod's own resource id
local HEAL=25

local function killer_text(event)
    if event.local_killer then return'local player'end
    if event.killer_peer then return'peer '..event.killer_peer end
    return'nobody'
end

hd2.events.on('entity_killed',function(event)
    local head=('kill: %s (%s) observed=%s corpse=%s killer=%s'):format(event.semantic_id,tostring(event.name),
        tostring(event.observed),tostring(event.corpse_id),killer_text(event))
    -- The game credits every kill to a player (its last-hit creditor); only the local player's kills heal.
    if not event.local_killer then mod:log(head..' -> no heal (not credited to the local player)');return end
    -- The game's own rule for an enemy kill: the victim's KillScore is positive.
    if not event.enemy then mod:log(head..' -> no heal (not an enemy)');return end
    local amount,why=hd2.actions.heal(HEAL)
    if amount then
        mod:log(head..(' -> heal +%d requested'):format(amount))
    else
        mod:log(head..' -> heal refused: '..tostring(why))
    end
end,{id='heal_on_kill'})

-- Every observed heal of the local player, with its cause: this mod's heals carry {source='mod', mod=<this mod>}.
hd2.events.on('player_healed',function(event)
    if not event.local_player then return end
    local cause=event.cause.source=='mod'and('mod '..event.cause.mod..' ('..event.cause.action..')')or'native'
    mod:log(('player healed +%d -> %d / %s, cause %s'):format(event.amount,event.health,tostring(event.max_health),cause))
end,{id='heal_log'})

hd2.events.on('mission_started',function(event)
    mod:log('mission started (host '..tostring(event.host)..'); kill an enemy to heal '..HEAL)
end,{id='mission_log'})
mod:log('loaded')
