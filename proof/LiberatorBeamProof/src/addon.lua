local hd2=require('mods/skyeshade/hd2runtime')
-- LiberatorBeamProof 0.1.0: EXPERIMENTAL, SOLO-ONLY live test of the Liberator component swap (the AR-23 Liberator
-- fires LAS-13 Trident pulses; research/docs/component-swap-liberator-beam.md). Needs the HD2Runtime build of branch
-- exp/liberator-beam (runtime/experiment_liberator_beam.lua); never part of a release. See README.md for the L0-L4 plan.
--   Ctrl+Shift+F1  L0  status (read-only): pins, state, live Liberators, solo, Trident package
--   Ctrl+Shift+F2  L1  write record 23 + row 21 (press twice within 6 s)
--   Ctrl+Shift+F3  L2  write the Liberator's membership list (press twice within 6 s)
--   Ctrl+Shift+F4  L4  restore: list, then row, then record (press twice within 6 s)
-- Every step refuses unless: zero live Liberators (equip another primary, do not open the armory), solo, every pin
-- and every before byte as reviewed; L2 also needs the Trident's package resident (requested below at load).
-- RESTART THE GAME after using L2.
local mod=hd2.mod()
local BUILD='0.1.0'
mod:log('LiberatorBeamProof '..BUILD..' EXPERIMENTAL BUILD: SOLO ONLY. Ctrl+Shift+F1 status (L0), Ctrl+Shift+F2 '
    ..'L1 (record + row), Ctrl+Shift+F3 L2 (the list swap), Ctrl+Shift+F4 restore (L4); write keys need two presses '
    ..'within 6 s. Zero live Liberators for every write and the restore: equip another primary and do not open the '
    ..'armory. RESTART THE GAME after using it.')

local ok,X=pcall(require,'hd2runtime/runtime/experiment_liberator_beam')
if not ok then
    mod:log('UNAVAILABLE: this HD2Runtime build has no Liberator beam experiment (install the exp/liberator-beam '
        ..'runtime ZIP): '..tostring(X))
    return
end

-- The Trident's package (laser_shotgun), held for the session by the Runtime's reference-counted request.
local assets
local function want_assets()
    if assets and assets.status~='rejected'and assets.status~='cancelled'then return end
    assets=hd2.require_assets({id='liberator-beam-trident',targets={hd2.weapon('LAS-13 Trident')}})
end
want_assets()

local function report(what,result)
    if type(result)~='table'then mod:log(what..': no result');return end
    if result.ok then
        mod:log(('%s: OK, state %s, %s write%s'):format(what,tostring(result.state),tostring(result.writes or 0),
            result.writes==1 and''or's'))
    else
        mod:log(what..': REFUSED: '..tostring(result.reason))
    end
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

hd2.input.bind('liberator_beam_proof.status',{key='Ctrl+Shift+F1',on_press=function()
    want_assets()
    local s=X.status()
    if s.ok then
        mod:log(('L0 STATUS: state %s (%s); live Liberators %s; solo %s (%s); Trident package %s (asset request %s)%s')
            :format(tostring(s.state),tostring(s.detail),tostring(s.live_liberators),tostring(s.solo),
            tostring(s.solo_reason),tostring(s.assets),tostring(assets and assets.status),
            s.restart_required and'; RESTART THE GAME after this session'or''))
    else
        mod:log('L0 STATUS: REFUSED: '..tostring(s.reason))
    end
end})
hd2.input.bind('liberator_beam_proof.l1',{key='Ctrl+Shift+F2',on_press=function()
    confirm('l1','L1 (record 23 + row 21)',function()report('L1',X.apply('L1'))end)
end})
hd2.input.bind('liberator_beam_proof.l2',{key='Ctrl+Shift+F3',on_press=function()
    want_assets()
    confirm('l2','L2 (the Liberator list swap)',function()report('L2',X.apply('L2'))end)
end})
hd2.input.bind('liberator_beam_proof.restore',{key='Ctrl+Shift+F4',on_press=function()
    confirm('restore','L4 restore (list, row, record)',function()report('L4 restore',X.restore())end)
end})
mod:log('loaded ('..BUILD..' EXPERIMENTAL): Ctrl+Shift+F1 status, Ctrl+Shift+F2 L1, Ctrl+Shift+F3 L2, Ctrl+Shift+F4 '
    ..'restore')
