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
        id='plan-ba459a00161d51049d7ffa03',
        operations={
            {
                id='op-7d1c0e4a64d39318ae49e947',
                target=hd2.weapon('MA5C Assault Rifle'):attack('primary'):projectile(),
                allow_shared=true,
                field=hd2.fields.projectile.drag,
                expect=0.3,
                value=0.2,
            },
            {
                id='op-7b437f8f60246ec7958141d3',
                target=hd2.weapon('MA5C Assault Rifle'):attack('primary'):projectile(),
                allow_shared=true,
                changes={
                    {field=hd2.fields.damage.player_durable_damage,expect=16,value=56},
                    {field=hd2.fields.damage.player_standard_damage,expect=90,value=75},
                },
            }
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-cc6964d0b2b38f1e31257e6b',
        target=hd2.weapon('MA5C Assault Rifle'),
        changes={
            {field=hd2.fields.weapon.recoil_climb_vertical,expect=30,value=20},
            {field=hd2.fields.weapon.sway,expect=1,value=0.8},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-7656c9accd9794fd7a19c5e1',
        target=hd2.weapon('MA5C Assault Rifle'),
        changes={
            {field=hd2.fields.magazine.capacity,expect=32,value=60},
            {field=hd2.fields.magazine.magazines_from_supply,expect=8,value=6},
            {field=hd2.fields.magazine.spare_magazines,expect=8,value=6},
            {field=hd2.fields.magazine.starting_magazines,expect=5,value=4},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    patch={
        id='stratagem-9fb77b22d9f4ba8687ce146c',
        target=hd2.stratagem('Orbital Precision Strike'),
        field=hd2.fields.stratagem.definition_cooldown,
        expect=80,
        value=60,
    }
})
return operations

end
local state=start() or true
rawset(_G,key,state)
return state
