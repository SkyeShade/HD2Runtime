-- Private, read-only HUD admission from the actual HellpodComponent manager.
-- Lead: same-build Vanilla Plus / HellpodDropHold v1.2 drop_hold.lua.
-- Global, array/hash layout, owner bit and network phase instructions were
-- independently inspected in the retained unpacked game.dll. Pins are checked
-- again in the fingerprint-proven event world; no FOV/lifecycle/timer heuristic.
local b=require('hd2runtime/core/bytes')
local W=require('hd2runtime/runtime/event_world')
local M={}
local GLOBAL=0x3326D58
local TYPES={E58163E71928D3E2='initial',EF9EB729A9D6D849='reinforcement'}
local PINS={
    {rva=0x92E7B8,hex="413b4730"}, -- active iteration bound
    {rva=0x568CF3,hex="4889055ee0db02"}, -- Hellpod manager global store
    {rva=0x53922E,hex="8b772c3b7748"}, -- total count and entity map capacity
    {rva=0x539241,hex="3b7724"}, -- allocated capacity
    {rva=0x53927C,hex="488b4758488d4f40448bc648892c038b5508"}, -- record pointers and entity key
    {rva=0x92AAE7,hex="448b4d488bd6448b5550440fafd0418d79ff4585c97436"}, -- entity map capacity and multiplier
    {rva=0x92AAFE,hex="4c8b5d408b5d4c"}, -- entity map buckets and empty key
    {rva=0x92B8A0,hex="4d8b67708bc8498b475848894df84c8965d84c8d2c89488b3cc84c8d348949c1e5054d036f68"}, -- network array, descriptor array, 20-byte network and 160-byte local strides
    {rva=0x92B8E9,hex="438b0cb4413b4d000f842502000083f9010f850c050000"}, -- network phase read and braking branch
    {rva=0x92C32E,hex="f6411401"}, -- owned descriptor bit
    {rva=0x92D3CC,hex="42c704b002000000"}, -- landed phase write
}
local proven
local function pointer(p)return type(p)=='number'and p>=65536 and p<0x800000000000 and p%1==0 end
local function power_of_two(n)
    if not n or n<1 or n>65536 then return false end
    while n>1 do if n%2~=0 then return false end;n=n/2 end
    return true
end
local function read(world)
    if not world or not world.key or not world.game or not world.view then return nil,'hellpod_state_unavailable'end
    local v=world.view
    if not proven or proven.key~=world.key then
        local ok=true
        for _,p in ipairs(PINS)do if v.proves(world.game+p.rva,p.hex)~=true then ok=false;break end end
        proven={key=world.key,ok=ok}
    end
    if not proven.ok then return nil,'hellpod_code_changed'end
    local manager=v.pointer(world.game+GLOBAL)
    if not pointer(manager)then return nil,'hellpod_manager_unavailable'end
    local header=v.read(manager+36,84)
    if type(header)~='string'or#header~=84 then return nil,'hellpod_header_unavailable'end
    local capacity,total,count=b.u32(header,0),b.u32(header,8),b.u32(header,12)
    if capacity>4096 or total>capacity or count>total then return nil,'hellpod_header_invalid'end
    -- Normal play has few player/support pods. Refuse excess work instead of
    -- interpreting an incomplete scan as absence of a local dropping pod.
    if count>64 then return nil,'hellpod_scan_budget',{state='unknown',count=count}end
    local details={state='none',count=count}
    local function stable()
        return v.pointer(world.game+GLOBAL)==manager and v.read(manager+36,84)==header
    end
    if count==0 then
        if not stable()then return nil,'hellpod_manager_changed'end
        return false,'no_active_player_drop',details
    end
    local records,nets=b.pointer(header,52),b.pointer(header,76)
    local map,slots,empty,mult=b.pointer(header,28),b.u32(header,36),b.u32(header,40),b.u32(header,44)
    if not pointer(records)or not pointer(nets)or not pointer(map)or not power_of_two(slots)then
        return nil,'hellpod_header_invalid'
    end
    local function map_index(entity)
        local start=W.mul32(entity,mult)
        for probe=0,math.min(slots,64)-1 do
            local raw=v.read(map+((start+probe)%slots)*8,8)
            if type(raw)~='string'or#raw~=8 then return nil end
            local key=b.u32(raw,0)
            if key==entity then return b.u32(raw,4)end
            if key==empty then return nil end
        end
    end
    for i=0,count-1 do
        local desc=v.pointer(records+i*8)
        local raw=pointer(desc)and v.read(desc,24)
        if type(raw)~='string'or#raw~=24 then return nil,'hellpod_record_unavailable'end
        local kind=string.format('%08X%08X',b.u32(raw,4),b.u32(raw,0))
        if TYPES[kind]and b.u32(raw,20)%2==1 then
            local entity=b.u32(raw,8)
            if W.entity_exists(world,entity)~=true or map_index(entity)~=i then return nil,'hellpod_identity_changed'end
            local at=nets+i*20
            local bytes=v.read(at,4)
            if type(bytes)~='string'or#bytes~=4 then return nil,'hellpod_phase_unavailable'end
            local phase=b.u32(bytes,0)
            if phase>2 then return nil,'hellpod_phase_unknown'end
            if v.pointer(records+i*8)~=desc or v.read(desc,24)~=raw or v.read(at,4)~=bytes
                or map_index(entity)~=i or W.entity_exists(world,entity)~=true or not stable()then
                return nil,'hellpod_identity_changed'
            end
            details={state=phase==0 and'falling'or(phase==1 and'braking'or'landed'),
                entity=entity,type=TYPES[kind],phase=phase,count=count}
            if phase<2 then return true,'hellpod_'..details.state,details end
        end
    end
    if not stable()then return nil,'hellpod_manager_changed'end
    return false,'no_active_player_drop',details
end
function M.active(world)
    local ok,value,why,details=pcall(read,world)
    if not ok then return nil,'hellpod_state_read_failed',{state='unknown'}end
    return value,why,details or{state='unknown'}
end
return M
