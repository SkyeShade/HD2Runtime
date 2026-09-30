-- HD2-Addon: mods/harness/h3_halt_sway_only
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
local key='HD2RuntimeMod:mods/harness/h3_halt_sway_only'
local existing=rawget(_G,key)
if existing then return existing end
local function start()
local hd2=require('mods/skyeshade/hd2runtime')

return {
    hd2.ensure({
        patch={
            id='gui-object-fd5f98440f4482ea96b79ad8',
            target=hd2.weapon('SMG-32 Reprimand'),
            field=hd2.fields.weapon.fire_rate,
            expect=490,
            value=539,
        }
    }),
    hd2.ensure({
        patch={
            id='gui-object-458f3277369af725e80a19d9',
            target=hd2.weapon('SG-20 Halt'),
            field=hd2.fields.weapon.sway,
            expect=1,
            value=1.1,
        }
    }),
    hd2.ensure({
        patch={
            id='gui-object-52f52e2ae0a28e9f7526e75e',
            target=hd2.weapon('SMG-32 Reprimand'),
            field=hd2.fields.weapon.sway,
            expect=1,
            value=1.1,
        }
    }),
    hd2.ensure({
        transaction={
            id='gui-object-df10a69fd28f65fa6d3ea5a5',
            target=hd2.weapon('AR-23 Liberator'),
            changes={
                {field=hd2.fields.weapon.ergonomics,expect=65,value=71.5},
                {field=hd2.fields.weapon.sway,expect=1,value=1.1},
            },
        }
    })
}

end
local state=start() or true
rawset(_G,key,state)
return state
