"""Post-migration validation and confidence summary.

  py scripts/validate_migration.py validation/migrations/<target-build> [--runtime-zip <zip>] [--quick]

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
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from migration import overlay, source  # noqa: E402
import apply_migration  # noqa: E402

SNAPSHOT_VALIDATORS = ('validate_entity_authoring_snapshot', 'validate_stratagem_authoring_snapshot',
    'validate_attachment_authoring_snapshot', 'validate_backpack_ammo_snapshot', 'validate_booster_authoring_snapshot',
    'validate_fire_mode_authoring_snapshot', 'validate_options_binding_snapshot', 'validate_pod_payload_snapshot',
    'validate_reticle_authoring_snapshot', 'validate_vehicle_weapon_authoring_snapshot',
    'validate_support_weapon_authoring_snapshot', 'validate_weapon_authoring_snapshot',
    'validate_reference_recreations')


def run(command, name):
    result = subprocess.run([sys.executable, '-B', *command], cwd=ROOT, capture_output=True, text=True)
    tail = (result.stdout + result.stderr).strip().splitlines()[-3:]
    print(('ok   ' if result.returncode == 0 else 'FAIL ') + name)
    return {'name': name, 'ok': result.returncode == 0, 'tail': tail}


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('migration')
    parser.add_argument('--runtime-zip', type=Path, help='built runtime ZIP for packaged validation')
    parser.add_argument('--quick', action='store_true', help='skip the full unit-test suite')
    parser.add_argument('--skip-snapshot', action='store_true', help='skip snapshot validators (no snapshot here)')
    args = parser.parse_args(argv)
    directory = Path(args.migration)
    summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
    checks = [migration_safety(directory)]
    current = overlay.runtime_build()
    file = overlay.OVERLAY
    stale_overlay = file.is_file() and overlay.load() is None
    checks.append({'name': 'overlay targets the active build', 'ok': not stale_overlay,
        'overlay': file.is_file(), 'activeBuild': current['exeSha256'][:12]})
    print(('ok   ' if not stale_overlay else 'FAIL ') + 'overlay targets the active build')
    checks.append(run(['scripts/regenerate_domains.py', '--check'], 'generator freshness'))
    if not args.skip_snapshot:
        for name in SNAPSHOT_VALIDATORS:
            checks.append(run(['scripts/' + name + '.py'], name))
    checks.append(run(['scripts/validate_examples.py'], 'examples'))
    checks.append(run(['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_sdk.py'], 'SDK tests'))
    checks.append(run(['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_migration.py'], 'migration tests'))
    if not args.quick:
        checks.append(run(['-m', 'unittest', 'discover', '-s', 'tests'], 'full test suite'))
    if args.runtime_zip:
        checks.append(run(['scripts/validate_packaged_runtime.py', str(args.runtime_zip)], 'packaged runtime'))
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
