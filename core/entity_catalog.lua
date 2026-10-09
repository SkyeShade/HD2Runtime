-- Generic, read-only enumeration of reviewed entity component indices.
-- Runtime addresses never leave this module.
local b=require('hd2runtime/core/bytes')
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local ZERO='0x0000000000000000'
local logged_strays={}

local function sorted_keys(values)
    local out={};for key in pairs(values)do out[#out+1]=key end
    table.sort(out);return out
end

-- options.identity_scan: a read-only identity scan (api/weapon_mapper.lua only; it never writes) reads the records'
-- own bytes without the table pointer check. Every write path omits it.
function M.capture(reader,owner,profile,names,options)
    metrics.count('entity_catalog.captures')
    local started=metrics.now()
    reader.stage='core/entity_catalog:entity_map'
    local header=reader.read(owner,0,28)
    assert(header==b.unhex(profile.map_header),'entity map framing changed')
    local size=28+b.u32(header,16)
    assert(size<=owner.size and size>=28+profile.map_rows*32,'entity map extent')
    local map=reader.read(owner,0,size,true)
    local entities,stray,strays={},{},{}
    for row=0,profile.map_rows-1 do
        local at=28+row*32
        local resource=b.resource(map,at)
        if resource~=ZERO then
            -- Every row's count, pointer and bounds are validated here. A row that fails is STRAY (0.30.3): only its
            -- own resource is refused (a write targeting it fails with this reason through its candidate's
            -- diagnostics); every other row reads as before. Before, one stray row of a resource no write touched
            -- refused every typed write (0.30.2 live: the LAS-12 Sai's row outside the map body, likely another
            -- mod's change). The membership list itself is scanned lazily and only for component candidates.
            local ok,offset,count=pcall(function()
                local n=b.pointer(map,at+16)
                assert(n>0 and n<=1024,'membership count bounds')
                return b.membership(b.pointer(map,at+8),owner.base+28,n*2,size-28,profile.map_rows*32,row,resource,n),n
            end)
            if ok then
                local rows=entities[resource] or {}
                rows[#rows+1]={row=row,offset=offset,count=count};entities[resource]=rows
            else
                stray[resource]=tostring(offset):gsub('^[^%s:]+:%d+: ','')
                strays[#strays+1]={row=row,resource=resource,reason=stray[resource]}
            end
        end
    end
    if #strays>0 then
        metrics.count('entity_catalog.stray_rows',#strays)
        -- One log line per stray row and session: writes to that resource are refused, every other write goes ahead.
        for _,s in ipairs(strays)do
            local key=s.row..'|'..s.resource
            if not logged_strays[key]then
                logged_strays[key]=true
                local okl,log=pcall(require,'hd2runtime/runtime/log')
                if okl and log.emit then
                    pcall(log.emit,('[HD2Runtime] entity map row %d (resource %s) is not as reviewed: writes to it are '
                        ..'refused, every other write goes ahead (%s)'):format(s.row,s.resource,s.reason))
                end
            end
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
    -- 0.30.4: the game must read each captured component from exactly this table (core/component_tables.lua). A
    -- component another mod repointed to its own copy is refused alone (its records raise the CONFLICT below); every
    -- other component reads and writes as before. Read-only, per capture.
    local schemas={}
    for name,component in pairs(components)do schemas[name]=component.schema end
    reader.stage='core/entity_catalog:component_tables'
    local checked,refused=true,{}
    if not(type(options)=='table'and options.identity_scan==true)then
        checked,refused=pcall(function()
            return require('hd2runtime/core/component_tables').check(reader,owner,profile,schemas)
        end)
    end
    if not checked then
        local why='TARGET_UNAVAILABLE: the component table pointers could not be checked ('
            ..tostring(refused):gsub('^[^%s:]+:%d+: ','')..')'
        refused={}
        for name in pairs(components)do refused[name]=why end
    end

    local function member(entry,index)
        for n=0,entry.count-1 do if b.u16(map,28+entry.offset+n*2)==index then return true end end
        return false
    end
    local ordered={}
    for _,resource in ipairs(sorted_keys(candidates))do
        local candidate=candidates[resource]
        local rows=entities[resource]
        if stray[resource]then
            candidate.diagnostics[#candidate.diagnostics+1]=stray[resource]
        elseif not rows or #rows~=1 then
            candidate.diagnostics[#candidate.diagnostics+1]=not rows and
                'entity owner absent' or 'entity owner ambiguous'
        else
            candidate.entityRow=rows[1].row
            for name,identity in pairs(candidate.ownership)do
                if not member(rows[1],identity.componentIndex) then
                    candidate.diagnostics[#candidate.diagnostics+1]=name..' membership absent'
                end
                identity.ownerCount=#components[name].by_record[identity.recordIndex]
                identity.uniqueOwner=identity.ownerCount==1
            end
        end
        ordered[#ordered+1]=candidate
    end

    -- strays: {row, resource, reason} of every row refused above (no write to them; diagnostics for a log).
    -- tables: {[component] = reason} of every component whose records are refused (the game reads its table from
    -- another place, or the pointer could not be read).
    local catalog={candidates=ordered,strays=strays,tables=refused}
    metrics.elapsed('entity_catalog.build',started)
    function catalog.record(candidate,name)
        local identity=assert(candidate.ownership[name],name..' ownership absent')
        assert(candidate.entityRow~=nil,name..' entity ownership unproven')
        if refused[name]then error(refused[name],0)end
        local component=components[name]
        local cached=component.records[identity.recordIndex]
        if cached then return cached end
        local c=component.schema
        reader.stage='core/entity_catalog:'..name..':record'
        local offset=c.offset+28+c.record_offset+identity.recordIndex*c.stride
        local record={bytes=reader.read(owner,offset,c.stride,true),identity=identity,
            owner=owner,offset=offset,index=identity.recordIndex,component=name,chain={identity}}
        component.records[identity.recordIndex]=record
        return record
    end
    return catalog
end
return M
