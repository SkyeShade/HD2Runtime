local hd2=require('mods/skyeshade/hd2runtime')
-- PelicanGatlingProof 0.2.0: THE GATLING'S PACKAGE THROUGH THE RUNTIME'S ASSET LOADER; WHY THE CHIN TURRET STAYS.
-- 0.1.0 live: REPLACE spawned and attached a Gatling that followed the Pelican, ran its AI and fired 148 at 1600 RPM with
-- its pattern and spin-up, and the game's teardown removed it with the Pelican; but the chin turret stayed (two turrets)
-- and the Gatling showed its whole sentry, ground base included; it spawned only with the Gatling Sentry in the loadout.
-- WEAPON live: the chin turret fired the Gatling projectile at 1600 RPM continuously (no pattern, no spin-up).
-- 0.2.0:
--   * the Gatling Sentry's package is requested through the Runtime's own asset loader as soon as you are in a mission
--     (mode REPLACE): "assets for pelican-gatling requested", then "... resident"; REPLACE waits for it and is refused
--     if it does not load. No Gatling Sentry is needed in the loadout;
--   * REMOVAL lines before and after the game's removal call: the chin turret's network id, its network object's flag
--     (set: the game only sends a removal request) and the pending removals. 2 s later, if it is still alive, a second
--     attempt with the game's own destroy routine (not forced: the game's own ownership check stays): DESTROY lines;
--   * GATLING UNIT: which engine unit functions exist and the Gatling's unit (mesh count); Ctrl+Shift+F3 hides the next
--     mesh of the newest Gatling (its own render state) so the ground base's meshes can be identified.
-- PelicanGatlingProof 0.1.0: ONE RUNTIME PELICAN'S CHIN TURRET AS A GATLING TURRET (research/docs/pelican-cas-
-- F5FEE03DCFDB.md section 16). Development only; solo host only. Install with PelicanCasProof: each Pelican CAS
-- Pelican (a Runtime-spawned, empty Pelican) is changed 3 s after it starts hovering, ONCE, in the current mode:
--   * REPLACE (the default): the game's own spawn request creates a gatling_turret; the game's own attach routine attaches
--     it to the Pelican at the chin turret's node; the Pelican's own mount record names it in the chin turret's slot
--     (one guarded write), so the game's own teardown removes it with the Pelican; the chin turret is unlinked and
--     removed by the game's own routines. The Gatling keeps its own AI, weapon, ammo pattern and spin-up.
--   * WEAPON (the fallback): the chin turret stays; the game's own copy routine gives it its own ProjectileWeapon
--     record; one guarded transaction sets its projectile to the Gatling's (148) and its rate to 1600 RPM.
-- Nothing shared is written: no Pelican, Gatling, weapon, projectile or mount definition (the type records are read
-- before and after to show it). Every native call is runtime/pelican_gatling.lua's, behind its pins and guards.
-- Ctrl+Shift+F6: next mode (REPLACE -> WEAPON -> OFF). Ctrl+Shift+F4: status.
local mod=hd2.mod()
local BUILD='0.2.0 GATLING PACKAGE-LOADER BUILD'
mod:log('PelicanGatlingProof '..BUILD..' (solo host; no Gatling Sentry needed in the loadout): in a mission the Gatling\'s '
    ..'package is requested ("assets for pelican-gatling requested", then "resident"). Call Pelican CAS (PelicanCasProof): '
    ..'3 s into the hover its chin turret is changed once, in the current mode. Expect "PELICAN GATLING" lines (BEFORE, '
    ..'ATTEMPT, REMOVAL, APPLIED or REFUSED, DESTROY), "GATLING VERIFY", "GATLING UNIT", "GATLING SAMPLE", "GATLING FIRE", '
    ..'"GATLING TEARDOWN". Ctrl+Shift+F6: mode; Ctrl+Shift+F4: status; Ctrl+Shift+F3: hide the next Gatling mesh.')

-- INTERNAL modules (development only).
local pelicans=require('hd2runtime/runtime/pelicans')
local gatling=require('hd2runtime/runtime/pelican_gatling')
local world_module=require('hd2runtime/runtime/event_world')
local MODES={'replace','weapon','off'}
local mode=1
local DELAY=3
local function n1(v)return v and('%.1f'):format(v)or'?'end
local function at(v)return v and('(%.1f, %.1f, %.1f)'):format(v.x,v.y,v.z)or'(?)'end
local function dist(a,c)
    if not(a and c)then return nil end
    return math.sqrt((a.x-c.x)^2+(a.y-c.y)^2+(a.z-c.z)^2)
end
local function changed(a,c)
    if not(a and c)then return 0 end
    local n=0
    for o=0,#a-4,4 do if a:sub(o+1,o+4)~=c:sub(o+1,o+4)then n=n+1 end end
    return n
end

local tracked={}   -- Pelican entity -> its experiment
local count=0
local clock=0
local assets={state=nil,reason=nil}   -- the Gatling package gate (REPLACE)
local newest            -- the newest Gatling, for Ctrl+Shift+F3
local mesh_index=0
local function sample(world,s)
    local p=pelicans.behaviours(world,{[667]=true})
    p=p and p[s.pelican]
    local pose=pelicans.pose(world,s.pelican)
    local target=s.mode=='replace'and s.result and s.result.gatling or s.turret
    local beh=target and(pelicans.behaviours(world,{[213]=true,[645]=true})or{})[target]
    local att=target and pelicans.attachable(world,target)
    local w=target and pelicans.weapon_config(world,target)
    local state=p and gatling.inspect(world,s.pelican)
    local out={alive=p~=nil,stage=p and p.stage,pose=pose,beh=beh,att=att,w=w,
        attached=state and #state.attached,original=s.original and(pelicans.behaviours(world,{[645]=true})or{})[s.original]
            ~=nil}
    out.distance=att and pose and dist(att.position,pose.position)
    return out
end
local function weapon_line(w)return gatling.weapon_text(w)end

local function attempt(world,s)
    if s.mode=='replace'and assets.state~='ready'then
        if assets.state=='failed'then
            s.attempted=true
            mod:log(('GATLING RESULT (#%d): REPLACE REFUSED on Pelican %d: ASSET_UNAVAILABLE: %s'):format(s.n,s.pelican,
                tostring(assets.reason)))
        end
        return
    end
    s.attempted=true
    local before=gatling.inspect(world,s.pelican)
    s.turret=before and before.turret and before.turret.entity
    s.original=s.turret
    s.shared_before=gatling.shared(world)
    local label='PelicanGatlingProof '..BUILD..' #'..s.n
    local result,code,reason
    if s.mode=='replace'then result,code,reason=gatling.replace(world,s.pelican,label)
    else result,code,reason=gatling.weapon(world,s.pelican,label)end
    s.result=result
    if not result then
        mod:log(('GATLING RESULT (#%d): %s REFUSED on Pelican %d: %s: %s'):format(s.n,s.mode:upper(),s.pelican,
            tostring(code),tostring(reason)))
        return
    end
    s.applied_at=clock
    if s.mode=='replace'then newest=result.gatling;mesh_index=0 end
    mod:log(('GATLING RESULT (#%d): %s applied on Pelican %d: %s'):format(s.n,s.mode:upper(),s.pelican,
        s.mode=='replace'and(('chin turret %d -> Gatling %d at node %d (mount slot %d)'):format(result.original,
            result.gatling,result.node,result.slot))or(('chin turret %d: own record #%d, projectile %d, %d RPM'):format(
            result.turret,result.copy,gatling.GATLING_PROJECTILE,gatling.GATLING_RPM))))
end

local function verify(world,s)
    s.verified_once=true
    local v=sample(world,s)
    local shared_after=gatling.shared(world)
    local w=v.w
    local projectile=w and(s.mode=='replace'and w.magazine and w.magazine.pattern and'pattern'
        or(w.copy and w.copy.projectileType))
    local ok={pelican=v.alive,oneTurret=v.attached==1,
        follows=v.distance~=nil and s.first_distance~=nil and math.abs(v.distance-s.first_distance)<2,
        ai=s.ai_changes>0,
        projectile=s.mode=='replace'and(w~=nil and w.magazine~=nil and w.magazine.pattern)or(w~=nil and w.copy~=nil
            and w.copy.projectileType==gatling.GATLING_PROJECTILE),
        rpm=w~=nil and w.rpm~=nil and math.abs(w.rpm-gatling.GATLING_RPM)<50,
        sharedUnchanged=gatling.shared_same(s.shared_before,shared_after)}
    if s.mode=='replace'then ok.originalGone=not v.original end
    local pattern=s.mode=='replace'and w and w.magazine and w.magazine.pattern
    local spin=w and w.windUp
    local parts={}
    for _,k in ipairs({'pelican','oneTurret','follows','ai','projectile','rpm','sharedUnchanged','originalGone'})do
        if ok[k]~=nil then parts[#parts+1]=k..' '..tostring(ok[k])end
    end
    mod:log(('GATLING VERIFY (#%d, %s, t=%s s after): %s; ammo pattern %s; spin-up %s; turret %s: %s; attachable link '
        ..'0x%X node %s, %s m from the Pelican (first %s m); shared types: %s'):format(s.n,s.mode:upper(),
        n1(clock-s.applied_at),table.concat(parts,', '),pattern and'ACTIVE (148,148,148,242,148)'or'not active',
        spin and'present (the Gatling\'s wind-up component)'or'absent',tostring(s.mode=='replace'and s.result.gatling
            or s.turret),weapon_line(w),v.att and v.att.link or 0,tostring(v.att and v.att.node),n1(v.distance),
        n1(s.first_distance),gatling.shared_text(shared_after)))
end

local function step()
    clock=clock+0.5
    local world=world_module.open()
    local state=hd2.game_state()
    if not(world and state and state.mission)then
        if next(tracked)or assets.state then tracked={};gatling.reset();assets={};newest=nil end
        return
    end
    if MODES[mode]=='replace'and assets.state~='ready'and assets.state~='failed'then
        local st,why=gatling.assets(world,0.5)
        if st~=assets.state then
            assets.state,assets.reason=st,why
            if st=='failed'then mod:log('GATLING ASSETS: the Gatling Sentry\'s package did not load: '..tostring(why))end
        end
    end
    for _,entity in ipairs(pelicans.active())do
        local s=tracked[entity]
        if not s then
            count=count+1
            s={n=count,pelican=entity,first=clock,mode=MODES[mode],ai_changes=0,fires=0,samples=0}
            tracked[entity]=s
            mod:log(('GATLING SEEN (#%d): Runtime Pelican %d; mode %s'):format(s.n,entity,s.mode:upper()))
        end
    end
    for entity,s in pairs(tracked)do
        local p=(pelicans.behaviours(world,{[667]=true})or{})[entity]
        if p and p.stage==6 and not s.hover_at then s.hover_at=clock end
        if p and not s.attempted and s.mode~='off'and s.hover_at and clock-s.hover_at>=DELAY then attempt(world,s)end
        if s.result and not s.gone then
            local v=sample(world,s)
            if not s.first_distance and v.distance then s.first_distance=v.distance end
            local raw=v.beh and v.beh.raw
            if raw and s.raw and changed(s.raw,raw)>0 then s.ai_changes=s.ai_changes+1 end
            s.raw=raw or s.raw
            local m=v.w and v.w.magazine
            if m and s.mag and(m.rounds~=s.mag.rounds or m.chambered~=s.mag.chambered)then
                s.fires=s.fires+1
                if s.fires<=40 then
                    mod:log(('GATLING FIRE (#%d): t=%s s: rounds %d -> %d, chambered %d -> %d; %s RPM (interval %s s)')
                        :format(s.n,n1(clock-s.applied_at),s.mag.rounds,m.rounds,s.mag.chambered,m.chambered,
                        v.w.rpm and('%.0f'):format(v.w.rpm)or'?',v.w.interval and('%.4f'):format(v.w.interval)or'?'))
                end
            end
            s.mag=m or s.mag
            if clock>=(s.next_sample or 0)then
                s.next_sample=clock+2
                s.samples=s.samples+1
                if s.samples<=40 then
                    mod:log(('GATLING SAMPLE (#%d): t=%s s: Pelican %s stage %s at %s; turret %s: %s, behaviour stage %s, '
                        ..'%d AI record changes so far; attachable link 0x%X node %s, %s m from the Pelican; %d turret(s) '
                        ..'attached; chin turret %s'):format(s.n,n1(clock-s.applied_at),p and'alive'or'GONE',
                        tostring(v.stage),at(v.pose and v.pose.position),v.beh and'alive'or'GONE',weapon_line(v.w),
                        tostring(v.beh and v.beh.stage),s.ai_changes,v.att and v.att.link or 0,tostring(v.att and v.att.node),
                        n1(v.distance),v.attached or 0,s.mode=='replace'and(v.original and'STILL PRESENT'or'gone')
                        or'kept'))
                end
            end
            if s.mode=='replace'and not s.removal_checked and clock-s.applied_at>=2 then
                s.removal_checked=true
                local r=gatling.removal_state(world,s.original)
                if r.alive then
                    mod:log(('GATLING REMOVAL (#%d): the original chin turret is still alive 2 s after the game\'s removal '
                        ..'call: %s; second attempt: the game\'s destroy routine'):format(s.n,gatling.removal_text(r)))
                    gatling.destroy_original(world,s.pelican,'PelicanGatlingProof '..BUILD..' #'..s.n)
                    s.destroy_at=clock
                else
                    mod:log(('GATLING REMOVAL (#%d): the original chin turret is gone (the game\'s removal took it)')
                        :format(s.n))
                end
            end
            if s.destroy_at and not s.destroy_checked and clock-s.destroy_at>=2 then
                s.destroy_checked=true
                local r=gatling.removal_state(world,s.original)
                mod:log(('GATLING REMOVAL (#%d): 2 s after the destroy routine: the original chin turret %s'):format(s.n,
                    r.alive and('is STILL ALIVE: '..gatling.removal_text(r))or'is gone'))
            end
            if not s.verified_once and clock-s.applied_at>=5 then verify(world,s)end
            if s.mode=='replace'and not s.unit_logged and clock-s.applied_at>=5 then
                s.unit_logged=true
                local api,awhy=gatling.unit_api()
                local names={}
                for k,v in pairs(api or{})do names[#names+1]=k..' '..tostring(v)end
                table.sort(names)
                mod:log(('GATLING UNIT API (#%d): %s'):format(s.n,api and table.concat(names,', ')or tostring(awhy)))
                local u,uwhy=gatling.gatling_unit(world,s.result.gatling)
                mod:log(('GATLING UNIT (#%d): %s'):format(s.n,u and(('the Gatling\'s unit found (%d gatling_turret '
                    ..'unit(s), %.1f m from its attachable position); meshes %s'):format(u.candidates,u.distance,
                    tostring(u.meshes)))or('not found: '..tostring(uwhy))))
            end
            if s.verified_once and not s.verified_late and clock-s.applied_at>=30 then
                s.verified_late=true;verify(world,s)
            end
        end
        if not p and not s.gone then
            s.gone=clock
            mod:log(('GATLING TEARDOWN (#%d): Pelican %d gone after %s s'):format(s.n,entity,n1(clock-s.first)))
        end
        if s.gone and s.result and s.mode=='replace'and not s.teardown_done and clock-s.gone>=5 then
            s.teardown_done=true
            local g=s.result.gatling
            local alive=(pelicans.behaviours(world,{[213]=true})or{})[g]~=nil
            if alive then
                local ok,code,reason=gatling.remove_gatling(world,g,'PelicanGatlingProof '..BUILD)
                mod:log(('GATLING TEARDOWN (#%d): Gatling %d still alive 5 s after its Pelican: the game\'s teardown did '
                    ..'NOT remove it; Runtime cleanup %s%s'):format(s.n,g,ok and'requested'or'REFUSED',ok and''
                    or(': '..tostring(code)..': '..tostring(reason))))
            else
                mod:log(('GATLING TEARDOWN (#%d): Gatling %d removed with its Pelican by the game\'s own teardown')
                    :format(s.n,g))
            end
        end
    end
end
hd2.every(0.5,step)
hd2.input.bind('pelican_gatling_proof.mode',{key='Ctrl+Shift+F6',on_press=function()
    mode=mode%#MODES+1
    mod:log(('Ctrl+Shift+F6 [%s]: mode %s (for Pelicans seen from now on)'):format(BUILD,MODES[mode]:upper()))
end})
hd2.input.bind('pelican_gatling_proof.status',{key='Ctrl+Shift+F4',on_press=function()
    local k,applied=0,0
    for _,s in pairs(tracked)do k=k+1;if s.result then applied=applied+1 end end
    mod:log(('Ctrl+Shift+F4 [%s]: mode %s; %d Pelican(s) followed, %d changed'):format(BUILD,MODES[mode]:upper(),k,
        applied))
end})
hd2.input.bind('pelican_gatling_proof.mesh',{key='Ctrl+Shift+F3',on_press=function()
    local world=world_module.open()
    if not(world and newest)then mod:log('Ctrl+Shift+F3 ['..BUILD..']: no Gatling yet');return end
    mesh_index=mesh_index+1
    local u,why=gatling.hide_mesh(world,newest,mesh_index)
    mod:log(('Ctrl+Shift+F3 [%s]: Gatling %d: mesh %d hidden: %s'):format(BUILD,newest,mesh_index,u and(('yes (%s '
        ..'meshes)'):format(tostring(u.meshes)))or('NO: '..tostring(why))))
end})
mod:log('loaded ('..BUILD..'): mode '..MODES[mode]:upper()..'; Ctrl+Shift+F6 mode, Ctrl+Shift+F4 status, Ctrl+Shift+F3 '
    ..'hide the next Gatling mesh')
