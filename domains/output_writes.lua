-- Guarded attack-output presentation: the label and HUD icon a weapon-function mode shows for the projectile it
-- fires. They are the projectile's own ProjectileInfo members (+12 short mode label, a localization string ID; +16
-- icon resource), so the target is the catalogued output that names the projectile (hd2.attack_output(name)). Only
-- native strings and native weapon-function icons are accepted (domains/attack_outputs.lua modeLabels, modeIcons).
-- Every write re-proves that the output's owner entity still fires that projectile (its ProjectileWeapon +0) and the
-- ProjectileSettings row identity before any memory is touched.
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local profile=require('hd2runtime/schemas/current')
local M={}
local component_names={'ProjectileWeaponComponentData'}
local function catalog()return require('hd2runtime/domains/attack_outputs')end

local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64
        and not value:find('[^%w_%-]'),'invalid operation id')
end
local function output_for(target)
    assert(type(target)=='table'and target.resource=='attack_output'and type(target.output)=='string',
        'unsupported attack output target')
    for key in pairs(target)do assert(key=='resource'or key=='output','unsupported attack output target identity')end
    local output=assert(catalog().outputs[target.output],'unknown attack output: '..target.output)
    assert(output.presentationFields,'attack output has no writable presentation (not a selectable projectile '
        ..'output): '..output.id)
    return output
end
-- 8-byte little-endian resource from its 0x... hex identity (IDs exceed double precision).
local function resource_bytes(hex)
    assert(type(hex)=='string'and hex:match('^0x%x+$')and#hex==18,'malformed icon resource')
    local out={}
    for index=17,3,-2 do out[#out+1]=string.char(tonumber(hex:sub(index,index+1),16))end
    return table.concat(out)
end
local function encode(field,value,label,offered_only)
    if field.type=='mode_label'then
        local item=type(value)=='string'and catalog().modeLabels[value]
        assert(item,label..' must be a native mode label (see sdk/AttackOutputCapabilities.json modePresentation)')
        assert(item.offered or not offered_only,label..' '..value..' is not an offered mode label')
        return b.encode(item.nativeId,'u32')
    end
    assert(field.type=='mode_icon','unsupported presentation field type')
    local item=type(value)=='string'and catalog().modeIcons[value]
    assert(not(item and item.auto),label..' auto resolves to a native icon before validation')
    assert(item,label..' must be a native weapon-function icon (see sdk/AttackOutputCapabilities.json modePresentation)')
    assert(item.offered or not offered_only,label..' '..value..' is not an offered icon')
    return resource_bytes(item.resource)
end
-- "auto": the exact native icon of the mode label (written in the same operation, else the current one), or the
-- generic fallback when that label has no native icon. Deterministic; an explicit icon always overrides it.
local function auto_icon(output,items)
    local label=output.presentationFields['presentation.mode_label'].currentDefault
    for _,item in ipairs(items)do if item.field=='presentation.mode_label'then label=item.value end end
    local entry=type(label)=='string'and catalog().modeLabels[label]
    return entry and entry.icon or catalog().modeIcons.auto.generic,entry and entry.iconSource or'generic_fallback'
end
M.auto_icon=auto_icon
local function validate_change(output,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value'or key=='icon_source',
        'unsupported change option: '..tostring(key))end
    local field=output.presentationFields[item.field]
    assert(field,'field is not exposed for attack outputs: '..tostring(item.field))
    assert(field.editable,'field is read-only: '..item.field)
    assert(not field.shared or request.allow_shared==true,'shared field requires allow_shared=true: '..item.field
        ..' (every weapon firing this projectile shows it: '..table.concat(field.sharedConsumers,', ')..')')
    assert(field.acknowledgement~='allow_unverified_effect'or request.allow_unverified_effect==true,
        'field requires allow_unverified_effect=true: '..item.field..' ('..tostring(field.acknowledgementReason)..')')
    assert(item.expect==field.currentDefault,'expect differs from the reviewed '..item.field..' of '..output.id
        ..': declared='..tostring(item.expect)..' reviewed='..tostring(field.currentDefault))
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
        -- The reviewed native value can always be restored; a new value must be an offered one.
        expected=encode(field,item.expect,'expect',false),
        desired=encode(field,item.value,'value',item.value~=field.currentDefault),
        expect=item.expect,value=item.value}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local output=output_for(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=32,'transaction requires one to 32 changes')
    -- "auto" icons resolve on a copy of the changes; the caller's descriptors are never modified.
    local source_items=items;items={}
    for index,item in ipairs(source_items)do
        items[index]=item
        if type(item)=='table'and item.field=='presentation.mode_icon'and item.value=='auto'then
            local resolved={};for key,value in pairs(item)do resolved[key]=value end
            resolved.value,resolved.icon_source=auto_icon(output,source_items)
            items[index]=resolved
        end
    end
    local result={kind='attack_output',id=request.id,output=output.id,diagnostic=request.diagnostic==true,
        allow_shared=request.allow_shared==true,allow_unverified_effect=request.allow_unverified_effect==true,
        changes={}}
    local seen={}
    for index,item in ipairs(items)do
        local change=validate_change(output,item,request)
        assert(not seen[change.canonical_field],'transaction lists '..change.canonical_field..' twice')
        seen[change.canonical_field]=true
        result.changes[index]=change
    end
    result.field=request.field;result.expect=request.expect;result.value=request.value
    return result
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

local function find_candidate(catalog_,output)
    local found
    for _,candidate in ipairs(catalog_.candidates)do if candidate.resourceHash==output.resource then
        assert(not found,'attack output owner identity ambiguous');found=candidate end end
    assert(found and found.entityRow and#found.diagnostics==0,'attack output owner entity absent: '..output.id)
    assert(found.entityRow==output.entityRow,'attack output owner row changed: '..output.id)
    return found
end
function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local roots=discover.locate(runtime,reader,profile,{entity=true,projectile=true})
    local captured=entities.capture(reader,roots.entity,profile,component_names)
    local results={}
    for index,spec in ipairs(specs)do
        local output=assert(catalog().outputs[spec.output],'reviewed attack output absent')
        local candidate=find_candidate(captured,output)
        -- The owner must still fire this projectile: its own ProjectileWeapon record, re-proven.
        local backing=output.backing
        local record=captured.record(candidate,backing.component)
        assert(record.identity.recordIndex==backing.recordIndex and record.identity.indexRow==backing.indexRow,
            'attack output owner '..backing.component..' ownership changed')
        assert(b.u32(record.bytes,backing.offset)==output.currentDefault,
            'CONFLICT: '..output.id..' owner no longer fires the reviewed projectile')
        results[index]={output=output,catalog=captured,candidate=candidate,roots=roots}
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots}
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        local root=assert(resolved.roots.projectile,'projectile settings allocation absent')
        local record=assert(root.records[backing.recordType],'reviewed ProjectileSettings row absent')
        assert(record.kind==backing.recordType and record.group==backing.group and record.row==backing.row
            and record.settings_type==backing.settingsType,'ProjectileSettings identity changed')
        assert(backing.offset+backing.width<=#record.bytes,'field outside reviewed record')
        local current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
        local expected=ownership.expected(change,current)
        -- Written as aligned 4-byte slots (the 8-byte icon as its two halves) in the one guarded transaction, so no
        -- write crosses a page.
        for slot=0,backing.width/4-1 do
            local from,to=slot*4+1,slot*4+4
            plan.changes[#plan.changes+1]={label=change.field..(backing.width>4 and'['..(slot+1)..']'or''),
                canonical_field=change.canonical_field,semantic_aliases={change.field},owner=root.owner,
                offset=record.offset+backing.offset+slot*4,field_offset=backing.offset+slot*4,
                expected=expected:sub(from,to),desired=change.desired:sub(from,to),before=current:sub(from,to),
                already_desired=current:sub(from,to)==change.desired:sub(from,to),expect=change.expect,
                value=change.value,
                identity={component='ProjectileSettings',component_type=backing.settingsType,record_index=backing.row,
                    group=backing.group,record_kind=backing.recordType,unique_owner=not change.descriptor.shared,
                    owner_count=#change.descriptor.sharedConsumers,scope=change.descriptor.operationGroup},
                chain={}}
        end
    end
    return plan
end
return M
