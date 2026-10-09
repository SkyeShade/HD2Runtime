-- Guarded status effect authoring (0.30.4; docs/status-effects.md "Status effect stats"). A status effect's own
-- definition, edited once for every attack that applies it:
--   status: the StatusEffectSettings row of the status (status.duration, +40);
--   damage: the DamageInfo row the status deals while active (StatusEffectInfo +44 names it; damage.*).
-- Every write re-proves, live: the settings allocations (runtime/discover), the status row's identity (its type,
-- group and row), the row's +44 link to the reviewed DamageInfo type (damage path), and that DamageInfo row's
-- identity; then the shared conflict rule (core/ownership). Both rows are global, so allow_shared is always required;
-- the tick damage also needs allow_unverified_effect.
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/status_effect_authoring')
local M={}

local function equal(a,c,storage)
    if storage=='f32'then return type(a)=='number'and type(c)=='number'
        and math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64
        and not value:find('[^%w_%-]'),'invalid operation id')
end
function M.entry(status)return database.statuses[status]end
local function target_for(target)
    assert(type(target)=='table'and target.resource=='status_effect','unsupported status effect target')
    for key in pairs(target)do assert(key=='resource'or key=='status'or key=='path',
        'unsupported status effect target identity')end
    local entry=assert(type(target.status)=='string'and database.statuses[target.status],
        'unknown status effect: '..tostring(target.status)..' (hd2.status_effects() lists every id)')
    local owned=assert(entry.targets[target.path],entry.semanticId..' has no '..tostring(target.path)
        ..' target'..(target.path=='damage'and' (this status deals no tick damage)'or''))
    return entry,owned
end
-- Who else a write to this target changes, for the allow_shared message.
local function shared_text(entry,owned)
    local parts={'every attack that applies '..entry.semanticId}
    if owned.sharedWithStatuses and#owned.sharedWithStatuses>0 then
        parts[#parts+1]='the statuses '..table.concat(owned.sharedWithStatuses,', ')..' (the same tick damage row)'
    end
    if owned.otherUsers and#owned.otherUsers>0 then
        parts[#parts+1]=table.concat(owned.otherUsers,', ')..' (the same DamageInfo row)'
    end
    return table.concat(parts,'; ')
end
local function validate_change(entry,owned,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=assert(owned.fields[item.field],'field is not exposed for status effect '..entry.semanticId..' '
        ..tostring(rawget(request.target,'path'))..': '..tostring(item.field))
    assert(field.editable~=false,'field is read-only: '..item.field)
    assert(request.allow_shared==true,'shared field requires allow_shared=true: '..item.field..' (changes '
        ..shared_text(entry,owned)..')')
    assert(field.acknowledgement~='allow_unverified_effect'or request.allow_unverified_effect==true,
        'field requires allow_unverified_effect=true: '..item.field..' ('..tostring(database.damageAcknowledgement)..')')
    local storage=field.backing.storage
    for _,value in ipairs({item.expect,item.value})do
        assert(type(value)=='number'and value==value and value>-math.huge and value<math.huge,
            'status effect values must be finite numbers')
        if field.type=='integer'then assert(value%1==0,'integer status effect field requires an integer: '..item.field)end
    end
    assert(item.value>=field.min and item.value<=field.max,'value outside the reviewed range ['..field.min..', '
        ..field.max..'] for '..item.field)
    assert(equal(item.expect,field.currentDefault,storage),'expect differs from reviewed current value for '..item.field)
    return {field=item.field,canonical_field=item.field,descriptor=field,
        expected=b.encode(item.expect,storage),desired=b.encode(item.value,storage),expect=item.expect,value=item.value}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local entry,owned=target_for(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=16,'transaction requires one to 16 changes')
    local result={kind='status_effect',id=request.id,status=entry.semanticId,target_path=request.target.path,
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,changes={}}
    local seen={}
    for index,item in ipairs(items)do
        local change=validate_change(entry,owned,item,request)
        assert(not seen[item.field],'duplicate status effect field: '..tostring(item.field));seen[item.field]=true
        result.changes[index]=change
    end
    result.field=request.field;result.expect=request.expect;result.value=request.value
    return result
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

-- A settings record found by its type, at its reviewed group and row.
local function settings_row(root,kind,group,row,label)
    local record=assert(root and root.records[kind],label..' absent')
    assert(record.group==group and record.row==row and record.kind==kind,label..' identity changed')
    return record
end
function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local needed={status=true}
    for _,spec in ipairs(specs)do if spec.target_path=='damage'then needed.damage=true end end
    -- Shared across every spec so each address has exactly one transaction context.
    local roots=discover.locate(runtime,reader,profile,needed)
    local results={}
    for index,spec in ipairs(specs)do
        local entry=assert(database.statuses[spec.status],'reviewed status effect absent')
        reader.stage='domains/status_effect_writes:'..spec.target_path
        local status=settings_row(roots.status,entry.nativeType,entry.group,entry.row,'status '..entry.semanticId..' row')
        local result={status_owner=roots.status.owner,status=status}
        if spec.target_path=='damage'then
            local owned=entry.targets.damage
            -- The status still deals the reviewed DamageInfo type (the link another mod could have changed).
            assert(b.u32(status.bytes,owned.statusLink)==owned.damageType,
                'status '..entry.semanticId..' tick damage link changed')
            result.damage_owner=roots.damage.owner
            result.damage=settings_row(roots.damage,owned.damageType,owned.group,owned.row,
                'status '..entry.semanticId..' tick DamageInfo row')
        end
        results[index]=result
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots};local physical={}
    for _,change in ipairs(spec.changes)do
        local descriptor=change.descriptor
        local backing=descriptor.backing
        local record,owner,component
        if backing.settings=='damage'then record,owner,component=resolved.damage,resolved.damage_owner,'DamageInfo'
        else record,owner,component=resolved.status,resolved.status_owner,'StatusEffectSettings'end
        assert(backing.offset+backing.width<=#record.bytes,'field outside reviewed record')
        local current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
        local expected=ownership.expected(change,current,nil,{target='status_effect '..spec.status
            ..(spec.target_path=='damage'and' damage'or'')})
        local offset=record.offset+backing.offset
        local key=tostring(owner.base)..':'..tostring(offset)
        assert(not physical[key],'overlapping status effect fields');physical[key]=true
        plan.changes[#plan.changes+1]={label=change.field,canonical_field=change.canonical_field,
            semantic_aliases={change.field},owner=owner,offset=offset,field_offset=backing.offset,
            expected=expected,desired=change.desired,before=current,
            already_desired=current==change.desired,expect=change.expect,value=change.value,
            identity={component=component,component_type='semantic',record_index=record.row,
                unique_owner=false,owner_count=0,scope=descriptor.operationGroup},chain={}}
    end
    return plan
end
return M
