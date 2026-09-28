import json
import sys
import unittest
from unittest import mock

from support import ROOT, run
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_entity_authoring
import generate_stratagem_authoring


class EntityAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vehicles = json.loads((ROOT / 'sdk/VehicleAuthoringCapabilities.json').read_text())
        cls.backpacks = json.loads((ROOT / 'sdk/BackpackAuthoringCapabilities.json').read_text())
        cls.stratagems = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())
        cls.research = json.loads((ROOT / 'research/entity-authoring-runtime-F5FEE03DCFDB.json').read_text())
        cls.vehicle = {item['name']: item for item in cls.vehicles['vehicles']}
        cls.backpack = {item['name']: item for item in cls.backpacks['backpacks']}
        cls.fields = {item['instanceKey']: item for item in
            cls.vehicles['fieldInstances'] + cls.backpacks['fieldInstances']}

    def field(self, family, name, field_id, **target):
        items = [item for item in (self.vehicles if family == 'vehicle' else self.backpacks)['fieldInstances']
            if item['target'][family] == name and item['semanticFieldId'] == field_id
            and all(item['target'].get(key) == value for key, value in target.items())]
        self.assertEqual(len(items), 1, (name, field_id, target))
        return items[0]

    def test_generated_outputs_are_fresh_and_sanitized(self):
        self.assertFalse(generate_entity_authoring.generate(check=True))
        for document, contract in ((self.vehicles, 'hd2runtime.vehicle.guarded_authoring.v1'),
                (self.backpacks, 'hd2runtime.backpack.guarded_authoring.v1')):
            self.assertEqual(document['contract'], contract)
            self.assertEqual(document['hd2RuntimeVersion'], (ROOT / 'VERSION').read_text().strip())
            self.assertTrue(document['instanceAudit']['exactMatch'])
            text = json.dumps(document).lower()
            self.assertNotIn('0x', text)
            for token in ('resourcehash', 'recordindex', 'indexrow', 'nativeidentity', 'entityrow'):
                self.assertNotIn(token, text)
            hashes = {item['resource'] for item in self.research['vehicles'] + self.research['backpacks']}
            hashes |= set(self.research['mountedEntities'])
            for value in hashes:
                self.assertNotIn(value[2:].lower(), text)

    def test_catalog_coverage(self):
        summary = self.vehicles['summary']
        self.assertEqual(summary['vehicles'], 11)
        self.assertEqual(summary['stratagemVehicles'], 9)
        self.assertEqual(summary['nativeOnlyVehicles'], 2)
        self.assertEqual(summary['discoveredMountedWeapons'], 79)
        self.assertEqual(summary['mountRecordsSurveyed'], 163)
        self.assertEqual(summary['swappableMountSlots'], 18)
        self.assertEqual(summary['nonWeaponMountSlots'], 4)
        self.assertEqual(summary['writableByTier'], {'gameplay_proven': 64, 'schema_proven': 636,
            'live_write_verified': 2, 'structural_reference': 16})
        backpack = self.backpacks['summary']
        self.assertEqual(backpack['backpacks'], 13)
        self.assertEqual(backpack['rackChainsResolved'], 13)
        self.assertEqual(backpack['writableFieldInstances'], 9)
        self.assertEqual(backpack['writableByTier'], {'gameplay_proven': 2, 'schema_proven': 7})

    def test_semantic_identities_are_unique_and_stable(self):
        for collection in (self.vehicles['vehicles'], self.backpacks['backpacks'], self.vehicles['mountedWeapons']):
            ids = [item['semanticId'] for item in collection]
            self.assertEqual(len(ids), len(set(ids)))
        zones = [zone['semanticId'] for item in self.vehicles['vehicles'] for zone in item['durability']['zones']]
        mounts = [mount['semanticId'] for item in self.vehicles['vehicles'] for mount in item['mounts']]
        self.assertEqual(len(zones), len(set(zones)))
        self.assertEqual(len(mounts), len(set(mounts)))
        self.assertEqual(self.vehicle['TD-220 Bastion MK XVI']['semanticId'],
            'vehicle/v1/td-220-bastion-mk-xvi/' + generate_entity_authoring.digest('TD-220 Bastion MK XVI'))
        self.assertEqual(self.backpack['LIFT-850 Jump Pack']['semanticId'],
            'backpack/v1/lift-850-jump-pack/' + generate_entity_authoring.digest('LIFT-850 Jump Pack'))

    def test_identity_chains_and_bidirectional_stratagem_links(self):
        roots = {item['semanticId']: item for item in self.stratagems['stratagems']}
        for family, entries in (('vehicle', self.vehicles['vehicles']), ('backpack', self.backpacks['backpacks'])):
            for item in entries:
                link = item['callInStratagem']
                if not link['known']:
                    self.assertEqual(item['catalogSource'], 'native_only')
                    continue
                root = roots[link['semanticId']]
                self.assertEqual(root['family'], family)
                self.assertEqual(root['delivers']['semanticId'], item['semanticId'])
                self.assertTrue(root['cooldownCapability']['writable'])
                self.assertTrue(all(item['correlation'].values()), item['name'])
        for item in self.research['vehicles']:
            if item['catalogSource'] == 'wiki_stratagem':
                self.assertEqual(item['stratagemRoot']['payloads'][0], item['resource'])
        for item in self.research['backpacks']:
            self.assertEqual(item['rack']['attachedItems'], [item['resource']])
        self.assertEqual(self.backpack['LIFT-850 Jump Pack']['deliveryChain'],
            ['stratagem_definition', 'hellpod_rack', 'backpack_entity'])

    def test_vehicle_durability_zones_and_evidence_tiers(self):
        bastion = self.vehicle['TD-220 Bastion MK XVI']
        self.assertEqual(bastion['durability']['mainHealth'], 8000)
        self.assertEqual(bastion['durability']['populatedZones'], 31)
        zones = {zone['zoneId']: zone for zone in bastion['durability']['zones']}
        self.assertEqual(zones['zone_3']['values']['affectsMainHealth'], 1.0)
        self.assertIn('zone_3', zones['zone_6']['childZones'])
        self.assertEqual(self.field('vehicle', 'TD-220 Bastion MK XVI', 'zone.armor', zone='zone_3')
            ['evidence']['tier'], 'gameplay_proven')
        self.assertEqual(self.field('vehicle', 'TD-110 Maelstrom', 'zone.armor', zone='zone_3')
            ['evidence']['tier'], 'schema_proven')
        self.assertEqual(self.field('vehicle', 'M-102 Gunner FRV', 'entity.health')['currentDefault'], 2400)
        exo = self.vehicle['EXO-45 Patriot Exosuit']
        self.assertEqual(exo['durability']['mainArmor'], 4)
        self.assertEqual(exo['durability']['populatedZones'], 8)
        for zone in bastion['durability']['zones']:
            self.assertEqual(len(zone['fieldInstanceKeys']), 3)

    def test_mount_slots_and_compatible_replacements(self):
        weapons = {item['semanticId']: item for item in self.vehicles['mountedWeapons']}
        frv = self.vehicle['M-102 Gunner FRV']['mounts'][0]
        gater = self.vehicle['GATER Oil Rig']['mounts'][0]['current']['semanticId']
        self.assertEqual(frv['role'], 'gun')
        self.assertEqual(frv['current']['displayName'], 'frv_mg')
        self.assertIn(gater, frv['allowedReplacements'])
        self.assertNotIn(frv['current']['semanticId'], frv['allowedReplacements'])
        for replacement in frv['allowedReplacements']:
            self.assertEqual(weapons[replacement]['attackFamily'], 'projectile')
        field = self.field('vehicle', 'M-102 Gunner FRV', 'mount.weapon', mount='slot_0')
        self.assertEqual(field['evidence']['tier'], 'live_write_verified')
        self.assertEqual(field['acknowledgement'], 'allow_unverified_reference')
        self.assertEqual(self.field('vehicle', 'EXO-49 Emancipator Exosuit', 'mount.weapon', mount='slot_0')
            ['evidence']['tier'], 'structural_reference')
        blocked = {(item['name'], mount['mountId']) for item in self.vehicles['vehicles']
            for mount in item['mounts'] if not mount['swappable']}
        self.assertEqual(blocked, {('EXO-55 Breakthrough Exosuit', 'slot_0'), ('TD-110 Maelstrom', 'slot_1'),
            ('M-103 Supply FRV', 'slot_1'), ('M-104 Incinerator FRV', 'slot_1')})

    def test_backpack_fields_expose_only_proven_writes(self):
        jump = self.field('backpack', 'LIFT-850 Jump Pack', 'recharge.time')
        self.assertEqual((jump['currentDefault'], jump['editable'], jump['evidence']['tier']),
            (15.0, True, 'gameplay_proven'))
        launch = self.field('backpack', 'LIFT-850 Jump Pack', 'jump.vertical_launch_velocity')
        self.assertTrue(launch['editable'])
        hover = self.field('backpack', 'LIFT-860 Hover Pack', 'jump.vertical_launch_velocity')
        self.assertFalse(hover['editable'])
        self.assertIn('Hover Pack', hover['reason'])
        self.assertEqual(self.field('backpack', 'LIFT-860 Hover Pack', 'recharge.time')['evidence']['tier'],
            'schema_proven')
        for name, capacity in (('AX/AR-23 Guard Dog', 8), ('AX/LAS-5 Rover', 4), ('B-1 Supply Pack', 4)):
            deposit = self.field('backpack', name, 'deposit.capacity')
            self.assertEqual(deposit['currentDefault'], capacity)
            self.assertFalse(deposit['editable'])
        generator = self.field('backpack', 'SH-32 Shield Generator Pack', 'shield.durability')
        self.assertTrue(generator['editable'])
        self.assertEqual(generator['evidence']['tier'], 'schema_proven')
        self.assertFalse(self.backpack['LIFT-182 Warp Pack']['fieldInstanceKeys'])
        self.assertTrue(self.backpack['LIFT-182 Warp Pack']['blockedFields'])

    def test_shield_relay_separates_base_and_shield(self):
        relay = next(item for item in self.stratagems['stratagems'] if item['name'] == 'FX-12 Shield Generator Relay')
        shield = relay['deployedEntity']['shield']
        self.assertEqual(shield['runtimeShieldInstance'], 'unresolved')
        self.assertEqual(len(shield['fieldInstances']), 2)
        fields = {(item['target']['path'], item['semanticFieldId']): item for item in self.stratagems['fieldInstances']
            if item['target'].get('stratagem') == relay['name']}
        self.assertEqual(fields[('shield', 'shield.radius')]['currentDefault'], 15)
        self.assertEqual(fields[('shield', 'shield.durability')]['currentDefault'], 4000)
        self.assertEqual(fields[('deployed_entity', 'entity.health')]['currentDefault'], 450)
        self.assertEqual(fields[('deployed_entity', 'payload.lifetime')]['currentDefault'], 40)
        self.assertEqual(fields[('damage_zone', 'zone.health')]['currentDefault'], 450)
        self.assertNotEqual(fields[('shield', 'shield.radius')]['backingObjectId'],
            fields[('deployed_entity', 'entity.health')]['backingObjectId'])
        self.assertEqual(fields[('shield', 'shield.radius')]['apiFieldConstant'], 'hd2.fields.shield.entity_radius')
        self.assertEqual(relay['deployedEntity']['damageZones'][0]['name'], 'body_front')

    def test_lua_api_guards(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local plans=require('hd2runtime/domains/composition_plans')
assert(hd2.support_weapon and hd2.backpack and hd2.vehicle)
local bastion=hd2.vehicle('TD-220 Bastion MK XVI')
assert(#bastion:damage_zones()==31 and #bastion:mounts()==2)
assert(bastion:describe().semanticId:find('^vehicle/v1/'))
transactions.validate{id='main',target=bastion,changes={
 {field=hd2.fields.entity.health,expect=8000,value=16000},{field=hd2.fields.entity.armor,expect=4,value=5}}}
assert(not pcall(function()transactions.validate{id='span',target=bastion,changes={
 {field=hd2.fields.entity.health,expect=8000,value=16000},
 {field=hd2.fields.zone.armor,expect=4,value=5}}}end))
patches.validate{id='z',target=bastion:damage_zone('zone_3'),field=hd2.fields.zone.affects_main_health,expect=1,value=0}
assert(not pcall(function()patches.validate{id='z',target=bastion:damage_zone(3),
 field=hd2.fields.zone.affects_main_health,expect=0.5,value=0}end))
local legacy=hd2.vehicle('Bastion');assert(legacy.resource=='bastion')
local gun=hd2.vehicle('M-102 Gunner FRV'):mount('gun')
local gater=hd2.vehicle('GATER Oil Rig'):mount('turret'):current()
local swap={id='swap',target=gun,field=hd2.fields.mount.weapon,expect=gun:current(),value=gun:candidate(gater.semanticId)}
assert(not pcall(function()patches.validate(swap)end))
swap.allow_unverified_reference=true;patches.validate(swap)
assert(not pcall(function()patches.validate{id='raw',target=gun,field=hd2.fields.mount.weapon,
 expect=gun:current(),value='0x9872EEB31A5F88FD',allow_unverified_reference=true}end))
local flamer=hd2.vehicle('M-104 Incinerator FRV'):mount('gun'):current()
assert(not pcall(function()patches.validate{id='family',target=gun,field=hd2.fields.mount.weapon,
 expect=gun:current(),value=flamer,allow_unverified_reference=true}end))
assert(not pcall(function()hd2.vehicle('EXO-55 Breakthrough Exosuit'):mount('left_gun')end))
plans.validate{id='frv',operations={{id='gun',target=gun,allow_unverified_reference=true,
 field=hd2.fields.mount.weapon,expect=gun:current(),value=gater}}}
local jump=hd2.backpack('LIFT-850 Jump Pack')
assert(not pcall(function()transactions.validate{id='jp',target=jump,changes={
 {field=hd2.fields.recharge.time,expect=15,value=8},
 {field=hd2.fields.jump.vertical_launch_velocity,expect=40,value=50}}}end))
assert(not pcall(function()patches.validate{id='dep',target=hd2.backpack('AX/AR-23 Guard Dog'),
 field=hd2.fields.deposit.capacity,expect=8,value=16}end))
assert(not pcall(function()patches.validate{id='hover',target=hd2.backpack('LIFT-860 Hover Pack'),
 field=hd2.fields.jump.vertical_launch_velocity,expect=40,value=50}end))
patches.validate{id='gen',target=hd2.backpack('SH-32 Shield Generator Pack'),
 field=hd2.fields.shield.entity_durability,expect=150,value=300}
local relay=hd2.stratagem('FX-12 Shield Generator Relay'):deployed_entity()
assert(relay:describe().shield and #relay:damage_zones()==1)
transactions.validate{id='shield',target=relay:shield(),changes={
 {field=hd2.fields.shield.entity_radius,expect=15,value=8},
 {field=hd2.fields.shield.entity_durability,expect=4000,value=40000}}}
assert(not pcall(function()patches.validate{id='legacy-name',target=relay:shield(),
 field=hd2.fields.shield.radius,expect=15,value=8}end))
return 'ok'
''')

    def test_snapshot_and_reference_recreation_artifacts(self):
        entity = json.loads((ROOT / 'validation/entity-authoring-snapshot.json').read_text())
        self.assertEqual(entity['status'], 'VALIDATED')
        writable = self.vehicles['summary']['writableFieldInstances'] + self.backpacks['summary']['writableFieldInstances']
        self.assertEqual(entity['alreadyDesired'], writable)
        self.assertEqual(entity['mountCandidatesResolvedLive'],
            sum(len(mount['allowedReplacements']) for item in self.vehicles['vehicles'] for mount in item['mounts']))
        self.assertEqual((entity['researchWrites'], entity['protectionChanges']), (0, 0))
        stratagem = json.loads((ROOT / 'validation/stratagem-authoring-snapshot.json').read_text())
        self.assertEqual(stratagem['status'], 'VALIDATED')
        editable = [item for item in self.stratagems['fieldInstances'] if item['editable']]
        rearm = sum(item['target']['path'] == 'eagle_rearm' for item in editable)
        # The shared Eagle rearm definition is one physical value; the validator checks it once.
        self.assertEqual(stratagem['fieldInstances'], len(editable) - rearm + 1)
        recreations = json.loads((ROOT / 'validation/reference-mod-recreations.json').read_text())
        self.assertEqual(recreations['status'], 'EXACT_MATCH')
        self.assertEqual(set(recreations['recreations']), {'ShieldRelayRecreation', 'BastionReArmoredRecreation',
            'FRVWeaponSwapRecreation', 'JumpPackRecreation', 'ConcussiveDrumMagazine'})
        for name, item in recreations['recreations'].items():
            self.assertEqual(item['physicalWrites'], item['referenceWrites'], name)
            self.assertTrue(item['allAtVanillaBaseline'], name)
            self.assertTrue((ROOT / 'examples/projects' / name / 'src/addon.lua').exists())
        self.assertEqual(recreations['recreations']['BastionReArmoredRecreation']['physicalWrites'], 58)

    def test_reference_mod_evidence_is_pinned(self):
        mods = self.research['referenceMods']
        self.assertEqual(set(mods), {'ShieldRelayImprovements', 'BastionReArmored', 'FRVWeaponSwap',
            'JumpPackImprovements'})
        for item in mods.values():
            self.assertTrue(item['files'])
            for entry in item['files']:
                self.assertRegex(entry['sha256'], r'^[0-9A-F]{64}$')

    def test_release_freshness_catches_stale_entity_metadata(self):
        original = generate_entity_authoring.build

        def stale(*args, **kwargs):
            runtime, vehicles, backpacks = original(*args, **kwargs)
            vehicles['summary']['vehicles'] += 1
            return runtime, vehicles, backpacks
        with mock.patch.object(generate_entity_authoring, 'build', stale):
            with self.assertRaisesRegex(RuntimeError, 'Stale entity authoring'):
                generate_entity_authoring.generate(check=True)
        self.assertFalse(generate_stratagem_authoring.generate(check=True)[0])
        release = (ROOT / 'scripts/build_release.py').read_text()
        self.assertIn('generate_entity_authoring.generate(check=True)', release)
        self.assertIn('reference-mod-recreations.json', release)


if __name__ == '__main__':
    unittest.main()
