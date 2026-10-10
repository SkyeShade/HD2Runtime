-- MULTI-WEAPON BEAM SWAP EXPERIMENT (EXPERIMENTAL, SOLO ONLY; branch exp/multi-beam, never the 0.30.x line). The AR-23
-- Liberator, the LAS-58 Talon and the SMG-32 Reprimand fire LAS-13 Trident pulses, together or in any subset, through
-- in-place writes to the entity file (research/docs/multi-beam-swap-F5FEE03DCFDB.md, research/multi-beam-swap-
-- F5FEE03DCFDB.json; domains/beam_swap.lua). It generalises the live-proven Liberator swap (runtime/experiment_liberator_
-- beam.lua, kept unchanged as the fallback):
--   shared: BeamWeapon record 23 (table +0xDA8, 120 bytes; the table's one unowned record) := the Trident's record 18,
--           written once, before the first row, restored after the last row is gone. Records are read-only type data:
--           every consumer resolves resource -> record and only reads it, so three rows may name it (research section 2).
--   per weapon (order Liberator, Talon, Reprimand; restore in reverse):
--     1. its BeamWeapon index row (empty: Liberator 21, Talon 11, Reprimand 25; the first empty row on its probe path)
--        := {weapon, record 23, 0}: the record index first, then the key;
--     2. its membership list: ProjectileWeapon (321) out, BeamWeapon (270) in, same count, sorted, pointer unchanged
--        (one 4-aligned window: Liberator / Reprimand 8 bytes, Talon 12 bytes incl. 2 bytes of the next list, kept);
--        its ProjectileWeapon row stays;
--     3. magazine weapons only (Liberator record 201, Reprimand record 139, each its own): +156..+159 01000000 ->
--        00000000, the 40-K Meltagun's no-chamber model (the chamber is filled only by a ProjectileWeapon instance).
--        The Talon is a heat weapon without a magazine: after the swap its components are a subset of the Trident's.
-- One guarded transaction per apply and per restore (core/guarded_transaction.lua: context bytes compared before every
-- write, READONLY pages opened and restored, every target read back, ROLLBACK of everything already written on any
-- failure), so an apply of several weapons is all or nothing.
--
-- Not exported by api/hd2.lua: proof/MultiBeamProof requires this module. Every call re-proves everything and fails
-- closed with a reason; nothing is cached but the pin proof per game.dll:
--   * the build fingerprint, every pin of domains/beam_swap.lua (the live-proven Liberator pins and the multi-weapon
--     research's) and the component table pins; the manager slots are the entity allocation's own tables;
--   * per weapon: its settings row by the game's probe with its count, network type and list place; its
--     ProjectileWeapon row; its magazine row by the game's probe, no other row naming its record; its targets exactly
--     vanilla or applied (a Liberator left in L1 / L2 by LiberatorBeamProof is 'partial', anything else 'foreign');
--   * the table: the Trident's row and record (the copy source) as reviewed, record 23 vanilla or the copy, no row but
--     the experiment's naming one of the weapons or record 23, the copy present whenever a row is;
--   * the crash rules, at the write AND at the restore: ZERO live instances of EVERY weapon written (the descriptor
--     census: ship previews, the armory and your own loadout included); solo (player list + PlayFab lobby, unreadable
--     fails closed); for an apply the Trident's package (laser_shotgun) resident.
-- After a write each weapon is recorded in core/reviewed_edits.lua (its dormant ProjectileWeapon fields and record 23
-- refused; everything else writable). A weapon spawned while swapped may leave a ProjectileWeapon private copy nothing
-- removes (the Liberator's default ammunition; a Reprimand muzzle): RESTART THE GAME after using the experiment.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local log_module=require('hd2runtime/runtime/log')
local edits=require('hd2runtime/core/reviewed_edits')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local D=require('hd2runtime/domains/beam_swap')
local CT=require('hd2runtime/domains/component_tables')
local unpack=unpack or table.unpack
local M={}
M.VERSION='0.1.0-experimental'
M.OWNER='HD2Runtime multi-weapon beam swap experiment'
local PRIVATE,COMMIT,READONLY,PAGE=0x20000,0x1000,0x2,4096
local BW,MG,MZ,PJ=D.beam,D.manager,D.magazine,D.projectile
local TRIDENT=D.trident
local BY={}
M.WEAPONS={}
for _,w in ipairs(D.weapons)do BY[w.id]=w;M.WEAPONS[#M.WEAPONS+1]=w.id end
local proven={}             -- world key -> true | reason
local used=false            -- a swap was applied this session: the game must be restarted afterwards
local hooks={}              -- tests only: census / solo / assets overrides

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

-- Every pin, exact bytes, once per proven world (game.dll base).
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
    local settings=world.view.read(s.esh+found*D.membership.rowStride,D.membership.rowStride)
    local list=b.pointer(settings,8)
    if not(b.u32(settings,16)==w.membership.count and b.u32(settings,20)==0
        and b.u32(settings,24)==w.membership.networkType)then
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
    -- Its BeamWeapon row.
    L.row_at=s.table+w.beam.rowOffset
    L.row_bytes=s.table_bytes:sub(w.beam.rowOffset+1,w.beam.rowOffset+16)
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
    -- Pages: every target in the entity allocation's read-only memory.
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
    if row=='vanilla'and lst=='vanilla'and mag_before then L.state='vanilla'
    elseif row=='swapped'and lst=='swapped'and mag_after then L.state='applied'
    elseif row=='swapped'and mz and mag_before and(lst=='vanilla'or lst=='swapped')then L.state='partial'
    else L.state='foreign'end
    L.detail=('row %d %s, list %s, magazine chamber %s'):format(w.beam.row,row,lst,mag)
    return L
end

-- Everything the writes and the restore need, re-derived and checked. Returns the located state or raises.
local function locate(world)
    local manager=world.view.pointer(world.game+MG.global)
    if not manager then fail('TARGET_UNAVAILABLE: the entity manager is not initialised')end
    local beam_slot=world.view.pointer(manager+CT.slotBase+8*BW.index)
    local r=beam_slot and region(world,beam_slot)
    if not r then fail('TARGET_UNAVAILABLE: the BeamWeapon table is not in committed private memory')end
    local base=r.allocation_base
    if world.view.read(base,28)~=b.unhex(profile.map_header)then fail('the entity allocation framing changed')end
    if world.view.pointer(manager+MG.eshSlot)~=base+28 then
        fail('CONFLICT: the game reads its EntitySettingsHashmap from another place (another mod moved it)')
    end
    local s={manager=manager,base=base,esh=base+28,weapons={}}
    local c
    s.table,c=component_table(world,manager,base,BW.component)
    assert(c.index==BW.index and c.indices==BW.capacity and c.records==BW.records and c.stride==BW.recordStride
        and c.record_offset==BW.recordBase,'BeamWeapon schema differs from the research')
    local pc
    s.ptable,pc=component_table(world,manager,base,PJ.component)
    assert(pc.index==PJ.index,'ProjectileWeapon index differs from the research')
    local mc
    s.mtable,mc=component_table(world,manager,base,MZ.component)
    assert(mc.index==MZ.index and mc.indices==MZ.capacity and mc.records==MZ.records and mc.stride==MZ.recordStride
        and mc.record_offset==MZ.recordBase,'WeaponMagazine schema differs from the research')
    local size=BW.recordBase+BW.records*BW.recordStride
    s.table_bytes=world.view.read(s.table,size)
    if not s.table_bytes then fail('TARGET_UNAVAILABLE: the BeamWeapon table is unreadable')end
    local function row(n)return s.table_bytes:sub(n*16+1,n*16+16)end
    local trident=row(BW.tridentRow)
    if b.resource(trident,0)~=TRIDENT or b.u32(trident,8)~=BW.tridentRecord or b.u32(trident,12)~=0 then
        fail('CONFLICT: BeamWeapon row '..BW.tridentRow..' is not the Trident\'s (another mod changed it)')
    end
    local source=s.table_bytes:sub(BW.recordBase+BW.tridentRecord*BW.recordStride+1,
        BW.recordBase+(BW.tridentRecord+1)*BW.recordStride)
    if source~=b.unhex(BW.recordAfter)then
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
    s.mrows=world.view.read(s.mtable,MZ.capacity*MZ.rowStride)
    if not s.mrows then fail('TARGET_UNAVAILABLE: the WeaponMagazine table is unreadable')end
    local rows_named=0
    for _,w in ipairs(D.weapons)do
        local L=locate_weapon(world,s,w,s.mrows)
        s.weapons[w.id]=L
        for _,top in ipairs(L.tops)do tops[#tops+1]=top end
        if L.state~='vanilla'and L.state~='foreign'then rows_named=rows_named+1 end
    end
    if rows_named>0 and s.record~='copy'then s.record_conflict=true end
    s.owner={base=base,size=math.max(unpack(tops))-base,type=PRIVATE,protect=READONLY}
    local parts={}
    for _,w in ipairs(D.weapons)do parts[#parts+1]=w.name..': '..s.weapons[w.id].state end
    s.detail=('record 23 %s; %s'):format(s.record=='copy'and'Trident copy'or s.record=='vanilla'and'vanilla'
        or'FOREIGN',table.concat(parts,', '))
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
local function record_edit(w,state)
    if state=='applied'then
        local rows={[BW.component]={row=w.beam.row,record=BW.record},
            [PJ.component]={row=w.projectile.row,record=w.projectile.record}}
        if w.magazine then rows[MZ.component]={row=w.magazine.row,record=w.magazine.record}end
        edits.set(w.resource,{owner=M.OWNER,stage='applied',membership=b.unhex(w.membership.after),rows=rows,
            absent={[PJ.component]=true},refuse={[PJ.component]=refuse_projectile(w),[BW.component]=M.REFUSE_BEAM}})
    elseif state=='vanilla'then
        local e=edits.get(w.resource)
        if e and e.owner==M.OWNER then edits.clear(w.resource)end
    end
end

-- The list window's bytes for a membership list hex (bytes past the list, the next list's first entry, kept).
local function list_window_bytes(world,L,hex)
    local list=b.unhex(hex)
    local cur=world.view.read(L.window,L.window_size)
    if not cur then fail('TARGET_UNAVAILABLE: the '..L.w.name..'\'s membership list is unreadable')end
    local offset=L.window-L.list
    local inside=list:sub(offset+1,math.min(offset+L.window_size,#list))
    return inside..cur:sub(#inside+1)
end

-- The ordered changes of one weapon: {label, address, before, desired}.
local function weapon_changes(world,L,forward)
    local w=L.w
    local out={}
    local row_before,row_after=b.unhex(w.beam.rowBefore),b.unhex(w.beam.rowAfter)
    local function row(i,label)
        local x,y=row_before:sub(i+1,i+8),row_after:sub(i+1,i+8)
        out[#out+1]={w.id..'.row'..w.beam.row..'.'..label,L.row_at+i,forward and x or y,forward and y or x}
    end
    local x,y=list_window_bytes(world,L,w.membership.before),list_window_bytes(world,L,w.membership.after)
    local list={w.id..'.membership_list+'..(L.window-L.list),L.window,forward and x or y,forward and y or x}
    local mag
    if w.magazine then
        local mx,my=b.unhex(w.magazine.before),b.unhex(w.magazine.after)
        mag={w.id..'.magazine'..w.magazine.record..'+'..MZ.window,L.chamber_at,forward and mx or my,forward and my or mx}
    end
    if forward then
        row(8,'record');row(0,'key')
        out[#out+1]=list
        if mag then out[#out+1]=mag end
    else
        if mag then out[#out+1]=mag end
        out[#out+1]=list
        row(0,'key');row(8,'record')
    end
    return out
end

local function record_changes(s,forward)
    local out={}
    local x,y=b.unhex(BW.recordBefore),b.unhex(BW.recordAfter)
    for i=0,BW.recordStride-4,4 do
        local p,q=x:sub(i+1,i+4),y:sub(i+1,i+4)
        if p~=q then out[#out+1]={('record23+%d'):format(i),s.record_at+i,forward and p or q,forward and q or p}end
    end
    return out
end

-- One guarded transaction (all or nothing): changes = {{label, address, before, desired}} in write order.
local function run(world,s,label,changes,targets)
    local plan={snapshots={{owner=s.owner,offset=s.table-s.base,bytes=s.table_bytes}},changes={}}
    for _,L in ipairs(targets)do
        plan.snapshots[#plan.snapshots+1]={owner=s.owner,offset=L.list_context_at-s.base,bytes=L.list_context}
        if L.mrecord then
            plan.snapshots[#plan.snapshots+1]={owner=s.owner,offset=L.mrecord_at-s.base,bytes=L.mrecord}
        end
    end
    for _,c in ipairs(changes)do
        if c[3]~=c[4]then
            plan.changes[#plan.changes+1]={label='beam_swap.'..c[1],owner=s.owner,offset=c[2]-s.base,
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

-- Read-only: the proof state, per weapon, the live instances, the lobby, the assets.
function M.status()
    return guarded('status',function()
        local world=open()
        local s=locate(world)
        local count,why=census(world,s.manager)
        local is_solo,solo_why=solo(world)
        local asset,asset_why=assets_state(world)
        local out={ok=true,proven=true,record=s.record,detail=s.detail,solo=is_solo,solo_reason=solo_why,assets=asset,
            assets_detail=asset_why,census_error=why,live_entities=count and count.live,
            live_tridents=count and count.tridents,restart_required=used,weapons={}}
        log(('STATUS: pins proven; record 23 %s; solo %s (%s); Trident package %s; live entities %s%s'):format(
            s.record=='copy'and'Trident copy'or s.record,tostring(is_solo),tostring(solo_why),tostring(asset),
            tostring(out.live_entities),used and'; RESTART THE GAME after this session (the swap was used)'or''))
        for _,w in ipairs(D.weapons)do
            local L=s.weapons[w.id]
            local e=edits.get(w.resource)
            local entry={id=w.id,name=w.name,state=L.state,detail=L.detail,live=count and count[w.id],
                recorded=e and e.stage or nil}
            out.weapons[#out.weapons+1]=entry
            log(('%s: %s (%s); live %s; recorded edit %s'):format(w.name,L.state,L.detail,tostring(entry.live),
                tostring(entry.recorded)))
        end
        return out
    end)
end

-- Applies the swap to the weapons in ids (nil = all three) in one transaction.
function M.apply(ids)
    local want=select_ids(ids)
    return guarded('apply '..names(want),function()
        local world=open()
        local s=locate(world)
        log(('apply %s: proven; %s'):format(names(want),s.detail))
        refuse_unusable(s)
        local targets,targets_ids={},{}
        for _,id in ipairs(want)do
            if s.weapons[id].state=='vanilla'then targets[#targets+1]=s.weapons[id];targets_ids[#targets_ids+1]=id end
        end
        for _,w in ipairs(D.weapons)do record_edit(w,s.weapons[w.id].state)end
        if#targets==0 then
            log('apply '..names(want)..': already applied, nothing written')
            return {ok=true,writes=0,applied=want}
        end
        local count,solo_why=gates(world,s,targets_ids,true)
        log(('apply %s: gates passed: 0 live %s (%d live entities), solo (%s), Trident package resident'):format(
            names(targets_ids),names(targets_ids),count.live,solo_why))
        local changes={}
        if s.record=='vanilla'then for _,c in ipairs(record_changes(s,true))do changes[#changes+1]=c end end
        for _,L in ipairs(targets)do
            for _,c in ipairs(weapon_changes(world,L,true))do changes[#changes+1]=c end
        end
        local report=run(world,s,('apply (%srows, lists, magazine bytes of %s)'):format(
            s.record=='vanilla'and'record 23 := Trident record 18, then 'or'',names(targets_ids)),changes,targets)
        used=true
        s=locate(world)
        for _,id in ipairs(targets_ids)do
            if s.weapons[id].state~='applied'then
                fail('after the write the '..BY[id].name..' is '..s.weapons[id].state..' ('..s.weapons[id].detail..')')
            end
        end
        if s.record~='copy'then fail('after the write record 23 is '..s.record)end
        for _,w in ipairs(D.weapons)do record_edit(w,s.weapons[w.id].state)end
        local after=census(world,s.manager)
        for _,id in ipairs(targets_ids)do
            local w=BY[id]
            log(('%s APPLIED: row %d -> record 23 (Trident copy), list %s%s; spawned from now on it fires Trident '
                ..'pulses%s. Live after the write: %s'):format(w.name,w.beam.row,'BeamWeapon in, ProjectileWeapon out',
                w.magazine and(', magazine record '..w.magazine.record..' +156 = 0 (no chamber)')or'',
                w.magazine and', one round per pulse, reload to a full magazine'or', heat per pulse, heat sinks',
                tostring(after and after[id])))
        end
        log('APPLIED ('..s.detail..'). Solo only; restore with zero live swapped weapons, then RESTART THE GAME')
        return {ok=true,writes=report.writes,applied=targets_ids}
    end)
end

-- Restores the weapons in ids (nil = every applied weapon) in one transaction, in reverse order; record 23 last, once
-- no weapon row names it.
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
                if x==id and s.weapons[id].state=='applied'then
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
        local record_back=remaining==0 and s.record=='copy'
        if#targets==0 and not record_back then
            for _,w in ipairs(D.weapons)do record_edit(w,s.weapons[w.id].state)end
            log('restore '..names(want)..': already vanilla, nothing written')
            return {ok=true,writes=0,restored={}}
        end
        local count,solo_why=gates(world,s,targets_ids,false)
        log(('restore %s: gates passed: 0 live %s (%d live entities), solo (%s)'):format(names(targets_ids),
            names(targets_ids),count.live,solo_why))
        local changes={}
        for _,L in ipairs(targets)do
            for _,c in ipairs(weapon_changes(world,L,false))do changes[#changes+1]=c end
        end
        if record_back then for _,c in ipairs(record_changes(s,false))do changes[#changes+1]=c end end
        local report=run(world,s,('restore (magazine bytes, lists, rows of %s%s)'):format(names(targets_ids),
            record_back and', then record 23'or''),changes,targets)
        s=locate(world)
        for _,id in ipairs(targets_ids)do
            if s.weapons[id].state~='vanilla'then
                fail('after the restore the '..BY[id].name..' is '..s.weapons[id].state..' ('..s.weapons[id].detail..')')
            end
        end
        if record_back and s.record~='vanilla'then fail('after the restore record 23 is '..s.record)end
        for _,w in ipairs(D.weapons)do record_edit(w,s.weapons[w.id].state)end
        for _,id in ipairs(targets_ids)do log(BY[id].name..' RESTORED: every byte is vanilla again')end
        log('RESTORED ('..s.detail..')'..(used and'; RESTART THE GAME before playing on (stale ProjectileWeapon '
            ..'copies of swapped weapons may remain until the game exits)'or''))
        return {ok=true,writes=report.writes,restored=targets_ids,record_restored=record_back}
    end)
end

-- Tests only.
function M.set_hooks_for_tests(h)hooks=h or{}end
function M.reset_for_tests()
    proven={};used=false;hooks={}
    for _,w in ipairs(D.weapons)do edits.clear(w.resource)end
end
return M
