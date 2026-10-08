"""Where a Helldiver armor's three displayed stats (ARMOR RATING, SPEED, STAMINA REGEN) come from, how the game applies
them, and what is editable. Read-only research against the retained snapshots
(research/docs/armor-stats-F5FEE03DCFDB.md).

  py scripts/research_armor_stats.py      # write research/armor-stats-F5FEE03DCFDB.json

Every structural claim is pinned as exact instruction bytes (verified identical in every retained snapshot); the
weight tables and the damage curve are pinned as data bytes of the game.dll image. Values are read from the
snapshots. The wiki importer output (HD2WikiImporter/output/wiki_armors.json) and the filediver datalibrary layout
are third-party leads: the wiki values are only COMPARED with what the game's own formulas give for every armor kit
in memory. Nothing writes. Requires capstone and numpy (research only).
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
import research_player_attributes as attributes  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/armor-stats-F5FEE03DCFDB.json'
WIKI = Path(r'C:\Users\Skye\Documents\HD2Mods\HD2WikiImporter\output\wiki_armors.json')

G_CUSTOMIZATION = attributes.G_CUSTOMIZATION   # 0x33264F8
G_AVATAR = base.G_AVATAR                       # 0x3326D20
G_LOCOMOTION = 0x3326CF8                       # LocomotionComponent manager (research_vehicle_mech_components.py)
F_AVERAGE = 0x11D91B0          # float KitWeightAverage(u32 helmetKit, u32 armorKit, u32 bodyType, u32 table)
F_STAMINA_FACTOR = 0x8774D0    # float ArmorStaminaFactor(?, u32 armorKit, u32 bodyType)
F_SPEED_FACTOR = 0x8777C0      # float ArmorSpeedFactor(?, u32 armorKit, u32 bodyType)
F_APPLY = 0x877AB0             # ApplyCustomizationToAvatar(mgr, player entity, avatar entity)
F_SET_SPEED_SLOT = 0x9CCAE0    # SetLocomotionSpeedMultiplier(?, entity, slot, float)
F_SPEED_PRODUCT = 0x9CCC20     # float LocomotionSpeedMultiplier(mgr, entity) = slot0*..*slot4
F_SPEED_SMOOTH = 0x7C6CE0      # record +0x14 moves toward the product
F_CURVE = 0x129C940            # float PlayerArmorDamageCurve(float armor value)
F_HIT_INIT = 0x12A15E0         # InitHitInfo
F_PASSIVE_VALUE = attributes.F_PASSIVE_VALUE

T_ARMOR, T_SPEED, T_STAMINA = 0x21CB160, 0x2160678, 0x21C6F78   # f32[3] by piece weight (light, medium, heavy)
T_CURVE = 0x21CEFF0            # {f32 key, f32 value}[5], keys descending
K_ONE, K_RATING_STEP, K_SPEED_STEP = 0x23C6D70, 0x23C76FC, 0x23C74A4
K_MINUS_ONE, K_THREE, K_PARTIAL = 0x23C800C, 0x23C7280, 0x23C6B7C
T_ZONE_MULTIPLIER = 0x21CF898

KIT_BODIES, KIT_BODY_COUNT = 0x30, 0x38
BODY_STRIDE, BODY_TYPE, BODY_PIECES, BODY_PIECE_COUNT = 0x18, 0x00, 0x08, 0x10
PIECE_STRIDE, PIECE_SLOT, PIECE_TYPE, PIECE_WEIGHT = 0x60, 0x08, 0x0C, 0x10
SLOTS = ['helmet', 'cape', 'torso', 'hips', 'left_leg', 'right_leg', 'left_arm', 'right_arm', 'left_shoulder',
    'right_shoulder']        # filediver CustomizationKitSlot (lead); the code tests slot 0, 2 and 2..9 except 3
WEIGHTS = ['light', 'medium', 'heavy']
AVATAR_STRIDE_SIM, AVATAR_STAMINA_FACTOR = 0x1238, 0x53E900
AVATAR_STRIDE_STATE, AVATAR_ARMOR_MODIFIER = 0x1B8, 0x546AC4
LOCO_RECORDS, LOCO_STRIDE = 0x48, 0x34

PINS = {
    'kitWeightAverage_0x11D91B0': [
        (0x11D91CC, 'movss xmm3, dword ptr [rip + {rip}]', K_ONE, 'count step 1.0'),
        (0x11D9203, 'mov r15, qword ptr [rip + {rip}]', G_CUSTOMIZATION, 'customization manager: kit array +0x00'),
        (0x11D920A, 'mov ebp, dword ptr [r15 + 8]', None, 'kit count'),
        (0x11D9224, 'cmp dword ptr [rax], ecx', None, 'first kit (ecx, the helmet slot) by id'),
        (0x11D9247, 'mov esi, dword ptr [rax + 0x38]', None, 'kit +0x38 body count'),
        (0x11D925D, 'mov r11, qword ptr [r14 + 0x30]', None, 'kit +0x30 bodies (0x18 each)'),
        (0x11D9265, 'mov eax, dword ptr [r11 + r10*8]', None, 'body +0x00 body type'),
        (0x11D9269, 'cmp eax, r12d', None, 'body type == requested (applied record +0x00)'),
        (0x11D926E, 'cmp eax, 3', None, 'or body type 3 (any)'),
        (0x11D9273, 'mov ebx, dword ptr [r11 + r10*8 + 0x10]', None, 'body +0x10 piece count'),
        (0x11D928D, 'shl rcx, 5', None, 'piece stride 3 << 5 = 0x60'),
        (0x11D9291, 'add rcx, qword ptr [r11 + r10*8 + 8]', None, 'body +0x08 pieces'),
        (0x11D92C3, 'cmp dword ptr [rax + 0xc], 0', None, 'helmet kit: piece type 0 (armor) only'),
        (0x11D92C9, 'cmp dword ptr [rax + 8], 0', None, 'helmet kit: piece slot 0 only'),
        (0x11D92CF, 'mov ecx, dword ptr [rax + 0x10]', None, 'piece +0x10 weight'),
        (0x11D92B4, 'lea r11, [rip - 0x11d92bb]', None, 'image base (tables are image-relative)'),
        (0x11D92ED, 'movss xmm0, dword ptr [r11 + rcx*4 + 0x21c6f78]', None, 'table 2: stamina'),
        (0x11D92F9, 'movss xmm0, dword ptr [r11 + rcx*4 + 0x2160678]', None, 'table 1: speed'),
        (0x11D9305, 'movss xmm0, dword ptr [r11 + rcx*4 + 0x21cb160]', None, 'table 0: armor'),
        (0x11D9365, 'mov r10, qword ptr [rsi + 0x30]', None, 'armor kit (edx) bodies'),
        (0x11D93C7, 'cmp dword ptr [rcx + 0xc], 0', None, 'armor kit: piece type 0 only'),
        (0x11D93CD, 'mov edx, dword ptr [rcx + 8]', None, 'piece slot'),
        (0x11D93D0, 'lea eax, [rdx - 2]', None, 'slot - 2'),
        (0x11D93D3, 'test eax, 0xfffffff8', None, 'slot 2..9 (torso..right shoulder)'),
        (0x11D93DA, 'cmp edx, 3', None, 'except slot 3 (hips)'),
        (0x11D93DF, 'mov edx, dword ptr [rcx + 0x10]', None, 'piece weight'),
        (0x11D93E2, 'addss xmm2, xmm3', None, 'count += 1'),
        (0x11D93FD, 'movss xmm0, dword ptr [r10 + rdx*4 + 0x21c6f78]', None, 'table 2'),
        (0x11D9409, 'movss xmm0, dword ptr [r10 + rdx*4 + 0x2160678]', None, 'table 1'),
        (0x11D9415, 'movss xmm0, dword ptr [r10 + rdx*4 + 0x21cb160]', None, 'table 0'),
        (0x11D941F, 'addss xmm1, xmm0', None, 'sum += table[weight]'),
        (0x11D942D, 'comiss xmm3, xmm2', None, 'count < 1 -> 0'),
        (0x11D948D, 'divss xmm1, xmm2', None, 'result = sum / count'),
        (0x11D94B0, 'xor r9d, r9d', None, 'wrapper: table 0 (no static caller)'),
        (0x11D94C0, 'mov r9d, 2', None, 'wrapper: table 2 (no static caller)'),
        (0x11D94D0, 'mov r9d, 1', None, 'wrapper: table 1 (no static caller)'),
    ],
    'armorStaminaFactor_0x8774D0': [
        (0x8774F5, 'mov r11, qword ptr [rip + {rip}]', G_CUSTOMIZATION, 'customization manager kits'),
        (0x8774FF, 'movss xmm2, dword ptr [rip + {rip}]', K_ONE, 'default 1.0 (no kit / no piece)'),
        (0x87757E, 'mov edi, dword ptr [rax + 0x38]', None, 'body count'),
        (0x87758A, 'mov r10, qword ptr [rsi + 0x30]', None, 'bodies'),
        (0x877598, 'cmp eax, ebp', None, 'body type == requested'),
        (0x8775A1, 'mov r11d, dword ptr [r10 + r9*8 + 0x10]', None, 'piece count (up to 20 pieces)'),
        (0x8775E3, 'lea r10, [rip + {rip}]', T_STAMINA, 'STAMINA table'),
        (0x87761A, 'cmp dword ptr [rax + 0xc], 0', None, 'piece type 0 (armor); NO slot filter'),
        (0x877620, 'mov r8d, dword ptr [rax + 0x10]', None, 'piece weight'),
        (0x877624, 'cmp r8d, 3', None, 'weight 3 skipped'),
        (0x87762A, 'addss xmm0, dword ptr [r10 + r8*4]', None, 'sum += table[weight]'),
        (0x877630, 'addss xmm1, xmm2', None, 'count += 1'),
        (0x877703, 'divss xmm0, xmm1', None, 'average'),
    ],
    'armorSpeedFactor_0x8777C0': [
        (0x8777EF, 'movss xmm2, dword ptr [rip + {rip}]', K_ONE, 'default 1.0'),
        (0x8778D3, 'lea r10, [rip + {rip}]', T_SPEED, 'SPEED table'),
        (0x87791A, 'addss xmm0, dword ptr [r10 + r8*4]', None, 'sum += table[weight] (same piece filter as stamina)'),
        (0x8779F3, 'divss xmm0, xmm1', None, 'average'),
    ],
    'applyCustomizationToAvatar_0x877AB0': [
        (0x874C0D, 'call 0x877ab0', None, 'caller: per-record update 0x874520 (kit change applied)'),
        (0x81C563, 'call 0x877ab0', None, 'caller: 0x81BE70 (avatar side)'),
        (0x877F53, 'movss xmm4, dword ptr [rip + {rip}]', K_ONE, 'default factor 1.0'),
        (0x8780BB, 'mov r8d, dword ptr [rcx + r15 + 0x96c]', None, 'applied record +0x00 body type'),
        (0x8780C3, 'mov edx, dword ptr [rcx + r15 + 0x978]', None, 'applied record +0x0C armor kit'),
        (0x8780CB, 'call 0x8774d0', None, 'stamina factor'),
        (0x877FBE, 'mov r10, qword ptr [rip + {rip}]', G_AVATAR, 'avatar manager'),
        (0x87802B, 'imul rax, rcx, 0x1238', None, 'avatar simulation block stride'),
        (0x878032, 'movss dword ptr [rax + r10 + 0x53e900], xmm0', None, 'avatar +0x53E900 = stamina factor'),
        (0x878109, 'call 0x8777c0', None, 'speed factor'),
        (0x878111, 'movaps xmm3, xmm4', None, 'value'),
        (0x878114, 'mov r8d, 3', None, 'locomotion speed slot 3'),
        (0x87811C, 'call 0x9ccae0', None, 'SetLocomotionSpeedMultiplier(avatar, 3, factor)'),
    ],
    'locomotionSpeedMultiplier': [
        (0x9CCAE8, 'mov r10, qword ptr [rip + {rip}]', G_LOCOMOTION, 'LocomotionComponent manager'),
        (0x9CCAEF, 'movsxd rbp, r8d', None, 'slot'),
        (0x9CCB62, 'mov rax, qword ptr [r10 + 0x48]', None, 'per-entity records (13 floats)'),
        (0x9CCB66, 'imul rdx, rcx, 0xd', None, 'record stride 13 floats'),
        (0x9CCB6D, 'movss dword ptr [rax + rdx*4], xmm3', None, 'record[slot] = value'),
        (0x9CCCAB, 'test byte ptr [rcx + 0x14], 1', None, 'product getter: active entity only'),
        (0x9CCC7C, 'movss xmm0, dword ptr [rip + {rip}]', K_ONE, 'else 1.0'),
        (0x9CCCC4, 'imul rax, rdx, 0x34', None, 'record'),
        (0x9CCCC8, 'movss xmm0, dword ptr [rax + rcx + 4]', None, 'slot 1'),
        (0x9CCCCE, 'mulss xmm0, dword ptr [rcx + rax]', None, '* slot 0'),
        (0x9CCCD3, 'mulss xmm0, dword ptr [rax + rcx + 8]', None, '* slot 2'),
        (0x9CCCD9, 'mulss xmm0, dword ptr [rax + rcx + 0xc]', None, '* slot 3 (armor)'),
        (0x9CCCDF, 'mulss xmm0, dword ptr [rax + rcx + 0x10]', None, '* slot 4'),
        (0x7C6CE4, 'movss xmm0, dword ptr [rcx + 4]', None, 'smoothing: product of slots 0..4'),
        (0x7C6CF0, 'movss xmm5, dword ptr [rcx + 0x14]', None, 'current (+0x14)'),
        (0x7C6D16, 'subss xmm4, xmm5', None, 'product - current'),
        (0x7C6D42, 'mulss xmm0, xmm4', None, '* min(1, rate x dt)'),
        (0x7C6D4E, 'movss dword ptr [rcx + 0x14], xmm0', None, 'current += ...'),
    ],
    'staminaRegen_0x829E90': [
        (0x82A0AF, 'imul r12, rbx, 0x1238', None, 'avatar simulation block'),
        (0x82A0C5, 'add r12, 0x53d8b0', None, 'r12 = manager + 0x53D8B0 + i x 0x1238'),
        (0x82A2A1, 'movss xmm0, dword ptr [r12 + 0x1050]', None, 'avatar +0x53E900 (the armor stamina factor)'),
        (0x82A2B9, 'mulss xmm0, dword ptr [rip + {rip}]', 0x32FDB08, 'x 1.3 while modifier 2 is active'),
        (0x82A2C1, 'call 0x11de2a0', None, 'x active type-0x33 effect values'),
        (0x82A2E3, 'movaps xmm2, xmm0', None, 'regen multiplier'),
        (0x82A3F1, 'movss xmm0, dword ptr [rax + 0x3c]', None, 'stamina_recover_time (stand)'),
        (0x82A403, 'divss xmm2, xmm0', None, 'factor / recover time'),
        (0x82A411, 'mulss xmm2, xmm10', None, 'x dt'),
        (0x82A416, 'addss xmm2, dword ptr [rax + r13 + 0x547854]', None, '+ stamina'),
        (0x82A420, 'minss xmm2, xmm11', None, 'capped at 1'),
    ],
    'staminaDrain_0x833930': [
        (0x833A0E, 'movss xmm0, dword ptr [rip + {rip}]', 0x32FDB08, 'divisor 1.3 while modifier 2 is active'),
        (0x833A16, 'call 0x11de2a0', None, 'x active type-0x33 effect values'),
        (0x833A1B, 'movss xmm2, dword ptr [rbx + rbp + 0x53e900]', None, 'the armor stamina factor'),
        (0x833A29, 'divss xmm2, dword ptr [r14 + 0x34]', None, '/ sprint_stamina_decay_duration'),
        (0x833A49, 'mulss xmm2, xmm6', None, 'x dt'),
        (0x833A4D, 'divss xmm2, xmm0', None, '/ divisor'),
        (0x833A54, 'subss xmm1, xmm2', None, 'stamina -= ...'),
    ],
    'hitArmorValue_0x12A15E0': [
        (0x12A1E61, 'call 0x922060', None, 'hit zone of the target'),
        (0x12A1E82, 'mov ecx, dword ptr [rax + 0xd8]', None, 'zone +0xD8 armor (int; 0 for every avatar zone)'),
        (0x12A1E8D, 'movss dword ptr [r14 + 0x50], xmm0', None, 'hit +0x50 = zone armor'),
        (0x12A2129, 'mov edx, dword ptr [rdi + r11 + 0x978]', None, 'target player: applied armor kit'),
        (0x12A2155, 'mov r8d, dword ptr [rdi + r11 + 0x96c]', None, 'applied body type'),
        (0x12A2163, 'call 0x11d91b0', None, 'base = average of table 0 (helmet kit 0)'),
        (0x12A2174, 'mov ecx, dword ptr [rbx + 0x1c]', None, 'armor KIT passive'),
        (0x12A2177, 'mov r8d, 0xafae3b47', None, 'armor-rating key'),
        (0x12A2180, 'call 0x11da090', None, 'A = PassiveValue(kit passive, key, base)'),
        (0x12A204A, 'addss xmm2, dword ptr [r14 + 0x50]', None, 'hit +0x50 += A'),
        (0x12A2050, 'addss xmm4, dword ptr [r14 + 0x54]', None, 'hit +0x54 += A'),
        (0x12A20CF, 'movss xmm3, dword ptr [rax + r12 + 0x546ac4]', None, 'avatar +0x546AC4 armor modifier'),
        (0x12A20E4, 'movss xmm0, dword ptr [rip + {rip}]', K_MINUS_ONE, 'lower clamp -1'),
        (0x12A20EC, 'addss xmm2, xmm3', None, 'armor + modifier'),
        (0x12A20F0, 'movss xmm5, dword ptr [rip + {rip}]', K_THREE, 'upper clamp 3'),
        (0x12A21A7, 'minss xmm1, xmm2', None, 'clamp'),
        (0x12A21AF, 'movss dword ptr [r14 + 0x50], xmm1', None, 'hit +0x50 (only when the modifier is not 0)'),
    ],
    'armorDamageCurve_0x129C940': [
        (0x129C940, 'lea r8, [rip + {rip}]', T_CURVE, 'curve {key, value}[5]'),
        (0x129C954, 'comiss xmm5, xmm4', None, 'first key <= armor'),
        (0x129C964, 'movss xmm0, dword ptr [rip + {rip}]', K_ONE, 'below every key: 1.0'),
        (0x129C973, 'movss xmm0, dword ptr [r8 + rax*8 + 4]', None, 'at or above the top key: its value'),
        (0x129C994, 'minss xmm0, xmm5', None, 'linear interpolation between neighbours'),
        (0x129C9A0, 'divss xmm0, xmm1', None, ''),
        (0x129C9A8, 'addss xmm0, dword ptr [r8 + rdx*8 + 4]', None, ''),
    ],
    'damageBuilder_0x129C9F0': [
        (0x129CA3E, 'call 0x129c7c0', None, 'effective penetration (angle-dependent)'),
        (0x129CA54, 'movss xmm9, dword ptr [rbx + 0x50]', None, 'hit +0x50 armor value'),
        (0x129CA5A, 'movss xmm7, dword ptr [rip + {rip}]', K_ONE, '1.0'),
        (0x129CABC, 'subss xmm0, xmm9', None, 'NOT an avatar: penetration - armor'),
        (0x129CAC5, 'comiss xmm0, xmm7', None, '>= 1: x1.0'),
        (0x129CB00, 'movss xmm6, dword ptr [rip + {rip}]', K_PARTIAL, '0..1: x0.65 (below 0: x0)'),
        (0x129CADB, 'movaps xmm1, xmm9', None, 'AVATAR: curve key = armor value only'),
        (0x129CADF, 'call 0x129c940', None, 'multiplier = curve(armor value)'),
        (0x129CAE4, 'cmp dword ptr [rbx + 0x7c], 0x8c5570c9', None, 'this hit kind: never below x1.0'),
        (0x129CB55, 'cmp byte ptr [rbx + 0x73], 0', None, 'flag: x1.0'),
        (0x129CB61, 'movss dword ptr [rdi + 4], xmm6', None, 'out +4 = multiplier'),
        (0x129CB66, 'mulss xmm1, xmm11', None, 'damage x multiplier'),
        (0x129CB93, 'lea rcx, [rip + {rip}]', T_ZONE_MULTIPLIER, 'then x zone damage multiplier [0,1.5,1,0.75,0.25]'),
        (0x129CB9A, 'mulss xmm1, dword ptr [rcx + rax*4]', None, ''),
        (0x129CE10, 'call 0x129c940', None, 'same curve in builder 0x129CD40'),
        (0x129CFDE, 'call 0x129c940', None, 'same curve in builder 0x129CF10'),
        (0x129D24A, 'call 0x129c940', None, 'same curve in builder 0x129D180 (explosions)'),
        (0x129D728, 'call 0x129c940', None, 'same curve in builder 0x129D660'),
    ],
    'armoryDisplay_0x1915EB0': [
        (0x1915FAB, 'movss xmm8, dword ptr [rip + {rip}]', K_ONE, 'xmm8 = 1.0'),
        (0x1915FBA, 'xorps xmm9, xmm9', None, 'xmm9 = 0'),
        (0x19161A0, 'mov dword ptr [rbp - 0x10], 0x42c80000', None, 'display base 100'),
        (0x19161D0, 'movss xmm7, dword ptr [rip + {rip}]', K_RATING_STEP, '50 per armor unit'),
        (0x19161DC, 'movss xmm6, dword ptr [rip + {rip}]', K_SPEED_STEP, '5'),
        (0x19161FA, 'call 0x11d91b0', None, 'average of table i (i = 0, 1, 2)'),
        (0x1916210, 'mov r8d, 0xafae3b47', None, 'i = 0: armor-rating key'),
        (0x191621C, 'call 0x11da090', None, 'PassiveValue(kit passive)'),
        (0x1916224, 'subss xmm4, xmm8', None, 'ARMOR RATING = 100 + (A - 1) x 50'),
        (0x1916229, 'mulss xmm4, xmm7', None, ''),
        (0x191622D, 'addss xmm4, xmm5', None, ''),
        (0x1916238, 'mulss xmm4, xmm6', None, 'SPEED = 100 x 5 x speed factor'),
        (0x191623C, 'mulss xmm4, xmm5', None, ''),
        (0x1916252, 'subss xmm4, xmm8', None, 'STAMINA REGEN = 100 x (0 - (F - 1) + 1) = 100 x (2 - F)'),
        (0x191625B, 'subss xmm0, xmm4', None, ''),
        (0x191625F, 'addss xmm0, xmm8', None, ''),
        (0x1916264, 'mulss xmm0, xmm5', None, ''),
        (0x14E766E, 'cmp dword ptr [rax + 8], 2', None, 'armory class label (0x14E7430): the TORSO piece'),
        (0x14E7674, 'mov ecx, dword ptr [rax + 0x10]', None, 'its weight'),
    ],
    'otherWriters': [
        (0x8321C2, 'movss dword ptr [rax + r10 + 0x53e900], xmm2', None, '0x832120: stamina factor *= x (status '
            'handler 0x692240 calls it 3 times)'),
        (0x833CE4, 'movss dword ptr [rcx + r10 + 0x546ac4], xmm3', None, '0x833C50: set avatar armor modifier '
            '(status handler 0x692240: -1.0 on apply, 0 on removal; also 0xBB6190)'),
        (0xB70FC3, 'movss dword ptr [rcx + r10 + 0x546ac4], xmm2', None, '0xB70F10 (no static caller): same field'),
    ],
}
DATA_PINS = [
    (T_ARMOR, 12, 'armor table f32[3] {0, 1, 2}'),
    (T_SPEED, 12, 'speed table f32[3] {1.1, 1.0, 0.9}'),
    (T_STAMINA, 12, 'stamina table f32[3] {0.75, 1.0, 1.5}'),
    (T_CURVE, 40, 'player armor damage curve {(3, 0.65), (2, 0.75), (1, 1.0), (0, 1.25), (-1, 1.66)}'),
    (K_ONE, 4, '1.0'), (K_RATING_STEP, 4, '50.0'), (K_SPEED_STEP, 4, '5.0'), (K_MINUS_ONE, 4, '-1.0'),
    (K_THREE, 4, '3.0'), (K_PARTIAL, 4, '0.65'), (T_ZONE_MULTIPLIER, 20, 'zone damage multiplier table'),
]


def sections(data):
    pe = struct.unpack_from('<I', data, 60)[0]
    count = struct.unpack_from('<H', data, pe + 6)[0]
    optional = struct.unpack_from('<H', data, pe + 20)[0]
    at = pe + 24 + optional
    out = []
    for i in range(count):
        name, vsize, va, _, _, _, _, _, _, flags = struct.unpack_from('<8sIIIIIIHHI', data, at + 40 * i)
        out.append({'name': name.rstrip(b'\0').decode().strip() or None, 'rva': '0x%X' % va, 'start': va,
            'size': vsize, 'flags': '0x%08X' % flags, 'writable': bool(flags & 0x80000000)})
    return out


def section_of(table, rva):
    for s in table:
        if s['start'] <= rva < s['start'] + s['size']:
            return {k: v for k, v in s.items() if k != 'start'}
    return None


def f32s(data, rva, count):
    return [round(v, 6) for v in struct.unpack_from('<%df' % count, data, rva)]


# ------------------------------------------------------------------------------------------- game formulas
def kit_pieces(mem, kit):
    out = []
    count = mem.u32(kit + KIT_BODY_COUNT) or 0
    bodies = mem.ptr(kit + KIT_BODIES)
    for b in range(count):
        body = bodies + b * BODY_STRIDE
        btype, pieces, pcount = mem.u32(body + BODY_TYPE), mem.ptr(body + BODY_PIECES), mem.u32(body + BODY_PIECE_COUNT)
        for p in range(pcount or 0):
            piece = pieces + p * PIECE_STRIDE
            out.append({'body': btype, 'slot': mem.u32(piece + PIECE_SLOT), 'type': mem.u32(piece + PIECE_TYPE),
                'weight': mem.u32(piece + PIECE_WEIGHT), 'address': piece})
    return out


def average_ui(pieces, body_type, table):
    """Replica of KitWeightAverage 0x11D91B0 for the armor kit (helmet kit 0): type 0, slot 2..9 except 3."""
    rows = [p for p in pieces if p['body'] in (body_type, 3)][:30]
    picked = [table[p['weight']] for p in rows if p['type'] == 0 and 2 <= p['slot'] <= 9 and p['slot'] != 3
        and p['weight'] < 3]
    return sum(picked) / len(picked) if picked else 0.0


def average_gameplay(pieces, body_type, table):
    """Replica of 0x8774D0 / 0x8777C0: type 0, any slot, weight != 3, default 1.0."""
    rows = [p for p in pieces if p['body'] in (body_type, 3)][:20]
    picked = [table[p['weight']] for p in rows if p['type'] == 0 and p['weight'] != 3]
    return sum(picked) / len(picked) if picked else 1.0


def passive_value(passive, key, base_value):
    value, add, mul = base_value, 0.0, 1.0
    for k, kind, v, _ in passive['modifiers'] if passive else []:
        if k != key:
            continue
        if kind == 0:
            value = v
        elif kind == 1:
            add += v
        elif kind == 2:
            mul *= v
    return (value + add) * mul


def curve(points, x):
    for i, (key, value) in enumerate(points):
        if x >= key:
            if i == 0:
                return value
            k0, v0 = points[i - 1]
            return (min(k0, x) - key) / (k0 - key) * (v0 - value) + value
    return 1.0


def norm(name):
    return re.sub(r'[^A-Z0-9]', '', (name or '').upper())


def observe(name, tables, text, points):
    mem = base.Mem(name)
    out = {'snapshot': name}
    mgr = mem.ptr(mem.game + G_CUSTOMIZATION)
    kit_array, kit_count = struct.unpack('<QI', mem.read(mgr, 12))
    passive_array, passive_count = struct.unpack('<QI', mem.read(mgr + 0x20, 12))
    passives = {}
    for i in range(passive_count):
        p = attributes.read_passive(mem, mem.ptr(passive_array + 8 * i))
        passives[p['id']] = p
    kits = {}
    for i in range(kit_count):
        pointer = mem.ptr(kit_array + 8 * i)
        row = struct.unpack('<IIIIIIIIQI', mem.read(pointer, 0x2C))
        kits[row[0]] = {'pointer': pointer, 'row': row}
    regions = {}
    sample = next(k for k in kits.values() if k['row'][9] == 0)
    for label, address in (('kitObject', sample['pointer']), ('bodies', mem.ptr(sample['pointer'] + KIT_BODIES)),
            ('pieces', mem.ptr(mem.ptr(sample['pointer'] + KIT_BODIES) + BODY_PIECES))):
        region = mem.s.region(address)
        regions[label] = {'protect': '0x%X' % region['protect'], 'type': '0x%X' % region['type'],
            'allocationBase': '0x%X' % region['allocation_base']}
    out['kitMemory'] = regions
    # Every armor kit: the game's formulas over its pieces.
    census = []
    for kid, kit in kits.items():
        row = kit['row']
        if row[9] != 0:
            continue
        pieces = kit_pieces(mem, kit['pointer'])
        passive = passives.get(row[7])
        entry = {'id': '%08X' % kid, 'name': text(row[4]) or text(row[3]), 'passive': row[7],
            'passiveName': text(passive['name']) if passive else None, 'bodyTypes': sorted({p['body'] for p in pieces})}
        per_body = {}
        for body_type in (0, 1):
            a = average_ui(pieces, body_type, tables['armor'])
            armor_value = passive_value(passive, 0xAFAE3B47, a)
            speed_ui, stamina_ui = average_ui(pieces, body_type, tables['speed']), average_ui(pieces, body_type,
                tables['stamina'])
            per_body[body_type] = {
                'weights': {SLOTS[p['slot']] if p['slot'] < len(SLOTS) else p['slot']: WEIGHTS[p['weight']]
                    if p['weight'] < 3 else p['weight'] for p in pieces if p['body'] in (body_type, 3) and p['type'] == 0},
                'armorBase': round(a, 6), 'armorValue': round(armor_value, 6),
                'displayRating': round(100 + (armor_value - 1) * 50, 4),
                'displaySpeed': round(500 * speed_ui, 4), 'displayStamina': round(100 * (2 - stamina_ui), 4),
                'displaySpeedFactor': round(speed_ui, 6), 'displayStaminaFactor': round(stamina_ui, 6),
                'gameplaySpeedFactor': round(average_gameplay(pieces, body_type, tables['speed']), 6),
                'gameplayStaminaFactor': round(average_gameplay(pieces, body_type, tables['stamina']), 6),
                'damageMultiplier': round(curve(points, armor_value), 6),
                'torsoWeight': next((WEIGHTS[p['weight']] for p in pieces if p['body'] in (body_type, 3)
                    and p['type'] == 0 and p['slot'] == 2 and p['weight'] < 3), None)}
        entry['stats'] = per_body[0]
        entry['bodyTypesAgree'] = {k: v for k, v in per_body[0].items() if k != 'weights'} == \
            {k: v for k, v in per_body[1].items() if k != 'weights'}
        census.append(entry)
    out['armorKits'] = census
    # The local player: computed vs the live values the game stored.
    pairs, _ = attributes.hashmap(mem, mgr + attributes.M_MAP)
    avatar = mem.ptr(mem.game + G_AVATAR)
    avatars, _ = attributes.hashmap(mem, avatar + 0xF8)
    loco = mem.ptr(mem.game + G_LOCOMOTION)
    loco_pairs, _ = attributes.hashmap(mem, loco + 0x20)
    loco_records = mem.ptr(loco + LOCO_RECORDS)
    players = []
    for entity, record in pairs:
        applied = mem.read(mgr + attributes.M_APPLIED + record * attributes.APPLIED_STRIDE, attributes.APPLIED_STRIDE)
        body_type, armor_kit = struct.unpack_from('<I', applied, 0)[0], struct.unpack_from('<I', applied, 0x0C)[0]
        kit = kits.get(armor_kit)
        pieces = kit_pieces(mem, kit['pointer']) if kit else []
        passive = passives.get(kit['row'][7]) if kit else None
        a = passive_value(passive, 0xAFAE3B47, average_ui(pieces, body_type, tables['armor']))
        row = {'entity': '0x%X' % entity, 'bodyType': body_type, 'armorKit': '%08X' % armor_kit,
            'armorKitName': (text(kit['row'][4]) or text(kit['row'][3])) if kit else None, 'computed': {
                'armorValue': round(a, 6), 'damageMultiplier': round(curve(points, a), 6),
                'speedFactor': round(average_gameplay(pieces, body_type, tables['speed']), 6),
                'staminaFactor': round(average_gameplay(pieces, body_type, tables['stamina']), 6)}, 'avatars': []}
        for avatar_entity, slot in avatars:
            loco_index = dict(loco_pairs).get(avatar_entity)
            loco_row = struct.unpack('<13f', mem.read(loco_records + loco_index * LOCO_STRIDE, LOCO_STRIDE)) \
                if loco_index is not None else None
            row['avatars'].append({'avatar': '0x%X' % avatar_entity,
                'staminaFactor_0x53E900': round(struct.unpack('<f', mem.read(avatar + AVATAR_STAMINA_FACTOR + slot *
                    AVATAR_STRIDE_SIM, 4))[0], 6),
                'armorModifier_0x546AC4': round(struct.unpack('<f', mem.read(avatar + AVATAR_ARMOR_MODIFIER + slot *
                    AVATAR_STRIDE_STATE, 4))[0], 6),
                'locomotionSlots0to4': [round(v, 6) for v in loco_row[:5]] if loco_row else None,
                'locomotionCurrent_0x14': round(loco_row[5], 6) if loco_row else None})
        players.append(row)
    out['players'] = players
    out['otherLocomotionRecordsSlot3'] = sorted({round(struct.unpack('<f', mem.read(loco_records + i * LOCO_STRIDE + 12,
        4))[0], 6) for _, i in loco_pairs if i is not None})
    mem.close()
    return out


def wiki_compare(census):
    if not WIKI.is_file():
        return None
    wiki = json.loads(WIKI.read_text(encoding='utf-8'))
    body = {norm(a['name']): a for a in wiki['armors'] if a['slot'] == 'Body'}
    rows, mismatches = [], []
    for kit in census:
        w = body.get(norm(kit['name']))
        if not w:
            continue
        s = kit['stats']
        listed = {k: (w.get(k) or {}).get('value') for k in ('armorRating', 'speed', 'staminaRegen')}
        game = {'armorRating': round(s['displayRating']), 'speed': round(s['displaySpeed']),
            'staminaRegen': round(s['displayStamina'] + 1e-9)}
        ok = all(listed[k] is None or abs(listed[k] - game[k]) < 0.6 for k in listed)
        rows.append({'name': kit['name'], 'class': w.get('class'), 'torsoWeight': s['torsoWeight'], 'wiki': listed,
            'game': game, 'match': ok})
        if not ok:
            mismatches.append(rows[-1])
    return {'matched': len(rows), 'agree': sum(1 for r in rows if r['match']),
        'classLabelEqualsTorsoWeight': sum(1 for r in rows if (r['class'] or '').lower() == r['torsoWeight']),
        'mismatches': mismatches, 'nonTierRows': [r for r in rows if r['game']['armorRating'] % 50 or
            r['game']['speed'] % 50]}


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PINS.items()}
    data_pins = [{'rva': rva, 'bytes': data[rva:rva + size].hex(), 'role': role} for rva, size, role in DATA_PINS]
    pins = [p for rows in proofs.values() for p in rows] + data_pins
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    code = attributes.Code(image)
    table = sections(data)
    tables = {'armor': f32s(data, T_ARMOR, 3), 'speed': f32s(data, T_SPEED, 3), 'stamina': f32s(data, T_STAMINA, 3)}
    raw_curve = f32s(data, T_CURVE, 10)
    points = [(raw_curve[2 * i], raw_curve[2 * i + 1]) for i in range(5)]
    text = attributes.text_lookup()

    readers = {}
    for name, rva in (('armor', T_ARMOR), ('speed', T_SPEED), ('stamina', T_STAMINA), ('curve', T_CURVE)):
        sites = set()
        packed = struct.pack('<I', rva)
        start = base.TEXT[0]
        while True:  # image-relative disp32 uses ([base + reg*4 + table])
            at = data.find(packed, start, base.TEXT[1])
            if at < 0:
                break
            start = at + 1
            for back in range(3, 9):
                insn = next(image.md.disasm(data[at - back:at - back + 15], at - back), None)
                if insn and insn.address + insn.size == at + 4 and ('0x%x' % rva) in insn.op_str:
                    sites.add('0x%X' % code.function_of(insn.address))
                    break
        hits = (code.index + 4 + code.disp) == rva
        for i in hits.nonzero()[0]:  # rip-relative
            insn = next((x for back in range(2, 8) for x in [next(image.md.disasm(data[int(i) - back:int(i) - back + 15],
                int(i) - back), None)] if x and x.address + x.size == int(i) + 4), None)
            if insn:
                sites.add('0x%X' % code.function_of(insn.address))
        readers[name] = sorted(sites)
    callers = {'0x%X' % f: sorted({'0x%X' % code.function_of(s) for s, _ in code.calls_to(f)})
        for f in (F_AVERAGE, F_STAMINA_FACTOR, F_SPEED_FACTOR, F_APPLY, F_SET_SPEED_SLOT, F_SPEED_PRODUCT,
            F_SPEED_SMOOTH, F_CURVE, 0x878160, 0x877710, 0x877A00, 0x833C50, 0x832120)}

    observations = [observe(name, tables, text, points) for name in SNAPSHOTS]
    first = next(o for o in observations if o['armorKits'])
    census = first['armorKits']
    consistent = all(o['armorKits'] == census for o in observations if o['armorKits'])
    comparison = wiki_compare(census)
    differs = [k['name'] or k['id'] for k in census if k['stats']['displaySpeedFactor'] !=
        k['stats']['gameplaySpeedFactor'] or k['stats']['displayStaminaFactor'] != k['stats']['gameplayStaminaFactor']]
    by_weight = {}
    for kit in census:
        key = tuple(sorted(set(kit['stats']['weights'].values()), key=str))
        by_weight[str(key)] = by_weight.get(str(key), 0) + 1

    document = {
        'schemaVersion': 1,
        'build': 'F5FEE03DCFDB',
        'generatedBy': 'scripts/research_armor_stats.py',
        'gameDll': base.PROFILE_DLL_SHA,
        'pins': proofs,
        'dataPins': data_pins,
        'pinCount': len(pins),
        'pinnedBytesMismatchPerSnapshot': relocation,
        'tables': {
            'armor': {'rva': '0x%X' % T_ARMOR, 'values': tables['armor'], 'section': section_of(table, T_ARMOR)},
            'speed': {'rva': '0x%X' % T_SPEED, 'values': tables['speed'], 'section': section_of(table, T_SPEED)},
            'stamina': {'rva': '0x%X' % T_STAMINA, 'values': tables['stamina'], 'section': section_of(table, T_STAMINA)},
            'damageCurve': {'rva': '0x%X' % T_CURVE, 'points': points, 'section': section_of(table, T_CURVE),
                'rangeGetters': {'0x129C9B0': 'key range (-1, 3)', '0x129C9D0': 'value range (0.65, 1.66)'}},
            'indexedBy': 'piece weight 0 light / 1 medium / 2 heavy (filediver CustomizationKitWeight, lead; the '
                'code indexes the tables with piece +0x10)',
            'readerFunctions': readers,
            'readerNote': 'image-relative disp32 and rip-relative references; 0x11D8C80 = the getters 0x11D9130 / '
                '0x11D9140 / 0x11D9150 / 0x11D9160 (no static callers); 0x129C7C0 = the curve 0x129C940 (no own '
                'unwind entry)',
        },
        'callers': callers,
        'layouts': {
            'kit': {'0x1C': 'u32 passive id', '0x28': 'u32 type (0 armor)', '0x30': 'Body *bodies',
                '0x38': 'u32 body count'},
            'body': {'stride': '0x18', '0x00': 'u32 body type (0 stocky, 1 slim, 3 any: lead names)',
                '0x08': 'Piece *pieces', '0x10': 'u32 piece count'},
            'piece': {'stride': '0x60', '0x08': 'u32 slot (0 helmet, 2 torso, 3 hips, 4..9 legs/arms/shoulders: '
                'lead names)', '0x0C': 'u32 piece type (0 armor)', '0x10': 'u32 WEIGHT (0 light, 1 medium, 2 heavy)'},
            'appliedRecord': {'0x00': 'u32 body type (passed to every averager)', '0x0C': 'u32 armor kit id'},
            'avatarManager': {'0x53E900 + i x 0x1238': 'f32 stamina factor (written by 0x877AB0; read by regen, '
                'sprint drain and the jump / dive / climb / slide costs)',
                '0x546AC4 + i x 0x1B8': 'f32 armor modifier (added to the armor value of hits on this avatar and '
                    'clamped to [-1, 3] when not 0)'},
            'locomotionRecord': {'manager': '0x%X' % G_LOCOMOTION, 'records': 'manager +0x48, 13 floats per entity',
                '0x00..0x10': 'five speed-multiplier slots (product = 0x9CCC20); slot 3 = armor, slot 4 = written by '
                    'the avatar movement 0xA6C700, slot 0 = 0x11234D0 / 0x1123560 / 0x11A8860, slot 1 multiplied by '
                    '0x9CCA30', '0x14': 'current multiplier, smoothed toward the product (0x7C6CE0)'},
        },
        'formulas': {
            'armorValue': 'A = PassiveValue(armorKit.passive, AFAE3B47, mean over the armor kit\'s type-0 pieces in '
                'slots 2..9 except 3 of armorTable[weight]) = ((Set or mean) + sum Add) x prod Mul. Extra Padding '
                'Add 1.0, Unflinching / Supplementary Adrenaline / Blunt-Force Mitigation Add 0.5, Concussive Padding '
                'Reinforced Add 0.6.',
            'displayedRating': '100 + (A - 1) x 50  (light 50, medium 100, heavy 150, heavy + Extra Padding 200)',
            'playerDamage': 'damage x curve(A + avatar modifier) x zone multiplier; curve keys (3, 0.65) (2, 0.75) '
                '(1, 1.0) (0, 1.25) (-1, 1.66), linear between, 0.65 above 3, 1.0 below -1. The attack\'s penetration '
                'is NOT part of the player multiplier (it is for every other target: pen - armor >= 1 x1, 0..1 '
                'x0.65, < 0 x0). Hit kind 0x8C5570C9 is never reduced below x1.',
            'speedFactor': 'S = mean over type-0 pieces (any slot, weight != 3) of speedTable[weight]; written to '
                'locomotion speed slot 3; displayed SPEED = 500 x S (UI averages slots 2..9 except 3)',
            'staminaFactor': 'F = same mean of staminaTable[weight]; written to avatar +0x53E900. Regen: stamina += '
                'F x (1.3) x effects / recover_time x dt. Sprint drain: stamina -= F / sprint_decay x dt / ((1.3) x '
                'effects). Jump / dive / climb / slide cost x F. Displayed STAMINA REGEN = 100 x (2 - F).',
            'wikiFormulasExplained': 'With A = rating/50 - 1: wiki "Speed = 600 - rating" and "stamina 150 - '
                'rating/2 / 200 - rating" are the light/medium/heavy table values blended by the piece mix; '
                '"damage = 1.5 - rating/200 (<= 150) / 1.05 - rating/500" is the curve.',
        },
        'snapshots': [{k: v for k, v in o.items() if k != 'armorKits'} for o in observations],
        'armorKitCensus': census,
        'armorKitCensusIdenticalInAllSnapshots': consistent,
        'weightMixes': by_weight,
        'displayVsGameplay': {'kitsWhoseGameplayFactorsDifferFromTheDisplay': len(differs), 'kits': differs,
            'why': 'the armory averages slots 2..9 except hips (0x11D91B0); the gameplay factors average every type-0 '
                'piece, so the hips and the armor kit own cape-slot piece (weight medium on most non-medium kits) '
                'pull the real factor toward medium (heavy 0.9 -> 0.911, light 1.1 -> 1.089)'},
        'wikiComparison': comparison,
        'verdicts': {
            'source': 'every displayed stat is derived from the PIECE WEIGHTS of the armor kit (piece +0x10, 0..2) '
                'through three per-weight f32[3] tables in game.dll .rdata, plus the kit passive for the rating. No '
                'kit has its own rating / speed / stamina number.',
            'perArmorVsPerClass': 'both exist: the three tables are per weight class (one edit changes every armor '
                'with that weight); the piece weights are per kit (an edit changes one armor, in steps of 1/n where n '
                'is the number of counted pieces, 5..9). Per-player live values also exist (below).',
            'liveness': {
                'armorTableAndCurve': 'read on every hit (InitHitInfo -> 0x11D91B0; damage builders -> 0x129C940): '
                    'LIVE',
                'speedAndStaminaTables': 'read only by 0x877AB0 when a kit change is applied or the avatar side '
                    'calls it (0x81BE70): SPAWN / next apply; the UI reads all three when it draws',
                'avatarStaminaFactor': 'avatar +0x53E900 is read every frame (regen, drain, action costs): LIVE until '
                    'the next 0x877AB0; status handler 0x692240 also multiplies it (0x832120)',
                'locomotionSlot3': 'LIVE value in the locomotion record (smoothed into +0x14); overwritten at the next '
                    '0x877AB0. The consumer of +0x14 was not found statically',
                'avatarArmorModifier': 'avatar +0x546AC4 is read on every hit: LIVE; status handler 0x692240 writes '
                    '-1 / 0 on apply / removal',
            },
            'memory': 'tables: game.dll read-only initialized-data section at 0x2111000 (flags 0x40000040, not '
                'writable; shared by every kit and every player on this machine). Kits, bodies and pieces: one private '
                'PAGE_READWRITE allocation (snapshots[].kitMemory, protect 0x4; the kit rows equal the filediver '
                'armor-sets lead per the player-attributes research); writable without VirtualProtect',
        },
        'recommendedApi': {
            'hd2.armor_class(name)': {'fields': {
                'rating': {'storage': 'armor table [w] (value A units; rating = 50 + 50 x A)', 'verdict': 'WRITABLE_LIVE'
                    ' (needs an image .rdata write: VirtualProtect, a new guard class)', 'range': 'A -1..4 (rating 0..250)'},
                'speed': {'storage': 'speed table [w] (factor; display 500 x f)', 'verdict': 'SPAWN (applied at the '
                    'next kit apply / respawn)', 'range': '0.5..1.5'},
                'stamina': {'storage': 'stamina table [w] (factor F; display 100 x (2 - F))', 'verdict': 'SPAWN',
                    'range': '0.25..2.0 (F scales drain AND regen)'}},
                'scope': 'every armor whose pieces have that weight, every player simulated or hit on this machine'},
            'hd2.armor_kit(id)': {'fields': {'weight': {'storage': 'piece +0x10 of every type-0 piece (or per slot)',
                'verdict': 'SPAWN for speed / stamina, LIVE for rating; also changes the armory class label (torso)',
                'range': '0..2'}}, 'scope': 'one armor, every player wearing it; discrete'},
            'hd2.player_armor (per player, development)': {'fields': {
                'armor_bonus': {'storage': 'avatar +0x546AC4', 'verdict': 'WRITABLE_LIVE (STRONG): the key becomes '
                    'clamp(A + bonus, -1, 3); a status effect can overwrite it', 'range': '-4..3'},
                'stamina_factor': {'storage': 'avatar +0x53E900', 'verdict': 'WRITABLE_LIVE until the next apply / '
                    'respawn; re-apply after 0x877AB0', 'range': '0.1..3'},
                'speed_factor': {'storage': 'locomotion slot 3 of the avatar', 'verdict': 'UNKNOWN (consumer of the '
                    'smoothed product not proven)', 'range': '0.5..1.5'}}},
        },
        'unproven': [
            'everything live (offline only)',
            'the consumer of the locomotion multiplier product (+0x14): no static caller of 0x9CCC20 / 0x7C6CE0 was '
            'found, so how S scales the AvatarComponentData speeds (jog 3.2 x 1.1?) is not proven',
            'which machine evaluates hits on a remote player (the armor value comes from the hit machine\'s '
            'customization record of that player)',
            'what the 0x877AB0 caller 0x81BE70 is (spawn?) and whether 0x874520 calls it for every respawn',
            'the status effect behind the -1 armor modifier (switch case at 0x6925F2 of 0x692240) and the type-0x33 '
            'effect multiplying stamina (0x11DE2A0)',
            'body type names (0 stocky / 1 slim / 3 any are filediver leads)',
            'ExertionLevelInfo (+340..+388) is unrelated: indexed by the exertion level +0x546AE4 (0x83495B)',
        ],
        'writes': [],
    }
    OUTPUT.write_text(json.dumps(document, indent=1, allow_nan=False) + '\n', encoding='utf-8')
    print('wrote', OUTPUT, 'pins', len(pins))
    print('tables', tables, 'curve', points)
    print('wiki', {k: v for k, v in (comparison or {}).items() if k not in ('nonTierRows',)})
    for o in observations:
        print(o['snapshot'][-40:], o.get('kitMemory'), [(p['armorKitName'], p['computed'], p['avatars'])
            for p in o['players']])


if __name__ == '__main__':
    main()
