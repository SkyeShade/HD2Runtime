"""The parallel validation pipeline must give exactly the serial verdicts.

--jobs 1 and multi-worker runs are compared for the test runner, packaged-runtime scenarios, sharded Lua
validators and migration classification; worker failures must surface, never be swallowed; and the test
planner must schedule every discovered test exactly once.
"""
import json
import unittest

from support import ROOT

import build_profile
import parallel
import run_tests
import sharded_validation
from migration import build_view as bv, engine, source


class MergeTests(unittest.TestCase):
    def test_counts_sum_tables_union_and_other_values_must_agree(self):
        merged = sharded_validation.merge([
            {'status': 'VALIDATED', 'fields': 3, 'byScope': {'a': 1}, 'scenarios': []},
            {'status': 'VALIDATED', 'fields': 4, 'byScope': {'a': 2, 'b': 1}, 'scenarios': {'x': {'writes': 1}}}])
        self.assertEqual(merged, {'status': 'VALIDATED', 'fields': 7, 'byScope': {'a': 3, 'b': 1},
            'scenarios': {'x': {'writes': 1}}})
        self.assertEqual(sharded_validation.merge([{'empty': []}, {'empty': []}]), {'empty': []})
        with self.assertRaisesRegex(ValueError, 'disagree'):
            sharded_validation.merge([{'status': 'VALIDATED'}, {'status': 'FAILED'}])
        with self.assertRaisesRegex(ValueError, 'disagree'):
            sharded_validation.merge([{'independentArms': True}, {'independentArms': False}])


SHARDED = r'''
local objects={}
for i=1,23 do objects[#objects+1]='object'..string.format('%02d',i)end
local result={objects=0,weight=0,byParity={},extras=0}
for _,name in ipairs(shard(objects))do
 local n=tonumber(name:sub(7))
 result.objects=result.objects+1;result.weight=result.weight+n*n
 local parity=n%2==0 and 'even' or 'odd'
 result.byParity[parity]=(result.byParity[parity]or 0)+1
end
if EXTRAS then result.extras=1;result.once='yes' end
local json=require('json')
return json.encode(result)
'''


class ShardedLuaTests(unittest.TestCase):
    def run_sharded(self, jobs, extras=True):
        json_module = (ROOT / 'primary_mapper/json.lua').read_text(encoding='utf-8')
        before = ('package.preload["json"]=function(...) return assert(loadstring(' + source.lua(json_module)
            + ',"json"))(...) end\n')
        return sharded_validation.run(before, SHARDED, jobs, extras=extras)

    def test_every_object_once_and_extras_once_for_any_job_count(self):
        serial = self.run_sharded(1)
        self.assertEqual((serial['objects'], serial['extras'], serial['once']), (23, 1, 'yes'))
        for jobs in (2, 3, 5):
            self.assertEqual(self.run_sharded(jobs), serial, jobs)
        without = self.run_sharded(4, extras=False)
        self.assertEqual((without['objects'], without['weight'], without['extras']), (23, serial['weight'], 0))

    def test_a_lua_error_in_any_worker_is_raised(self):
        with self.assertRaisesRegex(RuntimeError, 'shard failure 7'):
            parallel.lua_programs([[b'return "fine"'], [b'error("shard failure 7")'], [b'return "fine"']], {}, 3)
        self.assertEqual(parallel.lua_programs([[b'return "a"'], ['x', b'..""']], {'x': b'return "b"'}, 2),
            [b'a', b'b'])

    def test_worker_exceptions_propagate_from_the_thread_pool(self):
        def work(item):
            if item == 3:
                raise ValueError('item 3 failed')
            return item * 2
        with self.assertRaisesRegex(ValueError, 'item 3 failed'):
            parallel.map_ordered(work, range(6), 4)
        self.assertEqual(parallel.map_ordered(lambda item: item * 2, range(9), 4), [i * 2 for i in range(9)])


class TestRunnerTests(unittest.TestCase):
    def test_plan_schedules_every_discovered_test_exactly_once(self):
        loader = unittest.TestLoader()
        for module in ('test_patch', 'test_migration', 'test_parallel_validation'):
            units = [unit for unit in run_tests.plan([module])]
            tests = list(run_tests.flatten(loader.loadTestsFromName(module)))
            ids = [test.id() for test in tests]
            chosen = []
            for unit in units:
                chosen += [test.id() for test in tests if run_tests.selected(test, unit['include'])] \
                    if unit['include'] is not None else \
                    [test.id() for test in tests if not run_tests.selected(test, unit['exclude'])]
            self.assertEqual(sorted(chosen), sorted(ids), module)

    def test_parallel_and_serial_runs_report_identically(self):
        strip = lambda text: [line for line in text.splitlines() if not line.startswith('Ran ')]
        serial = run_tests.run(['test_stratagem_parser.py', 'test_weapon_heat.py'], jobs=1)
        wide = run_tests.run(['test_stratagem_parser.py', 'test_weapon_heat.py'], jobs=6)
        self.assertTrue(serial['ok'])
        self.assertEqual(strip(serial['text']), strip(wide['text']))
        self.assertEqual((serial['testsRun'], serial['modules']), (wide['testsRun'], {name: dict(item,
            seconds=serial['modules'][name]['seconds']) for name, item in wide['modules'].items()}))

    def test_a_broken_test_module_is_an_error_not_a_skip(self):
        report = run_tests.run_unit({'key': 'test_no_such_module:*', 'module': 'test_no_such_module',
            'include': None, 'exclude': []})
        self.assertEqual([record['kind'] for record in report['records']], ['ERROR'])
        self.assertIn('test_no_such_module', report['records'][0]['detail'])


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class PackagedRuntimeJobsTests(unittest.TestCase):
    def test_scenarios_report_identically_serial_and_parallel(self):
        import tempfile
        import build_release
        import validate_packaged_runtime as packaged
        scenarios = ['player-weapon-patch', 'booster-coverage', 'options-live', 'vehicle-weapon-tank']
        # Named with the version it packages: the validator checks the artifact name (prerelease names included).
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
            runtime_zip = build_release.build_runtime((ROOT / 'VERSION').read_text().strip(), folder=folder)
            serial = packaged.validate(runtime_zip, scenarios=scenarios, jobs=1)
            wide = packaged.validate(runtime_zip, scenarios=scenarios, jobs=4)
        self.assertEqual(json.dumps(serial, sort_keys=True), json.dumps(wide, sort_keys=True))
        self.assertEqual(list(wide['scenarios']), scenarios)


class MigrationEngineMemoTests(unittest.TestCase):
    def test_owner_index_matches_a_full_scan(self):
        table = bv.ComponentTable('X', 1, None, {5: (0, 0), 3: (0, 1), 9: (2, 2), 7: (1, 3)}, [b'', b'', b''], 0)
        for record in range(4):
            self.assertEqual(table.owners_of(record),
                sorted(r for r, (index, _) in table.owners.items() if index == record))
        self.assertEqual(table.owner_count, {0: 2, 2: 1, 1: 1})

    def test_layout_identity_memo_is_scoped_to_the_view_pair(self):
        member = lambda offset, name: {'offset': offset, 'size': 4, 'storage': 'FP32', 'atom': 'POD', 'count': 0,
            'nameLength': name, 'typeHash': 0}
        a, b = bv.Layout('A', 8, [member(0, 5), member(4, 6)]), bv.Layout('A', 8, [member(0, 5), member(4, 6)])
        grown = bv.Layout('A', 12, [member(0, 5), member(8, 7), member(4, 6)])
        source_view, target_view, other_view = bv.BuildView(), bv.BuildView(), bv.BuildView()
        self.assertEqual(engine.map_offset(source_view, a, target_view, b, 4, 4), (4, 'identical'))
        self.assertEqual(engine.map_offset(source_view, a, other_view, grown, 4, 4)[1], 'signature')
        self.assertEqual(engine.map_offset(source_view, a, target_view, b, 4, 4), (4, 'identical'))


if __name__ == '__main__':
    unittest.main()
