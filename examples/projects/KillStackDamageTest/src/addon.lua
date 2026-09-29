local hd2=require('mods/skyeshade/hd2runtime')
-- Kill-stacking damage (docs/events.md). Every enemy kill credited to the local player adds +10% AR-23 Liberator
-- damage, up to +100%, reset when a mission starts or ends.
--
-- Honest limits (docs/events.md#damage):
-- * No pre-damage event exists (Runtime patches no game code), so the bonus is a guarded change of the Liberator's
--   damage definition, bound to a script value: every Liberator in this game (and the StA-52 and Liberator Carbine,
--   which share the row) deals the boosted damage, not only yours, and each change re-applies after about half a
--   second.
-- * The weapon that made a kill is not identified by the game data Runtime can read, so kills with any weapon count.
assert(hd2.events and hd2.mod,'KillStackDamageTest needs an HD2Runtime build with the event system (hd2.events)')
local mod=hd2.mod('mods/hd2runtime_examples/kill_stack_damage_test')
local BASE,STEP,CAP=90,9,10          -- vanilla standard damage 90; +10% = +9 per kill; at most +100%
local damage=mod:value({id='liberator_damage',min=BASE,max=BASE+STEP*CAP,step=STEP,default=BASE})

local function stacks(count,why)
    mod.mission.stacks=count
    if damage:set(BASE+STEP*count)or count==0 then
        mod:log(('%s: %d stack(s), Liberator damage %d (+%d%%)'):format(why,count,BASE+STEP*count,count*10))
    end
end
mod:on('mission_started',function()stacks(0,'mission started')end,{id='reset_on_start'})
mod:on('mission_ended',function()damage:set(BASE);mod:log('mission ended: Liberator damage back to '..BASE)end,
    {id='reset_on_end'})
mod:on('entity_killed',function(event)
    if not(event.local_killer and event.enemy)then return end
    local count=math.min(CAP,(mod.mission.stacks or 0)+1)
    if count==mod.mission.stacks then return end
    stacks(count,'killed '..tostring(event.name or event.type))
end,{id='stack_on_kill'})

-- The guarded definition write, re-applied whenever the script value changes.
return hd2.ensure({patch={id='kill-stack-liberator-damage',target=hd2.weapon('AR-23 Liberator'):attack('primary'):projectile(),
    allow_shared=true,field=hd2.fields.damage.player_standard_damage,expect=BASE,value=damage}})
