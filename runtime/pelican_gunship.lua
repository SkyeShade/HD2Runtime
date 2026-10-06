-- A Runtime Pelican's chin gun as a gunship (development; docs/custom-stratagem-api.md, "Pelican gunship"). Not
-- exported by api/hd2.lua: hd2.pelican.spawn{gun = ..., orbit = ..., credit_to = ...} arms it.
--
-- The live-proven PelicanGatlingProof 0.5.0 lifecycle, without its diagnostics, for ONE Runtime-spawned Pelican:
--   1. its chin turret, once it exists and is the only turret naming that Pelican (runtime/pelican_gatling.lua);
--   2. once the Gatling Sentry's package (and, for the AP4 round, the MG-206's; for a firing sound, the package of its
--      bank) has settled: its OWN weapon configuration (runtime/pelican_weapon.lua configure: the projectile on its own
--      ProjectileWeapon copy, the rate, the Gatling casing, the firing sound, the 2047-round safe magazine, zero aim
--      recoil, the spread on its own WeaponData record and, with credit_to, its own no-credit tag cleared so its kills
--      credit the host who called it); a sound whose package failed is left the turret's own, one skipped while the
--      turret fired is applied once it is quiet;
--   3. the Gatling Sentry's AI (behaviour 213) while its own AI is quiet, then the Runtime's target lock every 0.05 s;
--   4. the orbit around its anchor once it holds there (runtime/pelicans.lua orbit);
--   5. every 0.25 s: the magazine refill below 1500 and the body turned toward the locked target.
-- With gun.impact_explosion (explosive rounds), from the configuration on: every round of its chin turret requests a
-- donor explosion reviewed for its rate on impact (an automatic donor's blast at any rate; a slow donor's volume, an EMS
-- field or a gas cloud, only with gun.rpm at most its max_rpm) (runtime/projectile_impact.lua, a continuous binding: one
-- guarded write of each round's OWN impact explosion copy, +0x7C, before its first step; its round's row, the MG-206 /
-- MG-43 rows and every other projectile stay as they are). Other compatible machines do the same on their own copies
-- (runtime/custom_mp_pelican.lua).
-- Every per-instance operation keeps its own guards (pins, the game thread, the solo host, this Pelican's own records);
-- nothing shared is written. Logging: one line per state transition and a summary; refusals always.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local pelicans=require('hd2runtime/runtime/pelicans')
local weapon=require('hd2runtime/runtime/pelican_weapon')
local heading=require('hd2runtime/runtime/pelican_heading')
local turrets=require('hd2runtime/runtime/pelican_gatling')
local instances=require('hd2runtime/runtime/spawned_instances')
local M={}
M.STEP=0.25
M.TARGET_STEP=0.05
-- How long the configuration waits for a firing sound's package once the chin turret exists; after that it is configured
-- without it and the sound follows once its bank is resident (never delaying the rest of the configuration more).
M.SOUND_WAIT=10
-- The rounds: its own (the MG-43's 148), the MG-206's AP4 275, the Eagle Strafing Run's 23mm HE round 16 (every round,
-- or the Eagle's own pattern: HE then three plain, on its own magazine copy; runtime/pelican_weapon.lua M.STRAFING).
M.ROUNDS={standard=true,native=true,ap4=true,strafing_run=true,strafing_run_pattern=true}
local ROUND_TEXT="'standard', 'native', 'ap4', 'strafing_run' or 'strafing_run_pattern'"
-- The gun options a Mod Options choice may give (read when the gun is armed): the round, the explosive rounds and the
-- spread.
M.CHOICES={round=true,impact_explosion=true,spread=true,aim_height=true}
-- The aim point, lowered (gun.aim_height; runtime/pelican_weapon.lua aim_lower): every update while the AI aims or fires
-- at a target, the turret's own targeting override is set to the target's root plus aim_height metres, except for these
-- targets, whose own aim node the game's aim keeps (the Bile Titans: big enough that it hits them).
M.AIM_HEIGHT_MAX=3
M.OWN_AIM={['enemy/v1/terminids/strider']=true,['enemy/v1/terminids/strider_gloom']=true}
M.AIM_MOVE=0.05           -- metres the point must move before it is written again
-- The aim diagnostic (read-only; runtime/pelican_weapon.lua aim_state / aim_error, research section 20b): sampled every
-- AIM_EVERY s while the gun fires at a target; the first AIM_LOG samples logged, the rest with the diagnostics switch;
-- the means in the summary.
M.AIM_EVERY,M.AIM_LOG=1,3
-- The activity diagnostic (read-only): the time its AI spends in each stage, every spell of at least IDLE_SECONDS without
-- firing (the first IDLE_LOG logged, the rest with the diagnostics switch) with the enemies it could attack meanwhile
-- (pelican_weapon.candidates, sampled every IDLE_SAMPLE s), and why each lock was released; all of it in the summary.
M.IDLE_SECONDS,M.IDLE_LOG,M.IDLE_SAMPLE=2,3,0.5
M.STAGE_NAMES={[1]='spawned',[2]='search',[3]='alert',[4]='leaving fire',[5]='aiming',[10]='weapon unusable',[11]='dead',
    [12]='firing',[-1]='other AI'}
M.ORBIT_DEFAULTS={radius=40,altitude=60,duration=55,interval=0.25,period=30,entry=15,mode='sweep'}

local function log(text)log_module.emit('[HD2Runtime] pelican gunship '..text)end

-- Validates a gun spec: {round = 'standard' | 'native' (the chin turret's own round, 120: the Pelican autocannon's) |
-- 'ap4', behave_as = 'gatling_sentry', rate_multiplier = 1 | 1.5 | 2, rpm = an explicit rate in rounds a minute (30 to
-- 3000; with behave_as, in place of the Gatling rate; held on its own copy's rate slot), casing = 'gatling' (with
-- behave_as, the default: the Gatling Sentry's) | 'own' (the chin turret's own),
-- spread = mrad (0, 100], recoil = false (zero aim recoil) | nil (its own), unlimited_ammo = true | nil, face_target =
-- true | nil, sound = a firing sound of the catalogue (hd2.sounds; runtime/weapon_sounds.lua: a shot or a loop, on its
-- own copy; docs/weapon-sounds.md) | 'pelican/chin_autocannon' or nil (its own), impact_explosion = a donor reviewed
-- for this gun's rate (runtime/explosion_donors.lua, by name or key: an automatic donor, 'Pelican chin autocannon',
-- '66mm Missile Mk2', 'Automaton explosion 27', ...; with gun.rpm at most its max_rpm, a slow donor: 'EMS mortar field',
-- 'Gas grenade cloud', 'Gas mortar cloud') | a Mod Options choice of their keys and 'none' (its value when the gun is
-- armed) | nil (its rounds' own: none)}.
-- Returns the normalized spec (sound: the canonical name, or nil for its own; impact: the donor's name or nil) or nil
-- and why.
function M.check_gun(gun)
    if type(gun)~='table'then return nil,'gun must be a table'end
    for key in pairs(gun)do
        if key~='round'and key~='behave_as'and key~='rate_multiplier'and key~='spread'and key~='recoil'
                and key~='unlimited_ammo'and key~='face_target'and key~='sound'and key~='impact_explosion'
                and key~='aim_height'and key~='rpm'and key~='casing'then
            return nil,'unsupported gun option: '..tostring(key)
        end
    end
    -- The explicit rate (the Gatling AI's, in place of the Gatling rate): what a slow donor is checked against.
    local rpm=gun.rpm
    if rpm~=nil then
        if not(type(rpm)=='number'and rpm==rpm and rpm>=30 and rpm<=3000)then
            return nil,'gun.rpm is rounds a minute, 30 to 3000'
        end
        if gun.behave_as~='gatling_sentry'then
            return nil,'gun.rpm is the Gatling AI\'s rate: it needs behave_as = \'gatling_sentry\''
        end
        if(gun.rate_multiplier or 1)~=1 then return nil,'gun.rpm replaces the Gatling rate: no rate_multiplier'end
    end
    local fit={gun=true,rpm=rpm or math.huge}
    -- Explosive rounds: only a donor reviewed for this gun (an automatic one: one plain blast a round; a slow one: a
    -- volume, with gun.rpm at most its max_rpm), by name or key, or a Mod Options choice whose values are such keys or
    -- 'none' (read here: an arm reads it at each call).
    local impact
    if gun.impact_explosion~=nil then
        local donors=require('hd2runtime/runtime/explosion_donors')
        local ref=gun.impact_explosion
        local reviewed='an explosion donor reviewed for '..(rpm and(rpm..' RPM')or'its rate (a slow donor needs gun.rpm)')
            ..': '..table.concat(donors.names(fit),', ')
        if require('hd2runtime/api/options').is_handle(ref)then
            if ref.kind~='choice'then return nil,'gun.impact_explosion must be a donor or a Mod Options choice'end
            for _,v in ipairs(ref.values)do
                if v~='none'and not donors.resolve(v,fit)then
                    return nil,'gun.impact_explosion: choice value '..tostring(v)..' is neither \'none\' nor '..reviewed
                end
            end
            local ok,value=pcall(function()return ref:get()end)
            impact=ok and value~='none'and donors.resolve(value,fit)or nil
        else
            impact=donors.resolve(ref,fit)
            if not impact then return nil,'gun.impact_explosion must be '..reviewed end
        end
    end
    -- The sound: a catalogue name (or alias), canonical from here; the chin turret's own leaves it (nil).
    local sound,swhy=weapon.sound_name(gun.sound)
    if sound==false then return nil,'gun.'..swhy end
    -- The round: a name, or a Mod Options choice of names (its value now).
    local round=gun.round
    if require('hd2runtime/api/options').is_handle(round)then
        if round.kind~='choice'then return nil,'gun.round must be '..ROUND_TEXT..' or a Mod Options choice'end
        for _,v in ipairs(round.values)do
            if not M.ROUNDS[v]then return nil,'gun.round: choice value '..tostring(v)..' is not '..ROUND_TEXT end
        end
        local ok,value=pcall(function()return round:get()end)
        round=ok and M.ROUNDS[value]and value or'standard'
    end
    -- The spread: a width in mrad, or a Mod Options choice of widths (its value now).
    local spread=gun.spread
    if require('hd2runtime/api/options').is_handle(spread)then
        if spread.kind~='choice'then return nil,'gun.spread must be a width in mrad or a Mod Options choice'end
        for _,v in ipairs(spread.values)do
            if not(type(v)=='number'and v>0 and v<=weapon.SPREAD_MAX)then
                return nil,'gun.spread: choice value '..tostring(v)..' is not a width in mrad above 0 and at most '
                    ..weapon.SPREAD_MAX
            end
        end
        local ok,value=pcall(function()return spread:get()end)
        spread=ok and value or nil
    end
    -- The aim height: metres above the target's root (0: the game's own aim node), or a Mod Options choice of heights.
    local aim=gun.aim_height
    local function aim_ok(v)return type(v)=='number'and v>=0 and v<=M.AIM_HEIGHT_MAX end
    if require('hd2runtime/api/options').is_handle(aim)then
        if aim.kind~='choice'then return nil,'gun.aim_height must be metres or a Mod Options choice'end
        for _,v in ipairs(aim.values)do
            if not aim_ok(v)then
                return nil,'gun.aim_height: choice value '..tostring(v)..' is not metres from 0 to '..M.AIM_HEIGHT_MAX
            end
        end
        local ok,value=pcall(function()return aim:get()end)
        aim=ok and value or 0
    elseif aim~=nil and not aim_ok(aim)then
        return nil,'gun.aim_height is metres above the target\'s feet, 0 (the game\'s own) to '..M.AIM_HEIGHT_MAX
    end
    -- The casing: the Gatling Sentry's (with behave_as, the default) or the chin turret's own.
    if gun.casing~=nil and gun.casing~='gatling'and gun.casing~='own'then
        return nil,'gun.casing must be \'gatling\' or \'own\''
    end
    if gun.casing=='gatling'and gun.behave_as~='gatling_sentry'then
        return nil,'gun.casing = \'gatling\' goes with behave_as = \'gatling_sentry\''
    end
    if aim~=nil and aim>0 and gun.behave_as~='gatling_sentry'then
        return nil,'gun.aim_height follows the Gatling AI\'s target: it needs behave_as = \'gatling_sentry\''
    end
    local out={round=round or'standard',behave_as=gun.behave_as,rate=gun.rate_multiplier or 1,spread=spread,
        aim_height=aim and aim>0 and aim or nil,
        recoil=gun.recoil,ammo=gun.unlimited_ammo,face=gun.face_target,sound=sound,impact=impact,
        impact_set=gun.impact_explosion~=nil,rpm=rpm,
        casing=gun.casing or(gun.behave_as=='gatling_sentry'and'gatling'or nil)}
    if not M.ROUNDS[out.round]then return nil,'gun.round must be '..ROUND_TEXT end
    if out.behave_as~=nil and out.behave_as~='gatling_sentry'then return nil,"gun.behave_as must be 'gatling_sentry'"end
    if not weapon.RATE_FACTORS[out.rate]then return nil,'gun.rate_multiplier must be 1, 1.5 or 2'end
    if out.rate~=1 and out.behave_as~='gatling_sentry'then
        return nil,'gun.rate_multiplier multiplies the Gatling Sentry\'s rate: it needs behave_as = \'gatling_sentry\''
    end
    if out.spread~=nil and not(type(out.spread)=='number'and out.spread>0 and out.spread<=weapon.SPREAD_MAX)then
        return nil,'gun.spread is a width in mrad, above 0 and at most '..weapon.SPREAD_MAX
    end
    if out.recoil~=nil and out.recoil~=false then return nil,'gun.recoil can only be false (no aim recoil)'end
    if out.ammo~=nil and out.ammo~=true then return nil,'gun.unlimited_ammo can only be true'end
    if out.face~=nil and out.face~=true then return nil,'gun.face_target can only be true'end
    if out.face and out.behave_as~='gatling_sentry'then
        return nil,'gun.face_target follows the Runtime target lock: it needs behave_as = \'gatling_sentry\''
    end
    return out
end
-- gun.impact_explosion as it stands now (rpm: the gun's explicit rate, gun.rpm): the donor's name, 'none' (a Mod
-- Options choice on none, or unusable), or nil when unset. What the registry hash and the logs compare (a choice is
-- read now).
function M.impact_now(ref,rpm)
    if ref==nil then return nil end
    local donors=require('hd2runtime/runtime/explosion_donors')
    if require('hd2runtime/api/options').is_handle(ref)then
        local ok,value=pcall(function()return ref:get()end)
        ref=ok and value or'none'
    end
    return donors.resolve(ref,{gun=true,rpm=rpm or math.huge})or'none'
end
-- The assets gun.impact_explosion needs on every machine: the `asset` (a stratagem whose call-in package ships the
-- blast's effect) of every donor it can name (each value of a choice), in order, once each.
function M.impact_assets(ref,rpm)
    local donors=require('hd2runtime/runtime/explosion_donors')
    local list=require('hd2runtime/api/options').is_handle(ref)and ref.values or{ref}
    local out,seen={},{}
    for _,v in ipairs(list)do
        local _,donor=donors.resolve(v,{gun=true,rpm=rpm or math.huge})
        if donor and donor.asset and not seen[donor.asset]then seen[donor.asset]=true;out[#out+1]=donor.asset end
    end
    return out
end
-- The gun data as it stands now: a copy whose Mod Options choices (M.CHOICES) are their values (the round's name; the
-- explosive rounds' donor name or 'none'). What the registry hash, the logs and every other machine compare.
function M.gun_now(gun)
    if type(gun)~='table'then return gun end
    local options=require('hd2runtime/api/options')
    local out={}
    for k,v in pairs(gun)do out[k]=v end
    if options.is_handle(out.impact_explosion)then out.impact_explosion=M.impact_now(out.impact_explosion,out.rpm)end
    if options.is_handle(out.round)then
        local handle=out.round
        local ok,value=pcall(function()return handle:get()end)
        out.round=ok and M.ROUNDS[value]and value or'standard'
    end
    if options.is_handle(out.spread)then
        local handle=out.spread
        local ok,value=pcall(function()return handle:get()end)
        out.spread=ok and value or nil
    end
    if options.is_handle(out.aim_height)then
        local handle=out.aim_height
        local ok,value=pcall(function()return handle:get()end)
        out.aim_height=ok and value or 0
    end
    return out
end
-- Whether any gun option is a Mod Options choice (its registry hash then follows the values now).
function M.has_choice(gun)
    local options=require('hd2runtime/api/options')
    if type(gun)~='table'then return false end
    for key in pairs(M.CHOICES)do if options.is_handle(gun[key])then return true end end
    return false
end
-- The assets the gun's round needs on every machine (each value of a choice), once each: the MG-206's for the AP4
-- round, the Eagle Strafing Run's for its rounds.
function M.round_assets(round)
    local list=require('hd2runtime/api/options').is_handle(round)and round.values or{round}
    local out,seen={},{}
    for _,r in ipairs(list)do
        local name=r=='ap4'and'MG-206 Heavy Machine Gun'
            or(r=='strafing_run'or r=='strafing_run_pattern')and weapon.STRAFING.asset or nil
        if name and not seen[name]then seen[name]=true;out[#out+1]=name end
    end
    return out
end
-- Validates an orbit spec ({radius, altitude, duration, period, entry}; defaults M.ORBIT_DEFAULTS). Returns it or nil, why.
function M.check_orbit(orbit)
    if type(orbit)~='table'then return nil,'orbit must be a table'end
    local out={}
    for key,value in pairs(M.ORBIT_DEFAULTS)do out[key]=value end
    for key,value in pairs(orbit)do
        if M.ORBIT_DEFAULTS[key]==nil or key=='mode'or key=='interval'then return nil,'unsupported orbit option: '..key end
        out[key]=value
    end
    for key,range in pairs(pelicans.ORBIT)do
        local v=out[key]
        if v~=nil and not(type(v)=='number'and v>=range[1]and v<=range[2])then
            return nil,('orbit.%s must be %s to %s'):format(key,tostring(range[1]),tostring(range[2]))
        end
    end
    if out.entry>=out.duration then return nil,'orbit.entry must be shorter than orbit.duration'end
    return out
end

local active={}           -- by Pelican entity
local ap_state,gatling_state,strafing_state={},{},{}
local function strafing(round)return round=='strafing_run'or round=='strafing_run_pattern'end
local sound_state={}      -- by sound name: {state, reason} of its package's asset gate
local donor_state={}      -- by blast (explosion donor) name: {state, reason} of its package's asset gate

local function emit(g,event)
    event.pelican=g.pelican
    if g.callback then
        local ok,why=pcall(g.callback,event)
        if not ok then log('callback failed: '..tostring(why))end
    end
end

local function configure(world,g)
    local round=g.gun.round
    if round=='ap4'and ap_state.state~='ready'then
        log(('%s: the AP4 round\'s package did not load (%s): the standard round instead'):format(g.label,
            tostring(ap_state.reason or ap_state.state)))
        round='standard'
    end
    if strafing(round)and strafing_state.state~='ready'then
        log(('%s: the Eagle Strafing Run\'s package did not load (%s): the standard round instead'):format(g.label,
            tostring(strafing_state.reason or strafing_state.state)))
        round='standard'
    end
    local projectile=round=='ap4'and weapon.AP4.projectile or strafing(round)and weapon.STRAFING.projectile
        or round=='native'and weapon.FROZEN.chin.projectile or weapon.AP4.standard.projectile
    local gatling=g.gun.behave_as=='gatling_sentry'
    -- The firing sound: in this transaction only with its bank resident (its package's gate ready). A package that
    -- failed leaves the turret its own sound; one still loading (M.SOUND_WAIT passed) follows once resident (step).
    local sound=g.gun.sound
    local ss=sound and sound_state[sound]or{}
    if sound and ss.state~='ready'then
        if ss.state=='failed'then
            log(('%s: the firing sound\'s package did not load (%s): its own sound instead'):format(g.label,
                tostring(ss.reason)))
            g.sound_reason='ASSET_UNAVAILABLE: '..tostring(ss.reason)
        else
            log(('%s: the firing sound\'s package is still loading: the sound follows once it is resident'):format(
                g.label))
            g.sound_retry,g.sound_waiting=sound,true
        end
        sound=nil
    end
    local r,code,reason=weapon.configure(world,g.pelican,{projectile=projectile,rpm=gatling and(g.gun.rpm or'gatling')
        or nil,hold_rate=gatling and g.gun.rpm and true or nil,rate_factor=gatling and not g.gun.rpm and g.gun.rate or nil,
        casing=gatling and g.gun.casing~='own'or nil,ammo=g.gun.ammo,
        recoil=g.gun.recoil==false and'zero'or nil,spread=g.gun.spread,credit=g.credit and true or nil,sound=sound,
        pattern=round=='strafing_run_pattern'and'strafing_run'or nil},g.label)
    if not r then
        emit(g,{kind='refused',stage='configure',code=code,reason=reason})
        return
    end
    g.config=r
    g.round=round
    local id=weapon.projectile_identity(world,projectile)
    g.speed=id and id.velocity or nil
    -- A sound skipped only because the turret was firing is applied once it is quiet (step).
    if r.sound and not r.sound.applied and r.sound.retry then g.sound_retry=sound end
    local sound_part=''
    if g.gun.sound then
        sound_part=r.sound and r.sound.applied and(', sound '..g.gun.sound)or(', sound '..g.gun.sound..(g.sound_retry
            and(g.sound_waiting and' once its bank is resident'or' once it stops firing')
            or(' NOT APPLIED: '..tostring(r.sound and r.sound.reason or g.sound_reason))))
    end
    local w=pelicans.weapon_config(world,g.turret)
    local cr=r.credit
    log(('%s: ARMED: chin turret %d: projectile %d (%s), %s RPM, spread %s, aim recoil %s, magazine %s, credit %s%s; %d '
        ..'writes; shared definitions unchanged %s; verified %s'):format(g.label,g.turret,projectile,round,
        w and w.currentRpm and('%.0f'):format(w.currentRpm)or'?',r.spread and r.spread.applied and('%g mrad'):format(
        r.spread.after.x)or'its own',r.recoil and r.recoil.applied and'zero'or'its own',r.ammo and r.ammo.applied
        and tostring(r.ammo.capacity)or'its own',cr and(cr.applied and'to the caller (the host)'or('NOT APPLIED: '
        ..tostring(cr.reason)))or'native',sound_part,r.writes,tostring(r.verify.shared),tostring(r.verified)))
    -- A call the host runs for ANOTHER player (custom multiplayer: credit_peer): every round of its chin turret credits
    -- that player (runtime/projectile_impact.lua bind_credit: each round's own pool creditor, before its first step).
    if g.credit_peer then
        local impacts=require('hd2runtime/runtime/projectile_impact')
        local binding,ccode,creason=impacts.bind_credit({sources={g.turret},projectiles={projectile},
            credit_to=g.credit_peer,label=g.label..' credit',multiplayer=true})
        g.credit_binding=binding
        log(binding and(('%s: CREDIT: chin turret %d\'s rounds credited to the requesting player %s (each round\'s own pool '
            ..'creditor, written before its first step; a round missed keeps the host)'):format(g.label,g.turret,
            g.credit_peer))or(('%s: CREDIT REFUSED (the rounds credit the host): %s: %s'):format(g.label,tostring(ccode),
            tostring(creason))))
    end
    -- Explosive rounds: every round of its chin turret, this machine's own copy (after the credit binding, so a round's
    -- creditor is written first; provenance: the exact turret decides, whoever it credits).
    local own=projectile==weapon.STRAFING.projectile and weapon.STRAFING.explosion or nil
    -- A round that natively explodes as an automatic donor's blast (the chin turret's own 120 as 234).
    for _,d in pairs(require('hd2runtime/runtime/explosion_donors').DONORS)do
        if d.automatic and d.round==projectile then own=d.explosion end
    end
    if g.gun.impact and own==require('hd2runtime/runtime/explosion_donors').DONORS[g.gun.impact].explosion then
        log(('%s: EXPLOSIVE ROUNDS: its round %d already explodes as %s\'s explosion %d (its own row): nothing to '
            ..'write'):format(g.label,projectile,g.gun.impact,own))
    elseif g.gun.impact then
        local impacts=require('hd2runtime/runtime/projectile_impact')
        local mp=require('hd2runtime/runtime/multiplayer')
        g.explosive={converted=0,impacts=0,refused=0}
        local binding,icode,ireason=impacts.bind({sources={g.turret},projectiles={projectile},donor=g.gun.impact,
            continuous=true,provenance=true,multiplayer=mp.entity_allowed(g.pelican),
            label=g.label..' explosive rounds'},function(e)
            local x=g.explosive
            if e.kind=='converted'then x.converted=x.converted+1
            elseif e.kind=='impact'then x.impacts=x.impacts+1
            elseif e.kind=='refused'then x.refused=x.refused+1
            elseif e.kind=='ended'then x.ended=tostring(e.reason)end
        end)
        g.impact_binding=binding
        if binding then
            local via=require('hd2runtime/runtime/explosion_donors').resident_package(g.gun.impact)
            log(('%s: EXPLOSIVE ROUNDS: chin turret %d\'s projectile %d rounds request %s\'s explosion %d on impact (each '
                ..'round\'s own copy, written before its first step; the projectile row and every other projectile '
                ..'unchanged; its effect resident in %s)'):format(g.label,g.turret,projectile,g.gun.impact,
                impacts.DONORS[g.gun.impact].explosion,via and(via.name or via.id)or'?'))
        else
            g.explosive.reason=tostring(icode)..': '..tostring(ireason)
            log(('%s: EXPLOSIVE ROUNDS REFUSED (its rounds stay plain): %s'):format(g.label,g.explosive.reason))
            emit(g,{kind='refused',stage='impact',code=icode,reason=ireason})
        end
    elseif g.gun.impact_set then
        log(('%s: EXPLOSIVE ROUNDS off: the Mod Options choice is none'):format(g.label))
    end
    emit(g,{kind='armed',turret=g.turret,round=round,projectile=projectile,rpm=w and w.currentRpm,verified=r.verified,
        credit=cr and cr.applied,credit_peer=g.credit_peer,credit_written=g.credit_binding~=nil,
        sound=r.sound and r.sound.applied and g.gun.sound or nil,
        impact_explosion=g.impact_binding and g.gun.impact or nil})
end

local clock,next_step=0,0
local function stage_text(times)
    local keys={}
    for k in pairs(times)do keys[#keys+1]=k end
    table.sort(keys,function(x,y)return times[x]>times[y]end)
    local parts={}
    for _,k in ipairs(keys)do
        parts[#parts+1]=('%s %.1f s'):format(M.STAGE_NAMES[k]or('stage '..k),times[k])
    end
    return table.concat(parts,', ')
end
-- One spell without firing ends (firing again, or the Pelican left): counted, and logged when it was long.
local function close_spell(g)
    local A=g.activity
    local S=A.spell
    A.spell=nil
    if not S then return end
    local length=clock-S.since
    if length<M.IDLE_SECONDS then return end
    A.spells=A.spells+1
    A.idle=A.idle+length
    if length>A.longest then A.longest=length end
    local text=('%s: IDLE %.1f s without firing: %s; enemies it could attack meanwhile: up to %d%s'):format(g.label,length,
        stage_text(S.stages),S.max,S.nearest and(' (nearest %.0f m)'):format(S.nearest)or'')
    if A.spells<=M.IDLE_LOG then log(text)else log_module.detail('[HD2Runtime] pelican gunship '..text)end
end
-- The activity part of the summary.
local function activity_text(g)
    local A=g.activity
    local total=0
    for _,t in pairs(A.time)do total=total+t end
    if total<=0 then return''end
    local reasons={}
    for why,n in pairs(A.releases)do reasons[#reasons+1]=('%s %d'):format(why,n)end
    table.sort(reasons)
    return('; activity (%.0f s armed): firing %.0f%% (%s); %d spells of %.0f s or more without firing (%.0f s in all, '
        ..'longest %.1f s); enemies it could attack while not firing: in %d of %d samples (mean %.1f); releases: %s; '
        ..'made due sooner: %d re-picks, %d fire checks'):format(
        total,100*(A.time[12]or 0)/total,stage_text(A.time),A.spells,M.IDLE_SECONDS,A.idle,A.longest,A.with,A.samples,
        A.samples>0 and A.candidates/A.samples or 0,#reasons>0 and table.concat(reasons,', ')or'none',A.repicks,A.fire_checks)
end

local function finish(g,world,reason)
    if g.status~='active'then return end
    g.status='complete'
    active[g.pelican]=nil
    local q=weapon.quiet_counts and weapon.quiet_counts(g.turret)or{}
    if g.impact_binding and g.impact_binding.status=='active'then g.impact_binding.cancel()end
    -- The aim override released while the turret still exists (the Runtime's own only; the game's aim resumes).
    close_spell(g)
    local L=g.lowered
    if L.on and world and g.turret and world_module.entity_exists(world,g.turret)~=false then
        pcall(weapon.aim_release,world,g.turret,g.label)
        L.on=false
    end
    local x=g.explosive
    log(('%s: SUMMARY: %s; chin turret %s; %d rounds fired, %d refills; %d targets locked; body turns %d; orbit %s; '
        ..'target exits %d, target set refusals %d, missed target sets %d (each logged once; verbose logs all)%s'):format(
        g.label,reason,tostring(g.turret),g.rounds,g.refills,g.locks,g.turns,g.orbit_reason or(g.orbit and'running'
        or'none'),q.exits or 0,q.set_refusals or 0,q.set_misses or 0,x and(x.reason and('; explosive rounds REFUSED: '
        ..x.reason)or(('; explosive rounds: %d converted, %d impacts seen, %d stayed plain'):format(x.converted,x.impacts,
        x.refused)))or'')..(g.aim.n>0 and(('; aim (%d samples, mean): %.1f m away, the shot %.2f m %s the aim point and '
        ..'%.2f m to the side, own-motion lead %.2f m, the aim point %s above the root'):format(g.aim.n,g.aim.d/g.aim.n,
        math.abs(g.aim.v/g.aim.n),g.aim.v>=0 and'above'or'below',g.aim.h/g.aim.n,g.aim.lead/g.aim.n,
        g.aim.nodes>0 and('%.2f m'):format(g.aim.node/g.aim.nodes)or'?'))or'')..(g.gun.aim_height and(
        ('; aim point lowered %.2f m above the feet: %d writes, %d starts, %d releases, %d Bile Titan targets left to the '
        ..'game\'s aim, consumed %s%s'):format(g.gun.aim_height,L.writes,L.starts,L.releases,L.own,tostring(L.consumed==true),
        L.refusals>0 and(', last refusal '..tostring(L.refused))or''))or'')..activity_text(g))
    emit(g,{kind='ended',reason=reason,turret=g.turret,rounds=g.rounds,refills=g.refills,locks=g.locks,
        explosive=x and{converted=x.converted,impacts=x.impacts,refused=x.refused}or nil})
end

local function step(g,world)
    local live=pelicans.behaviours(world,{[667]=true})or{}
    local p=live[g.pelican]
    if not p then return finish(g,world,'the Pelican left')end
    -- 1. The chin turret.
    if not g.turret and not g.refused and p.stage>=1 and p.stage<=6 then
        local st=turrets.inspect(world,g.pelican)
        if st and#st.attached==1 and st.turret and st.turret.behaviour==645 and st.mount and st.mount.slot then
            g.turret=st.turret.entity
            instances.associate_child(g.pelican,g.turret,'weapon')
        elseif st and#st.attached>1 then
            g.refused=true
            emit(g,{kind='refused',stage='turret',code='AMBIGUOUS',reason=#st.attached..' turrets name this Pelican'})
            log(('%s: REFUSED: %d turrets name Pelican %d: the chin turret is not unique'):format(g.label,#st.attached,
                g.pelican))
        end
    end
    -- 2. The configuration, once the packages settled (a firing sound's waited for at most M.SOUND_WAIT s).
    local ap_settled=(g.gun.round~='ap4'or ap_state.state=='ready'or ap_state.state=='failed')
        and(not strafing(g.gun.round)or strafing_state.state=='ready'or strafing_state.state=='failed')
    local ss=g.gun.sound and sound_state[g.gun.sound]
    if g.turret and not g.configured then g.waited=(g.waited or 0)+M.STEP end
    local sound_settled=not g.gun.sound or(ss and(ss.state=='ready'or ss.state=='failed'))
        or(g.waited or 0)>=M.SOUND_WAIT
    -- A blast's package (explosion_donors.assets) waited for as long as a sound's; a blast still loading or failed is
    -- refused at the binding (DONOR_NOT_RESIDENT) and its rounds stay plain.
    local ds=g.gun.impact and donor_state[g.gun.impact]
    local donor_settled=not g.gun.impact or(ds and(ds.state=='ready'or ds.state=='failed'))
        or(g.waited or 0)>=M.SOUND_WAIT
    if g.turret and not g.configured and gatling_state.state=='ready'and ap_settled and sound_settled and donor_settled then
        g.configured=true
        configure(world,g)
    elseif g.turret and not g.configured and gatling_state.state=='failed'then
        g.configured=true
        emit(g,{kind='refused',stage='configure',code='ASSET_UNAVAILABLE',reason=tostring(gatling_state.reason)})
        log(g.label..': REFUSED: ASSET_UNAVAILABLE: '..tostring(gatling_state.reason))
    end
    -- 3. The Gatling AI, while its own AI is quiet.
    if g.config and g.gun.behave_as=='gatling_sentry'and not g.ai_done then
        local r,code,reason=weapon.switch_ai(world,g.pelican,g.label)
        if r then
            g.ai_done,g.switched=true,true
            log(('%s: AI: chin turret %d: behaviour %d -> %d'):format(g.label,r.turret,r.before,r.after))
        elseif code~='NOT_QUIET'then
            g.ai_done=true
            emit(g,{kind='refused',stage='ai',code=code,reason=reason})
        end
    end
    -- 4. The orbit, once it holds over its anchor (pelicans.orbit waits for that itself).
    if g.orbit_spec and not g.orbit and g.config then
        local center=pelicans.anchor(world,g.pelican)
        if center then
            local spec={center=center,label=g.label}
            for key,value in pairs(g.orbit_spec)do spec[key]=value end
            local o,why=pelicans.orbit(g.pelican,spec,function(e)
                if e.kind=='started'then log(g.label..': ORBIT started around its anchor')
                elseif e.kind=='stopped'then g.orbit_reason=tostring(e.reason);log(g.label..': ORBIT stopped: '..g.orbit_reason)
                elseif e.kind=='refused'then g.orbit_refusals=(g.orbit_refusals or 0)+1 end
            end)
            g.orbit=o or{status='refused'}
            if not o then
                g.orbit_reason='refused: '..tostring(why)
                emit(g,{kind='refused',stage='orbit',code='ORBIT_REFUSED',reason=tostring(why)})
            end
        end
    end
    if not(g.turret and g.config)then return end
    -- The firing sound skipped while the turret fired or its bank loaded: on its own copy once it is quiet and the bank
    -- resident (pelican_weapon.apply_sound); a package that failed leaves its own.
    if g.sound_retry then
        local ss=sound_state[g.sound_retry]
        if ss and ss.state=='failed'then
            log(('%s: the firing sound\'s package did not load (%s): its own sound instead'):format(g.label,
                tostring(ss.reason)))
            g.sound_retry=nil
            emit(g,{kind='refused',stage='sound',code='ASSET_UNAVAILABLE',reason=tostring(ss.reason)})
        else
            local s,code,reason=weapon.apply_sound(world,g.turret,g.sound_retry,g.label,{quiet=true})
            if s or(code~='NOT_QUIET'and code~='ASSET_UNAVAILABLE')then
                g.sound_retry=nil
                if s then log(('%s: SOUND: chin turret %d: %s, verified %s'):format(g.label,g.turret,g.gun.sound,
                    tostring(s.verified)))
                elseif code~='ALREADY_APPLIED'then emit(g,{kind='refused',stage='sound',code=code,reason=reason})end
            end
        end
    end
    -- 5. Refill, rounds, body facing.
    local rf=weapon.refill_step(world,g.turret,g.label)
    if rf and rf.kind=='refilled'then g.refills=g.refills+1
    elseif rf and rf.kind=='refused'and rf.code~=g.refill_refused then
        g.refill_refused=rf.code
        log(('%s: REFILL REFUSED: %s: %s'):format(g.label,tostring(rf.code),tostring(rf.reason)))
    end
    local w=pelicans.weapon_config(world,g.turret)
    local m=w and w.magazine
    if m and g.mag and g.mag.rounds>m.rounds then g.rounds=g.rounds+(g.mag.rounds-m.rounds)end
    g.mag=m or g.mag
    if g.gun.face then
        local wt=weapon.watch_of(g.turret)
        local point
        if wt and wt.lock then
            local st=world_module.entity_state(world,wt.lock)
            local unit=st and st.descriptor and st.descriptor.unit
            point=unit and unit~=0 and world_module.unit_position(world,unit)or nil
        end
        local ev=heading.face_step(world,g.pelican,point,g.label)
        if ev and ev.kind=='turned'then g.turns=g.turns+1
        elseif ev and ev.kind=='refused'and ev.code~=g.heading_refused then
            g.heading_refused=ev.code
            log(('%s: BODY FACING REFUSED: %s: %s'):format(g.label,tostring(ev.code),tostring(ev.reason)))
        end
    end
end

-- The aim diagnostic (read-only): where the shot crosses the plane through the AI's aim point, against the target's root.
local function aim_tick(g,world)
    if not(g.config and g.turret)or clock<(g.next_aim or 0)then return end
    local a=weapon.ai_state(world,g.turret)
    if not(a and((a.id==213 and a.stage==12)or(a.id==645 and a.stage==3)))then return end
    g.next_aim=clock+M.AIM_EVERY
    local am=weapon.aim_state(world,g.turret)
    if not(am and am.target)then return end
    local st=world_module.entity_state(world,am.target)
    local unit=st and st.descriptor and st.descriptor.unit
    local root=unit and unit~=0 and world_module.unit_position(world,unit)or nil
    local e=weapon.aim_error(am,root,g.speed)
    if not e then return end
    local A=g.aim
    A.n=A.n+1;A.v=A.v+e.vertical;A.h=A.h+e.horizontal;A.lead=A.lead+e.lead_vertical;A.d=A.d+e.distance
    if e.node_height then A.node=A.node+e.node_height;A.nodes=A.nodes+1 end
    local text=('%s: AIM #%d: target %d at %.1f m: the shot crosses %.2f m %s its aim point (%.2f deg) and %.2f m to the '
        ..'side; the AI\'s lead for its own motion (muzzle %.1f m/s, the bullets do not get it) explains %.2f m '
        ..'vertically; the aim point is %s above the target\'s root; aim recoil %s'):format(g.label,A.n,am.target,
        e.distance,math.abs(e.vertical),e.vertical>=0 and'above'or'below',e.vertical_deg,e.horizontal,e.muzzle_speed,
        e.lead_vertical,e.node_height and('%.2f m'):format(e.node_height)or'?',am.recoil and('%.2f / %.2f deg'):format(
        am.recoil.x,am.recoil.y)or'?')
    if A.n<=M.AIM_LOG then log(text)else log_module.detail('[HD2Runtime] pelican gunship '..text)end
end

-- The aim point, lowered (gun.aim_height): every update while the AI aims (stage 5) or fires (stage 12) at a target, its
-- turret's own targeting override follows that target's root plus the height; for no target, another stage or a target
-- of M.OWN_AIM, the override is released and the game's own aim node is used.
local function lower_step(g,world)
    local h=g.gun.aim_height
    if not(h and g.config and g.turret)then return end
    local a=weapon.ai_state(world,g.turret)
    local target=a and a.id==213 and(a.stage==5 or a.stage==12)and a.target or nil
    local own=false
    if target then
        local info=world_module.type_info(world_module.entity_type(world,target))
        own=info~=nil and M.OWN_AIM[info.id]==true
        if own and g.own_aim~=target then
            g.own_aim=target
            g.lowered.own=g.lowered.own+1
        end
    end
    local root
    if target and not own then
        local st=world_module.entity_state(world,target)
        local unit=st and st.descriptor and st.descriptor.unit
        root=unit and unit~=0 and world_module.unit_position(world,unit)or nil
    end
    local L=g.lowered
    if not root then
        if L.on then
            local r,code,reason=weapon.aim_release(world,g.turret,g.label)
            if r then L.on=false;L.releases=L.releases+1;L.point=nil
            elseif code~=L.refused then
                L.refused=code
                log(('%s: AIM POINT RELEASE REFUSED: %s: %s'):format(g.label,tostring(code),tostring(reason)))
            end
        end
        return
    end
    local point={x=root.x,y=root.y,z=root.z+h}
    -- The consumer proof: T (targeting +8) reads back the written point once the game's full targeting path ran.
    if L.on and L.written and not L.consumed then
        local st=weapon.aim_override_state(world,g.turret)
        local T=st and st.point
        local W=L.written
        if T and T.x==W.x and T.y==W.y and T.z==W.z then
            L.consumed=true
            log(('%s: AIM POINT CONSUMED: the game aims at the written point (%.1f, %.1f, %.1f), %.2f m above its target\'s '
                ..'feet'):format(g.label,T.x,T.y,T.z,h))
        end
    end
    if L.on and L.point and math.abs(point.x-L.point.x)<M.AIM_MOVE and math.abs(point.y-L.point.y)<M.AIM_MOVE
        and math.abs(point.z-L.point.z)<M.AIM_MOVE then return end
    local r,code,reason=weapon.aim_lower(world,g.turret,point,g.label)
    if r and r.applied then
        L.writes=L.writes+1
        L.point=point
        local st=weapon.aim_override_state(world,g.turret)
        L.written=st and st.b
        if not L.on then
            L.on=true
            L.starts=L.starts+1
            if L.starts==1 then
                log(('%s: AIM POINT LOWERED: chin turret %d aims at target %d\'s feet + %.2f m (its own targeting '
                    ..'override, %d writes; Bile Titans keep the game\'s aim node); re-written as the target moves'):format(
                    g.label,g.turret,target,h,r.writes))
            end
        end
    elseif code~=L.refused then
        L.refused=code
        L.refusals=L.refusals+1
        log(('%s: AIM POINT REFUSED (the game\'s own aim): %s: %s'):format(g.label,tostring(code),tostring(reason)))
    end
end

local function activity_tick(g,world)
    if not(g.config and g.turret)then return end
    local A=g.activity
    local dt=clock-(A.at or clock)
    A.at=clock
    if dt<=0 or dt>1 then return end
    local a=weapon.ai_state(world,g.turret)
    if not a then return end
    local stage=a.id==213 and a.stage or-1
    A.time[stage]=(A.time[stage]or 0)+dt
    if stage==12 then close_spell(g)return end
    A.spell=A.spell or{since=clock,stages={},max=0}
    local S=A.spell
    S.stages[stage]=(S.stages[stage]or 0)+dt
    if clock>=(S.next or 0)then
        S.next=clock+M.IDLE_SAMPLE
        local list=weapon.candidates(world,g.turret,a)
        local n=list and#list or 0
        A.samples=A.samples+1
        A.candidates=A.candidates+n
        if n>0 then A.with=A.with+1 end
        if n>S.max then S.max=n end
        for _,c in ipairs(list or{})do
            if c.distance and(not S.nearest or c.distance<S.nearest)then S.nearest=c.distance end
        end
    end
end

local function target_tick(g,world)
    lower_step(g,world)
    aim_tick(g,world)
    activity_tick(g,world)
    if not(g.switched and g.turret)then return end
    local a=weapon.ai_state(world,g.turret)
    if not(a and a.id==213)then return end
    for _,e in ipairs(weapon.target_step(world,g.turret,g.label)or{})do
        if e.kind=='locked'then g.locks=g.locks+1 end
        if e.kind=='released'then
            local why=tostring(e.reason)
            g.activity.releases[why]=(g.activity.releases[why]or 0)+1
        elseif e.kind=='repick_forced'then g.activity.repicks=g.activity.repicks+1
        elseif e.kind=='fire_check_forced'then g.activity.fire_checks=g.activity.fire_checks+1 end
    end
end

local watch
local function tick(dt)
    clock=clock+(dt or 0)
    if not next(active)then return end
    local world=world_module.open()
    if not world then return end
    local game=world_module.game_state(world)
    if not(game and game.mission)then
        for _,g in pairs(active)do finish(g,nil,'the mission ended')end
        return
    end
    for _,g in pairs(active)do if g.status=='active'then target_tick(g,world)end end
    if clock<next_step then return end
    next_step=clock+M.STEP
    -- The packages the configuration needs, requested at once (shared by every gunship).
    if gatling_state.state~='ready'and gatling_state.state~='failed'then
        gatling_state.state,gatling_state.reason=weapon.assets(world,M.STEP)
    end
    local ap_wanted=false
    for _,g in pairs(active)do if g.gun.round=='ap4'then ap_wanted=true end end
    if ap_wanted and ap_state.state~='ready'and ap_state.state~='failed'then
        ap_state.state,ap_state.reason=weapon.ap_assets(world,M.STEP)
    end
    local strafing_wanted=false
    for _,g in pairs(active)do if strafing(g.gun.round)then strafing_wanted=true end end
    if strafing_wanted and strafing_state.state~='ready'and strafing_state.state~='failed'then
        strafing_state.state,strafing_state.reason=weapon.strafing_assets(world,M.STEP)
    end
    -- Each wanted blast's package (a stratagem's call-in package or a weapon's; a faction's blast needs none).
    local blasts={}
    for _,g in pairs(active)do if g.status=='active'and g.gun.impact then blasts[g.gun.impact]=true end end
    for name in pairs(blasts)do
        local st=donor_state[name]or{}
        donor_state[name]=st
        if st.state~='ready'and st.state~='failed'then
            st.state,st.reason=require('hd2runtime/runtime/explosion_donors').assets(world,name,M.STEP)
        end
    end
    -- Each wanted firing sound's package (its bank), requested at once and retained.
    local sounds={}
    for _,g in pairs(active)do if g.status=='active'and g.gun.sound then sounds[g.gun.sound]=true end end
    for name in pairs(sounds)do
        local st=sound_state[name]or{}
        sound_state[name]=st
        if st.state~='ready'and st.state~='failed'then st.state,st.reason=weapon.sound_assets(world,M.STEP,name)end
    end
    for _,g in pairs(active)do if g.status=='active'then step(g,world)end end
end

-- Arms one Runtime Pelican. spec = {gun (M.check_gun), orbit (M.check_orbit or nil), credit (true: its chin turret's
-- kills credit the host who called it), credit_peer (another player the host runs the call for: its rounds credit that
-- player), label}. callback(event): 'armed', 'refused' (stage, code, reason), 'ended'.
-- Returns the handle or nil and why.
function M.arm(pelican,spec,callback)
    if type(pelican)~='number'then return nil,'the Pelican entity is required'end
    if active[pelican]then return nil,'Pelican '..pelican..' is armed already'end
    local gun,why=M.check_gun(spec.gun or{})
    if not gun then return nil,why end
    local orbit
    if spec.orbit~=nil then
        orbit,why=M.check_orbit(spec.orbit)
        if not orbit then return nil,why end
    end
    local g={status='active',pelican=pelican,gun=gun,orbit_spec=orbit,credit=spec.credit==true,credit_peer=spec.credit_peer,
        label=tostring(spec.label or('Pelican '..pelican)),callback=callback,rounds=0,refills=0,locks=0,turns=0,
        aim={n=0,v=0,h=0,lead=0,d=0,node=0,nodes=0},lowered={on=false,writes=0,starts=0,releases=0,refusals=0,own=0},
        activity={time={},spells=0,idle=0,longest=0,samples=0,candidates=0,with=0,releases={},repicks=0,fire_checks=0}}
    active[pelican]=g
    if not watch or watch.status~='active'then
        watch={status='active'}
        function watch.tick(dt)if watch.status=='active'then tick(dt)end end
        function watch.cancel()watch.status='cancelled'end
        scheduler.attach(watch)
    end
    return g
end
function M.of(pelican)return active[pelican]end
function M.reset_for_tests()
    active,ap_state,gatling_state,strafing_state,sound_state,donor_state,clock,next_step={},{},{},{},{},{},0,0
    if watch then watch.cancel();watch=nil end
end
return M
