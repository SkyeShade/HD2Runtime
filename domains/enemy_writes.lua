-- Guarded enemy and enemy-structure authoring. Each class is a hash-verified native entity.
-- Health and damage zones: its HealthComponent record identity (record, index row, owner count) is re-proven before
-- every write. Attacks: the DamageInfo row a mounted weapon reaches; the whole chain (class MountComponent slot ->
-- weapon entity -> its weapon component -> projectile / explosion settings -> DamageInfo) is re-proven live before
-- every write. Whole-body gib threshold (gore.whole_body_gib_damage): the class's own GoreComponent record (unique
-- owner) and its first whole-body gore group: the record identity, the group's actor list and flags (+866 set) and
-- every earlier group's cleared +866 are re-proven before every write, so it never lands on a limb group.
-- Field descriptors are built from the compact generated database (domains/enemy_authoring.lua).
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/enemy_authoring')
local M={}
local component_names={'HealthComponentData','MountComponentData','ProjectileWeaponComponentData',
    'SprayWeaponComponentData','GoreComponentData'}

local function equal(a,c,storage)
    if storage=='f32'then return type(a)=='number'and type(c)=='number'
        and math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64
        and not value:find('[^%w_%-]'),'invalid operation id')
end
function M.entry(name)
    local canonical=database.enemies[name]and name or database.aliases[name]
    return canonical and database.enemies[canonical]or nil
end
function M.attack(entry,id)
    for _,attack in ipairs(entry.attacks or{})do if attack.id==id then return attack end end
end
local function entry_for(target)
    assert(type(target)=='table'and target.resource=='enemy','unsupported enemy target')
    local entry=assert(type(target.enemy)=='string'and database.enemies[target.enemy],
        'unknown reviewed enemy: '..tostring(target.enemy))
    if target.path=='damage_zone'then
        assert(type(rawget(target,'zone'))=='string','damage zone identity required')
    elseif target.path=='attack'then
        assert(type(rawget(target,'attack'))=='string'and M.attack(entry,rawget(target,'attack')),
            'reviewed enemy attack identity required')
    else assert(target.path=='entity','unsupported enemy target path')end
    for key in pairs(target)do assert(key=='resource'or key=='enemy'or key=='path'or key=='zone'or key=='attack',
        'unsupported enemy target identity')end
    return entry
end
local HEALTH_UNVERIFIED='The HealthComponent member is identified by its hidden member-name length and exact '
    ..'agreement with the wiki anatomy tables; its gameplay effect on enemies is not yet live-confirmed.'
local ATTACK_UNVERIFIED='The DamageInfo row is reached through this class\'s own mount chain (re-proven before '
    ..'every write); a change to an enemy attack is not yet live-confirmed.'
-- The generated entry plus the field schema as one descriptor.
function M.descriptor(entry,field)
    local schema=assert(database.schema[field.id],'field schema missing: '..field.id)
    local backing={}
    if field.backing.kind~='settings'then
        backing={component=entry.health.component,resource=entry.resource,
            recordIndex=entry.health.recordIndex,indexRow=entry.health.indexRow,ownerCount=entry.health.ownerCount,
            uniqueOwner=entry.health.uniqueOwner}
    end
    for key,value in pairs(field.backing)do backing[key]=value end
    local attack=field.attack and M.attack(entry,field.attack)
    local acknowledgement=schema.acknowledgement
    local reason=schema.acknowledgement and(schema.acknowledgementReason
        or(attack and ATTACK_UNVERIFIED or HEALTH_UNVERIFIED))or nil
    -- Structure health: offline-proven only until a structure live test passes (sdk/LiveEvidenceCatalog.json).
    local gate=database.structureAcknowledgement
    if entry.kind=='structure'and not acknowledgement and gate then
        for _,id in ipairs(gate.fields)do
            if id==field.id then acknowledgement='allow_unverified_effect';reason=gate.reason end
        end
    end
    return {semanticFieldId=field.id,type=schema.type,currentDefault=field.currentDefault,editable=field.editable~=false,
        reason=field.reason,target={resource='enemy',enemy=entry.name,path=field.path,zone=field.zone,
            attack=field.attack},
        backing=backing,shared=schema.shared==true or backing.uniqueOwner==false,min=schema.min,max=schema.max,
        disabledValue=schema.disabledValue,
        acknowledgement=acknowledgement,
        sharedWithClasses=attack and attack.reviewedClassesReachingRow or nil,
        acknowledgementReason=reason,
        operationGroup=entry.semanticId..'/'..tostring(field.path)..'/'..tostring(field.zone or field.attack)}
end
local function find_field(entry,target,id)
    for _,field in ipairs(entry.fields)do
        if field.id==id and field.path==target.path and field.zone==rawget(target,'zone')
            and field.attack==rawget(target,'attack')then
            return M.descriptor(entry,field)
        end
    end
    if id=='standard_damage'or id=='durable_damage'then
        error('field '..id..' is a legacy fixed-resource field; use hd2.fields.damage.player_'..id..' on enemy attacks',0)
    end
    error('field is not exposed for '..entry.name..': '..tostring(id),0)
end
local function validate_change(entry,target,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=find_field(entry,target,item.field)
    assert(field.editable,'field is read-only: '..item.field..' ('..tostring(field.reason)..')')
    assert(not field.shared or request.allow_shared==true,'shared field requires allow_shared=true: '..item.field)
    assert(field.acknowledgement~='allow_unverified_effect'or request.allow_unverified_effect==true,
        'field requires allow_unverified_effect=true: '..item.field..' ('..tostring(field.acknowledgementReason)..')')
    local storage=field.backing.storage
    local expected,desired=item.expect,item.value
    assert(type(expected)=='number'and expected==expected and expected>-math.huge and expected<math.huge,
        'expect must be a finite number')
    assert(type(desired)=='number'and desired==desired and desired>-math.huge and desired<math.huge,
        'value must be a finite number')
    if field.type=='integer'then
        assert(expected%1==0 and desired%1==0,'integer enemy field requires integer values')
    end
    assert(equal(expected,field.currentDefault,storage),'expect differs from reviewed current value for '..item.field)
    if field.disabledValue~=nil then
        -- A disable sentinel (-1 for the whole-body gib threshold) or a positive value up to the reviewed maximum.
        assert(desired==field.disabledValue or(desired>0 and desired<=field.max),
            'value outside the reviewed range for '..item.field..' ('..field.disabledValue..' to disable, or above 0 '
            ..'up to '..field.max..')')
    else
        assert(desired>=field.min and desired<=field.max,
            'value outside the reviewed range for '..item.field..' ('..field.min..' to '..field.max..')')
    end
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
        expected=b.encode(expected,storage),desired=b.encode(desired,storage),expect=expected,value=desired}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local entry=entry_for(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=32,'transaction requires one to 32 changes')
    local result={kind='enemy',id=request.id,enemy=entry.name,target_path=request.target.path,
        attack=rawget(request.target,'attack'),
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,
        allow_unverified_effect=request.allow_unverified_effect==true,changes={}}
    for index,item in ipairs(items)do
        result.changes[index]=validate_change(entry,request.target,item,request)
    end
    result.field=request.field;result.expect=request.expect;result.value=request.value
    return result
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

local function find_candidate(catalog,resource,row,label)
    local found
    for _,candidate in ipairs(catalog.candidates)do if candidate.resourceHash==resource then
        assert(not found,label..' identity ambiguous');found=candidate end end
    assert(found and found.entityRow and#found.diagnostics==0,'reviewed '..label..' identity absent')
    assert(row==nil or found.entityRow==row,label..' owner row changed')
    return found
end
local function component_record(catalog,candidate,reviewed,label)
    local record=catalog.record(candidate,reviewed.component)
    assert(record.identity.recordIndex==reviewed.recordIndex and record.identity.indexRow==reviewed.indexRow,
        label..' '..reviewed.component..' ownership changed')
    assert(record.identity.ownerCount==reviewed.ownerCount,label..' '..reviewed.component..' consumer scope changed')
    return record
end
local function settings_record(roots,kind,record_type,group,row)
    local root=assert(roots[kind],kind..' settings allocation absent')
    local record=assert(root.records[record_type],'reviewed '..kind..' settings row absent')
    assert(record.kind==record_type and(group==nil or record.group==group)and(row==nil or record.row==row),
        kind..' settings identity changed')
    return record,root.owner
end
-- Class -> mount slot -> weapon entity -> weapon component -> settings links, all re-read live.
local function prove_attack(resolved,attack)
    local entry=resolved.entry
    local mount=component_record(resolved.catalog,resolved.candidate,entry.mount,entry.name)
    assert(b.resource(mount.bytes,attack.mount.offset)==attack.mount.expect,
        entry.name..' mount slot '..attack.slot..' no longer holds the reviewed weapon')
    local weapon=find_candidate(resolved.catalog,attack.weapon.resource,attack.weapon.entityRow,'mounted weapon')
    local weapon_record=component_record(resolved.catalog,weapon,attack.weapon,'mounted weapon')
    for _,link in ipairs(attack.links)do
        local bytes=link.from=='weapon'and weapon_record.bytes
            or settings_record(resolved.roots,link.settings,link.recordType).bytes
        assert(b.u32(bytes,link.offset)==link.expect,'enemy attack native link changed ('
            ..(link.component or link.settings)..'+'..link.offset..')')
    end
end
function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local needed={entity=true}
    for _,spec in ipairs(specs)do
        if spec.target_path=='attack'then needed.projectile=true;needed.explosion=true;needed.damage=true end
    end
    local roots=discover.locate(runtime,reader,profile,needed)
    local catalog=entities.capture(reader,roots.entity,profile,component_names)
    local results={}
    for index,spec in ipairs(specs)do
        local entry=assert(database.enemies[spec.enemy],'reviewed enemy entry absent')
        local resolved={entry=entry,catalog=catalog,roots=roots,
            candidate=find_candidate(catalog,entry.resource,entry.entityRow,'enemy')}
        if spec.target_path=='attack'then prove_attack(resolved,assert(M.attack(entry,spec.attack)))end
        results[index]=resolved
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots};local physical={}
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        local record,owner
        if backing.kind=='settings'then
            record,owner=settings_record(resolved.roots,backing.settings,backing.recordType,backing.group,backing.row)
        else
            record=resolved.catalog.record(resolved.candidate,backing.component)
            local label=backing.component=='GoreComponentData'and'gore'or'health'
            assert(record.identity.recordIndex==backing.recordIndex
                and record.identity.indexRow==backing.indexRow,'enemy '..label..' record ownership changed')
            assert(record.identity.ownerCount==backing.ownerCount
                and record.identity.uniqueOwner==backing.uniqueOwner,'enemy '..label..' record consumer scope changed')
            if backing.goreGroup~=nil then
                -- The whole-body group: its index, actor list, flags (+866 set) and every earlier group's cleared
                -- +866 are re-read live; the target is that group's threshold (+0).
                assert(backing.uniqueOwner==true and backing.offset==backing.goreGroup*872,
                    'gore threshold is not a whole-body group threshold')
                assert(#(backing.guards or{})>=2,'gore group identity guards missing')
            end
            for _,guard in ipairs(backing.guards or{})do
                local expected=b.unhex(guard.hex)
                assert(record.bytes:sub(guard.offset+1,guard.offset+#expected)==expected,
                    'enemy '..tostring(backing.component)..' identity changed ('..change.field..' guard at +'
                    ..guard.offset..')')
            end
            owner=record.owner
        end
        assert(backing.offset+backing.width<=#record.bytes,'field outside reviewed record')
        local current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
        local expected=ownership.expected(change,current)
        local offset=record.offset+backing.offset
        local key=tostring(owner.base)..':'..tostring(offset)..':'..backing.width
        local prior=physical[key]
        if prior then
            assert(prior.canonical_field==change.canonical_field and prior.desired==change.desired,
                'overlapping enemy fields conflict')
        else
            local item={label=change.field,canonical_field=change.canonical_field,
                semantic_aliases={change.field},owner=owner,offset=offset,field_offset=backing.offset,
                expected=expected,desired=change.desired,before=current,
                already_desired=current==change.desired,expect=change.expect,value=change.value,
                identity={component=backing.component or backing.settings,component_type='semantic',
                    record_index=backing.recordIndex or backing.row,unique_owner=not change.descriptor.shared,
                    owner_count=backing.ownerCount or 0,scope=change.descriptor.operationGroup},
                chain={}}
            physical[key]=item;plan.changes[#plan.changes+1]=item
        end
    end
    return plan
end
return M
