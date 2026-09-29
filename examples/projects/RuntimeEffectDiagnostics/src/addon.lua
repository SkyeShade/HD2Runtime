local hd2=require('mods/skyeshade/hd2runtime')
-- Live diagnostic for the AyakaMods report (docs/user-report-ayakamods-2026-09-29.md). Six independent tests, each
-- behind its own Mod Options toggle (all off by default), each its own ensure: one failing test cannot stop another,
-- and switching a test off restores the game's own value. Values are exaggerated so the result cannot be mistaken
-- for normal variation. Component values (magazine, heat, backpack) are copied into a weapon or backpack when the
-- game builds it: after APPLY, get a freshly built one (redeploy, reinforce, or call in a new support weapon).
local options=hd2.options({id='runtime_effect_diagnostics',title='Runtime Effect Diagnostics'})
local function test(id,label,description)
    return options:toggle({id=id,label=label,default=false,description=description})
end
local operations={}

-- 1. MA5C magazine: 32 -> 60 rounds (WeaponMagazine, copied at weapon build).
operations[#operations+1]=hd2.ensure({enabled=test('ma5c_magazine','MA5C magazine 60',
        'MA5C Assault Rifle magazine 32 -> 60. Needs a freshly built MA5C (redeploy or reinforce).'),
    patch={id='diag-ma5c-magazine',target=hd2.weapon('MA5C Assault Rifle'),
        field=hd2.fields.magazine.capacity,expect=32,value=60}})

-- 2. SG-20 Halt flechette damage: 35 -> 350 per pellet (projectile damage row, read when a pellet hits).
local halt=hd2.weapon('SG-20 Halt'):attack('feed_primary'):projectile()
operations[#operations+1]=hd2.ensure({enabled=test('halt_damage','Halt flechette damage x10',
        'SG-20 Halt flechette (primary feed) damage 35 -> 350 per pellet. Applies to the next shot.'),
    patch={id='diag-halt-damage',target=halt,allow_shared=true,
        field=hd2.fields.damage.player_standard_damage,expect=35,value=350}})

-- 3. LAS-16 Sickle heat per shot: 1.15 -> 20 (WeaponHeat, copied at weapon build).
operations[#operations+1]=hd2.ensure({enabled=test('sickle_heat','Sickle overheats in 5 shots',
        'LAS-16 Sickle heat per shot 1.15 -> 20 (capacity 100). Needs a freshly built Sickle.'),
    patch={id='diag-sickle-heat',target=hd2.weapon('LAS-16 Sickle'),
        field=hd2.fields.heat.heat_per_shot,expect=1.15,value=20}})

-- 4. M-1000 Maxigun damage: 80 -> 800 per bullet (projectile damage row, read when a bullet hits).
operations[#operations+1]=hd2.ensure({enabled=test('maxigun_damage','Maxigun damage x10',
        'M-1000 Maxigun damage 80 -> 800 per bullet. Applies to the next shot.'),
    patch={id='diag-maxigun-damage',target=hd2.support_weapon('M-1000 Maxigun'):attack('primary'):projectile(),
        allow_shared=true,field=hd2.fields.damage.player_standard_damage,expect=80,value=800}})

-- 5. M-1000 Maxigun backpack: 1000 -> 3000 rounds carried and at delivery, supply refill 500 -> 1500.
operations[#operations+1]=hd2.ensure({enabled=test('maxigun_backpack','Maxigun backpack 3000',
        'Maxigun backpack capacity and starting rounds 1000 -> 3000, supply refill 500 -> 1500. Needs a newly '
        ..'called-in Maxigun (its backpack is built on delivery).'),
    transaction={id='diag-maxigun-backpack',target=hd2.support_weapon('M-1000 Maxigun'):backpack(),
        allow_unverified_effect=true,changes={
            {field=hd2.fields.deposit.capacity,expect=1000,value=3000},
            {field=hd2.fields.deposit.start_amount,expect=1000,value=3000},
            {field=hd2.fields.deposit.refill_amount,expect=500,value=1500}}}})

-- 6. Orbital Precision Strike cooldown: 80 -> 5 seconds (StratagemDefinition +104, the member the Shield Relay
-- cooldown proof used).
operations[#operations+1]=hd2.ensure({enabled=test('precision_cooldown','Precision Strike cooldown 5 s',
        'Orbital Precision Strike cooldown 80 -> 5 seconds. Try it on the next call-in.'),
    patch={id='diag-precision-cooldown',target=hd2.stratagem('Orbital Precision Strike'),
        field=hd2.fields.stratagem.definition_cooldown,expect=80,value=5}})

return operations
