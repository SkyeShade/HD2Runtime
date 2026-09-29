-- Guarded magazine-attachment authoring. An attachment's effects live in the entity delta
-- keyed by its AddPath: ammo values patch WeaponMagazineComponentData, reload duration patches
-- WeaponReloadComponentData, and its ergonomics is an Add_Ergonomics stat modifier patched onto
-- WeaponDataComponentData. Every write re-proves the complete delta chain inside the live,
-- uniquely owned delta allocation before touching the reviewed data bytes.
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/attachment_authoring')
local M={}
local MAX_CHANGES=6

local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64
        and not value:find('[^%w_%-]'),'invalid operation id')
end
local function entry_for(target)
    assert(type(target)=='table'and target.resource=='weapon_attachment','unsupported attachment target')
    assert(target.path=='magazine','unsupported attachment target path')
    for key in pairs(target)do assert(key=='resource'or key=='attachment'or key=='path',
        'unsupported attachment target identity')end
    return assert(type(target.attachment)=='string'and database.attachments[target.attachment],
        'unknown reviewed magazine attachment: '..tostring(target.attachment))
end
local function same(a,c,storage)
    if storage=='f32'then return math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function validate_value(field,value,label)
    assert(type(value)=='number'and value==value and value>-math.huge and value<math.huge,
        label..' must be a finite number')
    if field.storage=='u32'then
        assert(value%1==0 and value>=0 and value<=4294967295,'magazine attachment ammo values must be non-negative integers')
    end
    if field.min then assert(value>=field.min,label..' is below the reviewed minimum '..field.min)end
    if field.max then assert(value<=field.max,label..' is above the reviewed maximum '..field.max)end
end
local function validate_change(entry,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=assert(entry.fields[item.field],'field is not exposed for '..entry.name..': '..tostring(item.field))
    assert(field.editable~=false,'field is read-only: '..item.field..' ('..tostring(field.reason)..')')
    assert(request.allow_shared==true,
        'magazine attachments apply to every weapon that equips them; allow_shared=true is required')
    assert(request.allow_unverified_effect==true,
        'magazine attachment writes require allow_unverified_effect=true (re-application is not gameplay-proven)')
    validate_value(field,item.expect,'expect');validate_value(field,item.value,'value')
    assert(same(item.expect,field.currentDefault,field.storage),'expect differs from reviewed current value for '..item.field)
    return {field=item.field,canonical_field=item.field,descriptor=field,
        expected=b.encode(field.currentDefault,field.storage),desired=b.encode(item.value,field.storage),
        expect=item.expect,value=item.value}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local entry=entry_for(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=MAX_CHANGES,
        'transaction requires one to '..MAX_CHANGES..' changes')
    local result={kind='attachment',id=request.id,attachment=entry.semanticId,target_path='magazine',
        diagnostic=request.diagnostic==true,allow_shared=true,changes={}}
    local seen={}
    for index,item in ipairs(items)do
        local change=validate_change(entry,item,request)
        assert(not seen[item.field],'duplicate attachment field: '..item.field);seen[item.field]=true
        result.changes[index]=change
    end
    result.field=request.field;result.expect=request.expect;result.value=request.value
    return result
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

-- Re-prove the delta chain for one attachment; returns reviewed 4-byte data offsets by
-- component and component offset.
local function prove(reader,region,entry)
    local d=profile.entity_deltas
    local base=d.header_offset
    local header=reader.read(region,base,80,true)
    for index,name in ipairs({'hashmap','settings','component','delta','data'})do
        local pointer=b.pointer(header,(index-1)*16)
        assert(pointer==region.base+base+d[name..'_offset'],'entity delta '..name..' relocation changed')
        assert(b.pointer(header,(index-1)*16+8)==d[name..'_count'],'entity delta '..name..' count changed')
    end
    local row=reader.read(region,base+d.hashmap_offset+entry.hashmapSlot*16,16,true)
    assert(b.resource(row,0)==entry.resource and b.u32(row,8)==entry.settingsIndex,
        'attachment delta ownership changed')
    local settings=reader.read(region,base+d.settings_offset+entry.settingsIndex*8,8,true)
    local count,first=b.u32(settings,0),b.u32(settings,4)
    assert(count>0 and count<=64 and first+count<=d.component_count,'attachment delta settings bounds')
    local components=reader.read(region,base+d.component_offset+first*12,count*12,true)
    local offsets={}
    for i=0,count-1 do
        local component=b.u32(components,i*12)
        assert(not offsets[component],'attachment delta patches a component twice')
        local first_delta,deltas=b.u32(components,i*12+4),b.u32(components,i*12+8)
        assert(deltas>0 and deltas<=64 and first_delta+deltas<=d.delta_count,'attachment delta bounds')
        local rows=reader.read(region,base+d.delta_offset+first_delta*12,deltas*12,true)
        local by_offset={}
        for k=0,deltas-1 do
            local offset,size,raw=b.u32(rows,k*12),b.u32(rows,k*12+4),b.u32(rows,k*12+8)
            assert(raw+size<=d.data_count,'attachment delta data bounds')
            if size==4 then by_offset[offset]=base+d.data_offset+raw end
        end
        offsets[component]=by_offset
    end
    return offsets
end
-- Also used by player-weapon ammunition sources (domains/player_weapon_writes), whose entries carry the same
-- resource, hashmapSlot and settingsIndex.
M.prove=prove
local function check_field(reader,region,offsets,field,label)
    local rows=assert(offsets[field.component],'attachment delta no longer patches the reviewed component: '..label)
    assert(rows[field.componentOffset]==field.dataOffset,'reviewed attachment delta data offset changed: '..label)
    if field.guard then
        assert(rows[field.guard.componentOffset]==field.guard.dataOffset,'attachment stat modifier layout changed: '..label)
        local kind=reader.read(region,field.guard.dataOffset,4,true)
        assert(b.u32(kind,0)==field.guard.u32,'attachment stat modifier is no longer Add_Ergonomics: '..label)
    end
end
function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local roots=discover.locate(runtime,reader,profile,{entity_deltas=true})
    local region=roots.entity_deltas
    local results={}
    for index,spec in ipairs(specs)do
        local entry=assert(database.attachments[spec.attachment])
        reader.stage='domains/attachment_writes:delta_chain'
        local offsets=prove(reader,region,entry)
        for _,change in ipairs(spec.changes)do check_field(reader,region,offsets,change.descriptor,change.field)end
        results[index]={entry=entry,region=region}
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

local COMPONENT_NAMES={[5]='WeaponMagazineComponentData',[113]='WeaponReloadComponentData',
    [236]='WeaponDataComponentData'}
function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots}
    for _,change in ipairs(spec.changes)do
        local field=change.descriptor
        local current=reader.read(resolved.region,field.dataOffset,4,true)
        local expected=ownership.expected(change,current)
        plan.changes[#plan.changes+1]={label=change.field,canonical_field=change.field,
            semantic_aliases={change.field},owner=resolved.region,offset=field.dataOffset,
            field_offset=field.componentOffset,packed=true,expected=expected,desired=change.desired,
            before=current,already_desired=current==change.desired,expect=change.expect,value=change.value,
            identity={component='EntityDelta:'..assert(COMPONENT_NAMES[field.component]),component_type='semantic',
                record_index=resolved.entry.settingsIndex,unique_owner=false,owner_count=0,
                scope=field.operationGroup},chain={}}
    end
    return plan
end
return M
