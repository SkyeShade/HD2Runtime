local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the LIFT-182 Warp Pack (research/equipment-coverage-F5FEE03DCFDB.json). Every field is an exact
-- published Warp Pack value at a typed DisplacementComponent member: warp distance 10 m, heat 33 % per warp (safe
-- below 15 %), and the damage an unsafe warp deals to one limb (head 10, arms 35, legs 45; the chest sets you on
-- fire). The values are copied into a Warp Pack when it spawns: call in a fresh one after APPLY.
local warp=hd2.backpack('LIFT-182 Warp Pack')
local options=hd2.options({id='warp_pack_test',title='Warp Pack Test'})
local far=options:toggle({id='long_warp',label='Long warp',default=true,description='Warp 25 m instead of 10 m.'})
local cool=options:toggle({id='cool_pack',label='Cool pack',default=true,
    description='10 % heat per warp instead of 33 %: two safe warps back to back instead of one.'})
local harmless=options:toggle({id='no_limb_damage',label='No limb damage',default=false,
    description='Unsafe warps deal 0 damage to the head, arms and legs (the chest can still set you on fire).'})
return {
    hd2.ensure({enabled=far,patch={id='warp-distance',target=warp,allow_unverified_effect=true,
        field=hd2.fields.warp.distance,expect=10,value=25}}),
    hd2.ensure({enabled=cool,patch={id='warp-heat',target=warp,allow_unverified_effect=true,
        field=hd2.fields.warp.heat_per_use,expect=33,value=10}}),
    hd2.ensure({enabled=harmless,transaction={id='warp-injury',target=warp,allow_unverified_effect=true,changes={
        {field=hd2.fields.warp.head_injury_damage,expect=10,value=0},
        {field=hd2.fields.warp.left_arm_injury_damage,expect=35,value=0},
        {field=hd2.fields.warp.right_arm_injury_damage,expect=35,value=0},
        {field=hd2.fields.warp.left_leg_injury_damage,expect=45,value=0},
        {field=hd2.fields.warp.right_leg_injury_damage,expect=45,value=0}}}}),
}
