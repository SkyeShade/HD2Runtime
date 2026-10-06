"""Retained-snapshot instance analysis: shared type data vs per-instance/runtime data (research only).

The game loads the entity file's component tables into memory once (shared type data). Many components also keep a
per-instance block in their component manager, often seeded by copying the type record at spawn (the instance's own
copy, which per-instance writes can target) and then mutated at runtime.

* ``locate_records``  finds the loaded component table in a snapshot (its exact index bytes) and every type record's
                      address: the shared definitions every owner reads;
* ``find_copies``     finds OTHER occurrences of a record's distinctive bytes in captured heap memory: candidate
                      per-instance copies (a copy outside the loaded table is not shared type data);
* ``compare_copy``    diffs a copy against its type record member by member: equal members are copied type data,
                      differing members are per-instance state (or a resolved/customized value);
* ``diff_snapshots``  the same address range across snapshots of one capture session.

Scans read captured regions in bounded chunks; a full 12 GB snapshot pass takes minutes, so callers should pass a
region filter (heap only) and reuse results. Snapshot evidence is never treated as current-live validation.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import snapshot_image  # noqa: E402
from scan.tables import Component, Member, decode  # noqa: E402

CHUNK = 64 << 20
MEM_IMAGE = 0x1000000
MEM_PRIVATE = 0x20000
CAPTURED = 1


class SnapshotReader:
    def __init__(self, name: str):
        self.name = name
        self.snapshot = snapshot_image.Snapshot(build_profile.snapshot_directory() / name)
        self.modules = self.snapshot.modules

    def close(self):
        self.snapshot.close()

    def read(self, address: int, size: int) -> bytes | None:
        region = self.snapshot.region(address)
        if region is None or region['status'] != CAPTURED or address + size > region['base'] + region['size']:
            return None
        self.snapshot.handle.seek(region['data_offset'] + address - region['base'])
        return self.snapshot.handle.read(size)

    def regions(self, kinds=('private', 'mapped')):
        for region in self.snapshot.regions:
            if region['status'] != CAPTURED:
                continue
            kind = 'image' if region['type'] == MEM_IMAGE else 'private' if region['type'] == MEM_PRIVATE else 'mapped'
            if kind in kinds:
                yield region, kind

    def search(self, needles: dict[str, bytes], kinds=('private', 'mapped'), limit: int = 64) -> dict[str, list[int]]:
        """Addresses of every needle in the selected captured regions (bounded per needle)."""
        found = {key: [] for key in needles}
        longest = max(len(n) for n in needles.values())
        handle = self.snapshot.handle
        for region, _ in self.regions(kinds):
            offset = 0
            while offset < region['size']:
                size = min(CHUNK + longest, region['size'] - offset)
                handle.seek(region['data_offset'] + offset)
                data = handle.read(size)
                for key, needle in needles.items():
                    if len(found[key]) >= limit:
                        continue
                    at = data.find(needle)
                    while at >= 0 and len(found[key]) < limit:
                        if at < CHUNK or offset + CHUNK >= region['size']:
                            found[key].append(region['base'] + offset + at)
                        at = data.find(needle, at + 1)
                offset += CHUNK
        return found


def distinctive_window(raw: bytes, size: int = 24) -> tuple[int, bytes] | None:
    """The record window with the most distinct non-zero bytes (a search key unlikely to occur by chance)."""
    best = None
    for start in range(0, max(len(raw) - size, 0) + 1, 4):
        window = raw[start:start + size]
        score = len(set(window)) - window.count(0)
        if best is None or score > best[0]:
            best = (score, start, window)
    if best is None or best[0] < 8:
        return None
    return best[1], best[2]


def locate_records(reader: SnapshotReader, component: Component) -> dict | None:
    """The loaded copy of a component table: its address and each record's address (shared type data)."""
    index_bytes = component.body[:min(len(component.body), component.capacity * 16, 256)]
    hits = reader.search({'index': index_bytes}, kinds=('private', 'mapped', 'image'), limit=4)['index']
    if len(hits) != 1:
        return {'status': 'absent' if not hits else 'ambiguous', 'hits': len(hits)}
    start = hits[0]
    return {'status': 'located', 'table': start,
        'records': {index: start + component.records_offset + index * component.record_size
            for index in range(component.count)}}


def find_copies(reader: SnapshotReader, component: Component, records=None, exclude: dict | None = None,
                limit: int = 64) -> dict[int, list[int]]:
    """Record index -> heap addresses where the record's distinctive window occurs, minus the loaded table itself
    (``exclude``: the locate_records result). Addresses are of the window, rebased to the record start."""
    records = range(component.count) if records is None else records
    needles, starts = {}, {}
    for index in records:
        window = distinctive_window(component.raw(index))
        if window:
            starts[index] = window[0]
            needles[str(index)] = window[1]
    if not needles:
        return {}
    hits = reader.search(needles, limit=limit)
    loaded = set((exclude or {}).get('records', {}).values())
    result = {}
    for key, addresses in hits.items():
        index = int(key)
        result[index] = [a - starts[index] for a in addresses if a - starts[index] not in loaded]
    return result


def compare_copy(component: Component, record: int, copy: bytes) -> dict:
    """Member-by-member comparison of a candidate per-instance copy with its type record."""
    raw = component.raw(record)
    same, differ = [], []
    for member in component.members():
        if member.offset + member.size > len(copy):
            continue
        a, b = decode(member, raw), decode(member, copy)
        (same if a == b else differ).append({'path': member.path, 'type': a, 'instance': b})
    return {'record': record, 'equalMembers': len(same), 'differingMembers': differ,
        'classification': 'exact_copy' if not differ else 'seeded_copy' if len(same) > len(differ) else 'unrelated'}


def diff_snapshots(names: list[str], address: int, size: int, members: list[Member] | None = None) -> dict:
    """The same address range read from several snapshots (only meaningful within one capture session)."""
    reads = {}
    for name in names:
        reader = SnapshotReader(name)
        try:
            reads[name] = reader.read(address, size)
        finally:
            reader.close()
    out = {'address': address, 'size': size, 'snapshots': {n: (r.hex() if r else None) for n, r in reads.items()}}
    if members:
        changed = []
        present = {n: r for n, r in reads.items() if r}
        for member in members:
            values = {n: decode(member, r) for n, r in present.items() if member.offset + member.size <= len(r)}
            if len({repr(v) for v in values.values()}) > 1:
                changed.append({'path': member.path, 'values': values})
        out['changedMembers'] = changed
    return out


def u64(reader: SnapshotReader, address: int) -> int | None:
    data = reader.read(address, 8)
    return None if data is None else struct.unpack('<Q', data)[0]
