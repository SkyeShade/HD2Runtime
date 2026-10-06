-- Custom Eagles (development; docs/custom-stratagem-api.md, "eagle"; docs/research/custom-payloads-F5FEE03DCFDB.md). Not
-- exported by api/hd2.lua: hd2.custom_stratagem definitions with an `eagle` payload reach it.
--
-- research/custom-payloads-F5FEE03DCFDB.json:
--   * the jet: the Eagle dispatch (delivery kind 0) spawns the stratagem's payload[0], the jet, at the beacon's
--     activation, and appends its handle (+0 resource, +8 entity, +0x10 network id) to the Eagle manager
--     [game+0x3326650] (+0x48, count +0x1C). A redirected Eagle beacon (its type changed to the donor Eagle's in its
--     first update) therefore activates the DONOR's jet;
--   * its rockets (live 2026-10-04; research custom-payloads "eagleMount"): the 110mm's rockets are fired by the two
--     payload pods MOUNTED on the jet (its MountComponentData: 0x0E8C2515261E0325 at "payload_right", slot 0, and
--     0x486522867199D7F3 at "payload_left", slot 1), so each rocket's pool SOURCE is a pod and its OWNER is the jet; each
--     carries its own copy of the strike projectile row's impact explosion.
-- The jet of a call (M.capture): a tracker (armed while a custom Eagle is ready) notes the game clock at which each
-- jet (entity, network id) is first seen; a call's jet is the ONE jet of the donor's resource first seen from the
-- call's activation clock, within M.CAPTURE_SECONDS, while no OTHER beacon of the donor's type activated in that window
-- (M.note_activation: every beacon activation the beacon watch reports). Anything else is refused (AMBIGUOUS, NO_JET):
-- the rockets then stay vanilla.
-- The rockets of a call (M.bind_rockets), through the game's own ownership hierarchy, never by timing:
--   * the call's pods: the children the captured jet's OWN mount record names (the mount component, six per mount),
--     each in the slot the jet's type mounts that resource in, and of exactly that entity type;
--   * a rocket of the call: a projectile of the strike type whose source is one of those pods AND whose owner is the
--     captured jet (both checked per projectile, from its own records). A pod the mount record does not name is never
--     taken; only when the jet's mount record cannot be read at all is a source accepted by its pod type and the
--     projectile's owner (logged as such).
--   * A vanilla 110mm's rockets name its own jet as their owner and its own pods as their source: never this call's.
-- The binding follows the jet ENTITY (its id carries an 8-bit generation: a reused id never matches) for at most
-- M.BIND_SECONDS after the activation, or until the jet is gone and no converted rocket flies. Each converted rocket
-- requests the donor's explosion from its own impact copy (runtime/projectile_impact.lua: one guarded write, read back);
-- its type, the row, the pods, the jet and every other projectile stay vanilla.
-- The log keeps a call's state transitions: JET CAPTURED (or REFUSED), ROCKETS BOUND, each PAYLOAD POD, each rocket's
-- guarded write (projectile impact CONVERTED / REFUSED) and one ROCKETS RESULT. With M.verbose (hd2.custom_stratagem
-- .verbose(true)) a per-call TRACE (M.TRACE_LINES lines at most) also reports every candidate rocket (ROCKET CAPTURED /
-- IMPACT CONVERTED, or why not), the impacts, the jet's presence in the Eagle manager and the explosion requests read
-- from the game's queue; without it none of those reads happen. Either way only while a custom Eagle call is bound.
-- Uses (M.uses_watch): the custom Eagle's slot is a fleet member with its own uses (the slot conversion and the carrier
-- presentation's uses per rearm). With Eagle Rearm in the record (a real Eagle in the loadout) the game's own rearm
-- handles it, exactly as for a second native Eagle. Without it nothing native can rearm the slot, so the Runtime does:
-- once its uses reach 0, after the rearm time (Eagle Rearm's own cooldown, read live), one guarded 4-byte write of that
-- entry's uses (0 -> its uses), the entry block as context. Never another entry; never while Eagle Rearm is present.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local scheduler=require('hd2runtime/runtime/scheduler')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local impacts=require('hd2runtime/runtime/projectile_impact')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local D=require('hd2runtime/domains/custom_payloads')
local SD=require('hd2runtime/domains/stratagem_slots')
local M={}
local E=D.eagle
M.CAPTURE_SECONDS=3       -- a call's jet is first seen within this long of its activation
M.SETTLE_SECONDS=0.2      -- and the capture decides only this long after the activation (a second jet would show)
M.BIND_SECONDS=30         -- a rocket binding ends this long after the call's activation at most
M.GONE_SECONDS=1          -- ... or once the call's jet no longer exists for this long (no converted rocket flying)
M.TRACE_LINES=48          -- trace lines per call (then counted)
M.verbose=false           -- the per-call trace and its read-only probes (see the header)
M.MAX_ROCKETS=64
M.MAX_JETS=64
M.REARM_TYPE=D.eagleRearm.type
M.EAGLES=D.eagles
local US=1e6

local function log(text)log_module.emit('[HD2Runtime] custom eagle '..text)end
local function clock_of(world)return require('hd2runtime/runtime/beacon_redirect').clock(world)end

local proven={}
function M.prove(world)
    if D.source.gameDllSha256~=profile.dll_sha then return nil,'the custom payload research covers another game.dll build'end
    if proven[world.game]then return true end
    for _,pin in ipairs(D.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,('the Eagle code changed (%s at game+%X)'):format(pin.label,pin.rva)
        end
    end
    proven[world.game]=true
    return true
end

-- Every jet now: {[entity] = {entity, network, resource (hex, as event_world.entity_type), index}}, or nil and why.
function M.jets(world)
    local m=world.view.pointer(world.game+E.global)
    if not m or m==0 then return nil,'the Eagle manager is unreadable'end
    local count=world.view.u32(m+E.count)
    local handles=world.view.pointer(m+E.handles)
    if not count or count>M.MAX_JETS then return nil,'the Eagle manager is implausible'end
    local out={}
    if count==0 then return out end
    if not handles or handles==0 then return nil,'the Eagle handles are unreadable'end
    local active=world.view.u32(m+E.active)or 0
    for i=0,count-1 do
        local h=world.view.pointer(handles+i*8)
        local raw=h and h~=0 and world.view.read(h,E.handleNetwork+4)
        if not raw then return nil,'a jet handle is unreadable'end
        local entity=b.u32(raw,E.handleEntity)
        out[entity]={entity=entity,network=b.u32(raw,E.handleNetwork),index=i,active=i<active,
            resource=string.format('%08X%08X',b.u32(raw,E.handleResource+4),b.u32(raw,E.handleResource))}
    end
    return out
end

-------------------------------------------------------------------------------------------------- the tracker --
local tracker={armed=0,seen={},activations={},watch=nil}
local function key(j)return j.entity..':'..j.network end
local function track_tick()
    if tracker.armed<=0 then return end
    local world=world_module.open()
    if not world then return end
    local game=world_module.game_state(world)
    if not(game and game.mission)then tracker.seen,tracker.activations={},{};return end
    local now=clock_of(world)
    local jets=now and M.jets(world)
    if not jets then return end
    local present={}
    for _,j in pairs(jets)do
        local k=key(j)
        present[k]=true
        if not tracker.seen[k]then tracker.seen[k]={entity=j.entity,network=j.network,resource=j.resource,first=now}end
    end
    for k in pairs(tracker.seen)do if not present[k]then tracker.seen[k]=nil end end
    for i=#tracker.activations,1,-1 do
        if now-tracker.activations[i].clock>(M.CAPTURE_SECONDS+M.SETTLE_SECONDS)*2*US then table.remove(tracker.activations,i)end
    end
end
M.track_tick=track_tick
-- Arms the tracker (a custom Eagle is ready in this mission); disarm() when it no longer is. It must run before any
-- call: the jets present then are first seen before every activation.
function M.arm()
    tracker.armed=tracker.armed+1
    if not(tracker.watch and tracker.watch.status=='active')then
        tracker.watch={status='active'}
        function tracker.watch.tick()
            if tracker.watch.status~='active'then return end
            -- Disarmed (no custom Eagle ready): the watch stops; arm() starts it again.
            if tracker.armed<=0 then tracker.watch.status='complete';tracker.seen,tracker.activations={},{};return end
            track_tick()
        end
        function tracker.watch.cancel()tracker.watch.status='cancelled'end
        scheduler.attach(tracker.watch)
    end
    track_tick()
end
function M.disarm()tracker.armed=math.max(0,tracker.armed-1)end
-- Every beacon activation the beacon watch reports (custom or not): {type, entity, clock}.
function M.note_activation(kind,entity,clock)
    if tracker.armed<=0 or not clock then return end
    tracker.activations[#tracker.activations+1]={type=kind,entity=entity,clock=clock}
end
-- The jets first seen in [from, to] (game clock) of a resource.
local function first_seen(resource,from,to)
    local out={}
    for _,s in pairs(tracker.seen)do
        if s.resource==resource and s.first>=from and s.first<=to then out[#out+1]=s end
    end
    table.sort(out,function(a,c)return a.entity<c.entity end)
    return out
end

-- Follows one custom Eagle call to its jet. spec = {activation (the beacon's activation clock), beacon (its entity),
-- donor_type (the type the beacon activated as), resource (the donor's jet, hex), label}. callback(event): 'captured'
-- (jet, network, seconds), 'refused' (code, reason), 'ended'. Returns the watch, or nil and why.
function M.capture(spec,callback)
    if type(spec)~='table'or type(spec.activation)~='number'or type(spec.resource)~='string'
            or type(spec.donor_type)~='number'then
        return nil,'spec must be {activation, beacon, donor_type, resource}'
    end
    if tracker.armed<=0 then return nil,'the jet tracker is not armed'end
    local w={status='active'}
    local function emit(event)
        if callback then
            local ok,why=pcall(callback,event)
            if not ok then log('callback failed: '..tostring(why))end
        end
    end
    local function finish(kind,code,reason)
        if w.status~='active'then return end
        w.status='complete'
        if kind=='refused'then
            log(('JET REFUSED (%s): %s: %s (its rockets stay vanilla)'):format(tostring(spec.label),code,reason))
            emit({kind='refused',code=code,reason=reason})
        end
        emit({kind='ended'})
    end
    function w.tick()
        if w.status~='active'then return end
        local world=world_module.open()
        if not world then return end
        local game=world_module.game_state(world)
        if not(game and game.mission)then return finish('refused','NOT_IN_MISSION','the mission ended')end
        local ok,why=M.prove(world)
        if not ok then return finish('refused','UNSUPPORTED_BUILD',tostring(why))end
        track_tick()
        local now=clock_of(world)
        if not now then return end
        local window_end=spec.activation+M.CAPTURE_SECONDS*US
        for _,a in ipairs(tracker.activations)do
            if a.entity~=spec.beacon and a.type==spec.donor_type and a.clock>=spec.activation and a.clock<=window_end then
                return finish('refused','AMBIGUOUS',('another %d beacon (%s) activated within %.1f s of this call'):format(
                    spec.donor_type,tostring(a.entity),M.CAPTURE_SECONDS))
            end
        end
        local jets=first_seen(spec.resource,spec.activation,window_end)
        if#jets>1 then
            return finish('refused','AMBIGUOUS',#jets..' jets of '..spec.resource..' appeared after this call')
        end
        if now<spec.activation+M.SETTLE_SECONDS*US then return end
        if#jets==1 then
            local j=jets[1]
            w.status='complete'
            log(('JET CAPTURED (%s): jet %d (network id %d, %s) first seen %.2f s after the activation; no other %d beacon '
                ..'activated'):format(tostring(spec.label),j.entity,j.network,j.resource,(j.first-spec.activation)/US,
                spec.donor_type))
            emit({kind='captured',jet=j.entity,network=j.network,resource=j.resource,seconds=(j.first-spec.activation)/US})
            emit({kind='ended'})
            return
        end
        if now>window_end then
            return finish('refused','NO_JET',('no jet of %s within %.1f s of the activation'):format(spec.resource,
                M.CAPTURE_SECONDS))
        end
    end
    function w.cancel()if w.status=='active'then w.status='cancelled'end end
    scheduler.attach(w)
    return w
end

-- The game's explosion request queue (research custom-payloads "explosionQueue"), read-only: the requests it holds now,
-- {type, source, owner, creditor, x, y, z} (at most `limit`), or nil. The game drains it: an empty read proves nothing.
local Q=D.explosionQueue
function M.explosion_requests(world,limit)
    local queue=world.view.pointer(world.game+Q.global)
    local count=queue and queue~=0 and world.view.u32(queue+Q.count)
    if not count or count>Q.capacity then return nil end
    local out={}
    local n=math.min(count,limit or 64)
    local raw=n>0 and world.view.read(queue+Q.entries,n*Q.stride)
    for i=0,n-1 do
        if not raw then break end
        local o=i*Q.stride
        local function f(at)local ok,v=pcall(b.value,raw,o+at,'f32');return ok and v or 0 end
        out[#out+1]={type=b.u32(raw,o+Q.type),source=b.u32(raw,o+Q.source),owner=b.u32(raw,o+Q.owner),
            creditor=string.format('%08X%08X',b.u32(raw,o+Q.creditor+4),b.u32(raw,o+Q.creditor)),
            x=f(Q.position),y=f(Q.position+4),z=f(Q.position+8)}
    end
    return out,count
end

-- The children an entity's mount record names now (research custom-payloads "eagleMount": the mount component
-- [game+0x3326438], six per mount at +0x48): {[slot] = entity (0 = none)}, or nil when it has no mount record here.
local MT=D.mount
local function map_at(at)return {keys=at,capacity=at+8,empty=at+0xC,multiplier=at+0x10}end
function M.mounted(world,entity)
    local component=world.view.pointer(world.game+MT.global)
    if not component or component==0 then return nil end
    local index=require('hd2runtime/runtime/pelicans').index_of(world,component,map_at(MT.map),entity)
    local base=index and world.view.pointer(component+MT.children)
    local raw=base and base~=0 and world.view.read(base+index*MT.stride,MT.stride)
    if not raw then return nil end
    local out={}
    for k=0,MT.slots-1 do out[k]=b.u32(raw,k*4)end
    return out
end
-- The donor Eagle whose jet is `resource` (hex): its reviewed entry (with its mounts), or nil.
local function eagle_of(resource)
    for name,e in pairs(M.EAGLES)do
        if e.jet:gsub('^0x',''):upper()==resource then return e,name end
    end
end

-- Binds the rockets of one custom Eagle call (see the header). spec = {jet, network, resource (the donor's jet, hex),
-- projectile (its strike projectile), donor (a reviewed explosion donor), activation (the call's activation clock),
-- donor_type, beacon, rounds (per pod, default M.MAX_ROCKETS), label}. callback(event): projectile_impact's 'converted'
-- / 'refused' / 'impact' / 'lost', 'pod' (pod, slot, node, resource, how), 'ended' (reason, converted, refused, impacts,
-- impacts_to, observed, mine, others, pods, requests = {to, from, reads, nonempty}, proven). Returns the binding, or
-- nil, code, reason.
function M.bind_rockets(spec,callback)
    if type(spec)~='table'or type(spec.jet)~='number'or type(spec.network)~='number'or type(spec.activation)~='number'
            or type(spec.donor_type)~='number'then
        return nil,'INVALID','spec must name the jet, its network id, the activation and the donor type'
    end
    local label=tostring(spec.label)
    local donor_eagle=eagle_of(spec.resource)
    local mounts={}
    for _,m in ipairs(donor_eagle and donor_eagle.mounts or{})do if m.weapon then mounts[m.slot]=m end end
    if not next(mounts)then
        return nil,'NO_PODS',spec.resource..' mounts no reviewed weapon (its rockets cannot be told from another jet\'s)'
    end
    local verbose=M.verbose==true       -- fixed for the call
    local trace={lines=0,dropped=0}
    local stats={observed=0,mine=0,others=0,converted=0,refused=0,impacts=0,impacts_to=0,
        requests={to=0,from=0,reads=0,nonempty=0}}
    local pods={}            -- pod entity -> {slot, node, resource, how}
    local refused_pods={}    -- pod entity -> true: refused once, never tried again
    local function emit(event)
        if callback then
            local ok,why=pcall(callback,event)
            if not ok then log('callback failed: '..tostring(why))end
        end
    end
    local function at(world)
        local now=world and clock_of(world)
        return now and(now-spec.activation)/US or 0
    end
    local function line(world,text)
        if not verbose then return end
        if trace.lines>=M.TRACE_LINES then trace.dropped=trace.dropped+1;return end
        trace.lines=trace.lines+1
        log(('TRACE (%s) +%.2f s: %s'):format(label,at(world),text))
    end
    local binding,code,reason
    -- A pod of this call's jet: an exact entity of the slot's resource, owned (its projectiles' owner) by the jet.
    local function add_pod(world,pod,slot,how)
        local m=mounts[slot]
        if not m or pods[pod]or refused_pods[pod]then return pods[pod]~=nil end
        if world_module.entity_type(world,pod)~=m.resource then return false end
        local ok,acode,areason=binding.add_source(pod,{entity_type=m.resource,owner=spec.jet,how=how})
        if not ok then
            refused_pods[pod]=true
            log(('POD REFUSED (%s): pod %d (%s) not bound: %s: %s (its rockets stay vanilla)'):format(label,pod,m.node,
                tostring(acode),tostring(areason)))
            return false
        end
        pods[pod]={slot=slot,node=m.node,resource=m.resource,how=how}
        log(('PAYLOAD POD (%s): entity %d (%s, %s) of jet %d, %s'):format(label,pod,m.resource,m.node,spec.jet,how))
        emit({kind='pod',pod=pod,slot=slot,node=m.node,resource=m.resource,how=how})
        return true
    end
    local function pods_from_mount(world)
        local children=M.mounted(world,spec.jet)
        if not children then return nil end
        for slot,child in pairs(children)do
            if child~=0 and mounts[slot]and not pods[child]and world_module.entity_exists(world,child)==true then
                add_pod(world,child,slot,('its mount record\'s slot %d'):format(slot))
            end
        end
        return children
    end
    -- An unbound source of a strike-type projectile: this call's pod only through the hierarchy (see the header).
    local function accept(world,system,slot,source,owner)
        if owner~=spec.jet then return false end
        local children=pods_from_mount(world)
        if pods[source]then return true end
        if children then return false end          -- the mount record is readable and does not name it
        local kind=world_module.entity_type(world,source)
        for k,m in pairs(mounts)do
            if kind==m.resource then
                return add_pod(world,source,k,'by its pod type and the projectile\'s owner (the jet\'s mount record is '
                    ..'unreadable)')
            end
        end
        return false
    end
    binding,code,reason=impacts.bind({sources={spec.jet},projectile=spec.projectile,donor=spec.donor,
        rounds=spec.rounds or M.MAX_ROCKETS,entity_type=spec.resource,label=label,accept=accept,
        multiplayer=spec.multiplayer==true},function(e)
            local world=world_module.open()
            if e.kind=='converted'then
                stats.converted=stats.converted+1
            elseif e.kind=='refused'then
                stats.refused=stats.refused+1
            elseif e.kind=='impact'then
                stats.impacts=stats.impacts+1
                if e.explosion==binding.to then stats.impacts_to=stats.impacts_to+1 end
                line(world,('IMPACT REQUESTED: rocket in pool slot %d (pod %d) requested explosion %d from its own copy '
                    ..'(%s), %.2f s after its conversion'):format(e.slot,e.source,e.explosion,e.explosion==binding.to
                    and'the donor\'s'or'NOT the donor\'s',e.seconds or 0))
            elseif e.kind=='lost'then
                line(world,('rocket in pool slot %d (pod %d) not followed to its impact: %s'):format(e.slot,e.source,
                    tostring(e.reason)))
            end
            if e.kind~='ended'then emit(e)end
        end)
    if not binding then return nil,code,reason end
    local world0=world_module.open()
    log(('ROCKETS BOUND (%s): jet %d (network id %d, %s): its pods\' projectiles %d (owner this jet) request explosion %d '
        ..'instead of %d%s'):format(label,spec.jet,spec.network,spec.resource,spec.projectile,binding.to,binding.from,
        verbose and'; verbose trace on'or''))
    if world0 then pods_from_mount(world0)end
    -- Verbose only: every new projectile slot, read-only: the strike type's, and anything this call's jet or pods fire.
    local observer={cancel=function()end}
    if verbose then observer=impacts.observe(function(world,system,item,outcome)
        local st=impacts.slot_state(world,system,item.slot)
        local owner=st and st.owner
        local mine=pods[item.source]~=nil or item.source==spec.jet
        if not(mine or item.type==spec.projectile or owner==spec.jet)then return end
        stats.observed=stats.observed+1
        if mine and owner==spec.jet then stats.mine=stats.mine+1 else stats.others=stats.others+1 end
        local pod=pods[item.source]
        local from=pod and('source child %d (%s pod)'):format(item.source,pod.node)or('source %s (%s)'):format(
            tostring(item.source),tostring(world_module.entity_type(world,item.source)))
        local who=owner==spec.jet and('owner custom jet %d'):format(spec.jet)or('owner %s'):format(tostring(owner))
        if outcome and outcome.kind=='converted'then
            line(world,('ROCKET CAPTURED: projectile %d (pool slot %d), %s, %s'):format(item.type,item.slot,from,who))
            line(world,('IMPACT CONVERTED %d -> %d (read back %s; creditor %s)'):format(outcome.from,outcome.to,
                tostring(outcome.verify and outcome.verify.readBack),tostring(outcome.creditor)))
        elseif outcome and outcome.kind=='refused'then
            line(world,('ROCKET CAPTURED but NOT converted: projectile %d (pool slot %d), %s, %s: %s: %s (it stays '
                ..'vanilla)'):format(item.type,item.slot,from,who,tostring(outcome.code),tostring(outcome.reason)))
        elseif outcome and outcome.kind=='untouched'then
            line(world,('projectile %d (pool slot %d), %s: no rounds left (vanilla)'):format(item.type,item.slot,from))
        else
            line(world,('NOT THIS CALL\'S: projectile %d (pool slot %d), %s, %s, impact copy %s (left vanilla)'):format(
                item.type,item.slot,from,who,st and tostring(st.impact)or'?'))
        end
    end)end
    local requests_seen={}
    local gone_since
    local guard={status='active'}
    local function finish(world,reason)
        if guard.status~='active'then return end
        guard.status='complete'
        observer.cancel()
        if binding.status=='active'then binding.cancel()end
        local n=0;for _ in pairs(pods)do n=n+1 end
        local proven=stats.converted>0
        local tail=proven and''or'. NOT PROVEN: no rocket of this call was converted; the run was vanilla'
        if verbose then
            log(('ROCKETS RESULT (%s): %s; jet %d, %d pod%s; %d rocket%s of this call (%d converted %d -> %d, %d refused), '
                ..'%d impact%s requested (%d with explosion %d); %d other projectile%s seen (left vanilla); explosion queue '
                ..'read %d times, non-empty %d times: %d request%s of explosion %d and %d of %d from this call\'s pods seen; '
                ..'the field\'s presentation itself is not traceable in this build (watch for it)%s%s'):format(label,reason,
                spec.jet,n,n==1 and''or's',stats.mine,stats.mine==1 and''or's',stats.converted,binding.from,binding.to,
                stats.refused,stats.impacts,stats.impacts==1 and''or's',stats.impacts_to,binding.to,stats.others,
                stats.others==1 and''or's',stats.requests.reads,stats.requests.nonempty,stats.requests.to,
                stats.requests.to==1 and''or's',binding.to,stats.requests.from,binding.from,
                trace.dropped>0 and(('; %d trace lines not shown'):format(trace.dropped))or'',tail))
        else
            log(('ROCKETS RESULT (%s): %s; jet %d, %d pod%s; %d rocket%s converted %d -> %d, %d refused; %d impact%s '
                ..'requested (%d with explosion %d)%s'):format(label,reason,spec.jet,n,n==1 and''or's',stats.converted,
                stats.converted==1 and''or's',binding.from,binding.to,stats.refused,stats.impacts,
                stats.impacts==1 and''or's',stats.impacts_to,binding.to,tail))
        end
        emit({kind='ended',reason=reason,converted=stats.converted,refused=stats.refused,impacts=stats.impacts,
            impacts_to=stats.impacts_to,observed=stats.observed,mine=stats.mine,others=stats.others,pods=n,
            requests=stats.requests,proven=proven})
    end
    local present=true
    local guard_step
    function guard.tick()
        local started=metrics.now()
        guard_step()
        metrics.elapsed('custom_eagles.rockets_tick',started)
    end
    function guard_step()
        if guard.status~='active'then return end
        local world=world_module.open()
        if not world then return end
        if binding.status~='active'then return finish(world,'the binding ended (the mission ended)')end
        local now=clock_of(world)
        if not now then return end
        -- The mount record is read until every mounted slot has its pod (then nothing more can be added).
        local bound,slots=0,0
        for _ in pairs(pods)do bound=bound+1 end
        for _ in pairs(mounts)do slots=slots+1 end
        if bound<slots then pods_from_mount(world)end
        -- Verbose only: the jet in the Eagle manager (trace only: the binding follows the entity).
        local list=verbose and M.jets(world)
        if list then
            local j=list[spec.jet]
            if(j~=nil)~=present then
                present=j~=nil
                line(world,('jet %d %s the Eagle manager; the entity %s'):format(spec.jet,present and'back in'or'LEFT',
                    world_module.entity_exists(world,spec.jet)==true and'still exists'or'no longer exists'))
            end
        end
        -- Verbose only: the explosion requests the game's queue holds now (best effort: the game drains it).
        local reqs,count
        if verbose then reqs,count=M.explosion_requests(world,64)end
        if reqs then
            stats.requests.reads=stats.requests.reads+1
            if count>0 then stats.requests.nonempty=stats.requests.nonempty+1 end
            for _,r in ipairs(reqs)do
                if(r.type==binding.to or r.type==binding.from)and(pods[r.source]or r.source==spec.jet)then
                    local key=('%d:%d:%.1f:%.1f:%.1f'):format(r.type,r.source,r.x,r.y,r.z)
                    if not requests_seen[key]then
                        requests_seen[key]=true
                        if r.type==binding.to then stats.requests.to=stats.requests.to+1
                        else stats.requests.from=stats.requests.from+1 end
                        line(world,('EXPLOSION REQUEST observed in the game\'s queue: explosion %d at (%.1f, %.1f, %.1f), '
                            ..'source %d (this call\'s), owner %d, creditor %s'):format(r.type,r.x,r.y,r.z,r.source,
                            r.owner,r.creditor))
                    end
                end
            end
        end
        -- The end: the time limit, or the jet gone with no converted rocket in flight.
        if now-spec.activation>M.BIND_SECONDS*US then return finish(world,('bound %d s'):format(M.BIND_SECONDS))end
        if world_module.entity_exists(world,spec.jet)==true or next(binding.flying)then gone_since=nil
        else
            gone_since=gone_since or now
            if now-gone_since>=M.GONE_SECONDS*US then return finish(world,'the jet of this call is gone')end
        end
    end
    function guard.cancel()
        if guard.status=='active'then
            guard.status='cancelled'
            observer.cancel()
            if binding.status=='active'then binding.cancel()end
        end
    end
    scheduler.attach(guard)
    binding.guard=guard
    binding.pods=pods
    binding.stats=stats
    return binding
end

-------------------------------------------------------------------------------------------- uses and rearm --
-- Whether the local record holds Eagle Rearm (a real Eagle in the loadout): true / false, or nil when unreadable.
function M.record_rearm(world)
    local record=slots.local_record(world)
    if not record then return nil end
    for _,entry in ipairs(record.entries)do if entry.type==M.REARM_TYPE then return true end end
    return false
end
local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base and address+size<=r.base+r.size)
    then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end
-- One guarded write of one entry's uses (0 -> uses), the record's whole entry block as context. Returns the report
-- and the read-back, or nil, code, reason.
local function rearm_entry(world,record,index,uses)
    local R,EN=SD.record,SD.record.entry
    local entry=record.entries[index+1]
    local first=record.state+R.entries
    local span=R.entryCount+4-R.entries
    local owner=owner_of(world,record.address,R.state+R.entryCount+4)
    local context=owner and world.view.read(first,span)
    if not context then return nil,'NOT_PRIVATE','the record is not in private read-write memory'end
    local plan={snapshots={{owner=owner,offset=first-owner.base,bytes=context}},
        changes={{label='stratagem.record.slot'..index..'.uses',owner=owner,offset=entry.address+EN.uses-owner.base,
            expected=b.encode(0,'u32'),desired=b.encode(uses,'u32'),before=b.encode(0,'u32'),already_desired=false,
            identity={component='StratagemRecord',component_type='native',unique_owner=true,owner_count=1},chain={}}}}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('custom_eagles.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local after=slots.local_record(world)
    return report,after and after.entries[index+1]and after.entries[index+1].uses
end
-- Watches the custom Eagle's converted entries. spec = {definition, carrier_type, uses, seconds (default: Eagle
-- Rearm's own cooldown, read live), label}; the entries are the slot conversion's for the definition. callback(event):
-- 'native' (Eagle Rearm is in the record: the game rearms), 'depleted' (index), 'rearmed' (index, uses, writes,
-- verified), 'refused' (index, code, reason). Returns the watch.
function M.uses_watch(spec,callback)
    local w={status='active',timers={},native=nil}
    local function emit(event)
        if callback then
            local ok,why=pcall(callback,event)
            if not ok then log('callback failed: '..tostring(why))end
        end
    end
    function w.tick()
        if w.status~='active'then return end
        local world=world_module.open()
        if not world then return end
        local game=world_module.game_state(world)
        if not(game and game.mission)then w.status='complete';return end
        local state=slots.state(spec.definition)
        if not(state and state.converted)then return end
        local record=slots.local_record(world)
        if not record then return end
        local rearm=false
        for _,entry in ipairs(record.entries)do if entry.type==M.REARM_TYPE then rearm=true end end
        if rearm then
            if w.native~=true then
                w.native=true
                log(('USES (%s): Eagle Rearm is in the record (a real Eagle): the game\'s own rearm resets this slot to '
                    ..'its %d uses per rearm'):format(tostring(spec.label),spec.uses))
                emit({kind='native'})
            end
            return
        end
        w.native=false
        local now=clock_of(world)
        if not now then return end
        local seconds=spec.seconds
        if not seconds then
            seconds=require('hd2runtime/runtime/slot_cooldown').row_cooldown(world,M.REARM_TYPE)
            if not(seconds and seconds>0 and seconds<=1200)then seconds=D.eagleRearm.cooldown end
        end
        for _,index in ipairs(state.indices)do
            local entry=record.entries[index+1]
            if entry and entry.type==spec.carrier_type then
                if entry.uses==0 then
                    if not w.timers[index]then
                        w.timers[index]=now
                        log(('DEPLETED (%s): loadout entry %d has no use left: the Runtime rearms it in %.0f s (no Eagle '
                            ..'Rearm in the record)'):format(tostring(spec.label),index,seconds))
                        emit({kind='depleted',index=index,seconds=seconds})
                    elseif now-w.timers[index]>=seconds*US then
                        w.timers[index]=nil
                        local ok,why=M.prove(world)
                        local report,code,reason
                        if not ok then code,reason='UNSUPPORTED_BUILD',tostring(why)
                        elseif not scheduler.in_update()then code,reason='NOT_GAME_THREAD','only inside the Runtime\'s update'
                        else report,code,reason=rearm_entry(world,record,index,spec.uses)end
                        if report then
                            log(('REARMED (%s): loadout entry %d uses 0 -> %d (%d write; read back %s; non-target bytes '
                                ..'unchanged %s; protection restored %s)'):format(tostring(spec.label),index,spec.uses,
                                report.writes,tostring(code),tostring(report.non_target_bytes_unchanged),
                                tostring(report.protection_restored)))
                            emit({kind='rearmed',index=index,uses=spec.uses,writes=report.writes,verified=code==spec.uses})
                        else
                            log(('REARM REFUSED (%s): loadout entry %d: %s: %s'):format(tostring(spec.label),index,
                                tostring(code),tostring(reason)))
                            emit({kind='refused',index=index,code=code,reason=reason})
                        end
                    end
                else
                    w.timers[index]=nil
                end
            end
        end
    end
    function w.cancel()w.status='cancelled'end
    scheduler.attach(w)
    return w
end

function M.reset_for_tests()
    proven={}
    if tracker.watch then tracker.watch.cancel()end
    tracker={armed=0,seen={},activations={},watch=nil}
end
return M
