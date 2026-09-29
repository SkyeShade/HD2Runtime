local hd2=require('mods/skyeshade/hd2runtime')
-- M-1000 Maxigun: clear its "stationary while firing" flag (WeaponDataComponent +387, set on the Maxigun
-- only). Afterwards its movement-related weapon data equals the GL-28 Belt-Fed Grenade Launcher's.
local maxigun=hd2.support_weapon('M-1000 Maxigun')
return hd2.ensure({patch={id='maxigun-mobile-firing',target=maxigun,
    field=hd2.fields.weapon.stationary_while_firing,expect=true,value=false,allow_unverified_effect=true}})
