-- hd2.enemies (docs/enemy-spawns.md; runtime/enemy_spawn_weights.lua): how often each enemy type spawns.
--
--   local more = hd2.enemies.spawn_weight('Charger', 3, {allow_unverified_effect = true})
--   local none = hd2.enemies.spawn_weight('Bile Titan', 0, {allow_unverified_effect = true})
--   more:stop()
--
-- An enemy is named as the spawn rosters name it (hd2.enemies.spawn_list(); a display name such as 'Charger', a native
-- name such as 'warrior_tier_1', a catalogue id or the 16-hex entity type). The multiplier scales that type's weight in
-- every spawn group it is in, at every difficulty (or only opts.difficulties): 0 = it never spawns from a group,
-- 2 = twice its vanilla weight. It changes the mix of what spawns, not how many enemies a spawn makes. A refusal never
-- raises: the handle's status is 'refused' with a code and a reason.
local events=require('hd2runtime/runtime/events')
local weights=require('hd2runtime/runtime/enemy_spawn_weights')
local world_module=require('hd2runtime/runtime/event_world')
local D=require('hd2runtime/domains/enemy_spawn_weights')
local b=require('hd2runtime/core/bytes')
local M={}
local OPTIONS={difficulties=true,allow_unverified_effect=true,owner=true,label=true}

-- name (lower case) -> {entity = true}, and entity -> its label
local by_name,labels={},{}
local function add(name,entity)
    if type(name)~='string'or name==''then return end
    local key=name:lower()
    by_name[key]=by_name[key]or{}
    by_name[key][entity]=true
end
for _,faction in ipairs(D.factions)do
    for _,entry in ipairs(faction.entries)do
        local info=world_module.type_info(entry.entity)or{}
        labels[entry.entity]=info.display or info.name or entry.name or entry.entity
        add(entry.name,entry.entity);add(info.display,entry.entity);add(info.name,entry.entity)
        add(entry.id or info.id,entry.entity);add(entry.entity,entry.entity)
    end
end

local function resolve(name)
    if type(name)~='string'then
        return nil,'UNKNOWN_ENEMY','an enemy is named by its name (hd2.enemies.spawn_list())'
    end
    local key=name:lower():gsub('^0x','')
    local found=by_name[key]
    if not found then
        return nil,'UNKNOWN_ENEMY',name..' is in no spawn roster (see hd2.enemies.spawn_list())'
    end
    local list={}
    for entity in pairs(found)do list[#list+1]=entity end
    table.sort(list)
    return list
end

local STATUS_ORDER={refused=1,conflict=2,unavailable=3,deferred=4,pending=5,stopping=6,applied=7,stopped=8,replaced=9}
local Handle={}
local function aggregate(handle)
    local worst
    for _,config in ipairs(rawget(handle,'configs')or{})do
        local s=config.status
        if not worst or(STATUS_ORDER[s]or 0)<(STATUS_ORDER[worst]or 0)then worst=s end
    end
    return worst or'refused'
end
local meta={__index=function(t,k)
    if k=='status'then return aggregate(t)end
    if k=='code'or k=='reason'then
        for _,config in ipairs(rawget(t,'configs')or{})do if config[k]then return config[k]end end
        return nil
    end
    return Handle[k]
end}

-- Restores every type of the handle to its vanilla weights.
function Handle:stop()
    for _,config in ipairs(rawget(self,'configs')or{})do weights.stop(config)end
    return self
end
function Handle:describe()
    local types={}
    for _,config in ipairs(rawget(self,'configs')or{})do
        types[#types+1]={entity=config.entity,label=config.label,status=config.status,rows=#config.rows,
            factions=config.factions,code=config.code,reason=config.reason}
    end
    return {kind='enemy_spawn_weight',owner=self.owner,enemy=self.enemy,multiplier=self.multiplier,
        status=self.status,code=self.code,reason=self.reason,types=types}
end

local function refuse(handle,code,reason)
    rawset(handle,'status','refused');rawset(handle,'code',code);rawset(handle,'reason',reason)
    events.emit_log('enemy spawn weight ('..handle.owner..') refused: '..code..': '..reason)
    return handle
end

function M.spawn_weight(enemy,multiplier,opts)
    opts=opts or{}
    local explicit=type(opts)=='table'and opts.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    local handle=setmetatable({kind='enemy_spawn_weight',owner=owner,enemy=enemy,multiplier=multiplier},meta)
    if type(opts)~='table'then return refuse(handle,'INVALID_OPTION','opts must be a table')end
    for key in pairs(opts)do
        if not OPTIONS[key]then return refuse(handle,'INVALID_OPTION','unsupported option: '..tostring(key))end
    end
    if opts.allow_unverified_effect~=true then
        return refuse(handle,'ACKNOWLEDGEMENT_REQUIRED','spawn weights are not yet shown in game: pass '
            ..'allow_unverified_effect = true')
    end
    if type(multiplier)~='number'or multiplier~=multiplier or multiplier<0 or multiplier>weights.MAX_MULTIPLIER then
        return refuse(handle,'INVALID_MULTIPLIER','the multiplier must be a number from 0 to '..weights.MAX_MULTIPLIER)
    end
    local difficulties={}
    if opts.difficulties==nil then
        for d=1,10 do difficulties[d]=true end
    else
        if type(opts.difficulties)~='table'or#opts.difficulties<1 then
            return refuse(handle,'INVALID_OPTION','opts.difficulties must list difficulties 1..10')
        end
        for _,d in ipairs(opts.difficulties)do
            if type(d)~='number'or d%1~=0 or d<1 or d>10 then
                return refuse(handle,'INVALID_OPTION','opts.difficulties must list difficulties 1..10')
            end
            difficulties[d]=true
        end
    end
    if opts.label~=nil and(type(opts.label)~='string'or#opts.label>64)then
        return refuse(handle,'INVALID_OPTION','opts.label must be a string of at most 64 characters')
    end
    local list,code,reason=resolve(enemy)
    if not list then return refuse(handle,code,reason)end
    local configs={}
    for _,entity in ipairs(list)do
        local label=opts.label or labels[entity]
        if#list>1 then label=label..' ('..entity..')'end
        local config,ccode,creason=weights.configure({owner=owner,entity=entity,label=label,multiplier=multiplier,
            difficulties=difficulties})
        if not config then
            for _,made in ipairs(configs)do weights.stop(made)end
            return refuse(handle,ccode,creason)
        end
        configs[#configs+1]=config
    end
    rawset(handle,'configs',configs)
    rawset(handle,'types',list)
    return handle
end

-- Every roster row: {enemy, entity, id, faction, index, group, weights (difficulty 1..10)}, optionally only one
-- faction ('terminids', 'automatons', 'illuminate') or one enemy. Offline; the vanilla weights.
function M.spawn_list(filter)
    filter=type(filter)=='table'and filter or{}
    local wanted
    if filter.enemy~=nil then
        wanted={}
        for _,entity in ipairs(resolve(filter.enemy)or{})do wanted[entity]=true end
    end
    local out={}
    for _,faction in ipairs(D.factions)do
        if filter.faction==nil or filter.faction==faction.name then
            for _,entry in ipairs(faction.entries)do
                if not wanted or wanted[entry.entity]then
                    local raw=b.unhex(entry.weights)
                    local w={}
                    for d=1,10 do w[d]=b.value(raw,(d-1)*4,'f32')end
                    out[#out+1]={enemy=labels[entry.entity],entity=entry.entity,id=entry.id,faction=faction.name,
                        index=entry.index,group=entry.group,weights=w}
                end
            end
        end
    end
    return out
end

-- Every active configuration: {owner, enemy, entity, multiplier, status, rows}.
function M.spawn_status()
    local out={}
    for _,config in pairs(weights.configs())do
        out[#out+1]={owner=config.owner,enemy=config.label,entity=config.entity,multiplier=config.multiplier,
            status=config.status,rows=#config.rows}
    end
    table.sort(out,function(x,y)return x.entity<y.entity end)
    return out
end
return M
