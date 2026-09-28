"""Re-identify a previous HD2Runtime release's mappings in a new Helldivers 2 build and report what broke.

  py scripts/migrate_build.py --from-runtime 0.26.1 --snapshot <new>.hd2snap [--datalibrary <dir>]
  py scripts/migrate_build.py --from-runtime current --datalibrary <dir> --exe-sha <sha> --dll-sha <sha>

The source of truth is the previous release's generated domain tables (semantic ids, native identities, baselines,
chains, links, scope and guards), evaluated in the build that release was generated for (its reference snapshot).
The target is a new snapshot (tables read through the production discovery path when its game.dll has a runtime
profile) and/or the new build's Filediver datalibrary (required when the type library changed or the build is
unknown). Output: validation/migrations/<target-build>[-<label>]/. Offline tooling; nothing here runs in game.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from migration import build_view, engine, report, source  # noqa: E402


def source_view(release):
    """The build the release was generated for, read from its reference snapshot (or pinned datalibrary)."""
    build_id = release['profile']['buildId']
    profile = build_profile.build(build_id)
    snapshot = build_profile.snapshot_directory() / profile['referenceSnapshot'] if profile.get(
        'referenceSnapshot') else None
    if snapshot and snapshot.is_file():
        return build_view.from_snapshot(snapshot)
    return build_view.from_datalibrary(build_profile.datalibrary(build_id), {
        'exeSha256': profile['exeSha256'], 'gameDllSha256': profile['gameDllSha256']})


def target_view(args):
    if args.snapshot:
        view = build_view.from_snapshot(Path(args.snapshot), Path(args.datalibrary) if args.datalibrary else None,
            use_cache=not args.no_cache)
    elif args.datalibrary:
        fingerprints = {}
        if args.build:
            profile = build_profile.build(args.build)
            fingerprints = {'exeSha256': profile['exeSha256'], 'gameDllSha256': profile['gameDllSha256']}
        if args.exe_sha:
            fingerprints['exeSha256'] = args.exe_sha.upper()
        if args.dll_sha:
            fingerprints['gameDllSha256'] = args.dll_sha.upper()
        if set(fingerprints) != {'exeSha256', 'gameDllSha256'}:
            raise SystemExit('a datalibrary-only target needs --build <id> or --exe-sha and --dll-sha')
        view = build_view.from_datalibrary(Path(args.datalibrary), fingerprints)
    else:
        raise SystemExit('pass --snapshot and/or --datalibrary for the new build')
    return view


def portable(sources):
    """Input descriptions without machine-specific absolute paths."""
    result = []
    for item in sources:
        path = Path(item['path'])
        try:
            shown = path.resolve().relative_to(ROOT.parent).as_posix()
            shown = '../' + shown if not path.resolve().is_relative_to(ROOT) else path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            shown = path.name
        result.append(dict(item, path=shown))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--from-runtime', default='current',
        help='previous release version (e.g. 0.26.1), a git revision, or "current" (working tree)')
    parser.add_argument('--snapshot', help='.hd2snap of the new build')
    parser.add_argument('--datalibrary', help="the new build's Filediver datalibrary directory")
    parser.add_argument('--build', help='known build id from schemas/build_profile.json (datalibrary-only targets)')
    parser.add_argument('--exe-sha', help='new helldivers2.exe SHA-256 (datalibrary-only targets)')
    parser.add_argument('--dll-sha', help='new game.dll SHA-256 (datalibrary-only targets)')
    parser.add_argument('--label', help='suffix for the output directory (e.g. the snapshot time for same-build runs)')
    parser.add_argument('--output', help='output directory (default validation/migrations/<target-build>[-label])')
    parser.add_argument('--no-cache', action='store_true', help='re-extract snapshot tables even if cached')
    parser.add_argument('--no-history', action='store_true',
        help='do not record fingerprints under research/build-history/')
    args = parser.parse_args(argv)

    release = source.resolve_ref(args.from_runtime)
    release['profile'] = source.release_profile(release)
    source_s = source_view(release)
    loaded = source.load_release(args.from_runtime, source_s)
    target = target_view(args)
    build_id = build_profile.build_id_for(target.build['exeSha256'])
    known = build_profile.known_build(target.build['exeSha256'], target.build['gameDllSha256'])
    out = Path(args.output) if args.output else ROOT / 'validation/migrations' / (
        build_id + ('-' + args.label if args.label else ''))
    print(f"source HD2Runtime {loaded['version']} ({loaded['ref']} @ {loaded['commit'][:12]}), build "
        f"{loaded['profile']['buildId']}; target build {build_id}")
    result = engine.run(source_s, target, loaded)
    meta = {'extractorVersion': build_view.EXTRACTOR_VERSION, 'label': out.name,
        'source': {'version': loaded['version'], 'ref': loaded['ref'], 'commit': loaded['commit'],
            'dirtyWorkingTree': loaded['dirty'], 'buildId': loaded['profile']['buildId'],
            'exeSha256': loaded['profile']['exeSha256'], 'gameDllSha256': loaded['profile']['gameDllSha256'],
            'buildProfile': loaded['profile']['buildId'], 'sources': portable(source_s.sources),
            'entitiesSha256': source_s.build.get('entitiesSha256'), 'typelibSha256': source_s.build.get('typelibSha256'),
            'snapshot': source_s.build.get('snapshot'), 'capturedAt': source_s.build.get('capturedAt')},
        'target': {'buildId': build_id, 'buildProfile': known, 'exeSha256': target.build['exeSha256'],
            'gameDllSha256': target.build['gameDllSha256'], 'snapshot': target.build.get('snapshot'),
            'capturedAt': target.build.get('capturedAt'), 'snapshotBytes': target.build.get('snapshotBytes'),
            'entitiesSha256': target.build.get('entitiesSha256'), 'typelibSha256': target.build.get('typelibSha256'),
            'typelibMemberFormat': target.build.get('typelibMemberFormat'), 'sources': portable(target.sources)},
        'cache': target.cache}
    summary = report.write(out, result, meta)
    if not args.no_history:
        for path in report.record_history(result, meta):
            print('history', path.relative_to(ROOT))
    print('wrote', out.relative_to(ROOT) if out.is_relative_to(ROOT) else out)
    print('totals', {k: v for k, v in summary['totals'].items() if v})
    print('confidence', summary['confidence'])
    if summary['confidence']['unsafeStaleWritesCarriedForward']:
        raise SystemExit('unsafe stale writes would be carried forward')


if __name__ == '__main__':
    main()
