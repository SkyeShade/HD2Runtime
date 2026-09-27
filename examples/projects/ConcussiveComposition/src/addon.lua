local hd2=require('mods/skyeshade/hd2runtime')

local projectile=hd2.weapon('AR-23C Liberator Concussive')
    :attack('primary'):projectile()
local impact=projectile:terminal_action('impact')
local expiry=projectile:terminal_action('expiry')
local eruptor=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile()
    :terminal_action('impact'):explosion()

return hd2.ensure({
    plan={
        id='concussive-composition',
        operations={
            {id='damage',target=projectile,allow_shared=true,changes={
                {field=hd2.fields.damage.ap_direct,expect=2,value=3},
                {field=hd2.fields.damage.ap_slight,expect=2,value=3},
                {field=hd2.fields.damage.ap_large,expect=2,value=3},
                {field=hd2.fields.damage.ap_extreme,expect=2,value=3},
                {field=hd2.fields.damage.push_force,expect=60,value=30},
            }},
            {id='impact',target=impact,allow_shared=true,
                field=hd2.fields.terminal.explosion,
                expect=impact:no_explosion(),value=eruptor},
            {id='expiry',target=expiry,allow_shared=true,
                field=hd2.fields.terminal.explosion,
                expect=expiry:no_explosion(),value=eruptor},
        },
    },
})
