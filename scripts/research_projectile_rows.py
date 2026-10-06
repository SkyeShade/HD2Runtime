"""Runtime-owned custom projectile rows (the hybrid-row architecture of docs/custom-projectile-rows.md). Read-only.

Proves on build F5FEE03DCFDB, from the game.dll image of the retained mission snapshots, the pinned datalibrary and
its type library:

1. SpawnProjectile. game.dll 0x13A9830 SpawnProjectile(system, const descriptor *, const extra *) inserts one
   projectile into the system's 2048-slot pool and returns the slot (0 at once when the system is inactive, +0x28).
   The descriptor it reads: +0x00 position pointer, +0x08 direction pointer, +0x10 ProjectileInfo row pointer, +0x18
   source entity, +0x1C owner entity, +0x20 creditor peer (u64), +0x28 kind; nothing past +0x2C. Every use of the
   third argument is null-guarded (15 tests of r13; the one callee it is passed to tests it too), so null means "no
   extra parameters". FireProjectile's plain path (0x13A9700) builds exactly this descriptor: row = settings[type],
   source = owner = the entity, creditor = the peer that owns the entity (0x129C690: avatar -> network id -> peer; 0
   for any other entity), kind 2.
2. The row is not retained. SpawnProjectile reads the row through the descriptor while it runs: it stores row+0 (the
   ProjectileType) in the system's per-slot type array (+0xE5040) and copies what it needs into the slot's records
   (+0x3C DamageInfoType into the record +0x0C with that DamageInfo's armour penetration; +0x70/+0x78 into the record;
   the +0x48 (or +0x50) and +0x60 resources created with the spawn pose through the engine world API +0x280, their
   handles kept in the slot's effect record with +0x58 and +0x68).
3. Late lookups. The stored type is written once (SpawnProjectile 0x13A9BB5) and read back at exactly five places
   (0x13A8B20, 0x13ABCB1, 0x13AD834, 0x13AD8E6, 0x13B3204), each of which indexes the vanilla settings table at once.
   Through them, and only through them, the game reads: per frame +0xF4 (0x13ABDAD) and, in an out-of-line block of
   the same update, +0xF8 (0x13AC0D8); on a damage hit +0xFC bit 0 (0x13AD858, 0x13AD90A); in the unit hand-off +0xFC
   bit 1, +0x100..+0x10B and +0x80 (0x13A8B41 .. 0x13A8BE4); on impact +0xF0 bit 12 (0x13B322F). These are the only
   row members reread through a spawned projectile's stored vanilla type. Type 0 selects a default row 0x110 bytes
   before the table (game+0x37C7560), so a typeless row would make every late lookup read that default row: a
   Runtime-owned row must keep a vanilla type.
4. Configured-type readers. Every other settings-table reader takes its type from a weapon, stratagem or entity's
   configured data, never from a pool slot: the weapon firing path (+0x1C pellet count 0x75B95F, +0x3C 0x67FCD1),
   ProjectileWeapon and other component lookups (0x515100, 0x514B40, 0x5043C0: +0x20 at 0x6BD49F and 0x8A3883, the
   weapon's own +0xF0 at 0x851B89), the StratagemSettings weapon lists (game+0x37CB600: +0x90 at 0x7B8460, 0xA168C5,
   0xA16B03, 0xB55768, 0xB5D865) and the weapon statistics queries (+0x04, +0x18..+0x30, +0x3C, +0x90). A read there
   does not make a member late-bound.
5. Every by-type reader of the settings table in game.dll's code (image-base-relative and RIP-relative loads), with
   the members it reads in straight-line code, is the census. A member is COPIED_AT_SPAWN (may differ from the base)
   only when SpawnProjectile copies it, it is not a late lookup, and no census reader outside the reviewed
   configured-type functions reads it; this script fails when the census finds a new reader of such a member.
6. Row size 272: the type library's ProjectileInfo, the ProjectileSettings stride and the default row.
7. What SpawnProjectile does with the ballistics and explosion members (pinned): the speed +0x20 goes into the slot's
   ballistics record (0x13A9C95 -> 0x13AA0C3); gravity +0x2C is copied (0x13AA046); mass +0x24 is in grams (x 0.001,
   0x13AA066); +0x18 is the diameter in millimetres (x 0.0005 -> radius in metres, squared, x pi/2 x 1.2 air density
   x the drag coefficient +0x28 = the drag constant, 0x13AA095..0x13AA0D5); +0x38 is the random lifetime variance
   (0x13AA110); the penetration slowdown +0x40 is copied (0x13AA673); the impact explosion +0x90 is copied into the hit
   record (0x13AA646) and hit processing reads that copy (0x13AD7FD).
8. Visuals: +0x48 and +0x60 are particle effects created with the spawn pose; their only per-spawn variables are
   "start" and "end" (thin hashes 0x88F1AF97 / 0xE783D2BD), set to the slot position. No member is a colour or tint:
   colour is baked into the effect asset. The per-call extra parameters carry speed and damage multipliers, not
   colour.

Output: research/projectile-rows-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import sys

import capstone
from capstone.x86 import X86_OP_MEM, X86_OP_REG

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import research_entity_authoring as entity_research  # noqa: E402
import research_projectile_builder as builder  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/projectile-rows-F5FEE03DCFDB.json'
SNAPSHOTS = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
SPAWN = 0x13A9830
SPAWN_PROLOGUE_END = 0x13A9863        # through the active-system test and its branch
SYSTEM_GLOBAL, TABLE, DEFAULT_ROW, TYPE_COUNT = 0x347CEA8, 0x37C7670, 0x37C7560, 351
TYPE_ARRAY = 0xE5040
ROW_SIZE = 272
# The development proof's rows (docs/custom-projectile-rows.md): LAS-58 Talon base, PLAS-1 Scorcher spawn effect,
# RS-422 Railgun direct damage.
PROOF_ROWS = {'base': 144, 'effect': 142, 'damage': 186}

GAME_PROOFS = {
    'spawn': [
        (0x13A9830, 'push rbp', None, 'SpawnProjectile(system, const descriptor *, const extra *) -> pool slot'),
        (0x13A9854, 'cmp byte ptr [rcx + 0x28], 0', None, 'returns 0 unless the projectile system is active'),
        (0x13A9858, 'mov r13, r8', None, 'r13 = extra parameters (argument 3, may be null)'),
        (0x13A985B, 'mov r14, rdx', None, 'r14 = the spawn descriptor (argument 2)'),
        (0x13A985E, 'mov rsi, rcx', None, 'rsi = the projectile system (argument 1)'),
        (0x13A9A04, 'mov rax, qword ptr [r14]', None, 'descriptor +0x00: position pointer'),
        (0x13A9990, 'mov rax, qword ptr [r14 + 8]', None, 'descriptor +0x08: direction pointer'),
        (0x13A9B0D, 'mov rax, qword ptr [r14 + 0x10]', None, 'descriptor +0x10: the ProjectileInfo row'),
        (0x13A9BB3, 'mov ecx, dword ptr [rax]', None, 'row +0x00: the ProjectileType'),
        (0x13A9BB5, 'mov dword ptr [rsi + r12*4 + 0xe5040], ecx', None, 'stored in the per-slot type array'),
        (0x13A9C9A, 'mov eax, dword ptr [r14 + 0x18]', None, 'descriptor +0x18: source entity'),
        (0x13AA227, 'mov ecx, dword ptr [r14 + 0x1c]', None, 'descriptor +0x1C: owner entity'),
        (0x13AA5DB, 'mov rdx, qword ptr [r14 + 0x20]', None, 'descriptor +0x20: creditor peer'),
        (0x13AAA2B, 'mov eax, dword ptr [r14 + 0x28]', None, 'descriptor +0x28: kind'),
        (0x13AA7BC, 'mov rdx, r13', None, 'the extra parameters passed to one callee'),
        (0x13B28B4, 'test rdx, rdx', None, 'which null-checks them'),
    ] + [(rva, 'test r13, r13', None, 'extra parameters null-guarded') for rva in (
        0x13A9A5B, 0x13A9DA7, 0x13A9DEB, 0x13A9E87, 0x13AA024, 0x13AA1AE, 0x13AA567, 0x13AA5C5, 0x13AA792, 0x13AA95B,
        0x13AAA50, 0x13AAA6F, 0x13AAAEE, 0x13AAB12, 0x13AAB83)],
    'copied': [
        (0x13AA62F, 'mov ecx, dword ptr [rax + 0x3c]', None, 'row +0x3C DamageInfoType read at spawn'),
        (0x13AA632, 'mov dword ptr [rdi + 0xc], ecx', None, 'stored in the projectile record +0x0C'),
        (0x13AA684, 'mov edx, dword ptr [rax + 0x3c]', None, 'its DamageInfo row looked up at spawn'),
        (0x13AA692, 'movzx eax, word ptr [rax + 0xc]', None, 'armour penetration copied from the DamageInfo row'),
        (0x13AA696, 'mov word ptr [rdi + 0x18], ax', None, 'into the projectile record +0x18'),
        (0x13A9E0A, 'mov rdx, qword ptr [rax + 0x80]', None, 'row +0x80 unit resource read at spawn'),
        (0x13A9E2C, 'call rax', None, 'spawned through the engine world API +0x40 with the spawn pose'),
        (0x13AA86A, 'mov rcx, qword ptr [rax + 0x78]', None, 'row +0x78 read at spawn'),
        (0x13AA86E, 'mov qword ptr [rdi + 0x60], rcx', None, 'stored in the projectile record +0x60'),
        (0x13AA876, 'mov rcx, qword ptr [rax + 0x70]', None, 'row +0x70 read at spawn'),
        (0x13AA87A, 'mov qword ptr [rdi + 0x68], rcx', None, 'stored in the projectile record +0x68'),
        (0x13AAB92, 'mov rdx, qword ptr [rax + 0x50]', None, 'row +0x50: the spawn effect when the extra parameters '
            'ask for the alternate one'),
        (0x13AAB9F, 'mov rdx, qword ptr [rax + 0x48]', None, 'row +0x48: the spawn effect resource'),
        (0x13AABB7, 'mov rax, qword ptr [rcx + 0x280]', None, 'engine world API +0x280'),
        (0x13AABC1, 'call rax', None, 'called with the resource and the spawn pose; returns a handle'),
        (0x13AABCA, 'mov rcx, qword ptr [rax + 0x68]', None, 'row +0x68 read at spawn'),
        (0x13AABCE, 'mov qword ptr [rsi + rdi*8 + 0xd1040], rcx', None, 'stored in the slot effect record'),
        (0x13AABD6, 'mov dword ptr [rsi + rdi*8 + 0xd1050], r8d', None, 'with the spawn effect handle'),
        (0x13AABF1, 'mov ecx, dword ptr [rax + 0x58]', None, 'row +0x58 read at spawn'),
        (0x13AABFB, 'mov dword ptr [rsi + rdi*8 + 0xd1054], ecx', None, 'stored in the slot effect record'),
        (0x13AAC11, 'mov rdx, qword ptr [rax + 0x48]', None, 'row +0x48 again: effect variables (API +0x358)'),
        (0x13AACC6, 'mov rdx, qword ptr [rax + 0x60]', None, 'row +0x60: a second spawn effect resource'),
        (0x13AACDD, 'mov r9, qword ptr [r8 + 0x280]', None, 'engine world API +0x280'),
        (0x13AACED, 'mov dword ptr [rsi + rdi*8 + 0xd104c], ebx', None, 'its handle stored in the slot effect record'),
        (0x13A9C95, 'movss xmm6, dword ptr [rax + 0x20]', None, 'row +0x20: the launch speed'),
        (0x13AA0C3, 'movss dword ptr [r15 + rsi + 0x306c], xmm6', None, 'speed -> slot ballistics record +0x306C'),
        (0x13AA043, 'mov ecx, dword ptr [rax + 0x2c]', None, 'row +0x2C: gravity'),
        (0x13AA046, 'mov dword ptr [r15 + rsi + 0x305c], ecx', None, 'gravity -> ballistics record +0x305C'),
        (0x13AA061, 'movss xmm0, dword ptr [rax + 0x24]', None, 'row +0x24: mass'),
        (0x13AA066, 'mulss xmm0, dword ptr [rip + {rip}]', 0x23C65B4, 'x 0.001: grams -> kilograms'),
        (0x13AA06E, 'movss dword ptr [r15 + rsi + 0x3064], xmm0', None, 'mass -> ballistics record +0x3064'),
        (0x13AA052, 'mov ecx, dword ptr [rax + 0x18]', None, 'row +0x18: diameter'),
        (0x13AA055, 'mov dword ptr [r15 + rsi + 0x3060], ecx', None, 'diameter -> ballistics record +0x3060'),
        (0x13AA095, 'movss xmm0, dword ptr [rax + 0x18]', None, 'row +0x18 again, for the drag constant'),
        (0x13AA09A, 'mulss xmm0, dword ptr [rip + {rip}]', 0x23C65A8, 'x 0.0005: millimetres of diameter -> metres of '
            'radius'),
        (0x13AA0A2, 'mulss xmm0, xmm0', None, 'squared'),
        (0x13AA0A6, 'mulss xmm0, dword ptr [rip + {rip}]', 0x23C6F1C, 'x pi/2'),
        (0x13AA0AE, 'mulss xmm0, dword ptr [rip + {rip}]', 0x23C6E28, 'x 1.2 (air density)'),
        (0x13AA0B6, 'mulss xmm0, dword ptr [rax + 0x28]', None, 'x row +0x28: the drag coefficient'),
        (0x13AA0D5, 'movss dword ptr [r15 + rsi + 0x3068], xmm0', None, 'drag constant -> ballistics record +0x3068'),
        (0x13AA103, 'movss xmm2, dword ptr [rcx + 0x34]', None, 'row +0x34: lifetime'),
        (0x13AA110, 'mulss xmm1, dword ptr [rcx + 0x38]', None, 'x row +0x38: the random lifetime variance'),
        (0x13AA11D, 'mulss xmm0, dword ptr [rip + {rip}]', 0x23C6538, 'a random number scaled to [0, 1)'),
        (0x13AA673, 'mov ecx, dword ptr [rax + 0x40]', None, 'row +0x40: penetration slowdown'),
        (0x13AA676, 'mov dword ptr [rdi + 0x20], ecx', None, 'penetration slowdown -> the hit record +0x20'),
        (0x13AA646, 'mov ecx, dword ptr [rax + 0x90]', None, 'row +0x90: the impact explosion'),
        (0x13AA64C, 'mov dword ptr [rdi + 0x7c], ecx', None, 'impact explosion -> the hit record +0x7C'),
        (0x13AD7FD, 'cmp dword ptr [r14 + 0x7c], 0', None, 'hit processing reads the impact explosion from that copy'),
    ],
    'visual': [
        (0x13AABEB, 'mov r8d, 0x88f1af97', None, 'particle variable "start" (thin hash)'),
        (0x13AAC0A, 'mov r9, qword ptr [rcx + 0x358]', None, 'engine world API +0x358: find a particle variable'),
        (0x13AAC22, 'mov r8d, 0xe783d2bd', None, 'particle variable "end" (thin hash)'),
        (0x13AAC7C, 'call qword ptr [r10 + 0x368]', None, 'engine world API +0x368: set it to the slot position'),
    ],
    'late': [
        (0x13ABCB1, 'mov eax, dword ptr [rbx + rsi*4 + 0xe5040]', None, 'per frame: the slot\'s stored type'),
        (0x13ABCBC, 'lea r15, [rip + {rip}]', DEFAULT_ROW, 'type 0: the default row'),
        (0x13ABCCC, 'mov r15, qword ptr [rcx + rax*8 + 0x37c7670]', None, 'else the vanilla row of the stored type'),
        (0x13ABDAD, 'mov edx, dword ptr [r15 + 0xf4]', None, 'row +0xF4 collision filter, every frame'),
        (0x13AD834, 'mov eax, dword ptr [r15 + rdi*4 + 0xe5040]', None, 'damage hit: the slot\'s stored type'),
        (0x13AD850, 'mov rax, qword ptr [rcx + rax*8 + 0x37c7670]', None, 'its vanilla row'),
        (0x13AD858, 'test byte ptr [rax + 0xfc], 1', None, 'row +0xFC bit 0 on a damage hit'),
        (0x13AD902, 'mov rax, qword ptr [rcx + rax*8 + 0x37c7670]', None, 'the same, second hit path'),
        (0x13AD90A, 'test byte ptr [rax + 0xfc], 1', None, 'row +0xFC bit 0'),
        (0x13A8B41, 'test byte ptr [rax + 0xfc], 2', None, 'unit hand-off: row +0xFC bit 1'),
        (0x13A8BC4, 'movsd xmm0, qword ptr [rax + 0x100]', None, 'unit hand-off: row +0x100..+0x107'),
        (0x13A8BD2, 'mov eax, dword ptr [rax + 0x108]', None, 'unit hand-off: row +0x108..+0x10B'),
        (0x13A8BE4, 'mov rax, qword ptr [rdx + 0x80]', None, 'unit hand-off: row +0x80 unit resource'),
        (0x13B3204, 'mov eax, dword ptr [r15 + rcx*4 + 0xe5040]', None, 'impact: the slot\'s stored type'),
        (0x13B3221, 'mov rax, qword ptr [r13 + rax*8 + 0x37c7670]', None, 'its vanilla row'),
        (0x13B3229, 'mov r8d, 0x1000', None, 'impact: bit 12'),
        (0x13B322F, 'test word ptr [rax + 0xf0], r8w', None, 'impact: row +0xF0 bit 12'),
        (0x13A8B20, 'mov ecx, dword ptr [r15 + r13*4 + 0xe5040]', None, 'unit hand-off: the slot\'s stored type'),
        (0x13AD8E6, 'mov eax, dword ptr [r15 + rdi*4 + 0xe5040]', None, 'second hit path: the slot\'s stored type'),
        (0x13AC0D8, 'mov ecx, dword ptr [r15 + 0xf8]', None, 'per frame, out-of-line block: row +0xF8 overlap '
            'filter'),
    ],
    'fire': [
        (0x851B21, 'mov r11d, 0x1000', None, 'a weapon\'s configured impact effect: bit 12'),
        (0x851B89, 'test word ptr [rax + 0xf0], r11w', None, 'row +0xF0 bit 12 of a component\'s configured type '
            '(0x5043C0), not a stored type'),
        (0x75B95F, 'mov eax, dword ptr [rax + 0x1c]', None, 'weapon firing: row +0x1C pellet count of the weapon\'s '
            'configured type'),
        (0x67FC39, 'mov eax, dword ptr [r14 + 0x80]', None, 'weapon firing: the weapon\'s configured projectile type'),
        (0x67FC58, 'mov rax, qword ptr [rcx + rax*8]', None, 'its vanilla row'),
        (0x67FCD1, 'mov eax, dword ptr [r14 + 0x3c]', None, 'weapon firing: row +0x3C of the configured type'),
    ],
    'template': [
        (0x13A970C, 'lea rcx, [rip + {rip}]', DEFAULT_ROW, 'FireProjectile type 0: the default row'),
        (0x13A9715, 'lea rcx, [rip + {rip}]', TABLE, 'FireProjectile: the settings table'),
        (0x13A9722, 'mov qword ptr [rbp - 0x60], rcx', None, 'descriptor +0x10 = the row'),
        (0x13A9726, 'mov qword ptr [rbp - 0x50], rax', None, 'descriptor +0x20 = the creditor of the entity'),
        (0x13A9734, 'lea rdx, [rbp - 0x70]', None, 'argument 2 = the descriptor'),
        (0x13A9738, 'mov rcx, r12', None, 'argument 1 = the projectile system'),
        (0x13A975D, 'mov qword ptr [rbp - 0x70], r13', None, 'descriptor +0x00 = position pointer'),
        (0x13A9761, 'mov qword ptr [rbp - 0x68], r14', None, 'descriptor +0x08 = direction pointer'),
        (0x13A9765, 'mov dword ptr [rbp - 0x48], 2', None, 'descriptor +0x28 = kind 2'),
        (0x13A976C, 'mov dword ptr [rbp - 0x58], ebx', None, 'descriptor +0x18 = source = the entity'),
        (0x13A976F, 'mov dword ptr [rbp - 0x54], ebx', None, 'descriptor +0x1C = owner = the entity'),
        (0x13A9796, 'call 0x13a9830', None, 'SpawnProjectile'),
        (0x129C741, 'call 0xfd9af0', None, 'creditor lookup: the entity\'s network id'),
        (0x129C748, 'cmp eax, 0x7fff', None, 'no network id: creditor 0'),
        (0x129C76D, 'call rbx', None, 'the peer that owns that network id'),
    ],
}

# Members SpawnProjectile copies whose later readers were reviewed: none reads them through a spawned projectile's
# stored type. {offset: (label, unit or None, meaning and evidence)}. Every other member stays equal to the base row.
COPIED = {
    0x18: ('diameter', 'millimeters', 'projectile diameter: copied into the slot ballistics record (0x13AA055) and, '
        'x 0.0005 as the radius in metres, squared x pi/2 x 1.2 x the drag coefficient, the drag constant '
        '(0x13AA095..0x13AA0D5)'),
    0x20: ('speed', 'meters_per_second', 'launch speed (projectile.velocity): read at spawn (0x13A9C95) into the slot '
        'ballistics record (0x13AA0C3); the other readers are configured-type ones (component lookups, statistics)'),
    0x24: ('mass', 'grams', 'mass (projectile.mass): x 0.001 into the slot ballistics record (0x13AA066)'),
    0x28: ('drag', 'factor', 'drag coefficient (projectile.drag): multiplied into the drag constant (0x13AA0B6)'),
    0x2C: ('gravity', 'factor', 'gravity multiplier (projectile.gravity): copied into the slot ballistics record '
        '(0x13AA046)'),
    0x38: ('lifetime_variance', 'fraction', 'random lifetime variance: the lifetime (+0x34) varies by a random '
        '+-(this x lifetime) at spawn (0x13AA110)'),
    0x3C: ('direct_damage', None, 'DamageInfoType of the direct hit: stored in the record +0x0C with its armour '
        'penetration (0x13AA62F..0x13AA6D2); the fire path (0x67FCD1) and weapon statistics queries read it through the '
        "weapon's configured type only"),
    0x40: ('penetration_slowdown', 'factor', 'penetration slowdown (projectile.penetration_slowdown): copied into the '
        'hit record +0x20 (0x13AA676)'),
    0x48: ('spawn_effect', None, 'particle effect resource created with the spawn pose through engine world API +0x280, '
        'handle kept in the slot effect record; its "start" / "end" variables are set to the slot position '
        '(0x13AAB9F..0x13AACB3). No member is a colour or tint: colour is baked into the effect asset'),
    0x50: ('spawn_effect_alternate', None, 'particle effect used instead of +0x48 when the extra parameters ask for it '
        '(0x13AAB92); Runtime passes none'),
    0x58: ('spawn_effect_parameter', None, 'f32 stored beside the spawn effect handle (0x13AABF1)'),
    0x60: ('spawn_effect_secondary', None, 'second particle effect resource created with the spawn pose through API '
        '+0x280 (0x13AACC6)'),
    0x68: ('spawn_effect_record', None, 'u64 stored in the slot effect record (0x13AABCA)'),
    0x70: ('record_resource_70', None, 'u64 stored in the projectile record +0x68 (0x13AA876)'),
    0x78: ('record_resource_78', None, 'u64 stored in the projectile record +0x60 (0x13AA86A)'),
    0x90: ('impact_explosion', None, 'ExplosionType released on impact (projectile.impact_explosion): copied into the '
        'hit record +0x7C (0x13AA646) and read from that copy by hit processing (0x13AD7FD); the other readers take a '
        "stratagem's or weapon's configured type"),
}
# Late lookups through the stored type (offset, width, mask or None, label, reason); mask is over the member. These are
# the only row members reread through a spawned projectile's stored vanilla type.
LATE = [
    (0x80, 8, None, 'unit', 'unit resource: read again through the stored type by the unit hand-off (0x13A8BE4)'),
    (0xF0, 2, 0x1000, 'impact_effect_bit12', 'flags +0xF0 bit 12: read through the stored type on impact (0x13B322F)'),
    (0xF4, 4, None, 'collision_filter', 'RaycastTemplate: read through the stored type every frame (0x13ABDAD)'),
    (0xF8, 4, None, 'overlap_filter', 'overlap filter: read through the stored type in an out-of-line block of the '
        'per-frame update (0x13AC0D8)'),
    (0xFC, 1, 0x01, 'damage_hit_flag', 'flags +0xFC bit 0: read through the stored type on a damage hit (0x13AD858, '
        '0x13AD90A)'),
    (0xFC, 1, 0x02, 'unit_handoff_flag', 'flags +0xFC bit 1: read through the stored type by the unit hand-off '
        '(0x13A8B41)'),
    (0x100, 12, None, 'unit_offset', 'CApiVector3: read through the stored type by the unit hand-off (0x13A8BC4, '
        '0x13A8BD2)'),
]
FIRE_PATH = [
    (0x1C, 4, None, 'pellet_count', "pellet count: the weapon firing path reads it through the weapon's configured "
        'type (0x75B95F); SpawnProjectile never reads it'),
    (0x0C, 4, None, 'mode_label', "weapon-function mode label: read through the weapon's configured projectile type "
        'when the mode menu is built; SpawnProjectile never reads it'),
    (0x10, 8, None, 'mode_icon', "weapon-function mode icon: read through the weapon's configured projectile type; "
        'SpawnProjectile never reads it'),
]
GATES = {0x94: 'non-zero enables the overlap query whose filter (+0xF8) is a late lookup'}
# Members read at spawn whose promotion this research does not (yet) justify, with the reason kept in the policy.
NOT_PROMOTED = {
    0x30: 'u32 copied into the slot ballistics record +0x3088 (0x13AA07F); meaning not established',
    0x34: 'lifetime, read at spawn beside the variance (0x13AA103); not promoted in this pass',
    0x9C: 'expiry explosion, copied into the hit record +0x80 (0x13AA653); not promoted in this pass',
}
# Functions whose by-type reads were reviewed: each takes its type from a weapon, stratagem or entity's configured
# data, never from a pool slot's stored type, so the members they read are no evidence against COPIED_AT_SPAWN.
# Keyed by function start.
REVIEWED_FUNCTIONS = {
    0x1762D30: 'weapon statistics query: the type is a weapon component value (0x514C10 / 0x4FD8E0 lookups)',
    0x1766B10: 'weapon statistics query: the type is a weapon component value (0x514C10 / 0x4FD8E0 lookups)',
    0x176F830: 'weapon statistics query: the type is a weapon component value (0x514C10 / 0x4FD8E0 lookups)',
    0x1777860: 'weapon statistics query: the type is in a copied component record (calls 0x1766920 like the others)',
    0x67F3D0: "weapon-side firing function: the type is the weapon's configured projectile type ([r14 + 0x80]), not "
        "a pool slot's stored type",
    0x6BBDC0: 'configured type: ProjectileWeapon component +0 found through 0x515100',
    0x8A37D0: 'configured type: a component value (+0x18) found through 0x514B40',
    0x7B8390: 'configured type: a StratagemSettings (game+0x37CB600) weapon list, resolved through 0x503DC0',
    0xA16790: 'configured type: a StratagemSettings weapon list, resolved through 0x503DC0',
    0xA16A70: 'configured type: a StratagemSettings weapon list',
    0xB55650: 'configured type: a StratagemSettings (game+0x37CB600) weapon list, resolved through 0x503DC0',
    0xB5D700: 'configured type: a StratagemSettings weapon list, resolved through 0x503DC0',
}
SPAWN_RANGE = (0x13A9830, 0x13AAD40)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def full_register(md, reg):
    """The 64-bit register a register operand belongs to (eax -> rax, r8d -> r8)."""
    name = md.reg_name(reg)
    legacy = {'eax': 'rax', 'ebx': 'rbx', 'ecx': 'rcx', 'edx': 'rdx', 'esi': 'rsi', 'edi': 'rdi', 'ebp': 'rbp',
        'esp': 'rsp', 'ax': 'rax', 'bx': 'rbx', 'cx': 'rcx', 'dx': 'rdx', 'al': 'rax', 'bl': 'rbx', 'cl': 'rcx',
        'dl': 'rdx', 'si': 'rsi', 'di': 'rdi', 'sil': 'rsi', 'dil': 'rdi'}
    if name in legacy:
        return legacy[name]
    match = re.match(r'(r\d+)[dwb]?$', name)
    return match.group(1) if match else name


def function_start(data: bytes, rva: int) -> int:
    """The start of the function containing rva: the first byte after the nearest int3 padding before it."""
    at = rva
    while at > rva - 0x8000 and not (data[at - 1] == 0xCC and data[at - 2] == 0xCC and data[at] != 0xCC):
        at -= 1
    return at


def table_loads(data: bytes) -> list[int]:
    """Every instruction in code that loads a row pointer from the settings table: `mov r, [b + i*8 + table]`
    (image-base relative) and `lea r, [rip + table]` followed by `mov r2, [r + i*8]`."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    low, high = base.TEXT
    code = data[low:high]
    loads = set()
    needle = struct.pack('<I', TABLE)
    at = code.find(needle)
    while at != -1:
        # opcode + modrm + sib precede the displacement; a REX prefix (0x40..0x4F) before them belongs to the same
        # instruction and must be decoded with it (without it, `mov r15, [...]` reads as `mov edi, [...]`).
        backs = (4, 3) if 0x40 <= code[at - 4] <= 0x4F else (3,)
        for back in backs:
            start = low + at - back
            insn = next(md.disasm(data[start:start + 16], start), None)
            if insn and insn.address + insn.size == low + at + 4 and insn.mnemonic == 'mov' and any(
                    op.type == X86_OP_MEM and op.mem.disp == TABLE and op.mem.scale == 8 for op in insn.operands):
                loads.add(insn.address)
                break
        at = code.find(needle, at + 1)
    for at in range(0, len(code) - 4):
        disp = struct.unpack_from('<i', code, at)[0]
        if low + at + 4 + disp != TABLE:
            continue
        for back in range(3, 4):
            start = low + at - back
            insn = next(md.disasm(data[start:start + 7], start), None)
            if not (insn and insn.mnemonic == 'lea' and insn.address + insn.size == low + at + 4):
                continue
            table_reg = full_register(md, insn.operands[0].reg)
            for follow in md.disasm(data[insn.address + insn.size:insn.address + insn.size + 64], insn.address
                    + insn.size):
                ops = follow.operands
                if follow.mnemonic == 'mov' and len(ops) == 2 and ops[1].type == X86_OP_MEM and ops[1].mem.base \
                        and full_register(md, ops[1].mem.base) == table_reg and ops[1].mem.scale == 8:
                    loads.add(follow.address)
                    break
                if ops and ops[0].type == X86_OP_REG and full_register(md, ops[0].reg) == table_reg:
                    break
    return sorted(loads)


def member_reads(data: bytes, load: int, window: int = 300) -> tuple[dict, list]:
    """Straight-line member reads of the row a load produced, and calls that receive it (best effort)."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    rows, offsets, calls = set(), {}, []
    for insn in md.disasm(data[load:load + window * 8], load):
        window -= 1
        if window < 0 or insn.mnemonic in ('ret', 'int3'):
            break
        ops = insn.operands
        written = full_register(md, ops[0].reg) if ops and ops[0].type == X86_OP_REG and insn.mnemonic not in (
            'cmp', 'test', 'push') else None
        if insn.address == load:
            rows.add(written)
            continue
        for op in ops:
            if op.type == X86_OP_MEM and op.mem.base and not op.mem.index and full_register(md, op.mem.base) in rows:
                offsets.setdefault(op.mem.disp, []).append(insn.address)
        if insn.mnemonic == 'call':
            passed = [r for r in ('rcx', 'rdx', 'r8', 'r9') if r in rows]
            if passed:
                calls.append({'rva': insn.address, 'target': insn.op_str, 'rowArguments': passed})
            rows -= {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}
            continue
        if written:
            source = full_register(md, ops[1].reg) if len(ops) == 2 and ops[1].type == X86_OP_REG else None
            if insn.mnemonic == 'mov' and source in rows:
                rows.add(written)
            else:
                rows.discard(written)
    return {k: sorted(set(v)) for k, v in sorted(offsets.items())}, calls


def context(data: bytes, rva: int) -> str | None:
    return REVIEWED_FUNCTIONS.get(function_start(data, rva))


def row_members(native) -> list[dict]:
    desc = native.typelib_module.layout(native.typelib, 'ProjectileInfo', structured=True)
    if desc['size64'] != ROW_SIZE:
        raise ValueError('ProjectileInfo is no longer %d bytes' % ROW_SIZE)
    members = []
    for member in desc['members']:
        length = int(re.search(r'inferred_length=(\d+)', member['name']).group(1))
        entry = {'offset': member['offset64'], 'width': member['size64'], 'storage': member['storage'],
            'nameLength': length}
        type_name = native.names.get(member['type_hash']) if member.get('type_hash') else None
        if type_name:
            entry['type'] = type_name
        if member['atom'] == 'BITFIELD':
            entry['bit'], entry['bits'] = member['array_or_bits'] >> 8, member['array_or_bits'] & 0xFF
        members.append(entry)
    return members


def policy(members: list[dict], spawn_reads: set[int], readers: list[dict]) -> list[dict]:
    """One entry per member (bitfield bits separately) and per padding range: class, label, reason."""
    outside = {}
    for reader in readers:
        if reader['context'] is None:
            for offset in reader['reads']:
                outside.setdefault(int(offset), []).append(reader['load'])
    late = {(o, m): (w, label, reason) for o, w, m, label, reason in LATE}
    fire = {o: (w, label, reason) for o, w, m, label, reason in FIRE_PATH}
    entries, covered = [], set()
    for member in members:
        offset, width = member['offset'], member['width']
        covered.update(range(offset, offset + width))
        entry = {'offset': offset, 'width': width, 'storage': member['storage'], 'nameLength': member['nameLength']}
        if 'type' in member:
            entry['type'] = member['type']
        if 'bit' in member:
            entry['mask'] = ((1 << member['bits']) - 1) << member['bit']
        mask = entry.get('mask')
        read_at_spawn = any(o in spawn_reads for o in range(offset, offset + width))
        others = sorted({rva for o in range(offset, offset + width) for rva in outside.get(o, [])})
        if offset == 0:
            entry.update({'class': 'BASE_TYPE', 'label': 'projectile_type', 'reason': 'the vanilla ProjectileType: '
                'SpawnProjectile stores it in the slot type array and every late lookup indexes the vanilla table '
                'with it (a type 0 row reads the default row)'})
        elif (offset, mask) in late:
            _, label, reason = late[(offset, mask)]
            entry.update({'class': 'LATE_LOOKUP', 'label': label, 'reason': reason})
        elif offset in fire and mask is None:
            _, label, reason = fire[offset]
            entry.update({'class': 'FIRE_PATH_LOOKUP', 'label': label, 'reason': reason})
        elif offset in COPIED and mask is None:
            if not read_at_spawn:
                raise ValueError('+0x%X is not read by SpawnProjectile' % offset)
            if others:
                raise ValueError('+0x%X has unreviewed by-type readers %s' % (offset, [hex(r) for r in others]))
            label, unit, reason = COPIED[offset]
            entry.update({'class': 'COPIED_AT_SPAWN', 'label': label, 'reason': reason})
            if unit:
                entry['unit'] = unit
        else:
            notes = []
            notes.append('read by SpawnProjectile' if read_at_spawn else 'not read by SpawnProjectile')
            if others:
                notes.append('also read through a table lookup at ' + ', '.join('0x%X' % r for r in others[:6])
                    + (' and %d more' % (len(others) - 6) if len(others) > 6 else '') + ' (not reviewed)')
            if offset in GATES:
                notes.append(GATES[offset])
            if offset in NOT_PROMOTED and mask is None:
                notes.append(NOT_PROMOTED[offset])
            entry.update({'class': 'UNKNOWN', 'label': None, 'reason': '; '.join(notes)})
        entries.append(entry)
    for offset in range(ROW_SIZE):
        if offset not in covered:
            if entries and entries[-1].get('padding') and entries[-1]['offset'] + entries[-1]['width'] == offset:
                entries[-1]['width'] += 1
            else:
                entries.append({'offset': offset, 'width': 1, 'storage': 'PADDING', 'padding': True,
                    'class': 'UNKNOWN', 'label': None, 'reason': 'padding (no type-library member)'})
    # Bits of a bitfield word that no member names stay unknown.
    words = {}
    for entry in entries:
        if 'mask' in entry:
            words.setdefault((entry['offset'], entry['width']), 0)
            words[(entry['offset'], entry['width'])] |= entry['mask']
    for (offset, width), used in sorted(words.items()):
        rest = ((1 << (8 * width)) - 1) & ~used
        if rest:
            entries.append({'offset': offset, 'width': width, 'storage': 'BITS', 'mask': rest, 'class': 'UNKNOWN',
                'label': None, 'reason': 'bits no type-library member names'})
    for entry in entries:
        if entry.get('mask') is not None and entry['class'] == 'COPIED_AT_SPAWN':
            raise ValueError('a bitfield bit cannot be copied independently of its word')
    return sorted(entries, key=lambda e: (e['offset'], e.get('mask') or 0))


def live_rows(name: str, types: list[int]) -> dict:
    mem = base.Mem(name)
    out = {}
    system = mem.ptr(mem.game + SYSTEM_GLOBAL)
    out['projectileSystemActive'] = bool(system and mem.read(system + 0x28, 1)[0])
    out['defaultRowType'] = mem.u32(mem.game + DEFAULT_ROW)
    out['rows'] = {}
    for kind in types:
        record = mem.ptr(mem.game + TABLE + 8 * kind)
        raw = record and mem.read(record, ROW_SIZE)
        out['rows'][str(kind)] = {'type': raw and struct.unpack_from('<I', raw, 0)[0], 'sha256': raw and sha(raw),
            'bytes': raw.hex() if raw else None}
    mem.close()
    return out


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in GAME_PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    prologue = data[SPAWN:SPAWN_PROLOGUE_END].hex()

    # By-type readers of the settings table.
    readers = []
    for load in table_loads(data):
        reads, calls = member_reads(data, load)
        readers.append({'load': load, 'function': function_start(data, load), 'context': context(data, load),
            'reads': {str(k): v for k, v in reads.items()}, 'rowCalls': calls})
    # Members SpawnProjectile reads through the descriptor's row pointer.
    spawn_offsets = set()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    lines = list(md.disasm_lite(data[SPAWN_RANGE[0]:SPAWN_RANGE[1]], SPAWN_RANGE[0]))
    for index, (rva, size, mnemonic, operands) in enumerate(lines):
        if operands.endswith('qword ptr [r14 + 0x10]') and mnemonic == 'mov':
            row_reg = operands.split(',')[0]
            for follow in lines[index + 1:index + 40]:
                found = re.search(r'\[%s(?: \+ (0x[0-9a-f]+))?\]' % row_reg, follow[3])
                if found:
                    spawn_offsets.add(int(found.group(1) or '0', 16))
                if follow[3].startswith(row_reg + ',') or follow[2] == 'call':
                    break

    native = entity_research.Native()
    members = row_members(native)
    entries = policy(members, spawn_offsets, readers)

    # Vanilla rows (datalibrary) and the live rows of every mission snapshot.
    vanilla = builder.settings_rows('generated_projectile_settings.dl_bin', 'ProjectileSettings', ROW_SIZE)
    observations = [dict(live_rows(name, sorted(PROOF_ROWS.values())), snapshot=name) for name in SNAPSHOTS]
    for observation in observations:
        for kind, row in observation['rows'].items():
            row['matchesDatalibrary'] = row['bytes'] == vanilla[int(kind)]['bytes'].hex()
            if row['type'] != int(kind) or not row['matchesDatalibrary']:
                raise ValueError('live row %s differs from the datalibrary in %s' % (kind, observation['snapshot']))
            del row['bytes']
    active = [o['projectileSystemActive'] for o in observations]
    if active != [True, True, True, False]:
        raise ValueError('projectile system activity does not follow the mission: %r' % active)
    rows = {role: vanilla[kind]['bytes'] for role, kind in PROOF_ROWS.items()}
    proof_changes = {}
    for offset, width, source in ((0x3C, 4, 'damage'), (0x48, 8, 'effect'), (0x50, 8, 'effect'), (0x58, 4, 'effect'),
            (0x60, 8, 'effect'), (0x68, 8, 'effect')):
        before, after = rows['base'][offset:offset + width], rows[source][offset:offset + width]
        if before != after:
            proof_changes['0x%X' % offset] = {'base': before.hex(), 'value': after.hex(), 'from': PROOF_ROWS[source]}
    classes = {e['offset']: e['class'] for e in entries if 'mask' not in e and not e.get('padding')}
    if any(classes.get(int(k, 16)) != 'COPIED_AT_SPAWN' for k in proof_changes):
        raise ValueError('the proof changes a member that is not COPIED_AT_SPAWN')
    unit = rows['base'][0x80:0x88]
    if unit != bytes(8) or rows['effect'][0x80:0x88] != bytes(8):
        raise ValueError('the proof base or effect donor has a unit')

    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'spawn': {'rva': SPAWN, 'prologue': prologue,
            'signature': 'SpawnProjectile(ProjectileSystem *system, const SpawnDescriptor *descriptor, '
                'const SpawnExtra *extra /* may be null */) -> u32 pool slot',
            'descriptor': {'size': 0x30, 'position': 0x00, 'direction': 0x08, 'row': 0x10, 'source': 0x18,
                'owner': 0x1C, 'creditor': 0x20, 'kind': 0x28},
            'template': {'kind': 2, 'extra': None},
            'returns': 'the pool slot it wrote; 0 also when the system is inactive',
            'rowRetained': False},
        'system': {'global': SYSTEM_GLOBAL, 'active': 0x28, 'typeArray': TYPE_ARRAY},
        'table': {'rva': TABLE, 'defaultRow': DEFAULT_ROW, 'typeCount': TYPE_COUNT},
        'row': {'size': ROW_SIZE, 'align': 8,
            'sizeEvidence': ['type library ProjectileInfo size 272', 'ProjectileSettings stride 272 (datalibrary)',
                'FireProjectile type 0 row game+0x37C7560 = table - 0x110']},
        'members': members, 'policy': entries,
        'spawnReads': sorted(spawn_offsets),
        'readers': readers,
        'proofs': proofs, 'pinnedBytesMismatchPerSnapshot': relocation,
        'observations': observations,
        'proof': {'rows': PROOF_ROWS, 'changes': proof_changes},
        'unproven': ['The census follows a lea-loaded table register for 64 bytes only; loads further away (for '
            'example the configured-type +0xF0 reads at 0x851B85) are covered by the stored-type closure (every read of '
            'the slot type array is pinned) rather than by the census.',
            'What each particle effect looks like in game: colour is baked into the effect asset (the Scorcher donor '
            'was observed live).',
            'The meaning of copied members without a label (+0x30, +0x70, +0x78, +0x88, +0x98 ..): they stay UNKNOWN '
            'or unlabelled.',
            'Whether other machines see a projectile spawned from a Runtime-owned row: SpawnProjectile sends no '
            'network message that was found; peers would know only the vanilla base type.'],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    counts = {}
    for entry in entries:
        counts[entry['class']] = counts.get(entry['class'], 0) + 1
    print(json.dumps({'readers': len(readers), 'classes': counts, 'proofChanges': proof_changes,
        'spawnReads': ['0x%X' % o for o in sorted(spawn_offsets)]}, indent=1))


if __name__ == '__main__':
    main()
