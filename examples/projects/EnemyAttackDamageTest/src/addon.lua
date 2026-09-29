local hd2=require('mods/skyeshade/hd2runtime')
-- Spewer bile artillery ("Bile Bombard"): direct hit 500 -> 50 and its explosion 200 -> 20.
-- The Rupture Spewer's mount slot 1 fires the projectile whose DamageInfo rows equal the wiki's Bile Bombard on all
-- nine values; the chain (mount slot -> weapon -> projectile -> DamageInfo, explosion -> DamageInfo) is re-proven
-- before the write. The rows are shared by every Spewer class (allow_shared), and the effect on enemy attacks is not
-- yet live-confirmed (allow_unverified_effect).
local spewer=hd2.enemy('Rupture Spewer')
return hd2.ensure({plan={id='enemy-attack-damage-test',operations={
    {id='shell',target=spewer:attack('Bile Bombard'),allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.damage.player_standard_damage,expect=500,value=50},
        {field=hd2.fields.damage.player_durable_damage,expect=500,value=50}}},
    {id='splash',target=spewer:attack('slot_1_impact'),allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.damage.player_standard_damage,expect=200,value=20},
        {field=hd2.fields.damage.player_durable_damage,expect=200,value=20}}},
}}})
