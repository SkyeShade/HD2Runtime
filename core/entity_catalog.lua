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
    -- core/owned_tables.lua membership lists (the beam conversion's add layout): optional, so the SDK's offline
    -- scanner, which bundles only the modules it reads with, captures exactly as before. Empty: nothing changes.
    local lists_ok,owned_lists=pcall(require,'hd2runtime/core/owned_tables')
    if not(lists_ok and type(owned_lists)=='table'and owned_lists.lists_active and owned_lists.lists_active())then
        owned_lists=nil
    end
    for row=0,profile.map_rows-1 do
        local at=28+row*32
        local resource=b.resource(map,at)
        if resource~=ZERO then
            -- Every row's count, pointer and bounds are validated here. A row that fails is STRAY (0.30.3): only its
            -- own resource is refused (a write targeting it fails with this reason through its candidate's
            -- diagnostics); every other row reads as before. Before, one stray row of a resource no write touched
            -- refused every typed write (0.30.2 live: the LAS-12 Sai's row outside the map body, likely another
            -- mod's change). The membership list itself is scanned lazily and only for component candidates.
            -- The one exception: a row naming exactly HD2Runtime's own relocated list (core/owned_tables.lua), whose
            -- bytes are read back from its block and must be exactly the ones it built.
            local own=owned_lists and owned_lists.list_accepts(resource,row,b.pointer(map,at+8),b.pointer(map,at+16))
            local ok,offset,count
            if own then
                ok,offset=pcall(function()
                    local block={base=own.allocation,size=own.size,type=0x20000,protect=0x2}
                    local bytes=reader.read(block,own.list-own.allocation,own.count*2,true)
                    assert(bytes==own.bytes,'entity map row '..row..' (resource '..resource..') names HD2Runtime\'s '
                        ..'relocated membership list, but the list is not as HD2Runtime built it')
                    return bytes
                end)
                count=own.count
            else
                ok,offset,count=pcall(function()
                    local n=b.pointer(map,at+16)
                    assert(n>0 and n<=1024,'membership count bounds')
                    return b.membership(b.pointer(map,at+8),owner.base+28,n*2,size-28,profile.map_rows*32,row,resource,
                        n),n
                end)
            end
            if ok and own then
                local rows=entities[resource] or {}
                rows[#rows+1]={row=row,count=count,members=offset,owned_list=true};entities[resource]=rows
            elseif ok then
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

    -- 0.31.0: the game must read each captured component from exactly this table (core/component_tables.lua). A
    -- component another mod repointed to its own copy is refused alone (its records raise the CONFLICT below); every
    -- other component reads and writes as before. Read-only, per capture. EXPERIMENTAL (exp/multi-beam): a component
    -- the game reads from HD2Runtime's OWN moved copy (core/owned_tables.lua) is read from that copy, rows and records,
    -- so typed writes land where the game reads. Checked before the rows are read (it needs only the schemas).
    local schemas={}
    for _,name in ipairs(names)do
        schemas[name]=assert(profile.components[name],'unknown reviewed component: '..name)
    end
    reader.stage='core/entity_catalog:component_tables'
    local checked,refused,owned=true,{},{}
    if not(type(options)=='table'and options.identity_scan==true)then
        -- Its own coroutine, never a pcall: the reader yields when a busy update has spent its slice, and a yield
        -- cannot cross a pcall in the game's LuaJIT (0.30.2 live: "attempt to yield across C-call boundary"). Each
        -- inner yield is passed up when this capture runs in a coroutine (the read pacing holds); otherwise the check
        -- is resumed at once.
        local co=coroutine.create(function()
            return require('hd2runtime/core/component_tables').check(reader,owner,profile,schemas)
        end)
        local outer=coroutine.running()
        while true do
            local ok,result,own=coroutine.resume(co)
            if not ok then checked,refused=false,result;break end
            if coroutine.status(co)=='dead'then refused,owned=result,own or{};break end
            if outer then coroutine.yield()end
        end
    end

    local candidates,components={},{ }
    for _,name in ipairs(names)do
        reader.stage='core/entity_catalog:'..name
        local c=schemas[name]
        local own=checked and owned[name]
        -- Where this component's rows and records are read: the entity allocation, or the owned copy's allocation
        -- (its framing at the same 32 bytes before the table, its records after the same rows).
        local region,at,records=owner,c.offset-4,c.records
        if own then
            -- A permanent block: read-only after its fill, as the game's own table (protect, as the entity owner's).
            region={base=own.allocation,size=own.size,type=0x20000,protect=0x2}
            at=own.table-32-own.allocation
            records=own.records
        end
        local index=reader.read(region,at,32+c.record_offset,true)
        assert(b.u32(index,0)==c.index and index:sub(5,32)==b.unhex(c.header),
            name..' framing changed')
        if own then
            assert(c.record_offset==c.indices*16 and records>=c.records
                and at+32+c.record_offset+records*c.stride<=region.size,name..' owned copy extent mismatch')
        else
            assert(c.record_offset==c.indices*16
                and c.record_offset+c.records*c.stride<=b.u32(index,20),
                name..' schema extent mismatch')
        end
        local by_record={}
        for row=0,c.indices-1 do
            local at_row=32+row*16
            local resource=b.resource(index,at_row)
            local record=b.u32(index,at_row+8)
            local flags=b.u32(index,at_row+12)
            assert(record<records and flags==0,name..' component index bounds/flags')
            if resource~=ZERO then
                local owners=by_record[record] or {};owners[#owners+1]=resource;by_record[record]=owners
                local candidate=candidates[resource] or {resourceHash=resource,ownership={},diagnostics={}}
                candidate.ownership[name]={component=name,componentType=string.format('0x%08X',c.type),
                    componentIndex=c.index,indexRow=row,recordIndex=record}
                candidates[resource]=candidate
            end
        end
        components[name]={schema=c,by_record=by_record,records={},region=region,table_offset=at+32}
    end
    if not checked then
        local why='TARGET_UNAVAILABLE: the component table pointers could not be checked ('
            ..tostring(refused):gsub('^[^%s:]+:%d+: ','')..')'
        refused={}
        for name in pairs(components)do refused[name]=why end
    end

    -- core/reviewed_edits.lua (EXPERIMENTAL): optional, so the SDK's offline scanner (sdk/tools/snapshot_scan.py),
    -- which bundles only the modules it reads with, captures exactly as before.
    local edits_ok,edits=pcall(require,'hd2runtime/core/reviewed_edits')
    if not(edits_ok and type(edits)=='table'and edits.active)then edits=nil end
    local function member(entry,index)
        if entry.members then
            for n=0,entry.count-1 do if b.u16(entry.members,n*2)==index then return true end end
            return false
        end
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
            -- EXPERIMENTAL (exp/liberator-beam): an in-place edit HD2Runtime itself made and recorded exactly
            -- (core/reviewed_edits.lua): its own by-design diagnostics are dropped and its dormant components refused;
            -- any other state of that entity is foreign. Empty registry: nothing changes.
            if edits and edits.active()then
                local e=rows[1]
                edits.review(candidate,e.members or map:sub(29+e.offset,28+e.offset+e.count*2))
            end
        end
        ordered[#ordered+1]=candidate
    end

    -- strays: {row, resource, reason} of every row refused above (no write to them; diagnostics for a log).
    -- tables: {[component] = reason} of every component whose records are refused (the game reads its table from
    -- another place, or the pointer could not be read).
    -- owned: {[component] = owned entry} of every component read from HD2Runtime's own moved copy (EXPERIMENTAL).
    local catalog={candidates=ordered,strays=strays,tables=refused,owned=owned}
    metrics.elapsed('entity_catalog.build',started)
    function catalog.record(candidate,name)
        local identity=assert(candidate.ownership[name],name..' ownership absent')
        assert(candidate.entityRow~=nil,name..' entity ownership unproven')
        if refused[name]then error(refused[name],0)end
        if candidate.refused and candidate.refused[name]then error(candidate.refused[name],0)end
        local component=components[name]
        local cached=component.records[identity.recordIndex]
        if cached then return cached end
        local c=component.schema
        reader.stage='core/entity_catalog:'..name..':record'
        -- In place: the entity allocation + profile offset + 28 = the table. Owned move: the copy's table offset.
        local offset=component.table_offset+c.record_offset+identity.recordIndex*c.stride
        local record={bytes=reader.read(component.region,offset,c.stride,true),identity=identity,
            owner=component.region,offset=offset,index=identity.recordIndex,component=name,chain={identity},
            owned_table=component.region~=owner or nil}
        component.records[identity.recordIndex]=record
        return record
    end
    return catalog
end
return M
