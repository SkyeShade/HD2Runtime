local hd2=require('mods/skyeshade/hd2runtime')

return hd2.observe({
    targets={
        hd2.vehicle('Bastion'):health():read_target(),
        hd2.weapon('AMR'):read_target(),
    },
    on_result=function(result)return hd2.format(result)end,
})
