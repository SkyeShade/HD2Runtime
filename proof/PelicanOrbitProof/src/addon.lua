local hd2=require('mods/skyeshade/hd2runtime')
-- PelicanOrbitProof 0.3.0: WHERE DOES THE PELICAN POINT? (research/docs/pelican-cas-F5FEE03DCFDB.md, "Orientation").
-- 0.2.0 is LIVE-PROVEN: the full 60 s, 0 refused, behaviour 667 and stage 6 throughout (1.6-1.9 laps). Two additions,
-- the orbit itself unchanged:
--   * READ-ONLY orientation sampling every 0.25 s while it orbits: its root position and rotation (the transform
--     record's quaternion), its forward (the rotation's Y axis), pitch and bank, its velocity, its angle on the circle,
--     the circle's tangent and the direction to its flight target; the angles between its forward and each. Logged once
--     a second ("ORBIT POSE") and summed up per run ("ORBIT ORIENTATION": which direction its nose follows);
--   * a LEAD mode (the default now): the target is always N m ahead of the Pelican along the circle (from its own
--     angle), so it flies along the tangent instead of chasing a clock. Ctrl+Shift+F7 cycles N: 10, 15, 20, 5 m.
--     Ctrl+Shift+F10 cycles the modes: lead, sweep, steps. No rotation is written: the question is whether the flight
--     faces its direction of travel by itself.
-- PelicanOrbitProof 0.2.0: THE ORBIT ENTRY, AND A FULL 60 S.
-- 0.1.0 is LIVE-PROVEN in part: the normal Pelican (behaviour 667) circled the centre on retargets (1.4 laps, stage 6,
-- 0 refused). Two fixes, nothing else changed:
--   * it stopped at 44.9 s: its flight record had moved in its component array and its 12-byte target straddled a page
--     boundary, which the guarded transaction refuses (by an error, which cancelled the orbit). The retarget now
--     writes each target as three aligned 4-byte members in the same transaction (the guard is unchanged), and the
--     orbit catches any error and stops cleanly;
--   * it went straight from its low hover (about 6 m up) to a target 60 m up and 40 m out. Now the ENTRY: for 15 s the
--     circle's radius and height grow smoothly from its hover to 40 m and 60 m while it starts to turn (a spiral climb),
--     then the orbit is ESTABLISHED. The same 0.25 s update interval: no extra writes.
-- PelicanOrbitProof 0.1.0: CAN THE NORMAL PELICAN CIRCLE A BEACON? (research/docs/pelican-cas-F5FEE03DCFDB.md,
-- "Retargeting a live Pelican" and "The orbit"). Development only; solo host; no weapons; not a public API.
--
-- The Pelican CAS hover is live-proven: the game's transport Pelican, spawned empty with the beacon as its anchor, holds
-- over it, steered by its flight component's target. This proof asks whether the SAME normal Pelican (behaviour 667,
-- never the extraction's behaviour 202) circles when the Runtime moves that per-instance target:
--   * Ctrl+Shift+F8: one empty Pelican (hd2.pelican.spawn) anchored at the CENTRE: the landing position of the last
--     beacon you threw in the last 2 minutes (read-only: its delivery is the game's own; a harmless one such as a
--     Resupply is best), else 30 m east of you. Held 65 s after its release;
--   * once released and held, the orbit (runtime/pelicans.lua, internal): radius 40 m, 60 m above the centre, 60 s;
--     every INTERVAL s one guarded per-instance retarget of its hover point (P+0x1BC and its flight record's target,
--     written together as the game's own move-to does) along the circle;
--       sweep: the target moves continuously, one lap every 30 s;
--       steps: the target jumps 45 degrees once the Pelican is within 8 m of it (the extraction's own rule);
--   * after 60 s the orbit puts the game's own hover point back; the hold ends 5 s later and the departure is the
--     game's (stage 8 pushes its own target).
-- Measured (logged every second): its angle around the centre, its radius, its height above the centre, its speed,
-- how far it trails its target, its stage and behaviour; a summary per run.
-- Ctrl+Shift+F9 cycles the update interval (0.25, 0.5, 1.0, 0.1 s); Ctrl+Shift+F10 the mode (sweep, steps);
-- Ctrl+Shift+F11 status. Never written: any shared Pelican definition, the beacon (only read), any carrier or weapon.
local mod=hd2.mod()
local BUILD='0.3.0 ORBIT ORIENTATION BUILD'
mod:log('PelicanOrbitProof '..BUILD..': in a SOLO mission, throw a harmless stratagem (a Resupply) where you want the '
    ..'centre ("ORBIT CENTRE: beacon"), then press Ctrl+Shift+F8. Expect "ORBIT RUN 1 REQUESTED", the empty Pelican '
    ..'flying in and hovering over the centre, "PELICAN HELD", then "ORBIT STARTED", a 15 s spiral climb (ENTRY), '
    ..'"ORBIT ESTABLISHED" and the Pelican circling 40 m around the centre, about 60 m up, "ORBIT SAMPLE" lines every '
    ..'second, "ORBIT POSE" lines (where its nose points), after the full 60 s "ORBIT STOPPED ... its hover point ... is '
    ..'back", "ORBIT SUMMARY", "ORBIT ORIENTATION", then "PELICAN DEPARTING" (the game\'s departure) and "PELICAN '
    ..'GONE". Ctrl+Shift+F7: the lead distance; Ctrl+Shift+F9: the update interval; Ctrl+Shift+F10: lead, sweep or '
    ..'steps; Ctrl+Shift+F11: status.')

-- INTERNAL (development, not public): the guarded orbit, and read-only Pelican and beacon readers.
local pelicans=require('hd2runtime/runtime/pelicans')
local beacon_reader=require('hd2runtime/runtime/beacon_redirect')
local beacons=require('hd2runtime/runtime/beacons')
local world_module=require('hd2runtime/runtime/event_world')

local RADIUS,ALTITUDE,DURATION,PERIOD,STEP,NEAR=40,60,60,30,45,8
local ENTRY=15
local HOLD=DURATION+5
local INTERVALS={0.25,0.5,1.0,0.1}
local MODES={'lead','sweep','steps'}
local LEADS={10,15,20,5}
local settings={interval=1,mode=1,lead=1}
local function lead()return LEADS[settings.lead]end
local function interval()return INTERVALS[settings.interval]end
local function mode()return MODES[settings.mode]end
local function n1(v)return v and('%.1f'):format(v)or'?'end
local function n2(v)return v and('%.2f'):format(v)or'?'end
local function at(v)return v and('(%.1f, %.1f, %.1f)'):format(v.x,v.y,v.z)or'(?)'end
local function flat(a,c)
    if not(a and c)then return nil end
    return math.sqrt((a.x-c.x)^2+(a.y-c.y)^2)
end

-- The last beacon you threw (read-only): its landing position, by game clock.
local last_beacon
local seen_beacons={}
local function beacon_step()
    local world=world_module.open()
    local state=hd2.game_state()
    if not(world and state and state.mission)then seen_beacons={};return end
    local list=beacon_reader.beacons(world)
    if not list then return end
    for entity,it in pairs(list)do
        if not seen_beacons[entity]and it.mode~=nil and it.counting then
            local where=beacons.position(world,entity)
            if where then
                seen_beacons[entity]=true
                last_beacon={entity=entity,position=where,clock=pelicans.clock(world),type=it.type}
                mod:log(('ORBIT CENTRE: beacon %d (type %d) landed at %s: the next run circles it (Ctrl+Shift+F8 within 2 '
                    ..'minutes)'):format(entity,it.type,at(where)))
            end
        end
    end
end

local run={n=0}
local current
local function pelican_event(r)
    return function(e)
        if e.kind=='spawned'then
            local res=e.result
            r.entity=res.entity
            r.behaviour=res.pelican and res.pelican.behaviour
            mod:log(('PELICAN SPAWNED (run %d): entity %d: empty, behaviour %s, its anchor %s (%s m from the centre)'):format(
                r.n,res.entity,tostring(res.pelican and res.pelican.behaviour),at(res.anchor_read),
                n1(flat(res.anchor_read,r.center))))
            local o,why=pelicans.orbit(res.entity,{center=r.center,radius=RADIUS,altitude=ALTITUDE,duration=DURATION,
                interval=r.interval,mode=r.mode,period=PERIOD,step=STEP,near=NEAR,entry=ENTRY,lead=r.lead,
                label='OrbitProof run '..r.n},
                r.orbit_event)
            if not o then mod:log('ORBIT REFUSED (run '..r.n..'): '..tostring(why))end
            r.orbit=o
        elseif e.kind=='hovering'then
            mod:log(('PELICAN HOVERING (run %d): entity %d at %s s; hover point %s, %s m from the centre'):format(r.n,
                e.entity,n1(e.seconds),at(e.target),n1(flat(e.target,r.center))))
        elseif e.kind=='held'then
            mod:log(('PELICAN HELD (run %d): entity %d: departs %s s after its release; verified %s'):format(r.n,e.entity,
                n1(e.result.seconds),tostring(e.result.verified)))
        elseif e.kind=='stage'then
            mod:log(('PELICAN STAGE (run %d): entity %d: %s -> %s at %s s; at %s'):format(r.n,e.entity,tostring(e.from),
                tostring(e.to),n1(e.seconds),at(e.position)))
        elseif e.kind=='departing'then
            mod:log(('PELICAN DEPARTING (run %d): entity %d: stage %d, %s s after its release (the game\'s departure)')
                :format(r.n,e.entity,e.stage,n1(e.after_release)))
        elseif e.kind=='gone'then
            mod:log(('PELICAN GONE (run %d): entity %d, %s s after it was spawned'):format(r.n,e.entity,n1(e.seconds)))
        elseif e.kind=='refused'or e.kind=='unverified'or e.kind=='hold_refused'or e.kind=='cargo'then
            mod:log(('PELICAN %s (run %d): %s: %s'):format(e.kind:upper(),r.n,tostring(e.code or e.spawned),
                tostring(e.reason or'')))
        end
    end
end
local function orbit_event(r)
    return function(e)
        if e.kind=='started'then
            r.started=true
            mod:log(('ORBIT STARTED (run %d): entity %d: %s, a target every %s s; centre %s, radius %d m, %d m above it, '
                ..'%d s; starting at %s degrees; ENTRY %s s: a spiral climb from %s m up'):format(r.n,e.entity,
                r.mode=='sweep'and('sweep, one lap every '..PERIOD..' s')or r.mode=='lead'and('lead, '..r.lead
                ..' m ahead along the circle')or('steps of '..STEP..' degrees within '..NEAR..' m'),n2(r.interval),at(e.center),RADIUS,ALTITUDE,DURATION,n1(e.theta0),n1(e.entry),n1(e.from_height)))
        elseif e.kind=='established'then
            mod:log(('ORBIT ESTABLISHED (run %d): entity %d at %s s: radius %d m, %d m up from now on'):format(r.n,e.entity,
                n1(e.seconds),RADIUS,ALTITUDE))
        elseif e.kind=='sample'then
            local world=world_module.open()
            local p=world and pelicans.read(world,e.entity)
            if p and r.behaviour and p.behaviour~=r.behaviour then r.behaviour_changed=p.behaviour end
            mod:log(('ORBIT SAMPLE (run %d) t=%s s %s: angle %s deg, radius %s m (asked %s), height %s m (asked %s), speed '
                ..'%s m/s, %s m from its target, stage %s, behaviour %s, %d retargets'):format(r.n,n1(e.seconds),
                (e.phase or'?'):upper(),n1(e.angle),n1(e.radius),n1(e.asked_radius),n1(e.height),n1(e.asked_height),
                n1(e.speed),n1(e.target_distance),tostring(e.stage),tostring(p and p.behaviour),e.writes))
        elseif e.kind=='refused'then
            mod:log(('ORBIT RETARGET REFUSED (run %d): %s: %s'):format(r.n,tostring(e.code),tostring(e.reason)))
        elseif e.kind=='stopped'then
            local s=e.stats
            r.stopped=true
            mod:log(('ORBIT STOPPED (run %d): %s'):format(r.n,tostring(e.reason)))
            local expected=r.mode=='sweep'and 360/PERIOD or nil
            mod:log(('ORBIT SUMMARY (run %d): %s mode, a target every %s s: %d retargets (%d refused) over %s s; it turned '
                ..'%s degrees (%s laps, %s deg/s%s); once established: radius %s..%s m (mean %s, asked %d); height %s..%s m '
                ..'above the centre '
                ..'(mean %s, asked %d); mean speed %s m/s; it stayed in stage 6, behaviour %s -> %s'):format(r.n,r.mode,
                n2(r.interval),e.writes,e.refusals,n1(s.seconds),n1(s.degrees),n2(s.laps),n1(s.angular),expected and
                (', the target '..n1(expected)..' deg/s')or'',n1(s.radius.min),n1(s.radius.max),n1(s.radius.mean),RADIUS,
                n1(s.height.min),n1(s.height.max),n1(s.height.mean),ALTITUDE,n1(s.speed),r.behaviour_changed and
                (tostring(r.behaviour)..' CHANGED to '..tostring(r.behaviour_changed))or tostring(r.behaviour or'?'),
                ((s.laps or 0)>=0.75 and(s.radius.mean or 0)>RADIUS*0.6 and'IT CIRCLED (judge the smoothness by eye)'
                or'IT DID NOT CIRCLE: see the samples')..(tostring(e.reason):find('is over',1,true)
                and', THE FULL '..DURATION..' s'or', STOPPED EARLY: '..tostring(e.reason))))
            local o=r.pose
            if o and o.n>0 then
                local function m(k)return o.sum[k]/o.n end
                local best,bk
                for _,k in ipairs({'tangent','velocity','target'})do
                    if not best or m(k)<best then best,bk=m(k),k end
                end
                mod:log(('ORBIT ORIENTATION (run %d): %s mode%s, %d samples once established (every 0.25 s): its nose '
                    ..'vs the circle\'s tangent %s deg on average (max %s), vs its velocity %s (max %s), vs the direction '
                    ..'to its flight target %s (max %s); its velocity vs the tangent %s; pitch %s..%s deg, bank %s..%s '
                    ..'deg -> its nose follows its %s best (%s deg)%s'):format(r.n,r.mode,r.mode=='lead'and(' '..r.lead
                    ..' m')or'',o.n,n1(m('tangent')),n1(o.max.tangent),n1(m('velocity')),n1(o.max.velocity),
                    n1(m('target')),n1(o.max.target),n1(m('vt')),n1(o.pmin),n1(o.pmax),n1(o.bmin),n1(o.bmax),
                    bk=='target'and'flight target'or bk,n1(best),m('tangent')<=15 and', IT FACES ITS DIRECTION OF '
                    ..'TRAVEL (within 15 deg)'or', it does NOT face the tangent'))
            end
        end
    end
end

local function start_run()
    if current and current.handle and current.handle:alive()then
        mod:log('Ctrl+Shift+F8: run '..current.n..' is still alive (one at a time)')
        return
    end
    local state=hd2.game_state()
    if not(state and state.mission)then mod:log('Ctrl+Shift+F8: not in a mission');return end
    if state.host~=true then mod:log('Ctrl+Shift+F8: host only');return end
    if #hd2.players()~=1 then mod:log('Ctrl+Shift+F8 REFUSED (proof scope): solo only');return end
    local world=world_module.open()
    local now=world and pelicans.clock(world)
    local center,source
    if last_beacon and now and last_beacon.clock and now-last_beacon.clock<=120e6 then
        center,source=last_beacon.position,('the beacon %d you threw %s s ago'):format(last_beacon.entity,
            n1((now-last_beacon.clock)/1e6))
    else
        local me=hd2.local_player()
        local p=me and me:position()
        if not p then mod:log('Ctrl+Shift+F8: your position is unreadable');return end
        center,source={x=p.x+30,y=p.y,z=p.z},'30 m east of you (no beacon in the last 2 minutes)'
    end
    run.n=run.n+1
    local r={n=run.n,center=center,interval=interval(),mode=mode(),lead=lead()}
    r.orbit_event=orbit_event(r)
    current=r
    r.handle=hd2.pelican.spawn({position=center,hover=HOLD,on_event=pelican_event(r)})
    mod:log(('ORBIT RUN %d REQUESTED [%s]: centre %s (%s); %s mode%s, a target every %s s; radius %d m, %d m up, %d s; '
        ..'the Pelican held %d s: status %s%s'):format(r.n,BUILD,at(center),source,r.mode,r.mode=='lead'and(' '..r.lead
        ..' m ahead')or'',n2(r.interval),RADIUS,ALTITUDE,
        DURATION,HOLD,r.handle.status,r.handle.code and(' '..r.handle.code..': '..tostring(r.handle.reason))or''))
end

hd2.every(0.1,beacon_step)

-- READ-ONLY orientation sampling (every 0.25 s while the current run orbits): its forward against the circle's
-- tangent, its velocity and the direction to its flight target (horizontal angles), its pitch and bank.
local function heading(x,y)return math.atan2(y,x)end
local function diff(a,c)
    local d=math.deg(a-c)
    while d>180 do d=d-360 end
    while d<-180 do d=d+360 end
    return math.abs(d)
end
local function pose_step()
    local r=current
    if not(r and r.entity and r.orbit and r.orbit.status=='orbiting'and r.orbit.phase=='established'and not r.stopped)then
        return
    end
    local world=world_module.open()
    if not world then return end
    local pose=pelicans.pose(world,r.entity)
    local t=pelicans.targets(world,r.entity)
    local now=pelicans.clock(world)
    if not(pose and now)then return end
    local o=r.pose or{n=0,sum={tangent=0,velocity=0,target=0,vt=0},max={tangent=0,velocity=0,target=0},k=0}
    r.pose=o
    local p=pose.position
    if o.prev and now>o.prev_t then
        local dt=(now-o.prev_t)/1e6
        local vx,vy=(p.x-o.prev.x)/dt,(p.y-o.prev.y)/dt
        local theta=math.atan2(p.y-r.center.y,p.x-r.center.x)
        local tx,ty=-math.sin(theta),math.cos(theta)          -- counter-clockwise (the orbit's direction)
        local hf=heading(pose.forward.x,pose.forward.y)
        local ht,hv=heading(tx,ty),heading(vx,vy)
        local hg=t and t.flight and heading(t.flight.x-p.x,t.flight.y-p.y)
        local a={tangent=diff(hf,ht),velocity=diff(hf,hv),target=hg and diff(hf,hg)or 0}
        local rot=pose.rotation
        local bank=math.deg(math.asin(math.max(-1,math.min(1,2*(rot.x*rot.z-rot.w*rot.y)))))
        o.n=o.n+1
        for k,v in pairs(a)do o.sum[k]=o.sum[k]+v;o.max[k]=math.max(o.max[k],v)end
        o.sum.vt=o.sum.vt+diff(hv,ht)
        o.pmin,o.pmax=math.min(o.pmin or pose.pitch,pose.pitch),math.max(o.pmax or pose.pitch,pose.pitch)
        o.bmin,o.bmax=math.min(o.bmin or bank,bank),math.max(o.bmax or bank,bank)
        o.k=o.k+1
        if o.k%4==0 then
            mod:log(('ORBIT POSE (run %d): yaw %s deg, pitch %s, bank %s; at angle %s deg on the circle; its nose vs the '
                ..'tangent %s deg, vs its velocity %s (%s m/s), vs its flight target %s (%s m away)'):format(r.n,
                n1(pose.yaw),n1(pose.pitch),n1(bank),n1(math.deg(theta)),n1(a.tangent),n1(a.velocity),
                n1(math.sqrt(vx*vx+vy*vy)),n1(a.target),n1(t and t.flight and math.sqrt((t.flight.x-p.x)^2
                +(t.flight.y-p.y)^2))))
        end
    end
    o.prev,o.prev_t=p,now
end
hd2.every(0.25,pose_step)
hd2.input.bind('pelican_orbit_proof.run',{key='Ctrl+Shift+F8',on_press=start_run})
hd2.input.bind('pelican_orbit_proof.interval',{key='Ctrl+Shift+F9',on_press=function()
    settings.interval=settings.interval%#INTERVALS+1
    mod:log('Ctrl+Shift+F9: the next run retargets every '..n2(interval())..' s')
end})
hd2.input.bind('pelican_orbit_proof.lead',{key='Ctrl+Shift+F7',on_press=function()
    settings.lead=settings.lead%#LEADS+1
    mod:log('Ctrl+Shift+F7: the next lead run aims '..lead()..' m ahead along the circle')
end})
hd2.input.bind('pelican_orbit_proof.mode',{key='Ctrl+Shift+F10',on_press=function()
    settings.mode=settings.mode%#MODES+1
    mod:log('Ctrl+Shift+F10: the next run uses the '..mode()..' mode')
end})
hd2.input.bind('pelican_orbit_proof.status',{key='Ctrl+Shift+F11',on_press=function()
    local h=current and current.handle
    mod:log(('Ctrl+Shift+F11 [%s]: next run: %s mode (lead %d m), every %s s; last beacon %s; current run %s'):format(
        BUILD,mode(),lead(),n2(interval()),last_beacon and at(last_beacon.position)or'none',current and(current.n..': Pelican '..
        tostring(h and h.status)..' '..tostring(h and h.entity)..', orbit '..tostring(current.orbit and
        current.orbit.status))or'none'))
end})
mod:log('loaded ('..BUILD..'): Ctrl+Shift+F8 run, Ctrl+Shift+F7 lead, Ctrl+Shift+F9 interval, Ctrl+Shift+F10 mode, '
    ..'Ctrl+Shift+F11 status')
