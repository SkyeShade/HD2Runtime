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
        id='gui-object-aba9f0c284c40c71aaf8f6ff',
        target=hd2.weapon('SG-20 Halt'):attack('feed_primary'):projectile(),
        allow_shared=true,
        changes={
            {field=hd2.fields.damage.player_durable_damage,expect=10,value=20},
            {field=hd2.fields.damage.player_standard_damage,expect=35,value=26},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-a2877e602fe56952c82a3500',
        target=hd2.weapon('SG-20 Halt'):attack('feed_alternate'):projectile(),
        allow_shared=true,
        changes={
            {field=hd2.fields.damage.ap_direct,expect=2,value=3},
            {field=hd2.fields.damage.ap_large,expect=2,value=3},
            {field=hd2.fields.damage.ap_slight,expect=2,value=3},
            {field=hd2.fields.damage.player_durable_damage,expect=2,value=4},
            {field=hd2.fields.damage.player_standard_damage,expect=6,value=9},
            {field=hd2.fields.damage.status_1_strength,expect=1,value=3},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    patch={
        id='gui-object-2a64b61fd1fed19c196b1ab7',
        target=hd2.weapon('SG-20 Halt'),
        field=hd2.fields.weapon.sway,
        expect=1,
        value=0.8,
    }
})
return operations

end
local state=start() or true
rawset(_G,key,state)
return state
