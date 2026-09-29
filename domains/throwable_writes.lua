-- Guarded throwable authoring. Every target is a native record the throwable entity owns
-- (ThrowableComponent, ExplosiveComponent, StickyComponent, HealthComponent, ShieldComponent)
-- or reaches through typed references (ExplosionSettings, DamageInfo, ProjectileSettings,
-- StatusEffectSettings). Each write re-proves the entity identity, component ownership and
-- every link of the target's reviewed chain before any memory is touched.
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/throwable_authoring')
local M={}
local component_names={'ThrowableComponentData','ExplosiveComponentData','StickyComponentData',
    'ShieldComponentData','HealthComponentData'}
local PATHS={throwable=true,detonation=true,explosion=true,status_effect=true,shrapnel=true,
    bomblets=true,bomblet_explosion=true,damage=true,entity=true,shield=true}

local function equal(a,c,storage)
    if storage=='f32'then return type(a)=='number'and type(c)=='number'
        and math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64
        and not value:find('[^%w_%-]'),'invalid operation id')
end
local function entry_for(target)
    assert(type(target)=='table'and target.resource=='throwable'and type(target.throwable)=='string',
        'unsupported throwable target')
    local entry=assert(database.throwables[target.throwable],'unknown reviewed throwable: '..target.throwable)
    assert(PATHS[target.path],'unsupported throwable target path: '..tostring(target.path))
    for key in pairs(target)do assert(key=='resource'or key=='throwable'or key=='path'or key=='status',
        'unsupported throwable target identity')end
    local label=target.path
    if target.path=='status_effect'then
        assert(type(rawget(target,'status'))=='string','status effect identity required')
        label=label..':'..target.status
    else assert(rawget(target,'status')==nil,'status identity is only valid on status_effect targets')end
    local owned=assert(entry.targets[label],entry.name..' has no reviewed '..label..' target')
    return entry,owned,label
end
local function validate_change(entry,owned,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=owned.fields[item.field]
    assert(field,'field is not exposed for '..entry.name..': '..tostring(item.field))
    assert(field.editable,'field is read-only: '..item.field..' ('..tostring(field.reason)..')')
    assert(not field.shared or request.allow_shared==true,'shared field requires allow_shared=true: '..item.field)
    assert(request.allow_unverified_effect==true,
        'throwable writes require allow_unverified_effect=true: '..item.field..' ('..field.acknowledgementReason..')')
    local expected,desired=item.expect,item.value
    assert(type(expected)=='number'and expected==expected and expected>-math.huge and expected<math.huge,
        'expect must be a finite number')
    assert(type(desired)=='number'and desired==desired and desired>-math.huge and desired<math.huge,
        'value must be a finite number')
    if field.type=='integer'then
        assert(expected%1==0 and desired%1==0,'integer throwable field requires integer values: '..item.field)
    end
    assert(equal(expected,field.currentDefault,field.backing.storage),
        'expect differs from reviewed current value for '..item.field)
    local range=field.range
    assert(desired>=range.min and desired<=range.max,'value outside the reviewed range ['..range.min..', '
        ..range.max..'] for '..item.field)
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
        expected=b.encode(expected,field.backing.storage),desired=b.encode(desired,field.backing.storage),
        expect=expected,value=desired}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local entry,owned,label=entry_for(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=32,'transaction requires one to 32 changes')
    local result={kind='throwable',id=request.id,throwable=entry.name,target_path=request.target.path,
        target_label=label,diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,
        allow_unverified_effect=request.allow_unverified_effect==true,changes={}}
    local group
    for index,item in ipairs(items)do
        local change=validate_change(entry,owned,item,request)
        group=group or change.descriptor.operationGroup
        assert(not multiple or group==change.descriptor.operationGroup,
            'transaction spans multiple backing objects; use hd2.plan')
        result.changes[index]=change
    end
    result.field=request.field;result.expect=request.expect;result.value=request.value
    return result
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

local function find_candidate(catalog,resource,row)
    local found
    for _,candidate in ipairs(catalog.candidates)do if candidate.resourceHash==resource then
        assert(not found,'throwable entity identity ambiguous');found=candidate end end
    assert(found and found.entityRow and#found.diagnostics==0,'reviewed throwable entity absent')
    assert(found.entityRow==row,'throwable entity owner row changed')
    return found
end
local function component_record(resolved,name)
    local reviewed=assert(resolved.entry.components[name],'unreviewed component '..name)
    local record=resolved.catalog.record(resolved.candidate,name)
    assert(record.identity.recordIndex==reviewed.recordIndex and record.identity.indexRow==reviewed.indexRow,
        'throwable '..name..' ownership changed')
    assert(record.identity.ownerCount==reviewed.ownerCount,'throwable '..name..' consumer scope changed')
    return record
end
local function settings_record(roots,kind,record_type,group,row)
    local root=assert(roots[kind],kind..' settings allocation absent')
    local record=assert(root.records[record_type],'reviewed '..kind..' settings row absent')
    assert(record.kind==record_type and(group==nil or record.group==group)and(row==nil or record.row==row),
        kind..' settings identity changed')
    return record,root.owner
end
-- Re-prove every reviewed link from the throwable entity to the target's records.
local function prove_chain(resolved,owned)
    for _,link in ipairs(owned.chain)do
        local bytes
        if link.from=='component'then bytes=component_record(resolved,link.component).bytes
        else bytes=settings_record(resolved.roots,link.settings,link.recordType).bytes end
        assert(b.u32(bytes,link.offset)==link.expect,'throwable native link changed ('
            ..(link.component or link.settings)..'+'..link.offset..')')
    end
end
local function collect_needs(spec)
    local needed={entity=true}
    local entry=database.throwables[spec.throwable]
    local owned=entry.targets[spec.target_label]
    for _,link in ipairs(owned.chain)do if link.from=='settings'then needed[link.settings]=true end end
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        if backing.kind=='settings'then needed[backing.settings]=true end
    end
    return needed
end
function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local needed={}
    for _,spec in ipairs(specs)do for key in pairs(collect_needs(spec))do needed[key]=true end end
    local roots=discover.locate(runtime,reader,profile,needed)
    local catalog=entities.capture(reader,roots.entity,profile,component_names)
    local results={}
    for index,spec in ipairs(specs)do
        local entry=assert(database.throwables[spec.throwable],'reviewed throwable entry absent')
        local candidate=find_candidate(catalog,entry.resource,entry.entityRow)
        -- The entity must still be a thrown equipment item (it owns its reviewed ThrowableComponent).
        local resolved={entry=entry,catalog=catalog,candidate=candidate,roots=roots}
        component_record(resolved,'ThrowableComponentData')
        prove_chain(resolved,entry.targets[spec.target_label])
        results[index]=resolved
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots};local physical={}
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        local record,owner
        if backing.kind=='component'then
            record=component_record(resolved,backing.component)
            assert(record.identity.uniqueOwner==backing.uniqueOwner,'throwable component uniqueness changed')
            owner=record.owner
        else
            record,owner=settings_record(resolved.roots,backing.settings,backing.recordType,backing.group,backing.row)
        end
        assert(backing.offset+backing.width<=#record.bytes,'field outside reviewed record')
        local current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
        local expected=ownership.expected(change,current)
        local offset=record.offset+backing.offset
        local key=tostring(owner.base)..':'..tostring(offset)..':'..backing.width
        local prior=physical[key]
        if prior then
            assert(prior.canonical_field==change.canonical_field and prior.desired==change.desired,
                'overlapping throwable fields conflict')
        else
            local item={label=change.field,canonical_field=change.canonical_field,
                semantic_aliases={change.field},owner=owner,offset=offset,field_offset=backing.offset,
                expected=expected,desired=change.desired,before=current,
                already_desired=current==change.desired,expect=change.expect,value=change.value,
                identity={component=backing.component or backing.settings,component_type='semantic',
                    record_index=backing.recordIndex or backing.row,
                    unique_owner=not change.descriptor.shared,owner_count=backing.ownerCount or 0,
                    scope=change.descriptor.operationGroup},
                chain={}}
            physical[key]=item;plan.changes[#plan.changes+1]=item
        end
    end
    return plan
end
return M
