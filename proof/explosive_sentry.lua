-- Generated proof package; intentionally not loaded by the runtime launcher.
local hd2=require('mods/skyeshade/hd2runtime')
local strat=hd2.stratagem('A/AC-8 Autocannon Sentry')
local weapon=strat:deployed_entity():weapon('primary')
return hd2.plan({id='explosive-sentry-proof',operations={
    {id='cooldown',target=strat,field=hd2.fields.stratagem.definition_cooldown,
        expect=150,value=300},
    {id='radius',target=weapon:attack('primary_impact'):explosion(),
        field=hd2.fields.explosion.outer_radius,expect=6,value=8,allow_shared=true},
    {id='damage',target=weapon:attack('primary_impact_damage'):damage(),
        field=hd2.fields.explosion.damage_standard_damage,expect=150,value=220,allow_shared=true},
}})
