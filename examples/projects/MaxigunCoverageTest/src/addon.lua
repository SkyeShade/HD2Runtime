local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the M-1000 Maxigun recoil multipliers (research/equipment-coverage-F5FEE03DCFDB.json): the first pair of
-- the typed RecoilModifiers struct (WeaponData +60/+64), 1.0 on 364 of 366 weapons and never patched by attachments.
-- Maxigun Reimagined edits these as "internal recoil multipliers" (a research lead only). Copied when the weapon is
-- built: call in a fresh Maxigun after APPLY.
local maxigun=hd2.support_weapon('M-1000 Maxigun')
local options=hd2.options({id='maxigun_coverage_test',title='Maxigun Coverage Test'})
local climb=options:toggle({id='heavy_climb',label='Heavy climb',default=true,
    description='Vertical recoil multiplier 1 -> 5: the muzzle climbs far harder.'})
local steady=options:toggle({id='no_side_kick',label='No sideways kick',default=true,
    description='Horizontal recoil multiplier 1 -> 0.'})
return {
    hd2.ensure({enabled=climb,patch={id='maxigun-vertical-recoil',target=maxigun,allow_unverified_effect=true,
        field=hd2.fields.weapon.recoil_multiplier_vertical,expect=1,value=5}}),
    hd2.ensure({enabled=steady,patch={id='maxigun-horizontal-recoil',target=maxigun,allow_unverified_effect=true,
        field=hd2.fields.weapon.recoil_multiplier_horizontal,expect=1,value=0}}),
}
