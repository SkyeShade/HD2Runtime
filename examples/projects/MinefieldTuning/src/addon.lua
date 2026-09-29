local hd2=require('mods/skyeshade/hd2runtime')
-- MD-6 Anti-Personnel Minefield: the deployed mines' explosion (the deployer's MinefieldComponent names this
-- ExplosionSettings row; every contact mine detonates with it). Radius and damage are separate records.
local mine=hd2.stratagem('MD-6 Anti-Personnel Minefield'):mine()
return hd2.ensure({plan={id='minefield-tuning',operations={
    {id='radius',target=mine:explosion(),allow_shared=true,
        field=hd2.fields.explosion.outer_radius,expect=5,value=8},
    {id='damage',target=hd2.stratagem('MD-6 Anti-Personnel Minefield'):attack('mine_damage'):damage(),
        allow_shared=true,changes={
        {field=hd2.fields.explosion.damage_standard_damage,expect=700,value=1000},
        {field=hd2.fields.explosion.damage_durable_damage,expect=700,value=1000}}},
}}})
