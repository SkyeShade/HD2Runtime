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
    assert(type(target)=='table'and target.resource=='player_weapon'
        and type(target.weapon)=='string','unsupported player weapon target')
    if target.path=='weapon'then
        for key in pairs(target)do assert(key=='resource'or key=='path'or key=='weapon',
            'unsupported player weapon target identity')end
        return target.weapon,nil,'weapon',nil
    end
    assert((target.path=='attack'or target.path=='terminal_action'or target.path=='explosion')
        and type(target.attack)=='string','unsupported player weapon target')
    if target.path=='terminal_action'or target.path=='explosion'then
        assert(target.phase=='impact'or target.phase=='expiry','unsupported terminal action phase')
    end
    for key in pairs(target)do assert(key=='resource'or key=='path'or key=='weapon'or key=='attack'
        or key=='phase','unsupported player weapon target identity')end
    return target.weapon,target.attack,target.path,target.phase
end
local function canonical_explosion_phase(weapon,role,phase)
    local graph=assert(require('hd2runtime/domains/player_weapon_composition').weapons[weapon.name])
    local attack=assert(graph.attacks[role]);local action=assert(attack.terminal_actions[phase])
    for _,candidate in ipairs({'impact','expiry'})do
        local other=attack.terminal_actions[candidate]
        if other and other.reference_type==action.reference_type then return candidate end
    end
    return phase
end
local function field_for(weapon,id,role,path,phase)
    local resolved=id
    if id=='attack.projectile'then
        assert(type(role)=='string','attack.projectile requires weapon:attack(role) target')
        resolved='attack.'..role..'.projectile'
    elseif id=='terminal.explosion'then
        resolved='terminal.'..role..'.'..phase..'.explosion'
    elseif path=='explosion'and id:match('^explosion%.')
        and not id:match('^explosion%.[^.]+%.impact%.')
        and not id:match('^explosion%.[^.]+%.expiry%.')then
        resolved='explosion.'..role..'.'..canonical_explosion_phase(weapon,role,phase)..'.'
            ..id:sub(#'explosion.'+1)
    end
    for _,field in ipairs(weapon.fields)do if field.semanticFieldId==resolved then return field end end
    error('field is not exposed for '..weapon.name..': '..tostring(id),0)
end
local function identical_backing(a,c)
    if type(a)~='table'or type(c)~='table'or a.kind~=c.kind
        or a.offset~=c.offset or a.width~=c.width or a.storage~=c.storage then return false end
    if a.kind=='component'then return a.component==c.component and a.recordIndex==c.recordIndex
        and a.indexRow==c.indexRow end
    return a.settings==c.settings and a.group==c.group and a.row==c.row
        and a.recordType==c.recordType and a.settingsType==c.settingsType
end
local function scalar(field,value,label)
    if field.type=='boolean'then assert(type(value)=='boolean',label..' must be boolean');return value and 1 or 0 end
    assert(type(value)=='number'and value==value and value>-math.huge and value<math.huge,
        label..' must be finite number')
    if field.type=='integer'then assert(value%1==0,label..' must be integer')end
    return value
end
local function reference_selector(value,label)
    assert(type(value)=='table',label..' must be a projectile reference handle')
    for key in pairs(value)do assert(key=='resource'or key=='path'or key=='weapon'or key=='attack',
        label..' contains unsupported projectile reference identity')end
    assert(value.resource=='player_weapon'and value.path=='projectile_reference'
        and type(value.weapon)=='string'and type(value.attack)=='string',
        label..' must come from weapon:attack(role):projectile()')
    return {weapon=value.weapon,attack=value.attack}
end
local function explosion_selector(value,label)
    assert(type(value)=='table',label..' must be an explosion reference handle')
    for key in pairs(value)do assert(key=='resource'or key=='path'or key=='weapon'or key=='attack'
        or key=='phase',label..' contains unsupported explosion reference identity')end
    assert(value.resource=='player_weapon'and value.path=='explosion'
        and type(value.weapon)=='string'and type(value.attack)=='string'
        and(value.phase=='impact'or value.phase=='expiry'),
        label..' must come from projectile:terminal_action(phase):explosion()')
    return {weapon=value.weapon,attack=value.attack,phase=value.phase}
end
local function validate_change(weapon,item,allow_shared,role,path,phase)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    if path=='attack'then
        assert(item.field=='attack.projectile'or item.field=='attack.'..role..'.projectile',
            'attack targets only accept the typed attack.projectile reference field')
    elseif path=='terminal_action'then
        assert(item.field=='terminal.explosion'or item.field=='terminal.'..role..'.'..phase..'.explosion',
            'terminal targets only accept the typed terminal.explosion reference field')
    elseif path=='explosion'then
        assert(item.field:match('^explosion%.'),'explosion targets only accept explosion fields')
    else
        assert(item.field~='attack.projectile'and item.field~='terminal.explosion'
            and not item.field:match('^attack%..+%.projectile$')
            and not item.field:match('^terminal%.'),'typed reference field requires its semantic target')
    end
    local requested=field_for(weapon,item.field,role,path,phase);local field=requested
    if requested.aliasOf then
        field=field_for(weapon,requested.aliasOf,role,path,phase)
        assert(requested.deprecated and not requested.canonical and not requested.preferred
            and requested.acceptedForWrites and field.canonical and field.preferred,
            'field is read-only: '..item.field..' ('..tostring(requested.reason)..')')
        assert(requested.semanticTarget==field.semanticTarget
            and identical_backing(requested.backing,field.backing),'semantic alias backing changed')
    end
    assert(field.editable and field.backing,'field is read-only: '..item.field..' ('..tostring(field.reason)..')')
    assert(not field.affectsMultipleWeapons or allow_shared,
        'shared field requires allow_shared=true: '..item.field)
    if field.type=='projectile_reference'then
        assert(field.referenceKind=='projectile'and field.referenceRole==role,
            'projectile reference role changed')
        local expected=reference_selector(item.expect,'expect')
        local desired=reference_selector(item.value,'value')
        assert(expected.weapon==weapon.name and expected.attack==role,
            'expect must be the target attack current projectile handle')
        local source_weapon=assert(database.weapons[desired.weapon],
            'unknown projectile source weapon: '..desired.weapon)
        assert(not source_weapon.ordinaryWritesBlocked,
            'projectile source identity is ambiguous: '..desired.weapon)
        local source=field_for(source_weapon,'attack.'..desired.attack..'.projectile',desired.attack)
        assert(source.referenceKind=='projectile'and source.compatibilityClass==field.compatibilityClass,
            'incompatible projectile reference class')
        assert(source.compatibilityClass=='conventional_plain'
            or source.compatibilityClass=='explosive_impact'
            or source.compatibilityClass=='explosive_impact_and_expiry'
            or source.compatibilityClass=='explosive_shrapnel',
            'projectile compatibility class is not approved for replacement')
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            semantic_aliases={item.field},expect=item.expect,value=item.value,
            expected_selector=expected,desired_selector=desired,source_descriptor=source}
    end
    if field.type=='explosion_reference'then
        assert(field.referenceKind=='explosion'and field.referenceRole==role
            and field.referencePhase==phase,'explosion reference target changed')
        local expected=explosion_selector(item.expect,'expect')
        local desired=explosion_selector(item.value,'value')
        assert(expected.weapon==weapon.name and expected.attack==role and expected.phase==phase,
            'expect must be the target terminal action current explosion handle')
        local source_weapon=assert(database.weapons[desired.weapon],
            'unknown explosion source weapon: '..desired.weapon)
        assert(not source_weapon.ordinaryWritesBlocked,
            'explosion source identity is ambiguous: '..desired.weapon)
        local source=field_for(source_weapon,'terminal.explosion',desired.attack,
            'terminal_action',desired.phase)
        assert(source.referenceKind=='explosion','source is not a reviewed ExplosionSettings reference')
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            semantic_aliases={item.field},expect=item.expect,value=item.value,
            expected_selector=expected,desired_selector=desired,source_descriptor=source}
    end
    local expected=scalar(field,item.expect,'expect');local desired=scalar(field,item.value,'value')
    local storage=field.backing.storage
    local canonical=field.type=='boolean'and(field.currentDefault and 1 or 0)or field.currentDefault
    assert(equal(expected,canonical,storage),'expect differs from reviewed current value for '..item.field)
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
        semantic_aliases={item.field},expect=item.expect,value=item.value,
        expected=b.encode(expected,storage),desired=b.encode(desired,storage)}
end
local function id(value)
    assert(type(value)=='string'and#value>0 and#value<=64 and not value:find('[^%w_%-]'),'invalid operation id')
end

function M.validate_patch(request)
    assert(type(request)=='table','patch requires a descriptor')
    local allowed={id=true,target=true,field=true,expect=true,value=true,diagnostic=true,allow_shared=true}
    for key in pairs(request)do assert(allowed[key],'unsupported patch option: '..tostring(key))end
    id(request.id);local name,role,path,phase=target_name(request.target);local weapon=assert(database.weapons[name],'unknown player weapon')
    assert(not weapon.ordinaryWritesBlocked,weapon.blockReason)
    local change=validate_change(weapon,{field=request.field,expect=request.expect,value=request.value},
        request.allow_shared==true,role,path,phase)
    return {kind='player_weapon',id=request.id,weapon=name,resource=weapon.resources[1],
        attack=role,target_path=path,phase=phase,
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,
        field=request.field,expect=request.expect,value=request.value,changes={change}}
end
function M.validate_transaction(request)
    assert(type(request)=='table','transaction requires a descriptor')
    local allowed={id=true,target=true,changes=true,diagnostic=true,allow_shared=true}
    for key in pairs(request)do assert(allowed[key],'unsupported transaction option: '..tostring(key))end
    id(request.id);local name,role,path,phase=target_name(request.target);local weapon=assert(database.weapons[name],'unknown player weapon')
    assert(not weapon.ordinaryWritesBlocked,weapon.blockReason)
    assert(type(request.changes)=='table'and#request.changes>=1 and#request.changes<=32,
        'transaction requires one to 32 changes')
    local result={kind='player_weapon',id=request.id,weapon=name,resource=weapon.resources[1],attack=role,
        target_path=path,phase=phase,
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,changes={}}
    local seen,canonical_seen={},{ }
    for _,item in ipairs(request.changes)do
        assert(not seen[item.field],'duplicate transaction field: '..tostring(item.field));seen[item.field]=true
        local change=validate_change(weapon,item,result.allow_shared,role,path,phase)
        local prior=canonical_seen[change.canonical_field]
        if prior then
            local same_desired=prior.desired==change.desired
            local same_expected=prior.expected==change.expected
            if prior.desired_selector or change.desired_selector then
                same_desired=prior.desired_selector and change.desired_selector
                    and prior.desired_selector.weapon==change.desired_selector.weapon
                    and prior.desired_selector.attack==change.desired_selector.attack
                    and prior.desired_selector.phase==change.desired_selector.phase
                same_expected=prior.expected_selector and change.expected_selector
                    and prior.expected_selector.weapon==change.expected_selector.weapon
                    and prior.expected_selector.attack==change.expected_selector.attack
                    and prior.expected_selector.phase==change.expected_selector.phase
            end
            if not same_desired then
                error('SEMANTIC_CONFLICT: '..prior.field..' and '..change.field
                    ..' alias '..change.canonical_field..' with different desired values',0)
            end
            assert(same_expected,
                'semantic alias expected values differ: '..prior.field..' and '..change.field)
            prior.semantic_aliases[#prior.semantic_aliases+1]=change.field
        else
            result.changes[#result.changes+1]=change
            canonical_seen[change.canonical_field]=change
        end
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
        if backing.kind=='settings'and backing.settings~='explosion_damage'then needed[backing.settings]=true end
        if change.descriptor.type=='projectile_reference'then needed.projectile=true end
        if change.descriptor.type=='explosion_reference'or backing.settings=='explosion'
            or backing.settings=='explosion_damage'then
            needed.projectile=true;needed.explosion=true
        end
        if backing.settings=='explosion_damage'then needed.damage=true end
        if backing.settings=='damage'then
            needed.projectile=true;needed.arc='optional';needed.beam='optional'
        end
    end
    local roots=discover.locate(runtime,reader,profile,needed)
    local catalog=entities.capture(reader,roots.entity,profile,component_names)
    local resolved={roots=roots,catalog=catalog,candidate=find_candidate(catalog,spec.resource),
        reference_sources={}}
    for _,change in ipairs(spec.changes)do
        if change.desired_selector then
            local source=assert(database.weapons[change.desired_selector.weapon],
                'projectile source metadata missing')
            resolved.reference_sources[change.canonical_field]=find_candidate(catalog,source.resources[1])
        end
    end
    return resolved
end

local function component_record_for(resolved,candidate,backing)
    local record=resolved.catalog.record(candidate,backing.component)
    local identity=record.identity
    assert(identity.recordIndex==backing.recordIndex and identity.indexRow==backing.indexRow
        and identity.ownerCount==backing.ownerCount,'component ownership identity changed')
    return record
end
local function component_record(resolved,backing)
    return component_record_for(resolved,resolved.candidate,backing)
end
local function projectile_for_candidate(resolved,candidate,branch)
    local ownership=candidate.ownership
    local projectile_type
    if ownership.WeaponRoundsComponentData then
        local rounds=resolved.catalog.record(candidate,'WeaponRoundsComponentData')
        projectile_type=b.u32(rounds.bytes,(branch=='alternate'or branch=='feed_alternate')and 68 or 64)
    elseif ownership.ProjectileWeaponComponentData then
        local weapon=resolved.catalog.record(candidate,'ProjectileWeaponComponentData')
        projectile_type=b.u32(weapon.bytes,0)
    end
    assert(projectile_type and projectile_type~=0,'linked projectile selector absent')
    return assert(resolved.roots.projectile.records[projectile_type],
        'linked ProjectileSettings absent'),projectile_type
end
local function linked(resolved,kind,branch,phase)
    local ownership=resolved.candidate.ownership
    if kind=='projectile'or kind=='explosion'or kind=='explosion_damage'
        or(kind=='damage'and(ownership.WeaponRoundsComponentData
            or ownership.ProjectileWeaponComponentData))then
        local projectile_type
        local projectile;projectile,projectile_type=projectile_for_candidate(resolved,resolved.candidate,branch)
        if kind=='projectile'then return projectile,resolved.roots.projectile.owner end
        if kind=='damage'then
            local damage_type=b.u32(projectile.bytes,60)
            return assert(resolved.roots.damage.records[damage_type],'linked DamageInfo absent'),resolved.roots.damage.owner
        end
        local terminal_offset=phase=='expiry'and 156 or 144
        local explosion_type=b.u32(projectile.bytes,terminal_offset)
        local explosion=assert(resolved.roots.explosion.records[explosion_type],
            'linked ExplosionSettings absent')
        if kind=='explosion'then return explosion,resolved.roots.explosion.owner end
        local damage_type=b.u32(explosion.bytes,4)
        return assert(resolved.roots.damage.records[damage_type],
            'linked explosion DamageInfo absent'),resolved.roots.damage.owner
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
    local plan={changes={},snapshots=reader.snapshots};local physical={}
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing;local record,owner
        if backing.kind=='component'then record=component_record(resolved,backing);owner=record.owner
        else
            record,owner=linked(resolved,backing.settings,backing.branch,backing.phase)
            assert(record.group==backing.group and record.row==backing.row
                and record.kind==backing.recordType and record.settings_type==backing.settingsType,
                'settings record identity changed')
        end
        assert(backing.offset+backing.width<=#record.bytes,'field outside reviewed record')
        local current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
        local source_identity
        if change.descriptor.type=='projectile_reference'then
            local reviewed=change.descriptor.currentDefault.projectileType
            local expected=b.encode(reviewed,'u32')
            local source_candidate=assert(resolved.reference_sources[change.canonical_field],
                'projectile source was not freshly resolved')
            local source_record=component_record_for(resolved,source_candidate,
                change.source_descriptor.backing)
            local source_type=b.u32(source_record.bytes,change.source_descriptor.backing.offset)
            assert(source_type==change.source_descriptor.currentDefault.projectileType,
                'CONFLICT: source projectile reference changed')
            local settings=assert(resolved.roots.projectile.records[source_type],
                'source ProjectileSettings record absent')
            local reviewed_settings=change.source_descriptor.referenceSettings
            assert(settings.group==reviewed_settings.group and settings.row==reviewed_settings.row
                and settings.kind==reviewed_settings.recordType
                and settings.settings_type==reviewed_settings.settingsType,
                'source ProjectileSettings identity changed')
            change.expected=expected;change.desired=b.encode(source_type,'u32')
            source_identity={component=change.source_descriptor.backing.component,
                record_index=change.source_descriptor.backing.recordIndex,
                index_row=change.source_descriptor.backing.indexRow,
                projectile_type=source_type,settings_group=settings.group,
                settings_row=settings.row,settings_type=settings.settings_type,
                scope='projectile_reference_source'}
        elseif change.descriptor.type=='explosion_reference'then
            local reviewed=change.descriptor.currentDefault.explosionType
            local expected=b.encode(reviewed,'u32')
            local source_candidate=assert(resolved.reference_sources[change.canonical_field],
                'explosion source was not freshly resolved')
            local source_projectile,source_projectile_type=projectile_for_candidate(resolved,
                source_candidate,change.source_descriptor.referenceRole)
            local reviewed_projectile=change.source_descriptor.projectileSettings
            assert(source_projectile.group==reviewed_projectile.group
                and source_projectile.row==reviewed_projectile.row
                and source_projectile.kind==reviewed_projectile.recordType
                and source_projectile.settings_type==reviewed_projectile.settingsType,
                'source ProjectileSettings identity changed')
            local source_type=b.u32(source_projectile.bytes,change.source_descriptor.backing.offset)
            assert(source_type==change.source_descriptor.currentDefault.explosionType,
                'CONFLICT: source explosion reference changed')
            local settings=assert(resolved.roots.explosion.records[source_type],
                'source ExplosionSettings record absent')
            local reviewed_settings=change.source_descriptor.referenceSettings
            assert(settings.group==reviewed_settings.group and settings.row==reviewed_settings.row
                and settings.kind==reviewed_settings.recordType
                and settings.settings_type==reviewed_settings.settingsType,
                'source ExplosionSettings identity changed')
            change.expected=expected;change.desired=b.encode(source_type,'u32')
            source_identity={component='ExplosionSettings',record_index=settings.row,
                projectile_type=source_projectile_type,explosion_type=source_type,
                settings_group=settings.group,settings_row=settings.row,
                settings_type=settings.settings_type,scope='explosion_reference_source'}
        end
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
        local offset=record.offset+backing.offset
        local key=tostring(owner.base)..':'..tostring(offset)..':'..tostring(backing.width)
        local prior=physical[key]
        if prior then
            if prior.canonical_field==change.canonical_field then
                if prior.desired~=change.desired then
                    error('SEMANTIC_CONFLICT: '..prior.label..' and '..change.field
                        ..' resolve to the same backing bytes with different desired values',0)
                end
                for _,alias in ipairs(change.semantic_aliases)do
                    prior.semantic_aliases[#prior.semantic_aliases+1]=alias
                end
            else
                error('overlapping semantic fields are not proven aliases: '..prior.label
                    ..' and '..change.field,0)
            end
        else
            local item={label=change.field,canonical_field=change.canonical_field,
            semantic_aliases=change.semantic_aliases,owner=owner,offset=offset,
            expected=change.expected,desired=change.desired,before=current,
            already_desired=current==change.desired,identity=identity,chain={identity},
            expect=change.expect,value=change.value}
            if source_identity then item.chain[#item.chain+1]=source_identity end
            plan.changes[#plan.changes+1]=item;physical[key]=item
        end
    end
    return plan
end
return M
