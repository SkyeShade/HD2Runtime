-- The common shape of custom stratagem calls and their entities' PROVENANCE (0.30; internal: not exported to mods).
-- Read-only bookkeeping: it describes, it writes nothing of the game.
--
-- Three live-proven multiplayer families share one model (research/docs/runtime-peer-messaging-F5FEE03DCFDB.md, sections
-- 14 to 19):
--   support item provenance            the EAT-17G / Gas EAT launchers          (role launcher)
--   replicated native executor         the Orbital Gas Barrage's 120mm barrage  (role barrage)
--   host-created replicated entity     the Pelican CAS and its chin turret      (roles vehicle, turret)
--
--   CustomCall        what a call IS, on every machine alike: {custom_id, call_id, seq, caller_peer, slot,
--                     carrier_stable_id, beacon_network, position, authority}. authority: 'caller' (the thrower's machine
--                     runs it: support deliveries, native orbitals), 'host' (the session host runs it for its caller: the
--                     Pelican CAS) or 'each_peer_local' (every machine realizes its own copies: projectiles, shells).
--   ProvenanceEntity  what a networked entity IS: {network_id, custom_id, call, role, parent_network_id, entity (this
--                     machine's copy, once resolved), realized (this machine applied its local configuration)}.
--   Local realization network provenance -> this machine's entity copy -> its registered custom definition -> its local
--                     instance configuration (runtime/custom_stratagems.lua remote handlers; family-specific adapters).
-- Only semantic identity crosses the network (custom ids, network ids, roles): never an RPM, a projectile record, an
-- explosion, an offset or a memory value; every Runtime derives those from its own registered definition. A future
-- declarative custom projectile referenced by a custom weapon realizes the same way (role projectile_source: its
-- projectiles converted on each machine's own copies), with no networking code in the mod.
local M={}
M.ROLES={primary=true,launcher=true,weapon=true,turret=true,sentry=true,vehicle=true,barrage=true,
    projectile_source=true,payload=true}
M.AUTHORITY={caller=true,host=true,each_peer_local=true}

-- A CustomCall from its parts (a copy; unknown fields left nil). Returns the call, or nil and why.
function M.call(spec)
    if type(spec)~='table'or type(spec.custom_id)~='string'then return nil,'a custom call needs its custom id'end
    if spec.authority~=nil and not M.AUTHORITY[spec.authority]then return nil,'unknown authority '..tostring(spec.authority)end
    local p=spec.position
    return {custom_id=spec.custom_id,call_id=spec.call_id,seq=spec.seq,caller_peer=spec.caller_peer,slot=spec.slot,
        carrier_stable_id=spec.carrier_stable_id,beacon_network=spec.beacon_network,
        position=p and{x=p.x,y=p.y,z=p.z}or nil,authority=spec.authority}
end

-- The mission's provenance records, by network id (a network id names one entity at a time; a newer record of it
-- replaces an older one).
local records={}
local count=0
function M.reset()records,count={},0 end
M.reset_for_tests=M.reset

-- Records one entity's provenance: spec = {network_id, custom_id, call (a CustomCall or its call id / beacon network
-- id), role, parent_network_id, entity, realized}. Returns the record (a copy), or nil and why.
function M.entity(spec)
    if type(spec)~='table'or type(spec.network_id)~='number'or spec.network_id<1 then
        return nil,'a provenance record needs its network id'
    end
    if type(spec.custom_id)~='string'then return nil,'a provenance record needs its custom id'end
    if not M.ROLES[spec.role]then return nil,'unknown role '..tostring(spec.role)end
    local r=records[spec.network_id]
    if not r then count=count+1 end
    r={network_id=spec.network_id,custom_id=spec.custom_id,call=spec.call,role=spec.role,
        parent_network_id=spec.parent_network_id,entity=spec.entity,realized=spec.realized==true}
    records[spec.network_id]=r
    return M.get(spec.network_id)
end
-- This machine's copy realized (its local configuration applied): marks the record.
function M.realized(network_id,entity)
    local r=records[network_id]
    if not r then return false end
    r.realized,r.entity=true,entity or r.entity
    return true
end
local function copy(r)
    local out={}
    for k,v in pairs(r)do out[k]=v end
    return out
end
function M.get(network_id)local r=records[network_id];return r and copy(r)or nil end
-- Every record (copies, by network id), optionally of one custom id or role.
function M.list(filter)
    local out={}
    for _,r in pairs(records)do
        if not filter or((not filter.custom_id or r.custom_id==filter.custom_id)and(not filter.role or r.role==filter.role))
        then out[#out+1]=copy(r)end
    end
    table.sort(out,function(a,c)return a.network_id<c.network_id end)
    return out
end
-- A summary for the logs: '3 entities (launcher 2, barrage 1), 3 realized here'.
function M.summary()
    local roles,realized,n={},0,0
    for _,r in pairs(records)do
        n=n+1
        roles[r.role]=(roles[r.role]or 0)+1
        if r.realized then realized=realized+1 end
    end
    local parts={}
    for role,k in pairs(roles)do parts[#parts+1]=role..' '..k end
    table.sort(parts)
    return('%d entit%s (%s), %d realized here'):format(n,n==1 and'y'or'ies',#parts>0 and table.concat(parts,', ')or'none',
        realized)
end
return M
