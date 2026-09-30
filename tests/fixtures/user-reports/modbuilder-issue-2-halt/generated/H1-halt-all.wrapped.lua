-- HD2-Addon: mods/harness/h1_halt_all
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
local key='HD2RuntimeMod:mods/harness/h1_halt_all'
local existing=rawget(_G,key)
if existing then return existing end
local function start()
local hd2=require('mods/skyeshade/hd2runtime')

return {
    hd2.ensure({
        plan={
            id='plan-39050ab3450751362ef7902d',
            operations={
                {
                    id='op-02d51e1b4be2f94ed1e123c2',
                    target=hd2.weapon('SG-20 Halt'):attack('feed_primary'):projectile(),
                    allow_shared=true,
                    changes={
                        {field=hd2.fields.projectile.drag,expect=0.3,value=0.33},
                        {field=hd2.fields.projectile.gravity,expect=1,value=1.1},
                        {field=hd2.fields.projectile.mass,expect=6,value=6.6},
                        {field=hd2.fields.projectile.pellet_count,expect=11,value=12},
                        {field=hd2.fields.projectile.velocity,expect=385,value=423.5},
                    },
                },
                {
                    id='op-e139fd50c4ee70732d364b6e',
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
            },
        }
    }),
    hd2.ensure({
        plan={
            id='plan-6b95704f3a40baef12ada947',
            operations={
                {
                    id='op-dc96f5bbccdc5b9166c9838c',
                    target=hd2.weapon('SG-20 Halt'):attack('feed_alternate'):projectile(),
                    allow_shared=true,
                    changes={
                        {field=hd2.fields.projectile.drag,expect=0.3,value=0.33},
                        {field=hd2.fields.projectile.gravity,expect=1,value=1.1},
                        {field=hd2.fields.projectile.mass,expect=4.5,value=4.95},
                        {field=hd2.fields.projectile.pellet_count,expect=20,value=21},
                        {field=hd2.fields.projectile.velocity,expect=800,value=880},
                    },
                },
                {
                    id='op-aa496144fdf0c76f1fd9d716',
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
            },
        }
    }),
    hd2.ensure({
        patch={
            id='gui-object-3d9ff4833c24584a039f823f',
            target=hd2.weapon('SG-20 Halt'),
            field=hd2.fields.weapon.fire_rate,
            expect=80,
            value=88,
        }
    }),
    hd2.ensure({
        patch={
            id='gui-object-a83eacd759c68ae439e641ff',
            target=hd2.weapon('SMG-32 Reprimand'),
            field=hd2.fields.weapon.fire_rate,
            expect=490,
            value=539,
        }
    }),
    hd2.ensure({
        transaction={
            id='gui-object-96ab050f03038c0a4922cdd2',
            target=hd2.weapon('SG-20 Halt'),
            allow_unverified_effect=true,
            changes={
                {field=hd2.fields.weapon.ergonomics,expect=65,value=71.5},
                {field=hd2.fields.weapon.horizontal_spread,expect=300,value=330},
                {field=hd2.fields.weapon.recoil_climb_horizontal,expect=50,value=55},
                {field=hd2.fields.weapon.recoil_climb_vertical,expect=200,value=220},
                {field=hd2.fields.weapon.recoil_drift_horizontal,expect=40,value=44},
                {field=hd2.fields.weapon.recoil_drift_vertical,expect=40,value=44},
                {field=hd2.fields.weapon.suppressed,expect=false,value=true},
                {field=hd2.fields.weapon.sway,expect=1,value=1.1},
                {field=hd2.fields.weapon.third_person_reticle,expect=true,value=false},
                {field=hd2.fields.weapon.vertical_spread,expect=200,value=220},
            },
        }
    }),
    hd2.ensure({
        patch={
            id='gui-object-dbe3d863f828b9482dbecc42',
            target=hd2.weapon('SMG-32 Reprimand'),
            field=hd2.fields.weapon.sway,
            expect=1,
            value=1.1,
        }
    }),
    hd2.ensure({
        transaction={
            id='gui-object-8fd4e760e888cbde7a9ac6f3',
            target=hd2.weapon('AR-23 Liberator'),
            changes={
                {field=hd2.fields.weapon.ergonomics,expect=65,value=71.5},
                {field=hd2.fields.weapon.sway,expect=1,value=1.1},
            },
        }
    }),
    hd2.ensure({
        transaction={
            id='gui-object-3e66c8151dcaf52ef19365ec',
            target=hd2.weapon('SG-20 Halt'),
            changes={
                {field=hd2.fields.rounds.feed_capacity_1,expect=8,value=8.8},
                {field=hd2.fields.rounds.feed_capacity_2,expect=8,value=8.8},
                {field=hd2.fields.rounds.rounds_from_supply,expect=60,value=61},
                {field=hd2.fields.rounds.spare_rounds,expect=60,value=61},
                {field=hd2.fields.rounds.starting_rounds,expect=32,value=33},
            },
        }
    })
}

end
local state=start() or true
rawset(_G,key,state)
return state
