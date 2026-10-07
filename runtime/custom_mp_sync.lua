-- Custom stratagem multiplayer state over the Runtime peer channel (EXPERIMENTAL; research/docs/runtime-peer-messaging-
-- F5FEE03DCFDB.md, sections 3 and 10). The channel (runtime/peer_channel.lua: the game's own PlayFab lobby member
-- data) is live-proven between two Runtimes: both directions, the session peer ids, a 225-byte value, in a mission.
--
-- Each machine publishes its CURRENT custom picks as its one member value (protocol hd2rt/1, runtime/peer_protocol.lua):
--   hd2rt/1;<runtime version>;<registry hash>;<seq>;<slot0>,<slot1>,<slot2>,<slot3>[;host:<table hash>:<carrier hash>]
-- A slot is a registered custom stratagem id or '-' (a vanilla slot). The value is state, not an event: a selection, a
-- replacement, a clear, a reset loadout or a new lobby all just change what is published (seq + 1); an unchanged value
-- is never posted again (the channel's rate limit and failure cutoff apply). Only the session host adds the host field.
-- In a mission a member also lists the items its own custom calls delivered (items: custom id, the call's beacon
-- network id, the delivered launchers' network ids; runtime/custom_mp_items.lua): every other compatible Runtime
-- correlates them through its own network id map (entity ids differ between machines, network ids do not).
--
-- Each machine reads every lobby member's value (every POLL_SHIP / POLL_MISSION s) and keeps, per member:
--   * compatible: the same protocol, Runtime version and registry hash, every id registered here: its slots count;
--   * incompatible (another version or registry), invalid (malformed, or an id not registered here: its custom state is
--     ignored, never trusted), missing (no value: no Runtime peer channel there, or its first post still waits);
--   * a value with a lower seq than one already read from that member is stale and ignored.
-- The sender is always the lobby member the value was read from, never anything in the value.
-- Custom multiplayer is ENABLED only while every lobby member is compatible (this development build requires every
-- member to run a compatible Runtime). Then every machine holds the same canonical table peer -> slot -> custom id, its
-- hash, and computes the same carrier map from it (runtime/custom_stratagems.lua); the host publishes both hashes and
-- each client compares its own (M.agreement). Nothing in this module writes the game.
local channel=require('hd2runtime/runtime/peer_channel')
local P=require('hd2runtime/runtime/peer_protocol')
local log_module=require('hd2runtime/runtime/log')
local M={}
M.POLL_SHIP,M.POLL_MISSION=2,5
M.MISSING_GRACE=45       -- s a member may have no value before custom multiplayer is reported unavailable
M.STALE_GRACE=30         -- s after a mission end a member's pre-mission state may stand before it is used anyway
M.READ_ERROR_GRACE=10    -- s a member whose value cannot be read keeps its last state before it is invalid
M.SLOTS=4

local mine={seq=0}       -- this machine's state: version, registry, slots {[0..3] = id or false}, host, seq, value
local peers={}           -- [peer hex] = {state, seq, value, slots, host, version, registry, reason, first}
local view               -- the last view (M.poll)
local next_poll=0
local said={}
local function log(text)log_module.emit('[HD2Runtime] '..text)end
local function say(key,text)
    if said[key]==text then return false end
    said[key]=text
    log(text)
    return true
end
function M.reset_for_tests()mine,peers,view,next_poll,said={seq=0},{},nil,0,{};M.reset_reads()end

local function slots_of(list)
    local out={}
    for slot=0,M.SLOTS-1 do out[slot]=list and list[slot]or false end
    return out
end
local function slots_text(slots)
    local out={}
    for slot=0,M.SLOTS-1 do out[slot+1]=slots and slots[slot]or'-'end
    return table.concat(out,',')
end
M.slots_text=slots_text

-- The items of this machine's own custom calls ({{id, beacon, items}}: network ids), as text (for comparing and logs).
local function items_text(list)
    local out={}
    for k,e in ipairs(list or{})do
        local nets={}
        for j,n in ipairs(e.items)do nets[j]=tostring(n)end
        out[k]=('%s@%d=%s'):format(e.id,e.beacon,table.concat(nets,'+'))
    end
    return table.concat(out,',')
end
M.items_text=items_text
local function calls_text(list)
    local out={}
    for k,c in ipairs(list or{})do out[k]=('%s@%d#%d=%d:%s'):format(c.id,c.beacon,c.seq,c.slot,c.carrier)end
    return table.concat(out,',')
end
M.calls_text=calls_text
local function copy_calls(list)
    local out={}
    for k,c in ipairs(list or{})do out[k]={id=c.id,beacon=c.beacon,seq=c.seq,slot=c.slot,carrier=c.carrier}end
    return out
end
local function copy_items(list)
    local out={}
    for k,e in ipairs(list or{})do
        local items={}
        for j,n in ipairs(e.items)do items[j]=n end
        out[k]={id=e.id,beacon=e.beacon,items=items}
    end
    return out
end

-- This machine's state. spec = {version, registry, slots = {[0..3] = id or false}, host = {table, carrier} or nil,
-- items = {{id, beacon, items}} (in a mission: its own calls' delivered items, newest last) or nil}. Published (seq + 1)
-- only when something in it changed. A value too long for the protocol drops its OLDEST item calls first. Returns the
-- channel's outcome, or nil when unchanged.
function M.publish(spec)
    local slots=slots_of(spec.slots)
    local host=spec.host and{table=spec.host.table,carrier=spec.host.carrier}or nil
    local items=copy_items(spec.items)
    while#items>P.MAX_ITEM_CALLS do table.remove(items,1)end
    local calls=copy_calls(spec.calls)
    while#calls>P.MAX_CALLS do table.remove(calls,1)end
    local same=mine.value~=nil and mine.version==spec.version and mine.registry==spec.registry
        and slots_text(mine.slots)==slots_text(slots)
        and((mine.host==nil and host==nil)or(mine.host and host and mine.host.table==host.table
        and mine.host.carrier==host.carrier))
        and items_text(mine.items)==items_text(items)and calls_text(mine.calls)==calls_text(calls)
    -- spec.force: posted even when unchanged (once after a mission end: every peer reads fresh ship state, a new seq).
    if same and not spec.force then return nil end
    local list={}
    for slot=0,M.SLOTS-1 do list[slot+1]=slots[slot]end
    local value,code,why
    while true do
        value,code,why=P.encode({version=spec.version,registry=spec.registry,seq=mine.seq+1,slots=list,host=host,
            items=items,calls=calls})
        if value or code~='TOO_LONG'or#items==0 then break end
        table.remove(items,1)
    end
    if not value then
        say('encode','CUSTOM MP: this machine\'s state cannot be published: '..tostring(code)..': '..tostring(why))
        return {status='refused',code=code,reason=why}
    end
    mine={seq=mine.seq+1,version=spec.version,registry=spec.registry,slots=slots,host=host,items=items,calls=calls,
        value=value}
    return channel.publish(value,channel.OWNER)
end
function M.mine()return mine end

-- One member's value as read now (nil: none). known: the ids registered here.
local function process(peer,value,opts,now)
    local p=peers[peer]
    if not p then p={first=now,state='missing'};peers[peer]=p end
    if value==nil then
        if p.state~='missing'and p.value then
            -- A member whose value disappeared (it left and came back, or restarted): read afresh.
            p.seq,p.value,p.slots,p.host=nil,nil,nil,nil
        end
        p.state,p.reason='missing','no hd2rt value (no Runtime peer channel there, or its first post still waits)'
        return
    end
    if value==p.value then return end
    local s,code,why=P.decode(value)
    if not s then
        p.value,p.state,p.reason,p.slots,p.host,p.items,p.calls=value,'invalid',tostring(code)..': '..tostring(why),nil,
            nil,nil,nil
        return
    end
    if p.seq and s.seq<p.seq then
        say('stale:'..peer,('CUSTOM MP: %s: a stale value (seq %d after %d) is ignored'):format(peer,s.seq,p.seq))
        return
    end
    if p.seq and s.seq==p.seq and p.state~='invalid'then
        say('seq:'..peer,('CUSTOM MP: %s: another value with the same seq %d is ignored'):format(peer,s.seq))
        return
    end
    p.value,p.seq,p.version,p.registry,p.host=value,s.seq,s.version,s.registry,s.host
    if p.stale_seq and s.seq>p.stale_seq then p.stale_seq,p.stale_at=nil,nil end
    local ok,field=P.compatible({version=opts.version,registry=opts.registry},s)
    if not ok then
        p.state,p.slots,p.items,p.calls='incompatible',nil,nil,nil
        p.reason=('%s differs: theirs %s, mine %s'):format(field,field=='runtime version'and s.version or s.registry,
            field=='runtime version'and opts.version or opts.registry)
        return
    end
    local k,kcode,kwhy=P.decode(value,opts.known)
    if not k then
        p.state,p.slots,p.items,p.calls,p.reason='invalid',nil,nil,nil,tostring(kcode)..': '..tostring(kwhy)
        return
    end
    local slots={}
    for slot=0,M.SLOTS-1 do slots[slot]=k.slots[slot+1]end
    p.state,p.slots,p.items,p.calls,p.reason='compatible',slots,copy_items(k.items),copy_calls(k.calls),nil
    -- Every call request a member publishes, logged once when first read here (whatever happens to it next).
    for _,c in ipairs(p.calls)do
        say('calls:'..peer..'#'..c.seq,('CUSTOM MP CALLS READ: peer %s publishes call request seq %d: custom %s, beacon '
            ..'network id %d, loadout slot %d, carrier hash %s (value seq %d)'):format(peer,c.seq,c.id,c.beacon,c.slot,
            tostring(c.carrier),s.seq))
    end
end

local function state_line(v)
    local parts={}
    for k,peer in ipairs(v.members)do
        local tag=('P%d %s'):format(k,peer)
        local who={}
        if peer==v.local_peer then who[#who+1]='you'end
        if peer==v.host_peer then who[#who+1]='host'end
        if#who>0 then tag=tag..' ('..table.concat(who,', ')..')'end
        local text
        if peer==v.local_peer then text=slots_text(mine.slots)
        else
            local p=v.peers[peer]or{state='missing',reason='not read yet'}
            if p.state=='compatible'then text=slots_text(p.slots)
            elseif p.state=='missing'then text='no hd2rt value'
            else text=p.state:upper()..' ('..tostring(p.reason)..')'end
        end
        parts[#parts+1]=tag..': '..text
    end
    return table.concat(parts,'; ')
end

-- Reads every member's value (at most every POLL_SHIP / POLL_MISSION s) and composes the view, on EVERY call, from this
-- machine's CURRENT state and every member's last accepted one. The view is a fresh snapshot: its table, its slots and
-- its per-member states are copies, never the mutable reading state (a caller may freeze it). opts = {mission, known =
-- {[id] = true}, version, registry, verbose, fast}. The view: {status = 'solo' | 'waiting' | 'unavailable' | 'enabled',
-- reason, members (sorted peers), local_peer, host_peer, is_host, lobby, peers ({[peer] = {state, seq, slots, host,
-- items ({{id, beacon, items}}: a compatible member's; empty otherwise), reason}}),
-- table ({[peer] = {[0..3] = id or false}}: the compatible members and this machine), table_hash, host_hashes ({table,
-- carrier}: the session host's), local_seq, local_posted (this machine's current state posted)}.
-- Why composed every call (the live crash of 2026-10-04): a view cached between reads kept this machine's row from
-- before a publish in the same Runtime step, so the carriers were allocated without this machine's own new picks.
local lobby_read      -- the last lobby read: {members, local_peer, host_peer, is_host, id} or {error}
local posted_seq=0    -- the last seq this machine saw posted
local function copy_slots(slots)
    local out={}
    for slot=0,M.SLOTS-1 do out[slot]=slots and slots[slot]or false end
    return out
end
local function compose(now,opts)
    local where=opts.mission and'mission'or'aboard the ship'
    if not lobby_read or lobby_read.error then
        local v={status='solo',reason=lobby_read and lobby_read.error or'the lobby has not been read yet',members={},
            peers={},table={},local_seq=mine.seq}
        return v
    end
    local members=lobby_read.members
    local v={members={},local_peer=lobby_read.local_peer,host_peer=lobby_read.host_peer,is_host=lobby_read.is_host,
        lobby=lobby_read.id,peers={},table={},local_seq=mine.seq,
        local_posted=mine.value~=nil and channel.status().posted==mine.value}
    for k,peer in ipairs(members)do v.members[k]=peer end
    local bad,waiting={},{}
    -- The members running ANOTHER custom stratagem registry or Runtime version, or naming ids not registered here: custom
    -- stratagems are then disabled lobby-wide (0.30 fail closed; the full registry hash is the compatibility contract).
    v.incompatible={}
    for _,peer in ipairs(members)do
        if peer~=v.local_peer then
            local q=peers[peer]or{state='missing',first=now}
            v.peers[peer]={state=q.state,seq=q.seq,reason=q.reason,slots=q.slots and copy_slots(q.slots)or nil,
                host=q.host and{table=q.host.table,carrier=q.host.carrier}or nil,
                items=q.state=='compatible'and copy_items(q.items)or{},
                calls=q.state=='compatible'and copy_calls(q.calls)or{}}
            if q.stale_seq and q.state=='compatible'then
                if now-(q.stale_at or now)<M.STALE_GRACE then
                    waiting[#waiting+1]=peer..' (its state after the mission)'
                else
                    say('stale:'..peer..'#'..tostring(q.stale_seq),('CUSTOM MP: %s posted nothing new within %d s of the '
                        ..'mission end: its last state (seq %d) is used'):format(peer,M.STALE_GRACE,q.stale_seq))
                    q.stale_seq,q.stale_at=nil,nil
                end
            end
            if q.state=='missing'then
                if now-(q.first or now)<M.MISSING_GRACE then waiting[#waiting+1]=peer
                else bad[#bad+1]=peer..': no hd2rt value (no compatible Runtime there, or its posts fail)'end
            elseif q.state~='compatible'then
                bad[#bad+1]=peer..': '..q.state..' ('..tostring(q.reason)..')'
                if q.state=='incompatible'or q.state=='invalid'then
                    v.incompatible[#v.incompatible+1]={peer=peer,state=q.state,reason=tostring(q.reason)}
                end
            end
        end
    end
    local found_local=false
    for _,peer in ipairs(members)do found_local=found_local or peer==v.local_peer end
    if#members<=1 then v.status,v.reason='solo','one lobby member'
    elseif not found_local then v.status,v.reason='waiting','this machine is not among the lobby members read'
    elseif#bad>0 then v.status,v.reason='unavailable',table.concat(bad,'; ')
    elseif#waiting>0 then v.status,v.reason='waiting','waiting for the value of '..table.concat(waiting,', ')
    elseif not mine.value then v.status,v.reason='waiting','this machine has published nothing yet'
    else v.status='enabled'end
    if v.status=='enabled'then
        -- This machine's row is its CURRENT state (the one it publishes), every other member's its last accepted one.
        v.table[v.local_peer]=copy_slots(mine.slots)
        for _,peer in ipairs(members)do
            if peer~=v.local_peer then v.table[peer]=copy_slots(v.peers[peer].slots)end
        end
        v.table_hash=P.table_hash(v.table)
        if v.is_host then
            v.host_hashes=mine.host and{table=mine.host.table,carrier=mine.host.carrier}or nil
        else
            local h=v.peers[v.host_peer]
            v.host_hashes=h and h.state=='compatible'and h.host or nil
        end
        for _,peer in ipairs(members)do
            local q=v.peers[peer]
            if peer~=v.host_peer and q and q.host then
                say('host:'..peer,('CUSTOM MP: %s publishes a host field but is not the session host (%s): ignored')
                    :format(peer,tostring(v.host_peer)))
            end
        end
    end
    local line=('CUSTOM MP STATE (%s, lobby %s): %s'):format(where,tostring(v.lobby),state_line(v))
    if v.status=='enabled'then
        line=line..('; custom multiplayer ENABLED: %d compatible Runtimes (%s, registry %s); table hash %s'):format(
            #members,tostring(opts.version),tostring(opts.registry),v.table_hash)
    elseif v.status=='unavailable'then
        line=line..'; custom multiplayer UNAVAILABLE: '..v.reason..'. Vanilla gameplay is untouched; this build then '
            ..'keeps its earlier behaviour (the host runs its own custom calls, a client none): a player without a '
            ..'compatible Runtime can coexist as vanilla-only'
    elseif v.status=='waiting'then line=line..'; custom multiplayer WAITING: '..v.reason
    else line=line..'; solo'end
    say('state',line)
    -- This machine's own publishing: queued while the channel's rate limits hold it, then posted.
    local items=(#(mine.items or{})>0 and('; items '..items_text(mine.items))or'')
        ..(#(mine.calls or{})>0 and('; calls '..calls_text(mine.calls))or'')
    if mine.value and v.local_posted and posted_seq~=mine.seq then
        posted_seq=mine.seq
        log(('CUSTOM MP PUBLISH posted seq %d: %s%s'):format(mine.seq,slots_text(mine.slots),items))
    elseif mine.value and not v.local_posted and opts.verbose then
        say('queued',('CUSTOM MP PUBLISH queued seq %d: %s%s (the newest state; posted at the next allowed post)'):format(
            mine.seq,slots_text(mine.slots),items))
    end
    view=v
    return v
end
-- opts.fast: read every POLL_FAST s instead (a mission waiting for another member's call items: a remote custom
-- delivery seen here; reading a member value is a local read of the game's lobby state, not a request).
M.POLL_FAST=0.5
function M.poll(world,now,opts)
    if now>=next_poll or(opts.fast and now>=next_poll-(opts.mission and M.POLL_MISSION or M.POLL_SHIP)+M.POLL_FAST)then
        next_poll=now+(opts.mission and M.POLL_MISSION or M.POLL_SHIP)
        local p,code,why=channel.poll(world)
        if not p then
            lobby_read={error=tostring(code)..': '..tostring(why)}
        else
            local lobby=p.lobby
            if lobby_read and lobby_read.id and lobby.id~=lobby_read.id then
                log(('CUSTOM MP: another lobby (%s -> %s): the state of every member is read afresh'):format(
                    tostring(lobby_read.id),tostring(lobby.id)))
                peers={}
            end
            local members,present={},{}
            for _,m in ipairs(lobby.members)do members[#members+1]=m.peer;present[m.peer]=true end
            table.sort(members)
            -- A member that left is forgotten (if it comes back, its value is read afresh).
            for peer in pairs(peers)do if not present[peer]then peers[peer]=nil end end
            for _,entry in ipairs(p.values)do
                if entry.error then
                    -- A read error is the transport (a value read while the game rewrites it), not the member's state:
                    -- the member keeps its last state for M.READ_ERROR_GRACE s. Unreadable for longer, it is invalid
                    -- (fail closed), and its cached value is dropped so that its next good read is processed afresh,
                    -- never skipped as unchanged (a member was otherwise left invalid until it posted a new state).
                    local q=peers[entry.peer]or{first=now,state='missing'}
                    peers[entry.peer]=q
                    q.read_error_at=q.read_error_at or now
                    if now-q.read_error_at>=M.READ_ERROR_GRACE then
                        q.state,q.reason,q.slots,q.value='invalid',entry.error,nil,nil
                    end
                else
                    if peers[entry.peer]then peers[entry.peer].read_error_at=nil end
                    process(entry.peer,entry.value,opts,now)
                end
            end
            lobby_read={members=members,local_peer=lobby.local_peer,host_peer=lobby.host_peer,is_host=lobby.is_host,
                id=lobby.id}
        end
    end
    return compose(now,opts)
end
function M.view()return view end
-- The mission ended (the lobby may persist): every member's state read so far is from before or during the mission; it is
-- not used until that member posts newer state (each Runtime posts once after its return to the ship) or M.STALE_GRACE s
-- pass. The view is composed afresh at the next poll.
function M.mission_ended(now)
    for _,p in pairs(peers)do
        if p.seq then p.stale_seq,p.stale_at=p.seq,now end
        p.items,p.calls={},{}
    end
    next_poll,view=0,nil
end
-- Forgets the lobby read (the next poll reads afresh); keeps this machine's published state.
function M.reset_reads()lobby_read,posted_seq,next_poll,view=nil,0,0,nil end

-- The sorted unique custom ids of a table (the definitions the lobby allocation covers).
function M.table_ids(t)
    local set,out={},{}
    for _,slots in pairs(t or{})do
        for slot=0,M.SLOTS-1 do local id=slots[slot];if id and not set[id]then set[id]=true;out[#out+1]=id end end
    end
    table.sort(out)
    return out
end

-- The native selections of a lobby, deterministically from the game's own records and the synced table (the same on
-- every machine): every record entry counts except a loadout slot the table names as a custom slot of that record's
-- player (whatever it holds: the token, or a carrier its owner converted and the game synced). Granted entries
-- (mission defaults) always count. records = {{peer, entries = {{index, type, granted}}}}; id_of(type) -> stable id.
-- Returns present ({[stable id] = true}) and the custom entries ({{peer, slot, index, type, id}}).
function M.native_present(records,t,id_of)
    local present,custom={},{}
    local list={}
    for _,r in ipairs(records or{})do list[#list+1]=r end
    table.sort(list,function(a,c)return a.peer<c.peer end)
    for _,r in ipairs(list)do
        local picks=t and t[r.peer]
        local entries={}
        for _,e in ipairs(r.entries)do entries[#entries+1]=e end
        table.sort(entries,function(a,c)return a.index<c.index end)
        local slot=0
        for _,e in ipairs(entries)do
            local id
            if e.granted==0 then
                id=picks and picks[slot]or nil
                slot=slot+1
            end
            if id then custom[#custom+1]={peer=r.peer,slot=slot-1,index=e.index,type=e.type,id=id}
            else
                local sid=id_of(e.type)
                if sid then present[sid]=true end
            end
        end
    end
    return present,custom
end

-- A client's agreement with the host: {status = 'host' | 'waiting' | 'agree' | 'differ' | 'unavailable', field, host,
-- mine}. carrier_hash nil: the table only.
function M.agreement(v,table_hash,carrier_hash)
    if not(v and v.status=='enabled')then return {status='unavailable'}end
    if v.is_host then return {status='host'}end
    local h=v.host_hashes
    if not h then return {status='waiting',reason='the session host has published no hashes yet'}end
    if h.table~=table_hash then return {status='differ',field='table',host=h.table,mine=table_hash}end
    if carrier_hash and h.carrier~=carrier_hash then
        return {status='differ',field='carrier',host=h.carrier,mine=carrier_hash}
    end
    return {status='agree'}
end
return M
