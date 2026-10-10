-- Asset (package) residency for reference swaps.
--
-- Helldivers 2 loads an item's generated loadout package only while some system holds a reference on it in
-- game.dll's RefcountedPackageSystem (a player carries the item, level generation placed it, ...). A reference
-- swapped to an item nobody carries points at assets that were never loaded. Runtime requests the same package
-- through that same reference-counted system, waits until the engine reports every part loaded, and only then
-- lets the write proceed.
--
-- Safety:
-- * Package identities come only from the generated catalogs, keyed by semantic object: domains/package_residency.lua,
--   and a stratagem's call-in package by its stable id (domains/stratagem_slots.lua: the root package the game holds
--   for every type in a mission stratagem record). Callers never supply package or resource IDs.
-- * Before any native call the build fingerprint and the exact code bytes of the request function, the engine
--   has_loaded function and its package lookup are re-proven; the RefcountedPackageSystem instance and its map
--   are validated; the map must have headroom.
-- * Residency is read, never assumed: the engine's resource-manager package list and part states.
-- * Retention: Runtime keeps its reference for the rest of the session. Spawned objects may still use the
--   assets after an operation is disabled, and the native reference count does not track them, so Runtime never
--   releases natively (it cannot prove no live object depends on the package).
local b=require('hd2runtime/core/bytes')
local database=require('hd2runtime/domains/package_residency')
local slots_domain=require('hd2runtime/domains/stratagem_slots')
local stratagem_packages=slots_domain.packages
local call_in_packages=slots_domain.callInPackages or{}
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

-- A stratagem's call-in package, by the StratagemInfo stable id (domains/stratagem_slots.lua), or nil (never guessed).
-- This is the row's own root package (+0xA8) only; a support weapon's comes from its weapon (+0xF8): use
-- dependencies_for_stratagem for everything the mission loader requests.
-- The game's language font packages (0.31.0; research/docs/game-font-text.md): one per language, each a bundle in
-- this build's bundle_database.data, named by domains/ui_fonts.lua (generated from the installed game). The game loads
-- only its selected language's; a mod window that draws text only another language's font has asks for that package
-- (runtime/ui_fonts.lua want), through the same reference-counted system, so its text draws in any game language.
local font_packages={}
do
    local ok,fonts=pcall(require,'hd2runtime/domains/ui_fonts')
    for _,entry in ipairs(ok and type(fonts)=='table'and fonts.game or{})do
        if type(entry.package)=='string'and entry.package:match('^%x+$')and#entry.package==16 then
            font_packages['0x'..entry.package:upper()]={key=entry.key,label=entry.label}
        end
    end
end
-- A language font package as a dependency, by its font key ('zh_hans', 'ko', ...), or nil.
function M.font_dependency(key)
    for id,item in pairs(font_packages)do
        if item.key==key then
            return {key='font/'..key,package=id,label=item.label,name='the game font package of '..item.label,
                via='game_font'}
        end
    end
    return nil
end
local stratagem_ids={}
for id,package in pairs(stratagem_packages)do stratagem_ids[package]=tonumber(id)end
for id,list in pairs(call_in_packages)do
    for _,item in ipairs(list)do stratagem_ids[item.package]=stratagem_ids[item.package]or tonumber(id)end
end
function M.dependency_for_stratagem(stable_id,label)
    local package=stratagem_packages[tostring(stable_id)]
    if not package then return nil end
    return {key='stratagem/'..tostring(stable_id),package=package,label=label or tostring(stable_id),
        name='call-in package of '..(label or tostring(stable_id)),via='stratagem_call_in_package'}
end
-- EVERY call-in package of a stratagem, as the game's mission loader requests them for a record entry (0x1753080,
-- research "callInPackages"): the row's +0xA8 package and its +0xF8 weapon's package (a support weapon has only the
-- latter). A list of dependencies (distinct packages, the loader's order), or nil when none is known (never guessed).
function M.dependencies_for_stratagem(stable_id,label)
    local list=call_in_packages[tostring(stable_id)]
    if not list then
        local one=M.dependency_for_stratagem(stable_id,label)
        return one and{one}or nil
    end
    local out,seen={},{}
    local text=label or tostring(stable_id)
    for _,item in ipairs(list)do
        if not seen[item.package]then
            seen[item.package]=true
            local n=#out+1
            out[n]={key='stratagem/'..tostring(stable_id)..(n>1 and('/'..n)or''),package=item.package,label=text,
                name=(n>1 and'call-in package '..n..' of 'or'call-in package of ')..text,
                via='stratagem_call_in_package_'..string.lower(item.via)}
        end
    end
    return #out>0 and out or nil
end
-- Whether every package of a stratagem's call-in is known (no level- or entity-dependent part this build's research
-- leaves out). By catalogue name.
local incomplete={}
for _,name in ipairs(slots_domain.callInIncomplete or{})do incomplete[name]=true end
function M.call_in_complete(name)return not incomplete[name]end

-- The identity rule of M.request: a package id this build's catalog knows (domains/package_residency.lua, or a
-- stratagem call-in package). runtime/asset_sync.lua refuses every other id a peer names.
function M.known(package)
    return type(package)=='string'and(database.packages[package]~=nil or stratagem_ids[package]~=nil)
end
-- Every id M.known accepts, sorted (the synced asset catalog hash is computed from it).
function M.catalog_ids()
    local out,seen={},{}
    for id in pairs(database.packages)do if not seen[id]then seen[id]=true;out[#out+1]=id end end
    for id in pairs(stratagem_ids)do if not seen[id]then seen[id]=true;out[#out+1]=id end end
    table.sort(out)
    return out
end
-- A known package as a dependency (its catalog name, or the stratagem whose call-in it is), or nil.
function M.dependency_for_package(package,label)
    if not M.known(package)then return nil end
    local entry=database.packages[package]
    local name=entry and entry.name or('call-in package of stratagem '..tostring(stratagem_ids[package]))
    return {key='package/'..package,package=package,label=label or name,name=name,via='synced'}
end
-- Whether Runtime already holds its reference on a package, and how many it holds (policy.maxHeldPackages).
function M.held(package)return held[package]~=nil end
function M.held_count()return held_count end

-- Takes (once per session) Runtime's own reference on a catalog package through the native system.
function M.request(runtime,dependency,owner)
    assert(type(dependency)=='table'and(database.packages[dependency.package]or stratagem_ids[dependency.package]
        or font_packages[dependency.package]),'package is not in the catalog')
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

-- A shared gate's requested package goes to the synced asset set (runtime/asset_sync.lua). Never fatal to the gate.
local function share(dependency,owner)
    pcall(function()require('hd2runtime/runtime/asset_sync').note(dependency,owner)end)
end

-- Scheduler gate: 'ready' | 'waiting' | 'failed', reason. Requests on the first tick, then polls.
-- spec.shared: a mod's own request (hd2.require_assets, patch, plan, transaction, explosion/spawn actions): every
-- package it requests is published to the lobby's compatible Runtimes (runtime/asset_sync.lua), which load it too.
-- Runtime-internal gates never set it (custom stratagems sync their own assets).
function M.gate(runtime,spec,emit)
    local dependencies=M.collect(spec)
    local gate={dependencies=dependencies,state=#dependencies==0 and'ready'or'waiting'}
    if gate.state=='waiting'then
        pcall(function()require('hd2runtime/runtime/init_progress').track('assets',gate)end)
    end
    local elapsed,next_poll,requested=0,0,false
    local function log(message)if emit then pcall(emit,'[HD2Runtime] '..message)end end
    function gate.tick(dt)
        if gate.state~='waiting'then return gate.state,gate.reason end
        elapsed=elapsed+dt
        if elapsed<next_poll then return'waiting'end
        next_poll=elapsed+policy.pollSeconds
        local ok,why=pcall(function()
            if not requested then
                for _,dependency in ipairs(dependencies)do
                    M.request(runtime,dependency,spec.id)
                    if spec.shared then share(dependency,spec.id)end
                end
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
