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
    plan={
        id='plan-978a3a452b01199799d56d4e',
        operations={
            {
                id='op-0434d999b631183c177a808f',
                target=hd2.weapon('SMG-32 Reprimand'):attack('primary'):projectile(),
                allow_shared=true,
                field=hd2.fields.projectile.drag,
                expect=1.2,
                value=0.6,
            },
            {
                id='op-84fa0eeec6b1beb063512a05',
                target=hd2.weapon('SMG-32 Reprimand'):attack('primary'):projectile(),
                allow_shared=true,
                changes={
                    {field=hd2.fields.damage.player_durable_damage,expect=32,value=83},
                    {field=hd2.fields.damage.player_standard_damage,expect=140,value=110},
                },
            }
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-83b36bae82739da2e4f92309',
        target=hd2.weapon('SMG-32 Reprimand'),
        changes={
            {field=hd2.fields.weapon.recoil_climb_vertical,expect=55,value=45},
            {field=hd2.fields.weapon.recoil_drift_vertical,expect=40,value=20},
            {field=hd2.fields.weapon.sway,expect=1,value=0.5},
        },
    }
})
return operations

end
local state=start() or true
rawset(_G,key,state)
return state
