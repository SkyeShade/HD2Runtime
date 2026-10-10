local hd2=require('mods/skyeshade/hd2runtime')
-- MultiBeamProof 0.3.1: EXPERIMENTAL, SOLO-ONLY live test of the multi-weapon beam swap (the AR-23 Liberator, LAS-58
-- Talon and SMG-32 Reprimand fire LAS-13 Trident pulses, all three together or one at a time;
-- research/docs/multi-beam-swap-F5FEE03DCFDB.md), of each swapped weapon's own beam damage and armour penetration
-- (0.2.0; research/docs/beam-damage-per-weapon-F5FEE03DCFDB.md) and, new in 0.3.0, of each weapon's OWN BeamWeapon
-- record in a Runtime-owned copy of the BeamWeapon table the game is switched to read, so each has its own rate of fire
-- and pulse (research/docs/beam-table-relocation-F5FEE03DCFDB.md). New in 0.3.1: a rate without its own pulse gets a
-- pulse that fits its shot interval (the 0.3.0 live test capped 600 and 900 rpm at about 330-360 rpm: the next pulse
-- starts only the update after the last one ends; research/docs/beam-pulse-rate-F5FEE03DCFDB.md). Needs the HD2Runtime
-- build of branch exp/multi-beam (runtime/experiment_beam_swap.lua 0.3.1+, runtime/experiment_beam_table.lua 0.1.x,
-- runtime/experiment_beam_damage.lua 0.1.x); never part of a release. See README.md for the plan.
--   Ctrl+Alt+F5   status (read-only): the path (owned table / shared record), per weapon state, rate and live count,
--                 solo, Trident package, damage
--   Ctrl+Alt+F8   choose the weapon set for F6: all three -> Liberator -> Talon -> Reprimand -> all three (no write)
--   Ctrl+Alt+F6   apply the chosen set in one all-or-nothing write (press twice within 6 s)
--   Ctrl+Alt+F7   restore every swapped weapon, then the table (press twice within 6 s)
--   Ctrl+Alt+F9   choose the per-weapon damage profile: off -> A -> B -> off (the swapped weapons' next shots)
--   Ctrl+Alt+F10  choose the per-weapon rate / pulse profile: Trident -> R -> F -> C -> P -> Trident (owned table:
--                 at once)
-- Every swap write refuses unless: zero live instances of every weapon it writes (equip other weapons, do not open the
-- armory), solo, every pin and every before byte as reviewed, and (apply) the Trident's package resident.
-- RESTART THE GAME after using it. The live-proven Liberator-only path stays in LiberatorBeamProof (Ctrl+Shift+F1..F4).
local mod=hd2.mod()
local BUILD='0.3.1'
mod:log('MultiBeamProof '..BUILD..' EXPERIMENTAL BUILD: SOLO ONLY. Ctrl+Alt+F5 status, Ctrl+Alt+F8 choose the weapon '
    ..'set, Ctrl+Alt+F6 apply it (Liberator + Talon + Reprimand by default), Ctrl+Alt+F7 restore, Ctrl+Alt+F9 choose '
    ..'the per-weapon damage profile (off by default), Ctrl+Alt+F10 choose the per-weapon rate / pulse profile (the '
    ..'Trident\'s by default); write keys need two presses within 6 s. Zero live instances of the swapped weapons for '
    ..'every write and the restore: equip other weapons and do not open the armory. RESTART THE GAME after using it.')

local ok,X=pcall(require,'hd2runtime/runtime/experiment_beam_swap')
if not ok then
    mod:log('UNAVAILABLE: this HD2Runtime build has no multi-weapon beam experiment (install the exp/multi-beam '
        ..'runtime ZIP): '..tostring(X))
    return
end
if not(tostring(X.VERSION):find('^0%.3%.')and X.pulse_fit)then
    mod:log('UNAVAILABLE: this HD2Runtime build has multi-weapon beam experiment '..tostring(X.VERSION)..'; proof '
        ..BUILD..' needs 0.3.1 or later (the fitted pulse; install the exp/multi-beam runtime ZIP of the same '
        ..'hand-over)')
    return
end
local dok,BD=pcall(require,'hd2runtime/runtime/experiment_beam_damage')
if not(dok and tostring(BD.VERSION):find('^0%.1%.'))then
    mod:log('UNAVAILABLE: this HD2Runtime build has no per-weapon beam damage 0.1.x (install the exp/multi-beam '
        ..'runtime ZIP of the same hand-over): '..tostring(dok and BD.VERSION or BD))
    return
end

-- The Trident's package (laser_shotgun), held for the session by the Runtime's reference-counted request.
local assets
local function want_assets()
    if assets and assets.status~='rejected'and assets.status~='cancelled'then return end
    assets=hd2.require_assets({id='multi-beam-trident',targets={hd2.weapon('LAS-13 Trident')}})
end
want_assets()
-- The LAS-5 Scythe's package (laser_rifle): profile B gives the Liberator the Scythe's damage row (its status effect).
local scythe
local function want_scythe()
    if scythe and scythe.status~='rejected'and scythe.status~='cancelled'then return end
    scythe=hd2.require_assets({id='multi-beam-scythe',targets={hd2.weapon('LAS-5 Scythe')}})
end

local IDS={'liberator','talon','reprimand'}
local SETS={{label='all three (Liberator, Talon, Reprimand)',ids={'liberator','talon','reprimand'}},
    {label='AR-23 Liberator only',ids={'liberator'}},{label='LAS-58 Talon only',ids={'talon'}},
    {label='SMG-32 Reprimand only',ids={'reprimand'}}}
local chosen=1

-- Damage profiles. The Trident pulse: 60 standard / 6 durable damage, armour penetration 2/2/2/0 (DamageInfo 508).
local PROFILES={
    {label='off: every swapped weapon fires the Trident\'s own damage (60 / 6, AP 2)',
        weapons={liberator={},talon={},reprimand={}}},
    {label='A: Liberator 10x damage (600 / 60), Talon 0.1x damage (6 / 0.6), Reprimand AP 6 (60 / 6)',
        weapons={liberator={damage_multiplier=10},talon={damage_multiplier=0.1},reprimand={armor_penetration=6}}},
    {label='B: Liberator the LAS-5 Scythe\'s damage row (350 / 70, AP 2, its status), Talon 150 damage and AP 3 '
        ..'(150 / 15), Reprimand unchanged (the control: 60 / 6, AP 2)',
        scythe=true,weapons={liberator={damage_row='LAS-5 Scythe'},talon={damage=150,armor_penetration=3},
            reprimand={}}},
}
local profile=1
local retries=0

-- Rate / pulse profiles (the owned table: each weapon's own record +104 rpm, +108 beams per pulse, +112 s).
-- The Trident: 300 rpm, 2 beams per pulse, 0.15 s. 0.3.1: a rate without pulse_seconds gets a fitted pulse
-- (max(60 / (2 rpm), 60 / rpm - 1 / 30) s when the Trident's 0.15 s does not fit); an explicit pulse is kept (and a cap
-- warned): C is the capped control (the Reprimand exactly as in the 0.3.0 profile R).
local BEAMS={
    {label='Trident: every swapped weapon 300 rpm, 2 beams per pulse, 0.15 s (the Trident\'s own)',
        weapons={liberator={},talon={},reprimand={}}},
    {label='R (rates, fitted): Liberator 600 rpm (0.067 s pulse), Talon 150 rpm (0.15 s), Reprimand 900 rpm '
        ..'(0.033 s pulse)',
        weapons={liberator={fire_rate=600},talon={fire_rate=150},reprimand={fire_rate=900}}},
    {label='F (fast, fitted): Liberator 600 rpm (0.067 s), Talon 150 rpm, Reprimand 1200 rpm (0.025 s pulse: hits '
        ..'only above 40 fps)',
        weapons={liberator={fire_rate=600},talon={fire_rate=150},reprimand={fire_rate=1200}}},
    {label='C (capped control): Liberator 600 rpm (fitted), Talon 150 rpm, Reprimand 900 rpm with the Trident\'s '
        ..'0.15 s pulse (expect about 330-360 rpm, as in the 0.3.0 test)',
        weapons={liberator={fire_rate=600},talon={fire_rate=150},reprimand={fire_rate=900,pulse_seconds=0.15}}},
    {label='P (pulse): Liberator 600 rpm, 1 beam per pulse (fitted); Talon 150 rpm, 6 beams per pulse; Reprimand '
        ..'900 rpm, 1.0 s pulse (capped: about 57 rpm)',
        weapons={liberator={fire_rate=600,pulse_beams=1},talon={fire_rate=150,pulse_beams=6},
            reprimand={fire_rate=900,pulse_seconds=1.0}}},
}
local beams=1

local function apply_profile(quiet)
    local p=PROFILES[profile]
    if p.scythe then want_scythe()end
    local states=X.weapon_states()or{}
    local waiting=false
    for _,id in ipairs(IDS)do
        if states[id]=='applied'then
            local r=BD.set(id,p.weapons[id])
            if not r.ok and tostring(r.reason):find('package',1,true)then waiting=true end
        elseif not quiet then
            mod:log(('damage profile: the %s is not swapped (%s); its profile applies after F6'):format(id,
                tostring(states[id])))
        end
    end
    if waiting and retries<15 then
        retries=retries+1
        mod:log('damage profile '..p.label:sub(1,1)..': waiting for the LAS-5 Scythe package (retry '..retries
            ..' in 2 s)')
        hd2.after(2,function()apply_profile(true)end)
    else
        retries=0
    end
end

-- Each weapon's rate / pulse: written at once on the owned table, else kept for the next owned-table apply.
local function apply_beams()
    local p=BEAMS[beams]
    for _,id in ipairs(IDS)do
        local r=X.configure(id,p.weapons[id])
        local s=X.settings(id)
        local f=r.pulse
        mod:log(('beam profile %s: %s %d rpm, %d beams per pulse, %.3g s%s: %s'):format(p.label:sub(1,1),id,
            s.fire_rate,s.pulse_beams,s.pulse_seconds,f and(' (%s; about %d rpm at a steady 60 fps)'):format(
            f.fitted and'pulse FITTED'or f.capped and'pulse CAPS the rate'or'pulse fits',
            math.floor(f.rpm_at_60+0.5))or'',r.ok and(r.pending and'kept for the next owned-table apply'
            or(tostring(r.writes or 0)..' write'..(r.writes==1 and''or's')))or('NOT APPLIED: '..tostring(r.reason))))
    end
end

local function report(what,result)
    if type(result)~='table'then mod:log(what..': no result');return end
    if result.ok then
        mod:log(('%s: OK, %s write%s%s'):format(what,tostring(result.writes or 0),result.writes==1 and''or's',
            result.path and(', path '..tostring(X.PATHS[result.path]))or''))
    else
        mod:log(what..': REFUSED: '..tostring(result.reason))
    end
    X.status()      -- logs one 'MULTI BEAM: <weapon>: <state>' line per weapon
end

local armed={}
local function confirm(key,what,fn)
    if not armed[key]then
        armed[key]=true
        mod:log(what..': press the same key again within 6 s to confirm')
        hd2.after(6,function()armed[key]=nil end)
        return
    end
    armed[key]=nil
    fn()
end

hd2.input.bind('multi_beam_proof.status',{key='Ctrl+Alt+F5',on_press=function()
    want_assets()
    local s=X.status()
    if not s.ok then mod:log('STATUS: REFUSED: '..tostring(s.reason));return end
    local rates={}
    for _,w in ipairs(s.weapons)do
        rates[#rates+1]=w.settings and('%s %d rpm'):format(w.id,w.settings.fire_rate)or(w.id..' '..w.state)
    end
    mod:log(('STATUS: path %s (%s); owned table %s; record 23 %s; solo %s (%s); Trident package %s (asset request '
        ..'%s); rates %s; F6 set: %s; damage profile %s; beam profile %s%s'):format(tostring(s.path),
        s.table=='owned'and'the game reads HD2Runtime\'s copy'or'the game reads the file\'s own table',
        s.owned_available and'available'or('UNAVAILABLE: '..tostring(s.owned_reason)),tostring(s.record),
        tostring(s.solo),tostring(s.solo_reason),tostring(s.assets),tostring(assets and assets.status),
        table.concat(rates,', '),SETS[chosen].label,PROFILES[profile].label,BEAMS[beams].label,
        s.restart_required and'; RESTART THE GAME after this session'or''))
    local d=BD.status()    -- logs one 'MULTI BEAM DAMAGE: <weapon>: ...' line per weapon
    if d.unavailable then mod:log('damage: UNAVAILABLE: '..tostring(d.unavailable))end
end})
hd2.input.bind('multi_beam_proof.choose',{key='Ctrl+Alt+F8',on_press=function()
    chosen=chosen%#SETS+1
    mod:log('F6 will apply: '..SETS[chosen].label)
end})
hd2.input.bind('multi_beam_proof.apply',{key='Ctrl+Alt+F6',on_press=function()
    want_assets()
    local set=SETS[chosen]
    confirm('apply','APPLY '..set.label,function()
        local r=X.apply(set.ids)
        report('APPLY '..set.label,r)
        if r.ok and profile~=1 then apply_profile(true)end
    end)
end})
hd2.input.bind('multi_beam_proof.restore',{key='Ctrl+Alt+F7',on_press=function()
    confirm('restore','RESTORE (every swapped weapon, then the table)',function()report('RESTORE',X.restore())end)
end})
hd2.input.bind('multi_beam_proof.damage',{key='Ctrl+Alt+F9',on_press=function()
    profile=profile%#PROFILES+1
    retries=0
    mod:log('damage profile '..PROFILES[profile].label)
    apply_profile(false)
end})
hd2.input.bind('multi_beam_proof.beams',{key='Ctrl+Alt+F10',on_press=function()
    beams=beams%#BEAMS+1
    mod:log('beam profile '..BEAMS[beams].label)
    apply_beams()
end})
mod:log('loaded ('..BUILD..' EXPERIMENTAL): Ctrl+Alt+F5 status, Ctrl+Alt+F8 choose set, Ctrl+Alt+F6 apply, '
    ..'Ctrl+Alt+F7 restore, Ctrl+Alt+F9 damage profile, Ctrl+Alt+F10 beam profile; F6 set: '..SETS[chosen].label
    ..'; damage profile '..PROFILES[profile].label..'; beam profile '..BEAMS[beams].label)
