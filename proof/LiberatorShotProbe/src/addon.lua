local hd2=require('mods/skyeshade/hd2runtime')
-- LiberatorShotProbe 0.2.0: THE PER-SHOT MODIFICATION LIVE TEST (hd2.projectiles.modify_shots; docs/projectile-shots.md;
-- research/projectile-ballistics-F5FEE03DCFDB.json). Development only; SOLO; public API only, plus its logging.
-- The AR-23 Liberator's own shots get a damage multiplier on their own copy (hit +0x34); the Liberator Carbine, the
-- Stalwart and every other weapon firing the same projectile stay vanilla. F7 cycles the mode:
--     VANILLA (x1, nothing written: each shot's vanilla values are reported) -> HALF (x0.5) -> DOUBLE (x2) -> VANILLA
-- For each shot: its DamageInfo (the direct hit's standard / durable damage and penetration), its own copies before and
-- after the write and the damage EXPECTED at the muzzle. The measure (0.2.0): the game's own per-weapon stats for the
-- Liberator only, the projectile hits it counted (player_hit) and the damage it recorded (player_damage_dealt): the
-- damage per Liberator hit per mode and the values seen per check. (0.1.0 averaged entity_damaged, which counts every
-- damage credited to the player: a sentry's or a Pelican's too.) Ctrl+F7: the summary per mode.
local mod=hd2.mod()
local BUILD='0.2.0 PER-WEAPON STATS'
local WEAPON='AR-23 Liberator'
mod:log('LiberatorShotProbe '..BUILD..' BUILD: bring the AR-23 Liberator (not the Carbine), start a SOLO mission, shoot '
    ..'small unarmoured enemies (Scavengers, Hunters, Automaton troopers) at close range with single taps, with no '
    ..'sentry or stratagem out; F7 cycles VANILLA -> HALF (x0.5) -> DOUBLE (x2); about 15 hits per mode; Ctrl+F7 prints '
    ..'the summary.')

local MODES={{name='VANILLA',damage=1},{name='HALF',damage=0.5},{name='DOUBLE',damage=2}}
local state={mode=1,shots={},any={},recorded={},hits={},values={},logged={}}
for _,m in ipairs(MODES)do
    state.shots[m.name],state.any[m.name],state.recorded[m.name],state.hits[m.name]=0,0,0,0
    state.values[m.name],state.logged[m.name]={},0
end
local function mode()return MODES[state.mode]end
local function g(v)return v and('%g'):format(v)or'?'end

local function on_shot(e)
    local m=mode()
    state.shots[m.name]=state.shots[m.name]+1
    if state.logged[m.name]>=5 then return end
    state.logged[m.name]=state.logged[m.name]+1
    local d,a,bf=e.before.damage or{},e.after or e.before,e.before
    local ap,dap=bf.armor_penetration or{},d.armor_penetration or{}
    local mult=a.damage_multiplier or 1
    mod:log(('SHOT [%s] #%d (pool slot %d, %s): its DamageInfo %s = %s standard / %s durable, penetration %s/%s/%s/%s '
        ..'(the shot\'s own lanes %s/%s/%s/%s); its own copies: damage multiplier %s -> %s, penetration multiplier %s -> %s, '
        ..'speed %.1f m/s (reference %.1f), gravity %s, drag %s; %.2f m travelled when written. EXPECTED direct hit at '
        ..'the muzzle: %s standard (the multiplier\'s; durable parts: %s, under test)')
        :format(m.name,state.shots[m.name],e.slot,e.kind,tostring(d.id),tostring(d.standard),tostring(d.durable),
        tostring(dap[1]),tostring(dap[2]),tostring(dap[3]),tostring(dap[4]),tostring(ap[1]),tostring(ap[2]),
        tostring(ap[3]),tostring(ap[4]),g(bf.damage_multiplier),g(a.damage_multiplier),g(bf.penetration_multiplier),
        g(a.penetration_multiplier),bf.speed or 0,bf.reference_speed or 0,g(bf.gravity),g(bf.drag),bf.distance or 0,
        d.standard and g(d.standard*mult)or'?',d.durable and g(d.durable)..' if unscaled, '..g(d.durable*mult)
        ..' if scaled'or'?'))
end

local shots
local function apply()
    local m=mode()
    local opts={damage=m.damage}
    if shots and shots.status=='active'then
        local ok,code,why=shots:set(opts)
        if not ok then mod:log(('MODE %s NOT SET: %s: %s'):format(m.name,tostring(code),tostring(why)))return end
    else
        opts.on_shot=on_shot
        opts.label='LiberatorShotProbe'
        shots=hd2.projectiles.modify_shots(WEAPON,opts)
        if shots.status~='active'then
            mod:log(('REFUSED: %s: %s'):format(tostring(shots.code),tostring(shots.reason)))
            return
        end
    end
    mod:log(('MODE %s: %s shots x%g damage (each shot\'s own copy; every other weapon vanilla)'):format(m.name,WEAPON,
        m.damage))
end
apply()

-- Context only: every damage credited to the player (a sentry's, a Pelican's and a stratagem's too).
hd2.events.on('entity_damaged',function(e)
    if not e.local_attacker then return end
    local m=mode()
    state.any[m.name]=state.any[m.name]+1
    if state.any[m.name]<=8 then
        mod:log(('ANY DAMAGE [%s] #%d: %s lost %s health (now %s) (anything credited to you counts here)'):format(m.name,
            state.any[m.name],tostring(e.display_name or e.name),g(e.damage),g(e.health)))
    end
end)
-- The measure: the Liberator's own hits and damage, as the game's per-weapon stats count them.
hd2.events.on('player_hit',function(e)
    for _,s in ipairs(e.sources or{})do
        if s.name==WEAPON then
            local m=mode()
            state.hits[m.name]=state.hits[m.name]+(s.hits or 0)
        end
    end
end)
hd2.events.on('player_damage_dealt',function(e)
    for _,s in ipairs(e.sources or{})do
        if s.name==WEAPON then
            local m=mode()
            state.recorded[m.name]=state.recorded[m.name]+(s.damage or 0)
            local v=state.values[m.name]
            v[s.damage or 0]=(v[s.damage or 0]or 0)+1
            mod:log(('RECORDED [%s]: the game recorded %s damage for the %s since the last check (this mode: %s damage, %d '
                ..'hits)'):format(m.name,g(s.damage),WEAPON,g(state.recorded[m.name]),state.hits[m.name]))
        end
    end
end)

local function summary()
    local base
    for _,m in ipairs(MODES)do
        local hits,recorded=state.hits[m.name],state.recorded[m.name]
        local mean=hits>0 and recorded/hits or nil
        if m.name=='VANILLA'then base=mean end
        local values={}
        for v,n in pairs(state.values[m.name])do values[#values+1]={v=v,n=n}end
        table.sort(values,function(a,c)return a.n>c.n end)
        local common={}
        for k=1,math.min(5,#values)do common[k]=('%s (x%d)'):format(g(values[k].v),values[k].n)end
        mod:log(('SUMMARY [%s x%g]: %d Liberator shots, %d Liberator hits (the game\'s count), %s damage recorded for the '
            ..'Liberator = %s per hit%s; most common values per check: %s'):format(m.name,m.damage,state.shots[m.name],hits,
            g(recorded),mean and('%.2f'):format(mean)or'-',(mean and base and m.name~='VANILLA')and
            (' = %.3f x VANILLA (expected %g on standard damage)'):format(mean/base,m.damage)or'',
            #common>0 and table.concat(common,', ')or'none'))
    end
    if shots and shots.stats then
        local s=shots:stats()
        if s then
            local parts={}
            for code,n in pairs(s.refused or{})do parts[#parts+1]=code..' x '..n end
            mod:log(('SUMMARY: %d Liberator shots seen, %d modified, %d untouched, %d not yours, %d from another weapon '
                ..'(e.g. the Carbine) left vanilla%s'):format(s.shots,s.modified,s.untouched,s.others,s.other_sources,
                #parts>0 and('; vanilla: '..table.concat(parts,', '))or''))
        end
    end
end

hd2.input.bind('liberator_shot_probe.mode',{key='F7',on_press=function()
    state.mode=state.mode%#MODES+1
    apply()
end})
hd2.input.bind('liberator_shot_probe.summary',{key='Ctrl+F7',on_press=summary})
hd2.events.on('mission_ended',function()summary()end)
