local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for enemy spawn weights (hd2.enemies.spawn_weight; docs/enemy-spawns.md). Each option scales one or more
-- enemy types' weights in the game's spawn rosters: the type is picked more or less often within the spawn groups it
-- shares, or (x 0) never. It changes which enemies spawn, not how many. Not yet shown in game.
--
-- Set the options aboard the ship (APPLY), then deploy: the whole mission uses them. A type turned back on (from x 0)
-- returns only once you are aboard the ship again (the mission loaded without its packages). Host the mission: the
-- host's rosters decide what spawns.
local BANNER='ENEMY SPAWN MIX 0.1.0 BUILD'
local mod=hd2.mod()
local options=hd2.options({id='enemy_spawn_mix_test',title='Enemy Spawn Mix Test'})
local MIXES={
    {id='no_titans',label='No Bile Titans',default=true,enemies={'Bile Titan'},multiplier=0,
        description='Terminids: Bile Titans never spawn (x 0).'},
    {id='guard_swarm',label='Hive Guard swarm',default=true,enemies={'Hive Guard'},multiplier=5,
        description='Terminids: Hive Guards x 5 in the warrior groups (more Hive Guards, fewer warriors).'},
    {id='no_hunters',label='No Hunters',default=false,enemies={'hunter_tier_1','hunter_tier_2'},multiplier=0,
        description='Terminids: Hunters never spawn (both tiers x 0).'},
    {id='berserkers',label='Berserker rush',default=true,enemies={'berserker'},multiplier=5,
        description='Automatons: Berserkers x 5 in the groups they share with tanks and Hulks.'},
    {id='no_tanks',label='No tanks',default=false,
        enemies={'tank_heavycannon','tank_autocannons','tank_rocketlauncher'},multiplier=0,
        description='Automatons: tanks never spawn (all three x 0).'},
    {id='no_watchers',label='No Watchers',default=true,enemies={'Watcher'},multiplier=0,
        description='Illuminate: Watchers never spawn (x 0), so none calls reinforcements.'},
}
for _,mix in ipairs(MIXES)do
    mix.toggle=options:toggle({id=mix.id,label=mix.label,default=mix.default,description=mix.description})
end
mod:log(BANNER..': no Bile Titans, a Hive Guard swarm, a Berserker rush and no Watchers by default (and, off by '
    ..'default, no Hunters and no tanks); MODS page "Enemy Spawn Mix Test"')

-- The options are re-read every second: a change applies (or restores) that mix.
local active={}
hd2.every(1,function()
    for _,mix in ipairs(MIXES)do
        local on=mix.toggle:get()==true
        if on and not active[mix.id]then
            local handles={}
            for _,enemy in ipairs(mix.enemies)do
                local handle=hd2.enemies.spawn_weight(enemy,mix.multiplier,{allow_unverified_effect=true})
                handles[#handles+1]=handle
                if handle.status=='refused'then
                    mod:log(mix.label..': '..enemy..' refused: '..tostring(handle.code)..': '..tostring(handle.reason))
                end
            end
            active[mix.id]=handles
        elseif not on and active[mix.id]then
            for _,handle in ipairs(active[mix.id])do handle:stop()end
            active[mix.id]=nil
        end
    end
end)
