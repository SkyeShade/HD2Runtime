"""Native limb injury of the local player's avatar (research for hd2.actions.injure).

Read-only: nothing writes, nothing touches a live process. Proves, on build F5FEE03DCFDB, from the unpacked game.dll
and executable images held by the retained mission snapshots:

1. Zones. The Helldiver avatar (avatar_helldiver, 0x4D1C334D294DFA97) has six damageable zones in its
   HealthComponentData: head 85, body 60, arm_left 35, arm_right 35, leg_left 45, leg_right 45 (zone health), each
   listing the physics actors a hit on it can name (head: head, neck; body: chest, hips, spine1, spine2, boss;
   arm_right: r_clavicle, r_shoulder, r_hand, r_elbow; ...). The health record keeps each zone's health
   (record+0xF8 + 4*zone) and a 2-bit zone state (record+0x20, 2 bits per zone): 0 healthy, 1 down, 2 dead. A zone
   whose health reaches 0 (avatar zones have no constitution) is dead: that is an injured limb. The game's own
   readers: the Warp Pack limb filter (0x921E50, state == 2) and the injury HUD (0x18201F0, arm_left / leg_left /
   body / leg_right / arm_right, state >= 1).
2. ApplyDamage 0x9235F0 (health manager, target, kind, element, 15 stack arguments) resolves the zone whose actor
   list (zone +0x1C8, 24 actor names) holds the hit actor name (argument 13), lowers that zone's health
   (clamped at -constitution), derives its state, and applies the zone's affects_main_health share to main health.
   For a target this machine owns it updates the synced health component (0x6B2A90, replicated network properties);
   otherwise it sends the damage to the owner (0xBF2F50). It applies no damage to an avatar in the Ship state.
3. QueueDamage 0x129F910 (ignored, kind, element, target, damage, a6, dealer GOID, owner GOID, creditor, a10, f11,
   f12, f13, const float *a14, const float *a15, actor handle, a17, a18, f19) appends one 0x70-byte damage event to
   queue 0 of the damage system (global 0x347CF38; count +0x201120, capacity 4096, entries from +0x1120). It refuses
   the invalid entity, a target without a health record and a full queue. The world update drains the queue every
   frame (0x13F7D5E -> 0x12A6EF0 -> 0x12A7D40); the consumer turns the event's actor handle back into the actor's
   name through the engine actor API (validity slot +0x18, name slot +0x78 of the table at game+0x3326338) and calls
   ApplyDamage with it as argument 13. An event whose owner resolves to the target itself is applied only by the
   target's owner.
4. VG-70 Variable. The weapon fire path (0x7533C0) plays WeaponDataComponentData+0x3B0 instead of +0x3AC when the
   weapon fires in fire mode 7; only the VG-70 Variable and the expendable machine gun set it (AbilityId 50,
   FireMode 7 at +0x98). Ability 50 (dispatcher entry 49 -> 0x109E6C0) queues, on the machine that owns the weapon
   holder, 15 points of Ability damage (kind 6, element 0) at the wielder's r_shoulder actor: 0x11ADF50 resolves the
   actor handle with the engine unit API (game+0x3326310, slot +0x10 = exe 0x799DE0, lookup by actor name) and calls
   QueueDamage. r_shoulder is an arm_right actor: that is the shooter's right-arm self-injury.
5. Warp Pack. The displacement update iterates only this machine's owned instances (+0x14 owned count, written by
   the add-instance function when the instance is owned) and, after a warp above the safe heat, calls 0x88DCC0,
   which picks one HeatInjuryInfo entry (DisplacementComponentData +0xA0, 12 x 24 bytes) whose limb is not already
   dead and calls ApplyDamage directly with the entry's limb actor name (head, l_hand, r_hand, l_knee, r_knee) as
   argument 13 and Flat damage (kind 7). Both of the game's self-injuries run on the owner of the avatar.
6. Snapshots. In every mission snapshot every pin is byte-identical, queue 0 is drained (count 0), the engine unit
   and actor API slots are the pinned exe functions, the local avatar is owned by this machine with its zones at
   full health and state 0, it accepts kind 6 at x1.0, and its unit's actor list (emulating exe 0x799DE0) holds
   every limb actor Runtime names.

Requires the research-only package capstone.
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

OUTPUT = ROOT / 'research/player-injury-path-F5FEE03DCFDB.json'
SNAPSHOTS = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
SHIP_SNAPSHOTS = base.SNAPSHOTS

AVATAR_TYPE = 0x4D1C334D294DFA97
G_HEALTH, G_DAMAGE, G_INVALID = 0x3326688, 0x347CF38, 0x3483C20
G_UNIT_API, G_ACTOR_API = 0x3326310, 0x3326338
G_DISPLACEMENT = 0x3326AC8
QUEUE_DAMAGE = 0x129F910
QUEUE_COUNT, QUEUE_CAPACITY, QUEUE_ENTRIES, EVENT_SIZE = 0x201120, 0x1000, 0x1120, 0x70
APPLY_DAMAGE = 0x9235F0
UNIT_API_TABLE, UNIT_ACTOR_SLOT, UNIT_ACTOR = 0x27CD4C0, 0x10, 0x799DE0      # exe
ACTOR_API_TABLE, ACTOR_VALID_SLOT, ACTOR_VALID, ACTOR_NAME_SLOT, ACTOR_NAME = 0x27CD910, 0x18, 0x7972F0, 0x78, 0x799CE0
EXE_UNIT_RECORDS, EXE_ACTOR_POOLS = 0x27C5B40, 0x2369B00                       # exe .data (emulation only)
ZERO_VECTOR, DOWN_VECTOR, ONE = 0x3799DA8, 0x221E698, 0x23C6D70                # the VG-70 call's constants
RECORD_STRIDE, EXT_STRIDE = 0x1B8, 0x1C
ZONE_BASE, ZONE_STRIDE, ZONES = 520, 552, 38
# Limbs Runtime names: the actor the game's own injuries name (the Warp Pack's HeatInjuryInfo limbs; chest is the
# body actor the Warp Pack names for its chest entry and the game's own chest Bleed injury passes to ApplyDamage).
LIMBS = ['head', 'chest', 'l_hand', 'r_hand', 'l_knee', 'r_knee']
KIND_ABILITY, KIND_FLAT = 6, 7
DAMAGE_SOURCE_KINDS = ['Projectile', 'Ricochet', 'DPS', 'Single_Shot_Beam', 'Explosion', 'Impact', 'Ability', 'Flat',
    'Drown', 'BleedOut']

GAME_PROOFS = {
    'queueDamage': [
        (0x129F910, 'push rbp', None, 'QueueDamage(ignored, kind, element, target, damage, a6, dealer, owner, '
            'creditor, a10, f11, f12, f13, const float *a14, const float *a15, actor, a17, a18, f19)'),
        (0x129F931, 'cmp r9d, dword ptr [rip + {rip}]', G_INVALID, 'the invalid entity is refused'),
        (0x129F938, 'mov r14d, r8d', None, 'r14d = element (argument 3)'),
        (0x129F93B, 'mov rdi, qword ptr [rip + {rip}]', G_DAMAGE, 'the damage system global'),
        (0x129F942, 'mov r8d, edx', None, 'r8d = kind (argument 2)'),
        (0x129F945, 'mov ebx, r9d', None, 'ebx = target (argument 4)'),
        (0x129F94E, 'mov rax, qword ptr [rip + {rip}]', G_HEALTH, 'the health manager: the target needs a record'),
        (0x129F957, 'mov r8d, dword ptr [rax + 0x1038]', None, 'health hash capacity'),
        (0x129F9BB, 'cmp eax, -1', None, 'no health record ...'),
        (0x129F9BE, 'je 0x129fcba', None, '... return without writing'),
        (0x129F9C4, 'mov eax, dword ptr [rdi + 0x201120]', None, 'queue 0 count'),
        (0x129F9CA, 'cmp eax, 0x1000', None, 'queue 0 holds 4096 events'),
        (0x129F9CF, 'jae 0x129fcba', None, 'full: return without writing'),
        (0x129F9EE, 'imul rsi, rax, 0x70', None, 'event stride 0x70'),
        (0x129FA02, 'mov r12d, dword ptr [rbp + 0xaf]', None, 'argument 16: the actor handle'),
        (0x129FA09, 'mov dword ptr [rdi + 0x201120], eax', None, 'count + 1'),
        (0x129FA0F, 'mov eax, dword ptr [rbp + 0x67]', None, 'argument 7: dealer GOID'),
        (0x129FA12, 'mov dword ptr [rsp + 0x40], eax', None, '-> event +0x10'),
        (0x129FA16, 'mov rax, qword ptr [rbp + 0x77]', None, 'argument 9: creditor peer (u64)'),
        (0x129FA1A, 'mov qword ptr [rsp + 0x48], rax', None, '-> event +0x18'),
        (0x129FA25, 'movzx eax, byte ptr [rbp + 0x5f]', None, 'argument 6 (byte)'),
        (0x129FA29, 'mov byte ptr [rbp - 0x71], al', None, '-> event +0x28'),
        (0x129FA2C, 'mov eax, dword ptr [rbp + 0x57]', None, 'argument 5: damage'),
        (0x129FA3E, 'mov dword ptr [rbp - 0x6d], eax', None, '-> event +0x2C (the damage the consumer applies)'),
        (0x129FA37, 'mov r13, qword ptr [rbp + 0x9f]', None, 'argument 14: vec3 pointer (copied)'),
        (0x129FA49, 'mov r15d, dword ptr [rbp + 0x6f]', None, 'argument 8: owner GOID'),
        (0x129FA5F, 'mov rax, qword ptr [rbp + 0xa7]', None, 'argument 15: vec3 pointer (copied)'),
        (0x129FA82, 'mov r14d, dword ptr [rbp + 0xb7]', None, 'argument 17'),
        (0x129FAAD, 'mov dword ptr [rsp + 0x30], ebx', None, 'event +0x00 target'),
        (0x129FAB1, 'mov dword ptr [rsp + 0x34], r8d', None, 'event +0x04 kind'),
        (0x129FAB6, 'mov dword ptr [rsp + 0x3c], r12d', None, 'event +0x0C actor handle'),
        (0x129FAC0, 'mov dword ptr [rsp + 0x44], r15d', None, 'event +0x14 owner GOID'),
        (0x129FACE, 'movups xmmword ptr [rsi + rdi + 0x1120], xmm0', None, 'event +0x00..0x0F into queue 0'),
        (0x129FADA, 'movups xmmword ptr [rsi + rdi + 0x1130], xmm1', None, 'event +0x10..0x1F'),
        (0x129FB06, 'movups xmmword ptr [rsi + rdi + 0x1140], xmm0', None, 'event +0x20..0x2F'),
        (0x129FB71, 'call 0x129f4b0', None, 'relation flags (owner / target: player, owned) -> event +0x6C'),
        (0x129FB82, 'mov dword ptr [rsi + rdi + 0x118c], ecx', None, 'event +0x6C'),
        (0x129FB96, 'test r14d, r14d', None, 'element 0: no secondary element entry'),
        (0x129FB99, 'je 0x129fc9a', None, 'skip it'),
    ],
    'drain': [
        (0x13F7D5E, 'call 0x12a6ef0', None, 'the world update drains the damage system every frame'),
        (0x12A6F17, 'mov eax, dword ptr [rcx + 0x201120]', None, 'queue 0 count'),
        (0x12A6F1D, 'mov r15d, 0x10', None, 'at most 16 events per call'),
        (0x12A6FA3, 'call 0x12a7d40', None, 'ConsumeDamageEvent'),
        (0x12A6FA8, 'add rdi, 0x70', None, 'event stride'),
    ],
    'consumer': [
        (0x12A7D6E, 'mov ecx, dword ptr [rdx + 0xc]', None, 'event +0x0C actor handle'),
        (0x12A7D77, 'cmp ecx, -1', None, '-1: no actor (the default zone)'),
        (0x12A7D7C, 'mov rax, qword ptr [rip + {rip}]', G_ACTOR_API, 'the engine actor API'),
        (0x12A7D83, 'mov rdx, qword ptr [rax + 0x18]', None, 'slot +0x18: the handle is a live actor'),
        (0x12A7D87, 'call rdx', None, ''),
        (0x12A7D8D, 'mov rax, qword ptr [rip + {rip}]', G_ACTOR_API, 'the engine actor API'),
        (0x12A7D94, 'mov ecx, dword ptr [r14 + 0xc]', None, 'the actor handle'),
        (0x12A7D98, 'mov rdx, qword ptr [rax + 0x78]', None, 'slot +0x78: the actor\'s name'),
        (0x12A7D9C, 'call rdx', None, ''),
        (0x12A7DAF, 'mov dword ptr [rbp - 0x70], edi', None, 'the actor name, kept for ApplyDamage'),
        (0x12A7DA5, 'mov ebx, dword ptr [r14 + 0x14]', None, 'owner GOID'),
        (0x12A7DB2, 'call 0xfd9ba0', None, 'resolved to an entity'),
        (0x12A7DC2, 'cmp eax, dword ptr [r14]', None, 'the owner is the target itself ...'),
        (0x12A7DD8, 'test byte ptr [rax + 0x14], 1', None, '... then only the target\'s owner applies it'),
        (0x12A81DC, 'mov esi, dword ptr [r14 + 0x2c]', None, 'event damage'),
        (0x12A8280, 'mov eax, dword ptr [rbp - 0x70]', None, 'the actor name ...'),
        (0x12A8283, 'mov dword ptr [rsp + 0x60], eax', None, '... is ApplyDamage argument 13'),
        (0x12A82E0, 'mov rcx, qword ptr [rip + {rip}]', G_HEALTH, 'the health manager'),
        (0x12A82EB, 'call 0x9235f0', None, 'ApplyDamage'),
    ],
    'applyZone': [
        (0x92364C, 'mov eax, dword ptr [rbp + 0xb20]', None, 'ApplyDamage argument 13: the hit actor name'),
        (0x923652, 'mov dword ptr [rbp - 0x20], eax', None, ''),
        (0x9238B2, 'cmp dword ptr [rax + 0xac21c], 3', None, 'no damage to an avatar in the Ship state'),
        (0x92392E, 'mov edx, dword ptr [rdx + rax + 0x10]', None, 'per-kind 2-bit acceptance mask (ext +0x10)'),
        (0x923937, 'je 0x925d31', None, 'mask 0: no damage'),
        (0x923C50, 'mov r10d, dword ptr [rbp - 0x20]', None, 'the hit actor name'),
        (0x923C57, 'imul rdi, r8, 0x228', None, 'zone stride 0x228'),
        (0x923C68, 'lea rax, [rdi + 0x3d0]', None, 'the zone\'s actor names (settings +0x208 + zone +0x1C8)'),
        (0x923C83, 'cmp ecx, r10d', None, 'the zone lists the hit actor'),
        (0x923C8E, 'cmp edx, 0x18', None, '24 actor names per zone'),
        (0x923C95, 'mov eax, dword ptr [r9 + r8*4 + 0xf8]', None, 'that zone\'s health'),
        (0x923C9D, 'mov edx, 0xb62b4afd', None, 'an entity attribute (inferred: an armour passive) ...'),
        (0x923CB4, 'call 0x11d9df0', None, '... looked up on the target'),
        (0x923CE6, 'cmp eax, 0x64a3fa1d', None, '... spares leg_left'),
        (0x923CED, 'cmp eax, 0x87b05ff4', None, '... and leg_right'),
        (0x923D03, 'cmp r13d, 0x26', None, '38 zones'),
        (0x923F04, 'mov eax, dword ptr [rdx + rax*4 + 0xf8]', None, 'zone health'),
        (0x923F0B, 'sub eax, dword ptr [rbp - 0x10]', None, '- damage'),
        (0x923F15, 'mov dword ptr [rdx + rcx*4 + 0xf8], r13d', None, 'stored (clamped at -constitution)'),
        (0x923F2A, 'mov eax, 2', None, 'state 2 (dead) at -constitution'),
        (0x923F36, 'setle al', None, 'state 1 at or below 0'),
        (0x923F39, 'movss xmm8, dword ptr [rdi + 0x300]', None, 'the zone\'s affects_main_health'),
    ],
    'routing': [
        (0x925AF7, 'test byte ptr [rdx + 0x14], 1', None, 'the target is owned by this machine ...'),
        (0x925B1C, 'call 0x6b2a90', None, '... update the synced (replicated) health'),
        (0x925B71, 'call 0xbf2f50', None, 'otherwise send it to the owner'),
    ],
    'zoneState': [
        (0x921F00, 'cmp dword ptr [rax], edi', None, 'the zone named ...'),
        (0x921F4C, 'mov rax, qword ptr [rax + r8*8 + 0x20]', None, 'record +0x20: 2 bits per zone'),
        (0x921F51, 'shr rax, cl', None, ''),
        (0x921F54, 'and al, 3', None, ''),
        (0x921F56, 'cmp al, 2', None, 'state 2: the limb is injured (dead zone)'),
        (0x1820418, 'cmp eax, 0x1880288e', None, 'injury HUD: arm_left'),
        (0x182041F, 'cmp eax, 0x64a3fa1d', None, 'leg_left'),
        (0x1820426, 'cmp eax, 0x87b05ff4', None, 'leg_right'),
        (0x182042D, 'cmp eax, 0xaa1db0b0', None, 'body'),
        (0x1820434, 'cmp eax, 0xb6f2baf5', None, 'arm_right'),
        (0x18204B8, 'mov rdx, qword ptr [rcx + r8*8 + 0x20]', None, 'the zone state'),
        (0x18204C3, 'and edx, 3', None, ''),
        (0x18204D5, 'cmp edx, 1', None, 'shown injured from state 1'),
    ],
    'vg70': [
        (0x7537AE, 'cmp r15d, 7', None, 'weapon fire: fire mode 7 ...'),
        (0x7537B4, 'mov eax, dword ptr [r13 + 0x3b0]', None, '... plays WeaponDataComponentData +0x3B0'),
        (0x7537C4, 'cmovne edi, eax', None, 'instead of +0x3AC'),
        (0x7537FB, 'call 0x7caf40', None, 'play ability'),
        (0x1150D4D, 'call 0x109e6c0', None, 'ability dispatcher entry 49 (AbilityId 50)'),
        (0x109E719, 'test byte ptr [rax + 0x14], 1', None, 'the wielder is owned by this machine'),
        (0x109E82C, 'cmp eax, 0x15', None, 'above 21 (inferred: rounds in the volley)'),
        (0x109E849, 'mov r8d, 0x1620b2ce', None, 'actor r_shoulder (an arm_right actor)'),
        (0x109E852, 'call 0x11adf50', None, 'ability self-damage'),
        (0x11ADF5F, 'mov esi, r8d', None, 'esi = actor name'),
        (0x11ADF71, 'call 0x5896f0', None, 'the weapon\'s wielder'),
        (0x11AE087, 'call 0xfd98c0', None, 'the wielder\'s unit'),
        (0x11AE08C, 'mov rdx, qword ptr [rip + {rip}]', G_UNIT_API, 'the engine unit API'),
        (0x11AE09D, 'mov rax, qword ptr [rdx + 0x10]', None, 'slot +0x10: actor by name'),
        (0x11AE0A1, 'mov edx, esi', None, '(unit, actor name, null)'),
        (0x11AE0A3, 'call rax', None, ''),
        (0x11AE0AB, 'mov r14d, eax', None, 'the actor handle'),
        (0x11AE117, 'mov eax, dword ptr [rip + {rip}]', ZERO_VECTOR + 8, 'argument 15 vector z'),
        (0x11AE11D, 'lea r8, [rsp + 0xa0]', None, 'argument 15 vector'),
        (0x11AE125, 'mov edx, dword ptr [r15 + 0x10]', None, 'the ability owner\'s GOID'),
        (0x11AE129, 'mov r9d, ebx', None, 'target = the wielder'),
        (0x11AE12C, 'movsd xmm0, qword ptr [rip + {rip}]', ZERO_VECTOR, 'argument 15 vector x, y'),
        (0x11AE13B, 'mov eax, dword ptr [rip + {rip}]', DOWN_VECTOR + 8, 'argument 14 vector z'),
        (0x11AE151, 'movsd xmm0, qword ptr [rip + {rip}]', DOWN_VECTOR, 'argument 14 vector x, y'),
        (0x11AE162, 'movss xmm0, dword ptr [rip + {rip}]', ONE, 'argument 19'),
        (0x11AE16A, 'movss dword ptr [rsp + 0x90], xmm0', None, 'argument 19 = 1.0'),
        (0x11AE176, 'mov dword ptr [rsp + 0x88], 0', None, 'argument 18 = 0'),
        (0x11AE181, 'mov dword ptr [rsp + 0x80], 9', None, 'argument 17 = 9'),
        (0x11AE18C, 'mov dword ptr [rsp + 0x78], r14d', None, 'argument 16 = the actor handle'),
        (0x11AE191, 'mov qword ptr [rsp + 0x70], r8', None, 'argument 15 = &vector'),
        (0x11AE19E, 'mov qword ptr [rsp + 0x68], r8', None, 'argument 14 = &vector'),
        (0x11AE1A3, 'xor r8d, r8d', None, 'argument 3 (element) = 0'),
        (0x11AE1A6, 'movss dword ptr [rsp + 0x60], xmm0', None, 'argument 13 = 0.0'),
        (0x11AE1AC, 'movss dword ptr [rsp + 0x58], xmm0', None, 'argument 12 = 0.0'),
        (0x11AE1B2, 'movss dword ptr [rsp + 0x50], xmm0', None, 'argument 11 = 0.0'),
        (0x11AE1C8, 'mov rax, qword ptr [rcx + rax + 0x38]', None, 'the target\'s record +0x38 (its creditor)'),
        (0x11AE1CD, 'mov qword ptr [rsp + 0x40], rax', None, 'argument 9 = that creditor'),
        (0x11AE1D2, 'mov dword ptr [rsp + 0x38], edx', None, 'argument 8 = owner GOID'),
        (0x11AE1D6, 'mov dword ptr [rsp + 0x30], edx', None, 'argument 7 = dealer GOID'),
        (0x11AE1DA, 'lea edx, [r8 + 6]', None, 'argument 2 (kind) = 6 Ability'),
        (0x11AE1DE, 'mov byte ptr [rsp + 0x28], 1', None, 'argument 6 = 1'),
        (0x11AE1E3, 'mov dword ptr [rsp + 0x20], 0xf', None, 'argument 5 (damage) = 15'),
        (0x11AE1EB, 'call 0x129f910', None, 'QueueDamage'),
    ],
    'warp': [
        (0x547563, 'mov edi, dword ptr [rbx + 0x14]', None, 'add instance: an owned instance goes to [0, +0x14)'),
        (0x54757F, 'mov dword ptr [rbx + 0x14], eax', None, 'owned count + 1'),
        (0x88AD63, 'cmp dword ptr [rdx + 0x14], eax', None, 'the warp state loop runs over owned instances ...'),
        (0x88BD7C, 'cmp eax, dword ptr [rdx + 0x14]', None, '... only'),
        (0x88B980, 'call 0x88dcc0', None, 'an above-safe-heat warp injures the wearer'),
        (0x88DE07, 'mov r12, qword ptr [rip + {rip}]', G_HEALTH, 'the health manager'),
        (0x88DE0E, 'lea rsi, [r15 + 0xa0]', None, 'HeatInjuryInfo[12] at DisplacementComponentData +0xA0'),
        (0x88DE30, 'mov r8d, dword ptr [rsi]', None, 'entry +0: limb actor name'),
        (0x88DE6B, 'add rsi, 0x18', None, 'stride 24'),
        (0x88DE6F, 'cmp edi, 0xc', None, '12 entries'),
        (0x88DF21, 'mov ecx, dword ptr [r15 + rsi*8 + 0xa0]', None, 'the picked limb actor name'),
        (0x88DF4C, 'lea r8d, [r9 + 7]', None, 'kind 7 Flat'),
        (0x88DF6A, 'mov dword ptr [rsp + 0x60], ecx', None, 'is ApplyDamage argument 13'),
        (0x88DFAA, 'call 0x9235f0', None, 'ApplyDamage'),
    ],
}

EXE_PROOFS = {
    'unitActor': [
        (UNIT_ACTOR, 'mov qword ptr [rsp + 0x20], rbp', None, 'Unit actor by name (unit, name, u32 *index or null)'),
        (0x799DE5, 'push rsi', None, ''),
        (0x799DE6, 'sub rsp, 0x80', None, ''),
        (0x799DED, 'mov rsi, r8', None, 'optional index out'),
        (0x799DF0, 'mov ebp, edx', None, 'ebp = the actor name'),
        (0x799E13, 'mov edx, 1', None, 'the unit\'s actor list'),
        (0x799E20, 'call 0x7e1c20', None, ''),
        (0x799E40, 'mov ebx, dword ptr [r14 + r11*4]', None, 'each actor handle'),
        (0x799E4B, 'call 0x7951b0', None, 'handle -> actor (generation checked)'),
        (0x799E55, 'cmp dword ptr [rax + 0x18], ebp', None, 'actor +0x18: its name'),
        (0x799E58, 'je 0x799e90', None, ''),
        (0x799E62, 'mov eax, 0xffffffff', None, 'none: -1'),
        (0x799E98, 'mov eax, ebx', None, 'found: the handle'),
    ],
    'actorApi': [
        (ACTOR_VALID, 'sub rsp, 0x28', None, 'actor API +0x18: the handle names a live actor'),
        (0x7972F4, 'call 0x7951b0', None, ''),
        (0x7972FE, 'setne cl', None, ''),
        (ACTOR_NAME, 'sub rsp, 0x28', None, 'actor API +0x78: the actor\'s name'),
        (0x799CE4, 'call 0x7951b0', None, ''),
        (0x799CF3, 'mov eax, dword ptr [rax + 0x18]', None, 'actor +0x18'),
    ],
}


def prologue(image, start, count):
    at, asm = start, []
    for _ in range(count):
        insn = image.insn(at)
        asm.append(insn.mnemonic + (' ' + insn.op_str if insn.op_str else ''))
        at += insn.size
    return image.data[start:at].hex(), asm


# ------------------------------------------------------------------------------------------------ entity data
def entity_evidence():
    import research_entity_authoring as entity_research
    native = entity_research.Native()
    resource = '0x%016X' % AVATAR_TYPE
    component = native.component(resource, 'HealthComponentData')
    raw = native.record('HealthComponentData', component['record_index'])
    if len(raw) != 22096:
        raise ValueError('HealthComponentData layout changed')
    zones = []
    for index in range(ZONES):
        at = ZONE_BASE + index * ZONE_STRIDE
        name = struct.unpack_from('<I', raw, at + 96)[0]
        if not name:
            continue
        actors = [value for value in struct.unpack_from('<24I', raw, at + 456) if value]
        zones.append({'index': index, 'name': native.thin_name(name), 'nameHash': name,
            'health': struct.unpack_from('<i', raw, at + 232)[0], 'constitution': struct.unpack_from('<i', raw, at + 236)[0],
            'affectsMainHealth': round(struct.unpack_from('<f', raw, at + 248)[0], 6),
            'actors': [native.thin_name(a) or '0x%08X' % a for a in actors], 'actorHashes': actors})
    owners = native.owners('HealthComponentData').get(component['record_index'], [])
    by_actor = {}
    for zone in zones:
        for name, value in zip(zone['actors'], zone['actorHashes']):
            by_actor[name] = (zone, value)
    limbs = []
    for limb in LIMBS:
        zone, value = by_actor[limb]
        limbs.append({'limb': limb, 'actor': value, 'zone': zone['name'], 'zoneIndex': zone['index'],
            'zoneHealth': zone['health'], 'affectsMainHealth': zone['affectsMainHealth']})
    # The Warp Pack's HeatInjuryInfo limbs (the game's own injury table).
    coverage =json.loads((ROOT / 'research/equipment-coverage-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    warp = [{'limb': e['limb'], 'actor': e['limbHash'], 'damage': e['damage'], 'status': e['statusType'],
        'zone': by_actor[e['limb']][0]['name'] if e['limb'] in by_actor else None}
        for e in coverage['warpPack']['injuries']['entries'] if not e['unused']]
    # WeaponDataComponentData +0x98 (FireMode) and +0x3B0 / +0x3AC (AbilityId): who sets the fire-mode-7 ability.
    _, _, _, _, count = native.table('WeaponDataComponentData')
    weapon_owners = native.owners('WeaponDataComponentData')
    mode7 = []
    for index in range(count):
        row = native.record('WeaponDataComponentData', index)
        ability = struct.unpack_from('<I', row, 0x3B0)[0]
        if ability:
            mode7.append({'record': index, 'fireMode': struct.unpack_from('<I', row, 0x98)[0], 'modeAbility': ability,
                'fireAbility': struct.unpack_from('<I', row, 0x3AC)[0],
                'owners': [native.path(r) for r in weapon_owners.get(index, [])]})
    return {'avatar': {'type': '%016X' % AVATAR_TYPE, 'path': native.path(AVATAR_TYPE),
            'healthRecord': component['record_index'], 'owners': len(owners),
            'mainHealth': struct.unpack_from('<i', raw, 0)[0], 'zones': zones},
        'limbs': limbs, 'warpInjuries': warp, 'fireMode7Abilities': mode7}


# ------------------------------------------------------------------------------------------------ snapshots
def local_avatar(mem):
    """The local player's avatar entity through the player list, or None."""
    session = mem.ptr(mem.game + base.G_SESSION)
    local_peer = mem.u64(session + 0xB398)
    players = mem.ptr(mem.game + base.G_PLAYER)
    em = mem.ptr(mem.game + base.G_ENTITY_MANAGER)
    for i in range(mem.u32(players + 0x84) or 0):
        if mem.u64(players + 0x2C8 + 0x38 * i) != local_peer:
            continue
        net = mem.u32(players + 0x3A8 + 0x20 * i)
        slot = None if net == 0x7FFF else base.map_lookup(mem, em + 0xF22EC8, net)
        return None if slot is None else mem.u32(em + 0xF32F20 + 24 * slot)
    return None


def health_lookup(mem, manager, entity):
    """entity -> record index through the health manager's hash (0x4A4410)."""
    buckets, capacity = mem.ptr(manager + 0x1030), mem.u32(manager + 0x1038)
    empty, multiplier = mem.u32(manager + 0x103C), mem.u32(manager + 0x1040)
    raw = mem.read(buckets, capacity * 8)
    start = (entity * multiplier) & 0xFFFFFFFF
    for probe in range(capacity):
        key, value = struct.unpack_from('<II', raw, ((start + probe) & (capacity - 1)) * 8)
        if key == entity:
            return value
        if key == empty:
            return None
    return None


def actor_object(mem, handle):
    """exe 0x7951B0: an actor handle -> the actor, with its generation check; None when stale."""
    pool = mem.exe + EXE_ACTOR_POOLS + ((((handle >> 28) & 3) + ((handle >> 30) & 3) * 10) << 6)
    raw = mem.read(pool, 0x40)
    data, meta = struct.unpack_from('<Q', raw, 0)[0], struct.unpack_from('<I', raw, 0x1C)[0]
    count, mask, flags = struct.unpack_from('<III', raw, 0x24)[0], struct.unpack_from('<I', raw, 0x28)[0], \
        struct.unpack_from('<I', raw, 0x34)[0]
    index = handle & mask
    if count <= index or not flags & handle:
        return None
    stride, check, offset = meta & 0xFFFF, (meta >> 16) & 0xFF, meta >> 24
    if mem.u32(data + stride * index + check) != handle:
        return None
    return data + stride * index + offset


def unit_actors(mem, unit):
    """exe 0x799DE0 emulated: the unit's actor handles (0x7E1C20, list kind 0) and each actor's name."""
    record = mem.ptr(mem.exe + EXE_UNIT_RECORDS) + (unit & 0x3FFFFF) * 24
    raw = mem.read(record, 24)
    first, packed = struct.unpack_from('<II', raw, 0)
    if not packed & 0x40000000 or first & 0x3FFFFFFF != unit:
        return None
    count = packed & 0x7F
    listing = record + 8 if packed & 0x80000000 else struct.unpack_from('<Q', raw, 8)[0]
    out = {}
    for handle in struct.unpack('<%dI' % count, mem.read(listing, 4 * count)):
        actor = None if handle == 0xFFFFFFFF else actor_object(mem, handle)
        if actor:
            out.setdefault(mem.u32(actor + 0x18), handle)
    return out


def observe(name, limbs):
    mem = base.Mem(name)
    out = {'snapshot': name}
    system = mem.ptr(mem.game + G_DAMAGE)
    out['damageQueueCounts'] = [mem.u32(system + QUEUE_COUNT + 4 * k) for k in range(8)]
    unit_api, actor_api = mem.ptr(mem.game + G_UNIT_API), mem.ptr(mem.game + G_ACTOR_API)
    out['engineApis'] = {
        'unitApiTable': unit_api == mem.exe + UNIT_API_TABLE,
        'unitActorSlot': mem.u64(unit_api + UNIT_ACTOR_SLOT) == mem.exe + UNIT_ACTOR,
        'actorApiTable': actor_api == mem.exe + ACTOR_API_TABLE,
        'actorValidSlot': mem.u64(actor_api + ACTOR_VALID_SLOT) == mem.exe + ACTOR_VALID,
        'actorNameSlot': mem.u64(actor_api + ACTOR_NAME_SLOT) == mem.exe + ACTOR_NAME}
    out['constants'] = {'zeroVector': list(struct.unpack('<3f', mem.read(mem.game + ZERO_VECTOR, 12))),
        'downVector': list(struct.unpack('<3f', mem.read(mem.game + DOWN_VECTOR, 12))),
        'one': struct.unpack('<f', mem.read(mem.game + ONE, 4))[0]}
    displacement = mem.ptr(mem.game + G_DISPLACEMENT)
    out['displacement'] = displacement and {'live': mem.u32(displacement + 0x10), 'owned': mem.u32(displacement + 0x14)}
    manager = mem.ptr(mem.game + G_HEALTH)
    avatar = local_avatar(mem)
    out['localAvatar'] = None
    if avatar is not None:
        index = health_lookup(mem, manager, avatar)
        descriptor = base.descriptor(mem, mem.ptr(mem.ptr(manager + 0x1048) + 8 * index))
        record = mem.read(mem.ptr(manager + 0x1058) + index * RECORD_STRIDE, RECORD_STRIDE)
        ext = mem.read(mem.ptr(manager + 0x1060) + index * EXT_STRIDE, EXT_STRIDE)
        states = struct.unpack_from('<Q', record, 0x20)[0]
        mask = struct.unpack_from('<I', ext, 0x10)[0]
        actors = unit_actors(mem, descriptor['unit']) or {}
        out['localAvatar'] = {'entity': avatar, 'type': descriptor['type'], 'owned': descriptor['authority'],
            'networkId': descriptor['networkId'], 'unit': descriptor['unit'],
            'life': struct.unpack_from('<I', record, 0x19C)[0], 'health': struct.unpack_from('<i', record, 0x14)[0],
            'maxHealth': struct.unpack_from('<i', ext, 0x14)[0],
            'zoneHealth': list(struct.unpack_from('<6i', record, 0xF8)),
            'zoneStates': [(states >> (2 * z)) & 3 for z in range(6)],
            'acceptance': {DAMAGE_SOURCE_KINDS[k]: (mask >> (2 * k)) & 3 for k in range(10)},
            'creditorZero': struct.unpack_from('<Q', record, 0x38)[0] == 0,
            'unitActors': len(actors),
            'limbActors': {item['limb']: ('0x%08X' % actors[item['actor']]) if item['actor'] in actors else None
                for item in limbs}}
    mem.close()
    return out


def api_slots(name):
    mem = base.Mem(name)
    unit_api, actor_api = mem.ptr(mem.game + G_UNIT_API), mem.ptr(mem.game + G_ACTOR_API)
    ok = (unit_api == mem.exe + UNIT_API_TABLE and mem.u64(unit_api + UNIT_ACTOR_SLOT) == mem.exe + UNIT_ACTOR
        and actor_api == mem.exe + ACTOR_API_TABLE and mem.u64(actor_api + ACTOR_VALID_SLOT) == mem.exe + ACTOR_VALID
        and mem.u64(actor_api + ACTOR_NAME_SLOT) == mem.exe + ACTOR_NAME)
    mem.close()
    return ok


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA or snap.executable_sha256.upper() != base.PROFILE_EXE_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    game_base, data = snap.module_image('game.dll')
    exe_name = next(k for k in snap.modules if k.endswith('.exe'))
    exe_base, exe_data = snap.module_image(exe_name)
    snap.close()
    image = base.Image(data, game_base, base.TEXT)
    exe = base.Image(exe_data, exe_base, base.EXE_TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in GAME_PROOFS.items()}
    exe_proofs = {group: [exe.prove(*row) for row in rows] for group, rows in EXE_PROOFS.items()}
    # Ability dispatch: AbilityId 50 is entry 49 of the dispatcher's table (0x11509E0: id - 1 <= 0xB32).
    dispatcher = image.prove(0x11509E9, 'cmp edx, 0xb32', None, 'ability dispatcher: id - 1 <= 0xB32')
    entry = struct.unpack_from('<I', data, 0x115C784 + 4 * 49)[0]
    if entry != 0x1150D4A:
        raise ValueError('ability 50 no longer dispatches to 0x1150D4A')
    proofs['vg70'].insert(0, dispatcher)
    queue_prologue, queue_asm = prologue(image, QUEUE_DAMAGE, 14)
    actor_prologue, actor_asm = prologue(exe, UNIT_ACTOR, 5)
    rdata_down = list(struct.unpack_from('<3f', data, DOWN_VECTOR))
    rdata_one = struct.unpack_from('<f', data, ONE)[0]
    if rdata_down != [0.0, 0.0, -1.0] or rdata_one != 1.0:
        raise ValueError('the VG-70 call constants changed')
    entity = entity_evidence()
    zones = {zone['name']: zone for zone in entity['avatar']['zones']}
    if [z['name'] for z in entity['avatar']['zones']] != ['head', 'body', 'arm_left', 'arm_right', 'leg_left',
            'leg_right'] or any(z['constitution'] for z in entity['avatar']['zones']):
        raise ValueError('the avatar damage zones changed')
    if 'r_shoulder' not in zones['arm_right']['actors']:
        raise ValueError('r_shoulder is no longer an arm_right actor')
    if {m['modeAbility'] for m in entity['fireMode7Abilities']} != {50} or not any(
            'volley_gun' in (o or '') for m in entity['fireMode7Abilities'] for o in m['owners']):
        raise ValueError('the VG-70 fire mode 7 ability changed')
    pins = [p for rows in proofs.values() for p in rows]
    exe_pins = [p for rows in exe_proofs.values() for p in rows]
    observations, relocation = [], {}
    for name in SNAPSHOTS:
        relocation[name] = base.verify_pins_live(name, pins, exe_pins)
        observations.append(observe(name, entity['limbs']))
    ship = {}
    for name in SHIP_SNAPSHOTS:
        relocation[name] = base.verify_pins_live(name, pins, exe_pins)
        ship[name] = api_slots(name)
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    for o in observations:
        if o['damageQueueCounts'][0] != 0 or not all(o['engineApis'].values()):
            raise ValueError('damage queue or engine API disagrees in ' + o['snapshot'])
        if o['constants']['zeroVector'] != [0.0, 0.0, 0.0]:
            raise ValueError('the VG-70 hit position constant is not zero in ' + o['snapshot'])
        a = o['localAvatar']
        if a is None:
            continue
        if not (a['owned'] and a['type'] == '%016X' % AVATAR_TYPE and a['acceptance']['Ability'] == 2
                and a['zoneHealth'] == [z['health'] for z in entity['avatar']['zones']]
                and all(a['limbActors'].values())):
            raise ValueError('the local avatar disagrees in ' + o['snapshot'])
    if not all(ship.values()):
        raise ValueError('the engine API slots differ in a ship snapshot')
    limbs = entity['limbs']
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'exe': {'sha256': base.PROFILE_EXE_SHA, 'imageSize': base.EXE_IMAGE_SIZE},
        'queueDamage': {'rva': QUEUE_DAMAGE, 'prologue': queue_prologue, 'asm': queue_asm, 'system': G_DAMAGE,
            'count': QUEUE_COUNT, 'capacity': QUEUE_CAPACITY, 'entries': QUEUE_ENTRIES, 'eventSize': EVENT_SIZE,
            'healthManager': G_HEALTH,
            'signature': 'QueueDamage(void *ignored, u32 kind, u32 element, u32 target, u32 damage, u8 a6, '
                'u32 dealer_goid, u32 owner_goid, u64 creditor, u32 a10 (unread), float a11, float a12, float a13, '
                'const float a14[3], const float a15[3], u32 actor_handle, u32 a17, u32 a18, float a19)',
            'gameTemplate': {'site': 0x11AE1EB, 'kind': KIND_ABILITY, 'element': 0, 'damage': 15, 'a6': 1,
                'dealer': 'the ability owner\'s GOID', 'owner': 'the ability owner\'s GOID',
                'creditor': 'the target\'s health record +0x38', 'a11': 0.0, 'a12': 0.0, 'a13': 0.0,
                'a14': rdata_down, 'a15': [0.0, 0.0, 0.0], 'actor': 'unit actor handle of r_shoulder', 'a17': 9,
                'a18': 0, 'a19': rdata_one},
            'runtimeTemplate': {'kind': KIND_ABILITY, 'element': 0, 'a6': 1, 'a10': 0, 'a11': 0.0, 'a12': 0.0,
                'a13': 0.0, 'a14': rdata_down, 'a15': [0.0, 0.0, 0.0], 'a17': 9, 'a18': 0, 'a19': rdata_one,
                'dealer': 'the avatar\'s own network id', 'owner': 'the avatar\'s own network id',
                'creditor': 'the avatar\'s health record +0x38 (read just before the call)',
                'actor': 'unit actor handle of the requested limb (exe 0x799DE0)',
                'deviation': 'dealer and owner name the avatar itself (a self-inflicted injury) instead of the '
                    'VG-70 weapon; the consumer applies an event whose owner is its target only on the target\'s '
                    'owner (0x12A7DC2..0x12A7DDC)'}},
        'applyDamage': {'rva': APPLY_DAMAGE, 'argument13': 'the hit actor name (the consumer passes event +0x0C '
            'turned into its name)', 'zoneActors': '+0x3D0 from the settings record per zone (stride 0x228, 24)'},
        'unitApi': {'global': G_UNIT_API, 'tableRva': UNIT_API_TABLE, 'actorSlot': UNIT_ACTOR_SLOT, 'actorRva': UNIT_ACTOR,
            'prologue': actor_prologue, 'asm': actor_asm,
            'signature': 'u32 UnitActorByName(u32 unit, u32 actor_name, u32 *index_or_null): handle or 0xFFFFFFFF'},
        'actorApi': {'global': G_ACTOR_API, 'tableRva': ACTOR_API_TABLE, 'validSlot': ACTOR_VALID_SLOT,
            'validRva': ACTOR_VALID, 'nameSlot': ACTOR_NAME_SLOT, 'nameRva': ACTOR_NAME},
        'avatar': entity['avatar'], 'limbs': limbs, 'warpInjuries': entity['warpInjuries'],
        'fireMode7Abilities': entity['fireMode7Abilities'],
        'proofs': proofs, 'exeProofs': exe_proofs, 'pinnedBytesMismatchPerSnapshot': relocation,
        'observations': observations, 'shipApiSlots': ship,
        'confidence': {
            'zoneModel': 'CONFIRMED: six avatar zones, their actors and health (entity table), the 2-bit zone '
                'states the game\'s own readers use, full-health zones in every mission snapshot.',
            'applyDamageZone': 'CONFIRMED: ApplyDamage resolves the zone by the hit actor name and lowers that '
                'zone (pinned code); the Warp Pack and the game\'s chest Bleed injury pass actor names directly.',
            'queuePath': 'CONFIRMED: QueueDamage appends to queue 0, the world update drains it, the consumer turns '
                'the actor handle into its name and calls ApplyDamage with it (pinned code).',
            'vg70SelfInjury': 'CONFIRMED (code): fire mode 7 plays AbilityId 50 (data: VG-70 Variable and the '
                'expendable machine gun), which queues 15 kind-6 damage at the wielder\'s r_shoulder actor. The '
                'trigger condition (a count above 21) is UNKNOWN in meaning; not live-observed.',
            'ownerApplies': 'STRONG: both of the game\'s self-injuries run on the machine that owns the avatar; '
                'ApplyDamage updates the replicated synced health for an owned target and sends the damage to '
                'the owner otherwise. Not live-observed on a client.',
            'limbActors': 'CONFIRMED: the avatar unit\'s actor list holds every limb actor in all three mission '
                'snapshots with an avatar (emulated exe 0x799DE0).',
            'runtimeDeviation': 'PLAUSIBLE: dealer and owner = the avatar itself; stats and telemetry attribution of '
                'the injury follow the consumer\'s ordinary rules and are not live-tested.',
            'injuredState': 'STRONG: a zone at 0 health is state 2 (dead) and the HUD shows it injured; the '
                'gameplay effects (arm sway, leg limp) are the game\'s and are not live-observed here.',
        },
        'unproven': [
            'Where ApplyDamage\'s new zone states are committed to record +0x20 (the copy is passed to 0x925F10 and '
                'to a network message; the readers are pinned).',
            'The meaning of the VG-70 trigger count (0x11C4D60 > 21) and of arguments 6, 17 and 18.',
            'Which player the consumer\'s damage statistics and telemetry credit for a self-inflicted event.',
            'What other machines show for the injured limb (the synced health properties carry the zone states; '
                'not observed live).',
            'The entity attribute 0xB62B4AFD that spares leg zones (inferred: an armour passive).',
        ],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'pins': len(pins), 'exePins': len(exe_pins), 'limbs': [l['limb'] for l in limbs],
        'avatars': [o['localAvatar'] and o['localAvatar']['limbActors'] for o in observations]}, indent=1))


if __name__ == '__main__':
    main()
