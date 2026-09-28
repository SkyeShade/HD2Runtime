local hd2=require('mods/skyeshade/hd2runtime')
-- Gives the JAR-5 Dominator a full-auto mode. Its native mode set is Single, Burst (the default stays
-- Single); Automatic goes into the empty third FireMode slot, selectable with the weapon's existing
-- fire-mode selector. Rate of fire stays the weapon's own (one value shared by every mode).
return hd2.ensure({patch={id='jar5-full-auto',target=hd2.weapon('JAR-5 Dominator'),
    field=hd2.fields.fire_mode.modes,expect={'single','burst'},value={'single','burst','automatic'},
    allow_unverified_effect=true}})
