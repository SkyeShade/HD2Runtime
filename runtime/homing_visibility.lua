-- Pre-fire homing support, extracted from the user-tested AR-23 Homing Lab 0.4.1.
-- The generic Runtime integration is not yet live-tested.
-- Read-only menu gate. UI stack constants are from Mod Options Menu v1.2
-- src/view.lua, verified there for build 25480438 (same SHA256s as Runtime .40).
-- Called only with event_world.open()'s fingerprint-proven game.dll base.
-- This is independent of HUD z ordering and never changes acquisition.
local M={}
local UI_STATE,STACK,ENTRIES,ESCAPE=0x347ce28,0x429c,5,1
local function u32(s,i)
    local a,b,c,d=s:byte(i+1,i+4)
    return a and d and(a+b*256+c*65536+d*16777216)or nil
end
local function cursor_visible()
    local S=rawget(_G,'stingray');local W=type(S)=='table'and S.Window
    local f=type(W)=='table'and W.show_cursor
    if f then local ok,value=pcall(f);return ok and value==true end
    return false
end
local function player_context(world)
    local W=require('hd2runtime/runtime/event_world')
    local game=W.game_state(world)
    if not game or game.mission~=true then return true,'mission_required'end
    local dropping,drop_reason,drop=require('hd2runtime/runtime/homing_drop_state').active(world)
    if dropping~=false then return true,drop_reason or'hellpod_state_unavailable',drop end
    local players=W.players(world,true)
    if type(players)~='table'then return true,'local_player_unavailable'end
    local player
    for _,p in ipairs(players)do if p['local']==true then
        if player then return true,'local_player_ambiguous'end
        player=p
    end end
    if not player or not player.avatar then return true,'local_avatar_unavailable'end
    if player.lifecycle~=3 then return true,'player_not_spawned'end
    local health=W.entity_state(world,player.avatar)
    if not health or health.life~=0 or not health.descriptor or health.descriptor.owned~=true then
        return true,'local_avatar_not_alive'
    end
    local flags,why=require('hd2runtime/runtime/player_equipment').avatar_flags(world,player.avatar)
    if not flags then return true,why or'avatar_flags_unavailable'end
    if flags.tactical_map then return true,'tactical_map'end
    if flags.weapon_menu then return true,'weapon_menu'end
    if not flags.alive then return true,'local_avatar_not_alive'end
    if flags.seated then return true,'avatar_seated'end
    return false,nil,drop
end
local function read(world,aim_only)
    local ok,settings=pcall(require,'hd2runtime/runtime/runtime_settings')
    if ok and type(settings.visible)=='function'then
        local got,shown=pcall(settings.visible)
        if got and shown==true then return true,'runtime_settings'end
    end
    -- Also conservatively hide over a map/terminal/other UI exposing its cursor.
    -- Cursor visibility is not used as proof that a specific menu is open.
    if cursor_visible()then return true,'cursor_visible'end
    if not world then
        local W=require('hd2runtime/runtime/event_world');world=W.open()
    end
    if not world or not world.game or not world.view then return true,'menu_state_unavailable'end
    local p=world.view.pointer(world.game+UI_STATE)
    local bytes=p and world.view.read(p+STACK,4*(ENTRIES+1))
    if type(bytes)~='string'or#bytes~=24 then return true,'menu_state_unavailable'end
    local depth=u32(bytes,4*ENTRIES)
    if not depth or depth>ENTRIES then return true,'menu_state_unavailable'end
    for i=0,depth-1 do if u32(bytes,i*4)==ESCAPE then return true,'escape_menu'end end
    local hidden,why,drop=player_context(world)
    if hidden then return true,why,drop end
    if aim_only~=false then
        local aiming,why=require('hd2runtime/runtime/homing_aim_state').active(world)
        if aiming~=true then return true,aiming==false and'not_aiming'or(why or'aim_state_unavailable'),drop end
    end
    return false,nil,drop
end
function M.blocked(world,aim_only)
    local ok,hidden,why,drop=pcall(read,world,aim_only)
    if not ok then return true,'menu_state_unavailable'end
    return hidden,why,drop
end
return M
