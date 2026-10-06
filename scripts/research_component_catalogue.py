"""Inventory of every component table in the pinned entity file (read-only research; scripts/scan).

For each of the ~270 component tables: record type, size, record count, index capacity, shared records (more than
one owner), and every flattened member with its storage, hidden-name length and value statistics across all records.
Inline struct-array elements are collapsed to one pattern path (``160[*].8``) so the inventory stays small.
Filediver Go leads are attached where offset, size and hidden-name length agree (STRONG) or offset and size agree
(PLAUSIBLE). Nothing here names or promotes a field: it is the base map future discovery starts from.

  py scripts/research_component_catalogue.py            # write research/component-catalogue-F5FEE03DCFDB.json
  py scripts/research_component_catalogue.py --check    # fail if the committed catalogue is stale

Output: research/component-catalogue-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from scan import golib, report, tables  # noqa: E402
from scan.tables import decode  # noqa: E402

OUTPUT = ROOT / 'research/component-catalogue-F5FEE03DCFDB.json'
ELEMENT = re.compile(r'\[\d+\]')
FLT_MAX = 3.4028234663852886e38


def _stat(values: list):
    numeric = [v for v in values if isinstance(v, (int, float)) and not (isinstance(v, float) and
        (math.isnan(v) or math.isinf(v)))]
    distinct = len({round(v, 6) if isinstance(v, float) else v for v in numeric})
    out = {'distinct': distinct, 'zeros': sum(1 for v in numeric if v == 0)}
    if numeric:
        lo, hi = min(numeric), max(numeric)
        out['min'] = round(lo, 6) if isinstance(lo, float) else lo
        out['max'] = round(hi, 6) if isinstance(hi, float) else hi
    sentinels = sum(1 for v in numeric if v in (-1, FLT_MAX, -FLT_MAX, 0xFFFFFFFF))
    if sentinels:
        out['sentinels'] = sentinels
    return out


def component_entry(t: tables.EntityTables, go: golib.GoLibrary, component: tables.Component) -> dict:
    members = component.members()
    raws = [component.raw(i) for i in range(component.count)]
    leads = golib.leads_for(t, go, component.record_type) if component.record_type else {}
    grouped = defaultdict(lambda: {'values': [], 'member': None, 'elements': 0})
    for member in members:
        key = ELEMENT.sub('[*]', member.path)
        group = grouped[key]
        if group['member'] is None:
            group['member'] = member
        group['elements'] += 1
        for raw in raws:
            value = decode(member, raw)
            if isinstance(value, list):
                group['values'].extend(value)
            elif not isinstance(value, str):
                group['values'].append(value)
    rows = []
    for path, group in grouped.items():
        member = group['member']
        row = {'path': path, 'offset': member.offset, 'size': member.size, 'storage': member.storage,
            'atom': member.atom, 'count': member.count, 'nameLength': member.name_length, 'kind': member.kind,
            'parentType': member.parent_type}
        if group['elements'] > 1:
            row['elements'] = group['elements']
        row.update(_stat(group['values']))
        lead = leads.get(member.offset)
        if lead and path == member.path:
            row['lead'] = {'label': lead['label'], 'strength': lead['strength'], 'source': 'filediver'}
        rows.append(row)
    description = component.describe()
    description['members'] = rows
    description['varyingMembers'] = sum(1 for row in rows if row.get('distinct', 0) > 1)
    description['layoutFingerprint'] = t.fingerprint(component.name)
    return description


def build() -> dict:
    t = tables.pinned()
    go = golib.default_library()
    entries, skipped = [], []
    for name in sorted(t.component_names()):
        try:
            component = t.component(name)
        except (ValueError, KeyError) as error:
            skipped.append({'component': name, 'reason': str(error)})
            continue
        entries.append(component_entry(t, go, component))
    return report.document('Component catalogue', {'components': len(entries), 'skipped': skipped,
        'note': 'Inventory only: no member here is named or promoted. Leads are Filediver community names whose '
            'offset/size (PLAUSIBLE) and hidden-name length (STRONG) fit; they are not proof.'}, [],
        components=entries)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    data = build()
    text = json.dumps(data, indent=1, allow_nan=False) + '\n'
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding='utf-8') != text:
            print('component catalogue is stale:', OUTPUT)
            return 1
        print('component catalogue is current')
        return 0
    OUTPUT.write_text(text, encoding='utf-8')
    print('wrote', OUTPUT, len(text) // 1024, 'KiB', len(data['components']), 'components')
    return 0


if __name__ == '__main__':
    sys.exit(main())
