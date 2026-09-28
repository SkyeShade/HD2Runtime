local hd2=require('mods/skyeshade/hd2runtime')
-- Damage belongs to the projectile a weapon fires, not to the weapon itself:
--   hd2.weapon(name)       weapon-local values (fire rate, spread, recoil, ...)
--     :attack('primary')   one of the weapon's attacks
--     :projectile()        the projectile it fires, which owns damage and armor penetration
--
-- Every expect is the AR-23 Liberator's reviewed baseline from sdk/PlayerWeaponAuthoringCapabilities.json
-- (standard 90, durable 22, AP 2 / 2 / 2 / 0). Other weapons have other baselines: never copy expect
-- values from another weapon; read them from the SDK, ModBuilder, or projectile:describe().
--
-- Armor penetration is four fields, one per impact angle (direct, slight, large, extreme).
-- All six fields live in one DamageInfo record, so they are one transaction (not a plan).
-- That record is shared with the AR-23A Liberator Carbine and the StA-52 Assault Rifle, which change
-- too: allow_shared=true is required.
local projectile=hd2.weapon('AR-23 Liberator'):attack('primary'):projectile()
return hd2.ensure({transaction={id='liberator-damage',target=projectile,allow_shared=true,changes={
    {field=hd2.fields.damage.player_standard_damage,expect=90,value=120},
    {field=hd2.fields.damage.player_durable_damage,expect=22,value=35},
    {field=hd2.fields.damage.ap_direct,expect=2,value=3},
    {field=hd2.fields.damage.ap_slight,expect=2,value=3},
    {field=hd2.fields.damage.ap_large,expect=2,value=3},
    {field=hd2.fields.damage.ap_extreme,expect=0,value=2},
}}})
