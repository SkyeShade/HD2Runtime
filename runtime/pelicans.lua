-- The transport Pelican (development only; docs/research/pelican-cas-F5FEE03DCFDB.md). Not exported by api/hd2.lua.
--
-- research/pelican-F5FEE03DCFDB.json: the game's transport Pelican is the entity shuttle_transport. A vehicle or exosuit
-- call-in spawns it at the beacon (the dispatcher's own spawn) with the vehicle as its cargo. Three components describe
-- one Pelican, each found by its entity id:
--   * Transport (game+0x3326518; elements 0x40): +0x0 the cargo resource, +0x8 the spawned cargo entity (0: none),
--     +0xC the cargo timer, +0x28 an associated entity (an airlift);
--   * Behavior (game+0x3326740; records 0x1F8; P = the record + 8): the flight's stage machine. P+0 the stage,
--     P+0x170/+0x178/+0x180/+0x188 its timestamps (game clock, microseconds), P+0x1BC the target, P+0x1E0 bit 0
--     "released";
--   * the transform (game+0x3326508; records 0x308): +0x2E0 the position.
-- The flight: stage 3 flies to its hover point (its recorded position plus a height), stage 6 hovers; it releases at
-- the target or 6 s after the hover start (P+0x180), sets P+0x178 = now, and departs 0.6 s after P+0x178 (stage 8).
-- Stage 7 (after an airlift drop) departs 3 s after P+0x178. Stages 8-10 fly out and the entity is removed 12 s after
-- stage 10's P+0x178. Nothing else holds a Pelican: no 180 s limit exists in the game.
--
-- M.watch observes every Pelican, read-only, each Runtime update. With spec.hold it also HOLDS each Pelican that it
-- sees released: one guarded 8-byte write of that Pelican's P+0x178, so it departs spec.hold seconds after its
-- release instead of 0.6 s. The departure, the fly-out and the removal stay the game's. Guards (refused with nothing
-- written, one attempt per Pelican):
--   * the pins; in a mission, as host, solo;
--   * the entity is still a transport Pelican with its Behavior record at the same index, the same behaviour id;
--   * released: stage 6 with P+0x1E0 bit 0, or stage 7; P+0x178 exactly as observed, at most `now`, and its native
--     departure not yet reached;
--   * 0 < hold <= 120 s, and the new departure later than the native one (a hold only extends).
-- Afterwards P+0x178 is read back and the stage, flags and other timestamps are compared. No shared definition, no
-- entity settings, no StratagemInfo, no Transport member and no other Pelican is written; the Behavior record is the
-- Pelican's own and is removed with it, so nothing needs restoring.
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local D=require('hd2runtime/domains/pelican')
local M={}
local TC,BC,XC,CC=D.components.transport,D.components.behavior,D.components.bearer,D.components.clock
local F=D.flight
local US=1e6
M.HOLD_MAX_SECONDS=120
M.RELEASED_WAIT=F.microseconds.releasedDeparture/US     -- stage 6: departs 0.6 s after P+0x178
M.STAGE7_WAIT=F.microseconds.stage7Departure/US          -- stage 7: 3 s
local ENTITY=b.unhex(D.entity):reverse()                 -- the resource hash as the handle stores it

local function log(text)log_module.emit('[HD2Runtime] pelican '..text)end
local function spawn_log(text)log_module.emit('[HD2Runtime] PELICAN SPAWN '..text)end
local function f32(bytes,o)local ok,v=pcall(b.value,bytes,o,'f32');return ok and v or nil end
local function u64(bytes,o)return b.u32(bytes,o)+b.u32(bytes,o+4)*4294967296 end
local function encode64(n)return b.encode(n%4294967296,'u32')..b.encode(math.floor(n/4294967296),'u32')end
local function finite(v)return type(v)=='number'and v==v and v~=math.huge and v~=-math.huge end
local function vec(bytes,o)
    local x,y,z=f32(bytes,o),f32(bytes,o+4),f32(bytes,o+8)
    if finite(x)and finite(y)and finite(z)then return {x=x,y=y,z=z}end
end
function M.distance(a,c)
    if not(a and c)then return nil end
    return math.sqrt((a.x-c.x)^2+(a.y-c.y)^2+(a.z-c.z)^2)
end
-- The cargo resource as the catalogued vehicle it is (by name), or its hex.
local VEHICLES={}
for name,v in pairs(D.vehicles)do VEHICLES[v.vehicle]=name end
function M.cargo_name(hex)return hex and(VEHICLES[hex]or hex)end

local proven={}
function M.prove(world)
    if D.source.gameDllSha256~=profile.dll_sha then return nil,'the Pelican research covers another game.dll build'end
    if proven[world.game]then return true end
    for _,pin in ipairs(D.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,('Pelican code changed (%s at game+%X)'):format(pin.label,pin.rva)
        end
    end
    proven[world.game]=true
    return true
end

-- The game clock (microseconds), or nil.
function M.clock(world)
    local object=world.view.pointer(world.game+CC.global)
    local raw=object and world.view.read(object+CC.now,8)
    return raw and u64(raw,0)
end
-- A component's entity map lookup: the record index of `entity`, or nil.
local function index_of(world,component,layout,entity)
    local raw=world.view.read(component+layout.keys,layout.multiplier+4-layout.keys)
    if not raw then return nil end
    local ok,keys=pcall(b.pointer,raw,0)
    local cap=b.u32(raw,layout.capacity-layout.keys)
    local empty,mult=b.u32(raw,layout.empty-layout.keys),b.u32(raw,layout.multiplier-layout.keys)
    if not(ok and keys~=0 and cap>0 and cap<=1048576)then return nil end
    local start=world_module.mul32(entity,mult)
    for probe=0,math.min(cap,4096)-1 do
        local slot=world.view.read(keys+((start+probe)%cap)*8,8)
        if not slot then return nil end
        local key=b.u32(slot,0)
        if key==entity then
            local index=b.u32(slot,4)
            return index~=4294967295 and index or nil
        end
        if key==empty then return nil end
    end
end
-- The Pelican's Behavior record: {address, index, raw (0x1F8), handle_slot}, or nil.
local function behavior_of(world,entity)
    local component=world.view.pointer(world.game+BC.global)
    if not component then return nil end
    local index=index_of(world,component,BC,entity)
    local records=index and world.view.pointer(component+BC.records)
    if not records or records==0 then return nil end
    local address=records+index*BC.stride
    local raw=world.view.read(address,BC.stride)
    local handles=world.view.pointer(component+BC.handles)
    return raw and {address=address,index=index,raw=raw,handle_slot=handles and handles~=0 and handles+index*8 or nil}
end
-- The Pelican's position (the transform), or nil.
function M.position(world,entity)
    local component=world.view.pointer(world.game+XC.global)
    local index=component and index_of(world,component,XC,entity)
    local records=index and world.view.pointer(component+XC.records)
    local raw=records and records~=0 and world.view.read(records+index*XC.stride+XC.position,12)
    return raw and vec(raw,0)
end
-- Which movement components hold the Pelican (research "targetPush": the flight's target push 0x4D1150 writes the
-- flight component's record as plain data, and the two others through native calls), and the flight component's
-- target: {flight = index or nil, flight_target = {x, y, z} or nil, ground = bool, other = bool}. Read-only
-- diagnostics: a Pelican held by the flight component alone can be retargeted by data; one in a native mover cannot.
local FT,NM=D.flightTarget,D.nativeMovers
function M.movers(world,entity)
    local function member(layout)
        local component=world.view.pointer(world.game+layout.global)
        if not component or component==0 then return nil end
        return index_of(world,component,layout,entity),component
    end
    local index,component=member(FT)
    local records=index and world.view.pointer(component+FT.records)
    local raw=records and records~=0 and world.view.read(records+index*FT.stride+FT.target,12)
    return {flight=index or nil,flight_target=raw and vec(raw,0)or nil,ground=member(NM.ground)~=nil,
        other=member(NM.other)~=nil}
end
-- The flight members of one Behavior record (P = the record + context).
local function flight(raw)
    local P=BC.context
    local flags=b.u32(raw,P+F.flags)
    return {behaviour=b.u32(raw,BC.behaviourId),stage=b.u32(raw,P+F.stage),pending=b.u32(raw,P+F.pending),
        flags=flags,released=flags%2==1,target=vec(raw,P+F.target),
        times={stage=u64(raw,P+F.stageTime),release=u64(raw,P+F.releaseTime),hover=u64(raw,P+F.hoverStart),
            approach=u64(raw,P+F.approachTime)},
        release_raw=raw:sub(P+F.releaseTime+1,P+F.releaseTime+8)}
end
-- Every transport Pelican now, by entity: {entity, network, index, element, cargo (hex or nil), cargo_spawned (entity
-- or nil), cargo_timer, associated (entity or nil), record, behaviour, stage, pending, flags, released, times, target,
-- position}; or nil and why. Read-only.
function M.list(world)
    local component=world.view.pointer(world.game+TC.global)
    local raw=component and world.view.read(component,TC.elements+8)
    if not raw then return nil,'the Transport component is unreadable'end
    local count=b.u32(raw,TC.count)
    if count>4096 then return nil,'the Transport component is implausible'end
    local ok1,handles=pcall(b.pointer,raw,TC.handles)
    local ok2,elements=pcall(b.pointer,raw,TC.elements)
    if not(ok1 and ok2)then return nil,'the Transport arrays are unreadable'end
    local out={}
    if count==0 then return out end
    if handles==0 or elements==0 then return nil,'the Transport arrays are unreadable'end
    for i=0,count-1 do
        local handle=world.view.pointer(handles+i*8)
        local h=handle and handle~=0 and world.view.read(handle,TC.handleNetwork+4)
        if h and h:sub(1,8)==ENTITY then
            local entity=b.u32(h,TC.handleEntity)
            local element=elements+i*TC.stride
            local e=world.view.read(element,TC.stride)
            if e then
                local cargo=e:sub(TC.cargo+1,TC.cargo+8)
                local spawned,associated=b.u32(e,TC.spawnedCargo),b.u32(e,TC.associated)
                local p={entity=entity,network=b.u32(h,TC.handleNetwork),index=i,element=element,
                    cargo=cargo~=string.rep('\0',8)and b.hex(cargo:reverse()):upper()or nil,
                    cargo_spawned=spawned~=0 and spawned or nil,cargo_timer=f32(e,TC.cargoTimer),
                    associated=associated~=0 and associated or nil,position=M.position(world,entity)}
                local record=behavior_of(world,entity)
                if record then
                    p.record=record.address
                    for k,v in pairs(flight(record.raw))do p[k]=v end
                end
                out[entity]=p
            end
        end
    end
    return out
end
function M.read(world,entity)
    local list=M.list(world)
    return list and list[entity]
end

local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base and address+size<=r.base+r.size)
    then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end
-- Internal, for runtime/pelican_gatling.lua and runtime/pelican_weapon.lua: the entity-map lookup, the private
-- read-write owner of an address and an entity's Behavior record.
M.index_of,M.owner_of,M.behavior_of=index_of,owner_of,behavior_of
-- The departure wait of a released Pelican's stage (seconds), or nil when it is not released.
local function release_wait(p)
    if p.stage==6 and p.released then return M.RELEASED_WAIT end
    if p.stage==7 then return M.STAGE7_WAIT end
end
M.release_wait=release_wait

-- Hold one released Pelican: it departs `seconds` after its release (P+0x178) instead of the native wait. expect =
-- {behaviour = its behaviour id, release = the 8 bytes of P+0x178 as observed}. Returns {entity, release, departure
-- (native and new, game clock), seconds, writes, verified, verify} or nil, code, reason. One guarded transaction.
function M.hold(world,entity,expect,seconds)
    if type(expect)~='table'or type(expect.behaviour)~='number'or type(expect.release)~='string'
        or #expect.release~=8 then return nil,'INVALID','expect.behaviour and expect.release (8 bytes) are required'end
    if not(finite(seconds)and seconds>0 and seconds<=M.HOLD_MAX_SECONDS)then
        return nil,'HOLD_INVALID',('the hold must be above 0 and at most %d s, not %s'):format(M.HOLD_MAX_SECONDS,
            tostring(seconds))
    end
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','Pelicans are held in a mission only'end
    if game.host~=true then return nil,'NOT_HOST','development API: host only'end
    local record_list,code,reason=slots.local_record(world)
    if not record_list then return nil,code,reason end
    local mp=require('hd2runtime/runtime/multiplayer')
    local scode,swhy=mp.solo_guard(record_list.records,mp.entity_allowed(entity),'the hold is the host\'s flight state')
    if scode then return nil,scode,swhy end
    local p=M.read(world,entity)
    if not p then return nil,'GONE','Pelican '..tostring(entity)..' is not a transport Pelican now'end
    local record=behavior_of(world,entity)
    if not(p.record and record and record.address==p.record)then
        return nil,'NO_FLIGHT','Pelican '..tostring(entity)..' has no Behavior record'end
    if p.behaviour~=expect.behaviour then
        return nil,'UNEXPECTED_BEHAVIOUR',('Pelican %s runs behaviour %d, not %d'):format(tostring(entity),p.behaviour,
            expect.behaviour)
    end
    local wait=release_wait(p)
    if not wait then
        return nil,'NOT_RELEASED',('Pelican %s is in stage %d (flags %d): not released'):format(tostring(entity),p.stage,
            p.flags)
    end
    if p.release_raw~=expect.release then
        return nil,'RELEASE_UNEXPECTED','Pelican '..tostring(entity)..'\'s release time changed since it was observed'
    end
    local now=M.clock(world)
    if not now then return nil,'UNAVAILABLE','the game clock is unreadable'end
    local release=p.times.release
    if release>now then return nil,'RELEASE_UNEXPECTED','the release time is in the future: already held?'end
    local native=release+wait*US
    if now>=native then return nil,'DEPARTING','Pelican '..tostring(entity)..' has reached its native departure'end
    local departure=release+seconds*US
    if departure<=native then return nil,'HOLD_INVALID','a hold only extends: '..seconds..' s is not past the native '
        ..wait..' s'end
    if departure-now>M.HOLD_MAX_SECONDS*US then return nil,'HOLD_INVALID','the departure would be over '
        ..M.HOLD_MAX_SECONDS..' s away'end
    local new_release=departure-wait*US
    local desired=encode64(new_release)
    local P=BC.context
    local owner=owner_of(world,record.address,BC.stride)
    local handle_owner=record.handle_slot and owner_of(world,record.handle_slot,8)
    local handle_bytes=record.handle_slot and world.view.read(record.handle_slot,8)
    if not(owner and handle_owner and handle_bytes)then
        return nil,'NOT_PRIVATE','the Behavior records are not in private read-write memory'
    end
    local identity={component='Behavior',component_type='native',unique_owner=true,owner_count=1}
    local at=record.address+P+F.releaseTime
    local times_from=record.address+P+F.stageTime
    local plan={snapshots={
            {owner=owner,offset=record.address-owner.base,bytes=record.raw:sub(1,P+F.pending+4)},   -- id, stage
            {owner=owner,offset=times_from-owner.base,bytes=record.raw:sub(P+F.stageTime+1,P+F.approachTime+8)},
            {owner=owner,offset=record.address+P+F.flags-owner.base,bytes=record.raw:sub(P+F.flags+1,P+F.flags+4)},
            {owner=handle_owner,offset=record.handle_slot-handle_owner.base,bytes=handle_bytes}},
        changes={{label='pelican.'..tostring(entity)..'.release_time',owner=owner,offset=at-owner.base,
            expected=expect.release,desired=desired,before=expect.release,already_desired=false,identity=identity,
            chain={}}}}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('pelicans.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local after=world.view.read(record.address,BC.stride)
    local result={entity=entity,stage=p.stage,release=release,native=native,departure=departure,seconds=seconds,
        writes=report.writes,verify={nonTarget=report.non_target_bytes_unchanged==true,
            protection=report.protection_restored==true}}
    result.verify.release=after~=nil and after:sub(P+F.releaseTime+1,P+F.releaseTime+8)==desired
    -- The members the hold relies on, read back: the id and stage, the other timestamps, the flags.
    local function same(from,to)return after~=nil and after:sub(from+1,to)==record.raw:sub(from+1,to)end
    result.verify.others=same(0,P+F.pending+4)and same(P+F.stageTime,P+F.releaseTime)
        and same(P+F.releaseTime+8,P+F.approachTime+8)and same(P+F.flags,P+F.flags+4)
    local verified=true
    for _,v in pairs(result.verify)do if v~=true then verified=false end end
    result.verified=verified
    log(('HOLD APPLIED: Pelican %s (stage %d): departs %.1f s after its release instead of %.1f s (%.1f s from now); '
        ..'%d write; verified %s (read back, stage/flags/other timestamps unchanged %s, non-target bytes unchanged %s, '
        ..'protection restored %s)'):format(tostring(entity),p.stage,seconds,wait,(departure-now)/US,report.writes,
        tostring(verified),tostring(result.verify.others),tostring(result.verify.nonTarget),
        tostring(result.verify.protection)))
    return result
end

------------------------------------------------------------------------------------------------- the spawn --
-- M.spawn: a guarded call of the game's own spawn request for the transport Pelican (research "spawn" and "anchor"; the
-- native call is runtime/windows_write.lua native_spawn_pelican, the only one that can make it). The descriptor is the
-- one the beacon dispatcher builds for a vehicle's Pelican, with a Runtime-owned copy of the game's default spawn
-- context (all zero: no cargo, no associated entity) whose one member set is the ANCHOR (+0x610), as the beacon sets
-- it for a vehicle: the Pelican's drop-position record takes it at creation, and its flight approaches from the spawn
-- point and hovers over the anchor. Refused, with nothing called, unless:
--   * the build: the research covers this game.dll, the spawn request's exact bytes and every pin prove;
--   * the context: called from the Runtime's own update on the game thread (scheduler.in_update);
--   * the game: in a mission, as host;
--   * the world: the component world resolves; its default spawn context (0x8A0 bytes) is all zero;
--   * the entity: the Pelican's entity type is registered in the world's settings table and its package is resident;
--   * the spawn point and the anchor: finite world coordinates (|v| <= 100000); the facing a horizontal unit vector;
--   * fewer than M.MAX_ACTIVE Runtime Pelicans alive.
-- After the call: the entity is a transport Pelican in the Transport component, with no cargo, no spawned cargo, no
-- associated entity, a Behavior record, and its drop-position record holds the anchor. Logs PELICAN SPAWN REQUESTED /
-- CREATED (or UNVERIFIED).
local scheduler_state=scheduler
local core_assets=require('hd2runtime/core/assets')
local SP,AN=D.spawn,D.anchor
M.MAX_ACTIVE=4
local owned={}            -- entity -> the record of a Runtime-spawned Pelican (runtime/pelicans.lua's manager)
local function owned_count()local n=0;for _ in pairs(owned)do n=n+1 end;return n end
function M.owned(entity)return owned[entity]~=nil end
-- Who asked for a Runtime Pelican: the owner its request named (the mod; hd2.pelican.spawn passes its caller), or nil.
function M.request_owner(entity)
    local o=owned[entity]
    return o and o.request and o.request.spec and o.request.spec.owner or nil
end

-- The component world, or nil.
local function component_world(world)return world.view.pointer(world.game+SP.world)end
-- The Pelican's entity type in the world's entity settings table: true and its cargo timer, or nil and why.
function M.entity_registered(world)
    local w=component_world(world)
    local tab=w and world.view.pointer(w+SP.settingsTable)
    if not tab or tab==0 then return nil,'the entity settings table is unreadable'end
    local lo,hi=b.u32(ENTITY,0),b.u32(ENTITY,4)
    local slots=SP.settingsSlots
    local i=((hi%slots)*(4294967296%slots)+lo%slots)%slots   -- the 64-bit id modulo the slot count, exactly
    for _=1,slots do
        local slot=world.view.read(tab+16*i,16)
        if not slot then return nil,'the entity settings table is unreadable'end
        if slot:sub(1,8)==ENTITY then
            local settings=world.view.read(tab+SP.settingsBase+b.u32(slot,8)*SP.settingsStride,8)
            if not settings then return nil,'the Pelican\'s settings are unreadable'end
            return true,f32(settings,0)
        end
        if slot:sub(1,8)==string.rep('\0',8)then break end
        i=(i+1)%slots
    end
    return nil,'the Pelican\'s entity type is not registered in this world (its data is not loaded)'
end
-- The world's default spawn context: 'zero', or nil and why.
function M.default_context(world)
    local w=component_world(world)
    local raw=w and world.view.read(w+SP.defaultContext,SP.contextSize)
    if not raw then return nil,'the default spawn context is unreadable'end
    if raw~=string.rep('\0',SP.contextSize)then return nil,'the default spawn context is not all zero'end
    return 'zero'
end
local function finite_coordinate(v)return type(v)=='number'and v==v and math.abs(v)<=100000 end
-- A Pelican's anchor (its drop-position record: where its flight hovers), or nil. Read-only.
local AN_MAP={keys=AN.mapKeys,capacity=AN.mapCapacity,empty=AN.mapEmpty,multiplier=AN.mapMultiplier}
function M.anchor(world,entity)
    local component=world.view.pointer(world.game+AN.global)
    local index=component and index_of(world,component,AN_MAP,entity)
    local records=index and world.view.pointer(component+AN.records)
    local raw=records and records~=0 and world.view.read(records+index*AN.stride+AN.position,12)
    return raw and vec(raw,0)
end
local function text(p)return p and('(%.1f, %.1f, %.1f)'):format(p.x,p.y,p.z)or'(?)'end
M.text=text

-- spec = {x, y, z (the spawn point), fx, fy (a horizontal unit facing), ax, ay, az (the anchor: where it hovers), owner
-- (a label for logs)}. Returns {entity, network, position, anchor, facing, verify = {...}, verified} or nil, code,
-- reason.
function M.spawn(world,spec)
    spec=spec or{}
    local function refuse(code,reason)
        spawn_log(('REFUSED (%s): %s: %s'):format(tostring(spec.owner or'?'),code,reason))
        metrics.count('pelicans.spawn_refused')
        return nil,code,reason
    end
    local runtime=world.runtime
    if not runtime.native_spawn_pelican then
        return refuse('PELICAN_UNAVAILABLE','this Runtime adapter cannot call game functions')
    end
    if not scheduler_state.in_update()then
        return refuse('NOT_GAME_THREAD','the spawn runs only inside the Runtime\'s own update on the game thread')
    end
    local ok,why=M.prove(world)
    if not ok then return refuse('UNSUPPORTED_BUILD',tostring(why))end
    if not world.view.proves(world.game+SP.rva,SP.prologue)then
        return refuse('UNSUPPORTED_BUILD','the game\'s spawn request changed')
    end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return refuse('NOT_IN_MISSION','the game is not in a mission')end
    if game.host~=true then return refuse('HOST_ONLY','only the host creates a Pelican; a client\'s would be local')end
    if not component_world(world)then return refuse('PELICAN_UNAVAILABLE','the component world is unreadable')end
    local context,cwhy=M.default_context(world)
    if not context then return refuse('CONTEXT_UNEXPECTED',cwhy)end
    local registered,rwhy=M.entity_registered(world)
    if not registered then return refuse('PELICAN_UNAVAILABLE',rwhy)end
    local pok,state=pcall(core_assets.state,runtime,D.packageId)
    if not(pok and state=='resident')then
        return refuse('PELICAN_UNAVAILABLE',D.package..' is not resident ('..tostring(pok and state or'unreadable')..')')
    end
    if not(finite_coordinate(spec.x)and finite_coordinate(spec.y)and finite_coordinate(spec.z))then
        return refuse('INVALID_POSITION','the spawn point must be finite world coordinates')
    end
    if not(finite_coordinate(spec.ax)and finite_coordinate(spec.ay)and finite_coordinate(spec.az))then
        return refuse('INVALID_POSITION','the anchor must be finite world coordinates')
    end
    local fx,fy=spec.fx,spec.fy
    if not(finite(fx)and finite(fy)and math.abs(fx*fx+fy*fy-1)<1e-3)then
        return refuse('INVALID_FACING','the facing must be a horizontal unit vector')
    end
    if owned_count()>=M.MAX_ACTIVE then
        return refuse('PELICAN_LIMIT','at most '..M.MAX_ACTIVE..' Runtime Pelicans at a time')
    end
    local position={x=spec.x,y=spec.y,z=spec.z}
    local anchor={x=spec.ax,y=spec.ay,z=spec.az}
    spawn_log(('REQUESTED (%s): anchor %s (where it hovers), spawn point %s, facing (%.2f, %.2f); context: the game\'s '
        ..'default (%d zero bytes: no cargo, no associated entity) with the anchor at +0x%X, no modifier block; checks: '
        ..'build pins proven, mission host, game thread, the Pelican entity registered, %s resident'):format(
        tostring(spec.owner or'?'),text(anchor),text(position),fx,fy,SP.contextSize,AN.contextPosition,D.package))
    metrics.count('pelicans.native_spawns')
    local entity=runtime.native_spawn_pelican(world.game+SP.rva,spec.x,spec.y,spec.z,fx,fy,spec.ax,spec.ay,spec.az)
    spawn_log(('native call returned entity %s'):format(tostring(entity)))
    local result={entity=entity,position=position,anchor=anchor,facing={x=fx,y=fy},verify={}}
    local p=type(entity)=='number'and entity>0 and M.read(world,entity)
    result.verify.exists=p~=nil and p~=false
    if p then
        result.network=p.network
        result.verify.empty=p.cargo==nil and p.cargo_spawned==nil
        result.verify.unassociated=p.associated==nil
        result.verify.flight=p.record~=nil
        local held=M.anchor(world,entity)
        result.verify.anchor=held~=nil and M.distance(held,anchor)<0.01
        result.anchor_read=held
        result.pelican=p
    end
    local verified=true
    for _,v in pairs(result.verify)do if v~=true then verified=false end end
    result.verified=verified and result.verify.empty==true and result.verify.flight==true and result.verify.anchor==true
    if result.verified then
        spawn_log(('CREATED (%s): entity %d (network id %s) at %s; empty: no cargo, no cargo entity, no associated '
            ..'entity; anchor %s read back from its drop-position record; flight: behaviour %s, stage %s; verified true')
            :format(tostring(spec.owner or'?'),entity,tostring(p.network),text(p.position or position),
            text(result.anchor_read),tostring(p.behaviour),tostring(p.stage)))
    else
        spawn_log(('UNVERIFIED (%s): entity %s: exists %s, empty %s, unassociated %s, flight %s, anchor %s (read %s)')
            :format(tostring(spec.owner or'?'),tostring(entity),tostring(result.verify.exists),
            tostring(result.verify.empty),tostring(result.verify.unassociated),tostring(result.verify.flight),
            tostring(result.verify.anchor),text(result.anchor_read)))
    end
    return result
end

----------------------------------------------------------------------------------- Runtime Pelicans (manager) --
-- Every Runtime-spawned Pelican is followed by one manager watch, each update until it is gone: its stage, its hover,
-- its release; with a hover time it is HELD once released (M.hold: its own release time); then its departure and its
-- removal. Spawn requests are queued and made by the manager in its own update (the Runtime-owned execution context),
-- never inside a mod's callback. Events go to each request's callback.
local queue={}
local manager
local function emit(record,event)
    if record.callback then
        local okc,err=pcall(record.callback,event)
        if not okc then log('callback failed: '..tostring(err))end
    end
end
local function manager_tick()
    local world=world_module.open()
    if not world then return end
    local pending=queue;queue={}
    for _,request in ipairs(pending)do
        local result,code,reason=M.spawn(world,request.spec)
        if not result then
            emit(request,{kind='refused',code=code,reason=reason})
        elseif not result.verified then
            emit(request,{kind='unverified',result=result})
            if result.verify.exists then owned[result.entity]={request=request,callback=request.callback,
                first=M.clock(world),hold=request.hold,unverified=true}end
        else
            local now=M.clock(world)
            owned[result.entity]={request=request,callback=request.callback,first=now,hold=request.hold,
                stage=result.pelican.stage,behaviour=result.pelican.behaviour}
            emit(request,{kind='spawned',result=result,clock=now})
        end
    end
    if next(owned)==nil then return end
    local game=world_module.game_state(world)
    local list=game and game.mission and M.list(world)or{}
    local now=M.clock(world)
    local function seconds(from)return now and from and from>0 and(now-from)/US or nil end
    for entity,r in pairs(owned)do
        local p=list[entity]
        if not p then
            owned[entity]=nil
            emit(r,{kind='gone',entity=entity,seconds=seconds(r.first),after_release=seconds(r.released),
                after_departing=seconds(r.departing),held=r.held})
        else
            if p.cargo_spawned and not r.cargo then
                r.cargo=true
                emit(r,{kind='cargo',entity=entity,spawned=p.cargo_spawned})
            end
            if p.stage~=r.stage then
                emit(r,{kind='stage',entity=entity,from=r.stage,to=p.stage,seconds=seconds(r.first),target=p.target,
                    position=p.position})
                r.stage=p.stage
                if p.stage==6 then emit(r,{kind='hovering',entity=entity,seconds=seconds(r.first),target=p.target,
                    position=p.position})end
            end
            if release_wait(p)and not r.released then
                r.released=now
                emit(r,{kind='released',entity=entity,stage=p.stage,seconds=seconds(r.first),
                    hover=p.stage==6 and seconds(p.times.hover)or nil,target=p.target,position=p.position})
                if r.hold and r.behaviour then
                    local held,code,reason=M.hold(world,entity,{behaviour=r.behaviour,release=p.release_raw},r.hold)
                    if held then r.held=held;emit(r,{kind='held',entity=entity,result=held})
                    else r.hold_refused=code;emit(r,{kind='hold_refused',entity=entity,code=code,reason=reason})end
                end
            end
            if p.stage and p.stage>=8 and p.stage<=11 and not r.departing then
                r.departing=now
                emit(r,{kind='departing',entity=entity,stage=p.stage,after_release=seconds(r.released),
                    position=p.position})
            end
        end
    end
end
local function ensure_manager()
    if manager and manager.status=='active'then return end
    manager={status='active'}
    function manager.tick()
        if next(queue)==nil and next(owned)==nil then manager.status='complete';return end
        manager_tick()
    end
    function manager.cancel()manager.status='cancelled'end
    scheduler.attach(manager)
end
-- Queue one spawn, made in the manager's next update. spec as M.spawn, plus hold (seconds after the release, or nil:
-- the game's own) and callback(event): 'refused' {code, reason}, 'unverified' {result}, 'spawned' {result},
-- 'stage', 'hovering', 'released', 'held', 'hold_refused', 'departing', 'cargo', 'gone'. Returns the request.
function M.request(spec,callback)
    local request={spec=spec,hold=spec and spec.hold,callback=callback}
    queue[#queue+1]=request
    ensure_manager()
    return request
end
function M.active()local out={};for entity in pairs(owned)do out[#out+1]=entity end;table.sort(out);return out end

----------------------------------------------------------------------------------------------- the retarget --
-- Research "retarget" and "targetPush" (docs/research/pelican-cas-F5FEE03DCFDB.md, "Retargeting a live Pelican"): the
-- flight component steers every update toward its record's target (+0x4FC); the game's own move-to (0x4D1150) is, for
-- a Pelican held by the flight component alone, a plain 12-byte store of P+0x1BC into that member. A released stage 6
-- reads only its release time: nothing re-pushes a target until the departure (stage 8) pushes its own. So a held
-- Pelican's hover point is per-instance data: P+0x1BC and the flight record's target, written together as the game
-- does. Development only: not exported by api/hd2.lua (the orbit is proven first, OrbitProof).

-- A Pelican's two targets, read-only: {behaviour = P+0x1BC, flight = the flight record's +0x4FC, raw = {behaviour,
-- flight} (12 bytes each), record (its Behavior record), flight_record (address), flight_index}, or nil and why.
function M.targets(world,entity)
    local record=behavior_of(world,entity)
    if not record then return nil,'no Behavior record'end
    local component=world.view.pointer(world.game+FT.global)
    if not component or component==0 then return nil,'no flight component'end
    local index=index_of(world,component,FT,entity)
    if not index then return nil,'the flight component does not hold it'end
    local records=world.view.pointer(component+FT.records)
    if not records or records==0 then return nil,'the flight records are unreadable'end
    local address=records+index*FT.stride
    local fraw=world.view.read(address+FT.target,12)
    if not fraw then return nil,'the flight target is unreadable'end
    local P=BC.context
    local braw=record.raw:sub(P+F.target+1,P+F.target+12)
    return {behaviour=vec(braw,0),flight=vec(fraw,0),raw={behaviour=braw,flight=fraw},record=record,
        flight_record=address,flight_index=index}
end

-- The bounds of a retarget, against the Pelican's own anchor: at most RETARGET_RANGE m away horizontally and between
-- 0 and RETARGET_HEIGHT m above it.
M.RETARGET_RANGE=200
M.RETARGET_HEIGHT=200
local function encode_point(p)return b.encode(p.x,'f32')..b.encode(p.y,'f32')..b.encode(p.z,'f32')end

-- Retarget one HELD Runtime Pelican: its hover point becomes `point`. expect = {behaviour, flight} = the 12 bytes of
-- each target as observed. One guarded transaction (P+0x1BC and the flight record's +0x4FC), refused with nothing
-- written unless: the pins prove; a mission, host, solo; a Runtime-spawned Pelican, alive, its behaviour the one it was
-- spawned with, in stage 6 and released (held); the flight component holds it and no native mover does; both targets
-- exactly as observed (another writer is never overwritten); the point finite and within the bounds of its anchor.
-- Read back afterwards. Returns {entity, target, raw (the flight target written), writes, verify, verified} or nil,
-- code, reason. Logs nothing on success (an orbit makes many); refusals are returned.
function M.retarget(world,entity,expect,point)
    if type(expect)~='table'or type(expect.behaviour)~='string'or#expect.behaviour~=12 or type(expect.flight)~='string'
        or#expect.flight~=12 then return nil,'INVALID','expect.behaviour and expect.flight (12 bytes each) are required'end
    if not(type(point)=='table'and finite_coordinate(point.x)and finite_coordinate(point.y)
        and finite_coordinate(point.z))then return nil,'INVALID_TARGET','the point must be finite world coordinates'end
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','Pelicans are retargeted in a mission only'end
    if game.host~=true then return nil,'NOT_HOST','development API: host only'end
    local record_list,code,reason=slots.local_record(world)
    if not record_list then return nil,code,reason end
    local mp=require('hd2runtime/runtime/multiplayer')
    local scode,swhy=mp.solo_guard(record_list.records,mp.entity_allowed(entity),'the flight target is the host\'s')
    if scode then return nil,scode,swhy end
    local mine=owned[entity]
    if not mine then return nil,'NOT_RUNTIME_PELICAN','only a Pelican the Runtime spawned is retargeted'end
    local p=M.read(world,entity)
    if not p then return nil,'GONE','Pelican '..tostring(entity)..' is not a transport Pelican now'end
    if p.behaviour~=mine.behaviour then
        return nil,'UNEXPECTED_BEHAVIOUR',('Pelican %s runs behaviour %s, not %s'):format(tostring(entity),
            tostring(p.behaviour),tostring(mine.behaviour))
    end
    if not(p.stage==6 and p.released)then
        return nil,'NOT_HOLDING',('Pelican %s is in stage %s (released %s): only a released, hovering Pelican is '
            ..'retargeted'):format(tostring(entity),tostring(p.stage),tostring(p.released))
    end
    local m=M.movers(world,entity)
    if m.ground or m.other then return nil,'NATIVE_MOVER','a native mover holds it: its target is not plain data'end
    local t,twhy=M.targets(world,entity)
    if not(m.flight and t)then return nil,'NO_FLIGHT',tostring(twhy or'the flight component does not hold it')end
    if t.raw.behaviour~=expect.behaviour or t.raw.flight~=expect.flight then
        return nil,'TARGET_CHANGED','its target changed since it was observed (another writer): not overwritten'
    end
    local anchor=M.anchor(world,entity)
    if not anchor then return nil,'UNAVAILABLE','its anchor is unreadable'end
    local away,up=math.sqrt((point.x-anchor.x)^2+(point.y-anchor.y)^2),point.z-anchor.z
    if away>M.RETARGET_RANGE or up<0 or up>M.RETARGET_HEIGHT then
        return nil,'OUT_OF_RANGE',('the point is %.1f m from its anchor and %.1f m above it (at most %d m away, 0 to %d m '
            ..'up)'):format(away,up,M.RETARGET_RANGE,M.RETARGET_HEIGHT)
    end
    local record=t.record
    local P=BC.context
    local owner=owner_of(world,record.address,BC.stride)
    local flight_owner=owner_of(world,t.flight_record,FT.stride)
    if not(owner and flight_owner)then
        return nil,'NOT_PRIVATE','the Behavior or flight records are not in private read-write memory'
    end
    local desired=encode_point(point)
    if expect.behaviour==desired and expect.flight==desired then
        -- Already the point (an orbit's entry starts exactly at its hover point): nothing to write.
        return {entity=entity,target=point,raw=desired,writes=0,verify={behaviour=true,flight=true},verified=true}
    end
    -- The contexts: the Behavior record from its id to its flags (id, stage, target, flags), the flight target.
    -- Each target is written as its three naturally aligned 4-byte members (x, y, z): a 12-byte member can straddle a
    -- page boundary (records move inside their component arrays as other entities come and go; live, 44.9 s into an
    -- orbit), and the guarded transaction keeps every target inside one page. The six members change in the same
    -- transaction, between two game updates, so the flight never reads a half-written target.
    local identity_b={component='Behavior',component_type='native',unique_owner=true,owner_count=1}
    local identity_f={component='Flight',component_type='native',unique_owner=true,owner_count=1}
    local changes={}
    for k,axis in ipairs({'x','y','z'})do
        local from,to=(k-1)*4+1,k*4
        changes[#changes+1]={label='pelican.'..tostring(entity)..'.target.'..axis,owner=owner,
            offset=record.address+P+F.target+(k-1)*4-owner.base,expected=expect.behaviour:sub(from,to),
            desired=desired:sub(from,to),before=expect.behaviour:sub(from,to),already_desired=false,identity=identity_b,
            chain={}}
        changes[#changes+1]={label='pelican.'..tostring(entity)..'.flight_target.'..axis,owner=flight_owner,
            offset=t.flight_record+FT.target+(k-1)*4-flight_owner.base,expected=expect.flight:sub(from,to),
            desired=desired:sub(from,to),before=expect.flight:sub(from,to),already_desired=false,identity=identity_f,
            chain={}}
    end
    local plan={snapshots={
            {owner=owner,offset=record.address-owner.base,bytes=record.raw:sub(1,P+F.flags+4)},
            {owner=flight_owner,offset=t.flight_record+FT.target-flight_owner.base,bytes=expect.flight}},
        changes=changes}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('pelicans.retargets')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local after=M.targets(world,entity)
    local now=M.read(world,entity)
    local result={entity=entity,target=point,raw=desired,writes=report.writes,verify={
        behaviour=after~=nil and after.raw.behaviour==desired,flight=after~=nil and after.raw.flight==desired,
        stage=now~=nil and now.stage==6 and now.released==true,nonTarget=report.non_target_bytes_unchanged==true,
        protection=report.protection_restored==true}}
    local verified=true
    for _,v in pairs(result.verify)do if v~=true then verified=false end end
    result.verified=verified
    return result
end

------------------------------------------------------------------------------------------------- the orbit --
-- M.orbit(entity, spec, callback): a development orbit of one Runtime Pelican around a centre, by retargets of its
-- hover point (OrbitProof; not public). It waits until the Pelican is held (released in stage 6, its hold applied),
-- then every `interval` s of game time moves the target along a horizontal circle `radius` m around `center`,
-- `altitude` m above it:
--   mode 'sweep': the target's angle advances continuously, one lap every `period` s;
--   mode 'steps': the target jumps `step` degrees once the Pelican is within `near` m of it (horizontally), the
--   extraction Pelican's own rule (its behaviour 202 steps pi/4 within 5 m), here on the normal transport flight;
--   mode 'lead': the target is always `lead` m ahead of the Pelican along the circle (from its own current angle), a
--   look-ahead point on the tangent side, so the flight heads along the circle rather than chasing a clock.
-- It starts at the Pelican's own bearing from the centre, from where it hovers: during the first `entry` s (ENTRY) the
-- circle's radius and its height above the centre grow smoothly (smoothstep) from the Pelican's own (about 0 m out and
-- its hover height) to `radius` and `altitude`, so it spirals out and climbs while it starts to turn, then holds them
-- (ESTABLISHED). The same update interval throughout: no extra writes. After `duration` s it puts back the hover point it found
-- (the game's own), so the hold ends and the departure is the game's. It stops at once, never fighting, when the stage
-- leaves 6 (the game's departure), the target changes under it (another writer), a retarget is refused, the Pelican is
-- gone or the mission ends. callback(event): 'started' {center, theta0, home}, 'sample' (every second: angle (deg,
-- unwrapped from the start), radius, height, speed, target_distance, stage, writes), 'stopped' {reason, writes,
-- refusals, stats}. Returns the orbit, or nil and why.
M.ORBIT={radius={5,150},altitude={10,150},duration={1,120},interval={0.05,2},period={10,600},step={10,120},near={2,40},
    entry={0,60},lead={1,80}}
local orbits={}
function M.orbit(entity,spec,callback)
    if type(spec)~='table'then return nil,'spec is required'end
    local c=spec.center
    if not(type(c)=='table'and finite_coordinate(c.x)and finite_coordinate(c.y)and finite_coordinate(c.z))then
        return nil,'spec.center must be world coordinates'
    end
    local mode=spec.mode or'sweep'
    if mode~='sweep'and mode~='steps'and mode~='lead'then return nil,"spec.mode must be 'sweep', 'steps' or 'lead'"end
    local s={center={x=c.x,y=c.y,z=c.z},mode=mode,direction=spec.direction==-1 and-1 or 1,radius=spec.radius,
        altitude=spec.altitude,duration=spec.duration,interval=spec.interval or 0.25,period=spec.period or 30,
        step=spec.step or 45,near=spec.near or 8,entry=spec.entry or 15,lead=spec.lead or 10,
        label=type(spec.label)=='string'and spec.label or'orbit'}
    for key,range in pairs(M.ORBIT)do
        local v=s[key]
        if not(finite(v)and v>=range[1]and v<=range[2])then
            return nil,('spec.%s must be %s to %s'):format(key,tostring(range[1]),tostring(range[2]))
        end
    end
    if s.entry>=s.duration then return nil,'spec.entry must be shorter than spec.duration'end
    if orbits[entity]and orbits[entity].status~='complete'then return nil,'Pelican '..tostring(entity)..' already orbits'end
    local o={status='waiting',entity=entity,spec=s,writes=0,refusals=0}
    orbits[entity]=o
    local function emit(event)
        if callback then
            local okc,err=pcall(callback,event)
            if not okc then log('orbit callback failed: '..tostring(err))end
        end
    end
    local st={n=0,rmin=nil,rmax=nil,rsum=0,hmin=nil,hmax=nil,hsum=0,ssum=0}
    local function stop(reason,world)
        if o.status=='complete'then return end
        local was=o.status
        o.status='complete'
        local elapsed=o.t0 and o.now and(o.now-o.t0)/US or 0
        local stats={samples=st.n,radius={min=st.rmin,max=st.rmax,mean=st.n>0 and st.rsum/st.n or nil},
            height={min=st.hmin,max=st.hmax,mean=st.n>0 and st.hsum/st.n or nil},speed=st.n>0 and st.ssum/st.n or nil,
            degrees=o.turned or 0,laps=(o.turned or 0)/360,seconds=elapsed,
            angular=elapsed>0 and(o.turned or 0)/elapsed or nil}
        log(('ORBIT STOPPED: Pelican %s (%s): %s; %s; %d retargets, %d refused; %.0f degrees in %.1f s (%.2f laps)')
            :format(tostring(entity),s.label,reason,was=='waiting'and'it never started'or'it was orbiting',o.writes,
            o.refusals,stats.degrees,elapsed,stats.laps))
        emit({kind='stopped',entity=entity,reason=reason,writes=o.writes,refusals=o.refusals,stats=stats})
        if orbits[entity]==o then orbits[entity]=nil end
    end
    local function angle_of(p)return math.atan2(p.y-s.center.y,p.x-s.center.x)end
    -- The circle at `elapsed` s: during the entry the radius and the height grow (smoothstep) from where it hovered.
    local function shape(elapsed)
        if s.entry<=0 or elapsed>=s.entry then return s.radius,s.altitude,1 end
        local u=elapsed/s.entry
        local e=u*u*(3-2*u)
        return s.radius*e,o.h0+(s.altitude-o.h0)*e,e
    end
    local function point_at(theta,elapsed)
        local radius,height=shape(elapsed)
        return {x=s.center.x+radius*math.cos(theta),y=s.center.y+radius*math.sin(theta),z=s.center.z+height}
    end
    local function write(world,point,t)
        local okr,r,code,reason=pcall(M.retarget,world,entity,t.raw,point)
        if not okr then
            o.refusals=o.refusals+1
            stop('a retarget raised an error (nothing more is written): '..tostring(r),world)
            return
        end
        if r then
            o.writes=o.writes+1
            o.written=r.raw
            o.target=point
            if not r.verified then stop('a retarget was not verified',world)end
            return true
        end
        o.refusals=o.refusals+1
        emit({kind='refused',entity=entity,code=code,reason=reason})
        stop('a retarget was refused: '..tostring(code)..': '..tostring(reason),world)
    end
    local function tick()
        local world=world_module.open()
        if not world then return end
        local game=world_module.game_state(world)
        if not(game and game.mission)then return stop('the mission ended')end
        local p=M.read(world,entity)
        if not p then return stop('the Pelican is gone')end
        local now=M.clock(world)
        if not now then return end
        o.now=now
        local mine=owned[entity]
        if o.status=='waiting'then
            if p.stage and p.stage>=7 then return stop('it departed before the orbit started (stage '..p.stage..')',world)end
            if mine and mine.hold_refused then return stop('its hold was refused: '..tostring(mine.hold_refused),world)end
            if not(p.stage==6 and p.released and mine and mine.held)then return end
            local t,why=M.targets(world,entity)
            if not t then return stop('its targets are unreadable: '..tostring(why),world)end
            o.status='orbiting'
            o.t0,o.last,o.home,o.home_raw=now,nil,t.flight,t.raw
            -- The entry starts from its own hover: its target's height above the centre (at least 0).
            o.h0=math.max(0,math.min(s.altitude,(t.flight and t.flight.z or s.center.z)-s.center.z))
            o.phase='entry'
            o.theta0=p.position and math.sqrt((p.position.x-s.center.x)^2+(p.position.y-s.center.y)^2)>1
                and angle_of(p.position)or 0
            o.k,o.turned,o.prev_angle,o.prev_pos,o.prev_t,o.next_sample=0,0,p.position and angle_of(p.position),
                p.position,now,now+US
            log(('ORBIT STARTED: Pelican %s (%s): %s mode, centre %s, radius %.1f m, %.1f m above it, %.1f s, a target '
                ..'every %.2f s%s; entry %.1f s from %.1f m up; its hover point %s kept for the end'):format(
                tostring(entity),s.label,s.mode,text(s.center),s.radius,s.altitude,s.duration,s.interval,
                s.mode=='sweep'and(', one lap every '..s.period..' s')or s.mode=='lead'and(', '..s.lead..' m ahead')
                or(', '..s.step..' degrees within '..s.near..' m'),
                s.entry,o.h0,text(o.home)))
            emit({kind='started',entity=entity,center=s.center,theta0=math.deg(o.theta0),home=o.home,entry=s.entry,
                from_height=o.h0})
        end
        if o.status~='orbiting'then return end
        if p.stage~=6 then return stop('the game ended the hold (stage '..tostring(p.stage)..')',world)end
        local elapsed=(now-o.t0)/US
        -- Measure: the Pelican's angle around the centre (unwrapped), its radius, height and speed.
        local out=p.position and math.sqrt((p.position.x-s.center.x)^2+(p.position.y-s.center.y)^2)
        if p.position and out>=s.radius*0.5 then
            -- (the angle is counted once it is out on the circle: near the centre its bearing means nothing)
            local a=angle_of(p.position)
            if o.prev_angle then
                local d=a-o.prev_angle
                if d>math.pi then d=d-2*math.pi elseif d<-math.pi then d=d+2*math.pi end
                o.turned=o.turned+math.deg(d)*s.direction
            end
            o.prev_angle=a
        end
        if p.position then
            if now>=o.next_sample then
                local radius=math.sqrt((p.position.x-s.center.x)^2+(p.position.y-s.center.y)^2)
                local height=p.position.z-s.center.z
                local dt=(now-o.prev_t)/US
                local speed=o.prev_pos and dt>0 and math.sqrt((p.position.x-o.prev_pos.x)^2+(p.position.y-o.prev_pos.y)^2)
                    /dt or 0
                if elapsed>=s.entry then   -- the statistics are the established circle's
                    st.n=st.n+1;st.rsum=st.rsum+radius;st.hsum=st.hsum+height;st.ssum=st.ssum+speed
                    st.rmin=math.min(st.rmin or radius,radius);st.rmax=math.max(st.rmax or radius,radius)
                    st.hmin=math.min(st.hmin or height,height);st.hmax=math.max(st.hmax or height,height)
                end
                o.prev_pos,o.prev_t,o.next_sample=p.position,now,now+US
                local want_r,want_h=shape(elapsed)
                emit({kind='sample',entity=entity,seconds=elapsed,angle=o.turned,radius=radius,height=height,speed=speed,
                    target=o.target,target_distance=o.target and M.distance(p.position,o.target)or nil,stage=p.stage,
                    writes=o.writes,position=p.position,phase=elapsed<s.entry and'entry'or'established',
                    asked_radius=want_r,asked_height=want_h})
            end
        end
        local t,why=M.targets(world,entity)
        if not t then return stop('its targets are unreadable: '..tostring(why),world)end
        if o.written and t.raw.flight~=o.written then
            return stop('OVERWRITTEN: its flight target changed under the orbit (another writer); not fought',world)
        end
        if elapsed>=s.duration then
            -- The end: its own hover point back; the hold, then the game's departure, follow.
            if write(world,o.home,t)then
                return stop(('the duration (%.1f s) is over: its hover point %s is back; the hold and the game\'s '
                    ..'departure follow'):format(s.duration,text(o.home)),world)
            end
            return
        end
        if o.last and elapsed-o.last<s.interval then return end
        if o.phase=='entry'and elapsed>=s.entry then
            o.phase='established'
            emit({kind='established',entity=entity,seconds=elapsed})
        end
        local theta
        if s.mode=='lead'then
            -- `lead` m ahead along the circle (the circle's current radius during the entry), from its own angle.
            local radius=shape(elapsed)
            local here=p.position and math.sqrt((p.position.x-s.center.x)^2+(p.position.y-s.center.y)^2)>1
                and angle_of(p.position)or(o.last_theta or o.theta0)
            theta=here+s.direction*s.lead/math.max(radius,5)
            o.last_theta=theta
        elseif s.mode=='sweep'then
            theta=o.theta0+s.direction*2*math.pi*elapsed/s.period
        else
            if o.target and p.position and math.sqrt((p.position.x-o.target.x)^2+(p.position.y-o.target.y)^2)<=s.near
            then o.k=o.k+1 end
            theta=o.theta0+s.direction*math.rad(s.step)*o.k
            if o.target and o.k==o.k_written then o.last=elapsed;return end
        end
        o.last=elapsed
        if write(world,point_at(theta,elapsed),t)then o.k_written=o.k end
    end
    function o.tick()if o.status~='complete'then tick()end end
    function o.cancel()stop('cancelled')end
    scheduler.attach(o)
    return o
end
function M.orbiting(entity)return orbits[entity]end

------------------------------------------------------------------------------------------- read-only variants --
-- Research "variants", "extraction" and "turretComponents" (docs/research/pelican-cas-F5FEE03DCFDB.md, "Pelican
-- variants"): read-only diagnostics for the probes; nothing here writes.
local VS=D.variants.settings
local BY_RESOURCE={}
for name,v in pairs(D.variants.byType)do BY_RESOURCE[v.resource]=name end
M.variant_name=function(hex)return hex and BY_RESOURCE[hex]end
-- The behaviour an entity type gets by default (the component world's behaviour settings), or nil.
function M.type_behaviour(world,hex)
    local cworld=world.view.pointer(world.game+SP.world)
    local tab=cworld and world.view.pointer(cworld+VS.offset)
    if not tab or tab==0 then return nil end
    local key=b.unhex(hex):reverse()
    local lo,hi=b.u32(key,0),b.u32(key,4)
    local slot=((hi%VS.slots)*(4294967296%VS.slots)+lo%VS.slots)%VS.slots
    for _=1,VS.slots do
        local raw=world.view.read(tab+slot*VS.slotStride,VS.slotStride)
        if not raw then return nil end
        local k=raw:sub(1,8)
        if k==key then
            local entry=world.view.read(tab+VS.entries+b.u32(raw,8)*VS.entryStride,4)
            return entry and b.u32(entry,0)
        end
        if k==string.rep('\0',8)then return nil end
        slot=(slot+1)%VS.slots
    end
end
-- Every live entity whose Behavior record runs one of `ids` ({[id] = true}): {[entity] = {entity, behaviour, stage,
-- pending, flags, target, landing (P+0x1B0), resource (hex), variant (a name or nil), position}}.
function M.behaviours(world,ids)
    local component=world.view.pointer(world.game+BC.global)
    local raw=component and world.view.read(component+BC.keys,BC.multiplier+4-BC.keys)
    if not raw then return nil,'the Behavior component is unreadable'end
    local ok,keys=pcall(b.pointer,raw,0)
    local cap=b.u32(raw,BC.capacity-BC.keys)
    local empty=b.u32(raw,BC.empty-BC.keys)
    local records=world.view.pointer(component+BC.records)
    local handles=world.view.pointer(component+BC.handles)
    if not(ok and keys~=0 and records and records~=0 and cap>0 and cap<=65536)then return nil,'unreadable'end
    local out={}
    local P=BC.context
    for k=0,cap-1 do
        local slot=world.view.read(keys+k*8,8)
        if not slot then break end
        local entity,index=b.u32(slot,0),b.u32(slot,4)
        if entity~=empty and index~=4294967295 then
            local head=world.view.read(records+index*BC.stride,4)
            local id=head and b.u32(head,0)
            if id and ids[id]then
                local rec=world.view.read(records+index*BC.stride,BC.stride)
                local handle=handles and world.view.pointer(handles+index*8)
                local res=handle and handle~=0 and world.view.read(handle,8)
                local hex=res and b.hex(res:reverse()):upper()
                out[entity]={entity=entity,behaviour=id,index=index,stage=b.u32(rec,P+F.stage),
                    pending=b.u32(rec,P+F.pending),flags=b.u32(rec,P+F.flags),target=vec(rec,P+F.target),
                    landing=vec(rec,P+D.extraction.landingPoint),resource=hex,variant=hex and BY_RESOURCE[hex],
                    position=M.position(world,entity),raw=rec}
            end
        end
    end
    return out
end
-- Which weapon-side components (mount, turret, projectileWeapon, weaponData) hold an entity: {[name] = index}.
function M.weapon_components(world,entity)
    local out={}
    for name,c in pairs(D.turretComponents)do
        local component=world.view.pointer(world.game+c.global)
        if component and component~=0 then
            local index=index_of(world,component,{keys=c.map,capacity=c.map+8,empty=c.map+0xC,multiplier=c.map+0x10},
                entity)
            if index then out[name]=index end
        end
    end
    return out
end

-- An entity's pose (research "pose"), read-only: {position, rotation = {x, y, z, w}, forward = the rotation's Y axis
-- (a unit's forward), yaw (degrees, atan2 of the forward in the ground plane), pitch (degrees)}, or nil.
function M.pose(world,entity)
    local component=world.view.pointer(world.game+XC.global)
    local index=component and index_of(world,component,XC,entity)
    local records=index and world.view.pointer(component+XC.records)
    local raw=records and records~=0 and world.view.read(records+index*XC.stride+D.pose.rotation,0x20)
    if not raw then return nil end
    local x,y,z,w=f32(raw,0),f32(raw,4),f32(raw,8),f32(raw,12)
    local position=vec(raw,D.pose.position-D.pose.rotation)
    if not(finite(x)and finite(y)and finite(z)and finite(w)and position)then return nil end
    -- The Y axis of the rotation (a unit's forward; the spawn pose's second row).
    local fx,fy,fz=2*(x*y-w*z),1-2*(x*x+z*z),2*(y*z+w*x)
    local flat=math.sqrt(fx*fx+fy*fy)
    return {position=position,rotation={x=x,y=y,z=z,w=w},forward={x=fx,y=fy,z=fz},
        yaw=math.deg(math.atan2(fy,fx)),pitch=math.deg(math.atan2(fz,flat))}
end
-- An entity's Behavior handle, read-only: {resource (hex), entity, link (+0xC: what a mounted child's attachable record
-- names as its parent), network (+0x10)}, or nil.
function M.handle(world,entity)
    local component=world.view.pointer(world.game+BC.global)
    local index=component and index_of(world,component,BC,entity)
    local handles=index and world.view.pointer(component+BC.handles)
    local handle=handles and handles~=0 and world.view.pointer(handles+index*8)
    local raw=handle and handle~=0 and world.view.read(handle,0x18)
    if not raw then return nil end
    return {resource=b.hex(raw:sub(1,8):reverse()):upper(),entity=b.u32(raw,8),link=b.u32(raw,D.attachment.handleLink),
        network=b.u32(raw,0x10)}
end
-- The address of an entity's own world record (its Behavior handle: +0 resource, +8 entity, +0xC unit link, +0x10
-- network id, +0x14 flags), read-only, or nil.
function M.record_address(world,entity)
    local component=world.view.pointer(world.game+BC.global)
    local index=component and index_of(world,component,BC,entity)
    local handles=index and world.view.pointer(component+BC.handles)
    local handle=handles and handles~=0 and world.view.pointer(handles+index*8)
    local raw=handle and handle~=0 and world.view.read(handle,0x18)
    if not(raw and b.u32(raw,8)==entity)then return nil end
    return handle,raw
end
-- A mounted child's attachable record (research "attachment"), read-only: {index, link (its parent's handle link),
-- node, position, rotation, raw (0xAC)}, or nil when it is not attachable.
function M.attachable(world,entity)
    local A=D.attachment
    local component=world.view.pointer(world.game+A.global)
    if not component or component==0 then return nil end
    local index=index_of(world,component,{keys=A.map,capacity=A.map+8,empty=A.map+0xC,multiplier=A.map+0x10},entity)
    local records=index and world.view.pointer(component+A.records)
    local raw=records and records~=0 and world.view.read(records+index*A.stride,A.stride)
    if not raw then return nil end
    return {index=index,link=b.u32(raw,A.parentLink),node=b.u32(raw,A.parentNode),position=vec(raw,A.worldPosition),
        rotation={x=f32(raw,A.worldRotation),y=f32(raw,A.worldRotation+4),z=f32(raw,A.worldRotation+8),
            w=f32(raw,A.worldRotation+12)},raw=raw}
end
-- What a turret fires and what of it is per instance (research "turretWeapon", docs/research/pelican-cas-F5FEE03DCFDB.md
-- section 15), read-only: {flags (its weapon record), path ('heat': its resolved ProjectileWeapon +0; 'magazine': the
-- chambered type, re-derived after every shot from the pattern or the resolved ProjectileWeapon +0; 'rounds'; 'other'),
-- heat, windUp (true when it has those components), interval (s: its instance record, set once at creation), rpm
-- (60 / interval), currentRpm, rofSlots {x, y, z}, rofIndex, copy (its own resolved ProjectileWeapon {projectileType,
-- rpm}, or nil: it uses its type's shared record), magazine {rounds, pattern, chambered, length, copy (true when it has
-- its own resolved magazine)} or nil}, or nil when it is not a projectile weapon.
local TW=D.turretWeapon
local function map_at(at)return {keys=at,capacity=at+8,empty=at+0xC,multiplier=at+0x10}end
local function held(world,c,entity)
    local component=world.view.pointer(world.game+c.global)
    if not component or component==0 then return nil end
    return component,index_of(world,component,map_at(c.map),entity)
end
local function flag(flags,bit)return math.floor(flags/bit)%2==1 end
-- The chin turret's and the Gatling Sentry's type values (mission snapshots): {chinTurret, gatlingSentry} = {projectileType,
-- rpmSlots, magazinePattern, pattern, capacity}.
M.turret_types=TW.observed
function M.weapon_config(world,entity)
    local PW,MG,W=TW.projectileWeapon,TW.magazine,TW.weapon
    local pw,index=held(world,PW,entity)
    if not index then return nil end
    local instances,rof,current=world.view.pointer(pw+PW.instances),world.view.pointer(pw+PW.rof),
        world.view.pointer(pw+PW.current)
    local interval=instances and instances~=0 and world.view.read(instances+index*PW.instanceStride+PW.interval,4)
    local rec=rof and rof~=0 and world.view.read(rof+index*PW.rofStride,PW.rofStride)
    local cur=current and current~=0 and world.view.read(current+index*PW.currentStride+PW.currentRpm,4)
    local out={index=index,interval=interval and f32(interval,0),currentRpm=cur and f32(cur,0),
        rofSlots=rec and vec(rec,PW.rofSlots),rofIndex=rec and b.u32(rec,PW.rofIndex)}
    if finite(out.interval)and out.interval>0 then out.rpm=60/out.interval end
    local ci=index_of(world,pw,map_at(PW.copies),entity)
    local copies=ci and world.view.pointer(pw+PW.copyRecords)
    local copy=copies and copies~=0 and world.view.read(copies+ci*PW.copyStride,0x10)
    if copy then out.copy={projectileType=b.u32(copy,PW.projectileType),rpm=vec(copy,PW.rpmSlots)}end
    local wm,wi=held(world,W,entity)
    local records=wi and world.view.pointer(wm+W.records)
    local flags=records and records~=0 and world.view.read(records+wi*W.stride+W.flags,4)
    out.flags=flags and b.u32(flags,0)
    out.path=not out.flags and'other'or flag(out.flags,W.heat)and'heat'or flag(out.flags,W.magazine)and'magazine'
        or flag(out.flags,W.rounds)and'rounds'or'other'
    out.heat=select(2,held(world,TW.heat,entity))~=nil
    out.windUp=select(2,held(world,TW.windUp,entity))~=nil
    local mg,mi=held(world,MG,entity)
    local mrecords=mi and world.view.pointer(mg+MG.records)
    local m=mrecords and mrecords~=0 and world.view.read(mrecords+mi*MG.stride,MG.stride)
    if m then
        out.magazine={rounds=b.u32(m,MG.rounds),pattern=b.u32(m,MG.pattern)~=0,chambered=b.u32(m,MG.chambered),
            length=b.u32(m,MG.patternLength),copy=index_of(world,mg,map_at(MG.copies),entity)~=nil}
    end
    return out
end

------------------------------------------------------------------------------------------------- the watch --
-- M.watch(spec, callback): every Runtime update until the mission ends. spec = {hold = seconds (optional: hold every
-- Pelican seen released; one attempt each), label}. callback(event):
--   'seen' {pelican, frame, clock, cargo = {resource, spawned}}: the first update a Pelican exists;
--   'cargo' {entity, spawned, updates, seconds}: its cargo appeared after it was first seen (a window existed);
--   'stage' {entity, from, to, seconds}; 'released' {entity, stage, hover (s since the hover start), seconds, target,
--   position}; 'held' {entity, result}; 'hold_refused' {entity, code, reason};
--   'departing' {entity, stage, after_release}; 'gone' {entity, seconds, after_release, after_departing, held};
--   'ended'.
-- Returns the watch, or nil and why.
local active
function M.watch(spec,callback)
    spec=spec or{}
    if spec.hold~=nil and not(finite(spec.hold)and spec.hold>0 and spec.hold<=M.HOLD_MAX_SECONDS)then
        return nil,'spec.hold must be above 0 and at most '..M.HOLD_MAX_SECONDS..' s'
    end
    local label=type(spec.label)=='string'and spec.label or'Pelican watch'
    if active and active.status=='active'then
        active.status='cancelled'
        log(('WATCH REPLACED: "%s" stopped; "%s" now runs (one Pelican watch at a time)'):format(active.label,label))
    end
    local w={status='active',pelicans={},label=label,hold=spec.hold}
    local function emit(event)
        if callback then
            local ok,err=pcall(callback,event)
            if not ok then log('callback failed: '..tostring(err))end
        end
    end
    local function tick()
        local world=world_module.open()
        if not world then return end
        local game=world_module.game_state(world)
        if not(game and game.mission)then
            if w.seen then w.seen=false;w.pelicans={};emit({kind='ended',reason='the mission ended'})end
            return
        end
        w.seen=true
        local list=M.list(world)
        if not list then return end
        w.frame=(w.frame or 0)+1
        local now=M.clock(world)
        local function seconds(from)return now and from and from>0 and(now-from)/US or nil end
        for entity,p in pairs(list)do
            local s=w.pelicans[entity]
            if not s then
                s={first=w.frame,first_clock=now,stage=p.stage,behaviour=p.behaviour,cargo=p.cargo,
                    spawned=p.cargo_spawned,first_position=p.position}
                w.pelicans[entity]=s
                emit({kind='seen',pelican=p,frame=w.frame,clock=now,cargo={resource=p.cargo,spawned=p.cargo_spawned}})
            else
                if p.cargo_spawned and not s.spawned then
                    s.spawned=p.cargo_spawned
                    emit({kind='cargo',entity=entity,spawned=p.cargo_spawned,updates=w.frame-s.first,
                        seconds=seconds(s.first_clock)})
                end
                if p.stage~=s.stage then
                    emit({kind='stage',entity=entity,from=s.stage,to=p.stage,seconds=seconds(s.first_clock),
                        target=p.target,position=p.position})
                    s.stage=p.stage
                end
            end
            if release_wait(p)and not s.released then
                s.released=now
                emit({kind='released',entity=entity,stage=p.stage,hover=p.stage==6 and seconds(p.times.hover)or nil,
                    seconds=seconds(s.first_clock),since_release=seconds(p.times.release),target=p.target,
                    position=p.position})
                if w.hold and not s.hold_attempted and not owned[entity]then   -- a Runtime Pelican: its own hold
                    s.hold_attempted=true
                    local result,code,reason=M.hold(world,entity,{behaviour=s.behaviour,release=p.release_raw},w.hold)
                    if result then s.held=result;emit({kind='held',entity=entity,result=result})
                    else emit({kind='hold_refused',entity=entity,code=code,reason=reason})end
                end
            end
            if p.stage and p.stage>=8 and p.stage<=11 and not s.departing then
                s.departing=now
                emit({kind='departing',entity=entity,stage=p.stage,after_release=seconds(s.released),
                    position=p.position})
            end
        end
        for entity,s in pairs(w.pelicans)do
            if not list[entity]then
                w.pelicans[entity]=nil
                emit({kind='gone',entity=entity,seconds=seconds(s.first_clock),after_release=seconds(s.released),
                    after_departing=seconds(s.departing),held=s.held})
            end
        end
    end
    function w.tick()if w.status=='active'then tick()end end
    function w.cancel()w.status='cancelled';if active==w then active=nil end end
    active=w
    scheduler.attach(w)
    return w
end
function M.reset_for_tests()
    if active then active.status='cancelled'end
    active=nil
    proven={}
    if manager then manager.status='cancelled'end
    manager=nil;queue={};owned={}
    for _,o in pairs(orbits)do o.status='complete'end
    orbits={}
end
return M
