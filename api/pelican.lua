-- hd2.pelican: the game's own transport Pelican, summoned EMPTY to hover over a position (docs/event-scripting.md#pelicans;
-- research/docs/pelican-cas-F5FEE03DCFDB.md).
--
-- The Runtime calls the game's existing spawn request for the transport Pelican (and for nothing else) with the
-- descriptor the game's own beacon dispatcher builds for a vehicle's Pelican, minus the vehicle: a copy of the game's
-- default spawn context (all zero: no cargo, no associated entity) whose one set member is the ANCHOR, the point the
-- Pelican's flight hovers over (the game takes it into the Pelican's own drop-position record, as it does for a
-- vehicle drop at a beacon). The Pelican is created at a spawn point `approach` metres away and up, flies in, hovers
-- over `position`, releases nothing and leaves. With `hover`, the Runtime holds it: one guarded write of THAT Pelican's
-- own release time, so it stays `hover` seconds after its release.
--
-- No native pointer, no arbitrary call, no hook or patch: the Runtime exposes this one call, guarded (the build's
-- pins, the game thread, a mission as host, the world's default context, the Pelican's entity loaded, the positions)
-- and verified (the entity exists, carries nothing, has its flight and holds the anchor). Every refusal returns a
-- handle with a code.
local events=require('hd2runtime/runtime/events')
local handles=require('hd2runtime/runtime/handles')
local world_module=require('hd2runtime/runtime/event_world')
local pelicans=require('hd2runtime/runtime/pelicans')
local gunship=require('hd2runtime/runtime/pelican_gunship')
local instances=require('hd2runtime/runtime/spawned_instances')
local metrics=require('hd2runtime/runtime/metrics')
local M={}
M.MAX_HOVER=pelicans.HOLD_MAX_SECONDS
M.MAX_ACTIVE=pelicans.MAX_ACTIVE
-- Spawns per mod: a burst of BURST, refilled at REFILL per second.
M.BURST=4
M.REFILL=0.25
-- Where it is created: APPROACH_DISTANCE metres back from the anchor along its heading, APPROACH_HEIGHT metres up.
M.APPROACH_DISTANCE=250
M.APPROACH_HEIGHT=80
M.MAX_APPROACH_DISTANCE=1000
M.MAX_APPROACH_HEIGHT=500

local buckets={}
local function take_token(owner)
    local now=events.state.now
    local bucket=buckets[owner]
    if not bucket then bucket={tokens=M.BURST,at=now};buckets[owner]=bucket end
    bucket.tokens=math.min(M.BURST,bucket.tokens+(now-bucket.at)*M.REFILL)
    bucket.at=now
    if bucket.tokens<1 then return false end
    bucket.tokens=bucket.tokens-1
    return true
end

local Pelican={};Pelican.__index=Pelican
-- A snapshot of the request and what the Runtime has seen of it.
function Pelican:describe()
    return {owner=self.owner,status=self.status,code=self.code,reason=self.reason,entity=self.entity,
        position=self.position and{x=self.position.x,y=self.position.y,z=self.position.z}or nil,hover=self.hover,
        held=self.held,mission=self.mission,approach=self.approach,spawn_point=self.spawn_point}
end
-- True while the Pelican is requested or alive.
function Pelican:alive()return self.status~='refused'and self.status~='gone'and self.status~='unverified'end
-- The live Pelican now (read-only): {entity, stage, released, position, hover_point, cargo} or nil when it is not
-- alive.
function Pelican:state()
    if not self.entity then return nil end
    local world=world_module.open()
    local p=world and pelicans.read(world,self.entity)
    if not p then return nil end
    return {entity=p.entity,stage=p.stage,released=p.released,position=p.position,hover_point=p.target,
        anchor=pelicans.anchor(world,self.entity),cargo=p.cargo~=nil or p.cargo_spawned~=nil}
end

local function refuse(handle,code,reason)
    handle.status,handle.code,handle.reason='refused',code,reason
    events.emit_log('pelican ('..handle.owner..') refused: '..code..': '..reason)
    metrics.count('pelican.refused')
    return handle
end
local function finite(v,limit)return type(v)=='number'and v==v and math.abs(v)<=limit end

-- Summon an empty Pelican: hd2.pelican.spawn({position = p, hover = 60}). opts:
--   position  {x, y, z}: where it hovers (its anchor: the flight hovers over it, at a height of its own); required;
--   approach  {distance, height}: where it is created, back from the anchor along its heading and up (default 250 m
--             back, 80 m up; 0 to 1000 and 0 to 500);
--   hover     seconds it stays after its release (0 < hover <= 120); nil: the game's own (it leaves at once);
--   facing    {x, y}: the horizontal heading it is created with; nil: from the local player toward the position;
--   on_event  function(event): 'spawned', 'stage', 'hovering', 'released', 'held', 'departing', 'gone', and
--             'refused' / 'unverified' / 'hold_refused' / 'cargo' (never expected) with code and reason; with a gun
--             also 'gun_armed' (turret, round, rpm, credit), 'gun_refused' (stage, code, reason), 'gun_ended';
--   gun       its chin gun's OWN configuration (development; runtime/pelican_gunship.lua): {round = 'standard' |
--             'native' (the chin turret's own round 120; alone, {round = 'native'}, the chin turret is left exactly as
--             the game spawned it on every machine: nothing copied or written but its kill credit) | 'ap4',
--             behave_as = 'gatling_sentry' (the Gatling Sentry's
--             AI, casing and rate, with the Runtime target lock), rate_multiplier = 1 | 1.5 | 2, rpm = 30..3000 (with
--             behave_as: an explicit rate in place of the Gatling rate, held on its own copy's rate slot and on every
--             other machine's mirror), casing = 'gatling' | 'own' (with behave_as: the Gatling Sentry's casing, the
--             default, or the chin turret's own), spread = mrad (0, 100], recoil = false (no aim recoil), unlimited_ammo =
--             true (the 2047-round safe magazine, refilled), face_target = true (the body turns toward the lock),
--             sound = a name of the weapon sound catalogue (hd2.sounds; docs/weapon-sounds.md: a shot such as
--             'vehicle/maelstrom/main_gun' or a loop such as 'sentry/gatling', on its own weapon copy; the package of
--             the stratagem that provides its bank is loaded first; other machines with the Runtime mirror it on their
--             own copy; 'pelican/chin_autocannon' or nil: its own), impact_explosion = 'Pelican chin autocannon'
--             (explosive rounds: every round's own impact explosion copy written to the Pelican's own blast 234 before
--             its first step; other machines with the Runtime convert their own copies; the round's row, the MG-206 and
--             the MG-43 stay unchanged; with rpm at most 60, a slow donor's volume: 'EMS mortar field' or 'Gas grenade
--             cloud', never more than 60 a minute)};
--             only this Pelican's own copies and records change, never a shared definition;
--   orbit     {radius, altitude, duration, period, entry}: it circles its anchor once it holds there (needs hover);
--   credit_to the local player (hd2.local_player()): its chin gun's kills credit that player (its own no-credit tag
--             cleared: the game's own Creditor then names the owner of its network object, the host). Solo host only;
--   call      a custom stratagem call context: the Pelican (and its chin turret) are associated with that call;
--   owner     the mod id (defaults to the calling mod).
-- Host only, in a mission. The Runtime makes the call in its own next update (the game thread). Returns a handle; a
-- refusal never raises (status 'refused', code, reason).
function M.spawn(opts)
    opts=opts or{}
    local explicit=opts.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    local handle=setmetatable({owner=owner,status='pending'},Pelican)
    local _,epoch=events.mission()
    handle.mission=epoch
    local p=opts.position
    if not(type(p)=='table'and finite(p.x,100000)and finite(p.y,100000)and finite(p.z,100000))then
        return refuse(handle,'INVALID_POSITION','opts.position must be {x, y, z} world coordinates')
    end
    handle.position={x=p.x,y=p.y,z=p.z}
    if opts.hover~=nil and not(finite(opts.hover,M.MAX_HOVER)and opts.hover>0)then
        return refuse(handle,'INVALID_HOVER','opts.hover must be above 0 and at most '..M.MAX_HOVER..' seconds')
    end
    handle.hover=opts.hover
    local distance,height=M.APPROACH_DISTANCE,M.APPROACH_HEIGHT
    if opts.approach~=nil then
        local a=opts.approach
        if type(a)~='table'then return refuse(handle,'INVALID_APPROACH','opts.approach must be {distance, height}')end
        distance=a.distance==nil and distance or a.distance
        height=a.height==nil and height or a.height
        if not(finite(distance,M.MAX_APPROACH_DISTANCE)and distance>=0 and finite(height,M.MAX_APPROACH_HEIGHT)
            and height>=0)then
            return refuse(handle,'INVALID_APPROACH','opts.approach: distance 0 to '..M.MAX_APPROACH_DISTANCE
                ..' m, height 0 to '..M.MAX_APPROACH_HEIGHT..' m')
        end
    end
    handle.approach={distance=distance,height=height}
    if opts.on_event~=nil and type(opts.on_event)~='function'then
        return refuse(handle,'INVALID_CALLBACK','opts.on_event must be a function')
    end
    -- The gunship options, validated before anything is requested.
    if opts.gun~=nil then
        local ok,why=gunship.check_gun(opts.gun)
        if not ok then return refuse(handle,'INVALID_GUN',why)end
    end
    if opts.orbit~=nil then
        if opts.hover==nil then return refuse(handle,'INVALID_ORBIT','opts.orbit needs opts.hover (it orbits while held)')end
        local ok,why=gunship.check_orbit(opts.orbit)
        if not ok then return refuse(handle,'INVALID_ORBIT',why)end
    end
    local credit_peer
    if opts.credit_to~=nil then
        local who=opts.credit_to
        if opts.gun==nil then return refuse(handle,'INVALID_CREDIT','opts.credit_to credits its chin gun: give opts.gun')end
        -- Another player only for a call the host runs FOR that player (the custom stratagem orchestrator's own marked
        -- call context, runtime/custom_mp_calls.lua; a mod's table never qualifies).
        local remote=type(who)=='table'and who.is_local~=true and type(who.peer)=='string'and type(opts.call)=='table'
            and opts.call.remote==true and opts.call.player_peer==who.peer
            and require('hd2runtime/runtime/multiplayer').call_allowed(opts.call)
        if not(type(who)=='table'and(who.is_local==true or remote))then
            return refuse(handle,'INVALID_CREDIT','opts.credit_to must be the local player (hd2.local_player()): the '
                ..'game credits a Runtime Pelican\'s kills to the owner of its network object, the host')
        end
        if remote then credit_peer=who.peer end
    end
    if opts.call~=nil and not(type(opts.call)=='table'and type(opts.call.call_id)=='string')then
        return refuse(handle,'INVALID_CALL','opts.call must be a custom stratagem call context')
    end
    local world,why=world_module.open()
    if not world then return refuse(handle,'PELICAN_UNAVAILABLE',tostring(why))end
    local state=world_module.game_state(world)
    if not(state and state.mission)then return refuse(handle,'NOT_IN_MISSION','the game is not in a mission')end
    if state.host~=true then
        return refuse(handle,'HOST_ONLY','only the host creates a Pelican; a client\'s would exist only on that client')
    end
    -- The heading: given, or from the local player toward the position (as the game faces a vehicle's Pelican from
    -- its thrower toward the beacon).
    local fx,fy
    if opts.facing~=nil then
        local f=opts.facing
        if not(type(f)=='table'and finite(f.x,1e6)and finite(f.y,1e6))then
            return refuse(handle,'INVALID_FACING','opts.facing must be {x, y}')
        end
        local length=math.sqrt(f.x*f.x+f.y*f.y)
        if length<1e-6 then return refuse(handle,'INVALID_FACING','opts.facing must not be zero')end
        fx,fy=f.x/length,f.y/length
    else
        local avatar=handles.local_avatar(world)
        local from=avatar and avatar.unit and world_module.unit_position(world,avatar.unit)
        local dx,dy=from and p.x-from.x,from and p.y-from.y
        local length=dx and math.sqrt(dx*dx+dy*dy)or 0
        if length>=1 then fx,fy=dx/length,dy/length else fx,fy=0,1 end
    end
    if not take_token(owner)then
        return refuse(handle,'RATE_LIMITED','at most '..M.BURST..' Pelicans at once and one every '
            ..(1/M.REFILL)..' s per mod')
    end
    handle.status='requested'
    local callback=opts.on_event
    local sx,sy,sz=p.x-fx*distance,p.y-fy*distance,p.z+height
    if not(finite(sx,100000)and finite(sy,100000)and finite(sz,100000))then
        return refuse(handle,'INVALID_APPROACH','the spawn point falls outside the world coordinates')
    end
    handle.spawn_point={x=sx,y=sy,z=sz}
    pelicans.request({x=sx,y=sy,z=sz,fx=fx,fy=fy,ax=p.x,ay=p.y,az=p.z,owner=owner,hold=opts.hover},function(event)
        if event.kind=='refused'then
            handle.status,handle.code,handle.reason='refused',event.code,event.reason
        elseif event.kind=='unverified'then
            handle.status,handle.code,handle.reason='unverified','SPAWN_UNVERIFIED',
                'the game returned entity '..tostring(event.result.entity)..' but it is not an empty Pelican'
            handle.entity=event.result.entity
        elseif event.kind=='spawned'then
            handle.status,handle.entity='arriving',event.result.entity
            if opts.call then
                local ok,why=instances.associate(handle.entity,opts.call,'pelican')
                if not ok then events.emit_log('pelican ('..owner..'): not associated with '..opts.call.call_id..': '
                    ..tostring(why))end
            end
            if opts.gun then
                local g,why=gunship.arm(handle.entity,{gun=opts.gun,orbit=opts.orbit,credit=opts.credit_to~=nil,
                    credit_peer=credit_peer,
                    label=(opts.call and opts.call.call_id or owner)..' Pelican '..handle.entity},function(e)
                    local kind=e.kind=='armed'and'gun_armed'or e.kind=='refused'and'gun_refused'or'gun_ended'
                    e.kind=kind
                    if callback then events.run_as(owner,callback,e)end
                end)
                handle.gun=g
                if not g and callback then
                    events.run_as(owner,callback,{kind='gun_refused',stage='arm',code='INVALID_GUN',reason=why,
                        pelican=handle.entity})
                end
            end
        elseif event.kind=='hovering'then handle.status='hovering'
        elseif event.kind=='released'then handle.status='released'
        elseif event.kind=='held'then handle.status,handle.held='held',event.result.seconds
        elseif event.kind=='departing'then handle.status='departing'
        elseif event.kind=='gone'then handle.status='gone'
        end
        if callback then events.run_as(owner,callback,event)end
    end)
    metrics.count('pelican.requested')
    events.emit_log('pelican requested at ('..p.x..', '..p.y..', '..p.z..') by '..owner
        ..(opts.hover and(', hover '..opts.hover..' s')or''))
    return handle
end

-- The Runtime Pelicans alive now (entity ids).
function M.active()return pelicans.active()end
-- What this API can do on this build, and its limits.
function M.status()
    return {status='available',api='hd2.pelican.spawn({position = p, hover = seconds, approach = {distance, height}})',
        limits='the transport Pelican only, empty; host only; in a mission; at most '..M.MAX_ACTIVE..' at a time; '
            ..'hover at most '..M.MAX_HOVER..' s; other players may not see the hold',
        live='the spawn (empty) and the 60 s hold are live-proven (PelicanSpawnProof 0.1.0, solo host); the hover anchor '
            ..'(position) is not live-tested yet (PelicanSpawnProof 0.2.0, PelicanCasProof 0.1.0)'}
end
function M.reset_for_tests()for key in pairs(buckets)do buckets[key]=nil end end
return M
