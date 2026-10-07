-- The EXPERIMENTAL multiplayer scope of custom stratagems (0.30.0-dev; docs/custom-stratagem-api.md, "Several players").
-- Not a claim that multiplayer is safe: a test build for live research.
--
-- Every custom stratagem write path was solo-only: one stratagem record, or one player. Each of those guards protected
-- the same thing: what other machines see. A direct write is not sent to peers by itself; the game's own sync sends a
-- record (rpc_sync_stratagems: raw types, remaining cooldowns), never a beacon change or a projectile's own copy. None of
-- them guarded the write's own inputs: every write still reads and checks exactly the local record entry, the local
-- player's own beacon, the call's own entity or projectile. So for a custom stratagem call ONLY, this scope lifts the
-- solo guard, and only it:
--   * per call: a custom stratagem call passes multiplayer = true (runtime/custom_stratagems.lua, every write it makes
--     for its own call: the slot conversion, the cooldown, the beacon change, the bombardment, the impact bindings);
--   * per entity: an entity associated with a custom stratagem call the orchestrator marked (M.mark_call;
--     runtime/spawned_instances.lua), e.g. its sentry, launchers, Pelican and chin turret.
-- Every other caller (the proofs; a mod calling hd2.pelican.spawn outside a custom stratagem call, or with a table of its
-- own as `call`) keeps the solo guard. None of these modules is exported to mods: only the Runtime passes the scope. Every
-- other guard stays: in a mission, the host, the build's pins, the exact original bytes, the guarded transaction, the
-- beacon owned here (a copy with no state belongs to another machine and is never written), the local player's own
-- record entry, the projectile credited to the local player.
local M={}
local announced=false
-- The custom stratagem calls of the scope (marked by runtime/custom_stratagems.lua when it creates them; weak keys). A
-- table that merely carries a call_id (or multiplayer = true) is not one: the scope cannot be claimed by a caller.
local calls=setmetatable({},{__mode='k'})
function M.mark_call(ctx)if type(ctx)=='table'then calls[ctx]=true end end
function M.call_allowed(ctx)return type(ctx)=='table'and calls[ctx]==true end

local function log(text)
    local ok,l=pcall(require,'hd2runtime/runtime/log')
    if ok then pcall(l.emit,'[HD2Runtime] '..text)end
end

-- Whether a write's options accept the experimental multiplayer scope (a custom stratagem call's own write).
function M.allows(opts)return type(opts)=='table'and opts.multiplayer==true end
-- Whether an entity is associated with a custom stratagem call of the scope (its writes accept it).
function M.entity_allowed(entity)
    local ok,instances=pcall(require,'hd2runtime/runtime/spawned_instances')
    local e=ok and type(entity)=='number'and instances.lookup(entity)
    return e~=nil and e~=false and e.multiplayer==true
end
-- The solo guard of a write path: nil when it may run, else 'NOT_SOLO', reason. count: the stratagem records (or the
-- players); allowed: the scope (M.allows / M.entity_allowed); what: why the path was solo-only.
function M.solo_guard(count,allowed,what)
    if count==1 or allowed then return nil end
    return 'NOT_SOLO','solo only: '..tostring(count)..' stratagem records'..(what and(' ('..what..')')or'')
        ..'; only a custom stratagem call\'s own writes accept the experimental multiplayer scope'
end
-- THE CLIENT-WRITE PROOF (research/docs/runtime-peer-messaging-F5FEE03DCFDB.md, section 10). A non-host client runs
-- its OWN custom stratagem calls only for the payload families in M.CLIENT_FAMILIES (the support delivery: Gas EAT), and
-- only while the orchestrator enabled the proof for this mission (every lobby member a compatible Runtime, the synced
-- table and the carrier map agreeing with the host's). The host guard of exactly four writes accepts it, and only for a
-- write the orchestrator marked (client = true, never exported to mods):
--   * the slot conversion of this machine's OWN record entry (runtime/stratagem_slot_conversion.lua);
--   * that entry's cooldown (runtime/slot_cooldown.lua);
--   * the first-update delivery of a beacon this machine OWNS (runtime/beacons.lua; NOT_OWNED stays for a copy);
--   * the impact copy of a projectile in this machine's own pool fired from a tracked custom launcher: the call's own,
--     or another compatible Runtime's call's launcher correlated by its network id (runtime/projectile_impact.lua
--     provenance; runtime/custom_mp_items.lua). Live 2026-10-04: each machine explodes its own copy, so the payload is
--     the exact launcher's on every machine whoever fires it; NOT_LOCAL stays for every other binding.
-- None of them reads the host flag: each reads and checks only this machine's own record entry, beacon or projectile
-- copy (the guards that stay say so), and what the host guard protected (an unproven client-side write) is the subject
-- of the live proof. Every other family (Pelican CAS, Eagle payloads, the sentry, the Runtime bombardment) and every
-- other write keep NOT_HOST.
-- The families a client runs (the orchestrator decides per definition, M.client_family):
--   * support: the support delivery (the Gas EAT; live-proven r3);
--   * orbital_native: a native custom orbital (its beacon's delivery becomes the donor's own barrage, which the game
--     replicates; every machine converts its own copies of that barrage's shells). The Runtime bombardment executor
--     (a Runtime-fired barrage) is NOT in it: its shells exist on the caller's machine only;
--   * pelican: the client owns its slot, cooldown and beacon (neutralized) and REQUESTS the call; the session host
--     spawns the Pelican (runtime/custom_mp_calls.lua);
--   * expendable: the clone's own pod (its carrier weapon's beacon), the launchers' rockets as the support delivery's;
--   * sentry (2026-10-06, the user's request that every example work with several players; NOT live-tested): the
--     client's own beacon delivers the donor sentry's pod; the machine that CREATED the sentry configures its weapon
--     whole, every other compatible Runtime mirrors its round, spread and recoil on its own copy
--     (runtime/custom_weapons.lua roles, runtime/custom_mp_items.lua).
--   * silo (2026-10-06, NOT live-tested): the client's own beacon delivers the donor silo's pod (the support redirect);
--     its missile is captured read-only and published; the session host watches its own copy of that missile and
--     requests the blast where it detonates (hd2.explosions stays host-only).
-- Eagles, the Runtime bombardment and callback-only ('runtime') definitions stay host-only.
M.CLIENT_FAMILIES={support=true,orbital_native=true,pelican=true,expendable=true,sentry=true,silo=true}
-- A definition's client family key, or nil (host-only).
function M.family_name(d)
    if type(d)~='table'then return'unknown'end
    if d.kind=='orbital'and d.orbital and d.orbital.native then return'orbital_native'end
    return tostring(d.kind)
end
function M.client_family(d)
    local name=M.family_name(d)
    return M.CLIENT_FAMILIES[name]and name or nil
end
local client_proof=false
function M.enable_client_proof(on)client_proof=on==true end
function M.client_proof()return client_proof end
-- The host guard of a write path: nil when this machine is the host, or when the write belongs to the client-write
-- proof (client: the orchestrator's mark) while it is enabled. Else 'NOT_HOST', reason.
-- THE LOCKOUT (0.30 fail closed): a custom stratagem slot that will not run in this mission must never call its token.
-- The orchestrator enables it for the mission and marks exactly one write with client = 'lockout': this machine's OWN
-- record entry's cooldown end (runtime/slot_cooldown.lua lock_entry; the same write the client-write proof made live).
-- No other write accepts the mark.
local lockout=false
function M.enable_lockout(on)lockout=on==true end
function M.lockout()return lockout end
function M.host_guard(game,client,what)
    if game and game.host==true then return nil end
    if client==true and client_proof then return nil end
    if client=='lockout'and lockout then return nil end
    return 'NOT_HOST',(what or'development: host only')..(client==true
        and'; the client-write proof is not enabled in this mission'or'')
end
-- Logged once per session, the first time custom stratagems meet more than one player.
function M.announce(players,where)
    if announced or not(type(players)=='number'and players>1)then return false end
    announced=true
    log(('CUSTOM STRATAGEMS MULTIPLAYER EXPERIMENTAL: %d players (%s). Each player\'s own Runtime runs that player\'s '
        ..'calls (a beacon belongs to its thrower\'s machine); this build runs them on the host only (every payload '
        ..'write stays host-only); other machines see the game\'s own replication only (docs/custom-stratagem-api.md, '
        ..'"Several players")'):format(players,tostring(where)))
    return true
end
function M.announced()return announced end
function M.reset_for_tests()announced=false;calls=setmetatable({},{__mode='k'});client_proof=false;lockout=false end
return M
