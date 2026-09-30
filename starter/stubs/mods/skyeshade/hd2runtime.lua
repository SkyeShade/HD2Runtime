---@meta
-- Generated authoring definitions. Never package or execute this file.
-- Schema SHA256 e71af8e98862e03ed007e330d5db5e5bf1b9e4f56fe68a7aa8a3aea752b744e5

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
---@field option_defaults? boolean

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
---@field label? string
---@field context? table<string, string|number|boolean>
---@field expected? {process_id?: integer, exe_sha?: string, dll_sha?: string, exe_base?: integer, dll_base?: integer}
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
---@field fallback? "default"|"disable"

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

---@class HD2AssetRequest
---@field id string
---@field target? table
---@field targets? table[]

---@class HD2AssetDependency
---@field known boolean
---@field autoLoadSupported boolean
---@field key? string
---@field derivation? string
---@field package? string
---@field retain? string
---@field liveTested? boolean
---@field blocker? string

---@class HD2SnapshotControlRequest
---@field control_directory? string
---@field output_directory? string

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
---The output this attack emits, by native family (see sdk/AttackOutputCapabilities.json).
---@return HD2AttackOutput
function HD2PlayerAttack:output() end
---Where this attack's fired projectile lives: status (ACTIVE_DIRECT, INDIRECT, AMBIGUOUS, BLOCKED),
---mechanism, reason and, when writable, the target, field and expect handle that change it.
---@return HD2ProjectileSource
function HD2PlayerAttack:projectile_source() end

---@class HD2ProjectileSource
---@field weapon HD2WeaponName
---@field attack HD2AttackRole
---@field status "ACTIVE_DIRECT"|"INDIRECT"|"DORMANT_OR_METADATA"|"AMBIGUOUS"|"BLOCKED"
---@field mechanism "component"|"ammunition"|nil
---@field member string
---@field reason string
---@field writable boolean True only where changing field on target changes the fired projectile.
---@field target HD2PlayerAttack|HD2WeaponAmmunition|nil
---@field field string|nil
---@field expect HD2ProjectileReference|HD2AmmunitionProjectile|nil
---@field acknowledgements string[]|nil
local HD2ProjectileSource = {}

---@class HD2WeaponAmmunition
---@field resource "player_weapon"
---@field path "ammunition"
---@field weapon HD2WeaponName
local HD2WeaponAmmunition = {}
---The ammunition projectile handle: the expect of hd2.fields.ammunition.projectile, and the value that
---restores the reviewed ammunition projectile.
---@return HD2AmmunitionProjectile
function HD2WeaponAmmunition:projectile() end
---@return table
function HD2WeaponAmmunition:describe() end

---@class HD2AmmunitionProjectile
---@field resource "player_weapon"
---@field path "ammunition_projectile"
---@field weapon HD2WeaponName
local HD2AmmunitionProjectile = {}
---@return table
function HD2AmmunitionProjectile:describe() end

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

---@alias HD2AuthoringTarget HD2Weapon|HD2DamageProfile|HD2Stratagem|HD2StratagemAttack|HD2EagleRearm|HD2PlayerAttack|HD2WeaponAmmunition|HD2ProjectileReference|HD2TerminalAction|HD2Explosion|HD2SupportWeapon|HD2SupportAttack|HD2SupportProjectile|HD2SupportExplosion|HD2DeployedEntity|HD2DeployedShield|HD2DeployedZone|HD2MountedWeapon|HD2VehicleEntity|HD2VehicleZone|HD2VehicleMount|HD2VehicleWeapon|HD2VehicleWeaponAttack|HD2Backpack|HD2BackpackZone|HD2BoosterTarget|HD2WeaponAttachment|HD2PodRack|HD2PodSlot

---@param role HD2AttackRole
---@return HD2PlayerAttack
function HD2Weapon:attack(role) end
---The default ammunition that owns this weapon's fired projectile (its delta patches ProjectileWeapon +0
---when the weapon is built). Only weapons whose projectile_source() is INDIRECT; write it with
---hd2.fields.ammunition.projectile, allow_shared=true and allow_unverified_effect=true.
---@return HD2WeaponAmmunition
function HD2Weapon:ammunition() end
---@param role? HD2AttackRole Defaults to "primary".
---@return HD2ProjectileSource
function HD2Weapon:projectile_source(role) end
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

---@class HD2FireRateMode
---@field slot "x"|"y"|"z" The native slot
---@field index integer Storage position (x = 1, y = 2, z = 3): the position in hd2.fields.fire_rate.modes
---@field rpm number 0 = no mode in this slot
---@field enabled boolean rpm is not 0
---@field default boolean The Y slot: the rate a weapon is built on (weapon.fire_rate)
---@field menu integer? Position in the weapon menu (filled slots, X, Y, Z order)
---@field presses integer? Selector presses from the default (0 = the default)

---@class HD2FireRateModes
---@field weapon string
---@field state "selectable"|"addable"|"single_rate"|"blocked"|"absent"
---@field modes HD2FireRateMode[] The filled slots in weapon-menu order (X, Y, Z)
---@field slots HD2FireRateMode[] All three slots in storage order
---@field default HD2FireRateMode The Y slot
---@field selectorOrder string[] The filled slots in the order the selector visits them (from y)
---@field maxModes integer At most 3: the native storage
---@field expect number[] {X, Y, Z}: the expect of hd2.fields.fire_rate.modes
---@field selector table {bound, input, bindableInputs, order}
---@field binding table? {field, expect, value}: the weapon_function change a selector-less weapon adds with 2+ rates
---@field writable boolean
---@field reason string?

---The native rates of fire: three slots {X, Y, Z}, the order the weapon menu lists them. A weapon is built on
---Y and each selector press moves Y -> Z -> X, skipping empty (0) slots. Write them with
---hd2.fields.fire_rate.modes (allow_unverified_effect=true); weapons without a selector add one with the
---returned binding in the same transaction.
---@return HD2FireRateModes
function HD2Weapon:fire_rate_modes() end
---@param mode integer|"x"|"y"|"z" Menu position or slot
---@return HD2FireRateMode
function HD2Weapon:fire_rate_mode(mode) end

---@class HD2Feed
---@field resource "player_weapon"|"support_weapon"
---@field path "feed"
---@field weapon string
---@field feed "primary"|"alternate"|"programmable"
local HD2Feed = {}
---mechanism (projectile, rounds_magazine, programmable_ammo), selector, capacity field, writability.
---@return table
function HD2Feed:describe() end
---The projectile this feed fires: its projectile/damage fields for projectile and rounds feeds, the
---restore handle of a native programmable projectile.
---@return HD2ProjectileReference|table
function HD2Feed:projectile() end
---Where the feed projectile is written: {target, field, expect, binding?, acknowledgements, writable}.
---@return table
function HD2Feed:source() end
---Selectable ammunition/output sources: the normal projectile or two rounds magazines, then a
---ProgrammableAmmo projectile (hd2.fields.function_ammo.projectile).
---@return HD2Feed[]
function HD2Weapon:feeds() end
---@param id "primary"|"alternate"|"programmable"|integer
---@return HD2Feed
function HD2Weapon:feed(id) end
---The armory trait labels: {traits, armorPenetration, choices, writable, reason}; presentation only.
---Write hd2.fields.presentation.armor_penetration or hd2.fields.presentation.traits.
---@return table
function HD2Weapon:presentation() end
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
---@return HD2AttackOutput
function HD2SupportAttack:output() end

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
---The backpack that stores this weapon's ammunition (backpack-fed weapons only).
---@return HD2Backpack
function HD2SupportWeapon:backpack() end
---@return table
function HD2SupportWeapon:fire_modes() end
---@return HD2FireRateModes
function HD2SupportWeapon:fire_rate_modes() end
---@param mode integer|"x"|"y"|"z" Menu position or slot
---@return HD2FireRateMode
function HD2SupportWeapon:fire_rate_mode(mode) end
---@return HD2Feed[]
function HD2SupportWeapon:feeds() end
---@param id "primary"|"alternate"|"programmable"|integer
---@return HD2Feed
function HD2SupportWeapon:feed(id) end
---@return table
function HD2SupportWeapon:presentation() end
---@alias HD2StratagemAuthoringName "40-K Meltagun"|"A/AC-8 Autocannon Sentry"|"A/ARC-3 Tesla Tower"|"A/FLAM-40 Flame Sentry"|"A/G-16 Gatling Sentry"|"A/GM-17 Gas Mortar Sentry"|"A/LAS-98 Laser Sentry"|"A/M-12 Mortar Sentry"|"A/M-23 EMS Mortar Sentry"|"A/MG-43 Machine Gun Sentry"|"A/MLS-4X Rocket Sentry"|"AC-8 Autocannon"|"APW-1 Anti-Materiel Rifle"|"ARC-3 Arc Thrower"|"AX/AR-23 Guard Dog"|"AX/ARC-3 K-9"|"AX/FLAM-75 Hot Dog"|"AX/LAS-5 Rover"|"AX/TX-13 Dog Breath"|"B-1 Supply Pack"|"B-100 Portable Hellbomb"|"B/FLAM-80 Cremator"|"B/MD C4 Pack"|"CQC-1 One True Flag"|"CQC-20 Breaching Hammer"|"CQC-72 Entrenchment Tool"|"CQC-9 Defoliation Tool"|"E/AT-12 Anti-Tank Emplacement"|"E/GL-21 Grenadier Battlement"|"E/MG-101 HMG Emplacement"|"EAT-17 Expendable Anti-Tank"|"EAT-411 Leveller"|"EAT-700 Expendable Napalm"|"EXO-45 Patriot Exosuit"|"EXO-49 Emancipator Exosuit"|"EXO-51 Lumberer Exosuit"|"EXO-55 Breakthrough Exosuit"|"Eagle 110mm Rocket Pods"|"Eagle 500kg Bomb"|"Eagle Airstrike"|"Eagle Cluster Bomb"|"Eagle Gas Airstrike"|"Eagle Napalm Airstrike"|"Eagle Smoke Strike"|"Eagle Strafing Run"|"FAF-14 Spear"|"FLAM-40 Flamethrower"|"FX-12 Shield Generator Relay"|"GL-21 Grenade Launcher"|"GL-28 Belt-Fed Grenade Launcher"|"GL-52 De-Escalator"|"GR-8 Recoilless Rifle"|"LAS-98 Laser Cannon"|"LAS-99 Quasar Cannon"|"LIFT-182 Warp Pack"|"LIFT-850 Jump Pack"|"LIFT-860 Hover Pack"|"M-1000 Maxigun"|"M-102 Gunner FRV"|"M-103 Supply FRV"|"M-104 Incinerator FRV"|"M-105 Stalwart"|"MD-17 Anti-Tank Mines"|"MD-6 Anti-Personnel Minefield"|"MD-8 Gas Mines"|"MD-I4 Incendiary Mines"|"MG-206 Heavy Machine Gun"|"MG-43 Machine Gun"|"MGX-42 Bullet Storm"|"MLS-4X Commando"|"MS-11 Solo Silo"|"Orbital 120mm HE Barrage"|"Orbital 380mm HE Barrage"|"Orbital Airburst Strike"|"Orbital EMS Strike"|"Orbital Gas Strike"|"Orbital Gatling Barrage"|"Orbital Laser"|"Orbital Napalm Barrage"|"Orbital Precision Strike"|"Orbital Railcannon Strike"|"Orbital Smoke Strike"|"Orbital Walking Barrage"|"PLAS-45 Epoch"|"RL-77 Airburst Rocket Launcher"|"RS-422 Railgun"|"Resupply"|"S-11 Speargun"|"SG-88 Break-Action Shotgun"|"SH-20 Ballistic Shield Backpack"|"SH-32 Shield Generator Pack"|"SH-51 Directional Shield"|"StA-X3 W.A.S.P. Launcher"|"TD-110 Maelstrom"|"TD-220 Bastion MK XVI"|"TX-41 Sterilizer"
---@alias HD2StratagemAttackRole "beam"|"beam_damage"|"delivery_1_projectile"|"delivery_1_projectile_damage"|"delivery_1_projectile_expiry"|"delivery_1_projectile_expiry_damage"|"delivery_1_projectile_expiry_shrapnel"|"delivery_1_projectile_expiry_shrapnel_damage"|"delivery_1_projectile_expiry_shrapnel_impact"|"delivery_1_projectile_expiry_shrapnel_impact_damage"|"delivery_1_projectile_impact"|"delivery_1_projectile_impact_damage"|"delivery_1_projectile_impact_damage_status_1"|"delivery_1_projectile_impact_damage_status_2"|"delivery_1_projectile_impact_shrapnel"|"delivery_1_projectile_impact_shrapnel_damage"|"delivery_1_projectile_impact_shrapnel_impact"|"delivery_1_projectile_impact_shrapnel_impact_damage"|"delivery_2_projectile"|"delivery_2_projectile_damage"|"delivery_2_projectile_impact"|"delivery_2_projectile_impact_damage"|"delivery_2_projectile_impact_damage_status_1"|"delivery_2_projectile_impact_damage_status_2"|"delivery_3_projectile"|"delivery_3_projectile_damage"|"delivery_3_projectile_impact"|"delivery_3_projectile_impact_damage"|"delivery_3_projectile_impact_damage_status_1"|"delivery_3_projectile_impact_damage_status_2"|"delivery_4_projectile"|"delivery_4_projectile_damage"|"mine"|"mine_damage"|"mine_damage_status_1"|"mine_damage_status_2"|"primary"|"primary_damage"|"primary_damage_status_1"|"primary_damage_status_2"|"primary_damage_status_3"|"primary_expiry"|"primary_expiry_damage"|"primary_expiry_damage_status_1"|"primary_impact"|"primary_impact_damage"|"primary_impact_damage_status_1"|"primary_impact_damage_status_2"

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
---The deployed mines' explosion of a mine stratagem (attack role "mine"; see docs/stratagem-authoring.md).
---@return HD2StratagemAttack
function HD2Stratagem:mine() end
---@return HD2DeployedEntity
function HD2Stratagem:deployed_entity() end
---The drop pod this call-in delivers.
---@return HD2PodDelivery
function HD2Stratagem:delivery() end
---@return HD2PodRack
function HD2Stratagem:payload() end

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

---@class HD2DeployedTurret
---@field resource "stratagem"
---@field path "turret"
local HD2DeployedTurret = {}
---Sentry turret motion: turret.yaw_speed/pitch_speed (degrees per second) and pitch_min/pitch_max/
---yaw_min/yaw_max (degrees). Writes require allow_unverified_effect=true.
---@return table
function HD2DeployedTurret:describe() end
---@return HD2DeployedTurret
function HD2DeployedEntity:turret() end

---@class HD2DeployedTargeting
---@field resource "stratagem"
---@field path "targeting"
local HD2DeployedTargeting = {}
---Sentry target acquisition: targeting.range (meters). Writes require allow_unverified_effect=true.
---@return table
function HD2DeployedTargeting:describe() end
---@return HD2DeployedTargeting
function HD2DeployedEntity:targeting() end

---@class HD2DeployedMinefield
---@field resource "stratagem"
---@field path "minefield"
local HD2DeployedMinefield = {}
---Mine deployer counts: minefield.salvos and minefield.mines_per_salvo (reductions only; one launch socket
---per mine). Writes require allow_unverified_effect=true.
---@return table
function HD2DeployedMinefield:describe() end
---@return HD2DeployedMinefield
function HD2DeployedEntity:minefield() end
---@return HD2DeployedZone[]
function HD2DeployedEntity:damage_zones() end
---@param zone string
---@return HD2DeployedZone
function HD2DeployedEntity:damage_zone(zone) end
---@alias HD2VehicleAuthoringName "EXO-45 Patriot Exosuit"|"EXO-49 Emancipator Exosuit"|"EXO-51 Lumberer Exosuit"|"EXO-55 Breakthrough Exosuit"|"FRV (Super Earth variant)"|"GATER Oil Rig"|"M-102 Gunner FRV"|"M-103 Supply FRV"|"M-104 Incinerator FRV"|"TD-110 Maelstrom"|"TD-220 Bastion MK XVI"
---@alias HD2BackpackName "AX/AR-23 Guard Dog"|"AX/ARC-3 K-9"|"AX/FLAM-75 Hot Dog"|"AX/LAS-5 Rover"|"AX/TX-13 Dog Breath"|"B-1 Supply Pack"|"B-100 Portable Hellbomb"|"B/FLAM-80 Cremator Backpack"|"GL-28 Belt-Fed Grenade Launcher Backpack"|"LIFT-182 Warp Pack"|"LIFT-850 Jump Pack"|"LIFT-860 Hover Pack"|"M-1000 Maxigun Backpack"|"SH-20 Ballistic Shield Backpack"|"SH-32 Shield Generator Pack"|"SH-51 Directional Shield"
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

---@class HD2VehicleWeapon
---@field resource "vehicle_weapon"
---@field path "weapon"
---@field weapon string
local HD2VehicleWeapon = {}
---@return table
function HD2VehicleWeapon:describe() end
---@return HD2VehicleWeaponAttack[]
function HD2VehicleWeapon:attacks() end
---@param role string
---@return HD2VehicleWeaponAttack
function HD2VehicleWeapon:attack(role) end
---@return HD2VehicleWeaponAttack
function HD2VehicleWeapon:projectile() end
---@param phase? "impact"
---@return HD2VehicleWeaponAttack
function HD2VehicleWeapon:explosion(phase) end

---@class HD2VehicleWeaponAttack
---@field resource "vehicle_weapon"
---@field path "projectile_reference"|"explosion"|"attack"
---@field weapon string
---@field attack string
local HD2VehicleWeaponAttack = {}
---@return table
function HD2VehicleWeaponAttack:describe() end
---@return HD2VehicleWeapon[]
function HD2Vehicle:weapons() end
---@param identity integer|string mount slot, mount label, weapon key or semanticId
---@return HD2VehicleWeapon
function HD2Vehicle:weapon(identity) end
---@return HD2VehicleWeapon
function HD2VehicleMount:weapon() end

---@class HD2Backpack
---@field resource "backpack"
---@field path "backpack"
---@field backpack HD2BackpackName
local HD2Backpack = {}
---@return table
function HD2Backpack:describe() end
---The support weapon whose ammunition this backpack stores (weapon-fed backpacks only).
---@return HD2SupportWeapon
function HD2Backpack:weapon() end
---Reviewed damage zones (the SH-20 Ballistic Shield's "shield" plate zone).
---@return HD2BackpackZone[]
function HD2Backpack:damage_zones() end
---@param identity string|integer Zone id ("zone_0"), native zone name ("shield") or index.
---@return HD2BackpackZone
function HD2Backpack:damage_zone(identity) end

---@class HD2BackpackZone
---@field resource "backpack"
---@field path "damage_zone"
---@field backpack HD2BackpackName
---@field zone string
local HD2BackpackZone = {}
---zone.armor: the armor every hit on the zone uses (copied into a backpack entity when it spawns).
---@return table
function HD2BackpackZone:describe() end

---@class HD2BoosterTarget
---@field resource "booster"
---@field path "tuning"|"explosion"|"status_effect"|"status_damage"|"granted_stratagem"|"deployed_entity"
---@field booster string
local HD2BoosterTarget = {}
---@return table
function HD2BoosterTarget:describe() end
---Granted-stratagem targets only: the drop pod the granted stratagem delivers.
---@return HD2PodDelivery
function HD2BoosterTarget:delivery() end
---@return HD2PodRack
function HD2BoosterTarget:payload() end

---@class HD2PodDelivery
local HD2PodDelivery = {}
---@return HD2PodRack
function HD2PodDelivery:rack() end

---@class HD2PodRack
---@field resource "pod_rack"
---@field rack string
---@field path "rack"
local HD2PodRack = {}
---@return table
function HD2PodRack:describe() end
---@return HD2PodSlot[]
function HD2PodRack:slots() end
---@param number integer
---@return HD2PodSlot
function HD2PodRack:slot(number) end

---@class HD2PodSlot
---@field resource "pod_rack"
---@field rack string
---@field path "slot"
---@field slot integer
local HD2PodSlot = {}
---@return table
function HD2PodSlot:describe() end
---@return HD2Pickup|"empty"
function HD2PodSlot:current() end

---@class HD2Pickup
---@field resource "pickup"
---@field semanticId string
---@field name string
---@field category "support_weapon"|"backpack"|"ammo"|"stim"|"grenade"|"supply"
local HD2Pickup = {}
---@return table
function HD2Pickup:describe() end

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
---@alias HD2ThrowableName "G-10 Incendiary"|"G-109 Urchin"|"G-12 High Explosive"|"G-123 Thermite"|"G-13 Incendiary Impact"|"G-142 Pyrotech"|"G-16 Impact"|"G-23 Stun"|"G-3 Smoke"|"G-31 Arc"|"G-4 Gas"|"G-48 Giga Grenade"|"G-50 Seeker"|"G-6 Frag"|"G-60 Anti-Tank Seeker"|"G-7 Pineapple"|"G-8 Immolation"|"G-89 Smokescreen"|"G/40-K Melta Mine"|"G/SH-39 Shield"|"K-2 Throwing Knife"|"TED-63 Dynamite"|"TM-1 Lure Mine"|"throwable/v1/g-10-incendiary/1736e97d6edcce61"|"throwable/v1/g-109-urchin/1b511603e8da0354"|"throwable/v1/g-12-high-explosive/06eb3c818c823a96"|"throwable/v1/g-123-thermite/c2843f536cd7ad03"|"throwable/v1/g-13-incendiary-impact/15c4018f5a498687"|"throwable/v1/g-142-pyrotech/19647eadec46d6b8"|"throwable/v1/g-16-impact/9952735c29489c3e"|"throwable/v1/g-23-stun/058fac8f4d537dae"|"throwable/v1/g-3-smoke/ef4294e861d5d0aa"|"throwable/v1/g-31-arc/be684f24ecf5d82f"|"throwable/v1/g-4-gas/6b51845f7fe757ab"|"throwable/v1/g-40-k-melta-mine/0c5f1fb8cf91b5e6"|"throwable/v1/g-48-giga-grenade/85247d69b2820aa3"|"throwable/v1/g-50-seeker/4047998b4bd1a60b"|"throwable/v1/g-6-frag/f1e3b7ef6de8ab93"|"throwable/v1/g-60-anti-tank-seeker/5effccd40935511d"|"throwable/v1/g-7-pineapple/49b9f7e3894f382a"|"throwable/v1/g-8-immolation/d3eac31d7fb9efc6"|"throwable/v1/g-89-smokescreen/3c0123a31c2d9bfe"|"throwable/v1/g-sh-39-shield/48ef1fee1ed7957d"|"throwable/v1/k-2-throwing-knife/13af85feaa1ac06b"|"throwable/v1/ted-63-dynamite/af7d55bacbde8482"|"throwable/v1/tm-1-lure-mine/2a5ba3fcf9044b31"

---@class HD2ThrowableTarget
---@field resource "throwable"
---@field path "detonation"|"explosion"|"status_effect"|"shrapnel"|"bomblets"|"bomblet_explosion"|"damage"|"entity"|"shield"
---@field throwable string
---@field status? string
local HD2ThrowableTarget = {}
---@return table
function HD2ThrowableTarget:describe() end
---Explosion targets: a status effect its DamageInfo applies (label such as "fire", or slot number).
---@param identity string|integer
---@return HD2ThrowableTarget
function HD2ThrowableTarget:status_effect(identity) end
---@return HD2ThrowableTarget[]
function HD2ThrowableTarget:status_effects() end
---Explosion targets: the shrapnel projectile the explosion spawns.
---@return HD2ThrowableTarget
function HD2ThrowableTarget:shrapnel() end
---Explosion targets: the bomblet projectile the explosion spawns.
---@return HD2ThrowableTarget
function HD2ThrowableTarget:bomblets() end
---Bomblet targets: the explosion each bomblet makes on impact/expiry.
---@return HD2ThrowableTarget
function HD2ThrowableTarget:explosion() end

---@class HD2Throwable
---@field resource "throwable"
---@field path "throwable"
---@field throwable string
local HD2Throwable = {}
---Inventory counts (ThrowableComponent) and identity.
---@return table
function HD2Throwable:describe() end
---Fuse / detonation (ExplosiveComponent), where the throwable explodes.
---@return HD2ThrowableTarget
function HD2Throwable:detonation() end
---The explosion (ExplosionSettings and its DamageInfo).
---@return HD2ThrowableTarget
function HD2Throwable:explosion() end
---@param identity string|integer
---@return HD2ThrowableTarget
function HD2Throwable:status_effect(identity) end
---@return HD2ThrowableTarget[]
function HD2Throwable:status_effects() end
---Shrapnel projectile (e.g. G-6 Frag, TM-1 Lure Mine). Shared with other sources.
---@return HD2ThrowableTarget
function HD2Throwable:shrapnel() end
---Bomblet projectile (G-7 Pineapple); :explosion() reaches the explosion of each bomblet.
---@return HD2ThrowableTarget
function HD2Throwable:bomblets() end
---Direct-hit damage (K-2 Throwing Knife; no explosion).
---@return HD2ThrowableTarget
function HD2Throwable:damage() end
---Health of the deployed entity (mines).
---@return HD2ThrowableTarget
function HD2Throwable:entity() end
---Shield of the deployed entity (G/SH-39 Shield).
---@return HD2ThrowableTarget
function HD2Throwable:shield() end
---@alias HD2EnemyName "Bile Titan"|"Charger"|"Crusher"|"Dropship"|"Fleshmob"|"Gatekeeper"|"Gunship"|"Hive Guard"|"Impaler"|"Marauder"|"Predator Hunter"|"Rupture Charger"|"Rupture Spewer"|"Spore Burst Bile Titan"|"Spore Burst Hunter"|"Spore Burst Warrior"|"Spore Charger"|"Stalker"|"Veracitor"|"Watcher"|"assault_walker"|"beamer_champion"|"berserker"|"berserker_iron_fleet"|"berserker_ivory_legion"|"berserker_jumppack"|"big_walker_turret_cannon"|"bodyhorror_bladed"|"bodyhorror_helmetguy"|"boomer"|"boomer_burrower"|"boomer_nurser"|"boomer_nurser_mission"|"boomer_tier_2"|"cha_soldier.cha_soldier_jumppack"|"charger"|"charger_acid"|"charger_bull"|"charger_burrower"|"charger_tier2"|"conscript_backpack_lmg"|"conscript_base"|"conscript_commander"|"conscript_commander_jump"|"conscript_elite"|"conscript_flamer"|"conscript_ivory_legion"|"conscript_ivory_legion_tier_2"|"conscript_jump"|"conscript_jump_melee"|"conscript_jumppack"|"conscript_melee"|"conscript_scout"|"conscript_scout_walker_rider"|"conscript_shotgun"|"conscript_tier_1"|"conscript_tier_2"|"conscript_tier_3"|"corrupted"|"corrupted_v2"|"corrupted_v3"|"cyborg_elite"|"cyborg_elite_female"|"cyborg_elite_rusher"|"cyborg_elite_rusher_female"|"dragon"|"dropship"|"equipment.backpacks.soldier_jumppack.soldier_jumppack"|"exomech_melee"|"exomech_ranged"|"gunship"|"hexagon_shield"|"hive_lord"|"hunter_base"|"hunter_gloom"|"hunter_tier_1"|"hunter_tier_2"|"hunter_tier_3"|"illuminate_attack_ship"|"illuminate_dropship"|"illuminate_guy_staff"|"illuminate_guy_staff_fake"|"illuminate_guy_staff_tier_2"|"illuminate_turret_wm_cannon"|"illuminate_turret_wm_cannon_head_l"|"illuminate_turret_wm_cannon_head_r"|"illuminate_war_machine"|"illuminate_warmachine_bombball"|"impaler"|"impaler_tentacle"|"jet_champion"|"lieutenant_artillery"|"lieutenant_assault"|"lieutenant_base"|"lieutenant_flag"|"lieutenant_flag_ivory_legion"|"lieutenant_ivory_legion"|"lieutenant_ivory_legion_assault"|"lieutenant_jetpack"|"lieutenant_suppressor"|"meatglue"|"observer"|"scavenger_base"|"scavenger_gloom"|"scavenger_predator"|"scavenger_spitter"|"scavenger_tier_1"|"scavenger_tier_1_captive"|"scavenger_tier_2"|"shield_forcefield_outcast"|"shrieker"|"shrieker_gloom"|"siege_engine"|"soldier"|"soldier_iron_fleet"|"soldier_ivory_legion"|"soldier_mg"|"soldier_mg_assassinate"|"soldier_mg_ivory_legion"|"soldier_rpg"|"soldier_rpg_assassinate"|"soldier_rpg_ivory_legion"|"soldier_shield"|"soldier_shield_ivory_legion"|"soldier_shotgun_ivory_legion"|"spawner"|"spawner_jammer"|"stalker"|"strider"|"strider_gloom"|"tank_autocannons"|"tank_base"|"tank_heavycannon"|"tank_hull_mg"|"tank_rocketlauncher"|"tank_turret_autocannons"|"tank_turret_base"|"tank_turret_heavycannon"|"tank_turret_rocketlauncher"|"tripod"|"tripod_tier_2"|"turret_autocannons"|"turret_base"|"turret_command_bunker_hmg"|"turret_heavycannon"|"turret_mortar"|"walker_scout"|"warrior_acid"|"warrior_base"|"warrior_big"|"warrior_big_tier2"|"warrior_burrower"|"warrior_gloom"|"warrior_plus"|"warrior_tier_1"|"warrior_tier_1_captive"|"warrior_tier_2"|"warrior_tier_2_guard"
---@alias HD2StructureName "Gazer"|"ammunition_stockpile"|"blocking_chunk"|"bug_fog_generator"|"bug_fog_generator_large"|"bug_fog_generator_tcs"|"bug_larva_container_backpack"|"bug_spawner_shrieker"|"canister"|"capital_defense_building"|"central_core_drill_01"|"chemicals_backpack"|"colony_spawner_base"|"command_bunker"|"command_bunker_side"|"command_bunker_top"|"embryo_01"|"embryo_01_cluster_x6"|"embryo_01_cluster_x6_destroyed"|"emplacement_hmg"|"emplacement_mg"|"encounter_ship_landed_door_shield"|"fleet_ship_01"|"gen_footage_volume"|"grinder"|"harvester"|"landed_dropship"|"mothership"|"obj_asset_hijack_tech_hub_nexus_machine"|"power_generator"|"spawner_factory_conscript_airborne"|"spawner_factory_conscript_assault"|"spawner_factory_conscript_base"|"spawner_factory_conscript_phalanx"|"spawner_factory_conscript_standard"|"spore_lung"|"tcs_support_damageable"|"tcs_support_damageable_02"|"turret_01"|"turret_tactical_obj"

---@class HD2EnemyZone
---@field resource "enemy"
---@field path "damage_zone"
---@field enemy string
---@field zone string
local HD2EnemyZone = {}
---Zone fields: zone.health/armor/affects_main_health (proven), zone.constitution/durable_resistance/
---explosive_damage_percentage (allow_unverified_effect=true).
---@return table
function HD2EnemyZone:describe() end

---@class HD2Enemy
---@field resource "enemy"
---@field path "entity"
---@field enemy string
local HD2Enemy = {}
---Identity (wiki name or native class, faction, kind), damage zones and main fields.
---@return table
function HD2Enemy:describe() end
---@return HD2EnemyZone[]
function HD2Enemy:zones() end
---@param identity string|integer Zone id ("zone_0"), native zone name, wiki zone label or index.
---@return HD2EnemyZone
function HD2Enemy:zone(identity) end
---@return HD2EnemyZone[]
function HD2Enemy:damage_zones() end
---@param identity string|integer
---@return HD2EnemyZone
function HD2Enemy:damage_zone(identity) end

---@class HD2EnemyAttack
---@field resource "enemy"
---@field path "attack"
---@field enemy string
---@field attack string
local HD2EnemyAttack = {}
---One settings row per attack: DamageInfo (slot_<n>, slot_<n>_impact, ...), ProjectileSettings
---(slot_<n>_projectile: velocity, mass, drag, gravity, pellet_count) or ExplosionSettings (slot_<n>_impact_explosion: radii).
---Shared settings rows: writes need allow_shared=true and allow_unverified_effect=true.
---@return table
function HD2EnemyAttack:describe() end
---@param identity string Attack id ("slot_0", "slot_0_impact", "slot_0_projectile", "slot_0_impact_explosion") or an exactly matched wiki attack name.
---@return HD2EnemyAttack
function HD2Enemy:attack(identity) end
---@return HD2EnemyAttack[]
function HD2Enemy:attacks() end
---@alias HD2AttackOutputId "40-K Meltagun"|"A/M-23 EMS Mortar Sentry"|"AC-8 Autocannon"|"APW-1 Anti-Materiel Rifle"|"AR-11 Arbitrator"|"AR-2 Coyote"|"AR-23 Liberator"|"AR-23A Liberator Carbine"|"AR-23C Liberator Concussive"|"AR-23P Liberator Penetrator"|"AR-32 Pacifier"|"AR-59 Suppressor"|"AR-61 Tenderizer"|"AR/GL-21 One-Two"|"ARC-12 Blitzer"|"ARC-3 Arc Thrower"|"B/FLAM-80 Cremator"|"BR-14 Adjudicator"|"CB-9 Exploding Crossbow"|"CQC-1 One True Flag"|"CQC-19 Stun Lance"|"CQC-2 Saber"|"CQC-20 Breaching Hammer"|"CQC-30 Stun Baton"|"CQC-5 Combat Hatchet"|"CQC-9 Defoliation Tool"|"DBS-2 Double Freedom"|"EAT-17 Expendable Anti-Tank"|"EAT-411 Leveller"|"EAT-700 Expendable Napalm"|"FAF-14 Spear"|"FLAM-40 Flamethrower"|"FLAM-66 Torcher"|"GL-15 Evictor"|"GL-21 Grenade Launcher"|"GL-28 Belt-Fed Grenade Launcher"|"GL-52 De-Escalator"|"GP-20 Ultimatum"|"GR-8 Recoilless Rifle"|"JAR-5 Dominator"|"LAS-12 Sai"|"LAS-13 Trident"|"LAS-16 Sickle"|"LAS-17 Double-Edge Sickle"|"LAS-58 Talon"|"LAS-98 Laser Cannon"|"LAS-99 Quasar Cannon"|"M-1000 Maxigun"|"M-105 Stalwart"|"M6C/SOCOM Pistol"|"M7S SMG"|"M90A Shotgun"|"MA5C Assault Rifle"|"MG-206 Heavy Machine Gun"|"MG-43 Machine Gun"|"MGX-42 Bullet Storm"|"MLS-4X Commando"|"MP-98 Knight"|"P-11 Stim Pistol"|"P-113 Verdict"|"P-19 Redeemer"|"P-2 Peacemaker"|"P-33 Missile Pistol"|"P-34 Breacher"|"P-35 Re-Educator"|"P-4 Senator"|"P-69 Veto"|"P-92 Warrant"|"P/40-K Bolt Pistol"|"PLAS-1 Scorcher"|"PLAS-101 Purifier"|"PLAS-15 Loyalist"|"PLAS-39 Accelerator Rifle"|"PLAS-45 Epoch"|"R-2 Amendment"|"R-2124 Constitution"|"R-36 Eruptor"|"R-4 Hyena"|"R-6 Deadeye"|"R-63 Diligence"|"R-63CS Diligence Counter Sniper"|"R-72 Censor"|"R/40-K Hot-Shot Marksman Rifle"|"RL-77 Airburst Rocket Launcher"|"RS-422 Railgun"|"S-11 Speargun"|"SG-20 Halt"|"SG-22 Bushwhacker"|"SG-225 Breaker"|"SG-225IE Breaker Incendiary"|"SG-225SP Breaker Spray&Pray"|"SG-451 Cookout"|"SG-8 Punisher"|"SG-88 Break-Action Shotgun"|"SG-8P Punisher Plasma"|"SG-8S Slugger"|"SG-97 Sweeper"|"SMG-203 Gallant"|"SMG-32 Reprimand"|"SMG-72 Pummeler"|"SMG/FLAM-34 Stoker"|"StA-11 SMG"|"StA-52 Assault Rifle"|"StA-X3 W.A.S.P. Launcher"|"TX-41 Sterilizer"|"VG-70 Variable"|"output/v1/arc/arc-12-blitzer"|"output/v1/arc/arc-3-arc-thrower"|"output/v1/beam/40-k-meltagun"|"output/v1/beam/las-13-trident"|"output/v1/beam/las-98-laser-cannon"|"output/v1/melee/cqc-1-one-true-flag"|"output/v1/melee/cqc-19-stun-lance"|"output/v1/melee/cqc-2-saber"|"output/v1/melee/cqc-20-breaching-hammer"|"output/v1/melee/cqc-30-stun-baton"|"output/v1/melee/cqc-5-combat-hatchet"|"output/v1/melee/cqc-9-defoliation-tool"|"output/v1/projectile/a-m-23-ems-mortar-sentry"|"output/v1/projectile/ac-8-autocannon"|"output/v1/projectile/apw-1-anti-materiel-rifle"|"output/v1/projectile/ar-11-arbitrator"|"output/v1/projectile/ar-2-coyote"|"output/v1/projectile/ar-23-liberator"|"output/v1/projectile/ar-23a-liberator-carbine"|"output/v1/projectile/ar-23c-liberator-concussive"|"output/v1/projectile/ar-23p-liberator-penetrator"|"output/v1/projectile/ar-32-pacifier"|"output/v1/projectile/ar-59-suppressor"|"output/v1/projectile/ar-61-tenderizer"|"output/v1/projectile/ar-gl-21-one-two"|"output/v1/projectile/br-14-adjudicator"|"output/v1/projectile/cb-9-exploding-crossbow"|"output/v1/projectile/dbs-2-double-freedom"|"output/v1/projectile/eat-17-expendable-anti-tank"|"output/v1/projectile/eat-411-leveller"|"output/v1/projectile/eat-700-expendable-napalm"|"output/v1/projectile/faf-14-spear"|"output/v1/projectile/gl-15-evictor"|"output/v1/projectile/gl-21-grenade-launcher"|"output/v1/projectile/gl-28-belt-fed-grenade-launcher"|"output/v1/projectile/gl-52-de-escalator"|"output/v1/projectile/gp-20-ultimatum"|"output/v1/projectile/gr-8-recoilless-rifle"|"output/v1/projectile/jar-5-dominator"|"output/v1/projectile/las-12-sai"|"output/v1/projectile/las-16-sickle"|"output/v1/projectile/las-17-double-edge-sickle"|"output/v1/projectile/las-58-talon"|"output/v1/projectile/las-99-quasar-cannon"|"output/v1/projectile/m-1000-maxigun"|"output/v1/projectile/m-105-stalwart"|"output/v1/projectile/m6c-socom-pistol"|"output/v1/projectile/m7s-smg"|"output/v1/projectile/m90a-shotgun"|"output/v1/projectile/ma5c-assault-rifle"|"output/v1/projectile/mg-206-heavy-machine-gun"|"output/v1/projectile/mg-43-machine-gun"|"output/v1/projectile/mgx-42-bullet-storm"|"output/v1/projectile/mls-4x-commando"|"output/v1/projectile/mp-98-knight"|"output/v1/projectile/p-11-stim-pistol"|"output/v1/projectile/p-113-verdict"|"output/v1/projectile/p-19-redeemer"|"output/v1/projectile/p-2-peacemaker"|"output/v1/projectile/p-33-missile-pistol"|"output/v1/projectile/p-34-breacher"|"output/v1/projectile/p-35-re-educator"|"output/v1/projectile/p-4-senator"|"output/v1/projectile/p-40-k-bolt-pistol"|"output/v1/projectile/p-69-veto"|"output/v1/projectile/p-92-warrant"|"output/v1/projectile/plas-1-scorcher"|"output/v1/projectile/plas-101-purifier"|"output/v1/projectile/plas-15-loyalist"|"output/v1/projectile/plas-39-accelerator-rifle"|"output/v1/projectile/plas-45-epoch"|"output/v1/projectile/r-2-amendment"|"output/v1/projectile/r-2124-constitution"|"output/v1/projectile/r-36-eruptor"|"output/v1/projectile/r-4-hyena"|"output/v1/projectile/r-40-k-hot-shot-marksman-rifle"|"output/v1/projectile/r-6-deadeye"|"output/v1/projectile/r-63-diligence"|"output/v1/projectile/r-63cs-diligence-counter-sniper"|"output/v1/projectile/r-72-censor"|"output/v1/projectile/rl-77-airburst-rocket-launcher"|"output/v1/projectile/rs-422-railgun"|"output/v1/projectile/s-11-speargun"|"output/v1/projectile/sg-20-halt"|"output/v1/projectile/sg-22-bushwhacker"|"output/v1/projectile/sg-225-breaker"|"output/v1/projectile/sg-225ie-breaker-incendiary"|"output/v1/projectile/sg-225sp-breaker-spray-pray"|"output/v1/projectile/sg-451-cookout"|"output/v1/projectile/sg-8-punisher"|"output/v1/projectile/sg-88-break-action-shotgun"|"output/v1/projectile/sg-8p-punisher-plasma"|"output/v1/projectile/sg-8s-slugger"|"output/v1/projectile/sg-97-sweeper"|"output/v1/projectile/smg-203-gallant"|"output/v1/projectile/smg-32-reprimand"|"output/v1/projectile/smg-72-pummeler"|"output/v1/projectile/smg-flam-34-stoker"|"output/v1/projectile/sta-11-smg"|"output/v1/projectile/sta-52-assault-rifle"|"output/v1/projectile/sta-x3-w-a-s-p-launcher"|"output/v1/projectile/vg-70-variable"|"output/v1/spray/b-flam-80-cremator"|"output/v1/spray/flam-40-flamethrower"|"output/v1/spray/flam-66-torcher"|"output/v1/spray/tx-41-sterilizer"

---@class HD2AttackOutput
---@field resource "attack_output"
---@field output string
local HD2AttackOutput = {}
---Family (projectile, beam, arc, spray, melee), owner, structural class and whether a projectile host can
---reference it. Use as the value of hd2.fields.attack.projectile on weapon:attack(role); cross-class
---outputs need allow_unverified_reference=true and allow_unverified_effect=true; beam and arc outputs
---fail closed (INCOMPATIBLE_OUTPUT_FAMILY). A projectile output is also the target of its weapon-function
---mode label and icon (hd2.fields.presentation.mode_label / mode_icon; describe().presentation).
---@return table
function HD2AttackOutput:describe() end
---The native mode labels hd2.fields.presentation.mode_label accepts.
---@return string[]
function HD2AttackOutput:mode_labels() end
---The native weapon-function icons hd2.fields.presentation.mode_icon accepts ("default" is the skull).
---@return string[]
function HD2AttackOutput:mode_icons() end
---@alias HD2ExplosionName "B-100 Portable Hellbomb"|"Hellbomb"|"NUX-223 Hellbomb"|"Portable Hellbomb"
---@alias HD2StatusId "burning_heavy"|"fire"|"fire_panic"|"flamer_slowed"|"gas"|"gas_2"|"gas_confusion"|"gas_confusion_2"|"stun_large"|"stun_medium"|"stun_small"
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
---@field crosshair_type "crosshair_type" Legacy fixed-resource field (original short-name catalog only). APW-1 Anti-Materiel Rifle: read-only, integer
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
---@field stationary_while_firing "weapon.stationary_while_firing"
---@field suppressed "weapon.suppressed"
---@field sway "weapon.sway"
---@field third_person_reticle "weapon.third_person_reticle"
---@field vertical_recoil "weapon.vertical_recoil"
---@field vertical_spread "weapon.vertical_spread"

---@class HD2Fields_projectile
---@field projectile_type "projectile_type" Legacy fixed-resource field (original short-name catalog only). JAR-5 Dominator: read-only, integer
---@field alternate_drag "projectile.alternate.drag"
---@field alternate_gravity "projectile.alternate.gravity"
---@field alternate_mass "projectile.alternate.mass"
---@field alternate_pellet_count "projectile.alternate.pellet_count"
---@field alternate_penetration_slowdown "projectile.alternate.penetration_slowdown"
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
---@field primary_penetration_slowdown "projectile.primary.penetration_slowdown"
---@field primary_type "projectile.primary.type"
---@field primary_velocity "projectile.primary.velocity"
---@field type "projectile.type"
---@field velocity "projectile.velocity"

---@class HD2Fields_damage
---@field armor_penetration "armor_penetration" Legacy fixed-resource field (original short-name catalog only). Typed targets use hd2.fields.damage.ap_direct/ap_slight/ap_large/ap_extreme on weapon:attack(role):projectile(). JAR-5 Dominator: reviewed writable, integer
---@field armor_penetration_lanes_1 "armor_penetration_lanes.1" Legacy fixed-resource field (original short-name catalog only). JAR-5 Dominator: read-only, integer
---@field armor_penetration_lanes_2 "armor_penetration_lanes.2" Legacy fixed-resource field (original short-name catalog only). JAR-5 Dominator: read-only, integer
---@field armor_penetration_lanes_3 "armor_penetration_lanes.3" Legacy fixed-resource field (original short-name catalog only). JAR-5 Dominator: read-only, integer
---@field durable_damage "durable_damage" Legacy fixed-resource field (original short-name catalog only). Typed targets use hd2.fields.damage.player_durable_damage. JAR-5 Dominator: read-only, integer; Orbital Laser: read-only, integer
---@field standard_damage "standard_damage" Legacy fixed-resource field (original short-name catalog only). Typed targets use hd2.fields.damage.player_standard_damage. JAR-5 Dominator: read-only, integer; Orbital Laser: read-only, integer
---@field damage_type "damage_type" Legacy fixed-resource field (original short-name catalog only). Orbital Laser: read-only, integer
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
---@field alternate_status_2_strength "damage.alternate.status_2_strength"
---@field alternate_status_2_type "damage.alternate.status_2_type"
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
---@field primary_status_1_strength "damage.primary.status_1_strength"
---@field primary_status_1_type "damage.primary.status_1_type"
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
---@field status_4_strength "damage.status_4_strength"
---@field status_4_type "damage.status_4_type"
---@field status_strength "damage.status_strength"
---@field status_type "damage.status_type"
---@field type "damage.type"

---@class HD2Fields_vehicle

---@class HD2Fields_health
---@field default_armor "default_armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field main_health "main_health" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_0_armor "zones.0.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_1_armor "zones.1.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_10_armor "zones.10.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_11_armor "zones.11.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_12_armor "zones.12.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_13_armor "zones.13.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_14_armor "zones.14.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_15_armor "zones.15.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_16_armor "zones.16.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_17_armor "zones.17.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_18_armor "zones.18.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_19_armor "zones.19.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_2_armor "zones.2.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_20_armor "zones.20.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_21_armor "zones.21.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_22_armor "zones.22.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_23_armor "zones.23.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_24_armor "zones.24.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_25_armor "zones.25.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_26_armor "zones.26.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_27_armor "zones.27.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_28_armor "zones.28.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_29_armor "zones.29.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_3_affects_main_health "zones.3.affects_main_health" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, number; Maelstrom: read-only, number
---@field zones_3_armor "zones.3.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_30_armor "zones.30.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_31_armor "zones.31.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_32_armor "zones.32.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_33_armor "zones.33.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_34_armor "zones.34.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_35_armor "zones.35.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_36_armor "zones.36.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_37_armor "zones.37.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_4_affects_main_health "zones.4.affects_main_health" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, number; Maelstrom: read-only, number
---@field zones_4_armor "zones.4.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_5_armor "zones.5.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_6_armor "zones.6.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_7_armor "zones.7.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_8_armor "zones.8.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer
---@field zones_9_armor "zones.9.armor" Legacy fixed-resource field (original short-name catalog only). Bastion: read-only, integer; Maelstrom: read-only, integer

---@class HD2Fields_stratagem
---@field cooldown "cooldown" Legacy fixed-resource field (original short-name catalog only). Shield Relay: reviewed writable, number
---@field definition_cooldown "stratagem.cooldown"
---@field max_uses "stratagem.max_uses"

---@class HD2Fields_shield
---@field durability "durability" Legacy fixed-resource field (original short-name catalog only). Shield Relay: reviewed writable, number
---@field radius "radius" Legacy fixed-resource field (original short-name catalog only). Shield Relay: reviewed writable, number
---@field entity_radius "shield.radius"
---@field entity_durability "shield.durability"

---@class HD2Fields_payload
---@field lifetime "lifetime" Legacy fixed-resource field (original short-name catalog only). Shield Relay: reviewed writable, number
---@field entity_lifetime "payload.lifetime"
---@field entity "payload.entity"
---@field spawn_count "payload.spawn_count"

---@class HD2Fields_equipment

---@class HD2Fields_recharge
---@field recharge "recharge" Legacy fixed-resource field (original short-name catalog only). Jump Pack: read-only, number
---@field time "recharge.time"

---@class HD2Fields_jumppack
---@field movement_scalar_04 "movement_scalar_04" Legacy fixed-resource field (original short-name catalog only). Jump Pack: read-only, number
---@field movement_scalar_24 "movement_scalar_24" Legacy fixed-resource field (original short-name catalog only). Jump Pack: read-only, number
---@field vertical_launch_velocity "vertical_launch_velocity" Legacy fixed-resource field (original short-name catalog only). Jump Pack: read-only, number

---@class HD2Fields_orbital
---@field interval "interval" Legacy fixed-resource field (original short-name catalog only). Orbital Laser: read-only, number
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
---@field damage_status_1_strength "explosion.damage.status_1_strength"
---@field damage_status_1_type "explosion.damage.status_1_type"
---@field damage_status_2_type "explosion.damage.status_2_type"
---@field damage_status_3_strength "explosion.damage.status_3_strength"
---@field damage_status_3_type "explosion.damage.status_3_type"

---@class HD2Fields_fire_mode
---@field burst_rounds "fire_mode.burst_rounds"
---@field modes "fire_mode.modes"

---@class HD2Fields_fire_rate
---@field modes "fire_rate.modes"

---@class HD2Fields_function_ammo
---@field projectile "function_ammo.projectile"

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

---@class HD2Fields_presentation
---@field armor_penetration "presentation.armor_penetration"
---@field traits "presentation.traits"
---@field mode_label "presentation.mode_label"
---@field mode_icon "presentation.mode_icon"

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

---@class HD2Fields_weapon_function
---@field left "weapon_function.left"
---@field right "weapon_function.right"

---@class HD2Fields_windup
---@field wind_down_seconds "windup.wind_down_seconds"
---@field wind_up_seconds "windup.wind_up_seconds"

---@class HD2Fields_entity
---@field health "entity.health"
---@field armor "entity.armor"
---@field constitution "entity.constitution"
---@field constitution_rate "entity.constitution_rate"
---@field durable_resistance "entity.durable_resistance"
---@field explosive_damage_percentage "entity.explosive_damage_percentage"

---@class HD2Fields_eagle
---@field uses_per_rearm "eagle.uses_per_rearm"
---@field rearm_time "eagle.rearm_time"

---@class HD2Fields_turret
---@field yaw_speed "turret.yaw_speed"
---@field pitch_speed "turret.pitch_speed"
---@field pitch_min "turret.pitch_min"
---@field pitch_max "turret.pitch_max"
---@field yaw_min "turret.yaw_min"
---@field yaw_max "turret.yaw_max"

---@class HD2Fields_targeting
---@field range "targeting.range"

---@class HD2Fields_minefield
---@field salvos "minefield.salvos"
---@field mines_per_salvo "minefield.mines_per_salvo"

---@class HD2Fields_zone
---@field armor "zone.armor"
---@field health "zone.health"
---@field affects_main_health "zone.affects_main_health"
---@field constitution "zone.constitution"
---@field durable_resistance "zone.durable_resistance"
---@field explosive_damage_percentage "zone.explosive_damage_percentage"

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
---@field reload_duration "attachment.reload_duration"
---@field ergonomics_modifier "attachment.ergonomics_modifier"

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

---@class HD2Fields_throwable
---@field starting_count "throwable.starting_count"
---@field max_count "throwable.max_count"
---@field count_from_supply "throwable.count_from_supply"
---@field explosion_delay "throwable.explosion_delay"

---@class HD2Fields_ammunition
---@field projectile "ammunition.projectile"

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
---@field fire_mode HD2Fields_fire_mode
---@field fire_rate HD2Fields_fire_rate
---@field function_ammo HD2Fields_function_ammo
---@field heat HD2Fields_heat
---@field heatsink HD2Fields_heatsink
---@field magazine HD2Fields_magazine
---@field presentation HD2Fields_presentation
---@field reload HD2Fields_reload
---@field rounds HD2Fields_rounds
---@field status HD2Fields_status
---@field terminal HD2Fields_terminal
---@field weapon_function HD2Fields_weapon_function
---@field windup HD2Fields_windup
---@field entity HD2Fields_entity
---@field eagle HD2Fields_eagle
---@field turret HD2Fields_turret
---@field targeting HD2Fields_targeting
---@field minefield HD2Fields_minefield
---@field zone HD2Fields_zone
---@field jump HD2Fields_jump
---@field deposit HD2Fields_deposit
---@field mount HD2Fields_mount
---@field attachment HD2Fields_attachment
---@field booster HD2Fields_booster
---@field throwable HD2Fields_throwable
---@field ammunition HD2Fields_ammunition

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

---@alias HD2EventName "mission_started"|"mission_ended"|"player_spawned"|"player_died"|"entity_spawned"|"entity_died"|"entity_killed"|"entity_damaged"|"player_damaged"|"player_healed"|"player_fired"|"player_kill_credited"|"weapon_equipped"|"weapon_unequipped"|"weapon_changed"|"entity_damage_pre"|"key_down"|"key_up"

---A world position snapshot (metres).
---@class HD2Vector3
---@field x number
---@field y number
---@field z number
local HD2Vector3 = {}

---Where an event came from: native gameplay, or an action a mod performed through Runtime.
---@class HD2EventCause
---@field source "native"|"mod"
---@field mod string|nil The mod whose action caused it.
---@field action string|nil The action id (kind#n).
---@field kind string|nil The action kind (heal, explosion).
---@field depth integer|nil Mod-caused links in the chain (1 = reacting to native gameplay).
---@field parent table|nil The event the action reacted to ({event, cause}).
local HD2EventCause = {}

---Every event payload carries these fields. Payloads are snapshots; changing them changes nothing in the game.
---@class HD2Event
---@field event HD2EventName The event name.
---@field time number Game seconds (the update clock).
---@field frame integer Update tick.
---@field mission integer Mission epoch when observed.
---@field cause HD2EventCause
local HD2Event = {}

---@class HD2SubscribeOptions
---@field owner string|nil Mod id (defaults to the calling mod resource, or the hd2.mod context).
---@field id string|nil Makes registration idempotent: the same owner, event and id replace the earlier callback.
---@field priority integer|nil Higher runs first (-1000..1000, default 0); ties run in subscription order.
---@field scope "session"|"mission"|nil mission: removed automatically when the mission ends.
---@field max_failures integer|nil Consecutive failures before the subscription is disabled (default 25, 0 = never).
local HD2SubscribeOptions = {}

---A subscription handle.
---@class HD2Subscription
---@field id integer|nil
---@field event string
---@field owner string
---@field state "active"|"disabled"|"failed"|"removed"|"expired"|"complete"|"rejected"
---@field reason string|nil Why it was rejected or disabled.
local HD2Subscription = {}
---Stop receiving events (takes effect at once).
---@return HD2Subscription
function HD2Subscription:unsubscribe() end
---Pause without unsubscribing.
---@return HD2Subscription
function HD2Subscription:disable() end
---Resume (also re-enables a subscription disabled after failures).
---@return HD2Subscription
function HD2Subscription:enable() end
---@return boolean
function HD2Subscription:active() end
---Calls, failures, state and reason.
---@return table
function HD2Subscription:describe() end

---@class HD2TimerOptions
---@field owner string|nil
---@field id string|nil Starting a timer with the same owner and id cancels the earlier one.
---@field scope "session"|"mission"|nil mission: cancelled when the mission ends (needs a mission in progress).
local HD2TimerOptions = {}

---A timer handle (game time; paused while the game does not update).
---@class HD2Timer
---@field id integer|nil
---@field owner string
---@field state "active"|"complete"|"cancelled"|"expired"|"failed"|"rejected"
local HD2Timer = {}
---@return HD2Timer
function HD2Timer:cancel() end
---@return boolean
function HD2Timer:active() end
---Seconds until it next fires.
---@return number|nil
function HD2Timer:remaining() end
---@return table
function HD2Timer:describe() end

---@class HD2BindingSpec
---@field key string Default chord, e.g. 'F6' or 'Ctrl+Shift+F6'.
---@field on_press fun(binding: table)|nil
---@field on_release fun(binding: table)|nil
---@field enabled boolean|nil
---@field owner string|nil
local HD2BindingSpec = {}

---A mod keybind. A chord already bound elsewhere leaves this binding in state 'conflict' with no key.
---@class HD2Binding
---@field id string
---@field owner string
---@field key string|nil The active chord.
---@field state "active"|"disabled"|"conflict"|"removed"|"rejected"
local HD2Binding = {}
---Move to another chord; false when that chord is taken.
---@param key string
---@return boolean
function HD2Binding:rebind(key) end
---@return HD2Binding
function HD2Binding:disable() end
---@return HD2Binding
function HD2Binding:enable() end
---@return HD2Binding
function HD2Binding:unbind() end
---@return boolean
function HD2Binding:active() end
---@return table
function HD2Binding:describe() end

---hd2.input
---@class HD2Input
local HD2Input = {}
---Namespaced id ('author_mod.action'). Polled only while the game window has focus.
---@param id string
---@param spec HD2BindingSpec
---@return HD2Binding
function HD2Input.bind(id, spec) end
---@return table[]
function HD2Input.bindings() end
---@param id string
---@return HD2Binding|nil
function HD2Input.get(id) end
---Key names accepted in chords.
---@return string[]
function HD2Input.keys() end

---@class HD2ValueSpec
---@field id string Unique within the mod.
---@field min number
---@field max number
---@field step number|nil Default 1.
---@field default number|nil Default min.
local HD2ValueSpec = {}

---A number a mod sets from code and binds as an hd2.ensure field value (value=handle). The ensure validates min, max, default and one step through the normal guards when it is declared, and re-applies (debounced) whenever the value changes.
---@class HD2ScriptValue : HD2Option
---@field id string
---@field min number
---@field max number
local HD2ScriptValue = {}
---Snapped to the step and clamped to min..max; true when it changed.
---@param value number
---@return boolean
function HD2ScriptValue:set(value) end
---@return number
function HD2ScriptValue:get() end

---The game's state machine now.
---@class HD2GameState
---@field state integer
---@field name string Splash, TitleScreen, Ship, Mission, PrepareShip, PrepareMission.
---@field mission boolean In a mission (Mission state with a game_mode object).
---@field host boolean|nil This machine has authority over the mission.
---@field mode string|nil Game mode.
local HD2GameState = {}

---One source of a player stat: the entity type the game recorded it under.
---@class HD2StatSource
---@field type string Source entity type hash (16 hex digits).
---@field name string|nil The weapon, throwable or stratagem name when catalogued.
---@field shots integer|nil Shots (player_fired).
---@field kills integer|nil Kills (player_kill_credited).
local HD2StatSource = {}

---A read-only position snapshot (metres). Every subscriber and every delayed callback that kept it reads the same values; writing a field raises. tostring(p) formats it.
---@class HD2Position
---@field x number
---@field y number
---@field z number
local HD2Position = {}
---A plain table you can change.
---@return HD2Vector3
function HD2Position:copy() end
---x, y, z.
---@return number, number, number
function HD2Position:unpack() end
---Distance in metres.
---@param other HD2Vector3|HD2Position
---@return number
function HD2Position:distance(other) end

---The identity of an entity type (hd2.entities).
---@class HD2EntityIdentity
---@field id string Semantic id.
---@field type string Type hash (16 hex digits).
---@field name string|nil Catalogued name (wiki name, class name or path leaf).
---@field display_name string|nil Proven wiki name only.
---@field faction string|nil
---@field kind "enemy"|"structure"|nil
---@field enemy boolean Its death counts as an enemy kill (KillScore > 0).
---@field avatar boolean A Helldiver avatar.
local HD2EntityIdentity = {}

---hd2.entities: the identity catalog of every entity type with health. Offline.
---@class HD2Entities
local HD2Entities = {}
---A semantic id or a type hash; nil when unknown (use it to check your ids at load time).
---@param value string
---@return HD2EntityIdentity|nil
function HD2Entities.describe(value) end
---Every catalogued identity matching the filter, sorted by id.
---@param filter? {faction?: string, kind?: string, enemy?: boolean}
---@return HD2EntityIdentity[]
function HD2Entities.list(filter) end

---A gameplay action a mod requested. A refusal never raises: status is refused with a code and a reason.
---@class HD2ActionHandle
---@field kind string 'explosion', 'explosion_assets', 'projectile', 'projectile_assets', 'status'.
---@field owner string The mod that requested it.
---@field status "pending"|"waiting_for_assets"|"ready"|"requested"|"refused"|"cancelled" requested: the game accepted the request this frame.
---@field code string|nil Why it was refused (UNKNOWN_EXPLOSION, UNKNOWN_PROJECTILE, UNKNOWN_STATUS, ASSET_UNKNOWN, ASSET_UNAVAILABLE, NOT_IN_MISSION, HOST_ONLY, NO_LOCAL_AVATAR, RATE_LIMITED, CAUSE_DEPTH, QUEUE_FULL, INVALID_POSITION, INVALID_DIRECTION, INVALID_TARGET, INVALID_AMOUNT, INVALID_OPTION, TARGET_GONE, FIRER_UNSUPPORTED, EXPLOSION_UNAVAILABLE, PROJECTILE_UNAVAILABLE, STATUS_UNAVAILABLE).
---@field reason string|nil
---@field explosion string|nil The explosion (a named explosion or a weapon name).
---@field projectile string|nil The projectile (its weapon).
---@field effect string|nil The status id.
---@field position HD2Position|nil
---@field cause HD2EventCause|nil The event the action reacted to.
local HD2ActionHandle = {}
---@return boolean
function HD2ActionHandle:requested() end
---Only while waiting for assets.
---@return HD2ActionHandle
function HD2ActionHandle:cancel() end
---@return table
function HD2ActionHandle:describe() end

---@class HD2ExplosionOptions
---@field position HD2Vector3|HD2Position World position (an event position works as it is).
---@field owner string|nil Mod id (defaults to the calling mod).
local HD2ExplosionOptions = {}

---hd2.explosions: request a catalogued explosion (docs/event-scripting.md).
---@class HD2Explosions
local HD2Explosions = {}
---Request a catalogued explosion at a position: a named explosion ('Hellbomb' = the NUX-223 Hellbomb, 'B-100 Portable Hellbomb'), or a weapon's catalogued explosion. Host only, in a mission, credited to the local player; loads the explosion's package first when needed. Unknown explosions, raw ids and unknown packages are refused.
---@param explosion HD2ExplosionName|HD2WeaponName|HD2Explosion
---@param opts HD2ExplosionOptions
---@return HD2ActionHandle
function HD2Explosions.spawn(explosion, opts) end
---The weapon's catalogued explosion handle (impact, else expiry).
---@param weapon HD2WeaponName
---@return HD2Explosion|nil, string|nil
function HD2Explosions.of(weapon) end
---Load the explosion assets now (status ready or waiting_for_assets).
---@param explosion HD2ExplosionName|HD2WeaponName|HD2Explosion
---@return HD2ActionHandle
function HD2Explosions.prepare(explosion) end
---Every explosion hd2.explosions can request.
---@return {name: string, weapon: string|nil, type: integer, source: "behavior"|"weapon", assets_known: boolean}[]
function HD2Explosions.list() end

---hd2.actions: what event scripts can make the game do.
---@class HD2Actions
local HD2Actions = {}
---Heal the local player (clamped to maximum health).
---@param amount number
---@param opts? {owner?: string}
---@return number|nil, string|nil
function HD2Actions.heal(amount, opts) end
---Every action: available or blocked, with the reason.
---@return table
function HD2Actions.status() end

---The item in a player's hand (a snapshot; treat it as read-only).
---@class HD2EquippedWeapon
---@field name string|nil The catalogued weapon, throwable or stratagem item; nil when the held entity is not catalogued (for example a stratagem ball).
---@field type string The held entity's type (16 hex digits): the weapon resource.
---@field entity_id integer The held entity.
---@field slot string|nil primary or secondary (proven); support, held_item or unknown (inferred).
---@field slot_proven boolean Whether slot is proven (primary, secondary).
---@field selection integer|nil The game's raw inventory selection (1 primary, 2 secondary, ...).
---@field avatar_id integer The avatar holding it.
local HD2EquippedWeapon = {}

---@class HD2ProjectileOptions
---@field position HD2Vector3|HD2Position Where the projectile starts (world coordinates).
---@field direction HD2Vector3 Which way it flies (any non-zero length; Runtime normalises it).
---@field firer HD2PlayerHandle|nil Only the local player (the default): the projectile is fired and credited by the local player's avatar.
---@field owner string|nil Mod id (defaults to the calling mod).
local HD2ProjectileOptions = {}

---hd2.projectiles: fire a catalogued weapon projectile (docs/event-scripting.md).
---@class HD2Projectiles
local HD2Projectiles = {}
---Fire the weapon's projectile from a position in a direction through the game's own projectile function. Host only, in a mission; fired and credited by the local player (each counts as a shot in the stats); loads the weapon's package first when needed. Other players may not see it.
---@param weapon HD2WeaponName
---@param opts HD2ProjectileOptions
---@return HD2ActionHandle
function HD2Projectiles.spawn(weapon, opts) end
---Load the projectile assets now (status ready or waiting_for_assets).
---@param weapon HD2WeaponName
---@return HD2ActionHandle
function HD2Projectiles.prepare(weapon) end
---Every projectile hd2.projectiles can fire.
---@return {weapon: string, role: string, type: integer, assets_known: boolean}[]
function HD2Projectiles.list() end

---@class HD2StatusOptions
---@field buildup number|nil Buildup added (0 < buildup <= 1000, default 100). The status starts when the target's buildup reaches its susceptibility; strength and duration come from the status itself.
---@field owner string|nil Mod id (defaults to the calling mod).
local HD2StatusOptions = {}

---hd2.status: apply a status a player weapon applies (docs/event-scripting.md).
---@class HD2StatusEffects
local HD2StatusEffects = {}
---Request a status on an entity through the game's own status request queue (the game checks the target can have it and routes it to the target's owner). Host only, in a mission; the local player instigates it. Only statuses a player weapon applies through its damage; strength is refused.
---@param entity HD2EntityHandle|HD2PlayerHandle|{id: integer}
---@param status HD2StatusId
---@param opts? HD2StatusOptions
---@return HD2ActionHandle
function HD2StatusEffects.apply(entity, status, opts) end
---Every status hd2.status can apply.
---@return {id: string, name: string, family: string, type: integer}[]
function HD2StatusEffects.list() end

---An entity. Every live query re-resolves it through the game (same mission, still in the health manager's hash, same type and descriptor) and returns nil once it is gone; the fields are a snapshot.
---@class HD2EntityHandle
---@field id integer Engine entity id.
---@field type string Entity type hash.
---@field name string|nil
---@field faction string|nil
---@field enemy boolean
---@field avatar boolean
---@field semantic_id string Stable identity (see hd2.entities).
---@field display_name string|nil Proven wiki name only.
---@field kind "enemy"|"structure"|nil
---@field unit integer|nil Engine unit id (snapshot).
---@field network_id integer|nil Network id (snapshot).
local HD2EntityHandle = {}
---Still the same live object in the same mission.
---@return boolean
function HD2EntityHandle:is_valid() end
---Valid and not dead (downed counts as alive).
---@return boolean
function HD2EntityHandle:is_alive() end
---@return boolean
function HD2EntityHandle:is_downed() end
---Its death counts as an enemy kill (settings KillScore > 0). Static.
---@return boolean
function HD2EntityHandle:is_enemy() end
---A Helldiver avatar. Static.
---@return boolean
function HD2EntityHandle:is_player_avatar() end
---@return integer|nil
function HD2EntityHandle:health() end
---@return integer|nil
function HD2EntityHandle:max_health() end
---Root position now (nil once gone).
---@return HD2Position|nil
function HD2EntityHandle:position() end
---@return table
function HD2EntityHandle:describe() end
---True when its semantic id is one of the given ids (or in a set). Static: works after it is gone.
---@param ids string|table<string, boolean>
---@param ... string
---@return boolean
function HD2EntityHandle:is(ids, ...) end
---The identity snapshot as a plain table.
---@return table
function HD2EntityHandle:identity() end

---A player, identified by peer id. Valid while the player is in the session; the avatar changes on every respawn.
---@class HD2PlayerHandle
---@field peer string Peer id (16 hex digits).
---@field slot integer Player list index when captured (not stable).
---@field is_local boolean
local HD2PlayerHandle = {}
---@return boolean
function HD2PlayerHandle:is_local_player() end
---Still in the player list.
---@return boolean
function HD2PlayerHandle:is_valid() end
---The player's current avatar.
---@return HD2EntityHandle|nil
function HD2PlayerHandle:avatar() end
---@return boolean
function HD2PlayerHandle:is_alive() end
---@return integer|nil
function HD2PlayerHandle:health() end
---@return integer|nil
function HD2PlayerHandle:max_health() end
---The avatar's position now.
---@return HD2Position|nil
function HD2PlayerHandle:position() end
---Local player only: heal through the game's own heal function (AddHealthFraction), clamped to maximum health; refused while downed or dead. Returns the amount requested after the clamp, or nil and the reason.
---@param amount number
---@param opts? {owner?: string}
---@return number|nil, string|nil
function HD2PlayerHandle:heal(amount, opts) end
---Local player only: what the avatar holds now (its wielder slot 0), re-read on every call. nil and the reason when nothing is in hand, the player is dead or not spawned, or it is another player.
---@return HD2EquippedWeapon|nil, string|nil
function HD2PlayerHandle:equipped_weapon() end
---@return table
function HD2PlayerHandle:describe() end

---A mission began: the game entered its Mission state with a game_mode object. Also reported when Runtime first sees a mission already in progress (first_observation).
---@class HD2Event_mission_started : HD2Event
---@field mission integer Mission epoch; handles from other epochs are invalid.
---@field host boolean|nil This machine has authority over the mission (host or solo).
---@field mode string|nil Game mode (Mission, Horde, Blitz, ...).
---@field first_observation boolean The mission was already running when Runtime started watching.
local HD2Event_mission_started = {}

---The mission ended (the game left its Mission state). Dispatched before mission-scoped state is cleared.
---@class HD2Event_mission_ended : HD2Event
---@field mission integer The epoch that ended.
---@field duration number Game seconds since mission_started.
---@field game_state string The state the game moved to (Ship, PrepareShip, ...).
local HD2Event_mission_ended = {}

---A player's avatar appeared (deployment, reinforcement). Not reported for avatars already present when Runtime starts watching.
---@class HD2Event_player_spawned : HD2Event
---@field player HD2PlayerHandle The player.
---@field local_player boolean True for the player on this machine.
---@field peer string The player peer id (16 hex digits).
---@field avatar HD2EntityHandle|nil The new avatar.
---@field position HD2Position|nil Avatar position when observed.
---@field avatar_id integer|nil Engine entity id of the avatar (a snapshot).
---@field avatar_semantic_id string|nil The avatar type's semantic id.
local HD2Event_player_spawned = {}

---A player's avatar died (its health record reached the dead state, or the avatar disappeared before that was seen).
---@class HD2Event_player_died : HD2Event
---@field player HD2PlayerHandle The player.
---@field local_player boolean True for the player on this machine.
---@field peer string The player peer id (16 hex digits).
---@field avatar HD2EntityHandle|nil The dead avatar (invalid once the game removes it).
---@field position HD2Position|nil Death position: read at death while the unit exists, else the last position read alive.
---@field avatar_id integer|nil Engine entity id of the avatar (a snapshot).
---@field avatar_semantic_id string|nil The avatar type's semantic id.
---@field observed "dead_state"|"avatar_removed" How the death was seen: the avatar's health record reached the dead state, or the avatar was gone before that was seen.
local HD2Event_player_died = {}

---An entity with health appeared (spawned, or became present on this machine). Not reported for the population present when Runtime starts watching.
---@class HD2Event_entity_spawned : HD2Event
---@field entity HD2EntityHandle The entity handle. Live queries fail once the game destroys it; its identity fields stay readable. Delayed logic should use the snapshot fields of the event instead.
---@field type string Entity type hash (16 hex digits).
---@field name string|nil Catalogued name when the type is known.
---@field enemy boolean The game counts this entity's death as an enemy kill (its settings KillScore > 0).
---@field faction string|nil terminids, automatons, illuminate, helldivers or super_earth, when known.
---@field avatar boolean A Helldiver avatar.
---@field entity_id integer Engine entity id (a snapshot: stays readable after the entity is destroyed).
---@field semantic_id string Stable identity: the enemy catalog's id ('enemy/v1/automatons/soldier_mg') or a path-derived one ('entity/v1/helldivers/avatar_helldiver'); 'entity/v1/unresolved/<type>' when the path is unknown.
---@field display_name string|nil The wiki name, only where the enemy catalog proves it (a one-to-one anatomy match); never guessed.
---@field kind "enemy"|"structure"|nil The enemy catalog's kind of this class.
---@field unit_id integer|nil Engine unit id of its body (the corpse keeps it after the death).
---@field network_id integer|nil Network id (nil when the entity has none).
local HD2Event_entity_spawned = {}

---An entity with health died: its life state reached dead, or the game replaced it by its corpse before a poll saw the dead state. Environmental and unattributed deaths included; an entity removed without a corpse (despawned) is not a death.
---@class HD2Event_entity_died : HD2Event
---@field entity HD2EntityHandle The entity handle. Live queries fail once the game destroys it; its identity fields stay readable. Delayed logic should use the snapshot fields of the event instead.
---@field type string Entity type hash (16 hex digits).
---@field name string|nil Catalogued name when the type is known.
---@field enemy boolean The game counts this entity's death as an enemy kill (its settings KillScore > 0).
---@field faction string|nil terminids, automatons, illuminate, helldivers or super_earth, when known.
---@field avatar boolean A Helldiver avatar.
---@field entity_id integer Engine entity id (a snapshot: stays readable after the entity is destroyed).
---@field semantic_id string Stable identity: the enemy catalog's id ('enemy/v1/automatons/soldier_mg') or a path-derived one ('entity/v1/helldivers/avatar_helldiver'); 'entity/v1/unresolved/<type>' when the path is unknown.
---@field display_name string|nil The wiki name, only where the enemy catalog proves it (a one-to-one anatomy match); never guessed.
---@field kind "enemy"|"structure"|nil The enemy catalog's kind of this class.
---@field unit_id integer|nil Engine unit id of its body (the corpse keeps it after the death).
---@field network_id integer|nil Network id (nil when the entity has none).
---@field killer HD2PlayerHandle|nil The player the game credits with the kill (its last-hit creditor); nil for an environmental death. For a death seen through the corpse it is the creditor observed on the last poll before the death (nil for a one-hit kill from full health).
---@field local_killer boolean The kill is credited to the local player.
---@field killer_peer string|nil Creditor peer id, also when that player already left.
---@field position HD2Position|nil Position when the death was observed (the corpse keeps the unit); nil when the unit was already gone.
---@field max_health integer|nil Maximum health.
---@field observed "dead_state"|"corpse" How the death was seen: the health record reached the dead state, or the game had already replaced the entity by its corpse (the record was gone and a corpse on the same unit names the entity).
---@field corpse_id integer|nil Engine id of the corpse entity that replaced it (observed == "corpse"); nil when the dead state was seen first.
local HD2Event_entity_died = {}

---An entity died and the game credits the kill to a player (entity_died with a creditor).
---@class HD2Event_entity_killed : HD2Event
---@field entity HD2EntityHandle The entity handle. Live queries fail once the game destroys it; its identity fields stay readable. Delayed logic should use the snapshot fields of the event instead.
---@field type string Entity type hash (16 hex digits).
---@field name string|nil Catalogued name when the type is known.
---@field enemy boolean The game counts this entity's death as an enemy kill (its settings KillScore > 0).
---@field faction string|nil terminids, automatons, illuminate, helldivers or super_earth, when known.
---@field avatar boolean A Helldiver avatar.
---@field entity_id integer Engine entity id (a snapshot: stays readable after the entity is destroyed).
---@field semantic_id string Stable identity: the enemy catalog's id ('enemy/v1/automatons/soldier_mg') or a path-derived one ('entity/v1/helldivers/avatar_helldiver'); 'entity/v1/unresolved/<type>' when the path is unknown.
---@field display_name string|nil The wiki name, only where the enemy catalog proves it (a one-to-one anatomy match); never guessed.
---@field kind "enemy"|"structure"|nil The enemy catalog's kind of this class.
---@field unit_id integer|nil Engine unit id of its body (the corpse keeps it after the death).
---@field network_id integer|nil Network id (nil when the entity has none).
---@field killer HD2PlayerHandle|nil The player the game credits with the kill (its last-hit creditor); nil for an environmental death. For a death seen through the corpse it is the creditor observed on the last poll before the death (nil for a one-hit kill from full health).
---@field local_killer boolean The kill is credited to the local player.
---@field killer_peer string|nil Creditor peer id, also when that player already left.
---@field position HD2Position|nil Position when the death was observed (the corpse keeps the unit); nil when the unit was already gone.
---@field max_health integer|nil Maximum health.
---@field observed "dead_state"|"corpse" How the death was seen: the health record reached the dead state, or the game had already replaced the entity by its corpse (the record was gone and a corpse on the same unit names the entity).
---@field corpse_id integer|nil Engine id of the corpse entity that replaced it (observed == "corpse"); nil when the dead state was seen first.
local HD2Event_entity_killed = {}

---An entity lost health since the previous tick (the sum of every hit in that tick).
---@class HD2Event_entity_damaged : HD2Event
---@field entity HD2EntityHandle The entity handle. Live queries fail once the game destroys it; its identity fields stay readable. Delayed logic should use the snapshot fields of the event instead.
---@field type string Entity type hash (16 hex digits).
---@field name string|nil Catalogued name when the type is known.
---@field enemy boolean The game counts this entity's death as an enemy kill (its settings KillScore > 0).
---@field faction string|nil terminids, automatons, illuminate, helldivers or super_earth, when known.
---@field avatar boolean A Helldiver avatar.
---@field entity_id integer Engine entity id (a snapshot: stays readable after the entity is destroyed).
---@field semantic_id string Stable identity: the enemy catalog's id ('enemy/v1/automatons/soldier_mg') or a path-derived one ('entity/v1/helldivers/avatar_helldiver'); 'entity/v1/unresolved/<type>' when the path is unknown.
---@field display_name string|nil The wiki name, only where the enemy catalog proves it (a one-to-one anatomy match); never guessed.
---@field kind "enemy"|"structure"|nil The enemy catalog's kind of this class.
---@field unit_id integer|nil Engine unit id of its body (the corpse keeps it after the death).
---@field network_id integer|nil Network id (nil when the entity has none).
---@field damage integer Health lost since the previous tick.
---@field health integer Health now.
---@field max_health integer|nil Maximum health.
---@field downed boolean The entity is downed (constitution).
---@field attacker HD2PlayerHandle|nil The player credited with the last hit (the game's last-hit creditor).
---@field local_attacker boolean The last hit is credited to the local player.
---@field attacker_peer string|nil Creditor peer id.
local HD2Event_entity_damaged = {}

---A player's avatar lost health (entity_damaged for a Helldiver avatar, with its player).
---@class HD2Event_player_damaged : HD2Event
---@field entity HD2EntityHandle The entity handle. Live queries fail once the game destroys it; its identity fields stay readable. Delayed logic should use the snapshot fields of the event instead.
---@field type string Entity type hash (16 hex digits).
---@field name string|nil Catalogued name when the type is known.
---@field enemy boolean The game counts this entity's death as an enemy kill (its settings KillScore > 0).
---@field faction string|nil terminids, automatons, illuminate, helldivers or super_earth, when known.
---@field avatar boolean A Helldiver avatar.
---@field entity_id integer Engine entity id (a snapshot: stays readable after the entity is destroyed).
---@field semantic_id string Stable identity: the enemy catalog's id ('enemy/v1/automatons/soldier_mg') or a path-derived one ('entity/v1/helldivers/avatar_helldiver'); 'entity/v1/unresolved/<type>' when the path is unknown.
---@field display_name string|nil The wiki name, only where the enemy catalog proves it (a one-to-one anatomy match); never guessed.
---@field kind "enemy"|"structure"|nil The enemy catalog's kind of this class.
---@field unit_id integer|nil Engine unit id of its body (the corpse keeps it after the death).
---@field network_id integer|nil Network id (nil when the entity has none).
---@field player HD2PlayerHandle|nil The player whose avatar it is.
---@field local_player boolean
---@field damage integer
---@field health integer
---@field max_health integer|nil
---@field attacker HD2PlayerHandle|nil
---@field local_attacker boolean
local HD2Event_player_damaged = {}

---A player's avatar gained health (stim, regeneration, a Runtime heal). A heal a mod performed carries that mod's cause.
---@class HD2Event_player_healed : HD2Event
---@field entity HD2EntityHandle The entity handle. Live queries fail once the game destroys it; its identity fields stay readable. Delayed logic should use the snapshot fields of the event instead.
---@field type string Entity type hash (16 hex digits).
---@field name string|nil Catalogued name when the type is known.
---@field enemy boolean The game counts this entity's death as an enemy kill (its settings KillScore > 0).
---@field faction string|nil terminids, automatons, illuminate, helldivers or super_earth, when known.
---@field avatar boolean A Helldiver avatar.
---@field entity_id integer Engine entity id (a snapshot: stays readable after the entity is destroyed).
---@field semantic_id string Stable identity: the enemy catalog's id ('enemy/v1/automatons/soldier_mg') or a path-derived one ('entity/v1/helldivers/avatar_helldiver'); 'entity/v1/unresolved/<type>' when the path is unknown.
---@field display_name string|nil The wiki name, only where the enemy catalog proves it (a one-to-one anatomy match); never guessed.
---@field kind "enemy"|"structure"|nil The enemy catalog's kind of this class.
---@field unit_id integer|nil Engine unit id of its body (the corpse keeps it after the death).
---@field network_id integer|nil Network id (nil when the entity has none).
---@field player HD2PlayerHandle|nil
---@field local_player boolean
---@field amount integer Health gained since the previous tick.
---@field health integer
---@field max_health integer|nil
local HD2Event_player_healed = {}

---The local player fired: the game's projectiles_fired mission stat grew. Checked 10 times per second, so one event can count several shots (a shotgun counts each projectile). Local player only; `sources` names the weapons the game recorded the shots under.
---@class HD2Event_player_fired : HD2Event
---@field player HD2PlayerHandle The local player.
---@field local_player boolean Always true.
---@field shots integer Projectiles fired since the previous check.
---@field total integer The stat total now.
---@field sources HD2StatSource[] The growth per source type since the previous check, largest first: the weapon entity for guns, the throwable, or the stratagem payload.
---@field unattributed integer Growth the game recorded without a source.
local HD2Event_player_fired = {}

---The game credited the local player with kills: its dealt_kills mission stat grew (only deaths whose settings count as a kill). Checked 10 times per second, so one event can count several kills; `sources` names the weapons, throwables or stratagem payloads the kills were credited to.
---@class HD2Event_player_kill_credited : HD2Event
---@field player HD2PlayerHandle The local player.
---@field local_player boolean Always true.
---@field kills integer Kills credited since the previous check.
---@field total integer The stat total now.
---@field sources HD2StatSource[] The growth per source type since the previous check, largest first: the weapon entity for guns, the throwable, or the stratagem payload.
---@field unattributed integer Growth the game recorded without a source.
local HD2Event_player_kill_credited = {}

---The local player now holds an item: after a weapon switch, after a respawn (the game wields the first loadout item), or when a carried item is taken in hand. What is held when Runtime starts watching is the baseline (no event).
---@class HD2Event_weapon_equipped : HD2Event
---@field player HD2PlayerHandle The local player.
---@field local_player boolean Always true.
---@field weapon HD2EquippedWeapon What is in hand now.
local HD2Event_weapon_equipped = {}

---The local player no longer holds an item: switched to another (reason switched), hands emptied (emptied), or the avatar changed or died (avatar_changed).
---@class HD2Event_weapon_unequipped : HD2Event
---@field player HD2PlayerHandle The local player.
---@field local_player boolean Always true.
---@field weapon HD2EquippedWeapon What was in hand (HD2EquippedWeapon).
---@field reason "switched"|"emptied"|"avatar_changed" Why it left the hand.
local HD2Event_weapon_unequipped = {}

---What the local player holds changed (one event per change, after weapon_unequipped and weapon_equipped). previous or current is nil when nothing was or is held.
---@class HD2Event_weapon_changed : HD2Event
---@field player HD2PlayerHandle The local player.
---@field local_player boolean Always true.
---@field previous HD2EquippedWeapon|nil What was in hand (HD2EquippedWeapon).
---@field current HD2EquippedWeapon|nil What is in hand now.
local HD2Event_weapon_changed = {}

---Blocked: A pre-damage callback would have to run inside the native damage path before it applies (game.dll 0x9235F0). Runtime patches no game code, and nothing read at damage time can scale one attacker's or one weapon's damage: every multiplier there is global (Vitality, the relation table, mission modifiers) or belongs to the target (research/event-combat-F5FEE03DCFDB.json). Observe damage with entity_damaged.
---@class HD2Event_entity_damage_pre : HD2Event
local HD2Event_entity_damage_pre = {}

---A mod keybind was pressed (hd2.input.bind). Only bound keys are polled; there is no raw keyboard event.
---@class HD2Event_key_down : HD2Event
---@field binding string The binding id.
---@field key string The chord, e.g. 'Ctrl+F6'.
---@field owner string The mod that owns the binding.
local HD2Event_key_down = {}

---A pressed mod keybind was released (or the game window lost focus while it was held).
---@class HD2Event_key_up : HD2Event
---@field binding string The binding id.
---@field key string The chord.
---@field owner string The mod that owns the binding.
local HD2Event_key_up = {}
---@alias HD2MissionStartedEvent HD2Event_mission_started
---@alias HD2MissionEndedEvent HD2Event_mission_ended
---@alias HD2PlayerSpawnedEvent HD2Event_player_spawned
---@alias HD2PlayerDiedEvent HD2Event_player_died
---@alias HD2EntitySpawnedEvent HD2Event_entity_spawned
---@alias HD2EntityDiedEvent HD2Event_entity_died
---@alias HD2EntityKilledEvent HD2Event_entity_killed
---@alias HD2EntityDamagedEvent HD2Event_entity_damaged
---@alias HD2PlayerDamagedEvent HD2Event_player_damaged
---@alias HD2PlayerHealedEvent HD2Event_player_healed
---@alias HD2PlayerFiredEvent HD2Event_player_fired
---@alias HD2PlayerKillCreditedEvent HD2Event_player_kill_credited
---@alias HD2WeaponEquippedEvent HD2Event_weapon_equipped
---@alias HD2WeaponUnequippedEvent HD2Event_weapon_unequipped
---@alias HD2WeaponChangedEvent HD2Event_weapon_changed
---@alias HD2EntityDamagePreEvent HD2Event_entity_damage_pre
---@alias HD2KeyDownEvent HD2Event_key_down
---@alias HD2KeyUpEvent HD2Event_key_up

---hd2.events
---@class HD2Events
local HD2Events = {}
---Every catalogued event.
---@return string[]
function HD2Events.names() end
---Status, phase, payload and source of one event.
---@param name HD2EventName
---@return table
function HD2Events.describe(name) end
---Live status of every event (available, idle, unavailable, blocked) and why.
---@return table
function HD2Events.status() end
---@param filter? {owner?: string, event?: string}
---@return table[]
function HD2Events.subscriptions(filter) end
---The cause of the event whose callback is running.
---@return HD2EventCause|nil
function HD2Events.cause() end
---@return boolean
function HD2Events.in_mission() end
---Run fn as the given mod: every subscription, timer, keybind and action inside belongs to it (the SDK addon wrapper runs each startup this way).
---@param owner string
---@param fn fun(...): any
---@param ... any
---@return any
function HD2Events.run_as(owner, fn, ...) end
---The mod a registration made now belongs to.
---@return string
function HD2Events.owner() end
---The current mission id (the event.mission of this mission) and whether a mission is in progress.
---@return integer, boolean
function HD2Events.mission_id() end
---Subscribe. Bad registrations are logged and return a rejected handle; they never raise.
---@overload fun(name: "mission_started", callback: fun(event: HD2Event_mission_started), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "mission_ended", callback: fun(event: HD2Event_mission_ended), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_spawned", callback: fun(event: HD2Event_player_spawned), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_died", callback: fun(event: HD2Event_player_died), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "entity_spawned", callback: fun(event: HD2Event_entity_spawned), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "entity_died", callback: fun(event: HD2Event_entity_died), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "entity_killed", callback: fun(event: HD2Event_entity_killed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "entity_damaged", callback: fun(event: HD2Event_entity_damaged), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_damaged", callback: fun(event: HD2Event_player_damaged), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_healed", callback: fun(event: HD2Event_player_healed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_fired", callback: fun(event: HD2Event_player_fired), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_kill_credited", callback: fun(event: HD2Event_player_kill_credited), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "weapon_equipped", callback: fun(event: HD2Event_weapon_equipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "weapon_unequipped", callback: fun(event: HD2Event_weapon_unequipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "weapon_changed", callback: fun(event: HD2Event_weapon_changed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "key_down", callback: fun(event: HD2Event_key_down), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "key_up", callback: fun(event: HD2Event_key_up), opts?: HD2SubscribeOptions): HD2Subscription
---@param name HD2EventName
---@param callback fun(event: HD2Event)
---@param opts? HD2SubscribeOptions
---@return HD2Subscription
function HD2Events.on(name, callback, opts) end
---Subscribe for the next event only.
---@overload fun(name: "mission_started", callback: fun(event: HD2Event_mission_started), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "mission_ended", callback: fun(event: HD2Event_mission_ended), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_spawned", callback: fun(event: HD2Event_player_spawned), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_died", callback: fun(event: HD2Event_player_died), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "entity_spawned", callback: fun(event: HD2Event_entity_spawned), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "entity_died", callback: fun(event: HD2Event_entity_died), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "entity_killed", callback: fun(event: HD2Event_entity_killed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "entity_damaged", callback: fun(event: HD2Event_entity_damaged), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_damaged", callback: fun(event: HD2Event_player_damaged), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_healed", callback: fun(event: HD2Event_player_healed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_fired", callback: fun(event: HD2Event_player_fired), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_kill_credited", callback: fun(event: HD2Event_player_kill_credited), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "weapon_equipped", callback: fun(event: HD2Event_weapon_equipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "weapon_unequipped", callback: fun(event: HD2Event_weapon_unequipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "weapon_changed", callback: fun(event: HD2Event_weapon_changed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "key_down", callback: fun(event: HD2Event_key_down), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "key_up", callback: fun(event: HD2Event_key_up), opts?: HD2SubscribeOptions): HD2Subscription
---@param name HD2EventName
---@param callback fun(event: HD2Event)
---@param opts? HD2SubscribeOptions
---@return HD2Subscription
function HD2Events.once(name, callback, opts) end

---hd2.mod(id): one mod's scripting context. Everything registered through it is attributed to it.
---@class HD2ModContext
---@field id string
---@field session table Kept for the game session.
---@field mission table Cleared in place when a mission starts and when it ends.
local HD2ModContext = {}
---@param seconds number
---@param callback fun(timer: HD2Timer)
---@param opts? HD2TimerOptions
---@return HD2Timer
function HD2ModContext:after(seconds, callback, opts) end
---At least 0.05 s.
---@param seconds number
---@param callback fun(timer: HD2Timer)
---@param opts? HD2TimerOptions
---@return HD2Timer
function HD2ModContext:every(seconds, callback, opts) end
---@param id string
---@param spec HD2BindingSpec
---@return HD2Binding
function HD2ModContext:bind(id, spec) end
---Write a line to HD2Runtime.log, prefixed with the mod id.
---@param message string
---@return nil
function HD2ModContext:log(message) end
---@return boolean
function HD2ModContext:in_mission() end
---@return table[]
function HD2ModContext:subscriptions() end
---A script value owned by this mod (the same object for the same id).
---@param spec HD2ValueSpec
---@return HD2ScriptValue
function HD2ModContext:value(spec) end
---Run fn as this mod.
---@param fn fun(...): any
---@param ... any
---@return any
function HD2ModContext:run(fn, ...) end
---
---@overload fun(self: HD2ModContext, name: "mission_started", callback: fun(event: HD2Event_mission_started), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "mission_ended", callback: fun(event: HD2Event_mission_ended), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_spawned", callback: fun(event: HD2Event_player_spawned), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_died", callback: fun(event: HD2Event_player_died), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "entity_spawned", callback: fun(event: HD2Event_entity_spawned), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "entity_died", callback: fun(event: HD2Event_entity_died), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "entity_killed", callback: fun(event: HD2Event_entity_killed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "entity_damaged", callback: fun(event: HD2Event_entity_damaged), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_damaged", callback: fun(event: HD2Event_player_damaged), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_healed", callback: fun(event: HD2Event_player_healed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_fired", callback: fun(event: HD2Event_player_fired), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_kill_credited", callback: fun(event: HD2Event_player_kill_credited), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "weapon_equipped", callback: fun(event: HD2Event_weapon_equipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "weapon_unequipped", callback: fun(event: HD2Event_weapon_unequipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "weapon_changed", callback: fun(event: HD2Event_weapon_changed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "key_down", callback: fun(event: HD2Event_key_down), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "key_up", callback: fun(event: HD2Event_key_up), opts?: HD2SubscribeOptions): HD2Subscription
---@param name HD2EventName
---@param callback fun(event: HD2Event)
---@param opts? HD2SubscribeOptions
---@return HD2Subscription
function HD2ModContext:on(name, callback, opts) end
---
---@overload fun(self: HD2ModContext, name: "mission_started", callback: fun(event: HD2Event_mission_started), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "mission_ended", callback: fun(event: HD2Event_mission_ended), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_spawned", callback: fun(event: HD2Event_player_spawned), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_died", callback: fun(event: HD2Event_player_died), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "entity_spawned", callback: fun(event: HD2Event_entity_spawned), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "entity_died", callback: fun(event: HD2Event_entity_died), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "entity_killed", callback: fun(event: HD2Event_entity_killed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "entity_damaged", callback: fun(event: HD2Event_entity_damaged), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_damaged", callback: fun(event: HD2Event_player_damaged), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_healed", callback: fun(event: HD2Event_player_healed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_fired", callback: fun(event: HD2Event_player_fired), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_kill_credited", callback: fun(event: HD2Event_player_kill_credited), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "weapon_equipped", callback: fun(event: HD2Event_weapon_equipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "weapon_unequipped", callback: fun(event: HD2Event_weapon_unequipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "weapon_changed", callback: fun(event: HD2Event_weapon_changed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "key_down", callback: fun(event: HD2Event_key_down), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "key_up", callback: fun(event: HD2Event_key_up), opts?: HD2SubscribeOptions): HD2Subscription
---@param name HD2EventName
---@param callback fun(event: HD2Event)
---@param opts? HD2SubscribeOptions
---@return HD2Subscription
function HD2ModContext:once(name, callback, opts) end

---@class HD2Runtime
---@field fields HD2Fields
---@field enums HD2Enums
---@field resources HD2Resources
---@field version string
---@field api_version integer
---@field events HD2Events
---@field input HD2Input
---@field entities HD2Entities
---@field explosions HD2Explosions
---@field actions HD2Actions
---@field projectiles HD2Projectiles
---@field status HD2StatusEffects
local hd2 = {}
---@alias HD2WeaponName "AMR"|"APW-1 Anti-Materiel Rifle"|"AR-11 Arbitrator"|"AR-2 Coyote"|"AR-23 Liberator"|"AR-23A Liberator Carbine"|"AR-23C Liberator Concussive"|"AR-23P Liberator Penetrator"|"AR-32 Pacifier"|"AR-59 Suppressor"|"AR-61 Tenderizer"|"AR/GL-21 One-Two"|"ARC-12 Blitzer"|"BR-14 Adjudicator"|"CB-9 Exploding Crossbow"|"CQC-19 Stun Lance"|"CQC-2 Saber"|"CQC-30 Stun Baton"|"CQC-42 Machete"|"CQC-5 Combat Hatchet"|"CQC-73 Entrenchment Tool"|"DBS-2 Double Freedom"|"FLAM-66 Torcher"|"GL-15 Evictor"|"GP-20 Ultimatum"|"GP-31 Grenade Pistol"|"JAR-5 Dominator"|"LAS-12 Sai"|"LAS-13 Trident"|"LAS-16 Sickle"|"LAS-17 Double-Edge Sickle"|"LAS-5 Scythe"|"LAS-58 Talon"|"LAS-7 Dagger"|"M6C/SOCOM Pistol"|"M7S SMG"|"M90A Shotgun"|"MA5C Assault Rifle"|"MP-98 Knight"|"P-11 Stim Pistol"|"P-113 Verdict"|"P-19 Redeemer"|"P-2 Peacemaker"|"P-33 Missile Pistol"|"P-34 Breacher"|"P-35 Re-Educator"|"P-4 Senator"|"P-69 Veto"|"P-72 Crisper"|"P-92 Warrant"|"P/40-K Bolt Pistol"|"PLAS-1 Scorcher"|"PLAS-101 Purifier"|"PLAS-15 Loyalist"|"PLAS-39 Accelerator Rifle"|"R-2 Amendment"|"R-2124 Constitution"|"R-36 Eruptor"|"R-4 Hyena"|"R-6 Deadeye"|"R-63 Diligence"|"R-63CS Diligence Counter Sniper"|"R-72 Censor"|"R/40-K Hot-Shot Marksman Rifle"|"SG-20 Halt"|"SG-22 Bushwhacker"|"SG-225 Breaker"|"SG-225IE Breaker Incendiary"|"SG-225SP Breaker Spray&Pray"|"SG-451 Cookout"|"SG-8 Punisher"|"SG-8P Punisher Plasma"|"SG-8S Slugger"|"SG-97 Sweeper"|"SMG-203 Gallant"|"SMG-32 Reprimand"|"SMG-37 Defender"|"SMG-72 Pummeler"|"SMG/FLAM-34 Stoker"|"StA-11 SMG"|"StA-52 Assault Rifle"|"VG-70 Variable"|"amr"|"jar5"
---@param name HD2WeaponName
---@return HD2Weapon
function hd2.weapon(name) end
---@alias HD2VehicleName "Bastion"|"EXO-45 Patriot Exosuit"|"EXO-49 Emancipator Exosuit"|"EXO-51 Lumberer Exosuit"|"EXO-55 Breakthrough Exosuit"|"FRV (Super Earth variant)"|"GATER Oil Rig"|"M-102 Gunner FRV"|"M-103 Supply FRV"|"M-104 Incinerator FRV"|"Maelstrom"|"TD-110 Maelstrom"|"TD-220 Bastion MK XVI"|"bastion"|"maelstrom"
---@param name HD2VehicleName
---@return HD2Vehicle
function hd2.vehicle(name) end
---@alias HD2StratagemName "40-K Meltagun"|"A/AC-8 Autocannon Sentry"|"A/ARC-3 Tesla Tower"|"A/FLAM-40 Flame Sentry"|"A/G-16 Gatling Sentry"|"A/GM-17 Gas Mortar Sentry"|"A/LAS-98 Laser Sentry"|"A/M-12 Mortar Sentry"|"A/M-23 EMS Mortar Sentry"|"A/MG-43 Machine Gun Sentry"|"A/MLS-4X Rocket Sentry"|"AC-8 Autocannon"|"APW-1 Anti-Materiel Rifle"|"ARC-3 Arc Thrower"|"AX/AR-23 Guard Dog"|"AX/ARC-3 K-9"|"AX/FLAM-75 Hot Dog"|"AX/LAS-5 Rover"|"AX/TX-13 Dog Breath"|"B-1 Supply Pack"|"B-100 Portable Hellbomb"|"B/FLAM-80 Cremator"|"B/MD C4 Pack"|"CQC-1 One True Flag"|"CQC-20 Breaching Hammer"|"CQC-72 Entrenchment Tool"|"CQC-9 Defoliation Tool"|"E/AT-12 Anti-Tank Emplacement"|"E/GL-21 Grenadier Battlement"|"E/MG-101 HMG Emplacement"|"EAT-17 Expendable Anti-Tank"|"EAT-411 Leveller"|"EAT-700 Expendable Napalm"|"EXO-45 Patriot Exosuit"|"EXO-49 Emancipator Exosuit"|"EXO-51 Lumberer Exosuit"|"EXO-55 Breakthrough Exosuit"|"Eagle 110mm Rocket Pods"|"Eagle 500kg Bomb"|"Eagle Airstrike"|"Eagle Cluster Bomb"|"Eagle Gas Airstrike"|"Eagle Napalm Airstrike"|"Eagle Smoke Strike"|"Eagle Strafing Run"|"FAF-14 Spear"|"FLAM-40 Flamethrower"|"FX-12 Shield Generator Relay"|"GL-21 Grenade Launcher"|"GL-28 Belt-Fed Grenade Launcher"|"GL-52 De-Escalator"|"GR-8 Recoilless Rifle"|"LAS-98 Laser Cannon"|"LAS-99 Quasar Cannon"|"LIFT-182 Warp Pack"|"LIFT-850 Jump Pack"|"LIFT-860 Hover Pack"|"M-1000 Maxigun"|"M-102 Gunner FRV"|"M-103 Supply FRV"|"M-104 Incinerator FRV"|"M-105 Stalwart"|"MD-17 Anti-Tank Mines"|"MD-6 Anti-Personnel Minefield"|"MD-8 Gas Mines"|"MD-I4 Incendiary Mines"|"MG-206 Heavy Machine Gun"|"MG-43 Machine Gun"|"MGX-42 Bullet Storm"|"MLS-4X Commando"|"MS-11 Solo Silo"|"Orbital 120mm HE Barrage"|"Orbital 380mm HE Barrage"|"Orbital Airburst Strike"|"Orbital EMS Strike"|"Orbital Gas Strike"|"Orbital Gatling Barrage"|"Orbital Laser"|"Orbital Napalm Barrage"|"Orbital Precision Strike"|"Orbital Railcannon Strike"|"Orbital Smoke Strike"|"Orbital Walking Barrage"|"PLAS-45 Epoch"|"RL-77 Airburst Rocket Launcher"|"RS-422 Railgun"|"Resupply"|"S-11 Speargun"|"SG-88 Break-Action Shotgun"|"SH-20 Ballistic Shield Backpack"|"SH-32 Shield Generator Pack"|"SH-51 Directional Shield"|"Shield Relay"|"StA-X3 W.A.S.P. Launcher"|"TD-110 Maelstrom"|"TD-220 Bastion MK XVI"|"TX-41 Sterilizer"|"orbital_laser"|"shield_relay"
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
---A throwable-slot item by name or semantic ID (see sdk/ThrowableAuthoringCapabilities.json).
---@param name HD2ThrowableName
---@return HD2Throwable
function hd2.throwable(name) end
---@param identity HD2MagazineAttachmentId
---@return HD2WeaponAttachment
function hd2.weapon_attachment(identity) end
---A drop-pod rack by name or semantic ID (see sdk/PodPayloadCapabilities.json).
---@param identity string
---@return HD2PodRack
function hd2.pod_rack(identity) end
---A reviewed replacement pickup by name or semantic ID.
---@param identity string
---@return HD2Pickup
function hd2.pickup(identity) end
---@param category? "support_weapon"|"backpack"|"ammo"|"stim"|"grenade"|"supply"
---@return HD2Pickup[]
function hd2.pickups(category) end
---An enemy class by wiki name (when proven) or native class name (see sdk/EnemyAuthoringCapabilities.json).
---@param name HD2EnemyName
---@return HD2Enemy
function hd2.enemy(name) end
---An enemy structure (fabricators, emplacements, objectives) by wiki or native class name.
---@param name HD2StructureName
---@return HD2Enemy
function hd2.structure(name) end
---Reviewed enemy / structure names, optionally filtered by kind and faction.
---@param filter? {kind?: "enemy"|"structure", faction?: "terminids"|"automatons"|"illuminate"|"neutral"}
---@return string[]
function hd2.enemies(filter) end
---A catalogued attack output by semantic ID or owner weapon name (see docs/attack-outputs.md).
---@param identity HD2AttackOutputId
---@return HD2AttackOutput
function hd2.attack_output(identity) end
---Catalogued attack output IDs, optionally filtered.
---@param filter? {family?: "projectile"|"beam"|"arc"|"spray"|"melee", selectable?: boolean}
---@return string[]
function hd2.attack_outputs(filter) end
---Run once after a delay in game seconds (fractions work; 0 = the next update tick; math.random(1, 10) gives a random delay). The timer belongs to the calling mod; scope=mission cancels it when the mission ends.
---@param seconds number
---@param callback fun(timer: HD2Timer)
---@param opts? HD2TimerOptions
---@return HD2Timer
function hd2.after(seconds, callback, opts) end
---Run repeatedly (at least 0.05 s apart). Missed intervals are skipped, never replayed.
---@param seconds number
---@param callback fun(timer: HD2Timer)
---@param opts? HD2TimerOptions
---@return HD2Timer
function hd2.every(seconds, callback, opts) end
---The scripting context of one mod (the same object on every call). With no id: the calling mod (the SDK wrapper scope or the running callback); it refuses to guess.
---@param id? string
---@return HD2ModContext
function hd2.mod(id) end
---Every player in the session now.
---@return HD2PlayerHandle[]
function hd2.players() end
---The player on this machine.
---@return HD2PlayerHandle|nil
function hd2.local_player() end
---The game's state now (nil when it cannot be read).
---@return HD2GameState|nil
function hd2.game_state() end
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
---Armed capture (research tooling): wait for `py hd2.py snapshot arm` requests and capture on each one; never captures on its own.
---@param request HD2SnapshotControlRequest
---@return HD2Watch
function hd2.snapshot_control(request) end
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
---Wrap exactly one patch, transaction, or composition plan. The first run is fully guarded; afterwards only the applied target bytes are re-checked, backing off from interval (default 60 s) to max_interval (default 600 s). Drift triggers the full guarded path again; conflicts are terminal. Each guarded run retries transient not-ready failures up to 6 attempts, 5 s apart. An option handle as a field value, or an enabled toggle, makes the ensure follow in-game options. It waits until the options are settled (status waiting_for_options). Without Mod Options Menu it runs with the options' declared defaults, or, when the options page was declared with fallback='disable', stays inactive (status unavailable); each applied change re-runs the full guarded validation and write for the same operation; disabling restores the reviewed baseline through the same guards.
---@param request HD2EnsureRequest
---@return HD2EnsureWatch
function hd2.ensure(request) end
---Process-wide counters (scans, lookups, hashes, writes, verifications, scheduler ticks) and worst durations for performance audits.
---@return HD2RuntimeMetrics
function hd2.metrics() end
---Declare an in-game options page (a MODS tab category). CowboyBingus Mod Options Menu v1+ (needs Bingus Shared Loader v18+) is an optional enhancement of mods that use this: without it, or if it is incompatible or rejects an option, one warning is logged per page and every hd2.ensure bound to those options runs normally with the options' declared defaults (fallback='default', the default). Declare the page with fallback='disable' to keep those operations inactive for the session instead. Defaults are validated with the operation when it is declared. Mods that do not call hd2.options are unaffected.
---@param spec HD2OptionsRequest
---@return HD2Options
function hd2.options(spec) end
---Make the game load the packages that one to 16 typed handles (hd2.pickup, hd2.weapon, hd2.support_weapon, hd2.throwable, hd2.vehicle, hd2.backpack, a mounted-weapon candidate, a projectile handle) need, through the same reference-counted package system the game uses for loadouts. Status waiting_for_assets until every package is resident, then complete (result.status RESIDENT), or rejected with code ASSET_UNAVAILABLE. Never blocks; times out after 90 s. Package identities come only from the generated catalog; mods never pass package IDs. patch, transaction, plan and ensure already do this automatically for reference swaps, so most mods never call it.
---@param request HD2AssetRequest
---@return HD2Watch
function hd2.require_assets(request) end
---Offline: whether a typed handle's package dependency is known and auto-loadable, and how it was derived. No IDs.
---@param target table
---@return HD2AssetDependency
function hd2.asset_dependency(target) end

if rawget(_G,'CowboyBingusModLoader') then
    error("HD2Runtime SDK stubs are authoring-only; install the runtime package in-game")
end
return hd2
