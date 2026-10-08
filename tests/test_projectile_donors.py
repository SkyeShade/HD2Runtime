"""More projectile donors (scripts/research_projectile_donors.py, research/projectile-donors-F5FEE03DCFDB.json; the
attack-output catalogue, domains/attack_outputs.lua; docs/attack-outputs.md "More donors"):
  * the named projectile types not yet catalogued whose owner is one fixed member of one uniquely owned, profiled
    component record (a stratagem's Eagle payload, orbital shell, orbital projectile or entity weapon; a weapon's second
    projectile), the member holding the type in the snapshot, with the swap's own class rule;
  * every stratagem donor has its owner entity's loadable package; weapon donors resolve through their weapon;
  * each is a catalogued output (hd2.attack_output) whose live reference is its own component member, marked
    unverified: every use needs allow_unverified_reference and allow_unverified_effect, whatever the class;
  * the packaged runtime applies every one of them (scripts/validate_packaged_runtime.py projectile-donors-all)."""
import json
import unittest

from support import ROOT, run

RESEARCH = json.loads((ROOT / 'research/projectile-donors-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


class ProjectileDonorResearchTests(unittest.TestCase):
    def test_the_research(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        s = RESEARCH['summary']
        # 31 since 0.30.2: projectile 150 is the SEAF SMG round, not the SMG-37 Defender's (its proven root).
        self.assertEqual((s['named'], s['donors']), (224, 31))
        self.assertEqual(s['byOwnerKind'], {'player_weapon': 4, 'stratagem': 23, 'support_weapon': 4})
        self.assertNotIn(150, {d['projectileType'] for d in RESEARCH['donors']})
        by_type = {d['projectileType']: d for d in RESEARCH['donors']}
        # The Eagle 500kg Bomb: EagleComponentData +24 of its own record; the Railcannon: OrbitalAbility +532.
        self.assertEqual((by_type[239]['component'], by_type[239]['member'], by_type[239]['owner']),
            ('EagleComponentData', 24, 'Eagle 500kg Bomb'))
        self.assertEqual((by_type[277]['component'], by_type[277]['member']), ('OrbitalAbilityComponentData', 532))
        self.assertEqual((by_type[100]['component'], by_type[100]['member']), ('BombardmentComponentData', 64))
        for d in RESEARCH['donors']:
            self.assertTrue(d['componentIdentity']['uniqueOwner'], d['name'])
            self.assertIn(d['compatibilityClass'], ('conventional_plain', 'explosive_impact',
                'explosive_impact_and_expiry', 'explosive_shrapnel'))
        # A short name only for a stratagem with exactly one donor; never a weapon's own (catalogued) name.
        self.assertEqual(by_type[239]['aliases'], ['Eagle 500kg Bomb (projectile 239)', 'Eagle 500kg Bomb'])
        self.assertEqual(by_type[284]['aliases'], ['AC-8 Autocannon (projectile 284)'])
        self.assertEqual(by_type[194]['aliases'][1:], ['Orbital 120mm HE Barrage'])
        # The stun-field donor (EMS Mortar shell 154) stays catalogued for its own scope; enemy weapons are refused.
        self.assertNotIn(154, by_type)
        reasons = {r['projectileType']: r['reason'] for r in RESEARCH['refused']}
        self.assertTrue(any('enemy weapon' in r for r in reasons.values()))

    def test_outputs_are_current(self):
        import research_projectile_donors
        research_projectile_donors.main(['--check'])
        import generate_attack_outputs
        self.assertEqual(generate_attack_outputs.generate(check=True), [])

    def test_the_catalogue_entries(self):
        self.assertEqual(run(r"""
local A=require('hd2runtime/domains/attack_outputs')
local n=0
for _,o in pairs(A.outputs)do
    if o.unverifiedDonor then
        n=n+1
        assert(o.editable and o.family=='projectile'and o.backing.kind=='component'and o.backing.uniqueOwner,o.id)
        assert(o.dependencyKey or o.owner.kind=='player_weapon'or o.owner.kind=='support_weapon',o.id)
    end
end
assert(n==31,n)
local bomb=A.outputs[A.aliases['Eagle 500kg Bomb']]
assert(bomb.currentDefault==239 and bomb.backing.component=='EagleComponentData'and bomb.backing.offset==24)
assert(bomb.dependencyKey=='projectile_donor/Eagle 500kg Bomb (projectile 239)')
local assets=require('hd2runtime/core/assets')
local dep=assert(assets.dependency(bomb.dependencyKey),'the bomb package is catalogued')
assert(dep.name=='packages/generated/loadout/eagle_bomb',dep.name)
-- The SDK catalogue lists them with both acknowledgements.
return 'ok'
"""), b'ok')
        sdk = json.loads((ROOT / 'sdk/AttackOutputCapabilities.json').read_text(encoding='utf-8'))
        rows = [o for o in sdk['outputs'] if o.get('kind') == 'projectile_donor']
        self.assertEqual(len(rows), 31)
        for o in rows:
            self.assertEqual(o['acknowledgements']['sameClass'], ['allow_unverified_reference', 'allow_unverified_effect'])

    def test_every_donor_has_a_component_host_in_the_packaged_scenario(self):
        import validate_packaged_runtime as packaged
        self.assertIn('projectile-donors-all', packaged.SCENARIOS)
        body = packaged.projectile_donors_all()
        for d in RESEARCH['donors']:
            self.assertIn('hd2.attack_output("%s")' % d['name'], body)
        self.assertEqual(packaged.EXTRAS['projectile-donors']['rejected'],
            {'arbitrator-hmg-no-ack': 'this donor is not live-tested yet and requires allow_unverified_reference=true'})


if __name__ == '__main__':
    unittest.main()
