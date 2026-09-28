local hd2=require('mods/skyeshade/hd2runtime')
-- Both values live on the stim status effect Experimental Infusion applies.
local stim=hd2.booster('Experimental Infusion'):status_effect()
return hd2.ensure({transaction={id='combat-stim-boost',target=stim,
    allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.status.strength,expect=1.1,value=1.2},
        {field=hd2.fields.status.incoming_damage_scale,expect=0.9,value=0.8},
}}})
