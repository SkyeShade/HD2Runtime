"""Shipped examples must teach the current typed API and pass Runtime validation."""
import importlib.util
import json
import re
import sys
import unittest

from support import ROOT

sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('validate_examples', ROOT / 'scripts/validate_examples.py')
examples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(examples)


class ExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.offline = examples.validate(offline=True)
        cls.names = {name for name, _ in examples.examples()}

    def test_every_example_validates_against_the_current_api(self):
        failures = {name: item['problems'] for name, item in self.offline['results'].items()
            if item['status'] != 'VALIDATED'}
        self.assertEqual(failures, {})
        self.assertEqual(set(self.offline['results']), self.names)
        self.assertIn('ModTemplate', self.names)

    def test_snapshot_validation_is_current(self):
        # Refresh with: py scripts/validate_examples.py (the release build runs it again).
        report = json.loads((ROOT / 'validation/example-projects.json').read_text())
        self.assertEqual(report['status'], 'VALIDATED')
        self.assertEqual(set(report['results']), self.names)
        for name, item in report['results'].items():
            self.assertEqual(item['minVersion'], self.offline['results'][name]['minVersion'], name)
            if item['operations']:
                self.assertGreater(item['baselineChanges'] or 0, 0, name)

    def test_beginner_damage_example_matches_the_sdk(self):
        catalog = json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())
        liberator = next(w for w in catalog['weapons'] if w['name'] == 'AR-23 Liberator')
        baseline = {f['apiFieldConstant']: f['currentDefault'] for f in liberator['fields']}
        source = (ROOT / 'examples/projects/LiberatorDamageTransaction/src/addon.lua').read_text()
        self.assertIn("hd2.weapon('AR-23 Liberator'):attack('primary'):projectile()", source)
        self.assertIn('transaction=', source)
        self.assertIn('allow_shared=true', source)
        changes = re.findall(r'field=(hd2\.fields\.[\w.]+),expect=(\d+)', source)
        self.assertEqual({field for field, _ in changes}, {'hd2.fields.damage.player_standard_damage',
            'hd2.fields.damage.player_durable_damage', 'hd2.fields.damage.ap_direct', 'hd2.fields.damage.ap_slight',
            'hd2.fields.damage.ap_large', 'hd2.fields.damage.ap_extreme'})
        for field, expect in changes:
            self.assertEqual(int(expect), baseline[field], field)

    def test_every_example_project_runs_from_the_built_zip(self):
        packaged = importlib.util.spec_from_file_location('validate_packaged_runtime',
            ROOT / 'scripts/validate_packaged_runtime.py')
        module = importlib.util.module_from_spec(packaged)
        packaged.loader.exec_module(module)
        sources = {scenario: builder() for scenario, builder in module.SCENARIOS.items()}
        texts = set(sources.values())
        for project in (ROOT / 'examples/projects').iterdir():
            if (project / 'src/addon.lua').is_file():
                # Each scenario runs the addon exactly as its built ZIP ships it: inside the SDK addon wrapper. A
                # harness scenario may load it as a mod source (RuntimeVersionWarningTest with three more mods).
                wrapped = module.example(project.name)
                self.assertTrue(wrapped in texts or any(module.lua(wrapped) in text for text in texts), project.name)
                self.assertIn((project / 'src/addon.lua').read_text(encoding='utf-8'), module.example(project.name))

    def test_template_teaches_a_typed_field(self):
        source = (ROOT / 'starter/src/addon.lua').read_text()
        self.assertIn('hd2.fields.weapon.fire_rate', source)
        self.assertNotRegex(source, r'armor_penetration|:projectile\(\):damage\(\)')


if __name__ == '__main__':
    unittest.main()
