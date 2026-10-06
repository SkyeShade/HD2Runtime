-- THE CARRIER-IN-SLOT PROBE (development, solo host; the user's proposal of 2026-10-07; docs/custom-stratagem-api.md
-- "selection = 'carrier' (probe)"). A custom stratagem registered with selection = 'carrier' is picked into its loadout
-- slot as its CARRIER itself, not the Orbital Precision Strike token:
--   * the pick: the same guarded loadout-record write as the token's (runtime/stratagem_selector.lua select,
--     opts.carrier), with the carrier the ship allocation gives it now; the virtual slot records the carrier's stable
--     id, so the selector's tracking, its reconstruction and the loadout overlay follow it unchanged;
--   * the allocation: a carrier that the local loadout holds ONLY in such slots is not a native pick of this player
--     (M.discount), so it does not invalidate itself;
--   * the presentation: applied as early as the Runtime runs after the launch: on the loading screen (game state
--     PrepareMission) when the Runtime's update runs there, else in the mission's first update, before the HUD is
--     populated, so the HUD builds the slot with the custom name and icon from its first frame (the HUD does not
--     rebuild a slot whose type never changes);
--   * the mission: nothing converts; the slots are verified and adopted (stratagem_slot_conversion.adopt_virtual) and
--     the cooldown, uses, code, beacon and payload work as for a converted slot;
--   * the timing (the probe's question): every game state change, the presentation and the HUD population are logged
--     with their Runtime clock (CARRIER-IN-SLOT PROBE ...).
-- Several players: not part of the probe (selection writes the token there, as before; a carrier slot picked solo is
-- refused and locked in a multiplayer mission).
local world_module=require('hd2runtime/runtime/event_world')
local log_module=require('hd2runtime/runtime/log')
local M={}
local state={early={},last_state=nil,clock=0,hud=false}

local function log(text)log_module.emit('[HD2Runtime] CARRIER-IN-SLOT PROBE '..text)end

-- Whether a definition is in the probe's selection mode.
function M.enabled(d)return type(d)=='table'and d.selection=='carrier'end

-- The stable ids the LOCAL loadout holds only in carrier-mode virtual slots: never elsewhere in it, and in no other
-- player's record. ids: the local loadout's stable ids in order; set: the selector's virtual slots; peer_ids: a set of
-- the stable ids other players' records hold (nil: none).
function M.own_carriers(ids,set,peer_ids)
    local inside,outside={},{}
    for k,id in ipairs(ids or{})do
        local e=set and set.slots and set.slots[k-1]
        if e and e.carrier and e.token==id then inside[id]=true else outside[id]=true end
    end
    local out={}
    for id in pairs(inside)do
        if not outside[id]and not(peer_ids and peer_ids[id])then out[id]=true end
    end
    return out
end
-- A copy of a native-pick set without `own` (M.own_carriers), and the ids removed.
function M.discount(present,own)
    local out,removed={},{}
    for id in pairs(present or{})do
        if own and own[id]then removed[#removed+1]=id else out[id]=true end
    end
    table.sort(removed)
    return out,removed
end

-- The carrier-mode virtual slots of a set: {[definition id] = {slots = {...}, id = carrier stable id}}.
function M.slots_by_definition(set)
    local out={}
    for slot,e in pairs(set and set.slots or{})do
        if e.carrier then
            local x=out[e.definition]or{slots={},id=e.token}
            out[e.definition]=x
            x.slots[#x.slots+1]=slot
            if x.id~=e.token then x.mixed=true end
        end
    end
    for _,x in pairs(out)do table.sort(x.slots)end
    return out
end

-- Every Runtime step (the orchestrator's): the timing log and the early presentation. ctx = {game (event_world
-- game_state), clock, definitions (id -> definition), set (the virtual slots), carrier_name(stable id) -> name,
-- players (the player count, or nil when unreadable), hud() -> whether the mission HUD is populated (read lazily)}.
function M.step(ctx)
    local game=ctx.game
    state.clock=ctx.clock
    local by=M.slots_by_definition(ctx.set)
    if not next(by)then state.last_state=game and game.name;return end
    if game and game.name~=state.last_state then
        log(('TIMING: game state %s -> %s at %.2f s'):format(tostring(state.last_state),tostring(game.name),ctx.clock))
        state.last_state=game.name
        if game.name=='Ship'then state.early,state.hud={},false end
    end
    local populated=state.hud
    if game and game.mission and not populated then populated=ctx.hud()==true end
    if game and game.mission and populated and not state.hud then
        state.hud=true
        local parts={}
        for id,x in pairs(state.early)do parts[#parts+1]=('%s presented at %.2f s during %s'):format(id,x.at,x.during)end
        table.sort(parts)
        log(('TIMING: the mission HUD is populated at %.2f s; %s'):format(ctx.clock,#parts>0 and table.concat(parts,'; ')
            or'no early presentation (applied by the mission steps after the HUD instead)'))
    end
    -- The early presentation: entering the mission (the loading screen) or the mission before the HUD is populated.
    local entering=game and(game.name=='PrepareMission'or(game.mission and not populated))
    if not entering then return end
    if ctx.players and ctx.players>1 then return end
    local cp=require('hd2runtime/runtime/carrier_presentation')
    for id,x in pairs(by)do
        local d=ctx.definitions[id]
        local name=ctx.carrier_name(x.id)
        if d and name and not state.early[id]and not x.mixed and not cp.applied(name)then
            state.early[id]={carrier=name,at=ctx.clock,during=game.name,pending=true}
            log(('%s: applying the presentation on its carrier %s during %s at %.2f s (loadout slot%s %s)'):format(id,name,
                game.name,ctx.clock,#x.slots==1 and''or's',table.concat(x.slots,', ')))
            cp.apply({carrier=name,text=d.texts,icon=d.icon,code=d.code},function(h)
                local e=state.early[id]
                if not e then return end
                e.pending=false
                e.applied=h.status=='applied'
                log(('%s: presentation on %s %s at %.2f s%s'):format(id,name,e.applied and'APPLIED'or'REFUSED',state.clock,
                    e.applied and''or(': '..tostring(h.code)..': '..tostring(h.reason))))
            end)
        end
    end
end
-- Whether the early presentation is applied for a definition on that carrier (the mission step then skips its own).
function M.early(id,carrier)
    local e=state.early[id]
    return e~=nil and e.applied==true and e.carrier==carrier
end
-- Whether a definition's early presentation is still being applied (the mission step waits for it).
function M.waiting(id)
    local e=state.early[id]
    return e~=nil and e.pending==true
end
-- Whether an early presentation is applied or pending (the ship-side restore waits while the game enters the mission).
function M.entering()
    for _,e in pairs(state.early)do if e.applied or e.pending then return true end end
    return false
end
function M.log(text)log(text)end
function M.reset_for_tests()state={early={},last_state=nil,clock=0,hud=false}end
return M
