"""A Runtime-owned relocated BeamWeapon component table (EXPERIMENTAL multi-weapon beam swap, branch exp/multi-beam):
can HD2Runtime give the AR-23 Liberator, LAS-58 Talon and SMG-32 Reprimand each its OWN BeamWeapon record (so each has
its own rate of fire and pulse) by making the game read a private copy of the table with three records appended?
Read-only, offline, build F5FEE03DCFDB: the game.dll image of a retained snapshot (capstone), every retained snapshot,
the pinned entity file. Follows research/docs/multi-beam-swap-F5FEE03DCFDB.md section 6 (the plan).

Questions answered here (every answer pinned as exact code bytes and checked in all nine retained snapshots):
  1. Every reader of the BeamWeapon table pointer (slot 270 = [[game + 0x346BF98] + 0xF12478 + 8 x 270]): a raw scan
     of .text for every displacement of the 326-entry slot array, each hit decoded. Does anything cache the pointer?
  2. The lookup: its capacity and stride, where it takes the record base from (the header or the slot), whether it
     bounds the record index (so records 24+ in a copy are reached).
  3. The default record (+0xDA8) sites, the loader's slot store, the reload and unload paths.
  4. The copy: layout, size, and an offline overlay in every snapshot (the copy with the three rows and records
     24 / 25 / 26 = the Trident's record 18: every one of the 1,909 resources' lookups answers byte-identical records
     except the three).

Output: research/beam-table-relocation-F5FEE03DCFDB.json.   py -3 scripts/research_beam_table.py
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_beam_damage import SNAPSHOTS  # noqa: E402
from scan import tables as scan_tables  # noqa: E402

OUTPUT = ROOT / 'research/beam-table-relocation-F5FEE03DCFDB.json'
MULTI = ROOT / 'research/multi-beam-swap-F5FEE03DCFDB.json'
MANAGER_GLOBAL = 0x346BF98
SLOT_BASE, SLOTS, INDEX = 0xF12478, 326, 270
SLOT = SLOT_BASE + 8 * INDEX                     # 0xF12CE8
ESH_SLOT = 0xF12EA0
CAPACITY, ROW_STRIDE, RECORD_BASE, RECORD_STRIDE, FILE_RECORDS, DEFAULT_RECORD = 46, 16, 0x2E0, 0x78, 24, 23
FRAMING = 32                                     # u32 component index + the 28-byte DL header before the table
TRIDENT, TRIDENT_RECORD = 0x3C86E871923F3970, 18
WEAPONS = (('liberator', 0x968211C0033DCE64, 21, 24), ('talon', 0x416D053372C4E433, 11, 25),
           ('reprimand', 0x94BD931B5FB4EE95, 25, 26))
TRAILER_MAGIC = b'HD2RT-OWNED-BEAM'
TRAILER_SIZE = 32                                # magic 16, original table u64, component index u32, records u32

# (rva, asm, rip target or None, role)
PROOFS = {
    'lookup': [
        (0x50E885, 'mov rax, qword ptr [rip + {rip}]', MANAGER_GLOBAL, 'the entity manager from its global'),
        (0x50E88F, 'mov r10, qword ptr [rax + 0xf12ce8]', None, 'slot 270 read on EVERY call (no copy kept)'),
        (0x50E8B3, 'imul eax, eax, 0x2e', None, 'home = resource mod 46: the capacity is code, not the header'),
        (0x50E8C3, 'shl rax, 4', None, '16-byte index rows ...'),
        (0x50E8C7, 'add rax, r10', None, '... from the slot\'s table'),
        (0x50E8D2, 'test rdx, rdx', None, 'key 0 stops the probe'),
        (0x50E8E4, 'cmp eax, 0x2d', None, 'the probe wraps after row 45'),
        (0x50E8EB, 'cmp r9d, 0x2e', None, 'at most 46 probes'),
        (0x50E8F9, 'mov ecx, dword ptr [rax + 8]', None, 'the row\'s u32 record index, NOT bounded'),
        (0x50E8FC, 'imul rax, rcx, 0x78', None, 'record stride 0x78 ...'),
        (0x50E900, 'add rax, 0x2e0', None, '... after the 46 rows (+0x2E0) ...'),
        (0x50E906, 'add rax, r10', None, '... from the slot\'s table: the record base is the slot pointer, never the '
         'header'),
    ],
    'resolver': [
        (0x50ECE2, 'mov r11, qword ptr [rip + {rip}]', None, 'the beam manager: private copies first ...'),
        (0x50ED62, 'imul rax, rax, 0x78', None, '... a private copy by slot x 0x78 ...'),
        (0x50ED66, 'add rax, qword ptr [r11 + 0xb0]', None, '... in the manager\'s own array (values, never a table '
         'pointer)'),
        (0x50ED79, 'jmp 0x50e880', None, 'else the type lookup by resource'),
    ],
    'defaultGetter': [
        (0x50ECA0, 'mov rax, qword ptr [rip + {rip}]', MANAGER_GLOBAL, 'leaf getter: the manager'),
        (0x50ECA7, 'mov rax, qword ptr [rax + 0xf12ce8]', None, 'slot 270 read ...'),
        (0x50ECAE, 'add rax, 0xda8', None, '... + 0xDA8 = record 23 (the unowned default) of the slot\'s table'),
    ],
    'copyCreator': [
        (0x841BB8, 'call 0x50e880', None, 'the delta-copy creator 0x841AF0 looks the record up by resource ...'),
        (0x841BBD, 'mov r8, qword ptr [rip + {rip}]', MANAGER_GLOBAL, '... the manager ...'),
        (0x841BC7, 'jne 0x841bd6', None, '... no row: ...'),
        (0x841BC9, 'mov rax, qword ptr [r8 + 0xf12ce8]', None, '... slot 270 read ...'),
        (0x841BD0, 'add rax, 0xda8', None, '... record 23 of the slot\'s table'),
        (0x841BD6, 'movups xmm0, xmmword ptr [rax]', None, 'the record\'s BYTES are copied into the entity\'s private '
         'copy (no pointer kept)'),
    ],
    'loader': [
        (0xAE0D8B, 'call 0xfdb440', None, 'the entity file loader runs once at startup ...'),
        (0xFDB636, 'mov qword ptr [r13 + r12*8 + 0xf12478], r14', None, '... and is the only store to any slot'),
        (0xFDB866, 'cmp qword ptr [rcx + 0xf12ea0], 0', None, 'reload 0xFDB860 (no callers, no references) ...'),
        (0xFDB873, 'call 0xfdb7c0', None, '... unloads ...'),
        (0xFDB880, 'jmp 0xfdb440', None, '... and loads again: every slot back to a file table'),
        (0xFDB7CF, 'cmp dword ptr [rcx + 0xf12470], esi', None, 'unload 0xFDB7C0 releases the loaded files ...'),
        (0xFDB82B, 'mov dword ptr [rbx + 0xf12470], 0', None, '... and stores no slot'),
    ],
    'otherSlotArraySites': [
        (0x4F2FDF, 'mov r10, qword ptr [rax + 0xf12478]', None, 'slot 0 (a lookup of component index 0)'),
        (0x4F3091, 'mov r11, qword ptr [rax + 0xf12478]', None, 'slot 0 (a lookup of component index 0)'),
        (0x56953B, 'add rax, 0xf12478', None, 'the slot array ...'),
        (0x569543, 'cmp qword ptr [rax + 0xe8], rbp', None, '... slot 29 presence test only'),
        (0x569B78, 'add rax, 0xf12478', None, 'the slot array ...'),
        (0x569B80, 'cmp qword ptr [rax + 0x878], rbp', None, '... slot 271 presence test only'),
        (0x747FEC, 'add rax, 0xf12478', None, 'the slot array ...'),
        (0x747FF4, 'cmp qword ptr [rax + 0x878], 0', None, '... slot 271 presence test only'),
        (0x9F1E24, 'add rax, 0xf12478', None, 'the slot array ...'),
        (0x9F1E2C, 'cmp qword ptr [rax + 0xe8], 0', None, '... slot 29 presence test only'),
    ],
    'shotReads': [
        (0x83EA90, None, None, 'BeamWeapon +104 (fire rate) read per shot'),
        (0x83EAB1, None, None, 'BeamWeapon +112 read per shot'),
    ],
}
# Instructions of the census whose bytes hold a slot-array displacement (address -> the slot they address).
SLOT270_SITES = {0x50E88F: 'type lookup 0x50E880', 0x50ECA7: 'default-record leaf getter 0x50ECA0',
                 0x841BC9: 'delta-copy creator 0x841AF0 (no row: the default record)'}
BASE_SITES = {0x4F2FDF: 0, 0x4F3091: 0, 0x56953B: 29, 0x569B78: 271, 0x747FEC: 271, 0x9F1E24: 29, 0xFDB636: 'store'}


def prove_all(image) -> dict:
    out = {}
    for group, rows in PROOFS.items():
        out[group] = []
        for rva, asm, target, role in rows:
            if asm is None:     # pinned in domains/beam_swap.lua (the live-proven research); bytes only
                insn = image.insn(rva)
                out[group].append({'rva': rva, 'bytes': image.data[rva:rva + insn.size].hex(),
                                   'asm': insn.mnemonic + ' ' + insn.op_str, 'role': role})
            else:
                out[group].append(image.prove(rva, asm, target, role))
    return out


def covering(image, hit: int, sites) -> int | None:
    for at in sites:
        insn = image.insn(at)
        if at <= hit < at + insn.size:
            return at
    return None


def slot_census(image) -> dict:
    """Every 4-byte displacement of the slot array in .text, the hits of slot 270 and of the array base decoded."""
    lo, hi = base.TEXT
    data = image.data
    hits = {}
    for k in range(SLOTS + 1):
        needle = (SLOT_BASE + 8 * k).to_bytes(4, 'little')
        start, found = lo, []
        while True:
            at = data.find(needle, start, hi)
            if at < 0:
                break
            found.append(at)
            start = at + 1
        if found:
            hits[k] = found
    slot270 = hits.get(INDEX, [])
    decoded270 = {}
    for hit in slot270:
        site = covering(image, hit, SLOT270_SITES)
        if site is None:
            raise ValueError('an undecoded slot-270 displacement at 0x%X' % hit)
        decoded270['0x%X' % site] = SLOT270_SITES[site]
    if sorted(decoded270) != sorted('0x%X' % a for a in SLOT270_SITES) or len(slot270) != 3:
        raise ValueError('slot 270 is read at other sites: %r' % [hex(h) for h in slot270])
    base_hits = hits.get(0, [])
    decoded_base = {}
    for hit in base_hits:
        site = covering(image, hit, BASE_SITES)
        if site is None:
            raise ValueError('an undecoded slot-array base displacement at 0x%X' % hit)
        decoded_base['0x%X' % site] = BASE_SITES[site]
    if len(base_hits) != len(BASE_SITES) or len(decoded_base) != len(BASE_SITES):
        raise ValueError('the slot array base is used at other sites: %r' % [hex(h) for h in base_hits])
    # Every value in the manager-field window around the slot array that is not a slot displacement.
    window = {}
    start = lo
    while True:
        at = data.find(b'\xf1\x00', start, hi)
        if at < 0:
            break
        value = int.from_bytes(data[at - 2:at + 2], 'little')
        if 0xF11C00 <= value < 0xF13000 and not (SLOT_BASE <= value <= SLOT_BASE + 8 * SLOTS and value % 8 == 0):
            window.setdefault('0x%X' % value, []).append('0x%X' % (at - 2))
        start = at + 1
    aligned_into_array = sorted(v for v in window if SLOT_BASE <= int(v, 16) < SLOT_BASE + 8 * SLOTS
                                and int(v, 16) % 8 == 0)
    return {'slotsScanned': SLOTS + 1, 'slotsWithHits': len(hits),
            'slot270': {'rawHits': ['0x%X' % h for h in slot270], 'sites': decoded270},
            'slotArrayBase': {'rawHits': ['0x%X' % h for h in base_hits],
                              'sites': {k: ('the loader store' if v == 'store' else 'slot %d' % v)
                                        for k, v in decoded_base.items()},
                              'readsSlot270': False},
            'otherWindowValues': len(window), 'otherWindowValuesAddressingASlot': aligned_into_array,
            'note': 'A raw byte scan: every instruction whose displacement is a slot of the array (manager + 0xF12478 '
                    '+ 8 x index) or the array base (indexed or + constant). Values in the window 0xF11C00..0xF13000 '
                    'that are not 8-aligned slot displacements are the loader\'s own fields (0xF11C70, 0xF12070, '
                    '0xF12270, 0xF12470) or bytes of unrelated instructions; none addresses a slot. The protected '
                    'sections (.vm_sec, .winlice) cannot be scanned (the same limit as every earlier census).'}


def callers(image, target) -> list[int]:
    out = []
    lo, hi = base.TEXT
    data = image.data
    for opcode in (b'\xe8', b'\xe9'):
        start = lo
        while True:
            at = data.find(opcode, start, hi - 5)
            if at < 0:
                break
            rel = struct.unpack_from('<i', data, at + 1)[0]
            if at + 5 + rel == target:
                insn = image.insn(at)
                if insn.size == 5 and insn.mnemonic in ('call', 'jmp'):
                    out.append(at)
            start = at + 1
    return sorted(out)


def references(image, target) -> dict:
    data = image.data
    absolute = struct.pack('<Q', image.base + target)
    count, start = 0, 0
    while True:
        at = data.find(absolute, start)
        if at < 0:
            break
        count += 1
        start = at + 1
    return {'callsOrJumps': ['0x%X' % c for c in callers(image, target)], 'absolutePointers': count}


def lookup(rows: bytes, resource: int):
    at = resource % CAPACITY
    for _ in range(CAPACITY):
        key, record = struct.unpack_from('<QI', rows, at * ROW_STRIDE)
        if key == resource:
            return record
        if key == 0:
            return None
        at = (at + 1) % CAPACITY
    return None


def build_copy(framing: bytes, table: bytes, original: int) -> bytes:
    """The copy: framing, the 46 rows with the three weapons' rows, records 0..23 as the file's, records 24..26 = the
    Trident's record 18, then a trailer (magic, the original table, the component index, the record count)."""
    rows = bytearray(table[:RECORD_BASE])
    trident = table[RECORD_BASE + TRIDENT_RECORD * RECORD_STRIDE:RECORD_BASE + (TRIDENT_RECORD + 1) * RECORD_STRIDE]
    for _, resource, row, record in WEAPONS:
        if rows[row * ROW_STRIDE:(row + 1) * ROW_STRIDE] != bytes(16):
            raise ValueError('row %d is not empty' % row)
        struct.pack_into('<QII', rows, row * ROW_STRIDE, resource, record, 0)
    records = table[RECORD_BASE:RECORD_BASE + FILE_RECORDS * RECORD_STRIDE] + trident * len(WEAPONS)
    trailer = TRAILER_MAGIC + struct.pack('<QII', original, INDEX, FILE_RECORDS + len(WEAPONS))
    return framing + bytes(rows) + records + trailer


def observe(name: str, file_body: bytes) -> dict:
    mem = base.Mem(name)
    try:
        manager = mem.ptr(mem.game + MANAGER_GLOBAL)
        slot_at = manager + SLOT
        table = mem.ptr(slot_at)
        region = mem.s.region(table)
        mregion = mem.s.region(slot_at)
        size = RECORD_BASE + FILE_RECORDS * RECORD_STRIDE
        framing = mem.read(table - FRAMING, FRAMING)
        body = mem.read(table, size)
        esh = mem.ptr(manager + ESH_SLOT)
        settings = mem.read(esh, 32 * 4096)
        resources = []
        seen = set()
        for n in range(4096):
            key = struct.unpack_from('<Q', settings, n * 32)[0]
            if key and key not in seen:
                seen.add(key)
                resources.append(key)
        for n in range(CAPACITY):
            key = struct.unpack_from('<Q', body, n * ROW_STRIDE)[0]
            if key and key not in seen:
                seen.add(key)
                resources.append(key)
        copy = build_copy(framing, body, table)
        ctable = copy[FRAMING:]
        changed, differing = [], []
        own = {resource: record for _, resource, _, record in WEAPONS}
        for resource in resources:
            before, after = lookup(body, resource), lookup(ctable, resource)
            if before != after:
                changed.append('0x%016X=%s' % (resource, after))
            if after is not None and resource not in own:
                a = ctable[RECORD_BASE + after * RECORD_STRIDE:RECORD_BASE + (after + 1) * RECORD_STRIDE]
                b = body[RECORD_BASE + before * RECORD_STRIDE:RECORD_BASE + (before + 1) * RECORD_STRIDE]
                if a != b:
                    differing.append('0x%016X' % resource)
        trident = body[RECORD_BASE + TRIDENT_RECORD * RECORD_STRIDE:RECORD_BASE + (TRIDENT_RECORD + 1) * RECORD_STRIDE]
        own_records = {k: ctable[RECORD_BASE + r * RECORD_STRIDE:RECORD_BASE + (r + 1) * RECORD_STRIDE] == trident
                       for k, _, _, r in WEAPONS}
        default_same = (ctable[0xDA8:0xDA8 + RECORD_STRIDE] == body[0xDA8:0xDA8 + RECORD_STRIDE])
        return {'snapshot': name, 'slotAligned8': slot_at % 8 == 0,
                'slotIsTheEntityAllocationsOwnTable': region is not None and table - FRAMING >= region['base'],
                'tableProtect': '0x%X' % region['protect'], 'managerProtect': '0x%X' % mregion['protect'],
                'tableByteIdenticalToFile': body == file_body[:size] and len(file_body) == size,
                'framingIndex': struct.unpack_from('<I', framing, 0)[0],
                'tablePageOffset': (table - FRAMING) % 4096,
                'resourcesChecked': len(resources), 'answersChanged': sorted(changed),
                'otherRecordsByteIdentical': not differing, 'ownRecordsAreTheTridentRecord': own_records,
                'defaultRecordUnchanged': default_same, 'copySize': len(copy),
                'rowsInCopy': {k: ctable[row * 16:row * 16 + 16].hex() for k, _, row, _ in WEAPONS}}
    finally:
        mem.close()


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = prove_all(image)
    pins = [p for rows in proofs.values() for p in rows]
    census = slot_census(image)
    reload = {'0xFDB860': references(image, 0xFDB860), '0xFDB7C0': references(image, 0xFDB7C0),
              '0xFDB440': references(image, 0xFDB440), '0x50ECA0': references(image, 0x50ECA0)}
    if reload['0xFDB860']['callsOrJumps'] or reload['0xFDB860']['absolutePointers']:
        raise ValueError('the entity file reload has a caller: %r' % reload['0xFDB860'])
    if reload['0xFDB440']['callsOrJumps'] != ['0xAE0D8B', '0xFDB880']:
        raise ValueError('the entity file loader has another caller: %r' % reload['0xFDB440'])
    if reload['0x50ECA0']['callsOrJumps'] or reload['0x50ECA0']['absolutePointers']:
        raise ValueError('the default-record getter has a caller')
    # The unload stores no slot: no instruction of 0xFDB7C0..0xFDB851 writes into the slot array.
    unload_writes = []
    for rva, size, mnemonic, operands in image.md.disasm_lite(data[0xFDB7C0:0xFDB851], 0xFDB7C0):
        if operands.startswith('qword ptr [') and mnemonic.startswith('mov') and '0xf12' in operands.split(',')[0]:
            unload_writes.append('0x%X %s %s' % (rva, mnemonic, operands))
    if unload_writes:
        raise ValueError('the unload writes a slot: %r' % unload_writes)
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    multi = json.loads(MULTI.read_text(encoding='utf-8'))
    sites = multi['sharedRecord']['callSites']
    kept = [s for s in sites if 'stack frame' in s['use']]
    file_body = scan_tables.pinned().component('BeamWeaponComponentData').body
    observations = [observe(name, file_body) for name in SNAPSHOTS]
    expected = sorted('0x%016X=%d' % (resource, record) for _, resource, _, record in WEAPONS)
    for o in observations:
        if not (o['slotAligned8'] and o['tableByteIdenticalToFile'] and o['answersChanged'] == expected
                and o['otherRecordsByteIdentical'] and all(o['ownRecordsAreTheTridentRecord'].values())
                and o['defaultRecordUnchanged'] and o['framingIndex'] == INDEX and o['tableProtect'] == '0x2'
                and o['managerProtect'] == '0x4' and o['copySize'] <= 4096):
            raise ValueError('snapshot %s: %r' % (o['snapshot'], o))
    copy_size = observations[0]['copySize']
    report = {
        'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'gameDllSha256': base.PROFILE_DLL_SHA,
        'question': __doc__.split('Questions answered here')[0].strip(),
        'follows': ['multi-beam-swap-F5FEE03DCFDB.md section 6', 'entity-component-table-pointers.md'],
        'proofs': proofs, 'slotCensus': census, 'entryPoints': reload,
        'unloadStoresNoSlot': True,
        'lookup': {'capacity': CAPACITY, 'rowStride': ROW_STRIDE, 'recordBase': RECORD_BASE,
                   'recordStride': RECORD_STRIDE, 'capacityFrom': 'code (imul 0x2E, cmp 0x2D / 0x2E)',
                   'recordBaseFrom': 'the slot pointer (r10 = [manager + 0xF12CE8]); the DL header is never read',
                   'recordIndexBounded': False,
                   'defaultRecord': {'record': DEFAULT_RECORD, 'offset': 0xDA8, 'sites': ['0x50ECAE', '0x841BD0'],
                                     'from': 'the slot pointer + 0xDA8'}},
        'caching': {
            'tablePointer': 'NONE: slot 270 is read at exactly three instructions (0x50E88F, 0x50ECA7, 0x841BC9), each '
                            're-reads it per call into a register; the slot array base is used at six more sites, '
                            'none for slot 270 (slots 0, 29, 271) and the loader store. Nothing stores the slot\'s '
                            'value anywhere.',
            'recordPointers': 'Per call only: every one of the %d call sites of the lookup / resolver / copy creator '
                              '(research multi-beam-swap callSites) reads the record, copies its bytes or keeps it in '
                              'its own stack frame for the call (%s). BeamWeapon instances (0x70 bytes) and private '
                              'copies (beam manager +0xB0) hold values, never a table or record pointer.'
                              % (len(sites), ', '.join(s['site'] + ' ' + s['use'] for s in kept)),
            'switchConsequence': 'A lookup that already read the old pointer finishes on the old table (never freed: '
                                 'the file\'s table, or a Runtime copy that is never freed); the next call reads the '
                                 'new one. So the switch is safe at any time, and needs no ordering against a cache.'},
        'copy': {'framing': FRAMING, 'rows': CAPACITY, 'records': FILE_RECORDS + len(WEAPONS), 'size': copy_size,
                 'trailer': {'magic': TRAILER_MAGIC.decode(), 'size': TRAILER_SIZE,
                             'fields': 'magic 16, original table u64, component index u32, record count u32'},
                 'ownRecords': {k: record for k, _, _, record in WEAPONS},
                 'rows': {k: row for k, _, row, _ in WEAPONS}},
        'pinnedBytesMismatchPerSnapshot': relocation, 'observations': observations,
        'verdict': 'SAFE (CONFIRMED in .text; the protected sections cannot be scanned): the game reads the BeamWeapon '
                   'table only through slot 270, re-read per call; the record base is the slot pointer and the record '
                   'index is not bounded, so records 24, 25, 26 appended to a Runtime-owned copy are reached; the '
                   'default record stays +0xDA8 (record 23, the file\'s bytes in the copy); only the loader (once at '
                   'startup) stores a slot and the reload has no caller. One aligned 8-byte store makes the copy '
                   'live; nothing caches the old pointer.',
        'unproven': [
            'Live: the switch and the per-weapon records in a running game (offline only).',
            'Concurrency: the slot store is one aligned 8-byte write; a game thread that read the old pointer finishes '
            'on the old (never freed) table. That an aligned 8-byte WriteProcessMemory to the own process is a single '
            'store is a property of the copy routine, not of the game (STRONG, not proven).',
            'The protected sections (.vm_sec, .winlice) cannot be scanned for slot reads.'],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'pins': len(pins), 'slot270': census['slot270'], 'base': census['slotArrayBase']['sites'],
                      'otherWindowValues': census['otherWindowValues'], 'entryPoints': reload,
                      'copySize': copy_size, 'snapshots': len(observations),
                      'answersChanged': observations[0]['answersChanged'],
                      'resources': observations[0]['resourcesChecked']}, indent=1))


if __name__ == '__main__':
    main()
