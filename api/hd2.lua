-- Lazy adapter loading: describing/importing the API never opens process memory.
local factory=require('hd2runtime/api/session')
local log=require('hd2runtime/runtime/log')
local instance
local M={}
-- Support/debugging: the first line a session writes names the Runtime version actually loaded. The version is the
-- packaged copy of VERSION (domains/metadata.lua, generated from schemas/sdk.json and checked against VERSION); the
-- global flag keeps it to one line per Lua state even if this module is required again after package.loaded changes.
do
    -- The startup progress display measures the catalogue's load from here (it starts nothing until work exists).
    pcall(require,'hd2runtime/runtime/init_progress')
    -- Public-matchmaking safety (runtime/matchmaking_safety.lua): starts at load so a Public privacy setting is
    -- corrected before the first lobby is created. Only in the game (its engine Lua API is present); the watch ends
    -- itself on anything but the live process, and it calls nothing unless every pin proves.
    if type(rawget(_G,'stingray'))=='table'then
        pcall(function()require('hd2runtime/runtime/matchmaking_safety').start()end)
        -- The build label in the bottom-left corner aboard the ship (runtime/version_label.lua).
        pcall(function()require('hd2runtime/runtime/version_label').start()end)
        -- The HD2Runtime settings panel on F10 (runtime/runtime_settings.lua): turns its on-screen items off.
        pcall(function()require('hd2runtime/runtime/runtime_settings').start()end)
        -- Synced asset loading (runtime/asset_sync.lua, development): publishes the packages this machine's mods load
        -- and loads the ones a compatible lobby member's mods load. Reads only (one timer) outside a joined lobby.
        pcall(function()require('hd2runtime/runtime/asset_sync').start()end)
    end
    local metadata=require('hd2runtime/domains/metadata')
    if not rawget(_G,'HD2RuntimeStartupLogged')then
        rawset(_G,'HD2RuntimeStartupLogged',metadata.version)
        log.emit('[HD2Runtime] HD2Runtime '..tostring(metadata.version)..' initialized (API '
            ..tostring(metadata.api_version)..')')
    end
end
local function session()
    if not instance then
        local runtime=require('hd2runtime/runtime/live_process_reader')()
        instance=factory.new(runtime,require('hd2runtime/runtime/log').emit)
    end
    return instance
end
for _,name in ipairs({'read','enumerate_primary_weapons'})do
    local method=name
    M[method]=function(...)return session()[method](...)end
end
local metadata=factory.new({},require('hd2runtime/runtime/log').emit)
M.describe=metadata.describe
M.format=metadata.format
function M.observe(request)
    return require('hd2runtime/runtime/scheduler').attach(session().observe(request))
end
function M.map_primary_weapons(request)
    return require('hd2runtime/runtime/scheduler').attach(session().map_primary_weapons(request))
end
function M.capture_snapshot(request)
    return require('hd2runtime/runtime/scheduler').attach(session().capture_snapshot(request))
end
-- Armed capture: waits for `py hd2.py snapshot arm` requests (research tooling; never captures on its own).
function M.snapshot_control(request)
    return require('hd2runtime/runtime/scheduler').attach(session().snapshot_control(request))
end
local function disabled()
    require('hd2runtime/runtime/log').emit('[HD2Runtime] write request rejected: read-only milestone')
    return nil,{code='READ_ONLY_MILESTONE',message='No gameplay writer is included in milestone 1'}
end
-- Export every typed builder (legacy resources plus support_weapon, backpack, and other
-- catalog-backed builders), not only the legacy metadata builder list.
for name in pairs(require('hd2runtime/api/target').new(metadata.describe))do M[name]=metadata[name]end
M.fields=metadata.fields;M.enums=metadata.enums
-- hd2.resources: the builder resource constants, and a mod's own custom resources.
local images=require('hd2runtime/runtime/image_resources')
local resources={}
for key,value in pairs(metadata.resources)do resources[key]=value end
-- The calling mod's own image: images/<id>.png in its project, which the SDK build packs into the mod's archive as a
-- complete icon family (docs/custom-images.md). A value for hd2.fields.stratagem.presentation_icon. The handle names
-- the image only; whether it is loaded is checked before each write.
function resources.image(id)return images.handle(id,require('hd2runtime/runtime/events').owner())end
-- The game's own HUD icon of a stratagem or booster (docs/game-icons.md): kind 'stratagem' | 'booster' and its name as
-- the Runtime's catalogues name it ('EXO-45 Patriot Exosuit', 'Vitality Enhancement'). Draw it with d:image like a mod's
-- own image; it is read from the running game (nothing shipped, nothing written) and drawn only while its atlas page is
-- loaded (booster icons are not, during a mission). Returns the handle, or nil, code ('UNKNOWN_KIND' | 'UNKNOWN_ICON')
-- and reason.
function resources.game_icon(kind,name)return require('hd2runtime/runtime/game_icons').handle(kind,name)end
-- The names of every game icon of a kind ('stratagem' | 'booster'), sorted.
function resources.game_icons(kind)return require('hd2runtime/runtime/game_icons').names(kind)end
-- The calling mod's own model: models/<id>.json in its project, which the SDK build derives from its base weapon's unit
-- and packs beside the vanilla resources (docs/custom-models.md). A value for a weapon delivery's model
-- (hd2.custom_stratagem: delivery.family 'weapon'). The handle names the model only; whether it is loaded and exact is
-- checked before it is used.
function resources.model(id)
    return require('hd2runtime/runtime/model_resources').handle(id,require('hd2runtime/runtime/events').owner())
end
M.resources=resources
-- hd2.version is the compatibility version, exactly MAJOR.MINOR.PATCH: SDK wrappers before 0.28 parse nothing else
-- (a prerelease suffix would make every mod they built refuse to start). hd2.version_label is the full version of
-- this build (e.g. 0.30.0), as the startup line and the artifact name show it.
M.version=tostring(metadata.version):match('^(%d+%.%d+%.%d+)')or metadata.version
M.version_label=metadata.version;M.api_version=metadata.api_version
-- Process-wide work counters and worst durations for performance audits.
function M.metrics()return require('hd2runtime/runtime/metrics').snapshot()end
-- Write-conflict counts per ensure (always on) and opt-in sampled timing (docs/diagnostics.md).
local diagnostics=require('hd2runtime/runtime/diagnostics')
M.diagnostics={telemetry=diagnostics.telemetry,write_conflicts=diagnostics.write_conflicts}
-- Per-mod CPU time (runtime/perf_watch.lua; docs/runtime-performance.md "Which mod is slow").
M.diagnostics.performance=require('hd2runtime/runtime/perf_watch').snapshot
-- In-game options (Mod Options Menu). Required at startup with the rest of the API.
local options=require('hd2runtime/api/options')
function M.options(spec)return options.page(spec)end
-- One-shot operations resolve once and cannot follow an option; ensure owns bound values.
local function one_shot(request)
    assert(not options.contains(request),'option-bound values require hd2.ensure')
end
-- Registration isolation. A request that fails validation never writes; it is logged with its id and reason and
-- returned as a rejected handle instead of raising, so one invalid operation cannot abort an addon that registers
-- many independent operations (a ModBuilder export registers one per backing object, in a generated order).
local function operation_id(kind,request)
    if type(request)~='table'then return nil end
    local body=request
    if kind=='ensure'then body=request.patch or request.transaction or request.plan end
    return type(body)=='table'and type(body.id)=='string'and body.id or nil
end
local function rejected(kind,request,why)
    -- Drop the raising chunk's position prefix ('[string "x"]:12: ' or 'name:12: '); the reason follows it.
    local message=tostring(why):gsub('^%[string "[^"]*"%]:%d+: ',''):gsub('^[^%s:]+:%d+: ','')
    -- Runtime reason codes (DORMANT_PROJECTILE_REFERENCE, CONFLICT, ...) may follow a field prefix.
    local code=message:match('%f[%w]([A-Z][A-Z0-9_]*[A-Z0-9]):')or'INVALID_REQUEST'
    local id=operation_id(kind,request)
    log.emit('[HD2Runtime] '..kind..' '..(id or'(no id)')..' rejected: '..message)
    require('hd2runtime/runtime/metrics').count('api.rejected_registrations')
    local handle={kind=kind,id=id,status='rejected',error=message,runs=kind=='ensure'and 0 or nil,
        result={status='REJECTED',code=code,message=message}}
    function handle.tick()end
    function handle.cancel()end
    return handle
end
-- Apply latency is visible: component values are copied into a weapon when the game builds it, so a weapon built
-- before its operation applied keeps the old value until it is rebuilt. Once every operation registered in one
-- burst has settled (applied, rejected, unavailable or failed), one line reports the counts and the elapsed time.
local burst
local SLOW_SETTLE_SECONDS=10   -- a burst at least this slow also logs its slowest operations and their states
local function settled(handle)
    if handle.status=='rejected'or handle.status=='unavailable'or handle.status=='cancelled'
        or handle.status=='complete'or handle.status=='disabled'then return true end
    return handle.runs~=nil and handle.runs>=1
end
local function track(handle)
    if not burst then
        burst={handles={},elapsed=0,waits={},settled_at={}}
        local current=burst
        local watcher={status='waiting',perf_label='startup: tracking registered operations'}
        function watcher.cancel()watcher.status='cancelled'end
        function watcher.tick(dt)
            current.elapsed=current.elapsed+dt
            -- Per operation: the time spent in each state until it settled (logged when the burst was slow).
            local open=false
            for _,h in ipairs(current.handles)do
                if not settled(h)then
                    open=true
                    local w=current.waits[h]
                    if not w then w={};current.waits[h]=w end
                    local state=tostring(h.status)
                    w[state]=(w[state]or 0)+dt
                elseif not current.settled_at[h]then current.settled_at[h]=current.elapsed end
            end
            if open then return end
            local counts={applied=0,rejected=0,other=0}
            for _,h in ipairs(current.handles)do
                local result=h.result and h.result.status
                if h.status=='rejected'then counts.rejected=counts.rejected+1
                elseif result=='APPLIED'or result=='ALREADY_DESIRED'then counts.applied=counts.applied+1
                else counts.other=counts.other+1 end
            end
            log.emit(string.format('[HD2Runtime] %d registered operations settled in %.0f s: %d applied, '
                ..'%d rejected, %d other (see earlier lines)',#current.handles,current.elapsed,counts.applied,
                counts.rejected,counts.other))
            if current.elapsed>=SLOW_SETTLE_SECONDS then
                log.emit(require('hd2runtime/runtime/perf_watch').slowest_operations(current))
            end
            if burst==current then burst=nil end
            watcher.status='complete'
        end
        require('hd2runtime/runtime/scheduler').attach(watcher)
    end
    burst.handles[#burst.handles+1]=handle
    -- runtime/perf_watch.lua: the operation's updates are its mod's (the registering scope), labelled by id.
    handle.perf_owner=handle.perf_owner or require('hd2runtime/runtime/events').owner()
    handle.perf_label=handle.perf_label or(tostring(handle.kind or'operation')..' '..tostring(handle.id))
    -- The startup progress display (runtime/init_progress.lua) counts the same settled() state.
    pcall(function()require('hd2runtime/runtime/init_progress').track('plans',handle,settled)end)
    return handle
end
-- Operation ids name operations in the log and in diagnostics (drift, write conflicts). The same id registered twice
-- by one mod still registers both, with one warning, so an exported project's later operations are never dropped.
local registered_ids={}
local function warn_duplicate(kind,request)
    local id=operation_id(kind,request)
    if not id then return end
    local owner=require('hd2runtime/runtime/events').owner()
    local key=owner..'#'..id
    local seen=registered_ids[key]
    if seen==nil then registered_ids[key]=false;return end
    if seen==false then
        registered_ids[key]=true
        log.emit('[HD2Runtime] '..kind..' '..id..': another operation of '..owner..' already uses this id; give '
            ..'each operation a unique id (logs and diagnostics name operations by id)')
        require('hd2runtime/runtime/metrics').count('api.duplicate_operation_ids')
    end
end
-- Every registration this session, rejected ones included, for hd2.diagnostics.operations(): a validator or a mod can
-- see an operation that was refused or never applied even when the addon kept no handle. The oldest entries are
-- dropped past REGISTRY_LIMIT.
local sdk_compatibility=require('hd2runtime/core/sdk_compatibility')
local REGISTRY_LIMIT=4096
local registry,registry_dropped={},0
local function remember(kind,request,origin,handle)
    if type(handle)~='table'then return handle end
    if #registry>=REGISTRY_LIMIT then table.remove(registry,1);registry_dropped=registry_dropped+1 end
    registry[#registry+1]={kind=kind,id=operation_id(kind,request),origin=origin,handle=handle}
    return handle
end
local function register(kind,module,request,check)
    warn_duplicate(kind,request)
    -- The registering mod and the SDK it declares (core/sdk_compatibility.lua): read once, here, while its wrapper is
    -- on the call stack; every validation of this operation, now and on a later option change, runs as it.
    local origin=sdk_compatibility.origin()
    local function refuse(why)
        sdk_compatibility.discard(origin)
        return remember(kind,request,origin,track(rejected(kind,request,why)))
    end
    if check then
        local valid,why=pcall(sdk_compatibility.with_origin,origin,check,request)
        if not valid then return refuse(why)end
    end
    local ok,adapter=pcall(require,'hd2runtime/runtime/windows_write')
    if not ok then return disabled()end
    pcall(function()require('hd2runtime/runtime/init_progress').start()end)
    local started,watch=pcall(sdk_compatibility.with_origin,origin,function()
        return require(module).start(adapter.create(),log.emit,request)
    end)
    if not started then return refuse(watch)end
    sdk_compatibility.flush(origin,kind,operation_id(kind,request))
    return remember(kind,request,origin,track(require('hd2runtime/runtime/scheduler').attach(watch)))
end
-- A plain copy of every registration: kind, id, mod, the SDK it declares and how that was read, the handle's status,
-- result, code and error, its runs (ensure), and the fields it wrote as a legacy SDK operation.
local function operations()
    local out={}
    for index,item in ipairs(registry)do
        local h,origin=item.handle,item.origin or{}
        local result=type(h.result)=='table'and h.result or{}
        local legacy={}
        for _,use in ipairs(origin.legacy or{})do
            legacy[#legacy+1]={target=use.target,field=use.field:match('([^|]*)$'),acknowledgement=use.acknowledgement,
                since=use.since}
        end
        out[index]={kind=item.kind,id=item.id,mod=origin.mod,sdk=origin.sdk,sdk_source=origin.source,
            status=h.status,result=result.status,code=result.code,error=h.error or result.reason,runs=h.runs,
            legacy=legacy}
    end
    return out,{dropped=registry_dropped}
end
function M.patch(request)return register('patch','hd2runtime/api/patch',request,one_shot)end
function M.transaction(request)return register('transaction','hd2runtime/api/transaction',request,one_shot)end
function M.plan(request)return register('plan','hd2runtime/api/plan',request,one_shot)end
-- Load (through the game's own package system) the assets a semantic target needs; see docs/asset-loading.md.
function M.require_assets(request)
    local ok,adapter=pcall(require,'hd2runtime/runtime/windows_write')
    if not ok then return disabled()end
    return require('hd2runtime/runtime/scheduler').attach(
        require('hd2runtime/api/assets').start(adapter.create(),require('hd2runtime/runtime/log').emit,request))
end
-- Offline: is this target's package dependency known and auto-loadable? (no IDs)
function M.asset_dependency(target)return require('hd2runtime/api/assets').describe(target)end
function M.ensure(request)return register('ensure','hd2runtime/api/ensure',request)end
-- Every registered operation and how it ended so far, legacy SDK operations included (docs/diagnostics.md).
M.diagnostics.operations=operations
-- Every mod's options pages and script values with their current values and the ensures they drive (r51).
M.diagnostics.options=function()return options.list()end
-- Gameplay scripting (docs/events.md): events, timers, keybinds and per-mod contexts. Required at startup with the
-- rest of the API; nothing polls until a mod subscribes, starts a timer or binds a key.
local scripting=require('hd2runtime/api/events')
M.events=scripting.events
M.after=scripting.after
M.every=scripting.every
M.on_frame=scripting.on_frame
M.build=scripting.build
M.store=scripting.store
M.input=scripting.input
M.mod=scripting.mod
M.players=scripting.players
M.game_state=scripting.game_state
M.local_player=scripting.local_player
M.entities=scripting.entities
-- Gameplay actions an event script can perform (api/actions.lua): exported without wrappers so the calling mod is
-- their owner.
local actions=require('hd2runtime/api/actions')
M.actions={heal=actions.heal,injure=actions.injure,limbs=actions.limbs,status=actions.status,
    heal_limb=actions.heal_limb,heal_limbs=actions.heal_limbs,add_velocity=actions.add_velocity}
-- What the local player holds and wears (player:loadout(), :held_weapon(), :backpack(), :ammo()) and the Supply
-- Pack's own self-use (runtime/player_equipment.lua, api/player_equipment.lua; docs/player-equipment.md).
require('hd2runtime/runtime/player_equipment').install(require('hd2runtime/runtime/handles').Player)
M.actions.resupply_from_pack=require('hd2runtime/api/player_equipment').resupply_from_pack
M.explosions=actions.explosions
M.projectiles=actions.projectiles
-- Homing shots (api/homing.lua; docs/projectile-homing.md): the local player's own shots of a weapon turn toward
-- enemies or other players in flight.
local homing=require('hd2runtime/api/homing')
M.projectiles.homing=homing.homing
M.projectiles.homing_list=homing.list
M.projectiles.homing_status=homing.status
-- Per-shot modification (api/shots.lua; docs/projectile-shots.md; DEVELOPMENT, solo): the local player's own shots of a
-- weapon, each shot's own copy (damage, penetration, speed, gravity, drag multipliers); every other weapon stays vanilla.
do
    local shot_api=require('hd2runtime/api/shots')
    M.projectiles.modify_shots=shot_api.modify_shots
    M.projectiles.modify_shots_status=shot_api.status
end
-- How often each enemy type spawns (api/enemy_spawns.lua; docs/enemy-spawns.md): its weight in the game's spawn rosters.
-- hd2.enemies stays callable: hd2.enemies(filter) lists the reviewed enemy / structure names as before.
local enemy_spawns=require('hd2runtime/api/enemy_spawns')
local list_enemies=assert(M.enemies,'the enemy name list builder is missing')
M.enemies=setmetatable({spawn_weight=enemy_spawns.spawn_weight,spawn_list=enemy_spawns.spawn_list,
    spawn_status=enemy_spawns.spawn_status},{__call=function(_,filter)return list_enemies(filter)end})
-- Armor passives (api/player_passives.lua; docs/armor-passives.md): hd2.passives.list() every passive of the game;
-- hd2.player_passives() the local player's, and hd2.player_passives.set (DEVELOPMENT, solo) overrides them;
-- hd2.armor_kits(filter) / hd2.armor_kit(id or name) the game's 411 kits (read-only, offline).
do
    local player_passives=require('hd2runtime/api/player_passives')
    M.passives={list=player_passives.list,find=player_passives.find}
    M.armor_kits,M.armor_kit=player_passives.armor_kits,player_passives.armor_kit
    M.player_passives=setmetatable({set=player_passives.set,status=player_passives.status},
        {__call=function()return player_passives.current()end})
end
M.status=actions.status_effects
-- The game's own transport Pelican, summoned empty at a position and held per instance (api/pelican.lua).
local pelican=require('hd2runtime/api/pelican')
M.pelican={spawn=pelican.spawn,active=pelican.active,status=pelican.status}
-- Armor rating, speed and stamina (api/armor_stats.lua; docs/armor-stats.md; DEVELOPMENT, not live-tested): a kit's
-- piece weights (hd2.armor_stats.kit, guarded fields), the per-weight tables and the damage curve (guarded fields,
-- reviewed executable data), the local player's avatar members (hd2.armor_stats.player, solo). hd2.armor_class is
-- hd2.armor_stats.class.
do
    local armor_stats=require('hd2runtime/api/armor_stats')
    M.armor_stats={kit=armor_stats.kit,kits=armor_stats.kits,class=armor_stats.class,
        damage_curve=armor_stats.damage_curve,player=armor_stats.player}
    M.armor_class=armor_stats.class
end
-- The weapon firing-sound catalogue (api/sounds.lua; docs/weapon-sounds.md), the full sound-event catalogue and
-- playing game sound events (docs/sounds.md).
local sounds=require('hd2runtime/api/sounds')
M.sounds={list=sounds.list,describe=sounds.describe,play=sounds.play,available=sounds.available,
    asset=sounds.asset,name_for=sounds.name_for,parameters=sounds.parameters,switch_groups=sounds.switch_groups,
    state_groups=sounds.state_groups}
-- Mod screen overlays: rectangles and text drawn over the game in the Ui World (api/ui.lua; docs/ui-overlay.md).
local ui=require('hd2runtime/api/ui')
M.ui={overlay=ui.overlay,overlays=ui.overlays,cursor=ui.cursor,colour=ui.colour,color=ui.color,can_draw=ui.can_draw,
    game_fonts=ui.game_fonts,MAX_LAYER=ui.MAX_LAYER,
    DEFAULT_LAYER=ui.DEFAULT_LAYER}
-- Selectable custom stratagems and their spawned instances (development API, solo host; api/custom_stratagem.lua).
local custom_stratagem=require('hd2runtime/api/custom_stratagem')
M.custom_stratagem={register=custom_stratagem.register,status=custom_stratagem.status,
    describe=custom_stratagem.describe,groups=custom_stratagem.groups,
    instance_of=custom_stratagem.instance_of,verbose=custom_stratagem.verbose,focus_next=custom_stratagem.focus_next,
    select_focused=custom_stratagem.select_focused,undo=custom_stratagem.undo,tune=custom_stratagem.tune,
    untune=custom_stratagem.untune}
-- Who an associated autonomous entity's kills credit (development API, solo host; api/ownership.lua).
M.ownership={credit_to_player=require('hd2runtime/api/ownership').credit_to_player}
-- Mods needing a newer HD2Runtime (api/compatibility.lua): their SDK wrapper reports here before failing closed.
local compatibility=require('hd2runtime/api/compatibility')
M.compatibility={require_runtime=compatibility.require_runtime,compare=compatibility.compare,
    parse=compatibility.parse,incompatible=compatibility.incompatible,highest=compatibility.highest,
    status=compatibility.status}
return M
