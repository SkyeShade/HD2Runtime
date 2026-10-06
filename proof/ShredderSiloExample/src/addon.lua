-- Generated from custom_stratagems.json by the HD2Runtime SDK (hd2.py custom-stratagem compile; format hd2runtime-custom-stratagems/1).
-- Edit custom_stratagems.json, not this file: the build compiles it again. Source SHA-256 ae99ca8c5c70472e0e5bcbca7b249e5e6763827ac476cc27ffefac86e5aa8294.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('ShredderSilo 0.1.0 BUILD: select MS-N223 Shredder Silo in the custom panel, then a mission; call it with DOWN UP RIGHT UP DOWN DOWN RIGHT.')
hd2.custom_stratagem.register({
    id='shredder_silo',
    name='MS-N223 SHREDDER SILO',
    name_cased='MS-N223 Shredder Silo',
    description='A silo that fits one single, tactical nuclear missile. Possible side effects include shell shock, mutation, and/or death. A laser targetting remote is provided.',
    icon=hd2.resources.image('shredder_silo'),
    code={'down','up','right','up','down','down','right'},
    cooldown=180,
    traits={'Support Weapon','Explosive','Anti-Tank','Expendable'},
    carrier={group='support'},
    silo={donor='MS-11 Solo Silo',blast='Cyborg Production Unit',fallback='NUX-223 Hellbomb'},
})
