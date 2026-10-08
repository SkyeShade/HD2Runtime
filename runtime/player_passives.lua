-- PER-PLAYER ARMOR PASSIVES (development; the local player's own record; solo; the user's request of 2026-10-08;
-- research/player-attributes-F5FEE03DCFDB.json, domains/player_passives.lua, docs/armor-passives.md). Not exported
-- directly: hd2.passives and hd2.player_passives (api/player_passives.lua) use it.
--
-- The store is the game's customization manager ([game+0x33264F8]): +0x00 the 411 kit pointers (kit +0x1C its passive
-- id), +0x20 the 32 passive objects every player shares, +0x30 the passive id -> object index table (42 ids; 4 and 22-30
-- unused), +0x930 the entity -> record map, +0x96C the APPLIED records (0x44 each, at most 4 players): +0x04 helmet kit,
-- +0x0C armor kit, +0x38 the HELMET passive, +0x3C the ARMOR passive. EntityAttribute (0x11D9DF0), the only reader of
-- the slots, maps an avatar to its player entity, finds the record and returns the FIRST modifier row {key, type,
-- value, text} with the key, searching the armor passive (flags bit 0) then the helmet passive (bit 1); the caller keeps
-- its default when there is none. No vanilla helmet has a passive, so +0x38 is always 0: a passive put there ADDS the
-- keys the armor passive lacks for every flags=3 reader (an overlapping key: the armor's row wins, never stacked).
--
-- The only writer of the slots is 0x874520: when a new kit's package is ready it copies the pending kits into the
-- applied record and sets +0x38 / +0x3C = the kits' +0x1C. So a Runtime value stays until that player's armor or helmet
-- kit changes, and is then re-derived: the watch here re-applies it (each re-application is logged) and stop() puts the
-- derived values back while the slots still hold the Runtime's.
--
-- Every write is ONE guarded 4-byte write per slot on the local player's applied record, in one transaction whose
-- contexts are the manager pointer, the entity map entry, the record descriptor, the record and the kit rows read this
-- update (the exact bytes, private read-write target memory, read back), after the research's 59 pins proved and the
-- identity held: the map entry names the local player's entity, the descriptor carries it, the record's armor kit is
-- the kit row read, and each slot holds exactly its derived value (kit +0x1C) or the value this handle last wrote for
-- the same kits.
--
-- EFFECT PACKAGES (research/passive-effects-F5FEE03DCFDB.json, section 2). Passive +0x30 is a 32-bit key the game
-- resolves (0x12689C0) to a package: 17 INTEGRATED EXPLOSIVES -> 0xC76C97B3DFB67C5C (the death explosion's particles,
-- materials and sound), 19 ADRENO-DEFIBRILLATOR -> 0x1EEE5C22038560E5 (a sound bank). The game's own 0x874D80 requests
-- it the frame after a slot changes, never waits for it and loads it on the local peer only, so a death inside the load
-- window would fire the effect with nothing resident. A hold naming such a passive (either slot) therefore first opens
-- a core/assets gate on the generated catalogue entry 'passive/<id>' (domains/package_residency.lua, from the same
-- research) with shared = true (runtime/asset_sync.lua publishes it to the lobby's compatible Runtimes), status
-- 'waiting_for_assets' until the engine reports it resident, and writes only then; a failed gate refuses the hold
-- (ASSET_UNAVAILABLE) with nothing written. core/assets keeps its reference for the session; 0x874D80's own paired
-- request / release stays as it is. Every later write of such a passive re-checks the Runtime's reference and residency
-- (else PACKAGE_NOT_RESIDENT: suspended).
--
-- Scope: SOLO (several players: NOT_SOLO; a running override is suspended and restored): the applied record is per
-- peer, built from replicated kits, and which peer evaluates each effect is not proven. NOT LIVE-TESTED.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local natives=require('hd2runtime/domains/event_natives')
local core_assets=require('hd2runtime/core/assets')
local D=require('hd2runtime/domains/player_passives')
local M={}
M.ASSET_ID='player-passives'  -- the core/assets gate (and synced-asset holder) of the effect packages
local MG,R,K,P,MO=D.manager,D.record,D.kit,D.passive,D.modifier
M.EVERY=0.25              -- seconds between two looks at the record while a handle is held
M.MAX_MODIFIERS=16
M.MAX_KITS=2048
M.KIT_RESCAN=5            -- seconds before an unknown kit id makes the kit table be read again
local SLOTS={{name='armor',offset=R.armorPassive,kit=R.armorKit},{name='second',offset=R.helmetPassive,kit=R.helmetKit}}
M.SLOTS=SLOTS

local by_id,by_name={},{}
for _,p in ipairs(D.passives)do by_id[p.id]=p;by_name[p.name:lower()]=p end
M.by_id=by_id
local kit_by_id={}            -- '0x1F9BFA78' -> the research's kit (domains/player_passives.lua kits)
for _,k in ipairs(D.kits)do kit_by_id[k.id]=k end
M.kit_by_id=kit_by_id

local current               -- the one held override: {owner, want = {armor, second}, written, kits, status, ...}
local watch
local clock,next_look=0,0
local kit_cache={}

local function log(text)log_module.emit('[HD2Runtime] passives '..text)end
local function hex32(n)return n and string.format('0x%08X',n)or'?'end
local function round(v)return math.floor(v*1e6+0.5)/1e6 end
local function u64(n)return b.encode(n%4294967296,'u32')..b.encode(math.floor(n/4294967296),'u32')end
-- Seconds on the precise clock (else CPU seconds): only paces the kit table's re-reads.
local function seconds()return metrics.now()or os.clock()end
-- A user-space pointer from bytes, or nil (never raises on garbage).
local function pointer_at(raw,o)
    local lo,hi=b.u32(raw,o),b.u32(raw,o+4)
    if hi>0x7FFF then return nil end
    local v=lo+hi*4294967296
    return v>=65536 and v or nil
end
-- A row's f32 value, or nil when it is not finite.
local function f32(raw,o)
    if math.floor(b.u32(raw,o)/8388608)%256==255 then return nil end
    return round(b.value(raw,o,'f32'))
end
function M.name_of(id)
    local p=by_id[id]
    return p and p.name or('passive '..tostring(id))
end
local function label(id)return ('%s (%s)'):format(M.name_of(id),tostring(id))end

-- The research's pins, proven once per loaded game.dll. true, or nil and the first mismatch.
function M.prove(world)
    if world.player_passives_proven then return true end
    if D.source.gameDllSha256~=natives.source.gameDllSha256 then
        return nil,'the player attributes research covers another game.dll build'
    end
    for _,pin in ipairs(D.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,('native passive code changed (%s at game+%X)'):format(pin.label,pin.rva)
        end
    end
    world.player_passives_proven=true
    return true
end

-- The world, proven, or nil, code, reason.
local function open()
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE','the game is not readable: '..tostring(why)end
    local ok,reason=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',reason end
    return world
end
M.open=open

-- A memory region's owner for a guarded transaction: the target (writable) must be private read-write.
local function owner_of(world,address,size,writable)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and address>=r.base and address+size<=r.base+r.size)then return nil end
    if writable and not(r.type==0x20000 and r.protect==4)then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=r.type,protect=r.protect}
end

-- The manager {address, kits, kit_count, passives, passive_count, index = {[id] = i}, records}, or nil, why.
local function manager(world)
    local global=world.game+MG.globalRva
    local address=world.view.pointer(global)
    if not address then return nil,'the customization manager is not created yet'end
    local head=world.view.read(address,0x30)
    local index=world.view.read(address+MG.passiveIndex,MG.passiveIds*4)
    local records=world.view.u32(address+MG.recordCount)
    if not(head and index and records)then return nil,'the customization manager is unreadable'end
    local m={address=address,global=global,kits=pointer_at(head,MG.kits),kit_count=b.u32(head,MG.kitCount),
        passives=pointer_at(head,MG.passives),passive_count=b.u32(head,MG.passiveCount),records=records,index={}}
    if not(m.kits and m.passives)then return nil,'the customization manager has no kit or passive table yet'end
    if m.kit_count==0 or m.kit_count>M.MAX_KITS or m.passive_count==0
            or m.passive_count>MG.passiveIds or records>MG.capacity then
        return nil,('the customization manager is not the reviewed one (%d kits, %d passives, %d records)'):format(
            m.kit_count,m.passive_count,records)
    end
    for id=0,MG.passiveIds-1 do
        local v=b.u32(index,id*4)
        if v<m.passive_count then m.index[id]=v end
    end
    return m
end
M.manager=manager

-- A passive object as the game holds it: {id, address, package, modifiers = {{key, key_name, type, value}}}, or nil.
function M.passive(world,m,id)
    local i=m.index[id]
    if i==nil then return nil end
    local address=world.view.pointer(m.passives+i*8)
    local raw=address and world.view.read(address,P.read)
    if not raw or b.u32(raw,P.id)~=id then return nil end
    local count=b.u32(raw,P.count)
    if b.u32(raw,P.count+4)~=0 or count>M.MAX_MODIFIERS then return nil end
    local out={id=id,address=address,package=b.u32(raw,P.package),modifiers={}}
    if count==0 then return out end
    local list=world.view.pointer(address+P.modifiers)
    local rows=list and world.view.read(list,count*MO.stride)
    if not rows then return nil end
    for k=0,count-1 do
        local o=k*MO.stride
        local key=string.format('%08X',b.u32(rows,o+MO.key))
        local info=D.keys[key]
        out.modifiers[k+1]={key=key,key_name=key=='00000000'and'none'or(info and info.name or'unknown_'..key:lower()),
            type=D.types[b.u32(rows,o+MO.type)+1]or('type '..b.u32(rows,o+MO.type)),
            value=f32(rows,o+MO.value)}
    end
    return out
end

-- A kit row {id, address, passive, type, bytes} by kit id, through the kit pointer array (cached per array; every use
-- re-reads the row and checks its id).
local function kit(world,m,id)
    if not id or id==0 then return nil end
    local key=tostring(world.key)..':'..tostring(m.kits)..':'..m.kit_count
    local cache=kit_cache[key]
    local function row(address)
        local raw=address and world.view.read(address,K.read)
        if raw and b.u32(raw,K.id)==id then
            return {id=id,address=address,passive=b.u32(raw,K.passive),type=b.u32(raw,K.type),bytes=raw}
        end
    end
    if cache and cache.rows[id]then
        local found=row(cache.rows[id])
        if found then return found end
    elseif cache and seconds()-cache.built<M.KIT_RESCAN then
        return nil      -- not in the table read moments ago: an unknown kit (the table is static)
    end
    local pointers=world.view.read(m.kits,m.kit_count*8)
    if not pointers then return nil end
    cache={rows={},built=seconds()}
    kit_cache={[key]=cache}
    for i=0,m.kit_count-1 do
        local address=pointer_at(pointers,i*8)
        local kid=address and world.view.u32(address+K.id)
        if kid then cache.rows[kid]=address end
    end
    return cache.rows[id]and row(cache.rows[id])or nil
end

-- The local player's applied record, read this update: {world, manager, entity, index, address, bytes, map_entry,
-- descriptor, kits = {armor, helmet} (rows; helmet may be nil), derived = {armor, second}, slots = {armor, second},
-- players}, or nil, code, reason.
function M.read_local(world)
    local m,why=manager(world)
    if not m then return nil,'UNAVAILABLE',why end
    local players=world_module.players(world)
    local me
    for _,p in ipairs(players)do if p['local']then me=p end end
    if not(me and me.entity)then return nil,'NO_PLAYER','the local player is not in the player list'end
    local entity=me.entity
    local map=world.view.read(m.address+MG.map,20)
    if not map then return nil,'UNAVAILABLE','the entity map is unreadable'end
    local slots,capacity,empty,multiplier=pointer_at(map,0),b.u32(map,8),b.u32(map,12),b.u32(map,16)
    if not slots or capacity==0 or capacity>64 or capacity%2~=0 then
        return nil,'UNAVAILABLE','the entity map is not the reviewed one'
    end
    local entries=world.view.read(slots,capacity*8)
    if not entries then return nil,'UNAVAILABLE','the entity map is unreadable'end
    local start,index,entry=world_module.mul32(entity,multiplier)
    for probe=0,capacity-1 do
        local at=((start+probe)%capacity)*8
        local k=b.u32(entries,at)
        if k==entity then index,entry=b.u32(entries,at+4),slots+at;break end
        if k==empty then break end
    end
    if not index then return nil,'NO_RECORD','the local player (entity '..entity..') has no customization record yet'end
    if index>=m.records or index>=MG.capacity then
        return nil,'UNEXPECTED_STATE',('the entity map names record %d of %d'):format(index,m.records)
    end
    local descriptor=world.view.pointer(m.address+MG.descriptors+index*8)
    if not(descriptor and world.view.u32(descriptor+MG.descriptorEntity)==entity)then
        return nil,'UNEXPECTED_STATE','record '..index..' does not carry the local player\'s entity'
    end
    local address=m.address+MG.applied+index*MG.appliedStride
    local bytes=world.view.read(address,MG.appliedStride)
    if not bytes then return nil,'UNAVAILABLE','the applied record is unreadable'end
    local armor_kit=b.u32(bytes,R.armorKit)
    local armor=kit(world,m,armor_kit)
    if not(armor and armor.type==0)then
        return nil,'NOT_READY',('the armor kit %s is not in the kit table yet'):format(hex32(armor_kit))
    end
    local helmet_id=b.u32(bytes,R.helmetKit)
    local helmet=kit(world,m,helmet_id)
    if helmet and helmet.type~=1 then helmet=nil end
    return {world=world,manager=m,entity=entity,index=index,address=address,bytes=bytes,map_entry=entry,
        descriptor=descriptor,players=#players,
        kits={armor=armor,helmet=helmet,armor_id=armor_kit,helmet_id=helmet_id,cape_id=b.u32(bytes,R.capeKit)},
        derived={armor=armor.passive,second=helmet and helmet.passive or 0},
        slots={armor=b.u32(bytes,R.armorPassive),second=b.u32(bytes,R.helmetPassive)}}
end

-- The core/assets dependencies of the effect packages the passives of `want` ({armor, second}) carry, in slot order
-- (distinct), or nil and why (a catalogue without the entry: never guessed).
function M.dependencies(want)
    local out,seen={},{}
    for _,slot in ipairs(SLOTS)do
        local p=want[slot.name]and by_id[want[slot.name]]
        local info=p and p.packageInfo
        if info and not seen[info.dependency]then
            seen[info.dependency]=true
            local dependency=core_assets.dependency(info.dependency)
            if not dependency then return nil,'the asset catalogue has no entry '..info.dependency end
            out[#out+1]=dependency
        end
    end
    return out
end
-- Whether a passive's effect package (if any) is held by the Runtime and resident now.
local function package_ready(world,id)
    local info=by_id[id]and by_id[id].packageInfo
    if not info then return true end
    if not core_assets.held(info.package)then return false end
    local ok,state=pcall(core_assets.state,world.runtime,info.package)
    return ok and state=='resident'
end

-- The modifiers the game reads for flags=3, in its order: the armor passive's rows, then the second (helmet) passive's
-- rows whose key the armor passive lacks; the first row per key (key 00000000 is no effect).
local function effective(world,m,armor,second)
    local out,seen={},{['00000000']=true}
    for _,slot in ipairs({{'armor',armor},{'second',second}})do
        local p=slot[2]~=0 and M.passive(world,m,slot[2])
        for _,row in ipairs(p and p.modifiers or{})do
            if not seen[row.key]then
                seen[row.key]=true
                out[#out+1]={key=row.key,key_name=row.key_name,type=row.type,value=row.value,source=slot[1],
                    passive=slot[2],name=M.name_of(slot[2])}
            end
        end
    end
    return out
end
M.effective=effective

-- A worn kit: its id, the kit table's index, game name, slot and weight (research/armor-names-F5FEE03DCFDB.json), and
-- its passive as read now (kit +0x1C; nil without a kit row).
local function kit_view(id,row)
    local k=kit_by_id[hex32(id)]
    return {id=hex32(id),index=k and k.index,name=k and k.name,slot=k and k.slot,weight=k and k.weight,
        passive=row and row.passive or nil}
end
-- The local player's passives: {entity, record, armor_kit, helmet_kit, cape_kit, armor_passive, helmet_passive,
-- derived, overridden, effective}, or nil, code, reason.
function M.observe()
    local world,code,why=open()
    if not world then return nil,code,why end
    local s,scode,swhy=M.read_local(world)
    if not s then return nil,scode,swhy end
    local function passive_view(id)return {id=id,name=M.name_of(id)}end
    return {entity=s.entity,record=s.index,armor_kit=kit_view(s.kits.armor_id,s.kits.armor),
        helmet_kit=kit_view(s.kits.helmet_id,s.kits.helmet),cape_kit=kit_view(s.kits.cape_id),
        armor_passive=passive_view(s.slots.armor),helmet_passive=passive_view(s.slots.second),
        derived={armor=s.derived.armor,second=s.derived.second},
        overridden=s.slots.armor~=s.derived.armor or s.slots.second~=s.derived.second,
        runtime=current and current.status=='active'and current.owner or nil,
        effective=effective(world,s.manager,s.slots.armor,s.slots.second)}
end

-- Brings the local record's two slots to `want` ({armor, second}: a passive id, or nil = the derived value). `prior`
-- = {kits = {armor, helmet}, values = {armor, second}}: what this handle last wrote, accepted as the slots' current
-- value while the kits are the same. restore = true: a slot holding something else is left alone (not an error).
-- Returns {status = 'APPLIED' | 'UNCHANGED', writes, values, kits, derived, state} or nil, code, reason.
function M.sync(want,prior,restore)
    local world,code,why=open()
    if not world then return nil,code,why end
    local s,scode,swhy=M.read_local(world)
    if not s then return nil,scode,swhy end
    if s.players>1 and not restore then
        return nil,'NOT_SOLO',s.players..' players: armor passive overrides are solo only (the applied record is per '
            ..'peer; which peer evaluates each effect is not proven)'
    end
    -- A slot is this handle's while its own kit is the one it was written for (0x874520 re-derives each slot from its
    -- kit only).
    local kit_now={armor=s.kits.armor_id,second=s.kits.helmet_id}
    local kit_then=prior and prior.kits and{armor=prior.kits.armor,second=prior.kits.helmet}or{}
    local m=s.manager
    local changes,values,skipped={},{},{}
    local owner=owner_of(world,s.address,MG.appliedStride,true)
    for _,slot in ipairs(SLOTS)do
        local now,derived=s.slots[slot.name],s.derived[slot.name]
        local target=want[slot.name]or derived
        local ours=kit_then[slot.name]==kit_now[slot.name]and prior.values and prior.values[slot.name]or nil
        if now~=derived and now~=ours and now~=target then
            if not restore then
                return nil,'UNEXPECTED_STATE',('the %s slot holds %s, neither the kit\'s %s nor this override\'s value')
                    :format(slot.name,label(now),label(derived))
            end
            skipped[#skipped+1]=slot.name
            target=now
        end
        if target~=derived then
            if not by_id[target]or not M.passive(world,m,target)then
                return nil,'UNKNOWN_PASSIVE','passive '..tostring(target)..' is not in the game\'s passive table'
            end
            local info=by_id[target].packageInfo
            if info and now~=target and not package_ready(world,target)then
                return nil,'PACKAGE_NOT_RESIDENT',('%s carries an effect package (%s, %s) the Runtime does not hold '
                    ..'resident now'):format(label(target),info.dependency,info.package)
            end
        end
        values[slot.name]=target
        if target~=now then
            if not owner then return nil,'NOT_PRIVATE','the applied record is not in private read-write memory'end
            changes[#changes+1]={label=('customization.record%d.%sPassive'):format(s.index,slot.name),owner=owner,
                offset=s.address+slot.offset-owner.base,expected=b.encode(now,'u32'),desired=b.encode(target,'u32'),
                before=b.encode(now,'u32'),already_desired=false,
                identity={component='HelldiverCustomizationManager',component_type='native',
                    record_type='applied customization record',unique_owner=true,owner_count=1},chain={}}
        end
    end
    local result={status='UNCHANGED',writes=0,values=values,derived=s.derived,state=s,skipped=skipped,
        kits={armor=s.kits.armor_id,helmet=s.kits.helmet_id}}
    if#changes==0 then return result end
    local snapshots={{owner=owner,offset=s.address-owner.base,bytes=s.bytes}}
    local function context(address,size,bytes)
        local o=owner_of(world,address,size,false)
        if not o then return false end
        snapshots[#snapshots+1]={owner=o,offset=address-o.base,bytes=bytes or world.view.read(address,size)}
        return snapshots[#snapshots].bytes~=nil
    end
    local entry=b.encode(s.entity,'u32')..b.encode(s.index,'u32')
    if not(context(m.global,8,u64(m.address))and context(s.map_entry,8,entry)
            and context(s.descriptor+MG.descriptorEntity,4,b.encode(s.entity,'u32'))
            and context(s.kits.armor.address,K.read,s.kits.armor.bytes)
            and(not s.kits.helmet or context(s.kits.helmet.address,K.read,s.kits.helmet.bytes)))then
        return nil,'UNAVAILABLE','the identity chain is not readable memory'
    end
    local report=transaction.apply(world.runtime,{snapshots=snapshots,changes=changes})
    metrics.count('player_passives.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local after=world.view.read(s.address,MG.appliedStride)
    local verified=after~=nil
    for _,slot in ipairs(SLOTS)do verified=verified and b.u32(after,slot.offset)==values[slot.name]end
    result.status,result.writes,result.verified='APPLIED',report.writes,verified
    result.non_target=report.non_target_bytes_unchanged==true
    return result
end

local function describe(values,derived)
    return ('armor %s%s, second %s%s'):format(label(values.armor),values.armor==derived.armor and' (the kit\'s)'or'',
        values.second==0 and'none'or label(values.second),
        values.second~=0 and values.second==derived.second and' (the kit\'s)'or'')
end
M.describe=describe

local function settle(state,result)
    state.written={kits=result.kits,values=result.values}
    state.derived=result.derived
end

-- One look at the record for the held override: re-applies after the game re-derived it, suspends with several
-- players or a non-resident package, waits while the record is unavailable.
local function look()
    local state=current
    if not state or state.status=='stopped'or state.status=='refused'or state.status=='lost'
        or state.status=='waiting_for_assets'then return end
    local world=open()
    local s=world and M.read_local(world)
    if not s then return end
    local w=state.written
    local kits_changed=w and(w.kits.armor~=s.kits.armor_id or w.kits.helmet~=s.kits.helmet_id)
    local holds=w and not kits_changed and s.slots.armor==w.values.armor and s.slots.second==w.values.second
    if s.players>1 then
        if state.status=='active'then
            local r,rcode,rwhy=M.sync({},w,true)
            if r then settle(state,r)end
            state.status,state.code='suspended','NOT_SOLO'
            state.reason=s.players..' players: the override is solo only; '..(r and'the kit\'s passives are back'
                or('the kit\'s passives could NOT be restored ('..tostring(rcode)..': '..tostring(rwhy)..')'))
            log(('(%s): SUSPENDED: %s%s'):format(state.owner,state.reason,r and(' ('..describe(r.values,r.derived)..')')
                or''))
        end
        return
    end
    if state.status=='active'and holds then return end
    local result,code,why=M.sync(state.want,w,false)
    if not result then
        if code=='UNEXPECTED_STATE'then
            state.status,state.code,state.reason='lost',code,why
            log(('(%s): LOST: %s; this override no longer writes'):format(state.owner,why))
        elseif code=='PACKAGE_NOT_RESIDENT'or code=='NOT_SOLO'then
            if state.status~='suspended'or state.code~=code then
                state.status,state.code,state.reason='suspended',code,why
                log(('(%s): SUSPENDED: %s: %s'):format(state.owner,code,why))
            end
        elseif state.code~=code then
            state.code,state.reason=code,why
            log(('(%s): waiting: %s: %s'):format(state.owner,code,why))
        end
        return
    end
    local was=state.status
    settle(state,result)
    state.status,state.code,state.reason='active',nil,nil
    if result.status=='APPLIED'then
        state.applications=state.applications+1
        if kits_changed then
            log(('(%s): RE-APPLIED after the kit changed (armor %s -> %s, helmet %s -> %s; the game re-derived armor %s, '
                ..'second %s): %s; %d write%s, read back %s'):format(state.owner,hex32(w.kits.armor),
                hex32(s.kits.armor_id),hex32(w.kits.helmet),hex32(s.kits.helmet_id),label(s.slots.armor),
                label(s.slots.second),describe(result.values,result.derived),result.writes,
                result.writes==1 and''or's',tostring(result.verified)))
        else
            log(('(%s): %s: %s; %d write%s, read back %s'):format(state.owner,was=='active'and'RE-APPLIED'or'APPLIED',
                describe(result.values,result.derived),result.writes,result.writes==1 and''or's',
                tostring(result.verified)))
        end
    elseif was~='active'then
        log(('(%s): active: %s (already in place)'):format(state.owner,describe(result.values,result.derived)))
    end
end
M.look=look

local function package_names(state)
    local out={}
    for _,d in ipairs(state.dependencies)do out[#out+1]=d.key..' '..d.package end
    return table.concat(out,', ')
end
-- One step of a hold waiting for its effect packages: the gate is opened once the game is readable (shared: the
-- packages go to the synced asset set), then polled; resident -> 'waiting' and written at once; failed -> refused.
local function wait_for_assets(state,dt)
    if not state.gate then
        local world=world_module.open()
        if not world then return end
        state.gate=core_assets.gate(world.runtime,{id=M.ASSET_ID,asset_dependencies=state.dependencies,shared=true},
            log_module.emit)
        dt=0
    end
    local result,why=state.gate.tick(dt)
    if result=='failed'then
        state.gate=nil
        state.status,state.code='refused','ASSET_UNAVAILABLE'
        state.reason=tostring(why):gsub('^ASSET_UNAVAILABLE: ','')
        log(('(%s): REFUSED: ASSET_UNAVAILABLE: the effect package (%s) did not load: %s; nothing was written')
            :format(state.owner,package_names(state),state.reason))
    elseif result=='ready'then
        state.gate=nil
        state.status,state.code,state.reason='waiting',nil,nil
        log(('(%s): effect package resident (%s; requested through core/assets, shared with compatible peers): '
            ..'writing'):format(state.owner,package_names(state)))
    end
    return result
end

local function ensure_watch()
    if watch and watch.status=='active'then return end
    watch={status='active',perf_label='player passives'}
    function watch.tick(dt)
        if watch.status~='active'then return end
        clock=clock+(dt or 0)
        if not current or current.status=='stopped'or current.status=='refused'or current.status=='lost'then
            watch.status='complete'
            return
        end
        if current.status=='waiting_for_assets'then
            local ok,why=pcall(wait_for_assets,current,dt or 0)
            if not ok then log('asset wait failed: '..tostring(why))end
            next_look=clock+M.EVERY
            if why=='ready'then
                ok,why=pcall(look)
                if not ok then log('update failed: '..tostring(why))end
            end
            return
        end
        if clock<next_look then return end
        next_look=clock+M.EVERY
        local started=metrics.now()
        local ok,why=pcall(look)
        if not ok then log('update failed: '..tostring(why))end
        metrics.elapsed('player_passives.tick',started)
    end
    function watch.cancel()watch.status='cancelled'end
    scheduler.attach(watch)
end

-- Holds an override. spec = {owner, want = {armor = id|nil, second = id|nil}}, validated by api/player_passives.lua.
-- Applies it now when the record is there; returns the state (status 'active' | 'waiting' | 'waiting_for_assets' |
-- 'refused', code, reason). A passive with an effect package waits for it first (see EFFECT PACKAGES above).
-- Another owner's held override refuses (ALREADY_SET); the same owner's replaces it in place (no restore in between).
function M.hold(spec)
    local prior,prior_status
    if current and current.status~='stopped'and current.status~='refused'and current.status~='lost'then
        if current.owner~=spec.owner then
            return {status='refused',code='ALREADY_SET',reason='the local player\'s passives are overridden by '
                ..current.owner}
        end
        prior,prior_status=current,current.status
        prior.status='replaced'
    end
    local state={owner=spec.owner,want=spec.want,status='waiting',applications=0,written=prior and prior.written,
        derived=prior and prior.derived}
    -- An effect package first: loaded through core/assets (shared) before anything is written.
    local dependencies,dwhy=M.dependencies(spec.want)
    if not dependencies then
        if prior then prior.status=prior_status end
        return {status='refused',code='ASSET_UNAVAILABLE',reason=dwhy}
    end
    if#dependencies>0 then
        state.dependencies,state.status=dependencies,'waiting_for_assets'
        local result=wait_for_assets(state,0)
        if state.status=='refused'then
            if prior then prior.status=prior_status end
            return {status='refused',code=state.code,reason=state.reason}
        end
        if result~='ready'then
            log(('(%s): waiting_for_assets: the effect package (%s) loads first; nothing is written until it is '
                ..'resident'):format(state.owner,package_names(state)))
            current=state
            next_look=clock+M.EVERY
            ensure_watch()
            return state
        end
        state.status='waiting'
    end
    local result,code,why=M.sync(state.want,state.written,false)
    if result then
        settle(state,result)
        state.status='active'
        if result.status=='APPLIED'then state.applications=1 end
        log(('(%s): %s: %s; %d write%s%s; solo only, not live-tested'):format(state.owner,
            result.status=='APPLIED'and'APPLIED'or'active (already in place)',describe(result.values,result.derived),
            result.writes,result.writes==1 and''or's',result.status=='APPLIED'and(', read back '..tostring(result.verified))
            or''))
    elseif code=='UNAVAILABLE'or code=='NO_PLAYER'or code=='NO_RECORD'or code=='NOT_READY'then
        state.code,state.reason=code,why
        log(('(%s): waiting: %s: %s'):format(state.owner,code,why))
    else
        if prior then prior.status=prior_status end
        return {status='refused',code=code,reason=why}
    end
    current=state
    next_look=clock+M.EVERY
    ensure_watch()
    return state
end

-- Stops the held override: the derived values (kit +0x1C) go back into the slots still holding this override's values.
-- Returns true when the slots are the kit's again (or never were written), false and why otherwise.
function M.release(state)
    if not state or state~=current then
        if state and state.status~='refused'then state.status='stopped'end
        return true
    end
    state.status='stopped'
    current=nil
    if not state.written then log(('(%s): stopped (nothing was written)'):format(state.owner))return true end
    local result,code,why=M.sync({},state.written,true)
    if not result then
        log(('(%s): stopped; the kit\'s passives were NOT restored: %s: %s (a kit change re-derives them)'):format(
            state.owner,code,why))
        return false,why
    end
    log(('(%s): stopped: %s restored; %d write%s%s'):format(state.owner,describe(result.values,result.derived),
        result.writes,result.writes==1 and''or's',#result.skipped>0 and('; left alone (not this override\'s value): '
        ..table.concat(result.skipped,', '))or''))
    return true
end
function M.held()return current end
function M.reset_for_tests()
    current=nil
    clock,next_look=0,0
    kit_cache={}
    if watch then watch.status='cancelled'end
    watch=nil
end
return M
