local hd2=require('mods/skyeshade/hd2runtime')
-- Every Automaton fabricator variant: main health 1500 -> 150. The five classes share one anatomy (the wiki
-- Automaton Fabricator / Warp Gateway pages) and each owns its own health record, so changing all of them removes
-- the "which variant is this?" question. Structure health is offline-proven only: allow_unverified_effect.
local operations={}
for _,name in ipairs({'spawner_factory_conscript_base','spawner_factory_conscript_standard',
        'spawner_factory_conscript_assault','spawner_factory_conscript_airborne',
        'spawner_factory_conscript_phalanx'})do
    operations[#operations+1]={id=name,target=hd2.structure(name),allow_unverified_effect=true,changes={
        {field=hd2.fields.entity.health,expect=1500,value=150}}}
end
return hd2.ensure({plan={id='fabricator-health-all-variants',operations=operations}})
