local hd2=require('mods/skyeshade/hd2runtime')
-- The M-1000 Maxigun owns no magazine: its ammunition is stored in its backpack's DepositComponent.
-- Doubles the backpack's capacity, starting ammunition and ammunition from supply (1000/1000/500).
local backpack=hd2.support_weapon('M-1000 Maxigun'):backpack()
return hd2.ensure({transaction={id='maxigun-backpack-ammo',target=backpack,allow_unverified_effect=true,changes={
    {field=hd2.fields.deposit.capacity,expect=1000,value=2000},
    {field=hd2.fields.deposit.start_amount,expect=1000,value=2000},
    {field=hd2.fields.deposit.refill_amount,expect=500,value=1000}}}})
