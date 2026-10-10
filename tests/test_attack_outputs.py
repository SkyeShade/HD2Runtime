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
        # 89 player and support projectile weapons plus 17 mounted ones (vehicles, Exosuits, emplacements, drones).
        self.assertEqual(summary['projectileWeapons'], 106)
        self.assertEqual(sum(1 for e in self.weapons.values() if e['kind'] == 'vehicle_weapon'), 17)
        self.assertEqual(summary['byStatus'], {'ACTIVE_DIRECT': 60, 'AMBIGUOUS': 5, 'BLOCKED': 35, 'INDIRECT': 6})
        self.assertEqual(summary['previousHosts'], 72)
        self.assertEqual(summary['previousHostsByStatus'],
            {'ACTIVE_DIRECT': 52, 'AMBIGUOUS': 5, 'BLOCKED': 9, 'INDIRECT': 6})
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
        # By owner: each owner's own output (the more projectile donors, kind projectile_donor, share their owners'
        # names and are covered by tests/test_projectile_donors.py).
        cls.outputs = {o['owner']['name']: o for o in cls.catalog['outputs'] if o.get('kind') != 'projectile_donor'}
        cls.player = load('sdk/PlayerWeaponAuthoringCapabilities.json')
        cls.active = load('research/active-projectile-sources-F5FEE03DCFDB.json')

    def test_catalog(self):
        summary = self.catalog['summary']
        # 107 player, support and stratagem outputs plus the 23 mounted-weapon outputs, and the 32 more projectile
        # donors (research/projectile-donors-F5FEE03DCFDB.json, tests/test_projectile_donors.py).
        # 0.31.0 (research/beam-outputs): beam 4 -> 12: the six beam donors (Scythe, Dagger, Trident, LAS-98, 40-K, Laser
        # Sentry), the Rover drone gun and five enemy beams listed read-only (tests/test_beam_swaps.py).
        self.assertEqual(summary['outputs'], 169)   # the retired Defender donor (projectile 150)
        self.assertEqual(summary['byFamily'], {'projectile': 139, 'beam': 12, 'arc': 3, 'spray': 8, 'melee': 7})   # the retired Defender donor
        self.assertEqual(len(summary['stratagemDonors']), 23)
        self.assertIn('A/M-23 EMS Mortar Sentry', summary['stratagemDonors'])
        self.assertIn('Eagle 500kg Bomb', summary['stratagemDonors'])
        self.assertEqual((summary['selectable'], summary['projectileHosts'], summary['componentHosts'],
            summary['ammunitionHosts'], summary['directWritableAttackFields']), (111, 59, 53, 6, 61))   # +7 sentry hosts; -1 the retired Defender donor
        # Every selectable projectile output carries its weapon-function mode label and icon (native values only).
        presentation = self.catalog['modePresentation']
        icons = {i['value']: i for i in presentation['icons']}
        self.assertIn('ammo_stun', icons)
        self.assertEqual(presentation['genericFallbackIcon'], 'ammo_slug')
        self.assertTrue(icons['ammo_slug']['genericFallback'] and icons['auto']['source'] == 'auto')
        by_label = {l['value']: l for l in presentation['labels']}
        self.assertEqual((by_label['gas']['icon'], by_label['gas']['iconSource']), ('ammo_slug', 'generic_fallback'))
        self.assertEqual((by_label['stun']['icon'], by_label['stun']['iconSource']), ('ammo_stun', 'exact_native'))
        self.assertTrue({'none', 'gas', 'stun', 'flak', 'he'} <= {l['value'] for l in presentation['labels']})
        self.assertEqual(sum(1 for o in self.catalog['outputs'] if o.get('presentation')), 80)
        self.assertEqual(self.outputs['AC-8 Autocannon']['presentation']['label'], 'aphet')
        self.assertTrue(self.outputs['AC-8 Autocannon']['presentation']['shared'])
        self.assertEqual((self.outputs['S-11 Speargun']['presentation']['label'],
            self.outputs['S-11 Speargun']['presentation']['icon']), ('none', 'default'))
        self.assertNotRegex(json.dumps(self.catalog), r'0x[0-9A-Fa-f]{8}')
        # The EAT-700 also worked as the Reprimand's donor (UnifiedProjectileSwapTest, 2026-09-30).
        live_hosts = {'EAT-700 Expendable Napalm': (['LiberatorAttackOutputTest', 'UnifiedProjectileSwapTest'],
                ['AR-23 Liberator', 'SMG-32 Reprimand']),
            # The GL-52 also worked as the Speargun's function projectile (its donor output; that run is partial
            # because the GL-52 is not a stun field, not because the donor failed).
            'GL-52 De-Escalator': (['LiberatorAttackOutputTest', 'SpeargunGasStunTest'],
                ['AR-23 Liberator', 'S-11 Speargun'])}
        for name in ('EAT-700 Expendable Napalm', 'GL-52 De-Escalator'):
            output = self.outputs[name]
            self.assertTrue(output['selectableAsProjectileReference'])
            self.assertEqual(output['ownerFiresThisProjectile'], 'fires_reference')
            self.assertEqual(output['requiredCoordinatedReferences'], [])
            self.assertTrue(output['package']['known'] and output['package']['autoLoad'])
            self.assertEqual(output['acknowledgements']['crossClass'],
                ['allow_unverified_reference', 'allow_unverified_effect'])
            # Live-proven as donors: the Liberator fired both through its ammunition source.
            self.assertEqual(output['liveProof'], {'donorOutput': 'live_proven', 'tests': live_hosts[name][0],
                'provenOnHosts': live_hosts[name][1]})
        # The Talon output is live-proven as a donor (fired by the Reprimand); the Liberator failure is host-path
        # evidence and does not count against it.
        # UnifiedProjectileSwapTest (2026-09-30) fired it from the Liberator's ammunition too, and
        # VehicleProjectileBuilderTest (2026-09-30) from the Patriot minigun.
        self.assertEqual(self.outputs['LAS-58 Talon']['liveProof'], {'donorOutput': 'live_proven',
            'tests': ['AssetTestReprimandTalonProjectile', 'UnifiedProjectileSwapTest', 'VehicleProjectileBuilderTest'],
            'provenOnHosts': ['AR-23 Liberator', 'EXO-45 Patriot Exosuit / right_gun', 'SMG-32 Reprimand']})
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

    def test_projectile_builder_metadata(self):
        builder = self.catalog['projectileBuilder']
        self.assertEqual({k: v['supported'] for k, v in builder['classes'].items()},
            {'REFERENCE_COMPOSITION': True, 'DERIVED_MUTATION': 'spare_twins_only', 'CUSTOM_ROW': False})
        self.assertEqual(builder['rows'], {'total': 350, 'referenced': 288, 'unreferenced': 62})
        self.assertEqual(builder['spareTwins'], [{'output': 'output/v1/projectile/s-11-speargun-spare-twin',
            'twinOf': 'output/v1/projectile/s-11-speargun', 'borrowedVanillaRow': True, 'interim': True,
            'differingReferences': ['expiryExplosion']}])
        # A spare twin borrows a vanilla row: an interim, never presented as the end state.
        self.assertTrue(builder['classes']['DERIVED_MUTATION']['interim'])
        self.assertIn('Runtime-owned registry', builder['classes']['CUSTOM_ROW']['reason'])
        self.assertEqual([slot['key'] for slot in builder['slots']], ['directDamage', 'impactExplosion', 'expiryExplosion'])
        self.assertIn('RECURSIVE_COMPOSITION', builder['guards']['recursion'])
        self.assertIn('ASSET_UNAVAILABLE', builder['guards']['package'])
        self.assertIn('never adds', builder['api']['acknowledgements'])
        self.assertEqual(len(builder['unprovenMembers']), 2)
        spare = self.outputs['S-11 Speargun (spare twin)']
        self.assertEqual((spare['kind'], spare['referenceScope'], spare['spareTwin']['consumers']),
            ('spare_twin', ['function_ammo.projectile'], 0))
        self.assertTrue(spare['spareTwin']['buildScoped'] and spare['spareTwin']['borrowedVanillaRow'])
        self.assertIn('SPARE_TWIN_UNVERIFIED_BUILD', builder['guards']['spareTwin'])
        self.assertFalse(spare['slots']['expiryExplosion']['shared'])
        hmg = self.outputs['MG-206 Heavy Machine Gun']['slots']['directDamage']
        self.assertEqual((hmg['shared'], hmg['sharedConsumerCount'], hmg['consumerReferences']), (True, 6, 15))
        self.assertIn('allow_shared', hmg['acknowledgements'])
        self.assertFalse(self.outputs['AR-2 Coyote']['slots']['impactExplosion']['current'])

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
        # Support weapons follow the same host rule (research/projectile-builder supportHosts): magazine-fed, every shot
        # their own ProjectileWeapon +0. Ammunition hosts are player weapons only.
        kinds = {w['weapon']: w['kind'] for w in self.active['weapons']}
        # Sentry and emplacement hosts (0.30.2): '<stratagem> / weapon', research/sentry-projectile-hosts.
        sentries = sorted(h['weapon'] + ' / weapon' for h in load('research/sentry-projectile-hosts-F5FEE03DCFDB.json')[
            'hosts'] if h['status'] == 'ACTIVE_DIRECT')
        kinds.update({name: 'vehicle_weapon' for name in sentries})
        self.assertEqual(sorted(n for n in hosts['componentHosts'] if n.endswith(' / weapon')), sentries)
        self.assertEqual(len(sentries), 7)
        support = sorted(n for n in hosts['componentHosts'] if kinds[n] == 'support_weapon')
        self.assertEqual(support, ['APW-1 Anti-Materiel Rifle', 'EAT-17 Expendable Anti-Tank', 'EAT-411 Leveller',
            'EAT-700 Expendable Napalm', 'GL-21 Grenade Launcher', 'M-105 Stalwart', 'MG-206 Heavy Machine Gun',
            'S-11 Speargun'])
        self.assertTrue(all(kinds[n] == 'player_weapon' for n in hosts['ammunitionHosts']))
        mounted = sorted(n for n in hosts['componentHosts'] if kinds[n] == 'vehicle_weapon' and n not in sentries)
        self.assertEqual(mounted, ['AX/AR-23 Guard Dog / gun', 'EXO-45 Patriot Exosuit / right_gun',
            'EXO-49 Emancipator Exosuit / left_gun', 'EXO-49 Emancipator Exosuit / right_gun',
            'EXO-51 Lumberer Exosuit / right_gun', 'FRV (Super Earth variant) / gun', 'GATER Oil Rig / turret',
            'M-102 Gunner FRV / gun', 'M-103 Supply FRV / gun'])
        support_sources = {s['weapon']: s for s in self.catalog['projectileSources'] if s.get('kind') == 'support_weapon'}
        self.assertEqual(sorted(n for n, s in support_sources.items() if s['directWritable']), support)
        # ACTIVE_DIRECT but not magazine-fed: read-only with the reason; other selectors: their own reason.
        self.assertIn('not magazine-fed', support_sources['GL-28 Belt-Fed Grenade Launcher']['reason'])
        self.assertFalse(support_sources['GL-28 Belt-Fed Grenade Launcher']['directWritable'])
        self.assertIn('WeaponRounds', support_sources['AC-8 Autocannon']['reason'])
        self.assertEqual(support_sources['FAF-14 Spear']['status'], 'BLOCKED')
        live = hosts['hostLiveProof']
        # The two direct-path controls and UnifiedProjectileSwapTest (Reprimand <- EAT-700).
        self.assertEqual([r['result'] for r in live['SMG-32 Reprimand']], ['PASS', 'PASS', 'PASS'])
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
        # Every (host, output, mechanism) a live test proved: cross-class compositions, the two support host pairs, the
        # three Patriot minigun donors and the programmable-ammo function projectiles (2026-09-30).
        self.assertEqual([(c['host'], c['output'], c['mechanism']) for c in self.catalog['provenCompositions']],
            [('AR-23 Liberator', 'output/v1/projectile/eat-700-expendable-napalm', 'ammunition'),
             ('AR-23 Liberator', 'output/v1/projectile/gl-52-de-escalator', 'ammunition'),
             ('EAT-17 Expendable Anti-Tank', 'output/v1/projectile/plas-1-scorcher', 'component'),
             ('EXO-45 Patriot Exosuit / right_gun', 'output/v1/projectile/eat-17-expendable-anti-tank', 'component'),
             ('EXO-45 Patriot Exosuit / right_gun', 'output/v1/projectile/las-58-talon', 'component'),
             ('EXO-45 Patriot Exosuit / right_gun', 'output/v1/projectile/plas-1-scorcher', 'component'),
             ('M-105 Stalwart', 'output/v1/projectile/apw-1-anti-materiel-rifle', 'component'),
             ('MG-206 Heavy Machine Gun', 'output/v1/projectile/ar-32-pacifier', 'programmable_ammo'),
             ('MG-206 Heavy Machine Gun', 'output/v1/projectile/p-35-re-educator', 'programmable_ammo'),
             ('MG-206 Heavy Machine Gun', 'output/v1/projectile/r-4-hyena', 'programmable_ammo'),
             ('S-11 Speargun', 'output/v1/projectile/s-11-speargun-spare-twin', 'programmable_ammo'),
             ('SMG-32 Reprimand', 'output/v1/projectile/eat-700-expendable-napalm', 'component')])
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
-- 80 catalogued outputs and the 32 more donors (research/projectile-donors-F5FEE03DCFDB.json).
-- 111 since 0.30.2: the SMG-37 Defender donor (projectile 150, the SEAF SMG round) is retired with its reason.
-- 117 since 0.31.0: + the six beam donors (selectable as beam references only).
assert(#hd2.attack_outputs({selectable=true})==117,#hd2.attack_outputs({selectable=true}))
assert(#hd2.attack_outputs({selectable=true,family='projectile'})==111)
do local ok,why=pcall(hd2.attack_output,'SMG-37 Defender (projectile 150)')
 assert(not ok and tostring(why):find('retired attack output',1,true)
  and tostring(why):find('round of the SEAF SMG',1,true),tostring(why))end
-- The stratagem-owned stun-field donor is scoped to function_ammo.projectile and names its field and presentation.
local ems=hd2.attack_output('A/M-23 EMS Mortar Sentry'):describe()
assert(ems.owner.kind=='stratagem'and ems.referenceScope[1]=='function_ammo.projectile'and#ems.referenceScope==1)
assert(ems.fieldEffect.volume=='StaticField'and ems.fieldEffect.seconds==7 and ems.presentation.label=='none')
rejects(function()patches.validate{id='x',target=reprimand,field=hd2.fields.attack.projectile,
 expect=reprimand:projectile(),value=hd2.attack_output('A/M-23 EMS Mortar Sentry'),allow_unverified_reference=true,
 allow_unverified_effect=true}end,'OUTPUT_SCOPE')
return 'ok'
''')

    def test_support_hosts_share_the_donor_pool(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
local eat=hd2.support_weapon('EAT-17 Expendable Anti-Tank')
local source=eat:projectile_source()
assert(source.writable and source.status=='ACTIVE_DIRECT'and source.mechanism=='component'and source.field=='attack.projectile')
assert(source.target.resource=='support_weapon'and source.expect.path=='projectile_reference')
assert(source.acknowledgements[1]=='allow_unverified_effect')
assert(eat:attack('primary'):projectile_source().writable)
assert(eat:feed('primary'):source().writable)
local function swap(target,expect,value,extra)
 local request={id='s',target=target,field=hd2.fields.attack.projectile,expect=expect,value=value,
  allow_unverified_effect=true,allow_unverified_reference=true}
 for k,v in pairs(extra or{})do if v==false then request[k]=nil else request[k]=v end end
 return patches.validate(request)
end
-- Support host <- primary donor, by output or by the donor weapon's own handle (one pool).
local spec=swap(source.target,source.expect,hd2.attack_output('AR-2 Coyote'))
assert(spec.changes[1].cross_class and spec.asset_dependencies[1])
spec=swap(source.target,source.expect,hd2.weapon('SMG-32 Reprimand'):attack('primary'):projectile())
assert(spec.changes[1].desired_selector.output=='output/v1/projectile/smg-32-reprimand')
-- Same class: no allow_unverified_reference, but the support host path is not yet live-proven.
swap(source.target,source.expect,hd2.attack_output('EAT-411 Leveller'),{allow_unverified_reference=false})
rejects(function()swap(source.target,source.expect,hd2.attack_output('EAT-411 Leveller'),
 {allow_unverified_effect=false,allow_unverified_reference=false})end,'allow_unverified_effect')
rejects(function()swap(source.target,source.expect,hd2.attack_output('AR-2 Coyote'),
 {allow_unverified_reference=false})end,'allow_unverified_reference')
-- Restoring its own projectile is the reviewed baseline.
assert(swap(source.target,source.expect,source.expect,{allow_unverified_effect=false,
 allow_unverified_reference=false}).changes[1].self_reference)
-- Primary host <- support donor handle.
local reprimand=hd2.weapon('SMG-32 Reprimand'):attack('primary')
spec=patches.validate{id='p',target=reprimand,field=hd2.fields.attack.projectile,expect=reprimand:projectile(),
 value=hd2.support_weapon('EAT-700 Expendable Napalm'):attack('primary'):projectile(),allow_unverified_reference=true,
 allow_unverified_effect=true}
assert(spec.changes[1].desired_selector.output=='output/v1/projectile/eat-700-expendable-napalm')
-- Refusals: beam/arc/spray/melee families, another weapon's handle as expect, a non-host support weapon, the spare
-- twin and the stratagem donor outside their scope.
for _,name in ipairs({'LAS-98 Laser Cannon','ARC-3 Arc Thrower','FLAM-40 Flamethrower','CQC-2 Saber'})do
 rejects(function()swap(source.target,source.expect,hd2.attack_output(name))end,'INCOMPATIBLE_OUTPUT_FAMILY')
end
local hmg=hd2.support_weapon('MG-206 Heavy Machine Gun')
rejects(function()swap(hmg:attack('primary'),eat:attack('primary'):projectile(),hd2.attack_output('M-105 Stalwart'))end,
 'expect must be the target attack current projectile handle')
rejects(function()swap(hmg:attack('primary'),hd2.weapon('SMG-32 Reprimand'):attack('primary'):projectile(),
 hd2.attack_output('M-105 Stalwart'))end,'expect must be the target attack current projectile handle')
local gl28=hd2.support_weapon('GL-28 Belt-Fed Grenade Launcher')
assert(not gl28:projectile_source().writable and gl28:projectile_source().reason:find('not magazine-fed',1,true))
rejects(function()swap(gl28:attack('primary'),gl28:attack('primary'):projectile(),hd2.attack_output('AR-2 Coyote'))end,
 'field is not exposed')
rejects(function()swap(source.target,source.expect,hd2.attack_output('S-11 Speargun (spare twin)'))end,'OUTPUT_SCOPE')
rejects(function()swap(source.target,source.expect,hd2.attack_output('A/M-23 EMS Mortar Sentry'))end,'OUTPUT_SCOPE')
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
    def test_projectile_builder_snapshot_record(self):
        # Refresh with: py scripts/validate_projectile_builder_snapshot.py
        record = load('validation/projectile-builder-snapshot.json')
        self.assertEqual(record['status'], 'VALIDATED')
        self.assertIn('pending a live test', record['proofScope'])
        rows = record['speargun']['rows']
        self.assertEqual(rows['changedMembers'], {'spare': ['presentation', 'expiry_explosion'], 'own': ['presentation']})
        self.assertTrue(rows['gasExpiryUnchanged'])
        self.assertEqual(record['speargun']['spear-stun-slots']['packages'], 1)
        # Where each showcase row's effect lives: the Speargun gas is an expiry field, the EMS stun too; the EAT-700
        # and Eruptor release submunitions; the Coyote is a direct hit only.
        audit = record['audit']
        self.assertNotIn('impact', audit['S-11 Speargun'])
        self.assertTrue(audit['S-11 Speargun']['expiry']['lingeringField'])
        self.assertTrue(audit['A/M-23 EMS Mortar Sentry']['expiry']['lingeringField'])
        self.assertTrue(audit['EAT-700 Expendable Napalm']['impact']['submunition'])
        self.assertEqual(audit['AR-2 Coyote'], {'directHit': True})
        unified = record['unified']
        self.assertEqual({item['member'] for item in unified.values() if isinstance(item, dict)},
            {'ProjectileWeapon +0', 'ammunition delta'})
        self.assertTrue(unified['restoreIsBaseline'])
        self.assertEqual(set(record['rejections']), {'beamHasNoSlots', 'builderWithoutAcknowledgement',
            'crossSlotType', 'donorLacksSlot', 'mountedBeamDonor', 'mountedNonHost', 'mountedSharedRow',
            'staleMountChain',
            'dormantSource', 'incompatibleFamilies', 'missingPackage', 'nonHostSupport', 'recursionDirect',
            'recursionTwoStep', 'removeDirectHit', 'sharedRow', 'spareTwinChanged', 'spareTwinOtherBuild',
            'staleDonor', 'staleSlotDonor',
            'stale_identity', 'unknownOutput', 'unknownSlot', 'wrongExpect'})
        self.assertEqual(record['sharedWithAcknowledgement'], {'entities': 6, 'references': 15})
        self.assertEqual(record['submunitionChainAccepted'], 'EAT-700 Expendable Napalm impact explosion')

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
