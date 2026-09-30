local hd2=require('mods/skyeshade/hd2runtime')
-- Vampiric Throwing Knives (docs/events.md, "Damage and hit attribution"). When the local player's K-2 Throwing Knife
-- damages something, heal the local player. The attribution is the game's own: the dealt_damage mission stat, which
-- the game adds under the source that dealt the damage (the knife is its own source, a throwable). A throw that misses
-- records nothing; other weapons, stratagems and damage the game records without a source never heal; nothing here
-- depends on timing.
--
-- Log lines (what the live test reports):
--   knife damage <n> -> heal +<amount> requested | heal refused: <reason>
--   damage <n> by <source> -> no heal (not the knife)
--   damage <n> without a source -> no heal
-- No recursion is possible: a heal adds health; it never adds dealt_damage.
assert(hd2.events and hd2.actions,'VampiricThrowingKnivesTest needs an HD2Runtime build with player_damage_dealt')
local mod=hd2.mod()   -- the SDK wrapper runs this file as the mod's own resource id
local KNIFE='K-2 Throwing Knife'
local HEAL=25             -- fixed heal per knife hit
local PROPORTION=nil      -- set to 0.25 to heal 25% of the damage the game recorded instead of the fixed amount

hd2.events.on('player_damage_dealt',function(event)
    for _,source in ipairs(event.sources)do
        if source.name==KNIFE then
            -- One event per check (10 per second): two knife hits in the same tenth of a second heal once.
            local wanted=PROPORTION and math.floor(source.damage*PROPORTION+0.5)or HEAL
            local amount,why=hd2.actions.heal(wanted)
            if amount then
                mod:log(('knife damage %d -> heal +%d requested'):format(source.damage,amount))
            else
                mod:log(('knife damage %d -> heal refused: %s'):format(source.damage,tostring(why)))
            end
        else
            mod:log(('damage %d by %s -> no heal (not the knife)'):format(source.damage,tostring(source.name or source.type)))
        end
    end
    if event.unattributed>0 then mod:log(('damage %d without a source -> no heal'):format(event.unattributed))end
end,{id='vampiric_knives'})

-- Evidence only: the knife is a thrown entity, not a projectile-system projectile, so player_hit should never name it.
hd2.events.on('player_hit',function(event)
    for _,source in ipairs(event.sources)do
        mod:log(('projectile hits %d by %s'):format(source.hits,tostring(source.name or source.type)))
    end
end,{id='hit_log'})

hd2.events.on('player_healed',function(event)
    if not event.local_player then return end
    local cause=event.cause.source=='mod'and('mod '..event.cause.mod)or'native'
    mod:log(('player healed +%d -> %d / %s, cause %s'):format(event.amount,event.health,tostring(event.max_health),cause))
end,{id='heal_log'})

hd2.events.on('mission_started',function(event)
    mod:log('mission started (host '..tostring(event.host)..'); hit something with a K-2 Throwing Knife to heal '..HEAL)
end,{id='mission_log'})
mod:log('loaded')
