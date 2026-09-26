local b=require('hd2runtime/core/bytes')
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local Entity=require('hd2runtime/core/entity')
local Stratagem=require('hd2runtime/core/stratagem')
local profile=require('hd2runtime/schemas/current')
local catalog=require('hd2runtime/domains/catalog')
local M={}
local function copy(t)
    if type(t)~='table' then return t end
    local result={};for k,v in pairs(t)do result[k]=copy(v)end;return result
end
function M.new(runtime,emit)
    emit=emit or print
    local self={}
    local function log(message)pcall(emit,'[HD2Runtime] '..message)end
    local function key_for(resource)
        if profile.resources[resource] then return resource end
        for key,r in pairs(profile.resources)do if r.resource==resource then return key end end
        error('unknown resource identity: '..tostring(resource))
    end
    function self.describe(resource)
        local key=key_for(resource)
        local fields={}
        for name,f in pairs(catalog[key])do
            fields[name]={component=f.component,storage=f.storage,width=4,expected=f.expected,evidence=copy(f.evidence)}
        end
        return {resource=profile.resources[key].resource,label=profile.resources[key].label,fields=fields}
    end
    function self.read(request)
        assert(type(request)=='table' and type(request.targets)=='table' and #request.targets>0,'read requires targets')
        local requested=copy(request.targets)
        local job={status='pending'}
        local reader
        local worker=coroutine.create(function()
            local exe,dll=runtime.module(nil),runtime.module('game.dll')
            if not exe or not dll then error('TARGET_UNAVAILABLE: game modules not ready',0)end
            assert(runtime.module_hash(exe)==profile.exe_sha and runtime.module_hash(dll)==profile.dll_sha,'unsupported build fingerprint')
            reader=Reader.new(runtime)
            local needed={entity=true}
            local wants_stratagem=false
            for _,target in ipairs(requested)do
                target.key=key_for(target.resource)
                assert(type(target.fields)=='table' and #target.fields>0,'target requires fields')
                for _,name in ipairs(target.fields)do
                    local f=assert(catalog[target.key][name],'unknown field: '..tostring(name))
                    if target.component then assert(target.component==f.component,'component identity mismatch')end
                    if f.component=='DamageSettings' then
                        needed.damage=true
                        if target.key=='jar5' then needed.projectile=true end
                    end
                    if f.component=='StratagemSettings' then wants_stratagem=true end
                end
            end
            local roots=discover.locate(runtime,reader,profile,needed)
            local resolve=Entity.new(reader,roots.entity,profile)
            local stratagem=wants_stratagem and Stratagem.capture(runtime,reader,profile) or nil
            local function record(key,component)
                if component=='StratagemSettings' then
                    -- Also prove that the named payload is a current entity member.
                    local payload=resolve(key,'HellpodPayloadComponentData')
                    stratagem.chain={payload.identity,stratagem.identity}
                    return stratagem
                end
                if component~='DamageSettings' then return resolve(key,component)end
                local kind,chain
                if key=='jar5' then
                    local weapon=resolve(key,'ProjectileWeaponComponentData')
                    assert(b.u32(weapon.bytes,0)==177,'projectile link changed')
                    local projectile=assert(roots.projectile.records[177],'projectile record absent')
                    assert(projectile.group==0 and projectile.row==262,'projectile record identity changed')
                    kind=b.u32(projectile.bytes,60)
                    assert(kind==153,'projectile damage link changed')
                    local consumers=0
                    for _,r in pairs(roots.projectile.records)do if b.u32(r.bytes,60)==kind then consumers=consumers+1 end end
                    assert(consumers==1,'JAR-5 damage has multiple projectile consumers')
                    chain={weapon.identity,{component='ProjectileSettings',component_type=projectile.settings_type,
                        record_index=projectile.row,group=projectile.group,record_kind=177,
                        unique_owner=true,owner_count=1,scope='unique typed settings record'}}
                else
                    local orbital=resolve(key,'OrbitalAbilityComponentData')
                    kind=b.u32(orbital.bytes,476)
                    assert(kind==513,'orbital damage link changed')
                    chain={orbital.identity}
                end
                local r=assert(roots.damage.records[kind],'linked damage record absent')
                assert(r.group==1 and r.row==(key=='jar5' and 158 or 504),'damage record identity changed')
                r.identity={component='DamageSettings',component_type=r.settings_type,record_type='DamageInfo',
                    record_index=r.row,group=r.group,record_kind=kind,unique_owner=true,owner_count=1,
                    scope='unique typed record and checked resource linkage; not all consumers'}
                chain[#chain+1]=r.identity;r.chain=chain
                return r
            end
            local results={}
            for _,target in ipairs(requested)do
                local resource=profile.resources[target.key]
                local output={resource=resource.resource,label=resource.label,fields={},order=copy(target.fields)}
                for _,name in ipairs(target.fields)do
                    local f=catalog[target.key][name]
                    local r=record(target.key,f.component)
                    local value=b.value(r.bytes,f.offset,f.storage)
                    local evidence=copy(f.evidence)
                    evidence.current_live_ownership_proven=runtime.mode=='live'
                    evidence.ownership_scope='resource/component or checked settings linkage; not exhaustive consumer exclusivity'
                    local expected_match=value==f.expected
                    if f.storage=='f32' then expected_match=math.abs(value-f.expected)<=math.abs(f.expected)*0.00000006 end
                    local identity=copy(r.identity)
                    identity.resource=resource.resource;identity.field=name
                    identity.record=r.index or {group=r.group,row=r.row}
                    output.fields[name]={value=value,expected=f.expected,expected_match=expected_match,
                        identity=identity,ownership={unique=true,chain=copy(r.chain)},
                        storage=f.storage,width=4,evidence=evidence}
                end
                results[#results+1]=output
            end
            reader.stage='runtime/reader:stable_reread';reader.verify()
            log('read verified; targets='..#results..'; mode='..tostring(runtime.mode)..'; writes=0; protection_changes=0')
            return {targets=results,mode=runtime.mode or 'fixture',stable_snapshot=true,
                diagnostics={queries=reader.queries,bytes=reader.bytes,query_limit=100000,byte_limit=16*1024*1024},
                fingerprint={exe=profile.exe_sha,dll=profile.dll_sha},writes=0,protection_changes=0}
        end)
        function job.step()
            if job.status=='complete' or job.status=='rejected' then return true end
            job.status='running'
            local ok,result=coroutine.resume(worker)
            job.adapter=reader and reader.stage or 'runtime/windows_readonly:fingerprint'
            if not ok then
                job.status='rejected';job.error=tostring(result)
                job.code=job.error:sub(1,19)=='TARGET_UNAVAILABLE:' and 'TARGET_UNAVAILABLE' or 'VALIDATION_FAILED'
                job.adapter=reader and reader.stage or 'runtime/windows_readonly:fingerprint'
                log('read rejected: '..job.error);return true
            end
            if coroutine.status(worker)=='dead' then job.status='complete';job.result=result;return true end
            return false
        end
        return job
    end
    function self.format(result)
        local lines={}
        for _,target in ipairs(result.targets)do
            lines[#lines+1]=target.label
            for _,name in ipairs(target.order)do
                local f=target.fields[name]
                lines[#lines+1]='  '..name..' = '..string.format('%.7g',f.value)
            end
        end
        return table.concat(lines,'\n')
    end
    function self.observe(request)
        assert(type(request)=='table','observe requires a descriptor')
        local interval=request.interval or 60
        assert(type(interval)=='number' and interval>=1 and interval<math.huge,'invalid observation interval')
        local delay=request.startup_delay or 2
        assert(type(delay)=='number' and delay>=0 and delay<math.huge,'invalid startup delay')
        local elapsed,next_at,job=0,delay,nil
        local attempts=0
        local steps=0
        local timeout=request.timeout or 180
        assert(type(timeout)=='number' and timeout>0 and timeout<math.huge,'invalid timeout')
        local deadline=delay+timeout
        local watch={status='waiting'}
        local targets=copy(request.targets)
        if request.label then log('observation scheduled label='..tostring(request.label)..' startup_delay='..delay)end
        local function callback(fn,...)
            if not fn then return true end
            local ok,result=pcall(fn,...)
            if ok and type(result)=='string' then
                for line in (result..'\n'):gmatch('(.-)\n')do if line~='' then log(line)end end
            end
            return ok,result
        end
        local function reject(reason,detail)
            watch.status='rejected';watch.error=reason;job=nil
            log('observation rejected: '..reason)
            local ok,why=callback(request.on_error,reason,detail)
            if not ok then log('error callback failed: '..tostring(why))end
        end
        function watch.cancel()watch.status='cancelled';job=nil end
        function watch.tick(dt)
            if watch.status=='cancelled' or watch.status=='rejected' then return end
            assert(type(dt)=='number' and dt>=0 and dt<math.huge,'invalid elapsed time')
            elapsed=elapsed+dt
            if elapsed<next_at then return end
            steps=steps+1
            if elapsed>deadline or steps>10000 then
                return reject('observation budget exhausted',{code='TIMEOUT',adapter=job and job.adapter or 'api/observe'})
            end
            if not job then job=self.read({targets=targets});watch.status='reading';attempts=attempts+1 end
            if not job.step() then return end
            if job.status=='rejected' then
                if job.code=='TARGET_UNAVAILABLE' and attempts<6 then
                    log('target not ready; retry '..(attempts+1)..'/6 in 5 update seconds')
                    job=nil;next_at=elapsed+5;watch.status='waiting';return
                end
                return reject(job.error,{code=job.code,adapter=job.adapter})
            end
            if request.on_result then
                local ok,why=callback(request.on_result,job.result)
                if not ok then watch.status='rejected';watch.error=tostring(why);log('observer callback failed: '..watch.error);return end
            end
            next_at=elapsed+interval;job=nil;attempts=0
            deadline=next_at+timeout;steps=0
            if watch.status~='cancelled' then watch.status='waiting' end
        end
        return watch
    end
    local function disabled()
        log('write request rejected: milestone 1 is read-only')
        return nil,{code='READ_ONLY_MILESTONE',message='patch, ensure and transaction require the guarded writer milestone'}
    end
    self.patch=disabled;self.ensure=disabled;self.transaction=disabled
    return self
end
return M
