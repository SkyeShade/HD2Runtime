-- Guarded Booster authoring. Boosters own no settings type; their fields live on the records
-- the Booster enum reaches. Every write re-proves that link live:
--   tuning:            game.dll's own Booster name table -> native Booster definition table row
--                      (static .data) -> pinned IsBoosterActive gate and consumer instructions
--   explosion:         pinned gate + literal ExplosionType selector -> ExplosionSettings/DamageInfo
--   status_effect:     pinned gate + literal StatusEffectType selector -> StatusEffectSettings row
--   status_damage:     pinned gate + literal StatusEffectType -> status damage type -> DamageInfo
--   granted_stratagem: definition table row +4 -> StratagemSettings row (pinned grant path)
--   deployed_entity:   StratagemInfo booster entry -> entity delta -> rack item -> turret entity
-- Code bytes are only ever read, never written. No booster edit is gameplay-proven, so
-- allow_unverified_effect is always required.
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local Stratagem=require('hd2runtime/core/stratagem')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/booster_authoring')
local native=database.native
local M={}
local component_names={'ProjectileWeaponComponentData','WeaponMagazineComponentData'}
local IMAGE=0x1000000
local ACCESSORS='booster:tuning(), booster:explosion(), booster:status_effect(), booster:status_damage(), '
    ..'booster:granted_stratagem(), or booster:deployed_entity()'

local function equal(a,c,storage)
    if storage=='f32'then return type(a)=='number'and type(c)=='number'
        and math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64
        and not value:find('[^%w_%-]'),'invalid operation id')
end
local function target_for(target)
    assert(type(target)=='table'and target.resource=='booster','unsupported booster target')
    for key in pairs(target)do assert(key=='resource'or key=='booster'or key=='path',
        'unsupported booster target identity')end
    local entry=assert(type(target.booster)=='string'and database.boosters[target.booster],
        'unknown reviewed booster: '..tostring(target.booster))
    assert(target.path~='booster','booster root has no fields; use '..ACCESSORS)
    local owned=assert(entry.targets[target.path],entry.name..' has no reviewed '..tostring(target.path)..' target')
    return entry,owned
end
local function validate_change(entry,owned,item,request)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=assert(owned.fields[item.field],'field is not exposed for '..entry.name..': '..tostring(item.field))
    assert(request.allow_unverified_effect==true,
        'booster writes require allow_unverified_effect=true: '..item.field..' ('..field.acknowledgementReason..')')
    assert(not field.shared or request.allow_shared==true,
        'shared field requires allow_shared=true: '..item.field)
    local storage=field.backing.storage
    for _,value in ipairs({item.expect,item.value})do
        assert(type(value)=='number'and value==value and value>-math.huge and value<math.huge,
            'booster values must be finite numbers')
        if storage=='u32'then assert(value%1==0 and value>=0 and value<=4294967295,
            'integer booster field requires a non-negative integer')end
        if storage=='i32'then assert(value%1==0 and value>=-2147483648 and value<=2147483647,
            'integer booster field requires an integer')end
    end
    local range=field.range
    if range then
        assert(item.value>=range.min and item.value<=range.max,'value outside the reviewed range ['
            ..range.min..', '..range.max..'] for '..item.field)
        assert(not range.integer or item.value%1==0,'integer booster field requires an integer value: '..item.field)
    end
    assert(equal(item.expect,field.currentDefault,storage),'expect differs from reviewed current value for '..item.field)
    return {field=item.field,canonical_field=item.field,descriptor=field,
        expected=b.encode(item.expect,storage),desired=b.encode(item.value,storage),expect=item.expect,value=item.value}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local entry,owned=target_for(request.target)
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=8,'transaction requires one to eight changes')
    local result={kind='booster',id=request.id,booster=entry.name,target_path=request.target.path,
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,changes={}}
    local group;local seen={}
    for index,item in ipairs(items)do
        local change=validate_change(entry,owned,item,request)
        assert(not seen[item.field],'duplicate booster field: '..tostring(item.field));seen[item.field]=true
        group=group or change.descriptor.operationGroup
        assert(group==change.descriptor.operationGroup,'transaction spans multiple backing objects; use hd2.plan')
        result.changes[index]=change
    end
    result.field=request.field;result.expect=request.expect;result.value=request.value
    return result
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

-- game.dll, re-resolved on every capture: base from the loaded module, extent from its own
-- PE header. Reads only; the owner's protect is the RW data section the table lives in.
local function module_image(runtime,reader)
    local base=runtime.address(assert(runtime.module('game.dll'),'TARGET_UNAVAILABLE: game.dll not loaded'))
    local header=reader.read({base=base,size=4096,type=IMAGE},0,4096)
    assert(header:sub(1,2)=='MZ','game.dll DOS header missing')
    local pe=b.u32(header,60)
    assert(pe>=64 and pe+88<=#header and header:sub(pe+1,pe+4)=='PE\0\0'
        and b.u16(header,pe+24)==0x20B,'game.dll PE32+ framing')
    assert(b.u32(header,pe+80)==native.imageSize,'game.dll image size changed')
    return {base=base,size=native.imageSize,type=IMAGE,protect=4}
end
-- Exact instruction bytes at pinned RVAs (gates, selectors, consumers). Uncaptured: code is
-- never a transaction context.
local function prove_code(reader,image,proofs,label)
    for _,proof in ipairs(proofs)do
        local length=#proof.bytes/2
        assert(proof.rva+length<=image.size,'native proof outside game.dll')
        assert(reader.read(image,proof.rva,length)==b.unhex(proof.bytes),
            'native consumer changed ('..label..' at +'..string.format('%X',proof.rva)..')')
    end
end
-- game.dll's own Booster enum-name table: every pointer relocated to its reviewed string, and
-- the strings of the targeted values (plus the None/Count framing) read back exactly.
local function prove_names(reader,image,values)
    local count=#native.names
    local pointers=reader.read(image,native.namesRva,count*8)
    for index=1,count do
        assert(b.pointer(pointers,(index-1)*8)==image.base+native.nameStrings[index],
            'booster enum-name table changed')
    end
    local check={1,count}
    for _,value in ipairs(values)do check[#check+1]=value+1 end
    for _,index in ipairs(check)do
        local name=native.names[index]
        assert(reader.read(image,native.nameStrings[index],#name+1)==name..'\0',
            'booster enum name changed: '..name)
    end
end
-- The whole definition table is the transaction context. Row identity is checked with every
-- scalar masked, so edits made by other booster operations do not break unrelated rows.
local function capture_table(reader,image)
    prove_code(reader,image,{native.tableBound},'booster table bound')
    local bytes=reader.read(image,native.tableRva,native.rows*native.stride,true)
    for row=0,native.rows-1 do
        local raw=bytes:sub(row*native.stride+1,(row+1)*native.stride)
        assert(raw:sub(1,8)..'\0\0\0\0'..raw:sub(13)==b.unhex(native.rowIdentity[row+1]),
            'booster table row identity changed: '..native.names[row+1])
    end
    return bytes
end

-- StratagemInfo booster list entry still names this booster, payload, and delta.
local function prove_stratagem(reader,records,region,chain)
    reader.stage='domains/booster_writes:stratagem_entry'
    local record
    for _,item in ipairs(records)do
        if item.record_kind==chain.stratagemKind then record=item end
    end
    assert(record and record.id==chain.stratagemId,'booster stratagem identity changed')
    -- Uncaptured: capture_all already holds the whole table as this address's context.
    local list=reader.read(region,record.offset+280,16)
    local pointer,count=b.pointer(list,0),b.pointer(list,8)
    assert(count>chain.entryIndex and pointer>=region.base
        and pointer+count*32<=region.base+profile.stratagem.size,'booster list extent changed')
    local entry=reader.read(region,pointer-region.base+chain.entryIndex*32,32)
    assert(b.u32(entry,0)==chain.booster and b.resource(entry,8)==chain.payload
        and b.resource(entry,16)==chain.entityDelta,'stratagem booster entry changed')
end
-- The entity delta keyed by the entry still places the turret in the reviewed rack slot.
local function prove_delta(reader,region,chain,resource)
    reader.stage='domains/booster_writes:entity_delta'
    local d=profile.entity_deltas
    local base=d.header_offset
    local header=reader.read(region,base,80,true)
    for index,name in ipairs({'hashmap','settings','component','delta','data'})do
        assert(b.pointer(header,(index-1)*16)==region.base+base+d[name..'_offset'],
            'entity delta '..name..' relocation changed')
        assert(b.pointer(header,(index-1)*16+8)==d[name..'_count'],'entity delta '..name..' count changed')
    end
    local row=reader.read(region,base+d.hashmap_offset+chain.hashmapSlot*16,16,true)
    assert(b.resource(row,0)==chain.entityDelta and b.u32(row,8)==chain.settingsIndex,
        'booster entity delta ownership changed')
    local settings=reader.read(region,base+d.settings_offset+chain.settingsIndex*8,8,true)
    local count,first=b.u32(settings,0),b.u32(settings,4)
    assert(count>0 and count<=64 and first+count<=d.component_count,'booster delta settings bounds')
    local components=reader.read(region,base+d.component_offset+first*12,count*12,true)
    local found
    for i=0,count-1 do
        if b.u32(components,i*12)==chain.rackComponentIndex then
            assert(not found,'rack component patched twice');found=i
        end
    end
    assert(found,'booster delta no longer patches the hellpod rack')
    local first_delta,deltas=b.u32(components,found*12+4),b.u32(components,found*12+8)
    assert(deltas>0 and deltas<=128 and first_delta+deltas<=d.delta_count,'booster delta bounds')
    local rows=reader.read(region,base+d.delta_offset+first_delta*12,deltas*12,true)
    local located
    for i=0,deltas-1 do
        local offset,size,raw=b.u32(rows,i*12),b.u32(rows,i*12+4),b.u32(rows,i*12+8)
        if offset==chain.rackSlot*64 and size==8 then located=base+d.data_offset+raw end
    end
    assert(located==chain.dataOffset,'booster rack slot delta moved')
    assert(b.resource(reader.read(region,located,8,true),0)==resource,
        'booster delta no longer attaches the reviewed turret')
end
local function find_candidate(catalog,resource,row)
    local found
    for _,candidate in ipairs(catalog.candidates)do if candidate.resourceHash==resource then
        assert(not found,'booster entity identity ambiguous');found=candidate end end
    assert(found and found.entityRow==row and#found.diagnostics==0,'reviewed booster entity absent')
    return found
end
local function settings_row(roots,key,kind,group,row,label)
    local record=assert(roots[key]and roots[key].records[kind],label..' absent')
    assert(record.group==group and record.row==row and record.kind==kind,label..' identity changed')
    return record
end
local function granted_record(records,owned)
    local found
    for _,item in ipairs(records)do if item.record_kind==owned.stratagemType then
        assert(not found,'granted stratagem ambiguous');found=item end end
    local reviewed=owned.record
    assert(found and found.id==reviewed.id and found.group==reviewed.group and found.row==reviewed.row
        and found.package==reviewed.package and#found.payloads==#reviewed.payloads,
        'granted stratagem identity changed')
    for index,value in ipairs(reviewed.payloads)do
        assert(found.payloads[index]==value,'granted stratagem payload changed')
    end
    return found
end

function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local needed,need_image,need_stratagem,values={},false,false,{}
    for _,spec in ipairs(specs)do
        local path=spec.target_path
        if path=='deployed_entity'then needed.entity=true;needed.entity_deltas=true;need_stratagem=true
        else
            need_image=true
            values[#values+1]=database.boosters[spec.booster].enumValue
            if path=='status_effect'then needed.status=true
            elseif path=='status_damage'then needed.status=true;needed.damage=true
            elseif path=='explosion'then needed.explosion=true;needed.damage=true
            elseif path=='granted_stratagem'then need_stratagem=true
            else assert(path=='tuning','unsupported booster target path')end
        end
    end
    -- Shared across every spec so each address has exactly one transaction context.
    local roots=next(needed)and discover.locate(runtime,reader,profile,needed)or{}
    local catalog=needed.entity and entities.capture(reader,roots.entity,profile,component_names)
    local image,table_bytes,records,region
    if need_image then
        reader.stage='domains/booster_writes:native_image'
        image=module_image(runtime,reader)
        prove_code(reader,image,{native.gateFunction},'IsBoosterActive')
        prove_names(reader,image,values)
        table_bytes=capture_table(reader,image)
    end
    if need_stratagem then
        reader.stage='domains/booster_writes:stratagem_table'
        records,region=Stratagem.capture_all(runtime,reader,profile)
    end
    local results={}
    for index,spec in ipairs(specs)do
        local entry=assert(database.boosters[spec.booster],'reviewed booster entry absent')
        local owned=assert(entry.targets[spec.target_path],'reviewed booster target absent')
        local result={owned=owned,image=image,table=table_bytes}
        reader.stage='domains/booster_writes:'..spec.target_path
        if owned.proofs then prove_code(reader,image,owned.proofs,entry.name)end
        if spec.target_path=='deployed_entity'then
            prove_stratagem(reader,records,region,owned.chain)
            prove_delta(reader,roots.entity_deltas,owned.chain,owned.resource)
            result.catalog=catalog;result.candidate=find_candidate(catalog,owned.resource,owned.entityRow)
        elseif spec.target_path=='status_effect'then
            local row=assert(roots.status.records[owned.statusType],'booster status row absent')
            assert(row.group==0 and row.row==owned.row and row.offset==owned.rowOffset,'booster status row moved')
            result.status=roots.status;result.row=row
        elseif spec.target_path=='status_damage'then
            local row=settings_row(roots,'status',owned.statusType,owned.group,owned.row,'booster status row')
            assert(b.u32(row.bytes,44)==owned.damageType,'booster status damage type changed')
            result.damage_owner=roots.damage.owner
            result.damage=settings_row(roots,'damage',owned.damageType,owned.damageGroup,owned.damageRow,
                'booster status DamageInfo')
        elseif spec.target_path=='explosion'then
            local row=settings_row(roots,'explosion',owned.explosionType,owned.group,owned.row,'booster explosion')
            assert(b.u32(row.bytes,4)==owned.damageType,'booster explosion damage type changed')
            result.explosion_owner=roots.explosion.owner;result.explosion=row
            if owned.damageType~=0 then
                result.damage_owner=roots.damage.owner
                result.damage=settings_row(roots,'damage',owned.damageType,owned.damageGroup,owned.damageRow,
                    'booster explosion DamageInfo')
                assert(owned.statusType==nil or b.u32(result.damage.bytes,44)==owned.statusType,
                    'booster explosion status type changed')
            end
        elseif spec.target_path=='granted_stratagem'then
            assert(b.u32(table_bytes,owned.value*native.stride+4)==owned.stratagemType,
                'booster no longer grants the reviewed stratagem')
            result.record=granted_record(records,owned);result.region=region
        else
            assert(b.u32(table_bytes,owned.value*native.stride)==b.u32(b.unhex(native.rowIdentity[owned.value+1]),0),
                'booster table row changed')
        end
        results[index]=result
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

local SETTINGS_OWNER={explosion={'explosion_owner','explosion','ExplosionSettings'},
    explosion_damage={'damage_owner','damage','DamageInfo'},status_damage={'damage_owner','damage','DamageInfo'}}
function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots};local physical={}
    for _,change in ipairs(spec.changes)do
        local descriptor=change.descriptor
        local backing=descriptor.backing
        local owner,offset,field_offset,current,identity
        local function settings_identity(component,row)
            return {component=component,component_type='semantic',record_index=row,
                unique_owner=not descriptor.shared,owner_count=0,scope=descriptor.instanceKey}
        end
        if backing.kind=='component'then
            local record=resolved.catalog.record(resolved.candidate,backing.component)
            assert(record.identity.recordIndex==backing.recordIndex and record.identity.indexRow==backing.indexRow
                and record.identity.ownerCount==backing.ownerCount,'booster entity component ownership changed')
            owner,offset,field_offset=record.owner,record.offset+backing.offset,backing.offset
            current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
            identity={component=backing.component,component_type='semantic',record_index=backing.recordIndex,
                unique_owner=backing.uniqueOwner,owner_count=backing.ownerCount,scope=descriptor.instanceKey}
        elseif backing.kind=='booster_table'then
            owner=resolved.image
            local at=backing.row*native.stride+backing.offset
            offset,field_offset=native.tableRva+at,backing.offset
            current=resolved.table:sub(at+1,at+backing.width)
            identity={component='BoosterDefinitionTable',component_type='native_module_data',
                record_index=backing.row,unique_owner=true,owner_count=1,scope=descriptor.instanceKey}
        elseif SETTINGS_OWNER[backing.kind]then
            local keys=SETTINGS_OWNER[backing.kind]
            local record=assert(resolved[keys[2]],'booster settings row absent')
            owner=resolved[keys[1]]
            offset,field_offset=record.offset+backing.offset,backing.offset
            current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
            identity=settings_identity(keys[3],record.row)
        elseif backing.kind=='stratagem_row'then
            owner=resolved.region
            -- Uncaptured reread: the full StratagemSettings snapshot is this address's context.
            local bytes=reader.read(owner,resolved.record.offset,profile.stratagem.stride)
            offset,field_offset=resolved.record.offset+backing.offset,backing.offset
            current=bytes:sub(backing.offset+1,backing.offset+backing.width)
            identity=settings_identity('StratagemSettings',resolved.record.row)
        else
            owner=resolved.status.owner
            if backing.kind=='status_multiplier'then
                local row=resolved.row.bytes
                assert(b.pointer(row,104)==owner.base+backing.arrayOffset and b.pointer(row,112)==backing.count,
                    'booster status multiplier array changed')
                -- Uncaptured: discovery already captured the whole status allocation as the
                -- single transaction context for this address.
                local element=reader.read(owner,backing.arrayOffset+backing.index*8,8)
                assert(b.u32(element,0)==backing.stat,'booster status multiplier stat changed')
                offset=backing.arrayOffset+backing.index*8+4;field_offset=offset-resolved.row.offset
                current=element:sub(5,8)
            else
                assert(backing.kind=='status_row','unsupported booster backing')
                offset=resolved.row.offset+backing.offset;field_offset=backing.offset
                current=resolved.row.bytes:sub(backing.offset+1,backing.offset+backing.width)
            end
            identity=settings_identity('StatusEffectSettings',resolved.row.row)
        end
        assert(current==change.expected or current==change.desired,
            'CONFLICT: '..change.field..' is neither expected nor desired')
        local key=tostring(owner.base)..':'..tostring(offset)
        assert(not physical[key],'overlapping booster fields');physical[key]=true
        plan.changes[#plan.changes+1]={label=change.field,canonical_field=change.canonical_field,
            semantic_aliases={change.field},owner=owner,offset=offset,field_offset=field_offset,
            expected=change.expected,desired=change.desired,before=current,
            already_desired=current==change.desired,expect=change.expect,value=change.value,
            identity=identity,chain={}}
    end
    return plan
end
return M
