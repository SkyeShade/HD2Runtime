local b=require('hd2runtime/core/bytes')
local settings=require('hd2runtime/core/settings')
local metrics=require('hd2runtime/runtime/metrics')
local M={}
-- Short-lived sharing of a completed walk between back-to-back operations (guarded
-- operations run one at a time). Reuse re-validates every allocation's identity,
-- extent, protection, and header and re-parses settings; any difference or missing
-- key falls back to a full walk. Adapters without a clock never share.
local SHARE_SECONDS=15
local shared
local function reuse(runtime,reader,profile,needed,now)
    if not(shared and shared.profile==profile and now<=shared.expires)then return nil end
    -- Pass 1: validate every key with uncaptured reads only, so a fallback to the
    -- full walk never leaves partial snapshots behind in the reader.
    local regions={}
    for key in pairs(needed)do
        local cached=shared.regions[key]
        if not cached then return nil end
        reader.stage='runtime/discover:shared:'..key
        local r=reader.query(cached.base)
        if not(r.base==cached.base and r.allocation_base==cached.base and r.size==cached.size
            and r.state==0x1000 and r.type==0x20000 and(r.protect==2 or r.protect==4))then return nil end
        local h=reader.read(r,0,28)
        if key=='entity'then
            if h~=b.unhex(profile.map_header)then return nil end
        elseif key=='entity_deltas'then
            if h~=b.unhex(profile.entity_deltas.header)or r.protect~=2 then return nil end
        else
            local d=profile.settings[key]
            if not(b.u32(h,0)==#d.groups and h:sub(5,28)==b.unhex(d.groups[1].header))then return nil end
        end
        regions[key]=r
    end
    -- Pass 2: capture and parse exactly as the walk does.
    local result={}
    for key,r in pairs(regions)do
        if key=='entity'or key=='entity_deltas'then result[key]=r
        else
            local d=profile.settings[key]
            local bytes=reader.read(r,0,d.size,true)
            reader.stage='core/settings:'..key
            result[key]={owner=r,records=settings.parse(bytes,r.base,d)}
        end
    end
    return result
end
function M.locate(runtime,reader,profile,needed)
    local now=runtime.monotonic_time and runtime.monotonic_time()
    if now then
        local result=reuse(runtime,reader,profile,needed,now)
        if result then metrics.count('discover.shared_reuses');return result end
    end
    reader.stage='runtime/discover:allocation_map'
    metrics.count('discover.walks')
    local page,finish=runtime.system_info()
    assert(page==4096 and finish>65536 and finish<=9007199254740991,'unsupported address space')
    local matches={entity={},entity_deltas={}}
    for key in pairs(profile.settings)do matches[key]={}end
    local cursor=65536
    while cursor<finish do
        local r=reader.query(cursor);cursor=r.base+r.size
        metrics.count('discover.regions')
        if (r.capture_status==nil or r.capture_status==1)
            and r.base==r.allocation_base and r.state==0x1000 and r.type==0x20000
            and (r.protect==2 or r.protect==4) then
            if r.size==profile.entity_region_size then
                local h=reader.read(r,0,28)
                if h==b.unhex(profile.map_header) then matches.entity[#matches.entity+1]=r end
            end
            local deltas=profile.entity_deltas
            if needed.entity_deltas and deltas and r.protect==2
                and r.size>=deltas.size and r.size<=deltas.size+65536 then
                local h=reader.read(r,0,28)
                if h==b.unhex(deltas.header)then matches.entity_deltas[#matches.entity_deltas+1]=r end
            end
            for key,d in pairs(profile.settings)do
                if needed[key] and r.size>=d.size and r.size<=d.size+65536 then
                    local h=reader.read(r,0,28)
                    if b.u32(h,0)==#d.groups and h:sub(5,28)==b.unhex(d.groups[1].header) then
                        local bytes=reader.read(r,0,d.size,true)
                        reader.stage='core/settings:'..key
                        local records=settings.parse(bytes,r.base,d)
                        reader.stage='runtime/discover:allocation_map'
                        matches[key][#matches[key]+1]={owner=r,records=records}
                    end
                end
            end
        end
    end
    local result={}
    for key,requirement in pairs(needed)do
        reader.stage='runtime/discover:'..key
        if #matches[key]==0 then
            if requirement~='optional'then error('TARGET_UNAVAILABLE: '..key..' allocation absent',0)end
        else
            assert(#matches[key]==1,'expected unique '..key..' allocation; found '..#matches[key])
            result[key]=matches[key][1]
        end
    end
    if now then
        -- Record only allocations whose uniqueness this walk just proved.
        local regions={}
        for key in pairs(needed)do
            local item=result[key]
            local r=item and(item.owner or item)
            if r then regions[key]={base=r.base,size=r.size}end
        end
        shared={profile=profile,expires=now+SHARE_SECONDS,regions=regions}
    end
    return result
end
return M
