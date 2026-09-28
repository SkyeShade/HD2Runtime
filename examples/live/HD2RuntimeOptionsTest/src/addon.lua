local hd2=require('mods/skyeshade/hd2runtime')
-- Live-validation mod for in-game options. One page on the MODS tab (Mod Options Menu): an
-- Enabled toggle and a Liberator Damage slider, both driving the one ensure below on APPLY.
local options=hd2.options({id='hd2runtime_options_test',title='HD2Runtime Options Test'})
local enabled=options:toggle({id='enabled',label='Enabled',default=true,
    description='Off restores the game\'s own AR-23 Liberator damage (90).'})
local damage=options:slider({id='liberator_damage',label='Liberator Damage',min=90,max=300,step=10,default=100,
    description='AR-23 Liberator standard damage per bullet (vanilla 90). Shared with the AR-23A Liberator Carbine and StA-52.'})
return hd2.ensure({enabled=enabled,patch={id='options-test-liberator-damage',allow_shared=true,
    target=hd2.weapon('AR-23 Liberator'):attack('primary'):projectile(),
    field=hd2.fields.damage.player_standard_damage,expect=90,value=damage}})
