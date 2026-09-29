-- Public scripting API: hd2.events, hd2.after / hd2.every, hd2.input and hd2.mod. See docs/events.md.
local events=require('hd2runtime/runtime/events')
local input=require('hd2runtime/runtime/input')
local catalog=require('hd2runtime/domains/events_catalog')
local sources=require('hd2runtime/runtime/event_sources')
local handles=require('hd2runtime/runtime/handles')
local world_module=require('hd2runtime/runtime/event_world')
local M={}

-- The owner of a registration made directly through hd2.*: an explicit opts.owner, else the calling chunk when it
-- is a mod resource ('mods/author/name'), else 'unknown'. Stack level 3 is the mod's own frame (1 this function,
-- 2 the hd2.* function the mod called), so these functions must be exported without wrappers.
local function owner_of(opts)
    local explicit=opts and opts.owner
    if explicit~=nil then
        if type(explicit)~='string'or#explicit==0 or#explicit>128 or explicit:find('[%c]')then
            return nil,'owner must be a mod id string'
        end
        return explicit
    end
    local info=debug and debug.getinfo and debug.getinfo(3,'S')
    local source=(info and info.source or''):gsub('^[@=]',''):gsub('%.lua$','')
    return source:match('^mods/[%w_/]+$')and source or'unknown'
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
function M.mod(id)
    if id==nil then id=events.owner(nil,2)end
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
