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


def tests(name: str) -> list[dict]:
    return [dict(test, session=session['id'], date=session['date']) for session in load()['sessions']
        for test in session['tests'] if test['family'] == name]


def proven(name: str) -> dict | None:
    """The compact evidence reference generators publish on a live-proven field, or None. The full record (scope,
    observations, behaviour) is published once, in sdk/LiveEvidenceCatalog.json."""
    entry = family(name)
    if entry['status'] != 'live_proven':
        return None
    runs = tests(name)
    return {'status': 'live_proven', 'family': name, 'tests': [run['mod'] for run in runs],
        'date': max(run['date'] for run in runs)}
