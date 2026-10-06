local hd2=require('mods/skyeshade/hd2runtime')
-- VirtualSelectorProof 0.6.0: COORDINATE DIAGNOSTICS for the Runtime card in the native stratagem list
-- (docs/custom-stratagems.md, "Coordinate calibration"). 0.5.0 logged the card as shown in its cell but it could not be
-- seen. This build measures, against the native cards' own transforms, where the Runtime GUI draws. Development only;
-- aboard the ship, no mission step, and NO selection (F7 is off): it writes nothing to the game.
--   * Diagnostics (on at start; F8 toggles them): each time the list is still, the calibration is logged (the GUI
--     resolution, the list frame, the scroll offset and limit, the card scale, and for three native cards N0, N1, N2 and
--     the virtual cell V every stage: content -> after scroll -> model -> native transform -> Runtime GUI) and markers
--     are drawn on top (layers 990-993): magenta outlines and centre dots on N0..N2, a green outline and dot on V, a cyan
--     outline on the list frame F, yellow squares in the four corners of the Runtime GUI (BL 0,0 / BR / TL / TR) and a
--     cross at its centre, and yellow "L" probe dots at layer 21 inside N0 and V.
--   * The card is the tile alone (background, icon, border; no name or description), at layer 900.
--
-- One virtual stratagem, "Orbital Gas Barrage": this proof's own image as its icon and Runtime texts as its name and
-- description; its token is the Orbital Precision Strike (the 120mm carrier is not used here).
--   * The card's cell comes from the native list's layout: the free cell after the final native card; if the final row
--     is full, a new row only where the list can show it, else the free cell at the end of the token's own category
--     section (the Orbital section for the Precision Strike), else of any section. Its place on screen comes from the
--     list's scroll offset and the native cards' own geometry, at the native size and pitch. It is drawn only while that
--     cell is inside the list's viewport and clear of every native card: scroll to the end of the list to find it.
--     While the list scrolls or rebuilds the card is hidden, and drawn again once the list is still. The name and
--     description are drawn only where free cells (or a free row) have room for them. The native cards are never
--     touched.
--   * F7 (selection) is disabled in this build. F9: status.
local mod=hd2.mod()
local BUILD='0.6.0 COORDINATE-DIAGNOSTICS'
mod:log('VirtualSelectorProof '..BUILD..' BUILD: draws only (F7 selection is off). Open a stratagem grid: calibration '
    ..'markers N0 N1 N2 (native cards), V (the Runtime cell), F (the list frame) and the screen corners are drawn each '
    ..'time the list is still. F8 toggles them.')

local selector=require('hd2runtime/runtime/stratagem_selector')
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local texts=require('hd2runtime/runtime/text_resources')
local world_module=require('hd2runtime/runtime/event_world')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local RESOURCE='mods/skyeshade/hd2runtime_virtual_selector_proof'

local NAME=texts.handle('orbital_gas_barrage_name','Orbital Gas Barrage',RESOURCE)
local ICON=hd2.resources.image('orbital_gas_barrage_icon')
local GAS=virtual.define({id='orbital_gas_barrage',
    display={name=NAME,description=texts.handle('orbital_gas_barrage_description','Calls down a barrage of gas shells.',
        RESOURCE),icon=ICON},
    selection={token='Orbital Precision Strike'},mission={carrier='Orbital 120mm HE Barrage'}},RESOURCE)

local names_by_id={}
for name,entry in pairs(catalog.stratagems)do names_by_id[entry.root.id]=name end
local function slots_text(view)
    if not(view and view.record)then return'no local record'end
    local parts={}
    for _,entry in ipairs(view.record.entries)do
        parts[#parts+1]=('%d:%s'):format(entry.index,names_by_id[loadout.id_of(world_module.open(),entry.type)]
            or('type '..tostring(entry.type)))
    end
    return #parts>0 and table.concat(parts,', ')or'empty'
end
local function report(handle)
    if handle.status=='selected'then
        local id=handle.identity
        mod:log(('SELECTED: slot %d now holds the %s token for %s (the game repainted the slot: %s); the Runtime records '
            ..'slot %s of %d entries as virtual'):format(handle.index,GAS.selection.token,GAS.id,
            tostring(handle.verify and handle.verify.repainted),id and tostring(id.slot)or'?',id and#id.pairs or 0))
    elseif handle.status=='restored'then
        mod:log('RESTORED: slot '..handle.index..' is back as it was (exact: '..tostring(handle.exact)..')')
    else
        mod:log(('selection REFUSED (nothing written): %s: %s'):format(tostring(handle.code),tostring(handle.reason)))
    end
end

local S=selector.selector({placement='grid',focus_frame=false,tile_only=true,layer=900,diagnostics=true,
    on_selected=report})
-- The lifecycle, read-only.
selector.watch(function(event,view)
    if event=='opened'then mod:log('loadout screen opened: '..slots_text(view)..' ('..view.players..' player'
        ..(view.players==1 and''or's')..')')
    elseif event=='grid_opened'then mod:log('stratagem grid opened for slot '..view.editedSlot)
    elseif event=='grid_closed'then mod:log('stratagem grid closed')
    elseif event=='record_changed'then mod:log('loadout slots now: '..slots_text(view))
    elseif event=='closed'then mod:log('loadout screen closed')end
end)

hd2.input.bind('virtual_selector_proof.select',{key='F7',on_press=function()
    mod:log('F7: selection is disabled in the '..BUILD..' build (rendering only)')
end})
hd2.input.bind('virtual_selector_proof.diagnostics',{key='F8',on_press=function()
    local on=S.diagnostics()
    mod:log('F8: coordinate diagnostics '..(on and'on (drawn when the list is still)'or'off'))
end})

-- Aboard the ship: the saved loadout, read-only, whenever it changes, matched against the Runtime's virtual record.
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
        local slot,definition=selector.reconstruct(ids)
        mod:log(('saved ship loadout: %s; %s'):format(key~=''and key or'none',slot and('virtual slot reconstructed: slot '
            ..slot..' = '..definition)or'no virtual slot recognised in this order'))
    end
end,{id='virtual-selector-proof'})

hd2.input.bind('virtual_selector_proof.status',{key='F9',on_press=function()
    local world=world_module.open()
    local view=world and selector.screen(world)
    local id=selector.identity()
    local drawing=S.renderer()
    local place=S.placement
    mod:log(('F9 [%s]: loadout screen %s%s; card %s%s; drawing %s%s; virtual slot %s'):format(BUILD,
        view and view.open and'open'or'closed',view and view.open and(', grid '..(view.gridOpen and('slot '
        ..view.editedSlot)or'closed')..', slots '..slots_text(view))or'',S.shown and'shown'or'hidden',
        place and(' (%s cell, row %d, column %d)'):format(place.target.kind,place.target.row,place.target.column)or'',
        drawing and drawing.state or'not started',drawing and drawing.reason and(' ('..drawing.reason..')')or'',
        id and(tostring(id.slot)..' ('..id.definition..')')or'none'))
end})
mod:log('loaded ('..BUILD..'): virtual stratagem '..GAS.id..' (token '..GAS.selection.token..'). F8 diagnostics on/off; '
    ..'F9 status; F7 selection is off in this build.')
