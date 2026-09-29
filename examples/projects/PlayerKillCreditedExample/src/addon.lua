local hd2=require('mods/skyeshade/hd2runtime')
-- Per-source kill credit (docs/event-scripting.md#source-attribution).
--
-- The game keeps the local player's mission stats per source: every kill it credits to you is recorded under the
-- weapon, throwable or stratagem payload that made it. player_kill_credited reports how those counters grew since
-- the previous check (ten checks a second), for example:
--
--   player kill credited: +4 (total 37)
--     R-36 Eruptor +1
--     Eagle Strafing Run +3
--
-- This is a per-player counter, not per-death attribution: it cannot say which enemy each source killed. To know
-- which entity died and who was credited, subscribe to entity_killed.
assert(hd2.events,'PlayerKillCreditedExample needs an HD2Runtime build with the event system (hd2.events)')
local mod=hd2.mod()   -- the SDK wrapper runs this file as the mod's own resource id

hd2.events.on('player_kill_credited',function(event)
    mod:log(('player kill credited: +%d (total %d)'):format(event.kills,event.total))
    for _,source in ipairs(event.sources)do
        -- An unnamed source is a type the catalog cannot name uniquely (for example a payload many stratagems share).
        mod:log(('  %s +%d'):format(source.name or('unnamed source '..source.type),source.kills))
    end
    if event.unattributed>0 then
        mod:log(('  (recorded without a source) +%d'):format(event.unattributed))
    end
end,{id='credit_log'})

mod:log('loaded: kill enemies with different weapons and stratagems; each credit is logged per source')
