local hd2=require('mods/skyeshade/hd2runtime')
-- PelicanProbe 0.1.0: THE GAME'S OWN PELICAN, OBSERVED AND HELD (research/docs/pelican-cas-F5FEE03DCFDB.md).
--
-- The game's transport Pelican is the one a vehicle or exosuit call-in sends (runtime/pelicans.lua). This probe:
--   * observes every transport Pelican, read-only: its cargo when first seen (the research says the cargo already
--     exists by then: no per-call cargo window), its flight stages, its hover point against the beacon it came from,
--     its release, its departure and its removal;
--   * HOLDS each Pelican once released (on by default; Ctrl+F8 toggles): ONE guarded 8-byte write of that Pelican's
--     own release time, so it departs 60 s after its release instead of 0.6 s. The departure, the fly-out and the
--     removal stay the game's. Nothing shared is written: no Pelican settings, no StratagemInfo, no vehicle;
--   * aboard the ship, logs the read-only carrier allocation of the two custom stratagems (runtime/carrier_allocator.lua):
--     "CUSTOM CARRIER: Gas Barrage = X, Pelican CAS = Y; distinct = true". It converts and presents nothing.
-- Solo, host only (the hold refuses otherwise; the observation works anywhere).
local mod=hd2.mod()
local BUILD='0.1.0 PELICAN PROBE + HOLD'
local HOLD_SECONDS=60
mod:log('PelicanProbe '..BUILD..' (one guarded write per released Pelican, nothing shared): aboard the ship expect '
    ..'"CUSTOM CARRIER: ..."; in a SOLO mission call a vehicle or exosuit you own. Expect "PELICAN SEEN", "PELICAN '
    ..'STAGE", "PELICAN RELEASED", "PELICAN HELD" (it then hovers about 60 s), "PELICAN DEPARTING" and "PELICAN GONE". '
    ..'Ctrl+F8: hold on/off; Ctrl+F11: the live Pelicans and the allocation.')

local world_module=require('hd2runtime/runtime/event_world')
local pelicans=require('hd2runtime/runtime/pelicans')
local allocator=require('hd2runtime/runtime/carrier_allocator')
local redirect=require('hd2runtime/runtime/beacon_redirect')
local beacons=require('hd2runtime/runtime/beacons')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local catalog=require('hd2runtime/domains/stratagem_authoring')

local names_by_id={}
for name,entry in pairs(catalog.stratagems)do if entry.root then names_by_id[entry.root.id]=name end end
local function type_name(world,kind)
    if not kind then return'?'end
    if kind==0 then return'type 0'end
    local id=loadout.id_of(world,kind)
    return ('%s (%d)'):format(id and names_by_id[id]or'uncatalogued',kind)
end
local function n1(v)return v and('%.1f'):format(v)or'?'end
local function n2(v)return v and('%.2f'):format(v)or'?'end
local function at(v)return v and('(%.1f, %.1f, %.1f)'):format(v.x,v.y,v.z)or'(?)'end
local function flat(a,c)
    if not(a and c)then return nil end
    return math.sqrt((a.x-c.x)^2+(a.y-c.y)^2)
end

local proven
local function prove(world)
    if proven~=nil then return proven end
    local ok,why=pelicans.prove(world)
    proven=ok==true
    mod:log(proven and'pins: the Transport, Behavior and transform components and the flight\'s stage machine are the '
        ..'researched code (runtime/pelicans.lua)'or('REFUSED: '..tostring(why)..'; nothing is read or written'))
    return proven
end

------------------------------------------------------------------------------------- the beacons (read-only) --
-- Activated beacons with their positions, so a Pelican can be matched to the call it came from.
local activations={}       -- {entity, type, name, position, clock}
local known={}
local function poll_beacons(world)
    local list=redirect.beacons(world)
    if not list then return end
    local now=pelicans.clock(world)
    for entity,it in pairs(list)do
        local k=known[entity]
        if not k then k={type=it.type};known[entity]=k end
        if it.activated and not k.activated then
            k.activated=true
            activations[#activations+1]={entity=entity,type=it.type,name=type_name(world,it.type),
                position=beacons.position(world,entity),clock=now}
            if #activations>16 then table.remove(activations,1)end
        end
        if not k.position then k.position=beacons.position(world,entity)end
    end
    for entity in pairs(known)do if not list[entity]then known[entity]=nil end end
end
-- The beacon activated closest in time before `clock` (within 3 s), or nil.
local function beacon_for(clock)
    local best
    for _,a in ipairs(activations)do
        if clock and a.clock and a.clock<=clock+50000 and clock-a.clock<=3000000 then
            if not best or a.clock>best.clock then best=a end
        end
    end
    return best
end

------------------------------------------------------------------------------------------------ the Pelicans --
local hold_on=true
local pelican_state={}      -- entity -> {beacon, seen_at, spawn}
local function on_event(e)
    local world=world_module.open()
    if e.kind=='seen'then
        local p=e.pelican
        local bn=beacon_for(e.clock)
        pelican_state[p.entity]={beacon=bn,spawn=p.position}
        mod:log(('PELICAN SEEN: entity %d (network id %s), behaviour %s, stage %s; cargo %s, %s; cargo timer %s; '
            ..'associated %s; at %s%s'):format(p.entity,tostring(p.network),tostring(p.behaviour),tostring(p.stage),
            p.cargo and pelicans.cargo_name(p.cargo)or'none',p.cargo_spawned and('ALREADY SPAWNED (entity '
            ..p.cargo_spawned..'): no per-call cargo window')or(p.cargo and'NOT YET SPAWNED: a cargo window exists'
            or'nothing to spawn'),n2(p.cargo_timer),tostring(p.associated or'none'),at(p.position),
            bn and(('; from the %s beacon %d at %s (activated %s s before; %s m away)'):format(bn.name,bn.entity,
            at(bn.position),n2(e.clock and bn.clock and(e.clock-bn.clock)/1e6),n1(pelicans.distance(p.position,
            bn.position))))or'; no beacon activated just before'))
    elseif e.kind=='cargo'then
        mod:log(('PELICAN CARGO: entity %d: its cargo (entity %d) appeared %d update(s), %s s after it was first seen'):format(
            e.entity,e.spawned,e.updates,n2(e.seconds)))
    elseif e.kind=='stage'then
        local s=pelican_state[e.entity]
        mod:log(('PELICAN STAGE: entity %d: %s -> %s at %s s; target %s; at %s%s'):format(e.entity,tostring(e.from),
            tostring(e.to),n1(e.seconds),at(e.target),at(e.position),s and s.beacon and(' (target %s m from the beacon '
            ..'horizontally)'):format(n1(flat(e.target,s.beacon.position)))or''))
    elseif e.kind=='released'then
        local s=pelican_state[e.entity]
        mod:log(('PELICAN RELEASED: entity %d in stage %d, %s s after it was first seen; hovered %s s before its release; '
            ..'hover point %s, at %s%s; native departure %s s after the release'):format(e.entity,e.stage,n1(e.seconds),
            n1(e.hover),at(e.target),at(e.position),s and s.beacon and(('; %s m from the beacon horizontally, %s m above '
            ..'it'):format(n1(flat(e.position,s.beacon.position)),n1(e.position and s.beacon.position and
            e.position.z-s.beacon.position.z)))or'',n1(pelicans.release_wait({stage=e.stage,released=true}))))
    elseif e.kind=='held'then
        local r=e.result
        mod:log(('PELICAN HELD: entity %d: departs %s s after its release (native %s s); verified %s'):format(e.entity,
            n1(r.seconds),n1((r.native-r.release)/1e6),tostring(r.verified)))
    elseif e.kind=='hold_refused'then
        mod:log(('PELICAN HOLD REFUSED: entity %d: %s: %s (nothing written)'):format(e.entity,tostring(e.code),
            tostring(e.reason)))
    elseif e.kind=='departing'then
        mod:log(('PELICAN DEPARTING: entity %d: stage %d, %s s after its release; at %s'):format(e.entity,e.stage,
            n1(e.after_release),at(e.position)))
    elseif e.kind=='gone'then
        local s=pelican_state[e.entity]
        pelican_state[e.entity]=nil
        mod:log(('PELICAN GONE: entity %d: %s s after it was first seen, %s s after its release, %s s after departing; '
            ..'held %s'):format(e.entity,n1(e.seconds),n1(e.after_release),n1(e.after_departing),
            e.held and('yes ('..n1(e.held.seconds)..' s)')or'no'))
        mod:log(('PELICAN SUMMARY: entity %d: hover after the release %s s (asked %s); fly-out and removal %s s (the '
            ..'game: about 14 s)'):format(e.entity,n1(e.after_release and e.after_departing and
            (e.after_release-e.after_departing)),e.held and n1(e.held.seconds)or'native 0.6',n1(e.after_departing)))
    elseif e.kind=='ended'then
        mod:log('PELICAN WATCH: the mission ended')
    end
end
local watch
local function start_watch()
    watch=assert(pelicans.watch({hold=hold_on and HOLD_SECONDS or nil,label='PelicanProbe'},on_event))
    mod:log(('PELICAN WATCH: running; hold %s'):format(hold_on and(HOLD_SECONDS..' s after each release')or'OFF (observe only)'))
end

------------------------------------------------------------------------------ the carrier allocation (ship) --
local allocation={key=nil,line=nil,waiting=nil}
local function allocate(world)
    local saved=loadout.saved(world)
    if not saved then return end
    local ids,set={},{}
    for k,pair in ipairs(saved.pairs or{})do ids[k]=pair.id;set[pair.id]=true end
    local key=table.concat(ids,',')
    if key==allocation.key then return end
    local a=allocator.allocate(world,allocator.DEFINITIONS,set)
    if not a.ready then
        if allocation.waiting~=a.reason then
            allocation.waiting=a.reason
            mod:log('CUSTOM CARRIER: waiting: '..tostring(a.reason))
        end
        return
    end
    allocation.key,allocation.waiting,allocation.line=key,nil,a.line
    local saved_names={}
    for k,id in ipairs(ids)do saved_names[k]=names_by_id[id]or tostring(id)end
    mod:log(a.line..' (read-only; saved loadout: '..table.concat(saved_names,', ')..')')
    for _,id in ipairs(a.order)do
        local d=a.assignments[id]
        if d then
            mod:log(('CUSTOM CARRIER: %s -> %s (type %d, stable id %d, class %s): the first of %d eligible, %d skipped as '
                ..'taken or reserved'):format(d.label,d.carrier,d.type,d.stable_id,tostring(d.class),d.eligible,d.skipped))
        else
            mod:log(('CUSTOM CARRIER: %s REFUSED: %s'):format(id,a.refused[id]))
        end
    end
end

------------------------------------------------------------------------------------------------ the loop --
local in_mission=false
hd2.every(0.05,function()
    local world=world_module.open()
    if not world then return end
    local state=hd2.game_state()
    if not(state and state.mission)then
        if in_mission then in_mission=false;activations,known={},{}end
        local ok,err=pcall(allocate,world)
        if not ok then mod:log('CUSTOM CARRIER: failed: '..tostring(err))end
        return
    end
    if not prove(world)then return end
    if not in_mission then
        in_mission=true
        if not(watch and watch.status=='active')then start_watch()end
    end
    poll_beacons(world)
end,{id='pelican-probe'})

hd2.input.bind('pelican_probe.hold',{key='Ctrl+F8',on_press=function()
    hold_on=not hold_on
    mod:log(('Ctrl+F8 [%s]: hold %s'):format(BUILD,hold_on and('ON ('..HOLD_SECONDS..' s after each release)')or
        'OFF (observe only)'))
    -- In a mission the watch restarts now; aboard the ship the old one stops and the next mission starts a new one.
    if in_mission then start_watch()elseif watch then watch.cancel();watch=nil end
end})
hd2.input.bind('pelican_probe.status',{key='Ctrl+F11',on_press=function()
    local world=world_module.open()
    local parts={}
    if world and prove(world)then
        for _,p in pairs(pelicans.list(world)or{})do
            parts[#parts+1]=('entity %d stage %s released %s cargo %s at %s'):format(p.entity,tostring(p.stage),
                tostring(p.released),p.cargo and pelicans.cargo_name(p.cargo)or'none',at(p.position))
        end
    end
    mod:log(('Ctrl+F11 [%s]: hold %s; %d Pelican(s): %s; allocation: %s'):format(BUILD,hold_on and'ON'or'OFF',#parts,
        #parts>0 and table.concat(parts,'; ')or'none',tostring(allocation.line or allocation.waiting or'not yet')))
end})
mod:log('loaded ('..BUILD..'): Ctrl+F8 hold on/off, Ctrl+F11 status')
