-- Independent regression baselines, used only for comparison with observed reads.
-- These numbers must never supply missing live values.
local function f(name,value,tolerance)return {name=name,value=value,tolerance=tolerance or 0}end
local targets={
    {resource='jar5',id='0x80F1A156D9FA1E36',label='JAR-5 Dominator',
        records={ProjectileWeaponComponentData={component_index=321,record_index=211},
            DamageSettings={group=1,record_index=158,record_kind=153}},
        fields={f('projectile_type',177),f('standard_damage',275),f('durable_damage',90),
            f('armor_penetration',3),f('armor_penetration_lanes.1',3),
            f('armor_penetration_lanes.2',3),f('armor_penetration_lanes.3',0)}},
    {resource='amr',id='0x89C5493E08CA4207',label='AMR',
        records={WeaponDataComponentData={component_index=236,record_index=354}},
        fields={f('crosshair_type',3)}},
    {resource='bastion',id='0x16474112801385B6',label='Bastion',
        records={HealthComponentData={component_index=224,record_index=104}},
        fields={f('main_health',8000),f('default_armor',4)}},
    {resource='orbital_laser',id='0xEC3575E7A93793BB',label='Orbital Laser',
        records={OrbitalAbilityComponentData={component_index=308,record_index=0},
            DamageSettings={group=1,record_index=504,record_kind=513}},
        fields={f('damage_type',513),f('standard_damage',60),f('durable_damage',60),f('interval',0.1,0.00000001)}},
    {resource='shield_relay',id='0xED13DDC480EC6910',label='Shield Relay',
        records={ShieldComponentData={component_index=94,record_index=12},
            HellpodPayloadComponentData={component_index=164,record_index=3},
            StratagemSettings={group=3,record_index=1,record_kind=22}},
        fields={f('radius',15),f('durability',4000),f('lifetime',40),f('cooldown',90)}},
    {resource='jump_pack',id='0x59C5CA839449B379',label='Jump Pack',
        records={RechargeComponentData={component_index=99,record_index=1},
            JumppackComponentData={component_index=264,record_index=1}},
        fields={f('recharge',15),f('vertical_launch_velocity',40),f('movement_scalar_04',20),f('movement_scalar_24',60)}},
}
for zone=0,37 do
    local expected=zone>=31 and 0 or zone>=6 and zone<=11 and 2 or 4
    local fields=targets[3].fields
    fields[#fields+1]=f('zones.'..zone..'.armor',expected)
end
for _,zone in ipairs({3,4})do
    local fields=targets[3].fields
    fields[#fields+1]=f('zones.'..zone..'.affects_main_health',1)
end
return targets
