local hd2=require('mods/skyeshade/hd2runtime')
-- The M-1000 Maxigun owns no magazine: its ammunition is stored in its backpack's DepositComponent.
-- Raises the backpack to the game's limit and doubles the ammunition from supply (1000/1000/500 -> 1023/1023/1000).
-- 1023 is a hard limit: the live amount is a 10-bit network field the game clamps on every write
-- (docs/backpack-ammo.md), so Runtime refuses larger values.
local backpack=hd2.support_weapon('M-1000 Maxigun'):backpack()
return hd2.ensure({transaction={id='maxigun-backpack-ammo',target=backpack,allow_unverified_effect=true,changes={
    {field=hd2.fields.deposit.capacity,expect=1000,value=1023},
    {field=hd2.fields.deposit.start_amount,expect=1000,value=1023},
    {field=hd2.fields.deposit.refill_amount,expect=500,value=1000}}}})
