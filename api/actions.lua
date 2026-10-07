-- Gameplay actions for event scripts: hd2.actions and hd2.explosions (docs/event-scripting.md#gameplay-actions).
--
-- An action is something a mod asks the game to do from a callback, a timer or a keybind. Every action:
-- * belongs to the calling mod (runtime/events.lua M.owner), which names it in logs and causes;
-- * records a cause (the event it reacted to) and is refused past MAX_CAUSE_DEPTH mod-caused links;
-- * fails closed: an unproven target, a missing proof or a wrong game state refuses with a code and a reason, and
--   nothing is guessed or faked by editing shared definitions.
local events=require('hd2runtime/runtime/events')
local handles=require('hd2runtime/runtime/handles')
local world_module=require('hd2runtime/runtime/event_world')
local assets_api=require('hd2runtime/api/assets')
local core_assets=require('hd2runtime/core/assets')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local M={}

-- Explosion requests per mod: a burst of BURST, refilled at REFILL per second. It stops a chain reaction (an
-- explosion kills an enemy whose death requests another explosion) that no cause can trace: the game does not say
-- which explosion killed an entity.
M.EXPLOSION_BURST=6
M.EXPLOSION_REFILL=1
M.ASSET_TIMEOUT=90
-- Projectiles: a weapon's burst; each also counts as a shot in the owner's statistics.
M.PROJECTILE_BURST=12
M.PROJECTILE_REFILL=4
-- Status requests per mod, and per target (the game keeps at most 32 status records per entity).
M.STATUS_BURST=10
M.STATUS_REFILL=5
M.STATUS_PER_TARGET_BURST=4
M.STATUS_PER_TARGET_REFILL=2
M.STATUS_MAX_BUILDUP=1000

-------------------------------------------------------------------------------------------------- actions --
local Action={};Action.__index=Action
function Action:describe()
    return {kind=self.kind,owner=self.owner,status=self.status,code=self.code,reason=self.reason,
        explosion=self.explosion,projectile=self.projectile,effect=self.effect,type=self.type,
        position=self.position and self.position:copy()or nil,mission=self.mission,limb=self.limb,zone=self.zone,
        damage=self.damage,amount=self.amount,healed=self.healed,velocity=self.velocity and self.velocity:copy()or nil,
        after=self.after and self.after:copy()or nil}
end
-- True once the game accepted the request (the explosion is queued for this frame).
function Action:requested()return self.status=='requested'end
function Action:cancel()
    if self.status=='waiting_for_assets'then self.status='cancelled';self.reason='cancelled by the mod'end
    return self
end
local function new_action(kind,owner)
    return setmetatable({kind=kind,owner=owner,status='pending'},Action)
end
local function refuse(action,code,reason)
    action.status,action.code,action.reason='refused',code,reason
    events.emit_log(action.kind..' ('..action.owner..') refused: '..code..': '..reason)
    metrics.count('actions.refused')
    return action
end

------------------------------------------------------------------------------------------------------ heal --
-- Heal the local player through the game's own heal (clamped to maximum health). Returns the amount requested
-- after Runtime's clamp, or nil and the reason. See HD2PlayerHandle:heal.
function M.heal(amount,opts)
    local explicit=opts and opts.owner
    local owner=events.owner(explicit,2)
    local player=handles.local_player()
    if not player then return nil,'no local player'end
    local applied,why=player:heal(amount,{owner=owner})
    return applied,why
end

------------------------------------------------------------------------------------------------ explosions --
local explosions={}
local buckets={}
local natives=require('hd2runtime/domains/event_natives')
local verified={}   -- explosion type -> weapon, for the types the research matched in the game's settings table
for _,item in ipairs(natives.explosion.weapons)do verified[item.type]=item.weapon end
-- Named explosions: the type is a code literal of the entity behavior that requests it (Runtime re-proves the literal
-- with every other event pin). 'Hellbomb' is the NUX-223 Hellbomb detonation.
local named={}
for _,item in ipairs(natives.explosion.named or{})do named[item.name:lower()]=item;verified[item.type]=item.name end
named['hellbomb']=named['nux-223 hellbomb']
named['portable hellbomb']=named['b-100 portable hellbomb']
local function take_token(owner,kind,burst,refill)
    local key=kind and(kind..':'..owner)or owner
    burst,refill=burst or M.EXPLOSION_BURST,refill or M.EXPLOSION_REFILL
    local now=events.state.now
    local bucket=buckets[key]
    if not bucket then bucket={tokens=burst,at=now};buckets[key]=bucket end
    bucket.tokens=math.min(burst,bucket.tokens+(now-bucket.at)*refill)
    bucket.at=now
    if bucket.tokens<1 then return false end
    bucket.tokens=bucket.tokens-1
    return true
end

-- The catalogued explosion of a player weapon (its impact explosion, else its expiry explosion) as a typed handle,
-- or nil and the reason. The same handle hd2.weapon(name):attack('primary'):projectile():terminal_action(phase)
-- :explosion() returns.
function explosions.of(weapon)
    local hd2=require('hd2runtime/api/hd2')
    local last
    for _,phase in ipairs({'impact','expiry'})do
        local ok,handle=pcall(function()
            return hd2.weapon(weapon):attack('primary'):projectile():terminal_action(phase):explosion()
        end)
        if ok and handle then return handle end
        last=handle
    end
    return nil,'no catalogued explosion for '..tostring(weapon)..' ('..tostring(last):gsub('^[^%s:]+:%d+: ','')..')'
end

-- Validates an explosion target: {name, type, dependency} or nil, code, reason. The reviewed spawn set (the named
-- explosions, the catalogued weapon explosions and their typed handles) needs no acknowledgement; any other catalogued
-- explosion (hd2.explosions.list(); api/explosion_catalogue.lua) needs opts.allow_unverified_effect, its type proven
-- against the game's settings table and a known package. Raw explosion ids are refused.
local catalogue_api=require('hd2runtime/api/explosion_catalogue')
local resolve
local function resolve_catalogue(entry,id,opts)
    local legacy=entry.legacy
    if legacy then
        -- A reviewed explosion by its catalogue name resolves exactly as by its reviewed name.
        local target,code,reason=resolve(legacy.name)
        if target then target.catalogue=id end
        return target,code,reason
    end
    if not entry.spawn then
        return nil,'ASSET_UNKNOWN','no package is known that ships the effect of '..id..', so it cannot be requested'
    end
    if not(type(opts)=='table'and opts.allow_unverified_effect==true)then
        return nil,'UNVERIFIED_EXPLOSION',id..' is outside the reviewed spawn set (hd2.explosions.list({reviewed_spawn = '
            ..'true})): requesting it needs allow_unverified_effect = true'
    end
    local dependency=core_assets.dependency(entry.package.key)
    if not dependency then
        return nil,'ASSET_UNKNOWN','the package that holds the '..id..' explosion is not known'
    end
    return {name=id,type=entry.type,dependency=dependency,dependencies={dependency},catalogue=id,
        mission=entry.package.mission==true or nil}
end
function resolve(explosion,opts)
    local item=type(explosion)=='string'and named[explosion:lower()]
    if item then
        local dependency=core_assets.dependency('explosion/'..item.name)
        if not dependency then
            return nil,'ASSET_UNKNOWN','the package that holds the '..item.name..' explosion is not known'
        end
        -- An objective's explosion (the Cyborg Production Unit's): its sound ships in a second objective package.
        local list={dependency}
        if item.soundPackage then
            list[2]=core_assets.dependency('explosion/'..item.name..'/sound')
            if not list[2]then
                return nil,'ASSET_UNKNOWN','the package that holds the '..item.name..' explosion\'s sound is not known'
            end
        end
        return {name=item.name,type=item.type,dependency=dependency,dependencies=list,
            objective=item.objective==true or nil}
    end
    if type(explosion)=='string'or catalogue_api.is_handle(explosion)then
        local entry,id=catalogue_api.entry(explosion)
        if entry then return resolve_catalogue(entry,id,opts)end
        if catalogue_api.is_handle(explosion)then return nil,'UNKNOWN_EXPLOSION',id end
    end
    if type(explosion)=='string'then
        local handle,why=explosions.of(explosion)
        if not handle then return nil,'UNKNOWN_EXPLOSION',why end
        explosion=handle
    end
    if type(explosion)~='table'or rawget(explosion,'resource')~='player_weapon'or rawget(explosion,'path')~='explosion'
        or type(explosion.describe)~='function'then
        return nil,'UNKNOWN_EXPLOSION','only catalogued explosions are accepted (hd2.explosions.list(), '
            ..'hd2.explosion(name) or hd2.explosions.of(weapon)); raw explosion ids are refused'
    end
    local descriptor=explosion.describe()
    local kind=descriptor and descriptor.explosionType
    if type(kind)~='number'then return nil,'UNKNOWN_EXPLOSION','the explosion handle has no reviewed type'end
    if not verified[kind]then
        return nil,'UNKNOWN_EXPLOSION','explosion type '..kind..' is not one the research matched to the game '
            ..'settings table'
    end
    local key=assets_api.key_for(explosion)
    local dependency=key and core_assets.dependency(key)
    if not dependency then
        return nil,'ASSET_UNKNOWN','the package that holds the '..tostring(explosion.weapon)..' explosion is not '
            ..'known, so its assets cannot be guaranteed loaded'
    end
    return {name=tostring(explosion.weapon),type=kind,dependency=dependency}
end

local MISSION_PACKAGE_REASON='its effect ships in the mission effects package, which is resident in every mission and '
    ..'is never loaded by the Runtime; it is not resident now'
-- Whether every package of a resolved explosion target is resident now (read-only).
function M.explosion_resident(runtime,target)
    for _,dependency in ipairs(target.dependencies or{target.dependency})do
        local ok,state=pcall(core_assets.state,runtime,dependency.package)
        if not(ok and state=='resident')then return false end
    end
    return true
end
-- A named or catalogued explosion's target ({name, type, dependency, dependencies}) or nil, code, reason. Offline.
-- opts.allow_unverified_effect admits a catalogued explosion outside the reviewed spawn set.
function M.explosion_target(explosion,opts)return resolve(explosion,opts)end

-- Every axis is checked by name (a missing one refuses; iterating {x, y, z} would stop at it).
local function finite(v,limit)return type(v)=='number'and v==v and math.abs(v)<=limit end
local function position_of(value)
    if type(value)~='table'then return nil end
    local x,y,z=value.x,value.y,value.z
    if not(finite(x,100000)and finite(y,100000)and finite(z,100000))then return nil end
    return handles.position({x=x,y=y,z=z})
end

-- The game state that allows an explosion now: {world, avatar, peer_lo, peer_hi} or nil, code, reason.
local function authority(action)
    local world,why=world_module.open()
    if not world then return nil,'EXPLOSION_UNAVAILABLE',tostring(why)end
    -- The game's own state decides; the event engine's mission epoch (tracked while the game_state source runs)
    -- additionally refuses a request that waited into another mission.
    local state=world_module.game_state(world)
    if not(state and state.mission)then return nil,'NOT_IN_MISSION','the game is not in a mission'end
    local tracked,epoch=events.mission()
    if tracked and action.mission and epoch~=action.mission then
        return nil,'NOT_IN_MISSION','the mission it was requested in has ended'
    end
    if state.host~=true then
        return nil,'HOST_ONLY','only the host changes enemy health; a client request would be local and overwritten'
    end
    -- The local player's current avatar (the player list decides); in the moment it has just died it is still the one
    -- credited, so a reaction to the local player's death works.
    local avatar,why=handles.local_avatar(world,{include_dead=true})
    if not avatar then
        return nil,'NO_LOCAL_AVATAR','the action is credited to the local player\'s avatar; there is none now ('
            ..tostring(why)..')'
    end
    local lo,hi=world_module.local_peer(world)
    if not lo then return nil,'EXPLOSION_UNAVAILABLE','the local peer id is unreadable'end
    return {world=world,avatar=avatar.id,peer_lo=lo,peer_hi=hi}
end

local function fire(action,target)
    local allowed,code,reason=authority(action)
    if not allowed then return refuse(action,code,reason)end
    local p=action.position
    local ok,why=world_module.explode(allowed.world,{type=target.type,x=p.x,y=p.y,z=p.z,source=allowed.avatar,
        owner=allowed.avatar,peer_lo=allowed.peer_lo,peer_hi=allowed.peer_hi,cause=action.cause})
    if not ok then
        local code_text=tostring(why):match('^([A-Z_]+):')or'EXPLOSION_UNAVAILABLE'
        return refuse(action,code_text,tostring(why):gsub('^[A-Z_]+: ',''))
    end
    action.status='requested'
    metrics.count('actions.explosions')
    events.emit_log('explosion '..target.name..' requested at '..tostring(p)..' by '..action.owner)
    return action
end

-- INTERNAL (the Runtime's custom silos, runtime/custom_silos.lua; not exported to mods: hd2.explosions.spawn stays host
-- only). Requests a catalogued explosion on THIS machine, host or client, where an explosive the game simulates here
-- detonated: the game itself requests an explosive's own blast on every machine from that machine's copy (live
-- 2026-10-07: a client's queue held a host-called silo missile's own detonation, its source the client's copy of the
-- missile), and that local request is what draws and sounds it there; damage stays each machine's own simulation, enemy
-- health the host's. origin = {source, owner, peer_lo, peer_hi}: that detonation's own queue entry (the game's own
-- attribution: the explosive's owner and creditor); without it, or when its entities are gone, the local avatar and
-- peer. In a mission, with every package of the explosion resident now (it never waits: the detonation is now).
-- Returns the requested name, or nil, code, reason.
function M.mirror_explosion(explosion,position,origin)
    local target,code,reason=resolve(explosion)
    if not target then return nil,code,reason end
    local world,why=world_module.open()
    if not world then return nil,'EXPLOSION_UNAVAILABLE',tostring(why)end
    local state=world_module.game_state(world)
    if not(state and state.mission)then return nil,'NOT_IN_MISSION','the game is not in a mission'end
    if not M.explosion_resident(world.runtime,target)then
        return nil,'ASSET_UNAVAILABLE','the '..target.name..' explosion\'s packages are not resident here'
    end
    local p=position_of(position)
    if not p then return nil,'INVALID_POSITION','the position must be {x, y, z} world coordinates'end
    if not take_token('the custom silos','mirror')then
        return nil,'RATE_LIMITED','at most '..M.EXPLOSION_BURST..' mirrored explosions at once'
    end
    local function local_origin()
        local avatar=handles.local_avatar(world,{include_dead=true})
        local lo,hi=world_module.local_peer(world)
        if not(avatar and lo)then return nil end
        return {source=avatar.id,owner=avatar.id,peer_lo=lo,peer_hi=hi,from='this machine\'s player'}
    end
    local o=origin
    if not(o and world_module.entity_exists(world,o.source)==true and world_module.entity_exists(world,o.owner)==true)then
        o=local_origin()
    end
    if not o then return nil,'NO_LOCAL_AVATAR','neither the detonation\'s own entities nor a local avatar exist'end
    local function request(x)
        return world_module.explode(world,{type=target.type,x=p.x,y=p.y,z=p.z,source=x.source,owner=x.owner,
            peer_lo=x.peer_lo,peer_hi=x.peer_hi})
    end
    local ok,err=request(o)
    if not ok and o==origin then
        o=local_origin()
        if o then ok,err=request(o)end
    end
    if not ok then
        return nil,tostring(err):match('^([A-Z_]+):')or'EXPLOSION_UNAVAILABLE',(tostring(err):gsub('^[A-Z_]+: ',''))
    end
    metrics.count('actions.mirrored_explosions')
    events.emit_log(('explosion %s mirrored at %s on this machine (%s: source %d, owner %d, creditor %s)'):format(
        target.name,tostring(p),o.from or'the detonation\'s own attribution',o.source,o.owner,
        world_module.peer_hex(o.peer_lo or 0,o.peer_hi or 0)))
    return target.name
end

-- Request a catalogued explosion at a position: hd2.explosions.spawn(explosion, {position = event.position}).
-- explosion: a named explosion ('Hellbomb' = the NUX-223 Hellbomb, 'B-100 Portable Hellbomb'), a weapon name
-- ('R-36 Eruptor'), a typed explosion handle, or a catalogued explosion (its name from hd2.explosions.list(), or
-- hd2.explosion(name)); one outside the reviewed spawn set needs opts.allow_unverified_effect = true. Host only, during
-- a mission, credited to the local player (source and owner = the local avatar, creditor = the local peer). When the
-- explosion's package is not loaded yet, Runtime loads it through the game's own package system first (status
-- 'waiting_for_assets', then 'requested'); an explosion whose effect ships in the mission effects package is requested
-- only while that package is resident (it always is in a mission). Returns an action handle; a refusal never raises
-- (status 'refused', code, reason).
function explosions.spawn(explosion,opts)
    opts=opts or{}
    local explicit=opts.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    local action=new_action('explosion',owner)
    local _,epoch=events.mission()
    action.mission=epoch
    local target,code,reason=resolve(explosion,opts)
    if not target then return refuse(action,code,reason)end
    action.explosion,action.type=target.name,target.type
    action.position=position_of(opts.position)
    if not action.position then return refuse(action,'INVALID_POSITION','opts.position must be {x, y, z} world coordinates')end
    action.cause=events.action_cause(owner,'explosion')
    if action.cause.depth>events.MAX_CAUSE_DEPTH then
        return refuse(action,'CAUSE_DEPTH','refused to extend a chain of mod-caused actions')
    end
    local allowed
    allowed,code,reason=authority(action)
    if not allowed then return refuse(action,code,reason)end
    if not take_token(owner)then
        return refuse(action,'RATE_LIMITED','at most '..M.EXPLOSION_BURST..' explosions at once and '
            ..M.EXPLOSION_REFILL..' per second per mod')
    end
    local runtime=allowed.world.runtime
    if M.explosion_resident(runtime,target)then return fire(action,target)end
    -- The mission effects package is resident in every mission; the Runtime never loads it (about 300 MB).
    if target.mission then return refuse(action,'ASSET_UNAVAILABLE',MISSION_PACKAGE_REASON)end
    -- Load the explosion's assets first, through the same gate reference swaps use; then request.
    action.status='waiting_for_assets'
    local gate=core_assets.gate(runtime,{id='explosion-'..target.name:gsub('[^%w_%-]','_'),
        asset_dependencies=target.dependencies or{target.dependency},shared=true},events.emit_log)
    local elapsed=0
    local watch={status='waiting'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        if action.status~='waiting_for_assets'then watch.status='complete';return end
        elapsed=elapsed+dt
        local result,why=gate.tick(dt)
        if result=='ready'then
            watch.status='complete'
            fire(action,target)
        elseif result=='failed'or elapsed>M.ASSET_TIMEOUT then
            watch.status='complete'
            refuse(action,'ASSET_UNAVAILABLE',tostring(why or'the explosion assets did not load'))
        end
    end
    scheduler.attach(watch)
    return action
end

-- Load an explosion's assets now (for example when a mission starts) so a later spawn needs no wait. Returns an
-- action handle ('ready', 'waiting_for_assets' or 'refused').
function explosions.prepare(explosion,opts)
    local owner=events.owner(nil,2)
    local action=new_action('explosion_assets',owner)
    local target,code,reason=resolve(explosion,opts)
    if not target then return refuse(action,code,reason)end
    action.explosion,action.type=target.name,target.type
    local world,why=world_module.open()
    if not world then return refuse(action,'EXPLOSION_UNAVAILABLE',tostring(why))end
    if M.explosion_resident(world.runtime,target)then action.status='ready';return action end
    if target.mission then return refuse(action,'ASSET_UNAVAILABLE',MISSION_PACKAGE_REASON)end
    action.status='waiting_for_assets'
    local gate=core_assets.gate(world.runtime,{id='explosion-'..target.name:gsub('[^%w_%-]','_'),
        asset_dependencies=target.dependencies or{target.dependency},shared=true},events.emit_log)
    local watch={status='waiting'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        local result,reason_text=gate.tick(dt)
        if result=='ready'then action.status='ready';watch.status='complete'
        elseif result=='failed'then watch.status='complete';refuse(action,'ASSET_UNAVAILABLE',tostring(reason_text))end
    end
    scheduler.attach(watch)
    return action
end

-- The reviewed spawn set (0.29's hd2.explosions.list()): {name, weapon, source, assets_known, objective}. Named
-- explosions come first (source 'behavior', weapon nil; objective = true when its effect and sound ship in objective
-- packages, e.g. the Cyborg Production Unit's: two packages of about 300 MB), then weapon explosions (source 'weapon',
-- name = the weapon); each also names its catalogue entry (catalogue). Offline; no game reads.
function explosions.reviewed()
    local by_type={}
    local catalogue=require('hd2runtime/domains/explosion_catalogue')
    for _,id in ipairs(catalogue.order)do
        local entry=catalogue.explosions[id]
        if entry.legacy then by_type[entry.type]=id end
    end
    local result={}
    for _,item in ipairs(natives.explosion.named or{})do
        result[#result+1]={name=item.name,source='behavior',assets_known=resolve(item.name)~=nil,
            objective=item.objective==true or nil,catalogue=by_type[item.type]}
    end
    for _,item in ipairs(natives.explosion.weapons)do
        local handle=explosions.of(item.weapon)
        local key=handle and assets_api.key_for(handle)
        result[#result+1]={name=item.weapon,weapon=item.weapon,source='weapon',
            assets_known=key and core_assets.dependency(key)~=nil or false,catalogue=by_type[item.type]}
    end
    return result
end
-- Every catalogued explosion (api/explosion_catalogue.lua; docs/explosions.md): {name, label, family, evidence,
-- shared, owners, package_known, mission_package, payload, spawn, reviewed_spawn, legacy_name, stats}, filtered by
-- {family, owner, search, shared, payload, spawn, package_known, reviewed_spawn}. No raw ids. Offline.
explosions.list=catalogue_api.list
-- One catalogued explosion in full: the list entry plus its owners, package and editable fields; nil and the reason.
explosions.describe=catalogue_api.describe
M.explosions=explosions

------------------------------------------------------------------------------------------------ projectiles --
-- hd2.projectiles: the game's own projectile wrapper (research/event-actions-F5FEE03DCFDB.json). A projectile is named
-- by the weapon that fires it (its primary attack's projectile, else its first catalogued one).
local projectiles={}
local PJ=natives.projectile
local projectile_by_weapon={}
for _,item in ipairs(PJ and PJ.types or{})do
    local key=item.weapon:lower()
    if not projectile_by_weapon[key]or item.role=='primary'then projectile_by_weapon[key]=item end
end
-- A projectile's unit and effects are generated into its weapon's own loadout package (the same package a
-- projectile reference swap loads).
local function projectile_dependency(weapon)
    return core_assets.dependency('player_weapon/'..weapon)or core_assets.dependency('support_weapon/'..weapon)
end
local function resolve_projectile(name)
    if type(name)~='string'then
        return nil,'UNKNOWN_PROJECTILE','a projectile is named by its weapon (hd2.projectiles.list()); raw ids are refused'
    end
    local item=projectile_by_weapon[name:lower()]
    if not item then return nil,'UNKNOWN_PROJECTILE','no catalogued projectile for '..name end
    local dependency=projectile_dependency(item.weapon)
    if not dependency then
        return nil,'ASSET_UNKNOWN','the package that holds the '..item.weapon..' projectile is not known'
    end
    return {name=item.weapon,role=item.role,type=item.type,dependency=dependency}
end
local function unit_direction(value)
    if type(value)~='table'then return nil end
    local x,y,z=value.x,value.y,value.z
    if not(finite(x,1e6)and finite(y,1e6)and finite(z,1e6))then return nil end
    local length=math.sqrt(x*x+y*y+z*z)
    if length<1e-6 then return nil end
    return {x=x/length,y=y/length,z=z/length}
end
-- Loads a target's packages (target.dependencies, else target.dependency) through the asset gate, then calls
-- fire(action, target); 'waiting_for_assets' meanwhile.
local function after_assets(action,target,runtime,fire_now)
    local dependencies=target.dependencies or{target.dependency}
    local resident=true
    for _,dependency in ipairs(dependencies)do
        local ok,state=pcall(core_assets.state,runtime,dependency.package)
        if not(ok and state=='resident')then resident=false;break end
    end
    if resident then return fire_now(action,target)end
    action.status='waiting_for_assets'
    local gate=core_assets.gate(runtime,{id=action.kind..'-'..target.name:gsub('[^%w_%-]','_'),
        asset_dependencies=dependencies,shared=true},events.emit_log)
    local elapsed=0
    local watch={status='waiting'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        if action.status~='waiting_for_assets'then watch.status='complete';return end
        elapsed=elapsed+dt
        local result,why=gate.tick(dt)
        if result=='ready'then
            watch.status='complete'
            fire_now(action,target)
        elseif result=='failed'or elapsed>M.ASSET_TIMEOUT then
            watch.status='complete'
            refuse(action,'ASSET_UNAVAILABLE',tostring(why or'the assets did not load'))
        end
    end
    scheduler.attach(watch)
    return action
end
local function fire_projectile(action,target)
    local allowed,code,reason=authority(action)
    if not allowed then return refuse(action,code,reason)end
    local p,d=action.position,action.direction
    local ok,why=world_module.projectile(allowed.world,{type=target.type,x=p.x,y=p.y,z=p.z,dx=d.x,dy=d.y,dz=d.z,
        entity=allowed.avatar})
    if not ok then
        local code_text=tostring(why):match('^([A-Z_]+):')or'PROJECTILE_UNAVAILABLE'
        return refuse(action,code_text,(tostring(why):gsub('^[A-Z_]+: ','')))
    end
    action.status='requested'
    metrics.count('actions.projectiles')
    events.emit_log('projectile '..target.name..' fired from '..tostring(p)..' by '..action.owner)
    return action
end
-- Fire a catalogued weapon projectile: hd2.projectiles.spawn('R-36 Eruptor', {position = p, direction = d}).
-- The local player's avatar fires it (source, owner and credit), like an AI shot of the game's own. Host only,
-- during a mission; its package is loaded first when needed ('waiting_for_assets', then 'requested'). opts.firer
-- may name the local player's handle; any other firer is refused. Returns an action handle; a refusal never raises.
function projectiles.spawn(name,opts)
    opts=opts or{}
    local explicit=opts.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    local action=new_action('projectile',owner)
    local _,epoch=events.mission()
    action.mission=epoch
    local target,code,reason=resolve_projectile(name)
    if not target then return refuse(action,code,reason)end
    action.projectile,action.type=target.name,target.type
    action.position=position_of(opts.position)
    if not action.position then return refuse(action,'INVALID_POSITION','opts.position must be {x, y, z} world coordinates')end
    action.direction=unit_direction(opts.direction)
    if not action.direction then
        return refuse(action,'INVALID_DIRECTION','opts.direction must be a non-zero {x, y, z} vector')
    end
    if opts.firer~=nil then
        local mine=handles.local_player()
        if not(mine and type(opts.firer)=='table'and opts.firer.id==mine.id)then
            return refuse(action,'FIRER_UNSUPPORTED','projectiles are fired by the local player only')
        end
    end
    action.cause=events.action_cause(owner,'projectile')
    if action.cause.depth>events.MAX_CAUSE_DEPTH then
        return refuse(action,'CAUSE_DEPTH','refused to extend a chain of mod-caused actions')
    end
    local allowed
    allowed,code,reason=authority(action)
    if not allowed then return refuse(action,code,reason)end
    if not take_token(owner,'projectile',M.PROJECTILE_BURST,M.PROJECTILE_REFILL)then
        return refuse(action,'RATE_LIMITED','at most '..M.PROJECTILE_BURST..' projectiles at once and '
            ..M.PROJECTILE_REFILL..' per second per mod')
    end
    return after_assets(action,target,allowed.world.runtime,fire_projectile)
end
-- Load a projectile's assets now so a later spawn needs no wait. Returns an action handle ('ready',
-- 'waiting_for_assets' or 'refused').
function projectiles.prepare(name)
    local owner=events.owner(nil,2)
    local action=new_action('projectile_assets',owner)
    local target,code,reason=resolve_projectile(name)
    if not target then return refuse(action,code,reason)end
    action.projectile,action.type=target.name,target.type
    local world,why=world_module.open()
    if not world then return refuse(action,'PROJECTILE_UNAVAILABLE',tostring(why))end
    return after_assets(action,target,world.runtime,function(a)a.status='ready';return a end)
end
-- Every catalogued weapon projectile: {weapon, role, type, assets_known}. Offline; no game reads.
function projectiles.list()
    local result={}
    for _,item in ipairs(PJ and PJ.types or{})do
        result[#result+1]={weapon=item.weapon,role=item.role,type=item.type,
            assets_known=projectile_dependency(item.weapon)~=nil}
    end
    return result
end
M.projectiles=projectiles

-------------------------------------------------------------------------------------------- custom projectiles --
-- Runtime-owned custom projectile rows (docs/custom-projectile-rows.md). Infrastructure only: not exported by
-- api/hd2.lua (a development proof calls it). A definition (runtime/custom_projectiles.lua) is fired like a catalogued
-- projectile (host only, in a mission, fired and credited by the local player, its packages loaded first, the same
-- rate limit) but through the game's SpawnProjectile with the definition's Runtime-owned row.
local custom_projectiles=require('hd2runtime/runtime/custom_projectiles')
local function fire_custom(action,target)
    local allowed,code,reason=authority(action)
    if not allowed then return refuse(action,code,reason)end
    local definition=target.definition
    local p,d=action.position,action.direction
    local result,why,report=world_module.spawn_projectile_row(allowed.world,{row=definition.row.address,
        base_type=definition.base.type,x=p.x,y=p.y,z=p.z,dx=d.x,dy=d.y,dz=d.z,source=allowed.avatar,
        owner=allowed.avatar,peer_lo=allowed.peer_lo,peer_hi=allowed.peer_hi})
    if not result then
        local code_text=tostring(why):match('^([A-Z_]+):')or'CUSTOM_PROJECTILE_UNAVAILABLE'
        action.report=report
        return refuse(action,code_text,(tostring(why):gsub('^[A-Z_]+: ','')))
    end
    action.status='requested'
    action.slot,action.report=result.slot,result.report
    -- The vanilla base row is compared with the bytes read when the definition was built (Runtime never writes it).
    action.base_unchanged=result.base==definition.base_row
    metrics.count('actions.custom_projectiles')
    events.emit_log(custom_projectiles.line(definition,result.report)..' native spawn result=slot '..tostring(result.slot)
        ..' vanilla base row '..(action.base_unchanged and'unchanged'or'CHANGED since the definition')..' fired from '
        ..tostring(p)..' by '..action.owner)
    return action
end
-- Fires a custom projectile definition (its id or the definition): M.spawn_custom_projectile(id, {position = p,
-- direction = d}). Returns an action handle; a refusal never raises (status 'refused', code, reason).
function M.spawn_custom_projectile(id,opts)
    opts=opts or{}
    local explicit=opts.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    local action=new_action('custom_projectile',owner)
    local _,epoch=events.mission()
    action.mission=epoch
    local definition=type(id)=='table'and custom_projectiles.get(id.id)==id and id or custom_projectiles.get(id)
    if not definition then
        return refuse(action,'UNKNOWN_CUSTOM_PROJECTILE','no custom projectile definition '..tostring(type(id)=='table'
            and id.id or id))
    end
    action.projectile,action.type=definition.id,definition.base.type
    action.position=position_of(opts.position)
    if not action.position then return refuse(action,'INVALID_POSITION','opts.position must be {x, y, z} world coordinates')end
    action.direction=unit_direction(opts.direction)
    if not action.direction then
        return refuse(action,'INVALID_DIRECTION','opts.direction must be a non-zero {x, y, z} vector')
    end
    action.cause=events.action_cause(owner,'projectile')
    if action.cause.depth>events.MAX_CAUSE_DEPTH then
        return refuse(action,'CAUSE_DEPTH','refused to extend a chain of mod-caused actions')
    end
    local allowed,code,reason=authority(action)
    if not allowed then return refuse(action,code,reason)end
    if not take_token(owner,'projectile',M.PROJECTILE_BURST,M.PROJECTILE_REFILL)then
        return refuse(action,'RATE_LIMITED','at most '..M.PROJECTILE_BURST..' projectiles at once and '
            ..M.PROJECTILE_REFILL..' per second per mod')
    end
    return after_assets(action,{name=definition.id,definition=definition,dependencies=definition.dependencies},
        allowed.world.runtime,fire_custom)
end

-------------------------------------------------------------------------------- weapon projectile replacement --
-- Weapon projectile replacement (runtime/projectile_replacement.lua, docs/custom-projectile-rows.md#weapon-projectile-
-- replacement). Not exported by api/hd2.lua (a development proof calls it). The mod swaps a weapon to fire a carrier
-- through the ordinary guarded projectile swap; this binds the carrier to a custom projectile definition, so each
-- carrier the local player fires is replaced by the definition. Host only; the definition's packages load first.
local projectile_replacement=require('hd2runtime/runtime/projectile_replacement')
local rows_domain=require('hd2runtime/domains/projectile_rows')
local b=require('hd2runtime/core/bytes')
local function bind_now(action,target)
    local world,why=world_module.open()
    if not world then return refuse(action,'REPLACEMENT_UNAVAILABLE',tostring(why))end
    local state=world_module.game_state(world)
    if not state or state.host~=true then
        return refuse(action,'HOST_ONLY','a custom projectile only exists on the machine that spawns it; only the '
            ..'host decides hits')
    end
    action.binding=projectile_replacement.bind({carrier=target.carrier,definition=target.definition,
        weapon=target.weapon,unreplaced=target.unreplaced,detail_logs=target.detail_logs,sources=target.sources,
        credit=target.credit,context=target.context,attribute=target.attribute,owner=action.owner,
        runtime=world.runtime})
    action.status='bound'
    local observed=''
    if target.unreplaced and target.unreplaced.role=='suppressed'then
        observed=('; the native %s projectile (type %d) must not appear: every sighting is a suppression failure')
            :format(target.unreplaced.name,target.unreplaced.type)
    elseif target.unreplaced then
        observed=('; %s (type %d) shots are counted and never replaced'):format(target.unreplaced.name,
            target.unreplaced.type)
    end
    events.emit_log(('projectile replacement: %s (type %d) shots%s are replaced by %s, for %s%s%s'):format(
        target.carrier.name,target.carrier.type,target.weapon and(' from the '..target.weapon)or target.context and
        (' from '..target.context)or'',custom_projectiles.line(target.definition),action.owner,target.credit==
        'local_or_none'and'; credited to the local peer or to no peer'or'',observed))
    return action
end
-- Replaces each carrier shot the local player fires by a custom projectile definition (its id or the definition):
-- M.replace_projectiles(id, {carrier = <projectile output id or weapon name>, weapon = <only shots from this
-- catalogued weapon (optional)>, unreplaced = <the weapon's other projectile output, counted and logged as not
-- replaced (optional)>, detail_logs = <shots of each kind logged in full (optional; math.huge for all)>, source =
-- <a projectile output: only shots whose source entity is that output's owner (its catalogued entity type), for hosts
-- without a catalogued weapon name such as mounted weapons (optional)>, suppressed = <the host's native projectile
-- output, which the carrier swap replaces: every sighting from the source is logged as a suppression failure
-- (optional; not with unreplaced)>, credit = 'local' (default) or 'local_or_none' (also shots credited to no peer),
-- attribute = true (log each shot's creditor, owner, source and latency)}). The carrier must be a vanilla projectile
-- without impact or expiry explosion. Returns an action handle: 'bound', 'waiting_for_assets' or 'refused' (code,
-- reason); a refusal never raises.
function M.replace_projectiles(id,opts)
    opts=opts or{}
    local explicit=opts.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    local action=new_action('projectile_replacement',owner)
    local definition=type(id)=='table'and custom_projectiles.get(id.id)==id and id or custom_projectiles.get(id)
    if not definition then
        return refuse(action,'UNKNOWN_CUSTOM_PROJECTILE','no custom projectile definition '..tostring(type(id)=='table'
            and id.id or id))
    end
    action.projectile=definition.id
    local carrier,code,reason=custom_projectiles.output(opts.carrier,false)
    if not carrier then return refuse(action,code,reason)end
    action.type=carrier.type
    if opts.weapon~=nil and type(opts.weapon)~='string'then
        return refuse(action,'INVALID_WEAPON','opts.weapon must be a catalogued weapon name')
    end
    local unreplaced
    if opts.unreplaced~=nil then
        local output
        output,code,reason=custom_projectiles.output(opts.unreplaced,false)
        if not output then return refuse(action,code,reason)end
        if output.type==carrier.type then
            return refuse(action,'INVALID_UNREPLACED','opts.unreplaced must be another projectile than the carrier')
        end
        unreplaced={type=output.type,name=output.weapon or output.output}
    end
    local detail_logs=opts.detail_logs
    if detail_logs~=nil and(type(detail_logs)~='number'or detail_logs<0 or detail_logs~=detail_logs)then
        return refuse(action,'INVALID_DETAIL_LOGS','opts.detail_logs must be a count (math.huge for every shot)')
    end
    if opts.suppressed~=nil then
        if unreplaced then
            return refuse(action,'INVALID_UNREPLACED','give opts.unreplaced or opts.suppressed, not both')
        end
        local output
        output,code,reason=custom_projectiles.output(opts.suppressed,false)
        if not output then return refuse(action,code,reason)end
        if output.type==carrier.type then
            return refuse(action,'INVALID_UNREPLACED','opts.suppressed must be another projectile than the carrier')
        end
        unreplaced={type=output.type,name=output.weapon or output.output,role='suppressed'}
    end
    -- The source identity: the owner entity type of a catalogued output (attack output resource).
    local sources,context
    if opts.source~=nil then
        local host
        host,code,reason=custom_projectiles.output(opts.source,false)
        if not host then return refuse(action,code,reason)end
        local resource=host.catalog.resource
        if type(resource)~='string'or not resource:match('^0x%x+$')or#resource~=18 then
            return refuse(action,'UNKNOWN_SOURCE',host.output..' has no catalogued owner entity type')
        end
        sources={[resource:sub(3):upper()]=host.weapon or host.output}
        context=('%s (%s, native type %d)'):format(host.weapon or host.output,host.output,host.type)
    end
    if opts.credit~=nil and opts.credit~='local'and opts.credit~='local_or_none'then
        return refuse(action,'INVALID_CREDIT','opts.credit must be "local" or "local_or_none"')
    end
    local world,why=world_module.open()
    if not world then return refuse(action,'REPLACEMENT_UNAVAILABLE',tostring(why))end
    local proven
    proven,why=world_module.prove_projectile_pool(world)
    if not proven then return refuse(action,'REPLACEMENT_UNAVAILABLE',why)end
    -- A slot is skipped only while its previous projectile's explosion is pending: a carrier without explosions is
    -- never skipped into, so every carrier slot read was spawned since the previous update.
    local row=world_module.projectile_row(world,carrier.type)
    if not row then return refuse(action,'UNKNOWN_PROJECTILE','the vanilla row of '..carrier.output..' does not resolve')end
    for name,offset in pairs(rows_domain.pool.explosions)do
        if b.u32(row,offset)~=0 then
            return refuse(action,'CARRIER_HAS_EXPLOSION',carrier.output..' has an '..name..' explosion; a carrier must '
                ..'have none')
        end
    end
    return after_assets(action,{name=definition.id,definition=definition,dependencies=definition.dependencies,
        carrier={type=carrier.type,name=carrier.weapon or carrier.output},weapon=opts.weapon,unreplaced=unreplaced,
        detail_logs=detail_logs,sources=sources,context=context,credit=opts.credit,attribute=opts.attribute==true},
        world.runtime,bind_now)
end
-- Ends the replacement of a carrier (a projectile output id or weapon name). true when it was bound.
function M.stop_replacing_projectiles(carrier)
    local output=custom_projectiles.output(carrier,false)
    return output~=nil and projectile_replacement.unbind(output.type)
end

---------------------------------------------------------------------------------------------- status effects --
-- hd2.status: the game's own status request queue. Only statuses a player weapon already applies through its
-- damage are offered (natives.status.allowlist). The amount is BUILDUP: each request adds it, and the status starts
-- when the target's buildup reaches its susceptibility threshold; strength and duration come from the status
-- itself (applying again refreshes the duration, it does not stack).
local status_effects={}
local ST=natives.status
local status_by_key={}
do
    local names={}
    for _,item in ipairs(ST and ST.allowlist or{})do
        status_by_key[item.id]=item
        local name=item.name:lower():gsub('_',' ')
        names[name]=(names[name]or 0)+1
    end
    -- Display names only where they are unique ('Gas' names two statuses; use 'gas' or 'gas_2').
    for _,item in ipairs(ST and ST.allowlist or{})do
        local name=item.name:lower():gsub('_',' ')
        if names[name]==1 and not status_by_key[name]then status_by_key[name]=item end
    end
end
local function resolve_status(name)
    if type(name)~='string'then
        return nil,'UNKNOWN_STATUS','a status is named by its id (hd2.status.list()); raw ids are refused'
    end
    local item=status_by_key[name:lower()]or status_by_key[name:lower():gsub(' ','_')]
    if not item then
        return nil,'UNKNOWN_STATUS',name..' is not an offered status (only statuses a player weapon applies)'
    end
    return item
end
local target_buckets={}
local function take_target_token(target)
    local now=events.state.now
    local bucket=target_buckets[target]
    if not bucket then bucket={tokens=M.STATUS_PER_TARGET_BURST,at=now};target_buckets[target]=bucket end
    bucket.tokens=math.min(M.STATUS_PER_TARGET_BURST,bucket.tokens+(now-bucket.at)*M.STATUS_PER_TARGET_REFILL)
    bucket.at=now
    if bucket.tokens<1 then return false end
    bucket.tokens=bucket.tokens-1
    return true
end
-- Apply a status to an entity: hd2.status.apply(event.entity, 'fire', {buildup = 100}). The local player's avatar is
-- the instigator. Host only, during a mission. The game then checks that the target can have that status and
-- routes the request to the target's owner. opts.buildup: 0 < buildup <= 1000 (default 100, the value the game's own
-- stun requests use). Returns an action handle ('requested' or 'refused').
function status_effects.apply(entity,name,opts)
    opts=opts or{}
    local explicit=opts.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    local action=new_action('status',owner)
    local _,epoch=events.mission()
    action.mission=epoch
    local item,code,reason=resolve_status(name)
    if not item then return refuse(action,code,reason)end
    action.effect,action.type=item.id,item.type
    if opts.strength~=nil then
        return refuse(action,'INVALID_OPTION','strength and duration come from the status itself; pass buildup')
    end
    for key in pairs(opts)do
        if key~='buildup'and key~='owner'then return refuse(action,'INVALID_OPTION','unsupported option: '..tostring(key))end
    end
    local buildup=opts.buildup==nil and 100 or opts.buildup
    if type(buildup)~='number'or buildup~=buildup or buildup<=0 or buildup>M.STATUS_MAX_BUILDUP then
        return refuse(action,'INVALID_AMOUNT','buildup must be above 0 and at most '..M.STATUS_MAX_BUILDUP)
    end
    local id=type(entity)=='table'and tonumber(entity.id)
    if not id or id<=0 or id%1~=0 then return refuse(action,'INVALID_TARGET','the target must be an entity handle')end
    action.target=id
    action.cause=events.action_cause(owner,'status')
    if action.cause.depth>events.MAX_CAUSE_DEPTH then
        return refuse(action,'CAUSE_DEPTH','refused to extend a chain of mod-caused actions')
    end
    local allowed
    allowed,code,reason=authority(action)
    if not allowed then return refuse(action,code,reason)end
    if not take_token(owner,'status',M.STATUS_BURST,M.STATUS_REFILL)then
        return refuse(action,'RATE_LIMITED','at most '..M.STATUS_BURST..' status requests at once and '
            ..M.STATUS_REFILL..' per second per mod')
    end
    if not take_target_token(id)then
        return refuse(action,'RATE_LIMITED','at most '..M.STATUS_PER_TARGET_BURST..' status requests at once and '
            ..M.STATUS_PER_TARGET_REFILL..' per second per target')
    end
    local ok,why=world_module.status(allowed.world,{type=item.type,target=id,buildup=buildup,instigator=allowed.avatar})
    if not ok then
        local code_text=tostring(why):match('^([A-Z_]+):')or'STATUS_UNAVAILABLE'
        return refuse(action,code_text,(tostring(why):gsub('^[A-Z_]+: ','')))
    end
    action.status='requested'
    metrics.count('actions.status_requests')
    events.emit_log('status '..item.id..' requested on entity '..id..' (buildup '..buildup..') by '..owner)
    return action
end
-- Every offered status: {id, name, family, type}. Offline; no game reads.
function status_effects.list()
    local result={}
    for _,item in ipairs(ST and ST.allowlist or{})do
        result[#result+1]={id=item.id,name=item.name,family=item.family,type=item.type}
    end
    return result
end
M.status_effects=status_effects

------------------------------------------------------------------------------------------------------ injure --
-- hd2.actions.injure(player, limb, damage): the game's own limb injury of the LOCAL player's avatar
-- (research/player-injury-path-F5FEE03DCFDB.json). The damage is queued at the limb's physics actor through the game's
-- damage request, with the template of the VG-70 Variable's own self-damage to its shooter's right arm; the game's
-- drain applies it later in the frame like any hit on that limb: the limb zone loses that much health (an injured
-- limb at 0) and main health loses the zone's share. Each machine injures only the avatar it owns; no host needed.
-- Limbs: head, chest, l_hand, r_hand, l_knee, r_knee. damage: a whole number from 1 to the limb zone's health (head
-- 85, chest 60, hands 35, knees 45).
M.INJURE_BURST=12
M.INJURE_REFILL=10
function M.injure(player,limb,damage,opts)
    opts=type(opts)=='table'and opts or{}
    local explicit=opts.owner
    local owner=events.owner(type(explicit)=='string'and#explicit>0 and#explicit<=128 and explicit or nil,2)
    local action=new_action('injure',owner)
    local _,epoch=events.mission()
    action.mission,action.limb,action.damage=epoch,limb,damage
    if explicit~=nil and(type(explicit)~='string'or#explicit==0 or#explicit>128)then
        return refuse(action,'INVALID_OPTION','owner must be a mod id string')
    end
    for key in pairs(opts)do
        if key~='owner'then return refuse(action,'INVALID_OPTION','unsupported option: '..tostring(key))end
    end
    if getmetatable(player)~=handles.Player then
        return refuse(action,'INVALID_TARGET','the target must be a player handle (hd2.local_player())')
    end
    if not player.is_local then
        return refuse(action,'NOT_LOCAL_PLAYER','only the local player can be injured (each machine injures the '
            ..'avatar it owns)')
    end
    local item=world_module.injury_limb(limb)
    if not item then
        local names={}
        for _,known in ipairs(world_module.injury_limbs())do names[#names+1]=known.name end
        return refuse(action,'UNKNOWN_LIMB',tostring(limb)..' is not a limb; use '..table.concat(names,', '))
    end
    action.zone=item.zone
    if type(damage)~='number'or damage~=damage or damage%1~=0 or damage<1 or damage>item.maxDamage then
        return refuse(action,'INVALID_AMOUNT',item.name..' damage must be a whole number from 1 to '..item.maxDamage)
    end
    action.cause=events.action_cause(owner,'injure')
    if action.cause.depth>events.MAX_CAUSE_DEPTH then
        return refuse(action,'CAUSE_DEPTH','refused to extend a chain of mod-caused actions')
    end
    local world,why=world_module.open()
    if not world then return refuse(action,'INJURY_UNAVAILABLE',tostring(why))end
    local state=world_module.game_state(world)
    if not(state and state.mission)then return refuse(action,'NOT_IN_MISSION','the game is not in a mission')end
    local tracked,current=events.mission()
    if tracked and action.mission and current~=action.mission then
        return refuse(action,'NOT_IN_MISSION','the mission it was requested in has ended')
    end
    local avatar,reason=handles.local_avatar(world)
    if not avatar then return refuse(action,'NO_LOCAL_AVATAR',tostring(reason))end
    if not take_token(owner,'injure',M.INJURE_BURST,M.INJURE_REFILL)then
        return refuse(action,'RATE_LIMITED','at most '..M.INJURE_BURST..' injuries at once and '..M.INJURE_REFILL
            ..' per second per mod')
    end
    local result,failure=world_module.injure(world,{entity=avatar.id,limb=item.name,damage=damage})
    if not result then
        local code=tostring(failure):match('^([A-Z_]+):')or'INJURY_UNAVAILABLE'
        return refuse(action,code,(tostring(failure):gsub('^[A-Z_]+: ','')))
    end
    action.status,action.target='requested',avatar.id
    action.zone_health,action.injured_before=result.zone_health,result.injured_before
    metrics.count('actions.injuries')
    events.emit_log('injury '..item.name..' ('..item.zone..') '..damage..' requested on the local avatar '..avatar.id
        ..' by '..owner)
    return action
end
-- The common gate of the local-avatar actions (injure has its own, older copy): the action, the world and the local
-- avatar, or the refused action. `check(action)` validates the arguments first and returns code, reason to refuse.
local function avatar_action(kind,player,opts,check,burst,refill,depth_level)
    opts=type(opts)=='table'and opts or{}
    local explicit=opts.owner
    local owner=events.owner(type(explicit)=='string'and#explicit>0 and#explicit<=128 and explicit or nil,
        depth_level or 3)
    local action=new_action(kind,owner)
    local _,epoch=events.mission()
    action.mission=epoch
    if explicit~=nil and(type(explicit)~='string'or#explicit==0 or#explicit>128)then
        return nil,refuse(action,'INVALID_OPTION','owner must be a mod id string')
    end
    for key in pairs(opts)do
        if key~='owner'then return nil,refuse(action,'INVALID_OPTION','unsupported option: '..tostring(key))end
    end
    if getmetatable(player)~=handles.Player then
        return nil,refuse(action,'INVALID_TARGET','the target must be a player handle (hd2.local_player())')
    end
    if not player.is_local then
        return nil,refuse(action,'NOT_LOCAL_PLAYER','only the local player\'s own avatar (each machine acts on the '
            ..'avatar it owns)')
    end
    local code,reason=check(action)
    if code then return nil,refuse(action,code,reason)end
    action.cause=events.action_cause(owner,kind)
    if action.cause.depth>events.MAX_CAUSE_DEPTH then
        return nil,refuse(action,'CAUSE_DEPTH','refused to extend a chain of mod-caused actions')
    end
    local world,why=world_module.open()
    if not world then return nil,refuse(action,kind:upper()..'_UNAVAILABLE',tostring(why))end
    local state=world_module.game_state(world)
    if not(state and state.mission)then return nil,refuse(action,'NOT_IN_MISSION','the game is not in a mission')end
    local tracked,current=events.mission()
    if tracked and action.mission and current~=action.mission then
        return nil,refuse(action,'NOT_IN_MISSION','the mission it was requested in has ended')
    end
    local avatar,why2=handles.local_avatar(world)
    if not avatar then return nil,refuse(action,'NO_LOCAL_AVATAR',tostring(why2))end
    if not take_token(owner,kind,burst,refill)then
        return nil,refuse(action,'RATE_LIMITED','at most '..burst..' at once and '..refill..' per second per mod')
    end
    return action,world,avatar
end
local function refused_by(action,failure,default)
    local code=tostring(failure):match('^([A-Z_]+):')or default
    return refuse(action,code,(tostring(failure):gsub('^[A-Z_]+: ','')))
end

-- hd2.actions.heal_limb(player, limb[, amount]): the game's own one-zone restore (RestoreZone, research/player-avatar-
-- actions-F5FEE03DCFDB.json) on the LOCAL player's avatar: the limb's zone returns to its full health and an injured
-- limb is healed. Main health is not touched. The game has no partial one-zone heal: amount is 'full' (the default)
-- or a whole number that covers what the limb is missing (anything smaller is refused, PARTIAL_UNSUPPORTED).
M.LIMB_HEAL_BURST=6
M.LIMB_HEAL_REFILL=2
function M.heal_limb(player,limb,amount,opts)
    local item
    local action,world,avatar=avatar_action('heal_limb',player,opts,function(a)
        a.limb,a.amount=limb,amount
        item=world_module.injury_limb(limb)
        if not item then return 'UNKNOWN_LIMB',tostring(limb)..' is not a limb; use head, chest, l_hand, r_hand, '
            ..'l_knee, r_knee'end
        a.zone=item.zone
        if amount~=nil and amount~='full'and(type(amount)~='number'or amount~=amount or amount%1~=0 or amount<1
                or amount>item.maxDamage)then
            return 'INVALID_AMOUNT',item.name..' amount must be \'full\' or a whole number from 1 to '..item.maxDamage
        end
    end,M.LIMB_HEAL_BURST,M.LIMB_HEAL_REFILL)
    if not action then return world end
    if type(amount)=='number'then
        local zone=world_module.limb_state(world,avatar.id,item.name)
        if not zone then return refuse(action,'LIMB_HEAL_UNAVAILABLE','the limb is unreadable')end
        local missing=math.max(0,zone.max-math.max(zone.health,0))
        if amount<missing then
            return refuse(action,'PARTIAL_UNSUPPORTED',item.name..' is missing '..missing..'; the game restores a limb '
                ..'only to full (pass \'full\' or at least '..missing..')')
        end
    end
    local result,failure=world_module.heal_limb(world,{entity=avatar.id,limb=item.name})
    if not result then return refused_by(action,failure,'LIMB_HEAL_UNAVAILABLE')end
    action.status,action.target='requested',avatar.id
    action.zone_health,action.injured_before=result.zone_health,result.injured_before
    metrics.count('actions.limb_heals')
    events.emit_log('limb heal '..item.name..' ('..item.zone..') requested on the local avatar '..avatar.id..' by '
        ..action.owner)
    return action
end
-- hd2.actions.heal_limbs(player): heal_limb('full') for all six limbs, one request (one rate-limit token).
function M.heal_limbs(player,opts)
    local action,world,avatar=avatar_action('heal_limbs',player,opts,function()end,M.LIMB_HEAL_BURST,
        M.LIMB_HEAL_REFILL)
    if not action then return world end
    action.healed={}
    for _,item in ipairs(world_module.injury_limbs())do
        local result,failure=world_module.heal_limb(world,{entity=avatar.id,limb=item.name})
        if not result then return refused_by(action,failure,'LIMB_HEAL_UNAVAILABLE')end
        action.healed[#action.healed+1]=item.name
    end
    action.status,action.target='requested',avatar.id
    metrics.count('actions.limb_heals')
    events.emit_log('limb heal (all limbs) requested on the local avatar '..avatar.id..' by '..action.owner)
    return action
end

-- hd2.actions.add_velocity(player, {x, y, z}): the game's own MotionComponent velocity setter (SetVelocity,
-- research/player-avatar-actions-F5FEE03DCFDB.json) on the LOCAL player's avatar: its current velocity plus the
-- change, world space in m/s (+Z up). The change is at most MAX_VELOCITY_CHANGE (25 m/s, about four times the game's
-- own avatar launch of 5.8 m/s forward and 3.3 m/s up) and the result at most MAX_SPEED (50 m/s). What ground
-- locomotion does with it the next frame is not proven: an upward change that lifts the avatar is the reliable case.
M.VELOCITY_BURST=4
M.VELOCITY_REFILL=2
M.MAX_VELOCITY_CHANGE=25
M.MAX_SPEED=50
function M.add_velocity(player,change,opts)
    local delta
    local action,world,avatar=avatar_action('add_velocity',player,opts,function(a)
        if type(change)~='table'then return 'INVALID_VELOCITY','the change is a table {x, y, z} in m/s'end
        local x,y,z=change.x,change.y,change.z
        for _,v in ipairs({x or'',y or'',z or''})do
            if type(v)~='number'or v~=v or math.abs(v)==math.huge then
                return 'INVALID_VELOCITY','x, y and z must be finite numbers (m/s)'
            end
        end
        local size=math.sqrt(x*x+y*y+z*z)
        if size>M.MAX_VELOCITY_CHANGE then
            return 'INVALID_VELOCITY',('the change is %.1f m/s; at most %g'):format(size,M.MAX_VELOCITY_CHANGE)
        end
        if size==0 then return 'INVALID_VELOCITY','the change is zero'end
        delta={x=x,y=y,z=z}
        a.velocity=handles.position(delta)
    end,M.VELOCITY_BURST,M.VELOCITY_REFILL)
    if not action then return world end
    local result,failure=world_module.add_velocity(world,{entity=avatar.id,x=delta.x,y=delta.y,z=delta.z,
        max_speed=M.MAX_SPEED})
    if not result then return refused_by(action,failure,'VELOCITY_UNAVAILABLE')end
    action.status,action.target='requested',avatar.id
    action.before,action.after=handles.position(result.before),handles.position(result.after)
    metrics.count('actions.velocity_changes')
    events.emit_log(('velocity %s added to the local avatar %d (now %s) by %s'):format(tostring(action.velocity),
        avatar.id,tostring(action.after),action.owner))
    return action
end

-- Every limb hd2.actions.injure accepts: {name, zone, max_damage, affects_main_health}. Offline; no game reads.
function M.limbs()
    local result={}
    for _,item in ipairs(world_module.injury_limbs())do
        result[#result+1]={name=item.name,zone=item.zone,max_damage=item.maxDamage,
            affects_main_health=item.affectsMainHealth}
    end
    return result
end

------------------------------------------------------------------------------------------------------ status --
-- What event scripts can make the game do in this Runtime, and why the rest is not offered.
function M.status()
    return {
        heal={status='available',api='hd2.actions.heal(amount) / player:heal(amount)',
            limits='local player only; alive, not downed; clamped to maximum health'},
        injure={status='available',api='hd2.actions.injure(player, limb, damage) / player:injure(limb, damage)',
            limits='local player only (each machine injures the avatar it owns; no host needed); in a mission; '
                ..'alive, not downed; limbs head, chest, l_hand, r_hand, l_knee, r_knee; damage a whole number up to '
                ..'the limb zone health; '..M.INJURE_BURST..' at once and '..M.INJURE_REFILL..' per second per mod; '
                ..'main health loses the zone share and can down or kill',
            live='not live-tested: the queue, the zones and the VG-70 template are proven offline only'},
        heal_limb={status='available',api='hd2.actions.heal_limb(player, limb[, \'full\']) / '
                ..'hd2.actions.heal_limbs(player)',
            limits='local player only (no host needed); in a mission; alive, not downed; the game restores one limb '
                ..'to full (no partial limb heal exists); main health unchanged; '..M.LIMB_HEAL_BURST..' at once and '
                ..M.LIMB_HEAL_REFILL..' per second per mod',
            live='not live-tested'},
        add_velocity={status='available',api='hd2.actions.add_velocity(player, {x, y, z})',
            limits='local player only; in a mission; alive, not downed; change at most '..M.MAX_VELOCITY_CHANGE
                ..' m/s, result at most '..M.MAX_SPEED..' m/s; '..M.VELOCITY_BURST..' at once and '
                ..M.VELOCITY_REFILL..' per second per mod; what ground movement does with it is not proven',
            live='not live-tested'},
        definition={status='available',api='mod:value(spec) bound to hd2.ensure',
            limits='changes a shared definition (every user of it), re-applied about half a second later'},
        explosion={status='available',api='hd2.explosions.spawn(name, weapon or handle, {position=...})',
            limits='every catalogued explosion (hd2.explosions.list({spawn = true})) with a known package; outside the '
                ..'reviewed set (the named Hellbomb explosions and catalogued weapon explosions) with '
                ..'allow_unverified_effect; host only; in a mission; credited to the '
                ..'local player; '..M.EXPLOSION_BURST..' at once and '..M.EXPLOSION_REFILL..' per second per mod; '
                ..'other players may not see the effect',
            live='live-proven on host for the NUX-223 Hellbomb only; other explosions and what other players see are '
                ..'not live-tested'},
        projectile={status='available',api='hd2.projectiles.spawn(weapon, {position=..., direction=...})',
            limits='catalogued weapon projectiles with a known package; host only; in a mission; fired and credited '
                ..'by the local player (each counts as a shot); '..M.PROJECTILE_BURST..' at once and '
                ..M.PROJECTILE_REFILL..' per second per mod; other players may not see it',
            live='live-proven on host for the R-36 Eruptor only; other projectiles and what other players see are '
                ..'not live-tested'},
        status_effect={status='available',api='hd2.status.apply(entity, status, {buildup=...})',
            limits='statuses a player weapon applies; buildup, not strength; host only; in a mission; '
                ..M.STATUS_BURST..' at once and '..M.STATUS_REFILL..' per second per mod, '
                ..M.STATUS_PER_TARGET_BURST..' at once per target',
            live='live-proven on host for fire only; other statuses and what other players see are not live-tested'},
        pelican=require('hd2runtime/api/pelican').status(),
        spawn_entity={status='blocked',reason='the generic spawn (game.dll 0xFDC140) takes spawn parameters and '
            ..'network replication that are not proven; only the transport Pelican is spawned (hd2.pelican)'},
    }
end
function M.reset_for_tests()
    for key in pairs(buckets)do buckets[key]=nil end
    for key in pairs(target_buckets)do target_buckets[key]=nil end
end
return M
