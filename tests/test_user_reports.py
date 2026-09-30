"""The AyakaMods user report (docs/user-report-ayakamods-2026-09-29.md) as regression fixtures.

The user's ModBuilder project registered only its first 42 of 133 operations with the published 0.27.0: operation 42
(the SG-20 Halt primary-feed damage) raised `field is not exposed`, which aborted the addon. These tests keep the
fixture honest (the log is the export's prefix), prove every exported operation now validates, check the project's
structure, the Halt feed-field resolution, the one-time startup version line and the published effect model."""
import importlib.util
import json
import re
import unittest

from support import ROOT, run

FIXTURE = ROOT / 'tests/fixtures/user-reports/ayakamods-weaponry-rebalance'
GENERATED = FIXTURE / 'generated'
PURIFIER_DRAG = 'gui-object-64f6c65514d7e06d97274943'
HALT_PRIMARY = 'gui-object-aba9f0c284c40c71aaf8f6ff'


def operation_ids(source):
    return [re.search(r"id='([^']+)'", block).group(1)
        for block in re.split(r'\noperations\[#operations\+1\]=', source)[1:]]


PROBE = r'''
local validators={patch=require('hd2runtime/domains/patches').validate,
 transaction=require('hd2runtime/domains/transactions').validate,plan=require('hd2runtime/domains/composition_plans').validate}
local hd2=require('hd2runtime/api/hd2')
local out={}
local function backing_key(change)
 local b=change.descriptor and change.descriptor.backing or{}
 local owner=b.kind=='component'and(tostring(b.component)..'#'..tostring(b.recordIndex))
  or b.kind=='settings'and(tostring(b.settings)..'@'..tostring(b.group)..':'..tostring(b.row))
  or b.kind=='entity_delta'and('delta@'..tostring(change.descriptor.dataOffset))
  or tostring(b.kind)..'@'..tostring(b.nativeIdentity or b.row or'')
 return owner..'+'..tostring(b.offset)
end
for _,variant in ipairs(VARIANTS)do
 local results={}
 local function probe(request)
  local kind=request.patch and'patch'or request.transaction and'transaction'or'plan'
  local body=request[kind]
  local ok,spec=pcall(validators[kind],body)
  local row={id=body.id,ok=ok,error=not ok and tostring(spec)or nil,changes={}}
  if ok then
   local specs=kind=='plan'and{}or{spec}
   if kind=='plan'then for _,op in ipairs(spec.operations)do specs[#specs+1]=op.spec end end
   for _,s in ipairs(specs)do for _,c in ipairs(s.changes or{})do
    row.changes[#row.changes+1]={weapon=s.weapon or s.stratagem or s.attachment or'',backing=backing_key(c)}
   end end
  end
  results[#results+1]=row
  return {status=ok and'waiting'or'rejected'}
 end
 local env=setmetatable({hd2=hd2,probe=probe},{__index=_G})
 local chunk=assert(loadstring(variant.source,'@'..variant.name))
 setfenv(chunk,env);chunk()
 out[#out+1]={name=variant.name,results=results}
end
return require('hd2runtime/primary_mapper/json').encode(out)
'''


def probe_variants(names, folder=GENERATED):
    def lua_string(text):
        return '"' + ''.join(c if 32 <= ord(c) < 127 and c not in '"\\' else '\\%03d' % ord(c) for c in text) + '"'
    variants = []
    for name in names:
        source = (folder / (name + '.lua')).read_text(encoding='utf-8')
        source = source.replace("local hd2=require('mods/skyeshade/hd2runtime')", '')
        source = re.sub(r'\bhd2\.ensure\(', 'probe(', source)
        variants.append('{name=' + lua_string(name) + ',source=' + lua_string(source) + '}')
    out = run('local VARIANTS={' + ','.join(variants) + '}\n' + PROBE).decode()
    return {item['name']: item['results'] for item in json.loads(out[out.index('['):])}


class UserReportFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names = sorted(path.name[:-4] for path in GENERATED.glob('*.lua') if not path.name.endswith('.wrapped.lua'))
        cls.results = probe_variants(cls.names)

    def test_the_log_is_the_first_42_operations_of_the_export(self):
        ids = operation_ids((GENERATED / 'A-original.lua').read_text(encoding='utf-8'))
        log = (FIXTURE / 'HD2Runtime.log').read_text(encoding='utf-8')
        scheduled = re.findall(r'ensure (\S+) scheduled', log)
        self.assertEqual(len(ids), 133)
        self.assertEqual(scheduled, ids[:42])
        self.assertEqual(ids[42], HALT_PRIMARY)
        self.assertNotIn('rejected', log)

    def test_every_exported_operation_validates(self):
        self.assertEqual(len(self.names), 22)
        over_limit = set()
        for name, results in self.results.items():
            failed = {r['id']: r['error'] for r in results if not r['ok']}
            # Refusals under the current rule (these validate directly, with no declared SDK): the Purifier row its
            # charge levels fire only when charged (AMBIGUOUS, so it needs allow_unverified_effect since SDK 0.28.0,
            # which ModBuilder emits once the project is bound to that SDK), and a Maxigun backpack capacity above the
            # game's 1023 deposit limit (docs/backpack-ammo.md). Registered through the export's SDK 0.27.0 wrapper,
            # the Purifier edit applies as a legacy operation (docs/legacy-sdk-compatibility.md; the packaged
            # user-report-full-project scenario and tests/test_legacy_sdk_compatibility.py).
            expected = {PURIFIER_DRAG} if any(r['id'] == PURIFIER_DRAG for r in results) else set()
            for op, error in failed.items():
                if 'deposit.capacity' in error:
                    self.assertIn('(1 to 1023): the live deposit amount is the engine network field', error)
                    expected.add(op)
                    over_limit.add(name)
                else:
                    self.assertIn('allow_unverified_effect', error)
            self.assertEqual(set(failed), expected, name)
        # Exactly the variants that set the backpack to 1500 rounds.
        self.assertEqual(over_limit, {name for name in self.names if 'deposit.capacity,expect=1000,value=1500'
            in (GENERATED / (name + '.lua')).read_text(encoding='utf-8')})
        self.assertEqual(over_limit, {'C-original-plus-maxigun-backpack', 'E2-maxigun-plus-backpack',
            'E3-backpack-only'})
        self.assertTrue(all(r['ok'] for r in self.results['F-SG-20-Halt']))
        self.assertEqual({r['id'] for r in self.results['F-SG-20-Halt']}, {HALT_PRIMARY,
            'gui-object-a2877e602fe56952c82a3500', 'gui-object-2a64b61fd1fed19c196b1ab7'})

    def test_the_full_project_has_no_structural_collision(self):
        results = self.results['A-original']
        owners = {}
        for index, row in enumerate(results):
            for change in row['changes']:
                owners.setdefault(change['backing'], set()).add(index)
            self.assertLessEqual(len({c['weapon'] for c in row['changes']}), 1, row['id'])
        self.assertEqual(len(results), 133)
        self.assertEqual(sum(len(r['changes']) for r in results), 407)   # 408 minus the refused Purifier row
        self.assertTrue(all(len(indices) == 1 for indices in owners.values()))

    def test_variants_do_not_reorder_shared_operations(self):
        full = operation_ids((GENERATED / 'A-original.lua').read_text(encoding='utf-8'))
        for name in ('B-no-stratagem', 'B4-no-entity', 'C-original-plus-maxigun-backpack', 'D3-ma5c-plus-stratagem'):
            ids = operation_ids((GENERATED / (name + '.lua')).read_text(encoding='utf-8'))
            common = [i for i in full if i in set(ids)]
            self.assertEqual([i for i in ids if i in set(full)], common, name)

    def test_the_wrapper_enforces_the_sdk_version(self):
        wrapped = (GENERATED / 'A-original.wrapped.lua').read_text(encoding='utf-8')
        self.assertIn("local x,y,z=version('0.27.0')", wrapped)
        self.assertIn("'HD2Runtime dependency version mismatch'", wrapped)


HALT_ISSUE = ROOT / 'tests/fixtures/user-reports/modbuilder-issue-2-halt/generated'


class HaltIssueTests(unittest.TestCase):
    """ModBuilder issue 2: ModBuilder 1.3.1 exports editing SG-20 Halt fields next to unrelated weapons."""

    @classmethod
    def setUpClass(cls):
        cls.names = sorted(path.name[:-4] for path in HALT_ISSUE.glob('*.lua') if not path.name.endswith('.wrapped.lua'))
        cls.results = probe_variants(cls.names, HALT_ISSUE)
        cls.recorded = json.loads((HALT_ISSUE / 'results.json').read_text(encoding='utf-8'))

    def test_the_published_runtime_aborted_the_addon_at_the_first_halt_operation(self):
        published = self.recorded['published_0_27_0']
        for name in ('H1-halt-all', 'H2-halt-damage-only'):
            self.assertIn('field is not exposed for SG-20 Halt', published[name]['startupError'], name)
            self.assertEqual(published[name]['registered'], 0, name)
        self.assertEqual(published['H0-control-no-halt']['results'], ['APPLIED'] * 3)
        current = self.recorded['current_tree']
        self.assertTrue(all(v['startupError'] is None and set(v['results']) == {'APPLIED'} for v in current.values()))

    def test_every_operation_validates_with_halt_damage_and_non_damage_edits_together(self):
        self.assertEqual(self.names, ['H0-control-no-halt', 'H1-halt-all', 'H2-halt-damage-only', 'H3-halt-sway-only'])
        for name, results in self.results.items():
            self.assertEqual([r['error'] for r in results if not r['ok']], [], name)
        weapons = {change['weapon'] for row in self.results['H1-halt-all'] for change in row['changes']}
        self.assertEqual(weapons, {'SG-20 Halt', 'AR-23 Liberator', 'SMG-32 Reprimand'})
        fields = json.loads((HALT_ISSUE / 'summary.json').read_text(encoding='utf-8'))['variants'][1]['fields']
        halt = [f for f in fields if f.startswith('SG-20 Halt ')]
        # Damage, projectile, rounds and weapon fields of both feeds, all in one export.
        for prefix in ('damage.primary.', 'damage.alternate.', 'projectile.primary.', 'projectile.alternate.',
                'rounds.', 'weapon.'):
            self.assertTrue(any(f.split(' ', 2)[2].startswith(prefix) for f in halt), prefix)

    def test_operation_ids_are_unique_in_every_export(self):
        for name in self.names:
            source = (HALT_ISSUE / (name + '.lua')).read_text(encoding='utf-8')
            ids = re.findall(r"\bid='([^']+)'", source)
            self.assertEqual(len(ids), len(set(ids)), name)

    def test_a_rejected_operation_never_stops_later_ones_and_duplicate_ids_warn_once(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local lines={}
require('hd2runtime/runtime/log').emit=function(line)lines[#lines+1]=line end
local function count(needle)local n=0;for _,l in ipairs(lines)do if l:find(needle,1,true)then n=n+1 end end;return n end
local handles
require('hd2runtime/runtime/events').run_as('mods/test/halt_issue',function()
 handles={
  hd2.ensure({patch={id='same',target=hd2.weapon('AR-23 Liberator'),field=hd2.fields.weapon.sway,expect=1,value=1.1}}),
  hd2.ensure({plan={id='halt-plan',operations={
   {id='ok',target=hd2.weapon('SG-20 Halt'):attack('feed_primary'):projectile(),allow_shared=true,
    changes={{field=hd2.fields.projectile.drag,expect=0.3,value=0.33}}},
   {id='bad',target=hd2.weapon('SG-20 Halt'):attack('feed_primary'):projectile(),allow_shared=true,
    changes={{field='damage.no_such_field',expect=1,value=2}}}}}}),
  hd2.ensure({patch={id='same',target=hd2.weapon('SMG-32 Reprimand'),field=hd2.fields.weapon.sway,expect=1,value=1.1}}),
  hd2.ensure({patch={id='same',target=hd2.weapon('SMG-32 Reprimand'),field=hd2.fields.weapon.ergonomics,expect=1,
   value=1.1}}),
  hd2.ensure({patch={id='after',target=hd2.stratagem('Orbital Precision Strike'),
   field=hd2.fields.stratagem.definition_cooldown,expect=80,value=5}})}
end)
assert(#handles==5,'an operation was dropped')
assert(handles[2].status=='rejected'and handles[2].error:find('field is not exposed for SG-20 Halt',1,true))
assert(count('ensure halt-plan rejected: field is not exposed for SG-20 Halt')==1)
-- Registration continued after the refused plan: the later operations are real handles, not rejections.
assert(handles[3].status~='rejected'and handles[5].status~='rejected')
-- The repeated id warns exactly once, and the operations still register.
assert(count('another operation of mods/test/halt_issue already uses this id')==1,tostring(#lines))
return 'ok'
'''), b'ok')


class RuntimeContractTests(unittest.TestCase):
    def test_halt_feed_fields_resolve_to_their_own_branch(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local writes=require('hd2runtime/domains/player_weapon_writes')
local halt=hd2.weapon('SG-20 Halt')
local primary=writes.validate_patch{id='a',target=halt:attack('feed_primary'):projectile(),allow_shared=true,
 field=hd2.fields.damage.player_durable_damage,expect=10,value=20}
assert(primary.changes[1].canonical_field=='damage.primary.durable_damage')
assert(primary.changes[1].descriptor.backing.branch=='primary')
local alternate=writes.validate_patch{id='b',target=halt:attack('feed_alternate'):projectile(),allow_shared=true,
 field=hd2.fields.damage.status_1_strength,expect=1,value=3}
assert(alternate.changes[1].canonical_field=='damage.alternate.status_1_strength')
-- A feed never resolves to the other feed's branch: the alternate baseline on the primary feed is refused.
local ok=pcall(writes.validate_patch,{id='c',target=halt:attack('feed_primary'):projectile(),allow_shared=true,
 field=hd2.fields.damage.player_standard_damage,expect=6,value=9})
assert(not ok)
-- Branch-qualified constants (what ModBuilder should emit) keep working.
writes.validate_patch{id='d',target=halt:attack('feed_primary'):projectile(),allow_shared=true,
 field=hd2.fields.damage.primary_standard_damage,expect=35,value=26}
return 'ok'
'''), b'ok')

    def test_startup_version_line_is_emitted_once(self):
        version = (ROOT / 'VERSION').read_text().strip()
        out = run(r'''
local lines={}
package.loaded['hd2runtime/runtime/log']={emit=function(line)lines[#lines+1]=line end}
require('hd2runtime/api/hd2')
package.loaded['hd2runtime/api/hd2']=nil
require('hd2runtime/api/hd2')
require('hd2runtime/api/hd2')
return table.concat(lines,'\n')
''').decode()
        self.assertEqual(out.splitlines(), [f'[HD2Runtime] HD2Runtime {version} initialized (API 1)'])
        metadata = (ROOT / 'domains/metadata.lua').read_text(encoding='utf-8')
        self.assertIn(f'["version"]="{version}"', metadata)

    def test_packaged_version_source(self):
        import validate_packaged_runtime as packaged
        self.assertEqual(packaged.startup_line('0.27.0', 1), '[HD2Runtime] HD2Runtime 0.27.0 initialized (API 1)')
        self.assertIn('registration-isolation', packaged.SCENARIOS)
        self.assertEqual(packaged.EXTRAS['registration-isolation']['rejected'],
            {'isolation-invalid': 'field is not exposed for SG-20 Halt'})
        self.assertEqual(packaged.EXTRAS['user-report-full-project']['watches'], 133)
        # The SDK 0.27.0 export's Purifier edit applies (as a legacy operation) instead of being refused.
        self.assertNotIn('rejected', packaged.EXTRAS['user-report-full-project'])
        self.assertEqual(packaged.EXTRAS['user-report-full-project']['legacy'], {PURIFIER_DRAG: ['projectile.drag']})
        for name in ('user-report-ma5c-capacity-only', 'user-report-ma5c-plus-stratagem', 'user-report-maxigun-weapon',
                'user-report-maxigun-plus-backpack', 'user-report-halt-dual-feed', 'user-report-spray-and-pray-damage',
                'user-report-sai-heat', 'user-report-sickle-heat', 'user-report-orbital-cooldown',
                'example-runtime-effect-diagnostics'):
            self.assertIn(name, packaged.SCENARIOS)


class EffectModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog = json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())
        cls.summary = catalog['summary']['effect']
        cls.fields = {(w['name'], f['semanticFieldId']): f for w in catalog['weapons'] for f in w['fields']}
        cls.ownership = json.loads((ROOT / 'research/field-ownership-F5FEE03DCFDB.json').read_text())

    def test_ownership_audit(self):
        summary = self.ownership['summary']
        self.assertEqual(summary['byStatus'], {'ACTIVE_AT_INSTANTIATION': 1856, 'AMBIGUOUS': 30, 'OVERRIDDEN': 42})
        self.assertEqual(summary['editableByStatus'], {'ACTIVE_AT_INSTANTIATION': 1226, 'AMBIGUOUS': 21})
        self.assertEqual(summary['editableOverriddenByField'], {})

    def test_published_effects(self):
        self.assertEqual(self.summary['editableFieldInstances'], {'ACTIVE_AT_INSTANTIATION': 1385,
            'ACTIVE_DIRECT': 1473, 'AMBIGUOUS': 138, 'DORMANT_OR_METADATA': 51})
        self.assertNotIn('OVERRIDDEN', self.summary['editableFieldInstances'])
        magazine = self.fields[('MA5C Assault Rifle', 'magazine.capacity')]['effect']
        self.assertEqual((magazine['activeSource'], magazine['appliesWhen'], magazine['instantiationOnly']),
            ('ACTIVE_AT_INSTANTIATION', 'weapon_build', True))
        heat = self.fields[('LAS-12 Sai', 'heat.heat_per_shot')]['effect']
        self.assertEqual(heat['activeSource'], 'AMBIGUOUS')
        self.assertEqual(heat['overriddenWhenEquipped'], ['Laser Heatsink (Blaster). Improved Heatcapacity'])
        self.assertEqual(self.fields[('LAS-16 Sickle', 'heat.heat_per_shot')]['effect']['activeSource'],
            'ACTIVE_AT_INSTANTIATION')
        double = self.fields[('LAS-17 Double-Edge Sickle', 'damage.standard_damage')]
        self.assertEqual(double['effect']['activeSource'], 'DORMANT_OR_METADATA')
        self.assertEqual(double['acknowledgement'], 'allow_unverified_effect')
        self.assertIn('LAS-16 Sickle', double['effect']['reason'])
        purifier = self.fields[('PLAS-101 Purifier', 'projectile.drag')]
        self.assertEqual((purifier['effect']['activeSource'], purifier['acknowledgement']),
            ('AMBIGUOUS', 'allow_unverified_effect'))
        status = self.fields[('AR-23 Liberator', 'damage.status_1_type')]['effect']
        self.assertEqual((status['activeSource'], status['gameplayEffectProven']), ('ACTIVE_DIRECT', True))
        self.assertEqual(self.fields[('AR-23 Liberator', 'attack.primary.projectile')]['effect']['activeSource'],
            'OVERRIDDEN')
        for key, field in self.fields.items():
            effect = field.get('effect')
            if effect and field['editable'] and effect['activeSource'] in ('AMBIGUOUS', 'DORMANT_OR_METADATA') \
                    and field['backing'].get('kind') == 'settings':
                self.assertEqual(field.get('acknowledgement'), 'allow_unverified_effect', key)
                self.assertFalse(field.get('liveEvidence'), key)


HMG_READ_BUDGET = ROOT / 'tests/fixtures/user-reports/hmg-read-budget'
# The MG-206 plan exactly as reported: (operation, field, expect, value).
HMG_PLAN = [
    ('support-d0a433eb59e88faa485f1573', 'projectile.drag', 0.3, 0.1),
    ('support-d0a433eb59e88faa485f1573', 'projectile.pellet_count', 1, 2),
    ('support-d0a433eb59e88faa485f1573', 'projectile.penetration_slowdown', 0.25, 0.05),
    ('support-d0a433eb59e88faa485f1573', 'projectile.velocity', 980, 1960),
    ('support-9401c3d9683daa4817216b5d', 'weapon.fire_rate', 600, 1150),
    ('support-82b8fff675e3ca5aec780860', 'reload.duration', 5.5, 5),
    ('support-afdfc9922ea1555ac2bf3aed', 'weapon.ergonomics', 0, 30),
    ('support-afdfc9922ea1555ac2bf3aed', 'weapon.horizontal_spread', 5, 1),
    ('support-afdfc9922ea1555ac2bf3aed', 'weapon.recoil_climb_horizontal', 15, 3),
    ('support-afdfc9922ea1555ac2bf3aed', 'weapon.recoil_climb_vertical', 30, 6),
    ('support-afdfc9922ea1555ac2bf3aed', 'weapon.recoil_drift_horizontal', 50, 10),
    ('support-afdfc9922ea1555ac2bf3aed', 'weapon.recoil_drift_vertical', 80, 10),
    ('support-afdfc9922ea1555ac2bf3aed', 'weapon.vertical_spread', 5, 1),
    ('support-7e472931eaa978f00de204f8', 'magazine.magazines_from_supply', 2, 8),
    ('support-7e472931eaa978f00de204f8', 'magazine.spare_magazines', 2, 10),
    ('support-7e472931eaa978f00de204f8', 'magazine.starting_magazines', 1, 8),
    ('support-7e472931eaa978f00de204f8', 'weapon.capacity', 100, 300),
    ('support-bd9b831b96f7775ccfa8375d', 'damage.player_durable_damage', 35, 75),
    ('support-bd9b831b96f7775ccfa8375d', 'damage.player_standard_damage', 150, 250),
]


class HmgReadBudgetTests(unittest.TestCase):
    """The user's HMG mod (ModBuilder 1.3.1, SDK 0.27.0): its MG-206 plan exceeded the guarded read budget."""

    def test_the_fixture_is_the_users_exact_package(self):
        source = (HMG_READ_BUDGET / 'addon.lua').read_text(encoding='utf-8')
        wrapped = (HMG_READ_BUDGET / 'HMG.wrapped.lua').read_text(encoding='utf-8')
        self.assertIn(source, wrapped)
        self.assertTrue(wrapped.startswith('-- HD2-Addon: mods/strynox/las_98\n'))
        self.assertIn("local x,y,z=version('0.27.0')", wrapped)
        report = json.loads((HMG_READ_BUDGET / 'build-report.json').read_text(encoding='utf-8'))
        self.assertEqual((report['builder'], report['sdk_version']), ('HD2Runtime ModBuilder 1.3.1 / .NET 10', '0.27.0'))

    def test_the_mg206_plan_is_the_reported_shape_and_every_operation_validates(self):
        source = (HMG_READ_BUDGET / 'addon.lua').read_text(encoding='utf-8')
        plan = source[source.index("id='support-plan-ff0bc43a596f53f27e5dfd80'"):]
        found, operation = [], None
        for line in plan.splitlines():
            op = re.search(r"id='(support-[0-9a-f]{24})'", line)
            if op:
                operation = op.group(1)
            for field, expect, value in re.findall(
                    r'field=hd2\.fields\.([\w.]+),expect=([\d.]+),value=([\d.]+)', line):
                found.append((operation, field, float(expect), float(value)))
            single = re.search(r'field=hd2\.fields\.([\w.]+),$', line.strip())
            if single:
                pending = single.group(1)
            if line.strip().startswith('expect='):
                expect_value = float(line.strip()[7:-1])
            if line.strip().startswith('value='):
                found.append((operation, pending, expect_value, float(line.strip()[6:-1])))
        self.assertEqual(found, [(o, f, float(e), float(v)) for o, f, e, v in HMG_PLAN])
        results = probe_variants(['addon'], HMG_READ_BUDGET)['addon']
        self.assertEqual([r['error'] for r in results if not r['ok']], [])
        # Two plans (FLAM-40 and MG-206): 13 and 19 changes.
        self.assertEqual([len(r['changes']) for r in results], [13, 19])
        self.assertEqual({c['weapon'] for c in results[1]['changes']}, {'MG-206 Heavy Machine Gun'})

    def test_the_recorded_profile_explains_the_failure_and_the_fix(self):
        recorded = json.loads((HMG_READ_BUDGET / 'results.json').read_text(encoding='utf-8'))
        hmg = recorded['plans']['support-plan-ff0bc43a596f53f27e5dfd80']
        flam = recorded['plans']['support-plan-a7d11bc364c94023b9ff184d']
        # 19 fields, 53 contexts of which 33 are distinct (the delivery proof captured by each of 6 operations).
        self.assertEqual((hmg['changes'], hmg['contexts'], hmg['uniqueContexts']), (19, 53, 33))
        self.assertEqual(hmg['before']['guardedBytes'], hmg['before']['fullChecks'] * hmg['contextBytes'] + 2 * 19 * 4)
        self.assertGreater(hmg['before']['guardedBytes'], recorded['oldBudgetBytes'])
        self.assertLess(flam['before']['guardedBytes'], recorded['oldBudgetBytes'])
        for plan in (hmg, flam):
            after = plan['after']
            self.assertEqual(after['status'], 'APPLIED')
            self.assertEqual(after['guardedBytes'],
                after['fullChecks'] * plan['uniqueContextBytes'] + 2 * plan['changes'] * 4)
            self.assertLessEqual(after['guardedBytes'], after['allowance'])
            self.assertLessEqual(after['allowance'], recorded['readCeilingBytes'])

    def test_the_exact_package_is_a_packaged_runtime_scenario(self):
        packaged = importlib.util.spec_from_file_location('validate_packaged_runtime',
            ROOT / 'scripts/validate_packaged_runtime.py')
        module = importlib.util.module_from_spec(packaged)
        packaged.loader.exec_module(module)
        self.assertEqual(module.SCENARIOS['user-report-hmg-read-budget'](),
            (HMG_READ_BUDGET / 'HMG.wrapped.lua').read_text(encoding='utf-8'))
        self.assertEqual(module.EXTRAS['user-report-hmg-read-budget']['watches'], 2)


if __name__ == '__main__':
    unittest.main()
