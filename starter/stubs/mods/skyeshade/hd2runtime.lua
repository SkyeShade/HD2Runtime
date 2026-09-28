---@meta
-- Generated authoring definitions. Never package or execute this file.
-- Schema SHA256 acf80f00deaae51e03083bb79a751e73826d69f3156b37647407296cdbe66943

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
---@field attempts? integer
---@field max_attempts? integer
---@field last_transient? string

---@class HD2EnsureWatch
---@field status string
---@field result? table
---@field error? string
---@field cancel fun()
---@field runs integer
---@field interval number
---@field id string
---@field kind string
---@field current_interval number
---@field max_interval number
---@field verifications integer
---@field drifts integer
---@field bound? boolean
---@field enabled? boolean
---@field restores? integer
---@field rebinds? integer

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
---@field value number|boolean|HD2ProjectileReference|HD2Explosion|HD2Option
---@field diagnostic? boolean
---@field allow_shared? boolean
---@field allow_unverified_effect? boolean Required only where the capability catalog names it (magazine attachments).
---@field allow_unverified_reference? boolean Required only where the capability catalog names it (vehicle mount swaps).

---@class HD2TransactionChange
---@field field string
---@field expect number|boolean|HD2ProjectileReference|HD2Explosion
---@field value number|boolean|HD2ProjectileReference|HD2Explosion|HD2Option

---@class HD2TransactionRequest
---@field id string
---@field target HD2AuthoringTarget
---@field changes HD2TransactionChange[]
---@field diagnostic? boolean
---@field allow_shared? boolean
---@field allow_unverified_effect? boolean Required only where the capability catalog names it (magazine attachments).
---@field allow_unverified_reference? boolean Required only where the capability catalog names it (vehicle mount swaps).

---@class HD2PlanTargetFrom
---@field operation string
---@field path "projectile"|"terminal.impact"|"terminal.expiry"

---@class HD2PlanOperation
---@field id string
---@field target? HD2AuthoringTarget
---@field target_from? HD2PlanTargetFrom
---@field field? string
---@field expect? number|boolean|HD2ProjectileReference|HD2Explosion
---@field value? number|boolean|HD2ProjectileReference|HD2Explosion|HD2Option
---@field changes? HD2TransactionChange[]
---@field allow_shared? boolean
---@field allow_unverified_effect? boolean Required only where the capability catalog names it (magazine attachments).
---@field allow_unverified_reference? boolean Required only where the capability catalog names it (vehicle mount swaps).

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
---@field max_interval? number
---@field enabled? HD2Option

---@class HD2RuntimeMetrics
---@field counters table<string, number>
---@field worst_seconds table<string, number>
---@field total_seconds table<string, number>
---@field timed boolean

---@class HD2OptionsRequest
---@field id string
---@field title string

---@class HD2ToggleSpec
---@field id string
---@field label string
---@field description? string
---@field gap? boolean
---@field default? boolean

---@class HD2SliderSpec
---@field id string
---@field label string
---@field description? string
---@field gap? boolean
---@field min number
---@field max number
---@field step? number
---@field default? number

---@class HD2ChoiceSpec
---@field id string
---@field label string
---@field description? string
---@field gap? boolean
---@field choices string[]
---@field values? number[]
---@field default? integer

---@class HD2Option
---@field id string
---@field kind "toggle"|"slider"|"choice"
---@field label string
---@field registered boolean
---@field source "default"|"saved"|"menu"
---@field get fun(self: HD2Option): number|boolean
---@field index fun(self: HD2Option): integer?
---@field describe fun(self: HD2Option): table
---@field state "pending"|"ready"|"unavailable"
---@field reason? string
---@field available fun(self: HD2Option): boolean

---@class HD2Options
---@field id string
---@field title string
---@field toggle fun(self: HD2Options, spec: HD2ToggleSpec): HD2Option
---@field slider fun(self: HD2Options, spec: HD2SliderSpec): HD2Option
---@field choice fun(self: HD2Options, spec: HD2ChoiceSpec): HD2Option
---@field describe fun(self: HD2Options): table

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

---@alias HD2AuthoringTarget HD2Weapon|HD2DamageProfile|HD2Stratagem|HD2StratagemAttack|HD2EagleRearm|HD2PlayerAttack|HD2ProjectileReference|HD2TerminalAction|HD2Explosion|HD2SupportWeapon|HD2SupportAttack|HD2SupportProjectile|HD2SupportExplosion|HD2DeployedEntity|HD2DeployedShield|HD2DeployedZone|HD2MountedWeapon|HD2VehicleEntity|HD2VehicleZone|HD2VehicleMount|HD2Backpack|HD2BoosterTarget|HD2WeaponAttachment

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
---@alias HD2StratagemAuthoringName "40-K Meltagun"|"A/AC-8 Autocannon Sentry"|"A/ARC-3 Tesla Tower"|"A/FLAM-40 Flame Sentry"|"A/G-16 Gatling Sentry"|"A/GM-17 Gas Mortar Sentry"|"A/LAS-98 Laser Sentry"|"A/M-12 Mortar Sentry"|"A/M-23 EMS Mortar Sentry"|"A/MG-43 Machine Gun Sentry"|"A/MLS-4X Rocket Sentry"|"AC-8 Autocannon"|"APW-1 Anti-Materiel Rifle"|"ARC-3 Arc Thrower"|"AX/AR-23 Guard Dog"|"AX/ARC-3 K-9"|"AX/FLAM-75 Hot Dog"|"AX/LAS-5 Rover"|"AX/TX-13 Dog Breath"|"B-1 Supply Pack"|"B-100 Portable Hellbomb"|"B/FLAM-80 Cremator"|"B/MD C4 Pack"|"CQC-1 One True Flag"|"CQC-20 Breaching Hammer"|"CQC-72 Entrenchment Tool"|"CQC-9 Defoliation Tool"|"E/AT-12 Anti-Tank Emplacement"|"E/GL-21 Grenadier Battlement"|"E/MG-101 HMG Emplacement"|"EAT-17 Expendable Anti-Tank"|"EAT-411 Leveller"|"EAT-700 Expendable Napalm"|"EXO-45 Patriot Exosuit"|"EXO-49 Emancipator Exosuit"|"EXO-51 Lumberer Exosuit"|"EXO-55 Breakthrough Exosuit"|"Eagle 110mm Rocket Pods"|"Eagle 500kg Bomb"|"Eagle Airstrike"|"Eagle Cluster Bomb"|"Eagle Gas Airstrike"|"Eagle Napalm Airstrike"|"Eagle Smoke Strike"|"Eagle Strafing Run"|"FAF-14 Spear"|"FLAM-40 Flamethrower"|"FX-12 Shield Generator Relay"|"GL-21 Grenade Launcher"|"GL-28 Belt-Fed Grenade Launcher"|"GL-52 De-Escalator"|"GR-8 Recoilless Rifle"|"LAS-98 Laser Cannon"|"LAS-99 Quasar Cannon"|"LIFT-182 Warp Pack"|"LIFT-850 Jump Pack"|"LIFT-860 Hover Pack"|"M-1000 Maxigun"|"M-102 Gunner FRV"|"M-103 Supply FRV"|"M-104 Incinerator FRV"|"M-105 Stalwart"|"MD-17 Anti-Tank Mines"|"MD-6 Anti-Personnel Minefield"|"MD-8 Gas Mines"|"MD-I4 Incendiary Mines"|"MG-206 Heavy Machine Gun"|"MG-43 Machine Gun"|"MGX-42 Bullet Storm"|"MLS-4X Commando"|"MS-11 Solo Silo"|"Orbital 120mm HE Barrage"|"Orbital 380mm HE Barrage"|"Orbital Airburst Strike"|"Orbital EMS Strike"|"Orbital Gas Strike"|"Orbital Gatling Barrage"|"Orbital Laser"|"Orbital Napalm Barrage"|"Orbital Precision Strike"|"Orbital Railcannon Strike"|"Orbital Smoke Strike"|"Orbital Walking Barrage"|"PLAS-45 Epoch"|"RL-77 Airburst Rocket Launcher"|"RS-422 Railgun"|"S-11 Speargun"|"SG-88 Break-Action Shotgun"|"SH-20 Ballistic Shield Backpack"|"SH-32 Shield Generator Pack"|"SH-51 Directional Shield"|"StA-X3 W.A.S.P. Launcher"|"TD-110 Maelstrom"|"TD-220 Bastion MK XVI"|"TX-41 Sterilizer"
---@alias HD2StratagemAttackRole "beam"|"beam_damage"|"delivery_1_projectile"|"delivery_1_projectile_damage"|"delivery_1_projectile_expiry"|"delivery_1_projectile_expiry_damage"|"delivery_1_projectile_expiry_shrapnel"|"delivery_1_projectile_expiry_shrapnel_damage"|"delivery_1_projectile_expiry_shrapnel_impact"|"delivery_1_projectile_expiry_shrapnel_impact_damage"|"delivery_1_projectile_impact"|"delivery_1_projectile_impact_damage"|"delivery_1_projectile_impact_damage_status_1"|"delivery_1_projectile_impact_damage_status_2"|"delivery_1_projectile_impact_shrapnel"|"delivery_1_projectile_impact_shrapnel_damage"|"delivery_1_projectile_impact_shrapnel_impact"|"delivery_1_projectile_impact_shrapnel_impact_damage"|"delivery_2_projectile"|"delivery_2_projectile_damage"|"delivery_2_projectile_impact"|"delivery_2_projectile_impact_damage"|"delivery_2_projectile_impact_damage_status_1"|"delivery_2_projectile_impact_damage_status_2"|"delivery_3_projectile"|"delivery_3_projectile_damage"|"delivery_3_projectile_impact"|"delivery_3_projectile_impact_damage"|"delivery_3_projectile_impact_damage_status_1"|"delivery_3_projectile_impact_damage_status_2"|"delivery_4_projectile"|"delivery_4_projectile_damage"|"primary"|"primary_damage"|"primary_damage_status_1"|"primary_damage_status_2"|"primary_damage_status_3"|"primary_expiry"|"primary_expiry_damage"|"primary_expiry_damage_status_1"|"primary_impact"|"primary_impact_damage"|"primary_impact_damage_status_1"|"primary_impact_damage_status_2"

---@class HD2StratagemAttack
---@field resource "stratagem"
---@field path "attack"
---@field stratagem HD2StratagemAuthoringName
---@field attack HD2StratagemAttackRole
local HD2StratagemAttack = {}
---@return table
function HD2StratagemAttack:describe() end
---@return HD2StratagemAttack
function HD2StratagemAttack:projectile() end
---@return HD2StratagemAttack
function HD2StratagemAttack:explosion() end
---@return HD2StratagemAttack
function HD2StratagemAttack:damage() end
---@return HD2StratagemAttack
function HD2StratagemAttack:status() end
---@return HD2StratagemAttack
function HD2StratagemAttack:arc() end
---@return HD2StratagemAttack
function HD2StratagemAttack:beam() end

---@class HD2MountedWeapon
---@field resource "stratagem"
---@field path "weapon"
---@field stratagem HD2StratagemAuthoringName
---@field entity string
---@field weapon string
local HD2MountedWeapon = {}
---@return table
function HD2MountedWeapon:describe() end
---@return HD2StratagemAttack[]
function HD2MountedWeapon:attacks() end
---@param role HD2StratagemAttackRole
---@return HD2StratagemAttack
function HD2MountedWeapon:attack(role) end

---@class HD2DeployedEntity
---@field resource "stratagem"
---@field path "deployed_entity"
---@field stratagem HD2StratagemAuthoringName
---@field entity string
local HD2DeployedEntity = {}
---@return table
function HD2DeployedEntity:describe() end
---@return HD2DeployedEntity
function HD2DeployedEntity:health() end
---@param identity string
---@return HD2MountedWeapon
function HD2DeployedEntity:weapon(identity) end
---@return HD2MountedWeapon[]
function HD2DeployedEntity:weapons() end
---@param role HD2StratagemAttackRole
---@return HD2StratagemAttack
function HD2DeployedEntity:attack(role) end
---@class HD2EagleRearm
---@field resource "stratagem"
---@field path "eagle_rearm"
---@field stratagem HD2StratagemAuthoringName
local HD2EagleRearm = {}
---@return table
function HD2EagleRearm:describe() end
---@param role HD2StratagemAttackRole
---@return HD2StratagemAttack
function HD2Stratagem:attack(role) end
---@return HD2StratagemAttack[]
function HD2Stratagem:attacks() end
---@return HD2EagleRearm
function HD2Stratagem:eagle_rearm() end
---@return HD2DeployedEntity
function HD2Stratagem:deployed_entity() end

---@class HD2DeployedShield
---@field resource "stratagem"
---@field path "shield"
---@field stratagem HD2StratagemAuthoringName
---@field entity string
local HD2DeployedShield = {}
---@return table
function HD2DeployedShield:describe() end

---@class HD2DeployedZone
---@field resource "stratagem"
---@field path "damage_zone"
---@field stratagem HD2StratagemAuthoringName
---@field entity string
---@field zone string
local HD2DeployedZone = {}
---@return table
function HD2DeployedZone:describe() end
---@return HD2DeployedShield
function HD2DeployedEntity:shield() end
---@return HD2DeployedZone[]
function HD2DeployedEntity:damage_zones() end
---@param zone string
---@return HD2DeployedZone
function HD2DeployedEntity:damage_zone(zone) end
---@alias HD2VehicleAuthoringName "EXO-45 Patriot Exosuit"|"EXO-49 Emancipator Exosuit"|"EXO-51 Lumberer Exosuit"|"EXO-55 Breakthrough Exosuit"|"FRV (Super Earth variant)"|"GATER Oil Rig"|"M-102 Gunner FRV"|"M-103 Supply FRV"|"M-104 Incinerator FRV"|"TD-110 Maelstrom"|"TD-220 Bastion MK XVI"
---@alias HD2BackpackName "AX/AR-23 Guard Dog"|"AX/ARC-3 K-9"|"AX/FLAM-75 Hot Dog"|"AX/LAS-5 Rover"|"AX/TX-13 Dog Breath"|"B-1 Supply Pack"|"B-100 Portable Hellbomb"|"LIFT-182 Warp Pack"|"LIFT-850 Jump Pack"|"LIFT-860 Hover Pack"|"SH-20 Ballistic Shield Backpack"|"SH-32 Shield Generator Pack"|"SH-51 Directional Shield"
---@alias HD2BoosterName "Armed Resupply Pods"|"Concealed Insertion"|"Dead Sprint"|"Experimental Infusion"|"Expert Extraction Pilot"|"Firebomb Hellpods"|"Flexible Reinforcement Budget"|"Hellpod Space Optimization"|"Increased Reinforcement Budget"|"Integrated Extinguishers"|"Localization Confusion"|"Motivational Shocks"|"Muscle Enhancement"|"Sample Extricator"|"Sample Scanner"|"Stamina Enhancement"|"Stun Pods"|"Surplus EAT Allocation"|"UAV Recon Booster"|"Vitality Enhancement"|"booster/v1/armed-resupply-pods/83bb1f9c4b71e1f6"|"booster/v1/concealed-insertion/b5b751b967a5f98c"|"booster/v1/dead-sprint/4a6e9cedb6925630"|"booster/v1/experimental-infusion/35cf8142ae307311"|"booster/v1/expert-extraction-pilot/80eb5837348c63f3"|"booster/v1/firebomb-hellpods/7ee24ab5cca7028c"|"booster/v1/flexible-reinforcement-budget/61cabf5da1dabd59"|"booster/v1/hellpod-space-optimization/7d9f3f69c2e34c24"|"booster/v1/increased-reinforcement-budget/984d134f8ced7a96"|"booster/v1/integrated-extinguishers/e28b068e7da39f57"|"booster/v1/localization-confusion/6c8fbcaca31db83b"|"booster/v1/motivational-shocks/3d33317675dd9dc6"|"booster/v1/muscle-enhancement/132b26ad07a898d8"|"booster/v1/sample-extricator/e569d43463c9676f"|"booster/v1/sample-scanner/00954fb7a554d95e"|"booster/v1/stamina-enhancement/15f9ce6b6f1cdbae"|"booster/v1/stun-pods/728b06c223c7690f"|"booster/v1/surplus-eat-allocation/cb1271359bd85dbd"|"booster/v1/uav-recon-booster/a6a3f1f6d437ba4d"|"booster/v1/vitality-enhancement/caec9d2589e2a235"
---@alias HD2MountedWeaponId "mounted-weapon/v1/assault-rifle/1e4767cc1bb3f867"|"mounted-weapon/v1/combat-walker-anti-tank-cannon/7b5046ba53f31e10"|"mounted-weapon/v1/combat-walker-autocannon-left/cb15fea8423aa2f6"|"mounted-weapon/v1/combat-walker-autocannon-right/54728c643193e559"|"mounted-weapon/v1/combat-walker-flak-cannon/84989fb7944d6bba"|"mounted-weapon/v1/combat-walker-flamethrower/61d1fb4e55fd37dd"|"mounted-weapon/v1/combat-walker-missle-launcher/b69f79ed51aeb683"|"mounted-weapon/v1/combat-walker-turret/ec85bacd57e03497"|"mounted-weapon/v1/cyborg-big-walker-turret-cannon/283e3d22cc22ef01"|"mounted-weapon/v1/cyborg-tank-turret-autocannons/c35429998ba92cea"|"mounted-weapon/v1/cyborg-tank-turret-heavycannon/68a52c55b8083bd1"|"mounted-weapon/v1/cyborg-tank-turret-rocketlauncher/bbb3a8a3de937acb"|"mounted-weapon/v1/cyborg-turret-command-bunker-hmg/c31affd2be6199f5"|"mounted-weapon/v1/drone-flamethrower-mount/4eef657729c544ac"|"mounted-weapon/v1/drone-gas-projector-mount/fa183017e162b3a1"|"mounted-weapon/v1/drone-laser-rifle-mount/d24c7f3b6e85858c"|"mounted-weapon/v1/drone-mg-weapon/473e6c3f3ecb9759"|"mounted-weapon/v1/drone-stun-gun-mount/7f06093280ceb95e"|"mounted-weapon/v1/eagle-gunpod/111e7291542a80cd"|"mounted-weapon/v1/frv-flamethrower/52eb6d862f0c81ce"|"mounted-weapon/v1/frv-mg/87956cec45a21b90"|"mounted-weapon/v1/gater-oil-rig-turret-weapon/3aba6f3418fada66"|"mounted-weapon/v1/illuminate-turret-wm-cannon-head-l/d7ec908c4f54021f"|"mounted-weapon/v1/illuminate-turret-wm-cannon-head-r/60d5f153deb23159"|"mounted-weapon/v1/laser-rifle/9c4d326f378d8900"|"mounted-weapon/v1/m-103-supply-frv-gun-weapon/34d73fd6e0ab1d96"|"mounted-weapon/v1/shuttle-gunship-turret-hmg/d6d6cd9052e6709e"|"mounted-weapon/v1/soldier-flamer/45e032b636439337"|"mounted-weapon/v1/soldier-machinegun-flm/892c5a848f371242"|"mounted-weapon/v1/soldier-machinegun/97d452fb6ecd1f68"|"mounted-weapon/v1/soldier-standard-rifle/e8e838b975071d1b"|"mounted-weapon/v1/td-110-maelstrom-attach-tank-gun-weapon/dd2241a292c7330b"|"mounted-weapon/v1/td-110-maelstrom-slot-2-weapon/3a06c77a110e70c2"|"mounted-weapon/v1/td-110-maelstrom-slot-3-weapon/605fcfcd1be790c4"|"mounted-weapon/v1/td-220-bastion-mk-xvi-attach-tank-gun-mg-weapon/10e4809cf1704447"|"mounted-weapon/v1/td-220-bastion-mk-xvi-attach-tank-gun-weapon/e90a7fd19ec0d437"|"mounted-weapon/v1/unnamed-mounted-weapon/07d8504a50bdc316"|"mounted-weapon/v1/unnamed-mounted-weapon/0d330840f4f578e9"|"mounted-weapon/v1/unnamed-mounted-weapon/101f9dd2c0400653"|"mounted-weapon/v1/unnamed-mounted-weapon/1169bac0a5ba767a"|"mounted-weapon/v1/unnamed-mounted-weapon/11f435e5587ccdd1"|"mounted-weapon/v1/unnamed-mounted-weapon/137397eea95c1013"|"mounted-weapon/v1/unnamed-mounted-weapon/1688ac3e4dad0ae9"|"mounted-weapon/v1/unnamed-mounted-weapon/1c84b8fd4f07a463"|"mounted-weapon/v1/unnamed-mounted-weapon/203c50ce98a78d3a"|"mounted-weapon/v1/unnamed-mounted-weapon/205d3f18e6c4c986"|"mounted-weapon/v1/unnamed-mounted-weapon/250541fac04090c7"|"mounted-weapon/v1/unnamed-mounted-weapon/3b994e7172991b78"|"mounted-weapon/v1/unnamed-mounted-weapon/42aa69216544be42"|"mounted-weapon/v1/unnamed-mounted-weapon/4ec9af0a2bec8e85"|"mounted-weapon/v1/unnamed-mounted-weapon/51938480ad36da5a"|"mounted-weapon/v1/unnamed-mounted-weapon/51f18fa3cecd841f"|"mounted-weapon/v1/unnamed-mounted-weapon/58ecc827279959df"|"mounted-weapon/v1/unnamed-mounted-weapon/6c4babe49fc6677f"|"mounted-weapon/v1/unnamed-mounted-weapon/6ec61849439ad1e0"|"mounted-weapon/v1/unnamed-mounted-weapon/9197edf2fc0997c2"|"mounted-weapon/v1/unnamed-mounted-weapon/94761fd626e821fd"|"mounted-weapon/v1/unnamed-mounted-weapon/978ff8e750babd67"|"mounted-weapon/v1/unnamed-mounted-weapon/988019ef8dd87d56"|"mounted-weapon/v1/unnamed-mounted-weapon/9a0b2f30b8af9705"|"mounted-weapon/v1/unnamed-mounted-weapon/9b99e436c4807091"|"mounted-weapon/v1/unnamed-mounted-weapon/a0b9d41eb561ceb4"|"mounted-weapon/v1/unnamed-mounted-weapon/a48528dbc8a9a31a"|"mounted-weapon/v1/unnamed-mounted-weapon/a983210c172b417e"|"mounted-weapon/v1/unnamed-mounted-weapon/ad0f14d262d210b8"|"mounted-weapon/v1/unnamed-mounted-weapon/ad69246a4db149f3"|"mounted-weapon/v1/unnamed-mounted-weapon/b24ebb6af42c6794"|"mounted-weapon/v1/unnamed-mounted-weapon/b587cf80343bb0d6"|"mounted-weapon/v1/unnamed-mounted-weapon/c1555e52a30c4192"|"mounted-weapon/v1/unnamed-mounted-weapon/c4c4e526a882e2b1"|"mounted-weapon/v1/unnamed-mounted-weapon/c662ee639ea4ee58"|"mounted-weapon/v1/unnamed-mounted-weapon/ceb424b0c26962b0"|"mounted-weapon/v1/unnamed-mounted-weapon/d4c0d4ac30387388"|"mounted-weapon/v1/unnamed-mounted-weapon/d6880a93a0aeef03"|"mounted-weapon/v1/unnamed-mounted-weapon/db0385a87b4a86ca"|"mounted-weapon/v1/unnamed-mounted-weapon/e20b6a72f9714d83"|"mounted-weapon/v1/unnamed-mounted-weapon/ef60119f83d4cf57"|"mounted-weapon/v1/unnamed-mounted-weapon/facc00a32715cba1"|"mounted-weapon/v1/unnamed-mounted-weapon/ffd507e9cb88f3b7"

---@class HD2VehicleEntity
---@field resource "vehicle"
---@field path "entity"
---@field vehicle HD2VehicleAuthoringName
local HD2VehicleEntity = {}
---@return table
function HD2VehicleEntity:describe() end

---@class HD2VehicleZone
---@field resource "vehicle"
---@field path "damage_zone"
---@field vehicle HD2VehicleAuthoringName
---@field zone string
local HD2VehicleZone = {}
---@return table
function HD2VehicleZone:describe() end

---@class HD2MountedWeaponIdentity
---@field semanticId HD2MountedWeaponId
---@field displayName string
---@field attackFamily string

---@class HD2VehicleMount
---@field resource "vehicle"
---@field path "mount"
---@field vehicle HD2VehicleAuthoringName
---@field mount string
local HD2VehicleMount = {}
---@return table
function HD2VehicleMount:describe() end
---@return HD2MountedWeaponIdentity?
function HD2VehicleMount:current() end
---@return HD2MountedWeaponIdentity[]
function HD2VehicleMount:candidates() end
---@param identity HD2MountedWeaponId|string
---@return HD2MountedWeaponIdentity
function HD2VehicleMount:candidate(identity) end
---@return HD2VehicleEntity
function HD2Vehicle:entity() end
---@return HD2VehicleZone[]
function HD2Vehicle:damage_zones() end
---@param zone string
---@return HD2VehicleZone
function HD2Vehicle:damage_zone(zone) end
---@return HD2VehicleMount[]
function HD2Vehicle:mounts() end
---@param mount string
---@return HD2VehicleMount
function HD2Vehicle:mount(mount) end

---@class HD2Backpack
---@field resource "backpack"
---@field path "backpack"
---@field backpack HD2BackpackName
local HD2Backpack = {}
---@return table
function HD2Backpack:describe() end

---@class HD2BoosterTarget
---@field resource "booster"
---@field path "tuning"|"explosion"|"status_effect"|"status_damage"|"granted_stratagem"|"deployed_entity"
---@field booster string
local HD2BoosterTarget = {}
---@return table
function HD2BoosterTarget:describe() end

---@class HD2Booster
---@field resource "booster"
---@field path "booster"
---@field booster string
local HD2Booster = {}
---@return table
function HD2Booster:describe() end
---Tuning scalar in the native Booster definition table of game.dll (booster-local).
---@return HD2BoosterTarget
function HD2Booster:tuning() end
---Extra hellpod-impact explosion the booster adds (ExplosionSettings and its DamageInfo).
---@return HD2BoosterTarget
function HD2Booster:explosion() end
---Status effect the booster applies (only where a native record is linked).
---@return HD2BoosterTarget
function HD2Booster:status_effect() end
---Damage of the status effect the booster applies (Dead Sprint drain).
---@return HD2BoosterTarget
function HD2Booster:status_damage() end
---Stratagem the booster grants (its native use count).
---@return HD2BoosterTarget
function HD2Booster:granted_stratagem() end
---Entity the booster deploys (only where a native record is linked).
---@return HD2BoosterTarget
function HD2Booster:deployed_entity() end
---@alias HD2MagazineAttachmentId "Jet Assisted Rifle 15mm. Drum Standard"|"Karbin Rifle Standard"|"Pistol 12x20mm. Standard"|"Pistol 9x20mm. Extended"|"Plasma Medium. Canister Extended"|"Plasma Medium. Canister Standard"|"Plasma Pistol. Canister Extended"|"Plasma Pistol. Canister Pistol"|"RIFLE 9x70mm. Extended"|"RIFLE 9x70mm. Standard"|"RIFLE Drake. Short"|"RIFLE Drake. Standard"|"RIFLE Justice. Extended"|"RIFLE Justice. Short"|"RIFLE Justice. Standard"|"Rifle 5,5x50mm. Drum"|"Rifle 5,5x50mm. Drum Carbine"|"Rifle 5,5x50mm. Extended"|"Rifle 5,5x50mm. Extended Fastreload"|"Rifle 5,5x50mm. Standard"|"Rifle 5,5x50mm. Standard Fastreload"|"Rifle 8x40mm Rifle Standard"|"SHOTGUN 12g. Drum"|"SHOTGUN 12g. Drum Light"|"SHOTGUN 12g. Magazine Extended"|"SHOTGUN 12g. Magazine Extended Light"|"SMG 12x25mm. Drum"|"SMG 12x25mm. Drum Pummeler"|"SMG 12x25mm. Extended"|"SMG 12x25mm. Extended Pummeler"|"SMG 12x25mm. Standard"|"SMG 12x25mm. Standard Pummeler"|"SMG 9x20mm. Top Mounted Extended"|"SMG 9x20mm. Top Mounted Extended Solvent"|"SMG 9x20mm. Top Mounted Standard"|"SMG 9x20mm. Top Mounted Standard Solvent"|"SMG Flamer Drum Magazine"|"SMG Flamer Extended Magazine"|"SMG Flamer Standard Magazine"|"Shotgun 12g. Magazine Standard"|"Shotgun 12g. Magazine Standard Light"|"Whisper Rifle 5,5x50mm. Drum"|"Whisper Rifle 5,5x50mm. Standard"|"weapon-attachment/v1/magazine/jet-assisted-rifle-15mm-drum-standard/d973eb6ff9b6c804"|"weapon-attachment/v1/magazine/karbin-rifle-standard/e2f9b6b1f2e8fddb"|"weapon-attachment/v1/magazine/pistol-12x20mm-standard/874261a0d16e5e00"|"weapon-attachment/v1/magazine/pistol-9x20mm-extended/98939255db31bed4"|"weapon-attachment/v1/magazine/plasma-medium-canister-extended/09729aaa96113627"|"weapon-attachment/v1/magazine/plasma-medium-canister-standard/f4fa14d4afd3ea71"|"weapon-attachment/v1/magazine/plasma-pistol-canister-extended/6ec0d8e8516cbc07"|"weapon-attachment/v1/magazine/plasma-pistol-canister-pistol/b427e5ddcd7ebe62"|"weapon-attachment/v1/magazine/rifle-5-5x50mm-drum-carbine/00618531fc7a3692"|"weapon-attachment/v1/magazine/rifle-5-5x50mm-drum/fa499a29b375c6cf"|"weapon-attachment/v1/magazine/rifle-5-5x50mm-extended-fastreload/b9d2c29a3b15b591"|"weapon-attachment/v1/magazine/rifle-5-5x50mm-extended/bfc7127000978692"|"weapon-attachment/v1/magazine/rifle-5-5x50mm-standard-fastreload/b46fd3d0a10576b9"|"weapon-attachment/v1/magazine/rifle-5-5x50mm-standard/272e4c5f18bbd39e"|"weapon-attachment/v1/magazine/rifle-8x40mm-rifle-standard/892779ea0d77aeb3"|"weapon-attachment/v1/magazine/rifle-9x70mm-extended/ac5002ad314cd5a3"|"weapon-attachment/v1/magazine/rifle-9x70mm-standard/cda05894170c4de9"|"weapon-attachment/v1/magazine/rifle-drake-short/a04c9bf6b8f34a03"|"weapon-attachment/v1/magazine/rifle-drake-standard/30c524ee2906dec4"|"weapon-attachment/v1/magazine/rifle-justice-extended/621a26851cfd19a2"|"weapon-attachment/v1/magazine/rifle-justice-short/9deab1113f78adfa"|"weapon-attachment/v1/magazine/rifle-justice-standard/c52443137e402fe8"|"weapon-attachment/v1/magazine/shotgun-12g-drum-light/6848f4e70d10b9a7"|"weapon-attachment/v1/magazine/shotgun-12g-drum/c1aeebcaa7c23988"|"weapon-attachment/v1/magazine/shotgun-12g-magazine-extended-light/ce3ad89a45cec7a2"|"weapon-attachment/v1/magazine/shotgun-12g-magazine-extended/95b6103970039345"|"weapon-attachment/v1/magazine/shotgun-12g-magazine-standard-light/6304622136df620c"|"weapon-attachment/v1/magazine/shotgun-12g-magazine-standard/f9f877be8deda58d"|"weapon-attachment/v1/magazine/smg-12x25mm-drum-pummeler/4fded5f56e190410"|"weapon-attachment/v1/magazine/smg-12x25mm-drum/568bc4a451110ca0"|"weapon-attachment/v1/magazine/smg-12x25mm-extended-pummeler/946ef6b4fae7c0de"|"weapon-attachment/v1/magazine/smg-12x25mm-extended/73a27ec123b6d632"|"weapon-attachment/v1/magazine/smg-12x25mm-standard-pummeler/ea054f1cc567db3b"|"weapon-attachment/v1/magazine/smg-12x25mm-standard/6c63bd137af2da1e"|"weapon-attachment/v1/magazine/smg-9x20mm-top-mounted-extended-solvent/11156cef840b147a"|"weapon-attachment/v1/magazine/smg-9x20mm-top-mounted-extended/176c9113b2833712"|"weapon-attachment/v1/magazine/smg-9x20mm-top-mounted-standard-solvent/80bf5c7ef57ea0e0"|"weapon-attachment/v1/magazine/smg-9x20mm-top-mounted-standard/fc9cc6afc9155eb2"|"weapon-attachment/v1/magazine/smg-flamer-drum-magazine/edd0b384b4ec7242"|"weapon-attachment/v1/magazine/smg-flamer-extended-magazine/a7609a0fd1736a11"|"weapon-attachment/v1/magazine/smg-flamer-standard-magazine/e68347c558fb8b96"|"weapon-attachment/v1/magazine/whisper-rifle-5-5x50mm-drum/dc2b49810b002079"|"weapon-attachment/v1/magazine/whisper-rifle-5-5x50mm-standard/16af29c8d0590809"

---@class HD2WeaponAttachment
---@field resource "weapon_attachment"
---@field path "magazine"
---@field attachment string
local HD2WeaponAttachment = {}
---@return table
function HD2WeaponAttachment:describe() end
---Native default and uniquely proven magazine attachments for this weapon.
---@return HD2WeaponAttachment[]
function HD2Weapon:magazine_attachments() end
---@param identity? string Catalog option name, attachment semanticId, or "default".
---@return HD2WeaponAttachment
function HD2Weapon:magazine_attachment(identity) end

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
---@field lifetime "projectile.lifetime"
---@field mass "projectile.mass"
---@field pellet_count "projectile.pellet_count"
---@field penetration_slowdown "projectile.penetration_slowdown"
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
---@field definition_cooldown "stratagem.cooldown"
---@field max_uses "stratagem.max_uses"

---@class HD2Fields_shield
---@field durability "durability" Shield Relay: reviewed writable, number
---@field radius "radius" Shield Relay: reviewed writable, number
---@field entity_radius "shield.radius"
---@field entity_durability "shield.durability"

---@class HD2Fields_payload
---@field lifetime "lifetime" Shield Relay: reviewed writable, number
---@field entity_lifetime "payload.lifetime"

---@class HD2Fields_equipment

---@class HD2Fields_recharge
---@field recharge "recharge" Jump Pack: read-only, number
---@field time "recharge.time"

---@class HD2Fields_jumppack
---@field movement_scalar_04 "movement_scalar_04" Jump Pack: read-only, number
---@field movement_scalar_24 "movement_scalar_24" Jump Pack: read-only, number
---@field vertical_launch_velocity "vertical_launch_velocity" Jump Pack: read-only, number

---@class HD2Fields_orbital
---@field interval "interval" Orbital Laser: read-only, number
---@field duration "orbital.duration"
---@field movement_speed "orbital.movement_speed"
---@field search_radius "orbital.search_radius"
---@field tick_interval "orbital.tick_interval"

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

---@class HD2Fields_reload
---@field duration "reload.duration"

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
---@field incoming_damage_scale "status.incoming_damage_scale"

---@class HD2Fields_terminal
---@field explosion "terminal.explosion"
---@field feed_alternate_expiry_explosion "terminal.feed_alternate.expiry.explosion"
---@field feed_alternate_impact_explosion "terminal.feed_alternate.impact.explosion"
---@field feed_primary_expiry_explosion "terminal.feed_primary.expiry.explosion"
---@field feed_primary_impact_explosion "terminal.feed_primary.impact.explosion"
---@field primary_expiry_explosion "terminal.primary.expiry.explosion"
---@field primary_impact_explosion "terminal.primary.impact.explosion"

---@class HD2Fields_windup
---@field wind_down_seconds "windup.wind_down_seconds"
---@field wind_up_seconds "windup.wind_up_seconds"

---@class HD2Fields_entity
---@field health "entity.health"
---@field armor "entity.armor"

---@class HD2Fields_eagle
---@field uses_per_rearm "eagle.uses_per_rearm"
---@field rearm_time "eagle.rearm_time"

---@class HD2Fields_zone
---@field armor "zone.armor"
---@field health "zone.health"
---@field affects_main_health "zone.affects_main_health"

---@class HD2Fields_jump
---@field vertical_launch_velocity "jump.vertical_launch_velocity"

---@class HD2Fields_deposit
---@field capacity "deposit.capacity"
---@field start_amount "deposit.start_amount"
---@field refill_amount "deposit.refill_amount"

---@class HD2Fields_mount
---@field weapon "mount.weapon"

---@class HD2Fields_attachment
---@field magazine_capacity "attachment.magazine_capacity"
---@field starting_magazines "attachment.starting_magazines"
---@field magazines_from_supply "attachment.magazines_from_supply"
---@field spare_magazines "attachment.spare_magazines"

---@class HD2Fields_booster
---@field damage_taken_scale "booster.damage_taken_scale"
---@field stamina_scale "booster.stamina_scale"
---@field terrain_slowdown_scale "booster.terrain_slowdown_scale"
---@field radar_range_scale "booster.radar_range_scale"
---@field reinforcements_per_player "booster.reinforcements_per_player"
---@field reinforcement_cooldown_scale "booster.reinforcement_cooldown_scale"
---@field encounter_rate_scale "booster.encounter_rate_scale"
---@field extraction_time_scale "booster.extraction_time_scale"
---@field slow_scale "booster.slow_scale"
---@field double_sample_chance "booster.double_sample_chance"
---@field health_floor "booster.health_floor"
---@field sample_drop_cap "booster.sample_drop_cap"
---@field burn_decay_bonus "booster.burn_decay_bonus"

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
---@field reload HD2Fields_reload
---@field rounds HD2Fields_rounds
---@field status HD2Fields_status
---@field terminal HD2Fields_terminal
---@field windup HD2Fields_windup
---@field entity HD2Fields_entity
---@field eagle HD2Fields_eagle
---@field zone HD2Fields_zone
---@field jump HD2Fields_jump
---@field deposit HD2Fields_deposit
---@field mount HD2Fields_mount
---@field attachment HD2Fields_attachment
---@field booster HD2Fields_booster

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
---@alias HD2VehicleName "Bastion"|"EXO-45 Patriot Exosuit"|"EXO-49 Emancipator Exosuit"|"EXO-51 Lumberer Exosuit"|"EXO-55 Breakthrough Exosuit"|"FRV (Super Earth variant)"|"GATER Oil Rig"|"M-102 Gunner FRV"|"M-103 Supply FRV"|"M-104 Incinerator FRV"|"Maelstrom"|"TD-110 Maelstrom"|"TD-220 Bastion MK XVI"|"bastion"|"maelstrom"
---@param name HD2VehicleName
---@return HD2Vehicle
function hd2.vehicle(name) end
---@alias HD2StratagemName "40-K Meltagun"|"A/AC-8 Autocannon Sentry"|"A/ARC-3 Tesla Tower"|"A/FLAM-40 Flame Sentry"|"A/G-16 Gatling Sentry"|"A/GM-17 Gas Mortar Sentry"|"A/LAS-98 Laser Sentry"|"A/M-12 Mortar Sentry"|"A/M-23 EMS Mortar Sentry"|"A/MG-43 Machine Gun Sentry"|"A/MLS-4X Rocket Sentry"|"AC-8 Autocannon"|"APW-1 Anti-Materiel Rifle"|"ARC-3 Arc Thrower"|"AX/AR-23 Guard Dog"|"AX/ARC-3 K-9"|"AX/FLAM-75 Hot Dog"|"AX/LAS-5 Rover"|"AX/TX-13 Dog Breath"|"B-1 Supply Pack"|"B-100 Portable Hellbomb"|"B/FLAM-80 Cremator"|"B/MD C4 Pack"|"CQC-1 One True Flag"|"CQC-20 Breaching Hammer"|"CQC-72 Entrenchment Tool"|"CQC-9 Defoliation Tool"|"E/AT-12 Anti-Tank Emplacement"|"E/GL-21 Grenadier Battlement"|"E/MG-101 HMG Emplacement"|"EAT-17 Expendable Anti-Tank"|"EAT-411 Leveller"|"EAT-700 Expendable Napalm"|"EXO-45 Patriot Exosuit"|"EXO-49 Emancipator Exosuit"|"EXO-51 Lumberer Exosuit"|"EXO-55 Breakthrough Exosuit"|"Eagle 110mm Rocket Pods"|"Eagle 500kg Bomb"|"Eagle Airstrike"|"Eagle Cluster Bomb"|"Eagle Gas Airstrike"|"Eagle Napalm Airstrike"|"Eagle Smoke Strike"|"Eagle Strafing Run"|"FAF-14 Spear"|"FLAM-40 Flamethrower"|"FX-12 Shield Generator Relay"|"GL-21 Grenade Launcher"|"GL-28 Belt-Fed Grenade Launcher"|"GL-52 De-Escalator"|"GR-8 Recoilless Rifle"|"LAS-98 Laser Cannon"|"LAS-99 Quasar Cannon"|"LIFT-182 Warp Pack"|"LIFT-850 Jump Pack"|"LIFT-860 Hover Pack"|"M-1000 Maxigun"|"M-102 Gunner FRV"|"M-103 Supply FRV"|"M-104 Incinerator FRV"|"M-105 Stalwart"|"MD-17 Anti-Tank Mines"|"MD-6 Anti-Personnel Minefield"|"MD-8 Gas Mines"|"MD-I4 Incendiary Mines"|"MG-206 Heavy Machine Gun"|"MG-43 Machine Gun"|"MGX-42 Bullet Storm"|"MLS-4X Commando"|"MS-11 Solo Silo"|"Orbital 120mm HE Barrage"|"Orbital 380mm HE Barrage"|"Orbital Airburst Strike"|"Orbital EMS Strike"|"Orbital Gas Strike"|"Orbital Gatling Barrage"|"Orbital Laser"|"Orbital Napalm Barrage"|"Orbital Precision Strike"|"Orbital Railcannon Strike"|"Orbital Smoke Strike"|"Orbital Walking Barrage"|"PLAS-45 Epoch"|"RL-77 Airburst Rocket Launcher"|"RS-422 Railgun"|"S-11 Speargun"|"SG-88 Break-Action Shotgun"|"SH-20 Ballistic Shield Backpack"|"SH-32 Shield Generator Pack"|"SH-51 Directional Shield"|"Shield Relay"|"StA-X3 W.A.S.P. Launcher"|"TD-110 Maelstrom"|"TD-220 Bastion MK XVI"|"TX-41 Sterilizer"|"orbital_laser"|"shield_relay"
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
---@param name HD2BackpackName
---@return HD2Backpack
function hd2.backpack(name) end
---@param name HD2BoosterName
---@return HD2Booster
function hd2.booster(name) end
---@param identity HD2MagazineAttachmentId
---@return HD2WeaponAttachment
function hd2.weapon_attachment(identity) end
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
---Freshly resolve and apply one reviewed scalar or typed-reference change. Option handles require hd2.ensure.
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
---Wrap exactly one patch, transaction, or composition plan. The first run is fully guarded; afterwards only the applied target bytes are re-checked, backing off from interval (default 60 s) to max_interval (default 600 s). Drift triggers the full guarded path again; conflicts are terminal. Each guarded run retries transient not-ready failures up to 6 attempts, 5 s apart. An option handle as a field value, or an enabled toggle, makes the ensure follow in-game options. It waits until the options are available (status waiting_for_options) and stays inactive (status unavailable) if they are not; each applied change re-runs the full guarded validation and write for the same operation; disabling restores the reviewed baseline through the same guards.
---@param request HD2EnsureRequest
---@return HD2EnsureWatch
function hd2.ensure(request) end
---Process-wide counters (scans, lookups, hashes, writes, verifications, scheduler ticks) and worst durations for performance audits.
---@return HD2RuntimeMetrics
function hd2.metrics() end
---Declare an in-game options page (a MODS tab category). CowboyBingus Mod Options Menu v1+ (needs Bingus Shared Loader v18+) is an optional dependency of mods that use this: without it, or if it is incompatible or rejects an option, one warning is logged and every hd2.ensure bound to those options stays inactive for the session. Defaults are never applied silently. Mods that do not call hd2.options are unaffected.
---@param spec HD2OptionsRequest
---@return HD2Options
function hd2.options(spec) end

if rawget(_G,'CowboyBingusModLoader') then
    error("HD2Runtime SDK stubs are authoring-only; install the runtime package in-game")
end
return hd2
