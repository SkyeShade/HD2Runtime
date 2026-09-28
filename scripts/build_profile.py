"""Central build profile (schemas/build_profile.json): build fingerprints, reference snapshot and pinned
datalibrary for every known Helldivers 2 build. Research, validation and migration tooling read build-specific
identity from here instead of repeating it."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'schemas/build_profile.json'


def load() -> dict:
    return json.loads(PROFILE.read_text(encoding='utf-8'))


def build(build_id: str | None = None) -> dict:
    data = load()
    key = build_id or data['active']
    if key not in data['builds']:
        raise KeyError('unknown build ' + key + '; add it to schemas/build_profile.json')
    return dict(data['builds'][key], buildId=key)


def build_id_for(exe_sha256: str) -> str:
    """Builds are named by the first 12 hex digits of the executable SHA-256."""
    return exe_sha256.upper()[:12]


def snapshot_directory() -> Path:
    return Path(os.path.expandvars(load()['snapshotDirectory'].replace('%LOCALAPPDATA%', '$LOCALAPPDATA')))


def reference_snapshot(build_id: str | None = None) -> Path:
    name = build(build_id)['referenceSnapshot']
    if not name:
        raise FileNotFoundError('build has no reference snapshot')
    return snapshot_directory() / name


def datalibrary(build_id: str | None = None) -> Path:
    return (ROOT / build(build_id)['datalibrary']['path']).resolve()


def known_build(exe_sha256: str, dll_sha256: str) -> str | None:
    for key, item in load()['builds'].items():
        if item['exeSha256'].upper() == exe_sha256.upper() and item['gameDllSha256'].upper() == dll_sha256.upper():
            return key
    return None


ACTIVE = build()
BUILD_ID = ACTIVE['buildId']
SNAPSHOT = reference_snapshot()
SNAPSHOT_NAME = ACTIVE['referenceSnapshot']
FILEDIVER = datalibrary().parent
ENTITY_SHA256 = ACTIVE['datalibrary']['entitiesSha256']
TYPELIB_SHA256 = ACTIVE['datalibrary']['typelibSha256']
