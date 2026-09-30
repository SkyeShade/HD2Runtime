-- HD2-Addon: mods/harness/h0_control_no_halt
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
local key='HD2RuntimeMod:mods/harness/h0_control_no_halt'
local existing=rawget(_G,key)
if existing then return existing end
local function start()
local hd2=require('mods/skyeshade/hd2runtime')

return {
    hd2.ensure({
        patch={
            id='gui-object-1cc8282cf3f687c7088ea1e2',
            target=hd2.weapon('SMG-32 Reprimand'),
            field=hd2.fields.weapon.fire_rate,
            expect=490,
            value=539,
        }
    }),
    hd2.ensure({
        patch={
            id='gui-object-d1d8b4937e04e28ef1e40df8',
            target=hd2.weapon('SMG-32 Reprimand'),
            field=hd2.fields.weapon.sway,
            expect=1,
            value=1.1,
        }
    }),
    hd2.ensure({
        transaction={
            id='gui-object-62e0b1f6fdaa0b0c382af24c',
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
