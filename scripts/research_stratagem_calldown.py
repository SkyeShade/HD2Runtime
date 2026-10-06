"""A stratagem's calldown sequence (the arrow code), as the custom-stratagem P0 proof changes it
(docs/custom-stratagems.md). Read-only.

Proves on build F5FEE03DCFDB, from the game.dll image and the seven retained snapshots:

1. The row. Every StratagemInfo row (400 bytes, reached through the runtime table game+0x37CB600 by StratagemType)
   holds its calldown sequence as a pointer at +0x40 to an array of u32 directions and their count at +0x48 (+0x4C is
   zero padding). Every array lies inside the StratagemSettings allocation (one read-write private allocation, the
   buffer core/stratagem.lua captures), every value is 1..4, and the counts are 3..9.
2. The directions. 1 = Up, 2 = Right, 3 = Down, 4 = Left: the Orbital 120mm HE Barrage row (catalogue id 1063322614)
   holds 2, 2, 3, 4, 2, 3 (Right, Right, Down, Left, Right, Down, its in-game code), and every support weapon whose wiki
   page gives a stratagem code matches its row the same way.
3. The readers. Three game.dll functions read the sequence of a StratagemType through the same table, and each reads
   the row's live pointer and count every time (nothing is cached or hard-coded):
   * the calldown matcher (0x597FC0): for each slot, count = row +0x48; while the slot's progress (+0x1C) is below it,
     the input direction is compared with row +0x40[progress];
   * a copy helper (0xA106C0): *count_out = row +0x48, then memcpy(out, row +0x40, count x 4);
   * a copy-and-compare reader (0x66D8C0): memcpy of row +0x40 (count x 4) compared with an input buffer.
   The copies go into caller buffers, so a sequence must not be longer than the longest native one (9).
4. The P0 sequence Up, Up, Down, Down (1, 1, 3, 3) equals no row's sequence; three mission-objective rows start with it.
5. The HUD's stratagem list (evidence only: nothing here is a pin of the write). It is built when the game enters its
   Mission state (StateGame's enter handler 0xAC5D40 runs the HUD setup 0x12F0920, which builds the mission HUD when
   the state member +0xAC21C is 4) with 16 empty slots of 0x3760 bytes. Every frame it updates only while the local
   player's avatar exists: 0x606630 reads the player's avatar network id (player manager +0x3A8 + slot x 0x20, the
   member the Runtime reads) and resolves it through the network-id map (0xFD9BA0); without one the whole update
   returns. Each slot then takes its stratagem type from the player's per-peer stratagem record (game+0x347CE50,
   entries +0x188 x 0x30 from the record's +0x38) and copies the row's sequence through the copy helper every frame,
   but rebuilds its 10 arrow sprites (slot +0x2980, 0x158 apart; image region direction x 0.2) only when the slot's
   type or its displayed (scrambler) type changes. In the mission snapshots each slot's visible sprites spell exactly
   its row's code. So the arrows show the code the row held on the first frame the avatar existed, and a sequence
   written later is matched but not drawn.

Output: research/stratagem-calldown-F5FEE03DCFDB.json.
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

OUTPUT = ROOT / 'research/stratagem-calldown-F5FEE03DCFDB.json'
SNAPSHOTS = ['F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260927T155654Z.hd2snap',
    'F5FEE03DCFDB-20260927T160033Z.hd2snap', 'F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
BUFFER_RVA, TABLE, ENTRIES, STRIDE = 0x348E8F8, 0x37CB600, 150, 400
SEQUENCE, COUNT, PADDING = 0x40, 0x48, 0x4C
DIRECTIONS = {1: 'up', 2: 'right', 3: 'down', 4: 'left'}
WIKI = {'Up': 1, 'Right': 2, 'Down': 3, 'Left': 4}
MAX_LENGTH = 9
P0 = {'stratagem': 'Orbital 120mm HE Barrage', 'sequence': [1, 1, 3, 3]}
NATIVE_120MM = [2, 2, 3, 4, 2, 3]       # Right, Right, Down, Left, Right, Down: the in-game code
MEMCPY = 0x20988F0

PROOFS = {
    'matcher': [
        (0x598074, 'lea r8, [rip + {rip}]', TABLE, 'calldown matcher: the StratagemInfo table'),
        (0x59807B, 'mov r8, qword ptr [r8 + rax*8]', None, 'row = table[the slot\'s StratagemType]'),
        (0x59807F, 'mov eax, dword ptr [r15 + 0x1c]', None, 'the slot\'s progress (arrows matched so far)'),
        (0x598083, 'mov edx, dword ptr [r8 + 0x48]', None, 'row +0x48: the sequence count'),
        (0x598087, 'cmp eax, edx', None, 'progress below the count'),
        (0x59808D, 'mov rax, qword ptr [r8 + 0x40]', None, 'row +0x40: the sequence pointer'),
        (0x598091, 'cmp dword ptr [rax + rcx*4], edi', None, 'sequence[progress] == the input direction'),
        (0x59809E, 'mov rcx, qword ptr [r8 + 0x40]', None, 'row +0x40 again'),
    ],
    'copy': [
        (0xA107CA, 'lea rbx, [rip + {rip}]', TABLE, 'sequence copy helper: the StratagemInfo table'),
        (0xA107D1, 'mov rbx, qword ptr [rbx + rax*8]', None, 'row = table[type]'),
        (0xA107DD, 'mov r8d, dword ptr [rbx + 0x48]', None, 'row +0x48: the count'),
        (0xA107E1, 'mov rdx, qword ptr [rbx + 0x40]', None, 'row +0x40: the sequence'),
        (0xA107ED, 'mov dword ptr [rax], r8d', None, '*count_out = count'),
        (0xA107F0, 'shl r8, 2', None, 'count x 4 bytes'),
        (0xA107F4, 'call 0x20988f0', None, 'memcpy(out, sequence, count x 4)'),
    ],
    'compare': [
        (0x66E156, 'lea rcx, [rip + {rip}]', TABLE, 'copy-and-compare reader: the StratagemInfo table'),
        (0x66E15D, 'mov rdx, qword ptr [rcx + rax*8]', None, 'row = table[type]'),
        (0x66E161, 'mov edi, dword ptr [rdx + 0x48]', None, 'row +0x48: the count'),
        (0x66E169, 'mov rdx, qword ptr [rdx + 0x40]', None, 'row +0x40: the sequence'),
        (0x66E170, 'shl r8, 2', None, 'count x 4 bytes'),
        (0x66E174, 'call 0x20988f0', None, 'memcpy(out, sequence, count x 4)'),
    ],
}

# The HUD's stratagem list (point 5). Proven instruction bytes; not pins of the P0 write. The groups path, record,
# rebuild and sprite are the pins of the development HUD refresh (runtime/stratagem_hud.lua).
PLAYERS = 0x3326468         # domains/event_natives.lua players.global
HUD_SYSTEM = 0x346D538      # the HUD system global
CELL, IDENTITY = 0x23C6854, 0x3306AA8
RECORDS = 0x347CE50         # the per-peer stratagem records: {u64 peer, ...}, 0x1690 bytes, count at +0x2D200
RECORD_STRIDE, RECORD_COUNT, RECORD_ENTRIES, ENTRY_STRIDE, ENTRY_COUNT = 0x1690, 0x2D200, 0x38 + 0x188, 0x30, 0x38 + 0x788
HUD_SLOTS, HUD_SLOT_STRIDE, HUD_SLOT_INDEX, HUD_SLOT_TYPE, HUD_SLOT_SHOWN = 16, 0x3760, 0x3748, 0x374C, 0x3754
SPRITES, SPRITE_STRIDE, SPRITE_COUNT, SPRITE_REGION, SPRITE_VISIBLE, SPRITE_CELL = 0x2980, 0x158, 10, 0x114, 0x10, 0.2
SPRITE_DERIVED, SPRITE_SUBRECT, SPRITE_MASK = 0x124, 0x134, 0xB8
SPRITE_FLAG_PARENT, SPRITE_SIBLING, SPRITE_PARENT = 0xE0, 0xE8, 0xF0
HUD_SETUP, HUD_MISSION, HUD_PANEL, HUD_LIST, HUD_LIST_SLOT0 = 0x24E334, 0x24E340, 0x146DC0, 0x1040, 0x110
PATH_OFFSET = HUD_MISSION + HUD_PANEL + HUD_LIST + HUD_LIST_SLOT0
HUD_SLOT_SCRAMBLED, HUD_SLOT_TIMERS, HUD_SLOT_RELAYOUT = 0x3750, 0x370C, 0x36F1
HUD = {
    'construction': [
        (0xAC639E, 'call 0x12f0920', None, 'StateGame on_enter (the Mission state\'s enter handler) runs the HUD setup'),
        (0x12F0BEF, 'mov eax, dword ptr [r10 + 0xac21c]', None, 'HUD setup: the game state member'),
        (0x12F0C12, 'cmp eax, 4', None, 'state 4 (Mission) builds the mission HUD'),
        (0x12F0C2B, 'call 0x12e96d0', None, 'mission HUD construction (its stratagem list starts with empty slots)'),
        (0x18359A1, 'mov dword ptr [rcx + 0x374c], r13d', None, 'slot construction: stratagem type 0'),
    ],
    'avatarGate': [
        (0x1833651, 'call 0x606630', None, 'HUD update: the local player\'s avatar'),
        (0x183365D, 'cmp edi, dword ptr [rip + {rip}]', None, 'no avatar (the invalid entity id) ...'),
        (0x1833663, 'je 0x1833ba7', None, '... returns before the stratagem list is updated'),
        (0x606654, 'mov rdx, qword ptr [rip + {rip}]', PLAYERS, 'the player manager (players.global)'),
        (0x6066E6, 'shl rax, 5', None, 'player slot x 0x20'),
        (0x6066ED, 'mov edx, dword ptr [rax + rdx + 0x3a8]', None, 'the avatar network id (playerAvatars.avatarId)'),
        (0x6066F4, 'call 0xfd9ba0', None, 'resolved through the network-id map'),
    ],
    'slots': [
        (0x18339B2, 'call 0x1834a10', None, 'HUD update: the stratagem list'),
        (0x1834AE6, 'mov r9, qword ptr [rip + {rip}]', RECORDS, 'the per-peer stratagem records'),
        (0x1834D2F, 'mov r12d, 0x10', None, '16 slots'),
        (0x1834D59, 'call 0x1836510', None, 'each slot updated every frame'),
        (0x1834D68, 'add r14, 0x3760', None, 'slot stride 0x3760'),
        (0x183675C, 'mov edx, dword ptr [r10 + rcx*8 + 0x188]', None, 'the record entry\'s stratagem type'),
        (0x1836764, 'mov dword ptr [r15 + 0x374c], edx', None, 'slot +0x374C = that type'),
        (0x1836C8E, 'call 0xa106c0', None, 'the row\'s live sequence copied every frame (copy helper)'),
        (0x1836C93, 'mov dword ptr [r15 + 0x3754], eax', None, 'slot +0x3754 = the displayed (scrambler) type'),
    ],
    'redraw': [
        (0x1836CFE, 'mov eax, dword ptr [r15 + 0x374c]', None, 'this frame\'s type'),
        (0x1836D05, 'mov r9d, dword ptr [rbp - 0x30]', None, 'last frame\'s type'),
        (0x1836D09, 'cmp eax, r9d', None, 'type changed ...'),
        (0x1836D0C, 'jne 0x1836d31', None, '... rebuild the sprites'),
        (0x1836D0E, 'cmp ebx, edx', None, 'displayed type changed ...'),
        (0x1836D10, 'jne 0x1836d31', None, '... rebuild the sprites'),
        (0x1836D22, 'jbe 0x1836e23', None, 'otherwise (no scrambler animation) the copied sequence is not drawn'),
        (0x1836DA0, 'lea rcx, [r15 + 0x2980]', None, 'arrow sprites at slot +0x2980'),
        (0x1836DAF, 'imul r9, rax, 0x158', None, 'sprite stride 0x158'),
        (0x1836E0A, 'cmp r11d, 0xa', None, '10 sprites'),
    ],
    # The pinned path from a global to the list, used by runtime/stratagem_hud.lua (development).
    'path': [
        (0x12F53AF, 'mov rbp, qword ptr [rip + {rip}]', HUD_SYSTEM, 'the HUD system global'),
        (0x12F5875, 'mov rcx, rbp', None, 'the HUD system is the HUD update\'s object'),
        (0x12F5878, 'call 0x12f3c70', None, 'HUD update'),
        (0x12F4305, 'cmp r12d, 4', None, 'game mode 4 (Mission) ...'),
        (0x12F4314, 'lea rcx, [rdi + 0x24e340]', None, '... updates the mission HUD at HUD system +0x24E340'),
        (0x12F431E, 'call 0x12eb670', None, 'mission HUD update'),
        (0x12EB7D0, 'lea rcx, [rsi + 0x146dc0]', None, 'the stratagem panel at mission HUD +0x146DC0'),
        (0x12EB7E2, 'call 0x1833620', None, 'stratagem panel update'),
        (0x18339A4, 'lea rcx, [r14 + 0x1040]', None, 'the stratagem list at panel +0x1040'),
        (0x1834D28, 'lea r14, [rsi + 0x110]', None, 'slot 0 at list +0x110'),
        (0x12F13E3, 'mov byte ptr [rdi + 0x24e334], 1', None, 'HUD system +0x24E334 = 1: the HUD is set up'),
        (0x12F19A8, 'mov byte ptr [rbp + 0x24e334], 0', None, 'HUD system +0x24E334 = 0: torn down'),
        (0x1836582, 'mov r14d, dword ptr [r15 + 0x3748]', None, 'slot +0x3748: its index in the record'),
        (0x1836CB0, 'lea r10, [r15 + 0x3750]', None, 'slot +0x3750: scrambled'),
        (0x1836CA0, 'mov qword ptr [r15 + 0x370c], r12', None, 'slot +0x370C / +0x3710: scramble animation timers'),
        (0x1836CA7, 'movss xmm1, dword ptr [r15 + 0x3710]', None, 'slot +0x3710 read by the redraw gate'),
    ],
    'record': [
        (0x1834AED, 'mov ecx, dword ptr [r9 + 0x2d200]', None, 'the per-peer records\' count'),
        (0x1834B00, 'cmp qword ptr [rax], r8', None, 'record +0: the peer id'),
        (0x1834B07, 'add rax, 0x1690', None, 'record stride 0x1690'),
        (0x1834B41, 'lea r13, [r9 + 0x38]', None, 'the record\'s stratagem state at +0x38'),
        (0x1836589, 'cmp r14d, dword ptr [rdi + 0x788]', None, 'its entry count at +0x788'),
    ],
    'rebuild': [
        (0x1836D39, 'mov byte ptr [r15 + 0x36f1], 1', None, 'slot +0x36F1 = 1: the list lays the slot out again'),
        (0x1836D44, 'mov dword ptr [r15 + 0x3710], r12d', None, 'animation timer cleared'),
        (0x1836D7E, 'mov ecx, dword ptr [rbx]', None, 'the copied direction'),
        (0x1836D83, 'mov eax, 0xcccccccd', None, 'direction mod 5 ...'),
        (0x1836D9C, 'sub ecx, eax', None, '... = the cell'),
        (0x1836922, 'movss xmm10, dword ptr [rip + {rip}]', CELL, 'the cell width (0.2f)'),
        (0x1836DB6, 'mulss xmm1, xmm10', None, 'u0 = cell x width'),
        (0x1836DC7, 'addss xmm0, xmm10', None, 'u1 = u0 + width'),
        (0x1836D92, 'mov dword ptr [rbp - 0x4c], r12d', None, 'v0 = 0'),
        (0x1836D88, 'mov dword ptr [rsp + 0x74], 0x3f800000', None, 'v1 = 1.0'),
        (0x1836DA0, 'lea rcx, [r15 + 0x2980]', None, 'sprite array'),
        (0x1836DDA, 'call 0x143eef0', None, 'set the image region'),
        (0x1836DE9, 'setb dl', None, 'visible while index < count'),
        (0x1836DEF, 'call 0x14508e0', None, 'set the visibility'),
    ],
    'sprite': [
        (0x143EEFE, 'movss xmm0, dword ptr [rcx + 0x114]', None, 'region setter: unchanged region, nothing written'),
        (0x143EF42, 'mov qword ptr [rcx + 0x114], rdx', None, 'sprite +0x114: u0, v0'),
        (0x143EF49, 'mov qword ptr [rcx + 0x11c], r8', None, 'sprite +0x11C: u1, v1'),
        (0x143EF50, 'call 0x143f3c0', None, 'the derived region'),
        (0x143EF5F, 'or edx, 2', None, 'sprite flag 0x2: region changed'),
        (0x143EF64, 'mov rcx, qword ptr [rcx + 0xf0]', None, 'sprite +0xF0: layout parent'),
        (0x143EF7B, 'or edx, 8', None, 'each ancestor gets 0x8 until one has it'),
        (0x143EF80, 'mov rcx, qword ptr [rcx + 0xf0]', None, 'up the layout parents'),
        (0x143F3C0, 'movss xmm2, dword ptr [rcx + 0x134]', None, 'sprite +0x134: sub-rect x'),
        (0x143F3C8, 'ucomiss xmm2, dword ptr [rip + {rip}]', IDENTITY, 'identity sub-rect: the region is copied'),
        (0x143F3D3, 'movss xmm0, dword ptr [rcx + 0x138]', None, 'sub-rect y'),
        (0x143F3E6, 'movss xmm0, dword ptr [rcx + 0x13c]', None, 'sub-rect width'),
        (0x143F3F9, 'movss xmm0, dword ptr [rcx + 0x140]', None, 'sub-rect height'),
        (0x143F434, 'mulss xmm1, dword ptr [rcx + 0x11c]', None, 'width x u1 ...'),
        (0x143F43C, 'mulss xmm0, dword ptr [rcx + 0x114]', None, 'width x u0 ...'),
        (0x143F444, 'addss xmm1, xmm2', None, '... + x'),
        (0x143F448, 'addss xmm0, xmm2', None, '... + x'),
        (0x143F454, 'movss dword ptr [rcx + 0x12c], xmm1', None, 'sprite +0x12C: derived u1'),
        (0x143F464, 'movss dword ptr [rcx + 0x124], xmm0', None, 'sprite +0x124: derived u0'),
        (0x143F46F, 'mulss xmm0, dword ptr [rcx + 0x118]', None, 'height x v0 ...'),
        (0x143F477, 'mulss xmm2, dword ptr [rcx + 0x120]', None, 'height x v1 ...'),
        (0x143F47F, 'addss xmm0, xmm1', None, '... + y'),
        (0x143F483, 'addss xmm2, xmm1', None, '... + y'),
        (0x143F487, 'movss dword ptr [rcx + 0x128], xmm0', None, 'sprite +0x128: derived v0'),
        (0x143F48F, 'movss dword ptr [rcx + 0x130], xmm2', None, 'sprite +0x130: derived v1'),
        (0x14508F3, 'or r9d, 0x10', None, 'sprite flag 0x10: visible'),
        (0x145090B, 'or r9d, 0x20', None, 'flag 0x20: visibility changed'),
        (0x1450914, 'bts eax, 0xb', None, 'sprite +0xB8 bit 0x800 (unchanged: done)'),
        (0x145092E, 'mov rcx, qword ptr [rcx + 0xe0]', None, 'sprite +0xE0: flag parent (none on the arrows)'),
        (0x1450956, 'or r9d, 4', None, 'sprite flag 0x4: layout changed'),
        (0x145094F, 'mov rcx, qword ptr [r10 + 0xf0]', None, 'layout parent'),
        (0x1450966, 'jmp 0x144d200', None, 'ancestors ...'),
        (0x144D210, 'or edx, 4', None, '... get 0x4 until one has it'),
        (0x144D215, 'mov rcx, qword ptr [rcx + 0xf0]', None, 'up the layout parents'),
    ],
}
# Constants the rebuild reads, pinned as data: the cell width and the identity sub-rect (0, 0, 1, 1).
HUD_DATA = [(CELL, 'cdcc4c3e', 'the cell width 0.2f'),
    (IDENTITY, '00000000000000000000803f0000803f', 'the identity sub-rect (0, 0, 1, 1)')]

# The ship loadout (docs/custom-stratagems.md, "Selectable custom stratagem: research"). Leaving the loadout screen
# saves the chosen stratagems into the save store as {StratagemInfo +4 stable id, uses} pairs; the next session
# restores them by stable id with no availability check. 'saved' pins the store the selectable-stratagem proof reads
# (read-only); 'picker' records the loadout grid's availability rule (evidence only, nothing reads it at run time).
SAVE_STORE = 0x347CDD8      # the local save store
# Presentation members of a StratagemInfo row (localization ids and the image hash; values only, no pointers).
PRESENTATION_FIELDS = {'name': (0x28, 4), 'nameCased': (0x2C, 4), 'description': (0x30, 4), 'icon': (0xB0, 8)}
# Members whose localization id is in no registered English strings resource (the localization research of
# 2026-10-01 walked the game's registered list and every boot strings resource): as a presentation source they would
# display blank, so they are refused. Keyed by stable id.
PRESENTATION_UNRESOLVED = {73468749: ['nameCased']}     # LIFT-860 Hover Pack
SAVED_FLAG, SAVED_PAIRS, SAVED_PAIR_STRIDE, SAVED_PAIR_COUNT = 0x3C, 0x4C, 8, 32
LOADOUT = {
    'saved': [
        (0x175135F, 'mov rbx, qword ptr [rip + {rip}]', SAVE_STORE, 'loadout save: the save store'),
        (0x17513B2, 'lea rcx, [rbx + 0x4c]', None, 'store +0x4C: the stratagem pairs (cleared first)'),
        (0x17513C1, 'mov eax, dword ptr [rdi + 0x788]', None, "the loadout's stratagem count"),
        (0x17513C7, 'mov r8d, 0x20', None, 'at most 32'),
        (0x17513D9, 'lea rdx, [rbx + 0x50]', None, 'pair +4'),
        (0x1751402, 'mov eax, dword ptr [rax + 4]', None, "the slot type's row +4 (the stable id) ..."),
        (0x1751405, 'mov dword ptr [rdx - 4], eax', None, '... is pair +0'),
        (0x1751408, 'mov eax, dword ptr [rcx]', None, "the slot's uses (slot +4) ..."),
        (0x175140E, 'mov dword ptr [rdx], eax', None, '... is pair +4'),
        (0x1751410, 'add rdx, 8', None, 'pair stride 8'),
        (0x1751463, 'mov byte ptr [rbx + 0x3c], 1', None, 'store +0x3C = 1: a loadout is saved'),
        (0x17515E6, 'mov r14, qword ptr [rip + {rip}]', SAVE_STORE, 'loadout restore: the save store'),
        (0x17515ED, 'cmp byte ptr [r14 + 0x3c], dil', None, 'nothing saved: the default loadout'),
        (0x1752127, 'lea r10, [r14 + 0x4c]', None, 'the saved pairs'),
        (0x17521A3, 'cmp dword ptr [rcx + 4], eax', None,
            'restored as the type whose row +4 is the saved id (no availability check)'),
        (0x1752219, 'cmp r9d, 0x20', None, '32 pairs'),
    ],
    'presentation': [
        (0x66D54C, 'mov rax, qword ptr [r13 + r15*8 + 0x37cb600]', None, 'mission menu: the selected stratagem\'s row'),
        (0x66D559, 'mov edi, dword ptr [rax + 0x28]', None, 'mission menu name: row +0x28 (a localization id), read live'),
        (0x179D95D, 'mov esi, dword ptr [rbp + 0x28]', None, 'loadout details name: row +0x28 ...'),
        (0x179D962, 'mov esi, dword ptr [rbp + 0x2c]', None, '... or row +0x2C (the cased name)'),
        (0x189FBBA, 'mov edx, dword ptr [rbx + 4]', None, 'loadout details: the name widget is keyed by the stable id'),
        (0x189FBD0, 'mov edx, dword ptr [rbx + 0x30]', None, 'loadout details description: row +0x30 (a localization id)'),
        (0x1893645, 'lea rdi, [rip + {rip}]', TABLE, 'loadout slot: the StratagemInfo table'),
        (0x1893650, 'mov rdx, qword ptr [rdi + 0xb0]', None, 'loadout slot icon: row +0xB0 (a 64-bit image hash)'),
        (0x1893657, 'call 0x1450160', None, 'sets the image'),
        (0x183A053, 'mov edx, dword ptr [r9 + r12*8 + 0x188]', None, 'HUD slot widget: the record entry\'s type'),
        (0x183A05B, 'cmp edx, dword ptr [rsi + 0x14c8]', None,
            'the same type as last time: the slot visual is not rebuilt (cached per type)'),
        (0x183A1E5, 'mov rdx, qword ptr [r14 + 0xb0]', None, 'HUD slot icon: row +0xB0'),
        (0x183A352, 'mov dword ptr [rsi + 0x14c8], eax', None, 'the slot visual remembers its type'),
    ],
    'picker': [
        (0x146ED65, 'call 0x18d8710', None, 'choosing a slot rebuilds the loadout grid'),
        (0x18D8AA9, 'mov edi, 0x96', None, 'the grid: every stratagem type below 150 ...'),
        (0x18D8AB5, 'call 0x136fc20', None, '... through the availability check'),
        (0x136FC74, 'cmp dword ptr [r8 + rax*8 + 8], r11d', None,
            "an item-catalogue record whose +8 is the row's stable id"),
        (0x136FC89, 'test byte ptr [r10 + 0xc0], 1', None, 'row +0xC0 bit 0: enabled'),
        (0x136FC97, 'test byte ptr [r10 + 0x80], 2', None, 'row +0x80 bit 1: selectable'),
        (0x136FCC3, 'mov eax, dword ptr [rax + 0x14]', None, "the record's definition state (owned: 2 or 4) ..."),
        (0x136FD04, 'mov eax, dword ptr [rax + 0x14]', None, "... or its parent item's"),
    ],
}


def catalogue():
    """Stratagem name -> catalogue root id (domains/stratagem_authoring.lua), and the native type names."""
    text = (ROOT / 'domains/stratagem_authoring.lua').read_text(encoding='utf-8')
    ids = {}
    for match in re.finditer(r'\["name"\]="([^"]+)",\["family"\]="[^"]*",\["rootResolution"\]="[^"]*",'
            r'\["root"\]=\{\["id"\]=(\d+),\["package"\]="([^"]+)"', text):
        ids[match.group(1)] = {'id': int(match.group(2)), 'package': match.group(3)}
    icons = json.loads((ROOT / 'research/stratagem-icons-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    names = {item['value']: item['name'] for item in icons['types']}
    return ids, names


def wiki_codes():
    data = json.loads((ROOT / 'data/wiki_support_weapons.json').read_text(encoding='utf-8'))
    items = data if isinstance(data, list) else data.get('weapons') or list(data.values())
    out = {}
    for item in items:
        code = ((item.get('normalizedFields') or {}).get('stratagem') or {}).get('code')
        if code:
            out[item['name']] = [WIKI[part.strip()] for part in code.split('>')]
    return out


def observe(name: str) -> dict:
    mem = base.Mem(name)
    buffer = mem.u64(mem.game + BUFFER_RVA)
    region = mem.s.region(buffer)
    allocation = {'base': region['allocation_base'], 'size': region['size'], 'protect': region['protect'],
        'type': region['type']}
    rows = {}
    for kind in range(ENTRIES):
        row = mem.ptr(mem.game + TABLE + kind * 8)
        if not row:
            continue
        data = mem.read(row, STRIDE)
        pointer, count, padding = struct.unpack_from('<QII', data, SEQUENCE)
        sequence = list(struct.unpack('<%dI' % count, mem.read(pointer, 4 * count))) if 0 < count <= 64 else None
        rows[kind] = {'type': struct.unpack_from('<I', data, 0)[0], 'id': struct.unpack_from('<I', data, 4)[0],
            'rowOffset': row - buffer, 'sequenceOffset': pointer - buffer, 'count': count, 'padding': padding,
            'sequence': sequence,
            'inside': buffer <= row and row + STRIDE <= buffer + region['size']
                and buffer <= pointer and pointer + 4 * count <= buffer + region['size']}
    mem.close()
    return {'snapshot': name, 'allocation': allocation, 'rows': rows}


def observe_presentation(name: str) -> dict:
    """{type: {id, name, nameCased, description, icon (hex)}} for every StratagemInfo row of a snapshot."""
    mem = base.Mem(name)
    out = {}
    for kind in range(1, ENTRIES):
        row = mem.ptr(mem.game + TABLE + kind * 8)
        if not row:
            continue
        data = mem.read(row, STRIDE)
        values = {'id': struct.unpack_from('<I', data, 4)[0]}
        for field, (offset, width) in PRESENTATION_FIELDS.items():
            raw = data[offset:offset + width]
            values[field] = '0x%016X' % struct.unpack('<Q', raw)[0] if width == 8 else struct.unpack('<I', raw)[0]
        out[kind] = values
    mem.close()
    return out


def observe_saved(name: str, rows: dict) -> dict:
    """The saved ship loadout: the store's saved flag and its {stable id, uses} pairs, each with its current type."""
    mem = base.Mem(name)
    store = mem.ptr(mem.game + SAVE_STORE)
    by_id = {row['id']: kind for kind, row in rows.items()}
    flag = mem.read(store + SAVED_FLAG, 1)
    pairs = []
    for index in range(SAVED_PAIR_COUNT):
        at = store + SAVED_PAIRS + index * SAVED_PAIR_STRIDE
        stable, uses = mem.u32(at), mem.u32(at + 4)
        if stable or uses:
            pairs.append({'id': stable, 'uses': uses, 'type': by_id.get(stable)})
    mem.close()
    return {'snapshot': name, 'saved': bool(flag and flag[0] == 1), 'pairs': pairs}


LOCAL_USER, LOCAL_PEER = 0x347CEF0, 0xB398     # domains/event_natives.lua players.localUser / localPeer
AVATAR_ID, AVATAR_STRIDE, NO_AVATAR = 0x3A8, 0x20, 0x7FFF


def observe_hud(name: str, rows: dict) -> dict:
    """The local player's stratagem record and the HUD's stratagem list in one snapshot. The list is found by its 16
    consecutive slot indices (0..15 at +0x3748, 0x3760 apart) whose types are the record's entries in order; each
    slot's visible arrow sprites are decoded (image region x / 0.2) and compared with its row's live code."""
    import numpy as np
    mem = base.Mem(name)
    peer = mem.u64(mem.ptr(mem.game + LOCAL_USER) + LOCAL_PEER)
    records = mem.ptr(mem.game + RECORDS)
    entries = None
    for index in range(mem.u32(records + RECORD_COUNT) or 0):
        record = records + index * RECORD_STRIDE
        if mem.u64(record) == peer:
            count = mem.u32(record + ENTRY_COUNT)
            entries = [mem.u32(record + RECORD_ENTRIES + i * ENTRY_STRIDE) for i in range(count)]
    players = mem.ptr(mem.game + PLAYERS)
    avatar = mem.u32(players + AVATAR_ID) if players else None      # slot 0: the solo host
    lists, step = [], HUD_SLOT_STRIDE // 4
    for region in mem.s.regions:
        if region['status'] != 1 or region['type'] != 0x20000 or region['protect'] != 0x04 \
                or region['size'] < HUD_SLOTS * HUD_SLOT_STRIDE:
            continue
        mem.s.handle.seek(region['data_offset'])
        data = mem.s.handle.read(region['size'])
        values = np.frombuffer(data[:len(data) // 4 * 4], dtype='<u4')
        ones = np.nonzero(values == 1)[0]
        ones = ones[(ones >= step) & (ones + (HUD_SLOTS - 2) * step < len(values))]
        for one in ones[values[ones - step] == 0]:
            first = int(one) - step
            if all(values[first + k * step] == k for k in range(HUD_SLOTS)):
                address = region['base'] + first * 4 - HUD_SLOT_INDEX
                types = [mem.u32(address + k * HUD_SLOT_STRIDE + HUD_SLOT_TYPE) for k in range(HUD_SLOTS)]
                if entries and types[:len(entries)] == entries and not any(types[len(entries):]):
                    lists.append(address)
    if len(lists) != 1:
        raise ValueError('the HUD stratagem list is absent or ambiguous in %s: %r' % (name, lists))
    # The pinned path lands on the same list: [HUD system] + mission HUD + panel + list + slot 0.
    hud = mem.ptr(mem.game + HUD_SYSTEM)
    allocation = mem.s.region(hud)
    path = hud + PATH_OFFSET
    if path != lists[0]:
        raise ValueError('the pinned HUD path misses the list in %s' % name)

    def f32(value):
        return struct.unpack('<f', struct.pack('<f', value))[0]

    def word(address):
        return struct.unpack('<f', mem.read(address, 4))[0]

    width = struct.unpack('<f', bytes.fromhex('cdcc4c3e'))[0]
    slots, formula, structure = [], 0, []
    for k in range(len(entries)):
        slot = lists[0] + k * HUD_SLOT_STRIDE
        kind, shown = mem.u32(slot + HUD_SLOT_TYPE), mem.u32(slot + HUD_SLOT_SHOWN)
        sprites, container = [], mem.u64(slot + SPRITES + SPRITE_PARENT)
        for i in range(SPRITE_COUNT):
            sprite = slot + SPRITES + i * SPRITE_STRIDE
            # Every sprite: no flag parent, the next sprite as sibling, the slot's row container as layout parent.
            if mem.u64(sprite + SPRITE_FLAG_PARENT) != 0 or mem.u64(sprite + SPRITE_PARENT) != container \
                    or mem.u64(sprite + SPRITE_SIBLING) != (sprite + SPRITE_STRIDE if i < SPRITE_COUNT - 1 else 0):
                structure.append((k, i))
            if mem.u32(sprite) & SPRITE_VISIBLE:
                cell = round(word(sprite + SPRITE_REGION) / SPRITE_CELL)
                sprites.append(cell)
                # The image region and the derived region are exactly the game's float32 formula.
                u0 = f32(cell * width)
                region = (u0, 0.0, f32(u0 + width), 1.0)
                sub = [word(sprite + SPRITE_SUBRECT + 4 * j) for j in range(4)]
                derived = (f32(f32(sub[2] * region[0]) + sub[0]), f32(f32(sub[3] * region[1]) + sub[1]),
                    f32(f32(sub[2] * region[2]) + sub[0]), f32(f32(sub[3] * region[3]) + sub[1]))
                if tuple(word(sprite + SPRITE_REGION + 4 * j) for j in range(4)) != region \
                        or tuple(word(sprite + SPRITE_DERIVED + 4 * j) for j in range(4)) != derived:
                    raise ValueError('a sprite region differs from the formula in %s: slot %d sprite %d' % (name, k, i))
                formula += 1
        # The layout parents from the row container up: inside the HUD allocation, through the slot and the list.
        chain, at = [], container
        while at and len(chain) < 32:
            chain.append(at)
            at = mem.u64(at + SPRITE_PARENT)
        if slot not in chain or lists[0] - HUD_LIST_SLOT0 not in chain or at or any(
                not allocation['allocation_base'] <= item < allocation['allocation_base'] + allocation['size']
                for item in chain):
            structure.append((k, 'chain'))
        slots.append({'slot': k, 'type': kind, 'displayedType': shown, 'sprites': sprites,
            'row': rows[kind]['sequence'], 'match': sprites == rows[kind]['sequence'], 'ancestors': len(chain)})
    if structure:
        raise ValueError('the sprite structure differs in %s: %r' % (name, structure[:8]))
    setup = mem.read(hud + HUD_SETUP, 1)[0]
    mem.close()
    return {'snapshot': name, 'localPeer': '%016X' % peer, 'avatarNetworkId': avatar, 'recordTypes': entries,
        'listSlotsFound': len(lists), 'pathOffset': PATH_OFFSET, 'hudSetUp': setup,
        'spritesMatchingFormula': formula, 'slots': slots}


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[4])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    hud_proofs = {group: [image.prove(*row) for row in rows] for group, rows in HUD.items()}
    hud_data = []
    for rva, hexed, role in HUD_DATA:
        if data[rva:rva + len(hexed) // 2].hex() != hexed:
            raise ValueError('HUD constant at %x changed' % rva)
        hud_data.append({'rva': rva, 'bytes': hexed, 'asm': 'data', 'role': role})
    hud_pins = [p for rows in hud_proofs.values() for p in rows] + hud_data
    hud_relocation = {name: base.verify_pins_live(name, hud_pins, []) for name in SNAPSHOTS}
    if any(hud_relocation.values()):
        raise ValueError('pinned HUD bytes differ in a snapshot: %r' % hud_relocation)
    loadout_proofs = {group: [image.prove(*row) for row in rows] for group, rows in LOADOUT.items()
        if group != 'presentation'}
    presentation_proofs = [image.prove(*row) for row in LOADOUT['presentation']]
    presentation_relocation = {name: base.verify_pins_live(name, presentation_proofs, []) for name in SNAPSHOTS}
    if any(presentation_relocation.values()):
        raise ValueError('pinned presentation bytes differ in a snapshot: %r' % presentation_relocation)
    loadout_pins = [p for rows in loadout_proofs.values() for p in rows]
    loadout_relocation = {name: base.verify_pins_live(name, loadout_pins, []) for name in SNAPSHOTS}
    if any(loadout_relocation.values()):
        raise ValueError('pinned loadout bytes differ in a snapshot: %r' % loadout_relocation)

    ids, native_names = catalogue()
    target = ids[P0['stratagem']]
    observations = [observe(name) for name in SNAPSHOTS]
    summaries, p0_rows = [], []
    for observation in observations:
        rows = observation['rows']
        allocation = observation['allocation']
        if allocation['protect'] != 0x04 or allocation['type'] != 0x20000:
            raise ValueError('the StratagemSettings allocation is not private read-write in %s' % observation['snapshot'])
        for kind, row in rows.items():
            if row['type'] != kind or not row['inside'] or row['padding'] != 0 or not row['sequence'] \
                    or not 3 <= row['count'] <= MAX_LENGTH or any(v not in DIRECTIONS for v in row['sequence']):
                raise ValueError('an unexpected calldown sequence in %s: type %d %r' % (observation['snapshot'], kind, row))
        matches = [kind for kind, row in rows.items() if row['id'] == target['id']]
        if len(matches) != 1:
            raise ValueError('the 120mm row is absent or ambiguous')
        row = rows[matches[0]]
        if row['sequence'] != NATIVE_120MM:
            raise ValueError('the 120mm sequence is not its in-game code: %r' % row['sequence'])
        p0_rows.append({'snapshot': observation['snapshot'], 'type': row['type'], 'rowOffset': row['rowOffset'],
            'sequenceOffset': row['sequenceOffset'], 'count': row['count'], 'sequence': row['sequence']})
        lengths = {}
        for item in rows.values():
            lengths[item['count']] = lengths.get(item['count'], 0) + 1
        summaries.append({'snapshot': observation['snapshot'], 'rows': len(rows), 'allocation': {
            'size': allocation['size'], 'protect': allocation['protect'], 'type': allocation['type']},
            'lengths': {str(k): v for k, v in sorted(lengths.items())}})
    if len({(r['type'], r['rowOffset'], r['sequenceOffset']) for r in p0_rows}) != 1:
        raise ValueError('the 120mm row moved between snapshots')

    # The direction mapping, independently: the support weapons' wiki codes.
    rows = observations[4]['rows']
    by_id = {row['id']: row for row in rows.values()}
    wiki, compared, mismatched = wiki_codes(), [], []
    for name, code in sorted(wiki.items()):
        entry = ids.get(name)
        row = entry and by_id.get(entry['id'])
        if row:
            compared.append(name)
            if row['sequence'] != code:
                mismatched.append({'name': name, 'wiki': code, 'row': row['sequence']})
    if mismatched or len(compared) < 10:
        raise ValueError('wiki codes disagree with the rows: %r (%d compared)' % (mismatched, len(compared)))

    # The P0 sequence against every row: equal, a prefix of a longer code, or a shorter code that is its prefix.
    overlaps, identical = [], {}
    for kind, row in sorted(rows.items()):
        sequence, wanted = row['sequence'], P0['sequence']
        relation = 'equal' if sequence == wanted else 'starts_with_p0' if sequence[:len(wanted)] == wanted \
            else 'prefix_of_p0' if wanted[:len(sequence)] == sequence else None
        if relation:
            overlaps.append({'type': kind, 'nativeName': native_names.get(kind), 'id': row['id'],
                'sequence': sequence, 'relation': relation})
        identical.setdefault(tuple(sequence), []).append(kind)
    if any(item['relation'] != 'starts_with_p0' for item in overlaps):
        raise ValueError('the P0 sequence equals or extends a native code: %r' % overlaps)

    # Every row's native code by its stable id (StratagemType numbers drift between builds; the id does not), the
    # same in all seven snapshots: the baselines of stratagem.calldown_code.
    native_codes = {}
    for observation in observations:
        for row in observation['rows'].values():
            prior = native_codes.setdefault(row['id'], row['sequence'])
            if prior != row['sequence']:
                raise ValueError('row %d holds different codes between snapshots' % row['id'])
    if len(native_codes) != len(rows):
        raise ValueError('StratagemInfo ids are not unique')
    catalogued = {entry['id']: name for name, entry in ids.items()}
    native_rows = [{'id': row['id'], 'type': kind, 'nativeTypeName': native_names.get(kind),
        'sequence': row['sequence'], 'catalogued': catalogued.get(row['id'])} for kind, row in sorted(rows.items())]

    # The HUD's stratagem list in the mission snapshots that have a Helldiver: each slot draws its row's code.
    hud_snapshots = []
    for observation in observations:
        if 'mission-host' in observation['snapshot']:
            hud = observe_hud(observation['snapshot'], observation['rows'])
            if hud['avatarNetworkId'] in (None, NO_AVATAR) or not all(s['match'] for s in hud['slots']) \
                    or any(s['displayedType'] != s['type'] for s in hud['slots']):
                raise ValueError('the HUD stratagem list does not draw its rows in %s: %r' % (hud['snapshot'], hud))
            hud_snapshots.append(hud)

    # The saved ship loadout in every snapshot, by stable id; in the mission snapshots each saved stratagem is in the
    # local player's record, as the same type.
    saved_snapshots = []
    for observation in observations:
        saved = observe_saved(observation['snapshot'], observation['rows'])
        hud = next((h for h in hud_snapshots if h['snapshot'] == observation['snapshot']), None)
        if hud:
            saved['inRecord'] = [entry['type'] in hud['recordTypes'] for entry in saved['pairs']]
            if not all(saved['inRecord']):
                raise ValueError('a saved stratagem is not in the mission record: %r' % saved)
        if not saved['saved'] or not 1 <= len(saved['pairs']) <= 4 or any(e['type'] is None for e in saved['pairs']):
            raise ValueError('an unexpected saved loadout: %r' % saved)
        saved_snapshots.append(saved)

    # Every row's presentation values by stable id, identical in every snapshot: the reviewed native values.
    presentation_rows = {}
    for observation in observations:
        for kind, values in observe_presentation(observation['snapshot']).items():
            prior = presentation_rows.setdefault(values['id'], dict(values, type=kind))
            if any(prior[key] != values[key] for key in PRESENTATION_FIELDS):
                raise ValueError('row %d presentation differs between snapshots' % values['id'])
    presentation = {'fields': {name: {'offset': offset, 'width': width}
            for name, (offset, width) in PRESENTATION_FIELDS.items()},
        'proofs': presentation_proofs, 'pinnedBytesMismatchPerSnapshot': presentation_relocation,
        'rows': [dict(item, nativeTypeName=native_names.get(item['type']))
            for item in sorted(presentation_rows.values(), key=lambda item: item['type'])],
        'unresolvedSources': [{'id': key, 'members': members,
            'reason': 'its localization id is in no registered English strings resource: it would display blank'}
            for key, members in sorted(PRESENTATION_UNRESOLVED.items())],
        'consequence': 'The loadout screen (details name and description, slot icons) and the in-mission menu (name '
            'live, slot icon) read these members from the row. The HUD slot widget rebuilds its visual only when '
            'the slot\'s type changes, so a presentation written after the slot was built is not drawn until the '
            'next mission: write it before the mission.',
        'excluded': {'+0x10, +0x18, +0x20': 'string pointers (debug name, Acquisitions title and description keys): '
                'copying them would share another row\'s strings',
            '+0x34, +0x38': 'no reader found; +0x38 is one value per stratagem family',
            '+0xB8': 'category (0 to 4): also the loadout tab, the HUD colour set and the details category label',
            '+0xD4': 'beacon colour index (1 to 3, no bounds check in the game)'}}

    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'table': {'rva': TABLE, 'entries': ENTRIES, 'bufferRva': BUFFER_RVA, 'stride': STRIDE},
        'members': {'sequence': {'offset': SEQUENCE, 'storage': 'pointer to u32[count]'},
            'count': {'offset': COUNT, 'storage': 'u32'}, 'padding': {'offset': PADDING, 'storage': 'u32 (0)'}},
        'directions': {str(k): v for k, v in DIRECTIONS.items()}, 'maxLength': MAX_LENGTH,
        'memcpy': MEMCPY, 'proofs': proofs, 'pinnedBytesMismatchPerSnapshot': relocation,
        'p0': {'stratagem': P0['stratagem'], 'id': target['id'], 'package': target['package'],
            'nativeType': p0_rows[0]['type'], 'nativeTypeName': native_names.get(p0_rows[0]['type']),
            'nativeSequence': NATIVE_120MM, 'sequence': P0['sequence'], 'rows': p0_rows, 'overlaps': overlaps},
        'wikiCodes': {'compared': compared, 'mismatched': mismatched},
        'identicalNativeCodes': [{'sequence': list(k), 'types': v} for k, v in identical.items() if len(v) > 1],
        'nativeRows': native_rows,
        'snapshots': summaries,
        'hud': {'global': HUD_SYSTEM, 'setUp': HUD_SETUP, 'missionHud': HUD_MISSION, 'panel': HUD_PANEL,
            'list': HUD_LIST, 'slot0': HUD_LIST_SLOT0, 'pathOffset': PATH_OFFSET,
            'records': {'rva': RECORDS, 'stride': RECORD_STRIDE, 'count': RECORD_COUNT, 'key': 'u64 peer id',
                'entries': RECORD_ENTRIES, 'entryStride': ENTRY_STRIDE, 'entryCount': ENTRY_COUNT},
            'slots': {'count': HUD_SLOTS, 'stride': HUD_SLOT_STRIDE, 'index': HUD_SLOT_INDEX, 'type': HUD_SLOT_TYPE,
                'displayedType': HUD_SLOT_SHOWN, 'scrambled': HUD_SLOT_SCRAMBLED, 'timers': HUD_SLOT_TIMERS,
                'relayout': HUD_SLOT_RELAYOUT},
            'sprites': {'offset': SPRITES, 'stride': SPRITE_STRIDE, 'count': SPRITE_COUNT, 'region': SPRITE_REGION,
                'derived': SPRITE_DERIVED, 'subrect': SPRITE_SUBRECT, 'mask': SPRITE_MASK,
                'flagParent': SPRITE_FLAG_PARENT, 'sibling': SPRITE_SIBLING, 'parent': SPRITE_PARENT,
                'visibleBit': SPRITE_VISIBLE, 'cell': SPRITE_CELL, 'cellBytes': 'cdcc4c3e',
                'bits': {'regionChanged': 2, 'layoutChanged': 4, 'childChanged': 8, 'visible': 16,
                    'visibilityChanged': 32, 'maskBit': 2048}},
            'proofs': hud_proofs, 'data': hud_data, 'pinnedBytesMismatchPerSnapshot': hud_relocation,
            'snapshots': hud_snapshots,
            'consequence': 'The arrows show the code the row held on the first frame the local avatar existed; a '
                'sequence written later is matched but not drawn until the slot type changes. The game redraws a '
                'slot by writing, per sprite, its image region (+0x114) and derived region (+0x124, from its '
                'sub-rect +0x134) with flag 0x2, and its visibility (flag 0x10, 0x20, +0xB8 bit 0x800, flag 0x4); '
                'each ancestor up the +0xF0 layout parents gets 0x8 and 0x4 until one already has it; and the slot '
                'gets +0x36F1 = 1 so the list lays it out again.'},
        'presentation': presentation,
        'loadout': {'store': SAVE_STORE, 'savedFlag': SAVED_FLAG, 'pairs': SAVED_PAIRS, 'pairStride': SAVED_PAIR_STRIDE,
            'pairCount': SAVED_PAIR_COUNT, 'pair': {'id': 0, 'uses': 4},
            'proofs': loadout_proofs, 'pinnedBytesMismatchPerSnapshot': loadout_relocation, 'snapshots': saved_snapshots,
            'consequence': 'Leaving the loadout screen saves the chosen stratagems as StratagemInfo stable ids; the '
                'next session restores them by stable id without checking that they are still available. The loadout '
                'grid lists a type only when its row is enabled (+0xC0 bit 0) and selectable (+0x80 bit 1) and an '
                'item-catalogue record carrying its stable id is owned. In a mission the chosen stratagems are the '
                "local player's record entries, by numeric type."},
        'unproven': ['Whether the renderer draws a slot redrawn by data writes that mirror the game own writes (the '
            'development HUD refresh; only a live test shows it).',
            'Whether a language change rebuilds the mission HUD (0x12FF050 reads text_language, then 0xB4FD90 calls the '
            'HUD setup 0x12F0920): read statically; live-confirmed on 2026-10-01 that a language change and back '
            'redraws the custom arrows.',
            'How the matcher resolves two equipped stratagems whose codes are equal or one extends the other.',
            'Whether every caller of the copy helpers has room for more than 9 entries: a sequence is kept at most 9.',
            'What other players see: code entry is local, and the row is changed on this machine only.'],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'p0': {k: report['p0'][k] for k in ('id', 'nativeType', 'nativeTypeName', 'nativeSequence')},
        'overlaps': overlaps, 'wikiCompared': len(compared), 'snapshots': len(summaries)}, indent=1))


if __name__ == '__main__':
    main()
