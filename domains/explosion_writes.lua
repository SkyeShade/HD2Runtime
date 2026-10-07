-- Guarded edits of a catalogued explosion (hd2.explosion(name); docs/explosions.md). The target is one row of the game's
-- ExplosionSettings table, named by research/explosion-identities-F5FEE03DCFDB.json (domains/explosion_catalogue.lua),
-- and the DamageInfo row its +4 member links. Every write re-proves, in the live settings allocations, that the row
-- for the explosion's type is still the reviewed row (type, group, row, settings type) and, for a damage field, that its
-- +4 link still names the reviewed DamageInfo row and that row's identity, before any memory is touched.
--
-- No edit through this target is live-tested: every field needs allow_unverified_effect. A row more than one owner
-- requests (or a damage row more than one reference uses) changes for all of them: allow_shared.
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local profile=require('hd2runtime/schemas/current')
local catalogue=require('hd2runtime/domains/explosion_catalogue')
local M={}

local FIELDS={}
for index,field in ipairs(catalogue.fields)do FIELDS[field.id]={index=index,definition=field}end
M.FIELDS=FIELDS

-- A catalogued explosion by its semantic id, or by its label (case-insensitive): entry, id. nil when unknown.
local by_label
function M.entry(name)
    if type(name)~='string'then return nil end
    local entry=catalogue.explosions[name]
    if entry then return entry,name end
    if not by_label then
        by_label={}
        for id,item in pairs(catalogue.explosions)do by_label[item.label:lower()]=id end
    end
    local id=by_label[name:lower()]
    if id then return catalogue.explosions[id],id end
    return nil
end

-- The field descriptor of one explosion (cached: one table per explosion and field).
local descriptors={}
function M.descriptor(entry,id,field_id)
    local key=id..'|'..field_id
    if descriptors[key]then return descriptors[key]end
    local field=assert(FIELDS[field_id],'field is not exposed for explosions: '..tostring(field_id))
    local definition=field.definition
    local damage=definition.backing=='damage'
    local editable,reason=true,nil
    if damage and not entry.damage then
        editable,reason=false,'the explosion links no DamageInfo row (+4 is 0)'
    elseif field_id=='explosion.shrapnel_count'and not entry.shrapnel then
        editable,reason=false,'the explosion releases no shrapnel projectile (+84 is 0)'
    end
    local row=damage and entry.damage or entry
    local descriptor={semanticFieldId=field_id,type=definition.type,unit=definition.unit,
        currentDefault=entry.values[field.index],editable=editable,reason=reason,
        shared=damage and(entry.damage and entry.damage.shared==true or false)or entry.shared==true,
        range={min=definition.min,max=definition.max},acknowledgement='allow_unverified_effect',
        acknowledgementReason='no edit through hd2.explosion(name) is live-tested',
        target={resource='explosion',explosion=id},
        backing={kind='settings',settings=definition.backing,offset=definition.offset,width=4,
            storage=definition.storage,row=row and row.row,group=row and row.group,
            recordType=damage and(entry.damage and entry.damage.type)or entry.type,
            settingsType=row and row.settingsType}}
    descriptors[key]=descriptor
    return descriptor
end

local function finite(value)return type(value)=='number'and value==value and value>-math.huge and value<math.huge end
local function equal(a,c,storage)
    if storage=='f32'then return finite(a)and finite(c)and math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64 and not value:find('[^%w_%-]'),'invalid operation id')
end
local function entry_for(target)
    assert(type(target)=='table'and target.resource=='explosion'and type(target.explosion)=='string',
        'unsupported explosion target (use hd2.explosion(name))')
    for key in pairs(target)do assert(key=='resource'or key=='explosion','unsupported explosion target identity')end
    local entry,id=M.entry(target.explosion)
    assert(entry,'UNKNOWN_EXPLOSION: '..target.explosion..' is not a catalogued explosion (hd2.explosions.list())')
    return entry,id
end
local function validate_change(entry,id,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    assert(FIELDS[item.field],'field is not exposed for explosions: '..tostring(item.field))
    local field=M.descriptor(entry,id,item.field)
    assert(field.editable,'field is read-only: '..item.field..' ('..tostring(field.reason)..')')
    assert(not field.shared or request.allow_shared==true,'shared field requires allow_shared=true: '..item.field
        ..' ('..(field.backing.settings=='damage'and'its DamageInfo row is used by other references'
            or'the explosion row is requested by more than one owner')..'; hd2.explosion(name):describe().owners)')
    assert(request.allow_unverified_effect==true,'field requires allow_unverified_effect=true: '..item.field..' ('
        ..field.acknowledgementReason..')')
    assert(finite(item.expect),'expect must be a finite number')
    assert(finite(item.value),'value must be a finite number')
    if field.type=='integer'then
        assert(item.expect%1==0 and item.value%1==0,'integer explosion field requires integer values: '..item.field)
    end
    assert(equal(item.expect,field.currentDefault,field.backing.storage),'expect differs from the reviewed value of '
        ..item.field..' for '..id..': declared='..tostring(item.expect)..' reviewed='..tostring(field.currentDefault))
    assert(item.value>=field.range.min and item.value<=field.range.max,'value outside the reviewed range ['
        ..field.range.min..', '..field.range.max..'] for '..item.field)
    return {field=item.field,canonical_field=item.field,descriptor=field,semantic_aliases={item.field},
        expected=b.encode(item.expect,field.backing.storage),desired=b.encode(item.value,field.backing.storage),
        expect=item.expect,value=item.value}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local entry,id=entry_for(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=32,'transaction requires one to 32 changes')
    local result={kind='explosion',id=request.id,explosion=id,diagnostic=request.diagnostic==true,
        allow_shared=request.allow_shared==true,allow_unverified_effect=request.allow_unverified_effect==true,changes={}}
    local seen={}
    for index,item in ipairs(items)do
        local change=validate_change(entry,id,item,request)
        assert(not seen[change.field],'transaction lists '..change.field..' twice')
        seen[change.field]=true
        result.changes[index]=change
    end
    result.field=request.field;result.expect=request.expect;result.value=request.value
    return result
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local needed={explosion=true}
    for _,spec in ipairs(specs)do
        for _,change in ipairs(spec.changes)do
            if change.descriptor.backing.settings=='damage'then needed.damage=true end
        end
    end
    local roots=discover.locate(runtime,reader,profile,needed)
    local results={}
    for index,spec in ipairs(specs)do
        results[index]={roots=roots,entry=assert(catalogue.explosions[spec.explosion],'catalogued explosion absent')}
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

-- The live row of a reviewed settings identity, re-proven: (record, owner).
local function settings_row(roots,kind,record_type,group,row,settings_type,label)
    local root=assert(roots[kind],kind..' settings allocation absent')
    local record=root.records[record_type]
    assert(record,'EXPLOSION_ROW_ABSENT: '..label..': no live '..kind..' row for its type')
    assert(record.kind==record_type and record.group==group and record.row==row and record.settings_type==settings_type,
        'EXPLOSION_IDENTITY_CHANGED: '..label..': the live '..kind..' row is not the reviewed row')
    return record,root.owner
end
M.settings_row=settings_row

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots}
    local entry=resolved.entry
    local explosion,explosion_owner=settings_row(resolved.roots,'explosion',entry.type,entry.group,entry.row,
        entry.settingsType,spec.explosion)
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        local record,owner=explosion,explosion_owner
        if backing.settings=='damage'then
            local damage=assert(entry.damage,'catalogued explosion has no damage row')
            assert(b.u32(explosion.bytes,catalogue.layout.damageLink)==damage.type,'CONFLICT: '..spec.explosion
                ..': its DamageInfo link (+4) no longer names the reviewed row')
            record,owner=settings_row(resolved.roots,'damage',damage.type,damage.group,damage.row,damage.settingsType,
                spec.explosion..' damage')
        end
        assert(backing.offset+backing.width<=#record.bytes,'field outside reviewed record')
        local current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
        local expected=ownership.expected(change,current,nil,{target='explosion '..spec.explosion})
        plan.changes[#plan.changes+1]={label=change.field,canonical_field=change.canonical_field,
            semantic_aliases={change.field},owner=owner,offset=record.offset+backing.offset,field_offset=backing.offset,
            expected=expected,desired=change.desired,before=current,already_desired=current==change.desired,
            expect=change.expect,value=change.value,
            identity={component=(backing.settings=='damage'and'DamageInfo'or'ExplosionSettings'),
                component_type=backing.settingsType,record_index=backing.row,group=backing.group,
                record_kind=backing.recordType,unique_owner=not change.descriptor.shared,
                owner_count=change.descriptor.shared and 2 or 1,scope='explosion '..spec.explosion},
            chain={}}
    end
    return plan
end
return M
