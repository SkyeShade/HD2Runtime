"""Coverage pass: sentry turret motion / targeting range, the status catalog and status references, enemies and
enemy structures. Every field here is published only with its research proof; these tests pin the proofs, the
typed API and the guards."""
import json
import unittest

from support import ROOT, run

TURRETED = ('A/MG-43 Machine Gun Sentry', 'A/G-16 Gatling Sentry', 'A/AC-8 Autocannon Sentry',
    'A/M-12 Mortar Sentry', 'A/MLS-4X Rocket Sentry', 'A/M-23 EMS Mortar Sentry', 'A/LAS-98 Laser Sentry',
    'A/FLAM-40 Flame Sentry', 'A/GM-17 Gas Mortar Sentry')


class SentryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = {s['name']: s for s in json.loads(
            (ROOT / 'research/defensive-stratagem-runtime-F5FEE03DCFDB.json').read_text())['stratagems']}
        cls.catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())

    def fields(self, stratagem, path):
        return {f['semanticFieldId']: f for f in self.catalog['fieldInstances']
            if f['target'].get('stratagem') == stratagem and f['target']['path'] == path}

    def test_turret_members_equal_the_wiki_tables_on_every_turreted_sentry(self):
        for name in TURRETED:
            proof = self.research[name]['deploymentProofs']['turret']
            self.assertTrue(proof['exact'], name)
            self.assertEqual(set(proof['wikiChecks']), {'horizontalTurnSpeed', 'verticalTurnSpeed', 'verticalLimit'})
            fields = self.fields(name, 'turret')
            self.assertEqual(set(fields), {'turret.yaw_speed', 'turret.pitch_speed', 'turret.pitch_min',
                'turret.pitch_max', 'turret.yaw_min', 'turret.yaw_max'})
            table = self.research[name]['deploymentProofs']['wikiTable']
            self.assertEqual(fields['turret.yaw_speed']['currentDefault'], table['horizontalTurnSpeed'])
            self.assertEqual(fields['turret.pitch_speed']['currentDefault'], table['verticalTurnSpeed'])
            self.assertEqual([fields['turret.pitch_min']['currentDefault'], fields['turret.pitch_max']['currentDefault']],
                table['verticalLimit'])
            for field in fields.values():
                self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
                self.assertFalse(field['shared'])
                self.assertEqual(field['backingObjectKind'], 'TurretComponentData')
        autocannon = self.fields('A/AC-8 Autocannon Sentry', 'turret')
        flame = self.fields('A/FLAM-40 Flame Sentry', 'turret')
        self.assertEqual(autocannon['turret.yaw_speed']['currentDefault'], 20.0)
        self.assertEqual(flame['turret.yaw_speed']['currentDefault'], 140.0)
        self.assertEqual(self.fields('A/M-12 Mortar Sentry', 'turret')['turret.pitch_min']['currentDefault'], 35.0)
        # The Tesla Tower, emplacements and mines have no turret component.
        self.assertFalse(self.fields('A/ARC-3 Tesla Tower', 'turret'))
        self.assertFalse(self.fields('E/MG-101 HMG Emplacement', 'turret'))

    def test_targeting_range_rests_on_stated_ranges(self):
        stated = {name: s['deploymentProofs']['sensor']['statement'] for name, s in self.research.items()
            if (s.get('deploymentProofs') or {}).get('sensor', {}).get('statement')}
        self.assertEqual(len(stated), 7)
        self.assertTrue(all(item['exact'] for item in stated.values()))
        self.assertEqual({item['value'] for item in stated.values()}, {50, 75, 100, 125})
        ranges = {name: self.fields(name, 'targeting').get('targeting.range') for name in self.research}
        self.assertEqual(sum(1 for field in ranges.values() if field), 10)
        self.assertEqual(ranges['A/M-12 Mortar Sentry']['currentDefault'], 125.0)
        self.assertEqual(ranges['A/ARC-3 Tesla Tower']['currentDefault'], 25.0)

    def test_sentry_lifetime_uses_the_gameplay_proven_member(self):
        for name in TURRETED:
            lifetime = self.research[name]['deploymentProofs']['lifetime']
            self.assertTrue(lifetime['exact'], name)
            field = self.fields(name, 'deployed_entity')['payload.lifetime']
            self.assertEqual(field['currentDefault'], lifetime['wiki'])
            self.assertIsNone(field.get('acknowledgement'))

    def test_api_and_guards(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local entity=hd2.stratagem('A/AC-8 Autocannon Sentry'):deployed_entity()
local turret=entity:turret()
assert(turret.path=='turret' and #turret:describe().fields==6 and turret:describe().turret)
transactions.validate{id='turn',target=turret,allow_unverified_effect=true,changes={
 {field=hd2.fields.turret.yaw_speed,expect=20,value=120},{field=hd2.fields.turret.pitch_speed,expect=20,value=90}}}
local ok,why=pcall(patches.validate,{id='turn',target=turret,field=hd2.fields.turret.yaw_speed,expect=20,value=120})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true),why)
ok,why=pcall(patches.validate,{id='turn',target=turret,allow_unverified_effect=true,
 field=hd2.fields.turret.yaw_speed,expect=20,value=5000})
assert(not ok and tostring(why):find('reviewed range',1,true),why)
ok,why=pcall(patches.validate,{id='turn',target=turret,allow_unverified_effect=true,
 field=hd2.fields.turret.yaw_speed,expect=80,value=120})
assert(not ok and tostring(why):find('expect differs',1,true),why)
local targeting=hd2.stratagem('A/MG-43 Machine Gun Sentry'):deployed_entity():targeting()
patches.validate{id='range',target=targeting,allow_unverified_effect=true,field=hd2.fields.targeting.range,expect=75,value=25}
assert(not pcall(function()return hd2.stratagem('A/ARC-3 Tesla Tower'):deployed_entity():turret()end))
assert(hd2.stratagem('A/ARC-3 Tesla Tower'):deployed_entity():targeting():describe().targeting.range==25)
patches.validate{id='life',target=entity,field=hd2.fields.payload.entity_lifetime,expect=150,value=300}
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
