local hd2=require('mods/skyeshade/hd2runtime')
-- A/MG-43 Machine Gun Sentry: targeting range 75 m -> 25 m.
-- SensorEyeComponent +0 equals the wiki-stated targeting range of seven sentries; the gameplay effect is not yet
-- live-confirmed, so allow_unverified_effect is required.
local targeting=hd2.stratagem('A/MG-43 Machine Gun Sentry'):deployed_entity():targeting()
return hd2.ensure({patch={id='sentry-detection-range',target=targeting,allow_unverified_effect=true,
    field=hd2.fields.targeting.range,expect=75,value=25}})
