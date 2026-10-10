local hd2=require('mods/skyeshade/hd2runtime')
-- MultiBeamProof 0.1.0: EXPERIMENTAL, SOLO-ONLY live test of the multi-weapon beam swap (the AR-23 Liberator, LAS-58
-- Talon and SMG-32 Reprimand fire LAS-13 Trident pulses, all three together or one at a time;
-- research/docs/multi-beam-swap-F5FEE03DCFDB.md). Needs the HD2Runtime build of branch exp/multi-beam
-- (runtime/experiment_beam_swap.lua 0.1.x); never part of a release. See README.md for the plan.
--   Ctrl+Alt+F5  status (read-only): pins, record 23, per weapon state and live count, solo, Trident package
--   Ctrl+Alt+F8  choose the weapon set for F6: all three -> Liberator -> Talon -> Reprimand -> all three (no write)
--   Ctrl+Alt+F6  apply the chosen set in one all-or-nothing write (press twice within 6 s)
--   Ctrl+Alt+F7  restore every swapped weapon, then record 23 (press twice within 6 s)
-- Every write refuses unless: zero live instances of every weapon it writes (equip other weapons, do not open the
-- armory), solo, every pin and every before byte as reviewed, and (apply) the Trident's package resident.
-- RESTART THE GAME after using it. The live-proven Liberator-only path stays in LiberatorBeamProof (Ctrl+Shift+F1..F4).
local mod=hd2.mod()
local BUILD='0.1.0'
mod:log('MultiBeamProof '..BUILD..' EXPERIMENTAL BUILD: SOLO ONLY. Ctrl+Alt+F5 status, Ctrl+Alt+F8 choose the weapon '
    ..'set, Ctrl+Alt+F6 apply it (Liberator + Talon + Reprimand by default), Ctrl+Alt+F7 restore; write keys need two '
    ..'presses within 6 s. Zero live instances of the swapped weapons for every write and the restore: equip other '
    ..'weapons and do not open the armory. RESTART THE GAME after using it.')

local ok,X=pcall(require,'hd2runtime/runtime/experiment_beam_swap')
if not ok then
    mod:log('UNAVAILABLE: this HD2Runtime build has no multi-weapon beam experiment (install the exp/multi-beam '
        ..'runtime ZIP): '..tostring(X))
    return
end
if not tostring(X.VERSION):find('^0%.1%.')then
    mod:log('UNAVAILABLE: this HD2Runtime build has multi-weapon beam experiment '..tostring(X.VERSION)..'; proof '
        ..BUILD..' needs 0.1.x (install the exp/multi-beam runtime ZIP of the same hand-over)')
    return
end

-- The Trident's package (laser_shotgun), held for the session by the Runtime's reference-counted request.
local assets
local function want_assets()
    if assets and assets.status~='rejected'and assets.status~='cancelled'then return end
    assets=hd2.require_assets({id='multi-beam-trident',targets={hd2.weapon('LAS-13 Trident')}})
end
want_assets()

local SETS={{label='all three (Liberator, Talon, Reprimand)',ids={'liberator','talon','reprimand'}},
    {label='AR-23 Liberator only',ids={'liberator'}},{label='LAS-58 Talon only',ids={'talon'}},
    {label='SMG-32 Reprimand only',ids={'reprimand'}}}
local chosen=1

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
    mod:log(('STATUS: record 23 %s; solo %s (%s); Trident package %s (asset request %s); F6 set: %s%s'):format(
        tostring(s.record),tostring(s.solo),tostring(s.solo_reason),tostring(s.assets),
        tostring(assets and assets.status),SETS[chosen].label,
        s.restart_required and'; RESTART THE GAME after this session'or''))
end})
hd2.input.bind('multi_beam_proof.choose',{key='Ctrl+Alt+F8',on_press=function()
    chosen=chosen%#SETS+1
    mod:log('F6 will apply: '..SETS[chosen].label)
end})
hd2.input.bind('multi_beam_proof.apply',{key='Ctrl+Alt+F6',on_press=function()
    want_assets()
    local set=SETS[chosen]
    confirm('apply','APPLY '..set.label,function()report('APPLY '..set.label,X.apply(set.ids))end)
end})
hd2.input.bind('multi_beam_proof.restore',{key='Ctrl+Alt+F7',on_press=function()
    confirm('restore','RESTORE (every swapped weapon, then record 23)',function()report('RESTORE',X.restore())end)
end})
mod:log('loaded ('..BUILD..' EXPERIMENTAL): Ctrl+Alt+F5 status, Ctrl+Alt+F8 choose set, Ctrl+Alt+F6 apply, '
    ..'Ctrl+Alt+F7 restore; F6 set: '..SETS[chosen].label)
