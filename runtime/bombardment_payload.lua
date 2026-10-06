-- Carrier payload (development only; docs/custom-stratagems.md, "Payload stage B"): the converted carrier's OWN
-- BombardmentComponentData takes a donor's bombardment pattern (the Orbital 120mm HE Barrage's), so the carrier keeps
-- its type, stable id, presentation, code and call-in while its barrage follows the donor's pattern and fires the
-- donor's shells. Not exported by api/hd2.lua and no public field reaches it.
--
-- The record is found exactly as the game finds it (0x503DC0: the bombardment index by payload hash, hash mod 44,
-- linear probe; domains/bombardment_payload.lua). Only the pattern words that differ from the donor's are written (the
-- research's compatibility words, e.g. the 380mm's +0x08, +0x1C, +0x24 and its three shells), in one guarded
-- transaction with the whole record as context; the donor's record and shell rows are only read and re-proven.
--
-- Guards (all re-checked in the same tick as the write; any failure writes nothing):
--   * the build: game.dll as researched and every pinned reader (the lookup, the private copies, the instances, the
--     shell list, the timing and spread readers, the variants);
--   * the carrier and the donor: reviewed records; the carrier payload-compatible with the donor (its row's delivery
--     value equal to the donor's; nothing outside the pattern words differs);
--   * a mission, the host, solo (one stratagem record);
--   * after the conversion: the carrier is the slot conversion's current carrier, and none of its converted entries has
--     a call-in in flight;
--   * ownership: the bombardment framing as reviewed; the carrier's index slot and record as reviewed; that record owned
--     by exactly one slot; no StratagemInfo row but the carrier's lists its payload, and the carrier row's payload list
--     is its catalogued one;
--   * the bytes: the carrier's record exactly its vanilla bytes (or exactly the bytes this operation wrote: nothing to
--     do); the donor's record exactly vanilla; every shell the pattern references is a real, reviewed ProjectileInfo
--     row; the resulting shell list packed (no gap, at least one, at most eight) after every single write;
--   * no barrage: no bombardment instance of the carrier's payload, no barrage at all while writing (waited for), and no
--     active variant naming the carrier's payload (it would give a spawned carrier a private copy);
--   * the donor's call-in package resident (requested through the Runtime's loader first).
-- Stage C (spec.shells = 'Orbital Gas Strike'): the carrier keeps the 120mm's pattern words, and its shell list points
-- at the shell donor's own shell (197), repeated to the pattern's shell count ([197, 197, 197]). Two transactions in one
-- call, no yield between them: the pattern words (verified), then the shell list on the established pattern (verified:
-- packed, exactly the planned entries); a failure rolls back what was written. Extra guards: the shell donor's record
-- exactly vanilla, its shell row reviewed, its whole chain (explosion 82, damage 447, volume template 16, statuses
-- 42/44) its reviewed rows, its package resident. The shell, explosion, volume and status rows are never written.
-- The restore (restore(), the mission end, and the Lua state's close) writes the vanilla words back only when the
-- record holds exactly the written bytes and no instance of the carrier's payload exists, then verifies the whole record
-- equals its vanilla bytes. Solo only: the record is per payload type, so another player's carrier would read it too.
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local metrics=require('hd2runtime/runtime/metrics')
local transaction=require('hd2runtime/core/guarded_transaction')
local core_assets=require('hd2runtime/core/assets')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local D=require('hd2runtime/domains/bombardment_payload')
local M={}
M.BARRAGE_WAIT=60      -- seconds a write waits for running barrages to end
M.ASSET_TIMEOUT=60     -- seconds the donor's package is awaited
local C,MGR,VAR=D.component,D.manager,D.variants
local TABLE=profile.stratagem.table_rva
local ROWS=profile.stratagem.entries
local PATTERN={}
for _,word in ipairs(D.pattern)do PATTERN[word.offset]=word end

local function log(text)log_module.emit('[HD2Runtime] carrier payload '..text)end
local function hex64(value)return(b.unhex(value:gsub('^0x','')):reverse())end
local function conversion()return package.loaded['hd2runtime/runtime/stratagem_slot_conversion']end

-- The pinned readers on the loaded game.dll: true, or nil and the reason.
local proven={}
function M.prove(world)
    if D.source.gameDllSha256~=profile.dll_sha then return nil,'the bombardment research covers another game.dll build'end
    if proven[world.game]then return true end
    for _,pin in ipairs(D.pins)do
        if world.runtime.read(world.game+pin.rva,#pin.hex/2)~=b.unhex(pin.hex)then
            return nil,('bombardment reader changed (%s at game+%X)'):format(pin.label,pin.rva)
        end
    end
    proven[world.game]=true
    return true
end

-- The reviewed record and compatibility of a stratagem by name: entry, record, compatibility (or nils).
local function reviewed(name)
    local entry=catalog.stratagems[name]
    local id=entry and entry.root and entry.root.id
    return entry,id and D.records[tostring(id)],id and D.compatibility[tostring(id)],id
end
-- Static (no game read): whether `name` can take the donor's pattern on its own record. true, or false and the
-- reasons ({...}).
function M.compatible(name,donor)
    donor=donor or D.donor
    if donor~=D.donor then return false,{'only '..D.donor..'\'s pattern is researched'}end
    local _,record,compat=reviewed(name)
    if name==donor then return false,{'the donor itself'}end
    if not record then return false,{'no reviewed BombardmentComponentData record'}end
    if not compat then return false,{'no compatibility verdict'}end
    if not compat.compatible then return false,compat.reasons end
    return true,{}
end
-- The number of words the donor's pattern changes on `name`'s record (ranking: fewer first), or nil.
function M.words(name)
    local _,_,compat=reviewed(name)
    return compat and#compat.words or nil
end

-- The game's own lookup (0x503DC0) of a payload hash: {index, slot, record, address, owners} or nil, code, reason.
local function locate(world,payload)
    local components=world.view.pointer(world.game+C.global)
    local index=components and world.view.pointer(components+C.indexField)
    if not index then return nil,'UNAVAILABLE','the bombardment index is not readable'end
    if world.view.read(index-28,28)~=b.unhex(C.header)then return nil,'FRAMING_CHANGED','the bombardment framing changed'end
    local raw=world.view.read(index,C.slots*16)
    if not raw then return nil,'UNAVAILABLE','the bombardment index is unreadable'end
    local wanted=hex64(payload)
    local lo,hi=b.u32(wanted,0),b.u32(wanted,4)
    local slot=((hi%C.slots)*(4294967296%C.slots)+lo%C.slots)%C.slots
    local found
    for _=1,C.slots do
        local hash=raw:sub(slot*16+1,slot*16+8)
        if hash==wanted then found=slot;break end
        if hash==string.rep('\0',8)then break end
        slot=slot==C.slots-1 and 0 or slot+1
    end
    if not found then return nil,'NO_RECORD','the payload has no bombardment record'end
    local record,flags=b.u32(raw,found*16+8),b.u32(raw,found*16+12)
    if record>=C.records or flags~=0 then return nil,'FRAMING_CHANGED','the bombardment index slot is out of bounds'end
    local owners=0
    for k=0,C.slots-1 do
        if raw:sub(k*16+1,k*16+8)~=string.rep('\0',8)and b.u32(raw,k*16+8)==record then owners=owners+1 end
    end
    return {index=index,slot=found,record=record,owners=owners,address=index+C.recordOffset+record*C.stride}
end
-- The StratagemInfo types whose payload list holds the hash, and the row's own list of `type` (read-only).
local function rows_listing(world,payload,kind)
    local wanted=hex64(payload)
    local listing,own={},nil
    for t=1,ROWS-1 do
        local row=world.view.pointer(world.game+TABLE+t*8)
        local list=row and world.view.pointer(row+0x98)
        local count=row and world.view.u32(row+0xA0)
        if list and count and count<=16 then
            local items={}
            for k=0,count-1 do
                local item=world.view.read(list+k*8,8)
                items[#items+1]=item
                if item==wanted then listing[#listing+1]=t end
            end
            if t==kind then own=items end
        end
    end
    return listing,own
end
-- Every bombardment instance (the manager's handles): {total, barrages, of = number of instances of `payload`} or nil.
local function instances(world,payload)
    local manager=world.view.pointer(world.game+MGR.global)
    if not manager then return nil end
    local total,barrages=world.view.u32(manager+MGR.instances),world.view.u32(manager+MGR.barrages)
    if not(total and barrages and total<=4096 and barrages<=4096)then return nil end
    local handles=world.view.pointer(manager+MGR.handles)
    local wanted=payload and hex64(payload)
    local of=0
    for i=0,math.max(total,barrages)-1 do
        local handle=handles and world.view.pointer(handles+i*8)
        local hash=handle and world.view.read(handle+MGR.handleHash,8)
        if not hash then return nil end
        if hash==wanted then of=of+1 end
    end
    return {total=total,barrages=barrages,of=of}
end
-- Whether an ACTIVE variant names the payload (0x12E5590): true / false, or nil when unreadable.
local function variant_active(world,payload)
    local registry=world.view.pointer(world.game+VAR.global)
    if not registry then return false end
    local active,groups=world.view.u32(registry+VAR.activeCount),world.view.u32(registry+VAR.groupCount)
    if not(active and groups and active<=128 and groups<=4096)then return nil end
    local wanted=hex64(payload)
    for i=0,active-1 do
        local item=world.view.pointer(registry+VAR.active+i*VAR.activeStride)
        local id=item and world.view.u32(item+VAR.groupId)
        if item and not id then return nil end
        for k=0,(id and groups or 0)-1 do
            local group=world.view.pointer(registry+VAR.groups+k*8)
            if group and world.view.u32(group+VAR.groupId)==id then
                local entries,count=world.view.pointer(group+VAR.entries),world.view.u32(group+VAR.entryCount)
                if not(count and count<=4096)then return nil end
                for e=0,count-1 do
                    local at=entries and entries+e*VAR.entryStride
                    local hashes,n=at and world.view.pointer(at+VAR.hashes),at and world.view.u32(at+VAR.hashCount)
                    if not(n and n<=4096)then return nil end
                    for q=0,n-1 do if world.view.read(hashes+q*8,8)==wanted then return true end end
                end
            end
        end
    end
    return false
end
-- The private allocation holding a record: the guarded transaction's owner, or nil.
local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and(r.protect==2 or r.protect==4)and address>=r.base
            and address+size<=r.base+r.size)then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=r.protect}
end

-- The donor's pattern on `name`'s vanilla record: the desired bytes and the ordered changes {offset, expected,
-- desired} (non-shell words first, then the shells: ascending when the list grows, descending when it shrinks, so the
-- list stays packed after every single write).
local function pattern_plan(name)
    local _,record,compat=reviewed(name)
    local vanilla=b.unhex(record.vanilla)
    local donor=b.unhex(select(2,reviewed(D.donor)).vanilla)
    local words,shells={},{}
    for _,word in ipairs(compat.words)do
        local item={offset=word.offset,expected=vanilla:sub(word.offset+1,word.offset+4),
            desired=donor:sub(word.offset+1,word.offset+4)}
        if word.offset>=0x40 and word.offset<0x60 then shells[#shells+1]=item else words[#words+1]=item end
    end
    local function count(bytes)local n=0;for k=0,7 do if b.u32(bytes,0x40+k*4)~=0 then n=n+1 end end;return n end
    local desired=vanilla
    for _,item in ipairs(compat.words)do
        desired=desired:sub(1,item.offset)..donor:sub(item.offset+1,item.offset+4)..desired:sub(item.offset+5)
    end
    local grows=count(desired)>=count(vanilla)
    table.sort(shells,function(x,y)if grows then return x.offset<y.offset end;return x.offset>y.offset end)
    for _,item in ipairs(shells)do words[#words+1]=item end
    return vanilla,desired,words
end
-- Whether the shell list of `bytes` is packed (no gap, 1 to 8 entries): count, or nil.
local function packed(bytes)
    local n,ended=0,false
    for k=0,7 do
        if b.u32(bytes,0x40+k*4)~=0 then
            if ended then return nil end
            n=n+1
        else ended=true end
    end
    return n>0 and n or nil
end
M.packed=packed

-- Stage C: the 120mm's pattern words (not its shells) on `name`'s vanilla record, then the shell list made of the shell
-- donor's shells, in turn, to the pattern donor's shell count. Returns vanilla, mid (the pattern only), desired, the
-- pattern words, the shell words (ascending when the list grows or keeps its count, descending when it shrinks) and
-- the shell list.
local function shell_plan(name,shell_donor)
    local _,record,compat=reviewed(name)
    local vanilla=b.unhex(record.vanilla)
    local pattern_record=select(2,reviewed(D.donor))
    local donor=b.unhex(pattern_record.vanilla)
    local source=select(2,reviewed(shell_donor)).shells
    local pattern_words,mid={},vanilla
    for _,word in ipairs(compat.words)do
        if not(word.offset>=0x40 and word.offset<0x60)then
            local item={offset=word.offset,expected=vanilla:sub(word.offset+1,word.offset+4),
                desired=donor:sub(word.offset+1,word.offset+4)}
            pattern_words[#pattern_words+1]=item
            mid=mid:sub(1,item.offset)..item.desired..mid:sub(item.offset+5)
        end
    end
    local shells={}
    for k=1,#pattern_record.shells do shells[k]=source[(k-1)%#source+1]end
    local desired,shell_words=mid,{}
    for k=0,7 do
        local at=0x40+k*4
        local want=b.encode(shells[k+1]or 0,'u32')
        local now=mid:sub(at+1,at+4)
        if now~=want then
            shell_words[#shell_words+1]={offset=at,expected=now,desired=want}
            desired=desired:sub(1,at)..want..desired:sub(at+5)
        end
    end
    local grows=(packed(desired)or 0)>=(packed(mid)or 0)
    table.sort(shell_words,function(x,y)if grows then return x.offset<y.offset end;return x.offset>y.offset end)
    return vanilla,mid,desired,pattern_words,shell_words,shells
end
-- Bytes equal to a reviewed row, the masked (relocated pointer) words excepted.
local function masked_equal(bytes,reviewed_bytes,masked)
    if not bytes or#bytes~=#reviewed_bytes then return false end
    local skip={}
    for _,offset in ipairs(masked or{})do skip[offset]=true end
    for offset=0,#reviewed_bytes-4,4 do
        if not skip[offset]and bytes:sub(offset+1,offset+4)~=reviewed_bytes:sub(offset+1,offset+4)then return false end
    end
    return true
end
-- The Gas Strike chain exactly as reviewed (read only): the shell row, explosion 82, damage 447, volume template 16
-- and statuses 42/44. true, or false and which.
local function chain_intact(world)
    local shell=D.gasChain.shell
    local row=world.view.pointer(world.game+D.shellTable+shell*8)
    if not(row and world.view.read(row,D.shellStride)==b.unhex(D.shellRows[tostring(shell)]))then
        return false,'shell '..shell..' is not its reviewed row'
    end
    for _,item in ipairs(D.gasChainRows)do
        local at=world.view.pointer(world.game+item.table+item.id*8)
        if not masked_equal(at and world.view.read(at,item.stride),b.unhex(item.reviewed),item.masked)then
            return false,item.kind..' '..item.id..' is not its reviewed row'
        end
    end
    return true
end
M.chain_intact=chain_intact
-- Read-only: whether the donors are exactly as reviewed: {pattern (the 120mm's record), shells (the shell donor's
-- record), chain (its chain)}.
function M.donors(world,shell_donor)
    local function vanilla_of(name)
        local _,record=reviewed(name)
        local found=record and locate(world,record.payload)
        return found~=nil and world.view.read(found.address,C.stride)==b.unhex(record.vanilla)
    end
    return {pattern=vanilla_of(D.donor),shells=vanilla_of(shell_donor or D.shellDonor),chain=chain_intact(world)==true}
end

-- Read-only: everything the proof reports about `name`'s record (stage A research at run time): {name, id, type,
-- payload, address, record, indexRow, owners, size, rowsListing, ownRow (the row lists its catalogued payloads),
-- vanilla (true when the record is exactly its reviewed bytes), desired (true when it holds the donor's pattern),
-- shells, shellCount, perSalvo, salvos, shellDelay, salvoDelay, scatter, walk, centreScatter, drift, differences
-- ({offset, role, value, donor}), compatible, reasons, instances, variant}; or nil, code, reason.
function M.inspect(world,name,donor,shell_donor)
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',why end
    local entry,record,_,id=reviewed(name)
    if not(entry and record)then return nil,'NO_RECORD',name..' has no reviewed bombardment record'end
    local kind=loadout.type_of(world,id)
    local found,code,reason=locate(world,record.payload)
    if not found then return nil,code,reason end
    local bytes=world.view.read(found.address,C.stride)
    if not bytes then return nil,'UNAVAILABLE','the record is unreadable'end
    local listing,own=rows_listing(world,record.payload,kind)
    local own_ok=own~=nil and#own==#entry.root.payloads
    for k,payload in ipairs(entry.root.payloads)do if not(own and own[k]==hex64(payload))then own_ok=false end end
    local f=function(o)return b.value(bytes,o,'f32')end
    local u=function(o)return b.u32(bytes,o)end
    local shells={}
    for k=0,7 do if u(0x40+k*4)~=0 then shells[#shells+1]=u(0x40+k*4)end end
    local donor_record=select(2,reviewed(donor or D.donor))
    local donor_bytes=donor_record and b.unhex(donor_record.vanilla)
    local differences={}
    for o=0,C.stride-4,4 do
        if donor_bytes and bytes:sub(o+1,o+4)~=donor_bytes:sub(o+1,o+4)then
            local word=PATTERN[o]
            local kind_=word and word.type or'u32'
            differences[#differences+1]={offset=o,role=word and word.role or'outside the pattern',
                value=b.value(bytes,o,kind_),donor=b.value(donor_bytes,o,kind_)}
        end
    end
    local compatible,reasons=M.compatible(name,donor)
    local desired
    if compatible then
        if shell_donor then desired=select(3,shell_plan(name,shell_donor))else desired=select(2,pattern_plan(name))end
    end
    return {name=name,id=id,type=kind,payload=record.payload,address=found.address,record=found.record,
        indexRow=found.slot,reviewedRecord=record.record,reviewedRow=record.indexRow,owners=found.owners,size=C.stride,
        rowsListing=listing,ownRow=own_ok,vanilla=bytes==b.unhex(record.vanilla),desired=desired~=nil and bytes==desired,
        shells=shells,shellCount=packed(bytes),perSalvo=u(0x04),salvos=u(0x18),shellDelay={f(0x08),f(0x0C)},
        salvoDelay={f(0x1C),f(0x20)},scatter=f(0x24),walk={f(0x10),f(0x14)},centreScatter=f(0x28),drift=f(0x60),
        differences=differences,compatible=compatible,reasons=reasons,instances=instances(world,record.payload),
        variant=variant_active(world,record.payload)}
end

------------------------------------------------------------------------------------------------- the jobs --
local state      -- {applied, carrier, donor, id, payload, address, vanilla, desired, words}
local sentinel
local called={}  -- [conversion record:entry:cooldown end at the conversion] = true once a call is seen: never retried
-- Whether u64 little-endian a is above u64 c (the game's unsigned compare).
local function above(a,c)
    local ahi,chi=b.u32(a,4),b.u32(c,4)
    if ahi~=chi then return ahi>chi end
    return b.u32(a,0)>b.u32(c,0)
end

local function job(body,callback)
    local handle={status='pending'}
    local co=coroutine.create(body)
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        local ok,result,code,reason=coroutine.resume(co,dt)
        if ok and coroutine.status(co)~='dead'then return end
        watch.status='complete'
        if not ok then handle.status,handle.code,handle.reason='failed','PAYLOAD_FAILED',tostring(result)
        elseif result then for key,value in pairs(result)do handle[key]=value end
        else handle.status,handle.code,handle.reason='refused',code,reason end
        if handle.status=='refused'or handle.status=='failed'then
            log('refused: '..tostring(handle.code)..': '..tostring(handle.reason))
        end
        if callback then callback(handle)end
    end
    scheduler.attach(watch)
    return handle
end

-- The checks that hold before the package wait and again right before the write (one tick, no yield). opts.converted:
-- the conversion checks too (the carrier is the converted one and has not been called); opts.barrages: no barrage at
-- all. Returns the write context {found, owner, record, donor_found} or nil, code, reason.
local function write_checks(world,spec,opts)
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',why end
    local entry,record,_,id=reviewed(spec.carrier)
    local donor_entry,donor_record=reviewed(spec.donor)
    local compatible,reasons=M.compatible(spec.carrier,spec.donor)
    if not compatible then return nil,'NOT_COMPATIBLE',spec.carrier..': '..table.concat(reasons,'; ')end
    if not(entry and donor_entry and donor_record)then return nil,'NO_RECORD','no reviewed records'end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','the carrier payload is written in a mission only'end
    if game.host~=true then return nil,'NOT_HOST','development proof: host only'end
    local conv=conversion()
    if not conv then return nil,'NOT_CONVERTED','the slot conversion is not loaded'end
    local local_record,code,reason=conv.local_record(world)
    if not local_record then return nil,code,reason end
    if local_record.records~=1 then
        return nil,'NOT_SOLO','solo only: '..local_record.records..' stratagem records (the record is per payload type)'
    end
    local kind=loadout.type_of(world,id)
    if opts.converted then
        -- After the conversion: the carrier is the converted one, and has not been called since. The evidence of "not
        -- called" is NOT a zero cooldown end: in a live mission every entry holds one shared, non-zero time from the
        -- record's build (all four mission snapshots: 110331400 on every never-called entry) and a call sets a new one.
        -- So: the cooldown end exactly as the conversion recorded it, not above the game clock (a token called before the
        -- conversion would still be cooling down: 0x66D200), and no call-in in flight. A detected call is final for that
        -- conversion: the payload is never written after a call, nor retried.
        local converted=conv.state()
        if not(converted and converted.converted and converted.carrier==kind and converted.carrier_name==spec.carrier)then
            return nil,'NOT_CONVERTED','the carrier '..spec.carrier..' is not the converted carrier: the payload follows the '
                ..'mission-time conversion'
        end
        local observed=conv.observe(world)
        if not(observed and#observed>=1)then return nil,'NOT_CONVERTED','the converted entries are unreadable'end
        local clock_object=world.view.pointer(world.game+D.clock.global)
        local clock=clock_object and world.view.read(clock_object+D.clock.time,8)
        if not clock then return nil,'UNAVAILABLE','the game clock is unreadable'end
        for _,item in ipairs(observed)do
            local at=converted.cooldowns and converted.cooldowns[item.index]
            if not at then
                return nil,'NOT_CONVERTED','the conversion recorded no cooldown end for entry '..item.index
            end
            local key=('%s:%d:%s'):format(tostring(converted.record),item.index,b.hex(at))
            if called[key]then
                return nil,'ALREADY_CALLED','the converted entry '..item.index..' was called after the conversion: the '
                    ..'payload is never written after a call (not retried this mission)'
            end
            if item.flying~=false then
                called[key]=true
                return nil,'ALREADY_CALLED','a call-in of the converted entry '..item.index..' is in flight: the payload '
                    ..'is never written after a call (not retried this mission)'
            end
            if item.cooldown~=at then
                called[key]=true
                return nil,'ALREADY_CALLED','the converted entry '..item.index..'\'s cooldown end changed since the '
                    ..'conversion: it has been called; the payload is never written after a call (not retried this mission)'
            end
            if above(item.cooldown,clock)then
                return nil,'ON_COOLDOWN','the converted entry '..item.index..' is cooling down (its token was called '
                    ..'before the conversion)'
            end
        end
    end
    -- Ownership: the game's own lookup, one owner, the reviewed slot and record, only the carrier's row.
    local found
    found,code,reason=locate(world,record.payload)
    if not found then return nil,code,reason end
    if found.record~=record.record or found.slot~=record.indexRow then
        return nil,'OWNERSHIP_CHANGED','the carrier\'s record is not the reviewed one'
    end
    if found.owners~=1 then return nil,'SHARED','the carrier\'s record has '..found.owners..' index owners'end
    local listing,own=rows_listing(world,record.payload,kind)
    if not(#listing==1 and listing[1]==kind)then
        return nil,'SHARED','StratagemInfo rows other than the carrier\'s list its payload'
    end
    if not(own and#own==#entry.root.payloads)then return nil,'OWNERSHIP_CHANGED','the carrier row\'s payloads changed'end
    for k,payload in ipairs(entry.root.payloads)do
        if own[k]~=hex64(payload)then return nil,'OWNERSHIP_CHANGED','the carrier row\'s payloads changed'end
    end
    local donor_found=locate(world,donor_record.payload)
    if not(donor_found and donor_found.record==donor_record.record)then
        return nil,'DONOR_CHANGED','the donor\'s record is not the reviewed one'
    end
    if world.view.read(donor_found.address,C.stride)~=b.unhex(donor_record.vanilla)then
        return nil,'DONOR_CHANGED','the donor\'s record is not its vanilla bytes (it is never written)'
    end
    local owner=owner_of(world,found.address,C.stride)
    if not owner then return nil,'RECORD_CHANGED','the record is not in a private allocation'end
    -- The shells the pattern references: real, reviewed ProjectileInfo rows.
    for _,shell in ipairs(donor_record.shells)do
        local row=world.view.pointer(world.game+D.shellTable+shell*8)
        local reviewed_row=D.shellRows[tostring(shell)]
        if not row or row==world.game+D.emptyShell then return nil,'SHELL_ABSENT','shell '..shell..' has no row'end
        if not reviewed_row or world.view.read(row,D.shellStride)~=b.unhex(reviewed_row)then
            return nil,'SHELL_CHANGED','shell '..shell..' is not its reviewed row'
        end
    end
    -- Stage C: the shell donor's record exactly vanilla, its shell rows reviewed, its whole chain as reviewed.
    local shell_found
    if spec.shells then
        if spec.shells~=D.shellDonor then
            return nil,'NOT_COMPATIBLE','only '..D.shellDonor..'\'s shell chain is researched'
        end
        local _,shell_record=reviewed(spec.shells)
        if not(shell_record and#shell_record.shells>=1)then return nil,'NO_RECORD','no reviewed shell donor record'end
        shell_found=locate(world,shell_record.payload)
        if not(shell_found and shell_found.record==shell_record.record)then
            return nil,'SHELL_DONOR_CHANGED','the shell donor\'s record is not the reviewed one'
        end
        if world.view.read(shell_found.address,C.stride)~=b.unhex(shell_record.vanilla)then
            return nil,'SHELL_DONOR_CHANGED','the shell donor\'s record is not its vanilla bytes (it is never written)'
        end
        local intact,which=chain_intact(world)
        if not intact then return nil,'GAS_CHAIN_CHANGED',which..' (the chain is never written)'end
    end
    -- No barrage of the carrier's payload; no active variant naming it; none at all while writing.
    local live=instances(world,record.payload)
    if not live then return nil,'UNAVAILABLE','the bombardment instances are unreadable'end
    if live.of>0 then return nil,'IN_USE','a barrage of '..spec.carrier..' is running'end
    if opts.barrages and(live.total>0 or live.barrages>0)then
        return nil,'BARRAGE_ACTIVE','a bombardment is running ('..live.total..' instances)'
    end
    local variant=variant_active(world,record.payload)
    if variant==nil then return nil,'UNAVAILABLE','the variants are unreadable'end
    if variant then return nil,'VARIANT_ACTIVE','an active variant names '..spec.carrier..'\'s payload'end
    return {found=found,owner=owner,record=record,donor_found=donor_found,shell_found=shell_found,live=live,kind=kind,
        id=id}
end

local function arm()
    if sentinel then return end
    local ok,ffi=pcall(require,'ffi')
    if ok then sentinel=ffi.gc(ffi.new('uint8_t[1]'),function()pcall(M.finalize_now)end)end
end

-- Before the conversion (stratagem_selector.convert_with_payload): every guard that does not need the conversion,
-- with no barrage at all. The write context or nil, code, reason (read-only).
function M.preflight(world,spec)
    spec.donor=spec.donor or D.donor
    return write_checks(world,spec,{converted=false,barrages=true})
end
-- The donor's call-in package (its shells' and explosions' assets), or nil.
function M.donor_dependency(donor)
    donor=donor or D.donor
    return core_assets.dependency_for_stratagem(select(4,reviewed(donor)),donor)
end

-- The write: the donor's pattern words onto the carrier's own record. spec = {carrier, donor}. opts.atomic (inside
-- stratagem_selector.convert_with_payload, in the tick of the conversion): never yields: a package that is not
-- resident (NOT_READY) or a running barrage (BARRAGE_ACTIVE) refuses it instead of being waited for.
function M.apply_body(spec,opts)
    local atomic=opts and opts.atomic
    if type(spec)~='table'or type(spec.carrier)~='string'then return nil,'BAD_SPEC','spec must name the carrier'end
    spec.donor=spec.donor or D.donor
    if state and state.applied then
        if state.carrier==spec.carrier and state.donor==spec.donor then
            return {status='applied',already=true,writes=0,carrier=spec.carrier,donor=spec.donor}
        end
        return nil,'ALREADY_APPLIED','another carrier payload is applied'
    end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local ctx,code,reason=write_checks(world,spec,{converted=true})
    if not ctx then return nil,code,reason end
    -- The donors' call-in packages first: the pattern donor's (stage B fires its shells), and the shell donor's (stage
    -- C: its shell's, explosion's and gas volume's assets).
    local donor_id=select(4,reviewed(spec.donor))
    local dependencies={core_assets.dependency_for_stratagem(donor_id,spec.donor)}
    if spec.shells then dependencies[2]=core_assets.dependency_for_stratagem(select(4,reviewed(spec.shells)),spec.shells)end
    for k=1,spec.shells and 2 or 1 do
        if not dependencies[k]then return nil,'ASSET_UNAVAILABLE','no call-in package is known for a donor'end
    end
    local function resident()
        for _,dependency in ipairs(dependencies)do
            local ok,state_=pcall(core_assets.state,world.runtime,dependency.package)
            if not(ok and state_=='resident')then return false end
        end
        return true
    end
    local package_text='resident'
    if not resident()and atomic then
        return nil,'NOT_READY','a donor\'s call-in package is not resident'
    end
    if not resident()then
        local gate=core_assets.gate(world.runtime,{id='carrier-payload-'..donor_id,asset_dependencies=dependencies},
            log_module.emit)
        local waited=0
        while true do
            local dt=coroutine.yield()or 0
            waited=waited+dt
            local result,why_not=gate.tick(dt)
            if result=='ready'then break end
            if result=='failed'or waited>M.ASSET_TIMEOUT then
                return nil,'ASSET_UNAVAILABLE',tostring(why_not or'the donor\'s call-in package did not load')
            end
        end
        package_text=('loaded (%.1f s)'):format(waited)
    end
    -- No barrage at all while writing: wait for running ones to end.
    local waited=0
    while true do
        ctx,code,reason=write_checks(world,spec,{converted=true,barrages=true})
        if ctx then break end
        if code~='BARRAGE_ACTIVE'or atomic or waited>M.BARRAGE_WAIT then return nil,code,reason end
        waited=waited+(coroutine.yield()or 0)
    end
    local before=world.view.read(ctx.found.address,C.stride)
    local owner=ctx.owner
    local function plan_of(words,context,inverse)
        local changes={}
        local first,last,step=1,#words,1
        if inverse then first,last,step=#words,1,-1 end
        for k=first,last,step do
            local item=words[k]
            local expected,desired_=item.expected,item.desired
            if inverse then expected,desired_=item.desired,item.expected end
            changes[#changes+1]={label='bombardment.'..spec.carrier..'+'..string.format('0x%02X',item.offset)
                ..(inverse and'.undo'or''),owner=owner,offset=ctx.found.address+item.offset-owner.base,expected=expected,
                desired=desired_,before=expected,already_desired=false,
                identity={component='BombardmentComponentData',component_type='native',unique_owner=true,owner_count=1},
                chain={}}
        end
        return {snapshots={{owner=owner,offset=ctx.found.address-owner.base,bytes=context}},changes=changes}
    end
    if spec.shells then
        -- Stage C: the 120mm pattern, verified; then the shell list on it, verified; a failure rolls back.
        local vanilla,mid,desired,pattern_words,shell_words,shells=shell_plan(spec.carrier,spec.shells)
        if before==desired then
            return nil,'CONFLICT','the carrier\'s record already holds the payload, and this operation did not write it'
        end
        if before~=vanilla then return nil,'CONFLICT','the carrier\'s record is not its vanilla bytes'end
        local step=mid
        for _,item in ipairs(shell_words)do
            step=step:sub(1,item.offset)..item.desired..step:sub(item.offset+5)
            if not packed(step)then return nil,'BAD_PATTERN','the shell list would not stay packed'end
        end
        if packed(desired)~=#shells then return nil,'BAD_PATTERN','the shell list would not hold exactly '..#shells..' shells'end
        local first=transaction.apply(world.runtime,plan_of(pattern_words,before))
        metrics.count('carrier_payload.transactions')
        if first.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(first.reason)end
        local function undo(context,words)
            local back=transaction.apply(world.runtime,plan_of(words,context,true))
            return back.status=='APPLIED'and world.view.read(ctx.found.address,C.stride)==vanilla
        end
        local established=world.view.read(ctx.found.address,C.stride)
        if established~=mid then
            return nil,'VERIFY_FAILED','the 120mm pattern did not read back; undone: '..tostring(undo(established,pattern_words))
        end
        log(('120mm pattern applied: %s\'s own BombardmentComponentData: %d writes (the timing and spread words); the '
            ..'record verified: the 120mm pattern with the carrier\'s own shells'):format(spec.carrier,first.writes))
        local second=transaction.apply(world.runtime,plan_of(shell_words,mid))
        metrics.count('carrier_payload.transactions')
        if second.status~='APPLIED'then
            return nil,'GUARD_REJECTED','the shell list was refused ('..tostring(second.reason)..'); the 120mm pattern '
                ..'undone: '..tostring(undo(mid,pattern_words))
        end
        local after=world.view.read(ctx.found.address,C.stride)
        local all_shells=true
        for k,shell in ipairs(shells)do if b.u32(after,0x3C+k*4)~=shell then all_shells=false end end
        local donors=M.donors(world,spec.shells)
        local verify={record=after==desired,donor=donors.pattern,shellDonor=donors.shells,chain=donors.chain,
            shellCount=packed(after or''),shells=all_shells,nonTarget=first.non_target_bytes_unchanged
            and second.non_target_bytes_unchanged}
        local words={}
        for _,item in ipairs(pattern_words)do words[#words+1]=item end
        for _,item in ipairs(shell_words)do words[#words+1]=item end
        if not(verify.record and verify.donor and verify.shellDonor and verify.chain and verify.shellCount==#shells
                and verify.shells and verify.nonTarget)then
            return nil,'VERIFY_FAILED','the payload did not verify; undone: '..tostring(undo(after,words))
        end
        state={applied=true,carrier=spec.carrier,donor=spec.donor,shellDonor=spec.shells,id=ctx.id,
            payload=ctx.record.payload,address=ctx.found.address,vanilla=vanilla,desired=desired,words=#words,
            plan_words=words}
        arm()
        local list={}
        for k,shell in ipairs(shells)do list[k]=tostring(shell)end
        log(('Gas Strike shell %s applied: %s\'s shell list = %s (shell donor %s): %d writes; APPLIED: %d writes in all; '
            ..'record verified %s; packed with %d shells; %s record vanilla %s; %s record vanilla %s; its chain as reviewed '
            ..'%s; packages %s; non-target bytes unchanged %s; protection restored %s'):format(list[1],spec.carrier,
            table.concat(list,', '),spec.shells,second.writes,first.writes+second.writes,tostring(verify.record),
            verify.shellCount,spec.donor,tostring(verify.donor),spec.shells,tostring(verify.shellDonor),
            tostring(verify.chain),package_text,tostring(verify.nonTarget),tostring(first.protection_restored
            and second.protection_restored)))
        return {status='applied',carrier=spec.carrier,donor=spec.donor,shellDonor=spec.shells,
            writes=first.writes+second.writes,patternWrites=first.writes,shellWrites=second.writes,words=#words,
            shells=shells,verify=verify,package=package_text}
    end
    local vanilla,desired,words=pattern_plan(spec.carrier)
    if before==desired then
        return nil,'CONFLICT','the carrier\'s record already holds the donor\'s pattern, and this operation did not write it'
    end
    if before~=vanilla then return nil,'CONFLICT','the carrier\'s record is not its vanilla bytes'end
    -- Every intermediate shell list packed.
    local step=vanilla
    for _,item in ipairs(words)do
        step=step:sub(1,item.offset)..item.desired..step:sub(item.offset+5)
        if not packed(step)then return nil,'BAD_PATTERN','the shell list would not stay packed'end
    end
    local changes={}
    for _,item in ipairs(words)do
        changes[#changes+1]={label='bombardment.'..spec.carrier..'+'..string.format('0x%02X',item.offset),owner=owner,
            offset=ctx.found.address+item.offset-owner.base,expected=item.expected,desired=item.desired,
            before=item.expected,already_desired=false,
            identity={component='BombardmentComponentData',component_type='native',unique_owner=true,owner_count=1},
            chain={}}
    end
    local plan={snapshots={{owner=owner,offset=ctx.found.address-owner.base,bytes=before}},changes=changes}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('carrier_payload.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local after=world.view.read(ctx.found.address,C.stride)
    state={applied=true,carrier=spec.carrier,donor=spec.donor,id=ctx.id,payload=ctx.record.payload,
        address=ctx.found.address,vanilla=vanilla,desired=desired,words=#words}
    arm()
    local verify={record=after==desired,donor=world.view.read(ctx.donor_found.address,C.stride)
        ==b.unhex(select(2,reviewed(spec.donor)).vanilla),shellCount=packed(after or''),
        nonTarget=report.non_target_bytes_unchanged}
    log(('APPLIED: %s takes %s\'s pattern on its own BombardmentComponentData: %d writes; record verified %s; shells %s; '
        ..'donor record vanilla %s; package %s; non-target bytes unchanged %s; protection restored %s'):format(
        spec.carrier,spec.donor,report.writes,tostring(verify.record),tostring(verify.shellCount),tostring(verify.donor),
        package_text,tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored)))
    return {status='applied',carrier=spec.carrier,donor=spec.donor,writes=report.writes,words=#words,report=report,
        verify=verify,package=package_text}
end
function M.apply(spec,callback)return job(function()return M.apply_body(spec)end,callback)end

-- The restore: the vanilla words back, only from exactly the written bytes and with no instance of the carrier's
-- payload; then the whole record verified against its vanilla bytes.
function M.restore_body()
    if not(state and state.applied)then return nil,'NOT_APPLIED','nothing to restore'end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local ok,proof_why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',proof_why end
    local found,code,reason=locate(world,state.payload)
    if not found then return nil,code,reason end
    if found.address~=state.address then return nil,'RECORD_CHANGED','the carrier\'s record moved'end
    local now=world.view.read(found.address,C.stride)
    if now==state.vanilla then
        state.applied=false
        log('RESTORED: '..state.carrier..'\'s record already holds its vanilla bytes: 0 writes; exact: true')
        return {status='restored',writes=0,exact=true,carrier=state.carrier}
    end
    if now~=state.desired then
        return nil,'CONFLICT','the carrier\'s record is neither the written bytes nor its vanilla bytes: not restored'
    end
    local live=instances(world,state.payload)
    if not live then return nil,'UNAVAILABLE','the bombardment instances are unreadable'end
    if live.of>0 then return nil,'IN_USE','a barrage of '..state.carrier..' is running'end
    local owner=owner_of(world,found.address,C.stride)
    if not owner then return nil,'RECORD_CHANGED','the record is not in a private allocation'end
    local words=state.plan_words or select(3,pattern_plan(state.carrier))
    local changes={}
    for k=#words,1,-1 do
        local item=words[k]
        changes[#changes+1]={label='bombardment.'..state.carrier..'+'..string.format('0x%02X',item.offset)..'.restore',
            owner=owner,offset=found.address+item.offset-owner.base,expected=item.desired,desired=item.expected,
            before=item.desired,already_desired=false,
            identity={component='BombardmentComponentData',component_type='native',unique_owner=true,owner_count=1},
            chain={}}
    end
    local report=transaction.apply(world.runtime,{snapshots={{owner=owner,offset=found.address-owner.base,bytes=now}},
        changes=changes})
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local after=world.view.read(found.address,C.stride)
    local exact=after==state.vanilla
    if exact then state.applied=false end
    local donors=M.donors(world,state.shellDonor)
    log(('RESTORED: %s\'s BombardmentComponentData: %d writes; the whole record equals its vanilla bytes: %s; %s record '
        ..'vanilla %s; %s record vanilla %s; non-target bytes unchanged %s; protection restored %s'):format(state.carrier,
        report.writes,tostring(exact),D.donor,tostring(donors.pattern),state.shellDonor or D.shellDonor,
        tostring(donors.shells),tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored)))
    return {status='restored',writes=report.writes,exact=exact,carrier=state.carrier,report=report,donors=donors,
        shellDonor=state.shellDonor}
end
function M.restore(callback)return job(M.restore_body,callback)end

-- {applied, carrier, donor, words} of the current operation, or nil.
function M.state()
    return state and{applied=state.applied,carrier=state.carrier,donor=state.donor,shellDonor=state.shellDonor,
        words=state.words}or nil
end
-- Before the Lua state goes away: restore under the same guards (no instance of the carrier's payload; exactly the
-- written bytes).
function M.finalize_now()
    if not(state and state.applied)then return end
    local co=coroutine.create(M.restore_body)
    coroutine.resume(co,0)
end
function M.reset_for_tests()state=nil;proven={};called={}end
return M
