-- Native UI sounds through the engine's Wwise Lua API (development only; docs/custom-stratagems.md, "The selection
-- sound"). Not exported by api/hd2.lua and no public field reaches it. Nothing here writes game memory.
--
-- The loadout screen posts its sounds through game.dll 0x1327F50(key): the key is remapped to a Wwise event id and posted
-- on the WwiseWorld of the "Game World" ([[game+context]+0x10F8]; the world at +0x10E8). The Wwise plugin exposes the
-- same post to Lua: stingray.WwiseWorld.trigger_event(stingray.Wwise.wwise_world(world), name) posts the FNV-1
-- (lower-case) hash of the name, so a name whose hash equals a native event id posts that very event (domains/
-- stratagem_selector.lua uiSound: the picker-close and slot-select events by such names; two real UI event names).
-- The plugin's bindings check no arguments (a wrong world crashes natively; pcall cannot catch it), so every call is
-- guarded: the selector's pinned code; aboard the ship (the ui_ship bank); the API callable; the world passed is the
-- Application.worlds value at the game's own Game World's position in the engine's world array; Wwise.has_event true.
local world_module=require('hd2runtime/runtime/event_world')
local selector=require('hd2runtime/runtime/stratagem_selector')
local log_module=require('hd2runtime/runtime/log')
local engine_gui=require('hd2runtime/runtime/engine_gui')
local overlay=require('hd2runtime/runtime/stratagem_slot_overlay')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/stratagem_selector')
local U=D.uiSound
local M={}
M.EVENTS=U.events

local function log(text)log_module.emit('[HD2Runtime] ui sound '..text)end
local function qword(world,at)
    local s=at and world.view.read(at,8)
    return s and b.u32(s,0)+b.u32(s,4)*4294967296
end

local function xor8(a,c)
    local r,p=0,1
    for _=1,8 do
        if a%2~=c%2 then r=r+p end
        a,c,p=math.floor(a/2),math.floor(c/2),p*2
    end
    return r
end
-- The FNV-1 32-bit hash Wwise derives an event id from (AK GetIDFromString: lower-case A-Z only):
-- h = h * 0x1000193 mod 2^32 (exactly: h * 0x193 + (h mod 256) * 2^24), then h xor the character.
function M.fnv1(name)
    local h=0x811C9DC5
    for i=1,#name do
        local c=name:byte(i)
        if c>=65 and c<=90 then c=c+32 end
        h=(h*0x193+(h%256)*16777216)%4294967296
        local low=h%256
        h=h-low+xor8(low,c)
    end
    return h
end

-- The engine's World value of the game's own Game World, or nil and why: matched by its position in the engine's world
-- array (Application.worlds lists it in order; worlds are full userdata, not their pointers). Read-only.
function M.game_world(world)
    local context=world.view.pointer(world.game+U.context)
    local game_world=context and qword(world,context+U.world)
    local wwise_world=context and qword(world,context+U.wwiseWorld)
    if not(game_world and game_world~=0 and wwise_world and wwise_world~=0)then
        return nil,'the game has no Game World with a WwiseWorld'
    end
    return overlay.world_value(world,game_world)
end

-- What a post would use, without posting anything: the API, the Game World match and each event's has_event.
function M.status()
    local world,why=world_module.open()
    if not world then return'no game world: '..tostring(why)end
    local S=rawget(_G,'stingray')
    local Wwise,WwiseWorld=S and S.Wwise,S and S.WwiseWorld
    local api=type(Wwise)=='table'and type(WwiseWorld)=='table'and engine_gui.callable(Wwise.wwise_world)
        and engine_gui.callable(Wwise.has_event)and engine_gui.callable(WwiseWorld.trigger_event)
    local w,world_why=M.game_world(world)
    local parts={}
    for _,key in ipairs({'picker_close','slot_select','generic_select','item_hover_select'})do
        local event=U.events[key]
        local ok,has=false,nil
        if api then ok,has=pcall(Wwise.has_event,event.name)end
        parts[#parts+1]=('%s has_event %s'):format(key,ok and tostring(has)or'?')
    end
    return('Wwise API %s; Game World %s; %s'):format(api and'present'or'MISSING',w and'matched'or('NOT matched: '
        ..tostring(world_why)),table.concat(parts,', '))
end

-- Posts one native UI event (a key of M.EVENTS). Returns {status = 'played', event, name, playing, source} or nil, code,
-- reason (refused: nothing called).
function M.play(key)
    local event=U.events[key]
    if not event then return nil,'UNKNOWN_EVENT','no UI event '..tostring(key)end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local proven,proof_why=selector.prove(world)
    if not proven then return nil,'UNSUPPORTED_BUILD',tostring(proof_why)end
    local game=world_module.game_state(world)
    if not game then return nil,'UNAVAILABLE','the game state is unreadable'end
    if game.mission then return nil,'IN_MISSION','the UI sounds are played aboard the ship (their bank)'end
    if event.id and M.fnv1(event.name)~=event.id then return nil,'BAD_NAME','the name does not hash to the event id'end
    local S=rawget(_G,'stingray')
    local Wwise,WwiseWorld=S and S.Wwise,S and S.WwiseWorld
    if not(type(Wwise)=='table'and type(WwiseWorld)=='table'and engine_gui.callable(Wwise.wwise_world)
            and engine_gui.callable(Wwise.has_event)and engine_gui.callable(WwiseWorld.trigger_event))then
        return nil,'NO_API','stingray.Wwise / WwiseWorld are unavailable'
    end
    local w,world_why=M.game_world(world)
    if not w then return nil,'NO_WORLD',world_why end
    local ok,has=pcall(Wwise.has_event,event.name)
    if not(ok and has==true)then return nil,'NO_EVENT','the event is not known to the sound engine: '..event.name end
    local done,playing,source=pcall(function()return WwiseWorld.trigger_event(Wwise.wwise_world(w),event.name)end)
    if not done then return nil,'FAILED',tostring(playing)end
    if type(playing)~='number'or playing==0 then return nil,'NOT_PLAYED','the sound engine did not post it'end
    log(('PLAYED %s: %s (%s%s) on the Game World\'s WwiseWorld; playing id %s'):format(key,event.label,event.name,
        event.id and(', event id 0x%08X'):format(event.id)or'',tostring(playing)))
    return {status='played',event=key,name=event.name,playing=playing,source=source}
end
return M
