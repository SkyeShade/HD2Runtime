"""Migration decisions, reports and historical fingerprints.

`decide(field)` is the single auto-apply rule set, shared by the report (what *would* happen) and
scripts/apply_migration.py (what does happen):

  EXACT             carry forward unchanged
  MOVED             rebind to the new coordinates, only with structural identity (or a type-only settings row whose
                    content is byte-identical)
  BASELINE_CHANGED  rebind + new reviewed default, only with structural identity (the confidence threshold)
  LAYOUT_CHANGED    rebind to the new member offset, only when the member is proven by a unique signature or an
                    aligned run of neighbouring members (never by ordinal counting alone)
  AMBIGUOUS, LOST, BLOCKED, UNCHECKED
                    read-only (a previously writable field is downgraded; nothing stale is ever carried forward)
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from . import engine
from .source import DOMAIN_LABEL

ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = 1
AUTO = ('EXACT', 'MOVED', 'BASELINE_CHANGED', 'LAYOUT_CHANGED')
FILES = {'EXACT': 'exact.json', 'MOVED': 'moved.json', 'BASELINE_CHANGED': 'baseline-changed.json',
    'LAYOUT_CHANGED': 'layout-changed.json', 'AMBIGUOUS': 'ambiguous.json', 'LOST': 'lost.json',
    'BLOCKED': 'blocked.json', 'UNCHECKED': 'unchecked.json'}
HISTORY = ROOT / 'research/build-history'


def decide(field: dict) -> dict:
    """{'action': carry|rebind|readonly, 'reason': str}"""
    state, confidence = field['state'], field['confidence']
    if state == 'EXACT':
        return {'action': 'carry', 'reason': 'identical identity, location, layout, scope and baseline'}
    if state not in AUTO:
        return {'action': 'readonly', 'reason': f'{state}: ' + '; '.join(r['reason'] for r in field['reasons']
            if r['state'] == state)[:400]}
    if field['target'] is None:
        return {'action': 'readonly', 'reason': 'no proven target coordinates'}
    if confidence == 'structural':
        return {'action': 'rebind', 'reason': f'{state} with structural identity'}
    if confidence == 'type-only+content' and state == 'MOVED':
        return {'action': 'rebind', 'reason': 'MOVED settings row with byte-identical content'}
    return {'action': 'readonly', 'reason': f'{state} rests on {confidence} evidence, below the auto-apply '
        'threshold; review manually'}


def _compact(field):
    item = {'key': field['key'], 'object': field['object'], 'field': field['field'], 'domain': field['domain'],
        'editable': field['previouslyEditable']}
    if field['state'] != 'EXACT':
        item.update(reasons=[r['reason'] for r in field['reasons']], confidence=field['confidence'],
            evidence=field['evidence'], source=field['source'], target=field['target'])
    if field['baseline'] and field['baseline']['old'] != field['baseline']['new']:
        item['baseline'] = field['baseline']
    if field['review']:
        item['review'] = field['review']
    item['decision'] = decide(field)
    return item


def summarize(result: dict, meta: dict) -> dict:
    fields = result['fields']
    totals = Counter(field['state'] for field in fields)
    domains = {}
    for field in fields:
        entry = domains.setdefault(field['domain'], {'label': DOMAIN_LABEL[field['domain']], 'fields': 0,
            'previouslyWritable': 0, 'recovered': 0, 'states': Counter()})
        entry['fields'] += 1
        entry['states'][field['state']] += 1
        if field['previouslyEditable']:
            entry['previouslyWritable'] += 1
            entry['recovered'] += decide(field)['action'] != 'readonly'
    writable = [field for field in fields if field['previouslyEditable']]
    decisions = Counter(decide(field)['action'] for field in writable)
    downgraded = [field for field in writable if decide(field)['action'] == 'readonly']
    manual = [field for field in downgraded if field['state'] != 'LOST' or (field['review'] or {}).get('candidates')]
    unsafe = unsafe_stale_writes(fields)
    total = max(len(writable), 1)
    return {'schemaVersion': REPORT_VERSION, 'engine': {'extractorVersion': meta['extractorVersion'],
            'reportVersion': REPORT_VERSION},
        'source': meta['source'], 'target': meta['target'], 'cache': meta['cache'],
        'sameGameDll': result['sameGameDll'],
        'totals': {state: totals.get(state, 0) for state in engine.STATES}, 'fields': len(fields),
        'byDomain': {name: dict(entry, states=dict(sorted(entry['states'].items())))
            for name, entry in sorted(domains.items())},
        'relationships': dict(sorted(Counter(r['state'] for r in result['relationships']).items())),
        'newCandidates': {kind: len(items) for kind, items in result['new'].items()},
        'writable': {'previouslyWritable': len(writable), 'carried': decisions.get('carry', 0),
            'rebound': decisions.get('rebind', 0), 'downgradedToReadOnly': len(downgraded),
            'manualReview': len(manual)},
        'confidence': {'recoveredAutomaticallyPercent': round(100 * (len(writable) - len(downgraded)) / total, 2),
            'downgradedPercent': round(100 * len(downgraded) / total, 2),
            'manualReviewPercent': round(100 * len(manual) / total, 2),
            'unsafeStaleWritesCarriedForward': unsafe}}


def unsafe_stale_writes(fields) -> int:
    """Fields a decision would leave writable without proven, current coordinates. Must be 0."""
    unsafe = 0
    for field in fields:
        action = decide(field)['action']
        if action == 'readonly':
            continue
        if field['state'] not in AUTO or field['target'] is None:
            unsafe += 1
        elif action == 'carry' and field['state'] != 'EXACT':
            unsafe += 1
    return unsafe


def write(directory: Path, result: dict, meta: dict) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    summary = summarize(result, meta)
    by_state = {state: [] for state in engine.STATES}
    for field in result['fields']:
        by_state[field['state']].append(field)
    _dump(directory / 'summary.json', summary)
    for state, name in FILES.items():
        items = by_state[state]
        if state == 'EXACT':
            payload = {'count': len(items), 'keys': [field['key'] for field in items]}
        else:
            payload = {'count': len(items), 'fields': [_compact(field) for field in items]}
        _dump(directory / name, payload)
    diff = [dict(_compact(field), state=field['state']) for field in result['fields']
        if field['previouslyEditable'] and decide(field)['action'] != 'carry']
    _dump(directory / 'writable-diff.json', {'previouslyWritable': summary['writable']['previouslyWritable'],
        'changed': len(diff), 'fields': diff})
    _dump(directory / 'relationships.json', {'counts': summary['relationships'],
        'relationships': result['relationships']})
    _dump(directory / 'new-candidates.json', dict(result['new'], note='Unreviewed structural candidates. They are '
        'not named and never writable until a reviewed mapping adds them.'))
    # Everything scripts/apply_migration.py needs. EXACT fields carry forward unchanged and are listed by key only.
    _dump(directory / 'plan.json', {'target': meta['target'], 'source': meta['source'],
        'exact': [field['key'] for field in by_state['EXACT']], 'decisions': {
        field['key']: dict(decide(field), state=field['state'], domain=field['domain'], object=field['object'],
            locator=field['locator'],
            target=field['target'], baseline=field['baseline'], editable=field['previouslyEditable'])
        for field in result['fields'] if field['state'] != 'EXACT'}})
    (directory / 'human-report.md').write_text(human(summary, result), encoding='utf-8', newline='\n')
    return summary


def _dump(path: Path, value):
    """summary.json is indented; list/map members of the larger documents are written one record per line."""
    if path.name == 'summary.json':
        body = json.dumps(value, indent=1)
    else:
        parts = []
        for key, item in value.items():
            if isinstance(item, list) and item and isinstance(item[0], dict):
                inner = ',\n'.join('  ' + json.dumps(entry, separators=(',', ':')) for entry in item)
                parts.append(f' {json.dumps(key)}: [\n{inner}\n ]')
            elif isinstance(item, dict) and len(item) > 20:
                inner = ',\n'.join(f'  {json.dumps(k)}: {json.dumps(v, separators=(",", ":"))}'
                    for k, v in item.items())
                parts.append(f' {json.dumps(key)}: {{\n{inner}\n }}')
            else:
                parts.append(f' {json.dumps(key)}: {json.dumps(item, separators=(",", ":"))}')
        body = '{\n' + ',\n'.join(parts) + '\n}'
    path.write_text(body + '\n', encoding='utf-8', newline='\n')


def human(summary: dict, result: dict) -> str:
    source, target = summary['source'], summary['target']
    lines = ['# HD2Runtime build migration report', '',
        f"Source: HD2Runtime {source['version']} ({source['ref']} @ {source['commit'][:12]}), build "
        f"{source['buildId']}", f"Target: build {target['buildId']}"
        + (f" — snapshot {target['snapshot']} captured {target.get('capturedAt')}" if target.get('snapshot') else ''),
        '', '| | Source | Target |', '|---|---|---|',
        f"| Executable SHA-256 | `{source['exeSha256']}` | `{target['exeSha256']}` |",
        f"| game.dll SHA-256 | `{source['gameDllSha256']}` | `{target['gameDllSha256']}` |",
        f"| Build profile | {source['buildId']} | {target.get('buildProfile') or 'not in schemas/build_profile.json'} |",
        '', f"Target inputs: {', '.join(item['kind'] + ' `' + item['path'] + '`' for item in target['sources'])}. "
        f"Snapshot extraction cache: {_cache(summary['cache'])}.", '',
        '## Confidence summary', '',
        f"- Previously writable fields: {summary['writable']['previouslyWritable']}",
        f"- Recovered automatically: {summary['confidence']['recoveredAutomaticallyPercent']}% "
        f"({summary['writable']['carried']} carried, {summary['writable']['rebound']} rebound)",
        f"- Downgraded to read-only: {summary['confidence']['downgradedPercent']}% "
        f"({summary['writable']['downgradedToReadOnly']})",
        f"- Needing manual review: {summary['confidence']['manualReviewPercent']}% ({summary['writable']['manualReview']})",
        f"- Unsafe stale writes carried forward: {summary['confidence']['unsafeStaleWritesCarriedForward']}", '',
        '## Totals', '', '| State | Fields |', '|---|---|']
    lines += [f'| {state} | {count} |' for state, count in summary['totals'].items()]
    lines += ['', '## Recovered per category', '',
        '| Category | Fields | Previously writable | Recovered | States |', '|---|---|---|---|---|']
    for name, entry in summary['byDomain'].items():
        states = ', '.join(f'{state} {count}' for state, count in entry['states'].items())
        lines.append(f"| {entry['label']} | {entry['fields']} | {entry['previouslyWritable']} | {entry['recovered']} "
            f'| {states} |')
    fields = result['fields']
    downgraded = [f for f in fields if f['previouslyEditable'] and decide(f)['action'] == 'readonly']
    lines += ['', '## PREVIOUSLY SUPPORTED BUT NO LONGER SAFELY WRITABLE', '']
    if not downgraded:
        lines.append('None. Every previously writable field was re-proven.')
    else:
        lines.append(f'{len(downgraded)} fields; grouped by object (first reason shown). Full evidence: '
            'writable-diff.json.')
        lines.append('')
        grouped = {}
        for field in downgraded:
            grouped.setdefault((field['domain'], field['object']), []).append(field)
        for (domain, obj), items in sorted(grouped.items())[:400]:
            states = Counter(f['state'] for f in items)
            reason = decide(items[0])['reason']
            lines.append(f"- **{obj}** ({DOMAIN_LABEL[domain]}): {len(items)} field(s) "
                f"[{', '.join(f'{s} {n}' for s, n in sorted(states.items()))}] — {reason[:220]}")
        if len(grouped) > 400:
            lines.append(f'- … {len(grouped) - 400} more objects in writable-diff.json')
    changed = [f for f in fields if f['state'] == 'BASELINE_CHANGED']
    lines += ['', '## Changed baselines', '']
    lines += [f"- {f['key']}: {f['baseline']['old']} → {f['baseline']['new']}" for f in changed[:200]] or ['None.']
    if len(changed) > 200:
        lines.append(f'- … {len(changed) - 200} more in baseline-changed.json')
    for state, title in (('AMBIGUOUS', 'Ambiguous'), ('LOST', 'Lost'), ('BLOCKED', 'Blocked'),
            ('UNCHECKED', 'Unchecked (inputs cannot prove either way)')):
        items = [f for f in fields if f['state'] == state]
        lines += ['', f'## {title} ({len(items)})', '']
        reasons = Counter(next(r['reason'] for r in f['reasons'] if r['state'] == state) for f in items)
        lines += [f'- {count} × {reason}' for reason, count in reasons.most_common(25)] or ['None.']
        if len(reasons) > 25:
            lines.append(f'- … {len(reasons) - 25} more distinct reasons in {FILES[state]}')
    rel = result['relationships']
    lines += ['', '## Relationships', '', ', '.join(f'{state} {count}' for state, count in
        summary['relationships'].items()), '']
    lines += [f"- {r['state']} {r['key']}: {r['reason']}" for r in rel if r['state'] in ('BROKEN', 'AMBIGUOUS')][:100]
    unchecked = Counter(r['kind'] for r in rel if r['state'] == 'UNCHECKED')
    if unchecked:
        lines.append('- UNCHECKED: ' + ', '.join(f'{kind} {count}' for kind, count in sorted(unchecked.items())))
    new = result['new']
    lines += ['', '## New candidates (unreviewed, not writable)', '',
        f"- Entities: {len(new['entities'])} ({', '.join(f'{k} {v}' for k, v in sorted(Counter(e['category'] for e in new['entities']).items()))})",
        f"- Settings rows: {len(new['settings'])}", f"- Stratagem ids: {len(new['stratagems'])}",
        f"- Entity deltas (attachments): {len(new['entityDeltas'])}",
        f"- Component types: {', '.join(new['componentTypes']) or 'none'}", '',
        'Next steps: docs/game-update-migration.md.', '']
    return '\n'.join(lines)


def _cache(cache):
    if not cache:
        return 'not used (datalibrary input)'
    return ('reused' if cache['used'] else 'freshly extracted') + f" ({cache['directory']}, key {cache['key']})"


# -- historical fingerprints -----------------------------------------------------------------------------------------
def fingerprint(field: dict, side: str) -> str | None:
    """Compact native identity of one semantic field in one build (never read by the runtime)."""
    backing = field['source'] if side == 'source' else field['target']
    if not backing:
        return None
    base = field['baseline']
    value = None if not base else base['old' if side == 'source' else 'new']
    kind = backing['kind']
    if kind == 'component':
        return (f"component|{backing['component']}|{backing.get('resource')}|{backing['recordIndex']}/"
            f"{backing['indexRow']}/{backing['ownerCount']}|+{backing['offset']}|{value}")
    if kind == 'settings':
        return (f"settings|{backing['settings']}|{backing['recordType']}|{backing.get('group')}/{backing.get('row')}"
            f"|+{backing['offset']}|{value}")
    if kind == 'delta':
        return (f"delta|{backing['resource']}|{backing['componentIndex']}+{backing['componentOffset']}|"
            f"{backing['dataOffset']}|{value}")
    if kind == 'stratagem':
        return f"stratagem|{backing['id']}|{backing.get('group')}/{backing.get('row')}|+{backing['offset']}|{value}"
    if kind == 'code':
        return f"code|{backing['code']}|{backing.get('row')}|+{backing.get('offset')}|{value}"
    return None


def record_history(result: dict, meta: dict) -> list[Path]:
    """research/build-history/<buildId>.json: per-semantic-field fingerprints for each build seen by a migration.
    The source build is written from the source side of the comparison, the target from the proven target side
    (unproven fields are recorded as null)."""
    HISTORY.mkdir(parents=True, exist_ok=True)
    written = []
    for side, info in (('source', meta['source']), ('target', meta['target'])):
        path = HISTORY / (info['buildId'] + '.json')
        fields = {field['key']: fingerprint(field, side) for field in result['fields']}
        if side == 'target':
            fields = {field['key']: (fields[field['key']] if field['state'] in AUTO else None)
                for field in result['fields']}
        existing = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        merged = dict(existing.get('fields') or {})
        merged.update({key: value for key, value in fields.items() if value is not None or key not in merged})
        document = {'schemaVersion': 1, 'buildId': info['buildId'], 'exeSha256': info['exeSha256'],
            'gameDllSha256': info['gameDllSha256'], 'format': 'kind|native identity|coordinates|+offset|baseline',
            'recordedBy': sorted(set((existing.get('recordedBy') or []) + [meta['label']])),
            'fields': dict(sorted(merged.items()))}
        body = '{\n' + ',\n'.join(f' {json.dumps(k)}: {json.dumps(v)}' for k, v in document.items()
            if k != 'fields') + ',\n "fields": {\n' + ',\n'.join(f'  {json.dumps(k)}: {json.dumps(v)}'
            for k, v in document['fields'].items()) + '\n }\n}\n'
        path.write_text(body, encoding='utf-8', newline='\n')
        written.append(path)
    return written
