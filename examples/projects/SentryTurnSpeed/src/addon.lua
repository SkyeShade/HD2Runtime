local hd2=require('mods/skyeshade/hd2runtime')
-- A/AC-8 Autocannon Sentry: horizontal turn speed 20 -> 120 and vertical 20 -> 90 degrees per second.
-- Live-proven 2026-09-29 (sdk/LiveEvidenceCatalog.json): no acknowledgement is needed.
local turret=hd2.stratagem('A/AC-8 Autocannon Sentry'):deployed_entity():turret()
return hd2.ensure({plan={id='sentry-turn-speed',operations={
    {id='turret',target=turret,changes={
        {field=hd2.fields.turret.yaw_speed,expect=20,value=120},
        {field=hd2.fields.turret.pitch_speed,expect=20,value=90}}},
}}})
