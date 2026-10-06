local hd2=require('mods/skyeshade/hd2runtime')
-- SlotOverlayProof 0.1.0: a Runtime icon overlay over the native stratagem slot icons (docs/custom-stratagems.md, "Slot
-- icon overlays"). Development only; VISUAL ONLY: nothing is selected, converted or written, the native slot's type, icon
-- element, material and texture are only read.
--
-- A fake virtual slot identity is this proof's own table (never the selector's virtual slots, so no mission conversion
-- can see it). For every slot carrying one, runtime/stratagem_slot_overlay.lua draws the masked Orbital Gas Barrage icon,
-- coloured as the native slot colours the Orbital Precision Strike, in a screen GUI of the Ui World (the world the game
-- draws the loadout screen and the mission HUD in) above the slot icon's layer, at the icon element's own quad:
--   * aboard the ship: the four loadout slots (loadout screen);
--   * in a mission: the HUD stratagem list entry showing that loadout slot (granted entries skipped).
-- Keys: F5-F8 toggle slots 0-3; F9 the pattern virtual / native / virtual / native (again: clear all); Home the backing
-- plate under each overlay (off by default); End status.
local mod=hd2.mod()
local BUILD='0.1.0 SLOT ICON OVERLAY'
mod:log('SlotOverlayProof '..BUILD..' BUILD: F5-F8 toggle a fake virtual identity on slots 0-3 (the Gas Barrage icon '
    ..'drawn over that slot\'s native icon); F9 virtual / native / virtual / native; Home backing plate; End status. '
    ..'Visual only: nothing is selected, converted or written.')

local overlay=require('hd2runtime/runtime/stratagem_slot_overlay')
local selector=require('hd2runtime/runtime/stratagem_selector')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local world_module=require('hd2runtime/runtime/event_world')
local catalog=require('hd2runtime/domains/stratagem_authoring')

local ICON=hd2.resources.image('orbital_gas_barrage_masks')
local PRECISION=catalog.stratagems['Orbital Precision Strike'].root.id
local BACKING={255,22,24,26}

local fake={}          -- [slot] = true: this proof's fake virtual slot identities
local backing=false
local follower,colours,colours_why
local reasons={}

local function fakes_text()
    local parts={}
    for slot=0,3 do parts[#parts+1]=fake[slot]and'V'or'n'end
    return table.concat(parts,' ')
end
-- The Orbital Precision Strike's icon colours (its row's colour set), as the native loadout slot reads them.
local function colours_now(world)
    if colours then return colours end
    local proven,why=selector.prove(world)
    if not proven then colours_why=why;return nil end
    local kind=loadout.type_of(world,PRECISION)
    if not kind then colours_why='Orbital Precision Strike has no type';return nil end
    local c,cwhy=selector.icon_colours(world,kind)
    if not c then colours_why=cwhy;return nil end
    colours=c
    return c
end
-- The icon element of every slot with a fake identity: the mission HUD's while it is shown, else the loadout screen's.
local function targets(world)
    local out={}
    local in_mission=overlay.hud_entries(world)~=nil
    for slot=0,3 do
        if fake[slot]then
            local where=in_mission and'mission'or'ship'
            local icon,why
            if in_mission then icon,why=overlay.mission_icon(world,slot)else icon,why=overlay.ship_icon(world,slot)end
            if icon then
                out[#out+1]={key=where..' '..slot,icon=icon,label=where..' slot '..slot}
                reasons[slot]=nil
            elseif reasons[slot]~=why then
                reasons[slot]=why
                mod:log(('%s slot %d: no icon element: %s'):format(where,slot,tostring(why)))
            end
        end
    end
    return out
end
local function restart()
    if follower then follower.stop();follower=nil end
    local world=world_module.open()
    local c=world and colours_now(world)
    if not c then mod:log('the overlay colours are not known yet ('..tostring(colours_why)..'): drawn uncoloured')end
    follower=overlay.follow({image=ICON,colours=c,backing=backing and BACKING or nil,targets=targets})
end
local function changed(what)
    if not follower or(not colours and fakes_text()~='n n n n')then restart()end
    mod:log(('%s: fake virtual slots %s (V virtual, n native)'):format(what,fakes_text()))
end

for slot=0,3 do
    hd2.input.bind('slot_overlay_proof.slot'..slot,{key='F'..(5+slot),on_press=function()
        fake[slot]=not fake[slot]or nil
        changed(('F%d: slot %d %s'):format(5+slot,slot,fake[slot]and'VIRTUAL'or'native'))
    end})
end
hd2.input.bind('slot_overlay_proof.pattern',{key='F9',on_press=function()
    if fakes_text()=='V n V n'then fake={};changed('F9: all native')
    else fake={[0]=true,[2]=true};changed('F9: virtual / native / virtual / native')end
end})
hd2.input.bind('slot_overlay_proof.backing',{key='Home',on_press=function()
    backing=not backing
    restart()
    mod:log('Home: backing plate '..(backing and'ON'or'OFF'))
end})
hd2.input.bind('slot_overlay_proof.status',{key='End',on_press=function()
    local world=world_module.open()
    local uw,index=nil,nil
    if world then uw,index=overlay.ui_world(world)end
    mod:log(('End [%s]: fake virtual slots %s; backing %s; Ui World %s; colours %s; shown: %s'):format(BUILD,fakes_text(),
        backing and'on'or'off',uw and('worlds()['..index..']')or('not found: '..tostring(index)),
        colours and'Orbital Precision Strike\'s'or('unknown: '..tostring(colours_why)),
        follower and follower.status()or'no follower'))
end})
mod:log('loaded ('..BUILD..'): the masked Orbital Gas Barrage icon over native slot icons. F5-F8 slots 0-3; F9 pattern; '
    ..'Home backing; End status.')
