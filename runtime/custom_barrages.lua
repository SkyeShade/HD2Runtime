-- The NATIVE barrage of a custom stratagem call, on every machine (EXPERIMENTAL; read-only; research peer-messaging
-- "barrage"; local_research/mp/barrage/barrage-notes.md; docs/research/runtime-peer-messaging-F5FEE03DCFDB.md section
-- 15). Nothing here writes the game or calls a game function.
--
-- A custom orbital in native mode (orbital = {pattern, impact_explosion, native = true}) redirects its own beacon's
-- delivery to the pattern donor (e.g. the Orbital 120mm HE Barrage), so the thrower's dispatcher creates that donor's
-- barrage: a NETWORKED game object, the same network id on every machine, each remote copy spawned from the creator's
-- replicated block (seed included). Every copy fires its own shells, sourced from this machine's own barrage entity, and
-- each machine explodes its own copies (the shells have no shot id) [C]. So each compatible Runtime converts its own
-- copies of exactly that barrage's shells, as the Gas EAT converts each machine's copies of its launchers' rockets.
--
-- Which barrage is a custom call's, with no list and no guess [C]: nothing names the beacon, but the barrage carries,
-- replicated, the beacon's creation type (component 131: the CARRIER for a redirected beacon; a native 120mm its own
-- type) and its creator's peer (component 28), and its block's target is the beacon's position. M.instance reads them
-- for one entity (by the bombardment manager's own entity map; the shell's source names the entity). The orchestrator
-- matches them against the calls this machine knows: its own beacon (created here, its own peer), or another machine's
-- beacon (its thrown ball's thrower, its carrier, its position).
--
-- The association (section 18; research/barrage-association, its own pins): the barrage stores NO beacon entity, beacon
-- network id, record entry, call-in key or timestamp [C]. What ties it to its call exactly: the game spawns it inside its
-- beacon's activation update, and its block's target IS the position the dispatcher took from that beacon's state +0x30
-- (+ the row's per-payload offset, none for the 120mm, + a mission scatter, none without an active scatter effect) [C,
-- O]; its creation type IS that beacon state's +0x3D8. So on the CREATING machine M.instance names the beacon that
-- dispatched it (beacon_entity, beacon_network: an owned, activated beacon of that creation type whose dispatch record
-- names this payload and a requested spawn, at exactly the target). On every other machine the beacon is a copy without
-- state: M.beacon_position reads the position every machine holds (the element +0x10 from the creation message).
local world_module=require('hd2runtime/runtime/event_world')
local payload_module=require('hd2runtime/runtime/bombardment_payload')
local b=require('hd2runtime/core/bytes')
local PD=require('hd2runtime/domains/bombardment_payload')
local BR=require('hd2runtime/domains/peer_messaging').barrage
local M={}
M.TOLERANCE=3            -- metres between a barrage's target and its beacon's position
local MG,HD=BR.manager,BR.handle
local AS=BR.association
local EXACT={}
for _,payload in ipairs(AS.exactTarget)do EXACT[payload]=true end

-- The reviewed donor's payload hash ('0x...', as research/bombardment-payload records name it) and its shell types, by
-- stratagem name, or nil.
function M.payload_of(name)
    local entry=require('hd2runtime/domains/stratagem_authoring').stratagems[name]
    local id=entry and entry.root and entry.root.id
    local record=id and PD.records[tostring(id)]
    return record and record.payload or nil,record and record.shells or nil
end

local proven={}
function M.prove(world)
    if proven[world.game]then return true end
    local ok,why=payload_module.prove(world)
    if not ok then return nil,why end
    for _,pin in ipairs(BR.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,('game+%X changed (%s)'):format(pin.rva,pin.label)
        end
    end
    proven[world.game]=true
    return true
end
-- The association pins (the creation path from the activation to the block's target, the beacon's fields): proved
-- once per game image, after M.prove. Only the association fields depend on them.
local associated={}
function M.prove_association(world)
    if associated[world.game]then return true end
    local ok,why=M.prove(world)
    if not ok then return nil,why end
    for _,pin in ipairs(AS.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,('game+%X changed (%s)'):format(pin.rva,pin.label)
        end
    end
    associated[world.game]=true
    return true
end

-- An entity's index in a component's own entity map (keys {u32 entity, i32 index}), or nil.
local function index_of(world,component,at,entity)
    local keys=world.view.pointer(component+at)
    local cap=world.view.u32(component+at+8)
    local empty=world.view.u32(component+at+0xC)
    local mult=world.view.u32(component+at+0x10)
    if not(keys and keys~=0 and cap and cap>0 and cap<=65536 and mult)then return nil end
    local start=world_module.mul32(entity,mult)
    for probe=0,math.min(cap,4096)-1 do
        local slot=world.view.read(keys+((start+probe)%cap)*8,8)
        if not slot then return nil end
        local key=b.u32(slot,0)
        if key==entity then local i=b.u32(slot,4);return i~=4294967295 and i or nil end
        if key==empty then return nil end
    end
    return nil
end
local function f32(raw,o)local ok,v=pcall(b.value,raw,o,'f32');return ok and v or nil end
local function hex(raw)return(raw:reverse():gsub('.',function(c)return('%02X'):format(c:byte())end))end
local function finite(v)return type(v)=='number'and v==v and v~=math.huge and v~=-math.huge end
local function point(raw)
    local x,y,z=raw and f32(raw,0),raw and f32(raw,4),raw and f32(raw,8)
    if finite(x)and finite(y)and finite(z)then return {x=x,y=y,z=z}end
    return nil
end
local function same(a,c)return a~=nil and c~=nil and a.x==c.x and a.y==c.y and a.z==c.z end

-- The beacon whose dispatcher spawned a barrage created HERE (read-only; association pins proved by the caller): among
-- this machine's owned beacons (a state: index below the manager's owned count), the ones that activated (state +0x8E4),
-- whose creation type (state +0x3D8, which component 131 copied) is the barrage's carrier type and whose dispatch record
-- names its payload (state +0x418) and a requested spawn (state +0x8D8 = 10); of those, the ONE whose dispatcher position
-- (state +0x30) is exactly the barrage's target. Returns that beacon {entity, index, network, at}, or nil and why (never
-- a nearest guess: a mission scatter effect moves the target off the beacon, and then nothing is named).
local function dispatcher_beacon(world,inst)
    local redirect=require('hd2runtime/runtime/beacon_redirect')
    local stride=require('hd2runtime/domains/beacon_redirect').state.stride
    local m,why=redirect.manager(world)
    if not m then return nil,tostring(why)end
    local BC=AS.beacon
    local list,exact,nearest={},{},math.huge
    for i=0,m.active-1 do
        local it=redirect.beacon(world,m,i)
        local st=m.state+i*stride
        local activated=it and world.view.read(st+BC.activated,1)
        local payload=activated and activated:byte()~=0 and world.view.read(st+BC.dispatchPayload,8)
        if payload and b.resource(payload,0)==inst.payload and world.view.u32(st+BC.creationType)==inst.carrier_type
            and world.view.u32(st+BC.dispatchSpawn)==BC.spawnRequested then
            local at=point(world.view.read(st+BC.statePosition,12))
            local handle=world.view.pointer(it.handle_slot)
            local network=handle and handle~=0 and world.view.u32(handle+HD.network)or nil
            if network==0x7FFF then network=nil end
            local c={entity=it.entity,index=i,network=network,at=at}
            list[#list+1]=c
            if same(at,inst.target)then exact[#exact+1]=c end
            nearest=math.min(nearest,M.distance(inst.target,at))
        end
    end
    if#exact==1 then return exact[1]end
    if#exact>1 then return nil,('%d owned beacons dispatched it at exactly its target'):format(#exact)end
    if#list==0 then return nil,'no owned activated beacon of its creation type dispatched its payload'end
    return nil,('%d owned beacon%s of its creation type dispatched its payload, none at exactly its target (nearest '
        ..'%.2f m: a mission scatter effect?)'):format(#list,#list==1 and''or's',nearest)
end

-- A beacon's position as the game holds it on this machine, read-only (association pins): {x, y, z, owned, source, raw
-- (the 12 bytes, hex), element = {x, y, z}}. An OWNED beacon (this machine's: it has a state) reports its state +0x30,
-- the very position its dispatcher spawns at (source 'state'); a COPY of another machine's beacon has no state (so
-- runtime/beacons.lua position returns nil for it) and reports its element +0x10, the beacon's spawn position from the
-- creation message (source 'element'), the point the owner's state +0x30 was placement-checked from. Or nil and why.
function M.beacon_position(world,entity)
    local ok,why=M.prove_association(world)
    if not ok then return nil,'UNSUPPORTED_BUILD: '..tostring(why)end
    local redirect=require('hd2runtime/runtime/beacon_redirect')
    local stride=require('hd2runtime/domains/beacon_redirect').state.stride
    local m,mwhy=redirect.manager(world)
    if not m then return nil,tostring(mwhy)end
    local E=AS.beacon.elementPosition
    for i=0,m.count-1 do
        local it=redirect.beacon(world,m,i)
        if it and it.entity==entity then
            local owned=i<m.active
            local element=point(it.raw:sub(E+1,E+12))
            local raw=owned and world.view.read(m.state+i*stride+AS.beacon.statePosition,12)or it.raw:sub(E+1,E+12)
            local at=point(raw)
            if not at then return nil,'its position is unreadable'end
            at.owned,at.source,at.raw,at.element,at.index=owned,owned and'state'or'element',b.hex(raw),element,i
            return at
        end
    end
    return nil,'no beacon '..tostring(entity)..' here'
end

-- One entity as a barrage, read-only: {entity, index, payload ('0x' hex), network (its network id), created_here,
-- carrier_type (the beacon's creation type, component 131), creator (the creator's peer hex, component 28), target
-- {x, y, z}}, or nil and why (not a barrage: 'NOT_A_BARRAGE').
-- With the association pins also (section 18; else association_why names the failed pin and none of these is set):
-- target_raw (the target's 12 bytes, hex), shells and salvos (per salvo, salvos: with the creator's modules), heading,
-- seed (the rest of the replicated block), fired (the shells this machine's copy has fired; the instance holds no
-- timestamp), exact_target (its payload's record puts the target at the spawn position), and for a barrage created HERE:
-- beacon_entity and beacon_network (the owned beacon whose dispatcher spawned it, by dispatcher_beacon above; a copy on
-- another machine has none) or beacon_why.
function M.instance(world,entity)
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD: '..tostring(why)end
    local manager=world.view.pointer(world.game+PD.manager.global)
    if not manager then return nil,'the bombardment manager is unreadable'end
    local i=index_of(world,manager,MG.map,entity)
    local count=world.view.u32(manager+MG.networkCount)
    if not(i and count and i<count)then return nil,'NOT_A_BARRAGE'end
    local handles=world.view.pointer(manager+MG.handles)
    local handle=handles and world.view.pointer(handles+i*8)
    local h=handle and handle~=0 and world.view.read(handle,HD.flags+4)
    if not h or b.u32(h,HD.entity)~=entity then return nil,'its bombardment handle does not name it'end
    local blocks=world.view.pointer(manager+MG.block)
    local block=blocks and world.view.read(blocks+i*MG.blockStride,MG.blockStride)
    local out={entity=entity,index=i,payload='0x'..hex(h:sub(HD.payload+1,HD.payload+8)),network=b.u32(h,HD.network),
        created_here=b.u32(h,HD.flags)%2==1,owner_group=i<(world.view.u32(manager+MG.ownerCount)or 0)}
    if out.network==0x7FFF then out.network=nil end
    if block then
        out.target={x=f32(block,MG.blockTarget),y=f32(block,MG.blockTarget+4),z=f32(block,MG.blockTarget+8)}
    end
    local carrier=world.view.pointer(world.game+BR.carrier.global)
    local ci=carrier and index_of(world,carrier,BR.carrier.map,entity)
    local types=ci and world.view.pointer(carrier+BR.carrier.types)
    out.carrier_type=types and types~=0 and world.view.u32(types+ci*4)or nil
    local creator=world.view.pointer(world.game+BR.creator.global)
    local pi=creator and index_of(world,creator,BR.creator.map,entity)
    local peers=pi and world.view.pointer(creator+BR.creator.peers)
    local raw=peers and peers~=0 and world.view.read(peers+pi*8,8)
    out.creator=raw and world_module.peer_hex(b.u32(raw,0),b.u32(raw,4))or nil
    -- The association fields: only with their own pins; nothing above depends on them.
    local aok,awhy=M.prove_association(world)
    if not aok then out.association_why=awhy;return out end
    if block then
        out.target_raw=b.hex(block:sub(MG.blockTarget+1,MG.blockTarget+12))
        out.shells,out.salvos=b.u32(block,AS.block.shells),b.u32(block,AS.block.salvos)
        out.heading,out.seed=f32(block,AS.block.heading),b.u32(block,AS.block.seed)
    end
    local states=world.view.pointer(manager+AS.state.states)
    out.fired=states and states~=0 and world.view.u32(states+i*AS.state.stride+AS.state.fired)or nil
    out.exact_target=EXACT[out.payload]==true
    if out.created_here and out.exact_target and out.target and out.carrier_type then
        local c,cwhy=dispatcher_beacon(world,out)
        if c then out.beacon_entity,out.beacon_network=c.entity,c.network else out.beacon_why=cwhy end
    end
    return out
end
-- The distance (2D, metres) between a barrage's target and a position, or math.huge.
function M.distance(a,c)
    if not(a and c and a.x and a.y and c.x and c.y)then return math.huge end
    local dx,dy=a.x-c.x,a.y-c.y
    return math.sqrt(dx*dx+dy*dy)
end
function M.reset_for_tests()proven={};associated={}end
return M
