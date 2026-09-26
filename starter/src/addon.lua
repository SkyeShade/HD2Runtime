local hd2=require('mods/skyeshade/hd2runtime')

return hd2.ensure({
    patch={
        id='my-hd2-mod-jar5-ap4',
        target=hd2.weapon('JAR-5 Dominator'):projectile():damage(),
        field=hd2.fields.damage.armor_penetration,
        expect=3,
        value=4,
    },
})
