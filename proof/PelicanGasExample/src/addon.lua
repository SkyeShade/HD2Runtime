-- Generated from custom_stratagems.json by the HD2Runtime SDK (hd2.py custom-stratagem compile; format hd2runtime-custom-stratagems/1).
-- Edit custom_stratagems.json, not this file: the build compiles it again. Source SHA-256 288152254a16c840bfbc0c250e9ac35e08d2e2a50afedaecbd523343d31c4d0c.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('PelicanGasSupport 0.3.0 BUILD: select Pelican Gas Support in the custom panel, then a mission; call it with LEFT DOWN LEFT RIGHT DOWN RIGHT.')
hd2.custom_stratagem.register({
    id='pelican_gas_support',
    name='PELICAN GAS SUPPORT',
    name_cased='Pelican Gas Support',
    description='Calls down a Pelican for close air support. Hovers around the beacon for 90 seconds and assists Helldivers with a gas bombardment, causing confusion and blindness in hit enemies.',
    icon=hd2.resources.image('pelican_gas_support'),
    code={'left','down','left','right','down','right'},
    cooldown=300,
    uses=4,
    traits={'Pelican','Caustic'},
    carrier={beacon='offensive',prefer_families={'orbital'}},
    pelican={hover=90,orbit={radius=40,altitude=60,duration=85},gun={behave_as='gatling_sentry',rpm=60,round='native',casing='own',spread=15,recoil=false,unlimited_ammo=true,face_target=true,sound='sentry/gas_mortar',impact_explosion='Gas grenade cloud',aim_height=0.7}},
})
