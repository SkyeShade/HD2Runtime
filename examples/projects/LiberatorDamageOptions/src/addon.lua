local hd2=require('mods/skyeshade/hd2runtime')
-- Two rows on the MODS tab (Mod Options Menu): a toggle and a damage slider. Changes take
-- effect when the player presses APPLY; the one ensure below follows them live.
local options=hd2.options({id='liberator_damage',title='Liberator Damage'})
local enabled=options:toggle({id='enabled',label='Enabled',default=true,
    description='Off restores the game\'s own Liberator damage.'})
local damage=options:slider({id='damage',label='AR-23 Liberator Damage',min=90,max=500,step=10,default=150,
    description='Standard damage per bullet. Shared with the AR-23A Liberator Carbine and StA-52.'})
return hd2.ensure({enabled=enabled,patch={id='liberator-damage',allow_shared=true,
    target=hd2.weapon('AR-23 Liberator'):attack('primary'):projectile(),
    field=hd2.fields.damage.player_standard_damage,expect=90,value=damage}})
