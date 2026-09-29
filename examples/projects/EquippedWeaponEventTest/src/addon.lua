local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for player:equipped_weapon() and the weapon events (docs/events.md#weapons). Every change of what your
-- avatar holds is logged: weapon_unequipped, weapon_equipped and weapon_changed, with the catalogued name, the slot
-- (primary and secondary are proven; support, held_item and unknown are inferred) and the game's raw selection.
-- F7 logs what you hold right now.
--
-- What to check: switching primary <-> secondary, taking out the support weapon, a grenade or a stratagem ball,
-- picking up and dropping a carried item, dying and reinforcing. Report any log line whose name or slot is wrong.
assert(hd2.events and hd2.input,'EquippedWeaponEventTest needs an HD2Runtime build with the weapon events')
local mod=hd2.mod()

local function describe(weapon)
    if not weapon then return'nothing'end
    return tostring(weapon.name or('uncatalogued '..weapon.type))..' [slot '..tostring(weapon.slot)
        ..(weapon.slot_proven and''or' (inferred)')..', selection '..tostring(weapon.selection)..', entity '
        ..tostring(weapon.entity_id)..']'
end
hd2.events.on('weapon_unequipped',function(event)
    mod:log('unequipped '..describe(event.weapon)..' ('..event.reason..')')
end,{id='unequipped'})
hd2.events.on('weapon_equipped',function(event)mod:log('equipped '..describe(event.weapon))end,{id='equipped'})
hd2.events.on('weapon_changed',function(event)
    mod:log('changed '..describe(event.previous)..' -> '..describe(event.current))
end,{id='changed'})
hd2.input.bind('equipped_weapon_event_test.show',{key='F7',on_press=function()
    local me=hd2.local_player()
    if not me then mod:log('F7: no local player');return end
    local weapon,why=me:equipped_weapon()
    mod:log('F7: in hand: '..(weapon and describe(weapon)or('nothing ('..tostring(why)..')')))
end})

mod:log('loaded: switch weapons in a mission; press F7 to log what you hold')
