"""Helldiver avatar TYPE fields: movement speeds, stamina and the six body zones' damage values (read-only research).

Proves on build F5FEE03DCFDB, from the unpacked game.dll image and the seven retained snapshots, which members of the
two type records every Helldiver uses are read, by which code, and when:

* AvatarComponentData record 0 (852 bytes, the only owned row: avatar_helldiver 0x4D1C334D294DFA97, index row 1).
  Every live reader resolves it through 0x508DB0(entity descriptor): the avatar manager's private-copy map
  (+0x547C70, copies inline from +0x547D24, 0x354 apart; created only by entity deltas at spawn), else the type
  lookup 0x508770 (table = [entity manager + 0xF12BB8], records from +0x20). No member is copied into the avatar
  instance at creation, so a type write reaches the next read of every avatar without a private copy.
* HealthComponentData record 76 (avatar_helldiver, index row 443). The hit builder reads the zone members it copies
  into the hit event from the TYPE record (0x12A1D96 -> 0x507430); ApplyDamage and the explosion factor read the
  override-aware record (0x507920); zone health is copied into the health instance at spawn (0x91D580).

The snapshots prove the record identities (index rows, unique owners, bytes equal to the pinned datalibrary, the
loaded entity-file allocation), the avatar instances and their private copies, stamina state and zone health.
Nothing here writes. Requires the research-only package capstone.

Output: research/avatar-fields-F5FEE03DCFDB.json (summary: research/docs/avatar-fields-F5FEE03DCFDB.md).
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
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402
import snapshot_image  # noqa: E402
from migration import build_view  # noqa: E402
from scan import tables  # noqa: E402

OUTPUT = ROOT / 'research/avatar-fields-F5FEE03DCFDB.json'
HELLDIVER = 0x4D1C334D294DFA97
G_ENTITY_MANAGER, G_AVATAR, G_HEALTH, G_CORPSE, G_STATUS = 0x346BF98, 0x3326D20, 0x3326688, 0x3326920, 0x3326620
TABLE_BASE = 0xF12478            # entity manager + 0xF12478 + 8 x component index = the loaded table
AVATAR_INDEX, HEALTH_INDEX = 0xE8, 0xE0
AVATAR_SIZE, AVATAR_ROWS = 0x354, 2
HEALTH_SIZE, HEALTH_ROWS, HEALTH_RECORD = 0x5650, 1002, 76
ZONE_BASE, ZONE_STRIDE, DEFAULT_ZONE = 0x208, 0x228, 0x40
# Avatar manager layout (all from the pinned code).
AV_DESCRIPTORS, AV_TOTAL, AV_OWNED, AV_HASH = 0x110, 0x6C, 0x70, 0xF8
AV_COPY_MAP, AV_COPIES = 0x547C70, 0x547D24
AV_STAMINA, AV_STAMINA_STRIDE = 0x547854, 0x78
AV_SIM, AV_SIM_STRIDE, AV_DELAY, AV_COST = 0x53D8B0, 0x1238, 0x53E8FC, 0x53E900
DAMAGE_MULTIPLIER = ['None', 'Critical', 'Normal', 'Reduced', 'Symbolic']
MULTIPLIER_TABLE = 0x21CF898
FLT_MAX = 3.4028234663852886e+38
STATUS = {0x0F: 'sand', 0x10: 'mud', 0x11: 'snow', 0x1A: 'stim_stamina', 0x3B: 'death_march'}

R = '{rip}'
PROOFS = {
    'avatarTypeLookup_0x508770': [
        (0x508775, 'mov rax, qword ptr [rip + {rip}]', G_ENTITY_MANAGER, 'entity manager'),
        (0x50877F, 'and r8d, 1', None, 'home row = resource mod 2 (2 index rows)'),
        (0x508786, 'mov r10, qword ptr [rax + 0xf12bb8]', None, 'AvatarComponentData table = EM + 0xF12478 + 8 x 0xE8'),
        (0x5087BB, 'cmp r9d, 2', None, 'probe at most 2 rows'),
        (0x5087C9, 'mov eax, dword ptr [rax + 8]', None, 'record index of the matching row'),
        (0x5087CC, 'imul rcx, rax, 0x354', None, 'record index x 852'),
        (0x5087D3, 'lea rax, [r10 + 0x20]', None, 'records follow the 2 x 16-byte index rows'),
    ],
    'avatarResolver_0x508DB0': [
        (0x508DC3, 'mov eax, dword ptr [rcx + 8]', None, 'entity id of the descriptor'),
        (0x508DD2, 'mov r11, qword ptr [rip + {rip}]', G_AVATAR, 'avatar component manager'),
        (0x508DEB, 'mov r9d, dword ptr [r11 + 0x547c78]', None, 'private-copy map capacity'),
        (0x508E0A, 'mov rdi, qword ptr [r11 + 0x547c70]', None, 'private-copy map slots (entity id -> copy index)'),
        (0x508E62, 'imul rcx, rax, 0x354', None, 'copy index x 852'),
        (0x508E69, 'lea rax, [r11 + 0x547d24]', None, 'private copies inline in the manager'),
        (0x508E7F, 'jmp 0x508770', None, 'no private copy -> the TYPE record'),
    ],
    'avatarDeltaCopies': [
        (0x5757E8, 'call 0x508770', None, 'spawn-time entity-delta copy (0x5740B0, called by create 0x581320)'),
        (0x5757F9, 'mov rax, qword ptr [r8 + 0xf12bb8]', None, 'no row -> the table'),
        (0x575800, 'add rax, 0x374', None, '+0x20 + 0x354 = record 1, the unowned default record'),
        (0x83C502, 'call 0x508770', None, 'second delta-copy creator 0x83C420'),
        (0x83C51A, 'add rax, 0x374', None, 'same default-record fallback'),
    ],
    'avatarInstanceCreate': [
        (0x53F3DA, 'cmp byte ptr [rdx], r15b', None, 'queue handler 0x53F3A0: simulated-here flag'),
        (0x53F3E3, 'mov ebp, dword ptr [rsi + 0x70]', None, 'simulated-here instances take the first +0x70 slots'),
        (0x53F3FF, 'mov dword ptr [rsi + 0x70], eax', None, 'simulated count + 1'),
        (0x53F43C, 'call 0x208aaa0', None, 'zero the 0x1238-byte local simulation block (no settings copy)'),
        (0x53F4FA, 'mov qword ptr [rsi + rdi*8 + 0x110], r14', None, 'instance descriptor'),
        (0x83A880, 'mov dword ptr [rbx + rbp + 0x547854], 0x3f800000', None,
            'synced create 0x83A6F0: stamina = 1.0 (property 0x7870BB31)'),
    ],
    'avatarUpdate_0x829E90': [
        (0x5731CA, 'call 0x829e90', None, 'world update 0x571250 calls the avatar update with dt (xmm1)'),
        (0x82A010, 'cmp dword ptr [r13 + 0x70], edi', None, 'loop over the simulated-here avatars only'),
        (0x82A0A0, 'mov r14, qword ptr [r13 + rbx*8 + 0x110]', None, 'descriptor of avatar rbx'),
        (0x82A0E8, 'call 0x508db0', None, 'settings of this avatar, every frame'),
        (0x82A10A, 'mov qword ptr [rbp - 8], rax', None, 'kept for the stamina regen below'),
        (0x82A275, 'lea r8d, [r15 + 0x1a]', None, 'status 0x1A stim_stamina'),
        (0x82A279, 'call 0x69b1f0', None, 'has status -> regen without the delay'),
        (0x82A369, 'movss xmm0, dword ptr [r12 + 0x104c]', None, 'regen delay timer (manager +0x53E8FC + i x 0x1238)'),
        (0x82A37D, 'subss xmm0, xmm10', None, 'timer -= dt; no regen while it is positive'),
        (0x82A2A1, 'movss xmm0, dword ptr [r12 + 0x1050]', None, 'per-avatar regen multiplier'),
        (0x82A2B9, 'mulss xmm0, dword ptr [rip + {rip}]', 0x32FDB08, 'x 1.3 while modifier 2 is active (0x856D40)'),
        (0x82A33F, 'movss xmm0, dword ptr [rax + 0x44]', None, 'prone: stamina_recover_time_prone'),
        (0x82A3EA, 'movss xmm0, dword ptr [rax + 0x40]', None, 'crouched: stamina_recover_time_crouch'),
        (0x82A3F1, 'movss xmm0, dword ptr [rax + 0x3c]', None, 'standing: stamina_recover_time_stand'),
        (0x82A403, 'divss xmm2, xmm0', None, 'multiplier / recover time'),
        (0x82A411, 'mulss xmm2, xmm10', None, 'x dt'),
        (0x82A416, 'addss xmm2, dword ptr [rax + r13 + 0x547854]', None, '+ stamina (0..1)'),
        (0x82A420, 'minss xmm2, xmm11', None, 'capped at 1.0'),
        (0x82A425, 'movss dword ptr [r8], xmm2', None, 'stamina stored'),
        (0x82A4B1, 'call 0xa6c700', None, 'movement speed of this avatar, every frame'),
    ],
    'moveSpeed_0xA6C700': [
        (0xA6C74D, 'mov rsi, qword ptr [rip + {rip}]', G_AVATAR, 'avatar manager'),
        (0xA6CA4E, 'call 0x508db0', None, 'settings of this avatar'),
        (0xA6CA66, 'mov rbp, rax', None, 'rbp = settings record'),
        (0xA6CBDD, 'mulss xmm0, dword ptr [rbp + 4]', None, '+4: direction factor, blends 1 -> 0.75'),
        (0xA6CC21, 'movss xmm7, dword ptr [rbp + 0x30]', None, 'swimming (state bit 95): swim'),
        (0xA6CC91, 'movss xmm7, dword ptr [rbp + 0x28]', None, 'crouched + sprint action: crouch_sprint'),
        (0xA6CCAE, 'movss xmm7, dword ptr [rbp + 0x24]', None, 'crouched + jog action: crouch_jog'),
        (0xA6CCCB, 'mulss xmm7, dword ptr [rbp + 0x1c]', None, 'crouched + aim: crouch_aim x direction factor'),
        (0xA6CCD5, 'mulss xmm7, dword ptr [rbp + 0x20]', None, 'crouched: crouch_walk x direction factor'),
        (0xA6CD29, 'mulss xmm7, dword ptr [rbp + 0x2c]', None, 'prone (state bit 78): prone x direction factor'),
        (0xA6CD4D, 'comiss xmm6, dword ptr [rax + rsi + 0x547854]', None, 'sprint: stamina > 0?'),
        (0xA6CD61, 'mov r8d, 0x3b', None, 'status 0x3B death_march'),
        (0xA6CD69, 'call 0x69b1f0', None, 'empty stamina without Death March -> exerted'),
        (0xA6CD72, 'movss xmm7, dword ptr [rbp + 0x18]', None, 'sprint at empty stamina: sprint_exerted'),
        (0xA6CD79, 'movss xmm7, dword ptr [rbp + 0x14]', None, 'sprint'),
        (0xA6CD93, 'movss xmm7, dword ptr [rbp + 0x10]', None, 'jog action: jog'),
        (0xA6CDEB, 'mulss xmm7, dword ptr [rbp + 8]', None, 'state bit 82: aim x direction factor'),
        (0xA6CDF2, 'mulss xmm7, dword ptr [rbp + 0xc]', None, 'otherwise: walk x direction factor'),
        (0xA6CEB9, 'movss xmm2, dword ptr [rbp + 0xb4]', None, 'jog/sprint slope slow-down (uphill start angle)'),
        (0xA6CEC3, 'movss xmm2, dword ptr [rbp + 0xc0]', None, '(downhill start angle)'),
        (0xA6D0BF, 'movss xmm0, dword ptr [r13 + 8]', None, 'external cap (if >= 0)'),
        (0xA6D0DE, 'movss xmm6, dword ptr [rip + {rip}]', 0x23C7554, 'hard cap 10.0 m/s'),
        (0xA6D0E6, 'minss xmm6, xmm7', None, 'target = min(10, speed); negative -> 0'),
        (0xA6D0FA, 'movss dword ptr [r13 + 4], xmm6', None, 'target speed of this frame'),
    ],
    'staminaDrain_0x833930': [
        (0x8339D1, 'test byte ptr [rcx + 0x14], 1', None, 'only an avatar owned here'),
        (0x8339F0, 'call 0x508db0', None, 'settings of this avatar, every call'),
        (0x833A0E, 'movss xmm0, dword ptr [rip + {rip}]', 0x32FDB08, 'divisor 1.3 while modifier 2 is active'),
        (0x833A1B, 'movss xmm2, dword ptr [rbx + rbp + 0x53e900]', None, 'per-avatar stamina cost multiplier'),
        (0x833A29, 'divss xmm2, dword ptr [r14 + 0x34]', None, '/ sprint_stamina_decay_duration'),
        (0x833A49, 'mulss xmm2, xmm6', None, 'x dt'),
        (0x833A54, 'subss xmm1, xmm2', None, 'stamina -= ...'),
        (0x833A58, 'maxss xmm1, xmm0', None, 'not below 0'),
        (0x833A71, 'mov eax, dword ptr [r14 + 0x48]', None, 'stamina_recover_delay'),
        (0x833A7A, 'mov dword ptr [rbx + rbp + 0x53e8fc], eax', None, '-> regen delay timer'),
        (0xA8B360, 'call 0x833930', None, 'sprint state update 0xA8AE60'),
        (0xA717D9, 'call 0x833930', None, 'slide movement update 0xA71390 (reads ActionSlideMovementInfo)'),
        (0xA62E6E, 'lea r8d, [r9 + 0x11]', None, 'jog update 0xA62BA0: snow / mud / sand terrain status ...'),
        (0xA62EC5, 'call 0x833930', None, '... drains at the sprint rate'),
    ],
    'staminaCosts': [
        (0xA642E6, 'call 0x508db0', None, 'jump 0xA63F20'),
        (0xA64627, 'movss xmm0, dword ptr [rax + 0x53e900]', None, 'cost multiplier'),
        (0xA6462F, 'mulss xmm0, dword ptr [r15 + 0x4c]', None, 'x stamina_cost_jump'),
        (0xA6463A, 'subss xmm1, xmm0', None, 'stamina -= cost'),
        (0xA50BB4, 'call 0x508db0', None, 'dive 0xA50890'),
        (0xA50DB3, 'mulss xmm0, dword ptr [r13 + 0x50]', None, 'x stamina_cost_dodge'),
        (0xA50DC3, 'subss xmm1, xmm0', None, 'stamina -= cost'),
        (0xA72476, 'call 0x508db0', None, 'slide start 0xA722E0'),
        (0xA72641, 'mulss xmm0, dword ptr [r13 + 0x5c]', None, 'x stamina_cost_slide'),
        (0xA7265C, 'subss xmm1, xmm0', None, 'stamina -= cost'),
        (0xA9B393, 'call 0x508db0', None, 'climb 0xA9AFD0'),
        (0xA9B3DE, 'mulss xmm0, dword ptr [r12 + 0x58]', None, 'x stamina_cost_climb (vanilla 0)'),
    ],
    'healthTypeLookup_0x507430': [
        (0x507435, 'mov rax, qword ptr [rip + {rip}]', G_ENTITY_MANAGER, 'entity manager'),
        (0x50743F, 'mov r10, qword ptr [rax + 0xf12b78]', None, 'HealthComponentData table = EM + 0xF12478 + 8 x 0xE0'),
        (0x507463, 'imul eax, eax, 0x3ea', None, '1002 index rows'),
        (0x5074B1, 'imul rax, rcx, 0x5650', None, 'record index x 22096'),
        (0x5074B8, 'add rax, 0x3ea0', None, 'records follow the index rows'),
        (0x50797A, 'mov rdi, qword ptr [r11 + 0x1070]', None, '0x507920: health private-copy map, else 0x507430'),
    ],
    'hitBuilder_0x12A15E0': [
        (0x12A1D96, 'call 0x507430', None, 'TYPE record by resource (private copies ignored)'),
        (0x12A1E61, 'call 0x922060', None, 'zone of the hit actor'),
        (0x12A1E78, 'mov ecx, dword ptr [rax + 0xcc]', None, 'zone durable fraction -> event +0x4C (per hit)'),
        (0x12A227F, 'cmp dword ptr [rsp + 0x80], 2', None, 'damage-over-time hit?'),
        (0x12A22A7, 'mov ecx, dword ptr [r12 + 0xc4]', None, 'zone damage_multiplier ...'),
        (0x12A22AF, 'mov dword ptr [r14 + 0x6c], ecx', None, '... -> event +0x6C (per hit)'),
        (0x12A22B5, 'mov eax, dword ptr [r12 + 0xc8]', None, 'DoT hit: damage_multiplier_dps ...'),
        (0x12A22BF, 'cmovne ecx, eax', None, '... replaces it when not None (0)'),
    ],
    'damageByKind_0x129DC30': [
        (0x129DC5E, 'mov ecx, dword ptr [rdx + rax*4 + 0x129dd08]', None,
            'kind 0/1 -> 0x129C9F0, 2 -> 0x129CD40, 3 -> 0x129CF10, 4 -> 0x129D180, 5 -> 0x129D9A0, 6 -> 0x129D660'),
        (0x129CB80, 'movsxd rax, dword ptr [rbx + 0x6c]', None, 'kind 0/1 (projectile): event +0x6C'),
        (0x129CB9A, 'mulss xmm1, dword ptr [rcx + rax*4]', None, 'x [0, 1.5, 1, 0.75, 0.25][multiplier]'),
        (0x129CE6A, 'movsxd rax, dword ptr [rbx + 0x6c]', None, 'kind 2'),
        (0x129D03E, 'movsxd rax, dword ptr [rbx + 0x6c]', None, 'kind 3'),
        (0x129D3F9, 'movsxd rax, dword ptr [rdi + 0x6c]', None, 'kind 4 (explosion)'),
        (0x129D422, 'mulss xmm0, dword ptr [rcx + rax*4]', None, 'kind 4 multiplier'),
        (0x129D7CA, 'movsxd rax, dword ptr [rbx + 0x6c]', None, 'kind 6'),
        (0x129D9CD, 'movsxd rbx, dword ptr [r8 + 0x6c]', None, 'kind 5'),
        (0x129DBBC, 'mulss xmm1, dword ptr [r12 + rbx*4]', None, 'kind 5 multiplier'),
    ],
    'explosionZone_0x129D180': [
        (0x129D2C2, 'call 0x507920', None, 'override-aware health record'),
        (0x129D2DE, 'mov r8, qword ptr [rip + {rip}]', G_CORPSE, 'corpses skip the explosive percentage'),
        (0x129D346, 'call 0x921a80', None, 'zone index by name'),
        (0x129D36C, 'cmp byte ptr [rax + 0x143], sil', None, 'zone affected_by_explosions?'),
        (0x129D37B, 'cmovne rdx, rax', None, 'yes: the zone, else the default zone (+0x40)'),
        (0x129D37F, 'movss xmm0, dword ptr [rdx + 0x144]', None, 'explosive_damage_percentage (per hit)'),
        (0x129D38E, 'movss xmm0, dword ptr [rbx + 0x184]', None, 'unset (FLT_MAX): the default zone, else 1.0'),
    ],
    'applyDamage_0x9235F0': [
        (0x923766, 'call 0x507920', None, 'override-aware health record'),
        (0x923C57, 'imul rdi, r8, 0x228', None, 'zone i'),
        (0x923D2E, 'mulss xmm0, xmm8', None, 'after the zone pass: main-health loss = round(D x share), share 1.0 without a zone (STRONG: D not traced)'),
        (0x923D3F, 'comiss xmm10, xmm8', None, 'only when the share is positive'),
        (0x923F04, 'mov eax, dword ptr [rdx + rax*4 + 0xf8]', None, 'INSTANCE zone health'),
        (0x923F15, 'mov dword ptr [rdx + rcx*4 + 0xf8], r13d', None, 'instance zone health -= damage'),
        (0x923F39, 'movss xmm8, dword ptr [rdi + 0x300]', None, 'zone affects_main_health (per hit)'),
        (0x924236, 'movd xmm0, dword ptr [rdi + 0x2f0]', None, 'zone health (record) x zone +0xFC ...'),
        (0x924254, 'mulss xmm0, dword ptr [rdi + 0x304]', None, '... caps the main health on this path'),
    ],
    'healthInstanceCreate_0x91D580': [
        (0x91D61C, 'call 0x507920', None, 'override-aware record of the new instance'),
        (0x91D746, 'lea rbx, [rsi + 0x2e0]', None, 'zone 0 (+0x208) + 0xD8'),
        (0x91D751, 'lea rdi, [r13 + 0xf8]', None, 'instance zone health array'),
        (0x91D778, 'mov eax, dword ptr [rbx + 0x10]', None, 'zone health (+0xE8)'),
        (0x91D77B, 'mov dword ptr [rdi], eax', None, '-> instance +0xF8 + 4 x zone (copied at spawn)'),
        (0x91D786, 'movss xmm1, dword ptr [rbx + 0x20]', None, 'health -1: main health / affects_main_health'),
    ],
    'zoneRestore_0x91EFF0': [
        (0x91F1C6, 'movd xmm0, dword ptr [rax + rdi + 0x2f0]', None, 'restores a dead zone to record health x fraction'),
        (0x91F1DA, 'mov dword ptr [rsi + rdx*4 + 0xf8], eax', None, '-> instance zone health'),
    ],
}

# Field table: offset -> (member, storage, filediver lead, readers, lifecycle, grade, verdict, range, semantics).
LIVE, SPAWN, UNSAFE, UNKNOWN = 'WRITABLE_TYPE_LIVE', 'WRITABLE_TYPE_SPAWN', 'UNSAFE', 'UNKNOWN'
AVATAR_FIELDS = [
    (4, 'direction_factor', 'movement_info (PLAUSIBLE)', ['0xA6CBDD'], 'every_frame', 'STRONG', LIVE, [0, 1],
        'Directional multiplier: the slow speeds (aim, walk, crouch aim, crouch walk, prone) are scaled by '
        '(1 - f) + f x this, f from the move direction against the facing (0..1). Name not proven.'),
    (8, 'aim', 'aim', ['0xA6CDEB'], 'every_frame', 'STRONG', LIVE, [0, 10],
        'Standing, state bit 82 set (aiming, inferred): aim x direction factor (m/s).'),
    (12, 'walk', 'walk', ['0xA6CDF2', '0xA5D0C2', '0xA79B63'], 'every_frame', 'STRONG', LIVE, [0, 10],
        'Standing, no jog/sprint action, bit 82 clear: walk x direction factor (m/s).'),
    (16, 'jog', 'jog', ['0xA6CD93'], 'every_frame', 'CONFIRMED', LIVE, [0, 10], 'Standing with the jog action (m/s).'),
    (20, 'sprint', 'sprint', ['0xA6CD79', '0x68B536'], 'every_frame', 'CONFIRMED', LIVE, [0, 10],
        'Standing with the sprint action and stamina > 0 (or Death March) (m/s).'),
    (24, 'sprint_exerted', 'sprint_exerted', ['0xA6CD72'], 'every_frame', 'CONFIRMED', LIVE, [0, 10],
        'Sprinting at empty stamina without Death March (m/s).'),
    (28, 'crouch_aim', 'crouch_aim', ['0xA6CCCB'], 'every_frame', 'STRONG', LIVE, [0, 10],
        'Crouched (state bit 77) while aiming (0xA40B50): x direction factor (m/s).'),
    (32, 'crouch_walk', 'crouch_walk', ['0xA6CCD5', '0xA5D0DB', '0xA79B6F'], 'every_frame', 'STRONG', LIVE, [0, 10],
        'Crouched, otherwise: x direction factor (m/s).'),
    (36, 'crouch_jog', 'crouch_jog', ['0xA6CCAE'], 'every_frame', 'CONFIRMED', LIVE, [0, 10],
        'Crouched with the jog action (m/s).'),
    (40, 'crouch_sprint', 'crouch_sprint', ['0xA6CC91'], 'every_frame', 'CONFIRMED', LIVE, [0, 10],
        'Crouched with the sprint action (m/s).'),
    (44, 'prone', 'prone', ['0xA6CD29', '0x68B528', '0xA5D0EA', '0xA79B76'], 'every_frame', 'STRONG', LIVE, [0, 10],
        'Prone (state bit 78): x direction factor (m/s).'),
    (48, 'swim', 'swim', ['0xA6CC21'], 'every_frame', 'STRONG', LIVE, [0, 10], 'Swimming (state bit 95) (m/s).'),
    (52, 'sprint_stamina_decay_duration', 'sprint_stamina_decay_duration', ['0x833A29'], 'every_frame', 'CONFIRMED',
        LIVE, [1, 3600], 'Seconds to empty a full bar: stamina -= cost multiplier x dt / this (/1.3 with modifier 2), '
        'while sprinting, sliding, or jogging on sand / mud / snow. Divisor: 0 empties the bar at once.'),
    (56, 'jog_stamina_decay_duration', 'jog_stamina_decay_duration', [], 'none_found', 'UNKNOWN', UNKNOWN, None,
        'No reader among the 39 resolver call sites or the type-lookup callers; the terrain jog drain uses +52.'),
    (60, 'stamina_recover_time_stand', 'stamina_recover_time_stand', ['0x82A3F1'], 'every_frame', 'CONFIRMED', LIVE,
        [0.5, 600], 'Seconds to refill an empty bar standing: stamina += regen multiplier x dt / this (cap 1.0).'),
    (64, 'stamina_recover_time_crouch', 'stamina_recover_time_crouch', ['0x82A3EA'], 'every_frame', 'CONFIRMED', LIVE,
        [0.5, 600], 'Same, crouched.'),
    (68, 'stamina_recover_time_prone', 'stamina_recover_time_prone', ['0x82A33F'], 'every_frame', 'CONFIRMED', LIVE,
        [0.5, 600], 'Same, prone.'),
    (72, 'stamina_recover_delay', 'stamina_recover_delay', ['0x833A71', '0xA4FFB0+', '0xA513D0+', '0xA63790+',
        '0xA64AA0+', '0xA72C50+', '0xA85D40+', '0xA9B9C0+'], 'per_action', 'CONFIRMED', LIVE, [0, 60],
        'Seconds without regen after a drain or an action: copied into the per-avatar timer (+0x53E8FC) each time; '
        'the update counts it down (Stim Stamina skips it).'),
    (76, 'stamina_cost_jump', 'stamina_cost_jump', ['0xA6462F'], 'per_action', 'CONFIRMED', LIVE, [0, 1],
        'Fraction of the bar per jump, x the per-avatar cost multiplier.'),
    (80, 'stamina_cost_dodge', 'stamina_cost_dodge', ['0xA50DB3'], 'per_action', 'CONFIRMED', LIVE, [0, 1],
        'Fraction of the bar per dive (0xA50890, the locomotion launch), x the cost multiplier.'),
    (84, 'stamina_cost_vault', 'stamina_cost_vault', [], 'none_found', 'UNKNOWN', UNKNOWN, None, 'Vanilla 0; no reader.'),
    (88, 'stamina_cost_climb', 'stamina_cost_climb', ['0xA9B3DE'], 'per_action', 'CONFIRMED', LIVE, [0, 1],
        'Fraction of the bar per climb (vanilla 0).'),
    (92, 'stamina_cost_slide', 'stamina_cost_slide', ['0xA72641'], 'per_action', 'CONFIRMED', LIVE, [0, 1],
        'Fraction of the bar per slide start, x the cost multiplier.'),
]
ZONE_FIELDS = [
    (0xC4, 'damage_multiplier', 'u32 enum', ['0x12A22A7', '0x129CB9A/0x129D422/0x129DBBC (+3 kinds)'], 'per_hit',
        'CONFIRMED', LIVE, [0, 4], 'Event +0x6C; damage x [0, 1.5, 1, 0.75, 0.25][value] for every hit kind. 0 (None) '
        'makes the zone take no damage. Read from the TYPE record (0x507430) even when a private copy exists.'),
    (0xC8, 'damage_multiplier_dps', 'u32 enum', ['0x12A22B5'], 'per_hit', 'CONFIRMED', LIVE, [0, 4],
        'Damage-over-time hits (builder argument 2): replaces damage_multiplier when not 0; 0 = use it.'),
    (0xCC, 'durable_fraction', 'f32', ['0x12A1E78'], 'per_hit', 'CONFIRMED', LIVE, [0, 1],
        'Event +0x4C: damage = standard x (1 - d) + durable x d (TYPE record).'),
    (0xE8, 'health', 'i32', ['0x91D778 (spawn copy)', '0x91F1C6 (restore)', '0x924236'], 'spawn', 'CONFIRMED', SPAWN,
        [1, 100000], 'Copied into the health instance (+0xF8 + 4 x zone) when the avatar spawns; the live zone health '
        'is that copy. The record value is re-read when a dead zone is restored (0x91EFF0) and on one main-health cap '
        'path (0x924236), so a write also changes those for living avatars. -1 = main health / affects_main_health.'),
    (0xF8, 'affects_main_health', 'f32', ['0x923F39'], 'per_hit', 'CONFIRMED', LIVE, [0, 10],
        'Share of the hit forwarded to main health: main loss = round(D x this) after the zone pass (0x923D2E), only when > 0 (reader CONFIRMED; the exact D is STRONG). Override-aware record (0x507920).'),
    (0x144, 'explosive_damage_percentage', 'f32', ['0x129D37F'], 'per_hit', 'CONFIRMED', 'DORMANT', None,
        'Read only for a zone whose affected_by_explosions (+0x143) is set; it is 0 on all six avatar zones, so '
        'explosions use the DEFAULT zone value (record +0x184 = 0.5, live per hit). Writing a zone value alone has no '
        'effect.'),
]


def f32(raw, at):
    return struct.unpack_from('<f', raw, at)[0]


def rnd(value):
    return None if value is None else (None if value >= FLT_MAX else round(value, 6))


def zone_values(raw, base, thin):
    name = struct.unpack_from('<I', raw, base + 0x60)[0]
    return {'recordOffset': base, 'name': thin.get(name, '0x%08X' % name) if name else None,
        'damage_multiplier': DAMAGE_MULTIPLIER[struct.unpack_from('<I', raw, base + 0xC4)[0]],
        'damage_multiplier_dps': DAMAGE_MULTIPLIER[struct.unpack_from('<I', raw, base + 0xC8)[0]],
        'durable_fraction': rnd(f32(raw, base + 0xCC)), 'armor': struct.unpack_from('<I', raw, base + 0xD8)[0],
        'health': struct.unpack_from('<i', raw, base + 0xE8)[0],
        'constitution': struct.unpack_from('<i', raw, base + 0xEC)[0],
        'affects_main_health': rnd(f32(raw, base + 0xF8)), 'member_0xFC': rnd(f32(raw, base + 0xFC)),
        'affected_by_explosions': raw[base + 0x143], 'explosive_damage_percentage': rnd(f32(raw, base + 0x144))}


def datalibrary():
    t = tables.pinned()
    t.entity_rows()
    index_of = {v: k for k, v in t._index_type.items()}
    avatar, health = t.component('AvatarComponentData'), t.component('HealthComponentData')
    if (index_of[avatar.type_hash], index_of[health.type_hash]) != (AVATAR_INDEX, HEALTH_INDEX):
        raise ValueError('component indices changed')
    if (avatar.count, avatar.capacity, avatar.record_size, avatar.records_offset) != (2, AVATAR_ROWS, AVATAR_SIZE, 0x20):
        raise ValueError('AvatarComponentData geometry changed')
    if avatar.rows() != [(1, HELLDIVER, 0)]:
        raise ValueError('AvatarComponentData ownership changed: %r' % avatar.rows())
    if (health.capacity, health.record_size, health.records_offset) != (HEALTH_ROWS, HEALTH_SIZE, 0x3EA0):
        raise ValueError('HealthComponentData geometry changed')
    if health.owners(HEALTH_RECORD) != [HELLDIVER] or health.record_of(HELLDIVER) != HEALTH_RECORD:
        raise ValueError('health record 76 ownership changed')
    health_row = [row for row, resource, _ in health.rows() if resource == HELLDIVER]
    entity = t.entity(HELLDIVER)
    if entity.get('AvatarComponentData') != 0 or entity.get('HealthComponentData') != HEALTH_RECORD:
        raise ValueError('avatar_helldiver component list changed')
    raw0, raw1 = avatar.raw(0), avatar.raw(1)
    default_diff = [{'offset': o, 'record0': rnd(f32(raw0, o)), 'record1': rnd(f32(raw1, o))}
        for o in range(0, AVATAR_SIZE, 4) if raw0[o:o + 4] != raw1[o:o + 4]]
    hraw = health.raw(HEALTH_RECORD)
    thin = t.thin
    zones = [dict(zone_values(hraw, ZONE_BASE + i * ZONE_STRIDE, thin), index=i) for i in range(38)
        if struct.unpack_from('<I', hraw, ZONE_BASE + i * ZONE_STRIDE + 0x60)[0]]
    if [z['name'] for z in zones] != ['head', 'body', 'arm_left', 'arm_right', 'leg_left', 'leg_right']:
        raise ValueError('avatar zones changed')
    view = build_view.from_datalibrary(build_profile.datalibrary(), {})
    deltas = []
    for resource, delta in sorted(view.deltas.items()):
        entries = [e for e in delta['entries'] if e['component'] in (AVATAR_INDEX, HEALTH_INDEX)]
        if entries:
            deltas.append({'delta': '0x%016X' % resource, 'components': sorted({'0x%X' % e['component']
                for e in delta['entries']}), 'entries': [{'component': 'Avatar' if e['component'] == AVATAR_INDEX
                else 'Health', 'offset': e['offset'], 'value': rnd(f32(e['bytes'], 0)) if e['component'] == AVATAR_INDEX
                else struct.unpack_from('<i', e['bytes'], 0)[0] if e['offset'] == 0 else rnd(f32(e['bytes'], 0))}
                for e in entries]})
    return t, avatar, health, {
        'avatarComponent': {'componentIndex': '0x%X' % AVATAR_INDEX, 'typeHash': '0x%08X' % avatar.type_hash,
            'frameOffset': avatar.frame_offset, 'tableOffsetInFile': avatar.frame_offset + 28,
            'records': avatar.count, 'indexRows': avatar.capacity, 'recordSize': AVATAR_SIZE,
            'rows': [{'row': row, 'resource': '0x%016X' % res, 'record': rec} for row, res, rec in avatar.rows()],
            'record0': {'owner': 'content/fac_helldivers/cha_avatar/avatar_helldiver', 'ownerCount': 1,
                'sha256': base.sha(raw0)},
            'record1': {'owner': None, 'role': 'unowned default record: used only by the delta-copy creators when a '
                'resource has no row (0x5757F9, 0x83C513)', 'differsFromRecord0': default_diff}},
        'healthComponent': {'componentIndex': '0x%X' % HEALTH_INDEX, 'frameOffset': health.frame_offset,
            'tableOffsetInFile': health.frame_offset + 28, 'record': HEALTH_RECORD, 'indexRow': health_row[0],
            'ownerCount': 1, 'recordSha256': base.sha(hraw), 'mainHealth': struct.unpack_from('<i', hraw, 0)[0],
            'defaultZone': zone_values(hraw, DEFAULT_ZONE, thin), 'zones': zones},
        'entityDeltas': {'note': 'An entity spawned with one of these deltas gets a private copy of the WHOLE record at '
            'spawn (0x5740B0 / 0x83C420 for Avatar, 0x929A50 for Health), frozen from the type record of that moment. '
            'Which customizations carry them is not resolved here.', 'deltas': deltas},
    }


def hashmap(mem, at, slots, capacity, empty):
    pointer, count, sentinel = mem.ptr(at + slots), mem.u32(at + capacity), mem.u32(at + empty)
    if not pointer or not count or count > 1 << 20:
        return {}
    raw = mem.read(pointer, count * 8)
    out = {}
    for i in range(count):
        key, value = struct.unpack_from('<Ii', raw, i * 8)
        if key != sentinel and value != -1:
            out[key] = value
    return out


def observe(name, avatar, health):
    mem = base.Mem(name)
    em = mem.ptr(mem.game + G_ENTITY_MANAGER)
    at, ht = mem.ptr(em + TABLE_BASE + 8 * AVATAR_INDEX), mem.ptr(em + TABLE_BASE + 8 * HEALTH_INDEX)
    region, hregion = mem.s.region(at), mem.s.region(ht)
    if region['allocation_base'] != hregion['allocation_base']:
        raise ValueError('the two tables are not in one allocation in %s' % name)
    alloc = region['allocation_base']
    if at - alloc != avatar.frame_offset + 28 or ht - alloc != health.frame_offset + 28:
        raise ValueError('table offsets in the loaded entity file differ in %s' % name)
    if mem.read(at, len(avatar.body)) != avatar.body:
        raise ValueError('AvatarComponentData table differs from the datalibrary in %s' % name)
    if mem.read(ht, HEALTH_ROWS * 16) != health.body[:HEALTH_ROWS * 16] or \
            mem.read(ht + 0x3EA0 + HEALTH_RECORD * HEALTH_SIZE, HEALTH_SIZE) != health.raw(HEALTH_RECORD):
        raise ValueError('health index rows / record 76 differ in %s' % name)
    out = {'snapshot': name, 'gameDllBase': '0x%X' % mem.game, 'entityManager': '0x%X' % em,
        'entityFile': {'allocationBase': '0x%X' % alloc, 'regionSize': '0x%X' % region['size'],
            'protect': '0x%X' % region['protect'], 'type': '0x%X' % region['type']},
        'avatarTable': '0x%X' % at, 'avatarRecord0': '0x%X' % (at + 0x20),
        'healthTable': '0x%X' % ht, 'healthRecord76': '0x%X' % (ht + 0x3EA0 + HEALTH_RECORD * HEALTH_SIZE),
        'bytesEqualDatalibrary': True}
    av, hm = mem.ptr(mem.game + G_AVATAR), mem.ptr(mem.game + G_HEALTH)
    instances = hashmap(mem, av, AV_HASH, 0x100, 0x104)
    copies = hashmap(mem, av, AV_COPY_MAP, 0x547C78, 0x547C7C)
    hcopies = hashmap(mem, hm, 0x1070, 0x1078, 0x107C)
    hinst = hashmap(mem, hm, 0x1030, 0x1038, 0x103C)
    typ = mem.read(at + 0x20, AVATAR_SIZE)
    avatars = []
    for entity, index in sorted(instances.items()):
        d = base.descriptor(mem, mem.ptr(av + AV_DESCRIPTORS + 8 * index))
        item = {'entity': '0x%X' % entity, 'index': index, 'type': d['type'], 'owned': d['authority'],
            'simulatedHere': index < mem.u32(av + AV_OWNED),
            'stamina': rnd(f32(mem.read(av + AV_STAMINA + index * AV_STAMINA_STRIDE, 4), 0))}
        if item['simulatedHere']:
            item['staminaCostMultiplier'] = rnd(f32(mem.read(av + AV_COST + index * AV_SIM_STRIDE, 4), 0))
            item['regenDelayTimer'] = rnd(f32(mem.read(av + AV_DELAY + index * AV_SIM_STRIDE, 4), 0))
        if entity in copies:
            copy = mem.read(av + AV_COPIES + copies[entity] * AVATAR_SIZE, AVATAR_SIZE)
            item['privateCopy'] = {'index': copies[entity], 'differsFromType': [{'offset': o,
                'type': rnd(f32(typ, o)), 'copy': rnd(f32(copy, o))} for o in range(0, AVATAR_SIZE, 4)
                if typ[o:o + 4] != copy[o:o + 4]]}
        else:
            item['privateCopy'] = None
        hi = hinst.get(entity)
        if hi is not None:
            array = mem.ptr(hm + 0x1058)
            item['instanceZoneHealth'] = list(struct.unpack('<6i', mem.read(array + hi * 0x1B8 + 0xF8, 24)))
        item['healthPrivateCopy'] = entity in hcopies
        avatars.append(item)
    out['avatarManager'] = {'total': mem.u32(av + AV_TOTAL), 'simulatedHere': mem.u32(av + AV_OWNED),
        'privateCopies': len(copies), 'avatars': avatars}
    out['healthPrivateCopies'] = len(hcopies)
    mem.close()
    if any(a['type'] != '%016X' % HELLDIVER for a in avatars):
        raise ValueError('an avatar that is not avatar_helldiver in %s' % name)
    return out


def main():
    t, avatar, health, data = datalibrary()
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[4])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, image = snap.module_image('game.dll')
    snap.close()
    img = base.Image(image, image_base, base.TEXT)
    proofs = {group: [img.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    constants = {'0x23C7554': f32(image, 0x23C7554), '0x23C6D70': f32(image, 0x23C6D70),
        'multiplierTable_0x21CF898': [round(f32(image, MULTIPLIER_TABLE + 4 * i), 6) for i in range(5)],
        'jumpTable_0x129DD08': ['0x%X' % (struct.unpack_from('<I', image, 0x129DD08 + 4 * i)[0]) for i in range(7)]}
    if constants['0x23C7554'] != 10.0 or constants['multiplierTable_0x21CF898'] != [0.0, 1.5, 1.0, 0.75, 0.25]:
        raise ValueError('constants changed')
    data_pins = [{'rva': rva, 'bytes': image[rva:rva + n].hex(), 'asm': 'data', 'role': role} for rva, n, role in
        ((0x23C7554, 4, 'speed cap 10.0'), (MULTIPLIER_TABLE, 20, 'damage multiplier table'),
         (0x129DD08, 28, 'damage-by-kind jump table'))]
    relocation = {name: base.verify_pins_live(name, pins + data_pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    observations = [observe(name, avatar, health) for name in SNAPSHOTS]
    raw0 = avatar.raw(0)
    hraw = health.raw(HEALTH_RECORD)
    fields = []
    for offset, member, lead, readers, lifecycle, grade, verdict, limits, semantics in AVATAR_FIELDS:
        fields.append({'record': 'AvatarComponentData#0', 'offset': offset, 'member': member, 'filediverLead': lead,
            'storage': 'f32', 'vanilla': rnd(f32(raw0, offset)), 'readers': readers, 'lifecycle': lifecycle,
            'grade': grade, 'verdict': verdict, 'range': limits, 'semantics': semantics})
    for zone in data['healthComponent']['zones']:
        for zoffset, member, storage, readers, lifecycle, grade, verdict, limits, semantics in ZONE_FIELDS:
            at = ZONE_BASE + zone['index'] * ZONE_STRIDE + zoffset
            value = zone[member]
            fields.append({'record': 'HealthComponentData#76', 'zone': zone['name'], 'zoneIndex': zone['index'],
                'zoneOffset': zoffset, 'offset': at, 'member': member, 'storage': storage, 'vanilla': value,
                'readers': readers, 'lifecycle': lifecycle, 'grade': grade, 'verdict': verdict, 'range': limits,
                'semantics': semantics})
    fields.append({'record': 'HealthComponentData#76', 'zone': 'default', 'offset': DEFAULT_ZONE + 0x144,
        'member': 'explosive_damage_percentage', 'storage': 'f32', 'vanilla': rnd(f32(hraw, DEFAULT_ZONE + 0x144)),
        'readers': ['0x129D37F', '0x129D38E'], 'lifecycle': 'per_hit', 'grade': 'CONFIRMED', 'verdict': LIVE,
        'range': [0, 10], 'semantics': 'Explosion damage taken by every avatar zone (none sets affected_by_explosions); '
        'the existing enemy-schema id entity.explosive_damage_percentage (+388). Override-aware record.'})
    report = {
        'schemaVersion': 1,
        'title': 'Helldiver avatar type fields: movement, stamina, body zones (F5FEE03DCFDB)',
        'source': {'build': build_profile.BUILD_ID, 'gameDllSha256': base.PROFILE_DLL_SHA,
            'unpackedImageSha256': base.sha(image), 'snapshots': SNAPSHOTS, 'writes': 0},
        'summary': {
            'avatar': 'Every live reader resolves the record per call through 0x508DB0 (39 call sites): a private '
                'copy if the entity has one, else the type record. Movement speed (0xA6C700) and stamina regen run '
                'every frame in the avatar update 0x829E90 for the avatars simulated here (the first +0x70 slots); '
                'drains every frame in 0x833930 (owned only); costs once per action. No member is copied into an '
                'avatar instance. A type write applies at the next frame to every avatar this machine simulates '
                'that has no private copy.',
            'privateCopies': 'Entity deltas create a frozen copy of the whole record at spawn. The ship avatar has one '
                'in all three ship snapshots (delta 0x73012E9238B6E3B9: walk 1.5, jog 4.08), so type writes do not '
                'reach it; the mission avatars had none.',
            'zones': 'damage_multiplier (+0xC4), damage_multiplier_dps (+0xC8) and durable_fraction (+0xCC) are read '
                'per hit from the TYPE record; affects_main_health (+0xF8) and the explosive percentage per hit from the '
                'override-aware record; zone health (+0xE8) is copied at spawn. The six zones\' explosive percentage '
                'is dormant; the default zone\'s (+0x184 = 0.5) is the live one.',
            'speedCap': 'The target speed is min(10.0, speed) (0xA6D0DE): values above 10 m/s have no effect.',
        },
        'identity': data,
        'code': proofs,
        'dataPins': data_pins,
        'constants': constants,
        'pinCount': len(pins) + len(data_pins),
        'pinsIdenticalInAllSnapshots': True,
        'fields': fields,
        'observations': observations,
        'statuses': {('0x%X' % k): v for k, v in STATUS.items()},
        'guardsForAWrite': [
            'entity manager = [game + 0x346BF98] (pinned 0x507435 / 0x508775); table = [EM + 0xF12478 + 8 x index] '
            '(0xF12BB8 Avatar, 0xF12B78 Health) and it equals entity-file allocation + frame offset + 28',
            'AvatarComponentData: index row 1 = {0x4D1C334D294DFA97, record 0, 0}, row 0 empty, record 0 unique owner',
            'HealthComponentData: index row 443 = {0x4D1C334D294DFA97, record 76, 0}, no other row selects 76; zone '
            'name hashes of zones 0..5 (head, body, arm_left, arm_right, leg_left, leg_right)',
            'expected current bytes; the entity file allocation is read-only (protect 0x2): the guarded '
            'VirtualProtect path other type-record writes use',
            'effect check: the local avatar has no private copy (avatar manager +0x547C70 map; health +0x1070 map)',
        ],
        'unproven': [
            'Names of the state bits (77 crouch, 78 prone, 82 aim, 95 swim) and of +4 (direction factor).',
            'jog_stamina_decay_duration (+56), stamina_cost_vault (+84), ExertionLevelInfo (+340..+388): no reader found.',
            'Which customizations (armor passives?) carry the three AvatarComponentData deltas; they freeze a copy.',
            'Multiplayer: which machine builds a hit on a remote avatar (its type record decides +0xC4/+0xC8/+0xCC); '
            'remote avatars are not simulated here, so movement and stamina writes reach only the local avatar.',
            'The main-health formula beyond round(damage x affects_main_health); zone +0xFC (0 on the avatar).',
            'Nothing is live-tested.',
        ],
    }
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'pins': report['pinCount'], 'fields': len(fields),
        'observations': [(o['snapshot'][13:], o['avatarManager']['simulatedHere'], o['avatarManager']['privateCopies'])
            for o in observations]}, indent=1))


if __name__ == '__main__':
    main()
