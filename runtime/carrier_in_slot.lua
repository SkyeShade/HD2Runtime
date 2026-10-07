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
--   * the LOCK (probe 0.2.0): from the mission's first update until the custom stratagem is READY TO CALL, each
--     carrier slot's own record entry is locked (slot_cooldown.lock_entry: its cooldown end far ahead, so the game
--     refuses a call). Before READY the slot already holds the carrier, with the custom code, and a call would be the
--     carrier's own vanilla call. Released (unlock_entry: the end written back) right before its cooldown is armed;
--     a definition that never becomes ready stays locked;
--   * no lockout (0.2.1, the user's rule): a carrier slot never blocks its carrier natively (only the regular rule
--     does: the last viable carrier of a selected custom stratagem); the slot keeps its carrier while nobody else
--     holds it (the allocator's pin), and when anyone else picks it the slot MOVES to its next carrier aboard the ship
--     (stratagem_selector.move_carrier, custom_stratagems' probe_move_step). The early presentation goes only on a
--     carrier that is the definition's own and no real pick (ctx.consistent);
--   * the doubles (0.3.0): the carrier a carrier slot holds stays pickable natively in the player's other slots (the
--     game's "already in this loadout" grey lifted: stratagem_blocking.enable); picking it moves the custom slot;
--   * the launch fallback (0.3.0): a slot that could not move before the launch holds a carrier that is no longer its
--     carrier; the mission swaps it (old carrier -> its carrier, stratagem_selector.reconvert_virtual) while locked,
--     then releases it as an adopted slot (Runtime-counted uses);
--   * the mission: nothing converts; the slots are verified and adopted (stratagem_slot_conversion.adopt_virtual),
--     their native per-slot uses written when the definition has `uses` (0.2.0), and the cooldown, code, beacon and
--     payload work as for a converted slot;
--   * the timing (the probe's question): every game state change, the presentation and the HUD population are logged
--     with their Runtime clock (CARRIER-IN-SLOT PROBE ...).
-- Several players (r38, EXPERIMENTAL): with custom multiplayer (every lobby member a compatible Runtime) the pick writes
-- the carrier the lobby gives it; the other players' native picks the loadout screen shows move it before the launch;
-- in the mission the lock is marked as a lockout write (this machine's own entry), the native uses go through the
-- client-write proof, and every other player's carrier slot is presented on each machine (custom_stratagems
-- probe_remote_step), so the teammate panel shows it natively. Without custom multiplayer: the token, as before.
local world_module=require('hd2runtime/runtime/event_world')
local log_module=require('hd2runtime/runtime/log')
local M={}
local state={early={},locks={},last_state=nil,clock=0,hud=false}

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
-- players (the player count, or nil when unreadable), hud() -> whether the mission HUD is populated (read lazily),
-- consistent(id, x) -> true, or false and why (the slots' carrier is not the definition's own carrier now, or it is
-- also a real pick: no early presentation; the mission refuses the definition)}.
function M.step(ctx)
    local game=ctx.game
    state.clock=ctx.clock
    local by=M.slots_by_definition(ctx.set)
    if not next(by)then state.last_state=game and game.name;return end
    if game and game.name~=state.last_state then
        log(('TIMING: game state %s -> %s at %.2f s'):format(tostring(state.last_state),tostring(game.name),ctx.clock))
        state.last_state=game.name
        if game.name=='Ship'then state.early,state.locks,state.hud={},{},false end
    end
    local populated=state.hud
    if game and game.mission and not populated then populated=ctx.hud()==true end
    if game and game.mission and populated and not state.hud then
        state.hud=true
        local parts={}
        for id,x in pairs(state.early)do
            parts[#parts+1]=x.skipped and('%s NOT presented early (%s)'):format(id,x.skipped)
                or('%s presented at %.2f s during %s'):format(id,x.at,x.during)
        end
        table.sort(parts)
        log(('TIMING: the mission HUD is populated at %.2f s; %s'):format(ctx.clock,#parts>0 and table.concat(parts,'; ')
            or'no early presentation (applied by the mission steps after the HUD instead)'))
    end
    -- Several players: only with custom multiplayer (r38, EXPERIMENTAL), the lock marked as a lockout write.
    local several=ctx.players~=nil and ctx.players>1
    if several and not ctx.mp then return end
    -- The lock: the mission's first update (its record is this mission's), once per definition.
    if game and game.mission and ctx.world then
        for id,x in pairs(by)do
            if not state.locks[id]and not x.mixed then M.lock(ctx.world,id,x,several and'lockout'or nil)end
        end
    end
    -- The early presentation: entering the mission (the loading screen) or the mission before the HUD is populated.
    local entering=game and(game.name=='PrepareMission'or(game.mission and not populated))
    if not entering then return end
    local cp=require('hd2runtime/runtime/carrier_presentation')
    for id,x in pairs(by)do
        local d=ctx.definitions[id]
        local name=ctx.carrier_name(x.id)
        local ok,why=true,nil
        if ctx.consistent then ok,why=ctx.consistent(id,x)end
        if d and name and not state.early[id]and not x.mixed and not ok then
            state.early[id]={carrier=name,at=ctx.clock,during=game.name,skipped=why}
            log(('%s: NO early presentation on %s: %s (never on a carrier that is not its own)'):format(id,name,
                tostring(why)))
        end
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
    -- r41: and still applied (if anything restored it, the mission's own presenting step applies it again).
    return e~=nil and e.applied==true and e.carrier==carrier
        and require('hd2runtime/runtime/carrier_presentation').applied(carrier)==true
end
-- Locks each of a definition's carrier slots (x = M.slots_by_definition(set)[id]) in this mission's own record.
function M.lock(world,id,x,client)
    -- client = 'lockout' (several players): this machine's own entry's cooldown end, the multiplayer lockout mark.
    if client=='lockout'then require('hd2runtime/runtime/multiplayer').enable_lockout(true)end
    local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
    local cooldowns=require('hd2runtime/runtime/slot_cooldown')
    local carrier_type=require('hd2runtime/runtime/stratagem_loadout').type_of(world,x.id)
    local record=slots.local_record(world)
    if not(record and carrier_type)then return end
    local picks={}
    for _,entry in ipairs(record.entries)do if entry.granted==0 then picks[#picks+1]=entry end end
    local list={}
    for _,slot in ipairs(x.slots)do
        local entry=picks[slot+1]
        if not(entry and entry.type==carrier_type)then
            state.locks[id]={failed=('loadout slot %d does not hold its carrier (type %s)'):format(slot,tostring(carrier_type))}
            log(('%s: NOT LOCKED: %s'):format(id,state.locks[id].failed))
            return
        end
        local r,code,reason=cooldowns.lock_entry(world,{index=entry.index,token=carrier_type,label=id,client=client})
        if not(r and r.kind=='locked'and r.verified)then
            state.locks[id]={failed=tostring(code or(r and r.kind))..': '..tostring(reason)}
            log(('%s: NOT LOCKED (its slot can be called before it is ready): %s'):format(id,state.locks[id].failed))
            for _,l in ipairs(list)do cooldowns.unlock_entry(world,l)end
            return
        end
        list[#list+1]={index=entry.index,token=carrier_type,locked=r.raw_desired,original=r.raw_before,label=id,
            client=client}
    end
    state.locks[id]={entries=list}
    local indices={}
    for k,l in ipairs(list)do indices[k]=l.index end
    log(('%s: LOCKED record entr%s %s at %.2f s until it is ready to call (its slot holds the carrier with the custom '
        ..'code: a call before then would be the carrier\'s own)'):format(id,#list==1 and'y'or'ies',
        table.concat(indices,', '),state.clock))
end
-- Releases a definition's lock (its cooldown is armed right after). Returns true when nothing stays locked by it.
function M.release(world,id)
    local l=state.locks[id]
    if not(l and l.entries)then return true end
    local cooldowns=require('hd2runtime/runtime/slot_cooldown')
    local all=true
    for _,e in ipairs(l.entries)do
        local r,code,reason=world and cooldowns.unlock_entry(world,e)
        if r and r.verified then
            log(('%s: RELEASED record entry %d at %.2f s (%d write)'):format(id,e.index,state.clock,r.writes))
        else
            all=false
            log(('%s: record entry %d NOT RELEASED (it stays unavailable this mission): %s: %s'):format(id,e.index,
                tostring(code),tostring(reason)))
        end
    end
    l.entries=nil
    l.released=true
    return all
end
-- The launch fallback (0.3.0): a definition's locked entries now hold `kind` (the conversion swapped their type; their
-- locked cooldown end is untouched), so the release checks that type.
function M.retype(id,kind)
    local l=state.locks[id]
    for _,e in ipairs(l and l.entries or{})do e.token=kind end
end
-- Whether a definition's lock is held (or failed: {failed}). For tests and diagnostics.
function M.lock_state(id)return state.locks[id]end
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
function M.reset_for_tests()state={early={},locks={},last_state=nil,clock=0,hud=false}end
return M
