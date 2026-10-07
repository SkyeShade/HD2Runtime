-- hd2.projectiles.modify_shots (docs/projectile-shots.md; runtime/projectile_shots.lua). DEVELOPMENT, solo.
--
--   local shots = hd2.projectiles.modify_shots('AR-23 Liberator', {damage = 0.5, gravity = 0.25})
--   shots:set({damage = 2})        -- the next shots
--   shots:stop()
--
-- A weapon is named as the projectile research names it (hd2.projectiles.homing_list()): its shots are this weapon's
-- projectile types fired by this weapon's entity types, and only the local player's own. Every option is a MULTIPLIER
-- of that one shot's own copy (the row, the DamageInfo row and every other weapon firing the same projectile stay
-- vanilla): damage (each direct hit's damage; explosions are not scaled), armor_penetration (each direct hit's
-- penetration lanes, rounded by the game), speed (its velocity and reference speed together), gravity, drag.
-- opts.on_shot(event) is called for each shot of the weapon seen: event.kind 'modified' | 'untouched' (every
-- multiplier 1), with event.before / event.after = {damage_multiplier, penetration_multiplier, speed, reference_speed,
-- gravity, drag, distance, damage = {id, standard, durable, armor_penetration}, armor_penetration}. A mod's second call
-- for the same weapon replaces its first; another mod's weapon is refused (ALREADY_MODIFIED). The configuration lasts
-- until stop() or the end of the session. Returns a handle: status 'active', or 'refused' with code and reason (a
-- refusal never raises).
local events=require('hd2runtime/runtime/events')
local shots=require('hd2runtime/runtime/projectile_shots')
local D=require('hd2runtime/domains/projectile_homing')
local M={}

M.LIMITS={damage={0.01,100},armor_penetration={0.1,10},speed={0.1,10},gravity={0,20},drag={0,20}}
local OPTIONS={damage=true,armor_penetration=true,speed=true,gravity=true,drag=true,on_shot=true,label=true,owner=true}

local by_name={}
for _,weapon in ipairs(D.weapons)do by_name[weapon.name:lower()]=weapon end

local Handle={};Handle.__index=Handle
function Handle:describe()
    return {kind='projectile_shots',owner=self.owner,status=self.status,code=self.code,reason=self.reason,
        weapon=self.weapon,types=self.types,changes=self.changes}
end
local function refuse(handle,code,reason)
    handle.status,handle.code,handle.reason='refused',code,reason
    events.emit_log('projectile shots ('..handle.owner..') refused: '..code..': '..reason)
    return handle
end
-- The multipliers of opts (nil keys: untouched), or nil, code, reason.
local function changes_of(opts)
    local out={}
    for key,limit in pairs(M.LIMITS)do
        local v=opts[key]
        if v~=nil then
            if type(v)~='number'or v~=v or v<limit[1]or v>limit[2]then
                return nil,'INVALID_OPTION',('opts.%s must be a multiplier from %g to %g'):format(key,limit[1],limit[2])
            end
            if v~=1 then out[key]=v end
        end
    end
    return out
end
local function text(changes)
    local parts={}
    for key,v in pairs(changes)do parts[#parts+1]=('%s x%g'):format(key,v)end
    table.sort(parts)
    return#parts>0 and table.concat(parts,', ')or'no change (every multiplier 1)'
end

function M.modify_shots(name,opts)
    opts=opts or{}
    local explicit=type(opts)=='table'and opts.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    local handle=setmetatable({kind='projectile_shots',owner=owner,status='pending'},Handle)
    if type(opts)~='table'then return refuse(handle,'INVALID_OPTION','opts must be a table')end
    for key in pairs(opts)do
        if not OPTIONS[key]then return refuse(handle,'INVALID_OPTION','unsupported option: '..tostring(key))end
    end
    local weapon=type(name)=='string'and by_name[name:lower()]
    if not weapon then
        return refuse(handle,'UNKNOWN_WEAPON',tostring(name)..' fires no projectile the research names (see '
            ..'hd2.projectiles.homing_list(); beams, arcs, sprays and melee are not projectiles)')
    end
    handle.weapon=weapon.name
    if opts.on_shot~=nil and type(opts.on_shot)~='function'then
        return refuse(handle,'INVALID_OPTION','opts.on_shot must be a function')
    end
    if opts.label~=nil and(type(opts.label)~='string'or#opts.label>64)then
        return refuse(handle,'INVALID_OPTION','opts.label must be a string of at most 64 characters')
    end
    local changes,code,reason=changes_of(opts)
    if not changes then return refuse(handle,code,reason)end
    local config,ccode,creason=shots.configure({owner=owner,weapon=weapon.name,types=weapon.types,
        sources=weapon.sources,changes=changes,label=opts.label or(owner..': '..weapon.name),callback=opts.on_shot})
    if not config then return refuse(handle,ccode,creason)end
    handle.config,handle.types,handle.changes,handle.status=config,weapon.types,changes,'active'
    events.emit_log(('projectile shots (%s): %s shots (projectile type%s %s): %s, solo only; every other weapon firing '
        ..'the same projectile stays vanilla'):format(owner,weapon.name,#weapon.types==1 and''or's',
        table.concat(weapon.types,', '),text(changes)))
    return handle
end
-- New multipliers for the next shots (the same options as modify_shots; omitted ones become 1). Returns the handle, or
-- nil, code, reason.
function Handle:set(opts)
    if self.status~='active'then return nil,'NOT_ACTIVE','the configuration is '..tostring(self.status)end
    if type(opts)~='table'then return nil,'INVALID_OPTION','opts must be a table'end
    for key in pairs(opts)do
        if not M.LIMITS[key]then return nil,'INVALID_OPTION','unsupported option: '..tostring(key)end
    end
    local changes,code,reason=changes_of(opts)
    if not changes then return nil,code,reason end
    shots.set(self.config,changes)
    self.changes=changes
    events.emit_log(('projectile shots (%s): %s shots now: %s'):format(self.owner,self.weapon,text(changes)))
    return self
end
function Handle:stop()
    if shots.stop(self.config)then self.status='stopped'end
    return self
end
-- This mission so far: {shots, modified, writes, untouched, others, other_sources, refused = {CODE = n}}.
function Handle:stats()
    local c=self.config
    if not c then return nil end
    local refused={}
    for code,n in pairs(c.refused)do refused[code]=n end
    return {shots=c.shots,modified=c.modified,writes=c.writes,untouched=c.untouched,others=c.others,
        other_sources=c.other_sources,refused=refused}
end
-- Every active configuration: {owner, weapon, changes, shots, modified}.
function M.status()
    local out={}
    for _,c in ipairs(shots.configs())do
        out[#out+1]={owner=c.owner,weapon=c.weapon,changes=c.changes,shots=c.shots,modified=c.modified}
    end
    return out
end
return M
