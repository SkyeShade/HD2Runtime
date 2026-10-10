-- MULTI-WEAPON BEAM SWAP EXPERIMENT (EXPERIMENTAL, SOLO ONLY; branch exp/multi-beam, never the 0.30.x line). The AR-23
-- Liberator, the LAS-58 Talon and the SMG-32 Reprimand fire LAS-13 Trident pulses, together or in any subset, through
-- in-place writes to the entity file (research/docs/multi-beam-swap-F5FEE03DCFDB.md, research/multi-beam-swap-
-- F5FEE03DCFDB.json; domains/beam_swap.lua). It generalises the live-proven Liberator swap (runtime/experiment_liberator_
-- beam.lua, kept unchanged as the fallback). Two paths, never mixed:
--
-- OWNED TABLE (0.3.0, the default; research/docs/beam-table-relocation-F5FEE03DCFDB.md, domains/beam_table.lua,
-- runtime/experiment_beam_table.lua): each weapon gets its OWN BeamWeapon record (Liberator 24, Talon 25, Reprimand 26)
-- in a Runtime-owned, never-freed copy of the BeamWeapon table the game is switched to read (one aligned 8-byte store
-- into slot 270, guarded). So each weapon has its own rate of fire and pulse (M.configure: BeamWeapon +104 fire rate,
-- +108 beams per pulse, +112 pulse seconds; the same members and ranges as the 0.30.4 beam pulse fields; 0.3.1 fits the
-- pulse into the shot interval, research/docs/beam-pulse-rate-F5FEE03DCFDB.md). The file's
-- own table is never written; records 0..23 in the copy start byte-identical to it, and typed writes (a mod changing
-- the Trident's beam.fire_rate) land in the copy while it is live (core/owned_tables.lua, core/component_tables.lua,
-- core/entity_catalog.lua). Per weapon: its row in the COPY (record index, then key; empty: Liberator 21, Talon 11,
-- Reprimand 25), then its list and magazine byte as below. The first apply builds the copy WITH the rows, then one
-- transaction makes it live (the slot) and swaps the lists; the last restore puts the lists back, then the slot.
--
-- SHARED RECORD (0.1.0, the fallback when the owned table is not available: a pin, the adapter, the copy budget; or
-- opts.path = 'shared'): BeamWeapon record 23 (table +0xDA8, 120 bytes; the table's one unowned record) := the
-- Trident's record 18, written once, before the first row, restored after the last row is gone; rows in the FILE's
-- table name record 23 (research section 2). All three share one record: one rate and pulse.
--
-- Per weapon, both paths (order Liberator, Talon, Reprimand; restore in reverse):
--   1. its BeamWeapon index row (above);
--   2. its membership list: ProjectileWeapon (321) out, BeamWeapon (270) in, same count, sorted, pointer unchanged
--      (one 4-aligned window: Liberator / Reprimand 8 bytes, Talon 12 bytes incl. 2 bytes of the next list, kept);
--      its ProjectileWeapon row stays;
--   3. magazine weapons only (Liberator record 201, Reprimand record 139, each its own): +156..+159 01000000 ->
--      00000000, the 40-K Meltagun's no-chamber model (the chamber is filled only by a ProjectileWeapon instance).
--      The Talon is a heat weapon without a magazine: after the swap its components are a subset of the Trident's.
-- The donor is the Trident's record for every weapon: only its pulsed mode 6 is proven with these weapons' ammunition
-- (one round per pulse; heat per pulse). A continuous donor (mode 4: Scythe, LAS-98) clears the instance's discrete-shot
-- flag at spawn (0x546A4F) and its round / heat spend on a magazine weapon is not traced: not offered.
-- One guarded transaction per apply, restore and settings change (core/guarded_transaction.lua: context bytes compared
-- before every write, READONLY pages opened and restored, every target read back, ROLLBACK of everything already
-- written on any failure), so an apply of several weapons is all or nothing.
--
-- Not exported by api/hd2.lua: proof/MultiBeamProof requires this module. Every call re-proves everything and fails
-- closed with a reason; nothing is cached but the pin proof per game.dll:
--   * the build fingerprint, every pin of domains/beam_swap.lua (the live-proven Liberator pins and the multi-weapon
--     research's), the component table pins and, for the owned path, every pin of domains/beam_table.lua;
--   * where the game reads the BeamWeapon table: the file's own table, or exactly HD2Runtime's registered copy;
--     ANY other pointer (another mod moved it, e.g. True Lasgun Beam Overhaul) refuses both paths (never chained onto);
--     the ProjectileWeapon and WeaponMagazine slots must be the entity allocation's own tables;
--   * per weapon: its settings row by the game's probe with its count, network type and list place; its
--     ProjectileWeapon row; its magazine row by the game's probe, no other row naming its record; its targets exactly
--     vanilla or applied (a Liberator left in L1 / L2 by LiberatorBeamProof is 'partial', anything else 'foreign');
--   * the table: the Trident's row and record (the copy source) as reviewed in the file; record 23 vanilla or the copy;
--     no row but the experiment's naming one of the weapons or record 23; owned: the copy's rows (other than the
--     three) the file's, each own record the Trident's bytes but for +104..+115;
--   * the crash rules, at the write AND at the restore: ZERO live instances of EVERY weapon written (the descriptor
--     census: ship previews, the armory and your own loadout included); solo (player list + PlayFab lobby, unreadable
--     fails closed); for an apply the Trident's package (laser_shotgun) resident.
-- After a write each weapon is recorded in core/reviewed_edits.lua (its dormant ProjectileWeapon fields and its beam
-- record refused to typed writes: M.configure is the way; everything else writable). A weapon spawned while swapped may
-- leave a ProjectileWeapon private copy nothing removes (the Liberator's default ammunition; a Reprimand muzzle):
-- RESTART THE GAME after using the experiment.
-- Per-weapon beam damage (runtime/experiment_beam_damage.lua) keys on the states this module reports (M.weapon_states,
-- read-only and quiet), with either path; a restore forgets the restored weapons' damage settings.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local log_module=require('hd2runtime/runtime/log')
local edits=require('hd2runtime/core/reviewed_edits')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local D=require('hd2runtime/domains/beam_swap')
local T=require('hd2runtime/domains/beam_table')
local CT=require('hd2runtime/domains/component_tables')
local TB=require('hd2runtime/runtime/experiment_beam_table')
local unpack=unpack or table.unpack
local M={}
M.VERSION='0.3.1-experimental'
M.OWNER='HD2Runtime multi-weapon beam swap experiment'
M.PATHS={owned='owned table',shared='shared record'}
local PRIVATE,COMMIT,READONLY,PAGE=0x20000,0x1000,0x2,4096
local BW,MG,MZ,PJ=D.beam,D.manager,D.magazine,D.projectile
local TRIDENT=D.trident
local BY={}
M.WEAPONS={}
for _,w in ipairs(D.weapons)do BY[w.id]=w;M.WEAPONS[#M.WEAPONS+1]=w.id end
local SETTING={}
M.SETTINGS={}
for _,s in ipairs(T.settings)do SETTING[s.id]=s;M.SETTINGS[#M.SETTINGS+1]=s end
local SETTINGS_FROM,SETTINGS_TO=104,116        -- the members M.configure writes (+104..+115)
local DONOR=b.unhex(BW.recordAfter)              -- the Trident's record 18 (the reviewed copy source)
local proven={}             -- world key -> true | reason
local used=false            -- a swap was applied this session: the game must be restarted afterwards
local hooks={}              -- tests only: census / solo / assets overrides
local settings={}           -- weapon id -> {fire_rate, pulse_beams, pulse_seconds} (nil members: the Trident's)

local function log(text)log_module.emit('MULTI BEAM: '..text)end
local function clean(why)return(tostring(why):gsub('^%[string "[^"]*"%]:%d+: ',''):gsub('^[^%s:]+:%d+: ',''))end
local function fail(text)error(text,0)end
local hexs=b.hex

local function refuse_projectile(w)
    return('MULTI BEAM EXPERIMENT: the %s\'s ProjectileWeapon component is dormant while the experimental beam swap is '
        ..'applied (its list no longer names it); writes to its fire rate, projectile, ammunition and the rows they '
        ..'link to are refused until the swap is restored (owner: HD2Runtime experiment)'):format(w.name)
end
M.REFUSE_BEAM='MULTI BEAM EXPERIMENT: BeamWeapon record 23 (the shared Trident copy) belongs to the experimental beam '
    ..'swap; writes to it are refused (owner: HD2Runtime experiment)'
local function refuse_owned(w)
    return('MULTI BEAM EXPERIMENT: BeamWeapon record %d (the %s\'s own Trident copy in HD2Runtime\'s owned table) '
        ..'belongs to the experimental beam swap; set its rate and pulse with the experiment (configure), typed writes '
        ..'are refused (owner: HD2Runtime experiment)'):format(T.records[w.id],w.name)
end

-- Every pin of the shared path, exact bytes, once per proven world (game.dll base). The owned path also needs
-- experiment_beam_table.prove (domains/beam_table.lua).
local function prove(world)
    local key=world.key
    if proven[key]==true then return true end
    if proven[key]then return nil,proven[key]end
    local why
    if D.source.gameDllSha256~=profile.dll_sha or CT.source.gameDllSha256~=profile.dll_sha then
        why='the research covers another game.dll build'
    end
    local lists={D.pins,CT.pins,CT.lookups[BW.component]or{},CT.lookups[PJ.component]or{},CT.lookups[MZ.component]or{}}
    for _,list in ipairs(lists)do
        for _,pin in ipairs(list)do
            if not why and not world.view.proves(world.game+pin.rva,pin.hex)then
                why=('native code not as reviewed at game.dll+0x%X (%s)'):format(pin.rva,pin.label)
            end
        end
    end
    proven[key]=why or true
    if why then return nil,why end
    return true
end
M.prove=function(world)return prove(world)end

local function region(world,at)
    local r=world.runtime.query(at)
    if not(r and r.state==COMMIT and r.type==PRIVATE and r.allocation_base and r.allocation_base>0
        and at>=r.base and at<r.base+r.size)then
        return nil
    end
    return r
end

-- The component's table as the game reads it, proven to be the entity allocation's own (allocation + offset + 28).
local function component_table(world,manager,base,name)
    local c=assert(profile.components[name],'unknown component '..name)
    local at=world.view.pointer(manager+CT.slotBase+8*c.index)
    if at~=base+c.offset+CT.tableFromProfileOffset then
        fail('CONFLICT: the game reads its '..name..' table from another place (another mod moved it)')
    end
    local framing=world.view.read(at-32,32)
    if not(framing and b.u32(framing,0)==c.index and framing:sub(5,32)==b.unhex(c.header))then
        fail(name..' framing changed')
    end
    return at,c
end

local ZERO8=string.rep('\0',8)
local ZERO16=string.rep('\0',16)

-- A weapon's row in the owned copy: its key, its own record, flags 0.
local function owned_row(w)return b.unhex(w.beam.rowAfter):sub(1,8)..b.encode(T.records[w.id],'u32')..b.encode(0,'u32')end
-- The settings of a weapon as bytes +104..+115 (the Trident's where a member is not set).
local function settings_bytes(id)
    local s=settings[id]or{}
    local x=DONOR:sub(SETTINGS_FROM+1,SETTINGS_TO)
    local out={}
    for i,def in ipairs(T.settings)do
        local at=def.offset-SETTINGS_FROM
        out[i]=s[def.id]~=nil and b.encode(s[def.id],def.storage)or x:sub(at+1,at+4)
    end
    return table.concat(out)
end
-- The record a weapon's own record must hold for its settings: the Trident's bytes, +104..+115 its settings.
local function owned_record(id)
    return DONOR:sub(1,SETTINGS_FROM)..settings_bytes(id)..DONOR:sub(SETTINGS_TO+1)
end
local function decode_settings(record)
    local out={}
    for _,def in ipairs(T.settings)do out[def.id]=b.value(record,def.offset,def.storage)end
    return out
end

-- One weapon's targets, re-derived and checked; returns its located state or raises.
local function locate_weapon(world,s,w,mrows)
    local L={w=w}
    -- Its ProjectileWeapon row stays (it is never written).
    local prow=world.view.read(s.ptable+w.projectile.row*16,16)
    if not(prow and b.resource(prow,0)==w.resource and b.u32(prow,8)==w.projectile.record and b.u32(prow,12)==0)then
        fail('CONFLICT: the '..w.name..'\'s ProjectileWeapon row is not as reviewed')
    end
    -- Its EntitySettings row by the game's own probe (home = resource & 0xFFF).
    local found
    local at=w.membership.home
    for _=1,D.membership.rows do
        local key=world.view.read(s.esh+at*D.membership.rowStride,8)
        if not key then fail('TARGET_UNAVAILABLE: the entity map is unreadable')end
        if key==ZERO8 then break end
        if b.resource(key,0)==w.resource then found=at;break end
        at=(at+1)%D.membership.rows
    end
    if found~=w.membership.row then
        fail(('the %s\'s entity map row is not row %d (found %s)'):format(w.name,w.membership.row,tostring(found)))
    end
    local row_settings=world.view.read(s.esh+found*D.membership.rowStride,D.membership.rowStride)
    local list=b.pointer(row_settings,8)
    if not(b.u32(row_settings,16)==w.membership.count and b.u32(row_settings,20)==0
        and b.u32(row_settings,24)==w.membership.networkType)then
        fail('the '..w.name..'\'s entity map row (count, network type) is not as reviewed')
    end
    if list-s.esh~=w.membership.listOffsetInBody then
        fail('CONFLICT: the '..w.name..'\'s membership list is not at its reviewed place (another mod moved it)')
    end
    local count=w.membership.count
    L.list=list
    L.list_bytes=world.view.read(list,count*2)
    if not L.list_bytes then fail('TARGET_UNAVAILABLE: the '..w.name..'\'s membership list is unreadable')end
    local first=list+w.membership.firstChanged
    if first%2~=0 then fail('the '..w.name..'\'s membership list is not u16-aligned')end
    local finish=list+w.membership.endChanged
    L.window=first-first%4
    L.window_size=finish+(-finish)%4-L.window
    if L.window_size~=8 and L.window_size~=12 then fail('the '..w.name..'\'s list window is not 8 or 12 bytes')end
    if L.window%PAGE+L.window_size>PAGE then fail('the '..w.name..'\'s list window crosses a page')end
    L.list_context_at=list-16
    L.list_context=world.view.read(L.list_context_at,count*2+48)
    if not L.list_context then fail('TARGET_UNAVAILABLE: the '..w.name..'\'s membership list context is unreadable')end
    -- Its BeamWeapon row in the file's table.
    L.row_at=s.table+w.beam.rowOffset
    L.row_bytes=s.table_bytes:sub(w.beam.rowOffset+1,w.beam.rowOffset+16)
    -- Owned: its row and its own record in the copy.
    if s.tb.mode=='owned'then
        L.crow_at=s.ctable+w.beam.rowOffset
        L.crow_bytes=s.copy_bytes:sub(w.beam.rowOffset+1,w.beam.rowOffset+16)
        L.crecord_index=T.records[w.id]
        L.crecord_at=s.ctable+BW.recordBase+L.crecord_index*BW.recordStride
        L.crecord=s.copy_bytes:sub(BW.recordBase+L.crecord_index*BW.recordStride+1,
            BW.recordBase+(L.crecord_index+1)*BW.recordStride)
    end
    -- Its magazine (magazine weapons): row by the game's probe (home = resource mod 540, key 0 stops), its record named
    -- by no other row, the chamber window.
    local mz=w.magazine
    if mz then
        local mfound
        local mat=mz.home
        for _=1,MZ.capacity do
            local key=mrows:sub(mat*16+1,mat*16+8)
            if key==ZERO8 then break end
            if b.resource(key,0)==w.resource then mfound=mat;break end
            mat=(mat+1)%MZ.capacity
        end
        if mfound~=mz.row then
            fail(('the %s\'s WeaponMagazine row is not row %d (found %s)'):format(w.name,mz.row,tostring(mfound)))
        end
        if hexs(mrows:sub(mz.row*16+1,mz.row*16+16))~=mz.rowBytes then
            fail('CONFLICT: the '..w.name..'\'s WeaponMagazine row is not as reviewed (another mod changed it)')
        end
        for n=0,MZ.capacity-1 do
            local raw=mrows:sub(n*16+1,n*16+16)
            if n~=mz.row and raw:sub(1,8)~=ZERO8 and b.u32(raw,8)==mz.record then
                fail(('CONFLICT: another WeaponMagazine row names record %d (the %s\'s)'):format(mz.record,w.name))
            end
        end
        L.mrecord_at=s.mtable+MZ.recordBase+mz.record*MZ.recordStride
        L.mrecord=world.view.read(L.mrecord_at,MZ.recordStride)
        if not L.mrecord then fail('TARGET_UNAVAILABLE: the '..w.name..'\'s magazine record is unreadable')end
        L.chamber_at=s.mtable+mz.windowOffset
        L.chamber=hexs(L.mrecord:sub(MZ.window+1,MZ.window+4))
    end
    -- Pages: every entity-file target in the entity allocation's read-only memory.
    local extents={{L.row_at,16},{L.window,L.window_size}}
    if mz then extents[#extents+1]={L.chamber_at,4}end
    L.tops={}
    for _,extent in ipairs(extents)do
        local q=region(world,extent[1])
        if not(q and q.allocation_base==s.base and q.protect==READONLY and extent[1]+extent[2]<=q.base+q.size)then
            fail('a target page of the '..w.name..' is not in the entity allocation\'s read-only memory')
        end
        if extent[1]%4~=0 or extent[1]%PAGE+extent[2]>PAGE then
            fail('a target of the '..w.name..' crosses a page or is misaligned')
        end
        L.tops[#L.tops+1]=q.base+q.size
    end
    local lr=region(world,list)
    if lr then L.tops[#L.tops+1]=lr.base+lr.size end
    -- The state.
    local rb,lb=hexs(L.row_bytes),hexs(L.list_bytes)
    local row=rb==w.beam.rowBefore and'vanilla'or rb==w.beam.rowAfter and'swapped'or'FOREIGN'
    local lst=lb==w.membership.before and'vanilla'or lb==w.membership.after and'swapped'or'FOREIGN'
    local mag='n/a'
    if mz then mag=L.chamber==mz.before and'1 (vanilla)'or L.chamber==mz.after and'0 (no chamber)'or'FOREIGN'end
    local mag_before=not mz or L.chamber==mz.before
    local mag_after=not mz or L.chamber==mz.after
    local crow='n/a'
    if s.tb.mode=='owned'then
        crow=L.crow_bytes==ZERO16 and'empty'or L.crow_bytes==owned_row(w)and'own record '..L.crecord_index or'FOREIGN'
        -- Its own record: the Trident's bytes but for its settings (+104..+115).
        L.crecord_ok=L.crecord:sub(1,SETTINGS_FROM)==DONOR:sub(1,SETTINGS_FROM)
            and L.crecord:sub(SETTINGS_TO+1)==DONOR:sub(SETTINGS_TO+1)
        if not L.crecord_ok then crow=crow..', record FOREIGN'end
    end
    if s.tb.mode=='owned'then
        if row=='vanilla'and crow=='empty'and lst=='vanilla'and mag_before then L.state='vanilla'
        elseif row=='vanilla'and crow=='own record '..L.crecord_index and lst=='swapped'and mag_after then
            L.state='applied';L.path='owned'
        else L.state='foreign'end
    else
        if row=='vanilla'and lst=='vanilla'and mag_before then L.state='vanilla'
        elseif row=='swapped'and lst=='swapped'and mag_after then L.state='applied';L.path='shared'
        elseif row=='swapped'and mz and mag_before and(lst=='vanilla'or lst=='swapped')then L.state='partial'
        -- Its list still swapped but no row in the table the game reads (an owned copy that died): restore puts the
        -- list and the magazine byte back.
        elseif row=='vanilla'and lst=='swapped'and mag_after then L.state='orphaned'
        else L.state='foreign'end
    end
    L.detail=('row %d %s%s, list %s, magazine chamber %s'):format(w.beam.row,row,
        s.tb.mode=='owned'and(' (copy: '..crow..')')or'',lst,mag)
    return L
end

-- Everything the writes and the restore need, re-derived and checked. Returns the located state or raises.
local function locate(world)
    local tb=TB.locate(world)
    if tb.mode=='foreign'then fail('REFUSED: '..tb.reason)end
    local manager,base=tb.manager,tb.base
    local s={manager=manager,base=base,esh=base+28,weapons={},tb=tb}
    local c=assert(profile.components[BW.component],'BeamWeapon profile component')
    assert(c.index==BW.index and c.indices==BW.capacity and c.records==BW.records and c.stride==BW.recordStride
        and c.record_offset==BW.recordBase,'BeamWeapon schema differs from the research')
    s.table=tb.original
    s.table_bytes=tb.file
    local pc
    s.ptable,pc=component_table(world,manager,base,PJ.component)
    assert(pc.index==PJ.index,'ProjectileWeapon index differs from the research')
    local mc
    s.mtable,mc=component_table(world,manager,base,MZ.component)
    assert(mc.index==MZ.index and mc.indices==MZ.capacity and mc.records==MZ.records and mc.stride==MZ.recordStride
        and mc.record_offset==MZ.recordBase,'WeaponMagazine schema differs from the research')
    local function row(n)return s.table_bytes:sub(n*16+1,n*16+16)end
    local trident=row(BW.tridentRow)
    if b.resource(trident,0)~=TRIDENT or b.u32(trident,8)~=BW.tridentRecord or b.u32(trident,12)~=0 then
        fail('CONFLICT: BeamWeapon row '..BW.tridentRow..' is not the Trident\'s (another mod changed it)')
    end
    local source=s.table_bytes:sub(BW.recordBase+BW.tridentRecord*BW.recordStride+1,
        BW.recordBase+(BW.tridentRecord+1)*BW.recordStride)
    if source~=DONOR then
        fail('CONFLICT: the Trident\'s BeamWeapon record differs from the reviewed copy source (another mod changed it)')
    end
    -- No row but each weapon's own names one of the weapons, or record 23.
    local own_row,by_resource={},{}
    for _,w in ipairs(D.weapons)do own_row[w.beam.row]=w;by_resource[w.resource]=w end
    for n=0,BW.capacity-1 do
        if not own_row[n]then
            local raw=row(n)
            local key=b.resource(raw,0)
            if by_resource[key]then fail('CONFLICT: another BeamWeapon row already names the '..by_resource[key].name)end
            if raw:sub(1,8)~=ZERO8 and b.u32(raw,8)==BW.record then
                fail('CONFLICT: another BeamWeapon row already names record '..BW.record)
            end
        end
    end
    s.record_at=s.table+BW.recordOffset
    local rec=hexs(s.table_bytes:sub(BW.recordOffset+1,BW.recordOffset+BW.recordStride))
    s.record=rec==BW.recordBefore and'vanilla'or rec==BW.recordAfter and'copy'or'foreign'
    local q=region(world,s.record_at)
    if not(q and q.allocation_base==base and q.protect==READONLY and s.record_at+BW.recordStride<=q.base+q.size
        and s.record_at%4==0)then
        fail('the BeamWeapon record 23 page is not in the entity allocation\'s read-only memory')
    end
    local tops={q.base+q.size}
    -- Owned: the copy, and how far it drifted from the file (rows other than the three; records 0..23).
    s.drift={}
    if tb.mode=='owned'then
        s.ctable,s.copy_bytes,s.entry=tb.entry.table,tb.copy,tb.entry
        if tb.entry.records~=BW.records+#D.weapons then fail('HD2Runtime\'s BeamWeapon copy has another record count')end
        for n=0,BW.capacity-1 do
            if not own_row[n]and s.copy_bytes:sub(n*16+1,n*16+16)~=row(n)then
                fail('CONFLICT: row '..n..' of HD2Runtime\'s BeamWeapon copy differs from the file (not the '
                    ..'experiment\'s change): restart the game')
            end
        end
        for r=0,BW.records-1 do
            local at=BW.recordBase+r*BW.recordStride
            if s.copy_bytes:sub(at+1,at+BW.recordStride)~=s.table_bytes:sub(at+1,at+BW.recordStride)then
                s.drift[#s.drift+1]=r
            end
        end
        if s.record~='vanilla'then
            fail('REFUSED: record 23 of the file is not vanilla while the owned table is live (mixed paths)')
        end
    end
    s.mrows=world.view.read(s.mtable,MZ.capacity*MZ.rowStride)
    if not s.mrows then fail('TARGET_UNAVAILABLE: the WeaponMagazine table is unreadable')end
    local rows_named=0
    for _,w in ipairs(D.weapons)do
        local L=locate_weapon(world,s,w,s.mrows)
        s.weapons[w.id]=L
        for _,top in ipairs(L.tops)do tops[#tops+1]=top end
        if L.state=='applied'and L.path=='shared'or L.state=='partial'then rows_named=rows_named+1 end
    end
    if rows_named>0 and s.record~='copy'then s.record_conflict=true end
    s.owner={base=base,size=math.max(unpack(tops))-base,type=PRIVATE,protect=READONLY}
    s.path=tb.mode=='owned'and'owned'or(s.record=='copy'or rows_named>0)and'shared'or nil
    local parts={}
    for _,w in ipairs(D.weapons)do parts[#parts+1]=w.name..': '..s.weapons[w.id].state end
    s.detail=('path %s; table %s; record 23 %s; %s'):format(s.path and M.PATHS[s.path]or'none',
        tb.mode=='owned'and'HD2Runtime\'s copy'or'the file\'s own',s.record=='copy'and'Trident copy'
        or s.record=='vanilla'and'vanilla'or'FOREIGN',table.concat(parts,', '))
    return s
end

-- Live entities of each weapon type (and of the Trident, for the log) in the descriptor table.
local function census(world,manager)
    if hooks.census then return hooks.census(world,manager)end
    local invalid=world.view.u32(world.game+MG.invalidEntity)
    local raw=world.view.read(manager+MG.descriptors,MG.descriptorStride*MG.descriptorCount)
    if not(invalid and raw)then return nil,'the entity descriptor table is unreadable'end
    local out={live=0,tridents=0}
    local by={}
    for _,w in ipairs(D.weapons)do out[w.id]=0;by[w.resource]=w.id end
    for k=0,MG.descriptorCount-1 do
        local at=k*MG.descriptorStride
        if b.u32(raw,at+MG.descriptorEntity)~=invalid and(b.u32(raw,at)~=0 or b.u32(raw,at+4)~=0)then
            out.live=out.live+1
            local kind=b.resource(raw,at)
            if by[kind]then out[by[kind]]=out[by[kind]]+1 elseif kind==TRIDENT then out.tridents=out.tridents+1 end
        end
    end
    return out
end
M.census=function(world,manager)return census(world,manager)end

-- Solo: one player in the game's list, and no lobby or a lobby of this machine alone. Anything unreadable fails closed.
local function solo(world)
    if hooks.solo then return hooks.solo(world)end
    local players=world_module.players(world)or{}
    if#players>1 then return false,#players..' players in the game\'s player list'end
    local channel=require('hd2runtime/runtime/peer_channel')
    local ok,why=channel.prove(world)
    if not ok then return false,'the lobby state cannot be proven ('..tostring(why)..')'end
    local lobby,code,reason=channel.lobby(world)
    if lobby then
        if#lobby.members>1 then return false,#lobby.members..' lobby members (solo only)'end
        return true,'a lobby of 1 (this machine)'
    end
    if code=='NOT_JOINED'or code=='NO_SESSION'then return true,'no lobby ('..tostring(reason)..')'end
    return false,'the lobby state is unreadable ('..tostring(code)..': '..tostring(reason)..')'
end

-- The Trident's package (laser_shotgun): 'resident' | 'loading' | 'queued' | 'absent' | 'unknown', reason.
local function assets_state(world)
    if hooks.assets then return hooks.assets(world)end
    local assets=require('hd2runtime/core/assets')
    local dep=assets.dependency('player_weapon/LAS-13 Trident')
    if not(dep and tostring(dep.name):find('laser_shotgun',1,true))then return'unknown','no catalogued Trident package'end
    local ok,state=pcall(assets.state,world.runtime,dep.package)
    if not ok then return'unknown',clean(state)end
    return state,dep.name
end

local function open()
    local world,why=world_module.open()
    if not world then fail('TARGET_UNAVAILABLE: '..tostring(why))end
    local ok,reason=prove(world)
    if not ok then fail('UNPROVEN: '..reason)end
    return world
end

-- core/reviewed_edits.lua: an applied weapon's exact state (its list, its rows), or nothing.
local function record_edit(w,L)
    local state=L.state
    if state=='applied'then
        local owned_path=L.path=='owned'
        local rows={[BW.component]={row=w.beam.row,record=owned_path and T.records[w.id]or BW.record},
            [PJ.component]={row=w.projectile.row,record=w.projectile.record}}
        if w.magazine then rows[MZ.component]={row=w.magazine.row,record=w.magazine.record}end
        edits.set(w.resource,{owner=M.OWNER,stage='applied',
            membership=b.unhex(w.membership.after),rows=rows,absent={[PJ.component]=true},
            refuse={[PJ.component]=refuse_projectile(w),[BW.component]=owned_path and refuse_owned(w)or M.REFUSE_BEAM}})
    elseif state=='vanilla'then
        local e=edits.get(w.resource)
        if e and e.owner==M.OWNER then edits.clear(w.resource)end
    end
end
local function record_edits(s)for _,w in ipairs(D.weapons)do record_edit(w,s.weapons[w.id])end end

-- The list window's bytes for a membership list hex (bytes past the list, the next list's first entry, kept).
local function list_window_bytes(world,L,hex)
    local list=b.unhex(hex)
    local cur=world.view.read(L.window,L.window_size)
    if not cur then fail('TARGET_UNAVAILABLE: the '..L.w.name..'\'s membership list is unreadable')end
    local offset=L.window-L.list
    local inside=list:sub(offset+1,math.min(offset+L.window_size,#list))
    return inside..cur:sub(#inside+1)
end

-- A change: {label, address, before, desired, owner (nil: the entity allocation)}.
-- The list and magazine changes of one weapon, in write order (forward) or restore order.
local function list_changes(world,L,forward)
    local w=L.w
    local x,y=list_window_bytes(world,L,w.membership.before),list_window_bytes(world,L,w.membership.after)
    local out={{w.id..'.membership_list+'..(L.window-L.list),L.window,forward and x or y,forward and y or x}}
    if w.magazine then
        local mx,my=b.unhex(w.magazine.before),b.unhex(w.magazine.after)
        local mag={w.id..'.magazine'..w.magazine.record..'+'..MZ.window,L.chamber_at,forward and mx or my,
            forward and my or mx}
        if forward then out[#out+1]=mag else table.insert(out,1,mag)end
    end
    return out
end
-- A 16-byte row as two 8-byte changes (record index first when it appears, key first when it goes).
local function row_changes(prefix,at,before,after,forward,owner)
    local out={}
    local function half(i,label)
        local x,y=before:sub(i+1,i+8),after:sub(i+1,i+8)
        out[#out+1]={prefix..'.'..label,at+i,forward and x or y,forward and y or x,owner}
    end
    if forward then half(8,'record');half(0,'key')else half(0,'key');half(8,'record')end
    return out
end
-- Shared path: one weapon's changes (row in the file's table, list, magazine).
local function weapon_changes(world,L,forward)
    local w=L.w
    local row=row_changes(w.id..'.row'..w.beam.row,L.row_at,b.unhex(w.beam.rowBefore),b.unhex(w.beam.rowAfter),forward)
    local lists=list_changes(world,L,forward)
    local out={}
    if forward then
        for _,c in ipairs(row)do out[#out+1]=c end
        for _,c in ipairs(lists)do out[#out+1]=c end
    else
        for _,c in ipairs(lists)do out[#out+1]=c end
        for _,c in ipairs(row)do out[#out+1]=c end
    end
    return out
end
-- Owned path, the copy live: one weapon's own record settings (+104..+115, only the 4-byte members that differ).
local function settings_changes(s,L,owner)
    local out={}
    local want=owned_record(L.w.id)
    for at=SETTINGS_FROM,SETTINGS_TO-4,4 do
        local x,y=L.crecord:sub(at+1,at+4),want:sub(at+1,at+4)
        if x~=y then
            out[#out+1]={('%s.record%d+%d'):format(L.w.id,L.crecord_index,at),L.crecord_at+at,x,y,owner}
        end
    end
    return out
end

local function record_changes(s,forward)
    local out={}
    local x,y=b.unhex(BW.recordBefore),DONOR
    for i=0,BW.recordStride-4,4 do
        local p,q=x:sub(i+1,i+4),y:sub(i+1,i+4)
        if p~=q then out[#out+1]={('record23+%d'):format(i),s.record_at+i,forward and p or q,forward and q or p}end
    end
    return out
end

-- One guarded transaction (all or nothing): changes = {{label, address, before, desired, owner}} in write order;
-- extra = additional contexts {{owner, address, bytes}} (the copy, the slot).
local function run(world,s,label,changes,targets,extra)
    local plan={snapshots={{owner=s.owner,offset=s.table-s.base,bytes=s.table_bytes}},changes={}}
    for _,L in ipairs(targets)do
        plan.snapshots[#plan.snapshots+1]={owner=s.owner,offset=L.list_context_at-s.base,bytes=L.list_context}
        if L.mrecord then
            plan.snapshots[#plan.snapshots+1]={owner=s.owner,offset=L.mrecord_at-s.base,bytes=L.mrecord}
        end
    end
    for _,x in ipairs(extra or{})do
        plan.snapshots[#plan.snapshots+1]={owner=x[1],offset=x[2]-x[1].base,bytes=x[3]}
    end
    for _,c in ipairs(changes)do
        if c[3]~=c[4]then
            local owner=c[5]or s.owner
            plan.changes[#plan.changes+1]={label='beam_swap.'..c[1],owner=owner,offset=c[2]-owner.base,
                expected=c[3],desired=c[4],before=c[3],already_desired=false,packed=c[2]%4~=0 or nil,
                identity={component='EntitySettings',component_type='native',record_type='experiment',
                    unique_owner=true,owner_count=1},chain={}}
        end
    end
    if#plan.changes==0 then return{status='ALREADY_DESIRED',writes=0}end
    local report=transaction.apply(world.runtime,plan)
    log(('%s: %s, %d write%s, %d bytes, protection changes %d, rollback %s; %s'):format(label,report.status,
        report.writes,report.writes==1 and''or's',report.bytes_written,report.protection_changes,
        tostring(report.rollback),table.concat(transaction.report_lines(report),' ')))
    if report.status~='APPLIED'then
        fail('the guarded write was refused (nothing is left written: rollback '..tostring(report.rollback)..'): '
            ..tostring(report.reason))
    end
    return report
end

-- ids: a list of weapon ids, or nil for every weapon.
local function select_ids(ids)
    if ids==nil then return {unpack(D.order)}end
    assert(type(ids)=='table'and#ids>=1,'weapons must be a non-empty list of '..table.concat(D.order,', '))
    local want={}
    for _,id in ipairs(ids)do
        assert(BY[id],'unknown weapon '..tostring(id)..' (one of '..table.concat(D.order,', ')..')')
        want[id]=true
    end
    local out={}
    for _,id in ipairs(D.order)do if want[id]then out[#out+1]=id end end
    return out
end

local function names(ids)
    local out={}
    for _,id in ipairs(ids)do out[#out+1]=BY[id].name end
    return#out>0 and table.concat(out,', ')or'none'
end

-- The gates of a write or a restore: zero live instances of every weapon in ids, solo, and (apply) the package.
local function gates(world,s,ids,apply)
    local count,why=census(world,s.manager)
    if not count then fail('REFUSED: '..why)end
    local live={}
    for _,id in ipairs(ids)do
        if(count[id]or 0)>0 then live[#live+1]=('%d live %s'):format(count[id],BY[id].name)end
    end
    if#live>0 then
        fail('REFUSED: '..table.concat(live,', ')..' (the ship preview, the armory or your own loadout): equip other '
            ..'weapons, do not open the armory, and try again')
    end
    local ok,reason=solo(world)
    if not ok then fail('REFUSED: solo only: '..tostring(reason))end
    if apply then
        local state,detail=assets_state(world)
        if state~='resident'then
            fail('REFUSED: the Trident\'s package is '..tostring(state)..' ('..tostring(detail)
                ..'): equip the LAS-13 Trident once, or let the proof\'s hd2.require_assets finish, then try again')
        end
    end
    return count,reason
end

local function guarded(name,fn)
    local ok,result=pcall(fn)
    if ok then return result end
    local why=clean(result)
    log(name..' REFUSED: '..why)
    return {ok=false,reason=why}
end

local function refuse_unusable(s)
    if s.record=='foreign'then fail('REFUSED: BeamWeapon record 23 is in a state the experiment did not make')end
    if s.record_conflict then
        fail('REFUSED: a weapon row names record 23 but the record is not the Trident copy (not the experiment\'s state)')
    end
    for _,w in ipairs(D.weapons)do
        local L=s.weapons[w.id]
        if L.state=='foreign'then
            fail('REFUSED: the '..w.name..' is in a state the experiment did not make ('..L.detail..')')
        elseif L.state=='partial'then
            fail('REFUSED: the '..w.name..' is part-swapped ('..L.detail..'), as LiberatorBeamProof\'s L1 / L2 leave it: '
                ..'restore it with LiberatorBeamProof (Ctrl+Shift+F4) first')
        end
    end
end

-- Whether the owned path can start now: true, or nil and why (read-only).
local function owned_available(world,s)
    if s.tb.mode=='owned'then return true end
    if not s.tb.manager_owner then return nil,s.tb.slot_unwritable end
    local ok,why=TB.available(world)
    if not ok then return nil,why end
    return true
end

-- Read-only: the proof state, per weapon, the live instances, the lobby, the assets, the path.
function M.status()
    return guarded('status',function()
        local world=open()
        local s=locate(world)
        local count,why=census(world,s.manager)
        local is_solo,solo_why=solo(world)
        local asset,asset_why=assets_state(world)
        local can_own,own_why=owned_available(world,s)
        local out={ok=true,proven=true,record=s.record,detail=s.detail,solo=is_solo,solo_reason=solo_why,assets=asset,
            assets_detail=asset_why,census_error=why,live_entities=count and count.live,
            live_tridents=count and count.tridents,restart_required=used,weapons={},
            path=s.path and M.PATHS[s.path]or'none',table=s.tb.mode,owned_available=can_own==true,
            owned_reason=own_why,copies=TB.copies(),drift=#s.drift>0 and s.drift or nil}
        log(('STATUS: pins proven; path %s; the game reads %s; record 23 %s; owned table %s; solo %s (%s); Trident '
            ..'package %s; live entities %s%s%s'):format(out.path,s.tb.mode=='owned'and'HD2Runtime\'s copy'
            or'the file\'s own table',s.record=='copy'and'Trident copy'or s.record,
            can_own and('available ('..TB.copies()..' built)')or('UNAVAILABLE: '..tostring(own_why)),tostring(is_solo),
            tostring(solo_why),tostring(asset),tostring(out.live_entities),
            #s.drift>0 and('; records changed in the copy since the switch: '..table.concat(s.drift,', '))or'',
            used and'; RESTART THE GAME after this session (the swap was used)'or''))
        for _,w in ipairs(D.weapons)do
            local L=s.weapons[w.id]
            local e=edits.get(w.resource)
            local entry={id=w.id,name=w.name,state=L.state,detail=L.detail,live=count and count[w.id],
                recorded=e and e.stage or nil,path=L.path and M.PATHS[L.path]or nil}
            if L.state=='applied'and L.path=='owned'then entry.settings=decode_settings(L.crecord)
            elseif L.state=='applied'then entry.settings=decode_settings(DONOR)end
            out.weapons[#out.weapons+1]=entry
            log(('%s: %s%s (%s); live %s; recorded edit %s%s'):format(w.name,L.state,
                entry.path and(' ['..entry.path..']')or'',L.detail,tostring(entry.live),tostring(entry.recorded),
                entry.settings and(' ; beam %d rpm, %d per pulse, %.3g s'):format(entry.settings.fire_rate,
                    entry.settings.pulse_beams,entry.settings.pulse_seconds)or''))
        end
        return out
    end)
end

-- Read-only and quiet (no log line): {liberator = 'vanilla' | 'applied' | 'partial' | 'orphaned' | 'foreign', ...},
-- or nil and why. The second result names the active path ('owned' | 'shared' | nil).
function M.weapon_states()
    local ok,result,path=pcall(function()
        local world=open()
        local s=locate(world)
        local out={}
        for _,w in ipairs(D.weapons)do out[w.id]=s.weapons[w.id].state end
        return out,s.path
    end)
    if ok then return result,path end
    return nil,clean(result)
end

-- Owned path, the table still the file's: build the copy with every target's row and every weapon's own record, then
-- ONE transaction: the slot (the copy goes live), then each target's list and magazine byte.
local function apply_owned_switch(world,s,targets,targets_ids)
    local rows,records={},{}
    for _,L in ipairs(targets)do rows[L.w.beam.row]=owned_row(L.w)end
    for _,w in ipairs(D.weapons)do records[T.records[w.id]]=owned_record(w.id)end
    local entry=TB.build(world,s.tb,rows,records)
    local slot=TB.slot_change(s.tb,entry,true)
    local copy_owner={base=entry.allocation,size=entry.size,type=PRIVATE,protect=READONLY}
    local copy=world.view.read(entry.allocation,T.layout.size)
    local changes={{'slot270 := HD2Runtime\'s copy',s.tb.slot_at,slot.before,slot.desired,s.tb.manager_owner}}
    for _,L in ipairs(targets)do
        for _,c in ipairs(list_changes(world,L,true))do changes[#changes+1]=c end
    end
    local report=run(world,s,('apply, owned table (slot 270 := the new copy, then lists, magazine bytes of %s)')
        :format(names(targets_ids)),changes,targets,{{s.tb.manager_owner,s.tb.slot_at,slot.before},
        {copy_owner,entry.allocation,copy}})
    TB.register(entry)
    return report
end

-- Owned path, the copy live: each target's settings, row (record index, then key), list and magazine byte.
local function apply_owned_live(world,s,targets)
    local copy_owner=s.tb.copy_owner
    local changes={}
    for _,L in ipairs(targets)do
        for _,c in ipairs(settings_changes(s,L,copy_owner))do changes[#changes+1]=c end
        for _,c in ipairs(row_changes(L.w.id..'.copyrow'..L.w.beam.row,L.crow_at,ZERO16,owned_row(L.w),true,
            copy_owner))do changes[#changes+1]=c end
        for _,c in ipairs(list_changes(world,L,true))do changes[#changes+1]=c end
    end
    return changes,{{copy_owner,s.ctable,s.copy_bytes}}
end

-- Applies the swap to the weapons in ids (nil = all three) in one transaction. opts.path: 'owned' | 'shared' | nil
-- (nil: the active path, else the owned table when available, else the shared record).
function M.apply(ids,opts)
    local want=select_ids(ids)
    opts=opts or{}
    assert(opts.path==nil or M.PATHS[opts.path],'path must be owned or shared')
    return guarded('apply '..names(want),function()
        local world=open()
        local s=locate(world)
        log(('apply %s: proven; %s'):format(names(want),s.detail))
        refuse_unusable(s)
        for _,w in ipairs(D.weapons)do
            if s.weapons[w.id].state=='orphaned'then
                fail('REFUSED: the '..w.name..'\'s list is still swapped but no table row names it (an owned copy that '
                    ..'died): restore it first (Ctrl+Alt+F7)')
            end
        end
        local targets,targets_ids={},{}
        for _,id in ipairs(want)do
            if s.weapons[id].state=='vanilla'then targets[#targets+1]=s.weapons[id];targets_ids[#targets_ids+1]=id end
        end
        record_edits(s)
        if#targets==0 then
            log('apply '..names(want)..': already applied, nothing written')
            return {ok=true,writes=0,applied=want,path=s.path}
        end
        -- The path.
        local path=s.path
        if path and opts.path and opts.path~=path then
            fail('REFUSED: the '..M.PATHS[path]..' path is active; restore every weapon before using the '
                ..M.PATHS[opts.path]..' path')
        end
        if not path then
            if opts.path=='shared'then path='shared'
            else
                local ok,why=owned_available(world,s)
                if ok then path='owned'
                elseif opts.path=='owned'then fail('REFUSED: the owned table is unavailable: '..tostring(why))
                else
                    path='shared'
                    log('the owned table is unavailable ('..tostring(why)..'): the shared record 23 is used (one rate '
                        ..'and pulse for every swapped weapon)')
                end
            end
        end
        local count,solo_why=gates(world,s,targets_ids,true)
        log(('apply %s: gates passed: 0 live %s (%d live entities), solo (%s), Trident package resident; path %s')
            :format(names(targets_ids),names(targets_ids),count.live,solo_why,M.PATHS[path]))
        local report
        if path=='owned'and s.tb.mode=='in_place'then
            report=apply_owned_switch(world,s,targets,targets_ids)
        elseif path=='owned'then
            local changes,extra=apply_owned_live(world,s,targets)
            report=run(world,s,('apply, owned table (settings, copy rows, lists, magazine bytes of %s)')
                :format(names(targets_ids)),changes,targets,extra)
        else
            local changes={}
            if s.record=='vanilla'then for _,c in ipairs(record_changes(s,true))do changes[#changes+1]=c end end
            for _,L in ipairs(targets)do
                for _,c in ipairs(weapon_changes(world,L,true))do changes[#changes+1]=c end
            end
            report=run(world,s,('apply, shared record (%srows, lists, magazine bytes of %s)'):format(
                s.record=='vanilla'and'record 23 := Trident record 18, then 'or'',names(targets_ids)),changes,targets)
        end
        used=true
        s=locate(world)
        for _,id in ipairs(targets_ids)do
            if s.weapons[id].state~='applied'then
                fail('after the write the '..BY[id].name..' is '..s.weapons[id].state..' ('..s.weapons[id].detail..')')
            end
        end
        if path=='shared'and s.record~='copy'then fail('after the write record 23 is '..s.record)end
        if path=='owned'and s.tb.mode~='owned'then fail('after the write the game does not read the owned copy')end
        record_edits(s)
        local after=census(world,s.manager)
        for _,id in ipairs(targets_ids)do
            local w,L=BY[id],s.weapons[id]
            local set=path=='owned'and decode_settings(L.crecord)or decode_settings(DONOR)
            log(('%s APPLIED [%s]: row %d -> record %d (%s), list %s%s; spawned from now on it fires Trident pulses '
                ..'at %d rpm, %d beams per pulse, %.3g s%s. Live after the write: %s'):format(w.name,M.PATHS[path],
                w.beam.row,path=='owned'and T.records[id]or BW.record,path=='owned'and'its own Trident copy'
                or'the shared Trident copy','BeamWeapon in, ProjectileWeapon out',
                w.magazine and(', magazine record '..w.magazine.record..' +156 = 0 (no chamber)')or'',
                set.fire_rate,set.pulse_beams,set.pulse_seconds,
                w.magazine and', one round per pulse, reload to a full magazine'or', heat per pulse, heat sinks',
                tostring(after and after[id])))
        end
        log('APPLIED ('..s.detail..'). Solo only; restore with zero live swapped weapons, then RESTART THE GAME')
        return {ok=true,writes=report.writes,applied=targets_ids,path=path}
    end)
end

-- Restores the weapons in ids (nil = every applied weapon) in one transaction, in reverse order. Shared path: record 23
-- last, once no weapon row names it. Owned path: each weapon's magazine byte, list and copy row; the last weapon's
-- restore puts the slot back to the file's own table instead (the copy stays allocated, never freed). A weapon left
-- 'orphaned' (its list swapped, no row in the table the game reads) gets its magazine byte and list back.
function M.restore(ids)
    local want=select_ids(ids)
    return guarded('restore '..names(want),function()
        local world=open()
        local s=locate(world)
        log(('restore %s: proven; %s'):format(names(want),s.detail))
        refuse_unusable(s)
        local targets,targets_ids={},{}
        for i=#D.order,1,-1 do
            local id=D.order[i]
            for _,x in ipairs(want)do
                local st=s.weapons[id].state
                if x==id and(st=='applied'or st=='orphaned')then
                    targets[#targets+1]=s.weapons[id];targets_ids[#targets_ids+1]=id
                end
            end
        end
        local remaining=0
        for _,w in ipairs(D.weapons)do
            local mine=false
            for _,id in ipairs(targets_ids)do if id==w.id then mine=true end end
            if s.weapons[w.id].state=='applied'and not mine then remaining=remaining+1 end
        end
        local owned_path=s.tb.mode=='owned'
        local record_back=not owned_path and remaining==0 and s.record=='copy'
        local slot_back=owned_path and remaining==0
        if#targets==0 and not record_back and not slot_back then
            record_edits(s)
            log('restore '..names(want)..': already vanilla, nothing written')
            return {ok=true,writes=0,restored={}}
        end
        if slot_back and#s.drift>0 then
            fail('REFUSED: BeamWeapon record'..(#s.drift==1 and' 'or's ')..table.concat(s.drift,', ')..' changed in '
                ..'HD2Runtime\'s copy while it was live (a typed write, e.g. a mod\'s beam.fire_rate): undo that write '
                ..'(turn the mod\'s option off) first, or the game would lose it when it reads the file\'s table again')
        end
        local count,solo_why=gates(world,s,targets_ids,false)
        log(('restore %s: gates passed: 0 live %s (%d live entities), solo (%s)'):format(names(targets_ids),
            names(targets_ids),count.live,solo_why))
        local changes,extra={},nil
        for _,L in ipairs(targets)do
            if owned_path then
                for _,c in ipairs(list_changes(world,L,false))do changes[#changes+1]=c end
                if not slot_back then
                    for _,c in ipairs(row_changes(L.w.id..'.copyrow'..L.w.beam.row,L.crow_at,ZERO16,owned_row(L.w),
                        false,s.tb.copy_owner))do changes[#changes+1]=c end
                end
            elseif L.state=='orphaned'then
                for _,c in ipairs(list_changes(world,L,false))do changes[#changes+1]=c end
            else
                for _,c in ipairs(weapon_changes(world,L,false))do changes[#changes+1]=c end
            end
        end
        if owned_path then
            extra={{s.tb.copy_owner,s.ctable,s.copy_bytes}}
            if slot_back then
                local slot=TB.slot_change(s.tb,s.entry,false)
                changes[#changes+1]={'slot270 := the file\'s own table',s.tb.slot_at,slot.before,slot.desired,
                    s.tb.manager_owner}
                extra[#extra+1]={s.tb.manager_owner,s.tb.slot_at,slot.before}
            end
        end
        if record_back then for _,c in ipairs(record_changes(s,false))do changes[#changes+1]=c end end
        local report=run(world,s,('restore, %s (magazine bytes, lists, rows of %s%s)'):format(
            owned_path and'owned table'or'shared record',names(targets_ids),record_back and', then record 23'
            or slot_back and', then slot 270 := the file\'s own table'or''),changes,targets,extra)
        if slot_back then TB.forget()end
        s=locate(world)
        for _,id in ipairs(targets_ids)do
            if s.weapons[id].state~='vanilla'then
                fail('after the restore the '..BY[id].name..' is '..s.weapons[id].state..' ('..s.weapons[id].detail..')')
            end
        end
        if record_back and s.record~='vanilla'then fail('after the restore record 23 is '..s.record)end
        if slot_back and s.tb.mode~='in_place'then fail('after the restore the game does not read the file\'s table')end
        record_edits(s)
        for _,id in ipairs(targets_ids)do log(BY[id].name..' RESTORED: every byte is vanilla again')end
        local has_damage,damage=pcall(require,'hd2runtime/runtime/experiment_beam_damage')
        if has_damage and#targets_ids>0 then damage.forget(targets_ids,'its swap was restored')end
        log('RESTORED ('..s.detail..')'..(used and'; RESTART THE GAME before playing on (stale ProjectileWeapon '
            ..'copies of swapped weapons may remain until the game exits)'or''))
        return {ok=true,writes=report.writes,restored=targets_ids,record_restored=record_back,slot_restored=slot_back}
    end)
end

-- The pulsed beam's shot interval (research/docs/beam-pulse-rate-F5FEE03DCFDB.md; BeamWeapon update 0x83E200). Per
-- world update (step dt) both instance timers run down; a pulse starts only from "not firing" once the shot timer is
-- <= 0 (then shot timer := 60 / rate, pulse timer := pulse seconds); a running pulse ends in the update its timer
-- reaches <= 0, and the next start is the update after. So, in updates between pulse starts:
--   n = max(ceil(60 / (rate dt)), max(1, ceil(pulse / dt)) + 1),  effective rpm = 60 / (n dt)
-- A pulse that ends in the update after it fired is killed before its first hit phase: hits need pulse > dt.
M.PULSE={reference_fps=60,fit_fps=30}
local function ceil_eps(x)return math.ceil(x-1e-9)end
function M.pulse_updates(rate,pulse,fps)
    local dt=1/fps
    return math.max(ceil_eps(60/(rate*dt)),math.max(1,ceil_eps(pulse/dt))+1)
end
function M.effective_rate(rate,pulse,fps)return 60*fps/M.pulse_updates(rate,pulse,fps)end
-- The longest pulse that never decides the interval: 60 / (2 rate) at any frame rate, 60 / rate - 1 / 30 at any frame
-- rate >= 30 fps; the larger of the two (a longer pulse is the more robust hit).
function M.pulse_limit(rate)
    local interval=60/rate
    return math.max(interval/2,interval-1/M.PULSE.fit_fps)
end
-- The pulse configure() writes for a rate, and why: {pulse_seconds, fitted, explicit, limit, capped, rpm_at_60 (a
-- steady 60 fps), rpm_varying_60, hits_above_fps, notes}. requested = the caller's pulse_seconds (kept, warned when it
-- caps), nil = the donor's (fitted to the limit when it does not fit).
function M.pulse_fit(rate,requested,donor)
    local fps=M.PULSE.reference_fps
    local limit=M.pulse_limit(rate)
    local out={explicit=requested~=nil,limit=limit,notes={}}
    local pulse=requested or donor
    if requested==nil and donor>limit+1e-6 then
        pulse=limit
        out.fitted=true
        out.notes[#out.notes+1]=('pulse fitted to the rate: %.4g s instead of the Trident\'s %.3g s (at %d rpm a %.3g s '
            ..'pulse would cap it at about %d rpm at %d fps: the next pulse starts only the update after the last one '
            ..'ends)'):format(pulse,donor,rate,donor,math.floor(M.effective_rate(rate,donor,fps)+0.5),fps)
    elseif requested~=nil and requested>limit+1e-6 then
        out.capped=true
        out.notes[#out.notes+1]=('WARNING: pulse %.3g s caps %d rpm at about %d rpm at %d fps (the next pulse starts '
            ..'only the update after the last one ends); leave pulse_seconds out to fit it (<= %.4g s)'):format(
            requested,rate,math.floor(M.effective_rate(rate,requested,fps)+0.5),fps,limit)
    end
    out.pulse_seconds=pulse
    out.rpm_at_60=M.effective_rate(rate,pulse,fps)
    -- The shot timer is SET at a start (the overshoot is dropped): with a varying step each interval rounds up by
    -- about half an update on average.
    out.rpm_varying_60=math.min(out.rpm_at_60,60/(60/rate+0.5/fps))
    if not out.capped and out.rpm_varying_60<rate*0.98 then
        out.notes[#out.notes+1]=('note: each interval rounds up to whole updates: expect about %d rpm at a varying '
            ..'%d fps (more at higher frame rates)'):format(math.floor(out.rpm_varying_60+0.5),fps)
    end
    out.hits_above_fps=pulse>0 and 1/pulse or math.huge
    if pulse<=0 then
        out.notes[#out.notes+1]='WARNING: a 0 s pulse ends in the update after it fired, before its first hit: no damage'
    elseif out.hits_above_fps>M.PULSE.fit_fps then
        out.notes[#out.notes+1]=('note: a %.3g s pulse hits only above %d fps (a pulse that ends in the update after it '
            ..'fired is killed before its first hit)'):format(pulse,math.ceil(out.hits_above_fps))
    end
    if rate>20*fps then
        out.notes[#out.notes+1]=('note: above %d rpm the frame rate caps a pulse that hits (one every 3 updates: 20 x '
            ..'fps rpm)'):format(20*fps)
    end
    return out
end

-- Per-weapon beam settings (owned path only: each weapon's own record). values = {fire_rate (rpm, 1..6000),
-- pulse_beams (1..8), pulse_seconds (0..10)}: members not given keep the Trident's; nil or {} = the Trident's. 0.3.1:
-- without pulse_seconds, a rate whose interval the Trident's 0.15 s pulse does not fit gets a fitted pulse
-- (M.pulse_fit: max(60 / (2 rate), 60 / rate - 1 / 30) s, logged); an explicit pulse_seconds is kept and a cap is
-- warned (the live 0.3.0 test: 600 and 900 rpm with 0.15 s pulses fired at about 330-360 rpm). Kept for
-- the session; written at once (one guarded transaction on the copy) when the weapon is applied on the owned path,
-- else at its next owned apply. Records are type data the beam shot reads (+104 and +112 per shot), so no live-instance
-- gate: a live weapon fires its next shots at the new rate. Returns {ok, writes, pending, settings} or {ok=false,
-- reason}.
function M.configure(id,values)
    local w=BY[id]
    if not w then return {ok=false,reason='unknown weapon '..tostring(id)..' (one of '..table.concat(D.order,', ')..')'}end
    values=values or{}
    if type(values)~='table'then return {ok=false,reason='settings must be a table'}end
    local clean_values={}
    for key,value in pairs(values)do
        local def=SETTING[key]
        if not def then return {ok=false,reason='unknown beam setting '..tostring(key)}end
        if type(value)~='number'or value~=value or value<def.min or value>def.max
            or(def.storage=='i32'and value%1~=0)then
            return {ok=false,reason=('%s must be %s from %s to %s (%s)'):format(key,def.storage=='i32'and'a whole number'
                or'a number',tostring(def.min),tostring(def.max),def.unit)}
        end
        if def.storage=='f32'then value=b.value(b.encode(value,'f32'),0,'f32')end
        clean_values[key]=value
    end
    -- The pulse must fit inside the shot interval, or it decides the rate (research/docs/beam-pulse-rate-
    -- F5FEE03DCFDB.md): no pulse_seconds given and the Trident's 0.15 s does not fit -> fitted; an explicit pulse is
    -- kept and a cap is warned.
    local donor=decode_settings(DONOR)
    local fit=M.pulse_fit(clean_values.fire_rate or donor.fire_rate,clean_values.pulse_seconds,donor.pulse_seconds)
    if fit.fitted then clean_values.pulse_seconds=b.value(b.encode(fit.pulse_seconds,'f32'),0,'f32')end
    for _,line in ipairs(fit.notes)do log(w.name..': '..line)end
    settings[id]=next(clean_values)and clean_values or nil
    local function described()
        local set=decode_settings(owned_record(id))
        return set,('%d rpm, %d beams per pulse, %.3g s'):format(set.fire_rate,set.pulse_beams,set.pulse_seconds)
    end
    local result=guarded('configure '..w.name,function()
        local world=open()
        local s=locate(world)
        local L=s.weapons[id]
        local set,text=described()
        if L.state=='applied'and L.path=='shared'then
            fail('REFUSED: the '..w.name..' is applied on the shared record path (record 23, one record for every '
                ..'swapped weapon): kept for its next owned-table apply ('..text..'); restore and apply again')
        end
        if not(L.state=='applied'and L.path=='owned')then
            log(('%s: settings kept (%s): written at its next owned-table apply'):format(w.name,text))
            return {ok=true,writes=0,pending=true,settings=set}
        end
        local changes=settings_changes(s,L,s.tb.copy_owner)
        if#changes==0 then return {ok=true,writes=0,settings=set}end
        local report=run(world,s,('settings of the %s (its own record %d: %s)'):format(w.name,L.crecord_index,text),
            changes,{},{{s.tb.copy_owner,s.ctable,s.copy_bytes}})
        local after=locate(world).weapons[id]
        if after.state~='applied'or after.crecord~=owned_record(id)then
            fail('after the write the '..w.name..'\'s record does not hold its settings')
        end
        log(('%s: beam %s from its next shot (record %d)'):format(w.name,text,L.crecord_index))
        return {ok=true,writes=report.writes,settings=set}
    end)
    result.kept=true      -- the values stay set for the weapon's next owned-table apply, whatever happened now
    result.pulse=fit
    return result
end
-- The settings the weapon's record holds (applied, owned path) or will hold: {fire_rate, pulse_beams, pulse_seconds}.
function M.settings(id)
    assert(BY[id],'unknown weapon '..tostring(id))
    return decode_settings(owned_record(id))
end

-- Tests only.
function M.set_hooks_for_tests(h)hooks=h or{}end
function M.reset_for_tests()
    proven={};used=false;hooks={};settings={}
    for _,w in ipairs(D.weapons)do edits.clear(w.resource)end
    TB.reset_for_tests()
end
return M
