"""Can the Runtime create a genuinely new selectable stratagem? (docs/custom-stratagems.md, "A genuinely new selectable
stratagem: research"). Read-only, offline: the game.dll image and the seven retained snapshots of build F5FEE03DCFDB
(the installed build). Nothing is written.

Three concepts are kept apart:
  A. a new numeric StratagemInfo identity (a new type);
  B. a new selectable ship-loadout entry;
  C. custom presentation, calldown and payload on an existing owned carrier (live-proven).

Proves:

1. The registry. game.dll +0x37CB600 is a static array of exactly 150 row pointers indexed by type. Its only writer
   (0x11F2080) loads the game's generated_stratagem_settings.dl_bin, zeroes the array (0x4B0 bytes = 150 x 8) and stores
   table[row.type] = row for every row of that resource, with no bounds check. No other code stores into it; no other
   registry, registration call or stable-id index exists (every row lookup indexes this array by type; the only
   stable-id lookups are linear scans of types 1..149). In every snapshot table[0] is empty (type 0 = none, the static
   default row 0x37CB470) and types 1..149 are all filled, each row carrying its own type, all inside the settings
   buffer: there is no free type.
2. The readers trust the type. 286 instructions in 178 functions index the array; 12 have a 0x95/0x96 compare earlier
   in their function. The peer sync of loadouts (0x11E82D0, rpc_sync_stratagems / rpc_sync_player_history) writes each
   received raw u32 type into the player record and indexes table[type] unchecked, then reads row +0x94. The mission
   report indexes the static enum-name table (0x21D4AA0) by type: 150 names followed by "Count", the StratagemType
   enum compiled with Count = 150.
3. The picker. On every slot click the grid (0x18D8710) loops types 1..149, keeps table[type] for each type the
   availability check (0x136FC20: enabled, selectable, an owned account-catalogue record whose +8 is the row's stable
   id) accepts, into a stack-local array, then joins each row to its catalogue record. That loop is the grid's only
   source of entries: no UI model, mod resource or local list feeds it.
4. Persistence. Leaving the screen saves {stable id, uses} pairs (row +4) into the local save store; the next session
   restores each pair by scanning types 1..149 for that stable id, with no ownership or availability check; a stable id
   no row carries is dropped silently. At most 4 slots by row +0xBC.
5. The only alternate resolution: the mission menu takes type 128's (UploadDiscovery) name from a mission objective
   (0x6F24D0) before its row. It is keyed by that vanilla type, not an extension mechanism.

Output: research/stratagem-identity-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import sys

import capstone
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS, LOADOUT, TABLE, BUFFER_RVA, ENTRIES, STRIDE  # noqa: E402

OUTPUT = ROOT / 'research/stratagem-identity-F5FEE03DCFDB.json'
DEFAULT_ROW, ENUM_NAMES = 0x37CB470, 0x21D4AA0

GAME = {
    'registryFill': [
        (0x11F20AA, 'lea rcx, [rip + {rip}]', 0x2265D40, '"generated_stratagem_settings.dl_bin": the game\'s settings resource'),
        (0x11F20DB, 'lea r13, [rip + {rip}]', TABLE, 'the registry: the static array of row pointers'),
        (0x11F20E7, 'mov qword ptr [rip + {rip}], rbx', BUFFER_RVA, 'the settings buffer'),
        (0x11F20FE, 'mov r8d, 0x4b0', None, 'zeroed first: 0x4B0 bytes = 150 pointers'),
        (0x11F2104, 'mov rcx, r13', None, '... the registry'),
        (0x11F2216, 'imul rdx, rax, 0x190', None, 'each row of the resource (400 bytes) ...'),
        (0x11F2223, 'mov eax, dword ptr [rdx]', None, '... its type (row +0) ...'),
        (0x11F2225, 'mov qword ptr [r13 + rax*8], rdx', None, '... is its index: table[type] = row, no bounds check'),
    ],
    'picker': [
        (0x18D8AA1, 'mov ebx, 1', None, 'the grid: types from 1 ...'),
        (0x18D8AA9, 'mov edi, 0x96', None, '... to 149'),
        (0x18D8AB5, 'call 0x136fc20', None, 'each through the availability check'),
        (0x18D8AC0, 'mov rax, qword ptr [r15 + rax*8 + 0x37cb600]', None, 'an accepted type\'s row ...'),
        (0x18D8AC8, 'mov qword ptr [rsp + rbp*8 + 0xc10], rax', None, '... into a stack-local candidate array'),
        (0x18D8B2A, 'mov r10d, dword ptr [rax + 4]', None, 'each candidate\'s stable id ...'),
        (0x18D8B6E, 'cmp dword ptr [r11 + rcx*8 + 8], r10d', None, '... joined to its account-catalogue record'),
    ],
    'restore': [
        (0x175218F, 'test ecx, ecx', None, 'a saved pair with no uses is skipped'),
        (0x17521A3, 'cmp dword ptr [rcx + 4], eax', None, 'stable id -> type: a scan of the rows ...'),
        (0x17521AE, 'cmp edx, 0x96', None, '... of types 1..149'),
        (0x17521B6, 'jmp 0x1752200', None, 'no row carries it: the pair is dropped'),
        (0x17521C5, 'mov eax, dword ptr [rax + 0xbc]', None, 'row +0xBC: slot weight ...'),
        (0x17521CD, 'cmp eax, 4', None, '... at most 4'),
        (0x17521DB, 'mov dword ptr [rbx + rcx*8 + 0x188], edx', None, 'the slot: the type (no ownership check)'),
    ],
    'peerSync': [
        (0x11E8360, 'mov r14d, dword ptr [r12 + rdi*4 + 4]', None, 'a peer\'s loadout: the received raw type ...'),
        (0x11E8365, 'mov dword ptr [rcx + 0x188], r14d', None, '... written into its player record slot'),
        (0x11E83A2, 'lea rax, [rip + {rip}]', DEFAULT_ROW, 'type 0: the static default row'),
        (0x11E83AB, 'mov rax, qword ptr [rdx + rax*8]', None, 'any other type indexes the registry unchecked ...'),
        (0x11E83BB, 'mov eax, dword ptr [rax + 0x94]', None, '... and the row is read'),
    ],
    'alternateResolution': [
        (0x66D4CE, 'mov r15d, dword ptr [r8 + rcx*8 + 0x188]', None, 'mission menu: the type of a slot ...'),
        (0x66D4D6, 'cmp r15d, 0x80', None, '... type 128 (UploadDiscovery) only ...'),
        (0x66D4F3, 'call 0x6f24d0', None, '... takes its name from a mission objective first; still the vanilla type'),
        (0x66D54C, 'mov rax, qword ptr [r13 + r15*8 + 0x37cb600]', None, 'every other type: the registry row'),
    ],
    'report': [
        (0x135D0CB, 'mov rax, qword ptr [r9 + rax*8 + 0x37cb600]', None, 'mission report: each slot\'s row ...'),
        (0x135D0D3, 'test byte ptr [rax + 0x80], 2', None, '... if selectable ...'),
        (0x135D0E4, 'mov rax, qword ptr [r9 + rax*8 + 0x21d4aa0]', None, '... by its enum name (indexed by type)'),
    ],
}


def table_references(game: base.Image):
    """Every instruction addressing the registry: displacement 0x37CB600 (image-base indexed) or rip-relative."""
    data = game.data
    lite = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    found = {}
    needle = struct.pack('<I', TABLE)
    at = base.TEXT[0]
    while True:
        at = data.find(needle, at, base.TEXT[1])
        if at < 0:
            break
        for back in range(10, 0, -1):
            start = at - back
            insn = next(lite.disasm_lite(data[start:start + 16], start, 1), None)
            if insn and start + insn[1] >= at + 4 and '0x37cb600' in insn[3]:
                found[start] = insn[2] + ' ' + insn[3]
                break
        at += 1
    size = base.TEXT[1] - base.TEXT[0]
    for phase in range(4):
        count = (size - phase) // 4
        view = numpy.frombuffer(data, dtype='<i4', offset=base.TEXT[0] + phase, count=count).astype(numpy.int64)
        positions = numpy.arange(count, dtype=numpy.int64) * 4 + base.TEXT[0] + phase
        for tail in (0, 1, 4):
            for hit in numpy.nonzero(positions + 4 + view == TABLE - tail)[0]:
                disp = int(positions[hit])
                for back in range(10, 0, -1):
                    start = disp - back
                    insn = next(lite.disasm_lite(data[start:start + 16], start, 1), None)
                    if insn and insn[1] == back + 4 + tail and 'rip' in insn[3]:
                        found[start] = insn[2] + ' ' + insn[3] + ' [rip]'
                        break
    return found


def functions(game: base.Image):
    pe = struct.unpack_from('<I', game.data, 60)[0]
    exc_rva, exc_size = struct.unpack_from('<II', game.data, pe + 24 + 112 + 3 * 8)
    table = numpy.frombuffer(game.data[exc_rva:exc_rva + exc_size // 12 * 12], dtype='<u4').reshape(-1, 3)
    table = table[table[:, 0] < table[:, 1]]

    def of(rva):
        i = int(numpy.searchsorted(table[:, 0], rva, side='right')) - 1
        if i < 0 or not table[i, 0] <= rva < table[i, 1]:
            return None
        return int(table[i, 0]), int(table[i, 1])
    return of


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    availability = [game.prove(*row) for row in LOADOUT['picker'] if row[0] >= 0x136FC00]
    pins['availability'] = availability
    if game.cstr(0x2265D40) != 'generated_stratagem_settings.dl_bin':
        raise ValueError('the settings resource name moved')
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    # Every reference to the registry; the only store is the fill.
    refs = table_references(game)
    of = functions(game)
    by_function = {}
    for at in refs:
        span = of(at)
        by_function.setdefault(span, []).append(at)
    lite = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    stores, bounded = [], 0
    saved = {'rbx', 'rsi', 'rdi', 'rbp', 'r12', 'r13', 'r14', 'r15'}
    for span, items in by_function.items():
        listing = list(lite.disasm_lite(game.data[span[0]:span[1]], span[0])) if span else []
        compares = [a for a, _, m, o in listing if m == 'cmp' and re.search(r', (0x96|0x95)$', o)]
        for at in items:
            bounded += any(c < at for c in compares)
            text = refs[at]
            if re.match(r'mov (qword|dword) ptr \[[^\]]*0x37cb600\], ', text):
                stores.append(at)
            m = re.match(r'lea (\w+), ', text)
            if m:
                reg = m.group(1)
                for a, _, mn, op in list(lite.disasm_lite(game.data[at:at + 600], at))[1:120]:
                    t = mn + ' ' + op
                    if mn.startswith('mov') and re.search(r'ptr \[%s( \+ [^\]]*)?\], ' % reg, t):
                        stores.append(a)
                        break
                    if re.match(r'(mov|lea|xor|pop) %s,' % reg, t) or mn == 'ret' or (mn == 'call' and reg not in saved):
                        break
    if stores != [0x11F2225]:
        raise ValueError('another store into the registry: %s' % [hex(a) for a in stores])
    # Snapshot occupancy and the enum-name table.
    snapshots = []
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        entries = [mem.ptr(mem.game + TABLE + 8 * i) for i in range(ENTRIES)]
        buffer = mem.ptr(mem.game + BUFFER_RVA)
        region = mem.s.region(buffer)
        names = []
        for i in range(ENTRIES + 2):
            pointer = mem.u64(mem.game + ENUM_NAMES + 8 * i) or 0
            text = mem.read(pointer, 64) if pointer else None
            names.append(text.split(b'\0')[0].decode('latin-1') if text else None)
        snapshots.append({'snapshot': name, 'empty': [i for i, p in enumerate(entries) if not p],
            'filled': sum(1 for p in entries if p), 'typeIsIndex': sum(1 for i, p in enumerate(entries)
                if p and mem.u32(p) == i), 'rowsInSettingsBuffer': sum(1 for p in entries if p
                and region['base'] <= p < region['base'] + region['size']),
            'enumNames': {'first': names[1], 'last': names[ENTRIES - 1],
                'validNames': sum(1 for n in names[:ENTRIES] if n and re.fullmatch(r'[A-Za-z0-9_]+', n)),
                'after': [n if n and re.fullmatch(r'[A-Za-z0-9_]+', n) else None for n in names[ENTRIES:]]}})
        mem.close()
    if any(s['enumNames']['validNames'] != ENTRIES or s['enumNames']['after'][0] != 'Count' for s in snapshots):
        raise ValueError('the StratagemType enum is not 150 names followed by Count')
    if any(s['empty'] != [0] or s['filled'] != ENTRIES - 1 or s['typeIsIndex'] != ENTRIES - 1
            or s['rowsInSettingsBuffer'] != ENTRIES - 1 for s in snapshots):
        raise ValueError('a snapshot has a free or foreign registry entry: %r' % snapshots)

    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0,
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation,
        'registry': {'table': '0x%X' % TABLE, 'entries': ENTRIES, 'rowSize': STRIDE, 'defaultRow': '0x%X' % DEFAULT_ROW,
            'source': 'generated_stratagem_settings.dl_bin', 'writer': '0x11F2080', 'stores': ['0x%X' % a for a in stores],
            'references': len(refs), 'referencingFunctions': len(by_function), 'referencesAfterABoundsCompare': bounded,
            'stableIdLookups': 'linear scans of types 1..149 (the restore, the availability check joins by catalogue)'},
        'snapshots': snapshots,
        'determinations': {
            'A_newNumericIdentity': ('Not possible safely. The registry is a static 150-entry array filled only from the '
                'game\'s settings resource by row type; types 1..149 are all taken and type 0 means none. A type of 150 '
                'or more would sit outside the array, the StratagemType enum (Count = 150) and the picker loop, and every machine that '
                'received it in a loadout sync would index the array unchecked.'),
            'B_newSelectableEntry': ('Not possible without a type. The grid\'s only entries are types 1..149 accepted '
                'by the availability check, which needs an owned account-catalogue record carrying the row\'s stable '
                'id. No UI model, mod resource, local list or Runtime-owned row feeds it. A second entry for an '
                'existing type is not built, and would be indistinguishable downstream anyway: the loadout, the save, '
                'the mission record and the network all carry the type or its stable id.'),
            'C_carrier': ('Live-proven: an owned, selectable vanilla carrier with Runtime presentation, calldown and '
                '(next) payload, saved, synced and called as itself.')},
        'conclusion': ('True new selectable StratagemInfo identities are not supported safely by the current game '
            'architecture. The supported custom-stratagem model is the owned vanilla carrier with Runtime-owned '
            'presentation, calldown and payload.')}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; references', len(refs), 'in', len(by_function), 'functions,', bounded,
        'after a bounds compare; stores', [hex(a) for a in stores], '; occupancy',
        [(s['filled'], s['empty']) for s in snapshots][:1], '; enum names', snapshots[0]['enumNames'])


if __name__ == '__main__':
    main()
