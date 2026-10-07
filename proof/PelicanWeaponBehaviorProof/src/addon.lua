local hd2=require('mods/skyeshade/hd2runtime')
-- PelicanWeaponBehaviorProof 0.1.0: THE PELICAN'S OWN CHIN TURRET WITH A CONFIGURABLE WEAPON BEHAVIOUR (research/docs/
-- pelican-cas-F5FEE03DCFDB.md section 17). Development only; solo host only. Install with PelicanCasProof.
-- The chin turret keeps its entity, model, node 41 and targeting AI. 3 s into each Pelican CAS hover, once, through
-- runtime/pelican_weapon.lua (every write per instance and guarded; nothing shared):
--   * its own ProjectileWeapon record (the game's copy routine): projectile 148 at the configured RPM (default 600);
--   * continuous fire (default on): its AI fires in fixed 0.5 s windows (stage 3) with at least 1.5 s of re-aiming
--     between them; each time it starts firing, its own fire-window start is moved 1 h ahead, so it keeps firing until
--     its AI itself stops (no target, no line of fire);
--   * the Gatling ammo pattern 148,148,148,242,148 (default off; Ctrl+F10): its own magazine record (the game's
--     magazine copy routine);
--   * spin-up: not available (a component its type does not have).
-- The projectile's package goes through the Runtime's asset loader first ("assets for pelican-weapon ...").
-- Measured and logged every 2 s while it acts: rounds fired, the measured rate, the time in its firing stage, bursts.
-- Ctrl+Shift+F2: RPM 600 -> 1000 -> 1600 -> 300. Ctrl+F9: continuous on/off. Ctrl+F10: pattern on/off.
-- Ctrl+Shift+F1: status. Settings apply to Pelicans seen from then on.
local mod=hd2.mod()
local BUILD='0.1.0 CHIN TURRET CONTINUOUS-FIRE BUILD'
mod:log('PelicanWeaponBehaviorProof '..BUILD..' (solo host): call Pelican CAS (PelicanCasProof). 3 s into the hover its '
    ..'own chin turret gets projectile 148 at the configured RPM, continuous fire and optionally the Gatling pattern. '
    ..'Expect "assets for pelican-weapon" lines, "PELICAN WEAPON" lines (BEFORE, ATTEMPT, APPLIED or REFUSED, HOLD), '
    ..'"WEAPON FIRE" every 2 s while it acts and "WEAPON SUMMARY". Ctrl+Shift+F2 RPM, Ctrl+F9 continuous, Ctrl+F10 '
    ..'pattern, Ctrl+Shift+F1 status.')

-- INTERNAL modules (development only).
local pelicans=require('hd2runtime/runtime/pelicans')
local weapon=require('hd2runtime/runtime/pelican_weapon')
local world_module=require('hd2runtime/runtime/event_world')
local RPMS={600,1000,1600,300}
local config={rpm=1,continuous=true,pattern=false}
local DELAY=3
local function n1(v)return v and('%.1f'):format(v)or'?'end
local function spec_text(s)return ('projectile %d, %d RPM, continuous %s, pattern %s'):format(s.projectile,s.rpm,
    s.continuous and'on'or'off',s.pattern and'on'or'off')end

local tracked={}
local count=0
local clock=0
local assets={}
local function finish(s)
    if s.summarised then return end
    s.summarised=true
    if not s.result then return end
    local fire=s.fire_time>0 and(s.rounds/s.fire_time*60)or nil
    mod:log(('WEAPON SUMMARY (#%d): chin turret %d (%s): %d rounds in %s s of firing (%s rounds/min while firing); '
        ..'%d firing-stage entries (bursts), %d holds; %s s observed'):format(s.n,s.result.turret,spec_text(s.spec),s.rounds,
        n1(s.fire_time),fire and('%.0f'):format(fire)or'?',s.entries,s.holds,n1(clock-s.applied_at)))
end
local function step()
    clock=clock+0.5
    local world=world_module.open()
    local state=hd2.game_state()
    if not(world and state and state.mission)then
        if next(tracked)or assets.state then tracked={};weapon.reset();assets={}end
        return
    end
    if assets.state~='ready'and assets.state~='failed'then
        local st,why=weapon.assets(world,0.5)
        if st~=assets.state then
            assets.state,assets.reason=st,why
            if st=='failed'then mod:log('WEAPON ASSETS: the projectile\'s package did not load: '..tostring(why))end
        end
    end
    for _,entity in ipairs(pelicans.active())do
        if not tracked[entity]then
            count=count+1
            tracked[entity]={n=count,pelican=entity,spec={projectile=148,rpm=RPMS[config.rpm],
                continuous=config.continuous,pattern=config.pattern},rounds=0,fire_time=0,entries=0,holds=0,samples=0}
            mod:log(('WEAPON SEEN (#%d): Runtime Pelican %d; %s'):format(count,entity,spec_text(tracked[entity].spec)))
        end
    end
    for entity,s in pairs(tracked)do
        local p=(pelicans.behaviours(world,{[667]=true})or{})[entity]
        if p and p.stage==6 and not s.hover_at then s.hover_at=clock end
        if p and not s.attempted and s.hover_at and clock-s.hover_at>=DELAY then
            if assets.state=='failed'then
                s.attempted=true
                mod:log(('WEAPON RESULT (#%d): REFUSED on Pelican %d: ASSET_UNAVAILABLE: %s'):format(s.n,entity,
                    tostring(assets.reason)))
            elseif assets.state=='ready'then
                s.attempted=true
                local r,code,reason=weapon.configure(world,entity,s.spec,'PelicanWeaponBehaviorProof '..BUILD..' #'..s.n)
                s.result=r
                if r then
                    s.applied_at=clock
                    mod:log(('WEAPON RESULT (#%d): applied on Pelican %d: chin turret %d: %s'):format(s.n,entity,r.turret,
                        spec_text(s.spec)))
                else
                    mod:log(('WEAPON RESULT (#%d): REFUSED on Pelican %d: %s: %s'):format(s.n,entity,tostring(code),
                        tostring(reason)))
                end
            end
        end
        if s.result and not s.summarised then
            local t=s.result.turret
            local f=weapon.fire_state(world,t)
            local w=pelicans.weapon_config(world,t)
            if f then
                if f.stage==3 then
                    s.fire_time=s.fire_time+0.5
                    if s.last_stage~=3 then s.entries=s.entries+1 end
                end
                s.last_stage=f.stage
                if s.spec.continuous then
                    local held,code,reason=weapon.hold_fire(world,t,'PelicanWeaponBehaviorProof '..BUILD..' #'..s.n)
                    if held=='held'then s.holds=s.holds+1
                    elseif not held and not s.hold_refused then
                        s.hold_refused=true
                        mod:log(('WEAPON HOLD REFUSED (#%d): %s: %s'):format(s.n,tostring(code),tostring(reason)))
                    end
                end
            end
            local m=w and w.magazine
            if m and s.mag then
                local used=s.mag.rounds-m.rounds
                if used>0 then s.rounds=s.rounds+used;s.window=(s.window or 0)+used end
            end
            s.mag=m or s.mag
            if clock>=(s.next_sample or s.applied_at+2)then
                s.next_sample=clock+2
                s.samples=s.samples+1
                if s.samples<=40 then
                    mod:log(('WEAPON FIRE (#%d): t=%s s: %d rounds in the last 2 s (%s rounds/min); %d in all; firing stage '
                        ..'%s (%d entries, %d holds); interval %s s (%s RPM); chambered %s; rounds left %s'):format(s.n,
                        n1(clock-s.applied_at),s.window or 0,('%.0f'):format((s.window or 0)*30),s.rounds,
                        f and(f.stage==3 and'YES'or('no (stage '..f.stage..')'))or'?',s.entries,s.holds,
                        w and w.interval and('%.4f'):format(w.interval)or'?',w and w.rpm and('%.0f'):format(w.rpm)or'?',
                        tostring(m and m.chambered),tostring(m and m.rounds)))
                end
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
hd2.input.bind('pelican_weapon_proof.rpm',{key='Ctrl+Shift+F2',on_press=function()
    config.rpm=config.rpm%#RPMS+1
    mod:log(('Ctrl+Shift+F2 [%s]: %d RPM for Pelicans seen from now on'):format(BUILD,RPMS[config.rpm]))
end})
hd2.input.bind('pelican_weapon_proof.continuous',{key='Ctrl+F9',on_press=function()
    config.continuous=not config.continuous
    mod:log(('Ctrl+F9 [%s]: continuous fire %s for Pelicans seen from now on'):format(BUILD,config.continuous and'ON'
        or'OFF (the native bursts)'))
end})
hd2.input.bind('pelican_weapon_proof.pattern',{key='Ctrl+F10',on_press=function()
    config.pattern=not config.pattern
    mod:log(('Ctrl+F10 [%s]: the Gatling ammo pattern %s for Pelicans seen from now on'):format(BUILD,config.pattern
        and'ON'or'OFF'))
end})
hd2.input.bind('pelican_weapon_proof.status',{key='Ctrl+Shift+F1',on_press=function()
    local k=0;for _ in pairs(tracked)do k=k+1 end
    mod:log(('Ctrl+Shift+F1 [%s]: next Pelican: projectile 148, %d RPM, continuous %s, pattern %s; package %s; %d Pelican(s) '
        ..'followed'):format(BUILD,RPMS[config.rpm],config.continuous and'on'or'off',config.pattern and'on'or'off',
        tostring(assets.state),k))
end})
mod:log('loaded ('..BUILD..'): 600 RPM, continuous on, pattern off; Ctrl+Shift+F2 RPM, Ctrl+F9 continuous, Ctrl+F10 '
    ..'pattern, Ctrl+Shift+F1 status')
