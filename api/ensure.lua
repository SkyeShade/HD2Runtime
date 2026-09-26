-- Persistent scheduler over the same one-shot guarded operations.
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local M={}
function M.start(runtime,emit,request)
    assert(type(request)=='table','ensure requires a descriptor')
    local allowed={patch=true,transaction=true,interval=true,startup_delay=true}
    for key in pairs(request)do assert(allowed[key],'unsupported ensure option: '..tostring(key))end
    assert((request.patch~=nil)~=(request.transaction~=nil),
        'ensure requires exactly one patch or transaction')
    local interval=request.interval or 60
    local startup=request.startup_delay or 3
    assert(type(interval)=='number' and interval>=1 and interval<math.huge,'invalid ensure interval')
    assert(type(startup)=='number' and startup>=0 and startup<math.huge,'invalid ensure startup delay')
    local kind,spec,module
    if request.patch then
        kind='patch';spec=patches.validate(request.patch);module=require('hd2runtime/api/patch')
    else
        kind='transaction';spec=transactions.validate(request.transaction)
        module=require('hd2runtime/api/transaction')
    end
    local function log(message)pcall(emit,'[HD2Runtime] '..message)end
    local watch={status='waiting',runs=0,kind=kind,id=spec.id,interval=interval}
    local elapsed,next_at,child=0,0,module.start_spec(runtime,emit,spec,startup)
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
            watch.runs=watch.runs+1;watch.result=child.result;child=nil
            next_at=elapsed+interval;watch.status='waiting'
            log('ensure '..spec.id..' verified status='..watch.result.status
                ..' cycle='..watch.runs..' next='..interval)
        else watch.status='running' end
    end
    return watch
end
return M
