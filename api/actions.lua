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
        position=self.position and self.position:copy()or nil,mission=self.mission}
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

-- Validates an explosion target: {name, type, dependency} or nil, code, reason. Only catalogued player-weapon
-- explosion handles (hd2.explosions.of or the typed builder chain) are accepted, and only when the package that owns
-- their assets is known.
local function resolve(explosion)
    local item=type(explosion)=='string'and named[explosion:lower()]
    if item then
        local dependency=core_assets.dependency('explosion/'..item.name)
        if not dependency then
            return nil,'ASSET_UNKNOWN','the package that holds the '..item.name..' explosion is not known'
        end
        return {name=item.name,type=item.type,dependency=dependency}
    end
    if type(explosion)=='string'then
        local handle,why=explosions.of(explosion)
        if not handle then return nil,'UNKNOWN_EXPLOSION',why end
        explosion=handle
    end
    if type(explosion)~='table'or rawget(explosion,'resource')~='player_weapon'or rawget(explosion,'path')~='explosion'
        or type(explosion.describe)~='function'then
        return nil,'UNKNOWN_EXPLOSION','only catalogued weapon explosions are accepted (hd2.explosions.of(weapon)); '
            ..'raw explosion ids are refused'
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
    local avatar=handles.local_avatar(world)
    if not avatar then return nil,'NO_LOCAL_AVATAR','the action is credited to the local player\'s avatar; there is none now'end
    local lo,hi=world_module.local_peer(world)
    if not lo then return nil,'EXPLOSION_UNAVAILABLE','the local peer id is unreadable'end
    return {world=world,avatar=avatar.id,peer_lo=lo,peer_hi=hi}
end

local function fire(action,target)
    local allowed,code,reason=authority(action)
    if not allowed then return refuse(action,code,reason)end
    local p=action.position
    local ok,why=world_module.explode(allowed.world,{type=target.type,x=p.x,y=p.y,z=p.z,source=allowed.avatar,
        owner=allowed.avatar,peer_lo=allowed.peer_lo,peer_hi=allowed.peer_hi})
    if not ok then
        local code_text=tostring(why):match('^([A-Z_]+):')or'EXPLOSION_UNAVAILABLE'
        return refuse(action,code_text,tostring(why):gsub('^[A-Z_]+: ',''))
    end
    action.status='requested'
    metrics.count('actions.explosions')
    events.emit_log('explosion '..target.name..' requested at '..tostring(p)..' by '..action.owner)
    return action
end

-- Request a catalogued explosion at a position: hd2.explosions.spawn(explosion, {position = event.position}).
-- explosion: a named explosion ('Hellbomb' = the NUX-223 Hellbomb, 'B-100 Portable Hellbomb'), a weapon name
-- ('R-36 Eruptor') or a typed explosion handle. Host only, during a mission, credited to
-- the local player (source and owner = the local avatar, creditor = the local peer). When the explosion's package
-- is not loaded yet, Runtime loads it through the game's own package system first (status 'waiting_for_assets',
-- then 'requested'). Returns an action handle; a refusal never raises (status 'refused', code, reason).
function explosions.spawn(explosion,opts)
    opts=opts or{}
    local explicit=opts.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    local action=new_action('explosion',owner)
    local _,epoch=events.mission()
    action.mission=epoch
    local target,code,reason=resolve(explosion)
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
    local ok,state=pcall(core_assets.state,runtime,target.dependency.package)
    if ok and state=='resident'then return fire(action,target)end
    -- Load the explosion's assets first, through the same gate reference swaps use; then request.
    action.status='waiting_for_assets'
    local gate=core_assets.gate(runtime,{id='explosion-'..target.name:gsub('[^%w_%-]','_'),
        asset_dependencies={target.dependency}},events.emit_log)
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
function explosions.prepare(explosion)
    local owner=events.owner(nil,2)
    local action=new_action('explosion_assets',owner)
    local target,code,reason=resolve(explosion)
    if not target then return refuse(action,code,reason)end
    action.explosion,action.type=target.name,target.type
    local world,why=world_module.open()
    if not world then return refuse(action,'EXPLOSION_UNAVAILABLE',tostring(why))end
    local ok,state=pcall(core_assets.state,world.runtime,target.dependency.package)
    if ok and state=='resident'then action.status='ready';return action end
    action.status='waiting_for_assets'
    local gate=core_assets.gate(world.runtime,{id='explosion-'..target.name:gsub('[^%w_%-]','_'),
        asset_dependencies={target.dependency}},events.emit_log)
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

-- Every catalogued explosion: {name, weapon, type, source, assets_known}. Named explosions come first (source
-- 'behavior', weapon nil), then weapon explosions (source 'weapon', name = the weapon). Offline; no game reads.
function explosions.list()
    local result={}
    for _,item in ipairs(natives.explosion.named or{})do
        result[#result+1]={name=item.name,type=item.type,source='behavior',
            assets_known=core_assets.dependency('explosion/'..item.name)~=nil}
    end
    for _,item in ipairs(natives.explosion.weapons)do
        local handle=explosions.of(item.weapon)
        local key=handle and assets_api.key_for(handle)
        result[#result+1]={name=item.weapon,weapon=item.weapon,type=item.type,source='weapon',
            assets_known=key and core_assets.dependency(key)~=nil or false}
    end
    return result
end
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
-- Loads a target's package through the asset gate, then calls fire(action, target); 'waiting_for_assets' meanwhile.
local function after_assets(action,target,runtime,fire_now)
    local ok,state=pcall(core_assets.state,runtime,target.dependency.package)
    if ok and state=='resident'then return fire_now(action,target)end
    action.status='waiting_for_assets'
    local gate=core_assets.gate(runtime,{id=action.kind..'-'..target.name:gsub('[^%w_%-]','_'),
        asset_dependencies={target.dependency}},events.emit_log)
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

------------------------------------------------------------------------------------------------------ status --
-- What event scripts can make the game do in this Runtime, and why the rest is not offered.
function M.status()
    return {
        heal={status='available',api='hd2.actions.heal(amount) / player:heal(amount)',
            limits='local player only; alive, not downed; clamped to maximum health'},
        definition={status='available',api='mod:value(spec) bound to hd2.ensure',
            limits='changes a shared definition (every user of it), re-applied about half a second later'},
        explosion={status='available',api='hd2.explosions.spawn(name, weapon or handle, {position=...})',
            limits='the named Hellbomb explosions and catalogued weapon explosions, each with a known package; host '
                ..'only; in a mission; credited to the '
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
        spawn_entity={status='blocked',reason='the generic spawn (game.dll 0xFDC140) takes spawn parameters and '
            ..'network replication that are not proven'},
    }
end
function M.reset_for_tests()
    for key in pairs(buckets)do buckets[key]=nil end
    for key in pairs(target_buckets)do target_buckets[key]=nil end
end
return M
