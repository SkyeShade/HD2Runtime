-- What this machine sees of ANOTHER machine's custom stratagem call (EXPERIMENTAL; read-only; docs/research/runtime-
-- peer-messaging-F5FEE03DCFDB.md, section 10). Nothing here writes the game or calls a game function.
--
-- A beacon of a carrier type with no state here is another machine's call (its thrower's Runtime runs it). For the
-- client-write proof (Gas EAT) the questions are what the game replicates of it:
--   * REMOTE OBSERVED: pod: does the support pod the thrower's beacon dispatched exist here (the same read-only capture
--     as the caller's, runtime/support_pods.lua: the pod whose block names the beacon's network id), and its rack and
--     items, with their NETWORK ids (the same on every machine; entity ids are not), so both logs correlate;
--   * REMOTE OBSERVED: projectile: each projectile this machine holds from one of those items (runtime/projectile_impact
--     observe, read-only): its own impact explosion copy when first read, and the explosion it requested on impact.
-- The caller converts its own projectile's copy (376 -> 82, on the firing machine); this shows whether that reaches here.
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local support_pods=require('hd2runtime/runtime/support_pods')
local impacts=require('hd2runtime/runtime/projectile_impact')
local M={}
M.POD_SECONDS=60         -- a remote call is first seen at its beacon's creation (no activation is visible here)
M.RACK_SECONDS=90
M.FOLLOW_SECONDS=30
M.MAX_FOLLOWED=32
local function log(text)log_module.emit('[HD2Runtime] '..text)end

local items={}           -- [entity] = {network, label}: another machine's delivered items seen here
local flying={}          -- [slot] = {type, source, at}
local observer,watch
local clock=0
local diagnosed=false    -- the Transport component's pods logged once per mission at a remote NO_POD
function M.reset_for_tests()
    items,flying,clock,diagnosed={},{},0,false
    if observer then observer.cancel();observer=nil end
    if watch then watch.status='cancelled';watch=nil end
end
function M.reset_mission()items,flying,diagnosed={},{},false end

-- Live 2026-10-04: no pod named another machine's Gas EAT beacon here (NO_POD, every call). What this machine's Transport
-- component holds then (read-only; at most 8 pods, once per mission): whether a remote pod names its beacon or type at
-- all decides whether a later build can derive the delivery here instead of the caller publishing it.
local function transport_diagnostic(spec)
    if diagnosed then return end
    diagnosed=true
    local world=world_module.open()
    local pods,why
    if world then pods,why=support_pods.pods(world)end
    if not pods then
        log('REMOTE OBSERVED: this machine\'s Transport component is unreadable: '..tostring(why))
        return
    end
    local parts={}
    for k,p in ipairs(pods)do
        if k>8 then parts[#parts+1]=('... %d more'):format(#pods-8);break end
        parts[#parts+1]=('pod %d (network id %d): type %d, beacon network id %d, content %d'):format(p.entity,p.network,
            p.type,p.beacon_network,p.content_entity)
    end
    log(('REMOTE OBSERVED: this machine\'s Transport component holds %d pod%s when %s found none for beacon network id %s '
        ..'(type %s): %s'):format(#pods,#pods==1 and''or's',spec.call,tostring(spec.network),tostring(spec.type),
        #parts>0 and table.concat(parts,'; ')or'none'))
end

local function follow()
    if watch then return end
    watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        if watch.status~='active'then return end
        clock=clock+(dt or 0)
        if not next(flying)then return end
        local world=world_module.open()
        local counter,system
        if world then counter,system=world_module.projectile_counter(world)end
        if not system then return end
        for slot,f in pairs(flying)do
            local s=impacts.slot_state(world,system,slot)
            if not(s and s.type==f.type and s.source==f.source)then
                flying[slot]=nil
                log(('REMOTE OBSERVED: projectile slot %d (%s): gone without an impact request seen here (%.1f s)'):format(
                    slot,f.label,clock-f.at))
            elseif s.impact_requested then
                flying[slot]=nil
                log(('REMOTE OBSERVED: projectile slot %d (%s): impact requested here with explosion %d (this machine\'s '
                    ..'own copy), %.1f s after it was first read'):format(slot,f.label,s.impact,clock-f.at))
            elseif clock-f.at>M.FOLLOW_SECONDS then
                flying[slot]=nil
            end
        end
    end
    scheduler.attach(watch)
end

local function observe_projectiles()
    if observer then return end
    observer=impacts.observe(function(world,system,item)
        local who=item.source and items[item.source]
        if not who then return end
        local s=impacts.slot_state(world,system,item.slot)
        if not s then return end
        local n=0
        for _ in pairs(flying)do n=n+1 end
        if n<M.MAX_FOLLOWED then flying[item.slot]={type=s.type,source=s.source,at=clock,label=who.label}end
        log(('REMOTE OBSERVED: projectile %d in pool slot %d from %s: its impact explosion copy here %d, creditor %s%s, '
            ..'in flight %s'):format(s.type,item.slot,who.label,s.impact,s.creditor,s.local_creditor and' (this machine)'
            or'',tostring(s.in_flight)))
        follow()
    end)
end

-- Another machine's support delivery: its pod, rack and items, read only. spec = {beacon (the copy: runtime/
-- beacon_redirect beacon), network (its network id), call (text), type (the dispatched stratagem type), item_types}.
function M.remote_support(spec)
    local w,why=support_pods.capture({beacon_network=spec.network,type=spec.type,item_types=spec.item_types,
        label='remote '..spec.call,pod_seconds=M.POD_SECONDS,rack_seconds=M.RACK_SECONDS},function(e)
        if e.kind=='pod'then
            log(('REMOTE OBSERVED: pod %d (network id %s) of %s: it exists on this machine'):format(e.pod,
                tostring(e.network),spec.call))
        elseif e.kind=='captured'then
            local parts={}
            for k,entity in ipairs(e.items)do
                local network=e.networks and e.networks[k]
                local label=('item %d (network id %s) of %s'):format(entity,tostring(network),spec.call)
                items[entity]={network=network,label=label}
                parts[#parts+1]=('%d (network id %s)'):format(entity,tostring(network))
            end
            log(('REMOTE OBSERVED: pod %d (network id %s), rack %d (network id %s): items %s of %s, read %.1f s after the '
                ..'beacon was first seen here'):format(e.pod,tostring(e.pod_network),e.rack,tostring(e.rack_network),
                table.concat(parts,', '),spec.call,e.seconds or 0))
            observe_projectiles()
        elseif e.kind=='refused'then
            log(('REMOTE OBSERVED: no delivery of %s seen here: %s: %s'):format(spec.call,tostring(e.code),
                tostring(e.reason)))
            if e.code=='NO_POD'then pcall(transport_diagnostic,spec)end
        end
    end)
    if not w then log(('REMOTE OBSERVED: the delivery of %s cannot be followed: %s'):format(spec.call,tostring(why)))end
    return w
end
return M
