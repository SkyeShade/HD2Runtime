"""Per-shot projectile ballistics: where SpawnProjectile puts each copied ProjectileInfo member in the spawned
projectile's OWN pool records, which of those copies the game reads again after the spawn (so one guarded per-round
write changes THAT shot and nothing else), and SpawnProjectile's per-call extra block (speed and damage multipliers).
Read-only, offline, build F5FEE03DCFDB, game.dll image of a retained snapshot plus every retained snapshot.

SpawnProjectile is 0x13A9830 (domains/projectile_rows.lua spawn.rva = 20617264). Slot N's records (system = the
projectile system, game+0x347CEA8):
  flight  system + 0x3040 + N*0x70    position, velocity, ballistics (the integrator's inputs), speed, lifetime
  source  system + 0x3B040 + N*0x24
  hit     system + 0x4D040 + N*0xC8   damage id, armour penetration lanes, penetration slowdown, damage multipliers
  extra2  system + 0xB1040 + N*0x40   (written from the extra block, meaning not established)
  effect  system + 0xD1040 + N*0x28

Proven here (pins below; every pin byte-identical in every retained snapshot):

1. Destinations. row +0x2C gravity -> flight +0x1C; +0x18 diameter -> flight +0x20; +0x24 mass x 0.001 -> flight +0x24
   (kg); drag constant (row +0x18 x 0.0005)^2 x pi/2 x 1.2 x row +0x28 -> flight +0x28 (0.5 rho A Cd, rho 1.2); launch
   speed -> flight +0x2C (scalar) and direction x speed -> flight +0x0C (velocity); row +0x30 -> flight +0x48 (u32, the
   integrator's substep count); lifetime row +0x34 x (1 + row +0x38 x r), r uniform in [-1, 1) -> flight +0x34; row
   +0x3C -> hit +0x0C and its DamageInfo's four armour penetrations -> hit +0x18/+0x1A/+0x1C/+0x1E; row +0x40 -> hit
   +0x20; row +0x90 -> hit +0x7C.
2. Launch speed = row +0x20 (replaced by the source entity's component +0x23C when that is > 0), x the source's
   component multiplier (+0x50), x extra +0x2C (when an extra block is given). Stored twice: the scalar flight +0x2C
   and the velocity flight +0x0C (plus extra +0x20's vector and, with row +0xF0 bit 0, the source's velocity).
3. Read after the spawn, from the copy: the update passes flight +0x1C, +0x28, +0x24, +0x48 to the ballistic integrator
   every step (0x13AB557..0x13AB59A); the integrator uses them as gravity multiplier, drag constant, mass and substep
   count (0x13AAE3F..0x13AB077). flight +0x2C is the REFERENCE speed: the update ends a shot below 0.1 x it
   (0x13AB6D5), and each direct hit scales its damage by 0.25 + 0.75 x (|velocity| / flight +0x2C)^2 (1.0 for a
   unit-driven shot; 0x13AD058..0x13AD08B -> event +0x94 -> damage builders 0x129CA35). The lifetime is counted down
   (0x13AB82D). Mass is read again by the ricochet test (0x13B0C4D). hit +0x20 slows the velocity by (1 - it) at each
   penetration (0x13ADBB4..0x13ADBE5).
4. Extra block (r13, may be null): +0x00 carried step time -> flight +0x18; +0x04 -> hit +0x94; +0x08/+0x10 u32 list
   (<= 4) -> source +0x10; +0x18/+0x19/+0x1A/+0x1B flag bytes; +0x20 vec3* added to the velocity; +0x28 driving unit ->
   flight +0x50; +0x2C SPEED multiplier; +0x30 DAMAGE multiplier -> hit +0x34; +0x34 PENETRATION multiplier -> hit
   +0x38 (both 1.0 without a block); +0x38/+0x40 -> flight +0x60/+0x68; +0x44..+0x54 -> extra2 record. On each direct
   hit the damage event's damage (event +0x98, built by 0x12A25B0 from the hit record) is multiplied by hit +0x34 and
   each of its four penetration lanes by hit +0x38 (rounded) before the damage builders read them (0x13AD524..
   0x13AD55F). hit +0x34 / +0x38 have no other reader or writer in the projectile code: a per-round write of hit +0x34
   scales THAT shot's direct-hit damage (not its explosions).
5. Not read again (no reader found): the diameter copy flight +0x20 (its effect is the drag constant computed at spawn)
   and the lifetime variance (consumed into the lifetime).

Output: research/projectile-ballistics-F5FEE03DCFDB.json.   py scripts/research_projectile_ballistics.py
"""
from __future__ import annotations

import json
import math
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/projectile-ballistics-F5FEE03DCFDB.json'
SPAWN = 0x13A9830
SYSTEM_GLOBAL = 0x347CEA8
ROW_TABLE, ROW_SIZE, TYPE_COUNT = 0x37C7670, 272, 351
RECORDS = {
    'flight': {'base': 0x3040, 'stride': 0x70},
    'source': {'base': 0x3B040, 'stride': 0x24},
    'hit': {'base': 0x4D040, 'stride': 0xC8},
    'extra2': {'base': 0xB1040, 'stride': 0x40},
    'effect': {'base': 0xD1040, 'stride': 0x28},
    'types': {'base': 0xE5040, 'stride': 4},
    'flags': {'base': 0x203C, 'stride': 2},
}
CODE_RANGE = (0x13A8000, 0x13B4000)  # the projectile system's functions (SpawnProjectile, update, hit, explosion)

# (rva, asm, rip target or None, role)
PROOFS = {
    'spawnFlight': [
        (0x13A9858, 'mov r13, r8', None, 'r13 = the extra block (third argument; may be null)'),
        (0x13A9C34, 'imul r15, rdi, 0x70', None, 'flight record offset = slot * 0x70'),
        (0x13A9C52, 'movups xmmword ptr [r15 + rsi + 0x3040], xmm0', None, 'flight record zeroed (+0x00..+0x6F)'),
        (0x13A9C95, 'movss xmm6, dword ptr [rax + 0x20]', None, 'speed = row +0x20 (launch speed)'),
        (0x13A9D2B, 'movss xmm0, dword ptr [rax + 0x23c]', None, 'the source entity component +0x23C ...'),
        (0x13A9D39, 'movaps xmm6, xmm0', None, '... replaces the speed when it is > 0'),
        (0x13A9DA1, 'mulss xmm6, dword ptr [rdx + rax + 0x50]', None, 'speed x the source component multiplier +0x50'),
        (0x13A9DA7, 'test r13, r13', None, 'extra block given?'),
        (0x13A9DB2, 'mulss xmm6, dword ptr [r13 + 0x2c]', None, 'speed x extra +0x2C (SPEED multiplier)'),
        (0x13A9DBE, 'mov edx, dword ptr [r13 + 0x28]', None, 'extra +0x28: a driving unit ...'),
        (0x13A9DCE, 'mov dword ptr [r15 + rsi + 0x3090], ecx', None, '... resolved into flight +0x50 (0 = ballistic)'),
        (0x13A9DF0, 'cmp byte ptr [r13 + 0x1b], bl', None, 'extra +0x1B flag ...'),
        (0x13A9DFC, 'mov byte ptr [r15 + rsi + 0x3094], al', None, '... into flight +0x54'),
        (0x13A9E55, 'mov rax, qword ptr [r14 + 8]', None, 'descriptor +0x08: the direction'),
        (0x13A9E59, 'mulss xmm0, dword ptr [rax + 8]', None, 'velocity z = direction z x speed'),
        (0x13A9E5E, 'mulss xmm2, dword ptr [rax]', None, 'velocity x = direction x x speed'),
        (0x13A9E62, 'mulss xmm1, dword ptr [rax + 4]', None, 'velocity y = direction y x speed'),
        (0x13A9E75, 'movsd qword ptr [r15 + rsi + 0x304c], xmm0', None, 'flight +0x0C: velocity x, y'),
        (0x13A9E7F, 'mov dword ptr [r15 + rsi + 0x3054], eax', None, 'flight +0x14: velocity z'),
        (0x13A9E8C, 'mov rax, qword ptr [r13 + 0x20]', None, 'extra +0x20: a vec3 pointer ...'),
        (0x13A9E99, 'addss xmm0, dword ptr [r15 + rsi + 0x304c]', None, '... added to the velocity'),
        (0x13A9EE3, 'test byte ptr [rax + 0xf0], 1', None, 'row +0xF0 bit 0: also inherit the source velocity'),
        (0x13AA029, 'movss xmm0, dword ptr [r13]', None, 'extra +0x00 (0 without a block) ...'),
        (0x13AA035, 'movss dword ptr [r15 + rsi + 0x3058], xmm0', None, '... flight +0x18: carried step time'),
        (0x13AA043, 'mov ecx, dword ptr [rax + 0x2c]', None, 'row +0x2C gravity multiplier ...'),
        (0x13AA046, 'mov dword ptr [r15 + rsi + 0x305c], ecx', None, '... flight +0x1C'),
        (0x13AA052, 'mov ecx, dword ptr [rax + 0x18]', None, 'row +0x18 diameter (mm) ...'),
        (0x13AA055, 'mov dword ptr [r15 + rsi + 0x3060], ecx', None, '... flight +0x20 (copied unchanged)'),
        (0x13AA061, 'movss xmm0, dword ptr [rax + 0x24]', None, 'row +0x24 mass (g) ...'),
        (0x13AA066, 'mulss xmm0, dword ptr [rip + {rip}]', 0x23C65B4, '... x 0.001 ...'),
        (0x13AA06E, 'movss dword ptr [r15 + rsi + 0x3064], xmm0', None, '... flight +0x24: mass in kg'),
        (0x13AA07C, 'mov ecx, dword ptr [rax + 0x30]', None, 'row +0x30 (u32) ...'),
        (0x13AA07F, 'mov dword ptr [r15 + rsi + 0x3088], ecx', None, '... flight +0x48: the integrator substep count'),
        (0x13AA095, 'movss xmm0, dword ptr [rax + 0x18]', None, 'drag constant: diameter ...'),
        (0x13AA09A, 'mulss xmm0, dword ptr [rip + {rip}]', 0x23C65A8, '... x 0.0005 (radius in m) ...'),
        (0x13AA0A2, 'mulss xmm0, xmm0', None, '... squared ...'),
        (0x13AA0A6, 'mulss xmm0, dword ptr [rip + {rip}]', 0x23C6F1C, '... x pi/2 ...'),
        (0x13AA0AE, 'mulss xmm0, dword ptr [rip + {rip}]', 0x23C6E28, '... x 1.2 (air density) ...'),
        (0x13AA0B6, 'mulss xmm0, dword ptr [rax + 0x28]', None, '... x row +0x28 drag coefficient'),
        (0x13AA0BB, 'mov dword ptr [r15 + rsi + 0x3070], ebx', None, 'flight +0x30: distance travelled = 0'),
        (0x13AA0C3, 'movss dword ptr [r15 + rsi + 0x306c], xmm6', None, 'flight +0x2C: the launch speed (scalar)'),
        (0x13AA0D5, 'movss dword ptr [r15 + rsi + 0x3068], xmm0', None, 'flight +0x28: the drag constant'),
        (0x13A9A07, 'movss xmm13, dword ptr [rip + {rip}]', 0x23C6D70, 'xmm13 = 1.0'),
        (0x13AA103, 'movss xmm2, dword ptr [rcx + 0x34]', None, 'row +0x34 lifetime ...'),
        (0x13AA110, 'mulss xmm1, dword ptr [rcx + 0x38]', None, '... x row +0x38 variance ...'),
        (0x13AA11D, 'mulss xmm0, dword ptr [rip + {rip}]', 0x23C6538, '... random u32 x 2^-32 ...'),
        (0x13AA125, 'addss xmm0, xmm0', None, '... x 2 ...'),
        (0x13AA129, 'subss xmm0, xmm13', None, '... - 1 (r in [-1, 1)) ...'),
        (0x13AA137, 'mulss xmm1, xmm0', None, '... lifetime x variance x r ...'),
        (0x13AA13B, 'addss xmm1, xmm2', None, '... + lifetime ...'),
        (0x13AA13F, 'movss dword ptr [r15 + rsi + 0x3074], xmm1', None, '... flight +0x34: remaining lifetime'),
        (0x13AA197, 'mov ecx, dword ptr [rax + 0xe4]', None, 'row +0xE4 ...'),
        (0x13AA19D, 'mov dword ptr [r15 + rsi + 0x3084], ecx', None, '... flight +0x44'),
        (0x13AA1B3, 'mov rax, qword ptr [r13 + 0x38]', None, 'extra +0x38 ...'),
        (0x13AA1B7, 'mov qword ptr [r15 + rsi + 0x30a0], rax', None, '... flight +0x60'),
        (0x13AA1BF, 'mov eax, dword ptr [r13 + 0x40]', None, 'extra +0x40 ...'),
        (0x13AA1CF, 'mov dword ptr [r15 + rsi + 0x30a8], eax', None, '... flight +0x68'),
    ],
    'spawnHit': [
        (0x13A9BBF, 'cmp byte ptr [r13 + 0x18], bl', None, 'extra +0x18 flag: slot flag 0x20 unless a block has it 0'),
        (0x13AA56C, 'mov eax, dword ptr [r13 + 8]', None, 'extra +0x08: list count ...'),
        (0x13AA580, 'mov rax, qword ptr [r13 + 0x10]', None, '... extra +0x10: u32 list ...'),
        (0x13AA58C, 'mov dword ptr [r15 + rdx + 0xc], ecx', None, '... into source record +0x10.. (up to 4)'),
        (0x13AA603, 'lea rdi, [rsi + 0x4d040]', None, 'hit records'),
        (0x13AA60A, 'imul rax, rax, 0xc8', None, 'hit record stride 0xC8'),
        (0x13AA61F, 'call 0x208aaa0', None, 'hit record zeroed (0xC8 bytes)'),
        (0x13AA62F, 'mov ecx, dword ptr [rax + 0x3c]', None, 'row +0x3C DamageInfo id ...'),
        (0x13AA632, 'mov dword ptr [rdi + 0xc], ecx', None, '... hit +0x0C'),
        (0x13AA673, 'mov ecx, dword ptr [rax + 0x40]', None, 'row +0x40 penetration slowdown ...'),
        (0x13AA676, 'mov dword ptr [rdi + 0x20], ecx', None, '... hit +0x20'),
        (0x13AA692, 'movzx eax, word ptr [rax + 0xc]', None, 'DamageInfo AP lane 0 ...'),
        (0x13AA696, 'mov word ptr [rdi + 0x18], ax', None, '... hit +0x18'),
        (0x13AA6B0, 'mov word ptr [rdi + 0x1a], ax', None, 'AP lane 1 -> hit +0x1A'),
        (0x13AA6CA, 'mov word ptr [rdi + 0x1c], ax', None, 'AP lane 2 -> hit +0x1C'),
        (0x13AA6E8, 'mov word ptr [rdi + 0x1e], ax', None, 'AP lane 3 -> hit +0x1E'),
        (0x13AA646, 'mov ecx, dword ptr [rax + 0x90]', None, 'row +0x90 impact explosion ...'),
        (0x13AA64C, 'mov dword ptr [rdi + 0x7c], ecx', None, '... hit +0x7C'),
        (0x13AA79B, 'mov eax, dword ptr [r13 + 4]', None, 'extra +0x04 ...'),
        (0x13AA83B, 'mov dword ptr [rdi + 0x94], eax', None, '... hit +0x94'),
        (0x13AA943, 'mov eax, dword ptr [rdx + 0x54]', None, 'source component +0x54 ...'),
        (0x13AA946, 'mov dword ptr [rdi + 0x24], eax', None, '... hit +0x24 (with +0x28/+0x2C/+0x30 from +0x58/+0x5C/+0x60)'),
        (0x13AA95B, 'test r13, r13', None, 'extra block given?'),
        (0x13AA960, 'mov eax, dword ptr [r13 + 0x30]', None, 'extra +0x30 DAMAGE multiplier ...'),
        (0x13AA964, 'mov dword ptr [rdi + 0x34], eax', None, '... hit +0x34'),
        (0x13AA967, 'mov eax, dword ptr [r13 + 0x34]', None, 'extra +0x34 PENETRATION multiplier ...'),
        (0x13AA96B, 'mov dword ptr [rdi + 0x38], eax', None, '... hit +0x38'),
        (0x13AA974, 'cmp byte ptr [r13 + 0x1a], bl', None, 'extra +0x1A: hit +0x9C = row +0xB0 only when set'),
        (0x13AA989, 'mov dword ptr [rdi + 0x34], 0x3f800000', None, 'no extra block: damage multiplier 1.0'),
        (0x13AA990, 'mov dword ptr [rdi + 0x38], 0x3f800000', None, 'no extra block: penetration multiplier 1.0'),
        (0x13AAA32, 'lea rdi, [r12 + 0x2c41]', None, 'extra2 record: (slot + 0x2C41) * 0x40 ...'),
        (0x13AAA3A, 'shl rdi, 6', None, '... = system + 0xB1040 + slot * 0x40'),
        (0x13AAA55, 'mov eax, dword ptr [r13 + 0x50]', None, 'extra +0x50 (else row +0xD0) -> extra2 +0x0C'),
        (0x13AAA74, 'mov eax, dword ptr [r13 + 0x54]', None, 'extra +0x54 (else row +0xD4) -> extra2 +0x10'),
        (0x13AAAF3, 'mov eax, dword ptr [r13 + 0x44]', None, 'extra +0x44 -> extra2 +0x30'),
        (0x13AAAFA, 'mov ecx, dword ptr [r13 + 0x48]', None, 'extra +0x48 (resolved) -> extra2 +0x34'),
        (0x13AAB17, 'movss xmm14, dword ptr [r13 + 0x4c]', None, 'extra +0x4C -> extra2 +0x38'),
        (0x13AAB88, 'cmp byte ptr [r13 + 0x19], al', None, 'extra +0x19: particle effect row +0x50 instead of +0x48'),
    ],
    'update': [
        (0x13AB25E, 'imul r13, rsi, 0x70', None, 'update: this slot\'s flight record offset'),
        (0x13AB262, 'lea rdi, [rbx + 0x3040]', None, 'flight records'),
        (0x13AB269, 'add rdi, r13', None, 'rdi = this slot\'s flight record'),
        (0x13AB451, 'movss xmm8, dword ptr [rip + {rip}]', 0x23C675C, 'xmm8 = 0.1 (the minimum speed fraction)'),
        (0x13AB557, 'mov ecx, dword ptr [rdi + 0x48]', None, 'flight +0x48 substep count ...'),
        (0x13AB55A, 'lea rdx, [rdi + 0xc]', None, 'the velocity (integrator argument 2)'),
        (0x13AB55E, 'movss xmm1, dword ptr [rdi + 0x28]', None, 'flight +0x28 drag constant ...'),
        (0x13AB566, 'mov r8, rdi', None, 'the position (integrator argument 3)'),
        (0x13AB569, 'cvtsi2ss xmm0, rcx', None, 'substeps as a float ...'),
        (0x13AB56E, 'divss xmm9, xmm0', None, '... step time / substeps'),
        (0x13AB573, 'movss xmm0, dword ptr [rdi + 0x24]', None, 'flight +0x24 mass ...'),
        (0x13AB578, 'movss dword ptr [rsp + 0x40], xmm9', None, 'integrator argument 9: substep time'),
        (0x13AB57F, 'mov dword ptr [rsp + 0x38], ecx', None, 'integrator argument 8: substep count'),
        (0x13AB583, 'movss dword ptr [rsp + 0x30], xmm0', None, 'integrator argument 7: mass'),
        (0x13AB589, 'movss xmm0, dword ptr [rdi + 0x1c]', None, 'flight +0x1C gravity multiplier ...'),
        (0x13AB58E, 'movss dword ptr [rsp + 0x28], xmm1', None, 'integrator argument 6: drag constant'),
        (0x13AB594, 'movss dword ptr [rsp + 0x20], xmm0', None, 'integrator argument 5: gravity multiplier'),
        (0x13AB59A, 'call 0x13aae30', None, 'the ballistic integrator, every update of a ballistic slot'),
        (0x13AB6D5, 'divss xmm0, dword ptr [rdi + 0x2c]', None, '|velocity| / flight +0x2C ...'),
        (0x13AB6DA, 'comiss xmm8, xmm0', None, '... below 0.1: the shot ends (unless flags bit 2)'),
        (0x13AB82D, 'movss xmm0, dword ptr [rdi + 0x34]', None, 'flight +0x34 lifetime ...'),
        (0x13AB83C, 'subss xmm0, xmm15', None, '... counted down by the step time ...'),
        (0x13AB845, 'movss dword ptr [rdi + 0x34], xmm0', None, '... and stored back'),
    ],
    'integrator': [
        (0x13AAE3F, 'mov eax, dword ptr [rsp + 0x108]', None, 'argument 8: substep count ...'),
        (0x13AAE4C, 'test eax, eax', None, '... 0: no motion at all'),
        (0x13AAE7F, 'movss xmm11, dword ptr [rdx + 4]', None, 'loads the velocity'),
        (0x13AAEA1, 'movss xmm14, dword ptr [rsp + 0xf0]', None, 'argument 5: gravity multiplier ...'),
        (0x13AAEFE, 'mulss xmm7, xmm14', None, '... x the gravity vector'),
        (0x13AAF0C, 'movss xmm0, dword ptr [rsp + 0xf8]', None, 'argument 6: drag constant ...'),
        (0x13AAF18, 'comiss xmm0, xmm10', None, '... drag only when > 0'),
        (0x13AAF48, 'mulss xmm6, xmm0', None, '|v|^2 x drag constant ...'),
        (0x13AAF54, 'divss xmm6, dword ptr [rsp + 0x100]', None, '... / argument 7 (mass): drag deceleration'),
        (0x13AAFD4, 'movss xmm5, dword ptr [rsp + 0x110]', None, 'argument 9: substep time'),
        (0x13AB062, 'movss dword ptr [rbx], xmm12', None, 'stores the velocity back'),
        (0x13AB073, 'sub rsi, 1', None, 'next substep ...'),
        (0x13AB077, 'jne 0x13aaec0', None, '... (substep count times)'),
    ],
    'hit': [
        (0x13AC345, 'lea rdi, [r15 + 0x3040]', None, 'hit processing: flight records ...'),
        (0x13AC373, 'imul rax, rax, 0x70', None, '... slot * 0x70 ...'),
        (0x13AC384, 'add rdi, rax', None, '... rdi = the hit slot\'s flight record ...'),
        (0x13AC393, 'mov qword ptr [rbp - 0x60], rdi', None, '... kept at [rbp - 0x60]'),
        (0x13AC350, 'lea r14, [r15 + 0x4d040]', None, 'hit records ...'),
        (0x13AC3BC, 'imul rax, rdx, 0xc8', None, '... slot * 0xC8 ...'),
        (0x13AC3D0, 'add r14, rax', None, '... r14 = the hit slot\'s hit record'),
        (0x13AD058, 'cmp dword ptr [rdi + 0x50], 0', None, 'unit-driven?'),
        (0x13AD060, 'divss xmm1, dword ptr [rdi + 0x2c]', None, 'r = |velocity| / flight +0x2C ...'),
        (0x13AD065, 'movss xmm13, dword ptr [rip + {rip}]', 0x23C6D70, '... 1.0 ...'),
        (0x13AD06E, 'mulss xmm1, xmm1', None, '... r^2 ...'),
        (0x13AD076, 'subss xmm10, xmm1', None, '... (1 - r^2) ...'),
        (0x13AD07B, 'mulss xmm10, dword ptr [rip + {rip}]', 0x23C68C0, '... x 0.25 ...'),
        (0x13AD084, 'addss xmm10, xmm1', None, '... + r^2: speed factor 0.25 + 0.75 r^2'),
        (0x13AD089, 'je 0x13ad08f', None, 'ballistic: keep it ...'),
        (0x13AD08B, 'movaps xmm10, xmm13', None, '... unit-driven: 1.0'),
        (0x13AD29B, 'mov eax, dword ptr [r14 + 0xc]', None, 'hit +0x0C DamageInfo id, read per hit'),
        (0x13AD31E, 'movzx eax, word ptr [r14 + 0x18]', None, 'hit +0x18.. AP lanes, read per hit'),
        (0x13AD4D1, 'movss dword ptr [rsp + 0x30], xmm10', None, 'the speed factor -> 0x12A25B0 argument 7'),
        (0x13AD4E8, 'call 0x12a25b0', None, 'builds the hit\'s damage event at [rbp + 0x580]'),
        (0x13AD506, 'movss xmm0, dword ptr [rbp + 0x618]', None, 'event +0x98 (the damage) ...'),
        (0x13AD524, 'mulss xmm0, dword ptr [r14 + 0x34]', None, '... x hit +0x34 (DAMAGE multiplier) ...'),
        (0x13AD533, 'movss dword ptr [rbp + 0x618], xmm0', None, '... stored back'),
        (0x13AD550, 'movss xmm0, dword ptr [r14 + 0x38]', None, 'hit +0x38 (PENETRATION multiplier) ...'),
        (0x13AD556, 'mulss xmm0, dword ptr [rbx]', None, '... x each event penetration lane (+0x9C..+0xA8) ...'),
        (0x13AD55A, 'call 0x20bbb78', None, '... rounded ...'),
        (0x13AD55F, 'movss dword ptr [rbx], xmm0', None, '... stored back'),
        (0x13AD7C8, 'call 0x129dc30', None, 'damage values from the (multiplied) event'),
        (0x13AD88B, 'call 0x129dd30', None, 'damage produced from it'),
        (0x13ADBB4, 'movss xmm0, dword ptr [r14 + 0x20]', None, 'hit +0x20 penetration slowdown ...'),
        (0x13ADBC5, 'subsd xmm1, xmm0', None, '... 1 - it ...'),
        (0x13ADBD3, 'mulss xmm0, dword ptr [r13 + 0xc]', None, '... x the velocity ...'),
        (0x13ADBE5, 'movss dword ptr [r13 + 0xc], xmm0', None, '... stored (each penetration)'),
        (0x13AE52F, 'movss xmm2, dword ptr [rdi + 0x2c]', None, 'after a penetration: |velocity| / flight +0x2C again'),
        (0x13B0BF8, 'imul rdi, r15, 0x70', None, 'ricochet test: the slot\'s flight offset'),
        (0x13B0C4D, 'movss xmm0, dword ptr [rdi + rbx + 0x3064]', None, 'flight +0x24 mass ...'),
        (0x13B0C5C, 'comiss xmm0, dword ptr [rip + {rip}]', None, '... against a ricochet mass limit'),
        (0x13B117D, 'movss xmm2, dword ptr [rdi + rbx + 0x306c]', None, 'flight +0x2C: speed fraction after a ricochet'),
    ],
    'damageEvent': [
        (0x12A2695, 'movss xmm0, dword ptr [rsp + 0x80]', None, '0x12A25B0 argument 7 (the speed factor) ...'),
        (0x12A269E, 'movss dword ptr [rbx + 0x94], xmm0', None, '... event +0x94'),
        (0x12A26D9, 'movss dword ptr [rbx + 0x98], xmm1', None, 'event +0x98: the hit\'s damage'),
        (0x129DCA4, 'movss xmm0, dword ptr [rdi + 0x98]', None, 'damage values: event +0x98 (0 = no damage)'),
        (0x129CA2C, 'movss xmm11, dword ptr [r8 + 0x98]', None, 'a damage builder: event +0x98 ...'),
        (0x129CA35, 'mulss xmm11, dword ptr [r8 + 0x94]', None, '... x event +0x94 (the speed factor)'),
        (0x129CE52, 'mulss xmm0, dword ptr [rbx + 0x98]', None, 'another builder reads event +0x98'),
        (0x129D029, 'mulss xmm3, dword ptr [rbx + 0x98]', None, 'another builder reads event +0x98'),
        (0x129D291, 'mulss xmm0, dword ptr [rdi + 0x94]', None, 'another builder multiplies by event +0x94'),
    ],
}
CONSTANTS = {0x23C65B4: 0.001, 0x23C65A8: 0.0005, 0x23C6F1C: math.pi / 2, 0x23C6E28: 1.2, 0x23C6D70: 1.0,
    0x23C6538: 2.0 ** -32, 0x23C675C: 0.1, 0x23C68C0: 0.25}

# Members of interest: (record, offset) -> label. The census lists every access to them in the projectile code.
FLIGHT = {0x0C: 'velocity', 0x1C: 'gravity', 0x20: 'diameter', 0x24: 'mass', 0x28: 'dragConstant', 0x2C: 'speed',
    0x34: 'lifetime', 0x48: 'substeps'}
HIT = {0x0C: 'directDamage', 0x18: 'armorPenetration', 0x20: 'penetrationSlowdown', 0x34: 'damageMultiplier',
    0x38: 'penetrationMultiplier', 0x7C: 'impactExplosion'}
CENSUS_WINDOWS = [
    # (record, register, first, end, the assignments that make it that record) -- linear windows proven below
    ('flight', 'rdi', 0x13AB269, 0x13ABF32, 'update: rdi = the flight record (0x13AB262/0x13AB269) until the epilogue'),
    ('hit', 'r14', 0x13AC3D0, 0x13AF27F, 'hit processing: r14 = the hit record (0x13AC350/0x13AC3D0) until 0x13AF27F'),
]

VERDICTS = {
    'velocity': ('WRITABLE_PER_ROUND', 'flight', 0x0C, 'direction x launch speed (+ inherited)', 'the integrator '
        'loads it each step (0x13AAE7F) and stores it back; the actual flight speed and direction'),
    'speed': ('WRITABLE_PER_ROUND', 'flight', 0x2C, 'launch speed scalar (row +0x20, overrides, x extra +0x2C)',
        'the REFERENCE speed, not the flight speed: end below 0.1 x it (0x13AB6D5), direct-hit damage x (0.25 + '
        '0.75 (|v|/it)^2) (0x13AD060), after penetration (0x13AE52F) and ricochet (0x13B117D)'),
    'gravity': ('WRITABLE_PER_ROUND', 'flight', 0x1C, 'row +0x2C unchanged', 'integrator argument 5 every step '
        '(0x13AB589)'),
    'diameter': ('SPAWN_ONLY', 'flight', 0x20, 'row +0x18 unchanged; also folded into the drag constant',
        'no reader of the copy found (census); its only effect is the drag constant computed at spawn'),
    'mass': ('WRITABLE_PER_ROUND', 'flight', 0x24, 'row +0x24 x 0.001 (kg)', 'integrator argument 7 every step '
        '(0x13AB573) and the ricochet test (0x13B0C4D)'),
    'drag': ('WRITABLE_PER_ROUND', 'flight', 0x28, '(row +0x18 x 0.0005)^2 x pi/2 x 1.2 x row +0x28',
        'integrator argument 6 every step (0x13AB55E); write the constant, not a coefficient'),
    'substeps': ('WRITABLE_PER_ROUND', 'flight', 0x48, 'row +0x30 unchanged (u32)', 'integrator argument 8 and the '
        'substep time divisor every step (0x13AB557); 0 means no motion at all (0x13AAE4C): never write 0'),
    'lifetime': ('WRITABLE_PER_ROUND', 'flight', 0x34, 'row +0x34 x (1 + row +0x38 x r)', 'counted down every update '
        '(0x13AB82D); also rewritten by the fuse path (0x13AB751) and by weapon code (0x852EB6)'),
    'lifetime_variance': ('SPAWN_ONLY', None, None, 'consumed into flight +0x34', 'not stored'),
    'direct_damage': ('WRITABLE_PER_ROUND', 'hit', 0x0C, 'row +0x3C unchanged', 'read per direct hit (0x13AD29B)'),
    'armor_penetration': ('WRITABLE_PER_ROUND', 'hit', 0x18, 'the DamageInfo row\'s four u16 lanes',
        'read per hit (0x13AD31E) and reduced by each penetration (0x13AD211..0x13AD24C)'),
    'penetration_slowdown': ('WRITABLE_PER_ROUND', 'hit', 0x20, 'row +0x40 unchanged', 'velocity x (1 - it) at each '
        'penetration (0x13ADBB4)'),
    'impact_explosion': ('WRITABLE_PER_ROUND', 'hit', 0x7C, 'row +0x90 unchanged', 'research/projectile-pool'),
    'damage_multiplier': ('WRITABLE_PER_ROUND', 'hit', 0x34, 'extra +0x30, 1.0 without a block', 'event damage x it on '
        'each direct hit (0x13AD524), before every damage builder'),
    'penetration_multiplier': ('WRITABLE_PER_ROUND', 'hit', 0x38, 'extra +0x34, 1.0 without a block', 'each event '
        'penetration lane x it, rounded, on each direct hit (0x13AD550)'),
}


def f32(x: float) -> float:
    return struct.unpack('<f', struct.pack('<f', x))[0]


def operands_of(op: str):
    return re.findall(r'\[([^\]]+)\]', op)


def census(image) -> dict:
    """Every access to the members of interest in the projectile code: system-relative (any register pair with the
    record base folded into the displacement) and record-pointer-relative inside the proven register windows."""
    md = image.md
    code = list(md.disasm_lite(image.data[CODE_RANGE[0]:CODE_RANGE[1]], CODE_RANGE[0]))
    system_relative = []
    for rva, size, mnemonic, op in code:
        for mem in operands_of(op):
            m = re.search(r'\+ (0x[0-9a-f]+)$', mem)
            if not m or 'rsp' in mem or 'rbp' in mem or 'rip' in mem:
                continue
            disp = int(m.group(1), 16)
            for record, table in (('flight', FLIGHT), ('hit', HIT)):
                member = disp - RECORDS[record]['base']
                if record == 'flight' and member in (0x10, 0x14):
                    member = 0x0C  # velocity y / z
                if member not in table:
                    continue
                write = mem in op.split(',')[0] and mnemonic not in ('cmp', 'test', 'comiss', 'ucomiss')
                system_relative.append({'rva': rva, 'asm': mnemonic + ' ' + op, 'record': record,
                    'member': '0x%X' % member, 'label': table[member], 'access': 'write' if write else 'read'})
    windows = []
    for record, reg, first, end, why in CENSUS_WINDOWS:
        table = FLIGHT if record == 'flight' else HIT
        hits, reassigned = [], []
        for rva, size, mnemonic, op in code:
            if not first < rva < end:
                continue
            dest = op.split(',')[0].strip()
            if dest in (reg, reg.replace('r', 'e', 1) if reg == 'rdi' else reg + 'd') and mnemonic not in (
                    'cmp', 'test', 'push'):
                reassigned.append({'rva': rva, 'asm': mnemonic + ' ' + op})
            for mem in operands_of(op):
                m = re.fullmatch(reg + r'(?: \+ (0x[0-9a-f]+))?', mem)
                if m:
                    member = int(m.group(1), 16) if m.group(1) else 0
                    if member in table:
                        write = mem in dest and mnemonic not in ('cmp', 'test', 'comiss', 'ucomiss')
                        hits.append({'rva': rva, 'asm': mnemonic + ' ' + op, 'member': '0x%X' % member,
                            'label': table[member], 'access': 'write' if write else 'read'})
        windows.append({'record': record, 'register': reg, 'from': first, 'to': end, 'why': why,
            'reassigned': reassigned, 'accesses': hits})
    return {'range': list(CODE_RANGE), 'systemRelative': system_relative, 'registerWindows': windows}


def observe(name: str) -> dict:
    """Cross-check the destinations against live slots: every slot with a stored type holds its spawn-time copies
    (records stay until reuse); ballistic copies the game never rewrites must equal the transform of its row."""
    mem = base.Mem(name)
    try:
        system = mem.ptr(mem.game + SYSTEM_GLOBAL)
        if not system:
            return {'snapshot': name, 'system': None}
        counter = mem.u32(system + 0x30)
        types = struct.unpack('<2048I', mem.read(system + RECORDS['types']['base'], 8192))
        flags = struct.unpack('<2048H', mem.read(system + RECORDS['flags']['base'], 4096))
        flight = mem.read(system + RECORDS['flight']['base'], 2048 * 0x70)
        hit = mem.read(system + RECORDS['hit']['base'], 2048 * 0xC8)
        rows: dict[int, bytes | None] = {}
        tally = {k: [0, 0] for k in ('gravity', 'diameter', 'mass', 'drag', 'substeps', 'directDamage',
            'penetrationSlowdown', 'impactExplosion')}
        mismatches, damage_mult, pen_mult, speed_ratio = [], {}, {}, []
        spawned = 0
        for slot, t in enumerate(types):
            if not 0 < t < TYPE_COUNT:
                continue
            if t not in rows:
                p = mem.ptr(mem.game + ROW_TABLE + 8 * t)
                raw = mem.read(p, ROW_SIZE) if p else None
                rows[t] = raw if raw and struct.unpack_from('<I', raw, 0)[0] == t else None
            row = rows[t]
            if row is None:
                continue
            spawned += 1
            fl = flight[slot * 0x70:(slot + 1) * 0x70]
            hr = hit[slot * 0xC8:(slot + 1) * 0xC8]
            rf = lambda o: struct.unpack_from('<f', row, o)[0]  # noqa: E731
            expect = {
                'gravity': (struct.unpack_from('<I', fl, 0x1C)[0], struct.unpack_from('<I', row, 0x2C)[0]),
                'diameter': (struct.unpack_from('<I', fl, 0x20)[0], struct.unpack_from('<I', row, 0x18)[0]),
                'mass': (struct.unpack_from('<f', fl, 0x24)[0], f32(rf(0x24) * f32(0.001))),
                'drag': (struct.unpack_from('<f', fl, 0x28)[0], f32(f32(f32(f32(f32(rf(0x18) * f32(0.0005)) ** 2)
                    * f32(math.pi / 2)) * f32(1.2)) * rf(0x28))),
                'substeps': (struct.unpack_from('<I', fl, 0x48)[0], struct.unpack_from('<I', row, 0x30)[0]),
                'directDamage': (struct.unpack_from('<I', hr, 0x0C)[0], struct.unpack_from('<I', row, 0x3C)[0]),
                'penetrationSlowdown': (struct.unpack_from('<I', hr, 0x20)[0], struct.unpack_from('<I', row, 0x40)[0]),
                'impactExplosion': (struct.unpack_from('<I', hr, 0x7C)[0], struct.unpack_from('<I', row, 0x90)[0]),
            }
            for k, (got, want) in expect.items():
                same = got == want or (isinstance(got, float) and math.isclose(got, want, rel_tol=1e-6, abs_tol=1e-12))
                tally[k][0 if same else 1] += 1
                if not same and len(mismatches) < 12:
                    mismatches.append({'slot': slot, 'type': t, 'member': k, 'stored': got, 'fromRow': want})
            dm = round(struct.unpack_from('<f', hr, 0x34)[0], 4)
            pm = round(struct.unpack_from('<f', hr, 0x38)[0], 4)
            damage_mult[str(dm)] = damage_mult.get(str(dm), 0) + 1
            pen_mult[str(pm)] = pen_mult.get(str(pm), 0) + 1
            if rf(0x20) > 0:
                speed_ratio.append(struct.unpack_from('<f', fl, 0x2C)[0] / rf(0x20))
        ratios = sorted(round(r, 3) for r in speed_ratio)
        return {'snapshot': name, 'system': True, 'active': mem.read(system + 0x28, 1)[0], 'counter': counter,
            'inFlight': sum(1 for f in flags if f & 2), 'slotsWithType': spawned,
            'matches': {k: {'equal': v[0], 'differ': v[1]} for k, v in tally.items()}, 'mismatches': mismatches,
            'damageMultiplier': damage_mult, 'penetrationMultiplier': pen_mult,
            'storedSpeedOverRowSpeed': {'min': ratios[0], 'max': ratios[-1],
                'equalToRow': sum(1 for r in ratios if r == 1.0), 'count': len(ratios)} if ratios else None}
    finally:
        mem.close()


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[-1])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    if image.data[SPAWN:SPAWN + 4].hex() != '40555641':
        raise ValueError('SpawnProjectile prologue moved')
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    constants = []
    for rva, value in CONSTANTS.items():
        got = struct.unpack_from('<f', image.data, rva)[0]
        if not math.isclose(got, value, rel_tol=1e-6):
            raise ValueError('constant at %X is %r, not %r' % (rva, got, value))
        constants.append({'rva': rva, 'bytes': image.data[rva:rva + 4].hex(), 'value': got})
    ricochet_limit = 0x13B0C5C + 7 + struct.unpack_from('<i', image.data, 0x13B0C5C + 3)[0]
    constants.append({'rva': ricochet_limit, 'bytes': image.data[ricochet_limit:ricochet_limit + 4].hex(),
        'value': struct.unpack_from('<f', image.data, ricochet_limit)[0], 'role': 'ricochet mass limit (kg)'})
    slowdown_one = 0x13ADBBA + 8 + struct.unpack_from('<i', image.data, 0x13ADBBA + 4)[0]
    if struct.unpack_from('<d', image.data, slowdown_one)[0] != 1.0:
        raise ValueError('penetration slowdown is not 1 - x')
    constants.append({'rva': slowdown_one, 'bytes': image.data[slowdown_one:slowdown_one + 8].hex(), 'value': 1.0,
        'role': 'double 1.0 of the penetration slowdown'})
    relocation = {name: base.verify_pins_live(name, pins + constants, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    cen = census(image)
    for w in cen['registerWindows']:
        if w['reassigned']:
            raise ValueError('%s is reassigned inside its window: %r' % (w['register'], w['reassigned']))
    found = {(a['record'], a['label']) for a in cen['systemRelative']} | {
        (w['record'], a['label']) for w in cen['registerWindows'] for a in w['accesses']}
    # SpawnProjectile's two stores: the record zeroing (0x13A9C52..0x13A9CA0, movups) and the copy.
    if any(a['label'] == 'diameter' and a['rva'] not in (0x13A9C64, 0x13AA055) for a in cen['systemRelative']):
        raise ValueError('a new reader of the diameter copy appeared')
    if any(a['label'] == 'diameter' for w in cen['registerWindows'] for a in w['accesses']):
        raise ValueError('a register-relative reader of the diameter copy appeared')
    for need in (('flight', 'gravity'), ('flight', 'mass'), ('flight', 'dragConstant'), ('flight', 'speed'),
            ('flight', 'substeps'), ('flight', 'lifetime'), ('hit', 'damageMultiplier'),
            ('hit', 'penetrationSlowdown'), ('hit', 'directDamage')):
        if need not in found:
            raise ValueError('the census lost %r' % (need,))
    multiplier_writes = [a for a in cen['systemRelative'] if a['label'] in ('damageMultiplier', 'penetrationMultiplier')]
    multiplier_window = [a for w in cen['registerWindows'] for a in w['accesses']
        if a['label'] in ('damageMultiplier', 'penetrationMultiplier')]
    if multiplier_writes or sorted(a['rva'] for a in multiplier_window) != [0x13AD524, 0x13AD550]:
        raise ValueError('hit +0x34/+0x38 gained another accessor: %r %r' % (multiplier_writes, multiplier_window))

    observations = [observe(name) for name in SNAPSHOTS]
    for o in observations:
        if not o.get('system'):
            continue
        for k in ('gravity', 'diameter', 'mass', 'drag', 'substeps', 'penetrationSlowdown'):
            if o['matches'][k]['differ']:
                raise ValueError('%s: a stored %s differs from its row transform: %r' % (o['snapshot'], k,
                    o['mismatches']))

    layout = {
        'flight': {**RECORDS['flight'], 'members': {
            '0x00': 'position (vec3)', '0x0C': 'velocity (vec3) = direction x launch speed (+ extra +0x20, + source '
            'velocity with row +0xF0 bit 0)', '0x18': 'carried step time (extra +0x00)', '0x1C': 'gravity multiplier '
            '(row +0x2C)', '0x20': 'diameter mm (row +0x18)', '0x24': 'mass kg (row +0x24 x 0.001)', '0x28': 'drag '
            'constant (row +0x18 x 0.0005)^2 x pi/2 x 1.2 x row +0x28', '0x2C': 'launch speed scalar (reference '
            'speed)', '0x30': 'distance travelled', '0x34': 'remaining lifetime', '0x44': 'row +0xE4', '0x48':
            'substep count (row +0x30, u32)', '0x4C': 'resource handle (row +0x80)', '0x50': 'driving unit (extra '
            '+0x28)', '0x54': 'extra +0x1B flag', '0x58': '-1 at spawn', '0x5C': '1 at spawn (byte)', '0x60':
            'extra +0x38 (u64)', '0x68': 'extra +0x40'}},
        'hit': {**RECORDS['hit'], 'members': {
            '0x00': 'creditor peer', '0x08': 'owner entity', '0x0C': 'DamageInfo id (row +0x3C)', '0x10': 'row +0xE8',
            '0x14': 'descriptor +0x28', '0x18': 'AP lanes u16 x4 (DamageInfo +0x0C/+0x10/+0x14/+0x18)', '0x20':
            'penetration slowdown (row +0x40)', '0x24': 'source component +0x54/+0x58/+0x5C/+0x60 (+0x24..+0x30)',
            '0x34': 'damage multiplier (extra +0x30, else 1.0)', '0x38': 'penetration multiplier (extra +0x34, else '
            '1.0)', '0x70': 'row +0xA8', '0x74': 'row +0xAC', '0x7C': 'impact explosion (row +0x90)', '0x80':
            'expiry explosion (row +0x9C)', '0x84': 'row +0xEC', '0x88': 'row +0x88', '0x8C': 'row +0x98 (fuse time, '
            'copied into the lifetime by 0x13AB751)', '0x90': 'row +0xA4', '0x94': 'extra +0x04', '0x9C': 'row +0xB0 '
            '(when extra +0x1A, or no block)', '0xA0': 'row +0xB4 (ricochet angle)', '0xA4': 'row +0xB8', '0xA8':
            'row +0xBC', '0xAC': 'row +0xC0', '0xB0': 'row +0xC4', '0xBA': 'row +0x8C bit 0'}},
        'source': {**RECORDS['source'], 'members': {'0x00': 'row +0x94', '0x04': 'row +0xA0', '0x08': 'resolved '
            'owner', '0x0C': 'source entity', '0x10': 'extra +0x10 list (<= 4 u32)', '0x20': 'replication flag'}},
        'extra2': {**RECORDS['extra2'], 'members': {'0x0C': 'extra +0x50 else row +0xD0', '0x10': 'extra +0x54 else '
            'row +0xD4', '0x14': 'row +0xDC', '0x18': '-1.0', '0x1C': 'row +0xD8 or -1.0', '0x20': 'row +0xE0 bit 0',
            '0x24': 'row +0xC8', '0x2C': 'row +0xCC', '0x30': 'extra +0x44', '0x34': 'extra +0x48 resolved',
            '0x38': 'extra +0x4C'}},
    }
    extra = {'register': 'r13 (SpawnProjectile third argument; every read is null-guarded)', 'members': {
        '0x00': 'f32 carried step time -> flight +0x18 (0 without a block)',
        '0x04': 'u32 -> hit +0x94; also selects the replication call (0x62CC80 vs 0x62C930) when the source replicates',
        '0x08': 'u32 count of the +0x10 list (<= 4)', '0x10': 'u32* list -> source record +0x10..',
        '0x18': 'byte: slot flag 0x20 is set unless a block has it 0', '0x19': 'byte: particle effect row +0x50 '
        'instead of +0x48', '0x1A': 'byte: hit +0x9C = row +0xB0 only when set (no block: row +0xB0)',
        '0x1B': 'byte -> flight +0x54', '0x20': 'vec3* added to the launch velocity',
        '0x28': 'u32 driving unit -> flight +0x50 (unit-driven shot)', '0x2C': 'f32 SPEED multiplier (launch speed, '
        'stored speed and velocity)', '0x30': 'f32 DAMAGE multiplier -> hit +0x34', '0x34': 'f32 PENETRATION '
        'multiplier -> hit +0x38', '0x38': 'u64 -> flight +0x60', '0x40': 'u32 -> flight +0x68',
        '0x44': 'u32 -> extra2 +0x30', '0x48': 'u32 (resolved by 0x12556E0) -> extra2 +0x34', '0x4C': 'f32 -> extra2 '
        '+0x38', '0x50': 'u32 -> extra2 +0x0C (0: row +0xD0)', '0x54': 'u32 -> extra2 +0x10 (0: row +0xD4)'},
        'size': 'at least 0x58', 'writers': 'the projectile weapon fire path fills +0x2C/+0x30/+0x34 from the charge '
        'multipliers (research/railgun-charge, 0x616558..0x6165B2)'}
    verdicts = {k: {'verdict': v[0], 'record': v[1], 'offset': None if v[2] is None else '0x%X' % v[2],
        'systemOffset': None if v[1] is None else '0x%X' % (RECORDS[v[1]]['base'] + v[2]),
        'stride': None if v[1] is None else RECORDS[v[1]]['stride'], 'transform': v[3], 'readLater': v[4]}
        for k, v in VERDICTS.items()}
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'gameDllSha256': base.PROFILE_DLL_SHA,
        'spawn': {'rva': SPAWN, 'signature': 'SpawnProjectile(system, descriptor, extra /* may be null */)'},
        'system': {'global': SYSTEM_GLOBAL}, 'records': layout, 'extra': extra, 'verdicts': verdicts,
        'damageMultiplier': {
            'verdict': 'WRITABLE_PER_ROUND', 'member': 'hit +0x34 (system + 0x4D074 + slot * 0xC8), f32',
            'semantics': 'each direct hit: event damage (+0x98, from the hit record\'s DamageInfo and the speed '
                'factor) x hit +0x34, before damage values are built; explosions are separate (RequestExplosion) and '
                'not scaled', 'otherAccessors': 'none in the projectile code besides SpawnProjectile\'s two stores',
            'speedFactor': 'direct-hit damage is also x (0.25 + 0.75 (|velocity| / flight +0x2C)^2): a faster '
                'velocity without a matching flight +0x2C raises damage (no clamp found)'},
        'speed': {'storedAs': ['flight +0x0C velocity vector (the flight)', 'flight +0x2C scalar (reference: end '
            'threshold 0.1 x, damage speed factor, penetration and ricochet stops)'], 'rule': 'to change a shot\'s '
            'speed write both: velocity x k and +0x2C x k (keeps the damage speed factor at 1)'},
        'proofs': proofs, 'constants': constants, 'census': cen, 'pinnedBytesMismatchPerSnapshot': relocation,
        'observations': observations,
        'unproven': [
            'Timing: whether a Runtime write lands before the shot\'s first update step (SpawnProjectile and the '
            'update order relative to the Runtime frame hook); a later write only changes the rest of its flight.',
            'r13 at 0x13ADBD3 (the penetration slowdown) is the flight record by linear reading (loaded from '
            '[rbp - 0x60] at 0x13AD520, restored to [rbp - 0x78] at 0x13ADC03), not by a mechanical CFG proof.',
            'The diameter copy (flight +0x20): no reader in the projectile code or the proven register windows; a '
            'reader outside the projectile functions through a passed flight pointer is not excluded.',
            'The meaning of extra +0x04, +0x18..+0x1B, +0x38..+0x54 and of the extra2 record.',
            'Damage builders: 5 of the 6 kinds of 0x129DC30 read event +0x98 directly (0x129D9A0 not traced); the '
            'damage multiplier\'s live effect (and any clamp downstream) needs a live probe.',
            'Multiplayer: each machine simulates its own copy; a per-round write on one machine changes that '
            'machine\'s copy only (the owner\'s hit is the one that damages, research/projectile-homing).'],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'pins': len(pins), 'constants': len(constants),
        'census': {'systemRelative': len(cen['systemRelative']),
            'windows': [len(w['accesses']) for w in cen['registerWindows']]},
        'observations': [{k: o.get(k) for k in ('snapshot', 'counter', 'slotsWithType', 'matches', 'damageMultiplier',
            'storedSpeedOverRowSpeed')} for o in observations]}, indent=1))


if __name__ == '__main__':
    main()
