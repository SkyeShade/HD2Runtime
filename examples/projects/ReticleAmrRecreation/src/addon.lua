local hd2=require('mods/skyeshade/hd2runtime')
-- Recreates ReticleAmr: the APW-1 shows the normal third-person aiming reticle. Native owner:
-- WeaponDataComponent.crosshair_type, CrosshairDamageIndicatorOnly (3) -> AssaultRifle (4).
return hd2.ensure({patch={id='reticle-amr',target=hd2.support_weapon('APW-1 Anti-Materiel Rifle'),
    field=hd2.fields.weapon.third_person_reticle,expect=false,value=true}})
