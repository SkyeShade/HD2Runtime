-- Native EVIDENCE of other machines' custom calls (EXPERIMENTAL; docs/research/runtime-peer-messaging-F5FEE03DCFDB.md
-- section 16). Read-only: it remembers what this machine itself read, it writes nothing.
--
-- Every compatible Runtime OBSERVES another player's custom call natively, on its own machine:
--   * the carrier beacon copy: its creation type is a carrier of the mission's FROZEN carrier map (custom id -> carrier,
--     one carrier per custom id, every native lobby pick excluded), so it names exactly one custom id;
--   * the thrown ball (runtime/call_ins.lua): its thrower's session peer, its record entry, its loadout slot and, from
--     its landing, its beacon's network id.
-- Both are short-lived on this machine, while a semantic message about that call (a host-call request, a published item
-- list) comes later over the slower lobby channel. Live r4: a client's Pelican request reached the host when the
-- evidence the host checked was no longer there, so no Pelican came. So every observation is CACHED here by the
-- beacon's network id for M.KEEP s, and a later decision is checked against the cache, never against what the game still
-- holds then. A message is never evidence: only this machine's own reads are.
--
-- An entry: {network, id, type (the carrier type), carrier (its stable id), entity, position, peer, entry, slot, first,
-- last, sources = {beacon = true, ball = true}}. A network id the game reuses (another entity, another carrier) after
-- its call is gone starts a new entry; so does any entry older than M.KEEP.
--
-- The caller of an observed call (M.caller): the ball's thrower when a ball named that beacon ('ball'); else, by the
-- frozen carrier map, the ONLY other lobby member whose synced picks (frozen at the mission start) select its custom id
-- ('derived': a carrier is no native pick of anyone, so its beacon can only come from a custom slot of that id); else
-- unknown.
local M={}
M.KEEP=45            -- seconds an observation stays evidence (a request or an item list may arrive this late)
M.SLOTS=4
local by_network={}
function M.reset()by_network={}end
M.reset_for_tests=M.reset

local FIELDS={'id','type','carrier','entity','position','peer','entry','slot'}
local function copy(e)
    local out={network=e.network,first=e.first,last=e.last,sources={}}
    for _,k in ipairs(FIELDS)do out[k]=e[k]end
    if e.position then out.position={x=e.position.x,y=e.position.y,z=e.position.z}end
    for k in pairs(e.sources)do out.sources[k]=true end
    return out
end
local function fresh(e,now)return e~=nil and now-e.last<=M.KEEP end

-- One observation of the call whose beacon has network id `network`. spec: any of FIELDS, and source ('beacon' |
-- 'ball'). Returns the entry (a copy), or nil when the network id is no beacon's.
function M.observe(network,spec,now)
    if type(network)~='number'or network<1 or network>=0x7FFF then return nil end
    local e=by_network[network]
    if e and(not fresh(e,now)or(spec.entity and e.entity and spec.entity~=e.entity)
            or(spec.type and e.type and spec.type~=e.type))then
        e=nil
    end
    if not e then e={network=network,first=now,last=now,sources={}};by_network[network]=e end
    e.last=now
    for _,k in ipairs(FIELDS)do if spec[k]~=nil then e[k]=spec[k]end end
    if spec.source then e.sources[spec.source]=true end
    return copy(e)
end
-- The fresh evidence of a beacon's call (a copy), or nil.
function M.get(network,now)
    local e=type(network)=='number'and by_network[network]
    if not fresh(e,now)then return nil end
    return copy(e)
end
-- Forgets evidence older than M.KEEP s.
function M.prune(now)
    for network,e in pairs(by_network)do if not fresh(e,now)then by_network[network]=nil end end
end
-- Every fresh entry (copies, by network id).
function M.list(now)
    local out={}
    for _,e in pairs(by_network)do if fresh(e,now)then out[#out+1]=copy(e)end end
    table.sort(out,function(a,c)return a.network<c.network end)
    return out
end
-- Fresh entries with a custom id but no known thrower (a lobby read is worth doing fast meanwhile).
function M.unresolved(now)
    local n=0
    for _,e in pairs(by_network)do if fresh(e,now)and e.id and not e.peer then n=n+1 end end
    return n
end

-- The caller of evidence `e` (M.get): peer, how ('ball' | 'derived'), slot (or nil); or nil and why. t: the frozen synced
-- table ({[peer] = {[0..3] = id or false}}); local_peer: this machine's peer (never another machine's caller).
function M.caller(e,t,local_peer)
    if not e then return nil,'no observed beacon or thrown ball with that network id'end
    if e.peer then return e.peer,'ball',e.slot end
    if not e.id then return nil,'its beacon is no carrier of the frozen carrier map'end
    local found,slot
    local peers={}
    for peer in pairs(t or{})do peers[#peers+1]=peer end
    table.sort(peers)
    for _,peer in ipairs(peers)do
        if peer~=local_peer then
            local picks,mine=t[peer],nil
            for s=0,M.SLOTS-1 do if picks[s]==e.id then mine=mine or{};mine[#mine+1]=s end end
            if mine then
                if found then return nil,'no thrown ball named it and several other players select '..e.id end
                found,slot=peer,#mine==1 and mine[1]or nil
            end
        end
    end
    if not found then return nil,'no thrown ball named it and no other player selects '..e.id end
    return found,'derived',slot
end
return M
