local hd2=require('mods/skyeshade/hd2runtime')
-- The AR-23C's round count is owned by its magazine attachment, not the weapon record.
-- Editing the attachment definition also affects any other weapon that equips it.
local drum=hd2.weapon('AR-23C Liberator Concussive'):magazine_attachment()
return hd2.ensure({patch={id='concussive-drum-magazine',target=drum,
    field=hd2.fields.attachment.magazine_capacity,expect=60,value=90,
    allow_shared=true,allow_unverified_effect=true}})
