local hd2=require('mods/skyeshade/hd2runtime')
-- PelicanGatlingAIProof 0.2.0: THE AI CHANGE THROUGH THE GAME'S OWN SetBehaviour, FROM STAGE 1 OR 4.
-- 0.1.0 live: the AI was never changed (summary: AI switched false). The freshly spawned chin turret sat in 645 stage 4
-- (its turret not active, during the approach) and the 0.1.0 guard allowed stage 1 only. Research since (pinned):
-- stage 4 = turret inactive (entering it parks the aim and clears the target; no timer; the trigger is pulled only on
-- entering stage 3), and the game changes behaviours itself with SetBehaviour (0x843EA0): it exits the old behaviour
-- through its own transition, writes and replicates the id, and starts the new one at its own stage 1. 0.2.0 calls that
-- routine (213 only) while the turret is quiet (645 stage 1 or 4, nothing pending), logs "behaviour BEFORE" and
-- "behaviour AFTER" read from the field, refuses unless AFTER is exactly 213, and every AI STAGE line prints the field.
-- PelicanGatlingAIProof 0.1.0: THE GATLING SENTRY'S AI ON THE PELICAN'S OWN CHIN TURRET (research/docs/pelican-cas-
-- F5FEE03DCFDB.md section 18). Development only; solo host only. Install with PelicanCasProof.
-- The chin turret keeps its entity, model, mount, node 41 and attachment. As soon as a Runtime Pelican's chin turret
-- exists and is uniquely identified (during its approach), through runtime/pelican_weapon.lua:
--   1. READ-ONLY first: "AI FIELD" shows the turret's Behavior record and its behaviour id field (645), and the same for
--      every Gatling Sentry seen (213);
--   2. its weapon: its own ProjectileWeapon record, projectile 148 at the configured RPM (default 600); the Gatling ammo
--      pattern optional (Ctrl+F10);
--   3. its AI (default on; Ctrl+F9 turns this off for a read-only run): one guarded write of its own behaviour id,
--      645 -> 213, only while it is idle (stage 1, nothing pending); the Gatling AI then runs its own stage machine.
-- No fire-window hold, no spin-up, nothing shared written. Every AI stage transition ("AI STAGE") and target change
-- ("AI TARGET": acquired, lost, switched) is logged, with rounds fired ("AI FIRE") and a summary.
-- Ctrl+Shift+F2: RPM 600 -> 1000 -> 1600 -> 300. Ctrl+F9: AI switch on/off. Ctrl+F10: pattern on/off.
-- Ctrl+Shift+F1: status. Settings apply to Pelicans seen from then on.
local mod=hd2.mod()
local BUILD='0.2.0 GATLING-AI SET-BEHAVIOUR BUILD'
mod:log('PelicanGatlingAIProof '..BUILD..' (solo host): call Pelican CAS (PelicanCasProof). As soon as its chin turret '
    ..'exists: "AI FIELD" (read-only), then its weapon (148, configured RPM), then the game\'s SetBehaviour with 213 while '
    ..'the turret is quiet (stage 1 or 4). Expect "PELICAN WEAPON AI BEFORE" (behaviour BEFORE = 645) and "AI SWITCHED" '
    ..'(behaviour AFTER = 213, read back), then "AI STAGE" lines printing the behaviour field, "AI TARGET", "AI FIRE", '
    ..'"AI SUMMARY". Ctrl+Shift+F2 RPM, Ctrl+F9 AI request on/off, Ctrl+F10 pattern, Ctrl+Shift+F1 status.')

-- INTERNAL modules (development only).
local pelicans=require('hd2runtime/runtime/pelicans')
local weapon=require('hd2runtime/runtime/pelican_weapon')
local gatling_turrets=require('hd2runtime/runtime/pelican_gatling')
local world_module=require('hd2runtime/runtime/event_world')
local RPMS={600,1000,1600,300}
local config={rpm=1,ai=true,pattern=false}
local MAX_LINES=150
local function n1(v)return v and('%.1f'):format(v)or'?'end
local function spec_text(s)return ('projectile %d, %d RPM, pattern %s, AI requested %s'):format(s.projectile,s.rpm,
    s.pattern and'on'or'off',s.ai and'213 (the Gatling Sentry\'s)'or'none (read-only)')end

local tracked={}
local count=0
local clock=0
local assets={}
local sentries={}   -- Gatling Sentries already shown
local function say(s,text)
    s.lines=(s.lines or 0)+1
    if s.lines<=MAX_LINES then mod:log(text)end
end
local function finish(s)
    if s.summarised then return end
    s.summarised=true
    if not s.turret then return end
    mod:log(('AI SUMMARY (#%d): chin turret %d (%s): behaviour field after the change %s; behaviour field at the end %s; '
        ..'%d AI STAGE lines read behaviour 213; %d rounds in %s s of firing (%s rounds/min while firing); %d firing-stage '
        ..'entries; %d targets acquired, %d lost; stages seen (behaviour/stage): %s'):format(s.n,s.turret,spec_text(s.spec),
        tostring(s.after),tostring(s.final_id),s.stage213,s.rounds,n1(s.fire_time),s.fire_time>0 and('%.0f'):format(
        s.rounds/s.fire_time*60)or'?',s.fire_entries,s.acquired,s.lost,table.concat(s.stages_seen,' ')))
end
local function firing(a)
    if not a then return false end
    return(a.id==213 and a.stage==12)or(a.id==645 and a.stage==3)
end
local function step()
    clock=clock+0.5
    local world=world_module.open()
    local state=hd2.game_state()
    if not(world and state and state.mission)then
        if next(tracked)or assets.state then tracked={};weapon.reset();assets={};sentries={}end
        return
    end
    if assets.state~='ready'and assets.state~='failed'then
        local st,why=weapon.assets(world,0.5)
        if st~=assets.state then
            assets.state,assets.reason=st,why
            if st=='failed'then mod:log('AI ASSETS: the projectile\'s package did not load: '..tostring(why))end
        end
    end
    -- Read-only: every Gatling Sentry's AI field, once.
    for entity in pairs(pelicans.behaviours(world,{[213]=true})or{})do
        if not sentries[entity]and not weapon.switched(entity)then
            sentries[entity]=true
            local a=weapon.ai_state(world,entity)
            if a then
                mod:log(('AI FIELD (Gatling Sentry %d): Behavior record 0x%X; behaviour id at +0x0 = %d; %s'):format(entity,
                    a.record,a.id,weapon.ai_text(a)))
            end
        end
    end
    for _,entity in ipairs(pelicans.active())do
        if not tracked[entity]then
            count=count+1
            tracked[entity]={n=count,pelican=entity,spec={projectile=148,rpm=RPMS[config.rpm],pattern=config.pattern,
                ai=config.ai},rounds=0,fire_time=0,fire_entries=0,acquired=0,lost=0,stages_seen={},first=clock,
                stage213=0}
            mod:log(('AI SEEN (#%d): Runtime Pelican %d; %s'):format(count,entity,spec_text(tracked[entity].spec)))
        end
    end
    for entity,s in pairs(tracked)do
        local p=(pelicans.behaviours(world,{[667]=true})or{})[entity]
        local label='PelicanGatlingAIProof '..BUILD..' #'..s.n
        -- 1. Identify the chin turret as soon as it exists; show its AI field (read-only).
        if p and not s.turret and p.stage>=1 and p.stage<=6 then
            local st=gatling_turrets.inspect(world,entity)
            if st and #st.attached==1 and st.turret and st.turret.behaviour==645 and st.mount and st.mount.slot then
                s.turret=st.turret.entity
                local a=weapon.ai_state(world,s.turret)
                mod:log(('AI FIELD (#%d): Pelican %d (stage %d), chin turret %d: Behavior record 0x%X; behaviour id at +0x0 '
                    ..'(address 0x%X) = %d; %s; %s s after the Pelican was seen'):format(s.n,entity,p.stage,s.turret,
                    a and a.record or 0,a and a.idAddress or 0,a and a.id or -1,weapon.ai_text(a),n1(clock-s.first)))
            elseif st and #st.attached>1 then
                s.attempted_weapon=true;s.ai_done=true
                mod:log(('AI RESULT (#%d): REFUSED: %d turrets name Pelican %d; the chin turret is not unique'):format(s.n,
                    #st.attached,entity))
            end
        end
        -- 2. Its weapon, once the package is resident.
        if s.turret and not s.attempted_weapon and assets.state=='ready'then
            s.attempted_weapon=true
            local r,code,reason=weapon.configure(world,entity,{projectile=s.spec.projectile,rpm=s.spec.rpm,
                pattern=s.spec.pattern},label)
            s.weapon=r
            mod:log(('AI WEAPON (#%d): %s'):format(s.n,r and(('applied: chin turret %d: %s'):format(r.turret,
                spec_text(s.spec)))or(('REFUSED: %s: %s'):format(tostring(code),tostring(reason)))))
        elseif s.turret and not s.attempted_weapon and assets.state=='failed'then
            s.attempted_weapon=true
            mod:log(('AI WEAPON (#%d): REFUSED: ASSET_UNAVAILABLE: %s'):format(s.n,tostring(assets.reason)))
        end
        -- 3. Its AI, while idle.
        if s.turret and s.spec.ai and not s.ai_done and s.attempted_weapon then
            local r,code,reason=weapon.switch_ai(world,entity,label)
            if r then
                s.ai_done=true;s.switched=true;s.switched_at=clock;s.after=r.after
                mod:log(('AI RESULT (#%d): chin turret %d: behaviour BEFORE = %d, behaviour AFTER = %d (read back), stage %d; '
                    ..'%s s after the Pelican was seen'):format(s.n,r.turret,r.before,r.after,r.stage_after,
                    n1(clock-s.first)))
            elseif code~='NOT_QUIET'then
                s.ai_done=true
                mod:log(('AI RESULT (#%d): REFUSED: %s: %s'):format(s.n,tostring(code),tostring(reason)))
            end
        end
        -- Every transition and target change, and the rounds.
        if s.turret and not s.summarised then
            local a=weapon.ai_state(world,s.turret)
            if a then
                s.final_id=a.id
                if s.switched and a.id==213 then s.stage213=s.stage213+(a.id..':'..a.stage~=s.last_key and 1 or 0)end
                if s.switched and a.id~=213 and not s.reverted then
                    s.reverted=true
                    say(s,('AI CHECK (#%d): t=%s s: the behaviour field reads %d after the change to 213'):format(s.n,
                        n1(clock-s.first),a.id))
                end
                local key=a.id..':'..a.stage
                if key~=s.last_key then
                    if not s.last_key or #s.stages_seen<40 then s.stages_seen[#s.stages_seen+1]=a.id..'/'..a.stage end
                    say(s,('AI STAGE (#%d): t=%s s: chin turret %d: %s%s'):format(s.n,n1(clock-s.first),s.turret,
                        weapon.ai_text(a),firing(a)and' -- FIRING'or''))
                    if firing(a)then s.fire_entries=s.fire_entries+1 end
                    s.last_key=key
                end
                if a.target~=s.last_target then
                    if a.target and not s.last_target then s.acquired=s.acquired+1
                        say(s,('AI TARGET (#%d): t=%s s: acquired entity %d (%s)'):format(s.n,n1(clock-s.first),a.target,
                            weapon.ai_text(a)))
                    elseif not a.target then s.lost=s.lost+1
                        say(s,('AI TARGET (#%d): t=%s s: LOST entity %d (%s)'):format(s.n,n1(clock-s.first),s.last_target,
                            weapon.ai_text(a)))
                    else s.acquired=s.acquired+1
                        say(s,('AI TARGET (#%d): t=%s s: switched %d -> %d (%s)'):format(s.n,n1(clock-s.first),
                            s.last_target,a.target,weapon.ai_text(a)))
                    end
                    s.last_target=a.target
                end
                if firing(a)then s.fire_time=s.fire_time+0.5 end
            end
            local w=pelicans.weapon_config(world,s.turret)
            local m=w and w.magazine
            if m and s.mag then
                local used=s.mag.rounds-m.rounds
                if used>0 then s.rounds=s.rounds+used;s.window=(s.window or 0)+used end
            end
            s.mag=m or s.mag
            if (s.window or 0)>0 and clock>=(s.next_fire or 0)then
                s.next_fire=clock+2
                say(s,('AI FIRE (#%d): t=%s s: %d rounds since the last line; %d in all; %s; chambered %s; rounds left %s; '
                    ..'%s RPM'):format(s.n,n1(clock-s.first),s.window,s.rounds,a and(firing(a)and'FIRING'or'not firing')
                    or'?',tostring(m and m.chambered),tostring(m and m.rounds),w and w.rpm and('%.0f'):format(w.rpm)or'?'))
                s.window=0
            end
        end
        if not p then
            finish(s)
            tracked[entity]=nil
        end
    end
end
hd2.every(0.5,step)
hd2.input.bind('pelican_gatling_ai_proof.rpm',{key='Ctrl+Shift+F2',on_press=function()
    config.rpm=config.rpm%#RPMS+1
    mod:log(('Ctrl+Shift+F2 [%s]: %d RPM for Pelicans seen from now on'):format(BUILD,RPMS[config.rpm]))
end})
hd2.input.bind('pelican_gatling_ai_proof.ai',{key='Ctrl+F9',on_press=function()
    config.ai=not config.ai
    mod:log(('Ctrl+F9 [%s]: AI request %s for Pelicans seen from now on'):format(BUILD,config.ai and'ON (SetBehaviour 213)'
        or'OFF (read-only: the AI field is shown, not changed)'))
end})
hd2.input.bind('pelican_gatling_ai_proof.pattern',{key='Ctrl+F10',on_press=function()
    config.pattern=not config.pattern
    mod:log(('Ctrl+F10 [%s]: the Gatling ammo pattern %s for Pelicans seen from now on'):format(BUILD,config.pattern
        and'ON'or'OFF'))
end})
hd2.input.bind('pelican_gatling_ai_proof.status',{key='Ctrl+Shift+F1',on_press=function()
    local k=0;for _ in pairs(tracked)do k=k+1 end
    mod:log(('Ctrl+Shift+F1 [%s]: next Pelican: projectile 148, %d RPM, pattern %s, AI request %s; package %s; %d '
        ..'Pelican(s) followed'):format(BUILD,RPMS[config.rpm],config.pattern and'on'or'off',config.ai and'on'or'off',
        tostring(assets.state),k))
end})
mod:log('loaded ('..BUILD..'): 600 RPM, pattern off, AI request 213 on; Ctrl+Shift+F2 RPM, Ctrl+F9 AI request, Ctrl+F10 '
    ..'pattern, Ctrl+Shift+F1 status')
