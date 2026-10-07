-- Synced asset loading (DEVELOPMENT; docs/asset-loading.md, "Synced asset loading (development)"). Not exported to mods.
--
-- A mod that loads a package through the Runtime's asset loader (hd2.require_assets, a patch, plan or transaction
-- reference swap, an explosion or spawn action: core/assets.lua gates with spec.shared) makes its networked
-- entities and projectiles use assets the game did not load by itself. Another player of the lobby who runs the SAME
-- Runtime but not that mod has the same object without those assets. This module closes that gap between compatible
-- Runtimes only:
--   * LOCAL SHARED SET: every distinct catalog package a shared gate requested on this machine (M.note), at most
--     M.MAX_SHARED (the rest is logged once as not shared). Runtime-internal gates (custom stratagems, Pelican,
--     explosion donors, beacons, slot conversion, the selector) are never in it: custom stratagems sync their own
--     assets (runtime/custom_stratagems.lua, CUSTOM MP ASSETS).
--   * PUBLISH: the set as one lobby member property under the key `hd2as` (runtime/peer_channel.lua, the game's own
--     PlayFab member data, with the channel's rate limits shared with the `hd2rt` key), in the hd2as/1 grammar
--     (runtime/asset_sync_protocol.lua): this Runtime's version, its catalog hash, a sequence number and the package
--     ids. Nothing is published while the set is empty.
--   * READ: in the Runtime's own update, every M.POLL_EVERY s and only in a joined lobby of at least 2 members, every
--     other member's `hd2as` value. A member whose value decodes, whose Runtime version and catalog hash equal this
--     machine's, gets every listed package this machine's catalog knows (exactly core/assets.request's identity rule)
--     and does not hold yet requested through core/assets.gate ('synced-<peer>'), which proves the loader, checks the
--     reference map headroom and the package budget, and polls residency. A member of another version or catalog is
--     logged once and ignored; an unknown package id is logged once and skipped; a malformed value is refused whole.
-- Safety:
--   * A received value is text that names packages only through this machine's own catalog: never an address, a
--     resource id the catalog does not list, or a value to write. The only native call it can cause is core/assets'
--     own reference request on a catalogued package, with every guard that call always has.
--   * Synced packages never take the whole budget: they are requested only while the Runtime holds fewer than
--     policy.maxHeldPackages - M.RESERVE packages, so this machine's own mods and custom stratagems keep M.RESERVE.
--   * Retention is core/assets': for the session, never released (a peer's entity may still use the package).
--   * A player without the Runtime publishes nothing and cannot be told anything: its game shows what it loaded.
-- NOT proven live: a second member-data key next to `hd2rt`; a client loading a peer's package and the peer's
-- networked entity or projectile then drawing with it on that client; a joiner reading the value of a lobby it joins.
local core_assets=require('hd2runtime/core/assets')
local protocol=require('hd2runtime/runtime/asset_sync_protocol')
local channel=require('hd2runtime/runtime/peer_channel')
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local metadata=require('hd2runtime/domains/metadata')
local M={}
M.KEY='hd2as'
M.BY='asset sync'
M.MAX_SHARED=24
M.POLL_EVERY=3
M.RESERVE=16                 -- of core/assets' budget, never taken by a peer's packages

local shared,shared_count={},0   -- 16 hex digits -> {package (0x...), name, holders = {[owner] = true}}
local seq=0
local dirty=false            -- the set changed since it was last handed to the channel
local published              -- the value last handed to the channel
local catalog                -- this machine's catalog hash, computed once
local peers={}               -- peer hex -> {value, state, reason, asks, requested, resident}
local pending={}             -- {peer, gate, names}: synced gates still loading
local watch,acc=nil,0
local said,said_count={},0

local function log(text)log_module.emit('[HD2Runtime] '..text)end
-- Each distinct message once (bounded: the table starts afresh after 512 distinct lines).
local function say(text)
    if said[text]then return end
    if said_count>=512 then said,said_count={},0 end
    said[text]=true;said_count=said_count+1
    log(text)
end
function M.reset_for_tests()
    if watch then watch.status='cancelled'end
    shared,shared_count,seq,dirty,published,catalog=({}),0,0,false,nil,nil
    peers,pending,watch,acc,said,said_count={},{},nil,0,{},0
end

-- FNV-1a 32 of every package id core/assets accepts (sorted, one per line): equal hashes, equal identities.
function M.catalog_hash()
    if not catalog then
        catalog=require('hd2runtime/runtime/peer_protocol').fnv1a(table.concat(core_assets.catalog_ids(),'\n'))
    end
    return catalog
end
function M.version()return tostring(metadata.version)end

local function holders_text(entry)
    local list={}
    for owner in pairs(entry.holders)do list[#list+1]=owner end
    table.sort(list)
    return table.concat(list,', ')
end

-- A shared gate requested a package (core/assets.gate, spec.shared). Bookkeeping only: the watch publishes.
function M.note(dependency,owner)
    local id=type(dependency)=='table'and dependency.package
    if not core_assets.known(id)then return end
    local hex=id:sub(3):upper()
    local entry=shared[hex]
    owner=tostring(owner or'?')
    if entry then entry.holders[owner]=true;return end
    local name=tostring(dependency.name or id)
    if shared_count>=M.MAX_SHARED then
        say(('SYNCED ASSETS: %s (for %s) is not shared with the lobby: at most %d packages are published'):format(name,
            owner,M.MAX_SHARED))
        return
    end
    shared[hex]={package=id,name=name,holders={[owner]=true}}
    shared_count=shared_count+1
    seq=seq+1;dirty=true
end

-- The set as an hd2as/1 value (nil while empty).
function M.value()
    if shared_count==0 then return nil end
    local list={}
    for hex in pairs(shared)do list[#list+1]=hex end
    return protocol.encode({version=M.version(),catalog=M.catalog_hash(),seq=seq,packages=list})
end

local function publish_step()
    if not dirty then return end
    dirty=false
    local value,why=M.value()
    if not value then
        if why then say('SYNCED ASSETS: the shared set cannot be published ('..tostring(why)..')')end
        return
    end
    published=value
    local hexes={}
    for hex in pairs(shared)do hexes[#hexes+1]=hex end
    table.sort(hexes)
    local parts={}
    for _,hex in ipairs(hexes)do parts[#parts+1]=shared[hex].name..' (for '..holders_text(shared[hex])..')'end
    say(('SYNCED ASSETS: publishing seq %d, %d package(s) for the lobby\'s compatible Runtimes: %s'):format(seq,
        #hexes,table.concat(parts,'; ')))
    local result=channel.publish(value,M.BY,M.KEY)
    if result and(result.status=='refused'or result.status=='failed')then
        say(('SYNCED ASSETS: publish seq %d %s (%s: %s)'):format(seq,result.status,tostring(result.code),
            tostring(result.reason)))
    end
end

-- One member's value: decoded, checked against this machine, and its missing packages requested.
local function process(world,peer,value)
    local q=peers[peer]or{}
    peers[peer]=q
    if q.value==value then return end
    q.value=value
    local d,why=protocol.decode(value)
    if not d then
        q.state,q.reason='refused','malformed: '..tostring(why)
        say(('SYNCED ASSETS: peer %s published a malformed value (%s): ignored'):format(peer,tostring(why)))
        return
    end
    if d.version~=M.version()or d.catalog~=M.catalog_hash()then
        q.state,q.reason='incompatible','Runtime '..d.version..', catalog '..d.catalog
        say(('SYNCED ASSETS: peer %s runs Runtime %s (catalog %s): its assets are not loaded here (this machine runs %s, '
            ..'catalog %s)'):format(peer,d.version,d.catalog,M.version(),M.catalog_hash()))
        return
    end
    local asks,new,names,held={},{},{},{}
    for _,hex in ipairs(d.packages)do
        local id='0x'..hex
        local dependency=core_assets.dependency_for_package(id,'synced from '..peer)
        if not dependency then
            say(('SYNCED ASSETS: peer %s asks for package %s, unknown to this catalog: skipped'):format(peer,hex))
        else
            asks[#asks+1]=dependency.name
            if core_assets.held(id)then held[#held+1]=dependency.name
            else new[#new+1]=dependency;names[#names+1]=dependency.name end
        end
    end
    q.asks=asks
    say(('SYNCED ASSETS: peer %s (seq %d) asks for %d package(s): %s'):format(peer,d.seq,#d.packages,
        #asks>0 and table.concat(asks,', ')or'none known here'))
    if#held>0 then say(('SYNCED ASSETS: peer %s: already held here: %s'):format(peer,table.concat(held,', ')))end
    if#new==0 then q.state=q.state=='loading'and'loading'or'resident';return end
    local policy=require('hd2runtime/domains/package_residency').policy
    local room=policy.maxHeldPackages-M.RESERVE-core_assets.held_count()
    if room<#new then
        local refused={}
        for i=math.max(room,0)+1,#new do refused[#refused+1]=new[i].name;new[i]=nil;names[i]=nil end
        say(('SYNCED ASSETS: peer %s: refused %s (ASSET_UNAVAILABLE: synced packages use at most %d of the Runtime\'s %d '
            ..'packages; %d are kept for this machine\'s own requests)'):format(peer,table.concat(refused,', '),
            policy.maxHeldPackages-M.RESERVE,policy.maxHeldPackages,M.RESERVE))
        if#new==0 then q.state,q.reason='refused','budget';return end
    end
    local gate=core_assets.gate(world.runtime,{id='synced-'..peer,asset_dependencies=new},log_module.emit)
    pending[#pending+1]={peer=peer,gate=gate,names=names}
    q.state,q.requested='loading',names
    gate.tick(0)                              -- the request now, so the next member's budget check counts it
    say(('SYNCED ASSETS: peer %s: requesting %d package(s) here: %s'):format(peer,#new,table.concat(names,', ')))
end

local function gates_step(dt)
    for i=#pending,1,-1 do
        local p=pending[i]
        local state,why=p.gate.tick(dt)
        local q=peers[p.peer]
        if state=='ready'then
            table.remove(pending,i)
            say(('SYNCED ASSETS: peer %s: %d package(s) resident here: %s'):format(p.peer,#p.names,
                table.concat(p.names,', ')))
            if q then q.state='resident';q.resident=p.names end
        elseif state=='failed'then
            table.remove(pending,i)
            say(('SYNCED ASSETS: peer %s: loading failed (%s): %s'):format(p.peer,tostring(why),table.concat(p.names,', ')))
            if q then q.state,q.reason='failed',tostring(why)end
        end
    end
end

-- Every POLL_EVERY s: the own set handed to the channel when it changed, and the lobby's other values read.
local function poll_step()
    publish_step()
    local world=world_module.open()
    if not world then return end
    local lobby=channel.lobby(world)          -- reads only: nothing is called outside a joined lobby
    if not lobby or#lobby.members<2 then return end
    local p=channel.poll(world,{key=M.KEY})
    if not p then return end
    local present={}
    for _,m in ipairs(p.lobby.members)do present[m.peer]=true end
    for peer in pairs(peers)do if not present[peer]then peers[peer]=nil end end   -- left: read afresh if it returns
    for _,entry in ipairs(p.values)do
        if entry.value then process(world,entry.peer,entry.value)end
    end
end

-- Attaches the watch (once). Started at load in the game (api/hd2.lua); idle (one timer) outside a lobby.
function M.start()
    if watch and watch.status=='waiting'then return watch end
    watch={status='waiting',perf_label='synced assets'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        dt=dt or 0
        if#pending>0 then gates_step(dt)end
        acc=acc+dt
        if acc>=M.POLL_EVERY then
            acc=0
            poll_step()
        end
    end
    scheduler.attach(watch)
    return watch
end

-- Diagnostics: the shared set, what was published, and every member read.
function M.status()
    local list={}
    for hex,entry in pairs(shared)do list[#list+1]={package=hex,name=entry.name,holders=holders_text(entry)}end
    table.sort(list,function(a,c)return a.package<c.package end)
    local members={}
    for peer,q in pairs(peers)do members[peer]={state=q.state,reason=q.reason,asks=q.asks,requested=q.requested,
        resident=q.resident}end
    return {version=M.version(),catalog=M.catalog_hash(),seq=seq,shared=list,published=published,peers=members,
        loading=#pending,running=watch~=nil and watch.status=='waiting'}
end
return M
