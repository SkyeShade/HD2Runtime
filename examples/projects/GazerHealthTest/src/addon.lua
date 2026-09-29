local hd2=require('mods/skyeshade/hd2runtime')
-- Illuminate Gazer (named by an exact wiki anatomy match; a unique, easily recognised structure): main health
-- 900 -> 90. Its Eye zone has its own pool and forwards all its damage to main health.
-- Structure health is offline-proven only: allow_unverified_effect is required.
return hd2.ensure({patch={id='gazer-health-test',target=hd2.structure('Gazer'),allow_unverified_effect=true,
    field=hd2.fields.entity.health,expect=900,value=90}})
