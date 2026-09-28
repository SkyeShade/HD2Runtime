-- Guarded Booster authoring. Boosters own no native record; their fields live on the
-- records the Booster enum links to. Every write re-proves that link live:
--   deployed_entity: StratagemInfo booster entry -> entity delta -> hellpod rack item ->
--                    turret entity with uniquely owned weapon components
--   status_effect:   the reviewed StatusEffectSettings row and its stat-multiplier array
-- No booster edit is gameplay-proven, so allow_unverified_effect is always required.
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/booster_authoring')
local M={}
local component_names={'ProjectileWeaponComponentData','WeaponMagazineComponentData'}

local function equal(a,c,storage)
    if storage=='f32'then return type(a)=='number'and type(c)=='number'
        and math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64
        and not value:find('[^%w_%-]'),'invalid operation id')
end
local function target_for(target)
    assert(type(target)=='table'and target.resource=='booster','unsupported booster target')
    for key in pairs(target)do assert(key=='resource'or key=='booster'or key=='path',
        'unsupported booster target identity')end
    local entry=assert(type(target.booster)=='string'and database.boosters[target.booster],
        'unknown reviewed booster: '..tostring(target.booster))
    assert(target.path~='booster','booster root has no fields; use booster:status_effect() or '
        ..'booster:deployed_entity()')
    local owned=assert(entry.targets[target.path],entry.name..' has no reviewed '..tostring(target.path)..' target')
    return entry,owned
end
local function validate_change(entry,owned,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=assert(owned.fields[item.field],'field is not exposed for '..entry.name..': '..tostring(item.field))
    assert(request.allow_unverified_effect==true,
        'booster writes require allow_unverified_effect=true: '..item.field..' ('..field.acknowledgementReason..')')
    assert(not field.shared or request.allow_shared==true,
        'shared field requires allow_shared=true: '..item.field)
    local storage=field.backing.storage
    for _,value in ipairs({item.expect,item.value})do
        assert(type(value)=='number'and value==value and value>-math.huge and value<math.huge,
            'booster values must be finite numbers')
        if storage=='u32'then assert(value%1==0 and value>=0 and value<=4294967295,
            'integer booster field requires a non-negative integer')end
    end
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
    assert(type(items)=='table'and#items>=1 and#items<=8,'transaction requires one to eight changes')
    local result={kind='booster',id=request.id,booster=entry.name,target_path=request.target.path,
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,changes={}}
    local group;local seen={}
    for index,item in ipairs(items)do
        local change=validate_change(entry,owned,item,request)
        assert(not seen[item.field],'duplicate booster field: '..tostring(item.field));seen[item.field]=true
        group=group or change.descriptor.operationGroup
        assert(group==change.descriptor.operationGroup,'transaction spans multiple backing objects; use hd2.plan')
        result.changes[index]=change
    end
    result.field=request.field;result.expect=request.expect;result.value=request.value
    return result
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

-- StratagemInfo booster list entry still names this booster, payload, and delta.
local function prove_stratagem(runtime,reader,chain)
    reader.stage='domains/booster_writes:stratagem_entry'
    local records,region=require('hd2runtime/core/stratagem').capture_all(runtime,reader,profile)
    local record
    for _,item in ipairs(records)do
        if item.record_kind==chain.stratagemKind then record=item end
    end
    assert(record and record.id==chain.stratagemId,'booster stratagem identity changed')
    local list=reader.read(region,record.offset+280,16,true)
    local pointer,count=b.pointer(list,0),b.pointer(list,8)
    assert(count>chain.entryIndex and pointer>=region.base
        and pointer+count*32<=region.base+profile.stratagem.size,'booster list extent changed')
    local entry=reader.read(region,pointer-region.base+chain.entryIndex*32,32,true)
    assert(b.u32(entry,0)==chain.booster and b.resource(entry,8)==chain.payload
        and b.resource(entry,16)==chain.entityDelta,'stratagem booster entry changed')
end
-- The entity delta keyed by the entry still places the turret in the reviewed rack slot.
local function prove_delta(reader,region,chain,resource)
    reader.stage='domains/booster_writes:entity_delta'
    local d=profile.entity_deltas
    local base=d.header_offset
    local header=reader.read(region,base,80,true)
    for index,name in ipairs({'hashmap','settings','component','delta','data'})do
        assert(b.pointer(header,(index-1)*16)==region.base+base+d[name..'_offset'],
            'entity delta '..name..' relocation changed')
        assert(b.pointer(header,(index-1)*16+8)==d[name..'_count'],'entity delta '..name..' count changed')
    end
    local row=reader.read(region,base+d.hashmap_offset+chain.hashmapSlot*16,16,true)
    assert(b.resource(row,0)==chain.entityDelta and b.u32(row,8)==chain.settingsIndex,
        'booster entity delta ownership changed')
    local settings=reader.read(region,base+d.settings_offset+chain.settingsIndex*8,8,true)
    local count,first=b.u32(settings,0),b.u32(settings,4)
    assert(count>0 and count<=64 and first+count<=d.component_count,'booster delta settings bounds')
    local components=reader.read(region,base+d.component_offset+first*12,count*12,true)
    local found
    for i=0,count-1 do
        if b.u32(components,i*12)==chain.rackComponentIndex then
            assert(not found,'rack component patched twice');found=i
        end
    end
    assert(found,'booster delta no longer patches the hellpod rack')
    local first_delta,deltas=b.u32(components,found*12+4),b.u32(components,found*12+8)
    assert(deltas>0 and deltas<=128 and first_delta+deltas<=d.delta_count,'booster delta bounds')
    local rows=reader.read(region,base+d.delta_offset+first_delta*12,deltas*12,true)
    local located
    for i=0,deltas-1 do
        local offset,size,raw=b.u32(rows,i*12),b.u32(rows,i*12+4),b.u32(rows,i*12+8)
        if offset==chain.rackSlot*64 and size==8 then located=base+d.data_offset+raw end
    end
    assert(located==chain.dataOffset,'booster rack slot delta moved')
    assert(b.resource(reader.read(region,located,8,true),0)==resource,
        'booster delta no longer attaches the reviewed turret')
end
local function find_candidate(catalog,resource,row)
    local found
    for _,candidate in ipairs(catalog.candidates)do if candidate.resourceHash==resource then
        assert(not found,'booster entity identity ambiguous');found=candidate end end
    assert(found and found.entityRow==row and#found.diagnostics==0,'reviewed booster entity absent')
    return found
end
function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local needed={}
    for _,spec in ipairs(specs)do
        if spec.target_path=='deployed_entity'then needed.entity=true;needed.entity_deltas=true
        else needed.status=true end
    end
    local roots=discover.locate(runtime,reader,profile,needed)
    local catalog=needed.entity and entities.capture(reader,roots.entity,profile,component_names)
    local results={}
    for index,spec in ipairs(specs)do
        local entry=assert(database.boosters[spec.booster],'reviewed booster entry absent')
        local owned=assert(entry.targets[spec.target_path],'reviewed booster target absent')
        if spec.target_path=='deployed_entity'then
            prove_stratagem(runtime,reader,owned.chain)
            prove_delta(reader,roots.entity_deltas,owned.chain,owned.resource)
            results[index]={owned=owned,catalog=catalog,candidate=find_candidate(catalog,owned.resource,owned.entityRow)}
        else
            reader.stage='domains/booster_writes:status_row'
            local status=roots.status
            local row=assert(status.records[owned.statusType],'booster status row absent')
            assert(row.group==0 and row.row==owned.row and row.offset==owned.rowOffset,'booster status row moved')
            results[index]={owned=owned,status=status,row=row}
        end
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots};local physical={}
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        local owner,offset,field_offset,current,identity
        if backing.kind=='component'then
            local record=resolved.catalog.record(resolved.candidate,backing.component)
            assert(record.identity.recordIndex==backing.recordIndex and record.identity.indexRow==backing.indexRow
                and record.identity.ownerCount==backing.ownerCount,'booster entity component ownership changed')
            owner,offset,field_offset=record.owner,record.offset+backing.offset,backing.offset
            current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
            identity={component=backing.component,component_type='semantic',record_index=backing.recordIndex,
                unique_owner=backing.uniqueOwner,owner_count=backing.ownerCount,scope=change.descriptor.instanceKey}
        else
            owner=resolved.status.owner
            if backing.kind=='status_multiplier'then
                local row=resolved.row.bytes
                assert(b.pointer(row,104)==owner.base+backing.arrayOffset and b.pointer(row,112)==backing.count,
                    'booster status multiplier array changed')
                -- Uncaptured: discovery already captured the whole status allocation as the
                -- single transaction context for this address.
                local element=reader.read(owner,backing.arrayOffset+backing.index*8,8)
                assert(b.u32(element,0)==backing.stat,'booster status multiplier stat changed')
                offset=backing.arrayOffset+backing.index*8+4;field_offset=offset-resolved.row.offset
                current=element:sub(5,8)
            else
                offset=resolved.row.offset+backing.offset;field_offset=backing.offset
                current=resolved.row.bytes:sub(backing.offset+1,backing.offset+backing.width)
            end
            identity={component='StatusEffectSettings',component_type='semantic',record_index=resolved.row.row,
                unique_owner=false,owner_count=0,scope=change.descriptor.instanceKey}
        end
        assert(current==change.expected or current==change.desired,
            'CONFLICT: '..change.field..' is neither expected nor desired')
        local key=tostring(owner.base)..':'..tostring(offset)
        assert(not physical[key],'overlapping booster fields');physical[key]=true
        plan.changes[#plan.changes+1]={label=change.field,canonical_field=change.canonical_field,
            semantic_aliases={change.field},owner=owner,offset=offset,field_offset=field_offset,
            expected=change.expected,desired=change.desired,before=current,
            already_desired=current==change.desired,expect=change.expect,value=change.value,
            identity=identity,chain={}}
    end
    return plan
end
return M
