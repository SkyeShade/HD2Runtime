local hd2=require('mods/skyeshade/hd2runtime')
-- ExtractionPelicanProbe 0.1.0: THE EXTRACTION PELICAN, OBSERVED (research/docs/pelican-cas-F5FEE03DCFDB.md, "The
-- extraction Pelican"). Development only; READ-ONLY: nothing is written, spawned or called.
--
-- Research (offline, pinned): the extraction Pelican is the entity shuttle_gunship (the mission stratagem Extract,
-- type 148, delivers it like a vehicle's Pelican, from its beacon); its flight is behaviour 202, which it has from its
-- entity TYPE (the behaviour settings), not from the mission. Behaviour 202's holding stage 5 circles its anchor (a
-- 30 m constant, 30 m up), asks every update whether to abort (every helldiver gone) and whether to LAND (stage 6): a
-- player within 50 m of its landing point (its record +0x1B0) and mission-wide state. This probe watches a real one,
-- during a normal mission's extraction, to check that reading live:
--   * every behaviour-202 entity: its type, stages and their times, its targets against its anchor (the circle's real
--     radius and height), its landing point, the players near it, the two mission-wide values the decision reads;
--   * its chin turret (a behaviour-645 entity mounted on it): which weapon components hold it, its state changes.
-- Ctrl+Shift+F12: status.
local mod=hd2.mod()
local BUILD='0.1.0 EXTRACTION PELICAN PROBE'
mod:log('ExtractionPelicanProbe '..BUILD..' (read-only): play a normal mission to its extraction and call the '
    ..'extraction as usual. Expect "EXTRACTION PELICAN SEEN", "EXTRACTION PELICAN STAGE" lines, "EXTRACTION PELICAN '
    ..'CIRCLE" every 2 s while it holds (stage 5), "EXTRACTION PELICAN TURRET", then "EXTRACTION PELICAN GONE" and '
    ..'"EXTRACTION PELICAN SUMMARY". Nothing is written. Ctrl+Shift+F12: status.')

-- INTERNAL read-only readers (never written through here).
local pelicans=require('hd2runtime/runtime/pelicans')
local world_module=require('hd2runtime/runtime/event_world')
local PE=require('hd2runtime/domains/pelican')
local X=PE.extraction
local MISSION_STATE=0x3326D10      -- research "extraction": the landing decision's mission-wide state
local function n1(v)return v and('%.1f'):format(v)or'?'end
local function at(v)return v and('(%.1f, %.1f, %.1f)'):format(v.x,v.y,v.z)or'(?)'end
local function flat(a,c)
    if not(a and c)then return nil end
    return math.sqrt((a.x-c.x)^2+(a.y-c.y)^2)
end
local function components_text(c)
    local out={}
    for _,name in ipairs({'mount','turret','projectileWeapon','weaponData'})do
        out[#out+1]=name..' '..(c[name]and('#'..c[name])or'no')
    end
    return table.concat(out,', ')
end

local tracked={}
local seen_turrets={}
local count=0
local function players_near(point,radius)
    local n=0
    for _,p in ipairs(hd2.players())do
        local pos=p.position and p:position()
        if pos and point and math.sqrt((pos.x-point.x)^2+(pos.y-point.y)^2+(pos.z-point.z)^2)<=radius then n=n+1 end
    end
    return n
end
local function mission_state(world)
    local object=world.view.pointer(world.game+MISSION_STATE)
    if not object or object==0 then return'unreadable'end
    local a=world.view.u32(object+0x680)
    local raw=world.view.read(object+0x5194C,1)
    return ('+0x680 = %s, +0x5194C = %s'):format(tostring(a),raw and tostring(raw:byte())or'?')
end

local function step()
    local world=world_module.open()
    local state=hd2.game_state()
    if not(world and state and state.mission)then
        if next(tracked)then tracked={};seen_turrets={}end
        return
    end
    local list=pelicans.behaviours(world,{[X.behaviour]=true})
    if not list then return end
    local now=pelicans.clock(world)
    local turrets
    for entity,p in pairs(list)do
        local s=tracked[entity]
        local anchor=pelicans.anchor(world,entity)
        if not s then
            count=count+1
            s={n=count,first=now,stage=p.stage,stage_at=now,stages={},radii={},heights={},next_circle=now}
            tracked[entity]=s
            mod:log(('EXTRACTION PELICAN SEEN (#%d): entity %d, type %s (%s), behaviour %d (its type\'s own: %s), stage %d; '
                ..'at %s; its anchor %s; its landing point %s; its target %s; flags 0x%X'):format(s.n,entity,
                tostring(p.variant or'?'),tostring(p.resource),p.behaviour,tostring(p.resource and
                pelicans.type_behaviour(world,p.resource)),p.stage,at(p.position),at(anchor),at(p.landing),at(p.target),
                p.flags))
        end
        if p.stage~=s.stage then
            local dt=now and s.stage_at and(now-s.stage_at)/1e6
            s.stages[#s.stages+1]=('%d (%s s)'):format(s.stage,n1(dt))
            mod:log(('EXTRACTION PELICAN STAGE (#%d): entity %d: %d -> %d after %s s in it (%s s since seen); at %s (%s m '
                ..'from its anchor horizontally, %s m above it); target %s; players within 50 m of its landing point: %d; '
                ..'mission state %s'):format(s.n,entity,s.stage,p.stage,n1(dt),n1(now and s.first and(now-s.first)/1e6),
                at(p.position),n1(flat(p.position,anchor)),n1(p.position and anchor and p.position.z-anchor.z),at(p.target),
                players_near(p.landing,X.landingRadius),mission_state(world)))
            s.stage,s.stage_at=p.stage,now
        end
        if p.stage==X.holdingStage and now and now>=s.next_circle then
            s.next_circle=now+2e6
            local tr,th=flat(p.target,anchor),p.target and anchor and p.target.z-anchor.z
            if tr then s.radii[#s.radii+1]=tr end
            if th then s.heights[#s.heights+1]=th end
            mod:log(('EXTRACTION PELICAN CIRCLE (#%d): entity %d: its target %s m from its anchor horizontally, %s m above '
                ..'it (the code\'s constants: %d m, %d m); the Pelican %s m out, %s m up; players within %d m of its '
                ..'landing point: %d; mission state %s'):format(s.n,entity,n1(tr),n1(th),X.circleRadius,X.circleHeight,
                n1(flat(p.position,anchor)),n1(p.position and anchor and p.position.z-anchor.z),X.landingRadius,
                players_near(p.landing,X.landingRadius),mission_state(world)))
        end
        -- Its chin turret: a behaviour-645 entity within 15 m (read once per turret).
        turrets=turrets or pelicans.behaviours(world,{[645]=true})or{}
        for t,tp in pairs(turrets)do
            if not seen_turrets[t]and flat(tp.position,p.position)and flat(tp.position,p.position)<=15 then
                seen_turrets[t]=entity
                mod:log(('EXTRACTION PELICAN TURRET (#%d): entity %d (type %s, behaviour %d, stage %d) %s m from it; '
                    ..'weapon components: %s'):format(s.n,t,tostring(tp.variant or tp.resource),tp.behaviour,tp.stage,
                    n1(math.sqrt((tp.position.x-p.position.x)^2+(tp.position.y-p.position.y)^2
                    +(tp.position.z-p.position.z)^2)),components_text(pelicans.weapon_components(world,t))))
            end
        end
    end
    for entity,s in pairs(tracked)do
        if not list[entity]then
            tracked[entity]=nil
            local function mean(t)local sum=0;for _,v in ipairs(t)do sum=sum+v end;return #t>0 and sum/#t or nil end
            s.stages[#s.stages+1]=('%d (until gone)'):format(s.stage)
            mod:log(('EXTRACTION PELICAN GONE (#%d): entity %d, %s s after it was seen'):format(s.n,entity,
                n1(now and s.first and(now-s.first)/1e6)))
            mod:log(('EXTRACTION PELICAN SUMMARY (#%d): stages %s; while it held (stage %d): its target %s m from its '
                ..'anchor on average (%d samples), %s m above it'):format(s.n,table.concat(s.stages,' > '),X.holdingStage,
                n1(mean(s.radii)),#s.radii,n1(mean(s.heights))))
        end
    end
end
hd2.every(0.5,step)
hd2.input.bind('extraction_pelican_probe.status',{key='Ctrl+Shift+F12',on_press=function()
    local k=0;for _ in pairs(tracked)do k=k+1 end
    mod:log(('Ctrl+Shift+F12 [%s]: %d extraction Pelican(s) followed now, %d seen in all; read-only'):format(BUILD,k,count))
end})
mod:log('loaded ('..BUILD..'): read-only; Ctrl+Shift+F12 status')
