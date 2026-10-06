"""Candidate reports: the machine-readable output of a scan (research only).

A report lists candidates, never promotions. Each candidate carries its evidence and one confidence label; a
feature's own research script decides promotion with its reviewed proofs (owner, layout, active source, sharing,
lifecycle), exactly as before this toolkit.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402

SCHEMA = 'hd2runtime.scan.candidates/1'
CONFIDENCE = ('CONFIRMED', 'STRONG', 'PLAUSIBLE', 'UNKNOWN')
CONFIDENCE_RULES = {
    'CONFIRMED': 'independent proof: the native code that reads the member AND an exact published value or a passed '
                 'live test',
    'STRONG': 'a native read of the member OR an exact published value, plus a consistent hidden-name length and '
              'family differential',
    'PLAUSIBLE': 'layout, hidden-name length and family differential agree, but no active source is shown',
    'UNKNOWN': 'layout only',
}


def confidence(evidence: dict) -> str:
    """The label the evidence supports. evidence keys: codeRead, publishedExact, liveTest, nameLengthFit,
    differential (bools)."""
    code, published, live = evidence.get('codeRead'), evidence.get('publishedExact'), evidence.get('liveTest')
    fit, differential = evidence.get('nameLengthFit'), evidence.get('differential')
    if code and (published or live):
        return 'CONFIRMED'
    if (code or published) and fit and differential:
        return 'STRONG'
    if fit and differential:
        return 'PLAUSIBLE'
    return 'UNKNOWN'


def candidate(path: str, offset: int, storage: str, name_length, kind: str, values: dict, evidence: dict,
              proposed: str | None = None, notes=None, **extra) -> dict:
    label = confidence(evidence)
    item = {'path': path, 'offset': offset, 'storage': storage, 'nameLength': name_length, 'kind': kind,
        'values': values, 'evidence': evidence, 'confidence': label, 'proposedName': proposed,
        'proposedNameLengthFit': (proposed is not None and name_length is not None and len(proposed) == name_length)
            if proposed else None,
        'notes': list(notes or [])}
    item.update(extra)
    return item


def document(title: str, scope: dict, candidates: list[dict], **sections) -> dict:
    counts = {label: sum(1 for c in candidates if c.get('confidence') == label) for label in CONFIDENCE}
    return {'schema': SCHEMA, 'title': title, 'build': build_profile.BUILD_ID,
        'inputs': {'entitiesSha256': build_profile.ENTITY_SHA256, 'typelibSha256': build_profile.TYPELIB_SHA256},
        'generatedBy': 'scripts/scan', 'confidenceRules': CONFIDENCE_RULES, 'scope': scope, 'counts': counts,
        'candidates': candidates, **sections}


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False, allow_nan=False, default=_default) + '\n',
        encoding='utf-8')


def _default(value):
    if isinstance(value, (set, tuple)):
        return list(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float):
        return round(value, 6)
    raise TypeError(f'not serialisable: {type(value)}')


def markdown_table(headers: list[str], rows: list[list]) -> str:
    def cell(value):
        if isinstance(value, float):
            text = f'{value:.6g}'
        else:
            text = str(value)
        return text.replace('|', '\\|')
    lines = ['| ' + ' | '.join(headers) + ' |', '|' + '|'.join(' --- ' for _ in headers) + '|']
    lines += ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows]
    return '\n'.join(lines)


def family_markdown(description: dict, limit: int = 80) -> str:
    """A compact Markdown matrix of a Family.describe() result (varying members only)."""
    labels = description['entities']
    rows = []
    for member in description['members'][:limit]:
        rows.append([member['path'], member['storage'], member['nameLength']] +
            [member['values'][label] for label in labels])
    return markdown_table(['path', 'storage', 'len'] + labels, rows)


def stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
