-- hd2.inspect: who owns each field's live value (docs/diagnostics.md "Values changed by mods outside HD2Runtime").
--
-- For a typed target and its fields, runs the same guarded resolution a patch runs (discovery, ownership, identity,
-- the reviewed expected bytes), read only: nothing is written and no page protection changes. Each field reports
--   state 'vanilla'     the reviewed value HD2Runtime's catalogues name (currentDefault);
--         'runtime'     bytes an HD2Runtime patch, transaction, plan or ensure applied (owner = its mod, operation =
--                       its id);
--         'foreign'     neither: a mod outside HD2Runtime changed it (owner = 'unknown': a data-file mod or another
--                       program writing game memory). Writes to it are refused (CONFLICT, owner=unknown); a stats
--                       editor shows it read-only;
--         'changed'     a structural part this field depends on (a link, a status slot, a native array) is not as
--                       reviewed, and no single writer can be named (reason);
--         'unavailable' the target could not be resolved now (reason), e.g. its data is not loaded yet;
--         'invalid'     the request names no exposed field (reason).
-- plus value (the live value, when the field stores it plainly), vanilla (the reviewed value) and reason.
local Reader=require('hd2runtime/runtime/reader')
local b=require('hd2runtime/core/bytes')
local ownership=require('hd2runtime/core/ownership')
local M={}
M.MAX_FIELDS=64

local function plain(value)return type(value)=='number'or type(value)=='string'or type(value)=='boolean'end
-- The reviewed value of a field, from the target's describe() (currentDefault), when the caller gave no expect.
function M.reviewed(target,field)
    local ok,d=pcall(function()return target:describe()end)
    if not ok or type(d)~='table'then return nil end
    local function value(f)
        if type(f)~='table'then return nil end
        if f.currentDefault~=nil then return f.currentDefault end
        return f.expected
    end
    -- describe() lists descriptors in fields (a list, or a map by id) or, beside a list of ids, in fieldInstances
    for _,list in ipairs({d.fields,d.fieldInstances})do
        if type(list)=='table'then
            if type(list[field])=='table'then return value(list[field])end
            for _,f in pairs(list)do
                if type(f)=='table'and(f.semanticFieldId==field or f.name==field)then return value(f)end
            end
        end
    end
    return nil
end
-- A read-only patch spec for one field: value = expect, and every acknowledgement given (nothing is written, so
-- none of them grants anything); an acknowledgement the target's validator does not take is dropped.
local function spec_for(target,field,expect)
    local patches=require('hd2runtime/domains/patches')
    local body={id='hd2rt-inspect',target=target,field=field,expect=expect,value=expect,allow_shared=true,
        allow_unverified_effect=true,allow_unverified_reference=true}
    local why
    for _=1,4 do
        local ok,spec=pcall(patches.validate,body)
        if ok then return spec end
        why=tostring(spec)
        local key=why:match('unsupported[%w ]-option: (allow_[%w_]+)')
        if not key or body[key]==nil then break end
        body[key]=nil
    end
    return nil,(why or'invalid'):gsub('^[^%s:]+:%d+: ','')
end
-- The live value when the field stores it plainly: the reviewed value reads back from its own expected bytes.
local function value_of(change,current)
    local storage=((change.descriptor or{}).backing or{}).storage
    if type(current)~='string'or type(storage)~='string'or type(change.expect)~='number'then return nil end
    local ok,reviewed=pcall(b.value,change.expected,0,storage)
    if not ok or type(reviewed)~='number'then return nil end
    if math.abs(reviewed-change.expect)>math.max(1e-6,math.abs(change.expect)*1e-6)then return nil end
    local read,value=pcall(b.value,current,0,storage)
    return read and value or nil
end
-- One field's state from what its resolution recorded (change.inspect), or from the refusal it raised.
local function classify(change,error_text)
    local out={vanilla=plain(change.expect)and change.expect or nil}
    if error_text then
        local holder=error_text:find('CONFLICT:',1,true)and error_text:match('held by (%S+)')
        if ownership.foreign(error_text)then out.state,out.owner='foreign','unknown'
        elseif holder then out.state,out.owner='runtime',holder
        -- a structural guard (a link, a slot, a native array) is not as reviewed, by a writer it cannot name
        elseif error_text:find('CONFLICT:',1,true)or error_text:find('link changed',1,true)
            or error_text:find('reference changed',1,true)or error_text:find('identity changed',1,true)
            or error_text:find('list changed',1,true)or error_text:find('projectile changed',1,true)then
            out.state='changed'
        else out.state='unavailable'end
        out.reason=error_text
        return out
    end
    local found=change.inspect or{}
    if #found==0 then out.state,out.reason='unavailable','the field resolution recorded no value';return out end
    local first=found[1]
    for _,item in ipairs(found)do
        if item.current~=item.expected then first=item;break end
    end
    out.state,out.owner,out.operation=ownership.state(change,first.current)
    out.bytes=type(first.current)=='string'and b.hex(first.current)or nil
    out.value=value_of(change,first.current)
    if out.state=='foreign'then
        pcall(function()
            local records=require('hd2runtime/core/shared_records')
            local ok,name=pcall(records.describe,change.descriptor or{})
            local target=ok and name or nil
            -- records.describe ends with the catalogue's field id (an attack's own alias of the field, too)
            if target then target=target:match('^(.*) %S+$')or target end
            require('hd2runtime/core/foreign_values').note({target=target,field=change.field,
                observed=out.value~=nil and tostring(out.value)or('0x'..out.bytes),expected=tostring(change.expect)})
        end)
    end
    return out
end

-- request = {target = typed handle, fields = {field id | {field = id, expect = reviewed value}, ...},
--            on_result = function(result) (optional)}. Returns a job: status 'running' | 'complete' | 'rejected',
-- result = {fields = {{field, state, owner, operation, value, vanilla, bytes, reason}, ...}, by_field = {[id] = same}}.
function M.validate(request)
    assert(type(request)=='table','inspect requires a descriptor')
    for key in pairs(request)do
        assert(key=='target'or key=='fields'or key=='on_result','unsupported inspect option: '..tostring(key))
    end
    assert(type(request.target)=='table'and rawget(request.target,'resource')~=nil,
        'inspect requires a typed target (a Runtime handle such as hd2.weapon(name))')
    assert(require('hd2runtime/domains/write_domains').typed_resource(request.target.resource),
        'inspect supports typed targets only: '..tostring(request.target.resource))
    assert(type(request.fields)=='table'and#request.fields>=1 and#request.fields<=M.MAX_FIELDS,
        'inspect requires one to '..M.MAX_FIELDS..' fields')
    assert(request.on_result==nil or type(request.on_result)=='function','on_result must be a function')
    local items={}
    for index,item in ipairs(request.fields)do
        if type(item)=='string'then item={field=item}end
        assert(type(item)=='table'and type(item.field)=='string','field '..index..' must be a field id or {field, expect}')
        local expect=item.expect
        if expect==nil then expect=M.reviewed(request.target,item.field)end
        items[index]={field=item.field,expect=expect}
    end
    return items
end
-- Cost (live 2026-10-09: one resolution per field cost up to 20 ms a call when a mod inspected often): every field
-- of the request is captured once (the domain's capture_many: one discovery, one transaction context per address),
-- then each field's prepare runs in its own coroutine, so one field's refusal never fails another, and one stable
-- re-read verifies them all. A capture or a re-read that fails (the data moved) falls back to one full resolution per
-- field. Coroutines, never pcall, around code that reads: a read may yield (0.30.3: no yield across a C call).
function M.start(runtime,emit,request)
    local items=M.validate(request)
    local target,on_result=request.target,request.on_result
    local job={status='running',kind='inspect',perf_label='inspect '..tostring(target.resource)}
    local results,pending={},{}
    for index,item in ipairs(items)do
        if item.expect==nil then
            results[index]={state='invalid',reason='no reviewed value for this field: pass {field, expect}'}
        else
            local spec,why=spec_for(target,item.field,item.expect)
            if spec then pending[#pending+1]={index=index,item=item,spec=spec}
            else results[index]={state='invalid',reason=why}end
        end
    end
    local function reset(entry)for _,change in ipairs(entry.spec.changes or{})do change.inspect={}end end
    for _,entry in ipairs(pending)do reset(entry)end
    local domain=#pending>0 and require('hd2runtime/domains/write_domains').for_kind(pending[1].spec.kind)
    local stage=#pending>0 and'capture'or'done'
    local worker,steps,cursor,reader,resolved=nil,0,0,nil,nil
    local prepared={}
    local function change_of(entry)return(entry.spec.changes or{})[1]or{field=entry.item.field}end
    local function reason_of(result)return(tostring(result):gsub('^[^%s:]+:%d+: ',''))end
    local function begin(fn)worker=coroutine.create(fn);steps=0 end
    -- Resumes the worker once: nil while it runs, else true and its result or false and why.
    local function step()
        steps=steps+1
        local ok,result=coroutine.resume(worker)
        if ok and coroutine.status(worker)~='dead'then
            if steps<=10000 then return nil end
            ok,result=false,'inspect resolution budget exhausted'
        end
        worker=nil
        return ok,result
    end
    local function single()
        stage,cursor='single',0
        for _,entry in ipairs(pending)do reset(entry)end
    end
    local function finish()
        job.status='complete'
        local fields,by_field={},{}
        for index,item in ipairs(items)do
            local out=results[index]or{state='unavailable',reason='not resolved'}
            out.field=item.field;fields[index]=out;by_field[item.field]=out
        end
        job.result={fields=fields,by_field=by_field}
        if on_result then
            local ok,why=pcall(on_result,job.result)
            if not ok then pcall(emit,'[HD2Runtime] inspect on_result failed: '..tostring(why))end
        end
    end
    function job.cancel()if job.status=='running'then job.status='cancelled'end end
    function job.tick()
        if job.status~='running'then return end
        if stage=='done'then return finish()end
        if stage=='capture'then
            if not worker then
                local specs={}
                for index,entry in ipairs(pending)do specs[index]=entry.spec end
                begin(function()
                    reader=Reader.new(runtime)
                    return domain.capture_many(runtime,reader,specs)
                end)
            end
            local ok,result=step()
            if ok==nil then return end
            if not ok then return single()end
            resolved,stage,cursor=result,'prepare',0
            return
        end
        if stage=='prepare'or stage=='verify'then
            if not worker then
                cursor=cursor+1
                local entry=pending[cursor]
                if not entry then
                    stage='verify'
                    begin(function()reader.verify()end)
                else
                    begin(function()domain.prepare(resolved[cursor],reader,entry.spec)end)
                end
            end
            local ok,result=step()
            if ok==nil then return end
            if stage=='verify'then
                if not ok then return single()end
                for index,entry in ipairs(pending)do
                    if prepared[index]~=nil then
                        results[entry.index]=classify(change_of(entry),prepared[index]~=true and prepared[index]or nil)
                    end
                end
                stage='done'
                return
            end
            prepared[cursor]=ok and true or reason_of(result)
            return
        end
        -- single: one full guarded resolution per field
        if not worker then
            cursor=cursor+1
            local entry=pending[cursor]
            if not entry then stage='done';return end
            begin(function()
                local own=Reader.new(runtime)
                local captured=domain.capture(runtime,own,entry.spec)
                domain.prepare(captured,own,entry.spec)
                own.verify()
            end)
        end
        local entry=pending[cursor]
        local ok,result=step()
        if ok==nil then return end
        results[entry.index]=classify(change_of(entry),not ok and reason_of(result)or nil)
    end
    return job
end
return M
