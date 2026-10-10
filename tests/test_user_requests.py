"""0.30.4 user requests (proof/UserRequestsProof):

1. Charges before cooldown (research/stratagem-rearm-pool): StratagemInfo +200 names the rearm that refills a
   stratagem's uses; every reader compares it with 49 (Eagle Rearm). hd2.fields.stratagem.rearm_pool ('none' /
   'eagle_rearm') on every catalogued non-Eagle stratagem, read-only on the Eagles; a pool member keeps a finite use
   count (REARM_POOL_UNLIMITED).
2. Orbital targeting (research/orbital-targeting): the Railcannon's own OrbitalAbility record - search radius, tracking
   speed, beam duration, shot delay - on hd2.stratagem('Orbital Railcannon Strike'); the Laser's re-search interval on its
   beam attack. Ranges, allow_unverified_effect, the shot-type record proof.
3. The fire-mode selector (research/fire-mode-selector): it cycles three slots at most; a one-mode weapon with a free
   input ('addable', the R/40-K Hot-Shot) takes weapon_function.<input> = 'fire_mode' in the same transaction as its
   extra modes (SELECTOR_REQUIRED otherwise).
The snapshot tests write on a copy-on-write overlay of the retained snapshot."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from support import run
from test_multi_mod_composition import build_profile, snapshot_run

ROOT = Path(__file__).resolve().parents[1]
REARM = json.loads((ROOT / 'research/stratagem-rearm-pool-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
TARGETING = json.loads((ROOT / 'research/orbital-targeting-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
SELECTOR = json.loads((ROOT / 'research/fire-mode-selector-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
PROOF = ROOT / 'proof/UserRequestsProof'


class ResearchTests(unittest.TestCase):
    def test_rearm_pool_is_the_eagles_and_every_reader_compares_with_49(self):
        self.assertEqual({c['constant'] for c in REARM['rearmPoolComparisons']}, {49})
        self.assertEqual(len(REARM['rearmPoolComparisons']), 6)
        members = {m['nativeTypeName'] for m in REARM['pool']['members']}
        self.assertEqual(len(members), 10)
        self.assertTrue(all(name.startswith('Eagle') for name in members))
        self.assertEqual(REARM['pool']['rearm']['cooldown'], 150)
        self.assertIn('All at once', REARM['model']['recharge'])
        roles = [p['role'] for p in REARM['proofs']['callCooldown']]
        self.assertIn('... and refills its uses (all at once)', roles)
        self.assertTrue(REARM['rows']['unmoddedIdentical'])
        layout = {m['offset']: m for m in REARM['layout']}
        self.assertEqual((layout[200]['type'], layout[200]['hiddenNameLength']), ('StratagemType', 20))

    def test_orbital_targeting_records_and_fields(self):
        records = {r['stratagem']: r for r in TARGETING['records'] if r['stratagem']}
        rail, laser = records['Orbital Railcannon Strike'], records['Orbital Laser']
        self.assertEqual((rail['values']['472'], rail['values']['468'], rail['values']['460'], rail['values']['540']),
            (30.0, 90.0, 2.0, 1.7))
        self.assertEqual((rail['values']['520'], rail['values']['532'], rail['values']['544']), (1, 277, 0.0))
        self.assertEqual((laser['values']['472'], laser['values']['544'], laser['values']['520']), (50.0, 1.0, 0))
        fields = {(f['stratagem'], f['field']): f for f in TARGETING['fields']}
        self.assertEqual(set(fields), {('Orbital Railcannon Strike', 'orbital.search_radius'),
            ('Orbital Railcannon Strike', 'orbital.movement_speed'), ('Orbital Railcannon Strike', 'orbital.duration'),
            ('Orbital Railcannon Strike', 'orbital.fire_delay'), ('Orbital Laser', 'orbital.retarget_interval')})
        # The shot always comes before the strike ends: max fire_delay < min duration + the 1 s tail (+464).
        delay = fields[('Orbital Railcannon Strike', 'orbital.fire_delay')]['max']
        duration = fields[('Orbital Railcannon Strike', 'orbital.duration')]['min']
        self.assertLess(delay, duration + rail['values']['464'])
        self.assertTrue(TARGETING['checks']['snapshotsIdenticalToPinned'])

    def test_fire_mode_selector_reaches_three_slots(self):
        roles = ' '.join(p['role'] for p in SELECTOR['proofs']['fireModeCycle'])
        self.assertIn('+156 is not read', roles)
        self.assertEqual(SELECTOR['pressJumpTable']['targets']['3'], '0x75542B')
        self.assertEqual(SELECTOR['summary'], {'selectable': 34, 'addable': 30, 'single_mode': 0})
        hot = next(w for w in SELECTOR['weapons'] if w['weapon'] == 'R/40-K Hot-Shot Marksman Rifle')
        self.assertEqual((hot['state'], hot['maxModes'], hot['bindableInputs']), ('addable', 3, ['left', 'right']))

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained snapshot (game.dll image) not available')
    def test_research_outputs_are_current(self):
        for script in ('research_stratagem_rearm_pool.py', 'research_orbital_targeting.py',
                'research_fire_mode_selector.py'):
            result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), '--check'], cwd=ROOT,
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, script + ': ' + result.stdout + result.stderr)


class CatalogueTests(unittest.TestCase):
    def test_descriptors(self):
        self.assertEqual(run(r'''
local function field(fields,id,attack)
    for _,f in ipairs(fields)do if f.semanticFieldId==id and (f.target or{}).attack==attack then return f end end
end
local S=require('hd2runtime/domains/stratagem_authoring').stratagems
-- 1. The rearm pool: writable on every non-Eagle, read-only on the Eagles.
local writable,eagles=0,0
for name,entry in pairs(S)do
    local f=assert(field(entry.fields,'stratagem.rearm_pool'),name)
    assert(f.backing.offset==200 and f.backing.kind=='StratagemDefinition' and f.type=='enum',name)
    if f.currentDefault==49 then
        eagles=eagles+1;assert(not f.editable and name:find('^Eagle'),name)
    else
        writable=writable+1
        assert(f.editable and f.currentDefault==0 and f.acknowledgement=='allow_unverified_effect',name)
        assert(f.allowedValues[1].name=='none'and f.allowedValues[2].value==49 and f.allowedValues[2].name=='eagle_rearm')
        assert(f.rule:find('finite',1,true),name)
    end
end
assert(writable==86 and eagles==8,writable..' '..eagles)
-- 2. The Railcannon's targeting on the stratagem; the Laser's re-search interval on its beam.
local rail=S['Orbital Railcannon Strike']
for id,want in pairs({['orbital.search_radius']={472,30,1,300},['orbital.movement_speed']={468,90,1,1000},
        ['orbital.duration']={460,2,1.5,10},['orbital.fire_delay']={540,1.7,0,2.4}})do
    local f=assert(field(rail.fields,id),id)
    assert(f.target.path=='stratagem'and f.backing.component=='OrbitalAbilityComponentData',id)
    assert(f.backing.offset==want[1]and math.abs(f.currentDefault-want[2])<1e-6 and f.min==want[3]and f.max==want[4],id)
    assert(f.acknowledgement=='allow_unverified_effect'and f.backing.recordProofs[1].offset==532
        and f.backing.recordProofs[1].value==277,id)
end
assert(not field(rail.fields,'orbital.retarget_interval'),'the Railcannon keeps its first target')
local laser=S['Orbital Laser']
local retarget=assert(field(laser.fields,'orbital.retarget_interval','beam'))
assert(retarget.backing.offset==544 and retarget.currentDefault==1 and retarget.min==0.1 and retarget.max==60)
assert(field(laser.fields,'orbital.search_radius','beam').currentDefault==50)
-- 3. The Hot-Shot: addable, three modes at most, the fire_mode binding on both free inputs.
local W=require('hd2runtime/domains/player_weapon_authoring').weapons['R/40-K Hot-Shot Marksman Rifle'].fields
local modes=assert(field(W,'fire_mode.modes'))
assert(modes.fireModeState=='addable'and modes.maxModes==3 and modes.bindableInputs[1]=='left'and not modes.selectorBound)
for _,side in ipairs({'left','right'})do
    local input=assert(field(W,'weapon_function.'..side))
    local ok=false;for _,v in ipairs(input.allowedValues)do ok=ok or v=='fire_mode'end
    assert(ok and input.functionValues.fire_mode==3,side)
end
local J=require('hd2runtime/domains/player_weapon_authoring').weapons['JAR-5 Dominator'].fields
assert(field(J,'fire_mode.modes').maxModes==3)
local mg=require('hd2runtime/domains/support_weapon_authoring').weapons['MG-43 Machine Gun'].fields
assert(not field(mg,'weapon_function.right'),'its right input keeps the rate-of-fire selector (not offered)')
local left=assert(field(mg,'weapon_function.left'));local fm=false
for _,v in ipairs(left.allowedValues)do fm=fm or v=='fire_mode'end
assert(fm,'the MG-43 takes the fire-mode selector on its free left input')
return 'ok'
'''), b'ok')

    def test_validation_refusals(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local strat=require('hd2runtime/domains/stratagem_writes')
local transactions=require('hd2runtime/domains/transactions')
local F=hd2.fields
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
local laser=hd2.stratagem('Orbital Laser')
local rail=hd2.stratagem('Orbital Railcannon Strike')
-- names and numbers are the same values
local a=strat.validate_patch{id='a',target=laser,allow_unverified_effect=true,field=F.stratagem.rearm_pool,
    expect='none',value='eagle_rearm'}
local c=strat.validate_patch{id='c',target=laser,allow_unverified_effect=true,field=F.stratagem.rearm_pool,expect=0,value=49}
assert(a.changes[1].desired==c.changes[1].desired)
rejects(function()strat.validate_patch{id='n',target=laser,field=F.stratagem.rearm_pool,expect=0,value=49}end,
    'allow_unverified_effect')
rejects(function()strat.validate_patch{id='v',target=laser,allow_unverified_effect=true,field=F.stratagem.rearm_pool,
    expect=0,value=30}end,'not one of the reviewed values')
rejects(function()strat.validate_patch{id='w',target=laser,allow_unverified_effect=true,field=F.stratagem.rearm_pool,
    expect='none',value='orbital_pool'}end,'unknown value name')
rejects(function()strat.validate_patch{id='e',target=hd2.stratagem('Eagle Airstrike'),allow_unverified_effect=true,
    field=F.stratagem.rearm_pool,expect=49,value=0}end,'read-only')
-- the Railcannon's ranges and acknowledgement
for _,case in ipairs({{F.orbital.search_radius,30,0.5},{F.orbital.search_radius,30,301},{F.orbital.movement_speed,90,0},
        {F.orbital.duration,2,1},{F.orbital.duration,2,11},{F.orbital.fire_delay,1.7,2.5},{F.orbital.fire_delay,1.7,-1}})do
    rejects(function()strat.validate_patch{id='r',target=rail,allow_unverified_effect=true,field=case[1],
        expect=case[2],value=case[3]}end,'reviewed range')
end
rejects(function()strat.validate_patch{id='k',target=rail,field=F.orbital.search_radius,expect=30,value=200}end,
    'allow_unverified_effect')
rejects(function()strat.validate_patch{id='x',target=rail,allow_unverified_effect=true,field=F.orbital.retarget_interval,
    expect=0,value=1}end,'not exposed')
-- the Hot-Shot: the modes and the binding together, never alone, never four modes
local hot=hd2.weapon('R/40-K Hot-Shot Marksman Rifle')
local both=transactions.validate{id='h',target=hot,allow_unverified_effect=true,changes={
    {field=F.fire_mode.modes,expect={'single'},value={'single','automatic'}},
    {field=F.weapon_function.left,expect='none',value='fire_mode'}}}
assert(#both.changes==2)
rejects(function()transactions.validate{id='h1',target=hot,allow_unverified_effect=true,changes={
    {field=F.fire_mode.modes,expect={'single'},value={'single','automatic'}}}}end,'SELECTOR_REQUIRED')
rejects(function()transactions.validate{id='h2',target=hot,allow_unverified_effect=true,changes={
    {field=F.weapon_function.right,expect='none',value='fire_mode'}}}end,'SELECTOR_REQUIRED')
rejects(function()transactions.validate{id='h3',target=hot,allow_unverified_effect=true,changes={
    {field=F.fire_mode.modes,expect={'single'},value={'single','automatic','burst','single'}},
    {field=F.weapon_function.left,expect='none',value='fire_mode'}}}end,'allows 3')
-- the one mode alone is still replaced without a selector
transactions.validate{id='h4',target=hot,allow_unverified_effect=true,changes={
    {field=F.fire_mode.modes,expect={'single'},value={'automatic'}}}}
local set=hot:fire_modes().modeSet
assert(set.state=='addable'and set.maxModes==3 and set.binding.value=='fire_mode'and set.bindableInputs[2]=='right')
return 'ok'
'''), b'ok')

    def test_proof_toggles(self):
        source = (PROOF / 'src/addon.lua').read_text(encoding='utf-8')
        readme = (PROOF / 'README.md').read_text(encoding='utf-8')
        self.assertEqual((PROOF / 'VERSION').read_text().strip(), '0.1.0')
        for toggle in ('laser_charges', 'railcannon_charges', 'railcannon_radius', 'railcannon_radius_small',
                'railcannon_tracking', 'railcannon_slow_tracking', 'railcannon_quick_shot', 'railcannon_long_beam',
                'laser_retarget', 'laser_no_retarget', 'hotshot_single_auto', 'hotshot_three', 'mg43_single'):
            self.assertIn("id='" + toggle + "'", source)
        for label in ('Railcannon search radius 200 m', 'Railcannon tracking x5', 'Orbital Laser 5 charges',
                'Hot-Shot single/auto selector'):
            self.assertIn(label, source)
            self.assertIn(label, readme)
        self.assertIn('allow_unverified_effect=true', source)


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class SnapshotTests(unittest.TestCase):
    def test_every_proof_write_applies(self):
        result = snapshot_run(r'''
update=update or function()end
local F=hd2.fields
local laser=hd2.stratagem('Orbital Laser')
local rail=hd2.stratagem('Orbital Railcannon Strike')
local ops={
    {id='laser_charges',target=laser,writes=3,changes={{field=F.stratagem.max_uses,expect=3,value=5},
        {field=F.stratagem.definition_cooldown,expect=300,value=15},
        {field=F.stratagem.rearm_pool,expect='none',value='eagle_rearm'}}},
    {id='railcannon_charges',target=rail,writes=3,changes={{field=F.stratagem.max_uses,expect='unlimited',value=3},
        {field=F.stratagem.definition_cooldown,expect=180,value=15},
        {field=F.stratagem.rearm_pool,expect='none',value='eagle_rearm'}}},
    {id='railcannon_targeting',target=rail,writes=4,changes={{field=F.orbital.search_radius,expect=30,value=200},
        {field=F.orbital.movement_speed,expect=90,value=450},{field=F.orbital.fire_delay,expect=1.7,value=0.5},
        {field=F.orbital.duration,expect=2,value=8}}},
    {id='laser_retarget',target=laser:attack('beam'),writes=1,changes={
        {field=F.orbital.retarget_interval,expect=1,value=0.25}}},
    {id='hotshot',target=hd2.weapon('R/40-K Hot-Shot Marksman Rifle'),writes=2,changes={
        {field=F.fire_mode.modes,expect={'single'},value={'single','automatic'}},
        {field=F.weapon_function.left,expect='none',value='fire_mode'}}},
    {id='mg43',target=hd2.support_weapon('MG-43 Machine Gun'),writes=2,changes={
        {field=F.fire_mode.modes,expect={'automatic'},value={'automatic','single'}},
        {field=F.weapon_function.left,expect='none',value='fire_mode'}}},
}
local h={}
events.run_as('mods/test/user_requests',function()
    for _,op in ipairs(ops)do
        h[#h+1]=hd2.ensure({transaction={id='user-requests-'..op.id,target=op.target,allow_unverified_effect=true,
            changes=op.changes}})
    end
end)
settle(h)
local expected=0
for i,op in ipairs(ops)do
    check(h[i].runs>=1 and h[i].result and h[i].result.status=='APPLIED',op.id..' '..tostring(h[i].error))
    expected=expected+op.writes
end
-- The written bytes: the Railcannon radius, the rearm pool, the Hot-Shot's second slot and binding.
local r=resolve('transaction',{id='r',target=rail,allow_unverified_effect=true,changes={
    {field=F.orbital.search_radius,expect=30,value=200}}})
check(runtime.read(r[1].at,4)==b.encode(200,'f32'),'Railcannon radius written')
local p=resolve('transaction',{id='p',target=laser,allow_unverified_effect=true,changes={
    {field=F.stratagem.rearm_pool,expect=0,value=49}}})
check(runtime.read(p[1].at,4)==b.encode(49,'u32'),'Laser in the Eagle Rearm pool')
local n=0
for _ in pairs(overlay)do n=n+1 end
check(n==expected,'exactly the proof members written: '..n..' of '..expected)
return json.encode({ok=true,writes=n})
''')
        self.assertTrue(result['ok'])
        self.assertEqual(result['writes'], 15)

    def test_rearm_pool_refuses_unlimited_uses_and_the_railcannon_record_proof(self):
        result = snapshot_run(r'''
update=update or function()end
local F=hd2.fields
local rail=hd2.stratagem('Orbital Railcannon Strike')
local laser=hd2.stratagem('Orbital Laser')
-- An unlimited use count can never join the pool (the Railcannon is natively unlimited) ...
local ok,why=pcall(resolve,'patch',{id='u',target=rail,allow_unverified_effect=true,field=F.stratagem.rearm_pool,
    expect=0,value=49})
check(not ok and tostring(why):find('REARM_POOL_UNLIMITED',1,true),tostring(why))
ok,why=pcall(resolve,'transaction',{id='u2',target=laser,allow_unverified_effect=true,changes={
    {field=F.stratagem.max_uses,expect=3,value='unlimited'},{field=F.stratagem.rearm_pool,expect=0,value=49}}})
check(not ok and tostring(why):find('REARM_POOL_UNLIMITED',1,true),tostring(why))
-- ... and a pooled row never takes an unlimited count afterwards.
local h
events.run_as('mods/test/user_requests',function()
    h=hd2.ensure({transaction={id='pool',target=laser,allow_unverified_effect=true,changes={
        {field=F.stratagem.rearm_pool,expect=0,value=49}}}})
end)
settle({h})
check(h.result and h.result.status=='APPLIED',tostring(h.error))
ok,why=pcall(resolve,'patch',{id='u3',target=laser,allow_unverified_effect=true,field=F.stratagem.max_uses,expect=3,
    value='unlimited'})
check(not ok and tostring(why):find('REARM_POOL_UNLIMITED',1,true),tostring(why))
-- The Railcannon's record proof: another projectile type in +532 refuses its targeting writes.
local r=resolve('transaction',{id='r',target=rail,allow_unverified_effect=true,changes={
    {field=F.orbital.fire_delay,expect=1.7,value=0.5}}})
overlay[r[1].at-540+532]=b.encode(42,'u32')
ok,why=pcall(resolve,'transaction',{id='r2',target=rail,allow_unverified_effect=true,changes={
    {field=F.orbital.fire_delay,expect=1.7,value=0.5}}})
check(not ok and tostring(why):find('no longer the reviewed',1,true),tostring(why))
return json.encode({ok=true})
''')
        self.assertTrue(result['ok'])


if __name__ == '__main__':
    unittest.main()
