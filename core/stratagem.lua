-- Checked module-relative root and runtime table, extracted from the relay probe.
local b=require('hd2runtime/core/bytes')
local M={}
local function array_offset(pointer,root,base,finish,size,label)
    assert(type(size)=='number' and size>=0 and size%1==0,'invalid '..label..' size')
    local absolute_start,absolute_finish=base+root+16,base+finish
    local absolute=pointer>=absolute_start and pointer<=absolute_finish
        and size<=absolute_finish-pointer
    local relative_finish=finish-root
    local relative=pointer>=16 and pointer<=relative_finish
        and size<=relative_finish-pointer
    assert(absolute~=relative,label..' pointer outside/ambiguous in owning group')
    return absolute and pointer-base or root+pointer,
        absolute and 'relocated_absolute' or 'serialized_group_relative'
end
local function target_from_profile(s)
    return {resource=s.resource,package=s.package,id=s.id,current_type=s.record_type,
        group=s.group,row=s.row,payload_count=s.payload_count}
end
function M.parse_all(bytes,base,pointers,s)
    assert(type(bytes)=='string' and #bytes==s.size and type(pointers)=='string'
        and #pointers==s.entries*8,'stratagem captured sizes')
    assert(s.version==1 and s.info_type==0x7BD60854 and s.stride==400
        and s.entries>=1 and s.entries<=2048 and s.payload_max>=1 and s.payload_max<=64,
        'unsupported StratagemSettings/StratagemInfo schema')
    assert(b.u32(bytes,0)==s.groups and s.groups>=1 and s.groups<=32,'stratagem group count')
    local at,seen,total,records=4,{},0,{}
    for group=0,s.groups-1 do
        assert(at+40<=#bytes,'truncated stratagem group')
        assert(bytes:sub(at+1,at+4)=='LDLD' and b.u32(bytes,at+4)==s.version
            and b.u32(bytes,at+8)==s.type and b.u32(bytes,at+16)==1
            and b.u32(bytes,at+20)==0,'stratagem framing')
        local root=at+24
        local finish=root+b.u32(bytes,at+12)
        assert(finish<=#bytes and finish>=root+16,'stratagem group bounds')
        local count=b.u32(bytes,root+8)
        assert(count>0 and count<=s.entries and b.u32(bytes,root+12)==0,
            'stratagem row count/reserved')
        local start,row_representation=array_offset(b.pointer(bytes,root),root,base,finish,
            count*s.stride,'stratagem rows')
        for row=0,count-1 do
            local ro=start+row*s.stride
            local kind=b.u32(bytes,ro)
            assert(kind<s.entries and not seen[kind],'stratagem type duplicated/out of range')
            seen[kind]=true;total=total+1
            assert(b.pointer(pointers,kind*8)==base+ro,'stratagem runtime table mismatch')
            local payload_count=b.u32(bytes,ro+160)
            assert(payload_count<=s.payload_max and b.u32(bytes,ro+164)==0,
                'payload count/reserved')
            local payloads,payload_representation={},'empty'
            if payload_count>0 then
                local payload_at
                payload_at,payload_representation=array_offset(b.pointer(bytes,ro+152),root,
                    base,finish,payload_count*8,'payload list')
                for index=0,payload_count-1 do
                    payloads[#payloads+1]=b.resource(bytes,payload_at+index*8)
                end
            else assert(b.pointer(bytes,ro+152)==0,'empty payload pointer changed')end
            records[#records+1]={record_kind=kind,id=b.u32(bytes,ro+4),group=group,row=row,
                package=b.resource(bytes,ro+168),payload_count=payload_count,payloads=payloads,
                payload_pointer=payload_representation,row_pointer=row_representation,offset=ro,
                use_count=b.u32(bytes,ro+80),spawn_time=b.value(bytes,ro+84,'f32'),
                spawn_radius=b.value(bytes,ro+88,'f32'),beacon_linger_time=b.value(bytes,ro+96,'f32'),
                extra_travel_time=b.value(bytes,ro+100,'f32'),cooldown=b.value(bytes,ro+104,'f32'),
                cooldown_failed=b.value(bytes,ro+108,'f32'),cooldown_type=b.u32(bytes,ro+148),
                max_in_loadout=b.u32(bytes,ro+204),
                has_shared_uses_pool=bytes:byte(ro+209)%2==1}
        end
        at=finish
    end
    assert(at==#bytes,'stratagem group framing does not span buffer')
    assert(total==s.total_records,'stratagem total record count changed')
    table.sort(records,function(a,c)return a.record_kind<c.record_kind end)
    return records
end
function M.parse(bytes,base,pointers,s,target)
    target=target or target_from_profile(s)
    assert(type(bytes)=='string' and #bytes==s.size and type(pointers)=='string'
        and #pointers==s.entries*8,'stratagem captured sizes')
    assert(s.version==1 and s.info_type==0x7BD60854 and s.stride==400
        and s.entries>=1 and s.entries<=2048 and s.payload_max>=1 and s.payload_max<=64,
        'unsupported StratagemSettings/StratagemInfo schema')
    assert(b.u32(bytes,0)==s.groups and s.groups>=1 and s.groups<=32,'stratagem group count')
    local at,seen,total,selected=4,{},0,nil
    for group=0,s.groups-1 do
        assert(at+40<=#bytes,'truncated stratagem group')
        assert(bytes:sub(at+1,at+4)=='LDLD' and b.u32(bytes,at+4)==s.version
            and b.u32(bytes,at+8)==s.type and b.u32(bytes,at+16)==1
            and b.u32(bytes,at+20)==0,'stratagem framing')
        local root=at+24
        local finish=root+b.u32(bytes,at+12)
        assert(finish<=#bytes and finish>=root+16,'stratagem group bounds')
        local count=b.u32(bytes,root+8)
        assert(count>0 and count<=s.entries and b.u32(bytes,root+12)==0,
            'stratagem row count/reserved')
        local start,row_representation=array_offset(b.pointer(bytes,root),root,base,finish,
            count*s.stride,'stratagem rows')
        for row=0,count-1 do
            local ro=start+row*s.stride
            local kind=b.u32(bytes,ro)
            assert(kind<s.entries and not seen[kind],'stratagem type duplicated/out of range')
            seen[kind]=true;total=total+1
            assert(b.pointer(pointers,kind*8)==base+ro,'stratagem runtime table mismatch')
            local package=b.resource(bytes,ro+168)
            local id=b.u32(bytes,ro+4)
            local possible=package==target.package or id==target.id
                or (target.current_type~=nil and kind==target.current_type)
            if possible then
                assert(package==target.package and id==target.id
                    and (target.current_type==nil or kind==target.current_type),
                    'stratagem identity mismatch')
                local payload_count=b.u32(bytes,ro+160)
                assert(payload_count>=1 and payload_count<=s.payload_max
                    and b.u32(bytes,ro+164)==0,'payload count/reserved')
                if target.payload_count then
                    assert(payload_count==target.payload_count,'payload count changed')
                end
                local payload_at,payload_representation=array_offset(b.pointer(bytes,ro+152),root,
                    base,finish,payload_count*8,'payload list')
                local payloads,matches={},0
                for index=0,payload_count-1 do
                    local value=b.resource(bytes,payload_at+index*8)
                    payloads[#payloads+1]=value
                    if value==target.resource then matches=matches+1 end
                end
                assert(matches==1,'target payload absent/ambiguous')
                if target.group~=nil then assert(group==target.group,'stratagem group changed')end
                if target.row~=nil then assert(row==target.row,'stratagem row changed')end
                assert(not selected,'stratagem owner ambiguous')
                local identity={component='StratagemSettings',component_type=string.format('0x%08X',s.type),
                    record_type='StratagemInfo',record_type_id=string.format('0x%08X',s.info_type),
                    record_index=row,record_kind=kind,group=group,package=package,payload=target.resource,
                    payload_count=payload_count,payloads=payloads,payload_pointer=payload_representation,
                    row_pointer=row_representation,unique_owner=true,owner_count=1}
                selected={bytes=bytes:sub(ro+1,ro+s.stride),index=kind,group=group,row=row,
                    identity=identity,chain={identity},offset=ro,total_records=total}
            end
        end
        at=finish
    end
    assert(at==#bytes,'stratagem group framing does not span buffer')
    assert(total==s.total_records,'stratagem total record count changed')
    assert(selected,'stratagem owner absent')
    selected.total_records=total
    return selected
end
-- While HD2 is still loading, the settings buffer pointer is null or points at
-- memory that is not committed yet: that is transient, not a layout mismatch.
-- A committed allocation with the wrong extent still fails the caller's assertion.
function M.initialized_region(reader,base)
    if base==0 then error('TARGET_UNAVAILABLE: stratagem table not initialized',0)end
    local region=reader.query(base)
    if region.state~=0x1000 or region.allocation_base==0 then
        error('TARGET_UNAVAILABLE: stratagem table not committed',0)
    end
    return region
end
function M.capture(runtime,reader,profile)
    require('hd2runtime/runtime/metrics').count('stratagem.table_captures')
    reader.stage='core/stratagem:module_root'
    local s=profile.stratagem
    local dll=runtime.address(assert(runtime.module('game.dll')))
    local image={base=dll,size=4096,type=0x1000000}
    local h=reader.read(image,0,4096,true)
    assert(h:sub(1,2)=='MZ','module DOS header missing')
    local pe=b.u32(h,60)
    assert(pe>=64 and pe+88<=#h and h:sub(pe+1,pe+4)=='PE\0\0'
        and b.u16(h,pe+24)==0x20B,'module PE32+ framing')
    image.size=b.u32(h,pe+80)
    assert(s.buffer_rva+8<=image.size and s.table_rva+s.entries*8<=image.size,'settings RVA outside image')
    local lead=reader.read(image,s.buffer_rva,8,true)
    local base=b.pointer(lead,0)
    local region=M.initialized_region(reader,base)
    assert(region.base==base and region.allocation_base==base and region.size>=s.size
        and region.size<=s.size+65536,'stratagem allocation extent')
    local owner=region
    local bytes=reader.read(owner,0,s.size,true)
    local pointers=reader.read(image,s.table_rva,s.entries*8,true)
    reader.stage='core/stratagem:grouped_records'
    local result=M.parse(bytes,base,pointers,s)
    result.owner=owner
    return result
end
function M.capture_all(runtime,reader,profile)
    require('hd2runtime/runtime/metrics').count('stratagem.table_captures')
    reader.stage='core/stratagem:module_root'
    local s=profile.stratagem
    local dll=runtime.address(assert(runtime.module('game.dll')))
    local image={base=dll,size=4096,type=0x1000000}
    local h=reader.read(image,0,4096,true)
    assert(h:sub(1,2)=='MZ','module DOS header missing')
    local pe=b.u32(h,60)
    assert(pe>=64 and pe+88<=#h and h:sub(pe+1,pe+4)=='PE\0\0'
        and b.u16(h,pe+24)==0x20B,'module PE32+ framing')
    image.size=b.u32(h,pe+80)
    assert(s.buffer_rva+8<=image.size and s.table_rva+s.entries*8<=image.size,'settings RVA outside image')
    local base=b.pointer(reader.read(image,s.buffer_rva,8,true),0)
    local region=M.initialized_region(reader,base)
    assert(region.base==base and region.allocation_base==base and region.size>=s.size
        and region.size<=s.size+65536,'stratagem allocation extent')
    local bytes=reader.read(region,0,s.size,true)
    local pointers=reader.read(image,s.table_rva,s.entries*8,true)
    reader.stage='core/stratagem:grouped_records'
    return M.parse_all(bytes,base,pointers,s),region
end
return M
