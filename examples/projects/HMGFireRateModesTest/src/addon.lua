local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the MG-206 Heavy Machine Gun's three native rates of fire, each edited on its own from the MODS tab.
-- The HMG stores its rates in three slots of its own ProjectileWeapon record, X/Y/Z = 450/600/750 rpm, and its weapon
-- menu lists them in that order. A built HMG starts on the middle one (Y), and each press of its rate-of-fire
-- selector moves to the next filled slot: Y -> Z -> X -> Y. hd2.fields.fire_rate.modes lists the slots in menu order,
-- so the vanilla list is {450, 600, 750}; weapon:fire_rate_modes() also gives each mode's slot and selector presses.
-- Each slider writes exactly one slot; the other slots are conflict-checked and left alone. The rates are copied into
-- an HMG when the game builds it: call in a fresh HMG (or redeploy) after changing them.
local hmg=hd2.support_weapon('MG-206 Heavy Machine Gun')
local modes=hmg:fire_rate_modes()
assert(modes.state=='selectable'and#modes.modes==3,'the MG-206 rate-of-fire selector changed')
local options=hd2.options({id='hmg_fire_rate_modes',title='HMG Fire Rate Modes'})
local enabled=options:toggle({id='enabled',label='Enabled',default=true,
    description='Off restores the vanilla 450 / 600 / 750 rpm.'})
local top=options:slider({id='slot_x',label='Top of the menu, slot X (vanilla 450 rpm)',min=100,max=1500,step=50,
    default=300,description='Reached from the default with two presses of the rate-of-fire selector.'})
local middle=options:slider({id='slot_y',label='Middle, slot Y: the default (vanilla 600 rpm)',min=100,max=1500,
    step=50,default=550,description='The rate a freshly built HMG starts on.'})
local bottom=options:slider({id='slot_z',label='Bottom, slot Z (vanilla 750 rpm)',min=100,max=1500,step=50,
    default=1200,description='Reached from the default with one press of the rate-of-fire selector.'})
-- Editing the MG-206's rates is live-proven (sdk/LiveEvidenceCatalog.json): no allow_unverified_effect needed.
return hd2.ensure({enabled=enabled,patch={id='hmg-fire-rate-modes',target=hmg,field=hd2.fields.fire_rate.modes,
    expect=modes.expect,value={top,middle,bottom}}})
