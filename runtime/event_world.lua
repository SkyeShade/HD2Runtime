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
local IMAGE_SIZE,EXE_IMAGE_SIZE=natives.source.imageSize,natives.source.exeImageSize
local opened,adapter_override

-- Tests and the packaged harness supply their own adapter; in game it is the write-capable adapter (heal calls).
function M.set_runtime(runtime)adapter_override=runtime;opened=nil end
local function adapter()
    if adapter_override then return adapter_override end
    return require('hd2runtime/runtime/windows_write').create()
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
function M.unit_position(world,unit)
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
    local poses=world.view.pointer(object+E.sceneGraphOffset+E.poses)
    local bytes=poses and world.view.read(poses+E.translation,12)
    if not bytes then return nil end
    local x,y,z=b.value(bytes,0,'f32'),b.value(bytes,4,'f32'),b.value(bytes,8,'f32')
    if x~=x or y~=y or z~=z or math.abs(x)>100000 or math.abs(y)>100000 or math.abs(z)>100000 then return nil end
    return {x=x,y=y,z=z}
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

------------------------------------------------------------------------------------------------------ heal --
-- The game's own AddHealthFraction(health manager, entity, fraction) on the LOCAL player's avatar, from the main
-- thread (the update callback). Refused unless: the prologue bytes are exactly the reviewed ones, the entity is a
-- Helldiver avatar owned by this peer, alive (not downed or dead) and below its maximum. The game clamps to maximum.
-- Returns the amount requested (after Runtime's own clamp) or nil and the reason.
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
return M
