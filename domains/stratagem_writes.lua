-- Guarded stratagem definition and offensive payload authoring.
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local Stratagem=require('hd2runtime/core/stratagem')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/stratagem_authoring')
local calldown=require('hd2runtime/runtime/calldown_codes')
local calldown_domain=require('hd2runtime/domains/stratagem_calldown')
local presentation=require('hd2runtime/runtime/stratagem_presentation')
local images=require('hd2runtime/runtime/image_resources')
local texts=require('hd2runtime/runtime/text_resources')
local M={}
local component_names={'BombardmentComponentData','EagleComponentData',
    'ProjectileWeaponComponentData','OrbitalAbilityComponentData',
    'HealthComponentData','WeaponDataComponentData','WeaponMagazineComponentData',
    'WeaponRoundsComponentData','WeaponHeatComponentData','WeaponChargeComponentData',
    'ArcWeaponComponentData','BeamWeaponComponentData','SprayWeaponComponentData',
    'ShieldComponentData','HellpodPayloadComponentData','MinefieldComponentData',
    'TurretComponentData','SensorEyeComponentData','ThrowerComponentData','WeaponWindUpComponentData'}
local ENTITY_PATHS={deployed_entity=true,weapon=true,attack=true,shield=true,damage_zone=true,
    turret=true,targeting=true,minefield=true}
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
        or target.path=='targeting' or target.path=='minefield'then
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
-- The calldown code (StratagemInfo +0x40 pointer, +0x48 count; runtime/calldown_codes.lua): a list of 1 to 9
-- directions. expect must be the reviewed native code. A code equal to another stratagem's native code needs
-- allow_unverified_effect: how the game chooses between two equal codes is not proven. The bytes are planned in
-- prepare (a Runtime-owned array per code); expected/desired carry the codes so ensures can compare them.
local catalogued_by_id
local function stratagem_name(id)
    if not catalogued_by_id then
        catalogued_by_id={}
        for name,item in pairs(database.stratagems)do
            if item.root and item.root.id then catalogued_by_id[item.root.id]=name end
        end
    end
    return catalogued_by_id[id]or('StratagemInfo id '..id)
end
local function validate_calldown(entry,field,item,allow_unverified_effect)
    local expect,why=calldown.values(item.expect,'expect')
    assert(expect,why)
    local value;value,why=calldown.values(item.value,'value')
    assert(value,why)
    local native=assert(calldown.values(field.currentDefault),'the reviewed calldown baseline is missing')
    assert(calldown.same(expect,native),'expect differs from reviewed current value for '..item.field)
    if not calldown.same(value,expect)then
        local equal={}
        for id,code in pairs(calldown_domain.nativeCodes)do
            if tonumber(id)~=entry.root.id and calldown.same(code,value)then equal[#equal+1]=stratagem_name(tonumber(id))end
        end
        table.sort(equal)
        assert(#equal==0 or allow_unverified_effect,'calldown code '..calldown.text(value)..' equals the native code of '
            ..table.concat(equal,', ')..'; which stratagem the game calls for two equal codes is not proven, so it '
            ..'requires allow_unverified_effect=true: '..item.field)
    end
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
        calldown={expect=expect,value=value},expected='calldown:'..calldown.key(expect),
        desired='calldown:'..calldown.key(value),expect=item.expect,value=item.value}
end
-- Presentation (StratagemInfo name, cased name, description, icon; runtime/stratagem_presentation.lua): a value is a
-- catalogued stratagem, by name or hd2.stratagem(name), and stands for that stratagem's own reviewed value of the same
-- member, an existing vanilla resource. The field's own stratagem is its native value. Raw localization ids and image
-- hashes are not accepted. expected/desired are the exact row bytes.
--
-- presentation_icon also takes a mod's own icon, hd2.resources.image(id) (docs/custom-images.md): the complete icon
-- family the SDK builds from images/<id>.png (a texture and its GUI icon material). A stratagem icon value names a GUI
-- material as well as its pixels, and the loadout grid draws the icon as that material with no fallback, so a texture
-- alone crashed the game (CustomStratagemP0Proof 0.9.0) and the complete family draws (0.11.0, live-proven). Before
-- the write every +0xB0 consumer is proven and the family must be loaded and exact as the game reads it
-- (image_resources.icon_ready); otherwise nothing is written (ASSET_UNAVAILABLE). Custom images are icons only. Custom
-- text (runtime/text_resources.lua) is refused until its live proof.
local function presentation_source(value,label,member)
    -- Runtime-owned text (runtime/text_resources.lua) is a development capability until its live proof.
    assert(not texts.issued(value),'custom text is not yet a public presentation value: it waits for its live proof '
        ..'(docs/custom-text.md)')
    if images.issued(value)then
        assert(label=='value','expect must be the stratagem itself (its native value), not a custom image')
        assert(member=='icon','a custom image is a presentation_icon value only: '..tostring(value))
        return nil,nil,value
    end
    local name=value
    if type(value)=='table'then
        assert(rawget(value,'resource')=='stratagem'and(rawget(value,'path')==nil or rawget(value,'path')=='stratagem'),
            label..' must be a catalogued stratagem name or hd2.stratagem(name)'
            ..(member=='icon'and label=='value'and', or hd2.resources.image(id)'or''))
        name=rawget(value,'stratagem')
    end
    assert(type(name)=='string',label..' must be the name of a catalogued stratagem (raw localization ids and image '
        ..'hashes are not accepted)')
    local source=database.stratagems[name]
    assert(source and source.root and source.root.id,label..' '..name..' is not a catalogued stratagem')
    return name,source.root.id
end
local function validate_presentation(field,item)
    local member=field.backing.member
    local expect,expect_id=presentation_source(item.expect,'expect',member)
    assert(expect==field.currentDefault,'expect differs from reviewed current value for '..item.field
        ..' (its native value is its own: '..tostring(field.currentDefault)..')')
    local expected=presentation.reviewed(expect_id,member)
    assert(expected,'no reviewed presentation for '..expect)
    local value,value_id,image=presentation_source(item.value,'value',member)
    if image then
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,presentation=member,
            image=image,expected=expected,desired=images.bytes(image),expect=expect,value=image}
    end
    assert(value==expect or not presentation.unresolved(value_id,member),'value '..value..' cannot be a source for '
        ..item.field..': its '..member..' does not resolve to displayed text on this build')
    local desired=presentation.reviewed(value_id,member)
    assert(desired,'no reviewed presentation for '..value)
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,presentation=member,
        expected=expected,desired=desired,expect=expect,value=value}
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
    if field.type=='calldown_code'then return validate_calldown(entry,field,item,allow_unverified_effect)end
    if field.type=='stratagem_presentation'then return validate_presentation(field,item)end
    assert(field.acknowledgement~='allow_unverified_effect'or allow_unverified_effect,
        'field requires allow_unverified_effect=true: '..item.field..' ('..tostring(field.acknowledgementReason)..')')
    local expected=item.expect;local desired=item.value
    if field.type=='enum'then
        -- An enumerated member (stratagem.rearm_pool) also takes its reviewed value names ('none', 'eagle_rearm').
        local function named(value)
            if type(value)~='string'then return value end
            for _,option in ipairs(field.allowedValues or{})do if option.name==value then return option.value end end
            error('unknown value name for '..item.field..': '..value,0)
        end
        expected,desired=named(expected),named(desired)
    end
    assert(type(expected)=='number'and expected==expected and expected>-math.huge and expected<math.huge,
        'expect must be a finite number')
    assert(type(desired)=='number'and desired==desired and desired>-math.huge and desired<math.huge,
        'value must be a finite number')
    if field.type=='integer'then
        assert(expected%1==0 and desired%1==0,'integer stratagem field requires integer values')
    end
    assert(equal(expected,field.currentDefault,field.backing.storage),
        'expect differs from reviewed current value for '..item.field)
    -- A reviewed sentinel (targeting.side_range / rear_range: -1 = use targeting.range) is accepted besides the range.
    local sentinel=false
    for _,option in ipairs(field.sentinelValues or{})do if option.value==desired then sentinel=true end end
    if field.min and not sentinel then
        assert(desired>=field.min and desired<=field.max,
            'value outside the reviewed range for '..item.field..' ('..field.min..' to '..field.max
            ..(field.sentinelValues and', or '..field.sentinelValues[1].value or'')..')')
    end
    if field.allowedValues then
        -- An enumerated field (eagle.airstrike_pattern): only the reviewed values, never a neighbour of them.
        local allowed=false
        for _,option in ipairs(field.allowedValues)do if option.value==desired then allowed=true end end
        assert(allowed,'value is not one of the reviewed values of '..item.field..': '..tostring(desired))
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
-- The graph nodes a spec's changes reach, and every node on the way there from the root: the links a write depends on
-- (0.30.4). A settings row is located by its own identity (selected_record: group, row and kind), never through these
-- links; the links prove that this stratagem's graph reaches the row the reviewed way. So a write is checked against
-- the chain from the root to its own node (every consumer path of its row in this stratagem), and a link elsewhere in
-- the graph that another mod changed refuses only the values below that link. A component-backed change (turret,
-- weapon, shield records: located and proven through the entity catalogue) needs no graph link. nil (check every
-- link, as before) when a settings change names no path of this stratagem.
local SETTINGS_KINDS={ProjectileSettings=true,DamageInfo=true,ExplosionSettings=true,StatusEffectSettings=true,
    ArcSettings=true,BeamSettings=true}
local function graph_paths(entry,spec)
    local needed={}
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        if SETTINGS_KINDS[backing.kind]then
            local found=false
            for _,consumer in ipairs(backing.consumers or{})do
                if consumer.stratagem==entry.name and type(consumer.path)=='string'then
                    found=true
                    local prefix
                    for part in consumer.path:gmatch('[^/]+')do
                        prefix=prefix and(prefix..'/'..part)or part
                        needed[prefix]=true
                    end
                end
            end
            if not found then return nil end
        end
    end
    return needed
end
M.graph_paths=graph_paths
local function validate_graph(entry,roots,component,needed)
    local nodes={};for _,node in ipairs(entry.graph or{})do nodes[node.path]=node end
    -- needed: the node paths to check (graph_paths); nil checks every node and link
    local function checked(path)return needed==nil or needed[path]==true end
    local function child_of(path)return checked(path)and nodes[path]or nil end
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
        local record=checked(node.path)and graph_record(roots,node)
        if record then
            if node.kind=='ProjectileSettings'then
                local child=child_of(node.path..'/damage');if child then
                    assert(b.u32(record.bytes,60)==child.recordType,'projectile damage link changed')end
                for _,phase in ipairs({'impact','expiry'})do child=child_of(node.path..'/'..phase)
                    if child then assert(b.u32(record.bytes,phase=='impact'and 144 or 156)==child.recordType,
                        'projectile explosion link changed')end end
            elseif node.kind=='ExplosionSettings'then
                local child=child_of(node.path..'/damage');if child then
                    assert(b.u32(record.bytes,4)==child.recordType,'explosion damage link changed')end
                child=child_of(node.path..'/shrapnel');if child then
                    assert(b.u32(record.bytes,84)==child.recordType,'explosion shrapnel link changed')end
            elseif node.kind=='DamageInfo'then
                for slot=1,4 do local child=child_of(node.path..'/status:'..slot)
                    if child then assert(b.u32(record.bytes,44+(slot-1)*8)==child.recordType,
                        'damage status link changed')end end
            elseif node.kind=='ArcSettings'then
                local child=child_of(node.path..'/damage');if child then
                    assert(b.u32(record.bytes,36)==child.recordType,'arc damage link changed')end
            elseif node.kind=='BeamSettings'then
                local child=child_of(node.path..'/damage');if child then
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
        or spec.target_path=='targeting' or spec.target_path=='minefield'then needed.entity=true end
    if GRAPH_PATHS[spec.target_path]then
        needed.entity=true;needed.projectile=true;needed.damage=true
        needed.explosion=true;needed.status='optional';needed.arc='optional';needed.beam='optional'
    end
    return needed
end
-- A change backed by a component of the stratagem's own payload entity on the stratagem target itself (the Eagle
-- fields: EagleComponentData of the Eagle's jet, payload[0]) resolves that entity like an entity path does.
local function component_backed(spec)
    for _,change in ipairs(spec.changes)do if change.descriptor.backing.component then return true end end
    return false
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
        if ENTITY_PATHS[spec.target_path]or(spec.target_path=='stratagem'and entry.rootLink and component_backed(spec))then
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
                validate_graph(entry,roots,component,graph_paths(entry,spec))end
        end
        results[index]={entry=entry,root=root,stratagem_owner=stratagem_owner,roots=roots,
            catalog=catalog,candidate=candidate,component=component,records=records,runtime=runtime}
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
        -- Members the Runtime never writes that prove the record still is the reviewed one (an Eagle jet's attack
        -- kind), re-proven before every write.
        for _,proof in ipairs(backing.recordProofs or{})do
            assert(component.bytes:sub(proof.offset+1,proof.offset+4)==b.encode(proof.value,proof.storage),
                backing.component..' '..tostring(proof.member)..' (+'..proof.offset..') is no longer the reviewed '
                ..tostring(proof.value))
        end
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
-- The calldown code's two physical changes (runtime/calldown_codes.lua): the row's count (+0x48) and pointer (+0x40),
-- to the native array or to the Runtime-owned array of the desired code. The row must hold the expected (native) code,
-- the desired code, or the code this same operation wrote last time (an option-bound ensure's own bytes); anything
-- else is a conflict. Count first when the count does not grow, pointer first when it does, so the applied order never
-- describes more directions than the array it points to holds (every Runtime array has room for any count).
local SEQUENCE,COUNT,PADDING=calldown_domain.row.sequence,calldown_domain.row.count,calldown_domain.row.padding
local function u32(n)return b.encode(n,'u32')end
local function u64(n)return u32(n%4294967296)..u32(math.floor(n/4294967296))end
local function prepare_calldown(plan,physical,resolved,reader,change,owner,record)
    local bytes,label,entry=record.bytes,change.field,resolved.entry
    local proven,why=calldown.prove(resolved.runtime)
    assert(proven,'calldown code unavailable on this game build: '..tostring(why))
    assert(b.u32(bytes,PADDING)==0,'calldown row padding changed: '..label)
    local pointer,count=b.pointer(bytes,SEQUENCE),b.u32(bytes,COUNT)
    local address=owner.base+record.offset
    local native=calldown.native(address)
    local current=calldown.owned(pointer,count)
    if current then
        assert(native,'CONFLICT: '..label..' points to a Runtime array no calldown write planned for this row')
    else
        assert(count>=1 and count<=calldown_domain.maxLength and pointer>=owner.base+16
            and pointer+count*4<=owner.base+owner.size,
            'CONFLICT: '..label..' points outside the StratagemSettings allocation and outside Runtime')
        current=calldown.decode(reader.read(owner,pointer-owner.base,count*4))
        if native then
            assert(pointer==native.pointer and count==native.count,'CONFLICT: '..label..' native array moved')
        else
            native={pointer=pointer,count=count,values=current}
        end
    end
    local expect,wanted=change.calldown.expect,change.calldown.value
    assert(calldown.same(native.values,expect),'CONFLICT: '..label..' native code is '..calldown.text(native.values)
        ..', not the reviewed '..calldown.text(expect))
    local mine=change.owned=='calldown:'..calldown.key(current)
    if not(calldown.same(current,expect)or calldown.same(current,wanted)or mine)then
        error('CONFLICT: '..label..' is '..calldown.text(current)..', neither expected ('..calldown.text(expect)
            ..') nor desired ('..calldown.text(wanted)..')',0)
    end
    local desired_pointer,desired_count=native.pointer,native.count
    if not calldown.same(wanted,native.values)then
        desired_pointer,desired_count=calldown.array(resolved.runtime,wanted),#wanted
    end
    calldown.planned({address=address,id=entry.root.id,type=b.u32(bytes,0),name=entry.name,owner=owner,
        offset=record.offset,native=native,values=wanted})
    local parts={count={offset=COUNT,before=u32(count),desired=u32(desired_count),native=u32(native.count)},
        sequence={offset=SEQUENCE,before=u64(pointer),desired=u64(desired_pointer),native=u64(native.pointer)}}
    local order=desired_count>count and{'sequence','count'}or{'count','sequence'}
    for _,name in ipairs(order)do
        local part=parts[name]
        local key=tostring(owner.base)..':'..tostring(record.offset+part.offset)..':'..#part.before
        assert(not physical[key],'overlapping calldown changes conflict')
        -- Expected: the native bytes, or what is there now when it is this operation's own earlier code.
        local expected=(calldown.same(current,expect)or mine)and part.before or part.native
        local item={label=label..'.'..name,canonical_field=change.canonical_field,semantic_aliases={change.field},
            owner=owner,offset=record.offset+part.offset,field_offset=part.offset,expected=expected,
            desired=part.desired,before=part.before,already_desired=part.before==part.desired,expect=change.expect,
            value=change.value,identity={component='StratagemDefinition',component_type='semantic',
                record_index=change.descriptor.backing.recordIndex or change.descriptor.backing.row,unique_owner=true,
                owner_count=#change.descriptor.sharedConsumers,scope=change.descriptor.sharedScopeKey},chain={}}
        physical[key]=item;plan.changes[#plan.changes+1]=item
    end
end
local function prepare_scalar(plan,physical,change,owner,record,backing)
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
-- The Eagle Rearm pool (stratagem.rearm_pool, StratagemInfo +200 = 49; research/stratagem-rearm-pool): the automatic
-- rearm waits until every pool member has 0 uses left (0x66E580), and an unlimited count (0xFFFFFFFF, -1 in the
-- mission record) never does. So a row in the pool keeps a finite use count after the operation: joining checks the
-- row's uses (or the same operation's max_uses), and an unlimited max_uses is refused while the row is in the pool.
local UNLIMITED_USES,EAGLE_REARM=4294967295,49
local function check_rearm_pool(resolved,spec,rows)
    local pool,uses={},{}
    for _,change in ipairs(spec.changes)do
        local id=change.descriptor.semanticFieldId
        if id=='stratagem.rearm_pool'then pool.value=b.u32(change.desired,0);pool.change=change end
        if id=='stratagem.max_uses'then uses.value=b.u32(change.desired,0)end
    end
    if pool.change==nil and uses.value~=UNLIMITED_USES then return end
    local row=rows[resolved.entry.root.id]
    if not row then return end
    local in_pool=pool.value or b.u32(row,200)
    local count=uses.value or b.u32(row,80)
    if in_pool==EAGLE_REARM and count==UNLIMITED_USES then
        error('REARM_POOL_UNLIMITED: '..resolved.entry.name..' in the Eagle Rearm pool needs a finite use count (its '
            ..'charges): an unlimited count never reaches 0 and would stop the automatic rearm of every Eagle; set '
            ..'stratagem.max_uses to a number in the same transaction',0)
    end
end
function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots};local physical={}
    local rows={}
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
            if spec.target_path=='stratagem'then rows[resolved.entry.root.id]=bytes end
        end
        if change.calldown then prepare_calldown(plan,physical,resolved,reader,change,owner,record)
        else
            if change.presentation then
                -- The readers of the member are proven on this game.dll before any presentation write.
                local proven,why=presentation.prove_runtime(resolved.runtime)
                assert(proven,'stratagem presentation unavailable on this game build: '..tostring(why))
            end
            if change.image then
                -- A custom icon: every +0xB0 consumer proven and the complete family loaded and exact, or nothing is
                -- written. The family loads with the mod at startup, so a missing one is final.
                local ready,code,why=images.icon_ready(resolved.runtime,change.image)
                if not ready then
                    error((code=='UNSUPPORTED_BUILD'and'custom icons are unavailable on this game build: '
                        or'ASSET_UNAVAILABLE: ')..tostring(change.image)..' is not ready as a stratagem icon ('
                        ..tostring(code)..': '..tostring(why)..')',0)
                end
            end
            prepare_scalar(plan,physical,change,owner,record,backing)
        end
    end
    check_rearm_pool(resolved,spec,rows)
    return plan
end
return M
