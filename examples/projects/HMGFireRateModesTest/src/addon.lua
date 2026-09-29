local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the MG-206 Heavy Machine Gun's three native rates of fire, each edited on its own from the MODS tab.
-- The HMG stores its rates in three slots of its own ProjectileWeapon record (X/Y/Z = 450/600/750 rpm). A built HMG
-- starts on the Y slot, and each press of its rate-of-fire selector moves to the next slot, Y -> Z -> X -> Y.
-- hd2.fields.fire_rate.modes lists the rates in that order, so the vanilla list is {600, 750, 450}.
-- Each slider writes exactly one slot; the other slots are conflict-checked and left alone. The rates are copied into
-- an HMG when the game builds it: call in a fresh HMG (or redeploy) after changing them.
local hmg=hd2.support_weapon('MG-206 Heavy Machine Gun')
local modes=hmg:fire_rate_modes()
assert(modes.state=='selectable'and#modes.modes==3,'the MG-206 rate-of-fire selector changed')
local options=hd2.options({id='hmg_fire_rate_modes',title='HMG Fire Rate Modes'})
local enabled=options:toggle({id='enabled',label='Enabled',default=true,
    description='Off restores the vanilla 600 / 750 / 450 rpm.'})
local first=options:slider({id='mode_1',label='Mode 1: the default (vanilla 600 rpm)',min=100,max=1500,step=50,
    default=200,description='The rate a freshly built HMG starts on (native slot Y).'})
local second=options:slider({id='mode_2',label='Mode 2: one press (vanilla 750 rpm)',min=100,max=1500,step=50,
    default=700,description='The rate after one press of the rate-of-fire selector (native slot Z).'})
local third=options:slider({id='mode_3',label='Mode 3: two presses (vanilla 450 rpm)',min=100,max=1500,step=50,
    default=1400,description='The rate after two presses of the rate-of-fire selector (native slot X).'})
return hd2.ensure({enabled=enabled,patch={id='hmg-fire-rate-modes',target=hmg,field=hd2.fields.fire_rate.modes,
    expect=modes.expect,value={first,second,third},allow_unverified_effect=true}})
