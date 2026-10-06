-- The Runtime peer protocol hd2rt/1 (DEVELOPMENT; docs/research/runtime-peer-messaging-F5FEE03DCFDB.md, section 3):
-- the one value each machine publishes as its lobby member property (runtime/peer_channel.lua). Pure: no game access.
--
--   hd2rt/1;<runtime version>;<registry hash>;<seq>;<slot0>,<slot1>,<slot2>,<slot3>[;host:<table hash>:<carrier hash>]
--     [;items:<id>@<beacon>=<item>[+<item>...][,<id>@<beacon>=...]]
--     [;calls:<id>@<beacon>#<call seq>=<slot>:<carrier hash>[,...]]
--
-- It is STATE, not a message: the last value a member published is what every member reads, so a join, a reconnect or a
-- reopened loadout screen always sees the whole state. Every field is semantic: a version, a hash, a counter, custom
-- stratagem ids (or '-'), and in a mission the game's own NETWORK ids of the items this member's custom calls delivered
-- (items: which custom stratagem, the network id of the call's beacon, the network ids of the entities its call made:
-- launchers, a barrage, a Pelican and its chin turret; the same on every machine), and a call this member asks the
-- session host to run for it (calls: which custom stratagem, its beacon's network id, the call's sequence number, the
-- loadout slot it was called from, the carrier map hash it was converted with). Nothing in it is an address, an offset, a type number or a value to write: a receiver resolves
-- a network id through its own network id map, checks the entity against its own registered definition and derives
-- every change from that definition. decode accepts nothing else: a value that does not match the grammar exactly is
-- refused whole, never partly applied or guessed at. The sender is never in the value: the receiver takes it from the
-- lobby member it read.
local bit=require('bit')
local M={}
M.PROTOCOL='hd2rt/1'
M.SLOTS=4
M.MAX=512
M.MAX_SEQ=2147483647
M.MAX_ITEM_CALLS=4       -- items: calls listed at most (the newest)
M.MAX_ITEMS=8            -- items: delivered items per call at most (a pod rack's slots)
M.MAX_NETWORK=32766      -- a game network id (0x7FFF is the game's "none")
M.MAX_CALLS=4            -- calls: requests listed at most (the newest)
local TWO32=4294967296

-- FNV-1a 32 of a string, as 8 uppercase hex digits (the multiply split so it stays exact in doubles).
function M.fnv1a(text)
    local h=2166136261
    for i=1,#text do
        h=bit.bxor(h,text:byte(i))%TWO32
        h=((h%256)*16777216+h*403)%TWO32
    end
    return string.format('%08X',h)
end

local function id_ok(id)return type(id)=='string'and#id<=48 and id:match('^[a-z][a-z0-9_]*$')~=nil end
M.id_ok=id_ok
local function hash_ok(h)return type(h)=='string'and h:match('^%x%x%x%x%x%x%x%x$')~=nil and h==h:upper()end
local function version_ok(v)return type(v)=='string'and#v>=1 and#v<=32 and v:match('^[%w%.%+%-]+$')~=nil end

-- The registry hash: every registered custom stratagem's id with what the carrier allocation reads of it (its carrier
-- policy and payload family, as canonical text), sorted, one line each. defs: {{id, policy, family}}.
function M.registry_hash(defs)
    local lines={}
    for _,d in ipairs(defs or{})do lines[#lines+1]=tostring(d.id)..'|'..tostring(d.policy or'')..'|'
        ..tostring(d.family or'')end
    table.sort(lines)
    return M.fnv1a(table.concat(lines,'\n'))
end
-- The lobby table hash: {[peer hex] = {[slot 0..3] = id}}, every 'peer:slot=id' sorted.
function M.table_hash(t)
    local lines={}
    for peer,slots in pairs(t or{})do
        for slot,id in pairs(slots)do if id then lines[#lines+1]=('%s:%d=%s'):format(peer,slot,id)end end
    end
    table.sort(lines)
    return M.fnv1a(table.concat(lines,'\n'))
end
-- The carrier map hash: {[id] = carrier stable id}, every 'id=stable id' sorted.
function M.carrier_hash(map)
    local lines={}
    for id,stable in pairs(map or{})do lines[#lines+1]=id..'='..tostring(stable)end
    table.sort(lines)
    return M.fnv1a(table.concat(lines,'\n'))
end

local function network_ok(n)return type(n)=='number'and n%1==0 and n>=1 and n<=M.MAX_NETWORK end
local function network_of(text)
    if not(text:match('^[1-9]%d?%d?%d?%d?$'))then return nil end
    local n=tonumber(text)
    return network_ok(n)and n or nil
end
-- The items field's text: {{id, beacon (network id), items = {network ids}}}, or nil, reason.
local function items_text(list)
    if#list>M.MAX_ITEM_CALLS then return nil,'at most '..M.MAX_ITEM_CALLS..' calls'end
    local entries={}
    for k,e in ipairs(list)do
        if type(e)~='table'or not id_ok(e.id)or not network_ok(e.beacon)then
            return nil,'call '..k..' must be {id, beacon network id, items}'
        end
        if type(e.items)~='table'or#e.items<1 or#e.items>M.MAX_ITEMS then
            return nil,'call '..k..' must list 1..'..M.MAX_ITEMS..' item network ids'
        end
        local nets={}
        for j,n in ipairs(e.items)do
            if not network_ok(n)then return nil,'call '..k..' item '..j..' is not a network id'end
            nets[j]=tostring(n)
        end
        entries[k]=e.id..'@'..e.beacon..'='..table.concat(nets,'+')
    end
    return 'items:'..table.concat(entries,',')
end

-- The calls field's text: {{id, beacon, seq, slot, carrier}}, or nil, reason.
local function calls_text(list)
    if#list>M.MAX_CALLS then return nil,'at most '..M.MAX_CALLS..' calls'end
    local out={}
    for k,c in ipairs(list)do
        if type(c)~='table'or not id_ok(c.id)or not network_ok(c.beacon)or not(type(c.seq)=='number'and c.seq>=1
            and c.seq<=M.MAX_SEQ and c.seq%1==0)or not(type(c.slot)=='number'and c.slot>=0 and c.slot<M.SLOTS
            and c.slot%1==0)or not hash_ok(c.carrier)then
            return nil,'call '..k..' must be {id, beacon network id, seq, slot 0..3, carrier hash}'
        end
        out[k]=('%s@%d#%d=%d:%s'):format(c.id,c.beacon,c.seq,c.slot,c.carrier)
    end
    return 'calls:'..table.concat(out,',')
end

-- state = {version, registry, seq, slots = {[1..4] = id or false}, host = {table, carrier} (the host only), items =
-- {{id, beacon, items}} (in a mission: this member's own calls' entities, newest last; empty or nil: none), calls =
-- {{id, beacon, seq, slot, carrier}} (in a mission: calls this member asks the host to run; empty or nil: none)}.
-- Returns the value, or nil, code, reason.
function M.encode(state)
    if type(state)~='table'then return nil,'INVALID','the state must be a table'end
    if not version_ok(state.version)then return nil,'INVALID','the runtime version must be 1-32 of [A-Za-z0-9.+-]'end
    if not hash_ok(state.registry)then return nil,'INVALID','the registry hash must be 8 uppercase hex digits'end
    local seq=state.seq
    if not(type(seq)=='number'and seq>=1 and seq<=M.MAX_SEQ and seq%1==0)then
        return nil,'INVALID','seq must be an integer 1..'..M.MAX_SEQ
    end
    local slots={}
    for k=1,M.SLOTS do
        local id=state.slots and state.slots[k]
        if id==nil or id==false then slots[k]='-'
        elseif id_ok(id)then slots[k]=id
        else return nil,'INVALID','slot '..(k-1)..' must be a custom stratagem id or empty'end
    end
    local text=('%s;%s;%s;%d;%s'):format(M.PROTOCOL,state.version,state.registry,seq,table.concat(slots,','))
    if state.host~=nil then
        if not(type(state.host)=='table'and hash_ok(state.host.table)and hash_ok(state.host.carrier))then
            return nil,'INVALID','host must carry the table and carrier hashes'
        end
        text=text..';host:'..state.host.table..':'..state.host.carrier
    end
    if state.items~=nil and(type(state.items)~='table'or#state.items>0)then
        if type(state.items)~='table'then return nil,'INVALID','items must be a list'end
        local field,why=items_text(state.items)
        if not field then return nil,'INVALID','items: '..why end
        text=text..';'..field
    end
    if state.calls~=nil and(type(state.calls)~='table'or#state.calls>0)then
        if type(state.calls)~='table'then return nil,'INVALID','calls must be a list'end
        local field,why=calls_text(state.calls)
        if not field then return nil,'INVALID','calls: '..why end
        text=text..';'..field
    end
    if#text>M.MAX then return nil,'TOO_LONG',#text..' bytes (at most '..M.MAX..')'end
    return text
end

local function split(text,sep)
    local out,from={},1
    while true do
        local at=text:find(sep,from,true)
        if not at then out[#out+1]=text:sub(from);return out end
        out[#out+1]=text:sub(from,at-1)
        from=at+1
    end
end

-- The items field after 'items:' -> {{id, beacon, items}}, or nil, code, reason.
local function decode_items(text,known)
    local list={}
    local calls=split(text,',')
    if#calls<1 or#calls>M.MAX_ITEM_CALLS then return nil,'MALFORMED','items: '..#calls..' calls'end
    local seen={}
    for k,entry in ipairs(calls)do
        local id,beacon,nets=entry:match('^([a-z][a-z0-9_]*)@(%d+)=([%d%+]+)$')
        local b_=beacon and network_of(beacon)
        if not(id and id_ok(id)and b_)then return nil,'MALFORMED','items: call '..k end
        if seen[b_]then return nil,'MALFORMED','items: beacon '..b_..' listed twice'end
        seen[b_]=true
        if known and not known[id]then return nil,'UNKNOWN_ID','items: call '..k..' is '..id..', not registered here'end
        local parts=split(nets,'+')
        if#parts<1 or#parts>M.MAX_ITEMS then return nil,'MALFORMED','items: call '..k..' lists '..#parts..' items'end
        local items={}
        for j,p in ipairs(parts)do
            local n=network_of(p)
            if not n then return nil,'MALFORMED','items: call '..k..' item '..j end
            items[j]=n
        end
        list[k]={id=id,beacon=b_,items=items}
    end
    return list
end

-- The calls field after 'calls:' -> {{id, beacon, seq, slot, carrier}}, or nil, code, reason.
local function decode_calls(text,known)
    local list={}
    local parts=split(text,',')
    if#parts<1 or#parts>M.MAX_CALLS then return nil,'MALFORMED','calls: '..#parts..' calls'end
    local seen={}
    for k,entry in ipairs(parts)do
        local id,beacon,seq,slot,carrier=entry:match('^([a-z][a-z0-9_]*)@(%d+)#([1-9]%d*)=([0-3]):(%x%x%x%x%x%x%x%x)$')
        local b_=beacon and network_of(beacon)
        if not(id and id_ok(id)and b_ and#seq<=10 and tonumber(seq)<=M.MAX_SEQ and hash_ok(carrier))then
            return nil,'MALFORMED','calls: call '..k
        end
        if seen[b_]then return nil,'MALFORMED','calls: beacon '..b_..' listed twice'end
        seen[b_]=true
        if known and not known[id]then return nil,'UNKNOWN_ID','calls: call '..k..' is '..id..', not registered here'end
        list[k]={id=id,beacon=b_,seq=tonumber(seq),slot=tonumber(slot),carrier=carrier}
    end
    return list
end

-- A received value. known: nil (grammar only) or the set of ids registered here ({[id] = true}). Returns the state
-- ({protocol, version, registry, seq, slots = {[1..4] = id or false}, host, items = {{id, beacon, items}}, calls =
-- {{id, beacon, seq, slot, carrier}}}) or nil,
-- code, reason; code is one of MALFORMED (the grammar), PROTOCOL (another protocol version) or UNKNOWN_ID (an id not
-- registered here).
function M.decode(text,known)
    if type(text)~='string'or#text==0 then return nil,'MALFORMED','empty'end
    if#text>M.MAX then return nil,'MALFORMED',#text..' bytes (at most '..M.MAX..')'end
    if text:find('[^\32-\126]')then return nil,'MALFORMED','not printable ASCII'end
    local fields=split(text,';')
    if fields[1]~=M.PROTOCOL then
        if(fields[1]or''):match('^hd2rt/%d+$')then return nil,'PROTOCOL','protocol '..fields[1]..', not '..M.PROTOCOL end
        return nil,'MALFORMED','not an '..M.PROTOCOL..' value'
    end
    if#fields<5 or#fields>8 then return nil,'MALFORMED',#fields..' fields'end
    local version,registry,seq_text,slots_text=fields[2],fields[3],fields[4],fields[5]
    if not version_ok(version)then return nil,'MALFORMED','runtime version'end
    if not hash_ok(registry)then return nil,'MALFORMED','registry hash'end
    if not seq_text:match('^[1-9]%d*$')or#seq_text>10 or tonumber(seq_text)>M.MAX_SEQ then
        return nil,'MALFORMED','seq'
    end
    local parts=split(slots_text,',')
    if#parts~=M.SLOTS then return nil,'MALFORMED',#parts..' slots'end
    local slots={}
    for k,id in ipairs(parts)do
        if id=='-'then slots[k]=false
        elseif id_ok(id)then
            if known and not known[id]then return nil,'UNKNOWN_ID','slot '..(k-1)..' holds '..id..', not registered here'end
            slots[k]=id
        else return nil,'MALFORMED','slot '..(k-1)end
    end
    -- The optional fields, in this order: host, items, calls.
    local host,items,calls
    local k=6
    if fields[k]and fields[k]:sub(1,5)=='host:'then
        local t,c=fields[k]:match('^host:(%x%x%x%x%x%x%x%x):(%x%x%x%x%x%x%x%x)$')
        if not(t and hash_ok(t)and hash_ok(c))then return nil,'MALFORMED','host field'end
        host={table=t,carrier=c}
        k=k+1
    end
    if fields[k]and fields[k]:sub(1,6)=='items:'then
        local list,code,why=decode_items(fields[k]:sub(7),known)
        if not list then return nil,code,why end
        items=list
        k=k+1
    end
    if fields[k]and fields[k]:sub(1,6)=='calls:'then
        local list,code,why=decode_calls(fields[k]:sub(7),known)
        if not list then return nil,code,why end
        calls=list
        k=k+1
    end
    if fields[k]then return nil,'MALFORMED','field '..k end
    return {protocol=M.PROTOCOL,version=version,registry=registry,seq=tonumber(seq_text),slots=slots,host=host,
        items=items or{},calls=calls or{}}
end

-- Whether a peer's state is compatible with this machine's: the same protocol (decode already required it), Runtime
-- version and registry hash. Returns true, or false and the field that differs.
function M.compatible(mine,theirs)
    if mine.version~=theirs.version then return false,'runtime version'end
    if mine.registry~=theirs.registry then return false,'registry hash'end
    return true
end
return M
