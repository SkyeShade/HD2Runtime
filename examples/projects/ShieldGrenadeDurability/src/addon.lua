local hd2=require('mods/skyeshade/hd2runtime')
-- G/SH-39 Shield: the thrown device owns its ShieldComponent, so health and radius are one
-- throwable-local transaction.
return hd2.ensure({transaction={id='shield-grenade',target=hd2.throwable('G/SH-39 Shield'):shield(),
    allow_unverified_effect=true,changes={
        {field=hd2.fields.shield.entity_durability,expect=1000,value=2000},
        {field=hd2.fields.shield.entity_radius,expect=1.8,value=2.5}}}})
