---@meta
-- Generated authoring definitions. Never package or execute this file.
-- Schema SHA256 f22c8c3b52f463843ed3eaad53e4bd0b1b4884057ec6d67487b213d03e5c5f8f

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
---@field target HD2AuthoringTarget
---@field field string
---@field expect number|boolean|HD2ProjectileReference|HD2Explosion
---@field value number|boolean|HD2ProjectileReference|HD2Explosion
---@field diagnostic? boolean
---@field allow_shared? boolean

---@class HD2TransactionChange
---@field field string
---@field expect number|boolean|HD2ProjectileReference|HD2Explosion
---@field value number|boolean|HD2ProjectileReference|HD2Explosion

---@class HD2TransactionRequest
---@field id string
---@field target HD2AuthoringTarget
---@field changes HD2TransactionChange[]
---@field diagnostic? boolean
---@field allow_shared? boolean

---@class HD2PlanTargetFrom
---@field operation string
---@field path "projectile"|"terminal.impact"|"terminal.expiry"

---@class HD2PlanOperation
---@field id string
---@field target? HD2AuthoringTarget
---@field target_from? HD2PlanTargetFrom
---@field field? string
---@field expect? number|boolean|HD2ProjectileReference|HD2Explosion
---@field value? number|boolean|HD2ProjectileReference|HD2Explosion
---@field changes? HD2TransactionChange[]
---@field allow_shared? boolean

---@class HD2PlanPhase
---@field id? string
---@field operations HD2PlanOperation[]

---@class HD2PlanRequest
---@field id string
---@field operations? HD2PlanOperation[]
---@field phases? HD2PlanPhase[]
---@field diagnostic? boolean

---@class HD2EnsureRequest
---@field patch? HD2PatchRequest
---@field transaction? HD2TransactionRequest
---@field plan? HD2PlanRequest
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
---@alias HD2AttackRole "alternate"|"feed_alternate"|"feed_primary"|"primary"

---@class HD2PlayerAttack
---@field resource "player_weapon"
---@field path "attack"
---@field weapon HD2WeaponName
---@field attack HD2AttackRole
local HD2PlayerAttack = {}
---@return HD2ProjectileReference
function HD2PlayerAttack:projectile() end
---@return table
function HD2PlayerAttack:describe() end

---@class HD2ProjectileReference
---@field resource "player_weapon"
---@field path "projectile_reference"
---@field weapon HD2WeaponName
---@field attack HD2AttackRole
local HD2ProjectileReference = {}
---@param phase "impact"|"expiry"
---@return HD2TerminalAction
function HD2ProjectileReference:terminal_action(phase) end
---@return table
function HD2ProjectileReference:describe() end

---@class HD2TerminalAction
---@field resource "player_weapon"
---@field path "terminal_action"
---@field weapon HD2WeaponName
---@field attack HD2AttackRole
---@field phase "impact"|"expiry"
local HD2TerminalAction = {}
---@return table
function HD2TerminalAction:describe() end
---@return HD2Explosion
function HD2TerminalAction:explosion() end
---@return HD2NoExplosion
function HD2TerminalAction:no_explosion() end

---@class HD2NoExplosion
---@field resource "player_weapon"
---@field path "no_explosion"
---@field weapon HD2WeaponName
---@field attack HD2AttackRole
---@field phase "impact"|"expiry"
local HD2NoExplosion = {}

---@class HD2Explosion
---@field resource "player_weapon"
---@field path "explosion"
---@field weapon HD2WeaponName
---@field attack HD2AttackRole
---@field phase "impact"|"expiry"
local HD2Explosion = {}
---@return table
function HD2Explosion:describe() end
---@return HD2Explosion
function HD2Explosion:damage() end
---@return table
function HD2Explosion:shrapnel() end

---@class HD2MagazineOption
---@field resource "player_weapon"
---@field path "magazine_option"
---@field weapon HD2WeaponName
---@field option string
local HD2MagazineOption = {}
---@return table
function HD2MagazineOption:describe() end

---@class HD2AttachmentOption
---@field resource "player_weapon"
---@field path "attachment_option"
---@field weapon HD2WeaponName
---@field category string
---@field option string
local HD2AttachmentOption = {}
---@return table
function HD2AttachmentOption:describe() end

---@alias HD2AuthoringTarget HD2Weapon|HD2DamageProfile|HD2Stratagem|HD2PlayerAttack|HD2ProjectileReference|HD2TerminalAction|HD2Explosion|HD2SupportWeapon|HD2SupportAttack|HD2SupportProjectile|HD2SupportExplosion

---@param role HD2AttackRole
---@return HD2PlayerAttack
function HD2Weapon:attack(role) end
---@return HD2PlayerAttack[]
function HD2Weapon:attacks() end
---@return table
function HD2Weapon:fire_modes() end
---@return HD2MagazineOption[]
function HD2Weapon:magazine_options() end
---@return HD2MagazineOption?
function HD2Weapon:default_magazine() end
---@param identity string
---@return HD2MagazineOption
function HD2Weapon:magazine(identity) end
---@param category string
---@return HD2AttachmentOption[]
function HD2Weapon:attachment_options(category) end
---@param category string
---@param identity string
---@return HD2AttachmentOption
function HD2Weapon:attachment(category, identity) end
---@alias HD2SupportWeaponName "40-K Meltagun"|"AC-8 Autocannon"|"APW-1 Anti-Materiel Rifle"|"ARC-3 Arc Thrower"|"B/FLAM-80 Cremator"|"B/MD C4 Pack"|"CQC-1 One True Flag"|"CQC-20 Breaching Hammer"|"CQC-72 Entrenchment Tool"|"CQC-9 Defoliation Tool"|"EAT-17 Expendable Anti-Tank"|"EAT-411 Leveller"|"EAT-700 Expendable Napalm"|"FAF-14 Spear"|"FLAM-40 Flamethrower"|"GL-21 Grenade Launcher"|"GL-28 Belt-Fed Grenade Launcher"|"GL-52 De-Escalator"|"GR-8 Recoilless Rifle"|"LAS-98 Laser Cannon"|"LAS-99 Quasar Cannon"|"M-1000 Maxigun"|"M-105 Stalwart"|"MG-206 Heavy Machine Gun"|"MG-43 Machine Gun"|"MGX-42 Bullet Storm"|"MLS-4X Commando"|"MS-11 Solo Silo"|"PLAS-45 Epoch"|"RL-77 Airburst Rocket Launcher"|"RS-422 Railgun"|"S-11 Speargun"|"SG-88 Break-Action Shotgun"|"StA-X3 W.A.S.P. Launcher"|"TX-41 Sterilizer"
---@alias HD2SupportAttackName "40-K MELTAGUN B"|"AC-8 P"|"AC-8 P IE"|"AC-8 P1"|"AC-8 P1 IE"|"AC-8 P2"|"APW-1 P"|"AR-23 P"|"ARC-3 ARC THROWER A"|"B/FLAM-80 CREMATOR S"|"B/MD C4 PACK E"|"BurningHeavy"|"CQC-1 ONE TRUE FLAG_dm"|"CQC-20 BREACHING HAMMER IE"|"CQC-20 BREACHING HAMMER_dm"|"CQC-72 ENTRENCHMENT TOOL_dm"|"CQC-9 DEFOLIATION TOOL_dm"|"EAT-17 BACKBLAST E"|"EAT-17 P"|"EAT-17 P IE"|"EAT-411 P"|"EAT-411 P IE"|"EAT-700 P"|"EAT-700 P IE"|"EAT-700 P1"|"EAT-700 P1 IE"|"FAF-14 P"|"FAF-14 P IE"|"FLAM-40 FLAMETHROWER S"|"Fire"|"Fire Panic"|"FlamerSlowed"|"GL-21 P"|"GL-21 P IE"|"GL-28 P"|"GL-28 P IE"|"GL-52 P"|"GL-52 P IE"|"GL-52 P IE A"|"GR-8 BACKBLAST E"|"GR-8 P"|"GR-8 P IE"|"GR-8 P1"|"GR-8 P1 IE"|"Gas"|"Gas Confusion"|"Gas Confusion Var2"|"Gas Var2"|"LAS-98 LASER CANNON B"|"LAS-99 P"|"LAS-99 P IE"|"M-1000 P"|"MG-206 P"|"MG-43 P"|"MGX-42 P"|"MLS-4X BACKBLAST E"|"MLS-4X P"|"MLS-4X P IE"|"P3"|"P3 IE"|"PLAS-45 EPOCH Overcharge E"|"PLAS-45 P"|"PLAS-45 P IE"|"RL-77 P"|"RL-77 P IE"|"RL-77 P1"|"RL-77 P1 IE"|"RL-77 P2"|"RL-77 P2 IE"|"RL-77 P3"|"RS-422 P"|"RS-422 RAILGUN Overcharge E"|"Railgun Max Charge"|"S-11 P"|"S-11 P E"|"SG-88 P"|"SWP SOLO SILO E"|"SWP SOLO SILO EImpact"|"StA-X3 P"|"StA-X3 P IE"|"StA-X3 P1"|"StA-X3 P1 IE"|"Stun Small"|"TX-41 STERILIZER S"|"detonation"|"feed_primary"|"impact"|"primary"|"primary_expiry"|"primary_impact"|"primary_impact_status_32"|"primary_impact_status_5"|"primary_status_37"|"primary_status_42"|"primary_status_43"|"primary_status_44"|"primary_status_45"|"primary_status_5"|"primary_status_6"|"primary_status_67"

---@class HD2SupportAttack
---@field resource "support_weapon"
---@field path "attack"|"attack_read_only"
---@field weapon HD2SupportWeaponName
---@field attack string?
---@field attack_index integer?
local HD2SupportAttack = {}
---@return table
function HD2SupportAttack:describe() end
---@return HD2SupportProjectile
function HD2SupportAttack:projectile() end
---@return HD2SupportExplosion
function HD2SupportAttack:explosion() end
---@return HD2SupportAttack
function HD2SupportAttack:damage() end

---@class HD2SupportProjectile
---@field resource "support_weapon"
---@field path "projectile_reference"
---@field weapon HD2SupportWeaponName
---@field attack string
local HD2SupportProjectile = {}
---@return table
function HD2SupportProjectile:describe() end
---@return HD2SupportProjectile
function HD2SupportProjectile:damage() end

---@class HD2SupportExplosion
---@field resource "support_weapon"
---@field path "explosion"
---@field weapon HD2SupportWeaponName
---@field attack string
local HD2SupportExplosion = {}
---@return table
function HD2SupportExplosion:describe() end
---@return HD2SupportExplosion
function HD2SupportExplosion:damage() end

---@class HD2SupportWeapon
---@field resource "support_weapon"
---@field path "weapon"
---@field weapon HD2SupportWeaponName
local HD2SupportWeapon = {}
---@return table
function HD2SupportWeapon:describe() end
---@return HD2SupportAttack[]
function HD2SupportWeapon:attacks() end
---@param identity integer|HD2SupportAttackName
---@return HD2SupportAttack
function HD2SupportWeapon:attack(identity) end
---@param identity integer|HD2SupportAttackName
---@return HD2SupportProjectile
function HD2SupportWeapon:projectile(identity) end
---@param identity integer|HD2SupportAttackName
---@return HD2SupportExplosion
function HD2SupportWeapon:explosion(identity) end

---@class HD2Fields_weapon
---@field crosshair_type "crosshair_type" APW-1 Anti-Materiel Rifle: read-only, integer
---@field base_capacity "weapon.base_capacity"
---@field capacity "weapon.capacity" Deprecated compatibility alias; use hd2.fields.magazine.capacity.
---@field player_crosshair_type "weapon.crosshair_type"
---@field default_fire_mode "weapon.default_fire_mode"
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
---@field status_strength "damage.status_strength"
---@field status_type "damage.status_type"
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

---@class HD2Fields_attack
---@field feed_alternate_projectile "attack.feed_alternate.projectile"
---@field feed_primary_projectile "attack.feed_primary.projectile"
---@field primary_projectile "attack.primary.projectile"
---@field projectile "attack.projectile"

---@class HD2Fields_beam
---@field length "beam.length"
---@field radius "beam.radius"

---@class HD2Fields_charge
---@field level_1 "charge.level_1"
---@field level_2 "charge.level_2"
---@field level_3 "charge.level_3"
---@field maximum_seconds "charge.maximum_seconds"
---@field minimum_seconds "charge.minimum_seconds"

---@class HD2Fields_explosion
---@field damage_ap_direct "explosion.damage.ap_direct"
---@field damage_ap_extreme "explosion.damage.ap_extreme"
---@field damage_ap_large "explosion.damage.ap_large"
---@field damage_ap_slight "explosion.damage.ap_slight"
---@field damage_demolition "explosion.damage.demolition"
---@field damage_durable_damage "explosion.damage.durable_damage"
---@field damage_push_force "explosion.damage.push_force"
---@field damage_stagger "explosion.damage.stagger"
---@field damage_standard_damage "explosion.damage.standard_damage"
---@field inner_radius "explosion.inner_radius"
---@field outer_radius "explosion.outer_radius"
---@field primary_impact_damage_ap_direct "explosion.primary.impact.damage.ap_direct"
---@field primary_impact_damage_ap_extreme "explosion.primary.impact.damage.ap_extreme"
---@field primary_impact_damage_ap_large "explosion.primary.impact.damage.ap_large"
---@field primary_impact_damage_ap_slight "explosion.primary.impact.damage.ap_slight"
---@field primary_impact_damage_demolition "explosion.primary.impact.damage.demolition"
---@field primary_impact_damage_durable_damage "explosion.primary.impact.damage.durable_damage"
---@field primary_impact_damage_push_force "explosion.primary.impact.damage.push_force"
---@field primary_impact_damage_stagger "explosion.primary.impact.damage.stagger"
---@field primary_impact_damage_standard_damage "explosion.primary.impact.damage.standard_damage"
---@field primary_impact_inner_radius "explosion.primary.impact.inner_radius"
---@field primary_impact_outer_radius "explosion.primary.impact.outer_radius"
---@field primary_impact_shockwave_radius "explosion.primary.impact.shockwave_radius"
---@field primary_impact_shrapnel_count "explosion.primary.impact.shrapnel_count"
---@field primary_impact_shrapnel_projectile "explosion.primary.impact.shrapnel_projectile"
---@field shockwave_radius "explosion.shockwave_radius"
---@field shrapnel_count "explosion.shrapnel_count"
---@field shrapnel_projectile "explosion.shrapnel_projectile"

---@class HD2Fields_heat
---@field capacity "heat.capacity"
---@field cool_per_second "heat.cool_per_second"
---@field cool_per_second_cold "heat.cool_per_second_cold"
---@field cool_per_second_hot "heat.cool_per_second_hot"
---@field heat_per_second "heat.heat_per_second"
---@field heat_per_shot "heat.heat_per_shot"
---@field overheat_cooldown "heat.overheat_cooldown"
---@field warmup "heat.warmup"

---@class HD2Fields_heatsink
---@field from_ammo_box "heatsink.from_ammo_box"
---@field from_supply "heatsink.from_supply"
---@field spare "heatsink.spare"
---@field starting "heatsink.starting"

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

---@class HD2Fields_status
---@field duration "status.duration"
---@field strength "status.strength"

---@class HD2Fields_terminal
---@field explosion "terminal.explosion"
---@field feed_alternate_expiry_explosion "terminal.feed_alternate.expiry.explosion"
---@field feed_alternate_impact_explosion "terminal.feed_alternate.impact.explosion"
---@field feed_primary_expiry_explosion "terminal.feed_primary.expiry.explosion"
---@field feed_primary_impact_explosion "terminal.feed_primary.impact.explosion"
---@field primary_expiry_explosion "terminal.primary.expiry.explosion"
---@field primary_impact_explosion "terminal.primary.impact.explosion"

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
---@field attack HD2Fields_attack
---@field beam HD2Fields_beam
---@field charge HD2Fields_charge
---@field explosion HD2Fields_explosion
---@field heat HD2Fields_heat
---@field heatsink HD2Fields_heatsink
---@field magazine HD2Fields_magazine
---@field rounds HD2Fields_rounds
---@field status HD2Fields_status
---@field terminal HD2Fields_terminal

---@class HD2Enum_projectile_type
---@field jar5 177

---@class HD2Enum_damage_type
---@field jar5 153
---@field orbital_laser 513

---@class HD2Enum_crosshair_type
---@field amr_original 3

---@class HD2Enum_fire_mode
---@field full_auto 1
---@field semi_auto 2

---@class HD2Enums
---@field projectile_type HD2Enum_projectile_type
---@field damage_type HD2Enum_damage_type
---@field crosshair_type HD2Enum_crosshair_type
---@field fire_mode HD2Enum_fire_mode

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
---@param name HD2SupportWeaponName
---@return HD2SupportWeapon
function hd2.support_weapon(name) end
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
---Freshly resolve and apply one reviewed scalar or typed-reference change.
---@param request HD2PatchRequest
---@return HD2Watch
function hd2.patch(request) end
---Validate every change before writing; guarded rollback on failure.
---@param request HD2TransactionRequest
---@return HD2Watch
function hd2.transaction(request) end
---Coordinate ordered semantic operations across multiple related backing objects and phases.
---@param request HD2PlanRequest
---@return HD2Watch
function hd2.plan(request) end
---Wrap exactly one patch, transaction, or composition plan. Default 60 update seconds, three-second startup, terminal conflict rejection.
---@param request HD2EnsureRequest
---@return HD2EnsureWatch
function hd2.ensure(request) end

if rawget(_G,'CowboyBingusModLoader') then
    error("HD2Runtime SDK stubs are authoring-only; install the runtime package in-game")
end
return hd2
