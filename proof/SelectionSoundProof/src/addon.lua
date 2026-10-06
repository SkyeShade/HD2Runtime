local hd2=require('mods/skyeshade/hd2runtime')
-- SelectionSoundProof 0.1.0: the loadout screen's own UI sound events through the engine's Wwise Lua API, to identify
-- the native selection sound (docs/custom-stratagems.md, "The selection sound"; runtime/ui_sound.lua). Development
-- only; aboard the ship. No memory write, no selection, no native call: a key posts one event with
-- stingray.WwiseWorld.trigger_event on the WwiseWorld of the game's own Game World (matched by its address), by a name
-- whose hash is the game's event id. Nothing plays unless a key is pressed.
--   * F5: the picker-close event (the game plays it when a pick fills the last slot, and on Back).
--   * F6: the slot-select event (the game plays it when a loadout slot is selected and the grid opens).
--   * F7: ui_generic_select. F8: ui_armory_item_hover_select (two real UI event names).
--   * F9: status (the API, the Game World match, each event known to the sound engine): nothing plays.
local mod=hd2.mod()
local BUILD='0.1.0 UI SOUND IDENTIFICATION'
mod:log('SelectionSoundProof '..BUILD..' BUILD: F5 picker close, F6 slot select, F7 ui_generic_select, F8 '
    ..'ui_armory_item_hover_select; F9 status. Aboard the ship; nothing plays unless a key is pressed; nothing is written.')

local sound=require('hd2runtime/runtime/ui_sound')
local function play(key,label)
    local result,code,why=sound.play(key)
    mod:log(result and('%s: PLAYED %s (playing id %s)'):format(label,key,tostring(result.playing))
        or('%s: NOT played %s: %s: %s'):format(label,key,tostring(code),tostring(why)))
end
hd2.input.bind('selection_sound_proof.close',{key='F5',on_press=function()play('picker_close','F5')end})
hd2.input.bind('selection_sound_proof.slot',{key='F6',on_press=function()play('slot_select','F6')end})
hd2.input.bind('selection_sound_proof.generic',{key='F7',on_press=function()play('generic_select','F7')end})
hd2.input.bind('selection_sound_proof.hover',{key='F8',on_press=function()play('item_hover_select','F8')end})
hd2.input.bind('selection_sound_proof.status',{key='F9',on_press=function()
    mod:log('F9 ['..BUILD..']: '..sound.status())
end})
mod:log('loaded ('..BUILD..'): F5 picker close, F6 slot select, F7 ui_generic_select, F8 ui_armory_item_hover_select, '
    ..'F9 status.')
