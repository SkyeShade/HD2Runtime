local hd2=require('mods/skyeshade/hd2runtime')
-- A/AC-8 Autocannon Sentry: the slowest-tracking sentry (20 degrees per second on both axes) made fast.
-- TurretComponent turn speeds equal the wiki detailed tables on all nine turreted sentries; the gameplay
-- effect is not yet live-confirmed, so allow_unverified_effect is required.
local turret=hd2.stratagem('A/AC-8 Autocannon Sentry'):deployed_entity():turret()
return hd2.ensure({plan={id='sentry-turn-speed',operations={
    {id='turret',target=turret,allow_unverified_effect=true,changes={
        {field=hd2.fields.turret.yaw_speed,expect=20,value=120},
        {field=hd2.fields.turret.pitch_speed,expect=20,value=90}}},
}}})
