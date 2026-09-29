"""Attack-output composition: the native model, the active projectile source of every projectile weapon, the
family-aware catalog, the projectile-reference and ammunition APIs with typed handles, host eligibility and the
Liberator test mod.

A reference write landing correctly is not proof that a host fires it: the Liberator took a clean write of its
ProjectileWeapon +0 and kept firing its bullet (its default ammunition delta overwrites that member at weapon build),
while the same write works on the Reprimand. These tests therefore check that every writable projectile reference is
the host's established active source, not only that bytes change."""
import json
import re
import unittest

from support import ROOT, run


def load(relative):
    return json.loads((ROOT / relative).read_text())


class NativeModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = load('research/attack-outputs-F5FEE03DCFDB.json')

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
        for name in ('EAT-700 Napalm', 'Arc on impact'):
            self.assertIn('ammunition', cases[name]['writes'][0])
        subjects = self.research['subjects']
        liberator = subjects['AR-23 Liberator']
        self.assertTrue(liberator['projectileHost'])   # structural pre-filter only; see ActiveSourceTests
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


class ActiveSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = load('research/active-projectile-sources-F5FEE03DCFDB.json')
        cls.weapons = {w['weapon']: w for w in cls.research['weapons']}

    def test_live_controls(self):
        reprimand, liberator = self.weapons['SMG-32 Reprimand'], self.weapons['AR-23 Liberator']
        # Positive control: no customization patches a projectile member, so ProjectileWeapon +0 is fired.
        self.assertEqual((reprimand['status'], reprimand['baseMember']), ('ACTIVE_DIRECT', 'ACTIVE'))
        self.assertFalse([d for d in reprimand['defaultCustomization'] if d['projectilePatches']])
        self.assertFalse(reprimand['equippableProjectileOptions'])
        self.assertEqual(reprimand['liveControl']['result'], 'LIVE_PASS')
        # Negative control: the default ammunition delta overwrites +0 at weapon build; +0 is dormant.
        self.assertEqual((liberator['status'], liberator['baseMember']), ('INDIRECT', 'DORMANT'))
        self.assertEqual(liberator['liveControl']['result'], 'LIVE_FAIL')
        source = liberator['activeSource']
        self.assertEqual((source['kind'], source['item'], source['slot'], source['value']),
            ('ammunition_delta', 'RIFLE 5,5x50mm. FULL METAL JACKET', 6, 276))
        self.assertTrue(source['ownRow'] and source['baseAgrees'])
        self.assertEqual((source['defaultOf'], source['unlockListedBy']), (['AR-23 Liberator'], ['AR-23 Liberator']))
        # Alternate ammunition in the Liberator's unlock list: each patches +0 with its own projectile.
        alternates = {o['item']: o['projectilePatches'][0]['value'] for o in liberator['equippableProjectileOptions']}
        self.assertEqual(len(alternates), 10)
        self.assertEqual(alternates['RIFLE 5,5x50mm. PENETRATOR'], 7)
        self.assertTrue(all(o['projectilePatches'][0]['member'] == 'ProjType'
            for o in liberator['equippableProjectileOptions']))
        self.assertNotIn('Ammunition', liberator['armoryCategories'])

    def test_every_reachable_projectile_member_is_proven(self):
        members = self.research['projectileMembers']
        self.assertEqual(members['ProjectileWeaponComponentData']['offsets'], [0, 576])
        self.assertEqual(members['WeaponRoundsComponentData']['offsets'], [64, 68])
        self.assertEqual(members['WeaponMagazineComponentData']['arrays'], {'4': 32})
        self.assertEqual(members['WeaponChargeComponentData']['offsets'], [4, 28, 52])
        self.assertEqual(members['WeaponHeatComponentData']['offsets'], [4, 28, 52])

    def test_audit_counts(self):
        summary = self.research['summary']
        self.assertEqual(summary['projectileWeapons'], 89)
        self.assertEqual(summary['byStatus'], {'ACTIVE_DIRECT': 51, 'AMBIGUOUS': 3, 'BLOCKED': 29, 'INDIRECT': 6})
        self.assertEqual(summary['previousHosts'], 58)
        self.assertEqual(summary['previousHostsByStatus'],
            {'ACTIVE_DIRECT': 43, 'AMBIGUOUS': 3, 'BLOCKED': 6, 'INDIRECT': 6})
        self.assertEqual(summary['previouslyWritableAttackFieldsByStatus'],
            {'ACTIVE_DIRECT': 37, 'AMBIGUOUS': 9, 'BLOCKED': 6, 'INDIRECT': 5})
        self.assertEqual(summary['baseDisagreesWithActive'], ['P-19 Redeemer', 'P-2 Peacemaker'])
        self.assertEqual({w for w, e in self.weapons.items() if e['status'] == 'INDIRECT'},
            {'AR-23 Liberator', 'JAR-5 Dominator', 'P-19 Redeemer', 'P-2 Peacemaker', 'R-63 Diligence',
             'SG-225 Breaker'})

    def test_classification_rules(self):
        for weapon in self.research['weapons']:
            patched = [p for d in weapon['defaultCustomization'] for p in d['projectilePatches']]
            if weapon['status'] == 'ACTIVE_DIRECT':
                # Nothing overrides the member, nothing else selects a projectile.
                self.assertFalse(patched or weapon['equippableProjectileOptions'] or weapon['selectors'],
                    weapon['weapon'])
                self.assertEqual(weapon['base']['weaponFunctionProjectileType'], 0, weapon['weapon'])
            elif weapon['status'] == 'INDIRECT':
                source = weapon['activeSource']
                self.assertEqual([p['member'] for p in patched], ['ProjType'], weapon['weapon'])
                self.assertTrue(source['ownRow'] and source['slot'] == 6 and source['compatibilityClass'])
            elif weapon['status'] == 'BLOCKED':
                self.assertTrue(weapon['selectors'], weapon['weapon'])
        for row in self.research['attackFields']:
            if row['status'] == 'ACTIVE_DIRECT' and row['backing'].startswith('WeaponRounds'):
                # Rounds-backed members are direct only where nothing else carries a projectile.
                self.assertEqual(self.weapons[row['weapon']]['base']['projType'], 0, row['weapon'])


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load('sdk/AttackOutputCapabilities.json')
        cls.outputs = {o['owner']['name']: o for o in cls.catalog['outputs']}
        cls.player = load('sdk/PlayerWeaponAuthoringCapabilities.json')
        cls.active = load('research/active-projectile-sources-F5FEE03DCFDB.json')

    def test_catalog(self):
        summary = self.catalog['summary']
        self.assertEqual(summary['outputs'], 105)
        self.assertEqual(summary['byFamily'], {'projectile': 89, 'beam': 3, 'arc': 2, 'spray': 4, 'melee': 7})
        self.assertEqual((summary['selectable'], summary['projectileHosts'], summary['componentHosts'],
            summary['ammunitionHosts'], summary['directWritableAttackFields']), (66, 35, 29, 6, 37))
        self.assertNotRegex(json.dumps(self.catalog), r'0x[0-9A-Fa-f]{8}')
        for name in ('EAT-700 Expendable Napalm', 'GL-52 De-Escalator'):
            output = self.outputs[name]
            self.assertTrue(output['selectableAsProjectileReference'])
            self.assertEqual(output['ownerFiresThisProjectile'], 'fires_reference')
            self.assertEqual(output['requiredCoordinatedReferences'], [])
            self.assertTrue(output['package']['known'] and output['package']['autoLoad'])
            self.assertEqual(output['acknowledgements']['crossClass'],
                ['allow_unverified_reference', 'allow_unverified_effect'])
            # Live-proven as donors: the Liberator fired both through its ammunition source.
            self.assertEqual(output['liveProof'], {'donorOutput': 'live_proven', 'tests': ['LiberatorAttackOutputTest'],
                'provenOnHosts': ['AR-23 Liberator']})
        # The Talon output is live-proven as a donor (fired by the Reprimand); the Liberator failure is host-path
        # evidence and does not count against it.
        self.assertEqual(self.outputs['LAS-58 Talon']['liveProof'], {'donorOutput': 'live_proven',
            'tests': ['AssetTestReprimandTalonProjectile'], 'provenOnHosts': ['SMG-32 Reprimand']})
        for name, kind in (('LAS-98 Laser Cannon', 'continuous_beam'), ('LAS-13 Trident', 'pulsed_multi_beam'),
                ('ARC-3 Arc Thrower', 'arc')):
            output = self.outputs[name]
            self.assertEqual(output['kind'], kind)
            self.assertFalse(output['selectableAsProjectileReference'])
            self.assertIn('projectile host references only ProjectileType', output['blockedReason'])
        # An owner that fires through another selector does not offer its +0 row as its attack output.
        for name in ('P-92 Warrant', 'FAF-14 Spear', 'PLAS-101 Purifier', 'MG-43 Machine Gun'):
            self.assertEqual(self.outputs[name]['ownerFiresThisProjectile'], 'not_established', name)
            self.assertFalse(self.outputs[name]['selectableAsProjectileReference'], name)
        self.assertEqual(self.outputs['GL-52 De-Escalator']['kind'], 'arc_on_impact')
        self.assertTrue(self.outputs['GL-52 De-Escalator']['chain']['arcOnImpact'])
        self.assertTrue(self.outputs['EAT-700 Expendable Napalm']['chain']['submunition'])

    def test_hosts_are_the_active_source(self):
        hosts = self.catalog['hostModel']
        self.assertIn('SMG-32 Reprimand', hosts['componentHosts'])
        self.assertNotIn('AR-23 Liberator', hosts['componentHosts'])
        self.assertEqual(hosts['ammunitionHosts'], ['AR-23 Liberator', 'JAR-5 Dominator', 'P-19 Redeemer',
            'P-2 Peacemaker', 'R-63 Diligence', 'SG-225 Breaker'])
        sources = {(s['weapon'], s['attack']): s for s in self.catalog['projectileSources']}
        for name in hosts['componentHosts']:
            self.assertEqual((sources[(name, 'primary')]['status'], sources[(name, 'primary')]['mechanism']),
                ('ACTIVE_DIRECT', 'component'), name)
        for name in hosts['ammunitionHosts']:
            self.assertEqual((sources[(name, 'primary')]['status'], sources[(name, 'primary')]['mechanism']),
                ('INDIRECT', 'ammunition'), name)
        # No support weapon is a host: none has a guarded projectile reference target.
        kinds = {w['weapon']: w['kind'] for w in self.active['weapons']}
        self.assertTrue(all(kinds[n] == 'player_weapon' for n in hosts['componentHosts'] + hosts['ammunitionHosts']))
        live = hosts['hostLiveProof']
        self.assertEqual([r['result'] for r in live['SMG-32 Reprimand']], ['PASS', 'PASS'])
        liberator = {(r['result'], r['family'], r['superseded']) for r in live['AR-23 Liberator']}
        self.assertIn(('FAIL', 'weapon_projectile_reference_dormant_member', False), liberator)
        self.assertIn(('PASS', 'weapon_ammunition_projectile_reference', False), liberator)
        self.assertIn(('UNPROVEN', 'attack_output_cross_class', True), liberator)
        ammunition = {a['weapon']: a for a in self.catalog['ammunitionSources']}
        # Only the Liberator's own ammunition row is live-proven; the other INDIRECT weapons stay pending.
        self.assertEqual(ammunition['AR-23 Liberator']['acknowledgements'], ['allow_shared'])
        self.assertEqual(ammunition['AR-23 Liberator']['liveProof'], 'live_proven')
        for name in ('JAR-5 Dominator', 'P-19 Redeemer', 'P-2 Peacemaker', 'R-63 Diligence', 'SG-225 Breaker'):
            self.assertEqual((ammunition[name]['acknowledgements'], ammunition[name]['liveProof']),
                (['allow_shared', 'allow_unverified_effect'], 'pending'), name)
        self.assertEqual([(c['host'], c['output'], c['mechanism']) for c in self.catalog['provenCompositions']],
            [('AR-23 Liberator', 'output/v1/projectile/eat-700-expendable-napalm', 'ammunition'),
             ('AR-23 Liberator', 'output/v1/projectile/gl-52-de-escalator', 'ammunition')])
        self.assertEqual(ammunition['P-2 Peacemaker']['sharedWithWeapons'], ['MP-98 Knight', 'P-19 Redeemer'])

    def test_writable_projectile_fields_are_active_sources(self):
        """Writable means established as consumed, never merely that a projectile pointer exists."""
        sources = {(s['weapon'], s['attack']): s for s in self.catalog['projectileSources']}
        writable = 0
        for weapon in self.player['weapons']:
            for field in weapon['fields']:
                match = re.fullmatch(r'attack\.(\w+)\.projectile', field['semanticFieldId'])
                if not match:
                    continue
                source = sources[(weapon['name'], match.group(1))]
                self.assertEqual(field['projectileSource']['status'], source['status'])
                if field['editable']:
                    writable += 1
                    self.assertEqual(source['status'], 'ACTIVE_DIRECT', weapon['name'])
                    self.assertTrue(source['directWritable'])
                elif source['previouslyWritable']:
                    self.assertRegex(field['reason'], r'^(DORMANT_PROJECTILE_REFERENCE|UNPROVEN_PROJECTILE_SOURCE|'
                        r'PROJECTILE_SOURCE_BLOCKED): ', weapon['name'])
        self.assertEqual(writable, 37)
        self.assertEqual(self.player['summary']['composition']['projectile']['activeSourceWritableTargetAttacks'], 37)
        liberator = next(f for w in self.player['weapons'] if w['name'] == 'AR-23 Liberator' for f in w['fields']
            if f['semanticFieldId'] == 'attack.primary.projectile')
        self.assertFalse(liberator['editable'])
        self.assertIn('weapon:ammunition():projectile()', liberator['reason'])


class ApiTests(unittest.TestCase):
    def test_projectile_sources_and_ammunition(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
local liberator=hd2.weapon('AR-23 Liberator')
local attack=liberator:attack('primary')
local talon=hd2.weapon('LAS-58 Talon'):attack('primary'):projectile()
local eat=hd2.attack_output('EAT-700 Expendable Napalm')
-- The live-failed operation (old and new API alike) is refused: ProjectileWeapon +0 is dormant on the Liberator.
rejects(function()patches.validate{id='x',target=attack,field=hd2.fields.attack.projectile,expect=attack:projectile(),
 value=talon}end,'DORMANT_PROJECTILE_REFERENCE')
rejects(function()patches.validate{id='x',target=attack,field=hd2.fields.attack.projectile,expect=attack:projectile(),
 value=eat,allow_unverified_reference=true,allow_unverified_effect=true}end,'DORMANT_PROJECTILE_REFERENCE')
-- Its active source: the default ammunition.
local source=attack:projectile_source()
assert(source.status=='INDIRECT'and source.mechanism=='ammunition'and source.writable)
assert(source.field=='ammunition.projectile'and hd2.fields.ammunition.projectile=='ammunition.projectile')
assert(source.target.path=='ammunition'and source.expect.path=='ammunition_projectile')
assert(liberator:projectile_source().status=='INDIRECT')
assert(liberator:ammunition():describe().item=='RIFLE 5,5x50mm. FULL METAL JACKET')
local ammo=liberator:ammunition()
local function swap(value,extra)
 local request={id='a',target=ammo,field=hd2.fields.ammunition.projectile,expect=ammo:projectile(),value=value,
  allow_shared=true,allow_unverified_effect=true,allow_unverified_reference=true}
 for k,v in pairs(extra or{})do if v==false then request[k]=nil else request[k]=v end end
 return patches.validate(request)
end
local spec=swap(talon,{allow_unverified_reference=false})
assert(not spec.changes[1].cross_class and spec.asset_dependencies[1].name:find('laser_pistol',1,true))
spec=swap(eat)
assert(spec.changes[1].cross_class and spec.asset_dependencies[1].name:find('expendable_napalm_launcher',1,true))
swap(hd2.attack_output('GL-52 De-Escalator'))
assert(swap(ammo:projectile(),{allow_unverified_reference=false}).changes[1].self_reference)
rejects(function()swap(talon,{allow_shared=false})end,'allow_shared')
-- Live-proven scope: the Liberator's ammunition and its EAT-700 / GL-52 compositions need no acknowledgement.
swap(talon,{allow_unverified_effect=false,allow_unverified_reference=false})
swap(eat,{allow_unverified_effect=false,allow_unverified_reference=false})
swap(hd2.attack_output('GL-52 De-Escalator'),{allow_unverified_effect=false,allow_unverified_reference=false})
-- Anything outside it keeps both: another output on the Liberator, and another weapon's ammunition.
local eruptor=hd2.attack_output('R-36 Eruptor')
rejects(function()swap(eruptor,{allow_unverified_reference=false})end,'allow_unverified_reference')
rejects(function()swap(eruptor,{allow_unverified_effect=false})end,'allow_unverified_effect')
local breaker=hd2.weapon('SG-225 Breaker'):ammunition()
rejects(function()patches.validate{id='b',target=breaker,field=hd2.fields.ammunition.projectile,
 expect=breaker:projectile(),value=talon,allow_shared=true}end,'allow_unverified_effect')
for _,name in ipairs({'LAS-98 Laser Cannon','LAS-13 Trident','ARC-3 Arc Thrower'})do
 rejects(function()swap(hd2.attack_output(name))end,'INCOMPATIBLE_OUTPUT_FAMILY')
end
rejects(function()patches.validate{id='x',target=ammo,field=hd2.fields.ammunition.projectile,expect=attack:projectile(),
 value=talon,allow_shared=true,allow_unverified_effect=true}end,'expect must be the weapon ammunition')
transactions.validate{id='tx',target=ammo,allow_shared=true,allow_unverified_reference=true,allow_unverified_effect=true,
 changes={{field=hd2.fields.ammunition.projectile,expect=ammo:projectile(),value=eat}}}
-- The Reprimand (live PASS control) keeps its direct write, with the same donor handles as before.
local reprimand=hd2.weapon('SMG-32 Reprimand'):attack('primary')
local direct=reprimand:projectile_source()
assert(direct.status=='ACTIVE_DIRECT'and direct.mechanism=='component'and direct.field=='attack.projectile')
patches.validate{id='t',target=reprimand,field=hd2.fields.attack.projectile,expect=reprimand:projectile(),value=talon}
patches.validate{id='t2',target=reprimand,field=hd2.fields.attack.projectile,expect=reprimand:projectile(),
 value=hd2.attack_output('LAS-58 Talon')}
patches.validate{id='t3',target=reprimand,field=hd2.fields.attack.projectile,expect=reprimand:projectile(),value=eat,
 allow_unverified_reference=true,allow_unverified_effect=true}
rejects(function()patches.validate{id='x',target=reprimand,field=hd2.fields.attack.projectile,
 expect=reprimand:projectile(),value=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile()}end,
 'incompatible projectile reference class')
rejects(function()hd2.weapon('SMG-32 Reprimand'):ammunition()end,'NO_AMMUNITION_SOURCE')
-- A member whose consumption is not proven is not writable.
local evictor=hd2.weapon('GL-15 Evictor'):attack('primary')
assert(evictor:projectile_source().status=='AMBIGUOUS'and not evictor:projectile_source().writable)
rejects(function()patches.validate{id='x',target=evictor,field=hd2.fields.attack.projectile,
 expect=evictor:projectile(),value=evictor:projectile()}end,'UNPROVEN_PROJECTILE_SOURCE')
-- A weapon whose only projectile is its ammunition (no catalogued attack member).
assert(hd2.weapon('P-2 Peacemaker'):projectile_source().mechanism=='ammunition')
assert(#hd2.attack_outputs({selectable=true})==66)
return 'ok'
''')

    def test_choice_values_accept_reference_handles(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local ammo=hd2.weapon('AR-23 Liberator'):ammunition()
local page=hd2.options({id='attack_output_probe',title='Attack Output Probe'})
local choice=page:choice({id='output',label='Output',choices={'Vanilla','EAT-700'},
 values={ammo:projectile(),hd2.attack_output('EAT-700 Expendable Napalm')}})
assert(choice:get().path=='ammunition_projectile' and choice:samples()[2].resource=='attack_output')
local ok,why=pcall(function()page:choice({id='bad',label='Bad',choices={'A','B'},values={{},{}}})end)
assert(not ok and tostring(why):find('semantic reference handles',1,true),tostring(why))
return 'ok'
''')


class ValidationTests(unittest.TestCase):
    def test_snapshot_validation_record(self):
        record = load('validation/attack-output-snapshot.json')
        self.assertEqual(record['status'], 'VALIDATED')
        self.assertIn('not these bytes', record['proofScope'])
        controls = record['controls']
        self.assertEqual((controls['SMG-32 Reprimand']['status'], controls['SMG-32 Reprimand']['written'],
            controls['SMG-32 Reprimand']['to']), ('ACTIVE_DIRECT', 'ProjectileWeapon +0', 144))
        self.assertEqual((controls['AR-23 Liberator']['status'], controls['AR-23 Liberator']['baseline']),
            ('INDIRECT', 276))
        compositions = record['compositions']
        self.assertEqual({k: (v['projectile'], v['crossClass'], v['target'], v['dormantMemberUnchanged'])
            for k, v in compositions.items()},
            {'EAT-700 Expendable Napalm': (259, True, 'ammunition', True),
             'GL-52 De-Escalator': (222, True, 'ammunition', True),
             'LAS-58 Talon': (144, False, 'ammunition', True)})
        self.assertTrue(compositions['EAT-700 Expendable Napalm']['package'].endswith('expendable_napalm_launcher'))
        rejections = record['rejections']
        for name in ('LAS-98 Laser Cannon', 'LAS-13 Trident', 'ARC-3 Arc Thrower'):
            self.assertEqual(rejections[name], 'INCOMPATIBLE_OUTPUT_FAMILY')
        self.assertEqual(rejections['dormantMember'], 'DORMANT_PROJECTILE_REFERENCE')
        self.assertEqual((rejections['acknowledgements'], rejections['staleSource'], rejections['hostMagazinePattern'],
            rejections['staleDefaultAmmunition'], rejections['noAmmunitionSource']), (4, 1, 1, 1, 'SMG-32 Reprimand'))
        self.assertEqual(record['provenWithoutAcknowledgement'],
            ['LAS-58 Talon', 'EAT-700 Expendable Napalm', 'GL-52 De-Escalator'])

    def test_packaged_scenarios(self):
        import validate_packaged_runtime as packaged
        extra = packaged.EXTRAS['example-liberator-attack-output-test']
        self.assertEqual(extra['packageRequests'], 3)
        steps = re.findall(r"choose\((\d),'([^']+)',(\d)\)", extra['after'])
        self.assertEqual([int(s[0]) for s in steps], [2, 3, 4, 1, 4, 3])   # Talon, EAT, Arc, Vanilla, Arc, EAT
        self.assertIn('restores the exact ammunition baseline', extra['after'])
        # Direct source (Reprimand), dormant member refused and active source written (Liberator).
        self.assertIn('example-asset-test-reprimand-talon-projectile', packaged.EXTRAS)
        fixture = packaged.PROJECTILE_SOURCES
        self.assertIn('DORMANT_PROJECTILE_REFERENCE', fixture)
        self.assertIn("reprimand.status=='ACTIVE_DIRECT'", fixture)
        self.assertIn('hd2.fields.ammunition.projectile', fixture)
        self.assertEqual(packaged.EXTRAS['projectile-active-sources']['packageRequests'], 1)

    def test_migration_normalizes_output_and_ammunition_sources(self):
        from migration import source
        output = {'id': 'output/v1/projectile/x', 'family': 'projectile', 'owner': {'kind': 'support_weapon',
            'name': 'X'}, 'resource': '0x5', 'backing': {'kind': 'component', 'component': 'ProjectileWeaponComponentData',
            'offset': 0, 'storage': 'u32', 'width': 4, 'recordIndex': 3, 'indexRow': 4, 'ownerCount': 1},
            'currentDefault': 259, 'editable': True}
        tables = {'attack_outputs': {'outputs': {output['id']: output}}}
        [record] = source.normalize(tables)
        self.assertEqual((record['domain'], record['key'], record['backing']['recordIndex'], record['baseline']),
            ('attack_outputs', 'output:output/v1/projectile/x', 3, 259))
        self.assertEqual(record['locator'], {'path': ['outputs', output['id']], 'guard': {'id': output['id']}})
        ammunition = {'id': 'ammunition/v1/w/a', 'weapon': 'W', 'resource': '0x7', 'component': 321,
            'componentOffset': 0, 'dataOffset': 100, 'currentDefault': {'weapon': 'W', 'projectileType': 276},
            'editable': True, 'backing': {'kind': 'entity_delta', 'component': 'ProjectileWeaponComponentData'},
            'defaultCustomization': {'offset': 32, 'slot': 6, 'optionId': 99}}
        tables = {'attack_outputs': {'ammunition': {'W': ammunition}},
            'player_weapon_authoring': {'weapons': {'W': {'resources': ['0x9']}}}}
        [record] = source.normalize(tables)
        self.assertEqual((record['key'], record['backing']['kind'], record['backing']['dataOffset'],
            record['backing']['componentIndex'], record['baseline'], record['shared']),
            ('ammunition:W', 'delta', 100, 321, 276, True))
        self.assertEqual(record['locator'], {'path': ['ammunition', 'W'], 'guard': {'id': 'ammunition/v1/w/a'}})
        [link] = [l for l in source.relationships(tables) if l['key'] == 'ammunition-default:W']
        self.assertEqual((link['kind'], link['component'], link['offset'], link['expect'], link['blocks']),
            ('component_value', 'WeaponCustomizationComponentData', 36, 99, [['attack_outputs', 'W']]))

    def test_test_mod(self):
        addon = (ROOT / 'examples/projects/LiberatorAttackOutputTest/src/addon.lua').read_text()
        self.assertIn("choices={'Vanilla','LAS-58 Talon (control)','EAT-700 Napalm','GL-52 Arc (impact)'}", addon)
        self.assertIn('hd2.fields.ammunition.projectile', addon)
        self.assertNotIn('hd2.fields.attack.projectile', addon)
        for flag in ('allow_shared=true', 'allow_unverified_reference=true', 'allow_unverified_effect=true'):
            self.assertIn(flag, addon)
        self.assertNotRegex(addon, r"attack_output\('(LAS-98|LAS-13|ARC-3)")
        manifest = load('examples/projects/LiberatorAttackOutputTest/hd2runtime.json')
        self.assertIn('mod_options_menu', manifest['optional'])


if __name__ == '__main__':
    unittest.main()
