-- THE ONGOING PROBE (development, READ-ONLY; the user's request of 2026-10-07): which game data drives the HUD's
-- "Ongoing" countdown of a called stratagem (a carrier's, so a custom Pelican or a custom barrage shows its carrier's
-- time). Nothing in the research maps it yet (the leads: the HUD slot's unmapped float +0x371C between the inbound left
-- +0x3718 and the cooldown left +0x3720; the record entry's unknown 8 bytes +0x28; the arrival +0x20 itself; the
-- beacon's countdown +0x0 and activation threshold +0x4, computed from the carrier's type at the beacon's creation).
--
-- From each new call of one of this player's record entries (its activation +0x10 changes) until 5 s after its HUD
-- slot shows the cooldown state (4), at most M.MAX_SECONDS: one ONGOING PROBE line a second and one at every change of
-- the HUD state, each with
--   * the entry: activation, cooldown end, arrival (seconds relative to the clock: + ahead, - behind), +0x28 as hex,
--     as two u32 and as two f32;
--   * the HUD slot: its state (3 inbound, 4 cooling, others unmapped), +0x3714..+0x3724 as f32 (+0x3718 inbound left,
--     +0x3720 cooldown left; +0x3714, +0x371C, +0x3724 unmapped), the bar's total;
--   * every beacon of the entry's type: countdown, activation threshold, activated, state mode.
-- The tester calls a vanilla orbital (Orbital Walking Barrage, Orbital Smoke Strike) and notes when the HUD text reads
-- Inbound, Ongoing and the cooldown: the column that counts down with "Ongoing" is the field. Reads only; no write.
local world_module=require('hd2runtime/runtime/event_world')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local cooldowns=require('hd2runtime/runtime/slot_cooldown')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local HUD=require('hd2runtime/domains/stratagem_calldown').hud
local D=require('hd2runtime/domains/slot_cooldown')
local M={}
M.SAMPLE_EVERY=1
M.MAX_SECONDS=240
M.AFTER_COOLING=5
M.MAX_TRACKED=4

local state={seen={},tracked={},clock=0}
local function log(text)log_module.emit('[HD2Runtime] ONGOING PROBE '..text)end
local function u64(bytes,o)return b.u32(bytes,o)+b.u32(bytes,o+4)*4294967296 end
local function f32(raw,o)
    local ok,v=pcall(b.value,raw or'',o or 0,'f32')
    return ok and v or nil
end
local function num(v)
    if type(v)~='number'then return'-'end
    if v~=v then return'nan'end
    return('%.2f'):format(v)
end
-- The HUD slot drawing entry `index`: its floats +0x3714..+0x3724, state and bar total, or nil.
local function hud_slot(world,index)
    local hud=world.view.pointer(world.game+HUD.global)
    local set_up=hud and world.view.read(hud+HUD.setUp,1)
    if not(set_up and set_up:byte()==1)then return nil end
    local slot=hud+HUD.pathOffset+index*HUD.slots.stride
    local bar=slot+D.hud.bar
    if world.view.u32(slot+HUD.slots.index)~=index or world.view.u32(bar+D.hud.barIndex)~=index then return nil end
    local from=D.hud.inboundLeft-4
    local raw=world.view.read(slot+from,20)
    if not raw then return nil end
    local floats={}
    for k=0,4 do floats[k+1]=('+0x%X %s'):format(from+k*4,num(f32(raw,k*4)))end
    return {state=world.view.u32(bar+D.hud.barState),total=f32(world.view.read(bar+D.hud.barTotal,4)),
        floats=table.concat(floats,' ')}
end
local function beacons_of(world,kind)
    local ok,list=pcall(function()return require('hd2runtime/runtime/beacon_redirect').beacons(world)end)
    if not(ok and list)then return'unreadable'end
    local parts={}
    for entity,it in pairs(list)do
        if it.type==kind then
            parts[#parts+1]=('%d: countdown %s threshold %s activated %s mode %s'):format(entity,num(it.countdown),
                num(it.threshold),tostring(it.activated),tostring(it.mode))
        end
    end
    table.sort(parts)
    return#parts>0 and table.concat(parts,'; ')or'none'
end
local function line(world,t,entry,now,why)
    local bytes=entry.bytes
    local function rel(o)
        local v=u64(bytes,o)
        return v==0 and'0'or num((v-now)/1e6)
    end
    local extra=bytes:sub(0x28+1,0x30)
    local h=hud_slot(world,entry.index)
    log(('entry %d (type %d) t %.1f s%s: activation %s, end %s, arrival %s, +0x28 %s (u32 %d %d; f32 %s %s); HUD %s; '
        ..'beacons %s'):format(entry.index,entry.type,state.clock-t.at,why and(' ['..why..']')or'',rel(0x10),rel(0x18),
        rel(0x20),b.hex and b.hex(extra)or extra:gsub('.',function(c)return('%02x'):format(c:byte())end),b.u32(extra,0),
        b.u32(extra,4),num(f32(extra,0)),num(f32(extra,4)),h and(('state %s, %s, bar total %s'):format(tostring(h.state),
        h.floats,num(h.total)))or'no slot',beacons_of(world,entry.type)))
    return h
end

-- One update in a mission (custom_stratagems' mission step, after the HUD is populated).
function M.step(world,dt)
    state.clock=state.clock+(dt or 0)
    local game=world_module.game_state(world)
    if not(game and game.mission)then state.seen,state.tracked={},{};return end
    local record=slots.local_record(world)
    if not record then return end
    local now=cooldowns.clock(world)
    if not now then return end
    for _,entry in ipairs(record.entries)do
        local activation=u64(entry.bytes,0x10)
        local key=entry.index..':'..entry.type
        local seen=state.seen[key]
        state.seen[key]=activation
        local t=state.tracked[key]
        if seen~=nil and activation~=seen and activation~=0 and not t then
            local n=0;for _ in pairs(state.tracked)do n=n+1 end
            if n<M.MAX_TRACKED then
                t={at=state.clock,next=state.clock,hud=nil,cooling_at=nil}
                state.tracked[key]=t
                local cd=cooldowns.row_cooldown(world,entry.type)
                local timing=require('hd2runtime/runtime/beacon_redirect').row_timing(world,entry.type)
                log(('entry %d (type %d): a NEW CALL: its row: cooldown %s s, call-in %s s, linger %s s; one line a second '
                    ..'until %d s after its cooldown shows (read-only)'):format(entry.index,entry.type,num(cd),
                    num(timing and timing.callIn),num(timing and timing.linger),M.AFTER_COOLING))
            end
        end
        if t then
            local h=hud_slot(world,entry.index)
            local hstate=h and h.state
            local changed=hstate~=t.hud
            if changed or state.clock>=t.next then
                line(world,t,entry,now,changed and('HUD state '..tostring(t.hud)..' -> '..tostring(hstate))or nil)
                t.next=state.clock+M.SAMPLE_EVERY
                t.hud=hstate
            end
            if hstate==D.hud.cooling and not t.cooling_at then t.cooling_at=state.clock end
            if(t.cooling_at and state.clock>=t.cooling_at+M.AFTER_COOLING)or state.clock>=t.at+M.MAX_SECONDS then
                log(('entry %d (type %d): END after %.1f s (%s)'):format(entry.index,entry.type,state.clock-t.at,
                    t.cooling_at and'its cooldown showed'or'the time limit'))
                state.tracked[key]=nil
            end
        end
    end
end
function M.reset_for_tests()state={seen={},tracked={},clock=0}end
return M
