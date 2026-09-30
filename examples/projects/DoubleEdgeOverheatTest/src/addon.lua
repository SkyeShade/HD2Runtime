local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the LAS-17 Double-Edge Sickle's heat levels (research/equipment-coverage-F5FEE03DCFDB.json).
-- The weapon has three heat levels (50 / 100 / 190 of its 200 heat). From each level it fires a stronger pulse and
-- applies a self-damage status to the wielder: tick 20, 40 and 100; the level-3 status also sets the wielder on
-- fire (its damage row carries Fire). Self-damage is data, not code: moving the levels moves the burning, and the
-- level-3 status can be the level-2 one (heavy pulses without catching fire). The LAS-17 is the only weapon whose
-- lock-at-maximum-heat flag is off; the third option turns it on. All of it is copied into the weapon when the game
-- builds it: call in or re-equip a fresh LAS-17 after APPLY.
local sickle=hd2.weapon('LAS-17 Double-Edge Sickle')
local options=hd2.options({id='double_edge_overheat',title='Double-Edge Overheat'})
local later=options:toggle({id='later_levels',label='Later heat levels',default=true,
    description='Heat levels at 150 / 175 / 199 instead of 50 / 100 / 190: no self-damage until 75% heat.'})
local no_fire=options:toggle({id='no_ignition',label='No self-ignition',default=true,
    description='Heat level 3 applies the level-2 self-damage status: heavy pulses, the wielder does not catch fire.'})
local lock=options:toggle({id='overheat_lock',label='Overheat lock',default=false,
    description='Lock at maximum heat, like every other laser: at 200 heat the LAS-17 stops until you reload.'})
return {
    hd2.ensure({enabled=later,transaction={id='double-edge-levels',target=sickle,allow_unverified_effect=true,
        changes={
            {field=hd2.fields.heat.level_1_threshold,expect=50,value=150},
            {field=hd2.fields.heat.level_2_threshold,expect=100,value=175},
            {field=hd2.fields.heat.level_3_threshold,expect=190,value=199}}}}),
    hd2.ensure({enabled=no_fire,patch={id='double-edge-no-ignition',target=sickle,allow_unverified_effect=true,
        field=hd2.fields.heat.level_3_self_status,expect='hotshot_laser_rifle_3',value='hotshot_laser_rifle_2'}}),
    hd2.ensure({enabled=lock,patch={id='double-edge-lock',target=sickle,allow_unverified_effect=true,
        field=hd2.fields.heat.overheat_lock,expect=false,value=true}}),
}
