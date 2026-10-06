-- Generated from custom_stratagems.json by the HD2Runtime SDK (hd2.py custom-stratagem compile; format hd2runtime-custom-stratagems/1).
-- Edit custom_stratagems.json, not this file: the build compiles it again. Source SHA-256 5b537418160bbf42f7122c1e4e76cfe9b13e7df792438e3c8cfe41ff147609d5.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('OrbitalEmsBarrage 0.1.0 BUILD: select Orbital EMS Barrage in the custom panel, then a mission; call it with RIGHT DOWN UP RIGHT LEFT DOWN.')
hd2.custom_stratagem.register({
    id='orbital_ems_barrage',
    name='ORBITAL EMS BARRAGE',
    name_cased='Orbital EMS Barrage',
    description='A prolonged "compliance barrage" to modify enemy behavior in a wide area. Stuns enemies in a large area.',
    icon=hd2.resources.image('orbital_ems_barrage'),
    code={'right','down','up','right','left','down'},
    cooldown=60,
    traits={'Orbital','Anti-Tank','Stun'},
    carrier={beacon='offensive',prefer_families={'orbital'}},
    orbital={native=true,pattern='Orbital 120mm HE Barrage',impact_explosion='Orbital EMS Strike'},
})
