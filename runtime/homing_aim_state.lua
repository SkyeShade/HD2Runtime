-- Pre-fire homing support, extracted from the user-tested AR-23 Homing Lab 0.4.1.
-- The generic Runtime integration is not yet live-tested.
-- Read-only native Aim action (group 2, index 8). Layout: Runtime .40 input_bindings;
-- action identity/state byte: C4 Quick Actions 1.13.1 AimInputState.read and catalog
-- input_aim_action=0x800000002 / input_aim_code=0x20008. Layout is independently pinned by Runtime .40.
-- Not an OS RMB/pad query. In-game remaps resolve before this state is read.
-- This is action activation, not proof of a particular animation/ADS camera.
local L=require('hd2runtime/domains/input_bindings')
local M={};local proven
local function read(world)
    if not world or not world.key or not world.game or not world.view then return nil,'aim_state_unavailable'end
    local v=world.view
    if not proven or proven.key~=world.key then
        local ok=true
        for _,pin in ipairs(L.pins)do
            if v.proves(world.game+pin.rva,pin.bytes)~=true then ok=false;break end
        end
        proven={key=world.key,ok=ok}
    end
    if not proven.ok then return nil,'aim_input_code_changed'end
    local owner=v.pointer(world.game+L.ownerGlobal)
    if not owner then return nil,'aim_input_owner_unavailable'end
    local bytes=v.read(owner+L.state+L.stateStride*(2*L.actionsPerGroup+8),1)
    if type(bytes)~='string' or #bytes~=1 or bytes:byte()>1 then return nil,'aim_state_unavailable'end
    if v.pointer(world.game+L.ownerGlobal)~=owner then return nil,'aim_input_owner_changed'end
    return bytes:byte()==1,'native_aim_action_2_8'
end
function M.active(world)
    local ok,value,why=pcall(read,world)
    if not ok then return nil,'aim_state_read_failed'end
    return value,why
end
return M
