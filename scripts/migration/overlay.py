"""Build-migration overlay (schemas/build_migration.json), written by scripts/apply_migration.py and applied by
every domain generator to its runtime table just before serialization.

The overlay is keyed to one target build. It is applied only when the runtime profile (schemas/current.lua) is
that build; for any other build it is ignored (a generator can never apply a migration to the wrong build), and
with no overlay file the generators' output is unchanged. Each patch re-checks a guard (the field's semantic id or
instance key and its previous native coordinates) before changing anything, and fails loudly if the generated
table no longer matches what the migration reviewed.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / 'schemas/build_migration.json'
MISSING = object()


def runtime_build(root: Path = ROOT) -> dict:
    text = (root / 'schemas/current.lua').read_text(encoding='utf-8')
    return {'exeSha256': re.search(r'\["exe_sha"\]="([0-9A-F]+)"', text).group(1),
        'gameDllSha256': re.search(r'\["dll_sha"\]="([0-9A-F]+)"', text).group(1)}


def load(path: Path | None = None, root: Path = ROOT):
    """The overlay if it targets the current runtime profile's build, else None."""
    path = Path(path or OVERLAY)
    if not path.is_file():
        return None
    overlay = json.loads(path.read_text(encoding='utf-8'))
    target, build = overlay['target'], runtime_build(root)
    if (target['exeSha256'], target['gameDllSha256']) != (build['exeSha256'], build['gameDllSha256']):
        return None
    return overlay


def resolve(table, path):
    node = table
    for key in path:
        if isinstance(node, list):
            node = node[key] if isinstance(key, int) and 0 <= key < len(node) else MISSING
        elif isinstance(node, dict):
            node = node.get(key, MISSING)
        else:
            node = MISSING
        if node is MISSING:
            return MISSING
    return node


def _get(node, dotted):
    for part in dotted.split('.'):
        if not isinstance(node, dict) or part not in node:
            return MISSING
        node = node[part]
    return node


def _set(node, dotted, value):
    parts = dotted.split('.')
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value


def patch(module: str, table: dict, patches: list[dict]) -> dict:
    for item in patches:
        node = resolve(table, item['path'])
        if node is MISSING or not isinstance(node, dict):
            raise ValueError(f"{module}: migration patch {item['key']} no longer resolves ({item['path']})")
        for dotted, expected in item['guard'].items():
            if _get(node, dotted) != expected:
                raise ValueError(f"{module}: migration patch {item['key']} guard {dotted} differs "
                    f"({_get(node, dotted)!r} != {expected!r}); re-run the migration")
        for dotted, value in item['set'].items():
            _set(node, dotted, value)
    return table


def apply(module: str, table: dict, path: Path | None = None) -> dict:
    """Generator hook: patch `table` for the current build if an overlay targets it; otherwise return it as is."""
    overlay = load(path)
    if overlay is None:
        return table
    return patch(module, table, overlay['patches'].get(module, []))
