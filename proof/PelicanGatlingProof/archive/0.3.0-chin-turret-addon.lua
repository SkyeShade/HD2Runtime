local hd2=require('mods/skyeshade/hd2runtime')
-- PelicanGatlingProof 0.3.0: THE PELICAN'S OWN CHIN TURRET AS A GATLING SENTRY (research/docs/pelican-cas-F5FEE03DCFDB.md
-- section 19). Development only; solo host only. Install with PelicanCasProof (no other Pelican proof).
-- The chin turret keeps its entity, model, mount, node 41, parent link and movement. As soon as a Runtime Pelican's chin
-- turret exists and is uniquely identified (during its approach), through runtime/pelican_weapon.lua:
--   GATLING CONFIG: the Gatling Sentry is read from the game (its type records; a deployed Gatling Sentry's own records
--     when one exists): projectile, rate, casing, magazine. The turret's own ProjectileWeapon copy gets the Gatling's
--     projectile (148) and rate slot, the turret its current RPM (the Gatling Sentry's exact rate), in one guarded
--     transaction;
--   GATLING CASING: in that transaction, before the turret's first shot, its copy's casing (particles +0xB0, parameters
--     +0xD4) becomes the Gatling's; the first shot then picks the game's pooled Gatling casing effect;
--   GATLING AMMO: its own magazine copy gets 10x the Gatling Sentry's magazine capacity, full;
--   GATLING AI: the game's SetBehaviour with the Gatling Sentry's AI (213) while the turret is quiet, read back;
--   GATLING TARGET: every target change; no valid target for 2 s while firing: the AI's own transition back to search;
--   GATLING FIRE: rounds, the first shot's chambered round;
--   GATLING ORBIT: the live-proven orbit (spiral entry, 40 m, 60 m above the beacon, guarded flight-target updates).
-- No spin-up, no Gatling entity, nothing shared written (the type records are compared whole before and after).
-- Keys (each applies to Pelicans seen from then on): Ctrl+Shift+F2 rate (the Gatling Sentry's -> 600 -> 1000);
-- Ctrl+F9 AI 213 on/off; Ctrl+F10 pattern on/off; Ctrl+F11 orbit on/off; Ctrl+Shift+F1 status.
local mod=hd2.mod()
local BUILD='0.3.0 GATLING CHIN-TURRET BUILD'
mod:log('PelicanGatlingProof '..BUILD..' (solo host): call Pelican CAS (PelicanCasProof) near enemies. As soon as its '
    ..'chin turret exists: GATLING CONFIG (the Gatling Sentry read from the game; projectile 148 at its exact rate), '
    ..'GATLING CASING (the Gatling casing before the first shot), GATLING AMMO (10x the Gatling magazine), GATLING AI '
    ..'(behaviour BEFORE = 645, AFTER = 213), then GATLING ORBIT (40 m, 60 m up), GATLING TARGET, GATLING FIRE and '
    ..'GATLING SUMMARY. Ctrl+Shift+F2 rate, Ctrl+F9 AI, Ctrl+F10 pattern, Ctrl+F11 orbit, Ctrl+Shift+F1 status.')

-- INTERNAL modules (development only).
local pelicans=require('hd2runtime/runtime/pelicans')
local weapon=require('hd2runtime/runtime/pelican_weapon')
local gatling_turrets=require('hd2runtime/runtime/pelican_gatling')
local world_module=require('hd2runtime/runtime/event_world')
local CHIN,GATLING=weapon.RESOURCES.chin,weapon.RESOURCES.gatling
local RATES={'gatling',600,1000}
local config={rate=1,ai=true,pattern=false,orbit=true}
local ORBIT={radius=40,altitude=60,entry=15,interval=0.25,period=30,duration=55}
local STEP=0.25
local MAX_LINES=400
local function n1(v)return v and('%.1f'):format(v)or'?'end
local function rate_text(r)return r=='gatling'and'the Gatling Sentry\'s (read from the game)'or(r..' RPM')end
local function spec_text(s)
    return ('projectile 148, rate %s, casing Gatling, ammo %dx Gatling, AI requested %s, pattern %s, orbit %s, no-target '
        ..'release %s'):format(rate_text(s.rate),weapon.AMMO_FACTOR,s.ai and'213'or'none (read-only)',
        s.pattern and'on'or'off',s.orbit and'on'or'off',s.ai and'on (2 s)'or'off')
end

local tracked={}
local finished={}   -- Pelicans summarised already (never followed again)
local count=0
local clock=0
local assets={}
local function say(s,text)
    s.lines=(s.lines or 0)+1
    if s.lines<=MAX_LINES then mod:log(text)end
end
local function t(s)return n1(clock-s.first)end
local function firing(a)return a and((a.id==213 and a.stage==12)or(a.id==645 and a.stage==3))end

local function finish(s,world)
    if s.summarised then return end
    s.summarised=true
    if not s.turret then
        mod:log(('GATLING SUMMARY (#%d): Pelican %d: its chin turret was never identified'):format(s.n,s.pelican))
        return
    end
    local cfg=s.config
    local shared=world and cfg and gatling_turrets.shared_same(cfg.shared_before,gatling_turrets.shared(world))
    local o=s.orbit_stats
    mod:log(('GATLING SUMMARY (#%d): chin turret %d: AI behaviour field after the change %s, at the end %s (%d stage lines '
        ..'read 213); projectile %s; RPM %s (%s; measured while firing %s); magazine capacity %s rounds (the Gatling '
        ..'Sentry\'s %s x %d), %s rounds fired; casing %s; targets %d acquired, %d lost; %s s firing in all, %s s of it '
        ..'firing with no target (longest %s s); the 2 s no-target release ran %d time(s)%s; orbit %s; shared definitions '
        ..'unchanged %s'):format(s.n,s.turret,tostring(s.after),tostring(s.final_id),s.stage213,
        tostring(cfg and cfg.projectile_read),tostring(cfg and cfg.rpm_read),tostring(cfg and cfg.rpm_source),
        s.fire_time>0 and('%.0f RPM'):format(s.rounds/s.fire_time*60)or'?',tostring(s.ammo and s.ammo.capacity),
        tostring(s.ammo and s.ammo.reference),weapon.AMMO_FACTOR,s.rounds,s.casing_result or'not applied',s.acquired,s.lost,
        n1(s.fire_time),n1(s.nil_fire),n1(s.nil_fire_max),s.releases,s.release_refused>0 and(' ('..s.release_refused
        ..' refused)')or'',o and('radius %s m (asked %d), %s m up (asked %d), %s laps, %s'):format(n1(o.radius),
        ORBIT.radius,n1(o.height),ORBIT.altitude,n1(o.laps),o.reason)or(not s.spec.orbit and'off'or s.orbit_started and
        'running (no STOPPED line yet)'or'never started'),
        tostring(shared)))
end

local function orbit_event(s)
    return function(e)
        if e.kind=='started'then
            s.orbit_started=true
            say(s,('GATLING ORBIT (#%d): t=%s s: STARTED: centre %s (the beacon, the Pelican\'s anchor), radius %d m, %d m '
                ..'up, %d s; a %d s spiral climb from %s m up; a target every %s s (sweep, one lap every %d s)'):format(s.n,
                t(s),pelicans.text(e.center),ORBIT.radius,ORBIT.altitude,ORBIT.duration,ORBIT.entry,n1(e.from_height),
                ORBIT.interval,ORBIT.period))
        elseif e.kind=='established'then
            say(s,('GATLING ORBIT (#%d): t=%s s: ESTABLISHED: %d m around the beacon, %d m up'):format(s.n,t(s),
                ORBIT.radius,ORBIT.altitude))
        elseif e.kind=='sample'then
            s.orbit_samples=(s.orbit_samples or 0)+1
            if s.orbit_samples%5==1 then
                say(s,('GATLING ORBIT (#%d): t=%s s: %s: angle %s deg, radius %s m (asked %s), height %s m (asked %s), '
                    ..'speed %s m/s, %d retargets'):format(s.n,t(s),(e.phase or'?'):upper(),n1(e.angle),n1(e.radius),
                    n1(e.asked_radius),n1(e.height),n1(e.asked_height),n1(e.speed),e.writes))
            end
        elseif e.kind=='refused'then
            say(s,('GATLING ORBIT (#%d): RETARGET REFUSED: %s: %s'):format(s.n,tostring(e.code),tostring(e.reason)))
        elseif e.kind=='stopped'then
            local st=e.stats
            s.orbit_stats={radius=st.radius.mean,height=st.height.mean,laps=st.laps,reason=tostring(e.reason)}
            say(s,('GATLING ORBIT (#%d): t=%s s: STOPPED: %s; %d retargets (%d refused); once established radius %s..%s m '
                ..'(mean %s, asked %d), height %s..%s m (mean %s, asked %d), %s laps'):format(s.n,t(s),tostring(e.reason),
                e.writes,e.refusals,n1(st.radius.min),n1(st.radius.max),n1(st.radius.mean),ORBIT.radius,n1(st.height.min),
                n1(st.height.max),n1(st.height.mean),ORBIT.altitude,n1(st.laps)))
        end
    end
end

local function configure(world,s,label)
    local ref,rcode,rreason=weapon.reference(world)
    if ref then
        local g,c=ref,ref.chin
        say(s,('GATLING CONFIG (#%d): REFERENCE (read from the game, read-only): Gatling Sentry type: projectile %d, %s '
            ..'RPM, casing %s, magazine %s rounds; chin turret type: projectile %d, %s RPM, casing %s, magazine %s rounds; '
            ..'deployed Gatling Sentry: %s'):format(s.n,g.projectile,n1(g.rpm),weapon.hex(g.casing.particles),
            tostring(g.magazine and g.magazine.capacity),c.projectile,n1(c.rpm),weapon.hex(c.casing.particles),
            tostring(c.magazine and c.magazine.capacity),g.sentry and(('entity %d, current RPM %s, %s rounds; its %s'):format(
            g.sentry.entity,n1(g.sentry.currentRpm),tostring(g.sentry.rounds),weapon.casing_text(g.sentry.casing)))
            or'none'))
    else
        say(s,('GATLING CONFIG (#%d): REFERENCE unreadable: %s: %s'):format(s.n,tostring(rcode),tostring(rreason)))
    end
    s.casing_before=weapon.casing_state(world,s.turret,CHIN)
    local w0=pelicans.weapon_config(world,s.turret)
    s.chambered_at_config=w0 and w0.magazine and w0.magazine.chambered
    say(s,('GATLING CASING (#%d): BEFORE: chin turret %d: %s'):format(s.n,s.turret,weapon.casing_text(s.casing_before)))
    local r,code,reason=weapon.configure(world,s.pelican,{projectile=148,rpm=s.spec.rate,casing=true,
        pattern=s.spec.pattern,ammo=weapon.AMMO_FACTOR},label)
    if not r then
        say(s,('GATLING CONFIG (#%d): REFUSED: %s: %s'):format(s.n,tostring(code),tostring(reason)))
        return
    end
    local w=pelicans.weapon_config(world,s.turret)
    s.config={projectile_read=w and w.copy and w.copy.projectileType,rpm_read=w and w.currentRpm and('%.2f'):format(
        w.currentRpm),rpm_source=r.rpm_source,shared_before=r.shared_before}
    say(s,('GATLING CONFIG (#%d): APPLIED: chin turret %d: projectile %s (read back), current RPM %s (read back; %s), rate '
        ..'slot %s; %d guarded writes; shared definitions unchanged %s; verified %s'):format(s.n,s.turret,
        tostring(s.config.projectile_read),tostring(s.config.rpm_read),tostring(r.rpm_source),tostring(r.verify.rate_slot),
        r.writes,tostring(r.verify.shared),tostring(r.verified)))
    local cs=r.casing
    if cs.applied then
        s.casing_result=('the Gatling\'s %s (own record; its first shot picks the pooled effect)'):format(
            weapon.hex(cs.after.particles))
        say(s,('GATLING CASING (#%d): AFTER: chin turret %d: %s; the Gatling Sentry type\'s casing is %s'):format(s.n,
            s.turret,weapon.casing_text(cs.after),weapon.hex(r.reference.casing.particles)))
    else
        s.casing_result='NOT APPLIED: '..tostring(cs.reason)
        say(s,('GATLING CASING (#%d): NOT APPLIED: %s'):format(s.n,tostring(cs.reason)))
    end
    local a=r.ammo
    s.ammo=a
    if a then
        say(s,('GATLING AMMO (#%d): %s'):format(s.n,a.applied and(('the Gatling Sentry\'s magazine holds %d rounds (its '
            ..'type, read from the game; no spare magazines, no reload); the chin turret\'s own magazine now holds %d '
            ..'(%dx): %d loaded and one chambered, as the game fills a magazine (read back: capacity %s, rounds %s and %s, '
            ..'chambered %s, from its %s record; spare magazines %s, unchanged); shared magazines unchanged %s'):format(
            a.reference,a.capacity,weapon.AMMO_FACTOR,a.rounds,tostring(a.read and a.read.capacity),
            tostring(a.read and a.read.rounds),tostring(a.read and a.read.working),tostring(a.read and a.read.chambered),
            a.read and a.read.from or'?',tostring(a.read and a.read.spares),tostring(r.verify.shared)))
            or('NOT APPLIED: '..tostring(a.reason))))
    end
    say(s,('GATLING FIRE (#%d): chambered round at configuration: %s (loaded before the weapon copy: the first shot fires '
        ..'it; every later round is chambered from the copy, 148)'):format(s.n,tostring(s.chambered_at_config)))
    return r
end

local function step()
    clock=clock+STEP
    local world=world_module.open()
    local state=hd2.game_state()
    if not(world and state and state.mission)then
        if next(tracked)or assets.state then
            for _,s in pairs(tracked)do finish(s,nil)end
            tracked={};finished={};weapon.reset();assets={}
        end
        return
    end
    if assets.state~='ready'and assets.state~='failed'then
        local st,why=weapon.assets(world,STEP)
        if st~=assets.state then
            assets.state,assets.reason=st,why
            if st=='failed'then mod:log('GATLING CONFIG: the Gatling Sentry\'s package did not load: '..tostring(why))end
        end
    end
    local live=pelicans.behaviours(world,{[667]=true})or{}
    for _,entity in ipairs(pelicans.active())do
        if not tracked[entity]and not finished[entity]and live[entity]then
            count=count+1
            tracked[entity]={n=count,pelican=entity,spec={rate=RATES[config.rate],ai=config.ai,pattern=config.pattern,
                orbit=config.orbit},rounds=0,fire_time=0,nil_fire=0,nil_fire_max=0,nil_run=0,acquired=0,lost=0,releases=0,
                release_refused=0,stage213=0,first=clock}
            mod:log(('GATLING CONFIG (#%d): SEEN Runtime Pelican %d [%s]; %s'):format(count,entity,BUILD,
                spec_text(tracked[entity].spec)))
        end
    end
    for entity,s in pairs(tracked)do
        local p=live[entity]
        local label='PelicanGatlingProof '..BUILD..' #'..s.n
        -- 1. The chin turret, as soon as it exists and is unique.
        if p and not s.turret and not s.refused and p.stage>=1 and p.stage<=6 then
            local st=gatling_turrets.inspect(world,entity)
            if st and #st.attached==1 and st.turret and st.turret.behaviour==645 and st.mount and st.mount.slot then
                s.turret=st.turret.entity
                local a=weapon.ai_state(world,s.turret)
                say(s,('GATLING AI (#%d): FIELD: Pelican %d (stage %d), chin turret %d: Behavior record 0x%X; behaviour id '
                    ..'(address 0x%X) = %d; %s; t=%s s'):format(s.n,entity,p.stage,s.turret,a and a.record or 0,
                    a and a.idAddress or 0,a and a.id or-1,weapon.ai_text(a),t(s)))
            elseif st and #st.attached>1 then
                s.refused=true
                say(s,('GATLING CONFIG (#%d): REFUSED: %d turrets name Pelican %d; the chin turret is not unique'):format(
                    s.n,#st.attached,entity))
            end
        end
        -- 2. The configuration, once the package is resident.
        if s.turret and not s.configured and assets.state=='ready'then
            s.configured=true
            s.result=configure(world,s,label)
        elseif s.turret and not s.configured and assets.state=='failed'then
            s.configured=true
            say(s,('GATLING CONFIG (#%d): REFUSED: ASSET_UNAVAILABLE: %s'):format(s.n,tostring(assets.reason)))
        end
        -- 3. The AI, while quiet.
        if s.turret and s.spec.ai and s.result and not s.ai_done then
            local r,code,reason=weapon.switch_ai(world,entity,label)
            if r then
                s.ai_done=true;s.switched=true;s.after=r.after
                say(s,('GATLING AI (#%d): RESULT: chin turret %d: behaviour BEFORE = %d, behaviour AFTER = %d (read back), '
                    ..'stage %d; t=%s s'):format(s.n,r.turret,r.before,r.after,r.stage_after,t(s)))
            elseif code~='NOT_QUIET'then
                s.ai_done=true
                say(s,('GATLING AI (#%d): REFUSED: %s: %s'):format(s.n,tostring(code),tostring(reason)))
            end
        end
        -- 4. The orbit, once the Pelican is held over the beacon (pelicans.orbit waits for it).
        if p and s.spec.orbit and not s.orbit and s.result then
            local center=pelicans.anchor(world,entity)
            if center then
                local o,why=pelicans.orbit(entity,{center=center,radius=ORBIT.radius,altitude=ORBIT.altitude,
                    duration=ORBIT.duration,interval=ORBIT.interval,mode='sweep',period=ORBIT.period,entry=ORBIT.entry,
                    label='PelicanGatlingProof #'..s.n},orbit_event(s))
                s.orbit=o or{status='refused'}
                if not o then say(s,('GATLING ORBIT (#%d): REFUSED: %s'):format(s.n,tostring(why)))end
            end
        end
        -- 5. Every transition, target change, the no-target release, the rounds.
        if s.turret and not s.summarised then
            local a=weapon.ai_state(world,s.turret)
            if a then
                s.final_id=a.id
                local key=a.id..':'..a.stage
                if key~=s.last_key then
                    if s.switched and a.id==213 then s.stage213=s.stage213+1 end
                    say(s,('GATLING AI (#%d): STAGE t=%s s: chin turret %d: %s%s'):format(s.n,t(s),s.turret,
                        weapon.ai_text(a),firing(a)and' -- FIRING'or''))
                    s.last_key=key
                end
                if s.switched and a.id~=213 and not s.reverted then
                    s.reverted=true
                    say(s,('GATLING AI (#%d): CHECK t=%s s: the behaviour field reads %d after the change to 213'):format(s.n,
                        t(s),a.id))
                end
                if a.target~=s.last_target then
                    if a.target and not s.last_target then
                        s.acquired=s.acquired+1
                        say(s,('GATLING TARGET (#%d): t=%s s: acquired entity %d (%s)'):format(s.n,t(s),a.target,
                            weapon.ai_text(a)))
                    elseif not a.target then
                        s.lost=s.lost+1
                        say(s,('GATLING TARGET (#%d): t=%s s: LOST entity %d (%s)'):format(s.n,t(s),s.last_target,
                            weapon.ai_text(a)))
                    else
                        s.acquired=s.acquired+1
                        say(s,('GATLING TARGET (#%d): t=%s s: switched %d -> %d (%s)'):format(s.n,t(s),s.last_target,
                            a.target,weapon.ai_text(a)))
                    end
                    s.last_target=a.target
                end
                if firing(a)then
                    s.fire_time=s.fire_time+STEP
                    if not a.target then
                        s.nil_fire=s.nil_fire+STEP;s.nil_run=s.nil_run+STEP
                        s.nil_fire_max=math.max(s.nil_fire_max,s.nil_run)
                    else s.nil_run=0 end
                else s.nil_run=0 end
                -- The 2 s no-target release (the AI's own transition back to search).
                if s.switched and a.id==213 then
                    local ev=weapon.release_step(world,s.turret,label)
                    if ev and ev.kind=='released'then
                        s.releases=s.releases+1
                        say(s,('GATLING TARGET (#%d): t=%s s: NO-TARGET RELEASE #%d: %s'):format(s.n,t(s),s.releases,
                            ev.text))
                    elseif ev and ev.kind=='confirmed'then
                        say(s,('GATLING TARGET (#%d): t=%s s: NO-TARGET RELEASE #%d ran: the AI left its firing stage '
                            ..'itself (now stage %d)'):format(s.n,t(s),s.releases,ev.stage))
                    elseif ev and ev.kind=='refused'then
                        s.release_refused=s.release_refused+1
                        say(s,('GATLING TARGET (#%d): t=%s s: NO-TARGET RELEASE REFUSED: %s: %s'):format(s.n,t(s),
                            tostring(ev.code),tostring(ev.reason)))
                    end
                end
            end
            local w=pelicans.weapon_config(world,s.turret)
            local m=w and w.magazine
            if m and s.mag then
                local used=s.mag.rounds-m.rounds
                if used>0 then
                    s.rounds=s.rounds+used;s.window=(s.window or 0)+used
                    if not s.first_shot then
                        s.first_shot=true
                        local c=weapon.casing_state(world,s.turret,CHIN)
                        local ref=s.result and s.result.reference
                        local sentry=ref and ref.sentry and weapon.casing_state(world,ref.sentry.entity,
                            GATLING)
                        say(s,('GATLING CASING (#%d): FIRST SHOT t=%s s: %s%s'):format(s.n,t(s),weapon.casing_text(c),
                            sentry and sentry.cached~=0 and(sentry.cached==(c and c.cached)and(' -- the SAME pooled '
                            ..'casing effect as Gatling Sentry %d (#%d)'):format(ref.sentry.entity,sentry.cached)
                            or(' -- Gatling Sentry %d keeps #%d: not the same'):format(ref.sentry.entity,sentry.cached))
                            or''))
                        say(s,('GATLING FIRE (#%d): FIRST SHOT t=%s s: chambered now %s (the next round, from the copy)'
                            ):format(s.n,t(s),tostring(m.chambered)))
                    end
                end
            end
            s.mag=m or s.mag
            if (s.window or 0)>0 and clock>=(s.next_fire or 0)then
                s.next_fire=clock+2
                local am=weapon.ammo_state(world,s.turret)
                say(s,('GATLING FIRE (#%d): t=%s s: %d rounds since the last line, %d in all; %s; chambered %s; rounds left '
                    ..'%s of %s; %s RPM'):format(s.n,t(s),s.window,s.rounds,a and(firing(a)and'FIRING'or'not firing')or'?',
                    tostring(m and m.chambered),tostring(m and m.rounds),tostring(am and am.capacity),
                    w and w.currentRpm and('%.0f'):format(w.currentRpm)or'?'))
                s.window=0
            end
        end
        if not p then
            finish(s,world)
            tracked[entity]=nil;finished[entity]=true
        end
    end
end
hd2.every(STEP,step)
hd2.input.bind('pelican_gatling_proof.rate',{key='Ctrl+Shift+F2',on_press=function()
    config.rate=config.rate%#RATES+1
    mod:log(('Ctrl+Shift+F2 [%s]: rate %s for Pelicans seen from now on'):format(BUILD,rate_text(RATES[config.rate])))
end})
hd2.input.bind('pelican_gatling_proof.ai',{key='Ctrl+F9',on_press=function()
    config.ai=not config.ai
    mod:log(('Ctrl+F9 [%s]: AI 213 %s for Pelicans seen from now on'):format(BUILD,config.ai and'ON'or'OFF (read-only)'))
end})
hd2.input.bind('pelican_gatling_proof.pattern',{key='Ctrl+F10',on_press=function()
    config.pattern=not config.pattern
    mod:log(('Ctrl+F10 [%s]: the Gatling ammo pattern %s for Pelicans seen from now on'):format(BUILD,config.pattern
        and'ON'or'OFF'))
end})
hd2.input.bind('pelican_gatling_proof.orbit',{key='Ctrl+F11',on_press=function()
    config.orbit=not config.orbit
    mod:log(('Ctrl+F11 [%s]: the orbit %s for Pelicans seen from now on'):format(BUILD,config.orbit and'ON'or'OFF'))
end})
hd2.input.bind('pelican_gatling_proof.status',{key='Ctrl+Shift+F1',on_press=function()
    local k=0;for _ in pairs(tracked)do k=k+1 end
    mod:log(('Ctrl+Shift+F1 [%s]: next Pelican: %s; package %s; %d Pelican(s) followed'):format(BUILD,
        spec_text({rate=RATES[config.rate],ai=config.ai,pattern=config.pattern,orbit=config.orbit}),
        tostring(assets.state),k))
end})
mod:log('loaded ('..BUILD..'): '..spec_text({rate=RATES[config.rate],ai=config.ai,pattern=config.pattern,
    orbit=config.orbit})..'; Ctrl+Shift+F2 rate, Ctrl+F9 AI, Ctrl+F10 pattern, Ctrl+F11 orbit, Ctrl+Shift+F1 status')
