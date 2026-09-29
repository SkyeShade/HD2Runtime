-- Offline game world for event tests: sparse memory laid out exactly as domains/event_natives.lua describes, with
-- every pinned instruction present in fake game.dll / executable images. Nothing here touches a real process.
local natives=require('hd2runtime/domains/event_natives')
local profile=require('hd2runtime/schemas/current')
local H,P,A,S,E,T=natives.health,natives.players,natives.playerAvatars,natives.state,natives.engine,natives.stats
local C=natives.corpses
local X=natives.explosion
local W={}

-------------------------------------------------------------------------------------------------- memory --
local allocs={}
local next_base=0x40000000
local function alloc(size,base)
    base=base or next_base
    if not base then error('alloc') end
    if base>=next_base then next_base=base+size+0x10000-(base+size)%0x10000 end
    local a={base=base,size=size,bytes={}}
    allocs[#allocs+1]=a
    return base,a
end
local function find(address,size)
    for _,a in ipairs(allocs)do
        if address>=a.base and address+size<=a.base+a.size then return a end
    end
end
local function write(address,s)
    local a=assert(find(address,#s),string.format('write outside fixture %X',address))
    for i=1,#s do a.bytes[address-a.base+i]=s:byte(i)end
    if a.mirror then for i=1,#s do a.mirror[address-a.base+i-1]=s:byte(i)end end
end
local function read(address,size)
    local a=find(address,size)
    if not a then return nil end
    local out={}
    for i=1,size do out[i]=string.char(a.bytes[address-a.base+i]or 0)end
    return table.concat(out)
end
local function u32(n)n=n%4294967296;return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function u64(n)return u32(n%4294967296)..u32(math.floor(n/4294967296))end
local function f32(v)
    if v==0 then return u32(0)end
    local sign=v<0 and 1 or 0;v=math.abs(v)
    local m,e=math.frexp(v)
    local exponent=e+126
    local mantissa=math.floor((m*2-1)*8388608+0.5)
    return u32(sign*2147483648+exponent*8388608+mantissa)
end
local function unhex(h)return(h:gsub('..',function(p)return string.char(tonumber(p,16))end))end
local function le32(s)return s:byte(1)+s:byte(2)*256+s:byte(3)*65536+s:byte(4)*16777216 end
local function type_bytes(type_hex)return u32(tonumber(type_hex:sub(9),16))..u32(tonumber(type_hex:sub(1,8),16))end
-- Peer ids exceed 2^53: tests pass them as 16 hex digits and they are written exactly.
local function peer(value)
    if type(value)=='string'then return unhex(value):reverse()end
    return u64(value or 0)
end
W.u32,W.u64,W.f32,W.write,W.read=u32,u64,f32,write,read

-------------------------------------------------------------------------------------------------- images --
local GAME,EXE=0x10000000,0x20000000
local function image(base,size)
    alloc(size,base)
    local pe=128
    write(base,'MZ');write(base+60,u32(pe));write(base+pe,'PE\0\0');write(base+pe+24,string.char(0x0B,0x02))
    write(base+pe+80,u32(size))
end
image(GAME,natives.source.imageSize);image(EXE,natives.source.exeImageSize)
for _,pin in ipairs(natives.pins)do write((pin.module=='exe'and EXE or GAME)+pin.rva,unhex(pin.hex))end
write(GAME+natives.heal.rva,unhex(natives.heal.prologue))
write(GAME+X.rva,unhex(X.prologue))
write(GAME+natives.projectile.rva,unhex(natives.projectile.prologue))
write(GAME+natives.status.rva,unhex(natives.status.prologue))

-- Game-side managers.
local health=alloc(0x2000)
write(GAME+H.global,u64(health))
local CAPACITY=rawget(_G,'EVENT_FIXTURE_CAPACITY')or 64
local HASH=256
while HASH<CAPACITY*2 do HASH=HASH*2 end
local buckets=alloc(HASH*8)
local records=alloc(CAPACITY*H.stride)
local ext=alloc(CAPACITY*H.extStride)
local pointers=alloc(CAPACITY*8)
write(health+H.capacity,u32(1024));write(health+H.hashCapacity,u32(HASH));write(health+H.hashEmpty,u32(0))
write(health+H.hashMultiplier,u32(2));write(health+H.buckets,u64(buckets));write(health+H.records,u64(records))
write(health+H.extArray,u64(ext));write(health+H.descriptors,u64(pointers))
local players=alloc(0x1000)
write(GAME+P.global,u64(players))
local session=alloc(0xC000)
write(GAME+P.localUser,u64(session))
local entities=alloc(0x1000000)
write(GAME+A.entities,u64(entities))
local net_slots=alloc(64*8)
write(entities+A.mapSlots,u64(net_slots));write(entities+A.mapCapacity,u32(64));write(entities+A.mapEmpty,u32(0x7FFF))
write(entities+A.mapMultiplier,u32(1))
for slot=0,63 do write(net_slots+slot*8,u32(0x7FFF)..u32(0))end
local game_object=alloc(S.state+16)
write(GAME+S.game,u64(game_object))
local game_mode=alloc(0x100)
write(GAME+S.gameMode,u64(game_mode))
local mode_descriptor=alloc(0x18)
write(game_mode+S.gameModeDescriptor,u64(mode_descriptor))
-- Engine (executable) side: entity generations and the unit registry.
local engine=alloc(0x100)
write(EXE+E.entities,u64(engine))
local generations=alloc(0x10000)
write(engine+E.generationSize,u32(0x10000));write(engine+E.generations,u64(generations))
local registry=alloc(0x100)
write(EXE+E.units,u64(registry))
local unit_generations=alloc(0x10000)
local unit_objects=alloc(0x10000*8)
write(registry+E.unitCount,u32(0x10000));write(registry+E.unitGenerations,u64(unit_generations))
write(registry+E.unitObjects,u64(unit_objects))
local vtable=alloc(0x100)
write(vtable+0xE8,u64(EXE+E.sceneGraphMethod))
write(EXE+E.sceneGraphMethod,unhex(E.sceneGraphMethodBytes))

-- Held items: the wielder manager (entity -> instance; slot 0 = the entity in hand), the inventory manager (the
-- selection) and the entity map (entity -> descriptor carrying its type). Hashes use multiplier 1 and empty key 0.
local WI=natives.wielder
local function map_put(buckets,capacity,key,value)
    local slot=key%capacity
    while read(buckets+slot*8,4)~=u32(0)and read(buckets+slot*8,4)~=u32(key)do slot=(slot+1)%capacity end
    write(buckets+slot*8,u32(key)..u32(value))
end
local function map_remove(buckets,capacity,key)
    for slot=0,capacity-1 do if read(buckets+slot*8,4)==u32(key)then write(buckets+slot*8,u32(0)..u32(0))end end
end
local wielder=alloc(0x100)
write(GAME+WI.wielder,u64(wielder))
local wielder_buckets=alloc(64*8)
write(wielder+WI.wielderHash,u64(wielder_buckets)..u32(64)..u32(0)..u32(1))
local wielder_slots=alloc(16*WI.stride)
write(wielder+WI.slots,u64(wielder_slots))
local inventory=alloc(0x100)
write(GAME+WI.inventory,u64(inventory))
local inventory_buckets=alloc(64*8)
write(inventory+WI.inventoryHash,u64(inventory_buckets)..u32(64)..u32(0)..u32(1))
local inventory_records=alloc(16*WI.recordStride)
write(inventory+WI.records,u64(inventory_records))
local entity_buckets=alloc(256*8)
write(entities+WI.entityMap,u64(entity_buckets)..u32(256)..u32(0)..u32(1))
local instances,instance_count,next_descriptor={},0,1
-- The avatar's wielder instance holds `item` (0 = nothing) of type type_hex, with inventory selection `selection`.
function W.hold(avatar,item,type_hex,selection)
    local instance=instances[avatar]
    if not instance then
        instance=instance_count;instance_count=instance_count+1;instances[avatar]=instance
        map_put(wielder_buckets,64,avatar,instance);map_put(inventory_buckets,64,avatar,instance)
    end
    write(wielder_slots+instance*WI.stride,u32(item or 0))
    write(inventory_records+instance*WI.recordStride+WI.selection,u32(selection or 0))
    if item and item~=0 and type_hex then
        map_put(entity_buckets,256,item,next_descriptor)
        write(entities+WI.descriptors+next_descriptor*WI.descriptorStride,type_bytes(type_hex)..u32(item))
        next_descriptor=next_descriptor+1
    end
end
-- The game removed the avatar's wielder and inventory records (death).
function W.drop_wielder(avatar)
    map_remove(wielder_buckets,64,avatar);map_remove(inventory_buckets,64,avatar);instances[avatar]=nil
end

-- Mission stats: one player record (index 0) with an empty main table and one source block.
local score=alloc(T.recordBase+4*T.recordStride+0x100)
write(GAME+T.score,u64(score))
local score_map=alloc(16*8)
write(score+T.indexSlots,u64(score_map));write(score+T.indexCapacity,u32(16));write(score+T.indexEmpty,u32(0))
write(score+T.indexMultiplier,u32(1))
local main_table=alloc(16*T.entryStride)
local sources=alloc(T.sourceBlocks*T.sourceStride)
local record=score+T.recordBase
write(record+T.tableEntries,u64(main_table));write(record+T.tableCapacity,u32(16));write(record+T.tableEmpty,u32(0))
write(record+T.tableMultiplier,u32(1));write(record+T.sources,u64(sources))
-- The player entity's stat index, and the projectiles_fired count in source block 3 (keyed by the shooter's type).
function W.stats(player_entity,shots)
    write(score_map+(player_entity%16)*8,u32(player_entity)..u32(0))
    local block=sources+3*T.sourceStride
    write(block,u64(0x4D1C334D))
    write(block+T.sourceEntries,u32(T.keys.projectiles_fired)..u32(shots))
end
-- One stat value: in source block `block` keyed by the source type (16 hex digits), or in the main table (no block).
function W.stat(player_entity,key,value,block,type_hex)
    write(score_map+(player_entity%16)*8,u32(player_entity)..u32(0))
    if block then
        local base=sources+block*T.sourceStride
        write(base,type_bytes(type_hex))
        for entry=0,T.sourceEntryCount-1 do
            local at=base+T.sourceEntries+entry*T.entryStride
            local found=read(at,4)
            if found==u32(key)or found==u32(0)then write(at,u32(key)..u32(value));return end
        end
        error('source block full')
    end
    local slot=key%16
    while read(main_table+slot*T.entryStride,4)~=u32(0)and read(main_table+slot*T.entryStride,4)~=u32(key)do
        slot=(slot+1)%16
    end
    write(main_table+slot*T.entryStride,u32(key)..u32(value))
end

-- Corpses: when the game replaces a dead entity it spawns a corpse entity that takes over the unit and keeps the dead
-- entity's id in its record.
local corpse_manager=alloc(0x100)
write(GAME+C.global,u64(corpse_manager))
local corpse_descriptors=alloc(64*8)
local corpse_records=alloc(64*C.stride)
write(corpse_manager+C.descriptors,u64(corpse_descriptors));write(corpse_manager+C.records,u64(corpse_records))
local corpse_count=0
function W.corpse(origin,corpse,unit,type_hex)
    local descriptor=alloc(0x18)
    write(descriptor,type_bytes(type_hex or'0000000000000000')..u32(corpse)..u32(unit or 0)..u32(0x7FFF)..u32(1))
    write(corpse_descriptors+corpse_count*8,u64(descriptor))
    write(corpse_records+corpse_count*C.stride+C.origin,u32(origin))
    corpse_count=corpse_count+1
    write(corpse_manager+C.count,u32(corpse_count))
end

-- The explosion queue and the settings table the drain indexes by type (a record starts with its type).
local explosion_queue=alloc(0x28+X.capacity*0x98)
write(GAME+X.queue,u64(explosion_queue))
for _,list in ipairs({X.weapons,X.named or{}})do
    for _,item in ipairs(list)do
        local record=alloc(0x98)
        write(record,u32(item.type))
        write(GAME+X.settingsTable+item.type*8,u64(record))
    end
end
function W.queue_count(n)write(explosion_queue+X.count,u32(n))end

-- The projectile system (active in a mission) and its settings table; the status queue, manager and settings table.
local PJ,ST=natives.projectile,natives.status
local projectile_system=alloc(0x40)
write(GAME+PJ.system,u64(projectile_system))
function W.projectiles_active(on)write(projectile_system+PJ.active,string.char(on and 1 or 0))end
W.projectiles_active(true)
for _,item in ipairs(PJ.types)do
    local record=alloc(0x110)
    write(record,u32(item.type))
    write(GAME+PJ.settingsTable+item.type*8,u64(record))
end
local status_queue=alloc(ST.count+8)
write(GAME+ST.queue,u64(status_queue))
write(GAME+ST.manager,u64(alloc(0x10)))
for _,item in ipairs(ST.allowlist)do
    local record=alloc(0x98)
    write(record,u32(item.type))
    write(GAME+ST.settingsTable+item.type*8,u64(record))
end
function W.status_queue_count(n)write(status_queue+ST.count,u32(n))end

---------------------------------------------------------------------------------------------- the runtime --
local runtime={mode='event-fixture',heals={},explosions={},projectiles={},statuses={}}
-- The game's projectile wrapper and status request: recorded, never executed.
function runtime.native_projectile(entry,system,kind,x,y,z,dx,dy,dz,entity)
    assert(entry==GAME+PJ.rva and system==projectile_system,'projectile fired through the wrong function or system')
    runtime.projectiles[#runtime.projectiles+1]={type=kind,x=x,y=y,z=z,dx=dx,dy=dy,dz=dz,entity=entity}
    return true
end
function runtime.native_status(entry,kind,target,buildup,instigator)
    assert(entry==GAME+ST.rva,'status requested through the wrong function')
    runtime.statuses[#runtime.statuses+1]={type=kind,target=target,buildup=buildup,instigator=instigator}
    return true
end
-- The game's explosion request: recorded, never executed.
function runtime.native_explosion(entry,queue,x,y,z,kind,source,owner,peer_lo,peer_hi)
    assert(entry==GAME+X.rva and queue==explosion_queue,'explosion requested through the wrong function or queue')
    runtime.explosions[#runtime.explosions+1]={x=x,y=y,z=z,type=kind,source=source,owner=owner,
        peer=string.format('%08X%08X',peer_hi,peer_lo)}
    return true
end
-- Package residency as the asset gate reads it (core/assets.lua offline hook): 'resident' unless a test says otherwise.
runtime.packages={}
function runtime.package_state(package)return runtime.packages[package]or'resident'end
function runtime.module(name)if name==nil then return EXE end;if name=='game.dll'then return GAME end end
function runtime.address(handle)return handle end
function runtime.module_hash(handle)return handle==EXE and profile.exe_sha or profile.dll_sha end
function runtime.read(address,size)return read(address,size)end
function runtime.native_heal(entry,manager,entity,fraction)
    assert(entry==GAME+natives.heal.rva and manager==health,'heal called with the wrong function or manager')
    runtime.heals[#runtime.heals+1]={entity=entity,fraction=fraction}
    W.heal_now(entity,fraction)
    return true
end
W.runtime=runtime
-- An FFI mirror of every allocation (kept in sync by write): runtime.read_into then copies like ReadProcessMemory,
-- so the event sources run their in-game hot path. Used by scripts/bench_events.py.
function W.mirror()
    local ffi=require('ffi')
    for _,a in ipairs(allocs)do
        if a.size<=0x2000000 then
            a.mirror=ffi.new('uint8_t[?]',a.size)
            for offset,byte in pairs(a.bytes)do a.mirror[offset-1]=byte end
        end
    end
    function runtime.read_into(address,size,buffer)
        local a=find(address,size)
        if not a or not a.mirror then return false end
        ffi.copy(buffer,a.mirror+(address-a.base),size)
        return true
    end
end

------------------------------------------------------------------------------------------------ world state --
local live={}          -- index -> entity
local by_entity={}     -- entity -> {index, descriptor}
local function rewrite_hash()
    for slot=0,HASH-1 do write(buckets+slot*8,u32(0)..u32(0))end
    for index,entity in ipairs(live)do
        local slot=(entity*2)%HASH
        while read(buckets+slot*8,4)~=u32(0)do slot=(slot+1)%HASH end
        write(buckets+slot*8,u32(entity)..u32(index-1))
    end
    write(health+H.live,u32(#live))
end
local function place(entity)
    local item=by_entity[entity]
    local index=item.index
    write(pointers+index*8,u64(item.descriptor))
    local base=records+index*H.stride
    write(base+H.record.health,u32(item.health));write(base+H.record.life,u32(item.life))
    write(base+H.record.lastCreditor,peer(item.creditor))
    write(ext+index*H.extStride+H.extFields.maxHealth,u32(item.max))
end
local function relayout()
    for index,entity in ipairs(live)do by_entity[entity].index=index-1;place(entity)end
    rewrite_hash()
end
-- spec: {entity, type (16 hex), unit, owned, health, max, life, creditor}
function W.add(spec)
    local descriptor=alloc(0x18)
    local lo=tonumber(spec.type:sub(9),16);local hi=tonumber(spec.type:sub(1,8),16)
    write(descriptor,u32(lo)..u32(hi)..u32(spec.entity)..u32(spec.unit or 0)..u32(spec.goid or 0x7FFF)
        ..u32(spec.owned and 1 or 0))
    by_entity[spec.entity]={descriptor=descriptor,health=spec.health or 100,max=spec.max or spec.health or 100,
        life=spec.life or 0,creditor=spec.creditor}
    live[#live+1]=spec.entity
    write(generations+spec.entity%4194304,string.char(math.floor(spec.entity/4194304)%256))
    relayout()
    return spec.entity
end
function W.remove(entity)
    for i,e in ipairs(live)do if e==entity then table.remove(live,i)break end end
    by_entity[entity]=nil
    local index=entity%4194304
    local current=read(generations+index,1):byte()
    write(generations+index,string.char((current+1)%256))
    relayout()
end
-- The game replaces a dead entity by its corpse: the entity (and its health record) is destroyed and a corpse entity
-- of the same type takes over its unit.
function W.replace_by_corpse(entity,corpse)
    local descriptor=by_entity[entity].descriptor
    local type_hex=string.format('%08X%08X',le32(read(descriptor+4,4)),le32(read(descriptor,4)))
    local unit=le32(read(descriptor+12,4))
    W.remove(entity)
    write(generations+corpse%4194304,string.char(math.floor(corpse/4194304)%256))
    W.corpse(entity,corpse,unit,type_hex)
end
function W.set(entity,fields)
    local item=by_entity[entity]
    for k,v in pairs(fields)do item[k]=v end
    place(entity)
end
function W.get(entity)return by_entity[entity]end
function W.heal_now(entity,fraction)
    local item=by_entity[entity]
    item.health=math.min(item.max,item.health+math.floor(item.max*fraction))
    place(entity)
end
-- Units: a position for a unit id.
function W.unit(unit,x,y,z)
    local index,generation=unit%4194304,math.floor(unit/4194304)%256
    write(unit_generations+index,string.char(generation))
    local object=alloc(0x100)
    write(object,u64(vtable));write(object+E.unitId,u32(unit))
    local poses=alloc(0x100)
    write(object+E.sceneGraphOffset+E.poses,u64(poses))
    write(poses+E.translation,f32(x)..f32(y)..f32(z))
    write(unit_objects+index*8,u64(object))
end
function W.remove_unit(unit)
    local index=unit%4194304
    local current=read(unit_generations+index,1):byte()
    write(unit_generations+index,string.char((current+1)%256))
end
-- Players: list of {peer (number), avatar (entity|nil), lifecycle}; the first local peer.
local network_ids={}
function W.players(list,local_peer)
    write(session+P.localPeer,peer(local_peer))
    write(players+P.count,u32(#list))
    for slot,player in ipairs(list)do
        local i=slot-1
        write(players+P.peers+i*P.peerStride,peer(player.peer))
        write(players+A.lifecycle+i*P.peerStride,u32(player.lifecycle or 3))
        local net=0x7FFF
        if player.avatar then
            net=100+i
            network_ids[net]=player.avatar
            write(net_slots+(net%64)*8,u32(net)..u32(i))
            write(entities+A.entityBase+i*A.entityStride,u32(player.avatar))
        end
        write(players+A.avatarId+i*A.avatarIdStride,u32(net))
        local descriptor=alloc(0x18)
        write(descriptor+P.descriptorEntity,u32(10+i))
        write(players+P.descriptors+i*8,u64(descriptor))
    end
end
-- Game state: 3 Ship, 4 Mission (with a game_mode object unless mode=false), host flag.
function W.state(value,opts)
    opts=opts or{}
    write(game_object+S.state,u32(value))
    write(game_mode+S.gameModeCount,u32(opts.mode==false and 0 or(value==S.mission and 1 or 0)))
    write(mode_descriptor+S.descriptorFlags,u32(opts.host==false and 0 or 1))
    write(game_mode+S.gameModeType,u32(1))
end
W.state(3)
W.GAME=GAME;W.EXE=EXE
W.AVATAR='4D1C334D294DFA97'
return W
