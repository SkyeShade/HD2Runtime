-- Asset (package) residency for reference swaps.
--
-- Helldivers 2 loads an item's generated loadout package only while some system holds a reference on it in
-- game.dll's RefcountedPackageSystem (a player carries the item, level generation placed it, ...). A reference
-- swapped to an item nobody carries points at assets that were never loaded. Runtime requests the same package
-- through that same reference-counted system, waits until the engine reports every part loaded, and only then
-- lets the write proceed.
--
-- Safety:
-- * Package identities come only from the generated catalog (domains/package_residency.lua), keyed by semantic
--   object; callers never supply package or resource IDs.
-- * Before any native call the build fingerprint and the exact code bytes of the request function, the engine
--   has_loaded function and its package lookup are re-proven; the RefcountedPackageSystem instance and its map
--   are validated; the map must have headroom.
-- * Residency is read, never assumed: the engine's resource-manager package list and part states.
-- * Retention: Runtime keeps its reference for the rest of the session. Spawned objects may still use the
--   assets after an operation is disabled, and the native reference count does not track them, so Runtime never
--   releases natively (it cannot prove no live object depends on the package).
local b=require('hd2runtime/core/bytes')
local database=require('hd2runtime/domains/package_residency')
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local loader=database.loader
local engine=loader.engine
local policy=database.policy
local held={}          -- package id (hex) -> {holders={[owner]=true}, label, name}
local held_count=0
local proven={}        -- runtime identity -> pins

local ZERO8=string.rep('\0',8)
-- 0x0123456789ABCDEF -> 8-byte little-endian string (IDs exceed double precision; never use numbers).
local function id_bytes(hex)
    assert(type(hex)=='string'and hex:match('^0x%x%x%x%x%x%x%x%x%x%x%x%x%x%x%x%x$'),'malformed package identity')
    local out={}
    for index=17,3,-2 do out[#out+1]=string.char(tonumber(hex:sub(index,index+1),16))end
    return table.concat(out)
end
M.id_bytes=id_bytes

local function read(runtime,address,size)
    local bytes,why=runtime.read(address,size)
    if not bytes then error('ASSET_UNAVAILABLE: package state unreadable ('..tostring(why)..')',0)end
    return bytes
end
local function pointer(runtime,address)
    local value=b.pointer(read(runtime,address,8),0)
    if value==0 then error('ASSET_UNAVAILABLE: package system not initialised',0)end
    return value
end
local function module_base(runtime,name)
    local handle=runtime.module(name)
    if not handle then error('TARGET_UNAVAILABLE: '..tostring(name or 'executable')..' not loaded',0)end
    return runtime.address(handle)
end
local function prove_bytes(runtime,address,hex,label)
    local expected=b.unhex(hex)
    assert(read(runtime,address,#expected)==expected,'native package loader changed ('..label..')')
end

-- Re-proves the loader for this runtime identity; cheap after the first success.
function M.prove(runtime)
    require('hd2runtime/core/fingerprint').require(runtime)
    local exe,dll=module_base(runtime,nil),module_base(runtime,'game.dll')
    local key=tostring(runtime.mode)..'|'..exe..'|'..dll
    if proven[key]then return proven[key]end
    prove_bytes(runtime,dll+loader.requestRva,loader.requestProof,'RefcountedPackageSystem request')
    prove_bytes(runtime,dll+loader.releaseRva,loader.releaseProof,'RefcountedPackageSystem release')
    prove_bytes(runtime,exe+engine.hasLoadedRva,engine.hasLoadedProof,'engine has_loaded')
    prove_bytes(runtime,exe+engine.findPackageRva,engine.findPackageProof,'engine package lookup')
    local instance=pointer(runtime,dll+loader.instanceGlobalRva)
    local header=read(runtime,instance,32)
    local capacity=b.u32(header,loader.refcountMap.capacity)
    assert(capacity>=16 and capacity<=65536 and capacity%2==0,'package reference map shape changed')
    assert(b.pointer(header,loader.refcountMap.entries)~=0,'package reference map unallocated')
    local pins={exe=exe,dll=dll,instance=instance,request=dll+loader.requestRva,capacity=capacity}
    proven[key]=pins
    return pins
end

-- Fraction of the game's reference map in use (the native insert has no overflow path).
local function map_fill(runtime,pins)
    local header=read(runtime,pins.instance,32)
    local entries=b.pointer(header,loader.refcountMap.entries)
    local raw=read(runtime,entries,pins.capacity*loader.refcountMap.entryStride)
    local used=0
    for index=0,pins.capacity-1 do
        if raw:sub(index*16+1,index*16+8)~=ZERO8 then used=used+1 end
    end
    return used/pins.capacity
end

-- 'resident' | 'loading' (known to the engine, parts still loading) | 'queued' | 'absent'
function M.state(runtime,package_hex)
    if runtime.package_state then return runtime.package_state(package_hex)end  -- offline simulation hook
    metrics.count('assets.state_reads')
    local wanted=id_bytes(package_hex)
    local pins=M.prove(runtime)
    local manager=pointer(runtime,pointer(runtime,pins.exe+engine.managerGlobalRva)+engine.packageManager)
    local resources=pointer(runtime,manager+engine.resourceManager)
    local count=b.u32(read(runtime,resources+engine.listCount,4),0)
    assert(count<=8192,'engine package list bounds')
    if count>0 then
        local list=read(runtime,pointer(runtime,resources+engine.list),count*8)
        for index=0,count-1 do
            local package=b.pointer(list,index*8)
            if read(runtime,package+engine.packageId,8)==wanted then
                local parts=b.u32(read(runtime,package+engine.partCount,4),0)
                if parts==0 or parts>64 then return 'loading'end
                local array=read(runtime,pointer(runtime,package+engine.parts),parts*8)
                for part=0,parts-1 do
                    local state=b.u32(read(runtime,b.pointer(array,part*8)+engine.partState,4),0)
                    if state~=engine.loadedState then return 'loading'end
                end
                return 'resident'
            end
        end
    end
    local q=engine.queue
    local cursor=b.u32(read(runtime,manager+q.head,4),0)
    local tail=b.u32(read(runtime,manager+q.tail,4),0)
    local guard=0
    while cursor~=tail and guard<q.capacity do
        local entry=read(runtime,manager+q.entries+cursor*q.stride,q.stride)
        if entry:sub(1,8)==wanted and entry:byte(q.loadFlag+1)~=0 then return 'queued'end
        cursor=(cursor+1)%q.capacity;guard=guard+1
    end
    return 'absent'
end

-- Resolves the catalog dependency for a semantic key. Unknown keys return nil (never guessed).
function M.dependency(key)
    local item=database.dependencies[key]
    if not item then return nil end
    local package=database.packages[item.package]
    assert(package and package.inBundleDatabase,'catalog package absent from this build')
    return {key=key,package=item.package,label=item.label,name=package.name,via=item.via}
end
function M.dependency_for_resource(resource,label)
    local id=database.byResource[resource]
    if not id then return nil end
    return {key='resource/'..resource,package=id,label=label,name=database.packages[id].name,via='resource'}
end

-- Takes (once per session) Runtime's own reference on a catalog package through the native system.
function M.request(runtime,dependency,owner)
    assert(type(dependency)=='table'and database.packages[dependency.package],'package is not in the catalog')
    local entry=held[dependency.package]
    if entry then entry.holders[owner]=true;return entry end
    assert(held_count<policy.maxHeldPackages,'ASSET_UNAVAILABLE: Runtime package budget reached ('
        ..policy.maxHeldPackages..' packages)')
    local pins=M.prove(runtime)
    if not runtime.package_request then
        error('ASSET_UNAVAILABLE: this runtime cannot request packages ('..tostring(runtime.mode)..')',0)
    end
    assert(map_fill(runtime,pins)<policy.refcountFillLimit,'ASSET_UNAVAILABLE: game package reference map is full')
    metrics.count('assets.native_requests')
    runtime.package_request(pins.request,pins.instance,id_bytes(dependency.package))
    entry={holders={[owner]=true},label=dependency.label,name=dependency.name}
    held[dependency.package]=entry;held_count=held_count+1
    return entry
end
-- Bookkeeping only: Runtime retains its native reference for the session (see header).
function M.release(owner)
    for _,entry in pairs(held)do entry.holders[owner]=nil end
end
function M.holdings()
    local out={}
    for id,entry in pairs(held)do
        local holders={};for owner in pairs(entry.holders)do holders[#holders+1]=owner end
        table.sort(holders)
        out[#out+1]={package=entry.name,label=entry.label,holders=holders,retained=true}
    end
    table.sort(out,function(a,c)return a.package<c.package end)
    return out
end
-- Test hook: forget session state.
function M.reset()held={};held_count=0;proven={}end

-- De-duplicated dependency list for a validated spec (patch/transaction) or plan.
function M.collect(spec)
    local found,seen={},{}
    local function add(list)
        for _,dependency in ipairs(list or{})do
            if not seen[dependency.package]then seen[dependency.package]=true;found[#found+1]=dependency end
        end
    end
    add(spec.asset_dependencies)
    for _,phase in ipairs(spec.phases or{})do
        for _,capture in ipairs(phase.capture_specs or{})do add(capture.asset_dependencies)end
    end
    return found
end

-- Scheduler gate: 'ready' | 'waiting' | 'failed', reason. Requests on the first tick, then polls.
function M.gate(runtime,spec,emit)
    local dependencies=M.collect(spec)
    local gate={dependencies=dependencies,state=#dependencies==0 and'ready'or'waiting'}
    local elapsed,next_poll,requested=0,0,false
    local function log(message)if emit then pcall(emit,'[HD2Runtime] '..message)end end
    function gate.tick(dt)
        if gate.state~='waiting'then return gate.state,gate.reason end
        elapsed=elapsed+dt
        if elapsed<next_poll then return'waiting'end
        next_poll=elapsed+policy.pollSeconds
        local ok,why=pcall(function()
            if not requested then
                for _,dependency in ipairs(dependencies)do M.request(runtime,dependency,spec.id)end
                requested=true
                log('assets for '..spec.id..' requested: '..#dependencies..' package(s)')
            end
            local pending
            for _,dependency in ipairs(dependencies)do
                local state=M.state(runtime,dependency.package)
                if state~='resident'then pending=pending or{dependency=dependency,state=state}end
            end
            return pending
        end)
        if not ok then
            gate.state='failed'
            gate.reason=tostring(why):find('ASSET_UNAVAILABLE',1,true)and tostring(why)
                or'ASSET_UNAVAILABLE: '..tostring(why)
            return gate.state,gate.reason
        end
        if not why then
            gate.state='ready';log('assets for '..spec.id..' resident')
            return'ready'
        end
        gate.pending=why
        if elapsed>policy.loadTimeoutSeconds then
            gate.state='failed'
            gate.reason='ASSET_UNAVAILABLE: '..why.dependency.label..' requires package '..why.dependency.name
                ..'; still '..why.state..' after '..policy.loadTimeoutSeconds..' seconds'
            return gate.state,gate.reason
        end
        return'waiting'
    end
    return gate
end
return M
