-- Public API client: no private runtime modules, schema offsets or native APIs.
local M={}
local function number(value)return type(value)=='number' and string.format('%.9g',value) or tostring(value)end
local function bool(value)return value==true and 'true' or 'false'end
local function safe(value)return tostring(value):gsub('[\r\n]',' ')end
local function identity_text(i)
    local parts={'component='..safe(i.component),'type='..safe(i.component_type),
        'record_type='..safe(i.record_type or 'typed_settings_record'),
        'record_index='..safe(i.record_index),'unique_owner='..bool(i.unique_owner)}
    for _,key in ipairs({'component_index','record_type_id','group','record_kind','index_row','entity_row',
        'owner_count','package','payload','payload_count','payload_pointer','row_pointer'})do
        if i[key]~=nil then parts[#parts+1]=key..'='..safe(i[key])end
    end
    return table.concat(parts,' ')
end
function M.evaluate(spec,result)
    local lines={}
    local prefix='LIVE_VALIDATION resource='..spec.resource..' id='..spec.id
    local target=result.targets and result.targets[1]
    if not target or #result.targets~=1 or target.resource~=spec.id or not result.stable_snapshot
        or result.writes~=0 or result.protection_changes~=0 then
        return 'ERROR',prefix..' status=ERROR reason=invalid_public_read_result',false
    end
    local live=result.mode=='live'
    local mismatch,ownership_error=false,false
    lines[#lines+1]=prefix..' label="'..spec.label..'" mode='..safe(result.mode)..' stable_snapshot=true'
    local fp=result.fingerprint or {}
    lines[#lines+1]=prefix..' exe_sha256='..safe(fp.exe)..' dll_sha256='..safe(fp.dll)
    lines[#lines+1]=prefix..' ownership_scope=resource_component_or_checked_settings_linkage consumer_exclusivity=not_claimed'
    local seen={}
    for _,expected in ipairs(spec.fields)do
        local name=expected.name
        local field=target.fields[name]
        if not field then
            mismatch=true;ownership_error=true
            lines[#lines+1]=prefix..' field='..name..' status=MISSING_FIELD observed=unavailable expected='..number(expected.value)
        else
            local i,e=field.identity,field.evidence
            local matches=type(field.value)=='number' and math.abs(field.value-expected.value)<=expected.tolerance
            if not matches then mismatch=true end
            local want=i and spec.records[i.component]
            local owned=i and e and i.resource==spec.id and i.unique_owner==true
                and field.ownership and field.ownership.unique==true and want~=nil
            if owned then
                for key,value in pairs(want)do if i[key]~=value then owned=false end end
            end
            if not owned then ownership_error=true end
            if not e or e.current_live_ownership_proven~=true then live=false end
            for _,link in ipairs(field.ownership and field.ownership.chain or {})do
                local text=identity_text(link)
                if not seen[text] then lines[#lines+1]=prefix..' ownership '..text;seen[text]=true end
            end
            lines[#lines+1]=prefix..' field='..name..' observed='..number(field.value)
                ..' expected='..number(expected.value)..' status='..(matches and 'MATCH' or 'MISMATCH')
                ..' ownership='..(owned and 'VERIFIED' or 'MISMATCH')
                ..' component='..safe(i and i.component)..' record_index='..safe(i and i.record_index)
            if e then
                lines[#lines+1]=prefix..' field='..name..' provenance='..safe(e.source)
                    ..' structural_candidate='..bool(e.structural_candidate)..' schema_labelled='..bool(e.schema_labelled)
                    ..' current_live_ownership_proven='..bool(e.current_live_ownership_proven)
                    ..' gameplay_proven='..bool(e.gameplay_proven)..' native_consumer_proven='..bool(e.native_consumer_proven)
            end
        end
    end
    local status=ownership_error and 'OWNERSHIP_MISMATCH' or not live and 'NOT_LIVE'
        or mismatch and 'VALUE_MISMATCH' or 'LIVE_PASS'
    local d=result.diagnostics or {}
    lines[#lines+1]=prefix..' status='..status..' queries='..safe(d.queries)..' bytes_read='..safe(d.bytes)
        ..' writes=0 protection_changes=0 fixture_fallback=disabled'
    return status,table.concat(lines,'\n'),live and not ownership_error
end
function M.start(hd2,expectations,metadata)
    local state={status='running',reports={},errors={},mode='read_only',writes=0,protection_changes=0,
        completed=0,live_resolved=0,passed=0}
    local cursor=0
    local function summary()
        return 'LIVE_VALIDATION_SUMMARY completed='..state.completed..'/'..#expectations
            ..' live_resolved='..state.live_resolved..' passed='..state.passed
            ..' commit='..metadata.commit..' writes=0 protection_changes=0 fixture_fallback=disabled'
    end
    local advance
    advance=function()
        cursor=cursor+1
        local spec=expectations[cursor]
        if not spec then state.status='complete';return summary()end
        local described=hd2.describe(spec.resource)
        assert(described.resource==spec.id,'resource expectation differs from public schema')
        local fields={}
        for _,f in ipairs(spec.fields)do
            assert(described.fields[f.name],'field not present in public schema: '..f.name)
            fields[#fields+1]=f.name
        end
        local function finish(message)
            state.completed=state.completed+1
            local ending=advance()
            return ending and message..'\n'..ending or message
        end
        state.watch=hd2.observe{
            label='live_validation resource='..spec.resource..' version='..metadata.version..' commit='..metadata.commit,
            startup_delay=cursor==1 and 3 or 0,timeout=180,
            targets={{resource=spec.resource,fields=fields}},
            on_result=function(result)
                state.watch.cancel()
                local status,text,live=M.evaluate(spec,result)
                state.reports[spec.resource]={status=status,result=result}
                if live then state.live_resolved=state.live_resolved+1 end
                if status=='LIVE_PASS' then state.passed=state.passed+1 end
                return finish(text)
            end,
            on_error=function(reason,detail)
                detail=detail or {}
                state.errors[spec.resource]={reason=reason,adapter=detail.adapter,code=detail.code}
                return finish('LIVE_VALIDATION resource='..spec.resource..' id='..spec.id..' status=ERROR'
                    ..' adapter='..safe(detail.adapter)..' code='..safe(detail.code)..' reason='..safe(reason)
                    ..' observed=unavailable writes=0 protection_changes=0 fixture_fallback=disabled')
            end,
        }
    end
    advance()
    return state
end
return M
