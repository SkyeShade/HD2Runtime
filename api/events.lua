-- Public scripting API: hd2.events, hd2.after / hd2.every, hd2.input and hd2.mod. See docs/events.md.
local events=require('hd2runtime/runtime/events')
local input=require('hd2runtime/runtime/input')
local catalog=require('hd2runtime/domains/events_catalog')
local sources=require('hd2runtime/runtime/event_sources')
local handles=require('hd2runtime/runtime/handles')
local world_module=require('hd2runtime/runtime/event_world')
local M={}

-- The owner of a registration made directly through hd2.* (runtime/events.lua M.owner): an explicit opts.owner,
-- else the mod scope (the SDK addon wrapper runs each mod's startup as its resource id), else the mod whose callback
-- is running, else the calling chunk when it is a mod resource, else 'unknown'. Stack level 3 is the mod's own frame
-- (1 this function, 2 the hd2.* function the mod called), so these functions must be exported without wrappers.
local function owner_of(opts)
    local explicit=opts and opts.owner
    if explicit~=nil and(type(explicit)~='string'or#explicit==0 or#explicit>128 or explicit:find('[%c]'))then
        return nil,'owner must be a mod id string'
    end
    local owner=events.owner(explicit,3)   -- not a tail call: the level counts this frame
    return owner
end

local api={}
function api.on(name,callback,opts)
    local owner,why=owner_of(opts)
    if not owner then return events.refused(name,opts and opts.owner,why)end
    return events.subscribe(name,callback,setmetatable({owner=owner},{__index=opts}))
end
function api.once(name,callback,opts)
    local owner,why=owner_of(opts)
    if not owner then return events.refused(name,opts and opts.owner,why)end
    return events.subscribe(name,callback,setmetatable({owner=owner,once=true},{__index=opts}))
end
-- Every catalogued event name.
function api.names()local copy={};for i,name in ipairs(catalog.names)do copy[i]=name end;return copy end
-- Offline description of one event: status, phase (pre/post), payload fields, hot, source.
function api.describe(name)
    local spec=assert(catalog.events[name],'unknown event '..tostring(name))
    local copy={}
    for key,value in pairs(spec)do copy[key]=value end
    return copy
end
-- Live status of every event (available / idle / unavailable / blocked) with the reason.
function api.status()return events.status()end
function api.subscriptions(filter)return events.subscriptions(filter)end
-- The cause of the event whose callback is running now ({source='native'} or {source='mod', mod=...}).
function api.cause()local event=events.state.current_event;return event and event.cause or nil end
function api.in_mission()return(events.mission())end
-- The current mission id (the epoch every event of this mission carries as event.mission) and whether a mission is
-- in progress. Compare a saved event.mission with it to know a delayed callback still runs in the same mission.
function api.mission_id()local in_mission,epoch=events.mission();return epoch,in_mission end
-- The mod every registration made now belongs to (see runtime/events.lua M.owner).
function api.owner()local owner=events.owner(nil,2);return owner end
-- Run fn(...) as the given mod: every subscription, timer, keybind and action started inside belongs to it. The
-- SDK addon wrapper runs each mod's startup this way, so authors never pass their resource id.
function api.run_as(owner,fn,...)return events.run_as(owner,fn,...)end
M.events=api

function M.after(seconds,callback,opts)
    local owner,why=owner_of(opts)
    if not owner then return events.refused_timer(opts and opts.owner,why)end
    return events.timer('after',seconds,callback,setmetatable({owner=owner},{__index=opts}))
end
function M.every(seconds,callback,opts)
    local owner,why=owner_of(opts)
    if not owner then return events.refused_timer(opts and opts.owner,why)end
    return events.timer('every',seconds,callback,setmetatable({owner=owner},{__index=opts}))
end

----------------------------------------------------------------------------------------------- entity ids --
-- hd2.entities: the identity catalog of every entity type with health (domains/event_entities.lua). Offline; no game
-- reads. Semantic ids are the enemy catalog's ('enemy/v1/automatons/soldier_mg') or path-derived
-- ('entity/v1/helldivers/avatar_helldiver'); display_name is set only where the catalog proves a wiki name.
local entity_catalog=require('hd2runtime/domains/event_entities').entities
local by_semantic   -- semantic id -> type hash, built on first use
local function semantic_index()
    if not by_semantic then
        by_semantic={}
        for type_hex,info in pairs(entity_catalog)do by_semantic[info.id]=type_hex end
    end
    return by_semantic
end
local function identity(type_hex)
    local info=entity_catalog[type_hex]
    if not info then return nil end
    return {id=info.id,type=type_hex,name=info.name,display_name=info.display,faction=info.faction,kind=info.kind,
        enemy=info.kill==true,avatar=info.avatar==true}
end
local entities={}
-- The identity of a semantic id or a 16-hex-digit type hash; nil when the catalog does not have it (check your ids
-- at load time with this: a typo returns nil instead of silently never matching).
function entities.describe(value)
    if type(value)~='string'then return nil end
    local type_hex=semantic_index()[value]
    if not type_hex and#value==16 and value:match('^%x+$')then type_hex=value:upper()end
    return type_hex and identity(type_hex)or nil
end
-- Every catalogued identity matching filter {faction=, kind=, enemy=}, sorted by semantic id.
function entities.list(filter)
    local result={}
    for type_hex in pairs(entity_catalog)do
        local item=identity(type_hex)
        if(not filter or filter.faction==nil or filter.faction==item.faction)and(not filter or filter.kind==nil
            or filter.kind==item.kind)and(not filter or filter.enemy==nil or filter.enemy==item.enemy)then
            result[#result+1]=item
        end
    end
    table.sort(result,function(a,c)return a.id<c.id end)
    return result
end
M.entities=entities

-- The game's state now: {state, name, mission, host, mode}; nil when unreadable.
function M.game_state()
    local world=world_module.open()
    return world and world_module.game_state(world)or nil
end
-- Players in the session (HD2PlayerHandle) and the local player (nil when unreadable).
function M.players()return handles.players()end
function M.local_player()return handles.local_player()end

M.input={}
function M.input.bind(id,spec)
    local owner,why=owner_of(type(spec)=='table'and spec or nil)
    if not owner then return input.rejected(id,spec and spec.owner,why)end
    return input.bind(id,spec,owner)
end
function M.input.bindings()return input.bindings()end
function M.input.get(id)return input.get(id)end
function M.input.keys()
    local names={}
    for name in pairs(input.keys)do names[#names+1]=name end
    table.sort(names)
    return names
end

--------------------------------------------------------------------------------------------- mod contexts --
-- hd2.mod(id) is one mod's scripting context: everything it registers is attributed to it, and it owns a mission
-- table (cleared when a mission starts and when it ends) and a session table (kept for the game session).
-- Calling hd2.mod(id) again returns the same context.
local contexts=rawget(_G,'HD2RuntimeModContextsV1')or{}
rawset(_G,'HD2RuntimeModContextsV1',contexts)
local Mod={};Mod.__index=Mod
local function scoped(self,opts)return setmetatable({owner=self.id},{__index=opts})end
function Mod:on(name,callback,opts)return events.subscribe(name,callback,scoped(self,opts))end
function Mod:once(name,callback,opts)
    local merged=scoped(self,opts);merged=setmetatable({once=true},{__index=merged})
    return events.subscribe(name,callback,merged)
end
function Mod:after(seconds,callback,opts)return events.timer('after',seconds,callback,scoped(self,opts))end
function Mod:every(seconds,callback,opts)return events.timer('every',seconds,callback,scoped(self,opts))end
function Mod:bind(id,spec)return input.bind(id,spec,self.id)end
-- A number this mod sets from code and binds to an hd2.ensure field value (see api/options.lua M.value).
function Mod:value(spec)return require('hd2runtime/api/options').value(spec,self.id)end
function Mod:log(message)events.emit_log('['..self.id..'] '..tostring(message))end
function Mod:in_mission()return(events.mission())end
function Mod:subscriptions()return events.subscriptions({owner=self.id})end
-- Run fn(...) as this mod: hd2.events.on, hd2.after, hd2.input.bind and actions called inside belong to it.
function Mod:run(fn,...)return events.run_as(self.id,fn,...)end
-- hd2.mod() with no id is the calling mod (the SDK addon wrapper's scope, the running callback's mod, or the mod
-- resource chunk); it refuses to guess when none of those names a mod.
function M.mod(id)
    if id==nil then
        id=events.owner(nil,2)
        assert(id~='unknown','hd2.mod() cannot tell which mod is calling: pass the mod resource id, '
            ..'hd2.mod("mods/author/name")')
    end
    assert(type(id)=='string'and id:match('^[%w_][%w_/%.%-]*$')and#id<=128,
        'mod id must be the mod resource or a stable name (letters, digits, _ / . -)')
    local context=contexts[id]
    if context then return context end
    context=setmetatable({id=id,session={},mission=events.mission_table(id)},Mod)
    contexts[id]=context
    -- A mod context tracks mission boundaries (its mission table resets on them).
    events.require_source(sources.game_state.name,1)
    return context
end
return M
