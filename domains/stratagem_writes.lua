-- Guarded stratagem definition and offensive payload authoring.
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local Stratagem=require('hd2runtime/core/stratagem')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/stratagem_authoring')
local M={}
local component_names={'BombardmentComponentData','EagleComponentData',
    'ProjectileWeaponComponentData','OrbitalAbilityComponentData',
    'HealthComponentData','WeaponDataComponentData','WeaponMagazineComponentData',
    'WeaponRoundsComponentData','WeaponHeatComponentData','WeaponChargeComponentData',
    'ArcWeaponComponentData','BeamWeaponComponentData','SprayWeaponComponentData',
    'ShieldComponentData','HellpodPayloadComponentData','MinefieldComponentData',
    'TurretComponentData','SensorEyeComponentData'}
local ENTITY_PATHS={deployed_entity=true,weapon=true,attack=true,shield=true,damage_zone=true,
    turret=true,targeting=true}
local GRAPH_PATHS={deployed_entity=true,weapon=true,attack=true}

local function equal(a,c,storage)
    if storage=='f32'then return type(a)=='number'and type(c)=='number'
        and math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64
        and not value:find('[^%w_%-]'),'invalid operation id')
end
local function find_field(entry,target,id)
    for _,field in ipairs(entry.fields)do
        local t=field.target
        if field.semanticFieldId==id and t.path==target.path
            and t.entity==rawget(target,'entity') and t.weapon==rawget(target,'weapon')
            and t.attack==rawget(target,'attack') and t.zone==rawget(target,'zone') then return field end
    end
    error('field is not exposed for '..entry.name..': '..tostring(id),0)
end
local function validate_target(target)
    assert(type(target)=='table'and target.resource=='stratagem'
        and type(target.stratagem)=='string','unsupported stratagem target')
    local entry=assert(database.stratagems[target.stratagem],
        'unknown reviewed stratagem: '..target.stratagem)
    if target.path=='attack'then
        if entry.deployedEntity then
            assert(type(rawget(target,'entity'))=='string','deployed entity required')
            assert(type(rawget(target,'weapon'))=='string','mounted weapon required')
        end
        assert(type(rawget(target,'attack'))=='string','stratagem attack role required')
    elseif target.path=='weapon'then
        assert(type(rawget(target,'entity'))=='string','deployed entity required')
        assert(type(rawget(target,'weapon'))=='string','mounted weapon required')
    elseif target.path=='deployed_entity' or target.path=='shield' or target.path=='turret'
        or target.path=='targeting'then
        assert(type(rawget(target,'entity'))=='string','deployed entity required')
    elseif target.path=='damage_zone'then
        assert(type(rawget(target,'entity'))=='string','deployed entity required')
        assert(type(rawget(target,'zone'))=='string','damage zone identity required')
    else assert(target.path=='stratagem'or target.path=='eagle_rearm','unsupported stratagem target')end
    for key in pairs(target)do assert(key=='resource'or key=='stratagem'or key=='path'or key=='entity'
        or key=='weapon'or key=='attack'or key=='zone',
        'unsupported stratagem target identity')end
    return entry
end
-- Mission uses (StratagemInfo +80): an integer count or 'unlimited', which is the native
-- 0xFFFFFFFF value the game itself uses; no large finite number stands in for unlimited.
local UNLIMITED=4294967295
local function uses_value(field,value,label)
    if value=='unlimited'then return UNLIMITED end
    assert(type(value)=='number'and value%1==0 and value>=field.min and value<=field.max,
        label..' must be "unlimited" or an integer use count from '..field.min..' to '..field.max)
    return value
end
local function validate_uses(field,item,allow_unverified_effect)
    local expected=uses_value(field,item.expect,'expect');local desired=uses_value(field,item.value,'value')
    assert(item.expect==field.currentDefault,'expect differs from reviewed current value for '..item.field)
    local proven=false
    for _,value in ipairs(field.gameplayProvenValues or{})do if value==item.value then proven=true end end
    assert(proven or item.value==item.expect or allow_unverified_effect,
        'mission use change requires allow_unverified_effect=true: '..item.field..' ('..field.acknowledgementReason..')')
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
        expected=b.encode(expected,'u32'),desired=b.encode(desired,'u32'),expect=item.expect,value=item.value}
end
local function validate_change(entry,target,item,allow_shared,allow_unverified_effect)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=find_field(entry,target,item.field)
    assert(field.editable and field.backing,'field is read-only: '..item.field
        ..' ('..tostring(field.reason)..')')
    assert(not field.shared or allow_shared,'shared field requires allow_shared=true: '..item.field)
    if field.type=='stratagem_uses'then return validate_uses(field,item,allow_unverified_effect)end
    assert(field.acknowledgement~='allow_unverified_effect'or allow_unverified_effect,
        'field requires allow_unverified_effect=true: '..item.field..' ('..tostring(field.acknowledgementReason)..')')
    local expected=item.expect;local desired=item.value
    assert(type(expected)=='number'and expected==expected and expected>-math.huge and expected<math.huge,
        'expect must be a finite number')
    assert(type(desired)=='number'and desired==desired and desired>-math.huge and desired<math.huge,
        'value must be a finite number')
    if field.type=='integer'then
        assert(expected%1==0 and desired%1==0,'integer stratagem field requires integer values')
    end
    assert(equal(expected,field.currentDefault,field.backing.storage),
        'expect differs from reviewed current value for '..item.field)
    if field.min then
        assert(desired>=field.min and desired<=field.max,
            'value outside the reviewed range for '..item.field..' ('..field.min..' to '..field.max..')')
    end
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
        expected=b.encode(expected,field.backing.storage),desired=b.encode(desired,field.backing.storage),
        expect=expected,value=desired}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed=multiple and{id=true,target=true,changes=true,diagnostic=true,allow_shared=true,
        allow_unverified_effect=true}
        or{id=true,target=true,field=true,expect=true,value=true,diagnostic=true,allow_shared=true,
        allow_unverified_effect=true}
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id);local entry=validate_target(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=32,'transaction requires one to 32 changes')
    local result={kind='stratagem',id=request.id,stratagem=entry.name,target_path=request.target.path,
        attack=rawget(request.target,'attack'),diagnostic=request.diagnostic==true,
        allow_shared=request.allow_shared==true,allow_unverified_effect=request.allow_unverified_effect==true,
        changes={}}
    local object
    for index,item in ipairs(items)do
        local change=validate_change(entry,request.target,item,result.allow_shared,result.allow_unverified_effect)
        local current=change.descriptor.operationGroup
        object=object or current
        assert(not multiple or object==current,
            'transaction spans multiple backing objects; use hd2.plan')
        result.changes[index]=change
    end
    result.field=request.field;result.expect=request.expect;result.value=request.value
    return result
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

local function find_root(records,reviewed)
    local selected
    for _,record in ipairs(records)do
        if record.id==reviewed.id then
            assert(record.package==reviewed.package and record.group==reviewed.group
                and record.row==reviewed.row,'stratagem root identity changed')
            assert(#record.payloads==#reviewed.payloads,'stratagem payload count changed')
            for index,value in ipairs(reviewed.payloads)do
                assert(record.payloads[index]==value,'stratagem payload identity changed')
            end
            assert(not selected,'stratagem root ambiguous');selected=record
        end
    end
    return assert(selected,'stratagem root absent')
end
local function find_candidate(catalog,resource)
    local found
    for _,candidate in ipairs(catalog.candidates)do if candidate.resourceHash==resource then
        assert(not found,'payload entity identity ambiguous');found=candidate end end
    assert(found and found.entityRow and#found.diagnostics==0,'payload entity identity absent')
    return found
end
local function graph_record(roots,node)
    local map={ProjectileSettings='projectile',DamageInfo='damage',
        ExplosionSettings='explosion',StatusEffectSettings='status',
        ArcSettings='arc',BeamSettings='beam'}
    local kind=map[node.kind];if not kind then return nil end
    local record=assert(roots[kind]and roots[kind].records[node.recordType],
        'reviewed '..node.kind..' absent')
    assert(record.group==node.group and record.row==node.row and record.kind==node.recordType,
        node.kind..' identity changed')
    return record,roots[kind].owner
end
local function validate_graph(entry,roots,component)
    local nodes={};for _,node in ipairs(entry.graph or{})do nodes[node.path]=node end
    if entry.rootLink and entry.rootLink.component=='BombardmentComponentData'then
        for index,value in ipairs(entry.rootProjectiles)do
            assert(b.u32(component.bytes,64+(index-1)*4)==value,'bombardment projectile list changed')
        end
    elseif entry.rootLink and entry.rootLink.component=='EagleComponentData'then
        assert(b.u32(component.bytes,24)==entry.rootProjectiles[1],'Eagle payload projectile changed')
    elseif entry.rootLink and entry.rootLink.component=='ProjectileWeaponComponentData'then
        assert(b.u32(component.bytes,0)==entry.rootProjectiles[1],'Eagle gun projectile changed')
    elseif entry.rootLink and entry.name=='Orbital Railcannon Strike'then
        assert(b.u32(component.bytes,532)==entry.rootProjectiles[1],'orbital projectile changed')
    elseif entry.rootLink and entry.name=='Orbital Laser'then
        local damage=assert(nodes['beam/damage'],'orbital laser DamageInfo descriptor absent')
        assert(b.u32(component.bytes,476)==damage.recordType,'orbital laser damage link changed')
    end
    for _,node in ipairs(entry.graph or{})do
        local record=graph_record(roots,node)
        if record then
            if node.kind=='ProjectileSettings'then
                local child=nodes[node.path..'/damage'];if child then
                    assert(b.u32(record.bytes,60)==child.recordType,'projectile damage link changed')end
                for _,phase in ipairs({'impact','expiry'})do child=nodes[node.path..'/'..phase]
                    if child then assert(b.u32(record.bytes,phase=='impact'and 144 or 156)==child.recordType,
                        'projectile explosion link changed')end end
            elseif node.kind=='ExplosionSettings'then
                local child=nodes[node.path..'/damage'];if child then
                    assert(b.u32(record.bytes,4)==child.recordType,'explosion damage link changed')end
                child=nodes[node.path..'/shrapnel'];if child then
                    assert(b.u32(record.bytes,84)==child.recordType,'explosion shrapnel link changed')end
            elseif node.kind=='DamageInfo'then
                for slot=1,4 do local child=nodes[node.path..'/status:'..slot]
                    if child then assert(b.u32(record.bytes,44+(slot-1)*8)==child.recordType,
                        'damage status link changed')end end
            elseif node.kind=='ArcSettings'then
                local child=nodes[node.path..'/damage'];if child then
                    assert(b.u32(record.bytes,36)==child.recordType,'arc damage link changed')end
            elseif node.kind=='BeamSettings'then
                local child=nodes[node.path..'/damage'];if child then
                    assert(b.u32(record.bytes,12)==child.recordType,'beam damage link changed')end
            end
        end
    end
end

local function collect_needs(spec)
    local needed={}
    for _,change in ipairs(spec.changes)do
        local kind=change.descriptor.backing.kind
        if kind=='ProjectileSettings'then needed.projectile=true
        elseif kind=='DamageInfo'then needed.damage=true
        elseif kind=='ExplosionSettings'then needed.explosion=true
        elseif kind=='StatusEffectSettings'then needed.status=true
        elseif kind=='ArcSettings'then needed.arc=true
        elseif kind=='BeamSettings'then needed.beam=true
        elseif kind=='OrbitalAbilityComponentData'then needed.entity=true
        elseif kind=='HealthComponentData' or kind=='WeaponDataComponentData'
            or kind=='WeaponMagazineComponentData' or kind=='WeaponRoundsComponentData'
            or kind=='WeaponHeatComponentData' or kind=='WeaponChargeComponentData'
            or kind=='ArcWeaponComponentData' or kind=='BeamWeaponComponentData'
            or kind=='SprayWeaponComponentData' or kind=='ShieldComponentData'
            or kind=='HellpodPayloadComponentData' or change.descriptor.backing.component then needed.entity=true end
    end
    if spec.target_path=='shield' or spec.target_path=='damage_zone' or spec.target_path=='turret'
        or spec.target_path=='targeting'then needed.entity=true end
    if GRAPH_PATHS[spec.target_path]then
        needed.entity=true;needed.projectile=true;needed.damage=true
        needed.explosion=true;needed.status='optional';needed.arc='optional';needed.beam='optional'
    end
    return needed
end
function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local needed={};for _,spec in ipairs(specs)do for key,value in pairs(collect_needs(spec))do
        if value==true or needed[key]==nil then needed[key]=value end end end
    local roots=next(needed)and discover.locate(runtime,reader,profile,needed)or{}
    local records,stratagem_owner=Stratagem.capture_all(runtime,reader,profile)
    local catalog=needed.entity and entities.capture(reader,roots.entity,profile,component_names)or nil
    local results={}
    for index,spec in ipairs(specs)do
        local entry=assert(database.stratagems[spec.stratagem]);local root=find_root(records,entry.root)
        local component,candidate
        if ENTITY_PATHS[spec.target_path]then
            candidate=find_candidate(catalog,entry.rootLink and entry.rootLink.payload
                or entry.deployedEntity.resource)
            if entry.rootLink then
                component=catalog.record(candidate,entry.rootLink.component)
                assert(component.identity.recordIndex==entry.rootLink.recordIndex
                    and component.identity.indexRow==entry.rootLink.indexRow,
                    'payload component ownership changed')
            end
            if entry.rootComponentLink then
                -- A deployer component names the graph's first settings row (a mine deployer's explosion).
                local link=entry.rootComponentLink
                local record=catalog.record(candidate,link.component)
                assert(record.identity.recordIndex==link.recordIndex and record.identity.indexRow==link.indexRow,
                    'deployer '..link.component..' ownership changed')
                assert(b.u32(record.bytes,link.offset)==link.expect,
                    'deployer '..link.component..'+'..link.offset..' link changed')
                local node
                for _,item in ipairs(entry.graph or{})do if item.path==link.node then node=item end end
                assert(node and node.recordType==link.expect,'deployer root node changed')
            end
            if GRAPH_PATHS[spec.target_path] and entry.graph and #entry.graph>0 then
                validate_graph(entry,roots,component)end
        end
        results[index]={entry=entry,root=root,stratagem_owner=stratagem_owner,roots=roots,
            catalog=catalog,candidate=candidate,component=component,records=records}
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

local function selected_record(resolved,change,spec)
    local backing=change.descriptor.backing
    if backing.kind=='StratagemDefinition'then
        local entry=resolved.entry
        local reviewed=entry.root
        if spec.target_path=='eagle_rearm'then
            reviewed=database.eagleRearm.currentRoot
        end
        local record=find_root(resolved.records,reviewed)
        return {bytes=record.bytes or resolved.stratagem_owner and nil,offset=record.offset,
            owner=resolved.stratagem_owner,kind=record.record_kind,group=record.group,row=record.row}
    end
    if backing.component then
        local component=resolved.catalog.record(resolved.candidate,backing.component)
        assert(component.identity.recordIndex==backing.recordIndex
            and component.identity.indexRow==backing.indexRow,
            'deployed component ownership changed')
        assert(backing.ownerCount==nil or component.identity.ownerCount==backing.ownerCount,
            'deployed component consumer scope changed')
        assert(backing.uniqueOwner==nil or component.identity.uniqueOwner==backing.uniqueOwner,
            'deployed component uniqueness changed')
        return component
    end
    if backing.kind=='OrbitalAbilityComponentData'then return resolved.component end
    local kind={ProjectileSettings='projectile',DamageInfo='damage',ExplosionSettings='explosion',
        StatusEffectSettings='status',ArcSettings='arc',BeamSettings='beam'}
    local root=assert(resolved.roots[kind[backing.kind]],'settings allocation absent')
    local record=assert(root.records[backing.nativeIdentity],'settings record absent')
    assert(record.group==backing.group and record.row==backing.row and record.kind==backing.nativeIdentity,
        'settings record identity changed')
    return record,root.owner
end
function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots};local physical={}
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        local record,owner=selected_record(resolved,change,spec)
        owner=owner or record.owner
        local bytes=record.bytes
        if backing.kind=='StratagemDefinition'then
            -- capture_all validates the whole allocation; reread only this reviewed row for write planning.
            -- Not captured again: the full-table snapshot from capture_all is the guarded
            -- transaction context, and a second overlapping context makes apply ambiguous.
            bytes=reader.read(owner,record.offset,profile.stratagem.stride)
            record={bytes=bytes,offset=record.offset}
        end
        assert(backing.offset+backing.width<=#record.bytes,'field outside reviewed record')
        local current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
        local expected=ownership.expected(change,current)
        local offset=record.offset+backing.offset
        local key=tostring(owner.base)..':'..tostring(offset)..':'..backing.width
        local prior=physical[key]
        if prior then
            assert(prior.canonical_field==change.canonical_field and prior.desired==change.desired,
                'overlapping stratagem fields conflict')
        else
            local item={label=change.field,canonical_field=change.canonical_field,
                semantic_aliases={change.field},owner=owner,offset=offset,field_offset=backing.offset,
                expected=expected,desired=change.desired,before=current,
                already_desired=current==change.desired,expect=change.expect,value=change.value,
                identity={component=backing.kind,component_type='semantic',record_index=backing.recordIndex or backing.row,
                    unique_owner=backing.uniqueOwner~=nil and backing.uniqueOwner
                        or not change.descriptor.shared,
                    owner_count=backing.ownerCount or#change.descriptor.sharedConsumers,
                    scope=change.descriptor.sharedScopeKey},
                chain={}}
            physical[key]=item;plan.changes[#plan.changes+1]=item
        end
    end
    return plan
end
return M
