"""Carrier payload research, stage A (docs/custom-stratagems.md, "Payload stage B: the 120mm pattern on the carrier"):
can a discovered orbital carrier's own BombardmentComponentData take a donor's bombardment pattern (the Orbital 120mm
HE Barrage's) without writing the donor? Read-only, offline: the game.dll image and the seven retained snapshots of
build F5FEE03DCFDB. Nothing is written.

Proves:

1. The record lookup. The game finds a payload's bombardment record by its payload hash (0x503DC0): the index at
   [[game+0x346BF98]+0xF12A80] has 44 slots of {u64 hash, u32 record, u32 flags} (hash mod 44, linear probe); the
   record is index + 0x2C0 + record x 192. 0x5043C0 first looks for an entity's private copy in the bombardment
   manager [game+0x3326CE8] (+0x70 key/value table, capacity +0x78, empty key +0x7C; copies at +0xB0, stride 192).
2. The barrages. The manager's instances (count +0x24; barrages +0x20) each have a handle [+0x48][i] = {u64 payload
   hash, u32 entity}; barrage start (0x8518F0) counts the shell list's non-zero entries; the per-frame update
   (0x852170) re-reads the record for every shell: the shell type at +0x40 + idx*4 (idx = (idx + 1) mod count, reset
   every salvo), its ProjectileInfo row from [game+0x37C7670 + type*8] (a zero type fires the empty row 0x37C7560);
   the delays +0x08/+0x0C (between shells) and +0x1C/+0x20 (between salvos), the scatter +0x24, the aim walk
   +0x10/+0x14, the salvo-centre scatter +0x28, the drift +0x60. Creation (0x8547E0) reads the shells per salvo +0x04
   and the salvo count +0x18.
3. The variants. 0x12E5590 collects, for a payload hash, the deltas of every ACTIVE variant ([game+0x347CDD0]: active
   ids at +0x420, stride 0x50, count +0x2C20; groups at +0x20, count +0x18; a group {u32 id, entries +8 (32 bytes:
   hash list +0, count +8), count +0x10}): a spawned entity of that payload gets a private copy with them applied.
4. On every snapshot: each record is owned by one index slot; each orbital bombardment's record belongs to its own row's
   payload only; no private copy, no instance, no active variant; the records are identical in all seven snapshots.
5. Compatibility with the donor's pattern: a carrier is compatible when its row's delivery value (+0x3C) equals the
   donor's and its record differs from the donor's only in the code-proven pattern words above; the words to copy are
   exactly those that differ.
6. The Orbital Gas Strike's chain (stage C, read only): its record's one shell is 197; ProjectileInfo 197 (the table
   at game+0x37C7670) names impact explosion 82 at +0x90 (SpawnProjectile copies it, 0x13AA646; the impact uses the
   copy, 0x13AD7FD -> RequestExplosion 0x13C0A80); ExplosionInfo 82 (game+0x37CC920, 0x13C0DC0) names damage 447 at +4
   (0x13C2AF8; DamageInfo table game+0x37C60C0, 0x13C2B2B), radii +0x10/+0x14/+0x18 and the volume template 16 at +0x64
   for +0x68 seconds (template table game+0x37C5E90, 0x13C28F0; the status effect volume 0x13CD320, 0x13C2967);
   DamageInfo 447 applies statuses 42 (gas) and 44 (gas_confusion) once; template 16 applies 42 and 44 every tick
   while the volume lasts. Every row is identical in all seven snapshots except words holding relocated pointers
   (masked).

Output: research/bombardment-payload-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS, TABLE  # noqa: E402
from validate_event_world_snapshot import MISSION  # noqa: E402

OUTPUT = ROOT / 'research/bombardment-payload-F5FEE03DCFDB.json'
COMPONENTS, INDEX_FIELD, SLOTS, RECORDS, RECORD_OFFSET, STRIDE = 0x346BF98, 0xF12A80, 44, 23, 0x2C0, 192
MANAGER, VARIANTS, SHELL_TABLE, EMPTY_SHELL = 0x3326CE8, 0x347CDD0, 0x37C7670, 0x37C7560
CLOCK, CLOCK_FIELD = 0x3326348, 0x18
SHELL_STRIDE = 272
DONOR = 'Orbital 120mm HE Barrage'

GAME = {
    'recordLookup': [
        (0x503DC5, 'mov rax, qword ptr [rip + {rip}]', COMPONENTS, 'the shared lookup: the component instance ...'),
        (0x503DCF, 'mov r10, qword ptr [rax + 0xf12a80]', None, '... its bombardment index'),
        (0x503DE7, 'imul eax, edx, 0x2c', None, 'slot = payload hash mod 44'),
        (0x503DFA, 'mov rdx, qword ptr [rax]', None, 'a slot\'s payload hash'),
        (0x503E14, 'cmp eax, 0x2b', None, 'linear probe, wrapping after slot 43'),
        (0x503E1B, 'cmp r9d, 0x2c', None, 'at most 44 probes'),
        (0x503E29, 'mov ecx, dword ptr [rax + 8]', None, 'the slot\'s record index'),
        (0x503E34, 'add rax, 0x2c0', None, 'record = index + 0x2C0 + record x 192'),
        (0x503E3A, 'add rax, r10', None, '(relative to the index)'),
    ],
    'privateCopies': [
        (0x5043D3, 'mov eax, dword ptr [rcx + 8]', None, 'the per-entity lookup: the entity id'),
        (0x5043E2, 'mov r11, qword ptr [rip + {rip}]', MANAGER, 'the bombardment manager'),
        (0x5043FB, 'mov r9d, dword ptr [r11 + 0x78]', None, 'the private-copy table\'s capacity'),
        (0x504417, 'mov rdi, qword ptr [r11 + 0x70]', None, 'the private-copy table ({u32 entity, u32 copy})'),
        (0x50441B, 'mov esi, dword ptr [r11 + 0x7c]', None, 'its empty key'),
        (0x50445D, 'cmp eax, -1', None, 'no copy: -1'),
        (0x50446A, 'add rax, qword ptr [r11 + 0xb0]', None, 'the private copies (stride 192)'),
        (0x50447D, 'jmp 0x503dc0', None, 'otherwise the shared record by payload hash'),
    ],
    'instances': [
        (0x851943, 'mov r15, qword ptr [rip + {rip}]', MANAGER, 'barrage start: the same manager'),
        (0x8521D4, 'cmp dword ptr [rcx + 0x24], edi', None, 'the update: every instance (count +0x24) ...'),
        (0x8522F5, 'cmp dword ptr [r15 + 0x20], 0', None, '... and every barrage (count +0x20)'),
        (0x852382, 'mov rax, qword ptr [r15 + 0x48]', None, 'the instance handles'),
        (0x85238E, 'mov r13, qword ptr [rax + rbx*8]', None, 'a handle: {u64 payload hash, u32 entity}'),
        (0x8523A2, 'call 0x5043c0', None, 'the record, re-read every frame'),
    ],
    'shells': [
        (0x851B6A, 'cmp dword ptr [r14 + 0x40], edi', None, 'barrage start counts the non-zero shell entries: +0x40'),
        (0x851B97, 'cmp dword ptr [r14 + 0x44], 0', None, '+0x44'),
        (0x851BCA, 'cmp dword ptr [r14 + 0x48], 0', None, '+0x48'),
        (0x851BFD, 'cmp dword ptr [r14 + 0x4c], 0', None, '+0x4C'),
        (0x851C30, 'cmp dword ptr [r14 + 0x50], 0', None, '+0x50 (and on to +0x5C)'),
        (0x852591, 'mov eax, dword ptr [rsi + 0x48]', None, 'per shell: the barrage\'s index ...'),
        (0x852596, 'mov ecx, dword ptr [r14 + rax*4 + 0x40]', None, '... the shell type at +0x40 + idx*4 ...'),
        (0x85259D, 'div dword ptr [rsi + 0x4c]', None, '... idx = (idx + 1) mod the count fixed at start'),
        (0x8525A7, 'lea rdi, [rip + {rip}]', EMPTY_SHELL, 'a zero type fires the empty row'),
        (0x8525BA, 'mov rdi, qword ptr [rcx + rax*8 + 0x37c7670]', None, 'the shell\'s ProjectileInfo row'),
        (0x853946, 'mov dword ptr [rsi + 0x48], edi', None, 'idx reset at every salvo'),
    ],
    'timing': [
        (0x854889, 'mov ecx, dword ptr [rax + 4]', None, 'creation: shells per salvo (+0x04)'),
        (0x854890, 'mov ecx, dword ptr [rax + 0x18]', None, 'creation: salvo count (+0x18)'),
        (0x853545, 'mulss xmm0, dword ptr [r14 + 0xc]', None, 'delay to the next shell: +0x08 + r x +0x0C ...'),
        (0x85354B, 'addss xmm0, dword ptr [r14 + 8]', None, '... (+0x08)'),
        (0x85393A, 'mulss xmm0, dword ptr [r14 + 0x20]', None, 'delay to the next salvo: +0x1C + r x +0x20 ...'),
        (0x853940, 'addss xmm0, dword ptr [r14 + 0x1c]', None, '... (+0x1C)'),
    ],
    'spread': [
        (0x8526AF, 'mulss xmm0, dword ptr [r14 + 0x24]', None, 'per-shell scatter (+0x24)'),
        (0x852621, 'mulss xmm2, dword ptr [r14 + 0x14]', None, 'aim walk upper (+0x14)'),
        (0x85262C, 'mulss xmm1, dword ptr [r14 + 0x10]', None, 'aim walk lower (+0x10)'),
        (0x8538E7, 'mulss xmm2, dword ptr [r14 + 0x28]', None, 'salvo-centre scatter (+0x28)'),
        (0x851AC4, 'movss xmm8, dword ptr [r14 + 0x60]', None, 'barrage drift (+0x60)'),
    ],
    # An entry's availability (0x66D200): on cooldown while its cooldown end (an absolute game time, record entry
    # +0x18) is above the game clock. A never-called entry is NOT 0: the record holds one shared time for every entry.
    'readiness': [
        (0x66D24A, 'mov rcx, qword ptr [rsi + 0x1a0]', None, 'availability: the entry\'s cooldown end (u64) ...'),
        (0x66D251, 'mov rax, qword ptr [rip + {rip}]', CLOCK, '... against the game clock object ...'),
        (0x66D258, 'cmp rcx, qword ptr [rax + 0x18]', None, '... its time (u64) ...'),
        (0x66D25C, 'ja 0x66d34f', None, '... above it: on cooldown, unavailable'),
    ],
    'gasChain': [
        (0x13AA646, 'mov ecx, dword ptr [rax + 0x90]', None, 'SpawnProjectile: the shell row\'s impact explosion (+0x90)'),
        (0x13AD7FD, 'cmp dword ptr [r14 + 0x7c], 0', None, 'the impact: the projectile\'s copy of it'),
        (0x13B0A00, 'call 0x13c0a80', None, '... RequestExplosion'),
        (0x13C0DC0, 'mov r14, qword ptr [rcx + rax*8 + 0x37cc920]', None, 'the explosion row (ExplosionInfo table)'),
        (0x13C2AF8, 'mov eax, dword ptr [r14 + 4]', None, 'the explosion\'s damage (+4)'),
        (0x13C2B2B, 'mov rax, qword ptr [r12 + rax*8 + 0x37c60c0]', None, 'its DamageInfo row'),
        (0x13C28F0, 'mov rdx, qword ptr [rbx + rdx*8 + 0x37c5e90]', None, 'the explosion\'s volume template (+0x64) row'),
        (0x13C2967, 'call 0x13cd320', None, 'the status effect volume (+0x68 seconds)'),
    ],
    'variants': [
        (0x12E55A9, 'mov rbp, qword ptr [rip + {rip}]', VARIANTS, 'the variant deltas for a payload hash: the registry'),
        (0x12E55E7, 'cmp dword ptr [rbp + 0x2c20], esi', None, 'the active variants\' count'),
        (0x12E5607, 'mov rax, qword ptr [rbp + rcx*8 + 0x420]', None, 'an active variant (stride 0x50)'),
        (0x12E5614, 'mov r8d, dword ptr [rax]', None, 'its group id'),
        (0x12E561C, 'mov edx, dword ptr [rbp + 0x18]', None, 'the groups\' count'),
        (0x12E5629, 'lea rax, [rbp + 0x20]', None, 'the groups'),
        (0x12E5633, 'cmp dword ptr [r11], r8d', None, 'a group\'s id'),
        (0x12E564C, 'cmp dword ptr [r11 + 0x10], r10d', None, 'its entries\' count'),
        (0x12E565B, 'add r8, qword ptr [r11 + 8]', None, 'its entries (32 bytes)'),
        (0x12E565F, 'mov edx, dword ptr [r8 + 8]', None, 'an entry\'s hash count'),
        (0x12E5663, 'mov r9, qword ptr [r8]', None, 'its hashes'),
        (0x12E5670, 'cmp qword ptr [r9 + rax*8], rbx', None, 'the payload hash among them'),
    ],
}
# The pattern words: every member a code-proven reader above uses for the bombardment's pattern. A carrier takes the
# donor's pattern by copying exactly the pattern words that differ; anything else must already be equal.
PATTERN = [
    {'offset': 0x04, 'type': 'u32', 'role': 'shells per salvo (read at creation)'},
    {'offset': 0x08, 'type': 'f32', 'role': 'delay between shells'},
    {'offset': 0x0C, 'type': 'f32', 'role': 'delay between shells: random part'},
    {'offset': 0x10, 'type': 'f32', 'role': 'aim walk after the first shell: lower'},
    {'offset': 0x14, 'type': 'f32', 'role': 'aim walk after the first shell: upper'},
    {'offset': 0x18, 'type': 'u32', 'role': 'salvo count (read at creation)'},
    {'offset': 0x1C, 'type': 'f32', 'role': 'delay between salvos'},
    {'offset': 0x20, 'type': 'f32', 'role': 'delay between salvos: random part'},
    {'offset': 0x24, 'type': 'f32', 'role': 'per-shell scatter'},
    {'offset': 0x28, 'type': 'f32', 'role': 'salvo-centre scatter'},
] + [{'offset': 0x40 + 4 * k, 'type': 'u32', 'role': 'shell %d' % k} for k in range(8)] + [
    {'offset': 0x60, 'type': 'f32', 'role': 'barrage drift'},
]
PATTERN_OFFSETS = {w['offset'] for w in PATTERN}
DELIVERY = 0x3C   # StratagemInfo +0x3C: the call-in delivery value (5 for the barrages, 1 for the strikes)


# The Gas Strike chain's rows, by their tables (pointers indexed by id) and strides.
GAS_CHAIN = [
    ('explosion', 0x37CC920, 152, 82),
    ('damage', 0x37C60C0, 76, 447),
    ('template', 0x37C5E90, 40, 16),
    ('status', 0x37C5C50, 152, 42),
    ('status', 0x37C5C50, 152, 44),
]


def catalogue():
    """Every catalogued stratagem with a BombardmentComponentData root: {name: {id, payloads}}."""
    text = (ROOT / 'schemas/stratagem_authoring_catalog.json').read_text(encoding='utf-8')
    data = json.loads(text)['stratagems']
    out = {}
    for name, entry in data.items():
        link = entry.get('rootLink') or {}
        if link.get('component') == 'BombardmentComponentData':
            out[name] = {'id': entry['root']['id'], 'payload': link['payload'], 'family': entry.get('family'),
                'recordIndex': link.get('recordIndex'), 'indexRow': link.get('indexRow')}
    return out


def words(raw):
    return [raw[i:i + 4] for i in range(0, STRIDE, 4)]


def value(raw, offset, kind):
    return struct.unpack_from('<f' if kind == 'f32' else '<I', raw, offset)[0]


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    header = re.search(r'\["BombardmentComponentData"\]=\{[^}]*\["header"\]="([0-9a-f]+)"',
        (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')).group(1)

    stratagems = catalogue()
    if DONOR not in stratagems:
        raise ValueError('the donor has no reviewed bombardment root')
    per_snapshot, records_seen, shells_seen = [], {}, {}
    chain_seen, chain_links = {}, []
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        g = mem.game
        index = mem.ptr(mem.ptr(g + COMPONENTS) + INDEX_FIELD)
        if mem.read(index - 28, 28).hex() != header:
            raise ValueError('bombardment component framing differs in %s' % name)
        raw = mem.read(index, SLOTS * 16)
        slots = [struct.unpack_from('<QII', raw, i * 16) for i in range(SLOTS)]
        if any(r >= RECORDS or f for h, r, f in slots if h):
            raise ValueError('bombardment index bounds in %s' % name)
        owners = {}
        for i, (h, r, f) in enumerate(slots):
            if h:
                owners.setdefault(r, []).append(i)
        rows = {}
        for t in range(1, 150):
            p = mem.ptr(g + TABLE + 8 * t)
            if not p:
                continue
            count, plist = mem.u32(p + 0xA0), mem.ptr(p + 0x98)
            rows[t] = {'id': mem.u32(p + 4), 'delivery': mem.read(p + DELIVERY, 1)[0],
                'payloads': ['0x%016X' % mem.u64(plist + 8 * k) for k in range(count or 0)] if plist else []}
        by_id = {r['id']: t for t, r in rows.items()}
        listed = {}
        for t, r in rows.items():
            for h in r['payloads']:
                listed.setdefault(h, []).append(t)
        found = {}
        for sname, s in stratagems.items():
            h = int(s['payload'], 16)
            # The game's own probe (0x503DC0).
            slot, record = h % SLOTS, None
            for _ in range(SLOTS):
                if slots[slot][0] == h:
                    record = slots[slot][1]
                    break
                if slots[slot][0] == 0:
                    break
                slot = 0 if slot == SLOTS - 1 else slot + 1
            if record is None:
                raise ValueError('%s has no bombardment record in %s' % (sname, name))
            t = by_id[s['id']]
            data = mem.read(index + RECORD_OFFSET + record * STRIDE, STRIDE)
            found[sname] = {'record': record, 'indexRow': slot, 'owners': owners[record], 'type': t,
                'delivery': rows[t]['delivery'], 'rowsListing': listed.get(s['payload'].upper(), listed.get(s['payload'])),
                'hex': data.hex()}
            records_seen.setdefault(sname, set()).add(data.hex())
            for k in range(8):
                shell = struct.unpack_from('<I', data, 0x40 + 4 * k)[0]
                if shell:
                    row = mem.ptr(g + SHELL_TABLE + 8 * shell)
                    shells_seen.setdefault(shell, set()).add(mem.read(row, SHELL_STRIDE).hex() if row else None)
        for kind, table, stride, ident in GAS_CHAIN:
            row = mem.ptr(g + table + 8 * ident)
            chain_seen.setdefault((kind, ident), []).append(mem.read(row, stride) if row else None)
        p197 = mem.ptr(g + SHELL_TABLE + 8 * 197)
        chain_links.append({'snapshot': name, 'shell197Explosion': mem.u32(p197 + 0x90), 'shell197Direct': mem.u32(p197 + 0x3C)})
        mgr = mem.ptr(g + MANAGER)
        mm = mem.read(mgr, 0xC0)
        u32 = lambda o: struct.unpack_from('<I', mm, o)[0]
        cap, empty, table = u32(0x78), u32(0x7C), struct.unpack_from('<Q', mm, 0x70)[0]
        private = 0
        if table and cap:
            tab = mem.read(table, cap * 8)
            private = sum(1 for k in range(cap) if struct.unpack_from('<I', tab, k * 8)[0] != empty
                and struct.unpack_from('<I', tab, k * 8 + 4)[0] != 0xFFFFFFFF) if tab else None
        variants = mem.ptr(g + VARIANTS)
        active = mem.u32(variants + 0x2C20)
        region = mem.s.region(index)
        per_snapshot.append({'snapshot': name, 'phase': MISSION.get(name, 'ship'),
            'instances': u32(0x24), 'barrages': u32(0x20), 'privateCopies': private, 'activeVariants': active,
            'records': {n: {k: v for k, v in f.items() if k != 'hex'} for n, f in found.items()},
            'entityRegion': {'protect': region.get('protect'), 'type': region.get('type')} if region else None,
            'recordsIdentical': None})
        for n, f in found.items():
            if len(f['owners']) != 1 or f['rowsListing'] != [f['type']]:
                raise ValueError('%s: record %d owners %r, rows listing its payload %r in %s'
                    % (n, f['record'], f['owners'], f['rowsListing'], name))
        if u32(0x24) or u32(0x20) or private or active:
            raise ValueError('a barrage, private copy or active variant exists in %s' % name)
        last = found
        mem.close()
    if any(len(v) != 1 for v in records_seen.values()) or any(len(v) != 1 for v in shells_seen.values()):
        raise ValueError('a bombardment record or shell row differs between snapshots')

    donor = bytes.fromhex(next(iter(records_seen[DONOR])))
    reviewed, compatibility = {}, {}
    for sname, s in sorted(stratagems.items()):
        raw = bytes.fromhex(next(iter(records_seen[sname])))
        shells = [struct.unpack_from('<I', raw, 0x40 + 4 * k)[0] for k in range(8)]
        count = len([x for x in shells if x])
        packed = shells[:count] == [x for x in shells if x]
        reviewed[str(s['id'])] = {'name': sname, 'payload': s['payload'], 'record': last[sname]['record'],
            'indexRow': last[sname]['indexRow'], 'delivery': last[sname]['delivery'], 'vanilla': raw.hex(),
            'shells': [x for x in shells if x], 'packed': packed}
        if sname == DONOR:
            continue
        differ = [o for o in range(0, STRIDE, 4) if raw[o:o + 4] != donor[o:o + 4]]
        outside = [o for o in differ if o not in PATTERN_OFFSETS]
        reasons = []
        if last[sname]['delivery'] != last[DONOR]['delivery']:
            reasons.append('row +0x3C (call-in delivery) %d, the donor %d' % (last[sname]['delivery'],
                last[DONOR]['delivery']))
        if outside:
            reasons.append('record words outside the pattern differ: ' + ', '.join('+0x%02X' % o for o in outside))
        if not packed:
            reasons.append('the shell list is not packed')
        kinds = {w['offset']: w['type'] for w in PATTERN}
        compatibility[str(s['id'])] = {'name': sname, 'compatible': not reasons, 'reasons': reasons,
            'words': [{'offset': o, 'type': kinds.get(o, 'u32'), 'carrier': value(raw, o, kinds.get(o, 'u32')),
                'donor': value(donor, o, kinds.get(o, 'u32'))} for o in differ]}
    shell_rows = {str(k): next(iter(v)) for k, v in sorted(shells_seen.items())}
    # The Gas Strike chain: each row's bytes, the words that differ between snapshots masked (relocated pointers).
    chain = []
    for (kind, ident), rows in chain_seen.items():
        if any(r is None for r in rows):
            raise ValueError('a Gas Strike chain row is missing: %s %d' % (kind, ident))
        stride = len(rows[0])
        masked = [o for o in range(0, stride, 4) if len({r[o:o + 4] for r in rows}) != 1]
        table = next(t for k, t, st, i in GAS_CHAIN if (k, i) == (kind, ident))
        chain.append({'kind': kind, 'id': ident, 'table': '0x%X' % table, 'stride': stride, 'reviewed': rows[0].hex(),
            'masked': masked})
    rows_by = {(c['kind'], c['id']): bytes.fromhex(c['reviewed']) for c in chain}
    links = {link['shell197Explosion'] for link in chain_links}
    explosion, damage, template = rows_by[('explosion', 82)], rows_by[('damage', 447)], rows_by[('template', 16)]
    gas_chain = {'shell': 197, 'shellExplosion': 82, 'shellDirectDamage': chain_links[0]['shell197Direct'],
        'explosionDamage': struct.unpack_from('<I', explosion, 4)[0],
        'radii': [struct.unpack_from('<f', explosion, o)[0] for o in (0x10, 0x14, 0x18)],
        'volumeTemplate': struct.unpack_from('<I', explosion, 0x64)[0],
        'volumeSeconds': struct.unpack_from('<f', explosion, 0x68)[0],
        'damageStatuses': [[struct.unpack_from('<I', damage, 44 + 8 * k)[0], struct.unpack_from('<f', damage, 48 + 8 * k)[0]]
            for k in range(4) if struct.unpack_from('<I', damage, 44 + 8 * k)[0]],
        'templateStatuses': [[struct.unpack_from('<I', template, 4 + 8 * k)[0], struct.unpack_from('<f', template, 8 + 8 * k)[0]]
            for k in range(4) if struct.unpack_from('<I', template, 4 + 8 * k)[0]],
        'rows': chain}
    if links != {82} or gas_chain['explosionDamage'] != 447 or gas_chain['volumeTemplate'] != 16 \
            or gas_chain['volumeSeconds'] != 15.0 or gas_chain['radii'][1] != 15.0 \
            or [s_[0] for s_ in gas_chain['damageStatuses']] != [42, 44] \
            or [s_[0] for s_ in gas_chain['templateStatuses']] != [42, 44]:
        raise ValueError('the Gas Strike chain differs from the research: %r' % gas_chain)
    if records_seen['Orbital Gas Strike'] and [x for x in [struct.unpack_from('<I', bytes.fromhex(
            next(iter(records_seen['Orbital Gas Strike']))), 0x40 + 4 * k)[0] for k in range(8)] if x] != [197]:
        raise ValueError('the Gas Strike record\'s shell list is not [197]')
    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'gameDll': {'sha256': base.PROFILE_DLL_SHA},
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation,
        'component': {'global': '0x%X' % COMPONENTS, 'indexField': '0x%X' % INDEX_FIELD, 'header': header,
            'slots': SLOTS, 'records': RECORDS, 'recordOffset': RECORD_OFFSET, 'stride': STRIDE},
        'manager': {'global': '0x%X' % MANAGER, 'barrages': 0x20, 'instances': 0x24, 'handles': 0x48,
            'handleHash': 0, 'handleEntity': 8, 'privateTable': 0x70, 'privateCapacity': 0x78, 'privateEmpty': 0x7C,
            'privateNone': 0xFFFFFFFF, 'privateCopies': 0xB0},
        'variants': {'global': '0x%X' % VARIANTS, 'activeCount': 0x2C20, 'active': 0x420, 'activeStride': 0x50,
            'groupCount': 0x18, 'groups': 0x20, 'groupId': 0, 'entries': 8, 'entryCount': 0x10, 'entryStride': 32,
            'hashes': 0, 'hashCount': 8},
        'clock': {'global': '0x%X' % CLOCK, 'time': CLOCK_FIELD},
        'shellTable': '0x%X' % SHELL_TABLE, 'emptyShell': '0x%X' % EMPTY_SHELL, 'shellStride': SHELL_STRIDE,
        'delivery': DELIVERY, 'pattern': PATTERN, 'donor': DONOR,
        'records': reviewed, 'shellRows': shell_rows, 'compatibility': compatibility, 'snapshots': per_snapshot,
        'gasChain': gas_chain, 'shellDonor': 'Orbital Gas Strike',
        'determinations': {
            'ownership': ('Each record has exactly one index slot, and each orbital bombardment\'s record belongs to '
                'its own row\'s payload only; but the shared record is per type: every instance of that payload reads '
                'it, another player\'s included. Solo only.'),
            'timing': ('The shell list\'s count is fixed when a barrage starts and the record is re-read every frame: '
                'never write while an instance of the payload exists; +0x04/+0x18 are read at creation.'),
            'variants': ('An active variant naming the payload would give a spawned entity a private copy with its '
                'deltas: none is active in any snapshot; a write requires none.'),
            'compatibility': ('A carrier takes the donor\'s pattern by copying exactly the pattern words that differ, '
                'when its row delivery value equals the donor\'s and nothing outside the pattern differs.'),
            'gasChain': ('The single reference rec+0x40.. = 197 brings the Gas Strike\'s whole chain: shell 197 -> '
                'explosion 82 -> damage 447 (gas and gas_confusion once) and the volume template 16 for 15 s, radius 15 '
                '(gas and gas_confusion every tick). Nothing of the chain is written: the carrier only points at 197.')}}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; records', len(reviewed), '; compatible',
        sorted(c['name'] for c in compatibility.values() if c['compatible']))


if __name__ == '__main__':
    main()
