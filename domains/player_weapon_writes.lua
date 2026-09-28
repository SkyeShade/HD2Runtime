-- Reviewed semantic player-weapon writes. Runtime addresses never enter this database or public API.
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/player_weapon_authoring')
local support_database=require('hd2runtime/domains/support_weapon_authoring')
local M={}
local component_names={'ProjectileWeaponComponentData','WeaponDataComponentData',
    'WeaponMagazineComponentData','WeaponRoundsComponentData','ArcWeaponComponentData',
    'MeleeWeaponComponentData','BeamWeaponComponentData','SprayWeaponComponentData',
    'WeaponHeatComponentData','WeaponChargeComponentData','ExplosiveComponentData',
    'HellpodRackComponentData','WeaponLinkedAmmoComponentData','WeaponReloadComponentData',
    'WeaponWindUpComponentData'}

local function equal(a,c,kind)
    if kind=='f32'then return type(a)=='number'and type(c)=='number'
        and math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function target_name(target)
    assert(type(target)=='table'and(target.resource=='player_weapon'
        or target.resource=='support_weapon')and type(target.weapon)=='string',
        'unsupported weapon target')
    local kind=target.resource
    if target.path=='weapon'then
        for key in pairs(target)do assert(key=='resource'or key=='path'or key=='weapon',
            'unsupported player weapon target identity')end
        return target.weapon,nil,'weapon',nil,kind
    end
    assert((target.path=='attack'or target.path=='projectile_reference'
        or target.path=='terminal_action'or target.path=='explosion')
        and type(target.attack)=='string','unsupported weapon target')
    if target.path=='terminal_action'or(target.path=='explosion'and kind=='player_weapon')then
        assert(target.phase=='impact'or target.phase=='expiry','unsupported terminal action phase')
    end
    for key in pairs(target)do assert(key=='resource'or key=='path'or key=='weapon'or key=='attack'
        or key=='phase','unsupported player weapon target identity')end
    return target.weapon,target.attack,target.path,target.phase,kind
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
    if weapon.supportWeapon then
        if path=='projectile_reference'and id:match('^projectile%.')then
            resolved='projectile.'..role..'.'..id:sub(#'projectile.'+1)
        elseif path=='projectile_reference'and id:match('^damage%.')then
            resolved='damage.'..role..'.'..id:sub(#'damage.'+1)
        elseif path=='explosion'and id:match('^explosion%.damage%.')then
            resolved='explosion.'..role..'.damage.'..id:sub(#'explosion.damage.'+1)
        elseif path=='explosion'and id:match('^explosion%.')then
            resolved='explosion.'..role..'.'..id:sub(#'explosion.'+1)
        elseif path=='attack'and(id:match('^damage%.')or id:match('^arc%.')
            or id:match('^beam%.')or id:match('^status%.'))then
            local domain=id:match('^([^.]+)')
            resolved=domain..'.'..role..'.'..id:sub(#domain+2)
        end
        for _,field in ipairs(weapon.fields)do if field.semanticFieldId==resolved then return field end end
        error('field is not exposed for '..weapon.name..': '..tostring(id),0)
    end
    if id=='attack.projectile'then
        assert(type(role)=='string','attack.projectile requires weapon:attack(role) target')
        resolved='attack.'..role..'.projectile'
    elseif id=='terminal.explosion'then
        resolved='terminal.'..role..'.'..phase..'.explosion'
    elseif path=='projectile_reference'and id:match('^projectile%.')then
        local branch='projectile.'..role..'.'..id:sub(#'projectile.'+1)
        for _,field in ipairs(weapon.fields)do if field.semanticFieldId==branch then resolved=branch end end
    elseif path=='projectile_reference'and id:match('^damage%.')then
        local branch='damage.'..role..'.'..id:sub(#'damage.'+1)
        for _,field in ipairs(weapon.fields)do if field.semanticFieldId==branch then resolved=branch end end
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
    assert(value.resource=='player_weapon'and(value.path=='explosion'or value.path=='no_explosion')
        and type(value.weapon)=='string'and type(value.attack)=='string'
        and(value.phase=='impact'or value.phase=='expiry'),
        label..' must come from projectile:terminal_action(phase):explosion()')
    return {weapon=value.weapon,attack=value.attack,phase=value.phase,
        is_null=value.path=='no_explosion'}
end
local function validate_change(weapon,item,allow_shared,role,path,phase,allow_unverified_effect)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    if path=='attack'and weapon.supportWeapon then
        assert(item.field:match('^damage%.')or item.field:match('^arc%.')
            or item.field:match('^beam%.')or item.field:match('^status%.'),
            'support attack target accepts only its reviewed damage/family/status fields')
    elseif path=='attack'then
        assert(item.field=='attack.projectile'or item.field=='attack.'..role..'.projectile',
            'COMPOSITION_TARGET_CHANGED: attack transactions only replace the projectile reference; edit the freshly resolved source projectile object in a separate guarded operation with allow_shared=true')
    elseif path=='terminal_action'then
        assert(item.field=='terminal.explosion'or item.field=='terminal.'..role..'.'..phase..'.explosion',
            'terminal targets only accept the typed terminal.explosion reference field')
    elseif path=='explosion'then
        assert(item.field:match('^explosion%.'),'explosion targets only accept explosion fields')
    elseif path=='projectile_reference'then
        assert(item.field:match('^projectile%.')or item.field:match('^damage%.'),
            'projectile objects only accept projectile or linked damage fields')
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
    assert(field.acknowledgement~='allow_unverified_effect'or allow_unverified_effect,
        'field requires allow_unverified_effect=true: '..item.field..' ('..tostring(field.acknowledgementReason)..')')
    if path=='projectile_reference'and field.backing.settings then
        assert(allow_shared,'projectile object edits require allow_shared=true because definitions are shared')
    end
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
        assert(expected.weapon==desired.weapon and expected.attack==desired.attack
            or not source.residency or source.residency.classification~='SOURCE_WEAPON_REQUIRED',
            'projectile source dependency is not resident without its source weapon: '..desired.weapon)
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
        assert(expected.is_null==(field.currentDefault.explosionType==0),
            'expect does not represent the reviewed terminal reference')
        local source
        if not desired.is_null then
            local source_weapon=assert(database.weapons[desired.weapon],
                'unknown explosion source weapon: '..desired.weapon)
            assert(not source_weapon.ordinaryWritesBlocked,
                'explosion source identity is ambiguous: '..desired.weapon)
            source=field_for(source_weapon,'terminal.explosion',desired.attack,
                'terminal_action',desired.phase)
            assert(source.referenceKind=='explosion'and source.currentDefault.explosionType~=0,
                'source is not a reviewed ExplosionSettings reference')
        end
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            semantic_aliases={item.field},expect=item.expect,value=item.value,
            expected_selector=expected,desired_selector=desired,source_descriptor=source}
    end
    local expected=scalar(field,item.expect,'expect');local desired=scalar(field,item.value,'value')
    if field.writeKind=='reorder_native_mode_vector'then
        assert((expected==1 or expected==2)and(expected==field.currentDefault),
            'expect differs from reviewed default fire mode')
        local allowed={};for _,mode in ipairs(field.allowedValues)do allowed[mode]=true end
        assert(allowed[desired]and desired~=expected,
            'destination fire mode is not in this weapon native mode vector')
    end
    local storage=field.backing.storage
    local canonical=field.type=='boolean'and(field.currentDefault and 1 or 0)or field.currentDefault
    assert(equal(expected,canonical,storage),'expect differs from reviewed current value for '
        ..item.field..': declared='..tostring(expected)..' reviewed='..tostring(canonical)
        ..' resolved='..tostring(field.semanticFieldId))
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
        semantic_aliases={item.field},expect=item.expect,value=item.value,
        expected=b.encode(expected,storage),desired=b.encode(desired,storage)}
end
local function id(value)
    assert(type(value)=='string'and#value>0 and#value<=64 and not value:find('[^%w_%-]'),'invalid operation id')
end

function M.validate_patch(request)
    assert(type(request)=='table','patch requires a descriptor')
    local allowed={id=true,target=true,field=true,expect=true,value=true,diagnostic=true,allow_shared=true,
        allow_unverified_effect=true}
    for key in pairs(request)do assert(allowed[key],'unsupported patch option: '..tostring(key))end
    id(request.id);local name,role,path,phase,kind=target_name(request.target)
    local selected=kind=='support_weapon'and support_database or database
    local weapon=assert(selected.weapons[name],'unknown reviewed weapon')
    assert(not weapon.ordinaryWritesBlocked,weapon.blockReason)
    local change=validate_change(weapon,{field=request.field,expect=request.expect,value=request.value},
        request.allow_shared==true,role,path,phase,request.allow_unverified_effect==true)
    return {kind=kind,id=request.id,weapon=name,
        resource=weapon.attackResource or weapon.resources[1],identity_resource=weapon.identityResource,
        ownership_chain=weapon.ownershipChain,root_rack=weapon.rootRack,
        attack=role,target_path=path,phase=phase,
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,
        field=request.field,expect=request.expect,value=request.value,changes={change}}
end
function M.validate_transaction(request)
    assert(type(request)=='table','transaction requires a descriptor')
    local allowed={id=true,target=true,changes=true,diagnostic=true,allow_shared=true,
        allow_unverified_effect=true}
    for key in pairs(request)do assert(allowed[key],'unsupported transaction option: '..tostring(key))end
    id(request.id);local name,role,path,phase,kind=target_name(request.target)
    local selected=kind=='support_weapon'and support_database or database
    local weapon=assert(selected.weapons[name],'unknown reviewed weapon')
    assert(not weapon.ordinaryWritesBlocked,weapon.blockReason)
    assert(type(request.changes)=='table'and#request.changes>=1 and#request.changes<=32,
        'transaction requires one to 32 changes')
    local result={kind=kind,id=request.id,weapon=name,
        resource=weapon.attackResource or weapon.resources[1],identity_resource=weapon.identityResource,
        ownership_chain=weapon.ownershipChain,root_rack=weapon.rootRack,attack=role,
        target_path=path,phase=phase,
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,changes={}}
    local seen,canonical_seen={},{ }
    for _,item in ipairs(request.changes)do
        assert(not seen[item.field],'duplicate transaction field: '..tostring(item.field));seen[item.field]=true
        local change=validate_change(weapon,item,result.allow_shared,role,path,phase,
            request.allow_unverified_effect==true)
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

local function add_need(needed,name,value)
    if value==true or needed[name]==nil then needed[name]=value end
end
local function collect_needs(needed,spec)
    add_need(needed,'entity',true)
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        if backing.kind=='settings'then
            local settings_kind=backing.settings=='explosion_damage'and'damage'or backing.settings
            add_need(needed,settings_kind,true)
            local linkage=(backing.linkage or'')..' '..(backing.parentLinkage or'')
            if backing.parentLinkage then add_need(needed,'damage',true)end
            if linkage:find('projectile',1,true)then add_need(needed,'projectile',true)end
            if linkage:find('explosion',1,true)then add_need(needed,'explosion',true)end
            if linkage:find('arc',1,true)then add_need(needed,'arc',true)end
            if linkage:find('beam',1,true)then add_need(needed,'beam',true)end
        end
        if change.descriptor.type=='projectile_reference'then add_need(needed,'projectile',true)end
        if change.descriptor.type=='explosion_reference'or backing.settings=='explosion'
            or backing.settings=='explosion_damage'then
            add_need(needed,'projectile',true);add_need(needed,'explosion',true)
        end
        if backing.settings=='explosion_damage'then add_need(needed,'damage',true)end
        if backing.settings=='damage'then
            add_need(needed,'projectile',true);add_need(needed,'arc','optional')
            add_need(needed,'beam','optional')
        end
    end
end
function M.capture_many(runtime,reader,specs)
    assert(type(specs)=='table'and#specs>=1,'composition capture requires operation specs')
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local needed={};for _,spec in ipairs(specs)do collect_needs(needed,spec)end
    local roots=discover.locate(runtime,reader,profile,needed)
    local catalog=entities.capture(reader,roots.entity,profile,component_names)
    local results={}
    for index,spec in ipairs(specs)do
        local selected=spec.kind=='support_weapon'and support_database or database
        local resolved={roots=roots,catalog=catalog,candidate=find_candidate(catalog,spec.resource),
            database=selected,
            reference_sources={}}
        if spec.kind=='support_weapon'and spec.identity_resource
            and spec.identity_resource~=spec.resource then
            local identity_candidate=find_candidate(catalog,spec.identity_resource)
            local rack=resolved.catalog.record(identity_candidate,'HellpodRackComponentData')
            local linked=false
            for slot=0,7 do if b.resource(rack.bytes,slot*64)==spec.resource then linked=true end end
            assert(linked,'support ownership chain changed: rack no longer links attack entity')
            local expected=spec.root_rack
            assert(expected and identity_candidate.entityRow==expected.entityRow
                and rack.identity.recordIndex==expected.recordIndex,
                'support ownership chain changed: rack identity differs')
            local stratagem=require('hd2runtime/core/stratagem')
            local records=stratagem.capture_all(runtime,reader,profile);local chain=spec.ownership_chain or{}
            for _,node in ipairs(chain)do if node.kind=='stratagem_payload'then
                local found=false
                for _,record in ipairs(records)do
                    if record.id==node.id and record.package==node.package then
                        for _,payload in ipairs(record.payloads or{})do
                            if payload==spec.identity_resource then found=true end
                        end
                    end
                end
                assert(found,'support ownership chain changed: stratagem payload link absent')
            end end
            resolved.identity_candidate=identity_candidate
        end
        for _,change in ipairs(spec.changes)do
            if change.desired_selector and not change.desired_selector.is_null then
                local source=assert(selected.weapons[change.desired_selector.weapon],
                    'projectile source metadata missing')
                resolved.reference_sources[change.canonical_field]=find_candidate(catalog,source.resources[1])
            end
        end
        results[index]=resolved
    end
    return results
end
function M.capture(runtime,reader,spec)
    return M.capture_many(runtime,reader,{spec})[1]
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

local function support_explosion(resolved,backing)
    if backing.linkage:find('explosive_explosion',1,true)then
        local component=component_record(resolved,{component='ExplosiveComponentData',
            recordIndex=resolved.candidate.ownership.ExplosiveComponentData.recordIndex,
            indexRow=resolved.candidate.ownership.ExplosiveComponentData.indexRow,
            ownerCount=resolved.candidate.ownership.ExplosiveComponentData.ownerCount})
        local explosion_type=b.u32(component.bytes,assert(backing.selectorOffset))
        return assert(resolved.roots.explosion.records[explosion_type],
            'linked placed-entity ExplosionSettings absent')
    end
    local projectile=projectile_for_candidate(resolved,resolved.candidate,
        backing.parentRole or backing.branch)
    local offset=backing.phase=='expiry'and 156 or 144
    return assert(resolved.roots.explosion.records[b.u32(projectile.bytes,offset)],
        'linked support projectile ExplosionSettings absent')
end

local function support_damage(resolved,backing,linkage)
    if linkage=='projectile_damage'then
        local projectile=projectile_for_candidate(resolved,resolved.candidate,backing.branch)
        return assert(resolved.roots.damage.records[b.u32(projectile.bytes,60)],
            'linked support projectile DamageInfo absent')
    end
    if linkage=='arc_damage'then
        local component=resolved.catalog.record(resolved.candidate,'ArcWeaponComponentData')
        local arc=assert(resolved.roots.arc.records[b.u32(component.bytes,0)],'linked ArcSettings absent')
        return assert(resolved.roots.damage.records[b.u32(arc.bytes,36)],'linked arc DamageInfo absent')
    end
    if linkage=='beam_damage'then
        local component=resolved.catalog.record(resolved.candidate,'BeamWeaponComponentData')
        local beam=assert(resolved.roots.beam.records[b.u32(component.bytes,0)],'linked BeamSettings absent')
        return assert(resolved.roots.damage.records[b.u32(beam.bytes,12)],'linked beam DamageInfo absent')
    end
    if linkage=='spray_damage'then
        local component=resolved.catalog.record(resolved.candidate,'SprayWeaponComponentData')
        return assert(resolved.roots.damage.records[b.u32(component.bytes,200)],'linked spray DamageInfo absent')
    end
    if linkage=='melee_damage'then
        local component=resolved.catalog.record(resolved.candidate,'MeleeWeaponComponentData')
        return assert(resolved.roots.damage.records[b.u32(component.bytes,12)],'linked melee DamageInfo absent')
    end
    if linkage:find('explosion_damage',1,true)then
        local explosion=support_explosion(resolved,backing)
        return assert(resolved.roots.damage.records[b.u32(explosion.bytes,4)],
            'linked support explosion DamageInfo absent')
    end
    error('reviewed support DamageInfo linkage unavailable: '..tostring(linkage),0)
end

local function support_linked(resolved,backing)
    local linkage=assert(backing.linkage,'support settings linkage missing')
    if linkage=='projectile'then
        local record=projectile_for_candidate(resolved,resolved.candidate,backing.branch)
        return record,resolved.roots.projectile.owner
    end
    if linkage=='arc'then
        local component=resolved.catalog.record(resolved.candidate,'ArcWeaponComponentData')
        return assert(resolved.roots.arc.records[b.u32(component.bytes,0)],'linked ArcSettings absent'),
            resolved.roots.arc.owner
    end
    if linkage=='beam'then
        local component=resolved.catalog.record(resolved.candidate,'BeamWeaponComponentData')
        return assert(resolved.roots.beam.records[b.u32(component.bytes,0)],'linked BeamSettings absent'),
            resolved.roots.beam.owner
    end
    if linkage=='status'then
        local damage=support_damage(resolved,backing,assert(backing.parentLinkage))
        local matches=0
        for offset=44,68,8 do if b.u32(damage.bytes,offset)==backing.statusType then matches=matches+1 end end
        assert(matches==1,'linked StatusEffectSettings owner absent or ambiguous')
        return assert(resolved.roots.status.records[backing.statusType],
            'linked StatusEffectSettings absent'),resolved.roots.status.owner
    end
    if linkage:find('explosion',1,true)and not linkage:find('damage',1,true)then
        return support_explosion(resolved,backing),resolved.roots.explosion.owner
    end
    return support_damage(resolved,backing,linkage),resolved.roots.damage.owner
end

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots};local physical={}
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing;local record,owner
        if backing.kind=='component'then record=component_record(resolved,backing);owner=record.owner
        elseif spec.kind=='support_weapon'and backing.linkage then
            record,owner=support_linked(resolved,backing)
            assert(record.group==backing.group and record.row==backing.row
                and record.kind==backing.recordType and record.settings_type==backing.settingsType,
                'support settings record identity changed')
        else
            record,owner=linked(resolved,backing.settings,backing.branch,backing.phase)
            assert(record.group==backing.group and record.row==backing.row
                and record.kind==backing.recordType and record.settings_type==backing.settingsType,
                (spec.target_path=='projectile_reference'
                    and 'COMPOSITION_TARGET_CHANGED: projectile fields now belong to the newly referenced object; target that source projectile handle and acknowledge shared ownership'
                    or 'settings record identity changed'))
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
            local source_type=0
            if not change.desired_selector.is_null then
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
                source_type=b.u32(source_projectile.bytes,change.source_descriptor.backing.offset)
                assert(source_type==change.source_descriptor.currentDefault.explosionType,
                    'CONFLICT: source explosion reference changed')
                local settings=assert(resolved.roots.explosion.records[source_type],
                    'source ExplosionSettings record absent')
                local reviewed_settings=change.source_descriptor.referenceSettings
                assert(settings.group==reviewed_settings.group and settings.row==reviewed_settings.row
                    and settings.kind==reviewed_settings.recordType
                    and settings.settings_type==reviewed_settings.settingsType,
                    'source ExplosionSettings identity changed')
                source_identity={component='ExplosionSettings',record_index=settings.row,
                    projectile_type=source_projectile_type,explosion_type=source_type,
                    settings_group=settings.group,settings_row=settings.row,
                    settings_type=settings.settings_type,scope='explosion_reference_source'}
            end
            change.expected=expected;change.desired=b.encode(source_type,'u32')
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
            if change.descriptor.writeKind=='reorder_native_mode_vector'then
                local vector=change.descriptor.nativeModeVector
                assert(#vector==3 and(b.u32(record.bytes,144)==change.expect
                    or b.u32(record.bytes,144)==change.value),
                    'CONFLICT: native fire-mode vector changed')
                local companion_index
                for index=2,3 do if vector[index]==change.value then companion_index=index end end
                assert(companion_index,'destination fire mode is absent from native vector')
                local companion_offset=record.offset+144+(companion_index-1)*4
                local companion_current=record.bytes:sub(145+(companion_index-1)*4,
                    148+(companion_index-1)*4)
                local companion_expected=b.encode(change.value,'u32')
                local companion_desired=b.encode(change.expect,'u32')
                assert(companion_current==companion_expected or companion_current==companion_desired,
                    'CONFLICT: native fire-mode companion changed')
                local companion={label=change.field..'.allowed_slot',
                    canonical_field=change.canonical_field..'.allowed_slot',semantic_aliases={},
                    owner=owner,offset=companion_offset,expected=companion_expected,
                    desired=companion_desired,before=companion_current,
                    already_desired=companion_current==companion_desired,identity=identity,
                    chain={identity},expect=change.value,value=change.expect}
                plan.changes[#plan.changes+1]=companion
                physical[tostring(owner.base)..':'..tostring(companion_offset)..':4']=companion
            end
        end
    end
    return plan
end
return M
