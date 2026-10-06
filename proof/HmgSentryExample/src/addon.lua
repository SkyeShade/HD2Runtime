-- Generated from custom_stratagems.json by the HD2Runtime SDK (hd2.py custom-stratagem compile; format hd2runtime-custom-stratagems/1).
-- Edit custom_stratagems.json, not this file: the build compiles it again. Source SHA-256 429f88ab4448b7696c9933f1c8436567f777257b0e92da08b769d0c27c1980ec.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('HeavyMgSentry 0.3.0 BUILD: select A/MG-101 Heavy MG Sentry in the custom panel, then a mission; call it with DOWN UP RIGHT RIGHT RIGHT LEFT.')
hd2.custom_stratagem.register({
    id='hmg_sentry',
    name='A/MG-101 HEAVY MG SENTRY',
    name_cased='A/MG-101 Heavy MG Sentry',
    description='An automated sentry turret firing with the prowess of an heavy machine gun. More sluggish than lighter variants. Hazardous to Helldivers in the crossfire.',
    icon=hd2.resources.image('hmg_sentry'),
    code={'down','up','right','right','right','left'},
    cooldown=150,
    traits={'Sentry','Heavy Armor Penetrating'},
    carrier={beacon='support',prefer_families={'sentry'},allow_families={'sentry'}},
    sentry={donor='A/MG-43 Machine Gun Sentry',weapon={projectile='MG-206 Heavy Machine Gun',rpm=400,spread=5,ammo=300}},
})
