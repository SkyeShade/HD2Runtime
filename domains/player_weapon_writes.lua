-- Reviewed semantic player-weapon writes. Runtime addresses never enter this database or public API.
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/player_weapon_authoring')
local M={}
local component_names={'ProjectileWeaponComponentData','WeaponDataComponentData',
    'WeaponMagazineComponentData','WeaponRoundsComponentData','ArcWeaponComponentData',
    'MeleeWeaponComponentData','BeamWeaponComponentData','SprayWeaponComponentData'}

local function equal(a,c,kind)
    if kind=='f32'then return type(a)=='number'and type(c)=='number'
        and math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function target_name(target)
    assert(type(target)=='table'and target.resource=='player_weapon'and target.path=='weapon'
        and type(target.weapon)=='string','unsupported player weapon target')
    for key in pairs(target)do assert(key=='resource'or key=='path'or key=='weapon',
        'unsupported player weapon target identity')end
    return target.weapon
end
local function field_for(weapon,id)
    for _,field in ipairs(weapon.fields)do if field.semanticFieldId==id then return field end end
    error('field is not exposed for '..weapon.name..': '..tostring(id),0)
end
local function scalar(field,value,label)
    if field.type=='boolean'then assert(type(value)=='boolean',label..' must be boolean');return value and 1 or 0 end
    assert(type(value)=='number'and value==value and value>-math.huge and value<math.huge,
        label..' must be finite number')
    if field.type=='integer'then assert(value%1==0,label..' must be integer')end
    return value
end
local function validate_change(weapon,item,allow_shared)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=field_for(weapon,item.field)
    assert(field.editable and field.backing,'field is read-only: '..item.field..' ('..tostring(field.reason)..')')
    assert(not field.affectsMultipleWeapons or allow_shared,
        'shared field requires allow_shared=true: '..item.field)
    local expected=scalar(field,item.expect,'expect');local desired=scalar(field,item.value,'value')
    local storage=field.backing.storage
    local canonical=field.type=='boolean'and(field.currentDefault and 1 or 0)or field.currentDefault
    assert(equal(expected,canonical,storage),'expect differs from reviewed current value for '..item.field)
    return {field=item.field,descriptor=field,expect=item.expect,value=item.value,
        expected=b.encode(expected,storage),desired=b.encode(desired,storage)}
end
local function id(value)
    assert(type(value)=='string'and#value>0 and#value<=64 and not value:find('[^%w_%-]'),'invalid operation id')
end

function M.validate_patch(request)
    assert(type(request)=='table','patch requires a descriptor')
    local allowed={id=true,target=true,field=true,expect=true,value=true,diagnostic=true,allow_shared=true}
    for key in pairs(request)do assert(allowed[key],'unsupported patch option: '..tostring(key))end
    id(request.id);local name=target_name(request.target);local weapon=assert(database.weapons[name],'unknown player weapon')
    assert(not weapon.ordinaryWritesBlocked,weapon.blockReason)
    local change=validate_change(weapon,{field=request.field,expect=request.expect,value=request.value},
        request.allow_shared==true)
    return {kind='player_weapon',id=request.id,weapon=name,resource=weapon.resources[1],
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,
        field=request.field,expect=request.expect,value=request.value,changes={change}}
end
function M.validate_transaction(request)
    assert(type(request)=='table','transaction requires a descriptor')
    local allowed={id=true,target=true,changes=true,diagnostic=true,allow_shared=true}
    for key in pairs(request)do assert(allowed[key],'unsupported transaction option: '..tostring(key))end
    id(request.id);local name=target_name(request.target);local weapon=assert(database.weapons[name],'unknown player weapon')
    assert(not weapon.ordinaryWritesBlocked,weapon.blockReason)
    assert(type(request.changes)=='table'and#request.changes>=1 and#request.changes<=32,
        'transaction requires one to 32 changes')
    local result={kind='player_weapon',id=request.id,weapon=name,resource=weapon.resources[1],
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,changes={}}
    local seen={}
    for index,item in ipairs(request.changes)do
        assert(not seen[item.field],'duplicate transaction field: '..tostring(item.field));seen[item.field]=true
        result.changes[index]=validate_change(weapon,item,result.allow_shared)
    end
    return result
end

local function find_candidate(catalog,resource)
    local found
    for _,candidate in ipairs(catalog.candidates)do
        if candidate.resourceHash==resource then assert(not found,'duplicate resource candidate');found=candidate end
    end
    assert(found and found.entityRow and#found.diagnostics==0,'weapon resource ownership unresolved')
    return found
end

function M.capture(runtime,reader,spec)
    reader.stage='runtime/windows_readonly:fingerprint'
    local exe,dll=runtime.module(nil),runtime.module('game.dll')
    if not exe or not dll then error('TARGET_UNAVAILABLE: game modules not ready',0)end
    assert(runtime.module_hash(exe)==profile.exe_sha and runtime.module_hash(dll)==profile.dll_sha,
        'unsupported build fingerprint')
    local needed={entity=true}
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        if backing.kind=='settings'then needed[backing.settings]=true end
        if backing.settings=='damage'then
            needed.projectile=true;needed.arc='optional';needed.beam='optional'
        end
    end
    local roots=discover.locate(runtime,reader,profile,needed)
    local catalog=entities.capture(reader,roots.entity,profile,component_names)
    return {roots=roots,catalog=catalog,candidate=find_candidate(catalog,spec.resource)}
end

local function component_record(resolved,backing)
    local record=resolved.catalog.record(resolved.candidate,backing.component)
    local identity=record.identity
    assert(identity.recordIndex==backing.recordIndex and identity.indexRow==backing.indexRow
        and identity.ownerCount==backing.ownerCount,'component ownership identity changed')
    return record
end
local function linked(resolved,kind,branch)
    local ownership=resolved.candidate.ownership
    if kind=='projectile'or kind=='damage'then
        local projectile_type
        if ownership.WeaponRoundsComponentData then
            local rounds=resolved.catalog.record(resolved.candidate,'WeaponRoundsComponentData')
            projectile_type=b.u32(rounds.bytes,branch=='alternate'and 68 or 64)
        elseif ownership.ProjectileWeaponComponentData then
            local weapon=resolved.catalog.record(resolved.candidate,'ProjectileWeaponComponentData')
            projectile_type=b.u32(weapon.bytes,0)
        end
        if projectile_type and projectile_type~=0 then
            local projectile=assert(resolved.roots.projectile.records[projectile_type],
                'linked ProjectileSettings absent')
            if kind=='projectile'then return projectile,resolved.roots.projectile.owner end
            local damage_type=b.u32(projectile.bytes,60)
            return assert(resolved.roots.damage.records[damage_type],'linked DamageInfo absent'),resolved.roots.damage.owner
        end
    end
    if kind=='arc'or(kind=='damage'and ownership.ArcWeaponComponentData)then
        local component=resolved.catalog.record(resolved.candidate,'ArcWeaponComponentData')
        local record=assert(resolved.roots.arc.records[b.u32(component.bytes,0)],'linked ArcSettings absent')
        if kind=='arc'then return record,resolved.roots.arc.owner end
        return assert(resolved.roots.damage.records[b.u32(record.bytes,36)],'linked arc DamageInfo absent'),resolved.roots.damage.owner
    end
    if kind=='beam'or(kind=='damage'and ownership.BeamWeaponComponentData)then
        local component=resolved.catalog.record(resolved.candidate,'BeamWeaponComponentData')
        local record=assert(resolved.roots.beam.records[b.u32(component.bytes,0)],'linked BeamSettings absent')
        if kind=='beam'then return record,resolved.roots.beam.owner end
        return assert(resolved.roots.damage.records[b.u32(record.bytes,12)],'linked beam DamageInfo absent'),resolved.roots.damage.owner
    end
    if kind=='damage'and ownership.SprayWeaponComponentData then
        local component=resolved.catalog.record(resolved.candidate,'SprayWeaponComponentData')
        return assert(resolved.roots.damage.records[b.u32(component.bytes,200)],'linked spray DamageInfo absent'),resolved.roots.damage.owner
    end
    if kind=='damage'and ownership.MeleeWeaponComponentData then
        local component=resolved.catalog.record(resolved.candidate,'MeleeWeaponComponentData')
        return assert(resolved.roots.damage.records[b.u32(component.bytes,12)],'linked melee DamageInfo absent'),resolved.roots.damage.owner
    end
    error('reviewed settings linkage unavailable: '..kind,0)
end

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots}
    for index,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing;local record,owner
        if backing.kind=='component'then record=component_record(resolved,backing);owner=record.owner
        else
            record,owner=linked(resolved,backing.settings,backing.branch)
            assert(record.group==backing.group and record.row==backing.row
                and record.kind==backing.recordType and record.settings_type==backing.settingsType,
                'settings record identity changed')
        end
        assert(backing.offset+backing.width<=#record.bytes,'field outside reviewed record')
        local current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
        assert(current==change.expected or current==change.desired,
            'CONFLICT: '..change.field..' is neither expected nor desired')
        local identity
        if backing.kind=='component'then
            identity={component=backing.component,component_type=record.identity.componentType,
                record_index=record.identity.recordIndex,index_row=record.identity.indexRow,
                unique_owner=record.identity.uniqueOwner,owner_count=record.identity.ownerCount,
                scope=change.descriptor.writeScope}
        else
            identity={component=backing.settings..'Settings',component_type=backing.settingsType,
                record_index=backing.row,group=backing.group,record_kind=backing.recordType,
                unique_owner=not change.descriptor.affectsMultipleWeapons,
                owner_count=#change.descriptor.sharedWithWeapons+1,scope=change.descriptor.writeScope}
        end
        plan.changes[index]={label=change.field,owner=owner,offset=record.offset+backing.offset,
            expected=change.expected,desired=change.desired,before=current,
            already_desired=current==change.desired,identity=identity,chain={identity},
            expect=change.expect,value=change.value}
    end
    return plan
end
return M
