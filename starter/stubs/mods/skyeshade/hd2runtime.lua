---@meta
-- Generated authoring definitions. Never package or execute this file.
-- Schema SHA256 ec6a36467cd465f348873bb5fc9e39ddee8ce1f0d347e74dd636afc6ae6d2754

---@alias HD2Resource "0x16474112801385B6"|"0x59C5CA839449B379"|"0x80F1A156D9FA1E36"|"0x89C5493E08CA4207"|"0xB0C9FAF4AF8903F9"|"0xEC3575E7A93793BB"|"0xED13DDC480EC6910"|"amr"|"bastion"|"jar5"|"jump_pack"|"maelstrom"|"orbital_laser"|"shield_relay"
---@alias HD2PatchField "armor_penetration"
---@alias HD2TransactionField "cooldown"|"durability"|"lifetime"|"radius"

---@class HD2ReadTarget
---@field resource HD2Resource
---@field fields string[]

---@class HD2ReadRequest
---@field targets HD2ReadTarget[]

---@class HD2ReadJob
---@field status string
---@field result? table
---@field error? string
---@field step fun(): boolean

---@class HD2Watch
---@field status string
---@field result? table
---@field error? string
---@field cancel fun()

---@class HD2EnsureWatch
---@field status string
---@field result? table
---@field error? string
---@field cancel fun()
---@field runs integer
---@field interval number
---@field id string
---@field kind string

---@class HD2ObserveRequest
---@field targets HD2ReadTarget[]
---@field interval? number
---@field startup_delay? number
---@field timeout? number
---@field label? string
---@field on_result? fun(result: table): string?
---@field on_error? fun(reason: string, detail: table): string?

---@class HD2PrimaryWeaponMapRequest
---@field startup_delay? number
---@field on_result? fun(result: table)
---@field on_error? fun(reason: string, detail: table)

---@class HD2SnapshotCaptureRequest
---@field capture_delay_seconds? number
---@field output_directory? string
---@field output_path? string
---@field bytes_per_tick? integer
---@field chunk_bytes? integer
---@field on_result? fun(result: table)
---@field on_error? fun(reason: string, detail: table)

---@class HD2PatchRequest
---@field id string
---@field target HD2DamageProfile
---@field field HD2PatchField
---@field expect 3
---@field value 4
---@field diagnostic? boolean

---@class HD2TransactionChange
---@field field HD2TransactionField
---@field expect number
---@field value number

---@class HD2TransactionRequest
---@field id string
---@field target HD2Stratagem
---@field changes HD2TransactionChange[]
---@field diagnostic? boolean

---@class HD2EnsureRequest
---@field patch? HD2PatchRequest
---@field transaction? HD2TransactionRequest
---@field interval? number
---@field startup_delay? number

---@class HD2Weapon
---@field resource HD2Resource
---@field path string
local HD2Weapon = {}
---Available for: JAR-5 Dominator.
---@return HD2Projectile
function HD2Weapon:projectile() end
---Return a public read/observe target containing all mapped fields in this domain.
---@return HD2ReadTarget
function HD2Weapon:read_target() end
---Describe mapped domain fields without process access.
---@return table
function HD2Weapon:describe() end

---@class HD2Projectile
---@field resource HD2Resource
---@field path string
local HD2Projectile = {}
---Available for: JAR-5 Dominator.
---@return HD2DamageProfile
function HD2Projectile:damage() end
---Return a public read/observe target containing all mapped fields in this domain.
---@return HD2ReadTarget
function HD2Projectile:read_target() end
---Describe mapped domain fields without process access.
---@return table
function HD2Projectile:describe() end

---@class HD2DamageProfile
---@field resource HD2Resource
---@field path string
local HD2DamageProfile = {}
---Return a public read/observe target containing all mapped fields in this domain.
---@return HD2ReadTarget
function HD2DamageProfile:read_target() end
---Describe mapped domain fields without process access.
---@return table
function HD2DamageProfile:describe() end

---@class HD2Vehicle
---@field resource HD2Resource
---@field path string
local HD2Vehicle = {}
---Available for: Bastion, Maelstrom.
---@return HD2HealthComponent
function HD2Vehicle:health() end
---Return a public read/observe target containing all mapped fields in this domain.
---@return HD2ReadTarget
function HD2Vehicle:read_target() end
---Describe mapped domain fields without process access.
---@return table
function HD2Vehicle:describe() end

---@class HD2HealthComponent
---@field resource HD2Resource
---@field path string
local HD2HealthComponent = {}
---Return a public read/observe target containing all mapped fields in this domain.
---@return HD2ReadTarget
function HD2HealthComponent:read_target() end
---Describe mapped domain fields without process access.
---@return table
function HD2HealthComponent:describe() end

---@class HD2Stratagem
---@field resource HD2Resource
---@field path string
local HD2Stratagem = {}
---Available for: Shield Relay.
---@return HD2Shield
function HD2Stratagem:shield() end
---Available for: Shield Relay.
---@return HD2Payload
function HD2Stratagem:payload() end
---Available for: Orbital Laser.
---@return HD2DamageProfile
function HD2Stratagem:damage() end
---Available for: Orbital Laser.
---@return HD2OrbitalAbility
function HD2Stratagem:orbital() end
---Return a public read/observe target containing all mapped fields in this domain.
---@return HD2ReadTarget
function HD2Stratagem:read_target() end
---Describe mapped domain fields without process access.
---@return table
function HD2Stratagem:describe() end

---@class HD2Shield
---@field resource HD2Resource
---@field path string
local HD2Shield = {}
---Return a public read/observe target containing all mapped fields in this domain.
---@return HD2ReadTarget
function HD2Shield:read_target() end
---Describe mapped domain fields without process access.
---@return table
function HD2Shield:describe() end

---@class HD2Payload
---@field resource HD2Resource
---@field path string
local HD2Payload = {}
---Return a public read/observe target containing all mapped fields in this domain.
---@return HD2ReadTarget
function HD2Payload:read_target() end
---Describe mapped domain fields without process access.
---@return table
function HD2Payload:describe() end

---@class HD2Equipment
---@field resource HD2Resource
---@field path string
local HD2Equipment = {}
---Available for: Jump Pack.
---@return HD2RechargeComponent
function HD2Equipment:recharge() end
---Available for: Jump Pack.
---@return HD2JumppackComponent
function HD2Equipment:jumppack() end
---Return a public read/observe target containing all mapped fields in this domain.
---@return HD2ReadTarget
function HD2Equipment:read_target() end
---Describe mapped domain fields without process access.
---@return table
function HD2Equipment:describe() end

---@class HD2RechargeComponent
---@field resource HD2Resource
---@field path string
local HD2RechargeComponent = {}
---Return a public read/observe target containing all mapped fields in this domain.
---@return HD2ReadTarget
function HD2RechargeComponent:read_target() end
---Describe mapped domain fields without process access.
---@return table
function HD2RechargeComponent:describe() end

---@class HD2JumppackComponent
---@field resource HD2Resource
---@field path string
local HD2JumppackComponent = {}
---Return a public read/observe target containing all mapped fields in this domain.
---@return HD2ReadTarget
function HD2JumppackComponent:read_target() end
---Describe mapped domain fields without process access.
---@return table
function HD2JumppackComponent:describe() end

---@class HD2OrbitalAbility
---@field resource HD2Resource
---@field path string
local HD2OrbitalAbility = {}
---Return a public read/observe target containing all mapped fields in this domain.
---@return HD2ReadTarget
function HD2OrbitalAbility:read_target() end
---Describe mapped domain fields without process access.
---@return table
function HD2OrbitalAbility:describe() end

---@class HD2Fields_weapon
---@field crosshair_type "crosshair_type" APW-1 Anti-Materiel Rifle: read-only, integer
---@field base_capacity "weapon.base_capacity"
---@field capacity "weapon.capacity" Deprecated compatibility alias; use hd2.fields.magazine.capacity.
---@field player_crosshair_type "weapon.crosshair_type"
---@field ergonomics "weapon.ergonomics"
---@field feed_capacity_1 "weapon.feed_capacity_1" Deprecated compatibility alias; use hd2.fields.rounds.feed_capacity_1.
---@field feed_capacity_2 "weapon.feed_capacity_2" Deprecated compatibility alias; use hd2.fields.rounds.feed_capacity_2.
---@field fire_rate "weapon.fire_rate"
---@field horizontal_recoil "weapon.horizontal_recoil"
---@field horizontal_spread "weapon.horizontal_spread"
---@field primary_fire_mode "weapon.primary_fire_mode"
---@field recoil "weapon.recoil"
---@field recoil_climb_horizontal "weapon.recoil_climb_horizontal"
---@field recoil_climb_vertical "weapon.recoil_climb_vertical"
---@field recoil_drift_horizontal "weapon.recoil_drift_horizontal"
---@field recoil_drift_vertical "weapon.recoil_drift_vertical"
---@field slot "weapon.slot"
---@field suppressed "weapon.suppressed"
---@field sway "weapon.sway"
---@field vertical_recoil "weapon.vertical_recoil"
---@field vertical_spread "weapon.vertical_spread"

---@class HD2Fields_projectile
---@field projectile_type "projectile_type" JAR-5 Dominator: read-only, integer
---@field alternate_drag "projectile.alternate.drag"
---@field alternate_gravity "projectile.alternate.gravity"
---@field alternate_mass "projectile.alternate.mass"
---@field alternate_pellet_count "projectile.alternate.pellet_count"
---@field alternate_type "projectile.alternate.type"
---@field alternate_velocity "projectile.alternate.velocity"
---@field drag "projectile.drag"
---@field gravity "projectile.gravity"
---@field mass "projectile.mass"
---@field pellet_count "projectile.pellet_count"
---@field primary_drag "projectile.primary.drag"
---@field primary_gravity "projectile.primary.gravity"
---@field primary_mass "projectile.primary.mass"
---@field primary_pellet_count "projectile.primary.pellet_count"
---@field primary_type "projectile.primary.type"
---@field primary_velocity "projectile.primary.velocity"
---@field type "projectile.type"
---@field velocity "projectile.velocity"

---@class HD2Fields_damage
---@field armor_penetration "armor_penetration" JAR-5 Dominator: reviewed writable, integer
---@field armor_penetration_lanes_1 "armor_penetration_lanes.1" JAR-5 Dominator: read-only, integer
---@field armor_penetration_lanes_2 "armor_penetration_lanes.2" JAR-5 Dominator: read-only, integer
---@field armor_penetration_lanes_3 "armor_penetration_lanes.3" JAR-5 Dominator: read-only, integer
---@field durable_damage "durable_damage" JAR-5 Dominator: read-only, integer; Orbital Laser: read-only, integer
---@field standard_damage "standard_damage" JAR-5 Dominator: read-only, integer; Orbital Laser: read-only, integer
---@field damage_type "damage_type" Orbital Laser: read-only, integer
---@field alternate_ap_direct "damage.alternate.ap_direct"
---@field alternate_ap_extreme "damage.alternate.ap_extreme"
---@field alternate_ap_large "damage.alternate.ap_large"
---@field alternate_ap_slight "damage.alternate.ap_slight"
---@field alternate_demolition "damage.alternate.demolition"
---@field alternate_durable_damage "damage.alternate.durable_damage"
---@field alternate_push_force "damage.alternate.push_force"
---@field alternate_stagger "damage.alternate.stagger"
---@field alternate_standard_damage "damage.alternate.standard_damage"
---@field alternate_status_1_strength "damage.alternate.status_1_strength"
---@field alternate_status_1_type "damage.alternate.status_1_type"
---@field alternate_type "damage.alternate.type"
---@field ap_direct "damage.ap_direct"
---@field ap_extreme "damage.ap_extreme"
---@field ap_large "damage.ap_large"
---@field ap_slight "damage.ap_slight"
---@field demolition "damage.demolition"
---@field player_durable_damage "damage.durable_damage"
---@field primary_ap_direct "damage.primary.ap_direct"
---@field primary_ap_extreme "damage.primary.ap_extreme"
---@field primary_ap_large "damage.primary.ap_large"
---@field primary_ap_slight "damage.primary.ap_slight"
---@field primary_demolition "damage.primary.demolition"
---@field primary_durable_damage "damage.primary.durable_damage"
---@field primary_push_force "damage.primary.push_force"
---@field primary_stagger "damage.primary.stagger"
---@field primary_standard_damage "damage.primary.standard_damage"
---@field primary_type "damage.primary.type"
---@field push_force "damage.push_force"
---@field stagger "damage.stagger"
---@field player_standard_damage "damage.standard_damage"
---@field status_1_strength "damage.status_1_strength"
---@field status_1_type "damage.status_1_type"
---@field status_2_strength "damage.status_2_strength"
---@field status_2_type "damage.status_2_type"
---@field status_3_strength "damage.status_3_strength"
---@field status_3_type "damage.status_3_type"
---@field type "damage.type"

---@class HD2Fields_vehicle

---@class HD2Fields_health
---@field default_armor "default_armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field main_health "main_health" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_0_armor "zones.0.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_1_armor "zones.1.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_10_armor "zones.10.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_11_armor "zones.11.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_12_armor "zones.12.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_13_armor "zones.13.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_14_armor "zones.14.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_15_armor "zones.15.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_16_armor "zones.16.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_17_armor "zones.17.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_18_armor "zones.18.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_19_armor "zones.19.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_2_armor "zones.2.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_20_armor "zones.20.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_21_armor "zones.21.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_22_armor "zones.22.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_23_armor "zones.23.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_24_armor "zones.24.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_25_armor "zones.25.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_26_armor "zones.26.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_27_armor "zones.27.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_28_armor "zones.28.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_29_armor "zones.29.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_3_affects_main_health "zones.3.affects_main_health" Bastion: read-only, number; Maelstrom: read-only, number
---@field zones_3_armor "zones.3.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_30_armor "zones.30.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_31_armor "zones.31.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_32_armor "zones.32.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_33_armor "zones.33.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_34_armor "zones.34.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_35_armor "zones.35.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_36_armor "zones.36.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_37_armor "zones.37.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_4_affects_main_health "zones.4.affects_main_health" Bastion: read-only, number; Maelstrom: read-only, number
---@field zones_4_armor "zones.4.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_5_armor "zones.5.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_6_armor "zones.6.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_7_armor "zones.7.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_8_armor "zones.8.armor" Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_9_armor "zones.9.armor" Bastion: read-only, integer; Maelstrom: read-only, integer

---@class HD2Fields_stratagem
---@field cooldown "cooldown" Shield Relay: reviewed writable, number

---@class HD2Fields_shield
---@field durability "durability" Shield Relay: reviewed writable, number
---@field radius "radius" Shield Relay: reviewed writable, number

---@class HD2Fields_payload
---@field lifetime "lifetime" Shield Relay: reviewed writable, number

---@class HD2Fields_equipment

---@class HD2Fields_recharge
---@field recharge "recharge" Jump Pack: read-only, number

---@class HD2Fields_jumppack
---@field movement_scalar_04 "movement_scalar_04" Jump Pack: read-only, number
---@field movement_scalar_24 "movement_scalar_24" Jump Pack: read-only, number
---@field vertical_launch_velocity "vertical_launch_velocity" Jump Pack: read-only, number

---@class HD2Fields_orbital
---@field interval "interval" Orbital Laser: read-only, number

---@class HD2Fields_arc
---@field chain_count "arc.chain_count"
---@field distance_at_max_spread "arc.distance_at_max_spread"
---@field distance_at_max_spread_first_shot "arc.distance_at_max_spread_first_shot"
---@field max_angle_spread "arc.max_angle_spread"
---@field max_angle_spread_first_shot "arc.max_angle_spread_first_shot"
---@field max_split "arc.max_split"
---@field range "arc.range"
---@field velocity "arc.velocity"

---@class HD2Fields_beam
---@field length "beam.length"
---@field radius "beam.radius"

---@class HD2Fields_magazine
---@field capacity "magazine.capacity"
---@field magazines_from_ammo_box "magazine.magazines_from_ammo_box"
---@field magazines_from_supply "magazine.magazines_from_supply"
---@field spare_magazines "magazine.spare_magazines"
---@field starting_magazines "magazine.starting_magazines"

---@class HD2Fields_rounds
---@field capacity "rounds.capacity"
---@field feed_capacity_1 "rounds.feed_capacity_1"
---@field feed_capacity_2 "rounds.feed_capacity_2"
---@field rounds_from_ammo_box "rounds.rounds_from_ammo_box"
---@field rounds_from_supply "rounds.rounds_from_supply"
---@field spare_rounds "rounds.spare_rounds"
---@field starting_rounds "rounds.starting_rounds"

---@class HD2Fields
---@field weapon HD2Fields_weapon
---@field projectile HD2Fields_projectile
---@field damage HD2Fields_damage
---@field vehicle HD2Fields_vehicle
---@field health HD2Fields_health
---@field stratagem HD2Fields_stratagem
---@field shield HD2Fields_shield
---@field payload HD2Fields_payload
---@field equipment HD2Fields_equipment
---@field recharge HD2Fields_recharge
---@field jumppack HD2Fields_jumppack
---@field orbital HD2Fields_orbital
---@field arc HD2Fields_arc
---@field beam HD2Fields_beam
---@field magazine HD2Fields_magazine
---@field rounds HD2Fields_rounds

---@class HD2Enum_projectile_type
---@field jar5 177

---@class HD2Enum_damage_type
---@field jar5 153
---@field orbital_laser 513

---@class HD2Enum_crosshair_type
---@field amr_original 3

---@class HD2Enums
---@field projectile_type HD2Enum_projectile_type
---@field damage_type HD2Enum_damage_type
---@field crosshair_type HD2Enum_crosshair_type

---@class HD2Resources
---@field amr "amr"
---@field bastion "bastion"
---@field jar5 "jar5"
---@field jump_pack "jump_pack"
---@field maelstrom "maelstrom"
---@field orbital_laser "orbital_laser"
---@field shield_relay "shield_relay"

---@class HD2Runtime
---@field fields HD2Fields
---@field enums HD2Enums
---@field resources HD2Resources
---@field version string
---@field api_version integer
local hd2 = {}
---@alias HD2WeaponName "AMR"|"APW-1 Anti-Materiel Rifle"|"AR-11 Arbitrator"|"AR-2 Coyote"|"AR-23 Liberator"|"AR-23A Liberator Carbine"|"AR-23C Liberator Concussive"|"AR-23P Liberator Penetrator"|"AR-32 Pacifier"|"AR-59 Suppressor"|"AR-61 Tenderizer"|"AR/GL-21 One-Two"|"ARC-12 Blitzer"|"BR-14 Adjudicator"|"CB-9 Exploding Crossbow"|"CQC-19 Stun Lance"|"CQC-2 Saber"|"CQC-30 Stun Baton"|"CQC-42 Machete"|"CQC-5 Combat Hatchet"|"CQC-73 Entrenchment Tool"|"DBS-2 Double Freedom"|"FLAM-66 Torcher"|"GL-15 Evictor"|"GP-20 Ultimatum"|"GP-31 Grenade Pistol"|"JAR-5 Dominator"|"LAS-12 Sai"|"LAS-13 Trident"|"LAS-16 Sickle"|"LAS-17 Double-Edge Sickle"|"LAS-5 Scythe"|"LAS-58 Talon"|"LAS-7 Dagger"|"M6C/SOCOM Pistol"|"M7S SMG"|"M90A Shotgun"|"MA5C Assault Rifle"|"MP-98 Knight"|"P-11 Stim Pistol"|"P-113 Verdict"|"P-19 Redeemer"|"P-2 Peacemaker"|"P-33 Missile Pistol"|"P-34 Breacher"|"P-35 Re-Educator"|"P-4 Senator"|"P-69 Veto"|"P-72 Crisper"|"P-92 Warrant"|"P/40-K Bolt Pistol"|"PLAS-1 Scorcher"|"PLAS-101 Purifier"|"PLAS-15 Loyalist"|"PLAS-39 Accelerator Rifle"|"R-2 Amendment"|"R-2124 Constitution"|"R-36 Eruptor"|"R-4 Hyena"|"R-6 Deadeye"|"R-63 Diligence"|"R-63CS Diligence Counter Sniper"|"R-72 Censor"|"R/40-K Hot-Shot Marksman Rifle"|"SG-20 Halt"|"SG-22 Bushwhacker"|"SG-225 Breaker"|"SG-225IE Breaker Incendiary"|"SG-225SP Breaker Spray&Pray"|"SG-451 Cookout"|"SG-8 Punisher"|"SG-8P Punisher Plasma"|"SG-8S Slugger"|"SG-97 Sweeper"|"SMG-203 Gallant"|"SMG-32 Reprimand"|"SMG-37 Defender"|"SMG-72 Pummeler"|"SMG/FLAM-34 Stoker"|"StA-11 SMG"|"StA-52 Assault Rifle"|"VG-70 Variable"|"amr"|"jar5"
---@param name HD2WeaponName
---@return HD2Weapon
function hd2.weapon(name) end
---@alias HD2VehicleName "Bastion"|"Maelstrom"|"bastion"|"maelstrom"
---@param name HD2VehicleName
---@return HD2Vehicle
function hd2.vehicle(name) end
---@alias HD2StratagemName "Orbital Laser"|"Shield Relay"|"orbital_laser"|"shield_relay"
---@param name HD2StratagemName
---@return HD2Stratagem
function hd2.stratagem(name) end
---@alias HD2EquipmentName "Jump Pack"|"jump_pack"
---@param name HD2EquipmentName
---@return HD2Equipment
function hd2.equipment(name) end
---Describe schema and prior evidence without reading memory.
---@param resource HD2Resource
---@return table
function hd2.describe(resource) end
---Create a bounded read job; advance with job.step().
---@param request HD2ReadRequest
---@return HD2ReadJob
function hd2.read(request) end
---Runtime-scheduled read observation; default 60 update seconds.
---@param request HD2ObserveRequest
---@return HD2Watch
function hd2.observe(request) end
---Enumerate structurally owned weapon resources through one bounded shared discovery pass.
---@param request HD2PrimaryWeaponMapRequest
---@return HD2ReadJob
function hd2.enumerate_primary_weapons(request) end
---Schedule one read-only primary weapon enumeration after a startup delay.
---@param request HD2PrimaryWeaponMapRequest
---@return HD2Watch
function hd2.map_primary_weapons(request) end
---Incrementally capture committed readable current-process regions to a build-bound HD2SNAP file.
---@param request HD2SnapshotCaptureRequest
---@return HD2Watch
function hd2.capture_snapshot(request) end
---Format a completed read result.
---@param result table
---@return string
function hd2.format(result) end
---Freshly resolve and apply the reviewed JAR-5 logical AP field.
---@param request HD2PatchRequest
---@return HD2Watch
function hd2.patch(request) end
---Validate every change before writing; guarded rollback on failure.
---@param request HD2TransactionRequest
---@return HD2Watch
function hd2.transaction(request) end
---Wrap exactly one patch or transaction. Default 60 update seconds, three-second startup, terminal conflict rejection.
---@param request HD2EnsureRequest
---@return HD2EnsureWatch
function hd2.ensure(request) end

if rawget(_G,'CowboyBingusModLoader') then
    error("HD2Runtime SDK stubs are authoring-only; install the runtime package in-game")
end
return hd2
