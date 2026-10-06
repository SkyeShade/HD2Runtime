"""Side-by-side comparison of many related entities (research only).

A ``Family`` is a set of labelled entities and one component table. It builds the value matrix of every scalar element
of the flattened record layout and classifies each element:

* kind: float / int / enum / hash64 / bits / vector component, and value hints (angle-like, fraction, sentinel,
  thin-hash name, resource name) that are LEADS for review, never names;
* variation: constant, sentinel-only, or the partition of entities by value (canonical group labels);
* archetype-specific: elements whose value departs from the family mode for a strict minority of entities;
* clusters: elements with the same variation partition (they change together: a correlated gameplay role) and,
  for numeric elements, near-linear correlation across entities;
* ownership: per entity, its record index and owner count (shared type data vs a unique record).

Variant comparison (``variant_groups`` + ``variant_diff``) compares records across difficulty/variant/type families
that differ only by a name suffix (``_mk2``, ``_elite``, ``_01``, ...).
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import re

from scan.tables import EntityTables, Member, decode, hexid

FLT_MAX = 3.4028234663852886e38
SENTINELS = {0, -1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF, FLT_MAX, -FLT_MAX}


def _canonical(value):
    if isinstance(value, float):
        if math.isnan(value):
            return 'nan'
        return round(value, 6)
    return value


def partition(values: list) -> tuple[int, ...]:
    """Canonical group labels: equal values share a label; labels are numbered in first-seen order."""
    labels, out = {}, []
    for value in values:
        key = _canonical(value)
        if key not in labels:
            labels[key] = len(labels)
        out.append(labels[key])
    return tuple(out)


def hints(kind: str, values: list, tables: EntityTables | None = None) -> list[str]:
    """Value-shape leads for review (never a name)."""
    distinct = {_canonical(v) for v in values if v is not None}
    found = []
    numeric = [v for v in values if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))]
    if not numeric:
        return found
    if distinct <= SENTINELS:
        found.append('sentinel_only')
    if kind in ('float', 'vector'):
        lo, hi = min(numeric), max(numeric)
        if all(v == int(v) for v in numeric) and hi - lo >= 10 and -360 <= lo and hi <= 360:
            found.append('whole_degrees_range')
        if 0 <= lo and hi <= 1 and len(distinct) > 1:
            found.append('unit_interval')
        if -1.0 in distinct and len(distinct) > 1:
            found.append('minus_one_sentinel_present')
        if hi > 1e6:
            found.append('large_magnitude')
    if kind in ('int', 'enum'):
        if max(numeric) <= 1 and min(numeric) >= 0:
            found.append('boolean_like')
        elif all(0 <= v < 1024 for v in numeric):
            found.append('small_integer')
        elif tables is not None and any(tables.thin.get(v) for v in numeric if isinstance(v, int)):
            found.append('thin_hash_names')
        elif all(v == 0 or v > 0x00FFFFFF for v in numeric):
            found.append('hash_like')
    if kind == 'hash64' and tables is not None and any(tables.name(v) for v in numeric if isinstance(v, int)):
        found.append('resource_names')
    return found


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


class Family:
    """A labelled entity set compared on one component table."""

    def __init__(self, tables: EntityTables, component: str, entities):
        self.tables = tables
        self.component = tables.component(component)
        if isinstance(entities, dict):
            items = list(entities.items())
        else:
            items = [(tables.label(resource), resource) for resource in entities]
        self.entities = []      # (label, resource, record)
        self.missing = []
        for label, resource in items:
            record = self.component.record_of(resource)
            if record is None:
                self.missing.append(label)
            else:
                self.entities.append((label, resource, record))
        self.labels = [label for label, _, _ in self.entities]
        self._matrix = None

    # -- matrix ----------------------------------------------------------------------------------------------
    def matrix(self) -> dict[str, dict]:
        """path -> {member, kind, values (one per entity, family order)} for every scalar element."""
        if self._matrix is None:
            raws = [self.component.raw(record) for _, _, record in self.entities]
            out = {}
            for member in self.component.members():
                per_entity = [decode(member, raw) for raw in raws]
                if per_entity and isinstance(per_entity[0], list):
                    width = len(per_entity[0])
                    for index in range(width):
                        kind = 'vector' if member.atom == 'VECTOR' else member.kind
                        out[f'{member.path}[{index}]'] = {'member': member, 'kind': kind, 'element': index,
                            'values': [values[index] for values in per_entity]}
                else:
                    out[member.path] = {'member': member, 'kind': member.kind, 'element': None, 'values': per_entity}
            self._matrix = out
        return self._matrix

    def ownership(self) -> list[dict]:
        owners = self.component.owner_map()
        return [{'entity': label, 'resource': hexid(resource), 'record': record,
            'owners': len(owners.get(record, [])), 'shared': len(owners.get(record, [])) > 1,
            'coOwners': [self.tables.label(other) for other in owners.get(record, []) if other != resource][:8]}
            for label, resource, record in self.entities]

    # -- classification --------------------------------------------------------------------------------------
    def classify(self) -> list[dict]:
        rows = []
        for path, item in self.matrix().items():
            values, member = item['values'], item['member']
            groups = partition(values)
            counts = Counter(groups)
            distinct = len(counts)
            mode_label, mode_count = counts.most_common(1)[0] if counts else (0, 0)
            specific = []
            if 1 < distinct and mode_count > len(values) / 2:
                specific = [self.labels[i] for i, label in enumerate(groups) if label != mode_label]
            row = {'path': path, 'offset': member.offset + (item['element'] or 0) * (
                    member.element_size() if member.atom != 'VECTOR' else 4),
                'storage': member.storage, 'atom': member.atom, 'nameLength': member.name_length,
                'parent': member.parent, 'parentType': member.parent_type, 'kind': item['kind'],
                'distinct': distinct, 'constant': distinct == 1, 'partition': list(groups),
                'values': dict(zip(self.labels, (_canonical(v) for v in values))),
                'hints': hints(item['kind'], values, self.tables)}
            if specific:
                row['archetypeSpecific'] = {'modeValue': _canonical(values[groups.index(mode_label)]),
                    'entities': specific}
            rows.append(row)
        return rows

    def varying(self) -> list[dict]:
        return [row for row in self.classify() if not row['constant']]

    def clusters(self, threshold: float = 0.98) -> list[dict]:
        """Elements that vary together: identical partitions (exact co-variation), then numeric correlation."""
        rows = self.varying()
        by_partition = defaultdict(list)
        for row in rows:
            by_partition[tuple(row['partition'])].append(row['path'])
        result = [{'kind': 'same_partition', 'paths': paths, 'groups': len(set(key))}
            for key, paths in by_partition.items() if len(paths) > 1]
        numeric = [row for row in rows if row['kind'] in ('float', 'int', 'vector') and row['distinct'] >= 3]
        seen = set()
        for i, a in enumerate(numeric):
            xs = [a['values'][label] for label in self.labels]
            if any(not isinstance(x, (int, float)) for x in xs):
                continue
            linked = []
            for b in numeric[i + 1:]:
                ys = [b['values'][label] for label in self.labels]
                if any(not isinstance(y, (int, float)) for y in ys) or tuple(a['partition']) == tuple(b['partition']):
                    continue
                r = _pearson(xs, ys)
                if r is not None and abs(r) >= threshold:
                    linked.append({'path': b['path'], 'r': round(r, 4)})
            if linked and a['path'] not in seen:
                seen.add(a['path'])
                result.append({'kind': 'correlated', 'anchor': a['path'], 'linked': linked})
        return result

    def table(self, paths=None) -> list[list]:
        """Rows [path, value per entity...] for display."""
        matrix = self.matrix()
        selected = paths or [row['path'] for row in self.varying()]
        return [[path] + [_canonical(v) for v in matrix[path]['values']] for path in selected]

    def describe(self, include_constant: bool = False) -> dict:
        classified = self.classify()
        return {'component': self.component.name, 'recordType': self.component.record_type,
            'recordSize': self.component.record_size, 'layoutFingerprint': self.tables.fingerprint(self.component.name),
            'entities': self.labels, 'missing': self.missing, 'ownership': self.ownership(),
            'elements': len(classified), 'varyingElements': sum(1 for row in classified if not row['constant']),
            'members': [row for row in classified if include_constant or not row['constant']],
            'clusters': self.clusters()}


def presence(tables: EntityTables, entities) -> dict:
    """Which component tables each entity has, and which tables only some of the set have (archetype markers)."""
    items = list(entities.items()) if isinstance(entities, dict) else [(tables.label(r), r) for r in entities]
    rows = {label: sorted(tables.entity(resource)) for label, resource in items}
    every = set.intersection(*(set(v) for v in rows.values())) if rows else set()
    some = Counter(name for names in rows.values() for name in names)
    return {'entities': rows, 'common': sorted(every),
        'partial': {name: sorted(label for label, names in rows.items() if name in names)
            for name, count in sorted(some.items()) if name not in every}}


SUFFIX = re.compile(r'(_mk\d+|_mk_?[ivx]+|_elite|_heavy|_light|_small|_large|_big|_alpha|_beta|_\d{1,2}|_[abc]|_variant\w*'
    r'|_upgraded|_upgrade\d*|_lvl\d+|_level\d+|_diff\w*|_v\d+)$', re.I)


def variant_stem(label: str) -> str:
    stem = label
    while True:
        new = SUFFIX.sub('', stem)
        if new == stem:
            return stem
        stem = new


def variant_groups(labels) -> dict[str, list[str]]:
    groups = defaultdict(list)
    for label in labels:
        groups[variant_stem(label)].append(label)
    return {stem: sorted(items) for stem, items in groups.items() if len(items) > 1}


def variant_diff(family: Family) -> list[dict]:
    """Within each variant group of the family, the elements whose values differ between the variants."""
    groups = variant_groups(family.labels)
    matrix = family.matrix()
    result = []
    for stem, labels in sorted(groups.items()):
        index = [family.labels.index(label) for label in labels]
        differing = []
        for path, item in matrix.items():
            values = [_canonical(item['values'][i]) for i in index]
            if len(set(map(repr, values))) > 1:
                differing.append({'path': path, 'values': dict(zip(labels, values))})
        result.append({'stem': stem, 'variants': labels, 'differing': differing})
    return result


def shared_type_report(tables: EntityTables, component: str) -> dict:
    """Records with more than one owner: writes to them change every owner (shared type data)."""
    table = tables.component(component)
    shared = []
    for record, owners in sorted(table.owner_map().items()):
        if len(owners) > 1:
            shared.append({'record': record, 'owners': [tables.label(o) for o in owners]})
    return {'component': component, 'records': table.count, 'sharedRecords': shared}


def find_value(tables: EntityTables, value, kinds=('float',), tolerance=1e-4, components=None) -> list[dict]:
    """Every (component, entity, path) whose element equals ``value``: the reverse lookup for a published number."""
    hits = []
    for table in tables.components() if components is None else (tables.component(c) for c in components):
        members = [m for m in table.members() if m.kind in kinds or (m.atom == 'VECTOR' and 'vector' in kinds)]
        if not members:
            continue
        owners = table.owner_map()
        for record in range(table.count):
            raw = table.raw(record)
            for member in members:
                got = decode(member, raw)
                for index, item in enumerate(got if isinstance(got, list) else [got]):
                    if isinstance(item, (int, float)) and abs(item - value) <= tolerance:
                        hits.append({'component': table.name, 'record': record,
                            'path': member.path + (f'[{index}]' if isinstance(got, list) else ''),
                            'nameLength': member.name_length,
                            'owners': [tables.label(o) for o in owners.get(record, [])][:6]})
    return hits
