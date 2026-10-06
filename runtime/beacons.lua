-- The development beacon API (docs/research/beacon-redirect-F5FEE03DCFDB.md, "The beacon API"). Not exported by
-- api/hd2.lua yet: it becomes public only after its own live proof (proof/BeaconTimingProof).
--
-- A thrown stratagem is a beacon with three independent per-call properties the API exposes semantically:
--   * its carrier: the stratagem that created it (read-only: the type it was created with);
--   * its delivery: the stratagem the dispatcher executes when it activates (the beacon's type; 'none' = the empty
--     default row: nothing is spawned). Live-proven: Eagle Strafing Run and AC-8 Autocannon -> Orbital 120mm HE Barrage;
--   * its timing, in seconds:
--       call_in_time              = countdown - activation threshold: the time from now to the activation, counted
--                                   once the beacon has landed (the countdown runs only then);
--       lifetime_after_activation = the activation threshold: how long the beacon itself remains after its
--                                   activation (its beam). A 120mm barrage runs on its own and does not depend on it.
--     Both are computed once at the beacon's creation from the carrier's row; the API can set them per beacon.
-- Raw countdown / activation_threshold are readable, and settable as an explicit alternative to the semantic pair.
--
-- Every change is ONE guarded transaction on that beacon's element (the countdown +0x0, the threshold +0x4, the type
-- +0xC, whichever change), in the update it is asked for. Refused, with nothing written, unless: the beacon pins prove;
-- a mission, as host, solo; the beacon is present (the same entity), holds the expected type, is not activated, is not
-- a copy owned by another machine (no state here) or in a state mode other than 1; its current timers are sane (threshold > 0, countdown >= threshold) and, when given, exactly the
-- values the caller observed; a new delivery's call-in package is resident; the resulting timers are sane (threshold
-- > 0, countdown >= threshold, countdown <= 120 s). Afterwards every written member is read back, the others compared,
-- the non-target bytes checked and the protection restored. No StratagemInfo, component or payload record is written.
--
-- Scope: per beacon, on the machine whose beacon update runs its activation (the host in a solo or hosted game).
-- The type and threshold are replicated only at the beacon's creation; the countdown is re-sent every update.
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local core_assets=require('hd2runtime/core/assets')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local redirect=require('hd2runtime/runtime/beacon_redirect')   -- its proven readers (no write is used from it)
local D=require('hd2runtime/domains/beacon_redirect')
local M={}
local EL=D.element
M.MAX_SECONDS=120

local function log(text)log_module.emit('[HD2Runtime] beacon '..text)end
local function f32(bytes,o)local ok,v=pcall(b.value,bytes,o,'f32');return ok and v or nil end
local function finite(v)return type(v)=='number'and v==v and v~=math.huge and v~=-math.huge end

-- The stratagem a name or type means on this build: type, name (catalogued by stable id), or nil.
local names_by_id={}
for name,entry in pairs(catalog.stratagems)do if entry.root then names_by_id[entry.root.id]=name end end
function M.resolve(world,what)
    if what=='none'or what==0 then return 0,'none'end
    if type(what)=='number'then
        local id=loadout.id_of(world,what)
        return id and what or nil,id and names_by_id[id]
    end
    local entry=type(what)=='string'and catalog.stratagems[what]
    local id=entry and entry.root and entry.root.id
    local kind=id and loadout.type_of(world,id)
    return kind,kind and what
end
local function name_of(world,kind)
    if kind==0 then return'none'end
    local id=loadout.id_of(world,kind)
    return id and names_by_id[id]or('type '..tostring(kind))
end

-- A beacon's timing (seconds): {countdown, activation_threshold, call_in_time, lifetime_after_activation}.
function M.timing_of(it)
    return {countdown=it.countdown,activation_threshold=it.threshold,
        call_in_time=it.countdown and it.threshold and it.countdown-it.threshold,lifetime_after_activation=it.threshold}
end
-- The timers a timing change asks for, from the current ones. change: {call_in_time, lifetime_after_activation} (either
-- or both; the other is kept) or {countdown, activation_threshold} (explicit; either or both). Returns countdown,
-- threshold, or nil, code, reason.
function M.plan_timing(countdown,threshold,change)
    local semantic=change.call_in_time~=nil or change.lifetime_after_activation~=nil
    local explicit=change.countdown~=nil or change.activation_threshold~=nil
    if semantic and explicit then
        return nil,'TIMING_INVALID','give call_in_time/lifetime_after_activation or countdown/activation_threshold, not both'
    end
    local c,h
    if semantic then
        local call_in=change.call_in_time
        if call_in==nil then call_in=countdown-threshold end
        h=change.lifetime_after_activation
        if h==nil then h=threshold end
        if not(finite(call_in)and call_in>=0)then return nil,'TIMING_INVALID','call_in_time must be >= 0 seconds'end
        c=h+call_in
    else
        c=change.countdown;if c==nil then c=countdown end
        h=change.activation_threshold;if h==nil then h=threshold end
    end
    if not(finite(c)and finite(h)and h>0 and c>=h and c<=M.MAX_SECONDS)then
        return nil,'TIMING_INVALID',('countdown %s / activation threshold %s: needs threshold > 0, countdown >= threshold, '
            ..'countdown <= %d s'):format(tostring(c),tostring(h),M.MAX_SECONDS)
    end
    return c,h
end

-- A beacon's position as its activation uses it (its state's +0x30: the dispatcher's spawn position, 0x6ABC46),
-- {x, y, z}; or nil (gone, no state yet, unreadable). Read-only.
function M.position(world,entity)
    local m=redirect.manager(world)
    if not m then return nil end
    for i=0,m.active-1 do
        local it=redirect.beacon(world,m,i)
        if it and it.entity==entity then
            local raw=world.view.read(m.state+i*D.state.stride+D.state.position,12)
            local x,y,z=raw and f32(raw,0),raw and f32(raw,4),raw and f32(raw,8)
            if finite(x)and finite(y)and finite(z)then return {x=x,y=y,z=z}end
            return nil
        end
    end
end

local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base and address+size<=r.base+r.size)
    then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end
-- The resident state of EVERY call-in package of a delivery (the mission loader's list: a support weapon's comes from
-- its weapon): true, or nil, code, reason. A delivery with no known package is refused: its assets cannot be proven
-- loaded (never assumed to need nothing).
local function delivery_resident(world,kind)
    if kind==0 then return true end
    local id=loadout.id_of(world,kind)
    local name=name_of(world,kind)
    local dependencies=id and core_assets.dependencies_for_stratagem(id,name)
    if not dependencies then
        return nil,'DELIVERY_NOT_RESIDENT','no call-in package is known for '..name..': its assets cannot be proven loaded'
    end
    if not core_assets.call_in_complete(name)then
        return nil,'DELIVERY_NOT_RESIDENT','the call-in packages of '..name..' are not all known'
    end
    for _,dependency in ipairs(dependencies)do
        local ok,state=pcall(core_assets.state,world.runtime,dependency.package)
        if not(ok and state=='resident')then
            return nil,'DELIVERY_NOT_RESIDENT',('the %s is not resident (%s)'):format(dependency.name,
                tostring(ok and state or'unreadable'))
        end
    end
    return true
end
M.delivery_resident=delivery_resident

-- Change one beacon in one guarded transaction. expect = {type = its current type (required), timers = the 8 timer
-- bytes as observed (optional, exact)}; change = {delivery = name | type | 'none', call_in_time,
-- lifetime_after_activation | countdown, activation_threshold}. Returns {entity, index, delivery {from, to}, timing
-- {from, to}, writes, verify {...}} or nil, code, reason.
function M.apply(world,entity,expect,change)
    if type(expect)~='table'or type(expect.type)~='number'then return nil,'INVALID','expect.type is required'end
    if type(change)~='table'then return nil,'INVALID','no change'end
    local ok,why=redirect.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','beacons are changed in a mission only'end
    -- A beacon this machine OWNS (NOT_OWNED below): the host, or a client inside the client-write proof.
    local hcode,hwhy=require('hd2runtime/runtime/multiplayer').host_guard(game,expect.client==true,
        'development API: host only')
    if hcode then return nil,hcode,hwhy end
    local record,code,reason=slots.local_record(world)
    if not record then return nil,code,reason end
    -- Only a beacon owned here is changed (NOT_OWNED below): the thrower's machine runs its activation; the change is
    -- never sent (expect.multiplayer: a custom stratagem call, runtime/multiplayer.lua).
    local scode,swhy=require('hd2runtime/runtime/multiplayer').solo_guard(record.records,expect.multiplayer==true,
        'a changed delivery stays on this machine')
    if scode then return nil,scode,swhy end
    local m
    m,why=redirect.manager(world)
    if not m then return nil,'UNAVAILABLE',tostring(why)end
    local it
    for i=0,m.count-1 do
        local candidate=redirect.beacon(world,m,i)
        if candidate and candidate.entity==entity then it=candidate;break end
    end
    if not it then return nil,'GONE','beacon '..tostring(entity)..' is not in the beacon manager'end
    if expect.index~=nil and it.index~=expect.index then
        return nil,'MOVED',('beacon %s is at index %d, not %d'):format(tostring(entity),it.index,expect.index)
    end
    if it.type~=expect.type then
        return nil,'UNEXPECTED_TYPE',('beacon %s holds type %d, not %d'):format(tostring(entity),it.type,expect.type)
    end
    if it.activated then return nil,'ACTIVATED','beacon '..tostring(entity)..' has already activated'end
    -- Only the machine that owns a beacon (its thrower's) keeps its state (the owned instances come first, below +0x38)
    -- and runs its activation; a copy without state belongs to another machine. State mode 1 is the normal countdown;
    -- 0 is blocked (its owner destroys it) and 2 hands the delivery to the host (Resupply, Portable Hellbomb, mission
    -- rows: row +0x78 bit 3 or +0x94).
    if it.mode==nil then
        return nil,'NOT_OWNED','beacon '..tostring(entity)..' is a copy owned by another machine (no state here)'
    end
    if it.mode~=1 then
        return nil,'NOT_NORMAL_MODE',('beacon %s is in state mode %d (0 blocked, 2 delivered by the host)'):format(
            tostring(entity),it.mode)
    end
    if not(it.threshold and it.countdown and it.threshold>0)then
        return nil,'TIMING_UNEXPECTED',('beacon %s: its threshold %s is not positive'):format(tostring(entity),
            tostring(it.threshold))
    end
    if it.countdown<it.threshold then
        return nil,'CROSSED',('beacon %s: its countdown %.3f is below its threshold %.3f: the activation has passed'):format(
            tostring(entity),it.countdown,it.threshold)
    end
    local timers=it.raw:sub(EL.countdown+1,EL.threshold+4)
    if expect.timers~=nil and expect.timers~=timers then
        return nil,'TIMING_UNEXPECTED','beacon '..tostring(entity)..'\'s timers changed since they were observed'
    end
    -- The delivery.
    local to_type
    if change.delivery~=nil then
        to_type=M.resolve(world,change.delivery)
        if not to_type then return nil,'UNKNOWN_DELIVERY','not a catalogued stratagem on this build: '..tostring(change.delivery)end
        local resident,rcode,rwhy=delivery_resident(world,to_type)
        if not resident then return nil,rcode,rwhy end
    end
    -- The timing.
    local timing_change=change.call_in_time~=nil or change.lifetime_after_activation~=nil or change.countdown~=nil
        or change.activation_threshold~=nil
    local want_c,want_h
    if timing_change then
        local c,h,tcode=M.plan_timing(it.countdown,it.threshold,change)
        if not c then return nil,h,tcode end
        want_c,want_h=b.encode(c,'f32'),b.encode(h,'f32')
    end
    if to_type==nil and not timing_change then return nil,'INVALID','the change changes nothing'end
    local owner=owner_of(world,it.address,EL.stride)
    local handle_owner=owner_of(world,it.handle_slot,8)
    local handle_bytes=world.view.read(it.handle_slot,8)
    if not(owner and handle_owner and handle_bytes)then
        return nil,'NOT_PRIVATE','the beacon arrays are not in private read-write memory'
    end
    local identity={component='StratagemBeacon',component_type='native',unique_owner=true,owner_count=1}
    local changes={}
    local function add(label,offset,expected,desired)
        if expected==desired then return end
        changes[#changes+1]={label='beacon.'..tostring(entity)..'.'..label,owner=owner,
            offset=it.address+offset-owner.base,expected=expected,desired=desired,before=expected,already_desired=false,
            identity=identity,chain={}}
    end
    if want_c then
        add('countdown',EL.countdown,timers:sub(1,4),want_c)
        add('activation_threshold',EL.threshold,timers:sub(5,8),want_h)
    end
    if to_type~=nil then add('delivery',EL.type,b.encode(it.type,'u32'),b.encode(to_type,'u32'))end
    if #changes==0 then return nil,'ALREADY_DESIRED','the beacon already has this delivery and timing'end
    local plan={snapshots={{owner=owner,offset=it.address+EL.countdown-owner.base,bytes=it.raw:sub(EL.countdown+1,EL.type+4)},
            {owner=handle_owner,offset=it.handle_slot-handle_owner.base,bytes=handle_bytes}},changes=changes}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('beacons.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local after=world.view.read(it.address,EL.stride)
    local result={entity=entity,index=it.index,writes=report.writes,
        verify={nonTarget=report.non_target_bytes_unchanged==true,protection=report.protection_restored==true}}
    local others=after~=nil
        and after:sub(EL.threshold+5,EL.type)==it.raw:sub(EL.threshold+5,EL.type)        -- +0x8
        and after:sub(EL.type+5)==it.raw:sub(EL.type+5)                                   -- +0x10..+0x3F
    if after and not want_c then
        others=others and after:sub(EL.threshold+1,EL.threshold+4)==it.raw:sub(EL.threshold+1,EL.threshold+4)
    end
    if after and to_type==nil then others=others and after:sub(EL.type+1,EL.type+4)==it.raw:sub(EL.type+1,EL.type+4)end
    result.verify.others=others
    if to_type~=nil then
        result.delivery={from=it.type,to=to_type,from_name=name_of(world,it.type),to_name=name_of(world,to_type)}
        result.verify.delivery=after~=nil and b.u32(after,EL.type)==to_type
    end
    if want_c then
        result.timing={from=M.timing_of(it),to=M.timing_of({countdown=f32(want_c,0),threshold=f32(want_h,0)})}
        result.verify.timing=after~=nil and after:sub(1,4)==want_c and after:sub(5,8)==want_h
    end
    local verified=true
    for _,v in pairs(result.verify)do if v~=true then verified=false end end
    result.verified=verified
    log(('APPLIED: beacon %s (index %d)%s%s; %d write%s; verified %s (read back, other members unchanged %s, non-target '
        ..'bytes unchanged %s, protection restored %s)'):format(tostring(entity),it.index,result.delivery
        and(': delivery '..result.delivery.from_name..' -> '..result.delivery.to_name)or'',result.timing
        and(('%s call-in %.3f -> %.3f s, lifetime after activation %.3f -> %.3f s'):format(result.delivery and','or':',
        result.timing.from.call_in_time,result.timing.to.call_in_time,result.timing.from.lifetime_after_activation,
        result.timing.to.lifetime_after_activation))or'',report.writes,report.writes==1 and''or's',tostring(verified),
        tostring(others),tostring(result.verify.nonTarget),tostring(result.verify.protection)))
    return result
end

------------------------------------------------------------------------------------------------- the watch --
-- M.watch(spec, callback): every Runtime update until the mission ends. spec = {carrier = name (only beacons created
-- as this stratagem) or nil (every beacon), decide = function(beacon) -> change or nil, prepare = {delivery names whose
-- call-in packages are requested at the start}}. In the update a carrier beacon is FIRST seen, decide(beacon) is
-- called with {entity, index, carrier (name), type, timing, landed} and its change is applied in that same update
-- (expecting the type and the exact timers just read). callback(event): 'ready' (the prepared packages resident),
-- 'created', 'applied', 'refused', 'activated' (the delivery type the game had; seconds after first seen; timing then;
-- clock), 'gone' (seconds after its activation), 'ended'. Every beacon is tracked; non-carrier beacons are reported
-- with observed = true. Returns the watch, or nil and why.
local active
function M.watch(spec,callback)
    spec=spec or{}
    if spec.decide~=nil and type(spec.decide)~='function'then return nil,'spec.decide must be a function'end
    local label=type(spec.label)=='string'and spec.label or(spec.carrier and('watch for '..spec.carrier)or'watch')
    if active and active.status=='active'then
        -- One beacon watch at a time (two would race for the same beacons): the newest replaces the older one, loudly.
        active.status='cancelled'
        log(('WATCH REPLACED: "%s" stopped; "%s" now runs (only one beacon watch at a time: install one beacon proof)')
            :format(active.label,label))
    end
    local w={status='active',beacons={},gates={},label=label}
    local function emit(event)
        if callback then
            local ok,err=pcall(callback,event)
            if not ok then log('callback failed: '..tostring(err))end
        end
    end
    local prepared=false
    local function tick(dt)
        local world=world_module.open()
        if not world then return end
        local game=world_module.game_state(world)
        if not(game and game.mission)then
            if w.seen then w.status='complete';emit({kind='ended',reason='the mission ended'})end
            return
        end
        w.seen=true
        if w.carrier_type==nil and spec.carrier then
            w.carrier_type=M.resolve(world,spec.carrier)
            if not w.carrier_type then
                w.status='complete'
                emit({kind='refused',code='UNKNOWN_STRATAGEM',reason='not a catalogued stratagem: '..tostring(spec.carrier)})
                return
            end
        end
        -- Request the prepared deliveries' call-in packages through the Runtime's loader (once ready, 'ready').
        if not prepared then
            prepared=true
            for _,name in ipairs(spec.prepare or{})do
                local kind=M.resolve(world,name)
                local id=kind and loadout.id_of(world,kind)
                for _,dependency in ipairs(id and core_assets.dependencies_for_stratagem(id,name)or{})do
                    local ok,state=pcall(core_assets.state,world.runtime,dependency.package)
                    if not(ok and state=='resident')then
                        w.gates[#w.gates+1]={name=name,gate=core_assets.gate(world.runtime,{id='beacon-api-'..#w.gates,
                            asset_dependencies={dependency}},log_module.emit)}
                    end
                end
            end
            if #w.gates==0 then emit({kind='ready',names=spec.prepare or{}})end
        end
        for k=#w.gates,1,-1 do
            local g=w.gates[k]
            local result,gwhy=g.gate.tick(dt or 0)
            if result=='ready'then
                table.remove(w.gates,k)
                if #w.gates==0 then emit({kind='ready',names=spec.prepare})end
            elseif result=='failed'then
                table.remove(w.gates,k)
                emit({kind='refused',code='ASSET_UNAVAILABLE',reason=g.name..': '..tostring(gwhy)})
            end
        end
        local list,m=redirect.beacons(world)
        if not list then return end
        w.frame=(w.frame or 0)+1
        local now=redirect.clock(world)
        local function seconds(from)return now and from and(now-from)/1e6 or nil end
        for entity,it in pairs(list)do
            local s=w.beacons[entity]
            if not s then
                s={first=w.frame,first_clock=now,type=it.type,timing=M.timing_of(it),
                    carrier=(w.carrier_type==nil or it.type==w.carrier_type)and not it.activated}
                w.beacons[entity]=s
                local beacon={entity=entity,index=it.index,type=it.type,carrier=name_of(world,it.type),
                    timing=s.timing,landed=it.mode~=nil,activated=it.activated==true}
                emit({kind='created',beacon=beacon,observed=not s.carrier,frame=w.frame,clock=now})
                if s.carrier and spec.decide then
                    local okd,change=pcall(spec.decide,beacon)
                    if not okd then
                        log('decide failed: '..tostring(change))
                    elseif change then
                        -- change.client: the orchestrator's client-write proof mark (runtime/multiplayer.lua).
                        local client=change.client==true
                        change.client=nil
                        local result,code,reason=M.apply(world,entity,{type=it.type,index=it.index,
                            timers=it.raw:sub(EL.countdown+1,EL.threshold+4),multiplayer=spec.multiplayer==true,
                            client=client},change)
                        if result then
                            s.applied=result
                            emit({kind='applied',entity=entity,result=result,frame=w.frame})
                        else
                            emit({kind='refused',entity=entity,code=code,reason=reason})
                        end
                    end
                end
            elseif it.activated and not s.activated then
                s.activated=true
                s.activated_clock=now
                emit({kind='activated',entity=entity,type=it.type,delivery=name_of(world,it.type),
                    seconds=seconds(s.first_clock),updates=w.frame-s.first,first=s.timing,applied=s.applied,
                    observed=not s.carrier,dispatch=redirect.dispatch_record(world,m,it.index),clock=now})
            end
        end
        for entity,s in pairs(w.beacons)do
            if not list[entity]then
                w.beacons[entity]=nil
                emit({kind='gone',entity=entity,activated=s.activated==true,after=seconds(s.activated_clock),
                    seconds=seconds(s.first_clock),observed=not s.carrier,applied=s.applied,clock=now})
            end
        end
    end
    function w.tick(dt)if w.status=='active'then tick(dt)end end
    function w.cancel()w.status='cancelled';if active==w then active=nil end end
    active=w
    scheduler.attach(w)
    return w
end
function M.reset_for_tests()if active then active.status='cancelled'end;active=nil end
return M
