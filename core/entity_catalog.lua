-- Generic, read-only enumeration of reviewed entity component indices.
-- Runtime addresses never leave this module.
local b=require('hd2runtime/core/bytes')
local M={}
local ZERO='0x0000000000000000'

local function sorted_keys(values)
    local out={};for key in pairs(values)do out[#out+1]=key end
    table.sort(out);return out
end

function M.capture(reader,owner,profile,names)
    reader.stage='core/entity_catalog:entity_map'
    local header=reader.read(owner,0,28)
    assert(header==b.unhex(profile.map_header),'entity map framing changed')
    local size=28+b.u32(header,16)
    assert(size<=owner.size and size>=28+profile.map_rows*32,'entity map extent')
    local map=reader.read(owner,0,size,true)
    local entities={}
    for row=0,profile.map_rows-1 do
        local at=28+row*32
        local resource=b.resource(map,at)
        if resource~=ZERO then
            local count=b.pointer(map,at+16)
            assert(count>0 and count<=1024,'membership count bounds')
            local offset=b.relative(b.pointer(map,at+8),owner.base+28,count*2,
                size-28,profile.map_rows*32)
            local members={}
            for n=0,count-1 do members[b.u16(map,28+offset+n*2)]=true end
            local rows=entities[resource] or {}
            rows[#rows+1]={row=row,members=members};entities[resource]=rows
        end
    end

    local candidates,components={},{ }
    for _,name in ipairs(names)do
        reader.stage='core/entity_catalog:'..name
        local c=assert(profile.components[name],'unknown reviewed component: '..name)
        local index=reader.read(owner,c.offset-4,32+c.record_offset,true)
        assert(b.u32(index,0)==c.index and index:sub(5,32)==b.unhex(c.header),
            name..' framing changed')
        assert(c.record_offset==c.indices*16
            and c.record_offset+c.records*c.stride<=b.u32(index,20),
            name..' schema extent mismatch')
        local by_record={}
        for row=0,c.indices-1 do
            local at=32+row*16
            local resource=b.resource(index,at)
            local record=b.u32(index,at+8)
            local flags=b.u32(index,at+12)
            assert(record<c.records and flags==0,name..' component index bounds/flags')
            if resource~=ZERO then
                local owners=by_record[record] or {};owners[#owners+1]=resource;by_record[record]=owners
                local candidate=candidates[resource] or {resourceHash=resource,ownership={},diagnostics={}}
                candidate.ownership[name]={component=name,componentType=string.format('0x%08X',c.type),
                    componentIndex=c.index,indexRow=row,recordIndex=record}
                candidates[resource]=candidate
            end
        end
        components[name]={schema=c,by_record=by_record,records={}}
    end

    local ordered={}
    for _,resource in ipairs(sorted_keys(candidates))do
        local candidate=candidates[resource]
        local rows=entities[resource]
        if not rows or #rows~=1 then
            candidate.diagnostics[#candidate.diagnostics+1]=not rows and
                'entity owner absent' or 'entity owner ambiguous'
        else
            candidate.entityRow=rows[1].row
            for name,identity in pairs(candidate.ownership)do
                if not rows[1].members[identity.componentIndex] then
                    candidate.diagnostics[#candidate.diagnostics+1]=name..' membership absent'
                end
                identity.ownerCount=#components[name].by_record[identity.recordIndex]
                identity.uniqueOwner=identity.ownerCount==1
            end
        end
        ordered[#ordered+1]=candidate
    end

    local catalog={candidates=ordered}
    function catalog.record(candidate,name)
        local identity=assert(candidate.ownership[name],name..' ownership absent')
        assert(candidate.entityRow~=nil,name..' entity ownership unproven')
        local component=components[name]
        local cached=component.records[identity.recordIndex]
        if cached then return cached end
        local c=component.schema
        reader.stage='core/entity_catalog:'..name..':record'
        local offset=c.offset+28+c.record_offset+identity.recordIndex*c.stride
        local record={bytes=reader.read(owner,offset,c.stride,true),identity=identity}
        component.records[identity.recordIndex]=record
        return record
    end
    return catalog
end
return M
