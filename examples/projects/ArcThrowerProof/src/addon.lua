local hd2=require('mods/skyeshade/hd2runtime')
local attack=hd2.support_weapon('ARC-3 Arc Thrower'):attack('primary')

return hd2.ensure({patch={id='arc-thrower-proof',target=attack,allow_shared=true,
    field=hd2.fields.arc.range,expect=55,value=90}})
