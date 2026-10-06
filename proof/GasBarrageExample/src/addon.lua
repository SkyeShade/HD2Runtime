-- Generated from custom_stratagems.json by the HD2Runtime SDK (hd2.py custom-stratagem compile; format hd2runtime-custom-stratagems/1).
-- Edit custom_stratagems.json, not this file: the build compiles it again. Source SHA-256 74eb58cf8f1d5c330f5056358f3f5390b5c78ab4294c54bcab484954db69f883.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('OrbitalGasBarrage 0.2.0 BUILD: select Orbital Gas Barrage in the custom panel, then a mission; call it with RIGHT RIGHT DOWN LEFT DOWN LEFT.')
hd2.custom_stratagem.register({
    id='orbital_gas_barrage',
    name='ORBITAL GAS BARRAGE',
    name_cased='Orbital Gas Barrage',
    description='A prolonged caustic barrage, spreading corrosive gas over a large area. Causes confusion and blindness on those affected. Breathing it in is not advised.',
    icon=hd2.resources.image('orbital_gas_barrage'),
    code={'right','right','down','left','down','left'},
    cooldown=60,
    traits={'Orbital','Anti-Tank','Caustic'},
    carrier={beacon='offensive',prefer_families={'orbital'}},
    orbital={native=true,pattern='Orbital 120mm HE Barrage',impact_explosion='Orbital Gas Strike'},
})
