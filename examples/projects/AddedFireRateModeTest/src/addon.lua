local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: an AR-23 Liberator with three selectable rates of fire, like the MG-206's native selector.
-- The Liberator stores one rate (640 rpm) in the middle of its three rate slots (Y); the other two (X and Z) are empty
-- (0.0), and its left weapon-function input is unbound. One transaction fills the two empty slots and binds the game's
-- own rate-of-fire selector to that input, the same WeaponFunctionType the Tenderizer and the machine guns use. No
-- array grows: the slots already exist in the Liberator's own record.
-- hd2.fields.fire_rate.modes lists the slots in the order the weapon menu shows them, {X, Y, Z}: here
-- 450 / 700 / 950 from top to bottom. A built Liberator starts on the middle one (Y, 700) and the selector moves
-- Y -> Z -> X: 700 -> 950 -> 450 -> 700.
-- Equipping the Recoil Spring (internal attachment) overwrites all three slots when the weapon is built; test with
-- the default internal attachment. Rates and binding are copied into a Liberator when the game builds it.
local liberator=hd2.weapon('AR-23 Liberator')
local rates=liberator:fire_rate_modes()
assert(rates.state=='addable'and rates.binding,'the Liberator can no longer take a rate-of-fire selector')
local options=hd2.options({id='added_fire_rate_mode',title='Liberator Fire Rates'})
local enabled=options:toggle({id='enabled',label='Enabled',default=true,
    description='Off restores the single 640 rpm rate and removes the selector.'})
local top=options:slider({id='slot_x',label='Top of the menu, slot X',min=100,max=1500,step=10,default=450,
    description='Reached from the default with two presses of the new rate-of-fire selector.'})
local middle=options:slider({id='slot_y',label='Middle, slot Y: the default',min=100,max=1500,step=10,default=700,
    description='The rate a freshly built Liberator starts on (vanilla 640).'})
local bottom=options:slider({id='slot_z',label='Bottom, slot Z',min=100,max=1500,step=10,default=950,
    description='Reached from the default with one press of the new rate-of-fire selector.'})
-- The Liberator's added selector (these rates and the rate_of_fire binding) is live-proven: no acknowledgement needed.
return hd2.ensure({enabled=enabled,transaction={id='liberator-fire-rates',target=liberator,changes={
        {field=hd2.fields.fire_rate.modes,expect=rates.expect,value={top,middle,bottom}},
        {field=rates.binding.field,expect=rates.binding.expect,value=rates.binding.value}}}})
