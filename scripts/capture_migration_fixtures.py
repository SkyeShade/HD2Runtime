"""Capture migration-validator outputs as regression fixtures, to prove an optimized engine is equivalent.

  py scripts/capture_migration_fixtures.py build/test-artifacts/fixtures-before
  py scripts/capture_migration_fixtures.py build/test-artifacts/fixtures-after
  py scripts/capture_migration_fixtures.py --compare build/test-artifacts/fixtures-before build/test-artifacts/fixtures-after

Recorded, each in its own file:

* same-build: the working tree migrated onto a second capture of the active build (every field EXACT);
* cross-build: the working tree migrated onto the previous build's retained datalibrary (moved identities, changed
  baselines and layouts, ambiguous/lost/blocked fields, fail-closed code tables);
* synthetic: every engine.run / apply_migration.verify / overlay / cache outcome produced by tests/test_migration.py
  (moved, baseline changed, layout changed, ambiguous, lost, scope widened, stale offset, corrupted cache and
  overlay artifacts), in call order, including the exact error messages.

Real runs write their report files through scripts/migrate_build.py (--no-history), so the fixtures include the
exact report ordering. Offline tooling; nothing here runs in game.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402

SAME_BUILD_SNAPSHOT = 'F5FEE03DCFDB-20260927T155654Z.hd2snap'
PREVIOUS_BUILD = 'D8E23968D141'
SYNTHETIC = r'''
import json, sys, unittest
sys.path.insert(0, 'tests'); sys.path.insert(0, 'scripts')
import support  # noqa: F401  (path setup)
from migration import engine, overlay, build_view
import apply_migration
calls = []
def hook(module, name):
    original = getattr(module, name)
    def wrapper(*args, **kwargs):
        try:
            value = original(*args, **kwargs)
        except Exception as error:
            calls.append({'call': name, 'error': type(error).__name__ + ': ' + str(error)})
            raise
        if name == 'run':
            calls.append({'call': name, 'result': value})
        elif name == 'verify':
            calls.append({'call': name, 'result': value})
        return value
    setattr(module, name, wrapper)
hook(engine, 'run'); hook(apply_migration, 'verify'); hook(overlay, 'patch'); hook(build_view, 'from_snapshot')
import test_migration
names = ['SyntheticMigrationTests', 'ApplyTests', 'GeneratorHookTests', 'CacheTests']
suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(getattr(test_migration, n)) for n in names)
outcome = unittest.TextTestRunner(stream=sys.stderr, verbosity=0).run(suite)
json.dump({'tests': outcome.testsRun, 'failures': len(outcome.failures), 'errors': len(outcome.errors),
    'calls': calls}, sys.stdout, indent=1, sort_keys=True, default=repr)
'''


def migrate(output: Path, *args):
    subprocess.run([sys.executable, '-B', 'scripts/migrate_build.py', '--from-runtime', 'current', '--no-history',
        '--output', str(output), *args], cwd=ROOT, check=True)


def capture(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    snapshot = build_profile.snapshot_directory() / SAME_BUILD_SNAPSHOT
    if snapshot.is_file():
        migrate(folder / 'same-build', '--snapshot', str(snapshot))
    previous = build_profile.build(PREVIOUS_BUILD)
    datalibrary = build_profile.datalibrary(PREVIOUS_BUILD)
    if datalibrary.is_dir():
        migrate(folder / 'cross-build', '--datalibrary', str(datalibrary), '--build', PREVIOUS_BUILD)
    synthetic = subprocess.run([sys.executable, '-B', '-c', SYNTHETIC], cwd=ROOT, check=True, capture_output=True,
        text=True).stdout
    (folder / 'synthetic.json').write_text(synthetic, encoding='utf-8', newline='\n')
    print('captured', folder, 'previous build', previous['buildId'])


def normalized(path: Path):
    """Report files minus fields that legitimately differ between runs (output label/paths, cache reuse)."""
    data = json.loads(path.read_text(encoding='utf-8'))
    if path.name == 'summary.json':
        data.pop('cache', None)
        data.get('target', {}).pop('sources', None)
        data.pop('label', None)
    return data


def compare(before: Path, after: Path) -> list[str]:
    differences = []
    files = sorted({p.relative_to(before) for p in before.rglob('*') if p.is_file()}
        | {p.relative_to(after) for p in after.rglob('*') if p.is_file()})
    for relative in files:
        a, b = before / relative, after / relative
        if not a.is_file() or not b.is_file():
            differences.append(f'{relative}: present in only one capture')
        elif relative.suffix == '.json':
            if normalized(a) != normalized(b):
                differences.append(f'{relative}: content differs')
        elif relative.suffix == '.md':
            strip = lambda text: [line for line in text.splitlines() if 'cache' not in line.lower()
                and 'build/test-artifacts' not in line]
            if strip(a.read_text(encoding='utf-8')) != strip(b.read_text(encoding='utf-8')):
                differences.append(f'{relative}: report differs')
    return differences


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folders', nargs='+', type=Path)
    parser.add_argument('--compare', action='store_true')
    args = parser.parse_args(argv)
    if args.compare:
        before, after = args.folders
        differences = compare(before, after)
        for line in differences:
            print('DIFF', line)
        print('equivalent' if not differences else f'{len(differences)} difference(s)')
        raise SystemExit(1 if differences else 0)
    capture(args.folders[0])


if __name__ == '__main__':
    main()
