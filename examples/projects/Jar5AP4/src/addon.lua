local hd2=require('mods/skyeshade/hd2runtime')
-- JAR-5 Dominator armor penetration 3 -> 4 at the direct, slight and large impact angles.
-- Damage belongs to the projectile the weapon fires: weapon -> attack('primary') -> projectile().
-- These are the same three values the original fixed JAR-5 patch changed (gameplay-proven), written
-- through the typed API. AP extreme stays 0. Baselines come from the SDK
-- (PlayerWeaponAuthoringCapabilities.json); do not reuse them for another weapon.
-- One DamageInfo record, so one transaction. It may be referenced by other projectiles
-- (allow_shared=true is required).
local projectile=hd2.weapon('JAR-5 Dominator'):attack('primary'):projectile()
return hd2.ensure({transaction={id='jar5-ap4',target=projectile,allow_shared=true,changes={
    {field=hd2.fields.damage.ap_direct,expect=3,value=4},
    {field=hd2.fields.damage.ap_slight,expect=3,value=4},
    {field=hd2.fields.damage.ap_large,expect=3,value=4},
}}})
