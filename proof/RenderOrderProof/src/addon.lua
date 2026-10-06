local hd2=require('mods/skyeshade/hd2runtime')
-- RenderOrderProof 0.1.0: can a Runtime GUI appear above the native (Noesis) loadout UI? (docs/custom-stratagems.md,
-- "Render order"). Development only; aboard the ship, no mission, no selection, no custom stratagem: it only draws and
-- writes nothing to the game.
--
-- While a stratagem grid is open and still, runtime/render_probe.lua draws over four native stratagem cards and in an
-- empty area right of the loadout panels (labelled "RENDER ORDER PROBE: outside the native UI"):
--   * N0: TEST RECTANGLE (red, white edge, layers 998-999);
--   * N1: one horizontal strip per GUI layer, bottom to top 0 (red), 21 (orange), 100 (yellow), 900 (green), 990 (cyan);
--     F8 adds 2000 (blue) and 10000 (purple), whose render-side handling is unproven;
--   * N2: four GUIs created in the order A, B, C, D: A magenta then B cyan (top half), C cyan then D magenta (bottom
--     half), all at layer 500 - whichever colour is on top in the overlap shows which GUI draws later;
--   * N3: a white rectangle in an immediate GUI, drawn again every frame.
-- F6: the OVERLAY WORLD test - a script world rendered through the render config's 'overlay' viewport from the engine's
-- Lua render callback, with a green rectangle over N0's lower half and outside; released after 30 s, on F6, or when the
-- grid moves or closes. F9: status. Closing the grid removes everything.
local mod=hd2.mod()
local BUILD='0.1.0 RENDER-ORDER'
mod:log('RenderOrderProof '..BUILD..' BUILD: draws only, writes nothing. Open a stratagem grid and hold still: '
    ..'TEST RECTANGLE, layer strips, GUI order and an immediate GUI over native cards and outside the native UI. '
    ..'F8: layers 2000/10000; F6: overlay world; F9: status.')

local probe=require('hd2runtime/runtime/render_probe')
local C=probe.controller()

hd2.input.bind('render_order_proof.extended',{key='F8',on_press=function()
    mod:log('F8: '..C.toggle_extended())
end})
hd2.input.bind('render_order_proof.overlay',{key='F6',on_press=function()
    mod:log('F6: '..C.toggle_overlay())
end})
hd2.input.bind('render_order_proof.status',{key='F9',on_press=function()
    mod:log('F9 ['..BUILD..']: '..C.status())
end})
mod:log('loaded ('..BUILD..'). F6 overlay world; F8 layers 2000/10000; F9 status.')
