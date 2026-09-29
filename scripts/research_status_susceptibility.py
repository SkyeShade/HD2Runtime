"""Target-side status processing: StatusEffectReceiverComponent susceptibility tables. Read-only research.

Prompted by the MaxigunStun live test: Stun Medium (catalogued duration 3 s) was observed to hold enemies for about
1-2 s. This records what the native data says about target-side status processing, without assigning semantics.

StatusEffectReceiverComponentData (46,600 bytes, pinned type library):
  +0      StatusEffectZoneInfo[8]          (5,816 bytes each; a zone-name hash at +0, e.g. "default", "hip", "boss")
            +8  StatusEffectSusceptibility[33]   (176 bytes each)
                  +140 StatusEffectSusceptibilityType (enum; hidden member name length 4)
                  +144 f32, +148 f32              (hidden name lengths 13 and 13; a per-type value pair)
                  +152 u32 x2                     (hashes that do not resolve through the thin-hash list)
                  +168 f32, +172 f32              (default 1.0 / 1.0)
  +46536  (StatusEffectSusceptibilityType, f32)[8]

Every enemy class carries non-default pairs whose values scale with the enemy (for one type: Warrior 2.1/3.3,
Hunter 1/2, Devastator 6.2/8, Charger 8.5/10, Hulk 9/13), which shows status processing is target-dependent. The
enum's value names are stripped, so which type is stun, and whether a pair is a duration range, a strength threshold
or a resistance, is not identified. Nothing here is exposed or used to change status semantics.

Output: research/status-susceptibility-F5FEE03DCFDB.json.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from migration import build_view  # noqa: E402
import research_entity_authoring as entity_research  # noqa: E402

OUTPUT = ROOT / 'research/status-susceptibility-F5FEE03DCFDB.json'
ENEMIES = ROOT / 'research/enemy-authoring-F5FEE03DCFDB.json'
STATUS = ROOT / 'research/status-effects-F5FEE03DCFDB.json'
ZONES, ZONE_SIZE, ENTRIES, ENTRY_SIZE = 8, 5816, 33, 176
# (offset, size, storage, hidden-name length) checked against the pinned type library every run.
ENTRY_FINGERPRINT = ((140, 4, 'ENUM_UINT32', 4), (144, 4, 'FP32', 13), (148, 4, 'FP32', 13), (168, 4, 'FP32', 17),
    (172, 4, 'FP32', 19))


def fingerprint_ok() -> bool:
    library = build_view.TypeLibrary((build_profile.FILEDIVER / 'datalibrary/dl_library.dl_typelib').read_bytes())
    record = build_view._record_layout(library, library.layout('StatusEffectReceiverComponentData')['members'][1]['type_hash'])
    if getattr(record, 'size', None) != 46600:
        return False
    zone = build_view._record_layout(library, record.members[0]['typeHash'])
    entry = build_view._record_layout(library, zone.members[2]['typeHash'])
    members = {(m['offset'], m['size'], m['storage'], m['nameLength']) for m in entry.members}
    return getattr(entry, 'size', None) == ENTRY_SIZE and set(ENTRY_FINGERPRINT) <= members


def build():
    if not fingerprint_ok():
        raise ValueError('StatusEffectReceiver layout fingerprint changed')
    native = entity_research.Native()
    classes = json.loads(ENEMIES.read_text(encoding='utf-8'))['classes']
    default_entry = struct.pack('<140xIff', 0, 0.0, 1.0) + bytes(16) + struct.pack('<ff', 1.0, 1.0)
    rows, pair_values = [], {}
    for item in sorted(classes, key=lambda c: c['className']):
        component = native.component(item['resource'], 'StatusEffectReceiverComponentData')
        if not component:
            continue
        raw = native.record('StatusEffectReceiverComponentData', component['record_index'])
        zones = []
        for zone in range(ZONES):
            base = zone * ZONE_SIZE
            name_hash = struct.unpack_from('<I', raw, base)[0]
            entries = []
            for index in range(ENTRIES):
                at = base + 8 + index * ENTRY_SIZE
                kind = struct.unpack_from('<I', raw, at + 140)[0]
                pair = [round(v, 4) for v in struct.unpack_from('<ff', raw, at + 144)]
                scale = [round(v, 4) for v in struct.unpack_from('<ff', raw, at + 168)]
                hashes = [v for v in struct.unpack_from('<2I', raw, at + 152) if v]
                if raw[at:at + ENTRY_SIZE] == default_entry or (kind == 0 and pair == [0.0, 1.0] and not hashes):
                    continue
                entries.append({'type': kind, 'pair': pair, 'scale': scale, 'hashes': hashes})
                pair_values.setdefault(kind, {})[item['className']] = pair
            if name_hash or entries:
                zones.append({'zone': native.thin_name(name_hash) or name_hash, 'entries': entries})
        rows.append({'className': item['className'], 'wikiName': item['wikiName'], 'faction': item['faction'],
            'zones': zones})
    statuses = json.loads(STATUS.read_text(encoding='utf-8'))['statuses']
    varying = {kind: len({tuple(v) for v in values.values()}) for kind, values in pair_values.items()}
    return {'schemaVersion': 1, 'writes': 0, 'fixtureFallback': 'disabled',
        'layout': {'component': 'StatusEffectReceiverComponentData', 'size': 46600, 'zones': ZONES,
            'entriesPerZone': ENTRIES, 'entrySize': ENTRY_SIZE, 'entryFingerprint': ENTRY_FINGERPRINT},
        'liveObservation': {'test': 'MaxigunStun', 'status': 'stun_medium', 'strength': 2,
            'catalogDuration': next(s['duration'] for s in statuses if s['semanticId'] == 'stun_medium'),
            'observed': 'about 1-2 s on Hunters, Berserkers and Devastators (user report)'},
        'finding': ('Every enemy class carries per-susceptibility-type value pairs whose values scale with the enemy, '
            'so status processing is target-dependent. The susceptibility enum names are stripped: which type is stun '
            'and what a pair means (duration range, strength threshold or resistance) are not identified. Status '
            'duration semantics are unchanged.'),
        'summary': {'classesWithReceiver': len(rows),
            'typesSeen': sorted(pair_values), 'typesVaryingByClass': sorted(k for k, v in varying.items() if v > 1),
            'entriesPerClass': dict(Counter(sum(len(z['entries']) for z in r['zones']) for r in rows))},
        'classes': rows}


def main():
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['summary'], indent=1))


if __name__ == '__main__':
    main()
