-- Checked module-relative root and runtime table, extracted from the relay probe.
local b=require('hd2runtime/core/bytes')
local M={}
function M.capture(runtime,reader,profile)
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
    local region=reader.query(base)
    assert(region.base==base and region.allocation_base==base and region.size>=s.size
        and region.size<=s.size+65536,'stratagem allocation extent')
    local owner={base=base,size=s.size}
    local bytes=reader.read(owner,0,s.size,true)
    local pointers=reader.read(image,s.table_rva,s.entries*8,true)
    reader.stage='core/stratagem:grouped_records'
    assert(b.u32(bytes,0)==s.groups,'stratagem group count')
    local at,seen,total,selected=4,{},0,nil
    for group=0,s.groups-1 do
        assert(bytes:sub(at+1,at+4)=='LDLD' and b.u32(bytes,at+4)==1
            and b.u32(bytes,at+8)==s.type and b.u32(bytes,at+16)==1
            and b.u32(bytes,at+20)==0,'stratagem framing')
        local root=at+24
        local ending=root+b.u32(bytes,at+12)
        assert(ending<=#bytes and ending>=root+16,'stratagem group bounds')
        local count=b.pointer(bytes,root+8)
        assert(count>0 and count<=s.entries,'stratagem row count')
        local start=b.pointer(bytes,root)-base
        assert(start>=root+16 and start+count*s.stride<=ending,'stratagem rows outside group')
        for row=0,count-1 do
            local ro=start+row*s.stride
            local kind=b.u32(bytes,ro)
            assert(kind<s.entries and not seen[kind],'stratagem type duplicated/out of range')
            seen[kind]=true;total=total+1
            assert(b.pointer(pointers,kind*8)==base+ro,'stratagem runtime table mismatch')
            local package=b.resource(bytes,ro+168)
            if package==s.package or kind==s.record_type or b.u32(bytes,ro+4)==s.id then
                assert(package==s.package and kind==s.record_type and b.u32(bytes,ro+4)==s.id,
                    'stratagem identity mismatch')
                local pn=b.pointer(bytes,ro+160)
                local po=b.pointer(bytes,ro+152)-base
                assert(pn==1 and po>=root+16 and po+8<=ending,'payload list bounds/count')
                assert(b.resource(bytes,po)==s.resource,'stratagem payload owner mismatch')
                assert(not selected and group==s.group and row==s.row,'stratagem owner absent/ambiguous')
                local identity={component='StratagemSettings',component_type=string.format('0x%08X',s.type),
                    record_type='StratagemInfo',record_index=row,record_kind=kind,group=group,
                    package=package,payload=s.resource,unique_owner=true,owner_count=1}
                selected={bytes=bytes:sub(ro+1,ro+s.stride),index=kind,group=group,row=row,
                    identity=identity,chain={identity}}
            end
        end
        at=ending
    end
    assert(at==#bytes and total==s.total_records and selected,'stratagem structure changed')
    return selected
end
return M
