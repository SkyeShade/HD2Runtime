-- hd2.custom_stratagem: selectable custom stratagems (DEVELOPMENT API; the host's calls; several players EXPERIMENTAL:
-- docs/custom-stratagem-api.md, "Several players").
--
--   hd2.custom_stratagem.register({
--       id = 'pelican_close_air_support',            -- a-z, 0-9, _; unique across mods
--       name = 'PELICAN CLOSE AIR SUPPORT', name_cased = 'Pelican Close Air Support',
--       description = 'Calls in a Pelican that holds over the beacon for 60 seconds.',
--       icon = 'pelican_close_air_support',           -- the mod's images/<id>.png (a 256 x 256 mask)
--       code = {'left', 'down', 'left', 'up', 'left', 'up'},
--       cooldown = 60,                                -- seconds from the call-in's arrival (default: the carrier's)
--       carrier = {beacon = 'offensive', prefer_families = {'orbital'}},   -- or a carrier group: {group = 'support_pod',
--                                                     -- slots = 2} (hd2.custom_stratagem.groups())
--       assets = {'Orbital Gas Strike'},              -- stratagems whose call-in packages it needs in the mission
--       delivery = 'runtime' | {stratagem = 'EAT-17 Expendable Anti-Tank'},
--       on_called = fn(ctx), on_beacon_created = fn(ctx), on_beacon_landed = fn(ctx), on_activate = fn(ctx),
--       on_delivered = fn(ctx)                        -- support deliveries: ctx.weapons, the exact delivered weapons
--   })
--
-- The player selects it in the Runtime's custom panel on the loadout screen; the save keeps a vanilla token. In a
-- mission it borrows an owned vanilla CARRIER (allocated by its policy; never in the loadout; never shared with another
-- custom stratagem), which presents as the custom stratagem only during the mission and answers to its code. Its beacon
-- is the carrier's (the colour the policy asked for); in the beacon's first update its own delivery is replaced: by
-- nothing ('runtime': the mod delivers in on_activate) or by a vanilla support delivery. Everything is restored exactly
-- aboard the ship. Every write is guarded, per instance and host-only (solo, or a custom stratagem call of the host
-- with several players: EXPERIMENTAL); a refused step leaves the slot vanilla.
local events=require('hd2runtime/runtime/events')
local custom=require('hd2runtime/runtime/custom_stratagems')
local M={}

local Definition={};Definition.__index=Definition
-- {id, owner, carrier (allocated aboard the ship), state, calls, ship (the pre-mission line)}.
function Definition:status()
    for _,s in ipairs(custom.status())do if s.id==self.id then return s end end
end

-- Registers a custom stratagem of the calling mod. Errors (at load time) on an invalid spec. Returns its definition.
function M.register(spec)
    local owner=events.owner(nil,2)
    assert(owner~='unknown','hd2.custom_stratagem.register cannot tell which mod is calling')
    local d=custom.register(spec,owner)
    return setmetatable({id=d.id,owner=owner},Definition)
end
-- Every registered custom stratagem's state.
function M.status()return custom.status()end
-- What a custom stratagem uses (read-only plain data): its carrier group (and whether it requested it), its carrier
-- stratagem (name, type, stable id, beam; condensed for an expendable whose weapon's own stratagem carries the beacon),
-- its carrier weapon, its pod (the rack, its capacity, its items and their planned slots), whether it is available and
-- why not, and its state. nil for an unknown id. docs/custom-stratagem-api.md "describe".
function M.describe(id)return custom.describe(id)end
-- The carrier groups: {{name, beacon, families, pod, weapon, eagle, doc, payloads}} (docs/custom-stratagem-api.md
-- "Carrier groups").
function M.groups()return custom.groups()end
-- The custom stratagem call an entity belongs to: {id, call_id, n, role, player, parent} or nil.
function M.instance_of(entity)return custom.instance_of(entity)end
-- More log lines (every carrier candidate and its verdict; each custom Eagle call's per-rocket trace and its read-only
-- probes); off by default.
function M.verbose(on)custom.verbose(on)end
-- The custom panel's keyboard actions, for a mod that binds keys (the panel also takes mouse clicks):
-- focus_next() moves the focus, select_focused() selects the focused entry into the edited slot, undo() returns the
-- last selected slot to what it held. Each returns a short status text.
local function panel_call(name)
    local p=custom.panel()
    if not p then return'no custom stratagem is registered'end
    return p[name]()
end
function M.focus_next()return panel_call('focus_next')end
-- Development (2026-10-07; the CarrierModeEverywhere test mod): every custom stratagem that does not name its selection
-- takes the carrier-in-slot mode (true) or the token again (false). Applied aboard the ship; part of the registry hash
-- (every player of a lobby needs the same). Returns true when applied now, false when it waits for the ship.
function M.carrier_mode_all(on)
    assert(type(on)=='boolean','carrier_mode_all takes true or false')
    return custom.set_carrier_mode_all(on,'hd2.custom_stratagem.carrier_mode_all')
end
function M.select_focused()return panel_call('press')end
function M.undo()return panel_call('cancel')end
return M
