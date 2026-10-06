-- Generated from custom_stratagems.json by the HD2Runtime SDK (hd2.py custom-stratagem compile; format hd2runtime-custom-stratagems/1).
-- Edit custom_stratagems.json, not this file: the build compiles it again. Source SHA-256 21c2a8bb106a43332ed03c5a67b1acc093e2ca117d8761173f3789d9d656ca60.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('PelicanGatlingSupport 0.8.0 BUILD: select Pelican Gatling Support in the custom panel, then a mission; call it with LEFT DOWN LEFT LEFT UP UP.')
hd2.custom_stratagem.register({
    id='pelican_close_air_support',
    name='PELICAN GATLING SUPPORT',
    name_cased='Pelican Gatling Support',
    description='Calls down a Pelican for close air support. Hovers around the beacon for 90 seconds and bombards nearby enemies with its high fire rate machine gun.',
    icon=hd2.resources.image('pelican_close_air_support'),
    code={'left','down','left','left','up','up'},
    cooldown=300,
    uses=4,
    traits={'Pelican','Heavy Armor Penetrating'},
    carrier={beacon='offensive',prefer_families={'orbital'}},
    pelican={hover=90,orbit={radius=40,altitude=60,duration=85},gun={behave_as='gatling_sentry',rate_multiplier=1,round='ap4',spread=15,recoil=false,unlimited_ammo=true,face_target=true,sound='vehicle/bastion/hmg',aim_height=0.7}},
})
