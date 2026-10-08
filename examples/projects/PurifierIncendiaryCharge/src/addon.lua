local hd2=require('mods/skyeshade/hd2runtime')
-- PLAS-101 Purifier charged shots set what their blast hits on fire (Fire, strength 2, the AR-2 Coyote value), like
-- the first game's incendiary upgrade, without a bigger blast. The status goes into the first empty status slot of the
-- charged shot's own explosion (weapon/plas101_purifier/impact, not shared with any other weapon); uncharged shots fire
-- their own projectile and explosion and are unchanged. Two acknowledgements: only the charged levels fire this row,
-- and a status on an explosion is not live-proven yet.
local blast=hd2.weapon('PLAS-101 Purifier'):attack('primary'):projectile():terminal_action('impact'):explosion()
return hd2.ensure({plan={id='purifier-incendiary-charge',operations={
    {id='fire',target=blast,allow_unverified_effect=true,changes={
        {field=hd2.fields.explosion.damage_status_1_type,expect='none',value='fire'},
        {field=hd2.fields.explosion.damage_status_1_strength,expect=0,value=2}}},
}}})
