-- What the local Helldiver holds and wears, the worn backpack's own values, and the Supply Pack's own self-use
-- (docs/player-equipment.md; research/player-equipment-F5FEE03DCFDB.json; domains/player_equipment.lua).
--
-- Reads: the avatar's inventory record (primary +0x00, secondary +0x04, support +0x08, backpack +0x0C, held item +0x10,
-- throwable resource +0x28 and its count), each item's type through the game's own entity map, the worn backpack's
-- deposit instance (live amount, definition) and a weapon's magazine instance (spare magazines, rounds). Every value is
-- re-read through the game's own hashes on every call and checked against the descriptor that names the entity; no
-- address is kept between calls. Only the local player: no retained snapshot shows another player's records.
--
-- One native action, the Supply Pack's self-use (hd2.actions.resupply_from_pack): exactly the request the game's own
-- input step makes when the wearer presses the pack's key (game.dll 0xA433F0): the self-use ability the pack's own
-- deposit definition names (+0x24, 2629) is started on the avatar through the game's own try_start_action(context,
-- request) (0xA431D0: not busy, may act, start_action), which the game's interaction code also uses. The game's ability
-- then consumes one supply from the worn backpack and resupplies the wearer on its animation event, with its own
-- network replication. Runtime first refuses, without calling anything, whatever the game would refuse (no Supply Pack,
-- no supplies, busy, may not act), and asks the game's own needs_ammo(user) query (0x9AD7D0, a pure function: its call
-- tree writes nothing) so a supply is never spent on full ammunition. Nothing is written by Runtime.
local world_module=require('hd2runtime/runtime/event_world')
local D=require('hd2runtime/domains/player_equipment')
local natives=require('hd2runtime/domains/event_natives')
local b=require('hd2runtime/core/bytes')
local bit=require('bit')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local I,DP,MG,AV,AB,SP,N=D.inventory,D.deposit,D.magazine,D.avatar,D.ability,D.supplyPack,D.natives
M.SLOTS={'primary','secondary','support','backpack'}
M.SUPPLY_PACK=SP.name

local proven                 -- {key, ok, why}: the pins, once per loaded game.dll
local adapter_override,native

------------------------------------------------------------------------------------------------------ proofs --
-- Every pin of the research (layouts, the self-use path, both functions' surroundings), once per world.
function M.prove(world)
    if proven and proven.key==world.key then return proven.ok,proven.why end
    local ok,why=true,nil
    if D.source.gameDllSha256~=natives.source.gameDllSha256 then
        ok,why=false,'the player equipment research covers another game.dll build'
    else
        for _,pin in ipairs(D.pins)do
            if not world.view.proves(world.game+pin.rva,pin.hex)then
                ok,why=false,('native equipment structure changed (%s at game+%X)'):format(pin.label,pin.rva)
                break
            end
        end
    end
    proven={key=world.key,ok=ok,why=why}
    metrics.count('player_equipment.proofs')
    return ok,why
end

------------------------------------------------------------------------------------------------------ hashes --
local function power_of_two(n)
    if n<1 or n%1~=0 then return false end
    while n>1 do if n%2~=0 then return false end n=n/2 end
    return true
end
-- A value in one of the game's open-addressed u32 hashes ({buckets u64, capacity, empty key, multiplier}):
-- slot = (key * multiplier + i) & (capacity - 1). nil when absent, unreadable or implausible.
local function hash_value(world,header_address,key)
    if type(key)~='number'or key<=0 or key>=4294967296 or key%1~=0 then return nil end
    local header=world.view.read(header_address,20)
    if not header then return nil end
    local buckets=b.pointer(header,0)
    local capacity,empty,multiplier=b.u32(header,8),b.u32(header,12),b.u32(header,16)
    if buckets==0 or capacity>1048576 or not power_of_two(capacity)then return nil end
    local start=world_module.mul32(key,multiplier)
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
-- A component descriptor {entity, type (16 hex digits), type_lo, type_hi, owned}, or nil.
local function descriptor(world,pointer)
    local bytes=pointer and world.view.read(pointer,0x18)
    if not bytes then return nil end
    local lo,hi=b.u32(bytes,0),b.u32(bytes,4)
    return {entity=b.u32(bytes,8),type=string.format('%08X%08X',hi,lo),type_lo=lo,type_hi=hi,
        owned=b.u32(bytes,0x14)%2==1}
end
-- The instance of `entity` in the manager at [game + layout.global]: manager, index, descriptor; the descriptor must
-- name the same entity. `inline`: the descriptor pointers are inside the manager (the avatar manager), else behind a
-- pointer to an array.
local function instance(world,layout,entity,inline)
    local manager=world.view.pointer(world.game+layout.global)
    if not manager then return nil end
    local index=hash_value(world,manager+layout.hash,entity)
    if not index or index>=0x10000 then return nil end
    local pointer
    if inline then pointer=world.view.pointer(manager+layout.descriptors+index*8)
    else
        local array=world.view.pointer(manager+layout.descriptors)
        pointer=array and world.view.pointer(array+index*8)
    end
    local desc=descriptor(world,pointer)
    if not desc or desc.entity~=entity then return nil end
    return manager,index,desc
end

------------------------------------------------------------------------------------------------------- reads --
-- The avatar's inventory record: {index, owned, slots = {primary, secondary, support, backpack, held} (entity ids, 0 =
-- empty), selection, throwable (16 hex digits or nil), throwable_count}; nil and the reason when it has none.
function M.inventory(world,avatar)
    local manager,index,desc=instance(world,I,avatar)
    if not manager then return nil,'the avatar has no inventory record'end
    local records=world.view.pointer(manager+I.records)
    local record=records and world.view.read(records+index*I.stride,I.stride)
    local counts=world.view.pointer(manager+I.counts)
    local count=counts and world.view.u32(counts+index*I.countStride+I.throwableCount)
    if not record or not count then return nil,'the inventory record is unreadable'end
    local slots={}
    for name,offset in pairs(I.slots)do slots[name]=b.u32(record,offset)end
    local lo,hi=b.u32(record,I.throwable),b.u32(record,I.throwable+4)
    return {index=index,owned=desc.owned,slots=slots,selection=b.u32(record,I.selection),
        throwable=(lo~=0 or hi~=0)and string.format('%08X%08X',hi,lo)or nil,throwable_count=count}
end
-- A catalogued item: {entity_id, type, name, kind ('primary', 'secondary', 'support', 'throwable', 'backpack'), api},
-- or nil for an empty slot. An entity the engine no longer holds, or whose descriptor names another entity, is nil;
-- an uncatalogued one keeps name and kind nil.
function M.item(world,entity)
    if type(entity)~='number'or entity==0 then return nil end
    if world_module.entity_exists(world,entity)~=true then return nil end
    local type_hex=world_module.entity_type(world,entity)
    if not type_hex then return nil end
    local info=D.items[type_hex]
    return {entity_id=entity,type=type_hex,name=info and info.name,kind=info and info.kind,api=info and info.api,
        feeds=info and info.feeds,carries=info and info.carries}
end
-- x mod 58 for the u64 type hi:lo (exact in doubles).
local function mod58(lo,hi)return((hi%58)*(4294967296%58)+lo%58)%58 end
-- The deposit definition the game uses for this instance (0x502710): a per-instance override, else the per-type table.
local function definition(world,manager,entity,desc)
    local record,source
    local override=hash_value(world,manager+DP.overrideHash,entity)
    if override then
        local records=world.view.pointer(manager+DP.overrideRecords)
        record,source=records and records+override*DP.definitionStride,'instance'
    else
        local S=DP.settings
        local em=world.view.pointer(world.game+S.entityManager)
        local table_address=em and world.view.pointer(em+S.table)
        if not table_address then return nil end
        local start=mod58(desc.type_lo,desc.type_hi)
        for probe=0,S.buckets-1 do
            local bytes=world.view.read(table_address+((start+probe)%S.buckets)*S.entryStride,12)
            if not bytes then return nil end
            local lo,hi=b.u32(bytes,0),b.u32(bytes,4)
            if lo==desc.type_lo and hi==desc.type_hi then
                record,source=table_address+S.records+b.u32(bytes,8)*DP.definitionStride,'type'
                break
            end
            if lo==0 and hi==0 then return nil end
        end
    end
    local F=DP.definition
    local bytes=record and world.view.read(record,F.selfAbility+4)
    if not bytes then return nil end
    local start=b.u32(bytes,F.startAmount)
    return {capacity=b.u32(bytes,F.capacity),start_amount=start>=2147483648 and start-4294967296 or start,
        refill_amount=b.u32(bytes,F.refillAmount),other_ability=b.u32(bytes,F.otherAbility),
        self_ability=b.u32(bytes,F.selfAbility),source=source}
end
-- A deposit instance (a supply, guard dog or weapon-fed backpack): {amount, capacity, start_amount, refill_amount,
-- self_ability, other_ability, definition ('instance' or 'type'), owned, drone_network_id}; nil when it has none.
function M.deposit(world,entity)
    local manager,index,desc=instance(world,DP,entity)
    if not manager then return nil end
    local live=world.view.pointer(manager+DP.live)
    local bytes=live and world.view.read(live+index*DP.liveStride,8)
    if not bytes then return nil end
    local def=definition(world,manager,entity,desc)
    if not def then return nil end
    local drone=b.u32(bytes,DP.drone)
    return {amount=b.u32(bytes,DP.amount),capacity=def.capacity,start_amount=def.start_amount,
        refill_amount=def.refill_amount,self_ability=def.self_ability,other_ability=def.other_ability,
        definition=def.source,owned=desc.owned,drone_network_id=(drone~=0 and drone~=0x7FFF)and drone or nil}
end
-- A weapon's magazine instance: {rounds (in the magazine), spare_magazines}; nil when the weapon has none.
function M.magazine(world,weapon)
    local manager,index=instance(world,MG,weapon)
    if not manager then return nil end
    local records=world.view.pointer(manager+MG.records)
    local bytes=records and world.view.read(records+index*MG.stride,8)
    if not bytes then return nil end
    return {rounds=b.u32(bytes,MG.rounds),spare_magazines=b.u32(bytes,MG.spare)}
end
-- The avatar's action context (the game's own per-avatar action request block) and flags: {address, ability, target,
-- extra, busy, may_act}; nil when the avatar has none.
function M.action_context(world,avatar)
    local manager,index=instance(world,AV,avatar,true)
    if not manager then return nil end
    local address=manager+AV.context+index*AV.stride
    local fields=world.view.read(address,16)
    local flags=world.view.read(manager+AV.flags+index*AV.stride,16)
    if not fields or not flags or b.u32(fields,AV.contextFields.entity)~=avatar then return nil end
    local f0lo,f0hi,f1lo,f1hi=b.u32(flags,0),b.u32(flags,4),b.u32(flags,8),b.u32(flags,12)
    local busy=math.floor(f1lo/2^AV.busyBit)%2==1
    local may_act=bit.band(f1lo,AV.mayActMask.lo)==0 and bit.band(f1hi,AV.mayActMask.hi)==0
        and bit.band(f0lo,AV.blockingMask.lo)==0 and bit.band(f0hi,AV.blockingMask.hi)==0
        and bit.band(f0lo,AV.mayActRequired)~=0
    return {address=address,ability=b.u32(fields,AV.contextFields.ability),target=b.u32(fields,AV.contextFields.target),
        extra=b.u32(fields,AV.contextFields.extra),busy=busy,may_act=may_act}
end
-- The ability the avatar runs now: {id, active}; nil when it has no ability record.
function M.running_ability(world,avatar)
    local manager,index=instance(world,AB,avatar)
    if not manager then return nil end
    local records=world.view.pointer(manager+AB.records)
    local bytes=records and world.view.read(records+index*AB.stride,AB.active+1)
    if not bytes then return nil end
    return {id=b.u32(bytes,AB.id),active=bytes:byte(AB.active+1)~=0}
end

------------------------------------------------------------------------------------------- player-level reads --
local function player_avatar(world,player)
    for _,item in ipairs(world_module.players(world,true))do
        if item.peer==player.peer then
            if not item.avatar then return nil,'NO_AVATAR: the player has no avatar now'end
            return item.avatar
        end
    end
    return nil,'NO_AVATAR: the player is no longer in the player list'
end
local function open_for(player)
    if not player.is_local then
        return nil,nil,'NOT_LOCAL_PLAYER: only the local player\'s equipment is read (no retained snapshot proves '
            ..'another player\'s records)'
    end
    local world,why=world_module.open()
    if not world then return nil,nil,'EQUIPMENT_UNAVAILABLE: '..tostring(why)end
    local ok,reason=M.prove(world)
    if not ok then return nil,nil,'EQUIPMENT_UNAVAILABLE: '..tostring(reason)end
    local avatar,missing=player_avatar(world,player)
    if not avatar then return nil,nil,missing end
    return world,avatar
end
-- The worn backpack of the avatar: the item plus {deposit = M.deposit or nil, supply_pack}; nil and the reason.
local function backpack_of(world,inventory)
    local item=M.item(world,inventory.slots.backpack)
    if not item then return nil,'NO_BACKPACK: the avatar wears no backpack'end
    item.deposit=M.deposit(world,item.entity_id)
    item.supply_pack=item.type==SP.type
    return item
end
local SLOT_PROVEN={primary=true,secondary=true,support=true}
-- player:loadout(): {avatar_id, selection, primary, secondary, support, backpack, held, throwable}. Each of primary,
-- secondary, support, held is an item (M.item) or nil; backpack adds deposit and supply_pack; throwable is {name, type,
-- count, api}. nil and 'CODE: reason' when it cannot be read.
function M.loadout(player)
    local world,avatar,why=open_for(player)
    if not world then return nil,why end
    local inventory,missing=M.inventory(world,avatar)
    if not inventory then return nil,'NO_INVENTORY: '..missing end
    local out={avatar_id=avatar,selection=inventory.selection}
    for _,slot in ipairs({'primary','secondary','support','held'})do out[slot]=M.item(world,inventory.slots[slot])end
    out.backpack=backpack_of(world,inventory)
    if inventory.throwable then
        local info=D.items[inventory.throwable]
        out.throwable={type=inventory.throwable,name=info and info.name,api=info and info.api,
            count=inventory.throwable_count}
    end
    metrics.count('player_equipment.loadouts')
    return out
end
-- player:held_weapon(): the item in hand plus {slot, slot_proven, selection, avatar_id}; the slot is the inventory slot
-- that holds that same entity ('primary', 'secondary', 'support' proven by the record), else 'held_item' (a throwable,
-- stratagem ball or carried object held from record +0x10) or 'unknown'. nil and the reason when nothing is in hand.
function M.held_weapon(player)
    local world,avatar,why=open_for(player)
    if not world then return nil,why end
    local held,reason=world_module.equipped(world,avatar)
    if not held then return nil,'EQUIPMENT_UNAVAILABLE: '..tostring(reason)end
    if not held.entity then return nil,'NOTHING_IN_HAND: nothing in hand'end
    local item=M.item(world,held.entity)
    if not item then return nil,'NOTHING_IN_HAND: the held entity no longer exists'end
    local inventory=M.inventory(world,avatar)
    item.slot='unknown'
    for _,slot in ipairs({'primary','secondary','support'})do
        if inventory and inventory.slots[slot]==held.entity then item.slot=slot end
    end
    if item.slot=='unknown'and inventory and inventory.slots.held==held.entity then item.slot='held_item'end
    item.slot_proven=SLOT_PROVEN[item.slot]==true
    item.selection,item.avatar_id=held.selection,avatar
    return item
end
-- player:backpack(): the worn backpack (M.item plus deposit and supply_pack); nil and the reason.
function M.backpack(player)
    local world,avatar,why=open_for(player)
    if not world then return nil,why end
    local inventory,missing=M.inventory(world,avatar)
    if not inventory then return nil,'NO_INVENTORY: '..missing end
    return backpack_of(world,inventory)
end
-- player:ammo([slot]): the ammunition of a weapon slot ('primary', 'secondary', 'support'; default: the weapon in
-- hand): {slot, name, type, entity_id, feed, rounds, spare_magazines, capacity, max_spare_magazines}. feed 'magazine':
-- rounds in the magazine and spare magazines (capacity and max_spare_magazines are the catalog's base values, nil when
-- uncatalogued); feed 'backpack': rounds are the worn backpack's deposit (capacity its definition). nil and the reason
-- for any other feed (heat, rounds-fed, charge): those instances are not researched.
function M.ammo(player,slot)
    if slot~=nil and not SLOT_PROVEN[slot]then
        return nil,'INVALID_SLOT: slot must be \'primary\', \'secondary\' or \'support\''
    end
    local world,avatar,why=open_for(player)
    if not world then return nil,why end
    local inventory,missing=M.inventory(world,avatar)
    if not inventory then return nil,'NO_INVENTORY: '..missing end
    if slot==nil then
        local held=world_module.equipped(world,avatar)
        for _,name in ipairs({'primary','secondary','support'})do
            if held and held.entity and inventory.slots[name]==held.entity then slot=name end
        end
        if not slot then return nil,'NO_WEAPON_IN_HAND: no primary, secondary or support weapon is in hand'end
    end
    local item=M.item(world,inventory.slots[slot])
    if not item then return nil,'EMPTY_SLOT: no '..slot..' weapon'end
    local out={slot=slot,name=item.name,type=item.type,entity_id=item.entity_id}
    local magazine=M.magazine(world,item.entity_id)
    if magazine then
        local info=D.items[item.type]
        out.feed,out.rounds,out.spare_magazines='magazine',magazine.rounds,magazine.spare_magazines
        if info and info.magazine then out.capacity,out.max_spare_magazines=info.magazine.capacity,info.magazine.maxSpare end
        return out
    end
    local pack=M.item(world,inventory.slots.backpack)
    if pack and pack.feeds and pack.feeds==item.name then
        local deposit=M.deposit(world,pack.entity_id)
        if deposit then
            out.feed,out.rounds,out.capacity='backpack',deposit.amount,deposit.capacity
            return out
        end
    end
    return nil,'UNKNOWN_FEED: '..tostring(item.name or item.type)..' is not fed from a magazine or a worn backpack'
end

---------------------------------------------------------------------------------------------- native calls --
-- The two game functions as typed calls (tests replace them with M.set_adapter). Only the Supply Pack's self-use ability
-- and only an entity id for the query.
function M.native_adapter()
    local win=require('hd2runtime/runtime/windows_ffi')
    local ffi=win.ffi
    local A={}
    local function address(v)return type(v)=='number'and v>0 and v<=9007199254740991 and v%1==0 end
    local function u32(v)return type(v)=='number'and v>=0 and v<4294967296 and v%1==0 end
    -- needs_ammo(_, user) -> bool (game.dll 0x9AD7D0; its first argument is never read).
    function A.needs_ammo(entry,user)
        assert(address(entry)and u32(user)and user~=0,'unsupported needs_ammo call')
        local query=ffi.cast('uint8_t (*)(void *, uint32_t)',entry)
        return query(nil,user)~=0
    end
    -- try_start_action(context, request {ability, target, extra}) -> bool (game.dll 0xA431D0).
    function A.start_action(entry,context,ability,target,extra)
        assert(address(entry)and address(context)and ability==SP.selfAbility and u32(target)and u32(extra),
            'unsupported start_action call')
        local request=ffi.new('uint32_t[3]',ability,target,extra)
        local start=ffi.cast('uint8_t (*)(void *, const uint32_t *)',entry)
        local started=start(ffi.cast('void *',context),request)~=0
        -- Keeps the request referenced until the game returned (it copies it during the call).
        assert(request~=nil)
        return started
    end
    return A
end
function M.set_adapter(a)adapter_override=a end
local function caller(world)
    if adapter_override then return adapter_override end
    if not(world.runtime and world.runtime.mode=='live')then return nil,'not a live game process'end
    if not native then
        local ok,a=pcall(M.native_adapter)
        if not ok then return nil,'the native call adapter: '..tostring(a)end
        native=a
    end
    return native
end

-- The Supply Pack's self-use on the avatar, from the game update only. Returns {backpack, supplies, capacity, ability}
-- (supplies before the use), or nil and 'CODE: reason'. Nothing is called unless every check passes.
function M.resupply_self(world,avatar)
    local call,unavailable=caller(world)
    if not call then return nil,'RESUPPLY_UNAVAILABLE: '..unavailable end
    if not scheduler.in_update()then
        return nil,'NOT_GAME_THREAD: the Supply Pack is used only from the game update (a callback, timer or keybind)'
    end
    local ok,why=M.prove(world)
    if not ok then return nil,'RESUPPLY_UNAVAILABLE: '..tostring(why)end
    for name,item in pairs(N)do
        if not world.view.proves(world.game+item.rva,item.prologue)then
            return nil,'RESUPPLY_UNAVAILABLE: the game function '..name..' changed'
        end
    end
    local inventory,missing=M.inventory(world,avatar)
    if not inventory then return nil,'RESUPPLY_UNAVAILABLE: '..missing end
    if not inventory.owned then return nil,'NOT_LOCAL_PLAYER: this machine does not own the avatar'end
    local pack=M.item(world,inventory.slots.backpack)
    if not pack then return nil,'NO_BACKPACK: the avatar wears no backpack'end
    if pack.type~=SP.type then
        return nil,'NOT_A_SUPPLY_PACK: the worn backpack is '..tostring(pack.name or pack.type)..', not the '..SP.name
    end
    local deposit=M.deposit(world,pack.entity_id)
    if not deposit then return nil,'RESUPPLY_UNAVAILABLE: the Supply Pack has no readable deposit'end
    if deposit.self_ability~=SP.selfAbility then
        return nil,'RESUPPLY_UNAVAILABLE: the Supply Pack\'s self-use ability is '..tostring(deposit.self_ability)
            ..', not the researched '..SP.selfAbility
    end
    if deposit.amount<1 then return nil,'NO_SUPPLIES: the Supply Pack is empty'end
    local context=M.action_context(world,avatar)
    if not context then return nil,'RESUPPLY_UNAVAILABLE: the avatar has no action context'end
    local no_target=world.view.u32(world.game+AV.noTarget)
    if no_target==nil then return nil,'RESUPPLY_UNAVAILABLE: the game\'s no-target value is unreadable'end
    if context.busy or context.target~=no_target then return nil,'BUSY: the avatar is already performing an action'end
    if not context.may_act then return nil,'CANNOT_ACT: the avatar cannot start an action now'end
    if not call.needs_ammo(world.game+N.needsAmmo.rva,avatar)then
        return nil,'NO_AMMO_NEEDED: no weapon takes ammunition (the game refuses the pack then: NO ROOM)'
    end
    if not call.start_action(world.game+N.tryStartAction.rva,context.address,SP.selfAbility,no_target,context.extra)then
        return nil,'NOT_STARTED: the game did not start the self-use'
    end
    local running=M.running_ability(world,avatar)
    if not(running and running.id==SP.selfAbility and running.active)then
        return nil,'NOT_STARTED: the avatar does not run the self-use ability after the request'
    end
    metrics.count('player_equipment.self_resupplies')
    return {backpack=pack.entity_id,supplies=deposit.amount,capacity=deposit.capacity,ability=SP.selfAbility}
end

------------------------------------------------------------------------------------------------- installation --
-- Adds the read methods to the player handle (runtime/handles.lua Player).
function M.install(Player)
    Player.loadout=function(self)return M.loadout(self)end
    Player.held_weapon=function(self)return M.held_weapon(self)end
    Player.backpack=function(self)return M.backpack(self)end
    Player.ammo=function(self,slot)return M.ammo(self,slot)end
    Player.resupply_from_pack=function(self,opts)
        local forwarded={}
        for key,value in pairs(type(opts)=='table'and opts or{})do forwarded[key]=value end
        if forwarded.owner==nil then forwarded.owner=require('hd2runtime/runtime/events').owner(nil,2)end
        return require('hd2runtime/api/player_equipment').resupply_from_pack(self,forwarded)
    end
    return Player
end
function M.reset_for_tests()proven,adapter_override,native=nil,nil,nil end
return M
