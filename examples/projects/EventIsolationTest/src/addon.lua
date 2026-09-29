local hd2=require('mods/skyeshade/hd2runtime')
-- Event isolation acceptance test (docs/events.md). One subscriber on each event fails on purpose; a second
-- subscriber on the same event must still run every time, and the failure must be logged with the mod id, the
-- event name and the error. Press F9 in game, then read HD2Runtime.log.
assert(hd2.events and hd2.mod,'EventIsolationTest needs an HD2Runtime build with the event system (hd2.events)')
local mod=hd2.mod()   -- the SDK wrapper runs this file as the mod's own resource id
local presses,ticks=0,0

-- key_down: the failing subscriber runs first (higher priority) and never gets disabled (max_failures=0), so every
-- press shows both the logged failure and the healthy subscriber's line.
mod:on('key_down',function(event)
    if event.binding=='event_isolation_test.trigger'then error('EventIsolationTest: intentional failure')end
end,{id='failing',priority=10,max_failures=0})
mod:on('key_down',function(event)
    if event.binding~='event_isolation_test.trigger'then return end
    presses=presses+1
    mod:log('second subscriber ran after the failing one (press '..presses..')')
end,{id='healthy'})
mod:bind('event_isolation_test.trigger',{key='F9',on_press=function()end})

-- The same pair on a repeating timer: the failing timer is disabled after 25 consecutive failures (logged once),
-- the healthy timer keeps running.
mod:every(2,function()error('EventIsolationTest: intentional timer failure')end,{id='failing_timer'})
mod:every(2,function()
    ticks=ticks+1
    if ticks<=3 or ticks%30==0 then mod:log('healthy timer ran ('..ticks..')')end
end,{id='healthy_timer'})
mod:log('loaded: press F9; each press must log one failure and one "second subscriber ran" line')
