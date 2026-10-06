local hd2=require('mods/skyeshade/hd2runtime')
-- SlotTextureProbe 0.1.0: the native loadout slot icon's render-side texture chain, READ ONLY (docs/custom-stratagems.md,
-- "A custom texture in a native slot"; runtime/stratagem_slot_texture_probe.lua). Development only; aboard the ship.
-- Nothing is written: F9 resolves, for each of the four slots, the icon element's material clone, its render handle, the
-- render world and the render-side material object every draw reads, checks each link, and logs the texture handle the
-- slot draws with, the handle of the atlas page its sprite is on, and the handle of this proof's custom texture
-- (orbital_gas_barrage_masks, resident only to be compared).
local mod=hd2.mod()
local BUILD='0.1.0 READ ONLY'
mod:log('SlotTextureProbe '..BUILD..' BUILD: F9 reads the native slot icon texture chain and logs it. Nothing is written.')

local probe=require('hd2runtime/runtime/stratagem_slot_texture_probe')
local CUSTOM=hd2.resources.image('orbital_gas_barrage_masks')
hd2.input.bind('slot_texture_probe.run',{key='F9',on_press=function()
    local lines=probe.run(CUSTOM)
    mod:log('F9 ['..BUILD..']: '..#lines..' lines (see the slot texture probe lines)')
end})
mod:log('loaded ('..BUILD..'): open the loadout screen and press F9.')
