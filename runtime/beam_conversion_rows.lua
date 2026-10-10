-- Per-weapon beam and damage rows of beam conversions (research/docs/beam-rows-borrowed-F5FEE03DCFDB.md; the `rows`
-- section of domains/beam_conversion.lua). INTERIM, borrowedVanillaRow, build-scoped, solo only.
--
-- A beam shot takes its range, multipliers and DamageInfo id from the BeamInfo row of its BeamType, read through the
-- game.dll pointer array [game + 0x37C8250 + 8 x BeamType] when BeamFire runs, and the hit reads the DamageInfo row
-- through [game + 0x37C60C0 + 8 x id]. Both arrays are fixed (31 and 650 slots, every slot holds a row), so a weapon's
-- own row needs a BORROWED slot: one of the spare BeamTypes (3, 15, 16, 19, 20, 27) and spare DamageInfo ids (278, 577,
-- 233, 637, 434, 564) that no data, no traced code constant and no live record references on this build. Pair i is
-- (BeamType k, DamageInfo d). The vanilla rows are never written: the slot is repointed (one aligned 8-byte store) to a
-- Runtime-owned copy in a never-freed block: beam row = the Trident's row 6 with key k and +0x0C = d, damage row = the
-- Trident's row 508 with key d; the converted weapon's own BeamWeapon record +0 then names k. Restore = the vanilla
-- pointer back (only while the slot still holds the owned copy) and the record +0 back to 6.
-- Every consumer reads the slot at use time and nothing caches a row pointer or keys on +0 (the research's census), the
-- only writers are the startup loaders. A reload (the slot back to a vanilla row) is detected: the pair is free again.
-- At most 6 converted weapons have their own rows at once (ROWS_FULL past that).
if rawget(_G,'jit')then jit.off(true,true)end
local b=require('hd2runtime/core/bytes')
local log_module=require('hd2runtime/runtime/log')
local profile=require('hd2runtime/schemas/current')
local C=require('hd2runtime/domains/beam_conversion')
local RW=C.rows
local M={}
local PRIVATE,COMMIT,READONLY,READWRITE,PAGE=0x20000,0x1000,0x2,0x4,4096
local BEAM_STRIDE,DAMAGE_STRIDE=RW.beamTable.stride,RW.damageTable.stride
local KEY='HD2RuntimeBeamConversionRowsV1'
local proven={}
local function log(text)log_module.emit('BEAM CONVERSION ROWS: '..text)end
local function fail(text)error(text,0)end
local function u64(value)
    local lo=value%4294967296
    return b.encode(lo,'u32')..b.encode((value-lo)/4294967296,'u32')
end
local TRIDENT_BEAM,TRIDENT_DAMAGE=b.unhex(RW.tridentBeamHex),b.unhex(RW.tridentDamageHex)
M.PAIRS=#RW.pairs
local function registry()return rawget(_G,KEY)end

-- Build scope and pins: true, or nil and why (a code a refusal names).
function M.available(world)
    if RW.gameDllSha256~=profile.dll_sha then
        return nil,'BORROWED_ROWS_UNVERIFIED_BUILD: the spare BeamType / DamageInfo slots were proven unreferenced on '
            ..'build '..RW.build..' only; per-weapon damage, AP and range are refused on this build until '
            ..'scripts/research_beam_rows.py is re-run here'
    end
    local key=world.key
    if proven[key]==nil then
        local why
        for _,pin in ipairs(RW.pins)do
            if not why and not world.view.proves(world.game+pin.rva,pin.hex)then
                why=('native code not as reviewed at game.dll+0x%X (%s)'):format(pin.rva,pin.label)
            end
        end
        proven[key]=why or true
    end
    if proven[key]~=true then return nil,'UNPROVEN: '..proven[key]end
    return true
end

local function image_owner(world,at)
    local r=world.runtime.query(at)
    if not(r and r.state==COMMIT and r.allocation_base==world.game and r.protect==READWRITE and at>=r.base
        and at+8<=r.base+r.size)then
        return nil
    end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=r.type,protect=r.protect}
end
local function private_rw(world,at,n)
    local r=world.runtime.query(at)
    return r and r.state==COMMIT and r.type==PRIVATE and r.protect==READWRITE and at>=r.base and at+n<=r.base+r.size
end

-- The desired bytes of pair i's rows for a weapon's values ({[field id] = value}; nil members: the Trident's).
function M.rows_for(i,values)
    local pair=RW.pairs[i]
    local beam=b.encode(pair.beamType,'u32')..TRIDENT_BEAM:sub(5,12)..b.encode(pair.damageInfo,'u32')
        ..TRIDENT_BEAM:sub(17)
    local damage=b.encode(pair.damageInfo,'u32')..TRIDENT_DAMAGE:sub(5)
    for _,f in ipairs(C.fields)do
        if f.row and values and values[f.id]~=nil then
            local bytes=b.encode(values[f.id],f.storage)
            if f.row=='beam'then beam=beam:sub(1,f.offset)..bytes..beam:sub(f.offset+5)
            else damage=damage:sub(1,f.offset)..bytes..damage:sub(f.offset+5)end
        end
    end
    return beam,damage
end
-- The values a pair's rows hold.
function M.values_of(beam,damage)
    local out={}
    for _,f in ipairs(C.fields)do
        if f.row then out[f.id]=b.value(f.row=='beam'and beam or damage,f.offset,f.storage)end
    end
    return out
end
function M.defaults()
    local out={}
    for _,f in ipairs(C.fields)do if f.row then out[f.id]=f.default end end
    return out
end
-- Whether values differ from the Trident's (a weapon needs its own rows only then).
function M.needed(values)
    for _,f in ipairs(C.fields)do
        if f.row and values[f.id]~=nil and b.encode(values[f.id],f.storage)~=b.encode(f.default,f.storage)then
            return true
        end
    end
    return false
end

-- Where every pair stands now. rs.pairs[i] = {k, d, slot_k, slot_d (addresses), ptr_k, ptr_d, owner_k, owner_d,
-- state = 'free' | 'owned' | 'foreign', reason, beam, damage (owned: the rows' bytes)}; rs.block (the registered block),
-- rs.block_owner, rs.block_bytes; rs.unavailable (why nothing can be borrowed).
function M.locate(world)
    local rs={pairs={}}
    local ok,why=M.available(world)
    if not ok then rs.unavailable=why;return rs end
    local block=registry()
    if block then
        local q=world.runtime.query(block.allocation)
        if not(q and q.state==COMMIT and q.type==PRIVATE and q.allocation_base==block.allocation
            and(q.protect==READONLY or q.protect==READWRITE))then
            fail('HD2Runtime\'s beam row block is not the allocation it built')
        end
        rs.block=block
        rs.block_bytes=world.view.read(block.allocation,block.used)
        if not rs.block_bytes or rs.block_bytes:sub(1,16)~=RW.magic then fail('the beam row block header changed')end
        rs.block_owner={base=block.allocation,size=block.size,type=PRIVATE,protect=q.protect}
    end
    local beam_slots=world.game+RW.beamTable.rva
    local damage_slots=world.game+RW.damageTable.rva
    for i,pair in ipairs(RW.pairs)do
        local P={i=i,k=pair.beamType,d=pair.damageInfo,slot_k=beam_slots+8*pair.beamType,
            slot_d=damage_slots+8*pair.damageInfo}
        P.ptr_k=world.view.pointer(P.slot_k);P.ptr_d=world.view.pointer(P.slot_d)
        P.owner_k=image_owner(world,P.slot_k);P.owner_d=image_owner(world,P.slot_d)
        if not(P.ptr_k and P.ptr_d and P.owner_k and P.owner_d)then
            P.state='foreign';P.reason='the BeamInfo / DamageInfo pointer arrays are not read-write game.dll memory'
        elseif block and P.ptr_k==block.beam_at[i]and P.ptr_d==block.damage_at[i]then
            P.state='owned'
            P.beam=world.view.read(P.ptr_k,BEAM_STRIDE);P.damage=world.view.read(P.ptr_d,DAMAGE_STRIDE)
            if not(P.beam and P.damage and b.u32(P.beam,0)==P.k and b.u32(P.beam,12)==P.d and b.u32(P.damage,0)==P.d)then
                P.state='foreign';P.reason='the owned rows of pair '..i..' changed'
            end
        elseif block and(P.ptr_k==block.beam_at[i]or P.ptr_d==block.damage_at[i])then
            P.state='foreign';P.reason='pair '..i..' is half repointed'
        else
            local beam=private_rw(world,P.ptr_k,BEAM_STRIDE)and world.view.read(P.ptr_k,BEAM_STRIDE)
            local damage=private_rw(world,P.ptr_d,DAMAGE_STRIDE)and world.view.read(P.ptr_d,DAMAGE_STRIDE)
            if beam and damage and b.hex(beam)==pair.beamHex and b.hex(damage)==pair.damageHex then
                P.state='free';P.vanilla_k,P.vanilla_d=P.ptr_k,P.ptr_d
                if block and block.vanilla_k[i]and(block.vanilla_k[i]~=P.ptr_k or block.vanilla_d[i]~=P.ptr_d)then
                    -- A reload placed the vanilla rows elsewhere: the block's record of them is updated at apply.
                    P.moved=true
                end
            else
                P.state='foreign'
                P.reason=('BeamType %d / DamageInfo %d are not the reviewed vanilla rows (another mod or a game '
                    ..'update changed them)'):format(P.k,P.d)
            end
        end
        rs.pairs[i]=P
    end
    -- Live references: no BeamInfo row the game reaches other than an owned one names a spare DamageInfo id.
    local spare_d={}
    for i,P in ipairs(rs.pairs)do spare_d[P.d]=i end
    for t=1,RW.beamTable.slots-1 do
        local at=world.view.pointer(beam_slots+8*t)
        local owned_row=false
        for i,P in ipairs(rs.pairs)do if P.state=='owned'and at==block.beam_at[i]then owned_row=true end end
        if at and at~=0 and not owned_row then
            local id=world.view.u32(at+12)
            if id and spare_d[id]and rs.pairs[spare_d[id]].state~='foreign'then
                rs.pairs[spare_d[id]].state='foreign'
                rs.pairs[spare_d[id]].reason=('BeamType %d names DamageInfo %d (no longer spare)'):format(t,id)
            end
        end
    end
    return rs
end

-- The block (built once per game process, never freed): magic, then every pair's beam row and damage row.
function M.build(world,rs)
    if rs.block then return rs.block end
    if type(world.runtime.permanent_block)~='function'then fail('REFUSED: this Runtime adapter cannot allocate memory')end
    local parts={RW.magic}
    local beam_off,damage_off={},{}
    local at=16
    for i=1,#RW.pairs do
        local beam,damage=M.rows_for(i,nil)
        beam_off[i]=at;parts[#parts+1]=beam;at=at+BEAM_STRIDE
        damage_off[i]=at;parts[#parts+1]=damage;at=at+DAMAGE_STRIDE
        local pad=(-at)%16;parts[#parts+1]=string.rep('\0',pad);at=at+pad
    end
    local bytes=table.concat(parts)
    local address=world.runtime.permanent_block(bytes)
    if world.view.read(address,#bytes)~=bytes then fail('the beam row block did not read back as built')end
    local block={allocation=address,size=#bytes+(PAGE-#bytes%PAGE)%PAGE,used=#bytes,beam_at={},damage_at={},
        vanilla_k={},vanilla_d={}}
    for i=1,#RW.pairs do
        block.beam_at[i]=address+beam_off[i];block.damage_at[i]=address+damage_off[i]
        local P=rs.pairs[i]
        if P.state=='free'then block.vanilla_k[i],block.vanilla_d[i]=P.ptr_k,P.ptr_d end
    end
    rawset(_G,KEY,block)
    log(('block built: %d bytes at a new private read-only block (never freed): %d beam / damage row pairs, each the '
        ..'Trident\'s rows 6 / 508 keyed to its borrowed slots'):format(#bytes,#RW.pairs))
    rs.block=block
    rs.block_bytes=bytes
    rs.block_owner={base=address,size=block.size,type=PRIVATE,protect=READONLY}
    return block
end

-- Changes ({label, address, before, desired, owner}) that make pair i's owned rows hold `values`.
function M.value_changes(rs,i,values)
    local block=rs.block
    local beam,damage=M.rows_for(i,values)
    local out={}
    local function diff(label,at,want)
        local off=at-block.allocation
        local cur=rs.block_bytes:sub(off+1,off+#want)
        for x=0,#want-4,4 do
            local p,q=cur:sub(x+1,x+4),want:sub(x+1,x+4)
            if p~=q then out[#out+1]={('%s+%d'):format(label,x),at+x,p,q,rs.block_owner}end
        end
    end
    diff('rows.beam'..RW.pairs[i].beamType,block.beam_at[i],beam)
    diff('rows.damage'..RW.pairs[i].damageInfo,block.damage_at[i],damage)
    return out
end
-- The slot repoints of pair i: damage id first (the beam row names it), then the BeamType; contexts for both.
function M.assign_changes(rs,i)
    local P,block=rs.pairs[i],rs.block
    block.vanilla_k[i],block.vanilla_d[i]=P.ptr_k,P.ptr_d
    return {{'rows.slot_damage'..P.d,P.slot_d,u64(P.ptr_d),u64(block.damage_at[i]),P.owner_d},
        {'rows.slot_beam'..P.k,P.slot_k,u64(P.ptr_k),u64(block.beam_at[i]),P.owner_k}},
        {{P.owner_d,P.slot_d,u64(P.ptr_d)},{P.owner_k,P.slot_k,u64(P.ptr_k)}}
end
-- The vanilla pointers back (BeamType first): only while the slots hold the owned copies.
function M.release_changes(rs,i)
    local P,block=rs.pairs[i],rs.block
    assert(P.state=='owned'and block.vanilla_k[i]and block.vanilla_d[i],'pair '..i..' is not owned')
    return {{'rows.slot_beam'..P.k,P.slot_k,u64(P.ptr_k),u64(block.vanilla_k[i]),P.owner_k},
        {'rows.slot_damage'..P.d,P.slot_d,u64(P.ptr_d),u64(block.vanilla_d[i]),P.owner_d}},
        {{P.owner_d,P.slot_d,u64(P.ptr_d)},{P.owner_k,P.slot_k,u64(P.ptr_k)}}
end

-- Whether a live beam shot (a ring entry) still names BeamType k or DamageInfo d.
function M.ring_busy(world,k,d)
    local ring=RW.ring
    local system=world.view.pointer(world.game+ring.global)
    if not system then return false end
    local raw=world.view.read(system+ring.base,ring.slots*ring.stride)
    if not raw then return true,'the beam ring is unreadable'end
    for slot=0,ring.slots-1 do
        local at=slot*ring.stride
        if raw:byte(at+ring.alive+1)~=0 and(b.u32(raw,at+ring.beamType)==k or b.u32(raw,at+ring.damageInfo)==d)then
            return true,'a live beam shot still uses BeamType '..k
        end
    end
    return false
end

-- Tests only.
function M.reset_for_tests()proven={};rawset(_G,KEY,nil)end
return M
