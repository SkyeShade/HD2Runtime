"""Apply a reviewed build migration safely.

  py scripts/apply_migration.py validation/migrations/<target-build> [--dry-run] [--output schemas/build_migration.json]

Reads the migration's plan.json and writes the build-migration overlay the domain generators consume
(scripts/migration/overlay.py). Rules (scripts/migration/report.py `decide`):

  EXACT             carried forward (no patch)
  MOVED             rebound to the proven new record/row/delta coordinates
  BASELINE_CHANGED  rebound and the reviewed default updated, only with structural identity
  LAYOUT_CHANGED    rebound to the proven new member offset (signature/aligned evidence only)
  AMBIGUOUS, LOST, BLOCKED, UNCHECKED, or anything below the threshold
                    previously writable fields are downgraded to read-only with the migration reason
  NEW candidates    never written; they need a reviewed mapping first

Before writing, the overlay is simulated on the current generated tables and every field that would remain
writable must sit on proven target coordinates. Any unsafe stale write aborts the apply.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from migration import overlay, source  # noqa: E402

# Field-dict keys holding native coordinates, per domain and backing kind.
COMPONENT_KEYS = ('recordIndex', 'indexRow', 'ownerCount', 'offset')


def _readonly(decision, target_build):
    return f"Build migration to {target_build}: {decision['state']} — {decision['reason']}"[:600]


def _scalar(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def field_patch(key, decision, tables, target_build):
    """(module, patch) for one non-EXACT field, or None when nothing changes."""
    module, locator = decision['domain'], decision['locator']
    node = overlay.resolve(tables.get(module, {}), locator['path'])
    if node is overlay.MISSING:
        raise ValueError(f'{key}: locator no longer resolves in the current generated tables')
    guard = {dotted: value for dotted, value in locator['guard'].items()}
    rack_level = locator.get('rackLevel')
    readonly = decision['action'] == 'readonly'
    target = decision['target'] or {}
    if rack_level:
        # Drop-pod racks: slot/count offsets are runtime constants, so only rack coordinates can be rebound.
        if not readonly and (target.get('offset') != node_offset(locator) or decision['state'] == 'BASELINE_CHANGED'):
            readonly = True
            decision = dict(decision, reason='rack slot layout or payload changed; review the rack manually')
        if readonly:
            if not node.get('writable'):
                return None
            return {'key': key, 'path': locator['path'], 'guard': guard,
                'set': {'writable': False, 'reason': _readonly(decision, target_build)}}
        values = {k: target[k] for k in ('recordIndex', 'indexRow', 'ownerCount') if node.get(k) != target[k]}
        if not values:
            return None
        guard.update({k: node[k] for k in values})
        return {'key': key, 'path': locator['path'], 'guard': guard, 'set': values}
    if readonly:
        if node.get('editable') is False or (module != 'attachment_authoring' and not node.get('editable')):
            return None
        return {'key': key, 'path': locator['path'], 'guard': guard,
            'set': {'editable': False, 'reason': _readonly(decision, target_build)}}
    values = {}
    backing = node.get('backing') or {}
    kind = target.get('kind')
    if kind == 'component':
        for name in COMPONENT_KEYS:
            if backing.get(name) != target[name]:
                values['backing.' + name] = target[name]
    elif kind == 'settings':
        identity = 'recordType' if 'recordType' in backing else 'nativeIdentity'
        for name, value in ((identity, target['recordType']), ('group', target['group']), ('row', target['row']),
                ('offset', target['offset'])):
            if name in backing and backing[name] != value:
                values['backing.' + name] = value
    elif kind == 'delta':
        for name, value in (('component', target['componentIndex']), ('componentOffset', target['componentOffset']),
                ('dataOffset', target['dataOffset'])):
            if node.get(name) != value:
                values[name] = value
    elif kind == 'stratagem':
        root = overlay.resolve(tables[module], locator['path'][:2] + ['root'])
        if (root.get('group'), root.get('row')) != (target['group'], target['row']):
            return {'key': key, 'path': locator['path'][:2] + ['root'], 'guard': {'id': root['id'],
                'group': root['group'], 'row': root['row']}, 'set': {'group': target['group'], 'row': target['row']}}
    baseline = decision.get('baseline') or {}
    changed = baseline.get('old') != baseline.get('new')
    # Semantic defaults (a weapon-function name, a penetration label, trait and rate lists, a function projectile) are
    # derived from native values together with companion data (nativeTags, nativeSlots, penetrationSlot) by the field's
    # own research: a changed native default is never carried as a raw value.
    semantic = node.get('type') in SEMANTIC_DEFAULT_TYPES
    if changed and not semantic and _scalar(node.get('currentDefault')) and _scalar(baseline.get('new')):
        values['currentDefault'] = baseline['new']
    elif changed and node.get('editable'):
        values.update(editable=False, reason=_readonly(dict(decision, reason='the new default is not a scalar the '
            'overlay can carry; review manually'), target_build))
    if not values:
        return None
    for dotted in values:
        current = overlay._get(node, dotted)
        if current is not overlay.MISSING:
            guard[dotted] = current
    return {'key': key, 'path': locator['path'], 'guard': guard, 'set': values}


SEMANTIC_DEFAULT_TYPES = {'weapon_function', 'armor_penetration_label', 'trait_set', 'fire_rate_set',
    'function_projectile_reference'}


def node_offset(locator):
    if locator.get('spawnCount'):
        return 556
    return (int(locator['slot']) - 1) * 64


def verify(plan, tables_after, target_build):
    """Count fields that remain writable without proven target coordinates (must be 0)."""
    unsafe = []
    for key, decision in plan['decisions'].items():
        node = overlay.resolve(tables_after.get(decision['domain'], {}), decision['locator']['path'])
        if node is overlay.MISSING:
            unsafe.append((key, 'missing'))
            continue
        writable = node.get('writable') if decision['locator'].get('rackLevel') else (
            node.get('editable', True) if decision['domain'] == 'attachment_authoring' else node.get('editable'))
        if not writable:
            continue
        if decision['action'] == 'readonly':
            unsafe.append((key, 'writable despite a read-only decision'))
            continue
        target = decision['target'] or {}
        backing = node.get('backing') or {}
        if target.get('kind') == 'component' and not decision['locator'].get('rackLevel'):
            if any(backing.get(name) != target[name] for name in COMPONENT_KEYS):
                unsafe.append((key, 'component coordinates not rebound'))
        elif target.get('kind') == 'settings':
            identity = backing.get('recordType', backing.get('nativeIdentity'))
            if (identity, backing.get('offset')) != (target['recordType'], target['offset']):
                unsafe.append((key, 'settings coordinates not rebound'))
        elif target.get('kind') == 'delta':
            if (node.get('componentOffset'), node.get('dataOffset')) != (target['componentOffset'], target['dataOffset']):
                unsafe.append((key, 'delta coordinates not rebound'))
    return unsafe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('migration', help='validation/migrations/<target-build> directory')
    parser.add_argument('--dry-run', action='store_true', help='report what would change; write nothing to schemas/')
    parser.add_argument('--output', default=str(overlay.OVERLAY), help='overlay path')
    parser.add_argument('--tables-from', default='current',
        help='generated tables to patch-check against (default: working tree)')
    args = parser.parse_args(argv)
    directory = Path(args.migration)
    plan = json.loads((directory / 'plan.json').read_text(encoding='utf-8'))
    summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
    if summary['confidence']['unsafeStaleWritesCarriedForward']:
        raise SystemExit('the migration itself reports unsafe stale writes; refusing to apply')
    target = plan['target']
    tables = source.load_tables(source.resolve_ref(args.tables_from))
    patches, counts = {}, {'carry': len(plan['exact']), 'rebind': 0, 'readonly': 0, 'unchanged': 0}
    for key, decision in sorted(plan['decisions'].items()):
        item = field_patch(key, decision, tables, target['buildId'])
        if item is None:
            counts['unchanged'] += 1
            continue
        counts['readonly' if item['set'].get('editable') is False or item['set'].get('writable') is False
            else 'rebind'] += 1
        patches.setdefault(decision['domain'], []).append(item)
    for module in patches:
        # Rack-level patches for several slots of one rack collapse to one; keep the first per path+set.
        seen, unique = set(), []
        for item in patches[module]:
            signature = json.dumps([item['path'], item['set']], sort_keys=True)
            if signature not in seen:
                seen.add(signature)
                unique.append(item)
        patches[module] = unique
    after = copy.deepcopy(tables)
    for module, items in patches.items():
        overlay.patch(module, after[module], items)
    unsafe = verify(plan, after, target['buildId'])
    report = {'migration': directory.as_posix(), 'target': {k: target[k] for k in ('buildId', 'exeSha256',
        'gameDllSha256')}, 'source': {k: plan['source'][k] for k in ('version', 'commit', 'buildId')},
        'counts': counts, 'patches': {module: len(items) for module, items in sorted(patches.items())},
        'unsafeStaleWrites': len(unsafe), 'unsafe': unsafe[:50], 'dryRun': args.dry_run}
    (directory / 'apply-report.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'unsafe'}, indent=1))
    if unsafe:
        raise SystemExit(f'{len(unsafe)} unsafe stale writes would survive; nothing written')
    if args.dry_run:
        return report
    document = {'schemaVersion': 1, 'target': report['target'], 'source': report['source'],
        'migration': report['migration'], 'patches': dict(sorted(patches.items()))}
    Path(args.output).write_text(json.dumps(document, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('wrote', args.output, '(applied by the generators only while schemas/current.lua is build',
        target['buildId'] + ')')
    return report


if __name__ == '__main__':
    main()
