"""RS-422 Railgun charge and overcharge: the whole WeaponChargeComponent family tied to native code (research only).

Read-only. Nothing here writes game memory, runs in game, or edits the public API. Inputs: the pinned datalibrary
(scan.tables), the game.dll image from a retained snapshot (scan.xref), the retained snapshots (loaded-table and
manager checks), the entity-delta table, the settings tables (scan.settings) and the wiki import
(../HD2WikiImporter/output, independent published values).

Proven on build F5FEE03DCFDB (details, pins and per-member evidence in the JSON):

1. Owner and lifecycle. WeaponChargeComponentData (record type WeaponChargeComponent, 216 bytes, 11 records, 20 index
   rows) is managed by the weapon_charge component manager (game+0x3326C20). Its record resolver (0x5052C0) returns a
   per-instance resolved copy (manager +0x90, 0xD8 stride) only when the entity has one, else the loaded entity-file
   table block at [entity manager +0xF12AD8] (index rows then records at +0x140). That block is byte-identical to the
   pinned entity file in the retained snapshots, and no entity delta (customization) targets this component, so every
   charge rule below reads the shared type record live, every frame and every shot.
2. The charge update (0x73C8F0, called by the world update with dt). Per instance the manager keeps a 40-byte state
   (+0x40): +0x00 display value, +0x04 charge accumulator (seconds), +0x08 charge at release, +0x0C trigger held,
   +0x10 sound, +0x14 burst counter, +0x18 burst timer, +0x1C loop effect, +0x20 pending, +0x24 perspective.
   While the trigger is held the accumulator grows by dt. Unless the weapon's current fire mode is 6 (the Railgun's
   Unsafe slot), it is clamped at charge_time[1] (full charge); with +184 set the weapon fires automatically when it
   first reaches full charge. In fire mode 6 the accumulator is unbounded; with +185 set, crossing charge_time[2]
   fires the shot and then runs the overcharge failure (0x73DC60). Independently, +204 {state, seconds} is a hard
   limit: when the current charge state equals +204 and the accumulator exceeds +208 seconds, the failure runs
   without a shot (PLAS-45 Epoch: state 2, 3.25 s). Releasing at or above charge_time[0] fires; releasing below it
   cancels (accumulator reset, no shot).
3. The failure (0x73DC60, authority only) removes the weapon entity (0xFDC310) and spawns ExplosionType +200 at the
   weapon position + 0.1 m per axis (0x13C0A80), replicated through 0xBE1340. The Railgun's 326 and the Epoch's 321
   rows equal the wiki's "RS-422 RAILGUN Overcharge E" and "PLAS-45 EPOCH Overcharge E" branches exactly.
4. Charge scaling (0x73E280): with c the released charge, below charge_time[1] the multiplier is lerp(min, 1.0) over
   [charge_time[0], charge_time[1]]; above it lerp(1.0, overcharge) over [charge_time[1], charge_time[2]], clamped.
   Getters read the ProjectileMultipliers pairs: speed (+72/+76), damage (+80/+84), penetration (+88/+92), arc
   distance (+96/+100), extra arc splits/chains (+104/+108, +112/+116; rounded to int).
5. Consumers. Projectile weapons (0x741A00, charge capability bit 0x4000) pass speed, damage and penetration through
   0x6128B0 and 0x615940 into SpawnProjectile's extra block (+0x2C, +0x30, +0x34): launch speed is multiplied by +0x2C
   (0x13A9DB2); +0x30/+0x34 are stored in the hit record (+0x34/+0x38) and, on impact, multiply the hit's damage
   scalar and each of the four armor-penetration lanes (rounded) (0x13AD524..0x13AD55A). Arc weapons (0x13B3910)
   store distance, damage, penetration, splits and chains in the arc. No code reads the distance getter for a
   projectile weapon: the Railgun's published 0.7/1.4 "distance multiplier" has no consumer.
6. The fire helper (0x73D8C0) also proves +188 (shots per charge: a burst counter compared with it, >1 enables)
   and +192 (the burst re-fire delay, seconds), and selects the per-state projectile type/particle/u32 by the released
   charge (state 0 if t0 <= c < t1, state 2 if c >= t2, else state 1).
7. Presentation only: sounds +120/+124/+128/+132/+196, material +136/+140/+144 (display value 0.7*min(c/t1,1) +
   0.3*clamp((c-t1)/(t2-t1),0,1), RTPC "weapon_overcharging"), muzzle effects +152/+160, animation +168..+180, HUD
   reticle shake (0x17B71F0).
8. Existing public ids: charge.level_1/2/3 (+0/+24/+48) are the three charge_time thresholds in SECONDS, not
   multipliers; charge.minimum_seconds (+72) and charge.maximum_seconds (+76) are the projectile SPEED multipliers at
   minimum charge and full overcharge, not times (and no arc consumer reads them).

  py scripts/research_railgun_charge.py          # write research/railgun-charge-F5FEE03DCFDB.json + docs/research md
  py scripts/research_railgun_charge.py --check  # fail if the committed outputs are stale

Requires capstone and numpy, the pinned datalibrary and the retained snapshots.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from scan import compare, golib, report, tables  # noqa: E402
from scan.tables import decode, hexid  # noqa: E402

OUTPUT = ROOT / 'research/railgun-charge-F5FEE03DCFDB.json'
MARKDOWN = ROOT / 'docs/research/railgun-charge-F5FEE03DCFDB.md'
WIKI = ROOT.parent / 'HD2WikiImporter/output'
COMPONENT = 'WeaponChargeComponentData'
RECORD_TYPE = 'WeaponChargeComponent'
RECORD_SIZE = 216
SNAPSHOTS = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260926T222226Z.hd2snap']
G_ENTITY_MANAGER = 0x346BF98
LOADED_TABLE_OFFSET = 0xF12AD8          # [entity manager + 0xF12AD8] = the loaded WeaponChargeComponentData block
MANAGERS = {'weapon_charge': 0x3326C20, 'weapon': 0x3326660, 'weapon_data': 0x3326CE0,
    'projectile_weapon': 0x33266D8}
STATE_NAMES = {0: 'min_to_full (t0 < c <= t1)', 1: 'full_to_over (t1 < c <= t2)', 2: 'overcharged (c > t2)',
    3: 'below_min (c <= t0)'}
FIRE_MODE_UNSAFE = 6
CORRECTED = {'charge.level_1', 'charge.level_2', 'charge.level_3'}   # unit/display corrected in 0.30.0-dev

# ---------------------------------------------------------------------------------------------------------------
# Native code pins: (rva, text the decoded instruction must contain, role, group). A changed game.dll fails loudly.
# ---------------------------------------------------------------------------------------------------------------
PINS = [
    # manager, resolver, lifecycle
    (0x73F1DA, 'lea rdx, [rip', 'the manager names itself WeaponChargeComponent (capacity growth)', 'manager'),
    (0x73F28E, 'imul rdx, rax, 0xd8', 'per-instance resolved-copy array: 0xD8 = the 216-byte record', 'manager'),
    (0x73F2A8, 'mov qword ptr [r14 + 0x90], rax', '... stored at manager +0x90', 'manager'),
    (0x5052E2, 'mov r11, qword ptr [rip', 'record resolver: the weapon_charge manager', 'resolver'),
    (0x505362, 'imul rax, rax, 0xd8', 'resolver: a resolved per-instance copy when the entity has one ...', 'resolver'),
    (0x505369, 'add rax, qword ptr [r11 + 0x90]', '... from manager +0x90', 'resolver'),
    (0x50537C, 'jmp 0x504d80', '... else the type record', 'resolver'),
    (0x504D8F, 'mov r10, qword ptr [rax + 0xf12ad8]', 'type record: the loaded entity-table block', 'resolver'),
    (0x504DFC, 'imul rax, rcx, 0xd8', 'record index x 216 ...', 'resolver'),
    (0x504E03, 'add rax, 0x140', '... after the 20 index rows (0x140 bytes)', 'resolver'),
    # weapon update: trigger, dry fire
    (0x740A09, 'call 0x744ad0', 'weapon update: can the weapon fire (ammunition)?', 'trigger'),
    (0x740A88, 'mov byte ptr [rax + rdx*8 + 0xc], 1', 'trigger down and able to fire: charge state +0x0C = 1', 'trigger'),
    (0x740AB9, 'cmp dword ptr [rax + 0xc4], 0', 'trigger down, cannot fire: +196 dry-fire sound (once)', 'trigger'),
    (0x740BB0, 'mov byte ptr [rax + rdx*8 + 0xc], 0', 'trigger up: charge state +0x0C = 0', 'trigger'),
    # charge update
    (0x572EF2, 'call 0x73c8f0', 'the world update calls the charge update with dt', 'update'),
    (0x73C92B, 'movaps xmm14, xmm1', 'charge update: dt', 'update'),
    (0x73CA7C, 'movss xmm9, dword ptr [r15 + r14*8 + 4]', 'state +0x04: the charge accumulator (seconds)', 'update'),
    (0x73CB17, 'subss xmm0, xmm14', 'burst timer (state +0x18) counts down by dt ...', 'update'),
    (0x73CB35, 'call 0x73d8c0', '... and fires the next burst shot when it expires', 'update'),
    (0x73CAFE, 'movss xmm12, dword ptr [r13]', 'charge_time[0] (+0): minimum charge', 'update'),
    (0x73CB04, 'movss xmm10, dword ptr [r13 + 0x18]', 'charge_time[1] (+24): full charge', 'update'),
    (0x73CB0A, 'movss xmm11, dword ptr [r13 + 0x30]', 'charge_time[2] (+48): overcharge', 'update'),
    (0x73CB76, 'cmp byte ptr [r15 + r14*8 + 0xc], 0', 'trigger held?', 'update'),
    (0x73CC0C, 'call 0x756730', 'the weapon\'s current fire mode (weapon_data +0x60) ...', 'update'),
    (0x73CC11, 'cmp eax, 6', '... mode 6 (the Railgun\'s Unsafe slot) disables the full-charge clamp', 'update'),
    (0x73CBEC, 'addss xmm0, xmm14', 'safe: accumulator + dt ...', 'update'),
    (0x73CBF1, 'minss xmm0, xmm10', '... clamped at charge_time[1]', 'update'),
    (0x73CC1E, 'addss xmm0, xmm14', 'unsafe (mode 6): accumulator + dt, unbounded', 'update'),
    (0x73CC42, 'cmp byte ptr [r13 + 0xb8], 0', '+184: fire automatically when the charge first reaches full (safe)', 'update'),
    (0x73CC62, 'call 0x73d8c0', '... auto-fire shot', 'update'),
    (0x73CD73, 'cmp byte ptr [r13 + 0xb9], 0', '+185: in mode 6, crossing charge_time[2] ...', 'update'),
    (0x73CD8E, 'comiss xmm0, xmm11', '... (accumulator reaches charge_time[2]) ...', 'update'),
    (0x73CDB2, 'call 0x73d8c0', '... fires the shot ...', 'update'),
    (0x73CDBA, 'call 0x73dc60', '... then runs the overcharge failure', 'update'),
    (0x73CC74, 'movss xmm0, dword ptr [r13 + 0xd0]', '+208: limit seconds (0 disables) ...', 'update'),
    (0x73CCB3, 'cmp eax, dword ptr [r13 + 0xcc]', '... when the current charge state equals +204 ...', 'update'),
    (0x73CCC4, 'call 0x73dc60', '... and the accumulator exceeds +208: the failure, without a shot', 'update'),
    (0x73CDCF, 'comiss xmm9, xmm12', 'released: fire only at or above charge_time[0] ...', 'update'),
    (0x73CE7E, 'call 0x73d8c0', '... the release shot', 'update'),
    (0x73CE85, 'mov dword ptr [r15 + r14*8 + 4], eax', 'accumulator reset (shot or cancel)', 'update'),
    # presentation in the update
    (0x73D2EB, 'mov ecx, dword ptr [r13 + 0x78]', '+120: sound when the charge starts', 'presentation'),
    (0x73D38A, 'mov ecx, dword ptr [r13 + 0x7c]', '+124: sound when the charge stops', 'presentation'),
    (0x73D42C, 'mov ecx, dword ptr [r13 + 0x80]', '+128: sound when the charge crosses charge_time[0]', 'presentation'),
    (0x73D441, 'mov ecx, dword ptr [r13 + 0x84]', '+132: sound when the charge crosses charge_time[1]', 'presentation'),
    (0x73D4A9, 'mulss xmm2, dword ptr [rip', 'display value: 0.7 x min(c / t1, 1) ...', 'presentation'),
    (0x73D4DC, 'mulss xmm3, dword ptr [rip', '... + 0.3 x clamp((c - t1) / (t2 - t1), 0, 1)', 'presentation'),
    (0x73D515, 'lea r8, [rip', 'RTPC "weapon_overcharging" = accumulator > t1', 'presentation'),
    (0x73D53F, 'mov edx, dword ptr [r13 + 0x88]', '+136: charge mesh', 'presentation'),
    (0x73D5A0, 'mov edx, dword ptr [r13 + 0x8c]', '+140: charge material', 'presentation'),
    (0x73D5DA, 'mov edx, dword ptr [r13 + 0x90]', '+144: material variable = display value', 'presentation'),
    (0x73D0C9, 'cmp qword ptr [r13 + 0x98], 0', '+152: muzzle effect while charging', 'presentation'),
    (0x73CEB2, 'cmp qword ptr [r13 + 0xa0], 0', '+160: looping muzzle effect after full charge', 'presentation'),
    (0x73D339, 'cmp dword ptr [r13 + 0xa8], 0', '+168: animation event at charge start', 'presentation'),
    (0x73D3B5, 'cmp dword ptr [r13 + 0xac], 0', '+172: animation event at charge end', 'presentation'),
    (0x73D791, 'cmp dword ptr [r13 + 0xb0], ebx', '+176: animation variable = accumulator', 'presentation'),
    (0x73D7B8, 'cmp dword ptr [r13 + 0xb4], 0', '+180: animation variable = accumulator', 'presentation'),
    (0x73E088, 'cmp dword ptr [rax + 0xc4], 0', '+196: dry-fire sound', 'presentation'),
    (0x17B83A1, 'movss xmm3, dword ptr [rax + 0x18]', 'HUD reticle: charge_time[1] ...', 'presentation'),
    (0x17B83A6, 'movss xmm4, dword ptr [rax + 0x30]', '... and charge_time[2] drive the overcharge shake', 'presentation'),
    # fire helper
    (0x73D96F, 'test byte ptr [r13 + 0x14], 1', 'fire helper: authority only', 'fire'),
    (0x73D985, 'mov ecx, dword ptr [rax + 0xbc]', '+188: shots per charge (burst when > 1) ...', 'fire'),
    (0x73D999, 'mov ecx, dword ptr [rdi + 0xc0]', '... +192: delay before the next burst shot ...', 'fire'),
    (0x73D99F, 'mov dword ptr [r14 + rbp*8 + 0x18], ecx', '... into the burst timer (state +0x18)', 'fire'),
    (0x73DB30, 'mov r8d, dword ptr [rdi + 0x1c]', 'state 1 projectile type (default) ...', 'fire'),
    (0x73DB34, 'mov r9, qword ptr [rdi + 0x20]', '... with its particle ...', 'fire'),
    (0x73DB38, 'mov eax, dword ptr [rdi + 0x28]', '... and its u32 ...', 'fire'),
    (0x73DB4E, 'mov r8d, dword ptr [rdi + 4]', '... state 0 when t0 <= c < t1 ...', 'fire'),
    (0x73DB52, 'mov r9, qword ptr [rdi + 8]', '... (particle) ...', 'fire'),
    (0x73DB56, 'mov eax, dword ptr [rdi + 0x10]', '... (u32) ...', 'fire'),
    (0x73DB71, 'mov r8d, dword ptr [rdi + 0x34]', '... state 2 when c >= t2 ...', 'fire'),
    (0x73DB75, 'mov r9, qword ptr [rdi + 0x38]', '... (particle) ...', 'fire'),
    (0x73DB79, 'mov eax, dword ptr [rdi + 0x40]', '... (u32)', 'fire'),
    (0x73DB84, 'call 0x741a00', 'the shot with that projectile type and the charge multipliers', 'fire'),
    # interpolation and getters
    (0x73E316, 'movss xmm1, dword ptr [rax + 0x18]', 'scaling: charge_time[1] ...', 'scaling'),
    (0x73E31B, 'movss xmm3, dword ptr [rax]', '... charge_time[0] ...', 'scaling'),
    (0x73E31F, 'movss xmm2, dword ptr [rax + 0x30]', '... charge_time[2] ...', 'scaling'),
    (0x73E32D, 'movss xmm0, dword ptr [rax + rcx*8 + 8]', '... and the charge at release (state +0x08)', 'scaling'),
    (0x73E367, 'mulss xmm0, xmm4', 'above full: lerp(1, overcharge)', 'scaling'),
    (0x73E3B2, 'mulss xmm1, xmm5', 'below full: lerp(min, 1)', 'scaling'),
    (0x73E45B, 'movss xmm3, dword ptr [rax + 0x4c]', 'speed multiplier: overcharge (+76) ...', 'scaling'),
    (0x73E460, 'movss xmm2, dword ptr [rax + 0x48]', '... and min (+72)', 'scaling'),
    (0x73E50B, 'movss xmm3, dword ptr [rax + 0x54]', 'damage multiplier: overcharge (+84) ...', 'scaling'),
    (0x73E510, 'movss xmm2, dword ptr [rax + 0x50]', '... and min (+80)', 'scaling'),
    (0x73E5BB, 'movss xmm3, dword ptr [rax + 0x5c]', 'penetration multiplier: overcharge (+92) ...', 'scaling'),
    (0x73E5C0, 'movss xmm2, dword ptr [rax + 0x58]', '... and min (+88)', 'scaling'),
    (0x73E66B, 'movss xmm3, dword ptr [rax + 0x64]', 'distance multiplier getter (no caller): +100 ...', 'scaling'),
    (0x73E670, 'movss xmm2, dword ptr [rax + 0x60]', '... and +96', 'scaling'),
    (0x73E71B, 'movss xmm3, dword ptr [rax + 0x6c]', 'extra arc splits getter (no caller): +108 ...', 'scaling'),
    (0x73E7DB, 'movss xmm3, dword ptr [rax + 0x74]', 'extra arc chains getter (no caller): +116 ...', 'scaling'),
    # projectile consumer
    (0x741BCD, 'test dword ptr [rax + rcx*8], 0x4000', 'weapon fire: the charge capability bit', 'projectile'),
    (0x741BD8, 'call 0x73e3d0', 'speed multiplier', 'projectile'),
    (0x741BE2, 'call 0x73e480', 'damage multiplier', 'projectile'),
    (0x741BED, 'call 0x73e530', 'penetration multiplier', 'projectile'),
    (0x7420BF, 'call 0x6128b0', 'projectile weapons: the projectile_weapon fire ...', 'projectile'),
    (0x61443B, 'call 0x615940', '... the projectile fire path ...', 'projectile'),
    (0x616558, 'movss xmm0, dword ptr [rbp + 0xaa0]', 'speed multiplier ...', 'projectile'),
    (0x616560, 'movss dword ptr [rbp + 0x4c], xmm0', '... into SpawnProjectile extra +0x2C', 'projectile'),
    (0x61653A, 'movss xmm1, dword ptr [rbp + 0xaa8]', 'damage multiplier ...', 'projectile'),
    (0x6165AD, 'movss dword ptr [rbp + 0x50], xmm1', '... into extra +0x30', 'projectile'),
    (0x616568, 'movss xmm0, dword ptr [rbp + 0xab0]', 'penetration multiplier ...', 'projectile'),
    (0x6165B2, 'movss dword ptr [rbp + 0x54], xmm0', '... into extra +0x34', 'projectile'),
    (0x616612, 'call 0x13a9830', 'SpawnProjectile(system, descriptor, extra)', 'projectile'),
    (0x13A9DB2, 'mulss xmm6, dword ptr [r13 + 0x2c]', 'launch speed x the charge speed multiplier', 'projectile'),
    (0x13AA960, 'mov eax, dword ptr [r13 + 0x30]', 'damage multiplier ...', 'projectile'),
    (0x13AA964, 'mov dword ptr [rdi + 0x34], eax', '... kept in the hit record +0x34', 'projectile'),
    (0x13AA967, 'mov eax, dword ptr [r13 + 0x34]', 'penetration multiplier ...', 'projectile'),
    (0x13AA96B, 'mov dword ptr [rdi + 0x38], eax', '... kept in the hit record +0x38', 'projectile'),
    (0x13AA989, 'mov dword ptr [rdi + 0x34], 0x3f800000', 'no extra block: both 1.0', 'projectile'),
    (0x13AD524, 'mulss xmm0, dword ptr [r14 + 0x34]', 'impact: the hit\'s damage scalar x damage multiplier', 'projectile'),
    (0x13AD550, 'movss xmm0, dword ptr [r14 + 0x38]', 'impact: penetration multiplier ...', 'projectile'),
    (0x13AD556, 'mulss xmm0, dword ptr [rbx]', '... x each of the four armor-penetration lanes ...', 'projectile'),
    (0x13AD55A, 'call 0x20bbb78', '... rounded to a whole armor class', 'projectile'),
    # arc consumer
    (0x13B3F6F, 'movss xmm3, dword ptr [rax + 0x64]', 'arc spawn: distance multiplier overcharge (+100) ...', 'arc'),
    (0x13B3F74, 'movss xmm2, dword ptr [rax + 0x60]', '... and min (+96) ...', 'arc'),
    (0x13B3F80, 'movss dword ptr [rdi + 0xf0], xmm0', '... into the arc (+0xF0)', 'arc'),
    (0x13B3F8F, 'movss dword ptr [rdi + 0xf4], xmm0', 'damage multiplier into the arc (+0xF4)', 'arc'),
    (0x13B3FA3, 'movss dword ptr [rdi + 0xf8], xmm0', 'penetration multiplier into the arc (+0xF8)', 'arc'),
    (0x13B4011, 'movss xmm3, dword ptr [rax + 0x6c]', 'extra arc count A: +108 ...', 'arc'),
    (0x13B4016, 'movss xmm2, dword ptr [rax + 0x68]', '... and +104 ...', 'arc'),
    (0x13B402A, 'mov dword ptr [rdi + 0xfc], eax', '... rounded into the arc (+0xFC)', 'arc'),
    (0x13B4097, 'movss xmm3, dword ptr [rax + 0x74]', 'extra arc count B: +116 ...', 'arc'),
    (0x13B409C, 'movss xmm2, dword ptr [rax + 0x70]', '... and +112 ...', 'arc'),
    (0x13B40B0, 'mov dword ptr [rdi + 0x100], eax', '... rounded into the arc (+0x100)', 'arc'),
    # overcharge failure
    (0x73DC87, 'test byte ptr [rdx + 0x14], 1', 'overcharge failure: authority only', 'failure'),
    (0x73DD9F, 'call 0xfdc310', 'the weapon entity is removed', 'failure'),
    (0x73DF54, 'mov r8d, dword ptr [r14 + 0xc8]', '+200: the explosion type ...', 'failure'),
    (0x73DFB4, 'call 0x13c0a80', '... spawned at the weapon position (+0.1 m per axis)', 'failure'),
    (0x73DFC7, 'mov r8d, dword ptr [r14 + 0xc8]', '+200 again ...', 'failure'),
    (0x73DFFE, 'call 0xbe1340', '... replicated', 'failure'),
    # other readers
    (0x75674A, 'mov rax, qword ptr [r10 + 0x60]', 'fire-mode getter: weapon_data +0x60 (12-byte entries) ...', 'firemode'),
    (0x756752, 'mov eax, dword ptr [rax + rdx*4]', '... the current FireMode', 'firemode'),
    (0x83E3DF, 'comiss xmm0, dword ptr [r14]', 'another consumer: accumulator >= charge_time[0] (ready)', 'ready'),
]
RIP_TARGETS = {0x73F1DA: 0x2249A80, 0x5052E2: 0x3326C20, 0x73D515: 0x2249A98}
STRINGS = {0x2249A80: 'WeaponChargeComponent', 0x2249A98: 'weapon_overcharging', 0x2249AF8: None}

# ---------------------------------------------------------------------------------------------------------------
# Member semantics. nativeName: a snake_case name whose length must equal the hidden name length (a Filediver Go
# lead where it fits, else a length-fitted descriptive label marked invented). code: pin groups that read it.
# ---------------------------------------------------------------------------------------------------------------
FIELDS = {
    '0[0].0': dict(nativeName='charge_time', nameSource='filediver_go', unit='seconds', kind='gameplay',
        semantic='charge_time[0]: minimum charge. Releasing at or above it fires; below it cancels. Lower end of '
                 'the min->full multiplier lerp; state-0 projectile from here to charge_time[1].',
        code=['update', 'scaling', 'ready', 'fire'], wiki=('stage', 0)),
    '0[1].0': dict(nativeName='charge_time', nameSource='filediver_go', unit='seconds', kind='gameplay',
        semantic='charge_time[1]: full charge. Safe-mode clamp, auto-fire point (+184), multiplier 1.0 point, '
                 'danger sound and loop effect, start of the overcharge lerp.',
        code=['update', 'scaling', 'fire', 'presentation'], wiki=('stage', 1)),
    '0[2].0': dict(nativeName='charge_time', nameSource='filediver_go', unit='seconds', kind='gameplay',
        semantic='charge_time[2]: overcharge. Unsafe-mode failure point when +185 is set; overcharge multiplier '
                 'point; state-2 projectile at or above it.',
        code=['update', 'scaling', 'fire'], wiki=('stage', 2)),
    '0[0].4': dict(nativeName='projectile_type', nameSource='filediver_go', unit='ProjectileType', kind='gameplay',
        semantic='state-0 projectile (0 = the weapon\'s own projectile)', code=['fire']),
    '0[1].4': dict(nativeName='projectile_type', nameSource='filediver_go', unit='ProjectileType', kind='gameplay',
        semantic='state-1 projectile (default; 0 = the weapon\'s own projectile)', code=['fire']),
    '0[2].4': dict(nativeName='projectile_type', nameSource='filediver_go', unit='ProjectileType', kind='gameplay',
        semantic='state-2 projectile (c >= charge_time[2])', code=['fire']),
    '0[0].8': dict(nativeName='projectile_particle', nameSource='filediver_go', unit='resource', kind='presentation',
        semantic='state-0 shot particle override', code=['fire']),
    '0[1].8': dict(nativeName='projectile_particle', nameSource='filediver_go', unit='resource', kind='presentation',
        semantic='state-1 shot particle override', code=['fire']),
    '0[2].8': dict(nativeName='projectile_particle', nameSource='filediver_go', unit='resource', kind='presentation',
        semantic='state-2 shot particle override', code=['fire']),
    '0[0].16': dict(nativeName=None, unit=None, kind='unknown', semantic='u32 passed with the state-0 shot; '
        'consumer not decoded (0 in every record)', code=['fire']),
    '0[1].16': dict(nativeName=None, unit=None, kind='unknown', semantic='u32 passed with the state-1 shot; '
        'consumer not decoded (0 in every record)', code=['fire']),
    '0[2].16': dict(nativeName=None, unit=None, kind='unknown', semantic='u32 passed with the state-2 shot; '
        'consumer not decoded (0 in every record)', code=['fire']),
    '72.0': dict(nativeName='speed_multiplier_min', nameSource='filediver_go', unit='multiplier', kind='gameplay',
        semantic='projectile launch speed multiplier at charge_time[0] (lerps to 1.0 at full charge)',
        code=['scaling', 'projectile'], wiki=('speed', 'min')),
    '72.4': dict(nativeName='speed_multiplier_overcharge', nameSource='filediver_go', unit='multiplier',
        kind='gameplay', semantic='projectile launch speed multiplier at charge_time[2] (from 1.0 at full charge)',
        code=['scaling', 'projectile'], wiki=('speed', 'max')),
    '72.8': dict(nativeName='damage_multiplier_min', nameSource='filediver_go', unit='multiplier', kind='gameplay',
        semantic='impact damage multiplier at charge_time[0]', code=['scaling', 'projectile', 'arc'],
        wiki=('damage', 'min')),
    '72.12': dict(nativeName='damage_multiplier_overcharge', nameSource='filediver_go', unit='multiplier',
        kind='gameplay', semantic='impact damage multiplier at charge_time[2]', code=['scaling', 'projectile', 'arc'],
        wiki=('damage', 'max')),
    '72.16': dict(nativeName='penetration_multiplier_min', nameSource='filediver_go', unit='multiplier',
        kind='gameplay', semantic='armor-penetration multiplier at charge_time[0] (each AP lane, rounded)',
        code=['scaling', 'projectile', 'arc']),
    '72.20': dict(nativeName='penetration_multiplier_overcharge', nameSource='filediver_go', unit='multiplier',
        kind='gameplay', semantic='armor-penetration multiplier at charge_time[2] (each AP lane, rounded)',
        code=['scaling', 'projectile', 'arc']),
    '72.24': dict(nativeName='distance_multiplier_min', nameSource='filediver_go_corrected_spelling',
        unit='multiplier', kind='gameplay', semantic='ARC distance multiplier at charge_time[0]; read only by arc '
        'weapons (no projectile consumer)', code=['arc'], wiki=('distance', 'min')),
    '72.28': dict(nativeName='distance_multiplier_overcharge', nameSource='filediver_go_corrected_spelling',
        unit='multiplier', kind='gameplay', semantic='ARC distance multiplier at charge_time[2]; arc weapons only',
        code=['arc'], wiki=('distance', 'max')),
    '72.32': dict(nativeName='extra_arc_splits_min', nameSource='filediver_go', unit='count', kind='gameplay',
        semantic='extra arc count A at charge_time[0] (rounded); split-vs-chain order is the Go lead only',
        code=['arc']),
    '72.36': dict(nativeName='extra_arc_splits_overcharge', nameSource='filediver_go', unit='count',
        kind='gameplay', semantic='extra arc count A at charge_time[2]', code=['arc']),
    '72.40': dict(nativeName='extra_arc_chains_min', nameSource='filediver_go', unit='count', kind='gameplay',
        semantic='extra arc count B at charge_time[0] (rounded; the arc spawn then adds a value from manager '
                 'game+0x3326AC0 via 0xA079B0, not traced)',
        code=['arc']),
    '72.44': dict(nativeName='extra_arc_chains_overcharge', nameSource='filediver_go', unit='count',
        kind='gameplay', semantic='extra arc count B at charge_time[2]', code=['arc']),
    '120': dict(nativeName='charge_start_sound_id', nameSource='filediver_go', unit='thin_hash',
        kind='presentation', semantic='sound when charging starts', code=['presentation']),
    '124': dict(nativeName='charge_stop_sound_id', nameSource='filediver_go', unit='thin_hash',
        kind='presentation', semantic='sound when the charge resets', code=['presentation']),
    '128': dict(nativeName='ready_to_fire_sound_id', nameSource='filediver_go', unit='thin_hash',
        kind='presentation', semantic='sound when the charge crosses charge_time[0]', code=['presentation']),
    '132': dict(nativeName='danger_overcharge_sound_id', nameSource='filediver_go', unit='thin_hash',
        kind='presentation', semantic='sound when the charge crosses charge_time[1] (danger zone)',
        code=['presentation']),
    '136': dict(nativeName='charge_mesh', nameSource='filediver_go', unit='thin_hash', kind='presentation',
        semantic='mesh carrying the charge material variable', code=['presentation']),
    '140': dict(nativeName='charge_material', nameSource='filediver_go', unit='thin_hash', kind='presentation',
        semantic='material carrying the charge variable', code=['presentation']),
    '144': dict(nativeName='charge_variable', nameSource='filediver_go', unit='thin_hash', kind='presentation',
        semantic='material variable set to the display value (UI/visual only)', code=['presentation']),
    '152': dict(nativeName='charge_up_muzzle_flash', nameSource='filediver_go', unit='resource',
        kind='presentation', semantic='muzzle effect while charging', code=['presentation']),
    '160': dict(nativeName='charge_up_muzzle_flash_loop', nameSource='filediver_go', unit='resource',
        kind='presentation', semantic='looping muzzle effect once full', code=['presentation']),
    '168': dict(nativeName='charge_anim_id', nameSource='filediver_go', unit='thin_hash', kind='presentation',
        semantic='animation event at charge start', code=['presentation']),
    '172': dict(nativeName='charge_end_anim_id', nameSource='filediver_go', unit='thin_hash', kind='presentation',
        semantic='animation event at charge end', code=['presentation']),
    '176': dict(nativeName='charge_rate_anim_id', nameSource='filediver_go', unit='thin_hash', kind='presentation',
        semantic='animation variable set to the accumulator (seconds)', code=['presentation']),
    '180': dict(nativeName='spin_speed_anim_id', nameSource='filediver_go', unit='thin_hash', kind='presentation',
        semantic='animation variable set to the accumulator (seconds)', code=['presentation']),
    '184': dict(nativeName='auto_fire_in_safety', nameSource='filediver_go', unit='bool', kind='gameplay',
        semantic='outside fire mode 6: fire automatically when the charge first reaches charge_time[1]; '
                 '0 = hold the full charge until release', code=['update']),
    '185': dict(nativeName='explode_when_overcharged', nameSource='length_fitted_invented', unit='bool',
        kind='gameplay', semantic='in fire mode 6: crossing charge_time[2] fires, removes the weapon and spawns '
                 'the +200 explosion', code=['update', 'failure']),
    '188': dict(nativeName='burst_shots_per_charge', nameSource='length_fitted_invented', unit='count',
        kind='gameplay', semantic='shots per charge: > 1 re-fires (burst counter) until the count is reached',
        code=['fire', 'update']),
    '192': dict(nativeName='burst_shot_delay', nameSource='length_fitted_invented', unit='seconds',
        kind='gameplay', semantic='delay before each further burst shot (burst timer)', code=['fire', 'update']),
    '196': dict(nativeName='dry_fire_audio_event', nameSource='filediver_go', unit='thin_hash',
        kind='presentation', semantic='dry-fire sound when the trigger is pressed without ammunition',
        code=['trigger', 'presentation']),
    '200': dict(nativeName='overcharge_explosion_type', nameSource='length_fitted_invented', unit='ExplosionType',
        kind='gameplay', semantic='explosion spawned by the overcharge failure (weapon removed)',
        code=['failure']),
    '204.0': dict(nativeName='required_state', nameSource='length_fitted_invented', unit='ChargeState',
        kind='gameplay', semantic='overcharge limit: the charge state in which the limit applies (code states: '
        '3 below min, 0 min..full, 1 full..over, 2 overcharged)', code=['update']),
    '204.4': dict(nativeName='max_seconds', nameSource='length_fitted_invented', unit='seconds', kind='gameplay',
        semantic='overcharge limit: accumulator seconds after which the failure runs without a shot (0 = off)',
        code=['update']),
}
STRUCT_NAMES = {'204': ('overcharge_limit', 16, 'length_fitted_invented'),
    '72': ('proj_multipliers', 22, 'filediver_go (length 16 != 22: not fitted)'),
    '0': ('charge_state_settings', 21, 'filediver_go')}

# Proposed public field ids (family hd2.fields.charge.*) -------------------------------------------------------------
PROPOSAL = [
    # existing ids: metadata corrections
    dict(id='hd2.fields.charge.level_1', status='existing_correct_unit', path='0[0].0', offset=0, storage='f32',
        unit='seconds', type='number', range='>= 0; keep level_1 <= level_2 <= level_3 and level_2 > 0',
        write='type record, live next frame for every owner', note='Correct the unit from "multiplier" to '
        'seconds and the display to "Minimum charge time"; the offset is right.'),
    dict(id='hd2.fields.charge.level_2', status='existing_correct_unit', path='0[1].0', offset=24, storage='f32',
        unit='seconds', type='number', range='> 0 and >= level_1', write='type record, live',
        note='Display "Full charge time": the safe-mode clamp and auto-fire point.'),
    dict(id='hd2.fields.charge.level_3', status='existing_correct_unit', path='0[2].0', offset=48, storage='f32',
        unit='seconds', type='number', range='> level_2 (else the overcharge lerp divides by level_3)',
        write='type record, live', note='Display "Overcharge time": the Railgun unsafe failure point (3 s).'),
    dict(id='hd2.fields.charge.minimum_seconds', status='existing_mislabelled', path='72.0', offset=72,
        storage='f32', unit='multiplier', type='number', range='>= 0',
        write='type record, live', note='NOT a time: projectile speed multiplier at minimum charge. Recommend a '
        'schemas/player_weapon_fields.json alias_rules entry {alias: charge.minimum_seconds, canonical: '
        'charge.speed_multiplier_min, requires_identical_backing: true, deprecated: true} with the display/unit '
        'corrected; never retarget the old id to +0 silently (existing mods would change behaviour).'),
    dict(id='hd2.fields.charge.maximum_seconds', status='existing_mislabelled', path='72.4', offset=76,
        storage='f32', unit='multiplier', type='number', range='>= 0', write='type record, live',
        note='NOT a time: projectile speed multiplier at full overcharge. Deprecated alias of '
        'charge.speed_multiplier_overcharge (alias_rules). On arc weapons (ARC-3) neither id has any consumer: '
        'tests/test_support_weapon_authoring.py and test_multi_mod_composition.py write it on the ARC-3.'),
    # new ids
    dict(id='hd2.fields.charge.speed_multiplier_min', status='new', path='72.0', offset=72, storage='f32',
        unit='multiplier', type='number', range='>= 0 (0 stops the projectile)', write='type record, live'),
    dict(id='hd2.fields.charge.speed_multiplier_overcharge', status='new', path='72.4', offset=76, storage='f32',
        unit='multiplier', type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.charge.damage_multiplier_min', status='new', path='72.8', offset=80, storage='f32',
        unit='multiplier', type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.charge.damage_multiplier_overcharge', status='new', path='72.12', offset=84,
        storage='f32', unit='multiplier', type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.charge.penetration_multiplier_min', status='new', path='72.16', offset=88, storage='f32',
        unit='multiplier', type='number', range='>= 0 (result rounded per AP lane)', write='type record, live'),
    dict(id='hd2.fields.charge.penetration_multiplier_overcharge', status='new', path='72.20', offset=92,
        storage='f32', unit='multiplier', type='number', range='>= 0 (rounded per AP lane)',
        write='type record, live'),
    dict(id='hd2.fields.charge.arc_distance_multiplier_min', status='new_arc_only', path='72.24', offset=96,
        storage='f32', unit='multiplier', type='number', range='>= 0', write='type record, live',
        note='Expose only on arc weapons: projectile weapons never read it (the Railgun 0.7 is inert).'),
    dict(id='hd2.fields.charge.arc_distance_multiplier_overcharge', status='new_arc_only', path='72.28',
        offset=100, storage='f32', unit='multiplier', type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.charge.auto_fire_at_full', status='new', path='184', offset=184, storage='u8',
        unit=None, type='boolean', range='0 or 1', write='type record, live'),
    dict(id='hd2.fields.charge.explode_at_overcharge', status='new_hazard', path='185', offset=185, storage='u8',
        unit=None, type='boolean', range='0 or 1', write='type record, live',
        note='Hazard: 1 removes the weapon and explodes at level_3 in fire mode 6. Needs an explicit '
        'acknowledgement in addition to allow_unverified_effect.'),
    dict(id='hd2.fields.charge.overcharge_explosion', status='new_reference', path='200', offset=200,
        storage='u32', unit=None, type='explosion_reference', range='a catalogued ExplosionType',
        write='type record, live; reuse the typed explosion-reference guard (package residency, typed '
        'no-action sentinel) of terminal.explosion'),
    dict(id='hd2.fields.charge.overcharge_limit_state', status='new_hazard', path='204.0', offset=204,
        storage='u32', unit=None, type='enum', range='0..3 (ChargeState as the update computes it)',
        write='type record, live'),
    dict(id='hd2.fields.charge.overcharge_limit_seconds', status='new_hazard', path='204.4', offset=208,
        storage='f32', unit='seconds', type='number', range='>= 0 (0 disables)', write='type record, live',
        note='Hazard: a non-zero limit makes the weapon explode without firing (Epoch 3.25 s).'),
    dict(id='hd2.fields.charge.burst_shots', status='new', path='188', offset=188, storage='u32',
        unit='shots', type='integer', range='0..16 suggested (<= 1 = single shot)', write='type record, live',
        note='Each burst shot goes through the normal fire path (ammunition behaviour per shot not proven).'),
    dict(id='hd2.fields.charge.burst_interval_seconds', status='new', path='192', offset=192, storage='f32',
        unit='seconds', type='number', range='> 0 when burst_shots > 1', write='type record, live'),
]
NOT_PROMOTED = {
    '72.32': 'extra arc counts: which of +104/+112 is split vs chain rests on the Go field order only; both hidden '
             'names have the same length (20/27), the ARC-3 holds 0/0/0/0, and only arc weapons read them.',
    '72.36': 'see +104', '72.40': 'see +104', '72.44': 'see +104',
    '0[0].4': 'per-state projectile types are attack-output selectors (docs/attack-outputs.md: BLOCKED); promote '
              'through the attack-output graph, not as charge fields.',
    '0[1].4': 'see +4', '0[2].4': 'see +4',
    '0[0].8': 'per-state shot particle: presentation reference, needs resource residency proof.',
    '0[1].8': 'see +8', '0[2].8': 'see +8',
    '0[0].16': 'consumer not decoded; 0 in every record.', '0[1].16': 'see +16', '0[2].16': 'see +16',
}
PRESENTATION_REASON = ('presentation only (sound/material/effect/animation/HUD); the charge UI timing derives from '
    'charge_time and the accumulator, it does not drive firing.')


# ---------------------------------------------------------------------------------------------------------------
# helpers shared with research_hoverpack_components.py
# ---------------------------------------------------------------------------------------------------------------
def canonical(value):
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return str(value)
        return round(value, 6)
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value


def check_pins(image, pins, rip_targets=None) -> list[dict]:
    """Decode every pin; fail loudly when an instruction no longer contains the expected text."""
    out = []
    for rva, needle, role, group in pins:
        entry = image.pin(rva, role)
        if needle not in entry['asm']:
            raise ValueError(f'pin {rva:#x} changed: {entry["asm"]!r} does not contain {needle!r}')
        expected = (rip_targets or {}).get(rva)
        if expected is not None and entry.get('ripTarget') != expected:
            raise ValueError(f'pin {rva:#x} references {entry.get("ripTarget")} not {expected:#x}')
        entry['group'] = group
        out.append(entry)
    return out


def manager_map(image) -> dict[str, dict]:
    """Component name -> manager global, from the manager assigner (0x568230) and the memory report (0x56A920)."""
    import bisect
    import re
    pairs, last = [], None
    for ins in image.function_insns(0x568230):
        if ins.mnemonic == 'lea' and 'rbx +' in ins.op_str:
            last = ins.operands[1].mem.disp
        elif ins.mnemonic == 'mov' and ins.op_str.startswith('qword ptr [rip') and last is not None:
            pairs.append((last, image.rip_target(ins), ins.address))
            last = None
    pairs.sort()
    offsets = [p[0] for p in pairs]
    names, r9 = {}, None
    for ins in image.function_insns(0x56A920):
        if ins.mnemonic == 'mov' and ins.op_str.startswith('r9d, dword ptr [rdi'):
            r9 = ins.operands[1].mem.disp
        if ins.mnemonic == 'lea' and ins.op_str.startswith('r8, [rip'):
            match = re.match(r'"(\w+)" : \{ "max"', image.cstr(image.rip_target(ins)))
            if match and r9 is not None:
                index = bisect.bisect_right(offsets, r9) - 1
                world_offset, global_rva, site = pairs[index]
                names[match.group(1)] = {'global': global_rva, 'worldOffset': world_offset,
                    'assignSite': site, 'reportField': r9 - world_offset}
                r9 = None
    return names


def snapshot_tables(component, offset: int, manager_global: int) -> list[dict]:
    """For each retained snapshot: is [entity manager + offset] the loaded table (byte-identical to the file), and
    how many live instances does the component manager hold (+0x10)?"""
    from scan import instances
    out = []
    for name in SNAPSHOTS:
        path = build_profile.snapshot_directory() / name
        if not path.is_file():
            out.append({'snapshot': name, 'status': 'absent'})
            continue
        reader = instances.SnapshotReader(name)
        try:
            base = reader.modules['game.dll']['base']
            em = instances.u64(reader, base + G_ENTITY_MANAGER)
            block = instances.u64(reader, em + offset) if em else None
            live = reader.read(block, len(component.body)) if block else None
            manager = instances.u64(reader, base + manager_global)
            header = reader.read(manager, 0x18) if manager else None
            out.append({'snapshot': name, 'status': 'read',
                'loadedTableEqualsFile': live == component.body if live else None,
                'tableBytes': len(component.body),
                'managerCapacity': struct.unpack_from('<I', header, 0)[0] if header else None,
                'liveInstances': struct.unpack_from('<I', header, 0x10)[0] if header else None})
        finally:
            reader.close()
    return out


def delta_targets(t: tables.EntityTables, components: list[str]) -> dict[str, int]:
    """Entity-delta (customization) entries that patch each component: 0 = no per-instance customization."""
    from reference_format import dl_hash
    from research_magazine_attachments import DATALIB, entity_deltas
    t.entity_rows()
    by_type = {type_hash: index for index, type_hash in t._index_type.items()}
    wanted = {by_type.get(dl_hash(name)): name for name in components}
    deltas, _ = entity_deltas((DATALIB / 'generated_entity_deltas.dl_bin').read_bytes())
    counts = {name: 0 for name in components}
    for entry in deltas.values():
        for item in entry['entries']:
            if item['component'] in wanted:
                counts[wanted[item['component']]] += 1
    return counts


def pin_refs(pin_by_group: dict, groups, offset: int) -> list[int]:
    """Pins of the given groups that read ``offset`` from a record pointer (index-scaled state reads excluded),
    or whose role names the member (+offset)."""
    import re
    disp = f'+ {offset:#x}]' if offset >= 10 else f'+ {offset}]'   # capstone prints 0..9 in decimal
    role = re.compile(r'\+%d\b' % offset)
    out = []
    for group in groups:
        for pin in pin_by_group.get(group, []):
            asm = pin['asm']
            scaled = '*8' in asm or '*4' in asm or '*2' in asm or '[rbp' in asm or '[rsp' in asm
            direct = (disp in asm and not scaled) or (offset == 0 and re.search(r'\[(r13|rax|rdi|r14|r15|r12)\]',
                asm))
            if direct or role.search(pin['role']):
                out.append(pin['rva'])
    return sorted(set(out))


def golib_leads(t, record_type):
    try:
        return golib.leads_for(t, golib.default_library(), record_type)
    except Exception:  # noqa: BLE001 - leads are optional
        return {}


# ---------------------------------------------------------------------------------------------------------------
# identities and published values
# ---------------------------------------------------------------------------------------------------------------
def identities() -> dict[int, dict]:
    """Resource -> {name, kind, source}: player weapons from the SDK catalog, support weapons from the support
    weapon research, enemy weapons from the enemy attack research."""
    out = {}
    player = json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text(encoding='utf-8'))
    for weapon in player['weapons']:
        for resource in weapon.get('resources') or []:
            out[int(resource, 16)] = {'name': weapon['name'], 'kind': 'player_weapon',
                'source': 'sdk/PlayerWeaponAuthoringCapabilities.json'}
    support = json.loads((ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    for weapon in support['weapons']:
        for resource in weapon.get('resourceHashes') or []:
            out[int(resource, 16)] = {'name': weapon['catalogIdentity'], 'kind': 'support_weapon',
                'source': 'research/support-weapon-runtime-F5FEE03DCFDB.json'}
    enemies = json.loads((ROOT / 'research/enemy-attacks-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    for enemy in enemies.get('classes') or []:
        if not isinstance(enemy, dict):
            continue
        for slot in enemy.get('slots') or []:
            weapon = slot.get('weapon')
            if isinstance(weapon, str) and weapon.startswith('0x'):
                out.setdefault(int(weapon, 16), {'name': f"{enemy.get('name')} weapon (slot {slot.get('slot')})",
                    'kind': 'enemy_weapon', 'source': 'research/enemy-attacks-F5FEE03DCFDB.json'})
    return out


def wiki_charge() -> dict[str, dict]:
    out = {}
    for name in ('wiki_support_weapons.json', 'wiki_player_weapons.json'):
        path = WIKI / name
        if not path.is_file():
            continue
        for weapon in json.loads(path.read_text(encoding='utf-8'))['weapons']:
            charge = (weapon.get('mechanics') or {}).get('charge')
            overcharge = [a for a in weapon.get('attacks') or [] if 'Overcharge' in (a.get('name') or '')]
            if charge or overcharge:
                out[weapon['name']] = {'charge': charge, 'overchargeExplosions': overcharge,
                    'wikiRevisionId': weapon.get('wikiRevisionId'), 'file': name}
    return out


def explosion_matches(sv, native_type: int, branch: dict) -> dict:
    row = sv.decode('explosion', native_type)
    damage = sv.decode('damage', row['4']) if row else None
    area = branch.get('areaOfEffect') or {}
    special = branch.get('specialEffects') or {}
    published = {'inner_radius': (area.get('innerRadiusMeters') or {}).get('value'),
        'outer_radius': (area.get('outerRadiusMeters') or {}).get('value'),
        'shockwave_radius': (area.get('shockwaveRadiusMeters') or {}).get('value'),
        'standard_damage': ((branch.get('damage') or {}).get('standard') or {}).get('value'),
        'durable_damage': ((branch.get('damage') or {}).get('durable') or {}).get('value'),
        'demolition': (special.get('demolitionForce') or {}).get('value'),
        'stagger': (special.get('staggerForce') or {}).get('value'),
        'push_force': (special.get('pushForce') or {}).get('value')}
    native = {'inner_radius': row['16'], 'outer_radius': row['20'], 'shockwave_radius': row['24'],
        'standard_damage': damage['4'][0], 'durable_damage': damage['4'][1], 'demolition': damage['28'],
        'stagger': damage['32'], 'push_force': damage['36']} if row and damage else {}
    compared = {key: {'native': canonical(native.get(key)), 'published': value,
        'exact': value is not None and native.get(key) is not None and abs(native[key] - value) <= 1e-4}
        for key, value in published.items()}
    return {'explosionType': native_type, 'damageType': row['4'] if row else None, 'branch': branch.get('name'),
        'fields': compared, 'allExact': all(item['exact'] for item in compared.values() if item['published']
            is not None)}


# ---------------------------------------------------------------------------------------------------------------
def build() -> dict:
    t = tables.pinned()
    component = t.component(COMPONENT)
    if component.record_type != RECORD_TYPE or component.record_size != RECORD_SIZE:
        raise ValueError('WeaponChargeComponentData layout changed')
    members = component.members()
    by_path = {m.path: m for m in members}
    ident = identities()
    owners = component.owner_map()

    # family: every record, owned or not
    records = []
    for record in range(component.count):
        resources = owners.get(record, [])
        names = [ident.get(r, {}).get('name') or t.label(r) for r in resources]
        records.append({'record': record, 'owners': [hexid(r) for r in resources],
            'ownerPaths': [t.name(r) for r in resources], 'labels': names,
            'identity': [ident.get(r) for r in resources],
            'label': ', '.join(names) if names else f'unowned record {record}'})
    labels = [item['label'] for item in records]
    matrix = {}
    for member in members:
        values = [decode(member, component.raw(i)) for i in range(component.count)]
        matrix[member.path] = values
    owned = {item['label']: int(item['owners'][0], 16) for item in records if item['owners']}
    family = compare.Family(t, COMPONENT, owned)
    description = family.describe(include_constant=True)

    # published values
    wiki = wiki_charge()
    published = {}
    for item in records:
        name = item['labels'][0] if item['labels'] else None
        entry = wiki.get(name)
        if not entry or not entry['charge']:
            continue
        charge = entry['charge']
        values = {}
        for index, stage in enumerate(charge.get('stages') or []):
            values[f'0[{index}].0'] = stage['timeSeconds']
        for key, path_min, path_max in (('speedMultiplier', '72.0', '72.4'), ('damageMultiplier', '72.8', '72.12'),
                ('distanceMultiplier', '72.24', '72.28')):
            if charge.get(key):
                values[path_min], values[path_max] = charge[key]['min'], charge[key]['max']
        published[item['label']] = {'record': item['record'], 'values': values,
            'wikiRevisionId': entry['wikiRevisionId'],
            'exact': {path: abs(matrix[path][item['record']] - value) <= 1e-4 for path, value in values.items()},
            'derivedStageDamageNote': 'the wiki per-stage damage multipliers are a lerp over [t0, t2]; the native '
                'curve is min->1.0 over [t0, t1] then 1.0->overcharge over [t1, t2] (0x73E280), so they are not '
                'independent values and are not compared'}

    # overcharge explosions
    from scan import settings
    sv = settings.SettingsView(t)
    explosions = []
    for item in records:
        name = item['labels'][0] if item['labels'] else None
        native_type = matrix['200'][item['record']]
        row = sv.decode('explosion', native_type)
        entry = {'record': item['record'], 'label': item['label'], 'explosionType': native_type,
            'row': {'damageType': row['4'], 'innerRadius': canonical(row['16']), 'outerRadius': canonical(row['20']),
                'shockwaveRadius': canonical(row['24'])} if row else None,
            'explodesOnOvercharge': matrix['185'][item['record']],
            'limit': {'state': matrix['204.0'][item['record']], 'seconds': canonical(matrix['204.4'][item['record']])}}
        branches = (wiki.get(name) or {}).get('overchargeExplosions') or []
        if branches:
            entry['published'] = [explosion_matches(sv, native_type, branch) for branch in branches]
        explosions.append(entry)

    # native code
    from scan import xref
    image = xref.CodeImage.from_snapshot('game.dll')
    pins = check_pins(image, PINS, RIP_TARGETS)
    strings = {f'{rva:#x}': image.cstr(rva) for rva in (0x2249A80, 0x2249A98)}
    if strings['0x2249a80'] != 'WeaponChargeComponent' or strings['0x2249a98'] != 'weapon_overcharging':
        raise ValueError('pinned strings changed')
    managers = manager_map(image)
    if managers.get('weapon_charge', {}).get('global') != MANAGERS['weapon_charge']:
        raise ValueError('weapon_charge manager global changed')
    accessors = {f'{root:#x}': [f'{s:#x}' for s in sites]
        for root, sites in sorted(image.global_accessors(MANAGERS['weapon_charge']).items())}
    groups = {}
    for pin in pins:
        groups.setdefault(pin['group'], []).append(pin['rva'])
    fire_mode_names = {}
    fm_path = ROOT / 'research/weapon-fire-modes-F5FEE03DCFDB.json'
    fire_modes = json.loads(fm_path.read_text(encoding='utf-8'))
    for weapon in fire_modes['weapons']:
        if 'charge' in (weapon.get('families') or []) or weapon['weapon'] in ('RS-422 Railgun', 'PLAS-45 Epoch'):
            fire_mode_names[weapon['weapon']] = {'slots': weapon['slots'], 'selector': weapon['selector']}

    # lifecycle
    loaded = snapshot_tables(component, LOADED_TABLE_OFFSET, MANAGERS['weapon_charge'])
    deltas = delta_targets(t, [COMPONENT])

    # existing schema audit
    schema = json.loads((ROOT / 'schemas/player_weapon_fields.json').read_text(encoding='utf-8'))
    existing = [f for f in schema['fields'] if isinstance(f, dict) and f.get('component') == COMPONENT
        and f['id'] in CORRECTED | {'charge.minimum_seconds', 'charge.maximum_seconds'}]
    aliases = {rule['alias']: rule['canonical'] for rule in schema.get('alias_rules', [])}
    audit = []
    for field in existing:
        member = next((m for m in members if m.offset == field['offset']), None)
        spec = FIELDS.get(member.path) if member else None
        audit.append({'id': 'hd2.fields.' + field['id'], 'offset': field['offset'], 'path': member.path if member
            else None, 'schemaUnit': field.get('unit'), 'schemaDisplay': field.get('display_name'),
            'nativeMeaning': spec['semantic'] if spec else None, 'nativeUnit': spec['unit'] if spec else None,
            # Before the 0.30.0-dev correction the level ids were published as multipliers and the *_seconds ids as
            # times; the schema now carries the native units and the *_seconds ids are deprecated aliases.
            'verdict': ('correct_offset_wrong_unit' if spec and spec['unit'] != field.get('unit') and
                spec['unit'] == 'seconds' else 'mislabelled' if spec and spec['unit'] != field.get('unit') else
                'deprecated_alias' if field['id'] in aliases else 'corrected' if field['id'] in CORRECTED else
                'consistent'),
            'aliasOf': aliases.get(field['id'])})

    # candidates
    leads = golib_leads(t, RECORD_TYPE)
    candidates = []
    pin_by_group = {g: [p for p in pins if p['group'] == g] for g in groups}
    for member in members:
        spec = FIELDS.get(member.path)
        values = dict(zip(labels, (canonical(v) for v in matrix[member.path])))
        varying = len({json.dumps(v) for v in values.values()}) > 1
        refs = pin_refs(pin_by_group, (spec or {}).get('code', []), member.offset)
        code_read = bool(refs)
        name = spec['nativeName'] if spec else None
        fit = bool(name) and member.name_length is not None and len(name) == member.name_length
        pub = [label for label, item in published.items() if member.path in item['exact']]
        pub_exact = bool(pub) and all(published[label]['exact'][member.path] for label in pub)
        if member.path == '200':
            pub = [e['label'] for e in explosions if e.get('published')]
            pub_exact = bool(pub) and all(b['allExact'] for e in explosions for b in e.get('published', []))
        evidence = {'codeRead': code_read, 'publishedExact': pub_exact, 'liveTest': False, 'nameLengthFit': fit,
            'differential': varying}
        lead = leads.get(member.offset)
        notes = []
        if spec and spec.get('nameSource', '').startswith('length_fitted'):
            notes.append('nativeName is a length-fitted descriptive label, not a recovered name')
        if lead:
            notes.append(f"Filediver lead: {lead['label']} ({lead['strength']})")
        candidates.append(report.candidate(member.path, member.offset, member.storage, member.name_length,
            member.kind, values, evidence, proposed=name, notes=notes,
            semantic=spec['semantic'] if spec else None, unit=spec['unit'] if spec else None,
            role=spec['kind'] if spec else 'unknown', nameSource=spec.get('nameSource') if spec else None,
            publishedBy=pub, codeRefs=sorted(set(refs)),
            semanticsFromCode=bool(spec and spec['kind'] != 'unknown' and code_read)))

    summary = {
        'records': component.count, 'ownedRecords': len(owners), 'recordSize': component.record_size,
        'sharedRecords': sum(1 for v in owners.values() if len(v) > 1)}
    railgun = next(i for i in records if 'RS-422 Railgun' in i['labels'])
    rail = railgun['record']
    summary['railgun'] = {'record': rail, 'chargeTimes': [canonical(matrix[f'0[{i}].0'][rail]) for i in range(3)],
        'speedMultiplier': [canonical(matrix['72.0'][rail]), canonical(matrix['72.4'][rail])],
        'damageMultiplier': [canonical(matrix['72.8'][rail]), canonical(matrix['72.12'][rail])],
        'penetrationMultiplier': [canonical(matrix['72.16'][rail]), canonical(matrix['72.20'][rail])],
        'distanceMultiplier': [canonical(matrix['72.24'][rail]), canonical(matrix['72.28'][rail])],
        'autoFireInSafety': matrix['184'][rail], 'explodeWhenOvercharged': matrix['185'][rail],
        'overchargeExplosionType': matrix['200'][rail], 'limit': [matrix['204.0'][rail],
            canonical(matrix['204.4'][rail])], 'burst': [matrix['188'][rail], canonical(matrix['192'][rail])],
        'fireModes': fire_mode_names.get('RS-422 Railgun'),
        'behaviour': {
            'safe (fire mode 5)': 'charge clamps at 0.5 s and is held until release; releasing at >= 0.45 s fires',
            'unsafe (fire mode 6)': 'charge grows unbounded; damage lerps 1.0 -> 2.5 and speed stays 1.0 between '
                '0.5 s and 3.0 s; at 3.0 s the weapon fires, is removed, and ExplosionType 326 (300/300 damage, '
                'AP 3, radii 0.4/2/3 m) spawns at the weapon',
            'minimum-charge shot': 'released between 0.45 s and 0.5 s: speed x 0.7..1.0, damage x 1.0, '
                'penetration x 1.0'}}

    model = {
        'units': 'seconds for every charge time; dimensionless multipliers; the accumulator advances by the frame '
                 'delta (seconds) while the trigger is held',
        'chargeStates': STATE_NAMES,
        'fireMode': {'unsafe': FIRE_MODE_UNSAFE, 'getter': '0x756730 (weapon_data manager +0x60, 12-byte '
            'entries, +0)', 'railgunSlots': fire_mode_names.get('RS-422 Railgun'),
            'note': 'fire mode 6 is the only value the charge update tests; the Railgun binds Firemode to slots '
                    '[5, 6] (Safe/Unsafe), the Epoch holds [6, 6] (always unbounded), the ARC-3 holds [5, 6] '
                    'with no selector bound (never 6)'},
        'scaling': 'c <= t1: m = min + (1 - min) * clamp((c - t0) / (t1 - t0 or t1)); c > t1: m = 1 + '
                   '(over - 1) * clamp((c - t1) / (t2 - t1 or t2)); c is the charge at release (state +0x08)',
        'perInstanceState': {'manager': '+0x40, 40 bytes per instance', '+0x00': 'display value (material/HUD)',
            '+0x04': 'accumulator (s)', '+0x08': 'charge at release (s)', '+0x0C': 'trigger held (u8)',
            '+0x10': 'playing charge sound', '+0x14': 'burst shots fired', '+0x18': 'burst timer (s)',
            '+0x1C': 'loop effect id', '+0x20': 'shot pending (u8)', '+0x24': 'avatar perspective (RTPC)'},
        'authority': 'the update fires only when the weapon entity is owned/authoritative (descriptor +0x14 bit 0 '
                     'or state +0x20); the failure runs only on authority. Writes therefore act where the weapon '
                     'is simulated (its owner): a host-only write changes the host\'s own weapons (hypothesis for '
                     'remote players; not live-tested).',
        'uiVsMechanics': 'the 0.7/0.3 display curve, material variable, RTPC and reticle shake are derived from '
                         'charge_time and the accumulator; none of them feeds back into firing',
    }

    lifecycle = {'resolver': '0x5052C0', 'perInstanceCopy': 'manager +0x90 (0xD8 stride), only for entities '
        'present in the manager\'s resolved-copy map (+0x50); filled by no customization (entity deltas)',
        'typeRecord': '[entity manager +0xF12AD8] = the loaded WeaponChargeComponentData block',
        'snapshots': loaded, 'entityDeltasTargetingComponent': deltas[COMPONENT],
        'conclusion': 'type record read live: a write to the record takes effect on the next frame/shot for every '
                      'owner of that record, including weapons already in hand (no respawn needed)'}

    sharing = {'owners': {item['label']: len(item['owners']) for item in records},
        'sharedRecords': [], 'note': 'every owned record has exactly one owner; record 10 has no owner. The '
        'Watcher arc weapon and 0x345AC393DD820704 hold identical values in separate records.'}

    doc = report.document('RS-422 Railgun charge and overcharge (WeaponChargeComponent family)', {
        'component': COMPONENT, 'recordType': RECORD_TYPE, 'recordSize': RECORD_SIZE,
        'layoutFingerprint': t.fingerprint(COMPONENT), 'labels': labels,
        'gameDll': image.describe()}, candidates,
        summary=summary, records=records, matrix={path: dict(zip(labels, (canonical(v) for v in values)))
            for path, values in matrix.items()},
        familyClusters=description['clusters'], published=published, overchargeExplosions=explosions,
        model=model, lifecycle=lifecycle, sharing=sharing,
        code={'managers': {k: {'global': v['global'], 'assignSite': v['assignSite']} for k, v in managers.items()
                if k in MANAGERS}, 'weaponChargeAccessors': accessors, 'strings': strings,
            'functions': {'0x73C8F0': 'charge update (per frame, dt)', '0x73D8C0': 'fire helper (burst, per-state '
                'projectile)', '0x73DC60': 'overcharge failure (weapon removed, explosion)', '0x73E280':
                'charge scaling lerp', '0x5052C0': 'record resolver', '0x741A00': 'weapon fire with charge '
                'multipliers', '0x13B3910': 'arc spawn', '0x13A9830': 'SpawnProjectile', '0x13AC1F0': 'projectile '
                'impact', '0x756730': 'current fire mode', '0x17B71F0': 'HUD reticle', '0x7406A0': 'weapon update '
                '(trigger -> charge state)'},
            'pins': pins},
        existingIdAudit=audit,
        promotionProposal={'family': 'hd2.fields.charge', 'fields': PROPOSAL,
            'acknowledgement': 'allow_unverified_effect until a live test passes (native_consumer_proven offline); '
                'hazard fields (explode_at_overcharge, overcharge_limit_*) additionally need an explicit hazard '
                'acknowledgement; overcharge_explosion reuses the typed explosion-reference guard',
            'writeSemantics': 'patch the WeaponChargeComponentData type record of the weapon\'s own record (unique '
                'owner); takes effect next frame (no per-instance copy); expect/ensure guarded like the existing '
                'charge.* fields',
            'evidenceTier': 'native_consumer_proven; charge times and speed/damage/distance multipliers also '
                'publishedExact (wiki) for RS-422, ARC-3, PLAS-45, 40-K'},
        notPromoted=[{'path': path, 'reason': reason} for path, reason in NOT_PROMOTED.items()] +
            [{'path': path, 'reason': PRESENTATION_REASON} for path, spec in FIELDS.items()
                if spec['kind'] == 'presentation' and path not in NOT_PROMOTED],
        liveTests=LIVE_TESTS,
        openQuestions=OPEN_QUESTIONS)
    return doc


LIVE_TESTS = [
    {'id': 'railgun-times', 'target': 'RS-422 Railgun', 'writes': {'charge.level_1': 0.05, 'charge.level_2': 2.0,
        'charge.level_3': 8.0}, 'expect': 'Safe: holding reaches full only after 2 s (danger sound/reticle late); '
        'a tap fires at once. Unsafe: no explosion before 8 s (vanilla 3 s).'},
    {'id': 'railgun-no-explode', 'target': 'RS-422 Railgun', 'writes': {'charge.explode_at_overcharge': 0},
        'expect': 'Unsafe: hold 10 s, no explosion; release fires a full-overcharge shot.'},
    {'id': 'railgun-limit', 'target': 'RS-422 Railgun', 'writes': {'charge.explode_at_overcharge': 0,
        'charge.overcharge_limit_state': 1, 'charge.overcharge_limit_seconds': 1.5}, 'expect': 'Unsafe: at 1.5 s '
        'the weapon is removed and explodes WITHOUT firing (the Epoch rule, moved into the full..over window).'},
    {'id': 'railgun-autofire', 'target': 'RS-422 Railgun', 'writes': {'charge.auto_fire_at_full': 1},
        'expect': 'Safe: the shot leaves automatically at 0.5 s while the trigger is still held.'},
    {'id': 'railgun-speed', 'target': 'RS-422 Railgun', 'writes': {'charge.speed_multiplier_min': 0.05,
        'charge.speed_multiplier_overcharge': 0.05}, 'expect': 'Release at 0.45 s (min): the round crawls '
        '(about 100 m/s). Safe full shot unchanged (1.0). Unsafe late shots slow down towards x0.05.'},
    {'id': 'railgun-ap', 'target': 'RS-422 Railgun', 'writes': {'charge.penetration_multiplier_overcharge': 0.2},
        'expect': 'AP 5 x 0.2 = 1 near 3 s: unsafe late shots bounce off medium armor; safe shots unchanged.'},
    {'id': 'accelerator-burst', 'target': 'PLAS-39 Accelerator Rifle', 'writes': {'charge.burst_shots': 5,
        'charge.burst_interval_seconds': 0.3}, 'expect': 'One charge fires 5 shots 0.3 s apart (vanilla 2 x '
        '0.12 s); ammunition use per shot recorded.'},
    {'id': 'railgun-explosion', 'target': 'RS-422 Railgun', 'writes': {'charge.overcharge_explosion': 321},
        'expect': 'Unsafe failure explosion becomes the Epoch one (800 damage, 3/4/5 m). Requires the Epoch '
        'package resident (bring an Epoch) or the guard refuses.'},
]
OPEN_QUESTIONS = [
    'ARC-3 Arc Thrower repeat fire while held: its record has +184 = 0 and fire mode 5, so the charge update holds '
    'the full charge; the repeat must come from the trigger/fire-mode handling outside 0x73C8F0 (not traced).',
    'ChargeState enum names: the update computes 3 (<= t0), 0 (t0..t1], 1 (t1..t2], 2 (> t2); the type library '
    'enum value names were not decoded.',
    'Burst shots and ammunition: each burst shot goes through 0x741A00; whether a shot is skipped when the '
    'magazine is empty was not traced (the Railgun holds one round).',
    'Extra arc counts: the arc instance +0xFC/+0x100 consumers (split vs chain) were not traced.',
    'Remote-player semantics of writes (owner-simulated update) need a two-peer test.',
    'Record 10 (no owner) and 0x345AC393DD820704 / 0x24510E7B16B5F7A5 have no published identity.',
]


def markdown(doc: dict) -> str:
    lines = ['# RS-422 Railgun charge and overcharge (WeaponChargeComponent family)', '',
        f"Build {doc['build']}. Generated by `scripts/research_railgun_charge.py` (research only; nothing is promoted "
        'here). Full evidence, pins and the per-record matrix: `research/railgun-charge-F5FEE03DCFDB.json`.', '',
        '## Railgun summary', '']
    rail = doc['summary']['railgun']
    lines += [f"- Charge times (s): {rail['chargeTimes']} (min / full / overcharge).",
        f"- Speed multiplier min/over: {rail['speedMultiplier']}; damage: {rail['damageMultiplier']}; "
        f"penetration: {rail['penetrationMultiplier']}; distance: {rail['distanceMultiplier']} (no projectile "
        'consumer).',
        f"- auto_fire_in_safety {rail['autoFireInSafety']}, explode on overcharge {rail['explodeWhenOvercharged']}, "
        f"explosion type {rail['overchargeExplosionType']}, limit {rail['limit']}, burst {rail['burst']}.",
        f"- Fire modes: {rail['fireModes']}."]
    for key, text in rail['behaviour'].items():
        lines.append(f'- {key}: {text}')
    lines += ['', '## How charging works (native)', '']
    model = doc['model']
    lines += [f"- Units: {model['units']}.", f"- Fire mode: {model['fireMode']['note']}.",
        f"- Scaling: {model['scaling']}.", f"- Authority: {model['authority']}",
        f"- UI vs mechanics: {model['uiVsMechanics']}.",
        f"- Lifecycle: {doc['lifecycle']['conclusion']}. Entity deltas targeting the component: "
        f"{doc['lifecycle']['entityDeltasTargetingComponent']}. Loaded table equals file in "
        f"{sum(1 for s in doc['lifecycle']['snapshots'] if s.get('loadedTableEqualsFile'))} retained snapshots.", '']
    lines += ['Key functions: ' + ', '.join(f'`{k}` {v}' for k, v in doc['code']['functions'].items()) + '.', '']
    lines += ['## Members', '', report.markdown_table(['path', 'offset', 'len', 'name (source)', 'unit', 'role',
        'confidence', 'meaning'], [[c['path'], c['offset'], c['nameLength'], f"{c['proposedName']} "
        f"({c.get('nameSource')})", c.get('unit'), c.get('role'), c['confidence'], c.get('semantic')]
        for c in doc['candidates']]), '']
    lines += ['Confidence follows `scripts/scan/report.py` mechanically (CONFIRMED = code read + exact published '
        'value; STRONG = code read + name-length fit + differential across the family). Members whose semantics '
        'are code-proven but constant across the family stay at the mechanical label; see `semanticsFromCode`.', '']
    lines += ['## Per-record matrix (gameplay members)', '']
    gameplay = [c['path'] for c in doc['candidates'] if c.get('role') == 'gameplay']
    labels = doc['scope']['labels']
    lines += [report.markdown_table(['path'] + labels, [[p] + [doc['matrix'][p][label] for label in labels]
        for p in gameplay]), '']
    lines += ['## Published values', '']
    for label, item in doc['published'].items():
        exact = all(item['exact'].values())
        lines.append(f"- {label}: {len(item['values'])} published values, all exact: {exact}.")
    for entry in doc['overchargeExplosions']:
        for branch in entry.get('published', []):
            lines.append(f"- {entry['label']}: ExplosionType {entry['explosionType']} = wiki branch "
                f"\"{branch['branch']}\", all exact: {branch['allExact']}.")
    lines += ['', '## Existing public ids', '']
    for item in doc['existingIdAudit']:
        lines.append(f"- `{item['id']}` (+{item['offset']}, schema unit {item['schemaUnit']}): native "
            f"{item['nativeUnit']}: {item['nativeMeaning']} -> **{item['verdict']}**.")
    lines += ['', '## Promotion proposal (`hd2.fields.charge.*`)', '']
    lines += [report.markdown_table(['id', 'status', '+off', 'storage', 'unit', 'range', 'note'],
        [[p['id'], p['status'], p['offset'], p['storage'], p['unit'], p['range'], p.get('note', '')]
         for p in doc['promotionProposal']['fields']]), '',
        f"Acknowledgement: {doc['promotionProposal']['acknowledgement']}.",
        f"Write semantics: {doc['promotionProposal']['writeSemantics']}.", '']
    lines += ['## Not promoted', '']
    for item in doc['notPromoted']:
        lines.append(f"- `{item['path']}`: {item['reason']}")
    lines += ['', '## Live tests (strongly differentiated)', '']
    for test in doc['liveTests']:
        lines.append(f"- **{test['id']}** ({test['target']}): {test['writes']} -> {test['expect']}")
    lines += ['', '## Open questions', '']
    lines += [f'- {q}' for q in doc['openQuestions']]
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    doc = build()
    text = json.dumps(doc, indent=2, allow_nan=False, default=report._default) + '\n'
    md = markdown(doc)
    if args.check:
        stale = [str(p) for p, body in ((OUTPUT, text), (MARKDOWN, md))
            if not p.is_file() or p.read_text(encoding='utf-8') != body]
        if stale:
            print('stale:', ', '.join(stale))
            return 1
        print('up to date')
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    MARKDOWN.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding='utf-8')
    MARKDOWN.write_text(md, encoding='utf-8')
    print('wrote', OUTPUT.relative_to(ROOT), 'and', MARKDOWN.relative_to(ROOT))
    print('counts', doc['counts'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
