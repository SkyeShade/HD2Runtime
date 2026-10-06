-- Custom silo payloads (development; docs/custom-stratagem-api.md "silo"; research/silo-payload-F5FEE03DCFDB.json).
-- silo = {donor, blast, fallback}: the donor silo's own vanilla pod, by the support redirect (a blue support carrier's
-- beacon delivers the donor's pod). The pod deploys the silo (its rack entity); the rack's two items, the MISSILE and
-- the laser REMOTE, are captured exactly (runtime/support_pods.lua: the pod naming the call's beacon, its rack, each
-- slot's network id) and associated with the call. The silo, its launch and the missile's own blast stay vanilla.
-- When THAT missile detonates, the Runtime requests the BLAST (a catalogued explosion, hd2.explosions) at the point.
-- Read-only until then:
--   * the detonation: the explosion queue's entry of the missile's own detonation type whose source is the missile
--     entity (event natives: an explosive's detonation is queued with its own entity as the source), read every update
--     while the missile exists: its position, at once. Else, the missile entity gone after it left the silo: its last
--     read position (inferred). Gone before it left the silo (the silo destroyed first): no blast;
--   * the request: the session host's (hd2.explosions.spawn refuses a client, HOST_ONLY: enemy health is the host's),
--     credited to the host's player (the live-proven request). With several players the caller publishes the
--     missile's network id (runtime/custom_mp_items.lua) and the host watches its own copy of that missile;
--   * assets: the blast's packages (and the fallback's) are the definition's, requested at mission start on every
--     machine whose lobby picked it (the custom stratagem is not callable before the caller's are resident). Not
--     resident at the detonation: the fallback blast, if any; else none.
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local PP=require('hd2runtime/domains/pod_payload_authoring')
local M={}
M.LAUNCHED=15        -- metres from its first read position: the missile has left the silo
M.QUEUE_SLOTS=32     -- explosion queue entries read per update while a missile is watched (of 256)
M.MAX_SECONDS=900    -- a watch ends after this long without a detonation (a missile never fired)
M.SILOS=PP.silos or{}

local function hex(resource)return(tostring(resource):gsub('^0x',''):upper())end
local function distance(a,c)local x,y,z=a.x-c.x,a.y-c.y,a.z-c.z;return math.sqrt(x*x+y*y+z*z)end
local function log(text)log_module.emit('[HD2Runtime] custom silo '..text)end
function M.names()
    local out={}
    for name in pairs(M.SILOS)do out[#out+1]=name end
    table.sort(out)
    return out
end

-- silo = {donor = a reviewed silo stratagem, blast = an explosion, fallback = an explosion or nil}, an explosion being an
-- hd2.explosions name (a named explosion, 'Cyborg Production Unit', 'Hellbomb', or a weapon's). Returns the delivery
-- {kind = 'silo', stratagem, id, item_types, items, missile, remote, detonation, blast, fallback, deps}; errors.
function M.spec(value,policy,donor_name)
    assert(type(value)=='table','silo must be {donor = name, blast = explosion, fallback = explosion}')
    for key in pairs(value)do
        assert(key=='donor'or key=='blast'or key=='fallback','unsupported silo field: '..tostring(key))
    end
    local name=donor_name(value.donor)
    local silo=name and M.SILOS[name]
    assert(silo,'silo.donor must be a reviewed missile silo: '..table.concat(M.names(),', '))
    assert(policy.beacon=='support','a silo needs a support (blue beacon) carrier')
    local actions=require('hd2runtime/api/actions')
    local function blast(v,where)
        local target,code,reason=actions.explosion_target(v)
        assert(target,('%s must be a catalogued explosion whose packages are known (hd2.explosions.list()): %s: %s')
            :format(where,tostring(code),tostring(reason)))
        return target
    end
    assert(value.blast~=nil,'silo.blast is required: the explosion requested where the missile detonates')
    local main=blast(value.blast,'silo.blast')
    local fallback=value.fallback~=nil and blast(value.fallback,'silo.fallback')or nil
    assert(not fallback or fallback.name~=main.name,'silo.fallback must be another explosion than silo.blast')
    local deps,seen={},{}
    for _,t in ipairs(fallback and{main,fallback}or{main})do
        for _,dep in ipairs(t.dependencies or{t.dependency})do
            if not seen[dep.package]then seen[dep.package]=true;deps[#deps+1]=dep end
        end
    end
    local missile,remote=hex(silo.missile.resource),hex(silo.remote.resource)
    return {kind='silo',stratagem=name,id=silo.id,rack=silo.rack,missile=missile,remote=remote,
        missile_slot=silo.missile.slot,remote_slot=silo.remote.slot,detonation=silo.missile.detonation,
        item_types={[missile]=true,[remote]=true},items={[missile]={kind='missile'},[remote]={kind='remote'}},
        count=2,blast=main.name,blast_type=main.type,fallback=fallback and fallback.name or nil,
        fallback_type=fallback and fallback.type or nil,deps=deps,family='support',
        objective=main.objective}
end

-- Follows ONE missile until it detonates (read-only). spec = {missile (entity), detonation (its explosion type), label}.
-- callback(event): 'launched' {position}, 'detonated' {position, via = 'queue' | 'removal', seconds}, 'gone' (it ended
-- before it left the silo), 'ended' {reason}. Returns the watch {status, cancel()}.
function M.watch(spec,callback)
    local w={status='active',seconds=0}
    local start,last,launched
    local function emit(e)
        if callback then
            local ok,why=pcall(callback,e)
            if not ok then log('callback failed: '..tostring(why))end
        end
    end
    local function finish(reason)
        if w.status~='active'then return end
        w.status='complete'
        emit({kind='ended',reason=reason})
    end
    local function queued(world)
        for _,q in ipairs(world_module.explosion_queue(world,M.QUEUE_SLOTS)or{})do
            if q.type==spec.detonation and q.source==spec.missile then return q end
        end
    end
    function w.tick(dt)
        if w.status~='active'then return end
        w.seconds=w.seconds+(dt or 0)
        local world=world_module.open()
        if not world then return end
        local game=world_module.game_state(world)
        if not(game and game.mission)then return finish('the mission ended')end
        local exists=world_module.entity_exists(world,spec.missile)==true
        local unit=exists and world_module.entity_unit(world,spec.missile)
        local p=unit and world_module.unit_position(world,unit)
        if p then
            start=start or p
            last=p
            if not launched and distance(p,start)>M.LAUNCHED then
                launched=true
                emit({kind='launched',position=p,seconds=w.seconds})
            end
        end
        -- Its own detonation, queued this frame or still readable from an earlier one.
        local q=launched and queued(world)
        if q then
            emit({kind='detonated',position={x=q.x,y=q.y,z=q.z},via='queue',seconds=w.seconds})
            return finish('detonated')
        end
        if not exists then
            if launched and last then
                emit({kind='detonated',position=last,via='removal',seconds=w.seconds})
                return finish('detonated')
            end
            emit({kind='gone',position=last,seconds=w.seconds})
            return finish('the missile ended before it left the silo')
        end
        if w.seconds>M.MAX_SECONDS then return finish('no detonation within '..M.MAX_SECONDS..' s')end
    end
    function w.cancel()if w.status=='active'then w.status='cancelled'end end
    scheduler.attach(w)
    return w
end

-- The blast of a detonation: the definition's explosion (or its fallback when the blast's packages are not resident
-- here) requested at the position, by the session host only. d: the definition (its delivery a silo spec); owner: the
-- requesting mod (rate limit and log). Returns the explosion action (hd2.explosions.spawn's handle), or nil and why.
function M.blast(d,position,label)
    local s=d.delivery
    local actions=require('hd2runtime/api/actions')
    local world=world_module.open()
    if not world then return nil,'no game world'end
    local game=world_module.game_state(world)
    if not(game and game.host==true)then
        return nil,'HOST_ONLY: the session host requests the blast (enemy health is the host\'s)'
    end
    local name=s.blast
    local target=actions.explosion_target(name)
    if not(target and actions.explosion_resident(world.runtime,target))then
        local f=s.fallback and actions.explosion_target(s.fallback)
        if not(f and actions.explosion_resident(world.runtime,f))then
            return nil,('ASSET_UNAVAILABLE: the %s explosion\'s packages are not resident here%s'):format(name,
                s.fallback and(' (nor the fallback '..s.fallback..'\'s)')or'')
        end
        log(('%s: the %s explosion\'s packages are not resident here: its fallback %s instead'):format(label,name,
            s.fallback))
        name=s.fallback
    end
    local action=actions.explosions.spawn(name,{position=position,owner=d.owner})
    if action.status=='refused'then return nil,tostring(action.code)..': '..tostring(action.reason)end
    return action,name
end

-- The delivery's log text (registration).
function M.text(s)
    return('the vanilla %s pod: its silo and laser remote; where exactly this call\'s missile detonates, the session host '
        ..'requests the %s explosion%s (the missile\'s own blast stays)'):format(s.stratagem,s.blast,
        s.fallback and(' (else the '..s.fallback..'\'s when its packages are not resident)')or'')
end
-- What every machine must agree on (the registry hash).
function M.signature(s)
    return'silo='..tostring(s.stratagem)..',blast='..tostring(s.blast)..',fallback='..tostring(s.fallback)
end
return M
