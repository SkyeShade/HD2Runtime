"""The carrier weapon clone research (research/docs/carrier-weapon-clone-F5FEE03DCFDB.md,
research/carrier-weapon-clone-F5FEE03DCFDB.json): read-only, its pins identical in every snapshot, and the facts the
design rests on: the EAT-17's clone class is {EAT-700, EAT-411}; the expendable drop is WeaponData +0x1CC played by
0x753A10 only without a WeaponReload instance; the AC-8 cannot be an EAT; an EAT-700 -> EAT-17 clone is 19 member
copies into exclusively owned records with the expendable contract already identical."""
import json
import unittest

from support import ROOT

RESEARCH = json.loads((ROOT / 'research/carrier-weapon-clone-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


class CarrierWeaponCloneResearchTests(unittest.TestCase):
    def test_read_only_and_pinned(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        roles = {p['rva']: p['role'] for rows in RESEARCH['pins'].values() for p in rows}
        self.assertIn(0x753C2F, roles)      # auto drop: WeaponData +0x1CC
        self.assertIn(0x753BBF, roles)      # ... skipped when a WeaponReload instance exists
        self.assertIn(0x753CFA, roles)      # ... played on the wielder
        self.assertIn(0x6EAD74, roles)      # UnitComponent: the type record unless a delta copy exists
        self.assertIn(0x509AFC, roles)      # WeaponData resolver falls back to the type record
        self.assertEqual(RESEARCH['typeTableSlots']['checkedAgainst'], 12)

    def test_clone_class(self):
        checks = RESEARCH['checks']
        self.assertEqual(sorted(checks['eat17CloneClass']),
            ['EAT-17 Expendable Anti-Tank', 'EAT-411 Leveller', 'EAT-700 Expendable Napalm'])
        self.assertEqual(checks['eat17CloneHosts'], ['EAT-700 Expendable Napalm', 'EAT-411 Leveller'])
        self.assertEqual(RESEARCH['carrierCandidates'][0]['weapon'], 'EAT-700 Expendable Napalm')

    def test_expendable_is_a_component_property(self):
        checks = RESEARCH['checks']
        self.assertTrue(checks['autoDropOnlyWithoutWeaponReload'])
        self.assertTrue(checks['weaponReloadGateIsWeaponReloadManager'])
        self.assertEqual(checks['autoDropWeapons'], {'EAT-411 Leveller': 96, 'EAT-700 Expendable Napalm': 96,
            'MGX-42 Bullet Storm': 97, 'MLS-4X Commando': 96})
        readers = RESEARCH['code']['census']['0x509A40 WeaponData resolver (copy, else type)']['memberReaders']
        self.assertIn('0x753A10', readers['+0x1CC'])

    def test_ac8_is_not_an_eat(self):
        ac8 = next(c for c in RESEARCH['carrierCandidates'] if c['weapon'] == 'AC-8 Autocannon')
        self.assertFalse(ac8['eat17CloneHost'])
        self.assertEqual({m['component'] for m in ac8['missingComponents']},
            {'BackblastComponentData', 'WeaponMagazineComponentData'})
        self.assertEqual({m['component'] for m in ac8['extraComponents']}, {'WeaponReloadComponentData',
            'WeaponRoundsComponentData', 'WeaponAssistedReloadComponentData'})
        self.assertTrue(ac8['aspects']['expendable'].startswith('impossible'))
        self.assertTrue(ac8['aspects']['backblast'].startswith('impossible'))

    def test_eat700_clone_members(self):
        checks = RESEARCH['checks']
        self.assertEqual(checks['eat700CopyMembersByAspect'],
            {'animation': 8, 'firing': 1, 'handling': 4, 'model': 3, 'sound': 3})
        self.assertTrue(checks['eat700ContractIdentical'])
        self.assertTrue(checks['eat700EveryRecordExclusive'])
        members = {(m['component'], m['offset']): m for m in RESEARCH['focusDiffs']['EAT-700']['members']}
        self.assertEqual(members[('UnitComponentData', '0x0')]['donor']['resource'],
            'content/fac_helldivers/equipment/support_weapons/lat_oneshot/lat_oneshot')
        self.assertEqual(members[('WeaponCustomizationComponentData', '0x78')]['donor']['resource'],
            'content/fac_helldivers/equipment/support_weapons/lat_oneshot/lat_oneshot_sight')
        self.assertEqual(members[('EquipmentComponentData', '0xC0')]['donor'], 21)        # LAT grip
        self.assertEqual(members[('ProjectileWeaponComponentData', '0x0')]['donor'], 132)  # the EAT-17 rocket
        never = {m['component'] for m in members.values() if m['policy'] == 'never'}
        self.assertEqual(never, {'LoadoutEntryComponentData', 'LoadoutPackageComponentData'})

    def test_lifecycle_and_resources(self):
        checks = RESEARCH['checks']
        self.assertTrue(checks['noUnitComponentCopiesInMissions'])
        self.assertTrue(all(checks['writtenTypeTablesInPlace'].values()))
        self.assertTrue(checks['eat17WielderEventsInAvatar'])
        self.assertTrue(checks['eat17WeaponEventsInEat17StateMachine'])
        custom = RESEARCH['resources']['customization']
        self.assertFalse(custom['EAT-17']['optionInCustomizationTable'])    # no delta: the type's own sight
        self.assertEqual(custom['EAT-700']['optionDebugName'], 'Support Scope')
        units = RESEARCH['resources']['packages']['EAT-17']['unit']
        self.assertIn('content/fac_helldivers/equipment/support_weapons/lat_oneshot/lat_oneshot_sight', units)

    def test_round_overrides(self):
        """The EAT-17 clone's reviewed round (scripts/research_clone_rounds.py): the RL-77 Airburst round 312."""
        self.assertEqual(list(RESEARCH['roundOverrides']), ['EAT-17 Expendable Anti-Tank'])
        r = RESEARCH['roundOverrides']['EAT-17 Expendable Anti-Tank']['RL-77 Airburst Rocket Launcher']
        self.assertEqual((r['type'], r['hosts']), (312, ['EAT-700 Expendable Napalm', 'EAT-411 Leveller']))
        # Its chain: identical in every snapshot but the explosions' relocated +0x28 word.
        self.assertEqual([(x['kind'], x['id'], x['masked']) for x in r['rows']], [('projectile', 312, []),
            ('damage', 380, []), ('explosion', 325, [40, 44]), ('damage', 277, []), ('projectile', 78, []),
            ('explosion', 7, [40, 44]), ('damage', 335, [])])
        self.assertEqual(r['rowDigests']['projectile 312'], '3DB5B68EB196B804')
        self.assertEqual(r['rowDigests']['explosion 325'], '77280F0B95DA9895')
        self.assertEqual(r['rowDigests']['projectile 78'], 'BC04AC91153443DD')
        s = r['semantics']
        self.assertEqual((s['round']['proximity'], s['round']['arming'], s['round']['lifetime'], s['round']['impact'],
            s['round']['expiry'], s['round']['speed']), (2.0, 1.0, 1.5, 325, 325, 250.0))
        self.assertEqual((s['round']['damage']['standard'], s['round']['damage']['armorPenetration'][0]), (350, 3))
        self.assertEqual(s['explosion']['shrapnel'], {'count': 25, 'projectile': 78})
        self.assertEqual((s['submunition']['impact'], s['submunitionExplosion']['damage']['standard']), (7, 500))
        # The code consuming it: pinned, identical in every snapshot.
        self.assertFalse(any(r['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(len(r['pinnedBytesMismatchPerSnapshot']), 7)
        self.assertIn(0x13AC0D8, {p['rva'] for p in r['pins']})     # the proximity filter: row +0xF8
        # The weapon side: no airburst member, the hosts have no selector, networked fire everywhere.
        w = r['weaponSide']
        self.assertEqual(w['differsFromGR8'], ['+0x0', '+0x104', '+0x114', '+0x240'])
        self.assertEqual((w['selector']['EAT-700'], w['selector']['EAT-411']), (0, 0))
        self.assertEqual(set(w['networkedFire'].values()), {1})
        # The packages: every resource ships in the round's own package or the mission package; the mission package is
        # resident in every live mission snapshot, never aboard the ship, and never refcounted.
        p = r['packages']
        self.assertEqual((p['unit']['id'], p['unit']['name'], p['mission']['id']), ('0xF7646E79610C124D',
            'packages/generated/loadout/airburst_rocket_launcher', '0x7ED1F941859987B4'))
        self.assertEqual(w['loadoutPackage'], p['unit']['id'])
        self.assertTrue(all(x['inUnitPackage'] or x['inMissionPackage'] for x in p['resources']))
        only = {x['resource']: x['onlyIn'] for x in p['resources']}
        self.assertEqual(only['0x36AB9A3DCAE3D562'], ['packages/generated/loadout/airburst_rocket_launcher'])
        self.assertEqual(only['0x6D2BAD783480D272'], ['0x7ED1F941859987B4'])
        self.assertEqual(only['0xA6CD8A90185B6567'], ['0x7ED1F941859987B4'])
        for name, state in p['residency'].items():
            self.assertFalse(state['mission']['refcounted'], name)
            self.assertEqual(state['mission']['resident'], True if 'mission-host' in name else
                False if 'transition' in name else None, name)
        self.assertEqual(r['write'], {'component': 'ProjectileWeaponComponentData', 'offset': 0, 'width': 4,
            'value': '38010000', 'levels': r['write']['levels']})


if __name__ == '__main__':
    unittest.main()
