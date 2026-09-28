local Reader=require('hd2runtime/runtime/reader')
local exclusive=require('hd2runtime/runtime/exclusive')
local resolution=require('hd2runtime/core/resolution')
local fields=require('hd2runtime/domains/patches')
local writer=require('hd2runtime/core/guarded_write')
local profile=require('hd2runtime/schemas/current')
local M={}
function M.start_spec(runtime,emit,spec,startup_delay)
    startup_delay=startup_delay==nil and 3 or startup_delay
    assert(type(startup_delay)=='number' and startup_delay>=0 and startup_delay<math.huge,
        'invalid patch startup delay')
    local watch={status='waiting'}
    local elapsed,steps,worker=0,0,nil;local waited=0
    local function log(message)pcall(emit,'[HD2Runtime] '..message)end
    local function value_text(value)
        if type(value)=='table'and value.weapon and value.attack then
            return value.weapon..':'..value.attack
        end
        return tostring(value)
    end
    local function reject(reason)
        exclusive.release(watch)
        watch.status='rejected';watch.error=tostring(reason)
        watch.result=watch.result or {status='REJECTED',writes=0,protection_changes=0,
            protection_restored=true,rollback='not_needed'}
        watch.result.reason=watch.error
        watch.result.code=watch.error:find('CONFLICT:',1,true) and 'CONFLICT' or 'VALIDATION_FAILED'
        log('patch '..spec.id..' REJECTED code='..watch.result.code..' reason='..watch.error)
    end
    function watch.cancel()
        if watch.status~='complete' and watch.status~='rejected' then watch.status='cancelled';worker=nil;exclusive.release(watch) end
    end
    function watch.tick(dt)
        if watch.status=='complete' or watch.status=='rejected' or watch.status=='cancelled' then return end
        assert(type(dt)=='number' and dt>=0 and dt<math.huge,'invalid elapsed time')
        elapsed=elapsed+dt
        if elapsed<startup_delay then return end
        if not exclusive.acquire(watch)then watch.status='queued';waited=waited+dt;return end
        steps=steps+1
        if elapsed-waited>183 or steps>10000 then return reject('patch resolution budget exhausted')end
        if not worker then worker=coroutine.create(function()
            local reader=Reader.new(runtime)
            -- Fresh discovery on application, never a cached read result/address.
            local resolved,plan
            local domains=require('hd2runtime/domains/write_domains')
            if domains.typed_kind(spec.kind)then
                local domain=domains.for_kind(spec.kind)
                resolved=domain.capture(runtime,reader,spec);plan=domain.prepare(resolved,reader,spec)
            else
                resolved=resolution.capture(runtime,reader,fields.requests(spec))
                plan=fields.prepare(resolved,reader,spec)
            end
            reader.verify()
            log('patch '..spec.id..' target resolved')
            if spec.diagnostic then
                local change=plan.changes and plan.changes[1]or plan
                log('patch '..spec.id..' resource='..tostring(spec.resource)
                    ..' width='..#(change.desired or change.new)..' queries='..reader.queries
                    ..' bytes_read='..reader.bytes..' fixture_fallback=disabled mode='..tostring(runtime.mode))
                for _,i in ipairs(change.chain or{})do
                    log('patch '..spec.id..' component='..tostring(i.component)..' type='..tostring(i.component_type)
                        ..' record_index='..tostring(i.record_index)..' unique_owner='..tostring(i.unique_owner)
                        ..' scope='..tostring(i.scope or 'resource_component_membership'))
                end
            end
            assert(require('hd2runtime/core/fingerprint').matches(runtime),'application fingerprint mismatch')
            local applied=writer.apply(runtime,plan)
            if applied.status=='APPLIED' or applied.status=='ALREADY_DESIRED' then
                -- Retain only what ensure needs for cheap steady-state checks.
                watch.verification=require('hd2runtime/core/steady_state').capture(runtime,
                    plan.changes or{{owner=plan.owner,offset=plan.offset,desired=plan.new}})
            end
            return applied
        end)end
        watch.status='resolving'
        local ok,result=coroutine.resume(worker)
        if not ok then return reject(result)end
        if coroutine.status(worker)~='dead' then return end
        watch.result=result
        result.id=spec.id;result.field=spec.field;result.resource=spec.resource or'0x80F1A156D9FA1E36'
        result.mode=runtime.mode;result.fixture_fallback='disabled'
        if spec.diagnostic then
            log('patch '..spec.id..' writes='..result.writes..' bytes_written='..result.bytes_written
                ..' protection_changes='..result.protection_changes..' rollback='..result.rollback
                ..' guard_queries='..result.guard_queries..' guard_bytes='..result.guard_bytes
                ..' fixture_fallback=disabled')
        end
        if result.status=='APPLIED' then
            log(spec.field..' '..value_text(spec.expect)..' -> '..value_text(spec.value))
        end
        log('non_target_bytes_unchanged='..tostring(result.non_target_bytes_unchanged))
        log('protection_restored='..tostring(result.protection_restored))
        if result.status=='REJECTED' then
            log('patch '..spec.id..' rollback='..result.rollback..' writes='..result.writes
                ..' protection_changes='..result.protection_changes
                ..(result.rollback_error and ' rollback_reason='..result.rollback_error or ''))
            return reject(result.reason)
        end
        watch.status='complete';exclusive.release(watch)
        log('patch '..spec.id..' '..result.status)
    end
    return watch
end
function M.start(runtime,emit,request)
    return M.start_spec(runtime,emit,fields.validate(request),3)
end
return M
