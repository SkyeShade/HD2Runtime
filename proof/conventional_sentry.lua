-- Generated proof package; intentionally not loaded by the runtime launcher.
local hd2=require('mods/skyeshade/hd2runtime')
local strat=hd2.stratagem('A/MG-43 Machine Gun Sentry')
local entity=strat:deployed_entity()
local weapon=entity:weapon('primary')
return hd2.plan({id='conventional-sentry-proof',operations={
    {id='cooldown',target=strat,field=hd2.fields.stratagem.definition_cooldown,
        expect=90,value=180},
    {id='ammo',target=weapon,field=hd2.fields.weapon.capacity,expect=175,value=350},
    {id='fire-rate',target=weapon,field=hd2.fields.weapon.fire_rate,expect=630,value=900},
    {id='damage',target=weapon:attack('primary_damage'):damage(),
        field=hd2.fields.damage.standard_damage,expect=90,value=120,allow_shared=true},
}})
