-- Generated from custom_stratagems.json by the HD2Runtime SDK (hd2.py custom-stratagem compile; format hd2runtime-custom-stratagems/1).
-- Edit custom_stratagems.json, not this file: the build compiles it again. Source SHA-256 2da18db89efbcaee1b1df2a7a0ba532e537286c2f50a25883cd992ebaf0ee3cd.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('EAT77ExpendableCluster 0.3.0 BUILD: select EAT-77 Expendable Cluster in the custom panel, then a mission; call it with DOWN DOWN LEFT DOWN LEFT.')
hd2.custom_stratagem.register({
    id='eat_cluster',
    name='EAT-77 EXPENDABLE CLUSTER',
    name_cased='EAT-77 Expendable Cluster',
    description='A single-use weapon that comes down in pairs. Explodes into a cluster of lesser explosions upon impact.',
    icon=hd2.resources.image('eat_cluster'),
    code={'down','down','left','down','left'},
    cooldown=70,
    traits={'Support Weapon','Medium Armor Penetrating','Anti-Tank','Expendable'},
    carrier={group='expendable'},
    delivery={family='expendable',weapon='EAT-17 Expendable Anti-Tank',round='RL-77 Airburst Rocket Launcher',pod={{item='clone',count=2}}},
})
