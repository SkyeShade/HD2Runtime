-- HD2-Addon: mods/nephelym/nephelym_s_weaponry_rebalance
local loader=rawget(_G,'CowboyBingusModLoader')
assert(loader and loader.api==1 and type(loader.version)=='number' and loader.version>=16,
    'Requires Bingus Shared Loader v15+ / API 1')
local runtime=require('mods/skyeshade/hd2runtime')
local function version(v)
    local a,b,c=tostring(v):match('^(%d+)%.(%d+)%.(%d+)$')
    assert(a,'Invalid HD2Runtime version');return tonumber(a),tonumber(b),tonumber(c)
end
local a,b,c=version(runtime.version)
local x,y,z=version('0.27.0')
assert(runtime.api_version==1 and (a>x or a==x and (b>y or b==y and c>=z)),
    'HD2Runtime dependency version mismatch')
local key='HD2RuntimeMod:mods/nephelym/nephelym_s_weaponry_rebalance'
local existing=rawget(_G,key)
if existing then return existing end
local function start()
local hd2=require('mods/skyeshade/hd2runtime')

return {
    hd2.ensure({
        plan={
            id='support-plan-e1a82ead21eb0d21e252c7c1',
            operations={
                {
                    id='support-2474b4116e7f11da29d90d54',
                    target=hd2.support_weapon('M-1000 Maxigun'):attack('primary'):projectile(),
                    allow_shared=true,
                    changes={
                        {field=hd2.fields.projectile.drag,expect=0.3,value=0.2},
                        {field=hd2.fields.projectile.velocity,expect=920,value=1000},
                    },
                },
                {
                    id='support-2b541b2c8362e667bddd392e',
                    target=hd2.support_weapon('M-1000 Maxigun'),
                    changes={
                        {field=hd2.fields.weapon.ergonomics,expect=4,value=10},
                        {field=hd2.fields.weapon.horizontal_spread,expect=10,value=5},
                        {field=hd2.fields.weapon.recoil_climb_vertical,expect=30,value=20},
                        {field=hd2.fields.weapon.recoil_drift_vertical,expect=20,value=10},
                        {field=hd2.fields.weapon.sway,expect=1,value=0.8},
                        {field=hd2.fields.weapon.vertical_spread,expect=10,value=5},
                    },
                },
                {
                    id='support-074eebd83d07f6fcc7da931f',
                    target=hd2.support_weapon('M-1000 Maxigun'):attack('primary'):projectile(),
                    allow_shared=true,
                    changes={
                        {field=hd2.fields.damage.ap_direct,expect=3,value=4},
                        {field=hd2.fields.damage.ap_large,expect=3,value=4},
                        {field=hd2.fields.damage.ap_slight,expect=3,value=4},
                        {field=hd2.fields.damage.player_durable_damage,expect=18,value=55},
                        {field=hd2.fields.damage.stagger,expect=15,value=25},
                        {field=hd2.fields.damage.player_standard_damage,expect=80,value=65},
                    },
                }
            },
        }
    }),
    hd2.ensure({
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
}

end
local state=start() or true
rawset(_G,key,state)
return state
