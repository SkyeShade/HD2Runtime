-- hd2.projectiles.homing (docs/projectile-homing.md; runtime/projectile_homing.lua).
--
--   local homing = hd2.projectiles.homing('EAT-17 Expendable Anti-Tank', {target = 'enemy', turn_rate = 120})
--   local stims = hd2.projectiles.homing('P-11 Stim Pistol', {target = 'friendly', multiplayer = true})
--   homing:stop()
--
-- A weapon is named as the projectile research names it (hd2.projectiles.homing_list(); a catalogued projectile output
-- id also works): its shots are this weapon's projectile types fired by this weapon's entity types, and only the local
-- player's own. A mod's second call for the same weapon replaces its first; another mod's weapon is refused
-- (ALREADY_HOMING). The configuration lasts until stop() or the end of the session, across missions. Returns a handle:
-- status 'active', or 'refused' with code and reason (a refusal never raises).
local events=require('hd2runtime/runtime/events')
local homing=require('hd2runtime/runtime/projectile_homing')
local D=require('hd2runtime/domains/projectile_homing')
local M={}

M.DEFAULTS={target='enemy',turn_rate=90,cone=30,range=100,arm_distance=2,aim_height=1}
M.LIMITS={turn_rate={1,1440},cone={1,180},range={1,500},arm_distance={0,100},aim_height={-5,10}}
M.LIMITS.lateral_acceleration={1,100000}
M.DEFAULTS.lock_time,M.DEFAULTS.max_targets=.3,1
M.LIMITS.lock_time,M.LIMITS.max_targets={0,2},{1,6}
local OPTIONS={target=true,turn_rate=true,cone=true,range=true,arm_distance=true,aim_height=true,retarget=true,
    multiplayer=true,label=true,owner=true,lateral_acceleration=true,
    acquisition=true,lock_time=true,max_targets=true,require_los=true,require_aim=true}
local handles={}

local by_name={}
for _,weapon in ipairs(D.weapons)do by_name[weapon.name:lower()]=weapon end

local function resolve(name)
    if type(name)~='string'then
        return nil,'UNKNOWN_WEAPON','a weapon is named by its name (hd2.projectiles.homing_list()); raw ids are refused'
    end
    local weapon=by_name[name:lower()]
    if not weapon and name:match('^output/v1/projectile/')then
        local output=require('hd2runtime/domains/attack_outputs').outputs[name]
        local owner=output and output.owner and output.owner.name
        weapon=owner and by_name[owner:lower()]
        if output and not weapon then
            return nil,'UNKNOWN_WEAPON','the projectile research names no projectile fired by '..tostring(owner or name)
        end
    end
    if not weapon then
        return nil,'UNKNOWN_WEAPON',name..' fires no projectile the research names (beams, arcs, sprays and melee are '
            ..'not projectiles; see hd2.projectiles.homing_list())'
    end
    return weapon
end

local Handle={};Handle.__index=Handle
function Handle:describe()
    return {kind='projectile_homing',owner=self.owner,status=self.status,code=self.code,reason=self.reason,
        weapon=self.weapon,types=self.types,target=self.target,options=self.options}
end

local function refuse(handle,code,reason)
    handle.status,handle.code,handle.reason='refused',code,reason
    events.emit_log('projectile homing ('..handle.owner..') refused: '..code..': '..reason)
    return handle
end

local function number(opts,key,handle)
    local value=opts[key]
    if value==nil then return M.DEFAULTS[key]end
    local limit=M.LIMITS[key]
    if type(value)~='number'or value~=value or value<limit[1]or value>limit[2]then
        refuse(handle,'INVALID_OPTION',('opts.%s must be a number from %g to %g'):format(key,limit[1],limit[2]))
        return nil
    end
    return value
end

function M.homing(name,opts)
    opts=opts or{}
    local explicit=type(opts)=='table'and opts.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    local handle=setmetatable({kind='projectile_homing',owner=owner,status='pending'},Handle)
    if type(opts)~='table'then return refuse(handle,'INVALID_OPTION','opts must be a table')end
    for key in pairs(opts)do
        if not OPTIONS[key]then return refuse(handle,'INVALID_OPTION','unsupported option: '..tostring(key))end
    end
    local weapon,code,reason=resolve(name)
    if not weapon then return refuse(handle,code,reason)end
    handle.weapon=weapon.name
    local target=opts.target==nil and M.DEFAULTS.target or opts.target
    if target~='enemy'and target~='friendly'then
        return refuse(handle,'INVALID_OPTION','opts.target must be "enemy" or "friendly"')
    end
    local values={}
    for _,key in ipairs({'turn_rate','cone','range','arm_distance','aim_height'})do
        values[key]=number(opts,key,handle)
        if values[key]==nil then return handle end
    end
    if opts.lateral_acceleration~=nil then
        values.lateral_acceleration=number(opts,'lateral_acceleration',handle)
        if values.lateral_acceleration==nil then return handle end
    end
    for _,key in ipairs({'retarget','multiplayer','require_aim'})do
        if opts[key]~=nil and type(opts[key])~='boolean'then
            return refuse(handle,'INVALID_OPTION','opts.'..key..' must be true or false')
        end
    end
    local acquisition=opts.acquisition==nil and'in_flight'or opts.acquisition
    if acquisition~='in_flight'and acquisition~='pre_fire'then
        return refuse(handle,'INVALID_OPTION','opts.acquisition must be "in_flight" or "pre_fire"')
    end
    local lock
    if acquisition=='pre_fire'then
        if target~='enemy'or opts.multiplayer==true or opts.retarget==true then
            return refuse(handle,'INVALID_OPTION','pre_fire currently requires enemy targets, solo, and no retarget')
        end
        if values.cone>30 or values.range>300 then
            return refuse(handle,'INVALID_OPTION','pre_fire currently supports cone <= 30 degrees and range <= 300 m')
        end
        for _,key in ipairs({'lock_time','max_targets'})do
            values[key]=number(opts,key,handle);if values[key]==nil then return handle end
        end
        if values.max_targets%1~=0 or(opts.require_los~=nil and type(opts.require_los)~='boolean')then
            return refuse(handle,'INVALID_OPTION','max_targets must be an integer; require_los must be a boolean')
        end
        lock=require('hd2runtime/runtime/homing_lock').new({weapon=weapon,
            world=require('hd2runtime/runtime/event_world'),aim=require('hd2runtime/runtime/homing_aim'),
            require_aim=opts.require_aim==true,
            aim_state=opts.require_aim==true and require('hd2runtime/runtime/homing_aim_state')or nil,
            view=require('hd2runtime/runtime/homing_view'),aim_height=values.aim_height,
            position_age=homing.POSITION_AGE,
            config={enabled=true,mode=values.max_targets==1 and'single'or'multi',lock_time=values.lock_time,
                max_targets=values.max_targets,half_angle=values.cone,range=values.range,require_los=opts.require_los==true}})
    elseif opts.lock_time~=nil or opts.max_targets~=nil or opts.require_los~=nil or opts.require_aim~=nil then
        return refuse(handle,'INVALID_OPTION','lock_time, max_targets, require_los and require_aim need acquisition = "pre_fire"')
    end
    local retarget=acquisition=='in_flight'and opts.retarget~=false
    if opts.label~=nil and(type(opts.label)~='string'or#opts.label>64)then
        return refuse(handle,'INVALID_OPTION','opts.label must be a string of at most 64 characters')
    end
    local configs={}
    for _,kind in ipairs(weapon.types)do
        local config,ccode,creason=homing.configure({owner=owner,output=weapon.name..'#'..kind,weapon=weapon.name,
            type=kind,sources=weapon.sources,target=target,turn_rate=math.rad(values.turn_rate),
            lateral_acceleration=values.lateral_acceleration,
            lock_control=lock and lock.hooks,
            cone=math.rad(values.cone),range=values.range,arm_distance=values.arm_distance,
            aim_height=values.aim_height,retarget=retarget,multiplayer=opts.multiplayer==true,
            label=opts.label or(owner..': '..weapon.name)})
        if not config then
            for _,made in ipairs(configs)do homing.stop(made)end
            if lock then lock:stop()end
            return refuse(handle,ccode,creason)
        end
        configs[#configs+1]=config
    end
    handle.configs=configs
    handle._lock=lock
    handle.config=configs[1]
    handle.types=weapon.types
    handle.target=target
    handle.options={turn_rate=values.turn_rate,cone=values.cone,range=values.range,arm_distance=values.arm_distance,
        lateral_acceleration=values.lateral_acceleration,
        aim_height=values.aim_height,retarget=retarget,multiplayer=opts.multiplayer==true,
        acquisition=acquisition,lock_time=values.lock_time,max_targets=values.max_targets,
        require_los=opts.require_los==true,require_aim=opts.require_aim==true}
    handle.status='active'
    local key=owner..'\0'..weapon.name
    local previous=handles[key]
    if previous then previous:stop();previous.status='replaced'end
    handles[key]=handle
    handle._key=key
    events.emit_log(('projectile homing (%s): %s shots (projectile type%s %s) home on %s: turn %g deg/s, cone %g deg, '
        ..'range %g m, armed after %g m%s'):format(owner,weapon.name,#weapon.types==1 and''or's',
        table.concat(weapon.types,', '),target=='enemy'and'enemies'or'other players',values.turn_rate,values.cone,
        values.range,values.arm_distance,opts.multiplayer==true and', multiplayer (experimental)'or', solo only'))
    if values.lateral_acceleration then
        events.emit_log(('projectile homing (%s): acceleration budget %g m/s^2; turn_rate %g deg/s is the cap')
            :format(owner,values.lateral_acceleration,values.turn_rate))
    end
    return handle
end

-- Stops every projectile type of the weapon.
function Handle:stop()
    local stopped=false
    for _,config in ipairs(self.configs or{})do stopped=homing.stop(config)or stopped end
    if stopped then self.status='stopped'end
    if self._lock then self._lock:stop();self.status='stopped'end
    if self._reticle then self._reticle:stop();self._reticle=nil end
    if self._key and handles[self._key]==self then handles[self._key]=nil end
    return self
end

-- A detached, read-only observation for custom UI. Coordinates are top-left
-- pixels; entity IDs are game IDs, not hit confirmation or persistent identities.
function Handle:lock_state()
    if not self._lock then return nil end
    local visual=self._lock:visual_snapshot()
    local out=self._lock:status();out.locked,out.acquiring={},{}
    out.visible=visual.visible;out.half_angle=visual.half_angle
    out.ui_visible=visual.visible and not require('hd2runtime/runtime/homing_visibility').blocked()
    local V=require('hd2runtime/runtime/homing_view');local frame=visual.frame
    if frame then
        out.width,out.height=frame.width,frame.height
        out.vertical_fov=frame.vertical_fov
        out.radius=V.radius(frame,visual.half_angle)
    end
    for _,name in ipairs({'locked','acquiring'})do for _,t in ipairs(visual[name])do
        local point={x=t.x,y=t.y,z=t.z};local screen=frame and V.project(frame,point)
        out[name][#out[name]+1]={id='entity:'..tostring(t.entity),entity=t.entity,name=t.name,
            position=point,screen=screen and{x=screen.x,y=frame.height-screen.y},
            progress=t.progress,los=t.los or'unknown',los_reason=t.los_reason,
            los_observed_at=t.los_observed_at,acquired_at=t.acquired_at}
    end end
    return out
end

-- Optional standard HUD; custom renderers can instead consume lock_state().
-- Style errors raise like hd2.ui.overlay; a refused gameplay handle is never drawn.
function Handle:reticle(opts)
    local api=require('hd2runtime/api/homing_reticle')
    require('hd2runtime/runtime/homing_reticle').validate_style(opts)
    if self._reticle then self._reticle:stop()end
    self._reticle=api.open(self,opts)
    return self._reticle
end
-- This mission so far: {shots (own shots seen), steered, writes, locks, others (shots that are not this player's,
-- untouched), other_sources (this player's shots of the same type from another weapon), no_target (acquisitions that
-- found nothing), refused = {CODE = n}}.
function Handle:stats()
    if not self.configs then return nil end
    local out={shots=0,steered=0,writes=0,locks=0,others=0,other_sources=0,no_target=0,refused={}}
    for _,c in ipairs(self.configs)do
        for _,key in ipairs({'shots','steered','writes','locks','others','other_sources','no_target'})do
            out[key]=out[key]+c[key]
        end
        for code,n in pairs(c.refused)do out.refused[code]=(out.refused[code]or 0)+n end
    end
    return out
end

-- Every weapon whose shots can home: {name, categories, types}. Offline; no game reads.
function M.list()
    local out={}
    for _,weapon in ipairs(D.weapons)do
        local types={}
        for k,t in ipairs(weapon.types)do types[k]=t end
        local categories={}
        for k,c in ipairs(weapon.categories)do categories[k]=c end
        out[#out+1]={name=weapon.name,categories=categories,types=types}
    end
    return out
end

-- Every active configuration: {owner, weapon, type, target, shots, steered, writes}.
function M.status()
    local out={}
    for _,c in ipairs(homing.configs())do
        out[#out+1]={owner=c.owner,weapon=c.weapon,type=c.type,target=c.target,shots=c.shots,steered=c.steered,
            writes=c.writes}
    end
    return out
end
return M
