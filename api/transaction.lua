local Reader=require('hd2runtime/runtime/reader')
local resolution=require('hd2runtime/core/resolution')
local domain=require('hd2runtime/domains/transactions')
local writer=require('hd2runtime/core/guarded_transaction')
local profile=require('hd2runtime/schemas/current')
local M={}
function M.start_spec(runtime,emit,spec,startup_delay)
    startup_delay=startup_delay==nil and 3 or startup_delay
    assert(type(startup_delay)=='number' and startup_delay>=0 and startup_delay<math.huge,
        'invalid transaction startup delay')
    local watch={status='waiting'}
    local elapsed,steps,worker=0,0,nil
    local function log(message)pcall(emit,'[HD2Runtime] '..message)end
    local function value_text(value)
        if type(value)=='table'and value.weapon and value.attack then
            return value.weapon..':'..value.attack
        end
        return tostring(value)
    end
    local function reject(reason)
        watch.status='rejected';watch.error=tostring(reason)
        watch.result=watch.result or {status='REJECTED',writes=0,protection_changes=0,
            protection_restored=true,rollback='not_needed'}
        watch.result.reason=watch.error
        watch.result.code=watch.error:find('CONFLICT:',1,true) and 'CONFLICT' or 'VALIDATION_FAILED'
        log('transaction '..spec.id..' REJECTED code='..watch.result.code..' reason='..watch.error)
    end
    function watch.cancel()
        if watch.status~='complete' and watch.status~='rejected' then watch.status='cancelled';worker=nil end
    end
    function watch.tick(dt)
        if watch.status=='complete' or watch.status=='rejected' or watch.status=='cancelled' then return end
        assert(type(dt)=='number' and dt>=0 and dt<math.huge,'invalid elapsed time')
        elapsed=elapsed+dt
        if elapsed<startup_delay then return end
        steps=steps+1
        if elapsed>startup_delay+180 or steps>10000 then
            return reject('transaction resolution budget exhausted')
        end
        if not worker then worker=coroutine.create(function()
            local reader=Reader.new(runtime)
            local resolved,plan
            local domains=require('hd2runtime/domains/write_domains')
            if domains.typed_kind(spec.kind)then
                local weapons=domains.for_kind(spec.kind)
                resolved=weapons.capture(runtime,reader,spec);plan=weapons.prepare(resolved,reader,spec)
            else
                resolved=resolution.capture(runtime,reader,domain.requests(spec))
                plan=domain.prepare(resolved,reader,spec)
            end
            reader.verify()
            log('transaction '..spec.id..' targets resolved')
            if spec.diagnostic then
                log('transaction '..spec.id..' resource='..tostring(spec.resource)..' changes='..#plan.changes
                    ..' queries='..reader.queries..' bytes_read='..reader.bytes
                    ..' fixture_fallback=disabled mode='..tostring(runtime.mode))
                for _,change in ipairs(plan.changes)do
                    log('transaction '..spec.id..' field='..change.label
                        ..' component='..change.identity.component
                        ..' type='..change.identity.component_type
                        ..' record_index='..change.identity.record_index
                        ..' unique_owner='..tostring(change.identity.unique_owner))
                end
            end
            local exe,dll=runtime.module(nil),runtime.module('game.dll')
            assert(exe and dll and runtime.module_hash(exe)==profile.exe_sha
                and runtime.module_hash(dll)==profile.dll_sha,'application fingerprint mismatch')
            return writer.apply(runtime,plan)
        end)end
        watch.status='resolving'
        local ok,result=coroutine.resume(worker)
        if not ok then return reject(result)end
        if coroutine.status(worker)~='dead' then return end
        watch.result=result
        result.id=spec.id;result.resource=spec.resource
        result.mode=runtime.mode;result.fixture_fallback='disabled'
        if spec.diagnostic then
            log('transaction '..spec.id..' writes='..result.writes
                ..' bytes_written='..result.bytes_written
                ..' protection_changes='..result.protection_changes
                ..' rollback='..result.rollback..' guard_queries='..result.guard_queries
                ..' guard_bytes='..result.guard_bytes..' fixture_fallback=disabled')
        end
        if result.status=='APPLIED' or result.status=='ALREADY_DESIRED' then
            for index,change in ipairs(spec.changes)do
                local state=result.fields[index].state
                if state=='APPLIED' then
                    log(change.field..' '..value_text(change.expect)..' -> '..value_text(change.value))
                else log(change.field..' already '..value_text(change.value))end
            end
        end
        log('non_target_bytes_unchanged='..tostring(result.non_target_bytes_unchanged))
        log('protection_restored='..tostring(result.protection_restored))
        if result.status=='REJECTED' then
            log('transaction '..spec.id..' rollback='..result.rollback..' writes='..result.writes
                ..' protection_changes='..result.protection_changes
                ..(result.rollback_error and ' rollback_reason='..result.rollback_error or ''))
            return reject(result.reason)
        end
        watch.status='complete'
        log('transaction '..spec.id..' '..result.status)
    end
    return watch
end
function M.start(runtime,emit,request)
    return M.start_spec(runtime,emit,domain.validate(request),3)
end
return M
