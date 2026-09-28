local hd2=require('mods/skyeshade/hd2runtime')
-- Each tuning() field is the booster's own row in game.dll's native Booster definition table;
-- granted_stratagem() is the one-shot EAT stratagem Surplus EAT Allocation grants.
return hd2.ensure({plan={id='booster-tuning',operations={
    {id='vitality',target=hd2.booster('Vitality Enhancement'):tuning(),allow_unverified_effect=true,
        field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=0.75},
    {id='extraction',target=hd2.booster('Expert Extraction Pilot'):tuning(),allow_unverified_effect=true,
        field=hd2.fields.booster.extraction_time_scale,expect=0.7,value=0.5},
    {id='scanner',target=hd2.booster('Sample Scanner'):tuning(),allow_unverified_effect=true,
        field=hd2.fields.booster.double_sample_chance,expect=0.15,value=0.3},
    {id='eat-uses',target=hd2.booster('Surplus EAT Allocation'):granted_stratagem(),allow_unverified_effect=true,
        field=hd2.fields.stratagem.max_uses,expect=2,value=4},
}}})
