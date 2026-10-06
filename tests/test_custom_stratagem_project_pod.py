"""Carrier groups and carrier pods in the builder schema and the project format (docs/custom-stratagem-builder.md;
scripts/generate_custom_stratagem_schema.py, sdk/tools/custom_stratagem_project.py):
  * the schema: carrier.group / carrier.slots, the carrierGroups, podItems and podCarriers catalogues, the pod payload
    family (podFamily) and the expendable family's pod option (familyOptions), all from the Runtime's own tables;
  * an EAT-17G project (the expendable group, two clone launchers) and a support kit project (the support_pod group:
    an MG-43 and a B-1 Supply Pack) validate, compile deterministically to typed handles, and the compiled addon registers
    in the Runtime with the same data;
  * the validator refuses what the Runtime refuses (a group that cannot carry the payload, slots without a pod group,
    'clone' outside an expendable pod, a primary without its acknowledgement, an unknown item, an expendable pod without
    the clone)."""
import copy
import json
import sys
import unittest

from support import ROOT, run, lua as lua_literal
from test_custom_stratagem_project import json_schema_errors, wrapped
from test_stratagem_calldown_code import WORLD

sys.path.insert(0, str(ROOT / 'sdk'))
from tools import custom_stratagem_project as P  # noqa: E402

EAT = {'id': 'eat17g_pod', 'name': 'EAT-17G GAS EXPENDABLE ANTI-TANK', 'name_cased': 'EAT-17G Gas Expendable Anti-Tank',
    'description': 'Two expendable EAT-17G launchers.', 'icon': {'image': 'eat17g'},
    'code': ['down', 'down', 'up', 'up', 'left', 'right'], 'cooldown': 70, 'carrier': {'group': 'expendable'},
    'payload': {'family': 'expendable', 'weapon': 'EAT-17 Expendable Anti-Tank',
        'modify': {'impact_explosion': 'Orbital Gas Strike'}, 'level': 'full', 'pod': [{'item': 'clone', 'count': 2}]}}
KIT = {'id': 'support_kit', 'name': 'SUPPORT KIT', 'description': 'A machine gun and a supply pack.',
    'icon': {'image': 'eat17g'}, 'code': ['right', 'left', 'right', 'left', 'up'], 'cooldown': 90,
    'carrier': {'group': 'support_pod', 'slots': 2},
    'payload': {'family': 'pod', 'items': [{'item': 'support_weapon/MG-43 Machine Gun', 'modify': {'ammo': 300}},
        {'item': 'backpack/B-1 Supply Pack'}]}}
PROJECT = {'format': 'hd2runtime-custom-stratagems/1', 'stratagems': [EAT, KIT]}


class PodProjectTests(unittest.TestCase):
    def test_the_schema(self):
        schema = P.load_schema()
        self.assertEqual(set(schema['carrier']), {'beacon', 'prefer_families', 'allow_families', 'exclude', 'group',
            'slots'})
        self.assertEqual(schema['carrier']['group']['values'], ['orbital', 'any_red', 'any', 'support', 'support_pod',
            'expendable', 'weapon', 'sentry', 'emplacement', 'eagle'])
        groups = {g['name']: g for g in schema['catalogs']['carrierGroups']}
        self.assertEqual(groups['support_pod']['payloads'], ['pod'])
        self.assertEqual(groups['expendable']['defaults'], ['expendable'])
        self.assertIn('pelican', groups['any_red']['defaults'])
        items = {i['key']: i for i in schema['catalogs']['podItems']}
        self.assertEqual(items['player_weapon/JAR-5 Dominator']['acknowledgement'], 'allow_unverified_effect')
        self.assertEqual(items['backpack/B-1 Supply Pack']['role'], 'backpack')
        self.assertFalse(any(k.startswith('throwable/') for k in items))
        carriers = {c['name']: c for c in schema['catalogs']['podCarriers']}
        self.assertEqual(carriers['EAT-411 Leveller'], {'name': 'EAT-411 Leveller', 'capacity': 2,
            'roles': ['weapon', 'weapon']})
        self.assertEqual(schema['podFamily']['family'], 'pod')
        self.assertIn('pod', schema['familyOptions']['expendable'])

    def test_projects_validate_compile_and_register(self):
        schema = P.load_schema()
        project_schema = json.loads((ROOT / 'sdk/schemas/custom_stratagems.project.schema.json').read_text(
            encoding='utf-8'))
        self.assertEqual(P.validate(PROJECT, schema), [])
        self.assertEqual(json_schema_errors(PROJECT, project_schema), [])
        # A per-call rpm on a weapon whose type binds the rate-of-fire selector is refused, as the Runtime refuses it.
        rpm = copy.deepcopy(PROJECT)
        rpm['stratagems'][1]['payload']['items'][0]['modify'] = {'rpm': 900}
        self.assertTrue(any('binds the rate-of-fire selector' in p for p in P.validate(rpm, schema)),
            P.validate(rpm, schema))
        text = P.compile_lua(PROJECT)
        self.assertEqual(text, P.compile_lua(copy.deepcopy(PROJECT)))
        self.assertIn("carrier={group='expendable'},", text)
        self.assertIn("level='full',pod={{item='clone',count=2}}},", text)
        self.assertIn("carrier={group='support_pod',slots=2},", text)
        self.assertIn("delivery={family='support',items={{item=hd2.support_weapon('MG-43 Machine Gun'),modify={ammo=300}},"
            "{item=hd2.backpack('B-1 Supply Pack')}}},", text)
        resource, addon = wrapped('EAT17GExample', text)
        self.assertEqual(run(WORLD + 'local ADDON=' + lua_literal(addon) + '\nlocal RESOURCE=' + lua_literal(resource) + r'''
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
assert(loadstring(ADDON,'@'..RESOURCE))()
local e=custom.get('eat17g_pod')
assert(e and e.kind=='expendable'and e.group=='expendable'and e.delivery.pod.total==2 and e.slots==2)
local k=custom.get('support_kit')
assert(k and k.kind=='pod'and k.group=='support_pod'and k.slots==2 and k.delivery.count==2
    and k.delivery.items['11C27D3BABB38956'].modify.ammo==300 and k.delivery.items['4EF9A47109239A58'].kind=='backpack')
return 'ok'
'''), b'ok')

    def test_the_validator_refuses_what_the_runtime_refuses(self):
        schema = P.load_schema()

        def problems(change):
            bad = copy.deepcopy(PROJECT)
            change(bad['stratagems'])
            return P.validate(bad, schema)

        def expect(change, needle):
            found = problems(change)
            self.assertTrue(any(needle in p for p in found), (needle, found))

        expect(lambda s: s[1]['carrier'].update(group='orbital'), 'the group orbital cannot carry a pod payload')
        expect(lambda s: s[0]['carrier'].update(group='support_pod'), 'the group support_pod cannot carry a expendable')
        expect(lambda s: s[1].update(carrier={'beacon': 'support', 'slots': 2}),
            'a pod capacity: only with the support_pod or expendable group')
        expect(lambda s: s[1]['payload']['items'].append({'item': 'clone'}), '"clone" is an expendable pod')
        expect(lambda s: s[1]['payload']['items'].append({'item': 'player_weapon/JAR-5 Dominator'}),
            'it needs allow_unverified_effect = true')
        expect(lambda s: s[1]['payload']['items'].append({'item': 'throwable/G-6 Frag'}), 'must be "clone" (expendable) or a '
            'podItems key')
        expect(lambda s: s[0]['payload'].update(pod=[{'item': 'backpack/B-1 Supply Pack'}]), 'must hold the clone')
        expect(lambda s: s[1]['payload']['items'][1].update(modify={'ammo': 2}), 'a backpack: no instance-local backpack')


if __name__ == '__main__':
    unittest.main()
