local hd2=require('mods/skyeshade/hd2runtime')
-- PanelIconProof 0.1.0: the custom panel's icon as the game's icon masks (docs/custom-stratagems.md, "The panel icon:
-- the game's mask convention"). Development only; aboard the ship; VISUAL ONLY: nothing is selected or written.
--
-- The vanilla stratagem icon shader treats the texture's channels as masks coloured by the UI (R: the category colour,
-- G: white, B: a shadow). A full-colour picture lights the red mask in its white areas too, so the panel showed
-- orbital_gas_barrage wrongly. orbital_gas_barrage_masks is the same artwork converted to that convention (red artwork in
-- R, white artwork in G, the background 0: sdk/tools/hd2_image.py icon_masks, by
-- proof/CustomStratagemPanelProof/prepare_icons.py --mask); the original stays in this proof as the comparison.
--   * The panel (the 0.3/0.6 layout and lifecycle) shows the masked icon on the Orbital Gas Barrage tile.
--   * F6: focus next (tooltip). F8: icon diagnostics: row 1 coloured (A font, A vanilla 120mm icon as the reference, B the
--     masked icon by name and by hash, E original, C texture), row 2 the same plain, then the masked icon at four sizes.
--   * F9: status.
local mod=hd2.mod()
local BUILD='0.1.0 MASKED ICON'
mod:log('PanelIconProof '..BUILD..' BUILD: the Orbital Gas Barrage tile shows the icon converted to the game\'s icon '
    ..'masks; F8 compares it with the original picture and the vanilla 120mm icon. Visual only: nothing is selected or '
    ..'written.')

local panel=require('hd2runtime/runtime/custom_stratagem_panel')
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local texts=require('hd2runtime/runtime/text_resources')
local RESOURCE='mods/skyeshade/hd2runtime_panel_icon_proof'

local MASKS=hd2.resources.image('orbital_gas_barrage_masks')
local ORIGINAL=hd2.resources.image('orbital_gas_barrage')
virtual.define({id='orbital_gas_barrage',
    display={name=texts.handle('orbital_gas_barrage_name','Orbital Gas Barrage',RESOURCE),
        description=texts.handle('orbital_gas_barrage_description','Calls down a barrage of gas shells.',RESOURCE),
        icon=MASKS},
    selection={token='Orbital Precision Strike'},mission={carrier='Orbital 120mm HE Barrage'}},RESOURCE)

local P=panel.panel({renderer='compact',placeholders=5,focus=true,selection=false,mouse=true,icon_pattern=ORIGINAL,
    icon_pattern_label='E original'})
hd2.input.bind('panel_icon_proof.focus',{key='F6',on_press=function()mod:log('F6: '..P.focus_next())end})
hd2.input.bind('panel_icon_proof.icon_test',{key='F8',on_press=function()mod:log('F8: '..P.toggle_icon_test())end})
hd2.input.bind('panel_icon_proof.status',{key='F9',on_press=function()mod:log('F9 ['..BUILD..']: '..P.status())end})
mod:log('loaded ('..BUILD..'): the masked icon orbital_gas_barrage_masks on the tile, the original orbital_gas_barrage '
    ..'as the comparison. F6 focus; F8 icon diagnostics; F9 status.')
