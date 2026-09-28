local hd2=require('mods/skyeshade/hd2runtime')
-- The turret is attached to resupply pods by a native entity delta while the booster is active.
local turret=hd2.booster('Armed Resupply Pods'):deployed_entity()
return hd2.ensure({plan={id='armed-resupply-turret',operations={
    {id='rate',target=turret,allow_unverified_effect=true,
        field=hd2.fields.weapon.fire_rate,expect=640,value=900},
    {id='magazine',target=turret,allow_unverified_effect=true,
        field=hd2.fields.magazine.capacity,expect=140,value=300},
}}})
