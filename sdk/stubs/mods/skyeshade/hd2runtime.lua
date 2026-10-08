---@meta
-- Generated authoring definitions. Never package or execute this file.
-- Schema SHA256 b26e938c237a65d2765fc6cd232d55b713358f0dcb808f07acb4e7e227b9b0a4

---@alias HD2Resource "0x16474112801385B6"|"0x59C5CA839449B379"|"0x80F1A156D9FA1E36"|"0x89C5493E08CA4207"|"0xB0C9FAF4AF8903F9"|"0xEC3575E7A93793BB"|"0xED13DDC480EC6910"|"amr"|"bastion"|"jar5"|"jump_pack"|"maelstrom"|"orbital_laser"|"shield_relay"
---@alias HD2PatchField "armor_penetration"
---@alias HD2TransactionField "cooldown"|"durability"|"lifetime"|"radius"
---@alias HD2PassiveName "ACCLIMATED"|"ADRENO-DEFIBRILLATOR"|"ADVANCED FILTRATION"|"BALLISTIC PADDING"|"BLUNT-FORCE MITIGATION"|"CONCUSSIVE PADDING, GRENADIER"|"CONCUSSIVE PADDING, HAZMAT"|"CONCUSSIVE PADDING, REINFORCED"|"DEMOCRACY PROTECTS"|"DESERT STORMER"|"ELECTRICAL CONDUIT"|"ENGINEERING KIT"|"EXTRA PADDING"|"FEET FIRST"|"FORTIFIED"|"GUNSLINGER"|"INFLAMMABLE"|"INTEGRATED EXPLOSIVES"|"KINETIC DISPLACEMENT MITIGATION"|"MED-KIT"|"OXYGENATOR"|"PEAK PHYSIQUE"|"REDUCED SIGNATURE"|"REINFORCED EPAULETTES"|"ROCK-SOLID"|"SCOUT"|"SERVO-ASSISTED"|"SIEGE-READY"|"STANDARD ISSUE"|"SUPPLEMENTAL ADRENALINE"|"TRUE GRIT"|"UNFLINCHING"

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
---@field recoveries? integer
---@field retry_in? number

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
---@field recover? boolean|{delay?: number, max_delay?: number, limit?: integer}
---@field on_status? fun(status: string, info: {id: string, status: string, previous: string, error: string|nil, code: string|nil, runs: integer, recoveries: integer, retry_in: number|nil})

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

---@alias HD2AuthoringTarget HD2Weapon|HD2DamageProfile|HD2Stratagem|HD2StratagemAttack|HD2EagleRearm|HD2PlayerAttack|HD2WeaponAmmunition|HD2ProjectileReference|HD2TerminalAction|HD2Explosion|HD2SupportWeapon|HD2SupportAttack|HD2SupportProjectile|HD2SupportExplosion|HD2DeployedEntity|HD2DeployedShield|HD2DeployedZone|HD2MountedWeapon|HD2VehicleEntity|HD2VehicleZone|HD2VehicleMount|HD2VehicleWeapon|HD2VehicleWeaponAttack|HD2Backpack|HD2BackpackZone|HD2BackpackLinked|HD2BackpackLinkedZone|HD2BoosterTarget|HD2WeaponAttachment|HD2PodRack|HD2PodSlot|HD2CatalogueExplosion

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
---The projectile builder for this weapon's ProgrammableAmmo mode (weapon:feed("programmable")).
---@return HD2ProjectileBuilder
function HD2Weapon:programmable_ammo() end
---The armory trait labels: {traits, armorPenetration, choices, writable, reason}; presentation only.
---Write hd2.fields.presentation.armor_penetration or hd2.fields.presentation.traits.
---@return table
function HD2Weapon:presentation() end
---The underbarrel weapon: a separate weapon entity the host's underbarrel item names (AR/GL-21 One-Two
---grenade launcher, AR-11 Arbitrator shotgun, SMG/FLAM-34 Stoker flamer). Its own spread, rounds and fire
---rate are written on it with the ordinary field constants (allow_unverified_effect=true).
---@return HD2Subweapon
function HD2Weapon:underbarrel() end

---@class HD2Subweapon
---@field resource "player_weapon"
---@field path "weapon"
---@field weapon string "<host> / underbarrel"
local HD2Subweapon = {}
---{name, kind, subweaponOf, link, sharedDefinitions, notExposed, fields}.
---@return table
function HD2Subweapon:describe() end
---@alias HD2SupportWeaponName "40-K Meltagun"|"AC-8 Autocannon"|"APW-1 Anti-Materiel Rifle"|"ARC-3 Arc Thrower"|"B/FLAM-80 Cremator"|"B/MD C4 Pack"|"CQC-1 One True Flag"|"CQC-20 Breaching Hammer"|"CQC-72 Entrenchment Tool"|"CQC-9 Defoliation Tool"|"EAT-17 Expendable Anti-Tank"|"EAT-411 Leveller"|"EAT-700 Expendable Napalm"|"FAF-14 Spear"|"FLAM-40 Flamethrower"|"GL-21 Grenade Launcher"|"GL-28 Belt-Fed Grenade Launcher"|"GL-52 De-Escalator"|"GR-8 Recoilless Rifle"|"LAS-98 Laser Cannon"|"LAS-99 Quasar Cannon"|"M-1000 Maxigun"|"M-105 Stalwart"|"MG-206 Heavy Machine Gun"|"MG-43 Machine Gun"|"MGX-42 Bullet Storm"|"MLS-4X Commando"|"MS-11 Solo Silo"|"PLAS-45 Epoch"|"RL-77 Airburst Rocket Launcher"|"RS-422 Railgun"|"S-11 Speargun"|"SG-88 Break-Action Shotgun"|"StA-X3 W.A.S.P. Launcher"|"TX-41 Sterilizer"
---@alias HD2SupportAttackName "40-K MELTAGUN B"|"AC-8 P"|"AC-8 P IE"|"AC-8 P1"|"AC-8 P1 IE"|"AC-8 P2"|"APW-1 P"|"AR-23 P"|"ARC-3 ARC THROWER A"|"B/FLAM-80 CREMATOR S"|"B/MD C4 PACK E"|"BurningHeavy"|"CQC-1 ONE TRUE FLAG_dm"|"CQC-20 BREACHING HAMMER IE"|"CQC-20 BREACHING HAMMER_dm"|"CQC-72 ENTRENCHMENT TOOL_dm"|"CQC-9 DEFOLIATION TOOL_dm"|"EAT-17 BACKBLAST E"|"EAT-17 P"|"EAT-17 P IE"|"EAT-411 P"|"EAT-411 P IE"|"EAT-700 P"|"EAT-700 P IE"|"EAT-700 P1"|"EAT-700 P1 IE"|"FAF-14 P"|"FAF-14 P IE"|"FLAM-40 FLAMETHROWER S"|"Fire"|"Fire Panic"|"FlamerSlowed"|"GL-21 P"|"GL-21 P IE"|"GL-28 P"|"GL-28 P IE"|"GL-52 P"|"GL-52 P IE"|"GL-52 P IE A"|"GR-8 BACKBLAST E"|"GR-8 P"|"GR-8 P IE"|"GR-8 P1"|"GR-8 P1 IE"|"Gas"|"Gas Confusion"|"Gas Confusion Var2"|"Gas Var2"|"LAS-98 LASER CANNON B"|"LAS-99 P"|"LAS-99 P IE"|"M-1000 P"|"MG-206 P"|"MG-43 P"|"MGX-42 P"|"MLS-4X BACKBLAST E"|"MLS-4X P"|"MLS-4X P IE"|"P3"|"P3 IE"|"PLAS-45 EPOCH Overcharge E"|"PLAS-45 P"|"PLAS-45 P IE"|"RL-77 P"|"RL-77 P IE"|"RL-77 P1"|"RL-77 P1 IE"|"RL-77 P2"|"RL-77 P2 IE"|"RL-77 P3"|"RS-422 P"|"RS-422 RAILGUN Overcharge E"|"Railgun Max Charge"|"S-11 P"|"S-11 P E"|"SG-88 P"|"SWP SOLO SILO E"|"SWP SOLO SILO EImpact"|"StA-X3 P"|"StA-X3 P IE"|"StA-X3 P1"|"StA-X3 P1 IE"|"Stun Small"|"TX-41 STERILIZER S"|"detonation"|"feed_primary"|"full_charge"|"full_charge_impact"|"impact"|"overcharge_explosion"|"primary"|"primary_expiry"|"primary_impact"|"primary_impact_status_32"|"primary_impact_status_5"|"primary_status_37"|"primary_status_42"|"primary_status_43"|"primary_status_44"|"primary_status_45"|"primary_status_5"|"primary_status_6"|"primary_status_67"

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
---Where this attack's fired projectile lives and, for a support component host (magazine-fed, every shot
---its own ProjectileWeapon +0), the target and field that change it (hd2.fields.attack.projectile, with
---allow_unverified_effect=true; cross-class donors also allow_unverified_reference=true).
---@return HD2ProjectileSource
function HD2SupportAttack:projectile_source() end

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
---@param role? string Defaults to "primary".
---@return HD2ProjectileSource
function HD2SupportWeapon:projectile_source(role) end
---The projectile builder for this weapon's ProgrammableAmmo mode (weapon:feed("programmable")).
---@return HD2ProjectileBuilder
function HD2SupportWeapon:programmable_ammo() end

---@class HD2ProjectileModeSpec
---@field id string Operation id prefix (<id>-mode, <id>-slots, <id>-label, <id>-primary-label)
---@field base? HD2AttackOutput|HD2Option The projectile the mode fires: an output, or a choice of outputs
---@field direct_damage? HD2AttackOutputSlot Another output's direct-hit damage (a fixed base only)
---@field impact_explosion? HD2AttackOutputSlot|"none" Another output's explosion, or none
---@field expiry_explosion? HD2AttackOutputSlot|"none" Another output's explosion, or none
---@field label? string|table<string, string> A native mode label; with a choice base, output name -> label
---@field icon? string|table<string, string> A native icon; default "auto" (exact native icon, else the plain round)
---@field primary_label? string The weapon's own mode label
---@field primary_icon? string The weapon's own mode icon (default "auto")
---@field enabled? HD2Option A toggle applied to every request
---@field allow_shared? boolean Needed when the base (or the weapon's own) row is fired by more than one entity
---@field allow_unverified_effect? boolean Passed on to every request (the builder never adds it)
---@field allow_unverified_reference? boolean Passed on to the mode request (a function projectile needs it)

---@class HD2ProjectileBuilder
local HD2ProjectileBuilder = {}
---{weapon, writable, reason, binding, bases, slots, presentation, acknowledgements, note}.
---@return table
function HD2ProjectileBuilder:describe() end
---Every attack output a programmable mode can fire (projectile family, selectable, scoped for
---function_ammo.projectile), spare twins included.
---@return HD2AttackOutput[]
function HD2ProjectileBuilder:bases() end
---The ensure requests that build a programmable mode from native pieces, one per backing object: the
---binding and function projectile (<id>-mode), the base slots (<id>-slots), the base label and icon
---(<id>-label[-n]) and the weapon's own mode (<id>-primary-label). No new native row is created; a spare
---twin base is an independent native row, any other base changes every entity that fires it.
---Pass each to hd2.ensure.
---@param spec HD2ProjectileModeSpec
---@return table[]
function HD2ProjectileBuilder:operations(spec) end
---Only the label and icon requests (base labels and the weapon's own mode), for a separate option.
---@param spec HD2ProjectileModeSpec
---@return table[]
function HD2ProjectileBuilder:presentation(spec) end
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
---Where the mount's fired projectile lives and, for a mounted component host (magazine-fed, every shot its
---own ProjectileWeapon +0), the target and field that change it (hd2.fields.attack.projectile; the same donor
---pool as player and support weapons; allow_shared when another mount carries the same weapon entity).
---@param role? string Defaults to "primary".
---@return HD2ProjectileSource
function HD2VehicleWeapon:projectile_source(role) end
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
---@return HD2ProjectileSource
function HD2VehicleWeaponAttack:projectile_source() end
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
---The Guard Dog drone this backpack deploys (its own health and damage zone; the drone weapon).
---The backpack -> drone link is re-proven before every write.
---@return HD2BackpackLinked
function HD2Backpack:drone() end
---The SH-51 energy barrier this backpack spawns (shield energy, delays, the barrier damage zone).
---@return HD2BackpackLinked
function HD2Backpack:energy_shield() end
---Names of the linked entities this backpack exposes ("drone", "energy_shield").
---@return string[]
function HD2Backpack:linked() end

---@class HD2BackpackLinked
---@field resource "backpack"
---@field path "linked"
---@field backpack HD2BackpackName
---@field linked "drone"|"energy_shield"
local HD2BackpackLinked = {}
---@return table
function HD2BackpackLinked:describe() end
---@return HD2BackpackLinkedZone[]
function HD2BackpackLinked:damage_zones() end
---@param identity string|integer Zone id ("zone_0"), native zone name ("body_front") or index.
---@return HD2BackpackLinkedZone
function HD2BackpackLinked:damage_zone(identity) end
---The drone's mounted weapon (drones only; see sdk/VehicleWeaponCapabilities.json).
---@return HD2VehicleWeapon
function HD2BackpackLinked:weapon() end

---@class HD2BackpackLinkedZone
---@field resource "backpack"
---@field path "damage_zone"
---@field backpack HD2BackpackName
---@field linked "drone"|"energy_shield"
---@field zone string
local HD2BackpackLinkedZone = {}
---@return table
function HD2BackpackLinkedZone:describe() end

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
---@alias HD2HelldiverZoneName "arm_left"|"arm_right"|"body"|"head"|"leg_left"|"leg_right"
---@alias HD2DamageMultiplierName "critical"|"none"|"normal"|"reduced"|"symbolic"

---@class HD2HelldiverZone
---@field resource "helldiver"
---@field path "damage_zone"
---@field helldiver "Helldiver"
---@field zone HD2HelldiverZoneName
local HD2HelldiverZone = {}
---Zone fields: zone.damage_multiplier / zone.damage_multiplier_dps (by name: HD2DamageMultiplierName; for
---damage over time "inherit" instead of "none"), zone.durable_resistance, zone.affects_main_health and
---zone.health (from the next spawn). Writes need allow_shared=true and allow_unverified_effect=true.
---@return table
function HD2HelldiverZone:describe() end

---@class HD2Helldiver
---@field resource "helldiver"
---@field path "entity"
---@field helldiver "Helldiver"
local HD2Helldiver = {}
---The type, its scope (every Helldiver this machine simulates), zones and fields: hd2.fields.helldiver.speed_*,
---hd2.fields.helldiver.stamina_* and hd2.fields.entity.explosive_damage_percentage, each with its vanilla value,
---reviewed range, research grade and lifecycle (docs/helldiver-fields.md).
---@return table
function HD2Helldiver:describe() end
---@return HD2HelldiverZone[]
function HD2Helldiver:zones() end
---@param identity HD2HelldiverZoneName|integer Zone name or index (0 = head).
---@return HD2HelldiverZone
function HD2Helldiver:zone(identity) end
---@return HD2HelldiverZone[]
function HD2Helldiver:damage_zones() end
---@param identity HD2HelldiverZoneName|integer
---@return HD2HelldiverZone
function HD2Helldiver:damage_zone(identity) end
---Read-only: the Helldivers this machine simulates and which carries a private copy that a type write does
---not reach: {status="checked", simulated, avatars={{entity, local, avatar_copy, health_copy}}} or
---{status="unavailable", reason}.
---@return table
function HD2Helldiver:private_copies() end
---@alias HD2AttackOutputId "40-K Meltagun"|"A/GM-17 Gas Mortar Sentry"|"A/M-12 Mortar Sentry"|"A/M-23 EMS Mortar Sentry"|"A/MLS-4X Rocket Sentry"|"AC-8 Autocannon"|"APW-1 Anti-Materiel Rifle"|"AR-11 Arbitrator"|"AR-2 Coyote"|"AR-23 Liberator"|"AR-23A Liberator Carbine"|"AR-23C Liberator Concussive"|"AR-23P Liberator Penetrator"|"AR-32 Pacifier"|"AR-59 Suppressor"|"AR-61 Tenderizer"|"AR/GL-21 One-Two"|"ARC-12 Blitzer"|"ARC-3 Arc Thrower"|"AX/AR-23 Guard Dog / gun"|"AX/ARC-3 K-9 / gun"|"AX/FLAM-75 Hot Dog / gun"|"AX/LAS-5 Rover / gun"|"AX/TX-13 Dog Breath / gun"|"B/FLAM-80 Cremator"|"BR-14 Adjudicator"|"CB-9 Exploding Crossbow"|"CQC-1 One True Flag"|"CQC-19 Stun Lance"|"CQC-2 Saber"|"CQC-20 Breaching Hammer"|"CQC-30 Stun Baton"|"CQC-5 Combat Hatchet"|"CQC-9 Defoliation Tool"|"DBS-2 Double Freedom"|"E/MG-101 HMG Emplacement"|"EAT-17 Expendable Anti-Tank"|"EAT-411 Leveller"|"EAT-700 Expendable Napalm"|"EXO-45 Patriot Exosuit / left_gun"|"EXO-45 Patriot Exosuit / right_gun"|"EXO-49 Emancipator Exosuit / left_gun"|"EXO-49 Emancipator Exosuit / right_gun"|"EXO-51 Lumberer Exosuit / left_gun"|"EXO-51 Lumberer Exosuit / right_gun"|"EXO-55 Breakthrough Exosuit / right_gun"|"Eagle 110mm Rocket Pods"|"Eagle 500kg Bomb"|"Eagle Airstrike"|"Eagle Cluster Bomb"|"Eagle Gas Airstrike"|"Eagle Napalm Airstrike"|"Eagle Smoke Strike"|"FAF-14 Spear"|"FLAM-40 Flamethrower"|"FLAM-66 Torcher"|"FRV (Super Earth variant) / gun"|"GATER Oil Rig / turret"|"GL-15 Evictor"|"GL-21 Grenade Launcher"|"GL-28 Belt-Fed Grenade Launcher"|"GL-52 De-Escalator"|"GP-20 Ultimatum"|"GP-31 Grenade Pistol"|"GR-8 Recoilless Rifle"|"JAR-5 Dominator"|"LAS-12 Sai"|"LAS-13 Trident"|"LAS-16 Sickle"|"LAS-17 Double-Edge Sickle"|"LAS-58 Talon"|"LAS-98 Laser Cannon"|"LAS-99 Quasar Cannon"|"M-1000 Maxigun"|"M-102 Gunner FRV / gun"|"M-103 Supply FRV / gun"|"M-104 Incinerator FRV / gun"|"M-105 Stalwart"|"M6C/SOCOM Pistol"|"M7S SMG"|"M90A Shotgun"|"MA5C Assault Rifle"|"MG-206 Heavy Machine Gun"|"MG-43 Machine Gun"|"MGX-42 Bullet Storm"|"MLS-4X Commando"|"MP-98 Knight"|"Orbital 120mm HE Barrage"|"Orbital Airburst Strike"|"Orbital EMS Strike"|"Orbital Gas Strike"|"Orbital Gatling Barrage"|"Orbital Napalm Barrage"|"Orbital Precision Strike"|"Orbital Railcannon Strike"|"Orbital Smoke Strike"|"Orbital Walking Barrage"|"P-11 Stim Pistol"|"P-113 Verdict"|"P-19 Redeemer"|"P-2 Peacemaker"|"P-33 Missile Pistol"|"P-34 Breacher"|"P-35 Re-Educator"|"P-4 Senator"|"P-69 Veto"|"P-92 Warrant"|"P/40-K Bolt Pistol"|"PLAS-1 Scorcher"|"PLAS-101 Purifier"|"PLAS-15 Loyalist"|"PLAS-39 Accelerator Rifle"|"PLAS-45 Epoch"|"R-2 Amendment"|"R-2124 Constitution"|"R-36 Eruptor"|"R-4 Hyena"|"R-6 Deadeye"|"R-63 Diligence"|"R-63CS Diligence Counter Sniper"|"R-72 Censor"|"R/40-K Hot-Shot Marksman Rifle"|"RL-77 Airburst Rocket Launcher"|"RS-422 Railgun"|"S-11 Speargun"|"S-11 Speargun (spare twin)"|"SG-20 Halt"|"SG-22 Bushwhacker"|"SG-225 Breaker"|"SG-225IE Breaker Incendiary"|"SG-225SP Breaker Spray&Pray"|"SG-451 Cookout"|"SG-8 Punisher"|"SG-88 Break-Action Shotgun"|"SG-8P Punisher Plasma"|"SG-8S Slugger"|"SG-97 Sweeper"|"SMG-203 Gallant"|"SMG-32 Reprimand"|"SMG-37 Defender"|"SMG-72 Pummeler"|"SMG/FLAM-34 Stoker"|"StA-11 SMG"|"StA-52 Assault Rifle"|"StA-X3 W.A.S.P. Launcher"|"TD-110 Maelstrom / attach_tank_gun"|"TD-110 Maelstrom / slot_2"|"TD-110 Maelstrom / slot_3"|"TD-110 Maelstrom / slot_4"|"TD-220 Bastion MK XVI"|"TD-220 Bastion MK XVI / attach_tank_gun"|"TD-220 Bastion MK XVI / attach_tank_gun_mg"|"TX-41 Sterilizer"|"VG-70 Variable"|"output/v1/arc/arc-12-blitzer"|"output/v1/arc/arc-3-arc-thrower"|"output/v1/arc/ax-arc-3-k-9-gun"|"output/v1/beam/40-k-meltagun"|"output/v1/beam/ax-las-5-rover-gun"|"output/v1/beam/las-13-trident"|"output/v1/beam/las-98-laser-cannon"|"output/v1/melee/cqc-1-one-true-flag"|"output/v1/melee/cqc-19-stun-lance"|"output/v1/melee/cqc-2-saber"|"output/v1/melee/cqc-20-breaching-hammer"|"output/v1/melee/cqc-30-stun-baton"|"output/v1/melee/cqc-5-combat-hatchet"|"output/v1/melee/cqc-9-defoliation-tool"|"output/v1/projectile/a-gm-17-gas-mortar-sentry-projectile-342"|"output/v1/projectile/a-m-12-mortar-sentry-projectile-346"|"output/v1/projectile/a-m-23-ems-mortar-sentry"|"output/v1/projectile/a-mls-4x-rocket-sentry-projectile-320"|"output/v1/projectile/ac-8-autocannon"|"output/v1/projectile/ac-8-autocannon-projectile-284"|"output/v1/projectile/apw-1-anti-materiel-rifle"|"output/v1/projectile/ar-11-arbitrator"|"output/v1/projectile/ar-2-coyote"|"output/v1/projectile/ar-23-liberator"|"output/v1/projectile/ar-23a-liberator-carbine"|"output/v1/projectile/ar-23c-liberator-concussive"|"output/v1/projectile/ar-23p-liberator-penetrator"|"output/v1/projectile/ar-32-pacifier"|"output/v1/projectile/ar-59-suppressor"|"output/v1/projectile/ar-61-tenderizer"|"output/v1/projectile/ar-gl-21-one-two"|"output/v1/projectile/ax-ar-23-guard-dog-gun"|"output/v1/projectile/br-14-adjudicator"|"output/v1/projectile/cb-9-exploding-crossbow"|"output/v1/projectile/dbs-2-double-freedom"|"output/v1/projectile/e-mg-101-hmg-emplacement-projectile-83"|"output/v1/projectile/eagle-110mm-rocket-pods-projectile-82"|"output/v1/projectile/eagle-500kg-bomb-projectile-239"|"output/v1/projectile/eagle-airstrike-projectile-170"|"output/v1/projectile/eagle-cluster-bomb-projectile-286"|"output/v1/projectile/eagle-gas-airstrike-projectile-188"|"output/v1/projectile/eagle-napalm-airstrike-projectile-141"|"output/v1/projectile/eagle-smoke-strike-projectile-130"|"output/v1/projectile/eagle-smoke-strike-projectile-16"|"output/v1/projectile/eat-17-expendable-anti-tank"|"output/v1/projectile/eat-411-leveller"|"output/v1/projectile/eat-700-expendable-napalm"|"output/v1/projectile/exo-45-patriot-exosuit-left-gun"|"output/v1/projectile/exo-45-patriot-exosuit-right-gun"|"output/v1/projectile/exo-49-emancipator-exosuit-left-gun"|"output/v1/projectile/exo-49-emancipator-exosuit-right-gun"|"output/v1/projectile/exo-51-lumberer-exosuit-right-gun"|"output/v1/projectile/exo-55-breakthrough-exosuit-right-gun"|"output/v1/projectile/faf-14-spear"|"output/v1/projectile/frv-super-earth-variant-gun"|"output/v1/projectile/gater-oil-rig-turret"|"output/v1/projectile/gl-15-evictor"|"output/v1/projectile/gl-21-grenade-launcher"|"output/v1/projectile/gl-28-belt-fed-grenade-launcher"|"output/v1/projectile/gl-52-de-escalator"|"output/v1/projectile/gp-20-ultimatum"|"output/v1/projectile/gp-31-grenade-pistol-projectile-263"|"output/v1/projectile/gr-8-recoilless-rifle"|"output/v1/projectile/jar-5-dominator"|"output/v1/projectile/las-12-sai"|"output/v1/projectile/las-16-sickle"|"output/v1/projectile/las-17-double-edge-sickle"|"output/v1/projectile/las-58-talon"|"output/v1/projectile/las-99-quasar-cannon"|"output/v1/projectile/m-1000-maxigun"|"output/v1/projectile/m-102-gunner-frv-gun"|"output/v1/projectile/m-103-supply-frv-gun"|"output/v1/projectile/m-105-stalwart"|"output/v1/projectile/m6c-socom-pistol"|"output/v1/projectile/m7s-smg"|"output/v1/projectile/m90a-shotgun"|"output/v1/projectile/ma5c-assault-rifle"|"output/v1/projectile/mg-206-heavy-machine-gun"|"output/v1/projectile/mg-43-machine-gun"|"output/v1/projectile/mg-43-machine-gun-projectile-49"|"output/v1/projectile/mgx-42-bullet-storm"|"output/v1/projectile/mls-4x-commando"|"output/v1/projectile/mp-98-knight"|"output/v1/projectile/orbital-120mm-he-barrage-projectile-194"|"output/v1/projectile/orbital-airburst-strike-projectile-158"|"output/v1/projectile/orbital-ems-strike-projectile-74"|"output/v1/projectile/orbital-gas-strike-projectile-197"|"output/v1/projectile/orbital-gatling-barrage-projectile-77"|"output/v1/projectile/orbital-napalm-barrage-projectile-234"|"output/v1/projectile/orbital-precision-strike-projectile-100"|"output/v1/projectile/orbital-railcannon-strike-projectile-277"|"output/v1/projectile/orbital-smoke-strike-projectile-247"|"output/v1/projectile/orbital-walking-barrage-projectile-80"|"output/v1/projectile/p-11-stim-pistol"|"output/v1/projectile/p-113-verdict"|"output/v1/projectile/p-19-redeemer"|"output/v1/projectile/p-2-peacemaker"|"output/v1/projectile/p-33-missile-pistol"|"output/v1/projectile/p-33-missile-pistol-projectile-127"|"output/v1/projectile/p-34-breacher"|"output/v1/projectile/p-35-re-educator"|"output/v1/projectile/p-4-senator"|"output/v1/projectile/p-40-k-bolt-pistol"|"output/v1/projectile/p-69-veto"|"output/v1/projectile/p-92-warrant"|"output/v1/projectile/p-92-warrant-projectile-319"|"output/v1/projectile/plas-1-scorcher"|"output/v1/projectile/plas-101-purifier"|"output/v1/projectile/plas-15-loyalist"|"output/v1/projectile/plas-39-accelerator-rifle"|"output/v1/projectile/plas-45-epoch"|"output/v1/projectile/r-2-amendment"|"output/v1/projectile/r-2124-constitution"|"output/v1/projectile/r-36-eruptor"|"output/v1/projectile/r-4-hyena"|"output/v1/projectile/r-40-k-hot-shot-marksman-rifle"|"output/v1/projectile/r-6-deadeye"|"output/v1/projectile/r-63-diligence"|"output/v1/projectile/r-63cs-diligence-counter-sniper"|"output/v1/projectile/r-72-censor"|"output/v1/projectile/rl-77-airburst-rocket-launcher"|"output/v1/projectile/rl-77-airburst-rocket-launcher-projectile-96"|"output/v1/projectile/rs-422-railgun"|"output/v1/projectile/s-11-speargun"|"output/v1/projectile/s-11-speargun-spare-twin"|"output/v1/projectile/sg-20-halt"|"output/v1/projectile/sg-22-bushwhacker"|"output/v1/projectile/sg-225-breaker"|"output/v1/projectile/sg-225ie-breaker-incendiary"|"output/v1/projectile/sg-225sp-breaker-spray-pray"|"output/v1/projectile/sg-451-cookout"|"output/v1/projectile/sg-8-punisher"|"output/v1/projectile/sg-88-break-action-shotgun"|"output/v1/projectile/sg-8p-punisher-plasma"|"output/v1/projectile/sg-8s-slugger"|"output/v1/projectile/sg-97-sweeper"|"output/v1/projectile/smg-203-gallant"|"output/v1/projectile/smg-32-reprimand"|"output/v1/projectile/smg-37-defender-projectile-150"|"output/v1/projectile/smg-37-defender-projectile-3"|"output/v1/projectile/smg-72-pummeler"|"output/v1/projectile/smg-flam-34-stoker"|"output/v1/projectile/sta-11-smg"|"output/v1/projectile/sta-52-assault-rifle"|"output/v1/projectile/sta-x3-w-a-s-p-launcher"|"output/v1/projectile/sta-x3-w-a-s-p-launcher-projectile-330"|"output/v1/projectile/td-110-maelstrom-attach-tank-gun"|"output/v1/projectile/td-110-maelstrom-slot-2"|"output/v1/projectile/td-110-maelstrom-slot-3"|"output/v1/projectile/td-110-maelstrom-slot-4"|"output/v1/projectile/td-220-bastion-mk-xvi-attach-tank-gun"|"output/v1/projectile/td-220-bastion-mk-xvi-attach-tank-gun-mg"|"output/v1/projectile/td-220-bastion-mk-xvi-projectile-36"|"output/v1/projectile/vg-70-variable"|"output/v1/spray/ax-flam-75-hot-dog-gun"|"output/v1/spray/ax-tx-13-dog-breath-gun"|"output/v1/spray/b-flam-80-cremator"|"output/v1/spray/exo-51-lumberer-exosuit-left-gun"|"output/v1/spray/flam-40-flamethrower"|"output/v1/spray/flam-66-torcher"|"output/v1/spray/m-104-incinerator-frv-gun"|"output/v1/spray/tx-41-sterilizer"

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
---The native weapon-function icons hd2.fields.presentation.mode_icon accepts ("default" restores the
---unlabelled placeholder, an empty spot in the menu; "auto" writes the label exact native icon, else the
---plain round ammo_slug).
---@return string[]
function HD2AttackOutput:mode_icons() end
---The icon "auto" writes for a mode label: {icon, source="exact_native"|"generic_fallback"}.
---@param label string
---@return table
function HD2AttackOutput:mode_icon_for(label) end
---This output's direct-hit damage row, as a value for hd2.fields.projectile.direct_damage on another
---output (the projectile builder). Selectable projectile outputs only.
---@return HD2AttackOutputSlot
function HD2AttackOutput:direct_damage() end
---The explosion this output releases when its projectile hits (none on some rows: see describe().slots).
---@return HD2AttackOutputSlot
function HD2AttackOutput:impact_explosion() end
---The explosion this output releases when its projectile expires (a stuck spear, a timed shell).
---@return HD2AttackOutputSlot
function HD2AttackOutput:expiry_explosion() end

---@class HD2AttackOutputSlot
---@field resource "attack_output_slot"
---@field output string
---@field slot "directDamage"|"impactExplosion"|"expiryExplosion"
local HD2AttackOutputSlot = {}
---{output, slot, field, present, allowNone, shared}.
---@return table
function HD2AttackOutputSlot:describe() end
---@alias HD2CatalogueExplosionName "backpack/b100_portable_hellbomb/behavior"|"backpack/lift182_warp_pack/displacement"|"enemy/assault_walker/impact"|"enemy/assault_walker/impact_2"|"enemy/assault_walker/inventory_detonation"|"enemy/big_walker_turret_cannon/impact"|"enemy/bile_titan/ability"|"enemy/bile_titan/ragdoll_crash"|"enemy/bile_titan/spray_impact"|"enemy/boomer/ability"|"enemy/boomer/impact"|"enemy/bug_larva_container_backpack/behavior"|"enemy/canister/detonation"|"enemy/conscript_backpack_lmg/detonation"|"enemy/conscript_jumppack/detonation"|"enemy/conscript_shotgun/detonation"|"enemy/crusher/ability"|"enemy/cyborg_elite/impact"|"enemy/cyborg_elite_female/inventory_detonation"|"enemy/cyborg_elite_rusher/inventory_detonation"|"enemy/dropship/behavior"|"enemy/dropship/vehicle_crash"|"enemy/dropship/vehicle_crash_2"|"enemy/gatekeeper/impact"|"enemy/gatekeeper/impact_2"|"enemy/gazer/behavior"|"enemy/gunship/behavior"|"enemy/gunship/behavior_2"|"enemy/gunship/vehicle_crash"|"enemy/gunship/vehicle_crash_2"|"enemy/hive_lord/ability"|"enemy/hive_lord/ability/shrapnel_impact"|"enemy/hive_lord/ability_10"|"enemy/hive_lord/ability_2"|"enemy/hive_lord/ability_3"|"enemy/hive_lord/ability_4"|"enemy/hive_lord/ability_5"|"enemy/hive_lord/ability_6"|"enemy/hive_lord/ability_7"|"enemy/hive_lord/ability_8"|"enemy/hive_lord/ability_9"|"enemy/hive_lord/impact"|"enemy/illuminate_attack_ship/impact"|"enemy/illuminate_attack_ship/vehicle_crash"|"enemy/illuminate_attack_ship/vehicle_crash_2"|"enemy/illuminate_war_machine/ragdoll_crash"|"enemy/illuminate_war_machine/ragdoll_crash_2"|"enemy/illuminate_warmachine_bombball/detonation"|"enemy/impaler_tentacle/ability"|"enemy/impaler_tentacle/ability_2"|"enemy/jet_champion/behavior"|"enemy/lieutenant_artillery/behavior"|"enemy/lieutenant_ivory_legion/impact"|"enemy/lieutenant_jetpack/detonation"|"enemy/obj_asset_hijack_tech_hub_nexus_machine/ability"|"enemy/power_generator/behavior"|"enemy/rupture_charger/ability"|"enemy/rupture_charger/ability_2"|"enemy/rupture_charger/ability_3"|"enemy/rupture_charger/ability_4"|"enemy/rupture_charger/ability_5"|"enemy/rupture_charger/ability_6"|"enemy/rupture_spewer/inventory_detonation"|"enemy/scavenger_gloom/behavior"|"enemy/scavenger_spitter/behavior"|"enemy/siege_engine/ability"|"enemy/siege_engine/ability_2"|"enemy/siege_engine/ability_3"|"enemy/siege_engine/ability_4"|"enemy/siege_engine/ability_5"|"enemy/siege_engine/impact"|"enemy/siege_engine/impact_2"|"enemy/soldier_rpg/behavior"|"enemy/soldier_rpg/impact"|"enemy/spawner/ragdoll_crash"|"enemy/spore_burst_bile_titan/behavior"|"enemy/spore_burst_bile_titan/spray_impact"|"enemy/spore_burst_hunter/behavior"|"enemy/spore_burst_warrior/behavior"|"enemy/tank_rocketlauncher/behavior"|"enemy/tank_turret_base/impact"|"enemy/tank_turret_rocketlauncher/backblast"|"enemy/tank_turret_rocketlauncher/impact"|"enemy/turret_autocannons/ability"|"enemy/turret_autocannons/ability_2"|"enemy/turret_autocannons/ability_3"|"enemy/turret_autocannons/ability_4"|"enemy/turret_autocannons/ability_5"|"enemy/turret_autocannons/ability_6"|"enemy/turret_autocannons/ability_7"|"enemy/turret_autocannons/behavior"|"enemy/turret_autocannons/behavior_2"|"enemy/turret_mortar/impact"|"enemy/warrior_acid/behavior"|"enemy/watcher/ability"|"enemy/watcher/vehicle_crash"|"entity/avatar_helldiver/behavior"|"entity/beamer_champion_gun/impact"|"entity/beamer_champion_gun_direct/impact"|"entity/caltrops_grenade/detonation"|"entity/caltrops_mine/detonation"|"entity/cha_battlefront_seaf_medic/inventory_detonation"|"entity/cha_hive_lord_back_shell/gib"|"entity/conscript_grenade_incendiary/detonation"|"entity/cyborg_production_unit/ability"|"entity/cyborg_siege_engine_sarcophagus/gib"|"entity/cyborg_siege_engine_sarcophagus_left_door/gib"|"entity/eagle_missile/missile_impact"|"entity/explosive_gas_chimney/ability"|"entity/habs_barrel_fuel/detonation"|"entity/helldiver_dummy/behavior"|"entity/idle_sam_site/impact"|"entity/il_city_cannon/impact"|"entity/illuminate_adept_circle/detonation"|"entity/jet_champion_grenade_he/detonation"|"entity/pathfinder_lightspear/impact"|"entity/seaf_gun/impact"|"entity/soldier_riotgun/impact"|"stratagem/aac8_autocannon_sentry/impact"|"stratagem/agm17_gas_mortar_sentry/impact"|"stratagem/am12_mortar_sentry/impact"|"stratagem/am23_ems_mortar_sentry/expiry"|"stratagem/am23_ems_mortar_sentry/impact"|"stratagem/amls4x_rocket_sentry/impact"|"stratagem/eagle_110mm_rocket_pods/impact"|"stratagem/eagle_110mm_rocket_pods/magazine_impact"|"stratagem/eagle_110mm_rocket_pods/magazine_impact_2"|"stratagem/eagle_110mm_rocket_pods/payload_impact"|"stratagem/eagle_500kg_bomb/payload_expiry"|"stratagem/eagle_500kg_bomb/payload_impact"|"stratagem/eagle_airstrike/payload_impact"|"stratagem/eagle_cluster_bomb/payload_expiry"|"stratagem/eagle_cluster_bomb/payload_expiry/shrapnel_impact"|"stratagem/eagle_gas_airstrike/payload_impact"|"stratagem/eagle_napalm_airstrike/payload_impact"|"stratagem/eagle_smoke_strike/payload_impact"|"stratagem/eat12_antitank_emplacement/impact"|"stratagem/exo45_patriot_exosuit/vehicle_crash"|"stratagem/exo45_patriot_exosuit/vehicle_crash_2"|"stratagem/m102_gunner_frv/ability"|"stratagem/m104_incinerator_frv/ability"|"stratagem/m104_incinerator_frv/ability_2"|"stratagem/md17_antitank_mines/mine"|"stratagem/md6_antipersonnel_minefield/mine"|"stratagem/md8_gas_mines/mine"|"stratagem/mdi4_incendiary_mines/mine"|"stratagem/nux223_hellbomb/behavior"|"stratagem/orbital_120mm_he_barrage/shell_impact"|"stratagem/orbital_120mm_he_barrage/shell_impact_2"|"stratagem/orbital_380mm_he_barrage/shell_impact"|"stratagem/orbital_380mm_he_barrage/shell_impact_2"|"stratagem/orbital_airburst_strike/shell_expiry"|"stratagem/orbital_airburst_strike/shell_expiry/shrapnel_impact"|"stratagem/orbital_ems_strike/shell_impact"|"stratagem/orbital_gas_strike/shell_impact"|"stratagem/orbital_gatling_barrage/shell_impact"|"stratagem/orbital_napalm_barrage/shell_impact"|"stratagem/orbital_napalm_barrage/shell_impact_2"|"stratagem/orbital_precision_strike/shell_impact"|"stratagem/orbital_railcannon_strike/orbital_expiry"|"support_weapon/40k_meltagun/overcharge"|"support_weapon/ac8_autocannon/function_impact"|"support_weapon/ac8_autocannon/impact"|"support_weapon/bflam80_cremator/ability"|"support_weapon/bmd_c4_pack/detonation"|"support_weapon/eat17_expendable_antitank/backblast"|"support_weapon/eat17_expendable_antitank/impact"|"support_weapon/eat411_leveller/impact"|"support_weapon/eat700_expendable_napalm/impact"|"support_weapon/eat700_expendable_napalm/impact/shrapnel_impact"|"support_weapon/faf14_spear/impact"|"support_weapon/gl21_grenade_launcher/impact"|"support_weapon/gl28_beltfed_grenade_launcher/impact"|"support_weapon/gl52_deescalator/impact"|"support_weapon/gr8_recoilless_rifle/backblast"|"support_weapon/gr8_recoilless_rifle/function_impact"|"support_weapon/gr8_recoilless_rifle/impact"|"support_weapon/las98_laser_cannon/ability"|"support_weapon/las99_quasar_cannon/impact"|"support_weapon/mls4x_commando/backblast"|"support_weapon/mls4x_commando/impact"|"support_weapon/ms11_solo_silo/ability"|"support_weapon/ms11_solo_silo/detonation"|"support_weapon/ms11_solo_silo/explosive_40"|"support_weapon/plas45_epoch/charge_2_expiry"|"support_weapon/plas45_epoch/impact"|"support_weapon/rl77_airburst_rocket_launcher/function_expiry"|"support_weapon/rl77_airburst_rocket_launcher/function_expiry/shrapnel_expiry"|"support_weapon/rl77_airburst_rocket_launcher/impact"|"support_weapon/s11_speargun/expiry"|"support_weapon/stax3_wasp_launcher/function_impact"|"support_weapon/stax3_wasp_launcher/impact"|"throwable/g109_urchin/detonation"|"throwable/g10_incendiary/detonation"|"throwable/g123_thermite/detonation"|"throwable/g12_high_explosive/detonation"|"throwable/g13_incendiary_impact/detonation"|"throwable/g142_pyrotech/detonation"|"throwable/g16_impact/detonation"|"throwable/g23_stun/detonation"|"throwable/g31_arc/detonation"|"throwable/g3_smoke/detonation"|"throwable/g40k_melta_mine/detonation"|"throwable/g48_giga_grenade/detonation"|"throwable/g4_gas/detonation"|"throwable/g50_seeker/detonation"|"throwable/g60_antitank_seeker/detonation"|"throwable/g6_frag/detonation"|"throwable/g7_pineapple/detonation"|"throwable/g7_pineapple/detonation/shrapnel_expiry"|"throwable/g89_smokescreen/detonation"|"throwable/g8_immolation/detonation"|"throwable/gsh39_shield/detonation"|"throwable/ted63_dynamite/detonation"|"throwable/tm1_lure_mine/detonation"|"vehicle/exo45_patriot_exosuit_slot_0/impact"|"vehicle/exo49_emancipator_exosuit_attach_turret_l/impact"|"vehicle/td110_maelstrom_slot_2/ability"|"vehicle/td110_maelstrom_slot_3/fired_ability"|"vehicle/td110_maelstrom_slot_3/fired_explosive_40"|"vehicle/td220_bastion_mk_xvi_attach_tank_gun/impact"|"weapon/cb9_exploding_crossbow/impact"|"weapon/cqc42_machete/ability"|"weapon/gl15_evictor/impact"|"weapon/gp20_ultimatum/impact"|"weapon/gp31_grenade_pistol/impact"|"weapon/p33_missile_pistol/impact"|"weapon/p34_breacher/fired_detonation"|"weapon/p34_breacher/impact"|"weapon/p40k_bolt_pistol/impact"|"weapon/plas101_purifier/charge_1_impact"|"weapon/plas101_purifier/impact"|"weapon/plas101_purifier/overcharge"|"weapon/plas15_loyalist/charge_1_impact"|"weapon/plas15_loyalist/charge_2_impact"|"weapon/plas15_loyalist/impact"|"weapon/plas1_scorcher/impact"|"weapon/plas39_accelerator_rifle/impact"|"weapon/plas39_accelerator_rifle/overcharge"|"weapon/r36_eruptor/impact"|"weapon/sg8p_punisher_plasma/impact"
---@alias HD2ExplosionName "B-100 Portable Hellbomb"|"Cyborg Production Unit"|"Hellbomb"|"NUX-223 Hellbomb"|"Portable Hellbomb"
---@alias HD2StatusId "burning_heavy"|"fire"|"fire_panic"|"flamer_slowed"|"gas"|"gas_2"|"gas_confusion"|"gas_confusion_2"|"stun_large"|"stun_medium"|"stun_small"
---@alias HD2MagazineAttachmentId "Jet Assisted Rifle 15mm. Drum Standard"|"Karbin Rifle Standard"|"Pistol 12x20mm. Standard"|"Pistol 9x20mm. Extended"|"Plasma Medium. Canister Extended"|"Plasma Medium. Canister Standard"|"Plasma Pistol. Canister Extended"|"Plasma Pistol. Canister Pistol"|"RIFLE 9x70mm. Extended"|"RIFLE 9x70mm. Standard"|"RIFLE Drake. Short"|"RIFLE Drake. Standard"|"RIFLE Justice. Extended"|"RIFLE Justice. Short"|"RIFLE Justice. Standard"|"Rifle 5,5x50mm. Drum"|"Rifle 5,5x50mm. Drum Carbine"|"Rifle 5,5x50mm. Extended"|"Rifle 5,5x50mm. Extended Fastreload"|"Rifle 5,5x50mm. Standard"|"Rifle 5,5x50mm. Standard Fastreload"|"Rifle 8x40mm Rifle Standard"|"SHOTGUN 12g. Drum"|"SHOTGUN 12g. Drum Light"|"SHOTGUN 12g. Magazine Extended"|"SHOTGUN 12g. Magazine Extended Light"|"SMG 12x25mm. Drum"|"SMG 12x25mm. Drum Pummeler"|"SMG 12x25mm. Extended"|"SMG 12x25mm. Extended Pummeler"|"SMG 12x25mm. Standard"|"SMG 12x25mm. Standard Pummeler"|"SMG 9x20mm. Top Mounted Extended"|"SMG 9x20mm. Top Mounted Extended Solvent"|"SMG 9x20mm. Top Mounted Standard"|"SMG 9x20mm. Top Mounted Standard Solvent"|"SMG Flamer Drum Magazine"|"SMG Flamer Extended Magazine"|"SMG Flamer Standard Magazine"|"Shotgun 12g. Magazine Standard"|"Shotgun 12g. Magazine Standard Light"|"Whisper Rifle 5,5x50mm. Drum"|"Whisper Rifle 5,5x50mm. Standard"|"weapon-attachment/v1/magazine/jet-assisted-rifle-15mm-drum-standard/d973eb6ff9b6c804"|"weapon-attachment/v1/magazine/karbin-rifle-standard/e2f9b6b1f2e8fddb"|"weapon-attachment/v1/magazine/pistol-12x20mm-standard/874261a0d16e5e00"|"weapon-attachment/v1/magazine/pistol-9x20mm-extended/98939255db31bed4"|"weapon-attachment/v1/magazine/plasma-medium-canister-extended/09729aaa96113627"|"weapon-attachment/v1/magazine/plasma-medium-canister-standard/f4fa14d4afd3ea71"|"weapon-attachment/v1/magazine/plasma-pistol-canister-extended/6ec0d8e8516cbc07"|"weapon-attachment/v1/magazine/plasma-pistol-canister-pistol/b427e5ddcd7ebe62"|"weapon-attachment/v1/magazine/rifle-5-5x50mm-drum-carbine/00618531fc7a3692"|"weapon-attachment/v1/magazine/rifle-5-5x50mm-drum/fa499a29b375c6cf"|"weapon-attachment/v1/magazine/rifle-5-5x50mm-extended-fastreload/b9d2c29a3b15b591"|"weapon-attachment/v1/magazine/rifle-5-5x50mm-extended/bfc7127000978692"|"weapon-attachment/v1/magazine/rifle-5-5x50mm-standard-fastreload/b46fd3d0a10576b9"|"weapon-attachment/v1/magazine/rifle-5-5x50mm-standard/272e4c5f18bbd39e"|"weapon-attachment/v1/magazine/rifle-8x40mm-rifle-standard/892779ea0d77aeb3"|"weapon-attachment/v1/magazine/rifle-9x70mm-extended/ac5002ad314cd5a3"|"weapon-attachment/v1/magazine/rifle-9x70mm-standard/cda05894170c4de9"|"weapon-attachment/v1/magazine/rifle-drake-short/a04c9bf6b8f34a03"|"weapon-attachment/v1/magazine/rifle-drake-standard/30c524ee2906dec4"|"weapon-attachment/v1/magazine/rifle-justice-extended/621a26851cfd19a2"|"weapon-attachment/v1/magazine/rifle-justice-short/9deab1113f78adfa"|"weapon-attachment/v1/magazine/rifle-justice-standard/c52443137e402fe8"|"weapon-attachment/v1/magazine/shotgun-12g-drum-light/6848f4e70d10b9a7"|"weapon-attachment/v1/magazine/shotgun-12g-drum/c1aeebcaa7c23988"|"weapon-attachment/v1/magazine/shotgun-12g-magazine-extended-light/ce3ad89a45cec7a2"|"weapon-attachment/v1/magazine/shotgun-12g-magazine-extended/95b6103970039345"|"weapon-attachment/v1/magazine/shotgun-12g-magazine-standard-light/6304622136df620c"|"weapon-attachment/v1/magazine/shotgun-12g-magazine-standard/f9f877be8deda58d"|"weapon-attachment/v1/magazine/smg-12x25mm-drum-pummeler/4fded5f56e190410"|"weapon-attachment/v1/magazine/smg-12x25mm-drum/568bc4a451110ca0"|"weapon-attachment/v1/magazine/smg-12x25mm-extended-pummeler/946ef6b4fae7c0de"|"weapon-attachment/v1/magazine/smg-12x25mm-extended/73a27ec123b6d632"|"weapon-attachment/v1/magazine/smg-12x25mm-standard-pummeler/ea054f1cc567db3b"|"weapon-attachment/v1/magazine/smg-12x25mm-standard/6c63bd137af2da1e"|"weapon-attachment/v1/magazine/smg-9x20mm-top-mounted-extended-solvent/11156cef840b147a"|"weapon-attachment/v1/magazine/smg-9x20mm-top-mounted-extended/176c9113b2833712"|"weapon-attachment/v1/magazine/smg-9x20mm-top-mounted-standard-solvent/80bf5c7ef57ea0e0"|"weapon-attachment/v1/magazine/smg-9x20mm-top-mounted-standard/fc9cc6afc9155eb2"|"weapon-attachment/v1/magazine/smg-flamer-drum-magazine/edd0b384b4ec7242"|"weapon-attachment/v1/magazine/smg-flamer-extended-magazine/a7609a0fd1736a11"|"weapon-attachment/v1/magazine/smg-flamer-standard-magazine/e68347c558fb8b96"|"weapon-attachment/v1/magazine/whisper-rifle-5-5x50mm-drum/dc2b49810b002079"|"weapon-attachment/v1/magazine/whisper-rifle-5-5x50mm-standard/16af29c8d0590809"
---@alias HD2ModifierAttachmentId "10g. Duckbill"|"10g. Full Choke"|"10g. Half Choke"|"10g. Standard Choke"|"12g. Duckbill"|"12g. Full Choke"|"12g. Half Choke"|"12g. Standard Choke"|"12mm. Compensator"|"12mm. Flash Hider"|"12mm. Muzzle break"|"12mm. Naked"|"5,5mm. Compensator"|"5,5mm. Flash Hider"|"5,5mm. Muzzle brake Custom Penetrator"|"5,5mm. Muzzle break"|"5.5mm. Naked"|"5mm. Muzzle brake Custom Karbin"|"8mm. Compensator"|"8mm. Flash Hider"|"8mm. Muzzle brake Custom Adjudicator"|"8mm. Muzzle brake Custom Assault Rifle Large Calibre"|"8mm. Muzzle brake Custom Tenderdizer"|"8mm. Muzzle break"|"8mm. Naked"|"9mm. Compensator"|"9mm. Flash Hider"|"9mm. Muzzle brake Custom Diligence Counter Sniper"|"9mm. Muzzle break"|"9mm. Naked"|"Angled Foregrip"|"Angled Foregrip Advanced"|"Angled Foregrip With Laser"|"Bayonet"|"COMBAT SCOPE 4x"|"DUNE WALKER SNIPER SCOPE 10x"|"Empty Flashlight"|"Empty Laser"|"Empty Laser Flashlight"|"FAF SPEAR SCOPE"|"Flamerthrower SMG Flamer"|"Flashlight"|"Grenade Launcher Grenadier"|"HOLOGRAPHIC SIGHT"|"Iron Sights"|"Laser Sight"|"Laser Sight Flashlight"|"Laser. Blaster Focus"|"Laser. Blaster Standard"|"Laser. Charge Standard"|"Laser. Standard Prism"|"MORGUNSON HOLO-SIGHT"|"Muzzle brake Custom Drake"|"No Muzzle"|"No Optics"|"No Underbarrel"|"PISTOL REFLEX SIGHT"|"REFLEX SIGHT"|"REFLEX SIGHT MKII"|"Railgun Scope"|"Revolver. Medium Barrel"|"SNIPER SCOPE 10x"|"SNIPER SCOPE 10x HELGHAST"|"SNIPER SCOPE 10x SHARK"|"Support Scope"|"TUBE REDDOT 1,5x"|"TUBE REDDOT 2x"|"Trenchgun Bayonet"|"Vertical Grip"|"Vertical Grip 45 Degree"|"Vertical Grip Advanced"|"Vertical Grip Flashlight"|"shotgun risk"|"weapon-attachment/v1/muzzle/10g-duckbill/412d31cf7c892657"|"weapon-attachment/v1/muzzle/10g-full-choke/df6e05b18c5bf733"|"weapon-attachment/v1/muzzle/10g-half-choke/26a1b11d420c9e0e"|"weapon-attachment/v1/muzzle/10g-standard-choke/e0c46031c6d99d88"|"weapon-attachment/v1/muzzle/12g-duckbill/88ac4db624cc7cd5"|"weapon-attachment/v1/muzzle/12g-full-choke/d90b64b1f815ed6a"|"weapon-attachment/v1/muzzle/12g-half-choke/500e8e282a42ea8b"|"weapon-attachment/v1/muzzle/12g-standard-choke/82080b2b4f18985a"|"weapon-attachment/v1/muzzle/12mm-compensator/1dc5e77d04dc6075"|"weapon-attachment/v1/muzzle/12mm-flash-hider/ab06e26961a0b74b"|"weapon-attachment/v1/muzzle/12mm-muzzle-break/a74cd729cb78bd66"|"weapon-attachment/v1/muzzle/12mm-naked/1095cb7881a4694a"|"weapon-attachment/v1/muzzle/5-5mm-compensator/4ec5d2257a90f4d2"|"weapon-attachment/v1/muzzle/5-5mm-flash-hider/3d6e793c78a01b06"|"weapon-attachment/v1/muzzle/5-5mm-muzzle-brake-custom-penetrator/7bf12048e90c4eb1"|"weapon-attachment/v1/muzzle/5-5mm-muzzle-break/5514c8d6d01da45c"|"weapon-attachment/v1/muzzle/5-5mm-naked/d21a607950b1d906"|"weapon-attachment/v1/muzzle/5mm-muzzle-brake-custom-karbin/5e6b1feddde8631a"|"weapon-attachment/v1/muzzle/8mm-compensator/c2eeadc4475287e6"|"weapon-attachment/v1/muzzle/8mm-flash-hider/9b8b8d87e77430dc"|"weapon-attachment/v1/muzzle/8mm-muzzle-brake-custom-adjudicator/6ecb2d389d4c40db"|"weapon-attachment/v1/muzzle/8mm-muzzle-brake-custom-assault-rifle-large-calibre/2a9594ff0c252e42"|"weapon-attachment/v1/muzzle/8mm-muzzle-brake-custom-tenderdizer/0dba21162292a318"|"weapon-attachment/v1/muzzle/8mm-muzzle-break/10170c032e91884a"|"weapon-attachment/v1/muzzle/8mm-naked/97ccfadba9738d80"|"weapon-attachment/v1/muzzle/9mm-compensator/16e4625033b594cb"|"weapon-attachment/v1/muzzle/9mm-flash-hider/7422f0065407a775"|"weapon-attachment/v1/muzzle/9mm-muzzle-brake-custom-diligence-counter-sniper/a7607ba6e4fed01b"|"weapon-attachment/v1/muzzle/9mm-muzzle-break/0d5f7ca4346eda0f"|"weapon-attachment/v1/muzzle/9mm-naked/ecad2a628cad83a7"|"weapon-attachment/v1/muzzle/laser-blaster-focus/6103d062b831b110"|"weapon-attachment/v1/muzzle/laser-blaster-standard/910f99340b319620"|"weapon-attachment/v1/muzzle/laser-charge-standard/999bbb1342467088"|"weapon-attachment/v1/muzzle/laser-standard-prism/46d19d5c80239703"|"weapon-attachment/v1/muzzle/muzzle-brake-custom-drake/fdce6eb68b7ae8fd"|"weapon-attachment/v1/muzzle/no-muzzle/d1d7fb00a8ed4495"|"weapon-attachment/v1/muzzle/revolver-medium-barrel/b6f19fd0696bf145"|"weapon-attachment/v1/optics/combat-scope-4x/8fe8dedca12e8f87"|"weapon-attachment/v1/optics/dune-walker-sniper-scope-10x/cb57c44bb274b8e7"|"weapon-attachment/v1/optics/faf-spear-scope/937147287eecd60b"|"weapon-attachment/v1/optics/holographic-sight/052c05dfd1d8bb3c"|"weapon-attachment/v1/optics/iron-sights/5c0e0df266cafbb8"|"weapon-attachment/v1/optics/morgunson-holo-sight/5280a97eb66d420a"|"weapon-attachment/v1/optics/no-optics/d1d7fb00a8ed4495"|"weapon-attachment/v1/optics/pistol-reflex-sight/1e5ccd1b7e828d3d"|"weapon-attachment/v1/optics/railgun-scope/b32a146f741b3a48"|"weapon-attachment/v1/optics/reflex-sight-mkii/161a5f1f49e18552"|"weapon-attachment/v1/optics/reflex-sight/39b63d47c41165c3"|"weapon-attachment/v1/optics/sniper-scope-10x-helghast/12d1df5b4e3c311e"|"weapon-attachment/v1/optics/sniper-scope-10x-shark/2dd987af8f7b12a6"|"weapon-attachment/v1/optics/sniper-scope-10x/07f1a4f0021dcf2a"|"weapon-attachment/v1/optics/support-scope/b02b888256e41fa1"|"weapon-attachment/v1/optics/tube-reddot-1-5x/fbbe744b87a20507"|"weapon-attachment/v1/optics/tube-reddot-2x/184551d23defaf96"|"weapon-attachment/v1/underbarrel/angled-foregrip-advanced/a0bc2ffdf4139c59"|"weapon-attachment/v1/underbarrel/angled-foregrip-with-laser/69abc1d6fa03d593"|"weapon-attachment/v1/underbarrel/angled-foregrip/d22931feed28dbe6"|"weapon-attachment/v1/underbarrel/bayonet/199e45755aadc700"|"weapon-attachment/v1/underbarrel/empty-flashlight/53e0295561a4de67"|"weapon-attachment/v1/underbarrel/empty-laser-flashlight/a0642056ab8e4eba"|"weapon-attachment/v1/underbarrel/empty-laser/3ef03725020223ce"|"weapon-attachment/v1/underbarrel/flamerthrower-smg-flamer/07949e1674b5dddd"|"weapon-attachment/v1/underbarrel/flashlight/38587c188903ebc0"|"weapon-attachment/v1/underbarrel/grenade-launcher-grenadier/0a551758e788cdbd"|"weapon-attachment/v1/underbarrel/laser-sight-flashlight/25c6efee394ddfa0"|"weapon-attachment/v1/underbarrel/laser-sight/72fb7b94663086fe"|"weapon-attachment/v1/underbarrel/no-underbarrel/d1d7fb00a8ed4495"|"weapon-attachment/v1/underbarrel/shotgun-risk/d8182ddebef78288"|"weapon-attachment/v1/underbarrel/trenchgun-bayonet/61f8422733cbcb53"|"weapon-attachment/v1/underbarrel/vertical-grip-45-degree/549dd72a320448e9"|"weapon-attachment/v1/underbarrel/vertical-grip-advanced/e3aa6f7576c06858"|"weapon-attachment/v1/underbarrel/vertical-grip-flashlight/fb1ed26d82df104f"|"weapon-attachment/v1/underbarrel/vertical-grip/0222918bcbe339ba"

---@alias HD2AttachmentSlot "magazine"|"muzzle"|"optics"|"underbarrel"
---@alias HD2WeaponAttachmentId HD2MagazineAttachmentId|HD2ModifierAttachmentId

---@class HD2WeaponAttachment
---@field resource "weapon_attachment"
---@field path HD2AttachmentSlot
---@field attachment string
local HD2WeaponAttachment = {}
---Slot, relationship and fields; muzzle/optics/underbarrel also list compatibleWeapons, modifiers and the
---unproven readOnlyPatches. One definition is shared by every weapon that equips it.
---@return table
function HD2WeaponAttachment:describe() end
---Native default and uniquely proven magazine attachments for this weapon.
---@return HD2WeaponAttachment[]
function HD2Weapon:magazine_attachments() end
---@param identity? string Catalog option name, attachment semanticId, or "default".
---@return HD2WeaponAttachment
function HD2Weapon:magazine_attachment(identity) end
---Attachment definitions of one slot for this weapon (magazine: magazine_attachments()).
---@param slot HD2AttachmentSlot
---@return HD2WeaponAttachment[]
function HD2Weapon:attachments(slot) end
---One slot's definition: native name, semanticId, or "default"/nil for the native resource default.
---@param slot HD2AttachmentSlot
---@param identity? string
---@return HD2WeaponAttachment
function HD2Weapon:attachment_definition(slot, identity) end

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
---@field recoil_multiplier_horizontal "weapon.recoil_multiplier_horizontal"
---@field recoil_multiplier_vertical "weapon.recoil_multiplier_vertical"
---@field slot "weapon.slot"
---@field sound "weapon.sound"
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
---@field direct_damage "projectile.direct_damage"
---@field impact_explosion "projectile.impact_explosion"
---@field expiry_explosion "projectile.expiry_explosion"

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
---@field steering_response_speed "vehicle.steering_response_speed"

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
---@field call_in_time "stratagem.call_in_time"
---@field calldown_code "stratagem.calldown_code"
---@field presentation_name "stratagem.presentation.name"
---@field presentation_name_cased "stratagem.presentation.name_cased"
---@field presentation_description "stratagem.presentation.description"
---@field presentation_icon "stratagem.presentation.icon"

---@class HD2Fields_shield
---@field durability "durability" Legacy fixed-resource field (original short-name catalog only). Shield Relay: reviewed writable, number
---@field radius "radius" Legacy fixed-resource field (original short-name catalog only). Shield Relay: reviewed writable, number
---@field entity_radius "shield.radius"
---@field entity_durability "shield.durability"
---@field recharge_delay "shield.recharge_delay"
---@field broken_recharge_delay "shield.broken_recharge_delay"
---@field recharge_rate "shield.recharge_rate"

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
---@field salvos "orbital.salvos"
---@field shells_per_salvo "orbital.shells_per_salvo"
---@field shell_interval "orbital.shell_interval"
---@field shell_interval_random "orbital.shell_interval_random"
---@field salvo_interval "orbital.salvo_interval"
---@field salvo_interval_random "orbital.salvo_interval_random"
---@field scatter "orbital.scatter"
---@field salvo_scatter "orbital.salvo_scatter"

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
---@field fire_rate "beam.fire_rate"
---@field length "beam.length"
---@field radius "beam.radius"

---@class HD2Fields_charge
---@field arc_distance_multiplier_min "charge.arc_distance_multiplier_min"
---@field arc_distance_multiplier_overcharge "charge.arc_distance_multiplier_overcharge"
---@field auto_fire_at_full "charge.auto_fire_at_full"
---@field burst_interval_seconds "charge.burst_interval_seconds"
---@field burst_shots "charge.burst_shots"
---@field damage_multiplier_min "charge.damage_multiplier_min"
---@field damage_multiplier_overcharge "charge.damage_multiplier_overcharge"
---@field explode_at_overcharge "charge.explode_at_overcharge"
---@field level_1 "charge.level_1"
---@field level_2 "charge.level_2"
---@field level_3 "charge.level_3"
---@field maximum_seconds "charge.maximum_seconds" Deprecated compatibility alias; use hd2.fields.charge.speed_multiplier_overcharge.
---@field minimum_seconds "charge.minimum_seconds" Deprecated compatibility alias; use hd2.fields.charge.speed_multiplier_min.
---@field overcharge_explosion "charge.overcharge_explosion"
---@field overcharge_limit_seconds "charge.overcharge_limit_seconds"
---@field penetration_multiplier_min "charge.penetration_multiplier_min"
---@field penetration_multiplier_overcharge "charge.penetration_multiplier_overcharge"
---@field speed_multiplier_min "charge.speed_multiplier_min"
---@field speed_multiplier_overcharge "charge.speed_multiplier_overcharge"

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
---@field level_1_self_status "heat.level_1_self_status"
---@field level_1_threshold "heat.level_1_threshold"
---@field level_2_self_status "heat.level_2_self_status"
---@field level_2_threshold "heat.level_2_threshold"
---@field level_3_self_status "heat.level_3_self_status"
---@field level_3_threshold "heat.level_3_threshold"
---@field overheat_cooldown "heat.overheat_cooldown"
---@field overheat_lock "heat.overheat_lock"
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
---@field airstrike_pattern "eagle.airstrike_pattern"
---@field drop_interval "eagle.drop_interval"
---@field fire_duration "eagle.fire_duration"
---@field attack_sweep_length "eagle.attack_sweep_length"
---@field target_radius "eagle.target_radius"
---@field attack_angle "eagle.attack_angle"
---@field payload "eagle.payload"
---@field bombs_per_strike "eagle.bombs_per_strike"
---@field strafe_rounds_per_run "eagle.strafe_rounds_per_run"

---@class HD2Fields_turret
---@field yaw_speed "turret.yaw_speed"
---@field pitch_speed "turret.pitch_speed"
---@field pitch_min "turret.pitch_min"
---@field pitch_max "turret.pitch_max"
---@field yaw_min "turret.yaw_min"
---@field yaw_max "turret.yaw_max"
---@field pitch_yaw_coupling "turret.pitch_yaw_coupling"

---@class HD2Fields_targeting
---@field range "targeting.range"
---@field side_range "targeting.side_range"
---@field rear_range "targeting.rear_range"

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
---@field damage_multiplier "zone.damage_multiplier"
---@field damage_multiplier_dps "zone.damage_multiplier_dps"

---@class HD2Fields_jump
---@field vertical_launch_velocity "jump.vertical_launch_velocity"
---@field launch_duration "jump.launch_duration"
---@field launch_forward_ratio "jump.launch_forward_ratio"
---@field sustain_thrust "jump.sustain_thrust"
---@field sustain_duration "jump.sustain_duration"
---@field sustain_forward_ratio "jump.sustain_forward_ratio"
---@field sustain_start_delay "jump.sustain_start_delay"
---@field sustain_start_speed "jump.sustain_start_speed"
---@field sustain_cutoff_speed "jump.sustain_cutoff_speed"
---@field air_control_acceleration "jump.air_control_acceleration"
---@field air_control_max_speed "jump.air_control_max_speed"
---@field takeoff_forward_speed "jump.takeoff_forward_speed"
---@field takeoff_speed "jump.takeoff_speed"
---@field takeoff_speed_alternate_stance "jump.takeoff_speed_alternate_stance"

---@class HD2Fields_deposit
---@field capacity "deposit.capacity"
---@field start_amount "deposit.start_amount"
---@field refill_amount "deposit.refill_amount"

---@class HD2Fields_mount
---@field weapon "mount.weapon"

---@class HD2Fields_rotation
---@field turn_speed "rotation.turn_speed"
---@field acceleration "rotation.acceleration"
---@field deceleration "rotation.deceleration"

---@class HD2Fields_warp
---@field distance "warp.distance"
---@field upward_bias "warp.upward_bias"
---@field downward_bias "warp.downward_bias"
---@field safe_heat_threshold "warp.safe_heat_threshold"
---@field unsafe_heat_threshold "warp.unsafe_heat_threshold"
---@field heat_per_use "warp.heat_per_use"
---@field heat_cooldown_per_second "warp.heat_cooldown_per_second"
---@field head_injury_damage "warp.head_injury_damage"
---@field left_arm_injury_damage "warp.left_arm_injury_damage"
---@field right_arm_injury_damage "warp.right_arm_injury_damage"
---@field left_leg_injury_damage "warp.left_leg_injury_damage"
---@field right_leg_injury_damage "warp.right_leg_injury_damage"

---@class HD2Fields_hover
---@field duration "hover.duration"
---@field max_horizontal_speed "hover.max_horizontal_speed"
---@field max_vertical_speed "hover.max_vertical_speed"
---@field vertical_acceleration_low_speed "hover.vertical_acceleration_low_speed"
---@field vertical_acceleration_high_speed "hover.vertical_acceleration_high_speed"
---@field vertical_speed_range_end "hover.vertical_speed_range_end"
---@field fuel_rate_low_speed "hover.fuel_rate_low_speed"
---@field fuel_rate_high_speed "hover.fuel_rate_high_speed"

---@class HD2Fields_attachment
---@field magazine_capacity "attachment.magazine_capacity"
---@field starting_magazines "attachment.starting_magazines"
---@field magazines_from_supply "attachment.magazines_from_supply"
---@field spare_magazines "attachment.spare_magazines"
---@field reload_duration "attachment.reload_duration"
---@field ergonomics_modifier "attachment.ergonomics_modifier"
---@field modifier_sway "attachment.modifier.sway"
---@field modifier_recoil_horizontal "attachment.modifier.recoil_horizontal"
---@field modifier_recoil_vertical "attachment.modifier.recoil_vertical"
---@field modifier_climb_horizontal "attachment.modifier.climb_horizontal"
---@field modifier_climb_vertical "attachment.modifier.climb_vertical"
---@field modifier_spread_horizontal "attachment.modifier.spread_horizontal"
---@field modifier_spread_vertical "attachment.modifier.spread_vertical"

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

---@class HD2Fields_gore
---@field whole_body_gib_damage "gore.whole_body_gib_damage"

---@class HD2Fields_helldiver
---@field speed_direction_factor "helldiver.speed.direction_factor"
---@field speed_aim "helldiver.speed.aim"
---@field speed_walk "helldiver.speed.walk"
---@field speed_jog "helldiver.speed.jog"
---@field speed_sprint "helldiver.speed.sprint"
---@field speed_sprint_exhausted "helldiver.speed.sprint_exhausted"
---@field speed_crouch_aim "helldiver.speed.crouch_aim"
---@field speed_crouch_walk "helldiver.speed.crouch_walk"
---@field speed_crouch_jog "helldiver.speed.crouch_jog"
---@field speed_crouch_sprint "helldiver.speed.crouch_sprint"
---@field speed_prone "helldiver.speed.prone"
---@field speed_swim "helldiver.speed.swim"
---@field stamina_sprint_duration "helldiver.stamina.sprint_duration"
---@field stamina_recover_time_standing "helldiver.stamina.recover_time_standing"
---@field stamina_recover_time_crouching "helldiver.stamina.recover_time_crouching"
---@field stamina_recover_time_prone "helldiver.stamina.recover_time_prone"
---@field stamina_recover_delay "helldiver.stamina.recover_delay"
---@field stamina_cost_jump "helldiver.stamina.cost_jump"
---@field stamina_cost_dodge "helldiver.stamina.cost_dodge"
---@field stamina_cost_climb "helldiver.stamina.cost_climb"
---@field stamina_cost_slide "helldiver.stamina.cost_slide"

---@class HD2Fields_armor_kit
---@field piece_weight_cape "armor_kit.piece_weight.cape"
---@field piece_weight_torso "armor_kit.piece_weight.torso"
---@field piece_weight_hips "armor_kit.piece_weight.hips"
---@field piece_weight_left_leg "armor_kit.piece_weight.left_leg"
---@field piece_weight_right_leg "armor_kit.piece_weight.right_leg"
---@field piece_weight_left_arm "armor_kit.piece_weight.left_arm"
---@field piece_weight_right_arm "armor_kit.piece_weight.right_arm"
---@field piece_weight_left_shoulder "armor_kit.piece_weight.left_shoulder"
---@field piece_weight_right_shoulder "armor_kit.piece_weight.right_shoulder"

---@class HD2Fields_armor_class
---@field rating "armor_class.rating"
---@field speed "armor_class.speed"
---@field stamina "armor_class.stamina"

---@class HD2Fields_armor_damage_curve
---@field at_minus_1 "armor_damage_curve.at_minus_1"
---@field at_0 "armor_damage_curve.at_0"
---@field at_1 "armor_damage_curve.at_1"
---@field at_2 "armor_damage_curve.at_2"
---@field at_3 "armor_damage_curve.at_3"

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
---@field rotation HD2Fields_rotation
---@field warp HD2Fields_warp
---@field hover HD2Fields_hover
---@field attachment HD2Fields_attachment
---@field booster HD2Fields_booster
---@field gore HD2Fields_gore
---@field helldiver HD2Fields_helldiver
---@field armor_kit HD2Fields_armor_kit
---@field armor_class HD2Fields_armor_class
---@field armor_damage_curve HD2Fields_armor_damage_curve
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

---@class HD2Image
---@field resource "image"
---@field image string
---@field mod string
local HD2Image = {}
---{kind = "image", id, mod}.
---@return table
function HD2Image:describe() end

---@class HD2Resources
---@field amr "amr"
---@field bastion "bastion"
---@field jar5 "jar5"
---@field jump_pack "jump_pack"
---@field maelstrom "maelstrom"
---@field orbital_laser "orbital_laser"
---@field shield_relay "shield_relay"
local HD2Resources = {}
---The calling mod's own image: images/<id>.png in its project, packed by the SDK build as a complete icon
---family in the mod's archive (docs/custom-images.md). A value for hd2.fields.stratagem.presentation_icon;
---the write is refused (ASSET_UNAVAILABLE) unless the whole family is loaded.
---@param id string 1 to 64 lowercase letters, digits or underscores
---@return HD2Image
function HD2Resources.image(id) end

---@class HD2Model
---@field resource "model"
---@field model string
---@field mod string
---The calling mod's own model: models/<id>.json in its project, derived by the SDK build from its base
---weapon's unit and shipped beside the vanilla resources (docs/custom-models.md). A value for a weapon
---delivery's model (hd2.custom_stratagem, delivery.family 'weapon'); never used unless it is loaded and exact.
---@param id string 1 to 64 lowercase letters, digits or underscores
---@return HD2Model
function HD2Resources.model(id) end

---@alias HD2EventName "mission_started"|"mission_ended"|"player_spawned"|"player_died"|"entity_spawned"|"entity_died"|"entity_killed"|"entity_damaged"|"player_damaged"|"player_healed"|"player_fired"|"player_kill_credited"|"player_hit"|"player_damage_dealt"|"weapon_equipped"|"weapon_unequipped"|"weapon_changed"|"explosion"|"entity_damage_pre"|"key_down"|"key_up"

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
---@field state "active"|"disabled"|"complete"|"cancelled"|"expired"|"failed"|"rejected"
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
---Pause a frame callback (hd2.on_frame); no effect on timers.
---@return HD2Timer
function HD2Timer:disable() end
---Resume a paused frame callback.
---@return HD2Timer
function HD2Timer:enable() end

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

---hd2.input: keybinds (bound chords) and any key's state. Read-only: nothing is consumed.
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
---Key names accepted in chords; with raw=true also the names only down/pressed/released accept (CTRL, SHIFT, ALT, MOUSE1, MOUSE2).
---@param raw? boolean
---@return string[]
function HD2Input.keys(raw) end
---Whether a key is held now (any name of hd2.input.keys(true)). Only while the game window has the focus; the game still receives the key. Unknown names raise.
---@param key string
---@return boolean
function HD2Input.down(key) end
---True during the one update tick in which the key went down (sampled once per tick, before events, timers and frame callbacks). A key is followed from its first query on.
---@param key string
---@return boolean
function HD2Input.pressed(key) end
---True during the one update tick in which the key came up.
---@param key string
---@return boolean
function HD2Input.released(key) end
---Whether the game window has the keyboard focus.
---@return boolean
function HD2Input.focused() end
---The cursor in the game window (client pixels from the top-left), or nil and why when the window does not have the focus.
---@return HD2Mouse|nil, string|nil
function HD2Input.mouse() end
---EXPERIMENTAL (r51). The mouse wheel this update tick in notches (+ up, - down; fractions for smooth wheels), 0 when it did not move. Read from the engine's wheel axis and, while queried, a read-only message hook on the game window's thread (WM_MOUSEWHEEL and raw input); nothing is consumed.
---@return number
function HD2Input.wheel() end
---Diagnostics of hd2.input.wheel: {hooked, disabled (why the hook is off), source (the first source that delivered a notch), engine (the engine axis is readable)}.
---@return table
function HD2Input.wheel_status() end
---EXPERIMENTAL (r52). Keep the game from acting on input while a mod window is open: spec = {keyboard = true, mouse = true}, renewed every update (a 0.5 s lease); false stops. Key presses, characters, mouse button presses and the wheel become WM_NULL before the game's window sees them; releases always pass. Mods keep reading input through GetAsyncKeyState / GetCursorPos.
---@param spec table|false
---@return boolean, string|nil
function HD2Input.block(spec) end

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

---One source of a player stat: the entity type the game recorded it under. Exact attribution from the game's own accounting: a stat is added under the source entity the game passes to it.
---@class HD2StatSource
---@field type string Source entity type hash (16 hex digits).
---@field name string|nil The weapon, throwable or stratagem name when catalogued.
---@field shots integer|nil Shots (player_fired).
---@field kills integer|nil Kills (player_kill_credited).
---@field hits integer|nil Projectile hits (player_hit).
---@field damage integer|nil Damage dealt (player_damage_dealt).
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
---@field kind string 'explosion', 'explosion_assets', 'projectile', 'projectile_assets', 'status', 'injure', 'heal_limb', 'heal_limbs', 'add_velocity'.
---@field owner string The mod that requested it.
---@field status "pending"|"waiting_for_assets"|"ready"|"requested"|"refused"|"cancelled" requested: the game accepted the request this frame.
---@field code string|nil Why it was refused (UNKNOWN_EXPLOSION, UNKNOWN_PROJECTILE, UNKNOWN_STATUS, ASSET_UNKNOWN, ASSET_UNAVAILABLE, NOT_IN_MISSION, HOST_ONLY, NO_LOCAL_AVATAR, RATE_LIMITED, CAUSE_DEPTH, QUEUE_FULL, INVALID_POSITION, INVALID_DIRECTION, INVALID_TARGET, INVALID_AMOUNT, INVALID_OPTION, TARGET_GONE, FIRER_UNSUPPORTED, EXPLOSION_UNAVAILABLE, PROJECTILE_UNAVAILABLE, STATUS_UNAVAILABLE; injure: NOT_LOCAL_PLAYER, UNKNOWN_LIMB, NOT_GAME_THREAD, AVATAR_DOWNED, AVATAR_DEAD, NOT_A_HELLDIVER, LIMB_UNAVAILABLE, INJURY_UNAVAILABLE; heal_limb: PARTIAL_UNSUPPORTED, LIMB_HEAL_UNAVAILABLE; add_velocity: INVALID_VELOCITY, TOO_FAST, VELOCITY_UNAVAILABLE).
---@field reason string|nil
---@field explosion string|nil The explosion (a named explosion or a weapon name).
---@field projectile string|nil The projectile (its weapon).
---@field effect string|nil The status id.
---@field limb string|nil The injured limb (injure).
---@field zone string|nil The limb's damage zone (injure).
---@field damage integer|nil The damage requested (injure).
---@field healed string[]|nil The limbs heal_limbs restored.
---@field velocity HD2Position|nil The velocity change requested (add_velocity, m/s).
---@field after HD2Position|nil The avatar velocity Runtime set (add_velocity, m/s).
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
---@field allow_unverified_effect boolean|nil Required for a catalogued explosion outside the reviewed spawn set (docs/explosions.md).
local HD2ExplosionOptions = {}

---hd2.explosions.list filter (docs/explosions.md): every key optional.
---@class HD2ExplosionFilter
---@field family "weapon"|"support_weapon"|"throwable"|"stratagem"|"backpack"|"vehicle"|"enemy"|"entity"|nil The owner's family.
---@field owner string|nil A case-insensitive substring of an owner's name.
---@field search string|nil A case-insensitive substring of the name or label.
---@field shared boolean|nil More than one owner requests the row.
---@field payload boolean|nil Usable as a weapon's impact or expiry explosion (its package is known).
---@field spawn boolean|nil hd2.explosions.spawn can request it.
---@field package_known boolean|nil A package that ships its effect is known.
---@field reviewed_spawn boolean|nil In the reviewed spawn set (needs no acknowledgement to spawn).
local HD2ExplosionFilter = {}

---One catalogued explosion (hd2.explosions.list); no raw ids.
---@class HD2ExplosionEntry
---@field name string Semantic id: <family>/<owner>/<role>, e.g. weapon/r36_eruptor/impact.
---@field label string Readable name, e.g. R-36 Eruptor (impact).
---@field family string The owner's family.
---@field evidence "data"|"code"|"chain" How the owners were proven.
---@field shared boolean More than one owner requests the row: edits need allow_shared.
---@field owners integer How many owners request it (describe() lists them).
---@field package_known boolean A package that ships its effect is known.
---@field mission_package boolean Its effect ships in the mission effects package (resident in every mission; never loaded).
---@field payload boolean Usable as a weapon's impact or expiry explosion.
---@field spawn boolean hd2.explosions.spawn can request it.
---@field reviewed_spawn boolean In the reviewed spawn set.
---@field legacy_name string|nil Its reviewed name (a weapon or a named explosion).
---@field stats table inner_radius, outer_radius, shockwave_radius, shrapnel_count, standard_damage, durable_damage, ap_direct, ap_slight, ap_large, ap_extreme, demolition, stagger, push_force, shrapnel, arc, damage_row.
local HD2ExplosionEntry = {}

---hd2.explosion(name): a catalogued explosion (docs/explosions.md). The target of the explosion.* fields (allow_unverified_effect; allow_shared for a shared row), a value of terminal.explosion and of attack output explosion slots (allow_unverified_reference and allow_unverified_effect), and an argument of hd2.explosions.spawn / prepare.
---@class HD2CatalogueExplosion
---@field resource "explosion"
---@field explosion string Its semantic id.
local HD2CatalogueExplosion = {}
---The list entry plus owners, package and editable fields.
---@return table
function HD2CatalogueExplosion:describe() end
---The editable fields: {semanticFieldId, currentDefault, editable, reason, shared, range, acknowledgements}.
---@return table[]
function HD2CatalogueExplosion:fields() end

---hd2.explosions: request a catalogued explosion (docs/event-scripting.md).
---@class HD2Explosions
local HD2Explosions = {}
---Request a catalogued explosion at a position: a named explosion ('Hellbomb' = the NUX-223 Hellbomb, 'B-100 Portable Hellbomb'), a weapon's catalogued explosion, or any explosion of the catalogue (hd2.explosions.list({spawn = true}); outside the reviewed set with opts.allow_unverified_effect). Host only, in a mission, credited to the local player; loads the explosion's package first when needed (the mission effects package is only checked). Unknown explosions, raw ids and unknown packages are refused.
---@param explosion HD2ExplosionName|HD2WeaponName|HD2Explosion|HD2CatalogueExplosionName|HD2CatalogueExplosion
---@param opts HD2ExplosionOptions
---@return HD2ActionHandle
function HD2Explosions.spawn(explosion, opts) end
---The weapon's catalogued explosion handle (impact, else expiry).
---@param weapon HD2WeaponName
---@return HD2Explosion|nil, string|nil
function HD2Explosions.of(weapon) end
---Load the explosion assets now (status ready or waiting_for_assets).
---@param explosion HD2ExplosionName|HD2WeaponName|HD2Explosion|HD2CatalogueExplosionName|HD2CatalogueExplosion
---@param opts? HD2ExplosionOptions
---@return HD2ActionHandle
function HD2Explosions.prepare(explosion, opts) end
---Every catalogued explosion (docs/explosions.md), optionally filtered. No raw ids.
---@param filter? HD2ExplosionFilter
---@return HD2ExplosionEntry[]
function HD2Explosions.list(filter) end
---One catalogued explosion: the list entry plus owners, package and editable fields; nil and the reason when unknown.
---@param name HD2CatalogueExplosionName|HD2CatalogueExplosion
---@return table|nil, string|nil
function HD2Explosions.describe(name) end
---The reviewed spawn set (0.29's hd2.explosions.list()), each with its catalogue name.
---@return {name: string, weapon: string|nil, source: "behavior"|"weapon", assets_known: boolean, objective: boolean|nil, catalogue: string|nil}[]
function HD2Explosions.reviewed() end

---hd2.actions: what event scripts can make the game do.
---@class HD2Actions
local HD2Actions = {}
---Heal the local player (clamped to maximum health).
---@param amount number
---@param opts? {owner?: string}
---@return number|nil, string|nil
function HD2Actions.heal(amount, opts) end
---Injure a limb of the LOCAL player's avatar through the game's own damage request (the VG-70 Variable's self-damage path): the limb zone loses the damage (an injured limb at 0) and main health loses the zone's share, applied by the game later in the frame. Local player only (each machine injures its own avatar; no host needed), in a mission, alive and not downed; damage a whole number from 1 to the limb zone's health (head 85, chest 60, hands 35, knees 45); 12 at once and 10 per second per mod. Not live-tested.
---@param player HD2PlayerHandle
---@param limb "head"|"chest"|"l_hand"|"r_hand"|"l_knee"|"r_knee"
---@param damage integer
---@param opts? {owner?: string}
---@return HD2ActionHandle
function HD2Actions.injure(player, limb, damage, opts) end
---Every limb hd2.actions.injure accepts. Offline.
---@return {name: string, zone: string, max_damage: integer, affects_main_health: number}[]
function HD2Actions.limbs() end
---Restore one limb of the LOCAL player's avatar to full through the game's own zone restore (an injured limb is healed; main health unchanged). The game has no partial limb heal: amount is 'full' (default) or a whole number covering what the limb is missing (PARTIAL_UNSUPPORTED otherwise). Local player only, in a mission, alive and not downed; 6 at once and 2 per second per mod. Not live-tested.
---@param player HD2PlayerHandle
---@param limb "head"|"chest"|"l_hand"|"r_hand"|"l_knee"|"r_knee"
---@param amount? "full"|integer
---@param opts? {owner?: string}
---@return HD2ActionHandle
function HD2Actions.heal_limb(player, limb, amount, opts) end
---heal_limb(player, limb) for all six limbs, one request.
---@param player HD2PlayerHandle
---@param opts? {owner?: string}
---@return HD2ActionHandle
function HD2Actions.heal_limbs(player, opts) end
---Add a world-space velocity (m/s, +Z up) to the LOCAL player's avatar through the game's own motion velocity setter: its current velocity plus the change. The change is at most 25 m/s and the result at most 50 m/s; 4 at once and 2 per second per mod. What ground movement does with it the next frame is not proven: an upward change is the reliable case. Not live-tested.
---@param player HD2PlayerHandle
---@param change HD2Vector3
---@param opts? {owner?: string}
---@return HD2ActionHandle
function HD2Actions.add_velocity(player, change, opts) end
---Use one supply of the LOCAL player's worn Supply Pack on that player, exactly as the pack's own key does (the game plays its animation, spends one supply and refills ammunition, with its own network sync; Runtime writes nothing). Refused when no Supply Pack is worn, it is empty, the player is busy or nothing needs ammunition. Local player only, in a mission; rate-limited per mod. Not live-tested.
---@param player HD2PlayerHandle
---@param opts? {owner?: string}
---@return HD2ActionHandle
function HD2Actions.resupply_from_pack(player, opts) end
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

---hd2.projectiles: fire a catalogued weapon projectile, or make a weapon's shots home (docs/event-scripting.md, docs/projectile-homing.md).
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
---Make the LOCAL player's own shots of a weapon home in flight: each shot turns toward the living enemy (or other player's Helldiver) closest to its line inside the cone and range, by at most turn_rate per second, keeping its speed. One guarded write of that shot's own velocity per update; the weapon, its projectile row and every other projectile are never written. Solo unless opts.multiplayer (experimental: other machines draw the shot flying straight, with its hit where it homed). Lasts until stop() or the session ends. The weapon is a name from homing_list() (or a catalogued projectile output id). Not live-tested.
---@param weapon string
---@param opts? HD2HomingOptions
---@return HD2HomingHandle
function HD2Projectiles.homing(weapon, opts) end
---Every weapon whose shots can home, with the projectile types it fires (offline).
---@return {name: string, categories: string[], types: integer[]}[]
function HD2Projectiles.homing_list() end
---Every active homing configuration (one per weapon and projectile type) with this mission's counts.
---@return {owner: string, weapon: string, type: integer, target: string, shots: integer, steered: integer, writes: integer}[]
function HD2Projectiles.homing_status() end
---Modify the LOCAL player's own shots of a weapon (DEVELOPMENT, solo; docs/projectile-shots.md): each shot's own copy is multiplied once, right after it is fired: damage (each direct hit's damage; explosions are not scaled), armor_penetration (each direct hit's penetration lanes), speed (velocity and reference speed together), gravity, drag. The weapon, its projectile row, every DamageInfo row and every other weapon firing the same projectile (the Liberator Carbine for the AR-23 Liberator) stay vanilla. Lasts until stop() or the session ends. The weapon is a name from homing_list(). Not live-tested.
---@param weapon string
---@param opts? HD2ShotOptions
---@return HD2ShotHandle
function HD2Projectiles.modify_shots(weapon, opts) end
---Every active shot configuration with this mission's counts.
---@return {owner: string, weapon: string, changes: table<string, number>, shots: integer, modified: integer}[]
function HD2Projectiles.modify_shots_status() end

---@class HD2HomingOptions
---@field target "enemy"|"friendly"|nil What the shots home on: a living catalogued enemy (default) or another player's living Helldiver (never the shooter).
---@field turn_rate number|nil Degrees per second the shot may turn (1..1440, default 90). Fast bullets need a high rate.
---@field cone number|nil Half angle in degrees around the shot's direction a target must be inside to be acquired (1..180, default 30).
---@field range number|nil Metres from the shot a target may be (1..500, default 100).
---@field arm_distance number|nil Metres the shot flies straight before it steers (0..100, default 2).
---@field aim_height number|nil Metres above the target's root it aims at (-5..10, default 1).
---@field retarget boolean|nil Acquire another target when the first dies (default true).
---@field multiplayer boolean|nil Also steer with other players in the game (experimental; default false: solo only).
---@field label string|nil Name used in the log (at most 64 characters).
---@field owner string|nil Mod id (defaults to the calling mod).
local HD2HomingOptions = {}

---A homing configuration. A refusal never raises: status is refused with a code and a reason.
---@class HD2HomingHandle
---@field kind string 'projectile_homing'.
---@field owner string The mod that configured it.
---@field status string 'active', 'stopped' or 'refused'.
---@field code string|nil Why it was refused (UNKNOWN_WEAPON, INVALID_OPTION, ALREADY_HOMING, LIMIT).
---@field reason string|nil The refusal in words.
---@field weapon string|nil The weapon.
---@field types integer[]|nil The projectile types its shots are.
---@field target string|nil 'enemy' or 'friendly'.
local HD2HomingHandle = {}
---Stop homing (shots in flight fly on as they are).
---@return HD2HomingHandle
function HD2HomingHandle:stop() end
---This mission so far: own shots seen, steered, writes, target locks, shots that were not this player's, and why shots flew straight.
---@return {shots: integer, steered: integer, writes: integer, locks: integer, others: integer, refused: table<string, integer>}|nil
function HD2HomingHandle:stats() end
---A copy for logs.
---@return table
function HD2HomingHandle:describe() end

---@class HD2ShotOptions
---@field damage number|nil Multiplier of each direct hit's damage (0.01..100).
---@field armor_penetration number|nil Multiplier of each direct hit's penetration lanes (0.1..10; rounded by the game).
---@field speed number|nil Multiplier of the shot's velocity and reference speed (0.1..10).
---@field gravity number|nil Multiplier of the shot's gravity (0..20).
---@field drag number|nil Multiplier of the shot's drag (0..20).
---@field on_shot fun(event: table)|nil Called for each of the weapon's shots seen: kind 'modified' or 'untouched' (every multiplier 1); before/after hold damage_multiplier, penetration_multiplier, speed, reference_speed, gravity, drag, distance, damage = {id, standard, durable, armor_penetration}.
---@field label string|nil Name used in the log (at most 64 characters).
---@field owner string|nil Mod id (defaults to the calling mod).
local HD2ShotOptions = {}

---A shot configuration. A refusal never raises: status is refused with a code and a reason.
---@class HD2ShotHandle
---@field kind string 'projectile_shots'.
---@field owner string The mod that configured it.
---@field status string 'active', 'stopped' or 'refused'.
---@field code string|nil Why it was refused (UNKNOWN_WEAPON, INVALID_OPTION, ALREADY_MODIFIED, LIMIT).
---@field reason string|nil The refusal in words.
---@field weapon string|nil The weapon.
---@field types integer[]|nil The projectile types its shots are.
local HD2ShotHandle = {}
---New multipliers for the next shots (omitted ones become 1); nil, code, reason when refused.
---@param opts HD2ShotOptions
---@return HD2ShotHandle|nil
function HD2ShotHandle:set(opts) end
---Stop modifying (shots already written keep their values).
---@return HD2ShotHandle
function HD2ShotHandle:stop() end
---This mission so far: own shots seen, modified, writes, untouched, others (not this player's), other_sources (another weapon), and why shots stayed vanilla.
---@return {shots: integer, modified: integer, writes: integer, untouched: integer, others: integer, other_sources: integer, refused: table<string, integer>}|nil
function HD2ShotHandle:stats() end

---@class HD2SpawnWeightOptions
---@field allow_unverified_effect boolean Required (true) until the live test passes.
---@field difficulties integer[]|nil Only these difficulties (1..10); default all ten.
---@field label string|nil Name used in the log (at most 64 characters).
---@field owner string|nil Mod id (defaults to the calling mod).
local HD2SpawnWeightOptions = {}

---An enemy spawn weight setting. A refusal never raises: status is refused with a code and a reason. status is live.
---@class HD2SpawnWeightHandle
---@field kind string 'enemy_spawn_weight'.
---@field owner string The mod that set it.
---@field status string 'applied', 'pending', 'deferred' (waits until no mission runs), 'stopping', 'stopped', 'conflict' (another writer changed a row), 'unavailable' or 'refused'.
---@field code string|nil Why it was refused (ACKNOWLEDGEMENT_REQUIRED, UNKNOWN_ENEMY, INVALID_MULTIPLIER, INVALID_OPTION, ALREADY_SET, NOT_IN_A_ROSTER) or the conflict.
---@field reason string|nil The refusal in words.
---@field enemy string The enemy as named.
---@field multiplier number The multiplier.
---@field types string[]|nil The entity types (16 hex digits) it covers.
local HD2SpawnWeightHandle = {}
---Write the vanilla weights back (a type going from 0 to positive waits until no mission runs).
---@return HD2SpawnWeightHandle
function HD2SpawnWeightHandle:stop() end
---A copy for logs, with each type's status.
---@return table
function HD2SpawnWeightHandle:describe() end

---hd2.enemies: how often each enemy type spawns (docs/enemy-spawns.md).
---@class HD2Enemies
local HD2Enemies = {}
---Scale an enemy type's weight in every spawn group of the game's spawn rosters (0..10): 0 = never picked, k = k times its vanilla weight within the groups it shares. Changes which enemies spawn, not how many. A weight never goes from 0 to positive during a mission (it waits for the ship). The mission host's rosters decide. Not live-tested: needs allow_unverified_effect.
---@param enemy string
---@param multiplier number
---@param opts HD2SpawnWeightOptions
---@return HD2SpawnWeightHandle
function HD2Enemies.spawn_weight(enemy, multiplier, opts) end
---Every roster row with its ten vanilla weights (offline).
---@param filter? {faction?: string, enemy?: string}
---@return {enemy: string, entity: string, id: string|nil, faction: string, index: integer, group: string, weights: number[]}[]
function HD2Enemies.spawn_list(filter) end
---Every active spawn weight setting.
---@return {owner: string, enemy: string, entity: string, multiplier: number, status: string, rows: integer}[]
function HD2Enemies.spawn_status() end

---One modifier row of a passive {key, type, value}: what EntityAttribute returns to a reader.
---@class HD2PassiveModifier
---@field key string The row's key, 8 hex digits (a thin hash).
---@field key_name string The research's semantic name of the key (e.g. 'throw_range', 'movement_noise'; 'unknown_<key>' where no reader or text is known).
---@field type string 'Set', 'Add', 'Multiply' or 'Time': how the reader combines value with its default (the reader's own code).
---@field value number The value.
---@field text string|nil The game's effect text (list() only).
---@field reader string|nil list() only: the research's reader status (research/passive-effects-F5FEE03DCFDB.json): 'direct', 'data-driven' (both follow a swap), 'description-only' (stat-driven at spawn: reload, ammo, sidearm; a swap never changes it), 'armor rating' (follows the worn kit), 'none found' (Adreno's revive) or 'no effect'.
---@field follows boolean|nil list() only: whether the row follows a slot swap (nil: unknown or no effect).
---@field observable string|nil list() only: what to observe in play after a swap (the research).
---@field note string|nil list() only: why the row does not follow a swap.
---@field armor_slot_only boolean|nil list() only: every reader of the key reads the armor slot only (flags 1): a second-slot copy never reaches it.
---@field source string|nil effective only: 'armor' or 'second' (the helmet slot).
---@field passive integer|nil effective only: the passive id the row comes from.
---@field name string|nil effective only: that passive's name.
local HD2PassiveModifier = {}

---One of the game's 32 armor passives (research/player-attributes-F5FEE03DCFDB.json).
---@class HD2Passive
---@field id integer The passive id (0-41; 4 and 22-30 are unused).
---@field name string The game's own name (e.g. 'SERVO-ASSISTED').
---@field description string The game's own description (its effect lines; #BONUS as the game holds it).
---@field modifiers HD2PassiveModifier[] Its rows in the game's order.
---@field effect_package boolean It has an effect package (17 Integrated Explosives, 19 Adreno-Defibrillator): set() loads it through core/assets (shared) before the write.
---@field package string|nil The passive +0x30 key (8 hex digits) when it has an effect package; package_info has the package.
---@field armor_kits integer How many armor kits carry it.
---@field follows_swap 'full'|'partial'|'unknown' Whether its effects follow a slot swap: 'full', 'partial' (some rows follow the kit worn instead: see note), 'unknown' (19: the revive mechanism was not located).
---@field note string|nil What does not follow a swap, in words.
---@field stats {stat: integer, name: string, add: number, mul: number, described_by: string|nil}[] Its spawn-time stat rows (the kit worn at spawn applies them; a swap never changes them).
---@field package_info HD2PassivePackage|nil Its effect package.
local HD2Passive = {}

---hd2.passives: every armor passive of the game (offline; docs/armor-passives.md).
---@class HD2Passives
local HD2Passives = {}
---Every passive of the game with its modifier rows, by id (the research's table; no game read).
---@return HD2Passive[]
function HD2Passives.list() end
---One passive by its game name (any case) or id; nil, UNKNOWN_PASSIVE, reason otherwise.
---@param passive string|integer
---@return HD2Passive|nil, string?, string?
function HD2Passives.find(passive) end

---@class HD2PassiveRef
---@field id integer The passive id.
---@field name string Its game name.
local HD2PassiveRef = {}

---@class HD2KitRef
---@field id string The kit id (0x + 8 hex digits).
---@field index integer|nil Its index in the game's kit table (hd2.armor_kit(index)).
---@field name string|nil Its game name (research/armor-names-F5FEE03DCFDB.json; nil for the 33 the game's text does not name).
---@field slot 'armor'|'helmet'|'cape'|nil Its slot.
---@field weight 'light'|'medium'|'heavy'|nil An armor kit's weight (its armor pieces').
---@field passive integer|nil The kit's own passive (kit +0x1C): what the game derives the slot from.
local HD2KitRef = {}

---The local player's passives as the game reads them now (hd2.player_passives()).
---@class HD2PlayerPassives
---@field entity integer The player entity (an avatar is mapped to it by the game).
---@field record integer Its applied customization record (0-3).
---@field armor_kit HD2KitRef The armor kit.
---@field helmet_kit HD2KitRef The helmet kit (no vanilla helmet has a passive).
---@field cape_kit HD2KitRef The cape kit.
---@field armor_passive HD2PassiveRef The armor slot (record +0x3C).
---@field helmet_passive HD2PassiveRef The helmet slot (record +0x38), where set() puts the second passive; 0 = none.
---@field derived {armor: integer, second: integer} The kits' own passives (what the game puts back on a kit change).
---@field overridden boolean A slot differs from its kit.
---@field runtime string|nil The mod holding an override.
---@field effective HD2PassiveModifier[] The rows a flags=3 reader finds, in order: the armor passive's, then the second passive's keys the armor lacks (the first row per key wins; no stacking).
local HD2PlayerPassives = {}

---@class HD2PlayerPassiveSpec
---@field armor HD2PassiveName|integer|nil The armor passive (name or id); nil: the kit's own.
---@field second HD2PassiveName|integer|false|nil A second passive in the helmet slot; nil or false: none (the kit's). INTEGRATED EXPLOSIVES is refused here (ARMOR_SLOT_ONLY).
---@field owner string|nil Mod id (defaults to the calling mod).
---@field allow_unverified_effect boolean Required (true) except for an armor-slot swap alone to a live-proven passive (SCOUT, ENGINEERING KIT, SERVO-ASSISTED); without it set() is refused ACKNOWLEDGEMENT_REQUIRED.
local HD2PlayerPassiveSpec = {}

---An armor passive override. A refusal never raises: status is refused with a code and a reason.
---@class HD2PlayerPassiveHandle
---@field kind string 'player_passives'.
---@field owner string The mod that set it.
---@field status string 'active', 'waiting' (no record yet), 'waiting_for_assets' (an effect package loads first through core/assets; nothing is written until it is resident), 'suspended' (several players or the package is gone; the kit's values are back), 'lost' (something else wrote the slot), 'replaced', 'stopped' or 'refused'.
---@field code string|nil Why (INVALID_OPTION, ACKNOWLEDGEMENT_REQUIRED, UNKNOWN_PASSIVE, SAME_PASSIVE, ARMOR_SLOT_ONLY, ASSET_UNAVAILABLE, PACKAGE_NOT_RESIDENT, NOT_SOLO, ALREADY_SET, UNEXPECTED_STATE, NOT_PRIVATE, GUARD_REJECTED, UNSUPPORTED_BUILD; waiting: UNAVAILABLE, NO_PLAYER, NO_RECORD, NOT_READY).
---@field reason string|nil The reason in words.
---@field armor HD2PassiveRef|nil The armor passive asked for.
---@field second HD2PassiveRef|nil The second passive asked for.
---@field notes string[]|nil What the chosen passives do not carry over a swap (reload, ammo, sidearm stats, armor rating, Adreno's unlocated revive).
local HD2PlayerPassiveHandle = {}
---Stop holding: the kit's own passives go back into the slots that still hold this override's values.
---@return HD2PlayerPassiveHandle
function HD2PlayerPassiveHandle:stop() end
---The override and how many times it was written (re-applications after kit changes included).
---@return {kind: string, owner: string, status: string, code: string|nil, reason: string|nil, armor: HD2PassiveRef|nil, second: HD2PassiveRef|nil, applications: integer}
function HD2PlayerPassiveHandle:describe() end

---hd2.player_passives: call it for the local player's passives (HD2PlayerPassives, or nil, code, reason); set() overrides them (DEVELOPMENT, solo; docs/armor-passives.md).
---@class HD2PlayerPassivesApi
local HD2PlayerPassivesApi = {}
---Override the local player's armor passive and/or add a second passive in the helmet slot: one guarded 4-byte write per slot on the player's own record, re-applied after each kit change, until stop(). A passive with an effect package (17, 19) is loaded first through core/assets, shared with compatible peers (status waiting_for_assets; ASSET_UNAVAILABLE on failure). Readers that ignore the helmet slot (flinch, one chest-bleed site, Integrated Explosives: refused there) never see the second passive; overlapping keys do not stack; reload, ammo, sidearm stats and the armor rating follow the kit worn. Solo only (NOT_SOLO). Live-proven: the armor-slot swap to SCOUT, ENGINEERING KIT, SERVO-ASSISTED.
---@param spec HD2PlayerPassiveSpec
---@return HD2PlayerPassiveHandle
function HD2PlayerPassivesApi.set(spec) end
---The held override, or nil.
---@return {owner: string, status: string, code: string|nil, reason: string|nil, armor: HD2PassiveRef|nil, second: HD2PassiveRef|nil, applications: integer}|nil
function HD2PlayerPassivesApi.status() end

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

---Options of hd2.pelican.spawn.
---@class HD2PelicanOptions
---@field position HD2Vector3|HD2Position Where it hovers: its anchor, the point the game's flight hovers over (at a height of its own) (required).
---@field approach {distance: number|nil, height: number|nil}|nil Where it is created: distance metres back from the position along its heading (default 250, 0 to 1000) and height metres up (default 80, 0 to 500).
---@field hover number|nil Seconds it stays after its release (0 < hover <= 120); nil: the game's own (it leaves at once).
---@field facing {x: number, y: number}|nil Its horizontal heading at creation; nil: from the local player toward the position.
---@field on_event fun(event: HD2PelicanEvent)|nil Every step: spawned, stage, hovering, released, held, departing, gone; refused, unverified, hold_refused or cargo (never expected) with code and reason. With a gun also gun_armed (turret, round, projectile, rpm, credit), gun_refused (stage, code, reason), gun_ended.
---@field gun HD2PelicanGun|nil Its chin gun's OWN configuration (development, solo host): only this Pelican's own copies and records change, never a shared definition.
---@field orbit HD2PelicanOrbit|nil It circles its anchor once it holds there (needs hover).
---@field credit_to HD2PlayerHandle|nil The local player: its chin gun's kills credit that player (needs gun; solo host).
---@field call HD2CustomStratagemCall|nil A custom stratagem call: the Pelican and its chin turret are associated with it.
---@field owner string|nil Mod id (defaults to the calling mod).
local HD2PelicanOptions = {}

---One step of a Runtime Pelican (hd2.pelican.spawn on_event).
---@class HD2PelicanEvent
---@field kind "spawned"|"stage"|"hovering"|"released"|"held"|"departing"|"gone"|"refused"|"unverified"|"hold_refused"|"cargo"
---@field entity integer|nil The Pelican's entity id.
---@field code string|nil A refusal's code.
---@field reason string|nil A refusal's reason.
---@field seconds number|nil Seconds since it was spawned.
---@field from integer|nil stage: the flight stage before.
---@field to integer|nil stage: the flight stage now.
---@field position HD2Vector3|nil Its position at that step.
---@field target HD2Vector3|nil Its flight target at that step (its hover point once hovering).
local HD2PelicanEvent = {}

---A Runtime Pelican request (hd2.pelican.spawn).
---@class HD2Pelican
---@field status "pending"|"requested"|"refused"|"unverified"|"arriving"|"hovering"|"released"|"held"|"departing"|"gone"
---@field code string|nil Why it was refused.
---@field reason string|nil
---@field entity integer|nil The Pelican's entity id once spawned.
---@field owner string The mod that asked.
---@field hover number|nil The hover time asked.
---@field held number|nil The hover time applied once held.
---@field approach {distance: number, height: number}|nil The approach used.
---@field spawn_point HD2Vector3|nil Where it is created.
local HD2Pelican = {}
---True while requested or alive.
---@return boolean
function HD2Pelican:alive() end
---The live Pelican now (read-only), or nil when it is not alive.
---@return {entity: integer, stage: integer, released: boolean, position: HD2Vector3|nil, hover_point: HD2Vector3|nil, anchor: HD2Vector3|nil, cargo: boolean}|nil
function HD2Pelican:state() end
---A snapshot of the request.
---@return table
function HD2Pelican:describe() end

---hd2.pelican: the game's own transport Pelican, summoned empty (docs/event-scripting.md).
---@class HD2Pelicans
local HD2Pelicans = {}
---Summon an empty transport Pelican to hover over a position: it is created approach metres back and up, flies in, hovers over the position (its anchor, which the game keeps in the Pelican's own drop-position record) and leaves; with hover it stays that many seconds after its release (one guarded write of its own release time). The game's own spawn request, with no cargo and no associated entity. Host only, in a mission, at most 4 at a time; made in the Runtime's next update. A refusal never raises (status refused, code, reason).
---@param opts HD2PelicanOptions
---@return HD2Pelican
function HD2Pelicans.spawn(opts) end
---The Runtime Pelicans alive now (entity ids).
---@return integer[]
function HD2Pelicans.active() end
---What hd2.pelican can do on this build, and its limits.
---@return table
function HD2Pelicans.status() end

---The chin gun of a Runtime Pelican (hd2.pelican.spawn gun; development, solo host).
---@class HD2PelicanGun
---@field round "standard"|"ap4"|nil standard: its own (the MG-43's 148); ap4: the MG-206 Heavy Machine Gun's AP4 round 275.
---@field behave_as "gatling_sentry"|nil The Gatling Sentry's AI, casing and rate, with the Runtime target lock.
---@field rate_multiplier 1|1.5|2|nil Times the Gatling Sentry's rate read from the game (needs behave_as).
---@field spread number|nil Its spread in mrad (above 0, at most 100), on its own WeaponData record.
---@field recoil false|nil false: no aim recoil.
---@field unlimited_ammo true|nil Its own magazine at the safe maximum (2047), refilled below 1500.
---@field sound string|nil A firing sound of the catalogue (hd2.sounds.list(): a name of kind shot or loop, for example 'vehicle/maelstrom/main_gun', 'sentry/gatling', 'vehicle/bastion/hmg'; 'maelstrom_main_gun' still works) on its own weapon copy; nil or 'pelican/chin_autocannon': its own. The package of the stratagem that provides its bank is loaded first (a resident-only sound only while its package is resident); other machines apply it on their own copies. See docs/weapon-sounds.md.
---@field face_target true|nil The body turns toward the locked target (needs behave_as).
local HD2PelicanGun = {}

---A Runtime Pelican circling its anchor (hd2.pelican.spawn orbit).
---@class HD2PelicanOrbit
---@field radius number|nil Metres from the anchor (5 to 150, default 40).
---@field altitude number|nil Metres above the anchor (10 to 150, default 60).
---@field duration number|nil Seconds (1 to 120, default 55).
---@field period number|nil Seconds a lap (10 to 600, default 30).
---@field entry number|nil Seconds of the spiral climb into the orbit (0 to 60, default 15).
local HD2PelicanOrbit = {}

---One firing sound of the weapon sound catalogue (hd2.sounds; docs/weapon-sounds.md). No event, bank or package id.
---@class HD2WeaponSound
---@field name string Its semantic name, <family>/<weapon>[/<part>] (what gun.sound takes).
---@field label string A human name (the weapon, mount or unit).
---@field kind "shot"|"loop" shot: an event per shot (MIDI notes when midi); loop: started when the gun starts firing and stopped when it stops.
---@field family string The first part of its name: pelican, vehicle, sentry, emplacement, eagle, backpack, support, primary, secondary, automaton, illuminate, seaf, objective or other.
---@field stratagem string|nil The stratagem whose call-in package provides its bank (loaded for a Pelican gun that takes it), or nil.
---@field resident_only boolean No stratagem provides its bank: usable only while the game has a package listing it resident (for example while a player carries that weapon).
---@field designed_rpm number The rate its weapon was designed for (its record's rate slot).
---@field range_m number|nil How far its farthest layer carries, in metres (a heuristic reading of its bank's attenuation curves).
---@field midi boolean Its shots post MIDI notes (several per shot, one shot interval apart).
---@field pelican_default boolean The Pelican chin gun's own sound (taking it changes nothing).
local HD2WeaponSound = {}

---One sound event of the full catalogue (hd2.sounds.list{catalogue = 'events'}; docs/sounds.md): every Wwise event of the build, named <family>/<bank>/<event> from evidence (the event's own Wwise name where the game's code or data names it, else its id as eight hex digits).
---@class HD2SoundEvent
---@field name string Its catalogue name (what play, describe and asset take).
---@field catalogue "events" Which catalogue it is from (weapon firing sounds have no such field).
---@field family string weapons, throwables, melee, explosions (its sounds play on the game's explosion bus), stratagems, vehicles, enemies, seaf, objectives, hazards, ambience, foley, gore, voice, ui, music, cinematics, system or other: from its bank's content path.
---@field bank string Its bank (content/audio/<bank>).
---@field banks string[] Every bank that defines it.
---@field faction "automaton"|"terminid"|"illuminate"|nil The faction its bank is named for.
---@field kind "one_shot"|"loop"|"unknown"|"control" The game's own metadata: one shot, a loop (infinite, stop it), unknown (unsupported); control: it plays nothing (stops, states, switches).
---@field range_m number|nil Its maximum attenuation distance in metres (the game's metadata); nil for a 2D or unattenuated sound.
---@field duration_s number|nil A one-shot's longest duration in seconds (the game's metadata).
---@field positional boolean|nil A 3D sound (true) or 2D (false).
---@field bus string|nil The named path of the mixer bus its sounds play on.
---@field global_effect "persistent"|"transient"|nil persistent: it would leave the sound engine changed (a state, a global game parameter or mix change or pause it does not undo): play refuses it. transient: a global stop of an element.
---@field effects string[] state, parameter, mix, pause, stop.
---@field wwise_name string|nil Its own Wwise name, where the game's code or data names it.
---@field weapons string[] The weapon firing sounds (hd2.sounds.list()) that post it.
---@field stratagem string|nil The stratagem whose call-in package provides its bank.
---@field item string|nil The loadout item whose package provides its bank (when no stratagem does).
---@field resident_only boolean No package Runtime can load provides its bank: usable only while the game has one resident.
---@field parameters string[] The game parameters (RTPCs) its sounds react to ('0x<id>' when unnamed).
---@field volume_parameters string[] Those of them that drive its volume: what handle:set_parameter can turn on its own source (a lead: the curve's direction is not read).
---@field switch_groups string[] The switch groups its sounds react to.
---@field state_groups string[] The state groups its sounds react to.
local HD2SoundEvent = {}

---A game parameter (RTPC) of the sound engine (hd2.sounds.parameters()).
---@class HD2SoundParameter
---@field name string Its name, or '0x<id>' when the game names it nowhere.
---@field named boolean
---@field default number|nil Its default value.
---@field events integer How many catalogued events react to it.
local HD2SoundParameter = {}

---A switch or state group of the sound engine (hd2.sounds.switch_groups() / state_groups()).
---@class HD2SoundGroup
---@field name string Its name, or '0x<id>'.
---@field named boolean
---@field values string[] Its switches or states (names, or '0x<id>').
---@field parameter string|nil A switch group driven by a game parameter: that parameter.
local HD2SoundGroup = {}

---A filter of hd2.sounds.list. Without catalogue: the weapon firing sounds (family, kind shot/loop, stratagem, resident_only, text). catalogue = 'events': the full event catalogue (every key below); 'all': both, each with the keys it supports.
---@class HD2SoundFilter
---@field catalogue "weapons"|"events"|"all"|nil Which catalogue (default weapons).
---@field family string|nil Only this family (weapons: sentry, vehicle, support, ...; events: weapons, explosions, stratagems, enemies, ui, voice, ambience, music, ...).
---@field kind string|nil Only this kind (weapons: shot, loop; events: one_shot, loop, unknown, control).
---@field stratagem true|string|nil true: only sounds a stratagem provides; a name: only that stratagem's.
---@field resident_only boolean|nil Only resident-only sounds (true) or only those a package provides (false).
---@field text string|nil A part of the name (or label) (any case).
---@field bank string|nil Events: only those a bank defines.
---@field faction string|nil Events: automaton, terminid or illuminate.
---@field bus string|nil Events: a part of the bus path ('explosion').
---@field named boolean|nil Events: only those with (or without) their own Wwise name.
---@field weapon true|string|nil Events: only those a weapon firing sound posts (or that one's).
---@field global boolean|nil Events: only those with (or without) a global effect.
local HD2SoundFilter = {}

---hd2.sounds: the weapon firing-sound catalogue (docs/weapon-sounds.md), the full sound-event catalogue and playing game sound events (docs/sounds.md).
---@class HD2Sounds
local HD2Sounds = {}
---Every catalogued firing sound (sorted by name), or those the filter keeps (a family name or a table); {catalogue = 'events'} lists the full event catalogue, {catalogue = 'all'} both. An invalid filter raises an error.
---@param filter? HD2SoundFilter|string
---@return (HD2WeaponSound|HD2SoundEvent)[]
function HD2Sounds.list(filter) end
---One sound by its name (or an older alias such as 'maelstrom_main_gun'), else a sound event by its catalogue name or its own Wwise name, or nil.
---@param name string
---@return HD2WeaponSound|HD2SoundEvent|nil
function HD2Sounds.describe(name) end
---Post a game sound event now: a firing-sound name ('sentry/gatling' starts its loop), a sound event's catalogue name, 'ui/<key>' (ui/stratagem_pick, ui/picker_close, ui/slot_select, ui/generic_select, ui/item_hover_select), any Wwise event name, or {id = <32-bit event id>}. Its bank must be loaded. An event that would leave the sound engine changed is refused (GLOBAL_EVENT). Rate-limited per mod. nil, code, reason when refused.
---@param event string|{id: integer}
---@param opts? HD2SoundPlayOptions
---@return HD2SoundHandle|nil, string|nil, string|nil
function HD2Sounds.play(event, opts) end
---Whether the sound engine knows the event now (its bank is loaded).
---@param event string|{id: integer}
---@return boolean|nil, string|nil
function HD2Sounds.available(event) end
---A catalogue sound (a firing sound or a sound event) as a hd2.require_assets / hd2.asset_dependency target (its bank's package: a stratagem's call-in or a loadout item's). Raises on an unknown name.
---@param name string
---@return table
function HD2Sounds.asset(name) end
---A name the sound engine maps to a 32-bit id (what play({id = id}) posts). Every catalogued id has one generated at build time; any other is searched for about 40 ms once, then cached.
---@param id integer
---@return string|nil
function HD2Sounds.name_for(id) end
---The sound engine's game parameters (RTPCs), sorted by name.
---@return HD2SoundParameter[]
function HD2Sounds.parameters() end
---The sound engine's switch groups and their switches.
---@return HD2SoundGroup[]
function HD2Sounds.switch_groups() end
---The sound engine's state groups and their states (read-only: states are engine-wide and never set by Runtime).
---@return HD2SoundGroup[]
function HD2Sounds.state_groups() end

---Which vanilla carrier a custom stratagem borrows: its carrier group (a structural pool), or the older policy fields; owned, selectable, enabled, unlimited, not in any lobby pick, never another custom stratagem's carrier, asset or delivery.
---@class HD2CustomStratagemCarrier
---@field group string|nil The carrier group (hd2.custom_stratagem.groups()): orbital, any_red, any, support, support_pod, expendable, sentry, emplacement, eagle; default the payload family's.
---@field slots integer|nil A pod capacity to ask the group for (1..8; support_pod and expendable only).
---@field beacon "offensive"|"support"|"any"|nil The beacon the player throws: offensive = a red beam, support = a blue beam. Required unless group is given.
---@field prefer_families string[]|nil Catalogue families in order of preference ('orbital', 'eagle', 'sentry', 'emplacement', 'mine', 'support', 'backpack').
---@field allow_families string[]|nil The only families it may take (default: the preferred ones).
---@field exclude string[]|nil Stratagems never taken.
---@field require_unlimited true|nil Always true: a carrier has unlimited uses.
local HD2CustomStratagemCarrier = {}

---A custom stratagem (hd2.custom_stratagem.register; development, solo host).
---@class HD2CustomStratagemSpec
---@field id string a-z, 0-9 and _, starting with a letter (at most 48); unique across mods.
---@field name string Its name (the HUD).
---@field name_cased string|nil Its cased name (the panel, the loadout).
---@field description string Its description.
---@field icon string|HD2ImageHandle The id of one of the mod's images (images/<id>.png, a 256 x 256 mask).
---@field code string[] 1 to 8 directions ('up', 'down', 'left', 'right'); never equal to or the start of another custom stratagem's.
---@field cooldown number|nil Seconds from the call-in's arrival (at most 600); nil: the carrier's own.
---@field uses integer|nil Calls per mission, each player's own (1 to 100): the call that uses the last of them ends with a cooldown longer than any mission; nil: unlimited. Not for an Eagle (eagle.uses is per rearm).
---@field traits string[]|nil Up to 4 ITEM TRAITS the custom panel shows after the automatic CUSTOM STRATAGEM (1 to 32 characters each, shown in upper case); nil: the payload family's.
---@field selection 'token'|'carrier'|nil development probe (the carrier-in-slot probe, solo host): 'carrier' picks the carrier itself into the loadout slot instead of the Orbital Precision Strike token; default 'token'
---@field carrier HD2CustomStratagemCarrier Its carrier policy.
---@field sentry table|nil {donor, weapon = {projectile, rpm, spread, ammo, recoil}}: the donor sentry's own pod, its sentry's own weapon configured (docs/custom-stratagem-api.md).
---@field orbital table|nil {native = true, pattern, impact_explosion} (the donor's own barrage) or a Runtime bombardment {shell, pattern, salvos, ...}.
---@field pelican table|nil {hover, orbit = {radius, altitude, duration, period, entry}, gun = {...}, approach}: the Runtime's Pelican; gun = {round = 'native'} is its vanilla autocannon.
---@field silo table|nil {donor = a reviewed missile silo ('MS-11 Solo Silo'), blast = an hd2.explosions name, fallback = an hd2.explosions name or nil}: the donor silo's own pod; where exactly the call's missile detonates, every watching machine requests the blast from its own copy
---@field assets string[]|nil Stratagems whose call-in packages it needs in the mission (loaded before it can be called).
---@field delivery "runtime"|{stratagem: string}|nil runtime (default): the carrier's own delivery never comes and the mod delivers; {stratagem = 'EAT-17 Expendable Anti-Tank'}: that vanilla support delivery's pod.
---@field on_called fun(ctx: HD2CustomStratagemCall)|nil The call-in started.
---@field on_beacon_created fun(ctx: HD2CustomStratagemCall)|nil Its beacon, in its first update (changed).
---@field on_beacon_landed fun(ctx: HD2CustomStratagemCall)|nil The beacon landed: ctx.position.
---@field on_activate fun(ctx: HD2CustomStratagemCall)|nil The beacon activated: deliver now.
---@field on_delivered fun(ctx: HD2CustomStratagemCall)|nil A support delivery: ctx.weapons, the exact delivered weapons.
local HD2CustomStratagemSpec = {}

---One call of a custom stratagem (its callbacks' ctx).
---@class HD2CustomStratagemCall
---@field id string The custom stratagem.
---@field call_id string Mission-unique: '<id>#<n>'.
---@field n integer Its number in this mission.
---@field player HD2PlayerHandle The caller (the local player: solo host).
---@field slot integer|nil The loadout slot it was called from, when known.
---@field carrier {name: string, stable_id: integer, type: integer} The vanilla carrier it borrowed.
---@field beacon {entity: integer, network: integer|nil}|nil Its beacon.
---@field position HD2Vector3|nil The beacon's landing position (else its activation position).
---@field delivery string 'runtime' or the vanilla support delivery's name.
---@field weapons HD2CustomStratagemWeapon[]|nil on_delivered: the exact delivered weapons.
local HD2CustomStratagemCall = {}
---A log line tagged with the call.
---@param text string
---@return nil
function HD2CustomStratagemCall:log(text) end
---Associates an entity the call spawned with it (mission-scoped).
---@param entity integer
---@param role? string
---@return boolean|nil
function HD2CustomStratagemCall:associate(entity, role) end
---The live entities associated with the call.
---@param role? string
---@return integer[]
function HD2CustomStratagemCall:spawned(role) end
---A Runtime bombardment: the shell of `shell`'s reviewed record in `pattern`'s salvo pattern over the target (default ctx.position); shell must be one of its assets.
---@param spec {shell: string, pattern: string, target: HD2Vector3|nil}
---@return table|nil
function HD2CustomStratagemCall:barrage(spec) end

---A weapon a support delivery brought (exactly that entity).
---@class HD2CustomStratagemWeapon
---@field entity integer Its entity id.
local HD2CustomStratagemWeapon = {}
---Its projectiles explode as the donor's ('Orbital Gas Strike') on impact: each projectile's own copy, one round; every other weapon stays vanilla.
---@param donor string
---@return boolean|nil
function HD2CustomStratagemWeapon:set_impact_explosion(donor) end

---hd2.custom_stratagem: selectable custom stratagems (development, solo host; docs/custom-stratagem-api.md).
---@class HD2CustomStratagems
local HD2CustomStratagems = {}
---Registers a custom stratagem of the calling mod (errors at load time on an invalid spec).
---@param spec HD2CustomStratagemSpec
---@return table
function HD2CustomStratagems.register(spec) end
---Every custom stratagem's state.
---@return table[]
function HD2CustomStratagems.status() end
---What a custom stratagem uses (read-only): {group, group_source, carrier = {name, stable_id, type, beam, condensed, fallback}, carrier_weapon = {name, level}, pod = {rack, capacity, items, slots}, available, reason, state}.
---@param id string
---@return table|nil
function HD2CustomStratagems.describe(id) end
---The carrier groups: {name, beacon, families, pod, weapon, eagle, doc, payloads, defaults; expendable: members = {name, stable_id, rounds, pod_capacity, clone_class, carries, refused}}.
---@return table[]
function HD2CustomStratagems.groups() end
---The call an entity belongs to: {id, call_id, n, role, player, parent}.
---@param entity integer
---@return table|nil
function HD2CustomStratagems.instance_of(entity) end
---Log every carrier candidate.
---@param on boolean
---@return nil
function HD2CustomStratagems.verbose(on) end
---The custom panel's focus to the next entry.
---@return string
function HD2CustomStratagems.focus_next() end
---Selects the focused entry.
---@return string
function HD2CustomStratagems.select_focused() end
---Returns the last selected slot.
---@return string
function HD2CustomStratagems.undo() end
---r51, for in-game editors: a registered custom stratagem's cooldown (seconds) and uses (calls per mission) on this machine, values = {cooldown, uses}. Each player's own, from their next call; the lobby registry is unchanged. The same checks as register. True, or nil and why.
---@param id string
---@param values table
---@return boolean|nil, string|nil
function HD2CustomStratagems.tune(id, values) end
---Back to the registered cooldown and uses.
---@param id string
---@return boolean|nil, string|nil
function HD2CustomStratagems.untune(id) end

---hd2.ownership: whom an associated autonomous entity's kills credit (development, solo host).
---@class HD2Ownership
local HD2Ownership = {}
---Its kills credit the local player (its own no-credit tag cleared); it must belong to that player's custom stratagem call.
---@param entity integer
---@param player HD2PlayerHandle
---@return {applied: boolean, already: boolean|nil, reason: string|nil}
function HD2Ownership.credit_to_player(entity, player) end

---hd2.build() details.
---@class HD2BuildInfo
---@field pinned string The first 12 hex digits of the executable build this Runtime is pinned to.
---@field reason string|nil Why the status is not_ready.
local HD2BuildInfo = {}

---The cursor, read-only.
---@class HD2Mouse
---@field x number Client pixels from the left.
---@field y number Client pixels from the top.
---@field w number Client width.
---@field h number Client height.
---@field left boolean The left button is held.
local HD2Mouse = {}

---One mod's saved key/value data (hd2.store(); docs/mod-store.md). Values: booleans, finite numbers, strings and tables of those (arrays or string-keyed maps, no cycles, at most 16 deep). Saved about a second after a change, or at once with save().
---@class HD2Store
---@field owner string The mod it belongs to.
local HD2Store = {}
---The stored value (a copy, for a table), or default.
---@param key string
---@param default any
---@return any
function HD2Store:get(key, default) end
---Store a value (nil removes the key). Raises on a value that cannot be saved.
---@param key string
---@param value any
---@return HD2Store
function HD2Store:set(key, value) end
---Every key, sorted.
---@return string[]
function HD2Store:keys() end
---Remove every key.
---@return HD2Store
function HD2Store:clear() end
---Write now. false and the reason when it failed (the previous file is kept).
---@return boolean, string|nil
function HD2Store:save() end
---{owner, keys, dirty, saved, file, load_error}.
---@return table
function HD2Store:describe() end

---@class HD2SoundPlayOptions
---@field position HD2Vector3|number[]|nil A world position: a 3D sound there, on a source of its own. Without position or unit the sound plays on the game world's own 2D source.
---@field rotation number[]|nil With a position: the source's orientation, a quaternion {x, y, z, w}.
---@field unit userdata|nil An engine Unit: the sound plays on the unit's own source and follows it.
---@field owner string|nil
local HD2SoundPlayOptions = {}

---A posted sound.
---@class HD2SoundHandle
---@field state "playing"|"stopped"
---@field playing integer The plugin's playing id.
---@field event string
---@field name string The name posted.
---@field kind string shot, loop, ui, event, or a sound event's kind.
---@field owner string
local HD2SoundHandle = {}
---Stop this playing instance.
---@return boolean|nil, string|nil
function HD2SoundHandle:stop() end
---{state, event, name, kind, playing, owner, source (world, position or unit), own_source, controls (pause/resume/is_playing/elapsed available), controls_reason}.
---@return table
function HD2SoundHandle:describe() end
---Pause this instance.
---@return boolean|nil, string|nil, string|nil
function HD2SoundHandle:pause() end
---Resume this instance.
---@return boolean|nil, string|nil, string|nil
function HD2SoundHandle:resume() end
---Whether the sound engine still plays it (false up to one update after it ends).
---@return boolean|nil, string|nil, string|nil
function HD2SoundHandle:is_playing() end
---Seconds it has played (the engine's play position).
---@return number|nil, string|nil, string|nil
function HD2SoundHandle:elapsed() end
---Set a game parameter (RTPC) on this sound's own source (a position post only).
---@param parameter string|{id: integer}
---@param value number
---@return boolean|nil, string|nil, string|nil
function HD2SoundHandle:set_parameter(parameter, value) end
---Set a switch on this sound's own source (a position post only).
---@param group string|{id: integer}
---@param switch string|{id: integer}
---@return boolean|nil, string|nil, string|nil
function HD2SoundHandle:set_switch(group, switch) end
---Post a trigger on this sound's own source (a position post only).
---@param trigger string|{id: integer}
---@return boolean|nil, string|nil, string|nil
function HD2SoundHandle:post_trigger(trigger) end

---hd2.ui: mod screen overlays (docs/ui-overlay.md).
---@class HD2UI
---@field MAX_LAYER integer The highest layer (1023).
---@field DEFAULT_LAYER integer The default base layer (1011).
local HD2UI = {}
---The calling mod's overlay opts.id (default 'main'): created on first use, the same object afterwards.
---@param opts? HD2OverlayOptions
---@return HD2Overlay
function HD2UI:overlay(opts) end
---Every overlay's status.
---@return table[]
function HD2UI:overlays() end
---A colour as overlays take it ({r, g, b[, a]} or '#RRGGBB[AA]') -> {r, g, b, a}; nil when invalid.
---@param c number[]|string
---@return number[]|nil
function HD2UI:colour(c) end
---The cursor capture's state: holders, disabled, the game's saved values and what the engine reports now.
---@return table
function HD2UI:cursor() end

---@class HD2OverlayOptions
---@field id string|nil 1 to 48 letters, digits, _ . - (default 'main').
---@field layer integer|nil The base layer of its band, 1..1023 (default 1011); an item's z is added to it.
---@field visible boolean|nil Default true.
---@field owner string|nil
local HD2OverlayOptions = {}

---A mod's screen overlay: rectangles and text in the game's Ui World, over the HUD and under the game's menus (the Noesis UI always draws above). Coordinates are GUI pixels from the top-left.
---@class HD2Overlay
---@field owner string
---@field id string
---@field layer integer
---@field width number|nil The screen width in GUI pixels (after the first frame).
---@field height number|nil
---@field scale number|nil The screen against 1920 x 1080 (the smaller ratio).
local HD2Overlay = {}
---Set the draw function: called every frame while shown; it describes the whole frame. Unchanged items make no engine call.
---@param fn fun(d: HD2OverlayFrame, dt: number)
---@return HD2Overlay
function HD2Overlay:draw(fn) end
---@param on? boolean
---@return HD2Overlay
function HD2Overlay:show(on) end
---@return HD2Overlay
function HD2Overlay:hide() end
---The cursor in overlay coordinates.
---@return {x: number, y: number, left: boolean}|nil, string|nil
function HD2Overlay:mouse() end
---The width of text in pixels.
---@param text string
---@param size? number
---@param font? "body"|"title"|"mono"
---@return number
function HD2Overlay:text_width(text, size, font) end
---{owner, id, state, reason, layer, visible, width, height, items, frames, engine_calls, refused, first_refusal}.
---@return table
function HD2Overlay:status() end
---Remove its primitives, its GUI and its frame callback.
---@return HD2Overlay
function HD2Overlay:close() end
---EXPERIMENTAL (r50): while shown, the engine shows the cursor, stops clipping it and drops the mouse focus so the camera stops turning; opts {camera = false} keeps the focus. free_cursor(false) gives it back.
---@param on? boolean
---@param opts? table
---@return HD2Overlay
function HD2Overlay:free_cursor(on, opts) end

---What one frame of an overlay shows (the d of overlay:draw). Invalid items are refused (counted in status()), never passed to the engine.
---@class HD2OverlayFrame
---@field width number
---@field height number
---@field scale number
local HD2OverlayFrame = {}
---A filled rectangle; (x, y) its top-left corner. colour {r, g, b[, a]} 0-255 or '#RRGGBB[AA]' (default white). z is added to the overlay's layer.
---@param x number
---@param y number
---@param w number
---@param h number
---@param colour? number[]|string
---@param z? integer
---@return nil
function HD2OverlayFrame:rect(x, y, w, h, colour, z) end
---A line of text (1-160 printable bytes); (x, y) its top-left corner (or top-centre / top-right with align).
---@param text string|number
---@param x number
---@param y number
---@param opts? HD2OverlayTextOptions
---@return nil
function HD2OverlayFrame:text(text, x, y, opts) end
---One of the mod's own images (hd2.resources.image) through the game's icon material; (x, y) its top-left corner. Drawn once its resources are loaded; an image partly off screen is dropped. One colour set per image per overlay (r50).
---@param image table
---@param x number
---@param y number
---@param w number
---@param h number
---@param opts? HD2OverlayImageOptions
---@return nil
function HD2OverlayFrame:image(image, x, y, w, h, opts) end
---@param text string
---@param size? number
---@param font? "body"|"title"|"mono"
---@return number
function HD2OverlayFrame:text_width(text, size, font) end

---@class HD2OverlayTextOptions
---@field size number|nil Pixels (4-256, default 18).
---@field colour number[]|string|nil
---@field font "body"|"title"|"mono"|nil body / title: the FS Sinclair fonts the Runtime ships; mono: the engine's monaco.
---@field align "left"|"center"|"right"|nil
---@field z integer|nil
local HD2OverlayTextOptions = {}

---player:weapon_state() (docs/player-equipment.md).
---@class HD2WeaponState
---@field name string|nil
---@field type string|nil
---@field slot string
---@field entity_id integer
---@field fire_rate number|nil Its current rounds per minute.
---@field rate_slots number[]|nil Its rate selector's three slots.
---@field own_record boolean It has its own ProjectileWeapon copy.
---@field projectile integer|nil The projectile type it fires.
---@field feed "magazine"|"heat"|"rounds"|"other"
---@field magazine {rounds: integer, chambered: integer, capacity: integer}|nil
---@field spread {horizontal: number, vertical: number}|nil Milliradians.
---@field recoil {horizontal: number, vertical: number}|nil Its aim recoil per shot.
---@field wind_up boolean
---@field heat boolean
local HD2WeaponState = {}

---d:image options.
---@class HD2OverlayImageOptions
---@field colours table|nil {r =, g =, b =}: the colours of the image's R, G and B masks (overlay colours; alpha = strength). Default white R and G, a 0.2 black shadow on B.
---@field colour number[]|string|nil Vertex colour (tint and alpha); default white.
---@field z integer|nil Added to the overlay layer.
local HD2OverlayImageOptions = {}

---mod:choice declaration.
---@class HD2ChoiceSpec
---@field id string 1-40 letters, digits, _ or -.
---@field values any[] 1-64 values, no two the same (a following choice may repeat); every one is validated when an ensure binds the choice.
---@field default integer|nil 1-based index (default 1).
---@field labels string[]|nil Readable names, for describe() and logs.
---@field follow HD2ScriptChoice|nil r51: another script choice of the same mod this one follows: it always selects the same index (it cannot be set itself), may repeat values and has exactly as many; a bound ensure proves the two together, index by index (e.g. the rate-of-fire selector binding that a fire_rate.modes list with two or more rates needs).
local HD2ChoiceSpec = {}

---A script choice (mod:choice).
---@class HD2ScriptChoice
local HD2ScriptChoice = {}
---The selected value (a copy of a plain table).
---@return any
function HD2ScriptChoice:get() end
---Select the value equal to `value` (reference handles by identity, tables element by element); false when it is not one of the values.
---@param value any
---@return boolean
function HD2ScriptChoice:set(value) end
---Select by 1-based index.
---@param index integer
---@return boolean
function HD2ScriptChoice:select(index) end
---The declaration and the selected value.
---@return table
function HD2ScriptChoice:describe() end

---A passive's effect package (research/passive-effects-F5FEE03DCFDB.json; the generated core/assets catalogue entry).
---@class HD2PassivePackage
---@field key string The passive +0x30 key (8 hex digits).
---@field catalogue string The core/assets catalogue key ('passive/17').
---@field package string The package id the game resolves the key to.
---@field contents string What the package holds (resource types).
---@field armor_slot_only string[] Its effect rows read from the armor slot only (17: death_explosion): set() refuses it as the second passive (ARMOR_SLOT_ONLY).
---@field loads string How set() loads it.
local HD2PassivePackage = {}

---The community wiki's values for a kit (where a wiki page matched): NOT read from the game.
---@class HD2ArmorKitWiki
---@field source 'wiki' Always wiki.
---@field name string The wiki's name.
---@field match 'exact'|'contained'|'fuzzy' How the wiki page matched the game name.
---@field class string|nil The wiki's weight class (armor).
---@field armor_rating number|nil The wiki's armor rating (armor).
---@field speed number|nil The wiki's speed (armor).
---@field stamina_regen number|nil The wiki's stamina regen (armor).
---@field passive string|nil The wiki's passive name.
---@field passive_agrees boolean|nil The wiki's passive is the game's.
local HD2ArmorKitWiki = {}

---One of the game's 411 kits (research/armor-names-F5FEE03DCFDB.json; read-only, offline).
---@class HD2ArmorKit
---@field index integer Its index in the kit table (0-410).
---@field id string The kit id (0x + 8 hex digits).
---@field slot 'armor'|'helmet'|'cape' Its slot (kit +0x28).
---@field weight 'light'|'medium'|'heavy'|nil Armor only: its weight (its armor pieces').
---@field passive integer Its passive (kit +0x1C; 0 for every helmet and cape).
---@field passive_name string That passive's game name.
---@field set string|nil Its set id.
---@field dlc string|nil Its dlc id.
---@field rarity string 'common' or 'heroic'.
---@field name string|nil Its game name (378 of 411 resolved; armors and their helmets often share one).
---@field description string|nil Its game description.
---@field same_name integer How many kits carry this name (0: unnamed).
---@field wiki HD2ArmorKitWiki|nil The community wiki's values where a page matched (not the game's).
local HD2ArmorKit = {}

---@class HD2ArmorKitFilter
---@field slot 'armor'|'helmet'|'cape'|nil Only this slot.
---@field weight 'light'|'medium'|'heavy'|nil Only armor of this weight.
---@field passive HD2PassiveName|integer|nil Only kits with this passive.
---@field name string|nil Only kits with this game name (any case).
local HD2ArmorKitFilter = {}

---hd2.armor_stats: armor rating, speed and stamina (DEVELOPMENT, not live-tested; docs/armor-stats.md). No armor stores its own numbers: each armor piece has a weight (light, medium, heavy) that indexes three per-weight tables in game.dll.
---@class HD2ArmorStatsApi
local HD2ArmorStatsApi = {}
---An armor kit by id (0x1F9BFA78, "1F9BFA78") or game name (any case; a name several kits share raises AMBIGUOUS_ARMOR_KIT with their ids): the target of the armor_kit.piece_weight.<slot> fields. Unknown: raises UNKNOWN_ARMOR_KIT.
---@param identity string|integer
---@return HD2ArmorKitTarget
function HD2ArmorStatsApi.kit(identity) end
---Every armor kit of the build with its vanilla stats (offline).
---@return HD2ArmorKitSummary[]
function HD2ArmorStatsApi.kits() end
---A weight class: its table values (armor value, speed and stamina factors) now. Read-only: the tables sit in game.dll pages that are executable at run time, which a guarded write never targets.
---@param name "light"|"medium"|"heavy"
---@return HD2ArmorClassTarget
function HD2ArmorStatsApi.class(name) end
---The avatar damage curve (damage multiplier by armor value). Read-only, like the class tables.
---@return HD2ArmorDamageCurveTarget
function HD2ArmorStatsApi.damage_curve() end
---The local player's own avatar members: the armor bonus and the stamina factor (DEVELOPMENT, solo).
---@return HD2ArmorPlayer
function HD2ArmorStatsApi.player() end

---An armor kit (hd2.armor_stats.kit). Fields hd2.fields.armor_kit.piece_weight_<slot> (the weight of its armor piece in that slot, written in every body); every player wearing the kit reads them: allow_shared=true and allow_unverified_effect=true. The armor rating follows on the next hit, the speed and stamina factors at the next armor apply (a respawn or a kit change).
---@class HD2ArmorKitTarget
---@field resource "armor_kit"
---@field armor_kit string The kit id (8 hex digits).
local HD2ArmorKitTarget = {}
---Its pieces per slot, the stats they give now (rating, speed, stamina_regen, armor_value, damage_multiplier, speed_factor, stamina_factor, class; live when the game is readable, else the research's), its passive, the vanilla stats and its fields.
---@return table
function HD2ArmorKitTarget:describe() end
---Its piece weight fields with their vanilla weight, range and lifecycle.
---@return table[]
function HD2ArmorKitTarget:fields() end
---The change list {field, expect, value} that puts every armor piece (or the slots given) at a weight, for hd2.transaction / hd2.ensure. It adds no acknowledgement.
---@param weight "light"|"medium"|"heavy"|integer
---@param slots? string[]
---@return table[]
function HD2ArmorKitTarget:changes(weight, slots) end
---The stats the kit would give with these slot weights (the tables now, the stocky body).
---@param weights table<string, "light"|"medium"|"heavy"|integer>
---@return table
function HD2ArmorKitTarget:preview(weights) end

---One armor kit of the build (hd2.armor_stats.kits()).
---@class HD2ArmorKitSummary
---@field id string Kit id (8 hex digits).
---@field name string|nil Its game name.
---@field passive integer Its passive id.
---@field passive_name string|nil Its passive's game name.
---@field class string The armory class label (the torso piece's weight).
---@field vanilla table {rating, speed, stamina, armor_value, speed_factor, stamina_factor, damage_multiplier}.
local HD2ArmorKitSummary = {}

---A weight class (hd2.armor_stats.class / hd2.armor_class). Fields hd2.fields.armor_class.rating / speed / stamina: one f32 entry per class table in game.dll, written as reviewed executable data, for every Helldiver on this machine (allow_shared and allow_unverified_effect; docs/armor-stats.md).
---@class HD2ArmorClassTarget
---@field resource "armor_class"
---@field armor_class "light"|"medium"|"heavy"
local HD2ArmorClassTarget = {}
---rating {value (armor value A), display (50 + 50 x A), vanilla}, speed {value, display (500 x factor), vanilla}, stamina {value, display (100 x (2 - F)), vanilla}, damage_multiplier, source, editable = false and why.
---@return table
function HD2ArmorClassTarget:describe() end
---Its three fields (read-only).
---@return table[]
function HD2ArmorClassTarget:fields() end

---The avatar damage curve (hd2.armor_stats.damage_curve()). Fields hd2.fields.armor_damage_curve.at_minus_1 .. at_3: the damage multiplier at each armor value, written as reviewed executable data like the class tables.
---@class HD2ArmorDamageCurveTarget
---@field resource "armor_damage_curve"
local HD2ArmorDamageCurveTarget = {}
---{points = {{armor_value, damage}}, vanilla, source, editable = false}.
---@return table
function HD2ArmorDamageCurveTarget:describe() end
---Its five fields (read-only).
---@return table[]
function HD2ArmorDamageCurveTarget:fields() end

---The local player's avatar members (hd2.armor_stats.player(); DEVELOPMENT, solo, not live-tested). A refusal never raises: status refused with a code and a reason.
---@class HD2ArmorPlayer
local HD2ArmorPlayer = {}
---The members now, or nil, code, reason.
---@return HD2ArmorPlayerState|nil, string?, string?
function HD2ArmorPlayer:describe() end
---Write armor_bonus (live, every hit) and / or stamina_factor (live until the game next applies the armor: a respawn or a kit change). Each member must hold the game's own value or this Runtime's.
---@param spec HD2ArmorPlayerSpec
---@return HD2ArmorPlayerResult
function HD2ArmorPlayer:set(spec) end
---Put the game's own values back (armor bonus 0, the kit's derived stamina factor) where a member still holds this Runtime's value.
---@return HD2ArmorPlayerResult
function HD2ArmorPlayer:restore() end

---hd2.armor_stats.player():set options.
---@class HD2ArmorPlayerSpec
---@field armor_bonus? number -1..3: added to the armor value of every hit on the avatar (the sum clamped to -1..3).
---@field stamina_factor? number 0.1..3: scales stamina drain AND regen and the jump / dive / climb / slide costs (light armor 0.75, medium 1, heavy 1.5).
---@field allow_unverified_effect boolean Required: not live-tested.
---@field owner? string The mod name for the log (default: the calling mod).
local HD2ArmorPlayerSpec = {}

---The outcome of a per-player write or restore.
---@class HD2ArmorPlayerResult
---@field status string 'APPLIED', 'UNCHANGED' or 'refused'.
---@field code string|nil Why it was refused: NOT_SOLO, NO_LOCAL_AVATAR, UNEXPECTED_STATE, OUT_OF_RANGE, ...
---@field reason string|nil
---@field armor_bonus number|nil The value now.
---@field stamina_factor number|nil The value now.
---@field writes integer|nil
---@field verified boolean|nil Read back.
---@field skipped string[]|nil restore: members left alone.
local HD2ArmorPlayerResult = {}

---The local player's armor members now (hd2.armor_stats.player():describe()).
---@class HD2ArmorPlayerState
---@field entity integer The player entity.
---@field avatar integer The avatar entity.
---@field slot integer Its avatar manager slot (the game's own map).
---@field armor_bonus number The armor modifier (0; -1 under a status effect).
---@field stamina_factor number The stamina factor the game applied (or this Runtime's).
---@field armor_kit table|nil {id, name, passive}.
---@field derived table|nil What the kit gives now: {rating, speed, stamina_regen, armor_value, damage_multiplier, speed_factor, stamina_factor, ...}.
---@field effective_armor_value number|nil What a hit uses: clamp(A + bonus, -1, 3) when the bonus is not 0.
---@field overridden boolean A member holds this Runtime's value.
local HD2ArmorPlayerState = {}

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
---Local player only: hd2.actions.injure(player, limb, damage) for this player.
---@param limb "head"|"chest"|"l_hand"|"r_hand"|"l_knee"|"r_knee"
---@param damage integer
---@param opts? {owner?: string}
---@return HD2ActionHandle
function HD2PlayerHandle:injure(limb, damage, opts) end
---Local player only: hd2.actions.heal_limb(player, limb, amount).
---@param limb "head"|"chest"|"l_hand"|"r_hand"|"l_knee"|"r_knee"
---@param amount? "full"|integer
---@param opts? {owner?: string}
---@return HD2ActionHandle
function HD2PlayerHandle:heal_limb(limb, amount, opts) end
---Local player only: hd2.actions.heal_limbs(player).
---@param opts? {owner?: string}
---@return HD2ActionHandle
function HD2PlayerHandle:heal_limbs(opts) end
---Local player only: hd2.actions.add_velocity(player, change).
---@param change HD2Vector3
---@param opts? {owner?: string}
---@return HD2ActionHandle
function HD2PlayerHandle:add_velocity(change, opts) end
---Local player only: what the avatar holds now (its wielder slot 0), re-read on every call. nil and the reason when nothing is in hand, the player is dead or not spawned, or it is another player.
---@return HD2EquippedWeapon|nil, string|nil
function HD2PlayerHandle:equipped_weapon() end
---@return table
function HD2PlayerHandle:describe() end
---The local player's primary, secondary, support, backpack, held item and throwable (with count), each with its catalog name. Local player only.
---@return table|nil, string|nil
function HD2PlayerHandle:loadout() end
---The item in hand and the slot it is in. Local player only.
---@return table|nil, string|nil
function HD2PlayerHandle:held_weapon() end
---What the weapon in hand fires with now, from its own instance (the values a template change reaches only after the weapon is built again). Local player only; read-only.
---@return HD2WeaponState|nil, string|nil
function HD2PlayerHandle:weapon_state() end
---The worn backpack: catalog name and its live supply/ammo count, capacity and owner flag. Local player only.
---@return table|nil, string|nil
function HD2PlayerHandle:backpack() end
---Rounds in the magazine and spare magazines (or the backpack count for backpack-fed weapons) of the held weapon or the given slot. Local player only.
---@param slot? "primary"|"secondary"|"support"
---@return table|nil, string|nil
function HD2PlayerHandle:ammo(slot) end
---hd2.actions.resupply_from_pack(player) for this player.
---@param opts? {owner?: string}
---@return HD2ActionHandle
function HD2PlayerHandle:resupply_from_pack(opts) end

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

---The local player's projectiles hit: the game's projectiles_hit mission stat grew. The game adds it in its projectile system, once per projectile that hits, under the weapon that fired it. Checked 10 times per second, so one event can count several hits. Local player only. Thrown entities such as the K-2 Throwing Knife are not projectile-system projectiles: use player_damage_dealt for them.
---@class HD2Event_player_hit : HD2Event
---@field player HD2PlayerHandle The local player.
---@field local_player boolean Always true.
---@field hits integer Projectile hits since the previous check.
---@field total integer The stat total now.
---@field sources HD2StatSource[] The growth per source type since the previous check, largest first: the weapon entity for guns, the throwable, or the stratagem payload.
---@field unattributed integer Growth the game recorded without a source.
local HD2Event_player_hit = {}

---The local player dealt damage: the game's dealt_damage mission stat grew by the damage the game recorded, under the weapon, throwable or stratagem payload that dealt it (team damage is a separate stat and is not counted). Checked 10 times per second: `damage` is the sum since the previous check. A hit that the target's armor stops entirely records nothing. Follow-up damage the game credits to the same source (an explosion, a status) is counted under that source too; no per-hit victim is reported.
---@class HD2Event_player_damage_dealt : HD2Event
---@field player HD2PlayerHandle The local player.
---@field local_player boolean Always true.
---@field damage integer Damage dealt since the previous check.
---@field total integer The stat total now.
---@field sources HD2StatSource[] The growth per source type since the previous check, largest first: the weapon entity for guns, the throwable, or the stratagem payload.
---@field unattributed integer Damage the game recorded without a source.
local HD2Event_player_damage_dealt = {}

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

---An explosion this machine's game will detonate: a request seen in the game's explosion queue (the game processes it in its next update), or one Runtime requested (hd2.explosions.spawn). Requests the game queues and processes within one update before Runtime's next look are not seen: see docs/events.md#explosions. Not live-tested.
---@class HD2Event_explosion : HD2Event
---@field name string|nil The explosion type's name in the explosion catalogue (docs/explosions.md), the name hd2.explosions.describe / spawn and hd2.explosion take: 'weapon/r36_eruptor/impact', 'stratagem/nux223_hellbomb/behavior'; nil when uncatalogued. It names the explosion, not who caused it.
---@field position HD2Position Where it detonates (a read-only snapshot).
---@field observed "queue"|"request" 'queue': read from the game's explosion queue. 'request': requested by Runtime (its cause names the mod), reported from the request.
---@field source_id integer|nil The source entity the request names (a weapon for its shell, an explosive for itself), or nil.
---@field source_type string|nil The source entity's type (16 hex digits), read when observed; nil when it no longer resolves (an explosive is usually gone by then).
---@field source_name string|nil The source type's catalogued name (a weapon, throwable or stratagem payload), or nil.
---@field owner_id integer|nil The owner entity the request names (often a player avatar).
---@field owner_type string|nil The owner entity's type (16 hex digits), or nil.
---@field owner_name string|nil The owner type's catalogued name, or nil.
---@field creditor_peer string|nil The peer id (16 hex digits) the request credits (kills and damage go to that player), or nil.
---@field player HD2PlayerHandle|nil The credited player when that peer is in the player list.
---@field local_player boolean The local player is credited.
local HD2Event_explosion = {}

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
---@alias HD2PlayerHitEvent HD2Event_player_hit
---@alias HD2PlayerDamageDealtEvent HD2Event_player_damage_dealt
---@alias HD2WeaponEquippedEvent HD2Event_weapon_equipped
---@alias HD2WeaponUnequippedEvent HD2Event_weapon_unequipped
---@alias HD2WeaponChangedEvent HD2Event_weapon_changed
---@alias HD2ExplosionEvent HD2Event_explosion
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
---@overload fun(name: "player_hit", callback: fun(event: HD2Event_player_hit), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_damage_dealt", callback: fun(event: HD2Event_player_damage_dealt), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "weapon_equipped", callback: fun(event: HD2Event_weapon_equipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "weapon_unequipped", callback: fun(event: HD2Event_weapon_unequipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "weapon_changed", callback: fun(event: HD2Event_weapon_changed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "explosion", callback: fun(event: HD2Event_explosion), opts?: HD2SubscribeOptions): HD2Subscription
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
---@overload fun(name: "player_hit", callback: fun(event: HD2Event_player_hit), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "player_damage_dealt", callback: fun(event: HD2Event_player_damage_dealt), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "weapon_equipped", callback: fun(event: HD2Event_weapon_equipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "weapon_unequipped", callback: fun(event: HD2Event_weapon_unequipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "weapon_changed", callback: fun(event: HD2Event_weapon_changed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(name: "explosion", callback: fun(event: HD2Event_explosion), opts?: HD2SubscribeOptions): HD2Subscription
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
---Every update tick (see hd2.on_frame).
---@param callback fun(dt: number, handle: HD2Timer)
---@param opts? HD2TimerOptions
---@return HD2Timer
function HD2ModContext:on_frame(callback, opts) end
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
---A script choice owned by this mod: any field value (numbers, booleans, strings, reference handles, plain tables such as a calldown code), selected from code and bound to one hd2.ensure value like a script value (r50).
---@param spec HD2ChoiceSpec
---@return HD2ScriptChoice
function HD2ModContext:choice(spec) end
---Run fn as this mod.
---@param fn fun(...): any
---@param ... any
---@return any
function HD2ModContext:run(fn, ...) end
---This mod's saved key/value data (see hd2.store).
---@return HD2Store
function HD2ModContext:store() end
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
---@overload fun(self: HD2ModContext, name: "player_hit", callback: fun(event: HD2Event_player_hit), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_damage_dealt", callback: fun(event: HD2Event_player_damage_dealt), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "weapon_equipped", callback: fun(event: HD2Event_weapon_equipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "weapon_unequipped", callback: fun(event: HD2Event_weapon_unequipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "weapon_changed", callback: fun(event: HD2Event_weapon_changed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "explosion", callback: fun(event: HD2Event_explosion), opts?: HD2SubscribeOptions): HD2Subscription
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
---@overload fun(self: HD2ModContext, name: "player_hit", callback: fun(event: HD2Event_player_hit), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "player_damage_dealt", callback: fun(event: HD2Event_player_damage_dealt), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "weapon_equipped", callback: fun(event: HD2Event_weapon_equipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "weapon_unequipped", callback: fun(event: HD2Event_weapon_unequipped), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "weapon_changed", callback: fun(event: HD2Event_weapon_changed), opts?: HD2SubscribeOptions): HD2Subscription
---@overload fun(self: HD2ModContext, name: "explosion", callback: fun(event: HD2Event_explosion), opts?: HD2SubscribeOptions): HD2Subscription
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
---@field version string the compatibility version, MAJOR.MINOR.PATCH (every SDK wrapper compares it)
---@field version_label string the full version of this build (e.g. 0.30.0-dev)
---@field api_version integer
---@field events HD2Events
---@field input HD2Input
---@field entities HD2Entities
---@field explosions HD2Explosions
---@field actions HD2Actions
---@field projectiles HD2Projectiles
---@field status HD2StatusEffects
---@field pelican HD2Pelicans
---@field sounds HD2Sounds
---@field custom_stratagem HD2CustomStratagems
---@field ownership HD2Ownership
---@field ui HD2UI
---@field passives HD2Passives
---@field player_passives HD2PlayerPassivesApi|fun(): HD2PlayerPassives|nil, string?, string?
---@field armor_stats HD2ArmorStatsApi
---@field armor_class fun(name: "light"|"medium"|"heavy"): HD2ArmorClassTarget
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
---Any slot's attachment definition by semanticId or unique native name.
---@param identity HD2WeaponAttachmentId
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
---Reviewed enemy / structure names (call it: hd2.enemies(filter), optionally filtered by kind and faction),
---and how often each enemy type spawns (hd2.enemies.spawn_weight; docs/enemy-spawns.md).
---@type HD2Enemies|fun(filter?: {kind?: "enemy"|"structure", faction?: "terminids"|"automatons"|"illuminate"|"neutral"}): string[]
hd2.enemies = {}
---The Helldiver type (avatar_helldiver; docs/helldiver-fields.md): movement speeds, stamina and body zones of every
---Helldiver this machine simulates. Every write needs allow_shared=true and allow_unverified_effect=true.
---@param name? "Helldiver"
---@return HD2Helldiver
function hd2.helldiver(name) end
---A catalogued attack output by semantic ID or owner weapon name (see docs/attack-outputs.md).
---@param identity HD2AttackOutputId
---@return HD2AttackOutput
function hd2.attack_output(identity) end
---A catalogued explosion by semantic id or label (docs/explosions.md, sdk/ExplosionCatalogue.json): the target
---of the explosion.* fields, a payload value and a spawn argument.
---@param name HD2CatalogueExplosionName|string
---@return HD2CatalogueExplosion
function hd2.explosion(name) end
---Mods that need a newer HD2Runtime (HD2Runtime 0.28.0+). The SDK wrapper of every mod reports here before its
---own version check fails closed; HD2Runtime logs each mod and shows one update warning per session on the ship.
hd2.compatibility = {}
---Record that `mod` needs `minimum` (SemVer); true when the installed HD2Runtime satisfies it.
---@param mod string
---@param minimum string
---@param display string?
---@return boolean ok
---@return string? reason
function hd2.compatibility.require_runtime(mod, minimum, display) end
---SemVer precedence (-1, 0, 1; nil when malformed). A prerelease is older than its release.
---@param a string
---@param b string
---@return integer?
function hd2.compatibility.compare(a, b) end
---@return table[] {mod, display, required}
function hd2.compatibility.incompatible() end
---@return string? highest
function hd2.compatibility.highest() end
---@return table {incompatible, highest, shown, dialog}
function hd2.compatibility.status() end
---Catalogued attack output IDs, optionally filtered.
---@param filter? {family?: "projectile"|"beam"|"arc"|"spray"|"melee", selectable?: boolean}
---@return string[]
function hd2.attack_outputs(filter) end

---@class HD2Diagnostics
local HD2Diagnostics = {}
---Opt-in sampled timing (off by default): {enabled=true, report_seconds=60} logs, every interval, the average,
---p95, p99 and maximum of the Runtime update, one ensure byte-check and event polling, with the active
---ensures and re-applications. Returns {enabled, report_seconds, timed, sections}.
---@param options? {enabled?: boolean, report_seconds?: number}
---@return table
function HD2Diagnostics.telemetry(options) end
---Ensure-owned targets something else keeps overwriting (always on; a warning is logged after 3 re-applications
---in the operation's window): {operation, target, externalChanges, warnings, windowSeconds}[], most first.
---@return table[]
function HD2Diagnostics.write_conflicts() end
---Every operation registered this session, refused ones included (HD2Runtime 0.28.1+): {kind, id, mod, sdk,
---sdk_source, status, result, code, error, runs, legacy}[], in registration order. `legacy` lists the fields an
---operation of a mod declaring an older SDK wrote without an acknowledgement a later SDK added
---(docs/legacy-sdk-compatibility.md).
---@return table[]
function HD2Diagnostics.operations() end
---Per-mod CPU time (always on, quiet; HD2Runtime 0.30.0-dev+): every call into a mod (event listeners, timers,
---keybinds, its main file, custom stratagem callbacks) and every update the Runtime runs for it, by its own time.
---{timed, single_call_seconds, share_seconds, window_seconds, owners = {owner, total_seconds, calls, max_seconds,
---max_label, last_window}[]}, the most time first. A slow call or a high share is logged as PERFORMANCE.
---@return table
function HD2Diagnostics.performance() end
---@type HD2Diagnostics
hd2.diagnostics = {}
---Run once after a delay in game seconds (fractions work; 0 = the next update tick; math.random(1, 10) gives a random delay). The timer belongs to the calling mod; scope=mission cancels it when the mission ends.
---@param seconds number
---@param callback fun(timer: HD2Timer)
---@param opts? HD2TimerOptions
---@return HD2Timer
function hd2.after(seconds, callback, opts) end
---Run repeatedly (at least 0.05 s apart; hd2.on_frame runs a callback every frame). Missed intervals are skipped, never replayed.
---@param seconds number
---@param callback fun(timer: HD2Timer)
---@param opts? HD2TimerOptions
---@return HD2Timer
function hd2.every(seconds, callback, opts) end
---Run a callback on every update tick with the tick's dt in seconds, after events and timers. Same owner, id and scope rules as hd2.every; handle:cancel() removes it, :disable() / :enable() pause it. Keep the work small.
---@param callback fun(dt: number, handle: HD2Timer)
---@param opts? HD2TimerOptions
---@return HD2Timer
function hd2.on_frame(callback, opts) end
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
---The game's state now; nil and the reason when it cannot be read (hd2.build() tells a wrong game build apart from a game not readable yet).
---@return HD2GameState|nil, string|nil
function hd2.game_state() end
---The running game build against the one this Runtime was built for, without raising. Cheap to poll: each loaded build is hashed once, a wrong one included.
---@return "matched"|"mismatched"|"not_ready", HD2BuildInfo
function hd2.build() end
---The calling mod's saved key/value data, kept between game sessions in its own file (docs/mod-store.md). The mod is found the way hd2.mod() finds it.
---@return HD2Store
function hd2.store() end
---Every kit of the game matching the filter, by index (research/armor-names-F5FEE03DCFDB.json; read-only, offline). The wiki values are the wiki's, not the game's. A bad filter raises.
---@param filter? HD2ArmorKitFilter
---@return HD2ArmorKit[]
function hd2.armor_kits(filter) end
---One kit by index, id ('0x1F9BFA78') or game name (any case; a shared name: slot picks, else the armor first); nil, UNKNOWN_KIT, reason otherwise.
---@param kit string|integer
---@param slot? 'armor'|'helmet'|'cape'
---@return HD2ArmorKit|nil, string?, string?
function hd2.armor_kit(kit, slot) end
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
