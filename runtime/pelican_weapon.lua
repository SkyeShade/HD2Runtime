-- The Pelican chin turret's own weapon behaviour (development only; PelicanWeaponBehaviorProof;
-- docs/research/pelican-cas-F5FEE03DCFDB.md section 17). Not exported by api/hd2.lua.
--
-- One Runtime-spawned Pelican's own chin turret (shuttle_gunship_turret_hmg: its entity, model, node 41 and targeting
-- AI stay) takes a configurable weapon behaviour, per instance, without changing any shared definition
-- (research/pelican-F5FEE03DCFDB.json "pelicanWeapon", "turretWeapon", "gatling"):
--   * the projectile and rate: the game's ProjectileWeapon copy routine (0x61AF10, an unmodified copy of its type's
--     record for this turret only), then one guarded transaction: the copy's projectile type and the turret's own current
--     RPM (the engine re-derives its shot interval from it). Live-proven at 148 / 1600 RPM (PelicanGatlingProof WEAPON);
--   * continuous fire: its AI (behaviour 645) fires in a fixed 0.5 s window from its stage-3 entry time (P+0x180) and
--     then re-aims at least 1.5 s (stage 2). M.hold_fire keeps this turret's own P+0x180 ahead of the clock while it is in
--     stage 3 (one guarded 8-byte write per stage-3 entry), so it keeps firing until its AI itself leaves the stage (no
--     target, no line of fire), as the Gatling Sentry's AI does;
--   * the ammunition pattern (optional): the game's magazine copy routine (0x770B10, an unmodified copy of its type's
--     magazine record), then one guarded transaction: the copy's pattern mode (1) and entries, and the turret's own
--     magazine record's mode and pattern length, the values the game itself derives from a magazine with that pattern;
--   * spin-up: not available. It is a component (weapon_wind_up) the turret's type does not have, and no game routine
--     adds a component to a live entity;
--   * the Gatling AI (M.switch_ai): a Behavior record's behaviour id (+0) is per instance and the Behavior update reads it
--     every frame to choose the code it runs. The game changes it itself through SetBehaviour (0x843EA0); this calls that
--     routine with 213 (the Gatling Sentry's AI) for this turret only, while it is quiet (645 stage 1 or 4, nothing
--     pending: its trigger released). The Gatling AI then runs its own stage machine from its own stage 1.
-- The Gatling configuration (PelicanGatlingProof 0.3.0; docs section 19; research "casing", "firstShot", "rateSeed",
-- "ai213", "ammo"):
--   * M.FROZEN: the Gatling Sentry's values this configuration copies, FROZEN from the pinned research of this build
--     (research/pelican "turretWeapon", "casing", "ammo", "aim"; research/custom-payloads "sentryWeapons"). The
--     configuration never reads a live entity and never the Gatling Sentry's type records: a custom sentry's own
--     private records, or another mod, may have changed a Gatling Sentry, and the Pelican's chin gun must not follow
--     them (live 2026-10-04: a Pelican called after the custom HMG Sentry was refused, RATE_UNEXPECTED, because the old
--     path compared with a deployed sentry). M.reference(world) still reads the type records, read-only, for the
--     proofs' and the validator's comparison with M.FROZEN;
--   * the rate (rpm = 'gatling'): the frozen Gatling rate times the factor the game applied to THIS turret (its own
--     current RPM over its type's), and the copy's rate slot, so a re-derivation by the game gives the same rate;
--   * the casing (casing = true): the copy's casing particles (+0xB0) and parameters (+0xD4) become the Gatling's, before
--     the turret's first shot (its first shot then picks the game's pooled Gatling casing effect and keeps it);
--   * the ammunition (ammo = true): its own magazine copy at the safe maximum, 2047 (the rounds are an 11-bit network
--     field, saturated at every shot's replication), full; M.refill_step tops it up below M.REFILL_BELOW;
--   * M.target_step: a target lock held through the AI's own re-pick time; released (dead, out of sight, not hittable,
--     no target) through the AI's own transition out of its firing stage (the pending stage, as the game's own stage-12
--     exits use it).
-- Refused, with nothing called or written, unless: every Pelican pin and each routine's exact entry bytes prove; inside
-- the Runtime's own update; in a mission, as the solo host; the Pelican is Runtime-spawned, behaviour 667 and alive before
-- its departure (stages 1-6: applied as soon as its chin turret exists);
-- exactly one chin turret (behaviour 645, its resource) names it by its unit link and its mount record names that turret.
-- Runs interpreted. The game's LuaJIT (2.1.0-alpha) mis-restores a sunk table at a trace exit (allocation sinking): a
-- table this module built and returned from a compiled trace came back without its last fields (the chin turret's AI
-- state without its record, tests/test_pelican_gatling_proof.py; correct with the JIT or its sinking off). So the JIT
-- is off for this development module and every function in it; the work it does is a few reads a frame.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local core_assets=require('hd2runtime/core/assets')
local pelicans=require('hd2runtime/runtime/pelicans')
local gatling=require('hd2runtime/runtime/pelican_gatling')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/pelican')
local M={}
local G,TW,SP=D.gatling,D.turretWeapon,D.spawn
local MC,B645=G.magazineCopy,G.behaviour645
local AM,AI213=D.ammo,D.ai213
local AIM=D.aim
local BC=D.components.behavior
local CHIN=G.chinTurretResource
local US=1e6
M.GATLING={projectile=TW.observed.gatlingSentry.projectileType,rpm=TW.observed.gatlingSentry.rpmSlots[2],
    pattern=TW.observed.gatlingSentry.pattern}
M.HOLD_SECONDS=3600
-- The chin turret's and the Gatling Sentry's entity resources (hex).
M.RESOURCES={chin=CHIN,gatling=G.gatlingResource}
-- The rounds are an 11-bit network field (research "ammoNetwork"): every shot queues them for replication and the
-- flush saturates the host's own count to 0..2047 in place. So the safe maximum magazine is 2047 rounds, kept up by the
-- refill (M.refill_step) once the count falls below M.REFILL_BELOW.
M.AMMO_MAX=D.ammo.roundsMax
M.REFILL_BELOW=1500
M.REFILL_SPACING=2

local function log(text)log_module.emit('[HD2Runtime] PELICAN WEAPON '..text)end
-- The repeated target-state lines (TARGET EXIT, TARGET SET REFUSED, a TARGET SET that missed, AMMO REFILL) are logged the
-- first time per turret (and reason); the rest are counted (M.quiet_counts, in the gunship's SUMMARY). M.verbose
-- (hd2.custom_stratagem.verbose(true)) logs every one.
M.verbose=false
local quiet={}            -- turret -> {[what] = count}
local function first_time(turret,what)
    local q=quiet[turret or 0]
    if not q then q={};quiet[turret or 0]=q end
    q[what]=(q[what]or 0)+1
    return M.verbose==true or q[what]==1
end
-- How often each repeated line happened on a turret: {exits, set_refusals, set_misses, refills}.
function M.quiet_counts(turret)
    local q=quiet[turret or 0]or{}
    local refusals=0
    for k,n in pairs(q)do if k:find('^set_refused:')then refusals=refusals+n end end
    return {exits=q.exit or 0,set_refusals=refusals,set_misses=q.set_miss or 0,refills=q.refill or 0}
end
local function u32(n)return b.encode(n,'u32')end
local function u64(raw,o)return b.u32(raw,o)+b.u32(raw,o+4)*4294967296 end
local function encode64(n)return b.encode(n%4294967296,'u32')..b.encode(math.floor(n/4294967296),'u32')end
local function map_at(at)return {keys=at,capacity=at+8,empty=at+0xC,multiplier=at+0x10}end

function M.prove(world)
    local ok,why=gatling.prove(world)
    if not ok then return nil,why end
    if not world.view.proves(world.game+MC.rva,MC.prologue)then
        return nil,('the game\'s magazine copy routine changed (game+%X)'):format(MC.rva)
    end
    return true
end

-- The projectile's package through the Runtime's asset loader (the Gatling Sentry's call-in package holds projectile
-- 148). M.assets(world, dt): 'ready', 'waiting' or 'failed' and why; logs "assets for pelican-weapon requested" and
-- "... resident".
M.ASSET_ID='pelican-weapon'
local gate
function M.assets(world,dt)
    if not gate then
        local dependency=gatling.asset_dependency()
        if not dependency then return'failed','ASSET_UNAVAILABLE: no package is known for the projectile'end
        gate=core_assets.gate(world.runtime,{id=M.ASSET_ID,asset_dependencies={dependency}},log_module.emit)
    end
    return gate.tick(dt or 0)
end

-- The AP4 donor (research "apDonor", docs section 23): the MG-206 Heavy Machine Gun's round 275 (damage record 205: AP4
-- direct, slight and large; 980 m/s, mass 52), against the standard round 148 (damage 125, AP3). Its package through
-- the asset loader: M.ap_assets(world, dt), as M.assets. M.projectile_identity(world, kind): the live row's {type,
-- velocity, mass, damage, raw} or nil (read-only).
M.AP4=D.apDonor
M.AP_ASSET_ID='pelican-weapon-ap4'
local ap_gate
function M.ap_dependency()return core_assets.dependency(M.AP4.assetKey)end
function M.ap_assets(world,dt)
    if not ap_gate then
        local dependency=M.ap_dependency()
        if not dependency then return'failed','ASSET_UNAVAILABLE: no package is known for the AP4 donor'end
        ap_gate=core_assets.gate(world.runtime,{id=M.AP_ASSET_ID,asset_dependencies={dependency}},log_module.emit)
    end
    return ap_gate.tick(dt or 0)
end
-- The Eagle Strafing Run's own rounds (research/custom-payloads pelicanRounds): its 23mm HE round 16 (it explodes by its
-- own row as explosion 50, the 'Strafing run cannon' blast), its plain twin 27 and the Eagle's own magazine pattern (HE,
-- then three plain). Their effects ship in the Strafing Run's call-in package (eagle_base): M.strafing_assets(world, dt),
-- as M.ap_assets. Only this turret's own ProjectileWeapon copy (and, for the pattern, its own magazine copy) names them.
M.STRAFING=require('hd2runtime/domains/custom_payloads').pelicanRounds.strafing_run
M.STRAFING_ASSET_ID='pelican-weapon-strafing-run'
local strafing_gate
function M.strafing_dependency()
    local entry=require('hd2runtime/domains/stratagem_authoring').stratagems[M.STRAFING.asset]
    local list=entry and entry.root and core_assets.dependencies_for_stratagem(entry.root.id,M.STRAFING.asset)
    return list and list[1]or nil
end
function M.strafing_assets(world,dt)
    if not strafing_gate then
        local dependency=M.strafing_dependency()
        if not dependency then return'failed','ASSET_UNAVAILABLE: no package is known for the Eagle Strafing Run'end
        strafing_gate=core_assets.gate(world.runtime,{id=M.STRAFING_ASSET_ID,asset_dependencies={dependency}},
            log_module.emit)
    end
    return strafing_gate.tick(dt or 0)
end
function M.projectile_identity(world,kind)
    local raw=world_module.projectile_row(world,kind)
    if not raw then return nil end
    local A=M.AP4
    return {type=b.u32(raw,0),velocity=b.value(raw,A.rowVelocity,'f32'),mass=b.value(raw,A.rowMass,'f32'),
        damage=b.u32(raw,A.rowDamage),raw=raw}
end

local configured={}   -- turret -> {pelican, spec, holds, fire_entries}
function M.configured(turret)return configured[turret]end

local function guards(world,pelican,needs)
    for _,name in ipairs(needs)do
        if not world.runtime[name]then return nil,'UNAVAILABLE','this Runtime adapter cannot call game functions'end
    end
    if not scheduler.in_update()then return nil,'NOT_GAME_THREAD','only inside the Runtime\'s own update'end
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','in a mission only'end
    if game.host~=true then return nil,'NOT_HOST','development experiment: host only'end
    local record_list,code,reason=slots.local_record(world)
    if not record_list then return nil,code,reason end
    local mp=require('hd2runtime/runtime/multiplayer')
    local scode,swhy=mp.solo_guard(record_list.records,mp.entity_allowed(pelican),'its own copies are not sent to peers')
    if scode then return nil,scode,swhy end
    if not pelicans.owned(pelican)then
        return nil,'NOT_RUNTIME_PELICAN','Pelican '..tostring(pelican)..' was not spawned by the Runtime'
    end
    local state,scode,sreason=gatling.inspect(world,pelican)
    if not state then return nil,scode,sreason end
    if not(state.pelican.stage>=1 and state.pelican.stage<=6)then
        return nil,'NOT_ACTIVE',('Pelican %d is in stage %d (departing or not started)'):format(pelican,state.pelican.stage)
    end
    if #state.attached~=1 or not state.turret or state.turret.behaviour~=645 or state.turret.resource~=CHIN then
        return nil,'TURRET_UNEXPECTED','exactly one chin turret (behaviour 645) must be attached to the Pelican'
    end
    if not(state.mount and state.mount.slot)then
        return nil,'MOUNT_UNEXPECTED','the Pelican\'s mount record does not name its chin turret'
    end
    return state
end

-- The magazine manager's copy count and capacity, and the turret's own magazine record and copy (read-only).
local function magazine_state(world,turret)
    local MG=TW.magazine
    local manager=world.view.pointer(world.game+MG.global)
    if not manager or manager==0 then return nil end
    local count=world.view.read(manager+MC.count,4)
    local capacity=world.view.read(manager+MC.capacity,4)
    local ri=pelicans.index_of(world,manager,map_at(MG.map),turret)
    local records=ri and world.view.pointer(manager+MG.records)
    local entries=ri and world.view.pointer(manager+AM.entries)
    local ci=pelicans.index_of(world,manager,map_at(MC.map),turret)
    local copies=ci and world.view.pointer(manager+MC.records)
    return {manager=manager,count=count and b.u32(count,0),capacity=capacity and b.u32(capacity,0),
        record=records and records~=0 and records+ri*MG.stride or nil,
        entry=entries and entries~=0 and entries+ri*AM.entryStride or nil,
        copy=copies and copies~=0 and copies+ci*MC.stride or nil}
end
-- One turret's ammunition, read-only: {rounds (the authoritative count, entry +4), working (record +0, the fire loop's
-- copy of it), chambered (record +8: 0 = none), chamber_empty (entry +8), spares (entry +0), capacity (its resolved
-- magazine's +0x88), from ('copy': its own magazine record, or 'type')}, or nil. `resource` (hex) names its type.
function M.ammo_state(world,turret,resource)
    local mag=magazine_state(world,turret)
    local rec=mag and mag.record and world.view.read(mag.record,TW.magazine.stride)
    local entry=mag and mag.entry and world.view.read(mag.entry,AM.entryStride)
    if not(rec and entry)then return nil end
    local resolved,from
    if mag.copy then resolved,from=world.view.read(mag.copy,MC.stride),'copy'
    else resolved,from=gatling.type_record(world,G.magazineTypes,resource or CHIN),'type'end
    return {rounds=b.value(entry,AM.entryRounds,'i32'),working=b.value(rec,TW.magazine.rounds,'i32'),
        chambered=b.u32(rec,TW.magazine.chambered),chamber_empty=entry:byte(AM.entryChamberEmpty+1),
        spares=b.u32(entry,AM.entrySpares),capacity=resolved and b.u32(resolved,AM.capacity),from=from}
end

-------------------------------------------------------------------------------- the Gatling, read from the game --
-- What a Gatling configuration copies is read live, read-only, from the game's own records (never a catalogue): the
-- Gatling Sentry's and the chin turret's type records (component world tables), and a deployed Gatling Sentry's own
-- records when one exists.
local CS,PWT=D.casing,G.pwTypes
local function f32(raw,o)local ok,v=pcall(b.value,raw,o,'f32');return ok and v or nil end
local function hex(raw)return raw and b.hex(raw:reverse()):upper()or'?'end
M.hex=hex
-- The fire effects block of a ProjectileWeapon record with the casing's particles and parameters blanked: two records
-- with the same layout differ only in their casing (the nodes are the same, so the weapon's resolved nodes stay right).
local function effects_layout(raw)
    local block=raw:sub(CS.effects+1,CS.effectsEnd)
    local function blank(text,at,size)return text:sub(1,at)..string.rep('\0',size)..text:sub(at+size+1)end
    block=blank(block,CS.particles-CS.effects,8)
    return blank(block,CS.parameters-CS.effects,CS.parametersSize)
end
local function casing_of(raw)
    return {particles=raw:sub(CS.particles+1,CS.particles+8),parameters=raw:sub(CS.parameters+1,
        CS.parameters+CS.parametersSize),layout=effects_layout(raw)}
end

-- One projectile weapon's casing, read-only: {index, instance (its instance record's address), from ('copy': its own
-- resolved ProjectileWeapon, or 'type'), particles and parameters (raw bytes of the resolved record), cached (the pooled
-- casing effect its first shot kept, instance +0x90: 0 until it has fired), muzzle (the kept muzzle flash, +0x88), nodes
-- (its ejector node count)}, or nil. `resource` (hex) names its type when it has no copy.
function M.casing_state(world,entity,resource)
    local PW=TW.projectileWeapon
    local pw=world.view.pointer(world.game+PW.global)
    local index=pw and pw~=0 and pelicans.index_of(world,pw,map_at(PW.map),entity)
    if not index then return nil end
    local instances=world.view.pointer(pw+PW.instances)
    local inst=instances and instances~=0 and world.view.read(instances+index*PW.instanceStride,PW.instanceStride)
    if not inst then return nil end
    local ci=pelicans.index_of(world,pw,map_at(PW.copies),entity)
    local copies=ci and world.view.pointer(pw+PW.copyRecords)
    local rec,from
    if copies and copies~=0 then
        rec,from=world.view.read(copies+ci*PW.copyStride,PW.copyStride),'copy'
    else
        rec,from=resource and gatling.type_record(world,PWT,resource),'type'
    end
    if not rec then return nil end
    local c=casing_of(rec)
    return {index=index,instance=instances+index*PW.instanceStride,from=from,particles=c.particles,
        parameters=c.parameters,cached=b.u32(inst,CS.instanceCasing),muzzle=b.u32(inst,CS.instanceMuzzleFlash),
        nodes=b.u32(inst,CS.instanceNodeCount),nodes_raw=rec:sub(CS.nodes+1,CS.nodes+4*CS.nodeSlots)}
end
function M.casing_text(c)
    if not c then return'(unreadable)'end
    return ('casing particles %s from its %s record (parameters %d, %d, %d); casing effect kept from its first shot: %s; '
        ..'%d ejector node(s)'):format(hex(c.particles),c.from=='copy'and'own'or'type\'s',b.u32(c.parameters,0),
        b.u32(c.parameters,4),b.u32(c.parameters,8),c.cached~=0 and('#'..c.cached)or'none (it has not fired)',c.nodes)
end

-- The frozen Gatling configuration (see the header). Every value is pinned research of this build, never read from the
-- game at configuration time: {projectile, rpm (the Gatling's Y slot), casing = {particles, parameters, nodes},
-- magazine = {capacity, chamber}, recoil_b (its aim recoil block B, 28 bytes), spread = {x, y, word}, chin = {projectile,
-- rpm, casing, magazine} (the chin turret's own type, which its own records are checked against)}.
local CP=require('hd2runtime/domains/custom_payloads')
local function hex_bytes(h)return b.unhex(h):reverse()end   -- a '%016X' / '%08X' value -> its little-endian bytes
local function words(list)local out={};for k,v in ipairs(list)do out[k]=u32(v)end;return table.concat(out)end
local function nodes(list)local out={};for k,v in ipairs(list)do out[k]=hex_bytes(v)end;return table.concat(out)end
local function floats(list)local out={};for k,v in ipairs(list)do out[k]=b.encode(v,'f32')end;return table.concat(out)end
do
    local OB,CO,AO,WO=TW.observed,CS.observed,AM.observed,AIM.observed
    local GS=CP.sentryWeapons['A/G-16 Gatling Sentry']
    M.FROZEN={projectile=OB.gatlingSentry.projectileType,rpm=OB.gatlingSentry.rpmSlots[2],
        casing={particles=hex_bytes(CO.gatlingSentry.particles),parameters=words(CO.gatlingSentry.parameters),
            nodes=nodes(CO.gatlingSentry.nodes)},
        magazine={capacity=AO.gatlingSentry.capacity,chamber=AO.gatlingSentry.chamber},
        recoil_b=floats(WO.gatlingSentry.blockB),
        spread={x=WO.gatlingSentry.spread[1],y=WO.gatlingSentry.spread[2],word=GS.spreadWord},
        chin={projectile=OB.chinTurret.projectileType,rpm=OB.chinTurret.rpmSlots[2],
            casing={particles=hex_bytes(CO.chinTurret.particles),parameters=words(CO.chinTurret.parameters),
                nodes=nodes(CO.chinTurret.nodes)},
            magazine={capacity=AO.chinTurret.capacity,chamber=AO.chinTurret.chamber}}}
    assert(GS.rateSlots[2]==M.FROZEN.rpm and GS.projectile==M.FROZEN.projectile and GS.capacity==M.FROZEN.magazine.capacity,
        'the frozen Gatling values disagree between the research domains')
end
function M.frozen()return M.FROZEN end

-- M.reference(world), read-only diagnostics (the proofs and the packaged validator compare it with M.FROZEN): the type
-- records as the game holds them now: {projectile, rpm (the Gatling type's RPM, Y slot), casing = {particles,
-- parameters, layout}, chin = {projectile, rpm, casing}}, or nil, code, reason. Never a live entity, never used to
-- configure.
function M.reference(world)
    local gpw=gatling.type_record(world,PWT,G.gatlingResource)
    local cpw=gatling.type_record(world,PWT,CHIN)
    if not(gpw and cpw)then return nil,'UNAVAILABLE','the Gatling\'s or the chin turret\'s type record is unreadable'end
    local gmg=gatling.type_record(world,G.magazineTypes,G.gatlingResource)
    local cmg=gatling.type_record(world,G.magazineTypes,CHIN)
    if not(gmg and cmg)then return nil,'UNAVAILABLE','the Gatling\'s or the chin turret\'s magazine is unreadable'end
    local function magazine(raw)
        return {capacity=b.u32(raw,AM.capacity),spares=b.u32(raw,AM.spareMagazines),
            max_spares=b.u32(raw,AM.maxSpareMagazines),chamber=raw:byte(AM.chamber+1)}
    end
    return {projectile=b.u32(gpw,0),rpm=f32(gpw,8),casing=casing_of(gpw),magazine=magazine(gmg),
        chin={projectile=b.u32(cpw,0),rpm=f32(cpw,8),casing=casing_of(cpw),magazine=magazine(cmg)}}
end

-- The Gatling rate for THIS turret, as the game gives a weapon made now: the frozen Gatling RPM times the factor the
-- game applied to this turret's own rate when it was made (its own current RPM over its type's frozen RPM: 1, or the
-- rate seed factor while mission modifier 0x33 is active). Nothing else in the world is read. Returns rpm, source text;
-- or nil, code, reason.
-- The factor the game applied to this turret's rate at its creation (its current RPM over its type's: 1, or the
-- mission rate seed's factor), or nil, code, reason.
function M.turret_factor(world,turret)
    local F=M.FROZEN
    local w=pelicans.weapon_config(world,turret)
    if not(w and w.currentRpm)then return nil,'UNAVAILABLE','the chin turret\'s rate is unreadable'end
    local factor=w.currentRpm/F.chin.rpm
    local known
    for _,f in ipairs({1,D.rateSeed.factor})do if math.abs(factor-f)<1e-4 then known=f end end
    if not known then
        return nil,'RATE_UNEXPECTED',('the chin turret runs %.2f RPM, %.4f x its type\'s %.0f: not a rate the game gives'):format(
            w.currentRpm,factor,F.chin.rpm)
    end
    return known
end
function M.gatling_rpm(world,turret)
    local F=M.FROZEN
    local known,code,reason=M.turret_factor(world,turret)
    if not known then return nil,code,reason end
    local rpm=b.value(b.encode(F.rpm*known,'f32'),0,'f32')   -- the game multiplies in single precision
    return rpm,('the frozen Gatling rate %.0f RPM x %.2f (the factor the game applied to this turret)'):format(F.rpm,known)
end

------------------------------------------------------------------------------------ the firing sound, per instance --
-- docs/research/pelican-maelstrom-sound-F5FEE03DCFDB.md, docs/research/weapon-sounds-F5FEE03DCFDB.md; the catalogue
-- runtime/weapon_sounds.lua (domains/weapon_sounds.lua). A projectile weapon's firing sound is part of its RESOLVED
-- ProjectileWeapon record (its own copy when it has one): every shot reads its per-shot Wwise event (+0x104) and
-- whether that goes out as MIDI notes (+0xED) from that record (0x612A13 -> 0x614BAD, 0x614C4D); the update posts the
-- loop start (+0xFC) on the rising edge of the fire decision and the release posts the loop stop (+0x100) on its
-- falling edge, each read from that record then (0x617058 -> 0x6170FA, 0x6172DA -> 0x616806). No event id is cached
-- anywhere. The one per-instance value the game derives from it is the instance record's +0x38 (creation 0x611CD9 ->
-- 0x611D67): read only at the trigger release (0x6168B2), it keeps a MIDI weapon's audio source for the notes still
-- scheduled. So a sound is THIS turret's own copy's +0xED, +0xFC, +0x100 and +0x104 (only those that differ from the
-- chin turret's own: a shot = +0x104 and, for MIDI, +0xED; a loop = +0xFC, +0x100 and +0x104 = 0, as the loop weapons'
-- own records) plus its own instance +0x38 (MIDI only), exactly the values the game derives for a weapon whose record
-- names that sound: guarded writes while it is quiet (no trigger, fire state, fire decision or MIDI note: no loop
-- playing), never a shared record, never a Wwise call. The sound's bank must be resident (a package that lists it).
-- M.SOUNDS: the catalogue (name -> entry); names resolve through its aliases ('maelstrom_main_gun').
local WS=require('hd2runtime/runtime/weapon_sounds')
local SD=D.sound
M.SOUNDS=WS.SOUNDS
local sound_gates={}      -- canonical sound name -> the asset gate of its stratagem's call-in package(s)
local mirrored={}         -- turret -> true: its own copy was made on this machine by mirror_configure
local CHIN_SOUND=b.unhex(SD.chin.blockBytes)
assert(WS.CHIN.blockBytes==SD.chin.blockBytes,'the sound catalogue and the Pelican domain disagree on the chin turret')
local function sound_names()return WS.hint()end
M.sound_names=sound_names
-- A gun's sound name -> its canonical catalogue name; nil for none or the chin turret's own (nothing to write); false
-- and why for a name the catalogue does not have.
function M.sound_name(name)
    if name==nil then return nil end
    local canonical,s=WS.resolve(name)
    if not s then return false,'sound must be '..sound_names()end
    if s.own then return nil end
    return canonical
end
local function sound_proven(world)
    for _,pin in ipairs(WS.PINS)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,('game+%X changed (%s)'):format(pin.rva,pin.label)
        end
    end
    return true
end
-- The packages the Runtime requests for a sound: its catalogue stratagem's call-in packages that list its bank
-- (core/assets.lua dependencies_for_stratagem), or nil (resident-only, the chin turret's own, or unknown).
function M.sound_dependencies(name)
    local _,s=WS.resolve(name)
    if not(s and s.stratagemId and not s.own)then return nil end
    local out={}
    for _,dep in ipairs(core_assets.dependencies_for_stratagem(s.stratagemId,s.stratagem)or{})do
        for _,p in ipairs(s.requests)do if dep.package==p then out[#out+1]=dep end end
    end
    return #out>0 and out or nil
end
-- The sound's package through the Runtime's asset loader (as M.assets): 'ready', 'waiting' or 'failed' and why; logs
-- "assets for pelican-sound-<name> requested" / "... resident". The reference is retained for the session. A
-- resident-only sound (no stratagem provides its bank) is 'ready' only while a package listing its bank is resident
-- here, else 'failed' (ASSET_UNAVAILABLE): the Runtime requests nothing for it.
function M.sound_assets(world,dt,name)
    local canonical,s=WS.resolve(name)
    if not s then return'failed','INVALID: no firing sound '..tostring(name)end
    if s.own then return'ready'end
    if not s.stratagem then
        local package,_,why=M.sound_resident(world,canonical)
        if package then return'ready'end
        return'failed','ASSET_UNAVAILABLE: '..tostring(why)
    end
    local gate=sound_gates[canonical]
    if not gate then
        local deps=M.sound_dependencies(canonical)
        if not deps then return'failed','ASSET_UNAVAILABLE: no package is known for the '..s.label..' sound'end
        gate=core_assets.gate(world.runtime,{id='pelican-sound-'..canonical,asset_dependencies=deps},log_module.emit)
        sound_gates[canonical]=gate
    end
    return gate.tick(dt or 0)
end
-- Whether a sound's bank is resident here: any package of its catalogue entry that lists it, the requested call-in
-- packages first (read, never assumed). Returns that package's entry {package, label}, or nil, 'ASSET_UNAVAILABLE'
-- (or 'INVALID'), why.
function M.sound_resident(world,name)
    local _,s=WS.resolve(name)
    if not s then return nil,'INVALID','no firing sound '..tostring(name)end
    for _,p in ipairs(s.packages)do
        local ok,state=pcall(core_assets.state,world.runtime,p.package)
        if ok and state=='resident'then return p end
    end
    return nil,'ASSET_UNAVAILABLE',('the %s sound\'s bank (%s) is not resident%s'):format(s.label,s.bank.name,
        s.stratagem and': request it first (M.sound_assets)'or' (resident-only: no stratagem\'s package provides it; it '
        ..'is used only while the game has a package listing it resident)')
end
local function sound_block(raw)
    local out={}
    for k,blk in ipairs(SD.record.blocks)do out[k]=raw:sub(blk[1]+1,blk[1]+blk[2])end
    return table.concat(out)
end
-- One projectile weapon's firing sound, read-only: {from ('copy': its own record, or 'type'), copy_at, raw (the
-- resolved record), midi (+0xED), event (+0x104, hex), loop_start, loop_stop (hex), block (the firing-sound block's
-- bytes), name ('chin': the chin turret's own sound, else nil; M.sound_matches compares with a catalogue entry),
-- instance = {at, raw, midi (+0x38), firing (+0), trigger (+1), decision (+0x10), queue (no MIDI note scheduled,
-- +0x20..), quiet}}, or nil. `resource` (hex) names its type when it has no copy.
function M.sound_state(world,entity,resource)
    local PW,I=TW.projectileWeapon,SD.instance
    local pw=world.view.pointer(world.game+PW.global)
    local index=pw and pw~=0 and pelicans.index_of(world,pw,map_at(PW.map),entity)
    if not index then return nil end
    local instances=world.view.pointer(pw+PW.instances)
    local inst_at=instances and instances~=0 and instances+index*PW.instanceStride
    local inst=inst_at and world.view.read(inst_at,PW.instanceStride)
    if not inst then return nil end
    local ci=pelicans.index_of(world,pw,map_at(PW.copies),entity)
    local copies=ci and world.view.pointer(pw+PW.copyRecords)
    local rec,from,copy_at
    if copies and copies~=0 then
        copy_at=copies+ci*PW.copyStride
        rec,from=world.view.read(copy_at,SD.record.stride),'copy'
    else
        rec,from=resource and gatling.type_record(world,PWT,resource),'type'
    end
    if not(rec and #rec>=SD.record.stride)then return nil end
    local block=sound_block(rec)
    local i={at=inst_at,raw=inst,midi=inst:byte(I.midi+1),firing=inst:byte(I.firing+1),trigger=inst:byte(I.trigger+1),
        decision=inst:byte(I.decision+1),queue=inst:sub(I.queue+1,I.queue+I.queueSize)==string.rep('\0',I.queueSize)}
    i.quiet=i.firing==0 and i.trigger==0 and i.decision==0 and i.queue
    return {from=from,copy_at=copy_at,raw=rec,midi=rec:byte(SD.record.midi+1),
        event=('%08X'):format(b.u32(rec,SD.record.single)),loop_start=('%08X'):format(b.u32(rec,SD.record.loopStart)),
        loop_stop=('%08X'):format(b.u32(rec,SD.record.loopStop)),block=block,name=block==CHIN_SOUND and'chin'or nil,
        instance=i}
end
-- Whether a turret's sound state (M.sound_state) is exactly a catalogue sound on the chin turret: its firing-sound
-- block the chin turret's own with that sound's writes, and its instance's MIDI flag that sound's.
function M.sound_matches(st,name)
    local _,s=WS.resolve(name)
    return st~=nil and s~=nil and st.block==b.unhex(s.blockBytes)and st.instance.midi==s.midi
end
-- The writes of a sound for one turret whose OWN copy exists (st: M.sound_state after the copy): a transaction
-- {snapshots, changes}, or nil, why, retry (true when only its firing state stands in the way). Only its own copy's
-- writes (+0xED, +0xFC, +0x100, +0x104: those that differ from the chin turret's own) and its own instance record's
-- (+0x38, MIDI only), each from exactly the chin turret's own value.
local function sound_plan(world,turret,name,st,prefix)
    local _,s=WS.resolve(name)
    if st.from~='copy'or not st.copy_at then return nil,'it has no ProjectileWeapon copy of its own'end
    if st.block~=CHIN_SOUND then return nil,'its copy does not hold the chin turret\'s own firing sound'end
    local inst=st.instance
    if inst.midi~=SD.chin.midi then return nil,'its instance record\'s MIDI flag is not the one its type gives'end
    if not inst.quiet then return nil,'it is firing (its trigger, fire state or MIDI notes are set)',true end
    local copy_owner=pelicans.owner_of(world,st.copy_at,SD.record.stride)
    local inst_owner=pelicans.owner_of(world,inst.at,TW.projectileWeapon.instanceStride)
    if not(copy_owner and inst_owner)then return nil,'its copy or its instance record is not private read-write memory'end
    local span=SD.record.span
    local identity={component='ProjectileWeapon',component_type='native',unique_owner=true,owner_count=1}
    local plan={snapshots={{owner=copy_owner,offset=st.copy_at+span[1]-copy_owner.base,
        bytes=st.raw:sub(span[1]+1,span[2])},{owner=inst_owner,offset=inst.at-inst_owner.base,bytes=inst.raw}},changes={}}
    local function add(owner,at,raw,w,what)
        local from,to=b.unhex(w.from),b.unhex(w.to)
        local current=raw:sub(w.offset+1,w.offset+w.size)
        assert(#from==w.size and #to==w.size and current==from,'the sound\'s write source differs')
        plan.changes[#plan.changes+1]={label=prefix..turret..'.'..what..w.name,owner=owner,offset=at+w.offset-owner.base,
            expected=from,desired=to,before=current,already_desired=false,identity=identity,chain={}}
    end
    for _,w in ipairs(s.writes)do add(copy_owner,st.copy_at,st.raw,w,'copy.sound_')end
    for _,w in ipairs(s.instanceWrites)do add(inst_owner,inst.at,inst.raw,w,'instance.sound_')end
    if #plan.changes==0 then return nil,'the sound is the chin turret\'s own'end
    return plan
end
-- Read back: its own copy names the sound and its instance record keeps its source as the game would; st or nil.
local function sound_verify(world,turret,name)
    local st=M.sound_state(world,turret,CHIN)
    return st~=nil and st.from=='copy'and M.sound_matches(st,name),st
end
-- The sound's own weapon type record (its source weapon), read-only: compared whole before and after a write.
local function sound_shared(world,name)return gatling.type_record(world,PWT,WS.entry(name).resource)end
-- Before a copy is made: whether the turret's type record still gives the chin turret's own sound and it is quiet.
-- {name, wanted, reason, retry, before}.
local function sound_precheck(world,turret,name)
    local out={name=name,applied=false}
    local st=M.sound_state(world,turret,CHIN)
    out.before=st
    if not st then out.reason='its firing sound is unreadable'
    elseif st.from~='type'then out.reason='it already resolves its own record'
    elseif st.name~='chin'then out.reason='its type\'s firing sound is not the chin turret\'s'
    elseif st.instance.midi~=SD.chin.midi then out.reason='its instance record\'s MIDI flag is not the one its type gives'
    elseif not st.instance.quiet then out.reason,out.retry='it is firing (its trigger, fire state or MIDI notes are set)',true
    else out.wanted=true end
    return out
end
-- What a sound posts, for the log: "event E5CA1945 as MIDI notes", "loop 98F18D8B / 0C5CA529".
local function sound_events(s)
    if s.kind=='loop'then return('loop %s / %s'):format(s.start,s.stop)end
    return('event %s%s'):format(s.event,s.midi==1 and' as MIDI notes'or'')
end
M.sound_events=sound_events
local function sound_text(s)
    if not s then return''end
    local entry=WS.entry(s.name)
    if s.applied then return(', sound %s %s (%s)'):format(s.name,tostring(s.applied),entry.kind=='loop'and
        (entry.start..' / '..entry.stop)or entry.event)end
    return(', sound %s NOT APPLIED (%s)'):format(s.name,tostring(s.reason))
end
M.sound_text=sound_text

-- M.apply_sound(world, turret, name, label, opts): the sound on a turret whose own copy the Runtime made already on
-- THIS machine (configure; opts.mirror: mirror_configure), later: when its bank became resident or it stopped firing.
-- The same writes, in their own guarded transaction, with the same guards: the sound's pins, the game thread, a
-- mission, the bank resident, the turret quiet, its copy still holding the chin turret's own sound, its type and the
-- sound's own weapon type compared whole before and after. opts.quiet: no log line for ASSET_UNAVAILABLE. Returns
-- {applied, writes, verify = {sound, shared, sound_shared}, verified, package} or nil, code, reason: INVALID,
-- NOT_GAME_THREAD, UNSUPPORTED_BUILD, NOT_IN_MISSION, NOT_CONFIGURED, UNAVAILABLE, CREATED_HERE, NOT_CREATED_HERE,
-- ASSET_UNAVAILABLE, ALREADY_APPLIED (also the chin turret's own sound), NOT_QUIET (only its firing state stands in the
-- way: try again), SOUND_UNEXPECTED, GUARD_REJECTED. NOT_QUIET and ALREADY_APPLIED are not logged.
function M.apply_sound(world,turret,name,label,opts)
    label=tostring(label or'?')
    opts=opts or{}
    local prefix=opts.mirror and'MIRROR 'or''
    local function refuse(code,reason,silent)
        if not silent then log(('%sSOUND REFUSED (%s): chin turret %s: %s: %s'):format(prefix,label,tostring(turret),code,reason))end
        return nil,code,reason
    end
    local canonical,s=WS.resolve(name)
    if not s then return refuse('INVALID','sound must be '..sound_names())end
    if s.own then return refuse('ALREADY_APPLIED','the chin turret\'s own sound',true)end
    name=canonical
    if not scheduler.in_update()then return refuse('NOT_GAME_THREAD','only inside the Runtime\'s own update')end
    local ok,why=M.prove(world)
    if not ok then return refuse('UNSUPPORTED_BUILD',tostring(why))end
    ok,why=sound_proven(world)
    if not ok then return refuse('UNSUPPORTED_BUILD',why)end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return refuse('NOT_IN_MISSION','in a mission only')end
    if not(opts.mirror and mirrored[turret]or not opts.mirror and configured[turret])then
        return refuse('NOT_CONFIGURED','the Runtime made no copy of this turret\'s weapon on this machine')
    end
    local _,raw=pelicans.record_address(world,turret)
    if not raw then return refuse('UNAVAILABLE','the chin turret\'s world record is unreadable')end
    local here=b.u32(raw,0x14)%2==1
    if opts.mirror and here then return refuse('CREATED_HERE','this machine created that turret: its owner configures it')end
    if not opts.mirror and not here then return refuse('NOT_CREATED_HERE','not this machine\'s turret: it is mirrored')end
    local package,acode,areason=M.sound_resident(world,name)
    if not package then return refuse(acode,areason,opts.quiet)end
    local st=M.sound_state(world,turret,CHIN)
    if not st then return refuse('UNAVAILABLE','its firing sound is unreadable')end
    if st.from=='copy'and M.sound_matches(st,name)then
        return refuse('ALREADY_APPLIED','its own copy names that sound already',true)
    end
    local plan,reason,retry=sound_plan(world,turret,name,st,opts.mirror and'mirror.turret.'or'turret.')
    if not plan then return refuse(retry and'NOT_QUIET'or'SOUND_UNEXPECTED',reason,retry)end
    local before,shared_before=gatling.shared(world),sound_shared(world,name)
    local report=transaction.apply(world.runtime,plan)
    metrics.count('pelican_weapon.transactions')
    if report.status~='APPLIED'then return refuse('GUARD_REJECTED','the sound writes were refused: '..tostring(report.reason))end
    local applied,after=sound_verify(world,turret,name)
    local result={applied=applied,writes=report.writes,after=after,package=package,verify={sound=applied,
        shared=gatling.shared_same(before,gatling.shared(world)),
        sound_shared=shared_before~=nil and shared_before==sound_shared(world,name)}}
    result.verified=result.verify.sound and result.verify.shared and result.verify.sound_shared
    log(('%sSOUND APPLIED (%s): chin turret %d: its own copy posts the %s\'s %s (bank %s, resident through %s); '
        ..'%d writes; shared definitions unchanged %s; verified %s'):format(prefix,label,turret,s.label,sound_events(s),
        s.bank.name,package.label,report.writes,tostring(result.verify.shared and result.verify.sound_shared),
        tostring(result.verified)))
    return result
end

-- M.configure(world, pelican, spec, label): spec = {projectile, rpm (a number, or 'gatling': the frozen Gatling rate
-- for this turret, M.gatling_rpm), hold_rate (true, with a number rpm: as 'gatling' does, the copy's rate slot becomes
-- rpm and the current RPM rpm x the factor the game applied to this turret, M.turret_factor, so a later re-derivation
-- by the game gives the same rate; without it a number is the current RPM only), casing (true: the frozen Gatling
-- casing),
-- pattern (true: the Gatling's ammunition pattern), ammo (a factor: its own magazine holds that many times the Gatling
-- Sentry's magazine capacity, full), recoil (true or 'zero': M.configure_recoil), spread ('precise', 'mild',
-- 'gatling' or a width in mrad: M.configure_spread), rate_factor (1, 1.5 or 2: a tuning factor on the Gatling rate read
-- frozen; current RPM and rate slot alike), credit (true: its kills credited to the host who called it,
-- M.configure_credit), sound (a catalogue name, runtime/weapon_sounds.lua: its own copy's firing sound, a shot or a
-- loop, written in the same transaction while it is quiet; its bank must be resident: ASSET_UNAVAILABLE otherwise;
-- nil or 'pelican/chin_autocannon': its own)}. One guarded transaction on the
-- turret's own ProjectileWeapon copy
-- (projectile; with 'gatling' its rate slot too, so a later re-derivation by the game gives the same rate; the casing)
-- and its own current RPM. The casing only before the turret's first shot: its pooled casing effect is looked up then
-- and kept (instance +0x90). The pattern and the ammunition: the game's magazine copy routine, then one guarded
-- transaction on its own magazine copy and live magazine (M.configure_magazine). Returns {pelican, turret, spec, writes,
-- verify, verified, reference, rpm_source, casing = {before, after, applied, reason}, ammo = {reference, capacity,
-- rounds, applied, reason, read}} or nil, code, reason.
function M.configure(world,pelican,spec,label)
    label=tostring(label or'?')
    spec=spec or{}
    local function refuse(code,reason)
        log(('REFUSED (%s): Pelican %s: %s: %s'):format(label,tostring(pelican),code,reason))
        metrics.count('pelican_weapon.refused')
        return nil,code,reason
    end
    local projectile,rpm=spec.projectile or M.GATLING.projectile,spec.rpm or 600
    if not(type(projectile)=='number'and projectile>0 and projectile<65536 and projectile%1==0)then
        return refuse('INVALID','projectile must be a projectile type number')
    end
    if not(rpm=='gatling'or type(rpm)=='number'and rpm>=30 and rpm<=3000)then
        return refuse('INVALID','rpm must be 30..3000 or \'gatling\'')
    end
    if spec.ammo~=nil and spec.ammo~=true then return refuse('INVALID','ammo must be true (the safe maximum)')end
    -- A tuning factor on the frozen Gatling rate (1, 1.5 or 2; that rate itself stays within 30..3000).
    local factor=spec.rate_factor or 1
    if not M.RATE_FACTORS[factor]then return refuse('INVALID','rate_factor must be 1, 1.5 or 2')end
    if factor~=1 and rpm~='gatling'then
        return refuse('INVALID','rate_factor applies to the frozen Gatling rate (rpm = \'gatling\') only')
    end
    if spec.hold_rate~=nil and not(spec.hold_rate==true and type(rpm)=='number')then
        return refuse('INVALID','hold_rate is true, with a number rpm')
    end
    -- A catalogue name (or alias), canonical from here; the chin turret's own sound is no sound to write.
    local sound,swhy=M.sound_name(spec.sound)
    if sound==false then return refuse('INVALID',swhy)end
    local needs={'native_weapon_copy'}
    if spec.pattern or spec.ammo then needs[2]='native_magazine_copy'end
    local state,code,reason=guards(world,pelican,needs)
    if not state then return refuse(code,reason)end
    local pok,resident=pcall(core_assets.state,world.runtime,gatling.asset_dependency().package)
    if not(pok and resident=='resident')then
        return refuse('ASSET_UNAVAILABLE','the projectile\'s package is not resident: request it first (M.assets, "'
            ..M.ASSET_ID..'")')
    end
    -- The firing sound: its pins, and its bank resident (any catalogued package that lists it).
    local sound_package
    if sound then
        local sok,swhy=sound_proven(world)
        if not sok then return refuse('UNSUPPORTED_BUILD',swhy)end
        local scode,sreason
        sound_package,scode,sreason=M.sound_resident(world,sound)
        if not sound_package then return refuse(scode,sreason)end
    end
    -- The AP4 donor: its own package resident and its live row the catalogued round (its type, damage record, velocity
    -- and mass). Only this turret's own ProjectileWeapon copy will name it; the rows are compared before and after.
    local donor
    if projectile==M.AP4.projectile then
        local dependency=M.ap_dependency()
        local aok,ares=pcall(core_assets.state,world.runtime,dependency and dependency.package)
        if not(dependency and aok and ares=='resident')then
            return refuse('ASSET_UNAVAILABLE','the AP4 donor\'s package is not resident: request it first (M.ap_assets, "'
                ..M.AP_ASSET_ID..'")')
        end
        local A,id=M.AP4,M.projectile_identity(world,projectile)
        if not(id and id.type==A.projectile and id.damage==A.damage and id.velocity==A.velocity and id.mass==A.mass)then
            return refuse('DONOR_UNEXPECTED',('projectile %d\'s row does not read as the %s round (damage %d, %g m/s, mass '
                ..'%g)'):format(projectile,A.name,A.damage,A.velocity,A.mass))
        end
        donor={projectile=projectile,name=A.name,damage=id.damage,ap=A.ap,velocity=id.velocity,mass=id.mass}
    end
    -- The ammunition pattern: true (the Gatling's) or 'strafing_run' (the Eagle Strafing Run's, with its HE round).
    local pattern=spec.pattern==true and M.GATLING.pattern or spec.pattern=='strafing_run'and M.STRAFING.pattern or nil
    if spec.pattern~=nil and spec.pattern~=false and not pattern then
        return refuse('INVALID','pattern must be true (the Gatling\'s) or \'strafing_run\'')
    end
    -- The Eagle Strafing Run's HE round (and, with its pattern, its plain twin): the Strafing Run's package resident and
    -- each live row the reviewed round (its type, damage record, velocity and mass).
    if spec.pattern=='strafing_run'and projectile~=M.STRAFING.projectile then
        return refuse('INVALID','the Strafing Run pattern goes with its HE round')
    end
    if projectile==M.STRAFING.projectile then
        local S=M.STRAFING
        local dependency=M.strafing_dependency()
        local sok,sres=pcall(core_assets.state,world.runtime,dependency and dependency.package)
        if not(dependency and sok and sres=='resident')then
            return refuse('ASSET_UNAVAILABLE','the Eagle Strafing Run\'s package is not resident: request it first '
                ..'(M.strafing_assets, "'..M.STRAFING_ASSET_ID..'")')
        end
        for _,kind in ipairs(spec.pattern=='strafing_run'and{S.projectile,S.plain}or{S.projectile})do
            local id=M.projectile_identity(world,kind)
            if not(id and id.type==kind and id.damage==S.damage and id.velocity==S.velocity and id.mass==S.mass)then
                return refuse('DONOR_UNEXPECTED',('projectile %d\'s row does not read as the %s round (damage %d, %g m/s, '
                    ..'mass %g)'):format(kind,S.name,S.damage,S.velocity,S.mass))
            end
        end
        donor={projectile=projectile,name=S.name,damage=S.damage,velocity=S.velocity,mass=S.mass,
            pattern=spec.pattern=='strafing_run'and S.pattern or nil}
    end
    local function rows()
        local standard,own=M.projectile_identity(world,M.AP4.standard.projectile),M.projectile_identity(world,projectile)
        local plain=pattern==M.STRAFING.pattern and M.projectile_identity(world,M.STRAFING.plain)
        return (standard and standard.raw or'')..'|'..(own and own.raw or'')..'|'..(plain and plain.raw or'')
    end
    local rows_before=rows()
    local t=state.turret
    local w=t.weapon
    if not(w and w.path=='magazine'and w.magazine and not w.magazine.pattern)then
        return refuse('TURRET_UNEXPECTED','the chin turret is not a magazine weapon without a pattern')
    end
    if w.copy then return refuse('ALREADY_CONFIGURED','the chin turret already has its own ProjectileWeapon record')end
    -- The Gatling's values: frozen, never read from the world (M.FROZEN).
    local ref,rcode,rreason
    if rpm=='gatling'or spec.casing or spec.ammo then ref=M.FROZEN end
    local rpm_source='requested'
    if rpm=='gatling'then
        rpm,rcode,rreason=M.gatling_rpm(world,t.entity)
        if not rpm then return refuse(rcode,rreason)end
        rpm_source=rcode
        if not(rpm>=30 and rpm<=3000)then return refuse('RATE_UNEXPECTED','the Gatling rate reads '..rpm)end
        if factor~=1 then
            rpm=b.value(b.encode(rpm*factor,'f32'),0,'f32')
            rpm_source=('%s, x %g (the tuning)'):format(rpm_source,factor)
        end
    end
    -- The copy's rate slot (with 'gatling'): the frozen Gatling RPM times the tuning factor; with hold_rate: the
    -- requested rate, and the current RPM that rate times this turret's own factor (as the game derives it).
    local slot_rpm=rpm_source~='requested'and b.value(b.encode(ref.rpm*factor,'f32'),0,'f32')or nil
    if spec.hold_rate then
        local f,fcode,freason=M.turret_factor(world,t.entity)
        if not f then return refuse(fcode,freason)end
        slot_rpm=b.value(b.encode(rpm,'f32'),0,'f32')
        rpm=b.value(b.encode(slot_rpm*f,'f32'),0,'f32')
        rpm_source=('the requested %g RPM x %.2f (the factor the game applied to this turret)'):format(slot_rpm,f)
    end
    -- The casing: only when this turret's own record still holds its type's casing at the ejector nodes the frozen
    -- Gatling casing uses (research: both types' fire effects differ only in the casing), and the turret has not fired
    -- (no casing effect kept yet).
    local casing={before=spec.casing and M.casing_state(world,t.entity,CHIN)or nil,applied=false}
    if spec.casing then
        local c=casing.before
        if not c then casing.reason='its casing is unreadable'
        elseif c.from~='type'then casing.reason='it already resolves its own record'
        elseif c.cached~=0 then casing.reason='it has fired already: its casing effect #'..c.cached..' is kept'
        elseif c.nodes_raw~=ref.casing.nodes or ref.casing.nodes~=ref.chin.casing.nodes then
            casing.reason='its fire effects use other nodes than the frozen Gatling casing\'s'
        elseif c.particles~=ref.chin.casing.particles or c.parameters~=ref.chin.casing.parameters then
            casing.reason='its casing is not its type\'s'
        else casing.wanted=true end
        if not casing.wanted then
            log(('CASING NOT APPLIED (%s): chin turret %d: %s'):format(label,t.entity,casing.reason))
        end
    end
    -- The firing sound: only while its type still gives the chin turret's own sound and it is quiet (no trigger, no
    -- fire state, no MIDI note scheduled); otherwise the rest is configured and the sound is reported (retry: it fires).
    local sounding=sound and sound_precheck(world,t.entity,sound)
    if sounding and not sounding.wanted then
        log(('SOUND NOT APPLIED (%s): chin turret %d: %s'):format(label,t.entity,sounding.reason))
    end
    local runtime=world.runtime
    local PW=TW.projectileWeapon
    local pw=world.view.pointer(world.game+PW.global)
    local count=pw and world.view.read(pw+PW.copyCount,4)
    local capacity=pw and world.view.read(pw+G.copyCapacity,4)
    if not(count and capacity and b.u32(count,0)+1<b.u32(capacity,0))then
        return refuse('NO_CAPACITY','no room for a per-instance ProjectileWeapon copy')
    end
    local record=pelicans.record_address(world,t.entity)
    if not record then return refuse('UNAVAILABLE','the chin turret\'s world record is unreadable')end
    local mag=magazine_state(world,t.entity)
    if spec.pattern or spec.ammo then
        if not(mag and mag.record and mag.entry and mag.count and mag.capacity and mag.count+1<mag.capacity)then
            return refuse('NO_CAPACITY','no room for a per-instance magazine copy')
        end
        if mag.copy then return refuse('ALREADY_CONFIGURED','the chin turret already has its own magazine record')end
    end
    -- The ammunition: the safe maximum (the rounds' network field, 2047) as its own magazine's capacity, full as the
    -- game's own refill fills one (the rounds = the capacity, a round chambered). Only while a round is chambered, its
    -- two round counts agree, and it is the host's.
    local ammo
    if spec.ammo then
        ammo={reference=ref.magazine.capacity,applied=false}
        ammo.capacity=M.AMMO_MAX
        ammo.rounds=M.AMMO_MAX
        local a=M.ammo_state(world,t.entity,CHIN)
        local _,raw=pelicans.record_address(world,t.entity)
        ammo.before=a
        if not a then ammo.reason='its magazine is unreadable'
        elseif not(ammo.capacity>0 and ammo.capacity<=2047)then ammo.reason='the safe maximum reads '..ammo.capacity
        elseif ref.chin.magazine.chamber~=1 or ref.magazine.chamber~=1 then ammo.reason='a magazine without a chamber'
        elseif a.capacity~=ref.chin.magazine.capacity then ammo.reason='its magazine is not its type\'s'
        elseif a.rounds~=a.working then ammo.reason=('its two round counts differ (%d, %d)'):format(a.rounds,a.working)
        elseif a.chambered==0 or a.chamber_empty~=0 then ammo.reason='no round is chambered'
        elseif not(raw and b.u32(raw,0x14)%2==1)then ammo.reason='it is not the host\'s (no authority)'
        else ammo.wanted=true end
        if not ammo.wanted then log(('AMMO NOT APPLIED (%s): chin turret %d: %s'):format(label,t.entity,ammo.reason))end
    end
    local before=gatling.shared(world)
    log(('BEFORE (%s): %s'):format(label,gatling.state_text(state)))
    log(('ATTEMPT (%s): chin turret %d: 1. ProjectileWeapon copy routine (game+%X); 2. guarded writes: projectile %d -> %d, '
        ..'current RPM %.0f -> %.2f (%s)%s%s%s'):format(label,t.entity,G.copy.rva,w.copy and w.copy.projectileType or 120,
        projectile,w.currentRpm or 0,rpm,rpm_source,slot_rpm and(', rate slot %.0f -> %.0f'):format(
        M.FROZEN.chin.rpm,slot_rpm)or'',casing.wanted and(', casing %s -> %s'):format(hex(ref.chin.casing.particles),
        hex(ref.casing.particles))or'',(spec.pattern or(ammo and ammo.wanted))and(('; 3. magazine copy routine (game+%X)'
        ..'%s%s'):format(MC.rva,pattern and(', the pattern '..table.concat(pattern,','))or'',
        ammo and ammo.wanted and((', capacity %d -> %d, rounds %d -> %d (+1 chambered)'):format(ammo.before.capacity,
        ammo.capacity,ammo.before.rounds,ammo.rounds))or''))or''))
    metrics.count('pelican_weapon.native_calls')
    runtime.native_weapon_copy(world.game+G.copy.rva,pw,record)
    local ci=pelicans.index_of(world,pw,map_at(PW.copies),t.entity)
    local copies=ci and world.view.pointer(pw+PW.copyRecords)
    local copy_at=copies and copies~=0 and copies+ci*PW.copyStride
    local copy=copy_at and world.view.read(copy_at,CS.effectsEnd)
    if not copy then return refuse('COPY_FAILED','no per-instance ProjectileWeapon copy after the call')end
    local current=world.view.pointer(pw+PW.current)
    local entry_at=current and current~=0 and current+w.index*PW.currentStride
    local entry=entry_at and world.view.read(entry_at,PW.currentStride)
    local copy_owner=pelicans.owner_of(world,copy_at,PW.copyStride)
    local entry_owner=entry_at and pelicans.owner_of(world,entry_at,PW.currentStride)
    if not(entry and copy_owner and entry_owner)then
        return refuse('NOT_PRIVATE','the copy or the current-RPM entry is not in private read-write memory')
    end
    -- The copy is the chin turret's own record, unmodified: its casing must still be the chin turret's.
    if casing.wanted and copy:sub(CS.particles+1,CS.particles+8)~=ref.chin.casing.particles then
        casing.wanted=nil;casing.reason='the copy does not hold the chin turret\'s casing'
        log(('CASING NOT APPLIED (%s): chin turret %d: %s'):format(label,t.entity,casing.reason))
    end
    local identity={component='ProjectileWeapon',component_type='native',unique_owner=true,owner_count=1}
    local function change(name,at,desired)
        return {label='turret.'..t.entity..'.'..name,owner=copy_owner,offset=copy_at+at-copy_owner.base,
            expected=copy:sub(at+1,at+#desired),desired=desired,before=copy:sub(at+1,at+#desired),already_desired=false,
            identity=identity,chain={}}
    end
    local plan={snapshots={{owner=copy_owner,offset=copy_at-copy_owner.base,bytes=copy},
            {owner=entry_owner,offset=entry_at-entry_owner.base,bytes=entry}},
        changes={change('copy.projectile',PW.projectileType,u32(projectile)),
            {label='turret.'..t.entity..'.current_rpm',owner=entry_owner,offset=entry_at+PW.currentRpm-entry_owner.base,
                expected=entry:sub(PW.currentRpm+1,PW.currentRpm+4),desired=b.encode(rpm,'f32'),
                before=entry:sub(PW.currentRpm+1,PW.currentRpm+4),already_desired=false,identity=identity,chain={}}}}
    if slot_rpm then
        plan.changes[#plan.changes+1]=change('copy.rate_slot',PW.rpmSlots+4,b.encode(slot_rpm,'f32'))
    end
    if casing.wanted then
        plan.changes[#plan.changes+1]=change('copy.casing',CS.particles,ref.casing.particles)
        for k=0,CS.parametersSize-4,4 do
            plan.changes[#plan.changes+1]=change('copy.casing_parameter'..(k/4+1),CS.parameters+k,
                ref.casing.parameters:sub(k+1,k+4))
        end
    end
    -- The firing sound, in the same transaction: its own fresh copy's +0xED and +0x104 and its own instance +0x38.
    if sounding and sounding.wanted then
        local st=M.sound_state(world,t.entity,CHIN)
        local splan,why,retry
        if st then splan,why,retry=sound_plan(world,t.entity,sound,st,'turret.')else why='its firing sound is unreadable'end
        if splan then
            for _,snap in ipairs(splan.snapshots)do plan.snapshots[#plan.snapshots+1]=snap end
            for _,c in ipairs(splan.changes)do plan.changes[#plan.changes+1]=c end
            sounding.shared_before=sound_shared(world,sound)
        else
            sounding.wanted,sounding.reason,sounding.retry=nil,why,retry
            log(('SOUND NOT APPLIED (%s): chin turret %d: %s'):format(label,t.entity,why))
        end
    end
    local report=transaction.apply(runtime,plan)
    metrics.count('pelican_weapon.transactions')
    if report.status~='APPLIED'then return refuse('GUARD_REJECTED','the weapon writes were refused: '..tostring(report.reason))end
    local writes=report.writes
    local result={pelican=pelican,turret=t.entity,spec={projectile=projectile,rpm=rpm,rate_factor=factor,
        hold_rate=spec.hold_rate,slot_rpm=slot_rpm,pattern=spec.pattern or false,
        casing=spec.casing==true,ammo=spec.ammo,sound=sound},shared_before=before,verify={},reference=ref,
        rpm_source=rpm_source,casing=casing,ammo=ammo,sound=sounding or nil}
    if sounding and sounding.wanted then
        sounding.applied,sounding.after=sound_verify(world,t.entity,sound)
        sounding.package=sound_package
        sounding.shared=sounding.shared_before~=nil and sounding.shared_before==sound_shared(world,sound)
        result.verify.sound=sounding.applied
        result.verify.sound_shared=sounding.shared
    end
    -- The Gatling's aim recoil (optional).
    if spec.recoil then
        result.recoil=M.configure_recoil(world,t.entity,label,spec.recoil=='zero'and'zero'or'gatling')
        result.verify.recoil=result.recoil.applied
        writes=writes+(result.recoil.writes or 0)
    end
    -- Kill attribution (optional): the no-credit tag cleared on its own Tag mask (M.configure_credit).
    if spec.credit then
        result.credit=M.configure_credit(world,t.entity,label)
        result.verify.credit=result.credit.applied
        writes=writes+(result.credit.writes or 0)
    end
    -- The spread (optional): 'precise', 'mild' or 'gatling'.
    if spec.spread then
        result.spread=M.configure_spread(world,t.entity,label,spec.spread)
        result.verify.spread=result.spread.applied
        writes=writes+(result.spread.writes or 0)
    end
    -- 3. The magazine (optional): the pattern and/or the ammunition.
    if spec.pattern or(ammo and ammo.wanted)then
        local mwrites,mstatus,mreason=M.configure_magazine(world,t.entity,record,mag,{pattern=pattern,ammo=ammo and
            ammo.wanted and ammo},label)
        if spec.pattern then result.verify.pattern=mstatus=='APPLIED'end
        if ammo and ammo.wanted then
            ammo.read=M.ammo_state(world,t.entity,CHIN)
            ammo.applied=mstatus=='APPLIED'and ammo.read~=nil and ammo.read.from=='copy'
                and ammo.read.capacity==ammo.capacity and ammo.read.rounds==ammo.rounds and ammo.read.working==ammo.rounds
                and ammo.read.chambered~=0
            if not ammo.applied then ammo.reason=mreason or'the read-back differs'end
            result.verify.ammo=ammo.applied
        end
        writes=writes+(mwrites or 0)
    end
    local again=pelicans.weapon_config(world,t.entity)
    local now_copy=world.view.read(copy_at,CS.effectsEnd)
    result.writes=writes
    result.verify.projectile=again~=nil and again.copy~=nil and again.copy.projectileType==projectile
    result.verify.rpm=again~=nil and again.currentRpm==b.value(b.encode(rpm,'f32'),0,'f32')
    if slot_rpm then
        result.verify.rate_slot=now_copy~=nil and b.value(now_copy,PW.rpmSlots+4,'f32')==slot_rpm
    end
    if casing.wanted then
        casing.after=M.casing_state(world,t.entity,CHIN)
        casing.applied=casing.after~=nil and casing.after.from=='copy'and casing.after.particles==ref.casing.particles
            and casing.after.parameters==ref.casing.parameters and casing.after.cached==0
        result.verify.casing=casing.applied
    end
    result.verify.shared=gatling.shared_same(before,gatling.shared(world))
    -- The projectile rows (the standard round's and the one it fires), unchanged: only its own copy names the type.
    result.verify.rows=rows()==rows_before
    result.donor=donor
    local verified=true
    for _,v in pairs(result.verify)do if v~=true then verified=false end end
    result.verified=verified
    configured[t.entity]={pelican=pelican,spec=result.spec,holds=0,fire_entries=0,ammo=ammo and ammo.applied}
    log(('APPLIED (%s): chin turret %d: projectile %s, current RPM %s (%s)%s%s%s%s; %d writes; verified %s; spin-up: not '
        ..'available (a component its type does not have)'):format(label,t.entity,tostring(again and again.copy and
        again.copy.projectileType),tostring(again and again.currentRpm),rpm_source,casing.wanted and(', casing '
        ..tostring(casing.applied)..' ('..hex(casing.after and casing.after.particles)..')')or'',spec.pattern and(
        ', pattern '..tostring(result.verify.pattern))or'',ammo and(', ammunition '..tostring(ammo.applied)..(ammo.read
        and(' (capacity %s, rounds %s + chambered)'):format(tostring(ammo.read.capacity),tostring(ammo.read.rounds))or''))
        or'',sound_text(sounding),writes,tostring(verified)))
    return result
end

-- The game's magazine copy routine for one turret, then one guarded transaction on its own magazine copy, record and
-- entry: an ammunition pattern (opts.pattern, a list of rounds: the Gatling's or the Eagle Strafing Run's; the copy's
-- mode and entries, the record's mode and length, the values the
-- game derives from a magazine with that pattern) and/or the ammunition (opts.ammo = {capacity, rounds}: the copy's
-- capacity, and the rounds in both counts, the authoritative entry +4 and the record's working copy +0, as the game's
-- own fill does). Returns writes, status ('APPLIED' or a refusal), reason.
function M.configure_magazine(world,turret,record,mag,opts,label)
    local runtime=world.runtime
    runtime.native_magazine_copy(world.game+MC.rva,mag.manager,record)
    metrics.count('pelican_weapon.native_calls')
    mag=magazine_state(world,turret)
    local MG=TW.magazine
    local mcopy=mag and mag.copy and world.view.read(mag.copy,MC.stride)
    local mrec=mag and mag.record and world.view.read(mag.record,MG.stride)
    local ment=mag and mag.entry and world.view.read(mag.entry,AM.entryStride)
    local mcopy_owner=mag and mag.copy and pelicans.owner_of(world,mag.copy,MC.stride)
    local mrec_owner=mag and mag.record and pelicans.owner_of(world,mag.record,MG.stride)
    local ment_owner=mag and mag.entry and pelicans.owner_of(world,mag.entry,AM.entryStride)
    if not(mcopy and mrec and ment and mcopy_owner and mrec_owner and ment_owner)then
        log(('MAGAZINE REFUSED (%s): chin turret %d: no readable per-instance magazine copy after the call'):format(label,
            turret))
        return 0,'COPY_FAILED','no readable per-instance magazine copy after the call'
    end
    local identity={component='WeaponMagazine',component_type='native',unique_owner=true,owner_count=1}
    local plan={snapshots={{owner=mcopy_owner,offset=mag.copy-mcopy_owner.base,bytes=mcopy},
        {owner=mrec_owner,offset=mag.record-mrec_owner.base,bytes=mrec},
        {owner=ment_owner,offset=mag.entry-ment_owner.base,bytes=ment}},changes={}}
    local function change(name,owner,base,raw,at,desired)
        plan.changes[#plan.changes+1]={label='turret.'..turret..'.'..name,owner=owner,offset=base+at-owner.base,
            expected=raw:sub(at+1,at+#desired),desired=desired,before=raw:sub(at+1,at+#desired),already_desired=false,
            identity=identity,chain={}}
    end
    if opts.pattern then
        change('magazine_copy.mode',mcopy_owner,mag.copy,mcopy,MC.mode,u32(1))
        for k=1,#opts.pattern do
            change('magazine_copy.pattern'..k,mcopy_owner,mag.copy,mcopy,MC.pattern+(k-1)*4,u32(opts.pattern[k]))
        end
        change('magazine.mode',mrec_owner,mag.record,mrec,MG.pattern,u32(1))
        change('magazine.pattern_length',mrec_owner,mag.record,mrec,MG.patternLength,u32(#opts.pattern))
    end
    if opts.ammo then
        if b.u32(mcopy,AM.capacity)~=opts.ammo.before.capacity then
            return 0,'GUARD_REJECTED','the copy\'s capacity is not the chin turret\'s'
        end
        change('magazine_copy.capacity',mcopy_owner,mag.copy,mcopy,AM.capacity,u32(opts.ammo.capacity))
        change('magazine.rounds',ment_owner,mag.entry,ment,AM.entryRounds,u32(opts.ammo.rounds))
        change('magazine.working_rounds',mrec_owner,mag.record,mrec,MG.rounds,u32(opts.ammo.rounds))
    end
    local report=transaction.apply(runtime,plan)
    metrics.count('pelican_weapon.transactions')
    log(('MAGAZINE (%s): chin turret %d: %s'):format(label,turret,report.status=='APPLIED'and(('its own magazine record%s%s '
        ..'(%d writes)'):format(opts.pattern and(' holds the pattern '..table.concat(opts.pattern,','))or'',
        opts.ammo and((' holds %d rounds (capacity %d) and one chambered'):format(opts.ammo.rounds,opts.ammo.capacity))or'',
        report.writes))or('refused: '..tostring(report.reason))))
    if report.status~='APPLIED'then return 0,'GUARD_REJECTED',tostring(report.reason)end
    return report.writes,'APPLIED'
end

-- The chin turret's fire control, read-only: {stage, fireStart (P+0x180), aimStart (P+0x178), now, firing (stage 3)}.
function M.fire_state(world,turret)
    local rec=pelicans.behavior_of(world,turret)
    local now=pelicans.clock(world)
    if not(rec and now)then return nil end
    local P=BC.context
    local id=b.u32(rec.raw,0)
    return {behaviour=id,stage=b.u32(rec.raw,P),fireStart=u64(rec.raw,P+B645.fireStart),
        aimStart=u64(rec.raw,P+B645.aimStart),now=now,record=rec}
end

-- Continuous fire for one configured chin turret: when its AI has just entered its firing stage (3, its P+0x180 within
-- the native 0.5 s window), one guarded 8-byte write moves its own P+0x180 to now + M.HOLD_SECONDS, so the window does
-- not end; the AI still leaves the stage itself (no target, no line of fire). Returns 'held', 'idle' (nothing to do) or
-- nil, code, reason.
function M.hold_fire(world,turret,label)
    local c=configured[turret]
    if not c then return nil,'NOT_CONFIGURED','this chin turret was not configured here'end
    if not scheduler.in_update()then return nil,'NOT_GAME_THREAD','only inside the Runtime\'s own update'end
    local f=M.fire_state(world,turret)
    if not f then return nil,'GONE','the chin turret is gone'end
    if f.behaviour~=645 then return nil,'TURRET_UNEXPECTED','the entity no longer runs behaviour 645'end
    if f.stage~=B645.fireStage then return'idle'end
    if f.fireStart>f.now or f.now-f.fireStart>B645.fireWindow then return'idle'end   -- held already, or ending
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local P=BC.context
    local rec=f.record
    local owner=pelicans.owner_of(world,rec.address,BC.stride)
    if not owner then return nil,'NOT_PRIVATE','the Behavior record is not in private read-write memory'end
    local at=rec.address+P+B645.fireStart
    local old=rec.raw:sub(P+B645.fireStart+1,P+B645.fireStart+8)
    local desired=encode64(f.now+M.HOLD_SECONDS*US)
    local identity={component='Behavior',component_type='native',unique_owner=true,owner_count=1}
    local plan={snapshots={{owner=owner,offset=rec.address-owner.base,bytes=rec.raw:sub(1,P+4)},
            {owner=owner,offset=rec.address+P+B645.aimStart-owner.base,bytes=rec.raw:sub(P+B645.aimStart+1,
                P+B645.fireStart+8)}},
        changes={{label='turret.'..turret..'.fire_start',owner=owner,offset=at-owner.base,expected=old,desired=desired,
            before=old,already_desired=false,identity=identity,chain={}}}}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('pelican_weapon.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    c.holds=c.holds+1
    if c.holds<=10 then
        log(('HOLD (%s): chin turret %d entered its firing stage %.2f s ago: its fire window now ends in %d s (hold #%d)')
            :format(tostring(label),turret,(f.now-f.fireStart)/US,M.HOLD_SECONDS,c.holds))
    end
    return'held'
end

-- The chin turret's AI, read-only: {id (behaviour), stage, pending, transitioning, target (entity or nil), fireStart,
-- record (address), idAddress}.
local AI=G.ai
function M.ai_state(world,turret)
    local rec=pelicans.behavior_of(world,turret)
    if not rec then return nil end
    local raw=rec.raw
    local target=b.u32(raw,AI.target)
    local s={id=b.u32(raw,AI.id),stage=b.u32(raw,AI.stage),pending=b.value(raw,AI.pending,'i32'),
        transitioning=b.value(raw,AI.transitioning,'i32'),target=target~=0 and target or nil,
        fireStart=u64(raw,BC.context+B645.fireStart),record=rec.address,idAddress=rec.address+AI.id,raw=raw}
    return s
end
function M.ai_text(a)
    if not a then return'(gone)'end
    local names=a.id==AI.gatling and AI.stages213 or AI.stages645
    return ('behaviour %d, stage %d (%s), pending %d, transitioning %d, target %s'):format(a.id,a.stage,
        tostring(names[tostring(a.stage)]or'?'),a.pending,a.transitioning,tostring(a.target))
end

-- The Gatling AI for one Runtime Pelican's own chin turret, through the game's own SetBehaviour (0x843EA0) with the
-- Gatling Sentry's behaviour 213: it exits 645 through its own transition (stage 0), writes and replicates the id, and
-- starts 213 through its own transition at stage 1 (the start the game gives a new entity). Only while the turret is quiet:
-- behaviour 645 in stage 1 (idle) or stage 4 (its turret not active: the aim parked, the target cleared), nothing
-- pending, no transition running; in both its trigger is released (645 pulls it only on entering stage 3). The behaviour
-- field is read before and after; anything but exactly 213 after is a failure. Returns {turret, record, before, after,
-- stage_after} or nil, code, reason ('NOT_QUIET' when it is not quiet yet: try again later).
local SB=G.setBehaviour
local QUIET={[1]=true,[4]=true}
local switched={}
function M.switched(turret)return switched[turret]end
function M.switch_ai(world,pelican,label)
    label=tostring(label or'?')
    local function refuse(code,reason,quiet)
        if not quiet then log(('AI REFUSED (%s): Pelican %s: %s: %s'):format(label,tostring(pelican),code,reason))end
        return nil,code,reason
    end
    if not scheduler.in_update()then return refuse('NOT_GAME_THREAD','only inside the Runtime\'s own update')end
    for _,v in pairs(switched)do
        if v.pelican==pelican then
            return refuse('ALREADY_SWITCHED','this Pelican\'s chin turret already had the Gatling AI requested')
        end
    end
    local state,code,reason=guards(world,pelican,{'native_set_behaviour'})
    if not state then return refuse(code,reason)end
    if not world.view.proves(world.game+SB.rva,SB.prologue)then
        return refuse('UNSUPPORTED_BUILD','the game\'s SetBehaviour changed')
    end
    for name,expected in pairs({entry645=645,entry213=213})do
        if not world.view.proves(world.game+AI.table+4*(expected-1),AI[name])then
            return refuse('UNSUPPORTED_BUILD','the behaviour jump table changed')
        end
    end
    local manager=world.view.pointer(world.game+SB.manager)
    if not manager or manager==0 then return refuse('UNAVAILABLE','the Behavior manager is unreadable')end
    local t=state.turret.entity
    local a=M.ai_state(world,t)
    if not a then return refuse('UNAVAILABLE','the chin turret\'s Behavior record is unreadable')end
    if a.id~=AI.chin then return refuse('TURRET_UNEXPECTED','the chin turret\'s behaviour field reads '..a.id..', not 645')end
    if not(QUIET[a.stage]and a.pending==-1 and a.transitioning==-1)then
        return refuse('NOT_QUIET',('the chin turret is not quiet (stage 1 or 4, nothing pending): %s'):format(
            M.ai_text(a)),true)
    end
    log(('AI BEFORE (%s): Pelican %d, chin turret %d: Behavior record 0x%X; behaviour BEFORE = %d (the field at +0x%X, '
        ..'address 0x%X); %s; requested behaviour 213 through the game\'s SetBehaviour (game+%X)'):format(label,pelican,t,
        a.record,a.id,AI.id,a.idAddress,M.ai_text(a),SB.rva))
    metrics.count('pelican_weapon.native_calls')
    world.runtime.native_set_behaviour(world.game+SB.rva,manager,t,AI.gatling)
    local after=M.ai_state(world,t)
    switched[t]={pelican=pelican,at=pelicans.clock(world),after=after and after.id}
    if not(after and after.id==AI.gatling)then
        log(('AI SWITCH FAILED (%s): chin turret %d: behaviour AFTER = %s (read back), not the requested 213'):format(label,
            t,tostring(after and after.id)))
        return refuse('NOT_APPLIED','behaviour AFTER = '..tostring(after and after.id)..', not 213')
    end
    log(('AI SWITCHED (%s): chin turret %d: behaviour BEFORE = %d, behaviour AFTER = %d (read back from the field); %s')
        :format(label,t,a.id,after.id,M.ai_text(after)))
    return {turret=t,record=a.record,before=a.id,after=after.id,stage_after=after.stage}
end

-- The chin turret's OWN AI back (r44). The Gatling AI must never see the chin turret die: 213 has a death stage (11;
-- 0x495BC0) that the Behavior update enters when the entity's HealthComponent life reaches 2 (0x8433F1..0x84349B,
-- 0x927050), and its entry (0x285F2A) plays ability 0x9DF on it, which looks the entity up in a manager
-- (game+0x3326570, 0x1121140 -> 0x8ABB20) with no not-found path: a chin turret is not in it, so the game crashed (two
-- live host crashes, 2026-10-07: a Shredder Silo blast killing a Pelican's chin turret). 645 has no death stage. Through
-- the same SetBehaviour: 213 leaves through its own transition to stage 0, which runs no stage entry (0x285894: stage
-- 0 - 1 > 11), releasing the trigger if it was firing (0x285861); 645 enters at its stage 1. Only a turret this
-- machine switched, still 213 and not in its death stage, nothing transitioning. Read back: exactly 645 after.
-- Returns {turret, before, after} or nil, code, reason.
function M.restore_ai(world,turret,label)
    label=tostring(label or'?')
    local function refuse(code,reason)
        log(('AI RESTORE REFUSED (%s): chin turret %s: %s: %s'):format(label,tostring(turret),code,reason))
        return nil,code,reason
    end
    if not switched[turret]then return refuse('NOT_SWITCHED','the Runtime did not give this turret the Gatling AI')end
    if not scheduler.in_update()then return refuse('NOT_GAME_THREAD','only inside the Runtime\'s own update')end
    if not world.runtime.native_set_behaviour then
        return refuse('UNAVAILABLE','this Runtime adapter cannot call game functions')
    end
    if not world.view.proves(world.game+SB.rva,SB.prologue)then
        return refuse('UNSUPPORTED_BUILD','the game\'s SetBehaviour changed')
    end
    for name,expected in pairs({entry645=645,entry213=213})do
        if not world.view.proves(world.game+AI.table+4*(expected-1),AI[name])then
            return refuse('UNSUPPORTED_BUILD','the behaviour jump table changed')
        end
    end
    local manager=world.view.pointer(world.game+SB.manager)
    if not manager or manager==0 then return refuse('UNAVAILABLE','the Behavior manager is unreadable')end
    local a=M.ai_state(world,turret)
    if not a then return refuse('UNAVAILABLE','the chin turret\'s Behavior record is unreadable')end
    if a.id~=AI.gatling then return refuse('TURRET_UNEXPECTED','the behaviour field reads '..a.id..', not 213')end
    if a.stage==M.DEATH_STAGE then return refuse('DEAD','the Gatling AI is in its death stage already')end
    if a.transitioning~=-1 then return refuse('NOT_QUIET','a transition is running: '..M.ai_text(a))end
    metrics.count('pelican_weapon.native_calls')
    world.runtime.native_set_behaviour(world.game+SB.rva,manager,turret,AI.chin)
    local after=M.ai_state(world,turret)
    if not(after and after.id==AI.chin)then
        log(('AI RESTORE FAILED (%s): chin turret %d: behaviour AFTER = %s (read back), not 645'):format(label,turret,
            tostring(after and after.id)))
        return nil,'NOT_APPLIED','behaviour AFTER = '..tostring(after and after.id)
    end
    switched[turret]=nil
    log(('AI RESTORED (%s): chin turret %d: behaviour BEFORE = %d, behaviour AFTER = %d (its own AI: no death stage); %s')
        :format(label,turret,a.id,after.id,M.ai_text(after)))
    return {turret=turret,before=a.id,after=after.id}
end
M.DEATH_STAGE=11

-- THE CHIN TURRET'S OWN INVINCIBLE BYTE (r44, defence in depth; docs/research/chin-turret-invulnerability-F5FEE03DCFDB.md).
-- The turret's HealthComponent ext entry (manager game+0x3326688, ext array +0x1060, 0x1C bytes per entity) holds the
-- game's per-entity `invincible` byte at +0x18 (network field 0x95417727; the game sets it per entity itself, from some
-- AIs and seats). ApplyDamage returns before any health, state, life or kill work when it is set (0x92388C), and the
-- health update skips the entity, so its replicated state never becomes its life (0x920486): the death the Gatling AI
-- cannot survive on a chin turret never comes. One guarded byte 0 -> 1 on the turret's own entry only (never the game's
-- setter 0x91DE20: it would also heal it and publish the field); both gates are re-proven on the real code first.
-- Only on the Runtime Pelican's own chin turret (its type), alive (life 0, state 0), the byte 0 (a byte the game set is
-- never touched). Cleared only when this machine set it, the Gatling AI is off it and it is alive; a turret that died
-- anyway (a remote death report: state 2) keeps it (clearing it would run the death). Not live-tested.
do
local HN=require('hd2runtime/domains/event_natives').health
local INV={byte=0x18,state=0x0C,gates={{rva=0x92388C,bytes='44386C08180F859A240000'},
    {rva=0x920486,bytes='807C1F18000F857B0B0000'}}}
M.INVINCIBLE=INV
local invincible={}      -- turret -> true: this machine set its byte
function M.invincible_state(world,turret)
    local st=world_module.entity_state(world,turret)
    if not(st and st.header and st.header.ext)then return nil end
    local entry=st.header.ext+st.index*HN.extStride
    local raw=world.view.read(entry,HN.extStride)
    if not raw then return nil end
    return {at=entry+INV.byte,byte=raw:byte(INV.byte+1),state=b.u32(raw,INV.state),life=st.life,health=st.health,
        type=st.descriptor.type,owned=st.descriptor.owned,index=st.index,mine=invincible[turret]==true}
end
local function inv_text(s)
    return s and('invincible %d, state %d, life %d, health %d'):format(s.byte,s.state,s.life,s.health)or'(gone)'
end
local function inv_write(world,turret,s,from,to,label)
    local owner=pelicans.owner_of(world,s.at,1)
    if not owner then return nil,'UNAVAILABLE','its health entry is not in private read-write memory'end
    local identity={component='HealthComponent',component_type='native',unique_owner=true,owner_count=1}
    local plan={snapshots={{owner=owner,offset=s.at-owner.base,bytes=string.char(from)}},
        changes={{label='turret.'..turret..'.invincible',owner=owner,offset=s.at-owner.base,expected=string.char(from),
            desired=string.char(to),before=string.char(from),already_desired=false,identity=identity,chain={}}}}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('pelican_weapon.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local after=M.invincible_state(world,turret)
    local exact=after~=nil and after.at==s.at and after.byte==to and after.state==s.state and after.life==s.life
        and after.health==s.health
    return {before=s,after=after,verified=exact,writes=report.writes}
end
function M.make_invincible(world,turret,label)
    label=tostring(label or'?')
    local function refuse(code,reason)
        log(('INVINCIBLE REFUSED (%s): chin turret %s: %s: %s'):format(label,tostring(turret),code,reason))
        return nil,code,reason
    end
    if invincible[turret]then return {already=true}end
    if not scheduler.in_update()then return refuse('NOT_GAME_THREAD','only inside the Runtime\'s own update')end
    for _,g in ipairs(INV.gates)do
        if not world.view.proves(world.game+g.rva,g.bytes)then
            return refuse('UNSUPPORTED_BUILD',('the invincible check changed (game+%X)'):format(g.rva))
        end
    end
    local s=M.invincible_state(world,turret)
    if not s then return refuse('UNAVAILABLE','its health entry is unreadable')end
    if s.type~=CHIN then return refuse('TURRET_UNEXPECTED','its type is '..tostring(s.type)..', not the chin turret')end
    if s.byte~=0 then return refuse('GAME_SET','the game set its invincible byte ('..s.byte..'): left alone')end
    if s.life~=0 or s.state~=0 then return refuse('NOT_ALIVE',inv_text(s))end
    local r,code,reason=inv_write(world,turret,s,0,1,label)
    if not r then return refuse(code,reason)end
    if not r.verified then
        log(('INVINCIBLE NOT VERIFIED (%s): chin turret %d: %s after the write'):format(label,turret,inv_text(r.after)))
        return nil,'NOT_VERIFIED',inv_text(r.after)
    end
    invincible[turret]=true
    log(('INVINCIBLE (%s): chin turret %d: its own health entry\'s invincible byte 0 -> 1 (no damage, no death sync; '
        ..'%s machine\'s copy); %d write; read back: %s'):format(label,turret,s.owned and'this owning'or'this',r.writes,
        inv_text(r.after)))
    return r
end
-- Every step while the Gatling AI is on it: true while it is still invincible and alive here; false and why otherwise.
function M.invincible_check(world,turret)
    if not invincible[turret]then return false,'never made invincible here'end
    local s=M.invincible_state(world,turret)
    if not s then return false,'its health entry is gone'end
    if s.byte~=1 then return false,'its invincible byte was cleared ('..inv_text(s)..')'end
    if s.state>=2 or s.life>=2 then return false,'it is reported dead ('..inv_text(s)..')'end
    return true
end
function M.release_invincible(world,turret,label)
    label=tostring(label or'?')
    if not invincible[turret]then return nil,'NOT_MINE'end
    local s=M.invincible_state(world,turret)
    if not s then invincible[turret]=nil;return {gone=true}end
    if switched[turret]then return nil,'STILL_SWITCHED'end
    if not scheduler.in_update()then return nil,'NOT_GAME_THREAD'end
    if s.byte~=1 then invincible[turret]=nil;return {cleared_by_game=true}end
    if s.state>=2 or s.life>=2 then
        invincible[turret]=nil
        log(('INVINCIBLE KEPT (%s): chin turret %d: %s: clearing it would run its death; it goes with the entity')
            :format(label,turret,inv_text(s)))
        return {kept=true}
    end
    local r,code,reason=inv_write(world,turret,s,1,0,label)
    if not r then
        log(('INVINCIBLE NOT CLEARED (%s): chin turret %d: %s: %s'):format(label,turret,tostring(code),tostring(reason)))
        return nil,code,reason
    end
    invincible[turret]=nil
    log(('INVINCIBLE CLEARED (%s): chin turret %d: 1 -> 0 (its own AI back); read back: %s'):format(label,turret,
        inv_text(r.after)))
    return r
end
function M.reset_invincible_for_tests()invincible={}end
end
-- Whether a turret lives: its HealthComponent record's life below 2 (what the Behavior update's death check reads,
-- 0x9270F2). nil when it has no readable health record (gone).
function M.alive(world,turret)
    local st=world_module.entity_state(world,turret)
    if not st then return nil end
    return st.life<2
end

----------------------------------------------------------------------------------------------------- the aim --
-- Where the bullets go (research "aim", docs section 20b), read-only: the targeting system's aim point T (the target's
-- aim node nearest the turret), the weapon's own aim after the turret (WeaponData +0: the turret's achieved pointing,
-- which the shot flies toward from the muzzle), the muzzle position and its velocity, and the aim recoil angles of its
-- wielder slot. M.aim_state(world, turret): {target, point (T), aim, muzzle, velocity, recoil = {x, y} (degrees)} or nil.
local function vec3(raw,o)return {x=f32(raw,o),y=f32(raw,o+4),z=f32(raw,o+8)}end
local function record_of(world,layout,entity,size,base)
    local mgr=world.view.pointer(world.game+layout.global)
    local index=mgr and mgr~=0 and pelicans.index_of(world,mgr,map_at(layout.map),entity)
    local records=index and world.view.pointer(mgr+layout.records)
    if not(records and records~=0)then return nil end
    local at=records+index*layout.stride+(base or 0)
    return world.view.read(at,size),at
end
function M.aim_state(world,turret)
    local WD,TG,WL=AIM.weaponData,AIM.targeting,AIM.wielder
    local wd,wd_at=record_of(world,WD,turret,WD.muzzleVelocity+12)
    local tg=record_of(world,TG,turret,TG.point+12)
    local wl=record_of(world,WL,turret,8,WL.recoil)
    if not(wd and tg)then return nil end
    local target=b.u32(tg,TG.target)
    return {target=target~=0 and target or nil,point=vec3(tg,TG.point),aim=vec3(wd,WD.aim),muzzle=vec3(wd,WD.muzzle),
        velocity=vec3(wd,WD.muzzleVelocity),recoil=wl and{x=math.deg(f32(wl,0)or 0),y=math.deg(f32(wl,4)or 0)}or nil,
        weapon_data=wd_at}
end
-- The miss at the target (metres and degrees), from an aim state: where the shot (muzzle -> its aim) crosses the plane
-- through T across the line of sight; the part the AI's own-motion lead explains (the muzzle's velocity across the line of fire over
-- the projectile's speed: the bullets do not get that velocity); and, given the target's root, how far T is above it.
-- speed: the round's speed (m/s; default the standard round's).
function M.aim_error(s,root,speed)
    if not s then return nil end
    local function sub3(p,q)return {x=p.x-q.x,y=p.y-q.y,z=p.z-q.z}end
    local function len(v)return math.sqrt(v.x*v.x+v.y*v.y+v.z*v.z)end
    local line=sub3(s.point,s.muzzle)
    local dist=len(line)
    local shot=sub3(s.aim,s.muzzle)
    local sl=len(shot)
    if dist<1 or sl<1e-3 then return nil end
    local u={x=line.x/dist,y=line.y/dist,z=line.z/dist}
    -- Where the shot crosses the plane through T across the line of sight.
    local cos=(shot.x*u.x+shot.y*u.y+shot.z*u.z)/sl
    if cos<0.2 then return nil end
    local t=dist/cos
    local hit={x=s.muzzle.x+shot.x/sl*t,y=s.muzzle.y+shot.y/sl*t,z=s.muzzle.z+shot.z/sl*t}
    local miss=sub3(hit,s.point)
    local q=s.velocity
    local along=q.x*u.x+q.y*u.y+q.z*u.z
    local across={x=q.x-along*u.x,y=q.y-along*u.y,z=q.z-along*u.z}
    speed=speed or AIM.projectileSpeed
    return {distance=dist,vertical=miss.z,horizontal=math.sqrt(miss.x*miss.x+miss.y*miss.y),
        vertical_deg=math.deg(math.atan2(miss.z,dist)),lead_vertical=-dist*across.z/speed,
        lead=dist*len(across)/speed,muzzle_speed=len(q),node_height=root and(s.point.z-root.z)or nil}
end

--------------------------------------------------------------------------------------------- the aim point, lowered --
-- One turret's aim point, lowered (research/custom-payloads pelicanAim; docs/research/pelican-cas-F5FEE03DCFDB.md
-- section 29; build/test-artifacts/aim-research/aim-point.md). The game aims a turret at each target type's single aim
-- node (T): for a Terminid about 1.2 to 1.5 m above its feet, so the Pelican's rounds pass over it (live r13: the shot
-- 0.44 m above T, T 1.52 m above the root). The turret's OWN targeting record carries the game's aim override: while t
-- (+0x50) >= 0 the targeting update replaces the target-derived point by its curve (mode 2 at +0x60: linear from A
-- +0x20 to B +0x2C; +0x6C = 0: t stays) before T = Q (0x6BCF27), so the lead, the wielder, WeaponData +0, the solve and
-- the shot follow the written point in the same pass. Its only writers are creation, init (t = -1) and behaviour 50's /
-- the action dispatcher's setup, stop and speed: behaviour 213 never reaches them. The network bits (+0x10) must be 0
-- (else the full path skips the override). Nothing of it is replicated: every machine computes its own T, so this is
-- the host's turret only.
--   * M.aim_lower(world, turret, point, label): A = B = point (and, while the override is off, mode 2, no advance, t = 1)
--     in one guarded transaction on that record; read back. Only on a chin turret this Runtime configured, on the host,
--     with the override off or the Runtime's own (mode 2, t = 1, no advance): another user of it is never overridden.
--   * M.aim_release(world, turret, label): t = -1 (the game's own "off"), only over the Runtime's own override.
--   * M.aim_override_state(world, turret): {t, mode, advance, a, b, point (T), bits, at} read-only.
local PA=require('hd2runtime/domains/custom_payloads').pelicanAim
local aim_proven
local function aim_prove(world)
    if aim_proven then return true end
    for _,pin in ipairs(PA.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,('game+%X changed (%s)'):format(pin.rva,pin.label)
        end
    end
    aim_proven=true
    return true
end
local function aim_record(world,turret)
    local mgr=world.view.pointer(world.game+PA.global)
    local index=mgr and mgr~=0 and pelicans.index_of(world,mgr,map_at(PA.map),turret)
    local records=index and world.view.pointer(mgr+PA.records)
    local network=index and world.view.pointer(mgr+PA.network)
    if not(records and records~=0 and network and network~=0)then return nil end
    local at=records+index*PA.stride
    local raw=world.view.read(at,PA.stride)
    local bits=world.view.u32(network+index*PA.networkStride+PA.networkBits)
    if not(raw and bits)then return nil end
    return raw,at,bits
end
function M.aim_override_state(world,turret)
    local raw,at,bits=aim_record(world,turret)
    if not raw then return nil end
    return {t=f32(raw,PA.t),mode=b.u32(raw,PA.mode),advance=raw:byte(PA.advance+1),a=vec3(raw,PA.curveA),
        b=vec3(raw,PA.curveB),point=vec3(raw,PA.point),target=b.u32(raw,PA.target),bits=bits,at=at}
end
-- The Runtime's own override: mode 2, t exactly 1, no advance.
local function aim_ours(raw)
    return b.u32(raw,PA.mode)==PA.linearMode and raw:sub(PA.t+1,PA.t+4)==b.encode(PA.on,'f32')
        and raw:byte(PA.advance+1)==0
end
local function aim_guards(world,turret)
    if not scheduler.in_update()then return nil,'NOT_GAME_THREAD','only inside the Runtime\'s own update'end
    local ok,why=aim_prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',why end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','in a mission only'end
    if game.host~=true then return nil,'NOT_HOST','the host\'s turret only (its aim point is computed on each machine)'end
    if not configured[turret]then return nil,'NOT_CONFIGURED','not a chin turret this Runtime configured'end
    local raw,at,bits=aim_record(world,turret)
    if not raw then return nil,'UNAVAILABLE','its targeting record is unreadable'end
    local owner=pelicans.owner_of(world,at,PA.stride)
    if not owner then return nil,'NOT_PRIVATE','its targeting record is not in private read-write memory'end
    return raw,at,bits,owner
end
local function aim_plan(owner,at,raw,turret,writes)
    local identity={component='Targeting',component_type='native',unique_owner=true,owner_count=1}
    local plan={snapshots={{owner=owner,offset=at-owner.base,bytes=raw}},changes={}}
    for _,w in ipairs(writes)do
        local from=raw:sub(w.at+1,w.at+#w.bytes)
        if from~=w.bytes then
            plan.changes[#plan.changes+1]={label='turret.'..turret..'.targeting.'..w.name,owner=owner,
                offset=at+w.at-owner.base,expected=from,desired=w.bytes,before=from,already_desired=false,
                identity=identity,chain={}}
        end
    end
    return plan
end
function M.aim_lower(world,turret,point,label)
    if not(type(point)=='table'and point.x==point.x and point.y==point.y and point.z==point.z
            and math.abs(point.x)<1e6 and math.abs(point.y)<1e6 and math.abs(point.z)<1e6)then
        return nil,'INVALID','the point must be finite world coordinates'
    end
    local raw,at,bits,owner=aim_guards(world,turret)
    if not raw then return nil,at,bits end
    if bits~=0 then return nil,'NETWORK_BITS','its targeting holds a scripted aim (network bits '..bits..')'end
    local off=f32(raw,PA.t)<0
    if not(off or aim_ours(raw))then
        return nil,'OVERRIDE_IN_USE',('its aim override is in use (mode %d, t %s)'):format(b.u32(raw,PA.mode),
            tostring(f32(raw,PA.t)))
    end
    local xyz=b.encode(point.x,'f32')..b.encode(point.y,'f32')..b.encode(point.z,'f32')
    local writes={{name='curve_a',at=PA.curveA,bytes=xyz},{name='curve_b',at=PA.curveB,bytes=xyz}}
    if off then
        writes[#writes+1]={name='mode',at=PA.mode,bytes=u32(PA.linearMode)}
        writes[#writes+1]={name='advance',at=PA.advance,bytes=string.char(0)}
        writes[#writes+1]={name='t',at=PA.t,bytes=b.encode(PA.on,'f32')}   -- last: the switch
    end
    local plan=aim_plan(owner,at,raw,turret,writes)
    if#plan.changes==0 then return {writes=0,first=false,applied=true}end
    local report=transaction.apply(world.runtime,plan)
    metrics.count('pelican_weapon.aim_transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local again=world.view.read(at,PA.stride)
    local applied=again~=nil and again:sub(PA.curveB+1,PA.curveB+12)==xyz and again:sub(PA.curveA+1,PA.curveA+12)==xyz
        and aim_ours(again)
    return {writes=report.writes,first=off,applied=applied}
end
function M.aim_release(world,turret,label)
    local raw,at,bits,owner=aim_guards(world,turret)
    if not raw then return nil,at,bits end
    if f32(raw,PA.t)<0 then return {writes=0,applied=true}end
    if not aim_ours(raw)then return nil,'OVERRIDE_IN_USE','its aim override is not the Runtime\'s'end
    local plan=aim_plan(owner,at,raw,turret,{{name='t',at=PA.t,bytes=b.encode(PA.off,'f32')}})
    local report=transaction.apply(world.runtime,plan)
    metrics.count('pelican_weapon.aim_transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    return {writes=report.writes,applied=world.view.read(at+PA.t,4)==b.encode(PA.off,'f32')}
end

-- The aim recoil on this turret's own WeaponData instance record (recoil block B, the one the aim takes: research
-- "aim"; the chin turret's kicks 10 up and 2.5 sideways a shot, the Gatling Sentry's 3 and 0). mode 'gatling' (default):
-- the frozen Gatling block B (M.FROZEN); mode 'zero': 0 sideways and 0 up a shot, the rest of the block its own, in
-- BOTH blocks: block A too (instance +0x1C), which the aim update applies along the barrel's own up axis (chin: 2.5 / 10,
-- about 0.87 deg up at 1600 RPM; build/test-artifacts/aim-research/recoil-bias.md). With 'gatling' block A is left as
-- it is. Only while each written block is still its own type's. Returns {applied, reason, before, after, mode, a =
-- {before, after, applied}} (read back).
function M.configure_recoil(world,turret,label,mode)
    mode=mode=='zero'and'zero'or'gatling'
    local WD,TY=AIM.weaponData,AIM.weaponData.types
    local out={applied=false,mode=mode}
    local inst,at=record_of(world,WD,turret,WD.recoilB+WD.recoilSize)
    local chin=gatling.type_record(world,TY,CHIN)
    if not(inst and chin)then out.reason='its WeaponData is unreadable';return out end
    local mine=inst:sub(WD.recoilB+1,WD.recoilB+WD.recoilSize)
    local want=M.FROZEN.recoil_b
    if mode=='zero'then want=b.encode(0,'f32')..b.encode(0,'f32')..mine:sub(9)end
    out.before={x=f32(mine,0),y=f32(mine,4)}
    if mine~=chin:sub(TY.recoilB+1,TY.recoilB+WD.recoilSize)then out.reason='its recoil is not its type\'s';return out end
    -- Block A (mode 'zero' only, best effort): while it is still its own type's, 0 sideways and 0 up, the rest its own;
    -- otherwise it is left and reported (block B is written either way).
    local mine_a,want_a
    if mode=='zero'then
        mine_a=inst:sub(WD.recoilA+1,WD.recoilA+WD.recoilSize)
        out.a={before={x=f32(mine_a,0),y=f32(mine_a,4)},applied=false}
        if mine_a==chin:sub(TY.recoilA+1,TY.recoilA+WD.recoilSize)then
            want_a=b.encode(0,'f32')..b.encode(0,'f32')..mine_a:sub(9)
        else
            out.a.reason='its recoil block A is not its type\'s'
        end
    end
    local owner=pelicans.owner_of(world,at,WD.stride)
    if not owner then out.reason='its WeaponData is not in private read-write memory';return out end
    local identity={component='WeaponData',component_type='native',unique_owner=true,owner_count=1}
    local plan={snapshots={{owner=owner,offset=at+WD.recoilB-owner.base,bytes=mine}},changes={}}
    local function block(name,base,from,to)
        for k=0,WD.recoilSize-4,4 do
            if from:sub(k+1,k+4)~=to:sub(k+1,k+4)then
                plan.changes[#plan.changes+1]={label='turret.'..turret..'.'..name..'.'..(k/4),owner=owner,
                    offset=at+base+k-owner.base,expected=from:sub(k+1,k+4),desired=to:sub(k+1,k+4),
                    before=from:sub(k+1,k+4),already_desired=false,identity=identity,chain={}}
            end
        end
    end
    block('recoil_b',WD.recoilB,mine,want)
    if want_a then
        plan.snapshots[#plan.snapshots+1]={owner=owner,offset=at+WD.recoilA-owner.base,bytes=mine_a}
        block('recoil_a',WD.recoilA,mine_a,want_a)
    end
    if#plan.changes==0 then
        out.after,out.applied,out.writes=out.before,true,0
        if want_a then out.a.after,out.a.applied=out.a.before,true end
        return out
    end
    local report=transaction.apply(world.runtime,plan)
    metrics.count('pelican_weapon.transactions')
    if report.status~='APPLIED'then out.reason='refused: '..tostring(report.reason);return out end
    local again=world.view.read(at+WD.recoilB,WD.recoilSize)
    out.after=again and{x=f32(again,0),y=f32(again,4)}
    out.applied=again==want
    if want_a then
        local again_a=world.view.read(at+WD.recoilA,WD.recoilSize)
        out.a.after=again_a and{x=f32(again_a,0),y=f32(again_a,4)}
        out.a.applied=again_a==want_a
    end
    out.writes=report.writes
    log(('RECOIL (%s): chin turret %d: its own aim recoil (WeaponData block B) %s, %s -> %s %s, %s%s; %d writes; read '
        ..'back %s'):format(tostring(label),turret,tostring(out.before.x),tostring(out.before.y),mode=='zero'and'ZERO:'
        or'the frozen Gatling Sentry\'s',tostring(f32(want,0)),tostring(f32(want,4)),out.a and(want_a and(('; block A %s, '
        ..'%s -> ZERO: 0, 0 (read back %s)'):format(tostring(out.a.before.x),tostring(out.a.before.y),
        tostring(out.a.applied)))or('; block A left: '..tostring(out.a.reason)))or'',report.writes,tostring(out.applied)))
    return out
end

-------------------------------------------------------------------------------------------------- the spread --
-- The shot's spread (research "spread", docs section 22): every shot turns by two random angles from the weapon's OWN
-- WeaponData instance record: +0x58 (horizontal) and +0x5C (vertical), full widths in milliradians (a shot turns by up
-- to half of each, each way), and the distribution word +0x60. The instance took its type's spread times its own
-- multipliers (+0x3E0, +0x3E8) once, at creation; only an ammo-type switch rebuilds it. M.spread_state(world, entity):
-- {x, y, word, multipliers = {x, y}, at} or nil; M.type_spread(world, resource): a type's {x, y, word} or nil.
local SPD=D.spread
M.SPREAD_MODES={precise=true,mild=true,gatling=true}
function M.spread_state(world,entity)
    local raw,at=record_of(world,AIM.weaponData,entity,SPD.multipliers[2]+4)
    if not raw then return nil end
    return {x=f32(raw,SPD.instance),y=f32(raw,SPD.instance+4),word=b.u32(raw,SPD.word),
        multipliers={x=f32(raw,SPD.multipliers[1]),y=f32(raw,SPD.multipliers[2])},at=at,raw=raw}
end
function M.type_spread(world,resource)
    local raw=gatling.type_record(world,AIM.weaponData.types,resource)
    return raw and{x=f32(raw,SPD.type),y=f32(raw,SPD.type+4),word=b.u32(raw,SPD.typeWord)}
end
-- M.configure_spread(world, turret, label, mode): the chin turret's own spread, on its own WeaponData instance record
-- only (one guarded transaction, read back): 'precise' = its current spread (nothing written); 'mild' = halfway
-- between its current spread and the frozen Gatling Sentry's (M.FROZEN), its own distribution word;
-- 'gatling' = the frozen Gatling Sentry's exactly (both widths and the word); a number (0 < mrad <= M.SPREAD_MAX) = that full
-- width both ways, its own distribution word (nothing written when it is already its spread). Only while its spread is
-- still its type's times its own multipliers. Returns {mode, name, applied, reason, before, want, after, chin (its
-- type's), gatling, writes}.
M.SPREAD_MAX=100
M.RATE_FACTORS={[1]=true,[1.5]=true,[2]=true}
function M.configure_spread(world,turret,label,mode)
    local width=type(mode)=='number'and mode==mode and mode>0 and mode<=M.SPREAD_MAX and mode or nil
    if type(mode)=='number'and not width then
        return {mode=mode,name=tostring(mode)..' mrad',applied=false,writes=0,
            reason=('INVALID: a width must be more than 0 and at most %d mrad'):format(M.SPREAD_MAX)}
    end
    if not width then mode=M.SPREAD_MODES[mode]and mode or'mild'end
    local name=width and('%g mrad'):format(width)or mode:upper()
    local out={mode=width or mode,name=name,applied=false,writes=0}
    if not scheduler.in_update()then out.reason='NOT_GAME_THREAD: only inside the Runtime\'s update';return out end
    local s=M.spread_state(world,turret)
    local chin,gat=M.type_spread(world,CHIN),M.FROZEN.spread
    out.before,out.chin,out.gatling=s,chin,gat
    if not(s and chin)then out.reason='its WeaponData or its type record is unreadable';return out end
    local function single(v)return b.value(b.encode(v,'f32'),0,'f32')end
    if s.word~=chin.word or s.x~=single(chin.x*s.multipliers.x)or s.y~=single(chin.y*s.multipliers.y)then
        out.reason='its spread is not its type\'s';return out
    end
    local want={x=s.x,y=s.y,word=s.word}
    if mode=='mild'then want={x=single((s.x+gat.x)/2),y=single((s.y+gat.y)/2),word=s.word}
    elseif mode=='gatling'then want={x=gat.x,y=gat.y,word=gat.word}end
    if width then want={x=single(width),y=single(width),word=s.word}end
    out.want=want
    local writes=0
    if not(want.x==s.x and want.y==s.y and want.word==s.word)then
        local owner=pelicans.owner_of(world,s.at,AIM.weaponData.stride)
        if not owner then out.reason='its WeaponData is not in private read-write memory';return out end
        local identity={component='WeaponData',component_type='native',unique_owner=true,owner_count=1}
        local current=s.raw:sub(SPD.instance+1,SPD.word+4)
        local desired=b.encode(want.x,'f32')..b.encode(want.y,'f32')..u32(want.word)
        local plan={snapshots={{owner=owner,offset=s.at+SPD.instance-owner.base,bytes=current}},changes={}}
        for k=0,#current-4,4 do
            plan.changes[#plan.changes+1]={label='turret.'..turret..'.spread.'..(k/4),owner=owner,
                offset=s.at+SPD.instance+k-owner.base,expected=current:sub(k+1,k+4),desired=desired:sub(k+1,k+4),
                before=current:sub(k+1,k+4),already_desired=false,identity=identity,chain={}}
        end
        local report=transaction.apply(world.runtime,plan)
        metrics.count('pelican_weapon.transactions')
        if report.status~='APPLIED'then out.reason='refused: '..tostring(report.reason);return out end
        writes=report.writes
    end
    local again=M.spread_state(world,turret)
    out.after,out.writes=again,writes
    out.applied=again~=nil and again.x==want.x and again.y==want.y and again.word==want.word
    log(('SPREAD (%s): chin turret %d: its own spread (WeaponData +0x58) %s, %s mrad -> %s: %s, %s mrad (the frozen '
        ..'Gatling Sentry\'s %s, %s); distribution word %d -> %d; %d writes; read back %s'):format(
        tostring(label),turret,tostring(s.x),tostring(s.y),name,tostring(again and again.x),
        tostring(again and again.y),tostring(gat.x),tostring(gat.y),s.word,again and again.word or-1,writes,
        tostring(out.applied)))
    return out
end

-------------------------------------------------------------------------------------------------- the refill --
-- M.refill_step(world, turret, label), every Runtime update for a turret configured with the safe-maximum ammunition:
-- when its rounds (the authoritative count, entry +4) fall below M.REFILL_BELOW, one guarded transaction writes both
-- counts back to M.AMMO_MAX, the working count (record +0) first and the authoritative one (entry +4) last, the order
-- of the game's own refill. Only its own magazine (its copy's capacity is M.AMMO_MAX); no reload, no chamber, no spare
-- magazine, no shared definition is touched. Not while its magazine is dry (no chambered round: the game's own refills
-- leave that to a reload); not more often than every M.REFILL_SPACING s. A refill a shot overwrites in the same frame is
-- retried at the next poll. Returns nil (nothing to do) or {kind = 'refilled', old, new} / {kind = 'refused', code,
-- reason}.
local refills={}
function M.refill_step(world,turret,label)
    local c=configured[turret]
    if not(c and c.ammo)then return nil end
    if not scheduler.in_update()then return {kind='refused',code='NOT_GAME_THREAD',reason='only inside the Runtime\'s update'}end
    local a=M.ammo_state(world,turret,CHIN)
    local now=pelicans.clock(world)
    if not(a and now)then return nil end
    if a.rounds>=M.REFILL_BELOW then return nil end
    local last=refills[turret]
    if last and now-last<M.REFILL_SPACING*US then return nil end
    refills[turret]=now
    if a.from~='copy'or a.capacity~=M.AMMO_MAX then
        return {kind='refused',code='TURRET_UNEXPECTED',reason='its own magazine is not the safe maximum'}
    end
    if a.chambered==0 or a.chamber_empty~=0 then
        return {kind='refused',code='DRY',reason='its magazine is dry (no round chambered): left to the game'}
    end
    local ok,why=M.prove(world)
    if not ok then return {kind='refused',code='UNSUPPORTED_BUILD',reason=tostring(why)}end
    local mag=magazine_state(world,turret)
    local MG=TW.magazine
    local rec=mag and mag.record and world.view.read(mag.record,MG.stride)
    local ent=mag and mag.entry and world.view.read(mag.entry,AM.entryStride)
    local rec_owner=rec and pelicans.owner_of(world,mag.record,MG.stride)
    local ent_owner=ent and pelicans.owner_of(world,mag.entry,AM.entryStride)
    if not(rec_owner and ent_owner)then return {kind='refused',code='NOT_PRIVATE',reason='its magazine is unreadable'}end
    local identity={component='WeaponMagazine',component_type='native',unique_owner=true,owner_count=1}
    local plan={snapshots={{owner=rec_owner,offset=mag.record-rec_owner.base,bytes=rec},
            {owner=ent_owner,offset=mag.entry-ent_owner.base,bytes=ent}},
        changes={{label='turret.'..turret..'.magazine.working_rounds',owner=rec_owner,offset=mag.record+MG.rounds-rec_owner.base,
                expected=rec:sub(MG.rounds+1,MG.rounds+4),desired=u32(M.AMMO_MAX),before=rec:sub(MG.rounds+1,MG.rounds+4),
                already_desired=false,identity=identity,chain={}},
            {label='turret.'..turret..'.magazine.rounds',owner=ent_owner,offset=mag.entry+AM.entryRounds-ent_owner.base,
                expected=ent:sub(AM.entryRounds+1,AM.entryRounds+4),desired=u32(M.AMMO_MAX),
                before=ent:sub(AM.entryRounds+1,AM.entryRounds+4),already_desired=false,identity=identity,chain={}}}}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('pelican_weapon.transactions')
    if report.status~='APPLIED'then return {kind='refused',code='GUARD_REJECTED',reason=tostring(report.reason)}end
    local after=M.ammo_state(world,turret,CHIN)
    if first_time(turret,'refill')then
        log(('AMMO REFILL (%s): chin turret %d: %d -> %d (its own magazine; read back %s)'):format(tostring(label),turret,
            a.rounds,M.AMMO_MAX,tostring(after and after.rounds)))
    end
    return {kind='refilled',old=a.rounds,new=after and after.rounds or M.AMMO_MAX}
end

---------------------------------------------------------------------------------------- the turret's candidates --
-- What the Gatling AI could attack, read-only (research "targetSet", docs section 21): the perceiver its Behavior
-- record names (P+0x60) and that perceiver's lists A, B and C; per entry what the AI's own pick tests: perceived now
-- (the entry's sense bits against its sensors' bits, which only the game's own vision cone and ray set), hostile (the
-- entity's faction mask non-zero and sharing no bit with the perceiver's), entity flags 25 (invalid) and 35 (never
-- scored), alive with health, and under 100 m from the muzzle (nothing farther scores).
local bit=require('bit')
local TS=D.targetSet
local PC=TS.perception
local function component_index(world,global,map,key)
    local mgr=world.view.pointer(world.game+global)
    if not mgr or mgr==0 then return nil end
    return pelicans.index_of(world,mgr,map_at(map),key),mgr
end
local function faction_mask(world,entity)
    local F=TS.faction
    local index,mgr=component_index(world,F.global,F.map,entity)
    local masks=index and world.view.pointer(mgr+F.masks)
    local raw=masks and masks~=0 and world.view.read(masks+index*4,4)
    return raw and b.u32(raw,0)or 0
end
local function flag_set(world,entity,n)
    local EF=TS.entityFlags
    local index,mgr=component_index(world,EF.global,EF.map,entity)
    local values=index and world.view.pointer(mgr+EF.values)
    local raw=values and values~=0 and world.view.read(values+index*8+(n>=32 and 4 or 0),4)
    return raw~=nil and raw~=false and bit.band(b.u32(raw,0),bit.lshift(1,n%32))~=0
end
local function sub3(p,q)return {x=p.x-q.x,y=p.y-q.y,z=p.z-q.z}end
local function len3(v)return math.sqrt(v.x*v.x+v.y*v.y+v.z*v.z)end
-- The turn (degrees) from pointing at p to pointing at q, seen from the muzzle m: in all, and its yaw (azimuth) part.
local function traverse(m,p,q)
    local u,v=sub3(p,m),sub3(q,m)
    local lu,lv=len3(u),len3(v)
    if lu<1e-3 or lv<1e-3 then return nil end
    local c=math.max(-1,math.min(1,(u.x*v.x+u.y*v.y+u.z*v.z)/(lu*lv)))
    local yaw=(math.deg(math.atan2(v.y,v.x)-math.atan2(u.y,u.x))+180)%360-180
    return math.deg(math.acos(c)),yaw
end
M.traverse=traverse
-- M.perception(world, turret, a): {key, record, sensors, mask, faction, entries = {{entity, list, address,
-- position (last known), perceived, seen (u64), score (its last)}}} or nil.
function M.perception(world,turret,a)
    a=a or M.ai_state(world,turret)
    if not a then return nil end
    local key=b.u32(a.raw,TS.record.perceiver)
    if key==0 then return nil end
    local index,mgr=component_index(world,PC.global,PC.map,key)
    local records=index and world.view.pointer(mgr+PC.records)
    if not(records and records~=0)then return nil end
    local address=records+index*PC.stride
    local raw=world.view.read(address,PC.stride)
    if not raw then return nil end
    local sensors=b.u32(raw,PC.sensors)
    if sensors>PC.maxSensors then return nil end
    local mask=0
    for s=0,sensors-1 do mask=bit.bor(mask,bit.lshift(1,b.u32(raw,PC.sensorBit+s*PC.sensorStride)%32))end
    local out={key=key,record=address,sensors=sensors,mask=mask,faction=b.u32(raw,PC.factionMask),entries={}}
    for _,list in ipairs(PC.lists)do
        local count=b.u32(raw,list.count)
        if count>PC.listMax then return nil end
        for e=0,count-1 do
            local at=list.entries+e*PC.entryStride
            local entity=b.u32(raw,at+PC.entryEntity)
            if entity~=0 then
                out.entries[#out.entries+1]={entity=entity,list=list.name,address=address+at,
                    position=vec3(raw,at+PC.entryPosition),perceived=bit.band(b.u32(raw,at+PC.entrySense),mask)~=0,
                    seen=u64(raw,at+PC.entrySeen),score=f32(raw,at+PC.entryScore)}
            end
        end
    end
    return out
end
-- One entry judged as the AI's pick would: true, nil, its position (live, else last known) and its distance from the
-- muzzle; or false and why.
local function judge(world,p,e,muzzle)
    if not e.perceived then return false,'not perceived'end
    local theirs=faction_mask(world,e.entity)
    if theirs==0 or bit.band(theirs,p.faction)~=0 then return false,'not hostile'end
    local st=world_module.entity_state(world,e.entity)
    if not(st and st.health and st.health>0 and(st.life or 0)<2)then return false,'not alive'end
    if flag_set(world,e.entity,TS.entityFlags.invalid)or flag_set(world,e.entity,TS.entityFlags.unscored)then
        return false,'excluded by its entity flags'
    end
    local unit=st.descriptor and st.descriptor.unit
    local pos=unit and unit~=0 and world_module.unit_position(world,unit)or e.position
    local distance=muzzle and len3(sub3(pos,muzzle))
    if distance and distance>=TS.range then return false,'out of range'end
    return true,nil,pos,distance
end
-- M.candidates(world, turret, a, around, exclude): every entry the AI could attack now, with its position, its distance
-- from `around` (near), the turret's turn to it from where it points now (turn, yaw) and a score (near + M.TRAVERSE_WEIGHT
-- m a degree of turn); and the perception read. nil, why when unreadable.
M.NEAR={25,50}
M.TRAVERSE_WEIGHT=0.5
function M.candidates(world,turret,a,around,exclude)
    local p=M.perception(world,turret,a)
    if not p then return nil,'its perception record is unreadable'end
    local am=M.aim_state(world,turret)
    local muzzle=am and am.muzzle
    local out={}
    for _,e in ipairs(p.entries)do
        if not(exclude and exclude[e.entity])then
            local ok,_,pos,distance=judge(world,p,e,muzzle)
            if ok then
                local turn,yaw
                if muzzle and am.aim then turn,yaw=traverse(muzzle,am.aim,pos)end
                local near=around and len3(sub3(pos,around))
                out[#out+1]={entity=e.entity,entry=e.address,list=e.list,position=pos,distance=distance,near=near,
                    turn=turn,yaw=yaw,score=(near or 0)+(turn or 0)*M.TRAVERSE_WEIGHT}
            end
        end
    end
    return out,p
end
-- The candidate nearest `around`: within M.NEAR[1] m, else within M.NEAR[2] m, the lowest score; nil when none is that
-- close.
function M.nearest(list,around)
    if not(list and around)then return nil end
    for _,radius in ipairs(M.NEAR)do
        local best
        for _,c in ipairs(list)do
            if c.near and c.near<=radius and(not best or c.score<best.score)then best=c end
        end
        if best then best.radius=radius;return best end
    end
    return nil
end

------------------------------------------------------------------------------------------------- attribution --
-- Kill attribution (research "attribution", docs section 24). A turret's shot takes its owner from the weapon's wielder
-- (the Wieldable component) and its creditor from the game's own Creditor(owner) (0x129C690): the peer owning the
-- owner's network object, or none when the owner has no faction record, lacks faction bit 0, has no network id, or
-- carries the no-credit tag 0x10000000 (its own Tag mask; the game gives it to an Eagle without an owner). The
-- creditor travels with the projectile into the hit and the victim's health record (+0x38), which every kill dispatch
-- credits. The chin turret wields itself and carries that tag, so its kills credit nobody.
-- M.credit_state(world, turret): {wielder, tags_lo, tags_hi, tag_at, raw (8 bytes), no_credit, faction, network} of
-- its wielder, read-only, or nil.
local AT=D.attribution
function M.credit_state(world,turret)
    local W,TG=AT.wieldable,AT.tags
    local wi,wm=component_index(world,W.global,W.map,turret)
    local wielders=wi and world.view.pointer(wm+W.wielder)
    local wraw=wielders and wielders~=0 and world.view.read(wielders+wi*4,4)
    if not wraw then return nil end
    local wielder=b.u32(wraw,0)
    local ti,tm=component_index(world,TG.global,TG.map,wielder)
    local values=ti and world.view.pointer(tm+TG.values)
    local at=values and values~=0 and values+ti*8
    local raw=at and world.view.read(at,8)
    local r=gatling.removal_state(world,wielder)
    return {wielder=wielder,tag_at=at,raw=raw,tags_lo=raw and b.u32(raw,0),tags_hi=raw and b.u32(raw,4),
        no_credit=raw~=nil and bit.band(b.u32(raw,0),AT.noCredit)~=0,faction=faction_mask(world,wielder),
        network=r.network}
end
function M.credit_text(c)
    if not c then return'(unreadable)'end
    return ('wielder %d, Tag mask 0x%08X%08X (no-credit tag %s), faction %d, network id %s'):format(c.wielder,
        c.tags_hi or 0,c.tags_lo or 0,c.no_credit and'SET'or'clear',c.faction or 0,tostring(c.network))
end
-- M.configure_credit(world, turret, label): one guarded 8-byte write of the chin turret's OWN Tag mask, the no-credit
-- tag cleared and every other bit kept, so the game's own Creditor names the owner of its network object (the host,
-- who called the Pelican: Runtime Pelicans are host-only) for its shots, exactly as for a native self-wielding sentry.
-- Only when it wields itself, has faction bit 0, a network id and the tag. Returns {applied, already, reason, before,
-- after, writes, peer_lo, peer_hi (the local peer: the expected creditor)}.
function M.configure_credit(world,turret,label)
    local out={applied=false,writes=0}
    if not scheduler.in_update()then out.reason='NOT_GAME_THREAD: only inside the Runtime\'s update';return out end
    local c=M.credit_state(world,turret)
    out.before=c
    out.peer_lo,out.peer_hi=world_module.local_peer(world)
    if not c then out.reason='its Wieldable record is unreadable';return out end
    if c.wielder~=turret then
        out.reason=('WIELDER_UNEXPECTED: its wielder is %d, not itself'):format(c.wielder);return out
    end
    if not c.raw then out.reason='its Tag record is unreadable';return out end
    if bit.band(c.faction or 0,AT.factionBit)==0 then
        out.reason=('FACTION_UNEXPECTED: its faction mask is %d'):format(c.faction or 0);return out
    end
    if not c.network then out.reason='NO_NETWORK: it has no network id';return out end
    if not c.no_credit then
        out.applied,out.already,out.after=true,true,c
        log(('CREDIT (%s): chin turret %d: no no-credit tag to clear (%s)'):format(tostring(label),turret,M.credit_text(c)))
        return out
    end
    local owner=pelicans.owner_of(world,c.tag_at,8)
    if not owner then out.reason='its Tag mask is not in private read-write memory';return out end
    local desired=u32(bit.band(c.tags_lo,bit.bnot(AT.noCredit))%4294967296)..c.raw:sub(5,8)
    local identity={component='Tag',component_type='native',unique_owner=true,owner_count=1}
    local plan={snapshots={{owner=owner,offset=c.tag_at-owner.base,bytes=c.raw}},
        changes={{label='turret.'..turret..'.tags',owner=owner,offset=c.tag_at-owner.base,expected=c.raw,desired=desired,
            before=c.raw,already_desired=false,identity=identity,chain={}}}}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('pelican_weapon.transactions')
    if report.status~='APPLIED'then out.reason='refused: '..tostring(report.reason);return out end
    local after=M.credit_state(world,turret)
    out.after,out.writes=after,report.writes
    out.applied=after~=nil and after.raw==desired
    log(('CREDIT (%s): chin turret %d: its own Tag mask 0x%08X%08X -> 0x%08X%08X (the no-credit tag 0x%08X cleared, every '
        ..'other bit kept); %s; the game\'s own Creditor now names the owner of its network object (the host, peer %s); '
        ..'%d writes; read back %s'):format(tostring(label),turret,c.tags_hi,c.tags_lo,after and after.tags_hi or 0,
        after and after.tags_lo or 0,AT.noCredit,M.credit_text(after),out.peer_lo and world_module.peer_hex(out.peer_lo,
        out.peer_hi)or'?',report.writes,tostring(out.applied)))
    return out
end
-- M.last_hit(world, entity): its health record's last hit, read-only: {owner (entity, +0x30), creditor_lo, creditor_hi
-- (+0x38), health, life} or nil.
local HN=require('hd2runtime/domains/event_natives').health
function M.last_hit(world,entity)
    local st=world_module.entity_state(world,entity)
    if not(st and st.header and st.header.records)then return nil end
    local raw=world.view.read(st.header.records+st.index*HN.stride+AT.healthOwner,AT.healthCreditor+8-AT.healthOwner)
    if not raw then return nil end
    return {owner=b.u32(raw,0),creditor_lo=b.u32(raw,AT.healthCreditor-AT.healthOwner),
        creditor_hi=b.u32(raw,AT.healthCreditor-AT.healthOwner+4),health=st.health,life=st.life}
end

----------------------------------------------------------------------------------------------- the target setter --
-- M.set_target(world, turret, entity, label): the game's own target setter (0x4AF4E0), as the Gatling AI's own pick
-- calls it, for ONE Runtime Pelican's own chin turret that the Runtime gave the Gatling AI: the context the Behavior
-- update builds ({its Behavior handle record, P}) and the live entry of `entity` in the turret's own perception lists,
-- which it copies in as the target. Only on the game thread, in a mission, as the solo host, with the setter's entry
-- bytes and every Pelican pin proven, the AI in stage 5 or 12 with nothing pending, the handle naming the turret, and
-- `entity` a candidate the AI could attack (M.candidates). The target is read back: {target (P+0x10 after), requested,
-- installed (target == requested)} or nil, code, reason.
local SET=TS.setter
M.SET_LOG_FIRST=3
M.SET_LOG_EVERY=100
function M.set_target(world,turret,entity,label)
    label=tostring(label or'?')
    local function refuse(code,reason)
        if first_time(turret,'set_refused:'..tostring(code))then
            log(('TARGET SET REFUSED (%s): chin turret %s, entity %s: %s: %s'):format(label,tostring(turret),
                tostring(entity),code,reason))
        end
        return nil,code,reason
    end
    local sw=switched[turret]
    if not sw then return refuse('NOT_SWITCHED','not a chin turret the Runtime gave the Gatling AI')end
    if not world.runtime.native_set_target then
        return refuse('UNAVAILABLE','this Runtime adapter cannot call game functions')
    end
    if not scheduler.in_update()then return refuse('NOT_GAME_THREAD','only inside the Runtime\'s own update')end
    local ok,why=M.prove(world)
    if not ok then return refuse('UNSUPPORTED_BUILD',tostring(why))end
    if not world.view.proves(world.game+SET.rva,SET.prologue)then
        return refuse('UNSUPPORTED_BUILD',('the game\'s target setter changed (game+%X)'):format(SET.rva))
    end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return refuse('NOT_IN_MISSION','in a mission only')end
    if game.host~=true then return refuse('NOT_HOST','development experiment: host only')end
    local record_list,code,reason=slots.local_record(world)
    if not record_list then return refuse(code,reason)end
    local mp=require('hd2runtime/runtime/multiplayer')
    local scode,swhy=mp.solo_guard(record_list.records,mp.entity_allowed(sw.pelican),'the target is the host AI\'s')
    if scode then return refuse(scode,swhy)end
    if not pelicans.owned(sw.pelican)then
        return refuse('NOT_RUNTIME_PELICAN','Pelican '..tostring(sw.pelican)..' was not spawned by the Runtime')
    end
    local state,scode,sreason=gatling.inspect(world,sw.pelican)
    if not state then return refuse(scode,sreason)end
    if #state.attached~=1 or not state.turret or state.turret.entity~=turret or state.turret.resource~=CHIN then
        return refuse('TURRET_UNEXPECTED','the Pelican\'s one chin turret is not this entity')
    end
    local rec=pelicans.behavior_of(world,turret)
    if not(rec and rec.handle_slot)then return refuse('UNAVAILABLE','its Behavior record is unreadable')end
    local a=M.ai_state(world,turret)
    if not(a and a.id==AI.gatling)then return refuse('TURRET_UNEXPECTED','its behaviour is not 213')end
    if not(a.pending==-1 and a.transitioning==-1)then return refuse('NOT_QUIET','a stage is pending')end
    if a.stage~=AI213.fireStage and a.stage~=AI213.aimStage then
        return refuse('NOT_QUIET',('it is in stage %d, not aiming or firing'):format(a.stage))
    end
    local handle=world.view.pointer(rec.handle_slot)
    local named=handle and world.view.read(handle+TS.context.handleEntity,4)
    if not(named and b.u32(named,0)==turret)then return refuse('TURRET_UNEXPECTED','its Behavior handle names another')end
    local list,pwhy=M.candidates(world,turret,a)
    if not list then return refuse('UNAVAILABLE',pwhy)end
    local chosen
    for _,c in ipairs(list)do if c.entity==entity then chosen=c end end
    if not chosen then
        return refuse('NOT_A_CANDIDATE','not perceived, hostile, alive and in range in its own perception lists')
    end
    metrics.count('pelican_weapon.native_calls')
    world.runtime.native_set_target(world.game+SET.rva,handle,rec.address+TS.context.state,chosen.entry)
    local after=M.ai_state(world,turret)
    local target=after and after.target
    -- Logged for the first M.SET_LOG_FIRST calls on a turret, then every M.SET_LOG_EVERY-th (and the first that missed;
    -- every call with M.verbose).
    sw.sets=(sw.sets or 0)+1
    if M.verbose or sw.sets<=M.SET_LOG_FIRST or sw.sets%M.SET_LOG_EVERY==0
            or(target~=entity and first_time(turret,'set_miss'))then
        log(('TARGET SET (%s): chin turret %d: entity %d (list %s entry 0x%X) through the game\'s target setter (game+%X); '
            ..'target after: %s%s; call %d'):format(label,turret,entity,chosen.list,chosen.entry,SET.rva,tostring(target),
            target==entity and''or' (NOT the requested entity)',sw.sets))
    end
    return {target=target,requested=entity,installed=target==entity}
end

------------------------------------------------------------------------------------------- the target controller --
-- The Gatling AI (213) has no target lock (research "targetChoice"): it re-scores every perceived candidate whenever
-- its re-pick time (record +0x98, P+0x90) is due -- every 1 s with a target, and at every stage entry -- and it measures
-- only from the turret, so on the chin turret it jumps across the battlefield. M.target_step(world, turret, label),
-- several times a second for a switched turret, supervises it (docs section 21):
--   * LOCK the target the AI aims at (stage 5) or fires at (stage 12), alive. (0.4.1 measured its distance from the
--     turret's transform record, which a mounted child never updates -- its creation point, ~250 m from every target --
--     so nothing ever locked.)
--   * RETAIN it while it is the AI's target: its re-pick time is kept ahead of the clock (a guarded 8-byte write when
--     less than M.HOLD_MIN s remain, to now + M.HOLD s), so the periodic re-score cannot switch.
--   * RESTORE it through the game's own target setter when a stage entry's re-pick took another, or the AI lost it for a
--     moment, while it is still alive and perceived (at most every M.RESTORE_SPACING s).
--   * RELEASE it when it dies, when it has been out of the AI's sight for M.GRACE s, when it takes no damage for
--     M.RELEASE_SECONDS s of firing (not hittable), or when the AI aims at it for M.AIM_SECONDS s without firing (cannot
--     be fired at); the last two are not locked again for M.REJECT s.
--   * REPLACE it with the candidate nearest where it was (M.nearest), through the setter: while firing at once when the
--     turn is at most M.FIRE_TRAVERSE degrees, else through the AI's own exit from firing (pending stage 4) and then in
--     stage 5, which fires only within 3 degrees. None that close: the AI's own pick decides (the exit, when firing).
-- Never with a stage pending or a transition running; writes only the re-pick time and the pending stage, and calls
-- only the setter. Returns a list of events: {kind = 'locked' | 'retained' | 'released' | 'restored' | 'switched' |
-- 'transition' | 'exit_ran' | 'refused', ...}.
M.RELEASE_SECONDS=3       -- s of firing without damage before a target is let go (user: 3 s of non-stop shooting)
-- At a slow rate (a turret configured below 60 / ((RELEASE_SECONDS - RELEASE_MARGIN) / RELEASE_SHOTS) RPM) the window
-- holds RELEASE_SHOTS shots plus RELEASE_MARGIN s instead: 6.5 s at 30 RPM, 3.5 s at 60, 3 s at the Gatling rates
-- (build/test-artifacts/mortar-fire-research/mortar-fire.md 1.3: at 30 RPM one miss would otherwise let it go).
M.RELEASE_SHOTS,M.RELEASE_MARGIN=3,0.5
M.HOLD=2
M.HOLD_MIN=1.25
M.GRACE=0.5
M.REJECT=5
M.AIM_SECONDS=1.5         -- s aiming without firing before an unaimable target is let go (was 3)
-- Faster acquisition and firing (docs/research/pelican-cas-F5FEE03DCFDB.md section 30; research/custom-payloads
-- pelicanIdle; build/test-artifacts/ai-research/idle-ai.md): behaviour 213 idles on its own timers, a 1 s re-pick while it
-- searches (stages 2 / 3) and a 0.5 s fire check while it aims (stage 5, within 3 degrees). With M.AGGRESSIVE the
-- controller makes them due NOW (the same guarded 8-byte write as the lock's hold), so the game's own logic picks and
-- fires at once:
--   * the re-pick, in stage 2 or 3 while M.candidates lists something it could attack, at most every pelicanIdle
--     repickPeriod (0.25 s, the game's own fastest); after M.REPICK_TRIES that left it searching (it scores them 0 for a
--     reason the Runtime does not mirror), it pauses M.REPICK_PAUSE s;
--   * the fire check, in stage 5 while its target is one M.candidates lists (alive, perceived, hostile, in range);
--   * an unaimable target is let go after M.AIM_SECONDS and, with no candidate near it, replaced by the one the turret
--     turns least to reach (through the setter, as any stage-5 replacement).
M.AGGRESSIVE=true
M.REPICK_TRIES=4
M.REPICK_PAUSE=2
local PI=require('hd2runtime/domains/custom_payloads').pelicanIdle
local idle_proven
local function idle_prove(world)
    if idle_proven then return true end
    if not M.prove(world)then return false end
    for _,pin in ipairs(PI.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then return false end
    end
    idle_proven=true
    return true
end
M.FIRE_TRAVERSE=12
M.RESTORE_SPACING=0.5
M.WANT_SECONDS=2
local watches={}
function M.watch_of(turret)return watches[turret]end
local function guarded_u(world,turret,rec,at,size,desired,name)
    local owner=pelicans.owner_of(world,rec.address,BC.stride)
    if not owner then return nil,'NOT_PRIVATE','the Behavior record is not in private read-write memory'end
    local identity={component='Behavior',component_type='native',unique_owner=true,owner_count=1}
    local old=rec.raw:sub(at+1,at+size)
    -- The record's head (behaviour id, stage, pending, transition, target) always; the field too when it lies beyond it
    -- (each change in exactly one context).
    local snapshots={{owner=owner,offset=rec.address-owner.base,bytes=rec.raw:sub(1,AI.target+4)}}
    if at>=AI.target+4 then snapshots[2]={owner=owner,offset=rec.address+at-owner.base,bytes=old}end
    local plan={snapshots=snapshots,
        changes={{label='turret.'..turret..'.'..name,owner=owner,offset=rec.address+at-owner.base,expected=old,
            desired=desired,before=old,already_desired=false,identity=identity,chain={}}}}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('pelican_weapon.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    return true
end
-- A target's state, read-only: {alive, health, pos (its live root), distance (m, from the muzzle), seen (s since the AI
-- last saw it, while it is the AI's target)}.
local function target_state(world,entity,a,now,muzzle)
    local st=world_module.entity_state(world,entity)
    local health=st and st.health
    local unit=st and st.descriptor and st.descriptor.unit
    local pos=unit and unit~=0 and world_module.unit_position(world,unit)or nil
    local seen
    if a.target==entity then
        local t=u64(a.raw,AI213.lastSeen)
        if t>0 and now>=t then seen=(now-t)/US end
    end
    return {alive=health~=nil and health>0 and(st.life or 0)<2,health=health,pos=pos,
        distance=muzzle and pos and len3(sub3(pos,muzzle))or nil,seen=seen}
end
-- The not-hittable window of a turret, in seconds (its configured current RPM).
function M.release_window(turret)
    local c=configured[turret]
    local rpm=c and c.spec and tonumber(c.spec.rpm)
    if not(rpm and rpm>0)then return M.RELEASE_SECONDS end
    return math.max(M.RELEASE_SECONDS,M.RELEASE_SHOTS*60/rpm+M.RELEASE_MARGIN)
end
function M.target_step(world,turret,label)
    local out={}
    if not switched[turret]then return out end
    if not scheduler.in_update()then
        out[1]={kind='refused',code='NOT_GAME_THREAD',reason='only inside the Runtime\'s update'}
        return out
    end
    local a=M.ai_state(world,turret)
    local now=pelicans.clock(world)
    if not(a and now)then watches[turret]=nil;return out end
    if a.id~=AI.gatling then watches[turret]=nil;return out end
    local w=watches[turret]
    if not w then w={good=now,rejected={},restores=0,spatial=0,native=0};watches[turret]=w end
    local function emit(e)out[#out+1]=e;return e end
    -- A queued exit: consumed when the pending stage is.
    if w.queued then
        if a.pending~=AI213.releaseStage then
            emit({kind='exit_ran',stage=a.stage,reason=w.queued_reason})
            w.queued,w.queued_reason=nil,nil
            w.good=now
        elseif now-w.queued>=1e6 then
            emit({kind='refused',code='NOT_CONSUMED',reason=('the queued exit did not run within 1 s: %s'):format(
                M.ai_text(a))})
            w.queued,w.queued_reason=nil,nil
        else
            return out
        end
    end
    local quiet=a.pending==-1 and a.transitioning==-1
    local firing=a.stage==AI213.fireStage
    local aiming=a.stage==AI213.aimStage
    local am=M.aim_state(world,turret)
    local muzzle=am and am.muzzle
    local function state_of(entity)return target_state(world,entity,a,now,muzzle)end
    local function queue_exit(reason)
        if not(quiet and firing)then return false end
        local ok,code=M.prove(world)
        if not ok then emit({kind='refused',code='UNSUPPORTED_BUILD',reason=tostring(code)});return false end
        local rec=pelicans.behavior_of(world,turret)
        if not rec then return false end
        local r,c2,why=guarded_u(world,turret,rec,AI.pending,4,u32(AI213.releaseStage),'pending_stage')
        if not r then emit({kind='refused',code=c2,reason=why});return false end
        w.queued,w.queued_reason=now,reason
        if first_time(turret,'exit')then
            log(('TARGET EXIT (%s): chin turret %d: %s: queued the AI\'s own exit from firing (pending stage, record '
                ..'+0x%X: -1 -> %d)'):format(tostring(label),turret,reason,AI.pending,AI213.releaseStage))
        end
        return true
    end
    -- Keep the AI from re-scoring while the lock is its target (its re-pick time ahead of the clock).
    local function hold()
        if not(quiet and(firing or aiming)and w.lock and a.target==w.lock)then return end
        local due=u64(a.raw,AI213.repick)
        if due>=now+M.HOLD_MIN*US then return end
        local rec=pelicans.behavior_of(world,turret)
        local ok=M.prove(world)
        if not(rec and ok)then return end
        local r,c2,why=guarded_u(world,turret,rec,AI213.repick,8,encode64(now+M.HOLD*US),'repick_time')
        if r then w.holds=(w.holds or 0)+1 else emit({kind='refused',code=c2,reason=why})end
    end
    local function excluded(extra)
        local x={}
        for entity in pairs(w.rejected)do x[entity]=true end
        if extra then x[extra]=true end
        return x
    end
    -- The lock becomes `entity` (how: 'the AI's pick', 'spatial', 'switched'); a transition from the last lock.
    local function adopt(entity,ts,how)
        local last=w.last
        w.lock,w.lock_since,w.lost_at,w.good,w.health,w.lock_pos=entity,now,nil,now,ts.health,ts.pos
        w.aim_since=aiming and now or nil
        w.last,w.want=nil,nil
        emit({kind='locked',target=entity,state=ts,stage=a.stage,how=how})
        if last and last.entity~=entity then
            local e={kind='transition',from=last.entity,to=entity,from_pos=last.pos,to_pos=ts.pos,how=how,
                reason=last.reason}
            if last.pos and ts.pos then e.between=len3(sub3(ts.pos,last.pos))end
            if muzzle and last.pos and ts.pos then e.turn,e.yaw=traverse(muzzle,last.pos,ts.pos)end
            emit(e)
        end
        if how=='spatial'then w.spatial=w.spatial+1 else w.native=w.native+1 end
        hold()
    end
    -- Through the game's setter: the AI's target and the lock become c.entity.
    local function install(c)
        local r,code,why=M.set_target(world,turret,c.entity,label)
        if not r then emit({kind='refused',code=code,reason=why});return false end
        a=M.ai_state(world,turret)or a
        if not r.installed then
            emit({kind='refused',code='NOT_INSTALLED',reason=('the setter left target %s, not entity %d'):format(
                tostring(r.target),c.entity)})
            return false
        end
        adopt(c.entity,state_of(c.entity),'spatial')
        return true
    end
    -- The lock is let go; its replacement is the candidate nearest where it was. `picked`: the AI already has another
    -- target, which stands when it is itself that near.
    local function release(reason,why,reject,picked)
        local old=w.lock
        if reject and old then w.rejected[old]=now+M.REJECT*US end
        w.last={entity=old,pos=w.lock_pos,reason=reason}
        w.lock,w.lock_since,w.lost_at,w.health,w.aim_since=nil,nil,nil,nil,nil
        local list=M.candidates(world,turret,a,w.last.pos,excluded(old))
        local best=M.nearest(list,w.last.pos)
        -- Aiming with none near the old target: the one the turret turns least to reach (M.AGGRESSIVE).
        if not best and aiming and M.AGGRESSIVE then
            for _,c in ipairs(list or{})do if c.turn and(not best or c.turn<best.turn)then best=c end end
            if best then best.radius=math.huge end
        end
        local mine
        if picked and best then
            for _,c in ipairs(list)do if c.entity==a.target and c.near and c.near<=best.radius then mine=c end end
        end
        local now_ok=best and not mine and quiet and(aiming or(firing and(not best.turn or best.turn<=M.FIRE_TRAVERSE)))
        local plan=mine and'the AI\'s own pick is as near: it stands'
            or not best and(picked and'none within '..M.NEAR[#M.NEAR]..' m: the AI\'s own pick stands'
                or'none within '..M.NEAR[#M.NEAR]..' m: the AI\'s own pick')
            or now_ok and'installed now'or'after the AI\'s own exit from firing, in stage 5'
        local ev=emit({kind='released',target=old,reason=reason,text=why,replacement=mine or best,plan=plan,
            candidates=list and #list or nil})
        if mine then adopt(mine.entity,state_of(mine.entity),'spatial');return end
        if now_ok then
            if best.entity==a.target then adopt(best.entity,state_of(best.entity),'spatial');return end
            if install(best)then return end
            best=nil
        end
        if best then w.want={entity=best.entity,since=now,pos=w.last.pos}end
        if best or not picked then ev.exit=queue_exit(why)end
    end
    for entity,untill in pairs(w.rejected)do if now>=untill then w.rejected[entity]=nil end end
    local T=a.target
    -- The lock.
    if w.lock then
        local ts=state_of(w.lock)
        local held=w.lock
        if ts.pos then w.lock_pos=ts.pos end
        if T==w.lock then
            w.lost_at=nil
            if not ts.alive then
                release('dead',('entity %d is dead'):format(w.lock))
            elseif firing then
                w.aim_since=nil
                if ts.health and w.health and ts.health<w.health then w.good=now end
                w.health=ts.health
                if now-w.good>=M.release_window(turret)*US then
                    release('not hittable',('firing at entity %d for %.1f s and its health (%s) has not dropped: the '
                        ..'turret cannot hit it'):format(w.lock,(now-w.good)/US,tostring(ts.health)),true)
                end
            elseif aiming then
                w.good,w.health=now,ts.health
                w.aim_since=w.aim_since or now
                if now-w.aim_since>=M.AIM_SECONDS*US then
                    release('cannot fire',('aiming at entity %d for %.1f s without firing (the barrel never within 3 '
                        ..'degrees, or the AI does not score it)'):format(w.lock,(now-w.aim_since)/US),true)
                end
            else
                w.good,w.health,w.aim_since=now,ts.health,nil
            end
            if w.lock==held then
                hold()
                if not w.next_retained or now>=w.next_retained then
                    w.next_retained=now+2*US
                    emit({kind='retained',target=w.lock,state=ts,stage=a.stage,holds=w.holds or 0,
                        since=(now-w.lock_since)/US})
                end
            end
        else
            -- Not its target: the AI lost it (T nil) or a stage entry's re-pick took another (T). Back through the
            -- setter while it is alive and perceived; otherwise let go (dead at once; out of sight after M.GRACE s).
            w.lost_at=w.lost_at or now
            local seen=false
            if ts.alive and not w.rejected[w.lock]then
                local p=M.perception(world,turret,a)
                for _,e in ipairs(p and p.entries or{})do if e.entity==w.lock and e.perceived then seen=true end end
            end
            if not ts.alive then
                release('dead',('entity %d is dead'):format(w.lock),false,T~=nil)
            elseif seen and now-w.lost_at<M.WANT_SECONDS*US then
                -- In sight: restored as soon as the AI can take it.
                if quiet and(firing or aiming)and(not w.restored_at or now-w.restored_at>=M.RESTORE_SPACING*US)then
                    w.restored_at=now
                    local r=M.set_target(world,turret,w.lock,label)
                    a=M.ai_state(world,turret)or a
                    if r and r.installed then
                        w.lost_at=nil
                        w.restores=w.restores+1
                        emit({kind='restored',target=w.lock,from=T,stage=a.stage})
                        hold()
                    else
                        if T then emit({kind='switched',from=w.lock,to=T,lock_valid=true,stage=a.stage})end
                        release(T and'switched'or'out of sight',('the setter could not restore entity %d (%s)'):format(
                            w.lock,r and('target %s after it'):format(tostring(r.target))or'refused'),false,T~=nil)
                    end
                end
            elseif T then
                emit({kind='switched',from=w.lock,to=T,lock_valid=ts.alive,perceived=seen,stage=a.stage})
                release(seen and'switched'or'out of sight',('the AI\'s own re-pick took entity %d; entity %d is %s')
                    :format(T,w.lock,seen and'still in sight but could not be restored'or'out of its sight'),false,true)
            elseif seen or now-w.lost_at>=M.GRACE*US then
                release('out of sight',('entity %d has not been the AI\'s target for %.1f s (%s)'):format(w.lock,
                    (now-w.lost_at)/US,seen and'in sight, but it could not be restored'or'out of its sight'))
            end
        end
    end
    T=a.target
    -- A replacement chosen at a release, installed once the AI can take it: in stage 5 (it fires only within 3
    -- degrees), or while firing when the turn is small; a bigger turn while firing goes through the AI's own exit first.
    if not w.lock and w.want and not w.queued then
        if now-w.want.since>=M.WANT_SECONDS*US then
            w.want=nil
        elseif quiet and(aiming or firing)then
            local list=M.candidates(world,turret,a,w.want.pos,excluded())
            local c
            for _,x in ipairs(list or{})do if x.entity==w.want.entity then c=x end end
            c=c or M.nearest(list,w.want.pos)
            if not c then
                w.want=nil
            elseif aiming or(c.turn and c.turn<=M.FIRE_TRAVERSE)then
                w.want=nil
                if T==c.entity then adopt(T,state_of(T),'spatial')else install(c)end
            else
                queue_exit(('a %.0f degree turn to entity %d, the replacement: the AI\'s own exit first'):format(c.turn or-1,
                    c.entity))
            end
        end
    end
    T=a.target
    -- A new lock: the AI's own pick while aiming or firing (not one found unhittable).
    if not w.lock and not w.want and T and(firing or aiming)and not w.rejected[T]and not w.queued then
        local ts=state_of(T)
        if ts.alive then adopt(T,ts,'the AI\'s pick')end
    end
    -- A target found unhittable picked again while firing: out again at once.
    if T and w.rejected[T]and firing and not w.queued then
        queue_exit(('entity %d was found unhittable %.1f s ago'):format(T,(M.REJECT*US-(w.rejected[T]-now))/US))
    end
    -- No lock, firing with no valid target.
    if not w.lock and firing and not w.queued then
        local valid=T and state_of(T).alive
        if valid then w.nolock=nil else w.nolock=w.nolock or now end
        if w.nolock and now-w.nolock>=M.RELEASE_SECONDS*US then
            w.nolock=nil
            if queue_exit(('firing for %.1f s with no valid target (target %s)'):format(M.RELEASE_SECONDS,tostring(T)))then
                emit({kind='released',reason='no target',text='firing with no valid target',exit=true})
            end
        end
    else
        w.nolock=nil
    end
    -- Faster acquisition and firing (M.AGGRESSIVE): the AI's own re-pick / fire check made due now.
    if M.AGGRESSIVE and quiet and not w.queued then
        a=M.ai_state(world,turret)or a
        T=a.target
        local stage=a.stage
        local function due_now(at,name)
            if not idle_prove(world)then return nil end
            local rec=pelicans.behavior_of(world,turret)
            if not rec then return nil end
            local r,c2,why=guarded_u(world,turret,rec,at,8,encode64(now),name)
            if not r then emit({kind='refused',code=c2,reason=why})end
            return r
        end
        if a.id==AI.gatling and(stage==PI.searchStage or stage==PI.alertStage)then
            if now>=(w.repick_pause or 0)and now>=(w.next_repick or 0)and u64(a.raw,AI213.repick)>now then
                w.next_repick=now+PI.repickPeriod*US
                local list=M.candidates(world,turret,a)
                if list and#list>0 and due_now(AI213.repick,'repick_time')then
                    w.repick_streak=(w.repick_streak or 0)+1
                    w.repicks=(w.repicks or 0)+1
                    emit({kind='repick_forced',stage=stage,candidates=#list})
                    if w.repick_streak>=M.REPICK_TRIES then
                        w.repick_streak=0
                        w.repick_pause=now+M.REPICK_PAUSE*US
                    end
                end
            end
        else
            w.repick_streak=0
        end
        if a.id==AI.gatling and stage==PI.aimStage and T and u64(a.raw,AI213.fireCheck)>now then
            local list=M.candidates(world,turret,a)
            local valid=false
            for _,c in ipairs(list or{})do if c.entity==T then valid=true end end
            if valid and due_now(AI213.fireCheck,'fire_check')then
                w.fire_checks=(w.fire_checks or 0)+1
                emit({kind='fire_check_forced',target=T})
            end
        end
    end
    return out
end

------------------------------------------------------------------------------------------- the peer mirror --
-- A Pelican CAS chin gun on a machine that did NOT spawn it (custom multiplayer; runtime/custom_mp_pelican.lua;
-- research peer-messaging "pelicanMirror"): every machine fires its own rounds of that turret from its own data,
-- driven by the replicated trigger, so the host's private configuration shows only on the host. M.mirror_configure
-- gives THIS machine's own copy of the turret the same private presentation, never anything the network writes:
--   * its own ProjectileWeapon copy (the game's copy routine, ownership-free), then one guarded transaction: the copy's
--     projectile (the AP4 round 275, or the standard 148), its rate slot and the frozen Gatling casing (before its first
--     local shot);
--   * its own aim recoil (zero) and spread (WeaponData instance records, never deserialized);
--   * NOT its current RPM entry (re-applied from the host every changed update), its rounds, its trigger, its AI.
-- The rate: every machine fires its own shots on its own cooldown (+8), which each shot reloads with its instance
-- interval (+0xC); the barrel's "CyclingTime" follows the same interval (research peer-messaging "pelicanMirror"
-- cadence pins). The interval is no network field (the projectile weapon's network state is entry +0, the current RPM
-- +4 and +8); the game rewrites it only when the current RPM entry differs from its cached copy (+0x64). The host's own
-- Gatling rate is a plain write of the host's entry, never queued for replication, so a client's entry keeps the host's
-- creation seed (300, or 270 under modifier 0x33) unless a game reset re-sent it. M.mirror_interval therefore holds the
-- interval at 60 / (the Gatling rate x the mission factor x rate_factor) while the entry equals its cached copy and reads
-- either the seed or that Gatling rate (the factor read from it); anything else is never written (M.mirror_cadence logs
-- it).
-- spec = {pelican (this machine's entity), round ('ap4' | 'standard' | 'native' (the chin turret's own round) |
-- 'strafing_run' | 'strafing_run_pattern'), gatling (true), rate_factor (1, 1.5, 2), rpm (a number: the gun's explicit
-- rate, its rate slot in place of the Gatling's), casing ('own': the chin turret's own; else, with gatling, the frozen
-- Gatling casing), spread
-- (mrad or a mode), recoil ('zero' or nil), sound (a catalogue name: its own copy's firing sound, a shot or a loop, in
-- the same transaction when its bank is resident HERE and the turret is quiet; otherwise result.sound.deferred and M.apply_sound
-- later with {mirror = true}), client (the orchestrator's mark)}. Returns a result {writes, verify, verified,
-- projectile, rpm, sound} or nil, code, reason.
local PM=require('hd2runtime/domains/peer_messaging').pelicanMirror
function M.mirror_configure(world,turret,spec,label)
    label=tostring(label or'?')
    spec=spec or{}
    local function refuse(code,reason)
        log(('MIRROR REFUSED (%s): chin turret %s: %s: %s'):format(label,tostring(turret),code,reason))
        return nil,code,reason
    end
    if not world.runtime.native_weapon_copy then return refuse('UNAVAILABLE','this Runtime adapter cannot call game functions')end
    if not scheduler.in_update()then return refuse('NOT_GAME_THREAD','only inside the Runtime\'s own update')end
    local ok,why=M.prove(world)
    if not ok then return refuse('UNSUPPORTED_BUILD',tostring(why))end
    for _,pin in ipairs(PM.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return refuse('UNSUPPORTED_BUILD',('game+%X changed (%s)'):format(pin.rva,pin.label))
        end
    end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return refuse('NOT_IN_MISSION','in a mission only')end
    local mp=require('hd2runtime/runtime/multiplayer')
    local hcode,hwhy=mp.host_guard(game,spec.client==true,'a client mirrors only inside the client-write proof')
    if game.host~=true and hcode then return refuse(hcode,hwhy)end
    -- Exactly the published turret: a chin turret, a network copy here (not created here), attached to the published
    -- Pelican (its attachable link is the Pelican's unit link).
    if world_module.entity_type(world,turret)~=PM.chinResource then return refuse('NOT_A_CHIN_TURRET','its type is not the chin turret\'s')end
    if world_module.entity_type(world,spec.pelican)~=PM.pelicanResource then
        return refuse('NOT_A_PELICAN','the published Pelican is not a transport Pelican here')
    end
    local _,raw=pelicans.record_address(world,turret)
    if not raw then return refuse('UNAVAILABLE','the chin turret\'s world record is unreadable')end
    if b.u32(raw,0x14)%2==1 then return refuse('CREATED_HERE','this machine created that turret: it is configured by its owner')end
    local att,handle=pelicans.attachable(world,turret),pelicans.handle(world,spec.pelican)
    if not(att and handle and handle.link and handle.link~=0 and att.link==handle.link)then
        return refuse('NOT_ATTACHED','the chin turret is not attached to the published Pelican here')
    end
    local w=pelicans.weapon_config(world,turret)
    if not(w and w.path=='magazine'and w.magazine and not w.magazine.pattern)then
        return refuse('TURRET_UNEXPECTED','its weapon is not a magazine weapon without a pattern')
    end
    if w.copy then return refuse('ALREADY_CONFIGURED','it already has its own ProjectileWeapon record')end
    local pok,resident=pcall(core_assets.state,world.runtime,gatling.asset_dependency().package)
    if not(pok and resident=='resident')then return refuse('ASSET_UNAVAILABLE','the Gatling Sentry\'s package is not resident')end
    -- The firing sound (a catalogue name, canonical from here; the chin turret's own is none): its pins; its bank
    -- resident here, else deferred (M.apply_sound once it is); quiet.
    local sound,nwhy=M.sound_name(spec.sound)
    if sound==false then return refuse('INVALID',nwhy)end
    local sounding
    if sound~=nil then
        local sok,swhy=sound_proven(world)
        if not sok then return refuse('UNSUPPORTED_BUILD',swhy)end
        local package,_,sreason=M.sound_resident(world,sound)
        if package then
            sounding=sound_precheck(world,turret,sound)
            sounding.package=package
            sounding.deferred=sounding.retry
        else
            sounding={name=sound,applied=false,deferred=true,reason='ASSET_UNAVAILABLE: '..tostring(sreason)}
        end
        if not sounding.wanted then
            log(('MIRROR SOUND %s (%s): chin turret %d: %s'):format(sounding.deferred and'DEFERRED'or'NOT APPLIED',label,
                turret,sounding.reason))
        end
    end
    local projectile=M.AP4.standard.projectile
    if spec.round=='native'then
        projectile=M.FROZEN.chin.projectile
    elseif spec.round=='ap4'then
        local dependency=M.ap_dependency()
        local aok,ares=pcall(core_assets.state,world.runtime,dependency and dependency.package)
        local A,id=M.AP4,M.projectile_identity(world,M.AP4.projectile)
        if dependency and aok and ares=='resident'and id and id.type==A.projectile and id.damage==A.damage
            and id.velocity==A.velocity and id.mass==A.mass then projectile=A.projectile
        else
            log(('MIRROR (%s): the AP4 round is not resident or not as catalogued here: the standard round'):format(label))
        end
    elseif spec.round=='strafing_run'or spec.round=='strafing_run_pattern'then
        -- The Eagle Strafing Run's HE round on this machine's own copy. Its pattern is the host's own magazine copy, never
        -- made here (a magazine copy on a machine that does not own the turret is not researched): every round of this
        -- machine's copy is the HE round.
        local S=M.STRAFING
        local dependency=M.strafing_dependency()
        local sok,sres=pcall(core_assets.state,world.runtime,dependency and dependency.package)
        local id=M.projectile_identity(world,S.projectile)
        if dependency and sok and sres=='resident'and id and id.type==S.projectile and id.damage==S.damage
            and id.velocity==S.velocity and id.mass==S.mass then projectile=S.projectile
            if spec.round=='strafing_run_pattern'then
                log(('MIRROR (%s): the Strafing Run pattern is the host\'s own magazine: every round of this machine\'s '
                    ..'copy is the HE round'):format(label))
            end
        else
            log(('MIRROR (%s): the Strafing Run round is not resident or not as catalogued here: the standard round')
                :format(label))
        end
    end
    local ref=M.FROZEN
    local factor=spec.rate_factor or 1
    if not M.RATE_FACTORS[factor]then return refuse('INVALID','rate_factor must be 1, 1.5 or 2')end
    if spec.rpm~=nil and not(type(spec.rpm)=='number'and spec.rpm>=30 and spec.rpm<=3000 and factor==1)then
        return refuse('INVALID','rpm must be 30..3000, without a rate_factor')
    end
    local slot_rpm=b.value(b.encode(spec.rpm or ref.rpm*factor,'f32'),0,'f32')
    local casing={before=M.casing_state(world,turret,CHIN),applied=false}
    if spec.gatling and spec.casing~='own'then
        local c=casing.before
        if not c then casing.reason='its casing is unreadable'
        elseif c.from~='type'then casing.reason='it already resolves its own record'
        elseif c.cached~=0 then casing.reason='it has fired here already: its casing effect #'..c.cached..' is kept'
        elseif c.nodes_raw~=ref.casing.nodes or ref.casing.nodes~=ref.chin.casing.nodes then
            casing.reason='its fire effects use other nodes than the frozen Gatling casing\'s'
        elseif c.particles~=ref.chin.casing.particles or c.parameters~=ref.chin.casing.parameters then
            casing.reason='its casing is not its type\'s'
        else casing.wanted=true end
        if not casing.wanted then log(('MIRROR CASING NOT APPLIED (%s): chin turret %d: %s'):format(label,turret,casing.reason))end
    end
    local runtime=world.runtime
    local PW=TW.projectileWeapon
    local pw=world.view.pointer(world.game+PW.global)
    local count=pw and world.view.read(pw+PW.copyCount,4)
    local capacity=pw and world.view.read(pw+G.copyCapacity,4)
    if not(count and capacity and b.u32(count,0)+1<b.u32(capacity,0))then
        return refuse('NO_CAPACITY','no room for a per-instance ProjectileWeapon copy')
    end
    local record=pelicans.record_address(world,turret)
    local before=gatling.shared(world)
    metrics.count('pelican_weapon.native_calls')
    runtime.native_weapon_copy(world.game+G.copy.rva,pw,record)
    local ci=pelicans.index_of(world,pw,map_at(PW.copies),turret)
    local copies=ci and world.view.pointer(pw+PW.copyRecords)
    local copy_at=copies and copies~=0 and copies+ci*PW.copyStride
    local copy=copy_at and world.view.read(copy_at,CS.effectsEnd)
    if not copy then return refuse('COPY_FAILED','no per-instance ProjectileWeapon copy after the call')end
    local copy_owner=pelicans.owner_of(world,copy_at,PW.copyStride)
    if not copy_owner then return refuse('NOT_PRIVATE','the copy is not in private read-write memory')end
    if casing.wanted and copy:sub(CS.particles+1,CS.particles+8)~=ref.chin.casing.particles then
        casing.wanted=nil;casing.reason='the copy does not hold the chin turret\'s casing'
    end
    local identity={component='ProjectileWeapon',component_type='native',unique_owner=true,owner_count=1}
    local function change(name,at,desired)
        return {label='mirror.turret.'..turret..'.'..name,owner=copy_owner,offset=copy_at+at-copy_owner.base,
            expected=copy:sub(at+1,at+#desired),desired=desired,before=copy:sub(at+1,at+#desired),already_desired=false,
            identity=identity,chain={}}
    end
    local plan={snapshots={{owner=copy_owner,offset=copy_at-copy_owner.base,bytes=copy}},
        changes={change('copy.projectile',PW.projectileType,u32(projectile))}}
    if spec.gatling then plan.changes[#plan.changes+1]=change('copy.rate_slot',PW.rpmSlots+4,b.encode(slot_rpm,'f32'))end
    if casing.wanted then
        plan.changes[#plan.changes+1]=change('copy.casing',CS.particles,ref.casing.particles)
        for k=0,CS.parametersSize-4,4 do
            plan.changes[#plan.changes+1]=change('copy.casing_parameter'..(k/4+1),CS.parameters+k,
                ref.casing.parameters:sub(k+1,k+4))
        end
    end
    -- The firing sound, in the same transaction: its own fresh copy's +0xED and +0x104 and its own instance +0x38.
    if sounding and sounding.wanted then
        local st=M.sound_state(world,turret,CHIN)
        local splan,why,retry
        if st then splan,why,retry=sound_plan(world,turret,sound,st,'mirror.turret.')else why='its firing sound is unreadable'end
        if splan then
            for _,snap in ipairs(splan.snapshots)do plan.snapshots[#plan.snapshots+1]=snap end
            for _,c in ipairs(splan.changes)do plan.changes[#plan.changes+1]=c end
            sounding.shared_before=sound_shared(world,sound)
        else
            sounding.wanted,sounding.reason,sounding.retry,sounding.deferred=nil,why,retry,retry
            log(('MIRROR SOUND %s (%s): chin turret %d: %s'):format(retry and'DEFERRED'or'NOT APPLIED',label,turret,why))
        end
    end
    local report=transaction.apply(runtime,plan)
    metrics.count('pelican_weapon.transactions')
    if report.status~='APPLIED'then return refuse('GUARD_REJECTED','the copy writes were refused: '..tostring(report.reason))end
    mirrored[turret]=true
    local result={turret=turret,projectile=projectile,writes=report.writes,verify={},casing=casing,sound=sounding}
    if sounding and sounding.wanted then
        sounding.applied,sounding.after=sound_verify(world,turret,sound)
        sounding.shared=sounding.shared_before~=nil and sounding.shared_before==sound_shared(world,sound)
        result.verify.sound=sounding.applied
        result.verify.sound_shared=sounding.shared
    end
    if spec.recoil=='zero'then
        result.recoil=M.configure_recoil(world,turret,label,'zero')
        result.verify.recoil=result.recoil.applied
        result.writes=result.writes+(result.recoil.writes or 0)
    end
    if spec.spread then
        result.spread=M.configure_spread(world,turret,label,spec.spread)
        result.verify.spread=result.spread.applied
        result.writes=result.writes+(result.spread.writes or 0)
    end
    local again=pelicans.weapon_config(world,turret)
    result.verify.projectile=again~=nil and again.copy~=nil and again.copy.projectileType==projectile
    if casing.wanted then
        casing.after=M.casing_state(world,turret,CHIN)
        casing.applied=casing.after~=nil and casing.after.from=='copy'and casing.after.particles==ref.casing.particles
        result.verify.casing=casing.applied
    end
    result.verify.shared=gatling.shared_same(before,gatling.shared(world))
    local verified=true
    for _,v in pairs(result.verify)do if v~=true then verified=false end end
    result.verified=verified
    result.rate_factor=factor
    result.rpm=spec.rpm
    log(('MIRROR APPLIED (%s): chin turret %d (a network copy here): its own copy names projectile %d%s%s%s%s; %d writes; '
        ..'shared definitions unchanged %s; verified %s; not written: its current RPM, rounds, trigger and AI (the '
        ..'host\'s)'):format(label,turret,projectile,spec.gatling and(', rate slot %.0f'):format(slot_rpm)or'',
        casing.wanted and(', casing '..tostring(casing.applied))or'',result.spread and(', spread '
        ..tostring(result.spread.applied))or'',sounding and(sounding.deferred and(', sound '..sounding.name
        ..' deferred')or sound_text(sounding))or'',result.writes,tostring(result.verify.shared),tostring(verified)))
    return result
end
-- A mirrored turret's local fire state, read-only (research peer-messaging "pelicanMirror": instanceInterval,
-- instanceCachedRpm, cadence): {at (its instance record), entry (its current RPM entry: the host's replicated value),
-- cached (+0x64), interval (+0xC), cooldown (+8), trigger (+1, replicated), firing (+0), decision (+0x10: the update's
-- local fire decision), shots (+0x3C: local shots of this trigger hold), created_here (its world record +0x14 bit 0)};
-- with extra: rounds (its magazine entry) and its AI record's behaviour and stage (the owner's AI does not run here).
-- Nothing is written. Returns the state, or nil and why.
function M.mirror_cadence(world,turret,extra)
    local PW,C=TW.projectileWeapon,PM.cadence
    local w=pelicans.weapon_config(world,turret)
    if not(w and w.index)then return nil,'its projectile weapon is unreadable'end
    local pw=world.view.pointer(world.game+PW.global)
    local instances=pw and world.view.pointer(pw+PW.instances)
    local at=instances and instances~=0 and instances+w.index*PW.instanceStride
    local inst=at and world.view.read(at,PM.instanceCachedRpm+4)
    if not inst then return nil,'its instance record is unreadable'end
    local _,raw=pelicans.record_address(world,turret)
    local s={at=at,entry=w.currentRpm,cached=f32(inst,PM.instanceCachedRpm),interval=f32(inst,PM.instanceInterval),
        cooldown=f32(inst,C.cooldown),trigger=inst:byte(C.trigger+1),firing=inst:byte(C.firing+1),
        decision=inst:byte(C.decision+1),shots=b.u32(inst,C.shots),created_here=raw and b.u32(raw,0x14)%2==1,
        raw=inst:sub(PM.instanceInterval+1,PM.instanceInterval+4)}
    if extra then
        local a=M.ammo_state(world,turret,CHIN)
        local ai=M.ai_state(world,turret)
        s.rounds=a and a.rounds
        s.behaviour,s.stage=ai and ai.id,ai and ai.stage
    end
    return s
end
-- The cadence this machine wants for a turret whose current RPM entry reads entry: the frozen Gatling rate x the mission
-- factor x rate_factor, the factor read from the entry, which must be either the chin turret's creation seed (its type's
-- rate x 1 or x the rate seed factor: the host's own write never replicates) or that Gatling rate itself (a game reset
-- re-sent the host's). rpm (the gun's explicit rate) replaces the Gatling rate x rate_factor. Returns rpm, interval,
-- basis ('seed' or 'gatling': the host's rate), factor; or nil.
-- Live r5 (2026-10-05): the client's replicated entry read 299.96, not the chin turret's 300 seed: the old 1e-4 match
-- classified it 'unknown' on every update, so its interval stayed the game's 60/299.96 = 0.2000 s (about 300 RPM). A
-- seed or Gatling-rate entry is now recognised within M.RATE_TOLERANCE (relative); the factors are 10% apart.
M.RATE_TOLERANCE=0.01
function M.mirror_expected(entry,rate_factor,explicit)
    local F=M.FROZEN
    if not(entry and entry>0)then return nil end
    local function single(v)return b.value(b.encode(v,'f32'),0,'f32')end
    for _,f in ipairs({1,D.rateSeed.factor})do
        local rpm=explicit and single(single(explicit)*f)or single(F.rpm*f*(rate_factor or 1))
        local basis
        if math.abs(entry/F.chin.rpm/f-1)<=M.RATE_TOLERANCE then basis='seed'
        elseif math.abs(entry/rpm-1)<=M.RATE_TOLERANCE then basis='gatling'end
        if basis then return rpm,single(60/rpm),basis,f end
    end
    return nil
end
-- Every Runtime update while a mirrored turret lives: its instance interval (+0xC, local presentation state: the
-- cooldown every local shot reloads, the barrel's CyclingTime) at M.mirror_expected's interval, only while its current
-- RPM entry equals its cached copy (+0x64), so the game leaves the interval alone. Never on a turret created here (the
-- host's own: configured by its owner), never anything the network writes (the entry, the trigger, the rounds), never
-- a game call: one guarded 4-byte write of this turret's own instance record, read back. Returns {kind, code, reason,
-- state (M.mirror_cadence), rpm, want, basis, from, to}:
--   'held' (written, read back), 'steady' (already the wanted interval: nothing to write), 'pending' (its entry
--   differs from its cached copy: the game rewrites the interval this update; nothing written), 'unknown' (its entry is
--   neither the seed nor the Gatling rate: nothing written), 'refused' (code: UNAVAILABLE, NOT_GAME_THREAD,
--   CREATED_HERE, NOT_PRIVATE, GUARD_REJECTED, READBACK).
function M.mirror_interval(world,turret,rate_factor,rpm_explicit)
    local PW=TW.projectileWeapon
    local function refused(code,reason,s)return {kind='refused',code=code,reason=reason,state=s}end
    if not scheduler.in_update()then return refused('NOT_GAME_THREAD','only inside the Runtime\'s own update')end
    local s,why=M.mirror_cadence(world,turret)
    if not s then return refused('UNAVAILABLE',why)end
    if s.created_here==nil then return refused('UNAVAILABLE','its world record is unreadable',s)end
    if s.created_here then return refused('CREATED_HERE','this machine created that turret: its owner configures it',s)end
    if not(s.entry and s.entry>0 and s.cached and s.interval)then return refused('UNAVAILABLE','its rate is unreadable',s)end
    local rpm,want,basis,factor=M.mirror_expected(s.entry,rate_factor,rpm_explicit)
    local out={state=s,rpm=rpm,want=want,basis=basis,factor=factor}
    if s.cached~=s.entry then
        out.kind,out.reason='pending','its current RPM entry differs from its cached copy: the game rewrites the interval'
        return out
    end
    if not rpm then
        out.kind,out.code='unknown','UNKNOWN_RATE'
        out.reason=('its current RPM entry %.2f is neither the chin turret\'s seed nor the Gatling rate'):format(s.entry)
        return out
    end
    if s.interval==want then out.kind='steady';return out end
    local owner=pelicans.owner_of(world,s.at,PW.instanceStride)
    if not owner then return refused('NOT_PRIVATE','its instance record is not private memory',s)end
    local current=s.raw
    local offset=s.at+PM.instanceInterval-owner.base
    local report=transaction.apply(world.runtime,{snapshots={{owner=owner,offset=offset,bytes=current}},
        changes={{label='mirror.turret.'..turret..'.interval',owner=owner,offset=offset,expected=current,
            desired=b.encode(want,'f32'),before=current,already_desired=false,identity={component='ProjectileWeapon',
            component_type='native',unique_owner=true,owner_count=1},chain={}}}})
    metrics.count('pelican_weapon.transactions')
    if report.status~='APPLIED'then return refused('GUARD_REJECTED',tostring(report.reason),s)end
    local again=world.view.read(s.at+PM.instanceInterval,4)
    if not(again and f32(again,0)==want)then
        return refused('READBACK',('its interval reads %s after the write'):format(tostring(again and f32(again,0))),s)
    end
    out.kind,out.from,out.to=('held'),s.interval,want
    return out
end
function M.reset()configured={};gate=nil;ap_gate=nil;strafing_gate=nil;aim_proven=nil;idle_proven=nil;switched={};watches={};refills={};quiet={};sound_gates={};mirrored={}end
return M
