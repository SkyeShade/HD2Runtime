"""Borrowed BeamType / DamageInfo slots for per-weapon beam rows (EXPERIMENTAL beam conversion, branch
feature/beam-conversion): can each beam-converted weapon get its OWN BeamInfo row (spare BeamType slot k repointed to a
Runtime-owned 0x70-byte copy of the LAS-13 Trident's row 6) and its OWN DamageInfo row (spare id d repointed to a
Runtime-owned 0x4C-byte copy of row 508), so that damage, durable, AP, demolition, stagger, push, status and range are
per weapon? Read-only, offline, build F5FEE03DCFDB: the game.dll image of a retained snapshot (capstone), every retained
snapshot, the pinned settings / entity / delta data and the type library.

Follows research/docs/beam-damage-per-weapon-F5FEE03DCFDB.md (BeamFire, the ring, InitHitInfo, the typed reference
census) and research/docs/beam-table-relocation-F5FEE03DCFDB.md (the owned BeamWeapon table).

What this script proves (fail closed: every expectation below raises when the image says otherwise):
  1. Census of every instruction that addresses the BeamInfo pointer array (0x37C8250, 31 slots), its default row
     (0x37C81E0), the DamageInfo pointer array (0x37C60C0, 650 slots) and its default row (0x37C7510): rip-relative AND
     absolute (image-base + disp32) forms, inside .pdata functions AND in leaf functions without unwind data (the two
     getters). For each: the reaching definitions of the index (CFG, all paths, register moves followed), the row
     members read, whether the row pointer is stored anywhere but the stack frame, and every write to the arrays.
     Who calls the loaders, the getters, and the unreferenced reload / clear functions.
  2. Spare slots beyond typed references: constant BeamTypes / DamageInfo ids at every consumer (array index, getter
     argument, BeamFire / state-machine beam argument, the hit struct's DamageInfo id at every InitHitInfo caller and
     wrapper caller); immediates equal to a candidate id inside damage-related functions (fail closed); the typed census
     re-checked over the whole type library (nested structs, inline arrays, types without a table); the rows of every
     candidate in all nine snapshots.
  3. BeamInfo members by their readers: +8 is the beam range (ray length / sweep end / drawn-length clamp), +4 the sweep
     radius, the visual is created at fire time from the row's 64-bit resource hash (+0x30), and the ray / hit
     processing re-read the row through the array by the entry's BeamType at every update (no per-type cache). No
     consumer reads a row's own key (+0) except the loaders.
  4. DamageInfo members as InitHitInfo reads them; the id is read once to index the array and is not stored in the hit
     event (so it does not travel to DamageValues / ProduceDamage).
  5. The re-proof the Runtime must run at apply, and the allocation order.

Output: research/beam-rows-borrowed-F5FEE03DCFDB.json.   py -3 scripts/research_beam_rows.py
"""
from __future__ import annotations

import collections
import json
import re
import struct
import sys
from pathlib import Path

import capstone
from capstone import x86
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_beam_damage as damage_research  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from migration import build_view  # noqa: E402
from scan import tables as scan_tables, xref  # noqa: E402

OUTPUT = ROOT / 'research/beam-rows-borrowed-F5FEE03DCFDB.json'
SNAPSHOTS = damage_research.SNAPSHOTS
BEAM_TABLE, BEAM_SLOTS, BEAM_DEFAULT, BEAM_STRIDE = 0x37C8250, 31, 0x37C81E0, 0x70
DAMAGE_TABLE, DAMAGE_SLOTS, DAMAGE_DEFAULT, DAMAGE_STRIDE = 0x37C60C0, 650, 0x37C7510, 0x4C
RANGES = {
    'beamDefault': (BEAM_DEFAULT, BEAM_DEFAULT + BEAM_STRIDE),
    'beamArray': (BEAM_TABLE, BEAM_TABLE + 8 * BEAM_SLOTS),
    'damageArray': (DAMAGE_TABLE, DAMAGE_TABLE + 8 * DAMAGE_SLOTS),
    'damageDefault': (DAMAGE_DEFAULT, DAMAGE_DEFAULT + DAMAGE_STRIDE),
}
BEAM_SYSTEM_GLOBAL, RING_BASE, RING_STRIDE, RING_SLOTS = 0x347CED0, 0x170, 0x168, 64
ENTRY_BEAM_TYPE, ENTRY_DAMAGE_ID, ENTRY_ALIVE = 0x18, 0x34, 0x110
BEAM_MANAGER_GLOBAL, BEAM_WEAPON_SLOT, BEAM_RECORD_BASE, BEAM_RECORD_STRIDE, BEAM_FILE_RECORDS = (
    0x346BF98, 0xF12CE8, 0x2E0, 0x78, 24)
TRIDENT_BEAM, TRIDENT_DAMAGE = 6, 508

BEAM_FIRE, STATE_BEAM_FIRE, BEAM_LISTENERS = 0x13B8410, 0x11BB550, 0xB54920
GET_BEAM_INFO, GET_DAMAGE_INFO, INIT_HIT_INFO = 0x11D8020, 0x11F8EA0, 0x12A15E0
LOADERS = {'beam': 0x11D7E00, 'damage': 0x11F8C60}
NO_CALLER_FUNCTIONS = {
    0x129BE40: 'reloads every settings table (BeamInfo and DamageInfo loaders included)',
    0x129BF00: 'clears every settings array, then reloads them',
    0x129C110: 'clears every settings array (unload)',
    0x129C300: 'clears every settings array, then reloads them',
    0x11D7FC0: 'clears the BeamInfo array',
    0x11F8E30: 'clears the DamageInfo array',
    0xB54880: 'BeamType listener dispatch (row +0x58), second list',
    0xA37140: 'BeamType listener dispatch (row +0x58), leaf',
    0xA37170: 'BeamType listener dispatch (row +0x58), leaf',
    0xA282B0: 'reads DamageInfo [array + argument 4] +0xC',
}
# Expected results of the census (the script raises when the image differs).
EXPECTED_ARRAY_STORES = {0x11D7F7F, 0x11F8DDF}
EXPECTED_ARRAY_CLEARS = {0x11D7E5B, 0x11F8CBB, 0x11D7FF7, 0x11F8E83, 0x129BF42, 0x129BFDC, 0x129C152, 0x129C1EC,
                         0x129C342, 0x129C3DC}
EXPECTED_BEAM_CONSTANTS = {17, 21, 26, 28}
EXPECTED_DAMAGE_CONSTANTS = {12, 633}

# (rva, asm, rip target or None, role): generated from the image, every one checked byte-for-byte in all snapshots.
PROOFS = {
    'tableWriters': [
        (0x11D7E5B, 'lea r12, [rip + {rip}]', 0x37C8250, 'BeamInfo loader 0x11D7E00: the pointer array ...'),
        (0x11D7E72, 'cmp qword ptr [rip + {rip}], 0', 0x37C8258, "... 'already loaded' test on slot 1 ..."),
        (0x11D7E7E, 'mov r8d, 0xf8', None, '... 0xF8 bytes = 31 slots ...'),
        (0x11D7E87, 'call 0x208aaa0', None, '... cleared (memset) before a reload ...'),
        (0x11D7F76, 'imul rdx, rax, 0x70', None, '... rows of stride 0x70 ...'),
        (0x11D7F7D, 'mov eax, dword ptr [rdx]', None, "... slot index = the row's own +0 ..."),
        (0x11D7F7F, 'mov qword ptr [r12 + rax*8], rdx', None, '... slot := row pointer (the only per-slot store)'),
        (0x11F8CBB, 'lea r12, [rip + {rip}]', 0x37C60C0, 'DamageInfo loader 0x11F8C60: the pointer array ...'),
        (0x11F8CD2, 'cmp qword ptr [rip + {rip}], 0', 0x37C60C8, "... 'already loaded' test on slot 1 ..."),
        (0x11F8CDE, 'mov r8d, 0x1450', None, '... 0x1450 bytes = 650 slots ...'),
        (0x11F8DD6, 'imul rdx, rax, 0x4c', None, '... rows of stride 0x4C ...'),
        (0x11F8DDD, 'mov eax, dword ptr [rdx]', None, "... slot index = the row's own +0 ..."),
        (0x11F8DDF, 'mov qword ptr [r12 + rax*8], rdx', None, '... slot := row pointer (the only per-slot store)'),
        (0x13F35E5, 'call 0x11d7e00', None, 'settings load 0x13F2E00 runs the BeamInfo loader ...'),
        (0x13F35EF, 'call 0x11f8c60', None, '... and the DamageInfo loader'),
        (0xAB1D55, 'call 0x13f2e00', None, "the game Setup 0xAB0EE0 (BUILD_INFO, 'Game World') calls 0x13F2E00 once; "
            "Setup's only caller is 0x4EE63F"),
        (0x4EE63F, 'call 0xab0ee0', None, 'game module init 0x4EE160 -> Setup (0x4EE160 has no visible caller: the '
            'module entry)'),
        (0x129BE61, 'call 0x11d7e00', None, '0x129BE40 (no visible caller or reference) re-runs the BeamInfo loader '
            '...'),
        (0x129BE6B, 'call 0x11f8c60', None, '... and the DamageInfo loader'),
        (0x129BF42, 'lea rcx, [rip + {rip}]', 0x37C60C0, '0x129BF00 (no visible caller or reference) clears the '
            'DamageInfo array ...'),
        (0x129BFDC, 'lea rcx, [rip + {rip}]', 0x37C8250, '... and the BeamInfo array ...'),
        (0x129C0F6, 'call 0x11d7e00', None, '... then re-runs the BeamInfo loader ...'),
        (0x129C105, 'jmp 0x11f8c60', None, '... and the DamageInfo loader (tail jump)'),
        (0x129C152, 'lea rcx, [rip + {rip}]', 0x37C60C0, '0x129C110 (no visible caller or reference) clears the '
            'DamageInfo array ...'),
        (0x129C1EC, 'lea rcx, [rip + {rip}]', 0x37C8250, '... and the BeamInfo array (unload only)'),
        (0x129C342, 'lea rcx, [rip + {rip}]', 0x37C60C0, '0x129C300 (no visible caller or reference) clears the '
            'DamageInfo array ...'),
        (0x129C3DC, 'lea rcx, [rip + {rip}]', 0x37C8250, '... and the BeamInfo array ...'),
        (0x129C4F6, 'call 0x11d7e00', None, '... then re-runs the BeamInfo loader ...'),
        (0x129C505, 'jmp 0x11f8c60', None, '... and the DamageInfo loader (tail jump)'),
        (0x11D7FF7, 'lea rcx, [rip + {rip}]', 0x37C8250, '0x11D7FC0 (no visible caller or reference): clears the '
            'BeamInfo array'),
        (0x11F8E83, 'lea rcx, [rip + {rip}]', 0x37C60C0, '0x11F8E30 (no visible caller or reference): clears the '
            'DamageInfo array'),
    ],
    'getters': [
        (0x11D8020, 'test ecx, ecx', None, 'GetBeamInfo 0x11D8020 (leaf, no .pdata entry): BeamType 0 -> ...'),
        (0x11D8024, 'lea rax, [rip + {rip}]', 0x37C81E0, '... the default row; else ...'),
        (0x11D802E, 'lea rcx, [rip + {rip}]', 0x37C8250, '... the pointer array ...'),
        (0x11D8035, 'mov rax, qword ptr [rcx + rax*8]', None, '... [array + BeamType x 8], no bound'),
        (0x1773139, 'mov ecx, dword ptr [rbp + 0x960]', None, 'its only caller (arsenal stat builder 0x176F830): '
            'BeamType from a component record copy ...'),
        (0x177313F, 'call 0x11d8020', None, '... GetBeamInfo'),
        (0x11F8EA0, 'test ecx, ecx', None, 'GetDamageInfo 0x11F8EA0 (leaf, no .pdata entry): id 0 -> ...'),
        (0x11F8EA4, 'lea rax, [rip + {rip}]', 0x37C7510, '... the default row; else ...'),
        (0x11F8EAE, 'lea rcx, [rip + {rip}]', 0x37C60C0, '... the pointer array ...'),
        (0x11F8EB5, 'mov rax, qword ptr [rcx + rax*8]', None, '... [array + id x 8], no bound (80 callers)'),
    ],
    'codeConstants': [
        (0x92C614, 'mov ecx, 0x279', None, '0x92B770: a hard-coded DamageInfo id 633 ...'),
        (0x92C692, 'call 0x11f8ea0', None, '... GetDamageInfo(633)'),
        (0x8D8BB3, 'mov rdx, qword ptr [rip + {rip}]', 0x37C7488, '0x8D86D0: a fixed read of DamageInfo slot 633 '
            '([0x37C60C0 + 633 x 8])'),
        (0x70B314, 'lea rax, [rbp + 0x1a0]', None, '0x70ADB0: hit struct s = rbp+0x1A0 ...'),
        (0x70BAB5, 'mov dword ptr [rbp + 0x1c4], 0xc', None, '... s+0x24 := DamageInfo id 12 ...'),
        (0x70BD5F, 'mov dword ptr [rbp + 0x1c4], 0xc', None, '... s+0x24 := 12 ...'),
        (0x70C275, 'mov dword ptr [rbp + 0x1c4], 0xc', None, '... s+0x24 := 12 ...'),
        (0x70B330, 'mov qword ptr [rsp + 0x28], rax', None, '... s passed as InitHitInfo argument 6 ...'),
        (0x70B413, 'call 0x12a15e0', None, '... InitHitInfo'),
        (0x11BB56F, 'mov ebp, edx', None, '0x11BB550 (state-machine beam fire): BeamType = edx ...'),
        (0x11BB5A8, 'mov r9d, ebp', None, '... BeamFire argument 4 ...'),
        (0x11BB5D8, 'call 0x13b8410', None, '... BeamFire'),
        (0x10F6155, 'mov edx, 0x15', None, '0x10F60E0: BeamType 21 ...'),
        (0x10F6163, 'call 0x11bb550', None, '... fired'),
        (0x10F6192, 'mov edx, 0x15', None, '0x10F60E0: BeamType 21 ...'),
        (0x10F61A0, 'call 0x11bb550', None, '... fired'),
        (0x10F6474, 'mov edx, 0x15', None, '0x10F6430: BeamType 21 ...'),
        (0x10F6482, 'call 0x11bb550', None, '... fired'),
        (0x10F6664, 'mov edx, 0x15', None, '0x10F6620: BeamType 21 ...'),
        (0x10F6672, 'call 0x11bb550', None, '... fired'),
        (0x1103DA0, 'mov edx, 0x1c', None, '0x1103D10: BeamType 28 ...'),
        (0x1103DAE, 'call 0x11bb550', None, '... fired'),
        (0x110B2EF, 'test edx, edx', None, '0x110B2E0: the fire path runs only when the argument is 0 ...'),
        (0x110B2F1, 'jne 0x110b392', None, '... (jne skips it) ...'),
        (0x110B31C, 'lea edx, [rdi + 0x1a]', None, '... BeamType 0x1A + 0 = 26 ...'),
        (0x110B328, 'call 0x11bb550', None, '... fired'),
        (0x110D1F1, 'mov edx, 0x1a', None, '0x110D1C0: BeamType 26 ...'),
        (0x110D1FF, 'call 0x11bb550', None, '... fired'),
        (0x110D73F, 'test edx, edx', None, '0x110D730: only when the argument is 0 ...'),
        (0x110D741, 'jne 0x110d85a', None, '... (jne skips it) ...'),
        (0x110D75C, 'lea edx, [rsi + 0x11]', None, '... BeamType 0x11 + 0 = 17 ...'),
        (0x110D768, 'call 0x11bb550', None, '... fired'),
        (0x110DA8F, 'test edx, edx', None, '0x110DA80: only when the argument is 0 ...'),
        (0x110DA91, 'jne 0x110dbaa', None, '... (jne skips it) ...'),
        (0x110DAAC, 'lea edx, [rsi + 0x11]', None, '... BeamType 17 ...'),
        (0x110DAB8, 'call 0x11bb550', None, '... fired'),
    ],
    'beamRowMembers': [
        (0x13B9595, 'mov dword ptr [r14 + 0x18], ebx', None, "BeamFire: E+0x18 = BeamType (the entry's identity for "
            "every later row read)"),
        (0x13B9599, 'mov eax, dword ptr [r15 + 0x68]', None, 'row +0x68 (DangerLevel) ...'),
        (0x13B959D, 'mov dword ptr [r14 + 0x38], eax', None, '... E+0x38'),
        (0x13B95AF, 'mov rdx, qword ptr [r15 + 0x30]', None, 'row +0x30 (64-bit beam effect resource hash) ...'),
        (0x13B95DA, 'call rax', None, '... the effect is created at fire time from that hash (world effect interface '
            '+0x280)'),
        (0x13B95E0, 'mov rdx, qword ptr [r15 + 0x40]', None, 'row +0x40 (64-bit resource hash) -> another create call '
            'at fire time'),
        (0x13B9695, 'mov eax, dword ptr [r15 + 4]', None, 'row +4 ...'),
        (0x13B9699, 'mov dword ptr [r14 + 0x4c], eax', None, '... E+0x4C (sweep radius; 0 = a thin ray)'),
        (0x13B969D, 'mov eax, dword ptr [r15 + 8]', None, 'row +8 ...'),
        (0x13B96A1, 'mov dword ptr [r14 + 0x44], eax', None, '... E+0x44 (beam length / range)'),
        (0x13B96BA, 'mov dword ptr [r14 + 0x48], r12d', None, 'E+0x48 := 0 (drawn length, set by the hit processing)'),
        (0x13B9880, 'mov eax, dword ptr [r15 + 0x2c]', None, 'row +0x2C (SurfaceImpactType) ...'),
        (0x13B9884, 'mov dword ptr [r14 + 0x3c], eax', None, '... E+0x3C'),
        (0x13B9918, 'mov eax, dword ptr [r15 + 0x28]', None, 'row +0x28 ...'),
        (0x13B991C, 'mov dword ptr [r14 + 0x114], eax', None, '... E+0x114'),
        (0x13B9923, 'mov eax, dword ptr [r15 + 0x48]', None, 'row +0x48 (32-bit id) ...'),
        (0x13B9927, 'mov dword ptr [r14 + 0xf4], eax', None, '... E+0xF4 (passed to 0x12556E0 when non-zero)'),
        (0x13B992E, 'mov eax, dword ptr [r15 + 0x4c]', None, 'row +0x4C (32-bit id) ...'),
        (0x13B9932, 'mov dword ptr [r14 + 0xf8], eax', None, '... E+0xF8'),
        (0x13B9A04, 'mov rdx, qword ptr [r15 + 0x30]', None, 'row +0x30 again (effect parameters 0x88F1AF97 / '
            '0xE783D2BD) at fire time'),
        (0x13B9B50, 'movss xmm2, dword ptr [r15 + 0x5c]', None, 'row +0x5C read at fire time'),
    ],
    'range': [
        (0x13BAEDB, 'mov eax, dword ptr [rdi + rbx + 0x188]', None, 'ray submission 0x13BAE20: E+0x18 BeamType ...'),
        (0x13BAEFD, 'mov r14, qword ptr [rcx + rax*8]', None, '... its row, re-read through the pointer array at '
            'every update ...'),
        (0x13BAF01, 'movss xmm0, dword ptr [rdi + rbx + 0x1bc]', None, '... E+0x4C (radius) == 0 -> a single ray ...'),
        (0x13BAF39, 'mov edx, dword ptr [r14 + 0x50]', None, '... row +0x50 (RaycastTemplate) selects the query '
            'template ...'),
        (0x13BAF68, 'movss xmm0, dword ptr [rdi + rbx + 0x1b4]', None, '... E+0x44 ...'),
        (0x13BAF87, 'movss dword ptr [rsp + 0x20], xmm0', None, "... is the ray query's length argument ..."),
        (0x13BAF8D, 'call 0x175ca60', None, '... ray query 0x175CA60 ...'),
        (0x13BAF92, 'mov dword ptr [rdi + rbx + 0x2c4], eax', None, '... id in E+0x154'),
        (0x13BB02D, 'movss xmm1, dword ptr [rdi + rbx + 0x1b4]', None, 'radius != 0: E+0x44 (length) with E+0x4C '
            '(radius) into a sweep ...'),
        (0x13BB0D2, 'call 0x175bb40', None, '... sweep query 0x175BB40 (E+0x14C)'),
        (0x13BB0F6, 'mulss xmm0, dword ptr [rdi + rbx + 0x184]', None, 'end point = origin + direction x E+0x44 ...'),
        (0x13BB1BE, 'mov eax, dword ptr [r14 + 0x54]', None, '... with row +0x54 (32-bit hash) ...'),
        (0x13BB1D0, 'call 0x175bb40', None, '... second query 0x175BB40 (E+0x150)'),
        (0x13BB538, 'movss xmm9, dword ptr [r14 + rsi + 0x1b4]', None, 'hit processing: nearest-hit distance starts '
            'at E+0x44 ...'),
        (0x13BD1B1, 'movss xmm1, dword ptr [r14 + rsi + 0x1b4]', None, '... E+0x44 ...'),
        (0x13BD1C3, 'minss xmm0, xmm1', None, '... drawn length = min(nearest hit, E+0x44) ...'),
        (0x13BD1C7, 'movss dword ptr [r14 + rsi + 0x1b8], xmm0', None, '... E+0x48'),
        (0x13BD827, 'movss xmm3, dword ptr [r14 + rsi + 0x1b8]', None, 'E+0x48 -> the beam effect (vtable +0x378)'),
    ],
    'hitRowMembers': [
        (0x13BB3A0, 'mov eax, dword ptr [r14 + rsi + 0x188]', None, 'hit processing: E+0x18 ...'),
        (0x13BB3B2, 'mov rax, qword ptr [rdx + rax*8 + 0x37c8250]', None, '... the row re-read through the pointer '
            'array (no cache) ...'),
        (0x13BB3BA, 'mov qword ptr [rbp - 0x58], rax', None, '... kept in the stack frame only'),
        (0x13BB77E, 'test byte ptr [r12 + 0x64], 1', None, 'row +0x64 bit 0'),
        (0x13BB803, 'mov r9d, dword ptr [r12 + 0x58]', None, 'row +0x58 (HitEffectDamageType) -> InitHitInfo r9 '
            '(event +0xC)'),
        (0x13BBB2B, 'mov r9d, dword ptr [rdi + 0x58]', None, 'row +0x58 (pulse path) -> InitHitInfo r9'),
        (0x13BD0FF, 'cmp dword ptr [rdi + 0x60], 0', None, 'row +0x60 (ExplosionType): 0 = none ...'),
        (0x13BD109, 'movss xmm0, dword ptr [rdi + 0x5c]', None, '... row +0x5C ...'),
        (0x13BD18B, 'mov r8d, dword ptr [rdi + 0x60]', None, '... row +0x60 spawned'),
        (0x13BC3EA, 'mov rax, qword ptr [rbx + rax*8 + 0x37c8250]', None, "hit listeners: E+0x18's row ..."),
        (0x13BC3F2, 'cmp dword ptr [rax + 0x58], 0x11', None, '... +0x58 == 0x11'),
        (0xB5497E, 'mov rax, qword ptr [r15 + rbp*8]', None, '0xB54920 (BeamType from E+0x18 at all 5 callers): the '
            'row ...'),
        (0xB54982, 'cmp dword ptr [rax + 0x58], 0x11', None, '... +0x58 == 0x11 -> listener 0xA36E00'),
    ],
    'damageRow': [
        (0x12A1C21, 'mov rbx, qword ptr [rsp + 0x98]', None, 'InitHitInfo: the hit source s ...'),
        (0x12A1C29, 'mov eax, dword ptr [rbx + 0x24]', None, '... s+0x24, the DamageInfo id (its only read of s+0x24) '
            '...'),
        (0x12A23FD, 'lea rcx, [rip + {rip}]', 0x37C60C0, '... the pointer array ...'),
        (0x12A2404, 'mov rcx, qword ptr [rcx + rax*8]', None, '... row = [array + id x 8] ...'),
        (0x12A2408, 'mov eax, dword ptr [rcx + 0x28]', None, '... row +0x28 (ElementType) overwrites eax: the id is '
            'not stored in the event ...'),
        (0x12A240E, 'mov dword ptr [r14 + 4], eax', None, '... event +4 = element'),
        (0x12A2415, 'mov eax, dword ptr [rcx + 0x1c]', None, 'row +0x1C -> event +0xB0'),
        (0x12A2429, 'mov eax, dword ptr [rcx + 0x20]', None, 'row +0x20 -> event +0xAC'),
        (0x12A243A, 'mov eax, dword ptr [rcx + 0x24]', None, 'row +0x24 -> event +0xB4'),
        (0x12A2453, 'movups xmm0, xmmword ptr [rcx + 0x2c]', None, 'row +0x2C..+0x3B (status pairs 0, 1) ...'),
        (0x12A2457, 'movups xmmword ptr [r14 + 0xc0], xmm0', None, '... event +0xC0'),
        (0x12A245F, 'movups xmm1, xmmword ptr [rcx + 0x3c]', None, 'row +0x3C..+0x4B (status pairs 2, 3) ...'),
        (0x12A2471, 'movups xmmword ptr [r14 + 0xd0], xmm1', None, '... event +0xD0'),
        (0x12A2479, 'movd xmm3, dword ptr [rcx + 4]', None, 'row +4 (standard) ...'),
        (0x12A247E, 'movd xmm1, dword ptr [rcx + 8]', None, '... row +8 (durable) ...'),
        (0x12A249D, 'movss dword ptr [r14 + 0x98], xmm3', None, '... event +0x98 = the standard / durable blend'),
        (0x12A24A6, 'mov eax, dword ptr [rcx + 0xc]', None, 'row +0xC (AP lane 1) -> event +0x9C'),
        (0x12A24DF, 'mov eax, dword ptr [rcx + 0x18]', None, 'row +0x18 (AP lane 4) -> event +0xA8'),
    ],
}

# ------------------------------------------------------------------------------------------------ register dataflow
FAMILY = {}
for _f in ('ax', 'bx', 'cx', 'dx'):
    for _n in ('r' + _f, 'e' + _f, _f, _f[0] + 'l', _f[0] + 'h'):
        FAMILY[_n] = 'r' + _f
for _f in ('si', 'di', 'bp', 'sp'):
    for _n in ('r' + _f, 'e' + _f, _f, _f + 'l'):
        FAMILY[_n] = 'r' + _f
for _i in range(8, 16):
    for _s in ('', 'd', 'w', 'b'):
        FAMILY['r%d%s' % (_i, _s)] = 'r%d' % _i
VOLATILE = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}


def family(name):
    return FAMILY.get(name, name)


class Flow:
    """CFG per function (recursive descent from the root; tail jumps into other functions not followed) and
    reaching definitions of a register (all paths, register-to-register moves followed; a call defines the volatile
    registers)."""

    def __init__(self, code: xref.CodeImage):
        self.code, self.cache = code, {}

    def cfg(self, root):
        if root not in self.cache:
            insns = self.code.reachable(root)
            preds = collections.defaultdict(list)
            for a, ins in insns.items():
                m, nxt, succ = ins.mnemonic, a + ins.size, []
                if m in ('ret', 'int3', 'ud2'):
                    pass
                elif m == 'jmp':
                    if ins.operands[0].type == x86.X86_OP_IMM:
                        succ = [ins.operands[0].imm]
                elif m.startswith('j'):
                    succ = [nxt] + ([ins.operands[0].imm] if ins.operands[0].type == x86.X86_OP_IMM else [])
                else:
                    succ = [nxt]
                for s in succ:
                    if s in insns:
                        preds[s].append(a)
            self.cache[root] = (insns, preds)
        return self.cache[root]

    @staticmethod
    def writes(ins):
        _, w = ins.regs_access()
        out = {family(ins.reg_name(x)) for x in w}
        if ins.mnemonic == 'call':
            out |= VOLATILE
        return out

    def defs(self, root, at, reg):
        insns, preds = self.cfg(root)
        out, seen, work = set(), set(), [(p, reg) for p in preds[at]]
        if not preds[at] and at != root:
            out.add(('nopred', at, reg))
        while work:
            a, r = work.pop()
            if (a, r) in seen:
                continue
            seen.add((a, r))
            ins = insns[a]
            if r in self.writes(ins):
                ops = ins.operands
                if (ins.mnemonic in ('mov', 'movsxd', 'movzx') and len(ops) == 2 and ops[1].type == x86.X86_OP_REG
                        and family(ins.reg_name(ops[1].reg)) != r):
                    src = family(ins.reg_name(ops[1].reg))
                    if preds[a]:
                        work += [(p, src) for p in preds[a]]
                    else:
                        out.add(('entry', a, src))
                    continue
                out.add((ins.mnemonic + ' ' + ins.op_str, a, r))
                continue
            if preds[a]:
                work += [(p, r) for p in preds[a]]
            else:
                out.add(('entry', a, r))
        return out

    def forward_uses(self, root, start, reg, limit=400):
        """Memory operands based on reg after start, until reg is redefined (all successor paths)."""
        insns, _ = self.cfg(root)
        uses, seen, work = {}, set(), [start]
        while work:
            a, steps = work.pop(), 0
            while a in insns and a not in seen and steps < limit:
                seen.add(a)
                ins = insns[a]
                steps += 1
                if a != start:
                    for op in ins.operands:
                        if op.type == x86.X86_OP_MEM and op.mem.base and family(ins.reg_name(op.mem.base)) == reg:
                            uses[a] = ins
                if a != start and reg in self.writes(ins):
                    break
                if ins.mnemonic == 'ret':
                    break
                if ins.mnemonic == 'jmp':
                    if ins.operands[0].type == x86.X86_OP_IMM:
                        work.append(ins.operands[0].imm)
                    break
                if ins.mnemonic.startswith('j') and ins.operands[0].type == x86.X86_OP_IMM:
                    work.append(ins.operands[0].imm)
                a += ins.size
        return uses

    def slot_writes(self, root, base_reg, disp):
        """Instructions of the function writing the stack slot [base_reg + disp] (any width covering it)."""
        insns, _ = self.cfg(root)
        out = []
        for a, ins in sorted(insns.items()):
            if not ins.operands or ins.mnemonic in ('cmp', 'test'):
                continue
            op = ins.operands[0]
            if (op.type == x86.X86_OP_MEM and op.mem.base and ins.reg_name(op.mem.base) == base_reg
                    and not op.mem.index and op.mem.disp <= disp < op.mem.disp + op.size and len(ins.operands) > 1):
                src = ins.operands[1]
                if src.type == x86.X86_OP_IMM:
                    value = {'immediate': src.imm & 0xFFFFFFFF}
                elif src.type == x86.X86_OP_REG:
                    value = {'defs': self.describe(self.defs(root, a, family(ins.reg_name(src.reg))))}
                else:
                    value = {}
                out.append({'rva': '0x%X' % a, 'asm': ins.mnemonic + ' ' + ins.op_str, **value})
        return out

    @staticmethod
    def describe(found):
        return sorted(('0x%X %s' % (a, s)) if s not in ('entry', 'nopred') else '%s@0x%X:%s' % (s, a, r)
                      for s, a, r in found)


def fn_root(code, rva):
    """The function of rva: its .pdata root, or for a leaf without unwind data the first instruction after the int3
    padding that precedes it."""
    root = code.root(rva)
    if root is not None:
        return root
    at = rva
    while at > rva - 0x400 and code.data[at - 1] != 0xCC and not (at % 16 == 0 and code.data[at - 1] == 0xC3):
        at -= 1
    return at


def decode_at(code, rva):
    return next(code.md.disasm(code.data[rva:rva + 16], rva, 1), None)


def covering_instruction(code, at):
    """The instruction containing byte at: linear disassembly of its .pdata chunk, or of the leaf function."""
    chunk = code.chunk(at)
    start, end = chunk if chunk else (fn_root(code, at), at + 16)
    for address, size, _, _ in code.lite.disasm_lite(code.data[start:end], start):
        if address <= at < address + size:
            return address, size
        if address > at:
            return None
    return None


# -------------------------------------------------------------------------------------------------- 1. the census
def table_sites(code) -> dict:
    """Every instruction whose rip-relative target or absolute displacement lies in one of the four ranges."""
    lo, hi = code.text
    found = {}
    for phase in range(4):
        n = (hi - lo - phase) // 4
        view = numpy.frombuffer(code.data, dtype='<i4', offset=lo + phase, count=n).astype(numpy.int64)
        pos = numpy.arange(n, dtype=numpy.int64) * 4 + lo + phase
        for name, (a, b) in RANGES.items():
            candidates = set()
            for tail in (0, 1, 2, 4):
                t = pos + 4 + tail + view
                candidates |= {int(pos[h]) for h in numpy.nonzero((t >= a) & (t < b))[0]}
            unsigned = view & 0xFFFFFFFF
            candidates |= {int(pos[h]) for h in numpy.nonzero((unsigned >= a) & (unsigned < b))[0]}
            for at in sorted(candidates):
                cover = covering_instruction(code, at)
                if not cover:
                    continue
                ins = code.insn(cover[0])
                target = code.rip_target(ins)
                hit = target is not None and a <= target < b
                hit = hit or any(op.type == x86.X86_OP_MEM and op.mem.base != x86.X86_REG_RIP and a <= op.mem.disp < b
                                 for op in ins.operands)
                if hit:
                    found[ins.address] = (name, ins, target)
    return found


def census(code, flow) -> dict:
    sites = table_sites(code)
    out, array_writes, stored_rows, key_reads, index_sources = [], [], [], [], collections.Counter()
    constants = {'beam': [], 'damage': []}
    for rva in sorted(sites):
        name, ins, target = sites[rva]
        table = 'beam' if name.startswith('beam') else 'damage'
        root = fn_root(code, rva)
        rec = {'rva': '0x%X' % rva, 'function': '0x%X' % root, 'leafWithoutPdata': code.root(rva) is None,
               'range': name, 'asm': ins.mnemonic + ' ' + ins.op_str}
        if target is not None:
            rec['ripTarget'] = '0x%X' % target
            if name.endswith('Array') and target != RANGES[name][0]:
                rec['fixedSlot'] = (target - RANGES[name][0]) // 8
                if ins.mnemonic == 'mov':     # a row read (the loaders' cmp of slot 1 is the 'loaded' test)
                    constants[table].append({'value': rec['fixedSlot'], 'rva': rec['rva'], 'how': 'fixed slot read'})
        mem = [op for op in ins.operands if op.type == x86.X86_OP_MEM]
        if mem and ins.operands[0].type == x86.X86_OP_MEM and ins.mnemonic.startswith('mov') and len(ins.operands) > 1:
            array_writes.append(rec['rva'])
        # the row pointer: an indexed load here, or a lea of the array whose register is indexed later
        loads = []
        if mem and mem[0].mem.index and ins.operands[0].type == x86.X86_OP_REG:
            loads.append((rva, ins, family(ins.reg_name(mem[0].mem.index))))
        elif ins.mnemonic == 'lea' and name.endswith('Array'):
            reg = family(ins.reg_name(ins.operands[0].reg))
            for a, use in sorted(flow.forward_uses(root, rva, reg).items()):
                op = next(o for o in use.operands if o.type == x86.X86_OP_MEM and o.mem.base
                          and family(use.reg_name(o.mem.base)) == reg)
                if op.mem.index:
                    if use.operands[0].type == x86.X86_OP_MEM:
                        array_writes.append('0x%X' % a)
                        rec.setdefault('stores', []).append('0x%X %s %s' % (a, use.mnemonic, use.op_str))
                    else:
                        loads.append((a, use, family(use.reg_name(op.mem.index))))
                elif use.mnemonic != 'lea':
                    rec.setdefault('baseUses', []).append('0x%X %s %s' % (a, use.mnemonic, use.op_str))
        elif ins.mnemonic in ('lea', 'mov') and ins.operands[0].type == x86.X86_OP_REG and (
                name.endswith('Default') or rec.get('fixedSlot') is not None):
            loads.append((rva, ins, None))
        rec['loads'] = []
        for a, load, index in loads:
            item = {'rva': '0x%X' % a, 'asm': load.mnemonic + ' ' + load.op_str}
            if index:
                found = flow.defs(root, a, index)
                item['indexDefs'] = flow.describe(found)
                for s, at, _ in found:
                    if s.startswith('mov ') and re.search(r', (0x[0-9a-f]+|\d+)$', s):
                        value = int(s.rsplit(', ', 1)[1], 0)
                        constants[table].append({'value': value, 'rva': '0x%X' % at, 'how': 'array index'})
                    key = re.sub(r'0x[0-9a-f]{5,}', 'X', s.split(' ', 1)[-1]) if s not in ('entry', 'nopred') else s
                    index_sources[(table, key)] += 1
            row_reg = family(load.reg_name(load.operands[0].reg))
            members, persisted = set(), []
            for b, use in flow.forward_uses(root, a, row_reg).items():
                for k, op in enumerate(use.operands):
                    if op.type == x86.X86_OP_MEM and op.mem.base and family(use.reg_name(op.mem.base)) == row_reg:
                        if use.mnemonic.startswith('nop'):
                            continue
                        members.add(op.mem.disp)
                        if op.mem.disp == 0 and not op.mem.index:
                            key_reads.append({'rva': '0x%X' % b, 'asm': use.mnemonic + ' ' + use.op_str})
                        if k == 0 and len(use.operands) > 1 and use.mnemonic not in ('cmp', 'test'):
                            stored_rows.append({'rva': '0x%X' % b, 'asm': use.mnemonic + ' ' + use.op_str,
                                                'kind': 'write through the row pointer'})
                if (use.mnemonic == 'mov' and use.operands[0].type == x86.X86_OP_MEM and len(use.operands) == 2
                        and use.operands[1].type == x86.X86_OP_REG
                        and family(use.reg_name(use.operands[1].reg)) == row_reg):
                    persisted.append('0x%X %s %s' % (b, use.mnemonic, use.op_str))
            item['rowMembersRead'] = ['+0x%X' % m for m in sorted(members)]
            for p in persisted:
                base_reg = re.search(r'\[(\w+)', p).group(1)
                if base_reg not in ('rsp', 'rbp'):
                    stored_rows.append({'rva': p.split()[0], 'asm': p, 'kind': 'row pointer stored off the stack'})
            if persisted:
                item['rowPointerStores'] = persisted
            rec['loads'].append(item)
        out.append(rec)
    return {'sites': out, 'arrayWrites': sorted(set(array_writes)), 'rowPointerPersisted': stored_rows,
            'rowKeyReads': key_reads, 'constants': constants,
            'indexSourceSummary': [{'table': t, 'source': s, 'count': c}
                                   for (t, s), c in sorted(index_sources.items(), key=lambda x: (x[0][0], -x[1],
                                                                                                     x[0][1]))]}


def references(code, f) -> dict:
    """Direct calls / jumps, rip references, 4-byte RVAs and 8-byte pointers to f anywhere in the image (the 4-byte
    hits inside the exception directory are unwind data, listed separately)."""
    d4 = numpy.frombuffer(code.data[:len(code.data) // 4 * 4], dtype='<u4')
    d8 = numpy.frombuffer(code.data[:len(code.data) // 8 * 8], dtype='<u8')
    rva4 = [int(k) * 4 for k in numpy.nonzero(d4 == f)[0]]

    def unwind_like(r):   # a RUNTIME_FUNCTION {begin, end, unwind info} with begin = f or end = f
        end, info = struct.unpack_from('<II', code.data, r + 4)
        if f < end <= f + 0x200000 and 0 < info < len(code.data):
            return True
        begin, info = struct.unpack_from('<I', code.data, r - 4)[0], struct.unpack_from('<I', code.data, r + 4)[0]
        return f - 0x200000 <= begin < f and 0 < info < len(code.data)
    unwind = [r for r in rva4 if unwind_like(r)]
    return {'calls': ['0x%X' % c for c in code.calls_to(f)],
            'ripReferences': ['0x%X' % i.address for i in code.references(f) if i.mnemonic not in ('call', 'jmp')],
            'rva32': ['0x%X' % r for r in rva4 if r not in unwind], 'rva32UnwindEntries': len(unwind),
            'pointers64': ['0x%X' % (int(k) * 8) for k in numpy.nonzero(d8 == code.base + f)[0]]}


def pointers_into_tables(code) -> list:
    """8-byte values anywhere in the image (any alignment) that point into the four ranges: a stored alias of an
    array or default row (none expected)."""
    out = []
    for off in range(8):
        v = numpy.frombuffer(code.data, dtype='<u8', offset=off, count=(len(code.data) - off) // 8)
        for name, (a, b) in RANGES.items():
            for h in numpy.nonzero((v >= code.base + a) & (v < code.base + b))[0]:
                out.append({'at': '0x%X' % (off + int(h) * 8), 'range': name, 'target': '0x%X' % (int(v[h]) - code.base)})
    return sorted(out, key=lambda x: x['at'])


HIT_STRUCT_NOTES = {
    '0x680F08': 'reviewed by hand: no instruction of 0x680CF0 writes s+0x24 (rsp+0x84); no immediate',
    '0x694DCA': 'reviewed by hand (call not reachable by the CFG walk): s+0x24 = rbp+0x134 := [rdi + r14 + 0x101C] '
        '(0x694A67, instance data); no immediate',
    '0x6F8A38': 'reviewed by hand: s = rbp+8, s+0x24 zeroed by the qword store 0x6F8988 (rax = 0)',
}


def callers_up(code, f, depth=4) -> list:
    out, seen, work = [], set(), [(f, 0)]
    while work:
        g, d = work.pop()
        root = fn_root(code, g)
        if root in seen or d > depth:
            continue
        seen.add(root)
        callers = code.calls_to(root)
        out.append({'function': '0x%X' % root, 'callers': ['0x%X' % c for c in callers]})
        work += [(c, d + 1) for c in callers]
    return out


# ------------------------------------------------------------------------------------- 2. constants at consumers
def lea_guarded_constant(code, flow, root, def_text, at):
    """lea edx, [reg + imm] where reg is the function's argument 2 and the path runs only when that argument is 0
    (test edx, edx; jne past the lea at the function start): the constant imm."""
    m = re.match(r'lea \w+, \[(\w+) \+ (0x[0-9a-f]+)\]$', def_text)
    if not m:
        return None
    if flow.describe(flow.defs(root, at, family(m.group(1)))) != ['entry@0x%X:rdx' % root]:
        return None
    head = list(code.md.disasm(code.data[root:root + 0x20], root))
    for i, ins in enumerate(head[:-1]):
        if ins.mnemonic == 'test' and ins.op_str == 'edx, edx' and head[i + 1].mnemonic == 'jne':
            if head[i + 1].operands[0].imm > at:
                return int(m.group(2), 16)
    return None


def argument_constants(code, flow, target, reg, table) -> list:
    out = []
    for c in code.calls_to(target):
        root = fn_root(code, c)
        insns, _ = flow.cfg(root)
        item = {'call': '0x%X' % c, 'function': '0x%X' % root}
        if c not in insns:
            item['unresolved'] = 'not reachable from the function root'
            out.append(item)
            continue
        found = flow.defs(root, c, reg)
        item['defs'] = flow.describe(found)
        values = []
        for s, at, _ in found:
            m = re.match(r'mov \w+, (0x[0-9a-f]+|\d+)$', s)
            if m:
                values.append(int(m.group(1), 0))
            elif s.startswith('lea'):
                v = lea_guarded_constant(code, flow, root, s, at)
                if v is not None:
                    values.append(v)
        if values:
            item['constants'] = sorted(set(values))
        item['table'] = table
        out.append(item)
    return out


def hit_struct_ids(code, flow) -> dict:
    """The DamageInfo id each InitHitInfo caller puts in s+0x24 (s = argument 6, [rsp + 0x28] at the call); callers
    that pass their own argument 4 are wrappers, whose callers are traced the same way (s = r9)."""
    def trace(call, arg_reg=None):
        root = fn_root(code, call)
        insns, _ = flow.cfg(root)
        item = {'call': '0x%X' % call, 'function': '0x%X' % root}
        if call not in insns:
            item['unresolved'] = 'not reachable from the function root'
            return item
        if arg_reg is None:
            seq = sorted(insns)
            k = seq.index(call)
            store = next((insns[a] for a in reversed(seq[max(0, k - 80):k])
                          if insns[a].mnemonic == 'mov' and insns[a].op_str.startswith('qword ptr [rsp + 0x28],')), None)
            if store is None or store.operands[1].type != x86.X86_OP_REG:
                item['unresolved'] = 'argument 6 not found'
                return item
            found = flow.defs(root, store.address, family(store.reg_name(store.operands[1].reg)))
        else:
            found = flow.defs(root, call, arg_reg)
        item['structDefs'] = flow.describe(found)
        writes = []
        for s, at, _ in found:
            m = re.match(r'lea \w+, \[(rbp|rsp) ([+-]) (0x[0-9a-f]+)\]$', s)
            if m:
                disp = int(m.group(3), 16) * (1 if m.group(2) == '+' else -1) + 0x24
                writes += flow.slot_writes(root, m.group(1), disp)
        item['idWrites'] = writes
        item['constants'] = sorted({w['immediate'] for w in writes if 'immediate' in w})
        if any(s == 'entry' for s, _, _ in found):
            item['wrapper'] = True
        if not writes and not item.get('wrapper'):
            item['unresolved'] = 's+0x24 has no direct writer in the function (copied or zeroed elsewhere)'
        return item

    direct = [trace(c) for c in code.calls_to(INIT_HIT_INFO)]
    wrappers = sorted({int(d['function'], 16) for d in direct if d.get('wrapper')})
    nested = []
    for w in wrappers:
        for c in code.calls_to(w):
            nested.append({**trace(c, 'r9'), 'wrapper': '0x%X' % w})
    return {'initHitInfoCallers': direct, 'wrappers': ['0x%X' % w for w in wrappers], 'wrapperCallers': nested}


def related_immediates(code, roots, values) -> dict:
    """mov reg / [mem], imm32 with a candidate value inside the given functions."""
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    cs.skipdata = True
    lo, hi = code.text
    out = collections.defaultdict(list)
    for b, e, _ in code.pdata:
        b, e = int(b), int(e)
        if not lo <= b < hi or code.root(b) not in roots:
            continue
        for a, size, mnemonic, op in cs.disasm_lite(code.data[b:e], b):
            if mnemonic == 'mov' and op.count(',') == 1:
                src = op.split(', ')[-1]
                if re.fullmatch(r'0x[0-9a-f]+|\d+', src) and int(src, 0) in values:
                    out[int(src, 0)].append('0x%X %s %s (function 0x%X)' % (a, mnemonic, op, code.root(b)))
    return {str(k): v for k, v in sorted(out.items())}


# ------------------------------------------------------------------------------------------ data: typed census
def library_types_with(enums) -> list:
    """Every type in the type library with a member of the given enum types (direct members; containers listed)."""
    t = scan_tables.pinned()
    lib = t.library
    want = {build_view.dl_hash(n): n for n in enums}
    hits = {}
    for th in sorted(lib.index):
        try:
            layout = lib.layout(th)
        except ValueError:
            continue
        for m in layout['members']:
            if m['type_hash'] in want:
                hits.setdefault(th, []).append({'offset': m['offset64'], 'atom': m['atom'], 'storage': m['storage'],
                                                'count': m['array_or_bits'], 'enum': want[m['type_hash']]})
    containers = collections.defaultdict(list)
    for th in sorted(lib.index):
        try:
            layout = lib.layout(th)
        except ValueError:
            continue
        for m in layout['members']:
            if m['type_hash'] in hits:
                containers[m['type_hash']].append('%s +%d' % (t.type_name(th) or '0x%08X' % th, m['offset64']))
    return [{'type': t.type_name(th) or '0x%08X' % th, 'typeHash': '0x%08X' % th, 'members': v,
             'embeddedIn': containers.get(th, [])} for th, v in hits.items()]


# ------------------------------------------------------------------------------------------------ snapshot reads
def beam_row(raw) -> dict:
    f = struct.unpack_from('<I3fI', raw, 0)
    return {'key': f[0], 'radius': f[1], 'length': f[2], 'damageInfo': struct.unpack_from('<I', raw, 12)[0],
            'falloff': list(struct.unpack_from('<2f', raw, 0x10)),
            'multipliers': list(struct.unpack_from('<4f', raw, 0x18)), 'plus28': struct.unpack_from('<f', raw, 0x28)[0],
            'surfaceImpact': struct.unpack_from('<I', raw, 0x2C)[0],
            'hashes': ['0x%016X' % v for v in struct.unpack_from('<3Q', raw, 0x30)],
            'ids48_4C': ['0x%08X' % v for v in struct.unpack_from('<2I', raw, 0x48)],
            'raycastTemplate': struct.unpack_from('<I', raw, 0x50)[0],
            'hash54': '0x%08X' % struct.unpack_from('<I', raw, 0x54)[0],
            'hitEffectDamageType': struct.unpack_from('<I', raw, 0x58)[0],
            'plus5C': struct.unpack_from('<f', raw, 0x5C)[0], 'explosionType': struct.unpack_from('<I', raw, 0x60)[0],
            'bits64': raw[0x64], 'dangerLevel': struct.unpack_from('<I', raw, 0x68)[0], 'pulseBit6C': raw[0x6C] & 1,
            'bytes': raw.hex()}


def damage_row(raw) -> dict:
    v = struct.unpack_from('<I2i4I3IIi', raw, 0)
    return {'key': v[0], 'standard': v[1], 'durable': v[2], 'armorPenetration': list(v[3:7]),
            'plus1C_20_24': list(v[7:10]), 'element': v[10],
            'statuses': [list(struct.unpack_from('<If', raw, 44 + 8 * k)) for k in range(4)], 'bytes': raw.hex()}


def observe(name, beam_ids, damage_ids, file_beam, file_damage) -> dict:
    mem = base.Mem(name)
    try:
        def region(address):
            r = mem.s.region(address)
            return None if r is None else {'protect': '0x%X' % r['protect'], 'type': '0x%X' % r['type']}
        beam_ptrs = struct.unpack('<%dQ' % BEAM_SLOTS, mem.read(mem.game + BEAM_TABLE, 8 * BEAM_SLOTS))
        dmg_ptrs = struct.unpack('<%dQ' % DAMAGE_SLOTS, mem.read(mem.game + DAMAGE_TABLE, 8 * DAMAGE_SLOTS))
        rows = {}
        for k in sorted(set(beam_ids) | {TRIDENT_BEAM}):
            raw = mem.read(beam_ptrs[k], BEAM_STRIDE)
            rows['beam%d' % k] = {'keyMatches': struct.unpack_from('<I', raw)[0] == k,
                                  'equalsFile': raw == file_beam[k], 'region': region(beam_ptrs[k])}
        for d in sorted(set(damage_ids) | {TRIDENT_DAMAGE}):
            raw = mem.read(dmg_ptrs[d], DAMAGE_STRIDE)
            rows['damage%d' % d] = {'keyMatches': struct.unpack_from('<I', raw)[0] == d,
                                    'equalsFile': raw == file_damage[d], 'region': region(dmg_ptrs[d])}
        system = mem.ptr(mem.game + BEAM_SYSTEM_GLOBAL)
        ring_hits = []
        if system:
            ring = mem.read(system + RING_BASE, RING_SLOTS * RING_STRIDE)
            for s in range(RING_SLOTS):
                e = ring[s * RING_STRIDE:(s + 1) * RING_STRIDE]
                if e[ENTRY_ALIVE]:
                    bt, di = struct.unpack_from('<I', e, ENTRY_BEAM_TYPE)[0], struct.unpack_from('<I', e,
                                                                                                ENTRY_DAMAGE_ID)[0]
                    if bt in beam_ids or di in damage_ids:
                        ring_hits.append({'slot': s, 'beamType': bt, 'damageInfo': di})
        manager = mem.ptr(mem.game + BEAM_MANAGER_GLOBAL)
        table = mem.ptr(manager + BEAM_WEAPON_SLOT) if manager else None
        records = None
        if table:
            body = mem.read(table + BEAM_RECORD_BASE, BEAM_FILE_RECORDS * BEAM_RECORD_STRIDE)
            records = sorted({struct.unpack_from('<I', body, r * BEAM_RECORD_STRIDE)[0] for r in range(
                BEAM_FILE_RECORDS)})
        return {'snapshot': name, 'beamArrayRegion': region(mem.game + BEAM_TABLE),
                'damageArrayRegion': region(mem.game + DAMAGE_TABLE),
                'beamNullSlots': [k for k, p in enumerate(beam_ptrs) if not p],
                'damageNullSlots': [k for k, p in enumerate(dmg_ptrs) if not p],
                'rows': rows, 'liveRingEntriesOnCandidates': ring_hits,
                'liveBeamWeaponRecordBeamTypes': records}
    finally:
        mem.close()


# ----------------------------------------------------------------------------------------------------------- main
def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    code = xref.CodeImage(data, image_base, 'game.dll', base.PROFILE_DLL_SHA)
    flow = Flow(code)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    mismatch = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(mismatch.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % mismatch)

    # 1. census
    tables = census(code, flow)
    writes = {int(a, 16) for a in tables['arrayWrites']}
    if writes != EXPECTED_ARRAY_STORES:
        raise ValueError('another write to a pointer array: %r' % sorted(map(hex, writes)))
    if tables['rowPointerPersisted']:
        raise ValueError('a row pointer is kept beyond a stack frame: %r' % tables['rowPointerPersisted'])
    if tables['rowKeyReads']:
        raise ValueError('a consumer reads a row key: %r' % tables['rowKeyReads'])
    clears = {int(s['rva'], 16) for s in tables['sites'] if s['range'].endswith('Array')
              and s['asm'].startswith('lea') and not any(l.get('indexDefs') for l in s['loads'])
              and int(s['rva'], 16) not in (GET_BEAM_INFO + 0xE, GET_DAMAGE_INFO + 0xE)}
    aliases = pointers_into_tables(code)
    if aliases:
        raise ValueError('a stored pointer into the tables: %r' % aliases)
    if clears != EXPECTED_ARRAY_CLEARS:
        raise ValueError('array clears changed: %r' % sorted(map(hex, clears)))
    leaves = sorted({s['function'] for s in tables['sites'] if s['leafWithoutPdata']})
    functions = sorted({s['function'] for s in tables['sites']})
    who = {('0x%X' % f): {'role': role, **references(code, f)} for f, role in sorted(NO_CALLER_FUNCTIONS.items())}
    for f, r in who.items():
        if r['calls'] or r['ripReferences'] or r['rva32'] or r['pointers64']:
            raise ValueError('function %s has a visible caller or reference: %r' % (f, r))
    loaders = {k: {'function': '0x%X' % f, 'callers': ['0x%X' % c for c in code.calls_to(f)],
                   'callerChain': callers_up(code, f)} for k, f in LOADERS.items()}
    if sorted(loaders['beam']['callers']) != ['0x129BE61', '0x129C0F6', '0x129C4F6', '0x13F35E5']:
        raise ValueError('BeamInfo loader callers changed: %r' % loaders['beam']['callers'])

    # 2. constants at every consumer
    beam_args = (argument_constants(code, flow, BEAM_FIRE, 'r9', 'beam')
                 + argument_constants(code, flow, STATE_BEAM_FIRE, 'rdx', 'beam')
                 + argument_constants(code, flow, BEAM_LISTENERS, 'rdx', 'beam')
                 + argument_constants(code, flow, GET_BEAM_INFO, 'rcx', 'beam'))
    damage_args = argument_constants(code, flow, GET_DAMAGE_INFO, 'rcx', 'damage')
    hits = hit_struct_ids(code, flow)
    beam_constants = {v for a in beam_args for v in a.get('constants', [])}
    beam_constants |= {c['value'] for c in tables['constants']['beam']}
    damage_constants = {v for a in damage_args for v in a.get('constants', [])}
    damage_constants |= {c['value'] for c in tables['constants']['damage']}
    damage_constants |= {v for h in hits['initHitInfoCallers'] + hits['wrapperCallers'] for v in h.get('constants', [])}
    beam_constants.discard(0)
    damage_constants.discard(0)
    if beam_constants != EXPECTED_BEAM_CONSTANTS or damage_constants != EXPECTED_DAMAGE_CONSTANTS:
        raise ValueError('code constants changed: beam %r damage %r' % (beam_constants, damage_constants))

    # data: typed census (every component record, settings row, entity delta) + the whole type library
    typed = damage_research.typed_reference_census()
    library = library_types_with(('DamageInfoType', 'BeamType'))
    view = build_view.from_snapshot(build_profile.SNAPSHOT)
    file_beam = {k: view.settings['beam'].row_for_type(k)[0][1] for k in range(1, BEAM_SLOTS)}
    file_damage = {d: view.settings['damage'].row_for_type(d)[0][1] for d in range(1, DAMAGE_SLOTS)}
    spare_beam = [k for k in typed['unreferencedBeamTypes'] if k not in beam_constants]
    dmg_candidates = [d for d in typed['unreferencedDamageIds'] if d not in damage_constants]
    related = {int(s['function'], 16) for s in tables['sites'] if s['range'].startswith('damage')}
    related |= {int(h['function'], 16) for h in hits['initHitInfoCallers'] + hits['wrapperCallers']}
    related |= {int(a['function'], 16) for a in damage_args}
    imm = related_immediates(code, related, set(dmg_candidates))
    spare_damage = [d for d in dmg_candidates if str(d) not in imm]
    beam_related = {int(s['function'], 16) for s in tables['sites'] if s['range'].startswith('beam')}
    beam_related |= {int(a['function'], 16) for a in beam_args}
    beam_imm = related_immediates(code, beam_related, set(spare_beam))

    # allocation order
    trident = file_beam[TRIDENT_BEAM]
    slot_time = (0x50, 0x70)   # members re-read through the slot while a shot lives (+0x50..+0x6C)

    def beam_rank(k):
        same = file_beam[k][slot_time[0]:slot_time[1]] == trident[slot_time[0]:slot_time[1]]
        return (0 if same else 1, k)
    beam_order = sorted(spare_beam, key=beam_rank)

    def damage_rank(d):
        r = damage_row(file_damage[d])
        effects = any(s[0] for s in r['statuses']) or r['element'] != 0
        special = r['standard'] < 0 or r['durable'] < 0      # negative damage: semantics unknown, ranked last
        return (1 if special else 0, 1 if effects else 0, r['standard'] + r['durable'], sum(r['armorPenetration']),
                sum(r['plus1C_20_24']), -d)
    damage_order = sorted(spare_damage, key=damage_rank)
    capacity = min(len(spare_beam), len(spare_damage))

    observations = [observe(name, spare_beam, damage_order[:capacity], file_beam, file_damage) for name in SNAPSHOTS]
    for o in observations:
        if o['beamNullSlots'] != [0] or o['damageNullSlots'] != [0]:
            raise ValueError('%s: unexpected null slots' % o['snapshot'])
        bad = [k for k, v in o['rows'].items() if not (v['keyMatches'] and v['equalsFile'])]
        if bad or o['liveRingEntriesOnCandidates']:
            raise ValueError('%s: candidate rows changed or in use: %r %r' % (o['snapshot'], bad,
                                                                               o['liveRingEntriesOnCandidates']))
        if o['liveBeamWeaponRecordBeamTypes'] and set(o['liveBeamWeaponRecordBeamTypes']) & set(spare_beam):
            raise ValueError('%s: a live BeamWeapon record names a spare BeamType' % o['snapshot'])
        for key in ('beamArrayRegion', 'damageArrayRegion'):
            if o[key] != {'protect': '0x4', 'type': '0x1000000'}:
                raise ValueError('%s: %s is not image read-write memory: %r' % (o['snapshot'], key, o[key]))

    report = {
        'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'gameDllSha256': base.PROFILE_DLL_SHA,
        'writes': 0, 'protectionChanges': 0,
        'question': 'Can each beam-converted weapon get its own BeamInfo row (a spare BeamType slot repointed to a '
            'Runtime-owned copy of the Trident row 6) and its own DamageInfo row (a spare id repointed to a '
            'Runtime-owned copy of row 508), and is a BeamInfo-only variant (keep row 508, scale with the row '
            'multipliers) enough?',
        'verdict': {
            'optionA': 'STRONG (offline, solo): mechanically sound and the slots are free in every source this '
                'research can see. Every consumer reads the slot at use time (no cache, no stored row pointer, no key '
                'check); the only writers are the startup loaders (and four unreferenced reload / clear functions). '
                'Interim, borrowedVanillaRow, build-scoped (refused on any other build until this script is re-run), '
                'solo only, not live-tested. Capacity %d weapons (%d spare BeamTypes; %d spare DamageInfo ids).' % (
                    capacity, len(spare_beam), len(spare_damage)),
            'beamInfoOnly': 'STRONG (offline, solo), needs spare BeamTypes only: per weapon damage scale (standard and '
                'durable together, +0x18/+0x1C with falloff), AP scale (+0x20/+0x24, non-zero lanes only), range (+8), '
                'radius (+4), falloff (+0x10/+0x14), and +0xC may name ANY existing DamageInfo row read-only (e.g. the '
                'Scythe 501) without writing it. Not per weapon: durable ratio alone, +0x1C/+0x20/+0x24 (demolition / '
                'stagger / push leads), element, statuses, AP lane 4 when the row has 0 there.',
            'inPlaceAlternative': 'Writing the spare vanilla rows in place is possible without protection changes (row '
                'memory is private PAGE_READWRITE) but rejected: it writes vanilla rows, is a multi-dword write a '
                'reader can observe half-done, needs saved bytes to restore and a reload would leave it stale. The '
                'owned copy needs one aligned 8-byte store per slot, keeps the vanilla bytes as the re-proof anchor, '
                'restores with one store and a reload is detectable (slot != owned copy).'},
        'arrays': {'beamInfo': {'table': '0x%X' % BEAM_TABLE, 'slots': BEAM_SLOTS, 'defaultRow': '0x%X' % BEAM_DEFAULT,
                                'stride': BEAM_STRIDE},
                   'damageInfo': {'table': '0x%X' % DAMAGE_TABLE, 'slots': DAMAGE_SLOTS,
                                  'defaultRow': '0x%X' % DAMAGE_DEFAULT, 'stride': DAMAGE_STRIDE},
                   'memory': 'game.dll image .data, PAGE_READWRITE (MEM_IMAGE) in all nine snapshots; rows live in '
                       'private PAGE_READWRITE settings-resource memory'},
        'proofs': proofs, 'pinnedBytesMismatchPerSnapshot': mismatch,
        'census': {
            'sites': tables['sites'], 'siteCount': len(tables['sites']), 'functions': functions,
            'leafFunctionsWithoutPdata': leaves, 'arrayWrites': tables['arrayWrites'],
            'arrayClears': sorted('0x%X' % a for a in clears), 'expectedClears': sorted(
                '0x%X' % a for a in EXPECTED_ARRAY_CLEARS),
            'rowPointerPersisted': tables['rowPointerPersisted'], 'rowKeyReads': tables['rowKeyReads'],
            'indexSourceSummary': tables['indexSourceSummary'], 'loaders': loaders,
            'noVisibleCaller': who, 'storedPointersIntoTables': aliases,
            'covers': '.text by .pdata functions and leaf functions without unwind data; rip-relative and image-base '
                'absolute forms; NOT the protected sections (.vm_sec, .winlice, .boot), NOT Lua'},
        'constants': {'beamTypeArguments': beam_args, 'damageInfoGetterArguments': damage_args,
                      'hitStruct': hits, 'hitStructManualNotes': HIT_STRUCT_NOTES,
                      'arrayIndexConstants': tables['constants'],
                      'beamTypesInCode': sorted(beam_constants), 'damageIdsInCode': sorted(damage_constants),
                      'damageCandidateImmediatesInDamageFunctions': imm,
                      'beamCandidateImmediatesInBeamFunctions': beam_imm,
                      'beamImmediatesNote': 'informational: every BeamType consumer argument and index is traced to '
                          'its definition (the constants above), so these immediates (stat values in the arsenal '
                          'builders, other call arguments) do not feed a BeamType; DamageInfo ids keep the immediate '
                          'filter because some hit-struct sources are copies that are not traced to a writer'},
        'typedReferences': {**{k: v for k, v in typed.items() if k not in ('tridentBeamTypeReferences',
                                                                            'tridentDamageReferences')},
                            'libraryTypesWithMembers': library},
        'scriptData': 'No enum names: the type library stores no member or enumerator names and game.dll contains no '
            'DamageInfoType / BeamType strings. The Filediver reference enum (third-party, older build: 25 BeamType '
            'values against 31 slots here) is a lead only and is not used. Lua / script references to numeric ids '
            'are not searchable offline (compressed bundles): UNKNOWN.',
        'spare': {
            'beamTypes': [{'beamType': k, 'proof': 'STRONG', 'fileRow': beam_row(file_beam[k]),
                           'slotTimeMembersEqualTrident': file_beam[k][0x50:0x70] == trident[0x50:0x70]}
                          for k in beam_order],
            'beamTypesExcludedByCode': sorted(set(typed['unreferencedBeamTypes']) & beam_constants),
            'damageIds': [{'id': d, 'proof': 'STRONG', 'fileRow': damage_row(file_damage[d])} for d in damage_order],
            'damageIdsExcludedByCode': sorted(set(typed['unreferencedDamageIds']) & damage_constants),
            'damageIdsExcludedByImmediates': sorted(int(k) for k in imm),
            'proofLevels': 'STRONG = no typed reference (every component record incl. nested structs, settings row, '
                'entity delta; type library swept), no constant at any traced consumer, candidate immediates filtered '
                '(DamageInfo), row key == slot and bytes == file in all nine snapshots, no live ring entry or live '
                'BeamWeapon record on it. Not CONFIRMED: protected sections and Lua are not scannable.'},
        'observations': observations,
        'allocation': {
            'capacity': capacity, 'beamTypeOrder': beam_order, 'damageIdOrder': damage_order[:max(capacity, 8)],
            'pairs': [{'weaponSlot': i, 'beamType': beam_order[i], 'damageInfo': damage_order[i]}
                      for i in range(capacity)],
            'beamRule': 'first the spare rows whose members re-read through the slot during a shot (+0x50..+0x6F: '
                'RaycastTemplate, query hash, HitEffectDamageType, +0x5C, ExplosionType, +0x64, DangerLevel, pulse '
                'bit) equal the Trident row 6, so a restore with a live shot is benign; then by number',
            'damageRule': 'rows with negative damage (unknown semantics) last; rows without element or status first, '
                'then the lowest damage, AP and +0x1C/+0x20/+0x24 (a stale E+0x34 after a restore applies the vanilla '
                'spare row for at most one pulse), then the highest id'},
        'rowLayouts': {
            'beamInfo': [
                {'offset': '+0x00', 'type': 'BeamType', 'proof': 'CONFIRMED: read only by the loader (slot index); '
                    'no consumer reads it'},
                {'offset': '+0x04', 'name': 'radius', 'proof': 'CONFIRMED: -> E+0x4C; 0 = one ray (0x13BAF01), else '
                    'a sweep with this radius (0x13BB024)'},
                {'offset': '+0x08', 'name': 'range (beam length)', 'proof': 'CONFIRMED: -> E+0x44 (0x13B96A1); the '
                    'ray query length (0x13BAF87), the sweep end point (0x13BB0F6), the drawn-length clamp '
                    'min(hit, E+0x44) (0x13BD1C3). Copied at fire: a change applies to the next shot'},
                {'offset': '+0x0C', 'type': 'DamageInfoType', 'proof': 'CONFIRMED: -> E+0x34 -> InitHitInfo s+0x24'},
                {'offset': '+0x10/+0x14', 'name': 'falloff start / range', 'proof': 'CONFIRMED (beam damage research)'},
                {'offset': '+0x18/+0x1C', 'name': 'damage multiplier near / far', 'proof': 'CONFIRMED (beam damage '
                    'research)'},
                {'offset': '+0x20/+0x24', 'name': 'penetration multiplier near / far', 'proof': 'CONFIRMED (beam '
                    'damage research)'},
                {'offset': '+0x28', 'name': None, 'proof': '-> E+0x114 at fire; meaning UNKNOWN'},
                {'offset': '+0x2C', 'type': 'SurfaceImpactType', 'proof': '-> E+0x3C at fire'},
                {'offset': '+0x30', 'name': 'beam effect resource hash (u64)', 'proof': 'CONFIRMED: passed to the '
                    'world effect interface at fire (0x13B95AF..0x13B95DA, 0x13B9A04): a hash, not a pointer, so a '
                    'byte copy draws the same effect (package residency unchanged)'},
                {'offset': '+0x38', 'name': 'u64 hash (0 in row 6)', 'proof': 'no reader found in the beam path'},
                {'offset': '+0x40', 'name': 'resource hash (u64)', 'proof': 'read at fire (0x13B95E0)'},
                {'offset': '+0x48/+0x4C', 'name': '32-bit ids (audio leads)', 'proof': '-> E+0xF4 / E+0xF8 at fire'},
                {'offset': '+0x50', 'type': 'RaycastTemplate', 'proof': 're-read via the slot every update '
                    '(0x13BAF39)'},
                {'offset': '+0x54', 'name': '32-bit hash', 'proof': 're-read via the slot (0x13BB1BE)'},
                {'offset': '+0x58', 'type': 'HitEffectDamageType', 'proof': 're-read via the slot per hit -> '
                    'InitHitInfo r9 (event +0xC); == 0x11 drives the listeners'},
                {'offset': '+0x5C', 'name': 'float', 'proof': 'read at fire and with +0x60 in the hit processing'},
                {'offset': '+0x60', 'type': 'ExplosionType', 'proof': 're-read via the slot (0x13BD0FF): an '
                    'explosion on hit when non-zero'},
                {'offset': '+0x64', 'name': 'bit 0', 'proof': 're-read via the slot (0x13BB77E)'},
                {'offset': '+0x68', 'type': 'DangerLevel', 'proof': '-> E+0x38 at fire'},
                {'offset': '+0x6C', 'name': 'pulse bit', 'proof': 'CONFIRMED: -> E+0x160 (beam damage research)'}],
            'damageInfo': [
                {'offset': '+0x00', 'type': 'DamageInfoType', 'proof': 'CONFIRMED: read only by the loader'},
                {'offset': '+0x04/+0x08', 'name': 'standard / durable', 'proof': 'CONFIRMED: event +0x98 blend'},
                {'offset': '+0x0C..+0x18', 'name': 'AP lanes 1..4', 'proof': 'CONFIRMED: event +0x9C..+0xA8'},
                {'offset': '+0x1C/+0x20/+0x24', 'name': 'demolition / stagger / push (leads)', 'proof': 'CONFIRMED '
                    'reads: event +0xB0 / +0xAC / +0xB4; names are leads'},
                {'offset': '+0x28', 'type': 'ElementType', 'proof': 'CONFIRMED: event +4'},
                {'offset': '+0x2C..+0x4B', 'type': 'StatusEffectType x4 + value', 'proof': 'CONFIRMED: event '
                    '+0xC0..+0xDF'}]},
        'propagation': {
            'damageInfoId': 'STRONG: in the beam path the id lives in E+0x34 and the hit struct s+0x24; InitHitInfo '
                'reads s+0x24 once to index the array and overwrites the register (0x12A2408); no other read of '
                's+0x24 or copy into the event. DamageValues / ProduceDamage get the event (values), not the id.',
            'beamType': 'CONFIRMED local: E+0x18 comes from the firing machine\'s own BeamWeapon record (0x83FD50, '
                'beam damage research) and is used only to re-read the local row and for the local listeners.',
            'multiplayer': 'A peer without the mod never resolves the borrowed slots: its weapon records do not name '
                'k, and no hit event carries k or d. Which machine\'s beam hit decides enemy damage, and how the '
                'resulting damage is replicated, is UNKNOWN (not traced past ProduceDamage 0x129DD30). Solo only.'},
        'runtimeReproof': [
            'build: game.dll SHA-256 == %s and every pin of this file byte-identical; otherwise refuse '
                '(SPARE_TWIN_UNVERIFIED_BUILD, or a new code for slots)' % base.PROFILE_DLL_SHA,
            'slot k: [0x37C8250 + 8k] is the pointer captured at first apply (or, before the first apply, a pointer '
                'into private RW memory whose 0x70 bytes equal the pinned vanilla row k incl. key k); same for '
                '[0x37C60C0 + 8d] with 0x4C bytes and key d',
            'donor: slot 6 -> a row whose structural members (+0x30/+0x38/+0x40 hashes, +0x50, +0x54, +0x6C) equal '
                'the pinned Trident row 6; slot 508 -> a row with key 508',
            'live typed references: no record of the live BeamWeapon table (in place or Runtime-owned copy) names '
                'k; no live BeamInfo row other than the owned ones names d at +0xC; no live ProjectileInfo +0x3C, '
                'ExplosionInfo +4, ArcInfo +0x24, StatusEffectInfo +0x2C, Melee +12, Spray +200, Sticky +44, '
                'DamageZoneShield +4904, OrbitalAbility +476 names d',
            'ring: no live entry (E+0x110) with E+0x18 == k or E+0x34 == d before apply; before restore wait until '
                'none (one pulse)',
            'after apply: read back slot == owned copy and the copy bytes == the built bytes; on every later call the '
                'slot must still equal the owned copy (else a reload or another writer: CONFLICT, refuse)',
            'restore: slot := the captured vanilla pointer only while slot == owned copy; owned copies are never '
                'freed; the Runtime catalog must treat owned slots as owned (typed beam.* / damage.* writes to k or d '
                'refused)'],
        'unproven': [
            'Live: the owned rows in a running game (visual, range, damage, AP, demolition/stagger/push, status).',
            'Protected sections (.vm_sec, .winlice, .boot) and Lua cannot be scanned for slot readers or constant ids.',
            '0x129BE40 / 0x129BF00 / 0x129C110 / 0x129C300 and the two clear functions have no visible caller; if a '
                'protected-section caller runs them, the arrays are cleared / reloaded and the owned slots revert to '
                'vanilla (detectable, fail-safe).',
            'DamageInfo hit-struct sources not traced to a writer (copies or zeroing elsewhere): see '
                'constants.hitStruct entries marked unresolved; covered by the candidate-immediate filter only.',
            'Concurrency: the slot store is one aligned 8-byte write; that no reader runs on another thread during it '
                'is STRONG (same as the BeamWeapon table relocation).',
            'Multiplayer damage authority and replication (see propagation).',
            'Members +0x28, +0x38, +0x40, +0x48, +0x4C, +0x54, +0x5C, +0x64 of BeamInfo: readers pinned, meanings '
                'not named (copied unchanged from row 6).'],
    }
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    unresolved = sorted(h['call'] for h in hits['initHitInfoCallers'] + hits['wrapperCallers'] if h.get('unresolved'))
    if unresolved != sorted(HIT_STRUCT_NOTES):
        raise ValueError('unresolved hit-struct sources changed: %r' % unresolved)
    print(json.dumps({'pins': len(pins), 'sites': len(tables['sites']), 'functions': len(functions),
                      'leaves': leaves, 'arrayWrites': tables['arrayWrites'],
                      'beamTypesInCode': sorted(beam_constants), 'damageIdsInCode': sorted(damage_constants),
                      'spareBeamTypes': beam_order, 'spareDamageIds': len(spare_damage),
                      'damageOrderHead': damage_order[:capacity], 'capacity': capacity,
                      'unresolvedHitStruct': [h['call'] for h in hits['initHitInfoCallers'] + hits['wrapperCallers']
                                              if h.get('unresolved')]}, indent=1))


if __name__ == '__main__':
    main()
