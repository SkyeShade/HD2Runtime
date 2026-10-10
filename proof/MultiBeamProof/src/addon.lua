local hd2=require('mods/skyeshade/hd2runtime')
-- MultiBeamProof 0.2.0: EXPERIMENTAL, SOLO-ONLY live test of the multi-weapon beam swap (the AR-23 Liberator, LAS-58
-- Talon and SMG-32 Reprimand fire LAS-13 Trident pulses, all three together or one at a time;
-- research/docs/multi-beam-swap-F5FEE03DCFDB.md) and, new in 0.2.0, of each swapped weapon's OWN beam damage and armour
-- penetration (research/docs/beam-damage-per-weapon-F5FEE03DCFDB.md). Needs the HD2Runtime build of branch
-- exp/multi-beam (runtime/experiment_beam_swap.lua 0.2.x, runtime/experiment_beam_damage.lua 0.1.x); never part of a
-- release. See README.md for the plan.
--   Ctrl+Alt+F5  status (read-only): pins, record 23, per weapon state and live count, solo, Trident package, damage
--   Ctrl+Alt+F8  choose the weapon set for F6: all three -> Liberator -> Talon -> Reprimand -> all three (no write)
--   Ctrl+Alt+F6  apply the chosen set in one all-or-nothing write (press twice within 6 s)
--   Ctrl+Alt+F7  restore every swapped weapon, then record 23 (press twice within 6 s)
--   Ctrl+Alt+F9  choose the per-weapon damage profile: off -> A -> B -> off (the swapped weapons' next shots)
-- Every swap write refuses unless: zero live instances of every weapon it writes (equip other weapons, do not open the
-- armory), solo, every pin and every before byte as reviewed, and (apply) the Trident's package resident.
-- RESTART THE GAME after using it. The live-proven Liberator-only path stays in LiberatorBeamProof (Ctrl+Shift+F1..F4).
local mod=hd2.mod()
local BUILD='0.2.0'
mod:log('MultiBeamProof '..BUILD..' EXPERIMENTAL BUILD: SOLO ONLY. Ctrl+Alt+F5 status, Ctrl+Alt+F8 choose the weapon '
    ..'set, Ctrl+Alt+F6 apply it (Liberator + Talon + Reprimand by default), Ctrl+Alt+F7 restore, Ctrl+Alt+F9 choose '
    ..'the per-weapon damage profile (off by default); write keys need two presses within 6 s. Zero live instances '
    ..'of the swapped weapons for every write and the restore: equip other weapons and do not open the armory. '
    ..'RESTART THE GAME after using it.')

local ok,X=pcall(require,'hd2runtime/runtime/experiment_beam_swap')
if not ok then
    mod:log('UNAVAILABLE: this HD2Runtime build has no multi-weapon beam experiment (install the exp/multi-beam '
        ..'runtime ZIP): '..tostring(X))
    return
end
if not tostring(X.VERSION):find('^0%.2%.')then
    mod:log('UNAVAILABLE: this HD2Runtime build has multi-weapon beam experiment '..tostring(X.VERSION)..'; proof '
        ..BUILD..' needs 0.2.x (install the exp/multi-beam runtime ZIP of the same hand-over)')
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

local function apply_profile(quiet)
    local p=PROFILES[profile]
    if p.scythe then want_scythe()end
    local states=X.weapon_states()or{}
    local waiting=false
    for _,id in ipairs({'liberator','talon','reprimand'})do
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

local function report(what,result)
    if type(result)~='table'then mod:log(what..': no result');return end
    if result.ok then
        mod:log(('%s: OK, %s write%s'):format(what,tostring(result.writes or 0),result.writes==1 and''or's'))
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
    mod:log(('STATUS: record 23 %s; solo %s (%s); Trident package %s (asset request %s); F6 set: %s; damage '
        ..'profile %s%s'):format(tostring(s.record),tostring(s.solo),tostring(s.solo_reason),tostring(s.assets),
        tostring(assets and assets.status),SETS[chosen].label,PROFILES[profile].label,
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
    confirm('restore','RESTORE (every swapped weapon, then record 23)',function()report('RESTORE',X.restore())end)
end})
hd2.input.bind('multi_beam_proof.damage',{key='Ctrl+Alt+F9',on_press=function()
    profile=profile%#PROFILES+1
    retries=0
    mod:log('damage profile '..PROFILES[profile].label)
    apply_profile(false)
end})
mod:log('loaded ('..BUILD..' EXPERIMENTAL): Ctrl+Alt+F5 status, Ctrl+Alt+F8 choose set, Ctrl+Alt+F6 apply, '
    ..'Ctrl+Alt+F7 restore, Ctrl+Alt+F9 damage profile; F6 set: '..SETS[chosen].label..'; damage profile '
    ..PROFILES[profile].label)
