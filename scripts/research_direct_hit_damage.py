"""Direct-hit damage of a projectile: the damage event 0x12A25B0 builds, where the standard / durable choice is made,
and what the per-shot hit-record members (+0x34 damage multiplier, +0x24..+0x30 additive bonuses) scale. Read-only,
offline, build F5FEE03DCFDB, game.dll image of a retained snapshot plus every retained snapshot.

Chain of one direct hit (hit processing in the projectile system, r14 = the shot's hit record system+0x4D040+N*0xC8):

  0x13AD29B   source struct s = [rbp+0x4E0]: s+0x24 = hit +0x0C (the DamageInfo id); lanes = float(hit +0x18..+0x1E)
  0x13AD4E8   BuildHitEvent 0x12A25B0(ctx, event=[rbp+0x580], r8=[rbp+0x1A0], s, pos, hit+0x10, speedFactor,
              lanes*, &hit+0x24, &hit+0x2C, kind = (hit +0x98 > 0))
    0x12A25C4   event zeroed, 0x118 bytes
    0x12A2669   InitHitInfo 0x12A15E0(..., event, kind, hit+0x10, r8, s, pos):
      0x12A1E7E   D = event +0x4C = hit zone +0xCC (the zone's durable fraction; zone = 0x922060(settings, node));
                  D = 0 when the target has no zone (0x12A1AFE / 0x12A1C15 / 0x12A23F0)
      0x12A1C29   s+0x24 (the DamageInfo id) -> row = [0x37C60C0 + id*8] (0x12A23FD; id 0 -> default row 0x37C7510)
      0x12A2479   event +0x98 = row+0x04 (standard) x (1 - D) + row+0x08 (durable) x D        <- THE CHOICE
                  event +0x04 = row+0x28, +0xAC/+0xB0/+0xB4 = float(row +0x20/+0x1C/+0x24), +0xC0..+0xDF = row
                  +0x2C..+0x4B (statuses); the id itself is NOT stored in the event
    0x12A26D9   event +0x98 += hit+0x2C x (1 - D) + hit+0x30 x D     (per-shot additive standard / durable damage)
    0x12A269E   event +0x94 = speed factor (0.25 + 0.75 (|v|/ref)^2; 1.0 unit-driven)
    0x12A26FF.. event +0x9C..+0xA8 = max(0, float(hit lane i) + hit+0x24 x (1 - D) + hit+0x28 x D)
  0x13AD524   event +0x98 x= hit +0x34 (the per-shot damage multiplier)  -> scales the BLEND (standard and durable)
  0x13AD550   event lanes x= hit +0x38, rounded
  0x13AD7C8   DamageValues 0x129DC30 -> kind 0/1 builder 0x129C9F0:
                values+0x00 = round(max(0, A x event+0x98 x event+0x94)) x relation[event+0x6C]
                A = 1.0 (pen - zone armor >= 1), 0.65 (0 <= .. < 1), 0 (< 0); pen = an event lane picked by angle
  0x13AD88B   ProduceDamage 0x129DD30: queue-0 entry +0x2C = trunc(values+0x00 [x an entity attribute for zone
              hash 0xAA1DB0B0]); consumed by 0x12A7D40: ApplyDamage(amount) and the dealt_damage stat (0x12A0F50,
              amount unchanged, -1 = kill sentinel)

No consumer after 0x12A15E0 re-reads the DamageInfo row: the event carries no id, the only rip-relative references to
the table are the 10 listed in `census.tableReferences` (loader, clear, getter 0x11F8EA0, InitHitInfo, SpawnProjectile,
two non-projectile systems), and the getter has no caller in the functions reachable from the builders / producer /
consumer (`census.reachability`).

Output: research/direct-hit-damage-F5FEE03DCFDB.json.   py scripts/research_direct_hit_damage.py
"""
from __future__ import annotations

import collections
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/direct-hit-damage-F5FEE03DCFDB.json'
DAMAGE_TABLE, DAMAGE_STRIDE, DAMAGE_DEFAULT = 0x37C60C0, 0x4C, 0x37C7510
DAMAGE_GETTER = 0x11F8EA0
SYSTEM_GLOBAL = 0x347CEA8
SETTINGS_ROOT = 0x346BF98            # [root + 0xF12B78] = shared HealthComponentData hash (0x507430)
LIBERATOR_DAMAGE = 108               # AR-23 Liberator round's DamageInfo (live probe 2026-10-07)
RELATION_TABLE = 0x21CF898

# (rva, asm, rip target or None, role)
PROOFS = {
    'hitSite': [
        (0x13AD29B, 'mov eax, dword ptr [r14 + 0xc]', None, 'hit +0x0C DamageInfo id ...'),
        (0x13AD29F, 'mov dword ptr [rbp + 0x504], eax', None, '... into the source struct s (rbp+0x4E0) +0x24'),
        (0x13AD31E, 'movzx eax, word ptr [r14 + 0x18]', None, 'hit +0x18 AP lane 0 ...'),
        (0x13AD348, 'movss dword ptr [rbp + 0x6b0], xmm0', None, '... as a float into lanes[0] (rbp+0x6B0)'),
        (0x13AD484, 'cmp dword ptr [r14 + 0x98], 0', None, 'hit +0x98 > 0 ...'),
        (0x13AD48C, 'lea rcx, [r14 + 0x2c]', None, '&hit +0x2C (additive damage pair) -> argument 10'),
        (0x13AD490, 'lea rdx, [r14 + 0x24]', None, '&hit +0x24 (additive penetration pair) -> argument 9'),
        (0x13AD494, 'setg al', None, '... -> argument 11, the event kind (0 or 1)'),
        (0x13AD497, 'lea r9, [rbp + 0x4e0]', None, 'argument 4: the source struct s'),
        (0x13AD4AE, 'lea rax, [rbp + 0x6b0]', None, 'argument 8: the float lanes'),
        (0x13AD4C1, 'lea rdx, [rbp + 0x580]', None, 'argument 2: the event'),
        (0x13AD4CD, 'mov eax, dword ptr [r14 + 0x10]', None, 'argument 6: hit +0x10'),
        (0x13AD4D1, 'movss dword ptr [rsp + 0x30], xmm10', None, 'argument 7: the speed factor'),
        (0x13AD4E8, 'call 0x12a25b0', None, 'BuildHitEvent'),
        (0x13AD506, 'movss xmm0, dword ptr [rbp + 0x618]', None, 'event +0x98 (the blended damage) ...'),
        (0x13AD524, 'mulss xmm0, dword ptr [r14 + 0x34]', None, '... x hit +0x34 ...'),
        (0x13AD533, 'movss dword ptr [rbp + 0x618], xmm0', None, '... stored back (no other write to it before 0x129DC30)'),
        (0x13AD550, 'movss xmm0, dword ptr [r14 + 0x38]', None, 'hit +0x38 x each event lane'),
        (0x13AD7BA, 'lea r8, [rbp + 0x580]', None, 'the event ...'),
        (0x13AD7C1, 'lea rdx, [rbp + 0x540]', None, '... -> damage values at rbp+0x540'),
        (0x13AD7C8, 'call 0x129dc30', None, 'DamageValues'),
        (0x13AD858, 'test byte ptr [rax + 0xfc], 1', None, 'ProjectileInfo +0xFC bit 0 ...'),
        (0x13AD869, 'mov dword ptr [rbp + 0x3e4], 0x3f800000', None, '... forces values +0x04 (armour factor) to 1.0'),
        (0x13AD884, 'lea rdx, [rbp + 0x3e0]', None, 'the (copied) damage values ...'),
        (0x13AD88B, 'call 0x129dd30', None, '... ProduceDamage'),
    ],
    'spawnBonusCopies': [
        (0x13AA943, 'mov eax, dword ptr [rdx + 0x54]', None, 'source component record +0x54 ...'),
        (0x13AA946, 'mov dword ptr [rdi + 0x24], eax', None, '... hit +0x24 (penetration bonus, standard weight)'),
        (0x13AA94F, 'mov eax, dword ptr [rdx + 0x58]', None, 'source component record +0x58 ...'),
        (0x13AA952, 'mov dword ptr [rdi + 0x28], eax', None, '... hit +0x28 (penetration bonus, durable weight)'),
        (0x13AA949, 'mov eax, dword ptr [rdx + 0x5c]', None, 'source component record +0x5C ...'),
        (0x13AA94C, 'mov dword ptr [rdi + 0x2c], eax', None, '... hit +0x2C (damage bonus, standard weight)'),
        (0x13AA955, 'mov eax, dword ptr [rdx + 0x60]', None, 'source component record +0x60 ...'),
        (0x13AA958, 'mov dword ptr [rdi + 0x30], eax', None, '... hit +0x30 (damage bonus, durable weight)'),
    ],
    'buildHitEvent': [
        (0x12A25C4, 'movups xmmword ptr [rdx], xmm0', None, 'event zeroed from +0x00 ...'),
        (0x12A264A, 'mov dword ptr [rdx + 0x114], eax', None, '... to +0x117: the event is 0x118 bytes'),
        (0x12A25D9, 'movzx r8d, byte ptr [rsp + 0xa0]', None, 'argument 11 (kind) -> InitHitInfo r8 (event +0x00)'),
        (0x12A265F, 'mov r9d, dword ptr [rsp + 0x78]', None, 'argument 6 (hit +0x10) -> InitHitInfo r9 (event +0x0C)'),
        (0x12A265A, 'mov qword ptr [rsp + 0x28], r9', None, 'the source struct s -> InitHitInfo argument 6'),
        (0x12A2669, 'call 0x12a15e0', None, 'InitHitInfo: DamageInfo row and hit zone -> event'),
        (0x12A266E, 'movss xmm4, dword ptr [rbx + 0x4c]', None, 'D = event +0x4C ...'),
        (0x12A2681, 'movss xmm3, dword ptr [rip + {rip}]', 0x23C6D70, '... 1.0 ...'),
        (0x12A2691, 'subss xmm3, xmm4', None, '... (1 - D)'),
        (0x12A2689, 'mov rax, qword ptr [rsp + 0x98]', None, 'argument 10 = &hit +0x2C'),
        (0x12A2695, 'movss xmm0, dword ptr [rsp + 0x80]', None, 'argument 7 (speed factor) ...'),
        (0x12A269E, 'movss dword ptr [rbx + 0x94], xmm0', None, '... event +0x94'),
        (0x12A26A6, 'mov dword ptr [rbx + 0xb8], edi', None, 'event +0xB8 = 0'),
        (0x12A26AC, 'mov dword ptr [rbx + 0xbc], 0x3f800000', None, 'event +0xBC = 1.0'),
        (0x12A26B6, 'mulss xmm1, dword ptr [rax + 4]', None, 'D x hit +0x30 ...'),
        (0x12A26BE, 'mulss xmm0, dword ptr [rax]', None, '... + (1 - D) x hit +0x2C ...'),
        (0x12A26D1, 'addss xmm1, dword ptr [rbx + 0x98]', None, '... + event +0x98 (the row blend) ...'),
        (0x12A26D9, 'movss dword ptr [rbx + 0x98], xmm1', None, '... event +0x98'),
        (0x12A2676, 'mov rcx, qword ptr [rsp + 0x90]', None, 'argument 9 = &hit +0x24'),
        (0x12A26C2, 'mov rax, qword ptr [rsp + 0x88]', None, 'argument 8 = the hit\'s float lanes'),
        (0x12A26E4, 'mulss xmm0, dword ptr [rcx]', None, '(1 - D) x hit +0x24 ...'),
        (0x12A26E8, 'mulss xmm1, dword ptr [rcx + 4]', None, '... + D x hit +0x28 ...'),
        (0x12A26F4, 'addss xmm1, dword ptr [rax]', None, '... + the hit\'s lane 0 ...'),
        (0x12A26F8, 'maxss xmm0, xmm1', None, '... at least 0 ...'),
        (0x12A26FF, 'movss dword ptr [rbx + 0x9c], xmm0', None, '... event +0x9C (lanes +0xA0/+0xA4/+0xA8 alike)'),
        (0x12A276B, 'movss dword ptr [rbx + 0xa8], xmm2', None, 'event +0xA8: lane 3'),
    ],
    'initHitInfo': [
        (0x12A15FA, 'mov rcx, qword ptr [rsp + 0x98]', None, 'argument 6: the source struct s'),
        (0x12A1610, 'mov dword ptr [rdx], r8d', None, 'event +0x00 = kind'),
        (0x12A1616, 'mov dword ptr [rdx + 0xc], r9d', None, 'event +0x0C = hit +0x10'),
        (0x12A161A, 'mov edi, dword ptr [rcx + 0xc]', None, 's +0x0C ...'),
        (0x12A161D, 'mov dword ptr [rdx + 0x18], edi', None, '... event +0x18'),
        (0x12A1620, 'mov eax, dword ptr [rcx + 0x1c]', None, 's +0x1C (the hit node) ...'),
        (0x12A1623, 'mov dword ptr [rdx + 0x24], eax', None, '... event +0x24'),
        (0x12A1626, 'mov eax, dword ptr [rcx + 0x20]', None, 's +0x20 ...'),
        (0x12A1629, 'mov dword ptr [rdx + 0x1c], eax', None, '... event +0x1C'),
        (0x12A162C, 'movsd xmm0, qword ptr [rcx + 0x10]', None, 's +0x10 vec3 ...'),
        (0x12A1631, 'movsd qword ptr [rdx + 0x28], xmm0', None, '... event +0x28 (the hit direction, angle test)'),
        (0x12A163C, 'movsd xmm0, qword ptr [rcx]', None, 's +0x00 vec3 ...'),
        (0x12A1640, 'movsd qword ptr [rdx + 0x34], xmm0', None, '... event +0x34'),
        (0x12A16A4, 'mov dword ptr [r14 + 0x20], eax', None, 'event +0x20: the target entity'),
        (0x12A16A8, 'mov dword ptr [r14 + 0x6c], 2', None, 'event +0x6C = 2: relation index (x1.0) by default'),
        (0x12A1AFE, 'mov dword ptr [r14 + 0x4c], r15d', None, 'D = 0 (no hit zone)'),
        (0x12A1C15, 'mov dword ptr [r14 + 0x4c], r15d', None, 'D = 0 (no hit zone)'),
        (0x12A1E06, 'mov ecx, dword ptr [r14 + 0x24]', None, 'the hit node (event +0x24) ...'),
        (0x12A1E61, 'call 0x922060', None, '... ZoneOf(settings, node): the hit zone'),
        (0x12A1E71, 'mov ecx, dword ptr [rax + 0x60]', None, 'zone +0x60 (zone name hash) ...'),
        (0x12A1E74, 'mov dword ptr [r14 + 0x7c], ecx', None, '... event +0x7C'),
        (0x12A1E78, 'mov ecx, dword ptr [rax + 0xcc]', None, 'zone +0xCC: the durable fraction D ...'),
        (0x12A1E7E, 'mov dword ptr [r14 + 0x4c], ecx', None, '... event +0x4C'),
        (0x12A1E82, 'mov ecx, dword ptr [rax + 0xd8]', None, 'zone +0xD8 (armour) ...'),
        (0x12A1E8D, 'movss dword ptr [r14 + 0x50], xmm0', None, '... as a float into event +0x50'),
        (0x12A1C21, 'mov rbx, qword ptr [rsp + 0x98]', None, 'the source struct s ...'),
        (0x12A1C29, 'mov eax, dword ptr [rbx + 0x24]', None, '... s +0x24 = the hit\'s DamageInfo id (its only read)'),
        (0x12A1C2C, 'test eax, eax', None, 'id 0 ...'),
        (0x12A1C34, 'lea rcx, [rip + {rip}]', DAMAGE_DEFAULT, '... the default DamageInfo row'),
        (0x12A23FD, 'lea rcx, [rip + {rip}]', DAMAGE_TABLE, 'the DamageInfo pointer table ...'),
        (0x12A2404, 'mov rcx, qword ptr [rcx + rax*8]', None, '... row = table[id]'),
        (0x12A2408, 'mov eax, dword ptr [rcx + 0x28]', None, 'row +0x28 ...'),
        (0x12A240E, 'mov dword ptr [r14 + 4], eax', None, '... event +0x04'),
        (0x12A2415, 'mov eax, dword ptr [rcx + 0x1c]', None, 'row +0x1C -> float event +0xB0'),
        (0x12A2429, 'mov eax, dword ptr [rcx + 0x20]', None, 'row +0x20 -> float event +0xAC'),
        (0x12A243A, 'mov eax, dword ptr [rcx + 0x24]', None, 'row +0x24 -> float event +0xB4'),
        (0x12A2453, 'movups xmm0, xmmword ptr [rcx + 0x2c]', None, 'row +0x2C..+0x3B (statuses) -> event +0xC0'),
        (0x12A245F, 'movups xmm1, xmmword ptr [rcx + 0x3c]', None, 'row +0x3C..+0x4B (statuses) -> event +0xD0'),
        (0x12A2463, 'movss xmm0, dword ptr [rip + {rip}]', 0x23C6D70, '1.0 ...'),
        (0x12A246B, 'subss xmm0, dword ptr [r14 + 0x4c]', None, '... - D'),
        (0x12A2479, 'movd xmm3, dword ptr [rcx + 4]', None, 'row +0x04 STANDARD damage ...'),
        (0x12A247E, 'movd xmm1, dword ptr [rcx + 8]', None, 'row +0x08 DURABLE damage ...'),
        (0x12A2489, 'mulss xmm1, dword ptr [r14 + 0x4c]', None, 'durable x D ...'),
        (0x12A248F, 'mulss xmm3, xmm0', None, 'standard x (1 - D) ...'),
        (0x12A2496, 'addss xmm3, xmm1', None, '... summed ...'),
        (0x12A249D, 'movss dword ptr [r14 + 0x98], xmm3', None, '... event +0x98: the blended damage'),
        (0x12A24A6, 'mov eax, dword ptr [rcx + 0xc]', None, 'row AP lanes -> event +0x9C.. (replaced by the hit\'s '
            'own lanes in BuildHitEvent)'),
    ],
    'zoneOf': [
        (0x922067, 'lea r9, [rdx + 0x268]', None, 'zone[0] +0x60 (zones at settings +0x208, stride 0x228)'),
        (0x92207D, 'lea rcx, [r9 + 0x168]', None, 'the zone\'s node list (zone +0x1C8, <= 24)'),
        (0x9220A1, 'add r9, 0x228', None, 'zone stride 0x228'),
        (0x9220A8, 'cmp r10, 0x26', None, '<= 38 zones'),
        (0x9220AE, 'lea rax, [rdx + 0x40]', None, 'no match: the default zone (settings +0x40)'),
        (0x9220C7, 'lea rax, [rdx + 0x208]', None, 'match: settings +0x208 + i * 0x228'),
    ],
    'damageValues': [
        (0x129DC4F, 'mov eax, dword ptr [r8]', None, 'event +0x00 kind: the builder jump table (0, 1 -> 0x129C9F0)'),
        (0x129DC6D, 'call 0x129c9f0', None, 'builder of kinds 0 and 1 (every projectile direct hit)'),
        (0x129DC9F, 'call 0x129d9a0', None, 'builder of kind 5 (not a projectile direct hit)'),
        (0x129DCA4, 'movss xmm0, dword ptr [rdi + 0x98]', None, 'event +0x98 ...'),
        (0x129DCAC, 'ucomiss xmm0, dword ptr [rip + {rip}]', 0x23C800C, '... == -1.0 (kill sentinel) ...'),
        (0x129DCB7, 'mov dword ptr [rbx], 0xbf800000', None, '... values +0x00 = -1'),
        (0x129CA2C, 'movss xmm11, dword ptr [r8 + 0x98]', None, 'builder: event +0x98 ...'),
        (0x129CA35, 'mulss xmm11, dword ptr [r8 + 0x94]', None, '... x event +0x94 (speed factor): the whole blend'),
        (0x129CA3E, 'call 0x129c7c0', None, 'penetration: the event lane picked by impact angle'),
        (0x129CA54, 'movss xmm9, dword ptr [rbx + 0x50]', None, 'event +0x50 zone armour'),
        (0x129CABC, 'subss xmm0, xmm9', None, 'penetration - armour ...'),
        (0x129CAC5, 'comiss xmm0, xmm7', None, '... >= 1: factor 1.0 ...'),
        (0x129CB00, 'movss xmm6, dword ptr [rip + {rip}]', 0x23C6B7C, '... >= 0: factor 0.65 (else 0)'),
        (0x129CB61, 'movss dword ptr [rdi + 4], xmm6', None, 'values +0x04 = the armour factor'),
        (0x129CB66, 'mulss xmm1, xmm11', None, 'factor x damage x speed factor ...'),
        (0x129CB6F, 'maxss xmm0, xmm1', None, '... at least 0 ...'),
        (0x129CB77, 'call 0x2108e78', None, '... rounded ...'),
        (0x129CB80, 'movsxd rax, dword ptr [rbx + 0x6c]', None, '... x relation[event +0x6C] ...'),
        (0x129CB93, 'lea rcx, [rip + {rip}]', RELATION_TABLE, '... (the relation table 0 / 1.5 / 1 / 0.75 / 0.25) ...'),
        (0x129CB9A, 'mulss xmm1, dword ptr [rcx + rax*4]', None, '...'),
        (0x129CB9F, 'movss dword ptr [rdi], xmm1', None, 'values +0x00: the damage'),
    ],
    'produceAndConsume': [
        (0x129E098, 'mov rax, qword ptr [rsp + 0x30]', None, 'ProduceDamage: the damage values ...'),
        (0x129E09D, 'movss xmm1, dword ptr [rax]', None, '... values +0x00'),
        (0x129E10C, 'cmp dword ptr [r15 + 0x7c], 0xaa1db0b0', None, 'one zone hash ...'),
        (0x129E13C, 'mulss xmm1, xmm0', None, '... x an entity attribute (else unchanged)'),
        (0x129E430, 'imul r13, rcx, 0x70', None, 'queue 0 entry (0x70) ...'),
        (0x129E4B4, 'cvttss2si rax, xmm1', None, '... trunc(damage) ...'),
        (0x129E4B9, 'mov dword ptr [r14 + r13 + 0x114c], eax', None, '... entry +0x2C'),
        (0x12A81DC, 'mov esi, dword ptr [r14 + 0x2c]', None, 'ConsumeDamageEvent: entry +0x2C amount ...'),
        (0x12A82C8, 'mov dword ptr [rsp + 0x38], esi', None, '... ApplyDamage argument'),
        (0x12A82EB, 'call 0x9235f0', None, 'ApplyDamage'),
        (0x12A89D5, 'mov eax, dword ptr [r14 + 0x2c]', None, 'the same amount ...'),
        (0x12A89E4, 'mov dword ptr [rsp + 0x48], eax', None, '... damage stats argument 10'),
        (0x12A89FA, 'call 0x12a0f50', None, 'damage stats'),
        (0x12A1062, 'mov r15d, dword ptr [rsp + 0xa8]', None, 'stats: the amount ...'),
        (0x12A106A, 'cmp r15d, ebx', None, '... -1 (kill sentinel) is replaced by health; else unchanged'),
        (0x12A11D1, 'mov r8d, 0x5c7a2930', None, 'stat key dealt_damage ...'),
        (0x12A11DE, 'mov r9d, r15d', None, '... += the amount'),
        (0x12A11F2, 'call 0x62c930', None, 'AddStat'),
    ],
    'damageInfoGetter': [
        (0x11F8EA4, 'lea rax, [rip + {rip}]', DAMAGE_DEFAULT, 'GetDamageInfo(0): the default row'),
        (0x11F8EAE, 'lea rcx, [rip + {rip}]', DAMAGE_TABLE, 'GetDamageInfo(id): table[id]'),
    ],
}
CONSTANTS = {0x23C6D70: 1.0, 0x23C6B7C: 0.65, 0x23C800C: -1.0}
RELATION_VALUES = [0.0, 1.5, 1.0, 0.75, 0.25]

# Every rip-relative reference to the DamageInfo table in .text (instruction start) and what it is.
TABLE_REFERENCES = {
    0x11F8CBB: 'settings loader (r12 = the table while rows are registered)',
    0x11F8E83: 'clear (memset 0x1450)',
    0x11F8EAE: 'GetDamageInfo getter 0x11F8EA0',
    0x129BF42: 'clear (memset 0x1450)',
    0x129C152: 'clear (memset 0x1450)',
    0x129C342: 'clear (memset 0x1450)',
    0x12A23FD: 'InitHitInfo 0x12A15E0: the direct-hit row read (blend into event +0x98)',
    0x13AA628: 'SpawnProjectile: AP lanes -> hit +0x18 (research/projectile-ballistics)',
    0x7D251C: 'another system (reads row +0x20); not reached from the projectile hit',
    0xA28363: 'another system (reads row +0x0C); not reached from the projectile hit',
}
REACH_ROOTS = {0x129DC30: 'DamageValues', 0x129C9F0: 'builder kinds 0/1', 0x129DD30: 'ProduceDamage',
    0x12A7D40: 'ConsumeDamageEvent (ApplyDamage + stats)'}

EVENT_LAYOUT = {
    'size': '0x118 (zeroed by BuildHitEvent 0x12A25C4..0x12A264A)',
    '0x00': 'u32 kind = (hit +0x98 > 0): selects the DamageValues builder (0 and 1 -> 0x129C9F0)',
    '0x04': 'u32 DamageInfo row +0x28 (element / type; copied into queue entry +0x08)',
    '0x0C': 'u32 hit +0x10 (ProjectileInfo +0xE8)',
    '0x18': 'u32 source struct +0x0C',
    '0x1C': 'u32 source struct +0x20',
    '0x20': 'u32 target entity (resolved)',
    '0x24': 'u32 hit node (source struct +0x1C): the hit zone key for 0x922060',
    '0x28': 'vec3 source struct +0x10 (direction; the angle test of 0x129C7C0)',
    '0x34': 'vec3 source struct +0x00',
    '0x40': 'vec3 argument 5 +0x00 (position)',
    '0x4C': 'f32 D = hit zone +0xCC, the zone\'s durable fraction (0 without a zone)',
    '0x50': 'f32 zone armour (zone +0xD8)',
    '0x54': 'f32 zone +0xE0',
    '0x5C': 'f32 (FLT_MAX by default)',
    '0x6C': 'i32 relation index (2 = x1.0)',
    '0x70..0x79': 'flag bytes (+0x73 forces the armour factor to 1.0; +0x78/+0x79 = zone +0x1B8/+0x1B9)',
    '0x7C': 'u32 zone +0x60 (zone name hash)',
    '0x80': 'u32 argument 3 +0x00',
    '0x84': 'u32 resolved from +0x80 (0x7FFF if none)',
    '0x88': 'vec3 argument 5 +0x0C (surface normal; the angle test)',
    '0x94': 'f32 speed factor 0.25 + 0.75 (|v| / flight +0x2C)^2 (1.0 for a unit-driven shot)',
    '0x98': 'f32 DAMAGE = row standard x (1 - D) + row durable x D + hit +0x2C x (1 - D) + hit +0x30 x D; then x hit '
        '+0x34 at 0x13AD524',
    '0x9C..0xA8': 'f32 x4 penetration lanes = max(0, hit lane i + hit +0x24 x (1 - D) + hit +0x28 x D); then x hit +0x38 '
        'rounded at 0x13AD550',
    '0xAC': 'f32 DamageInfo row +0x20 (to values +0x0C only when the armour factor is not 0)',
    '0xB0': 'f32 DamageInfo row +0x1C (to values +0x08)',
    '0xB4': 'f32 DamageInfo row +0x24 (to values +0x10)',
    '0xB8': 'u32 0',
    '0xBC': 'f32 1.0',
    '0xC0..0xDF': 'DamageInfo row +0x2C..+0x4B (status / value pairs)',
    '0xFC': 'u8 0',
    '0x100': 'u32 argument 3 +0x04; +0x104 resolved (0x7FFF if none); +0x108 u8',
    '0x110': 'u64 argument 3 +0x08',
    'notStored': 'the DamageInfo id (source struct +0x24) is read once (0x12A1C29) and not copied into the event',
}
VALUES_LAYOUT = {
    'size': '0x24 (0x129DC30 zeroes +0x00..+0x23)',
    '0x00': 'f32 damage = round(max(0, armour factor x event +0x98 x event +0x94)) x relation[event +0x6C] (-1 = kill)',
    '0x04': 'f32 armour factor 1.0 / 0.65 / 0 (1.0 when event +0x73 or ProjectileInfo +0xFC bit 0)',
    '0x08': 'i32 (int) event +0xB0', '0x0C': 'i32 (int) event +0xAC or 0', '0x10': 'i32 (int) event +0xB4',
    '0x14': 'i32 from D and the zone armour', '0x18': 'f32 from the angle', '0x1C..0x1F': 'flag bytes',
}


def func_insns(md, data: bytes, start: int, limit: int = 0x8000) -> dict:
    """Instructions reachable from start through jumps (not calls), bounded."""
    seen, work = {}, [start]
    while work:
        a = work.pop()
        while a not in seen and start - 0x200 <= a < start + limit:
            ins = next(md.disasm(data[a:a + 16], a), None)
            if ins is None:
                break
            seen[a] = ins
            if ins.mnemonic.startswith('j'):
                if ins.op_str.startswith('0x'):
                    work.append(int(ins.op_str, 16))
                if ins.mnemonic == 'jmp':
                    break
            if ins.mnemonic in ('ret', 'int3'):
                break
            a += ins.size
    return seen


def table_census(image) -> list[dict]:
    """Every rip-relative operand in .text that resolves to the DamageInfo table."""
    found = []
    for rva, size, mnemonic, op in image.sweep():
        if 'rip' in op and base.rip_of(rva, size, op) == DAMAGE_TABLE:
            found.append({'rva': rva, 'asm': mnemonic + ' ' + op, 'role': TABLE_REFERENCES.get(rva, 'UNCLASSIFIED')})
    return found


def getter_callers(image) -> list[int]:
    out = []
    for rva, size, mnemonic, op in image.sweep():
        if mnemonic in ('call', 'jmp') and op == '0x%x' % DAMAGE_GETTER:
            out.append(rva)
    return out


def reachability(image, forbidden: set[int], depth: int = 4) -> dict:
    """Direct callees of the damage consumers, transitively: none may contain a table reference or a getter call."""
    md, data = image.md, image.data
    result = {}
    for root, label in REACH_ROOTS.items():
        frontier, visited, hits = [root], set(), []
        for _ in range(depth):
            nxt = []
            for f in frontier:
                if f in visited or not (base.TEXT[0] <= f < base.TEXT[1]):
                    continue
                visited.add(f)
                insns = func_insns(md, data, f)
                hits += ['%X in %X' % (a, f) for a in insns if a in forbidden]
                for ins in insns.values():
                    if ins.mnemonic == 'call' and ins.op_str.startswith('0x'):
                        nxt.append(int(ins.op_str, 16))
            frontier = nxt
        result['0x%X' % root] = {'label': label, 'depth': depth, 'functions': len(visited), 'tableOrGetterHits': hits}
    return result


def observe(name: str) -> dict:
    mem = base.Mem(name)
    try:
        p = mem.ptr(mem.game + DAMAGE_TABLE + 8 * LIBERATOR_DAMAGE)
        raw = mem.read(p, DAMAGE_STRIDE) if p else None
        v = struct.unpack_from('<19I', raw, 0) if raw else None
        liberator = None if v is None or v[0] != LIBERATOR_DAMAGE else {
            'standard': v[1], 'durable': v[2], 'armorPenetration': list(v[3:7]), 'row0x1C_0x28': list(v[7:11]),
            'statuses': [[v[k], v[k + 1]] for k in range(11, 19, 2) if v[k]], 'bytes': raw.hex()}
        # Hit-zone durable fractions (zone +0xCC) in the shared HealthComponentData table (0x507430's layout).
        zones = {'settings': 0, 'zones': 0, 'outside01': 0, 'histogram': {}}
        root = mem.ptr(mem.game + SETTINGS_ROOT)
        table = mem.ptr(root + 0xF12B78) if root else None
        if table:
            hashed = mem.read(table, 0x3EA0)
            hist = collections.Counter()
            for k in range(0x3EA):
                key, idx = struct.unpack_from('<QI', hashed, k * 16)
                if not key:
                    continue
                s = mem.read(table + 0x3EA0 + idx * 0x5650, 0x5650)
                if s is None:
                    continue
                zones['settings'] += 1
                for i in range(0x26):
                    z = 0x208 + i * 0x228
                    if struct.unpack_from('<I', s, z + 0x60)[0] == 0:
                        break
                    d = struct.unpack_from('<f', s, z + 0xCC)[0]
                    zones['zones'] += 1
                    if not 0.0 <= d <= 1.0:
                        zones['outside01'] += 1
                    hist[str(round(d, 3))] += 1
            zones['histogram'] = dict(hist.most_common(12))
        # The per-shot additive pairs in every stored hit record.
        bonus = collections.Counter()
        system = mem.ptr(mem.game + SYSTEM_GLOBAL)
        if system:
            types = struct.unpack('<2048I', mem.read(system + 0xE5040, 8192))
            hit = mem.read(system + 0x4D040, 2048 * 0xC8)
            for slot, t in enumerate(types):
                if 0 < t < 351:
                    bonus[str([round(x, 4) for x in struct.unpack_from('<4f', hit, slot * 0xC8 + 0x24)])] += 1
        relation = [struct.unpack_from('<f', mem.read(mem.game + RELATION_TABLE + 4 * i, 4))[0] for i in range(5)]
        return {'snapshot': name, 'liberatorDamageInfo': liberator, 'hitZones': zones,
            'hitBonusPairs': dict(bonus), 'relationTable': relation}
    finally:
        mem.close()


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[-1])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    constants = []
    for rva, value in CONSTANTS.items():
        got = struct.unpack_from('<f', data, rva)[0]
        if not math.isclose(got, value, rel_tol=1e-6):
            raise ValueError('constant at %X is %r, not %r' % (rva, got, value))
        constants.append({'rva': rva, 'bytes': data[rva:rva + 4].hex(), 'value': got})
    rel = list(struct.unpack_from('<5f', data, RELATION_TABLE))
    if any(not math.isclose(a, b, abs_tol=1e-6) for a, b in zip(rel, RELATION_VALUES)):
        raise ValueError('relation table changed: %r' % rel)
    constants.append({'rva': RELATION_TABLE, 'bytes': data[RELATION_TABLE:RELATION_TABLE + 20].hex(), 'value': rel,
        'role': 'relation multipliers (event +0x6C index)'})
    jump = list(struct.unpack_from('<7I', data, 0x129DD08))
    if jump[0] != 0x129DC6A or jump[1] != 0x129DC6A:
        raise ValueError('DamageValues kinds 0/1 no longer go to the 0x129C9F0 call: %r' % jump)
    constants.append({'rva': 0x129DD08, 'bytes': data[0x129DD08:0x129DD08 + 28].hex(), 'value': ['0x%X' % j for j in jump],
        'role': 'DamageValues jump table by event kind (0, 1 -> call 0x129C9F0)'})
    relocation = {name: base.verify_pins_live(name, pins + constants, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    refs = table_census(image)
    if sorted(r['rva'] for r in refs) != sorted(TABLE_REFERENCES):
        raise ValueError('DamageInfo table references changed: %r' % refs)
    callers = getter_callers(image)
    reach = reachability(image, set(TABLE_REFERENCES) | set(callers))
    for root, r in reach.items():
        if r['tableOrGetterHits']:
            raise ValueError('%s reaches a DamageInfo read: %r' % (root, r['tableOrGetterHits']))

    # The hit function never touches event +0x4C / +0x94 / +0x98 (rbp+0x5CC / +0x614 / +0x618) except the multiply.
    window = []
    for ins in image.md.disasm(data[0x13AC300:0x13AF280], 0x13AC300):
        if any(m in ins.op_str for m in ('rbp + 0x5cc]', 'rbp + 0x614]', 'rbp + 0x618]')):
            window.append({'rva': ins.address, 'asm': ins.mnemonic + ' ' + ins.op_str})
    if [w['rva'] for w in window] != [0x13AD506, 0x13AD533]:
        raise ValueError('the hit function gained an event damage / D / speed accessor: %r' % window)

    observations = [observe(name) for name in SNAPSHOTS]
    lib ={json.dumps(o['liberatorDamageInfo'], sort_keys=True) for o in observations}
    if len(lib) != 1 or None in [o['liberatorDamageInfo'] for o in observations]:
        raise ValueError('DamageInfo %d differs between snapshots' % LIBERATOR_DAMAGE)

    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'gameDllSha256': base.PROFILE_DLL_SHA,
        'functions': {
            '0x12A25B0': 'BuildHitEvent(ctx, event, arg3, sourceStruct, pos, hit+0x10, speedFactor, lanes*, &hit+0x24, '
                '&hit+0x2C, kind)',
            '0x12A15E0': 'InitHitInfo: target, hit zone (D, armour), DamageInfo row -> event',
            '0x922060': 'ZoneOf(settings, node): hit zone (<= 38, stride 0x228 from settings +0x208; default +0x40)',
            '0x129DC30': 'DamageValues(ctx, values, event): builder by event kind; -1.0 damage -> -1',
            '0x129C9F0': 'builder of kinds 0/1 (projectile direct hits)',
            '0x129C7C0': 'penetration: one of the four event lanes by impact angle',
            '0x129DD30': 'ProduceDamage(ctx, values, event, arg4): queue entries (amount = trunc(values +0x00))',
            '0x12A7D40': 'ConsumeDamageEvent: ApplyDamage 0x9235F0 + stats 0x12A0F50 with the same amount',
            '0x11F8EA0': 'GetDamageInfo(id) (not called on this path)'},
        'damageInfoRow': {'table': '0x%X' % DAMAGE_TABLE, 'stride': '0x%X' % DAMAGE_STRIDE, 'members': {
            '0x00': 'id', '0x04': 'standard damage (u32)', '0x08': 'durable damage (u32)', '0x0C..0x18': 'AP x4 (u32)',
            '0x1C': '-> event +0xB0', '0x20': '-> event +0xAC', '0x24': '-> event +0xB4', '0x28': '-> event +0x04',
            '0x2C..0x4B': 'status / value pairs -> event +0xC0..+0xDF'}},
        'eventLayout': EVENT_LAYOUT, 'valuesLayout': VALUES_LAYOUT,
        'formula': {
            'blend': 'B = std x (1 - D) + dur x D + hit+0x2C x (1 - D) + hit+0x30 x D  (D = hit zone +0xCC)',
            'event98': 'B x hit+0x34',
            'values00': 'round(max(0, A x B x hit+0x34 x S)) x relation[event +0x6C]  (S = speed factor, A = 1 / 0.65 / 0)',
            'queuedAmount': 'trunc(values +0x00 [x attribute for zone hash 0xAA1DB0B0]) = ApplyDamage amount = the '
                'dealt_damage stat'},
        'verdicts': {
            'standardVsDurableChoice': 'made ONCE in InitHitInfo 0x12A15E0 at 0x12A2479..0x12A249D: event +0x98 = '
                'standard x (1 - D) + durable x D, D = the hit zone\'s durable fraction (zone +0xCC -> event +0x4C, '
                '0x12A1E78/0x12A1E7E). The durable value is not stored separately and is never re-read by id after it.',
            'hit34': 'SCALES BOTH: hit +0x34 multiplies event +0x98 (0x13AD524), which already is the standard / durable '
                'blend (plus the hit +0x2C/+0x30 additive pair). Every later step is multiplicative or monotone: '
                'damage = round(max(0, A x S x hit+0x34 x B)) x relation, truncated.',
            'perShotDurable': 'hit +0x30 (f32, from the source component record +0x60 at spawn, 0 in every stored '
                'record) is a per-shot ADDITIVE durable-weighted damage (x D), and hit +0x2C its standard-weighted '
                'twin (x (1 - D)); both are read only at 0x13AD48C (argument 10). No per-shot member scales durable '
                'alone multiplicatively; a durable-only scale is a hit +0x30 add of dur x (k - 1) (with hit +0x34 '
                'left at 1), or a hit +0x0C swap to a reviewed row.',
            'speedFactor': 'applies to the whole blend (standard and durable): the builder multiplies event +0x98 by '
                'event +0x94 (0x129CA35).',
            'liveEvidence': 'The static chain cannot produce "x0.5 leaves durable damage unchanged": a 0.5 write that '
                'is in the record when the hit is processed halves the recorded amount on every zone. Leading '
                'explanation (INFERRED): those hits were processed before the write landed (close-range warrior '
                'hits resolved in the shot\'s first update), the unproven timing item of research/projectile-'
                'ballistics. The per-hit means also mix targets and zones between modes.'},
        'proofs': proofs, 'constants': constants,
        'census': {'tableReferences': refs, 'getterCallers': ['0x%X' % c for c in callers], 'reachability': reach,
            'hitFunctionEventAccesses': window},
        'pinnedBytesMismatchPerSnapshot': relocation, 'observations': observations,
        'unproven': [
            'Timing: whether a Runtime write of hit +0x34 lands before a close-range shot\'s first hit (the live '
            'x0.5 result fits a write that did not land; not proven).',
            'Builder 0x129D9A0 (kind 5) is not traced; projectile direct hits are kind 0/1 (0x13AD494) and use '
            '0x129C9F0.',
            'ApplyDamage 0x9235F0 internals (zone health pools, Vitality, relation acceptance) act on the amount '
            'after the stat; they do not see a DamageInfo id (the queue entry carries none).',
            'Names of DamageInfo +0x1C/+0x20/+0x24/+0x28 and of event +0x14 values are not established here.',
            'The entity attribute for zone hash 0xAA1DB0B0 (0x129E10C) is not identified.',
            'hit +0x2C/+0x30 writes are not live-tested.'],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'pins': len(pins), 'constants': len(constants), 'tableReferences': len(refs),
        'getterCallers': len(callers), 'reachability': {k: (v['functions'], len(v['tableOrGetterHits']))
            for k, v in reach.items()},
        'liberator': observations[-1]['liberatorDamageInfo'],
        'zones': [(o['hitZones']['settings'], o['hitZones']['zones'], o['hitZones']['outside01']) for o in observations],
        'bonus': [o['hitBonusPairs'] for o in observations]}, indent=1))


if __name__ == '__main__':
    main()
