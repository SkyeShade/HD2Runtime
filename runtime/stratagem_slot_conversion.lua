-- Mission-time slot conversion (development only; docs/custom-stratagems.md, "Mission-time slot conversion"). Not
-- exported by api/hd2.lua and no public field reaches it.
--
-- One entry of the LOCAL player's mission stratagem record changes from a token type (the later of two loadout entries
-- of the same type, e.g. a second Orbital Precision Strike) to an owned, unselected vanilla carrier type. The game then
-- treats that slot as the carrier (research/stratagem-slot-conversion-F5FEE03DCFDB.json):
--   * the HUD takes each entry's type every frame and rebuilds a slot whose type changed (arrows, icon): no HUD write;
--   * the matcher reads each entry's type and that type's code, one candidate per type: the carrier is its own
--     candidate; its result is the carrier type, which activation maps to the carrier's row;
--   * uses, cooldown and in-flight call-ins stay with the entry;
--   * the save store and the loadout screen's record are never touched, and the game rebuilds this record for the ship
--     at the mission end, which discards the conversion by itself.
--
-- Guards (refused with nothing written): the game.dll build and the record, HUD, matcher, call-in and ownership code
-- (pins); in a mission, as host, solo (one record: a direct write is not synchronised to peers); token and carrier are
-- catalogued, by stable id, different; the carrier is enabled, selectable and owned (the availability check's own
-- rule, read-only) and in no entry of the record; token and carrier both have unlimited uses, and so has the entry; the
-- token appears at least twice among the loadout (non-granted) entries; no call-in of the entry is in flight; the
-- carrier's call-in package is resident (loaded first through the game's reference-counted package system, as the
-- game holds every record type's package). One guarded transaction writes the 4-byte type, with the whole entry block
-- and count as its context; afterwards the entry reads the carrier and every other entry, the count and the save store
-- are unchanged. Restore writes the token back under the same guards; a finalizer restores before this Lua state
-- closes.
--
-- M.convert_virtual is the custom stratagem selector's conversion: instead of the later duplicate, exactly the loadout
-- slots the Runtime records as virtual instances of one definition (several at once, one transaction), and only while
-- the mission loadout is exactly the order they were recorded in. Every other guard is the same.
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local core_assets=require('hd2runtime/core/assets')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local stratagem_hud=require('hd2runtime/runtime/stratagem_hud')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local D=require('hd2runtime/domains/stratagem_slots')
local M={}
local R,E,CI,CAT,ROWM=D.record,D.record.entry,D.callIns,D.catalogue,D.row
local HUD=require('hd2runtime/domains/stratagem_calldown').hud
local payload=require('hd2runtime/runtime/bombardment_payload')
local TABLE=profile.stratagem.table_rva
local ASSET_TIMEOUT=30

local function log(text)log_module.emit('[HD2Runtime] stratagem slot '..text)end
local function signed(n)return n and n>=2147483648 and n-4294967296 or n end
local function u32(n)n=n%4294967296;return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end

local proven={}
function M.prove(world)
    if D.source.gameDllSha256~=profile.dll_sha then return nil,'the slot research covers another game.dll build'end
    if proven[world.game]then return true end
    for _,pin in ipairs(D.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,'stratagem record code changed ('..pin.label..' at game+'..string.format('%X',pin.rva)..')'
        end
    end
    proven[world.game]=true
    return true
end

local function row(world,kind)
    return type(kind)=='number'and kind>0 and kind<150 and world.view.pointer(world.game+TABLE+kind*8)or nil
end
local function name_of(world,kind)
    local id=loadout.id_of(world,kind)
    for name,entry in pairs(catalog.stratagems)do if entry.root and entry.root.id==id then return name end end
    return 'type '..tostring(kind)
end
-- The availability check's ownership rule, read-only: true / false, or nil when the catalogue is unreadable.
-- The same rule with its evidence: {owned, found (in the catalogue's range), state, parent (the parent item's state),
-- range = {first, last}}, or nil when the catalogue is unreadable.
-- The catalogue's first record of each stable id over its range (the scan's order), read once per update
-- (scheduler.serial): a carrier discovery asks for about a hundred stratagems' ownership, and a scan per stratagem read
-- the whole range each time (two reads per entry; live, each read is one ReadProcessMemory: a lobby allocation of four
-- custom stratagems made about 46,000 reads). A snapshot of the update's catalogue; a record found through it is read
-- again and, when it no longer holds that id, the scan decides. nil (the scan as before) outside an update or when the
-- index array cannot be read in one piece.
local catalogue_index={}
local function records_by_id(world,cat,first,last)
    local serial=require('hd2runtime/runtime/scheduler').serial()
    if not serial then return nil end
    local c=catalogue_index
    if c.serial==serial and c.key==world.key and c.cat==cat and c.first==first and c.last==last then return c.map end
    local raw=last>first and world.view.read(cat+CAT.index+first*4,(last-first)*4)
    if last>first and not raw then return nil end
    local map={}
    for position=first,last-1 do
        local index=b.u32(raw,(position-first)*4)
        local record=cat+CAT.records+index*CAT.recordStride
        local id=world.view.u32(record+CAT.recordId)
        if id and map[id]==nil then map[id]=record end
    end
    catalogue_index={serial=serial,key=world.key,cat=cat,first=first,last=last,map=map}
    return map
end
local function ownership(world,stable_id)
    local cat=world.view.pointer(world.game+CAT.global)
    if not cat then return nil end
    local first,last=world.view.u32(cat+CAT.rangeFirst),world.view.u32(cat+CAT.rangeLast)
    if not(first and last and first<=last and last<=0x10000)then return nil end
    local function state_of(record)
        local definition=world.view.u32(record)
        return definition and world.view.u32(cat+CAT.definitions+definition*CAT.definitionStride+CAT.definitionState)
    end
    local function ok(state)return state==CAT.ownedStates[1]or state==CAT.ownedStates[2]end
    local function found(record)
        local state=state_of(record)
        local back=world.view.u32(record+CAT.recordBack)
        local parent=back~=nil and back>0 and state_of(record-back*CAT.recordStride)or nil
        return {owned=ok(state)or(parent~=nil and ok(parent)),found=true,state=state,parent=parent,range={first,last}}
    end
    local map=records_by_id(world,cat,first,last)
    if map then
        local record=map[stable_id]
        if not record then return {owned=false,found=false,range={first,last}}end
        if world.view.u32(record+CAT.recordId)==stable_id then return found(record)end
        -- The record changed since the index was read: the scan below decides.
    end
    for position=first,last-1 do
        local index=world.view.u32(cat+CAT.index+position*4)
        local record=index and cat+CAT.records+index*CAT.recordStride
        if record and world.view.u32(record+CAT.recordId)==stable_id then return found(record)end
    end
    return {owned=false,found=false,range={first,last}}
end
M.ownership=ownership
local function owned(world,stable_id)
    local r=ownership(world,stable_id)
    if r==nil then return nil end
    return r.owned
end
M.owned=owned

-- The local player's record: {address, state, key, count, records, entries = {{index, address, type, uses, granted,
-- bytes}}}, or nil, code, reason.
local function local_record(world)
    local lo,hi=world_module.local_peer(world)
    if not lo then return nil,'UNAVAILABLE','the local peer is unknown'end
    local base=world.view.pointer(world.game+R.global)
    local count=base and world.view.u32(base+R.count)
    if not(base and count and count<=64)then return nil,'NO_RECORD','no stratagem records'end
    for index=0,count-1 do
        local record=base+index*R.stride
        if world.view.u32(record)==lo and world.view.u32(record+4)==hi then
            local state=record+R.state
            local n=world.view.u32(state+R.entryCount)
            if not n or n>R.maxEntries then return nil,'NO_RECORD','the record has an unexpected entry count'end
            local entries={}
            for k=0,n-1 do
                local at=state+R.entries+k*R.entryStride
                local bytes=world.view.read(at,R.entryStride)
                if not bytes then return nil,'NO_RECORD','a record entry is unreadable'end
                entries[#entries+1]={index=k,address=at,type=b.u32(bytes,E.type),uses=signed(b.u32(bytes,E.uses)),
                    granted=bytes:byte(E.granted+1),bytes=bytes}
            end
            return {address=record,state=state,key=world.view.read(state+R.key,8),count=n,records=count,entries=entries}
        end
    end
    return nil,'NO_RECORD','the local player has no stratagem record'
end
M.local_record=local_record
-- Every stratagem record the game holds now (one per peer: its peer id and its entries; the game's peer sync fills the
-- others'), read-only, sorted by peer id: {{peer (hex), local (true for this machine's), count, entries = {{index,
-- type, uses, granted}}}}, or nil, code, reason. In a mission each player's record is there (research
-- stratagem-slot-conversion: the per-peer records, the peer sync); aboard the ship other players' are not proven to be.
function M.records(world)
    local lo,hi=world_module.local_peer(world)
    local base=world.view.pointer(world.game+R.global)
    local count=base and world.view.u32(base+R.count)
    if not(base and count and count<=64)then return nil,'NO_RECORD','no stratagem records'end
    local out={}
    for index=0,count-1 do
        local record=base+index*R.stride
        local plo,phi=world.view.u32(record),world.view.u32(record+4)
        local state=record+R.state
        local n=world.view.u32(state+R.entryCount)
        if plo and phi and n and n<=R.maxEntries then
            local entries={}
            for k=0,n-1 do
                local bytes=world.view.read(state+R.entries+k*R.entryStride,R.entryStride)
                if bytes then
                    entries[#entries+1]={index=k,type=b.u32(bytes,E.type),uses=signed(b.u32(bytes,E.uses)),
                        granted=bytes:byte(E.granted+1)}
                end
            end
            out[#out+1]={peer=world_module.peer_hex(plo,phi),['local']=plo==lo and phi==hi,count=n,entries=entries}
        end
    end
    table.sort(out,function(a,c)return a.peer<c.peer end)
    return out
end

-- Whether a call-in of this entry is in flight (the matcher's own test): true / false, or nil when unreadable.
local function in_flight(world,record,index)
    local system=world.view.pointer(world.game+CI.global)
    if not system then return false end
    local count=world.view.u32(system+CI.count)
    if count==nil then return nil end
    if count==0 then return false end
    local entries=world.view.pointer(system+CI.entries)
    if count>512 or not entries then return nil end
    for k=0,count-1 do
        local item=world.view.read(entries+k*CI.stride,CI.stride)
        if not item then return nil end
        if item:sub(CI.key+1,CI.key+8)==record.key and b.u32(item,CI.slot)==index and item:byte(CI.done+1)==0 then
            return true
        end
    end
    return false
end

-- Read-only inspection (the development proof's probe): the record, the token entries and the carrier's checks.
function M.inspect(world,spec)
    local out={}
    local game=world_module.game_state(world)
    out.mission,out.host=game and game.mission or false,game and game.host
    local record,code,reason=local_record(world)
    if not record then out.record={code=code,reason=reason};return out end
    out.records=record.records
    out.entries={}
    for _,entry in ipairs(record.entries)do
        out.entries[#out.entries+1]={index=entry.index,type=entry.type,name=name_of(world,entry.type),uses=entry.uses,
            granted=entry.granted}
    end
    local token=spec and catalog.stratagems[spec.token]
    local carrier=spec and catalog.stratagems[spec.carrier]
    if token and carrier then
        local token_type,carrier_type=loadout.type_of(world,token.root.id),loadout.type_of(world,carrier.root.id)
        out.tokenType,out.carrierType=token_type,carrier_type
        out.tokenEntries={}
        for _,entry in ipairs(record.entries)do
            if entry.granted==0 and entry.type==token_type then out.tokenEntries[#out.tokenEntries+1]=entry.index end
            if entry.type==carrier_type then out.carrierInRecord=true end
        end
        local crow=row(world,carrier_type)
        out.carrierSelectable=crow and math.floor(world.view.u32(crow+ROWM.selectable)/ROWM.selectableBit)%2==1
        out.carrierEnabled=crow and world.view.u32(crow+ROWM.enabled)%2==1
        out.carrierOwned=owned(world,carrier.root.id)
        out.carrierUnlimited=crow and signed(world.view.u32(crow+ROWM.maxUses))==-1
        local dependencies=core_assets.dependencies_for_stratagem(carrier.root.id,spec.carrier)
        local states={}
        for _,dependency in ipairs(dependencies or{})do
            local ok,state=pcall(core_assets.state,world.runtime,dependency.package)
            states[#states+1]=ok and state or'unreadable'
        end
        out.carrierPackage=dependencies and table.concat(states,', ')or'unknown'
    end
    return out
end

------------------------------------------------------------------------------------------------- the jobs --
-- One conversion per key (several custom stratagems convert their own virtual slots to their own carriers in one
-- mission): the virtual definition's id, or '*' for the duplicate-token conversion. Each: {converted, record, index,
-- indices, token, carrier, token_name, carrier_name, key, definition, slots, cooldowns, keeper}. `latest` serves the
-- one-conversion accessors (no definition given).
local conversions={}
local latest
local sentinel
local function pick(definition)
    if definition~=nil then return conversions[definition]end
    return latest
end
-- The other held conversions' entries: {[record entry index] = conversion}.
local function held_entries(except)
    local out={}
    for key,c in pairs(conversions)do
        if key~=except and c.converted then
            for _,index in ipairs(c.indices)do out[index]=c end
        end
    end
    return out
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
        if not ok then handle.status,handle.code,handle.reason='failed','SLOT_FAILED',tostring(result)
        elseif result then for key,value in pairs(result)do handle[key]=value end
        else handle.status,handle.code,handle.reason='refused',code,reason end
        if handle.status~='converted'and handle.status~='restored'then
            log('refused: '..tostring(handle.code)..': '..tostring(handle.reason))
        end
        if callback then callback(handle)end
    end
    scheduler.attach(watch)
    return handle
end

local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base and address+size<=r.base+r.size)
    then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end
-- The 4-byte type change of each entry in `indices` (one transaction), with the record's peer id and its whole entry
-- block and count as context. uses (optional): {[index] = {expected, desired}} also changes each entry's own uses (an
-- Eagle carrier's slot: unlimited -> its uses per rearm, and back).
local function plan_for(world,record,indices,expected,desired,uses)
    local first=record.state+R.entries
    local span=R.entryCount+4-R.entries
    local owner=owner_of(world,record.address,R.state+R.entryCount+4)
    local context=owner and world.view.read(first,span)
    local peer=owner and world.view.read(record.address,8)
    if not(owner and context and peer)then return nil end
    local changes={}
    for _,index in ipairs(indices)do
        changes[#changes+1]={label='stratagem.record.slot'..index..'.type',owner=owner,
            offset=record.entries[index+1].address-owner.base,expected=u32(expected),desired=u32(desired),
            before=u32(expected),already_desired=false,
            identity={component='StratagemRecord',component_type='native',unique_owner=true,owner_count=1},chain={}}
        local u=uses and uses[index]
        if u then
            changes[#changes+1]={label='stratagem.record.slot'..index..'.uses',owner=owner,
                offset=record.entries[index+1].address+E.uses-owner.base,expected=u32(u[1]),desired=u32(u[2]),
                before=u32(u[1]),already_desired=false,
                identity={component='StratagemRecord',component_type='native',unique_owner=true,owner_count=1},chain={}}
        end
    end
    return {snapshots={{owner=owner,offset=record.address-owner.base,bytes=peer},
            {owner=owner,offset=first-owner.base,bytes=context}},changes=changes}
end

-- A plan of uses changes only: uses = {[record entry index] = {expected, desired}} (the type is never written).
local function uses_plan(world,record,uses)
    local first=record.state+R.entries
    local span=R.entryCount+4-R.entries
    local owner=owner_of(world,record.address,R.state+R.entryCount+4)
    local context=owner and world.view.read(first,span)
    local peer=owner and world.view.read(record.address,8)
    if not(owner and context and peer)then return nil end
    local changes={}
    local indices={}
    for index in pairs(uses)do indices[#indices+1]=index end
    table.sort(indices)
    for _,index in ipairs(indices)do
        local u=uses[index]
        changes[#changes+1]={label='stratagem.record.slot'..index..'.uses',owner=owner,
            offset=record.entries[index+1].address+E.uses-owner.base,expected=u32(u[1]),desired=u32(u[2]),
            before=u32(u[1]),already_desired=false,
            identity={component='StratagemRecord',component_type='native',unique_owner=true,owner_count=1},chain={}}
    end
    return {snapshots={{owner=owner,offset=record.address-owner.base,bytes=peer},
            {owner=owner,offset=first-owner.base,bytes=context}},changes=changes}
end

local function same_except(before,after,indices)
    if not after or after.count~=before.count then return false end
    local skip={}
    for _,index in ipairs(indices)do skip[index]=true end
    for k,entry in ipairs(before.entries)do
        if not skip[k-1]and after.entries[k].bytes~=entry.bytes then return false end
    end
    return true
end
local function list_text(indices)
    local parts={}
    for _,index in ipairs(indices)do parts[#parts+1]=tostring(index)end
    return table.concat(parts,', ')
end

-- The carrier's own guards (both conversions): catalogued, different from the token, enabled, selectable, owned, and
-- token and carrier with unlimited uses. Returns the types or nil, code, reason.
local function carrier_checks(world,spec)
    local token,carrier=catalog.stratagems[spec.token],catalog.stratagems[spec.carrier]
    if not(token and token.root and carrier and carrier.root)then
        return nil,'UNKNOWN_STRATAGEM','token and carrier must be catalogued stratagems'
    end
    if token.root.id==carrier.root.id then return nil,'SAME_STRATAGEM','the carrier is the token'end
    local types={token=loadout.type_of(world,token.root.id),carrier=loadout.type_of(world,carrier.root.id),
        tokenId=token.root.id,carrierId=carrier.root.id}
    if not(types.token and types.carrier)then return nil,'UNKNOWN_STRATAGEM','no row carries their stable ids'end
    local trow,crow=row(world,types.token),row(world,types.carrier)
    if not(math.floor(world.view.u32(crow+ROWM.selectable)/ROWM.selectableBit)%2==1
            and world.view.u32(crow+ROWM.enabled)%2==1)then
        return nil,'CARRIER_NOT_SELECTABLE',spec.carrier..' is not an enabled, selectable stratagem'
    end
    local is_owned=owned(world,carrier.root.id)
    if is_owned==nil then return nil,'UNAVAILABLE','the account catalogue is unreadable'end
    if not is_owned then return nil,'CARRIER_NOT_OWNED',spec.carrier..' is not owned'end
    local token_unlimited=signed(world.view.u32(trow+ROWM.maxUses))==-1
    local carrier_unlimited=signed(world.view.u32(crow+ROWM.maxUses))==-1
    if spec.uses~=nil then
        -- An Eagle carrier (limited: uses per rearm): its slot gets its own uses, a fleet member of the record.
        if not(type(spec.uses)=='number'and spec.uses>=1 and spec.uses<=M.MAX_EAGLE_USES and spec.uses%1==0)then
            return nil,'INVALID','uses must be 1..'..M.MAX_EAGLE_USES
        end
        if carrier.family~='eagle'then return nil,'NOT_AN_EAGLE',spec.carrier..' is not an Eagle'end
        if not token_unlimited then return nil,'USES_DIFFER','the token must have unlimited uses'end
        types.uses=spec.uses
        return types
    end
    if not(token_unlimited and carrier_unlimited)then
        return nil,'USES_DIFFER','token and carrier must both have unlimited uses'
    end
    return types
end
M.MAX_EAGLE_USES=20

-- Read-only: the first of `candidates` (stratagem names, in order) that every carrier guard accepts for the token
-- (catalogued and not the token; enabled, selectable, owned; token and carrier unlimited; a known call-in package) and
-- that is not in `present` (a set of stable ids: the saved loadout aboard the ship, the record in a mission). Returns
-- the name and its types, plus every passed-over candidate with its code and reason ({carrier, code, reason}).
function M.choose_carrier(world,token,candidates,present)
    local passed={}
    local proven_ok,proof_why=M.prove(world)
    if not proven_ok then return nil,nil,{{carrier='*',code='UNSUPPORTED_BUILD',reason=tostring(proof_why)}}end
    for _,name in ipairs(candidates or{})do
        local types,code,why=carrier_checks(world,{token=token,carrier=name})
        if types then
            if present and present[types.carrierId]then
                code,why='CARRIER_PRESENT',name..' is in the loadout'
            elseif not(core_assets.dependencies_for_stratagem(types.carrierId,name)and core_assets.call_in_complete(name))
                    then
                code,why='ASSET_UNAVAILABLE','no call-in package is known for '..name
            else
                return name,types,passed
            end
        end
        passed[#passed+1]={carrier=name,code=code,reason=why}
    end
    return nil,nil,passed
end

-- Read-only carrier DISCOVERY from what the account actually owns (no fixed list): every catalogued stratagem type,
-- checked as a carrier for the token. A carrier must be:
--   * catalogued and resolved by stable id (never a type number); not the token; not opts.exclude (e.g. the donor);
--   * selectable, enabled, owned (the availability check's rule) and with unlimited uses (token too);
--   * a normal player-facing call-in: a catalogued family with a call-in (orbital, sentry, emplacement, mine, support,
--     backpack); never mission/objective types, vehicles or exosuits (special semantics, not proven), never eagles
--     (limited uses and rearm);
--   * a known call-in package the Runtime can request; a reviewed native presentation; a native calldown code (1-8
--     directions);
--   * not in opts.present (a set of stable ids: the saved loadout);
--   * with opts.payload = {donor = name}: PAYLOAD-COMPATIBLE with the donor's bombardment pattern
--     (runtime/bombardment_payload.lua compatible: a reviewed BombardmentComponentData record, the row's delivery value
--     equal to the donor's, nothing outside the pattern words differing). Sentries, mines, backpacks, support weapons,
--     strikes and other orbitals are then never carriers.
-- Ranked by class (orbital bombardments, the donor's machinery, first; then other orbitals; then sentries,
-- emplacements and mines; then support weapons and backpacks), then (with opts.payload) by the number of words the
-- pattern changes, then by name. Returns {ready, reason, candidates =
-- {{name, id, type, family, component, class, owned, ownership, selectable, enabled, unlimited, inLoadout, special,
-- package, presentation, code, eligible, reasons = {...}, codes = {...}}}, chosen (the first eligible)}. Each reason has
-- a short code at the same position (in_loadout, not_owned, not_selectable, disabled, limited_use, package_unavailable,
-- special_case, no_call_in_class, no_reviewed_presentation, no_native_code, not_payload_compatible, donor). ready is
-- false (nothing to trust) while the account catalogue does not show the token as owned: early in a session it may not
-- be filled yet.
local CLASS={orbital={BombardmentComponentData=1,OrbitalAbilityComponentData=2},sentry=3,emplacement=3,mine=3,support=4,
    backpack=4}
local SPECIAL_FAMILY={mission='a mission/objective stratagem',vehicle='a vehicle or exosuit (not proven safe)',
    eagle='an eagle (limited uses, rearm)'}
-- opts.eagle (a custom Eagle: its slot gets its own uses per rearm, a fleet member): ONLY Eagles are candidates, their
-- limited uses accepted, each with a reviewed uses-per-rearm field (runtime/carrier_presentation.lua native_uses).
-- The discovery's preconditions on the token and its context: {token_id, exclude, present, payload}, or nil and why.
local function discovery_context(world,token,opts)
    local proven_ok,proof_why=M.prove(world)
    if not proven_ok then return nil,tostring(proof_why)end
    local token_entry=catalog.stratagems[token]
    local token_id=token_entry and token_entry.root and token_entry.root.id
    local token_type=token_id and loadout.type_of(world,token_id)
    if not token_type then return nil,'the token is not a catalogued stratagem with a row'end
    local token_owned=ownership(world,token_id)
    if not(token_owned and token_owned.owned)then
        return nil,'the account catalogue does not show the token '..token..' as owned yet (not filled yet?)'
    end
    local trow=row(world,token_type)
    if signed(world.view.u32(trow+ROWM.maxUses))~=-1 then return nil,'the token has limited uses'end
    local exclude={}
    for _,name in ipairs(opts.exclude or{})do
        local e=catalog.stratagems[name]
        if e and e.root then exclude[e.root.id]=name end
    end
    return {token_id=token_id,exclude=exclude,present=opts.present or{},payload=opts.payload,eagle=opts.eagle==true}
end
-- Every carrier guard on one catalogued stratagem, read now: the candidate table (eligible, reasons, codes), or nil
-- when it has no row on this build or is the token.
local function evaluate(world,name,entry,ctx)
    local P=require('hd2runtime/domains/stratagem_calldown').presentation
    local id=entry.root and entry.root.id
    local kind=id and loadout.type_of(world,id)
    local crow=kind and row(world,kind)
    if not crow or id==ctx.token_id then return nil end
    local c={name=name,id=id,type=kind,family=entry.family,component=entry.rootLink and entry.rootLink.component,
        reasons={},codes={}}
    local function no(code,why)c.reasons[#c.reasons+1]=why;c.codes[#c.codes+1]=code end
    c.selectable=math.floor((world.view.u32(crow+ROWM.selectable)or 0)/ROWM.selectableBit)%2==1
    c.enabled=(world.view.u32(crow+ROWM.enabled)or 0)%2==1
    c.unlimited=signed(world.view.u32(crow+ROWM.maxUses))==-1
    c.ownership=ownership(world,id)
    c.owned=c.ownership~=nil and c.ownership.owned
    c.inLoadout=ctx.present[id]==true
    c.special=SPECIAL_FAMILY[entry.family]
    local class=CLASS[entry.family]
    if type(class)=='table'then class=class[c.component]end
    if ctx.eagle and entry.family=='eagle'then
        -- Eagle mode: an Eagle is a normal carrier (its limited uses are the custom Eagle's own).
        c.special=nil
        class=1
        c.eagle=true
        c.usesPerRearm=require('hd2runtime/runtime/carrier_presentation').native_uses(name)
    end
    c.class=class
    -- The beacon's look (research "beaconPresentation"): the beam colour IS the beacon category (1 red = offensive,
    -- 2 blue = support, 3 yellow = other, 0 none); the ping colour is a separate member. Neither is the family.
    c.beam=world.view.u32(crow+ROWM.beam)
    c.ping=world.view.u32(crow+ROWM.ping)
    c.beamColour=c.beam and D.beacon.beams[c.beam]or'none'
    c.beaconCategory=c.beam and D.beacon.categories[c.beam]or'none'
    c.pingColour=c.ping and(D.beacon.pings[c.ping]or D.beacon.pingOther)or'unreadable'
    -- Every package the mission loader would request for it (a support weapon's comes from its weapon, +0xF8).
    c.package=core_assets.dependencies_for_stratagem(id,name)~=nil and core_assets.call_in_complete(name)
    c.presentation=P.values[tostring(id)]~=nil
    local count=world.view.u32(crow+0x48)
    c.code=count~=nil and count>=1 and count<=8
    if ctx.exclude[id]then no('donor','excluded ('..ctx.exclude[id]..': the donor, not a carrier)')end
    if not c.selectable then no('not_selectable','not selectable')end
    if not c.enabled then no('disabled','not enabled')end
    if not c.owned then no('not_owned','not owned')end
    if ctx.eagle and entry.family~='eagle'then no('not_an_eagle','not an Eagle (a custom Eagle takes Eagles only)')end
    if ctx.eagle and c.eagle and not c.usesPerRearm then no('no_reviewed_uses','no reviewed uses per rearm')end
    if not c.unlimited and not c.eagle then no('limited_use','limited uses')end
    if c.inLoadout then no('in_loadout','in the loadout')end
    if c.special then no('special_case',c.special)end
    if not class and not c.special then no('no_call_in_class','no normal call-in class ('..tostring(entry.family)..')')end
    if not c.package then no('package_unavailable','no known call-in package')end
    if not c.presentation then no('no_reviewed_presentation','no reviewed presentation')end
    if not c.code then no('no_native_code','no native calldown code')end
    if ctx.payload then
        local fits,why=payload.compatible(name,ctx.payload.donor)
        c.payloadCompatible=fits
        c.payloadWords=fits and payload.words(name)or nil
        if not fits then
            no('not_payload_compatible','not payload-compatible with '..tostring(ctx.payload.donor)..'\'s pattern ('
                ..table.concat(why,'; ')..')')
        end
    end
    c.eligible=#c.reasons==0
    return c
end
function M.discover_carriers(world,token,opts)
    opts=opts or{}
    local out={ready=false,candidates={}}
    local ctx,why=discovery_context(world,token,opts)
    if not ctx then out.reason=why;return out end
    out.ready=true
    for name,entry in pairs(catalog.stratagems)do
        local c=evaluate(world,name,entry,ctx)
        if c then out.candidates[#out.candidates+1]=c end
    end
    table.sort(out.candidates,function(a,b)
        if a.eligible~=b.eligible then return a.eligible end
        local ra,rb=a.class or 9,b.class or 9
        if ra~=rb then return ra<rb end
        local wa,wb=a.payloadWords or 99,b.payloadWords or 99
        if wa~=wb then return wa<wb end
        return a.name<b.name
    end)
    for _,c in ipairs(out.candidates)do if c.eligible then out.chosen=c;break end end
    return out
end
-- Read-only: a cached carrier, validated now with exactly the discovery's guards and options (the CURRENT loadout in
-- opts.present). Returns {ready, valid, candidate, codes = {...}, reasons = {...}, reason}: ready false when nothing can
-- be trusted yet (the same preconditions as the discovery); valid false with every failing guard's code and reason.
function M.validate_carrier(world,token,carrier,opts)
    opts=opts or{}
    local ctx,why=discovery_context(world,token,opts)
    if not ctx then return {ready=false,valid=false,codes={},reasons={},reason=why}end
    local entry=catalog.stratagems[carrier]
    if not(entry and entry.root and entry.root.id)then
        return {ready=true,valid=false,codes={'not_catalogued'},reasons={tostring(carrier)..' is not catalogued'}}
    end
    if entry.root.id==ctx.token_id then
        return {ready=true,valid=false,codes={'token'},reasons={'it is the token'}}
    end
    local c=evaluate(world,carrier,entry,ctx)
    if not c then return {ready=true,valid=false,codes={'no_row'},reasons={'no row carries its stable id'}}end
    return {ready=true,valid=c.eligible,candidate=c,codes=c.codes,reasons=c.reasons}
end

-- The record guards: in a mission, host, solo, the carrier in no entry. Returns the record or nil, code, reason.
local function record_checks(world,spec,types)
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','the record is converted in a mission only'end
    -- This machine's OWN record entry: the host, or a client inside the client-write proof (runtime/multiplayer.lua).
    local hcode,hwhy=require('hd2runtime/runtime/multiplayer').host_guard(game,spec.client==true,
        'development proof: host only')
    if hcode then return nil,hcode,hwhy end
    local record,code,reason=local_record(world)
    if not record then return nil,code,reason end
    -- The local player's own record entry, found by its peer id; with several players the converted type reaches peers
    -- only through the game's own record sync (spec.multiplayer: a custom stratagem call, runtime/multiplayer.lua).
    local scode,swhy=require('hd2runtime/runtime/multiplayer').solo_guard(record.records,spec.multiplayer==true,
        'a direct write is not synchronised to peers')
    if scode then return nil,scode,swhy end
    for _,entry in ipairs(record.entries)do
        if entry.type==types.carrier then
            return nil,'CARRIER_IN_RECORD',spec.carrier..' is already in the stratagem record (entry '..entry.index..')'
        end
    end
    return record
end
-- The entry guards: unlimited uses and no call-in in flight. nil when they hold, else code, reason.
local function entry_checks(world,record,entry,what)
    if entry.uses~=-1 then
        return'USES_DIFFER',(what or('entry '..entry.index))..' has '..tostring(entry.uses)..' uses, not unlimited'
    end
    local flying=in_flight(world,record,entry.index)
    if flying==nil then return'UNAVAILABLE','the in-flight call-ins are unreadable'end
    if flying then return'IN_USE','a call-in of entry '..entry.index..' is in flight'end
end

-- The guards that hold both before the package wait and right before the write: the record, the entry, the token pair.
-- The duplicate rule (VirtualSlotProof): the later of at least two token entries.
local function check(world,spec,types)
    local record,code,reason=record_checks(world,spec,types)
    if not record then return nil,code,reason end
    local tokens={}
    for _,entry in ipairs(record.entries)do
        if entry.granted==0 and entry.type==types.token then tokens[#tokens+1]=entry end
    end
    if #tokens<2 then
        return nil,'NO_DUPLICATE_TOKEN','the loadout holds '..#tokens..' '..spec.token..'; a second one is the token'
    end
    local entry=tokens[#tokens]
    code,reason=entry_checks(world,record,entry,'the token entry')
    if code then return nil,code,reason end
    return record,{entry}
end
-- The identity rule (the custom stratagem selector): exactly the loadout slots the Runtime records as virtual instances
-- of the definition, in a mission loadout that is exactly the order they were recorded in (stable ids), each holding
-- the token. The loadout slots are the record's non-granted entries, in order (the save's order).
local function check_virtual(world,spec,types)
    local record,code,reason=record_checks(world,spec,types)
    if not record then return nil,code,reason end
    local picks={}
    for _,entry in ipairs(record.entries)do if entry.granted==0 then picks[#picks+1]=entry end end
    -- Entries another custom stratagem converted hold their carriers: for the identity they are their tokens.
    local others=held_entries(spec.definition)
    if #picks~=#spec.order then
        return nil,'IDENTITY_CHANGED',('the mission loadout holds %d stratagems; the virtual slots were recorded in a '
            ..'loadout of %d'):format(#picks,#spec.order)
    end
    for k,entry in ipairs(picks)do
        local other=others[entry.index]
        local id=(other and entry.type==other.carrier)and loadout.id_of(world,other.token)or loadout.id_of(world,entry.type)
        if id~=spec.order[k]then
            return nil,'IDENTITY_CHANGED',('loadout slot %d holds %s, the virtual slots were recorded with %s there'):format(
                k-1,name_of(world,entry.type),tostring(spec.order[k]))
        end
    end
    local targets={}
    for _,slot in ipairs(spec.slots)do
        local entry=picks[slot+1]
        if others[entry.index]then
            return nil,'SLOT_HELD',('loadout slot %d (entry %d) is converted for %s'):format(slot,entry.index,
                tostring(others[entry.index].definition))
        end
        if entry.type~=types.token then
            return nil,'NOT_TOKEN',('loadout slot %d (entry %d) holds %s, not the token %s'):format(slot,entry.index,
                name_of(world,entry.type),spec.token)
        end
        code,reason=entry_checks(world,record,entry)
        if code then return nil,code,reason end
        targets[#targets+1]=entry
    end
    return record,targets
end

local function finalize()
    local keys={}
    for key,c in pairs(conversions)do if c.converted then keys[#keys+1]=key end end
    table.sort(keys)
    for _,key in ipairs(keys)do
        local co=coroutine.create(function()return M.restore_body(key)end)
        for _=1,10000 do
            if coroutine.status(co)=='dead'then break end
            if not coroutine.resume(co,0)then break end
        end
    end
end
function M.finalize_for_tests()finalize()end
local function arm()
    if sentinel then return end
    local ffi=require('ffi')
    sentinel=ffi.gc(ffi.new('uint8_t[1]'),function()pcall(finalize)end)
end
local function disarm()
    for _,c in pairs(conversions)do if c.converted then return end end
    if sentinel then require('ffi').gc(sentinel,nil);sentinel=nil end
end

-- Watches the converted entries: when the game rebuilds the record (the mission end transition) or the mission ends,
-- the conversion is gone and nothing is left to restore.
local function keep(world,state)
    if state.keeper then state.keeper.cancel()end
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick()
        if watch.status~='active'or not(state and state.converted)then watch.status='complete';return end
        local game=world_module.game_state(world)
        local record=game and game.mission and local_record(world)
        local held=record~=nil
        for _,index in ipairs(state.indices)do
            local entry=record and record.entries[index+1]
            if not(entry and entry.type==state.carrier)then held=false end
        end
        if not held then
            log(('entr%s %s no longer hold%s %s (%s): the game rebuilt the stratagem record; nothing to restore'):format(
                #state.indices==1 and'y'or'ies',list_text(state.indices),#state.indices==1 and's'or'',state.carrier_name,
                game and game.mission and'the record changed'or'the mission ended'))
            state.converted=false
            disarm()
            watch.status='complete'
        end
    end
    state.keeper=watch
    scheduler.attach(watch)
end

-- The shared body: the carrier's guards, the record guards (check_fn), the carrier's call-in package, one guarded
-- transaction for every target entry, the verification, the keeper.
local function convert_body(spec,check_fn,extra)
    local key=extra and extra.definition or'*'
    local current=conversions[key]
    if current and current.converted then
        return nil,'ALREADY_CONVERTED',(#current.indices==1 and'entry %s is'or'entries %s are'):format(
            list_text(current.indices))..' already converted'
    end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local proven_ok,proof_why=M.prove(world)
    if not proven_ok then return nil,'UNSUPPORTED_BUILD',tostring(proof_why)end
    local types,tcode,treason=carrier_checks(world,spec)
    if not types then return nil,tcode,treason end
    local record,targets,reason=check_fn(world,spec,types)
    if not record then return nil,targets,reason end
    -- The carrier's call-in packages first (every one the mission loader would request for it): an unselected
    -- carrier's assets are not resident in a mission.
    local dependencies=core_assets.dependencies_for_stratagem(types.carrierId,spec.carrier)
    if not(dependencies and core_assets.call_in_complete(spec.carrier))then
        return nil,'ASSET_UNAVAILABLE','no call-in package is known for '..spec.carrier
    end
    local all_resident=true
    for _,dependency in ipairs(dependencies)do
        local ok,resident=pcall(core_assets.state,world.runtime,dependency.package)
        if not(ok and resident=='resident')then all_resident=false end
    end
    local package_text='resident'
    if not all_resident and extra and extra.atomic then
        -- An atomic conversion (stratagem_selector.convert_with_payload) never waits once it starts.
        return nil,'NOT_READY','the carrier\'s call-in package is not resident'
    end
    if not all_resident then
        local gate=core_assets.gate(world.runtime,{id='slot-carrier-'..types.carrierId,asset_dependencies=dependencies},
            log_module.emit)
        local waited=0
        while true do
            local dt=coroutine.yield()or 0
            waited=waited+dt
            local result,why_not=gate.tick(dt)
            if result=='ready'then break end
            if result=='failed'or waited>ASSET_TIMEOUT then
                return nil,'ASSET_UNAVAILABLE',tostring(why_not or'the carrier\'s call-in package did not load')
            end
        end
        package_text=('loaded (%.1f s)'):format(waited)
        record,targets,reason=check_fn(world,spec,types)
        if not record then return nil,targets,reason end
    end
    local indices={}
    for _,entry in ipairs(targets)do indices[#indices+1]=entry.index end
    local uses
    if types.uses then
        uses={}
        for _,index in ipairs(indices)do uses[index]={-1,types.uses}end
    end
    local plan=plan_for(world,record,indices,types.token,types.carrier,uses)
    if not plan then return nil,'RECORD_CHANGED','the stratagem record is not in private read-write memory'end
    local report=transaction.apply(world.runtime,plan)
    metrics.count('stratagem_slot.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local state={converted=true,record=record.address,index=indices[1],indices=indices,token=types.token,
        carrier=types.carrier,token_name=spec.token,carrier_name=spec.carrier,key=record.key,
        definition=extra and extra.definition,slots=extra and extra.slots,uses=types.uses}
    conversions[key],latest=state,state
    arm()
    local after=local_record(world)
    -- Each converted entry's cooldown end right after the conversion: the carrier has not been called while it still
    -- holds exactly this (runtime/bombardment_payload.lua). It is an absolute game time, not 0, in a live mission.
    state.cooldowns={}
    for _,index in ipairs(indices)do
        local entry=after and after.entries[index+1]
        state.cooldowns[index]=entry and entry.bytes:sub(E.cooldownEnd+1,E.cooldownEnd+8)
    end
    local all_carrier=after~=nil
    for _,index in ipairs(indices)do
        if not(after and after.entries[index+1].type==types.carrier)then all_carrier=false end
        if types.uses and not(after and after.entries[index+1].uses==types.uses)then all_carrier=false end
    end
    local verify={type=all_carrier,others=same_except(record,after,indices),nonTarget=report.non_target_bytes_unchanged==true,
        protection=report.protection_restored==true}
    local text
    if extra and extra.definition then
        text=('virtual %s: loadout slot%s %s = record entr%s %s: %s (type %d) -> %s (type %d, stable id %d), the local '
            ..'record of %d entries: %d write%s; each entry reads the carrier: %s; every other entry and the count '
            ..'unchanged: %s; non-target bytes unchanged %s; protection restored %s; the carrier\'s call-in package %s; '
            ..'the saved loadout is not written%s'):format(extra.definition,#extra.slots==1 and''or's',
            list_text(extra.slots),#indices==1 and'y'or'ies',list_text(indices),spec.token,types.token,spec.carrier,
            types.carrier,types.carrierId,record.count,report.writes,report.writes==1 and''or's',tostring(verify.type),
            tostring(verify.others),tostring(verify.nonTarget),tostring(verify.protection),package_text,
            types.uses and(('; each entry\'s own uses unlimited -> %d (an Eagle fleet member)'):format(types.uses))or'')
    else
        -- The duplicate conversion's own (live-tested) wording.
        text=('entry %d %s (type %d) -> %s (type %d), the local record of %d entries: %d write; entry reads the '
            ..'carrier: %s; every other entry and the count unchanged: %s; non-target bytes unchanged %s; protection '
            ..'restored %s; the saved loadout is not written'):format(indices[1],spec.token,types.token,spec.carrier,
            types.carrier,record.count,report.writes,tostring(verify.type),tostring(verify.others),
            tostring(verify.nonTarget),tostring(verify.protection))
    end
    for _,key in ipairs({'type','others','nonTarget','protection'})do
        if not verify[key]then
            log('conversion VERIFY FAILED ('..key..'), restoring now: '..text)
            local restored=M.restore_body(state.definition or'*')
            return nil,'VERIFY_FAILED',key..(restored and'; restored'or'; restore refused')
        end
    end
    log('CONVERTED: '..text)
    keep(world,state)
    return {status='converted',index=indices[1],indices=indices,slots=extra and extra.slots,token=types.token,
        carrier=types.carrier,carrierId=types.carrierId,package=package_text,report=report,verify=verify}
end

-- Converts the later duplicate token entry to the carrier. spec: {token = name, carrier = name}. A job: 'pending',
-- then 'converted' (or 'refused' / 'failed' with code and reason).
function M.convert(spec,callback)
    return job(function()
        if type(spec)~='table'then return nil,'BAD_SPEC','spec must be {token = name, carrier = name}'end
        return convert_body(spec,check)
    end,callback)
end

-- Converts exactly the loadout slots of a virtual definition (the custom stratagem selector's identity,
-- runtime/stratagem_selector.lua conversion_spec) to the carrier, in one guarded transaction. spec: {definition (id),
-- token = name, carrier = name, slots = {loadout slot indices, ascending}, order = {the stable ids of the loadout the
-- slots were recorded in, in order}}; spec.reason instead of slots: why no slot is virtual. Every other guard is the
-- duplicate conversion's: in a mission, host, solo; the carrier enabled, selectable, owned and in no entry; token and
-- carrier unlimited, and each entry; no call-in of an entry in flight; the carrier's package resident; the pins.
-- Never another slot: when the mission loadout is not exactly the recorded order, or a slot does not hold the token,
-- nothing is written. A job: 'pending', then 'converted' {indices (record entries), slots} or 'refused' / 'failed'.
local function virtual_body(spec,atomic)
        if type(spec)~='table'or type(spec.definition)~='string'then
            return nil,'BAD_SPEC','spec must name the virtual definition'
        end
        if spec.slots==nil then return nil,'NO_VIRTUAL_SLOT',tostring(spec.reason or'no virtual slot')end
        if type(spec.slots)~='table'or#spec.slots<1 or type(spec.order)~='table'or#spec.order<1
                or#spec.order>R.maxEntries then
            return nil,'BAD_SPEC','spec.slots and spec.order must be non-empty lists'
        end
        local token=catalog.stratagems[spec.token]
        local last=-1
        for _,slot in ipairs(spec.slots)do
            if type(slot)~='number'or slot%1~=0 or slot<=last or slot>=#spec.order then
                return nil,'BAD_SPEC','spec.slots must be ascending loadout slots of the recorded order'
            end
            if not(token and token.root and spec.order[slot+1]==token.root.id)then
                return nil,'BAD_SPEC','the recorded order does not hold the token at loadout slot '..slot
            end
            last=slot
        end
        return convert_body(spec,check_virtual,{definition=spec.definition,slots=spec.slots,atomic=atomic})
end
function M.convert_virtual(spec,callback)
    return job(function()return virtual_body(spec,false)end,callback)
end
-- THE CARRIER-IN-SLOT PROBE (development; runtime/carrier_in_slot.lua): the virtual slots of spec.definition were
-- picked with the CARRIER itself (spec.carrier), not the token, so the mission record already holds it there. Nothing
-- is written: the entries are verified (the recorded loadout order, each slot exactly the carrier with unlimited uses,
-- no call-in in flight, not held by another conversion) and adopted as this definition's conversion, so what reads a
-- conversion (runtime/slot_cooldown.lua, hud_types, observe) finds them. Its restore writes nothing back: the slot is the
-- carrier in the save too. spec = {definition, carrier, slots, order, uses}. Same handle as convert_virtual.
-- spec.uses = N (1..100; probe 0.2.0, research carrier-max-uses option A): each adopted entry's OWN uses -1 -> N, the
-- game's native per-slot count (its HUD counter, its depleted look, its refusal at 0; the game decrements it). One
-- guarded transaction of this player's own record entries only, never the carrier's row (a shared definition) and never
-- another player's record. Extra guards: the carrier row unlimited, its cooldown type 0 (not team-shared), not an Eagle,
-- not type 28 or 124; the carrier type nowhere else in the record (no native entry of it can be touched); read back
-- exactly N. The game rebuilds the record at the mission end and at every launch (the next one starts from the row);
-- a restore while the record still stands writes -1 back.
function M.adopt_virtual(spec,callback)
    return job(function()
        if type(spec)~='table'or type(spec.definition)~='string'or type(spec.slots)~='table'or#spec.slots<1
                or type(spec.order)~='table'then
            return nil,'BAD_SPEC','spec must name the definition, its slots and the recorded order'
        end
        local current=conversions[spec.definition]
        if current and current.converted then return nil,'ALREADY_CONVERTED','its slots are adopted already'end
        local world,why=world_module.open()
        if not world then return nil,'UNAVAILABLE',tostring(why)end
        local ok,proof_why=M.prove(world)
        if not ok then return nil,'UNSUPPORTED_BUILD',tostring(proof_why)end
        local game=world_module.game_state(world)
        if not(game and game.mission)then return nil,'NOT_IN_MISSION','the record is adopted in a mission only'end
        local carrier=catalog.stratagems[spec.carrier]
        local carrier_type=carrier and carrier.root and loadout.type_of(world,carrier.root.id)
        if not carrier_type then return nil,'UNKNOWN_STRATAGEM','no row carries '..tostring(spec.carrier)end
        local record,code,reason=local_record(world)
        if not record then return nil,code,reason end
        local picks={}
        for _,entry in ipairs(record.entries)do if entry.granted==0 then picks[#picks+1]=entry end end
        if#picks~=#spec.order then
            return nil,'IDENTITY_CHANGED',('the mission loadout holds %d stratagems; the slots were recorded in a loadout '
                ..'of %d'):format(#picks,#spec.order)
        end
        for k,entry in ipairs(picks)do
            if loadout.id_of(world,entry.type)~=spec.order[k]then
                return nil,'IDENTITY_CHANGED',('loadout slot %d holds %s, the slots were recorded with %s there'):format(
                    k-1,name_of(world,entry.type),tostring(spec.order[k]))
            end
        end
        local others=held_entries(spec.definition)
        local indices={}
        for _,slot in ipairs(spec.slots)do
            local entry=picks[slot+1]
            if not entry then return nil,'IDENTITY_CHANGED','no loadout slot '..tostring(slot)end
            if others[entry.index]then
                return nil,'SLOT_HELD',('loadout slot %d (entry %d) is converted for %s'):format(slot,entry.index,
                    tostring(others[entry.index].definition))
            end
            if entry.type~=carrier_type then
                return nil,'NOT_CARRIER',('loadout slot %d (entry %d) holds %s, not the carrier %s'):format(slot,
                    entry.index,name_of(world,entry.type),spec.carrier)
            end
            local ecode,ewhy=entry_checks(world,record,entry)
            if ecode then return nil,ecode,ewhy end
            indices[#indices+1]=entry.index
        end
        local state={converted=true,adopted=true,record=record.address,index=indices[1],indices=indices,
            token=carrier_type,carrier=carrier_type,token_name=spec.carrier,carrier_name=spec.carrier,key=record.key,
            definition=spec.definition,slots=spec.slots,cooldowns={}}
        for _,index in ipairs(indices)do
            state.cooldowns[index]=record.entries[index+1].bytes:sub(E.cooldownEnd+1,E.cooldownEnd+8)
        end
        -- The native uses (spec.uses): every guard first, then one transaction; nothing written when any fails.
        local writes=0
        if spec.uses~=nil then
            local n=spec.uses
            if not(type(n)=='number'and n%1==0 and n>=1 and n<=100)then
                return nil,'BAD_SPEC','spec.uses must be a whole number from 1 to 100'
            end
            -- With several players (r38): this machine's own entry, the host or a client inside the client-write proof.
            local hcode,hwhy=require('hd2runtime/runtime/multiplayer').host_guard(game,spec.client==true,
                'the native uses: the session host, or a client inside the client-write proof')
            if hcode then return nil,hcode,hwhy end
            local crow=row(world,carrier_type)
            if not(crow and signed(world.view.u32(crow+ROWM.maxUses))==-1)then
                return nil,'USES_DIFFER',spec.carrier..' does not have unlimited uses: its uses are its own'
            end
            local _,cooldown_type=require('hd2runtime/runtime/slot_cooldown').row_cooldown(world,carrier_type)
            if cooldown_type~=0 then
                return nil,'SHARED_COOLDOWN',spec.carrier..'\'s cooldown type is '..tostring(cooldown_type)
                    ..' (team-shared: its uses are not per entry)'
            end
            if carrier.family=='eagle'or carrier_type==28 or carrier_type==124 then
                return nil,'SPECIAL_USES',spec.carrier..' has the game\'s own special uses (an Eagle, type 28 or 124)'
            end
            local mine={}
            for _,index in ipairs(indices)do mine[index]=true end
            for _,entry in ipairs(record.entries)do
                if entry.type==carrier_type and not mine[entry.index]then
                    return nil,'CARRIER_ELSEWHERE',('record entry %d holds %s too (not this custom stratagem\'s): no uses are '
                        ..'written'):format(entry.index,spec.carrier)
                end
            end
            local uses={}
            for _,index in ipairs(indices)do uses[index]={-1,n}end
            local plan=uses_plan(world,record,uses)
            if not plan then return nil,'RECORD_CHANGED','the stratagem record is not in private read-write memory'end
            local report=transaction.apply(world.runtime,plan)
            metrics.count('stratagem_slot.transactions')
            if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
            local after=local_record(world)
            local exact=after~=nil and same_except(record,after,indices)
            for _,index in ipairs(indices)do
                local e=after and after.entries[index+1]
                if not(e and e.type==carrier_type and e.uses==n)then exact=false end
            end
            writes=report.writes
            state.native_uses=n
            log(('NATIVE USES (carrier-in-slot probe): virtual %s: record entr%s %s (%s) uses -1 -> %d, the game\'s own '
                ..'per-slot count: %d write%s; read back %s; every other entry unchanged; the carrier\'s row and every other '
                ..'record not written'):format(spec.definition,#indices==1 and'y'or'ies',list_text(indices),spec.carrier,n,
                writes,writes==1 and''or's',tostring(exact)))
            if not exact then
                return nil,'VERIFY_FAILED','the entries do not read back exactly '..n..' uses'
            end
        end
        conversions[spec.definition],latest=state,state
        keep(world,state)
        log(('ADOPTED (carrier-in-slot probe): virtual %s: loadout slot%s %s = record entr%s %s already hold the carrier '
            ..'%s (type %d)%s: no slot write; the saved loadout holds it too'):format(spec.definition,
            #spec.slots==1 and''or's',list_text(spec.slots),#indices==1 and'y'or'ies',list_text(indices),spec.carrier,
            carrier_type,state.native_uses and(' with '..state.native_uses..' native uses each')or' with unlimited uses'))
        return {status='converted',adopted=true,index=indices[1],indices=indices,slots=spec.slots,writes=writes,
            native_uses=state.native_uses}
    end,callback)
end
-- The same conversion inside the caller's own job, for stratagem_selector.convert_with_payload: with atomic, it never
-- yields (a package that is not resident refuses it: NOT_READY), so the caller's next step runs in the same tick.
function M.convert_virtual_body(spec,opts)return virtual_body(spec,opts and opts.atomic)end

-- Writes the token back into every converted entry (inside a job or the finalizer): true, or nil and code, reason.
-- definition: whose conversion (a virtual definition's id, '*' for the duplicate one; default the latest).
function M.restore_body(definition)
    local state=pick(definition)
    if not(state and state.converted)then return nil,'NOT_CONVERTED','nothing to restore'end
    -- An adopted slot (the carrier-in-slot probe) keeps its carrier; its native uses (if written) go back to unlimited
    -- while the record still stands (rebuilt, the game re-seeded it from the row: nothing to write).
    if state.adopted then
        local writes=0
        if state.native_uses then
            local world=world_module.open()
            local record=world and local_record(world)
            local held=record~=nil and record.address==state.record and record.key==state.key
            local uses={}
            for _,index in ipairs(state.indices)do
                local e=held and record.entries[index+1]
                if not(e and e.type==state.carrier and e.uses>=0 and e.uses<=state.native_uses)then held=false
                elseif e.uses~=-1 then uses[index]={e.uses,-1}end
            end
            if held and next(uses)then
                local plan=uses_plan(world,record,uses)
                local report=plan and transaction.apply(world.runtime,plan)
                if not(report and report.status=='APPLIED')then
                    return nil,'GUARD_REJECTED','the native uses were not written back: '..tostring(report and report.reason)
                end
                writes=report.writes
            end
            log(('NATIVE USES RELEASED (carrier-in-slot probe): entr%s %s (%s): %s'):format(#state.indices==1 and'y'
                or'ies',list_text(state.indices),state.carrier_name,held and(writes..' write'..(writes==1 and''or's')
                ..' back to unlimited')or'the record was rebuilt (re-seeded from the row): nothing to write'))
        end
        state.converted=false
        if state.keeper then state.keeper.cancel()end
        disarm()
        log(('RELEASED (carrier-in-slot probe): entr%s %s keep the carrier %s (adopted)'):format(
            #state.indices==1 and'y'or'ies',list_text(state.indices),state.carrier_name))
        return {status='restored',index=state.index,indices=state.indices,adopted=true,exact=true,
            report={writes=writes,non_target_bytes_unchanged=true,protection_restored=true}}
    end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local proven_ok,proof_why=M.prove(world)
    if not proven_ok then return nil,'UNSUPPORTED_BUILD',tostring(proof_why)end
    local record,code,reason=local_record(world)
    if not record then return nil,code,reason end
    for _,index in ipairs(state.indices)do
        local entry=record.entries[index+1]
        if not(record.address==state.record and entry and entry.type==state.carrier)then
            state.converted=false;disarm()
            return nil,'GONE','the game rebuilt the stratagem record; nothing to restore'
        end
    end
    for _,index in ipairs(state.indices)do
        local flying=in_flight(world,record,index)
        if flying~=false then return nil,'IN_USE','a call-in of entry '..index..' is in flight'end
    end
    local uses
    if state.uses then
        uses={}
        for _,index in ipairs(state.indices)do
            local now=record.entries[index+1].uses
            if now~=-1 then uses[index]={now,-1}end
        end
    end
    local plan=plan_for(world,record,state.indices,state.carrier,state.token,uses)
    if not plan then return nil,'RECORD_CHANGED','the stratagem record is not in private read-write memory'end
    local report=transaction.apply(world.runtime,plan)
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    state.converted=false
    disarm()
    local after=local_record(world)
    local exact=after~=nil and same_except(record,after,state.indices)
    for _,index in ipairs(state.indices)do
        if not(after and after.entries[index+1].type==state.token)then exact=false end
        if state.uses and not(after and after.entries[index+1].uses==-1)then exact=false end
    end
    log(('RESTORED: entr%s %s %s -> %s: %d write%s; exact: %s; non-target bytes unchanged %s; protection restored %s')
        :format(#state.indices==1 and'y'or'ies',list_text(state.indices),state.carrier_name,state.token_name,
        report.writes,report.writes==1 and''or's',tostring(exact),tostring(report.non_target_bytes_unchanged),
        tostring(report.protection_restored)))
    return {status='restored',index=state.index,indices=state.indices,report=report,exact=exact}
end
function M.restore(callback,definition)return job(function()return M.restore_body(definition)end,callback)end

-- Read-only: whether the HUD slot drawing the (first) converted entry now holds the carrier (the vanilla type-change
-- refresh).
function M.hud_follows(world,definition)
    local state=pick(definition)
    if not(state and state.converted)then return nil end
    local located=stratagem_hud.locate(world,state.carrier)
    return located~=nil and located.index==state.index,located and located.index
end
-- Read-only: the HUD list's type in each converted entry's slot (the HUD draws entry k in its slot k): {[index] =
-- type}, or nil when the HUD is not set up.
function M.hud_types(world,definition)
    local state=pick(definition)
    if not(state and state.indices)then return nil end
    local hud=world.view.pointer(world.game+HUD.global)
    local set_up=hud and world.view.read(hud+HUD.setUp,1)
    if not(set_up and set_up:byte()==1)then return nil end
    local out={}
    for _,index in ipairs(state.indices)do
        out[index]=world.view.u32(hud+HUD.pathOffset+index*HUD.slots.stride+HUD.slots.type)
    end
    return out
end
-- Read-only: each converted entry now: {index, type, uses, cooldown (its 8 cooldown-end bytes), flying}.
function M.observe(world,definition)
    local state=pick(definition)
    if not(state and state.indices)then return nil end
    local record=local_record(world)
    if not record then return nil end
    local out={}
    for _,index in ipairs(state.indices)do
        local entry=record.entries[index+1]
        if entry then
            out[#out+1]={index=index,type=entry.type,uses=entry.uses,
                cooldown=entry.bytes:sub(E.cooldownEnd+1,E.cooldownEnd+8),flying=in_flight(world,record,index)}
        end
    end
    return out
end
function M.state(definition)return pick(definition)end
-- Every conversion still held, sorted by key: {conversion, ...}.
function M.conversions()
    local keys,out={},{}
    for key,c in pairs(conversions)do if c.converted then keys[#keys+1]=key end end
    table.sort(keys)
    for k,key in ipairs(keys)do out[k]=conversions[key]end
    return out
end
function M.reset_for_tests()
    for _,c in pairs(conversions)do if c.keeper then c.keeper.cancel()end end
    conversions,latest={},nil
    disarm()
    proven={}
end
return M
