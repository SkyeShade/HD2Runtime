"""Beacon redirect and delivery semantics (research/docs/beacon-redirect-F5FEE03DCFDB.md): the facts a per-call beacon
redirect would rest on, which the live BeaconProbe (proof/BeaconProbe) cannot see by itself. Read-only, offline: the
game.dll image and the seven retained snapshots of build F5FEE03DCFDB. Nothing is written.

Proves [C] and observes [O]:

1. The manager path. The beacon component manager is systems + 0x1380 and systems = the component world + 0x40
   (0xFDAF4B -> 0x571250 -> 0x5712FB); the component world is [game+0x346BF98], the bombardment research's root. In
   all seven snapshots the path reads a plausible manager (an entity map of 128, no beacon) [O].
2. Replication. The beacon init copies each value into a creation buffer and registers THAT copy ({hash, kind,
   pointer}); afterwards the update marks only the countdown (0x6109F766) and the activation flag (0x44F85B36) dirty
   (0xFD97E0). The type (0xC2EB5C15) is never re-sent: a later change of +0xC stays on the machine that has it. The
   update skips instances whose state +0x8E0 is 2 (presumably remote copies) [I].
3. Every reader of a beacon's type before activation: the per-frame loop (0x6AB4A3: the row's +0x104 bit 0x200 chooses
   the drop-position geometry for the beacon's visual nodes), the activation loop (0x6AB84A; type 0x94 special-cased),
   and the activation itself (0x6ABC14).
4. Delivery semantics: the call-in TABLE entry (+8, its own copy of the type) drives the per-second re-targeting of
   rows with +0x170 bit 1 (0x6A1405-0x6A147C -> 0x69FCB0: an entity's current position, ground ray): set for every
   hellpod and mission type, clear for every orbital and Eagle [O]. The beacon's +0xC is not read there.
5. The beacon colour: the marker component ([game+0x3326A58], 0x2C-byte elements, its own type at +0x28) takes its
   colour from the row's category +0xB8 when it is drawn (0x13D1557): 0 red (1, 0.28, 0.32), 2 blue (0.44, 0.96, 1.0),
   else yellow (1, 0.91, 0). The category per family [O]: 0 orbitals and Eagles, 2 support weapons, vehicles and most
   backpacks, 3 sentries, emplacements and mines, 4 mission. No per-instance colour field; no gameplay reader of
   +0xB8 found (the readers are UI, the call voice line and this marker).
6. Eagle Rearm. The fleet is the record's entries whose row links Eagle Rearm (+0xC8 == 0x31, 0x66E696); the rearm
   prompt needs every one of them out of uses (0x66D3D0); the post-call branch first requires Eagle Rearm in the
   record (0x670D50); the record build grants it only from rows that link it (0x6AE4B1).
7. Call-in timing (after the BeaconRedirectProof 0.1.0 live run). The beacon init (0x6AE7D5 -> 0x6A5B70) computes both
   timers ONCE, from the type in the spawn parameters (the carrier's): threshold = [delivery kinds 1 and 5: the orbital
   travel beyond the call-in (0x10026A0)] + the delivery time (0x6ADED0: a pod's fall, an aircraft's flight, or the
   bombardment record's duration) + the row's linger +0x60; countdown = threshold + the call-in (0x879900: the row's
   +0x54, the player's upgrade settings 0xB5FBF0, the active mission effects 0x8F, never negative; type 0x94 alone
   can have it zeroed, 0x6A5C6E). Every update with state
   subtracts the frame time; the activation is the crossing (before >= threshold > after); below zero the beacon is
   removed (0xFDC310). So the call-in delay is countdown - threshold and the beacon's life after activation is the
   threshold; both stay the carrier's after a type redirect. The threshold is replicated at creation only, the
   countdown on every update. A further wave adds its delay to the countdown and clears "activated" (0x6AD9A3).
   The rows' call-in members per catalogued stratagem are observed [O].
8. The dispatcher's own record. The activation passes state + 0x40 to the dispatcher (0x6ABB89), which records there:
   the payload (state +0x418), "called" (+0x420) and the type it was given (+0x424) for every delivery but the Eagle's
   (0x6AC007), per wave the type (+0x814), 10 at +0x8D8 right before the spawn request (0xFD9710), and the waves
   spawned in the element's +0x2C. Read after an activation, it shows what the dispatcher actually requested.
9. The timers' consumers. A sweep of the beacon component's code (timing_accesses) finds every access of an element's
   countdown or threshold: the init and its creation-message copies, the update (subtraction, crossing, removal), the
   type-0x94 path, a further wave, whole-element moves, and one accessor with no static reference. Nothing outside the
   beacon component reads them: the HUD's inbound time is the mission record's.
10. The barrage. Its start (0x8518F0) reads only its bombardment record (start delay +0x80, plus a time for its entity
   when the record's +0x3C is set, 0xA0AF50), its replicated block and its spawn entity. Its instance (0x70 bytes at
   manager +0x58) counts shells fired (+0x0), shells left in the salvo (+0x4) and salvos left (+0xC); once nothing is
   left its own 5 s timer (+0x50) removes it. So the beacon's timers decide when the dispatcher spawns the barrage and
   how long the beacon itself lives, not the barrage's schedule.

Output: research/beacon-redirect-F5FEE03DCFDB.json.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS, TABLE, RECORDS  # noqa: E402
from research_stratagem_slot_conversion import catalogue_roots  # noqa: E402

OUTPUT = ROOT / 'research/beacon-redirect-F5FEE03DCFDB.json'
WORLD, SYSTEMS, BEACONS = 0x346BF98, 0x40, 0x1380
MARKERS = 0x3326A58
COLOURS = {'offensive': 0x21D4790, 'supply': 0x21D4770, 'other': 0x21D4760}
MISSION_SNAPSHOT = 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap'

GAME = {
    'managerPath': [
        (0xFDAF4B, 'lea rcx, [rdi + 0x40]', None, 'systems = the component world + 0x40 ...'),
        (0xFDAF4F, 'call 0x571250', None, '... updated'),
        (0x5712FB, 'lea rcx, [rdi + 0x1380]', None, 'the beacon manager = systems + 0x1380 ...'),
        (0x571305, 'call 0x6ab3e0', None, '... its update'),
    ],
    'managerLayout': [
        (0x6AB42C, 'mov eax, dword ptr [rsi + 0x34]', None, 'the instance count +0x34'),
        (0x6AB490, 'mov rax, qword ptr [rsi + 0x78]', None, 'the elements +0x78 (0x40 each)'),
        (0x6AB812, 'cmp dword ptr [rsi + 0x38], 0', None, 'the count with state +0x38'),
        (0x6AB830, 'mov r12, qword ptr [rsi + 0x78]', None, 'the elements (activation loop)'),
        (0x6AB837, 'imul r13, r15, 0x8e8', None, 'the state stride 0x8E8 ...'),
        (0x6AB842, 'add r13, qword ptr [rsi + 0x68]', None, '... the states +0x68'),
        (0x6AE829, 'mov r9d, dword ptr [rsi + 0x50]', None, 'the entity map: capacity +0x50 ...'),
        (0x6AE82F, 'mov r10d, dword ptr [rsi + 0x58]', None, '... multiplier +0x58 ...'),
        (0x6AE840, 'mov r11, qword ptr [rsi + 0x48]', None, '... keys +0x48 ...'),
        (0x6AE844, 'mov r12d, dword ptr [rsi + 0x54]', None, '... empty key +0x54'),
    ],
    'replication': [
        (0x6AE918, 'mov ecx, dword ptr [rdi + rax + 0xc]', None, 'init: the type ...'),
        (0x6AE91C, 'mov dword ptr [r14], ecx', None, '... copied into the creation buffer ...'),
        (0x6AE928, 'mov dword ptr [r15 + rax*8], 0xc2eb5c15', None, '... described as 0xC2EB5C15 ...'),
        (0x6AE939, 'mov qword ptr [r15 + rax*8 + 8], r14', None, '... pointing at the COPY'),
        (0x6ABB37, 'mov edx, 0x6109f766', None, 'the countdown ...'),
        (0x6ABB53, 'call 0xfd97e0', None, '... marked dirty every update'),
        (0x6AB879, 'mov byte ptr [r12 + rdi + 0x3c], 1', None, 'the flag +0x3C ...'),
        (0x6AB87F, 'mov edx, 0x44f85b36', None, '...'),
        (0x6AB89A, 'call 0xfd97e0', None, '... marked dirty once'),
        (0x6AB863, 'cmp dword ptr [r13 + 0x8e0], 2', None, 'state mode 2: the activation logic is skipped'),
    ],
    'typeReaders': [
        (0x6AB4A3, 'mov edx, dword ptr [rax + r14 + 0xc]', None, 'every update: each beacon\'s type ...'),
        (0x6AB546, 'test dword ptr [r15 + 0x104], 0x200', None, '... its row\'s +0x104 bit 0x200 ...'),
        (0x6AB568, 'movss xmm1, dword ptr [rax + r14 + 0x20]', None, '... the drop-position geometry of the visual nodes'),
        (0x6AB84A, 'mov eax, dword ptr [r12 + rdi + 0xc]', None, 'the activation loop: the type'),
        (0x6ABC14, 'mov ecx, dword ptr [r12 + rdi + 0xc]', None, 'activation: the type to the dispatcher'),
    ],
    'activation': [
        (0x6ABB58, 'movss xmm0, dword ptr [r12 + rdi]', None, 'the countdown ...'),
        (0x6ABB5E, 'movss xmm1, dword ptr [r12 + rdi + 4]', None, '... the threshold ...'),
        (0x6ABB65, 'comiss xmm1, xmm0', None, '... crossed ...'),
        (0x6ABB68, 'jbe 0x6abcdd', None, '...'),
        (0x6ABB77, 'cmp byte ptr [r13 + 0x8e4], 0', None, '... not yet activated ...'),
        (0x6ABB8D, 'mov byte ptr [r13 + 0x8e4], 1', None, '... activated once'),
        (0x6ABC72, 'call 0x6abdb0', None, 'the spawn dispatcher with the element\'s type'),
        (0x6ABE0E, 'lea r14, [rip + {rip}]', 0x37CB470, 'type 0: the all-zero default row ...'),
        (0x6ABE19, 'cmp dword ptr [r14 + 0xa0], 0', None, '... no payload ...'),
        (0x6ABE21, 'je 0x6adb08', None, '... nothing spawned'),
        (0x6ABE62, 'lea r14, [rip + {rip}]', TABLE, 'any other type: the StratagemInfo table ...'),
        (0x6ABE69, 'mov r14, qword ptr [r14 + r12*8]', None, '... its row'),
        (0x6AB4B7, 'test edx, edx', None, 'every update, type 0: the default row ...'),
        (0x6AB4BB, 'mov r15, qword ptr [r9 + rdx*8]', None, '... any other: the type\'s row'),
        (0x6AB939, 'cmp dword ptr [r12 + rdi + 0xc], 0x94', None, 'type 0x94: special-cased'),
    ],
    'callInTracking': [
        (0x6A1405, 'mov eax, dword ptr [r14 + rsi*8 + 8]', None, 'the call-in TABLE entry\'s own type ...'),
        (0x6A1426, 'test byte ptr [rax + 0x170], 2', None, '... its row\'s +0x170 bit 1 ...'),
        (0x6A142F, 'movss xmm0, dword ptr [r12 + 0x48]', None, '... a one-second timer ...'),
        (0x6A1477, 'call 0x69fcb0', None, '... re-targets from an entity\'s current position ...'),
        (0x6A147C, 'mov dword ptr [r12 + 0x48], 0x3f800000', None, '... every 1.0 s'),
        (0x69FD78, 'call 0x50cd90', None, 'the entity\'s unit ...'),
        (0x69FE61, 'call qword ptr [rax + 0xa8]', None, '... ground ray'),
    ],
    'marker': [
        (0x13D1389, 'mov r8, qword ptr [rip + {rip}]', MARKERS, 'the marker component'),
        (0x13D1393, 'mov r9d, dword ptr [r8 + 0x30]', None, 'its entity map capacity'),
        (0x13D1397, 'mov r10d, dword ptr [r8 + 0x38]', None, 'its multiplier'),
        (0x13D13AC, 'mov r11, qword ptr [r8 + 0x28]', None, 'its keys'),
        (0x13D13B0, 'mov edi, dword ptr [r8 + 0x34]', None, 'its empty key'),
        (0x13D14AB, 'imul rcx, rax, 0x2c', None, 'its elements, 0x2C each ...'),
        (0x13D14AF, 'mov rax, qword ptr [r8 + 0x50]', None, '... +0x50 ...'),
        (0x13D14B3, 'mov ebx, dword ptr [rcx + rax + 0x28]', None, '... its own type +0x28'),
        (0x13D1557, 'mov eax, dword ptr [rdi + 0xb8]', None, 'the row\'s category ...'),
        (0x13D1566, 'jne 0x13d1578', None, '...'),
        (0x13D1568, 'movaps xmm0, xmmword ptr [rip + {rip}]', COLOURS['offensive'], '... 0: red'),
        (0x13D157E, 'cmp eax, 2', None, '...'),
        (0x13D1583, 'movaps xmm0, xmmword ptr [rip + {rip}]', COLOURS['supply'], '... 2: blue'),
        (0x13D1593, 'movaps xmm0, xmmword ptr [rip + {rip}]', COLOURS['other'], '... else: yellow'),
    ],
    'timing': [
        (0x6AE7D5, 'call 0x6a5b70', None, 'beacon init: the countdown and threshold computed once ...'),
        (0x6AE7EA, 'movss dword ptr [rdi + rcx], xmm0', None, '... the countdown stored (+0x0)'),
        (0x6A5C5D, 'mov r8d, dword ptr [r14 + 0x398]', None, 'from the spawn parameters\' type (the carrier\'s) ...'),
        (0x6A5C69, 'call 0x879900', None, '... the call-in time ...'),
        (0x87997F, 'addss xmm0, dword ptr [rdi + 0x54]', None, '... the row\'s call-in time +0x54 ...'),
        (0x87999A, 'call 0xb5fbf0', None, '... the player\'s modifiers ...'),
        (0x8799C5, 'cmp dword ptr [rdi + rax*8 + 0x21e8], 0x8f', None, '... each active mission effect 0x8F ...'),
        (0x8799D2, 'mov edx, 0x8a8c0daa', None, '... its call-in setting ...'),
        (0x879A36, 'maxss xmm6, xmm8', None, '... never negative'),
        (0x6A5C6E, 'cmp dword ptr [r14 + 0x398], 0x94', None, 'type 0x94 only ...'),
        (0x6A5C7F, 'jne 0x6a5cd2', None, '... (every other type skips to the delivery time) ...'),
        (0x6A5C97, 'call 0x8f3f20', None, '... a game condition ...'),
        (0x6A5CA0, 'xorps xmm7, xmm7', None, '... zeroes its call-in'),
        (0x6A5CF2, 'call 0x6aded0', None, 'the delivery time ...'),
        (0x6ADF35, 'mov eax, dword ptr [rbx + 0x104]', None, '... row +0x104 bit 1: a pod\'s fall ...'),
        (0x6ADFD5, 'test byte ptr [rbx + 0x104], 0x80', None, '... bit 0x80: an aircraft\'s flight ...'),
        (0x6AE06F, 'call 0x504180', None, '... otherwise the bombardment record\'s duration'),
        (0x6A5D1B, 'mov eax, dword ptr [rax + 0x3c]', None, 'delivery kinds 1 and 5 ...'),
        (0x6A5D66, 'call 0x10026a0', None, '... add the orbital travel beyond the call-in'),
        (0x6A5D87, 'movss xmm2, dword ptr [rdi + 0x60]', None, 'the row\'s linger +0x60'),
        (0x6A5DAF, 'movss dword ptr [rcx + rax + 4], xmm1', None, 'threshold = travel + delivery + linger'),
        (0x6A5DAB, 'addss xmm6, xmm2', None, 'countdown = threshold + call-in'),
        (0x6AE8AB, 'mov dword ptr [r15 + rax*8], 0x248ff28e', None, 'the threshold: replicated at creation only'),
        (0x6ABB3C, 'movss dword ptr [rdi + rax], xmm0', None, 'every update with state: the countdown minus the frame time'),
        (0x6ABB6E, 'comiss xmm6, xmm1', None, 'the activation is the crossing: before >= threshold > after'),
        (0x6ABC81, 'comiss xmm10, xmm0', None, 'below zero ...'),
        (0x6ABCD8, 'call 0xfdc310', None, '... the beacon is removed'),
        (0x6AD9A3, 'movss dword ptr [rcx + rax], xmm0', None, 'a further wave: the countdown plus its delay ...'),
        (0x6AD9CA, 'mov byte ptr [rcx + rax + 0x8e4], r15b', None, '... and "activated" cleared (re-armed)'),
    ],
    'dispatchRecord': [
        (0x6ABC3D, 'mov eax, dword ptr [r13 + 0x38]', None, 'the spawn position passed to the dispatcher: state +0x38 ...'),
        (0x6ABC46, 'movsd xmm0, qword ptr [r13 + 0x30]', None, '... and +0x30 (the beacon position)'),
        (0x6ABB89, 'lea r15, [r13 + 0x40]', None, 'the dispatcher\'s record = the state + 0x40 ...'),
        (0x6ABC6D, 'mov qword ptr [rsp + 0x20], r15', None, '... passed to the dispatcher ...'),
        (0x6ABDE9, 'mov rsi, qword ptr [rbp + 0x3b0]', None, '... as rsi'),
        (0x6AC007, 'cmp dword ptr [r14 + 0x3c], r15d', None, 'delivery kind 0 (Eagle) records nothing here'),
        (0x6AC03D, 'mov qword ptr [rsi + 0x3d8], rcx', None, 'the payload (state +0x418) ...'),
        (0x6AC044, 'mov byte ptr [rsi + 0x3e0], 1', None, '... a call recorded (state +0x420) ...'),
        (0x6AC04B, 'mov dword ptr [rsi + 0x3e4], r12d', None, '... the type the dispatcher was given (state +0x424)'),
        (0x6AD1D4, 'mov qword ptr [rsi + 0x3d8], rdx', None, 'per wave: its payload'),
        (0x6AD3CF, 'mov dword ptr [rsi + 0x7d4], ecx', None, 'per wave: the type (state +0x814)'),
        (0x6AD90F, 'mov dword ptr [rsi + 0x898], 0xa', None, 'a spawn requested (state +0x8D8 = 10) ...'),
        (0x6AD919, 'call 0xfd9710', None, '... the request'),
        (0x6AEB7A, 'mov dword ptr [rdi + rax + 0x2c], r8d', None, 'beacon init: the element\'s +0x2C (waves) = 0 ...'),
        (0x6AD9F9, 'mov dword ptr [rcx + rax + 0x2c], r8d', None, '... the waves spawned, after each'),
    ],
    # Every access of a beacon element's countdown (+0x0) or threshold (+0x4) in the beacon component's code (the sweep
    # in timing_accesses() finds exactly these): the init, the update, the type-0x94 path, a further wave, element moves
    # (whole 0x40-byte copies) and one accessor with no static reference.
    'timingReaders': [
        (0x6AE7EA, 'movss dword ptr [rdi + rcx], xmm0', None, 'init: the countdown'),
        (0x6A5DAF, 'movss dword ptr [rcx + rax + 4], xmm1', None, 'init: the threshold'),
        (0x6AE891, 'mov dword ptr [rdi + rdx + 4], eax', None, 'init: the threshold (the same element)'),
        (0x6AB9C4, 'movss dword ptr [rcx + rax], xmm0', None, 'type 0x94: the countdown minus the frame time'),
        (0x6ABB3C, 'movss dword ptr [rdi + rax], xmm0', None, 'every update: the countdown minus the frame time'),
        (0x6AB942, 'movss xmm6, dword ptr [r12 + rdi]', None, 'the countdown before this update\'s subtraction'),
        (0x6ABB58, 'movss xmm0, dword ptr [r12 + rdi]', None, 'the crossing: the countdown ...'),
        (0x6ABB5E, 'movss xmm1, dword ptr [r12 + rdi + 4]', None, '... and the threshold'),
        (0x6ABC77, 'movss xmm0, dword ptr [r12 + rdi]', None, 'the removal: the countdown below zero'),
        (0x6AD9A3, 'movss dword ptr [rcx + rax], xmm0', None, 'a further wave: the countdown plus its delay'),
        (0x6AE610, 'movups xmm0, xmmword ptr [rdi + rax]', None, 'element moves: whole elements copied'),
        (0x6A5E79, 'movss xmm0, dword ptr [rcx + rax + 4]', None, 'an accessor (the threshold by entity): no static reference'),
    ],
    # The barrage a 120mm dispatch spawns: its own timers from its bombardment record and its spawn entity; nothing of
    # the beacon is read.
    'bombardmentLifecycle': [
        (0x851943, 'mov r15, qword ptr [rip + {rip}]', 0x3326CE8, 'the bombardment manager'),
        (0x8521D4, 'cmp dword ptr [rcx + 0x24], edi', None, 'its instance count +0x24 ...'),
        (0x8522F5, 'cmp dword ptr [r15 + 0x20], 0', None, '... and barrage count +0x20'),
        (0x8519B0,'mov dword ptr [rcx + rdx*4], 0x40a00000', None, 'barrage start: its removal timer 5 s ...'),
        (0x8519B7, 'movss xmm1, dword ptr [rax + 0x80]', None, '... its start delay: the record\'s +0x80 ...'),
        (0x8519BF, 'cmp byte ptr [rax + 0x3c], dil', None, '... and when the record\'s +0x3C ...'),
        (0x851A20, 'call 0xa0af50', None, '... a time for its entity'),
        (0x851A6E, 'mov dword ptr [rsi + 4], eax', None, 'the instance: shells left in the salvo (+0x4) ...'),
        (0x851A8F, 'mov dword ptr [rsi + 0xc], eax', None, '... salvos left (+0xC) ...'),
        (0x851A9A, 'movss dword ptr [rsi + 0x10], xmm1', None, '... the salvo timer (+0x10): the start delay'),
        (0x852382, 'mov rax, qword ptr [r15 + 0x48]', None, 'the update: the handles ...'),
        (0x852386, 'imul rsi, rbx, 0x70', None, '... the instance states, 0x70 each ...'),
        (0x852392, 'add rsi, qword ptr [r15 + 0x58]', None, '... at +0x58'),
        (0x853551, 'dec dword ptr [rsi + 4]', None, 'a shell fired: shells left - 1 ...'),
        (0x853554, 'inc dword ptr [rsi]', None, '... shells fired (+0x0) + 1'),
        (0x853837, 'mov edx, dword ptr [rsi + 0xc]', None, 'no shell left: the next salvo, if any'),
        (0x8522AB, 'cmp dword ptr [rbx + 4], 0', None, 'nothing left to fire ...'),
        (0x8522B1, 'cmp dword ptr [rbx + 0xc], 0', None, '...'),
        (0x8522B7, 'movss xmm0, dword ptr [r14 + rdi*4]', None, '... its removal timer (+0x50) ...'),
        (0x8522D5, 'call 0xfdc310', None, '... then the barrage is removed'),
    ],
    # The thrown stratagem ball (the "call-in table", the game's StratagemBallComponent): its own type copy (+8) decides
    # the beam, the glow, the ping and the steering before the beacon exists (research only; nothing reads these pins
    # at run time).
    'ballPresentation': [
        (0x6A21A5, 'mov r14d, dword ptr [rax + 0xd4]', None, 'the beam: the ball type\'s row +0xD4 (1 red, 2 blue, 3 yellow)'),
        (0x6A1405, 'mov eax, dword ptr [r14 + rsi*8 + 8]', None, 'the ball\'s own type (+8) ...'),
        (0x6A0830, 'movzx eax, byte ptr [rax + 0x170]', None, '... its row\'s +0x170 (walkable-ground steering) ...'),
        (0x6A0A89, 'cmp byte ptr [r14 + rsi*8], 0', None, '... skipped once the ball has landed'),
        (0x6A33DD, 'call 0xfd9710', None, 'landing spawns the beacon entity'),
        (0x13D1443, 'mov ebx, dword ptr [rax + rcx*8 + 8]', None, 'the ping (HUD marker) takes the ball\'s type'),
    ],
    # A per-player ship counter of orbitals in flight: +1 at a beacon's creation when its SPAWN type is an orbital
    # (delivery kind 1 or 5), -1 (floored at 0) at its removal when its CURRENT type (+0xC) is one. A redirect across the
    # orbital line unbalances it (research only; its reader is unknown).
    'orbitalCounter': [
        (0x6A89EF, 'mov eax, dword ptr [rdi + 0x3c]', None, 'creation: the spawn type\'s delivery kind ...'),
        (0x6A8ABB, 'inc dword ptr [rax + rcx*8 + 0x1fb20]', None, '... 1 or 5: the ship counter + 1'),
        (0x6AA84F, 'mov ecx, dword ptr [r14 + rax + 0xc]', None, 'removal: the beacon\'s CURRENT type ...'),
        (0x6AA880, 'mov eax, dword ptr [rax + 0x3c]', None, '... its delivery kind 1 or 5 ...'),
        (0x6AA930, 'mov dword ptr [rdx + rcx*8 + 0x1fb20], eax', None, '... the ship counter - 1 (not below 0)'),
    ],
    'eagleRearm': [
        (0x66E696, 'cmp dword ptr [rax + 0xc8], 0x31', None, 'the fleet: rows linking Eagle Rearm ...'),
        (0x66E6A5, 'call 0x66d3d0', None, '... uses left ...'),
        (0x66E6BD, 'xor al, al', None, '... any one: not depleted'),
        (0x66EB41, 'call 0x670d50', None, 'the post-call branch: Eagle Rearm in the record? ...'),
        (0x670DD0, 'cmp dword ptr [rax], r8d', None, '... an entry of that type'),
        (0x6AE4B1, 'mov r8d, dword ptr [rax + 0xc8]', None, 'the record build: a row\'s linked type'),
    ],
}


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def timing_accesses(game_data, start=0x6A0000, end=0x6B0000):
    """Every instruction in the beacon component's code that reads or writes +0x0 or +0x4 relative to an element
    (index scaled 0x40) after loading an element array (qword [reg + 0x78]): a register holding the array is tracked
    until it is overwritten. Returns the sorted addresses (whole-element 16-byte moves included)."""
    import re
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.skipdata = True
    held, found = {}, set()
    for address, _size, mnemonic, operands in md.disasm_lite(game_data[start:end], start):
        if mnemonic == 'ret':
            held.clear()
            continue
        destination = operands.split(',')[0].strip()
        loaded = re.match(r'(\w+), qword ptr \[(?!rsp)\w+ \+ 0x78\]$', operands)   # not a stack slot
        for register in list(held):
            memory = re.search(r'\[(%s \+ \w+|\w+ \+ %s)( \+ (0x4|4))?\]' % (register, register), operands)
            if memory and re.search(r'(dword|xmmword) ptr', operands):
                found.add(address)
            if destination == register and not loaded:
                del held[register]
        if mnemonic == 'mov' and loaded:
            held[loaded.group(1)] = address
    return sorted(found)


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    # The timers' accessors (9.): the sweep must find exactly the pinned readers plus the creation-message copies and the
    # element moves; anything else would be an unknown consumer of the countdown or threshold.
    accesses = timing_accesses(game_data)
    expected = {p['rva'] for p in pins['timingReaders']} | {0x6AE614, 0x6AE7F3, 0x6AE88D, 0x6AE89E, 0x6AD99E, 0x6AFBCA,
        0x6AFBF0, 0x6AFC07, 0x6AFC21, 0x6AFF7D, 0x6AFFAC, 0x6AFFC3, 0x6AFFE1}
    if set(accesses) != expected:
        raise ValueError('the countdown/threshold accessors changed: %s' % ' '.join('%X' % a for a in
            sorted(set(accesses) ^ expected)))
    colours = {name: list(struct.unpack_from('<4f', game_data, rva)) for name, rva in COLOURS.items()}
    pins['colours'] = [{'rva': rva, 'bytes': game_data[rva:rva + 16].hex(), 'asm': 'dd 4 x f32',
        'role': 'the %s marker colour' % name} for name, rva in COLOURS.items()]
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    managers, records = [], {}
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        g = mem.game
        world = mem.ptr(g + WORLD)
        mgr = world + SYSTEMS + BEACONS
        raw = mem.read(mgr, 0x80)
        count, active = u32(raw, 0x34), u32(raw, 0x38)
        cap, empty, mult = struct.unpack_from('<III', raw, 0x50)
        pointers = [struct.unpack_from('<Q', raw, o)[0] for o in (0x48, 0x60, 0x68, 0x70, 0x78)]
        heap = all(mem.read(p, 8) is not None for p in pointers)
        if count > 4096 or active > 4096 or cap & (cap - 1) or not heap:
            raise ValueError('%s: the beacon manager path is implausible' % name)
        managers.append({'snapshot': name, 'count': count, 'active': active, 'mapCapacity': cap, 'emptyKey': empty,
            'multiplier': mult})
        base_records = mem.ptr(g + RECORDS)
        records[name] = mem.u32(base_records + 0x2D200)
        mem.close()

    names = {root['id']: name for name, root in catalogue_roots().items()}
    families = {}
    import re
    text = (ROOT / 'domains/stratagem_authoring.lua').read_text(encoding='utf-8')
    for m in re.finditer(r'\["name"\]="([^"]+)",\["family"\]="([^"]*)"', text):
        families[m.group(1)] = m.group(2)
    mem = base.Mem(MISSION_SNAPSHOT)
    g = mem.game
    category, follows, timing = defaultdict(set), defaultdict(set), {}
    for kind in range(1, 150):
        row = mem.ptr(g + TABLE + kind * 8)
        if not row:
            continue
        raw = mem.read(row, 0x180)
        family = families.get(names.get(u32(raw, 4))) or 'uncatalogued'
        category[family].add(u32(raw, 0xB8))
        follows[family].add(bool(raw[0x170] & 2))
        name = names.get(u32(raw, 4))
        if name:
            flags = u32(raw, 0x104)
            timing[name] = {'type': kind, 'kind': u32(raw, 0x3C), 'category': u32(raw, 0xB8),
                'callIn': round(struct.unpack_from('<f', raw, 0x54)[0], 4),
                'linger': round(struct.unpack_from('<f', raw, 0x60)[0], 4), 'waves': u32(raw, 0x12C) + 1,
                'deliveryTime': 'pod fall' if flags & 2 and u32(raw, 0xA0) >= 2 else 'aircraft flight' if flags & 0x80
                    else 'bombardment record' if u32(raw, 0xA0) else 'none',
                'orbitalTravel': u32(raw, 0x3C) in (1, 5)}
    mem.close()
    expected = {'Eagle Strafing Run': (0.0, 0.0, 'aircraft flight'), 'Orbital 120mm HE Barrage': (5.0, 0.0,
        'bombardment record'), 'AC-8 Autocannon': (3.0, 4.0, 'pod fall')}
    for name, (call_in, linger, source) in expected.items():
        t = timing[name]
        if (t['callIn'], t['linger'], t['deliveryTime']) != (call_in, linger, source):
            raise ValueError('%s: the call-in members changed: %r' % (name, t))
    category = {k: sorted(v) for k, v in sorted(category.items())}
    follows = {k: sorted(v) for k, v in sorted(follows.items())}
    if category['orbital'] != [0] or category['eagle'] != [0] or category['sentry'] != [3]:
        raise ValueError('the category no longer separates the families: %r' % category)
    if follows['orbital'] != [False] or follows['eagle'] != [False] or follows['sentry'] != [True]:
        raise ValueError('+0x170 bit 1 no longer separates pods from orbitals and Eagles: %r' % follows)

    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'gameDll': {'sha256': base.PROFILE_DLL_SHA},
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation,
        'managerPath': {'world': '0x%X' % WORLD, 'systems': SYSTEMS, 'beacons': BEACONS, 'perSnapshot': managers},
        'beacon': {'manager': {'count': 0x34, 'active': 0x38, 'mapKeys': 0x48, 'mapCapacity': 0x50, 'mapEmpty': 0x54,
                'mapMultiplier': 0x58, 'entities': 0x60, 'state': 0x68, 'nodes': 0x70, 'elements': 0x78},
            'element': {'stride': 0x40, 'countdown': 0x0, 'threshold': 0x4, 'type': 0xC, 'position': 0x10,
                'dropPosition': 0x1C, 'field28': 0x28, 'flag': 0x3C},
            'state': {'stride': 0x8E8, 'position': 0x30, 'mode': 0x8E0, 'activated': 0x8E4},
            'replicatedAtCreation': ['type 0xC2EB5C15', 'countdown 0x6109F766', 'threshold 0x248FF28E',
                'position 0x776786CE', 'drop position 0xD5077FC6'],
            'replicatedOnChange': ['countdown 0x6109F766', 'flag 0x44F85B36']},
        'marker': {'global': '0x%X' % MARKERS, 'keys': 0x28, 'capacity': 0x30, 'empty': 0x34, 'multiplier': 0x38,
            'elements': 0x50, 'stride': 0x2C, 'type': 0x28, 'colours': colours},
        # The call-in timing (7.): element members, the row members, and every catalogued row's values [O].
        'timing': {'countdown': 0x0, 'threshold': 0x4, 'row': {'callIn': 0x54, 'linger': 0x60, 'kind': 0x3C,
                'category': 0xB8, 'deliveryFlags': 0x104, 'waves': 0x12C, 'follows': 0x170},
            'formula': {'threshold': 'orbital travel beyond the call-in (kinds 1 and 5) + delivery time + linger',
                'countdown': 'threshold + call-in (row +0x54 with the player and mission modifiers)',
                'activation': 'countdown - threshold after the beacon has state', 'lifeAfterActivation': 'threshold',
                'computedFrom': 'the type at creation (the carrier type); a later type change does not recompute'},
            'byStratagem': dict(sorted(timing.items()))},
        # The dispatcher's own record (8.), in the beacon's state (the record is the state + 0x40).
        # 9. Every access of an element's countdown or threshold in the beacon component (the sweep, [O] on the image).
        'timingAccesses': ['0x%X' % a for a in accesses],
        # 10. A barrage instance (the bombardment manager: handles +0x48, removal timers +0x50 (f32 each), states +0x58,
        # 0x70 each): its own counters, read-only evidence of the barrage's start and duration.
        'bombardmentInstance': {'handles': 0x48, 'removalTimers': 0x50, 'states': 0x58, 'stride': 0x70,
            'shellsFired': 0x0, 'shellsLeft': 0x4, 'salvosLeft': 0xC, 'salvoTimer': 0x10, 'aim': 0x14,
            'removalSeconds': 5.0},
        'dispatchRecord': {'base': 0x40, 'payload': 0x418, 'called': 0x420, 'type': 0x424, 'waveType': 0x814,
            'spawn': 0x8D8, 'spawnRequested': 10, 'elementWaves': 0x2C, 'eagleRecordsNothing': True},
        'categoryByFamily': category, 'followsByFamily': follows, 'recordsPerSnapshot': records,
        'neutralType': {'type': 0, 'row': 'the all-zero default row game+0x37CB470: no payload, no flags'}}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; categories', category, '; follows', follows)


if __name__ == '__main__':
    main()
