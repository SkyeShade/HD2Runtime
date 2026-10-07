-- The synced asset protocol hd2as/1 (DEVELOPMENT; docs/asset-loading.md, "Synced asset loading"): the one value each
-- machine publishes under its second lobby member key, `hd2as` (runtime/peer_channel.lua), naming the catalog packages
-- its mods asked the Runtime to load (runtime/asset_sync.lua). Pure: no game access.
--
--   hd2as/1;<runtime version>;<catalog hash>;<seq>;<pkg>,<pkg>,...
--
-- <runtime version>: domains/metadata.lua's version (1-32 of [A-Za-z0-9.+-]). <catalog hash>: 8 uppercase hex digits,
-- the FNV-1a 32 (runtime/peer_protocol.lua fnv1a) of every package id the sender's core/assets accepts, sorted, one per
-- line: two machines with the same hash know exactly the same package identities. <seq>: 1..2^31-1 without leading
-- zeros, raised on every change of the set. <pkg>: 16 uppercase hex digits, a package id without its 0x; 1..MAX_PACKAGES
-- of them, strictly ascending (sorted, no duplicates). At most MAX bytes.
-- It is STATE, not a message: the last value a member published is what every member reads (a joiner included). Nothing
-- in it is an address or a value to write: a package id names a package only through the receiver's own catalog, and a
-- receiver loads nothing its catalog does not know. decode accepts nothing else: a value that does not match the grammar
-- exactly is refused whole, never partly used. The sender is never in the value: the receiver takes it from the lobby
-- member it read.
local M={}
M.PROTOCOL='hd2as/1'
M.MAX=512
M.MAX_PACKAGES=24
M.MAX_SEQ=2147483647

local function version_ok(v)return type(v)=='string'and#v>=1 and#v<=32 and v:match('^[%w%.%+%-]+$')~=nil end
local function hash_ok(h)return type(h)=='string'and h:match('^%x%x%x%x%x%x%x%x$')~=nil and h==h:upper()end
local PKG='^'..string.rep('%x',16)..'$'
local function package_ok(p)return type(p)=='string'and p:match(PKG)~=nil and p==p:upper()end
M.package_ok=package_ok
local function seq_ok(n)return type(n)=='number'and n%1==0 and n>=1 and n<=M.MAX_SEQ end

-- state: {version, catalog, seq, packages = {16 hex digits, ...}} (any order; sorted here). The value, or nil, reason.
function M.encode(state)
    if type(state)~='table'then return nil,'no state'end
    if not version_ok(state.version)then return nil,'invalid runtime version'end
    if not hash_ok(state.catalog)then return nil,'invalid catalog hash'end
    if not seq_ok(state.seq)then return nil,'invalid sequence number'end
    local list=state.packages
    if type(list)~='table'or#list<1 then return nil,'no package'end
    if#list>M.MAX_PACKAGES then return nil,'at most '..M.MAX_PACKAGES..' packages'end
    local sorted,seen={},{}
    for _,p in ipairs(list)do
        if not package_ok(p)then return nil,'invalid package id'end
        if seen[p]then return nil,'duplicate package id'end
        seen[p]=true;sorted[#sorted+1]=p
    end
    table.sort(sorted)
    local value=('%s;%s;%s;%d;%s'):format(M.PROTOCOL,state.version,state.catalog,state.seq,table.concat(sorted,','))
    if#value>M.MAX then return nil,'longer than '..M.MAX..' bytes'end
    return value
end

-- Splits on a one-character separator, keeping empty fields.
local function split(text,sep)
    local out,start=nil,1
    out={}
    while true do
        local at=text:find(sep,start,true)
        if not at then out[#out+1]=text:sub(start);return out end
        out[#out+1]=text:sub(start,at-1)
        start=at+1
    end
end

-- A received value: {version, catalog, seq, packages = {ascending 16 hex digits}}, or nil, reason.
function M.decode(text)
    if type(text)~='string'then return nil,'not text'end
    if#text<1 or#text>M.MAX then return nil,'length outside 1-'..M.MAX..' bytes'end
    if text:find('[^\32-\126]')then return nil,'not printable ASCII'end
    local fields=split(text,';')
    if fields[1]~=M.PROTOCOL then return nil,'not '..M.PROTOCOL end
    if#fields~=5 then return nil,'expected 5 fields, got '..#fields end
    local version,catalog,seq_text,list=fields[2],fields[3],fields[4],fields[5]
    if not version_ok(version)then return nil,'invalid runtime version'end
    if not hash_ok(catalog)then return nil,'invalid catalog hash'end
    if not seq_text:match('^[1-9]%d?%d?%d?%d?%d?%d?%d?%d?%d?$')then return nil,'invalid sequence number'end
    local seq=tonumber(seq_text)
    if not seq_ok(seq)then return nil,'invalid sequence number'end
    local packages=split(list,',')
    if#packages>M.MAX_PACKAGES then return nil,'more than '..M.MAX_PACKAGES..' packages'end
    for i,p in ipairs(packages)do
        if not package_ok(p)then return nil,'invalid package id'end
        if i>1 and not(packages[i-1]<p)then return nil,'package ids not strictly ascending'end
    end
    return {version=version,catalog=catalog,seq=seq,packages=packages}
end
return M
