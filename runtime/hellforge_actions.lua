-- The actions on HellForge (runtime/hellforge.lua, docs/hellforge.md): each one the Runtime made by calling or writing
-- the game itself goes to HellForge's engine action of the same kind (its SDK 11: the same game functions, called on
-- the game thread). The public API, its checks, rate limits and answers stay the Runtime's; only the last step, the
-- call or the write, changes. What HellForge answers with a refusal comes back as HELLFORGE_REFUSED and its reason.
--   heal, heal_limb, injure, add_velocity, the status request, resupply_from_pack (the Supply Pack's self-use)
--   explosions and projectiles (HellForge loads their packages through its own package loader, as every request here)
--   homing and per-shot changes (HellForge's shot rules), the Pelican (its hover held by HellForge), kill credit, the
--   mission timer freeze
local hellforge=require('hd2runtime/runtime/hellforge')
local writes=require('hd2runtime/runtime/hellforge_writes')
local b=require('hd2runtime/core/bytes')
local log=require('hd2runtime/runtime/log')
local M={}

local function backend()return hellforge.backend()end
-- The HellForge mod the action is the mod's own (lua.<mod>), else the Runtime's.
local function actor()
    local ok,owner=pcall(function()return require('hd2runtime/runtime/events').owner()end)
    return hellforge.mod(ok and owner or nil)
end
local function refused(m)return 'HELLFORGE_REFUSED: '..(m and backend().last(m)or'HellForge has no room for another Lua mod')end
local function finite(v)return type(v)=='number'and v==v and v>-math.huge and v<math.huge end
local function resource(hex)return type(hex)=='string'and writes.resource(hex)or hex end

-- event_world's actions (runtime/event_world.lua): the reads stay, the call is HellForge's.
local function world_actions(world_module)
    local scheduler=require('hd2runtime/runtime/scheduler')
    local AVATAR='4D1C334D294DFA97'
    function world_module.heal(world,entity,amount)
        if not finite(amount)or amount<=0 or amount>100000 then return nil,'heal amount must be a positive number'end
        local state=world_module.entity_state(world,entity)
        if not state then return nil,'the entity has no health record'end
        if state.descriptor.type~=AVATAR then return nil,'only a Helldiver avatar can be healed'end
        if not state.descriptor.owned then return nil,'only the local player (the avatar this machine owns) can be healed'end
        if state.life~=0 then return nil,'the avatar is downed or dead'end
        local maximum=state.max_health
        if not maximum or maximum<=0 or maximum>100000 then return nil,'maximum health unreadable'end
        if state.health>=maximum then return 0 end
        local applied=math.min(amount,maximum-state.health)
        local m=actor()
        if not m or backend().heal(m,applied)==0 then return nil,refused(m)end
        return applied
    end
    local function limb_before(world,entity,limb)
        local now=backend().limb_state(actor(),entity,limb.zoneIndex)
        return now and now.health,now and now.injured
    end
    function world_module.injure(world,spec)
        if not scheduler.in_update()then
            return nil,'NOT_GAME_THREAD: an injury is requested only from the game update (a callback, timer or keybind)'
        end
        local limb=world_module.injury_limb(spec.limb)
        if not limb then return nil,'UNKNOWN_LIMB: '..tostring(spec.limb)..' is not a limb Runtime can injure'end
        local damage=spec.damage
        if type(damage)~='number'or damage~=damage or damage%1~=0 or damage<1 or damage>limb.maxDamage then
            return nil,'INVALID_AMOUNT: '..limb.name..' damage must be a whole number from 1 to '..limb.maxDamage
        end
        local before,injured=limb_before(world,spec.entity,limb)
        local m=actor()
        if not m or backend().injure(m,limb.zoneIndex,damage)==0 then return nil,refused(m)end
        return {limb=limb.name,zone=limb.zone,damage=damage,actor=0,zone_health=before,injured_before=injured}
    end
    function world_module.heal_limb(world,spec)
        if not scheduler.in_update()then
            return nil,'NOT_GAME_THREAD: a limb heal is requested only from the game update (a callback, timer or keybind)'
        end
        local limb=world_module.injury_limb(spec.limb)
        if not limb then return nil,'UNKNOWN_LIMB: '..tostring(spec.limb)..' is not a limb Runtime can heal'end
        local before,injured=limb_before(world,spec.entity,limb)
        local m=actor()
        if not m or backend().heal_limb(m,limb.zoneIndex)==0 then return nil,refused(m)end
        return {limb=limb.name,zone=limb.zone,zone_health=before,max=limb.maxDamage,injured_before=injured}
    end
    function world_module.limb_state(world,entity,name)
        local limb=world_module.injury_limb(name)
        local now=limb and backend().limb_state(actor(),entity,limb.zoneIndex)
        return now and{health=now.health,max=now.max,injured=now.injured}or nil
    end
    function world_module.add_velocity(world,spec)
        if not scheduler.in_update()then
            return nil,'NOT_GAME_THREAD: a velocity change is requested only from the game update (a callback, timer or keybind)'
        end
        for _,k in ipairs({'x','y','z'})do
            if not finite(spec[k])or math.abs(spec[k])>1000 then return nil,'INVALID_VELOCITY: the change must be finite'end
        end
        local motion=world_module.motion(world,spec.entity)
        local v=motion and motion.velocity or{x=0,y=0,z=0}
        local after={x=v.x+spec.x,y=v.y+spec.y,z=v.z+spec.z}
        local speed=math.sqrt(after.x^2+after.y^2+after.z^2)
        if spec.max_speed and not(speed<=spec.max_speed)then
            return nil,('TOO_FAST: the avatar would move at %.1f m/s (at most %g)'):format(speed,spec.max_speed)
        end
        local m=actor()
        if not m or backend().add_velocity(m,spec.x,spec.y,spec.z)==0 then return nil,refused(m)end
        return {before={x=v.x,y=v.y,z=v.z},after=after}
    end
    function world_module.status(world,spec)
        local buildup=spec.buildup
        if not finite(buildup)or buildup<=0 or buildup>1000 then return nil,'INVALID_AMOUNT: buildup must be above 0 and at most 1000'end
        local m=actor()
        if not m or backend().apply_status(m,spec.target,spec.type,buildup)==0 then return nil,refused(m)end
        return true
    end
    function world_module.explode(world,spec)
        for _,k in ipairs({'x','y','z'})do
            if not finite(spec[k])or math.abs(spec[k])>100000 then return nil,'the position must be finite world coordinates'end
        end
        local m=actor()
        local result=m and backend().spawn_explosion(m,spec.type,spec.x,spec.y,spec.z)or 0
        if result==0 then return nil,refused(m)end
        if result==hellforge.ACT.waiting then return nil,'ASSET_UNAVAILABLE: HellForge is loading the explosion\'s packages'end
        return true
    end
    function world_module.projectile(world,spec)
        local m=actor()
        local result=m and backend().spawn_projectile(m,spec.type,spec.x,spec.y,spec.z,spec.dx,spec.dy,spec.dz)or 0
        if result==0 then return nil,refused(m)end
        if result==hellforge.ACT.waiting then return nil,'ASSET_UNAVAILABLE: HellForge is loading the projectile\'s packages'end
        return true
    end
end

-- Packages a request needs go through HellForge's package loader (the native request was the Runtime's own write).
local function packages(windows_write,world_module)
    local create=windows_write.create
    local function adapt(adapter)
        function adapter.package_request(request,instance,id)
            local hex=('%08X%08X'):format(b.u32(id,4),b.u32(id,0))
            local m=actor()
            if not m or backend().load_package(m,resource(hex))==0 then error('ASSET_UNAVAILABLE: '..refused(m),0)end
        end
        return adapter
    end
    windows_write.create=function(...)return adapt(create(...))end
    world_module.set_runtime(adapt(create()))
end

-- Homing and per-shot changes: HellForge's shot rules (one per projectile type), stopped with their configuration.
local function shots(homing,shots_module)
    local homing_configs,shot_configs={},{}
    local function sources(list)
        local out={}
        for _,hex in ipairs(list or{})do out[#out+1]=resource(hex)end
        return out
    end
    function homing.configure(spec)
        for _,config in ipairs(homing_configs)do
            if config.output==spec.output and config.status=='active'and config.owner~=spec.owner then
                return nil,'ALREADY_HOMING',spec.weapon..' shots already home for '..config.owner
            end
        end
        local m=actor()
        local flags=(spec.target=='friendly'and 4 or 0)+(spec.retarget==false and 2 or 0)+(spec.multiplayer and 1 or 0)
        local id=m and backend().homing(m,spec.type,sources(spec.sources),math.deg(spec.turn_rate),math.deg(spec.cone),
            spec.range,spec.arm_distance,spec.aim_height,flags)or 0
        if id==0 then return nil,'HELLFORGE_REFUSED',refused(m)end
        local config={id=id,status='active',owner=spec.owner,output=spec.output,weapon=spec.weapon,type=spec.type,
            label=spec.label or(spec.owner..' '..spec.weapon),mod=m,shots=0,steered=0,writes=0,locks=0,others=0,
            no_target=0,other_sources=0,refused={},hellforge=true}
        homing_configs[#homing_configs+1]=config
        return config
    end
    function homing.stop(config)
        if not config or config.status~='active'then return false end
        backend().stop_shots(config.mod,config.id)
        config.status='stopped'
        for i,item in ipairs(homing_configs)do if item==config then table.remove(homing_configs,i)break end end
        return true
    end
    function homing.configs()return homing_configs end
    local function rules(config)
        local c=config.changes or{}
        config.rules={}
        for _,kind in ipairs(config.types or{})do
            local id=backend().modify_shots(config.mod,kind,config.sources,c.damage or 1,c.armor_penetration or 1,c.speed or 1,
                c.gravity or 1,c.drag or 1,0)
            if id==0 then return false end
            config.rules[#config.rules+1]=id
        end
        return true
    end
    local function unrule(config)
        for _,id in ipairs(config.rules or{})do backend().stop_shots(config.mod,id)end
        config.rules={}
    end
    function shots_module.configure(spec)
        for _,config in ipairs(shot_configs)do
            if config.weapon==spec.weapon and config.status=='active'and config.owner~=spec.owner then
                return nil,'ALREADY_MODIFIED',spec.weapon..' shots are already modified for '..config.owner
            end
        end
        local m=actor()
        if not m then return nil,'HELLFORGE_REFUSED',refused(m)end
        if spec.callback then log.emit('[HD2Runtime] on HellForge: on_shot callbacks are not called (HellForge changes the shots itself)')end
        local config={status='active',owner=spec.owner,weapon=spec.weapon,types=spec.types,sources=sources(spec.sources),
            changes=spec.changes,label=spec.label or(spec.owner..' '..spec.weapon),mod=m,shots=0,modified=0,writes=0,
            untouched=0,others=0,other_sources=0,refused={},hellforge=true}
        if not rules(config)then
            local why=refused(m)
            unrule(config)
            return nil,'HELLFORGE_REFUSED',why
        end
        config.id=config.rules[1]
        shot_configs[#shot_configs+1]=config
        return config
    end
    function shots_module.set(config,changes)
        if not config or config.status~='active'then return false end
        unrule(config)
        config.changes=changes
        return rules(config)
    end
    function shots_module.stop(config)
        if not config or config.status~='active'then return false end
        unrule(config)
        config.status='stopped'
        for i,item in ipairs(shot_configs)do if item==config then table.remove(shot_configs,i)break end end
        return true
    end
    function shots_module.configs()return shot_configs end
end

-- The Pelican: HellForge spawns it and holds its hover (the request's hold); the Runtime's manager follows its stages.
local function pelican(pelicans)
    function pelicans.spawn(world,spec)
        spec=spec or{}
        local scheduler_state=require('hd2runtime/runtime/scheduler')
        if not scheduler_state.in_update()then
            return nil,'NOT_GAME_THREAD','the spawn runs only inside the Runtime\'s own update on the game thread'
        end
        for _,k in ipairs({'x','y','z','ax','ay','az','fx','fy'})do
            if not finite(spec[k])then return nil,'INVALID_POSITION','the spawn point, anchor and facing must be finite'end
        end
        local distance=math.sqrt((spec.ax-spec.x)^2+(spec.ay-spec.y)^2)
        local m=actor()
        local result,entity=0,0
        if m then result,entity=backend().spawn_pelican(m,spec.ax,spec.ay,spec.az,spec.hold or 0,distance,spec.z-spec.az,spec.fx,spec.fy)end
        if result==0 then return nil,'HELLFORGE_REFUSED',refused(m)end
        local anchor={x=spec.ax,y=spec.ay,z=spec.az}
        local out={entity=entity,position={x=spec.x,y=spec.y,z=spec.z},anchor=anchor,facing={x=spec.fx,y=spec.fy},verify={}}
        local p=pelicans.read(world,entity)
        out.verify.exists=p~=nil and p~=false
        if p then
            out.network=p.network;out.pelican=p
            out.verify.empty=p.cargo==nil and p.cargo_spawned==nil
            out.verify.flight=p.record~=nil
            local held=pelicans.anchor(world,entity)
            out.anchor_read=held
            out.verify.anchor=held~=nil and pelicans.distance(held,anchor)<0.01
        end
        out.verified=out.verify.exists==true and out.verify.empty==true and out.verify.flight==true and out.verify.anchor==true
        return out
    end
    -- HellForge holds it (the hold went with the spawn)
    function pelicans.hold(world,entity,expect,seconds)return {held_by='hellforge',seconds=seconds}end
end

-- Kill credit, the mission timer freeze, the Supply Pack.
local function the_rest(ownership,freeze,equipment)
    function ownership.credit_to_host(world,entity,label)
        local m=actor()
        local result=m and backend().credit_to_player(m,entity)or 0
        return {applied=result~=0,already=false,reason=result==0 and refused(m)or nil}
    end
    function freeze.set(request)
        assert(type(request)=='table','mission timer freeze request required')
        for k in pairs(request)do
            assert(k=='frozen'or k=='allow_unverified_effect','unsupported mission timer freeze option: '..tostring(k))
        end
        assert(type(request.frozen)=='boolean','frozen must be true or false')
        if request.allow_unverified_effect~=true then
            return nil,'ACKNOWLEDGEMENT_REQUIRED','freezing the mission timer is not gameplay-tested: it requires '
                ..'allow_unverified_effect=true'
        end
        local m=actor()
        if not m or backend().freeze_mission_timer(m,request.frozen)==0 then return nil,'HELLFORGE_REFUSED',refused(m)end
        return {status='APPLIED',frozen=request.frozen,source='hellforge',verified=false}
    end
    function freeze.follow()return nil,'NOT_APPLICABLE','on HellForge only the host freezes the timer'end
    -- the two game calls of the self-use: HellForge checks the ammunition and starts it
    equipment.set_adapter({
        needs_ammo=function()return true end,
        start_action=function()local m=actor();return m~=nil and backend().resupply_from_pack(m)~=0 end,
    })
end

function M.install()
    if not hellforge.active()then return false end
    local world_module=require('hd2runtime/runtime/event_world')
    world_actions(world_module)
    -- the game process's own adapter (a test's fake bridge has none)
    if backend().native then packages(require('hd2runtime/runtime/windows_write'),world_module)end
    shots(require('hd2runtime/runtime/projectile_homing'),require('hd2runtime/runtime/projectile_shots'))
    pelican(require('hd2runtime/runtime/pelicans'))
    the_rest(require('hd2runtime/runtime/ownership'),require('hd2runtime/runtime/mission_timer_freeze'),
        require('hd2runtime/runtime/player_equipment'))
    return true
end
return M
