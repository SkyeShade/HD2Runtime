"""Shared package-residency evidence for the generators.

Two questions are kept apart everywhere:
* package residency: are the replacement's assets loaded? Runtime answers this by loading the owning package
  (core/assets). Its proof level per reference family comes from research/package-residency-live-evidence.json.
* reference compatibility: does the game behave correctly with that reference in that slot? Package loading
  says nothing about it; each domain keeps its own acknowledgements for it.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/package-residency-F5FEE03DCFDB.json'
LIVE = ROOT / 'research/package-residency-live-evidence.json'

# Reference families that can depend on another package; the loader path is the same for all of them.
FAMILIES = {
    'pod_payload_pickup': 'A drop-pod rack slot referencing a pickup from another package.',
    'projectile_reference': 'A weapon attack referencing another weapon\'s projectile.',
    'explosion_reference': 'A terminal action referencing another weapon\'s explosion.',
    'vehicle_mount': 'A vehicle mount referencing another vehicle\'s mounted weapon.',
}
SAME_PATH = {'explosion_reference': 'projectile_reference'}


def research():
    return json.loads(RESEARCH.read_text(encoding='utf-8'))


def live():
    return json.loads(LIVE.read_text(encoding='utf-8'))


def families(evidence=None):
    evidence = evidence or live()
    out = {}
    for family, description in FAMILIES.items():
        tests = [t for t in evidence['tests'] if t['family'] == family]
        passed = [t['id'] for t in tests if t['result'] == 'PASS']
        state = 'LIVE_PROVEN' if passed else 'OFFLINE_PROVEN'
        basis = ('Live: the replacement loaded and worked with nobody carrying the donor item ('
            + ('tests ' if len(passed) > 1 else 'test ') + ', '.join(passed) + ').') if passed else (
            'Offline: native loader proofs, snapshot residency reads and the packaged-runtime simulation. '
            + ('Uses the same loader path and the same source-weapon packages as the live-proven '
                + SAME_PATH[family] + ' family; not separately live-tested.' if family in SAME_PATH else
                'Not live-tested' + ('; live test ' + ', '.join(t['id'] for t in tests) + ' was inconclusive.'
                    if tests else '.')))
        out[family] = {'description': description, 'packageResidency': state, 'basis': basis,
            'liveBuild': evidence['build'] if passed else None,
            'liveTests': [{'id': t['id'], 'project': t['project'], 'result': t['result']} for t in tests]}
    return out


def live_objects(evidence=None):
    evidence = evidence or live()
    return sorted({key for t in evidence['tests'] if t['result'] == 'PASS' for key in t['objects']})


def live_packages(catalog, evidence=None):
    return sorted({catalog[key]['dependency']['package'] for key in live_objects(evidence)
        if catalog.get(key, {}).get('dependency')})


def live_pairs(evidence=None):
    evidence = evidence or live()
    return [dict(pair, test=t['id'], project=t['project']) for t in evidence['tests'] if t['result'] == 'PASS'
        for pair in t.get('pairs', [])]


def source_dependency(catalog, name, role):
    item = catalog.get('projectile_source/' + name + ':' + role) or catalog.get('player_weapon/' + name)
    return item['dependency'] if item and item['known'] else None


def projectile_residency(name, role, catalog=None, evidence=None):
    """Residency of a weapon attack used as a projectile/explosion source."""
    catalog = catalog if catalog is not None else research()['catalog']
    evidence = evidence or live()
    dependency = source_dependency(catalog, name, role)
    observed = ('SOURCE_WEAPON_REQUIRED' if name == 'LAS-58 Talon' else
        'SELF_CONTAINED' if name == 'JAR-5 Dominator' else None)
    observed_evidence = ('Observed before automatic loading: the projectile was invisible until LAS-58 Talon '
        'was equipped.' if observed == 'SOURCE_WEAPON_REQUIRED' else
        'Observed Reprimand to JAR-5 gameplay swap remained functional.' if observed else None)
    live_tested = ('player_weapon/' + name) in live_objects(evidence)
    family = families(evidence)['projectile_reference']['packageResidency']
    if dependency:
        return {'classification': 'PACKAGE_AUTO_LOADED', 'package': (dependency['name'] or '').rsplit('/', 1)[-1] or None,
            'preloadSupported': True, 'packageResidency': family, 'liveTested': live_tested,
            'observedWithoutLoader': observed, 'observedEvidence': observed_evidence,
            'evidence': ('Live: the Reprimand fired this projectile correctly with nobody carrying the source '
                'weapon.' if live_tested else 'The source weapon\'s own loadout package; Runtime loads it before '
                'a swap from a weapon in another package.'),
            'reason': None}
    return {'classification': 'DEPENDENCY_UNRESOLVED', 'package': None, 'preloadSupported': False,
        'packageResidency': 'UNRESOLVED', 'liveTested': False, 'observedWithoutLoader': observed,
        'observedEvidence': observed_evidence,
        'evidence': 'No loadout package structurally owns this weapon resource.',
        'reason': 'Runtime cannot name the package, so it cannot load the source\'s assets.'}
