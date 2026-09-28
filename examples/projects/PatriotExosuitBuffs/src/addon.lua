local hd2=require('mods/skyeshade/hd2runtime')
-- Recreates EXO-45 Patriot Buff 1.12.0 (all but the "max armor" values, which are not exposed).
local patriot=hd2.vehicle('EXO-45 Patriot Exosuit')
local missiles,hmg=patriot:weapon('left_gun'),patriot:weapon('right_gun')
local hull={}
for _,zone in ipairs(patriot:damage_zones())do
    local changes={}
    for _,field in ipairs(zone:describe().fields)do
        if field.semanticFieldId=='zone.health'then
            changes[#changes+1]={field=hd2.fields.zone.health,expect=field.currentDefault,value=8000}
        elseif field.semanticFieldId=='zone.armor'and field.currentDefault<4 then
            changes[#changes+1]={field=hd2.fields.zone.armor,expect=field.currentDefault,value=4}
        end
    end
    if #changes>0 then hull[#hull+1]={id='zone-'..zone.zone,target=zone,changes=changes}end
end
hull[#hull+1]={id='hull',target=patriot,field=hd2.fields.entity.health,expect=1800,value=8000}
return hd2.ensure({plan={id='patriot-exosuit-buffs',phases={
    {id='hull',operations=hull},
    {id='arms',operations={
        {id='missile-magazine',target=missiles,field=hd2.fields.weapon.capacity,expect=14,value=30},
        {id='missile-arm',target=missiles,changes={
            {field=hd2.fields.entity.health,expect=800,value=8000},
            {field=hd2.fields.entity.armor,expect=3,value=10},
            {field=hd2.fields.zone.health,expect=800,value=8000},
            {field=hd2.fields.zone.armor,expect=3,value=10}}},
        {id='hmg-magazine',target=hmg,field=hd2.fields.weapon.capacity,expect=1350,value=2000},
        {id='hmg-arm',target=hmg,changes={
            {field=hd2.fields.entity.health,expect=800,value=8000},
            {field=hd2.fields.entity.armor,expect=3,value=10},
            {field=hd2.fields.zone.health,expect=800,value=8000},
            {field=hd2.fields.zone.armor,expect=3,value=10}}},
        {id='hmg-rate',target=hmg,field=hd2.fields.weapon.fire_rate,expect=1200,value=600}}},
    {id='rounds',operations={
        -- The Patriot missile's DamageInfo is its own; the HMG round is shared with other machine guns.
        {id='missile-damage',target=missiles:projectile(),allow_shared=true,changes={
            {field=hd2.fields.damage.player_standard_damage,expect=1250,value=2000},
            {field=hd2.fields.damage.player_durable_damage,expect=1250,value=2000},
            {field=hd2.fields.damage.ap_large,expect=5,value=6},
            {field=hd2.fields.damage.ap_extreme,expect=0,value=3},
            {field=hd2.fields.damage.stagger,expect=40,value=50}}},
        {id='hmg-damage',target=hmg:projectile(),allow_shared=true,changes={
            {field=hd2.fields.damage.player_standard_damage,expect=90,value=500},
            {field=hd2.fields.damage.player_durable_damage,expect=23,value=150},
            {field=hd2.fields.damage.ap_direct,expect=3,value=5},
            {field=hd2.fields.damage.ap_slight,expect=3,value=5},
            {field=hd2.fields.damage.ap_large,expect=3,value=5},
            {field=hd2.fields.damage.ap_extreme,expect=1,value=5}}}}},
    {id='call-in',operations={
        {id='cooldown',target=hd2.stratagem('EXO-45 Patriot Exosuit'),
            field=hd2.fields.stratagem.definition_cooldown,expect=420,value=250}}}}}})
