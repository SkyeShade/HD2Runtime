-- The beam conversion sync protocol hd2bc/2 (DEVELOPMENT; docs/beam-conversion.md "Multiplayer";
-- research/docs/beam-conversion-mp-sync-F5FEE03DCFDB.md, research/docs/beam-conversion-add-layout-F5FEE03DCFDB.md):
-- the one value each machine publishes under its third lobby member key, `hd2bc` (runtime/peer_channel.lua), naming
-- the beam conversions applied on it (runtime/beam_conversion_sync.lua). Pure: no game access.
--
--   hd2bc/2;<runtime version>;<build>;<catalogue hash>;<seq>;<digest>;<entries>
--
-- <runtime version>: domains/metadata.lua's version (1-32 of [A-Za-z0-9.+-]). <build>: the first 12 uppercase hex
-- digits of the game executable's SHA-256 (schemas/current.lua exe_sha). <catalogue hash>: 8 uppercase hex digits, the
-- FNV-1a 32 of the beam conversion catalogue (runtime/beam_conversion_sync.lua catalogue_hash). <seq>: 1..2^31-1
-- without leading zeros, raised on every change of the set. <entries>: `-` (nothing converted), or 1..MAX_ENTRIES
-- entries separated by `,`, strictly ascending (sorted by resource, no duplicates), each
--   <resource>.<layout>.<path>.<record>.<rows>
-- <resource>: the converted root resource, 16 uppercase hex digits without 0x. <layout>: `a` (the add layout:
-- ProjectileWeapon kept, BeamWeapon added) or `w` (the swap layout: ProjectileWeapon swapped out, solo only). <path>:
-- `o` (the Runtime-owned table), `s` (the shared record 23 fallback) or `x` (orphaned: no BeamWeapon row, or a list
-- the loader put back). <record>: 8 uppercase hex, the FNV-1a 32 of the weapon's BeamWeapon record bytes with its
-- BeamType (+0, which names a locally borrowed slot) zeroed: rate, beams, pulse and every other member;
-- `00000000` for x. <rows>: 8 uppercase hex, the FNV-1a 32 of the weapon's own beam row followed by its own damage
-- row, each with the row ids a local borrow puts in them zeroed (beam +0 and +12, damage +0): range, damage, AP ...;
-- `00000000` when it has no own rows (and for x). So two machines that converted a weapon the same way post the same
-- entry whichever spare slots they borrowed (the ids never leave a machine: research/docs/beam-rows-borrowed-
-- F5FEE03DCFDB.md). <digest>: 8 uppercase hex, the FNV-1a 32 of the <entries> text: two values with the same version,
-- build, catalogue and digest describe the same conversions. At most MAX bytes. It is STATE, not a message: the last
-- value a member published is what every member reads (a joiner included). Nothing in it is an address or a value to
-- write: a receiver only compares it and names catalogued weapons from it. decode accepts nothing else: a value that
-- does not match the grammar exactly (the digest included) is refused whole. hd2bc/1 values (an older Runtime) are not
-- this protocol: malformed.
local fnv1a=require('hd2runtime/runtime/peer_protocol').fnv1a
local M={}
M.PROTOCOL='hd2bc/2'
M.MAX=512
M.MAX_ENTRIES=11
M.MAX_SEQ=2147483647
M.NONE='-'
M.ZERO='00000000'
M.PATHS={o='owned table',s='shared record',x='orphaned'}
M.LAYOUTS={a='add',w='swap'}
M.LAYOUT_CODE={add='a',swap='w'}

local function version_ok(v)return type(v)=='string'and#v>=1 and#v<=32 and v:match('^[%w%.%+%-]+$')~=nil end
local function hex_ok(h,n)return type(h)=='string'and#h==n and not h:find('[^0-9A-F]')end
local function seq_ok(n)return type(n)=='number'and n%1==0 and n>=1 and n<=M.MAX_SEQ end
M.hex_ok=hex_ok

-- The digests (pure). record: the 120 record bytes. beam, damage: the own row bytes, or nil (no own rows).
local function zero(bytes,from,to)return bytes:sub(1,from)..string.rep('\0',to-from)..bytes:sub(to+1)end
function M.record_digest(record)
    assert(type(record)=='string'and#record>=4,'record bytes')
    return fnv1a(zero(record,0,4))
end
function M.rows_digest(beam,damage)
    if beam==nil and damage==nil then return M.ZERO end
    assert(type(beam)=='string'and#beam>=16 and type(damage)=='string'and#damage>=4,'row bytes')
    local digest=fnv1a(zero(zero(beam,0,4),12,16)..zero(damage,0,4))
    if digest==M.ZERO then digest='00000001'end   -- never the "no own rows" value
    return digest
end

-- One entry {resource (16 hex), layout, path, record (8 hex), rows (8 hex)} as text, or nil, reason.
local function entry_text(e)
    if type(e)~='table'then return nil,'invalid entry'end
    if not hex_ok(e.resource,16)then return nil,'invalid resource'end
    if not M.LAYOUTS[e.layout]then return nil,'invalid layout'end
    if not M.PATHS[e.path]then return nil,'invalid path'end
    if not hex_ok(e.record,8)then return nil,'invalid record digest'end
    if not hex_ok(e.rows,8)then return nil,'invalid rows digest'end
    if e.path=='x'and(e.record~=M.ZERO or e.rows~=M.ZERO)then return nil,'an orphaned root has no record or rows'end
    return ('%s.%s.%s.%s.%s'):format(e.resource,e.layout,e.path,e.record,e.rows)
end
M.entry_text=entry_text
-- Whether two entries describe the same conversion of the same root.
function M.same(a,c)
    return a~=nil and c~=nil and a.resource==c.resource and a.layout==c.layout and a.path==c.path
        and a.record==c.record and a.rows==c.rows
end

-- The canonical <entries> text of a set (any order; sorted here) and its digest, or nil, reason.
function M.canonical(entries)
    if type(entries)~='table'then return nil,'no entries'end
    if#entries>M.MAX_ENTRIES then return nil,'at most '..M.MAX_ENTRIES..' converted roots'end
    if#entries==0 then return M.NONE,fnv1a(M.NONE)end
    local list,seen={},{}
    for _,e in ipairs(entries)do
        local text,why=entry_text(e)
        if not text then return nil,why end
        if seen[e.resource]then return nil,'duplicate resource'end
        seen[e.resource]=true
        list[#list+1]=text
    end
    table.sort(list)
    local text=table.concat(list,',')
    return text,fnv1a(text)
end

-- state: {version, build, catalog, seq, entries = {entry, ...}}. The value, or nil, reason.
function M.encode(state)
    if type(state)~='table'then return nil,'no state'end
    if not version_ok(state.version)then return nil,'invalid runtime version'end
    if not hex_ok(state.build,12)then return nil,'invalid build'end
    if not hex_ok(state.catalog,8)then return nil,'invalid catalogue hash'end
    if not seq_ok(state.seq)then return nil,'invalid sequence number'end
    local text,digest=M.canonical(state.entries)
    if not text then return nil,digest end
    local value=('%s;%s;%s;%s;%d;%s;%s'):format(M.PROTOCOL,state.version,state.build,state.catalog,state.seq,digest,
        text)
    if#value>M.MAX then return nil,'longer than '..M.MAX..' bytes'end
    return value
end

local function split(text,sep)
    local out,start={},1
    while true do
        local at=text:find(sep,start,true)
        if not at then out[#out+1]=text:sub(start);return out end
        out[#out+1]=text:sub(start,at-1)
        start=at+1
    end
end

-- A received value: {version, build, catalog, seq, digest, entries = {entry, ...} (ascending)}, or nil, reason.
function M.decode(text)
    if type(text)~='string'then return nil,'not text'end
    if#text<1 or#text>M.MAX then return nil,'length outside 1-'..M.MAX..' bytes'end
    if text:find('[^\32-\126]')then return nil,'not printable ASCII'end
    local f=split(text,';')
    if f[1]~=M.PROTOCOL then return nil,'not '..M.PROTOCOL end
    if#f~=7 then return nil,'expected 7 fields, got '..#f end
    local version,build,catalog,seq_text,digest,list=f[2],f[3],f[4],f[5],f[6],f[7]
    if not version_ok(version)then return nil,'invalid runtime version'end
    if not hex_ok(build,12)then return nil,'invalid build'end
    if not hex_ok(catalog,8)then return nil,'invalid catalogue hash'end
    if not seq_text:match('^[1-9]%d?%d?%d?%d?%d?%d?%d?%d?%d?$')then return nil,'invalid sequence number'end
    local seq=tonumber(seq_text)
    if not seq_ok(seq)then return nil,'invalid sequence number'end
    if not hex_ok(digest,8)then return nil,'invalid digest'end
    if fnv1a(list)~=digest then return nil,'the digest does not match the entries'end
    local entries={}
    if list~=M.NONE then
        local parts=split(list,',')
        if#parts>M.MAX_ENTRIES then return nil,'more than '..M.MAX_ENTRIES..' entries'end
        for i,p in ipairs(parts)do
            local resource,layout,path,record,rows=p:match('^(%x+)%.(%a)%.(%a)%.(%x+)%.(%x+)$')
            local e={resource=resource,layout=layout,path=path,record=record,rows=rows}
            local canon,why=entry_text(resource and e or nil)
            if not canon or canon~=p then return nil,'invalid entry ('..tostring(why or'not canonical')..')'end
            if i>1 and not(parts[i-1]<p and entries[i-1].resource<resource)then
                return nil,'entries not strictly ascending'
            end
            entries[i]=e
        end
    end
    return {version=version,build=build,catalog=catalog,seq=seq,digest=digest,entries=entries}
end
return M
