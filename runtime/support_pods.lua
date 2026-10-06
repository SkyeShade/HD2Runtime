-- A support beacon's hellpod and the exact weapon entities its rack holds (development; read-only;
-- docs/research/gas-eat-F5FEE03DCFDB.md, "Capture"). Not exported by api/hd2.lua: hd2.custom_stratagem call contexts
-- reach it (ctx:spawned_weapons).
--
-- research/support-delivery-F5FEE03DCFDB.json: when a beacon activates, the dispatcher creates the pod and the pod's
-- Transport block names the BEACON (block +0x10, its network id) and the dispatched TYPE (block +0xC). About 0.5 s after
-- the landing the authority spawns the pod's content (a support weapon's rack) and names it in the Transport element
-- (+0x8 = +0x24); in that same native call the rack spawns its items and names each one in a slot (HellpodRack +0x8 + 4 x
-- slot: the item's network id, 0x7FFF none). So the Runtime finds the exact launchers through the game's own records,
-- from the beacon it threw: no scan of the world, no guess.
--
-- M.beacon_network(world, beacon) reads a beacon's network id from its entity handle (+0x10) and accepts it only when the
-- game's own network id map resolves it back to that beacon. M.capture(spec) follows ONE delivery: it finds the pod
-- whose block names that network id and type (exactly one), waits for its rack, checks the rack (present, 8 slots, the
-- type) and resolves every filled slot through the network id map to an entity of the expected entity type. The items are
-- read before anything can take them from the rack (a slot is reset when its item leaves). Everything is re-read each
-- update; nothing is written.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local D=require('hd2runtime/domains/support_delivery')
local M={}
M.POD_SECONDS=15         -- the pod must appear this long after the activation at most
M.RACK_SECONDS=40        -- its rack (the content spawn) this long after the activation at most
M.MAX_TRANSPORTS=256
local T,HD,R=D.transport,D.handle,D.rack

local function log(text)log_module.emit('[HD2Runtime] support pod '..text)end
-- A pointer member, or 0 when it is not a plausible pointer.
local function ptr(s,o)local ok,v=pcall(b.pointer,s,o);return ok and v or 0 end

local proven={}
function M.prove(world)
    if D.source.gameDllSha256~=profile.dll_sha then return nil,'the support delivery research covers another game.dll build'end
    if proven[world.game]then return true end
    for _,pin in ipairs(D.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,('support delivery code changed (%s at game+%X)'):format(pin.label,pin.rva)
        end
    end
    proven[world.game]=true
    return true
end

-- A beacon's network id (read from its entity handle), accepted only when the game's network id map resolves it back to
-- the beacon entity. beacon: {entity, handle_slot} (runtime/beacon_redirect.lua beacon). Returns the id, or nil and why.
function M.beacon_network(world,beacon)
    local handle=beacon and beacon.handle_slot and world.view.pointer(beacon.handle_slot)
    local raw=handle and handle~=0 and world.view.read(handle,HD.network+4)
    if not raw then return nil,'the beacon\'s entity handle is unreadable'end
    if b.u32(raw,HD.entity)~=beacon.entity then return nil,'the beacon\'s entity handle names another entity'end
    local network=b.u32(raw,HD.network)
    if world_module.network_entity(world,network)~=beacon.entity then
        return nil,'the network id map does not resolve the beacon\'s network id back to it'
    end
    return network
end

-- Every Transport pod now: {index, entity, network, content (u64 hex), content_entity, content_copy, type,
-- beacon_network}; or nil and why. Read-only.
function M.pods(world)
    local component=world.view.pointer(world.game+T.global)
    local raw=component and world.view.read(component,T.blocks+8)
    if not raw then return nil,'the Transport component is unreadable'end
    local count=b.u32(raw,T.count)
    if count>M.MAX_TRANSPORTS then return nil,'the Transport component is implausible'end
    local handles,elements,blocks=ptr(raw,T.handles),ptr(raw,T.elements),ptr(raw,T.blocks)
    local out={}
    if count==0 then return out end
    if handles==0 or elements==0 or blocks==0 then return nil,'the Transport arrays are unreadable'end
    for i=0,count-1 do
        local handle=world.view.pointer(handles+i*8)
        local h=handle and handle~=0 and world.view.read(handle,HD.network+4)
        local e=world.view.read(elements+i*T.stride,T.stride)
        local k=world.view.read(blocks+i*T.blockStride,T.blockStride)
        if h and e and k then
            out[#out+1]={index=i,entity=b.u32(h,HD.entity),network=b.u32(h,HD.network),
                content=b.resource(e,T.content),
                content_entity=b.u32(e,T.contentEntity),content_copy=b.u32(e,T.contentEntityCopy),
                type=b.u32(k,T.type),beacon_network=b.u32(k,T.beaconNetwork)}
        end
    end
    return out
end

-- The rack element of a rack entity (the HellpodRack entity map): {index, present, slot_count, type, slots = {network
-- ids}}, or nil and why.
function M.rack(world,entity)
    local component=world.view.pointer(world.game+R.global)
    local raw=component and world.view.read(component+R.keys,R.elements+8-R.keys)
    if not raw then return nil,'the HellpodRack component is unreadable'end
    local keys=ptr(raw,0)
    local cap,empty,mult=b.u32(raw,R.capacity-R.keys),b.u32(raw,R.empty-R.keys),b.u32(raw,R.multiplier-R.keys)
    local elements=ptr(raw,R.elements-R.keys)
    if keys==0 or elements==0 or cap==0 or cap>65536 then return nil,'the HellpodRack map is unreadable'end
    local start=world_module.mul32(entity,mult)
    local index
    for probe=0,math.min(cap,4096)-1 do
        local slot=world.view.read(keys+((start+probe)%cap)*8,8)
        if not slot then return nil,'the HellpodRack map is unreadable'end
        local key=b.u32(slot,0)
        if key==entity then index=b.u32(slot,4);break end
        if key==empty then return nil,'the entity has no rack'end
    end
    if not index or index==4294967295 then return nil,'the entity has no rack'end
    local e=world.view.read(elements+index*R.stride,R.stride)
    if not e then return nil,'the rack element is unreadable'end
    local slots={}
    for s=0,R.maxSlots-1 do slots[s+1]=b.u32(e,R.slots+4*s)end
    return {index=index,present=e:byte(R.present+1),slot_count=b.u32(e,R.slotCount),type=b.u32(e,R.type),slots=slots}
end

-- Follows one delivery until what it delivered is known. spec = {beacon_network (M.beacon_network), type (the
-- dispatched stratagem type), label} and one of:
--   * item_type (the expected item entity type, '%08X%08X') or item_types (a set of them: a rack holding a weapon and
--     its backpack): the pod's content is a RACK and its filled slots are the delivered items;
--   * content_type ('%08X%08X'): the pod's content entity IS the delivered entity (a sentry, an emplacement), checked
--     against that entity type.
-- callback(event): 'pod' (entity), 'captured' (pod, rack (the content entity), items = {entity ids}, types = {entity
-- types}, slots), 'refused' (code, reason), 'ended'. Starts at the activation (call it then). Returns the watch
-- {status, cancel()}, or nil and why.
function M.capture(spec,callback)
    if type(spec)~='table'or type(spec.beacon_network)~='number'or type(spec.type)~='number'then
        return nil,'spec must be {beacon_network, type, item_type | item_types | content_type}'
    end
    local accepted
    if type(spec.item_type)=='string'then accepted={[spec.item_type]=true}
    elseif type(spec.item_types)=='table'and next(spec.item_types)then accepted=spec.item_types
    elseif type(spec.content_type)~='string'then
        return nil,'spec must name the delivered entity types (item_type, item_types or content_type)'
    end
    local w={status='active',seconds=0}
    local function emit(event)
        if callback then
            local ok,why=pcall(callback,event)
            if not ok then log('callback failed: '..tostring(why))end
        end
    end
    local function finish(kind,code,reason)
        if w.status~='active'then return end
        w.status='complete'
        if kind=='refused'then
            log(('REFUSED (%s): %s: %s'):format(tostring(spec.label),tostring(code),tostring(reason)))
            emit({kind='refused',code=code,reason=reason})
        end
        emit({kind='ended'})
    end
    function w.tick(dt)
        if w.status~='active'then return end
        w.seconds=w.seconds+(dt or 0)
        local world=world_module.open()
        if not world then return end
        local game=world_module.game_state(world)
        if not(game and game.mission)then return finish('refused','NOT_IN_MISSION','the mission ended')end
        local ok,why=M.prove(world)
        if not ok then return finish('refused','UNSUPPORTED_BUILD',tostring(why))end
        if not w.pod then
            local pods,pwhy=M.pods(world)
            if not pods then return finish('refused','UNREADABLE',tostring(pwhy))end
            local found={}
            for _,p in ipairs(pods)do
                if p.beacon_network==spec.beacon_network and p.type==spec.type then found[#found+1]=p end
            end
            if#found>1 then return finish('refused','AMBIGUOUS',#found..' pods name this beacon')end
            if#found==1 then
                w.pod=found[1].entity
                emit({kind='pod',pod=w.pod,content=found[1].content,network=found[1].network})
            elseif w.seconds>(spec.pod_seconds or M.POD_SECONDS)then
                return finish('refused','NO_POD','no pod named this beacon within '..(spec.pod_seconds or M.POD_SECONDS)
                    ..' s')
            end
            return
        end
        local pods=M.pods(world)
        local pod
        for _,p in ipairs(pods or{})do if p.entity==w.pod then pod=p end end
        if not pod then return finish('refused','POD_GONE','the pod is gone before its rack was read')end
        if pod.beacon_network~=spec.beacon_network or pod.type~=spec.type then
            return finish('refused','POD_CHANGED','the pod no longer names this beacon and type')
        end
        if pod.content_entity==0 then
            if w.seconds>(spec.rack_seconds or M.RACK_SECONDS)then
                return finish('refused','NO_RACK','the pod\'s content was not spawned within '
                    ..(spec.rack_seconds or M.RACK_SECONDS)..' s')
            end
            return
        end
        if pod.content_copy~=pod.content_entity then return finish('refused','POD_CHANGED','the content entity differs')end
        if spec.content_type then
            -- The content entity is the delivery itself (a sentry): its entity type, alive.
            local kind=world_module.entity_type(world,pod.content_entity)
            if kind~=spec.content_type then
                return finish('refused','CONTENT_UNEXPECTED',('the pod\'s content %d is entity type %s, not %s'):format(
                    pod.content_entity,tostring(kind),spec.content_type))
            end
            if world_module.entity_exists(world,pod.content_entity)~=true then
                return finish('refused','CONTENT_GONE','the pod\'s content entity is gone')
            end
            w.status='complete'
            log(('CAPTURED (%s): pod %d -> content %d, entity type %s (the delivered entity itself), read %.1f s after the '
                ..'activation'):format(tostring(spec.label),w.pod,pod.content_entity,kind,w.seconds))
            emit({kind='captured',pod=w.pod,rack=pod.content_entity,content=pod.content_entity,items={pod.content_entity},
                types={kind},slots={},seconds=w.seconds})
            emit({kind='ended'})
            return
        end
        local rack,rwhy=M.rack(world,pod.content_entity)
        if not rack then return finish('refused','NO_RACK',tostring(rwhy))end
        if rack.present~=1 or rack.slot_count~=R.maxSlots or rack.type~=spec.type then
            return finish('refused','RACK_UNEXPECTED',('rack present %d, %d slots, type %d'):format(rack.present,
                rack.slot_count,rack.type))
        end
        local items,slots,types,networks={},{},{},{}
        for s,network in ipairs(rack.slots)do
            if network~=R.noItem then
                local entity=world_module.network_entity(world,network)
                if not entity then return finish('refused','ITEM_UNRESOLVED','slot '..(s-1)..' does not resolve')end
                local kind=world_module.entity_type(world,entity)
                if not accepted[kind]then
                    local names={}
                    for name in pairs(accepted)do names[#names+1]=name end
                    table.sort(names)
                    return finish('refused','ITEM_UNEXPECTED',('slot %d holds entity type %s, not %s'):format(s-1,
                        tostring(kind),table.concat(names,' or ')))
                end
                items[#items+1]=entity
                slots[#slots+1]=s-1
                types[#types+1]=kind
                networks[#networks+1]=network
            end
        end
        if#items==0 then return finish('refused','EMPTY_RACK','the rack holds no item (already taken?)')end
        w.status='complete'
        log(('CAPTURED (%s): pod %d -> rack %d (type %d): %d item%s %s in slots %s, entity type%s %s, read %.1f s after '
            ..'the activation'):format(tostring(spec.label),w.pod,pod.content_entity,rack.type,#items,#items==1 and''or's',
            table.concat(items,', '),table.concat(slots,', '),#types==1 and''or's',table.concat(types,', '),w.seconds))
        -- Network ids are the same on every machine (entity ids are not): pod, rack and items, for multiplayer logs.
        emit({kind='captured',pod=w.pod,rack=pod.content_entity,items=items,types=types,slots=slots,seconds=w.seconds,
            networks=networks,pod_network=pod.network,rack_network=world_module.entity_network(world,pod.content_entity)})
        emit({kind='ended'})
    end
    function w.cancel()if w.status=='active'then w.status='cancelled'end end
    scheduler.attach(w)
    return w
end
function M.reset_for_tests()proven={}end
return M
