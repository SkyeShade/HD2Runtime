-- Game sound events a mod plays (hd2.sounds.play / stop / name_for; docs/sounds.md). Nothing here writes game memory.
--
-- The post is the Wwise plugin's own Lua API, the path runtime/ui_sound.lua proved for the loadout screen's sounds:
-- stingray.WwiseWorld.trigger_event(Wwise.wwise_world(world), name[, source]) on the game's own Game World
-- (ui_sound.game_world: the Application.worlds value at the Game World's position in the engine's world array). Every
-- binding's arguments are read from the plugin's code (bin/plugins/wwise_pluginw64_release.dll;
-- research/docs/wwise-plugin-bindings-F5FEE03DCFDB.md, research/wwise-plugin-F5FEE03DCFDB.json):
--   * trigger_event 0xD9C0: (WwiseWorld, name STRING, [source]): the name is strlen'd and hashed by 0xD4A70 (AK
--     GetIDFromString: FNV-1 32 of the lower-cased name; a number would be hashed as its decimal text); the source from
--     arg 3 by the resolver 0xA6C0: absent = the world's own default source (+0x4148; an explicit nil counts as present
--     and fails); a Unit (engine type test, a deleted unit refused) = that unit's own source; a Vector3 with an optional
--     Quaternion = a NEW position source for this post; a number = a source id. Returns the playing id (the plugin's own
--     counter, 0 when nothing was posted) and the resolved source id;
--   * stop_event 0xDB50: (WwiseWorld, playing id) stops that one instance (the plugin's counter map; unknown ids
--     ignored);
--   * set_source_parameter 0xD480: (WwiseWorld, source, name, value), set_switch 0xE4A0: (WwiseWorld, group, switch,
--     source), post_trigger 0xE6A0: (WwiseWorld, source, name): the source id is checked exactly (a stale id does
--     nothing); every name hashed as above. Called here only on a handle's OWN position source;
--   * pause_event 0xDC70 / resume_event 0xDDC0 / is_playing 0xE1A0: (WwiseWorld, engine playing id), looked up in the
--     plugin's record map keyed by the SOUND ENGINE's playing id (not the counter id trigger_event returns);
--     get_playing_elapsed 0xE2B0: (WwiseWorld (unread), engine playing id) -> milliseconds, no value when ended. The
--     engine id is read from the plugin's counter map right after this thread's own post (runtime/wwise_plugin.lua);
--   * has_event 0xD810: (name) whether the sound engine knows the event (its bank is loaded).
-- An event known only by its 32-bit id is posted through a name whose FNV-1 is that id (M.name_for: 'hd2runtime_' and
-- seven characters, generated at build time for every catalogued id).
-- Guards (the plugin checks no argument types): the world proven, the selector's pins (they cover the Game World
-- offsets), the API callable, the Game World matched, has_event true, a per-mod rate limit; a position and a rotation
-- are finite numbers; a unit is a userdata (the plugin type-tests it); an event whose actions would leave the sound
-- engine changed (domains/sound_events.lua `persistent`: a state, a global game parameter, a global mix change or
-- pause it does not undo) is refused. Engine-wide calls (set_state, set_global_parameter, stop_all, pause_all,
-- resume_all, set_environment, set_listener, set_language, load/unload_bank, set_enabled) are never made.
local world_module=require('hd2runtime/runtime/event_world')
local selector=require('hd2runtime/runtime/stratagem_selector')
local ui_sound=require('hd2runtime/runtime/ui_sound')
local weapon_sounds=require('hd2runtime/runtime/weapon_sounds')
local catalogue=require('hd2runtime/runtime/sound_catalogue')
local wwise_plugin=require('hd2runtime/runtime/wwise_plugin')
local engine_gui=require('hd2runtime/runtime/engine_gui')
local log=require('hd2runtime/runtime/log')
local events=require('hd2runtime/runtime/events')
local wwise_names=require('hd2runtime/runtime/wwise_names')
local KEY='HD2RuntimeSoundEventsV1'
local existing=rawget(_G,KEY)
if existing then return existing end
local M={}
rawset(_G,KEY,M)
M.RATE=32            -- posts and source calls per mod per RATE_WINDOW seconds
M.RATE_WINDOW=1
M.SOURCE_INVALID=4294967295

local function emit(message)pcall(log.emit,'[HD2Runtime] '..message)end

------------------------------------------------------------------------------------------- names for event ids --
-- Every catalogued id's name is generated at build time (domains/sound_event_names.lua, by the same search run
-- offline; loaded on first use); any other id is searched here once (runtime/wwise_names.lua: about 40 ms) and cached
-- for the session.
M.forward,M.backward,M.mul32=wwise_names.forward,wwise_names.backward,wwise_names.mul32
local found={}   -- id -> name, searched this session
local precomputed
function M.name_for(id)
    assert(type(id)=='number'and id%1==0 and id>0 and id<4294967296,'a Wwise id is an integer from 1 to 2^32 - 1')
    precomputed=precomputed or require('hd2runtime/domains/sound_event_names')
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
local function valid_name(s)return type(s)=='string'and#s>0 and#s<=128 and not s:find('[%z\1-\31\127]')end
-- The catalogue entry of a resolved event id (runtime/sound_catalogue.lua), recorded on the spec.
local function with_entry(spec)
    local name,entry=catalogue.by_id(spec.id)
    spec.event_name,spec.entry=name,entry
    return spec
end
-- event: a firing-sound name ('sentry/gatling': its loop start; a shot entry: its shot event), a sound event's catalogue
-- name, 'ui/<key>', any Wwise event name, or {id = <32-bit event id>}. Returns {name (what is posted), id, kind, label,
-- entry} or nil and why.
function M.resolve(event)
    if type(event)=='table'then
        local id=event.id
        if not(type(id)=='number'and id%1==0 and id>0 and id<4294967296)then
            return nil,'{id = ...} needs a 32-bit Wwise event id'
        end
        local name=M.name_for(id)
        if not name then return nil,('no name was found for event 0x%08X'):format(id)end
        return with_entry({name=name,id=id,kind='event',label=('event 0x%08X'):format(id)})
    end
    if not valid_name(event)then
        return nil,'the event must be a sound name, a Wwise event name or {id = ...}'
    end
    if UI[event]then
        local e=UI[event]
        return with_entry({name=e.name,id=e.id or ui_sound.fnv1(e.name),kind='ui',label=e.label})
    end
    local canonical,entry=weapon_sounds.resolve(event)
    if entry then
        -- A loop's start event (entry.start; its stop is entry.stop), a shot's event (entry.event): big-endian hex.
        local hex=entry.kind=='loop'and entry.start or entry.event
        local id=type(hex)=='string'and tonumber(hex,16)or nil
        if not(id and id>0)then return nil,'the sound '..canonical..' has no event to post'end
        local name=M.name_for(id)
        if not name then return nil,('no name was found for the event of %s'):format(canonical)end
        return with_entry({name=name,id=id,kind=entry.kind,label=entry.label,sound=canonical,midi=entry.midi==1})
    end
    local cname,centry=catalogue.resolve(event)
    if centry then
        local id=catalogue.id(centry)
        local name=centry.wwise or M.name_for(id)
        if not name then return nil,'no name was found for '..cname end
        return {name=name,id=id,kind=centry.kind,label=cname,sound=cname,event_name=cname,entry=centry}
    end
    return with_entry({name=event,id=ui_sound.fnv1(event),kind='event',label=event})
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
    local plugin,pluginwhy=wwise_plugin.prove(world)
    if not plugin then return nil,'UNSUPPORTED_BUILD',tostring(pluginwhy)end
    return w
end
-- The plugin's {state, Wwise playing id} of a counter id this thread just posted (runtime/wwise_plugin.lua), or nil
-- and why.
local function playing_entry(counter)
    local world,why=world_module.open()
    if not world then return nil,tostring(why)end
    return wwise_plugin.counter_entry(world,counter)
end
M.hooks={game_world=game_world,playing_entry=playing_entry,now=function()return events.now()end}
-- One unit of the owner's budget (`peek`: only whether one is left): true, or nil, 'RATE_LIMITED', why.
local function spend(owner,peek)
    local now=M.hooks.now()
    local rate=posts[owner]
    if not rate or now-rate.start>=M.RATE_WINDOW then rate={start=now,count=0};posts[owner]=rate end
    if rate.count>=M.RATE then return nil,'RATE_LIMITED','at most '..M.RATE..' sound calls a second per mod'end
    if not peek then rate.count=rate.count+1 end
    return true
end
local function finite(n)return type(n)=='number'and n==n and math.abs(n)<1e6 end

local Handle={};Handle.__index=Handle
M.Handle=Handle
-- The WwiseWorld binding `name` and the Game World's WwiseWorld for a handle call, or nil, code, why.
local function bound(self,name)
    if self.state~='playing'then return nil,'STOPPED','the sound is '..tostring(self.state)end
    local _,Wwise,WwiseWorld=wwise()
    if not(Wwise and engine_gui.callable(WwiseWorld[name]))then
        return nil,'NO_API','stingray.WwiseWorld.'..name..' is unavailable'
    end
    local w,code,why=M.hooks.game_world()
    if not w then return nil,code,why end
    local ok,ww=pcall(Wwise.wwise_world,w)
    if not(ok and ww~=nil)then return nil,'NO_WORLD','the Game World has no WwiseWorld'end
    return WwiseWorld,ww
end
-- Stops this playing instance (WwiseWorld.stop_event). true, or nil and why.
function Handle:stop()
    if self.state~='playing'then return nil,'the sound is '..tostring(self.state)end
    local WwiseWorld,ww,why=bound(self,'stop_event')
    if not WwiseWorld then return nil,why or ww end
    local ok,err=pcall(WwiseWorld.stop_event,ww,self.playing)
    if not ok then return nil,tostring(err)end
    self.state='stopped'
    return true
end
function Handle:describe()
    return {state=self.state,event=self.event,name=self.name,kind=self.kind,playing=self.playing,owner=self.owner,
        source=self.source_kind,own_source=self.source_kind=='position',controls=self.wwise~=nil,
        controls_reason=self.wwise==nil and self.id_why or nil}
end
-- The sound engine's own playing id of this sound (read from the plugin right after the post), or nil, code, why.
local function engine_id(self)
    if self.wwise then return self.wwise end
    return nil,'UNPROVEN_ID',self.id_why or"the sound engine's playing id of this sound is unknown"
end
-- handle:pause() / handle:resume(): pauses / resumes this one instance (WwiseWorld.pause_event / resume_event(world,
-- playing id): the plugin's record of exactly this instance). true, or nil, code, why.
local function pause_resume(self,binding)
    local id,code,why=engine_id(self)
    if not id then return nil,code,why end
    local WwiseWorld,ww,bwhy=bound(self,binding)
    if not WwiseWorld then return nil,ww,bwhy end
    local spent,rcode,rwhy=spend(self.owner)
    if not spent then return nil,rcode,rwhy end
    local done,err=pcall(WwiseWorld[binding],ww,id)
    if not done then return nil,'FAILED',tostring(err)end
    self.paused=binding=='pause_event'
    return true
end
function Handle:pause()return pause_resume(self,'pause_event')end
function Handle:resume()return pause_resume(self,'resume_event')end
-- handle:is_playing(): whether the sound engine still plays this instance (WwiseWorld.is_playing(world, playing id);
-- it turns false up to one update after the sound ends). false once stopped; nil, code, why when it cannot be asked.
function Handle:is_playing()
    if self.state~='playing'then return false end
    local id,code,why=engine_id(self)
    if not id then return nil,code,why end
    local WwiseWorld,ww,bwhy=bound(self,'is_playing')
    if not WwiseWorld then return nil,ww,bwhy end
    local done,playing=pcall(WwiseWorld.is_playing,ww,id)
    if not done then return nil,'FAILED',tostring(playing)end
    return playing==true
end
-- handle:elapsed(): seconds this instance has played (WwiseWorld.get_playing_elapsed(world, playing id): the sound
-- engine's play position, in milliseconds), or nil, code, why (nil, 'ENDED' when the engine no longer knows it).
function Handle:elapsed()
    local id,code,why=engine_id(self)
    if not id then return nil,code,why end
    local WwiseWorld,ww,bwhy=bound(self,'get_playing_elapsed')
    if not WwiseWorld then return nil,ww,bwhy end
    local done,ms=pcall(WwiseWorld.get_playing_elapsed,ww,id)
    if not done then return nil,'FAILED',tostring(ms)end
    if type(ms)~='number'or ms~=ms then return nil,'ENDED','the sound engine no longer plays it'end
    return ms/1000
end
-- A source call on this handle's OWN source (a position post's): refused for the world's default source and a unit's
-- source, which the game's own sounds share.
local function own_source(self)
    if self.source_kind~='position'or not self.source then
        return nil,'SHARED_SOURCE','only a sound posted at a position has a source of its own (this one plays on '
            ..(self.source_kind=='unit'and'the unit\'s source'or'the game world\'s default source')..')'
    end
    return true
end
-- A name the sound engine hashes for `value` (a name or {id = n}) of catalogue kind `kind`, or nil, code, why.
local function engine_name(value,kind,group)
    if type(value)=='table'then
        local id=value.id
        if not(type(id)=='number'and id%1==0 and id>0 and id<4294967296)then
            return nil,'INVALID','{id = ...} needs a 32-bit id'
        end
        local _,own=catalogue.lookup(kind,value,group)
        local name=own or M.name_for(id)
        if not name then return nil,'INVALID',('no name was found for 0x%08X'):format(id)end
        return name,ui_sound.fnv1(name)
    end
    if not valid_name(value)then return nil,'INVALID','a name or {id = ...} is required'end
    return value,ui_sound.fnv1(value)
end
M.engine_name=engine_name
-- handle:set_parameter(parameter, value): sets a game parameter (RTPC) on this sound's own source
-- (WwiseWorld.set_source_parameter(world, source, name, value)); only this sound's source changes. parameter: a name
-- ('rounds_fired', or one of hd2.sounds.parameters()) or {id = n}. true, or nil, code, why.
function Handle:set_parameter(parameter,value)
    local ok,code,why=own_source(self)
    if not ok then return nil,code,why end
    if not finite(value)then return nil,'INVALID','the value must be a finite number'end
    local name,ncode,nwhy=engine_name(parameter,'parameters')
    if not name then return nil,ncode,nwhy end
    local WwiseWorld,ww,bwhy=bound(self,'set_source_parameter')
    if not WwiseWorld then return nil,ww,bwhy end
    local spent,rcode,rwhy=spend(self.owner)
    if not spent then return nil,rcode,rwhy end
    local done,err=pcall(WwiseWorld.set_source_parameter,ww,self.source,name,value)
    if not done then return nil,'FAILED',tostring(err)end
    return true
end
-- handle:set_switch(group, switch): sets a switch on this sound's own source (WwiseWorld.set_switch(world, group,
-- switch, source)). Names or {id = n}. true, or nil, code, why.
function Handle:set_switch(group,switch)
    local ok,code,why=own_source(self)
    if not ok then return nil,code,why end
    local gname,gid_or_code,gwhy=engine_name(group,'switchGroups')
    if not gname then return nil,gid_or_code,gwhy end
    local sname,scode,swhy=engine_name(switch,'switchGroups',('%08X'):format(gid_or_code))
    if not sname then return nil,scode,swhy end
    local WwiseWorld,ww,bwhy=bound(self,'set_switch')
    if not WwiseWorld then return nil,ww,bwhy end
    local spent,rcode,rwhy=spend(self.owner)
    if not spent then return nil,rcode,rwhy end
    local done,err=pcall(WwiseWorld.set_switch,ww,gname,sname,self.source)
    if not done then return nil,'FAILED',tostring(err)end
    return true
end
-- handle:post_trigger(trigger): posts a Wwise trigger on this sound's own source (WwiseWorld.post_trigger(world,
-- source, name); a trigger cues music stingers on that source only). A name or {id = n}. true, or nil, code, why.
function Handle:post_trigger(trigger)
    local ok,code,why=own_source(self)
    if not ok then return nil,code,why end
    local name,ncode,nwhy=engine_name(trigger,'triggers')
    if not name then return nil,ncode,nwhy end
    local WwiseWorld,ww,bwhy=bound(self,'post_trigger')
    if not WwiseWorld then return nil,ww,bwhy end
    local spent,rcode,rwhy=spend(self.owner)
    if not spent then return nil,rcode,rwhy end
    local done,err=pcall(WwiseWorld.post_trigger,ww,self.source,name)
    if not done then return nil,'FAILED',tostring(err)end
    return true
end

-- The source argument of a post from opts: nil (the world's default source), or {kind, args...}; or nil, code, why.
local function source_of(S,opts)
    local position,rotation,unit=opts.position,opts.rotation,opts.unit
    if unit~=nil then
        if position~=nil or rotation~=nil then return nil,'INVALID','unit and position are exclusive'end
        if type(unit)~='userdata'then return nil,'INVALID','unit must be an engine Unit'end
        return {kind='unit',unit}
    end
    if rotation~=nil and position==nil then return nil,'INVALID','a rotation needs a position'end
    if position==nil then return nil end
    if type(position)~='table'then return nil,'INVALID','position must be three finite numbers'end
    local x,y,z=position[1]or position.x,position[2]or position.y,position[3]or position.z
    if not(finite(x)and finite(y)and finite(z))then return nil,'INVALID','position must be three finite numbers'end
    if not engine_gui.callable(S.Vector3)then return nil,'NO_API','stingray.Vector3 is unavailable'end
    local q
    if rotation~=nil then
        if type(rotation)~='table'then return nil,'INVALID','rotation must be four finite numbers'end
        local qx,qy,qz,qw=rotation[1]or rotation.x,rotation[2]or rotation.y,rotation[3]or rotation.z,
            rotation[4]or rotation.w
        if not(finite(qx)and finite(qy)and finite(qz)and finite(qw))then
            return nil,'INVALID','rotation must be four finite numbers'
        end
        local n=math.sqrt(qx*qx+qy*qy+qz*qz+qw*qw)
        if n<1e-6 then return nil,'INVALID','rotation must be a non-zero quaternion'end
        if not(type(S.Quaternion)=='table'and engine_gui.callable(S.Quaternion.from_elements))then
            return nil,'NO_API','stingray.Quaternion.from_elements is unavailable'
        end
        q={qx/n,qy/n,qz/n,qw/n}
    end
    return {kind='position',position={x,y,z},rotation=q}
end

-- Posts `event` for `owner`. opts: {position = {x, y, z} (a 3D sound at that world position, on a new source of its
-- own), rotation = {x, y, z, w} (a quaternion; with a position), unit = <engine Unit> (the unit's own source: the sound
-- follows the unit)}; none of them: the world's own default source. Returns a handle {state = 'playing', playing (the
-- playing id), source, ...} or nil, code, why.
function M.play(owner,event,opts)
    opts=opts or{}
    if type(opts)~='table'then return nil,'INVALID','opts must be a table'end
    local spec,why=M.resolve(event)
    if not spec then return nil,'UNKNOWN_EVENT',why end
    if spec.entry and spec.entry.persistent then
        return nil,'GLOBAL_EVENT',(spec.event_name or spec.label)..' would leave the sound engine changed ('
            ..table.concat(spec.entry.effects or{},', ')..')'
    end
    local S,Wwise,WwiseWorld=wwise()
    local source,scode,swhy
    if S then
        source,scode,swhy=source_of(S,opts)
        if scode then return nil,scode,swhy end
    else
        local _,c,w=source_of({Vector3=function()end,Quaternion={from_elements=function()end}},opts)
        if c=='INVALID'then return nil,c,w end
    end
    local spent,rcode,rwhy=spend(owner,true)
    if not spent then return nil,rcode,rwhy end
    if not S then return nil,'NO_API','stingray.Wwise / WwiseWorld are unavailable'end
    local w,code,wwhy=M.hooks.game_world()
    if not w then return nil,code,wwhy end
    local okh,has=pcall(Wwise.has_event,spec.name)
    if not(okh and has==true)then
        return nil,'NO_EVENT','the sound engine does not know '..spec.label..' (its bank is not loaded)'
    end
    spend(owner)
    local done,playing,source_id=engine_gui.temp_scope(function()
        local ww=Wwise.wwise_world(w)
        if source and source.kind=='unit'then
            return WwiseWorld.trigger_event(ww,spec.name,source[1])
        elseif source then
            local p=source.position
            local v=S.Vector3(p[1],p[2],p[3])
            if source.rotation then
                local q=source.rotation
                return WwiseWorld.trigger_event(ww,spec.name,v,S.Quaternion.from_elements(q[1],q[2],q[3],q[4]))
            end
            return WwiseWorld.trigger_event(ww,spec.name,v)
        end
        return WwiseWorld.trigger_event(ww,spec.name)
    end)
    if not done then return nil,'FAILED',tostring(playing)end
    if type(playing)~='number'or playing==0 then return nil,'NOT_PLAYED','the sound engine did not post it'end
    if log.sample('sound play '..tostring(owner)..' '..spec.name,3)then
        emit(('sound %s played by %s (%s); playing id %s'):format(spec.label,tostring(owner),spec.name,tostring(playing)))
    end
    local valid_source=type(source_id)=='number'and source_id%1==0 and source_id>0 and source_id<M.SOURCE_INVALID
    -- The sound engine's playing id, read now (the self-check: only a post made synchronously on this thread).
    local wwise,id_why
    local entry,ewhy=M.hooks.playing_entry(playing)
    if not entry then
        id_why="the plugin's record of this post is unreadable: "..tostring(ewhy)
    elseif entry.state==wwise_plugin.STATES.posted and entry.id>0 then
        wwise=entry.id
    elseif entry.state==wwise_plugin.STATES.sharedJoined or entry.state==wwise_plugin.STATES.sharedStarted then
        id_why='this sound shares one engine instance with other posts'
    elseif entry.state==wwise_plugin.STATES.queued then
        id_why="the post was queued for the plugin's own thread"
    else
        id_why='the sound engine has not started it yet (state '..tostring(entry.state)..')'
    end
    return setmetatable({state='playing',playing=playing,event=type(event)=='string'and event or spec.label,
        name=spec.name,kind=spec.kind,owner=owner,source_kind=source and source.kind or'world',
        source=valid_source and source_id or nil,wwise=wwise,id_why=id_why,posted=M.hooks.now(),
        duration=spec.entry and spec.entry.duration or nil},Handle)
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
function M.reset_for_tests()posts={};found={}end
return M
