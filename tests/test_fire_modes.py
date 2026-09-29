import json
import sys
import unittest
from collections import Counter

from support import ROOT, run
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_fire_mode_authoring
import validate_packaged_runtime


class FireModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = json.loads((ROOT / 'research/weapon-fire-modes-F5FEE03DCFDB.json').read_text())
        cls.catalog = json.loads((ROOT / 'sdk/WeaponFireModeCapabilities.json').read_text())
        cls.rows = {(row['kind'], row['weapon']): row for row in cls.research['weapons']}
        cls.weapons = {(row['kind'], row['weapon']): row for row in cls.catalog['weapons']}

    def test_native_model(self):
        self.assertEqual(self.research['layout'], {'140': 'num_burst_rounds', '144': 'primary', '148': 'secondary',
            '152': 'tertiary', '156': 'quaternary', '184': 'function_info'})
        fire = self.research['fireMode']
        self.assertEqual([fire[str(v)] for v in range(4)], ['None', 'Automatic', 'Single', 'Burst'])
        self.assertEqual(self.research['weaponFunction']['3'], 'Firemode')
        self.assertFalse(generate_fire_mode_authoring.generate(check=True))

    def test_jar5_has_single_and_burst_and_a_selector(self):
        jar = self.rows[('player', 'JAR-5 Dominator')]
        self.assertEqual((jar['slots'], jar['modes'], jar['burstRounds']), ([2, 3, 0, 0], ['single', 'burst'], 3))
        self.assertEqual((jar['state'], jar['selector']['right'], jar['maxModes']), ('selectable', 'Firemode', 4))
        self.assertNotIn('automatic', jar['modes'])  # full-auto does not exist natively; it is added

    def test_coverage_and_blockers(self):
        states = Counter((row['kind'], row['state']) for row in self.catalog['weapons'])
        self.assertEqual(states[('player', 'selectable')], 30)
        self.assertEqual(states[('player', 'single_mode')], 19)
        self.assertEqual(states[('support', 'selectable')], 3)
        self.assertEqual(states[('support', 'single_mode')], 10)
        self.assertEqual(self.catalog['summary']['writable'], 62)
        blocked = {('player', 'PLAS-15 Loyalist'): 'charge or safety', ('support', 'RS-422 Railgun'): 'charge or safety',
            ('support', 'M-1000 Maxigun'): 'conventional projectile', ('player', 'P-92 Warrant'): 'ProgrammableAmmo',
            ('player', 'AR-11 Arbitrator'): 'special fire-control', ('player', 'SG-8 Punisher'): 'weapon-function'}
        for key, needle in blocked.items():
            row = self.weapons[key]
            self.assertFalse(row['writable'], key)
            self.assertIn(needle, row['reason'], key)
        for row in self.catalog['weapons']:
            if row['writable']:
                self.assertTrue(set(row['modes']) <= {'automatic', 'single', 'burst'}, row['weapon'])
                self.assertEqual(row['defaultMode'], row['modes'][0])
                self.assertIn(row['maxModes'], (1, 4))

    def test_lua_guards_and_api(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local b=require('hd2runtime/core/bytes')
local F=hd2.fields.fire_mode
local jar=hd2.weapon('JAR-5 Dominator')
local set=jar:fire_modes().modeSet
assert(set.state=='selectable'and set.defaultMode=='single'and set.maxModes==4 and set.writable)
local spec=patches.validate({id='j',target=jar,field=F.modes,expect={'single','burst'},
 value={'single','burst','automatic'},allow_unverified_effect=true})
assert(b.hex(spec.changes[1].desired)=='02000000030000000100000000000000')
assert(not pcall(patches.validate,{id='j',target=jar,field=F.modes,expect={'single','burst'},
 value={'single','burst','automatic'}}))
assert(not pcall(patches.validate,{id='j',target=jar,field=F.modes,expect={'single','burst'},
 value={'single','single'},allow_unverified_effect=true}))
local amr=hd2.support_weapon('APW-1 Anti-Materiel Rifle')
assert(amr:fire_modes().modeSet.maxModes==1)
patches.validate({id='a',target=amr,field=F.modes,expect={'single'},value={'automatic'},allow_unverified_effect=true})
assert(not pcall(patches.validate,{id='a',target=amr,field=F.modes,expect={'single'},value={'single','automatic'},
 allow_unverified_effect=true}))
local railgun=hd2.support_weapon('RS-422 Railgun')
assert(not railgun:fire_modes().modeSet.writable)
assert(not pcall(patches.validate,{id='r',target=railgun,field=F.modes,expect={'single'},value={'automatic'},
 allow_unverified_effect=true}))
assert(not pcall(patches.validate,{id='jb',target=jar,field=F.burst_rounds,expect=3,value=11,allow_unverified_effect=true}))
return 'ok'
'''), b'ok')

    def test_validation_and_scenarios(self):
        result = json.loads((ROOT / 'validation/fire-mode-authoring-snapshot.json').read_text())
        self.assertEqual(result['status'], 'VALIDATED')
        # 62 writable fire-mode sets since the EAT-17 was delivery-resolved.
        self.assertEqual((result['modeSetChecks'], result['burstChecks']), (62, 62))
        for key in ('changedWrites', 'rollbacks', 'conflictRejections', 'acknowledgementRejections'):
            self.assertEqual(result[key], 124, key)
        self.assertEqual(result['jar5'], {'after': '01000000', 'before': '00000000', 'bytesWritten': 4,
            'changedSlot': 'tertiary_fire_mode (+152)', 'fieldOffset': 152, 'owner': 'WeaponDataComponentData',
            'record': 290, 'uniqueOwner': True})
        self.assertEqual(result['blockedRejections'], 5)
        self.assertTrue(result['overlapRejected'])
        for name in ('fire-mode-jar5-full-auto', 'fire-mode-burst-and-automatic'):
            self.assertIn(name, validate_packaged_runtime.SCENARIOS)
        addon = (ROOT / 'examples/projects/JAR5FullAuto/src/addon.lua').read_text()
        self.assertIn("value={'single','burst','automatic'}", addon)


if __name__ == '__main__':
    unittest.main()
