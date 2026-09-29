local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for hd2.projectiles (docs/event-scripting.md#projectiles). F6 fires one R-36 Eruptor shell through the
-- game's own projectile function (game.dll FireProjectile, the same call the game's AI fire helper makes): from
-- 2.5 m above your avatar, flying horizontally along the world X axis. Your avatar fires and is credited with it
-- (each shot also counts in your mission stats). Host only, in a mission.
--
-- What to check: a shell leaves from above your head, flies away and explodes where it lands; the Eruptor's
-- sound and trail play (its package is loaded when the mission starts); the log names every step.
assert(hd2.projectiles and hd2.input,'ProjectileActionTest needs an HD2Runtime build with hd2.projectiles')
local mod=hd2.mod()
local WEAPON='R-36 Eruptor'

hd2.events.on('mission_started',function()
    local warm=hd2.projectiles.prepare(WEAPON)
    mod:log('mission started: '..WEAPON..' projectile assets '..warm.status
        ..(warm.reason and(' ('..warm.reason..')')or''))
end,{id='warm'})

hd2.input.bind('projectile_action_test.fire',{key='F6',on_press=function()
    local me=hd2.local_player()
    local here=me and me:position()
    if not here then mod:log('F6: no local avatar position (not spawned?)');return end
    local from={x=here.x,y=here.y,z=here.z+2.5}
    local shot=hd2.projectiles.spawn(WEAPON,{position=from,direction={x=1,y=0,z=0}})
    mod:log(('F6: %s projectile from (%.2f, %.2f, %.2f) along +X: %s%s'):format(WEAPON,from.x,from.y,from.z,
        shot.status,shot.code and(' '..shot.code..': '..shot.reason)or''))
end})

mod:log('loaded: press F6 in a mission (as host) to fire an R-36 Eruptor shell from above your head')
