local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the LIFT-860 Hover Pack (research/equipment-coverage-F5FEE03DCFDB.json). Hover duration: the six
-- published seconds, a member only the Hover Pack sets (both jump packs hold -1). The launch uses the jump-pack
-- vertical launch member (gameplay-proven on the LIFT-850); whether the Hover Pack reads it is what this tests.
-- Recharge is the already-authored recharge time. Copied when the pack spawns: call in a fresh one after APPLY.
local pack=hd2.backpack('LIFT-860 Hover Pack')
local options=hd2.options({id='hover_pack_test',title='Hover Pack Test'})
local long=options:toggle({id='long_hover',label='Long hover',default=true,
    description='Hover for 20 s instead of 6 s.'})
local high=options:toggle({id='high_launch',label='High launch',default=false,
    description='Vertical launch velocity 40 -> 80 (a much higher take-off).'})
local quick=options:toggle({id='quick_recharge',label='Quick recharge',default=false,
    description='Recharge 11.5 s -> 3 s.'})
return {
    hd2.ensure({enabled=long,patch={id='hover-duration',target=pack,allow_unverified_effect=true,
        field=hd2.fields.hover.duration,expect=6,value=20}}),
    hd2.ensure({enabled=high,patch={id='hover-launch',target=pack,allow_unverified_effect=true,
        field=hd2.fields.jump.vertical_launch_velocity,expect=40,value=80}}),
    hd2.ensure({enabled=quick,patch={id='hover-recharge',target=pack,
        field=hd2.fields.recharge.time,expect=11.5,value=3}}),
}
