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
        id='gui-object-1fa21a42f1e0a9f422dd041f',
        target=hd2.weapon('R/40-K Hot-Shot Marksman Rifle'):attack('primary'):projectile(),
        allow_shared=true,
        changes={
            {field=hd2.fields.damage.player_durable_damage,expect=40,value=161},
            {field=hd2.fields.damage.player_standard_damage,expect=275,value=215},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-b3b8d1322fea2e6411e98b68',
        target=hd2.weapon('R/40-K Hot-Shot Marksman Rifle'),
        changes={
            {field=hd2.fields.weapon.recoil_climb_horizontal,expect=12.5,value=10},
            {field=hd2.fields.weapon.recoil_climb_vertical,expect=32.5,value=25},
            {field=hd2.fields.weapon.recoil_drift_horizontal,expect=12.5,value=10},
            {field=hd2.fields.weapon.recoil_drift_vertical,expect=17.5,value=15},
            {field=hd2.fields.weapon.sway,expect=1,value=0.8},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-05950074751c8c07d5f1d507',
        target=hd2.weapon('R/40-K Hot-Shot Marksman Rifle'),
        changes={
            {field=hd2.fields.magazine.magazines_from_supply,expect=7,value=9},
            {field=hd2.fields.magazine.spare_magazines,expect=7,value=9},
        },
    }
})
return operations

end
local state=start() or true
rawset(_G,key,state)
return state
