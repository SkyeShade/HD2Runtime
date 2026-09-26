-- HD2-Addon: mods/skyeshade/hd2runtime_jar5_ap4
local key='HD2RuntimeJar5AP4ProofV1'
local existing=rawget(_G,key)
if existing then return existing end
local hd2=require('mods/skyeshade/hd2runtime')
local patch=hd2.patch({
    id='jar5-ap4',
    target=hd2.weapon('JAR-5 Dominator'):projectile():damage(),
    field='armor_penetration',
    expect=3,
    value=4,
})
rawset(_G,key,patch)
return patch
