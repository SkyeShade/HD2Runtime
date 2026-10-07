local hd2=require('mods/skyeshade/hd2runtime')
-- PelicanTurretProbe 0.3.0: WHAT THE TURRET FIRES, AND WHAT OF IT IS PER INSTANCE (research/docs/pelican-cas-
-- F5FEE03DCFDB.md section 15). READ-ONLY: nothing is written, created or called.
-- Research (pinned): the projectile a turret fires comes from its weapon record's flags (the components it has). A
-- magazine turret (the chin turret, the Gatling Sentry) fires its magazine record's chambered type, re-derived after
-- every shot from its magazine pattern (the Gatling: 148,148,148,242,148) or, with no pattern (the chin turret), from
-- its resolved ProjectileWeapon +0. "Resolved" is the entity's own per-instance copy when an entity delta made one at
-- creation, else its TYPE's shared record. The shot interval (60 / RPM) is per instance, set once at creation.
-- Spin-up is a separate component (weapon_wind_up) the chin turret does not have.
-- Now, for every chin turret and Gatling Sentry: TURRET WEAPON (its path, flags, own copies or none, interval and RPM,
-- magazine record, heat and wind-up), and for every chin turret GATLING CONFIG: each value a Gatling configuration
-- would change and whether this turret has a per-instance home for it. While they fire: TURRET FIRE (rounds and the
-- chambered type). Ctrl+Shift+F5: status.
-- PelicanTurretProbe 0.2.0: THE PARENT/CHILD LINK, READ (research/docs/pelican-cas-F5FEE03DCFDB.md, "The turret as a
-- child entity"). READ-ONLY.
-- 0.1.0 live: every Runtime Pelican's chin turret exists (entity = the Pelican's + 1) and acts (its Behavior record
-- cycles), but its transform position stays where it was created, so "within 15 m" mostly missed it. Research since
-- (pinned): a mounted child's ATTACHABLE record (0xAC) names its parent by the parent's handle link (+0xC) at +0x0 and
-- the parent's node at +0x4, then a world position and rotation. Now for every turret: its attachable record (link,
-- node, world position), its parent found BY THAT LINK (a Runtime Pelican or not), and every 2 s its attachable
-- position against its parent's pose (does it follow?) and its transform position (stale?). For a Gatling Sentry the
-- same record shows what a ground turret's link is.
-- PelicanTurretProbe 0.1.0: THE PELICAN'S CHIN TURRET AND THE GATLING SENTRY, OBSERVED
-- (research/docs/pelican-cas-F5FEE03DCFDB.md, "The Pelican's turret"). Development only; READ-ONLY.
--
-- Research (offline): the transport Pelican (shuttle_transport) and the extraction Pelican (shuttle_gunship) both
-- mount the same chin turret, a separate entity (shuttle_gunship_turret_hmg, behaviour 645) spawned on their
-- attach_front_turret node from their entity type's MountComponentData (a shared definition). The A/G-16 Gatling
-- Sentry is its own entity (hellpod/turret/gatling_turret, behaviour 213) with the same kind of weapon chain (turret,
-- targeting, weapon data, projectile weapon, magazine, wind-up). Whether one Pelican's turret can take the Gatling's
-- weapon PER INSTANCE is not established; this probe gathers the live evidence first, writing nothing:
--   * every chin turret (behaviour 645) and every Gatling Sentry (behaviour 213): its entity, type, position, the
--     Pelican it rides (the nearest behaviour 667 / 202 entity within 15 m, and whether the Runtime spawned it), which
--     weapon components hold it (mount, turret, projectile weapon, weapon data), and its Behavior state: the offsets
--     of its record that change while it lives (targeting and firing show there);
--   * for every Runtime Pelican: whether a chin turret rides it.
-- Spawn a Pelican with PelicanSpawnProof (Ctrl+F8) or PelicanCasProof, and place a Gatling Sentry near enemies.
-- Ctrl+Shift+F5: status.
local mod=hd2.mod()
local BUILD='0.3.0 TURRET WEAPON CONFIG PROBE'
mod:log('PelicanTurretProbe '..BUILD..' (read-only): in a mission, call a Runtime Pelican (PelicanSpawnProof Ctrl+F8 '
    ..'or Pelican CAS) and a Gatling Sentry near enemies. Expect "TURRET SEEN", "TURRET WEAPON" and (chin turret) '
    ..'"GATLING CONFIG" lines, "TURRET FIRE" lines while they shoot, "RUNTIME PELICAN TURRET", and "TURRET GONE". '
    ..'Nothing is written. Ctrl+Shift+F5: status.')

-- INTERNAL read-only readers (never written through here).
local pelicans=require('hd2runtime/runtime/pelicans')
local world_module=require('hd2runtime/runtime/event_world')
local TURRETS={[645]='the Pelican chin turret',[213]='the Gatling Sentry'}
local PARENTS={[667]=true,[202]=true}
local function n1(v)return v and('%.1f'):format(v)or'?'end
local function at(v)return v and('(%.1f, %.1f, %.1f)'):format(v.x,v.y,v.z)or'(?)'end
local function dist(a,c)
    if not(a and c)then return nil end
    return math.sqrt((a.x-c.x)^2+(a.y-c.y)^2+(a.z-c.z)^2)
end
local function components_text(c)
    local out={}
    for _,name in ipairs({'mount','turret','projectileWeapon','weaponData'})do
        out[#out+1]=name..' '..(c[name]and('#'..c[name])or'no')
    end
    return table.concat(out,', ')
end
-- The 4-byte words of a record that differ (offsets), at most `limit` listed.
local function changed(a,c,limit)
    local out,n={},0
    for o=0,#a-4,4 do
        if a:sub(o+1,o+4)~=c:sub(o+1,o+4)then
            n=n+1
            if #out<limit then out[#out+1]=('+0x%X'):format(o)end
        end
    end
    return n,table.concat(out,' ')
end

-- 0.3.0: what it fires, and what of it is per instance.
local TYPES=pelicans.turret_types
local function n0(v)return v and('%.0f'):format(v)or'?'end
local function weapon_text(w)
    if not w then return'NOT a projectile weapon'end
    local m=w.magazine
    return ('path %s (flags 0x%X); its own resolved ProjectileWeapon: %s; shot interval %s s = %s RPM (current %s, '
        ..'slots %s/%s/%s, index %s); magazine: %s; weapon_heat %s; wind-up (spin-up) %s'):format(w.path,w.flags or 0,
        w.copy and('YES (projectile '..w.copy.projectileType..', RPM '..n0(w.copy.rpm and w.copy.rpm.y)..')')
            or'none (it uses its type\'s shared record)',w.interval and('%.4f'):format(w.interval)or'?',n0(w.rpm),
        n0(w.currentRpm),n0(w.rofSlots and w.rofSlots.x),n0(w.rofSlots and w.rofSlots.y),n0(w.rofSlots and w.rofSlots.z),
        tostring(w.rofIndex),m and(('%d rounds, pattern %s, chambered %d, length %d, own copy %s'):format(m.rounds,
            m.pattern and'on'or'off',m.chambered,m.length,m.copy and'YES'or'none'))or'none',w.heat and'yes'or'no',
        w.windUp and'yes'or'no')
end
-- For a chin turret: each value a Gatling configuration changes, and whether this turret has a per-instance home for it.
local function gatling_lines(n,entity,w)
    local hmg,gat=TYPES.chinTurret,TYPES.gatlingSentry
    local m=w.magazine
    local fires=w.path=='magazine'and m and m.chambered~=0 and m.chambered or(w.copy and w.copy.projectileType)
        or hmg.projectileType
    local lines={
        ('projectile %s -> %d: from %s; per instance only through its own resolved ProjectileWeapon copy: %s'):format(
            tostring(fires),gat.projectileType,m and not m.pattern and'the resolved ProjectileWeapon +0 (no pattern)'
            or w.path,w.copy and'PRESENT'or'ABSENT (its type record is shared by every chin turret)'),
        ('rate %s -> %d RPM: the shot interval +0xC is this instance\'s own (%s s now); the ROF record and current RPM '
            ..'too'):format(n0(w.rpm),gat.rpmSlots[2],w.interval and('%.4f'):format(w.interval)or'?'),
        ('pattern %s -> on (%s): the magazine pattern is %s'):format(hmg.magazinePattern and'on'or'off',
            table.concat(gat.pattern,','),m and m.copy and'this instance\'s own copy'or'type data (shared)'),
        ('spin-up: wind-up component %s; the Gatling\'s is its own component, not weapon data'):format(
            w.windUp and'present'or'absent')}
    for k,text in ipairs(lines)do mod:log(('GATLING CONFIG (#%d) %d/%d: entity %d: %s'):format(n,k,#lines,entity,text))end
    mod:log(('GATLING CONFIG (#%d): verdict: %s. Nothing written (read-only).'):format(n,w.copy
        and'a per-instance ProjectileWeapon copy exists: its projectile type and RPM have a per-instance home'
        or'NO per-instance home for the projectile type on this turret (a copy would need the engine\'s own copy routine)'))
end

local tracked={}
local runtime_checked={}
local count=0
local clock=0
-- The parent a child's attachable record names (its handle link), among the Pelicans and Gatling Sentries now.
local function linked_parent(world,parents,link)
    for entity,p in pairs(parents)do
        local h=pelicans.handle(world,entity)
        if h and h.link==link then return p,h end
    end
end
local function nearest_parent(parents,position)
    local best,bd
    for entity,p in pairs(parents)do
        local d=dist(p.position,position)
        if d and d<=15 and(not bd or d<bd)then best,bd=p,d end
    end
    return best,bd
end
local function step()
    clock=clock+0.5
    local world=world_module.open()
    local state=hd2.game_state()
    if not(world and state and state.mission)then
        if next(tracked)then tracked={};runtime_checked={}end
        return
    end
    local ids={}
    for id in pairs(TURRETS)do ids[id]=true end
    local turrets=pelicans.behaviours(world,ids)
    local parents=pelicans.behaviours(world,PARENTS)
    if not(turrets and parents)then return end
    for entity,t in pairs(turrets)do
        local s=tracked[entity]
        local att=pelicans.attachable(world,entity)
        local linked=att and linked_parent(world,parents,att.link)
        local lp=linked and pelicans.pose(world,linked.entity)
        local parent,d=nearest_parent(parents,t.position)
        if not s then
            count=count+1
            s={n=count,first=clock,raw=t.raw,stage=t.stage,changes=0,next_state=clock+1,parent=parent and parent.entity}
            tracked[entity]=s
            mod:log(('TURRET SEEN (#%d): %s: entity %d, type %s, behaviour %d (stage %d, flags 0x%X), at %s; rides %s; '
                ..'weapon components: %s'):format(s.n,TURRETS[t.behaviour],entity,tostring(t.variant or t.resource),
                t.behaviour,t.stage,t.flags,at(t.position),parent and(('the %s %d (behaviour %d%s), %s m away'):format(
                tostring(parent.variant or'entity'),parent.entity,parent.behaviour,pelicans.owned(parent.entity)
                and', a Runtime Pelican'or'',n1(d)))or'nothing (no Pelican within 15 m)',
                components_text(pelicans.weapon_components(world,entity))))
            local own=pelicans.handle(world,entity)
            mod:log(('TURRET LINK (#%d): entity %d: its handle link 0x%X; attachable %s; its parent by that link: %s; its '
                ..'transform at %s'):format(s.n,entity,own and own.link or 0,att and('record #'..att.index..': parent link 0x'
                ..('%X'):format(att.link)..', node '..att.node..', world position '..at(att.position))or'NONE (not attached)',
                linked and(('the %s %d (behaviour %d%s; entity id %s its own)'):format(tostring(linked.variant or'entity'),
                linked.entity,linked.behaviour,pelicans.owned(linked.entity)and', a Runtime Pelican'or'',
                linked.entity+1==entity and'+1 ='or'not +1 of'))or'none among the Pelicans',at(t.position)))
            local w=pelicans.weapon_config(world,entity)
            s.weapon=w
            mod:log(('TURRET WEAPON (#%d): %s, entity %d: %s'):format(s.n,TURRETS[t.behaviour],entity,weapon_text(w)))
            if w and t.behaviour==645 then gatling_lines(s.n,entity,w)end
        elseif clock>=s.next_state then
            local w=pelicans.weapon_config(world,entity)
            local was=s.weapon and s.weapon.magazine
            local m=w and w.magazine
            if m and was and(m.rounds~=was.rounds or m.chambered~=was.chambered)then
                s.fire=(s.fire or 0)+1
                if s.fire<=40 then
                    mod:log(('TURRET FIRE (#%d): entity %d t=%s s: rounds %d -> %d, chambered %d -> %d; interval %s s'):format(
                        s.n,entity,n1(clock-s.first),was.rounds,m.rounds,was.chambered,m.chambered,
                        w.interval and('%.4f'):format(w.interval)or'?'))
                end
            end
            if w and s.weapon and(w.copy~=nil)~=(s.weapon.copy~=nil)then
                mod:log(('TURRET WEAPON (#%d): entity %d: its own resolved ProjectileWeapon is now %s'):format(s.n,entity,
                    w.copy and'PRESENT'or'absent'))
            end
            s.weapon=w or s.weapon
            s.next_state=clock+1
            if att and lp and clock>=(s.next_follow or 0)then
                s.next_follow=clock+2
                mod:log(('TURRET FOLLOW (#%d): entity %d: its attachable world position %s, %s m from its parent %d at '
                    ..'%s; its transform %s (%s m from its parent)'):format(s.n,entity,at(att.position),
                    n1(dist(att.position,lp.position)),linked.entity,at(lp.position),at(t.position),
                    n1(dist(t.position,lp.position))))
            end
            local n,list=changed(s.raw,t.raw,8)
            if n>0 or t.stage~=s.stage then
                s.changes=s.changes+1
                if s.changes<=60 then
                    mod:log(('TURRET STATE (#%d): entity %d t=%s s: stage %d, flags 0x%X; %d record words changed in 1 s: '
                        ..'%s; %s'):format(s.n,entity,n1(clock-s.first),t.stage,t.flags,n,list,parent and(('%s m from its '
                        ..'Pelican'):format(n1(d)))or'no Pelican within 15 m'))
                end
            end
            s.raw,s.stage=t.raw,t.stage
        end
    end
    for entity,s in pairs(tracked)do
        if not turrets[entity]then
            tracked[entity]=nil
            mod:log(('TURRET GONE (#%d): entity %d after %s s; %d state changes seen'):format(s.n,entity,
                n1(clock-s.first),s.changes))
        end
    end
    -- Every Runtime Pelican: does a chin turret ride it?
    for _,entity in ipairs(pelicans.active())do
        local p=parents[entity]
        if p and not runtime_checked[entity]and p.stage and p.stage>=3 then
            runtime_checked[entity]=true
            local found,node
            local h=pelicans.handle(world,entity)
            for t,tt in pairs(turrets)do
                local a=pelicans.attachable(world,t)
                if tt.behaviour==645 and a and h and a.link==h.link then found,node=t,a.node end
            end
            mod:log(('RUNTIME PELICAN TURRET: Pelican %d (behaviour %d, stage %d, handle link 0x%X): %s'):format(entity,
                p.behaviour,p.stage,h and h.link or 0,found and('a chin turret rides it by its attachable link: entity '
                ..found..', node '..tostring(node))or'NO chin turret names it'))
        end
    end
end
hd2.every(0.5,step)
hd2.input.bind('pelican_turret_probe.status',{key='Ctrl+Shift+F5',on_press=function()
    local k=0;for _ in pairs(tracked)do k=k+1 end
    mod:log(('Ctrl+Shift+F5 [%s]: %d turret(s) followed now, %d seen in all; read-only'):format(BUILD,k,count))
end})
mod:log('loaded ('..BUILD..'): read-only; Ctrl+Shift+F5 status')
