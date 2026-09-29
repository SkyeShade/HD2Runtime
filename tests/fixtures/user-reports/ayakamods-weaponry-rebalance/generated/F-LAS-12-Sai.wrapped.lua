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
        id='gui-object-2a7269b665783a5d909780a8',
        target=hd2.weapon('LAS-12 Sai'):attack('primary'):projectile(),
        allow_shared=true,
        changes={
            {field=hd2.fields.damage.player_durable_damage,expect=4,value=41},
            {field=hd2.fields.damage.player_standard_damage,expect=80,value=55},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-f1af46f43e5b20cc65720691',
        target=hd2.weapon('LAS-12 Sai'),
        changes={
            {field=hd2.fields.weapon.horizontal_spread,expect=140,value=40},
            {field=hd2.fields.weapon.recoil_climb_vertical,expect=25,value=15},
            {field=hd2.fields.weapon.sway,expect=1,value=0.8},
            {field=hd2.fields.weapon.vertical_spread,expect=140,value=40},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-ef52be410d921d00a14057a6',
        target=hd2.weapon('LAS-12 Sai'),
        changes={
            {field=hd2.fields.heat.cool_per_second,expect=5.4,value=8},
            {field=hd2.fields.heat.heat_per_shot,expect=2,value=1},
        },
    }
})
return operations

end
local state=start() or true
rawset(_G,key,state)
return state
