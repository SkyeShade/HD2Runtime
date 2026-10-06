-- Generated from custom_stratagems.json by the HD2Runtime SDK (hd2.py custom-stratagem compile; format hd2runtime-custom-stratagems/1).
-- Edit custom_stratagems.json, not this file: the build compiles it again. Source SHA-256 c28ac99fe7e7e330de4aa3ce5686e5685aa8bc06b01cbf07db31d39092d25828.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('EAT40ExpendableGas 0.3.0 BUILD: select EAT-40 Expendable Gas in the custom panel, then a mission; call it with DOWN DOWN LEFT DOWN RIGHT.')
hd2.custom_stratagem.register({
    id='eat17g_clone',
    name='EAT-40 EXPENDABLE GAS',
    name_cased='EAT-40 Expendable Gas',
    description='A single-use weapon that comes down in pairs. Outfitted with a caustic warhead that causes confusion and blindness in those affected.',
    icon=hd2.resources.image('eat17g'),
    code={'down','down','left','down','right'},
    cooldown=70,
    traits={'Support Weapon','Anti-Tank','Caustic','Expendable'},
    carrier={group='expendable'},
    delivery={family='expendable',weapon='EAT-17 Expendable Anti-Tank',modify={impact_explosion='Orbital Gas Strike'},pod={{item='clone',count=2}}},
})
