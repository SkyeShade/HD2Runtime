-- Guarded enemy and enemy-structure health / damage-zone authoring. Each class is a hash-verified native entity;
-- its HealthComponent record identity (record, index row, owner count) is re-proven before every write. Field
-- descriptors are built from the compact generated database (domains/enemy_authoring.lua).
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/enemy_authoring')
local M={}
local component_names={'HealthComponentData'}

local function equal(a,c,storage)
    if storage=='f32'then return type(a)=='number'and type(c)=='number'
        and math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64
        and not value:find('[^%w_%-]'),'invalid operation id')
end
function M.entry(name)
    local canonical=database.enemies[name]and name or database.aliases[name]
    return canonical and database.enemies[canonical]or nil
end
local function entry_for(target)
    assert(type(target)=='table'and target.resource=='enemy','unsupported enemy target')
    local entry=assert(type(target.enemy)=='string'and database.enemies[target.enemy],
        'unknown reviewed enemy: '..tostring(target.enemy))
    if target.path=='damage_zone'then
        assert(type(rawget(target,'zone'))=='string','damage zone identity required')
    else assert(target.path=='entity','unsupported enemy target path')end
    for key in pairs(target)do assert(key=='resource'or key=='enemy'or key=='path'or key=='zone',
        'unsupported enemy target identity')end
    return entry
end
-- The generated entry plus the field schema as one descriptor.
function M.descriptor(entry,field)
    local schema=assert(database.schema[field.id],'field schema missing: '..field.id)
    local backing={component=entry.health.component,resource=entry.resource,
        recordIndex=entry.health.recordIndex,indexRow=entry.health.indexRow,ownerCount=entry.health.ownerCount,
        uniqueOwner=entry.health.uniqueOwner}
    for key,value in pairs(field.backing)do backing[key]=value end
    return {semanticFieldId=field.id,type=schema.type,currentDefault=field.currentDefault,editable=field.editable~=false,
        reason=field.reason,target={resource='enemy',enemy=entry.name,path=field.path,zone=field.zone},
        backing=backing,shared=not backing.uniqueOwner,min=schema.min,max=schema.max,
        acknowledgement=schema.acknowledgement,
        acknowledgementReason=schema.acknowledgement and('The HealthComponent member is identified by its '
            ..'hidden member-name length and exact agreement with the wiki anatomy tables; its gameplay effect on '
            ..'enemies is not yet live-confirmed.')or nil,
        operationGroup=entry.semanticId..'/'..tostring(field.path)..'/'..tostring(field.zone)}
end
local function find_field(entry,target,id)
    for _,field in ipairs(entry.fields)do
        if field.id==id and field.path==target.path and field.zone==rawget(target,'zone')then
            return M.descriptor(entry,field)
        end
    end
    error('field is not exposed for '..entry.name..': '..tostring(id),0)
end
local function validate_change(entry,target,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=find_field(entry,target,item.field)
    assert(field.editable,'field is read-only: '..item.field..' ('..tostring(field.reason)..')')
    assert(not field.shared or request.allow_shared==true,'shared field requires allow_shared=true: '..item.field)
    assert(field.acknowledgement~='allow_unverified_effect'or request.allow_unverified_effect==true,
        'field requires allow_unverified_effect=true: '..item.field..' ('..tostring(field.acknowledgementReason)..')')
    local storage=field.backing.storage
    local expected,desired=item.expect,item.value
    assert(type(expected)=='number'and expected==expected and expected>-math.huge and expected<math.huge,
        'expect must be a finite number')
    assert(type(desired)=='number'and desired==desired and desired>-math.huge and desired<math.huge,
        'value must be a finite number')
    if field.type=='integer'then
        assert(expected%1==0 and desired%1==0,'integer enemy field requires integer values')
    end
    assert(equal(expected,field.currentDefault,storage),'expect differs from reviewed current value for '..item.field)
    assert(desired>=field.min and desired<=field.max,
        'value outside the reviewed range for '..item.field..' ('..field.min..' to '..field.max..')')
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
        expected=b.encode(expected,storage),desired=b.encode(desired,storage),expect=expected,value=desired}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local entry=entry_for(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=32,'transaction requires one to 32 changes')
    local result={kind='enemy',id=request.id,enemy=entry.name,target_path=request.target.path,
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,
        allow_unverified_effect=request.allow_unverified_effect==true,changes={}}
    for index,item in ipairs(items)do
        result.changes[index]=validate_change(entry,request.target,item,request)
    end
    result.field=request.field;result.expect=request.expect;result.value=request.value
    return result
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

local function find_candidate(catalog,resource,row)
    local found
    for _,candidate in ipairs(catalog.candidates)do if candidate.resourceHash==resource then
        assert(not found,'enemy identity ambiguous');found=candidate end end
    assert(found and found.entityRow and#found.diagnostics==0,'reviewed enemy identity absent')
    assert(row==nil or found.entityRow==row,'enemy owner row changed')
    return found
end
function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local roots=discover.locate(runtime,reader,profile,{entity=true})
    local catalog=entities.capture(reader,roots.entity,profile,component_names)
    local results={}
    for index,spec in ipairs(specs)do
        local entry=assert(database.enemies[spec.enemy],'reviewed enemy entry absent')
        results[index]={entry=entry,catalog=catalog,candidate=find_candidate(catalog,entry.resource,entry.entityRow)}
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots};local physical={}
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        local record=resolved.catalog.record(resolved.candidate,backing.component)
        assert(record.identity.recordIndex==backing.recordIndex
            and record.identity.indexRow==backing.indexRow,'enemy health record ownership changed')
        assert(record.identity.ownerCount==backing.ownerCount
            and record.identity.uniqueOwner==backing.uniqueOwner,'enemy health record consumer scope changed')
        assert(backing.offset+backing.width<=#record.bytes,'field outside reviewed record')
        local current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
        local expected=ownership.expected(change,current)
        local offset=record.offset+backing.offset
        local key=tostring(record.owner.base)..':'..tostring(offset)..':'..backing.width
        local prior=physical[key]
        if prior then
            assert(prior.canonical_field==change.canonical_field and prior.desired==change.desired,
                'overlapping enemy fields conflict')
        else
            local item={label=change.field,canonical_field=change.canonical_field,
                semantic_aliases={change.field},owner=record.owner,offset=offset,field_offset=backing.offset,
                expected=expected,desired=change.desired,before=current,
                already_desired=current==change.desired,expect=change.expect,value=change.value,
                identity={component=backing.component,component_type='semantic',
                    record_index=backing.recordIndex,unique_owner=backing.uniqueOwner,
                    owner_count=backing.ownerCount,scope=change.descriptor.operationGroup},
                chain={}}
            physical[key]=item;plan.changes[#plan.changes+1]=item
        end
    end
    return plan
end
return M
