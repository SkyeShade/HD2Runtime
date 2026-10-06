-- Custom stratagem P0 (docs/custom-stratagems.md): a vanilla stratagem's calldown sequence replaced by a Runtime-owned
-- one. Development infrastructure: not exported by api/hd2.lua, no SDK field (a development proof calls it).
--
-- A StratagemInfo row holds its arrow code as a pointer to u32 directions (+0x40) and their count (+0x48); the calldown
-- matcher and the sequence copy helpers read both from the live row every time (domains/stratagem_calldown.lua,
-- research/stratagem-calldown-F5FEE03DCFDB.json). P0 writes exactly those two members of one row, through the guarded
-- transaction every other Runtime write uses (exact expected bytes, the whole row as its context, protection restored,
-- rollback on failure): +0x48 to the new count and +0x40 to a block the Runtime owns. Nothing else of the row (name,
-- icon, payload, cooldown, timing, category) and no other row is written.
--
-- The HUD's stratagem list copies the row every frame but draws its arrows only when a slot's stratagem type changes,
-- and it fills its slots on the first frame the local player's avatar exists (research: hud). That frame comes about
-- two frames after the mission starts, before even an early write lands (live, 2026-10-01), so the list keeps the
-- original arrows; refresh_hud() redraws the one slot. P0 applies in a mission without waiting for an avatar: nothing
-- in the write depends on it.
--
-- The block is allocated once and kept, with the adapter that owns it, for the life of this Lua state: the game may read
-- it as long as the row points to it. restore() writes the original pointer and count back (pointer first, so the count
-- never exceeds the array it describes), and a finalizer restores them if the Lua state closes while applied.
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local events=require('hd2runtime/runtime/events')
local metrics=require('hd2runtime/runtime/metrics')
local reader_module=require('hd2runtime/runtime/reader')
local b=require('hd2runtime/core/bytes')
local Stratagem=require('hd2runtime/core/stratagem')
local transaction=require('hd2runtime/core/guarded_transaction')
local profile=require('hd2runtime/schemas/current')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local C=require('hd2runtime/domains/stratagem_calldown')
local hud=require('hd2runtime/runtime/stratagem_hud')
local M={}

M.P0={stratagem=C.p0.stratagem,sequence=C.p0.sequence}
M.NAMES={[1]='Up',[2]='Right',[3]='Down',[4]='Left'}
-- u32 entries of the Runtime-owned block: room for the longest native code, the rest zero.
M.CAPACITY=10
local ROW,SEQUENCE,COUNT,PADDING=C.row.stride,C.row.sequence,C.row.count,C.row.padding

-- {stratagem, id, type, row_address, original = {pointer, count, sequence}, custom = {pointer, count, sequence},
-- report, applied, restored, restore_report}; nil before the first apply.
local state
local block                 -- {address, runtime}: the Runtime-owned array and the adapter that keeps it alive
local sentinel              -- a finalizer that restores the row if this Lua state closes while applied

local function log(text)events.emit_log('custom stratagem: '..text)end
local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function u64(n)return u32(n%4294967296)..u32(math.floor(n/4294967296))end

-- The u32 little-endian bytes of a sequence, or nil and the reason. 1..maxLength directions, each 1 (Up) .. 4 (Left).
function M.encode(sequence)
    if type(sequence)~='table'or#sequence<1 or#sequence>C.maxLength then
        return nil,'a sequence has 1 to '..C.maxLength..' directions'
    end
    local parts={}
    for index,value in ipairs(sequence)do
        if type(value)~='number'or value%1~=0 or value<1 or value>4 then
            return nil,'direction '..index..' must be 1 (Up), 2 (Right), 3 (Down) or 4 (Left)'
        end
        parts[index]=u32(value)
    end
    return table.concat(parts)
end
function M.decode(bytes)
    local out={}
    for index=1,#bytes/4 do out[index]=b.u32(bytes,(index-1)*4)end
    return out
end
function M.names(sequence)
    local out={}
    for index,value in ipairs(sequence or{})do out[index]=M.NAMES[value]or tostring(value)end
    return table.concat(out,' ')
end
local function same(a,c)
    if#a~=#c then return false end
    for index=1,#a do if a[index]~=c[index]then return false end end
    return true
end

-- Every calldown reader pin, proven once per loaded game.dll. true, or nil and the first mismatch.
function M.prove(world)
    if world.calldown_proven then return true end
    if C.source.gameDllSha256~=profile.dll_sha then return nil,'the calldown research covers another game.dll build'end
    for _,pin in ipairs(C.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,'native calldown reader changed ('..pin.label..' at game+'..string.format('%X',pin.rva)..')'
        end
    end
    world.calldown_proven=true
    return true
end

-- The live row of a catalogued stratagem (found by its catalogue id and package, never by a type number): {entry,
-- record, owner, reader, row, pointer, count, sequence}. Runs inside a job (the reader paces its reads).
local function resolve(world,name)
    local entry=catalog.stratagems[name]
    if not(entry and entry.root and entry.root.id)then return nil,'UNKNOWN_STRATAGEM','no catalogued stratagem '..tostring(name)end
    local reader=reader_module.new(world.runtime)
    local records,owner=Stratagem.capture_all(world.runtime,reader,profile)
    local record
    for _,item in ipairs(records)do
        if item.id==entry.root.id and item.package==entry.root.package then
            if record then return nil,'STRATAGEM_AMBIGUOUS',name..' resolves to more than one row'end
            record=item
        end
    end
    if not record then return nil,'STRATAGEM_ABSENT',name..' has no StratagemInfo row'end
    local row=reader.read(owner,record.offset,ROW,true)
    if b.u32(row,0)~=record.record_kind or b.u32(row,4)~=entry.root.id or b.u32(row,PADDING)~=0 then
        return nil,'ROW_CHANGED','the '..name..' row no longer carries its identity'
    end
    local pointer,count=b.pointer(row,SEQUENCE),b.u32(row,COUNT)
    if count<1 or count>C.maxLength then return nil,'ROW_CHANGED','the '..name..' sequence count is '..count end
    local bytes
    if pointer>=owner.base+16 and pointer+count*4<=owner.base+owner.size then
        bytes=reader.read(owner,pointer-owner.base,count*4)
    elseif block and pointer==block.address then
        bytes=world.view.read(pointer,count*4)
    end
    if not bytes then
        return nil,'ROW_CHANGED','the '..name..' sequence points outside the settings and outside Runtime'
    end
    return {entry=entry,record=record,owner=owner,reader=reader,row=row,pointer=pointer,count=count,
        sequence=M.decode(bytes)}
end

-- Mission and host: true, or nil and code, reason. No avatar: the row is static settings data, and before the avatar
-- exists no calldown can be in progress and the HUD has not drawn the code yet.
local function authority(world)
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','only in a mission (never aboard the ship)'end
    if game.host~=true then return nil,'HOST_ONLY','only the host (or a solo player) changes a calldown sequence'end
    return true
end

-- Whether the local player's avatar exists now, as the HUD's stratagem list sees it: the player's avatar network id
-- resolves through the network-id map (research: hud.avatarGate). Until it does, the HUD does not fill its slots.
-- {present, id}; present is nil when the local player is not in the player list (or the list is unreadable).
function M.local_avatar(world)
    for _,player in ipairs(world_module.players(world,true))do
        if player['local']then return {present=player.avatar~=nil,id=player.avatar}end
    end
    return {present=nil}
end

-- One guarded transaction on the row: changes = {{label, offset, expected, desired}, ...} in write order.
local function write(world,resolved,changes)
    local owner={base=resolved.owner.base,size=resolved.owner.size,type=resolved.owner.type,
        protect=resolved.owner.protect}
    local plan={snapshots={{owner=owner,offset=resolved.record.offset,bytes=resolved.row}},changes={}}
    for _,item in ipairs(changes)do
        plan.changes[#plan.changes+1]={label=item.label,owner=owner,offset=resolved.record.offset+item.offset,
            expected=item.expected,desired=item.desired,before=item.expected,already_desired=false,
            identity={component='StratagemSettings',record_type='StratagemInfo',record_kind=resolved.record.record_kind,
                group=resolved.record.group,row=resolved.record.row,unique_owner=true,owner_count=1},chain={}}
    end
    local report=transaction.apply(world.runtime,plan)
    metrics.count('custom_stratagem.transactions')
    return report
end

local function finalize()
    -- Best effort when this Lua state closes while applied: the game must not keep a pointer into freed memory.
    if not(state and state.applied and not state.restored)then return end
    local co=coroutine.create(function()
        local restored=M.restore_body()
        -- A slot that draws the custom code draws the original again, through the same guarded redraw (it refuses
        -- and writes nothing when the HUD is gone).
        if restored and state.hud_draws=='custom'then
            local world=world_module.open()
            if world and hud.refresh(world,{type=state.type,row=state.row_address,draw=state.original.sequence,
                    from={state.original.sequence,state.custom.sequence}})then
                state.hud_draws='original'
            end
        end
        return restored
    end)
    for _=1,10000 do
        if coroutine.status(co)=='dead'then break end
        local ok=coroutine.resume(co)
        if not ok then break end
    end
end
-- The Lua-state-close path, for tests: restore, then the HUD slot.
function M.finalize_for_tests()finalize()end
local function arm()
    if sentinel then return end
    local ffi=require('ffi')
    sentinel=ffi.gc(ffi.new('uint8_t[1]'),function()pcall(finalize)end)
end
local function disarm()
    if sentinel then require('ffi').gc(sentinel,nil);sentinel=nil end
end

-- A job: body runs in a coroutine resumed once per update (the reader paces its reads); the result is copied into the
-- job and callback(job) runs once.
local function job(body,callback)
    local handle={status='pending'}
    local co=coroutine.create(body)
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick()
        local ok,result,code,reason=coroutine.resume(co)
        if ok and coroutine.status(co)~='dead'then return end
        watch.status='complete'
        if not ok then
            handle.status,handle.code,handle.reason='failed','CUSTOM_STRATAGEM_FAILED',tostring(result)
        elseif result then
            for key,value in pairs(result)do handle[key]=value end
        else
            handle.status,handle.code,handle.reason='refused',code,reason
        end
        if handle.status=='refused'or handle.status=='failed'then
            log((handle.kind or'job')..' refused: '..tostring(handle.code)..': '..tostring(handle.reason))
        end
        if callback then callback(handle)end
    end
    scheduler.attach(watch)
    return handle
end

-- Applies a Runtime-owned calldown sequence to a catalogued stratagem's row. spec: {stratagem = name, sequence = {...},
-- expected = the native sequence the row must hold (default: the P0 stratagem's researched code)}. Returns a job:
-- 'pending', then 'applied' (or 'refused' / 'failed' with code and reason); callback(job) once it settles.
function M.apply(spec,callback)
    spec=spec or M.P0
    local custom,why=M.encode(spec.sequence)
    local expected=spec.expected or(spec.stratagem==C.p0.stratagem and C.p0.nativeSequence or nil)
    return job(function()
        if not custom then return nil,'INVALID_SEQUENCE',why end
        if not expected then return nil,'INVALID_SEQUENCE','the native sequence of '..tostring(spec.stratagem)..' is not known'end
        if state and state.applied and not state.restored then
            return nil,'ALREADY_APPLIED','a custom sequence is applied to '..state.stratagem..'; restore it first'
        end
        local world,reason=world_module.open()
        if not world then return nil,'CUSTOM_STRATAGEM_UNAVAILABLE',tostring(reason)end
        if not(world.runtime.owned_block and world.runtime.owned_write and world.runtime.write and world.runtime.protect)then
            return nil,'CUSTOM_STRATAGEM_UNAVAILABLE','this Runtime adapter cannot own memory or write'
        end
        local allowed,code
        allowed,code,reason=authority(world)
        if not allowed then return nil,code,reason end
        local proven
        proven,reason=M.prove(world)
        if not proven then return nil,'CUSTOM_STRATAGEM_UNAVAILABLE',reason end
        local resolved
        resolved,code,reason=resolve(world,spec.stratagem)
        if not resolved then return nil,code,reason end
        -- The exact original: the researched native sequence, in the settings allocation.
        if block and resolved.pointer==block.address then
            return nil,'ALREADY_APPLIED','the row already points to the Runtime-owned sequence'
        end
        if not same(resolved.sequence,expected)then
            return nil,'ROW_CHANGED','the '..spec.stratagem..' code is '..M.names(resolved.sequence)..', not the native '
                ..M.names(expected)
        end
        if not block then
            local address=world.runtime.owned_block(M.CAPACITY*4)
            block={address=address,runtime=world.runtime}
        end
        local bytes=custom..string.rep('\0',M.CAPACITY*4-#custom)
        world.runtime.owned_write(block.address,bytes)
        if world.view.read(block.address,#bytes)~=bytes then
            return nil,'CUSTOM_STRATAGEM_UNAVAILABLE','the Runtime-owned sequence did not read back as written'
        end
        -- Count first (shrinking or growing within the larger array), then the pointer.
        local count=#spec.sequence
        local changes={{label='calldown.count',offset=COUNT,expected=u32(resolved.count),desired=u32(count)},
            {label='calldown.sequence',offset=SEQUENCE,expected=u64(resolved.pointer),desired=u64(block.address)}}
        if count>resolved.count then changes={changes[2],changes[1]}end
        local report=write(world,resolved,changes)
        if report.status~='APPLIED'then
            return nil,'GUARD_REJECTED','the guarded write was '..tostring(report.status)..': '..tostring(report.reason)
        end
        -- In the same tick as the write (the transaction does not yield): had the HUD's slots been filled already?
        local avatar=M.local_avatar(world)
        local after=resolve(world,spec.stratagem)
        if not(after and after.pointer==block.address and after.count==count and same(after.sequence,spec.sequence))then
            return nil,'CUSTOM_STRATAGEM_FAILED','the row did not read back as written'
        end
        state={stratagem=spec.stratagem,id=resolved.entry.root.id,type=resolved.record.record_kind,
            row_address=resolved.owner.base+resolved.record.offset,
            original={pointer=resolved.pointer,count=resolved.count,sequence=resolved.sequence},
            custom={pointer=block.address,count=count,sequence=spec.sequence},report=report,applied=true,
            restored=false}
        arm()
        metrics.count('custom_stratagem.applied')
        return {kind='apply',status='applied',stratagem=state.stratagem,type=state.type,id=state.id,
            original=state.original,custom=state.custom,report=report,avatar=avatar}
    end,callback)
end

-- The restore transaction (no authority needed: it only writes the captured original values back, guarded by the
-- values P0 wrote). Returns the result table, or nil, code, reason.
function M.restore_body()
    if not(state and state.applied)then return nil,'NOT_APPLIED','no custom sequence is applied'end
    if state.restored then return nil,'ALREADY_RESTORED','the original sequence is already restored'end
    local world,reason=world_module.open()
    if not world then return nil,'CUSTOM_STRATAGEM_UNAVAILABLE',tostring(reason)end
    local resolved,code
    resolved,code,reason=resolve(world,state.stratagem)
    if not resolved then return nil,code,reason end
    if resolved.pointer==state.original.pointer and resolved.count==state.original.count then
        state.restored=true
        disarm()
        return {kind='restore',status='restored',stratagem=state.stratagem,original=state.original,
            note='the row already holds its original sequence'}
    end
    if resolved.pointer~=state.custom.pointer or resolved.count~=state.custom.count then
        return nil,'ROW_CHANGED','the row holds neither the custom nor the original sequence'
    end
    -- Pointer first (the original array is the larger or equal one), then the count.
    local changes={{label='calldown.sequence',offset=SEQUENCE,expected=u64(state.custom.pointer),
        desired=u64(state.original.pointer)},
        {label='calldown.count',offset=COUNT,expected=u32(state.custom.count),desired=u32(state.original.count)}}
    if state.original.count<state.custom.count then changes={changes[2],changes[1]}end
    local report=write(world,resolved,changes)
    if report.status~='APPLIED'then
        return nil,'GUARD_REJECTED','the guarded restore was '..tostring(report.status)..': '..tostring(report.reason)
    end
    local after=resolve(world,state.stratagem)
    if not(after and after.pointer==state.original.pointer and after.count==state.original.count
            and same(after.sequence,state.original.sequence))then
        return nil,'CUSTOM_STRATAGEM_FAILED','the row did not read back as the original'
    end
    state.restored,state.restore_report=true,report
    disarm()
    metrics.count('custom_stratagem.restored')
    return {kind='restore',status='restored',stratagem=state.stratagem,original=state.original,report=report}
end
function M.restore(callback)return job(M.restore_body,callback)end

-- The row's live sequence now (what the matcher reads, and what the HUD draws when it next builds a slot), or nil and
-- the reason. Runs inside a job.
function M.read(callback,name)
    return job(function()
        local world,reason=world_module.open()
        if not world then return nil,'CUSTOM_STRATAGEM_UNAVAILABLE',tostring(reason)end
        local resolved,code
        resolved,code,reason=resolve(world,name or(state and state.stratagem)or M.P0.stratagem)
        if not resolved then return nil,code,reason end
        return {kind='read',status='read',pointer=resolved.pointer,count=resolved.count,sequence=resolved.sequence,
            type=resolved.record.record_kind,id=resolved.entry.root.id,
            runtime_owned=block~=nil and resolved.pointer==block.address}
    end,callback)
end

-- Redraws the P0 stratagem's slot in the HUD's stratagem list from the row's live code: the custom code while applied,
-- the original after restore (runtime/stratagem_hud.lua). The list draws a slot's arrows when its type first appears
-- and keeps them, so a code written later is matched but not drawn. Only that slot's arrow sprites, the layout flags
-- the game's own redraw sets and the slot's relayout flag are written; never the slot's type, the scrambler, the row or
-- the loadout. The slot must draw the original or the custom code now. A job: 'refreshed' or 'current' ('refused' /
-- 'failed' otherwise).
function M.refresh_hud(callback)
    return job(function()
        if not(state and state.applied)then return nil,'NOT_APPLIED','no custom sequence has been applied'end
        local world,reason=world_module.open()
        if not world then return nil,'CUSTOM_STRATAGEM_UNAVAILABLE',tostring(reason)end
        if not(world.runtime.query and world.runtime.write and world.runtime.protect)then
            return nil,'CUSTOM_STRATAGEM_UNAVAILABLE','this Runtime adapter cannot write'
        end
        local draw=state.restored and state.original.sequence or state.custom.sequence
        local result,code
        result,code,reason=hud.refresh(world,{type=state.type,row=state.row_address,draw=draw,
            from={state.original.sequence,state.custom.sequence}})
        if not result then return nil,code,reason end
        -- Which code the slot draws now, for the Lua-state-close restore.
        state.hud_draws=state.restored and'original'or'custom'
        result.kind='refresh_hud'
        return result
    end,callback)
end

-- A copy of the state for logs and status keys.
function M.state()
    if not state then return {applied=false}end
    return {stratagem=state.stratagem,id=state.id,type=state.type,row_address=state.row_address,
        original={pointer=state.original.pointer,count=state.original.count,sequence=state.original.sequence},
        custom={pointer=state.custom.pointer,count=state.custom.count,sequence=state.custom.sequence},
        applied=state.applied,restored=state.restored,capacity=M.CAPACITY,
        report=state.report and{status=state.report.status,writes=state.report.writes,
            non_target_bytes_unchanged=state.report.non_target_bytes_unchanged,
            protection_restored=state.report.protection_restored}}
end
function M.reset_for_tests()state,block=nil,nil;disarm()end
return M
