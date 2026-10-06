-- hd2.ownership: who an autonomous entity's kills credit (DEVELOPMENT API, solo host only;
-- docs/custom-stratagem-api.md, "Ownership").
--
-- The game credits a hit to Creditor(owner): the peer that owns the shooter's network object, unless the shooter is
-- marked as crediting nobody (its no-credit tag) or has no network object. A self-wielding autonomous weapon the
-- Runtime summoned (a Runtime Pelican's chin turret) carries that tag, so its kills credit nobody. credit_to_player
-- clears that ONE entity's own tag (one guarded 8-byte write of its own Tag record, every other bit kept): the game's
-- own Creditor then names the owner of its network object, the host. Nothing shared, no network object and no
-- creditor structure is written, and the public API names none of them.
--
-- Refused unless: the Runtime's own update (the game thread); a mission, as the solo host; `player` is the local
-- player (the only player the game can credit for a host-owned entity); the entity is ASSOCIATED with a custom stratagem
-- call of that player (hd2.custom_stratagem); it wields itself, has the player's faction bit, a network id and its Tag
-- record in private memory.
local world_module=require('hd2runtime/runtime/event_world')
local instances=require('hd2runtime/runtime/spawned_instances')
local scheduler=require('hd2runtime/runtime/scheduler')
local M={}

-- Credits an associated autonomous entity's kills to the local player. Returns {applied, already, reason}.
function M.credit_to_player(entity,player)
    local function no(reason)return {applied=false,reason=reason}end
    if not scheduler.in_update()then return no('NOT_GAME_THREAD: call it from a Runtime callback')end
    if not(type(player)=='table'and player.is_local==true)then
        return no('NOT_LOCAL_PLAYER: only the local player (the host) can be credited for a Runtime entity')
    end
    local world=world_module.open()
    if not world then return no('UNAVAILABLE: no game world')end
    local game=world_module.game_state(world)
    if not(game and game.mission and game.host==true)then return no('NOT_HOST: a mission, as the host')end
    -- The credit goes to the owner of the entity's network object: the host that spawned it, which is the caller (a
    -- custom stratagem call runs on its thrower's machine, and a Runtime spawn on the host only).
    local scode,swhy=require('hd2runtime/runtime/multiplayer').solo_guard(#world_module.players(world),
        require('hd2runtime/runtime/multiplayer').entity_allowed(entity),'the credit is the host\'s')
    if scode then return no(scode..': '..swhy)end
    local entry=instances.lookup(entity)
    if not entry then return no('NOT_ASSOCIATED: the entity belongs to no custom stratagem call')end
    -- The call's caller is a Player handle (ctx.player, runtime/handles.lua): compare the canonical identity, its
    -- session peer id (an older association may hold the peer id itself).
    local caller=entry.player
    local caller_peer=type(caller)=='table'and caller.peer or caller
    if type(caller_peer)~='string'or caller_peer~=player.peer then
        return no('OTHER_PLAYER: the entity belongs to another player\'s call')
    end
    return require('hd2runtime/runtime/ownership').credit_to_host(world,entity,entry.call_id)
end
return M
