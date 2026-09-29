-- Persistent scheduler over the same one-shot guarded operations.
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local plans=require('hd2runtime/domains/composition_plans')
local steady=require('hd2runtime/core/steady_state')
local metrics=require('hd2runtime/runtime/metrics')
local options=require('hd2runtime/api/options')
local M={}
local DEBOUNCE=0.5 -- update seconds that coalesce a burst of option changes into one resolution

-- Copy a request with every option handle replaced by its current value (or an override).
-- Handles may bind only a field `value`; target objects (tables with a metatable) are kept.
local function materialize(value,key,found,override,baseline)
    if options.is_handle(value)then
        assert(key=='value','an option may only bind a field value, not '..tostring(key))
        if found then found[#found+1]=value end
        if override and override.handle==value then return override.value end
        return value:get()
    end
    if type(value)~='table'or getmetatable(value)~=nil then return value end
    local copy={}
    for k,v in pairs(value)do copy[k]=materialize(v,k,found,override,baseline)end
    -- Restore request: every change goes back to its reviewed baseline.
    if baseline and value.expect~=nil and value.value~=nil then copy.value=copy.expect end
    return copy
end
local function each_change(kind,spec,fn)
    if kind=='plan'then
        for _,operation in ipairs(spec.operations)do
            for index,change in ipairs(operation.spec.changes or{})do fn(operation.id..'#'..index,change)end
        end
    else
        for index,change in ipairs(spec.changes or{})do fn('#'..index,change)end
    end
end
-- What a change will write. Scalars carry their encoded bytes; typed reference changes (projectile / explosion
-- references, attack outputs) are encoded only when their source is re-proven live, so their identity is the
-- selected source.
local function desired_key(change)
    if change.desired~=nil then return tostring(change.desired)end
    local selector=change.desired_selector
    if selector then
        return 'ref:'..tostring(selector.output or'')..'|'..tostring(selector.weapon or'')..'|'
            ..tostring(selector.attack or'')..'|'..tostring(selector.phase or'')..'|'..tostring(selector.is_null or'')
    end
    return 'value:'..tostring(change.value)
end
local function signature(kind,spec,enabled)
    local parts={enabled and'on'or'off'}
    each_change(kind,spec,function(key,change)parts[#parts+1]=key..'='..desired_key(change)end)
    return table.concat(parts,'\n')
end

-- One logical operation whose field values and enabled state follow option handles.
local function start_bound(runtime,emit,request,kind,validate,module,interval,startup,max_interval)
    local body=request[kind]
    local enabled_handle=request.enabled
    assert(enabled_handle==nil or(options.is_handle(enabled_handle)and enabled_handle.kind=='toggle'),
        'ensure enabled must be a toggle option')
    local bound={}
    local function build(override,baseline)return validate(materialize(body,nil,nil,override,baseline))end
    local current=materialize(body,nil,bound)
    for _,handle in ipairs(bound)do
        assert(handle.kind~='toggle','a toggle option can only control ensure enabled')
    end
    local spec=validate(current)
    local id=spec.id
    -- Bind-time proof: the whole option domain passes the normal guarded validation
    -- (acknowledgements, reviewed ranges, integer storage, known values), and so does restore.
    for _,handle in ipairs(bound)do
        for _,sample in ipairs(handle:samples())do
            local ok,why=pcall(build,{handle=handle,value=sample})
            if not ok then error('option '..handle.id..' value '..tostring(sample)
                ..' is not accepted by '..id..': '..tostring(why),0)end
        end
    end
    local restore=build(nil,true)
    local function log(message)pcall(emit,'[HD2Runtime] '..message)end
    local watch={status='waiting',runs=0,kind=kind,id=id,interval=interval,max_interval=max_interval,
        current_interval=interval,verifications=0,drifts=0,bound=true,enabled=true,restores=0,rebinds=0}
    local elapsed,next_at=0,0
    local child,mode,target,verification
    local owned,applied_signature={},nil
    local dirty,debounce=false,0

    local function launch(next_mode,next_spec,next_signature)
        -- Bytes this operation verified live last time are its own, not a conflict.
        each_change(kind,next_spec,function(key,change)
            local mine=owned[key]
            if mine and mine~=change.desired and mine~=change.expected then change.owned=mine end
        end)
        if child then child.cancel()end
        child=module.start_spec(runtime,emit,next_spec,math.max(0,startup-elapsed))
        mode,target,verification=next_mode,{spec=next_spec,signature=next_signature},nil
        watch.status='running'
        metrics.count(next_mode=='restore'and'options.restores'or'options.bound_resolutions')
    end
    local function settle()
        dirty=false
        local ok,next_spec=pcall(build)
        if not ok then
            if child then child.cancel();child=nil end
            watch.status='blocked';watch.error=tostring(next_spec)
            log('ensure '..id..' blocked: '..watch.error);return
        end
        local enabled=enabled_handle==nil or enabled_handle:get()==true
        watch.enabled=enabled
        local next_signature=signature(kind,next_spec,enabled)
        if target and target.signature==next_signature and child then return end
        if not child and applied_signature==next_signature and watch.status~='blocked'then
            metrics.count('options.noop_settles');return
        end
        watch.rebinds=watch.rebinds+1
        if enabled then
            launch('apply',next_spec,next_signature)
        elseif next(owned)then
            -- Restore through the same guards: only bytes this operation owns go back.
            launch('restore',build(nil,true),next_signature)
        else
            if child then child.cancel();child=nil end
            applied_signature,verification,target=next_signature,nil,nil
            watch.status='disabled';log('ensure '..id..' disabled; nothing applied to restore')
        end
    end
    local function listener()
        -- Values seen before the options are available are picked up when they become available.
        if watch.status=='waiting_for_options'or watch.status=='unavailable'then return end
        -- A child never sits between a write and its completion across ticks (guarded writes
        -- do not yield), so cancelling it here changes no bytes and frees the operation gate.
        dirty,debounce=true,DEBOUNCE
        if child then child.cancel();child=nil end
        if watch.status=='blocked'or watch.status=='running'then watch.status='waiting'end
    end
    for _,handle in ipairs(bound)do handle:subscribe(listener)end
    if enabled_handle then enabled_handle:subscribe(listener)end

    function watch.cancel()
        if child then child.cancel()end
        child=nil;watch.status='cancelled'
        log('ensure '..id..' cancelled')
    end
    function watch.tick(dt)
        if watch.status=='cancelled'or watch.status=='unavailable'
            or watch.status=='waiting_for_options'then return end
        assert(type(dt)=='number'and dt>=0 and dt<math.huge,'invalid elapsed time')
        elapsed=elapsed+dt
        if dirty then
            debounce=debounce-dt
            if debounce>0 then return end
            settle()
        end
        if watch.status=='blocked'or watch.status=='disabled'then return end
        if not child then
            if elapsed<next_at then return end
            if verification then
                local stable,reason=steady.verify(runtime,verification)
                watch.verifications=watch.verifications+1
                if stable then
                    watch.current_interval=math.min(watch.current_interval*2,max_interval)
                    next_at=elapsed+watch.current_interval;return
                end
                watch.drifts=watch.drifts+1;watch.current_interval=interval
                metrics.count('ensure.full_resolutions_after_drift')
                log('ensure '..id..' drift detected ('..tostring(reason)..'); full guarded resolution')
            end
            metrics.count('ensure.full_resolutions')
            launch('apply',target and target.spec or spec,target and target.signature
                or signature(kind,spec,true))
        end
        child.tick(dt)
        if child.status=='rejected'or child.status=='cancelled'then
            watch.result=child.result;watch.error=child.error or'ensured operation cancelled unexpectedly'
            child=nil;watch.status='blocked'
            log('ensure '..id..' blocked until an option changes: '..tostring(watch.error))
            return
        end
        if child.status~='complete'then
            watch.status=child.status=='waiting_for_assets'and'waiting_for_assets'or'running';return
        end
        watch.result=child.result
        if mode=='restore'then
            owned,verification={},nil;applied_signature=target.signature;watch.restores=watch.restores+1
            watch.status='disabled';child=nil
            log('ensure '..id..' restored the reviewed baseline and is disabled')
            return
        end
        owned={}
        each_change(kind,target.spec,function(key,change)owned[key]=change.desired end)
        applied_signature=target.signature;verification=child.verification;child=nil
        watch.runs=watch.runs+1;next_at=elapsed+watch.current_interval;watch.status='waiting'
        log('ensure '..id..' verified status='..watch.result.status..' cycle='..watch.runs
            ..' next='..watch.current_interval..(verification and' steady=byte-check'or' steady=full'))
    end
    -- Mod Options Menu is an optional enhancement. Nothing runs until every option this operation
    -- uses is settled (at most the options startup grace period). An unavailable option supplies
    -- its declared default, which the bind-time proof above already validated, unless its page was
    -- declared with fallback='disable': then the operation stays inactive for the session and
    -- leaves the scheduler.
    local required={}
    for _,handle in ipairs(bound)do required[#required+1]=handle end
    if enabled_handle then required[#required+1]=enabled_handle end
    local function availability()
        local reasons,pending,defaults={},false,false
        for _,handle in ipairs(required)do
            if handle:disables()then reasons[#reasons+1]=handle.id..': '..tostring(handle.reason)
            elseif handle.state=='unavailable'then defaults=true
            elseif handle.state~='ready'then pending=true end
        end
        if #reasons>0 then return 'unavailable',reasons end
        return pending and'pending'or'ready',nil,defaults
    end
    local function on_state()
        if watch.status~='waiting_for_options'then return end
        local state,reasons,defaults=availability()
        if state=='unavailable'then
            watch.status='unavailable';watch.error='options unavailable: '..table.concat(reasons,'; ')
            metrics.count('options.inactive_operations')
        elseif state=='ready'then
            -- Resolve once with the applied values (saved, live, or declared defaults), after the
            -- startup delay, through the same guarded path.
            watch.option_defaults=defaults or nil
            if defaults then metrics.count('options.default_operations')end
            watch.status='waiting';dirty,debounce=true,0
        end
    end
    local late={}
    for _,handle in ipairs(required)do
        handle.page.operations[id]=true
        if handle:disables()and handle.page.warned>0 then late[handle.page.id]=true end
        handle:on_state(on_state)
    end
    watch.status='waiting_for_options'
    on_state()
    if watch.status=='unavailable'and next(late)then
        -- The page warning was logged before this operation was declared.
        log('ensure '..id..' inactive: '..watch.error)
    end
    return watch
end

function M.start(runtime,emit,request)
    assert(type(request)=='table','ensure requires a descriptor')
    local allowed={patch=true,transaction=true,plan=true,interval=true,startup_delay=true,max_interval=true,
        enabled=true}
    for key in pairs(request)do assert(allowed[key],'unsupported ensure option: '..tostring(key))end
    local count=(request.patch and 1 or 0)+(request.transaction and 1 or 0)+(request.plan and 1 or 0)
    assert(count==1,'ensure requires exactly one patch, transaction or plan')
    local interval=request.interval or 60
    local startup=request.startup_delay or 3
    assert(type(interval)=='number' and interval>=1 and interval<math.huge,'invalid ensure interval')
    assert(type(startup)=='number' and startup>=0 and startup<math.huge,'invalid ensure startup delay')
    -- Stable cheap verifications back off geometrically up to this ceiling.
    local max_interval=request.max_interval or math.max(interval,600)
    assert(type(max_interval)=='number' and max_interval>=interval and max_interval<math.huge,
        'invalid ensure max_interval')
    local body_kind=request.patch and'patch'or request.transaction and'transaction'or'plan'
    if request.enabled~=nil or options.contains(request[body_kind])then
        -- Option-bound ensure; requests without options keep the exact path below.
        local validators={patch=patches.validate,transaction=transactions.validate,plan=plans.validate}
        local modules={patch='hd2runtime/api/patch',transaction='hd2runtime/api/transaction',
            plan='hd2runtime/api/plan'}
        local watch=start_bound(runtime,emit,request,body_kind,validators[body_kind],
            require(modules[body_kind]),interval,startup,max_interval)
        return watch
    end
    local kind,spec,module
    if request.patch then
        kind='patch';spec=patches.validate(request.patch);module=require('hd2runtime/api/patch')
    elseif request.transaction then
        kind='transaction';spec=transactions.validate(request.transaction)
        module=require('hd2runtime/api/transaction')
    else
        kind='plan';spec=plans.validate(request.plan);module=require('hd2runtime/api/plan')
    end
    local function log(message)pcall(emit,'[HD2Runtime] '..message)end
    local watch={status='waiting',runs=0,kind=kind,id=spec.id,interval=interval,
        max_interval=max_interval,current_interval=interval,verifications=0,drifts=0}
    local elapsed,next_at,child=0,0,module.start_spec(runtime,emit,spec,startup)
    local verification
    metrics.count('ensure.full_resolutions')
    log('ensure '..spec.id..' scheduled interval='..interval)
    function watch.cancel()
        if child then child.cancel()end
        child=nil;watch.status='cancelled'
        log('ensure '..spec.id..' cancelled')
    end
    function watch.tick(dt)
        if watch.status=='cancelled' or watch.status=='rejected' then return end
        assert(type(dt)=='number' and dt>=0 and dt<math.huge,'invalid elapsed time')
        elapsed=elapsed+dt
        if not child then
            if elapsed<next_at then return end
            if verification then
                -- Steady state: re-check only the retained target bytes. No discovery,
                -- catalog rebuild, fingerprint hashing, protection change, or write.
                local stable,reason=steady.verify(runtime,verification)
                watch.verifications=watch.verifications+1
                if stable then
                    local grown=math.min(watch.current_interval*2,max_interval)
                    if grown==max_interval and watch.current_interval<max_interval then
                        log('ensure '..spec.id..' stable; verification interval='..max_interval)
                    end
                    watch.current_interval=grown;next_at=elapsed+grown
                    return
                end
                watch.drifts=watch.drifts+1;verification=nil;watch.current_interval=interval
                metrics.count('ensure.full_resolutions_after_drift')
                log('ensure '..spec.id..' drift detected ('..tostring(reason)..'); full guarded resolution')
            end
            metrics.count('ensure.full_resolutions')
            child=module.start_spec(runtime,emit,spec,0)
        end
        child.tick(dt)
        if child.status=='rejected' then
            watch.status='rejected';watch.error=child.error;watch.result=child.result;child=nil
            log('ensure '..spec.id..' stopped code='..tostring(watch.result and watch.result.code)
                ..' reason='..tostring(watch.error))
            return
        end
        if child.status=='cancelled' then
            watch.status='rejected';watch.error='ensured operation cancelled unexpectedly';child=nil
            log('ensure '..spec.id..' stopped reason='..watch.error);return
        end
        if child.status=='complete' then
            watch.runs=watch.runs+1;watch.result=child.result;verification=child.verification;child=nil
            next_at=elapsed+watch.current_interval;watch.status='waiting'
            log('ensure '..spec.id..' verified status='..watch.result.status
                ..' cycle='..watch.runs..' next='..watch.current_interval
                ..(verification and' steady=byte-check'or' steady=full'))
        else watch.status='running' end
    end
    return watch
end
return M
