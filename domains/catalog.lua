-- Public aliases contain identities and field names, never process addresses.
-- Evidence booleans describe prior sibling evidence, not this observation.
local function field(component,offset,storage,expected,source,gameplay,labelled)
    return {component=component,offset=offset,storage=storage,expected=expected,
        evidence={structural_candidate=true,schema_labelled=labelled==true,
            gameplay_proven=gameplay==true,native_consumer_proven=false,source=source}}
end
local damage_source='Jar-5_buff/docs/research.md'
local shield_source='ShieldRelayImprovements/README.md'
local health_source='BastionReArmored/src/armor_proof/validate.lua'
local catalog={
    jar5={
        projectile_type=field('ProjectileWeaponComponentData',0,'u32',177,damage_source,false,true),
        standard_damage=field('DamageSettings',4,'i32',275,damage_source,false,true),
        durable_damage=field('DamageSettings',8,'i32',90,damage_source,false,true),
        armor_penetration=field('DamageSettings',12,'u32',3,damage_source,false,true),
        ['armor_penetration_lanes.1']=field('DamageSettings',16,'u32',3,damage_source,false,true),
        ['armor_penetration_lanes.2']=field('DamageSettings',20,'u32',3,damage_source,false,true),
        ['armor_penetration_lanes.3']=field('DamageSettings',24,'u32',0,damage_source,false,true)},
    orbital_laser={
        damage_type=field('DamageSettings',0,'u32',513,'StrongerOrbitalLaser/src/damage/validate.lua',false,true),
        standard_damage=field('DamageSettings',4,'i32',60,'StrongerOrbitalLaser/research/gameplay-proof-400.md',true,true),
        durable_damage=field('DamageSettings',8,'i32',60,'StrongerOrbitalLaser/research/gameplay-proof-400.md',true,true),
        interval=field('OrbitalAbilityComponentData',480,'f32',0.1,'StrongerOrbitalLaser/src/damage/validate.lua',false,true)},
    shield_relay={
        radius=field('ShieldComponentData',0,'f32',15,shield_source,true,false),
        durability=field('ShieldComponentData',76,'f32',4000,shield_source,true,false),
        lifetime=field('HellpodPayloadComponentData',4,'f32',40,shield_source,true,false),
        cooldown=field('StratagemSettings',104,'f32',90,'ShieldRelayImprovements/research/cooldown-live-confirmation.json',true,true)},
    jump_pack={
        recharge=field('RechargeComponentData',0,'f32',15,'JumpPackImprovements/research/current-build-port.md',true,false),
        vertical_launch_velocity=field('JumppackComponentData',0,'f32',40,'JumpPackImprovements/README.md',true,false),
        movement_scalar_04=field('JumppackComponentData',4,'f32',20,'JumpPackImprovements/research/movement.md',false,false),
        movement_scalar_24=field('JumppackComponentData',36,'f32',60,'JumpPackImprovements/research/movement.md',false,false)},
    amr={crosshair_type=field('WeaponDataComponentData',400,'u32',3,'ReticleAmr/research/gameplay-confirmation-0.1.0.json',true,true)},
}
for _,key in ipairs({'bastion','maelstrom'})do
    catalog[key]={
        main_health=field('HealthComponentData',0,'i32',8000,'BastionReArmored/README.md',key=='bastion',false),
        default_armor=field('HealthComponentData',280,'u32',4,health_source,key=='bastion',false)}
    for zone=0,37 do
        local prefix='zones.'..zone..'.'
        local ap=zone>=31 and 0 or zone>=6 and zone<=11 and 2 or 4
        catalog[key][prefix..'armor']=field('HealthComponentData',520+zone*552+216,'u32',ap,health_source,key=='bastion' and ap==4,false)
        if zone==3 or zone==4 then
            catalog[key][prefix..'affects_main_health']=field('HealthComponentData',520+zone*552+248,'f32',1,
                'BastionReArmored/src/lunchbox_proof/validate.lua',key=='bastion',false)
        end
    end
end
return catalog
