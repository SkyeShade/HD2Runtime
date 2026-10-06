-- The Pelican's body heading while it is held (development only; PelicanGatlingProof 0.4.0;
-- docs/research/pelican-cas-F5FEE03DCFDB.md section 20e; research/pelican-F5FEE03DCFDB.json "heading"). Not exported by
-- api/hd2.lua.
--
-- In its hold (behaviour 667 stage 6) the Pelican's flight is in mode 1: its hover controller (game+0x3326DB0) owns its
-- rotation and turns the body's forward toward a per-instance desired facing D (the controller's sim record +0xC),
-- smoothly (its own thrusters, about a 1 s response), and replicates the result. Behaviour 667 sets D toward its hover
-- point while it approaches and departs; the hold never sets it, so the nose keeps the direction it arrived from (moving
-- its flight target, the orbit, does not turn it).
-- M.face_step writes D, for one Runtime-held Pelican only, as the game's own setter (0x6D4E30) does: a horizontal unit
-- vector, stepped toward the chosen point by at most `rate` degrees per second, as three aligned 4-byte floats in one
-- guarded transaction. Refused, with nothing written, unless: inside the Runtime's own update; the Pelican is
-- Runtime-spawned and held, behaviour 667, stage 6, released; its flight is in mode 1; the controller simulates it here
-- (the host's authority partition), enabled and not crashed. It stops for good, never fighting, when D is no longer the
-- value it wrote (another writer). The stage change ends it by itself: the departure sets its own D.
-- Runs interpreted, as runtime/pelican_weapon.lua does (the game's LuaJIT allocation-sinking bug, docs section 19g).
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local pelicans=require('hd2runtime/runtime/pelicans')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/pelican')
local M={}
local H=D.heading
local US=1e6
M.RATE=40          -- degrees per second, at most
M.DEADBAND=2       -- degrees: closer than this, nothing is written

local function log(text)log_module.emit('[HD2Runtime] PELICAN HEADING '..text)end
local function f32(raw,o)local ok,v=pcall(b.value,raw,o,'f32');return ok and v or nil end
local function map_at(at)return {keys=at,capacity=at+8,empty=at+0xC,multiplier=at+0x10}end
local function wrap(d)while d>180 do d=d-360 end;while d<-180 do d=d+360 end;return d end
-- Two 12-byte vectors within a float rounding of each other (D is a plain store; this tolerates a renormalised copy).
local function same(x,y)
    for k=0,8,4 do
        local p,q=f32(x,k),f32(y,k)
        if not(p and q and math.abs(p-q)<1e-4)then return false end
    end
    return true
end

-- One Pelican's heading, read-only: {yaw (its body's, degrees), desired = {x, y, z} (D), desired_yaw (degrees, or nil
-- when D is zero), yaw_rate (degrees/s, the controller's angular velocity about Z), mode (its flight mode), simulated,
-- enabled, crashed, address (D's), raw (D's 12 bytes), record (the sim record), owner}, or nil and why.
function M.state(world,pelican)
    local comp=world.view.pointer(world.game+H.global)
    if not comp or comp==0 then return nil,'the hover controller is unreadable'end
    local index=pelicans.index_of(world,comp,map_at(H.map),pelican)
    if not index then return nil,'the hover controller does not hold it'end
    local count=world.view.read(comp+H.simulated,4)
    local records=world.view.pointer(comp+H.records)
    local entries=world.view.pointer(comp+H.entries)
    if not(count and records and records~=0 and entries and entries~=0)then return nil,'its records are unreadable'end
    local rec=world.view.read(records+index*H.stride,H.stride)
    local ent=world.view.read(entries+index*H.entryStride,H.entryStride)
    local t=pelicans.targets(world,pelican)
    local mode=t and world.view.read(t.flight_record+H.flightMode,4)
    local pose=pelicans.pose(world,pelican)
    if not(rec and ent and mode and pose)then return nil,'its records are unreadable'end
    local x,y,z=f32(rec,H.desired),f32(rec,H.desired+4),f32(rec,H.desired+8)
    local wz=f32(rec,H.omega+8)
    local flat=x and y and math.sqrt(x*x+y*y)or 0
    return {index=index,yaw=pose.yaw,position=pose.position,desired={x=x,y=y,z=z},
        desired_yaw=flat>1e-4 and math.deg(math.atan2(y,x))or nil,yaw_rate=wz and math.deg(wz),mode=b.u32(mode,0),
        simulated=index<b.u32(count,0),enabled=ent:byte(H.enabled+1)~=0,crashed=ent:byte(H.crashed+1)~=0,
        address=records+index*H.stride+H.desired,raw=rec:sub(H.desired+1,H.desired+12),record=records+index*H.stride}
end
function M.text(s)
    if not s then return'(unreadable)'end
    return ('body yaw %.1f deg, desired %s, yaw rate %s deg/s, flight mode %d%s'):format(s.yaw,s.desired_yaw and
        ('%.1f deg'):format(s.desired_yaw)or'none',s.yaw_rate and('%.1f'):format(s.yaw_rate)or'?',s.mode,
        s.simulated and''or', not simulated here')
end

local faces={}    -- pelican -> {written (raw D), at (clock), stopped (why)}
function M.facing(pelican)return faces[pelican]end

-- M.face_step(world, pelican, point, label): turns the desired facing toward `point` ({x, y, z}: the turret's target),
-- by at most M.RATE degrees per second since the last write. nil `point`: nothing is written (the heading is kept).
-- Returns nil (nothing to do) or an event: {kind = 'turned', from, to, toward, body, error} (degrees),
-- {kind = 'stopped', reason} (once: another writer changed D) or {kind = 'refused', code, reason}.
function M.face_step(world,pelican,point,label)
    local f=faces[pelican]or{}
    faces[pelican]=f
    if f.stopped then return nil end
    if not scheduler.in_update()then return {kind='refused',code='NOT_GAME_THREAD',reason='only inside the Runtime\'s update'}end
    if not pelicans.owned(pelican)then return {kind='refused',code='NOT_RUNTIME_PELICAN',reason='not spawned by the Runtime'}end
    local p=pelicans.read(world,pelican)
    if not(p and p.behaviour==667 and p.stage==H.holdStage and p.released)then return nil end
    local s,why=M.state(world,pelican)
    if not s then return {kind='refused',code='UNAVAILABLE',reason=why}end
    if f.written and not same(s.raw,f.written)then
        f.stopped='its desired facing was changed by another writer'
        log(('STOPPED (%s): Pelican %d: %s; not fought'):format(tostring(label),pelican,f.stopped))
        return {kind='stopped',reason=f.stopped}
    end
    if not point then return nil end
    if s.mode~=H.holdMode then return nil end
    if not(s.simulated and s.enabled and not s.crashed)then
        return {kind='refused',code='NOT_CONTROLLED',reason='the hover controller does not steer it here'}
    end
    local _,handle=pelicans.record_address(world,pelican)
    if not(handle and b.u32(handle,0x14)%2==1)then return {kind='refused',code='NOT_HOST',reason='not the host\'s'}end
    local dx,dy=point.x-s.position.x,point.y-s.position.y
    if dx*dx+dy*dy<1 then return nil end
    local toward=math.deg(math.atan2(dy,dx))
    local from=s.desired_yaw or s.yaw
    local err=wrap(toward-from)
    if math.abs(err)<M.DEADBAND and s.desired_yaw then return nil end
    local now=pelicans.clock(world)
    local dt=math.min(0.5,math.max(0.05,f.at and now and(now-f.at)/US or 0.25))
    local step=math.max(-M.RATE*dt,math.min(M.RATE*dt,err))
    local to=from+step
    local r=math.rad(to)
    local desired=b.encode(math.cos(r),'f32')..b.encode(math.sin(r),'f32')..b.encode(0,'f32')
    local owner=pelicans.owner_of(world,s.record,H.stride)
    local rec=world.view.read(s.record,H.stride)
    if not(owner and rec)then return {kind='refused',code='NOT_PRIVATE',reason='its sim record is unreadable'}end
    local identity={component='HoverController',component_type='native',unique_owner=true,owner_count=1}
    local plan={snapshots={{owner=owner,offset=s.record-owner.base,bytes=rec}},changes={}}
    for k=0,8,4 do
        plan.changes[#plan.changes+1]={label='pelican.'..pelican..'.desired_facing.'..('xyz'):sub(k/4+1,k/4+1),
            owner=owner,offset=s.address+k-owner.base,expected=rec:sub(H.desired+k+1,H.desired+k+4),
            desired=desired:sub(k+1,k+4),before=rec:sub(H.desired+k+1,H.desired+k+4),already_desired=false,
            identity=identity,chain={}}
    end
    local report=transaction.apply(world.runtime,plan)
    metrics.count('pelican_heading.transactions')
    if report.status~='APPLIED'then return {kind='refused',code='GUARD_REJECTED',reason=tostring(report.reason)}end
    f.written,f.at=desired,now
    return {kind='turned',from=from,to=to,toward=toward,body=s.yaw,error=wrap(toward-s.yaw)}
end

function M.reset()faces={}end
return M
