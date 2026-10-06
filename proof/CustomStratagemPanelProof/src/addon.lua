local hd2=require('mods/skyeshade/hd2runtime')
-- CustomStratagemPanelProof 0.7.0: SLOT OVERLAYS. The custom Gas Barrage icon in the native loadout slots of virtual
-- slots is drawn by the live-proven Runtime overlay (SlotOverlayProof 0.1.0) over the UNTOUCHED native slot, and the
-- panel's tile icon is drawn with the same technique (docs/custom-stratagems.md, "Slot icon overlays in the custom
-- stratagem system").
-- Development only; aboard the ship, solo, NO mission. This build WRITES (unchanged from 0.6.0):
--   * selecting Orbital Gas Barrage puts the vanilla Orbital Precision Strike token into the slot the native selector
--     is open for (replacing what it holds; the existing guarded loadout-record write), records that slot as a virtual
--     instance (several slots may hold Gas Barrage), then moves the native selector on to the next empty slot with the
--     live-proven slot-focus write (the native highlight AND the edited slot). With no empty slot left the panel
--     closes and the native selector stays open: close it with Back.
-- New in 0.7.0 (visual only, nothing written for it):
--   * every virtual slot shows the masked Gas Barrage icon over its native slot icon: a Runtime GUI in the Ui World at
--     layer 940 on an opaque plate of that slot's own icon background (layer 939, exactly the icon's quad), coloured as
--     the native slot colours the Precision Strike. Native slots (a natively picked Precision Strike included) get
--     nothing. The native slot's type, icon element, material, texture and UV are never written: the 0.5/0.6
--     borrowed Orbital Gas Strike icon is NOT used (it stays a documented fallback in the runtime);
--   * the panel is a Ui World GUI too; its tile is opaque and its icon is the same masked icon on the same plate with
--     the same colours.
-- No save-format, account, catalogue, inventory, mission record or StratagemInfo change; no calldown or payload change.
--
-- The panel sits right of the native details panel only while a native stratagem selector is open: Orbital Gas Barrage
-- and five visual placeholders.
--   * Mouse: hover focuses a tile; a left click on Orbital Gas Barrage selects it; placeholders are refused.
--   * F6 / Ctrl+F6: focus next / clear. F7: select the focused tile. Ctrl+F7: undo the newest selection.
--   * Ctrl+F9: slot overlays off / on (off shows the untouched native icons underneath). F8: icon diagnostics.
--   * F9: status. Every second aboard the ship, the saved loadout is read and the virtual slots reconstructed from it.
local mod=hd2.mod()
local BUILD='0.7.0 SLOT OVERLAYS'
mod:log('CustomStratagemPanelProof '..BUILD..' BUILD: selection is ON (a click or F7 on Orbital Gas Barrage writes the '
    ..'Precision Strike token into the open selector\'s slot and moves the native highlight and the edited slot to the '
    ..'next empty slot; Ctrl+F7 undoes the newest). Virtual slots show the Gas Barrage icon as a Runtime overlay over '
    ..'the untouched native slot (Ctrl+F9 toggles). F8 icon diagnostics; F9 status. Aboard the ship only; solo; no '
    ..'mission.')

local panel=require('hd2runtime/runtime/custom_stratagem_panel')
local selector=require('hd2runtime/runtime/stratagem_selector')
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local texts=require('hd2runtime/runtime/text_resources')
local world_module=require('hd2runtime/runtime/event_world')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local RESOURCE='mods/skyeshade/hd2runtime_custom_stratagem_panel_proof'

-- The Runtime-rendered icon: the artwork in the game's icon mask convention (red artwork in R, white in G, background
-- 0), converted from the author's source picture source/orbital_gas_barrage.png (prepare_icons.py --mask).
local ICON=hd2.resources.image('orbital_gas_barrage_masks')
-- A diagnostic control only (never a tile icon): the VirtualSelectorProof 0.3.0 test pattern.
local PATTERN=hd2.resources.image('icon_test_pattern')
local GAS=virtual.define({id='orbital_gas_barrage',
    display={name=texts.handle('orbital_gas_barrage_name','Orbital Gas Barrage',RESOURCE),
        description=texts.handle('orbital_gas_barrage_description','Calls down a barrage of gas shells.',RESOURCE),
        icon=ICON},
    selection={token='Orbital Precision Strike'},mission={carrier='Orbital 120mm HE Barrage'}},RESOURCE)

local names_by_id={}
for name,entry in pairs(catalog.stratagems)do names_by_id[entry.root.id]=name end
local function report(handle)
    if handle.status=='selected'then
        local advance=handle.advance
        mod:log(('SELECTED: slot %d now holds the %s token for %s (%s; the game repainted the slot: %s); virtual slots: %s; '
            ..'next empty slot: %s; selector: %s'):format(handle.index,GAS.selection.token,GAS.id,
            handle.written and'written'or'it already held the token: no write',
            tostring(handle.verify and handle.verify.repainted),selector.slots_text(selector.virtual_slots()),
            handle.next and tostring(handle.next)or'none',advance and(tostring(advance.status)..(advance.slot and(' to slot '
            ..advance.slot)or'')..(advance.reason and(' ('..tostring(advance.reason)..')')or''))or'not moved'))
    elseif handle.status=='restored'then
        mod:log('RESTORED: slot '..handle.index..' is back as it was (exact: '..tostring(handle.exact)..'); virtual slots: '
            ..selector.slots_text(selector.virtual_slots()))
    else
        mod:log(('selection REFUSED (nothing written): %s: %s'):format(tostring(handle.code),tostring(handle.reason)))
    end
end

local P=panel.panel({renderer='compact',placeholders=5,focus=true,selection=true,mouse=true,on_selected=report,
    icon_pattern=PATTERN})

hd2.input.bind('custom_stratagem_panel_proof.focus',{key='F6',on_press=function()mod:log('F6: '..P.focus_next())end})
hd2.input.bind('custom_stratagem_panel_proof.unfocus',{key='Ctrl+F6',on_press=function()mod:log('Ctrl+F6: '..P.clear_focus())end})
hd2.input.bind('custom_stratagem_panel_proof.select',{key='F7',on_press=function()mod:log('F7: '..P.press())end})
hd2.input.bind('custom_stratagem_panel_proof.restore',{key='Ctrl+F7',on_press=function()mod:log('Ctrl+F7: '..P.cancel())end})
hd2.input.bind('custom_stratagem_panel_proof.icon_test',{key='F8',on_press=function()mod:log('F8: '..P.toggle_icon_test())end})
hd2.input.bind('custom_stratagem_panel_proof.slot_overlays',{key='Ctrl+F9',on_press=function()
    mod:log('Ctrl+F9: slot overlays '..(P.set_slot_overlays(not P.overlays)and'on'or'off (the native icons underneath)'))
end})
hd2.input.bind('custom_stratagem_panel_proof.status',{key='F9',on_press=function()
    mod:log('F9 ['..BUILD..']: '..P.status()..'; virtual slots: '..selector.slots_text(selector.virtual_slots()))
end})

-- Aboard the ship: the saved loadout, read-only, whenever it changes, matched against the Runtime's virtual slots.
local saved_key
hd2.every(1,function()
    local world=world_module.open()
    if not world then return end
    local state=hd2.game_state()
    if state and state.mission then return end
    local saved=loadout.saved(world)
    local parts,ids={},{}
    for index,pair in ipairs(saved and saved.pairs or{})do
        parts[index]=names_by_id[pair.id]or tostring(pair.id)
        ids[index]=pair.id
    end
    local key=table.concat(parts,'; ')
    if key~=saved_key then
        saved_key=key
        local slots,n=selector.reconstruct(ids)
        local found={}
        for slot=0,3 do if slots and slots[slot]then found[#found+1]='slot '..slot..' = '..slots[slot]end end
        mod:log(('saved ship loadout: %s; %s'):format(key~=''and key or'none',slots and(('%d virtual slot%s reconstructed: '
            ..'%s (token %s)'):format(n,n==1 and''or's',table.concat(found,', '),GAS.selection.token))
            or'no virtual slot recognised in this order'))
    end
end,{id='custom-stratagem-panel-proof'})
mod:log('loaded ('..BUILD..'): virtual stratagem '..GAS.id..' (token '..GAS.selection.token..', carrier '
    ..GAS.mission.carrier..', icon orbital_gas_barrage_masks drawn over virtual slots) and 5 visual placeholders. Click or '
    ..'F7 selects; Ctrl+F7 undoes; F6 focus; F8 icon diagnostics; Ctrl+F9 slot overlays; F9 status.')
