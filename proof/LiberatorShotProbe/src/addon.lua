local hd2=require('mods/skyeshade/hd2runtime')
-- LiberatorShotProbe 0.1.0: THE PER-SHOT MODIFICATION LIVE TEST (hd2.projectiles.modify_shots; docs/projectile-shots.md;
-- research/projectile-ballistics-F5FEE03DCFDB.json). Development only; SOLO; public API only, plus its logging.
-- The AR-23 Liberator's own shots get a damage multiplier on their own copy (hit +0x34); the Liberator Carbine, the
-- Stalwart and every other weapon firing the same projectile stay vanilla. F7 cycles the mode:
--     VANILLA (x1, nothing written: each shot's vanilla values are reported) -> HALF (x0.5) -> DOUBLE (x2) -> VANILLA
-- For each shot: its DamageInfo (the direct hit's standard / durable damage and penetration), its own copies before and
-- after the write and the damage EXPECTED at the muzzle. For each hit of the local player: the health the victim lost
-- (entity_damaged) and the damage the game recorded for the Liberator (player_damage_dealt). Ctrl+F7: the summary per
-- mode (shots, hits, mean damage per hit, its ratio to VANILLA's).
local mod=hd2.mod()
local BUILD='0.1.0 LIBERATOR SHOT PROBE'
local WEAPON='AR-23 Liberator'
mod:log('LiberatorShotProbe '..BUILD..' BUILD: bring the AR-23 Liberator (not the Carbine), start a SOLO mission, shoot '
    ..'one unarmoured enemy\'s body at close range with single taps; F7 cycles VANILLA -> HALF (x0.5) -> DOUBLE (x2); '
    ..'about 10 hits per mode on the same enemy type; Ctrl+F7 prints the summary.')

local MODES={{name='VANILLA',damage=1},{name='HALF',damage=0.5},{name='DOUBLE',damage=2}}
local state={mode=1,shots={},hits={},recorded={},logged={}}
for _,m in ipairs(MODES)do state.shots[m.name],state.hits[m.name],state.recorded[m.name],state.logged[m.name]=0,{},0,0 end
local function mode()return MODES[state.mode]end
local function g(v)return v and('%g'):format(v)or'?'end

local function on_shot(e)
    local m=mode()
    state.shots[m.name]=state.shots[m.name]+1
    if state.logged[m.name]>=5 then return end
    state.logged[m.name]=state.logged[m.name]+1
    local d,a,bf=e.before.damage or{},e.after or e.before,e.before
    local ap=bf.armor_penetration or{}
    local mult=a.damage_multiplier or 1
    mod:log(('SHOT [%s] #%d (pool slot %d, %s): its DamageInfo %s = %s standard / %s durable, penetration %s/%s/%s/%s '
        ..'(the shot\'s own lanes %s/%s/%s/%s); its own copies: damage multiplier %s -> %s, penetration multiplier %s -> %s, '
        ..'speed %.1f m/s (reference %.1f), gravity %s, drag %s; %.2f m travelled when written. EXPECTED direct hit at '
        ..'the muzzle: %s standard / %s durable (less at range: the game scales it by 0.25 + 0.75 (speed/reference)^2)')
        :format(m.name,state.shots[m.name],e.slot,e.kind,tostring(d.id),tostring(d.standard),tostring(d.durable),
        tostring(d.armor_penetration and d.armor_penetration[1]),tostring(d.armor_penetration and d.armor_penetration[2]),
        tostring(d.armor_penetration and d.armor_penetration[3]),tostring(d.armor_penetration and d.armor_penetration[4]),
        tostring(ap[1]),tostring(ap[2]),tostring(ap[3]),tostring(ap[4]),g(bf.damage_multiplier),g(a.damage_multiplier),
        g(bf.penetration_multiplier),g(a.penetration_multiplier),bf.speed or 0,bf.reference_speed or 0,g(bf.gravity),
        g(bf.drag),bf.distance or 0,d.standard and g(d.standard*mult)or'?',d.durable and g(d.durable*mult)or'?'))
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

hd2.events.on('entity_damaged',function(e)
    if not e.local_attacker then return end
    local m=mode()
    local list=state.hits[m.name]
    list[#list+1]=e.damage
    if#list<=12 then
        mod:log(('HIT [%s] #%d: %s lost %s health (now %s)'):format(m.name,#list,tostring(e.display_name or e.name),
            g(e.damage),g(e.health)))
    end
end)
hd2.events.on('player_damage_dealt',function(e)
    for _,s in ipairs(e.sources or{})do
        if s.name==WEAPON then
            local m=mode()
            state.recorded[m.name]=state.recorded[m.name]+(s.damage or 0)
            mod:log(('RECORDED [%s]: the game recorded %s damage for the %s since the last check (this mode: %s)'):format(
                m.name,g(s.damage),WEAPON,g(state.recorded[m.name])))
        end
    end
end)

local function summary()
    local base
    for _,m in ipairs(MODES)do
        local list=state.hits[m.name]
        local sum=0
        for _,v in ipairs(list)do sum=sum+v end
        local mean=#list>0 and sum/#list or nil
        if m.name=='VANILLA'then base=mean end
        mod:log(('SUMMARY [%s x%g]: %d shots, %d hits, mean %s health per hit%s; the game recorded %s for the %s')
            :format(m.name,m.damage,state.shots[m.name],#list,mean and('%.2f'):format(mean)or'-',
            (mean and base and m.name~='VANILLA')and(' = %.3f x VANILLA (expected %g)'):format(mean/base,m.damage)or'',
            g(state.recorded[m.name]),WEAPON))
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
