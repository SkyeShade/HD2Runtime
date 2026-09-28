-- Persistent scheduler over the same one-shot guarded operations.
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local plans=require('hd2runtime/domains/composition_plans')
local steady=require('hd2runtime/core/steady_state')
local metrics=require('hd2runtime/runtime/metrics')
local M={}
function M.start(runtime,emit,request)
    assert(type(request)=='table','ensure requires a descriptor')
    local allowed={patch=true,transaction=true,plan=true,interval=true,startup_delay=true,max_interval=true}
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
