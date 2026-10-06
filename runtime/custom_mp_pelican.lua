-- A host-spawned Pelican CAS on every OTHER compatible machine (EXPERIMENTAL; docs/research/runtime-peer-messaging-
-- F5FEE03DCFDB.md section 15; research peer-messaging "pelicanMirror"; local_research/mp/pelican/pelican-mp-notes.md).
--
-- The session host spawns the Pelican and keeps everything that is simulation: its flight, hold and orbit, its chin
-- gun's AI (behaviour 213, its target lock, its continuous fire), its rounds and refill, its lifetime and the credit of
-- its rounds. That replicates, as the trigger. But every machine fires its OWN rounds of that turret from its OWN data
-- (live: the client saw the stock autocannon round), so the host's private configuration shows on the host only. Each
-- compatible Runtime that correlates the published Pelican and chin turret (runtime/custom_mp_items.lua, by network id)
-- gives ITS OWN copy of the turret the same private presentation, derived from its own registered definition (the
-- pelican family's gun data): runtime/pelican_weapon.lua mirror_configure (its own ProjectileWeapon copy: the round,
-- the rate slot and the casing before its first local shot; zero recoil; the spread), then mirror_interval every update
-- (its instance interval, the local shot cadence, at the Gatling rate while its replicated current RPM entry stands and
-- reads the host's seed or the Gatling rate; docs section 16). With gun.sound, the same firing sound on its own copy
-- (every machine posts its own local shots' sound from its own copy: docs/research/pelican-maelstrom-sound-
-- F5FEE03DCFDB.md), its bank's package requested here. With gun.impact_explosion (explosive rounds), every round its
-- copy fires HERE requests the donor's explosion on impact: runtime/projectile_impact.lua's continuous binding on this
-- machine's own pool (provenance: the exact turret decides, whoever its rounds credit), as the Gas EAT's launchers are
-- mirrored; a peer explodes its OWN copy of a round (research/projectile-pool), so every compatible machine converts its
-- own and the vanilla Pelican's stock round (120 -> 234 by its row) behaves the same way on every machine. Never
-- anything the network writes (the current RPM entry, the rounds, the trigger, the AI), never a shared definition,
-- never a game call after the configuration. Each update's branch is counted; REMOTE CUSTOM PELICAN CADENCE samples
-- this machine's own fire state (read-only).
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local PM=require('hd2runtime/domains/peer_messaging').pelicanMirror
local M={}
M.CONFIGURE_SECONDS=20   -- a mirror waits this long for its turret's weapon to be readable (replication)
M.SOUND_RETRY=0.25       -- a deferred firing sound is tried this often (seconds) once its bank is resident
M.DONOR_WAIT=10          -- explosive rounds wait this long (seconds) for their blast's package before binding
local function log(text)log_module.emit('[HD2Runtime] '..text)end

local pelican_of={}      -- [turret] = the published Pelican's entity here (index 1 of the same entry)
-- What a published network id must name here: index 1 the transport Pelican, index 2 its chin turret. Returns info, or
-- nil, why, wait.
function M.check(world,entity,index)
    local kind=world_module.entity_type(world,entity)
    if index==1 then
        if kind~=PM.pelicanResource then return nil,'not a transport Pelican'end
        return {pelican=entity}
    end
    if kind~=PM.chinResource then return nil,'not a Pelican chin turret'end
    return {turret=entity}
end
-- The cadence diagnostics (read-only; REMOTE CUSTOM PELICAN CADENCE): a sample every SAMPLE_FAST s during the first
-- SAMPLE_FAST_SECONDS of fire (its trigger or firing byte set), then every SAMPLE_SLOW s; at most SAMPLE_MAX a mirror.
M.SAMPLE_FAST,M.SAMPLE_FAST_SECONDS,M.SAMPLE_SLOW,M.SAMPLE_MAX=0.25,20,5,200
local KINDS={'held','steady','pending','unknown','refused'}
local function num(v,fmt)return v and(fmt or'%.2f'):format(v)or'?'end
-- The mirror of one published chin turret. spec = {turret, pelican (its Pelican here), network, gun (the definition's
-- gun data), label, client}. Returns the handle {status, cancel(), describe()}.
function M.mirror(spec)
    local gun=spec.gun or{}
    -- An untouched gun ({round = 'native'} alone; runtime/pelican_gunship.lua M.plain): the Pelican's own chin turret on
    -- this machine too, nothing copied or written.
    if require('hd2runtime/runtime/pelican_gunship').untouched(gun)then
        log(('REMOTE CUSTOM PELICAN: %s: chin gun UNTOUCHED: the Pelican\'s own autocannon on this machine, nothing '
            ..'mirrored'):format(tostring(spec.label)))
        return {status='complete',untouched=true,cancel=function()end,
            describe=function()return'its chin gun is the Pelican\'s own autocannon on this machine (nothing mirrored)'end}
    end
    local h={status='active',seconds=0,holds=0,label=spec.label,counts={},codes={},updates=0,fire=0,samples=0}
    for _,k in ipairs(KINDS)do h.counts[k]=0 end
    -- Why it never held, from the per-branch counts: the most frequent branch that did not hold, and the last values.
    local function diagnosis()
        local c=h.counts
        if c.held+c.steady>0 then
            return('held on %d of %d updates (written %d, already steady %d)'):format(c.held+c.steady,h.updates,c.held,
                c.steady)
        end
        if h.updates==0 then return'never evaluated (its gun was never configured here, or it is not a Gatling gun)'end
        local worst,n='pending',-1
        for _,k in ipairs({'pending','unknown','refused'})do if c[k]>n then worst,n=k,c[k]end end
        local why={pending='its current RPM entry always differed from its cached copy (the game rewrote the interval)',
            unknown='its current RPM entry was never the chin turret\'s seed nor the Gatling rate',
            refused='every attempt was refused'}
        local l=h.last or{}
        return('NEVER HELD: %s (%d of %d updates)%s; last: entry %s, cached %s, interval %s'):format(why[worst],n,
            h.updates,l.code and(' last code '..l.code..': '..tostring(l.reason))or'',num(l.entry),num(l.cached),
            num(l.interval,'%.4f'))
    end
    -- Explosive rounds on this machine's own copy (gun.impact_explosion): bound once its gun copy names its round.
    local function explosive(projectile)
        if gun.impact_explosion==nil or h.explosive then return end
        local impacts=require('hd2runtime/runtime/projectile_impact')
        -- A Mod Options choice is read now (every machine's value is in the registry hash, so they agree).
        local donor=require('hd2runtime/runtime/pelican_gunship').impact_now(gun.impact_explosion,gun.rpm)
        local S=require('hd2runtime/runtime/pelican_weapon').STRAFING
        local own=projectile==S.projectile and S.explosion or nil
        -- A round that natively explodes as an automatic donor's blast (the chin turret's own 120 as 234).
        for _,d in pairs(impacts.DONORS)do if d.automatic and d.round==projectile then own=d.explosion end end
        if donor~='none'and own and impacts.DONORS[donor].explosion==own then
            h.explosive={none=true}
            log(('REMOTE CUSTOM PELICAN: %s: explosive rounds: its round %d already explodes as %s\'s explosion %d'):format(
                spec.label,projectile,donor,own))
            return
        end
        if donor=='none'then
            h.explosive={none=true}
            log(('REMOTE CUSTOM PELICAN: %s: explosive rounds off (the Mod Options choice is none)'):format(spec.label))
            return
        end
        h.explosive={converted=0,impacts=0,refused=0}
        local binding,code,reason=impacts.bind({sources={spec.turret},projectiles={projectile},donor=donor,
            continuous=true,provenance=true,multiplayer=true,client=spec.client==true,
            label=spec.label..' explosive rounds'},function(e)
                local x=h.explosive
                if e.kind=='converted'then x.converted=x.converted+1
                elseif e.kind=='impact'then x.impacts=x.impacts+1
                elseif e.kind=='refused'then x.refused=x.refused+1 end
            end)
        h.impact_binding=binding
        if binding then
            log(('REMOTE CUSTOM PELICAN: %s: EXPLOSIVE ROUNDS on this machine\'s own copy: its projectile %d rounds request '
                ..'%s\'s explosion %d on impact'):format(spec.label,projectile,donor,impacts.DONORS[donor].explosion))
        else
            h.explosive.reason=tostring(code)..': '..tostring(reason)
            log(('REMOTE CUSTOM PELICAN: %s: EXPLOSIVE ROUNDS REFUSED (its rounds stay plain on this machine): %s'):format(
                spec.label,h.explosive.reason))
        end
    end
    local function finish(reason)
        if h.status~='active'then return end
        h.status='complete'
        if h.impact_binding and h.impact_binding.status=='active'then h.impact_binding.cancel()end
        local x=h.explosive
        if x and not x.none then
            log(('REMOTE CUSTOM PELICAN: %s: explosive rounds %s'):format(spec.label,x.reason and('REFUSED: '..x.reason)
                or(('%d converted, %d impacts seen, %d stayed plain'):format(x.converted,x.impacts,x.refused))))
        end
        local c,codes=h.counts,{}
        for code,k in pairs(h.codes)do codes[#codes+1]=('%s x%d'):format(code,k)end
        table.sort(codes)
        local held=c.held+c.steady
        log(('REMOTE CUSTOM PELICAN: %s: mirror ended (%s); interval held %d time%s (written %d, already steady %d; '
            ..'not held: pending %d, unknown rate %d, refused %d%s); %s; cadence samples %d'):format(spec.label,reason,
            held,held==1 and''or's',c.held,c.steady,c.pending,c.unknown,c.refused,
            #codes>0 and(': '..table.concat(codes,', '))or'',diagnosis(),h.samples))
    end
    -- One read-only sample of this machine's own copy (its own fire state) with the latest branch.
    local function sample(world,e,first)
        local weapon=require('hd2runtime/runtime/pelican_weapon')
        local s=weapon.mirror_cadence(world,spec.turret,true)
        h.samples=h.samples+1
        if not s then
            log(('REMOTE CUSTOM PELICAN CADENCE: %s: #%d: its fire state is unreadable'):format(spec.label,h.samples))
            return
        end
        local rate='n/a'
        local p=h.previous
        if p and s.shots>=p.shots and h.seconds>p.at then
            rate=('+%d in %.2f s = %.0f RPM here'):format(s.shots-p.shots,h.seconds-p.at,
                (s.shots-p.shots)*60/(h.seconds-p.at))
        elseif p then rate='a new trigger hold'end
        h.previous={shots=s.shots,at=h.seconds}
        local c=h.counts
        -- The FIRST sample always; the later ones only with the diagnostics switch (hd2.custom_stratagem.verbose).
        local emit=first and log or function(text)log_module.detail('[HD2Runtime] '..text)end
        emit(('REMOTE CUSTOM PELICAN CADENCE: %s: %s t %.2f s, fire %.2f s: current RPM entry %s (the host\'s), cached '
            ..'%s, interval %s s (expected %s), cooldown %s, trigger %d, firing %d, fire decision %d, shots %d (%s), '
            ..'rounds %s, AI record here behaviour %s stage %s; branch %s%s; counts held %d steady %d pending %d '
            ..'unknown %d refused %d'):format(spec.label,first and'FIRST'or('#'..h.samples),h.seconds,h.fire,
            num(s.entry),num(s.cached),num(s.interval,'%.4f'),e.want and('%.4f s = %.0f RPM, %s x%g'):format(e.want,e.rpm,e.basis,
            e.factor)or'none',num(s.cooldown,'%.4f'),s.trigger,s.firing,s.decision,s.shots,rate,tostring(s.rounds),
            tostring(s.behaviour),tostring(s.stage),e.kind,e.kind=='held'and(' (written over '..num(e.from,'%.4f')..' s)')
            or e.code and(' '..e.code..': '..tostring(e.reason))or'',c.held,
            c.steady,c.pending,c.unknown,c.refused))
    end
    function h.describe()
        return('its chin gun mirrored on this machine\'s own copy once its weapon is readable (round %s, %s, spread %s, '
            ..'recoil %s%s); the host keeps its flight, AI, target, rounds and lifetime'):format(tostring(
            require('hd2runtime/runtime/pelican_gunship').gun_now(gun).round or'standard'),
            gun.behave_as=='gatling_sentry'and(gun.rpm and(gun.rpm..' RPM')or('the Gatling rate x '
                ..tostring(gun.rate_multiplier or 1)))or'its own rate',
            tostring(require('hd2runtime/runtime/pelican_gunship').gun_now(gun).spread or'its own'),
            gun.recoil==false and'zero'or'its own',
            (gun.sound and(', sound '..tostring(gun.sound))or'')..(gun.impact_explosion~=nil and(', explosive rounds '
            ..require('hd2runtime/runtime/pelican_gunship').impact_now(gun.impact_explosion,gun.rpm))or''))
    end
    -- The firing sound (gun.sound): its bank's package requested here from the first update (never waited for: the
    -- copy is configured as soon as it is readable); applied in mirror_configure's own transaction when resident and
    -- quiet then, else once both hold (pelican_weapon.apply_sound on this machine's own copy, tried every
    -- SOUND_RETRY s once the package is resident). One line each way.
    local function sound_step(world,weapon,dt)
        -- Its catalogue name (an alias resolves; the chin turret's own is no sound to apply).
        if h.sound==nil then h.sound=weapon.sound_name(gun.sound)or false end
        if not h.sound or h.sound_done then return end
        if h.sound_gate~='ready'and h.sound_gate~='failed'then
            local why
            h.sound_gate,why=weapon.sound_assets(world,dt,h.sound)
            if h.sound_gate=='failed'then
                h.sound_done=true
                log(('REMOTE CUSTOM PELICAN: %s: firing sound %s not applied: its package did not load here (%s)'):format(
                    spec.label,h.sound,tostring(why)))
                return
            end
        end
        if not h.configured then return end
        local r=h.configured.sound
        if r and r.applied then h.sound_done=true;return end
        if h.sound_gate~='ready'or h.seconds<(h.sound_at or 0)then return end
        h.sound_at=h.seconds+M.SOUND_RETRY
        local s,code,reason=weapon.apply_sound(world,spec.turret,h.sound,spec.label,{mirror=true,quiet=true})
        if s then
            h.sound_done=true
            log(('REMOTE CUSTOM PELICAN: %s: firing sound %s on this machine\'s own copy (deferred until its bank was '
                ..'resident and the turret quiet); verified %s'):format(spec.label,h.sound,tostring(s.verified)))
        elseif code~='NOT_QUIET'and code~='ASSET_UNAVAILABLE'then
            h.sound_done=true
            if code~='ALREADY_APPLIED'then
                log(('REMOTE CUSTOM PELICAN: %s: firing sound %s not applied: %s: %s'):format(spec.label,h.sound,
                    tostring(code),tostring(reason)))
            end
        end
    end
    function h.cancel()if h.status=='active'then h.status='cancelled'end end
    function h.tick(dt)
        if h.status~='active'then return end
        h.seconds=h.seconds+(dt or 0)
        local world=world_module.open()
        if not world then return end
        local game=world_module.game_state(world)
        if not(game and game.mission)then return finish('the mission ended')end
        if world_module.entity_exists(world,spec.turret)==false then return finish('the chin turret is gone')end
        local weapon=require('hd2runtime/runtime/pelican_weapon')
        sound_step(world,weapon,dt)
        if not h.configured then
            local round=require('hd2runtime/runtime/pelican_gunship').gun_now(gun).round
            local r,code,reason=weapon.mirror_configure(world,spec.turret,{pelican=spec.pelican,round=round,
                gatling=gun.behave_as=='gatling_sentry',rate_factor=gun.rate_multiplier,rpm=gun.rpm,casing=gun.casing,
                spread=require('hd2runtime/runtime/pelican_gunship').gun_now(gun).spread,
                recoil=gun.recoil==false and'zero'or nil,sound=h.sound or nil,client=spec.client},spec.label)
            if r then
                h.configured=r
                log(('REMOTE CUSTOM PELICAN: %s: chin gun MIRRORED on this machine\'s own copy: projectile %d, verified %s'):format(
                    spec.label,r.projectile,tostring(r.verified)))
                -- Explosive rounds once the blast's package is resident here (explosion_donors.assets).
                if gun.impact_explosion~=nil then h.explosive_wait={projectile=r.projectile,since=h.seconds}end
            elseif code=='UNAVAILABLE'or code=='NOT_ATTACHED'then
                if h.seconds>M.CONFIGURE_SECONDS then return finish('never configurable: '..tostring(code)..': '..tostring(reason))end
            else
                return finish('refused: '..tostring(code)..': '..tostring(reason))
            end
            return
        end
        if h.explosive_wait then
            local w=h.explosive_wait
            local donor=require('hd2runtime/runtime/pelican_gunship').impact_now(gun.impact_explosion,gun.rpm)
            local state=donor=='none'and'ready'or require('hd2runtime/runtime/explosion_donors').assets(world,donor,dt)
            if state=='ready'or state=='failed'or h.seconds-w.since>=M.DONOR_WAIT then
                h.explosive_wait=nil
                explosive(w.projectile)
            end
        end
        if gun.behave_as=='gatling_sentry'then
            local e=weapon.mirror_interval(world,spec.turret,gun.rate_multiplier,gun.rpm)
            local s=e.state
            h.updates=h.updates+1
            h.counts[e.kind]=(h.counts[e.kind]or 0)+1
            h.last={code=e.code,reason=e.reason,entry=s and s.entry,cached=s and s.cached,interval=s and s.interval}
            if e.kind=='refused'then h.codes[e.code]=(h.codes[e.code]or 0)+1 end
            if e.kind=='held'then
                h.holds=h.holds+1
                if h.holds==1 then
                    log(('REMOTE CUSTOM PELICAN: %s: its own shot interval %.4f -> %.4f s (%.0f RPM, %s x%g) on this '
                        ..'machine; held while its current RPM entry stands'):format(spec.label,e.from or 0,e.to,e.rpm,
                        e.basis,e.factor))
                end
            elseif e.kind=='refused'and not h.said then
                h.said=true
                log(('REMOTE CUSTOM PELICAN: %s: interval not held: %s: %s'):format(spec.label,tostring(e.code),
                    tostring(e.reason)))
            end
            if e.kind=='refused'and e.code=='CREATED_HERE'then
                return finish('refused: CREATED_HERE: '..tostring(e.reason))
            end
            local firing=s~=nil and(s.trigger~=0 or s.firing~=0)
            if firing then h.fire=h.fire+(dt or 0)end
            local every=(firing and h.fire<=M.SAMPLE_FAST_SECONDS)and M.SAMPLE_FAST or M.SAMPLE_SLOW
            if h.samples<M.SAMPLE_MAX and(not h.sampled or h.seconds-h.sampled>=every-1e-6)then
                local first=h.sampled==nil
                h.sampled=h.seconds
                sample(world,e,first)
            end
        end
    end
    scheduler.attach(h)
    return h
end
return M
