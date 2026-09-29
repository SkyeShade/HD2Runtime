-- Guarded vehicle and backpack entity authoring. Field identities come from the
-- generated entity catalog; mount references accept only discovered semantic
-- weapon identities and never caller-supplied native identifiers.
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/entity_authoring')
local M={}
local component_names={'HealthComponentData','MountComponentData','RechargeComponentData',
    'JumppackComponentData','ShieldComponentData','HellpodRackComponentData','WeaponDataComponentData',
    'DepositComponentData','TagComponentData','WeaponLinkedAmmoComponentData'}
local REFERENCE='mounted_weapon_reference'

local function equal(a,c,storage)
    if storage=='f32'then return type(a)=='number'and type(c)=='number'
        and math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64
        and not value:find('[^%w_%-]'),'invalid operation id')
end
local function u64(resource)
    assert(type(resource)=='string'and resource:match('^0x%x%x%x%x%x%x%x%x%x%x%x%x%x%x%x%x$'),
        'reviewed resource identity malformed')
    local out={}
    for index=17,3,-2 do out[#out+1]=string.char(tonumber(resource:sub(index,index+1),16))end
    return table.concat(out)
end
local function entry_for(target)
    assert(type(target)=='table','entity target must be a descriptor')
    if target.resource=='vehicle'then
        local entry=assert(type(target.vehicle)=='string'and database.vehicles[target.vehicle],
            'unknown reviewed vehicle: '..tostring(target.vehicle))
        if target.path=='damage_zone'then
            assert(type(rawget(target,'zone'))=='string','damage zone identity required')
        elseif target.path=='mount'then
            assert(type(rawget(target,'mount'))=='string','mount slot identity required')
        else assert(target.path=='entity','unsupported vehicle target path')end
        for key in pairs(target)do assert(key=='resource'or key=='vehicle'or key=='path'
            or key=='zone'or key=='mount','unsupported vehicle target identity')end
        return entry,target.vehicle
    end
    assert(target.resource=='backpack','unsupported entity target')
    local entry=assert(type(target.backpack)=='string'and database.backpacks[target.backpack],
        'unknown reviewed backpack: '..tostring(target.backpack))
    assert(target.path=='backpack','unsupported backpack target path')
    for key in pairs(target)do assert(key=='resource'or key=='backpack'or key=='path',
        'unsupported backpack target identity')end
    return entry,target.backpack
end
local function find_field(entry,target,id)
    for _,field in ipairs(entry.fields)do
        local t=field.target
        if field.semanticFieldId==id and t.path==target.path
            and t.zone==rawget(target,'zone') and t.mount==rawget(target,'mount') then return field end
    end
    error('field is not exposed for '..entry.name..': '..tostring(id),0)
end
local function weapon_identity(value)
    if type(value)=='table'then value=value.semanticId end
    assert(type(value)=='string','mounted weapon reference must be a discovered semantic identity')
    return assert(database.mountedWeapons[value],'unknown discovered mounted weapon: '..value)
end
local function validate_change(entry,target,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=find_field(entry,target,item.field)
    assert(field.editable and field.backing,'field is read-only: '..item.field..' ('..tostring(field.reason)..')')
    assert(not field.shared or request.allow_shared==true,'shared field requires allow_shared=true: '..item.field)
    assert(field.acknowledgement~='allow_unverified_effect'or request.allow_unverified_effect==true,
        'field requires allow_unverified_effect=true: '..item.field..' ('..tostring(field.acknowledgementReason)..')')
    local storage=field.backing.storage
    if field.type==REFERENCE then
        assert(request.allow_unverified_reference==true,
            'mount reference swaps require allow_unverified_reference=true: '..item.field)
        local expected,desired=weapon_identity(item.expect),weapon_identity(item.value)
        assert(expected.semanticId==field.currentDefault,
            'expect differs from the reviewed mounted weapon for '..item.field)
        local allowed=false
        for _,candidate in ipairs(field.allowedValues or{})do
            if candidate==desired.semanticId then allowed=true end
        end
        assert(allowed or desired.semanticId==expected.semanticId,
            'replacement is not a compatible discovered mounted weapon: '..desired.semanticId)
        -- The replacement weapon's assets (its own package, or its vanilla vehicle's) load automatically.
        local dependency=desired.semanticId~=expected.semanticId
            and require('hd2runtime/core/assets').dependency('mounted_weapon/'..desired.semanticId)or nil
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            expected=u64(expected.resource),desired=u64(desired.resource),
            expect=expected.semanticId,value=desired.semanticId,replacement=desired,asset_dependency=dependency}
    end
    local expected,desired=item.expect,item.value
    assert(type(expected)=='number'and expected==expected and expected>-math.huge and expected<math.huge,
        'expect must be a finite number')
    assert(type(desired)=='number'and desired==desired and desired>-math.huge and desired<math.huge,
        'value must be a finite number')
    if field.type=='integer'then
        assert(expected%1==0 and desired%1==0,'integer entity field requires integer values')
    end
    assert(equal(expected,field.currentDefault,storage),
        'expect differs from reviewed current value for '..item.field)
    if field.min then
        assert(desired>=field.min and desired<=field.max,
            'value outside the reviewed range for '..item.field..' ('..field.min..' to '..field.max..')')
    end
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
        expected=b.encode(expected,storage),desired=b.encode(desired,storage),expect=expected,value=desired}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_reference=true,
        allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local entry,name=entry_for(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=32,'transaction requires one to 32 changes')
    local result={kind='entity',family=request.target.resource,id=request.id,entity=name,
        target_path=request.target.path,diagnostic=request.diagnostic==true,
        allow_shared=request.allow_shared==true,allow_unverified_effect=request.allow_unverified_effect==true,
        changes={}}
    local group
    for index,item in ipairs(items)do
        local change=validate_change(entry,request.target,item,request)
        group=group or change.descriptor.operationGroup
        assert(not multiple or group==change.descriptor.operationGroup,
            'transaction spans multiple backing objects; use hd2.plan')
        result.changes[index]=change
        if change.asset_dependency then
            result.asset_dependencies=result.asset_dependencies or{}
            result.asset_dependencies[#result.asset_dependencies+1]=change.asset_dependency
        end
    end
    result.field=request.field;result.expect=request.expect;result.value=request.value
    return result
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

local function find_candidate(catalog,resource,row)
    local found
    for _,candidate in ipairs(catalog.candidates)do if candidate.resourceHash==resource then
        assert(not found,'entity identity ambiguous');found=candidate end end
    assert(found and found.entityRow and#found.diagnostics==0,'reviewed entity identity absent')
    assert(row==nil or found.entityRow==row,'entity owner row changed')
    return found
end
local function entry_of(spec)
    return spec.family=='vehicle'and database.vehicles[spec.entity]or database.backpacks[spec.entity]
end
function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local roots=discover.locate(runtime,reader,profile,{entity=true})
    local catalog=entities.capture(reader,roots.entity,profile,component_names)
    local results={}
    for index,spec in ipairs(specs)do
        local entry=assert(entry_of(spec),'reviewed entity entry absent')
        local candidate=find_candidate(catalog,entry.resource,entry.entityRow)
        if spec.family=='backpack'then
            -- Re-prove the call-in chain: the reviewed hellpod rack still attaches this backpack.
            local rack=find_candidate(catalog,entry.rack.resource)
            local record=catalog.record(rack,'HellpodRackComponentData')
            assert(record.identity.recordIndex==entry.rack.recordIndex
                and record.identity.indexRow==entry.rack.indexRow,'backpack rack ownership changed')
            local attached=false
            local slots=entry.rack.slots or{}
            for slot=0,7 do
                local item=b.resource(record.bytes,slot*64)
                if item==entry.resource then attached=true
                elseif slots[tostring(slot)]then
                    assert(item==slots[tostring(slot)],'backpack rack no longer delivers the reviewed support weapon')
                else assert(item=='0x0000000000000000','backpack rack attaches an unreviewed item')end
            end
            assert(attached,'backpack rack no longer attaches the reviewed backpack')
            local feeds=entry.feeds
            if feeds then
                -- Re-prove the ammunition link: the weapon draws from the Backpack slot through a tag
                -- that this backpack carries.
                local weapon=find_candidate(catalog,feeds.weaponResource,feeds.weaponEntityRow)
                local linked=catalog.record(weapon,'WeaponLinkedAmmoComponentData')
                assert(linked.identity.recordIndex==feeds.linkedAmmo.recordIndex
                    and linked.identity.indexRow==feeds.linkedAmmo.indexRow,'weapon linked-ammo ownership changed')
                assert(b.resource(linked.bytes,0)==feeds.tag.value and b.u32(linked.bytes,8)==feeds.ammoMode
                    and b.u32(linked.bytes,12)==feeds.inventorySlot,'weapon no longer draws ammunition from this backpack')
                local tag=catalog.record(candidate,'TagComponentData')
                assert(tag.identity.recordIndex==feeds.tag.recordIndex and tag.identity.indexRow==feeds.tag.indexRow,
                    'backpack tag ownership changed')
                assert(b.resource(tag.bytes,0)==feeds.tag.value,'backpack no longer carries the weapon ammunition tag')
            end
        end
        for _,change in ipairs(spec.changes)do
            if change.replacement then
                local weapon=find_candidate(catalog,change.replacement.resource,change.replacement.entityRow)
                assert(weapon.ownership.WeaponDataComponentData,'replacement mounted weapon is not a live weapon entity')
            end
        end
        results[index]={entry=entry,catalog=catalog,candidate=candidate}
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
            and record.identity.indexRow==backing.indexRow,'entity component ownership changed')
        assert(record.identity.ownerCount==backing.ownerCount
            and record.identity.uniqueOwner==backing.uniqueOwner,'entity component consumer scope changed')
        assert(backing.offset+backing.width<=#record.bytes,'field outside reviewed record')
        local current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
        local expected=ownership.expected(change,current)
        local offset=record.offset+backing.offset
        local key=tostring(record.owner.base)..':'..tostring(offset)..':'..backing.width
        local prior=physical[key]
        if prior then
            assert(prior.canonical_field==change.canonical_field and prior.desired==change.desired,
                'overlapping entity fields conflict')
        else
            local item={label=change.field,canonical_field=change.canonical_field,
                semantic_aliases={change.field},owner=record.owner,offset=offset,field_offset=backing.offset,
                expected=expected,desired=change.desired,before=current,
                already_desired=current==change.desired,expect=change.expect,value=change.value,
                identity={component=backing.component,component_type='semantic',
                    record_index=backing.recordIndex,unique_owner=backing.uniqueOwner,
                    owner_count=backing.ownerCount,scope=change.descriptor.sharedScopeKey},
                chain={}}
            physical[key]=item;plan.changes[#plan.changes+1]=item
        end
    end
    return plan
end
return M
