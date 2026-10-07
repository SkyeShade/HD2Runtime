"""Native barrage -> call association (research/docs/runtime-peer-messaging-F5FEE03DCFDB.md section 18;
local_research/mp/barrage/barrage-association-notes.md). Read-only, offline: the game.dll image and the seven retained
snapshots of build F5FEE03DCFDB. Nothing is written, no game function is called.

Live r5 (two players): the custom identity of a redirected Orbital Gas Barrage worked (its barrage's creation type is the
frozen carrier), but its association with the call failed on both machines ("matches 0 of its own calls at its target",
"matches 0 of its beacons seen here"). This research follows the creation path from the beacon's activation to the
bombardment instance and every field the instance is created with.

Proves:

1. The activation (0x6AB3E0, the systems pass 0x571305): an owned beacon (state) crossing its threshold sets its state
   +0x8E4 (0x6ABB8D) and calls the dispatcher 0x6ABDB0 (0x6ABC72) with the beacon manager, the instance index, the
   thrower's player entity, a pointer to a copy of the STATE +0x30 position (0x6ABC46, 0x6ABC3D, 0x6ABC41), the dispatch
   record = state +0x40 (0x6ABB89) and the element's +0xC type (the redirected 136).
2. The dispatcher: the dispatch record (ctx) +0x3F8 := the beacon entity (0x6ABE48); per payload +0x3D8 := the payload
   hash (0x6AD1D4, state +0x418); the payload's offset = the row's per-payload offset (+0x130, rotated by the beacon's
   heading) (0x6AD240 .. 0x6AD4B1), plus, for delivery kinds 1 and 5 only, a square scatter of half-width r on x/y
   (0x6AD4C8 .. 0x6AD5ED; r = the sum of the active mission effects keyed 0xA8B06BF1, 0x12D26C0; 0 with none); the spawn
   position = position + offset (0x6AD645 .. 0x6AD69A) at the spawn descriptor's +0x38 (0x6AD8B1); the descriptor's
   +0x48 names the ctx (0x6AD7D3); ctx +0x898 := 10 (0x6AD90F, state +0x8D8) and the spawn request (0x6AD919), which
   spawns the entity at once (0xFD9710 -> 0xFDC0C0 -> 0xFDC140: created-here bit 0xFDC1D7, the components' creation with
   the descriptor). The spawned handle is not kept: after the request only the element's waves (+0x2C) change
   (0x6AD9F9).
3. The bombardment instance (manager [game+0x3326CE8]): insertion 0x5373E0 (owner group or remote copies; the 0x70
   state zeroed 0x537461), creation 0x5374D0 -> 0x8547E0 with the descriptor: block (+0x60, 0x1C) +0 shells per salvo
   (0x854902), +4 salvos (0x8549AD), +8 the target = 0x851650(descriptor) (0x8549ED, 0x854A00), +0x14 a heading
   (0x854A52), +0x18 a seed from the manager's own generator (0x854A86, 0x854AAF). 0x851650: when the record's +0x88 is
   0 (0x8516D7, 0x8516ED) the target IS the descriptor's +0x38 (0x8516F9, 0x851701); else a drift-compensated start.
   A remote copy copies the creator's block verbatim (0x854B00: 0x854BA5). The block moves with its handle and the map
   follows (0x854490: 0x854534, 0x8545B7): block index == handle index == the entity map's value.
4. The start (0x8518F0): start delay = record +0x80 (+ 0xA0AF50 when record +0x3C); its aim := the target (0x851AA9).
   The update (0x852170, systems pass 0x572E5C, after the beacon update 0x571305) fires a shell once the shell timer
   (zeroed at insertion) runs out (0x852578, 0x852582): with no start delay the first shell is fired in the frame of the
   activation.
5. The beacon's own position: at its creation the element +0x10 := the beacon's spawn position (0x6A5FEE, 0x6AE95D) and
   the state's transform := the same descriptor (0x6A60CD); the state +0x30 is later set from the placement check
   (0x6A8913, 0x6A8967). A copy on another machine (no state) gets the element from the creation message (0x6AED30:
   0x6AEDF2, called 0xBD5374).
6. Nothing in the barrage names its beacon: component 131 copies the ctx's +0x398 (the beacon's creation type, state
   +0x3D8: 0x6A8F72, 0x52B67E), component 28 the creating machine's local peer (0x51A3F6), component 48 the network id
   of the ctx's +0x3A4 entity (the ball's creation parameter +0xC, copied at the landing 0x6A3154: the caller's object,
   0x9EF3C8, 0x9EF3D7); the ctx's beacon entity (+0x3F8) is read through a spawn descriptor only by the Transport (pod)
   component (0x6DBC74, 0x6DBF43, 0x6DBF52).
7. [O] in every snapshot: the 120mm's row (136) lists one payload and no per-payload offset (+0x130 count 0; the default
   vector 0x3797950 is zero); the 120mm's record has +0x88 = +0x84 = +0x60 = 0 (its target is the spawn position) and
   +0x80 = 0; every orbital row (delivery 1 or 5) has +0x78 bit 0 clear (the element +0x10 is not moved) and +0x74 = 0.

Output: research/barrage-association-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS, TABLE  # noqa: E402
from research_bombardment_payload import (COMPONENTS, INDEX_FIELD, SLOTS, RECORDS, RECORD_OFFSET, STRIDE,  # noqa: E402
    catalogue)

OUTPUT = ROOT / 'research/barrage-association-F5FEE03DCFDB.json'
DONOR, DONOR_TYPE, DONOR_PAYLOAD = 'Orbital 120mm HE Barrage', 136, 0x2D3BD00B1ED411B1
ZERO_VECTOR, SCATTER_BASIS, SCATTER_EFFECT = 0x3797950, 0x3289A10, 0xA8B06BF1
# The bombardment block (manager +0x60, 0x1C per instance) and the instance state (manager +0x58, 0x70 each).
BLOCK = {'shells': 0x00, 'salvos': 0x04, 'target': 0x08, 'heading': 0x14, 'seed': 0x18}
STATE = {'states': 0x58, 'stride': 0x70, 'fired': 0x00}
# The beacon: state +0x30 the dispatcher's position, +0x3D8 its creation parameters (+0 the creation type), +0x8E4 the
# activation flag; the element +0x10 the position every machine holds (a copy's from the creation message). The dispatch
# record (state +0x40): +0x3D8 the payload (state +0x418), +0x898 = 10 before the spawn request (state +0x8D8).
BEACON = {'statePosition': 0x30, 'creationType': 0x3D8, 'activated': 0x8E4, 'elementPosition': 0x10,
    'dispatchPayload': 0x418, 'dispatchSpawn': 0x8D8, 'spawnRequested': 10}
RECORD = {'drift': 0x60, 'startDelay': 0x80, 'driftAngle': 0x84, 'driftStart': 0x88, 'startDelayEntity': 0x3C}

PINS = {
    'activation': [
        (0x571305, 'call 0x6ab3e0', None, 'the systems pass: the beacon update ...'),
        (0x572E5C, 'call 0x852170', None, '... and, later in the same pass, the bombardment update'),
        (0x6ABB77, 'cmp byte ptr [r13 + 0x8e4], 0', None, 'an owned beacon crossing its threshold, not yet activated ...'),
        (0x6ABB89, 'lea r15, [r13 + 0x40]', None, '... its dispatch record (state + 0x40) ...'),
        (0x6ABB8D, 'mov byte ptr [r13 + 0x8e4], 1', None, '... is marked activated before the dispatcher runs'),
        (0x6ABB9D, 'mov r14d, dword ptr [rcx + 0x10]', None, 'the beacon\'s entity handle +0x10: its network id (0x7FFF: '
            'none)'),
        (0x6ABC3D, 'mov eax, dword ptr [r13 + 0x38]', None, 'the dispatcher\'s position: the state +0x30 (z) ...'),
        (0x6ABC41, 'lea r9, [rsp + 0x60]', None, '... a copy on the stack, passed by pointer ...'),
        (0x6ABC46, 'movsd xmm0, qword ptr [r13 + 0x30]', None, '... (x, y)'),
        (0x6ABC72, 'call 0x6abdb0', None, 'the dispatcher, in the activation update'),
    ],
    'dispatcher': [
        (0x6ABDF0, 'mov r13, r9', None, 'the dispatcher keeps the position pointer (never written through)'),
        (0x6ABE48, 'mov dword ptr [rsi + 0x3f8], eax', None, 'ctx +0x3F8 := the beacon entity'),
        (0x6AD1D4, 'mov qword ptr [rsi + 0x3d8], rdx', None, 'ctx +0x3D8 := the payload hash (state +0x418)'),
        (0x6AD240, 'movsd xmm4, qword ptr [rdx]', None, 'the row\'s per-payload offset (+0x130; none: the zero vector)'),
        (0x6AD491, 'movsd qword ptr [rsi + 0x7c0], xmm0', None, '... rotated by the beacon\'s heading into ctx +0x7C0'),
        (0x6AD4C8, 'mov edx, 0xa8b06bf1', None, 'delivery kinds 1 and 5: the mission\'s scatter (effects keyed 0xA8B06BF1) '
            '...'),
        (0x6AD4CD, 'call 0x12d26c0', None, '... their summed value r (0 with none) ...'),
        (0x6AD5CD, 'addss xmm1, dword ptr [rsi + 0x7c0]', None, '... adds u x r on x and y (u uniform in [-1, 1], this '
            'machine\'s generator) to the offset'),
        (0x6AD645, 'movss xmm0, dword ptr [r13]', None, 'the spawn position: the beacon\'s position ...'),
        (0x6AD64F, 'addss xmm0, dword ptr [rsi + 0x7c0]', None, '... plus the offset ...'),
        (0x6AD8B1, 'movups xmmword ptr [rbp + 0x38], xmm0', None, '... at the spawn descriptor\'s +0x38'),
        (0x6AD7D3, 'mov qword ptr [rbp + 0x48], rsi', None, 'the descriptor\'s +0x48 names the ctx'),
        (0x6AD90F, 'mov dword ptr [rsi + 0x898], 0xa', None, 'ctx +0x898 := 10 (state +0x8D8) ...'),
        (0x6AD919, 'call 0xfd9710', None, '... and the spawn request'),
        (0x6AD91E, 'mov ecx, dword ptr [rsp + 0x44]', None, 'the spawned handle is not kept ...'),
        (0x6AD9F9, 'mov dword ptr [rcx + rax + 0x2c], r8d', None, '... only the element\'s waves (+0x2C) change'),
    ],
    'spawn': [
        (0xFDC1D7, 'mov dword ptr [r14 + 0x14], 1', None, 'the spawn runs at once: the handle\'s created-here bit'),
        (0x5374EC, 'call 0x8547e0', None, 'the bombardment creation, with the spawn descriptor'),
        (0x537461, 'movups xmmword ptr [rax], xmm0', None, 'its 0x70 state zeroed at the insertion (shell timer 0)'),
    ],
    'block': [
        (0x854902, 'mov dword ptr [rcx + r13], eax', None, 'block +0: shells per salvo (with the creator\'s modules)'),
        (0x8549AD, 'mov dword ptr [rcx + r13 + 4], eax', None, 'block +4: salvos'),
        (0x8549ED, 'call 0x851650', None, 'the target, from the descriptor ...'),
        (0x854A00, 'movsd qword ptr [rcx + r13 + 8], xmm0', None, '... block +8'),
        (0x854A52, 'movss dword ptr [rax + r13 + 0x14], xmm0', None, 'block +0x14: the heading'),
        (0x854A86, 'movabs rax, 0x5851f42d4c957f2d', None, 'the manager\'s own generator ...'),
        (0x854AAF, 'mov dword ptr [rax + r13 + 0x18], ecx', None, '... block +0x18: the seed'),
        (0x8516D7, 'movss xmm1, dword ptr [r15 + 0x88]', None, 'the target: the record\'s +0x88 ...'),
        (0x8516ED, 'ucomiss xmm1, xmm0', None, '... is 0 ...'),
        (0x8516F9, 'movsd xmm0, qword ptr [rsi + 0x38]', None, '... the target is the descriptor\'s +0x38 ...'),
        (0x851701, 'movsd qword ptr [rbx], xmm0', None, '... unchanged'),
        (0x854BA5, 'movsd qword ptr [r8 + 8], xmm0', None, 'a remote copy: the creator\'s target, verbatim'),
        (0x854534, 'movups xmmword ptr [r8 + rdx], xmm0', None, 'a moved instance takes its block with it ...'),
        (0x8545B7, 'mov dword ptr [r8 + 4], r14d', None, '... and the entity map its new index'),
    ],
    'start': [
        (0x8519B7, 'movss xmm1, dword ptr [rax + 0x80]', None, 'the start delay: the record\'s +0x80 ...'),
        (0x8519BF, 'cmp byte ptr [rax + 0x3c], dil', None, '... plus, when +0x3C, ...'),
        (0x851A20, 'call 0xa0af50', None, '... an entity timeline\'s remaining time (0 with none)'),
        (0x851AA9, 'movsd qword ptr [rsi + 0x14], xmm0', None, 'the aim starts at the target'),
        (0x852578, 'movss xmm0, dword ptr [rsi + 8]', None, 'the update: the shell timer ...'),
        (0x852582, 'comiss xmm14, xmm0', None, '... run out: a shell (its first update for a new barrage)'),
        (0x853554, 'inc dword ptr [rsi]', None, 'state +0: the shells fired by this machine\'s copy'),
    ],
    'beaconPosition': [
        (0x6A5FEE, 'movsd xmm0, qword ptr [r9 + 0x38]', None, 'the beacon\'s creation: its spawn position ...'),
        (0x6AE95D, 'movsd qword ptr [rdi + rcx + 0x10], xmm0', None, '... into the element +0x10 (a network field)'),
        (0x6A60CD, 'movups xmmword ptr [rdx + rax + 0x30], xmm3', None, 'the state\'s transform from the same descriptor'),
        (0x6A8913, 'movups xmmword ptr [r13 + 0x30], xmm1', None, 'the state +0x30 set again when the state starts ...'),
        (0x6A8967, 'movsd qword ptr [r13 + 0x30], xmm0', None, '... from the placement check of the element +0x10'),
        (0xBD5374, 'call 0x6aed30', None, 'a copy on another machine (no state) ...'),
        (0x6AEDF2, 'movsd qword ptr [r8 + 0x10], xmm0', None, '... gets the element +0x10 from the creation message'),
    ],
    'noBeaconLink': [
        (0x6A8F72, 'movups xmmword ptr [rbx + 0x3d8], xmm0', None, 'the state +0x3D8: the beacon\'s creation parameters '
            '(+0 its creation type)'),
        (0x52B67E, 'mov ecx, dword ptr [rcx + 0x398]', None, 'component 131: the ctx\'s +0x398 (= state +0x3D8)'),
        (0x51A3F6, 'mov rdx, qword ptr [rcx + 0xb398]', None, 'component 28: the creating machine\'s local peer'),
        (0x6A3154, 'movups xmmword ptr [rbp + 0x398], xmm0', None, 'the landing copies the ball\'s creation parameters '
            '(type +0, entity +0xC) into the beacon\'s spawn ctx'),
        (0x9EF3C8, 'mov ecx, dword ptr [rcx + 0x3a4]', None, 'component 48 ([game+0x3326C38]): the ctx\'s +0x3A4 entity '
            '...'),
        (0x9EF3D7, 'mov dword ptr [rbx + rcx], eax', None, '... its network id at +0x40 (field 0xD22B948C): the caller\'s '
            'object, not the beacon'),
        (0x6DBC74, 'mov ecx, dword ptr [rax + 0x3f8]', None, 'the ctx\'s beacon entity is read through a spawn '
            'descriptor only in the Transport (pod) component ...'),
        (0x6DBF43, 'mov ecx, dword ptr [rax + 0x3f8]', None, '... which makes it a network field ...'),
        (0x6DBF52, 'mov dword ptr [rbx + rcx + 0x10], eax', None, '... (its +0x10: the beacon\'s network id)'),
    ],
}


def f32(raw, at):
    return struct.unpack_from('<f', raw, at)[0]


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def record_of(mem, payload):
    """A payload's shared bombardment record, by the game's own probe (0x503DC0), or None."""
    index = mem.ptr(mem.ptr(mem.game + COMPONENTS) + INDEX_FIELD)
    raw = mem.read(index, SLOTS * 16)
    slot = payload % SLOTS
    for _ in range(SLOTS):
        h, r, f = struct.unpack_from('<QII', raw, slot * 16)
        if h == payload:
            if r >= RECORDS or f:
                raise ValueError('bombardment index bounds')
            return mem.read(index + RECORD_OFFSET + r * STRIDE, STRIDE)
        if h == 0:
            return None
        slot = 0 if slot == SLOTS - 1 else slot + 1
    return None


def observe(name, bombardments):
    mem = base.Mem(name)
    g = mem.game
    row = mem.ptr(g + TABLE + DONOR_TYPE * 8)
    raw = mem.read(row, 0x180)
    plist, pcount = struct.unpack_from('<QI', raw, 0x98)
    offsets, ocount = struct.unpack_from('<QI', raw, 0x130)
    floats, fcount = struct.unpack_from('<QI', raw, 0x140)
    out = {'snapshot': name, 'row136': {'delivery': u32(raw, 0x3C), 'payloads': ['0x%016X' % mem.u64(plist + 8 * k)
        for k in range(pcount)], 'offsetCount': ocount, 'offsetFloatCount': fcount},
        'zeroVector': mem.read(g + ZERO_VECTOR, 12).hex(),
        'scatterBasis': [round(f32(mem.read(g + SCATTER_BASIS, 0x1C), k * 4), 6) for k in range(7)]}
    orbital = {}
    for t in range(1, 400):
        p = mem.ptr(g + TABLE + 8 * t)
        r = p and mem.read(p, 0x180)
        if not r or u32(r, 0x3C) not in (1, 5):
            continue
        orbital[t] = {'delivery': u32(r, 0x3C), 'moveFlag': u32(r, 0x78) & 1, 'placement': u32(r, 0x74)}
    out['orbitalRows'] = orbital
    records = {}
    for sname, s in bombardments.items():
        rec = record_of(mem, int(s['payload'], 16))
        if rec is None:
            continue
        records[s['payload']] = {'name': sname, 'drift': f32(rec, RECORD['drift']), 'startDelay': f32(rec,
            RECORD['startDelay']), 'driftAngle': f32(rec, RECORD['driftAngle']), 'driftStart': f32(rec, RECORD['driftStart']),
            'startDelayEntity': rec[RECORD['startDelayEntity']]}
    out['records'] = records
    mem.close()
    return out


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    pins = {group: [dict(game.prove(*row), module='game') for row in rows] for group, rows in PINS.items()}
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    bombardments = catalogue()
    snapshots = [observe(name, bombardments) for name in SNAPSHOTS]
    first = snapshots[0]
    for s in snapshots:
        if {k: v for k, v in s.items() if k != 'snapshot'} != {k: v for k, v in first.items() if k != 'snapshot'}:
            raise ValueError('%s: the rows, records or constants differ between snapshots' % s['snapshot'])
    row = first['row136']
    if row['payloads'] != ['0x%016X' % DONOR_PAYLOAD] or row['delivery'] != 5 or row['offsetCount'] != 0:
        raise ValueError('the 120mm row is not one payload without a per-payload offset: %r' % row)
    if first['zeroVector'] != '00' * 12:
        raise ValueError('the default offset vector is not zero')
    donor = first['records'].get('0x%016X' % DONOR_PAYLOAD)
    if not donor or donor['driftStart'] != 0 or donor['startDelay'] != 0:
        raise ValueError('the 120mm record would move its target or delay its start: %r' % donor)
    moved = {t: r for t, r in first['orbitalRows'].items() if r['moveFlag'] or r['placement']}
    if moved:
        raise ValueError('an orbital row moves its beacon position: %r' % moved)
    exact = sorted(p for p, r in first['records'].items() if r['driftStart'] == 0)
    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'nativeCalls': 0,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA}, 'exe': {'sha256': base.PROFILE_EXE_SHA},
        'block': BLOCK, 'state': STATE, 'beacon': BEACON, 'record': RECORD,
        'exactTargetPayloads': exact,
        'scatterEffect': '0x%08X' % SCATTER_EFFECT,
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation, 'snapshots': snapshots,
        'facts': {
            'creation': 'the barrage is spawned at once inside its beacon\'s activation update (0x6ABC72 -> 0x6AD919 -> '
                '0xFDC140 -> 0x5374EC), after the beacon\'s state +0x8E4 is set (0x6ABB8D) [C]',
            'target': 'block +8 = the spawn descriptor\'s +0x38 when the record\'s +0x88 is 0 (every reviewed orbital '
                'payload listed in exactTargetPayloads, the 120mm included) [C, O]; the descriptor\'s +0x38 = the '
                'beacon\'s state +0x30 + the row\'s rotated per-payload offset (none for 136: 0) + the mission scatter '
                '(kinds 1 and 5; 0 without an active effect keyed 0xA8B06BF1) [C, O]. So on the creating machine the '
                'target EQUALS the beacon\'s state +0x30 (the position runtime/beacons.lua position reads), unless a '
                'scatter effect is active (then within r on x and on y; z equal) [C]',
            'remote': 'a remote copy\'s block is the creator\'s, verbatim (0x854BA5): the same target on every machine '
                '[C]; a beacon copy has no state (beacons.lua position returns nil for it) but holds the element +0x10 '
                'from the creation message (0x6AEDF2) = the owner\'s element +0x10, the beacon\'s spawn position; the '
                'owner\'s state +0x30 is that point after its placement check (0x6A8967) [C]; the size of that '
                'check\'s move is U (expected small: a valid ground point near the beacon) [I]',
            'blockIndex': 'block index == handle index == the entity map\'s value; moves keep them together (0x854490) '
                '[C]',
            'noBeaconLink': 'the barrage stores no beacon entity, beacon network id, record entry, call-in key, '
                'timestamp or thrower: its block holds shells, salvos, target, heading and seed; component 131 the '
                'beacon\'s creation type; component 28 the creating machine\'s local peer; the dispatcher does not keep '
                'the spawned handle [C]',
            'time': 'created in the frame of the activation (same update as state +0x8E4); the first shell in that '
                'frame when the start delay is 0 (record +0x80 = 0 for the 120mm; + an entity timeline\'s remaining '
                'time, 0xA0AF50, U; live 0.3.0 read the salvo timer 2.00 and 5 salvos left one update after the '
                'activation, which is the no-delay branch) [C, L]; a remote copy is created when the creation message '
                'arrives (network latency later) [C]',
        }}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), len(flat), 'pins;', len(exact), 'exact-target payloads')


if __name__ == '__main__':
    main()
