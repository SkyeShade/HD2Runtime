-- Generated from custom_stratagems.json by the HD2Runtime SDK (hd2.py custom-stratagem compile; format hd2runtime-custom-stratagems/1).
-- Edit custom_stratagems.json, not this file: the build compiles it again. Source SHA-256 2ccb0f6f7abfe82ba64a4ef12f2fb9f739c1f8cefb19e018288636ee4500edfe.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('EAT23ExpendableEMS 0.1.0 BUILD: select EAT-23 Expendable EMS in the custom panel, then a mission; call it with DOWN DOWN LEFT RIGHT RIGHT.')
hd2.custom_stratagem.register({
    id='eat23_ems',
    name='EAT-23 EXPENDABLE EMS',
    name_cased='EAT-23 Expendable EMS',
    description='A single-use "compliance weapon" that comes down in pairs and modifies enemy behaviour. The EMS warhead stuns targets within the impact radius.',
    icon=hd2.resources.image('eat23_ems'),
    code={'down','down','left','right','right'},
    cooldown=70,
    traits={'Support Weapon','Anti-Tank','Stun','Expendable'},
    carrier={group='expendable'},
    delivery={family='expendable',weapon='EAT-17 Expendable Anti-Tank',modify={impact_explosion='Orbital EMS Strike'},pod={{item='clone',count=2}}},
})
