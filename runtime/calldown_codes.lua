-- Stratagem calldown codes (hd2.fields.stratagem.calldown_code, docs/stratagem-calldown-code.md): the Runtime side of
-- the field that the generic stratagem write path (domains/stratagem_writes.lua) cannot express as bytes in place.
--
-- A StratagemInfo row holds its code as a pointer to u32 directions (+0x40) and their count (+0x48). A changed code is
-- an immutable Runtime-owned array, one per distinct code, kept for the life of this Lua state; the guarded write
-- points the row at it. This module:
--   * encodes and decodes codes ('up', 'right', 'down', 'left' <-> 1..4, 1 to 9 directions);
--   * owns the arrays and recognises them when a row already points to one;
--   * remembers every row a calldown write was planned for: its native pointer, count and code, and every code the
--     Runtime put there;
--   * keeps the HUD's stratagem list in step with those rows. The list draws a slot's arrows once, so whenever a
--     row's live code differs from what was last drawn for it (after an apply, an ensure re-apply, a rollback or a
--     restore, whichever path wrote it) or a new mission builds a new list, the slot is redrawn through
--     runtime/stratagem_hud.lua once it exists. Checks run every 0.25 s only while a row differs from its native
--     code, a redraw is pending or a planned write has not shown yet; a redraw happens once per change, never every
--     frame. A refused redraw never undoes the row write: it is reported once and retried;
--   * restores every row that still points to a Runtime array before this Lua state (and its arrays) goes away,
--     then redraws its slot.
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log=require('hd2runtime/runtime/log')
local metrics=require('hd2runtime/runtime/metrics')
local transaction=require('hd2runtime/core/guarded_transaction')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local C=require('hd2runtime/domains/stratagem_calldown')
local hud=require('hd2runtime/runtime/stratagem_hud')
local M={}

M.DIRECTIONS={'up','right','down','left'}
M.VALUES={up=1,right=2,down=3,left=4}
M.MAX=C.maxLength
M.CAPACITY=10                     -- u32 entries per array: room for the longest code, the rest zero
M.SYNC_INTERVAL=0.25              -- seconds between checks while a row differs from its native code
M.PLAN_GRACE=300                  -- seconds a planned write is awaited: the longest operation budget (api/plan.lua)
local SEQUENCE,COUNT=C.row.sequence,C.row.count
local WAITING={NO_HUD=true,SLOT_ABSENT=true,NOT_IN_MISSION=true}

local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function u64(n)return u32(n%4294967296)..u32(math.floor(n/4294967296))end
local function same(a,c)
    if not(a and c)or#a~=#c then return false end
    for index=1,#a do if a[index]~=c[index]then return false end end
    return true
end
M.same=same
local function key(values)return table.concat(values,',')end

-- Direction names -> native values, or nil and the reason.
function M.values(code,label)
    label=label or'calldown code'
    if type(code)~='table'or#code<1 or#code>M.MAX then
        return nil,label..' must be a list of 1 to '..M.MAX..' directions'
    end
    for index in pairs(code)do
        if type(index)~='number'or index%1~=0 or index<1 or index>#code then
            return nil,label..' must be a plain list of directions'
        end
    end
    local out={}
    for index,name in ipairs(code)do
        local value=M.VALUES[name]
        if not value then
            return nil,label..' direction '..index..' must be "up", "right", "down" or "left", not '..tostring(name)
        end
        out[index]=value
    end
    return out
end
-- Native values -> direction names (unknown values as numbers).
function M.names(values)
    local out={}
    for index,value in ipairs(values or{})do out[index]=M.DIRECTIONS[value]or value end
    return out
end
function M.text(values)
    local out={}
    for index,name in ipairs(M.names(values))do out[index]=tostring(name)end
    return table.concat(out,' ')
end
-- The u32 little-endian bytes of values, padded with zeros to the array capacity.
function M.bytes(values)
    local parts={}
    for index,value in ipairs(values)do parts[index]=u32(value)end
    return table.concat(parts)..string.rep('\0',(M.CAPACITY-#values)*4)
end
function M.decode(bytes)
    local out={}
    for index=1,#bytes/4 do out[index]=b.u32(bytes,(index-1)*4)end
    return out
end
-- How code a relates to code c (native values): 'equal', 'prefix' (a is the start of c), 'extends' (c is the start of
-- a), or nil when they part before either ends.
function M.relation(a,c)
    for index=1,math.min(#a,#c)do if a[index]~=c[index]then return nil end end
    if#a==#c then return'equal'end
    return#a<#c and'prefix'or'extends'
end
-- Every reviewed native code (every StratagemInfo row, by stable id) that relates to values, read-only:
-- {{id, values, relation}} sorted by stable id; the ids in skip (a set) are left out.
function M.native_relations(values,skip)
    local out={}
    for id,code in pairs(C.nativeCodes)do
        local relation=M.relation(values,code)
        if relation and not(skip and skip[tonumber(id)])then
            out[#out+1]={id=tonumber(id),values=code,relation=relation}
        end
    end
    table.sort(out,function(x,y)return x.id<y.id end)
    return out
end

-- The native calldown readers (domains/stratagem_calldown.lua pins: the matcher and both sequence copies read the
-- row's +0x40/+0x48 live), proven once per loaded game.dll before any calldown write. true, or nil and the reason.
local proven={}
function M.prove(runtime)
    if C.source.gameDllSha256~=profile.dll_sha then return nil,'the calldown research covers another game.dll build'end
    local handle=runtime.module and runtime.module('game.dll')
    local base=handle and runtime.address and runtime.address(handle)
    if type(base)~='number'then return nil,'game.dll is not loaded'end
    if proven[base]then return true end
    for _,pin in ipairs(C.pins)do
        local expected=pin.hex:gsub('..',function(pair)return string.char(tonumber(pair,16))end)
        if runtime.read(base+pin.rva,#expected)~=expected then
            return nil,'native calldown reader changed ('..pin.label..' at game+'..string.format('%X',pin.rva)..')'
        end
    end
    proven[base]=true
    return true
end

------------------------------------------------------------------------------------------------- arrays --
-- One immutable array per distinct code. Its bytes never change once a row may point to it, so switching a row between
-- codes is always a pointer change, never a rewrite under the game. Each operation runs on its own write adapter and
-- an array lives as long as the adapter that allocated it, so the array keeps that adapter for the life of this Lua
-- state.
local arrays={}                    -- [key] = {address, runtime}
local owned={}                     -- [address] = values
function M.array(runtime,values)
    local item=arrays[key(values)]
    if item then return item.address end
    assert(runtime.owned_block and runtime.owned_write,'this Runtime adapter cannot own memory')
    local address=runtime.owned_block(M.CAPACITY*4)
    local bytes=M.bytes(values)
    runtime.owned_write(address,bytes)
    assert(runtime.read(address,#bytes)==bytes,'the Runtime-owned calldown array did not read back as written')
    arrays[key(values)]={address=address,runtime=runtime}
    owned[address]=values
    metrics.count('calldown.arrays')
    return address
end
M.key=key
-- The code of a Runtime-owned array of that count, or nil when the address is not one.
function M.owned(address,count)
    local values=owned[address]
    if values and count==#values then return values end
end

---------------------------------------------------------------------------------------------- registry --
-- [row address] = {address, id, type, name, owner, offset, native = {pointer, count, values}, codes = {[key] =
-- values}, drawn (the code the HUD sync last confirmed), pending, expect (a planned code not seen yet), expect_left,
-- hud = {state, code, reason}, said}.
local rows={}
local sentinel,watch
local finalize

-- The row's live code: values, pointer, count; nil when unreadable or not a code this module can name (the native
-- array, or a Runtime array).
local function live(world,row)
    local bytes=world.view.read(row.address+SEQUENCE,12)
    if not bytes then return nil end
    local pointer,count=b.pointer(bytes,0),b.u32(bytes,8)
    if pointer==row.native.pointer and count==row.native.count then return row.native.values,pointer,count end
    local values=M.owned(pointer,count)
    if values then return values,pointer,count end
end

local function note(row,text)
    if row.said[text]then return end
    row.said[text]=true
    log.emit('[HD2Runtime] stratagem calldown '..row.name..': '..text)
end

-- One redraw attempt (one tick, no yield): the slot draws the row's live code.
local function sync(world,row,values)
    local from={row.native.values}
    for _,code in pairs(row.codes)do from[#from+1]=code end
    local result,code,reason=hud.refresh(world,{type=row.type,row=row.address,draw=values,from=from})
    if result then
        row.pending,row.drawn=false,values
        row.hud={state=result.status,index=result.index,writes=result.writes and#result.writes or 0}
        if result.status=='refreshed'then
            log.emit(('[HD2Runtime] stratagem calldown %s: HUD slot %d redrawn %s -> %s (%d writes, guard %s)'):format(
                row.name,result.index,M.text(result.before),M.text(result.after),#result.writes,
                tostring(result.report and result.report.status)))
        end
        metrics.count('calldown.hud_'..result.status)
        return
    end
    row.hud={state='refused',code=code,reason=reason}
    if WAITING[code]then
        -- No list yet, or the stratagem is not in it. A filled list without its slot means it is not in the
        -- loadout: nothing to draw (a slot filled later is built from the row by the game itself).
        if code=='SLOT_ABSENT'and hud.populated(world)then
            row.pending,row.drawn=false,values
            row.hud={state='not_in_list',reason=reason}
        end
        return
    end
    note(row,('calldown applied; HUD refresh refused: %s: %s (the code stays applied; retried every %g s)'):format(
        tostring(code),tostring(reason),M.SYNC_INTERVAL))
    if code=='HUD_UNAVAILABLE'then row.pending,row.drawn=false,values end
    metrics.count('calldown.hud_refused')
end

-- The check: every row whose live code differs from what was last drawn for it (or every row, when a new mission
-- built a new list) is pending; pending rows are redrawn once in a mission. Returns whether anything still needs
-- watching: a pending row, a row that does not hold its native code, or a planned write not seen yet (an operation
-- writes a few ticks after it plans, and the check may run in between; a refused write never shows, so it is awaited
-- for PLAN_GRACE seconds at most).
local function check(world,mission,started,dt)
    local active=false
    for _,row in pairs(rows)do
        local values=live(world,row)
        if row.expect then
            if values and same(values,row.expect)then row.expect=nil
            else
                row.expect_left=row.expect_left-(dt or 0)
                if row.expect_left<=0 then row.expect=nil end
            end
        end
        if values then
            if(started or not same(values,row.drawn))and not row.pending then row.pending,row.said=true,{}end
            if row.pending and mission then sync(world,row,values)end
            if row.pending or not same(values,row.native.values)then active=true end
        end
        if row.expect then active=true end
    end
    return active
end
local function mission_now(world)
    local state=world_module.game_state(world)
    return state and state.mission or false
end
local function attach()
    if watch and watch.status=='active'then return end
    local elapsed,mission=M.SYNC_INTERVAL,nil
    local current={status='active'}
    function current.cancel()current.status='cancelled'end
    function current.tick(dt)
        elapsed=elapsed+(dt or 0)
        if elapsed<M.SYNC_INTERVAL then return end
        local spent=elapsed
        elapsed=0
        local world,why=world_module.open()
        if not world then
            -- No proven game world on this build: the HUD cannot be kept in step. The row writes stand; the next
            -- calldown write tries again.
            for _,row in pairs(rows)do row.hud={state='unavailable',reason=tostring(why)}end
            current.status='complete'
            if watch==current then watch=nil end
            return
        end
        local now=mission_now(world)
        -- A new mission builds a new list from the rows: confirm every changed row once more.
        local started=now and mission==false
        mission=now
        if not check(world,now,started,spent)then
            current.status='complete'
            if watch==current then watch=nil end
        end
    end
    watch=current
    scheduler.attach(current)
end
local function arm()
    if sentinel then return end
    local ok,ffi=pcall(require,'ffi')
    if ok then sentinel=ffi.gc(ffi.new('uint8_t[1]'),function()pcall(finalize)end)end
end

-- A calldown write is planned for this row. info = {address, id, type, name, owner, offset, native = {pointer,
-- count, values}, values (the code the write puts there)}. The native state is recorded the first time a row is seen;
-- the HUD check starts (or keeps running) from here.
function M.planned(info)
    local row=rows[info.address]
    if not row then
        row={address=info.address,id=info.id,type=info.type,name=info.name,owner=info.owner,offset=info.offset,
            native=info.native,codes={},drawn=info.native.values,said={}}
        rows[info.address]=row
    end
    if info.values and not same(info.values,row.native.values)then row.codes[key(info.values)]=info.values end
    row.expect,row.expect_left=info.values,M.PLAN_GRACE
    arm()
    attach()
end
-- The native pointer, count and code of a row seen before, or nil.
function M.native(address)
    local row=rows[address]
    return row and row.native
end
-- {name, values, native, drawn, pending, hud} of a row seen before, or nil.
function M.status(address)
    local row=rows[address]
    if not row then return nil end
    local world=world_module.open()
    return {name=row.name,values=world and live(world,row),native=row.native.values,drawn=row.drawn,
        pending=row.pending==true,hud=row.hud}
end
-- The status of every row seen, with its address, by name (diagnostics).
function M.list()
    local out={}
    for address in pairs(rows)do
        local item=M.status(address)
        item.address=address
        out[#out+1]=item
    end
    table.sort(out,function(x,y)return x.name<y.name end)
    return out
end
-- One check now (tests and diagnostics): the same as the periodic one.
function M.check_now(mission_started)
    local world=world_module.open()
    if world then return check(world,mission_now(world),mission_started==true)end
end
-- Whether the periodic check is running.
function M.watching()return watch~=nil and watch.status=='active'end

-- Before this Lua state (and its arrays) goes away: every row that still points to a Runtime array gets its native
-- pointer and count back through the guarded transaction (the count first: the array has room for any count), then
-- its slot is redrawn. Best effort; refused when anything differs.
function finalize()
    local world=world_module.open()
    if not world then return end
    for address,row in pairs(rows)do
        local bytes=world.runtime.read(address,C.row.stride)
        local pointer=bytes and b.pointer(bytes,SEQUENCE)
        local count=bytes and b.u32(bytes,COUNT)
        if pointer and M.owned(pointer,count)then
            local plan={snapshots={{owner=row.owner,offset=row.offset,bytes=bytes}},changes={
                {label='calldown.count',owner=row.owner,offset=row.offset+COUNT,expected=u32(count),
                    desired=u32(row.native.count),before=u32(count),already_desired=false,chain={}},
                {label='calldown.sequence',owner=row.owner,offset=row.offset+SEQUENCE,expected=u64(pointer),
                    desired=u64(row.native.pointer),before=u64(pointer),already_desired=false,chain={}}}}
            if transaction.apply(world.runtime,plan).status=='APPLIED'then
                local from={row.native.values}
                for _,code in pairs(row.codes)do from[#from+1]=code end
                pcall(hud.refresh,world,{type=row.type,row=address,draw=row.native.values,from=from})
            end
        end
    end
end
function M.finalize_for_tests()finalize()end
function M.reset_for_tests()
    rows,arrays,owned,proven={},{},{},{}
    if watch then watch.status='cancelled';watch=nil end
    if sentinel then pcall(function()require('ffi').gc(sentinel,nil)end);sentinel=nil end
end
return M
