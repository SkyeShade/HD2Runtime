-- Guarded magazine-attachment authoring. An attachment's ammo values live in the
-- entity delta keyed by its AddPath (patches onto WeaponMagazineComponentData).
-- Every write re-proves the complete delta chain inside the live, uniquely owned
-- delta allocation before touching the reviewed data bytes.
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/attachment_authoring')
local M={}
local MAGAZINE_COMPONENT=5

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
local function validate_change(entry,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=assert(entry.fields[item.field],'field is not exposed for '..entry.name..': '..tostring(item.field))
    assert(request.allow_shared==true,
        'magazine attachments apply to every weapon that equips them; allow_shared=true is required')
    assert(request.allow_unverified_effect==true,
        'magazine attachment writes require allow_unverified_effect=true (re-application is not gameplay-proven)')
    for _,value in ipairs({item.expect,item.value})do
        assert(type(value)=='number'and value%1==0 and value>=0 and value<=4294967295,
            'magazine attachment values must be non-negative integers')
    end
    assert(item.expect==field.currentDefault,'expect differs from reviewed current value for '..item.field)
    return {field=item.field,canonical_field=item.field,descriptor=field,
        expected=b.encode(item.expect,'u32'),desired=b.encode(item.value,'u32'),expect=item.expect,value=item.value}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local entry=entry_for(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=4,'transaction requires one to four changes')
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

-- Re-prove the delta chain for one attachment; returns reviewed data offsets by field.
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
    local found
    for i=0,count-1 do
        if b.u32(components,i*12)==MAGAZINE_COMPONENT then
            assert(not found,'magazine component patched twice');found=i
        end
    end
    assert(found,'attachment delta no longer patches WeaponMagazineComponentData')
    local first_delta,deltas=b.u32(components,found*12+4),b.u32(components,found*12+8)
    assert(deltas>0 and deltas<=64 and first_delta+deltas<=d.delta_count,'attachment delta bounds')
    local rows=reader.read(region,base+d.delta_offset+first_delta*12,deltas*12,true)
    local offsets={}
    for i=0,deltas-1 do
        local offset,size,raw=b.u32(rows,i*12),b.u32(rows,i*12+4),b.u32(rows,i*12+8)
        assert(raw+size<=d.data_count,'attachment delta data bounds')
        if size==4 then offsets[offset]=base+d.data_offset+raw end
    end
    return offsets
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
        for _,change in ipairs(spec.changes)do
            local field=change.descriptor
            assert(offsets[field.componentOffset]==field.dataOffset,
                'reviewed attachment delta data offset changed: '..change.field)
        end
        results[index]={entry=entry,region=region}
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots}
    for _,change in ipairs(spec.changes)do
        local field=change.descriptor
        local current=reader.read(resolved.region,field.dataOffset,4,true)
        assert(current==change.expected or current==change.desired,
            'CONFLICT: '..change.field..' is neither expected nor desired')
        plan.changes[#plan.changes+1]={label=change.field,canonical_field=change.field,
            semantic_aliases={change.field},owner=resolved.region,offset=field.dataOffset,
            field_offset=field.componentOffset,packed=true,expected=change.expected,desired=change.desired,
            before=current,already_desired=current==change.desired,expect=change.expect,value=change.value,
            identity={component='EntityDelta:WeaponMagazineComponentData',component_type='semantic',
                record_index=resolved.entry.settingsIndex,unique_owner=false,owner_count=0,
                scope=field.operationGroup},chain={}}
    end
    return plan
end
return M
