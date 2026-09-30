-- Guarded attack-output presentation: the label and HUD icon a weapon-function mode shows for the projectile it
-- fires. They are the projectile's own ProjectileInfo members (+12 short mode label, a localization string ID; +16
-- icon resource), so the target is the catalogued output that names the projectile (hd2.attack_output(name)). Only
-- native strings and native weapon-function icons are accepted (domains/attack_outputs.lua modeLabels, modeIcons).
-- Every write re-proves that the output's owner entity still fires that projectile (its ProjectileWeapon +0) and the
-- ProjectileSettings row identity before any memory is touched.
--
-- Projectile slots (research/projectile-builder-F5FEE03DCFDB.json): the row's direct-hit damage (+60 DamageInfoType),
-- impact explosion (+144) and expiry explosion (+156) re-point to another catalogued output's reference
-- (hd2.attack_output(donor):direct_damage() / :impact_explosion() / :expiry_explosion()), or "none" for an explosion.
-- The donor row is only referenced and re-proven live; the written row changes for every weapon that fires it.
-- A spare twin output has no owner entity: it is proven by its settings identity and by being, live, byte-identical to
-- its twin's row except its references and presentation (so the twin's package covers its assets).
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
local SLOT_KEYS={['projectile.direct_damage']='directDamage',['projectile.impact_explosion']='impactExplosion',
    ['projectile.expiry_explosion']='expiryExplosion'}
local SLOT_FIELDS={directDamage='projectile.direct_damage',impactExplosion='projectile.impact_explosion',
    expiryExplosion='projectile.expiry_explosion'}
-- A slot value: "none" (explosion slots only) or a slot handle {resource='attack_output_slot', output, slot}.
local function slot_selector(field,value,label)
    if value=='none'then
        assert(field.allowNone,label..': the direct-hit damage cannot be removed');return {none=true,type=0}
    end
    assert(type(value)=='table'and value.resource=='attack_output_slot'and type(value.output)=='string'
        and SLOT_FIELDS[value.slot],label..' must be "none" or hd2.attack_output(name):direct_damage() / '
        ..':impact_explosion() / :expiry_explosion()')
    for key in pairs(value)do assert(key=='resource'or key=='output'or key=='slot',label..' has an unsupported identity')end
    local donor=assert(catalog().outputs[value.output],'unknown attack output: '..value.output)
    local donor_field=assert(donor.slotFields and donor.slotFields[SLOT_FIELDS[value.slot]],
        'attack output has no projectile slots: '..donor.id)
    assert((donor_field.type=='damage_slot')==(field.type=='damage_slot'),
        label..': a damage slot takes a direct_damage() handle, an explosion slot an explosion handle')
    assert(donor_field.currentDefault~=0,label..': '..donor.id..' has no '..value.slot..' to reference')
    return {donor=donor,donor_field=donor_field,slot=value.slot,type=donor_field.currentDefault}
end
-- The package a donor reference needs: the donor's owner package (a spare twin: its twin owner's). A donor without a
-- catalogued package is refused: its explosion or damage assets could not be loaded before the reference is written.
local function donor_dependency(target,donor)
    if donor.id==target.id then return nil end
    local owner=donor.dependencyOwner or donor.owner
    local assets=require('hd2runtime/core/assets')
    local dependency
    if owner.kind=='player_weapon'or owner.kind=='support_weapon'then
        dependency=assets.dependency('player_weapon/'..owner.name)or assets.dependency('support_weapon/'..owner.name)
    elseif donor.dependencyKey then
        dependency=assets.dependency(donor.dependencyKey)
    end
    return assert(dependency,'ASSET_UNAVAILABLE: no catalogued package for attack output '..donor.id
        ..' (its assets could not be loaded before the reference is written)')
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
-- A spare twin is proven unreferenced on the build it was researched on only; anywhere else it is refused.
local function require_spare_build(output)
    if output.spare then
        assert(output.spare.researchedBuild==profile.exe_sha,'SPARE_TWIN_UNVERIFIED_BUILD: '..output.id..' was proven '
            ..'unreferenced on another game build; re-run scripts/research_projectile_builder.py for this one')
    end
end
M.require_spare_build=require_spare_build
local function live_proven(field,value)
    for _,proven in ipairs(field.liveProvenValues or{})do if proven==value then return true end end
    return false
end
local function validate_change(output,item,request)
    assert(type(item)=='table','change must be a descriptor')
    require_spare_build(output)
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value'or key=='icon_source',
        'unsupported change option: '..tostring(key))end
    local field=output.presentationFields[item.field]or(output.slotFields or{})[item.field]
    assert(field,'field is not exposed for attack outputs: '..tostring(item.field))
    if SLOT_KEYS[item.field]then
        assert(field.editable,'field is read-only: '..item.field)
        assert(not field.shared or request.allow_shared==true,'shared field requires allow_shared=true: '..item.field
            ..' (every weapon firing this projectile changes: '..#field.sharedConsumers..' consumers)')
        local expected,desired=slot_selector(field,item.expect,'expect'),slot_selector(field,item.value,'value')
        -- Exact (row, slot, donor) tuples a live test proved need no acknowledgement (liveProvenValues: "none" or
        -- "<donor output id>#<slot>").
        local key=desired.none and'none'or desired.donor.id..'#'..desired.slot
        assert(request.allow_unverified_effect==true or live_proven(field,key),'field requires '
            ..'allow_unverified_effect=true: '..item.field..' ('..tostring(field.acknowledgementReason)..')')
        assert(expected.type==field.currentDefault and(expected.none or expected.donor.id==output.id
            and expected.slot==SLOT_KEYS[item.field]),'expect must be this output\'s own '..item.field
            ..' handle (hd2.attack_output(name):'..({directDamage='direct_damage',impactExplosion='impact_explosion',
            expiryExplosion='expiry_explosion'})[SLOT_KEYS[item.field]]..'()) or "none" where it has none')
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,slot=true,
            expected=b.encode(expected.type,'u32'),desired=b.encode(desired.type,'u32'),donor=desired.donor,
            donor_field=desired.donor_field,expect=item.expect,value=item.value,
            asset_dependency=desired.donor and donor_dependency(output,desired.donor)or nil}
    end
    assert(field.editable,'field is read-only: '..item.field)
    assert(not field.shared or request.allow_shared==true,'shared field requires allow_shared=true: '..item.field
        ..' (every weapon firing this projectile shows it: '..table.concat(field.sharedConsumers,', ')..')')
    -- A live-proven label or icon (the resolved icon when "auto" was asked) needs no acknowledgement.
    assert(field.acknowledgement~='allow_unverified_effect'or request.allow_unverified_effect==true
        or live_proven(field,item.value),
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
    local slots=false
    for _,spec in ipairs(specs)do for _,change in ipairs(spec.changes or{})do slots=slots or change.slot==true end end
    -- Slot writes also read the live explosion table (the recursion guard follows its submunitions).
    local roots=discover.locate(runtime,reader,profile,{entity=true,projectile=true,explosion=slots or nil})
    local captured=entities.capture(reader,roots.entity,profile,component_names)
    local results={}
    for index,spec in ipairs(specs)do
        local output=assert(catalog().outputs[spec.output],'reviewed attack output absent')
        local candidate,owner_fires
        if output.spare then
            -- A spare twin has no owner entity; prepare re-proves its row against its twin's.
        else
            candidate=find_candidate(captured,output)
            -- The owner entity and its ProjectileWeapon record are re-proven. What the owner fires right now is not a
            -- condition: these writes target the projectile row itself, whose identity prepare re-proves, and the
            -- owner may legitimately fire a donor another operation gave it (a Patriot minigun swapped to EAT-17
            -- keeps its own bullet row, which the Gatling Sentry still fires).
            local backing=output.backing
            local record=captured.record(candidate,backing.component)
            assert(record.identity.recordIndex==backing.recordIndex and record.identity.indexRow==backing.indexRow,
                'attack output owner '..backing.component..' ownership changed')
            owner_fires=b.u32(record.bytes,backing.offset)==output.currentDefault
        end
        results[index]={output=output,catalog=captured,candidate=candidate,roots=roots,owner_fires=owner_fires}
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

local function settings_row(root,settings,label)
    local record=assert(root.records[settings.recordType],label..' ProjectileSettings row absent')
    assert(record.kind==settings.recordType and record.group==settings.group and record.row==settings.row
        and record.settings_type==settings.settingsType,label..' ProjectileSettings identity changed')
    return record
end
-- The live rows, byte for byte, outside the members a spare twin may differ in (its key, presentation, references).
local function masked(bytes,excluded)
    local out=bytes
    for _,range in ipairs(excluded)do out=out:sub(1,range[1])..string.rep('\0',range[2]-range[1])..out:sub(range[2]+1)end
    return out
end
-- A composition must never make a projectile spawn itself: from the written explosion, follow each explosion's
-- submunition projectile (+84) and that projectile's impact and expiry explosions (+144, +156), read live, and refuse
-- the write if the chain reaches the written row (an endless spawn loop). The chain is bounded.
local SUBMUNITION,IMPACT,EXPIRY=84,144,156
local function assert_no_recursion(resolved,row_type,explosion_type,label)
    local explosions=assert(resolved.roots.explosion,'explosion settings allocation absent')
    local projectiles=resolved.roots.projectile
    local seen,queue,steps={},{explosion_type},0
    while #queue>0 do
        local current=table.remove(queue)
        if current~=0 and not seen[current]then
            seen[current]=true;steps=steps+1
            assert(steps<=64,'RECURSIVE_COMPOSITION: '..label..': the explosion chain is longer than reviewed')
            local row=assert(explosions.records[current],label..': explosion '..current..' has no live row')
            local submunition=b.u32(row.bytes,SUBMUNITION)
            if submunition~=0 then
                assert(submunition~=row_type,'RECURSIVE_COMPOSITION: '..label..' would make the projectile spawn '
                    ..'itself (its explosion releases the same projectile as a submunition)')
                local projectile=projectiles.records[submunition]
                if projectile then
                    queue[#queue+1]=b.u32(projectile.bytes,IMPACT);queue[#queue+1]=b.u32(projectile.bytes,EXPIRY)
                end
            end
        end
    end
end
function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots}
    local output=resolved.output
    -- Slot and label writes edit this row, never a host. While the owner fires another row (another operation swapped
    -- its projectile) the edit does not reach the owner. Not a refusal (the row identity is re-proven below): the log
    -- says so once per application.
    if resolved.owner_fires==false then
        local owner=output.owner.name
        plan.notes={'note: '..spec.id..' edits the '..owner..' projectile row, but '..owner..' currently fires '
            ..'another projectile (a swap), so the edit does not reach it until it fires its own row again; every '
            ..'other entity that fires this row still shows it. Slot and label writes edit a row and do not follow a '
            ..'swapped projectile.'}
    end
    local root=assert(resolved.roots.projectile,'projectile settings allocation absent')
    if output.spare then
        local own=settings_row(root,output.referenceSettings,output.id)
        local twin=settings_row(root,output.spare.twinSettings,output.spare.twinOf)
        assert(masked(own.bytes,output.spare.excluded)==masked(twin.bytes,output.spare.excluded),
            'SPARE_TWIN_CHANGED: '..output.id..' is no longer byte-identical to '..output.spare.twinOf
            ..' outside its references (its assets are no longer covered by the twin package)')
    end
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        local record=assert(root.records[backing.recordType],'reviewed ProjectileSettings row absent')
        assert(record.kind==backing.recordType and record.group==backing.group and record.row==backing.row
            and record.settings_type==backing.settingsType,'ProjectileSettings identity changed')
        if change.donor and change.donor.id~=output.id then
            -- The donor row still holds the reviewed reference (it is only read, never written).
            local donor=settings_row(root,change.donor.referenceSettings,change.donor.id)
            assert(b.u32(donor.bytes,change.donor_field.backing.offset)==change.donor_field.currentDefault,
                'CONFLICT: '..change.donor.id..' '..change.donor_field.semanticFieldId..' changed')
        end
        if change.slot and change.descriptor.type=='explosion_slot'then
            local desired=b.u32(change.desired,0)
            if desired~=0 then assert_no_recursion(resolved,backing.recordType,desired,change.field)end
        end
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
