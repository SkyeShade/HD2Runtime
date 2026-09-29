"""Post-migration validation and confidence summary.

  py scripts/validate_migration.py validation/migrations/<target-build> [--runtime-zip <zip>] [--quick] [--jobs N]

Checks, in order (each one recorded in <migration>/post-validation.json):

  1. migration safety   plan re-simulated on the current generated tables: 0 unsafe stale writes, and no field
                        that depends on a BROKEN/AMBIGUOUS relationship is still writable
  2. overlay            schemas/build_migration.json is absent or targets the active runtime profile build
  3. generator freshness every generated domain table / SDK file equals a fresh generation (overlay included)
  4. snapshot validation every production snapshot validator against the active build's reference snapshot
  5. examples           every shipped example validated against the current API and snapshot baselines
  6. SDK/schema tests   tests/test_sdk.py, tests/test_migration.py (plus the full suite unless --quick)
  7. packaged runtime   scripts/validate_packaged_runtime.py on the built runtime ZIP (when --runtime-zip is given)

Snapshot validators and the packaged runtime prepare every write against the snapshot and never write.

Checks 3-5 are independent and run concurrently; so do the tests and the packaged runtime afterwards (the tests
read the validation records that 3-5 rewrite, so they never overlap them). Every check still runs in full and is
reported in the order above. Without --quick the full suite runs once and the SDK and migration test checks are
read from that same run (they are subsets of it). --jobs 1 reproduces the serial run.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from migration import overlay, source  # noqa: E402
import apply_migration  # noqa: E402
import parallel  # noqa: E402
import run_tests  # noqa: E402

SNAPSHOT_VALIDATORS = ('validate_entity_authoring_snapshot', 'validate_stratagem_authoring_snapshot',
    'validate_attachment_authoring_snapshot', 'validate_backpack_ammo_snapshot', 'validate_booster_authoring_snapshot',
    'validate_fire_mode_authoring_snapshot', 'validate_options_binding_snapshot', 'validate_pod_payload_snapshot',
    'validate_reticle_authoring_snapshot', 'validate_vehicle_weapon_authoring_snapshot',
    'validate_support_weapon_authoring_snapshot', 'validate_weapon_authoring_snapshot',
    'validate_throwable_authoring_snapshot', 'validate_reference_recreations', 'validate_coverage_pass_snapshot')
# Longest first, so the slowest validators set the phase's critical path instead of starting last.
SLOWEST_FIRST = ('validate_vehicle_weapon_authoring_snapshot', 'validate_throwable_authoring_snapshot',
    'validate_attachment_authoring_snapshot', 'validate_pod_payload_snapshot', 'validate_weapon_authoring_snapshot',
    'examples', 'validate_booster_authoring_snapshot', 'validate_fire_mode_authoring_snapshot')
TEST_CHECKS = (('SDK tests', 'test_sdk'), ('migration tests', 'test_migration'))


TIMINGS = {}


def report(result):
    """A check record from a finished subprocess (same shape as the serial runner's)."""
    tail = (result['stdout'] + result['stderr']).strip().splitlines()[-3:]
    print(('ok   ' if result['returncode'] == 0 else 'FAIL ') + result['name'])
    TIMINGS[result['name']] = result['seconds']
    return {'name': result['name'], 'ok': result['returncode'] == 0, 'tail': tail}


class phase:
    """Wall-clock timing of one pipeline phase (printed with --timings; never written to post-validation.json)."""

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.started = time.perf_counter()

    def __exit__(self, *exc):
        TIMINGS['[phase] ' + self.name] = time.perf_counter() - self.started


def migration_safety(directory: Path) -> dict:
    plan = json.loads((directory / 'plan.json').read_text(encoding='utf-8'))
    relationships = json.loads((directory / 'relationships.json').read_text(encoding='utf-8'))['relationships']
    build = overlay.runtime_build()
    active = overlay.load()
    targets_active = (plan['target']['exeSha256'], plan['target']['gameDllSha256']) == (build['exeSha256'],
        build['gameDllSha256'])
    # When the runtime profile is the migration's target build, the generated tables are what ships for it:
    # every field still writable there must sit on the proven target coordinates.
    unsafe = apply_migration.verify(plan, source.load_tables(source.resolve_ref('current')),
        plan['target']['buildId']) if targets_active else []
    broken = {tuple(block) for item in relationships if item['state'] in ('BROKEN', 'AMBIGUOUS')
        for block in item['blocks']}
    writable_broken = [key for key, decision in plan['decisions'].items()
        if decision['action'] != 'readonly' and (decision['domain'], decision['object']) in broken]
    ok = not unsafe and not writable_broken
    print(('ok   ' if ok else 'FAIL ') + 'migration safety')
    return {'name': 'migration safety', 'ok': ok, 'unsafeStaleWrites': len(unsafe),
        'writableDespiteBrokenRelationship': writable_broken[:20], 'overlayApplied': bool(active),
        'generatedTablesChecked': targets_active}


def test_checks(quick: bool, jobs) -> list[dict]:
    """SDK and migration tests, plus the full suite unless quick; the suite runs once and each check reads the
    modules it covers."""
    patterns = [module + '.py' for _, module in TEST_CHECKS] if quick else 'test*.py'
    result = run_tests.run(patterns, jobs, verbose=False)
    checks = []
    for name, module in TEST_CHECKS:
        item = result['modules'].get(module, {'ok': False, 'tests': 0})
        checks.append({'name': name, 'ok': item['ok'], 'tail': [f"Ran {item['tests']} tests", '',
            'OK' if item['ok'] else 'FAILED']})
    if not quick:
        checks.append({'name': 'full test suite', 'ok': result['ok'], 'tail': result['text'].strip().splitlines()[-3:]})
    for check in checks:
        print(('ok   ' if check['ok'] else 'FAIL ') + check['name'])
    if not result['ok']:
        print(result['text'], end='')      # the failures, as unittest prints them
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('migration')
    parser.add_argument('--runtime-zip', type=Path, help='built runtime ZIP for packaged validation')
    parser.add_argument('--quick', action='store_true', help='skip the full unit-test suite')
    parser.add_argument('--skip-snapshot', action='store_true', help='skip snapshot validators (no snapshot here)')
    parser.add_argument('--timings', action='store_true', help='print wall time per phase and check')
    parallel.add_argument(parser)
    args = parser.parse_args(argv)
    parallel.configure(args.jobs)
    started = time.perf_counter()
    directory = Path(args.migration)
    summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
    with phase('migration safety'):
        checks = [migration_safety(directory)]
    current = overlay.runtime_build()
    file = overlay.OVERLAY
    stale_overlay = file.is_file() and overlay.load() is None
    checks.append({'name': 'overlay targets the active build', 'ok': not stale_overlay,
        'overlay': file.is_file(), 'activeBuild': current['exeSha256'][:12]})
    print(('ok   ' if not stale_overlay else 'FAIL ') + 'overlay targets the active build')
    independent = [('generator freshness', ['scripts/regenerate_domains.py', '--check'])]
    if not args.skip_snapshot:
        independent += [(name, ['scripts/' + name + '.py']) for name in SNAPSHOT_VALIDATORS]
    independent.append(('examples', ['scripts/validate_examples.py']))
    with phase('freshness, snapshot validators, examples'):
        checks += [report(result) for result in parallel.run_commands(independent, args.jobs, SLOWEST_FIRST)]
    with phase('tests'):
        checks += test_checks(args.quick, args.jobs)
    if args.runtime_zip:
        with phase('packaged runtime'):
            checks.append(report(parallel.run(['scripts/validate_packaged_runtime.py', str(args.runtime_zip),
                '--jobs', str(parallel.resolve(args.jobs))], 'packaged runtime')))
    TIMINGS['[total]'] = time.perf_counter() - started
    if args.timings:
        print(f'\nTimings (jobs={parallel.resolve(args.jobs)})')
        for name, seconds in sorted(TIMINGS.items(), key=lambda item: -item[1]):
            print(f'  {seconds:7.1f}s  {name}')
    confidence = dict(summary['confidence'])
    confidence['unsafeStaleWritesCarriedForward'] = max(confidence['unsafeStaleWritesCarriedForward'],
        checks[0]['unsafeStaleWrites'])
    result = {'migration': directory.as_posix(), 'target': summary['target']['buildId'],
        'ok': all(check['ok'] for check in checks), 'checks': checks, 'confidence': confidence}
    (directory / 'post-validation.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8',
        newline='\n')
    print('\nConfidence summary')
    print(f"  Recovered automatically: {confidence['recoveredAutomaticallyPercent']}%")
    print(f"  Downgraded to read-only: {confidence['downgradedPercent']}%")
    print(f"  Needing manual review:   {confidence['manualReviewPercent']}%")
    print(f"  Unsafe stale writes carried forward: {confidence['unsafeStaleWritesCarriedForward']}")
    if not result['ok']:
        raise SystemExit('post-migration validation failed: ' + ', '.join(c['name'] for c in checks if not c['ok']))


if __name__ == '__main__':
    main()
