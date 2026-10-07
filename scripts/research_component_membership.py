"""Can the component MEMBERSHIP of an entity type be changed by a mission-scoped data edit (no code patch), e.g. remove
the AC-8's WeaponReload or give a weapon type the EAT-17's Backblast / WeaponMagazine, so that any weapon could become
an EAT clone? (research/docs/component-membership-F5FEE03DCFDB.md). Read-only, offline.

Proves on build F5FEE03DCFDB, from the pinned entity file, the game.dll image and the seven retained snapshots:

1. Where the structures live. The loader 0xFDB440 reads generated_entities.dl_bin into ONE allocation and loads it
   in place (DL pointer patching 0xAAEDD0): EntitySettingsHashmap -> entity manager +0xF12EA0,
   EntityNetworkDataArray -> +0xF12EA8, then every component table -> +0xF12478 + 8 x componentIndex (the index
   comes from the file framing). In every snapshot that allocation is PAGE_READONLY, every slot points into it, the
   component tables are byte-identical to the file and the only differing qwords are the patched DL array pointers.
2. Membership at spawn = the EntitySettings u16 list. Spawn 0xFDC140 -> 0x581320 / 0x581780 look the resource up
   in the 4096-row EntitySettingsHashmap (open addressing, & 0xFFF, linear probe, key 0 = empty) and call one
   handler per listed component index from 9 handler tables at the component world (entity manager + 0x40)
   + 0xF0C110 + k x 0xA20. Destroy 0xFDC820, network create 0x581C40 / 0xFDBB40 (via EntityNetworkDataArray ->
   EntitySettings ROW INDEX) and 0x581E10 iterate the same CURRENT list.
3. Per-type lookups: every type lookup is an open-addressing hash over the table's own ComponentIndexData rows
   (home = resource mod capacity, the capacity a code immediate; linear probe; key 0 = empty and stop; no
   tombstone; NULL on a miss). 24,241 rows in 270 tables all sit on a valid probe path. 59 tables carry one extra
   unowned DEFAULT record that the delta-copy paths use when a type has no row.
4. Vanilla invariant: an entity has a row in table X  <=>  X is in its EntitySettings list (0 exceptions).
5. Consequences for WeaponReload (the AC-8 case): the auto-drop gate 0x753A10 tests the manager's INSTANCE hash
   (+0x20), filled by the create handler only when 113 is in the list; the resolver 0x4FD220 returns the copy, else
   the TYPE record (no instance test) and 17 of its 18 call sites dereference without a NULL test; destroy 0x778A00
   removes through 0x172F8A0, which returns 0 on a miss (indistinguishable from instance 0); the network handler
   0x778C70 indexes with -1 on a miss. WeaponRounds and WeaponAssistedReload never occur without WeaponReload.

Output: research/component-membership-F5FEE03DCFDB.json. Nothing is written to the game.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import re
import struct
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from capstone import x86  # noqa: E402

import research_event_state as base  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402
from reference_format import dl_hash  # noqa: E402
from scan import instances, tables, xref  # noqa: E402

OUTPUT = ROOT / 'research/component-membership-F5FEE03DCFDB.json'
BUILD = 'F5FEE03DCFDB'
MISSION = [s for s in SNAPSHOTS if 'mission' in s]

ENTITY_MANAGER = 0x346BF98      # [game.dll + this] = entity manager (settings root)
SLOT_BASE = 0xF12478            # manager + SLOT_BASE + 8 x component index = that component's loaded type table
ESH_SLOT, ENA_SLOT, DELTAS_SLOT = 0xF12EA0, 0xF12EA8, 0xF12E98
WORLD_OFFSET = 0x40             # component world = manager + 0x40 (0xFDC250 lea rcx, [rsi + 0x40])
HANDLER_TABLES = {              # component world + offset + 8 x component index (0xA20 = 324 entries per table)
    'p1_create_queue': 0xF0C110, 'p2_create_init': 0xF0CB30, 'p3_post_create': 0xF0D550, 'p4_destroy_a': 0xF0DF70,
    'p5_destroy_b': 0xF0E990, 'p6_network_a': 0xF0F3B0, 'p7_network_b': 0xF0FDD0, 'p8_net_detach_a': 0xF107F0,
    'p9_net_detach_b': 0xF11210, 'p0_unreferenced': 0xF0B6F0}
DESCRIPTORS, DESCRIPTOR_STRIDE, DESCRIPTOR_COUNT = 0xF32F18, 24, 0x800   # manager +: {u64 resource, u32 entity, ..}
INVALID_ENTITY = 0x348456C      # u32 invalid entity id (0xFDC1F6 free-descriptor test)
ESH_CAPACITY = 4096
INDEX = {'WeaponMagazine': 5, 'WeaponAssistedReload': 60, 'Backblast': 62, 'Wieldable': 111, 'WeaponReload': 113,
    'WeaponRounds': 117, 'WeaponData': 236, 'SeatCollection': 286}
MANAGER_GLOBALS = {0x3326A70: 'auto-drop gate 1 (prior research)', 0x3326D88: 'auto-drop gate 2 (prior research)'}
AC8 = 0xA8CFFB316F0B5C5F        # content/fac_helldivers/equipment/support_weapons/automatic_cannon/automatic_cannon
EAT17 = 0x80932FA0ED6901D3      # .../lat_oneshot/lat_oneshot
EAT700 = 0xB2B5E0D185605F9E     # .../expendable_napalm_launcher/expendable_napalm_launcher

# (rva, exact asm, role). Every pin is re-decoded from the image and its bytes compared in all seven snapshots.
PINS = {
    'loader 0xFDB440 (generated_entities.dl_bin, in-place load)': [
        (0xFDB46B, 'lea rcx, [rip + 0x1281e2e]', 'file name "generated_entities.dl_bin" (0x225D2A0)'),
        (0xFDB54E, 'call 0xaaedd0', 'DL in-place load of the first instance (pointer patching)'),
        (0xFDB55A, 'mov qword ptr [r13 + 0xf12ea0], rsi', 'EntitySettingsHashmap (first instance) -> manager +0xF12EA0'),
        (0xFDB5C3, 'mov qword ptr [r13 + 0xf12ea8], r14', 'EntityNetworkDataArray (second) -> manager +0xF12EA8'),
        (0xFDB5D0, 'mov r12d, dword ptr [rbx + r15]', 'component index read from the file framing'),
        (0xFDB636, 'mov qword ptr [r13 + r12*8 + 0xf12478], r14', 'slot[index] := the loaded table (in place)'),
        (0xFDB664, 'lea rcx, [rip + 0x1281c85]', 'file name "generated_entity_deltas.dl_bin" (0x225D2F0)'),
        (0xFDB731, 'mov qword ptr [r13 + 0xf12e98], rdi', 'entity deltas -> manager +0xF12E98'),
        (0xFDB866, 'cmp qword ptr [rcx + 0xf12ea0], 0', '0xFDB860: reload = unload 0xFDB7C0 + load (no callers)'),
        (0xFDB880, 'jmp 0xfdb440', '0xFDB860 reloads the whole entity file (edits would be lost)'),
    ],
    'spawn 0xFDC140 -> 0x581320 (create) / 0x581780 (post-create)': [
        (0xFDC1C3, 'mov qword ptr [r14], rdi', 'entity descriptor +0 := resource (manager +0xF32F18 + 24 x slot)'),
        (0xFDC1BB, 'mov dword ptr [r14 + 8], ebx', 'entity descriptor +8 := entity id'),
        (0xFDC250, 'lea rcx, [rsi + 0x40]', 'component world = manager + 0x40'),
        (0xFDC25A, 'call 0x581320', 'create pass'),
        (0xFDC2B1, 'call 0x581780', 'post-create pass'),
        (0x5817B3, 'mov r11, qword ptr [r9 + 0xf12ea0]', 'EntitySettingsHashmap lookup by resource'),
        (0x5817BD, 'and r9d, 0xfff', 'home row = resource & 0xFFF (4096 rows)'),
        (0x5817DD, 'test rcx, rcx', 'key 0 = empty row: stop (not found)'),
        (0x5817FF, 'cmp r10d, 0x1000', 'linear probe bounded by the capacity'),
        (0x58140E, 'mov rax, qword ptr [r12 + rcx*8 + 0xf0c110]', 'per listed index: create handler (table p1)'),
        (0x5814B6, 'call 0x5740b0', 'entity-delta dispatcher (private copies) between the passes'),
        (0x581509, 'mov rax, qword ptr [r12 + rcx*8 + 0xf0cb30]', 'per listed index: init handler (table p2)'),
        (0x5816AF, 'mov esi, dword ptr [rcx + 0x18]', 'EntitySettings +0x18 network type (-1 = not networked)'),
        (0x581A3B, 'mov rax, qword ptr [rdi + rcx*8 + 0xf0d550]', 'per listed index: post-create handler (p3)'),
    ],
    'destroy 0xFDC820 (iterates the CURRENT list)': [
        (0xFDC8D3, 'mov r11, qword ptr [rcx + 0xf12ea0]', 'EntitySettingsHashmap lookup at destroy time'),
        (0xFDC943, 'mov rdx, qword ptr [r13 + rax*8 + 0xf0dfb0]', 'per listed index: destroy handler (p4)'),
        (0xFDCC53, 'mov rdx, qword ptr [r13 + rax*8 + 0xf0e9d0]', 'per listed index: destroy handler (p5)'),
    ],
    'network: remote spawn and per-component network handlers': [
        (0xBA0442, 'mov rax, qword ptr [rbx + 0xf12ea8]', 'remote spawn: EntityNetworkDataArray'),
        (0xBA0449, 'mov edx, dword ptr [rax + rcx*8 + 4]', 'EntityNetworkData +4 = EntitySettings ROW INDEX'),
        (0xBA0555, 'call 0xfdc140', 'remote peer spawns with its OWN list'),
        (0x581D1D, 'mov rax, qword ptr [r8 + 0xf12ea8]', 'network create 0x581C40: network type -> row index'),
        (0x581D24, 'mov edx, dword ptr [rax + rcx*8 + 4]', 'EntitySettings row index'),
        (0x581D63, 'mov r9, qword ptr [r15 + rax*8 + 0xf0f3b0]', 'per listed index: network handler (p6)'),
        (0x581DC3, 'mov r9, qword ptr [r15 + rax*8 + 0xf0fdd0]', 'per listed index: network handler (p7)'),
        (0xFDBDD3, 'mov r9, qword ptr [r15 + rax*8 + 0xf0f3b0]', 'migration 0xFDBB40: the same per-index handlers'),
        (0x581F53, 'mov r8, qword ptr [r14 + rax*8 + 0xf11210]', '0x581E10: per listed index (p9)'),
        (0x581F83, 'mov r8, qword ptr [r14 + rax*8 + 0xf107f0]', '0x581E10: per listed index (p8)'),
    ],
    'type lookups (open addressing over the ComponentIndexData rows)': [
        (0x4FCE2F, 'mov r10, qword ptr [rax + 0xf12800]', 'WeaponReload lookup 0x4FCE20: slot 113'),
        (0x4FCE47, 'imul eax, edx, 0x1f2', 'home = resource mod 498 (the capacity is a code immediate)'),
        (0x4FCE6D, 'cmp rdx, rcx', 'row key == resource: hit'),
        (0x4FCE75, 'je 0x4fce96', 'row key 0: stop, NULL (no tombstone handling)'),
        (0x4FCE8D, 'cmp r9d, 0x1f2', 'probe bounded by the capacity'),
        (0x4FCE96, 'xor eax, eax', 'miss returns NULL'),
        (0x4FCE9E, 'mov ecx, dword ptr [rax + 8]', 'hit: record index = row +8'),
        (0x4FE44F, 'mov r10, qword ptr [rax + 0xf12860]', 'Spottable lookup 0x4FE440: slot 125'),
        (0x4FE467, 'imul eax, edx, 0x56a', 'home = resource mod 1386'),
        (0x514C1F, 'mov r10, qword ptr [rax + 0xf12e80]', 'ProjectileWeapon lookup 0x514C10: slot 321'),
        (0x514C37, 'imul eax, edx, 0x21e', 'home = resource mod 542 (the "542-row hash index")'),
        (0x514C91, 'imul rax, rcx, 0x268', 'record = table + 0x21E0 + 0x268 x index'),
    ],
    'WeaponReload consumers': [
        (0x52841F, 'mov rbx, qword ptr [rip + 0x2dfe64a]', 'create handler (p1) 0x528410: WeaponReload manager'),
        (0x5284A2, 'lea rcx, [rbx + 0x20]', '... inserts the entity into the INSTANCE hash +0x20'),
        (0x753B33, 'mov rcx, qword ptr [rip + 0x2bd2f36]', 'auto-drop 0x753A10 gate 1: WeaponReload manager'),
        (0x753B51, 'mov r11, qword ptr [rcx + 0x20]', '... tests the INSTANCE hash +0x20 (not the type row)'),
        (0x753BBF, 'jne 0x753d89', '... an instance exists: return, no auto drop'),
        (0x4FD242, 'mov r11, qword ptr [rip + 0x2e29827]', 'resolver 0x4FD220: WeaponReload manager'),
        (0x4FD274, 'mov rdi, qword ptr [r11 + 0x60]', '... private-copy map +0x60 (deltas), not the instance hash'),
        (0x4FD2DD, 'jmp 0x4fce20', '... else the TYPE record by resource (may be NULL)'),
        (0x5A9F10, 'call 0x4fd220', 'resolver consumer: result dereferenced without a NULL test'),
        (0xA7C35F, 'call 0x4fd220', 'team-reload consumer 0xA7BFE0: dereferenced without a NULL test'),
        (0x7794DC, 'call 0x4fce20', 'delta copy 0x779410: type lookup'),
        (0x7794ED, 'mov rax, qword ptr [r8 + 0xf12800]', '... miss: falls back to the table\'s DEFAULT record'),
        (0x7794F4, 'add rax, 0x6cf0', '... record 249 = the unowned last record'),
        (0x83E02A, 'call 0x4f7420', 'Backblast delta copy: type lookup'),
        (0x83E03B, 'mov rax, qword ptr [rcx + 0xf12668]', '... miss: Backblast DEFAULT record'),
        (0x83E042, 'add rax, 0x7e0', '... record 21 = the unowned last record'),
        (0x778A08, 'mov rbx, qword ptr [rip + 0x2bae061]', 'destroy handler (p5) 0x778A00: WeaponReload manager'),
        (0x778A15, 'lea rcx, [rbx + 0x20]', '... removes the entity from the instance hash'),
        (0x778A19, 'call 0x172f8a0', '... hash remove'),
        (0x172F8EB, 'xor eax, eax', 'hash remove returns 0 on a MISS (indistinguishable from instance 0)'),
        (0x778A27, 'cmp eax, r8d', '... then treats the returned 0 as the instance index'),
        (0x778C8B, 'mov rbp, qword ptr [rip + 0x2baddde]', 'network handler (p6) 0x778C70: WeaponReload manager'),
        (0x778CD2, 'mov ebx, 0xffffffff', '... instance not found: index -1'),
        (0x778D16, 'mov rax, qword ptr [rax + rdi*8]', '... indexes the instance array with -1 (out of bounds)'),
    ],
    'record iterators (records, not index rows)': [
        (0x9F1CDA, 'mov rdi, qword ptr [rax + 0xf12560]', '0x9F1CC0 iterates LoadoutEntry RECORDS'),
        (0x9F1D23, 'cmp r10d, 0xc1', '... 193 records (not the index rows)'),
    ],
}


# ------------------------------------------------------------------------------------------------ helpers
def hx(value: int) -> str:
    return '0x%X' % value


def names_of(t) -> dict[int, str]:
    t.entity_rows()
    return {i: (t.type_name(h) or hx(h)).replace('ComponentData', '') for i, h in t._index_type.items()}


def esh_body(t) -> bytes:
    position, size = t.frames[dl_hash('EntitySettingsHashmap')]
    return t.entities[position + tables.FRAME_SIZE:position + tables.FRAME_SIZE + size]


def esh_row(body: bytes, row: int) -> tuple[int, int, int, int]:
    resource, offset, count = struct.unpack_from('<QQQ', body, row * 32)
    network = struct.unpack_from('<I', body, row * 32 + 24)[0]
    return resource, offset, count, network


def probe_path(home: int, position: int, capacity: int) -> list[int]:
    path, p = [], home
    while True:
        path.append(p)
        if p == position:
            return path
        p = (p + 1) % capacity
        if len(path) > capacity:
            raise ValueError('probe path does not reach the row')


# ------------------------------------------------------------------------------------------------ code
def prove_pins(img) -> dict:
    out = {}
    for group, rows in PINS.items():
        out[group] = [img.pin(rva, role, asm) for rva, asm, role in rows]
    return out


def classify_slot_sites(img, t) -> dict:
    """Every code reference to a component's slot, by kind: hash lookup (capacity and capacity-1 immediates, modulo by
    mul or a power-of-two mask), direct record (the default/fallback record), other (record iterators etc.)."""
    idx_of = {h: i for i, h in t._index_type.items()}
    kinds = collections.Counter()
    others, directs = [], []
    for c in t.components():
        slot = SLOT_BASE + 8 * idx_of[c.type_hash]
        for ins in img.immediates(slot):
            if ins.address == 0xFDB636:
                continue
            seq = img.disasm(ins.address, ins.address + 0x180)[:70]
            imms, masked = set(), False
            for s in seq:
                for op in s.operands:
                    if op.type == x86.X86_OP_IMM:
                        imms.add(op.imm & 0xFFFFFFFF)
                if s.mnemonic == 'and' and len(s.operands) == 2 and s.operands[1].type == x86.X86_OP_IMM and \
                        s.operands[1].imm == c.capacity - 1:
                    masked = True
            modulo = any(s.mnemonic == 'mul' for s in seq) or masked
            records = [v for v in imms if c.records_offset <= v < c.records_offset + c.count * c.record_size
                and (v - c.records_offset) % c.record_size == 0]
            if c.capacity in imms and (c.capacity - 1 in imms or c.capacity == 1):
                kind = 'hash_lookup' if modulo else 'hash_lookup_small_capacity'
            elif records:
                kind = 'direct_record'
                directs.append({'component': c.name, 'site': hx(ins.address),
                    'record': (records[0] - c.records_offset) // c.record_size, 'records': c.count})
            else:
                kind = 'other'
                others.append({'component': c.name, 'site': hx(ins.address), 'function': hx(img.root(ins.address) or 0)})
            kinds[kind] += 1
    default_direct = [d for d in directs if d['record'] == d['records'] - 1]
    return {'kinds': dict(kinds), 'directRecordSites': len(directs), 'directRecordIsLastRecord': len(default_direct),
        'directRecordNotLast': [d for d in directs if d['record'] != d['records'] - 1],
        'others': others,
        'note': 'hash_lookup sites carry the capacity and capacity-1 as immediates with a modulo (mul by the '
            'reciprocal, or & (capacity-1) for powers of two); "other" sites were reviewed: record iterators '
            '(LoadoutEntry 0x9F1CC0, EncyclopediaEntry 0x1789B60 / 0x1789FA0), the generic Visibility path '
            '0x569490 and Bombardment 0x13462C0. No site iterates the index rows.'}


def esh_readers(img) -> list[dict]:
    out = []
    for f in sorted({img.root(i.address) for i in img.immediates(ESH_SLOT)}):
        text = [i.mnemonic + ' ' + i.op_str for i in img.function_insns(f)]
        handlers = sorted({m for x in text for m in re.findall(r'\+ (0xf0[0-9a-f]{4}|0xf1[01][0-9a-f]{3})\]', x)})
        out.append({'function': hx(f),
            'byResource': any(re.search(r'and r\w+, 0xfff$', x) for x in text),
            'byNetworkRowIndex': any('0xf12ea8' in x for x in text),
            'iteratesList': any('movzx' in x and 'word ptr' in x for x in text),
            'handlerTables': handlers})
    return out


def resolver_null_census(img) -> dict:
    out = {}
    for target, label in ((0x4FD220, 'WeaponReload resolver 0x4FD220 (copy, else type)'),
                          (0x4FCE20, 'WeaponReload type lookup 0x4FCE20')):
        sites = []
        for site in img.calls_to(target):
            seq = img.disasm(site, site + 0x30)[:5]
            checked = any(s.mnemonic == 'test' and s.op_str in ('rax, rax', 'rsi, rsi') for s in seq[1:4])
            sites.append({'site': hx(site), 'function': hx(img.root(site) or 0), 'nullTested': checked,
                'next': '; '.join(s.mnemonic + ' ' + s.op_str for s in seq[1:3])})
        out[label] = {'sites': sites, 'nullTested': sum(s['nullTested'] for s in sites), 'total': len(sites)}
    return out


# ------------------------------------------------------------------------------------------------ data
def hash_structure(t) -> dict:
    total = bad = 0
    maxdisp = 0
    default_tables, per_table = [], {}
    for c in t.components():
        occupied = {row: resource for row, resource, _ in c.rows()}
        for row, resource, _ in c.rows():
            total += 1
            try:
                path = probe_path(resource % c.capacity, row, c.capacity)
            except ValueError:
                bad += 1
                continue
            if any(p not in occupied for p in path):
                bad += 1
            maxdisp = max(maxdisp, len(path) - 1)
        owned = {record for _, _, record in c.rows()}
        unowned = [k for k in range(c.count) if k not in owned]
        if unowned == [c.count - 1]:
            default_tables.append(c.name)
        per_table[c.name] = {'capacity': c.capacity, 'rows': len(c.rows()), 'records': c.count,
            'free': c.capacity - len(c.rows())}
    shared = sum(1 for c in t.components() for v in c.owner_map().values() if len(v) > 1)
    return {'tables': len(per_table), 'rows': total, 'rowsOffProbePath': bad, 'maxDisplacement': maxdisp,
        'emptyKey': 0, 'tombstoneSupport': False,
        'capacityIsTwiceRows': sum(1 for v in per_table.values() if v['capacity'] == 2 * v['rows']),
        'tablesWithDefaultRecord': len(default_tables), 'defaultRecordExamples': default_tables[:12],
        'sharedRecordsVanilla': shared,
        'focus': {k: per_table[k + 'ComponentData'] for k in ('WeaponReload', 'WeaponRounds', 'WeaponAssistedReload',
            'Backblast', 'WeaponMagazine', 'Spottable', 'ProjectileWeapon')}}


def membership_invariant(t) -> dict:
    rows = t.entity_rows()
    idx_of = {h: i for i, h in t._index_type.items()}
    row_not_list = list_not_row = 0
    for c in t.components():
        i = idx_of[c.type_hash]
        owners = {resource for _, resource, _ in c.rows()}
        row_not_list += sum(1 for r in owners if r not in rows or i not in rows[r])
        list_not_row += sum(1 for r, lst in rows.items() if i in lst and r not in owners)
    tableless = sorted({i for lst in rows.values() for i in lst} - set(t._index_type))
    return {'rowWithoutListEntry': row_not_list, 'listEntryWithoutRow': list_not_row,
        'tablelessIndicesInLists': tableless}


def entity_settings(t) -> dict:
    body = esh_body(t)
    spans = []
    for row in range(ESH_CAPACITY):
        resource, offset, count, _ = esh_row(body, row)
        if resource:
            spans.append((offset, count))
    spans.sort()
    gaps = overlaps = 0
    end = None
    for offset, count in spans:
        if end is not None:
            overlaps += offset < end
            gaps += max(0, offset - end)
        end = max(end or 0, offset + 2 * count)
    rows = t.entity_rows()
    on_probe = all(probe_path(r & 0xFFF, row, ESH_CAPACITY) and
        all(esh_row(body, p)[0] for p in probe_path(r & 0xFFF, row, ESH_CAPACITY))
        for row in range(ESH_CAPACITY) for r in [esh_row(body, row)[0]] if r)
    position, size = t.frames[dl_hash('EntityNetworkDataArray')]
    ena = t.entities[position + tables.FRAME_SIZE:position + tables.FRAME_SIZE + size]
    pairs = [struct.unpack_from('<II', ena, 8 * i) for i in range(len(ena) // 8)]
    matched = sum(1 for key, row in pairs if row < ESH_CAPACITY and esh_row(body, row)[3] == key)
    networked = sum(1 for row in range(ESH_CAPACITY) if esh_row(body, row)[0] and esh_row(body, row)[3] != 0xFFFFFFFF)
    return {'capacity': ESH_CAPACITY, 'rows': len(spans), 'rowLayout': '{u64 resource, DL array<u16> (pointer, u32 '
        'count after load), u32 network type}', 'rowsOnProbePath': on_probe,
        'listStorage': {'firstOffset': spans[0][0], 'end': end, 'bodySize': len(body), 'gapBytes': gaps,
            'overlaps': overlaps, 'sharedLists': len(spans) - len({o for o, _ in spans})},
        'listsSorted': all(v == sorted(v) for v in rows.values()),
        'listsUnique': all(len(set(v)) == len(v) for v in rows.values()),
        'networkData': {'entries': len(pairs), 'sortedByNetworkType': all(a[0] <= b[0] for a, b in zip(pairs, pairs[1:])),
            'entryPointsToRowWithSameType': matched, 'networkedRows': networked}}


def cooccurrence(t) -> dict:
    rows = t.entity_rows()
    def count(need, lack=()):
        return sum(1 for lst in rows.values() if all(i in lst for i in need) and not any(i in lst for i in lack))
    i = INDEX
    return {
        'WeaponReload': count([i['WeaponReload']]),
        'WeaponRounds': count([i['WeaponRounds']]),
        'WeaponRounds without WeaponReload': count([i['WeaponRounds']], [i['WeaponReload']]),
        'WeaponAssistedReload': count([i['WeaponAssistedReload']]),
        'WeaponAssistedReload without WeaponReload': count([i['WeaponAssistedReload']], [i['WeaponReload']]),
        'WeaponMagazine and WeaponRounds': count([i['WeaponMagazine'], i['WeaponRounds']]),
        'Backblast and WeaponRounds': count([i['Backblast'], i['WeaponRounds']]),
        'Backblast and WeaponReload': count([i['Backblast'], i['WeaponReload']]),
        'WeaponReload without WeaponMagazine': count([i['WeaponReload']], [i['WeaponMagazine']]),
    }


def ac8_case(t, names) -> dict:
    rows = t.entity_rows()
    body = esh_body(t)
    ac8, eat = rows[AC8], rows[EAT17]
    esh_index = next(r for r in range(ESH_CAPACITY) if esh_row(body, r)[0] == AC8)
    _, offset, count, network = esh_row(body, esh_index)
    removal = {}
    for name in ('WeaponReload', 'WeaponRounds', 'WeaponAssistedReload'):
        c = t.component(name + 'ComponentData')
        occupied = {row: resource for row, resource, _ in c.rows()}
        position = next(row for row, resource, _ in c.rows() if resource == AC8)
        home = AC8 % c.capacity
        dependents = []
        for row, resource, _ in c.rows():
            if resource == AC8:
                continue
            path = probe_path(resource % c.capacity, row, c.capacity)
            if position in path[:-1]:
                dependents.append(t.label(resource))
        # backward-shift deletion (linear probing): entries moved to close the hole
        moved, hole, p = [], position, (position + 1) % c.capacity
        work = dict(occupied)
        del work[position]
        while p in work:
            h = work[p] % c.capacity
            if (p > hole and (h <= hole or h > p)) or (p < hole and h <= hole and h > p):
                work[hole] = work.pop(p)
                moved.append(t.label(work[hole]))
                hole = p
            p = (p + 1) % c.capacity
        removal[name] = {'row': position, 'home': home, 'displacement': len(probe_path(home, position, c.capacity)) - 1,
            'record': c.record_of(AC8), 'recordOwners': len(c.owners(c.record_of(AC8))),
            'keysWhoseProbeCrossesTheRow': dependents,
            'zeroingBreaksLookups': bool(dependents), 'backwardShiftMoves': moved}
    addition = {}
    for name in ('Backblast', 'WeaponMagazine'):
        c = t.component(name + 'ComponentData')
        occupied = {row for row, _, _ in c.rows()}
        home, p = AC8 % c.capacity, AC8 % c.capacity
        while p in occupied:
            p = (p + 1) % c.capacity
        donor = c.record_of(EAT17)
        addition[name] = {'home': home, 'insertRow': p, 'displacement': (p - home) % c.capacity,
            'freeRows': c.capacity - len(c.rows()), 'eat17Record': donor,
            'eat17RecordOwners': [t.label(o) for o in c.owners(donor)]}
    return {
        'resource': hx(AC8), 'path': t.name(AC8),
        'entitySettings': {'row': esh_index, 'home': AC8 & 0xFFF, 'listOffsetInFile': offset, 'count': count,
            'networkType': hx(network), 'list': ac8, 'components': [names.get(i, 'tableless %d' % i) for i in ac8]},
        'eat17List': eat,
        'membershipDiffToEat17': {'remove': [names[i] for i in ac8 if i not in eat],
            'add': [names[i] for i in eat if i not in ac8]},
        'listSlack': 'none: lists are packed back to back, so growth needs a relocated (Runtime-owned) list',
        'removal': removal, 'addition': addition}


# ------------------------------------------------------------------------------------------------ snapshots
def manager_map(img, reader, base_address, root) -> dict[int, list[int]]:
    """Manager global -> component indices, from the first rip-relative global each component's handlers load."""
    world = root + WORLD_OFFSET
    out = {}
    for idx in range(324):
        for table in ('p0_unreferenced', 'p1_create_queue', 'p5_destroy_b'):
            value = instances.u64(reader, world + HANDLER_TABLES[table] + 8 * idx)
            if not value or not base_address <= value < base_address + len(img.data):
                continue
            found = None
            for ins in img.disasm(value - base_address, value - base_address + 0x40)[:12]:
                target = img.rip_target(ins)
                if target and 0x3300000 <= target < 0x3500000 and ins.mnemonic == 'mov':
                    found = target
                    break
            if found:
                out.setdefault(found, set()).add(idx)
                break
    return {k: sorted(v) for k, v in out.items()}


def snapshot_facts(t, img, names) -> dict:
    data = t.entities
    frames = sorted(t.frames.items(), key=lambda kv: kv[1][0])
    idx_of = {h: i for i, h in t._index_type.items()}
    out = {}
    for name in SNAPSHOTS:
        reader = instances.SnapshotReader(name)
        try:
            game = reader.modules['game.dll']['base']
            root = instances.u64(reader, game + ENTITY_MANAGER)
            esh = instances.u64(reader, root + ESH_SLOT)
            ena = instances.u64(reader, root + ENA_SLOT)
            region = reader.snapshot.region(esh)
            blob_base = region['base']
            image = reader.read(blob_base, len(data))
            esh_start, esh_size = frames[0][1][0] + tables.FRAME_SIZE, frames[0][1][1]
            file_esh, mem_esh = data[esh_start:esh_start + esh_size], image[esh_start:esh_start + esh_size]
            patch = collections.Counter()
            for row in range(ESH_CAPACITY):
                f, m = file_esh[row * 32:row * 32 + 32], mem_esh[row * 32:row * 32 + 32]
                same_rest = f[:8] == m[:8] and f[16:] == m[16:]
                file_pointer, mem_pointer = struct.unpack_from('<Q', f, 8)[0], struct.unpack_from('<Q', m, 8)[0]
                if not struct.unpack_from('<Q', f)[0]:
                    patch['emptyRowNullPatched' if same_rest and file_pointer == 2 ** 64 - 1 and mem_pointer == 0
                        else 'emptyRowOther'] += 1
                else:
                    patch['listPointerPatched' if same_rest and mem_pointer == esh + file_pointer
                        else 'usedRowOther'] += 1
            rest_identical = (image[:esh_start] == data[:esh_start] and
                image[esh_start + ESH_CAPACITY * 32:] == data[esh_start + ESH_CAPACITY * 32:])
            slots_ok = 0
            for type_hash, (position, _) in t.frames.items():
                index = idx_of.get(type_hash)
                if index is not None and instances.u64(reader, root + SLOT_BASE + 8 * index) == \
                        blob_base + position + tables.FRAME_SIZE:
                    slots_ok += 1
            world = root + WORLD_OFFSET
            handlers = {}
            for label in ('WeaponReload', 'WeaponRounds', 'WeaponAssistedReload', 'Backblast', 'WeaponMagazine'):
                row = {}
                for table, offset in HANDLER_TABLES.items():
                    value = instances.u64(reader, world + offset + 8 * INDEX[label])
                    row[table] = (hx(value - game) if value and game <= value < game + len(img.data)
                        else None if not value else hx(value))
                handlers[label] = row
            mapping = manager_map(img, reader, game, root) if name == xref.DEFAULT_SNAPSHOT else None
            invalid = struct.unpack('<I', reader.read(game + INVALID_ENTITY, 4))[0]
            census = collections.Counter()
            raw = reader.read(root + DESCRIPTORS, DESCRIPTOR_STRIDE * DESCRIPTOR_COUNT)
            for k in range(DESCRIPTOR_COUNT):
                resource, entity = struct.unpack_from('<QI', raw, k * DESCRIPTOR_STRIDE)
                if entity != invalid and resource:
                    census[resource] += 1
            out[name] = {
                'entityManager': hx(root), 'componentWorld': hx(world),
                'entityFile': {'base': hx(blob_base), 'regionSize': hx(region['size']), 'fileSize': len(data),
                    'protect': hx(region['protect']), 'readOnly': region['protect'] == 2,
                    'privateAllocation': region['type'] == instances.MEM_PRIVATE,
                    'eshIsFirstInstanceData': esh - blob_base == frames[0][1][0] + tables.FRAME_SIZE,
                    'enaIsSecondInstanceData': ena - blob_base == frames[1][1][0] + tables.FRAME_SIZE,
                    'entitySettingsRows': dict(patch), 'everythingElseByteIdentical': rest_identical,
                    'slotsPointingIntoTheFile': slots_ok, 'componentTables': len(t._index_type)},
                'handlers': handlers,
                'managerGlobals': ({hx(g): [names.get(i, i) for i in mapping.get(g, [])] for g in MANAGER_GLOBALS}
                    if mapping else None),
                'liveEntities': {'total': sum(census.values()), 'AC-8': census.get(AC8, 0),
                    'EAT-17': census.get(EAT17, 0), 'EAT-700': census.get(EAT700, 0)},
            }
        finally:
            reader.close()
    return out


# ------------------------------------------------------------------------------------------------ verdicts
ANSWERS = {
    'q1_mechanism': {
        'a_spawnMembership': {'answer': 'The EntitySettings u16 list of the entity\'s resource (EntitySettingsHashmap, '
            '4096 rows, & 0xFFF, linear probe, key 0 = empty). Spawn 0xFDC140 -> 0x581320 calls, per listed index, '
            'the create handler (component world +0xF0C110) and the init handler (+0xF0CB30) around the entity-delta '
            'dispatcher; 0x581780 calls the post-create handler (+0xF0D550). Destroy 0xFDC820 calls +0xF0DF70 / '
            '+0xF0E990 per index of the CURRENT list; network create 0x581C40 and migration 0xFDBB40 reach the row '
            'by its ROW INDEX through EntityNetworkDataArray and call +0xF0F3B0 / +0xF0FDD0; 0x581E10 calls +0xF107F0 '
            '/ +0xF11210. The per-table index rows play no part in deciding membership.',
            'confidence': 'CONFIRMED (code pins; the list/row invariant holds for all 1,909 entities)'},
        'b_typeLookup': {'answer': 'Open-addressing hash over the table\'s own ComponentIndexData rows as loaded '
            '{u64 resource, u32 record, u32 0}: home = resource mod capacity (capacity compiled in as an immediate, '
            'reciprocal multiply or & (capacity-1)); linear probe +1 with wrap; key == resource -> record index at '
            'row +8; key 0 -> stop, NULL; at most capacity probes. No tombstone value, no sorted array, no rebuilt '
            'runtime index, no per-type pointer cache. Capacity = 2 x rows in 269 of 270 tables (load factor 0.5). '
            'Resolvers (e.g. WeaponReload 0x4FD220, WeaponData 0x509A40) first try the manager\'s private-copy map '
            '(deltas only) and fall back to this lookup; delta-copy creators fall back to the table\'s unowned last '
            '(DEFAULT) record (59 tables have one) when the type has no row.',
            'confidence': 'CONFIRMED (pins for WeaponReload, Spottable, ProjectileWeapon; 24,241 rows on valid '
                'probe paths; slot-site census)'},
        'c_memory': {'answer': 'Both structures are the entity file bytes loaded IN PLACE by 0xFDB440 into one '
            'private allocation (DL load-in-place; only the 1,909 EntitySettings array offsets are patched into '
            'absolute pointers). Slots, EntitySettingsHashmap and EntityNetworkDataArray pointers live in the '
            'entity manager (RW). The allocation is PAGE_READONLY (0x2) in all seven snapshots: every write needs '
            'the existing guarded VirtualProtect handling (already used for type-record writes, which live in the '
            'same allocation). 0xFDB860 can reload the whole file (no static callers found).',
            'confidence': 'CONFIRMED (seven snapshots)'},
    },
    'q2_removal': {
        'listOnly': 'Spawn skips the component cleanly (no handler call, no instance), and 0x753A10 gate 1 then '
            'passes (it tests the instance hash +0x20). But the type row stays: the resolver 0x4FD220 still '
            'returns the AC-8\'s WeaponReload TYPE record for an entity without an instance - a state that never '
            'occurs in vanilla (row <=> list invariant).',
        'rowOnly': 'Unsafe: the create handler still makes an instance, while the resolver returns NULL. 17 of its '
            '18 call sites dereference the result without a NULL test (STRONG crash path).',
        'both': 'WeaponReload itself then looks exactly like an EAT\'s (no instance, no row). The AC-8 would keep '
            'WeaponRounds and WeaponAssistedReload, though. In all 25 / 6 vanilla types these components occur only '
            'with WeaponReload. The team-reload consumer 0xA7BFE0 calls the resolver and dereferences without a '
            'NULL test (0xA7C35F). Unproven consumers: refused.',
        'consumers': {
            'spawn': 'clean skip (CONFIRMED)',
            'autoDrop0x753A10': 'gate 1 passes without an instance (CONFIRMED). Gate 2 is the SeatCollection '
                'manager (index 286, STRONG). The AC-8\'s auto_drop_ability is 0, and whether a WeaponRounds weapon '
                'reaches 0x753A10 at all is UNKNOWN: its callers sit in the Wieldable / WeaponData paths.',
            'reloadAndAmmoUi': 'via the resolver: NULL-dereference risk when the row is absent but the code path '
                'assumes it (STRONG). With list + row both removed, every path that EATs exercise is safe; the '
                'paths reached because of WeaponRounds are UNKNOWN.',
            'teamReload': 'WeaponAssistedReload without WeaponReload: never in vanilla. 0xA7BFE0 dereferences the '
                'resolver result (UNKNOWN, likely crash).',
            'destroy': 'HAZARD (CONFIRMED in code): destroy iterates the list as it is at destroy time. If the '
                'list changes between spawn and destroy, the WeaponReload destroy 0x778A00 runs for an entity '
                'without an instance. Its hash remove 0x172F8A0 returns 0 on a miss, so it removes ANOTHER '
                'entity\'s instance 0 or underflows the counts. The list must never change while any instance of '
                'the type exists.',
            'network': 'Every peer builds the component set from its own list (remote spawn 0xBA03C0 goes through '
                'EntityNetworkDataArray to the row index), and the per-component network handlers (+0xF0F3B0 / '
                '+0xF0FDD0, +0xF107F0 / +0xF11210) iterate that list. Component lists are never sent; the network '
                'type (row +0x18) is unchanged. Peers with different lists register different component state for '
                'the same network object, so the WeaponReload network handler 0x778C70 indexes with -1. Every peer '
                'must apply the identical edit before any instance exists anywhere. Whether the network layer '
                'tolerates a layout change per network type is UNKNOWN.',
            'saveAndLoadout': 'Loadout and armory code is keyed by resource. Record iterators (LoadoutEntry '
                '0x9F1CC0, Encyclopedia 0x1789B60) do not read the index rows. The armory\'s WeaponReload type '
                'lookups (0x1762D30, 0x1766B10) do test for NULL. Nothing is saved from membership (PLAUSIBLE).',
        },
        'safeRowRemoval': 'Never write key 0: in linear probing that cuts the probe chain of every later key in the '
            'cluster. Use either a tombstone (a non-zero key that no resource can equal; the lookups simply probe '
            'past it, and no index-row iterator exists) or backward-shift deletion. The AC-8\'s WeaponReload and '
            'WeaponAssistedReload rows have no dependents, but zeroing its WeaponRounds row (displaced by one) '
            'would make pump_shotgun_trench and bolt_action_rifle unfindable (see ac8.removal). Either way is '
            'restorable byte for byte.',
        'verdict': 'refused (removing WeaponReload alone); research-only (removing it as part of a full set '
            'transplant)',
    },
    'q3_addition': {
        'indexRow': 'Hash-safe: write the new row into the first empty slot on the AC-8\'s probe path. No existing '
            'key\'s probe passes an empty slot, so other lookups are unchanged. Free rows exist (capacity = 2 x '
            'rows). There are no spare records, though (records = rows, or rows + the default record). Mapping the '
            'AC-8 to the EAT-17\'s record would make it the FIRST shared record of this build: no record has two '
            'owners anywhere (sharedRecordsVanilla = 0). The record is only read, but the pattern is novel '
            '(UNKNOWN).',
        'list': 'There is no slack: the 1,909 lists are packed with 0 gap bytes. Growing a list means pointing the '
            'row\'s array pointer at a Runtime-owned u16 array (sorted, same order as the creation passes) and '
            'raising the count. That is a pointer from game data into Runtime memory, and it must outlive every '
            'reader until the exact restore.',
        'disagreement': 'List entry without a row: an instance is created; the resolvers return NULL (crash path); '
            'delta copies fall back to the DEFAULT record. Row without a list entry: no instance, but the resolvers '
            'return type data. Neither state exists in vanilla.',
        'ac8Specific': 'Backblast + WeaponRounds and WeaponMagazine + WeaponRounds never co-occur in vanilla. Adding '
            'only Backblast / WeaponMagazine to the AC-8 creates two novel combinations.',
        'verdict': 'refused (partial addition); research-only (as part of a full set transplant)',
    },
    'q4_safety': {
        'noCodePatching': 'met: every edit is data (rows, list pointer and count).',
        'missionScopedExactRestore': 'conditionally met. The restore is byte-exact, but it is only safe when NO '
            'instance of the type exists on this machine (destroy and network handlers follow the current list). '
            'The entity descriptor table (manager +0xF32F18, 24 bytes x 0x800, +0 resource) allows a read-only '
            '"zero live instances" proof before both the write and the restore.',
        'consumerPathProof': 'not met for partial edits (novel combinations). For a full transplant (carrier list '
            ':= donor list, every donor component backed by a row, every carrier-only row tombstoned) each '
            'component sees a vanilla-proven combination. Still unproven: the new rows must point at the donor\'s '
            'records (no spare records exist), which would create the first shared records of the build; the '
            'carrier\'s own records for the common components (EAT-17-class consumers apply to them); and the '
            'carrier\'s network type against its new layout.',
        'multiplayer': 'no protocol change is needed for consistency, but every peer must hold the identical '
            'transplant before the first instance exists anywhere. Join in progress is unsolved (a joiner\'s '
            'existing list would disagree with the host\'s entities). A vanilla peer with a different list for '
            'the same network type is UNKNOWN to unsafe.',
        'verdicts': {
            'removal': 'REFUSED as a partial edit (removing WeaponReload alone from the AC-8). Research-only as '
                'part of a full transplant.',
            'addition': 'REFUSED as a partial edit (Backblast / WeaponMagazine onto the AC-8). Research-only as '
                'part of a full transplant.',
            'fullTransplant': 'RESEARCH-ONLY. Feasible-with-proof only if the proof plan passes. Compared with the '
                'EAT-700 clone (same component set, no membership edit) it gains nothing for the EAT-17 goal except '
                'carrier choice, and it adds the lifecycle and multiplayer constraints above.',
        },
    },
}

PROOF_PLAN = [
    {'step': 'O1 offline overlay (no game)', 'what': 'On the loaded entity-file image from a mission snapshot, '
        'apply the transplant overlay: AC-8 list := EAT-17 list (relocated buffer), rows added for Backblast / '
        'WeaponMagazine (EAT-17 records), WeaponReload / WeaponRounds / WeaponAssistedReload rows tombstoned. Re-run '
        'every type lookup algorithm (all 270 tables) for every resource; diff against the original. Pass: only '
        'the AC-8\'s five component answers change; every other resource is bit-identical; the restore bytes '
        'reproduce the snapshot.'},
    {'step': 'O2 consumer census', 'what': 'For every handler (p1..p9) and resolver of the five components: '
        'enumerate the call sites reachable for a wielded support weapon and classify them as NULL-tested / '
        'instance-guarded / unguarded. Pass: no unguarded site is reachable for an EAT-17-class entity.'},
    {'step': 'O3 lifecycle guard design', 'what': 'Read-only "zero live instances of the carrier" check over the '
        'entity descriptor table; write and restore are refused unless it holds and no spawn is queued. Prove the '
        'descriptor layout in all snapshots (the census is part of this script).'},
    {'step': 'L1 live, solo, ship -> mission', 'what': 'Transplant at mission start (zero AC-8 instances), call '
        'the AC-8 rack, pick up, fire, drop, discard, die with it held, extract. Restore on the ship after teardown '
        'with the zero-instance guard. Pass: no crash, EAT behaviour, a vanilla AC-8 in the armory afterwards, a '
        'second mission vanilla.'},
    {'step': 'L2 live, two machines with the same transplant', 'what': 'Both peers apply before spawn; '
        'host-spawned and client-spawned carriers; ownership migration (pickup by the other player). Pass: no '
        'desync or crash; both peers see the EAT behaviour.'},
    {'step': 'L3 refusals', 'what': 'Join in progress and vanilla / non-Runtime peers: the capability must '
        'refuse. Pass: a refusal is logged and no write happens.'},
]

RISKS = [
    'Destroy-time list mismatch corrupts another entity\'s component instance (0x172F8A0 returns 0 on a miss).',
    'Network handlers index with -1 when the list and the instance disagree (0x778C70). Peers with different lists '
    'for one network type are not understood.',
    'A relocated list buffer must stay valid (and never be freed) until the restore. If the Runtime unloads first, '
    'the game reads freed memory.',
    'Entity-file reload 0xFDB860 would silently discard the edit (it is only reachable through a pointer; no '
    'static caller found).',
    'Entity deltas (weapon customization) can create private copies for a component that is not in the list '
    '(dispatcher 0x5740B0 / 0x779410). Such copies are never destroyed: a stale copy keyed by entity id.',
    'The ship and armory spawn weapon entities as well: the carrier must have zero instances at write and restore '
    'time, including previews.',
]

OPEN_QUESTIONS = [
    'Does the network layer bind a fixed replicated layout to the network type (EntitySettings +0x18), or does it '
    'accept whatever the components register per entity?',
    'Is 0x753A10 ever reached for a WeaponRounds (clip) weapon, and what does the AC-8 HUD do without WeaponReload?',
    'Which entity deltas target the AC-8 or the EAT-17 on the hellpod path (default customization)?',
    'Is 0xFDB860 (entity-file reload) reachable in retail builds (for example on a content hot reload)?',
    'Unnamed table-less components in the lists (39, 237, 240) participate in the same passes; 237 is the '
    'manager behind 0x3326660 used by 0x753A10.',
]

CONCLUSION = ('Component membership is plain data and can be edited without code: the spawn, destroy and network '
    'passes iterate the EntitySettings u16 list, and every type lookup is an open-addressing hash over the table\'s '
    'own index rows, both loaded in place from the entity file into one PAGE_READONLY allocation. The game, '
    'however, relies on two invariants that vanilla data never breaks: a type has a row in a table if and only if '
    'the component is in its list, and the list does not change while an instance of the type exists. Removing only '
    'the AC-8\'s WeaponReload (or adding only Backblast / WeaponMagazine) creates component combinations that never '
    'occur in vanilla (WeaponRounds and WeaponAssistedReload always come with WeaponReload) and unguarded consumers '
    'dereference NULL, so partial edits are refused. A full set transplant (the carrier takes the donor\'s exact list, '
    'with rows that share the donor\'s records) stays inside vanilla-proven component combinations, but it is '
    'research-only: shared records do not occur in this build, and the transplant needs a zero-live-instance '
    'guard for both the write and the restore, an identical edit on every peer before any spawn, and no join in '
    'progress. The EAT-700 clone already achieves the EAT-17 goal without any membership edit.')


def build() -> dict:
    t = tables.pinned()
    names = names_of(t)
    img = xref.CodeImage.from_snapshot('game.dll')
    pins = prove_pins(img)
    flat = [p for rows in pins.values() for p in rows]
    mismatch = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(mismatch.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % mismatch)
    structure = hash_structure(t)
    invariant = membership_invariant(t)
    settings = entity_settings(t)
    co = cooccurrence(t)
    case = ac8_case(t, names)
    sites = classify_slot_sites(img, t)
    readers = esh_readers(img)
    nulls = resolver_null_census(img)
    snaps = snapshot_facts(t, img, names)
    checks = {
        'entityFileReadOnlyInEverySnapshot': all(s['entityFile']['readOnly'] for s in snaps.values()),
        'everySlotPointsIntoTheLoadedFile': all(s['entityFile']['slotsPointingIntoTheFile'] ==
            s['entityFile']['componentTables'] for s in snaps.values()),
        'onlyTheListPointersArePatched': all(s['entityFile']['everythingElseByteIdentical'] and
            s['entityFile']['entitySettingsRows'] == {'listPointerPatched': settings['rows'],
            'emptyRowNullPatched': ESH_CAPACITY - settings['rows']} for s in snaps.values()),
        'allRowsOnProbePath': structure['rowsOffProbePath'] == 0,
        'membershipInvariant': invariant['rowWithoutListEntry'] == 0 and invariant['listEntryWithoutRow'] == 0,
        'listsPackedNoSlack': settings['listStorage']['gapBytes'] == 0 and settings['listStorage']['sharedLists'] == 0,
        'roundsAndAssistedReloadNeverWithoutReload': co['WeaponRounds without WeaponReload'] == 0 and
            co['WeaponAssistedReload without WeaponReload'] == 0,
        'ac8RowsWhoseZeroingBreaksOtherLookups': {k: v['keysWhoseProbeCrossesTheRow'] for k, v in
            case['removal'].items() if v['zeroingBreaksLookups']},
        'gate2IsSeatCollection': any(s['managerGlobals'] and s['managerGlobals'].get('0x3326D88') == ['SeatCollection']
            for s in snaps.values()),
        'gate1IsWeaponReload': any(s['managerGlobals'] and s['managerGlobals'].get('0x3326A70') == ['WeaponReload']
            for s in snaps.values()),
        'resolverSitesWithoutNullTest': nulls['WeaponReload resolver 0x4FD220 (copy, else type)']['total'] -
            nulls['WeaponReload resolver 0x4FD220 (copy, else type)']['nullTested'],
        'noEshReaderIteratesAllRows': all(r['byResource'] or r['byNetworkRowIndex'] or not r['iteratesList']
            for r in readers),
    }
    return {
        'build': BUILD, 'writes': 0, 'protectionChanges': 0,
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': mismatch,
        'structures': {'hashTables': structure, 'membershipInvariant': invariant, 'entitySettings': settings,
            'handlerTables': {k: hx(v) for k, v in HANDLER_TABLES.items()},
            'componentWorld': 'entity manager + 0x40'},
        'code': {'slotSites': sites, 'entitySettingsReaders': readers, 'resolverNullCensus': nulls},
        'cooccurrence': co,
        'ac8': case,
        'snapshots': snaps,
        'checks': checks,
        'answers': ANSWERS, 'proofPlan': PROOF_PLAN, 'risks': RISKS, 'openQuestions': OPEN_QUESTIONS,
        'conclusion': CONCLUSION,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--check', action='store_true', help='regenerate and compare with the committed JSON')
    args = parser.parse_args()
    result = build()
    text = json.dumps(result, indent=1) + '\n'
    if args.check:
        current = OUTPUT.read_text(encoding='utf-8') if OUTPUT.is_file() else ''
        if current != text:
            print('component membership research is out of date:', OUTPUT.relative_to(ROOT))
            sys.exit(1)
        print('component membership research is current')
        return
    OUTPUT.write_text(text, encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; checks', result['checks'])


if __name__ == '__main__':
    main()
