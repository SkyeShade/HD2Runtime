-- Generated from custom_stratagems.json by the HD2Runtime SDK (hd2.py custom-stratagem compile; format hd2runtime-custom-stratagems/1).
-- Edit custom_stratagems.json, not this file: the build compiles it again. Source SHA-256 602c04314bf758ae38cde32f9e17d672e84ccd16e9d050171783067538cbdb09.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('PelicanCannonSupport 0.1.0 BUILD: select Pelican Cannon Support in the custom panel, then a mission; call it with LEFT DOWN LEFT UP LEFT UP.')
hd2.custom_stratagem.register({
    id='pelican_cannon_support',
    name='PELICAN CANNON SUPPORT',
    name_cased='Pelican Cannon Support',
    description='Calls down a Pelican for close air support. Hovers around the beacon for 90 seconds and bombards nearby enemies with a heavy burst autocannon.',
    icon=hd2.resources.image('pelican_cannon_support'),
    code={'left','down','left','up','left','up'},
    cooldown=300,
    uses=3,
    traits={'Pelican','Anti-Tank','Explosive'},
    carrier={beacon='offensive',prefer_families={'orbital'}},
    pelican={hover=90,orbit={radius=40,altitude=60,duration=85},gun={round='native'}},
})
