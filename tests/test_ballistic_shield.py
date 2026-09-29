"""SH-20 Ballistic Shield: the active plate armor is damage zone 0 "shield", not the default-zone entity.armor."""
import json
import unittest

from support import ROOT, run

RESEARCH = json.loads((ROOT / 'research/ballistic-shield-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
BACKPACKS = json.loads((ROOT / 'sdk/BackpackAuthoringCapabilities.json').read_text(encoding='utf-8'))
SH20 = 'SH-20 Ballistic Shield Backpack'


def fields(backpack):
    return {(f['target']['path'], f['semanticFieldId']): f for f in BACKPACKS['fieldInstances']
        if f['target'].get('backpack') == backpack}


class BallisticShieldTests(unittest.TestCase):
    def test_the_research_explains_the_live_observation(self):
        active = RESEARCH['answer']['activeField']
        self.assertEqual((active['zoneName'], active['recordOffset'], active['vanilla'], active['ownerCount']),
            ('shield', 736, 4, 1))
        self.assertEqual(set(active['zoneActors']), {'damageable', 'collision'})
        self.assertEqual(RESEARCH['source']['writes'], 0)
        rule = RESEARCH['damageModel']['rule']
        self.assertIn('0.65 if 0 <= AP - armor < 1', rule)

    def test_the_catalog_publishes_the_plate_zone_and_downgrades_the_fallback(self):
        sh20 = fields(SH20)
        plate = sh20[('damage_zone', 'zone.armor')]
        self.assertEqual((plate['currentDefault'], plate['editable'], plate['acknowledgement']),
            (4, True, 'allow_unverified_effect'))
        self.assertEqual(plate['effect']['activeSource'], 'ACTIVE_AT_INSTANTIATION')
        self.assertEqual(plate['target']['zone'], 'zone_0')
        fallback = sh20[('backpack', 'entity.armor')]
        self.assertEqual(fallback['effect']['activeSource'], 'DORMANT_OR_METADATA')
        self.assertFalse(fallback['editable'])                   # live-failed: withdrawn, with the reason
        self.assertIn("damage_zone('shield')", fallback['reason'])
        # Main health stays the plate's pool (zone health -1 forwards to it) and needs no acknowledgement.
        self.assertIsNone(sh20[('backpack', 'entity.health')].get('acknowledgement'))
        sh51 = fields('SH-51 Directional Shield')
        for field in ('entity.health', 'entity.armor'):
            self.assertEqual(sh51[('backpack', field)]['effect']['activeSource'], 'AMBIGUOUS')
            self.assertEqual(sh51[('backpack', field)]['acknowledgement'], 'allow_unverified_effect')

    def test_runtime_resolves_the_zone_and_refuses_the_fallback_without_acknowledgement(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local writes=require('hd2runtime/domains/entity_writes')
local shield=hd2.backpack('SH-20 Ballistic Shield Backpack')
local plate=shield:damage_zone('shield')
assert(plate.zone=='zone_0'and shield:damage_zone(0).zone=='zone_0'and #shield:damage_zones()==1)
assert(shield:describe().damageZones[1].name=='shield')
local ok,why=pcall(writes.validate_patch,{id='plate',target=plate,field=hd2.fields.zone.armor,expect=4,value=5})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true),tostring(why))
local spec=writes.validate_patch{id='plate',target=plate,allow_unverified_effect=true,
 field=hd2.fields.zone.armor,expect=4,value=5}
local guards=spec.changes[1].descriptor.backing.guards
assert(#guards==2 and guards[1].offset==616 and guards[1].hex=='e5d61ac6',tostring(guards[1].hex))
ok,why=pcall(writes.validate_patch,{id='old',target=shield,allow_unverified_effect=true,
 field=hd2.fields.entity.armor,expect=4,value=5})
assert(not ok and tostring(why):find('field is read-only',1,true)and tostring(why):find("damage_zone('shield')",1,true),
 tostring(why))
ok,why=pcall(shield.damage_zone,shield,'arm')
assert(not ok and tostring(why):find('unknown reviewed damage zone',1,true))
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
