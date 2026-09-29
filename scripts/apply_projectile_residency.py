"""Apply the current package-residency evidence to the projectile composition graphs.

The composition research (scripts/research_weapon_composition.py) was captured before Runtime could load
packages; re-running it only to refresh residency would also churn unrelated capture metadata. This step rewrites
exactly the per-attack `residency` objects and the `residencyPolicy` summary from
scripts/package_residency_evidence.py, which the research script also uses, so both paths agree.

Outputs (in place): schemas/player_weapon_composition_catalog.json, sdk/ProjectileCompositionCapabilities.json,
sdk/PlayerWeaponProjectileReferenceGraph.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import package_residency_evidence as evidence  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'schemas/player_weapon_composition_catalog.json'
GRAPHS = (ROOT / 'sdk/ProjectileCompositionCapabilities.json', ROOT / 'sdk/PlayerWeaponProjectileReferenceGraph.json')


def residency_policy(weapons):
    attacks = [attack['residency'] for weapon in weapons for attack in weapon['attacks']]
    family = evidence.families()['projectile_reference']
    return {'preloadApiAvailable': True, 'automaticPackageLoading': True,
        'packageResidency': family['packageResidency'], 'basis': family['basis'],
        'knownSourceWeaponRequired': sorted({weapon['weapon'] for weapon in weapons for attack in weapon['attacks']
            if attack['residency']['observedWithoutLoader'] == 'SOURCE_WEAPON_REQUIRED'}),
        'autoLoadedSources': sum(r['classification'] == 'PACKAGE_AUTO_LOADED' for r in attacks),
        'unknownSourcesRemain': sum(r['classification'] == 'DEPENDENCY_UNRESOLVED' for r in attacks),
        'referenceCompatibility': ('Unchanged: a swap is allowed only between approved compatibility classes; '
            'package loading does not widen it.')}


def outputs():
    catalog, live = evidence.research()['catalog'], evidence.live()
    result = {}
    document = json.loads(CATALOG.read_text(encoding='utf-8'))
    for name, weapon in document['weapons'].items():
        for attack in weapon['attacks']:
            attack['residency'] = evidence.projectile_residency(name, attack['role'], catalog, live)
    result[CATALOG] = document
    for path in GRAPHS:
        graph = json.loads(path.read_text(encoding='utf-8'))
        for weapon in graph['weapons']:
            for attack in weapon['attacks']:
                attack['residency'] = evidence.projectile_residency(weapon['weapon'], attack['role'], catalog, live)
        graph['residencyPolicy'] = residency_policy(graph['weapons'])
        result[path] = graph
    return {path: json.dumps(body, indent=2) + '\n' for path, body in result.items()}


def generate(check=False):
    stale = []
    for path, body in outputs().items():
        if path.read_text(encoding='utf-8') != body:
            stale.append(path)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale projectile residency: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(p.relative_to(ROOT)) for p in generate(args.check)) or 'up to date')
