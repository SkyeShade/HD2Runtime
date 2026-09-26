local Reader=require('hd2runtime/runtime/reader')
local resolution=require('hd2runtime/core/resolution')
local fields=require('hd2runtime/domains/patches')
local writer=require('hd2runtime/core/guarded_write')
local profile=require('hd2runtime/schemas/current')
local M={}
function M.start(runtime,emit,request)
    local spec=fields.validate(request) -- Copies scalars; retains no caller-owned table.
    local watch={status='waiting'}
    local elapsed,steps,worker=0,0,nil
    local function log(message)pcall(emit,'[HD2Runtime] '..message)end
    local function reject(reason)
        watch.status='rejected';watch.error=tostring(reason)
        watch.result=watch.result or {status='REJECTED',writes=0,protection_changes=0,
            protection_restored=true,rollback='not_needed'}
        watch.result.reason=watch.error
        watch.result.code=watch.error:find('CONFLICT:',1,true) and 'CONFLICT' or 'VALIDATION_FAILED'
        log('patch '..spec.id..' REJECTED code='..watch.result.code..' reason='..watch.error)
    end
    function watch.cancel()
        if watch.status~='complete' and watch.status~='rejected' then watch.status='cancelled';worker=nil end
    end
    function watch.tick(dt)
        if watch.status=='complete' or watch.status=='rejected' or watch.status=='cancelled' then return end
        assert(type(dt)=='number' and dt>=0 and dt<math.huge,'invalid elapsed time')
        elapsed=elapsed+dt
        if elapsed<3 then return end
        steps=steps+1
        if elapsed>183 or steps>10000 then return reject('patch resolution budget exhausted')end
        if not worker then worker=coroutine.create(function()
            local reader=Reader.new(runtime)
            -- Fresh discovery on application, never a cached read result/address.
            local resolved=resolution.capture(runtime,reader,{{key='jar5',fields={'armor_penetration'}}})
            local plan=fields.prepare(resolved,reader,spec)
            reader.verify()
            log('patch '..spec.id..' target resolved')
            if spec.diagnostic then
                log('patch '..spec.id..' resource=0x80F1A156D9FA1E36 projectile_type=177'
                    ..' damage_type=153 group=1 record_index=158 width=12 queries='..reader.queries
                    ..' bytes_read='..reader.bytes..' fixture_fallback=disabled mode='..tostring(runtime.mode))
                for _,i in ipairs(plan.chain)do
                    log('patch '..spec.id..' component='..i.component..' type='..i.component_type
                        ..' record_index='..i.record_index..' unique_owner='..tostring(i.unique_owner)
                        ..' scope='..tostring(i.scope or 'resource_component_membership'))
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
        result.id=spec.id;result.field=spec.field;result.resource='0x80F1A156D9FA1E36'
        result.mode=runtime.mode;result.fixture_fallback='disabled'
        if spec.diagnostic then
            log('patch '..spec.id..' writes='..result.writes..' bytes_written='..result.bytes_written
                ..' protection_changes='..result.protection_changes..' rollback='..result.rollback
                ..' guard_queries='..result.guard_queries..' guard_bytes='..result.guard_bytes
                ..' fixture_fallback=disabled')
        end
        if result.status=='APPLIED' then log(spec.field..' '..spec.expect..' -> '..spec.value)end
        log('non_target_bytes_unchanged='..tostring(result.non_target_bytes_unchanged))
        log('protection_restored='..tostring(result.protection_restored))
        if result.status=='REJECTED' then
            log('patch '..spec.id..' rollback='..result.rollback..' writes='..result.writes
                ..' protection_changes='..result.protection_changes
                ..(result.rollback_error and ' rollback_reason='..result.rollback_error or ''))
            return reject(result.reason)
        end
        watch.status='complete'
        log('patch '..spec.id..' '..result.status)
    end
    return watch
end
return M
