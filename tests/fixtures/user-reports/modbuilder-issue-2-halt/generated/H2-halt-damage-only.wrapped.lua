-- HD2-Addon: mods/harness/h2_halt_damage_only
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
local key='HD2RuntimeMod:mods/harness/h2_halt_damage_only'
local existing=rawget(_G,key)
if existing then return existing end
local function start()
local hd2=require('mods/skyeshade/hd2runtime')

return {
    hd2.ensure({
        transaction={
            id='gui-object-00264ddd702ac80141e278bb',
            target=hd2.weapon('SG-20 Halt'):attack('feed_primary'):projectile(),
            allow_shared=true,
            changes={
                {field=hd2.fields.damage.ap_direct,expect=3,value=4},
                {field=hd2.fields.damage.ap_extreme,expect=0,value=1},
                {field=hd2.fields.damage.ap_large,expect=3,value=4},
                {field=hd2.fields.damage.ap_slight,expect=3,value=4},
                {field=hd2.fields.damage.demolition,expect=10,value=11},
                {field=hd2.fields.damage.player_durable_damage,expect=10,value=11},
                {field=hd2.fields.damage.push_force,expect=20,value=21},
                {field=hd2.fields.damage.stagger,expect=20,value=21},
                {field=hd2.fields.damage.player_standard_damage,expect=35,value=36},
            },
        }
    }),
    hd2.ensure({
        transaction={
            id='gui-object-5fb7d3f3f1ee1da079509248',
            target=hd2.weapon('SG-20 Halt'):attack('feed_alternate'):projectile(),
            allow_shared=true,
            changes={
                {field=hd2.fields.damage.ap_direct,expect=2,value=3},
                {field=hd2.fields.damage.ap_extreme,expect=0,value=1},
                {field=hd2.fields.damage.ap_large,expect=2,value=3},
                {field=hd2.fields.damage.ap_slight,expect=2,value=3},
                {field=hd2.fields.damage.demolition,expect=10,value=11},
                {field=hd2.fields.damage.player_durable_damage,expect=2,value=3},
                {field=hd2.fields.damage.push_force,expect=10,value=11},
                {field=hd2.fields.damage.stagger,expect=15,value=16},
                {field=hd2.fields.damage.player_standard_damage,expect=6,value=7},
                {field=hd2.fields.damage.status_1_strength,expect=1,value=1.1},
            },
        }
    }),
    hd2.ensure({
        patch={
            id='gui-object-db49747b1905c9e913c04f70',
            target=hd2.weapon('SMG-32 Reprimand'),
            field=hd2.fields.weapon.fire_rate,
            expect=490,
            value=539,
        }
    }),
    hd2.ensure({
        patch={
            id='gui-object-d4013c34076eeb57bbd094cc',
            target=hd2.weapon('SMG-32 Reprimand'),
            field=hd2.fields.weapon.sway,
            expect=1,
            value=1.1,
        }
    }),
    hd2.ensure({
        transaction={
            id='gui-object-a086d747d1c246b36cfecd1f',
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
