-- The per-beacon redirect (development only; research/docs/beacon-redirect-F5FEE03DCFDB.md). Not exported by
-- api/hd2.lua and no public field reaches it.
--
-- research/beacon-redirect-F5FEE03DCFDB.json: a thrown stratagem is a beacon. The manager is
-- [game+0x346BF98] + 0x40 + 0x1380; each beacon has a 0x40-byte element whose +0xC is its stratagem TYPE and a
-- 0x8E8-byte state (+0x8E0 mode, +0x8E4 activated). The game reads the element's type when the beacon activates and
-- passes it to the spawn dispatcher, which only then reads that type's row (its delivery kind and payload list). Type
-- 0 reads the all-zero default row: nothing is spawned. The type is replicated only at the beacon's creation; a later
-- change stays on this machine.
--
-- The call-in timing (read-only here): the beacon's countdown (+0x0) and threshold (+0x4) are computed ONCE at its
-- creation from the carrier's row (call-in +0x54 with the player's and the mission's modifiers, the delivery time,
-- linger +0x60). Every update with state subtracts the frame time; the activation is the crossing of the threshold; the
-- beacon is removed below zero. So the call-in delay is countdown - threshold and the life after activation is the
-- threshold, and a redirected beacon keeps the CARRIER's timing. The element's +0x3C is set when the countdown starts
-- (the first update with state), not at the activation.
--
-- M.arm watches every Runtime update. In the update a beacon of the carrier type is FIRST seen, it writes that one
-- beacon's +0xC once, from the carrier type to the target type (or 0, neutral): one guarded 4-byte transaction with the
-- exact carrier type as its expectation and the beacon's threshold, its member +0x8 and its entity handle as context.
-- Guards (refused with nothing written, never retried):
--   * the pins; in a mission, as host, solo;
--   * carrier and target catalogued by stable id; the target's call-in package resident (requested when armed);
--   * the beacon still there, the same entity at the same index and array, its type exactly the carrier, not activated
--     (state +0x8E4), its countdown not below its threshold (the crossing not passed), not a remote copy (state mode
--     +0x8E0 2), not already redirected.
-- Afterwards it reads the type back and checks every other member it read (except the countdown) is unchanged, then
-- watches the beacon to its activation and reports the type the game passed, the dispatcher's own record (the type and
-- payload it was given, the spawn request) and the timing.
--
-- spec.timing (optional; the timing proof): the same transaction also sets that beacon's countdown (+0x0) and threshold
-- (+0x4) to the given target timing (atomic with the type: one guarded transaction, three changes, in the same update).
-- Extra guards: a target timing (threshold > 0, countdown >= threshold, both at most 120 s); the beacon's timers
-- exactly the values observed when it was first seen; no earlier timing write. Read back: countdown, threshold, type.
--
-- No StratagemInfo, payload record, mission record or shared data is written; nothing needs restoring (a beacon is
-- consumed by its activation and removed below zero). With spec.observe, every other beacon and every barrage instance
-- (its shells fired, its start and its end) are reported read-only.
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local core_assets=require('hd2runtime/core/assets')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local D=require('hd2runtime/domains/beacon_redirect')
local PD=require('hd2runtime/domains/bombardment_payload')   -- the game clock and the bombardment manager (read-only)
local M={}
local MG,EL,ST=D.manager,D.element,D.state
local MK,DR,TR=D.marker,D.dispatch,D.timing.row

local function log(text)log_module.emit('[HD2Runtime] beacon redirect '..text)end
local function u32(n)return b.encode(n,'u32')end
local function f32(bytes,o)local ok,v=pcall(b.value,bytes,o,'f32');return ok and v or nil end

local proven={}
function M.prove(world)
    if D.source.gameDllSha256~=profile.dll_sha then return nil,'the beacon research covers another game.dll build'end
    if proven[world.game]then return true end
    for _,pin in ipairs(D.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,('beacon code changed (%s at game+%X)'):format(pin.label,pin.rva)
        end
    end
    proven[world.game]=true
    return true
end

-- The beacon manager: {address, count, active, entities, state, elements}, or nil and why.
function M.manager(world)
    local w=world.view.pointer(world.game+D.path.world)
    local address=w and w+D.path.systems+D.path.beacons
    local raw=address and world.view.read(address,0x80)
    if not raw then return nil,'the beacon manager is unreadable'end
    local count,active,cap=b.u32(raw,MG.count),b.u32(raw,MG.active),b.u32(raw,MG.mapCapacity)
    if count>4096 or active>4096 or cap==0 or cap>65536 or(cap%2~=0 and cap~=1)then
        return nil,'the beacon manager is implausible'
    end
    local ok1,entities=pcall(b.pointer,raw,MG.entities)
    local ok2,state=pcall(b.pointer,raw,MG.state)
    local ok3,elements=pcall(b.pointer,raw,MG.elements)
    if not(ok1 and ok2 and ok3 and elements~=0)then return nil,'the beacon arrays are unreadable'end
    return {address=address,count=count,active=active,entities=entities,state=state,elements=elements}
end
-- One beacon: {index, entity, address, raw (0x40), type, countdown, threshold, flag, counting, activated, mode (nil:
-- no state yet)}, or nil.
function M.beacon(world,m,i)
    if i>=m.count then return nil end
    local address=m.elements+i*EL.stride
    local raw=world.view.read(address,EL.stride)
    local handle=world.view.pointer(m.entities+i*8)
    local entity=handle and world.view.u32(handle+8)
    if not(raw and entity)then return nil end
    local activated,mode=false,nil
    if i<m.active then
        local flag=world.view.read(m.state+i*ST.stride+ST.activated,1)
        if not flag then return nil end
        activated=flag:byte()~=0
        mode=world.view.u32(m.state+i*ST.stride+ST.mode)
    end
    -- activated: the state's +0x8E4 (set at the crossing, right before the dispatcher). counting: the element's +0x3C,
    -- set in the first update with state, when the countdown starts (0x6AB879), NOT at the activation.
    return {index=i,entity=entity,address=address,raw=raw,type=b.u32(raw,EL.type),countdown=f32(raw,EL.countdown),
        threshold=f32(raw,EL.threshold),flag=raw:byte(EL.flag+1),counting=raw:byte(EL.flag+1)~=0,activated=activated,
        mode=mode,handle_slot=m.entities+i*8}
end
-- Every beacon now, by entity.
function M.beacons(world)
    local m,why=M.manager(world)
    if not m then return nil,why end
    local out={}
    for i=0,m.count-1 do
        local it=M.beacon(world,m,i)
        if it then out[it.entity]=it end
    end
    return out,m
end

local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base and address+size<=r.base+r.size)
    then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end
-- The type's stable id resolved to this build's type number, or nil.
local function type_of(world,name)
    local entry=catalog.stratagems[name]
    local id=entry and entry.root and entry.root.id
    return id and loadout.type_of(world,id),id
end
M.type_of=type_of

------------------------------------------------------------------------------------------ read-only observation --
-- The game clock (u64 microseconds), or nil.
function M.clock(world)
    local object=world.view.pointer(world.game+PD.clock.global)
    local raw=object and world.view.read(object+PD.clock.time,8)
    return raw and b.u32(raw,0)+b.u32(raw,4)*4294967296
end
-- A type's call-in members: {callIn (+0x54), linger (+0x60), kind (+0x3C), category (+0xB8), follows (+0x170 bit 1)},
-- or nil (type 0 and unknown types).
function M.row_timing(world,kind)
    if type(kind)~='number'or kind<=0 or kind>=profile.stratagem.entries then return nil end
    local row=world.view.pointer(world.game+profile.stratagem.table_rva+kind*8)
    local raw=row and world.view.read(row,0x180)
    if not raw then return nil end
    return {callIn=f32(raw,TR.callIn),linger=f32(raw,TR.linger),kind=b.u32(raw,TR.kind),category=b.u32(raw,TR.category),
        follows=raw:byte(TR.follows+1)%4>=2}
end
-- The marker component's OWN type for a beacon entity (its colour comes from that type's category), or nil.
function M.marker_type(world,entity)
    if type(entity)~='number'then return nil end
    local mgr=world.view.pointer(world.game+MK.global)
    local raw=mgr and world.view.read(mgr+MK.keys,MK.multiplier+4-MK.keys)
    if not raw then return nil end
    local ok,keys=pcall(b.pointer,raw,0)
    local cap,empty,mult=b.u32(raw,MK.capacity-MK.keys),b.u32(raw,MK.empty-MK.keys),b.u32(raw,MK.multiplier-MK.keys)
    if not(ok and keys~=0 and cap>0 and cap<=65536)then return nil end
    local start=world_module.mul32(entity,mult)
    for probe=0,cap-1 do
        local slot=world.view.read(keys+((start+probe)%cap)*8,8)
        if not slot then return nil end
        local key=b.u32(slot,0)
        if key==entity then
            local elements=world.view.pointer(mgr+MK.elements)
            return elements and world.view.u32(elements+b.u32(slot,4)*MK.stride+MK.type)
        end
        if key==empty then return nil end
    end
end
-- What the dispatcher recorded for beacon i (in its state; the element's waves): {payload ('0x...'), called, type,
-- waveType, spawn, requested (spawn == 10), waves}, or nil (no state yet, unreadable).
function M.dispatch_record(world,m,i)
    if not(m and i and i<m.active)then return nil end
    local at=m.state+i*ST.stride
    local payload,called=world.view.read(at+DR.payload,8),world.view.read(at+DR.called,1)
    local kind,wave,spawn=world.view.u32(at+DR.type),world.view.u32(at+DR.waveType),world.view.u32(at+DR.spawn)
    local waves=world.view.u32(m.elements+i*EL.stride+DR.elementWaves)
    if not(payload and called and kind and wave and spawn and waves)then return nil end
    return {payload=b.resource(payload,0),called=called:byte(),type=kind,waveType=wave,spawn=spawn,
        requested=spawn==DR.spawnRequested,waves=waves}
end
-- The bombardment manager's instances: {total, barrages, by = {[payload '0x...'] = n}, list = {{index, entity,
-- payload, fired (shells fired), left (shells left in the salvo), salvos (salvos left), salvoTimer, removal (its removal
-- timer), aim = {x, y, z}}}}, or nil.
local BI=D.bombardment
function M.bombardment(world)
    local MGR=PD.manager
    local manager=world.view.pointer(world.game+MGR.global)
    if not manager then return nil end
    local total,barrages=world.view.u32(manager+MGR.instances),world.view.u32(manager+MGR.barrages)
    if not(total and barrages and total<=4096 and barrages<=4096)then return nil end
    local handles=world.view.pointer(manager+MGR.handles)
    local states,timers=world.view.pointer(manager+BI.states),world.view.pointer(manager+BI.removalTimers)
    local by,list={},{}
    for i=0,math.max(total,barrages)-1 do
        local handle=handles and world.view.pointer(handles+i*8)
        local head=handle and world.view.read(handle+MGR.handleHash,16)
        if not head then return nil end
        local key=b.resource(head,0)
        by[key]=(by[key]or 0)+1
        local state=states and world.view.read(states+i*BI.stride,BI.stride)
        local timer=timers and world.view.read(timers+i*4,4)
        list[#list+1]={index=i,entity=b.u32(head,8),payload=key,fired=state and b.u32(state,BI.shellsFired),
            left=state and b.u32(state,BI.shellsLeft),salvos=state and b.u32(state,BI.salvosLeft),
            salvoTimer=state and f32(state,BI.salvoTimer),removal=timer and f32(timer,0),
            aim=state and{f32(state,BI.aim),f32(state,BI.aim+4),f32(state,BI.aim+8)}}
    end
    return {total=total,barrages=barrages,by=by,list=list}
end

------------------------------------------------------------------------------------------------- the write --
local done={}         -- [entity] = true once attempted (never retried)
local timed={}        -- [entity] = true once its timers were written

local MAX_SECONDS=120
-- Whether a target timing is usable: true, or nil and why.
local function timing_valid(t)
    local c,h=type(t)=='table'and t.countdown,type(t)=='table'and t.threshold
    if not(type(c)=='number'and type(h)=='number'and c==c and h==h)then return nil,'no target countdown and threshold'end
    if not(h>0 and c>=h and c<=MAX_SECONDS)then
        return nil,('target countdown %s / threshold %s: needs threshold > 0, countdown >= threshold, countdown <= %d s'
            ):format(tostring(c),tostring(h),MAX_SECONDS)
    end
    return true
end
M.timing_valid=timing_valid

-- The guards and the write for one beacon, in the update it was first seen. spec = {carrierType, targetType, resident,
-- timing = {countdown, threshold} (optional)}; observed = the beacon's 8 timer bytes (+0x0, +0x4) as first seen
-- (required with spec.timing). Returns the applied result or nil, code, reason.
function M.redirect_now(world,spec,entity,observed)
    if spec.timing and timed[entity]then
        return nil,'TIMING_ALREADY','beacon '..tostring(entity)..'\'s timers were already written'
    end
    if done[entity]then return nil,'ALREADY_REDIRECTED','beacon '..tostring(entity)..' was already attempted'end
    done[entity]=true
    if spec.timing then
        local valid,invalid=timing_valid(spec.timing)
        if not valid then return nil,'TIMING_INVALID',invalid end
        if type(observed)~='string'or#observed~=8 then
            return nil,'TIMING_UNEXPECTED','the carrier\'s timers as first seen are not known'
        end
    end
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','beacons are redirected in a mission only'end
    if game.host~=true then return nil,'NOT_HOST','development proof: host only'end
    local record,code,reason=slots.local_record(world)
    if not record then return nil,code,reason end
    if record.records~=1 then return nil,'NOT_SOLO','solo only: '..record.records..' stratagem records'end
    if spec.targetType~=0 and not spec.resident then
        return nil,'TARGET_NOT_RESIDENT','the target\'s call-in package is not resident'
    end
    local m
    m,why=M.manager(world)
    if not m then return nil,'UNAVAILABLE',tostring(why)end
    local it
    for i=0,m.count-1 do
        local candidate=M.beacon(world,m,i)
        if candidate and candidate.entity==entity then it=candidate;break end
    end
    if not it then return nil,'GONE','beacon '..tostring(entity)..' is not in the beacon manager'end
    if it.type~=spec.carrierType then
        return nil,'NOT_THE_CARRIER',('beacon %s holds type %d, not the carrier type %d'):format(tostring(entity),it.type,
            spec.carrierType)
    end
    if it.activated then return nil,'ACTIVATED','beacon '..tostring(entity)..' has already activated'end
    -- The dispatcher runs only at the crossing (before >= threshold > after) with "activated" clear: a countdown below
    -- the threshold means the crossing has passed.
    if not(it.countdown and it.threshold)or it.countdown<it.threshold then
        return nil,'CROSSED',('beacon %s: its countdown %s is below its threshold %s: the activation has passed'):format(
            tostring(entity),tostring(it.countdown),tostring(it.threshold))
    end
    if it.mode==2 then return nil,'REMOTE','beacon '..tostring(entity)..' is a remote copy (state mode 2)'end
    local timers=it.raw:sub(EL.countdown+1,EL.threshold+4)
    if spec.timing then
        -- The carrier's timers exactly as first seen (this update: the game has not run between).
        if timers~=observed then
            return nil,'TIMING_UNEXPECTED',('beacon %s: its countdown/threshold changed since it was first seen'):format(
                tostring(entity))
        end
        if not(it.threshold>0)then
            return nil,'TIMING_UNEXPECTED',('beacon %s: its threshold %s is not positive'):format(tostring(entity),
                tostring(it.threshold))
        end
    end
    local owner=owner_of(world,it.address,EL.stride)
    local handle_owner=owner_of(world,it.handle_slot,8)
    local handle_bytes=world.view.read(it.handle_slot,8)
    if not(owner and handle_owner and handle_bytes)then
        return nil,'NOT_PRIVATE','the beacon arrays are not in private read-write memory'
    end
    local identity={component='StratagemBeacon',component_type='native',unique_owner=true,owner_count=1}
    local function change(label,offset,expected,desired)
        return {label='beacon.'..tostring(entity)..'.'..label,owner=owner,offset=it.address+offset-owner.base,
            expected=expected,desired=desired,before=expected,already_desired=false,identity=identity,chain={}}
    end
    local changes,context_at,context={},nil,nil
    local want_countdown,want_threshold
    if spec.timing then
        -- Type and timers in one transaction: the whole timer/type head (+0x0..+0xF) as context.
        want_countdown,want_threshold=b.encode(spec.timing.countdown,'f32'),b.encode(spec.timing.threshold,'f32')
        context_at,context=it.address+EL.countdown,it.raw:sub(EL.countdown+1,EL.type+4)
        if want_countdown~=timers:sub(1,4)then
            changes[#changes+1]=change('countdown',EL.countdown,timers:sub(1,4),want_countdown)
        end
        if want_threshold~=timers:sub(5,8)then
            changes[#changes+1]=change('threshold',EL.threshold,timers:sub(5,8),want_threshold)
        end
    else
        -- The type alone, with the threshold, +0x8 and the type as context.
        context_at,context=it.address+EL.threshold,it.raw:sub(EL.threshold+1,EL.type+4)
    end
    changes[#changes+1]=change('type',EL.type,u32(spec.carrierType),u32(spec.targetType))
    local plan={snapshots={{owner=owner,offset=context_at-owner.base,bytes=context},
            {owner=handle_owner,offset=it.handle_slot-handle_owner.base,bytes=handle_bytes}},changes=changes}
    if spec.timing then timed[entity]=true end
    local report=transaction.apply(world.runtime,plan)
    metrics.count('beacon_redirect.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local after=world.view.read(it.address,EL.stride)
    local others=after~=nil
    if after then
        -- Every member but the countdown (+0x0: the game's own, unless written here), the threshold when written and
        -- the type.
        others=after:sub(EL.type+5)==it.raw:sub(EL.type+5)
            and after:sub(EL.threshold+5,EL.type)==it.raw:sub(EL.threshold+5,EL.type)
            and(spec.timing~=nil or after:sub(EL.threshold+1,EL.threshold+4)==it.raw:sub(EL.threshold+1,EL.threshold+4))
    end
    local result={status='applied',entity=entity,index=it.index,address=it.address,from=spec.carrierType,
        to=spec.targetType,countdown=it.countdown,threshold=it.threshold,writes=report.writes,
        verify={type=after~=nil and b.u32(after,EL.type)==spec.targetType,others=others,
            nonTarget=report.non_target_bytes_unchanged==true,protection=report.protection_restored==true}}
    local timing_text=''
    if spec.timing then
        result.timing={from={countdown=it.countdown,threshold=it.threshold},
            to={countdown=f32(want_countdown,0),threshold=f32(want_threshold,0)}}
        result.verify.countdown=after~=nil and after:sub(EL.countdown+1,EL.countdown+4)==want_countdown
        result.verify.threshold=after~=nil and after:sub(EL.threshold+1,EL.threshold+4)==want_threshold
        timing_text=('; countdown %.3f -> %.3f, threshold %.3f -> %.3f, timers read back %s'):format(it.countdown,
            result.timing.to.countdown,it.threshold,result.timing.to.threshold,
            tostring(result.verify.countdown and result.verify.threshold))
    end
    log(('APPLIED: beacon %s (index %d): type %d -> %d%s; %d write%s; type reads back %s; its other members unchanged '
        ..'%s; non-target bytes unchanged %s; protection restored %s'):format(tostring(entity),it.index,spec.carrierType,
        spec.targetType,timing_text,report.writes,report.writes==1 and''or's',tostring(result.verify.type),
        tostring(others),tostring(result.verify.nonTarget),tostring(result.verify.protection)))
    return result
end

------------------------------------------------------------------------------------------------- the watch --
local armed   -- {spec, callback, watch, gate, beacons = {[entity] = state}}
local function emit(a,event)
    if a.callback then
        local ok,why=pcall(a.callback,event)
        if not ok then log('callback failed: '..tostring(why))end
    end
end

local function finish(a,reason)
    emit(a,{kind='ended',reason=reason})
    a.watch.status='complete'
    if armed==a then armed=nil end
end

-- Barrage instances (read-only, with spec.observe): each new instance is attributed to the beacon(s) that activated in
-- the same update (the dispatcher spawns it during the activation); 'bombardment' events: 'created' (its start delay,
-- aim, salvos), 'fired' (its first shell), 'ended' (shells fired, first and last shell, its life). Instances present when
-- the watch starts are baseline only.
local function track_barrages(a,world,now,seconds)
    local bombs=M.bombardment(world)
    if not bombs then return end
    local seen={}
    local fresh=a.instances==nil
    a.instances=a.instances or{}
    for _,it in ipairs(bombs.list)do
        seen[it.entity]=true
        local s=a.instances[it.entity]
        if not s then
            s={payload=it.payload,first_clock=now,baseline=fresh,fired=it.fired or 0,salvos=it.salvos,
                beacons=a.activated_now}
            a.instances[it.entity]=s
            if not fresh then
                emit(a,{kind='bombardment',phase='created',entity=it.entity,payload=it.payload,beacons=s.beacons,
                    startDelay=it.salvoTimer,salvos=it.salvos,left=it.left,fired=it.fired,aim=it.aim,clock=now})
            end
        elseif not s.baseline then
            if(it.fired or 0)>s.fired then
                if s.fired==0 then
                    s.first_shell=now
                    emit(a,{kind='bombardment',phase='fired',entity=it.entity,payload=s.payload,beacons=s.beacons,
                        after=seconds(s.first_clock),clock=now})
                end
                s.last_shell=now
                s.fired=it.fired
            end
            s.salvos=it.salvos
        end
    end
    for entity,s in pairs(a.instances)do
        if not seen[entity]then
            a.instances[entity]=nil
            if not s.baseline then
                emit(a,{kind='bombardment',phase='ended',entity=entity,payload=s.payload,beacons=s.beacons,
                    shells=s.fired,life=seconds(s.first_clock),first=s.first_shell and(s.first_shell-s.first_clock)/1e6,
                    last=s.last_shell and(s.last_shell-s.first_clock)/1e6,clock=now})
            end
        end
    end
end

local function tick(a,dt)
    local world=world_module.open()
    if not world then return end
    if not a.resolved then
        local ok,why=M.prove(world)
        if not ok then
            emit(a,{kind='refused',code='UNSUPPORTED_BUILD',reason=tostring(why)})
            return finish(a,'refused: unsupported build')
        end
        local carrierType,carrierId=type_of(world,a.spec.carrier)
        local targetType,targetId=0,nil
        if not a.spec.neutral then targetType,targetId=type_of(world,a.spec.target)end
        if not(carrierType and targetType and carrierType~=targetType)then
            emit(a,{kind='refused',code='UNKNOWN_STRATAGEM',reason='carrier and target must be different catalogued '
                ..'stratagems with rows on this build'})
            return finish(a,'refused: unknown stratagem')
        end
        a.spec.carrierType,a.spec.targetType=carrierType,targetType
        a.resolved=true
        local dependency=targetId and core_assets.dependency_for_stratagem(targetId,a.spec.target)
        if targetId and not dependency then
            emit(a,{kind='refused',code='ASSET_UNAVAILABLE',reason='no call-in package is known for '..a.spec.target})
            return finish(a,'refused: no target package')
        end
        a.dependency=dependency
        if not dependency then a.spec.resident=true end
        emit(a,{kind='armed',carrier=a.spec.carrier,carrierType=carrierType,target=a.spec.neutral and'neutral (type 0)'
            or a.spec.target,targetType=targetType,package=dependency and dependency.name,
            carrierTiming=M.row_timing(world,carrierType),targetTiming=M.row_timing(world,targetType)})
    end
    local game=world_module.game_state(world)
    if not(game and game.mission)then
        if a.beacons_seen then return finish(a,'the mission ended')end
        return
    end
    a.beacons_seen=true
    if a.dependency and not a.spec.resident then
        local ok,state=pcall(core_assets.state,world.runtime,a.dependency.package)
        if ok and state=='resident'then
            a.spec.resident=true
            emit(a,{kind='ready',package=a.dependency.name})
        else
            a.gate=a.gate or core_assets.gate(world.runtime,{id='beacon-redirect-target',
                asset_dependencies={a.dependency}},log_module.emit)
            local result,why=a.gate.tick(dt or 0)
            if result=='ready'then
                a.spec.resident=true
                emit(a,{kind='ready',package=a.dependency.name})
            elseif result=='failed'then
                emit(a,{kind='refused',code='ASSET_UNAVAILABLE',reason=tostring(why)})
                return finish(a,'refused: the target package did not load')
            end
        end
    end
    local list,m=M.beacons(world)
    if not list then return end
    a.frame=(a.frame or 0)+1
    local now=M.clock(world)
    local function seconds(from)return now and from and(now-from)/1e6 or nil end
    a.activated_now={}
    for entity,it in pairs(list)do
        local s=a.beacons[entity]
        if not s then
            -- First seen: the timers as created (the carrier's), the dispatcher's record so far and the marker's type.
            s={first=a.frame,first_clock=now,type=it.type,countdown=it.countdown,threshold=it.threshold,
                stateful=it.mode~=nil,activations=0,activated=it.activated==true,carrier=it.type==a.spec.carrierType,
                baseline=M.dispatch_record(world,m,it.index),marker=M.marker_type(world,entity)}
            a.beacons[entity]=s
            local event={entity=entity,index=it.index,type=it.type,countdown=it.countdown,threshold=it.threshold,
                activated=it.activated,counting=it.counting,mode=it.mode,address=it.address,frame=a.frame,clock=now,
                marker=s.marker,timing=M.row_timing(world,it.type)}
            if s.carrier then
                event.kind='created'
                emit(a,event)
                if it.activated then
                    s.missed=true
                    emit(a,{kind='missed',entity=entity,reason='first seen already activated'})
                else
                    -- The first update this beacon is seen: the only attempt. With spec.timing, its target timing
                    -- (spec.timing(world, beacon) -> {countdown, threshold, source} or nil and why) goes into the same
                    -- transaction; without one, nothing is written.
                    local result,code,reason
                    if a.spec.timing then
                        local target,why=a.spec.timing(world,it)
                        if target then
                            result,code,reason=M.redirect_now(world,setmetatable({timing=target},{__index=a.spec}),entity,
                                it.raw:sub(EL.countdown+1,EL.threshold+4))
                            if result then result.timing.source=target.source end
                        else
                            done[entity]=true
                            code,reason='NO_TARGET_TIMING',tostring(why or'no target timing')
                        end
                    else
                        result,code,reason=M.redirect_now(world,a.spec,entity)
                    end
                    if result then
                        s.applied=result
                        result.kind='applied'
                        result.frame=a.frame
                        emit(a,result)
                    else
                        s.refused=code
                        emit(a,{kind='refused',entity=entity,code=code,reason=reason})
                    end
                end
            elseif a.spec.observe then
                event.kind,event.phase='observed','created'
                emit(a,event)
            end
        else
            if s.carrier and s.applied and s.activations==0 and it.type~=a.spec.targetType and not s.reverted then
                s.reverted=true
                emit(a,{kind='reverted',entity=entity,value=it.type,frame=a.frame})
            end
            -- A beacon first seen in flight has no state yet: its record's baseline is taken once it has one.
            if not s.baseline and it.mode~=nil and not it.activated then s.baseline=M.dispatch_record(world,m,it.index)end
            if it.activated and not s.activated then
                -- An activation (a further wave clears "activated" and activates again).
                s.activated=true
                s.activations=s.activations+1
                a.activated_now[#a.activated_now+1]=entity
                s.activated_clock=s.activated_clock or now
                local event={entity=entity,type=it.type,n=s.activations,updates=a.frame-s.first,frame=a.frame,
                    seconds=seconds(s.first_clock),countdown=it.countdown,threshold=it.threshold,
                    first_countdown=s.countdown,first_threshold=s.threshold,stateful=s.stateful,
                    dispatch=M.dispatch_record(world,m,it.index),before=s.baseline,marker=M.marker_type(world,entity),
                    carrierMarker=s.marker,clock=now}
                s.baseline=event.dispatch
                if s.carrier then
                    event.kind='activated'
                    event.redirected=s.applied~=nil and it.type==a.spec.targetType
                    event.applied=s.applied~=nil
                    emit(a,event)
                elseif a.spec.observe then
                    event.kind,event.phase='observed','activated'
                    emit(a,event)
                end
            elseif s.activated and not it.activated then
                s.activated=false
            end
        end
    end
    for entity,s in pairs(a.beacons)do
        if not list[entity]then
            a.beacons[entity]=nil
            local event={entity=entity,type=s.type,activated=s.activations>0,activations=s.activations,
                applied=s.applied~=nil,updates=a.frame-s.first,seconds=seconds(s.first_clock),
                after=seconds(s.activated_clock),threshold=s.threshold,clock=now}
            if s.carrier then
                event.kind='gone'
                emit(a,event)
            elseif a.spec.observe then
                event.kind,event.phase='observed','gone'
                emit(a,event)
            end
        end
    end
    if a.spec.observe then track_barrages(a,world,now,seconds)end
end

-- Arms the redirect: spec = {carrier = name, target = name} or {carrier = name, neutral = true}; observe = true also
-- reports every other beacon and every barrage instance (read-only); timing = function(world, beacon) -> {countdown,
-- threshold, source} or nil and why: the target timing written with the type (not with neutral). Watches every update
-- until the mission ends. callback(event): 'armed' (with both rows' call-in members), 'ready' (the target's package
-- resident), 'created' (a carrier beacon first seen: its timers, marker type, row timing), 'applied' (verify; timing
-- {from, to, source} when written), 'refused' (code, reason), 'missed', 'reverted', 'activated' (the type the game
-- had; n; updates and seconds after first seen; the dispatcher's record before and after; the marker's type; clock),
-- 'gone' (seconds after first seen and after the activation), 'observed' (phase 'created', 'activated' or 'gone' for
-- any other beacon), 'bombardment' (phase 'created', 'fired' or 'ended' for a barrage instance, with the beacons that
-- activated in its update), 'ended'. Returns the watch, or nil and why.
function M.arm(spec,callback)
    if type(spec)~='table'or type(spec.carrier)~='string'or not(spec.neutral==true or type(spec.target)=='string')then
        return nil,'spec must name the carrier and the target (or neutral = true)'
    end
    if spec.timing~=nil and(type(spec.timing)~='function'or spec.neutral==true)then
        return nil,'spec.timing must be a function, and needs a target (not neutral)'
    end
    if armed then armed.watch.status='cancelled';armed=nil end
    local a={spec={carrier=spec.carrier,target=spec.target,neutral=spec.neutral==true,observe=spec.observe==true,
        timing=spec.timing},callback=callback,beacons={}}
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled';if armed==a then armed=nil end end
    function watch.tick(dt)if watch.status=='active'then tick(a,dt)end end
    a.watch=watch
    armed=a
    scheduler.attach(watch)
    return watch
end
function M.armed()return armed~=nil and armed.watch.status=='active'end
function M.disarm()if armed then armed.watch.cancel()end end
function M.reset_for_tests()if armed then armed.watch.status='cancelled'end;armed=nil;proven={};done={};timed={}end
return M
