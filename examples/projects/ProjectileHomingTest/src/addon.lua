local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for projectile homing (hd2.projectiles.homing; docs/projectile-homing.md). Each option makes the local
-- player's OWN shots of one weapon turn toward a target in flight: Runtime turns that shot's own velocity a little every
-- update and keeps its speed. The weapon, its projectile row and every other projectile are never written. Not yet
-- shown in game.
--
-- What to check, in a mission (solo first; the log shows one "home on" line per option that is on, then a "locked on"
-- line and a "first steering write" line for the first homing shot of each weapon):
--   * EAT-17: fired past an enemy (up to 30 degrees off), the rocket curves into it;
--   * R-36 Eruptor: the same with its shell (its shrapnel is the game's own and does not home);
--   * GL-21 Grenade Launcher: grenades arc toward enemies instead of only falling;
--   * (off by default) AR-23 Liberator: bullets bend toward enemies (bullets are fast: a high turn rate);
--   * (off by default) A/MG-43 Machine Gun Sentry: the sentry's rounds bend toward what it shoots at;
--   * (with friends; multiplayer on) P-11 Stim Pistol: a stim fired near a teammate curves into that teammate.
local BANNER='PROJECTILE HOMING 0.1.0 BUILD'
local mod=hd2.mod()
local options=hd2.options({id='projectile_homing_test',title='Projectile Homing Test'})
local WEAPONS={
    {id='eat',weapon='EAT-17 Expendable Anti-Tank',target='enemy',default=true,rate=1},
    {id='eruptor',weapon='R-36 Eruptor',target='enemy',default=true,rate=1},
    {id='grenade_launcher',weapon='GL-21 Grenade Launcher',target='enemy',default=true,rate=1},
    {id='liberator',weapon='AR-23 Liberator',target='enemy',default=false,rate=6},
    {id='sentry',weapon='A/MG-43 Machine Gun Sentry',target='enemy',default=false,rate=6},
    {id='stims',weapon='P-11 Stim Pistol',target='friendly',default=true,rate=2},
}
for _,item in ipairs(WEAPONS)do
    item.toggle=options:toggle({id=item.id,label=item.weapon:gsub('^[%w/%-]+ ',''),default=item.default,
        description=item.weapon..': its shots home on '..(item.target=='enemy'and'enemies'or'other players')..'.'})
end
local turn=options:slider({id='turn_rate',label='Turn rate (deg/s)',min=30,max=240,step=30,default=120,gap=true,
    description='How fast a rocket, shell or grenade may turn; bullets and sentry rounds turn 6 x faster, stims 2 x.'})
local cone=options:slider({id='cone',label='Cone (deg)',min=10,max=90,step=5,default=30,
    description='How far off its direction a target may be when the shot looks for one.'})
local multiplayer=options:toggle({id='multiplayer',label='Also with other players',default=false,
    description='Experimental: home with friends in the game too (other players see these shots fly straight).'})
mod:log(BANNER..': EAT-17, R-36 Eruptor and GL-21 shots home on enemies, P-11 stims on teammates (and, off by default, '
    ..'the AR-23 Liberator and the A/MG-43 sentry); MODS page "Projectile Homing Test"')

-- The options are re-read twice a second: a change restarts that weapon's homing with the new values (a refused
-- weapon is tried again only when its values change).
local current={}
local function wanted(item)
    if not item.toggle:get()then return nil end
    return {target=item.target,turn_rate=math.min(1440,turn:get()*item.rate),cone=cone:get(),range=150,
        multiplayer=multiplayer:get()==true}
end
local function same(a,b)
    if a==nil or b==nil then return a==b end
    for key,value in pairs(a)do if b[key]~=value then return false end end
    return true
end
hd2.every(0.5,function()
    for _,item in ipairs(WEAPONS)do
        local want=wanted(item)
        local now=current[item.id]
        if not same(want,now and now.options)then
            if now and now.handle then now.handle:stop()end
            current[item.id]={options=want}
            if want then
                local handle=hd2.projectiles.homing(item.weapon,want)
                current[item.id].handle=handle
                if handle.status~='active'then
                    mod:log(item.weapon..' homing refused: '..tostring(handle.code)..': '..tostring(handle.reason))
                end
            end
        end
    end
end)
