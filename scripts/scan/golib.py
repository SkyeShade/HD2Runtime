"""Filediver Go struct leads aligned with the pinned type library (research only).

The Filediver reference ships hand-written Go structs for some component types (``datalibrary/*.go``). Their field
names and comments are community leads from older type libraries, not proof. This module:

* parses the raw (binary.Read) structs, never the ``Simple*`` JSON mirrors: binary.Read packs fields with no
  padding, so a field's offset is the sum of the preceding sizes (explicit ``_ [N]uint8`` fields carry padding);
* aligns a Go struct with the type library layout of the same type name: per member, whether a Go field starts at
  the same offset with the same size, and whether the field's snake_case name has exactly the hidden name length.

A name that fits offset, size AND hidden-name length is a STRONG naming lead; anything else stays a lead or nothing.
"""
from __future__ import annotations

from pathlib import Path
import re

from scan.tables import EntityTables

BASIC = {'float32': 4, 'float64': 8, 'uint8': 1, 'int8': 1, 'byte': 1, 'bool': 1, 'uint16': 2, 'int16': 2,
    'uint32': 4, 'int32': 4, 'uint64': 8, 'int64': 8, 'stingray.Hash': 8, 'stingray.ThinHash': 4,
    'mgl32.Vec2': 8, 'mgl32.Vec3': 12, 'mgl32.Vec4': 16, 'mgl32.Quat': 16, 'DLArray': 16}
STRUCT_RE = re.compile(r'^type\s+(\w+)\s+struct\s*\{(.*?)^\}', re.M | re.S)
ENUM_RE = re.compile(r'^type\s+(\w+)\s+(u?int(?:8|16|32|64))\s*$', re.M)
FIELD_RE = re.compile(r'^\s*(\w+)\s+((?:\[\d+\])*)([\w.*]+)\s*(`[^`]*`)?\s*(?://\s*(.*))?$')
JSON_RE = re.compile(r'json:"([^",]+)')


def snake(name: str) -> str:
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    return name.lower()


class GoLibrary:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.enums = {}
        for path in sorted((self.folder / 'enum').glob('*.go')) if (self.folder / 'enum').is_dir() else []:
            for name, base in ENUM_RE.findall(path.read_text(encoding='utf-8', errors='ignore')):
                self.enums['enum.' + name] = BASIC[base]
        self.structs = {}
        for path in sorted(self.folder.glob('*.go')):
            text = path.read_text(encoding='utf-8', errors='ignore')
            for name, body in STRUCT_RE.findall(text):
                if name.startswith('Simple'):
                    continue
                fields = []
                for line in body.splitlines():
                    match = FIELD_RE.match(line)
                    if not match:
                        continue
                    field, dims, kind, tag, comment = match.groups()
                    counts = [int(x) for x in re.findall(r'\[(\d+)\]', dims)]
                    json = JSON_RE.search(tag or '')
                    fields.append({'name': field, 'json': json.group(1) if json else None, 'type': kind,
                        'counts': counts, 'comment': (comment or '').strip(), 'file': path.name})
                self.structs[name] = fields

    def size_of(self, kind: str, seen=()) -> int | None:
        if kind in BASIC:
            return BASIC[kind]
        if kind in self.enums:
            return self.enums[kind]
        if kind.startswith('enum.'):
            return 4
        if kind in self.structs and kind not in seen:
            total = 0
            for field in self.structs[kind]:
                size = self.size_of(field['type'], seen + (kind,))
                if size is None:
                    return None
                for count in field['counts']:
                    size *= count
                total += size
            return total
        return None

    def layout(self, name: str) -> list[dict] | None:
        """Go fields with offsets and sizes, or None if a field type is unknown."""
        if name not in self.structs:
            return None
        out, offset = [], 0
        for field in self.structs[name]:
            size = self.size_of(field['type'])
            if size is None:
                return None
            for count in field['counts']:
                size *= count
            if field['name'] != '_':
                label = field['json'] or snake(field['name'])
                out.append(dict(field, offset=offset, size=size, label=label))
            offset += size
        return out


def align(tables: EntityTables, go: GoLibrary, type_name: str) -> dict:
    """Compare a Go struct with the type library's direct members of the same type."""
    try:
        members = tables.struct_members(type_name)
        native_size = tables.type_size(type_name)
    except ValueError:
        return {'type': type_name, 'status': 'absent_in_type_library'}
    fields = go.layout(type_name)
    if fields is None:
        return {'type': type_name, 'status': 'no_go_struct' if type_name not in go.structs else 'unsized_go_struct'}
    by_offset = {}
    for field in fields:
        by_offset.setdefault(field['offset'], []).append(field)
    rows = []
    for member in members:
        candidates = by_offset.get(member['offset'], [])
        best = None
        for field in candidates:
            fit = {'goField': field['name'], 'label': field['label'], 'goType': field['type'],
                'sizeMatch': field['size'] == member['size'],
                'nameLengthFit': member['nameLength'] is not None and len(field['label']) == member['nameLength'],
                'comment': field['comment'] or None}
            if best is None or (fit['sizeMatch'], fit['nameLengthFit']) > (best['sizeMatch'], best['nameLengthFit']):
                best = fit
        rows.append({'offset': member['offset'], 'size': member['size'], 'storage': member['storage'],
            'nameLength': member['nameLength'], 'type': member['type'], 'lead': best,
            'strength': 'STRONG' if best and best['sizeMatch'] and best['nameLengthFit'] else
                'PLAUSIBLE' if best and best['sizeMatch'] else 'NONE'})
    go_size = sum(field['size'] for field in fields) if fields else 0
    return {'type': type_name, 'status': 'aligned', 'nativeSize': native_size,
        'goSize': go.size_of(type_name), 'sizeMatch': go.size_of(type_name) == native_size, 'members': rows,
        'strongLeads': sum(1 for row in rows if row['strength'] == 'STRONG')}


def align_tree(tables: EntityTables, go: GoLibrary, type_name: str, depth: int = 0) -> dict:
    """``align`` for a type and, recursively, every nested struct type that both sides know."""
    result = align(tables, go, type_name)
    if depth < 4 and result.get('status') == 'aligned':
        nested = {}
        for row in result['members']:
            child = row['type']
            if child and child in go.structs and child not in nested and child != type_name:
                nested[child] = align_tree(tables, go, child, depth + 1)
        if nested:
            result['nested'] = nested
    return result


def leads_for(tables: EntityTables, go: GoLibrary, record_type: str) -> dict[int, dict]:
    """Absolute record offset -> STRONG/PLAUSIBLE lead, for the flattened members of a record type."""
    out = {}

    def walk(type_name, base):
        aligned = align(tables, go, type_name)
        if aligned.get('status') != 'aligned':
            return
        for row in aligned['members']:
            if row['lead'] and row['strength'] != 'NONE':
                out.setdefault(base + row['offset'], dict(row['lead'], strength=row['strength'], parentType=type_name))
            if row['type'] and row['type'] in go.structs:
                walk(row['type'], base + row['offset'])
    walk(record_type, 0)
    return out


def default_library() -> GoLibrary:
    import build_profile
    return GoLibrary(build_profile.datalibrary())
