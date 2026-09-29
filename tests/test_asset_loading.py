import importlib.util
import json
import re
import unittest

from support import ROOT, run


spec = importlib.util.spec_from_file_location('generate_package_residency',
    ROOT / 'scripts/generate_package_residency.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)

ASSET_EXAMPLES = ('AssetTestStalwartPodEat700', 'AssetTestReprimandTalonProjectile', 'AssetTestFrvBastionCannon',
    'AssetTestMg43PodGrenadeBox')


class AssetLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = json.loads((ROOT / 'research/package-residency-F5FEE03DCFDB.json').read_text())
        cls.public = json.loads((ROOT / 'sdk/AssetDependencyCapabilities.json').read_text())

    def test_generated_outputs_are_fresh(self):
        self.assertFalse(generator.generate(check=True))

    def test_residency_model_evidence(self):
        # Every snapshot: the reference-counted loadout packages are the equipped loadout, and all resident
        # except the armory preview captured mid-load.
        evidence = {e['snapshot']: e for e in self.research['snapshotEvidence']}
        self.assertEqual(len(evidence), 3)
        mid_load = evidence['F5FEE03DCFDB-20260927T155654Z.hd2snap']
        self.assertIn('packages/generated/loadout/marksman_rifle', mid_load['requestedNotYetResident'])
        self.assertFalse(mid_load['everyRefcountedLoadoutPackageResident'])
        for name, item in evidence.items():
            if name != 'F5FEE03DCFDB-20260927T155654Z.hd2snap':
                self.assertTrue(item['everyRefcountedLoadoutPackageResident'], name)
                self.assertEqual(item['refcountedLoadoutPackages'], item['residentLoadoutPackages'], name)
        phases = self.research['logEvidence']['loadoutPackagesRequestedByPhase']
        self.assertIn('lmg_stalwart', phases['prepare_mission'])
        loader = self.research['loader']['gameDll']
        self.assertEqual((loader['engineLoadSlot'], loader['engineUnloadSlot']), (0x2f0, 0x300))
        self.assertGreaterEqual(loader['callSites'], 40)

    def test_anchor_dependencies(self):
        catalog = self.research['catalog']
        expected = {
            'support_weapon/EAT-700 Expendable Napalm': 'expendable_napalm_launcher',
            'player_weapon/LAS-58 Talon': 'laser_pistol',
            'player_weapon/SMG-32 Reprimand': 'smg_rhino',
            'support_weapon/M-105 Stalwart': 'lmg_stalwart',
            'vehicle/TD-220 Bastion MK XVI': 'tank',
            'pickup/pickup/v1/grenade-box/5ad3b36a5d3adbb7': 'grenade_box',
        }
        for key, package in expected.items():
            dependency = catalog[key]['dependency']
            self.assertEqual(dependency['name'], 'packages/generated/loadout/' + package, key)
            self.assertTrue(dependency['inBundleDatabase'], key)
        summary = self.research['summary']
        self.assertEqual(summary['known'] + summary['unknown'], summary['semanticObjects'])
        self.assertEqual(summary['known'], summary['ownPackage'] + summary['holderPackage'] + summary['stratagemPackage'])
        # Objects without a structural package owner stay unknown (never inferred).
        self.assertFalse(catalog['pickup/pickup/v1/supply-box/d0e8fed8c01ceb1f']['known'])

    def test_public_metadata_has_no_identifiers(self):
        self.assertEqual(self.public['contract'], 'hd2runtime.asset_dependencies.v1')
        self.assertNotRegex(json.dumps(self.public).lower(), re.compile(r'0x[0-9a-f]{8,}'))
        for item in self.public['objects']:
            dependency = item['packageDependency']
            self.assertEqual(set(dependency), {'known', 'autoLoadSupported', 'derivation', 'package', 'packageNamed',
                'liveTested', 'packageLiveLoaded', 'blocker'})
            self.assertEqual(dependency['known'], dependency['blocker'] is None)
            if dependency['liveTested']:
                self.assertTrue(dependency['packageLiveLoaded'])
        metadata = json.loads((ROOT / 'sdk/metadata.json').read_text())
        functions = metadata['api']['functions']
        self.assertIn('require_assets', functions)
        self.assertIn('asset_dependency', functions)
        self.assertFalse([name for name in functions if 'package' in name])
        stub = (ROOT / 'sdk/stubs/mods/skyeshade/hd2runtime.lua').read_text()
        self.assertIn('function hd2.require_assets(request) end', stub)
        self.assertNotIn('load_package', (ROOT / 'api/hd2.lua').read_text())

    def test_live_evidence(self):
        live = json.loads((ROOT / 'research/package-residency-live-evidence.json').read_text())
        results = {t['id']: (t['family'], t['result'], t['donorCarried']) for t in live['tests']}
        self.assertEqual(results, {'A': ('pod_payload_pickup', 'PASS', False),
            'B': ('projectile_reference', 'PASS', False), 'C': ('vehicle_mount', 'INCONCLUSIVE', False),
            'D': ('pod_payload_pickup', 'PASS', False)})
        catalog = self.research['catalog']
        for test in live['tests']:
            for key in test['objects']:
                self.assertTrue(catalog[key]['known'], key)
        families = self.public['referenceFamilies']
        self.assertEqual({k: v['packageResidency'] for k, v in families.items()}, {
            'pod_payload_pickup': 'LIVE_PROVEN', 'projectile_reference': 'LIVE_PROVEN',
            'explosion_reference': 'OFFLINE_PROVEN', 'vehicle_mount': 'OFFLINE_PROVEN'})
        objects = {o['key']: o['packageDependency'] for o in self.public['objects']}
        self.assertEqual(sorted(k for k, v in objects.items() if v['liveTested']), [
            'pickup/pickup/v1/eat-700-expendable-napalm/bff4b15f31d35c94',
            'pickup/pickup/v1/grenade-box/5ad3b36a5d3adbb7', 'player_weapon/LAS-58 Talon'])
        self.assertTrue(objects['support_weapon/EAT-700 Expendable Napalm']['packageLiveLoaded'])
        self.assertFalse(objects['support_weapon/EAT-700 Expendable Napalm']['liveTested'])
        bastion = 'mounted_weapon/mounted-weapon/v1/td-220-bastion-mk-xvi-attach-tank-gun-weapon/e90a7fd19ec0d437'
        self.assertFalse(objects[bastion]['liveTested'])
        self.assertEqual(self.public['summary']['liveProvenFamilies'], ['pod_payload_pickup', 'projectile_reference'])

    def test_residency_separated_from_compatibility(self):
        pods = json.loads((ROOT / 'sdk/PodPayloadCapabilities.json').read_text())
        pickups = {p['name']: p for p in pods['pickups']}
        self.assertEqual(pickups['EAT-700 Expendable Napalm']['packageDependency']['packageResidency'], 'LIVE_PROVEN')
        self.assertEqual(pickups['Supply Box']['packageDependency']['packageResidency'], 'ALWAYS_RESIDENT')
        self.assertEqual(pickups['Health Pack (pod)']['packageDependency']['packageResidency'], 'UNRESOLVED')
        # slot compatibility is untouched: the acknowledgement is still published for every authored slot
        self.assertEqual(pickups['Grenade Box']['compatibility'], 'UNVERIFIED_REFERENCE')
        for rack in pods['racks']:
            for slot in rack['slots']:
                if slot.get('writable'):
                    self.assertIn('allow_unverified_reference', slot['acknowledgements'])
        self.assertEqual({(p['rack'], p['slot'], p['pickup']) for p in pods['liveVerifiedPairs']},
            {('M-105 Stalwart pod', 2, 'EAT-700 Expendable Napalm'), ('MG-43 Machine Gun pod', 1, 'Grenade Box')})
        projectiles = json.loads((ROOT / 'sdk/ProjectileCompositionCapabilities.json').read_text())
        residency = {w['weapon']: a['residency'] for w in projectiles['weapons'] for a in w['attacks']}
        talon = residency['LAS-58 Talon']
        self.assertEqual((talon['classification'], talon['package'], talon['liveTested'],
            talon['observedWithoutLoader']), ('PACKAGE_AUTO_LOADED', 'laser_pistol', True, 'SOURCE_WEAPON_REQUIRED'))
        self.assertEqual(residency['GP-31 Grenade Pistol']['classification'], 'DEPENDENCY_UNRESOLVED')
        policy = projectiles['residencyPolicy']
        self.assertTrue(policy['automaticPackageLoading'])
        attacks = sum(len(w['attacks']) for w in projectiles['weapons'])
        self.assertEqual(policy['autoLoadedSources'] + policy['unknownSourcesRemain'], attacks)
        self.assertNotIn('No reviewed Bingus', json.dumps(projectiles))
        vehicles = (ROOT / 'sdk/VehicleAuthoringCapabilities.json').read_text()
        self.assertNotIn('it does not load packages', vehicles)
        self.assertIn('Mount compatibility is separate and unverified', vehicles)
        spec_ = importlib.util.spec_from_file_location('apply_projectile_residency',
            ROOT / 'scripts/apply_projectile_residency.py')
        module = importlib.util.module_from_spec(spec_)
        spec_.loader.exec_module(module)
        self.assertFalse(module.generate(check=True))

    def test_snapshot_validation(self):
        result = json.loads((ROOT / 'validation/asset-residency-snapshot.json').read_text())
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertEqual((result['writes'], result['nativeCalls']), (0, 0))
        self.assertEqual(len(result['snapshots']), 3)
        for snapshot in result['snapshots']:
            self.assertEqual(snapshot['status'], 'VALIDATED')
            self.assertTrue(snapshot['proven'])
            self.assertEqual(snapshot['dedupedNativeRequests'], 1)
            self.assertEqual(snapshot['budget'], 64)
            self.assertEqual(snapshot['states']['0x5D68E55823ACD1BF'], 'absent')
            self.assertIn('ASSET_UNAVAILABLE', snapshot['timeoutReason'])
            self.assertEqual(set(snapshot['rejections']), {'changed request code byte',
                'changed engine has_loaded byte', 'wrong build', 'uncatalogued package',
                'runtime without native package loading', 'session package budget'})

    def test_operations_carry_dependencies(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local assets=require('hd2runtime/core/assets')
local function one(spec,package)
 local found=assets.collect(spec)
 assert(#found==1,'expected one dependency, got '..#found)
 assert(found[1].name=='packages/generated/loadout/'..package,found[1].name)
end
-- A: pod slot -> EAT-700
local rack=hd2.pod_rack('M-105 Stalwart pod')
one(patches.validate{id='a',target=rack:slot(2),field=hd2.fields.payload.entity,expect=rack:slot(2):current(),
 value=hd2.pickup('EAT-700 Expendable Napalm'),allow_unverified_reference=true},'expendable_napalm_launcher')
-- the acknowledgement is still required (reference semantics remain unverified)
local ok,why=pcall(patches.validate,{id='a2',target=rack:slot(2),field=hd2.fields.payload.entity,
 expect=rack:slot(2):current(),value=hd2.pickup('EAT-700 Expendable Napalm')})
assert(not ok and tostring(why):find('allow_unverified_reference',1,true),tostring(why))
-- restoring the vanilla occupant needs nothing
local vanilla=patches.validate{id='a3',target=rack:slot(1),field=hd2.fields.payload.entity,
 expect=rack:slot(1):current(),value=rack:slot(1):current()}
assert(#assets.collect(vanilla)==0)
-- B: Reprimand <- Talon projectile
local target=hd2.weapon('SMG-32 Reprimand'):attack('primary')
one(patches.validate{id='b',target=target,field=hd2.fields.attack.projectile,expect=target:projectile(),
 value=hd2.weapon('LAS-58 Talon'):attack('primary'):projectile()},'laser_pistol')
-- C: FRV gun <- Bastion cannon
local gun=hd2.vehicle('M-102 Gunner FRV'):mount('slot_0')
local cannon=hd2.vehicle('TD-220 Bastion MK XVI'):mount('slot_0'):current()
local c=patches.validate{id='c',target=gun,field=hd2.fields.mount.weapon,expect=gun:current(),
 value=gun:candidate(cannon.semanticId),allow_unverified_reference=true}
assert(#assets.collect(c)==1)
-- D: MG-43 pod <- Grenade Box
local mg=hd2.pod_rack('MG-43 Machine Gun pod')
one(patches.validate{id='d',target=mg:slot(1),field=hd2.fields.payload.entity,expect=mg:slot(1):current(),
 value=hd2.pickup('Grenade Box'),allow_unverified_reference=true,allow_shared=true},'grenade_box')
return 'ok'
''')

    def test_source_weapon_required_without_package_stays_rejected(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local assets=require('hd2runtime/core/assets')
local original=assets.dependency
assets.dependency=function()return nil end
local target=hd2.weapon('SMG-32 Reprimand'):attack('primary')
local ok,why=pcall(patches.validate,{id='b',target=target,field=hd2.fields.attack.projectile,
 expect=target:projectile(),value=hd2.weapon('LAS-58 Talon'):attack('primary'):projectile()})
assets.dependency=original
assert(not ok and tostring(why):find('not resident',1,true),tostring(why))
return 'ok'
''')

    def test_semantic_api(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local api=require('hd2runtime/api/assets')
local assets=require('hd2runtime/core/assets')
local eat=hd2.asset_dependency(hd2.pickup('EAT-700 Expendable Napalm'))
assert(eat.known and eat.autoLoadSupported and eat.package=='expendable_napalm_launcher' and eat.retain=='session')
assert(not tostring(eat.package):find('0x',1,true))
local talon=hd2.asset_dependency(hd2.weapon('LAS-58 Talon'))
assert(talon.known and talon.package=='laser_pistol')
assert(eat.liveTested==true and talon.liveTested==true)
assert(hd2.asset_dependency(hd2.support_weapon('EAT-700 Expendable Napalm')).liveTested==false)
-- a package proven by identity but without a recovered name: known, no name published, never crashes
local rover=hd2.asset_dependency(hd2.backpack('AX/LAS-5 Rover'))
assert(rover.known and rover.package==nil,tostring(rover.package))
local rover_dependency=assets.dependency(rover.key)
assert(type(rover_dependency.name)=='string'and rover_dependency.name:find('unnamed loadout package',1,true))
local supply=hd2.asset_dependency(hd2.pickup('Supply Box'))
assert(not supply.known and not supply.autoLoadSupported and supply.blocker)
assert(not hd2.asset_dependency({resource='package',id='0x5D68E55823ACD1BF'}).known)
-- require_assets takes typed handles only, validates its request, and never accepts unknown objects
local function rejects(request,needle)
 local ok,why=pcall(api.start,{mode='test'},function()end,request)
 assert(not ok and tostring(why):find(needle,1,true),tostring(why))
end
rejects({id='x',target={resource='package',id='0x5D68E55823ACD1BF'}},'no asset catalog entry')
rejects({id='x',target=hd2.pickup('Supply Box')},'ASSET_UNAVAILABLE')
rejects({id='x',target=hd2.pickup('Grenade Box'),package='0x5D68E55823ACD1BF'},'unsupported require_assets option')
rejects({id='bad id!',target=hd2.pickup('Grenade Box')},'valid id')
-- simulated loader: waiting_for_assets -> complete, one native request per package
assets.reset()
local calls,loaded=0,false
local runtime={mode='simulated',package_state=function()return loaded and'resident'or'queued'end}
local original=assets.prove
assets.prove=function()return {instance=1,request=2,capacity=1024}end
runtime.package_request=function()calls=calls+1 end
runtime.read=function(at,n)return string.rep('\0',n)end
local watch=api.start(runtime,function()end,{id='warm',targets={hd2.pickup('EAT-700 Expendable Napalm'),
 hd2.support_weapon('EAT-700 Expendable Napalm')}})
watch.tick(0.3);assert(watch.status=='waiting_for_assets')
loaded=true;watch.tick(0.3)
assert(watch.status=='complete'and watch.result.status=='RESIDENT'and calls==1,watch.status..' '..calls)
-- cancellation drops bookkeeping only
local second=api.start(runtime,function()end,{id='cancel',target=hd2.pickup('EAT-700 Expendable Napalm')})
second.cancel();assert(second.status=='cancelled')
local held=assets.holdings();assert(#held==1 and held[1].retained and calls==1)
assets.prove=original;assets.reset()
-- id_bytes: little-endian, exact 64-bit
assert(assets.id_bytes('0x5D68E55823ACD1BF')=='\191\209\172\35\88\229\104\93')
assert(not pcall(assets.id_bytes,'0x1234'))
return 'ok'
''')

    def test_examples_use_the_typed_api(self):
        for name in ASSET_EXAMPLES:
            source = (ROOT / 'examples/projects' / name / 'src/addon.lua').read_text()
            self.assertNotRegex(source.lower(), re.compile(r'0x[0-9a-f]{6,}'), name)
            self.assertNotRegex(source, re.compile(r'(load|require)_package|package\s*='), name)
            self.assertIn('hd2.ensure', source, name)
            self.assertIn(name, (ROOT / 'validation/example-projects.json').read_text())

    def test_docs_and_release_wiring(self):
        docs = (ROOT / 'docs/asset-loading.md').read_text(encoding='utf-8')
        for needle in ('ASSET_UNAVAILABLE', 'waiting_for_assets', 'allow_unverified_reference', 'Multiplayer',
                       'Live results', 'Live-proven', 'not required for 0.27.0'):
            self.assertIn(needle, docs)
        self.assertEqual((ROOT / 'sdk/docs/asset-loading.md').read_text(encoding='utf-8'), docs)
        self.assertIn('generate_package_residency', (ROOT / 'scripts/regenerate_domains.py').read_text())
        self.assertIn('asset_residency_snapshot_validation', (ROOT / 'scripts/build_release.py').read_text())


if __name__ == '__main__':
    unittest.main()
