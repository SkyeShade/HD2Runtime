-- Generated from custom_stratagems.json by the HD2Runtime SDK (hd2.py custom-stratagem compile; format hd2runtime-custom-stratagems/1).
-- Edit custom_stratagems.json, not this file: the build compiles it again. Source SHA-256 7f297cd05a4f18bf9cfee543dd6c055f52d71a5e4f4cafd6cbb2d62d3802eafd.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('PelicanEmsSupport 0.3.0 BUILD: select Pelican EMS Support in the custom panel, then a mission; call it with LEFT DOWN LEFT RIGHT LEFT DOWN.')
hd2.custom_stratagem.register({
    id='pelican_ems_support',
    name='PELICAN EMS SUPPORT',
    name_cased='Pelican EMS Support',
    description='Calls down a Pelican for close air support. Hovers around the beacon for 90 seconds and assists Helldivers with EMS shells to modify enemy behaviour. Stunning enemies around the impact of each shell.',
    icon=hd2.resources.image('pelican_ems_support'),
    code={'left','down','left','right','left','down'},
    cooldown=300,
    uses=4,
    traits={'Pelican','Stun'},
    carrier={beacon='offensive',prefer_families={'orbital'}},
    pelican={hover=90,orbit={radius=40,altitude=60,duration=85},gun={behave_as='gatling_sentry',rpm=30,round='native',casing='own',spread=15,recoil=false,unlimited_ammo=true,face_target=true,sound='sentry/ems_mortar',impact_explosion='EMS mortar field',aim_height=0.7}},
})
