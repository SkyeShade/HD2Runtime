-- Game sound events a mod plays (hd2.sounds.play / stop / name_for; docs/sounds.md). Nothing here writes game memory.
--
-- The post is the Wwise plugin's own Lua API, the path runtime/ui_sound.lua proved for the loadout screen's sounds:
-- stingray.WwiseWorld.trigger_event(Wwise.wwise_world(world), name[, position]) on the game's own Game World
-- (ui_sound.game_world: the Application.worlds value at the Game World's position in the engine's world array). The
-- plugin (bin/plugins/wwise_pluginw64_release.dll, read from the installed file):
--   * trigger_event 0xD9C0: arg 1 the WwiseWorld, arg 2 a STRING (strlen'd and hashed by 0xD4A70, AK GetIDFromString:
--     FNV-1 32 of the lower-cased name; a number would be hashed as its decimal text), the source from arg 3 on
--     (0xA6C0: none = the world's own default source +0x4148; a unit; a Vector3 position with an optional Quaternion);
--     returns the playing id and the source id (0 when the event id is 0, the invalid id when the source is invalid);
--   * stop_event 0xDB50: (WwiseWorld, playing id) stops that one playing instance;
--   * has_event 0xD810: (name) whether the sound engine knows the event (its bank is loaded).
-- So an event is posted by NAME. An event known only by its 32-bit id is posted through a name whose FNV-1 is that id
-- (M.name_for: 'hd2runtime_' and seven characters, found by meet-in-the-middle, as the Runtime's own UI sounds are).
-- Guards (the plugin checks no arguments): the world proven, the selector's pins (they cover the Game World offsets),
-- the API callable, the Game World matched, has_event true, a per-mod rate limit. A position is three finite numbers.
local world_module=require('hd2runtime/runtime/event_world')
local selector=require('hd2runtime/runtime/stratagem_selector')
local ui_sound=require('hd2runtime/runtime/ui_sound')
local weapon_sounds=require('hd2runtime/runtime/weapon_sounds')
local engine_gui=require('hd2runtime/runtime/engine_gui')
local log=require('hd2runtime/runtime/log')
local events=require('hd2runtime/runtime/events')
local wwise_names=require('hd2runtime/runtime/wwise_names')
local precomputed=require('hd2runtime/domains/sound_event_names')
local KEY='HD2RuntimeSoundEventsV1'
local existing=rawget(_G,KEY)
if existing then return existing end
local M={}
rawset(_G,KEY,M)
M.RATE=32            -- posts per mod per RATE_WINDOW seconds
M.RATE_WINDOW=1

local function emit(message)pcall(log.emit,'[HD2Runtime] '..message)end

------------------------------------------------------------------------------------------- names for event ids --
-- Every catalogued event's name is generated at build time (domains/sound_event_names.lua, by the same search run
-- offline); any other id is searched here once (runtime/wwise_names.lua: about 40 ms) and cached for the session.
M.forward,M.backward,M.mul32=wwise_names.forward,wwise_names.backward,wwise_names.mul32
local found={}   -- id -> name, searched this session
function M.name_for(id)
    assert(type(id)=='number'and id%1==0 and id>0 and id<4294967296,'a Wwise event id is an integer from 1 to 2^32 - 1')
    local name=precomputed[id]or found[id]
    if name then return name end
    name=wwise_names.search(id)
    if name then found[id]=name end
    return name
end

------------------------------------------------------------------------------------------------- what to play --
-- The ui family: the loadout screen's events (domains/stratagem_selector.lua uiSound), by their keys.
local UI={}
for key,event in pairs(ui_sound.EVENTS)do UI['ui/'..key]=event end
M.UI=UI
-- event: a catalogue name ('sentry/gatling': its loop start; a shot entry: its shot event), 'ui/<key>', any Wwise
-- event name, or {id = <32-bit event id>}. Returns {name (what is posted), id, kind, label} or nil and why.
function M.resolve(event)
    if type(event)=='table'then
        local id=event.id
        if not(type(id)=='number'and id%1==0 and id>0 and id<4294967296)then
            return nil,'{id = ...} needs a 32-bit Wwise event id'
        end
        local name=M.name_for(id)
        if not name then return nil,('no name was found for event 0x%08X'):format(id)end
        return {name=name,id=id,kind='event',label=('event 0x%08X'):format(id)}
    end
    if type(event)~='string'or#event==0 or#event>128 or event:find('[%z\1-\31\127]')then
        return nil,'the event must be a sound name, a Wwise event name or {id = ...}'
    end
    if UI[event]then
        local e=UI[event]
        return {name=e.name,id=e.id or ui_sound.fnv1(e.name),kind='ui',label=e.label}
    end
    local canonical,entry=weapon_sounds.resolve(event)
    if entry then
        -- A loop's start event (entry.start; its stop is entry.stop), a shot's event (entry.event): big-endian hex.
        local hex=entry.kind=='loop'and entry.start or entry.event
        local id=type(hex)=='string'and tonumber(hex,16)or nil
        if not(id and id>0)then return nil,'the sound '..canonical..' has no event to post'end
        local name=M.name_for(id)
        if not name then return nil,('no name was found for the event of %s'):format(canonical)end
        return {name=name,id=id,kind=entry.kind,label=entry.label,sound=canonical,midi=entry.midi==1}
    end
    return {name=event,id=ui_sound.fnv1(event),kind='event',label=event}
end

---------------------------------------------------------------------------------------------------- posting --
local posts={}   -- owner -> {window start, count}
local function wwise()
    local S=rawget(_G,'stingray')
    local Wwise,WwiseWorld=S and S.Wwise,S and S.WwiseWorld
    if not(type(Wwise)=='table'and type(WwiseWorld)=='table'and engine_gui.callable(Wwise.wwise_world)
            and engine_gui.callable(Wwise.has_event)and engine_gui.callable(WwiseWorld.trigger_event))then
        return nil
    end
    return S,Wwise,WwiseWorld
end
-- The engine world to post on, or nil, code, why.
local function game_world()
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local proven,pwhy=selector.prove(world)
    if not proven then return nil,'UNSUPPORTED_BUILD',tostring(pwhy)end
    local w,wwhy=ui_sound.game_world(world)
    if not w then return nil,'NO_WORLD',tostring(wwhy)end
    return w
end
M.hooks={game_world=game_world,now=function()return events.now()end}

local Handle={};Handle.__index=Handle
-- Stops this playing instance (WwiseWorld.stop_event). true, or nil and why.
function Handle:stop()
    if self.state~='playing'then return nil,'the sound is '..tostring(self.state)end
    local _,Wwise,WwiseWorld=wwise()
    if not(Wwise and engine_gui.callable(WwiseWorld.stop_event))then return nil,'stingray.WwiseWorld.stop_event is unavailable'end
    local w,_,why=M.hooks.game_world()
    if not w then return nil,why end
    local ok,err=pcall(function()WwiseWorld.stop_event(Wwise.wwise_world(w),self.playing)end)
    if not ok then return nil,tostring(err)end
    self.state='stopped'
    return true
end
function Handle:describe()
    return {state=self.state,event=self.event,name=self.name,kind=self.kind,playing=self.playing,owner=self.owner}
end

-- Posts `event` for `owner`. opts: {position = {x, y, z} (a world position: a 3D sound there; else the world's own
-- default source)}. Returns a handle {state = 'playing', playing (the playing id), ...} or nil, code, why.
function M.play(owner,event,opts)
    opts=opts or{}
    if type(opts)~='table'then return nil,'INVALID','opts must be a table'end
    local spec,why=M.resolve(event)
    if not spec then return nil,'UNKNOWN_EVENT',why end
    local position=opts.position
    if position~=nil then
        local x,y,z=position[1]or position.x,position[2]or position.y,position[3]or position.z
        local function ok(n)return type(n)=='number'and n==n and math.abs(n)<1e6 end
        if not(ok(x)and ok(y)and ok(z))then return nil,'INVALID','position must be three finite numbers'end
        position={x,y,z}
    end
    local now=M.hooks.now()
    local rate=posts[owner]
    if not rate or now-rate.start>=M.RATE_WINDOW then rate={start=now,count=0};posts[owner]=rate end
    if rate.count>=M.RATE then return nil,'RATE_LIMITED','at most '..M.RATE..' sounds a second per mod'end
    local S,Wwise,WwiseWorld=wwise()
    if not S then return nil,'NO_API','stingray.Wwise / WwiseWorld are unavailable'end
    if position and not engine_gui.callable(S.Vector3)then return nil,'NO_API','stingray.Vector3 is unavailable'end
    local w,code,wwhy=M.hooks.game_world()
    if not w then return nil,code,wwhy end
    local okh,has=pcall(Wwise.has_event,spec.name)
    if not(okh and has==true)then
        return nil,'NO_EVENT','the sound engine does not know '..spec.label..' (its bank is not loaded)'
    end
    rate.count=rate.count+1
    local done,playing=engine_gui.temp_scope(function()
        if position then
            return WwiseWorld.trigger_event(Wwise.wwise_world(w),spec.name,S.Vector3(position[1],position[2],position[3]))
        end
        return WwiseWorld.trigger_event(Wwise.wwise_world(w),spec.name)
    end)
    if not done then return nil,'FAILED',tostring(playing)end
    if type(playing)~='number'or playing==0 then return nil,'NOT_PLAYED','the sound engine did not post it'end
    if log.sample('sound play '..tostring(owner)..' '..spec.name,3)then
        emit(('sound %s played by %s (%s); playing id %s'):format(spec.label,tostring(owner),spec.name,tostring(playing)))
    end
    return setmetatable({state='playing',playing=playing,event=type(event)=='string'and event or spec.label,
        name=spec.name,kind=spec.kind,owner=owner},Handle)
end
-- Whether the sound engine knows an event now (its bank is loaded): true / false, or nil and why.
function M.available(event)
    local spec,why=M.resolve(event)
    if not spec then return nil,why end
    local _,Wwise=wwise()
    if not Wwise then return nil,'stingray.Wwise is unavailable'end
    local ok,has=pcall(Wwise.has_event,spec.name)
    if not ok then return nil,tostring(has)end
    return has==true
end
function M.reset_for_tests()posts={}end
return M
