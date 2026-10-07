local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for the PLAS-45 Epoch's three explosions and the RS-422 Railgun's overcharge explosion (docs/support-weapon-
-- api.md "Charge-level shots and explosions", research/docs/charge-explosions-F5FEE03DCFDB.md). Each charge level of the
-- Epoch fires its own projectile row, chosen by the Epoch's own charge record when the trigger is released:
--   attack('primary')         partial-charge shot: released after 1 s and before 2.5 s; its explosion attack('primary_impact');
--   attack('full_charge')     full-charge and overcharged shots: released at 2.5 s or later; its explosion
--                             attack('full_charge_impact');
--   attack('overcharge_explosion')  held overcharged for 3.25 s, the Epoch is destroyed and this explosion spawns IN YOUR
--                             HANDS: vanilla it kills you (800 damage).
-- Explosion rows are read when the explosion happens: an APPLIED write changes the next explosion. A projectile row is
-- copied into the shot when it is fired: an APPLIED write changes the next shot. None of these fields is shown in game
-- yet, so every operation carries allow_unverified_effect; the rows are shared definitions, so allow_shared.
-- The full-charge explosion and the overcharge explosion share ONE damage row: "Harmless overcharge" also makes the
-- full-charge blast do 1 damage (that is part of the test).
local BANNER='EPOCH EXPLOSIONS 0.1.0 BUILD'
local mod=hd2.mod()
local epoch=hd2.support_weapon('PLAS-45 Epoch')
local rail=hd2.support_weapon('RS-422 Railgun')
local options=hd2.options({id='epoch_explosions_test',title='Epoch Explosions Test'})
local harmless=options:toggle({id='harmless_overcharge',label='Harmless overcharge (keep on)',default=true,
    description='Epoch overcharge explosion 800 -> 1 damage, no push. Shared: the full-charge blast also does 1 damage.'})
local wide=options:toggle({id='wide_overcharge',label='Wide overcharge blast',default=false,
    description='Epoch overcharge explosion radii 3 / 4 / 5 m -> 15 / 18 / 20 m. Only with Harmless overcharge on.'})
local partial=options:toggle({id='big_partial_blast',label='Big partial-charge blast',default=false,
    description='Partial-charge explosion radii 2.3 / 3 / 4 m -> 9.2 / 12 / 16 m. Shoot targets 30 m away or more.'})
local full=options:toggle({id='big_full_charge_blast',label='Big full-charge blast',default=false,
    description='Full-charge explosion radii 3 / 4 / 5 m -> 9 / 12 / 15 m. Needs Harmless overcharge OFF to see it.'})
local slow=options:toggle({id='slow_full_charge',label='Slow full-charge shot',default=false,
    description='Full-charge projectile speed 250 -> 60 m/s. Partial-charge shots keep 250 m/s.'})
local gentle=options:toggle({id='railgun_gentle_overcharge',label='Gentle Railgun overcharge (keep on)',default=true,
    description='RS-422 overcharge explosion 300 -> 1 damage, no push.'})
mod:log(BANNER..': PLAS-45 Epoch partial-charge, full-charge and overcharge explosions; RS-422 overcharge explosion '
    ..'(MODS page "Epoch Explosions Test"; APPLIED lines follow)')
return {
    hd2.ensure({enabled=harmless,transaction={id='epoch-harmless-overcharge',
        target=epoch:attack('overcharge_explosion'):explosion(),allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.explosion.damage_standard_damage,expect=800,value=1},
        {field=hd2.fields.explosion.damage_durable_damage,expect=800,value=1},
        {field=hd2.fields.explosion.damage_push_force,expect=30,value=0}}}}),
    hd2.ensure({enabled=wide,transaction={id='epoch-wide-overcharge',
        target=epoch:attack('overcharge_explosion'):explosion(),allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.explosion.inner_radius,expect=3,value=15},
        {field=hd2.fields.explosion.outer_radius,expect=4,value=18},
        {field=hd2.fields.explosion.shockwave_radius,expect=5,value=20}}}}),
    hd2.ensure({enabled=partial,transaction={id='epoch-big-partial-blast',
        target=epoch:attack('primary_impact'):explosion(),allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.explosion.inner_radius,expect=2.299999952316284,value=9.2},
        {field=hd2.fields.explosion.outer_radius,expect=3,value=12},
        {field=hd2.fields.explosion.shockwave_radius,expect=4,value=16}}}}),
    hd2.ensure({enabled=full,transaction={id='epoch-big-full-charge-blast',
        target=epoch:attack('full_charge_impact'):explosion(),allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.explosion.inner_radius,expect=3,value=9},
        {field=hd2.fields.explosion.outer_radius,expect=4,value=12},
        {field=hd2.fields.explosion.shockwave_radius,expect=5,value=15}}}}),
    hd2.ensure({enabled=slow,patch={id='epoch-slow-full-charge',target=epoch:attack('full_charge'):projectile(),
        allow_shared=true,allow_unverified_effect=true,field=hd2.fields.projectile.velocity,expect=250,value=60}}),
    hd2.ensure({enabled=gentle,transaction={id='railgun-gentle-overcharge',
        target=rail:attack('overcharge_explosion'):explosion(),allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.explosion.damage_standard_damage,expect=300,value=1},
        {field=hd2.fields.explosion.damage_durable_damage,expect=300,value=1},
        {field=hd2.fields.explosion.damage_push_force,expect=40,value=0}}}}),
}
