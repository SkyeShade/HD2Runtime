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
W.alloc=function(size)return (alloc(size))end

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
-- SpawnProjectile and every projectile row pin (custom projectile rows, domains/projectile_rows.lua).
local rows_domain=require('hd2runtime/domains/projectile_rows')
for _,pin in ipairs(rows_domain.pins)do write(GAME+pin.rva,unhex(pin.hex))end
write(GAME+rows_domain.spawn.rva,unhex(rows_domain.spawn.prologue))

-- Game-side managers.
local health=alloc(0x2000)
write(GAME+H.global,u64(health))
local CAPACITY=rawget(_G,'EVENT_FIXTURE_CAPACITY')or 64
local HASH=256
while HASH<CAPACITY*2 do HASH=HASH*2 end
local buckets=alloc(HASH*8)
local records=alloc(CAPACITY*H.stride)
local ext=alloc(math.max(CAPACITY*H.extStride,0x1000))   -- at least a page (a guarded write checks its page)
local pointers=alloc(CAPACITY*8)
write(health+H.capacity,u32(1024));write(health+H.hashCapacity,u32(HASH));write(health+H.hashEmpty,u32(0))
write(health+H.hashMultiplier,u32(2));write(health+H.buckets,u64(buckets));write(health+H.records,u64(records))
write(health+H.extArray,u64(ext));write(health+H.descriptors,u64(pointers))
local players=alloc(0x1000)
write(GAME+P.global,u64(players))
local session=alloc(0x20000)          -- the network context (+0x1D470: the lobby wrapper)
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
-- The avatar's wielder instance holds `item` (0 = nothing) of type type_hex, with inventory selection `selection`;
-- `unit` (optional) is the held entity's unit in its descriptor.
function W.hold(avatar,item,type_hex,selection,unit)
    local instance=instances[avatar]
    if not instance then
        instance=instance_count;instance_count=instance_count+1;instances[avatar]=instance
        map_put(wielder_buckets,64,avatar,instance);map_put(inventory_buckets,64,avatar,instance)
    end
    write(wielder_slots+instance*WI.stride,u32(item or 0))
    write(inventory_records+instance*WI.recordStride+WI.selection,u32(selection or 0))
    if item and item~=0 and type_hex then
        map_put(entity_buckets,256,item,next_descriptor)
        write(entities+WI.descriptors+next_descriptor*WI.descriptorStride,type_bytes(type_hex)..u32(item)..u32(unit or 0))
        next_descriptor=next_descriptor+1
    end
end
-- An entity in the entity map (its type, its unit) without being held: a dropped or racked weapon.
-- goid (optional): its network id in the descriptor (+0x10, as the game's own entity map holds it).
function W.register_entity(entity,type_hex,unit,goid)
    map_put(entity_buckets,256,entity,next_descriptor)
    write(entities+WI.descriptors+next_descriptor*WI.descriptorStride,type_bytes(type_hex)..u32(entity)..u32(unit or 0)
        ..(goid and u32(goid)or''))
    next_descriptor=next_descriptor+1
end
-- The component world object the entity and network id maps hang from (W.bombardment replaces its global).
W.ENTITIES=entities
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
-- Every catalogued explosion (domains/explosion_catalogue.lua): its type, damage link and radii, as the live row.
for _,entry in pairs(require('hd2runtime/domains/explosion_catalogue').explosions)do
    local at=GAME+X.settingsTable+entry.type*8
    local record=le32(read(at,4))+le32(read(at+4,4))*4294967296
    if record==0 then
        record=alloc(0x98)
        write(at,u64(record))
    end
    write(record,u32(entry.type)..u32(entry.damage and entry.damage.type or 0))
    write(record+16,f32(entry.values[1])..f32(entry.values[2])..f32(entry.values[3]))
end
function W.queue_count(n)write(explosion_queue+X.count,u32(n))end
-- The queue as the game keeps it (research/event-explosions-F5FEE03DCFDB.json): a request appends at index count; one
-- world update (W.explosion_update) kicks min(count, 8), processes exactly those and moves the rest to the front.
-- Entries are never cleared. spec: {type, position = {x, y, z}, source, owner, creditor (16 hex digits), argument7}.
local function queued()return le32(read(explosion_queue+X.count,4))end
function W.request_explosion(spec)
    local index=queued()
    local p=spec.position or{x=0,y=0,z=0}
    local entry=f32(p.x)..f32(p.y)..f32(p.z)..u32(spec.type)..u32(spec.source or 0)..u32(spec.owner or 0)
        ..peer(spec.creditor)..u32(spec.argument7 or 0)
    write(explosion_queue+X.entry+index*X.stride,entry..string.rep('\0',X.stride-#entry))
    write(explosion_queue+X.count,u32(index+1))
    return index
end
function W.explosion_update(requests_after_kick)
    local count=queued()
    local kicked=math.min(count,X.perFrame)
    write(explosion_queue+X.kicked,u32(kicked))
    for _,spec in ipairs(requests_after_kick or{})do W.request_explosion(spec)end
    count=queued()
    local rest=count-kicked
    if rest>0 then
        write(explosion_queue+X.entry,read(explosion_queue+X.entry+kicked*X.stride,rest*X.stride))
    end
    write(explosion_queue+X.count,u32(rest)..u32(0))
end

-- The projectile system (active in a mission) and its settings table; the status queue, manager and settings table.
local PJ,ST=natives.projectile,natives.status
-- Large enough for the whole pool (domains/projectile_rows.lua pool): its type array ends at +0xE7040.
local projectile_system=alloc(0xE8000)
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
-- A whole ProjectileInfo row for a type; a record is allocated when the catalog has none (a support weapon's).
function W.projectile_row(kind,bytes)
    local at=GAME+PJ.settingsTable+kind*8
    local record=le32(read(at,4))+le32(read(at+4,4))*4294967296
    if record==0 then record=alloc(0x110);write(at,u64(record))end
    if bytes then write(record,bytes)end
    return record
end
W.projectile_system=projectile_system
-- The projectile pool as SpawnProjectile leaves it (research/projectile-pool-F5FEE03DCFDB.json): spawn records one
-- projectile at slot = counter & 0x7FF and advances the counter. spec: {type, position = {x, y, z}, velocity = {x, y,
-- z}, speed, distance (travelled), lifetime, creditor (16 hex digits, or a number), owner, source, skip (slots the
-- counter skips first)}. Returns the slot.
local PO=require('hd2runtime/domains/projectile_rows').pool
for _,pin in ipairs(PO.pins)do write(GAME+pin.rva,unhex(pin.hex))end
function W.pool_counter(n)
    if n then write(projectile_system+PO.counter,u32(n))end
    return le32(read(projectile_system+PO.counter,4))
end
function W.spawn_projectile(spec)
    local counter=W.pool_counter()+(spec.skip or 0)
    local slot=counter%PO.slots
    local F,S,H=PO.flight,PO.source,PO.hit
    local p,v=spec.position or{x=0,y=0,z=0},spec.velocity or{x=0,y=500,z=0}
    write(projectile_system+PO.types.base+slot*PO.types.stride,u32(spec.type))
    write(projectile_system+PO.flags.base+slot*PO.flags.stride,string.char(PO.flags.inFlight,0))
    local flight=projectile_system+F.base+slot*F.stride
    write(flight+F.position,f32(p.x)..f32(p.y)..f32(p.z))
    write(flight+F.velocity,f32(v.x)..f32(v.y)..f32(v.z))
    write(flight+F.speed,f32(spec.speed or 500)..f32(spec.distance or 0)..f32(spec.lifetime or 0))
    write(projectile_system+S.base+slot*S.stride+S.entity,u32(spec.source or 0))
    local hit=projectile_system+H.base+slot*H.stride
    write(hit+H.creditor,peer(spec.creditor))
    write(hit+H.owner,u32(spec.owner or 0))
    W.pool_counter(counter+1)
    return slot
end

---------------------------------------------------------------------------------------------- the runtime --
local runtime={mode='event-fixture',heals={},explosions={},projectiles={},statuses={}}
function W.pool_spawns(on)runtime.pool_spawns=on end
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
-- Runtime-owned blocks and the game's SpawnProjectile: blocks live in fixture memory; the call is recorded, never
-- executed, and only accepts a block this adapter allocated (as runtime/windows_write.lua asserts).
runtime.custom_projectiles,runtime.owned={},{}
function runtime.owned_block(size)
    local address=alloc(size)
    runtime.owned[address]=size
    return address
end
function runtime.owned_write(address,bytes)
    assert(runtime.owned[address]==#bytes,'not a whole Runtime-owned block')
    write(address,bytes)
    return true
end
function runtime.native_spawn_projectile(entry,system,row,x,y,z,dx,dy,dz,source,owner,peer_lo,peer_hi,kind,layout)
    assert(entry==GAME+rows_domain.spawn.rva and system==projectile_system,'spawned through the wrong function or system')
    assert(runtime.owned[row],'SpawnProjectile was given a row the Runtime does not own')
    runtime.custom_projectiles[#runtime.custom_projectiles+1]={row=row,x=x,y=y,z=z,dx=dx,dy=dy,dz=dz,source=source,
        owner=owner,peer=string.format('%08X%08X',peer_hi,peer_lo),kind=kind,layout=layout,bytes=read(row,0x110)}
    -- W.pool_spawns(true): the spawn lands in the pool like the game's (its row's type at the next counter slot).
    if runtime.pool_spawns then
        return W.spawn_projectile({type=le32(read(row,4)),position={x=x,y=y,z=z},velocity={x=dx,y=dy,z=dz},
            creditor=string.format('%08X%08X',peer_hi,peer_lo),owner=owner,source=source})
    end
    return 40+#runtime.custom_projectiles
end
-- The game's explosion request: recorded, never executed.
function runtime.native_explosion(entry,queue,x,y,z,kind,source,owner,peer_lo,peer_hi)
    assert(entry==GAME+X.rva and queue==explosion_queue,'explosion requested through the wrong function or queue')
    runtime.explosions[#runtime.explosions+1]={x=x,y=y,z=z,type=kind,source=source,owner=owner,
        peer=string.format('%08X%08X',peer_hi,peer_lo)}
    -- W.queue_requests(true): the request lands in the queue like the game's (appended at count).
    if runtime.queue_requests then
        W.request_explosion({type=kind,position={x=x,y=y,z=z},source=source,owner=owner,
            creditor=string.format('%08X%08X',peer_hi,peer_lo)})
    end
    return true
end
function W.queue_requests(on)runtime.queue_requests=on end
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
-- A unit at (x, y, z); axes (optional) = {right, forward, up} rotation rows of its root world pose, each {x, y, z}.
function W.unit(unit,x,y,z,axes)
    local index,generation=unit%4194304,math.floor(unit/4194304)%256
    write(unit_generations+index,string.char(generation))
    local object=alloc(0x100)
    write(object,u64(vtable));write(object+E.unitId,u32(unit))
    local poses=alloc(0x100)
    write(object+E.sceneGraphOffset+E.poses,u64(poses))
    for row,axis in ipairs(axes or{{x=1,y=0,z=0},{x=0,y=1,z=0},{x=0,y=0,z=1}})do
        write(poses+(row-1)*16,f32(axis.x)..f32(axis.y)..f32(axis.z))
    end
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
-- A network id the game's map resolves to an entity (a beacon, a pod's content, a rack item): entry k of the map's
-- entity array (k >= 8: past the players').
function W.network_id(net,entity,k)
    write(net_slots+(net%64)*8,u32(net)..u32(k))
    write(entities+A.entityBase+k*A.entityStride,u32(entity))
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

------------------------------------------------------------------------------ the PlayFab lobby (peer channel) --
-- W.lobby(spec): the game's lobby as research/peer-messaging-F5FEE03DCFDB.json found it: the wrapper (network context
-- + 0x1D470) with its flag, the engine lobby, the PlayfabLobby (members, state, handle, id text), the engine API registry
-- and T in the executable with both member-data slots, and every pin. spec: {members = {peer hex, ...} (default: the
-- local peer), state (default 3), active (default true), platform (false: the game's "platform_lobby" post not made
-- yet), engine (false: none), handle (false: zero), id (default 'cv2:fixture'), slots (false: T's slots left zero),
-- host (the session host's peer hex; default the local peer)}. Calling it again updates the same objects. The service is
-- W.lobby_values ({[peer hex] = value}): runtime.native_lobby_publish sets the local peer's value (recorded in
-- runtime.lobby_posts; W.LOBBY_RESULT is the HRESULT it returns), and runtime.native_lobby_read returns the address of
-- a fixture copy of a member's value (nil for no value or a non-member), as the engine does. Values are keyed:
-- W.lobby_values is the 'hd2rt' key's store; every other key's is W.lobby_keyed[key] ({[peer hex] = value}).
local PM=require('hd2runtime/domains/peer_messaging')
local function hex_of(bytes)return(bytes:reverse():gsub('.',function(c)return string.format('%02X',c:byte())end))end
W.lobby_values={}
W.lobby_keyed={}
local function lobby_store(key)
    if key=='hd2rt'then return W.lobby_values end
    W.lobby_keyed[key]=W.lobby_keyed[key]or{}
    return W.lobby_keyed[key]
end
runtime.lobby_posts,runtime.lobby_reads={},{}
local lobby_objects
function W.lobby(spec)
    spec=spec or{}
    for _,pin in ipairs(PM.pins)do write((pin.module=='exe'and EXE or GAME)+pin.rva,unhex(pin.hex))end
    local A=PM.api
    write(GAME+A.registryGlobal,u64(EXE+A.registry))
    write(EXE+A.registry+A.table,u64(EXE+A.tableRva))
    write(EXE+A.tableRva+A.memberData,u64(spec.slots==false and 0 or EXE+A.memberDataRva))
    write(EXE+A.tableRva+A.setMemberData,u64(spec.slots==false and 0 or EXE+A.setMemberDataRva))
    lobby_objects=lobby_objects or{engine=alloc(0x40),pl=alloc(0x200),array=alloc(16*8),id=alloc(64)}
    local o=lobby_objects
    o.members=spec.members or{hex_of(read(session+P.localPeer,8))}
    for i,p in ipairs(o.members)do write(o.array+(i-1)*8,peer(p))end
    write(o.pl+PM.playfab.memberCount,u32(#o.members));write(o.pl+PM.playfab.members,u64(o.array))
    write(o.pl+PM.playfab.state,u32(spec.state or PM.playfab.joined))
    write(o.pl+PM.playfab.handle,u64(spec.handle==false and 0 or 0x1234))
    write(o.id,(spec.id or'cv2:fixture')..'\0');write(o.pl,u64(o.id))
    write(o.engine+PM.playfab.lobby,u64(o.pl))
    -- The session host (network context +0xB3A8): spec.host, else the local peer.
    write(session+PM.context.hostPeer,spec.host and peer(spec.host)or read(session+P.localPeer,8))
    local wrapper=session+PM.context.wrapper
    write(wrapper+PM.wrapper.engineLobby,u64(spec.engine==false and 0 or o.engine))
    write(wrapper+PM.wrapper.active,string.char(spec.active==false and 0 or 1))
    write(wrapper+PM.wrapper.platformPosted,string.char(spec.platform==false and 0 or 1))
    return o
end
function runtime.native_lobby_publish(entry,lobby,key,value)
    assert(entry==EXE+PM.api.setMemberDataRva and lobby==lobby_objects.engine,
        'a member property published through the wrong function or lobby')
    runtime.lobby_posts[#runtime.lobby_posts+1]={key=key,value=value}
    local result=W.LOBBY_RESULT or 0
    if result==0 then lobby_store(key)[hex_of(read(session+P.localPeer,8))]=value end
    return result
end
function runtime.native_lobby_read(entry,lobby,peer_lo,peer_hi,key)
    assert(entry==EXE+PM.api.memberDataRva and lobby==lobby_objects.engine,
        'a member property read through the wrong function or lobby')
    local hex=string.format('%08X%08X',peer_hi,peer_lo)
    runtime.lobby_reads[#runtime.lobby_reads+1]={peer=hex,key=key}
    local member=false
    for _,p in ipairs(lobby_objects.members)do member=member or p==hex end
    local value=member and lobby_store(key)[hex]
    if not value then return nil end
    local at=alloc(4096)                     -- a heap page: readable past the string, as the SDK's are
    write(at,value..'\0')
    return at
end

------------------------------------------------------------------------------------- guarded writes (opt-in) --
-- W.guarded_runtime(): the adapter functions the guarded transaction needs (core/guarded_transaction.lua): region
-- queries (the images are read-only image memory, every other allocation private read-write), writes (recorded in
-- runtime.writes) and page protection. Opt-in, so the event tests keep the read-only adapter they were written for.
local IMAGE_TYPE,PRIVATE,COMMIT=0x1000000,0x20000,0x1000
function W.guarded_runtime()
    runtime.writes,runtime.protections=runtime.writes or{},runtime.protections or{}
    function runtime.query(at)
        local a=find(at,1)
        if not a then return nil end
        local image=a.base==GAME or a.base==EXE
        local page=at-at%4096
        local protect=runtime.protections[page]or(image and 2 or 4)
        if runtime.protections[page]then
            return {base=page,size=4096,allocation_base=a.base,allocation_protect=protect,state=COMMIT,
                protect=protect,type=image and IMAGE_TYPE or PRIVATE}
        end
        return {base=a.base,size=a.size,allocation_base=a.base,allocation_protect=protect,state=COMMIT,
            protect=protect,type=image and IMAGE_TYPE or PRIVATE}
    end
    function runtime.write(at,bytes)
        runtime.writes[#runtime.writes+1]={address=at,bytes=bytes}
        write(at,bytes)
        return true,nil,#bytes
    end
    function runtime.protect(page,size,value)
        local old=runtime.protections[page]or 4
        runtime.protections[page]=value
        return old
    end
    function runtime.system_info()return 4096,0x800000000000 end
    return runtime
end

-- W.stratagem_settings(rows): a StratagemSettings buffer (core/stratagem.lua framing) holding the rows, each {type, id,
-- package (16 hex digits), payload (16 hex digits) or payloads = {...}, sequence = {...}, cooldown, group, row, fields =
-- {[offset] = bytes} (other members, e.g. the presentation)}, with
-- their payload lists and sequence arrays inside their group. A row with group/row sits at exactly that group and row
-- (filler rows of unused types around it), so a catalogue root (id, package, group, row, payloads) resolves; rows
-- without one fill group 0 in order. It is installed where the profile's buffer and runtime table point, and the
-- loaded profile describes it. Returns {base, size, rows = {[type] = {address, sequence}}}.
local looks
local function beacon_looks()
    if not looks then
        looks={}
        for _,v in pairs(require('hd2runtime/domains/stratagem_slots').beacon.observed)do looks[v.id]=v end
    end
    return looks
end
function W.stratagem_settings(rows)
    local profile_module=require('hd2runtime/schemas/current')
    local s=profile_module.stratagem
    local group_type=s.type
    local function hex64(h)return unhex(h:gsub('^0x','')):reverse()end
    -- The groups and their rows: placed rows first, then fillers for every gap.
    local used,groups,last={},{},0
    for _,row in ipairs(rows)do used[row.type]=true end
    for _,row in ipairs(rows)do
        local g=row.group or 0
        groups[g]=groups[g]or{}
        local r=row.row or#groups[g]
        while groups[g][r]~=nil and row.row==nil do r=r+1 end
        assert(groups[g][r]==nil,'two rows at group '..g..' row '..r)
        groups[g][r]=row
        if g>last then last=g end
    end
    local filler=0
    local function fill()
        repeat filler=filler+1 until not used[filler]
        used[filler]=true
        return {type=filler,id=1000000+filler,package=string.format('0x%016X',0xF000+filler),payloads={},
            sequence={1,2,3}}
    end
    local ordered={}
    for g=0,last do
        groups[g]=groups[g]or{}
        local top=-1
        for r in pairs(groups[g])do if r>top then top=r end end
        if top<0 then top=0 end
        ordered[g+1]={}
        for r=0,top do ordered[g+1][r+1]=groups[g][r]or fill()end
    end
    -- Sizes: each group is its 24-byte header, the 16-byte root, its rows, payload lists and sequences.
    local parts,cursor,total,out={},4,0,{rows={}}
    local layout={}
    for g,list in ipairs(ordered)do
        local at=cursor
        local root=at+24
        local rows_at=root+16
        local payloads_at=rows_at+#list*400
        local count=0
        for _,row in ipairs(list)do count=count+#(row.payloads or{row.payload})end
        local sequences_at=payloads_at+count*8
        local finish=sequences_at
        for _,row in ipairs(list)do finish=finish+#row.sequence*4 end
        layout[g]={at=at,root=root,rows_at=rows_at,payloads_at=payloads_at,sequences_at=sequences_at,finish=finish}
        cursor=finish;total=total+#list
    end
    local length=cursor
    local size=length+(8-length%8)%8
    layout[#ordered].finish=size
    local base=alloc(size+(4096-size%4096)%4096)
    local body={}
    local function put(offset,bytes)body[#body+1]={offset=offset,bytes=bytes}end
    put(0,u32(#ordered))
    for g,list in ipairs(ordered)do
        local l=layout[g]
        put(l.at,'LDLD'..u32(1)..u32(group_type)..u32(l.finish-l.root)..u32(1)..u32(0))
        put(l.root,u64(base+l.rows_at)..u32(#list)..u32(0))
        local payload_cursor,sequence_cursor=l.payloads_at,l.sequences_at
        for index,row in ipairs(list)do
            local at=l.rows_at+(index-1)*400
            local record=string.rep('\0',400)
            local function field(offset,bytes)record=record:sub(1,offset)..bytes..record:sub(offset+#bytes+1)end
            local payloads=row.payloads or{row.payload}
            field(0,u32(row.type));field(4,u32(row.id))
            field(0x40,u64(base+sequence_cursor));field(0x48,u32(#row.sequence)..u32(0))
            field(80,u32(3));field(104,f32(row.cooldown or 180))
            if#payloads>0 then field(152,u64(base+payload_cursor)..u32(#payloads)..u32(0))end
            field(168,hex64(row.package))
            -- A catalogued stratagem's beacon look as the game has it (its beam +0xD4 and ping +0xB8, observed).
            local look=beacon_looks()[row.id]
            if look then field(0xB8,u32(look.ping));field(0xD4,u32(look.beam))end
            for offset,bytes in pairs(row.fields or{})do field(offset,bytes)end   -- any other member: {[offset] = bytes}
            put(at,record)
            for _,payload in ipairs(payloads)do put(payload_cursor,hex64(payload));payload_cursor=payload_cursor+8 end
            local sequence={}
            for _,value in ipairs(row.sequence)do sequence[#sequence+1]=u32(value)end
            put(sequence_cursor,table.concat(sequence))
            out.rows[row.type]={address=base+at,sequence=base+sequence_cursor}
            sequence_cursor=sequence_cursor+#row.sequence*4
            write(GAME+s.table_rva+row.type*8,u64(base+at))
        end
    end
    write(base,string.rep('\0',size))
    for _,item in ipairs(body)do write(base+item.offset,item.bytes)end
    write(GAME+s.buffer_rva,u64(base))
    local spec={}
    for key,value in pairs(s)do spec[key]=value end
    spec.size,spec.groups,spec.total_records=size,#ordered,total
    profile_module.stratagem=spec
    out.base,out.size=base,size
    return out
end
-- W.stratagem_hud(spec): the mission HUD's stratagem list as the research lays it out (domains/stratagem_calldown.lua
-- hud), and the local player's stratagem record. spec = {peer = the local peer, slots = {{type, code = {...}}, ...},
-- set_up = false to leave the HUD torn down}. Each slot draws its code with the real HUD's bytes: its sprites' sub-rect,
-- image regions and derived regions are those of the retained mission snapshots, flags as the game leaves them, and
-- the 11 layout parents of the real list: row container (slot +0x2870) -> slot +0x6B0 -> +0x5A0 -> +0x490 -> slot ->
-- list -> list -0xE20 -> -0xF30 -> panel (list -0x1040) -> HUD +0x820 -> HUD +0x258 (the last two already have 0x4
-- and 0x8), at the offsets and with the flags of the mission snapshots.
-- Returns {hud, list, root, record, chain = {shared parents}, slots = {[index] = {address, container, ancestors =
-- {address, ...}, sprites = {address, ...}}}}.
W.HUD_CELLS={[0]={'0000000000000000cdcc4c3e0000803f','0090263f0000213f00902a3f0000293f'},
    {'cdcc4c3e00000000cdcccc3e0000803f','00902a3f0000213f00902e3f0000293f'},
    {'cdcccc3e000000009a99193f0000803f','00902e3f0000213f0090323f0000293f'},
    {'9a99193f00000000cdcc4c3f0000803f','0090323f0000213f0090363f0000293f'},
    {'cdcc4c3f000000000000803f0000803f','0090363f0000213f00903a3f0000293f'}}
W.HUD_SUBRECT='0090263f0000213f0000a03d0000003d'
function W.stratagem_hud(spec)
    local H=require('hd2runtime/domains/stratagem_calldown').hud
    local SL,SP,R=H.slots,H.sprites,H.records
    local hud=alloc(0x400000)
    write(GAME+H.global,u64(hud))
    write(hud+H.setUp,string.char(spec.set_up==false and 0 or 1))
    local first=hud+H.pathOffset
    local list,root=first-H.listSlot0,hud+0x258
    -- Shared parents: list -> list -0xE20 -> -0xF30 -> panel -> HUD +0x820 -> root.
    local shared={{list,0x41011},{list-0xE20,0x41011},{list-0xF30,0x41011},{list-0x1040,0x41011},{hud+0x820,0x4101D},
        {root,0x101D}}
    for position,item in ipairs(shared)do
        write(item[1],u32(item[2]));write(item[1]+SP.parent,u64(shared[position+1]and shared[position+1][1]or 0))
    end
    local out={hud=hud,list=list,root=root,slots={},chain={}}
    for position,item in ipairs(shared)do out.chain[position]=item[1]end
    for index=0,SL.count-1 do
        local slot=first+index*SL.stride
        local item=spec.slots[index+1]or{type=0,code={}}
        write(slot+SL.index,u32(index));write(slot+SL.type,u32(item.type));write(slot+SL.displayedType,u32(item.type))
        -- The slot's own parents: row container -> +0x6B0 -> +0x5A0 -> +0x490 -> slot -> list.
        local own={{slot+0x2870,0x41011},{slot+0x6B0,0x41011},{slot+0x5A0,0x41011},{slot+0x490,0x41011},{slot,0x45011}}
        for position,parent in ipairs(own)do
            write(parent[1],u32(parent[2]));write(parent[1]+SP.parent,u64(own[position+1]and own[position+1][1]or list))
        end
        local container=slot+0x2870
        local entry={address=slot,container=container,sprites={},ancestors={}}
        for _,parent in ipairs(own)do entry.ancestors[#entry.ancestors+1]=parent[1]end
        for _,parent in ipairs(shared)do entry.ancestors[#entry.ancestors+1]=parent[1]end
        for number=0,SP.count-1 do
            local sprite=slot+SP.offset+number*SP.stride
            local cell=item.code[number+1]
            write(sprite,u32(cell and 0x000C1051 or 0x000C1043));write(sprite+SP.mask,u32(0))
            write(sprite+SP.flagParent,u64(0))
            write(sprite+SP.sibling,u64(number<SP.count-1 and sprite+SP.stride or 0))
            write(sprite+SP.parent,u64(container))
            write(sprite+SP.region,unhex(W.HUD_CELLS[cell or 0][1]))
            write(sprite+SP.derived,unhex(W.HUD_CELLS[cell or 0][2]))
            write(sprite+SP.subrect,unhex(W.HUD_SUBRECT))
            entry.sprites[number+1]=sprite
        end
        out.slots[index]=entry
    end
    -- The local player's record: its entries are the slots' types in order.
    local records=alloc(R.count+8)
    write(GAME+R.global,u64(records))
    write(records+R.count,u32(1))
    write(records,peer(spec.peer))
    local types={}
    for _,item in ipairs(spec.slots)do types[#types+1]=item.type end
    -- An entry is a type, or {type=, uses=, granted=} (uses: -1 unlimited; granted: 1 for a default or mission-granted
    -- stratagem, 0 for a loadout pick).
    for entry,kind in ipairs(spec.record or types)do
        local item=type(kind)=='table'and kind or{type=kind}
        local at=records+R.entries+(entry-1)*R.entryStride
        write(at,u32(item.type))
        if item.uses then write(at+4,u32(item.uses%4294967296))end
        if item.granted then write(at+9,string.char(item.granted))end
    end
    write(records+R.entryCount,u32(#(spec.record or types)))
    -- The key a call-in of this record carries (record state +0x9E8).
    write(records+0x38+0x9E8,u32(1)..u32(0x1234))      -- W.RECORD_KEY
    out.record=records
    return out
end
-- W.saved_loadout(pairs, saved): the save store the game writes when the loadout screen is left (domains/
-- stratagem_calldown.lua loadout): {id = StratagemInfo +4 stable id, uses} pairs and the saved flag (default true).
function W.saved_loadout(pairs,saved)
    local L=require('hd2runtime/domains/stratagem_calldown').loadout
    local store=W.save_store
    if not store then store=alloc(0x200);W.save_store=store;write(GAME+L.store,u64(store))end
    write(store+L.savedFlag,string.char(saved==false and 0 or 1))
    write(store+L.pairs,string.rep(string.char(0),L.pairCount*L.pairStride))
    for index,pair in ipairs(pairs)do
        write(store+L.pairs+(index-1)*L.pairStride+L.pair.id,u32(pair.id))
        write(store+L.pairs+(index-1)*L.pairStride+L.pair.uses,u32(pair.uses or 0xFFFFFFFF))
    end
    return store
end
-- W.bombardment(spec): the bombardment component (domains/bombardment_payload.lua) as the game's own lookup reads it,
-- with every reviewed record at its reviewed index slot and record index and every pinned reader in the image:
-- [game + component.global] -> an object whose +indexField is the index (its framing header 28 bytes before it, the
-- slots, the records at +recordOffset); the manager (no instance); the variant registry (none active); the shell table
-- with every reviewed shell row. spec.records = {[stable id] = 192 bytes} overrides a record.
-- Returns {index, record(id) -> address, set_instances({payload hex, ...}, barrages), set_variant({payload hex, ...}),
-- slot(row, payload hex, record) (an extra index slot), read(id) -> the record's bytes, set_clock(time) (the game clock,
-- spec.clock or a live mission's time by default)}.
function W.bombardment(spec)
    spec=spec or{}
    local D=require('hd2runtime/domains/bombardment_payload')
    local C=D.component
    for _,pin in ipairs(D.pins)do write(GAME+pin.rva,unhex(pin.hex))end
    -- The component world object (sparse): up to the bombardment index, and past the world's default spawn context
    -- (domains/pelican.lua spawn.defaultContext + contextSize) the Pelican spawn checks.
    local PS=require('hd2runtime/domains/pelican').spawn
    local object=alloc(math.max(C.indexField+8,PS.defaultContext+PS.contextSize+0x100))
    local block=alloc(4096+C.recordOffset+C.records*C.stride)
    local index=block+32
    write(GAME+C.global,u64(object))
    write(object+C.indexField,u64(index))
    write(index-28,unhex(C.header))
    local function hash(payload)return unhex(payload:gsub('^0x','')):reverse()end
    local out={index=index}
    function out.slot(row,payload,record)write(index+row*16,hash(payload)..u32(record)..u32(0))end
    for id,record in pairs(D.records)do
        out.slot(record.indexRow,record.payload,record.record)
        write(index+C.recordOffset+record.record*C.stride,spec.records and spec.records[id]or unhex(record.vanilla))
    end
    function out.record(id)return index+C.recordOffset+D.records[tostring(id)].record*C.stride end
    function out.read(id)return read(out.record(id),C.stride)end
    local manager=alloc(0x100)
    local handles=alloc(0x1000)
    write(GAME+D.manager.global,u64(manager))
    write(manager+D.manager.handles,u64(handles))
    function out.set_instances(payloads,barrages)
        for k,payload in ipairs(payloads)do
            local handle=alloc(16)
            write(handle,hash(payload)..u32(4242+k)..u32(0))
            write(handles+(k-1)*8,u64(handle))
        end
        write(manager+D.manager.instances,u32(#payloads))
        write(manager+D.manager.barrages,u32(barrages or#payloads))
    end
    out.set_instances({},0)
    local registry=alloc(0x4000)
    write(GAME+D.variants.global,u64(registry))
    function out.set_variant(payloads)
        local V=D.variants
        local group=alloc(0x40)
        local entries=alloc(0x40)
        local hashes=alloc(8*math.max(1,#payloads))
        for k,payload in ipairs(payloads)do write(hashes+(k-1)*8,hash(payload))end
        write(entries+V.hashes,u64(hashes));write(entries+V.hashCount,u32(#payloads))
        write(group+V.groupId,u32(77));write(group+V.entries,u64(entries));write(group+V.entryCount,u32(1))
        write(registry+V.groups,u64(group));write(registry+V.groupCount,u32(1))
        local active=alloc(16)
        write(active,u32(77))
        write(registry+V.active,u64(active));write(registry+V.activeCount,u32(1))
    end
    for shell,bytes in pairs(D.shellRows)do
        local row=alloc(#bytes/2)
        write(row,unhex(bytes))
        write(GAME+D.shellTable+tonumber(shell)*8,u64(row))
    end
    -- The Gas Strike chain (stage C): explosion 82, damage 447, volume template 16, statuses 42/44, reviewed, in their
    -- tables (pointers by id). out.chain_row(kind, id) -> the row's address.
    local chain={}
    for _,item in ipairs(D.gasChainRows)do
        local row=alloc(item.stride)
        write(row,unhex(item.reviewed))
        write(GAME+item.table+item.id*8,u64(row))
        chain[item.kind..':'..item.id]=row
    end
    function out.chain_row(kind,id)return chain[kind..':'..id]end
    function out.shell_row(shell)return le32(read(GAME+D.shellTable+shell*8,4))+le32(read(GAME+D.shellTable+shell*8+4,4))*4294967296 end
    -- The game clock an entry's cooldown end is compared with (0x66D200); a live mission's time by default.
    local clock=alloc(0x40)
    write(GAME+D.clock.global,u64(clock))
    function out.set_clock(time)write(clock+D.clock.time,u64(time))end
    out.set_clock(spec.clock or 165760761)
    return out
end
-- Writes every calldown reader pin, every HUD pin, every saved-loadout pin and every presentation reader pin
-- (domains/stratagem_calldown.lua) into the image.
for _,pin in ipairs(require('hd2runtime/domains/stratagem_calldown').pins)do write(GAME+pin.rva,unhex(pin.hex))end
for _,pin in ipairs(require('hd2runtime/domains/stratagem_calldown').hud.pins)do write(GAME+pin.rva,unhex(pin.hex))end
for _,pin in ipairs(require('hd2runtime/domains/stratagem_calldown').loadout.pins)do write(GAME+pin.rva,unhex(pin.hex))end
for _,pin in ipairs(require('hd2runtime/domains/stratagem_calldown').presentation.pins)do write(GAME+pin.rva,unhex(pin.hex))end
-- The resource lookup the custom image guard proves (runtime/image_resources.lua, domains/image_resources.lua).
local IMG=require('hd2runtime/domains/image_resources')
for _,pin in ipairs(IMG.pins)do write((pin.module=='exe'and EXE or GAME)+pin.rva,unhex(pin.hex))end
for _,pin in ipairs(IMG.consumerPins)do write((pin.module=='exe'and EXE or GAME)+pin.rva,unhex(pin.hex))end
-- W.icon_resources(spec, opts): the game's resource manager with these icon resources loaded, laid out as the game's
-- lookups read it (application global -> resource manager -> type map -> type record -> name map -> resource records).
-- spec.textures: resource names, or {name=... or hash='0x<16 hex>', state='tombstone' | 'unloaded'};
-- spec.materials: resource names, or {name=..., state=..., bytes=<160 bytes, default the icon material of the name>,
--   fixups=false (pointers not set as the loader sets them), object={magic=, shader=, name=} (object overrides)};
-- spec.sprites: atlas sprite names, or {name=... or hash='0x<16 hex>', atlas=<its atlas page texture name> or
-- atlasHash='0x<16 hex>', rect={offset u, v, scale u, v}} (the sprite map at resource manager +0x2A0; a sprite with a
-- rectangle is also what the loadout slot repaint's image setter finds, W.atlas).
-- Filler textures and materials are always added and the name maps have few buckets (opts.buckets, default 5), so
-- names share chains. Returns {set=function(kind, name, state)} with kind 'texture' or 'material'.
-- W.textures(list, opts) is W.icon_resources({textures=list}, opts).
W.atlas={}
function W.icon_resources(spec,opts)
    spec,opts=spec or{},opts or{}
    local T,R,N,K=IMG.typeMap,IMG.record,IMG.names,IMG.markers
    local images=require('hd2runtime/runtime/image_resources')
    local hash=images.hash
    -- A resource by name, or by its name hash ({hash='0x...'}: a vanilla resource whose name string is unknown).
    local function hash_of(item)
        if type(item)=='table'and item.hash then
            return tonumber(item.hash:sub(3,10),16),tonumber(item.hash:sub(11,18),16)
        end
        return hash(type(item)=='table'and item.name or item)
    end
    local app,rm=alloc(0x400),alloc(0x400)
    write(EXE+IMG.manager.applicationGlobal,u64(app));write(app+IMG.manager.resourceManager,u64(rm))
    local function map(capacity,stride,next_offset)
        local base=alloc(capacity*stride)
        for i=0,capacity-1 do write(base+i*stride+next_offset,u32(K.empty))end
        return {base=base,capacity=capacity,stride=stride,next=next_offset}
    end
    -- Chain `key` (8 bytes) into an in-array map: its bucket's head when free, else a free overflow entry.
    local function insert(m,buckets,high,key)
        m.used=m.used or buckets
        local i=high%buckets
        if le32(read(m.base+i*m.stride+m.next,4))==K.empty then
            write(m.base+i*m.stride,key);write(m.base+i*m.stride+m.next,u32(K['end']));return m.base+i*m.stride
        end
        while le32(read(m.base+i*m.stride+m.next,4))~=K['end']do i=le32(read(m.base+i*m.stride+m.next,4))end
        assert(m.used<m.capacity,'fixture map full')
        local at=m.used;m.used=m.used+1
        write(m.base+i*m.stride+m.next,u32(at))
        write(m.base+at*m.stride,key);write(m.base+at*m.stride+m.next,u32(K['end']))
        return m.base+at*m.stride
    end
    local types=map(8,T.stride,T.next)
    write(rm+T.capacity,u32(8));write(rm+T.records,u64(types.base));write(rm+T.count,u32(3));write(rm+T.buckets,u32(3))
    insert(types,3,0xA14E8DFA,type_bytes('A14E8DFA2CD117E2'))    -- lua
    local buckets=opts.buckets or 5
    local kinds={}
    local function kind(label,type_hex,fillers,list)
        local hex=type_hex:sub(3)
        local record=insert(types,3,tonumber(hex:sub(1,8),16),type_bytes(hex))
        local names=map(64,N.stride,N.next)
        local resources=alloc(64*R.resourceStride)
        write(record+R.resources,u64(resources));write(record+R.capacity,u32(64));write(record+R.entries,u64(names.base))
        write(record+R.buckets,u32(buckets))
        local all={}
        for _,item in ipairs(fillers)do all[#all+1]=item end
        for _,item in ipairs(list or{})do all[#all+1]=item end
        local entries={}
        kinds[label]={entries=entries,resources=resources}
        for index,item in ipairs(all)do
            local name=type(item)=='table'and(item.name or item.hash)or item
            local high,low=hash_of(item)
            entries[name]={at=insert(names,buckets,high,u32(low)..u32(high)),slot=index-1,item=item,high=high,low=low}
        end
        write(record+R.count,u32(#all))
        return entries
    end
    -- A texture's resource is only a marker; a material's is its 160 bytes as the loader leaves them, with its object.
    local MA=IMG.material
    local template=unhex(MA.template)
    local function material_resource(entry)
        local item=type(entry.item)=='table'and entry.item or{}
        local name=u32(entry.low)..u32(entry.high)
        local bytes=item.bytes or template:sub(1,MA.nameOffset)..name..template:sub(MA.nameOffset+9)
        local at,object=alloc(MA.size),alloc(MA.object.size)
        write(at,bytes)
        if item.fixups~=false then
            write(at+MA.fixups.object,u64(object))
            write(at+MA.fixups.slotIds,u64(at+MA.slotIds));write(at+MA.fixups.slotNames,u64(at+MA.slotNames))
        end
        local o=item.object or{}
        write(object,u32(o.magic or MA.object.magic)..u32(0xFFFFFF))
        write(object+MA.object.body,u64(at+MA.body))
        write(object+MA.object.shader,u32(o.shader or MA.shader))
        write(object+MA.object.name,o.name and(u32(o.name.low)..u32(o.name.high))or name)
        return at
    end
    local function set(label,name,state)
        local k=assert(kinds[label],'no fixture kind '..tostring(label))
        local entry=assert(k.entries[name],'not a fixture '..label..': '..name)
        write(entry.at+N.slot,u32(state=='tombstone'and K.absent or entry.slot))
        local value=0
        if state~='unloaded'then
            if label=='material'then entry.resource=entry.resource or material_resource(entry);value=entry.resource
            else value=0x7000000+entry.slot end
        end
        write(k.resources+entry.slot*R.resourceStride,u64(value))
    end
    local textures=kind('texture',IMG.texture.type,{'core/fallback_resources/missing_texture','content/ui/filler_a',
        'content/ui/filler_b','content/ui/filler_c','content/ui/filler_d','content/ui/filler_e','content/ui/filler_f'},
        spec.textures)
    local materials=kind('material',MA.type,{'core/fallback_resources/missing_material','content/ui/filler_m'},
        spec.materials)
    -- spec.fonts: font resources by name (the engine font the development selector draws with).
    local fonts
    if spec.fonts then
        fonts=kind('font','0x9EFE0A916AAE7880',{'content/ui/filler_font'},spec.fonts)
        write(rm+T.count,u32(4))
    end
    -- spec.units / spec.shading: unit and shading environment resources by name (the render-order probe's script world).
    local extra,count={},fonts and 4 or 3
    local RENDER=require('hd2runtime/domains/stratagem_selector').render
    if spec.units then extra.unit=kind('unit',RENDER.unitType,{'content/filler_unit'},spec.units);count=count+1 end
    if spec.shading then
        extra.shading=kind('shading',RENDER.shadingType,{'content/filler_shading'},spec.shading);count=count+1
    end
    write(rm+T.count,u32(count))
    for name,entry in pairs(textures)do set('texture',name,type(entry.item)=='table'and entry.item.state or nil)end
    for name,entry in pairs(materials)do set('material',name,type(entry.item)=='table'and entry.item.state or nil)end
    for name,entry in pairs(fonts or{})do set('font',name,type(entry.item)=='table'and entry.item.state or nil)end
    for label,entries in pairs(extra)do
        for name,entry in pairs(entries)do set(label,name,type(entry.item)=='table'and entry.item.state or nil)end
    end
    -- The atlas sprite map (GUI API +0x348 / +0x350): name -> sprite record.
    local S=IMG.sprites
    local sprites=map(64,N.stride,N.next)
    local sprite_names={'content/ui/sprite_filler'}
    for _,item in ipairs(spec.sprites or{})do sprite_names[#sprite_names+1]=item end
    for _,item in ipairs(sprite_names)do
        local high,low=hash_of(item)
        local entry=insert(sprites,buckets,high,u32(low)..u32(high))
        -- The sprite record: its name, then its atlas page texture (+8) and its rectangle (+0x18).
        local record=alloc(0x28)
        local ah,al
        if type(item)=='table'and item.atlasHash then
            ah,al=tonumber(item.atlasHash:sub(3,10),16),tonumber(item.atlasHash:sub(11,18),16)
        else
            ah,al=hash(type(item)=='table'and item.atlas or'content/ui/atlas_test_page')
        end
        write(record,u32(low)..u32(high)..u32(al)..u32(ah))
        -- its size in pixels (+0x10: u32 width, height)
        if type(item)=='table'and item.size then write(record+0x10,u32(item.size[1])..u32(item.size[2]))end
        if type(item)=='table'and item.rect then
            local r=item.rect
            write(record+0x18,f32(r[1])..f32(r[2])..f32(r[3])..f32(r[4]))
            W.atlas[('0x%08X%08X'):format(high,low)]={page=('0x%08X%08X'):format(ah,al),rect=r}
        end
        write(entry+8,u64(record))
    end
    write(rm+S.entries,u64(sprites.base));write(rm+S.count,u32(#sprite_names));write(rm+S.buckets,u32(buckets))
    return {set=set}
end
function W.textures(list,opts)return W.icon_resources({textures=list},opts)end

-- Runtime-owned permanent blocks (a Runtime text table): fixture memory, read-only, never freed; recorded.
runtime.permanent={}
function runtime.permanent_block(bytes)
    local address=alloc(#bytes)
    write(address,bytes)
    runtime.permanent[#runtime.permanent+1]={address=address,size=#bytes}
    return address
end
-- The game's text registry (domains/text_resources.lua) as exe 0x321C40 reads it, with every text pin present.
local TXT=require('hd2runtime/domains/text_resources')
for _,pin in ipairs(TXT.pins)do write((pin.module=='exe'and EXE or GAME)+pin.rva,unhex(pin.hex))end
local LANGUAGE_HASH={}
for _,item in ipairs(TXT.languages)do LANGUAGE_HASH[item.code]=item.hash end
W.LANGUAGE_HASH=LANGUAGE_HASH
-- A text table from {[language code or hash] = {[id] = text}} (scripts/hd2_text.py build).
function W.text_table(entries)
    local languages,ids,seen_ids={},{},{}
    local by={}
    for language,texts in pairs(entries)do
        local hash=type(language)=='string'and LANGUAGE_HASH[language]or language
        languages[#languages+1]=hash;by[hash]=texts
        for id in pairs(texts)do if not seen_ids[id]then seen_ids[id]=true;ids[#ids+1]=id end end
    end
    table.sort(languages);table.sort(ids)
    local nl,n=#languages,#ids
    local head={u32(TXT.table.magic),u32(nl),u32(n)}
    for _,h in ipairs(languages)do head[#head+1]=u32(h)end
    for _,id in ipairs(ids)do head[#head+1]=u32(id)end
    local base=12+4*nl+4*n+4*nl*n
    local offsets,blob,seen,size={},{},{},0
    for _,h in ipairs(languages)do
        for _,id in ipairs(ids)do
            local text=by[h][id]
            if text==nil then offsets[#offsets+1]=u32(0)
            else
                local data=text..'\0'
                local at=seen[data]
                if not at then at=base+size;seen[data]=at;blob[#blob+1]=data;size=size+#data end
                offsets[#offsets+1]=u32(at)
            end
        end
    end
    return table.concat(head)..table.concat(offsets)..table.concat(blob)
end
-- W.text_registry(spec): the registry holding these tables in order. spec.tables: {entries, ...} for W.text_table
-- (default: one 'us' table with the 120mm's name, cased name and description); spec.capacity (default the count + 1);
-- spec.language (a code or a raw hash; default 'us'); spec.stale: the bytes in the first spare slot (default zeros).
-- Returns {list, array, tables = {addresses}, set_language(code or hash), rebuild(list of table entries): the game's
-- language registration (count 0, then each table appended in order; the array and capacity kept), count(), slot(i)}.
function W.text_registry(spec)
    spec=spec or{}
    local entries=spec.tables or{{us={[0x4FAAD695]='ORBITAL 120MM HE BARRAGE',[0x628B5A83]='Orbital 120mm HE Barrage',
        [0x35FEBFE6]='A barrage of high-explosive shells.'}}}
    local capacity=spec.capacity or(#entries+1)
    -- Whole pages, as the game's heap regions are (the guarded transaction checks each target's page).
    local list=alloc(4096)
    local array=alloc(4096)
    write(EXE+TXT.registry.global,u64(list))
    write(list,u32(0)..u32(capacity)..u64(array)..u64(0))
    local out={list=list,array=array,tables={}}
    local function place(address,index)write(array+index*8,u64(address))end
    function out.count()return le32(read(list,4))end
    function out.slot(index)return le32(read(array+index*8,4))+le32(read(array+index*8+4,4))*4294967296 end
    function out.set_language(code)write(EXE+TXT.currentLanguage,u32(type(code)=='string'and LANGUAGE_HASH[code]or code))end
    function out.rebuild(list_of_entries)
        write(list,u32(0))
        out.tables={}
        for index,item in ipairs(list_of_entries)do
            local bytes=W.text_table(item)
            local at=alloc(#bytes);write(at,bytes)
            place(at,index-1);out.tables[index]=at
            write(list,u32(index))
        end
    end
    out.rebuild(entries)
    if spec.stale and#entries<capacity then write(array+#entries*8,spec.stale)end
    out.set_language(spec.language or'us')
    return out
end
-- The mission stratagem record code (domains/stratagem_slots.lua pins) and the account catalogue's ownership rule.
local SLOTS=require('hd2runtime/domains/stratagem_slots')
for _,pin in ipairs(SLOTS.pins)do write(GAME+pin.rva,unhex(pin.hex))end
-- The slot cooldown's readers (domains/slot_cooldown.lua pins): the entry's times, the clock, the HUD bar, the peer sync.
for _,pin in ipairs(require('hd2runtime/domains/slot_cooldown').pins)do write(GAME+pin.rva,unhex(pin.hex))end
-- W.catalogue({[stable id] = definition state, ...}): kind-10 records carrying those stable ids (state 2 or 4 = owned).
function W.catalogue(states)
    local CAT=SLOTS.catalogue
    local ids={}
    for id in pairs(states)do ids[#ids+1]=id end
    table.sort(ids)
    local cat=alloc(CAT.index+4*#ids+0x100)
    write(GAME+CAT.global,u64(cat))
    write(cat+CAT.rangeFirst,u32(0));write(cat+CAT.rangeLast,u32(#ids))
    for position,id in ipairs(ids)do
        local record=cat+CAT.records+(position-1)*CAT.recordStride
        write(cat+CAT.index+(position-1)*4,u32(position-1))
        write(record,u32(position-1));write(record+CAT.recordId,u32(id));write(record+CAT.recordBack,u32(0))
        write(cat+CAT.definitions+(position-1)*CAT.definitionStride+CAT.definitionState,u32(states[id]))
    end
    return cat
end
-- W.call_ins(list): the in-flight call-ins, each {key = u64, slot = index, done = 0 or 1}.
function W.call_ins(list)
    local CI=SLOTS.callIns
    local system=alloc(0x100)
    local entries=alloc(math.max(1,#list)*CI.stride)
    write(GAME+CI.global,u64(system))
    write(system+CI.count,u32(#list));write(system+CI.entries,u64(entries))
    for k,item in ipairs(list)do
        local at=entries+(k-1)*CI.stride
        write(at+CI.key,u64(item.key));write(at+CI.slot,u32(item.slot));write(at+CI.done,string.char(item.done or 0))
    end
end
W.RECORD_KEY=0x1234*4294967296+1
W.AVATAR='4D1C334D294DFA97'

-- The loadout screen (domains/stratagem_selector.lua; research/runtime-stratagem-ui-F5FEE03DCFDB.json) and its pinned
-- code. W.loadout_screen(spec): the UI object behind the owner global, with the local record (spec.index, default 0)
-- holding spec.entries ({type, uses}), spec.players records with an owner id (default 1, the local one first),
-- spec.subState (default 10, the stratagem grid), spec.editedSlot (default 0), spec.ready / spec.launched, and the local
-- panel bound to the local record with its four slot widgets painted from it. Returns {ui, record, frame(), entry(k),
-- widget(k), set(field, value), close()}: frame() is the game's per-frame bind (0x1895A20): while the panel's cached
-- record pointer differs from the record it repaints the widgets from the record's entries and caches the pointer.
local SEL=require('hd2runtime/domains/stratagem_selector')
for _,pin in ipairs(SEL.pins)do write((pin.module=='exe'and EXE or GAME)+pin.rva,unhex(pin.hex))end
-- The game's own selection close (research selectorClose): its exact first bytes.
write(GAME+SEL.selectorClose.rva,unhex(SEL.selectorClose.prologue))
-- The loadout screens by UI address (the native selection close acts on the one it is given).
W.SCREENS={}
-- The icon shader's mask colours as game.dll holds them (research iconShader): the colour set table, c1 and c2.
do
    local C=SEL.iconColours
    local TABLE={{0.8,1.0,0.43137255,0.35686275},{1.0,0.78823531,0.69803923,0.40784314},
        {0.8,0.34117648,0.84313726,0.98039216},{1.0,0.4,0.58039218,0.3137255},{1.0,0.78823531,0.69803923,0.40784314}}
    for k,v in ipairs(TABLE)do write(GAME+C.table+(k-1)*C.stride,f32(v[1])..f32(v[2])..f32(v[3])..f32(v[4]))end
    write(GAME+C.c1,f32(1)..f32(1)..f32(1)..f32(0.93333334))
    write(GAME+C.c2,f32(0.2)..f32(0)..f32(0)..f32(0))
end
function W.loadout_screen(spec)
    spec=spec or{}
    local LO=SEL.loadout
    local owner=alloc(0x100)
    local ui=alloc(0x280000)   -- through the selection-open byte (+0x273990)
    write(GAME+LO.ownerGlobal,u64(owner));write(owner+LO.root,u64(ui))
    local index=spec.index or 0
    write(ui+LO.subState,u32(spec.subState or LO.gridSubState));write(ui+LO.editedSlot,u32((spec.editedSlot or 0)%4294967296))
    -- The selection-open byte (ui+0x273990): set unless spec.selecting is false (a focused slot with no open grid).
    write(ui+LO.selectionOpen,string.char(spec.selecting==false and 0 or 1))
    write(ui+LO.localRecordIndex,u32(index))
    write(ui+LO.ready,string.char(spec.ready and 1 or 0));write(ui+LO.launched,string.char(spec.launched and 1 or 0))
    local players=spec.players or 1
    local order={index}
    for k=0,LO.recordCount-1 do if k~=index then order[#order+1]=k end end
    for n=1,players do write(ui+LO.records+order[n]*LO.recordStride+LO.owner,u64(0x7700+n))end
    local record=ui+LO.records+index*LO.recordStride
    local entries=spec.entries or{}
    for k,entry in ipairs(entries)do
        local at=record+LO.entries+(k-1)*LO.entryStride
        write(at+LO.entryType,u32(entry.type));write(at+LO.entryUses,u32((entry.uses or-1)%4294967296))
    end
    write(record+LO.count,u32(#entries))
    local out={ui=ui,record=record,owner=owner,repaints=0,pushes={}}
    -- Each slot widget's icon element (domains/stratagem_selector.lua slotIcon): an image element (kind 3) with a
    -- material, base UV (0, 0, 1, 1), under a widget element under a panel root (+0xF0 parents).
    local I=SEL.slotIcon
    local root=alloc(0x1000)
    write(root+I.flags,u32(0));write(root+I.parent,u64(0))
    local elements,parents={},{}
    for k=0,3 do
        local e=ui+LO.panel0Widgets+k*LO.widgetStride+I.element
        local p=alloc(0x1000)
        write(p+I.flags,u32(0));write(p+I.parent,u64(root))
        write(e+I.flags,u32(I.imageKind*2^I.kindShift));write(e+I.parent,u64(p))
        write(e+I.base,f32(0)..f32(0)..f32(1)..f32(1))
        write(e+I.material,u64(0x5500+k));write(e+I.primitive,u32(100+k))
        elements[k],parents[k]=e,p
    end
    out.root=root
    -- The local panel's focus (domains/stratagem_selector.lua slotFocus): the focus on the edited slot (or spec.focus),
    -- no previous focus, the panel local, the local group active, its container bound; each slot widget's flags carry
    -- bit 1 on the focused one and bit 3 while a selection is open, its frame drawn as the widget visual update draws it.
    local FO=SEL.slotFocus
    local P=ui+FO.panel
    local focus=spec.focus or((spec.editedSlot or 0)>=0 and(spec.editedSlot or 0)<4 and(spec.editedSlot or 0)or 0)
    write(P+FO.focus,u32(focus%4294967296));write(P+FO.previous,u32(4294967295));write(P+FO.localFlag,string.char(1))
    write(ui+FO.activeGroup,u32(0));write(ui+FO.containerBound,u64(0x7400))
    out.panel=P
    out.panelUpdate=true
    local function widget(k)return ui+LO.panel0Widgets+k*LO.widgetStride end
    function out.widget_flags(k)return le32(read(widget(k)+FO.widgetFlags,2)..string.char(0,0))end
    local function visuals(k)
        -- The widget visual update (0x18932F0), as far as the tests read it: the frame thickness and gap, and with the
        -- selection open the frame and selected-element opacities.
        local W=widget(k)
        local fl=out.widget_flags(k)
        local focused,selection=math.floor(fl/FO.focusedBit)%2==1,math.floor(fl/FO.selectionBit)%2==1
        write(W+FO.thickness,f32(focused and 3 or 2));write(W+FO.gap,f32(focused and 0 or 16))
        write(W+FO.frame+FO.opacity,f32((focused and selection)and 0 or 1))
        write(W+FO.selectedElement+FO.opacity,f32((focused and selection)and 1 or 0))
        out.visual_updates=(out.visual_updates or 0)+1
    end
    out.visuals=visuals
    for k=0,3 do
        local fl=(k==focus and FO.focusedBit or 0)+(spec.selecting==false and 0 or FO.selectionBit)
        write(widget(k)+FO.widgetFlags,string.char(fl%256,0))
        visuals(k)
    end
    out.visual_updates=0
    -- The panel update's end of a frame flash (0x1894C30): a set byte with no colour tween on the frame is cleared and
    -- the widget redrawn from its flags; only in panel mode 0 with the container bound.
    function out.panel_update()
        if not out.panelUpdate then return end
        if le32(read(ui+LO.panelMode,4))~=0 or le32(read(ui+FO.containerBound,4))==0 then return end
        for k=0,3 do
            local W=widget(k)
            if read(W+FO.flash,1):byte()~=0 then
                local ff=le32(read(W+FO.frame,4))
                local tw=le32(read(W+FO.frame+FO.colourTween,4))
                if not(math.floor(ff/FO.colourTweenFlag)%2==1 and tw%(FO.tweenMask+1)~=0)then
                    write(W+FO.flash,string.char(0))
                    visuals(k)
                end
            end
        end
    end
    function out.element(k)return elements[k]end
    function out.parent(k)return parents[k]end
    local function flags_of(a)return le32(read(a+I.flags,4))end
    local function rect_of(k)
        local s=read(elements[k]+I.rect,16)
        local v={}
        for i=0,3 do v[i+1]=require('hd2runtime/core/bytes').value(s,i*4,'f32')end
        return v
    end
    out.rect=rect_of
    -- The game's image setter (0x1450160) for a slot taking a type: the name, the sprite rectangle, the UV, dirty bits.
    local function set_image(k,kind)
        local e=elements[k]
        local rowp=le32(read(GAME+0x37CB600+kind*8,4))+le32(read(GAME+0x37CB600+kind*8+4,4))*4294967296
        local name=rowp~=0 and read(rowp+0xB0,8)or u64(0)
        write(e+I.name,name)
        local key=('0x%08X%08X'):format(le32(name:sub(5,8)),le32(name:sub(1,4)))
        local sprite=W.atlas[key]
        local r=sprite and sprite.rect or{0,0,1,1}
        write(e+I.rect,f32(r[1])..f32(r[2])..f32(r[3])..f32(r[4]))
        write(e+I.uv,f32(r[1])..f32(r[2])..f32(r[1]+r[3])..f32(r[2]+r[4]))
        local fl=flags_of(e)
        if math.floor(fl/I.dirty)%2==0 then write(e+I.flags,u32(fl+I.dirty))end
        local a=parents[k]
        while a~=0 do
            local af=flags_of(a)
            if math.floor(af/I.childDirty)%2==1 then break end
            write(a+I.flags,u32(af+I.childDirty))
            a=le32(read(a+I.parent,4))+le32(read(a+I.parent+4,4))*4294967296
        end
    end
    -- The scene update (0x143EC80): a dirty image element's rectangle is pushed (recorded) and its dirty bits cleared;
    -- each ancestor's child-dirty bit too.
    function out.scene_update()
        for k=0,3 do
            local e=elements[k]
            local fl=flags_of(e)
            if math.floor(fl/I.dirty)%2==1 then
                out.pushes[k]=rect_of(k)
                local cleared=fl-I.dirty
                if math.floor(cleared/I.childDirty)%2==1 then cleared=cleared-I.childDirty end
                write(e+I.flags,u32(cleared))
            end
        end
        for _,a in ipairs({parents[0],parents[1],parents[2],parents[3],root})do
            local af=flags_of(a)
            if math.floor(af/I.childDirty)%2==1 then write(a+I.flags,u32(af-I.childDirty))end
        end
    end
    function out.entry(k)
        local at=record+LO.entries+k*LO.entryStride
        return le32(read(at+LO.entryType,4)),le32(read(at+LO.entryUses,4))
    end
    function out.count()return le32(read(record+LO.count,4))end
    function out.widget(k)return le32(read(ui+LO.panel0Widgets+k*LO.widgetStride+LO.widgetType,4))end
    function out.bound()return le32(read(ui+LO.panel0BoundRecord,4))+le32(read(ui+LO.panel0BoundRecord+4,4))*4294967296 end
    local function paint()
        -- The repaint's first bind (0x18963B5): after the cached record pointer was cleared, a local panel whose focus is
        -- not slot 0 gets the focus on slot 0, both widgets redrawn (the native inline focus setter).
        local first_bind=out.initialised and out.bound()==0
        if first_bind then
            local FS=SEL.slotFocus
            local old=le32(read(out.panel+FS.focus,4))
            if old~=0 and old<4 then
                write(out.panel+FS.previous,u32(old));write(out.panel+FS.focus,u32(0))
                local function flag(k,on)
                    local fl=out.widget_flags(k)
                    local has=math.floor(fl/FS.focusedBit)%2==1
                    if on and not has then fl=fl+FS.focusedBit elseif not on and has then fl=fl-FS.focusedBit end
                    write(ui+LO.panel0Widgets+k*LO.widgetStride+FS.widgetFlags,string.char(fl%256))
                end
                flag(old,false);out.visuals(old);flag(0,true);out.visuals(0)
                out.first_binds=(out.first_binds or 0)+1
            end
        end
        local n=le32(read(record+LO.count,4))
        local slot=0
        for k=0,math.min(n,32)-1 do
            local kind=le32(read(record+LO.entries+k*LO.entryStride+LO.entryType,4))
            if kind~=0 and slot<4 then
                write(ui+LO.panel0Widgets+slot*LO.widgetStride+LO.widgetType,u32(kind))
                set_image(slot,kind)
                slot=slot+1
            end
        end
        for k=slot,3 do write(ui+LO.panel0Widgets+k*LO.widgetStride+LO.widgetType,u32(0))end
        write(ui+LO.panel0BoundRecord,u64(record))
        out.repaints=out.repaints+1
    end
    function out.frame()
        if out.bound()~=record then paint()end
        out.panel_update();out.scene_update()
        -- After a native close: the screen update's sub-state from the focused slot (10 for a stratagem slot 0-3).
        if out.substate_recompute then
            local f=le32(read(out.panel+SEL.slotFocus.focus,4))
            write(ui+LO.subState,u32(f<4 and LO.gridSubState or 0))
        end
    end
    function out.set(field,value)
        if field=='subState'or field=='editedSlot'then write(ui+LO[field],u32(value%4294967296))
        elseif field=='ready'or field=='launched'then write(ui+LO[field],string.char(value and 1 or 0))
        elseif field=='selecting'then
            write(ui+LO.selectionOpen,string.char(value and 1 or 0))
            -- The open and close handlers set and clear bit 3 on the slot widgets and redraw them.
            for k=0,3 do
                local fl=out.widget_flags(k)
                local has=math.floor(fl/SEL.slotFocus.selectionBit)%2==1
                if value and not has then fl=fl+SEL.slotFocus.selectionBit elseif not value and has then
                    fl=fl-SEL.slotFocus.selectionBit end
                write(ui+LO.panel0Widgets+k*LO.widgetStride+SEL.slotFocus.widgetFlags,string.char(fl%256,0))
                out.visuals(k)
            end
        else error('fixture field '..tostring(field))end
    end
    function out.close()write(owner+LO.root,u64(0))end
    -- The game's own selection close (0x146F3B0) as far as the tests read it, at once: ui+0x273991 from +0x273992, the
    -- selection byte and the sub-state 0, the card list's row and card counts 0, bit 3 off on the four slot widgets
    -- (each redrawn). The focus stays where it is; from the next frame the screen update recomputes the sub-state from
    -- it (research note 8).
    function out.native_close()
        out.substate_recompute=true
        write(ui+0x273991,read(ui+0x273992,1))
        out.set('selecting',false)
        write(ui+LO.subState,u32(0))
        write(ui+SEL.grid.list+SEL.grid.rowCount,u32(0));write(ui+SEL.grid.list+SEL.grid.cardCount,u64(0))
        out.native_closes=(out.native_closes or 0)+1
    end
    W.SCREENS[ui]=out
    paint()
    out.repaints=0
    out.initialised=true
    return out
end
-- The game's own selection close (research selectorClose): recorded; on a W.loadout_screen UI it does what the handler
-- does at once (screen.native_close). W.SELECTOR_CLOSE_INERT: the call changes nothing (a close that did not happen).
runtime.selector_closes={}
function runtime.native_selector_close(entry,ui)
    assert(entry==GAME+SEL.selectorClose.rva,'the selection closed through the wrong function')
    runtime.selector_closes[#runtime.selector_closes+1]={ui=ui}
    local screen=W.SCREENS[ui]
    if screen and not W.SELECTOR_CLOSE_INERT then screen.native_close()end
    return true
end
-- W.native_grid(screen, spec): the native stratagem grid of a W.loadout_screen, laid out and scrolled as the game does it
-- (domains/stratagem_selector.lua grid and grid.scroll): spec.rows = {cards in each layout row}, spec.sections = {first
-- row of each section} (default {0}) with spec.sectionIds (their categories, default 1, 2, ...), spec.header (header
-- units on each section's first row, default 30), spec.scroll (units; clamped to the limit as the game clamps it;
-- 'bottom' for the limit), spec.scale (pixels per unit, default 1.2), spec.frame = {x, y} (the list frame's bottom-left
-- corner on screen, default 590, 200; it is 395 x 528 units), spec.left (units from the frame's left edge to column 0,
-- default 12). Each row is 85 units (80-unit cards, 5-unit gap) plus its header; the content height is their sum; the
-- limit is content + 20 - 528 when the content is taller than 528, else 0. The realized rows are those meeting the
-- viewport; each realized card element gets its size and world transform, the frame element its own. Returns {rows =
-- {[absolute row] = {card rects}}, content, scroll, limit, first, realized}.
function W.native_grid(screen,spec)
    local GR=SEL.grid
    local E,SC=GR.element,GR.scroll
    local list=screen.ui+GR.list
    local function element(at,units_w,units_h,x,y,w,h)
        write(at+E.size,f32(units_w)..f32(units_h))
        write(at+E.m00,f32(w/units_w));write(at+E.m02,f32(0));write(at+E.m20,f32(0));write(at+E.m22,f32(h/units_h))
        write(at+E.tx,f32(x));write(at+E.ty,f32(y))
    end
    local rows,sections=spec.rows,spec.sections or{0}
    local header=spec.header or 30
    local scale=spec.scale or 1.2
    local frame=spec.frame or{x=590,y=200}
    local left=spec.left or 12
    local starts={}
    for _,start in ipairs(sections)do starts[start]=true end
    local heights,tops,content={},{},0
    for r=0,#rows-1 do
        tops[r]=content
        heights[r]=SC.cell+SC.gap+(starts[r]and header or 0)
        content=content+heights[r]
    end
    local limit=content>SC.viewport and content+SC.padding-SC.viewport or 0
    local scroll=spec.scroll=='bottom'and limit or math.max(0,math.min(spec.scroll or 0,limit))
    -- The realized rows: every row meeting [scroll, scroll + viewport], at most 12.
    local first,last
    for r=0,#rows-1 do
        if tops[r]+heights[r]>scroll and tops[r]<scroll+SC.viewport then first=first or r;last=r end
    end
    local realized=math.min(last-first+1,12)
    write(list+GR.rowCount,u32(#rows));write(list+GR.firstRealizedRow,u32(first));write(list+GR.realizedRows,u32(realized))
    write(list+GR.sections,u32(#sections))
    for k,start in ipairs(sections)do
        write(list+GR.sectionFirstRow+(k-1)*4,u32(start))
        write(list+SC.sectionIds+(k-1)*4,u32(spec.sectionIds and spec.sectionIds[k]or k))
    end
    local total=0
    for r,n in ipairs(rows)do
        write(list+GR.rowCards+(r-1)*4,u32(n));write(list+SC.rowHeights+(r-1)*4,f32(heights[r-1]))
        total=total+n
    end
    write(list+GR.cardCount,u32(total))
    write(list+SC.content,f32(content));write(list+SC.offset,f32(scroll));write(list+SC.limit,f32(limit))
    element(list,SC.frame[1],SC.frame[2],frame.x,frame.y,SC.frame[1]*scale,SC.frame[2]*scale)
    local top=frame.y+SC.frame[2]*scale
    local out={rows={},content=content,scroll=scroll,limit=limit,first=first,realized=realized}
    for r=first,first+realized-1 do
        local base=list+(r-first)*GR.rowWidgetStride
        local n=rows[r+1]
        write(base+GR.rowRealizedCards,u32(n))
        out.rows[r]={}
        local bottom=tops[r]+heights[r]-SC.gap
        for c=0,n-1 do
            local rect={x=frame.x+(left+c*(SC.cell+SC.gap))*scale,y=top-(bottom-scroll)*scale,w=SC.cell*scale,
                h=SC.cell*scale}
            element(base+GR.cardWidget+c*GR.cardWidgetStride,80,80,rect.x,rect.y,rect.w,rect.h)
            out.rows[r][c+1]=rect
        end
    end
    return out
end
-- W.native_details(screen, spec): the native details panel of a W.loadout_screen (research detailsPanel): the GUI element
-- at ui+0x24B520 with its laid-out size (spec.units, default the stratagem layout 1024 x 400) and its world transform:
-- spec.x, spec.y (its bottom-left corner on screen, pixels), spec.scale (pixels per unit; spec.scaleY for an uneven one).
-- Returns its screen rectangle.
function W.native_details(screen,spec)
    local E=SEL.grid.element
    local at=screen.ui+SEL.loadout.details
    local units=spec.units or SEL.loadout.detailsUnits
    local sx,sy=spec.scale,spec.scaleY or spec.scale
    write(at+E.size,f32(units[1])..f32(units[2]))
    write(at+E.m00,f32(sx));write(at+E.m02,f32(0));write(at+E.m20,f32(0));write(at+E.m22,f32(sy))
    write(at+E.tx,f32(spec.x));write(at+E.ty,f32(spec.y))
    return {x=spec.x,y=spec.y,w=units[1]*sx,h=units[2]*sy}
end
-- W.engine_worlds({World pointers}): the engine's world array in Application.worlds order (domains/stratagem_selector.lua
-- slotOverlay: [exe + application] + worldCount / worldArray).
function W.engine_worlds(pointers)
    local O=SEL.slotOverlay
    local app=alloc(0x1000)
    local array=alloc(8*math.max(1,#pointers))
    for k,ptr in ipairs(pointers)do write(array+8*(k-1),u32(ptr%4294967296)..u32(math.floor(ptr/4294967296)))end
    write(app+O.worldCount,u32(#pointers));write(app+O.worldArray,u64(array))
    write(EXE+O.application,u64(app))
    return app
end
-- W.input_actions({[action] = true}): the game's evaluated input actions of the menu group (domains/stratagem_selector.lua
-- input), byte 0 set for each triggered action.
function W.input_actions(triggered)
    local IA=SEL.input
    local owner=alloc(IA.states+IA.groups*IA.groupActions*IA.stride+0x100)
    write(GAME+IA.ownerGlobal,u64(owner))
    for action in pairs(triggered or{})do
        write(owner+IA.states+(IA.menu.group*IA.groupActions+action)*IA.stride,string.char(1))
    end
    return owner
end
return W
