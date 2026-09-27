-- Generated proof package; intentionally not loaded by the runtime launcher.
local hd2=require('mods/skyeshade/hd2runtime')
local strat=hd2.stratagem('A/LAS-98 Laser Sentry')
local weapon=strat:deployed_entity():weapon('primary')
return hd2.plan({id='unusual-sentry-proof',operations={
    {id='cooldown',target=strat,field=hd2.fields.stratagem.definition_cooldown,
        expect=150,value=300},
    {id='beam',target=weapon:attack('primary'):beam(),field=hd2.fields.beam.length,
        expect=200,value=240,allow_shared=true},
    {id='heat',target=weapon,field=hd2.fields.heat.capacity,
        expect=250,value=400},
}})
