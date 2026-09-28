local Reader=require('hd2runtime/runtime/reader')
local exclusive=require('hd2runtime/runtime/exclusive')
local plans=require('hd2runtime/domains/composition_plans')
local domains=require('hd2runtime/domains/write_domains')
local writer=require('hd2runtime/core/guarded_transaction')
local profile=require('hd2runtime/schemas/current')
local M={}

local function fingerprint(runtime)
    return require('hd2runtime/core/fingerprint').matches(runtime)==true
end
local function run_nested(worker)
    while true do
        local result={coroutine.resume(worker)};local ok=table.remove(result,1)
        if not ok then return false,result[1]end
        if coroutine.status(worker)=='dead'then return true,result[1],result[2]end
        coroutine.yield()
    end
end
local function rollback_prior(runtime,history,report)
    local needed=false;local success=true
    for index=#history,1,-1 do
        local item=history[index];local inverse=item.inverse
        if #inverse.changes>0 then
            needed=true
            if not fingerprint(runtime)then
                success=false;item.rollback={status='REJECTED',reason='application fingerprint mismatch'}
            else
                local result=writer.apply(runtime,inverse);item.rollback=result
                report.writes=report.writes+result.writes
                report.bytes_written=report.bytes_written+result.bytes_written
                report.protection_changes=report.protection_changes+result.protection_changes
                report.protection_restored=report.protection_restored and result.protection_restored
                if result.status~='APPLIED'and result.status~='ALREADY_DESIRED'then success=false end
            end
        end
    end
    if not needed then return 'not_needed'end
    return success and'verified'or'refused_or_failed'
end

function M.start_spec(runtime,emit,spec,startup_delay)
    startup_delay=startup_delay==nil and 3 or startup_delay
    assert(type(startup_delay)=='number'and startup_delay>=0 and startup_delay<math.huge,
        'invalid plan startup delay')
    local watch={status='waiting'};local elapsed,steps,worker=0,0,nil;local waited=0
    local function log(message)pcall(emit,'[HD2Runtime] '..message)end
    local function reject(reason,result)
        exclusive.release(watch)
        watch.status='rejected';watch.error=tostring(reason)
        watch.result=result or watch.result or{status='REJECTED',writes=0,bytes_written=0,
            protection_changes=0,protection_restored=true,rollback='not_needed',phases={}}
        watch.result.reason=watch.error
        watch.result.code=watch.error:find('CONFLICT:',1,true)and'CONFLICT'or'VALIDATION_FAILED'
        log('plan '..spec.id..' REJECTED code='..watch.result.code..' reason='..watch.error)
    end
    function watch.cancel()
        if watch.status~='complete'and watch.status~='rejected'then watch.status='cancelled';worker=nil;exclusive.release(watch) end
    end
    function watch.tick(dt)
        if watch.status=='complete'or watch.status=='rejected'or watch.status=='cancelled'then return end
        assert(type(dt)=='number'and dt>=0 and dt<math.huge,'invalid elapsed time')
        elapsed=elapsed+dt;if elapsed<startup_delay then return end
        if not exclusive.acquire(watch)then watch.status='queued';waited=waited+dt;return end
        steps=steps+1;if elapsed-waited>startup_delay+300 or steps>20000 then
            return reject('plan resolution budget exhausted')end
        if not worker then worker=coroutine.create(function()
            local report={status='ALREADY_DESIRED',writes=0,bytes_written=0,
                protection_changes=0,protection_restored=true,
                non_target_bytes_unchanged=true,rollback='not_needed',phases={},fields={}}
            local history={};local any_applied=false
            for _,phase in ipairs(spec.phases)do
                local phase_worker=coroutine.create(function()
                    local reader=Reader.new(runtime)
                    local key=domains.key_for_kind(phase.capture_specs[1].kind)
                    local domain=domains.for_kind(phase.capture_specs[1].kind)
                    for _,capture_spec in ipairs(phase.capture_specs)do
                        assert(domains.key_for_kind(capture_spec.kind)==key,
                            'one plan phase cannot mix stratagem, entity, and weapon targets')
                    end
                    local resolved=domain.capture_many(runtime,reader,phase.capture_specs)
                    local plan=plans.prepare_phase(resolved,reader,phase)
                    reader.verify()
                    assert(fingerprint(runtime),'application fingerprint mismatch')
                    return plan,writer.apply(runtime,plan)
                end)
                local ok,plan,result=run_nested(phase_worker)
                if not ok then
                    report.rollback=rollback_prior(runtime,history,report)
                    report.status='REJECTED';report.reason=tostring(plan)
                    report.non_target_bytes_unchanged=false
                    return report
                end
                report.writes=report.writes+result.writes
                report.bytes_written=report.bytes_written+result.bytes_written
                report.protection_changes=report.protection_changes+result.protection_changes
                report.protection_restored=report.protection_restored and result.protection_restored
                report.non_target_bytes_unchanged=report.non_target_bytes_unchanged
                    and result.non_target_bytes_unchanged
                local phase_report={id=phase.id,index=phase.index,status=result.status,
                    writes=result.writes,bytes_written=result.bytes_written,
                    protection_changes=result.protection_changes,
                    protection_restored=result.protection_restored,
                    non_target_bytes_unchanged=result.non_target_bytes_unchanged,
                    rollback=result.rollback,fields={}}
                for index,change in ipairs(plan.changes)do
                    local field={field=change.label,state=result.fields[index].state,
                        operations=change.plan_operations,phase=phase.index}
                    phase_report.fields[#phase_report.fields+1]=field
                    report.fields[#report.fields+1]=field
                end
                report.phases[#report.phases+1]=phase_report
                if result.status=='REJECTED'then
                    local earlier=rollback_prior(runtime,history,report)
                    if result.rollback=='refused_or_failed'or earlier=='refused_or_failed'then
                        report.rollback='refused_or_failed'
                    elseif result.rollback=='verified'or earlier=='verified'then report.rollback='verified'
                    else report.rollback='not_needed'end
                    report.status='REJECTED';report.reason=result.reason
                    return report
                end
                if result.status=='APPLIED'then any_applied=true end
                history[#history+1]={phase=phase,plan=plan,result=result,inverse=writer.inverse(plan)}
            end
            report.status=any_applied and'APPLIED'or'ALREADY_DESIRED'
            local changes={}
            for _,entry in ipairs(history)do
                for _,change in ipairs(entry.plan.changes)do changes[#changes+1]=change end
            end
            watch.verification=require('hd2runtime/core/steady_state').capture(runtime,changes)
            return report
        end)end
        watch.status='resolving';local ok,result=coroutine.resume(worker)
        if not ok then return reject(result)end
        if coroutine.status(worker)~='dead'then return end
        watch.result=result;result.id=spec.id;result.mode=runtime.mode
        result.fixture_fallback='disabled'
        if result.status=='REJECTED'then return reject(result.reason,result)end
        watch.status='complete';exclusive.release(watch)
        log('plan '..spec.id..' '..result.status..' phases='..#result.phases
            ..' writes='..result.writes..' protection_changes='..result.protection_changes)
        log('non_target_bytes_unchanged='..tostring(result.non_target_bytes_unchanged))
        log('protection_restored='..tostring(result.protection_restored))
    end
    return watch
end
function M.start(runtime,emit,request)
    return M.start_spec(runtime,emit,plans.validate(request),3)
end
return M
