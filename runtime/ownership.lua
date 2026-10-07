-- Who an autonomous entity's kills credit (development; docs/custom-stratagem-api.md, "Ownership"). Not exported by
-- api/hd2.lua directly: api/ownership.lua is its public face.
--
-- The game credits a hit to Creditor(owner): the peer owning the shooter's network object, unless the shooter carries
-- the no-credit tag or has none (research/pelican-F5FEE03DCFDB.json "attribution"; research/docs/pelican-cas section
-- 24). The live-proven per-instance path (PelicanGatlingProof 0.5.0) clears that ONE entity's own tag through one
-- guarded 8-byte write of its own Tag record (runtime/pelican_weapon.lua configure_credit: it wields itself, has the
-- player faction bit and a network id). This module is the semantic seam: callers name an entity and a reason, never a
-- tag, a mask or a creditor structure.
local M={}

-- Credits a self-wielding autonomous entity's kills to the host who owns its network object (the local player in a
-- solo game). Returns {applied, already, reason}.
function M.credit_to_host(world,entity,label)
    local r=require('hd2runtime/runtime/pelican_weapon').configure_credit(world,entity,label)
    return {applied=r.applied==true,already=r.already==true,reason=r.reason}
end
-- The last hit an entity took (its health record's owner and creditor), read-only: {owner, creditor_lo, creditor_hi,
-- health, life} or nil.
function M.last_hit(world,entity)return require('hd2runtime/runtime/pelican_weapon').last_hit(world,entity)end
return M
