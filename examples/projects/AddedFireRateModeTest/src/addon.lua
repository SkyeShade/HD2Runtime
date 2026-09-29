local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: an AR-23 Liberator with three selectable rates of fire, like the AR-61 Tenderizer's native selector.
-- The Liberator stores one rate (640 rpm, native slot Y) and its other two rate slots are empty (0.0). Its left
-- weapon-function input is unbound. One transaction fills the two empty slots and binds the game's own rate-of-fire
-- selector to that input, the same WeaponFunctionType the Tenderizer and the machine guns use. No array grows: the
-- slots already exist in the Liberator's own record. The selector visits the rates in list order from the first
-- (the default): 450 -> 700 -> 950 -> 450.
-- Equipping the Recoil Spring (internal attachment) overwrites all three slots when the weapon is built; test with
-- the default internal attachment. Rates and binding are copied into a Liberator when the game builds it.
local liberator=hd2.weapon('AR-23 Liberator')
local rates=liberator:fire_rate_modes()
assert(rates.state=='addable'and rates.binding,'the Liberator can no longer take a rate-of-fire selector')
local options=hd2.options({id='added_fire_rate_mode',title='Liberator Fire Rates'})
local enabled=options:toggle({id='enabled',label='Enabled',default=true,
    description='Off restores the single 640 rpm rate and removes the selector.'})
local first=options:slider({id='mode_1',label='Rate 1: the default',min=100,max=1500,step=10,default=450,
    description='The rate a freshly built Liberator starts on.'})
local second=options:slider({id='mode_2',label='Rate 2: one press',min=100,max=1500,step=10,default=700,
    description='The rate after one press of the new rate-of-fire selector.'})
local third=options:slider({id='mode_3',label='Rate 3: two presses',min=100,max=1500,step=10,default=950,
    description='The rate after two presses of the new rate-of-fire selector.'})
return hd2.ensure({enabled=enabled,transaction={id='liberator-fire-rates',target=liberator,
    allow_unverified_effect=true,changes={
        {field=hd2.fields.fire_rate.modes,expect=rates.expect,value={first,second,third}},
        {field=rates.binding.field,expect=rates.binding.expect,value=rates.binding.value}}}})
