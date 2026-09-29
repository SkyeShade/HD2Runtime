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

-------------------------------------------------------------------------------------------------- actions --
local Action={};Action.__index=Action
function Action:describe()
    return {kind=self.kind,owner=self.owner,status=self.status,code=self.code,reason=self.reason,
        explosion=self.explosion,type=self.type,position=self.position and self.position:copy()or nil,
        mission=self.mission}
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
local function take_token(owner)
    local now=events.state.now
    local bucket=buckets[owner]
    if not bucket then bucket={tokens=M.EXPLOSION_BURST,at=now};buckets[owner]=bucket end
    bucket.tokens=math.min(M.EXPLOSION_BURST,bucket.tokens+(now-bucket.at)*M.EXPLOSION_REFILL)
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

local function position_of(value)
    if type(value)~='table'then return nil end
    local x,y,z=value.x,value.y,value.z
    for _,v in ipairs({x,y,z})do if type(v)~='number'or v~=v or math.abs(v)>100000 then return nil end end
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
    if not avatar then return nil,'NO_LOCAL_AVATAR','the explosion is credited to the local player\'s avatar; there is none now'end
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
-- explosion: a weapon name ('R-36 Eruptor') or a typed explosion handle. Host only, during a mission, credited to
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

-- Every catalogued weapon explosion: {weapon, type, assets_known}. Offline; no game reads.
function explosions.list()
    local result={}
    for _,item in ipairs(natives.explosion.weapons)do
        local handle=explosions.of(item.weapon)
        local key=handle and assets_api.key_for(handle)
        result[#result+1]={weapon=item.weapon,type=item.type,assets_known=key and core_assets.dependency(key)~=nil or false}
    end
    return result
end
M.explosions=explosions

------------------------------------------------------------------------------------------------------ status --
-- What event scripts can make the game do in this Runtime, and why the rest is not offered.
function M.status()
    return {
        heal={status='available',api='hd2.actions.heal(amount) / player:heal(amount)',
            limits='local player only; alive, not downed; clamped to maximum health'},
        definition={status='available',api='mod:value(spec) bound to hd2.ensure',
            limits='changes a shared definition (every user of it), re-applied about half a second later'},
        explosion={status='available',api='hd2.explosions.spawn(weapon or handle, {position=...})',
            limits='catalogued weapon explosions with a known package; host only; in a mission; credited to the '
                ..'local player; '..M.EXPLOSION_BURST..' at once and '..M.EXPLOSION_REFILL..' per second per mod; '
                ..'other players may not see the effect',live='not live-tested yet'},
        projectile={status='blocked',reason='no proven native request to fire a projectile from script'},
        status_effect={status='blocked',reason='no proven native call that applies a status to one entity'},
        spawn_entity={status='blocked',reason='the generic spawn (game.dll 0xFDC140) takes spawn parameters and '
            ..'network replication that are not proven'},
    }
end
function M.reset_for_tests()for key in pairs(buckets)do buckets[key]=nil end end
return M
