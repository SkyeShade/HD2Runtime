local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for the jump / hover movement fields (hd2.fields.jump.*, hd2.fields.hover.*, docs/backpack-authoring.md,
-- research/docs/hoverpack-components-F5FEE03DCFDB.md). Each field is a member of the pack's own JumppackComponent
-- record, read live by the flight code every frame: an APPLIED write takes effect at once, also on a pack you already
-- wear. Not yet shown in game: every write needs allow_unverified_effect.
local BANNER='JUMP HOVER 0.1.0 BUILD'
local mod=hd2.mod()
local jump=hd2.backpack('LIFT-850 Jump Pack')
local hover=hd2.backpack('LIFT-860 Hover Pack')
local options=hd2.options({id='jump_hover_test',title='Jump Hover Test'})
local dash=options:toggle({id='flat_dash',label='Jump: flat dash',default=true,
    description='Launch thrust forward share 0.4 -> 0.95: a long, low dash along your facing.'})
local long_launch=options:toggle({id='long_launch',label='Jump: long launch',default=false,
    description='Launch thrust duration 0.5 -> 2 s: a much higher jump.'})
local boost=options:toggle({id='second_boost',label='Jump: strong second boost',default=false,
    description='Sustain thrust 60 -> 120 and duration 1 -> 4 s.'})
local steer=options:toggle({id='air_steer',label='Jump: strong air control',default=false,
    description='Mid-air steering acceleration 4 -> 40.'})
local hop=options:toggle({id='big_hop',label='Jump: big take-off hop',default=false,
    description='Take-off upward impulse 2.8 -> 12 m/s.'})
local drift=options:toggle({id='hover_drift',label='Hover: fast drift, slow climb',default=true,
    description='Hover horizontal speed 3.5 -> 15 m/s, climb speed cap 10 -> 1 m/s.'})
local fuel=options:toggle({id='hover_fuel',label='Hover: frugal fuel',default=false,
    description='Hover fuel use 1 + 1.6 / 1 + 0 -> 0.1 / 0.1 s per second (hover much longer).'})
local climb=options:toggle({id='hover_climb',label='Hover: snappy climb',default=false,
    description='Hover lift (vertical acceleration at low speed) 9.8 -> 40: a fast climb, about 6 m/s.'})
mod:log(BANNER..': LIFT-850 launch / sustain / air control / take-off, LIFT-860 hover speed / fuel / climb '
    ..'(MODS page "Jump Hover Test"; APPLIED lines follow)')
return {
    hd2.ensure({enabled=dash,patch={id='jump-flat-dash',target=jump,allow_unverified_effect=true,
        field=hd2.fields.jump.launch_forward_ratio,expect=0.4,value=0.95}}),
    hd2.ensure({enabled=long_launch,patch={id='jump-long-launch',target=jump,allow_unverified_effect=true,
        field=hd2.fields.jump.launch_duration,expect=0.5,value=2}}),
    hd2.ensure({enabled=boost,transaction={id='jump-second-boost',target=jump,allow_unverified_effect=true,changes={
        {field=hd2.fields.jump.sustain_thrust,expect=60,value=120},
        {field=hd2.fields.jump.sustain_duration,expect=1,value=4}}}}),
    hd2.ensure({enabled=steer,patch={id='jump-air-steer',target=jump,allow_unverified_effect=true,
        field=hd2.fields.jump.air_control_acceleration,expect=4,value=40}}),
    hd2.ensure({enabled=hop,patch={id='jump-big-hop',target=jump,allow_unverified_effect=true,
        field=hd2.fields.jump.takeoff_speed,expect=2.8,value=12}}),
    hd2.ensure({enabled=drift,transaction={id='hover-drift',target=hover,allow_unverified_effect=true,changes={
        {field=hd2.fields.hover.max_horizontal_speed,expect=3.5,value=15},
        {field=hd2.fields.hover.max_vertical_speed,expect=10,value=1}}}}),
    hd2.ensure({enabled=fuel,transaction={id='hover-fuel',target=hover,allow_unverified_effect=true,changes={
        {field=hd2.fields.hover.fuel_rate_low_speed,expect=1.6,value=-0.9},
        {field=hd2.fields.hover.fuel_rate_high_speed,expect=0,value=-0.9}}}}),
    hd2.ensure({enabled=climb,patch={id='hover-climb',target=hover,allow_unverified_effect=true,
        field=hd2.fields.hover.vertical_acceleration_low_speed,expect=9.8,value=40}}),
}
