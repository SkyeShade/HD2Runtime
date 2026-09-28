local hd2=require('mods/skyeshade/hd2runtime')
-- The magazine half of Better M-103 FRV Turret 1.31: the roof gun holds 600 rounds instead of 120.
-- The reference mod's damage/penetration addend edit is not recreated (see README).
return hd2.ensure({patch={id='m103-turret-magazine',target=hd2.vehicle('M-103 Supply FRV'):mount('gun'):weapon(),
    field=hd2.fields.weapon.capacity,expect=120,value=600}})
