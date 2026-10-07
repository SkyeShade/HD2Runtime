local hd2=require('mods/skyeshade/hd2runtime')
-- PodProbe 0.1.0: READ-ONLY HELLPOD PROBE (research/docs/carrier-families-F5FEE03DCFDB.md, "Support and deployable
-- payloads"). Writes nothing. It observes the first per-call object that selects what a hellpod delivers: the pod's
-- TransportComponent element ([game+0x3326518], 0x40 bytes each at +0x40):
--     +0x0  the content resource hash (a weapon rack, a sentry, ...), copied from the beacon's dispatcher record when
--           the pod is created (0x6D9835/0x6D983C) and read once by the host when the content spawns (0x6D8D6C);
--     +0x8  the spawned content entity (not yet spawned until then);
--     +0xC  the spawn timer: armed at landing (0x92C464, 0.5 s), the content spawns when it crosses zero;
-- and its replicated block (+0x48, 0x18 each: +0 content hash, +8 kind, +0xC type, +0x10 the beacon's network id).
-- For every pod: its content (named from the catalogue's payload lists), its type, the beacon that spawned it, the
-- moment it lands and the moment its content spawns: the per-pod window in which a future per-call content change
-- would have to happen. Throw support weapons, backpacks, sentries, mines and emplacements.
local mod=hd2.mod()
local BUILD='0.1.0 READ-ONLY HELLPOD PROBE'
mod:log('PodProbe '..BUILD..' (writes nothing): in a SOLO mission, throw an AC-8 Autocannon, then (one at a time) a '
    ..'backpack, a Gatling Sentry, a minefield and an emplacement, each to its end. Expect "POD CREATED", "POD LANDED", '
    ..'"POD CONTENT SPAWNED" and "POD SUMMARY" lines. Ctrl+F11: the live pods.')

local world_module=require('hd2runtime/runtime/event_world')
local redirect=require('hd2runtime/runtime/beacon_redirect')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')

local DLL='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
local TR={global=0x3326518,count=0x10,handles=0x38,elements=0x40,stride=0x40,blocks=0x48,blockStride=0x18,
    content=0x0,spawned=0x8,timer=0xC,timer2=0x10,call=0x14,owner=0x18}
local BL={content=0x0,kind=0x8,type=0xC,beacon=0x10}
local PINS={
    {rva=0x6D97A0,hex='488b2d71cdc402',label='the Transport manager [game+0x3326518]'},
    {rva=0x6DA28D,hex='397110',label='the pods: count +0x10'},
    {rva=0x6DA2C0,hex='498b4738',label='their entity handles +0x38'},
    {rva=0x6DA2C6,hex='48c1e306',label='elements 0x40 each ...'},
    {rva=0x6DA2CA,hex='49035f40',label='... at +0x40'},
    {rva=0x6DA2FB,hex='498b4748',label='replicated blocks +0x48 (0x18 each)'},
    {rva=0x6DA31F,hex='488b0cf0',label='an entity handle ...'},
    {rva=0x6DA323,hex='8b4910',label='... its network id +0x10'},
    {rva=0x6D9835,hex='498b8fd8030000',label='creation: the dispatcher record +0x3D8 (the content) ...'},
    {rva=0x6D983C,hex='48890e',label='... into element +0x0'},
    {rva=0x6D8D1A,hex='49390424',label='the spawn: content +0x0 non-zero ...'},
    {rva=0x6D8D2A,hex='4139442408',label='... and +0x8 not yet spawned ...'},
    {rva=0x6D8D6C,hex='498b3c24',label='... the content read'},
    {rva=0x92C464,hex='f30f1144020c',label='landing arms the spawn timer +0xC'},
    {rva=0x6AB897,hex='8b4910',label='a beacon handle: its network id +0x10'},
}

-- Names: stratagem types and payload hashes (each catalogued stratagem's payload list, in name order).
local names_by_id,payload_users,sorted={},{},{}
for name in pairs(catalog.stratagems)do sorted[#sorted+1]=name end
table.sort(sorted)
for _,name in ipairs(sorted)do
    local root=catalog.stratagems[name].root
    if root then
        names_by_id[root.id]=name
        for k,hash in ipairs(root.payloads or{})do
            local key=(hash:upper():gsub('^0X','0x'))
            payload_users[key]=payload_users[key]or{}
            table.insert(payload_users[key],name..' payload '..k)
        end
    end
end
local function payload_name(hash)
    local users=payload_users[hash]
    if not users then return hash..' (no catalogued stratagem lists it)'end
    return ('%s (%s%s)'):format(hash,users[1],#users>1 and(', and '..(#users-1)..' more')or'')
end
local function type_name(world,kind)
    if not kind then return'?'end
    if kind==0 then return'type 0'end
    local id=loadout.id_of(world,kind)
    return ('%s (%d)'):format(id and names_by_id[id]or'uncatalogued',kind)
end
local function n2(v)return v and('%.2f'):format(v)or'?'end
local function f32(bytes,o)local ok,v=pcall(b.value,bytes,o,'f32');return ok and v or nil end

------------------------------------------------------------------------------------------------ reading --
local proven
local function prove(world)
    if proven~=nil then return proven end
    if profile.dll_sha~=DLL then
        proven=false
        mod:log('REFUSED: another game.dll build (the probe\'s offsets are for F5FEE03DCFDB); nothing is read')
        return false
    end
    for _,pin in ipairs(PINS)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            proven=false
            mod:log(('REFUSED: the pod code changed (%s at game+%X); nothing is read'):format(pin.label,pin.rva))
            return false
        end
    end
    proven=true
    mod:log('pins: the Transport component and its readers are the researched code ('..#PINS..' pins)')
    return true
end
-- Every pod now: {[entity] = {index, entity, net, content, spawned, timer, timer2, call, owner, block = {...}}}, count.
local function pods(world)
    local mgr=world.view.pointer(world.game+TR.global)
    if not mgr then return nil end
    local count=world.view.u32(mgr+TR.count)
    if not count or count>4096 then return nil end
    local handles,elements,blocks=world.view.pointer(mgr+TR.handles),world.view.pointer(mgr+TR.elements),
        world.view.pointer(mgr+TR.blocks)
    local out={}
    for i=0,count-1 do
        local handle=handles and world.view.pointer(handles+i*8)
        local raw=elements and world.view.read(elements+i*TR.stride,TR.stride)
        local block=blocks and world.view.read(blocks+i*TR.blockStride,TR.blockStride)
        if handle and raw then
            local entity=world.view.u32(handle+8)
            out[entity or('index '..i)]={index=i,entity=entity,net=world.view.u32(handle+0x10),
                content=b.resource(raw,TR.content),spawned=b.u32(raw,TR.spawned),timer=f32(raw,TR.timer),
                timer2=f32(raw,TR.timer2),call=raw:byte(TR.call+1),owner=b.u32(raw,TR.owner),
                block=block and{content=b.resource(block,BL.content),kind=b.u32(block,BL.kind),type=b.u32(block,BL.type),
                    beacon=b.u32(block,BL.beacon)}}
        end
    end
    return out,count
end
-- The beacons by network id (their handle +0x10): {[net] = {entity, type}}.
local function beacons_by_net(world)
    local out={}
    local m=redirect.manager(world)
    if not m then return out end
    for i=0,m.count-1 do
        local it=redirect.beacon(world,m,i)
        local handle=it and world.view.pointer(it.handle_slot)
        local net=handle and world.view.u32(handle+0x10)
        if net then out[net]={entity=it.entity,type=it.type}end
    end
    return out
end

------------------------------------------------------------------------------------------------ watching --
local clock=0
local tracked={}
local known_beacons={}
local first=true
local function step(world)
    if not prove(world)then return end
    local list=pods(world)
    if not list then return end
    for net,bn in pairs(beacons_by_net(world))do known_beacons[net]=bn end
    for key,p in pairs(list)do
        local t=tracked[key]
        if not t then
            t={first=clock,content=p.content,spawned=p.spawned,baseline=first}
            tracked[key]=t
            if not first then
                local bn=p.block and known_beacons[p.block.beacon]
                mod:log(('POD CREATED: entity %s (network id %s), content %s, type %s, kind %s, call flag %d, owner %d; from '
                    ..'the beacon with network id %s%s; spawn timer %s'):format(tostring(p.entity),tostring(p.net),
                    payload_name(p.content),type_name(world,p.block and p.block.type),tostring(p.block and p.block.kind),
                    p.call,p.owner,tostring(p.block and p.block.beacon),bn and(' (beacon entity '..tostring(bn.entity)
                    ..', its type now '..type_name(world,bn.type)..')')or' (not seen)',n2(p.timer)))
            end
        elseif not t.baseline then
            if p.content~=t.content then
                mod:log(('POD CONTENT CHANGED (by the game): entity %s, %s -> %s, %.2f s after creation'):format(
                    tostring(p.entity),payload_name(t.content),payload_name(p.content),clock-t.first))
                t.content=p.content
            end
            if not t.landed and p.timer and p.timer>=0 then
                t.landed=clock
                mod:log(('POD LANDED: entity %s, %.2f s after creation (spawn timer armed: %s s)'):format(
                    tostring(p.entity),clock-t.first,n2(p.timer)))
            end
            if p.spawned~=t.spawned and not t.content_at then
                t.content_at=clock
                mod:log(('POD CONTENT SPAWNED: entity %s, content entity %d (%s), %.2f s after landing, %.2f s after '
                    ..'creation; replicated kind %s'):format(tostring(p.entity),p.spawned,payload_name(p.content),
                    t.landed and clock-t.landed or-1,clock-t.first,tostring(p.block and p.block.kind)))
            end
        end
    end
    for key,t in pairs(tracked)do
        if not list[key]then
            tracked[key]=nil
            if not t.baseline then
                mod:log(('POD SUMMARY: entity %s, content %s: landed %s s after creation, content spawned %s s after creation; '
                    ..'the window for a per-pod content change: creation -> content spawn = %s s'):format(tostring(key),
                    payload_name(t.content),t.landed and n2(t.landed-t.first)or'never',
                    t.content_at and n2(t.content_at-t.first)or'never',t.content_at and n2(t.content_at-t.first)or'?'))
            end
        end
    end
    first=false
end

hd2.every(0.05,function()
    clock=clock+0.05
    local world=world_module.open()
    if not world then return end
    local state=hd2.game_state()
    if not(state and state.mission)then
        tracked,known_beacons,first={},{},true
        return
    end
    step(world)
end,{id='pod-probe'})

hd2.input.bind('pod_probe.status',{key='Ctrl+F11',on_press=function()
    local world=world_module.open()
    local list,count
    if world and prove(world)then list,count=pods(world)end
    local parts={}
    for _,p in pairs(list or{})do
        parts[#parts+1]=('entity %s content %s type %s spawned %s timer %s'):format(tostring(p.entity),p.content,
            tostring(p.block and p.block.type),tostring(p.spawned),n2(p.timer))
    end
    mod:log(('Ctrl+F11 [%s]: %s pod(s): %s'):format(BUILD,tostring(count),#parts>0 and table.concat(parts,'; ')or'none'))
end})
mod:log('loaded ('..BUILD..'): every hellpod observed; Ctrl+F11 status')
