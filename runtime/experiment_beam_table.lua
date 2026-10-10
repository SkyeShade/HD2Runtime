-- RUNTIME-OWNED RELOCATED BEAMWEAPON TABLE (EXPERIMENTAL, SOLO ONLY; branch exp/multi-beam, never the 0.30.x line).
-- research/docs/beam-table-relocation-F5FEE03DCFDB.md, research/beam-table-relocation-F5FEE03DCFDB.json,
-- domains/beam_table.lua. The primitives runtime/experiment_beam_swap.lua (0.3.0, the 'owned table' path) uses to give
-- the AR-23 Liberator, LAS-58 Talon and SMG-32 Reprimand their OWN BeamWeapon records 24, 25 and 26:
--   * the copy: one private, NEVER-FREED page (runtime adapter permanent_block, PAGE_READONLY like the game's own table)
--     holding the table's 32-byte framing (component index + the 28-byte DL header), its 46 index rows (the file's,
--     plus the rows the caller adds BEFORE it goes live) and records 0..23 byte-identical to the file, then the
--     Runtime-owned records 24.. (each the donor's bytes), then a 32-byte trailer (magic, the original table, the
--     component index, the record count) that names the page as HD2Runtime's in a log;
--   * the switch: ONE aligned 8-byte store into slot 270 ([[game + 0x346BF98] + 0xF12CE8]), in a guarded transaction
--     whose before-bytes are the entity allocation's own table: the game re-reads the slot on every lookup and nothing
--     caches it (the research's census: three readers, all per call); records 24.. are reached (the lookup takes the
--     record base from the slot and does not bound the index); the default record +0xDA8 is the file's record 23;
--   * the registry (core/owned_tables.lua): after the switch, exactly that pointer over exactly that original is
--     HD2Runtime's own; core/component_tables.lua accepts it and core/entity_catalog.lua reads BeamWeapon rows and
--     records from the copy (typed writes land where the game reads). Any other value of the slot is FOREIGN: refused,
--     never chained onto (True Lasgun Beam Overhaul moves this table);
--   * re-validation on every call (M.locate): the slot back to the file's own table while the registry names a copy =
--     the copy is dead (a loader reload or another program): the registry is cleared and the table is vanilla again.
-- Nothing here gates on live instances or solo: runtime/experiment_beam_swap.lua does, for every write it makes.
if rawget(_G,'jit')then jit.off(true,true)end
local b=require('hd2runtime/core/bytes')
local log_module=require('hd2runtime/runtime/log')
local owned=require('hd2runtime/core/owned_tables')
local profile=require('hd2runtime/schemas/current')
local T=require('hd2runtime/domains/beam_table')
local D=require('hd2runtime/domains/beam_swap')
local CT=require('hd2runtime/domains/component_tables')
local M={}
M.VERSION='0.1.0-experimental'
M.OWNER='HD2Runtime owned BeamWeapon table (multi-weapon beam experiment)'
M.COMPONENT='BeamWeaponComponentData'
local PRIVATE,COMMIT,READONLY,READWRITE,PAGE=0x20000,0x1000,0x2,0x4,4096
local L=T.layout
local MG=D.manager
local COPIES_KEY='HD2RuntimeBeamTableCopiesV1'
local proven={}             -- world key -> true | reason

local function log(text)log_module.emit('BEAM TABLE: '..text)end
local function fail(text)error(text,0)end
local function u64(value)
    local lo=value%4294967296
    return b.encode(lo,'u32')..b.encode((value-lo)/4294967296,'u32')
end
M.u64=u64

-- The pins of the relocation research (exact bytes), once per proven world: true, or nil and why.
function M.prove(world)
    local key=world.key
    if proven[key]==true then return true end
    if proven[key]then return nil,proven[key]end
    local why
    if T.source.gameDllSha256~=profile.dll_sha then why='the beam table research covers another game.dll build'end
    for _,pin in ipairs(T.pins)do
        if not why and not world.view.proves(world.game+pin.rva,pin.hex)then
            why=('native code not as reviewed at game.dll+0x%X (%s)'):format(pin.rva,pin.label)
        end
    end
    proven[key]=why or true
    if why then return nil,why end
    return true
end

local function region(world,at)
    local r=world.runtime.query(at)
    if not(r and r.state==COMMIT and r.type==PRIVATE and r.allocation_base and r.allocation_base>0
        and at>=r.base and at<r.base+r.size)then
        return nil
    end
    return r
end

-- The trailer that ends every copy: magic, the original table, the component index, the record count.
function M.trailer(original,records)
    return T.trailer.magic..u64(original)..b.encode(T.slot.index,'u32')..b.encode(records,'u32')
end
local function trailer_at(entry)return entry.table+L.recordBase+entry.records*L.recordStride end

-- Where the game reads the BeamWeapon table now, re-derived and checked. Returns t or raises:
--   t.mode 'in_place' (the slot is the entity allocation's own table), 'owned' (exactly HD2Runtime's registered copy
--   over this original) or 'foreign' (anything else; t.reason says why); t.manager, t.slot_at, t.slot, t.base (the
--   entity allocation), t.original (its own table), t.framing, t.file (rows + records 0..23 of the file's table),
--   t.manager_owner (the transaction owner of the slot's page); owned: t.entry, t.copy (rows + every record),
--   t.copy_owner; t.reloaded = true when a registered copy was found dead (and forgotten) by this call.
function M.locate(world)
    local manager=world.view.pointer(world.game+MG.global)
    if not manager then fail('TARGET_UNAVAILABLE: the entity manager is not initialised')end
    local t={manager=manager,slot_at=manager+T.slot.offset}
    if t.slot_at%8~=0 then fail('the BeamWeapon slot is not 8-byte aligned')end
    t.slot=world.view.pointer(t.slot_at)
    if not t.slot then fail('TARGET_UNAVAILABLE: the BeamWeapon slot is unreadable')end
    local esh=world.view.pointer(manager+MG.eshSlot)
    if not esh then fail('TARGET_UNAVAILABLE: the entity map slot is unreadable')end
    t.base=esh-28
    if world.view.read(t.base,28)~=b.unhex(profile.map_header)then
        fail('CONFLICT: the game reads its EntitySettingsHashmap from another place (another mod moved it)')
    end
    local c=assert(profile.components[M.COMPONENT],'BeamWeapon profile component')
    assert(c.index==T.slot.index and c.indices==L.rows and c.records==L.fileRecords and c.stride==L.recordStride
        and c.record_offset==L.recordBase,'the BeamWeapon schema differs from the research')
    t.original=t.base+c.offset+CT.tableFromProfileOffset
    t.framing=world.view.read(t.original-L.framing,L.framing)
    if not(t.framing and b.u32(t.framing,0)==c.index and t.framing:sub(5,32)==b.unhex(c.header))then
        fail('the BeamWeapon table framing changed')
    end
    t.file=world.view.read(t.original,L.recordBase+L.fileRecords*L.recordStride)
    if not t.file then fail('TARGET_UNAVAILABLE: the BeamWeapon table is unreadable')end
    -- The slot's page: the transaction owner of the switch. Not fatal here (the shared path never writes the slot):
    -- without it the owned path is unavailable (t.slot_unwritable says why).
    local mr=region(world,t.slot_at)
    local page=t.slot_at-t.slot_at%PAGE
    if not(mr and mr.protect==READWRITE and mr.base<=page and page+PAGE<=mr.base+mr.size)then
        t.slot_unwritable='the BeamWeapon slot\'s page is not one read-write private region'
    else
        t.manager_owner={base=mr.allocation_base,size=page+PAGE-mr.allocation_base,type=PRIVATE,protect=READWRITE}
    end
    local entry=owned.get(M.COMPONENT)
    if t.slot==t.original then
        t.mode='in_place'
        if entry then
            owned.clear(M.COMPONENT)
            t.reloaded=true
            log(('RELOAD DETECTED: the slot holds the entity file\'s own table again (%s): HD2Runtime\'s copy is dead '
                ..'(never freed) and forgotten; the BeamWeapon table is vanilla'):format(entry.original==t.original
                and'the same table'or'a new entity allocation'))
        end
        return t
    end
    if entry and t.slot==entry.table and entry.original==t.original then
        local q=region(world,entry.table)
        if not(q and q.allocation_base==entry.allocation and q.base+q.size>=entry.allocation+entry.size
            and(q.protect==READONLY or q.protect==READWRITE))then
            fail('HD2Runtime\'s BeamWeapon copy is not the allocation it built')
        end
        if world.view.read(entry.table-L.framing,L.framing)~=t.framing then
            fail('HD2Runtime\'s BeamWeapon copy framing changed')
        end
        if world.view.read(trailer_at(entry),T.trailer.size)~=M.trailer(entry.original,entry.records)then
            fail('HD2Runtime\'s BeamWeapon copy trailer changed')
        end
        t.copy=world.view.read(entry.table,L.recordBase+entry.records*L.recordStride)
        if not t.copy then fail('TARGET_UNAVAILABLE: HD2Runtime\'s BeamWeapon copy is unreadable')end
        t.mode='owned'
        t.entry=entry
        t.copy_owner={base=entry.allocation,size=entry.size,type=PRIVATE,protect=q.protect}
        return t
    end
    t.mode='foreign'
    if entry then
        owned.clear(M.COMPONENT)
        log('the slot no longer holds HD2Runtime\'s copy: another program changed it; the copy is forgotten')
    end
    -- A page that carries HD2Runtime's trailer but is not registered: a copy from an earlier Lua state.
    local q=region(world,t.slot)
    local own_page=false
    if q and q.allocation_base==t.slot-L.framing then
        for records=L.fileRecords+1,L.fileRecords+8 do
            local at=t.slot+L.recordBase+records*L.recordStride
            if at+T.trailer.size<=q.base+q.size and world.view.read(at,T.trailer.size)==M.trailer(t.original,records)then
                own_page=true
            end
        end
    end
    t.reason=own_page and'the game reads its BeamWeapon table from an HD2Runtime copy this session no longer records '
        ..'(an earlier Lua state): restart the game'
        or'CONFLICT: the game reads its BeamWeapon table from another place (another mod moved it, e.g. True Lasgun '
        ..'Beam Overhaul): HD2Runtime never chains onto a foreign copy'
    return t
end

-- How many copies this game process has built (they are never freed); a new one is refused past T.maxCopies.
function M.copies()return rawget(_G,COPIES_KEY)or 0 end
function M.available(world)
    local ok,why=M.prove(world)
    if not ok then return nil,'UNPROVEN: '..tostring(why)end
    if type(world.runtime.permanent_block)~='function'then
        return nil,'this Runtime adapter cannot allocate a permanent block'
    end
    if M.copies()>=T.maxCopies then
        return nil,('%d copies were built this session (each stays allocated): restart the game'):format(M.copies())
    end
    return true
end

-- The copy's bytes: framing, the 46 rows (the file's, with `rows` = {[row] = 16 bytes} written in), records 0..23 =
-- the file's, then `records` = {[24] = 120 bytes, ...} (consecutive from 24), then the trailer.
function M.copy_bytes(t,rows,records)
    local body={t.framing}
    for row=0,L.rows-1 do
        local raw=t.file:sub(row*L.rowStride+1,(row+1)*L.rowStride)
        if rows[row]then
            assert(raw==string.rep('\0',L.rowStride),'row '..row..' of the file table is not empty')
            assert(#rows[row]==L.rowStride,'row bytes')
            raw=rows[row]
        end
        body[#body+1]=raw
    end
    body[#body+1]=t.file:sub(L.recordBase+1,L.recordBase+L.fileRecords*L.recordStride)
    local count=L.fileRecords
    while records[count]do
        assert(#records[count]==L.recordStride,'record bytes')
        body[#body+1]=records[count];count=count+1
    end
    assert(count>L.fileRecords and count<=L.records,'the copy needs its own records (24..)')
    for k in pairs(records)do assert(k>=L.fileRecords and k<count,'Runtime-owned records must be consecutive from 24')end
    body[#body+1]=M.trailer(t.original,count)
    local bytes=table.concat(body)
    assert(#bytes<=PAGE,'the copy does not fit one page')
    return bytes,count
end

-- Builds the copy (NOT live): a permanent page, read back and checked. Returns the owned entry (not registered).
function M.build(world,t,rows,records)
    assert(t.mode=='in_place','a copy is built only while the game reads the file\'s own table')
    local ok,why=M.available(world)
    if not ok then fail(why)end
    local bytes,count=M.copy_bytes(t,rows,records)
    local address=world.runtime.permanent_block(bytes)
    rawset(_G,COPIES_KEY,M.copies()+1)
    assert(type(address)=='number'and address>0 and address%PAGE==0,'the permanent block is not page-aligned')
    local q=region(world,address)
    if not(q and q.allocation_base==address and q.protect==READONLY and q.base+q.size>=address+#bytes)then
        fail('the copy is not one read-only private allocation')
    end
    if world.view.read(address,#bytes)~=bytes then fail('the copy did not read back as built')end
    local size=#bytes+(PAGE-#bytes%PAGE)%PAGE
    log(('copy %d built: %d bytes at a new private read-only page (never freed): framing, 46 rows, records 0..23 as '
        ..'the file, %d Runtime-owned record%s, trailer; not live yet'):format(M.copies(),#bytes,count-L.fileRecords,
        count-L.fileRecords==1 and''or's'))
    return {owner=M.OWNER,index=T.slot.index,table=address+L.framing,allocation=address,size=size,
        original=t.original,records=count}
end

-- The slot change: {label, owner, offset, before, desired} (forward: the original -> the copy; back: the reverse).
function M.slot_change(t,entry,forward)
    local x,y=u64(t.original),u64(entry.table)
    return {label='beam_table.slot270',owner=t.manager_owner,offset=t.slot_at-t.manager_owner.base,
        before=forward and x or y,desired=forward and y or x}
end
function M.register(entry)owned.set(M.COMPONENT,entry)end
function M.forget()owned.clear(M.COMPONENT)end

-- Tests only.
function M.reset_for_tests()proven={};owned.clear(M.COMPONENT);rawset(_G,COPIES_KEY,nil)end
return M
