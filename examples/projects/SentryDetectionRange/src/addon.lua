local hd2=require('mods/skyeshade/hd2runtime')
-- A/MG-43 Machine Gun Sentry: targeting range 75 m -> 25 m.
-- Live-proven 2026-09-29 (sdk/LiveEvidenceCatalog.json): no acknowledgement is needed.
local targeting=hd2.stratagem('A/MG-43 Machine Gun Sentry'):deployed_entity():targeting()
return hd2.ensure({patch={id='sentry-detection-range',target=targeting,
    field=hd2.fields.targeting.range,expect=75,value=25}})
