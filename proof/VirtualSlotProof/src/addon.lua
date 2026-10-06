local hd2=require('mods/skyeshade/hd2runtime')
-- VirtualSlotProof 0.1.0: the mission-time slot conversion proof (docs/custom-stratagems.md, "Mission-time slot
-- conversion"). Development only: no custom presentation, code or payload.
--
-- Ship loadout: TWO Orbital Precision Strikes (the duplicate needs the Stratagem MultiSelect mod; this proof never
-- writes the loadout, the save or the account). In a solo mission, as host, once the HUD's stratagem list is filled,
-- the LATER Precision Strike entry of the local player's mission stratagem record becomes the Orbital 120mm HE
-- Barrage (owned, not selected): one guarded 4-byte write through runtime/stratagem_slot_conversion.lua, after the
-- 120mm's call-in package is loaded. The game then sees two different vanilla stratagems:
--   * the HUD refreshes that slot itself (its own type-change path; this proof only reads it);
--   * Right Right Up (the Precision Strike's code) calls the Precision Strike, Right Right Down Left Right Down (the
--     120mm's) the 120mm barrage, each from its own slot.
-- The game rebuilds the record for the ship at the mission end, which discards the conversion; the saved loadout keeps
-- the two Precision Strikes.
--
-- Development-only parts: the read-only probe (record entries, token entries, the carrier's checks), the HUD follow
-- check, F9 status. Restore: MODS > Virtual Slot Proof > "Convert the second Precision Strike" off + APPLY, in the
-- mission. Without Mod Options Menu nothing is converted.
local mod=hd2.mod()
local BUILD='0.1.0 VIRTUAL-SLOT-CONVERSION'
mod:log('VirtualSlotProof '..BUILD..' BUILD: in a solo mission the second Orbital Precision Strike slot becomes the Orbital '
    ..'120mm HE Barrage (record entry type only). Select two Orbital Precision Strikes on the ship.')

local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local world_module=require('hd2runtime/runtime/event_world')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local stratagem_hud=require('hd2runtime/runtime/stratagem_hud')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local SPEC={token='Orbital Precision Strike',carrier='Orbital 120mm HE Barrage'}
local TOKEN_ID=catalog.stratagems[SPEC.token].root.id

local names_by_id={}
for name,entry in pairs(catalog.stratagems)do names_by_id[entry.root.id]=name end
local function label(world,kind)
    local id=loadout.id_of(world,kind)
    return ('%s (type %s)'):format(names_by_id[id]or'not catalogued',tostring(kind))
end

------------------------------------------------------------------------------------------------- the options --
local options=hd2.options({id='virtual_slot_proof',title='Virtual Slot Proof',fallback='disable'})
local toggle=options:toggle({id='convert',label='Convert the second Precision Strike',default=true,
    description='In a solo mission the second Orbital Precision Strike slot becomes the Orbital 120mm HE Barrage. Off + '
        ..'APPLY in the mission converts it back.'})

local op={state='idle',attempts=0}   -- idle | converting | converted | restoring | restored | refused | gone
local mission_clock,populated_at,probed,followed=0,nil,false,nil
local function entries_text(world)
    local view=slots.inspect(world,SPEC)
    if not view.entries then return tostring(view.record and view.record.reason)end
    local parts={}
    for _,entry in ipairs(view.entries)do
        parts[#parts+1]=('%d:%s%s'):format(entry.index,label(world,entry.type),entry.granted==1 and'*'or'')
    end
    return table.concat(parts,', ')..' (* granted)'
end
local function report(handle)
    if handle.status=='converted'then
        op.state='converted';followed={since=mission_clock}
        mod:log('CONVERTED in the mission: record entry '..handle.index..'; the record now: '
            ..entries_text(world_module.open()))
    elseif handle.status=='restored'then
        op.state='restored'
        mod:log('RESTORED: '..entries_text(world_module.open()))
    else
        op.state='refused'
        mod:log(('conversion REFUSED (nothing written): %s: %s'):format(tostring(handle.code),tostring(handle.reason)))
    end
end

------------------------------------------------------------------------------------------------- the loop --
local in_mission,ship_key=false,nil
hd2.every(0.5,function()
    local state=hd2.game_state()
    local mission=state and state.mission
    local world=world_module.open()
    if not world then return end
    if mission and not in_mission then
        in_mission,mission_clock,populated_at,probed,followed=true,0,nil,false,nil
        if op.state~='refused'then op.state='idle'end
        mod:log(('mission started (host %s)'):format(tostring(state.host)))
    elseif not mission and in_mission then
        in_mission=false
        mod:log('mission ended (state '..tostring(state and state.name)..'); conversion state: '..op.state)
        if op.state=='converted'then op.state='gone'end
    end
    if not mission then
        -- Aboard the ship: the saved loadout, read-only.
        local saved=loadout.saved(world)
        local parts,count={},0
        for index,pair in ipairs(saved and saved.pairs or{})do
            parts[index]=names_by_id[pair.id]or tostring(pair.id)
            if pair.id==TOKEN_ID then count=count+1 end
        end
        local key=table.concat(parts,'; ')
        if key~=ship_key then
            ship_key=key
            mod:log(('saved ship loadout: %s -> %s'):format(key~=''and key or'none',count>=2
                and'two Orbital Precision Strikes saved: the second becomes the 120mm in the mission'
                or count..' Orbital Precision Strike saved: select two (Stratagem MultiSelect) for this proof'))
        end
        return
    end
    mission_clock=mission_clock+0.5
    if not populated_at then
        if stratagem_hud.populated(world)then populated_at=mission_clock end
        return
    end
    if mission_clock<populated_at+5 then return end
    if not probed then
        probed=true
        local view=slots.inspect(world,SPEC)
        mod:log('slot probe (before any write): record entries: '..entries_text(world))
        mod:log(('slot probe: %d Orbital Precision Strike loadout entries; carrier %s: owned %s, selectable %s, enabled %s, '
            ..'unlimited %s, in the record %s, call-in package %s; %s stratagem records'):format(#(view.tokenEntries or{}),
            SPEC.carrier,tostring(view.carrierOwned),tostring(view.carrierSelectable),tostring(view.carrierEnabled),
            tostring(view.carrierUnlimited),tostring(view.carrierInRecord==true),tostring(view.carrierPackage),
            tostring(view.records)))
    end
    local wanted=toggle:available()and toggle:get()==true
    if not toggle:available()and toggle:disables()and not op.said_menu then
        op.said_menu=true
        mod:log('Mod Options Menu unavailable: nothing is converted (the toggle is the restore path)')
    end
    if wanted and op.state=='idle'then
        op.state='converting';op.attempts=op.attempts+1
        slots.convert(SPEC,report)
    elseif not wanted and op.state=='converted'then
        op.state='restoring'
        slots.restore(report)
    end
    -- The vanilla HUD's own refresh: the slot drawing the converted entry takes the carrier.
    if followed and not followed.done then
        local follows,index=slots.hud_follows(world)
        if follows then
            followed.done=true
            mod:log(('HUD slot %d now holds %s (the vanilla HUD refreshed it from the type change; nothing written to '
                ..'the HUD)'):format(index,SPEC.carrier))
        elseif mission_clock>followed.since+10 then
            followed.done=true
            mod:log('HUD did NOT follow within 10 s: the slot drawing the converted entry still holds another type')
        end
    end
end,{id='virtual-slot-proof'})

hd2.input.bind('virtual_slot_proof.status',{key='F9',on_press=function()
    local world=world_module.open()
    local state=hd2.game_state()or{}
    local current=slots.state()
    mod:log(('F9 [%s]: conversion %s (attempts %d), toggle %s; converted entry %s; record: %s; mission %s, host %s'):format(
        BUILD,op.state,op.attempts,toggle:get()and'on'or'off',current and current.converted and tostring(current.index)
        or'none',world and state.mission and entries_text(world)or'-',tostring(state.mission==true),tostring(state.host)))
end})
mod:log('loaded ('..BUILD..'): select two Orbital Precision Strikes (Stratagem MultiSelect), start a solo mission; after '
    ..'"CONVERTED", Right Right Up calls the Precision Strike and Right Right Down Left Right Down the 120mm. F9 status.')
