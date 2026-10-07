-- The live game world as event sources and handles see it (domains/event_natives.lua, docs/events.md).
--
-- open() proves the build fingerprint, game.dll's image size and every pinned instruction the tables were derived
-- from, once per loaded game.dll. Every other function re-reads what it needs: no address survives a call, so a
-- destroyed object can only make a read fail or a check disagree, never be used as if it were valid. Reads go through
-- ReadProcessMemory on the game's own process (runtime/native_view.lua).
local natives=require('hd2runtime/domains/event_natives')
local catalog=require('hd2runtime/domains/event_entities')
local entities,stat_sources=catalog.entities,catalog.sources or{}
local native_view=require('hd2runtime/runtime/native_view')
local b=require('hd2runtime/core/bytes')
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local H,P,A,S,E,T=natives.health,natives.players,natives.playerAvatars,natives.state,natives.engine,natives.stats
local C=natives.corpses
local X=natives.explosion
local PJ,ST=natives.projectile,natives.status
local WI=natives.wielder
local IMAGE_SIZE,EXE_IMAGE_SIZE=natives.source.imageSize,natives.source.exeImageSize
local opened,adapter_override,created

-- Tests and the packaged harness supply their own adapter; in game it is the write-capable adapter (heal calls).
function M.set_runtime(runtime)adapter_override=runtime;opened=nil end
-- One adapter for the session: open() runs several times per update, and building one allocates about 40 closures and
-- FFI buffers. The proven world already kept the first one (a matching key returns it); the adapter holds no state
-- between calls (every read and query goes to the process).
local function adapter()
    if adapter_override then return adapter_override end
    if not created then created=require('hd2runtime/runtime/windows_write').create()end
    return created
end

local function module_base(runtime,view,name,size)
    local label=name or'executable'
    local handle=runtime.module(name)
    if not handle then error('TARGET_UNAVAILABLE: '..label..' not loaded',0)end
    local base=runtime.address(handle)
    local header=view.read(base,4096)
    assert(header and header:sub(1,2)=='MZ',label..' DOS header unreadable')
    local pe=b.u32(header,60)
    assert(pe>=64 and pe+88<=#header and header:sub(pe+1,pe+4)=='PE\0\0',label..' PE header')
    assert(b.u32(header,pe+80)==size,label..' image size changed')
    return base
end
local function prove(runtime)
    require('hd2runtime/core/fingerprint').require(runtime)
    local view=native_view.new(runtime)
    local bases={game=module_base(runtime,view,'game.dll',IMAGE_SIZE),exe=module_base(runtime,view,nil,EXE_IMAGE_SIZE)}
    for _,pin in ipairs(natives.pins)do
        assert(view.proves(bases[pin.module]+pin.rva,pin.hex),'native event structure changed ('..pin.label..' at '
            ..pin.module..'+'..string.format('%X',pin.rva)..')')
    end
    metrics.count('events.world_proofs')
    return {runtime=runtime,view=view,game=bases.game,exe=bases.exe,key=tostring(bases.game)..':'..tostring(bases.exe)}
end

-- The game build against the pinned one: 'matched', 'mismatched' or 'not_ready' (and the reason). It proves no pins
-- and reads no memory; the files are hashed once per loaded module, a mismatch included (core/fingerprint.lua).
function M.build()
    local ok,runtime=pcall(adapter)
    if not ok then return 'not_ready',(tostring(runtime):gsub('^[^%s:]+:%d+: ',''))end
    return require('hd2runtime/core/fingerprint').status(runtime)
end

-- The proven world, or nil and the reason. Re-proven when game.dll's base changes.
function M.open()
    local runtime=adapter()
    local handle,exe=runtime.module('game.dll'),runtime.module(nil)
    local key=handle and exe and(tostring(runtime.address(handle))..':'..tostring(runtime.address(exe)))
    if opened and opened.key==key then return opened end
    local ok,world=pcall(prove,runtime)
    if not ok then return nil,(tostring(world):gsub('^%[string "[^"]*"%]:%d+: ',''):gsub('^[^%s:]+:%d+: ',''))end
    opened=setmetatable(world,{__index=M})
    return opened
end

---------------------------------------------------------------------------------------------------- health --
function M.health_manager(world)return world.view.pointer(world.game+H.global)end

-- Header fields of the health manager, validated. nil when unreadable or implausible.
function M.health_header(world,block)
    local manager=M.health_manager(world)
    if not manager then return nil end
    local header=world.view.fill(block,manager+H.header,H.headerSize)
    if not header then return nil end
    local base=H.header
    local live=header:u32(H.live-base)
    local capacity=header:u32(H.capacity-base)
    local hash=header:u32(H.hashCapacity-base)
    if capacity==0 or capacity>H.maxRecords or live>capacity or hash==0 or hash>65536
        or hash%2~=0 then return nil end
    return {manager=manager,live=live,capacity=capacity,hash_capacity=hash,
        hash_empty=header:u32(H.hashEmpty-base),hash_multiplier=header:u32(H.hashMultiplier-base),
        buckets=header:ptr(H.buckets-base),descriptors=header:ptr(H.descriptors-base),
        records=header:ptr(H.records-base),ext=header:ptr(H.extArray-base)}
end

-- (a*b) mod 2^32, exact for u32 operands (a double product can exceed 2^53).
local function mul32(a,c)
    local low,high=c%65536,math.floor(c/65536)
    return(a*low+((a*high)%65536)*65536)%4294967296
end
M.mul32=mul32
-- entity -> record index through the game's own hash (open addressing, slot = (i + entity*mult) & (cap-1), u32).
function M.find_index(world,header,entity)
    if not header.buckets then return nil end
    local start=mul32(entity,header.hash_multiplier)
    for probe=0,header.hash_capacity-1 do
        local slot=(start+probe)%header.hash_capacity
        local bytes=world.view.read(header.buckets+slot*8,8)
        if not bytes then return nil end
        local key=b.u32(bytes,0)
        if key==entity then
            local index=b.u32(bytes,4)
            return index<header.live and index or nil
        end
        if key==header.hash_empty then return nil end
    end
    return nil
end

-- A live descriptor: {type (16 hex digits), type_lo, type_hi, entity, unit, goid, owned, pointer}. nil if unreadable.
function M.descriptor(world,header,index)
    if not header.descriptors or index>=header.live then return nil end
    local pointer=world.view.pointer(header.descriptors+index*8)
    if not pointer then return nil end
    local bytes=world.view.read(pointer,H.descriptor.size)
    if not bytes then return nil end
    local D=H.descriptor
    local lo,hi=b.u32(bytes,D.type),b.u32(bytes,D.type+4)
    return {type=string.format('%08X%08X',hi,lo),type_lo=lo,type_hi=hi,entity=b.u32(bytes,D.entity),
        unit=b.u32(bytes,D.unit),goid=b.u32(bytes,D.goid),owned=b.u32(bytes,D.flags)%2==1,pointer=pointer}
end

-- Current state of one entity: {index, health, max_health, life, descriptor}. nil when it no longer has health.
function M.entity_state(world,entity)
    local header=M.health_header(world,world.view.slot())
    if not header then return nil end
    local index=M.find_index(world,header,entity)
    if not index then return nil end
    local descriptor=M.descriptor(world,header,index)
    if not descriptor or descriptor.entity~=entity then return nil end
    local record=world.view.read(header.records+index*H.stride,H.stride)
    local ext=header.ext and world.view.read(header.ext+index*H.extStride,H.extStride)
    if not record then return nil end
    local R=H.record
    local life=b.u32(record,R.life)
    local health=b.u32(record,R.health)
    if health>=2147483648 then health=health-4294967296 end
    return {index=index,health=health,max_health=ext and b.u32(ext,H.extFields.maxHealth)or nil,life=life,
        descriptor=descriptor,header=header}
end

-- Catalog facts about an entity type (domains/event_entities.lua).
function M.type_info(type_hex)return entities[type_hex]end
-- The name of a stat source type (a weapon, throwable or stratagem payload entity type), or nil when uncatalogued.
function M.source_name(type_hex)
    local source=stat_sources[type_hex]or entities[type_hex]
    return source and source.name or nil
end

---------------------------------------------------------------------------------------------------- corpses --
-- When the game replaces a dead entity by its corpse it spawns a new entity that takes over the dead one's unit and
-- keeps the dead entity's full id in the corpse record (research/event-mission-F5FEE03DCFDB.json). Returns
-- {origins = {[dead entity id] = corpse index}, descriptors} for every corpse now, or nil when unreadable.
function M.corpses(world,block)
    local manager=world.view.pointer(world.game+C.global)
    if not manager then return nil end
    local count=world.view.u32(manager+C.count)
    if not count or count>C.maxRecords then return nil end
    local result={origins={},count=count,descriptors=world.view.pointer(manager+C.descriptors)}
    if count==0 then return result end
    local records=world.view.pointer(manager+C.records)
    local bytes=records and world.view.fill(block,records,count*C.stride)
    if not bytes or not result.descriptors then return nil end
    for index=0,count-1 do
        local origin=bytes:u32(index*C.stride+C.origin)
        if origin~=0 then result.origins[origin]=index end
    end
    return result
end
-- The corpse entity id at `index` when its descriptor carries `unit` (the corpse took over that unit), else nil.
function M.corpse_entity(world,corpses,index,unit)
    local pointer=corpses.descriptors and world.view.pointer(corpses.descriptors+index*8)
    local bytes=pointer and world.view.read(pointer,H.descriptor.size)
    if not bytes or b.u32(bytes,H.descriptor.unit)~=unit then return nil end
    return b.u32(bytes,H.descriptor.entity)
end

---------------------------------------------------------------------------------------------------- players --
-- The local peer id as two u32 halves (never a double: peer ids exceed 2^53). nil when unreadable.
function M.local_peer(world)
    local user=world.view.pointer(world.game+P.localUser)
    local bytes=user and world.view.read(user+P.localPeer,8)
    if not bytes then return nil end
    return b.u32(bytes,0),b.u32(bytes,4)
end
function M.peer_hex(lo,hi)return string.format('%08X%08X',hi,lo)end

-- Players in the game's player list: {slot, peer, peer_lo, peer_hi, entity, local, lifecycle, avatar_network_id,
-- avatar}. avatar (with_avatars) is the avatar entity id resolved through the network id map, nil when the player has
-- none. Empty when unreadable. The slot is the list index, which is not stable (players can be reordered).
function M.players(world,with_avatars)
    local manager=world.view.pointer(world.game+P.global)
    local result={}
    if not manager then return result end
    local count=world.view.u32(manager+P.count)
    if not count or count>P.maxPlayers then return result end
    local lo,hi=M.local_peer(world)
    for slot=0,count-1 do
        local block=world.view.read(manager+P.peers+slot*P.peerStride,P.peerStride)
        local descriptor=world.view.pointer(manager+P.descriptors+slot*8)
        local entity=descriptor and world.view.u32(descriptor+P.descriptorEntity)
        if block then
            local plo,phi=b.u32(block,0),b.u32(block,4)
            local player={slot=slot,peer=M.peer_hex(plo,phi),peer_lo=plo,peer_hi=phi,entity=entity,
                ['local']=plo==lo and phi==hi,lifecycle=b.u32(block,A.lifecycle-P.peers)}
            if with_avatars then
                player.avatar_network_id=world.view.u32(manager+A.avatarId+slot*A.avatarIdStride)
                player.avatar=M.network_entity(world,player.avatar_network_id)
            end
            result[#result+1]=player
        end
    end
    return result
end

------------------------------------------------------------------------------------------------ game state --
-- {state=<number>, name=<string>, mission=<bool>, host=<bool|nil>, mode=<string|nil>} or nil when unreadable.
-- mission: the game is in its Mission state and a game_mode object exists. host: this peer has authority over it.
function M.game_state(world)
    local game=world.view.pointer(world.game+S.game)
    local value=game and world.view.u32(game+S.state)
    if not value or value>16 then return nil end
    local result={state=value,name=S.names[value+1]or('state '..value),mission=false}
    if value~=S.mission then return result end
    local mode=world.view.pointer(world.game+S.gameMode)
    if not mode then return result end
    local count=world.view.u32(mode+S.gameModeCount)
    if count~=1 then return result end
    result.mission=true
    local descriptor=world.view.pointer(mode+S.gameModeDescriptor)
    local flags=descriptor and world.view.u32(descriptor+S.descriptorFlags)
    if flags then result.host=flags%2==1 end
    local mode_type=world.view.u32(mode+S.gameModeType)
    result.mode=mode_type and S.modeNames[mode_type+1]or nil
    result.mode_entity=descriptor and world.view.u32(descriptor+S.descriptorEntity)or nil
    return result
end

------------------------------------------------------------------------------------------- engine identity --
-- True while the engine still holds this entity id (its 8-bit generation matches); destroying an entity advances
-- the generation, so every stale copy of the id fails. nil when unreadable.
function M.entity_exists(world,id)
    if type(id)~='number'or id<=0 or id>=4294967296 then return false end
    local index,generation=id%4194304,math.floor(id/4194304)%256
    local manager=world.view.pointer(world.exe+E.entities)
    if not manager then return nil end
    local size=world.view.u32(manager+E.generationSize)
    local bytes=world.view.pointer(manager+E.generations)
    if not size or not bytes then return nil end
    if index>=size then return false end
    local current=world.view.read(bytes+index,1)
    if not current then return nil end
    return current:byte()==generation
end

-- A unit's root position {x,y,z}, or nil. The unit must still be registered with the same generation, its object
-- must still carry the unit id, and its scene-graph accessor must be the reviewed one (lea rax,[rcx+0x60]; ret).
-- The world pose array of a unit (its root node's 4x4 world matrix first), after the generation, identity and
-- scene-graph accessor checks; nil otherwise.
local function unit_poses(world,unit)
    if type(unit)~='number'or unit<=0 or unit>=4294967296 then return nil end
    local index,generation=unit%4194304,math.floor(unit/4194304)%256
    local registry=world.view.pointer(world.exe+E.units)
    if not registry then return nil end
    local count=world.view.u32(registry+E.unitCount)
    local generations=world.view.pointer(registry+E.unitGenerations)
    local objects=world.view.pointer(registry+E.unitObjects)
    if not count or not generations or not objects or index>=count then return nil end
    local current=world.view.read(generations+index,1)
    if not current or current:byte()~=generation then return nil end
    local object=world.view.pointer(objects+index*8)
    if not object or world.view.u32(object+E.unitId)~=unit then return nil end
    local vtable=world.view.pointer(object)
    local method=vtable and world.view.pointer(vtable+0xE8)
    if method~=world.exe+E.sceneGraphMethod or not world.view.proves(method,E.sceneGraphMethodBytes)then return nil end
    return world.view.pointer(object+E.sceneGraphOffset+E.poses)
end
function M.unit_position(world,unit)
    local poses=unit_poses(world,unit)
    local bytes=poses and world.view.read(poses+E.translation,12)
    if not bytes then return nil end
    local x,y,z=b.value(bytes,0,'f32'),b.value(bytes,4,'f32'),b.value(bytes,8,'f32')
    if x~=x or y~=y or z~=z or math.abs(x)>100000 or math.abs(y)>100000 or math.abs(z)>100000 then return nil end
    return {x=x,y=y,z=z}
end
-- A unit's root world pose: {position, right, forward, up}. The rotation is rows 0..2 of the same 4x4 world matrix
-- whose row 3 (E.translation) unit_position reads, and the axes follow the engine's convention (+X right, +Y forward,
-- +Z up): in every retained snapshot the local avatar's root is an exact upright rotation (row 2 = +Z) with its held
-- weapon to its +X side, and a weapon held in the hands points along the avatar's +Y. nil when unreadable, not
-- finite, or not an orthonormal rotation (a scaled or corrupt matrix). Read-only and internal: the custom projectile
-- development proof aims with it; no public API exposes it.
function M.unit_pose(world,unit)
    local poses=unit_poses(world,unit)
    local bytes=poses and E.translation==48 and world.view.read(poses,60)
    if not bytes then return nil end
    local rows={}
    for row=0,3 do
        local x,y,z=b.value(bytes,row*16,'f32'),b.value(bytes,row*16+4,'f32'),b.value(bytes,row*16+8,'f32')
        if x~=x or y~=y or z~=z or math.abs(x)>100000 or math.abs(y)>100000 or math.abs(z)>100000 then return nil end
        rows[row]={x=x,y=y,z=z}
    end
    local function dot(p,q)return p.x*q.x+p.y*q.y+p.z*q.z end
    for i=0,2 do
        if math.abs(dot(rows[i],rows[i])-1)>0.02 then return nil end
        for j=i+1,2 do if math.abs(dot(rows[i],rows[j]))>0.02 then return nil end end
    end
    return {position=rows[3],right=rows[0],forward=rows[1],up=rows[2]}
end

-- network id -> entity id through the game's own map ({slots, cap, empty, mult}; entity = em+0xF32F20+24*slot).
function M.network_entity(world,network_id)
    if not network_id or network_id==A.noNetworkId then return nil end
    local manager=world.view.pointer(world.game+A.entities)
    if not manager then return nil end
    local header=world.view.read(manager+A.mapSlots,20)
    if not header then return nil end
    local slots=b.pointer(header,0)
    local capacity,empty,multiplier=b.u32(header,8),b.u32(header,12),b.u32(header,16)
    if slots==0 or capacity==0 or capacity>1048576 or capacity%2~=0 then return nil end
    local start=M.mul32(network_id,multiplier)
    for probe=0,math.min(capacity,4096)-1 do
        local bytes=world.view.read(slots+((start+probe)%capacity)*8,8)
        if not bytes then return nil end
        local key=b.u32(bytes,0)
        if key==network_id then return world.view.u32(manager+A.entityBase+b.u32(bytes,4)*A.entityStride)end
        if key==empty then return nil end
    end
    return nil
end

------------------------------------------------------------------------------------------------------ stats --
local function lookup(world,slots,capacity,empty,multiplier,key,stride,value_offset)
    if not slots or capacity==0 or capacity>65536 or capacity%2~=0 then return nil end
    local start=M.mul32(key,multiplier)
    for probe=0,capacity-1 do
        local at=slots+((start+probe)%capacity)*stride
        local bytes=world.view.read(at,8)
        if not bytes then return nil end
        local found=b.u32(bytes,0)
        if found==key then return b.u32(bytes,value_offset)end
        if found==empty then return false end
    end
    return false
end

-- A player's mission stats by source, as the game keeps them: {totals = {[key] = n}, main = {[key] = n},
-- sources = {[type hex] = {[key] = n}}} for the given stat keys. The kill-credit listener records each stat under the
-- source entity's type (a weapon, throwable or stratagem payload); the main table holds the unattributed part.
function M.stat_breakdown(world,player_entity,keys,block)
    local score=world.view.pointer(world.game+T.score)
    if not score or not player_entity then return nil end
    local map=world.view.read(score+T.indexSlots,20)
    if not map then return nil end
    local index=lookup(world,b.pointer(map,0),b.u32(map,8),b.u32(map,12),b.u32(map,16),player_entity,8,4)
    if not index or index>=T.maxPlayers then return nil end
    local record=world.view.read(score+T.recordBase+index*T.recordStride,T.recordStride)
    if not record then return nil end
    local wanted={}
    for _,key in ipairs(keys)do wanted[key]=true end
    local result={totals={},main={},sources={}}
    for _,key in ipairs(keys)do
        local value=lookup(world,b.pointer(record,T.tableEntries),b.u32(record,T.tableCapacity),b.u32(record,T.tableEmpty),
            b.u32(record,T.tableMultiplier),key,T.entryStride,T.entryValue)
        if value==nil then return nil end
        value=value and(value>=2147483648 and value-4294967296 or value)or 0
        result.main[key],result.totals[key]=value,value
    end
    local sources=b.pointer(record,T.sources)
    if sources~=0 then
        local blocks=world.view.fill(block,sources,T.sourceBlocks*T.sourceStride)
        if not blocks then return nil end
        for index=0,T.sourceBlocks-1 do
            local base=index*T.sourceStride
            local lo,hi=blocks:u32(base),blocks:u32(base+4)
            if lo~=0 or hi~=0 then
                local source
                for entry=0,T.sourceEntryCount-1 do
                    local at=base+T.sourceEntries+entry*T.entryStride
                    local found=blocks:u32(at)
                    if found==0 then break end
                    if wanted[found]then
                        local value=blocks:i32(at+T.entryValue)
                        if not source then
                            local type_hex=string.format('%08X%08X',hi,lo)
                            source=result.sources[type_hex]or{}
                            result.sources[type_hex]=source
                        end
                        source[found]=(source[found]or 0)+value
                        result.totals[found]=result.totals[found]+value
                    end
                end
            end
        end
    end
    return result
end
-- A player's mission stat total, as the game's own get_stat computes it: the main table value plus every source
-- block entry with that key. player_entity is the player's entity (the player list descriptor +8). nil if unreadable.
function M.stat_total(world,player_entity,key,block)
    local stats=M.stat_breakdown(world,player_entity,{key},block)
    return stats and stats.totals[key]or nil
end

------------------------------------------------------------------------------------------------ explosions --
-- The explosion settings record of a type (its first field is the type), or nil: the drain's own lookup table.
function M.explosion_settings(world,kind)
    if type(kind)~='number'or kind<=0 or kind>=X.typeBound or kind%1~=0 then return nil end
    local record=world.view.pointer(world.game+X.settingsTable+kind*8)
    if not record or world.view.u32(record)~=kind then return nil end
    return record
end
-- The game's own explosion request, from the main thread (a callback or timer). Refused unless: the request
-- function's exact prologue bytes match, the queue is readable with headroom, the type's settings record carries
-- that type, the position is finite and in range, and the source and owner entities exist. spec: {type, x, y, z,
-- source, owner, peer_lo, peer_hi}. Returns true, or nil and the reason.
function M.explode(world,spec)
    local runtime=world.runtime
    if not runtime.native_explosion then return nil,'EXPLOSION_UNAVAILABLE: this Runtime adapter cannot call game functions'end
    if not world.view.proves(world.game+X.rva,X.prologue)then
        return nil,'EXPLOSION_UNAVAILABLE: the game explosion request changed'
    end
    local queue=world.view.pointer(world.game+X.queue)
    local count=queue and world.view.u32(queue+X.count)
    if not count then return nil,'EXPLOSION_UNAVAILABLE: the explosion queue is unreadable'end
    if count>=X.capacity then return nil,'QUEUE_FULL: the game explosion queue is full this frame'end
    if not M.explosion_settings(world,spec.type)then
        return nil,'UNKNOWN_EXPLOSION: the game has no settings record for explosion type '..tostring(spec.type)
    end
    for _,axis in ipairs({'x','y','z'})do
        local v=spec[axis]
        if type(v)~='number'or v~=v or math.abs(v)>100000 then return nil,'the position must be finite world coordinates'end
    end
    if M.entity_exists(world,spec.source)~=true or M.entity_exists(world,spec.owner)~=true then
        return nil,'the source entity no longer exists'
    end
    runtime.native_explosion(world.game+X.rva,queue,spec.x,spec.y,spec.z,spec.type,spec.source,spec.owner,
        spec.peer_lo,spec.peer_hi)
    metrics.count('events.native_explosions')
    return true
end
-- The explosion queue's first `slots` entries as they are now, read-only: {{x, y, z, type, source, owner, peer_lo,
-- peer_hi}, ...}, or nil when unreadable. The game drains the queue every frame (its count back to 0) without clearing
-- an entry, so an entry stays readable until a later request reuses its slot: this frame's requests, then stale ones of
-- earlier frames. An explosive's own detonation is queued with its type, its own entity as the source and its instance's
-- owner and creditor (event natives pins).
function M.explosion_queue(world,slots)
    local queue=world.view.pointer(world.game+X.queue)
    local n=math.min(slots or 0,X.capacity)
    local raw=queue and n>0 and world.view.read(queue+X.entry,n*X.stride)
    if not raw then return nil end
    local out={}
    for i=0,n-1 do
        local at=i*X.stride
        out[#out+1]={x=b.value(raw,at,'f32'),y=b.value(raw,at+4,'f32'),z=b.value(raw,at+8,'f32'),
            type=b.u32(raw,at+X.entryType),source=b.u32(raw,at+X.entrySource),owner=b.u32(raw,at+X.entryOwner),
            peer_lo=b.u32(raw,at+X.entryCreditor),peer_hi=b.u32(raw,at+X.entryCreditor+4)}
    end
    metrics.count('events.explosion_queue_reads')
    return out
end

------------------------------------------------------------------------------------------------------ heal --
-- The game's own AddHealthFraction(health manager, entity, fraction) on the LOCAL player's avatar, from the main
-- thread (the update callback). Refused unless: the prologue bytes are exactly the reviewed ones, the entity is a
-- Helldiver avatar owned by this peer, alive (not downed or dead) and below its maximum. The game clamps to maximum.
-- Returns the amount requested (after Runtime's own clamp) or nil and the reason.
-------------------------------------------------------------------------------------------------- equipped --
local function power_of_two(n)
    if n<1 or n%1~=0 then return false end
    while n>1 do if n%2~=0 then return false end n=n/2 end
    return true
end
-- A value in one of the game's open-addressed u32 hashes, whose 20-byte header is {buckets u64, capacity u32, empty
-- key u32, multiplier u32}: slot = (key * multiplier + i) & (capacity - 1). nil when absent or unreadable.
local function hash_value(world,header_address,key)
    if type(key)~='number'or key<=0 or key>=4294967296 or key%1~=0 then return nil end
    local header=world.view.read(header_address,20)
    if not header then return nil end
    local buckets=b.pointer(header,0)
    local capacity,empty,multiplier=b.u32(header,8),b.u32(header,12),b.u32(header,16)
    if buckets==0 or capacity>1048576 or not power_of_two(capacity)then return nil end
    local start=mul32(key,multiplier)
    for probe=0,math.min(capacity,4096)-1 do
        local bytes=world.view.read(buckets+((start+probe)%capacity)*8,8)
        if not bytes then return nil end
        local found=b.u32(bytes,0)
        if found==key then
            local value=b.u32(bytes,4)
            return value~=4294967295 and value or nil
        end
        if found==empty then return nil end
    end
    return nil
end
-- An entity's descriptor through the game's own entity map, only when it names that same entity; nil otherwise.
local function entity_descriptor(world,entity)
    local manager=world.view.pointer(world.game+WI.entities)
    if not manager then return nil end
    local index=hash_value(world,manager+WI.entityMap,entity)
    if not index or index>=0x100000 then return nil end
    local descriptor=world.view.read(manager+WI.descriptors+index*WI.descriptorStride,WI.descriptorStride)
    if not descriptor or b.u32(descriptor,WI.descriptorEntity)~=entity then return nil end
    return descriptor
end
-- An entity's type (16 hex digits) through the game's own entity map; the descriptor must name the same entity.
function M.entity_type(world,entity)
    local descriptor=entity_descriptor(world,entity)
    if not descriptor then return nil end
    return string.format('%08X%08X',b.u32(descriptor,4),b.u32(descriptor,0))
end
-- An entity's network id through the game's own entity map (the descriptor's +0x10, as in the health descriptor),
-- accepted only when the network id map resolves it back to that entity; nil otherwise (none, or not networked).
-- Read-only: network ids are the same on every machine, entity ids are not (multiplayer logs correlate by them).
function M.entity_network(world,entity)
    local descriptor=entity_descriptor(world,entity)
    local network=descriptor and b.u32(descriptor,H.descriptor.goid)
    if not network or network==A.noNetworkId or M.network_entity(world,network)~=entity then return nil end
    return network
end
-- An entity's unit through the game's own entity map (the descriptor's unit, as in the health descriptor), or nil
-- when the entity is unknown or has no unit. Read-only and internal (the custom projectile development proof).
function M.entity_unit(world,entity)
    local descriptor=entity_descriptor(world,entity)
    local unit=descriptor and b.u32(descriptor,H.descriptor.unit)
    return unit and unit~=0 and unit or nil
end
-- What an avatar holds now (research/event-wielder-F5FEE03DCFDB.json): {entity (or nil), type, selection, slot,
-- slot_proven} from wielder slot 0 and the inventory selection the same switch writes. Everything is re-read: an
-- entity that no longer exists, or whose descriptor names another entity, is reported as nothing held.
-- Returns nil and the reason when the records are unreadable.
function M.equipped(world,avatar)
    if type(avatar)~='number'or avatar<=0 then return {entity=nil}end
    local wielder=world.view.pointer(world.game+WI.wielder)
    if not wielder then return nil,'the wielder manager is unreadable'end
    local selection
    local inventory=world.view.pointer(world.game+WI.inventory)
    if inventory then
        local record=hash_value(world,inventory+WI.inventoryHash,avatar)
        local records=record and record<0x10000 and world.view.pointer(inventory+WI.records)
        selection=records and world.view.u32(records+record*WI.recordStride+WI.selection)or nil
    end
    local selected=selection and WI.selections[selection]
    local result={selection=selection,slot=selected and selected.slot or nil,slot_proven=selected and selected.proven or false}
    local instance=hash_value(world,wielder+WI.wielderHash,avatar)
    if not instance or instance>=0x10000 then return result end
    local slots=world.view.pointer(wielder+WI.slots)
    local held=slots and world.view.u32(slots+instance*WI.stride)
    if held==nil then return nil,'the wielder slot is unreadable'end
    if held==0 or held==avatar or M.entity_exists(world,held)~=true then return result end
    local type_hex=M.entity_type(world,held)
    if not type_hex then return result end
    result.entity,result.type=held,type_hex
    return result
end

----------------------------------------------------------------------------------------- projectiles/status --
-- A settings record that carries its type (+0) in a pointer table indexed by type, or nil. The game's own lookups
-- (projectile wrapper, status apply) do not bound or null-check the type, so every request checks this first.
local function typed_record(world,table_rva,kind,count)
    if type(kind)~='number'or kind<=0 or kind>=count or kind%1~=0 then return nil end
    local record=world.view.pointer(world.game+table_rva+kind*8)
    if not record or world.view.u32(record)~=kind then return nil end
    return record
end
local function finite(spec,keys,limit)
    for _,key in ipairs(keys)do
        local v=spec[key]
        if type(v)~='number'or v~=v or math.abs(v)>limit then return false end
    end
    return true
end
-- The game's own projectile wrapper, from the main thread (a callback or timer). Refused unless: the wrapper's
-- exact prologue bytes match, the projectile system is active (a mission), the type's settings record carries that
-- type, the position is finite, the direction is a unit vector and the entity exists. spec: {type, x, y, z, dx, dy,
-- dz, entity}. Returns true, or nil and the reason.
function M.projectile(world,spec)
    local runtime=world.runtime
    if not runtime.native_projectile then
        return nil,'PROJECTILE_UNAVAILABLE: this Runtime adapter cannot call game functions'
    end
    if not world.view.proves(world.game+PJ.rva,PJ.prologue)then
        return nil,'PROJECTILE_UNAVAILABLE: the game projectile function changed'
    end
    local system=world.view.pointer(world.game+PJ.system)
    local flag=system and world.view.read(system+PJ.active,1)
    if not flag then return nil,'PROJECTILE_UNAVAILABLE: the projectile system is unreadable'end
    if flag:byte()~=1 then return nil,'NOT_IN_MISSION: the projectile system is not active'end
    if not typed_record(world,PJ.settingsTable,spec.type,PJ.typeCount)then
        return nil,'UNKNOWN_PROJECTILE: the game has no settings record for projectile type '..tostring(spec.type)
    end
    if not finite(spec,{'x','y','z'},100000)then return nil,'INVALID_POSITION: the position must be finite world coordinates'end
    if not finite(spec,{'dx','dy','dz'},1.0001)or math.abs(spec.dx^2+spec.dy^2+spec.dz^2-1)>=1e-3 then
        return nil,'INVALID_DIRECTION: the direction must be a unit vector'
    end
    if M.entity_exists(world,spec.entity)~=true then return nil,'NO_LOCAL_AVATAR: the firing entity no longer exists'end
    runtime.native_projectile(world.game+PJ.rva,system,spec.type,spec.x,spec.y,spec.z,spec.dx,spec.dy,spec.dz,
        spec.entity)
    metrics.count('events.native_projectiles')
    return true
end
------------------------------------------------------------------------------------ custom projectile rows --
-- Runtime-owned custom projectile rows (docs/custom-projectile-rows.md, domains/projectile_rows.lua).
local rows_domain=require('hd2runtime/domains/projectile_rows')
local projectile_rows=require('hd2runtime/core/projectile_rows')
local scheduler=require('hd2runtime/runtime/scheduler')
local RS=rows_domain.spawn

-- The live vanilla row of a projectile type (a string of the row size), only when its settings table entry carries
-- that type; nil otherwise. Read-only; the second result is the row's address.
function M.projectile_row(world,kind)
    local record=typed_record(world,PJ.settingsTable,kind,PJ.typeCount)
    local bytes=record and world.view.read(record,projectile_rows.SIZE)
    if not bytes then return nil end
    return bytes,record
end
-- Every projectile row pin (SpawnProjectile's descriptor and row reads, the copied members, the late lookups, the fire
-- path and FireProjectile's template), proven once per loaded game.dll. true, or nil and the first mismatch. Only
-- custom projectiles depend on these pins.
function M.prove_projectile_rows(world)
    if world.projectile_rows_proven then return true end
    if rows_domain.source.gameDllSha256~=natives.source.gameDllSha256 then
        return nil,'the projectile row research covers another game.dll build'
    end
    for _,pin in ipairs(rows_domain.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,'native projectile structure changed ('..pin.label..' at game+'..string.format('%X',pin.rva)..')'
        end
    end
    world.projectile_rows_proven=true
    return true
end
-- The game's own SpawnProjectile with a Runtime-owned row, on the game thread only. Refused unless: this runs inside
-- the game update, SpawnProjectile's exact prologue bytes and every projectile row pin match, the projectile system is
-- active (a mission), the base type's vanilla row resolves and carries it, the Runtime-owned row reads back and is a
-- VALID hybrid of that live vanilla row (row+0 is the base type; every LATE_LOOKUP, FIRE_PATH_LOOKUP and UNKNOWN byte
-- equals it), the position is finite, the direction is a unit vector, source and owner exist and the creditor is a
-- peer id. spec: {row, base_type, x, y, z, dx, dy, dz, source, owner, peer_lo, peer_hi}. Returns {slot, report,
-- base} (base = the live vanilla row bytes), or nil, the reason and the validation report when it was made.
function M.spawn_projectile_row(world,spec)
    local runtime=world.runtime
    if not(runtime.native_spawn_projectile and runtime.owned_block)then
        return nil,'CUSTOM_PROJECTILE_UNAVAILABLE: this Runtime adapter cannot call game functions'
    end
    if not scheduler.in_update()then
        return nil,'NOT_GAME_THREAD: a custom projectile is spawned only from the game update (a callback, timer or '
            ..'keybind)'
    end
    if not world.view.proves(world.game+RS.rva,RS.prologue)then
        return nil,'CUSTOM_PROJECTILE_UNAVAILABLE: the game SpawnProjectile function changed'
    end
    local proven,why=M.prove_projectile_rows(world)
    if not proven then return nil,'CUSTOM_PROJECTILE_UNAVAILABLE: '..why end
    local system=world.view.pointer(world.game+PJ.system)
    local flag=system and world.view.read(system+PJ.active,1)
    if not flag then return nil,'PROJECTILE_UNAVAILABLE: the projectile system is unreadable'end
    if flag:byte()~=1 then return nil,'NOT_IN_MISSION: the projectile system is not active'end
    local base=M.projectile_row(world,spec.base_type)
    if not base then
        return nil,'UNKNOWN_PROJECTILE: the vanilla row of base type '..tostring(spec.base_type)..' does not resolve'
    end
    local custom=type(spec.row)=='number'and world.view.read(spec.row,projectile_rows.SIZE)
    if not custom then return nil,'ROW_UNREADABLE: the Runtime-owned row is not readable'end
    local report=projectile_rows.validate(custom,base,spec.base_type)
    if report.status~='VALID'then return nil,'HYBRID_INCOMPATIBLE: '..report.summary,report end
    if not finite(spec,{'x','y','z'},100000)then return nil,'INVALID_POSITION: the position must be finite world coordinates'end
    if not finite(spec,{'dx','dy','dz'},1.0001)or math.abs(spec.dx^2+spec.dy^2+spec.dz^2-1)>=1e-3 then
        return nil,'INVALID_DIRECTION: the direction must be a unit vector'
    end
    if M.entity_exists(world,spec.source)~=true or M.entity_exists(world,spec.owner)~=true then
        return nil,'NO_LOCAL_AVATAR: the firing entity no longer exists'
    end
    for _,key in ipairs({'peer_lo','peer_hi'})do
        local v=spec[key]
        if type(v)~='number'or v<0 or v>=4294967296 or v%1~=0 then return nil,'INVALID_CREDITOR: no creditor peer id'end
    end
    local slot=runtime.native_spawn_projectile(world.game+RS.rva,system,spec.row,spec.x,spec.y,spec.z,spec.dx,
        spec.dy,spec.dz,spec.source,spec.owner,spec.peer_lo,spec.peer_hi,RS.kind,RS.descriptor)
    metrics.count('events.native_custom_projectiles')
    return {slot=slot,report=report,base=base}
end

------------------------------------------------------------------------------------------- projectile pool --
-- The projectile system's pool, read-only (domains/projectile_rows.lua pool, research/projectile-pool-F5FEE03DCFDB.json):
-- weapon projectile replacement (runtime/projectile_replacement.lua) reads which projectiles the game spawned since
-- its last look. SpawnProjectile adds 1 to the system's spawn counter per projectile (and per slot it skips while an
-- explosion of the slot's previous projectile is pending) and writes slot = counter & 0x7FF. Nothing here writes.
local PO=rows_domain.pool

-- Every projectile pool pin, proven once per loaded game.dll. true, or nil and the first mismatch.
function M.prove_projectile_pool(world)
    if world.projectile_pool_proven then return true end
    if rows_domain.source.gameDllSha256~=natives.source.gameDllSha256 then
        return nil,'the projectile pool research covers another game.dll build'
    end
    for _,pin in ipairs(PO.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,'native projectile pool changed ('..pin.label..' at game+'..string.format('%X',pin.rva)..')'
        end
    end
    world.projectile_pool_proven=true
    return true
end
-- The spawn counter now and the system it belongs to, or nil and the reason (NOT_IN_MISSION while the projectile
-- system is inactive).
function M.projectile_counter(world)
    local proven,why=M.prove_projectile_pool(world)
    if not proven then return nil,'PROJECTILE_POOL_UNAVAILABLE: '..why end
    local system=world.view.pointer(world.game+PJ.system)
    local flag=system and world.view.read(system+PO.active,1)
    if not flag then return nil,'PROJECTILE_POOL_UNAVAILABLE: the projectile system is unreadable'end
    if flag:byte()~=1 then return nil,'NOT_IN_MISSION: the projectile system is not active'end
    local counter=world.view.u32(system+PO.counter)
    if not counter then return nil,'PROJECTILE_POOL_UNAVAILABLE: the spawn counter is unreadable'end
    return counter,system
end
-- The slots spawned since counter value `from`, up to `count` of them (at most a whole pool), with their stored
-- types: a list of {slot, type} in spawn order, read in at most two bulk reads. nil when unreadable.
function M.projectile_types(world,system,from,count)
    if type(count)~='number'or count<1 or count>PO.slots or count%1~=0 then return nil end
    local first=from%PO.slots
    local head=math.min(count,PO.slots-first)
    local base=system+PO.types.base
    local bytes=world.view.read(base+first*PO.types.stride,head*PO.types.stride)
    if bytes and head<count then
        local tail=world.view.read(base,(count-head)*PO.types.stride)
        bytes=tail and bytes..tail
    end
    if not bytes then return nil end
    local out={}
    for index=0,count-1 do out[#out+1]={slot=(first+index)%PO.slots,type=b.u32(bytes,index*PO.types.stride)}end
    return out
end
local function f32(bytes,offset)
    local n=b.u32(bytes,offset)
    if math.floor(n/8388608)%256==255 then return nil end
    return b.value(bytes,offset,'f32')
end
-- One slot's records as SpawnProjectile wrote them (and the update since): {slot, type, position, velocity (x, y, z
-- tables), speed, distance (travelled since spawn), lifetime (0 = no time limit), creditor_lo, creditor_hi, owner,
-- source}, or nil when unreadable or not finite.
function M.projectile_slot(world,system,slot)
    if type(slot)~='number'or slot<0 or slot>=PO.slots or slot%1~=0 then return nil end
    local F,S,H=PO.flight,PO.source,PO.hit
    local kind=world.view.u32(system+PO.types.base+slot*PO.types.stride)
    local flight=world.view.read(system+F.base+slot*F.stride,F.lifetime+4)
    local source=world.view.read(system+S.base+slot*S.stride,S.entity+4)
    local hit=world.view.read(system+H.base+slot*H.stride,H.owner+4)
    if not(kind and flight and source and hit)then return nil end
    local values={}
    for index,offset in ipairs({F.position,F.position+4,F.position+8,F.velocity,F.velocity+4,F.velocity+8,F.speed,
            F.distance,F.lifetime})do
        values[index]=f32(flight,offset)
        if values[index]==nil then return nil end
    end
    return {slot=slot,type=kind,position={x=values[1],y=values[2],z=values[3]},
        velocity={x=values[4],y=values[5],z=values[6]},speed=values[7],distance=values[8],lifetime=values[9],
        creditor_lo=b.u32(hit,H.creditor),creditor_hi=b.u32(hit,H.creditor+4),owner=b.u32(hit,H.owner),
        source=b.u32(source,S.entity)}
end

-- The game's own status request queue, from the main thread. Refused unless: the request function's exact prologue
-- bytes match, the queue is readable with headroom, the type is on the reviewed allowlist and its settings record
-- carries that type, the buildup is positive and bounded, and the target and instigator exist. The game then checks
-- the target's status instance and susceptibility itself and routes the request to the target's owner.
-- spec: {type, target, buildup, instigator}. Returns true, or nil and the reason.
local allowed_status={}
for _,item in ipairs(ST and ST.allowlist or{})do allowed_status[item.type]=true end
function M.status(world,spec)
    local runtime=world.runtime
    if not runtime.native_status then return nil,'STATUS_UNAVAILABLE: this Runtime adapter cannot call game functions'end
    if not allowed_status[spec.type]then
        return nil,'UNKNOWN_STATUS: status type '..tostring(spec.type)..' is not on the reviewed allowlist'
    end
    if not world.view.proves(world.game+ST.rva,ST.prologue)then
        return nil,'STATUS_UNAVAILABLE: the game status request changed'
    end
    local queue=world.view.pointer(world.game+ST.queue)
    local count=queue and world.view.u32(queue+ST.count)
    if not count then return nil,'STATUS_UNAVAILABLE: the status queue is unreadable'end
    if count>=ST.capacity then return nil,'QUEUE_FULL: the game status queue is full this frame'end
    if not world.view.pointer(world.game+ST.manager)then return nil,'STATUS_UNAVAILABLE: no status manager'end
    if not typed_record(world,ST.settingsTable,spec.type,72)then
        return nil,'UNKNOWN_STATUS: the game has no settings record for status type '..tostring(spec.type)
    end
    local buildup=spec.buildup
    if type(buildup)~='number'or buildup~=buildup or buildup<=0 or buildup>1000 then
        return nil,'INVALID_AMOUNT: buildup must be above 0 and at most 1000'
    end
    if M.entity_exists(world,spec.target)~=true then return nil,'TARGET_GONE: the target entity no longer exists'end
    if M.entity_exists(world,spec.instigator)~=true then return nil,'NO_LOCAL_AVATAR: the instigator no longer exists'end
    runtime.native_status(world.game+ST.rva,spec.type,spec.target,buildup,spec.instigator)
    metrics.count('events.native_status_requests')
    return true
end

function M.heal(world,entity,amount)
    if type(amount)~='number'or amount~=amount or amount<=0 or amount>100000 then
        return nil,'heal amount must be a positive number'
    end
    local runtime=world.runtime
    if not runtime.native_heal then return nil,'HEAL_UNAVAILABLE: this Runtime adapter cannot call game functions'end
    if not world.view.proves(world.game+natives.heal.rva,natives.heal.prologue)then
        return nil,'HEAL_UNAVAILABLE: the game heal function changed'
    end
    local state=M.entity_state(world,entity)
    if not state then return nil,'the entity has no health record'end
    local info=entities[state.descriptor.type]
    if not(info and info.avatar)then return nil,'only a Helldiver avatar can be healed'end
    if not state.descriptor.owned then return nil,'only the local player (the avatar this machine owns) can be healed'end
    if state.life~=0 then return nil,'the avatar is downed or dead'end
    local maximum=state.max_health
    if not maximum or maximum<=0 or maximum>100000 then return nil,'maximum health unreadable'end
    if state.health>=maximum then return 0 end
    local missing=maximum-state.health
    local applied=math.min(amount,missing)
    local fraction=applied/maximum
    runtime.native_heal(world.game+natives.heal.rva,state.header.manager,entity,fraction)
    metrics.count('events.native_heals')
    return applied
end

---------------------------------------------------------------------------------------------------- injury --
-- The game's own limb injury of the LOCAL player's avatar (research/player-injury-path-F5FEE03DCFDB.json,
-- docs/research/player-injury-path-F5FEE03DCFDB.md): the engine's unit actor lookup finds the limb's physics actor on
-- the avatar's unit, then QueueDamage queues one damage event at it with the template of the VG-70 Variable's own
-- self-damage (kind 6 Ability, element 0). The game's drain applies it later in the frame through ApplyDamage, which
-- lowers the zone that lists that actor; a zone at 0 health is an injured limb. Nothing gameplay runs inside the call.
local IJ=natives.injury
local injury_limbs={}
for _,limb in ipairs(IJ and IJ.limbs or{})do injury_limbs[limb.name]=limb end
-- The limb Runtime names, or nil: {name, actor, zone, zoneIndex, maxDamage, affectsMainHealth}.
function M.injury_limb(name)return type(name)=='string'and injury_limbs[name]or nil end
-- Every limb, in the research's order.
function M.injury_limbs()
    local out={}
    for _,limb in ipairs(IJ and IJ.limbs or{})do out[#out+1]=limb end
    return out
end
-- An engine function through the engine API table game.dll itself uses, re-read every call: the global must hold the
-- pinned table and the slot the pinned function. The function's address, or nil.
local function engine_slot(world,global,table_rva,slot,rva)
    local api=world.view.pointer(world.game+global)
    if api~=world.exe+table_rva then return nil end
    local fn=world.view.pointer(api+slot)
    if fn~=world.exe+rva then return nil end
    return fn
end
local function zone_state(states,index)
    local word=b.u32(states,math.floor(index/16)*4)
    return math.floor(word/(4^(index%16)))%4
end
-- Refused unless: this runs inside the game update; the adapter can call game functions; the limb is one the research
-- names and the damage a whole number from 1 to that limb zone's health; QueueDamage's and the unit actor lookup's
-- exact entry bytes match; the engine unit and actor API slots are the pinned functions; queue 0 has headroom; the
-- entity is a Helldiver avatar (the catalogued type) this machine owns, alive and not downed, with a network id that
-- resolves back to it and a unit; and its unit has the limb's actor. spec: {entity, limb, damage}. Returns {limb,
-- zone, damage, actor, zone_health, injured_before}, or nil and 'CODE: reason'.
function M.injure(world,spec)
    local runtime=world.runtime
    if not IJ then return nil,'INJURY_UNAVAILABLE: no injury research in this Runtime'end
    if not(runtime.native_injure and runtime.native_unit_actor)then
        return nil,'INJURY_UNAVAILABLE: this Runtime adapter cannot call game functions'
    end
    if not scheduler.in_update()then
        return nil,'NOT_GAME_THREAD: an injury is requested only from the game update (a callback, timer or keybind)'
    end
    local limb=M.injury_limb(spec.limb)
    if not limb then return nil,'UNKNOWN_LIMB: '..tostring(spec.limb)..' is not a limb Runtime can injure'end
    local damage=spec.damage
    if type(damage)~='number'or damage~=damage or damage%1~=0 or damage<1 or damage>limb.maxDamage then
        return nil,'INVALID_AMOUNT: '..limb.name..' damage must be a whole number from 1 to '..limb.maxDamage
    end
    if not world.view.proves(world.game+IJ.rva,IJ.prologue)then
        return nil,'INJURY_UNAVAILABLE: the game damage request changed'
    end
    local U,AA=IJ.unitApi,IJ.actorApi
    local lookup=engine_slot(world,U.global,U.table,U.slot,U.rva)
    if not lookup or not world.view.proves(lookup,U.prologue)then
        return nil,'INJURY_UNAVAILABLE: the engine unit actor lookup is not the pinned function'
    end
    if not(engine_slot(world,AA.global,AA.table,AA.validSlot,AA.validRva)
            and engine_slot(world,AA.global,AA.table,AA.nameSlot,AA.nameRva))then
        return nil,'INJURY_UNAVAILABLE: the engine actor API the game\'s drain uses is not the pinned one'
    end
    local system=world.view.pointer(world.game+IJ.system)
    local count=system and world.view.u32(system+IJ.count)
    if not count then return nil,'INJURY_UNAVAILABLE: the damage queue is unreadable'end
    if count>=IJ.capacity then return nil,'QUEUE_FULL: the game damage queue is full this frame'end
    local entity=spec.entity
    if M.entity_exists(world,entity)~=true then return nil,'NO_LOCAL_AVATAR: the avatar no longer exists'end
    local state=M.entity_state(world,entity)
    if not state then return nil,'NO_LOCAL_AVATAR: the avatar has no health record'end
    local descriptor=state.descriptor
    if descriptor.type~=IJ.avatarType then return nil,'NOT_A_HELLDIVER: only a Helldiver avatar has these limbs'end
    if not descriptor.owned then return nil,'NOT_LOCAL_PLAYER: this machine does not own the avatar'end
    if state.life==1 then return nil,'AVATAR_DOWNED: the avatar is downed'end
    if state.life~=0 then return nil,'AVATAR_DEAD: the avatar is dead'end
    local network=descriptor.goid
    if not network or network==A.noNetworkId or M.network_entity(world,network)~=entity then
        return nil,'INJURY_UNAVAILABLE: the avatar has no network id that resolves to it'
    end
    if not descriptor.unit or descriptor.unit==0 then return nil,'INJURY_UNAVAILABLE: the avatar has no unit'end
    local record=world.view.read(state.header.records+state.index*H.stride,H.stride)
    if not record then return nil,'INJURY_UNAVAILABLE: the avatar health record is unreadable'end
    local before=b.value(record,IJ.zoneHealth+4*limb.zoneIndex,'i32')
    local injured=zone_state(record:sub(IJ.zoneStates+1,IJ.zoneStates+16),limb.zoneIndex)==2
    local creditor_lo,creditor_hi=b.u32(record,IJ.creditor),b.u32(record,IJ.creditor+4)
    local actor=runtime.native_unit_actor(lookup,descriptor.unit,limb.actor)
    if type(actor)~='number'or actor<0 or actor>=4294967295 or actor%1~=0 then
        return nil,'LIMB_UNAVAILABLE: the avatar has no '..limb.name..' actor now'
    end
    runtime.native_injure(world.game+IJ.rva,entity,damage,network,creditor_lo,creditor_hi,actor)
    metrics.count('events.native_injuries')
    return {limb=limb.name,zone=limb.zone,damage=damage,actor=actor,zone_health=before,injured_before=injured}
end

------------------------------------------------------------------------------------------------- limb heal --
-- The game's own one-zone restore (research/player-avatar-actions-F5FEE03DCFDB.json): RestoreZone(ignored, entity,
-- zone name) sets that zone to its full health, clears its injured state and commits it the way the game's heal does
-- (sent to the other machines for an entity this machine owns). Main health is not touched. RestoreZone checks
-- neither the zone name nor the health record, so Runtime passes only the avatar's own zone names (the catalogued
-- Helldiver type) for an avatar whose record it has just resolved.
local LH=natives.limbHeal
-- A limb's zone now: {health, max, injured}, or nil when the record is unreadable.
local function limb_zone(world,state,limb)
    local record=world.view.read(state.header.records+state.index*H.stride,H.stride)
    if not record then return nil end
    return {health=b.value(record,IJ.zoneHealth+4*limb.zoneIndex,'i32'),max=limb.maxDamage,
        injured=zone_state(record:sub(IJ.zoneStates+1,IJ.zoneStates+16),limb.zoneIndex)==2}
end
-- The local avatar's living, owned health state for a limb action, or nil and 'CODE: reason'.
local function own_avatar(world,entity,kind)
    if M.entity_exists(world,entity)~=true then return nil,'NO_LOCAL_AVATAR: the avatar no longer exists'end
    local state=M.entity_state(world,entity)
    if not state then return nil,'NO_LOCAL_AVATAR: the avatar has no health record'end
    if state.descriptor.type~=IJ.avatarType then return nil,'NOT_A_HELLDIVER: only a Helldiver avatar has '..kind end
    if not state.descriptor.owned then return nil,'NOT_LOCAL_PLAYER: this machine does not own the avatar'end
    if state.life==1 then return nil,'AVATAR_DOWNED: the avatar is downed'end
    if state.life~=0 then return nil,'AVATAR_DEAD: the avatar is dead'end
    return state
end
-- Refused unless: inside the game update; the adapter can call game functions; the limb is one Runtime names;
-- RestoreZone's exact entry bytes match; the entity is the catalogued Helldiver avatar, owned here, alive and not
-- downed. spec: {entity, limb}. Returns {limb, zone, zone_health (before), max, injured_before}, or nil and
-- 'CODE: reason'.
function M.heal_limb(world,spec)
    local runtime=world.runtime
    if not(LH and IJ)then return nil,'LIMB_HEAL_UNAVAILABLE: no limb heal research in this Runtime'end
    if not runtime.native_restore_zone then
        return nil,'LIMB_HEAL_UNAVAILABLE: this Runtime adapter cannot call game functions'
    end
    if not scheduler.in_update()then
        return nil,'NOT_GAME_THREAD: a limb heal is requested only from the game update (a callback, timer or keybind)'
    end
    local limb=M.injury_limb(spec.limb)
    local zone=limb and LH.zones[limb.name]
    if not zone then return nil,'UNKNOWN_LIMB: '..tostring(spec.limb)..' is not a limb Runtime can heal'end
    if not world.view.proves(world.game+LH.rva,LH.prologue)then
        return nil,'LIMB_HEAL_UNAVAILABLE: the game zone restore changed'
    end
    local state,why=own_avatar(world,spec.entity,'these limbs')
    if not state then return nil,why end
    local before=limb_zone(world,state,limb)
    if not before then return nil,'LIMB_HEAL_UNAVAILABLE: the avatar health record is unreadable'end
    runtime.native_restore_zone(world.game+LH.rva,spec.entity,zone)
    metrics.count('events.native_limb_heals')
    return {limb=limb.name,zone=limb.zone,zone_health=before.health,max=before.max,injured_before=before.injured}
end
-- A limb zone of an avatar now (read-only): {health, max, injured}, or nil.
function M.limb_state(world,entity,name)
    local limb=M.injury_limb(name)
    local state=limb and M.entity_state(world,entity)
    return state and limb_zone(world,state,limb)or nil
end

-------------------------------------------------------------------------------------------------- velocity --
-- The game's own MotionComponent velocity setter (research/player-avatar-actions-F5FEE03DCFDB.json):
-- SetVelocity(ignored, entity, v) writes the velocity the avatar's movement and the jump pack's thrust use. It does
-- not check that the entity has a motion record, so Runtime resolves the record first (the motion hash, below its
-- capacity, its descriptor naming the entity and owned here). What ground locomotion does with the new velocity the
-- next frame is not proven.
local MV=natives.velocity
-- The entity's motion record: {index, velocity = {x, y, z}, owned}, or nil.
function M.motion(world,entity)
    if not MV then return nil end
    local manager=world.view.pointer(world.game+MV.manager)
    if not manager then return nil end
    local index=hash_value(world,manager+MV.hash,entity)
    local capacity=world.view.u32(manager+MV.capacity)
    if not index or not capacity or index>=capacity or capacity>0x10000 then return nil end
    local descriptors=world.view.pointer(manager+MV.descriptors)
    local descriptor=descriptors and world.view.pointer(descriptors+index*8)
    local bytes=descriptor and world.view.read(descriptor,H.descriptor.size)
    if not bytes or b.u32(bytes,H.descriptor.entity)~=entity then return nil end
    local records=world.view.pointer(manager+MV.records)
    local v=records and world.view.read(records+index*MV.stride+MV.velocity,12)
    if not v then return nil end
    local x,y,z=f32(v,0),f32(v,4),f32(v,8)
    if not(x and y and z)then return nil end
    return {index=index,velocity={x=x,y=y,z=z},owned=b.u32(bytes,H.descriptor.flags)%2==1}
end
-- Refused unless: inside the game update; the adapter can call game functions; SetVelocity's exact entry bytes match;
-- the entity is the catalogued Helldiver avatar, owned here, alive and not downed, with a motion record that names it
-- and is owned here; the new velocity is finite and at most spec.max_speed. spec: {entity, x, y, z (the change),
-- max_speed}. Returns {before = {x, y, z}, after = {x, y, z}}, or nil and 'CODE: reason'.
function M.add_velocity(world,spec)
    local runtime=world.runtime
    if not MV then return nil,'VELOCITY_UNAVAILABLE: no velocity research in this Runtime'end
    if not runtime.native_set_velocity then
        return nil,'VELOCITY_UNAVAILABLE: this Runtime adapter cannot call game functions'
    end
    if not scheduler.in_update()then
        return nil,'NOT_GAME_THREAD: a velocity change is requested only from the game update (a callback, timer or '
            ..'keybind)'
    end
    if not finite(spec,{'x','y','z'},1000)then return nil,'INVALID_VELOCITY: the change must be finite'end
    if not world.view.proves(world.game+MV.rva,MV.prologue)then
        return nil,'VELOCITY_UNAVAILABLE: the game velocity setter changed'
    end
    local state,why=own_avatar(world,spec.entity,'this movement')
    if not state then return nil,why end
    local motion=M.motion(world,spec.entity)
    if not motion then return nil,'VELOCITY_UNAVAILABLE: the avatar has no motion record that names it'end
    if not motion.owned then return nil,'NOT_LOCAL_PLAYER: this machine does not own the avatar\'s motion'end
    local v=motion.velocity
    local after={x=v.x+spec.x,y=v.y+spec.y,z=v.z+spec.z}
    local speed=math.sqrt(after.x^2+after.y^2+after.z^2)
    if not(speed<=spec.max_speed)then
        return nil,('TOO_FAST: the avatar would move at %.1f m/s (at most %g)'):format(speed,spec.max_speed)
    end
    runtime.native_set_velocity(world.game+MV.rva,spec.entity,after.x,after.y,after.z)
    metrics.count('events.native_velocity_changes')
    return {before={x=v.x,y=v.y,z=v.z},after=after}
end
return M
