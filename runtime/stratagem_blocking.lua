-- The game's own BLOCKED stratagem card state, for vanilla carrier stratagems a selected custom stratagem reserves
-- (docs/research/stratagem-blocking-F5FEE03DCFDB.md; research/stratagem-blocking-F5FEE03DCFDB.json). Development
-- module: not exported by api/hd2.lua; its caller (the custom stratagem owner) computes the reservations.
--
-- What the game does for an item Arrowhead disables: the online override data sets the catalogue item's disabled flag;
-- when the stratagem grid opens for a slot the grid builder copies that flag into each card's list entry (the BLOCKED
-- byte, card list + 0x92EC2 + i). That entry byte alone draws the native treatment (the overlay icon element, the card
-- at 50% opacity, the red frame) and makes both select paths refuse the card (no pick, no sound). This module sets
-- THAT UI-LOCAL BYTE, per card, for exactly the reserved carriers, and never the catalogue flag (server data):
--   * apply(world, blocked): blocked = {[stable id] = {reason, holders = {text}}} (the caller ref-counts; collect()
--     builds it from reservations). While the grid is open (a selection open on a stratagem slot, the list in its
--     stratagem mode) every card whose key is a blocked carrier's key gets its blocked byte 0 -> 1, and a card this
--     module blocked whose carrier is no longer blocked gets 1 -> 0 (only where the catalogue flag is 0: a card Arrowhead
--     disabled stays as the game has it). Cards not in the set are never touched. Idempotent: call it every update.
--   * the game rebuilds the list (from the catalogue) at every grid open and clears it on close: a rebuilt entry no
--     longer reads what this module wrote, its ownership is dropped and the next apply sets it again.
--   * a visible card shows the byte on its next realize; after a change this module sets the list's one-shot realize
--     request (+0x928FA, the flag the game itself sets to realize on the next frame; the per-frame list update consumes
--     it, the list clear zeroes it), 0 -> 1 only, while the scrollbar is idle and the screen shows its grid.
--   * every write is one guarded transaction (core/guarded_transaction.lua): the expected byte, the list's count, mode
--     and the keys around the targets as context, the loadout UI's private read-write allocation as the owner, read
--     back. No hook, no patch, no native call; no StratagemInfo, catalogue, account, inventory or save write.
--   * not reproduced: the details panel's "DISABLED" notice and button lock (they read the catalogue flag only).
-- Logs: "STRATAGEM BLOCKED (native)" when a stable id enters the blocked set, "STRATAGEM UNBLOCKED (native)" when it
-- leaves it (after its cards are restored); one line per grid change and per refusal reason.
local transaction=require('hd2runtime/core/guarded_transaction')
local log_module=require('hd2runtime/runtime/log')
local metrics=require('hd2runtime/runtime/metrics')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local D=require('hd2runtime/domains/stratagem_blocking')
local M={}
local L,G,C=D.loadout,D.grid,D.catalogue
local PRIVATE,COMMIT,READWRITE=0x20000,0x1000,4
M.REQUEST_TIMEOUT=1      -- seconds (apply's dt; 1/30 s per call without one) before an unconsumed request is reported

local function log(text)log_module.emit('[HD2Runtime] '..text)end
local function signed(n)return n and n>=2147483648 and n-4294967296 or n end

-- {[stable id] = {reason, holders}}: the set apply() was last given (each logged BLOCKED once).
local wanted={}
-- Ids that left the set while a card this module blocked for them is not restored yet: UNBLOCKED is logged once none is.
local leaving={}
-- The cards this module blocked: {ui, list, entries = {[index] = {id, key}}}; nil when none.
local owned
-- The realize request this module wrote and has not seen consumed: {ui, list, age}.
local request
local refused={}         -- [code] = the reason last logged (one line per reason)
local game_seen={}       -- [ui..':'..id] = true: a card the game itself blocks (logged once)
local first_consumed=false
local proven={}

function M.prove(world)
    if D.source.gameDllSha256~=profile.dll_sha or D.source.exeSha256~=profile.exe_sha then
        return nil,'the stratagem blocking research covers another game build'
    end
    if proven[world.key or world.game]then return true end
    for _,pin in ipairs(D.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,('stratagem grid code changed (%s at game+%X)'):format(pin.label,pin.rva)
        end
    end
    proven[world.key or world.game]=true
    return true
end

--------------------------------------------------------------------------------------------------------- names --
local names
local function name_of(id)
    if not names then
        names={}
        local ok,catalog=pcall(require,'hd2runtime/domains/stratagem_authoring')
        for name,entry in pairs(ok and catalog.stratagems or{})do
            if type(entry)=='table'and entry.root and entry.root.id then names[entry.root.id]=name end
        end
    end
    return names[id]or('stratagem 0x%08X'):format(id)
end
local function label(id)return('%s (0x%08X)'):format(name_of(id),id)end
local function holders_text(spec)
    local h=spec and spec.holders or{}
    return #h>0 and table.concat(h,', ')or'no holder named'
end

-------------------------------------------------------------------------------------------------- reading --
local function byte(world,at)local s=world.view.read(at,1);return s and s:byte()end
local function qword(world,at)
    local s=world.view.read(at,8)
    return s and b.u32(s,0)+b.u32(s,4)*4294967296
end
-- The native grid as the game holds it: {open = false} without an open stratagem grid; otherwise {open = true, ui, list,
-- edited, mode, count, keys = {[i] = key}, blocked = {[i] = 0|1|...}, enabled = {[i] = 0|1|...}, shown, request,
-- scrollbar}; or nil and why.
function M.grid(world)
    local owner=world.view.pointer(world.game+L.ownerGlobal)
    local ui=owner and qword(world,owner+L.root)
    if not owner or not ui or ui==0 then return {open=false}end
    local selecting,sub,edited=byte(world,ui+L.selectionOpen),world.view.u32(ui+L.subState),world.view.u32(ui+L.editedSlot)
    if not(selecting and sub and edited)then return nil,'the loadout screen is unreadable'end
    edited=signed(edited)
    if not(selecting~=0 and sub==L.gridSubState and edited>=0 and edited<L.maxLoadoutEntries)then
        return {open=false,ui=ui}
    end
    local list=ui+L.list
    local mode,count=world.view.u32(list+G.mode),world.view.u32(list+G.count)
    local flags=world.view.read(list+G.scrollMoved,G.requestContext)
    local shown=byte(world,ui+L.screen+G.shown)
    if not(mode and count and flags and shown)or count>G.maxCards then return nil,'the card list is unreadable'end
    local out={open=true,ui=ui,list=list,edited=edited,mode=mode,count=count,keys={},blocked={},enabled={},
        shown=shown~=0,request=flags:byte(G.realizeRequest-G.scrollMoved+1),
        scrollbar=flags:byte(G.scrollbarActive-G.scrollMoved+1)}
    if count>0 then
        local keys,bytes=world.view.read(list+G.keys,count*4),world.view.read(list+G.blocked,count)
        local enabled=world.view.read(list+G.enabled,count)
        if not(keys and bytes and enabled)then return nil,'the card list is unreadable'end
        for i=0,count-1 do
            out.keys[i],out.blocked[i],out.enabled[i]=b.u32(keys,i*4),bytes:byte(i+1),enabled:byte(i+1)
        end
    end
    return out
end

-- The catalogue record of a stratagem stable id, as the grid builder finds it (its stratagem range; the FIRST record
-- with that id): {key, definition, disabled (the server flag)}, or nil and why. Read only.
function M.card_of(world,id)
    local cat=world.view.pointer(world.game+C.global)
    if not cat then return nil,'the account catalogue is not set'end
    local first,last=world.view.u32(cat+C.rangeFirst),world.view.u32(cat+C.rangeLast)
    if not(first and last and first<=last and last-first<=0x1000)then return nil,'the catalogue range is unreadable'end
    for position=first,last-1 do
        local index=world.view.u32(cat+C.index+position*4)
        local record=index and cat+C.records+index*C.recordStride
        if record and world.view.u32(record+C.recordId)==id then
            local key,definition=world.view.u32(record+C.recordKey),world.view.u32(record+C.recordDefinition)
            local disabled=definition and byte(world,cat+C.definitions+definition*C.definitionStride+C.disabled)
            if not(key and disabled)then return nil,'the catalogue record is unreadable'end
            return {key=key,definition=definition,disabled=disabled}
        end
    end
    return nil,'not in the catalogue\'s stratagem range (not owned or unknown)'
end

-- The loadout UI's allocation, as the guarded transaction checks it: committed private read-write memory holding the UI
-- object and its card list through the blocked array.
local function owner_of(world,ui,list)
    local r=world.runtime.query and world.runtime.query(list)
    if not(r and r.state==COMMIT and r.type==PRIVATE and r.protect==READWRITE)then return nil end
    if not(r.allocation_base<=ui and list>=r.base and list+G.blocked+G.maxCards<=r.base+r.size)then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=PRIVATE,protect=READWRITE}
end

------------------------------------------------------------------------------------------------- outcomes --
local function refuse(code,reason)
    metrics.count('stratagem_blocking.refused')
    if refused[code]~=reason then
        refused[code]=reason
        log(('stratagem blocking REFUSED (nothing written): %s: %s'):format(code,tostring(reason)))
    end
    return {status='refused',code=code,reason=reason}
end
local function copy(blocked)
    local out={}
    for id,spec in pairs(blocked or{})do
        local holders={}
        for k,h in ipairs(type(spec)=='table'and spec.holders or{})do holders[k]=tostring(h)end
        out[id]={reason=type(spec)=='table'and spec.reason or nil,holders=holders}
    end
    return out
end
local function same_holders(a,c)
    if #a.holders~=#c.holders or a.reason~=c.reason then return false end
    for k=1,#a.holders do if a.holders[k]~=c.holders[k]then return false end end
    return true
end
local function sorted_ids(set)
    local out={}
    for id in pairs(set)do out[#out+1]=id end
    table.sort(out)
    return out
end
local function names_of(list)
    local seen,out={},{}
    for _,e in ipairs(list)do if not seen[e.id]then seen[e.id]=true;out[#out+1]=name_of(e.id)end end
    return table.concat(out,', ')
end

-- The guarded transaction over the blocked bytes (or, field = 'enabled', the enabled bytes) of the given entries
-- ({index, from, to}): the list's mode and count, the keys and those bytes from the first to the last target as context.
local function write_cards(world,g,owner,entries,field)
    local array=field=='enabled'and G.enabled or G.blocked
    local name=field=='enabled'and'enabled'or'blocked'
    local first,last=math.huge,-1
    for _,e in ipairs(entries)do first=math.min(first,e.index);last=math.max(last,e.index)end
    local function snap(at,n)
        local bytes=world.view.read(at,n)
        return bytes and{owner=owner,offset=at-owner.base,bytes=bytes}or nil
    end
    local mode,count=snap(g.list+G.mode,4),snap(g.list+G.count,4)
    local keys,bytes=snap(g.list+G.keys+first*4,(last-first+1)*4),snap(g.list+array+first,last-first+1)
    if not(mode and count and keys and bytes)then return nil,'the card list is unreadable'end
    local changes={}
    for _,e in ipairs(entries)do
        local from,to=string.char(e.from),string.char(e.to)
        changes[#changes+1]={label=('stratagem_grid.card%d.%s'):format(e.index,name),owner=owner,
            offset=g.list+array+e.index-owner.base,expected=from,desired=to,before=from,already_desired=false,
            identity={component='StratagemGridCard',component_type='native',unique_owner=true,owner_count=1},chain={}}
    end
    local report=transaction.apply(world.runtime,{snapshots={mode,count,keys,bytes},changes=changes})
    metrics.count('stratagem_blocking.transactions')
    if report.status~='APPLIED'then return nil,'guard rejected: '..tostring(report.reason)end
    metrics.count('stratagem_blocking.cards_written',#entries)
    return report
end

-- The one-shot realize request: 0 -> 1 while the screen shows its grid and the scrollbar is idle. Returns what was done.
local function request_realize(world,g,owner)
    if not g.shown then return'skipped (the screen does not show its grid)'end
    if g.request~=0 then return'already pending (the game realizes next frame)'end
    if g.scrollbar~=0 then return'not needed (the scrollbar is dragged: the list realizes every frame)'end
    local ctx=world.view.read(g.list+G.scrollMoved,G.requestContext)
    if not ctx then return'skipped (unreadable)'end
    local report=transaction.apply(world.runtime,{snapshots={{owner=owner,offset=g.list+G.scrollMoved-owner.base,
        bytes=ctx}},changes={{label='stratagem_grid.realize_request',owner=owner,
        offset=g.list+G.realizeRequest-owner.base,expected='\0',desired='\1',before='\0',already_desired=false,
        identity={component='StratagemGridList',component_type='native',unique_owner=true,owner_count=1},chain={}}}})
    metrics.count('stratagem_blocking.transactions')
    if report.status~='APPLIED'then return'refused ('..tostring(report.reason)..')'end
    request={ui=g.ui,list=g.list,age=0}
    metrics.count('stratagem_blocking.realize_requests')
    return'requested'
end
local function watch_request(world,g,dt)
    if not request then return end
    if not(g and g.open and g.ui==request.ui)then request=nil;return end   -- the list was cleared: the clear zeroes it
    if g.request==0 then
        metrics.count('stratagem_blocking.realize_consumed')
        if not first_consumed then
            first_consumed=true
            log('stratagem blocking: the native grid consumed the realize request (the visible cards were refilled)')
        end
        request=nil
        return
    end
    request.age=request.age+(dt or 1/30)
    if request.age>=M.REQUEST_TIMEOUT then
        log(('stratagem blocking: the realize request was not consumed within %g s (the grid\'s per-frame update did '
            ..'not run); a blocked card shows its look on the next scroll; the refusal applies regardless'):format(
            M.REQUEST_TIMEOUT))
        request=nil
    end
end

----------------------------------------------------------------------------------------------------- apply --
-- The set's own transitions: BLOCKED for an id that enters it, the reservation line when its holders change.
local function announce(blocked)
    for _,id in ipairs(sorted_ids(blocked))do
        local spec,before=blocked[id],wanted[id]or leaving[id]
        leaving[id]=nil
        if not before then
            log(('STRATAGEM BLOCKED (native): %s: %s; reserved by %s (%d); the native picker shows it blocked and refuses '
                ..'it while the stratagem grid is open'):format(label(id),tostring(spec.reason or'reserved as a carrier'),
                holders_text(spec),#spec.holders))
        elseif not same_holders(before,spec)then
            log(('stratagem blocking: %s: reserved by %s (%d)'):format(label(id),holders_text(spec),#spec.holders))
        end
    end
end
local function holds(id)
    for _,e in pairs(owned and owned.entries or{})do if e.id==id then return true end end
    return false
end
local function unannounce(blocked,restored)
    for id,spec in pairs(wanted)do if not blocked[id]then leaving[id]=spec end end
    for _,id in ipairs(sorted_ids(leaving))do
        if not holds(id)then
            leaving[id]=nil
            local n=restored[id]or 0
            log(('STRATAGEM UNBLOCKED (native): %s: no reservation left%s'):format(label(id),
                n>0 and(' (%d card%s restored)'):format(n,n==1 and''or's')or''))
        end
    end
end

-- Applies the blocked set to the open grid (see the header). Returns {status = 'applied' | 'idle' | 'refused', grid
-- (open), blocked = n cards blocked by this module now, wrote, restored, native = {ids the game itself blocks},
-- missing = {[id] = why}, realize, code, reason}.
function M.apply(world,blocked,dt)
    blocked=copy(blocked)
    -- Unproven code: nothing is read further, written or announced (the set is offered again next time).
    local ok,why=M.prove(world)
    if not ok then return refuse('UNPROVEN',why)end
    announce(blocked)
    local restored_by_id={}
    local function finish(result)
        unannounce(blocked,restored_by_id)
        wanted=blocked
        return result
    end
    local g,gwhy=M.grid(world)
    if not g then return finish(refuse('UNREADABLE',gwhy))end
    watch_request(world,g,dt)
    if owned and not(g.open and g.ui==owned.ui and g.list==owned.list)then
        -- The grid closed or the UI changed: the game cleared the list (and with it every byte written here).
        metrics.count('stratagem_blocking.cleared_by_game')
        owned=nil
    end
    if not g.open then return finish({status='idle',grid=false,blocked=0})end
    if g.mode~=G.stratagemMode then
        return finish(refuse('LIST_MODE',('the card list is in mode %s, not the stratagem list (%d)'):format(
            tostring(g.mode),G.stratagemMode)))
    end
    local own=owned or{ui=g.ui,list=g.list,entries={}}
    -- Entries the game rebuilt (another key there, or no longer the byte written here): not ours any more.
    for index,e in pairs(own.entries)do
        if index>=g.count or g.keys[index]~=e.key or g.blocked[index]~=1 then
            own.entries[index]=nil
            metrics.count('stratagem_blocking.rebuilt_entries')
        end
    end
    local by_key={}
    for i=0,g.count-1 do
        local k=g.keys[i]
        if k and k~=0 then by_key[k]=by_key[k]or{};by_key[k][#by_key[k]+1]=i end
    end
    local block,restore,native,missing={},{},{},{}
    for _,id in ipairs(sorted_ids(blocked))do
        local card,cwhy=M.card_of(world,id)
        if not card then missing[id]=cwhy
        elseif not by_key[card.key]then missing[id]='no card in the open grid'
        else
            for _,i in ipairs(by_key[card.key])do
                if not own.entries[i]then
                    if g.blocked[i]==0 then block[#block+1]={index=i,id=id,key=card.key,from=0,to=1}
                    else
                        native[#native+1]=id
                        local seen=g.ui..':'..id
                        if not game_seen[seen]then
                            game_seen[seen]=true
                            log(('stratagem blocking: %s is already blocked by the game (%s): left as the game has it'):format(
                                label(id),card.disabled~=0 and'Arrowhead\'s online override'or'its blocked byte reads '
                                ..tostring(g.blocked[i])))
                        end
                    end
                end
            end
        end
    end
    for index,e in pairs(own.entries)do
        if not blocked[e.id]then
            local card=M.card_of(world,e.id)
            if card and card.key==e.key and card.disabled==0 then
                restore[#restore+1]={index=index,id=e.id,key=e.key,from=1,to=0}
            else
                own.entries[index]=nil      -- the game itself wants it blocked now: never cleared here
            end
        end
    end
    table.sort(block,function(x,y)return x.index<y.index end)
    table.sort(restore,function(x,y)return x.index<y.index end)
    local result={status='applied',grid=true,native=native,missing=missing,wrote=0,restored=0}
    if #block+#restore>0 then
        local owner=owner_of(world,g.ui,g.list)
        if not owner then
            owned=next(own.entries)and own or nil
            return finish(refuse('NOT_PRIVATE','the loadout UI is not in committed private read-write memory'))
        end
        local entries={}
        for _,e in ipairs(block)do entries[#entries+1]=e end
        for _,e in ipairs(restore)do entries[#entries+1]=e end
        if #entries>128 then return finish(refuse('TOO_MANY','more than 128 cards would change at once'))end
        local report,wwhy=write_cards(world,g,owner,entries)
        if not report then
            owned=next(own.entries)and own or nil
            return finish(refuse('GUARD_REJECTED',wwhy))
        end
        refused={}
        for _,e in ipairs(block)do own.entries[e.index]={id=e.id,key=e.key}end
        for _,e in ipairs(restore)do
            own.entries[e.index]=nil
            restored_by_id[e.id]=(restored_by_id[e.id]or 0)+1
        end
        result.wrote,result.restored=#block,#restore
        -- The visible cards realized before this write: ask the game for its next-frame realize.
        local fresh=M.grid(world)
        result.realize=fresh and fresh.open and request_realize(world,fresh,owner)or'skipped (the grid changed)'
        local parts={}
        if #block>0 then parts[#parts+1]=('blocked %d card%s (%s)'):format(#block,#block==1 and''or's',names_of(block))end
        if #restore>0 then
            parts[#parts+1]=('restored %d card%s (%s)'):format(#restore,#restore==1 and''or's',names_of(restore))
        end
        log(('stratagem blocking: native grid (slot %d): %s; blocked byte card list+0x%X (guarded, %d write%s, '
            ..'non-target bytes unchanged %s, protection restored %s); realize %s'):format(g.edited,
            table.concat(parts,'; '),G.blocked,report.writes,report.writes==1 and''or's',
            tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored),result.realize))
    end
    owned=next(own.entries)and own or nil
    local n=0
    for _ in pairs(own.entries)do n=n+1 end
    result.blocked=n
    return finish(result)
end

-- Unblocks every card this module blocked (restored exactly) and forgets the set: apply with nothing blocked.
function M.release(world,dt)return M.apply(world,{},dt)end

-------------------------------------------------------------------------------------------------- the doubles --
-- THE CARRIER-IN-SLOT PROBE'S DOUBLES (0.3.0; the user's rule of 2026-10-07: a custom carrier slot never locks its
-- carrier out). The game greys every type the edited record already holds: the card's ENABLED byte (card list +
-- 0x92DC2 + i), 0 from the grid build and from the grey refresh after every pick; both select paths refuse a greyed card
-- exactly as a blocked one. Stratagem MultiSelect (a research lead only, docs/research/multi-stratagem-select-
-- F5FEE03DCFDB.md) re-enables greyed cards with the game's card-enable call and the game then puts the same stratagem in
-- several slots. The Runtime writes that UI-local byte itself (no native call), 0 -> 1, for exactly the carriers in
-- `enable` = {[stable id] = {definition, slots = {loadout slots holding it as a custom carrier}}}, while the grid is open:
--   * never while the grid edits one of those slots (a native pick of it there could not be told apart from the custom
--     one); never a card blocked (this module's block or the game's), never one whose catalogue flag is set;
--   * re-applied every update (the game re-greys after each pick); a card leaving the set gets its grey back (1 -> 0)
--     only while the edited record still holds its type (the game's own state otherwise: left as it is);
--   * the same guarded transaction as the block (the list's mode, count, keys and bytes as context), then the one-shot
--     realize request.
-- A native pick of it then doubles the stratagem; custom_stratagems moves the custom slot to its next carrier aboard
-- the ship (probe_move_step). Logs: "STRATAGEM PICKABLE (native)" once per id entering the set.
local doubles={owned=nil,wanted={},refused=nil}
local function record_types(world,ui)
    local ok,screen=pcall(function()return require('hd2runtime/runtime/stratagem_selector').screen(world)end)
    local types={}
    if ok and screen and screen.open and screen.ui==ui and screen.record then
        for _,e in ipairs(screen.record.entries)do if e.type then types[e.type]=true end end
        return types
    end
    return nil
end
function M.enable(world,enable,dt)
    enable=enable or{}
    local ok,why=M.prove(world)
    if not ok then return {status='refused',code='UNPROVEN',reason=why}end
    for _,id in ipairs(sorted_ids(enable))do
        if not doubles.wanted[id]then
            local spec=enable[id]
            log(('STRATAGEM PICKABLE (native, the carrier-in-slot probe): %s: held by your custom stratagem %s itself '
                ..'(loadout slot%s %s); it stays pickable in your other slots (the game\'s "already in this loadout" grey '
                ..'lifted while the grid edits another slot); picking it moves the custom slot to its next carrier'):format(
                label(id),tostring(spec.definition),#(spec.slots or{})==1 and''or's',table.concat(spec.slots or{},', ')))
        end
    end
    doubles.wanted=enable
    local g,gwhy=M.grid(world)
    if not g then return {status='refused',code='UNREADABLE',reason=gwhy}end
    local own=doubles.owned
    if own and not(g.open and g.ui==own.ui and g.list==own.list)then own=nil end
    if not g.open then doubles.owned=nil;return {status='idle',grid=false,enabled=0}end
    if g.mode~=G.stratagemMode then doubles.owned=nil;return {status='idle',grid=true,enabled=0}end
    own=own or{ui=g.ui,list=g.list,entries={}}
    for index,e in pairs(own.entries)do
        if index>=g.count or g.keys[index]~=e.key or g.enabled[index]~=1 then own.entries[index]=nil end
    end
    local by_key={}
    for i=0,g.count-1 do
        local k=g.keys[i]
        if k and k~=0 then by_key[k]=by_key[k]or{};by_key[k][#by_key[k]+1]=i end
    end
    local open_up,grey={},{}
    for _,id in ipairs(sorted_ids(enable))do
        local spec=enable[id]
        local editing=false
        for _,slot in ipairs(spec.slots or{})do if slot==g.edited then editing=true end end
        local card=M.card_of(world,id)
        if card and card.disabled==0 and by_key[card.key]and not editing then
            for _,i in ipairs(by_key[card.key])do
                if not own.entries[i]and g.enabled[i]==0 and g.blocked[i]==0 then
                    open_up[#open_up+1]={index=i,id=id,key=card.key,from=0,to=1}
                end
            end
        end
    end
    local types
    for index,e in pairs(own.entries)do
        local spec=enable[e.id]
        local editing=false
        for _,slot in ipairs(spec and spec.slots or{})do if slot==g.edited then editing=true end end
        if not spec or editing then
            types=types or record_types(world,g.ui)
            local kind=require('hd2runtime/runtime/stratagem_loadout').type_of(world,e.id)
            if types and kind and types[kind]then grey[#grey+1]={index=index,id=e.id,key=e.key,from=1,to=0}
            else own.entries[index]=nil end
        end
    end
    table.sort(open_up,function(x,y)return x.index<y.index end)
    table.sort(grey,function(x,y)return x.index<y.index end)
    local result={status='applied',grid=true,wrote=0,greyed=0}
    if #open_up+#grey>0 then
        local owner=owner_of(world,g.ui,g.list)
        local entries={}
        for _,e in ipairs(open_up)do entries[#entries+1]=e end
        for _,e in ipairs(grey)do entries[#entries+1]=e end
        local report,wwhy
        if owner then report,wwhy=write_cards(world,g,owner,entries,'enabled')
        else wwhy='the loadout UI is not in committed private read-write memory'end
        if not report then
            doubles.owned=next(own.entries)and own or nil
            if doubles.refused~=wwhy then
                doubles.refused=wwhy
                log('stratagem doubles REFUSED (nothing written; the game\'s grey stays): '..tostring(wwhy))
            end
            return {status='refused',code='GUARD_REJECTED',reason=wwhy}
        end
        doubles.refused=nil
        for _,e in ipairs(open_up)do own.entries[e.index]={id=e.id,key=e.key}end
        for _,e in ipairs(grey)do own.entries[e.index]=nil end
        result.wrote,result.greyed=#open_up,#grey
        local fresh=M.grid(world)
        result.realize=fresh and fresh.open and request_realize(world,fresh,owner)or'skipped (the grid changed)'
        local parts={}
        if #open_up>0 then parts[#parts+1]=('pickable %d card%s (%s)'):format(#open_up,#open_up==1 and''or's',
            names_of(open_up))end
        if #grey>0 then parts[#parts+1]=('greyed again %d card%s (%s)'):format(#grey,#grey==1 and''or's',
            names_of(grey))end
        log(('stratagem doubles: native grid (slot %d): %s; enabled byte card list+0x%X (guarded, %d write%s, non-target '
            ..'bytes unchanged %s, protection restored %s); realize %s'):format(g.edited,table.concat(parts,'; '),
            G.enabled,report.writes,report.writes==1 and''or's',tostring(report.non_target_bytes_unchanged),
            tostring(report.protection_restored),result.realize))
    end
    doubles.owned=next(own.entries)and own or nil
    local n=0
    for _ in pairs(own.entries)do n=n+1 end
    result.enabled=n
    return result
end

-- The ref count: reservations = {{carrier = stable id, holder = text, reason = text}} (one per custom stratagem
-- instance / slot / teammate reserving a carrier). Returns the blocked set for apply(): {[stable id] = {reason (the
-- first given), holders = {distinct holder texts, sorted}}}; a carrier stays blocked while any holder remains.
function M.collect(reservations)
    local out,seen={},{}
    for _,r in ipairs(reservations or{})do
        local id=type(r)=='table'and tonumber(r.carrier)
        if id and id>0 then
            local spec=out[id]or{reason=r.reason,holders={}}
            out[id]=spec
            spec.reason=spec.reason or r.reason
            local h=tostring(r.holder or'a custom stratagem')
            seen[id]=seen[id]or{}
            if not seen[id][h]then seen[id][h]=true;spec.holders[#spec.holders+1]=h end
        end
    end
    for _,spec in pairs(out)do table.sort(spec.holders)end
    return out
end

-- {blocked = {[id] = {reason, holders}} (the last set), cards = {[index] = {id, key}} (blocked by this module now), ui,
-- request (pending)}.
function M.state()
    local cards={}
    for i,e in pairs(owned and owned.entries or{})do cards[i]={id=e.id,key=e.key}end
    return {blocked=copy(wanted),cards=cards,ui=owned and owned.ui,request=request~=nil}
end

function M.reset_for_tests()
    wanted,leaving,owned,request,refused,game_seen,first_consumed,proven,names={},{},nil,nil,{},{},false,{},nil
    doubles={owned=nil,wanted={},refused=nil}
end

return M
