"""The converted slot's cooldown (docs/custom-stratagems.md, "The fixed cooldown: research"): where a mission
stratagem record entry's cooldown lives, what the game writes when the entry is called, how it is compared with the
game clock, what the HUD shows from it and how it travels to peers, so that a converted virtual slot (the Gas Barrage
carrier) can be given a fixed cooldown without touching the carrier's own StratagemInfo row. Read-only, offline: the
game.dll image and the seven retained snapshots of build F5FEE03DCFDB. Nothing is written.

Proves:

1. The entry's times. A record entry (0x30 bytes, research/stratagem-slot-conversion) holds three u64 game times:
   +0x10 the activation, +0x18 the cooldown end, +0x20 the call-in's arrival. The game clock is
   [[game+0x3326348]+0x18], a u64 in MICROSECONDS (the HUD and 0x66CE4A divide the difference by 1000000.0).
2. Availability. 0x66D200 compares the entry's end with the clock unsigned: above it, the entry is unavailable
   (on cooldown); 0x6711C0 returns the remaining time (end - clock, or 0). Every entry has its own end; the type 0x7C
   (Reinforce) reads a shared one instead.
3. What a call writes [O]. In the mission snapshots a never-called entry holds one shared time from the record's
   build (110331400, below the clock); a called entry holds its activation, its arrival and an end where
   end - arrival = the row's cooldown (StratagemInfo +0x68, seconds) x the active modifiers: the Orbital EMS Strike
   75 s -> 64.125 s (x 0.855), the Reinforce 6 s -> 5.7 s (x 0.95). The cooldown is counted from the ARRIVAL. The code
   that writes it at a call is not in the unprotected .text (every direct writer of +0x18 there is listed below:
   the record build's zeroes, the entry removal and the peer sync); a live proof records the write.
4. The HUD. Each frame, per slot of the in-mission list (hud + pathOffset + index x 0x3760): +0x3718 = (arrival -
   clock) / 1e6 and +0x3720 = (end - clock) / 1e6. The slot is INBOUND (state 3) while the first is above 0, then
   COOLING (state 4) while the second is; its bar widget (slot +0x7C0) resets its total (+0x14C4) to -1 on every change
   into state 3 or 4 and takes the FIRST remaining time it sees as the total; the bar shows 1 - remaining / total. So
   an end written before the arrival is the total the bar shows; one written later only moves the remaining time.
5. Peers. rpc_sync_stratagems (0x670530) carries a record from its peer: the sender writes each entry's REMAINING
   cooldown (max(end - clock, 0), 0x11E8699-0x11E86AD) and the receiver rebuilds end = remaining + its own clock
   (0x11E8376-0x11E837F). A row whose cooldown type (+0x94) is non-zero also copies it into another record's entries of
   that type (0x11E83BB, 0x11E84A0). The cooldown therefore replicates as a remaining time; a solo record has no peer.
6. The ship. The record build writes end 0 (0x66EFD0 defaults, 0x66F190 append, 0x66F3xx); a new mission's record
   holds one shared time below the clock in every entry: nothing of a mission's cooldown survives into the next one.

Output: research/slot-cooldown-F5FEE03DCFDB.json.
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
from research_stratagem_calldown import SNAPSHOTS, TABLE, RECORDS, HUD_SYSTEM, HUD_SETUP, PATH_OFFSET  # noqa: E402
from research_stratagem_calldown import HUD_SLOT_STRIDE, HUD_SLOT_INDEX, HUD_SLOT_TYPE, HUD_SLOTS  # noqa: E402
from research_stratagem_slot_conversion import catalogue_roots  # noqa: E402

OUTPUT = ROOT / 'research/slot-cooldown-F5FEE03DCFDB.json'
CLOCK, CLOCK_FIELD, MICROSECONDS = 0x3326348, 0x18, 0x23C7EC0
RECORD_STRIDE, RECORD_COUNT, STATE, ENTRIES, ENTRY_STRIDE, ENTRY_COUNT = 0x1690, 0x2D200, 0x38, 0x188, 0x30, 0x788
ACTIVATION, COOLDOWN_END, ARRIVAL = 0x10, 0x18, 0x20
ROW_COOLDOWN, ROW_COOLDOWN_TYPE = 0x68, 0x94
SLOT_INBOUND, SLOT_COOLING, BAR = 0x3718, 0x3720, 0x7C0
BAR_INDEX, BAR_TOTAL, BAR_STATE = 0x14B8, 0x14C4, 0x14CC
SYNC_LOG = 'rpc_sync_stratagems from %llx (stratagem count: %u)'

GAME = {
    'availability': [
        (0x66D24A, 'mov rcx, qword ptr [rsi + 0x1a0]', None, 'availability: the entry\'s cooldown end (+0x18, u64) ...'),
        (0x66D251, 'mov rax, qword ptr [rip + {rip}]', CLOCK, '... against the game clock object ...'),
        (0x66D258, 'cmp rcx, qword ptr [rax + 0x18]', None, '... its time (u64, microseconds) ...'),
        (0x66D25C, 'ja 0x66d34f', None, '... above it (unsigned): unavailable'),
        (0x6711F5, 'mov rax, qword ptr [rdx + rcx*8 + 0x1a0]', None, 'the remaining time: the entry\'s end ...'),
        (0x671201, 'mov rcx, qword ptr [rip + {rip}]', CLOCK, '... the clock ...'),
        (0x671208, 'mov rdx, qword ptr [rcx + 0x18]', None, '... its time ...'),
        (0x67120C, 'cmp rax, rdx', None, '... end above it ...'),
        (0x671211, 'sub rax, rdx', None, '... end - clock (else 0)'),
        (0x66CE60, 'mov rbx, qword ptr [rdx + rbx*8 + 0x1a0]', None, 'a reader of the end ...'),
        (0x66CE4A, 'sub rbx, rcx', None, '... end - clock ...'),
        (0x66CE4D, 'cvtsi2ss xmm6, rbx', None, '... as a float ...'),
        (0x66CE52, 'divss xmm6, dword ptr [rip + {rip}]', MICROSECONDS, '... / 1000000.0: seconds (the clock counts '
            'microseconds)'),
    ],
    'recordBuild': [
        (0x66F13A, 'mov qword ptr [rdi + 0x1a0], 0', None, 'the record build\'s defaults: end 0'),
        (0x66F2E0, 'mov qword ptr [rsi + 0x1a0], 0', None, 'the record append: end 0'),
        (0x66F467, 'mov qword ptr [r14 + 0x1a0], 0', None, 'another record build path: end 0'),
    ],
    'hud': [
        (0x183678D, 'mov rax, qword ptr [r10 + rcx*8 + 0x1a8]', None, 'HUD slot: the entry\'s arrival (+0x20) ...'),
        (0x1836798, 'sub rax, qword ptr [r10 + rcx*8 + 0x198]', None, '... minus its activation (+0x10) ...'),
        (0x18367C6, 'divss xmm0, xmm8', None, '... / 1e6 ...'),
        (0x18367CB, 'movss dword ptr [r15 + 0x3714], xmm0', None, '... the inbound duration (slot +0x3714)'),
        (0x18367D4, 'mov rax, qword ptr [r10 + rcx*8 + 0x1a8]', None, 'the arrival ...'),
        (0x18367DC, 'sub rax, qword ptr [r8 + 0x18]', None, '... minus the clock ...'),
        (0x18367F2, 'movss dword ptr [r15 + 0x3718], xmm0', None, '... the inbound time left (slot +0x3718, s)'),
        (0x18368EA, 'mov rax, qword ptr [r10 + rcx*8 + 0x1a0]', None, 'the cooldown end ...'),
        (0x18368F7, 'sub rax, qword ptr [r8 + 0x18]', None, '... minus the clock ...'),
        (0x1836903, 'divss xmm0, xmm8', None, '... / 1e6 ...'),
        (0x1836908, 'movss dword ptr [r15 + 0x3720], xmm0', None, '... the cooldown left (slot +0x3720, s)'),
        (0x1836A30, 'movss xmm0, dword ptr [r15 + 0x3718]', None, 'inbound time left above 0 ...'),
        (0x1836A3F, 'mov dword ptr [rsp + 0x54], 3', None, '... state 3 (inbound)'),
        (0x1836BEA, 'movss xmm0, dword ptr [r15 + 0x3720]', None, 'else cooldown left above 0 ...'),
        (0x1836BF9, 'mov dword ptr [rsp + 0x54], 4', None, '... state 4 (cooling)'),
        (0x18375E1, 'lea rcx, [r15 + 0x7c0]', None, 'the slot\'s bar widget (slot +0x7C0) ...'),
        (0x18375F6, 'call 0x1839fd0', None, '... updated with the state'),
        (0x183A358, 'cmp dword ptr [rsi + 0x14cc], r13d', None, 'a state change ...'),
        (0x183A367, 'call 0x183aa60', None, '... sets it'),
        (0x183AAAA, 'mov dword ptr [rcx + 0x14cc], edx', None, 'the bar\'s state (+0x14CC)'),
        (0x183AB93, 'mov dword ptr [rbx + 0x14c4], 0xbf800000', None, 'entering state 3 or 4: the bar\'s total = -1'),
        (0x183A91E, 'mov eax, dword ptr [rsi + 0x14b8]', None, 'state 4: the bar\'s entry index (+0x14B8) ...'),
        (0x183A952, 'mov r14, qword ptr [r15 + rcx*8 + 0x1a0]', None, '... that entry\'s cooldown end ...'),
        (0x183A964, 'mov rcx, qword ptr [rax + 0x18]', None, '... the clock ...'),
        (0x183A96D, 'sub r14, rcx', None, '... end - clock ...'),
        (0x183A975, 'divss xmm0, dword ptr [rip + {rip}]', MICROSECONDS, '... / 1000000.0: the remaining time'),
        (0x183A97D, 'movss xmm1, dword ptr [rsi + 0x14c4]', None, 'the bar\'s total ...'),
        (0x183A985, 'comiss xmm8, xmm1', None, '... still unset (below 0) ...'),
        (0x183A99C, 'movss dword ptr [rsi + 0x14c4], xmm1', None, '... takes the first remaining time it sees'),
        (0x183A9A4, 'divss xmm0, xmm1', None, 'remaining / total ...'),
        (0x183A9AE, 'subss xmm9, xmm0', None, '... the bar shows 1 - remaining / total'),
    ],
    'peerSync': [
        (0x670567, 'lea rdx, [rip + {rip}]', None, 'the handler of rpc_sync_stratagems (its log line) ...'),
        (0x670717, 'call 0x11e82d0', None, '... writes the sending peer\'s record'),
        (0x11E82EE, 'mov rbp, qword ptr [rip + {rip}]', CLOCK, 'the receiver\'s clock'),
        (0x11E8376, 'mov rax, qword ptr [r9 + rdi*8 + 8]', None, 'a received entry\'s remaining cooldown ...'),
        (0x11E837B, 'add rax, qword ptr [rbp + 0x18]', None, '... + the receiver\'s clock ...'),
        (0x11E837F, 'mov qword ptr [rcx + 0x1a0], rax', None, '... is the entry\'s end'),
        (0x11E83BB, 'mov eax, dword ptr [rax + 0x94]', None, 'the type\'s cooldown type (row +0x94): 0, the entry only'),
        (0x11E83C9, 'cmp eax, 2', None, 'a shared cooldown type ...'),
        (0x11E84A0, 'mov qword ptr [r8 + rdx*8 + 0x1a0], rcx', None, '... is copied into another record\'s entries of that '
            'type'),
        (0x11E8629, 'mov rax, qword ptr [rip + {rip}]', CLOCK, 'the sender\'s clock'),
        (0x11E8699, 'mov rdx, qword ptr [rax + 0x14]', None, 'the sender: each entry\'s end ...'),
        (0x11E869D, 'mov rcx, rdx', None, '...'),
        (0x11E86A0, 'sub rcx, rsi', None, '... - the clock ...'),
        (0x11E86A6, 'cmovbe rcx, r14', None, '... or 0 ...'),
        (0x11E86AD, 'mov qword ptr [r10], rcx', None, '... is sent: the REMAINING cooldown'),
    ],
}


def u64(raw, at):
    return struct.unpack_from('<Q', raw, at)[0]


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    sync_text = pins['peerSync'][0]['ripTarget']
    if game.cstr(sync_text) != SYNC_LOG:
        raise ValueError('the rpc_sync_stratagems handler\'s log line changed')
    if struct.unpack_from('<f', game_data, MICROSECONDS)[0] != 1000000.0:
        raise ValueError('the clock divisor is not 1000000.0')
    pins['constants'] = [{'rva': MICROSECONDS, 'bytes': game_data[MICROSECONDS:MICROSECONDS + 4].hex(),
        'asm': 'dd 1000000.0', 'role': 'the clock\'s unit: 1000000.0 per second'}]
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    names = {root['id']: name for name, root in catalogue_roots().items()}
    snapshots, calls, bars = [], [], []
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        g = mem.game
        clock = mem.u64(mem.ptr(g + CLOCK) + CLOCK_FIELD)
        records = mem.ptr(g + RECORDS)
        count = mem.u32(records + RECORD_COUNT)
        if count != 1:
            raise ValueError('%s: %d stratagem records (the retained snapshots are solo)' % (name, count))
        state = records + STATE
        n = mem.u32(state + ENTRY_COUNT)
        hud = mem.ptr(g + HUD_SYSTEM)
        set_up = hud is not None and mem.read(hud + HUD_SETUP, 1) == b'\x01'
        entries, shared = [], {}
        for k in range(n):
            raw = mem.read(state + ENTRIES + k * ENTRY_STRIDE, ENTRY_STRIDE)
            kind, uses = struct.unpack_from('<Ii', raw, 0)
            row = mem.ptr(g + TABLE + kind * 8)
            row_raw = mem.read(row, 0x98)
            stable = struct.unpack_from('<I', row_raw, 4)[0]
            cooldown = struct.unpack_from('<f', row_raw, ROW_COOLDOWN)[0]
            ctype = struct.unpack_from('<I', row_raw, ROW_COOLDOWN_TYPE)[0]
            activation, end, arrival = u64(raw, ACTIVATION), u64(raw, COOLDOWN_END), u64(raw, ARRIVAL)
            e = {'index': k, 'type': kind, 'id': stable, 'name': names.get(stable), 'uses': uses, 'granted': raw[9],
                'rowCooldown': cooldown, 'rowCooldownType': ctype, 'activation': activation, 'end': end,
                'arrival': arrival, 'onCooldown': end > clock}
            shared[end] = shared.get(end, 0) + 1
            if activation and arrival:
                e['inboundSeconds'] = (arrival - activation) / 1e6
                e['afterArrivalSeconds'] = (end - arrival) / 1e6
                e['modifier'] = round(e['afterArrivalSeconds'] / cooldown, 6) if cooldown else None
                calls.append({'snapshot': name, 'name': e['name'], 'type': kind, 'rowCooldown': cooldown,
                    'inboundSeconds': e['inboundSeconds'], 'afterArrivalSeconds': e['afterArrivalSeconds'],
                    'modifier': e['modifier']})
            if set_up and k < HUD_SLOTS:
                slot = hud + PATH_OFFSET + k * HUD_SLOT_STRIDE
                bar = slot + BAR
                e['hud'] = {'index': mem.u32(slot + HUD_SLOT_INDEX), 'type': mem.u32(slot + HUD_SLOT_TYPE),
                    'inboundLeft': struct.unpack('<f', mem.read(slot + SLOT_INBOUND, 4))[0],
                    'coolingLeft': struct.unpack('<f', mem.read(slot + SLOT_COOLING, 4))[0],
                    'barIndex': mem.u32(bar + BAR_INDEX), 'barState': mem.u32(bar + BAR_STATE),
                    'barTotal': struct.unpack('<f', mem.read(bar + BAR_TOTAL, 4))[0]}
            entries.append(e)
        # The bar's total is the time left on its first cooling frame: that frame's clock = end - total.
        for e in entries:
            total = e.get('hud', {}).get('barTotal', 0.0)
            if total > 0:
                first = e['end'] - round(total * 1e6)
                bars.append({'snapshot': name, 'name': e['name'], 'type': e['type'], 'barTotal': total,
                    'firstCoolingClock': first, 'afterArrivalSeconds': (first - e['arrival']) / 1e6 if e['arrival']
                    else None, 'afterActivationSeconds': (first - e['activation']) / 1e6})
        baseline = max(shared, key=shared.get) if entries else None
        snapshots.append({'snapshot': name, 'clock': clock, 'records': count, 'hudSetUp': set_up,
            'sharedEnd': baseline, 'sharedEndBelowClock': baseline is not None and baseline <= clock,
            'entries': entries})
        mem.close()
    # The exact evidence: every called entry with a cooldown proper (not the eagles' shared rearm) ends a whole
    # multiple of the row's cooldown after its ARRIVAL.
    ems = [c for c in calls if c['name'] == 'Orbital EMS Strike']
    if not ems or ems[0]['afterArrivalSeconds'] != 64.125 or ems[0]['rowCooldown'] != 75.0:
        raise ValueError('the EMS Strike call no longer shows end = arrival + 75 s x 0.855: %r' % ems)
    rearm = [x for x in bars if x['type'] == 49]
    if not rearm or abs(rearm[0]['barTotal'] - 102.6) > 1e-4:
        raise ValueError('the HUD bar no longer holds the first cooling frame\'s time left: %r' % bars)
    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'gameDll': {'sha256': base.PROFILE_DLL_SHA},
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation,
        'clock': {'global': '0x%X' % CLOCK, 'time': CLOCK_FIELD, 'perSecond': 1000000},
        'entry': {'activation': ACTIVATION, 'cooldownEnd': COOLDOWN_END, 'arrival': ARRIVAL},
        'row': {'cooldown': ROW_COOLDOWN, 'cooldownType': ROW_COOLDOWN_TYPE},
        'hud': {'inboundLeft': SLOT_INBOUND, 'coolingLeft': SLOT_COOLING, 'bar': BAR, 'barIndex': BAR_INDEX,
            'barTotal': BAR_TOTAL, 'barState': BAR_STATE, 'inbound': 3, 'cooling': 4},
        'snapshots': snapshots, 'calls': calls, 'bars': bars,
        'determinations': {
            'where': ('Per entry of the local player\'s mission stratagem record: +0x18 the cooldown end (u64 game time, '
                'microseconds), with +0x10 the activation and +0x20 the call-in\'s arrival. Not the StratagemInfo row '
                '(its +0x68 is the cooldown in seconds the game starts from) and not a per-player structure.'),
            'written': ('At a call the entry gets an activation, an arrival and end = arrival + row cooldown x the '
                'active modifiers (EMS Strike 75 s -> 64.125 s after its arrival, x 0.855). The writing code is not '
                'in the unprotected .text: a live proof records the write.'),
            'compared': ('0x66D200: unavailable while end > clock (unsigned u64); the clock is '
                '[[game+0x3326348]+0x18] in microseconds; the HUD shows (end - clock) / 1e6 seconds.'),
            'scope': ('A write of one entry\'s +0x18 changes that entry only (every reader indexes the entry); a row '
                'with a non-zero cooldown type (+0x94) is also copied between records by the peer sync, so a carrier '
                'must have type 0.'),
            'afterCall': ('Safe once the game has written its own end: every reader only compares it with the clock. '
                'Written before the arrival, the HUD bar takes it as its total; later, only the time left moves.'),
            'beforeCall': ('Not useful: above the clock the entry is unavailable (it could not be called); at or below '
                'it the call\'s own write replaces it.'),
            'replication': ('rpc_sync_stratagems carries each entry\'s remaining cooldown and the receiver rebuilds '
                'the end on its own clock: a changed end replicates. Solo only.'),
            'restore': ('Nothing to restore: the row\'s cooldown is never written, and the record\'s ends are mission '
                'state the game rebuilds (0 at the build, one shared time below the clock in a new mission).'),
            'existingApi': ('hd2.fields.stratagem.cooldown is the row\'s +0x68 (every use of the type, the carrier\'s '
                'native cooldown): not for a converted slot. The slot conversion already reads the entry\'s end '
                '(stratagem_slot_conversion.observe) and the payload guard the clock; nothing writes the end.')}}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; calls', [(c['name'], c['afterArrivalSeconds'],
        c['modifier']) for c in calls])


if __name__ == '__main__':
    main()
