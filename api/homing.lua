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
local OPTIONS={target=true,turn_rate=true,cone=true,range=true,arm_distance=true,aim_height=true,retarget=true,
    multiplayer=true,label=true,owner=true}

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
    for _,key in ipairs({'retarget','multiplayer'})do
        if opts[key]~=nil and type(opts[key])~='boolean'then
            return refuse(handle,'INVALID_OPTION','opts.'..key..' must be true or false')
        end
    end
    if opts.label~=nil and(type(opts.label)~='string'or#opts.label>64)then
        return refuse(handle,'INVALID_OPTION','opts.label must be a string of at most 64 characters')
    end
    local configs={}
    for _,kind in ipairs(weapon.types)do
        local config,ccode,creason=homing.configure({owner=owner,output=weapon.name..'#'..kind,weapon=weapon.name,
            type=kind,sources=weapon.sources,target=target,turn_rate=math.rad(values.turn_rate),
            cone=math.rad(values.cone),range=values.range,arm_distance=values.arm_distance,
            aim_height=values.aim_height,retarget=opts.retarget~=false,multiplayer=opts.multiplayer==true,
            label=opts.label or(owner..': '..weapon.name)})
        if not config then
            for _,made in ipairs(configs)do homing.stop(made)end
            return refuse(handle,ccode,creason)
        end
        configs[#configs+1]=config
    end
    handle.configs=configs
    handle.config=configs[1]
    handle.types=weapon.types
    handle.target=target
    handle.options={turn_rate=values.turn_rate,cone=values.cone,range=values.range,arm_distance=values.arm_distance,
        aim_height=values.aim_height,retarget=opts.retarget~=false,multiplayer=opts.multiplayer==true}
    handle.status='active'
    events.emit_log(('projectile homing (%s): %s shots (projectile type%s %s) home on %s: turn %g deg/s, cone %g deg, '
        ..'range %g m, armed after %g m%s'):format(owner,weapon.name,#weapon.types==1 and''or's',
        table.concat(weapon.types,', '),target=='enemy'and'enemies'or'other players',values.turn_rate,values.cone,
        values.range,values.arm_distance,opts.multiplayer==true and', multiplayer (experimental)'or', solo only'))
    return handle
end

-- Stops every projectile type of the weapon.
function Handle:stop()
    local stopped=false
    for _,config in ipairs(self.configs or{})do stopped=homing.stop(config)or stopped end
    if stopped then self.status='stopped'end
    return self
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
