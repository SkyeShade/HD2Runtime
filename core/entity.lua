local b=require('hd2runtime/core/bytes')
local M={}
function M.new(reader,owner,profile)
    local header=b.unhex(profile.map_header)
    local size=28+b.u32(header,16)
    local map=reader.read(owner,0,size,true)
    assert(map:sub(1,28)==header,'entity framing changed')
    local cache={}
    return function(resource_key,component_name)
        reader.stage='core/entity:'..component_name
        local key=resource_key..'/'..component_name
        if cache[key] then return cache[key] end
        local resource=assert(profile.resources[resource_key],'unknown resource')
        local target=assert(resource.components[component_name],'component not reviewed for resource')
        local c=assert(profile.components[component_name],'unknown component schema')
        local found
        for row=0,profile.map_rows-1 do
            local at=28+row*32
            if b.resource(map,at)==resource.resource then
                assert(not found,'duplicate entity owner')
                found=row
                local count=b.pointer(map,at+16)
                assert(count>0 and count<=1024,'membership count bounds')
                local offset=b.membership(b.pointer(map,at+8),owner.base+28,count*2,size-28,profile.map_rows*32,row,
                    resource.resource,count)
                assert(row==resource.owner_row and offset==resource.membership_offset,'entity identity changed')
                local members=map:sub(29+offset,28+offset+count*2)
                assert(members==b.unhex(resource.membership),'membership changed')
                local occurrences=0
                for n=0,count-1 do if b.u16(members,n*2)==c.index then occurrences=occurrences+1 end end
                assert(occurrences==1,'component membership absent/ambiguous')
            end
        end
        assert(found,'entity resource absent')
        local framing=reader.read(owner,c.offset-4,32+c.indices*16,true)
        assert(b.u32(framing,0)==c.index and framing:sub(5,32)==b.unhex(c.header),'component framing changed')
        assert(c.record_offset==c.indices*16 and c.record_offset+c.records*c.stride<=b.u32(framing,20),'schema extent mismatch')
        local selected,aliases
        aliases=0
        for row=0,c.indices-1 do
            local at=32+row*16
            local record=b.u32(framing,at+8)
            assert(record<c.records and b.u32(framing,at+12)==0,'component index bounds/flags')
            local id=b.resource(framing,at)
            if id==resource.resource then
                assert(not selected and row==target.row and record==target.record,'resource record mapping changed')
                selected=record
            end
            if id~='0x0000000000000000' and record==target.record then aliases=aliases+1 end
        end
        assert(selected and aliases==1,'component record absent/shared')
        local offset=c.offset+28+c.record_offset+selected*c.stride
        local identity={component=component_name,component_type=string.format('0x%08X',c.type),
            component_index=c.index,record_index=selected,index_row=target.row,entity_row=found,
            record_type=component_name:gsub('Data$',''),unique_owner=true,owner_count=aliases}
        local record={bytes=reader.read(owner,offset,c.stride,true),owner=owner,offset=offset,
            index=selected,component=component_name,
            identity=identity,chain={identity}}
        cache[key]=record;return record
    end
end
return M
