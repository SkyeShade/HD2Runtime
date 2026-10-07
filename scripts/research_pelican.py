"""The Pelican (research/docs/pelican-cas-F5FEE03DCFDB.md): how the game makes, flies, holds and removes its transport
Pelican, what a per-instance Runtime write can reach, and what only native code can. Read-only, offline: the game.dll
image, the retained snapshots of build F5FEE03DCFDB and the game's own bundles. Nothing is written.

A third-party mod (Suzuka's Pelican Cover Flag 1.0.0) was the lead. Its offsets and native calls are not used: every
fact below is proven here from the game's own code [C] or observed in the snapshots and bundles [O].

1. The entity. A transport Pelican is the entity resource `content/fac_helldivers/vehicles/shuttle_transport/
   shuttle_transport` (0x75BE82ED8592A6B3). Every vehicle and exosuit row's payload list is [the vehicle, the Pelican];
   the dispatcher's wave spawns payload[2w+1] (the Pelican) with payload[2w] (the vehicle) as its cargo (0x6AD15E-
   0x6AD1D4), passing its own record (the beacon state + 0x40) as the spawn context (0x6AD7D3) to the generic spawn
   request (0xFD9710) [C]. The Pelican lives in `packages/content/base_faction`, resident in every mission snapshot;
   the vehicles' loadout packages are not [O].
2. The cargo has no Runtime window. The Transport component (game+0x3326518; elements 0x40 at +0x40) takes its cargo
   from the context's +0x3D8 at creation (0x6D9835) and its spawn timer +0xC from the entity's transport settings
   (0x6D9863): 0.0 for the Pelican [O]. The same system pass updates the beacons (0x571305), which spawn the Pelican,
   and then the transports (0x57243D), whose first update takes the timer below zero and spawns the cargo
   (0x6DA36F-0x6DA392) unless something overlaps the spawn box. So a vehicle Pelican carries its vehicle before any
   Runtime update can see it [C].
3. Association. The context's +0x3F0 becomes the element's +0x28 (0x6D98FF): an associated transport never runs the
   cargo timer (0x6DA2F0) and flies to the associated entity (0x4D62B0). The game uses it to airlift a mission object:
   a system (0x5EBEC0, systems + 0x1400) spawns the Pelican with its own context whose +0x3F0 is the object (0x5EC7CE)
   [C]. No beacon code writes the beacon state's +0x430 (the record's +0x3F0) [C]: it is not a stratagem mechanism.
4. The flight. The Pelican's Behavior record (game+0x3326740: entity map +0x40, records +0x60, 0x1F8 each; the
   behaviour context is the record + 8 = P) runs a stage machine (0x45C760): P+0 the stage, P+0x1BC the target,
   P+0x1E0 bit 0 "released". Stage 3 targets the position a shared position component holds for it, plus a random
   height (0x4D5A60; its spawn point or its position then: live). Stage 6 (0x45AF10) hovers: P+0x180 = its start;
   with no cargo it releases once at the target or 6 s after the start, sets the bit and P+0x178 = now (0x45B33C);
   0.6 s after P+0x178 it departs (stage 8, 0x45B134-0x45B14F).
   Stage 7 departs 3 s after P+0x178. Stages 8-10 fly out, and 12 s after P+0x178 in stage 10 the entity is removed
   (0xFDC310) [C]. The clock is [game+0x3326348]+0x18, in microseconds.
5. Lifetime. No 180 s value exists in the stage machine; 180 s is the mod's own limit. The time a released Pelican
   stays is per instance: P+0x178 + 0.6 s (stage 6). One 8-byte write of P+0x178 moves its departure; nothing shared
   changes. The departure, the fly-out and the removal stay native [C].
6. The position. The hover point is P+0x1BC, pushed into the flight by 0x4D1150 at each transition; changing it while
   alive needs that native push (the mod calls it) or a second, unmapped flight member [C].

Output: research/pelican-F5FEE03DCFDB.json.
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
from research_stratagem_slot_conversion import catalogue_roots  # noqa: E402

OUTPUT = ROOT / 'research/pelican-F5FEE03DCFDB.json'
MISSION_SNAPSHOTS = ['F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap']
WORLD = 0x346BF98
BEHAVIOR, TRANSPORT, BEARER, CLOCK = 0x3326740, 0x3326518, 0x3326508, 0x3326348
ANCHOR, FLIGHT = 0x3326658, 0x3326460
# The per-entity-type behaviour settings (research "variants"): the component world + 0xF12D58, 0x7D8 slots of 16 bytes
# {resource, index}, then 12-byte entries {behaviour id, a float, ...} at +0x7D80.
BEHAVIOUR_SETTINGS, BEHAVIOUR_SLOTS, BEHAVIOUR_ENTRIES = 0xF12D58, 0x7D8, 0x7D80
# The Pelican entities and the turrets (resources; names resolved by hash and the retained entity table).
PELICAN_VARIANTS = {
    'shuttle_transport': (0x75BE82ED8592A6B3, 'content/fac_helldivers/vehicles/shuttle_transport/shuttle_transport'),
    'shuttle_gunship': (0xEF3A4136B21592CB, 'content/fac_helldivers/vehicles/shuttle_gunship/shuttle_gunship'),
    'shuttle': (0x3F8734AEC15B82AD, None),
    'shuttle_dropship': (0x7B0F8449CA9D2DA0, None),
    'shuttle_transport_personnel': (0x18F11A4E18192CFE,
        'content/fac_helldivers/vehicles/shuttle_transport_personnel/shuttle_transport_personnel'),
    'shuttle_gunship_turret_hmg': (0x8365609B35EF6672,
        'content/fac_helldivers/vehicles/shuttle_gunship/turrets/shuttle_gunship_turret_hmg'),
    'gatling_turret': (0xEF85D6CF58E31D70, 'content/fac_helldivers/hellpod/turret/gatling_turret'),
}
PELICAN = 0x75BE82ED8592A6B3
TURRET_HMG, GATLING = PELICAN_VARIANTS['shuttle_gunship_turret_hmg'][0], PELICAN_VARIANTS['gatling_turret'][0]
PELICAN_UNIT = 'content/fac_helldivers/vehicles/shuttle_transport/shuttle_transport'
INVALID_ENTITY = 0x3483C20
SETTINGS_TABLE, SETTINGS_SLOTS = 0xF12898, 0x1C
POD_TABLE, POD_SLOTS = 0xF12AE0, 0x10
BASE_FACTION = 0xF6FB08CC02D24255
US = 1_000_000
SPAWN, SPAWN_END = 0xFD9710, 0xFD97C8
DEFAULT_CONTEXT, DEFAULT_MODIFIERS = 0xF3EF28, 0xF3F7C8
CONTEXT_SIZE = DEFAULT_MODIFIERS - DEFAULT_CONTEXT

GAME = {
    # The component globals and their layouts, from the game's own accessors.
    'behavior': [
        (0x8449BB, 'mov r9, qword ptr [rip + {rip}]', BEHAVIOR, 'the Behavior component'),
        (0x8449C8, 'mov r10d, dword ptr [r9 + 0x48]', None, 'its entity map: capacity +0x48 ...'),
        (0x8449D4, 'mov ebx, dword ptr [r9 + 0x50]', None, '... multiplier +0x50 ...'),
        (0x8449F2, 'mov esi, dword ptr [r9 + 0x4c]', None, '... empty key +0x4C ...'),
        (0x8449FB, 'mov rdi, qword ptr [r9 + 0x40]', None, '... keys +0x40 (entity id, index)'),
        (0x844A31, 'mov rax, qword ptr [r9 + 0x58]', None, 'its handles +0x58'),
        (0x8422FF, 'imul rdi, rdx, 0x1f8', None, 'a record is 0x1F8 bytes ...'),
        (0x84230E, 'add rdi, qword ptr [r11 + 0x60]', None, '... at +0x60'),
        (0x8423FF, 'mov dword ptr [rdi], eax', None, 'the record +0: its behaviour id'),
        (0x842428, 'lea rax, [rdi + 8]', None, 'the behaviour context: the record + 8 (P)'),
    ],
    'transport': [
        (0x6D97A0, 'mov rbp, qword ptr [rip + {rip}]', TRANSPORT, 'the Transport component'),
        (0x6D97B6, 'mov r9d, dword ptr [rbp + 0x28]', None, 'its entity map: capacity +0x28 ...'),
        (0x6D97BC, 'mov r10d, dword ptr [rbp + 0x30]', None, '... multiplier +0x30 ...'),
        (0x6D97CD, 'mov r11, qword ptr [rbp + 0x20]', None, '... keys +0x20 ...'),
        (0x6D97D1, 'mov ebx, dword ptr [rbp + 0x2c]', None, '... empty key +0x2C'),
        (0x6D9814, 'shl rsi, 6', None, 'an element is 0x40 bytes ...'),
        (0x6D9818, 'add rsi, qword ptr [rbp + 0x40]', None, '... at +0x40'),
        (0x6DA28D, 'cmp dword ptr [rcx + 0x10], esi', None, 'the update: the count +0x10 ...'),
        (0x6DA2C0, 'mov rax, qword ptr [r15 + 0x38]', None, '... the handles +0x38 ...'),
        (0x6DA2DF, 'mov rcx, qword ptr [rdi]', None, '... a handle\'s +0: the entity resource'),
        (0x6D9835, 'mov rcx, qword ptr [r15 + 0x3d8]', None, 'creation: the cargo from the spawn context +0x3D8 ...'),
        (0x6D983C, 'mov qword ptr [rsi], rcx', None, '... into the element +0x0'),
        (0x6D9824, 'call 0x4fe950', None, 'the entity\'s transport settings ...'),
        (0x6D9830, 'call 0x505390', None, '... and its pod settings: present, the timer waits for a landing ...'),
        (0x6D984C, 'mov dword ptr [rsi + 0xc], 0xbf800000', None, '... (-1) ...'),
        (0x6D9863, 'mov dword ptr [rsi + 0xc], eax', None, '... absent, the cargo timer +0xC = the settings\' first value'),
        (0x6D98FF, 'mov ecx, dword ptr [r15 + 0x3f0]', None, 'the context +0x3F0 ...'),
        (0x6D9906, 'mov dword ptr [rsi + 0x28], ecx', None, '... the associated entity +0x28'),
        (0x6DA2F0, 'cmp dword ptr [rbx + 0x28], ecx', None, 'the update: an associated transport skips the cargo timer'),
        (0x6DA36F, 'movss xmm0, dword ptr [rbx + 0xc]', None, 'the cargo timer ...'),
        (0x6DA37D, 'subss xmm0, xmm6', None, '... minus the frame time ...'),
        (0x6DA392, 'call 0x6db970', None, '... below zero: unless the spawn box overlaps something, the cargo spawns'),
        (0x6D8D1A, 'cmp qword ptr [r12], rax', None, 'no cargo (+0x0 empty): nothing spawns'),
        (0x6DAC31, 'mov ecx, dword ptr [r13 + 8]', None, 'the release: the spawned cargo +0x8 ...'),
        (0x6DAC37, 'je 0x6db113', None, '... none: nothing to release'),
        (0x4FE955, 'mov rax, qword ptr [rip + {rip}]', WORLD, 'the transport settings table ...'),
        (0x4FE95F, 'mov r10, qword ptr [rax + 0xf12898]', None, '... at the component world + 0xF12898'),
    ],
    'bearer': [
        (0x6AC1BC, 'mov rcx, qword ptr [rip + {rip}]', BEARER, 'the transform component'),
        (0x6AC1C6, 'mov r10d, dword ptr [rcx + 0x50]', None, 'its entity map: multiplier +0x50 ...'),
        (0x6AC1CA, 'mov r9d, dword ptr [rcx + 0x48]', None, '... capacity +0x48 ...'),
        (0x6AC1D7, 'mov r11, qword ptr [rcx + 0x40]', None, '... keys +0x40 ...'),
        (0x6AC1DB, 'mov ecx, dword ptr [rcx + 0x4c]', None, '... empty key +0x4C'),
        (0x6AC254, 'imul rcx, rax, 0x308', None, 'a record is 0x308 bytes ...'),
        (0x6AC262, 'mov rax, qword ptr [rax + 0x68]', None, '... at +0x68 ...'),
        (0x6AC266, 'movsd xmm0, qword ptr [rcx + rax + 0x2e0]', None, '... its position +0x2E0'),
    ],
    'clock': [
        (0x45CAB2, 'mov rax, qword ptr [rip + {rip}]', CLOCK, 'the game clock ...'),
        (0x45CAB9, 'cmp rcx, qword ptr [rax + 0x18]', None, '... +0x18, in microseconds'),
    ],
    # The dispatcher spawns a vehicle row's Pelican with the vehicle as its cargo and its own record as the context.
    'dispatcher': [
        (0x6AD15E, 'mov rax, qword ptr [r14 + 0x98]', None, 'a wave: the row\'s payload list ...'),
        (0x6AD165, 'mov r12, qword ptr [rax + rcx*8]', None, '... payload[2w+1] (a vehicle row: the Pelican) is spawned ...'),
        (0x6AD1D0, 'mov rdx, qword ptr [rcx + rdx*8]', None, '... payload[2w] (the vehicle) ...'),
        (0x6AD1D4, 'mov qword ptr [rsi + 0x3d8], rdx', None, '... is the record\'s cargo'),
        (0x6AD7D3, 'mov qword ptr [rbp + 0x48], rsi', None, 'the spawn context: the dispatcher\'s record'),
        (0x6AD919, 'call 0xfd9710', None, 'the generic spawn request'),
    ],
    # One system pass: the beacons (whose activation spawns the Pelican), then the transports (its first update).
    'systemOrder': [
        (0x5712FB, 'lea rcx, [rdi + 0x1380]', None, 'the beacon manager ...'),
        (0x571305, 'call 0x6ab3e0', None, '... updated ...'),
        (0x571314, 'call 0x5ebec0', None, '... then the airlift system ...'),
        (0x57243D, 'call 0x6da270', None, '... then, in the same pass, the transports'),
    ],
    # The game's own associated Pelican: an airlift of a mission object (research only).
    'airlift': [
        (0x5EBF17, 'movabs r14, 0x75be82ed8592a6b3', None, 'the airlift system spawns the transport Pelican ...'),
        (0x5EC7CE, 'mov dword ptr [rbp + 0x4a0], esi', None, '... with its context +0x3F0 = the object ...'),
        (0x5EC90E, 'call 0xfdc140', None, '... created'),
        (0x45BFD5, 'call 0x4d62b0', None, 'stage 3, associated: the target from the object'),
    ],
    # The spawn request (research only until the spawn API: runtime/pelicans.lua M.spawn). FD9710(out, entity resource,
    # descriptor): a null modifier block becomes its own zeroed block; the world creates the entity and completes it.
    'spawn': [
        (0xFD9710, 'mov r11, rsp', None, 'the spawn request (out, entity resource, descriptor) ...'),
        (0xFD9737, 'mov rdi, r8', None, '... the descriptor ...'),
        (0xFD973A, 'mov r8, qword ptr [r8 + 0x50]', None, '... its modifier block +0x50 ...'),
        (0xFD9770, 'test r8, r8', None, '... none ...'),
        (0xFD9779, 'mov qword ptr [rdi + 0x50], rax', None, "... becomes the request's own zeroed block"),
        (0xFD9781, 'call 0x12e5590', None, "the entity's modifiers prepared"),
        (0xFD9786, 'mov rcx, qword ptr [rip + {rip}]', WORLD, 'the component world ...'),
        (0xFD9798, 'mov r8, qword ptr [rcx]', None, '... its engine world'),
        (0xFD979B, 'call 0xfdc0c0', None, 'the entity created ...'),
        (0xFD97A0, 'mov rax, rsi', None, '... returns the out pointer'),
        (0xFDC0ED, 'movabs rdx, 0xb04d927afb137b9b', None, "the entity's root unit ..."),
        (0xFDC101, 'lea r8, [rdi + 8]', None, "... at the descriptor's pose (+0x8, 4x4) ..."),
        (0xFDC112, 'mov dword ptr [r14], eax', None, '... its id written to out ...'),
        (0xFDC11D, 'call 0xfdc140', None, '... then completed'),
        (0xFDC1C3, 'mov qword ptr [r14], rdi', None, 'the entity handle: +0 the entity resource ...'),
        (0xFDC1C6, 'mov eax, dword ptr [rbp + 4]', None, "... the descriptor's network id (+0x4) ..."),
        (0xFDC1C9, 'mov dword ptr [r14 + 0x10], eax', None, '... at +0x10 ...'),
        (0xFDC1D1, 'cmp byte ptr [rbp], r9b', None, "... the descriptor's +0x0: created here (the authority) ..."),
        (0xFDC1D7, 'mov dword ptr [r14 + 0x14], 1', None, '... +0x14 = 1'),
        (0xFDC22A, 'cmp qword ptr [rbp + 0x48], r9', None, 'no spawn context (+0x48) ...'),
        (0xFDC230, 'lea rax, [rsi + 0xf3ef28]', None, "... the world's own default context ..."),
        (0xFDC237, 'mov qword ptr [rbp + 0x48], rax', None, '... is used'),
        (0xFDC23B, 'cmp qword ptr [rbp + 0x50], r9', None, 'no modifier block ...'),
        (0xFDC241, 'lea rax, [rsi + 0xf3f7c8]', None, "... the world's own default"),
        (0xFDC25A, 'call 0x581320', None, 'every component created with the descriptor'),
        (0x6D9801, 'cmp byte ptr [r15], dil', None, 'Transport creation: the descriptor ...'),
        (0x6D980E, 'mov r15, qword ptr [r15 + 0x48]', None, '... its context (never null here)'),
        (0x8422FB, 'mov rcx, qword ptr [r15 + 0x48]', None, 'Behavior creation: the context ...'),
        (0x842312, 'test rcx, rcx', None, '...'),
        (0x84231B, 'mov eax, dword ptr [rcx + 0x67c]', None, '... +0x67C a behaviour override (0: none) ...'),
        (0x842329, 'mov ebp, dword ptr [rcx + 0x398]', None, '... +0x398 a stratagem type (0: none) ...'),
        (0x84237C, 'test ebp, ebp', None, "... none: the entity type's own behaviour"),
        (0x8425F6, 'mov eax, dword ptr [rcx + 0x66c]', None, '... +0x66C a target entity (0: none)'),
        (0x84264A, 'mov r8, qword ptr [rax + 0x680]', None, '... +0x680 a pointer (0: none)'),
    ],
    # The hover anchor: a per-Pelican, replicated drop-position record (game+0x3326658; 0x20-byte records at +0x60, +0x0
    # the position) written ONCE at creation from the spawn context's +0x610 (or, with no context, the pose); the flight
    # derives every target from it (stage 1: 0x4D60D0, stage 3: 0x4D5A60). The beacon code fills +0x610 for a vehicle
    # (0x6A914A: state +0x650 = the record +0x610).
    'anchor': [
        (0x71D9C0, 'mov rax, qword ptr [rbp + 0x48]', None, "the drop-position record's creation: the spawn context ..."),
        (0x71D9C9, 'movsd xmm0, qword ptr [rax + 0x610]', None, '... its +0x610 (x, y) ...'),
        (0x71D9D1, 'mov ecx, dword ptr [rax + 0x618]', None, '... +0x618 (z) ...'),
        (0x71D9E4, 'movsd xmm0, qword ptr [rbp + 0x38]', None, "... (no context: the pose's position) ..."),
        (0x71D9EC, 'mov rax, qword ptr [rdi + 0x60]', None, '... into the record (+0x60, 0x20 each) ...'),
        (0x71D9F8, 'shl r9, 5', None, '...'),
        (0x71D9FC, 'movsd qword ptr [r9 + rax], xmm0', None, '... +0x0 ...'),
        (0x71DA02, 'mov dword ptr [r9 + rax + 8], ecx', None, '... +0x8'),
        (0x71DA23, 'mov dword ptr [rsi + rax*8], 0xd5077fc6', None, 'replicated (0xD5077FC6)'),
        (0x71DAB6, 'movzx ecx, byte ptr [rax + 0x61c]', None, 'the context +0x61C: a flag (record +0x14)'),
        (0x71DAFE, 'movss xmm0, dword ptr [rax + 0x620]', None, 'the context +0x620: a value (record +0x18)'),
        (0x4D5A8F, 'mov rsi, qword ptr [rip + {rip}]', ANCHOR, 'stage 3: the drop-position component ...'),
        (0x4D5B6A, 'mov rdx, qword ptr [rsi + 0x60]', None, '... its records ...'),
        (0x4D5BAB, 'movss xmm0, dword ptr [rdx + rcx]', None, '... the anchor: the hover point (plus a height)'),
        (0x4D6164, 'mov rdi, qword ptr [rip + {rip}]', ANCHOR, 'stage 1: the approach point from the anchor'),
    ],
    # Evidence (research only): the beacon fills the anchor for a vehicle's Pelican.
    'vehicleAnchor': [
        (0x6A914A, 'movsd qword ptr [rbx + 0x650], xmm1', None, 'a vehicle beacon: the drop position (state +0x650 = '
            'the record +0x610) ...'),
        (0x6A915B, 'mov dword ptr [rbx + 0x658], eax', None, '... z'),
        (0x6A9169, 'movss dword ptr [rbx + 0x660], xmm1', None, '... +0x660 (the record +0x620) ...'),
        (0x6A9171, 'mov byte ptr [rbx + 0x65c], 1', None, '... +0x65C = 1 (the record +0x61C)'),
    ],
    # The game's circling (research only): behaviour 202 (the dispatch table entry 201), stage 5, around the anchor.
    'orbit': [
        (0x472FAC, 'mov eax, dword ptr [r8 + rax*4 + 0x4795c4]', None, 'the behaviour dispatch: one table by behaviour id'),
        (0x271F42, 'call 0x26eed0', None, 'behaviour 202, stage 5: the holding pattern'),
        (0x26F07A, 'movss xmm0, dword ptr [rip + {rip}]', 0x23C7614, 'within 5 m (25 squared) of its point ...'),
        (0x26F09E, 'movss xmm3, dword ptr [rip + {rip}]', 0x23C7654, '... radius 30 m at 30 m ...'),
        (0x26F0B4, 'call 0x4d5e60', None, '... the next circle point'),
        (0x4D5E80, 'mov rbp, qword ptr [rip + {rip}]', ANCHOR, 'the circle point: around the anchor ...'),
        (0x4D5FA9, 'call 0x2106bfc', None, '... the angle of the current position ...'),
        (0x4D5FB5, 'addss xmm7, dword ptr [rip + {rip}]', 0x23C6C28, '... plus a fixed step (pi/4) ...'),
        (0x4D5FCC, 'mulss xmm8, dword ptr [rsp + 0xd0]', None, '... times the radius ...'),
        (0x4D6064, 'movsd qword ptr [rcx + 0x1bc], xmm0', None, '... the flight target'),
    ],
    # The target push (research only): for the flight component (game+0x3326460, 0x534 each) a plain data write.
    # Retargeting a held Pelican (runtime/pelicans.lua retarget, the orbit): the flight component steers every update to
    # its record's target, which only the move-to pushes write; a released stage 6 reads only its release time, and its
    # one push of P+0x1BC happens at the release itself.
    'retarget': [
        (0x573D01, 'call 0x84b0f0', None, 'every systems update: the flight component ...'),
        (0x84B1BD, 'imul rcx, rdx, 0x534', None, '... each record (0x534) ...'),
        (0x84CB48, 'movsd xmm0, qword ptr [rax + 0x4fc]', None, '... steers toward its target +0x4FC ...'),
        (0x84CB50, 'mov eax, dword ptr [rax + 0x504]', None, '... (z)'),
        (0x84EDCF, 'movsd qword ptr [rcx + 0x4fc], xmm0', None, 'the only other writer: the AI move-to (0x7ED4C0), not '
            'the transport flight'),
        (0x45B123, 'test byte ptr [rax + 0x1e0], 1', None, 'stage 6 released: only its release time is read'),
        (0x45B37D, 'movsd xmm0, qword ptr [rax + 0x1bc]', None, 'the release itself pushes P+0x1BC once ...'),
        (0x45B395, 'call 0x4d1150', None, '... into the flight'),
    ],
    # How a Behavior record gets its behaviour at creation (0x8422FB-0x842547): the spawn context's +0x67C override
    # first; else its stratagem type +0x398 (only three upgraded sentries get another behaviour there); else the entity
    # type's own, from the component world's behaviour settings (0x510790).
    'variants': [
        (0x84231B, 'mov eax, dword ptr [rcx + 0x67c]', None, 'creation: the spawn context\'s behaviour override ...'),
        (0x842323, 'jne 0x8423f7', None, '... when set, it is the behaviour'),
        (0x842520, 'cmp ebp, 0x2c', None, 'the stratagem path: only upgraded sentries (0x2C, 0x34, 0x75) ...'),
        (0x8423F0, 'call 0x510bb0', None, 'else the entity\'s own (an instance override map, then its type\'s) ...'),
        (0x51079F, 'mov r10, qword ptr [rax + 0xf12d58]', None, '... the type behaviour settings (component world '
            '+0xF12D58) ...'),
        (0x5107C3, 'imul eax, eax, 0x7d8', None, '... 0x7D8 slots of 16 bytes ...'),
        (0x510811, 'lea rax, [rcx + 0xfb0]', None, '... its 12-byte entry after them (+0x7D80)'),
    ],
    # The extraction Pelican's flight (behaviour 202: research only, nothing used at run time but by the read-only probe).
    'extraction': [
        (0x271D06, 'cmp eax, 0xc', None, 'behaviour 202: 13 stages'),
        (0x26EEF6, 'call 0x4b0030', None, 'its holding stage 5: abort when no helldiver is left ...'),
        (0x26EF02, 'mov edx, 0xd', None, '... (stage 13: it leaves)'),
        (0x26EF11, 'movss xmm2, dword ptr [rip + {rip}]', 0x23C76FC, 'the landing decision: a player within 50 m ...'),
        (0x26EF3B, 'call 0x4d6930', None, '... of its landing point ...'),
        (0x26EF4B, 'mov rcx, qword ptr [rip + {rip}]', 0x3326D10, '... and mission-wide state ...'),
        (0x26EFBF, 'mov edx, 6', None, '... then it lands (stage 6)'),
        (0x26F09E, 'movss xmm3, dword ptr [rip + {rip}]', 0x23C7654, 'the circle: a 30 m constant ...'),
        (0x26F0B4, 'call 0x4d5e60', None, '... around its anchor'),
        (0x4D6957, 'movsd xmm0, qword ptr [rax + 0x1b0]', None, 'the landing point P+0x1B0'),
        (0x4B0034, 'mov r8, qword ptr [rip + {rip}]', 0x3326468, 'the abort check: the players ...'),
        (0x4B0049, 'add r8, 0x3ac', None, '... their state flags'),
    ],
    # The weapon-side components a mounted turret lives in (read-only diagnostics: PelicanTurretProbe). Each manager's
    # entity map: keys, capacity +8, empty key +0xC, multiplier +0x10 from the map offset.
    'turretComponents': [
        (0x5AB438, 'mov rbx, qword ptr [rip + {rip}]', 0x3326438, 'the mount component ...'),
        (0x5AB445, 'lea rcx, [rbx + 0x20]', None, '... its entity map +0x20'),
        (0x6E16F8, 'mov rbx, qword ptr [rip + {rip}]', 0x3326D70, 'the turret component ...'),
        (0x6E1705, 'lea rcx, [rbx + 0x28]', None, '... its entity map +0x28'),
        (0x619F98, 'mov rbx, qword ptr [rip + {rip}]', 0x33266D8, 'the projectile weapon component ...'),
        (0x619FA5, 'lea rcx, [rbx + 0x50]', None, '... its entity map +0x50'),
        (0x75E028, 'mov rbx, qword ptr [rip + {rip}]', 0x3326CE0, 'the weapon data component ...'),
        (0x75E035, 'lea rcx, [rbx + 0x30]', None, '... its entity map +0x30'),
    ],
    # A root's pose (read-only: the orbit's orientation sampling): the transform record's rotation, a quaternion
    # (x, y, z, w), beside its position +0x2E0.
    'pose': [
        (0x4C1D94, 'mov rbx, qword ptr [rip + {rip}]', 0x3326508, 'the transform component ...'),
        (0x4C1E36, 'imul rcx, rax, 0x308', None, '... a record (0x308) ...'),
        (0x4C1E47, 'movups xmm6, xmmword ptr [rcx + rax + 0x2d0]', None, '... its rotation +0x2D0 (x, y, z, w) ...'),
        (0x4C1E59, 'xorps xmm13, xmm0', None, '... conjugated with the sign mask'),
    ],
    # A mounted child (read-only: PelicanTurretProbe): the attachable component (records 0xAC, its link to its parent at
    # +0x0, the parent's node +0x4) and the mount system that spawns and removes the children.
    'attachment': [
        (0x81585A, 'mov rdi, qword ptr [rip + {rip}]', 0x3326698, 'the attachable component ...'),
        (0x815867, 'lea rcx, [rdi + 0x18]', None, '... its entity map +0x18 ...'),
        (0x814DD6, 'mov r8, qword ptr [rcx + 0x30]', None, '... its handles +0x30 ...'),
        (0x814DDD, 'imul rcx, r11, 0xac', None, '... its records, 0xAC each ...'),
        (0x814DF3, 'add rcx, qword ptr [rbx + 0x38]', None, '... at +0x38'),
        (0x5A802B, 'call 0xfdc140', None, 'the mount spawns each child with the entity creation ...'),
        (0x5A804E, 'call 0xb0a5f0', None, '... links it to its parent (a relation component) ...'),
        (0x5A84A6, 'call 0xfdc310', None, '... and removes the children with their parent'),
    ],
    # What a mounted turret fires, and what of it is per instance (read-only: PelicanTurretProbe 0.3.0; docs section
    # 15). The projectile a weapon fires comes from its weapon record's flags: a weapon_heat entity fires its resolved
    # ProjectileWeapon +0; a magazine entity its magazine record's chambered type +8, re-derived after every shot from
    # the magazine pattern (record +4 set) or the resolved ProjectileWeapon +0. "Resolved" is the per-instance copy when
    # the entity has one, else its type's record: a copy exists only when an entity delta (a ComponentEntityDelta) was
    # applied at creation, from the creation descriptor +0x50 or, for a mounted child, the global upgrade lists.
    'turretWeapon': [
        (0x7456EE, 'mov r9, qword ptr [rip + {rip}]', 0x3326660, 'the projectile a weapon fires: the weapon component ...'),
        (0x745712, 'mov r14, qword ptr [r9 + 0x28]', None, '... its entity map +0x28 ...'),
        (0x745751, 'mov rax, qword ptr [r9 + 0x50]', None, '... its records (40 bytes) +0x50 ...'),
        (0x74575D, 'bt r8d, 9', None, '... flag 0x200 (weapon_heat): its resolved ProjectileWeapon +0 ...'),
        (0x745787, 'test r8b, r8b', None, '... flag 0x80 (magazine): ...'),
        (0x7457F5, 'add rbx, qword ptr [r14 + 0x48]', None, '... its magazine record (16 bytes at +0x48) ...'),
        (0x745805, 'mov ecx, dword ptr [rbx + 8]', None, '... its chambered type +8 ...'),
        (0x74581D, 'cmp dword ptr [rbx + 4], ebp', None, '... (pattern flag +4) ...'),
        (0x745A4F, 'mov ebp, dword ptr [rax]', None, '... else its resolved ProjectileWeapon +0'),
        (0x7400BB, 'or dword ptr [rdi + rbx*8], 0x80', None, 'the flags are the components it has: 0x80 a magazine ...'),
        (0x74012A, 'or dword ptr [rdi + rbx*8], 0x100', None, '... 0x100 weapon_rounds ...'),
        (0x74013D, 'mov rcx, qword ptr [rip + {rip}]', 0x3326D48, '... the weapon_heat component (entity map +0x28) ...'),
        (0x74019A, 'or dword ptr [rdi + rbx*8], 0x200', None, '... 0x200 weapon_heat'),
        (0x7453C3, 'mov rbp, qword ptr [rip + {rip}]', 0x3326648, 'the magazine component (entity map +0x20) ...'),
        (0x745449, 'mov dword ptr [rdi + 8], eax', None, '... the chambered type is re-derived ...'),
        (0x6149EC, 'call 0x744690', None, '... after every shot (the fire path) ...'),
        (0x7447D4, 'mov eax, dword ptr [rcx]', None, '... from the resolved ProjectileWeapon +0 when no pattern ...'),
        (0x744800, 'mov eax, dword ptr [r15 + rax*4 + 4]', None, '... else the magazine pattern ...'),
        (0x74480B, 'mov dword ptr [rdi + 8], eax', None, '... into +8 (so +8 holds no lasting override)'),
        (0x51515A, 'mov rdi, qword ptr [r11 + 0x90]', None, 'resolved ProjectileWeapon: the copies\' entity map +0x90 ...'),
        (0x5151B9, 'add rax, qword ptr [r11 + 0xd0]', None, '... a per-instance copy (0x268) at +0xD0 ...'),
        (0x5151CC, 'jmp 0x514c10', None, '... else the type\'s record (shared)'),
        (0x61AFEF, 'call 0x514c10', None, 'a copy is made (0x61AF10) from the type\'s record ...'),
        (0x61B0A9, 'call 0x515540', None, '... patched by one entity delta (offset, size, bytes) ...'),
        (0x61B0B7, 'mov dword ptr [rsi + 0xc8], eax', None, '... and added (count +0xC8)'),
        (0x576AB4, 'call 0x61af10', None, 'the entity-delta dispatcher (a ProjectileWeapon delta) ...'),
        (0x5814B6, 'call 0x5740b0', None, '... runs at creation ...'),
        (0x581436, 'mov rdx, qword ptr [rsi + 0x50]', None, '... over the creation descriptor\'s delta list +0x50'),
        (0x5A7FEF, 'call 0x12e5590', None, 'a mounted child\'s list: only the global upgrade deltas for its type'),
        (0x5513ED, 'jmp 0x611b20', None, 'once per new projectile weapon (a component callback) ...'),
        (0x611C4C, 'mulss xmm1, dword ptr [r13 + 8]', None, '... the RPM (Y slot) of its resolved ProjectileWeapon ...'),
        (0x611C69, 'movss dword ptr [rbp + 0xc], xmm0', None, '... sets its instance record\'s shot interval +0xC = 60 / RPM'),
        (0x77E8E6, 'mov rcx, qword ptr [rip + {rip}]', 0x33267A0, 'the weapon_wind_up component (spin-up) ...'),
        (0x77E905, 'mov rdi, qword ptr [rcx + 0x28]', None, '... its entity map +0x28'),
    ],
    # The Gatling turret experiment (PelicanGatlingProof; docs section 16): the mount component's own per-instance
    # records and the game's own attach, relation unlink and removal routines, as the mount system calls them.
    'gatlingTurret': [
        # The mount component's callbacks (0x548E40-0x548F56): create, attach, remove.
        (0x548E79, 'call 0x5a7b60', None, 'mount create: the children are created ...'),
        (0x548E88, 'mov rax, qword ptr [rsi + 0x50]', None, '... and {count, child network ids} kept at +0x50 (24 bytes)'),
        (0x548F1A, 'jmp 0x5a8aa0', None, 'mount attach callback ...'),
        (0x548F23, 'jmp 0x5a8320', None, 'mount remove callback'),
        # Attach (0x5A8AA0): each child is attached by the game's attach routine, and its entity kept per slot.
        (0x5A8B9C, 'mov r8, qword ptr [rdx + 0x6d8]', None, 'the parent unit\'s node by the slot\'s node name ...'),
        (0x5A8BB5, 'mov r8d, dword ptr [r13 + 0xc]', None, '... attach: the parent\'s unit link ...'),
        (0x5A8BBB, 'mov edx, dword ptr [rdi + 8]', None, '... the child entity ...'),
        (0x5A8BBE, 'mov r9d, eax', None, '... the node ...'),
        (0x5A8BEA, 'mov rcx, qword ptr [rip + {rip}]', 0x3326698, '... the attachable manager ...'),
        (0x5A8BFD, 'call 0x812540', None, '... the attach routine'),
        (0x5A8D0B, 'mov dword ptr [r14 + rbp*4], r8d', None, 'the child entity kept in the mount record +0x48 (per slot)'),
        # The attach routine 0x812540(attachable manager, child, parent unit link, node, &offset, &rotation, float).
        (0x812568, 'mov ebx, r8d', None, 'attach: the parent unit link ...'),
        (0x812574, 'mov dword ptr [rsp + 0x38], r9d', None, '... the node ...'),
        (0x81256B, 'mov rsi, qword ptr [rbp + 0xa0]', None, '... &offset (12 bytes) ...'),
        (0x812623, 'mov rax, qword ptr [rdx + 0x720]', None, '... both units must be alive ...'),
        (0x81265A, 'cmp dword ptr [r13 + 0xc], ebx', None, '... and not the same unit ...'),
        (0x8126DD, 'movsd qword ptr [r12 + 0x8c], xmm0', None, '... the offset into the child\'s attachable +0x8C ...'),
        (0x8126D6, 'mov rax, qword ptr [rbp + 0xa8]', None, '... &rotation ...'),
        (0x8126F2, 'movaps xmm0, xmmword ptr [rax]', None, '... the rotation (16-byte aligned) ...'),
        (0x8126F5, 'movups xmmword ptr [r12 + 0x98], xmm0', None, '... into +0x98 ...'),
        (0x812EA1, 'call qword ptr [r10 + 0xc8]', None, '... then the engine links the units at the node'),
        # Remove (0x5A8320): per slot child: the relation unlinked, the entity removed, the link cleared.
        (0x5A851C, 'mov rax, qword ptr [rbp + 0x48]', None, 'remove: the mount record +0x48 ...'),
        (0x5A8520, 'lea rdx, [r15 + rcx*2]', None, '... (6 per mount: index * 6 + slot) ...'),
        (0x5A8524, 'mov ecx, dword ptr [rax + rdx*4]', None, '... names the child entity ...'),
        (0x5A83D8, 'je 0x5a8596', None, '... none alive: the slot is skipped ...'),
        (0x5A83E4, 'mov rdx, rbp', None, '... relation unlink (child, the mount manager, ...'),
        (0x5A83E1, 'mov r8d, edi', None, '... the parent) ...'),
        (0x5A83E7, 'call 0xb0b020', None, '... 0xB0B020 ...'),
        (0x5A849D, 'mov rcx, qword ptr [rip + {rip}]', 0x346BF98, '... the world ...'),
        (0x5A84A6, 'call 0xfdc310', None, '... the entity removed ...'),
        (0x5A858E, 'mov dword ptr [r9 + rax], 0', None, '... and its attachable link cleared'),
        # The relation unlink: no relation, nothing done.
        (0xB0B0B0, 'jmp 0xb0b1a6', None, 'unlink: the child has no relation: it returns'),
        # The type tables the experiment reads to show no shared definition changed (read-only).
        (0x514C1F, 'mov r10, qword ptr [rax + 0xf12e80]', None, 'ProjectileWeapon types: component world +0xF12E80 ...'),
        (0x514C37, 'imul eax, edx, 0x21e', None, '... 542 slots (resource mod 542) ...'),
        (0x514C98, 'add rax, 0x21e0', None, '... records (0x268) from +0x21E0'),
        (0x4F32FF, 'mov r10, qword ptr [rax + 0xf124a0]', None, 'magazine types: component world +0xF124A0 ...'),
        (0x4F3317, 'imul eax, edx, 0x21c', None, '... 540 slots ...'),
        (0x4F3371, 'add rcx, 0x36', None, '... records (160) from +0x21C0'),
        # Why a mounted child can survive the removal (PelicanGatlingProof 0.1.0 live: the chin turret stayed). The
        # removal 0xFDC310 queues an entity only when its network object is not flagged; a flagged one gets a removal
        # request instead. Each queued entity is destroyed by 0xFDC820 with the world's own entity record.
        (0xFDC339, 'mov rdx, qword ptr [rip + {rip}]', 0x346BF98, 'removal of a networked entity: the world ...'),
        (0xFDC340, 'mov rcx, qword ptr [rdx + 8]', None, '... its network manager (world +8) ...'),
        (0xFDC346, 'call 0xfde390', None, '... flagged: only a removal request is sent ...'),
        (0xFDE3DD, 'mov r11, qword ptr [rbx + 0xb020]', None, 'the network manager\'s object map +0xB020 ...'),
        (0xFDE420, 'movzx ebx, byte ptr [rax + rbx + 0x201c]', None, '... the flag, +0x201C + its index'),
        (0xFDC3EF, 'mov rcx, qword ptr [rdi + 0xf3ef20]', None, 'not flagged: the pending removal list +0xF3EF20 ...'),
        (0xFDC3F9, 'inc dword ptr [rdi + 0xf3ef18]', None, '... count +0xF3EF18'),
        (0xFDC7DC, 'lea rdx, [rbx + rax*8]', None, 'each pending removal: the world\'s entity record ...'),
        (0xFDC7E0, 'call 0xfdc820', None, '... destroyed by 0xFDC820 ...'),
        (0xFDC869, 'test r8b, r8b', None, '... not forced: ...'),
        (0xFDC86E, 'mov ebp, dword ptr [rdx + 0x10]', None, '... a networked entity (record +0x10) ...'),
        (0xFDC897, 'call rdi', None, '... passes the network layer\'s ownership check ...'),
        (0xFDC8A3, 'test byte ptr [rdx + 0x14], 1', None, '... else it was created here (+0x14 bit 0) ...'),
        (0xFDC8B7, 'call 0xb4bad0', None, '... then it is destroyed'),
        (0xFDC1A4, 'lea r14, [r15*2 + 0x1e65e3]', None, 'the entity record: world + 0xF32F18 + index * 24 ...'),
        (0xFDC1AF, 'lea r14, [rsi + r14*8]', None, '... (the record the component handles point at)'),
        (0xFDC526, 'mov rdi, qword ptr [rax + 0x160]', None, 'the network-aware removal asks the owner ...'),
        (0xFDC54A, 'cmp rdi, qword ptr [rcx + 0xb398]', None, '... this machine: 0xFDC310 ...'),
        (0xFDC59C, 'call 0xfdc310', None, '... else a request to the owner'),
        # The removal 0xFDC310(world, entity): deferred.
        (0xFDC32D, 'call 0xfd9af0', None, 'removal: the entity\'s network id ...'),
        (0xFDC370, 'mov ecx, 0x14b715b6', None, '... not ours: a removal request is sent ...'),
        (0xFDC399, 'mov r8d, dword ptr [rdi + 0xf1aeb8]', None, '... ours: queued in the world\'s removal map'),
    ],
    # The Pelican chin turret's own weapon behaviour (PelicanWeaponBehaviorProof; docs section 17): its AI (behaviour 645)
    # fires in a fixed 0.5 s window (stage 3, from P+0x180) and re-aims at least 1.5 s (stage 2, from P+0x178); the
    # Gatling Sentry's AI (213) holds the trigger for its whole firing stage. The magazine has its own per-instance copy
    # routine (0x770B10), like the projectile weapon's.
    'pelicanWeapon': [
        (0x478D9D, 'mov rcx, qword ptr [rcx + 8]', None, 'behaviour 645 (the chin turret): P ...'),
        (0x478DF4, 'mov edx, 4', None, 'stage 3 (firing): no target: stage 4 ...'),
        (0x478E0A, 'je 0x478dd3', None, '... no line of fire: stage 1 ...'),
        (0x478E10, 'mov rcx, qword ptr [rax + 0x180]', None, '... else its stage-3 entry time P+0x180 ...'),
        (0x478E1E, 'add rcx, 0x7a120', None, '... + 0.5 s ...'),
        (0x478E25, 'cmp rcx, qword ptr [rax + 0x18]', None, '... passed (the game clock) ...'),
        (0x478E2F, 'mov edx, 2', None, '... back to stage 2 (the burst ends)'),
        (0x4507FF, 'mov rcx, qword ptr [rcx + 0x178]', None, 'stage 2 (aiming): its entry time P+0x178 ...'),
        (0x450806, 'add rcx, 0x16e360', None, '... + 1.5 s ...'),
        (0x450867, 'mov edx, 3', None, '... and aimed: stage 3 (the next burst)'),
        (0x450B06, 'cmp ecx, 3', None, 'a transition out of stage 3 ...'),
        (0x450B0E, 'call 0x4bc9e0', None, '... releases the trigger'),
        (0x450C41, 'mov qword ptr [r8 + 0x180], rcx', None, 'entering stage 3: P+0x180 = now ...'),
        (0x450C62, 'call 0x4bc940', None, '... pulls the trigger'),
        (0x450C8D, 'mov qword ptr [rcx + 0x178], rax', None, 'entering stage 2: P+0x178 = now'),
        (0x4BC9C9, 'call 0x786be0', None, 'the trigger: each of the wielder\'s weapon slots ...'),
        (0x4BC9D0, 'cmp ebx, 5', None, '... five'),
        (0x2846DF, 'mov qword ptr [r8 + 0x90], rdx', None, 'the Gatling Sentry (213) entering its firing stage ...'),
        (0x2846E6, 'jmp 0x4bc940', None, '... pulls the trigger ...'),
        (0x285861, 'cmp ecx, 0xc', None, '... and releases it only on leaving that stage (12) ...'),
        (0x285869, 'call 0x4bc9e0', None, '... (no fixed window: continuous fire)'),
        # The magazine's per-instance copy routine and the record the game derives from it.
        (0x574172, 'lea rcx, [r13 + 0x180]', None, 'the delta dispatcher: the magazine manager ...'),
        (0x57417F, 'call 0x770b10', None, '... its copy routine 0x770B10(manager, handle, delta entry)'),
        (0x770B58, 'mov rdi, qword ptr [rcx + 0x60]', None, 'magazine copies: the entity map +0x60 ...'),
        (0x770BE5, 'call 0x4f32f0', None, '... a new copy starts as the type\'s record ...'),
        (0x770C6A, 'call 0x515540', None, '... patched by the delta ...'),
        (0x770C9F, 'lea rcx, [rbx + 0x80]', None, '... indexed back (+0x80) ...'),
        (0x770CBD, 'add rdx, qword ptr [rbx + 0xa0]', None, '... written at +0xA0 (160 bytes; no capacity check)'),
        (0x76F6AF, 'mov dword ptr [rbx + 4], 0x80', None, 'magazine copies\' capacity +4: 128 ...'),
        (0x76FB91, 'mov dword ptr [r14 + 4], ecx', None, '... grown by 0x180'),
        (0x4F3794, 'mov rdi, qword ptr [r11 + 0x60]', None, 'the magazine resolver: its own copy first ...'),
        (0x4F37EA, 'add rax, qword ptr [r11 + 0xa0]', None, '... at +0xA0, else the type\'s record'),
        (0x76D943, 'mov dword ptr [rbx + 4], ecx', None, 'a magazine record: +4 = the resolved pattern mode ...'),
        (0x76D94A, 'mov dword ptr [rbx], ecx', None, '... +0 the rounds ...'),
        (0x76DA00, 'cmp dword ptr [rax], edi', None, '... with a pattern: +0xC = the leading non-zero entries ...'),
        (0x76DA2E, 'cmp edx, 0x20', None, '... of 32'),
    ],
    # The Gatling AI on the chin turret (PelicanGatlingAIProof; docs section 18): a Behavior record's behaviour id (+0) is
    # per instance, written at creation and read by the Behavior update every frame to choose the code it runs; the record
    # is generic (the same layout for every behaviour). The Gatling Sentry's AI (213) walks its own stage machine.
    'pelicanAI': [
        (0x8434C9, 'mov edx, dword ptr [rsi + rbp]', None, 'every update: the record\'s behaviour id (+0) ...'),
        (0x8434D4, 'call 0x472f60', None, '... chooses the code it runs ...'),
        (0x472FAC, 'mov eax, dword ptr [r8 + rax*4 + 0x4795c4]', None, '... through the behaviour jump table'),
        (0x8434A0, 'cmp dword ptr [rsi + rbp + 0xc], -1', None, 'a pending stage (P+4) ...'),
        (0x8434C4, 'call 0x48ee50', None, '... is applied by that behaviour\'s own transition'),
        (0x842417, 'call 0x8449b0', None, 'creation: the id written is replicated (mask 2)'),
        (0x842428, 'lea rax, [rdi + 8]', None, 'the context P = the record + 8: generic for every behaviour'),
        (0x47522D, 'mov rdx, qword ptr [rcx + 8]', None, 'behaviour 213 (the Gatling Sentry): P ...'),
        (0x47523E, 'mov ecx, dword ptr [r8 + rax*4 + 0x47a1a4]', None, '... its 12 stages ...'),
        (0x475252, 'mov rcx, qword ptr [rdx + 0x180]', None, 'stage 1: P+0x180 ...'),
        (0x475259, 'add rcx, 0x1e8480', None, '... + 2 s ...'),
        (0x47526A, 'mov edx, 6', None, '... then stage 6'),
        (0x4752B9, 'mov eax, dword ptr [rdx + 0x1e0]', None, 'stage 6: P+0x1E0 chooses stage 7, 8 or 9'),
        (0x4752ED, 'mov edx, dword ptr [rdx + 0x1e0]', None, 'stages 7-9: P+0x1E0 bit 2 ...'),
        (0x4752FC, 'shr edx, 2', None, '... chooses stage 2 or 3'),
        (0x280A26, 'mov edx, 0xa', None, 'stage 2: neither weapon check passes (0x4BB080, 0x4BB440): stage 10 ...'),
        (0x47530F, 'call 0x4a9710', None, '... stage 10 leaves only with bit 48 of a component (game+0x3326430) ...'),
        (0x47531A, 'shr rbx, 0x30', None, '... (absent on the chin turret: 0)'),
        (0x47535F, 'call 0x2846f0', None, 'stage 12: the firing stage (entered through 0x2846D0: the trigger)'),
        (0x4507A2, 'mov dword ptr [rcx + 0x10], eax', None, 'the shared turret AI: the target entity is P+0x10'),
        # How a behaviour starts: creation sets stage 0 and, for a behaviour with stages, the pending stage 1, so the first
        # update enters stage 1 through the behaviour's own transition (0x495F20 returns the stage count: 213 13, 645 4).
        (0x84221E, 'xor r12d, r12d', None, 'creation: stage 0 ...'),
        (0x842459, 'call 0x495f20', None, '... a behaviour with stages ...'),
        (0x842462, 'mov dword ptr [rdi + 0xc], 1', None, '... gets the pending stage 1'),
        # The chin turret's stage 4: its turret is not active (the turret component's per-instance byte, +0x58, 16 bytes
        # each); entering it parks the aim and clears the target; it leaves to stage 1 when the turret is active.
        (0x478DC6, 'call 0x4b0810', None, '645 stage 4: the turret active? ...'),
        (0x478DD3, 'mov edx, 1', None, '... then stage 1'),
        (0x4B0891, 'jmp 0x6e01f0', None, 'the active check ...'),
        (0x6E028A, 'mov rax, qword ptr [r10 + 0x58]', None, '... the turret component\'s per-instance records +0x58 ...'),
        (0x6E0291, 'movzx eax, byte ptr [rax + rcx*8]', None, '... byte +0 (16 bytes each)'),
        (0x450C02, 'mov byte ptr [rax + 0x70], 1', None, 'entering 645 stage 4: the aim parked ...'),
        (0x450C27, 'mov dword ptr [rcx + 0x10], eax', None, '... the target cleared (no trigger: only stage 3 pulls it)'),
        # The game's own behaviour change, SetBehaviour(manager, entity, behaviour) (0x843EA0): it exits the old behaviour
        # through its own transition to stage 0, writes and replicates the new id, and enters the new one at stage 1.
        (0x197D83, 'mov rcx, qword ptr [rip + {rip}]', 0x3326740, 'a caller: the Behavior manager ...'),
        (0x197D8A, 'mov edx, dword ptr [rax + 8]', None, '... the entity ...'),
        (0x197D7D, 'mov r8d, 0x53', None, '... a behaviour id ...'),
        (0x197D8D, 'call 0x843ea0', None, '... SetBehaviour'),
        (0x1185B98, 'call 0x843ea0', None, 'another: back to the type\'s own behaviour'),
        (0x843F31, 'cmp dword ptr [rbx], esi', None, 'SetBehaviour: already that behaviour: nothing ...'),
        (0x843F3E, 'call 0x843cf0', None, '... a pending behaviour change dropped ...'),
        (0x843F5F, 'xor r8d, r8d', None, '... the old behaviour\'s own transition ...'),
        (0x843F67, 'call 0x48ee50', None, '... to stage 0 (its exit) ...'),
        (0x843F7A, 'mov dword ptr [rbx], esi', None, '... the new id ...'),
        (0x843F8A, 'mov r8d, 2', None, '... replicated (mask 2) ...'),
        (0x843F97, 'mov r8d, 1', None, '... the new behaviour\'s own transition ...'),
        (0x843FA2, 'call 0x48ee50', None, '... to stage 1 (its start)'),
    ],
    # Research only (docs section 15, follow-up): a weapon's rate is its current RPM (manager +0x80, entry +4), a
    # replicated per-instance value; the shot interval follows it every update. The system pass resets it from the
    # resolved slots only when the mission fire-rate modifier changes (and every update for weapon_heat weapons).
    # The ejected casing (section 19): a projectile weapon's fire effects (0x612290), from its RESOLVED ProjectileWeapon
    # (its per-instance copy when it has one): effect B is the casing, particles +0xB0 emitted at the nodes +0xB8..+0xC4
    # ("ejector"), cycled per shot, with its parameters +0xD4..+0xDC. The effect is the game's pooled particle system
    # for that particles resource (0x13024B0: one per resource, shared by every weapon that ejects it), looked up on the
    # weapon's first shot and kept in the weapon's own instance record (+0x90). So a per-instance copy whose +0xB0 names
    # another casing changes that weapon's casing, provided it is written before the weapon's first shot.
    'casing': [
        (0x611BD8, 'call 0x515100', None, 'creation: the resolved ProjectileWeapon ...'),
        (0x6120D2, 'mov edx, dword ptr [r13 + 0xa8]', None, '... the node of effect A (+0xA8) ...'),
        (0x61211A, 'mov dword ptr [rbp + 0x68], eax', None, '... into the instance record +0x68 ...'),
        (0x612120, 'lea rbx, [r13 + 0xb8]', None, '... the casing\'s nodes (+0xB8, "ejector") ...'),
        (0x612167, 'mov dword ptr [rsi + rbx - 0x44], eax', None, '... into the instance record +0x74 ...'),
        (0x612174, 'cmp edi, 4', None, '... (four at most)'),
        (0x6122CC, 'call 0x515100', None, 'the fire effects: the resolved ProjectileWeapon (copy or type) ...'),
        (0x6122D8, 'imul rbx, rbx, 0xa8', None, '... the weapon\'s instance record (0xA8) ...'),
        (0x61244A, 'cmp qword ptr [rsi + 0xb0], 0', None, '... the casing particles +0xB0 ...'),
        (0x61245E, 'mov eax, dword ptr [rbx + 0x70]', None, '... the next ejector node (cycled) ...'),
        (0x612461, 'mov r12d, dword ptr [rbx + rax*4 + 0x74]', None, '... from the instance record ...'),
        (0x61248E, 'mov edx, dword ptr [rbx + 0x90]', None, '... the casing effect kept in the instance record +0x90 ...'),
        (0x61249B, 'mov ecx, dword ptr [rsi + 0xdc]', None, '... or, the first time, from the parameters +0xDC ...'),
        (0x6124A1, 'mov r9d, dword ptr [rsi + 0xd8]', None, '... +0xD8 ...'),
        (0x6124A8, 'mov r8d, dword ptr [rsi + 0xd4]', None, '... +0xD4 ...'),
        (0x6124AF, 'mov rdx, qword ptr [rsi + 0xb0]', None, '... and the particles +0xB0 ...'),
        (0x6124BA, 'call 0x13024b0', None, '... the pooled particle system for that resource ...'),
        (0x6124BF, 'mov dword ptr [rbx + 0x90], eax', None, '... kept for every later shot'),
        (0x13024DD, 'call 0x1733410', None, 'the pool: one particle system per particles resource ...'),
        (0x13024EA, 'cmp qword ptr [rax], rbx', None, '... reused when it exists ...'),
        (0x1302580, 'call rax', None, '... else created'),
        (0x612A13, 'call 0x515100', None, 'a shot: the resolved ProjectileWeapon ...'),
        (0x6151D7, 'cmp dword ptr [r8 + 0x98], 0', None, '... (+0x98 and +0x234 clear: both turrets) ...'),
        (0x6151F8, 'call 0x612290', None, '... the fire effects, the casing among them ...'),
        (0x61520D, 'mov rdx, qword ptr [r8 + 0xe0]', None, '... the muzzle flash +0xE0 (not the casing) ...'),
        (0x615259, 'mov dword ptr [rax + 0x88], r14d', None, '... kept in the instance record +0x88'),
    ],
    # The first shot after a weapon copy: a magazine weapon fires the type its magazine record holds chambered (+8);
    # after every shot 0x744690 chambers the next one from the resolved ProjectileWeapon +0 (or the pattern) and counts
    # one round. The round chambered before the copy is fired first; there is no other rechamber routine.
    'firstShot': [
        (0x6149EC, 'call 0x744690', None, 'after a shot ...'),
        (0x7447B6, 'call 0x515100', None, '... the resolved ProjectileWeapon ...'),
        (0x7447D4, 'mov eax, dword ptr [rcx]', None, '... its projectile type (no pattern) ...'),
        (0x744800, 'mov eax, dword ptr [r15 + rax*4 + 4]', None, '... or the pattern entry ...'),
        (0x74480B, 'mov dword ptr [rdi + 8], eax', None, '... is chambered for the next shot ...'),
        (0x74481C, 'dec dword ptr [rdi]', None, '... and one round counted'),
    ],
    # The rate a new projectile weapon starts with: its resolved RPM (Y slot, +8), x0.9 while mission modifier 0x33 is
    # active; the shot interval is 60 / that.
    'rateSeed': [
        (0x611C04, 'cmp dword ptr [rcx + 0xac21c], 4', None, 'creation: the mission modifier state ...'),
        (0x611C20, 'cmp dword ptr [rdx], 0x33', None, '... modifier 0x33 ...'),
        (0x611C4C, 'mulss xmm1, dword ptr [r13 + 8]', None, '... times the resolved RPM (Y slot) ...'),
        (0x611C65, 'divss xmm0, xmm1', None, '... 60 / RPM ...'),
        (0x611C69, 'movss dword ptr [rbp + 0xc], xmm0', None, '... the shot interval'),
    ],
    # The Gatling AI's firing stage (section 19d): stage 12 leaves only when its weapon is empty or its "target lost" flag
    # (P+0x1E0 bit 4) has been set for 1 s, both through its own transition (0x285810) to stage 4, which releases the
    # trigger. A re-pick clears the flag; nothing in stage 12 checks the barrel's angle (only stage 5 does, 3 degrees,
    # before it enters stage 12). A pending stage (record +0xC) is consumed by the Behavior update through the same
    # transition, for 213 in every stage but 11.
    'ai213': [
        (0x285704, 'call 0x4bb080', None, 'stage 12: the rounds left (fraction) ...'),
        (0x28571C, 'ja 0x285746', None, '... none: stage 4 ...'),
        (0x285722, 'test byte ptr [rdx + 0x1e0], 0x10', None, '... or the target-lost flag ...'),
        (0x285732, 'mov rdx, qword ptr [rdx + 0x190]', None, '... set at P+0x190 ...'),
        (0x285739, 'add rdx, 0xf4240', None, '... 1 s ago ...'),
        (0x285746, 'mov edx, 4', None, '... stage 4 ...'),
        (0x28574E, 'call 0x285810', None, '... through its own transition'),
        (0x28583E, 'cmp dword ptr [rax + 8], edx', None, 'the transition: not while already entering that stage ...'),
        (0x28584E, 'mov dword ptr [rax + 4], 0xffffffff', None, '... the pending stage cleared ...'),
        (0x285861, 'cmp ecx, 0xc', None, '... leaving stage 12 ...'),
        (0x285869, 'call 0x4bc9e0', None, '... releases the trigger ...'),
        (0x28587B, 'mov dword ptr [rax], ebx', None, '... the new stage ...'),
        (0x28588F, 'call 0x8449b0', None, '... replicated'),
        (0x8434B7, 'mov r8d, dword ptr [rsi + rbp + 0xc]', None, 'the Behavior update: a pending stage ...'),
        (0x4963B8, 'cmp r8d, 0xb', None, '... (213: in any stage but 11) ...'),
        (0x48FE62, 'call 0x285810', None, '... goes through 213\'s own transition'),
        (0x283E02, 'call 0x4b54d0', None, 'stage 5: fire only with the barrel within 3 degrees ...'),
        (0x28408D, 'call 0x285810', None, '... then stage 12'),
        (0x4B5571, 'call 0x7582d0', None, 'the barrel angle: the weapon\'s aim node (an engine node pose) ...'),
        (0x7583B7, 'call rax', None, '... read through the engine, not data'),
        (0x280A26, 'mov edx, 0xa', None, 'stage 2: no rounds and no spare magazines: stage 10'),
    ],
    # The ammunition (section 19e): the magazine manager's per-entity 12-byte entries (+0x50) hold the spare magazines (+0),
    # the authoritative, replicated rounds (+4) and a chamber-empty flag (+8); its 16-byte records (+0x48) a working copy of
    # the rounds that the fire loop takes from +4. The capacity is the RESOLVED magazine's +0x88 (the per-instance copy
    # when one exists). A weapon spawns with capacity - 1 rounds and one chambered (+0x9C). A reload needs a reload
    # animation (the reload type's +4): the chin turret's is 0, the Gatling Sentry has none, so neither reloads.
    'ammo': [
        (0x742A9B, 'mov ebp, dword ptr [rax + rdx*4 + 4]', None, 'the rounds left: entry +4 ...'),
        (0x74353E, 'mov esi, dword ptr [rax + 0x88]', None, '... over the resolved capacity +0x88 ...'),
        (0x743534, 'call 0x4f3740', None, '... (the resolved magazine) ...'),
        (0x4F3794, 'mov rdi, qword ptr [r11 + 0x60]', None, '... the per-instance copy when one exists'),
        (0x4BB10C, 'call 0x743410', None, 'the AI\'s weapon checks read both'),
        (0x4BB1AC, 'call 0x742900', None, '...'),
        (0x76E34B, 'mov dword ptr [rcx + rax + 4], r14d', None, 'a shot: the rounds into entry +4 ...'),
        (0x76E363, 'mov edx, 0xd7a5d63e', None, '... replicated from there'),
        (0x745CDE, 'mov eax, dword ptr [rax + rdx*4 + 4]', None, 'the fire loop: entry +4 ...'),
        (0x745CE2, 'mov dword ptr [rcx + r8*8], eax', None, '... into the record\'s working rounds +0'),
        (0x7447BB, 'cmp byte ptr [r15 + 0x9c], 0', None, 'a weapon with a chamber (+0x9C) ...'),
        (0x76F048, 'mov eax, dword ptr [rax + 0x88]', None, 'spawn: the capacity ...'),
        (0x76EE50, 'mov ecx, dword ptr [rax + 0x8c]', None, '... the spare magazines ...'),
        (0x76EE56, 'mov r15d, dword ptr [rax + 0x94]', None, '... at most +0x94 ...'),
        (0x76EFEA, 'mov dword ptr [rax + r15*4], edi', None, '... into entry +0'),
        (0x774D13, 'call 0x4fd220', None, 'a reload: the reload type ...'),
        (0x774D1B, 'cmp dword ptr [rax + 4], r15d', None, '... no reload animation (+4 = 0): no reload'),
    ],
    # The rounds are a network field (section 20a): a shot queues entry +4 for replication by POINTER (0xFD97E0); the
    # world update's flush (0xFDAF6C -> 0xFDE0F0) calls the engine's field update with clamp = 1, which saturates the
    # host's own value in place to the field's range; the next frame's sync copies entry +4 into the record (0x6178F0).
    'ammoNetwork': [
        (0x76E363, 'mov edx, 0xd7a5d63e', None, 'a shot queues the rounds (entry +4) ...'),
        (0x76E371, 'jmp 0xfd97e0', None, '... by pointer ...'),
        (0xFDAF25, 'mov byte ptr [rax + 0x301c], 1', None, 'the world update batches the queue ...'),
        (0xFDAF6C, 'call 0xfdc780', None, '... and flushes it after the systems ...'),
        (0xFDE0FC, 'mov byte ptr [rsp + 0x20], 1', None, '... with clamp = 1 ...'),
        (0xFDE105, 'mov r10, qword ptr [r8 + 0xa0]', None, '... through the engine\'s field update (the value clamped in place) ...'),
        (0xFDE12F, 'call qword ptr [r10 + 0xb8]', None, '... then into the network state'),
        (0x6178F0, 'call 0x745bc0', None, 'every frame the record takes the (clamped) rounds ...'),
        (0x617919, 'call 0x616ac0', None, '... before the weapons fire'),
        (0x76E0F0, 'mov eax, 0xffffffff', None, 'the game\'s refill (0x76E080) ...'),
        (0x76E135, 'mov eax, dword ptr [rax + 0x88]', None, '... to the resolved capacity'),
    ],
    # The body's heading (section 20e): in flight modes 1 and 3 the hover controller (game+0x3326DB0) owns the rotation:
    # it turns the body's forward toward a per-instance desired facing D (sim record +0xC) through its own thrusters and
    # writes (and replicates) the flight entry's rotation, which the body follows. Behaviour 667 sets D toward its hover
    # point in its approach and departure stages; its hold (stage 6, mode 1) never sets it, so the heading stays.
    'heading': [
        (0x573D01, 'call 0x84b0f0', None, 'the systems pass: the flight ...'),
        (0x573D10, 'call 0x6d1980', None, '... then the hover controller'),
        (0x6D1A24, 'cmp dword ptr [rcx + 0x18], ebx', None, 'the controller: the simulated (authority) entries ...'),
        (0x6D1A5E, 'cmp byte ptr [rax + rcx*8 + 0x15], 0', None, '... not crashed (+0x15) ...'),
        (0x6D1A78, 'cmp byte ptr [rax + rcx*8 + 0x14], 0', None, '... and enabled (+0x14) ...'),
        (0x6D1E27, 'addss xmm6, dword ptr [rbx + r15*8 + 0x18]', None, '... fixed substeps (sim record +0x18) ...'),
        (0x6D2847, 'movss xmm8, dword ptr [rbx + r15*8 + 0xc]', None, '... toward the desired facing D (+0xC)'),
        (0x6D4E3B, 'mov r11, qword ptr [rip + {rip}]', 0x3326DB0, 'the game\'s own setter of D ...'),
        (0x6D4EC0, 'mov rax, qword ptr [r11 + 0x48]', None, '... the sim records +0x48 ...'),
        (0x6D4EC4, 'lea rdx, [rcx + rcx*4]', None, '... 0x28 each ...'),
        (0x6D4ED0, 'movsd qword ptr [rcx + 0xc], xmm0', None, '... D at +0xC (a plain store)'),
        (0x45A801, 'call 0x4c1aa0', None, '667 stage 3: D toward its hover point'),
        (0x45C161, 'call 0x4c4a70', None, '667 stage 6: flight mode 1 (the controller owns the rotation)'),
        (0x848940, 'mov dword ptr [rdi + 0x52c], eax', None, 'the flight record\'s mode +0x52C'),
    ],
    # The Gatling AI's target choice (section 20c): it re-scores every perceived candidate only when its re-pick time
    # (P+0x90) is due (1 s with a target); every stage entry makes it due. There is no lock field. The setter (0x4AF4E0)
    # copies the chosen perception entry in; the per-update refresh (0x4AF390) clears an invalid target and stamps when
    # the target was last seen (P+0x20).
    'targetChoice': [
        (0x2846DF, 'mov qword ptr [r8 + 0x90], rdx', None, 'entering stage 12: the re-pick is due now ...'),
        (0x284798, 'cmp qword ptr [rcx + 0x90], rdx', None, '... stage 12 re-scores only when P+0x90 is due ...'),
        (0x28479F, 'ja 0x284fbe', None, '... otherwise it keeps its target ...'),
        (0x2847CF, 'mov qword ptr [rcx + 0x90], rax', None, '... and sets the next re-pick'),
        (0x284F82, 'call 0x4af4e0', None, 'the best candidate through the setter'),
        (0x2834D1, 'cmp qword ptr [rcx + 0x90], rdx', None, 'stage 5 re-picks on the same timer'),
        (0x283D5D, 'cmp qword ptr [rcx + 0xa8], rax', None, 'stage 5 checks fire every 0.5 s (P+0xA8)'),
        (0x4AF41C, 'mov dword ptr [rbx + 0x10], eax', None, 'the refresh: an invalid target cleared ...'),
        (0x4AF4A2, 'mov qword ptr [rbx + 0x20], rax', None, '... and when it was last seen (P+0x20)'),
    ],
    # Where a turret's bullets go (section 20b): the targeting system's aim point T (the target's aim node nearest the
    # turret), the wielder's desired aim (T plus a lead for the muzzle's own velocity), recoil from the weapon's OWN
    # WeaponData instance record (its two recoil blocks, copied from its type at creation), the turret's achieved
    # pointing written back into WeaponData +0, the shot from the muzzle toward it, spawned without the muzzle's velocity.
    'aim': [
        (0x6BCF27, 'movsd qword ptr [rcx + r13 + 8], xmm0', None, 'targeting: the aim point T (state +8)'),
        (0x753F00, 'movsd qword ptr [r14 + rax*4 + 0xfc], xmm3', None, 'WeaponData: the muzzle position (+0xFC) ...'),
        (0x753EE8, 'movsd qword ptr [r14 + rcx*4 + 0x21c], xmm0', None, '... and its velocity (+0x21C)'),
        (0x7846A9, 'imul rax, rax, 0x1d0', None, 'a shot\'s recoil: the wielder record (0x1D0) ...'),
        (0x784960, 'imul rax, rcx, 0x3f0', None, '... the weapon\'s own WeaponData instance record (0x3F0) ...'),
        (0x78496E, 'add rax, qword ptr [r11 + 0x58]', None, '... (records +0x58) ...'),
        (0x784C94, 'mov rdi, qword ptr [rsp + 0x50]', None, '...'),
        (0x784CAC, 'lea rdx, [rdi + 0x1c]', None, '... recoil block A (+0x1C) ...'),
        (0x784CCF, 'lea rdx, [rdi + 0x38]', None, '... recoil block B (+0x38) ...'),
        (0x784CE2, 'lea r8, [rbx + 0x14]', None, '... into the wielder slot\'s aim recoil angles (+0x14)'),
        (0x615984, 'xor r14d, r14d', None, 'the shot: no inherited velocity ...'),
        (0x616612, 'call 0x13a9830', None, '... into the projectile spawn'),
    ],
    'turretRate': [
        (0x617919, 'call 0x616ac0', None, 'every update, each projectile weapon ...'),
        (0x616E93, 'movss xmm1, dword ptr [rcx + rax*4 + 4]', None, '... its current RPM ...'),
        (0x616E99, 'ucomiss xmm1, dword ptr [r14 + rbp + 0x64]', None, '... against the cached RPM (instance +0x64) ...'),
        (0x616EA8, 'movss xmm0, dword ptr [rip + {rip}]', 0x23C7740, '... changed: 60.0 ...'),
        (0x616EB0, 'divss xmm0, xmm1', None, '... / the current RPM ...'),
        (0x616EB9, 'movss dword ptr [r14 + rbp + 0x64], xmm1', None, '... cached ...'),
        (0x616EC0, 'movss dword ptr [r14 + rbp + 0xc], xmm0', None, '... is the new shot interval +0xC'),
        (0x616C2C, 'movss xmm0, dword ptr [r14 + rbp + 8]', None, 'the cooldown +8 ...'),
        (0x616C33, 'subss xmm0, xmm8', None, '... runs down every update'),
        (0x612CFD, 'movss xmm0, dword ptr [rax + 0xc]', None, 'each shot adds the interval +0xC ...'),
        (0x612D02, 'addss xmm0, dword ptr [rax + 8]', None, '... to the cooldown ...'),
        (0x612D07, 'movss dword ptr [rax + 8], xmm0', None, '... +8'),
        (0x612238, 'call 0x6117c0', None, 'creation (0x611B20) seeds the rate ...'),
        (0x611856, 'test byte ptr [rcx + 0x14], 1', None, '... on the machine that created it (handle +0x14) ...'),
        (0x611941, 'mov dword ptr [rcx + rdx*4 + 4], eax', None, '... current RPM = its resolved slot ...'),
        (0x61195C, 'mov edx, 0x4cbcc2a2', None, '... replicated under 0x4CBCC2A2 ...'),
        (0x611964, 'call 0xfd97e0', None, '... by the replication call'),
        (0x617599, 'cmp dword ptr [rcx + 0x28], eax', None, 'the system pass: the mission fire-rate modifier state changed ...'),
        (0x6175C0, 'cmp dword ptr [rcx], 0x33', None, '... (modifier 0x33 ...'),
        (0x6175D2, 'movss xmm6, dword ptr [rip + {rip}]', 0x23C6CCC, '... x0.9) ...'),
        (0x617626, 'mov r15, qword ptr [rip + {rip}]', 0x3326D48, '... or a weapon_heat weapon ...'),
        (0x61784D, 'mov dword ptr [rcx + rdx*4 + 4], eax', None, '... its current RPM reset from its resolved slots ...'),
        (0x617851, 'mov edx, 0x4cbcc2a2', None, '... and replicated'),
        (0x617AC1, 'movss dword ptr [rax + rcx*4], xmm6', None, 'the rate-of-fire selector writes it too (replicated)'),
    ],
    # Installing a target the way the Gatling AI does (section 21): the Behavior update's context is {the entity's
    # handle record (handles +0x58, entity +8), P = its record + 8}; the setter 0x4AF4E0(context, entry) reads only P,
    # copies the perceiver's live 0x50-byte entry into P+0x10..0x5F, sets P+0x70 and the previous target P+0x68, follows
    # one redirect and tail-calls the refresh (validity, aim point, last seen); a null entry would clear the target (never
    # passed). The candidates are the perceiver's (P+0x60) lists A, B and C; perceived = the entry's sense bits against its
    # sensors' bits; hostile = the target's faction mask, non-zero and sharing no bit with the perceiver's; entity flags 25
    # (invalid) and 35 (scores 0); nothing beyond 100 m from the turret scores.
    'targetSet': [
        (0x8431C0, 'mov rax, qword ptr [rdi + 0x58]', None, 'the Behavior update: the handle records (+0x58) ...'),
        (0x8431C7, 'mov r14, qword ptr [rax + r12*8]', None, '... one pointer per record ...'),
        (0x8431DA, 'imul rsi, rcx, 0x1f8', None, '... the record (0x1F8) ...'),
        (0x8431EB, 'mov ebx, dword ptr [r14 + 8]', None, '... the handle names its entity (+8) ...'),
        (0x8431EF, 'lea r13, [rbp + 8]', None, '... P = the record + 8 ...'),
        (0x8431F6, 'mov qword ptr [rsp + 0x28], r14', None, '... the context: the handle ...'),
        (0x8431FB, 'mov qword ptr [rsp + 0x30], r13', None, '... then P'),
        (0x2847DA, 'mov ecx, dword ptr [rax + 0x60]', None, 'the Gatling AI\'s pick: its perceiver P+0x60 ...'),
        (0x2847DD, 'call 0x889830', None, '... its perception record ...'),
        (0x284A48, 'call 0x4a9710', None, '... a candidate\'s entity flags ...'),
        (0x284A4D, 'bt rax, 0x23', None, '... flag 35 scores 0 ...'),
        (0x284B5B, 'mov qword ptr [rbp + 0x18], 0x42c80000', None, '... nothing at 100 m from the turret scores ...'),
        (0x284F74, 'mov ecx, r14d', None, '... the best: its live entry ...'),
        (0x284F77, 'call 0x889940', None, '... from the lists ...'),
        (0x284F7F, 'mov rcx, rbx', None, '... with the update\'s context ...'),
        (0x284F82, 'call 0x4af4e0', None, '... through the setter'),
        (0x4AF4FA, 'mov r8, qword ptr [rcx + 8]', None, 'the setter reads P (context +8) ...'),
        (0x4AF501, 'test rdx, rdx', None, '... a null entry ...'),
        (0x4AF504, 'je 0x4af6d1', None, '... clears the target (never passed) ...'),
        (0x4AF50A, 'movups xmm0, xmmword ptr [rdx]', None, '... the entry copied into P+0x10..0x5F ...'),
        (0x4AF53D, 'mov byte ptr [rax + 0x70], 1', None, '... P+0x70 set ...'),
        (0x4AF558, 'mov dword ptr [rcx + 0x68], eax', None, '... the previous target P+0x68 ...'),
        (0x4AF571, 'mov rdi, qword ptr [rip + {rip}]', 0x3326D78, '... one redirect ...'),
        (0x4AF718, 'jmp 0x4af390', None, '... then the refresh ...'),
        (0x4AF39F, 'mov rbx, qword ptr [rcx + 8]', None, '... which reads P only ...'),
        (0x4AF407, 'bt rax, 0x19', None, '... and clears a target with entity flag 25'),
        (0x889846, 'mov rax, qword ptr [rip + {rip}]', 0x3326548, 'the perception manager: its map ...'),
        (0x88985E, 'mov r9d, dword ptr [rax + 0x38]', None, '... capacity +0x38 ...'),
        (0x889862, 'mov r11d, dword ptr [rax + 0x40]', None, '... multiplier +0x40 ...'),
        (0x889873, 'mov rbx, qword ptr [rax + 0x30]', None, '... slots +0x30 ...'),
        (0x889877, 'mov edi, dword ptr [rax + 0x3c]', None, '... empty key +0x3C'),
        (0x889942, 'imul r9, rax, 0x13f8', None, 'a perception record (0x13F8) ...'),
        (0x889950, 'add r9, qword ptr [rax + 0x50]', None, '... at +0x50 ...'),
        (0x889954, 'mov eax, dword ptr [r9 + 0x310]', None, '... list A: its count +0x310 ...'),
        (0x889969, 'lea rax, [r9 + 0x318]', None, '... its 0x50-byte entries +0x318 ...'),
        (0x889976, 'mov eax, dword ptr [r9 + 0x818]', None, '... list B +0x818 ...'),
        (0x889983, 'add rax, 0x1a', None, '... entries +0x820 ...'),
        (0x889995, 'mov eax, dword ptr [r9 + 0xd20]', None, '... list C +0xD20 ...'),
        (0x8899A8, 'lea rax, [r9 + 0xd28]', None, '... entries +0xD28'),
        (0x885A69, 'mov r9d, dword ptr [r8]', None, 'perceived: the record\'s sensors (+0) ...'),
        (0x885A71, 'mov r10d, dword ptr [r14 + 0x4c]', None, '... the entry\'s sense bits (+0x4C) ...'),
        (0x885A75, 'mov edx, dword ptr [r8 + rax*8 + 8]', None, '... against each sensor\'s bit (+8, 8 each) ...'),
        (0x885A7A, 'bt r10d, edx', None, '... any one set'),
        (0x4B507A, 'mov edx, dword ptr [rdx + rax + 0x13e8]', None, 'hostile: the perceiver\'s faction mask (+0x13E8) ...'),
        (0x4B5087, 'jmp 0x8d54a0', None, '...'),
        (0x8D54C4, 'mov rbx, qword ptr [rip + {rip}]', 0x3326CB8, '... the faction component ...'),
        (0x8D54D1, 'mov r11d, dword ptr [rbx + 0x12058]', None, '... its map: capacity ...'),
        (0x8D54D8, 'mov edi, dword ptr [rbx + 0x12060]', None, '... multiplier ...'),
        (0x8D54EB, 'mov rsi, qword ptr [rbx + 0x12050]', None, '... slots ...'),
        (0x8D54F2, 'mov ebp, dword ptr [rbx + 0x1205c]', None, '... empty key ...'),
        (0x8D5591, 'mov rax, qword ptr [rbx + 0x12078]', None, '... the target\'s mask (+0x12078, 4 each) ...'),
        (0x8D5598, 'mov edx, dword ptr [rax + rcx*4]', None, '...'),
        (0x8D559B, 'test edx, edx', None, '... non-zero ...'),
        (0x8D559F, 'test r15d, edx', None, '... and no bit shared'),
        (0x4A972A, 'mov r10, qword ptr [rip + {rip}]', 0x3326430, 'the entity flags: their component ...'),
        (0x4A9733, 'mov r9d, dword ptr [r10 + 0x20]', None, '... capacity +0x20 ...'),
        (0x4A9739, 'mov ebx, dword ptr [r10 + 0x28]', None, '... multiplier +0x28 ...'),
        (0x4A9749, 'mov rdi, qword ptr [r10 + 0x18]', None, '... slots +0x18 ...'),
        (0x4A974D, 'mov esi, dword ptr [r10 + 0x24]', None, '... empty key +0x24 ...'),
        (0x4A9797, 'mov rax, qword ptr [r10 + 0x38]', None, '... 64-bit flags (+0x38) ...'),
        (0x4A979B, 'mov rax, qword ptr [rax + rcx*8]', None, '... per entity'),
    ],
    # The spread (section 22): every shot turns its direction by two random angles from the weapon's OWN WeaponData
    # instance record (+0x58: two floats, full widths in milliradians; +0x60: the distribution word): spread x 0.5 x
    # [-1, 1] x 0.001 rad. The instance block is built once, at creation (the component's post-create callback), from its
    # type (+0x54, +0x58, word +0x5C) times its own multipliers (+0x3E0, +0x3E8); it is rebuilt only by an ammo-type
    # switch (0x744690 -> 0x779DF0 -> 0x77A8D0), for a weapon with the ammo-type component.
    'spread': [
        (0x615A30, 'imul rdi, rcx, 0x3f0', None, 'the shot: its weapon\'s own WeaponData instance record ...'),
        (0x615A3A, 'add rdi, qword ptr [rbx + 0x58]', None, '... (records +0x58) ...'),
        (0x615BAB, 'lea r9, [rdi + 0x58]', None, '... its spread block +0x58 ...'),
        (0x615BBA, 'call 0x759740', None, '... turns the shot\'s direction'),
        (0x759AC9, 'cmp byte ptr [r12 + 8], 0', None, 'two random numbers; the distribution word (+8) ...'),
        (0x759AF9, 'call 0x759390', None, '... into the turn ...'),
        (0x75945D, 'movss xmm4, dword ptr [rbx]', None, '... the horizontal width (+0) ...'),
        (0x759461, 'mulss xmm4, dword ptr [rip + {rip}]', 0x23C6AD0, '... x 0.5 ...'),
        (0x759445, 'movss xmm1, dword ptr [rbx + 4]', None, '... the vertical width (+4) ...'),
        (0x75944D, 'mulss xmm1, dword ptr [rip + {rip}]', 0x23C6AD0, '... x 0.5 ...'),
        (0x7594CB, 'mulss xmm15, dword ptr [rip + {rip}]', 0x23C65B4, '... x 0.001: milliradians ...'),
        (0x7594ED, 'mulss xmm2, dword ptr [rip + {rip}]', 0x23C65B4, '...'),
        (0xFDC2B1, 'call 0x581780', None, 'an entity\'s creation ...'),
        (0x581A3B, 'mov rax, qword ptr [rdi + rcx*8 + 0xf0d550]', None, '... each component\'s post-create callback ...'),
        (0x55BEA3, 'mov qword ptr [rcx + 0xf0dcb0], rax', None, '... (WeaponData\'s slot) ...'),
        (0x540266, 'mov rcx, qword ptr [rip + {rip}]', 0x3326CE0, '... the WeaponData component ...'),
        (0x54026D, 'jmp 0x752370', None, '... builds its instance record:'),
        (0x75263D, 'movsd xmm0, qword ptr [r15 + 0x54]', None, 'the type\'s spread (+0x54, +0x58) ...'),
        (0x752643, 'movsd qword ptr [rbp + 0x58], xmm0', None, '... into the instance (+0x58) ...'),
        (0x752648, 'mov eax, dword ptr [r15 + 0x5c]', None, '... the type\'s word (+0x5C) ...'),
        (0x752654, 'mov dword ptr [rbp + 0x60], eax', None, '... into +0x60 ...'),
        (0x752621, 'movss xmm1, dword ptr [rbp + 0x3e0]', None, '... times the instance\'s own multipliers (+0x3E0 ...'),
        (0x75264C, 'movss xmm0, dword ptr [rbp + 0x3e8]', None, '... and +0x3E8) ...'),
        (0x752666, 'movss dword ptr [rbp + 0x58], xmm1', None, '...'),
        (0x752661, 'movss dword ptr [rbp + 0x5c], xmm0', None, '... once'),
        (0x74495D, 'call 0x77b450', None, 'rebuilt only on an ammo-type switch (a weapon with that component) ...'),
        (0x744A57, 'call 0x779df0', None, '...'),
        (0x77A015, 'call 0x77a8d0', None, '...'),
        (0x77AB2D, 'movsd xmm0, qword ptr [rdx + 0x54]', None, '... from the type again'),
    ],
    # Kill attribution (section 24): a turret's shot takes its owner from the weapon's wielder (the Wieldable component)
    # and its creditor from the game's own Creditor(owner): the peer owning the owner's network object, or none when
    # the owner has no faction record, lacks faction bit 0, has no network id, or carries the no-credit tag 0x10000000
    # (the Tag component's per-entity mask; an Eagle without an owner gets it). The creditor travels through the hit to
    # the victim's health record (+0x38), which every kill dispatch credits.
    'attribution': [
        (0x612A18, 'mov rbx, qword ptr [rip + {rip}]', 0x3326730, 'the fire path: the Wieldable component ...'),
        (0x612A28, 'mov ecx, dword ptr [rax + 8]', None, '... the weapon\'s entity ...'),
        (0x612A2F, 'mov r10d, dword ptr [rbx + 0x28]', None, '... its map: multiplier +0x28 ...'),
        (0x612A35, 'mov r9d, dword ptr [rbx + 0x20]', None, '... capacity +0x20 ...'),
        (0x612A42, 'mov r11, qword ptr [rbx + 0x18]', None, '... slots +0x18 ...'),
        (0x612A5F, 'cmp eax, dword ptr [rbx + 0x24]', None, '... empty key +0x24 ...'),
        (0x612BA6, 'mov rax, qword ptr [rbx + 0x38]', None, '... its wielder (+0x38, 4 each) ...'),
        (0x612BAA, 'mov ebx, dword ptr [rax + rcx*4]', None, '...'),
        (0x614437, 'mov dword ptr [rsp + 0x20], ebx', None, '... into the shot ...'),
        (0x61443B, 'call 0x615940', None, '...'),
        (0x616502, 'mov ebx, dword ptr [rbp + 0xa80]', None, 'the shot: the owner (the wielder) ...'),
        (0x61650A, 'call 0x129c690', None, '... its creditor from Creditor(owner) ...'),
        (0x61650F, 'mov rdx, rax', None, '...'),
        (0x6165BB, 'mov dword ptr [rbp - 4], ebx', None, '... the projectile\'s owner ...'),
        (0x6165BE, 'mov qword ptr [rbp], rdx', None, '... and creditor'),
        (0x129C716, 'cmp dword ptr [r9 + 4], -1', None, 'Creditor: a faction record ...'),
        (0x129C720, 'mov edx, 1', None, '... faction bit 0 ...'),
        (0x129C725, 'call 0x8d5100', None, '...'),
        (0x129C72E, 'mov r8d, 0x10000000', None, '... not tagged 0x10000000 ...'),
        (0x129C736, 'call 0x6b5190', None, '...'),
        (0x129C73D, 'jne 0x129c772', None, '... (tagged: no creditor) ...'),
        (0x129C741, 'call 0xfd9af0', None, '... a network id ...'),
        (0x129C748, 'cmp eax, 0x7fff', None, '...'),
        (0x129C75A, 'mov rbx, qword ptr [rax + 0x160]', None, '... then its network object\'s owning peer'),
        (0x6B51AF, 'mov r11, qword ptr [rip + {rip}]', 0x3326430, 'HasTags: the Tag component ...'),
        (0x6B5229, 'mov rax, qword ptr [r11 + 0x38]', None, '... the entity\'s 64-bit mask (+0x38) ...'),
        (0x6B5231, 'and rdx, rdi', None, '...'),
        (0x6B5234, 'cmp rdx, rdi', None, '... has every bit asked'),
        (0x8A1C3F, 'or qword ptr [rax + rcx*8], 0x10000000', None, 'an Eagle without an owner gets the no-credit tag'),
        (0x923C0A, 'mov rax, qword ptr [r15 + 0x38]', None, 'a hit: the victim\'s creditor ...'),
        (0x923C20, 'mov qword ptr [r15 + 0x38], rax', None, '... becomes the hit\'s (kept when the hit has none)'),
    ],
    # Research only: the copy routine 0x61AF10 (manager, entity handle, delta entry {kind, first patch, count}), as the
    # delta dispatcher calls it. A count of 0 is an unmodified copy of the type's record.
    'copyRoutine': [
        (0x576AA7, 'lea rcx, [r13 + 0xf0b3b8]', None, 'the dispatcher: the manager (component world + 0xF0B3B8) ...'),
        (0x576AB1, 'mov rdx, r12', None, '... the entity handle ...'),
        (0x576AAE, 'mov r8, r14', None, '... the delta entry'),
        (0x61AF2A, 'mov eax, dword ptr [rdx + 8]', None, 'the routine: the handle\'s entity ...'),
        (0x61AF2D, 'mov rbp, r8', None, '... the entry ...'),
        (0x61AFCD, 'call 0x173b6f0', None, '... a scratch scope ...'),
        (0x61AFDF, 'mov edx, 0x268', None, '... 616 scratch bytes ...'),
        (0x61AFE9, 'mov rcx, qword ptr [r14]', None, '... the type record by the handle\'s resource'),
        (0x515554, 'mov ebx, dword ptr [rdx + 4]', None, 'the patches: the entry\'s first ...'),
        (0x51555A, 'mov r9d, dword ptr [rdx + 8]', None, '... and count (0: none) ...'),
        (0x515576, 'mov rax, qword ptr [rsi + 0x30]', None, '... each {offset, size, data} in the delta table +0x30 ...'),
        (0x51558D, 'call 0x20988f0', None, '... a byte copy'),
        (0x61B0AE, 'mov ebp, dword ptr [rsi + 0xc8]', None, 'the new copy\'s index = the count +0xC8 ...'),
        (0x61B0BD, 'cmp eax, dword ptr [rsi + 0x98]', None, '... the entity map is rehashed when full ...'),
        (0x61B0F9, 'add rdx, qword ptr [rsi + 0xd0]', None, '... written at +0xD0 (no check against the array capacity +0x30)'),
        (0x61950F, 'mov dword ptr [rbx + 0x30], 0x80', None, 'the copies\' capacity starts at 128 ...'),
        (0x619A9D, 'mov dword ptr [rbp + 0x30], ecx', None, '... and grows (by 0x180) ...'),
        (0x5811AC, 'call 0x6199d0', None, '... only in the creation reserve'),
        (0x173B705, 'mov rax, qword ptr [rip + {rip}]', 0x33263E8, 'scratch memory: the engine ...'),
        (0x173B71D, 'call qword ptr [rax + 0xd8]', None, '... thread index ...'),
        (0x173B723, 'mov rdx, qword ptr [rip + {rip}]', 0x33263B0, '... selects a per-thread arena'),
        (0x61A0B5, 'mov dword ptr [rbx + 0xc8], ebp', None, 'the entity\'s removal drops its copy'),
    ],
    'targetPush': [
        (0x4D1191, 'mov rax, qword ptr [rip + {rip}]', 0x3326418, 'a ground movement component (keys +0x30) ...'),
        (0x4D11F1, 'mov r10, qword ptr [rip + {rip}]', 0x3326638, 'another movement component (keys +0x3C38) ...'),
        (0x4D12F9, 'call 0x5b36c0', None, 'a ground movement component: native path planning'),
        (0x4D133A, 'call 0x6292a0', None, 'another movement component: native'),
        (0x4D1261, 'mov r9, qword ptr [rip + {rip}]', FLIGHT, 'the flight component ...'),
        (0x4D139C, 'imul rdx, rax, 0x534', None, '... its records (0x534) ...'),
        (0x4D13B3, 'movsd qword ptr [rdx + 0x4fc], xmm0', None, '... the target +0x4FC ...'),
        (0x4D13BB, 'mov dword ptr [rdx + 0x504], eax', None, '... +0x504'),
    ],
    # The flight's stage machine (P = the Behavior record + 8).
    'stages': [
        (0x45C77B, 'mov rdx, qword ptr [rcx + 8]', None, 'the update: P ...'),
        (0x45C782, 'mov eax, dword ptr [rdx]', None, '... its stage P+0 ...'),
        (0x45C786, 'cmp eax, 0xa', None, '... 1 to 11'),
        (0x45CA9A, 'call 0x45af10', None, 'stage 6: the hover'),
        (0x45CAA4, 'mov rcx, qword ptr [rdx + 0x178]', None, 'stage 7: P+0x178 ...'),
        (0x45CAAB, 'add rcx, 0x2dc6c0', None, '... + 3 s ...'),
        (0x45CAC3, 'mov edx, 8', None, '... then stage 8'),
        (0x45CB06, 'mov rcx, qword ptr [rax + 0x178]', None, 'stage 8: P+0x178 ...'),
        (0x45CB14, 'add rcx, 0xf4240', None, '... + 1 s, then stage 9'),
        (0x45CB68, 'mov rcx, qword ptr [rax + 0x170]', None, 'stage 9: P+0x170 + 1 s, then stage 10'),
        (0x45CBCA, 'mov rcx, qword ptr [rax + 0x178]', None, 'stage 10: P+0x178 ...'),
        (0x45CBD8, 'add rcx, 0xb71b00', None, '... + 12 s ...'),
        (0x45CBF6, 'call 0xfdc310', None, '... the entity is removed'),
        (0x45BD24, 'mov dword ptr [rax + 8], edx', None, 'a transition: P+8 ...'),
        (0x45BD98, 'mov dword ptr [rax], edi', None, '... the new stage'),
        (0x45BF70, 'mov qword ptr [r8 + 0x188], rcx', None, 'stage 3 entry: P+0x188 = now ...'),
        (0x45BFF5, 'call 0x4d5a60', None, '... the target: its position in the position component, plus a height ...'),
        (0x45C01B, 'call 0x4d1150', None, '... pushed into the flight'),
        (0x45C185, 'mov qword ptr [r8 + 0x180], rcx', None, 'stage 6 entry: the hover start P+0x180 = now'),
        (0x45C2C2, 'mov qword ptr [r8 + 0x178], rcx', None, 'stage 7 entry: P+0x178 = now'),
        (0x45AF3E, 'test byte ptr [rax + 0x1e0], 1', None, 'the hover: released (P+0x1E0 bit 0)? ...'),
        (0x45B081, 'mov rcx, qword ptr [rcx + 0x180]', None, '... not yet: the hover start ...'),
        (0x45B08C, 'add rcx, 0x5b8d80', None, '... + 6 s (or at the target) ...'),
        (0x45B2DC, 'call 0x6dab90', None, '... releases the cargo ...'),
        (0x45B308, 'mov dword ptr [rax + 0x1e0], ecx', None, '... marks it released ...'),
        (0x45B33C, 'mov qword ptr [rcx + 0x178], rax', None, '... and P+0x178 = now'),
        (0x45B134, 'mov rax, qword ptr [rax + 0x178]', None, 'released: P+0x178 ...'),
        (0x45B13B, 'add rax, 0x927c0', None, '... + 0.6 s ...'),
        (0x45B141, 'cmp rax, qword ptr [rbx + 0x18]', None, '... passed ...'),
        (0x45B147, 'mov edx, 8', None, '... departs (stage 8)'),
    ],
}


def table_lookup(mem, table, slots, key):
    """The index of `key` in one of the component world's entity-type tables (open addressing, key % slots)."""
    i = key % slots
    for _ in range(slots):
        k, index = struct.unpack('<QQ', mem.read(table + 16 * i, 16))
        if k == key:
            return index & 0xFFFFFFFF
        if k == 0:
            return None
        i = 0 if i == slots - 1 else i + 1
    return None


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

    names = {root['id']: name for name, root in catalogue_roots().items()}
    mem = base.Mem(MISSION_SNAPSHOTS[0])
    g = mem.game
    if mem.u32(g + INVALID_ENTITY) != 0:
        raise ValueError('the invalid entity id is no longer 0')
    world = mem.ptr(g + WORLD)
    # The Pelican's transport settings: its cargo timer starts at 0 [O]; no pod settings (the timer is not held).
    table = mem.ptr(world + SETTINGS_TABLE)
    index = table_lookup(mem, table, SETTINGS_SLOTS, PELICAN)
    if index is None:
        raise ValueError('the Pelican has no transport settings')
    settings = struct.unpack('<2f', mem.read(table + 8 * (5 * index + 0x38), 8))
    if settings[0] != 0.0:
        raise ValueError('the Pelican\'s cargo timer no longer starts at 0: %r' % (settings,))
    if table_lookup(mem, mem.ptr(world + POD_TABLE), POD_SLOTS, PELICAN) is not None:
        raise ValueError('the Pelican has pod settings: its cargo timer would wait for a landing')
    # Every vehicle row carries [vehicle, Pelican] [O].
    vehicles = {}
    for kind in range(1, 150):
        row = mem.ptr(g + TABLE + kind * 8)
        if not row:
            continue
        raw = mem.read(row, 0x180)
        if struct.unpack_from('<I', raw, 0x3C)[0] != 3:
            continue
        name = names.get(struct.unpack_from('<I', raw, 4)[0])
        listing, count = struct.unpack_from('<Q', raw, 0x98)[0], struct.unpack_from('<I', raw, 0xA0)[0]
        payloads = [struct.unpack('<Q', mem.read(listing + 8 * i, 8))[0] for i in range(count)]
        if name:
            if payloads[1:] != [PELICAN]:
                raise ValueError('%s no longer delivers with the transport Pelican: %r' % (name, payloads))
            vehicles[name] = {'type': kind, 'vehicle': '0x%016X' % payloads[0], 'pelican': '0x%016X' % payloads[1]}
    mem.close()
    if len(vehicles) < 9:
        raise ValueError('fewer catalogued vehicle rows than expected: %r' % sorted(vehicles))

    # The world's default spawn context and modifier block [O]: all zero in every retained snapshot.
    defaults = {}
    for name in SNAPSHOTS:
        m = base.Mem(name)
        w = m.ptr(m.game + WORLD)
        context, modifiers = m.read(w + DEFAULT_CONTEXT, CONTEXT_SIZE), m.read(w + DEFAULT_MODIFIERS, 0x58)
        m.close()
        if context != bytes(CONTEXT_SIZE) or modifiers != bytes(0x58):
            raise ValueError('%s: the default spawn context or modifiers are not all zero' % name)
        defaults[name] = 'all zero'
    prologue = game_data[SPAWN:SPAWN_END].hex()
    # The behaviour of every Pelican variant and turret, by entity type [O]: identical in every retained snapshot.
    variants = None
    for name in SNAPSHOTS:
        m = base.Mem(name)
        w = m.ptr(m.game + WORLD)
        table = m.ptr(w + BEHAVIOUR_SETTINGS)
        found = {}
        for key, (resource, path) in PELICAN_VARIANTS.items():
            index = table_lookup(m, table, BEHAVIOUR_SLOTS, resource)
            entry = m.read(table + BEHAVIOUR_ENTRIES + 12 * index, 12) if index is not None else None
            found[key] = {'resource': '0x%016X' % resource, 'path': path,
                'behaviour': struct.unpack_from('<I', entry, 0)[0] if entry else None,
                'value': round(struct.unpack_from('<f', entry, 4)[0], 4) if entry else None}
        m.close()
        if variants is None:
            variants = found
        elif found != variants:
            raise ValueError('%s: the behaviour settings differ' % name)
    if (variants['shuttle_transport']['behaviour'], variants['shuttle_gunship']['behaviour']) != (667, 202):
        raise ValueError('the Pelican behaviours moved: %r' % variants)
    # A mounted pair in the mission snapshots [O]: the shuttle escape hatch (it has a MountComponent) carries a personnel
    # shuttle (Attachable). The child's attachable +0x0 is the parent's link id (its entity handle +0xC), +0x4 a node.
    m = base.Mem(MISSION_SNAPSHOTS[0])

    def entity_map(component, keys_at):
        keys, cap, empty = m.ptr(component + keys_at), m.u32(component + keys_at + 8), m.u32(component + keys_at + 0xC)
        out = {}
        for k in range(cap):
            e, i = struct.unpack('<II', m.read(keys + 8 * k, 8))
            if e != empty and i != 0xFFFFFFFF:
                out[e] = i
        return out
    attach, mount = m.ptr(m.game + 0x3326698), m.ptr(m.game + 0x3326438)
    attached, mounted = entity_map(attach, 0x18), entity_map(mount, 0x20)
    pair = None
    for parent, index in mounted.items():
        handle = m.ptr(m.ptr(mount + 0x38) + 8 * index)
        link = m.u32(handle + 0xC)
        for child, ci in attached.items():
            rec = m.read(m.ptr(attach + 0x38) + 0xAC * ci, 0xAC)
            if child != parent and struct.unpack_from('<I', rec, 0)[0] == link:
                pair = {'parent': parent, 'parentResource': m.read(handle, 8)[::-1].hex().upper(), 'link': '0x%X' % link,
                    'child': child, 'node': struct.unpack_from('<I', rec, 4)[0],
                    'childPosition': [round(v, 3) for v in struct.unpack_from('<3f', rec, 0x10)],
                    'childRotation': [round(v, 4) for v in struct.unpack_from('<4f', rec, 0x1C)]}
    m.close()
    if not pair:
        raise ValueError('no mounted pair in the mission snapshot')
    # The parent's mount record [O]: +0x48 the child entity per slot (6 per mount), +0x50 {count, child network ids}.
    m = base.Mem(MISSION_SNAPSHOTS[0])
    mount = m.ptr(m.game + 0x3326438)
    mi = entity_map(mount, 0x20)[pair['parent']]
    children = list(struct.unpack('<6I', m.read(m.ptr(mount + 0x48) + 24 * mi, 24)))
    networks = list(struct.unpack('<6I', m.read(m.ptr(mount + 0x50) + 24 * mi, 24)))
    invalid = m.u32(m.game + 0x3483C34)
    m.close()
    if children[0] != pair['child'] or networks[0] != 1 or invalid != 0:
        raise ValueError('the mount record no longer names its child: %r %r %r' % (children, networks, invalid))
    pair['mountChildren'], pair['mountNetworks'] = children, networks
    # The Extract stratagem (mission type 148) delivers the gunship: a vehicle-kind row with that one payload [O].
    m = base.Mem(MISSION_SNAPSHOTS[0])
    extract = None
    for kind in range(1, 150):
        row = m.ptr(m.game + TABLE + 8 * kind)
        if row and m.u32(row + 4) == 115737856:
            listing, count = struct.unpack('<QI', m.read(row + 0x98, 12))
            extract = {'type': kind, 'stableId': 115737856, 'kind': m.u32(row + 0x3C),
                'payloads': ['0x%016X' % struct.unpack('<Q', m.read(listing + 8 * i, 8))[0] for i in range(count)]}
    m.close()
    if not extract or extract['payloads'] != ['0x%016X' % PELICAN_VARIANTS['shuttle_gunship'][0]]:
        raise ValueError('the Extract stratagem no longer delivers the gunship: %r' % extract)
    # The behaviour dispatch table: the Pelican's flight (667) and the circling behaviour (202) [O].
    dispatch = {str(i + 1): struct.unpack_from('<I', game_data, 0x4795C4 + 4 * i)[0] for i in (201, 666)}
    if dispatch != {'202': 0x4750D0, '667': 0x47926C}:
        raise ValueError('the behaviour dispatch moved: %r' % dispatch)
    constants = {'angleStep': struct.unpack_from('<f', game_data, 0x23C6C28)[0],
        'nearSquared': struct.unpack_from('<f', game_data, 0x23C7614)[0],
        'radius': struct.unpack_from('<f', game_data, 0x23C7654)[0]}

    # The turret weapons [O] (section 15). Type records: the chin turret and the Gatling Sentry in the ProjectileWeapon
    # table (world +0xF12E80: 542 x 16-byte index, records 0x268 from +0x21E0) and the magazine table (world +0xF124A0:
    # 540 x 16, records 160 from +0x21C0). Per instance: how many resolved copies exist, and every projectile weapon's
    # shot interval against its RPM.
    turret_weapon = {}
    for name in MISSION_SNAPSHOTS:
        m = base.Mem(name)
        w = m.ptr(m.game + WORLD)
        types = {}
        for key, resource in (('chinTurret', TURRET_HMG), ('gatlingSentry', GATLING)):
            pw_table, mag_table = m.ptr(w + 0xF12E80), m.ptr(w + 0xF124A0)
            i, j = table_lookup(m, pw_table, 542, resource), table_lookup(m, mag_table, 540, resource)
            if i is None or j is None:
                raise ValueError('%s: no ProjectileWeapon or magazine record for %s' % (name, key))
            pw, mag = m.read(pw_table + 0x21E0 + 0x268 * i, 0x268), m.read(mag_table + 0x21C0 + 160 * j, 160)
            pattern = list(struct.unpack_from('<32I', mag, 4))
            while pattern and pattern[-1] == 0:
                pattern.pop()
            types[key] = {'projectileType': struct.unpack_from('<I', pw, 0)[0],
                'rpmSlots': [round(v, 3) for v in struct.unpack_from('<3f', pw, 4)],
                'magazinePattern': bool(struct.unpack_from('<I', mag, 0)[0]), 'pattern': pattern,
                'capacity': struct.unpack_from('<I', mag, 0x88)[0]}
        component = m.ptr(m.game + 0x33266D8)

        def entries(base_at, at):
            keys, cap, empty = m.ptr(base_at + at), m.u32(base_at + at + 8), m.u32(base_at + at + 0xC)
            out = {}
            for k in range(cap):
                e, idx = struct.unpack('<II', m.read(keys + 8 * k, 8))
                if e != empty and idx != 0xFFFFFFFF:
                    out[e] = idx
            return out
        instances = entries(component, 0x50)
        intervals, cached = [], []
        for entity, idx in instances.items():
            record = m.read(m.ptr(component + 0x78) + 0xA8 * idx, 0xA8)
            interval, cache = struct.unpack_from('<f', record, 0xC)[0], struct.unpack_from('<f', record, 0x64)[0]
            rpm = struct.unpack('<f', m.read(m.ptr(component + 0x70) + 0x20 * idx + 0x14, 4))[0]
            current = struct.unpack('<f', m.read(m.ptr(component + 0x80) + 12 * idx + 4, 4))[0]
            intervals.append(abs(interval * rpm - 60.0) < 0.01)
            cached.append(cache == current and abs(interval * current - 60.0) < 0.01)
        magazine = m.ptr(m.game + 0x3326648)
        turret_weapon[name] = {'projectileWeapons': len(instances), 'intervalIs60OverRpm': all(intervals),
            'cachedIsCurrentRpm': all(cached), 'copyCapacity': m.u32(component + 0x30),
            'projectileWeaponCopies': len(entries(component, 0x90)), 'copyCount': m.u32(component + 0xC8),
            'magazineCopies': len(entries(magazine, 0x60)), 'types': types}
        m.close()
    if any(v['projectileWeaponCopies'] or v['copyCount'] or not v['intervalIs60OverRpm'] or not v['cachedIsCurrentRpm']
            or v['copyCapacity'] < 128 for v in turret_weapon.values()):
        raise ValueError('the per-instance weapon observations changed: %r' % turret_weapon)
    # The casing [O]: both types' fire effects (ProjectileWeapon +0xA0..+0xE7), and the node names by their 32-bit
    # name hashes ("ejector", "muzzle").
    import hd2_game_data as gdata
    ejector, muzzle = gdata.murmur64(b'ejector') >> 32, gdata.murmur64(b'muzzle') >> 32
    m = base.Mem(MISSION_SNAPSHOTS[0])
    w = m.ptr(m.game + WORLD)
    casings = {}
    for key, resource in (('chinTurret', TURRET_HMG), ('gatlingSentry', GATLING)):
        pw_table = m.ptr(w + 0xF12E80)
        raw = m.read(pw_table + 0x21E0 + 0x268 * table_lookup(m, pw_table, 542, resource), 0x268)
        casings[key] = {'particles': '%016X' % struct.unpack_from('<Q', raw, 0xB0)[0],
            'nodes': ['%08X' % v for v in struct.unpack_from('<4I', raw, 0xB8)],
            'parameters': list(struct.unpack_from('<3I', raw, 0xD4)),
            'effectA': struct.unpack_from('<Q', raw, 0xA0)[0], 'nodeA': '%08X' % struct.unpack_from('<I', raw, 0xA8)[0],
            'effectC': struct.unpack_from('<Q', raw, 0xC8)[0], 'nodeC': struct.unpack_from('<I', raw, 0xD0)[0],
            'muzzleFlash': '%016X' % struct.unpack_from('<Q', raw, 0xE0)[0],
            'muzzleNode': '%08X' % struct.unpack_from('<I', raw, 0x21C)[0]}
    m.close()
    c, gc = casings['chinTurret'], casings['gatlingSentry']
    if not (c['nodes'] == gc['nodes'] == ['%08X' % ejector, '00000000', '00000000', '00000000']
            and c['nodeA'] == gc['nodeA'] == '%08X' % ejector and c['effectA'] == gc['effectA'] == 0
            and c['effectC'] == gc['effectC'] == 0 and c['nodeC'] == gc['nodeC'] == 0
            and c['particles'] != gc['particles'] and gc['muzzleNode'] == '%08X' % muzzle):
        raise ValueError('the turrets\' fire effects changed: %r' % casings)
    # The Gatling Sentry's call-in package lists its casing and its muzzle flash (the bundles) [O].
    PARTICLES, PACKAGE = gdata.murmur64(b'particles'), gdata.murmur64(b'package')
    gd = gdata.Data()
    found = gd.find({(0x992D325D88DE5FBF, PACKAGE)})
    listing = gd.read(*[(v[0], v[1]) for v in found.values()][0]) if found else b''
    listed = {}
    for key in ('particles', 'muzzleFlash'):
        at = listing.find(struct.pack('<Q', int(gc[key], 16)))
        listed[key] = at >= 8 and struct.unpack_from('<Q', listing, at - 8)[0] == PARTICLES
    if not all(listed.values()):
        raise ValueError('the Gatling call-in package no longer lists its casing: %r' % listed)

    # The magazines and reloads of both types [O]: the magazine type fields +0x84..+0x9D, the reload type table
    # (world +0xF12800, 0x1F2 slots, 0x50-byte records from +0x1F20).
    m = base.Mem(MISSION_SNAPSHOTS[0])
    w = m.ptr(m.game + WORLD)
    ammo = {}
    for key, resource in (('chinTurret', TURRET_HMG), ('gatlingSentry', GATLING)):
        mag_table, reload_table = m.ptr(w + 0xF124A0), m.ptr(w + 0xF12800)
        mag = m.read(mag_table + 0x21C0 + 160 * table_lookup(m, mag_table, 540, resource), 160)
        ri = table_lookup(m, reload_table, 0x1F2, resource)
        reload = m.read(reload_table + 0x1F20 + 0x50 * ri, 0x50) if ri is not None else None
        ammo[key] = {'capacity': struct.unpack_from('<I', mag, 0x88)[0],
            'spareMagazines': struct.unpack_from('<I', mag, 0x8C)[0],
            'perResupply': struct.unpack_from('<I', mag, 0x90)[0],
            'maxSpareMagazines': struct.unpack_from('<I', mag, 0x94)[0],
            'reloadThreshold': struct.unpack_from('<I', mag, 0x98)[0], 'chamber': mag[0x9C],
            'firstRound': struct.unpack_from('<I', mag, 0x84)[0],
            'reloadAnimation': struct.unpack_from('<I', reload, 4)[0] if reload else None}
    m.close()
    if not (ammo['gatlingSentry']['capacity'] == 500 and ammo['gatlingSentry']['spareMagazines'] == 0
            and ammo['gatlingSentry']['maxSpareMagazines'] == 0 and ammo['gatlingSentry']['reloadAnimation'] is None
            and ammo['chinTurret']['reloadAnimation'] == 0 and ammo['chinTurret']['chamber'] == 1
            and ammo['gatlingSentry']['chamber'] == 1 and ammo['chinTurret']['firstRound'] == 0):
        raise ValueError('the turrets\' magazines changed: %r' % ammo)

    # The network fields of the magazine [O]: the engine's network configuration (session = [[exe+0x1A10278]+0xA8],
    # config = session +0x18: field descriptors +0x18 (24 bytes: kind +0xC, bits +0xD, min +0x10), object types +0x78
    # (0x50 bytes: field count +0x18, descriptor indices +0x20, name hashes +0x38)).
    m = base.Mem(MISSION_SNAPSHOTS[0])
    cfg = m.ptr(m.ptr(m.ptr(m.exe + 0x1A10278) + 0xA8) + 0x18)
    types_at, fields_at = m.ptr(cfg + 0x78), m.ptr(cfg + 0x18)
    names = {0xD7A5D63E: 'rounds', 0xEC64918B: 'spareMagazines', 0x4A893E74: 'chamberEmpty'}
    net = {}
    for ti in range(0x800):
        t = m.read(types_at + 0x50 * ti, 0x50)
        if t is None:
            break
        nf, ip, hp = struct.unpack_from('<I', t, 0x18)[0], struct.unpack_from('<Q', t, 0x20)[0], struct.unpack_from('<Q', t, 0x38)[0]
        if not (0 < nf <= 500 and hp and ip):
            continue
        hashes, indices = m.read(hp, 4 * nf), m.read(ip, 4 * nf)
        if not (hashes and indices):
            continue
        for h, i in zip(struct.unpack('<%dI' % nf, hashes), struct.unpack('<%dI' % nf, indices)):
            if h in names:
                d = m.read(fields_at + 0x18 * i, 0x18)
                net.setdefault(names[h], set()).add((d[0xC], d[0xD], struct.unpack_from('<i', d, 0x10)[0]))
    m.close()
    ammo_net = {k: [{'kind': kind, 'bits': bits, 'min': low, 'max': low - 1 + (1 << bits)} for kind, bits, low in sorted(v)]
        for k, v in net.items()}
    if [(f['bits'], f['min']) for f in ammo_net.get('rounds', [])] != [(11, 0)]:
        raise ValueError('the rounds are no longer an 11-bit network field: %r' % ammo_net)

    # The recoil of both types [O]: WeaponData type table (world +0xF12BD8, 0x2DA slots, 0x4D0-byte records from
    # +0x2DA0): block A +0x00 and block B +0x1C, 7 floats each (copied into the instance record +0x1C / +0x38); and the
    # projectile 148's speed (its settings row +0x20; rows by type at game +0x37C7670).
    m = base.Mem(MISSION_SNAPSHOTS[0])
    w = m.ptr(m.game + WORLD)
    recoil = {}
    for key, resource in (('chinTurret', TURRET_HMG), ('gatlingSentry', GATLING)):
        table = m.ptr(w + 0xF12BD8)
        raw = m.read(table + 0x2DA0 + 0x4D0 * table_lookup(m, table, 0x2DA, resource), 0x60)
        recoil[key] = {'blockA': [round(v, 4) for v in struct.unpack_from('<7f', raw, 0x00)],
            'blockB': [round(v, 4) for v in struct.unpack_from('<7f', raw, 0x1C)],
            'spread': [round(v, 4) for v in struct.unpack_from('<2f', raw, 0x54)]}
    row148 = m.ptr(m.game + 0x37C7670 + 8 * 148)
    speed148 = struct.unpack('<f', m.read(row148 + 0x20, 4))[0]
    m.close()
    if not (recoil['gatlingSentry']['blockB'][:2] == [0.0, 3.0] and recoil['chinTurret']['blockB'][:2] == [2.5, 10.0]
            and abs(speed148 - 820.0) < 1e-3):
        raise ValueError('the turrets\' recoil or projectile 148 changed: %r %r' % (recoil, speed148))

    # The perception records [O] (section 21), in both mission snapshots, through the manager's own map: every list
    # within 16 entries; every listed entity known to the health manager or not; the hostile test (the target's faction
    # mask against the perceiver's) over lists A and B; how many entries are perceived now (sense bits against the
    # sensors' bits).
    perception = {}
    for name in MISSION_SNAPSHOTS:
        m = base.Mem(name)
        mgr = m.ptr(m.game + 0x3326548)
        faction = m.ptr(m.game + 0x3326CB8)
        health = m.ptr(m.game + 0x3326688)
        slots, capacity, empty = m.ptr(mgr + 0x30), m.u32(mgr + 0x38), m.u32(mgr + 0x3C)
        records = m.ptr(mgr + 0x50)
        table = m.read(slots, capacity * 8)
        seen = {'perceivers': 0, 'withSensors': 0, 'entries': {'A': 0, 'B': 0, 'C': 0}, 'maxCount': 0,
            'withHealth': 0, 'perceivedNow': 0, 'hostile': {'A': 0, 'B': 0}, 'listed': 0}
        for k in range(capacity):
            key, index = struct.unpack_from('<II', table, k * 8)
            if key == empty or index == 0xFFFFFFFF:
                continue
            rec = m.read(records + index * 0x13F8, 0x13F8)
            seen['perceivers'] += 1
            sensors = struct.unpack_from('<I', rec, 0)[0]
            if sensors > 32:
                raise ValueError('%s: perceiver %d names %d sensors' % (name, key, sensors))
            if sensors:
                seen['withSensors'] += 1
            mask = 0
            for s in range(sensors):
                mask |= 1 << struct.unpack_from('<I', rec, 8 + 8 * s)[0]
            mine = struct.unpack_from('<I', rec, 0x13E8)[0]
            for label, count_at, entries_at in (('A', 0x310, 0x318), ('B', 0x818, 0x820), ('C', 0xD20, 0xD28)):
                count = struct.unpack_from('<I', rec, count_at)[0]
                if count > 16:
                    raise ValueError('%s: perceiver %d list %s holds %d entries' % (name, key, label, count))
                seen['maxCount'] = max(seen['maxCount'], count)
                for e in range(count):
                    entity, = struct.unpack_from('<I', rec, entries_at + e * 0x50)
                    sense, = struct.unpack_from('<I', rec, entries_at + e * 0x50 + 0x4C)
                    seen['entries'][label] += 1
                    seen['listed'] += 1
                    if base.map_lookup(m, health + 0x1030, entity) is not None:
                        seen['withHealth'] += 1
                    if sense & mask:
                        seen['perceivedNow'] += 1
                    if label in ('A', 'B'):
                        fi = base.map_lookup(m, faction + 0x12050, entity)
                        theirs = struct.unpack('<I', m.read(m.ptr(faction + 0x12078) + 4 * fi, 4))[0] if fi is not None else 0
                        if theirs and not theirs & mine:
                            seen['hostile'][label] += 1
        m.close()
        perception[name] = seen
    if not (all(v['perceivers'] and v['hostile']['A'] == v['entries']['A'] and v['hostile']['B'] == 0
            and v['withHealth'] == v['listed'] for v in perception.values())
            and any(v['listed'] for v in perception.values())):
        raise ValueError('the perception lists do not read as lists A (hostile), B and C: %r' % perception)

    # The spread [O] (section 22), in both mission snapshots: every WeaponData instance's spread (+0x58, +0x5C) and word
    # (+0x60) are some type's (+0x54, +0x58, +0x5C) times its own multipliers (+0x3E0, +0x3E8); the chin turret's and
    # the Gatling Sentry's types.
    spread = {}
    for name in MISSION_SNAPSHOTS:
        m = base.Mem(name)
        mgr = m.ptr(m.game + 0x3326CE0)
        table = m.ptr(m.ptr(m.game + WORLD) + 0xF12BD8)
        typed = []
        raw_slots = m.read(table, 0x2DA * 16)
        for s in range(0x2DA):
            key, idx = struct.unpack_from('<QI', raw_slots, s * 16)
            if key:
                typed.append(struct.unpack_from('<2fI', m.read(table + 0x2DA0 + idx * 0x4D0 + 0x54, 12)))
        slots, capacity, empty = m.ptr(mgr + 0x30), m.u32(mgr + 0x38), m.u32(mgr + 0x3C)
        records = m.ptr(mgr + 0x58)
        keys = m.read(slots, capacity * 8)
        seen = {'instances': 0, 'consistent': 0, 'multipliersOne': 0, 'pairs': []}
        f32 = lambda v: struct.unpack('<f', struct.pack('<f', v))[0]
        for k in range(capacity):
            entity, index = struct.unpack_from('<II', keys, k * 8)
            if entity == empty or index == 0xFFFFFFFF:
                continue
            inst = m.read(records + index * 0x3F0, 0x3F0)
            sx, sy, word = struct.unpack_from('<2fI', inst, 0x58)
            mx, my = struct.unpack_from('<f', inst, 0x3E0)[0], struct.unpack_from('<f', inst, 0x3E8)[0]
            seen['instances'] += 1
            seen['multipliersOne'] += mx == 1.0 and my == 1.0
            if any(tw == word and f32(tx * mx) == sx and f32(ty * my) == sy for tx, ty, tw in typed):
                seen['consistent'] += 1
            if [sx, sy] not in seen['pairs']:
                seen['pairs'].append([sx, sy])
        for key, resource in (('chinTurret', TURRET_HMG), ('gatlingSentry', GATLING)):
            seen[key] = list(struct.unpack_from('<2fI', m.read(table + 0x2DA0 + 0x4D0 * table_lookup(m, table, 0x2DA,
                resource) + 0x54, 12)))
        m.close()
        seen['pairs'].sort()
        spread[name] = seen
    if not all(v['instances'] and v['consistent'] == v['instances'] and v['chinTurret'] == [1.0, 1.0, 0]
            and v['gatlingSentry'] == [10.0, 10.0, 0] for v in spread.values()):
        raise ValueError('the WeaponData spread no longer reads as its type times its multipliers: %r' % spread)

    # The AP4 donor (section 23): the MG-206 Heavy Machine Gun's round 275 (also the FRVs' and the Bastion's coaxial gun),
    # from the existing research: its damage record 205 is AP4 (research/vehicle-weapons); its row (the projectile
    # settings table, game +0x37C7670) carries its type (+0), velocity (+0x20), mass (+0x24) and damage id (+0x3C) in
    # both mission snapshots, as do the standard round 148's and the Maelstrom's 251 (the same round: only its type and
    # an 8-byte resource at +0x48 differ).
    vehicle_weapons = json.loads((ROOT / 'research/vehicle-weapons-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    ap = {}
    for vehicle in vehicle_weapons['vehicles']:
        for slot in vehicle.get('slots', []):
            p = slot.get('projectile') or {}
            damage = p.get('damage') or {}
            if p.get('type') in (148, 275, 251) and damage.get('values'):
                ap[p['type']] = {'damage': damage.get('type'), 'apDirect': damage['values']['ap_direct'],
                    'apSlight': damage['values']['ap_slight'], 'apLarge': damage['values']['ap_large'],
                    'apExtreme': damage['values']['ap_extreme'], 'standardDamage': damage['values']['standard_damage'],
                    'durableDamage': damage['values']['durable_damage']}
    donor_rows = {}
    for name in MISSION_SNAPSHOTS:
        m = base.Mem(name)
        rows = {}
        for kind in (148, 275, 251):
            raw = m.read(m.ptr(m.game + 0x37C7670 + 8 * kind), 272)
            rows[kind] = {'type': struct.unpack_from('<I', raw, 0)[0], 'velocity': struct.unpack_from('<f', raw, 0x20)[0],
                'mass': struct.unpack_from('<f', raw, 0x24)[0], 'damage': struct.unpack_from('<I', raw, 0x3C)[0],
                'differsFrom275': None}
            rows[kind]['raw'] = raw
        for kind in (148, 251):
            rows[kind]['differsFrom275'] = [o for o in range(0, 272, 4) if rows[kind]['raw'][o:o + 4] != rows[275]['raw'][o:o + 4]]
        for kind in rows:
            del rows[kind]['raw']
        m.close()
        donor_rows[name] = rows
    for rows in donor_rows.values():
        if not (rows[275]['type'] == 275 and rows[275]['damage'] == ap[275]['damage'] == 205 and ap[275]['apDirect'] == 4
                and ap[275]['apSlight'] == 4 and ap[275]['apLarge'] == 4 and rows[148]['damage'] == ap[148]['damage']
                and rows[251]['differsFrom275'] == [0, 0x48, 0x4C]):
            raise ValueError('the AP4 donor no longer reads as the MG-206 round with damage 205 (AP4): %r %r' % (rows, ap))

    # Attribution [O] (section 24), in both mission snapshots: the Wieldable records (a player's weapon wielded by its
    # avatar; turrets and cameras wielding themselves), the avatar's Tag mask and faction, and the local peer.
    attribution = {}
    for name in MISSION_SNAPSHOTS:
        m = base.Mem(name)
        wield = m.ptr(m.game + 0x3326730)
        tags = m.ptr(m.game + 0x3326430)
        faction = m.ptr(m.game + 0x3326CB8)
        slots, capacity, empty = m.ptr(wield + 0x18), m.u32(wield + 0x20), m.u32(wield + 0x24)
        keys = m.read(slots, capacity * 8)
        pairs = []
        for k in range(capacity):
            entity, index = struct.unpack_from('<II', keys, k * 8)
            if entity == empty or index == 0xFFFFFFFF:
                continue
            wielder = m.u32(m.ptr(wield + 0x38) + 4 * index)
            ti = base.map_lookup(m, tags + 0x18, wielder) if wielder else None
            fi = base.map_lookup(m, faction + 0x12050, wielder) if wielder else None
            pairs.append({'entity': entity, 'wielder': wielder, 'self': wielder == entity,
                'wielderTags': '0x%X' % m.u64(m.ptr(tags + 0x38) + 8 * ti) if ti is not None else None,
                'wielderFaction': m.u32(m.ptr(faction + 0x12078) + 4 * fi) if fi is not None else None})
        user = m.ptr(m.game + 0x347CEF0)
        attribution[name] = {'localPeer': '%016X' % m.u64(user + 0xB398), 'wieldable': sorted(pairs,
            key=lambda p: p['entity'])}
        m.close()
    if not all(any(p['wielderTags'] == '0x9' and p['wielderFaction'] == 1 and not p['self'] for p in v['wieldable'])
            for v in attribution.values()):
        raise ValueError('no weapon reads as wielded by the avatar (tags 0x9, faction 1): %r' % attribution)

    turret_types = {json.dumps(v['types'], sort_keys=True) for v in turret_weapon.values()}
    if len(turret_types) != 1:
        raise ValueError('the turret weapon types differ between snapshots')

    # Residency [O]: base_faction (which lists the Pelican entity) is resident in the mission snapshots.
    import research_package_residency as rpr
    loader = rpr.loader_pins(snapshot_image.Snapshot(build_profile.SNAPSHOT))
    resident = {}
    for name in MISSION_SNAPSHOTS:
        s = snapshot_image.Snapshot(build_profile.snapshot_directory() / name)
        states, _refs, _capacity = rpr.residency(s, loader)
        s.close()
        resident[name] = bool(states.get(BASE_FACTION))
    if not all(resident.values()):
        raise ValueError('base_faction is not resident in every mission snapshot: %r' % resident)

    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'gameDll': {'sha256': base.PROFILE_DLL_SHA},
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation,
        'pelican': {'entity': '0x%016X' % PELICAN, 'unit': PELICAN_UNIT, 'package': 'packages/content/base_faction',
            'packageId': '0x%016X' % BASE_FACTION, 'residentInMissionSnapshots': resident,
            'transportSettings': {'cargoTimer': settings[0], 'second': settings[1]}, 'podSettings': False},
        'vehicles': dict(sorted(vehicles.items())),
        'invalidEntity': 0,
        'components': {
            'behavior': {'global': '0x%X' % BEHAVIOR, 'keys': 0x40, 'capacity': 0x48, 'empty': 0x4C, 'multiplier': 0x50,
                'handles': 0x58, 'records': 0x60, 'stride': 0x1F8, 'behaviourId': 0x0, 'context': 0x8},
            'transport': {'global': '0x%X' % TRANSPORT, 'count': 0x10, 'keys': 0x20, 'capacity': 0x28, 'empty': 0x2C,
                'multiplier': 0x30, 'handles': 0x38, 'elements': 0x40, 'stride': 0x40, 'cargo': 0x0,
                'spawnedCargo': 0x8, 'cargoTimer': 0xC, 'associated': 0x28, 'handleEntityResource': 0x0,
                'handleEntity': 0x8, 'handleNetwork': 0x10},
            'bearer': {'global': '0x%X' % BEARER, 'keys': 0x40, 'capacity': 0x48, 'empty': 0x4C, 'multiplier': 0x50,
                'records': 0x68, 'stride': 0x308, 'position': 0x2E0},
            'clock': {'global': '0x%X' % CLOCK, 'now': 0x18, 'unitsPerSecond': US}},
        # The flight (offsets in P = the Behavior record + 8).
        'flight': {'stage': 0x0, 'pending': 0x8, 'stageTime': 0x170, 'releaseTime': 0x178, 'hoverStart': 0x180,
            'approachTime': 0x188, 'target': 0x1BC, 'flags': 0x1E0, 'released': 1,
            'stages': {'1': 'climb from the spawn point', '2': 'approach',
                '3': 'to the hover point (its recorded position plus a height)',
                '4': 'airlift pickup (associated)', '5': 'airlift (associated)', '6': 'hover, release, then depart',
                '7': 'released (stage 4): depart', '8': 'depart', '9': 'depart', '10': 'fly out; removed'},
            'microseconds': {'hoverRelease': 6 * US, 'releasedDeparture': 600_000, 'stage7Departure': 3 * US,
                'stage8': US, 'stage9': US, 'removal': 12 * US}},
        'lifetime': {'nativeHover': 'released at the target or 6 s after the hover start; departs 0.6 s later',
            'perInstance': 'P+0x178 (the release time) of one Behavior record',
            'claimed180s': 'not in the game: the mod\'s own limit (THREE_MINUTE_LIMIT)'},
        'cargo': {'window': False, 'why': 'timer 0.0 at creation; the transports update after the beacons in the same '
            'pass, so the first transport update spawns the cargo in the frame the Pelican was created'},
        'association': {'beaconStateOffset': 0x430, 'writtenByBeaconCode': False,
            'meaning': 'airlift: the Pelican flies to the associated entity and picks it up (stages 4 and 5)'},
        # The spawn request as runtime/pelicans.lua M.spawn calls it: the descriptor the beacon dispatcher builds, with
        # no context (the world's own default, all zero: no cargo, no associated entity) and no modifier block.
        'spawn': {'rva': SPAWN, 'prologue': prologue, 'world': '0x%X' % WORLD,
            'descriptor': {'size': 0x58, 'authority': 0x0, 'network': 0x4, 'networkNone': 0x7FFF, 'pose': 0x8,
                'context': 0x48, 'modifiers': 0x50},
            'defaultContext': DEFAULT_CONTEXT, 'contextSize': CONTEXT_SIZE, 'defaultModifiers': DEFAULT_MODIFIERS,
            'defaultsPerSnapshot': defaults, 'settingsTable': SETTINGS_TABLE, 'settingsSlots': SETTINGS_SLOTS,
            'settingsStride': 40, 'settingsBase': 0x1C0},
        # The hover anchor: the drop-position record, set from the spawn context +0x610 at creation.
        'anchor': {'global': '0x%X' % ANCHOR, 'records': 0x60, 'stride': 0x20, 'position': 0x0, 'replicated': '0xD5077FC6',
            'contextPosition': 0x610, 'contextFlag': 0x61C, 'contextValue': 0x620, 'mapKeys': 0x30, 'mapCapacity': 0x38,
            'mapEmpty': 0x3C, 'mapMultiplier': 0x40,
            'readBy': {'stage1': '0x4D60D0 (approach point = anchor + an offset)',
                'stage3': '0x4D5A60 (hover point = anchor + a random height, a free spot)'}},
        'orbit': {'behaviour': 202, 'stage': 5, 'dispatch': {k: '0x%X' % v for k, v in dispatch.items()},
            'function': '0x4D5E60', 'constants': constants,
            'rule': 'within 5 m of its point: the next point = anchor + radius at (its angle + pi/4), 30 m up'},
        'flightTarget': {'global': '0x%X' % FLIGHT, 'keys': 0x30, 'capacity': 0x38, 'empty': 0x3C, 'multiplier': 0x40,
            'records': 0x50, 'stride': 0x534, 'target': 0x4FC},
        # The two movement components whose target push is native (read-only diagnostics: a Pelican in neither is
        # retargeted by plain data).
        'nativeMovers': {'ground': {'global': '0x3326418', 'keys': 0x30, 'capacity': 0x38, 'empty': 0x3C,
                'multiplier': 0x40},
            'other': {'global': '0x3326638', 'keys': 0x3C38, 'capacity': 0x3C40, 'empty': 0x3C44, 'multiplier': 0x3C48}},
        'variants': {'settings': {'offset': '0x%X' % BEHAVIOUR_SETTINGS, 'slots': BEHAVIOUR_SLOTS, 'slotStride': 16,
                'entries': BEHAVIOUR_ENTRIES, 'entryStride': 12}, 'override': 0x67C, 'byType': variants,
            'extract': extract},
        'extraction': {'behaviour': 202, 'stages': 13, 'holdingStage': 5, 'landingStage': 6, 'departureStage': 13,
            'landingPoint': 0x1B0, 'landingRadius': 50.0, 'circleRadius': 30.0, 'circleHeight': 30.0,
            'abort': '0x4B0030', 'landingDecision': '0x4D6930'},
        'pose': {'transform': '0x3326508', 'rotation': 0x2D0, 'position': 0x2E0, 'forwardAxis': 'y'},
        'attachment': {'global': '0x3326698', 'map': 0x18, 'handles': 0x30, 'records': 0x38, 'stride': 0xAC,
            'parentLink': 0x0, 'parentNode': 0x4, 'worldPosition': 0x10, 'worldRotation': 0x1C, 'handleLink': 0xC,
            'observedPair': pair},
        'turretComponents': {'mount': {'global': '0x3326438', 'map': 0x20}, 'turret': {'global': '0x3326D70', 'map': 0x28},
            'projectileWeapon': {'global': '0x33266D8', 'map': 0x50}, 'weaponData': {'global': '0x3326CE0', 'map': 0x30}},
        # What a turret fires and what of it is per instance (read-only: PelicanTurretProbe 0.3.0). Maps: keys, capacity
        # +8, empty key +0xC, multiplier +0x10 from the map offset.
        'turretWeapon': {
            'weapon': {'global': '0x3326660', 'map': 0x28, 'records': 0x50, 'stride': 40, 'flags': 0x0,
                'magazine': 0x80, 'rounds': 0x100, 'heat': 0x200},
            'projectileWeapon': {'global': '0x33266D8', 'map': 0x50, 'rof': 0x70, 'rofStride': 0x20, 'rofSlots': 0x10,
                'rofIndex': 0x1C, 'instances': 0x78, 'instanceStride': 0xA8, 'interval': 0xC, 'current': 0x80,
                'currentStride': 12, 'currentRpm': 0x4, 'copies': 0x90, 'copyRecords': 0xD0, 'copyStride': 0x268,
                'copyCount': 0xC8, 'projectileType': 0x0, 'rpmSlots': 0x4},
            'magazine': {'global': '0x3326648', 'map': 0x20, 'records': 0x48, 'stride': 16, 'rounds': 0x0, 'pattern': 0x4,
                'chambered': 0x8, 'patternLength': 0xC, 'copies': 0x60},
            'heat': {'global': '0x3326D48', 'map': 0x28},
            'windUp': {'global': '0x33267A0', 'map': 0x28},
            'observed': turret_weapon[MISSION_SNAPSHOTS[0]]['types'],
            'snapshots': turret_weapon,
            'perInstance': ['the shot interval (instance record +0xC, set once from the resolved RPM)',
                'the rate-of-fire record and current RPM', 'the magazine record (rounds, chambered type)',
                'a resolved ProjectileWeapon or magazine copy, only when an entity delta made one at creation'],
            'shared': ['ProjectileWeaponComponentData (projectile type, RPM)', 'the magazine pattern',
                'TurretComponentData', 'WeaponDataComponentData', 'the wind-up component (spin-up)',
                'the entity deltas (a read-only table)']},
        # The Gatling turret experiment (runtime/pelican_gatling.lua): the game's own routines it may call, each by its
        # exact entry bytes, and the per-instance records it reads and writes.
        'gatling': {
            'attach': {'rva': 0x812540, 'prologue': game_data[0x812540:0x812581].hex()},
            'remove': {'rva': 0xFDC310, 'prologue': game_data[0xFDC310:0xFDC325].hex()},
            'unlink': {'rva': 0xB0B020, 'prologue': game_data[0xB0B020:0xB0B038].hex()},
            'copy': {'rva': 0x61AF10, 'prologue': game_data[0x61AF10:0x61AF49].hex()},
            'world': '0x%X' % WORLD,
            'mount': {'global': '0x3326438', 'map': 0x20, 'children': 0x48, 'networks': 0x50, 'stride': 24, 'slots': 5},
            'attachable': {'offset': 0x8C, 'rotation': 0x98},
            'destroy': {'rva': 0xFDC820, 'prologue': game_data[0xFDC820:0xFDC86E].hex()},
            'entityRecords': {'base': 0xF32F18, 'stride': 24, 'network': 0x10, 'flags': 0x14, 'noNetwork': 0x7FFF},
            'network': {'manager': 0x8, 'map': 0xB020, 'flags': 0x201C},
            'pending': {'count': 0xF3EF18, 'list': 0xF3EF20},
            'copyCapacity': 0x30,
            'magazineCopy': {'rva': 0x770B10, 'prologue': game_data[0x770B10:0x770B4A].hex(), 'map': 0x60,
                'records': 0xA0, 'stride': 160, 'count': 0x98, 'capacity': 0x4, 'mode': 0x0, 'pattern': 0x4,
                'slots': 32},
            'setBehaviour': {'rva': 0x843EA0, 'prologue': game_data[0x843EA0:0x843EC4].hex(),
                'manager': '0x3326740'},
            'turretActive': {'records': 0x58, 'stride': 16, 'active': 0x0},
            'ai': {'table': 0x4795C4, 'entry645': game_data[0x4795C4 + 4 * 644:0x4795C4 + 4 * 645].hex(),
                'entry213': game_data[0x4795C4 + 4 * 212:0x4795C4 + 4 * 213].hex(), 'id': 0x0, 'stage': 0x8,
                'pending': 0xC, 'transitioning': 0x10, 'target': 0x18, 'chin': 645, 'gatling': 213,
                'stages213': {'1': 'spawned (waits 2 s)', '6': 'deploy decision', '7': 'deploy', '8': 'deploy',
                    '9': 'deploy', '2': 'search', '3': 'track', '4': 'stage 4', '5': 'stage 5',
                    '10': 'weapon unusable (waits for a flag the chin turret lacks)', '12': 'FIRING'},
                'stages645': {'1': 'idle', '2': 'aiming', '3': 'FIRING (0.5 s window)', '4': 'turret inactive'}},
            'behaviour645': {'fireStart': 0x180, 'aimStart': 0x178, 'fireWindow': 500000, 'aimMinimum': 1500000,
                'fireStage': 3, 'aimStage': 2},
            'pwTypes': {'offset': 0xF12E80, 'slots': 542, 'records': 0x21E0, 'stride': 0x268},
            'magazineTypes': {'offset': 0xF124A0, 'slots': 540, 'records': 0x21C0, 'stride': 160},
            'invalidEntity': 0,
            'gatlingStratagem': 623391597,
            'gatlingResource': '%016X' % GATLING, 'chinTurretResource': '%016X' % TURRET_HMG},
        # The fire effects block +0xA0..+0xDF: effect A (+0xA0, node +0xA8), the casing (+0xB0, nodes +0xB8..+0xC4,
        # parameters +0xD4..+0xDC), effect C (+0xC8, node +0xD0).
        'casing': {'effects': 0xA0, 'effectsEnd': 0xE0, 'particles': 0xB0, 'nodes': 0xB8, 'nodeSlots': 4,
            'parameters': 0xD4, 'parametersSize': 12,
            'muzzleFlash': 0xE0, 'instanceCasing': 0x90, 'instanceMuzzleFlash': 0x88, 'instanceNodeCount': 0x6C,
            'instanceNodes': 0x74, 'ejectorNode': '%08X' % ejector, 'muzzleNode': '%08X' % muzzle,
            'observed': casings, 'gatlingPackage': '0x992D325D88DE5FBF', 'gatlingPackageLists': listed,
            'rule': 'the casing is the resolved ProjectileWeapon +0xB0 at its ejector nodes; the pooled particle system '
                'is looked up on the first shot and kept in the instance record +0x90'},
        'firstShot': {'chambered': 'magazine record +8', 'rederivedAfterEveryShot': '0x744690',
            'rule': 'the round chambered before a weapon copy is fired first; the next is chambered from the copy'},
        'rateSeed': {'modifier': '0x33', 'factor': struct.unpack_from('<f', game_data, 0x23C6CCC)[0],
            'rule': 'a new weapon starts at its resolved RPM (Y slot) times the factor while the modifier is active'},
        'ai213': {'repick': 0x98, 'lastSeen': 0x28, 'aimPoint': 0x1C, 'senseBits': 0x64, 'fireCheck': 0xB0,
            'repickWithTarget': 1000000, 'pending': 0xC, 'lostFlags': 0x1E8, 'lostBit': 0x10, 'lostSince': 0x198, 'lostTimeout': 1000000,
            'fireStage': 12, 'releaseStage': 4, 'aimStage': 5, 'aimDegrees': 3.0, 'deathStage': 11,
            'stages': {'2': 'search', '3': 'alert (searches the last position)', '4': 'leaves firing (the trigger '
                'released)', '5': 'aims (fires only within 3 degrees)', '10': 'weapon unusable', '12': 'FIRING'},
            'rule': 'stage 12 leaves only when empty or with the target-lost flag set for 1 s; a re-pick clears it, '
                'so a selected target keeps it firing wherever the barrel points'},
        'ammo': {'entries': 0x50, 'entryStride': 12, 'entrySpares': 0x0, 'entryRounds': 0x4, 'entryChamberEmpty': 0x8,
            'records': 0x48, 'recordRounds': 0x0, 'capacity': 0x88, 'spareMagazines': 0x8C, 'perResupply': 0x90,
            'maxSpareMagazines': 0x94, 'chamber': 0x9C, 'observed': ammo,
            'rule': 'a magazine spawns with capacity - 1 rounds and one chambered; the rounds live in entry +4 (the '
                'record +0 copies it); the capacity is the resolved +0x88; neither turret reloads'},
        'ammoNetwork': {'fields': ammo_net, 'roundsMax': ammo_net['rounds'][0]['max'],
            'rule': 'a value above the field\'s range is saturated in place at the next flush (every shot queues it); '
                'the host\'s rounds therefore never exceed roundsMax for long'},
        'heading': {'global': '0x3326DB0', 'map': 0x28, 'simulated': 0x18, 'records': 0x48, 'stride': 0x28,
            'omega': 0x0, 'desired': 0xC, 'entries': 0x58, 'entryStride': 0x18, 'enabled': 0x14, 'crashed': 0x15,
            'flightMode': 0x52C, 'holdMode': 1, 'holdStage': 6,
            'rule': 'in the hold (stage 6, flight mode 1) nothing sets D; written there, the controller turns the body '
                'toward it smoothly (about a 1 s response) and replicates the rotation'},
        'aim': {'weaponData': {'global': '0x3326CE0', 'map': 0x30, 'records': 0x58, 'stride': 0x3F0, 'aim': 0x0,
                'recoilA': 0x1C, 'recoilB': 0x38, 'recoilSize': 0x1C, 'muzzle': 0xFC, 'muzzleVelocity': 0x21C,
                'types': {'offset': 0xF12BD8, 'slots': 0x2DA, 'records': 0x2DA0, 'stride': 0x4D0, 'recoilA': 0x0,
                    'recoilB': 0x1C}},
            'targeting': {'global': '0x3326D30', 'map': 0x150, 'records': 0x178, 'stride': 0xD0, 'target': 0x0,
                'point': 0x8},
            'wielder': {'global': '0x3326420', 'map': 0x30, 'records': 0x60, 'stride': 0x1D0, 'slotStride': 0x50,
                'recoil': 0x14},
            'projectileSpeed': round(speed148, 3), 'observed': recoil,
            'rule': 'the bullets go from the muzzle toward WeaponData +0 (the turret\'s achieved pointing); the AI '
                'aims at T plus a lead for the muzzle\'s own velocity the bullets never get; recoil climbs by the '
                'weapon\'s own instance blocks'},
        'targetSet': {'setter': {'rva': 0x4AF4E0, 'prologue': game_data[0x4AF4E0:0x4AF50A].hex()},
            'context': {'handles': 0x58, 'records': 0x60, 'stride': 0x1F8, 'state': 8, 'handleEntity': 8},
            'record': {'target': 0x18, 'previous': 0x70, 'perceiver': 0x68, 'hasTarget': 0x78, 'entry': 0x18,
                'entrySize': 0x50},
            'perception': {'global': '0x3326548', 'map': 0x30, 'records': 0x50, 'stride': 0x13F8, 'sensors': 0x0,
                'sensorBit': 0x8, 'sensorStride': 8, 'maxSensors': 32, 'factionMask': 0x13E8,
                'lists': [{'name': 'A', 'count': 0x310, 'entries': 0x318}, {'name': 'B', 'count': 0x818, 'entries': 0x820},
                    {'name': 'C', 'count': 0xD20, 'entries': 0xD28}],
                'listMax': 16, 'entryStride': 0x50, 'entryEntity': 0x0, 'entryPosition': 0x4, 'entrySeen': 0x10,
                'entryScore': 0x44, 'entryFlags': 0x48, 'entrySense': 0x4C},
            'faction': {'global': '0x3326CB8', 'map': 0x12050, 'masks': 0x12078},
            'entityFlags': {'global': '0x3326430', 'map': 0x18, 'values': 0x38, 'invalid': 25, 'unscored': 35},
            'range': 100.0, 'observed': perception,
            'rule': 'the setter installs a perceiver\'s live entry as the AI\'s target the way its own pick does; it is '
                'not sticky (the next re-pick decides again) and validates nothing beyond its refresh'},
        'spread': {'instance': 0x58, 'word': 0x60, 'type': 0x54, 'typeWord': 0x5C, 'multipliers': [0x3E0, 0x3E8],
            'unit': 'milliradians (full width: a shot turns by up to half of it each way)', 'observed': spread,
            'rule': 'the shot turns by the weapon\'s own WeaponData instance spread; the instance takes its type\'s '
                'spread times its own multipliers once, at creation, and again only on an ammo-type switch'},
        'attribution': {'wieldable': {'global': '0x3326730', 'map': 0x18, 'wielder': 0x38},
            'tags': {'global': '0x3326430', 'map': 0x18, 'values': 0x38}, 'noCredit': 0x10000000, 'factionBit': 1,
            'noNetwork': 0x7FFF, 'healthOwner': 0x30, 'healthCreditor': 0x38, 'observed': attribution,
            'rule': 'a turret shot is credited to the peer owning its wielder\'s network object, unless the wielder '
                'carries the no-credit tag; the chin turret wields itself and carries it, so its kills credit nobody'},
        'apDonor': {'projectile': 275, 'name': 'MG-206 Heavy Machine Gun', 'damage': 205, 'ap': ap[275],
            'assetKey': 'support_weapon/MG-206 Heavy Machine Gun', 'velocity': 980.0, 'mass': 52.0,
            'rowVelocity': 0x20, 'rowMass': 0x24, 'rowDamage': 0x3C, 'rowSize': 272,
            'standard': {'projectile': 148, 'name': 'MG-43 Machine Gun', 'ap': ap[148], 'velocity': 820.0, 'mass': 11.0},
            'alternatives': [
                {'projectile': 251, 'name': 'TD-110 Maelstrom coaxial gun', 'damage': 205,
                    'why': 'the same round (damage 205, 980 m/s, mass 52); only a visual resource differs; its package '
                        'is the whole tank'},
                {'projectile': 68, 'name': 'EXO-55 Breakthrough right gun', 'damage': 188,
                    'why': 'AP4 but a slow, light pellet (385 m/s, mass 6), 90 damage'},
                {'projectile': 226, 'name': 'APW-1 Anti-Materiel Rifle', 'damage': 206, 'why': 'a sniper round'}],
            'observed': donor_rows,
            'rule': 'the chin turret\'s own ProjectileWeapon copy names projectile 275 instead of 148; no projectile or '
                'damage definition is written'},
        'turretRate': {'currentRpm': 'manager +0x80, entry +4 (12-byte entries), replicated under key 0x4CBCC2A2',
            'cachedRpm': 0x64, 'interval': 0xC, 'cooldown': 0x8,
            'rule': 'every update: current RPM != cached -> cached = current, interval = 60 / current; each shot adds the '
                'interval to the cooldown',
            'seeded': 'at creation, on the creating machine only, from the resolved RPM slots (x0.9 with modifier 0x33)',
            'resetBy': ['the system pass when the mission fire-rate modifier state changes (every weapon)',
                'the system pass every update for weapon_heat weapons', 'the rate-of-fire selector'],
            'snapshotsCachedIsCurrent': all(v['cachedIsCurrentRpm'] for v in turret_weapon.values())},
        'copyRoutine': {'rva': '0x61AF10', 'arguments': ['the projectile_weapon manager (component world + 0xF0B3B8)',
                'the entity handle (+0 resource, +8 entity)', 'a delta entry {kind, first patch, count}'],
            'unmodifiedCopy': 'count 0: no patch is read', 'existing': 'an entity with a copy only gets the patches',
            'capacity': {'count': 0xC8, 'capacity': 0x30, 'checked': False,
                'grownBy': 'the creation reserve only (0x5811AC -> 0x6199D0)'},
            'scratch': 'per engine thread (engine thread index -> per-thread arena)',
            'removal': '0x619F90 drops the copy with the entity',
            'replicationCall': False},
        'nativeOnly': ['a cargo-less transport Pelican (the generic spawn 0xFD9710 with an empty context)',
            'a new hover point while alive (0x4D1150 pushes P+0x1BC into the flight)',
            'an early withdrawal'],
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; vehicles', len(vehicles), '; settings', settings)


if __name__ == '__main__':
    main()
