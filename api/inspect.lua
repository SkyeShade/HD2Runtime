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
function M.start(runtime,emit,request)
    local items=M.validate(request)
    local target,on_result=request.target,request.on_result
    local job={status='running',kind='inspect',perf_label='inspect '..tostring(target.resource)}
    local results,by_field={},{}
    local index,worker,spent=0,nil,0
    local function finish(item,out)
        out.field=item.field
        results[#results+1]=out;by_field[item.field]=out
    end
    function job.cancel()if job.status=='running'then job.status='cancelled'end end
    function job.tick(dt)
        if job.status~='running'then return end
        spent=spent+(dt or 0)
        if not worker then
            index=index+1
            local item=items[index]
            if not item then
                job.status='complete';job.result={fields=results,by_field=by_field}
                if on_result then
                    local ok,why=pcall(on_result,job.result)
                    if not ok then pcall(emit,'[HD2Runtime] inspect on_result failed: '..tostring(why))end
                end
                return
            end
            if item.expect==nil then
                return finish(item,{state='invalid',reason='no reviewed value for this field: pass {field, expect}'})
            end
            local spec,why=spec_for(target,item.field,item.expect)
            if not spec then return finish(item,{state='invalid',reason=why})end
            for _,change in ipairs(spec.changes or{})do change.inspect={}end
            worker=coroutine.create(function()
                local domains=require('hd2runtime/domains/write_domains')
                local reader=Reader.new(runtime)
                local domain=domains.for_kind(spec.kind)
                local resolved=domain.capture(runtime,reader,spec)
                domain.prepare(resolved,reader,spec)
                reader.verify()
                return spec
            end)
            job.current={item=item,spec=spec,steps=0}
        end
        local current=job.current
        current.steps=current.steps+1
        local ok,result=coroutine.resume(worker)
        if ok and coroutine.status(worker)~='dead'then
            if current.steps<=10000 then return end
            ok,result=false,'inspect resolution budget exhausted'
        end
        worker=nil;job.current=nil
        local change=(current.spec.changes or{})[1]or{field=current.item.field}
        local reason=not ok and tostring(result):gsub('^[^%s:]+:%d+: ','')or nil
        finish(current.item,classify(change,reason))
    end
    return job
end
return M
