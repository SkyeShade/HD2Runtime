-- Guarded type-wide Helldiver fields (hd2.helldiver(); docs/helldiver-fields.md): movement speeds and stamina in the
-- avatar_helldiver AvatarComponentData record (record 0, the only owned row of a two-row table) and the six body zones
-- plus the default-zone explosion share in its HealthComponentData record (record 76). Source of truth:
-- research/avatar-fields-F5FEE03DCFDB.json, generated into domains/helldiver_fields.lua.
--
-- Both are TYPE records in the loaded (read-only) entity file: every Helldiver this machine simulates reads them, so
-- every write needs allow_shared, and no change is live-tested, so every write also needs allow_unverified_effect.
-- Before any memory is touched each write re-proves, on the live tables: the build the research covers, the entity
-- owner and its component membership (core/entity_catalog.lua), the record's index row, record index and single owner,
-- for a zone field the zone's name hash (+96), and the expected current bytes (core/ownership.lua: the reviewed vanilla
-- value or the desired one, anything else is a CONFLICT). The AvatarComponentData framing is not part of the runtime
-- profile; the generated table carries it and the catalog checks it exactly like a profile component.
--
-- Private copies. Every avatar reader resolves the record through 0x508DB0: an avatar spawned with an entity delta
-- carries a frozen private copy of the whole record (the ship's avatar always does) and reads that instead, so a type
-- write does not reach it; health zones read the override-aware record the same way, except damage_multiplier,
-- damage_multiplier_dps and the durable share, which every hit reads from the type record. Runtime never writes a
-- private copy: each write reports (a plan note, logged with the result) when a Helldiver this machine simulates holds
-- one, from the avatar manager's own maps, read-only, after the pinned layout is re-proven.
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/helldiver_fields')
local M={}
local NAME=database.name
M.ZONES={}
for _,zone in ipairs(database.zones)do M.ZONES[#M.ZONES+1]=zone.id end
local RECORDS={avatar=database.avatar,health=database.health}

-- The runtime profile plus the AvatarComponentData table framing (the entity catalog reads components by name).
local view_profile=setmetatable({components=setmetatable({[database.avatar.component]=database.avatar.layout},
    {__index=profile.components})},{__index=profile})

local function finite(value)return type(value)=='number'and value==value and value>-math.huge and value<math.huge end
local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64 and not value:find('[^%w_%-]'),'invalid operation id')
end
local zone_by_id={}
for _,zone in ipairs(database.zones)do zone_by_id[zone.id]=zone end
function M.zone(identity)
    if type(identity)=='number'then
        for _,zone in ipairs(database.zones)do if zone.index==identity then return zone end end
        return nil
    end
    return type(identity)=='string'and zone_by_id[identity]or nil
end
local function zone_list()return table.concat(M.ZONES,', ')end

-- One descriptor per field instance (cached: the same table for every request).
local descriptors={}
local function descriptor(field)
    local cached=descriptors[field]
    if cached then return cached end
    local record=RECORDS[field.record]
    local guards
    if field.zone then
        local zone=zone_by_id[field.zone]
        guards={{offset=database.zone.base+zone.index*database.zone.stride+database.zone.nameOffset,hex=zone.nameHash}}
    end
    cached={semanticFieldId=field.id,type=field.type,enum=field.enum,unit=field.unit,currentDefault=field.currentDefault,
        editable=true,min=field.min,max=field.max,grade=field.grade,lifecycle=field.lifecycle,reads=field.reads,
        copyReader=field.copyReader,semantics=field.semantics,
        allowedValues=field.enum and database.enums[field.enum]or nil,
        target={resource='helldiver',helldiver=NAME,path=field.path,zone=field.zone},
        backing={component=record.component,resource=database.resource,recordIndex=record.recordIndex,
            indexRow=record.indexRow,ownerCount=record.ownerCount,uniqueOwner=record.uniqueOwner,offset=field.offset,
            storage=field.storage,width=4,guards=guards},
        shared=true,allowSharedRequired=true,sharedReason=database.sharedReason,
        acknowledgement='allow_unverified_effect',acknowledgementReason=database.unverifiedReason,
        operationGroup='helldiver/'..field.record}
    descriptors[field]=cached
    return cached
end
M.descriptor=descriptor
-- The field instances of one path (and zone), in research order.
function M.fields(path,zone)
    local out={}
    for _,field in ipairs(database.fields)do
        if field.path==path and field.zone==zone then out[#out+1]=descriptor(field)end
    end
    return out
end
local function find_field(target,id)
    assert(type(id)=='string','field must be a field id (hd2.fields.helldiver.*, hd2.fields.zone.*)')
    for _,field in ipairs(database.fields)do
        if field.id==id and field.path==target.path and field.zone==rawget(target,'zone')then return descriptor(field)end
    end
    if target.path=='entity'and id:match('^zone%.')then
        error('field '..id..' is a damage zone field: use hd2.helldiver():zone(name) ('..zone_list()..')',0)
    end
    if target.path=='damage_zone'and not id:match('^zone%.')then
        error('field '..id..' is not a damage zone field: use hd2.helldiver()',0)
    end
    local zone=rawget(target,'zone')
    error('field is not exposed for the Helldiver'..(zone and(' zone '..zone)or'')..': '..id,0)
end
local function target_of(target)
    assert(type(target)=='table'and target.resource=='helldiver','unsupported Helldiver target (use hd2.helldiver())')
    for key in pairs(target)do
        assert(key=='resource'or key=='helldiver'or key=='path'or key=='zone','unsupported Helldiver target identity: '
            ..tostring(key))
    end
    assert(target.helldiver==nil or target.helldiver==NAME,'unknown Helldiver type: '..tostring(target.helldiver))
    if target.path=='damage_zone'then
        assert(type(rawget(target,'zone'))=='string'and zone_by_id[target.zone],
            'UNKNOWN_ZONE: unknown Helldiver damage zone: '..tostring(rawget(target,'zone'))..' ('..zone_list()..')')
    else
        assert(target.path=='entity'and rawget(target,'zone')==nil,'unsupported Helldiver target path: '
            ..tostring(target.path))
    end
    return target
end

-- An enum value by name ('none', 'critical', 'normal', 'reduced', 'symbolic'; for damage over time 'inherit' instead
-- of 'none'): the native value, or an error naming the accepted names.
local function enum_value(field,value,label)
    local names=field.allowedValues
    local ordered={}
    for name,native in pairs(names)do ordered[native+1]=name end
    local accepted=table.concat(ordered,', ')
    assert(type(value)=='string','UNKNOWN_DAMAGE_MULTIPLIER: '..field.semanticFieldId..' '..label
        ..' takes a name ('..accepted..'), not '..tostring(value))
    local native=names[value:lower()]
    if native==nil and field.enum=='damage_multiplier_dps'and value:lower()=='none'then
        error('UNKNOWN_DAMAGE_MULTIPLIER: '..field.semanticFieldId..' has no "none": its native 0 means "use '
            ..'zone.damage_multiplier" (name it "inherit"); to make a zone immune set zone.damage_multiplier to "none"',0)
    end
    assert(native~=nil,'UNKNOWN_DAMAGE_MULTIPLIER: '..field.semanticFieldId..' '..label..' '..value
        ..' is not one of '..accepted)
    return native,value:lower()
end
local function validate_change(target,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=find_field(target,item.field)
    assert(request.allow_shared==true,'shared field requires allow_shared=true: '..item.field..' ('..field.sharedReason
        ..')')
    assert(request.allow_unverified_effect==true,'field requires allow_unverified_effect=true: '..item.field..' ('
        ..field.acknowledgementReason..')')
    local storage=field.backing.storage
    local expected,desired,expect,value
    if field.type=='enum'then
        expected,expect=enum_value(field,item.expect,'expect')
        desired,value=enum_value(field,item.value,'value')
        assert(expect==field.currentDefault,'expect differs from the reviewed value of '..item.field..': declared='
            ..expect..' reviewed='..tostring(field.currentDefault))
    else
        assert(finite(item.expect),'expect must be a finite number')
        assert(finite(item.value),'value must be a finite number')
        if field.type=='integer'then
            assert(item.expect%1==0 and item.value%1==0,'integer Helldiver field requires integer values: '..item.field)
        end
        expect,value,expected,desired=item.expect,item.value,item.expect,item.value
        local same=storage=='f32'and math.abs(expect-field.currentDefault)<=math.max(0.000001,
            math.abs(field.currentDefault)*0.000001)or expect==field.currentDefault
        assert(same,'expect differs from the reviewed value of '..item.field..': declared='..tostring(expect)
            ..' reviewed='..tostring(field.currentDefault))
        assert(value>=field.min and value<=field.max,'value outside the reviewed range ['..field.min..', '..field.max
            ..'] for '..item.field)
    end
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,semantic_aliases={item.field},
        expected=b.encode(expected,storage),desired=b.encode(desired,storage),expect=expect,value=value}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local target=target_of(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=32,'transaction requires one to 32 changes')
    local result={kind='helldiver',id=request.id,helldiver=NAME,target_path=target.path,zone=rawget(target,'zone'),
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,
        allow_unverified_effect=request.allow_unverified_effect==true,changes={}}
    local seen={}
    for index,item in ipairs(items)do
        local change=validate_change(target,item,request)
        assert(not seen[change.field],'transaction lists '..change.field..' twice')
        seen[change.field]=true
        result.changes[index]=change
    end
    result.field=request.field;result.expect=request.expect;result.value=request.value
    return result
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

---------------------------------------------------------------------------------------------- resolution --
-- The components the specs touch, in a fixed order.
function M.names_for(specs)
    local wanted={}
    for _,spec in ipairs(specs)do
        for _,change in ipairs(spec.changes)do wanted[change.descriptor.backing.component]=true end
    end
    local names={}
    for _,name in ipairs({database.avatar.component,database.health.component})do
        if wanted[name]then names[#names+1]=name end
    end
    return names
end
function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    assert(database.source.gameDllSha256==profile.dll_sha,'HELLDIVER_BUILD_CHANGED: the Helldiver field research '
        ..'covers another game build than the runtime profile')
    local roots=discover.locate(runtime,reader,profile,{entity=true})
    local catalog=entities.capture(reader,roots.entity,view_profile,M.names_for(specs))
    local found
    for _,candidate in ipairs(catalog.candidates)do
        if candidate.resourceHash==database.resource then
            assert(not found,'Helldiver identity ambiguous');found=candidate
        end
    end
    assert(found and found.entityRow and#found.diagnostics==0,'reviewed Helldiver identity absent ('
        ..(found and table.concat(found.diagnostics,', ')or'no owner row')..')')
    local results={}
    for index in ipairs(specs)do results[index]={catalog=catalog,candidate=found}end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

------------------------------------------------------------------------------------------- private copies --
-- Read-only: which Helldivers this machine simulates and whether each carries a private AvatarComponentData or
-- HealthComponentData copy, from the avatar manager's own maps. {status='checked', simulated, avatars={{entity, type,
-- local, avatar_copy, health_copy}}} or {status='unavailable', reason}. Every pinned instruction of the layout is
-- re-proven first (once per loaded game.dll); nothing is written and no address is kept.
local P=database.privateCopies
local proven
local function prove(world)
    if proven and proven.key==world.key then return proven.ok,proven.why end
    local ok,why=true,nil
    for _,pin in ipairs(P.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            ok,why=false,('the avatar manager layout changed (%s at game+%X)'):format(pin.label,pin.rva)
            break
        end
    end
    proven={key=world.key,ok=ok,why=why}
    return ok,why
end
function M.reset_for_tests()proven=nil end
function M.private_copies(world)
    if not world then
        local opened,why=require('hd2runtime/runtime/event_world').open()
        if not opened then return {status='unavailable',reason=tostring(why)}end
        world=opened
    end
    local ok,why=prove(world)
    if not ok then return {status='unavailable',reason=why}end
    local event_world=require('hd2runtime/runtime/event_world')
    local manager=world.view.pointer(world.game+P.global)
    if not manager then return {status='unavailable',reason='no avatar manager'}end
    local simulated=world.view.u32(manager+P.simulated)
    if not simulated or simulated>64 then return {status='unavailable',reason='the simulated avatar count is unreadable'}end
    local local_avatar
    local listed,players=pcall(event_world.players,world,true)
    if listed then
        for _,player in ipairs(players)do if player['local']then local_avatar=player.avatar end end
    end
    local health=event_world.health_manager(world)
    local report={status='checked',simulated=simulated,avatars={}}
    for index=0,simulated-1 do
        local descriptor=world.view.pointer(manager+P.descriptors+index*8)
        local bytes=descriptor and world.view.read(descriptor,24)
        if not bytes then return {status='unavailable',reason='an avatar descriptor is unreadable'}end
        local entity=b.u32(bytes,P.descriptorEntity)
        report.avatars[#report.avatars+1]={entity=entity,
            type=string.format('0x%08X%08X',b.u32(bytes,4),b.u32(bytes,0)),
            ['local']=local_avatar~=nil and local_avatar==entity or nil,
            owned=b.u32(bytes,P.descriptorFlags)%2==1,
            avatar_copy=event_world.hash_value(world,manager+P.copyMap,entity)~=nil,
            health_copy=health~=nil and event_world.hash_value(world,health+P.healthCopyMap,entity)~=nil}
    end
    return report
end
-- The plan notes for one spec: which fields a private copy held by a simulated Helldiver keeps from this write.
local COPY_LABEL={avatar='AvatarComponentData',health='HealthComponentData'}
function M.notes(spec,report)
    local by_reader,order={},{}
    for _,change in ipairs(spec.changes)do
        local reader=change.descriptor.copyReader
        if reader then
            if not by_reader[reader]then by_reader[reader]={};order[#order+1]=reader end
            local list=by_reader[reader];list[#list+1]=change.field
        end
    end
    if #order==0 then return nil end
    if report.status~='checked'then
        return {'note: '..spec.id..': could not check for private copies ('..tostring(report.reason)..'): a Helldiver '
            ..'spawned with one keeps its copied values for '..table.concat(by_reader[order[1]],', ')
            ..(order[2]and(', '..table.concat(by_reader[order[2]],', '))or'')}
    end
    local notes={}
    for _,reader in ipairs(order)do
        local holders={}
        for _,avatar in ipairs(report.avatars)do
            if avatar[reader..'_copy']then
                holders[#holders+1]='entity '..avatar.entity..(avatar['local']and' (the local player)'or'')
            end
        end
        if #holders>0 then
            notes[#notes+1]='note: '..spec.id..': '..table.concat(holders,', ')..' carries a private '
                ..COPY_LABEL[reader]..' copy (made at spawn by an entity delta; the ship\'s avatar always has one): '
                ..table.concat(by_reader[reader],', ')..' changed the type record but not that Helldiver; it keeps the '
                ..'copied values until it spawns again without a copy (Runtime never writes private copies)'
        end
    end
    return #notes>0 and notes or nil
end

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots};local physical={}
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        local record=resolved.catalog.record(resolved.candidate,backing.component)
        assert(record.identity.recordIndex==backing.recordIndex and record.identity.indexRow==backing.indexRow,
            'Helldiver '..backing.component..' record ownership changed')
        assert(record.identity.ownerCount==backing.ownerCount and record.identity.uniqueOwner==true,
            'Helldiver '..backing.component..' record consumer scope changed')
        for _,guard in ipairs(backing.guards or{})do
            local expected=b.unhex(guard.hex)
            assert(record.bytes:sub(guard.offset+1,guard.offset+#expected)==expected,
                'Helldiver damage zone identity changed ('..change.field..' guard at +'..guard.offset..')')
        end
        assert(backing.offset+backing.width<=#record.bytes,'field outside reviewed record')
        local current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
        local zone=change.descriptor.target.zone
        local expected=ownership.expected(change,current,nil,{target='helldiver '..(zone and('zone '..zone..' ')or'')
            ..change.field})
        local offset=record.offset+backing.offset
        local key=tostring(record.owner.base)..':'..tostring(offset)..':'..backing.width
        local prior=physical[key]
        if prior then
            assert(prior.desired==change.desired,'overlapping Helldiver fields conflict')
        else
            local item={label=change.field,canonical_field=change.canonical_field,semantic_aliases={change.field},
                owner=record.owner,offset=offset,field_offset=backing.offset,expected=expected,desired=change.desired,
                before=current,already_desired=current==change.desired,expect=change.expect,value=change.value,
                identity={component=backing.component,component_type='semantic',record_index=backing.recordIndex,
                    unique_owner=true,owner_count=backing.ownerCount,scope=change.descriptor.operationGroup},
                chain={}}
            physical[key]=item;plan.changes[#plan.changes+1]=item
        end
    end
    -- Report, never refuse: the write is correct for the type record; a private copy only keeps it from one avatar.
    -- Fields every hit reads from the type record (the zone multipliers, the durable share) need no check.
    local shadowed=false
    for _,change in ipairs(spec.changes)do if change.descriptor.copyReader then shadowed=true end end
    if shadowed then
        local ok,report=pcall(M.private_copies)
        if not ok then report={status='unavailable',reason=tostring(report)}end
        plan.notes=M.notes(spec,report)
        plan.private_copies=report
    end
    return plan
end
return M
