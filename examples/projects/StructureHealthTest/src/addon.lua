local hd2=require('mods/skyeshade/hd2runtime')
-- Automaton fabricator (native class spawner_factory_conscript_base) main health 1500 -> 150. The wiki name is not
-- attached: the anatomy also matches the Warp Gateway page, so the class is addressed by its native name.
-- Structure health is offline-proven only (its live test was inconclusive): allow_unverified_effect is required.
local fabricator=hd2.structure('spawner_factory_conscript_base')
return hd2.ensure({patch={id='structure-health-test',target=fabricator,allow_unverified_effect=true,
    field=hd2.fields.entity.health,expect=1500,value=150}})
