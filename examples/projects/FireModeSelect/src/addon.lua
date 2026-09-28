local hd2=require('mods/skyeshade/hd2runtime')
-- AR-23C Liberator Concussive: its native fire modes are Automatic, Single, and the first is the
-- default. Reordering them makes Single the default; both stay selectable in game.
-- The mode set is weapon-local. Changing it requires allow_unverified_effect=true.
return hd2.ensure({patch={id='concussive-semi-auto',target=hd2.weapon('AR-23C Liberator Concussive'),
    field=hd2.fields.fire_mode.modes,expect={'automatic','single'},value={'single','automatic'},
    allow_unverified_effect=true}})
