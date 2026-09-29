"""Central live-test evidence (schemas/live_evidence.json) for the generators.

A capability family is live_proven only when a user-run in-game test passed on it; only such families drop
allow_unverified_effect, and only within the scope recorded in the registry. Generators ask:

  live_evidence.proven(family)   -> publication dict for a live_proven family, else None
  live_evidence.family(family)   -> the registry entry (any status)
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'schemas/live_evidence.json'
_CACHE = {}


def load() -> dict:
    if 'registry' not in _CACHE:
        _CACHE['registry'] = json.loads(REGISTRY.read_text(encoding='utf-8'))
    return _CACHE['registry']


def family(name: str) -> dict:
    return load()['families'][name]


def families_of(test: dict) -> list[str]:
    """A test exercises one family, or several (`families`) when one run proves more than one capability."""
    return test.get('families') or [test['family']]


def tests(name: str, current: bool = False) -> list[dict]:
    """The runs recorded for a family; `current` drops runs a later session superseded."""
    return [dict(test, session=session['id'], date=session['date']) for session in load()['sessions']
        for test in session['tests'] if name in families_of(test) and not (current and test.get('supersededBy'))]


def proven(name: str) -> dict | None:
    """The compact evidence reference generators publish on a live-proven field, or None. The full record (scope,
    observations, behaviour) is published once, in sdk/LiveEvidenceCatalog.json."""
    entry = family(name)
    if entry['status'] != 'live_proven':
        return None
    runs = [run for run in tests(name, current=True) if run['result'] == 'PASS']
    return {'status': 'live_proven', 'family': name, 'tests': sorted({run['mod'] for run in runs}),
        'date': max(run['date'] for run in runs)}


def proven_target(name: str, target: str, field: str) -> dict | None:
    """Evidence for one exact (target, field) pair of a live-proven family scoped by `provenTargets`, else None. Only
    the tested target is promoted; the same member on other targets stays unpromoted."""
    evidence = proven(name)
    if not evidence:
        return None
    if not any(item['target'] == target and item['field'] == field for item in family(name).get('provenTargets') or []):
        return None
    return dict(evidence, target=target, field=field)


def proven_targets() -> dict:
    """Every promoted (target, field) pair across families: {(target, field): evidence}."""
    result = {}
    for name, entry in load()['families'].items():
        for item in entry.get('provenTargets') or []:
            evidence = proven_target(name, item['target'], item['field'])
            if evidence:
                result[(item['target'], item['field'])] = evidence
    return result
