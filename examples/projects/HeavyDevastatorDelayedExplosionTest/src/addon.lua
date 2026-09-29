local hd2=require('mods/skyeshade/hd2runtime')
-- Heavy Devastator delayed explosion (docs/event-scripting.md). Hand-written gameplay logic on the event API:
-- when a Heavy Devastator dies, remember where, wait a few seconds, then request an R-36 Eruptor explosion at the
-- saved position.
--
-- What it proves:
-- * enemy identity from the event snapshot (the semantic id), also when the game replaced the enemy by its corpse
--   before Runtime saw its dead state (event.observed == 'corpse');
-- * the death position survives the enemy's destruction: the delayed callback only uses values saved from the
--   event, never the dead entity;
-- * a timer that fires after the entity is gone, owned by this mod automatically;
-- * a gameplay action (hd2.explosions.spawn) from arbitrary Lua, or the exact reason it was refused.
--
-- Identity: the enemy catalog does not attach the name "Heavy Devastator" to any native class (no one-to-one anatomy
-- match), so this test targets the heavy machine gun Devastator classes by their semantic ids, the in-game Heavy
-- Devastator by its resource path (cha_soldier_mg). Every other automaton class that dies is logged once per mission
-- with its id, so a live kill confirms or corrects this mapping.
assert(hd2.explosions and hd2.entities,'HeavyDevastatorDelayedExplosionTest needs an HD2Runtime with hd2.explosions')
local mod=hd2.mod()   -- the SDK wrapper runs this file as the mod's own resource id

local DELAY=3               -- deterministic for the live test; a real mod can use math.random(1, 10)
local EXPLOSION='R-36 Eruptor'
local TARGETS={
    ['enemy/v1/automatons/soldier_mg']=true,
    ['enemy/v1/automatons/soldier_mg_ivory_legion']=true,
    ['enemy/v1/automatons/soldier_mg_assassinate']=true,
}
-- Catch typos at load time: an unknown id would silently never match.
for id in pairs(TARGETS)do assert(hd2.entities.describe(id),'unknown enemy id '..id)end

-- Warm the explosion's assets when a mission starts, so the first request needs no wait.
hd2.events.on('mission_started',function()
    mod.mission.seen={}
    local warm=hd2.explosions.prepare(EXPLOSION)
    mod:log('mission started: '..EXPLOSION..' explosion assets '..warm.status
        ..(warm.reason and(' ('..warm.reason..')')or''))
end,{id='warm'})

hd2.events.on('entity_died',function(event)
    if event.faction~='automatons'then return end
    if not TARGETS[event.semantic_id]then
        -- Every other automaton class, once per mission: the live test shows which id a Heavy Devastator has.
        local seen=mod.mission.seen or{}
        mod.mission.seen=seen
        if not seen[event.semantic_id]then
            seen[event.semantic_id]=true
            mod:log('automaton died: '..event.semantic_id..' ('..tostring(event.name)..'), not a target')
        end
        return
    end
    -- Keep only snapshot values: the entity itself is destroyed before the timer fires.
    local position=event.position
    local identity=event.semantic_id
    local entity=event.entity
    mod:log('Heavy Devastator died at '..tostring(position)..' ('..identity..', observed='..event.observed
        ..', corpse='..tostring(event.corpse_id)..')')
    if not position then
        mod:log('no death position (its unit was already gone): nothing scheduled')
        return
    end
    mod:log('scheduled explosion in '..DELAY..' s')
    hd2.after(DELAY,function()
        mod:log('timer fired at saved position '..tostring(position)..' (the entity is still valid: '
            ..tostring(entity:is_valid())..')')
        local action=hd2.explosions.spawn(EXPLOSION,{position=position})
        if action.status=='refused'then
            mod:log('explosion blocked: '..action.code..': '..action.reason)
        else
            mod:log('explosion '..action.status..': '..EXPLOSION..' at '..tostring(position))
        end
    end,{scope='mission'})   -- a mission that ends first cancels it: nothing explodes aboard the ship
end,{id='heavy_devastator'})

mod:log('loaded: kill a Heavy Devastator; an '..EXPLOSION..' explosion follows '..DELAY..' s later where it died')
