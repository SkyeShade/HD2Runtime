"""Enemy spawn weights (runtime/enemy_spawn_weights.lua, api/enemy_spawns.lua, docs/enemy-spawns.md).

Pins the research (each faction's static roster in game.dll, PickEnemy's weighted pick by the difficulty's weight, the
mission package selection that reads the same weight sign, the 14 pick sites, no store into a roster), the generated
domain, the API's refusals and offline listing, the weight arithmetic, and the snapshot validation."""
import json
import unittest

from support import ROOT, run

import build_profile

RESEARCH = ROOT / 'research/enemy-spawn-weights-F5FEE03DCFDB.json'
VALIDATION = ROOT / 'validation/enemy-spawn-weights-snapshot.json'
MISSION = build_profile.snapshot_directory() / 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap'
SNAPSHOTS = all((build_profile.snapshot_directory() / name).is_file() for name in (
    'F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap', MISSION.name,
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap'))

PRELUDE = r'''
local api=require('hd2runtime/api/enemy_spawns')
local weights=require('hd2runtime/runtime/enemy_spawn_weights')
local D=require('hd2runtime/domains/enemy_spawn_weights')
local b=require('hd2runtime/core/bytes')
weights.reset_for_tests()
local ACK={allow_unverified_effect=true,owner='mods/a'}
local function refused(handle,code)
    assert(handle.status=='refused',tostring(handle.status))
    assert(handle.code==code,tostring(handle.code)..': '..tostring(handle.reason))
end
'''


class EnemySpawnWeightTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body + "\nreturn 'ok'"), b'ok')

    def test_the_research(self):
        research = json.loads(RESEARCH.read_text(encoding='utf-8'))
        self.assertEqual((research['writes'], research['protectionChanges']), (0, 0))
        self.assertEqual({f['name']: (f['rows'], f['count']) for f in research['factions']},
            {'terminids': (0x32B6BA0, 45), 'illuminate': (0x32B8220, 46), 'automatons': (0x32B9920, 61)})
        self.assertEqual(research['row']['weights'], 0x30)
        self.assertEqual(research['row']['difficulties'], 10)
        pins = {pin['rva']: pin['asm'] for group in research['proofs'].values() for pin in group}
        self.assertEqual(pins[0x95321B], 'movss xmm0, dword ptr [rdi + rax*4 + 0x30]')
        self.assertEqual(pins[0x953212], 'mov eax, dword ptr [r13 + 0x518c4]')
        self.assertEqual(pins[0x9532BD], 'subss xmm0, dword ptr [rdx + rax*4 + 0x30]')
        self.assertEqual(pins[0x94D3FB], 'mov qword ptr [r11 + 0x660], rax')
        census = research['census']
        self.assertEqual(len(census['pickCallers']), 14)
        self.assertEqual(census['ripStores'], [])
        roles = {item['rva']: item['role'] for item in census['weightReaders']}
        self.assertIn('package selection', roles[0xABD6AC])
        # The Charger: one Terminid row, weight 1 up to difficulty 6, then shrinking, 0 at 10.
        charger = [e for f in research['factions'] for e in f['entries'] if e['name'] == 'Charger']
        self.assertEqual(len(charger), 1)
        self.assertEqual(charger[0]['weights'][:6], [1.0] * 6)
        self.assertEqual(charger[0]['weights'][9], 0.0)
        self.assertEqual([m['difficulty'] for m in research['missionObservations']], [0, 10, 10, 10, 10])

    @unittest.skipUnless(SNAPSHOTS, 'retained snapshots absent')
    def test_outputs_are_current(self):
        import research_enemy_spawn_weights
        research_enemy_spawn_weights.main(['--check'])
        import generate_enemy_spawn_weights
        self.assertEqual(generate_enemy_spawn_weights.generate(check=True), [])

    def test_refusals_and_listing(self):
        self.lua(r'''
refused(api.spawn_weight('Charger',2,{owner='mods/a'}),'ACKNOWLEDGEMENT_REQUIRED')
refused(api.spawn_weight('No Such Bug',2,ACK),'UNKNOWN_ENEMY')
refused(api.spawn_weight(12,2,ACK),'UNKNOWN_ENEMY')
refused(api.spawn_weight('Charger',-1,ACK),'INVALID_MULTIPLIER')
refused(api.spawn_weight('Charger',11,ACK),'INVALID_MULTIPLIER')
refused(api.spawn_weight('Charger',0/0,ACK),'INVALID_MULTIPLIER')
refused(api.spawn_weight('Charger',2,{allow_unverified_effect=true,owner='mods/a',difficulties={11}}),'INVALID_OPTION')
refused(api.spawn_weight('Charger',2,{allow_unverified_effect=true,owner='mods/a',speed=1}),'INVALID_OPTION')
assert(next(weights.configs())==nil,'a refusal configured something')
local all=api.spawn_list()
assert(#all==45+46+61,#all)
local bugs=api.spawn_list({faction='terminids'})
assert(#bugs==45)
local charger=api.spawn_list({enemy='charger'})
assert(#charger==1 and charger[1].enemy=='Charger'and charger[1].faction=='terminids',#charger)
assert(charger[1].weights[1]==1 and charger[1].weights[10]==0)
-- A name, a native name, a catalogue id and the entity type name the same rows.
assert(#api.spawn_list({enemy=charger[1].entity})==1 and#api.spawn_list({enemy='0x'..charger[1].entity})==1)
local hd2=require('hd2runtime/api/hd2')
assert(hd2.enemies.spawn_weight==api.spawn_weight and hd2.enemies.spawn_list==api.spawn_list)
-- hd2.enemies stays callable: the reviewed enemy / structure names as before.
assert(#hd2.enemies({kind='structure'})==39 and #hd2.enemies()>39)
''')

    def test_the_weights_a_multiplier_writes(self):
        self.lua(r'''
-- Offline there is no game world: the configuration waits, and its desired bytes are computed exactly.
local h=api.spawn_weight('Charger',2,ACK)
assert(h.status=='pending'or h.status=='unavailable',h.status)
local config=h.configs[1]
local row=config.rows[1]
for d=1,10 do
    local v=b.value(row.vanilla,(d-1)*4,'f32')
    assert(b.value(config.desired[row],(d-1)*4,'f32')==v*2,d)
end
refused(api.spawn_weight('Charger',3,{allow_unverified_effect=true,owner='mods/b'}),'ALREADY_SET')
-- The same mod replaces its own.
local only=api.spawn_weight('Charger',3,{allow_unverified_effect=true,owner='mods/a',difficulties={7,8}})
local c2=only.configs[1]
for d=1,10 do
    local v=b.value(row.vanilla,(d-1)*4,'f32')
    local want=(d==7 or d==8)and v*3 or v
    assert(math.abs(b.value(c2.desired[row],(d-1)*4,'f32')-want)<1e-6,d)
end
only:stop()
assert(next(weights.configs())==nil,'stopping a never-applied configuration leaves nothing')
local zero=api.spawn_weight('Bile Titan',0,ACK)
for d=1,10 do assert(b.value(zero.configs[1].desired[zero.configs[1].rows[1]],(d-1)*4,'f32')==0)end
zero:stop()
''')

    @unittest.skipUnless(MISSION.is_file(), 'retained mission snapshot absent')
    def test_the_snapshot_validation(self):
        import validate_enemy_spawn_weights_snapshot as validation
        result = validation.validate(MISSION)
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertTrue(all(check['ok'] for check in result['checks']))
        self.assertEqual(len(result['checks']), 20)
        self.assertEqual(result['protectionChanges'], 0)
        shares = {s['difficulty']: (round(s['before'], 4), round(s['after'], 4)) for s in result['chargerShares']}
        self.assertEqual(shares[7], (0.5, 0.6667))
        self.assertEqual(shares[1], (1.0, 1.0))
        self.assertEqual(shares[10], (0.0, 0.0))
        recorded = json.loads(VALIDATION.read_text(encoding='utf-8'))
        self.assertEqual({k: v for k, v in recorded.items() if k != 'log'},
            {k: v for k, v in json.loads(json.dumps(result, sort_keys=True)).items() if k != 'log'})


if __name__ == '__main__':
    unittest.main()
