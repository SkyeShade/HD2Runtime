local hd2=require('mods/skyeshade/hd2runtime')
-- BeaconProbe 0.1.0: READ-ONLY (research/docs/beacon-redirect-F5FEE03DCFDB.md). Development only. Writes nothing.
-- Every Runtime update it reads the game's stratagem beacons (research/arbitrary-carrier-F5FEE03DCFDB.json):
--   the beacon component manager = [game+0x346BF98] + 0x40 (systems) + 0x1380 (pinned: 0xFDAF4B, 0x5712FB);
--   +0x34 the instance count, +0x38 the count with state, +0x60 entity handles, +0x68 state (0x8E8 each, +0x8E4
--   activated), +0x78 elements (0x40 each: +0x0 countdown, +0x4 threshold, +0xC STRATAGEM TYPE, +0x10 position, +0x1C
--   drop position, +0x28, +0x3C flag).
-- It logs each beacon's creation, every change of its type, its activation and its removal, with the Runtime update
-- frames and the game time between them: the window a per-call redirect would have. Also, read-only: the call-in
-- table, the bombardment manager's instances and private copies (does a vanilla barrage get its own record?), and every
-- player's mission stratagem record (what a deterministic carrier choice could read). Nothing is written: no
-- transaction, no guarded write, no native call.
local mod=hd2.mod()
local BUILD='0.1.0 READ-ONLY BEACON PROBE'
mod:log('BeaconProbe '..BUILD..' (writes nothing): in a mission, throw stratagems and watch for "BEACON CREATED", '
    ..'"BEACON ACTIVATED" (with "window: N Runtime updates") and "BEACON SUMMARY". Please throw, one at a time and '
    ..'waiting for each to land: an Eagle Strafing Run, an Orbital 120mm HE Barrage (or another barrage), an Orbital '
    ..'Precision Strike, a sentry or emplacement, a support weapon or backpack; then any others you can. Ctrl+F11: the '
    ..'live beacons, the call-in table, the bombardment manager and every player\'s record; the per-type window table.')

local world_module=require('hd2runtime/runtime/event_world')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local scheduler=require('hd2runtime/runtime/scheduler')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local SD=require('hd2runtime/domains/stratagem_slots')
local PD=require('hd2runtime/domains/bombardment_payload')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')

local DLL='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
local SYSTEMS,BEACONS=0x40,0x1380
local MG={count=0x34,active=0x38,mapCap=0x50,entities=0x60,state=0x68,elements=0x78}
local EL={stride=0x40,countdown=0x0,threshold=0x4,type=0xC,position=0x10,drop=0x1C,field28=0x28,flag=0x3C}
local ST={stride=0x8E8,activated=0x8E4,mode=0x8E0}
local CI,R=SD.callIns,SD.record
local BM={instances=0x1C,copies=0xA8,copyArray=0xB0,copySize=192}
-- The marker component (its colour comes from the type's row category +0xB8: 0 offensive/red, 2 supply/blue, else
-- yellow; 0x13D1557): an entity map and 0x2C-byte elements with the stratagem type at +0x28.
local MK={global=0x3326A58,keys=0x28,cap=0x30,empty=0x34,mult=0x38,elements=0x50,stride=0x2C,type=0x28}
local CATEGORY={[0]='offensive (red)',[1]='category 1',[2]='supply (blue)',[3]='defensive',[4]='mission'}
-- The code this probe's offsets come from (research/arbitrary-carrier-F5FEE03DCFDB.json); any change refuses.
local PINS={
    {rva=0xFDAF4B,hex='488d4f40',label='systems = world + 0x40'},
    {rva=0x5712FB,hex='488d8f80130000',label='beacon manager = systems + 0x1380'},
    {rva=0x571305,hex='e8d6a01300',label='the beacon update every frame'},
    {rva=0x6AB42C,hex='8b4634',label='the instance count +0x34'},
    {rva=0x6AB490,hex='488b4678',label='the elements +0x78'},
    {rva=0x6AB812,hex='837e3800',label='the count with state +0x38'},
    {rva=0x6AB830,hex='4c8b6678',label='the elements, activation loop'},
    {rva=0x6AB837,hex='4d69efe8080000',label='the state stride 0x8E8'},
    {rva=0x6AB842,hex='4c036e68',label='the state +0x68'},
    {rva=0x6AB84A,hex='418b443c0c',label='each beacon\'s type +0xC'},
    {rva=0x6ABB58,hex='f3410f10043c',label='the countdown +0x0'},
    {rva=0x6ABB5E,hex='f3410f104c3c04',label='the threshold +0x4'},
    {rva=0x6ABB77,hex='4180bde408000000',label='activated +0x8E4'},
    {rva=0x6ABB8D,hex='41c685e408000001',label='activated once'},
    {rva=0x6ABC14,hex='418b4c3c0c',label='the type passed at activation'},
    {rva=0x6ABC72,hex='e839010000',label='the spawn dispatcher'},
    {rva=0x6AE910,hex='89440f0c',label='beacon init: the type stored'},
    {rva=0x6AE829,hex='448b4e50',label='the entity map capacity +0x50'},
    {rva=0x13D1389,hex='4c8b05c856f501',label='the marker component [game+0x3326A58]'},
    {rva=0x13D1393,hex='458b4830',label='its entity map capacity +0x30'},
    {rva=0x13D1397,hex='458b5038',label='its hash multiplier +0x38'},
    {rva=0x13D13AC,hex='4d8b5828',label='its entity map +0x28'},
    {rva=0x13D13B0,hex='418b7834',label='its empty key +0x34'},
    {rva=0x13D14AB,hex='486bc82c',label='its elements, 0x2C each'},
    {rva=0x13D14AF,hex='498b4050',label='its elements +0x50'},
    {rva=0x13D14B3,hex='8b5c0128',label='its stratagem type +0x28'},
    {rva=0x13D1557,hex='8b87b8000000',label='the marker colour from the row category +0xB8'},
}

local names_by_id={}
for name,entry in pairs(catalog.stratagems)do if entry.root then names_by_id[entry.root.id]=name end end
local function type_name(world,kind)
    if kind==0 then return'type 0 (the empty default row)'end
    local id=loadout.id_of(world,kind)
    return ('%s (type %d)'):format(names_by_id[id]or('uncatalogued, stable id '..tostring(id)),kind)
end
local function f32(bytes,o)local ok,v=pcall(b.value,bytes,o,'f32');return ok and v or 0/0 end
local function vec(bytes,o)return('(%.1f, %.1f, %.1f)'):format(f32(bytes,o),f32(bytes,o+4),f32(bytes,o+8))end
local function u64(bytes,o)return b.u32(bytes,o)+b.u32(bytes,o+4)*4294967296 end
local function n2(v)return('%.3f'):format(v)end

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
            mod:log(('REFUSED: the beacon code changed (%s at game+%X); nothing is read'):format(pin.label,pin.rva))
            return false
        end
    end
    proven=true
    mod:log('pins: the beacon manager path and its readers are the researched code ('..#PINS..' pins)')
    return true
end
local function clock(world)
    local object=world.view.pointer(world.game+PD.clock.global)
    local raw=object and world.view.read(object+PD.clock.time,8)
    return raw and u64(raw,0)
end
-- The beacon manager: {address, count, active, entities, state, elements}, or nil and why.
local function manager(world)
    local w=world.view.pointer(world.game+PD.component.global)
    local address=w and w+SYSTEMS+BEACONS
    local raw=address and world.view.read(address,0x80)
    if not raw then return nil,'the beacon manager is unreadable'end
    local count,active,cap=b.u32(raw,MG.count),b.u32(raw,MG.active),b.u32(raw,MG.mapCap)
    if count>4096 or active>4096 or cap==0 or cap>65536 or cap%2~=0 and cap~=1 then
        return nil,('the beacon manager is implausible (count %d, active %d, map %d)'):format(count,active,cap)
    end
    local ok1,entities=pcall(b.pointer,raw,MG.entities)
    local ok2,state=pcall(b.pointer,raw,MG.state)
    local ok3,elements=pcall(b.pointer,raw,MG.elements)
    if not(ok1 and ok2 and ok3)then return nil,'the beacon arrays are unreadable'end
    return {address=address,count=count,active=active,entities=entities,state=state,elements=elements}
end
-- One beacon instance: {index, entity, raw, type, countdown, threshold, field28, flag, activated (nil: no state yet)}.
local function instance(world,m,i)
    local raw=world.view.read(m.elements+i*EL.stride,EL.stride)
    if not raw then return nil end
    local handle=world.view.pointer(m.entities+i*8)
    local entity=handle and world.view.u32(handle+8)
    local activated,mode
    if i<m.active then
        local flag=world.view.read(m.state+i*ST.stride+ST.activated,1)
        activated=flag and flag:byte()~=0
        mode=world.view.u32(m.state+i*ST.stride+ST.mode)
    end
    return {index=i,entity=entity or('index '..i),raw=raw,type=b.u32(raw,EL.type),countdown=f32(raw,EL.countdown),
        threshold=f32(raw,EL.threshold),field28=b.u32(raw,EL.field28),flag=raw:byte(EL.flag+1),activated=activated,mode=mode}
end
-- The call-in table: {{type, key, slot, done}}.
local function call_ins(world)
    local system=world.view.pointer(world.game+CI.global)
    local count=system and world.view.u32(system+CI.count)
    local entries=system and world.view.pointer(system+CI.entries)
    if not(count and entries)or count>512 then return{}end
    local out={}
    for k=0,count-1 do
        local raw=world.view.read(entries+k*CI.stride,CI.stride)
        if raw then
            out[#out+1]={type=b.u32(raw,8),key=b.hex(raw:sub(CI.key+1,CI.key+8)),slot=b.u32(raw,CI.slot),
                done=raw:byte(CI.done+1)}
        end
    end
    return out
end
local function call_in_text(world,list)
    local parts={}
    for _,c in ipairs(list)do
        parts[#parts+1]=('%s key %s slot %d done %d'):format(type_name(world,c.type),c.key,c.slot,c.done)
    end
    return #parts==0 and'none'or table.concat(parts,'; ')
end
-- Every player's mission stratagem record: {{peer, key, types = {...}, granted = {...}}}.
local function records(world)
    local base=world.view.pointer(world.game+R.global)
    local count=base and world.view.u32(base+R.count)
    if not(base and count and count<=64)then return nil end
    local out={}
    for k=0,count-1 do
        local record=base+k*R.stride
        local peer=world.view.read(record,8)
        local n=world.view.u32(record+R.state+R.entryCount)
        local item={peer=peer and b.hex(peer:reverse())or'?',key=b.hex(world.view.read(record+R.state+R.key,8)or''),
            types={},granted={}}
        for e=0,math.min(n or 0,R.maxEntries)-1 do
            local raw=world.view.read(record+R.state+R.entries+e*R.entryStride,R.entryStride)
            if raw then item.types[#item.types+1]=b.u32(raw,0);item.granted[#item.granted+1]=raw:byte(10)end
        end
        out[#out+1]=item
    end
    return out
end
local function records_text(world)
    local list=records(world)
    if not list then return'unreadable'end
    local lines={}
    for k,r in ipairs(list)do
        local parts={}
        for e,kind in ipairs(r.types)do parts[#parts+1]=type_name(world,kind)..(r.granted[e]==1 and'*'or'')end
        lines[#lines+1]=('record %d peer %s key %s: %s'):format(k-1,r.peer,r.key,table.concat(parts,', '))
    end
    return #list..' record(s) (* granted): '..table.concat(lines,' | ')
end
-- The bombardment manager: instances and private copies (each copy's shell list).
local function bombardment(world)
    local mgr=world.view.pointer(world.game+PD.manager.global)
    if not mgr then return nil end
    local instances,copies=world.view.u32(mgr+BM.instances),world.view.u32(mgr+BM.copies)
    local shells={}
    local array=world.view.pointer(mgr+BM.copyArray)
    for k=0,math.min(copies or 0,16)-1 do
        local raw=array and world.view.read(array+k*BM.copySize+0x40,32)
        local list={}
        for s=0,7 do local v=raw and b.u32(raw,s*4);if v and v~=0 then list[#list+1]=tostring(v)end end
        shells[#shells+1]='['..table.concat(list,',')..']'
    end
    return {instances=instances,copies=copies,shells=shells}
end

-- The marker component's type for an entity (read-only), or nil.
local function marker_type(world,entity)
    if type(entity)~='number'then return nil end
    local mgr=world.view.pointer(world.game+MK.global)
    local raw=mgr and world.view.read(mgr+MK.keys,0x18)
    if not raw then return nil end
    local ok,keys=pcall(b.pointer,raw,0)
    local cap,empty,mult=b.u32(raw,MK.cap-MK.keys),b.u32(raw,MK.empty-MK.keys),b.u32(raw,MK.mult-MK.keys)
    if not(ok and keys and cap>0 and cap<=65536)then return nil end
    local start=world_module.mul32(entity,mult)
    for probe=0,cap-1 do
        local slot=world.view.read(keys+((start+probe)%cap)*8,8)
        if not slot then return nil end
        local key=b.u32(slot,0)
        if key==entity then
            local elements=world.view.pointer(mgr+MK.elements)
            return elements and world.view.u32(elements+b.u32(slot,4)*MK.stride+MK.type)
        end
        if key==empty then return nil end
    end
end
local function category(world,kind)
    local row=kind and kind>0 and kind<150 and world.view.pointer(world.game+profile.stratagem.table_rva+kind*8)
    local c=row and world.view.u32(row+0xB8)
    return c and(CATEGORY[c]or('category '..c))or'?'
end
local function marker_text(world,it)
    local kind=marker_type(world,it.entity)
    return kind and('marker component type %s (%s), %s the beacon type'):format(type_name(world,kind),category(world,kind),
        kind==it.type and'SAME AS'or'DIFFERENT FROM')or'no marker component on this entity'
end

------------------------------------------------------------------------------------------------ watching --
local frame=0
local tracked={}        -- [entity] = beacon history
local by_type={}        -- [type] = {n, min, max, sum, seconds}
local last_ci,last_bomb,mission_seen
local function window_note(h)
    if h.window==0 then return'0 Runtime updates: NO update saw it before activation (the current blocker for this type)'end
    return h.window..' Runtime update'..(h.window==1 and''or's')..' saw it before activation'
end
local function summary(world,h,why)
    local window=h.window or 0
    local seconds=h.activated_clock and h.first_clock and(h.activated_clock-h.first_clock)/1e6
    mod:log(('BEACON SUMMARY: %s, entity %s: first seen frame %d; %s; activated %s; type %s; %s; %s'):format(
        type_name(world,h.type),tostring(h.entity),h.first,h.activated_frame and('at frame '..h.activated_frame..', '
        ..(h.activated_frame-h.first)..' updates and '..(seconds and n2(seconds)..' s'or'? s')..' after first seen')
        or'NOT seen activated',h.activated_frame and window_note(h)or('seen for '..window..' updates'),
        h.type_changes==0 and'UNCHANGED throughout'or('CHANGED '..h.type_changes..' time(s)'),
        ('countdown first seen %s, threshold %s'):format(n2(h.countdown0),n2(h.threshold0)),why))
    if h.activated_frame then
        local t=by_type[h.type]or{n=0,min=math.huge,max=-1,sum=0}
        t.n,t.sum=t.n+1,t.sum+window
        t.min,t.max=math.min(t.min,window),math.max(t.max,window)
        by_type[h.type]=t
    end
end
local function tick_beacons(world)
    local m,why=manager(world)
    if not m then
        if not tracked.__said then tracked.__said=true;mod:log('beacon manager: '..tostring(why))end
        return
    end
    local now=clock(world)
    local seen={}
    for i=0,m.count-1 do
        local it=instance(world,m,i)
        if it then
            seen[it.entity]=true
            local h=tracked[it.entity]
            if not h then
                h={entity=it.entity,first=frame,first_clock=now,type=it.type,type_changes=0,countdown0=it.countdown,
                    threshold0=it.threshold,window=0,last_countdown=it.countdown}
                tracked[it.entity]=h
                mod:log(('BEACON CREATED: %s, entity %s, index %d of %d (with state: %d), frame %d, game time %s: countdown '
                    ..'%s, threshold %s, position %s, drop position %s, +0x28 = %d, flag +0x3C = %d, activated %s, state mode +0x8E0 = %s; element '
                    ..'%s; manager 0x%X; category %s; %s; call-ins: %s'):format(type_name(world,it.type),tostring(it.entity),i,m.count,
                    m.active,frame,tostring(now),n2(it.countdown),n2(it.threshold),vec(it.raw,EL.position),
                    vec(it.raw,EL.drop),it.field28,it.flag,tostring(it.activated),tostring(it.mode),b.hex(it.raw),m.address,
                    category(world,it.type),marker_text(world,it),call_in_text(world,call_ins(world))))
            end
            if it.type~=h.type then
                h.type_changes=h.type_changes+1
                mod:log(('BEACON TYPE CHANGED (by the game): entity %s: %s -> %s at frame %d'):format(tostring(it.entity),
                    type_name(world,h.type),type_name(world,it.type),frame))
                h.type=it.type
            end
            if it.activated and not h.activated_frame then
                h.activated_frame,h.activated_clock=frame,now
                mod:log(('BEACON ACTIVATED: %s, entity %s at frame %d, game time %s: %d updates after first seen; window: '
                    ..'%s; countdown now %s (last seen before activation %s), threshold %s; type at activation %s; %s; '
                    ..'element %s'):format(type_name(world,it.type),tostring(it.entity),frame,tostring(now),
                    frame-h.first,window_note(h),n2(it.countdown),n2(h.last_countdown),n2(it.threshold),
                    type_name(world,it.type),marker_text(world,it),b.hex(it.raw)))
            elseif not it.activated and not h.activated_frame then
                h.window=h.window+1
                -- A sparse countdown trace: the first three updates, then every 15th.
                if h.window<=3 or h.window%15==0 then
                    mod:log(('BEACON TRACE: entity %s update %d: countdown %s, threshold %s, state %s, flag %d'):format(
                        tostring(it.entity),h.window,n2(it.countdown),n2(it.threshold),it.activated==nil and'none yet'
                        or('present, mode '..tostring(it.mode)),it.flag))
                end
            end
            h.last_countdown=it.countdown
        end
    end
    for entity,h in pairs(tracked)do
        if entity~='__said'and not seen[entity]then
            tracked[entity]=nil
            summary(world,h,'GONE at frame '..frame..' ('..(frame-h.first)..' updates after first seen)')
        end
    end
end
local function tick_others(world)
    local list=call_ins(world)
    local text=call_in_text(world,list)
    if text~=last_ci then
        last_ci=text
        mod:log(('CALL-INS (frame %d): %s'):format(frame,text))
    end
    local bomb=bombardment(world)
    local btext=bomb and('instances %s, private copies %s %s'):format(tostring(bomb.instances),tostring(bomb.copies),
        table.concat(bomb.shells,' '))
    if btext and btext~=last_bomb then
        last_bomb=btext
        mod:log(('BOMBARDMENT (frame %d): %s'):format(frame,btext))
    end
end

local watch={status='active'}
function watch.cancel()watch.status='cancelled'end
function watch.tick()
    frame=frame+1
    local world=world_module.open()
    if not world or not prove(world)then
        if proven==false then watch.status='complete'end
        return
    end
    local state=world_module.game_state(world)
    local mission=state and state.mission
    if mission and not mission_seen then
        mission_seen=true
        mod:log(('MISSION START (frame %d): host %s; %s'):format(frame,tostring(state.host),records_text(world)))
    elseif not mission and mission_seen then
        mission_seen=false
        mod:log('MISSION END (frame '..frame..')')
    end
    tick_beacons(world)
    tick_others(world)
end
scheduler.attach(watch)

hd2.input.bind('beacon_probe.status',{key='Ctrl+F11',on_press=function()
    local world=world_module.open()
    if not world then return end
    local m,why=manager(world)
    local parts={}
    if m then
        for i=0,m.count-1 do
            local it=instance(world,m,i)
            if it then
                parts[#parts+1]=('%d: %s entity %s countdown %s threshold %s activated %s'):format(i,
                    type_name(world,it.type),tostring(it.entity),n2(it.countdown),n2(it.threshold),tostring(it.activated))
            end
        end
    end
    local rows={}
    for kind,t in pairs(by_type)do
        rows[#rows+1]=('%s: %d beacon(s), window min %d max %d mean %.1f updates'):format(type_name(world,kind),t.n,
            t.min,t.max,t.sum/t.n)
    end
    table.sort(rows)
    mod:log(('Ctrl+F11 [%s] frame %d: beacons %s; call-ins: %s; bombardment: %s; %s; WINDOW TABLE: %s'):format(BUILD,frame,
        m and(m.count..' ('..m.active..' with state): '..(#parts>0 and table.concat(parts,'; ')or'none'))or tostring(why),
        call_in_text(world,call_ins(world)),tostring(last_bomb),records_text(world),
        #rows>0 and table.concat(rows,' | ')or'no beacon activated yet'))
end})
mod:log('loaded ('..BUILD..'): reading the beacon manager every Runtime update; Ctrl+F11 status')
