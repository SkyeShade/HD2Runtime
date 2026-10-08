-- Guarded armor stat fields (hd2.armor_stats; docs/armor-stats.md). Source of truth: research/armor-stats-F5FEE03DCFDB.json,
-- generated into domains/armor_stats.lua; the formulas and the live reads are runtime/armor_stats.lua.
--
-- Three typed targets:
--   * armor_kit (hd2.armor_stats.kit(id_or_name)): the weight (0 light, 1 medium, 2 heavy) of the kit's armor piece in
--     one slot, field armor_kit.piece_weight.<slot>. WRITABLE: the kit's pieces are ordinary private read-write
--     memory. Every player wearing that kit reads them, so every write needs allow_shared; not live-tested, so every
--     write needs allow_unverified_effect. The armor rating follows on the next hit (LIVE); the speed and stamina
--     factors when the game next applies the kit (a respawn or an armor change). A slot is written in every body
--     (stocky, slim, any) that has a piece there.
--   * armor_class (hd2.armor_stats.class('light' | 'medium' | 'heavy')): armor_class.rating / speed / stamina, the
--     per-weight tables;
--   * armor_damage_curve (hd2.armor_stats.damage_curve()): armor_damage_curve.at_minus_1 .. at_3, the avatar damage
--     multiplier at each armor value.
--   The tables and the curve live in game.dll pages that are PAGE_EXECUTE_READWRITE at run time (every retained
--   snapshot). A guarded write never targets an executable page, EXCEPT a reviewed extent (the user's decision of
--   2026-10-08; core/page_protection.lua register_executable_data): before a class or curve write this domain proves
--   the build, every pin and constant, and registers the exact 4-byte extent of each changed entry; the transaction
--   then accepts that page as it is (never re-protected) only for changes inside registered extents.
--
-- Before any kit write the domain re-proves: the build the research covers, game.dll's image, every instruction pin
-- of the research plus the slot-map pins and the consumers' constants, the customization manager pointer, the kit's
-- row (id, armor type, passive, body count) at its research index, its bodies and pieces (each array a transaction
-- context), and each piece's current weight: the reviewed vanilla weight or the desired one (core/ownership.lua),
-- anything else is a CONFLICT.
local ownership=require('hd2runtime/core/ownership')
local protection=require('hd2runtime/core/page_protection')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local natives=require('hd2runtime/domains/event_natives')
local D=require('hd2runtime/domains/armor_stats')
local A=require('hd2runtime/runtime/armor_stats')
local M={}
local IMAGE,PRIVATE=0x1000000,0x20000
local K,BODY,PIECE,CM=D.kit,D.body,D.piece,D.customization
local ACKS={'allow_shared','allow_unverified_effect'}
M.SHARED_KIT='every player wearing this armor kit reads its pieces (stocky, slim and any-body pieces alike)'
M.SHARED_CLASS='every armor whose pieces have this weight, for every player this machine simulates or hits'
M.UNVERIFIED='not live-tested (docs/armor-stats.md)'
M.CURVE_KEYS={{key=3,name='at_3'},{key=2,name='at_2'},{key=1,name='at_1'},{key=0,name='at_0'},{key=-1,name='at_minus_1'}}

local function finite(v)return type(v)=='number'and v==v and v>-math.huge and v<math.huge end
local function valid_id(value)
    assert(type(value)=='string'and#value>0 and#value<=64 and not value:find('[^%w_%-]'),'invalid operation id')
end
local function slot_index(name)
    for index,slot in ipairs(D.slots)do if slot==name then return index-1 end end
end

---------------------------------------------------------------------------------------------- descriptors --
local descriptors={}
local function cached(key,build)
    local d=descriptors[key]
    if not d then d=build();descriptors[key]=d end
    return d
end
-- The field descriptors of a kit: one per armor slot it has.
function M.kit_fields(kit)
    local out={}
    for _,slot in ipairs(D.slots)do
        local vanilla=kit.weights[slot]
        if vanilla then
            out[#out+1]=cached('kit:'..kit.id..':'..slot,function()
                return {semanticFieldId='armor_kit.piece_weight.'..slot,type='enum',unit='weight class',
                    currentDefault=A.weight_name(vanilla),vanilla=vanilla,editable=true,min=0,max=2,
                    allowedValues={'light','medium','heavy'},slot=slot,slotIndex=slot_index(slot),
                    lifecycle='armor rating: the next hit (live); speed and stamina: the next armor apply (respawn or '
                        ..'a kit change)',
                    target={resource='armor_kit',armor_kit=kit.id},
                    backing={kind='armor_piece',kit=kit.id,slot=slot,offset=PIECE.weight,storage='u32',width=4},
                    shared=true,allowSharedRequired=true,sharedReason=M.SHARED_KIT,
                    acknowledgement='allow_unverified_effect',acknowledgementReason=M.UNVERIFIED,
                    acknowledgements=ACKS,operationGroup='armor_kit/'..kit.id}
            end)
        end
    end
    return out
end
local CLASS_FIELDS={{name='rating',table='armor',unit='armor value A (rating = 50 + 50 x A)'},
    {name='speed',table='speed',unit='speed factor (SPEED = 500 x factor)'},
    {name='stamina',table='stamina',unit='stamina factor F (STAMINA REGEN = 100 x (2 - F); F scales drain and regen)'}}
function M.class_fields(index)
    local out={}
    for _,f in ipairs(CLASS_FIELDS)do
        out[#out+1]=cached('class:'..index..':'..f.name,function()
            local range=D.ranges[f.name]
            return {semanticFieldId='armor_class.'..f.name,type='number',unit=f.unit,
                currentDefault=D.tables[f.table].values[index+1],editable=true,executableData=true,
                min=range[1],max=range[2],
                lifecycle=f.name=='rating'and'the next hit (live)'or'the next armor apply (respawn or a kit change)'
                    ..(f.name=='speed'and'; how the game consumes the speed product is UNPROVEN'or''),
                target={resource='armor_class',armor_class=D.classes[index+1]},
                backing={kind='image_table',table=f.table,rva=D.tables[f.table].rva+index*4,storage='f32',width=4},
                shared=true,allowSharedRequired=true,sharedReason=M.SHARED_CLASS,
                acknowledgement='allow_unverified_effect',acknowledgementReason=M.UNVERIFIED,acknowledgements=ACKS,
                operationGroup='armor_class/'..f.table}
        end)
    end
    return out
end
function M.curve_fields()
    local out={}
    for i,point in ipairs(M.CURVE_KEYS)do
        out[#out+1]=cached('curve:'..point.name,function()
            local range=D.ranges.damage
            return {semanticFieldId='armor_damage_curve.'..point.name,type='number',
                unit='damage multiplier at armor value '..point.key,currentDefault=D.curve.points[i][2],editable=true,
                executableData=true,min=range[1],max=range[2],armorValue=point.key,
                lifecycle='the next hit on a Helldiver (live)',target={resource='armor_damage_curve'},
                backing={kind='image_table',table='curve',rva=D.curve.rva+(i-1)*8+4,storage='f32',width=4},
                shared=true,allowSharedRequired=true,sharedReason='every Helldiver hit on this machine',
                acknowledgement='allow_unverified_effect',acknowledgementReason=M.UNVERIFIED,acknowledgements=ACKS,
                operationGroup='armor_damage_curve'}
        end)
    end
    return out
end

---------------------------------------------------------------------------------------------- validation --
local function target_of(target)
    assert(type(target)=='table','unsupported armor stats target (use hd2.armor_stats.kit, .class or .damage_curve)')
    local resource=target.resource
    for key in pairs(target)do
        assert(key=='resource'or key=='armor_kit'or key=='armor_class','unsupported armor stats target identity: '
            ..tostring(key))
    end
    if resource=='armor_kit'then
        local kit,code,why=A.find_kit(target.armor_kit)
        if not kit then error(code..': '..why,0)end
        return 'armor_kit',kit,M.kit_fields(kit)
    elseif resource=='armor_class'then
        local index=A.weight(target.armor_class)
        if not index or type(target.armor_class)~='string'then
            error('UNKNOWN_ARMOR_CLASS: '..tostring(target.armor_class)..' is not an armor class (light, medium, heavy)',0)
        end
        return 'armor_class',index,M.class_fields(index)
    end
    assert(resource=='armor_damage_curve','unsupported armor stats target: '..tostring(resource))
    return 'armor_damage_curve',nil,M.curve_fields()
end
local function find_field(fields,id,label)
    assert(type(id)=='string','field must be a field id (hd2.fields.armor_kit.*, hd2.fields.armor_class.*, '
        ..'hd2.fields.armor_damage_curve.*)')
    for _,field in ipairs(fields)do if field.semanticFieldId==id then return field end end
    error('field is not exposed for '..label..': '..id,0)
end
local function validate_change(kind,fields,item,request,label)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local field=find_field(fields,item.field,label)
    assert(request.allow_shared==true,'shared field requires allow_shared=true: '..item.field..' ('..field.sharedReason..')')
    assert(request.allow_unverified_effect==true,'field requires allow_unverified_effect=true: '..item.field..' ('
        ..field.acknowledgementReason..')')
    if kind=='armor_kit'then
        local expect,value=A.weight(item.expect),A.weight(item.value)
        assert(expect~=nil,'UNKNOWN_WEIGHT: expect must be light, medium, heavy or 0..2: '..tostring(item.expect))
        assert(value~=nil,'UNKNOWN_WEIGHT: value must be light, medium, heavy or 0..2: '..tostring(item.value))
        assert(expect==field.vanilla,'expect differs from the reviewed value of '..item.field..': declared='
            ..A.weight_name(expect)..' reviewed='..field.currentDefault)
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,semantic_aliases={item.field},
            expected=b.encode(expect,'u32'),desired=b.encode(value,'u32'),expect=item.expect,value=item.value,
            weight=value}
    end
    assert(finite(item.expect),'expect must be a finite number')
    assert(finite(item.value),'value must be a finite number')
    assert(A.same(item.expect,field.currentDefault),'expect differs from the reviewed value of '..item.field
        ..': declared='..tostring(item.expect)..' reviewed='..tostring(field.currentDefault))
    assert(item.value>=field.min and item.value<=field.max,'value outside the reviewed range ['..field.min..', '
        ..field.max..'] for '..item.field)
    -- A reviewed executable-data entry (core/page_protection.lua): its own f32, at its own image offset.
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,semantic_aliases={item.field},
        expected=b.encode(field.currentDefault,'f32'),desired=b.encode(item.value,'f32'),expect=item.expect,
        value=item.value,rva=field.backing.rva,table=field.backing.table}
end
local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_shared=true,allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local kind,identity,fields=target_of(request.target)
    local label=kind=='armor_kit'and('armor kit '..identity.id..(identity.name and(' '..identity.name)or''))
        or kind=='armor_class'and('the '..D.classes[identity+1]..' armor class')or'the armor damage curve'
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=#D.slots,'transaction requires one to '..#D.slots..' changes')
    local result={kind='armor_kit',target_kind=kind,id=request.id,armor_kit=kind=='armor_kit'and identity.id or nil,
        target_label=label,
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,
        allow_unverified_effect=request.allow_unverified_effect==true,changes={},resource='armor_kit'}
    local seen={}
    for index,item in ipairs(items)do
        local change=validate_change(kind,fields,item,request,label)
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
-- game.dll, re-resolved on every capture: base from the loaded module, extent from its own PE header.
local function module_image(runtime,reader)
    local handle=runtime.module('game.dll')
    if not handle then error('TARGET_UNAVAILABLE: game.dll not loaded',0)end
    local base=runtime.address(handle)
    local header=reader.read({base=base,size=4096,type=IMAGE},0,4096)
    assert(header:sub(1,2)=='MZ','game.dll DOS header missing')
    local pe=b.u32(header,60)
    assert(pe>=64 and pe+88<=#header and header:sub(pe+1,pe+4)=='PE\0\0'and b.u16(header,pe+24)==0x20B,
        'game.dll PE32+ framing')
    assert(b.u32(header,pe+80)==natives.source.imageSize,'game.dll image size changed')
    return {base=base,size=natives.source.imageSize,type=IMAGE}
end
-- The owner (allocation) of an address, as the region query reports it now.
local function owner_at(reader,address,label)
    local r=reader.query(address)
    assert(r.state==0x1000 and r.allocation_base>0,label..' is not committed memory')
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=r.type,protect=r.protect}
end
local function pointer(bytes,offset,label)
    assert(b.u32(bytes,offset+4)<=0x7FFF,label..' is not a user-space pointer')
    local value=b.pointer(bytes,offset)
    assert(value>=65536,label..' is null')
    return value
end
-- The kit as the game holds it, every array captured: {kit, row, bodies = {{type, pieces = {{slot, type, weight,
-- address, owner, bytes}}}}}.
local function capture_kit(reader,manager,kit)
    reader.stage='domains/armor_stats_writes:kit '..kit.id
    local head_owner=owner_at(reader,manager,'the customization manager')
    local head=reader.read(head_owner,manager+CM.kits-head_owner.base,16,true)
    local kits,count=pointer(head,CM.kits,'the kit table'),b.u32(head,CM.kitCount)
    assert(count>kit.index and count<=A.MAX_KITS,'the kit table is not the reviewed one ('..count..' kits)')
    local array_owner=owner_at(reader,kits,'the kit table')
    local entry=reader.read(array_owner,kits+kit.index*8-array_owner.base,8,true)
    local address=pointer(entry,0,'kit '..kit.id)
    local row_owner=owner_at(reader,address,'kit '..kit.id)
    local row=reader.read(row_owner,address-row_owner.base,K.read,true)
    assert(string.format('%08X',b.u32(row,K.id))==kit.id,'ARMOR_KIT_MOVED: the kit table no longer holds armor kit '
        ..kit.id..' at index '..kit.index)
    assert(b.u32(row,K.type)==0,'kit '..kit.id..' is no longer an armor kit')
    assert(b.u32(row,K.passive)==kit.passive,'kit '..kit.id..' passive changed')
    local bodies,n=pointer(row,K.bodies,'kit '..kit.id..' bodies'),b.u32(row,K.bodyCount)
    assert(n==kit.bodies and b.u32(row,K.bodyCount+4)==0,'kit '..kit.id..' body count changed')
    local body_owner=owner_at(reader,bodies,'kit '..kit.id..' bodies')
    local body_rows=reader.read(body_owner,bodies-body_owner.base,n*BODY.stride,true)
    local out={kit=kit,address=address,bodies={},pieces={}}
    for i=0,n-1 do
        local o=i*BODY.stride
        local count_=b.u32(body_rows,o+BODY.count)
        assert(count_<=A.MAX_PIECES and b.u32(body_rows,o+BODY.count+4)==0,'kit '..kit.id..' piece count changed')
        local body={type=b.u32(body_rows,o+BODY.type),pieces={}}
        if count_>0 then
            local pieces=pointer(body_rows,o+BODY.pieces,'kit '..kit.id..' pieces')
            local owner=owner_at(reader,pieces,'kit '..kit.id..' pieces')
            local rows=reader.read(owner,pieces-owner.base,count_*PIECE.stride,true)
            for k=0,count_-1 do
                local p=k*PIECE.stride
                local piece={body=body.type,slot=b.u32(rows,p+PIECE.slot),type=b.u32(rows,p+PIECE.type),
                    weight=b.u32(rows,p+PIECE.weight),address=pieces+p,owner=owner,
                    bytes=rows:sub(p+PIECE.weight+1,p+PIECE.weight+4)}
                body.pieces[#body.pieces+1]=piece
                out.pieces[#out.pieces+1]=piece
            end
        end
        out.bodies[#out.bodies+1]=body
    end
    return out
end
function M.capture_many(runtime,reader,specs)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    assert(D.source.gameDllSha256==profile.dll_sha and D.source.gameDllSha256==natives.source.gameDllSha256,
        'ARMOR_BUILD_CHANGED: the armor stats research covers another game build than the runtime profile')
    reader.stage='domains/armor_stats_writes:pins'
    local image=module_image(runtime,reader)
    -- Code and constants are only read (never a context).
    for _,list in ipairs({D.pins,D.constants})do
        for _,pin in ipairs(list)do
            local want=b.unhex(pin.hex)
            assert(reader.read(image,pin.rva,#want)==want,('native armor code changed (%s at game+%X)'):format(pin.label,
                pin.rva))
        end
    end
    local tables={}
    for _,name in ipairs({'armor','speed','stamina'})do
        local raw=reader.read(image,D.tables[name].rva,12)
        tables[name]={}
        for i=0,2 do tables[name][i+1]=A.round(A.f32(raw,i*4)or 0)end
    end
    local raw=reader.read(image,D.curve.rva,40)
    local points={}
    for i=0,4 do points[i+1]={A.round(A.f32(raw,i*8)or 0),A.round(A.f32(raw,i*8+4)or 1)}end
    reader.stage='domains/armor_stats_writes:customization manager'
    local manager=pointer(reader.read(image,CM.globalRva,8,true),0,'the customization manager')
    local by_kit,results={},{}
    for index,spec in ipairs(specs)do
        if spec.target_kind and spec.target_kind~='armor_kit'then
            results[index]={target_kind=spec.target_kind,image=image,tables=tables,points=points}
        else
            local kit=assert(A.kit_by_id[spec.armor_kit],'reviewed armor kit absent')
            by_kit[kit.id]=by_kit[kit.id]or capture_kit(reader,manager,kit)
            results[index]={kit=kit,live=by_kit[kit.id],tables=tables,points=points}
        end
    end
    return results
end
function M.capture(runtime,reader,spec)return M.capture_many(runtime,reader,{spec})[1]end

-- One change per piece. Each spec change's first piece comes first, in the spec's order (the transaction log pairs
-- them), then every other body's piece of the same slot.
-- A class-table or curve write: each change's 4-byte entry in game.dll's image, its extent registered as reviewed
-- executable data (core/page_protection.lua) after capture_many proved the build, every pin and constant; the entry
-- itself is a captured context, and its expected bytes are the reviewed vanilla (or this Runtime's own earlier write,
-- through core/ownership).
local function prepare_image(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots}
    local image=resolved.image
    for _,change in ipairs(spec.changes)do
        local address=image.base+change.rva
        local r=reader.query(address)
        assert(r.state==0x1000 and r.allocation_base==image.base and r.type==IMAGE,
            spec.target_label..': '..change.field..' is not in game.dll\'s image')
        assert(r.protect==protection.REVIEWED_EXECUTABLE or r.protect==protection.READONLY
            or r.protect==protection.READWRITE,spec.target_label..': '..change.field..' page protection '
            ..string.format('0x%X',r.protect or 0)..' is not the reviewed one')
        local owner={base=image.base,size=image.size,type=IMAGE,protect=r.protect}
        local before=reader.read(owner,change.rva,4,true)
        if r.protect==protection.REVIEWED_EXECUTABLE then
            protection.register_executable_data(address,4,'armor stats '..change.table..' entry (game+'
                ..string.format('%X',change.rva)..')')
        end
        local expected=ownership.expected(change,before,nil,{target=spec.target_label..' '..change.field})
        plan.changes[#plan.changes+1]={label=change.field,canonical_field=change.canonical_field,
            semantic_aliases={change.field},owner=owner,offset=change.rva,field_offset=0,expected=expected,
            desired=change.desired,before=before,already_desired=before==change.desired,expect=change.expect,
            value=change.value,identity={component='ArmorStatsTable',component_type='native',record_index=change.rva,
                record_type='game.dll '..change.table..' table',unique_owner=true,owner_count=1,
                scope=change.descriptor.operationGroup},chain={}}
    end
    plan.notes={('note: %s: %s: %s (every Helldiver on this machine; %s)'):format(spec.id,spec.target_label,
        table.concat((function()local t={};for _,c in ipairs(spec.changes)do t[#t+1]=c.field..' = '..tostring(c.value)end
            return t end)(),', '),spec.changes[1].descriptor.lifecycle)}
    return plan
end
function M.prepare(resolved,reader,spec)
    if resolved.target_kind and resolved.target_kind~='armor_kit'then return prepare_image(resolved,reader,spec)end
    local plan={changes={},snapshots=reader.snapshots}
    local primary,extra,weights={},{},{}
    for _,change in ipairs(spec.changes)do
        local descriptor=change.descriptor
        local pieces={}
        for _,p in ipairs(resolved.live.pieces)do
            if p.type==0 and p.slot==descriptor.slotIndex then pieces[#pieces+1]=p end
        end
        assert(#pieces>0,'armor kit '..resolved.kit.id..' has no armor piece in slot '..descriptor.slot)
        weights[descriptor.slot]=change.weight
        for index,p in ipairs(pieces)do
            assert(p.owner.type==PRIVATE and p.owner.protect==4,'armor kit '..resolved.kit.id
                ..' pieces are not private read-write memory')
            local expected=ownership.expected(change,p.bytes,nil,{target='armor kit '..resolved.kit.id..' '
                ..descriptor.slot..' piece (body '..p.body..')'})
            local item={label=change.field,canonical_field=change.canonical_field,semantic_aliases={change.field},
                owner=p.owner,offset=p.address+PIECE.weight-p.owner.base,field_offset=PIECE.weight,expected=expected,
                desired=change.desired,before=p.bytes,already_desired=p.bytes==change.desired,expect=change.expect,
                value=change.value,identity={component='CustomizationKitPiece',component_type='native',
                    record_index=p.slot,record_type='armor kit '..resolved.kit.id..' body '..p.body,
                    unique_owner=false,owner_count=0,scope=descriptor.operationGroup},chain={}}
            if index==1 then primary[#primary+1]=item else extra[#extra+1]=item end
        end
    end
    for _,item in ipairs(primary)do plan.changes[#plan.changes+1]=item end
    for _,item in ipairs(extra)do plan.changes[#plan.changes+1]=item end
    assert(#plan.changes<=128,'armor kit write-set size unsupported')
    -- What the kit gives after this write (the stocky body; the tables as read now).
    local pieces={}
    for _,p in ipairs(resolved.live.pieces)do
        local w=p.weight
        if p.type==0 then
            local name=D.slots[p.slot+1]
            if name and weights[name]~=nil then w=weights[name]end
        end
        pieces[#pieces+1]={body=p.body,slot=p.slot,type=p.type,weight=w}
    end
    local after=A.stats(pieces,resolved.tables,resolved.points,resolved.kit.passive,0)
    if after then
        plan.notes={('note: %s: armor kit %s%s now gives rating %s (armor value %s, damage x%s) from the next hit, and '
            ..'speed %s / stamina regen %s (factors %s / %s) from the next armor apply (a respawn or a kit change); '
            ..'every player wearing it on this machine'):format(spec.id,resolved.kit.id,
            resolved.kit.name and(' '..resolved.kit.name)or'',after.rating,after.armor_value,after.damage_multiplier,
            after.speed,after.stamina_regen,after.speed_factor,after.stamina_factor)}
        plan.effect=after
    end
    return plan
end
return M
