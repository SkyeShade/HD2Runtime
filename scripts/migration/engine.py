"""Structural re-identification of a previous release's fields and relationships in a new build.

Every field of the source release is re-proven against the target BuildView from structural evidence only:
resource hashes and component ownership, settings chains followed from the owning weapon, entity-delta ownership,
stratagem ids, type-library member signatures and shared-scope owner sets. Display names are never used for
identity. Each field ends in exactly one state:

  EXACT             same identity, location, layout, scope and baseline bytes
  MOVED             identity proven; record index / index row / settings row / delta data offset changed
  BASELINE_CHANGED  identity proven; the reviewed default value changed (old -> new recorded)
  LAYOUT_CHANGED    identity proven; the field's member moved inside its record (new offset proven by signature)
  AMBIGUOUS         more than one candidate satisfies the evidence
  LOST              the owner, record, member or delta entry no longer exists
  BLOCKED           identity found but a guard fails: shared scope changed, member type changed, a relationship
                    the field depends on broke, or identity rests on weaker evidence than the change requires
  UNCHECKED         the inputs cannot prove it either way (e.g. game.dll-resident tables of a different game.dll)

Priority when several apply: LOST > BLOCKED > AMBIGUOUS > UNCHECKED > LAYOUT_CHANGED > BASELINE_CHANGED > MOVED > EXACT.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import struct

STATES = ('EXACT', 'MOVED', 'BASELINE_CHANGED', 'LAYOUT_CHANGED', 'AMBIGUOUS', 'LOST', 'BLOCKED', 'UNCHECKED')
PRIORITY = ('LOST', 'BLOCKED', 'AMBIGUOUS', 'UNCHECKED', 'LAYOUT_CHANGED', 'BASELINE_CHANGED', 'MOVED', 'EXACT')
FORMATS = {'f32': '<f', 'u32': '<I', 'i32': '<i', 'u64': '<Q', 'i64': '<q', 'u8': '<B', 'bool': '<B', 'u16': '<H',
    'i16': '<h', 'f64': '<d', 'i8': '<b'}
# Native links the runtime follows from a weapon to its settings rows (component/settings member -> settings kind).
COMPONENT_EDGES = {'ProjectileWeaponComponentData': ((0, 'projectile'),), 'ArcWeaponComponentData': ((0, 'arc'),),
    'BeamWeaponComponentData': ((0, 'beam'),), 'SprayWeaponComponentData': ((200, 'damage'),),
    'MeleeWeaponComponentData': ((12, 'damage'),), 'ExplosiveComponentData': ((36, 'explosion'), (40, 'explosion')),
    'WeaponRoundsComponentData': ((64, 'projectile'), (68, 'projectile')),
    'StickyComponentData': ((44, 'damage'),)}
SETTINGS_EDGES = {'projectile': ((60, 'damage'), (144, 'explosion'), (156, 'explosion')),
    'explosion': ((4, 'damage'), (84, 'projectile')), 'arc': ((36, 'damage'),), 'beam': ((12, 'damage'),)}
MAX_CHAIN = 3


def decode(raw: bytes | None, storage: str):
    if raw is None:
        return None
    fmt = FORMATS.get(storage)
    if fmt is None or len(raw) < struct.calcsize(fmt):
        return raw.hex()
    value = struct.unpack_from(fmt, raw)[0]
    if storage == 'f32':
        return float(f'{value:.7g}')
    if storage == 'u64':
        return f'0x{value:016X}'
    return value


def masked(layout, raw: bytes) -> bytes:
    """Row bytes with pointer-bearing members (ARRAY/PTR/STR heads) zeroed: live tables hold absolute pointers where
    the decoded file holds relative offsets, so only the pointed-to data layout is comparable, not the pointer."""
    data = bytearray(raw)
    for member in layout.members:
        if member['atom'] == 'ARRAY' or member['storage'] in ('PTR', 'STR'):
            data[member['offset']:member['offset'] + 8] = bytes(8)
    return bytes(data)


def hexid(value) -> str | None:
    return None if value is None else f'0x{value:016X}'


# -- layout mapping --------------------------------------------------------------------------------------------------
class LayoutError(Exception):
    def __init__(self, state, reason, candidates=()):
        super().__init__(reason)
        self.state, self.reason, self.candidates = state, reason, list(candidates)


def _sig(member):
    """Matching signature. Nested structs match by their type hash (their size may change with their contents)."""
    if member['storage'] == 'STRUCT':
        return ('STRUCT', member['atom'], member['count'], member['nameLength'], member['typeHash'])
    return (member['storage'], member['atom'], member['count'], member['nameLength'], member['size'])


def _full(member):
    return (member['storage'], member['atom'], member['count'], member['nameLength'], member['size'],
        member['typeHash'], member['offset'])


def map_offset(source_view, source_layout, target_view, target_layout, offset, width, depth=0):
    """Map a field offset from the source record layout to the target one. Returns (offset, evidence) where
    evidence is 'identical', 'signature' or 'ordinal'; raises LayoutError(LOST/AMBIGUOUS/BLOCKED)."""
    if source_layout is None or target_layout is None:
        raise LayoutError('LOST', 'record type absent from a type library')
    if _identical(source_view, source_layout, target_view, target_layout):
        return offset, 'identical'
    member = source_layout.member_at(offset)
    if member is None:
        raise LayoutError('LOST', f'source offset {offset} is not inside a member of {source_layout.name}')
    same = [m for m in target_layout.members if _sig(m) == _sig(member)]
    evidence = 'signature'
    aligned = _aligned(source_layout, target_layout).get(source_layout.members.index(member))
    if len(same) != 1 and aligned is not None:
        # The member sits in a run of members whose signatures match in order on both sides (sequence alignment),
        # so its position is proven by its neighbours, not just by counting equal signatures.
        same, evidence = [target_layout.members[aligned]], 'aligned'
    if len(same) != 1:
        source_same = [m for m in source_layout.members if _sig(m) == _sig(member)]
        if len(same) > 1 and len(same) == len(source_same):
            same = [same[source_same.index(member)]]
            evidence = 'ordinal'
        elif same:
            raise LayoutError('AMBIGUOUS', f'{len(same)} target members share the signature of source member +'
                f"{member['offset']} ({member['storage']})", [m['offset'] for m in same])
        else:
            renamed = [m for m in target_layout.members if m['nameLength'] == member['nameLength']
                and m['atom'] == member['atom']]
            if len(renamed) == 1:
                raise LayoutError('BLOCKED', f"member +{member['offset']} changed type "
                    f"({member['storage']}/{member['size']} -> {renamed[0]['storage']}/{renamed[0]['size']})",
                    [renamed[0]['offset']])
            raise LayoutError('LOST', f"member +{member['offset']} ({member['storage']}) has no counterpart")
    match = same[0]
    inner = offset - member['offset']
    if member['storage'] == 'STRUCT' and depth < 6:
        nested_source = source_view.layout(member['typeHash'])
        nested_target = target_view.layout(match['typeHash'])
        if member['atom'] == 'INLINE_ARRAY' and member['count']:
            stride = member['size'] // member['count']
            element, inner = divmod(inner, stride)
            base = match['offset'] + element * (match['size'] // match['count'])
        else:
            base = match['offset']
        mapped, nested_evidence = map_offset(source_view, nested_source, target_view, nested_target, inner, width,
            depth + 1)
        return base + mapped, 'ordinal' if 'ordinal' in (evidence, nested_evidence) else (
            'identical' if evidence == nested_evidence == 'identical' else
            'aligned' if 'aligned' in (evidence, nested_evidence) else 'signature')
    if inner + width > max(member['size'], width):
        raise LayoutError('BLOCKED', f'field width {width} exceeds member size {member["size"]}')
    return match['offset'] + inner, evidence


ALIGN_MIN_RUN = 3


def _aligned(source_layout, target_layout):
    """source member index -> target member index for members inside matching runs of >= ALIGN_MIN_RUN members."""
    # Keyed by content (never object identity, which Python may reuse for a different layout).
    key = (tuple(_full(m) for m in source_layout.members), tuple(_full(m) for m in target_layout.members))
    if key not in _ALIGN_CACHE:
        matcher = SequenceMatcher(None, [_sig(m) for m in source_layout.members],
            [_sig(m) for m in target_layout.members], autojunk=False)
        mapping = {}
        for a, b, size in matcher.get_matching_blocks():
            if size >= ALIGN_MIN_RUN:
                mapping.update({a + i: b + i for i in range(size)})
        _ALIGN_CACHE[key] = mapping
    return _ALIGN_CACHE[key]


_ALIGN_CACHE = {}


def _identical(source_view, source_layout, target_view, target_layout):
    """Whether two record layouts (and every nested struct) are identical. Pure per pair of views, and asked once per
    field, so it is memoized on the target view; the entry keeps its objects alive so the id() key stays unique."""
    memo = target_view.__dict__.setdefault('_identical_memo', {})
    key = (id(source_view), id(source_layout), id(target_layout))
    if key not in memo:
        memo[key] = (source_view, source_layout, target_layout, source_layout.size == target_layout.size
            and [_full(m) for m in source_layout.members] == [_full(m) for m in target_layout.members]
            and _nested_identical(source_view, source_layout, target_view, target_layout))
    return memo[key][3]


def _nested_identical(source_view, source_layout, target_view, target_layout, depth=0):
    for a, b in zip(source_layout.members, target_layout.members):
        if a['storage'] == 'STRUCT' and depth < 6:
            nested_a, nested_b = source_view.layout(a['typeHash']), target_view.layout(b['typeHash'])
            if nested_a is None or nested_b is None or nested_a.size != nested_b.size or [_full(m) for m in
                    nested_a.members] != [_full(m) for m in nested_b.members] or not _nested_identical(
                    source_view, nested_a, target_view, nested_b, depth + 1):
                return False
    return True


# -- settings chains -------------------------------------------------------------------------------------------------
def _u32(raw, offset):
    return struct.unpack_from('<I', raw, offset)[0] if raw is not None and offset + 4 <= len(raw) else None


def _single_row(view, kind, record_type):
    table = view.settings_table(kind)
    rows = table.row_for_type(record_type) if table else []
    return rows[0] if len(rows) == 1 else None


def chains(view, anchors):
    """Every (kind, recordType) reachable from the anchors through the runtime's native links, with the paths."""
    reached = {}
    for anchor in anchors:
        for component, edges in COMPONENT_EDGES.items():
            record = view.record(component, anchor)
            if record is None:
                continue
            for offset, kind in edges:
                _walk(view, reached, [(anchor, component, offset)], kind, _u32(record['bytes'], offset))
    return reached


def _walk(view, reached, path, kind, record_type):
    if not record_type or len(path) > MAX_CHAIN:
        return
    row = _single_row(view, kind, record_type)
    if row is None:
        return
    reached.setdefault((kind, record_type), []).append(list(path))
    for offset, next_kind in SETTINGS_EDGES.get(kind, ()):
        _walk(view, reached, path + [(kind, offset)], next_kind, _u32(row[1], offset))


def replay(source_view, target_view, path, final_kind):
    """Follow a source chain in the target build, mapping each link member through the target layouts."""
    anchor, component, offset = path[0]
    record = target_view.record(component, anchor)
    if record is None:
        return None, f'anchor {hexid(anchor)} no longer owns {component}'
    try:
        mapped, _ = map_offset(source_view, source_view.component(component).layout, target_view,
            target_view.component(component).layout, offset, 4)
    except LayoutError as error:
        return None, f'{component} link member: {error.reason}'
    kinds = [step[0] for step in path[1:]] + [final_kind]
    value, kind = _u32(record['bytes'], mapped), kinds[0]
    for (step_kind, step_offset), next_kind in zip(path[1:], kinds[1:]):
        row = _single_row(target_view, step_kind, value)
        if row is None:
            return None, f'{step_kind} type {value} is not a unique row'
        try:
            mapped, _ = map_offset(source_view, source_view.settings_table(step_kind).layout, target_view,
                target_view.settings_table(step_kind).layout, step_offset, 4)
        except LayoutError as error:
            return None, f'{step_kind} link member: {error.reason}'
        value, kind = _u32(row[1], mapped), next_kind
    return value, None


# -- consumer (scope) index ------------------------------------------------------------------------------------------
class Scope:
    """Which resources reach each settings row through native links (the row's write scope)."""

    def __init__(self, view):
        self.consumers, self.reach = {}, {}
        resources = set()
        for component in COMPONENT_EDGES:
            table = view.component(component)
            if table:
                resources.update(table.owners)
        for resource in resources:
            self.reach[resource] = chains(view, [resource])
            for key in self.reach[resource]:
                self.consumers.setdefault(key, set()).add(resource)

    def paths(self, anchors, kind, record_type):
        return [path for anchor in anchors for path in self.reach.get(anchor, {}).get((kind, record_type), [])]

    def of(self, kind, record_type):
        return self.consumers.get((kind, record_type), set())


# -- field classification -------------------------------------------------------------------------------------------
class Result:
    def __init__(self, field):
        self.field = field
        self.flags = []            # (state, reason)
        self.evidence = []
        self.failed = []
        self.candidates = []
        self.distinguish = []
        self.target = None
        self.baseline = None
        self.confidence = None     # structural | type-only | layout-ordinal | none

    def flag(self, state, reason):
        self.flags.append((state, reason))

    @property
    def state(self):
        states = {state for state, _ in self.flags} or {'EXACT'}
        return next(state for state in PRIORITY if state in states)

    def to_json(self):
        field = self.field
        source = {key: (hexid(value) if key in ('resource',) and isinstance(value, int) else value)
            for key, value in field['backing'].items() if key != 'anchors'}
        if 'anchors' in field['backing']:
            source['anchors'] = [hexid(value) for value in field['backing']['anchors']]
        return {'key': field['key'], 'domain': field['domain'], 'object': field['object'], 'field': field['field'],
            'state': self.state, 'previouslyEditable': field['editable'], 'shared': field['shared'],
            'reasons': [{'state': state, 'reason': reason} for state, reason in self.flags],
            'confidence': self.confidence, 'evidence': self.evidence, 'source': source, 'target': self.target,
            'baseline': self.baseline, 'locator': field['locator'],
            'review': None if self.state in ('EXACT', 'MOVED', 'BASELINE_CHANGED', 'LAYOUT_CHANGED') else {
                'previous': {'semanticKey': field['key'], 'nativeIdentity': source, 'baseline': field['baseline']},
                'candidates': self.candidates, 'failedEvidence': self.failed,
                'distinguishingEvidence': self.distinguish}}


class Engine:
    def __init__(self, source_view, target_view, release):
        self.S, self.T, self.release = source_view, target_view, release
        self.same_dll = source_view.build.get('gameDllSha256') == target_view.build.get('gameDllSha256') and \
            bool(source_view.build.get('gameDllSha256'))
        self._scope_s = self._scope_t = None
        self._new_by_component = None

    # scope indexes are expensive; build once, lazily
    @property
    def scope_s(self):
        if self._scope_s is None:
            self._scope_s = Scope(self.S)
        return self._scope_s

    @property
    def scope_t(self):
        if self._scope_t is None:
            self._scope_t = Scope(self.T)
        return self._scope_t

    def classify(self, field) -> Result:
        result = Result(field)
        kind = field['backing']['kind']
        try:
            getattr(self, '_' + kind)(field, result)
        except LayoutError as error:
            result.flag(error.state, error.reason)
            result.candidates += [{'offset': offset, 'why': 'member with a compatible signature'}
                for offset in error.candidates]
            result.distinguish.append('the member name from an unobfuscated type library, or a live write test '
                'on a snapshot of the new build')
        return result

    # component records ---------------------------------------------------------------------------------------------
    def _component(self, field, result):
        b = field['backing']
        name = b['component']
        table_s, table_t = self.S.component(name), self.T.component(name)
        if table_s is None:
            raise ValueError(f"{field['key']}: source build has no {name}")
        owners_s = set(table_s.owners_of(b['recordIndex']))
        resource = b['resource']
        if resource is None or resource not in owners_s:
            result.flag('BLOCKED', 'release backing does not resolve in its own build (source mismatch)')
            result.failed.append('source record ownership')
            return
        source_record = table_s.record(resource)
        if (source_record['recordIndex'], source_record['indexRow'], source_record['ownerCount']) != (
                b['recordIndex'], b['indexRow'], b['ownerCount']):
            result.flag('BLOCKED', 'release backing coordinates differ from its own build (source mismatch)')
            return
        if table_t is None:
            result.flag('LOST', f'{name} no longer exists in the target type library/entity table')
            result.failed.append('component type present')
            return
        if resource not in self.T.entity_rows:
            result.flag('LOST', f'resource {hexid(resource)} no longer exists')
            result.failed.append('owning resource present')
            self._resource_candidates(result, resource, name, source_record['bytes'])
            return
        record = table_t.record(resource)
        if record is None:
            result.flag('LOST', f'resource {hexid(resource)} no longer owns {name}')
            result.failed.append('resource owns component')
            return
        result.evidence.append(f'resource {hexid(resource)} owns {name} record {record["recordIndex"]}')
        result.confidence = 'structural'
        owners_t = set(table_t.owners_of(record['recordIndex']))
        if owners_t - owners_s:
            added, removed = sorted(owners_t - owners_s), sorted(owners_s - owners_t)
            result.flag('BLOCKED', f'shared scope changed: record now owned by {len(owners_t)} resources '
                f'(was {len(owners_s)}; +{len(added)} -{len(removed)})')
            result.failed.append('write scope (owner set) unchanged')
            result.candidates.append({'addedOwners': [hexid(x) for x in added], 'removedOwners':
                [hexid(x) for x in removed], 'why': 'owner set of the record changed'})
            result.distinguish.append('review whether the new owners may share the edit (acknowledge shared scope)')
        elif owners_s - owners_t:
            result.evidence.append(f'write scope narrowed: {len(owners_s - owners_t)} previous co-owner(s) no longer '
                'share the record')
        offset, layout_evidence = map_offset(self.S, table_s.layout, self.T, table_t.layout, b['offset'], b['width'])
        self._layout(result, b['offset'], offset, layout_evidence)
        if (record['recordIndex'], record['indexRow']) != (b['recordIndex'], b['indexRow']):
            result.flag('MOVED', f"record {b['recordIndex']}/{b['indexRow']} -> "
                f"{record['recordIndex']}/{record['indexRow']}")
        old = source_record['bytes'][b['offset']:b['offset'] + b['width']]
        new = record['bytes'][offset:offset + b['width']]
        self._baseline(result, field, old, new)
        result.target = {'kind': 'component', 'component': name, 'resource': hexid(resource),
            'recordIndex': record['recordIndex'], 'indexRow': record['indexRow'], 'ownerCount': record['ownerCount'],
            'offset': offset, 'storage': b['storage'], 'width': b['width']}

    def _resource_candidates(self, result, resource, component, record_bytes):
        """New resources that own the same component set and (ideally) an identical record."""
        owned_s = set(self.S.resource_components().get(resource, ()))
        new = [r for r in self.T.entity_rows if r not in self.S.entity_rows]
        owned_t = self.T.resource_components()
        ranked = []
        for candidate in new:
            names = set(owned_t.get(candidate, ()))
            if component not in names:
                continue
            overlap = len(names & owned_s) / max(len(names | owned_s), 1)
            record = self.T.record(component, candidate)
            same = record is not None and record['bytes'] == record_bytes
            ranked.append((same, overlap, candidate))
        for same, overlap, candidate in sorted(ranked, reverse=True)[:5]:
            result.candidates.append({'resource': hexid(candidate), 'path': self.T.paths.get(candidate),
                'componentSetOverlap': round(overlap, 3), 'identicalRecord': same,
                'why': 'new resource owning ' + component + (' with an identical record' if same else '')})
        result.distinguish.append('resource path names (hashes.txt) for the new build, or a snapshot with the object '
            'spawned so its live owner can be matched')

    # settings rows -------------------------------------------------------------------------------------------------
    def _settings(self, field, result):
        b = field['backing']
        kind = b['settings']
        table_s, table_t = self.S.settings_table(kind), self.T.settings_table(kind)
        if table_s is None:
            result.flag('UNCHECKED', f'the source view has no {kind} settings (snapshot-only table)')
            return
        if table_t is None:
            result.flag('UNCHECKED', f'the target view has no {kind} settings (snapshot-only table)')
            return
        group_s = table_s.groups.get(b['group']) if b.get('group') is not None else table_s
        source_rows = group_s.row_for_type(b['recordType']) if group_s else []
        if len(source_rows) != 1:
            result.flag('BLOCKED', 'release settings type is not a unique row in its own build (source mismatch)')
            return
        source_row, source_bytes = source_rows[0]
        group_t = table_t.group_by_type(group_s.settings_type)
        if group_t is None:
            result.flag('LOST', f'{kind} group type 0x{group_s.settings_type:08X} no longer exists')
            result.failed.append('settings group type present')
            return
        primary = group_s is table_s or group_s.settings_type == table_s.settings_type
        target_type, identity = self._settings_identity(field, result, kind, group_t, primary)
        if result.flags and result.state in ('LOST', 'AMBIGUOUS', 'BLOCKED'):
            return
        rows = group_t.row_for_type(target_type)
        if len(rows) != 1:
            result.flag('LOST' if not rows else 'AMBIGUOUS', f'{kind} type {target_type}: {len(rows)} rows')
            return
        row, row_bytes = rows[0]
        consumers_s = self.scope_s.of(kind, b['recordType']) if primary else set()
        consumers_t = self.scope_t.of(kind, target_type) if primary else set()
        if consumers_s - consumers_t and not consumers_t - consumers_s:
            result.evidence.append(f'write scope narrowed: {len(consumers_s - consumers_t)} previous consumer(s) no '
                'longer reach the row')
        elif consumers_s != consumers_t:
            result.flag('BLOCKED', f'shared scope widened: {len(consumers_s)} -> {len(consumers_t)} native consumers '
                f'({len(consumers_t - consumers_s)} new)')
            result.failed.append('write scope (consumer set) unchanged')
            result.candidates.append({'addedConsumers': [hexid(x) for x in sorted(consumers_t - consumers_s)],
                'removedConsumers': [hexid(x) for x in sorted(consumers_s - consumers_t)],
                'why': 'the set of weapons reaching this row changed'})
        offset, layout_evidence = map_offset(self.S, group_s.layout, self.T, group_t.layout, b['offset'], b['width'])
        self._layout(result, b['offset'], offset, layout_evidence)
        if identity == 'type-only':
            # Record types can be renumbered between builds; without a chain only an unchanged row is accepted.
            content_s = masked(group_s.layout, source_bytes)[4:]
            if masked(group_t.layout, row_bytes)[4:] == content_s:
                result.confidence = 'type-only+content'
                result.evidence.append('row content identical (live pointers masked)')
            elif group_s.layout.size == group_t.layout.size:
                same_content = [r for r, _, data in group_t.rows if masked(group_t.layout, data)[4:] == content_s]
                result.flag('BLOCKED', f'{kind} type {target_type} changed and no weapon chain proves it is the '
                    'same row (types can renumber)')
                result.failed.append('row content unchanged (type-only identity)')
                result.candidates += [{'row': r, 'recordType': group_t.rows[r][1],
                    'why': 'row with identical content under a different type'} for r in same_content[:5]]
                result.distinguish.append('the consuming stratagem/entity chain in a snapshot of the new build')
        if (b.get('group'), b.get('row')) != (group_t.group, row) or target_type != b['recordType']:
            result.flag('MOVED', f"{kind} group/row/type {b.get('group')}/{b.get('row')}/{b['recordType']} -> "
                f'{group_t.group}/{row}/{target_type}')
        old = source_bytes[b['offset']:b['offset'] + b['width']]
        new = row_bytes[offset:offset + b['width']]
        self._baseline(result, field, old, new)
        if b.get('enum') == 'status':
            self._status_table(result)
        result.target = {'kind': 'settings', 'settings': kind, 'recordType': target_type, 'group': group_t.group,
            'row': row, 'offset': offset, 'storage': b['storage'], 'width': b['width']}

    def _settings_identity(self, field, result, kind, group_t, primary):
        b = field['backing']
        anchors = b.get('anchors') or []
        paths = self.scope_s.paths(anchors, kind, b['recordType']) if anchors and primary else []
        if not paths and primary:
            # No chain from the field's own object (e.g. stratagem settings): prove the row through every native
            # consumer that reaches it in the source build instead.
            consumers = sorted(self.scope_s.of(kind, b['recordType']))
            paths = self.scope_s.paths(consumers, kind, b['recordType'])
            if paths:
                result.evidence.append(f'{len(consumers)} native consumer(s) reach this row in the source build')
        if not paths:
            result.confidence = 'type-only'
            result.evidence.append(f'{kind} record type {b["recordType"]} (no weapon chain; type-only identity)')
            if not group_t.row_for_type(b['recordType']):
                result.flag('LOST', f'{kind} type {b["recordType"]} no longer exists')
                result.failed.append('record type present')
                result.distinguish.append('the consuming stratagem/entity chain in a snapshot of the new build')
            return b['recordType'], 'type-only'
        reached, failures = {}, []
        for path in paths:
            value, error = replay(self.S, self.T, path, kind)
            if error:
                failures.append(error)
            else:
                reached.setdefault(value, []).append(path)
        described = ' -> '.join(f'{step[1]}+{step[2]}' if len(step) == 3 else f'{step[0]}+{step[1]}'
            for step in paths[0])
        if len(reached) == 1:
            target_type = next(iter(reached))
            result.confidence = 'structural'
            result.evidence.append(f'chain {described} -> {kind} type {target_type} '
                f'({len(paths)} source path(s), all agree)')
            vanished = [f for f in failures if 'no longer owns' in f]
            if len(vanished) != len(failures):
                result.flag('AMBIGUOUS', 'some source chains now fail: ' + '; '.join(sorted(set(failures) - set(vanished))))
                result.failed += sorted(set(failures) - set(vanished))
            elif vanished:
                result.evidence.append(f'{len(vanished)} source chain(s) end at consumers that no longer exist')
            return target_type, 'chain'
        if not reached:
            lost = [f for f in failures if 'no longer owns' in f]
            result.flag('LOST' if lost and len(lost) == len(failures) else 'AMBIGUOUS',
                'weapon chain no longer resolves: ' + '; '.join(sorted(set(failures))))
            result.failed += sorted(set(failures))
            result.distinguish.append('a snapshot of the new build with the weapon equipped')
            return None, 'chain'
        result.flag('AMBIGUOUS', f'source chains now reach {len(reached)} different {kind} rows')
        result.candidates += [{'recordType': value, 'paths': len(p), 'why': 'reached through the weapon chain'}
            for value, p in sorted(reached.items())]
        result.failed.append('all chains agree')
        result.distinguish.append('the phase (impact/expiry) or attack role that each chain serves in the new build')
        return None, 'chain'

    # entity deltas (magazine attachments) --------------------------------------------------------------------------
    def _delta(self, field, result):
        b = field['backing']
        if self.S.deltas is None or self.T.deltas is None:
            result.flag('UNCHECKED', 'entity deltas are not available in one of the views')
            return
        source = self.S.deltas.get(b['resource'])
        entry_s = next((e for e in (source or {}).get('entries', ()) if e['component'] == b['componentIndex']
            and e['offset'] == b['componentOffset']), None)
        if entry_s is None or entry_s['dataOffset'] != b['dataOffset']:
            result.flag('BLOCKED', 'release delta entry does not resolve in its own build (source mismatch)')
            return
        target = self.T.deltas.get(b['resource'])
        if target is None:
            result.flag('LOST', f"entity delta {hexid(b['resource'])} no longer exists")
            result.failed.append('delta resource present')
            same = [hexid(r) for r, d in self.T.deltas.items() if r not in self.S.deltas and
                [(e['component'], e['offset'], e['bytes']) for e in d['entries']] ==
                [(e['component'], e['offset'], e['bytes']) for e in source['entries']]]
            result.candidates += [{'resource': r, 'why': 'new delta with identical entries'} for r in same[:5]]
            result.distinguish.append('the attachment unlock list / customization catalog of the new build')
            return
        name = self.S.delta_component_index.get(b['componentIndex'])
        reverse = {value: key for key, value in self.T.delta_component_index.items()}
        if name not in reverse or name not in self.T.components:
            result.flag('LOST', f'{name} is no longer a delta-able component')
            return
        offset, layout_evidence = map_offset(self.S, self.S.component(name).layout, self.T,
            self.T.component(name).layout, b['componentOffset'], b['width'])
        self._layout(result, b['componentOffset'], offset, layout_evidence)
        index = reverse[name]
        entry_t = next((e for e in target['entries'] if e['component'] == index and e['offset'] == offset), None)
        if entry_t is None:
            result.flag('LOST', f'delta no longer overrides {name}+{offset}')
            result.failed.append('delta entry present')
            return
        result.confidence = 'structural'
        result.evidence.append(f"delta {hexid(b['resource'])} overrides {name}+{offset}")
        if entry_t['dataOffset'] != b['dataOffset'] or index != b['componentIndex']:
            result.flag('MOVED', f"delta data {b['dataOffset']} -> {entry_t['dataOffset']}, component index "
                f"{b['componentIndex']} -> {index}")
        self._baseline(result, field, entry_s['bytes'][:b['width']], entry_t['bytes'][:b['width']])
        result.target = {'kind': 'delta', 'resource': hexid(b['resource']), 'componentIndex': index,
            'componentOffset': offset, 'dataOffset': entry_t['dataOffset'], 'storage': b['storage']}

    # stratagem rows (located through game.dll) ---------------------------------------------------------------------
    def _stratagem(self, field, result):
        b = field['backing']
        if self.S.stratagems is None or self.T.stratagems is None:
            result.flag('UNCHECKED', 'stratagem rows are only readable from a snapshot of a runtime-profiled game.dll')
            result.distinguish.append('a snapshot of the new build after its runtime profile (schemas/current.lua) '
                'is imported')
            return
        if not self.same_dll:
            result.flag('UNCHECKED', 'StratagemDefinition layout is code-defined; a different game.dll cannot be '
                'proven structurally')
            return
        source, target = self.S.stratagems.get(b['id']), self.T.stratagems.get(b['id'])
        if source is None:
            result.flag('BLOCKED', 'release stratagem id is absent from its own build (source mismatch)')
            return
        if target is None:
            result.flag('LOST', f"stratagem id {b['id']} no longer exists")
            return
        result.confidence = 'structural'
        result.evidence.append(f"stratagem id {b['id']} (identical game.dll)")
        if (target['group'], target['row']) != (b['group'], b['row']):
            result.flag('MOVED', f"stratagem row {b['group']}/{b['row']} -> {target['group']}/{target['row']}")
        if b['storage'] == 'calldown':
            # The calldown code is a pointer to a per-process array plus a count: compare the codes themselves.
            old_code, new_code = source.get('calldown'), target.get('calldown')
            result.baseline = {'old': old_code, 'new': new_code, 'release': field['baseline']}
            if old_code is None or new_code is None:
                result.flag('UNCHECKED', 'the calldown array is not readable in a view')
            elif old_code != new_code:
                result.flag('BASELINE_CHANGED', f'default {old_code} -> {new_code}')
        else:
            old = bytes.fromhex(source['bytes'])[b['offset']:b['offset'] + b['width']]
            new = bytes.fromhex(target['bytes'])[b['offset']:b['offset'] + b['width']]
            self._baseline(result, field, old, new)
        result.target = dict(b, group=target['group'], row=target['row'])

    # game.dll-resident tables --------------------------------------------------------------------------------------
    def _code(self, field, result):
        if self.same_dll:
            result.confidence = 'structural'
            result.evidence.append('identical game.dll (code-resident table bytes unchanged)')
            result.target = dict(field['backing'])
            self.baseline_value(result, field, field['baseline'])
            return
        result.flag('UNCHECKED', 'game.dll-resident booster table: a new game.dll must be re-proven by '
            'scripts/research_booster_native.py')
        result.distinguish.append('re-run the booster native research on the new game.dll')

    def _status_table(self, result):
        """A status_reference slot holds a status *identity* (domains/status_catalog.lua maps semantic IDs to this
        build's StatusEffectType values). It carries forward only when both builds' status tables are available and
        identical row for row (pointers masked); otherwise the catalog could name the wrong status."""
        if not hasattr(self, '_status_verdict'):
            table_s, table_t = self.S.settings_table('status'), self.T.settings_table('status')
            if table_s is None or table_t is None:
                self._status_verdict = ('UNCHECKED', 'status reference: a view has no status table (snapshot-only), '
                    'so status identities cannot be proven')
            else:
                rows_s = {kind: masked(table_s.layout, raw) for _, kind, raw in table_s.rows}
                rows_t = {kind: masked(table_t.layout, raw) for _, kind, raw in table_t.rows}
                self._status_verdict = None if rows_s == rows_t else ('BLOCKED', 'status table changed between '
                    'builds; re-run scripts/research_status_effects.py and regenerate the status catalog')
        if self._status_verdict:
            result.flag(*self._status_verdict)
            result.failed.append('status table identical')

    # shared checks -------------------------------------------------------------------------------------------------
    def _layout(self, result, old, new, evidence):
        if evidence == 'ordinal':
            result.confidence = 'layout-ordinal'
            result.evidence.append('member matched by ordinal among identical signatures')
        if new != old:
            result.flag('LAYOUT_CHANGED', f'member offset {old} -> {new} ({evidence} match)')
        elif evidence != 'identical':
            result.evidence.append(f'record layout changed; member offset unchanged ({evidence} match)')

    def _baseline(self, result, field, old: bytes, new: bytes):
        storage = field['backing']['storage']
        old_value, new_value = decode(old, storage), decode(new, storage)
        result.baseline = {'old': old_value, 'new': new_value, 'release': field['baseline']}
        if old != new:
            result.flag('BASELINE_CHANGED', f'default {old_value} -> {new_value}')

    def baseline_value(self, result, field, value):
        result.baseline = {'old': value, 'new': value, 'release': value}

    # relationships -------------------------------------------------------------------------------------------------
    def relationship(self, link):
        method = getattr(self, '_rel_' + link['kind'], None)
        if method is None:
            return 'UNCHECKED', 'no structural check for this relationship', None
        source = method(self.S, link)
        target = method(self.T, link)
        if source[0] == 'UNCHECKED' or target[0] == 'UNCHECKED':
            return 'UNCHECKED', target[1] if target[0] == 'UNCHECKED' else source[1], None
        if source[0] != 'INTACT':
            return 'BROKEN', 'relationship does not hold in the source build: ' + source[1], None
        return target[0], target[1], target[2] if len(target) > 2 else None

    @staticmethod
    def _slots(view, component, resource):
        table = view.component(component)
        record = table.record(resource) if table else None
        if record is None:
            return None
        first = table.layout.members[0]
        stride = first['size'] // max(first['count'], 1)
        return [struct.unpack_from('<Q', record['bytes'], i * stride)[0] for i in range(max(first['count'], 1))]

    def _rel_vehicle_mount(self, view, link):
        slots = self._slots(view, 'MountComponentData', link['vehicle'])
        if slots is None:
            return 'BROKEN', 'vehicle no longer owns a MountComponent', None
        if link['slot'] < len(slots) and slots[link['slot']] == link['weapon']:
            return 'INTACT', f"mount slot {link['slot']} -> {hexid(link['weapon'])}", None
        holders = [i for i, value in enumerate(slots) if value == link['weapon']]
        if holders:
            return 'BROKEN', f"weapon moved to mount slot(s) {holders}", {'slots': holders}
        return 'BROKEN', f"mount slot {link['slot']} no longer holds the weapon", None

    def _rel_rack_delivers(self, view, link):
        items = self._slots(view, 'HellpodRackComponentData', link['rack'])
        if items is None:
            return 'BROKEN', 'rack no longer owns a HellpodRackComponent', None
        if link['item'] in items:
            return 'INTACT', f"rack slot {items.index(link['item'])} delivers {hexid(link['item'])}", None
        return 'BROKEN', f"rack no longer delivers {hexid(link['item'])}", None

    def _rel_backpack_feed(self, view, link):
        record = view.record('WeaponLinkedAmmoComponentData', link['weapon'])
        if record is None:
            return 'BROKEN', 'weapon no longer owns WeaponLinkedAmmo', None
        if struct.unpack_from('<Q', record['bytes'], 0)[0] != link['tag']:
            return 'BROKEN', 'linked-ammo tag changed', None
        table = view.component('TagComponentData')
        carriers = set()
        for resource, (index, _) in (table.owners.items() if table else ()):
            if link['tag'] in struct.unpack_from('<64Q', table.records[index], 0):
                carriers.add(resource)
        if carriers != {link['backpack']}:
            return ('AMBIGUOUS' if len(carriers) > 1 else 'BROKEN'), \
                f'tag carried by {len(carriers)} entities', {'carriers': [hexid(x) for x in sorted(carriers)]}
        return 'INTACT', 'weapon linked-ammo tag carried only by the backpack', None

    def _rel_stratagem_rack(self, view, link):
        if view.stratagems is None:
            return 'UNCHECKED', 'stratagem rows need a snapshot of a runtime-profiled game.dll', None
        row = view.stratagems.get(link['stratagemId'])
        if row is None:
            return 'BROKEN', 'stratagem id no longer exists', None
        payloads = [int(value, 16) if isinstance(value, str) else value for value in row.get('payloads') or []]
        return ('INTACT', 'stratagem payload includes the rack', None) if link['rack'] in payloads else (
            'BROKEN', 'stratagem no longer delivers the rack', None)

    def _rel_stratagem_payload(self, view, link):
        if view.stratagems is None:
            return 'UNCHECKED', 'stratagem rows need a snapshot of a runtime-profiled game.dll', None
        row = view.stratagems.get(link['stratagemId'])
        if row is None:
            return 'BROKEN', 'stratagem id no longer exists', None
        payloads = [int(value, 16) if isinstance(value, str) else value for value in row.get('payloads') or []]
        return ('INTACT', 'primary payload unchanged', None) if payloads[:1] == [link['payload']] else (
            'BROKEN', 'primary payload changed', {'payloads': [hexid(x) for x in payloads]})

    def _rel_booster_granted(self, view, link):
        if view.stratagems is None:
            return 'UNCHECKED', 'stratagem rows need a snapshot of a runtime-profiled game.dll', None
        return ('INTACT', 'granted stratagem id exists', None) if link['stratagemId'] in view.stratagems else (
            'BROKEN', 'granted stratagem id no longer exists', None)

    def _rel_component_owner(self, view, link):
        return ('INTACT', f"{hexid(link['resource'])} owns {link['component']}", None) if view.record(
            link['component'], link['resource']) else ('BROKEN', f"{link['component']} owner missing", None)

    def _rel_component_value(self, view, link):
        """A component member that names a settings row (a mine deployer's explosion type) must be unchanged."""
        record = view.record(link['component'], link['resource'])
        if record is None:
            return 'BROKEN', f"{link['component']} owner missing", None
        source_table, target_table = self.S.component(link['component']), view.component(link['component'])
        if source_table is not None and target_table is not None:
            before = source_table.layout.member_at(link['offset'])
            after = target_table.layout.member_at(link['offset'])
            signature = lambda m: m and (m['offset'], m['size'], m['storage'], m['nameLength'])
            if signature(before) != signature(after):
                return 'BROKEN', f"{link['component']}+{link['offset']} layout changed", None
        value = struct.unpack_from('<I', record['bytes'], link['offset'])[0]
        return ('INTACT', f"{link['component']}+{link['offset']} still names {link['expect']}", None)             if value == link['expect'] else ('BROKEN', f"{link['component']}+{link['offset']} now names {value}",
                {'value': value})

    def _rel_entity_present(self, view, link):
        return ('INTACT', 'entity present', None) if link['resource'] in view.entity_rows else (
            'BROKEN', f"{hexid(link['resource'])} no longer exists", None)

    def _rel_attachment_compatibility(self, view, link):
        if view.deltas is None:
            return 'UNCHECKED', 'entity deltas unavailable', None
        if link['attachment'] not in view.deltas:
            return 'BROKEN', 'attachment delta no longer exists', None
        missing = [hexid(value) for value in link['weapons'] if value not in view.entity_rows]
        if missing:
            return 'BROKEN', 'weapon resource(s) missing: ' + ', '.join(missing), None
        if link['relationship'] != 'native_resource_default':
            return 'UNCHECKED', f"{link['relationship']} compatibility comes from the customization catalog, which "\
                'the migration does not read; attachment and weapons are both present', None
        return 'INTACT', 'attachment delta and weapon resources present', None

    def _rel_no_call_in(self, view, link):
        return 'UNCHECKED', 'no-call-in state is a reviewed absence; re-run stratagem research to confirm', None

    def _rel_stratagem_icon(self, view, link):
        return 'UNCHECKED', 'icons are archive textures; re-run scripts/research_stratagem_icons.py', None

    # new content ---------------------------------------------------------------------------------------------------
    def new_candidates(self):
        categories = (('weapon', lambda names: 'WeaponDataComponentData' in names and names & set(COMPONENT_EDGES)),
            ('vehicle', lambda names: 'MountComponentData' in names),
            ('backpack', lambda names: 'BackpackComponentData' in names),
            ('pod_rack', lambda names: 'HellpodRackComponentData' in names),
            ('pickup', lambda names: 'InteractableComponentData' in names),
            ('projectile_or_explosive', lambda names: 'ExplosiveComponentData' in names),
            ('deployable_or_entity', lambda names: 'HealthComponentData' in names))
        owned = self.T.resource_components()
        entities = []
        for resource in sorted(set(self.T.entity_rows) - set(self.S.entity_rows)):
            names = set(owned.get(resource, ()))
            category = next((label for label, test in categories if test(names)), None)
            if category:
                entities.append({'resource': hexid(resource), 'category': category, 'components': sorted(names),
                    'path': self.T.paths.get(resource), 'status': 'CANDIDATE (unreviewed; not named, not writable)'})
        settings = []
        for kind, table in sorted(self.T.settings.items()):
            source = self.S.settings_table(kind)
            if source is None:
                continue
            for record_type in sorted(set(table.by_type) - set(source.by_type)):
                settings.append({'settings': kind, 'recordType': record_type,
                    'row': table.by_type[record_type][0], 'consumers':
                    [hexid(x) for x in sorted(self.scope_t.of(kind, record_type))][:8]})
        stratagems = []
        if self.S.stratagems is not None and self.T.stratagems is not None:
            stratagems = [{'id': value, 'group': self.T.stratagems[value]['group'], 'row':
                self.T.stratagems[value]['row']} for value in sorted(set(self.T.stratagems) - set(self.S.stratagems))]
        deltas = []
        if self.S.deltas is not None and self.T.deltas is not None:
            deltas = [{'resource': hexid(value), 'components': sorted({self.T.delta_component_index.get(
                e['component'], e['component']) for e in self.T.deltas[value]['entries']}, key=str)}
                for value in sorted(set(self.T.deltas) - set(self.S.deltas))]
        components = sorted(set(self.T.components) - set(self.S.components))
        return {'entities': entities, 'settings': settings, 'stratagems': stratagems, 'entityDeltas': deltas,
            'componentTypes': components}


def run(source_view, target_view, release, progress=None) -> dict:
    engine = Engine(source_view, target_view, release)
    results = {}
    for index, field in enumerate(release['fields']):
        results[field['key']] = engine.classify(field)
        if progress and index % 1000 == 0:
            progress(index, len(release['fields']))
    relationships = []
    blocked, unchecked = {}, {}
    for link in release['relationships']:
        state, reason, detail = engine.relationship(link)
        entry = {'key': link['kind'] + ':' + link['key'], 'kind': link['kind'], 'object': link['object'],
            'state': state, 'reason': reason, 'detail': detail, 'blocks': link['blocks'],
            'source': {k: (hexid(v) if isinstance(v, int) and k not in ('slot', 'stratagemId') else v)
                for k, v in link.items() if k not in ('kind', 'key', 'object', 'blocks')}}
        relationships.append(entry)
        if state in ('BROKEN', 'AMBIGUOUS'):
            for domain, obj in link['blocks']:
                blocked.setdefault((domain, obj), []).append(entry)
        elif state == 'UNCHECKED':
            for domain, obj in link['blocks']:
                unchecked.setdefault((domain, obj), []).append(entry)
    for result in results.values():
        field = result.field
        for entry in blocked.get((field['domain'], field['object']), ()):
            result.flag('BLOCKED', f"relationship {entry['key']} is {entry['state']}: {entry['reason']}")
            result.failed.append('relationship ' + entry['key'])
        for entry in unchecked.get((field['domain'], field['object']), ()):
            result.evidence.append(f"relationship {entry['key']} unchecked by these inputs: {entry['reason']}")
    return {'fields': [results[field['key']].to_json() for field in release['fields']],
        'relationships': relationships, 'new': engine.new_candidates(), 'sameGameDll': engine.same_dll}
