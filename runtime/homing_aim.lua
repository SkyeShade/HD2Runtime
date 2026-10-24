-- Pre-fire homing support, extracted from the user-tested AR-23 Homing Lab 0.4.1.
-- The generic Runtime integration is not yet live-tested.
-- Read-only internal HD2Runtime 0.40 event_world adapter. Supply a world returned
-- by event_world.open(), which performs the build/pin checks. This module makes
-- no native calls and writes no game memory. Loading it does not open the world.
-- unit_pose is the weapon ROOT (+Y forward), not a verified muzzle/camera pose.
local M={}
local function id(n) return type(n)=='number' and n>0 and n<4294967296 and n%1==0 end
local function number(n) return type(n)=='number' and n==n and math.abs(n)<=100000 end
local function vector(v)
    if type(v)~='table' or not number(v.x) or not number(v.y) or not number(v.z) then return nil end
    return {x=v.x,y=v.y,z=v.z}
end
local function solo_player(W,world)
    local players=W.players(world,true)
    if type(players)~='table' or #players~=1 then return nil,'solo_required' end
    local player=players[1]
    if player['local']~=true or not id(player.avatar) or type(player.peer)~='string' then
        return nil,'local_avatar_unavailable'
    end
    if W.entity_exists(world,player.avatar)~=true then return nil,'avatar_unavailable' end
    return player
end
local function capture(world,sources)
    if type(world)~='table' or type(world.view)~='table' or type(world.key)~='string' then
        return nil,'world_unavailable'
    end
    local W=require('hd2runtime/runtime/event_world')
    local game=W.game_state(world)
    if not game or game.mission~=true then return nil,'mission_required' end
    if game.host~=true then return nil,'host_required' end
    if not id(game.mode_entity) then return nil,'mission_identity_unavailable' end
    local player,reason=solo_player(W,world)
    if not player then return nil,reason end
    local held=W.equipped(world,player.avatar)
    if not held then return nil,'equipped_unavailable' end
    if not sources[held.type] or not id(held.entity) then return nil,'configured_weapon_not_held' end
    local unit=W.entity_unit(world,held.entity)
    if not id(unit) then return nil,'weapon_unit_unavailable' end
    local pose=W.unit_pose(world,unit)
    local origin=pose and vector(pose.position)
    local forward=pose and vector(pose.forward)
    if not origin or not forward then return nil,'weapon_pose_unavailable' end
    local length2=forward.x^2+forward.y^2+forward.z^2
    if length2<.98 or length2>1.02 then return nil,'weapon_forward_invalid' end
    local length=math.sqrt(length2)
    forward.x,forward.y,forward.z=forward.x/length,forward.y/length,forward.z/length
    -- A slot switch or destroyed/replaced unit during these reads invalidates the pose.
    local again=W.equipped(world,player.avatar)
    if not again or again.entity~=held.entity or again.type~=held.type
        or W.entity_unit(world,held.entity)~=unit then return nil,'held_weapon_changed' end
    local current=W.game_state(world)
    local owner=solo_player(W,world)
    if not current or current.mission~=true or current.host~=true or current.mode_entity~=game.mode_entity
        or not owner or owner.avatar~=player.avatar or owner.peer~=player.peer then
        return nil,'session_changed'
    end
    return {origin=origin,forward=forward,weapon_id=held.entity,avatar_id=player.avatar,weapon_unit=unit,
        avatar_unit=W.entity_unit(world,player.avatar),
        session_key=world.key..':'..tostring(game.mode_entity)..':'..player.peer..':'..tostring(player.avatar),
        aim_basis='weapon_root',muzzle_and_screen_verified=false}
end
function M.capture(world,sources)
    local ok,value,reason=pcall(capture,world,sources)
    if not ok then return nil,'aim_read_failed' end
    return value,reason
end

-- No supported .40 LOS API: use the separately pinned read-only native query.
-- Missing modules/identity/proof remain unknown; never a synthetic clear result.
local los
function M.visible(world,origin,target_position,current,target_unit)
    if not los then
        local ok,L=pcall(require,'hd2runtime/runtime/homing_los')
        if not ok then return nil,'los_unavailable'end
        local got,N=pcall(require,'hd2runtime/runtime/homing_los_native')
        los=L.new({read=got and N.read or nil})
    end
    return los:visible(world,origin,target_position,{target_unit=target_unit,
        avatar_unit=current and current.avatar_unit,weapon_unit=current and current.weapon_unit})
end
return M
