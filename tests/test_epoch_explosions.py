"""Charge-level shots and overcharge explosions (scripts/charge_fields.py, research/charge-explosions-F5FEE03DCFDB.json).

The PLAS-45 Epoch's partial-charge shot ('primary' / 'primary_impact', ids unchanged), its full-charge shot
('full_charge' / 'full_charge_impact') and its overcharge explosion ('overcharge_explosion'), and the RS-422 Railgun's
overcharge explosion: each its own support attack role, resolved live through the weapon's own WeaponCharge record.
Every field of these roles needs allow_unverified_effect and allow_shared; the Epoch's partial-charge fields gained the
acknowledgement in 0.30.0 (a row only one charge level fires, the Purifier rule), version-aware: a mod that declares an
older SDK keeps writing them as a logged legacy operation. Plus the retained-snapshot overlay validation and the live-test
example (examples/projects/EpochExplosionsTest)."""
import json
import re
import struct
import subprocess
import sys
import unittest

from support import ROOT, run

sys.path.insert(0, str(ROOT / 'scripts'))
import generate_legacy_acknowledgements as legacy_table  # noqa: E402
import generate_support_weapon_authoring  # noqa: E402
from test_legacy_sdk_compatibility import legacy_lines, modbuilder_wrap, only, run_mods  # noqa: E402

RESEARCH = json.loads((ROOT / 'research/charge-explosions-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
SUPPORT = json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text(encoding='utf-8'))
LEGACY = json.loads((ROOT / 'schemas/legacy_acknowledgements.json').read_text(encoding='utf-8'))
SNAPSHOT_REPORT = ROOT / 'validation/epoch-explosions-snapshot.json'
EXAMPLE = ROOT / 'examples/projects/EpochExplosionsTest'
EPOCH, RAIL = 'PLAS-45 Epoch', 'RS-422 Railgun'
PROJECTILE = {'projectile.velocity', 'projectile.mass', 'projectile.drag', 'projectile.gravity', 'projectile.pellet_count',
    'projectile.lifetime', 'projectile.penetration_slowdown'}
DAMAGE = {'standard_damage', 'durable_damage', 'ap_direct', 'ap_slight', 'ap_large', 'ap_extreme', 'demolition', 'stagger',
    'push_force'}
PROJECTILE_ROLE = PROJECTILE | {'damage.' + name for name in DAMAGE} | {'damage.status_1_type', 'damage.status_1_strength'}
EXPLOSION_ROLE = ({'explosion.inner_radius', 'explosion.outer_radius', 'explosion.shockwave_radius'}
    | {'explosion.damage.' + name for name in DAMAGE}
    | {'explosion.damage.status_1_type', 'explosion.damage.status_1_strength'})
ROLES = {EPOCH: {'primary': ('partial', PROJECTILE_ROLE), 'primary_impact': ('partial', EXPLOSION_ROLE),
        'full_charge': ('full', PROJECTILE_ROLE), 'full_charge_impact': ('full', EXPLOSION_ROLE),
        'overcharge_explosion': ('overcharge', EXPLOSION_ROLE)},
    RAIL: {'overcharge_explosion': ('overcharge', EXPLOSION_ROLE)}}
# The 0.28.1 instance key of an existing partial-charge field: the ids and keys of 0.28.x stay.
EPOCH_VELOCITY_KEY = 'support-field/v1/plas-45-epoch/projectile-reference/primary/projectile-velocity/9ed92fa3a82b5806'


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def instances(weapon, role=None):
    return [item for item in SUPPORT['fieldInstances'] if item['supportWeapon'] == weapon
        and (role is None or item['target']['attackRole'] == role)]


def by_id(weapon, role):
    return {item['semanticFieldId']: item for item in instances(weapon, role)}


class ResearchTests(unittest.TestCase):
    def test_charge_levels_select_the_reviewed_rows(self):
        epoch = RESEARCH['weapons'][EPOCH]['chargeRecord']
        self.assertEqual(epoch['levelProjectiles'], {'partial': 165, 'full': 193, 'overcharged': 193})
        self.assertEqual([round(t, 6) for t in epoch['chargeTimes']], [1.0, 2.5, 2.6])
        self.assertEqual((epoch['overchargeExplosion'], epoch['explodeWhenOvercharged']), (321, 0))
        self.assertEqual(epoch['overchargeLimit'], {'state': 2, 'seconds': 3.25})
        self.assertEqual(epoch['fireModes']['reachable'], [6])
        rail = RESEARCH['weapons'][RAIL]['chargeRecord']
        self.assertEqual(set(rail['levelProjectiles'].values()), {0})
        self.assertEqual((rail['overchargeExplosion'], rail['explodeWhenOvercharged']), (326, 1))
        rows = RESEARCH['rows']
        self.assertEqual((rows['projectile']['165']['impactExplosion'], rows['projectile']['165']['expiryExplosion']),
            (227, 227))
        self.assertEqual((rows['projectile']['193']['impactExplosion'], rows['projectile']['193']['expiryExplosion']),
            (407, 407))
        self.assertEqual(rows['explosion']['407']['damage'], rows['explosion']['321']['damage'])

    def test_every_branch_equals_its_published_values(self):
        published = RESEARCH['published']
        self.assertEqual({name: item['row'] for name, item in published[EPOCH].items()},
            {'PLAS-45 P': 'projectile:165', 'P3': 'projectile:193', 'PLAS-45 P IE': 'explosion:227',
                'P3 IE': 'explosion:407', 'PLAS-45 EPOCH Overcharge E': 'explosion:321'})
        for weapon in (EPOCH, RAIL):
            for name, item in published[weapon].items():
                if item.get('row'):
                    self.assertTrue(item['allExact'], (weapon, name))
                    self.assertFalse(item['mismatchedFields'], (weapon, name))
        self.assertTrue(published[RAIL]['Railgun Max Charge']['exact'])
        self.assertIsNone(published[RAIL]['Railgun Max Charge']['row'])

    def test_native_code_and_live_rows(self):
        self.assertEqual(RESEARCH['code']['pinGroups'], ['chain', 'drain', 'failure', 'selection'])
        self.assertEqual(len(RESEARCH['code']['pins']), 37)
        read = [snap for snap in RESEARCH['liveEquality'] if snap['status'] == 'read']
        self.assertGreaterEqual(len(read), 3)
        for snap in read:
            self.assertTrue(all(item['equalsDatalibrary'] for item in snap['rows'].values()), snap['snapshot'])

    def test_shared_ownership(self):
        sharing = RESEARCH['sharing']
        self.assertEqual({(item['component'], item['member']) for item in sharing['projectile:193']},
            {('WeaponChargeComponentData', 28), ('WeaponChargeComponentData', 52)})
        self.assertEqual({(item['component'], item['member']) for item in sharing['projectile:165']},
            {('WeaponChargeComponentData', 4), ('ProjectileWeaponComponentData', 0)})
        self.assertEqual(sorted(item['row'] for item in sharing['damage:61']), [321, 407])
        over = {item['weapon']: item['reachable'] for item in sharing['explosion:321']}
        self.assertEqual(over, {EPOCH: True, '40-K Meltagun': False})
        rail = {item['weapon']: item['reachable'] for item in sharing['explosion:326']}
        self.assertEqual(rail, {RAIL: True, 'PLAS-39 Accelerator Rifle': False})
        self.assertEqual(sorted(item['row'] for item in sharing['damage:352']), [269, 326])
        for key in ('explosion:227', 'explosion:407'):
            self.assertEqual(sorted(item['kind'] for item in sharing[key]), ['projectile_expiry', 'projectile_impact'])


class CatalogTests(unittest.TestCase):
    def test_generated_outputs_are_current(self):
        self.assertFalse(generate_support_weapon_authoring.generate(check=True))

    def test_each_charge_level_is_its_own_role_with_the_full_field_set(self):
        for weapon, roles in ROLES.items():
            for role, (level, expected) in roles.items():
                fields = by_id(weapon, role)
                self.assertEqual(set(fields), expected, (weapon, role))
                for item in fields.values():
                    self.assertTrue(item['writable'], (weapon, role, item['semanticFieldId']))
                    self.assertEqual(item['chargeLevel']['level'], level)
                    self.assertEqual(item['operation']['acknowledgement'], 'allow_unverified_effect')
                    self.assertTrue(item['operation']['allowSharedRequired'])
                    self.assertNotIn('liveEvidence', item)
                    self.assertEqual(item['chargeLevel']['evidence'], 'research/charge-explosions-F5FEE03DCFDB.json')
                    self.assertIn(item['chargeLevel']['readTiming'], item['effect']['readTiming'])
                    self.assertFalse(item['effect']['gameplayEffectProven'])
                    self.assertTrue(item['effect']['unverifiedEffect'])
                    self.assertEqual(item['effect']['activeSource'],
                        'ACTIVE_DIRECT' if level == 'overcharge' else 'AMBIGUOUS')
                    if level == 'overcharge':
                        self.assertIn('damages the wielder', item['chargeLevel']['selfDamage'])
                        self.assertIn('damages the wielder', item['operation']['acknowledgementReason'])
                    self.assertIn('other players', item['chargeLevel']['multiplayer'])

    def test_baselines_equal_the_research_rows(self):
        rows = RESEARCH['rows']
        full = by_id(EPOCH, 'full_charge')
        self.assertEqual(full['projectile.velocity']['value']['baseline'], 250.0)
        self.assertAlmostEqual(full['projectile.lifetime']['value']['baseline'], 0.6, places=6)
        self.assertEqual({full['damage.' + lane]['value']['baseline'] for lane in ('ap_direct', 'ap_extreme')}, {5})
        partial = by_id(EPOCH, 'primary')
        self.assertEqual({partial['damage.' + lane]['value']['baseline'] for lane in ('ap_direct', 'ap_extreme')}, {4})
        for weapon, role, native in ((EPOCH, 'primary_impact', '227'), (EPOCH, 'full_charge_impact', '407'),
                (EPOCH, 'overcharge_explosion', '321'), (RAIL, 'overcharge_explosion', '326')):
            fields = by_id(weapon, role)
            row = rows['explosion'][native]
            damage = rows['damage'][str(row['damage'])]['values']
            for suffix in ('inner_radius', 'outer_radius', 'shockwave_radius'):
                self.assertAlmostEqual(fields['explosion.' + suffix]['value']['baseline'],
                    f32(row['values']['explosion_' + suffix]), places=6, msg=(weapon, role, suffix))
            for name in DAMAGE:
                self.assertEqual(fields['explosion.damage.' + name]['value']['baseline'], damage[name], (role, name))
        self.assertEqual(by_id(EPOCH, 'overcharge_explosion')['explosion.damage.standard_damage']['value']['baseline'],
            800)
        self.assertEqual(by_id(RAIL, 'overcharge_explosion')['explosion.damage.standard_damage']['value']['baseline'],
            300)

    def test_existing_partial_charge_ids_keep_their_keys_and_gain_the_acknowledgement(self):
        partial = by_id(EPOCH, 'primary')
        velocity = partial['projectile.velocity']
        self.assertEqual(velocity['instanceKey'], EPOCH_VELOCITY_KEY)
        self.assertEqual(velocity['qualifiedSemanticFieldId'], 'projectile.primary.velocity')
        self.assertIn('Only the partial-charge shot fires this row', velocity['operation']['acknowledgementReason'])
        self.assertIn("attack('full_charge')", velocity['operation']['acknowledgementReason'])
        blast = by_id(EPOCH, 'primary_impact')['explosion.outer_radius']
        self.assertIn('Only the partial-charge shot releases this explosion', blast['operation']['acknowledgementReason'])
        self.assertEqual(blast['chargeLevel']['phases'], ['impact', 'expiry'])

    def test_the_full_charge_and_overcharge_explosions_share_one_damage_row(self):
        impact = by_id(EPOCH, 'full_charge_impact')
        over = by_id(EPOCH, 'overcharge_explosion')
        for name in DAMAGE:
            a, c = impact['explosion.damage.' + name], over['explosion.damage.' + name]
            self.assertEqual(a['backing']['objectKey'], c['backing']['objectKey'], name)
            roles = {item['attackRole'] for item in a['sharedScope']['affectedSemanticConsumers']}
            self.assertEqual(roles, {'full_charge_impact', 'overcharge_explosion'})
            self.assertIn("attack('overcharge_explosion')", a['operation']['acknowledgementReason'])
            self.assertIn("attack('full_charge_impact')", c['operation']['acknowledgementReason'])
        # The radii are their own rows.
        self.assertNotEqual(impact['explosion.inner_radius']['backing']['objectKey'],
            over['explosion.inner_radius']['backing']['objectKey'])
        consumers = over['explosion.inner_radius']['chargeLevel']['sharedConsumers']
        self.assertEqual([(item['weapon'], item['reachable']) for item in consumers], [('40-K Meltagun', False)])
        rail = by_id(RAIL, 'overcharge_explosion')['explosion.damage.standard_damage']['chargeLevel']
        self.assertEqual({item['weapon'] for item in rail['sharedConsumers']}, {'ARC-3 Arc Thrower', 'PLAS-101 Purifier',
            'PLAS-15 Loyalist', 'PLAS-39 Accelerator Rifle', 'Watcher weapon (slot 0)'})
        self.assertEqual(rail['unidentifiedSharedConsumers'], 3)

    def test_branches_resolve_on_their_roles(self):
        weapons = {item['name']: item for item in SUPPORT['weapons']}
        epoch = {item['name']: item for item in weapons[EPOCH]['attackBranches']}
        self.assertEqual({name: (item['runtimeRole'], item['state'], item['writable'], item['chargeLevel'])
            for name, item in epoch.items()}, {
            'PLAS-45 P': ('primary', 'RESOLVED', True, 'partial'),
            'PLAS-45 P IE': ('primary_impact', 'RESOLVED', True, 'partial'),
            'P3': ('full_charge', 'RESOLVED', True, 'full'),
            'P3 IE': ('full_charge_impact', 'RESOLVED', True, 'full'),
            'PLAS-45 EPOCH Overcharge E': ('overcharge_explosion', 'RESOLVED', True, 'overcharge')})
        self.assertFalse([item for item in weapons[EPOCH]['blockedFields'] if item['field'] == 'unresolved branch'])
        rail = {item['name']: item for item in weapons[RAIL]['attackBranches']}
        self.assertEqual((rail['RS-422 RAILGUN Overcharge E']['runtimeRole'], rail['RS-422 RAILGUN Overcharge E']['state']),
            ('overcharge_explosion', 'RESOLVED'))
        self.assertEqual(rail['Railgun Max Charge']['state'], 'UNRESOLVED')
        runtime, _ = generate_support_weapon_authoring.build()
        self.assertEqual(runtime['weapons'][EPOCH]['branchRoles'], {'PLAS-45 P': 'primary',
            'PLAS-45 P IE': 'primary_impact', 'P3': 'full_charge', 'P3 IE': 'full_charge_impact',
            'PLAS-45 EPOCH Overcharge E': 'overcharge_explosion'})
        self.assertEqual(runtime['weapons'][RAIL]['branchRoles'], {'RS-422 P': 'primary',
            'RS-422 RAILGUN Overcharge E': 'overcharge_explosion'})
        # Every charge-level field resolves through the weapon's own charge record.
        for weapon, roles in ROLES.items():
            for field in runtime['weapons'][weapon]['fields']:
                if field['target'].get('attack') in roles:
                    self.assertTrue(field['backing']['linkage'].startswith('charge_'), field['semanticFieldId'])
                    self.assertEqual(field['backing']['chargeRecord']['ownerCount'], 1)
        reference = next(item for item in instances(EPOCH) if item['semanticFieldId'] == 'charge.overcharge_explosion')
        self.assertEqual(reference['charge']['contents'], "attack('overcharge_explosion'):explosion()")


class LegacyTableTests(unittest.TestCase):
    def test_the_partial_charge_fields_gained_the_acknowledgement_in_0_30_0(self):
        entries = [entry for entry in LEGACY['entries'] if entry['since'] == '0.30.0']
        # Every partial-charge field except the explosion's status slot, which already needed the acknowledgement.
        partial = {item['qualifiedSemanticFieldId'] for role in ('primary', 'primary_impact')
            for item in instances(EPOCH, role)} - {'explosion.primary_impact.damage.status_1_type',
            'explosion.primary_impact.damage.status_1_strength'}
        self.assertEqual({entry['field'] for entry in entries}, partial)
        self.assertEqual(len(entries), 30)
        self.assertEqual({(entry['resource'], entry['target']) for entry in entries}, {('support_weapon', EPOCH)})
        legacy_table.generate(check=True)
        lua = (ROOT / 'domains/legacy_acknowledgements.lua').read_text(encoding='utf-8')
        # 0.31.0 added the team-reload magazine rows of other support weapons to the same resource table.
        self.assertIn('["PLAS-45 Epoch"]={["damage.primary.ap_direct"]="0.30.0"', lua)

    @unittest.skipUnless(subprocess.run(['git', 'rev-parse', '-q', '--verify', 'v0.28.1^{commit}'], cwd=ROOT,
        capture_output=True).returncode == 0, 'the v0.28.1 tag is not available')
    def test_they_were_writable_without_it_in_0_28_1(self):
        previous = legacy_table.fields(legacy_table.git_catalogs('v0.28.1'))
        for entry in LEGACY['entries']:
            if entry['since'] == '0.30.0':
                field = previous[(entry['resource'], entry['target'], entry['field'])]
                self.assertTrue(field['editable'] and field['acknowledgement'] is None, entry['field'])
        # None of the new roles existed: no SDK older than 0.30.0 ever wrote them, so there is no earlier rule to keep.
        new = {key for key in previous if key[1] in (EPOCH, RAIL) and len(key[2].split('.')) > 2
            and key[2].split('.')[1] in ('full_charge', 'full_charge_impact', 'overcharge_explosion')}
        self.assertFalse(new)


# Operations as a published mod writes them (no allow_unverified_effect).
PARTIAL_BLAST = ("hd2.ensure({transaction={id='epoch-partial',target=hd2.support_weapon('PLAS-45 Epoch'):attack("
    "'primary_impact'):explosion(),allow_shared=true,changes={{field=hd2.fields.explosion.inner_radius,"
    "expect=2.299999952316284,value=3},{field=hd2.fields.explosion.outer_radius,expect=3,value=4}}}})")
PARTIAL_SPEED = ("hd2.ensure({patch={id='epoch-speed',target=hd2.support_weapon('PLAS-45 Epoch'):attack('primary')"
    ":projectile(),allow_shared=true,field=hd2.fields.projectile.velocity,expect=250,value=400}})")
# A new role, written through the target identity a handle carries (api/target.lua resolves the role name).
FULL_BLAST = ("hd2.ensure({patch={id='epoch-full',target={resource='support_weapon',path='explosion',"
    "weapon='PLAS-45 Epoch',attack='full_charge_impact'},allow_shared=true,field=hd2.fields.explosion.outer_radius,"
    "expect=4,value=6}})")


class LegacyOperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = run_mods([
            ('sdk-027', modbuilder_wrap('mods/test/epoch_027', '0.27.0', PARTIAL_BLAST)),
            ('sdk-0281', modbuilder_wrap('mods/test/epoch_0281', '0.28.1', PARTIAL_SPEED)),
            ('sdk-030', modbuilder_wrap('mods/test/epoch_030', '0.30.0', PARTIAL_BLAST)),
            ('sdk-030-ack', modbuilder_wrap('mods/test/epoch_030_ack', '0.30.0',
                PARTIAL_BLAST.replace('allow_shared=true,', 'allow_shared=true,allow_unverified_effect=true,'))),
            ('bare', "local hd2=require('mods/skyeshade/hd2runtime')\n" + PARTIAL_SPEED),
            ('new-role-027', modbuilder_wrap('mods/test/epoch_new_027', '0.27.0', FULL_BLAST)),
            ('new-role-030-ack', modbuilder_wrap('mods/test/epoch_new_030', '0.30.0',
                FULL_BLAST.replace('allow_shared=true,', 'allow_shared=true,allow_unverified_effect=true,'))),
        ])

    def legacy(self, name, sdk_version, fields):
        op = only(self.results[name])
        self.assertNotEqual(op['status'], 'rejected', op.get('error'))
        self.assertEqual(op['sdk'], sdk_version)
        self.assertEqual([(item['target'], item['field'], item['since']) for item in op['legacy']],
            [(EPOCH, field, '0.30.0') for field in fields])
        lines = legacy_lines(self.results[name])
        self.assertEqual(len(lines), len(fields), lines)
        return lines

    def refused(self, name, *needles):
        op = only(self.results[name])
        self.assertEqual(op['status'], 'rejected')
        self.assertFalse(op['legacy'])
        self.assertIn('field requires allow_unverified_effect=true', op['error'])
        for needle in needles:
            self.assertIn(needle, op['error'])

    def test_older_sdk_mods_keep_writing_the_partial_charge_fields_as_legacy_operations(self):
        lines = self.legacy('sdk-027', '0.27.0', ['explosion.primary_impact.inner_radius',
            'explosion.primary_impact.outer_radius'])
        self.assertIn('PLAS-45 Epoch explosion.primary_impact.inner_radius needs allow_unverified_effect=true since '
            'SDK 0.30.0 and is applied without it, as SDK 0.27.0 allowed', lines[0])
        self.assertIn('Rebind the project to SDK 0.30.0 or later', lines[0])
        self.assertIn('Only the partial-charge shot releases this explosion', lines[0])
        self.legacy('sdk-0281', '0.28.1', ['projectile.primary.velocity'])

    def test_current_and_unknown_sdk_mods_keep_the_rule(self):
        self.refused('sdk-030', 'required since SDK 0.30.0; mods/test/epoch_030 declares SDK 0.30.0')
        self.refused('bare', 'Runtime could not read the SDK version of')
        op = only(self.results['sdk-030-ack'])
        self.assertNotEqual(op['status'], 'rejected', op.get('error'))
        self.assertEqual(op['legacy'] or [], [])

    def test_new_roles_have_no_legacy_rule(self):
        self.refused('new-role-027', 'Only the full-charge or overcharged shot releases this explosion')
        self.assertNotIn('required since', only(self.results['new-role-027'])['error'])
        op = only(self.results['new-role-030-ack'])
        self.assertNotEqual(op['status'], 'rejected', op.get('error'))


class WriteRuleTests(unittest.TestCase):
    def test_linkages_acknowledgements_and_shared_rows(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local F=hd2.fields
local function target(weapon,path,attack)return {resource='support_weapon',path=path,weapon=weapon,attack=attack}end
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
local epoch,rail='PLAS-45 Epoch','RS-422 Railgun'
local over=target(epoch,'explosion','overcharge_explosion')
local impact=target(epoch,'explosion','full_charge_impact')
local full=target(epoch,'projectile_reference','full_charge')
-- Every role needs both acknowledgements.
rejects(function()writes.validate_patch{id='a',target=over,allow_shared=true,field=F.explosion.damage_standard_damage,
 expect=800,value=1}end,'allow_unverified_effect')
rejects(function()writes.validate_patch{id='s',target=over,allow_unverified_effect=true,
 field=F.explosion.damage_standard_damage,expect=800,value=1}end,'allow_shared')
rejects(function()writes.validate_patch{id='e',target=over,allow_shared=true,allow_unverified_effect=true,
 field=F.explosion.damage_standard_damage,expect=500,value=1}end,'expect differs')
local damage=writes.validate_patch{id='d',target=over,allow_shared=true,allow_unverified_effect=true,
 field=F.explosion.damage_standard_damage,expect=800,value=1}
local shared=writes.validate_patch{id='i',target=impact,allow_shared=true,allow_unverified_effect=true,
 field=F.explosion.damage_standard_damage,expect=800,value=2}
local a,c=damage.changes[1].descriptor.backing,shared.changes[1].descriptor.backing
assert(a.linkage=='charge_overcharge_explosion_damage'and c.linkage=='charge_projectile_explosion_damage')
assert(a.row==c.row and a.group==c.group and a.recordType==c.recordType and a.offset==c.offset,'one damage row')
local radius=writes.validate_patch{id='r',target=over,allow_shared=true,allow_unverified_effect=true,
 field=F.explosion.outer_radius,expect=4,value=0.2}
assert(radius.changes[1].descriptor.backing.chargeExplosionOffset==200)
local speed=writes.validate_patch{id='v',target=full,allow_shared=true,allow_unverified_effect=true,
 field=F.projectile.velocity,expect=250,value=60}
local selectors=speed.changes[1].descriptor.backing.chargeSelectorOffsets
assert(selectors[1]==28 and selectors[2]==52 and#selectors==2)
local partial=writes.validate_patch{id='p',target=target(epoch,'projectile_reference','primary'),allow_shared=true,
 allow_unverified_effect=true,field=F.projectile.velocity,expect=250,value=400}
assert(partial.changes[1].descriptor.backing.chargeSelectorOffsets[1]==4)
-- Outside any registration (no declared SDK) the partial-charge rule applies.
rejects(function()writes.validate_patch{id='n',target=target(epoch,'explosion','primary_impact'),allow_shared=true,
 field=F.explosion.outer_radius,expect=3,value=12}end,'required since SDK 0.30.0')
local railgun=writes.validate_patch{id='g',target=target(rail,'explosion','overcharge_explosion'),allow_shared=true,
 allow_unverified_effect=true,field=F.explosion.damage_push_force,expect=40,value=0}
assert(railgun.changes[1].descriptor.backing.linkage=='charge_overcharge_explosion_damage')
-- The Railgun keeps one shot: no full-charge role.
rejects(function()writes.validate_patch{id='f',target=target(rail,'projectile_reference','full_charge'),
 allow_shared=true,allow_unverified_effect=true,field=F.projectile.velocity,expect=2000,value=1000}end,
 'not exposed')
return 'ok'
'''), b'ok')


@unittest.skipUnless('branchRoles' in (ROOT / 'api/target.lua').read_text(encoding='utf-8'),
    'api/target.lua does not resolve the authoring branchRoles yet (the reviewed charge-level role names)')
class HandleTests(unittest.TestCase):
    def test_public_handles_name_every_charge_level(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local epoch=hd2.support_weapon('PLAS-45 Epoch')
assert(epoch:attack('full_charge'):projectile().attack=='full_charge')
assert(epoch:attack('P3'):projectile().attack=='full_charge')
assert(epoch:attack('full_charge_impact'):explosion().attack=='full_charge_impact')
assert(epoch:attack('PLAS-45 EPOCH Overcharge E'):explosion().attack=='overcharge_explosion')
assert(epoch:attack('primary'):describe().name=='PLAS-45 P')
assert(hd2.support_weapon('RS-422 Railgun'):attack('overcharge_explosion'):explosion().attack=='overcharge_explosion')
assert(not pcall(function()return hd2.support_weapon('RS-422 Railgun'):attack('Railgun Max Charge'):explosion()end))
return 'ok'
'''), b'ok')


@unittest.skipUnless(SNAPSHOT_REPORT.is_file(), 'epoch explosions snapshot validation not run')
class SnapshotTests(unittest.TestCase):
    def test_every_field_round_trips_on_the_retained_snapshot(self):
        report = json.loads(SNAPSHOT_REPORT.read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'VALIDATED')
        expected = sum(len(fields) for roles in ROLES.values() for _, fields in roles.values())
        self.assertEqual(report['fields'], expected)
        self.assertEqual(report['byRole'], {f'{weapon}/{role}': len(fields) for weapon, roles in ROLES.items()
            for role, (_, fields) in roles.items()})
        for key in ('baselineMatches', 'noOps', 'changedWrites', 'isolatedWrites', 'protectionRestored', 'rollbacks',
                'conflictRejections', 'acknowledgementRejections', 'sharedRejections', 'staleExpectRejections'):
            self.assertEqual(report[key], report['fields'], key)
        self.assertEqual((report['selectorRefusals'], report['overchargeSwapRefusals'], report['sharedRowProofs']),
            (4, 4, 3))
        self.assertEqual(report['liveTestWrites'], 16)
        # The partial-charge rows are the rows 0.28.x wrote; the two Epoch explosions name one damage row.
        rows = report['rows']
        self.assertEqual((rows['PLAS-45 Epoch/primary/projectile'], rows['PLAS-45 Epoch/primary_impact/explosion']),
            (317, 103))
        self.assertEqual(rows['PLAS-45 Epoch/full_charge_impact/explosion_damage'],
            rows['PLAS-45 Epoch/overcharge_explosion/explosion_damage'])
        self.assertEqual(report['writes'], 2 * report['fields'] + report['sharedRowProofs'] + report['liveTestWrites'])


class ExampleTests(unittest.TestCase):
    def test_example_is_differentiated_and_acknowledged(self):
        spec = json.loads((EXAMPLE / 'hd2runtime.json').read_text(encoding='utf-8'))
        self.assertEqual(spec['requires']['hd2runtime']['min_version'], '0.30.0')
        self.assertEqual(spec['resource'], 'mods/hd2runtime_examples/epoch_explosions_test')
        self.assertEqual((EXAMPLE / 'VERSION').read_text(encoding='utf-8'), '0.1.0\n')
        source = (EXAMPLE / 'src/addon.lua').read_text(encoding='utf-8')
        self.assertIn("local BANNER='EPOCH EXPLOSIONS 0.1.0 BUILD'", source)
        ensures = source.split('hd2.ensure(')[1:]
        self.assertEqual(len(ensures), 6)
        for block in ensures:
            self.assertIn('allow_shared=true', block)
            self.assertIn('allow_unverified_effect=true', block)
        toggles = re.findall(r"options:toggle\(\{id='(\w+)'.*?default=(true|false)", source, re.S)
        self.assertEqual(toggles, [('harmless_overcharge', 'true'), ('wide_overcharge', 'false'),
            ('big_partial_blast', 'false'), ('big_full_charge_blast', 'false'), ('slow_full_charge', 'false'),
            ('railgun_gentle_overcharge', 'true')])
        # The overcharge explosions are harmless by default: their damage is written down to 1 in the default state.
        self.assertIn("{field=hd2.fields.explosion.damage_standard_damage,expect=800,value=1}", source)
        self.assertIn("{field=hd2.fields.explosion.damage_standard_damage,expect=300,value=1}", source)
        readme = (EXAMPLE / 'README.md').read_text(encoding='utf-8')
        self.assertIn('Never hold the Epoch past 3 s while "Harmless overcharge" is off', readme)
        self.assertIn('**You survive and are not thrown**', readme)


if __name__ == '__main__':
    unittest.main()
