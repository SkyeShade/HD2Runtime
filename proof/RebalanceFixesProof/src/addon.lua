local hd2=require('mods/skyeshade/hd2runtime')
-- RebalanceFixesProof 0.1.0 (HD2Runtime 0.30.4, development only): live tests for three rebalance reports.
--   1. Hover Pack height: the lift (hover.vertical_acceleration_low_speed) is what makes it climb; vanilla 9.8 is just
--      under gravity (9.82), so the pack only holds height (docs/backpack-authoring.md "How high the Hover Pack
--      flies", research/docs/hover-height-F5FEE03DCFDB.md).
--   2. Wind-up: heat.firing_charge / heat.charge_gain_per_second (Sickle, Quasar, Rover, Laser Sentry) and
--      windup.wind_up_seconds / wind_down_seconds (Maxigun, Patriot minigun) (docs/player-weapon-authoring.md
--      "Wind-up", research/docs/windup-controls-F5FEE03DCFDB.md).
--   3. The CQC-20 Breaching Hammer's charge blast through the support weapon target (docs/support-weapon-api.md,
--      research/explosion-identities-F5FEE03DCFDB.json).
-- One options toggle per test (MODS tab, page "Rebalance Fixes Proof"). Every value is read live: a toggle takes effect
-- at once, also on gear already in hand. Toggles that edit the same field must not be on together (the second is
-- refused, CONFLICT, and logged).
local mod=hd2.mod()
local BUILD='0.1.0 REBALANCE FIXES'
mod:log('RebalanceFixesProof '..BUILD..' BUILD: hover climb, Sickle instant wind-up, Maxigun instant spin-up and the '
    ..'big hammer blast are on by default; everything else is off (MODS tab).')
local page=hd2.options({id='rebalance_fixes_proof',title='Rebalance Fixes Proof'})
local function report(label)
    return function(status,info)
        mod:log(label..': '..tostring(info and info.previous)..' -> '..tostring(status)
            ..(info and info.error and(': '..tostring(info.error))or''))
    end
end
local F=hd2.fields
local hover=hd2.backpack('LIFT-860 Hover Pack')
local hammer=hd2.support_weapon('CQC-20 Breaching Hammer'):attack('ability'):explosion()
local tests={
    -- 1. Hover Pack
    {id='hover_climb',label='Hover: climb higher (lift 9.8 -> 15)',default=true,target=hover,changes={
        {field=F.hover.vertical_acceleration_low_speed,expect=9.8,value=15}}},
    {id='hover_long_window',label='Hover: climb window 6 -> 10 s (with climb higher)',default=false,target=hover,
        changes={{field=F.hover.duration,expect=6,value=10}}},
    {id='hover_cap_only',label='Hover control: climb cap 10 -> 30 only (expect no change)',default=false,target=hover,
        changes={{field=F.hover.max_vertical_speed,expect=10,value=30}}},
    -- 2. Wind-up
    {id='sickle_instant',label='Sickle: no wind-up (charge 100 -> 0)',default=true,target=hd2.weapon('LAS-16 Sickle'),
        changes={{field=F.heat.firing_charge,expect=100,value=0}}},
    {id='sickle_slow',label='Sickle: 2 s wind-up (gain 200 -> 50)',default=false,target=hd2.weapon('LAS-16 Sickle'),
        changes={{field=F.heat.charge_gain_per_second,expect=200,value=50}}},
    {id='quasar_fast',label='Quasar: 1 s charge (gain 33 -> 100)',default=false,
        target=hd2.support_weapon('LAS-99 Quasar Cannon'),changes={{field=F.heat.charge_gain_per_second,expect=33,
        value=100}}},
    {id='maxigun_instant',label='Maxigun: instant spin-up (0.5 -> 0 s)',default=true,
        target=hd2.support_weapon('M-1000 Maxigun'),changes={{field=F.windup.wind_up_seconds,expect=0.5,value=0}}},
    {id='maxigun_slow',label='Maxigun: slow spin-up (0.5 -> 3 s; instant off)',default=false,
        target=hd2.support_weapon('M-1000 Maxigun'),changes={{field=F.windup.wind_up_seconds,expect=0.5,value=3}}},
    {id='maxigun_hard_stop',label='Maxigun: barrels stop at once (spin-down switch 0.5 -> 0)',default=false,
        target=hd2.support_weapon('M-1000 Maxigun'),changes={{field=F.windup.wind_down_seconds,expect=0.5,value=0}}},
    {id='patriot_instant',label='Patriot minigun: instant spin-up (1 -> 0 s)',default=false,
        target=hd2.vehicle('EXO-45 Patriot Exosuit'):weapon('right_gun'),changes={
        {field=F.windup.wind_up_seconds,expect=1,value=0}}},
    {id='rover_instant',label='Rover drone: no wind-up (charge 100 -> 0)',default=false,
        target=hd2.backpack('AX/LAS-5 Rover'):drone():weapon(),changes={{field=F.heat.firing_charge,expect=100,
        value=0}}},
    {id='laser_sentry_slow',label='Laser Sentry: 2 s wind-up (gain 200 -> 50)',default=false,
        target=hd2.stratagem('A/LAS-98 Laser Sentry'):deployed_entity():weapon('primary'),changes={
        {field=F.heat.charge_gain_per_second,expect=200,value=50}}},
    -- 3. Breaching Hammer blast
    {id='hammer_big_blast',label='Hammer: blast 2200 -> 5000 damage, radius 3 -> 6 m',default=true,target=hammer,
        allow_shared=true,changes={
        {field=F.explosion.damage_standard_damage,expect=2200,value=5000},
        {field=F.explosion.damage_durable_damage,expect=2200,value=5000},
        {field=F.explosion.outer_radius,expect=3,value=6}}},
    {id='hammer_gentle_blast',label='Hammer: blast 2200 -> 50 damage (big blast off)',default=false,target=hammer,
        allow_shared=true,changes={
        {field=F.explosion.damage_standard_damage,expect=2200,value=50},
        {field=F.explosion.damage_durable_damage,expect=2200,value=50}}},
}
for _,t in ipairs(tests)do
    local toggle=page:toggle({id=t.id,label=t.label,default=t.default})
    hd2.ensure({enabled=toggle,transaction={id='rebalance-'..t.id,target=t.target,allow_unverified_effect=true,
        allow_shared=t.allow_shared,changes=t.changes},on_status=report(t.label)})
end
