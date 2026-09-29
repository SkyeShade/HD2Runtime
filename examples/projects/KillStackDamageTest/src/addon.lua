local hd2=require('mods/skyeshade/hd2runtime')
-- Kill-stacking damage (docs/event-scripting.md). Every kill the game credits to the local player's AR-23 Liberator
-- adds +10% Liberator damage, up to +100%, reset when a mission starts or ends.
--
-- Liberator kills come from player_kill_credited: the game records each credited kill under the weapon that made it,
-- and this mod counts only the growth recorded under the AR-23 Liberator. That is exact per kill count (every +1 is
-- one Liberator kill) but not per death: it cannot tell which enemy died to the Liberator, which a stack count does
-- not need. Kills with every other weapon, stratagem or throwable add nothing.
--
-- Honest limits (docs/events.md#damage):
-- * No pre-damage event exists (Runtime patches no game code), so the bonus is a guarded change of the Liberator's
--   damage definition, bound to a script value: every Liberator in this game (and the StA-52 and Liberator Carbine,
--   which share the row) deals the boosted damage, not only yours, and each change re-applies after about half a
--   second.
-- * Stats are checked ten times a second, so a burst of kills can arrive as one event with several kills.
assert(hd2.events and hd2.mod,'KillStackDamageTest needs an HD2Runtime build with the event system (hd2.events)')
local mod=hd2.mod()   -- the SDK wrapper runs this file as the mod's own resource id
local BASE,STEP,CAP=90,9,10          -- vanilla standard damage 90; +10% = +9 per kill; at most +100%
local LIBERATOR='AR-23 Liberator'     -- the stat source name of the weapon whose kills stack
local damage=mod:value({id='liberator_damage',min=BASE,max=BASE+STEP*CAP,step=STEP,default=BASE})

local function stacks(count,why)
    mod.mission.stacks=count
    if damage:set(BASE+STEP*count)or count==0 then
        mod:log(('%s: %d stack(s), Liberator damage %d (+%d%%)'):format(why,count,BASE+STEP*count,count*10))
    end
end
hd2.events.on('mission_started',function()stacks(0,'mission started')end,{id='reset_on_start'})
hd2.events.on('mission_ended',function()damage:set(BASE);mod:log('mission ended: Liberator damage back to '..BASE)end,
    {id='reset_on_end'})
hd2.events.on('player_kill_credited',function(event)
    local gained=0
    for _,source in ipairs(event.sources)do
        if source.name==LIBERATOR then gained=gained+source.kills end
    end
    if gained==0 then return end
    local count=math.min(CAP,(mod.mission.stacks or 0)+gained)
    if count==mod.mission.stacks then return end
    stacks(count,('%d %s kill(s) credited'):format(gained,LIBERATOR))
end,{id='stack_on_liberator_kill'})

-- The guarded definition write, re-applied whenever the script value changes.
return hd2.ensure({patch={id='kill-stack-liberator-damage',target=hd2.weapon('AR-23 Liberator'):attack('primary'):projectile(),
    allow_shared=true,field=hd2.fields.damage.player_standard_damage,expect=BASE,value=damage}})
