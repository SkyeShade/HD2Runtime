-- Weapon projectile replacement (docs/custom-projectile-rows.md#weapon-projectile-replacement). Development
-- infrastructure: not exported by api/hd2.lua (a development proof calls api/actions.lua replace_projectiles).
--
-- A carrier is a vanilla projectile a weapon is swapped to fire through the ordinary guarded projectile swap. Every
-- update, Runtime reads which projectiles the game spawned since its last look (runtime/event_world.lua, read-only):
-- for each carrier the local player fired, it spawns a custom projectile (runtime/custom_projectiles.lua) through the
-- game's SpawnProjectile, from the carrier's spawn point along its direction. The carrier's distance travelled leads
-- back to the spawn point even when the game already moved it, or it already hit something.
--
-- The replacement itself writes nothing: the carrier flies on, so it should be an invisible, harmless projectile
-- without explosions (a projectile with an explosion could be skipped into, so it is refused). The spawn is up to one
-- frame after the shot: the engine runs Lua's update before the game update that fires weapons.
local world_module=require('hd2runtime/runtime/event_world')
local handles=require('hd2runtime/runtime/handles')
local scheduler=require('hd2runtime/runtime/scheduler')
local events=require('hd2runtime/runtime/events')
local metrics=require('hd2runtime/runtime/metrics')
local core_assets=require('hd2runtime/core/assets')
local custom_projectiles=require('hd2runtime/runtime/custom_projectiles')
local M={}

-- Replacements per binding: a burst of BURST, refilled at REFILL per second, and at most MAX_PER_TICK in one update.
-- The fastest player weapons fire about 15 rounds per second.
M.BURST,M.REFILL,M.MAX_PER_TICK=40,30,24
-- The first DETAIL_LOGS replacements of each binding are logged in full (a binding can ask for more); then a summary
-- every SUMMARY_SECONDS. A burst of the weapon's shots ends after BURST_GAP seconds without one, and is logged with its
-- cadence.
M.DETAIL_LOGS,M.SUMMARY_SECONDS,M.BURST_GAP=8,10,0.3
local POOL_SLOTS=require('hd2runtime/domains/projectile_rows').pool.slots
local COUNTER_RANGE=4294967296

local bindings,order={},{}
local observed={}          -- an unreplaced projectile type -> the binding that counts it
local pending={}           -- the pool slot of a custom projectile spawned last update -> the binding that spawned it
local watch
local pool={}              -- {system, counter}: where the previous update stopped reading
local clock=0              -- seconds of game updates since the module loaded (the dt the engine passes)

local function log(text)events.emit_log('projectile replacement: '..text)end
local function vector(v)return string.format('(%.2f, %.2f, %.2f)',v.x,v.y,v.z)end

local function observed_text(binding)
    local unreplaced=binding.unreplaced
    if not unreplaced then return''end
    if unreplaced.role=='suppressed'then
        return ('; %d native %s shots seen (suppression %s)'):format(binding.normal,unreplaced.name,
            binding.normal==0 and'held'or'FAILED')
    end
    return ('; %d %s shots not replaced'):format(binding.normal,unreplaced.name)
end
local function latency_text(binding)
    local l=binding.latency
    if l.count==0 then return''end
    return ('; latency one game update: mean %.1f ms, max %.1f ms; carrier flight before the read max %.1f ms')
        :format(l.sum/l.count*1000,l.max*1000,l.flight*1000)
end
local function summary(binding)
    log(('%s -> %s: %d carriers, %d replaced (%d confirmed in the pool, %d not), %d dropped (rate), %d refused, %d not '
        ..'the local player\'s, %d other weapons%s%s'):format(binding.carrier_name,binding.definition.id,binding.carriers,
        binding.replaced,binding.confirmed,binding.unconfirmed,binding.dropped,binding.refused,binding.foreign,
        binding.other_weapons,observed_text(binding),latency_text(binding)))
end

-- Burst cadence: shots of the binding's weapon (replaced, dropped or unreplaced) at the update that first saw them.
-- Several shots of one update share its time, so the cadence is exact to about one update per end of the burst.
local function close_burst(binding)
    local burst=binding.burst
    binding.burst=nil
    if not burst or burst.shots<2 then return end
    local seconds=burst.last-burst.first
    burst.seconds=seconds
    burst.rpm=seconds>0 and(burst.shots-1)/seconds*60 or nil
    binding.last_burst=burst
    log(('%s burst: %d shots (%d custom, %d %s) over %.2f s%s'):format(tostring(binding.weapon or binding.context
        or binding.carrier_name),burst.shots,burst.custom,burst.normal,binding.unreplaced and binding.unreplaced.role
        =='suppressed'and'native'or'normal',seconds,burst.rpm and(' = %.0f rpm'):format(burst.rpm)or''))
end
local function track(binding,mode)
    local burst=binding.burst
    if burst and clock-burst.last>M.BURST_GAP then close_burst(binding);burst=nil end
    if not burst then
        burst={first=clock,last=clock,shots=0,custom=0,normal=0}
        binding.burst=burst
    end
    burst.last=clock
    burst.shots=burst.shots+1
    burst[mode]=burst[mode]+1
    binding.last_mode=mode
end

-- Who an entity is, for logs: the local avatar, a catalogued name, or its entity type.
local function identity(world,entity,avatar,names)
    if entity==0 then return'none'end
    if entity==avatar then return'the local avatar'end
    local kind=world_module.entity_type(world,entity)
    if not kind then return'unknown entity'end
    local info=world_module.type_info(kind)
    local name=names and names[kind]or world_module.source_name(kind)or info and(info.name or info.id)
    return ('type %s%s'):format(kind,name and(' '..name)or'')
end
-- The attribution and latency of one slot, appended to its log line.
local function attribution(binding,allowed,record,dt)
    local world=allowed.world
    local creditor=record.creditor_lo==allowed.peer_lo and record.creditor_hi==allowed.peer_hi and'local peer'
        or(record.creditor_lo==0 and record.creditor_hi==0)and'none'
        or string.format('peer %08X%08X',record.creditor_hi,record.creditor_lo)
    local v=record.velocity
    local speed=math.sqrt(v.x^2+v.y^2+v.z^2)
    return ('; creditor %s; owner %d (%s); source %d (%s); projectile type %d%s; latency one game update (dt %.1f ms), '
        ..'carrier flew %.2f m = %.1f ms before the read'):format(creditor,record.owner,identity(world,record.owner,
        allowed.avatar),record.source,identity(world,record.source,allowed.avatar,binding.sources),record.type,
        binding.context and(' in '..binding.context)or'',dt*1000,record.distance,speed>0 and record.distance/speed*1000
        or 0)
end

-- The custom projectile for one carrier slot. allowed: {world, avatar, peer_lo, peer_hi, weapons = {}}.
local function replace(binding,allowed,record,dt)
    local world=allowed.world
    local v=record.velocity
    local speed=math.sqrt(v.x^2+v.y^2+v.z^2)
    if speed<1e-3 then
        binding.refused=binding.refused+1
        return 'the carrier has no velocity'
    end
    local d={x=v.x/speed,y=v.y/speed,z=v.z/speed}
    local travelled=math.max(record.distance,0)
    local p=record.position
    local origin={x=p.x-d.x*travelled,y=p.y-d.y*travelled,z=p.z-d.z*travelled}
    local definition=binding.definition
    local result,why=world_module.spawn_projectile_row(world,{row=definition.row.address,
        base_type=definition.base.type,x=origin.x,y=origin.y,z=origin.z,dx=d.x,dy=d.y,dz=d.z,source=allowed.avatar,
        owner=allowed.avatar,peer_lo=allowed.peer_lo,peer_hi=allowed.peer_hi})
    if not result then
        binding.refused=binding.refused+1
        return tostring(why)
    end
    binding.replaced=binding.replaced+1
    metrics.count('projectile_replacement.spawns')
    -- Confirmed on the next update, when its pool slot is in the range read (runtime/event_world.lua).
    if type(result.slot)=='number'then pending[result.slot]={binding=binding,at=clock}end
    local l=binding.latency
    l.count,l.sum,l.max=l.count+1,l.sum+dt,math.max(l.max,dt)
    l.flight=math.max(l.flight,speed>0 and record.distance/speed or 0)
    if binding.detailed<binding.detail_logs then
        binding.detailed=binding.detailed+1
        local avatar_position=world_module.entity_state(world,allowed.avatar)
        local body=avatar_position and world_module.unit_pose(world,avatar_position.descriptor.unit)
        log(('%s%s shot %d: carrier slot %d (type %d) at %s travelled %.2f m (lifetime %.2f), velocity %s; owner %d, '
            ..'source %d (%s); custom %s from %s along %s -> slot %s%s'):format(binding.unreplaced and'custom mode: '
            or'',binding.carrier_name,binding.replaced,
            record.slot,record.type,vector(p),record.distance,record.lifetime,vector(v),record.owner,record.source,
            tostring(record.weapon),definition.id,vector(origin),vector(d),tostring(result.slot),
            body and(', the avatar at '..vector(body.position))or'')..(binding.attribute and
            attribution(binding,allowed,record,dt)or''))
    end
    return nil
end

-- Who may replace now: the host, with a local avatar and peer. nil and the reason otherwise.
local function authority(world)
    local state=world_module.game_state(world)
    if not(state and state.mission)then return nil,'not in a mission'end
    if state.host~=true then return nil,'not the host'end
    local avatar,why=handles.local_avatar(world,{include_dead=true})
    if not avatar then return nil,'no local avatar ('..tostring(why)..')'end
    local lo,hi=world_module.local_peer(world)
    if not lo then return nil,'the local peer id is unreadable'end
    return {world=world,avatar=avatar.id,peer_lo=lo,peer_hi=hi}
end

local function resident(binding)
    for _,dependency in ipairs(binding.definition.dependencies)do
        local ok,state=pcall(core_assets.state,binding.runtime,dependency.package)
        if not(ok and state=='resident')then return false end
    end
    return true
end

-- A shot of the unreplaced type: the weapon's normal projectile (counted and logged, never replaced), or the native
-- projectile a carrier swap should suppress (every sighting is a suppression failure).
local function pass(binding,allowed,record,dt)
    binding.normal=binding.normal+1
    if binding.unreplaced.role=='suppressed'then
        if binding.normal_detailed<binding.detail_logs then
            binding.normal_detailed=binding.normal_detailed+1
            log(('SUPPRESSION FAILED: native %s projectile %d: slot %d (type %d) at %s travelled %.2f m: the carrier swap '
                ..'did not reach this shot; it is not replaced%s'):format(binding.unreplaced.name,binding.normal,
                record.slot,record.type,vector(record.position),record.distance,attribution(binding,allowed,record,dt)))
        end
        return
    end
    if binding.normal_detailed<binding.detail_logs then
        binding.normal_detailed=binding.normal_detailed+1
        log(('normal mode: %s shot %d: native projectile slot %d (type %d) at %s travelled %.2f m; owner %d, source %d '
            ..'(%s) -> no replacement'):format(binding.unreplaced.name,binding.normal,record.slot,record.type,
            vector(record.position),record.distance,record.owner,record.source,tostring(record.weapon)))
    end
end

local function tick(dt)
    if #order==0 then
        watch.status='complete'
        watch=nil
        return
    end
    clock=clock+dt
    for _,carrier in ipairs(order)do
        local binding=bindings[carrier]
        if binding.burst and clock-binding.burst.last>M.BURST_GAP then close_burst(binding)end
        binding.this_tick=0
        binding.tokens=math.min(M.BURST,binding.tokens+dt*M.REFILL)
        binding.since_summary=binding.since_summary+dt
        if binding.since_summary>=M.SUMMARY_SECONDS then
            binding.since_summary=0
            if binding.replaced+binding.dropped+binding.refused~=binding.reported then
                binding.reported=binding.replaced+binding.dropped+binding.refused
                summary(binding)
            end
        end
    end
    local world=world_module.open()
    local counter,system=nil,nil
    if world then counter,system=world_module.projectile_counter(world)end
    if not counter then
        pool.system,pool.counter=nil,nil
        return
    end
    -- A new mission (the counter restarts) or a new system starts from what exists now; nothing older is replaced.
    local count=pool.counter and(counter-pool.counter)%COUNTER_RANGE
    if pool.system~=system or not count or count>POOL_SLOTS then
        if pool.system==system and count and count>POOL_SLOTS and count<COUNTER_RANGE/2 then
            log(('%d projectiles spawned in one update, more than the pool holds; they are not replaced'):format(count))
        end
        pool.system,pool.counter=system,counter
        return
    end
    for slot,spawned in pairs(pending)do
        if spawned.at<clock-1 then
            pending[slot]=nil
            spawned.binding.unconfirmed=spawned.binding.unconfirmed+1
        end
    end
    if count==0 then return end
    local from=pool.counter
    pool.counter=counter
    local slots=world_module.projectile_types(world,system,from,count)
    if not slots then return end
    -- Authority is read once per update, and only when a carrier was spawned.
    local allowed,why,checked
    for _,item in ipairs(slots)do
        -- A custom projectile spawned last update: confirmed when its slot holds the definition's base type.
        local spawned=pending[item.slot]
        if spawned then
            pending[item.slot]=nil
            local owner=spawned.binding
            if item.type==owner.definition.base.type then
                owner.confirmed=owner.confirmed+1
            else
                owner.unconfirmed=owner.unconfirmed+1
                log(('custom projectile slot %d holds type %d, not %d'):format(item.slot,item.type,
                    owner.definition.base.type))
            end
        end
        local binding=bindings[item.type]or observed[item.type]
        if binding then
            local normal=item.type~=binding.carrier
            if not checked then
                checked=true
                allowed,why=authority(world)
            end
            local record=allowed and world_module.projectile_slot(world,system,item.slot)
            if not allowed then
                if not normal then
                    binding.refused=binding.refused+1
                    if binding.last_refusal~=why then log('carrier shots are not replaced: '..tostring(why))end
                    binding.last_refusal=why
                end
            elseif not record or record.type~=item.type then
                if not normal then binding.refused=binding.refused+1 end
            elseif(record.creditor_lo~=allowed.peer_lo or record.creditor_hi~=allowed.peer_hi)and not(
                    binding.credit=='local_or_none'and record.creditor_lo==0 and record.creditor_hi==0)then
                if not normal then binding.foreign=binding.foreign+1 end
            else
                local entity_type=world_module.entity_type(world,record.source)
                local name=entity_type and(binding.sources and binding.sources[entity_type]or
                    world_module.source_name(entity_type))
                record.weapon=name
                if binding.weapon and name~=binding.weapon or binding.sources and not(entity_type and
                        binding.sources[entity_type])then
                    if not normal then binding.other_weapons=binding.other_weapons+1 end
                elseif normal then
                    track(binding,'normal')
                    pass(binding,allowed,record,dt)
                elseif binding.tokens<1 or binding.this_tick>=M.MAX_PER_TICK then
                    binding.carriers=binding.carriers+1
                    track(binding,'custom')
                    binding.dropped=binding.dropped+1
                elseif not binding.assets_checked and not resident(binding)then
                    binding.carriers=binding.carriers+1
                    binding.refused=binding.refused+1
                    if binding.last_refusal~='assets'then log('the packages of '..binding.definition.id..' are not resident')end
                    binding.last_refusal='assets'
                else
                    track(binding,'custom')
                    binding.carriers=binding.carriers+1
                    binding.assets_checked=true
                    binding.tokens=binding.tokens-1
                    binding.this_tick=binding.this_tick+1
                    local refused=replace(binding,allowed,record,dt)
                    if refused and binding.last_refusal~=refused then log('a replacement was refused: '..refused)end
                    binding.last_refusal=refused
                end
            end
        end
    end
end

-- Binds a carrier type to a custom projectile definition. spec: {carrier = {type, name}, definition = a defined
-- custom projectile, weapon = the catalogued name of the only weapon whose carrier shots are replaced (optional),
-- unreplaced = {type, name} (optional: the same weapon's other projectile, for example its normal mode when the carrier
-- is its programmable mode; counted and logged as not replaced, never replaced; with role = 'suppressed', the native
-- projectile a carrier swap replaced, whose every sighting is a suppression failure), detail_logs = how many shots of
-- each kind are logged in full (default DETAIL_LOGS; math.huge for every shot), sources = {[entity type] = name}
-- (optional: only shots whose source entity has one of these types), credit = 'local' (default: the creditor is the
-- local peer) or 'local_or_none' (also a shot credited to no peer), context = a description of the host for logs,
-- attribute = true (log each shot's creditor, owner, source and latency), owner = the mod, runtime = the adapter that
-- checks package residency}. A second binding of the same carrier replaces the first. Returns the binding description.
function M.bind(spec)
    local carrier,unreplaced=spec.carrier,spec.unreplaced
    assert(type(carrier)=='table'and type(carrier.type)=='number'and custom_projectiles.get(spec.definition.id)
        ==spec.definition,'unsupported projectile replacement binding')
    assert(unreplaced==nil or type(unreplaced)=='table'and type(unreplaced.type)=='number'
        and unreplaced.type~=carrier.type,'the unreplaced projectile must be another type than the carrier')
    assert(spec.detail_logs==nil or type(spec.detail_logs)=='number'and spec.detail_logs>=0,'detail_logs must be a count')
    assert(unreplaced==nil or unreplaced.role==nil or unreplaced.role=='normal'or unreplaced.role=='suppressed',
        'unreplaced.role must be normal or suppressed')
    assert(spec.credit==nil or spec.credit=='local'or spec.credit=='local_or_none','credit must be local or local_or_none')
    assert(spec.sources==nil or type(spec.sources)=='table'and next(spec.sources)~=nil,'sources must name entity types')
    M.unbind(carrier.type,true)
    order[#order+1]=carrier.type
    -- Only carriers spawned after this binding are replaced: the next update starts from the counter it reads.
    if #order==1 then pool.system,pool.counter=nil,nil end
    if unreplaced and unreplaced.role==nil then
        unreplaced={type=unreplaced.type,name=unreplaced.name,role='normal'}
    end
    bindings[carrier.type]={carrier=carrier.type,carrier_name=carrier.name,definition=spec.definition,
        weapon=spec.weapon,unreplaced=unreplaced,detail_logs=spec.detail_logs or M.DETAIL_LOGS,owner=spec.owner,
        sources=spec.sources,credit=spec.credit or'local',context=spec.context,attribute=spec.attribute==true,
        runtime=spec.runtime,tokens=M.BURST,this_tick=0,since_summary=0,carriers=0,replaced=0,confirmed=0,
        unconfirmed=0,dropped=0,refused=0,foreign=0,other_weapons=0,normal=0,detailed=0,normal_detailed=0,reported=0,
        latency={count=0,sum=0,max=0,flight=0}}
    if unreplaced then observed[unreplaced.type]=bindings[carrier.type]end
    if not watch then
        watch={status='active'}
        function watch.tick(dt)tick(dt)end
        function watch.cancel()watch.status='cancelled'end
        scheduler.attach(watch)
    end
    metrics.count('projectile_replacement.bindings')
    return M.describe(carrier.type)
end
-- Ends the binding of a carrier type; its counts (and an open burst) are logged unless quiet. true when there was one.
function M.unbind(carrier_type,quiet)
    local binding=bindings[carrier_type]
    if not binding then return false end
    if not quiet then
        close_burst(binding)
        summary(binding)
    end
    for kind,owner in pairs(observed)do if owner==binding then observed[kind]=nil end end
    for slot,spawned in pairs(pending)do if spawned.binding==binding then pending[slot]=nil end end
    bindings[carrier_type]=nil
    for index=#order,1,-1 do if order[index]==carrier_type then table.remove(order,index)end end
    return true
end
function M.describe(carrier_type)
    local binding=bindings[carrier_type]
    if not binding then return nil end
    local last=binding.last_burst
    local l=binding.latency
    return {carrier=binding.carrier,carrier_name=binding.carrier_name,definition=binding.definition.id,
        weapon=binding.weapon,owner=binding.owner,context=binding.context,credit=binding.credit,
        carriers=binding.carriers,confirmed=binding.confirmed,unconfirmed=binding.unconfirmed,
        role=binding.unreplaced and binding.unreplaced.role,latency={count=l.count,mean=l.count>0 and l.sum/l.count
        or nil,max=l.max,flight=l.flight},replaced=binding.replaced,dropped=binding.dropped,
        refused=binding.refused,foreign=binding.foreign,other_weapons=binding.other_weapons,
        unreplaced=binding.unreplaced and binding.unreplaced.type,unreplaced_name=binding.unreplaced
        and binding.unreplaced.name,normal=binding.normal,last_mode=binding.last_mode,
        last_burst=last and{shots=last.shots,custom=last.custom,normal=last.normal,seconds=last.seconds,rpm=last.rpm}}
end
function M.list()
    local out={}
    for _,carrier in ipairs(order)do out[#out+1]=M.describe(carrier)end
    return out
end
function M.reset_for_tests()
    for _,carrier in ipairs(order)do bindings[carrier]=nil end
    for kind in pairs(observed)do observed[kind]=nil end
    for slot in pairs(pending)do pending[slot]=nil end
    for index=#order,1,-1 do order[index]=nil end
    if watch then watch.status='cancelled';watch=nil end
    pool.system,pool.counter=nil,nil
end
return M
