local b=require('hd2runtime/core/bytes')
local Reader=require('hd2runtime/runtime/reader')
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
            fields[name]={name=name,domain=f.domain,value_type=f.value_type,readable=f.readable,
                writable=f.writable,semantic_range=copy(f.semantic_range),enum=f.enum,
                component=f.component,storage=f.storage,width=4,expected=f.expected,evidence=copy(f.evidence)}
        end
        return {resource=profile.resources[key].resource,label=profile.resources[key].label,fields=fields}
    end
    function self.read(request)
        assert(type(request)=='table' and type(request.targets)=='table' and #request.targets>0,'read requires targets')
        local requested=copy(request.targets)
        local job={status='pending'}
        local reader
        local worker=coroutine.create(function()
            reader=Reader.new(runtime)
            for _,target in ipairs(requested)do target.key=key_for(target.resource)end
            local resolved=require('hd2runtime/core/resolution').capture(runtime,reader,requested)
            local record=resolved.record
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
    function self.enumerate_primary_weapons(request)
        return require('hd2runtime/api/weapon_mapper').start(runtime,emit,request)
    end
    function self.map_primary_weapons(request)
        request=request or {}
        local delay=request.startup_delay or 3
        assert(type(delay)=='number'and delay>=0 and delay<math.huge,'invalid mapper startup delay')
        local elapsed,job=0,nil
        local watch={status='waiting'}
        function watch.cancel()watch.status='cancelled';job=nil end
        function watch.tick(dt)
            if watch.status=='cancelled'or watch.status=='complete'or watch.status=='rejected'then return end
            elapsed=elapsed+dt;if elapsed<delay then return end
            if not job then job=self.enumerate_primary_weapons(request);watch.status='running'end
            if not job.step()then return end
            if job.status=='rejected'then
                watch.status='rejected';watch.error=job.error
                if request.on_error then pcall(request.on_error,job.error,{code=job.code,adapter=job.adapter})end
                return
            end
            watch.status='complete';watch.result=job.result
            if request.on_result then
                local ok,why=pcall(request.on_result,job.result)
                if not ok then watch.status='rejected';watch.error=tostring(why);log('mapper callback failed: '..watch.error)end
            end
        end
        return watch
    end
    function self.capture_snapshot(request)
        return require('hd2runtime/api/snapshot_capture').start(runtime,emit,request)
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
        return nil,{code='READ_ONLY_MILESTONE',message='patch, transaction, plan and ensure require the guarded writer milestone'}
    end
    for name,builder in pairs(require('hd2runtime/api/target').new(self.describe))do self[name]=builder end
    local constants=copy(require('hd2runtime/domains/constants'))
    self.fields=constants.fields;self.enums=constants.enums;self.resources=constants.resources
    local authoring=require('hd2runtime/domains/player_weapon_authoring')
    for domain,values in pairs(authoring.fields)do
        self.fields[domain]=self.fields[domain]or{}
        for key,value in pairs(values)do
            if self.fields[domain][key]and self.fields[domain][key]~=value then
                self.fields[domain]['player_'..key]=value
            else self.fields[domain][key]=value end
        end
    end
    local composition=require('hd2runtime/domains/player_weapon_composition')
    for domain,values in pairs(composition.fields)do
        self.fields[domain]=self.fields[domain]or{}
        for key,value in pairs(values)do self.fields[domain][key]=value end
    end
    local support=require('hd2runtime/domains/support_weapon_authoring')
    for domain,values in pairs(support.fields)do
        self.fields[domain]=self.fields[domain]or{}
        for key,value in pairs(values)do self.fields[domain][key]=value end
    end
    local metadata=require('hd2runtime/domains/metadata')
    self.version=metadata.version;self.api_version=metadata.api_version
    function self.patch(request)
        if not runtime.write or not runtime.protect then return disabled()end
        return require('hd2runtime/api/patch').start(runtime,emit,request)
    end
    function self.transaction(request)
        if not runtime.write or not runtime.protect then return disabled()end
        return require('hd2runtime/api/transaction').start(runtime,emit,request)
    end
    function self.plan(request)
        if not runtime.write or not runtime.protect then return disabled()end
        return require('hd2runtime/api/plan').start(runtime,emit,request)
    end
    function self.ensure(request)
        if not runtime.write or not runtime.protect then return disabled()end
        return require('hd2runtime/api/ensure').start(runtime,emit,request)
    end
    return self
end
return M
