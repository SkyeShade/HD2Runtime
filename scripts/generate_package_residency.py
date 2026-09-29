"""Generate the package-residency tables from research/package-residency-F5FEE03DCFDB.json.

Outputs:
* domains/package_residency.lua: runtime pins for the native loader (RVAs plus the exact code bytes each call
  re-proves), the engine residency layout, and the semantic dependency catalog (semantic key / resource ->
  owning package). The runtime never accepts a package identity from a caller; it only resolves one here.
* sdk/AssetDependencyCapabilities.json: public metadata (no package or resource IDs): per semantic object,
  whether its package dependency is known and auto-loadable, how it was derived, and live-test state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migration import overlay as migration_overlay  # noqa: E402  build-migration hook
import generate_entity_authoring  # noqa: E402
import package_residency_evidence as evidence  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/package-residency-F5FEE03DCFDB.json'
LUA_OUTPUT = ROOT / 'domains/package_residency.lua'
JSON_OUTPUT = ROOT / 'sdk/AssetDependencyCapabilities.json'
CONTRACT = 'hd2runtime.asset_dependencies.v1'


def outputs(research_path=RESEARCH):
    research = json.loads(Path(research_path).read_text(encoding='utf-8'))
    loader = research['loader']
    g, e = loader['gameDll'], loader['engine']
    packages, dependencies, by_resource = {}, {}, {}
    public = []
    live_objects = set(evidence.live_objects())
    live_packages = set(evidence.live_packages(research['catalog']))
    for key, item in research['catalog'].items():
        dep = item['dependency']
        known = bool(item['known'])
        name = (dep or {}).get('name')
        entry = {'key': key, 'label': item['label'], 'kind': item['kind'],
            'packageDependency': {'known': known, 'autoLoadSupported': known,
                'derivation': (dep or {}).get('via'), 'package': name.rsplit('/', 1)[-1] if name else None,
                'packageNamed': bool(name) if known else None,
                'liveTested': key in live_objects,
                'packageLiveLoaded': known and dep['package'] in live_packages,
                'blocker': None if known else ('No loadout package owns this object and no vanilla holder with a '
                    'package references it, so Runtime cannot name the assets it needs.')}}
        public.append(entry)
        if not known:
            continue
        pid = dep['package']
        # Some packages are proven by identity but their name is not reversed; they get a display name only.
        packages.setdefault(pid, {'name': name or 'unnamed loadout package of ' + item['label'],
            'named': bool(name), 'inBundleDatabase': dep['inBundleDatabase']})
        dependencies[key] = dict({'package': pid, 'via': dep['via'], 'label': item['label']},
            **({'live': True} if key in live_objects else {}))
        by_resource.setdefault(item['resource'], pid)
    runtime = {'version': 1, 'build': research['build'],
        'loader': {'requestRva': g['requestRva'], 'releaseRva': g['releaseRva'],
            'requestProof': g['requestProof'], 'releaseProof': g['releaseProof'],
            'instanceGlobalRva': g['instanceGlobalRva'], 'refcountMap': g['refcountMap'],
            'engineApiGlobalRva': g['engineApiGlobalRva'],
            'engine': {'managerGlobalRva': e['managerGlobalRva'], 'packageManager': e['packageManager'],
                'resourceManager': e['resourceManager'], 'listCount': e['listCount'], 'list': e['list'],
                'packageId': e['packageId'], 'partCount': e['partCount'], 'parts': e['parts'],
                'partState': e['partState'], 'loadedState': e['loadedState'], 'queue': e['queue'],
                'hasLoadedRva': e['hasLoadedRva'], 'hasLoadedProof': e['hasLoadedProof'],
                'findPackageRva': e['findPackageRva'], 'findPackageProof': e['findPackageProof']}},
        'packages': dict(sorted(packages.items())), 'dependencies': dict(sorted(dependencies.items())),
        'byResource': dict(sorted(by_resource.items())),
        'policy': {'retain': 'session', 'maxHeldPackages': 64, 'loadTimeoutSeconds': 90,
            'pollSeconds': 0.25, 'refcountFillLimit': 0.75}}
    summary = dict(research['summary'], packages=len(packages),
        unnamedPackages=sum(not p['named'] for p in packages.values()),
        liveTestedObjects=len(live_objects), liveLoadedPackages=len(live_packages),
        liveProvenFamilies=sorted(k for k, v in evidence.families().items() if v['packageResidency'] == 'LIVE_PROVEN'))
    live = evidence.live()
    document = {'contract': CONTRACT, 'schemaVersion': 1, 'build': research['build'],
        'model': ['A reference swap only works in game when the replacement\'s assets are resident. Helldivers 2 '
            'loads an item\'s generated loadout package when some player carries the item (or level generation '
            'places it); a swapped-in item nobody carries shows up missing (for example a purple question-mark '
            'pickup or an invisible projectile).',
            'Runtime requests the same package through the game\'s own reference-counted package system before '
            'it writes such a reference, waits until the engine reports it resident, and only then applies the '
            'write (status WAITING_FOR_ASSETS while loading, ASSET_UNAVAILABLE if it cannot).'],
        'residencyVersusCompatibility': ('packageDependency answers only whether Runtime can load the assets a '
            'reference needs. Whether the game behaves correctly with that reference in that slot is a separate '
            'question answered by each domain (for example allow_unverified_reference on pod and mount swaps).'),
        'referenceFamilies': evidence.families(),
        'liveEvidence': {'recorded': live['recorded'], 'runtimeCommit': live['runtime']['commit'],
            'control': live['control'], 'tests': [{'id': t['id'], 'project': t['project'], 'family': t['family'],
                'result': t['result'], 'donorCarried': t['donorCarried'], 'observations': t['observations']}
                for t in live['tests']]},
        'policy': runtime['policy'], 'summary': summary, 'objects': public,
        'safety': {'arbitraryPackages': False, 'callerSuppliedIdentities': False, 'writes': 0}}
    return {LUA_OUTPUT: '-- Generated by scripts/generate_package_residency.py; do not edit.\nreturn '
        + generate_entity_authoring.lua(migration_overlay.apply('package_residency', runtime)) + '\n',
        JSON_OUTPUT: json.dumps(document, indent=2) + '\n'}


def generate(check=False, research_path=RESEARCH):
    stale = []
    for path, body in outputs(research_path).items():
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(path)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale package residency outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
