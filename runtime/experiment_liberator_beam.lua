-- LIBERATOR BEAM EXPERIMENT (EXPERIMENTAL, SOLO ONLY; branch exp/liberator-beam, never the 0.30.x line). The AR-23
-- Liberator fires LAS-13 Trident pulses through three in-place writes to the entity file (research/docs/component-swap-
-- liberator-beam.md, research/component-swap-liberator-beam-F5FEE03DCFDB.json; domains/liberator_beam.lua):
--   1. BeamWeapon record 23 (table +0xDA8, 120 bytes; the table's unowned default record) := the Trident's record 18;
--   2. BeamWeapon index row 21 (table +0x150, 16 bytes, empty) := {Liberator, record 23, flags 0}; the record index is
--      written before the key, so the row only becomes findable once it is whole;
--   3. the Liberator's membership list (EntitySettings row 3686, 46 bytes): last entries 271, 290, 321 -> 270, 271, 290
--      (same count, sorted, pointer unchanged). Its ProjectileWeapon index row stays (0x744690 needs it).
-- Write order record -> row -> list; restore list -> row -> record. Stage L1 = writes 1 and 2 (nothing consults them
-- until a Liberator has a BeamWeapon instance); stage L2 = write 3 (every Liberator spawned after it is a beam weapon).
--
-- Not exported by api/hd2.lua: proof/LiberatorBeamProof requires this module, as other proofs use Runtime internals.
-- Every call re-proves everything and fails closed with a reason; nothing is cached but the pin proof per game.dll:
--   * the build fingerprint and game.dll image (runtime/event_world.lua open), then every pin of domains/liberator_beam
--     .lua (93 exact code byte ranges: the BeamWeapon lookup whole, the EntitySettings lookup whole, the loader's slot
--     and EntitySettingsHashmap stores, the spawn's descriptor writes, the trigger, ammo and destroy paths) and the
--     component table pins of domains/component_tables.lua;
--   * the addresses, re-derived: [game + 0x346BF98] = the manager; its BeamWeapon and ProjectileWeapon slots must be the
--     entity allocation's own tables (allocation + profile offset + 28; the allocation header the profile's), its
--     EntitySettingsHashmap slot the allocation + 28; the Liberator's settings row found by the game's own probe at
--     row 3686 with count 23, its network type and its list at the reviewed body offset;
--   * the bytes: the Trident row 20 / record 18 (the copy source) exactly as reviewed, no other row naming the
--     Liberator or record 23, the Liberator's ProjectileWeapon row 4 -> record 192, and all three targets exactly in
--     one of the three states (vanilla, L1, L2); any other state is foreign and refused;
--   * the crash rules, at the write AND at the restore: ZERO live Liberators (the entity descriptor table, 0x800 x 24
--     bytes, every descriptor with a valid entity: ship previews, the armory and the player's own weapon included);
--     solo (the game's player list and the PlayFab lobby of runtime/peer_channel.lua: one member, or no lobby); for L2
--     the Trident's package (packages/generated/loadout/laser_shotgun) resident.
-- Writes go through core/guarded_transaction.lua (context bytes compared before every write, READONLY pages opened and
-- restored, every target read back, rollback on failure). After a write the edit is recorded in core/reviewed_edits.lua:
-- the entity catalog then recognises exactly this state (its 'membership absent' diagnostics are the Runtime's own) and
-- refuses the Liberator's dormant ProjectileWeapon fields and the experiment's BeamWeapon record; its other components
-- (WeaponData, the magazine, ...) stay writable. A Liberator spawned while the list was swapped keeps a ProjectileWeapon
-- private copy that nothing removes: RESTART THE GAME after using the experiment.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local log_module=require('hd2runtime/runtime/log')
local edits=require('hd2runtime/core/reviewed_edits')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local D=require('hd2runtime/domains/liberator_beam')
local CT=require('hd2runtime/domains/component_tables')
local unpack=unpack or table.unpack
local M={}
M.VERSION='0.1.0-experimental'
M.OWNER='HD2Runtime Liberator beam experiment'
local PRIVATE,COMMIT,READONLY,PAGE=0x20000,0x1000,0x2,4096
local LIBERATOR,TRIDENT=D.resources.liberator,D.resources.trident
local BW,MB,PJ,MG=D.beam,D.membership,D.projectile,D.manager
local proven={}             -- world key -> true | reason
local used_l2=false         -- L2 was applied this session: the game must be restarted afterwards
local hooks={}              -- tests only: census / solo / assets overrides

local function log(text)log_module.emit('LIBERATOR BEAM: '..text)end
local function clean(why)return(tostring(why):gsub('^%[string "[^"]*"%]:%d+: ',''):gsub('^[^%s:]+:%d+: ',''))end
local function fail(text)error(text,0)end
local function hexs(s)return b.hex(s)end

M.REFUSE_PROJECTILE='LIBERATOR BEAM EXPERIMENT: the AR-23 Liberator\'s ProjectileWeapon component is dormant while the '
    ..'experimental beam swap is applied (its list no longer names it); writes to its fire rate, projectile, ammunition '
    ..'and the rows they link to are refused until the swap is restored (owner: HD2Runtime experiment)'
M.REFUSE_BEAM='LIBERATOR BEAM EXPERIMENT: BeamWeapon record 23 (the Liberator\'s Trident copy) belongs to the '
    ..'experimental beam swap; writes to it are refused (owner: HD2Runtime experiment)'

-- Every pin, exact bytes, once per proven world (game.dll base).
local function prove(world)
    local key=world.key
    if proven[key]==true then return true end
    if proven[key]then return nil,proven[key]end
    local why
    if D.source.gameDllSha256~=profile.dll_sha or CT.source.gameDllSha256~=profile.dll_sha then
        why='the research covers another game.dll build'
    end
    local lists={D.pins,CT.pins,CT.lookups[BW.component]or{},CT.lookups[PJ.component]or{}}
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

-- Everything the writes and the restore need, re-derived and checked. Returns the located state or raises.
local function locate(world)
    local manager=world.view.pointer(world.game+MG.global)
    if not manager then fail('TARGET_UNAVAILABLE: the entity manager is not initialised')end
    local beam_slot=world.view.pointer(manager+CT.slotBase+8*BW.index)
    local r=beam_slot and region(world,beam_slot)
    if not r then fail('TARGET_UNAVAILABLE: the BeamWeapon table is not in committed private memory')end
    local base=r.allocation_base
    local header=world.view.read(base,28)
    if header~=b.unhex(profile.map_header)then fail('the entity allocation framing changed')end
    if world.view.pointer(manager+MG.eshSlot)~=base+28 then
        fail('CONFLICT: the game reads its EntitySettingsHashmap from another place (another mod moved it)')
    end
    local tbl,c=component_table(world,manager,base,BW.component)
    assert(c.index==BW.index and c.indices==BW.capacity and c.records==BW.records and c.stride==BW.recordStride
        and c.record_offset==BW.recordBase,'BeamWeapon schema differs from the research')
    local ptbl,pc=component_table(world,manager,base,PJ.component)
    local size=BW.recordBase+BW.records*BW.recordStride
    local table_bytes=world.view.read(tbl,size)
    if not table_bytes then fail('TARGET_UNAVAILABLE: the BeamWeapon table is unreadable')end
    -- The index rows: the Trident at its row, no other row names the Liberator or record 23.
    local function row(n)return table_bytes:sub(n*16+1,n*16+16)end
    local trident=row(BW.tridentRow)
    if b.resource(trident,0)~=TRIDENT or b.u32(trident,8)~=BW.tridentRecord or b.u32(trident,12)~=0 then
        fail('CONFLICT: BeamWeapon row '..BW.tridentRow..' is not the Trident\'s (another mod changed it)')
    end
    for n=0,BW.capacity-1 do
        if n~=BW.row then
            local raw=row(n)
            local key=b.resource(raw,0)
            if key==LIBERATOR then fail('CONFLICT: another BeamWeapon row already names the Liberator')end
            if key~='0x0000000000000000'and b.u32(raw,8)==BW.record then
                fail('CONFLICT: another BeamWeapon row already names record '..BW.record)
            end
        end
    end
    local source=table_bytes:sub(BW.recordBase+BW.tridentRecord*BW.recordStride+1,
        BW.recordBase+(BW.tridentRecord+1)*BW.recordStride)
    if source~=b.unhex(BW.recordAfter)then
        fail('CONFLICT: the Trident\'s BeamWeapon record differs from the reviewed copy source (another mod changed it)')
    end
    local row_bytes=table_bytes:sub(BW.rowOffset+1,BW.rowOffset+16)
    local record_bytes=table_bytes:sub(BW.recordOffset+1,BW.recordOffset+BW.recordStride)
    -- The Liberator's ProjectileWeapon row stays (row 4 -> record 192).
    local prow=world.view.read(ptbl+PJ.row*16,16)
    if not(prow and b.resource(prow,0)==LIBERATOR and b.u32(prow,8)==PJ.record and b.u32(prow,12)==0)then
        fail('CONFLICT: the Liberator\'s ProjectileWeapon row is not as reviewed')
    end
    assert(pc.index==PJ.index,'ProjectileWeapon index differs from the research')
    -- The Liberator's EntitySettings row by the game's own probe (home = resource & 0xFFF).
    local esh=base+28
    local found
    local at=MB.home
    for _=1,MB.rows do
        local key=world.view.read(esh+at*MB.rowStride,8)
        if not key then fail('TARGET_UNAVAILABLE: the entity map is unreadable')end
        if key==string.rep('\0',8)then break end
        if b.resource(key,0)==LIBERATOR then found=at;break end
        at=(at+1)%MB.rows
    end
    if found~=MB.row then fail('the Liberator\'s entity map row is not row '..MB.row..' (found '..tostring(found)..')')end
    local settings=world.view.read(esh+found*MB.rowStride,MB.rowStride)
    local list=b.pointer(settings,8)
    if not(b.u32(settings,16)==MB.count and b.u32(settings,20)==0 and b.u32(settings,24)==MB.networkType)then
        fail('the Liberator\'s entity map row (count, network type) is not as reviewed')
    end
    if list-esh~=MB.listOffsetInBody then
        fail('CONFLICT: the Liberator\'s membership list is not at its reviewed place (another mod moved it)')
    end
    local list_bytes=world.view.read(list,MB.count*2)
    if not list_bytes then fail('TARGET_UNAVAILABLE: the Liberator\'s membership list is unreadable')end
    local lr=region(world,list)
    local pages={}
    for _,extent in ipairs({{tbl+BW.rowOffset,16},{tbl+BW.recordOffset,BW.recordStride},{list,MB.count*2}})do
        local q=region(world,extent[1])
        if not(q and q.allocation_base==base and q.protect==READONLY and extent[1]+extent[2]<=q.base+q.size)then
            fail('a target page is not in the entity allocation\'s read-only memory')
        end
        pages[#pages+1]=q.base+q.size
    end
    -- The list window: 8 bytes, 4-aligned, holding the three changed entries (bytes 40..45).
    local first=list+40
    if first%2~=0 then fail('the membership list is not u16-aligned')end
    local window=first-first%4
    if window%PAGE+8>PAGE or(tbl+BW.rowOffset)%4~=0 or(tbl+BW.recordOffset)%4~=0
        or(tbl+BW.rowOffset)%PAGE+16>PAGE then
        fail('a target crosses a page or is misaligned')
    end
    local state
    local rb,rec,lb=hexs(row_bytes),hexs(record_bytes),hexs(list_bytes)
    if rb==BW.rowBefore and rec==BW.recordBefore and lb==MB.before then state='vanilla'
    elseif rb==BW.rowAfter and rec==BW.recordAfter and lb==MB.before then state='L1'
    elseif rb==BW.rowAfter and rec==BW.recordAfter and lb==MB.after then state='L2'
    else state='foreign'end
    local top=math.max(lr and lr.base+lr.size or 0,unpack(pages))
    return {manager=manager,base=base,owner={base=base,size=top-base,type=PRIVATE,protect=READONLY},table=tbl,
        table_bytes=table_bytes,list=list,list_bytes=list_bytes,window=window,row_bytes=row_bytes,
        record_bytes=record_bytes,state=state,
        detail=('row 21 %s, record 23 %s, list %s'):format(rb==BW.rowBefore and'vanilla'or rb==BW.rowAfter and'swapped'
            or'FOREIGN',rec==BW.recordBefore and'vanilla'or rec==BW.recordAfter and'Trident copy'or'FOREIGN',
            lb==MB.before and'vanilla'or lb==MB.after and'swapped'or'FOREIGN')}
end

-- Live entities of the Liberator type (and of the Trident, for the log) in the descriptor table.
local function census(world,manager)
    if hooks.census then return hooks.census(world,manager)end
    local invalid=world.view.u32(world.game+MG.invalidEntity)
    local raw=world.view.read(manager+MG.descriptors,MG.descriptorStride*MG.descriptorCount)
    if not(invalid and raw)then return nil,'the entity descriptor table is unreadable'end
    local live,liberators,tridents=0,0,0
    for k=0,MG.descriptorCount-1 do
        local at=k*MG.descriptorStride
        if b.u32(raw,at+MG.descriptorEntity)~=invalid and(b.u32(raw,at)~=0 or b.u32(raw,at+4)~=0)then
            live=live+1
            local kind=b.resource(raw,at)
            if kind==LIBERATOR then liberators=liberators+1 elseif kind==TRIDENT then tridents=tridents+1 end
        end
    end
    return {live=live,liberators=liberators,tridents=tridents}
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

local function record_edit(stage)
    local rows={[BW.component]={row=BW.row,record=BW.record},[PJ.component]={row=PJ.row,record=PJ.record}}
    if stage=='L1'then
        edits.set(LIBERATOR,{owner=M.OWNER,stage='L1',membership=b.unhex(MB.before),rows=rows,
            absent={[BW.component]=true},refuse={[BW.component]=M.REFUSE_BEAM}})
    elseif stage=='L2'then
        edits.set(LIBERATOR,{owner=M.OWNER,stage='L2',membership=b.unhex(MB.after),rows=rows,
            absent={[PJ.component]=true},refuse={[PJ.component]=M.REFUSE_PROJECTILE,[BW.component]=M.REFUSE_BEAM}})
    else
        edits.clear(LIBERATOR)
    end
end

-- One guarded transaction: changes = {{label, address, before, desired}} in write order, contexts = {{address, bytes}}.
local function run(world,s,label,changes,contexts)
    local plan={snapshots={},changes={}}
    for _,c in ipairs(contexts)do
        plan.snapshots[#plan.snapshots+1]={owner=s.owner,offset=c[1]-s.base,bytes=c[2]}
    end
    for _,c in ipairs(changes)do
        if c[3]~=c[4]then
            plan.changes[#plan.changes+1]={label='liberator_beam.'..c[1],owner=s.owner,offset=c[2]-s.base,
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
    if report.status~='APPLIED'then fail('the guarded write was refused: '..tostring(report.reason))end
    return report
end

local function table_context(s)return{s.table,s.table_bytes}end
local function list_context(world,s)
    local at=s.list-16
    local bytes=world.view.read(at,MB.count*2+48)
    if not bytes then fail('TARGET_UNAVAILABLE: the membership list context is unreadable')end
    return{at,bytes}
end

-- Record 23 then row 21 (its record index first, then its key), one transaction.
local function write_l1(world,s,forward)
    local changes={}
    local rec_before,rec_after=b.unhex(BW.recordBefore),b.unhex(BW.recordAfter)
    local row_before,row_after=b.unhex(BW.rowBefore),b.unhex(BW.rowAfter)
    local rec_at,row_at=s.table+BW.recordOffset,s.table+BW.rowOffset
    local function rec(i)
        local x,y=rec_before:sub(i+1,i+4),rec_after:sub(i+1,i+4)
        changes[#changes+1]={('record23+%d'):format(i),rec_at+i,forward and x or y,forward and y or x}
    end
    local function row(i,label)
        local x,y=row_before:sub(i+1,i+8),row_after:sub(i+1,i+8)
        changes[#changes+1]={label,row_at+i,forward and x or y,forward and y or x}
    end
    if forward then
        for i=0,BW.recordStride-4,4 do rec(i)end
        row(8,'row21.record');row(0,'row21.key')
    else
        row(0,'row21.key');row(8,'row21.record')
        for i=0,BW.recordStride-4,4 do rec(i)end
    end
    return run(world,s,forward and'L1 write (record 23 := Trident record 18, then row 21 := Liberator -> 23)'
        or'L1 restore (row 21, then record 23)',changes,{table_context(s)})
end
local function write_l2(world,s,forward)
    local offset=s.window-s.list
    local function bytes(hex)
        local list=b.unhex(hex)
        local cur=world.view.read(s.window,8)
        if not cur then fail('TARGET_UNAVAILABLE: the membership list is unreadable')end
        -- The window may hold two bytes past the list (the next list's first entry): kept as they are.
        local inside=list:sub(offset+1,math.min(offset+8,#list))
        return inside..cur:sub(#inside+1)
    end
    local x,y=bytes(MB.before),bytes(MB.after)
    return run(world,s,forward and'L2 write (membership list: 271, 290, 321 -> 270, 271, 290)'
        or'L2 restore (membership list: 270, 271, 290 -> 271, 290, 321)',
        {{'membership_list+'..offset,s.window,forward and x or y,forward and y or x}},{list_context(world,s)})
end

-- The gates of a write or a restore. stage: 'L1' | 'L2' | 'restore'.
local function gates(world,s,stage)
    local count,why=census(world,s.manager)
    if not count then fail('REFUSED: '..why)end
    if count.liberators>0 then
        fail(('REFUSED: %d live AR-23 Liberator%s (the ship preview, the armory or your own weapon): equip another '
            ..'primary, do not open the armory, and try again'):format(count.liberators,count.liberators==1 and''or's'))
    end
    local ok,reason=solo(world)
    if not ok then fail('REFUSED: solo only: '..tostring(reason))end
    if stage=='L2'then
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

-- Read-only: the proof state, the live Liberators, the lobby, the assets, the applied stage.
function M.status()
    return guarded('status',function()
        local world=open()
        local s=locate(world)
        local count,why=census(world,s.manager)
        local is_solo,solo_why=solo(world)
        local asset,asset_why=assets_state(world)
        local e=edits.get(LIBERATOR)
        local out={ok=true,proven=true,state=s.state,detail=s.detail,live_liberators=count and count.liberators,
            live_tridents=count and count.tridents,live_entities=count and count.live,census_error=why,solo=is_solo,
            solo_reason=solo_why,assets=asset,assets_detail=asset_why,recorded=e and e.stage or nil,
            restart_required=used_l2}
        log(('STATUS: pins proven; state %s (%s); live Liberators %s (live entities %s); solo %s (%s); Trident '
            ..'package %s; recorded edit %s%s'):format(out.state,s.detail,tostring(out.live_liberators),
            tostring(out.live_entities),tostring(is_solo),tostring(solo_why),tostring(asset),tostring(out.recorded),
            used_l2 and'; RESTART THE GAME after this session (the swap was used)'or''))
        return out
    end)
end

-- stage 'L1': record + row. stage 'L2': the list (L1 first when it is not applied yet).
function M.apply(stage)
    assert(stage=='L1'or stage=='L2','apply(stage): stage must be L1 or L2')
    return guarded('apply '..stage,function()
        local world=open()
        local s=locate(world)
        log(('apply %s: proven; state %s (%s)'):format(stage,s.state,s.detail))
        if s.state=='foreign'then fail('REFUSED: the targets are in a state the experiment did not make ('..s.detail..')')end
        if s.state==stage or(stage=='L1'and s.state=='L2')then
            record_edit(s.state)
            log('apply '..stage..': already applied (state '..s.state..'), nothing written')
            return {ok=true,state=s.state,writes=0}
        end
        local count,solo_why=gates(world,s,stage)
        log(('apply %s: gates passed: 0 live Liberators (%d live entities), solo (%s)%s'):format(stage,count.live,
            solo_why,stage=='L2'and', Trident package resident'or''))
        local writes=0
        if s.state=='vanilla'then
            writes=writes+write_l1(world,s,true).writes
            s=locate(world)
            if s.state~='L1'then fail('after the L1 write the state is '..s.state..' ('..s.detail..')')end
            record_edit('L1')
            log('L1 APPLIED: record 23 holds the Trident copy, row 21 names the Liberator; the list is unchanged '
                ..'(bullets as before)')
        end
        if stage=='L2'then
            gates(world,s,'L2')         -- again, right before the list write
            writes=writes+write_l2(world,s,true).writes
            s=locate(world)
            if s.state~='L2'then fail('after the L2 write the state is '..s.state..' ('..s.detail..')')end
            record_edit('L2')
            used_l2=true
            local after=census(world,s.manager)
            log(('L2 APPLIED: the Liberator\'s list names BeamWeapon (270) instead of ProjectileWeapon (321); every '
                ..'Liberator spawned from now on fires Trident pulses. Live Liberators after the write: %s. Solo only; '
                ..'restore with zero live Liberators, then RESTART THE GAME'):format(tostring(after and after.liberators)))
        end
        return {ok=true,state=s.state,writes=writes}
    end)
end

-- Reverse order: the list, then row 21 and record 23.
function M.restore()
    return guarded('restore',function()
        local world=open()
        local s=locate(world)
        log(('restore: proven; state %s (%s)'):format(s.state,s.detail))
        if s.state=='foreign'then fail('REFUSED: the targets are in a state the experiment did not make ('..s.detail..')')end
        if s.state=='vanilla'then
            record_edit(nil)
            log('restore: already vanilla, nothing written')
            return {ok=true,state='vanilla',writes=0}
        end
        local count,solo_why=gates(world,s,'restore')
        log(('restore: gates passed: 0 live Liberators (%d live entities), solo (%s)'):format(count.live,solo_why))
        local writes=0
        if s.state=='L2'then
            writes=writes+write_l2(world,s,false).writes
            s=locate(world)
            if s.state~='L1'then fail('after the list restore the state is '..s.state..' ('..s.detail..')')end
            record_edit('L1')
            log('L2 RESTORED: the Liberator\'s list is vanilla again (row 21 and record 23 still applied)')
        end
        writes=writes+write_l1(world,s,false).writes
        s=locate(world)
        if s.state~='vanilla'then fail('after the restore the state is '..s.state..' ('..s.detail..')')end
        record_edit(nil)
        log('RESTORED: every byte is vanilla again'..(used_l2 and'; RESTART THE GAME before playing on (stale '
            ..'ProjectileWeapon copies of the swapped Liberators remain until the game exits)'or''))
        return {ok=true,state='vanilla',writes=writes}
    end)
end

-- Tests only.
function M.set_hooks_for_tests(h)hooks=h or{}end
function M.reset_for_tests()proven={};used_l2=false;hooks={};edits.clear(LIBERATOR)end
return M
