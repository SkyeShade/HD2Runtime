"""Attack-output composition: the native model, the family-aware catalog, the projectile-reference API with typed
attack_output handles, host eligibility and the Liberator test mod."""
import json
import re
import unittest

from support import ROOT, run


class NativeModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = json.loads((ROOT / 'research/attack-outputs-F5FEE03DCFDB.json').read_text())

    def test_no_common_output_reference(self):
        model = self.research['model']
        self.assertFalse(model['commonOutputAbstraction'])
        refs = self.research['typeReferences']
        # A BeamType is referenced only inside the beam system; nothing a projectile or explosion does reaches it.
        self.assertEqual({r['type'] for r in refs['BeamType']}, {'BeamInfo', 'BeamPrisms', 'BeamWeaponComponent'})
        # An explosion can release an arc (+120); otherwise only the arc system references ArcType.
        self.assertEqual({(r['type'], r['offset']) for r in refs['ArcType']},
            {('ArcInfo', 0), ('ArcWeaponComponent', 0), ('ExplosionInfo', 120)})
        self.assertIn({'type': 'ProjectileWeaponComponent', 'offset': 0, 'array': None}, refs['ProjectileType'])

    def test_liberator_cases(self):
        cases = self.research['liberatorCases']
        self.assertEqual({name: case['status'] for name, case in cases.items()}, {'LAS Beam': 'BLOCKED',
            'Trident': 'BLOCKED', 'EAT-700 Napalm': 'SUPPORTED', 'ARC-3 Arc': 'BLOCKED', 'Arc on impact': 'SUPPORTED'})
        subjects = self.research['subjects']
        liberator = subjects['AR-23 Liberator']
        self.assertTrue(liberator['projectileHost'])
        self.assertEqual((liberator['rpm'], liberator['magazinePatternEntries']), (640.0, 0))
        self.assertEqual(subjects['EAT-700 Expendable Napalm']['compatibilityClass'], 'explosive_shrapnel')
        self.assertEqual(subjects['GL-52 De-Escalator']['compatibilityClass'], 'explosive_arc')
        self.assertEqual(subjects['LAS-13 Trident']['beamFireMode'], 6)
        self.assertEqual(subjects['LAS-98 Laser Cannon']['beamFireMode'], 4)
        self.assertIn('WeaponHeatComponentData', subjects['LAS-98 Laser Cannon']['fireResource'])
        self.assertIn('WeaponChargeComponentData', subjects['ARC-3 Arc Thrower']['fireResource'])
        self.assertNotIn('WeaponChargeComponentData', subjects['ARC-12 Blitzer']['fireResource'])
        # The ARC-3 arc is released by no explosion; the De-Escalator's explosion releases its own arc.
        arcs = {e['explosion']: e for e in self.research['explosionArcs']}
        self.assertNotIn(subjects['ARC-3 Arc Thrower']['reference']['value'], {e['arc'] for e in arcs.values()})
        self.assertEqual(arcs[41]['consumers'], ['grenade_launcher_tactical'])


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/AttackOutputCapabilities.json').read_text())
        cls.outputs = {o['owner']['name']: o for o in cls.catalog['outputs']}

    def test_catalog(self):
        self.assertEqual(self.catalog['summary']['outputs'], 105)
        self.assertEqual(self.catalog['summary']['byFamily'], {'projectile': 89, 'beam': 3, 'arc': 2, 'spray': 4,
            'melee': 7})
        self.assertEqual(self.catalog['summary']['selectable'], 78)
        self.assertEqual(self.catalog['summary']['projectileHosts'], 58)
        self.assertNotRegex(json.dumps(self.catalog), r'0x[0-9A-Fa-f]{8}')
        for name in ('EAT-700 Expendable Napalm', 'GL-52 De-Escalator'):
            output = self.outputs[name]
            self.assertTrue(output['selectableAsProjectileReference'])
            self.assertEqual(output['requiredCoordinatedReferences'], [])
            self.assertTrue(output['package']['known'] and output['package']['autoLoad'])
            self.assertEqual(output['acknowledgements']['crossClass'],
                ['allow_unverified_reference', 'allow_unverified_effect'])
            self.assertIsNone(output['liveProof'])
        for name, kind in (('LAS-98 Laser Cannon', 'continuous_beam'), ('LAS-13 Trident', 'pulsed_multi_beam'),
                ('ARC-3 Arc Thrower', 'arc')):
            output = self.outputs[name]
            self.assertEqual(output['kind'], kind)
            self.assertFalse(output['selectableAsProjectileReference'])
            self.assertIn('projectile host references only ProjectileType', output['blockedReason'])
        self.assertEqual(self.outputs['GL-52 De-Escalator']['kind'], 'arc_on_impact')
        self.assertTrue(self.outputs['GL-52 De-Escalator']['chain']['arcOnImpact'])
        self.assertTrue(self.outputs['EAT-700 Expendable Napalm']['chain']['submunition'])


class ApiTests(unittest.TestCase):
    def test_output_swaps_guards_and_backward_compatibility(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local host=hd2.weapon('AR-23 Liberator'):attack('primary')
local eat=hd2.attack_output('EAT-700 Expendable Napalm')
assert(eat.resource=='attack_output' and eat:describe().family=='projectile')
assert(hd2.attack_output('output/v1/projectile/eat-700-expendable-napalm').output==eat.output)
assert(host:output():describe().compatibilityClass=='conventional_plain')
assert(#hd2.attack_outputs({family='beam'})==3 and #hd2.attack_outputs({selectable=true})==78)
local function swap(value,extra)
 local request={id='o',target=host,field=hd2.fields.attack.projectile,expect=host:projectile(),value=value,
  allow_unverified_reference=true,allow_unverified_effect=true}
 for k,v in pairs(extra or{})do if v==false then request[k]=nil else request[k]=v end end
 return patches.validate(request)
end
local spec=swap(eat)
assert(spec.changes[1].cross_class and #spec.asset_dependencies==1)
assert(spec.asset_dependencies[1].name:find('expendable_napalm_launcher',1,true))
swap(hd2.attack_output('GL-52 De-Escalator'))
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
rejects(function()swap(eat,{allow_unverified_reference=false})end,'allow_unverified_reference')
rejects(function()swap(eat,{allow_unverified_effect=false})end,'allow_unverified_effect')
for _,name in ipairs({'LAS-98 Laser Cannon','LAS-13 Trident','ARC-3 Arc Thrower'})do
 rejects(function()swap(hd2.attack_output(name))end,'INCOMPATIBLE_OUTPUT_FAMILY')
end
-- A weapon whose rounds are not all its projectile reference cannot host a cross-class output.
local evictor=hd2.weapon('GL-15 Evictor'):attack('primary')
rejects(function()patches.validate{id='x',target=evictor,field=hd2.fields.attack.projectile,
 expect=evictor:projectile(),value=eat,allow_unverified_reference=true,allow_unverified_effect=true}end,
 'CROSS_CLASS_HOST_REJECTED')
-- Vanilla (the host's own projectile) needs no acknowledgement.
patches.validate{id='v',target=host,field=hd2.fields.attack.projectile,expect=host:projectile(),value=host:projectile()}
-- The existing API is unchanged: same-class swaps between player weapons need no new acknowledgement,
-- cross-class swaps through player handles stay rejected, transactions accept the new option.
local reprimand=hd2.weapon('SMG-32 Reprimand'):attack('primary')
patches.validate{id='t',target=reprimand,field=hd2.fields.attack.projectile,expect=reprimand:projectile(),
 value=hd2.weapon('LAS-58 Talon'):attack('primary'):projectile()}
patches.validate{id='t2',target=reprimand,field=hd2.fields.attack.projectile,expect=reprimand:projectile(),
 value=hd2.attack_output('LAS-58 Talon')}
rejects(function()patches.validate{id='x',target=host,field=hd2.fields.attack.projectile,expect=host:projectile(),
 value=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile(),allow_unverified_reference=true,
 allow_unverified_effect=true}end,'incompatible projectile reference class')
transactions.validate{id='tx',target=host,allow_unverified_reference=true,allow_unverified_effect=true,changes={
 {field=hd2.fields.attack.projectile,expect=host:projectile(),value=eat}}}
return 'ok'
''')

    def test_choice_values_accept_reference_handles(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local host=hd2.weapon('AR-23 Liberator'):attack('primary')
local page=hd2.options({id='attack_output_probe',title='Attack Output Probe'})
local choice=page:choice({id='output',label='Output',choices={'Vanilla','EAT-700'},
 values={host:projectile(),hd2.attack_output('EAT-700 Expendable Napalm')}})
assert(choice:get().resource=='player_weapon' and choice:samples()[2].resource=='attack_output')
local ok,why=pcall(function()page:choice({id='bad',label='Bad',choices={'A','B'},values={{},{}}})end)
assert(not ok and tostring(why):find('semantic reference handles',1,true),tostring(why))
return 'ok'
''')


class ValidationTests(unittest.TestCase):
    def test_snapshot_validation_record(self):
        record = json.loads((ROOT / 'validation/attack-output-snapshot.json').read_text())
        self.assertEqual((record['status'], record['host'], record['baselineProjectile']),
            ('VALIDATED', 'AR-23 Liberator', 276))
        compositions = record['compositions']
        self.assertEqual({k: (v['projectile'], v['crossClass']) for k, v in compositions.items()},
            {'EAT-700 Expendable Napalm': (259, True), 'GL-52 De-Escalator': (222, True),
             'LAS-58 Talon': (144, False)})
        self.assertTrue(compositions['EAT-700 Expendable Napalm']['package'].endswith('expendable_napalm_launcher'))
        rejections = record['rejections']
        for name in ('LAS-98 Laser Cannon', 'LAS-13 Trident', 'ARC-3 Arc Thrower'):
            self.assertEqual(rejections[name], 'INCOMPATIBLE_OUTPUT_FAMILY')
        self.assertEqual((rejections['acknowledgements'], rejections['staleSource'], rejections['hostMagazinePattern']),
            (2, 1, 1))

    def test_packaged_scenario_covers_every_transition(self):
        import validate_packaged_runtime as packaged
        extra = packaged.EXTRAS['example-liberator-attack-output-test']
        self.assertEqual(extra['packageRequests'], 2)
        steps = re.findall(r"choose\((\d),'([^']+)',(\d)\)", extra['after'])
        self.assertEqual([int(s[0]) for s in steps], [2, 3, 1, 3, 2])     # EAT, Arc, Vanilla, Arc, EAT
        self.assertIn('restores the exact baseline', extra['after'])

    def test_migration_normalizes_output_sources(self):
        from migration import source
        output = {'id': 'output/v1/projectile/x', 'family': 'projectile', 'owner': {'kind': 'support_weapon',
            'name': 'X'}, 'resource': '0x5', 'backing': {'kind': 'component', 'component': 'ProjectileWeaponComponentData',
            'offset': 0, 'storage': 'u32', 'width': 4, 'recordIndex': 3, 'indexRow': 4, 'ownerCount': 1},
            'currentDefault': 259, 'editable': True}
        [record] = source.normalize({'attack_outputs': {'outputs': {output['id']: output}}})
        self.assertEqual((record['domain'], record['key'], record['backing']['recordIndex'], record['baseline']),
            ('attack_outputs', 'output:output/v1/projectile/x', 3, 259))
        self.assertEqual(record['locator'], {'path': ['outputs', output['id']], 'guard': {'id': output['id']}})

    def test_test_mod(self):
        addon = (ROOT / 'examples/projects/LiberatorAttackOutputTest/src/addon.lua').read_text()
        self.assertIn("choices={'Vanilla','EAT-700 Napalm','GL-52 Arc (impact)'}", addon)
        self.assertIn('allow_unverified_reference=true', addon)
        self.assertIn('allow_unverified_effect=true', addon)
        self.assertNotRegex(addon, r"attack_output\('(LAS-98|LAS-13|ARC-3)")
        manifest = json.loads((ROOT / 'examples/projects/LiberatorAttackOutputTest/hd2runtime.json').read_text())
        self.assertIn('mod_options_menu', manifest['optional'])


if __name__ == '__main__':
    unittest.main()
