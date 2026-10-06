"""Enemy gib ("splootch") research and the whole-body gib threshold field: the decision is GoreGroupInfo +0 of the
class's first whole-body gore group on the killing hit, read from the shared GoreComponentData table, published as
hd2.fields.gore.whole_body_gib_damage on hd2.enemy(name) for the 23 eligible classes."""
import json
import re
import sys
import unittest

from support import ROOT, run

RESEARCH = json.loads((ROOT / 'research/enemy-gib-threshold-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
ENEMIES = json.loads((ROOT / 'research/enemy-authoring-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
SDK = (ROOT / 'sdk/EnemyAuthoringCapabilities.json').read_text(encoding='utf-8')
CATALOG = json.loads(SDK)
OVERLAY = json.loads((ROOT / 'validation/enemy-gib-threshold-snapshot.json').read_text(encoding='utf-8'))
FIELD = 'gore.whole_body_gib_damage'


def pins():
    return {p['rva']: p for group in RESEARCH['code'].values() for p in group}


def by_class():
    return {c['className']: c for c in RESEARCH['classes']}


class GibThresholdResearchTests(unittest.TestCase):
    def test_the_research_is_read_only_and_build_pinned(self):
        source = RESEARCH['source']
        self.assertEqual(source['writes'], 0)
        self.assertEqual(source['build'], 'F5FEE03DCFDB')
        self.assertEqual(len(source['missionSnapshots']), 3)
        everything = pins()
        self.assertGreaterEqual(len(everything), 100)
        for pin in everything.values():
            self.assertTrue(pin['bytes'] and pin['asm'] and pin['role'], pin)
        # The decision itself, pinned instruction by instruction.
        self.assertEqual(everything['0x9251A8']['asm'], 'call 0x9057d0')
        self.assertEqual(everything['0x905E39']['asm'], 'movss xmm1, dword ptr [r14]')
        self.assertEqual(everything['0x905E4F']['asm'], 'comiss xmm0, xmm1')
        self.assertEqual(everything['0x905E58']['asm'], 'cmp byte ptr [r14 + 0x362], 0')
        self.assertEqual(everything['0x905904']['asm'], 'addss xmm0, xmm0')
        self.assertEqual(everything['0x9250F7']['asm'], 'cmp dword ptr [rbp - 0x7c], 8')
        self.assertEqual(everything['0x5085B1']['asm'], 'mov r11, qword ptr [rax + 0xf12ba8]')
        self.assertEqual(everything['0x568E51']['ripTarget'], '0x33264D0')

    def test_the_layout_matches_the_type_library(self):
        geometry = RESEARCH['layout']['geometry']
        self.assertEqual((geometry['indexRows'], geometry['records'], geometry['recordSize'], geometry['groups'],
            geometry['groupStride']), (418, 209, 33488, 38, 872))
        group = {m['offset']: m for m in RESEARCH['layout']['goreGroupInfo']}
        self.assertEqual((group[0]['storage'], group[0]['nameLength']), ('FP32', 10))     # destroy threshold
        self.assertEqual((group[4]['storage'], group[4]['nameLength']), ('FP32', 16))     # secondary threshold
        self.assertEqual((group[8]['storage'], group[8]['nameLength']), ('FP32', 22))     # impulse scale
        self.assertEqual((group[866]['storage'], group[866]['nameLength']), ('UINT8', 10))  # whole-body flag
        self.assertEqual(RESEARCH['layout']['unlistedGroupMembers'], [])

    def test_no_health_value_enters_the_decision(self):
        isolation = RESEARCH['evaluatorIsolation']
        self.assertFalse(isolation['decisionCallsHealthSettingsGetter'])
        self.assertIn('0x9235F0', isolation['evaluatorCallers'])
        refs = {(c['scope'], c['offset']): c['applyDamageReferences']
            for c in RESEARCH['applyDamageHealthReferences']['candidates']}
        for unread in (('record', 40), ('record', 44), ('record', 21916), ('zone', 328), ('zone', 436)):
            self.assertEqual(refs[unread], [], unread)                 # UnitSize, mass and unknown floats
        self.assertIn('0x924472', refs[('zone', 340)])                  # the zone cap shapes the damage
        self.assertIn('0x9244F2', refs[('record', 24)])                 # constitution: the death gate
        self.assertIn('0x923F39', refs[('zone', 248)])

    def test_the_loaded_table_is_the_datalibrary_definition(self):
        for snapshot in RESEARCH['snapshots']:
            equal = snapshot['goreTableLoadedEqualsDatalibrary']
            self.assertTrue(equal['indexOwners'] and equal['allRecords'], snapshot['snapshot'])
            self.assertGreater(snapshot['goreManager']['liveInstances'], 0)
        self.assertEqual(RESEARCH['entityDeltas']['entityDeltasTouchingGore'], [])

    def test_per_class_thresholds_and_terminid_only_splootch(self):
        table = {row['className']: row for row in RESEARCH['comparison']}
        self.assertEqual(table['scavenger_tier_1']['wholeBodyThreshold'], 400)
        self.assertEqual(table['hunter_tier_1']['wholeBodyThreshold'], 500)
        self.assertEqual(table['warrior_tier_1']['wholeBodyThreshold'], 750)
        self.assertEqual(table['warrior_big']['wholeBodyThreshold'], 750)
        self.assertEqual((table['warrior_plus']['verdict'], table['warrior_plus']['wholeBodyThreshold']),
            ('WHOLE_BODY_DISABLED', -1))
        for cls in ('boomer', 'boomer_nurser', 'charger', 'strider', 'conscript_tier_2', 'soldier',
                'lieutenant_base', 'berserker'):
            self.assertEqual(table[cls]['verdict'], 'NO_WHOLE_BODY_GROUP', cls)
        classes = by_class()
        self.assertEqual(len(classes), ENEMIES['summary']['classes'])
        gibbing = [c for c in classes.values() if c['verdict'] == 'WHOLE_BODY_GIB']
        self.assertTrue(gibbing)
        self.assertEqual({c['faction'] for c in gibbing}, {'terminids'})
        for c in classes.values():
            if c['gore']:
                self.assertTrue(c['gore']['uniqueOwner'], c['className'])
                whole = c['gore']['wholeBodyGroup']
                if whole:
                    self.assertEqual(c['gore']['wholeBodyThreshold'], whole['destroyThreshold'])
                    self.assertEqual(whole['recordOffset'], whole['index'] * 872)

    def test_the_answer_rejects_overkill_ratio_and_force(self):
        hypotheses = RESEARCH['answer']['hypotheses']
        for key in ('overkillThreshold', 'ratioOfHitToMaxHealth', 'explosionForceThreshold'):
            self.assertTrue(hypotheses[key].startswith('NO'), key)
        for key in ('perEnemyDamageThreshold', 'gibDismemberThreshold', 'nativeDecisionOnMultipleValues'):
            self.assertTrue(hypotheses[key].startswith('YES'), key)
        # Same family threshold across very different health: it cannot be a ratio of health.
        ratios = RESEARCH['summary']['wholeBodyThresholdToMainHealthRatios']
        self.assertLess(min(ratios), 1)
        self.assertGreater(max(ratios), 6)
        self.assertIn('STRONG', RESEARCH['answer']['confidence']['wholeBodyDestructionIsTheVisibleSplootch'])

    def test_the_research_records_the_exposure(self):
        exposure = RESEARCH['exposure']
        self.assertEqual((exposure['decision'], exposure['field']), ('EXPOSED', 'hd2.fields.' + FIELD))
        self.assertEqual(exposure['acknowledgement'], 'allow_unverified_effect until the live test below passes')
        self.assertEqual(exposure['liveTestProject'], 'examples/projects/GibThresholdTest')
        for item in by_class().values():
            whole = item['gore'] and item['gore']['wholeBodyGroup']
            if whole:   # the guards a write re-proves: actors, flags with +866 set, earlier groups cleared
                self.assertEqual([g['offset'] for g in whole['guards'][:2]],
                    [whole['index'] * 872 + 340, whole['index'] * 872 + 864])
                self.assertEqual(int(whole['guards'][1]['hex'][4:6], 16), 1)
                self.assertEqual(len(whole['guards']), 2 + whole['index'])


class GibThresholdFieldTests(unittest.TestCase):
    """The public field: eligibility, baselines, value rule, acknowledgement and the native backing."""

    def instances(self):
        return {i['target']['enemy']: i for i in CATALOG['fieldInstances'] if i['semanticFieldId'] == FIELD}

    def test_every_eligible_class_carries_its_research_baseline(self):
        research = by_class()
        eligible = {name for name, c in research.items() if c['verdict'] == 'WHOLE_BODY_GIB'} | {'warrior_plus'}
        self.assertEqual(len(eligible), 23)
        names = {c['className']: c['name'] for c in CATALOG['classes']}
        instances = self.instances()
        self.assertEqual(set(instances), {names[c] for c in eligible})
        self.assertEqual(CATALOG['summary']['goreFieldInstances'], 23)
        for cls in eligible:
            item = instances[names[cls]]
            self.assertEqual(item['currentDefault'], research[cls]['gore']['wholeBodyThreshold'], cls)
            self.assertTrue(item['editable'])
            self.assertEqual(item['target'], {'resource': 'enemy', 'enemy': names[cls], 'path': 'entity'})
            self.assertEqual(item['effect']['activeSource'], 'ACTIVE_DIRECT')
            self.assertEqual(item['disabledValue'], -1)
        self.assertEqual(instances['Hive Guard']['currentDefault'], -1)
        self.assertEqual({instances[names[c]]['currentDefault'] for c in eligible}, {400, 500, 750, -1})
        model = CATALOG['model']['fields'][FIELD]
        self.assertEqual((model['type'], model['unit'], model['acknowledgement'], model['range'], model['valueRule']),
            ('number', 'damage', 'allow_unverified_effect', [-1, 100000], '-1, or 0 < value <= 100000'))
        self.assertIn('Electricity counts double', model['semantics'])
        self.assertIn('already alive', model['lifecycle'])
        self.assertNotRegex(SDK, r'0x[0-9A-Fa-f]{8}|recordIndex|indexRow')   # no native identity published

    def test_the_backing_is_the_first_whole_body_group_of_the_own_record(self):
        lua = (ROOT / 'domains/enemy_authoring.lua').read_text(encoding='utf-8')
        backings = re.findall(r'id="gore\.whole_body_gib_damage",path="entity",currentDefault=(-?\d+),editable=true,'
            r'backing=\{component="GoreComponentData",recordIndex=(\d+),indexRow=(\d+),ownerCount=1,uniqueOwner=true,'
            r'offset=(\d+),storage="f32",width=4,goreGroup=(\d+),guards=\{\{offset=(\d+),hex="([0-9a-f]+)"\},'
            r'\{offset=(\d+),hex="([0-9a-f]{8})"\}\}', lua)
        self.assertEqual(len(backings), 23)
        research = {c['gore']['recordIndex']: c for c in RESEARCH['classes'] if c['gore']}
        for default, record, row, offset, group, actors_at, actors, flags_at, flags in backings:
            item = research[int(record)]
            self.assertEqual((int(row), int(group), int(offset)), (item['gore']['indexRow'], 0, 0))
            self.assertEqual((int(actors_at), int(flags_at)), (340, 864))
            self.assertEqual(flags[4:6], '01')                          # +866: the whole-body flag
            self.assertEqual(actors, item['gore']['wholeBodyGroup']['guards'][0]['hex'])
            self.assertEqual(int(default), item['gore']['wholeBodyThreshold'])

    def test_value_rule_acknowledgement_and_eligibility(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local writes=require('hd2runtime/domains/enemy_writes')
local F=hd2.fields.gore.whole_body_gib_damage
assert(F=='gore.whole_body_gib_damage')
local warrior=hd2.enemy('warrior_tier_2')
local function patch(target,expect,value,ack)
 return writes.validate_patch{id='gib',target=target,field=F,expect=expect,value=value,allow_unverified_effect=ack}
end
local function refused(needle,...)
 local ok,why=pcall(patch,...)
 assert(not ok and tostring(why):find(needle,1,true),tostring(why))
end
local spec=patch(warrior,750,400,true)
local d=spec.changes[1].descriptor
assert(d.backing.component=='GoreComponentData'and d.backing.goreGroup==0 and d.backing.offset==0 and not d.shared)
assert(d.acknowledgement=='allow_unverified_effect'and d.acknowledgementReason:find('live-confirmed',1,true))
for _,value in ipairs({-1,0.5,400,430,450,750,100000})do patch(warrior,750,value,true)end
patch(hd2.enemy('Hive Guard'),-1,750,true)
for _,bad in ipairs({0,-0.5,-2,-100,100000.5,100001})do refused('reviewed range',warrior,750,bad,true)end
refused('finite',warrior,750,0/0,true);refused('finite',warrior,750,math.huge,true)
refused('finite',warrior,750,-math.huge,true)
refused('allow_unverified_effect',warrior,750,400,nil)
refused('expect differs',warrior,700,400,true)
for _,name in ipairs({'Charger','Bile Titan','boomer','Stalker','soldier','lieutenant_base','Marauder','dragon',
  'Watcher','tank_turret_heavycannon'})do refused('not exposed',hd2.enemy(name),750,400,true)end
refused('not exposed',warrior:zone(0),750,400,true)
local found
for _,f in ipairs(warrior:describe().fields)do if f.semanticFieldId==F then found=f end end
assert(found and found.currentDefault==750 and found.min==-1 and found.max==100000)
return 'ok'
'''), b'ok')


class GibThresholdRuntimeTests(unittest.TestCase):
    """Profile, migration view, snapshot overlay writes and the live-test artifact."""

    def test_the_profile_locates_gore_component_data(self):
        profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
        entry = re.search(r'\["GoreComponentData"\]=\{([^}]*)\}', profile).group(1)
        for part in ('["index"]=230', '["indices"]=418', '["records"]=209', '["record_offset"]=6688',
                '["stride"]=33488'):
            self.assertIn(part, entry)
        self.assertEqual(RESEARCH['entityDeltas']['goreComponentTypeIndex'], 230)
        self.assertIn("'GoreComponentData'", (ROOT / 'scripts/import_fixtures.py').read_text(encoding='utf-8'))
        sys.path.insert(0, str(ROOT / 'scripts'))
        from migration import build_view
        self.assertIn('GoreComponentData', build_view.COMPONENTS)
        offset = int(re.search(r'\["offset"\]=(\d+)', entry).group(1))
        fixture = json.loads((ROOT / 'tests/fixtures/reference.json').read_text(encoding='utf-8'))
        spans = {e['offset']: len(e['hex']) // 2 for e in fixture['entity']}
        self.assertEqual(spans[offset - 4], 4 + 28 + 6688)               # framing and every index row
        self.assertIn("'GoreComponentData'", (ROOT / 'domains/enemy_writes.lua').read_text(encoding='utf-8'))

    def test_the_snapshot_overlay_writes_exactly_the_target(self):
        self.assertEqual((OVERLAY['status'], OVERLAY['fixtureFallback'], OVERLAY['eligibleClasses']),
            ('VALIDATED', 'disabled', 23))
        trips = OVERLAY['roundTrips']
        self.assertEqual({k: (t['class'], t['from'], t['to']) for k, t in trips.items()}, {
            'warrior_tier_2': ('warrior_tier_2', 750, 400), 'hive_guard': ('Hive Guard', -1, 750),
            'scavenger_tier_1': ('scavenger_tier_1', 400, -1),
            'warrior_big_tier2_max': ('warrior_big_tier2', 750, 100000)})
        for key, trip in trips.items():
            self.assertEqual(trip['writes'], 1, key)
            self.assertGreaterEqual(trip['targetBytesChanged'], 1, key)
            self.assertEqual(trip['targetOffsetInRecord'], 0, key)
            self.assertEqual((trip['tableBytesCompared'], trip['otherRecordsUnchanged'],
                trip['limbGroupBytesUnchanged']), (7005680, 208, 33488 - 872), key)
            self.assertTrue(trip['healthRecordUnchanged'] and trip['protectionRestored'] and trip['restored'], key)
            self.assertEqual(trip['protectionChanges'], 2, key)
        combined = OVERLAY['combined']
        self.assertEqual((combined['classes'], combined['writes'], combined['restored']), (23, 23, True))
        self.assertLess(combined['contextBytes'], combined['contextCeiling'])
        self.assertLess(combined['readAllowance'], combined['readCeiling'])
        self.assertLess(combined['readerBytes'], combined['readerCeiling'])
        self.assertEqual(set(OVERLAY['rejections']), {'not eligible: Charger', 'not eligible: soldier',
            'not eligible: dragon', 'not eligible: Watcher', 'value 0', 'value -0.5', 'value -2', 'value 100001',
            'value NaN', 'value inf', 'missing acknowledgement', 'stale expect', 'whole-body flag cleared',
            'actor list changed', 'index row moved', 'third-party value'})
        self.assertIn('guard at +864', OVERLAY['rejections']['whole-body flag cleared'])
        self.assertIn('guard at +340', OVERLAY['rejections']['actor list changed'])
        self.assertIn('enemy gore record ownership changed', OVERLAY['rejections']['index row moved'])
        self.assertTrue(OVERLAY['rejections']['third-party value'].startswith('CONFLICT'))

    def test_the_live_test_artifact(self):
        project = ROOT / 'examples/projects/GibThresholdTest'
        source = (project / 'src/addon.lua').read_text(encoding='utf-8')
        manifest = json.loads((project / 'hd2runtime.json').read_text(encoding='utf-8'))
        # 0.2.0 EXTREME: every eligible class (23) at 1 or -1, a toggle restores vanilla.
        self.assertEqual((project / 'VERSION').read_text().strip(), '0.2.0')
        self.assertEqual(manifest['requires']['hd2runtime']['min_version'], '0.30.0-dev')
        self.assertIn('mod_options_menu', manifest['optional'])
        self.assertIn("local BANNER='GIB THRESHOLD 0.2.0 EXTREME BUILD'", source)
        self.assertIn('values={1,-1}', source)
        self.assertIn('field=hd2.fields.gore.whole_body_gib_damage,', source)
        self.assertIn('expect=vanilla,value=burst', source)
        self.assertIn('enabled=active', source)
        self.assertIn('allow_unverified_effect=true', source)
        catalog = json.loads((ROOT / 'sdk/EnemyAuthoringCapabilities.json').read_text(encoding='utf-8'))
        eligible = {}

        def walk(node):
            if isinstance(node, dict):
                if node.get('semanticFieldId') == FIELD:
                    eligible[node['target']['enemy']] = node['currentDefault']
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(catalog)
        listed = {name: int(value) for name, value in re.findall(r"\{'([^']+)',(-?\d+)\}", source)}
        self.assertEqual(listed, eligible)
        self.assertEqual(len(listed), 23)
        readme = (project / 'README.md').read_text(encoding='utf-8')
        self.assertIn('GIB THRESHOLD 0.2.0 EXTREME BUILD', readme)
        packaged = (ROOT / 'scripts/validate_packaged_runtime.py').read_text(encoding='utf-8')
        self.assertIn("'example-gib-threshold-test': {'menu': MENU_STUB, 'watches': 23", packaged)
        report = json.loads((ROOT / 'validation/example-projects.json').read_text(encoding='utf-8'))
        result = report['results']['GibThresholdTest']
        self.assertEqual((result['status'], len(result['operations'])), ('VALIDATED', 23))

if __name__ == '__main__':
    unittest.main()
