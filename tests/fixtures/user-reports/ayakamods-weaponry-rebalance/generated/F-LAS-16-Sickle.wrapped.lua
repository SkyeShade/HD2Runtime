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

local operations={}
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-b2d4734fc42038f85874a150',
        target=hd2.weapon('LAS-16 Sickle'):attack('primary'):projectile(),
        allow_shared=true,
        changes={
            {field=hd2.fields.damage.ap_direct,expect=2,value=3},
            {field=hd2.fields.damage.player_durable_damage,expect=6,value=23},
            {field=hd2.fields.damage.player_standard_damage,expect=60,value=65},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-b604c101133563247e3cbb3b',
        target=hd2.weapon('LAS-16 Sickle'),
        changes={
            {field=hd2.fields.weapon.horizontal_spread,expect=20,value=10},
            {field=hd2.fields.weapon.recoil_climb_vertical,expect=2,value=1},
            {field=hd2.fields.weapon.recoil_drift_horizontal,expect=2,value=1},
            {field=hd2.fields.weapon.recoil_drift_vertical,expect=2,value=1},
            {field=hd2.fields.weapon.sway,expect=1,value=0.8},
            {field=hd2.fields.weapon.vertical_spread,expect=20,value=10},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-7ee38e771dbebfb048ee936a',
        target=hd2.weapon('LAS-16 Sickle'),
        changes={
            {field=hd2.fields.heat.cool_per_second,expect=8,value=10},
            {field=hd2.fields.heat.heat_per_shot,expect=1.15,value=1},
        },
    }
})
return operations

end
local state=start() or true
rawset(_G,key,state)
return state
