"""The expendable family in the builder schema and the project format (docs/custom-stratagem-builder.md;
scripts/generate_custom_stratagem_schema.py, sdk/tools/custom_stratagem_project.py):
  * sdk/CustomStratagemSchema.json has the expendable family (weapon, presentation, modify without projectile, level)
    and the cloneDonors catalogue with the Runtime's own pool; the project schema accepts it;
  * a project with it is valid, compiles deterministically into a delivery = {family = 'expendable', ...} register call,
    and that compiled addon registers in the Runtime as an expendable definition with the same data;
  * the validator refuses what the Runtime refuses (another donor, an unknown level, a projectile, a presentation field
    it does not know, a missing presentation image)."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from support import ROOT, run, lua as lua_literal
from test_custom_stratagem_project import json_schema_errors, wrapped
from test_stratagem_calldown_code import WORLD

sys.path.insert(0, str(ROOT / 'sdk'))
from tools import custom_stratagem_project as P  # noqa: E402

PROJECT = {'format': 'hd2runtime-custom-stratagems/1', 'stratagems': [{
    'id': 'eat17g_clone', 'name': 'EAT-17G GAS EXPENDABLE ANTI-TANK', 'name_cased': 'EAT-17G Gas Expendable Anti-Tank',
    'description': 'Two expendable EAT-17G launchers.', 'icon': {'image': 'eat17g', 'source': 'images/eat17g.png'},
    'code': ['down', 'down', 'up', 'up', 'left', 'right'], 'cooldown': 70,
    'carrier': {'beacon': 'support', 'prefer_families': ['support', 'backpack']},
    'payload': {'family': 'expendable', 'weapon': 'EAT-17 Expendable Anti-Tank',
        'presentation': {'name': 'EAT-17G GAS EXPENDABLE ANTI-TANK', 'icon': 'eat17g'},
        'modify': {'impact_explosion': 'Orbital Gas Strike'}, 'level': 'model'}}]}


class ExpendableProjectTests(unittest.TestCase):
    def test_the_schema_has_the_family_and_its_catalogue(self):
        schema = P.load_schema()
        fam = next(f for f in schema['families'] if f['family'] == 'expendable')
        self.assertTrue(fam['builder'])
        self.assertEqual(fam['carrier'], {'beacon': ['support']})
        self.assertEqual(set(fam['fields']), {'weapon', 'presentation', 'modify', 'round', 'level'})
        self.assertNotIn('projectile', fam['fields']['modify']['fields'])
        self.assertEqual(fam['fields']['level']['values'], ['presentation', 'model', 'full'])
        clones = schema['catalogs']['cloneDonors']
        self.assertEqual([c['name'] for c in clones], ['EAT-17 Expendable Anti-Tank'])
        self.assertEqual([p['name'] for p in clones[0]['pool']], ['EAT-700 Expendable Napalm', 'EAT-411 Leveller'])
        self.assertEqual(clones[0]['projectile'], 132)
        self.assertTrue(any(u['field'] == 'expendable.modify.projectile' for u in schema['unsupported']))

    def test_a_project_validates_compiles_and_registers(self):
        schema = P.load_schema()
        project_schema = json.loads((ROOT / 'sdk/schemas/custom_stratagems.project.schema.json').read_text(
            encoding='utf-8'))
        self.assertEqual(P.validate(PROJECT, schema), [])
        self.assertEqual(json_schema_errors(PROJECT, project_schema), [])
        text = P.compile_lua(PROJECT)
        self.assertEqual(text, P.compile_lua(copy.deepcopy(PROJECT)))
        self.assertIn("delivery={family='expendable',weapon='EAT-17 Expendable Anti-Tank',presentation={name='EAT-17G GAS "
            "EXPENDABLE ANTI-TANK',icon='eat17g'},modify={impact_explosion='Orbital Gas Strike'},level='model'},", text)
        resource, addon = wrapped('EAT17GExample', text)
        self.assertEqual(run(WORLD + 'local ADDON=' + lua_literal(addon) + '\nlocal RESOURCE=' + lua_literal(resource) + r'''
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
assert(loadstring(ADDON,'@'..RESOURCE))()
local d=custom.get('eat17g_clone')
assert(d and d.kind=='expendable'and d.delivery.donor=='EAT-17 Expendable Anti-Tank'and custom.level_of(d)=='model')
assert(d.delivery.impact=='Orbital Gas Strike'and d.weapon_text~=nil and d.weapon_icon~=nil)
assert(require('hd2runtime/runtime/text_resources').text(d.weapon_text,'us')=='EAT-17G GAS EXPENDABLE ANTI-TANK')
return 'ok'
'''), b'ok')

    def test_the_validator_refuses_what_the_runtime_refuses(self):
        schema = P.load_schema()
        bad = copy.deepcopy(PROJECT)
        payload = bad['stratagems'][0]['payload']
        payload.update({'weapon': 'AC-8 Autocannon', 'level': 'half', 'modify': {'projectile': 'MG-43 Machine Gun'},
            'presentation': {'colour': 'red'}})
        problems = P.validate(bad, schema)
        for needle in ('payload.weapon: must be a support weapon with a reviewed expendable clone class',
                'payload.level: must be presentation, model, full', 'payload.modify: unsupported field projectile',
                'payload.presentation: unsupported field colour'):
            self.assertTrue(any(needle in p for p in problems), (needle, problems))
        red = copy.deepcopy(PROJECT)
        red['stratagems'][0]['carrier'] = {'beacon': 'offensive'}
        self.assertTrue(any('a expendable payload needs a support beacon' in p for p in P.validate(red, schema)))
        # A presentation icon needs its PNG beside the project.
        with tempfile.TemporaryDirectory() as folder:
            project = copy.deepcopy(PROJECT)
            project['stratagems'][0]['payload']['presentation']['icon'] = 'missing_icon'
            Path(folder, 'images').mkdir()
            Path(folder, 'images/eat17g.png').write_bytes((ROOT / 'proof/EAT17GExample/images/eat17g.png').read_bytes())
            Path(folder, 'custom_stratagems.json').write_text(json.dumps(project), encoding='utf-8')
            with self.assertRaises(ValueError) as caught:
                P.compile_project(folder, write=False)
            self.assertIn('payload.presentation.icon: images/missing_icon.png is missing', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
