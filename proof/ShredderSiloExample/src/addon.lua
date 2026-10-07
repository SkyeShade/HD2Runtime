-- Generated from custom_stratagems.json by the HD2Runtime SDK (hd2.py custom-stratagem compile; format hd2runtime-custom-stratagems/1).
-- Edit custom_stratagems.json, not this file: the build compiles it again. Source SHA-256 1a6fcd9b5979ab2b894dece94a23a05b0a1fc12462d66b716e660ec1b28cba44.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('ShredderSilo 0.2.0 BUILD: one MS-N223 Shredder Silo per player, one use per mission; call it with DOWN UP RIGHT UP DOWN DOWN RIGHT.')
hd2.custom_stratagem.register({
    id='shredder_silo',
    name='MS-N223 SHREDDER SILO',
    name_cased='MS-N223 Shredder Silo',
    description='A silo that fits one single, tactical nuclear missile. Possible side effects include shell shock, mutation, and/or death. A laser targetting remote is provided.',
    icon=hd2.resources.image('shredder_silo'),
    code={'down','up','right','up','down','down','right'},
    cooldown=180,
    uses=1,
    max_per_player=1,
    traits={'Support Weapon','Explosive','Anti-Tank','Expendable'},
    carrier={group='support'},
    silo={donor='MS-11 Solo Silo',blast='Cyborg Production Unit',fallback='NUX-223 Hellbomb'},
})
