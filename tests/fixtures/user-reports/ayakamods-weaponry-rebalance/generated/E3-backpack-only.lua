local hd2=require('mods/skyeshade/hd2runtime')

return hd2.ensure({
    transaction={
        id='entity-2f5a386db841be55d3be8e66',
        target=hd2.support_weapon('M-1000 Maxigun'):backpack(),
        allow_unverified_effect=true,
        changes={
            {field=hd2.fields.deposit.capacity,expect=1000,value=1500},
            {field=hd2.fields.deposit.refill_amount,expect=500,value=750},
        },
    }
})
