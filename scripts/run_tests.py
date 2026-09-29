"""Run the unit-test suite in parallel with exactly the tests, order and verdict of `unittest discover -s tests`.

  py scripts/run_tests.py                 # full suite, one worker per physical core
  py scripts/run_tests.py -v --jobs 1     # serial
  py scripts/run_tests.py -p test_sdk.py  # one module (fnmatch pattern, like unittest's -p)

Work units are test classes (no test module defines module-level fixtures, so setUpClass/tearDownClass run
exactly as they do serially). Each module's last unit runs "every class not scheduled elsewhere", so a class the
static scan misses is still run, never dropped. Every worker loads its module through unittest's own loader and
reports each test's outcome; the parent reassembles them in the loader's order, so the verbose listing, error
blocks and the final OK/FAILED line read as a serial run's would. A worker that crashes is reported as an error,
never skipped. Offline tooling; nothing here ships in the runtime.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import importlib
import json
from pathlib import Path
import sys
import time
import traceback
import unittest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'
sys.path.insert(0, str(ROOT / 'scripts'))
import parallel  # noqa: E402

MARKER = '@@HD2-TEST-RESULT '
TIMINGS = ROOT / 'build/test-timings.json'
SEPARATOR1, SEPARATOR2 = '=' * 70, '-' * 70


# -- worker ------------------------------------------------------------------------------------------------------------
class Recorder(unittest.TestResult):
    """Per-test outcomes in the words unittest's verbose runner prints."""

    def __init__(self):
        super().__init__()
        self.records = []

    @staticmethod
    def describe(test):
        doc = test.shortDescription() if hasattr(test, 'shortDescription') else None
        return '\n'.join((str(test), doc)) if doc else str(test)

    def _add(self, test, outcome, detail=None, kind=None):
        self.records.append({'id': test.id(), 'description': self.describe(test), 'outcome': outcome,
            'detail': detail, 'kind': kind})

    def addSuccess(self, test):
        super().addSuccess(test)
        self._add(test, 'ok')

    def addError(self, test, err):
        super().addError(test, err)
        self._add(test, 'ERROR', self.errors[-1][1], 'ERROR')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._add(test, 'FAIL', self.failures[-1][1], 'FAIL')

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._add(test, f'skipped {reason!r}')

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._add(test, 'expected failure')

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._add(test, 'unexpected success')

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            failure = issubclass(err[0], test.failureException)
            listed = self.failures if failure else self.errors
            self._add(subtest, 'FAIL' if failure else 'ERROR', listed[-1][1], 'FAIL' if failure else 'ERROR')


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def selected(test, selectors) -> bool:
    """A selector is a test class name or Class.method."""
    name = type(test).__name__
    return bool({name, name + '.' + getattr(test, '_testMethodName', '')} & set(selectors))


def worker(module_name: str, include: list[str] | None, exclude: list[str]) -> dict:
    sys.path.insert(0, str(TESTS))             # what `discover -s tests` does
    loader = unittest.TestLoader()
    try:
        tests = list(flatten(loader.loadTestsFromModule(importlib.import_module(module_name))))
    except Exception:                          # an import failure is a test error, exactly as discover reports it
        tests = list(flatten(loader.loadTestsFromName(module_name)))
    order = [test.id() for test in tests]
    classes = sorted({type(test).__name__ for test in tests})
    chosen = [test for test in tests if (selected(test, include) if include is not None
        else not selected(test, exclude))]
    result = Recorder()
    started = time.perf_counter()
    unittest.TestSuite(chosen)(result)
    return {'module': module_name, 'order': order, 'classes': classes, 'scheduled': [test.id() for test in chosen],
        'testsRun': result.testsRun,
        'records': result.records, 'skipped': len(result.skipped), 'expectedFailures': len(result.expectedFailures),
        'unexpectedSuccesses': len(result.unexpectedSuccesses), 'seconds': time.perf_counter() - started}


# -- planning ----------------------------------------------------------------------------------------------------------
def modules(pattern='test*.py') -> list[str]:
    """Test modules in `unittest discover` order (sorted file names). `pattern` may be a list of patterns."""
    patterns = [pattern] if isinstance(pattern, str) else list(pattern)
    return [path.stem for path in sorted(TESTS.iterdir(), key=lambda p: p.name)
        if path.suffix == '.py' and any(fnmatch.fnmatch(path.name, item) for item in patterns)]


CHUNK = 4                                      # tests per unit when a fixture-free class is split


def test_classes(module: str) -> dict[str, list[str] | None]:
    """Top-level classes deriving (directly or through a local base) from a *TestCase, with their test methods
    when the class may be split (a direct TestCase subclass without class-level fixtures), else None."""
    tree = ast.parse((TESTS / (module + '.py')).read_text(encoding='utf-8'))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = {base.attr if isinstance(base, ast.Attribute) else getattr(base, 'id', '') for base in node.bases}
            if any(base.endswith('TestCase') for base in bases) or bases & set(found):
                names = [item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
                fixtures = {'setUpClass', 'tearDownClass'} & set(names) or not any(base.endswith('TestCase')
                    for base in bases)
                found[node.name] = None if fixtures else sorted(name for name in names if name.startswith('test'))
    return dict(sorted(found.items()))


def plan(names: list[str]) -> list[dict]:
    """Units of work. Each module's last unit takes every test no other unit selected, so nothing is dropped."""
    units = []
    for module in names:
        selectors = []
        for name, methods in test_classes(module).items():
            if methods and len(methods) > CHUNK:
                selectors += [[name + '.' + method for method in methods[i:i + CHUNK]]
                    for i in range(0, len(methods), CHUNK)]
            else:
                selectors.append([name])
        explicit = selectors[:-1]
        units += [{'key': module + ':' + chosen[0], 'module': module, 'include': chosen, 'exclude': []}
            for chosen in explicit]
        units.append({'key': module + ':*', 'module': module, 'include': None,
            'exclude': [selector for chosen in explicit for selector in chosen]})
    return units


def schedule(units: list[dict]) -> list[str]:
    """Longest-first start order from the previous run's timings (scheduling only; never affects results)."""
    try:
        timings = json.loads(TIMINGS.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        timings = {}
    size = lambda unit: (TESTS / (unit['module'] + '.py')).stat().st_size / 1e5
    return [unit['key'] for unit in sorted(units, key=lambda unit: -timings.get(unit['key'], size(unit)))]


def run_unit(unit: dict) -> dict:
    command = ['scripts/run_tests.py', '--worker', unit['module'], '--include' if unit['include'] is not None
        else '--exclude', ','.join(unit['include'] if unit['include'] is not None else unit['exclude'])]
    outcome = parallel.run(command, unit['key'])
    lines = [line for line in outcome['stdout'].splitlines() if line.startswith(MARKER)]
    if outcome['returncode'] == 0 and lines:
        report = json.loads(lines[-1][len(MARKER):])
    else:                                      # the worker itself died: a hard error, with its output
        report = {'module': unit['module'], 'order': [], 'classes': [], 'scheduled': [], 'testsRun': 0, 'skipped': 0,
            'expectedFailures': 0, 'unexpectedSuccesses': 0, 'seconds': outcome['seconds'], 'records': [{
                'id': unit['key'], 'description': unit['key'] + ' (test worker)', 'outcome': 'ERROR', 'kind': 'ERROR',
                'detail': 'test worker exited with %s\n%s' % (outcome['returncode'],
                    (outcome['stdout'] + outcome['stderr'])[-20000:])}]}
    report['unit'] = unit
    report['wall'] = outcome['seconds']
    report['noise'] = outcome['stderr']
    return report


# -- aggregation -------------------------------------------------------------------------------------------------------
def run(pattern='test*.py', jobs=None, verbose=True, stream=None) -> dict:
    started = time.perf_counter()
    names = modules(pattern)
    units = plan(names)
    first = schedule(units)
    reports = parallel.map_ordered(run_unit, sorted(units, key=lambda unit: first.index(unit['key'])), jobs)
    by_module = {}
    for report in reports:
        by_module.setdefault(report['module'], []).append(report)
    records, problems, per_module = [], [], {}
    for module in names:
        shards = by_module.get(module, [])
        order = next((shard['order'] for shard in shards if shard['order']), [])
        position = {test_id: index for index, test_id in enumerate(order)}
        seen = [record for shard in shards for record in shard['records']]
        # Subtest records share their parent's position; setUpClass errors sort to their class's first test.
        rank = lambda record: position.get(record['id'].split(' ')[0], position.get(_parent(record['id'], order),
            len(order)))
        seen.sort(key=rank)
        ran = sum(shard['testsRun'] for shard in shards)
        crashed = [shard for shard in shards if not shard['order']]
        # Every test the loader found must be scheduled in exactly one unit.
        scheduled = sorted(test_id for shard in shards for test_id in shard['scheduled'])
        if not crashed and scheduled != sorted(order):
            problems.append(f'{module}: scheduled {len(scheduled)} tests, the loader found {len(order)}')
        records += seen
        per_module[module] = {'tests': ran, 'ok': all(record['kind'] is None for record in seen) and not crashed,
            'seconds': round(max((shard['wall'] for shard in shards), default=0), 2)}
    failures = [r for r in records if r['kind'] == 'FAIL']
    errors = [r for r in records if r['kind'] == 'ERROR']
    for problem in problems:
        errors.append({'description': 'test scheduling', 'detail': problem + '\n', 'kind': 'ERROR'})
    total = sum(report['testsRun'] for report in reports)
    skipped = sum(report['skipped'] for report in reports)
    expected = sum(report['expectedFailures'] for report in reports)
    unexpected = sum(report['unexpectedSuccesses'] for report in reports)
    elapsed = time.perf_counter() - started
    lines = [record['description'] + ' ... ' + record['outcome'] for record in records] if verbose else []
    blocks = []
    for flavour, items in (('ERROR', errors), ('FAIL', failures)):
        for record in items:
            blocks += [SEPARATOR1, f"{flavour}: {record['description']}", SEPARATOR2, record['detail'].rstrip('\n')]
    ok = not failures and not errors and not unexpected
    infos = [f'failures={len(failures)}'] * bool(failures) + [f'errors={len(errors)}'] * bool(errors) + \
        [f'skipped={skipped}'] * bool(skipped) + [f'expected failures={expected}'] * bool(expected) + \
        [f'unexpected successes={unexpected}'] * bool(unexpected)
    verdict = ('OK' if ok else 'FAILED') + (' (' + ', '.join(infos) + ')' if infos else '')
    text = '\n'.join(lines + ([''] if lines else []) + blocks + [SEPARATOR2,
        f"Ran {total} test{'s' if total != 1 else ''} in {elapsed:.3f}s", '', verdict]) + '\n'
    if stream is not None:
        stream.write(text)
    try:
        timings = json.loads(TIMINGS.read_text(encoding='utf-8')) if TIMINGS.is_file() else {}
        timings.update({r['unit']['key']: round(r['wall'], 2) for r in reports})
        TIMINGS.parent.mkdir(parents=True, exist_ok=True)
        TIMINGS.write_text(json.dumps(timings, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    except (OSError, ValueError):
        pass
    return {'ok': ok, 'text': text, 'testsRun': total, 'modules': per_module, 'failures': len(failures),
        'errors': len(errors), 'skipped': skipped, 'seconds': round(elapsed, 2), 'jobs': parallel.resolve(jobs)}


def _parent(test_id: str, order: list[str]) -> str:
    """An error holder such as 'setUpClass (module.Class)' belongs before that class's first test."""
    if '(' in test_id and test_id.endswith(')'):
        owner = test_id[test_id.index('(') + 1:-1]
        return next((known for known in order if known.startswith(owner + '.')), test_id)
    return test_id


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-p', '--pattern', default='test*.py')
    parser.add_argument('--json', type=Path, help='also write a machine-readable summary here')
    parser.add_argument('--worker', help=argparse.SUPPRESS)
    parser.add_argument('--include', help=argparse.SUPPRESS)
    parser.add_argument('--exclude', help=argparse.SUPPRESS)
    parallel.add_argument(parser)
    args = parser.parse_args(argv)
    if args.worker:
        try:
            report = worker(args.worker, args.include.split(',') if args.include is not None else None,
                [name for name in (args.exclude or '').split(',') if name])
        except Exception:
            traceback.print_exc()
            raise SystemExit(2)
        sys.stdout.write('\n' + MARKER + json.dumps(report) + '\n')
        return
    parallel.configure(args.jobs)
    result = run(args.pattern, args.jobs, args.verbose, sys.stderr)
    if args.json:
        args.json.write_text(json.dumps({k: v for k, v in result.items() if k != 'text'}, indent=1) + '\n')
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
