-- The beam conversion sync protocol hd2bc/1 (DEVELOPMENT; docs/beam-conversion.md "Multiplayer";
-- research/docs/beam-conversion-mp-sync-F5FEE03DCFDB.md): the one value each machine publishes under its third lobby
-- member key, `hd2bc` (runtime/peer_channel.lua), naming the beam conversions applied on it (runtime/beam_conversion_
-- sync.lua). Pure: no game access.
--
--   hd2bc/1;<runtime version>;<build>;<catalogue hash>;<seq>;<digest>;<entries>
--
-- <runtime version>: domains/metadata.lua's version (1-32 of [A-Za-z0-9.+-]). <build>: the first 12 uppercase hex
-- digits of the game executable's SHA-256 (schemas/current.lua exe_sha). <catalogue hash>: 8 uppercase hex digits, the
-- FNV-1a 32 of the beam conversion catalogue (runtime/beam_conversion_sync.lua catalogue_hash). <seq>: 1..2^31-1
-- without leading zeros, raised on every change of the set. <entries>: `-` (nothing converted), or 1..MAX_ENTRIES
-- entries separated by `,`, strictly ascending (sorted by resource, no duplicates), each
--   <resource>.<path>.<record>.<pair>.<rows>
-- <resource>: the converted root resource, 16 uppercase hex digits without 0x. <path>: `o` (the Runtime-owned table),
-- `s` (the shared record 23 fallback) or `x` (lists converted, no BeamWeapon row: orphaned). <record>: 8 uppercase hex,
-- the FNV-1a 32 of the weapon's BeamWeapon record bytes (rate, beams, pulse, the BeamType it names; `00000000` for x).
-- <pair>: 0 (no borrowed rows) or 1..MAX_PAIR, the borrowed BeamType / DamageInfo pair in research order. <rows>: 8
-- uppercase hex, the FNV-1a 32 of the pair's beam row bytes followed by its damage row bytes (range, damage, AP ...);
-- `00000000` exactly when <pair> is 0. <digest>: 8 uppercase hex, the FNV-1a 32 of the <entries> text: two values
-- with the same version, build, catalogue and digest describe the same conversions, byte for byte. At most MAX bytes.
-- It is STATE, not a message: the last value a member published is what every member reads (a joiner included).
-- Nothing in it is an address or a value to write: a receiver only compares it and names catalogued weapons from it.
-- decode accepts nothing else: a value that does not match the grammar exactly (the digest included) is refused whole.
local fnv1a=require('hd2runtime/runtime/peer_protocol').fnv1a
local M={}
M.PROTOCOL='hd2bc/1'
M.MAX=512
M.MAX_ENTRIES=11
M.MAX_PAIR=6
M.MAX_SEQ=2147483647
M.NONE='-'
M.PATHS={o='owned table',s='shared record',x='orphaned'}

local function version_ok(v)return type(v)=='string'and#v>=1 and#v<=32 and v:match('^[%w%.%+%-]+$')~=nil end
local function hex_ok(h,n)return type(h)=='string'and#h==n and not h:find('[^0-9A-F]')end
local function seq_ok(n)return type(n)=='number'and n%1==0 and n>=1 and n<=M.MAX_SEQ end
M.hex_ok=hex_ok

-- One entry {resource (16 hex), path, record (8 hex), pair (0..MAX_PAIR), rows (8 hex)} as text, or nil, reason.
local function entry_text(e)
    if type(e)~='table'then return nil,'invalid entry'end
    if not hex_ok(e.resource,16)then return nil,'invalid resource'end
    if not M.PATHS[e.path]then return nil,'invalid path'end
    if not hex_ok(e.record,8)then return nil,'invalid record digest'end
    if not(type(e.pair)=='number'and e.pair%1==0 and e.pair>=0 and e.pair<=M.MAX_PAIR)then
        return nil,'invalid pair'
    end
    if not hex_ok(e.rows,8)then return nil,'invalid rows digest'end
    if(e.pair==0)~=(e.rows=='00000000')then return nil,'rows digest without a pair, or a pair without one'end
    if e.path=='x'and(e.record~='00000000'or e.pair~=0)then return nil,'an orphaned root has no record or pair'end
    return ('%s.%s.%s.%d.%s'):format(e.resource,e.path,e.record,e.pair,e.rows)
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
            local resource,path,record,pair,rows=p:match('^(%x+)%.(%a)%.(%x+)%.(%d)%.(%x+)$')
            local e={resource=resource,path=path,record=record,pair=tonumber(pair),rows=rows}
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
