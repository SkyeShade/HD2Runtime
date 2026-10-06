local hd2=require('mods/skyeshade/hd2runtime')
-- PelicanGatlingProof 0.5.0 (development only, solo host; docs/research/pelican-cas-F5FEE03DCFDB.md sections 19-24).
-- The Pelican CAS chin gun with its combat tuning FROZEN (the final Pelican CAS defaults for now):
--   * the Gatling Sentry's AI (behaviour 213) with the Runtime's target lock, spatial replacement and body facing
--     (sections 20-21), and the live-proven orbit;
--   * the MG-206's AP4 round 275 on its own ProjectileWeapon copy (section 23) at 3200 RPM (2x the Gatling Sentry's rate
--     read from the game), 100 mrad spread and zero aim recoil on its own WeaponData record (section 22), the Gatling
--     casing, and the 2047-round safe magazine refilled below 1500.
-- The 0.4.3-0.4.5 Mod Options tuning experiments are gone (runtime/pelican_weapon.lua keeps the per-instance operations).
-- Logging is lighter: the high-frequency diagnostics (aim error, body heading, fire, orbit samples, retained) are sampled
-- less often; nothing they do changes.
-- Keys (each applies to Pelicans seen from then on): Ctrl+F9 AI 213 on/off; Ctrl+F11 orbit on/off; Ctrl+Shift+F4 body
-- facing on/off; Ctrl+Shift+F1 status.
local mod=hd2.mod()
local BUILD='0.5.0 GATLING ATTRIBUTION BUILD'
mod:log('PelicanGatlingProof '..BUILD..' (solo host): call Pelican CAS (PelicanCasProof) near enemies. Expect GATLING CONFIG '
    ..'(read from the game), GATLING TUNING (FROZEN: spread 100 mrad, rate 3200 RPM, AP4 projectile 275, zero aim '
    ..'recoil), GATLING AP, GATLING AMMO, GATLING AI (behaviour AFTER = 213), GATLING ORBIT, TARGET LOCKED / RELEASED / '
    ..'TRANSITION, GATLING ATTRIBUTION, KILL CREDIT and GATLING SUMMARY. Ctrl+F9 AI, Ctrl+F11 orbit, Ctrl+Shift+F4 body '
    ..'facing, Ctrl+Shift+F1 status.')

-- INTERNAL modules (development only).
local pelicans=require('hd2runtime/runtime/pelicans')
local weapon=require('hd2runtime/runtime/pelican_weapon')
local heading=require('hd2runtime/runtime/pelican_heading')
local gatling_turrets=require('hd2runtime/runtime/pelican_gatling')
local world_module=require('hd2runtime/runtime/event_world')
local CHIN,GATLING=weapon.RESOURCES.chin,weapon.RESOURCES.gatling
-- The frozen combat tuning: the Gatling Sentry's rate read from the game x 2, 100 mrad, the AP4 round, zero recoil.
local FINAL={rate='gatling',rate_factor=2,spread=100,ap='ap4',recoil=true,pattern=false}
local config={ai=true,orbit=true,facing=true}
local ORBIT={radius=40,altitude=60,entry=15,interval=0.25,period=30,duration=55}
local STEP=0.25
local TARGET_STEP=0.05
local MAX_LINES=500
-- How often the high-frequency diagnostics log (seconds; their samples still feed the summary).
local EVERY={aim=10,heading=10,fire=10,retained=10,orbit=10,spread=5}
local function n1(v)return v and('%.1f'):format(v)or'?'end
local function n2(v)return v and('%.2f'):format(v)or'?'end
local function rate_text(r,factor)
    if r=='gatling'then
        return factor and factor~=1 and('the Gatling Sentry\'s x %g (read from the game)'):format(factor)
            or'the Gatling Sentry\'s (read from the game)'
    end
    return r..' RPM'
end
local function onoff(v)return v and'on'or'off'end
local function spread_text(v)return ('%g mrad'):format(v)end
-- The round a penetration setting fires: its projectile type and how it reads in the log.
local function round_of(ap)
    local A=weapon.AP4
    if ap=='ap4'then return A.projectile,('AP4: projectile %d, the %s\'s (damage %d, AP %d)'):format(A.projectile,A.name,
        A.damage,A.ap.apDirect)end
    return A.standard.projectile,('Standard: projectile %d, the %s\'s (damage %d, AP %d)'):format(A.standard.projectile,
        A.standard.name,A.standard.ap.damage,A.standard.ap.apDirect)
end
local function factor_text(f)return f==1 and'Normal'or('%gx'):format(f)end
local function spec_text(s)
    return ('round %s, rate %s, casing Gatling, ammo %d (safe maximum, refilled below %d), aim recoil %s, spread %s, AI '
        ..'%s, target lock %s, orbit %s, body facing %s'):format(select(2,round_of(s.ap)),rate_text(s.rate,s.rate_factor),
        weapon.AMMO_MAX,weapon.REFILL_BELOW,s.recoil and'ZERO (0 horizontal, 0 vertical)'or'chin turret\'s own',
        spread_text(s.spread),s.ai and'213'or'none (read-only)',onoff(s.ai),onoff(s.orbit),onoff(s.facing))
end
local function spec_now()
    return {rate=FINAL.rate,rate_factor=FINAL.rate_factor,spread=FINAL.spread,ap=FINAL.ap,recoil=FINAL.recoil,
        pattern=FINAL.pattern,ai=config.ai,orbit=config.orbit,facing=config.facing}
end
local function wrap(d)while d>180 do d=d-360 end;while d<-180 do d=d+360 end;return d end

local tracked={}
local finished={}   -- Pelicans summarised already (never followed again)
local count=0
local clock=0
local assets={}
local ap_assets={}
local function say(s,text)
    s.lines=(s.lines or 0)+1
    if s.lines<=MAX_LINES then mod:log(text)end
end
local function t(s)return n1(clock-s.first)end
local function firing(a)return a and((a.id==213 and a.stage==12)or(a.id==645 and a.stage==3))end
local function position_of(world,entity)
    local st=world_module.entity_state(world,entity)
    local unit=st and st.descriptor and st.descriptor.unit
    return unit and unit~=0 and world_module.unit_position(world,unit)or nil
end

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
    local A=s.aim
    local released={}
    for k,v in pairs(s.released)do released[#released+1]=k..' '..v end
    table.sort(released)
    local X=s.transitions
    mod:log(('GATLING SUMMARY (#%d): chin turret %d: AI behaviour field after the change %s, at the end %s; projectile %s; '
        ..'RPM %s (%s; measured while firing %s); magazine %s rounds (safe maximum), %d refills, %d rounds fired; casing '
        ..'%s; aim recoil %s; spread %s (last read %s); tuning selected %s, applied %s; targets: %d locked (%d spatial, %d the AI\'s pick; longest held %s s), %d restored, released '
        ..'%s, %d switched, %d exits ran (%d not consumed); %d transitions: %s m between targets on average (max %s), a %s '
        ..'degree turn on average (max %s); %s s firing in all, %s s of it with no target (longest %s s); aim error over '
        ..'%d samples: vertical %s m mean (%s deg), sideways %s m, the own-motion lead %s m of it vertically, aim point %s '
        ..'m above the target\'s root; body facing %s; orbit %s; shared definitions unchanged %s'):format(s.n,s.turret,
        tostring(s.after),tostring(s.final_id),tostring(cfg and cfg.projectile_read),tostring(cfg and cfg.rpm_read),
        tostring(cfg and cfg.rpm_source),s.fire_time>0 and('%.0f RPM'):format(s.rounds/s.fire_time*60)or'?',
        tostring(s.ammo and s.ammo.applied and s.ammo.capacity or'not set'),s.refills,s.rounds,
        s.casing_result or'not applied',s.recoil_result or'not changed',s.spread_result or'not changed',
        s.spread_last and(('%s, %s mrad%s'):format(tostring(s.spread_last.x),tostring(s.spread_last.y),
        s.spread_changed and', CHANGED after it was applied'or''))or'?',s.tuning and s.tuning.selected or'?',
        s.tuning and s.tuning.applied or'not applied',s.locks,s.spatial,s.locks-s.spatial,
        n1(s.longest_lock),s.restores,#released>0 and table.concat(released,', ')or'none',s.switches,s.exits,
        s.not_consumed,X.n,X.bn>0 and n1(X.between/X.bn)or'?',X.bn>0 and n1(X.maxb)or'?',
        X.tn>0 and n1(X.turn/X.tn)or'?',X.tn>0 and n1(X.maxt)or'?',n1(s.fire_time),
        n1(s.nil_fire),n1(s.nil_fire_max),A.n,A.n>0 and n2(A.v/A.n)or'?',A.n>0 and n2(A.vd/A.n)or'?',
        A.n>0 and n2(A.h/A.n)or'?',A.n>0 and n2(A.lead/A.n)or'?',A.nodes>0 and n2(A.node/A.nodes)or'?',
        s.spec.facing and(('%d turns, last error %s deg%s'):format(s.turns,n1(s.last_heading_error),
        s.heading_stopped and(', stopped: '..s.heading_stopped)or''))or'off',
        o and('radius %s m (asked %d), %s m up (asked %d), %s laps, %s'):format(n1(o.radius),ORBIT.radius,n1(o.height),
        ORBIT.altitude,n1(o.laps),o.reason)or(not s.spec.orbit and'off'or s.orbit_started and'running (no STOPPED '
        ..'line yet)'or'never started'),tostring(shared)))
    local T=s.attr
    if T then
        mod:log(('GATLING ATTRIBUTION (#%d): SUMMARY: chin turret %d: no-credit tag cleared %s%s; %d of its shots seen in '
            ..'the projectile pool: %d credited to you, %d to nobody, %d to another peer; %d kills by it (its last hit): '
            ..'entity_died credited %d to you, %d to nobody, %d to another player; full chain logged %s'):format(s.n,
            s.turret,tostring(T.applied),T.applied and''or(' ('..tostring(T.reason)..')'),T.shots,T.mine,T.none,T.other,
            T.kills,T.kills_mine,T.kills_none,T.kills_other,tostring(T.chain==true)))
    end
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
            if s.orbit_samples%math.floor(EVERY.orbit/ORBIT.interval)==1 then
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
    -- The rate factor tunes the Gatling rate read from the game.
    local factor=s.spec.rate=='gatling'and s.spec.rate_factor or 1
    -- The round: AP4 needs its donor's package; when that failed to load, the standard round (logged).
    local ap=s.spec.ap
    if ap=='ap4'and ap_assets.state~='ready'then
        say(s,('GATLING AP (#%d): AP4 NOT AVAILABLE: %s; the standard round instead'):format(s.n,
            tostring(ap_assets.reason or ap_assets.state)))
        ap='standard'
    end
    local projectile=round_of(ap)
    s.ap_used=ap
    local r,code,reason=weapon.configure(world,s.pelican,{projectile=projectile,rpm=s.spec.rate,rate_factor=factor,
        casing=true,pattern=s.spec.pattern,ammo=true,recoil=s.spec.recoil and'zero'or nil,spread=s.spec.spread,
        credit=true},label)
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
        say(s,('GATLING CASING (#%d): AFTER: chin turret %d: %s'):format(s.n,s.turret,weapon.casing_text(cs.after)))
    else
        s.casing_result='NOT APPLIED: '..tostring(cs.reason)
        say(s,('GATLING CASING (#%d): NOT APPLIED: %s'):format(s.n,tostring(cs.reason)))
    end
    if r.recoil then
        local rc=r.recoil
        s.recoil_result=rc.applied and(('ZERO applied: %s horizontal, %s vertical a shot (read back; was %s, %s)'):format(
            tostring(rc.after.x),tostring(rc.after.y),tostring(rc.before.x),tostring(rc.before.y)))
            or('NOT APPLIED: '..tostring(rc.reason))
        say(s,('GATLING CONFIG (#%d): AIM RECOIL: %s'):format(s.n,s.recoil_result))
    end
    if r.spread then
        local sp=r.spread
        local g=sp.gatling
        s.spread_result=sp.applied and(('%s applied: %s horizontal, %s vertical mrad (read back; the chin turret\'s own %s, '
            ..'%s; the Gatling Sentry\'s %s, %s, read from the game)'):format(sp.name,tostring(sp.after.x),
            tostring(sp.after.y),tostring(sp.before.x),tostring(sp.before.y),tostring(g and g.x),tostring(g and g.y)))
            or(('%s NOT APPLIED: %s'):format(sp.name,tostring(sp.reason)))
        say(s,('GATLING SPREAD (#%d): chin turret %d: %s; its own WeaponData instance record only (+0x58; a shot turns by '
            ..'up to half of each width each way); %d writes'):format(s.n,s.turret,s.spread_result,sp.writes or 0))
    end
    -- GATLING TUNING: the selected spread and rate, and what its own records read back.
    local after=r.spread and r.spread.applied and r.spread.after
    local spread_read=after and(after.x==after.y and('%g mrad'):format(after.x)or('%g/%g mrad'):format(after.x,after.y))
        or'not applied'
    local rate_read=w and w.currentRpm and('%.0f RPM'):format(w.currentRpm)or'?'
    local fired=s.config.projectile_read
    local penetration=fired==weapon.AP4.projectile and'AP4'or fired==weapon.AP4.standard.projectile and'Standard'
        or tostring(fired)
    s.tuning={selected=('spread %s, rate %s, %s'):format(spread_text(s.spec.spread),s.spec.rate=='gatling'
        and factor_text(s.spec.rate_factor)or rate_text(s.spec.rate),s.spec.ap=='ap4'and'AP4'or'Standard'),
        applied=('spread %s, rate %s, %s (projectile %s)'):format(spread_read,rate_read,penetration,tostring(fired))}
    -- GATLING AP: the round, its damage record and armor penetration, and the projectile rows unchanged.
    local A=weapon.AP4
    local d=r.donor
    say(s,('GATLING AP (#%d): %s; its own ProjectileWeapon copy names projectile %s (read back)%s; projectile rows '
        ..'(%d and %s) unchanged %s; shared definitions unchanged %s'):format(s.n,select(2,round_of(s.ap_used)),
        tostring(fired),d and(('; donor row read live: type %d, damage %d, %g m/s, mass %g; AP %d direct, %d slight, '
        ..'%d large, %d extreme, %d damage (%d durable); the casing stays the Gatling\'s'):format(d.projectile,d.damage,
        d.velocity,d.mass,A.ap.apDirect,A.ap.apSlight,A.ap.apLarge,A.ap.apExtreme,A.ap.standardDamage,
        A.ap.durableDamage))or'',A.standard.projectile,tostring(projectile),tostring(r.verify.rows),
        tostring(r.verify.shared)))
    say(s,('GATLING TUNING (#%d): %s (selected: %s; read back from its own records; the rate slot %s)'):format(s.n,
        s.tuning.applied,s.tuning.selected,tostring(r.verify.rate_slot)))
    -- GATLING ATTRIBUTION: who called it, and the chin turret's credit (its own no-credit tag cleared).
    local cr=r.credit or{}
    local me=hd2.local_player()
    local avatar=me and me:avatar()
    s.attr={caller_peer=me and me.peer,caller_avatar=avatar and avatar.id,asked_by=pelicans.request_owner(s.pelican),
        applied=cr.applied==true,before=cr.before,after=cr.after,reason=cr.reason,shots=0,mine=0,none=0,other=0,
        kills=0,kills_mine=0,kills_none=0,kills_other=0,victims={}}
    say(s,('GATLING ATTRIBUTION (#%d): SETUP: the call: Pelican %d asked for by %s (the Pelican CAS custom stratagem); '
        ..'the caller: the local player, peer %s, avatar %s (the solo host); chin turret %d: %s -> %s: %s'):format(s.n,
        s.pelican,tostring(s.attr.asked_by),tostring(s.attr.caller_peer),tostring(s.attr.caller_avatar),s.turret,
        weapon.credit_text(cr.before),weapon.credit_text(cr.after),cr.applied and('its shots are credited by the '
        ..'game\'s own Creditor to the owner of its network object, the host (expected creditor %s)'):format(
        cr.peer_lo and world_module.peer_hex(cr.peer_lo,cr.peer_hi)or'?')or('NOT APPLIED: '..tostring(cr.reason))))
    local a=r.ammo
    s.ammo=a
    if a then
        say(s,('GATLING AMMO (#%d): %s'):format(s.n,a.applied and(('its own magazine holds the safe maximum, %d rounds and '
            ..'one chambered (the rounds are an 11-bit network field: every shot saturates them to %d), refilled below '
            ..'%d; the Gatling Sentry\'s magazine is %d (read back: capacity %s, rounds %s and %s, chambered %s, from its '
            ..'%s record; spare magazines %s, unchanged)'):format(a.rounds,weapon.AMMO_MAX,weapon.REFILL_BELOW,a.reference,
            tostring(a.read and a.read.capacity),tostring(a.read and a.read.rounds),tostring(a.read and a.read.working),
            tostring(a.read and a.read.chambered),a.read and a.read.from or'?',tostring(a.read and a.read.spares)))
            or('NOT APPLIED: '..tostring(a.reason))))
    end
    say(s,('GATLING FIRE (#%d): chambered round at configuration: %s (loaded before the weapon copy: the first shot fires '
        ..'it; every later round is chambered from the copy, 148)'):format(s.n,tostring(s.chambered_at_config)))
    return r
end

-- The target controller's events.
local function target_events(s,list)
    for _,e in ipairs(list)do
        if e.kind=='locked'then
            s.locks=s.locks+1
            if e.how=='spatial'then s.spatial=s.spatial+1 end
            if s.lock_at then s.longest_lock=math.max(s.longest_lock or 0,clock-s.lock_at)end
            s.lock_at,s.los=clock,true
            say(s,('TARGET LOCKED (#%d): t=%s s: entity %d (%s), %s m from the muzzle, health %s, AI stage %d'):format(s.n,
                t(s),e.target,tostring(e.how),n1(e.state.distance),tostring(e.state.health),e.stage))
        elseif e.kind=='restored'then
            s.restores=s.restores+1
            say(s,('TARGET RESTORED (#%d): t=%s s: entity %d back as the AI\'s target through the game\'s target setter '
                ..'(%s), AI stage %d'):format(s.n,t(s),e.target,e.from and('its re-pick had taken entity '..e.from)
                or'it had lost it for a moment',e.stage))
        elseif e.kind=='transition'then
            local X=s.transitions
            X.n=X.n+1
            if e.between then X.bn=X.bn+1;X.between=X.between+e.between;X.maxb=math.max(X.maxb,e.between)end
            if e.turn then X.tn=X.tn+1;X.turn=X.turn+e.turn;X.maxt=math.max(X.maxt,e.turn)end
            say(s,('TARGET TRANSITION (#%d): t=%s s: %d -> %d (%s; the old one %s): old_pos %s, new_pos %s, '
                ..'distance_between_targets %s m, turret_yaw_delta %s deg (a %s degree turn in all, seen from the muzzle)')
                :format(s.n,t(s),e.from,e.to,tostring(e.how),tostring(e.reason),pelicans.text(e.from_pos),
                pelicans.text(e.to_pos),n1(e.between),n1(e.yaw),n1(e.turn)))
        elseif e.kind=='retained'then
            s.longest_lock=math.max(s.longest_lock or 0,e.since)
            if clock>=(s.next_retained_log or 0)then
                s.next_retained_log=clock+EVERY.retained
                say(s,('TARGET RETAINED (#%d): t=%s s: entity %d for %s s: health %s, %s m away, last seen %s s ago, AI '
                    ..'stage %d, its re-pick held %d times'):format(s.n,t(s),e.target,n1(e.since),tostring(e.state.health),
                    n1(e.state.distance),n1(e.state.seen),e.stage,e.holds))
            end
        elseif e.kind=='released'then
            s.released[e.reason]=(s.released[e.reason]or 0)+1
            -- A lock that died: its last hit, kept in case its health record is gone when its death is reported.
            if e.reason=='dead'and e.target and s.attr then
                local world=world_module.open()
                s.attr.victims[e.target]=world and weapon.last_hit(world,e.target)or nil
            end
            if s.lock_at then s.longest_lock=math.max(s.longest_lock or 0,clock-s.lock_at)end
            s.lock_at=nil
            local r=e.replacement
            say(s,('TARGET RELEASED (#%d): t=%s s: %s: %s; %s candidate(s); replacement: %s; %s; the AI\'s own exit from '
                ..'firing %s'):format(s.n,t(s),e.reason,tostring(e.text),tostring(e.candidates),r and(('entity %d, %s m '
                ..'from the old one (within %s m), a %s degree turn'):format(r.entity,n1(r.near),tostring(r.radius),
                n1(r.turn)))or'none',tostring(e.plan),e.exit and'queued'or'not queued'))
        elseif e.kind=='switched'then
            s.switches=s.switches+1
            say(s,('TARGET SWITCHED (#%d): t=%s s: %d -> %d by the AI\'s own re-pick (the lock %s)'):format(s.n,t(s),e.from,
                e.to,e.lock_valid and(e.perceived==false and'alive, out of its sight'or'still valid')or'no longer valid'))
        elseif e.kind=='exit_ran'then
            s.exits=s.exits+1
            say(s,('TARGET EXIT RAN (#%d): t=%s s: the AI left firing itself (stage %d now%s)'):format(s.n,t(s),e.stage,
                e.stage==12 and': back in firing already, within 3 degrees of a target'or''))
        elseif e.kind=='refused'then
            if e.code=='NOT_CONSUMED'then s.not_consumed=s.not_consumed+1 end
            say(s,('TARGET REFUSED (#%d): t=%s s: %s: %s'):format(s.n,t(s),tostring(e.code),tostring(e.reason)))
        end
    end
end

-- Kill attribution (docs section 24), read-only: the chin turret's shots in the projectile pool (source, owner,
-- creditor), and every death whose last hit came from a followed chin turret (the victim's health record: owner,
-- creditor) against what the Runtime's own entity_died reports as the killer.
local function peer_text(lo,hi,caller)
    if not lo or(lo==0 and hi==0)then return'none'end
    local hex=world_module.peer_hex(lo,hi)
    return hex..(caller and hex==caller and' (you)'or'')
end
local pool={}            -- {system, counter}: the pool position read last
local MAX_SHOT_READS=64  -- slots read per step at most (the newest are kept)
local function turret_of(entity)
    for _,s in pairs(tracked)do if s.turret==entity and not s.summarised then return s end end
end
local function scan_shots(world)
    local counter,system=world_module.projectile_counter(world)
    if not counter then pool={};return end
    if pool.system~=system or not pool.counter then pool.system,pool.counter=system,counter;return end
    local count=(counter-pool.counter)%4294967296
    if count==0 then return end
    local from=pool.counter
    pool.counter=counter
    if count>2048 then return end
    if count>MAX_SHOT_READS then from=(from+count-MAX_SHOT_READS)%4294967296;count=MAX_SHOT_READS end
    local slots=world_module.projectile_types(world,system,from,count)
    for _,item in ipairs(slots or{})do
        if item.type==weapon.AP4.projectile or item.type==weapon.AP4.standard.projectile then
            local rec=world_module.projectile_slot(world,system,item.slot)
            local s=rec and turret_of(rec.source)
            if s then
                local A=s.attr
                local peer=rec.creditor_lo~=0 or rec.creditor_hi~=0
                local mine=peer and world_module.peer_hex(rec.creditor_lo,rec.creditor_hi)==A.caller_peer
                A.shots=A.shots+1
                if mine then A.mine=A.mine+1 elseif peer then A.other=A.other+1 else A.none=A.none+1 end
                if not A.shot or(mine and not A.shot_mine)then
                    A.shot={slot=item.slot,type=item.type,source=rec.source,owner=rec.owner,
                        creditor=peer_text(rec.creditor_lo,rec.creditor_hi,A.caller_peer)}
                    A.shot_mine=mine
                    say(s,('GATLING ATTRIBUTION (#%d): t=%s s: SHOT: projectile %d in pool slot %d: source %d (the chin '
                        ..'turret), owner %d, creditor %s'):format(s.n,t(s),item.type,item.slot,rec.source,rec.owner,
                        A.shot.creditor))
                end
            end
        end
    end
end
-- A death: credited to the caller when its last hit came from a followed chin turret?
local function on_death(event)
    local world=world_module.open()
    if not world then return end
    local hit=weapon.last_hit(world,event.entity_id)
    for _,s in pairs(tracked)do
        local A=s.attr
        local h=hit or(A and A.victims[event.entity_id])
        if A and s.turret and h and h.owner==s.turret then
            A.victims[event.entity_id]=nil
            A.kills=A.kills+1
            local credited=event.killer_peer
            if event.local_killer then A.kills_mine=A.kills_mine+1 elseif credited then A.kills_other=A.kills_other+1
            else A.kills_none=A.kills_none+1 end
            local victim=('%d (%s)'):format(event.entity_id,tostring(event.semantic_id))
            local record=('owner %d, creditor %s'):format(h.owner,peer_text(h.creditor_lo,h.creditor_hi,A.caller_peer))
            local killer=credited and(credited..(event.local_killer and' (you, the local player)'or''))or'nobody'
            if A.kills<=5 then
                say(s,('KILL CREDIT (#%d): t=%s s: victim %s: its health record\'s last hit: %s; entity_died: killer %s'):format(
                    s.n,t(s),victim,record,killer))
            end
            if not A.chain and event.local_killer then
                A.chain=true
                local shot=A.shot
                say(s,('GATLING ATTRIBUTION (#%d): CHAIN: the call: Pelican CAS (asked for by %s) -> the player: peer %s, '
                    ..'avatar %s -> Pelican %d -> chin turret %d (%s) -> projectile %s (pool slot %s: source %s, owner %s, '
                    ..'creditor %s) -> victim %s (health record: %s) -> credited: entity_died killer %s'):format(s.n,
                    tostring(A.asked_by),tostring(A.caller_peer),tostring(A.caller_avatar),s.pelican,s.turret,
                    weapon.credit_text(A.after),tostring(shot and shot.type),tostring(shot and shot.slot),
                    tostring(shot and shot.source),tostring(shot and shot.owner),tostring(shot and shot.creditor),victim,record,
                    killer))
            end
        end
    end
end

local function step()
    clock=clock+STEP
    local world=world_module.open()
    local state=hd2.game_state()
    if not(world and state and state.mission)then
        if next(tracked)or assets.state then
            for _,s in pairs(tracked)do finish(s,nil)end
            tracked={};finished={};weapon.reset();heading.reset();assets={};ap_assets={}
        end
        return
    end
    -- The AP4 donor's package (the MG-206's), requested at once in a mission like the Gatling's.
    if ap_assets.state~='ready'and ap_assets.state~='failed'then
        local st,why=weapon.ap_assets(world,STEP)
        if st~=ap_assets.state then
            ap_assets.state,ap_assets.reason=st,why
            if st=='failed'then mod:log('GATLING AP: the AP4 donor\'s package did not load: '..tostring(why))end
        end
    end
    if assets.state~='ready'and assets.state~='failed'then
        local st,why=weapon.assets(world,STEP)
        if st~=assets.state then
            assets.state,assets.reason=st,why
            if st=='failed'then mod:log('GATLING CONFIG: the Gatling Sentry\'s package did not load: '..tostring(why))end
        end
    end
    if next(tracked)then scan_shots(world)end
    local live=pelicans.behaviours(world,{[667]=true})or{}
    for _,entity in ipairs(pelicans.active())do
        if not tracked[entity]and not finished[entity]and live[entity]then
            count=count+1
            tracked[entity]={n=count,pelican=entity,spec=spec_now(),rounds=0,
                fire_time=0,nil_fire=0,nil_fire_max=0,nil_run=0,locks=0,spatial=0,restores=0,switches=0,exits=0,
                not_consumed=0,released={},refills=0,turns=0,transitions={n=0,bn=0,between=0,maxb=0,tn=0,turn=0,maxt=0},
                aim={n=0,v=0,vd=0,h=0,lead=0,node=0,nodes=0},first=clock}
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
        -- 2. The configuration, once the package is resident (and the AP4 donor's, when AP4 is selected: loaded, or
        -- failed, which falls back to the standard round).
        local ap_settled=s.spec.ap~='ap4'or ap_assets.state=='ready'or ap_assets.state=='failed'
        if s.turret and not s.configured and assets.state=='ready'and ap_settled then
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
        -- 5. The turret: its stages, its target, its ammunition, its aim; the body's heading.
        if s.turret and not s.summarised then
            local a=weapon.ai_state(world,s.turret)
            if a then
                s.final_id=a.id
                local key=a.id..':'..a.stage
                if key~=s.last_key then
                    s.stage_changes=(s.stage_changes or 0)+1
                    if s.stage_changes<=30 then
                        say(s,('GATLING AI (#%d): STAGE t=%s s: chin turret %d: %s%s%s'):format(s.n,t(s),s.turret,
                            weapon.ai_text(a),firing(a)and' -- FIRING'or'',s.stage_changes==30
                            and' (later stage changes are counted, not logged)'or''))
                    end
                    s.last_key=key
                end
                if s.switched and a.id~=213 and not s.reverted then
                    s.reverted=true
                    say(s,('GATLING AI (#%d): CHECK t=%s s: the behaviour field reads %d after the change to 213'):format(s.n,
                        t(s),a.id))
                end
                if firing(a)then
                    s.fire_time=s.fire_time+STEP
                    if not a.target then
                        s.nil_fire=s.nil_fire+STEP;s.nil_run=s.nil_run+STEP
                        s.nil_fire_max=math.max(s.nil_fire_max,s.nil_run)
                    else s.nil_run=0 end
                else s.nil_run=0 end
                if s.switched and a.id==213 then
                    -- (The target controller itself runs every TARGET_STEP s: target_tick below.)
                    -- TARGET LOS: the lock in or out of the AI's sight.
                    local wt=weapon.watch_of(s.turret)
                    if wt and wt.lock and a.target==wt.lock then
                        if s.los==false then
                            say(s,('TARGET LOS (#%d): t=%s s: entity %d back in sight'):format(s.n,t(s),wt.lock))
                        end
                        s.los=true
                    elseif wt and wt.lock and s.los then
                        s.los=false
                        say(s,('TARGET LOS (#%d): t=%s s: entity %d out of the AI\'s sight (no longer its target; released '
                            ..'after %s s unless it comes back)'):format(s.n,t(s),wt.lock,n1(weapon.GRACE)))
                    end
                    -- TARGET AIM ERROR: read-only, sampled every second while firing at a target (for the summary),
                    -- logged every EVERY.aim s.
                    if firing(a)and a.target and clock>=(s.next_aim or 0)then
                        s.next_aim=clock+1
                        local am=weapon.aim_state(world,s.turret)
                        local root=am and am.target and position_of(world,am.target)
                        local e=weapon.aim_error(am,root)
                        if e then
                            local A=s.aim
                            A.n=A.n+1;A.v=A.v+e.vertical;A.vd=A.vd+e.vertical_deg;A.h=A.h+e.horizontal
                            A.lead=A.lead+e.lead_vertical
                            if e.node_height then A.node=A.node+e.node_height;A.nodes=A.nodes+1 end
                            local logged=clock>=(s.next_aim_log or 0)
                            if logged then s.next_aim_log=clock+EVERY.aim end
                            if logged then say(s,('TARGET AIM ERROR (#%d): t=%s s: entity %s at %s m: the shot crosses %s m %s it (%s deg) '
                                ..'and %s m to the side; the AI\'s lead for its own motion (muzzle %s m/s; the bullets do '
                                ..'not get it) explains %s m vertically; the aim point is %s m above its root; aim recoil '
                                ..'%s/%s deg; aim %s, muzzle %s'):format(s.n,t(s),tostring(am.target),n1(e.distance),
                                n2(math.abs(e.vertical)),e.vertical>=0 and'above'or'below',n2(e.vertical_deg),
                                n2(e.horizontal),n1(e.muzzle_speed),n2(e.lead_vertical),n2(e.node_height),
                                am.recoil and n2(am.recoil.x)or'?',am.recoil and n2(am.recoil.y)or'?',
                                pelicans.text(am.aim),pelicans.text(am.muzzle)))end
                        end
                    end
                end
            end
            -- GATLING SPREAD: its own spread read back while it flies (read-only); a change after it was applied is
            -- logged once.
            if s.result and clock>=(s.next_spread or 0)then
                s.next_spread=clock+EVERY.spread
                local sp=weapon.spread_state(world,s.turret)
                if sp then
                    local was=s.spread_last
                    s.spread_last=sp
                    if was and(was.x~=sp.x or was.y~=sp.y or was.word~=sp.word)and not s.spread_changed then
                        s.spread_changed=true
                        say(s,('GATLING SPREAD (#%d): t=%s s: CHANGED: %s, %s -> %s, %s mrad (word %d -> %d)'):format(s.n,
                            t(s),tostring(was.x),tostring(was.y),tostring(sp.x),tostring(sp.y),was.word,sp.word))
                    end
                end
            end
            -- GATLING AMMO REFILL.
            local rf=weapon.refill_step(world,s.turret,label)
            if rf and rf.kind=='refilled'then
                s.refills=s.refills+1
                say(s,('GATLING AMMO REFILL (#%d): t=%s s: %d -> %d'):format(s.n,t(s),rf.old,rf.new))
            elseif rf and rf.kind=='refused'then
                say(s,('GATLING AMMO REFILL (#%d): t=%s s: REFUSED: %s: %s'):format(s.n,t(s),tostring(rf.code),
                    tostring(rf.reason)))
            end
            -- BODY HEADING: toward the locked target, smoothly; with none, its heading is kept.
            if s.spec.facing and p then
                local wt=weapon.watch_of(s.turret)
                local point=wt and wt.lock and position_of(world,wt.lock)
                local ev=heading.face_step(world,entity,point,label)
                if ev and ev.kind=='turned'then
                    s.turns=s.turns+1
                    s.last_heading_error=ev.error
                elseif ev and ev.kind=='stopped'then
                    s.heading_stopped=ev.reason
                    say(s,('BODY HEADING (#%d): t=%s s: STOPPED: %s'):format(s.n,t(s),tostring(ev.reason)))
                elseif ev and ev.kind=='refused'and ev.code~=s.heading_refused then
                    s.heading_refused=ev.code
                    say(s,('BODY HEADING (#%d): t=%s s: REFUSED: %s: %s'):format(s.n,t(s),tostring(ev.code),
                        tostring(ev.reason)))
                end
                if clock>=(s.next_heading or 0)then
                    local hs=heading.state(world,entity)
                    if hs and hs.mode==1 then
                        s.next_heading=clock+EVERY.heading
                        local rel=point and wrap(math.deg(math.atan2(point.y-hs.position.y,point.x-hs.position.x))-hs.yaw)
                        say(s,('BODY HEADING (#%d): t=%s s: %s; toward %s%s'):format(s.n,t(s),heading.text(hs),
                            rel and('the locked target (%s deg from the nose)'):format(n1(rel))or'nothing (its heading kept)',
                            s.turns>0 and(' (%d turns written)'):format(s.turns)or''))
                    end
                end
            end
            -- GATLING FIRE.
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
                        local sentry=ref and ref.sentry and weapon.casing_state(world,ref.sentry.entity,GATLING)
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
                s.next_fire=clock+EVERY.fire
                local am=weapon.ammo_state(world,s.turret)
                local a2=weapon.ai_state(world,s.turret)
                say(s,('GATLING FIRE (#%d): t=%s s: %d rounds since the last line, %d in all; %s; chambered %s; rounds left '
                    ..'%s of %s; %s RPM'):format(s.n,t(s),s.window,s.rounds,a2 and(firing(a2)and'FIRING'or'not firing')
                    or'?',tostring(m and m.chambered),tostring(m and m.rounds),tostring(am and am.capacity),
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
-- The target controller, every TARGET_STEP s for each switched chin turret still followed (a stage entry's re-pick or a
-- target's death is answered within one tick).
local function target_tick()
    if not next(tracked)then return end
    local world=world_module.open()
    if not world then return end
    for _,s in pairs(tracked)do
        if s.switched and s.turret and not s.summarised then
            local a=weapon.ai_state(world,s.turret)
            if a and a.id==213 then
                target_events(s,weapon.target_step(world,s.turret,'PelicanGatlingProof '..BUILD..' #'..s.n))
            end
        end
    end
end
hd2.every(TARGET_STEP,target_tick)
hd2.events.on('entity_died',on_death)
hd2.input.bind('pelican_gatling_proof.ai',{key='Ctrl+F9',on_press=function()
    config.ai=not config.ai
    mod:log(('Ctrl+F9 [%s]: AI 213 %s for Pelicans seen from now on'):format(BUILD,config.ai and'ON'or'OFF (read-only)'))
end})
hd2.input.bind('pelican_gatling_proof.orbit',{key='Ctrl+F11',on_press=function()
    config.orbit=not config.orbit
    mod:log(('Ctrl+F11 [%s]: the orbit %s for Pelicans seen from now on'):format(BUILD,config.orbit and'ON'or'OFF'))
end})
hd2.input.bind('pelican_gatling_proof.facing',{key='Ctrl+Shift+F4',on_press=function()
    config.facing=not config.facing
    mod:log(('Ctrl+Shift+F4 [%s]: body facing %s for Pelicans seen from now on'):format(BUILD,config.facing and'ON'
        or'OFF'))
end})
hd2.input.bind('pelican_gatling_proof.status',{key='Ctrl+Shift+F1',on_press=function()
    local k=0;for _ in pairs(tracked)do k=k+1 end
    mod:log(('Ctrl+Shift+F1 [%s]: next Pelican: %s; packages %s / %s; %d Pelican(s) followed'):format(BUILD,
        spec_text(spec_now()),tostring(assets.state),tostring(ap_assets.state),k))
end})
mod:log('loaded ('..BUILD..'): '..spec_text(spec_now())..'; Ctrl+F9 AI, Ctrl+F11 orbit, Ctrl+Shift+F4 body facing, '
    ..'Ctrl+Shift+F1 status')
