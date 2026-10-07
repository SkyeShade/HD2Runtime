local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for the vehicle tuning fields (docs/vehicle-weapons.md turret motion, docs/vehicle-authoring.md body
-- rotation and steering; research research/docs/vehicle-mech-components-F5FEE03DCFDB.md). Every field here needs
-- allow_unverified_effect until this test passes: sentry live evidence for the same turret ids does not apply to
-- vehicles.
--
-- When each value takes effect (native lifecycle):
-- - turret.yaw_speed / pitch_speed and the Exosuit rotation.* fields are copied into the vehicle when it is created:
--   call in a NEW vehicle after APPLY (one already in the world keeps its old values);
-- - turret.yaw_min / yaw_max / pitch_min / pitch_max are re-read every turret update: a deployed vehicle follows at once;
-- - vehicle.steering_response_speed is read every frame from the vehicle type: every live FRV of that type follows at
--   once.
--
-- One MODS-tab page (Mod Options Menu) picks every value; without the menu the defaults below apply. Every line this
-- mod logs starts with the banner.
local BANNER='VEHICLE TUNING 0.1.0 BUILD'
local mod=hd2.mod()
local F=hd2.fields
local options=hd2.options({id='vehicle_tuning_test',title='Vehicle Tuning Test'})

local m103_traverse=options:choice({id='m103_traverse',label='M-103 gun traverse (deg/s)',
    choices={'130 (vanilla)','30'},values={130,30},default=2,
    description='M-103 Supply FRV gun horizontal turn speed. Copied at call-in: call in a new FRV after APPLY.'})
local bastion_traverse=options:choice({id='bastion_traverse',label='Bastion cannon traverse (deg/s)',
    choices={'35 (vanilla)','8'},values={35,8},default=2,
    description='TD-220 Bastion cannon horizontal turn speed. Copied at call-in: call in a new Bastion after APPLY.'})
local bastion_left=options:choice({id='bastion_left_limit',label='Bastion cannon left limit (deg)',
    choices={'-20 (vanilla)','-5'},values={-20,-5},default=2,
    description='Read every turret update: a deployed Bastion follows at once.'})
local bastion_right=options:choice({id='bastion_right_limit',label='Bastion cannon right limit (deg)',
    choices={'20 (vanilla)','5'},values={20,5},default=2,
    description='Read every turret update: a deployed Bastion follows at once.'})
local bastion_elevation=options:choice({id='bastion_elevation',label='Bastion cannon highest aim (deg)',
    choices={'25 (vanilla)','45'},values={25,45},default=2,
    description='Read every turret update: a deployed Bastion follows at once.'})
local patriot_turn=options:choice({id='patriot_turn_speed',label='Patriot body turn speed (deg/s)',
    choices={'65 (vanilla)','20'},values={65,20},default=2,
    description='EXO-45 Patriot body turn rate. Copied at call-in: call in a new Exosuit after APPLY.'})
local patriot_acceleration=options:choice({id='patriot_turn_acceleration',label='Patriot turn acceleration (deg/s2)',
    choices={'0 (vanilla, instant)','30'},values={0,30},default=1,
    description='0 turns at the full rate at once. 30 ramps up over about a second. Copied at call-in.'})
local frv_steering=options:choice({id='frv_steering',label='M-102 FRV steering response (per s)',
    choices={'3.1 (vanilla)','0.5'},values={3.1,0.5},default=2,
    description='How fast the steering input follows the stick or keys. Read every frame: a live FRV follows at once.'})

local bastion=hd2.vehicle('TD-220 Bastion MK XVI'):weapon('attach_tank_gun')
local operations={
    hd2.ensure({patch={id='m103-traverse',target=hd2.vehicle('M-103 Supply FRV'):weapon('gun'),
        allow_unverified_effect=true,field=F.turret.yaw_speed,expect=130,value=m103_traverse}}),
    hd2.ensure({patch={id='bastion-traverse',target=bastion,allow_unverified_effect=true,
        field=F.turret.yaw_speed,expect=35,value=bastion_traverse}}),
    hd2.ensure({transaction={id='bastion-cannon-limits',target=bastion,allow_unverified_effect=true,changes={
        {field=F.turret.yaw_min,expect=-20,value=bastion_left},
        {field=F.turret.yaw_max,expect=20,value=bastion_right},
        {field=F.turret.pitch_max,expect=25,value=bastion_elevation}}}}),
    hd2.ensure({transaction={id='patriot-rotation',target=hd2.vehicle('EXO-45 Patriot Exosuit'),
        allow_unverified_effect=true,changes={
        {field=F.rotation.turn_speed,expect=65,value=patriot_turn},
        {field=F.rotation.acceleration,expect=0,value=patriot_acceleration}}}}),
    hd2.ensure({patch={id='frv-steering',target=hd2.vehicle('M-102 Gunner FRV'),allow_unverified_effect=true,
        field=F.vehicle.steering_response_speed,expect=3.1,value=frv_steering}}),
}

-- An option's current value (an options handle in game; the declared default where no options menu exists).
local function current(handle)return type(handle)=='table'and handle:get()or handle end
local function summary()
    return ('M-103 traverse %s; Bastion traverse %s, limits %s/%s, highest aim %s; Patriot turn %s, acceleration %s; '
        ..'FRV steering %s'):format(tostring(current(m103_traverse)),tostring(current(bastion_traverse)),
        tostring(current(bastion_left)),tostring(current(bastion_right)),tostring(current(bastion_elevation)),
        tostring(current(patriot_turn)),tostring(current(patriot_acceleration)),tostring(current(frv_steering)))
end

hd2.events.on('mission_started',function()
    mod:log(BANNER..': mission started; '..summary()..'. Call in NEW vehicles for traverse and Exosuit turn values.')
end,{id='vehicle_tuning_mission'})

mod:log(BANNER..': loaded; '..summary())
return operations
