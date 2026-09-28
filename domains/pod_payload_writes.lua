-- Guarded drop-pod payload authoring: HellpodRackComponent slot items and spawn count.
-- Replacements are catalog pickups only (hd2.pickup); raw identifiers are never accepted.
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local Stratagem=require('hd2runtime/core/stratagem')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/pod_payload_authoring')
local M={}
local component_names={'HellpodRackComponentData','InteractableComponentData','BackpackComponentData',
    'WeaponDataComponentData'}
local ENTITY,COUNT='payload.entity','payload.spawn_count'
local EMPTY='0x0000000000000000'
local SLOT_STRIDE,COUNT_OFFSET,RANDOM_OFFSET=64,556,552
local INTERACT={PickupWeaponPrimary=1,PickupWeaponSidearm=2,PickupWeaponSupport=3,PickupAmmo=4,PickupHealth=5,
    PickupGrenades=6,PickupSupplies=7,PickupSuppliesFromRack=8}

local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64 and not value:find('[^%w_%-]'),'invalid operation id')
end
local function u64(resource)
    local out={}
    for index=17,3,-2 do out[#out+1]=string.char(tonumber(resource:sub(index,index+1),16))end
    return table.concat(out)
end
local function rack_for(target)
    assert(type(target)=='table'and target.resource=='pod_rack','unsupported pod payload target')
    local rack=assert(type(target.rack)=='string'and database.racks[target.rack],
        'unknown reviewed pod rack: '..tostring(target.rack))
    assert(rack.writable,rack.name..' is read-only: '..tostring(rack.reason))
    for key in pairs(target)do assert(key=='resource'or key=='rack'or key=='path'or key=='slot',
        'unsupported pod payload target identity')end
    if target.path=='slot'then
        local slot=database.racks[target.rack].slots[tostring(target.slot)]
        assert(slot,'slot '..tostring(target.slot)..' of '..rack.name..' is not an authored payload slot')
        return rack,slot
    end
    assert(target.path=='rack','unsupported pod payload target path')
    return rack,nil
end
-- A pickup handle (hd2.pickup), its semantic identity, or 'empty'. Never a raw identifier.
local function pickup_of(value,label)
    if value=='empty'then return 'empty'end
    if type(value)=='table'then value=value.semanticId end
    assert(type(value)=='string',label..' must be a pickup from hd2.pickup(...) or \"empty\"')
    return assert(database.pickups[value],label..' is not a reviewed pickup: '..value)
end
local function identity_of(pickup)return pickup=='empty'and'empty'or pickup.semanticId end
local function resource_of(pickup)return pickup=='empty'and EMPTY or pickup.resource end

local function descriptor(rack,field)
    return {semanticFieldId=field,operationGroup='pod-rack:'..rack.semanticId,shared=rack.shared,
        backing={kind='component',component='HellpodRackComponentData'}}
end
local function validate_change(rack,slot,target,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    assert(not rack.shared or request.allow_shared==true,
        rack.name..' is shared by '..#rack.consumers..' stratagems; payload writes require allow_shared=true')
    if item.field==ENTITY then
        assert(target.path=='slot','payload.entity is a slot field; use rack:slot(n)')
        local expected=pickup_of(item.expect,'expect');local desired=pickup_of(item.value,'value')
        assert(identity_of(expected)==slot.current,'expect differs from the reviewed slot item for '..rack.name
            ..' slot '..target.slot)
        assert(identity_of(desired)==slot.current or request.allow_unverified_reference==true,
            'replacement requires allow_unverified_reference=true ('..database.unverifiedReason..')')
        return {field=item.field,canonical_field=ENTITY,descriptor=descriptor(rack,ENTITY),
            offset=slot.index*SLOT_STRIDE,width=8,
            expected=u64(slot.resource),desired=u64(resource_of(desired)),expect=identity_of(expected),
            value=identity_of(desired),replacement=desired~='empty'and desired or nil,slot=slot}
    end
    assert(item.field==COUNT,'field is not exposed for '..rack.name..': '..tostring(item.field))
    assert(target.path=='rack','payload.spawn_count is a rack field; use the rack target')
    assert(item.expect==rack.spawnCount,'expect differs from the reviewed spawn count for '..rack.name)
    local value=item.value
    assert(type(value)=='number'and value%1==0 and value>=1 and value<=database.authoredSlots,
        'spawn count must be an integer from 1 to '..database.authoredSlots)
    assert(value==rack.spawnCount or request.allow_unverified_effect==true,
        'spawn count changes require allow_unverified_effect=true ('..database.countReason..')')
    return {field=item.field,canonical_field=COUNT,descriptor=descriptor(rack,COUNT),offset=COUNT_OFFSET,width=4,
        expected=b.encode(rack.spawnCount,'u32'),desired=b.encode(value,'u32'),expect=item.expect,value=value}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_reference=true,
        allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local rack,slot=rack_for(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=8,'transaction requires one to 8 changes')
    local result={kind='pod',id=request.id,rack=rack.name,target_path=request.target.path,
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,changes={}}
    for index,item in ipairs(items)do result.changes[index]=validate_change(rack,slot,request.target,item,request)end
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
-- The replacement must still be the reviewed entity with its typed pickup component.
local function prove_pickup(catalog,pickup)
    local candidate=find_candidate(catalog,pickup.resource,pickup.entityRow)
    local component=pickup.component
    if component.name=='BackpackComponentData'then
        assert(candidate.ownership.BackpackComponentData,pickup.name..' no longer owns a backpack component')
        return
    end
    local record=catalog.record(candidate,'InteractableComponentData')
    assert(record.identity.recordIndex==component.recordIndex,pickup.name..' interactable ownership changed')
    local kinds={}
    for zone=0,7 do if b.u32(record.bytes,8+zone*136)~=0 then kinds[b.u32(record.bytes,8+zone*136+40)]=true end end
    for _,name in ipairs(component.interactTypes)do
        assert(kinds[INTERACT[name]],pickup.name..' no longer offers the '..name..' interaction')
    end
end
function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local roots=discover.locate(runtime,reader,profile,{entity=true})
    local catalog=entities.capture(reader,roots.entity,profile,component_names)
    local records=Stratagem.capture_all(runtime,reader,profile)
    local results={}
    for index,spec in ipairs(specs)do
        local rack=assert(database.racks[spec.rack],'reviewed pod rack absent')
        -- Every consumer stratagem still delivers this rack as its primary payload.
        for _,consumer in ipairs(rack.consumers)do
            local found
            for _,record in ipairs(records)do if record.id==consumer.id then
                assert(not found,'consumer stratagem ambiguous: '..consumer.name);found=record end end
            assert(found,'consumer stratagem absent: '..consumer.name)
            assert(found.payloads[1]==rack.resource,consumer.name..' no longer delivers '..rack.name)
        end
        local candidate=find_candidate(catalog,rack.resource)
        local record=catalog.record(candidate,'HellpodRackComponentData')
        assert(record.identity.recordIndex==rack.recordIndex and record.identity.indexRow==rack.indexRow
            and record.identity.ownerCount==rack.ownerCount,'pod rack ownership changed')
        assert(b.u32(record.bytes,RANDOM_OFFSET)==0,rack.name..' now draws random payloads')
        for _,change in ipairs(spec.changes)do
            if change.slot then
                assert(b.u32(record.bytes,change.slot.index*SLOT_STRIDE+8)~=0,rack.name..' slot has no attach node')
            end
            if change.replacement then prove_pickup(catalog,change.replacement)end
        end
        results[index]={rack=rack,record=record}
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots};local seen={}
    local record=resolved.record
    for _,change in ipairs(spec.changes)do
        assert(change.offset+change.width<=#record.bytes,'field outside reviewed record')
        assert(not seen[change.offset],'transaction writes one slot twice');seen[change.offset]=true
        local current=record.bytes:sub(change.offset+1,change.offset+change.width)
        ownership.expected(change,current)
        -- Rack records are 4-byte aligned, so an 8-byte slot reference is written as two aligned
        -- dwords in the same atomic transaction (a u64 may straddle a page).
        for at=0,change.width-4,4 do
            local part_current=current:sub(at+1,at+4)
            local part={expected=change.expected:sub(at+1,at+4),desired=change.desired:sub(at+1,at+4),field=change.field}
            plan.changes[#plan.changes+1]={label=change.field,canonical_field=change.canonical_field,
                semantic_aliases={change.field},owner=record.owner,offset=record.offset+change.offset+at,
                field_offset=change.offset+at,expected=ownership.expected(part,part_current),desired=part.desired,
                before=part_current,already_desired=part_current==part.desired,expect=change.expect,value=change.value,
                identity={component='HellpodRackComponentData',component_type='semantic',
                    record_index=resolved.rack.recordIndex,unique_owner=not resolved.rack.shared,
                    owner_count=#resolved.rack.consumers,scope=resolved.rack.semanticId},chain={}}
        end
    end
    return plan
end
return M
