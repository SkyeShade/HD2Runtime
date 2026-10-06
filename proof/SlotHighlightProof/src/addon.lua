local hd2=require('mods/skyeshade/hd2runtime')
-- SlotHighlightProof 0.1.0: the native loadout slot highlight moved by guarded data writes (docs/custom-stratagems.md,
-- "Moving the native slot highlight"; runtime/stratagem_slot_focus.lua). Development only; aboard the ship, solo, NO
-- mission. Not combined with any custom stratagem: no loadout record, save, account or StratagemInfo write.
--   * F7: move the highlight to the next slot (0 -> 1 -> 2 -> 3): the panel focus, bit 1 on both slot widgets and the
--     frame-flash byte on both, which the game's own panel update consumes by redrawing both widgets. The edited slot
--     (where a pick lands) is NOT moved: with the selector open, a pick still goes to the slot it was opened on.
--   * Ctrl+F7: the same AND the edited slot (only while a stratagem selector is open): the next pick lands on the newly
--     highlighted slot.
--   * F8 / Ctrl+F8: the same towards the previous slot.
--   * F9: the highlight state (focus, edited slot, each widget's flags, flash byte and frame).
-- Every move logs what it wrote and verifies the game redrew both widgets and that nothing else in the loadout changed;
-- bytes the game does not consume within a second are put back.
local mod=hd2.mod()
local BUILD='0.1.0 NATIVE HIGHLIGHT'
mod:log('SlotHighlightProof '..BUILD..' BUILD: F7 / F8 move the native loadout slot highlight to the next / previous '
    ..'slot; Ctrl+F7 / Ctrl+F8 also move the edited slot (selector open). F9 status. Aboard the ship only; solo; no '
    ..'mission. No custom stratagem, no loadout record write.')

local focus=require('hd2runtime/runtime/stratagem_slot_focus')
local selector=require('hd2runtime/runtime/stratagem_selector')
local world_module=require('hd2runtime/runtime/event_world')

local function current()
    local world=world_module.open()
    local view=world and selector.screen(world)
    local st=view and view.open and focus.read(world,view)
    return world,view,st
end
local function report(handle)
    if handle.status=='moved'then
        mod:log(('MOVED: highlight slot %d -> slot %d%s; redrawn by the game and verified: %s; every other loadout field '
            ..'unchanged: %s'):format(handle.from,handle.to,handle.edited and' (with the edited slot)'or'',
            tostring(handle.all),tostring(handle.others)))
    elseif handle.status=='reverted'then
        mod:log(('NOT MOVED: the game did not redraw the widgets within a second; put back (%s)'):format(
            handle.undo and handle.undo.status or'nothing'))
    else
        mod:log(('REFUSED (nothing written): %s: %s'):format(tostring(handle.code),tostring(handle.reason)))
    end
end
local function step(delta,edited,key)
    local _,view,st=current()
    if not st then mod:log(key..': the loadout screen is not open');return end
    local target=st.focus+delta
    mod:log(('%s: moving the native highlight from slot %d to slot %d%s'):format(key,st.focus,target,
        edited and' with the edited slot'or''))
    focus.move(target,report,{edited=edited})
end
hd2.input.bind('slot_highlight_proof.next',{key='F7',on_press=function()step(1,false,'F7')end})
hd2.input.bind('slot_highlight_proof.next_edited',{key='Ctrl+F7',on_press=function()step(1,true,'Ctrl+F7')end})
hd2.input.bind('slot_highlight_proof.previous',{key='F8',on_press=function()step(-1,false,'F8')end})
hd2.input.bind('slot_highlight_proof.previous_edited',{key='Ctrl+F8',on_press=function()step(-1,true,'Ctrl+F8')end})
hd2.input.bind('slot_highlight_proof.status',{key='F9',on_press=function()
    local world,view=current()
    mod:log('F9 ['..BUILD..']: '..(view and view.open and focus.describe(world,view)or'the loadout screen is not open'))
end})
mod:log('loaded ('..BUILD..'): F7 next, Ctrl+F7 next with the edited slot, F8 previous, Ctrl+F8 previous with the '
    ..'edited slot, F9 status.')
