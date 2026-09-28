local hd2=require('mods/skyeshade/hd2runtime')
local jump=hd2.backpack('LIFT-850 Jump Pack')
return hd2.ensure({plan={id='jump-pack-recreation',operations={
 {id='recharge',target=jump,field=hd2.fields.recharge.time,expect=15,value=8},
 {id='launch',target=jump,field=hd2.fields.jump.vertical_launch_velocity,expect=40,value=50},
}}})
