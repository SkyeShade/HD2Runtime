"""Beam damage per weapon (EXPERIMENTAL multi-weapon beam swap, branch exp/multi-beam): where a beam's damage and armour
penetration come from, what is per weapon, per BeamWeapon record, per BeamType and per DamageInfo row, and which route
gives the AR-23 Liberator, LAS-58 Talon and SMG-32 Reprimand (all three fire BeamWeapon record 23, a copy of the LAS-13
Trident's record 18) their own damage and penetration. Read-only, offline, build F5FEE03DCFDB: the game.dll image of a
retained snapshot (capstone), every retained snapshot, the pinned entity / settings / delta data.

The chain of one beam shot (system S = [game+0x347CED0] = world + 0x2563C48, world = [game+0x3326340]):

  0x83F9D0 beam shot (BeamWeapon component update 0x83E200, reached from the entity component update at 0xAB5EC9)
    0x83FBBA  ebx = [entity +8]: the WEAPON entity id
    0x83FBBF  BeamType = 0x83FD50(manager, entity) = [0x50ECC0(entity) +0]: the weapon's BeamWeapon record (private
              copy first) +0, read at every shot
    0x83FC02  BeamFire 0x13B8410(S, ..., BeamType, entity, ...)
  0x13B8410 BeamFire: takes ring entry E = S+0x170+slot*0x168 (64 slots, write index S+0x16C), zeroes it (0x168 bytes),
            row R = BeamType ? [0x37C8250 + BeamType*8] : default 0x37C81E0, and copies the row INTO THE ENTRY:
              E+0x18 BeamType; E+0x34 = R+0x0C (the DamageInfo id); E+0x1C/+0x20 = R+0x10/+0x14 (falloff start /
              range); E+0x24/+0x28 = R+0x18/+0x1C (DAMAGE multipliers near / far); E+0x2C/+0x30 = R+0x20/+0x24
              (PENETRATION multipliers near / far); E+0x160 = R+0x6C bit 0 (single-application pulse); E+0x161 = 0;
              E+0x110 = 1 (alive); E+0x54 = E+0x68 = the weapon entity; E+0x58 the creditor; E+0x14C..+0x157 = 0
              (no ray query yet)
  0x13BAE20 (from 0x13F73F0 at 0xAB55AF, BEFORE the component update): submits the ray queries of every live entry
            (E+0x154, E+0x14C, E+0x150)
  0x13BB240 (at 0xAB5FCB, after the component update): for an entry with ray results, per hit:
              w from the falloff (E+0x1C, E+0x20; 0 when the range is 0)
              m = (1 - w) x E+0x24 + w x E+0x28        (damage)
              p = (1 - w) x E+0x2C + w x E+0x30        (penetration)
              InitHitInfo 0x12A15E0(..., s) with s+0x24 = E+0x34: event +0x98 = standard x (1 - D) + durable x D of
              DamageInfo [0x37C60C0 + id*8], lanes +0x9C..+0xA8 = the row's four AP values, statuses, ...
              event +0x98 x= m; lanes x= p (not rounded)
              pulse (E+0x160 = 1, the Trident's row 6): kind 3, DamageValues -> builder 0x129CF10:
                damage = round(max(0, A x event +0x98)) x relation x event +0xF8 (1.0); ProduceDamage at once;
                E+0x161 = 1
              continuous: kind 2 per tick (x dt), accumulated in E+0x13C, produced in whole units

So every damage input of a beam shot is the BeamInfo row of its BeamType (per BeamType: shared by every weapon firing
that BeamType, the real Trident included) and the DamageInfo row it names (per id). Nothing on the weapon (record 23
is shared by all three swapped weapons and holds only the BeamType), its WeaponData, its ProjectileWeapon row or its
instance scales a beam hit. But the shot's OWN entry carries copies of the row's damage id and multipliers, written
once at BeamFire and read only by the hit processing: a per-shot, per-weapon (E+0x54 is the weapon entity) lever.

Output: research/beam-damage-per-weapon-F5FEE03DCFDB.json.   py -3 scripts/research_beam_damage.py
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

import capstone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from migration import build_view  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS as CALLDOWN_SNAPSHOTS  # noqa: E402
from research_magazine_attachments import DATALIB, DELTAS_SHA, entity_deltas, sha  # noqa: E402
from scan import tables as scan_tables, xref  # noqa: E402

OUTPUT = ROOT / 'research/beam-damage-per-weapon-F5FEE03DCFDB.json'
SNAPSHOTS = list(CALLDOWN_SNAPSHOTS) + [
    'F5FEE03DCFDB-20261008T162919Z-weapon-roots-scythe-dagger.hd2snap',
    'F5FEE03DCFDB-20261008T163453Z-weapon-roots-defender-etool.hd2snap']

WORLD_GLOBAL = 0x3326340
BEAM_SYSTEM_GLOBAL = 0x347CED0
BEAM_SYSTEM_IN_WORLD = 0x2563C48
BEAM_TABLE, BEAM_TABLE_SLOTS, BEAM_DEFAULT_ROW, BEAM_STRIDE = 0x37C8250, 31, 0x37C81E0, 0x70
DAMAGE_TABLE, DAMAGE_TABLE_SLOTS, DAMAGE_DEFAULT_ROW, DAMAGE_STRIDE = 0x37C60C0, 650, 0x37C7510, 0x4C
RING = {'indices': {'read': 0x168, 'write': 0x16C}, 'base': 0x170, 'stride': 0x168, 'slots': 64}
ENTRY = {
    'beamType': 0x18, 'falloffStart': 0x1C, 'falloffRange': 0x20, 'damageNear': 0x24, 'damageFar': 0x28,
    'penetrationNear': 0x2C, 'penetrationFar': 0x30, 'damageInfo': 0x34, 'weaponEntity': 0x54, 'creditor': 0x58,
    'entity': 0x68, 'alive': 0x110, 'rayQueries': 0x14C, 'rayQuery': 0x154, 'pulse': 0x160, 'applied': 0x161}
ROW = {'damageInfo': 0x0C, 'falloffStart': 0x10, 'falloffRange': 0x14, 'damageNear': 0x18, 'damageFar': 0x1C,
    'penetrationNear': 0x20, 'penetrationFar': 0x24, 'pulseFlag': 0x6C}
TRIDENT_BEAM, TRIDENT_DAMAGE = 6, 508
WEAPONS = {'liberator': 0x968211C0033DCE64, 'talon': 0x416D053372C4E433, 'reprimand': 0x94BD931B5FB4EE95}
TRIDENT = 0x3C86E871923F3970

# (rva, asm, rip target or None, role)
PROOFS = {
    'shot': [
        (0x5737B1, 'call 0x83e200', None, 'the entity component update 0x571250 runs the BeamWeapon update 0x83E200'),
        (0x83F0D3, 'call 0x83f9d0', None, 'the BeamWeapon update runs the beam shot 0x83F9D0'),
        (0x83FBBA, 'mov ebx, dword ptr [rax + 8]', None, 'the weapon entity id ([entity +8]) ...'),
        (0x83FBBF, 'call 0x83fd50', None, 'BeamType of that weapon entity (0x83FD50) ...'),
        (0x83FDE3, 'call 0x50ecc0', None, '... = its BeamWeapon record (resolver by entity: private copy first) ...'),
        (0x83FDE8, 'mov eax, dword ptr [rax]', None, '... +0, read at every shot'),
        (0x83FBEA, 'mov rcx, qword ptr [rip + {rip}]', BEAM_SYSTEM_GLOBAL, 'the beam system S'),
        (0x83FBFE, 'mov dword ptr [rsp + 0x20], ebx', None, 'argument 5 = the weapon entity'),
        (0x83FC02, 'call 0x13b8410', None, 'BeamFire: one ring entry per shot'),
    ],
    'beamFire': [
        (0x13B8470, 'mov rsi, qword ptr [rip + {rip}]', BEAM_SYSTEM_GLOBAL, 'S'),
        (0x13B8488, 'mov edi, dword ptr [rsi + 0x16c]', None, 'the ring write index S+0x16C ...'),
        (0x13B934F, 'lea r14, [rsi + 0x170]', None, '... entry E = S + 0x170 ...'),
        (0x13B9356, 'imul rcx, rax, 0x168', None, '... + slot x 0x168'),
        (0x13B935F, 'mov r8d, 0x168', None, 'E zeroed (0x168 bytes) ...'),
        (0x13B936B, 'call 0x208aaa0', None, '... memset'),
        (0x13B957D, 'test ebx, ebx', None, 'BeamType 0 -> ...'),
        (0x13B9581, 'lea r15, [rip + {rip}]', BEAM_DEFAULT_ROW, '... the default BeamInfo row; else ...'),
        (0x13B958A, 'lea r15, [rip + {rip}]', BEAM_TABLE, '... the BeamInfo pointer table ...'),
        (0x13B9591, 'mov r15, qword ptr [r15 + rbx*8]', None, '... [table + BeamType x 8] (no bound check)'),
        (0x13B9595, 'mov dword ptr [r14 + 0x18], ebx', None, 'E+0x18 = BeamType'),
        (0x13B95A1, 'mov qword ptr [r14 + 0x14c], r12', None, 'E+0x14C/+0x150 = 0 (no ray query yet)'),
        (0x13B95A8, 'mov dword ptr [r14 + 0x154], r12d', None, 'E+0x154 = 0 (no ray query yet)'),
        (0x13B9631, 'mov ecx, dword ptr [rbp + 0x110]', None, 'argument 5 (the weapon entity) ...'),
        (0x13B9637, 'mov dword ptr [r14 + 0x68], ecx', None, '... E+0x68'),
        (0x13B963F, 'mov byte ptr [r14 + 0x110], 1', None, 'E+0x110 = 1 (alive)'),
        (0x13B96A5, 'movzx eax, byte ptr [r15 + 0x6c]', None, 'row +0x6C ...'),
        (0x13B96AA, 'and al, 1', None, '... bit 0 ...'),
        (0x13B96AC, 'mov byte ptr [r14 + 0x161], r12b', None, 'E+0x161 = 0 (not yet applied)'),
        (0x13B96B3, 'mov byte ptr [r14 + 0x160], al', None, '... E+0x160 (single application: the pulse path)'),
        (0x13B96BE, 'mov eax, dword ptr [r15 + 0xc]', None, 'row +0x0C (DamageInfoType) ...'),
        (0x13B96C2, 'mov dword ptr [r14 + 0x34], eax', None, '... E+0x34: the shot\'s own DamageInfo id'),
        (0x13B96C6, 'mov eax, dword ptr [r15 + 0x10]', None, 'row +0x10 ...'),
        (0x13B96CA, 'mov dword ptr [r14 + 0x1c], eax', None, '... E+0x1C (falloff start)'),
        (0x13B96CE, 'mov eax, dword ptr [r15 + 0x14]', None, 'row +0x14 ...'),
        (0x13B96D2, 'mov dword ptr [r14 + 0x20], eax', None, '... E+0x20 (falloff range)'),
        (0x13B96D6, 'mov eax, dword ptr [r15 + 0x18]', None, 'row +0x18 ...'),
        (0x13B96DA, 'mov dword ptr [r14 + 0x24], eax', None, '... E+0x24 (damage multiplier, near)'),
        (0x13B96DE, 'mov eax, dword ptr [r15 + 0x1c]', None, 'row +0x1C ...'),
        (0x13B96E2, 'mov dword ptr [r14 + 0x28], eax', None, '... E+0x28 (damage multiplier, far)'),
        (0x13B96E6, 'mov eax, dword ptr [r15 + 0x20]', None, 'row +0x20 ...'),
        (0x13B96EA, 'mov dword ptr [r14 + 0x2c], eax', None, '... E+0x2C (penetration multiplier, near)'),
        (0x13B96EE, 'mov eax, dword ptr [r15 + 0x24]', None, 'row +0x24 ...'),
        (0x13B96F2, 'mov dword ptr [r14 + 0x30], eax', None, '... E+0x30 (penetration multiplier, far)'),
        (0x13B9867, 'mov eax, dword ptr [rbp + 0x118]', None, 'argument 6 ...'),
        (0x13B986D, 'mov dword ptr [r14 + 0x58], eax', None, '... E+0x58 (the creditor, 0x12A1210 r9)'),
        (0x13B987C, 'mov dword ptr [r14 + 0x54], ecx', None, 'E+0x54 = the weapon entity (0x12A1210 r8: the source)'),
    ],
    'raySubmit': [
        (0xAB5025, 'mov r14, qword ptr [rip + {rip}]', WORLD_GLOBAL, 'the world'),
        (0xAB55A8, 'lea rcx, [r14 + 0x1024220]', None, 'the query phase ...'),
        (0xAB55AF, 'call 0x13f73f0', None, '... 0x13F73F0, BEFORE the component update'),
        (0x13F764D, 'lea rcx, [rdi + 0x153fa28]', None, 'S (= world + 0x2563C48) ...'),
        (0x13F7654, 'call 0x13bae20', None, '... beam ray submission 0x13BAE20 (its only caller)'),
        (0x13BAF92, 'mov dword ptr [rdi + rbx + 0x2c4], eax', None, 'E+0x154: the ray query'),
        (0x13BB0EF, 'mov dword ptr [rdi + rbx + 0x2bc], eax', None, 'E+0x14C: a ray query'),
        (0x13BB1D5, 'mov dword ptr [rdi + rbx + 0x2c0], eax', None, 'E+0x150: a ray query'),
        (0xAB5EC5, 'lea rcx, [rsi + 0x40]', None, 'the entity component update ...'),
        (0xAB5EC9, 'call 0x571250', None, '... 0x571250 (weapons fire here: BeamFire, SpawnProjectile)'),
        (0xAB5FC4, 'lea rcx, [r14 + 0x2563c48]', None, 'S ...'),
        (0xAB5FCB, 'call 0x13bb240', None, '... beam hit processing 0x13BB240, AFTER the component update'),
        (0xAB5FE8, 'lea rcx, [r14 + 0x44f7e30]', None, 'the projectile system ...'),
        (0xAB5FEF, 'call 0x13ac1f0', None, '... projectile hit processing (the same phase)'),
    ],
    'hitProcessing': [
        (0x13BB282, 'mov eax, dword ptr [rcx + 0x168]', None, 'from the read index ...'),
        (0x13BB291, 'cmp eax, dword ptr [rcx + 0x16c]', None, '... to the write index'),
        (0x13BB350, 'imul r14, rax, 0x168', None, 'entry slot x 0x168'),
        (0x13BB361, 'cmp byte ptr [r14 + rsi + 0x280], 0', None, 'E+0x110 alive'),
        (0x13BB2A5, 'lea r8, [rip + {rip}]', BEAM_DEFAULT_ROW, 'the default BeamInfo row'),
        (0x13BB3A0, 'mov eax, dword ptr [r14 + rsi + 0x188]', None, 'E+0x18 BeamType ...'),
        (0x13BB3B2, 'mov rax, qword ptr [rdx + rax*8 + 0x37c8250]', None, '... its BeamInfo row (effects, flags)'),
        (0x13BB3EB, 'mov eax, dword ptr [r14 + rsi + 0x2c4]', None, 'E+0x154 ray results (0: no hits)'),
        (0x13BB4A2, 'mov eax, dword ptr [r14 + rsi + 0x2bc]', None, 'E+0x14C ray results (0: no hits)'),
        (0x13BB4D9, 'mov eax, dword ptr [r14 + rsi + 0x2c0]', None, 'E+0x150 ray results (0: no hits)'),
        (0x13BB5A0, 'cmp byte ptr [r14 + rsi + 0x2d1], 0', None, 'E+0x161 set: the hit loop is skipped'),
        (0x13BB6D6, 'movss xmm2, dword ptr [r14 + rsi + 0x190]', None, 'E+0x20 falloff range (<= 0: w = 0)'),
        (0x13BB6F4, 'subss xmm1, dword ptr [r14 + rsi + 0x18c]', None, '|hit distance - E+0x1C|'),
        (0x13BBAC5, 'mulss xmm1, dword ptr [r14 + rsi + 0x1a0]', None, 'w x E+0x30 ...'),
        (0x13BBACF, 'mulss xmm0, dword ptr [r14 + rsi + 0x198]', None, 'w x E+0x28 ...'),
        (0x13BBADD, 'mulss xmm6, dword ptr [r14 + rsi + 0x19c]', None, '(1 - w) x E+0x2C ...'),
        (0x13BBAE7, 'mulss xmm8, dword ptr [r14 + rsi + 0x194]', None, '(1 - w) x E+0x24 ...'),
        (0x13BBAF1, 'addss xmm6, xmm1', None, '... p = the penetration multiplier'),
        (0x13BBAF5, 'addss xmm8, xmm0', None, '... m = the damage multiplier'),
        (0x13BBB43, 'mov eax, dword ptr [r14 + rsi + 0x1a4]', None, 'E+0x34 ...'),
        (0x13BBB4B, 'mov dword ptr [rbp + 0x44c], eax', None, '... s+0x24 (s = rbp+0x428): the DamageInfo id'),
        (0x13BBBE9, 'cmp byte ptr [r14 + rsi + 0x2d0], al', None, 'E+0x160: the pulse path (kind 3) or the tick'),
        (0x13BBC0C, 'mov r8d, 3', None, 'kind 3 (single application)'),
        (0x13BBCC5, 'call 0x12a15e0', None, 'InitHitInfo (pulse): event rbp+0x650 from DamageInfo [s+0x24]'),
        (0x13BBCCA, 'movups xmm1, xmmword ptr [rbp + 0x6ec]', None, 'event lanes +0x9C..+0xA8 ...'),
        (0x13BBCD8, 'mov dword ptr [rbp + 0x748], 0x3f800000', None, 'event +0xF8 = 1.0 (pulse)'),
        (0x13BBCE2, 'movss xmm0, dword ptr [rbp + 0x6e8]', None, 'event +0x98 (the standard / durable blend) ...'),
        (0x13BBCF1, 'mulps xmm1, xmm6', None, '... lanes x p'),
        (0x13BBD03, 'mulss xmm0, xmm8', None, '... event +0x98 x m'),
        (0x13BBD1C, 'movups xmmword ptr [rbp + 0x6ec], xmm1', None, 'lanes stored'),
        (0x13BBD29, 'movss dword ptr [rbp + 0x6e8], xmm0', None, 'damage stored'),
        (0x13BBDAF, 'call 0x129dc30', None, 'DamageValues'),
        (0x13BBDEA, 'call 0x129dd30', None, 'ProduceDamage, at once'),
        (0x13BBDEF, 'mov byte ptr [r14 + rsi + 0x2d1], 1', None, 'E+0x161 = 1: once per pulse'),
        (0x13BB831, 'mov eax, dword ptr [r14 + rsi + 0x1a4]', None, 'E+0x34 -> s+0x24 (the accumulated tick carrier)'),
        (0x13BBED3, 'call 0x12a15e0', None, 'InitHitInfo (continuous tick, kind 2)'),
        (0x13BBF11, 'mulss xmm0, xmm8', None, 'tick damage x m'),
        (0x13BBEFF, 'mulps xmm1, xmm6', None, 'tick lanes x p'),
        (0x13BC114, 'mov eax, dword ptr [r14 + rsi + 0x1a4]', None, 'E+0x34 -> s+0x24 (another tick event)'),
        (0x13BC24B, 'call 0x12a15e0', None, 'InitHitInfo (tick, kind 2)'),
        (0x13BC26E, 'mulss xmm0, xmm8', None, 'tick damage x m'),
        (0x13BC27D, 'mulps xmm1, xmm6', None, 'tick lanes x p'),
    ],
    'damageRow': [
        (0x12A1C29, 'mov eax, dword ptr [rbx + 0x24]', None, 'InitHitInfo: s+0x24, the DamageInfo id ...'),
        (0x12A23FD, 'lea rcx, [rip + {rip}]', DAMAGE_TABLE, '... row = [0x37C60C0 + id x 8]'),
        (0x12A249D, 'movss dword ptr [r14 + 0x98], xmm3', None, 'event +0x98 = standard x (1 - D) + durable x D'),
        (0x129DC7E, 'mov rdx, rbx', None, 'DamageValues kind 3 ...'),
        (0x129DC81, 'call 0x129cf10', None, '... builder 0x129CF10'),
        (0x129D029, 'mulss xmm3, dword ptr [rbx + 0x98]', None,
            'A (1 / 0.65 / 0 by the penetration lane) x event +0x98'),
        (0x129D049, 'movss xmm2, dword ptr [rbx + 0xf8]', None, '... x event +0xF8'),
    ],
    'tables': [
        (0x11D7E5B, 'lea r12, [rip + {rip}]', BEAM_TABLE, 'BeamInfo loader: the pointer table ...'),
        (0x11D7E7E, 'mov r8d, 0xf8', None, '... 0xF8 bytes = 31 slots (BeamType 0..30) ...'),
        (0x11D7F7F, 'mov qword ptr [r12 + rax*8], rdx', None, '... slot [row +0] = the row'),
        (0x11F8CBB, 'lea r12, [rip + {rip}]', DAMAGE_TABLE, 'DamageInfo loader: the pointer table ...'),
        (0x11F8CDE, 'mov r8d, 0x1450', None, '... 0x1450 bytes = 650 slots (id 0..649) ...'),
        (0x11F8DDF, 'mov qword ptr [r12 + rax*8], rdx', None, '... slot [row +0] = the row'),
        (0x11F8EAE, 'lea rcx, [rip + {rip}]', DAMAGE_TABLE, 'GetDamageInfo: [table + id x 8] ...'),
        (0x11F8EB5, 'mov rax, qword ptr [rcx + rax*8]', None, '... no bound check'),
    ],
}
KIND_TABLE = 0x129DD08          # DamageValues jump table: kind 3 -> 0x129DC7E (call 0x129CF10)
WORLD_UPDATE, WORLD_UPDATE_JUMP_TABLE = 0xAB5000, (0xAB60BA, 0xAB7664, 6)


def prove_order(image) -> dict:
    """In the world update 0xAB5000: the component update (0xAB5EC9) is followed by the beam hit processing (0xAB5FCB)
    and never by the ray submission (0xAB55AF) in the same call. Jumps followed (the one indirect jump is the
    0xAB7664 table, all of whose targets are forward), calls stepped over."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    jump_at, table, count = WORLD_UPDATE_JUMP_TABLE
    targets = [struct.unpack_from('<I', image.data, table + 4 * k)[0] for k in range(count)]
    if any(t <= jump_at for t in targets):
        raise ValueError('a world update jump table target is not forward: %r' % targets)

    def reach(start, stop=()):
        seen, work = set(), [start]
        while work:
            a = work.pop()
            while WORLD_UPDATE <= a < 0xAB7664 and a not in seen:
                seen.add(a)
                if a in stop:
                    break
                ins = next(md.disasm(image.data[a:a + 16], a), None)
                if ins is None:
                    break
                m = ins.mnemonic
                if a == jump_at:
                    work.extend(targets)
                    break
                if m.startswith('j'):
                    if not ins.op_str.startswith('0x'):
                        raise ValueError('unexpected indirect jump at %X' % a)
                    work.append(int(ins.op_str, 16))
                    if m == 'jmp':
                        break
                if m in ('ret', 'int3'):
                    break
                a += ins.size
        return seen
    after_fire = reach(0xAB5EC9)
    from_entry = reach(WORLD_UPDATE)
    result = {'fireReachesHitProcessing': 0xAB5FCB in after_fire,
        'fireReachesRaySubmission': 0xAB55AF in after_fire,
        'entryReachesAll': all(a in from_entry for a in (0xAB55AF, 0xAB5EC9, 0xAB5FCB)),
        'jumpTableTargets': ['0x%X' % t for t in targets]}
    if not result['fireReachesHitProcessing'] or result['fireReachesRaySubmission'] or not result['entryReachesAll']:
        raise ValueError('world update order changed: %r' % result)
    return result


def callers(image, target) -> list[int]:
    out = []
    for rva, size, mnemonic, op in image.sweep():
        if mnemonic in ('call', 'jmp') and op == '0x%x' % target:
            out.append(rva)
    return out


def entry_census(image) -> dict:
    """Who reads and writes a shot's multipliers and damage id: every function that takes the beam system (a rip
    reference to S, or S from the world: world + 0x2563C48, or the query object + 0x153FA28), the two that receive it
    as rcx (hit processing, ray submission) and the direct callees of the hit processing, BeamFire and the ray
    submission. In those, every memory operand at an entry field's in-system displacement ([slot + S + 0x170 + field],
    unscaled) and, in BeamFire (the only function holding an entry pointer), every [entry + field] operand."""
    code = xref.CodeImage(image.data)
    fields = {ENTRY[k]: k for k in ('damageNear', 'damageFar', 'penetrationNear', 'penetrationFar', 'damageInfo')}
    in_system = {RING['base'] + d: k for d, k in fields.items()}
    roots = set()
    for rva, size, mnemonic, op in image.sweep():
        on_s = 'rip' in op and base.rip_of(rva, size, op) == BEAM_SYSTEM_GLOBAL
        if on_s or '+ 0x2563c48]' in op or '+ 0x153fa28]' in op:
            roots.add(code.root(rva) or rva)
    roots |= {0x13BB240, 0x13BAE20}
    for f in (0x13BB240, 0x13B8410, 0x13BAE20):
        roots |= set(code.calls_in(f))
    found = []
    for f in sorted(roots):
        for ins in code.function_insns(f):
            for k, op in enumerate(ins.operands):
                if op.type != capstone.x86.X86_OP_MEM or op.mem.base == capstone.x86.X86_REG_RIP:
                    continue
                unscaled_pair = op.mem.index != 0 and op.mem.scale == 1
                hit = (unscaled_pair and op.mem.disp in in_system) or (
                    f == 0x13B8410 and op.mem.index == 0 and op.mem.disp in fields
                    and ins.reg_name(op.mem.base) == 'r14')
                if hit:
                    name = in_system.get(op.mem.disp) if unscaled_pair else fields[op.mem.disp]
                    found.append({'function': '0x%X' % f, 'rva': '0x%X' % ins.address,
                        'asm': ins.mnemonic + ' ' + ins.op_str, 'field': name,
                        'write': k == 0 and len(ins.operands) > 1 and not ins.mnemonic.startswith(('cmp', 'test'))})
    return {'functions': ['0x%X' % f for f in sorted(roots)], 'accesses': found}


def typed_reference_census() -> dict:
    """References to every DamageInfoType id and BeamType from typed members of every component record, settings
    row (not its own key) and entity delta. Code immediates are NOT covered (ids can be hard-coded)."""
    t = scan_tables.pinned()
    view = build_view.from_snapshot(build_profile.SNAPSHOT)
    want = {'DamageInfoType': {}, 'BeamType': {}}

    def hit(enum, value, where):
        want[enum].setdefault(value, []).append(where)
    by_index = t._index_types()
    leaves_of = {}
    for comp in t.components():
        leaves = [m for m in comp.members() if m.type_name in want and m.size == 4 and m.atom == 'POD']
        leaves_of[comp.type_hash] = (comp, leaves)
        if not leaves:
            continue
        for record in range(comp.count):
            raw = comp.raw(record)
            for m in leaves:
                hit(m.type_name, struct.unpack_from('<I', raw, m.offset)[0], 'component %s record %d %s' % (
                    comp.name, record, m.path))
    for kind, table in view.settings.items():
        for group in table.groups.values():
            leaves = [m for m in t.flatten(group.layout.type_hash) if m.type_name in want and m.size == 4
                and m.atom == 'POD' and m.offset != 0]
            for row, rtype, raw in group.rows:
                for m in leaves:
                    hit(m.type_name, struct.unpack_from('<I', raw, m.offset)[0], 'settings %s row %d (type %d) %s' % (
                        kind, row, rtype, m.path))
    deltas_file = (DATALIB / 'generated_entity_deltas.dl_bin').read_bytes()
    if sha(deltas_file) != DELTAS_SHA:
        raise ValueError('pinned entity delta table changed')
    deltas, _ = entity_deltas(deltas_file)
    for add_path, delta in deltas.items():
        for e in delta['entries']:
            comp, leaves = leaves_of.get(by_index.get(e['component']), (None, []))
            for m in leaves:
                if e['offset'] <= m.offset and m.offset + 4 <= e['offset'] + e['size']:
                    value = struct.unpack_from('<I', e['bytes'], m.offset - e['offset'])[0]
                    hit(m.type_name, value, 'delta 0x%016X %s %s' % (add_path, comp.name, m.path))
    damage_ids = sorted(view.settings['damage'].by_type)
    beam_types = sorted(view.settings['beam'].by_type)
    unref_damage = [i for i in damage_ids if not want['DamageInfoType'].get(i)]
    unref_beam = [i for i in beam_types if not want['BeamType'].get(i)]
    return {'damageRows': len(damage_ids), 'damageIdRange': [damage_ids[0], damage_ids[-1]],
        'beamRows': len(beam_types), 'beamTypeRange': [beam_types[0], beam_types[-1]],
        'unreferencedDamageIds': unref_damage, 'unreferencedBeamTypes': unref_beam,
        'tridentBeamTypeReferences': want['BeamType'].get(TRIDENT_BEAM, []),
        'tridentDamageReferences': want['DamageInfoType'].get(TRIDENT_DAMAGE, []),
        'covers': 'typed members of every component record, every settings row (not its own key) and every entity '
            'delta; NOT code immediates, NOT Lua / script data'}


def row_values(raw: bytes) -> dict:
    return {'damageInfo': struct.unpack_from('<I', raw, ROW['damageInfo'])[0],
        'falloff': [struct.unpack_from('<f', raw, ROW['falloffStart'])[0],
            struct.unpack_from('<f', raw, ROW['falloffRange'])[0]],
        'damageMultipliers': list(struct.unpack_from('<2f', raw, ROW['damageNear'])),
        'penetrationMultipliers': list(struct.unpack_from('<2f', raw, ROW['penetrationNear'])),
        'pulseFlag': raw[ROW['pulseFlag']] & 1, 'bytes': raw.hex()}


def damage_values(raw: bytes) -> dict:
    v = struct.unpack_from('<I2i4I3IIi', raw, 0)
    return {'id': v[0], 'standard': v[1], 'durable': v[2], 'armorPenetration': list(v[3:7]),
        'demolition': v[7], 'stagger': v[8], 'push': v[9], 'element': v[10],
        'statuses': [list(struct.unpack_from('<If', raw, 44 + 8 * k)) for k in range(4)], 'bytes': raw.hex()}


def observe(name: str) -> dict:
    mem = base.Mem(name)
    try:
        world = mem.ptr(mem.game + WORLD_GLOBAL)
        system = mem.ptr(mem.game + BEAM_SYSTEM_GLOBAL)
        beam = mem.read(mem.game + BEAM_TABLE, BEAM_TABLE_SLOTS * 8)
        dmg = mem.read(mem.game + DAMAGE_TABLE, DAMAGE_TABLE_SLOTS * 8)
        beam_ptrs = struct.unpack('<%dQ' % BEAM_TABLE_SLOTS, beam)
        dmg_ptrs = struct.unpack('<%dQ' % DAMAGE_TABLE_SLOTS, dmg)
        beam_keys = [None if not p else struct.unpack('<I', mem.read(p, 4))[0] for p in beam_ptrs]
        dmg_keys = [None if not p else struct.unpack('<I', mem.read(p, 4))[0] for p in dmg_ptrs]
        ring = mem.read(system + RING['base'], RING['slots'] * RING['stride']) if system else None
        alive = [k for k in range(RING['slots']) if ring and ring[k * RING['stride'] + ENTRY['alive']]]
        region = mem.s.region(system + RING['base']) if system else None
        return {'snapshot': name, 'systemIsWorldPlusOffset': system == world + BEAM_SYSTEM_IN_WORLD,
            'ringIndices': list(struct.unpack('<2I', mem.read(system + 0x168, 8))) if system else None,
            'aliveEntries': len(alive),
            'ringProtect': None if region is None else '0x%X' % region['protect'],
            'beamTableNullSlots': [k for k, p in enumerate(beam_ptrs) if not p],
            'beamTableKeysMatchSlots': all(k is None or k == i for i, k in enumerate(beam_keys)),
            'damageTableNullSlots': [k for k, p in enumerate(dmg_ptrs) if not p],
            'damageTableKeysMatchSlots': all(k is None or k == i for i, k in enumerate(dmg_keys)),
            'afterBeamTable': mem.read(mem.game + BEAM_TABLE + BEAM_TABLE_SLOTS * 8, 8).hex(),
            'afterDamageTableIsDefaultRow': mem.game + DAMAGE_TABLE + DAMAGE_TABLE_SLOTS * 8
                == mem.game + DAMAGE_DEFAULT_ROW,
            'tridentBeamRow': row_values(mem.read(beam_ptrs[TRIDENT_BEAM], BEAM_STRIDE)),
            'tridentDamageRow': damage_values(mem.read(dmg_ptrs[TRIDENT_DAMAGE], DAMAGE_STRIDE))}
    finally:
        mem.close()


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    kinds = list(struct.unpack_from('<7I', data, KIND_TABLE))
    if kinds[3] != 0x129DC7E:
        raise ValueError('DamageValues kind 3 no longer goes to the 0x129CF10 call: %r' % kinds)
    constants = [{'rva': KIND_TABLE, 'bytes': data[KIND_TABLE:KIND_TABLE + 28].hex(),
        'value': ['0x%X' % k for k in kinds], 'role': 'DamageValues jump table by event kind (3 -> call 0x129CF10)'}]
    order = prove_order(image)
    sole = {'0x13BAE20': ['0x%X' % c for c in callers(image, 0x13BAE20)],
        '0x13F73F0': ['0x%X' % c for c in callers(image, 0x13F73F0)],
        '0x13B8410': ['0x%X' % c for c in callers(image, 0x13B8410)]}
    if sole['0x13BAE20'] != ['0x13F7654'] or sole['0x13F73F0'] != ['0xAB55AF']:
        raise ValueError('the beam ray submission has another caller: %r' % sole)
    census = entry_census(image)
    writers = sorted(a['rva'] for a in census['accesses'] if a['write'])
    readers = sorted(a['rva'] for a in census['accesses'] if not a['write'])
    if writers != ['0x13B96C2', '0x13B96DA', '0x13B96E2', '0x13B96EA', '0x13B96F2'] or readers != [
            '0x13BB831', '0x13BBAC5', '0x13BBACF', '0x13BBADD', '0x13BBAE7', '0x13BBB43', '0x13BC114']:
        raise ValueError('another access to the shot\'s multipliers / damage id: %r' % census['accesses'])
    relocation = {name: base.verify_pins_live(name, pins + constants, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    observations = [observe(name) for name in SNAPSHOTS]
    for o in observations:
        if not (o['systemIsWorldPlusOffset'] and o['beamTableNullSlots'] == [0] and o['damageTableNullSlots'] == [0]
                and o['beamTableKeysMatchSlots'] and o['damageTableKeysMatchSlots']):
            raise ValueError('snapshot %s: unexpected tables or beam system' % o['snapshot'])
    trident = {json.dumps([o['tridentBeamRow'], o['tridentDamageRow']], sort_keys=True) for o in observations}
    if len(trident) != 1:
        raise ValueError('the Trident beam / damage rows differ between snapshots')
    references = typed_reference_census()
    view = build_view.from_snapshot(build_profile.SNAPSHOT)
    donors = {}
    for label, beam_type in (('LAS-13 Trident', 6), ('LAS-5 Scythe', 8), ('LAS-7 Dagger', 11),
            ('LAS-98 Laser Cannon', 1), ('40-K Meltagun', 18)):
        brow = view.settings['beam'].row_for_type(beam_type)[0][1]
        drow = view.settings['damage'].row_for_type(struct.unpack_from('<I', brow, 12)[0])[0][1]
        donors[label] = {'beamType': beam_type, 'beam': row_values(brow), 'damage': damage_values(drow)}
    report = {
        'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'gameDllSha256': base.PROFILE_DLL_SHA,
        'question': 'Can the Liberator, Talon and Reprimand Trident beams (one shared BeamWeapon record 23) each have '
            'their own damage and armour penetration, independent of each other and of the real LAS-13 Trident?',
        'chain': __doc__.split('The chain of one beam shot')[1].split('Output:')[0].strip(),
        'ring': {**RING, 'system': {'global': '0x%X' % BEAM_SYSTEM_GLOBAL,
            'world': '0x%X' % WORLD_GLOBAL, 'inWorld': '0x%X' % BEAM_SYSTEM_IN_WORLD}, 'entry': ENTRY},
        'beamInfoRow': {'table': '0x%X' % BEAM_TABLE, 'slots': BEAM_TABLE_SLOTS,
            'defaultRow': '0x%X' % BEAM_DEFAULT_ROW,
            'stride': BEAM_STRIDE, 'members': ROW},
        'damageInfoRow': {'table': '0x%X' % DAMAGE_TABLE, 'slots': DAMAGE_TABLE_SLOTS,
            'defaultRow': '0x%X' % DAMAGE_DEFAULT_ROW, 'stride': DAMAGE_STRIDE},
        'proofs': proofs, 'constants': constants, 'order': order, 'soleCallers': sole, 'entryCensus': census,
        'pinnedBytesMismatchPerSnapshot': relocation, 'observations': observations,
        'typedReferences': references, 'donors': donors,
        'perLevel': {
            'perShot': 'ring entry E: E+0x34 DamageInfo id, E+0x24/+0x28 damage multipliers, E+0x2C/+0x30 penetration '
                'multipliers, E+0x1C/+0x20 falloff; E+0x54 the weapon entity. Copied at BeamFire, read only by '
                '0x13BB240 (entryCensus).',
            'perRecord': 'BeamWeapon record +0 (BeamType), read at every shot by 0x83FD50. Record 23 is shared by the '
                'three swapped weapons: one BeamType for all three.',
            'perBeamType': 'BeamInfo row (damage id +0x0C, falloff +0x10/+0x14, multipliers +0x18..+0x24, pulse flag '
                '+0x6C): shared with every weapon firing that BeamType (row 6: the real LAS-13 Trident).',
            'perDamageRow': 'DamageInfo row (standard, durable, four AP lanes, +0x1C/+0x20/+0x24, element, statuses): '
                'shared with every BeamInfo / projectile / explosion naming the id (508: BeamInfo row 6 only).',
            'notInvolved': 'WeaponData, the kept ProjectileWeapon row, the BeamWeapon instance (0x70 bytes, no record '
                'pointer), the wielder: BeamFire copies nothing else that scales a hit (its other arguments are the '
                'entity, the creditor, the ignore list and timing).'},
        'options': {
            'a_perWeaponMember': 'NO data member: nothing on the weapon scales a beam hit. YES per shot: the '
                'shot\'s own entry multipliers and damage id, keyed by the weapon entity (E+0x54). Written by the '
                'Runtime between BeamFire (component update, 0xAB5EC9) and the shot\'s first ray results (submitted '
                'at the next world update\'s 0xAB55AF, processed at its 0xAB5FCB): the window the live-proven '
                'per-shot projectile writes use (0.00 m travelled: projectiles follow the same submit / fire / '
                'process order).',
            'b_separateRecords': 'Needs records 24+ in a Runtime-owned relocated BeamWeapon table (multi-beam research '
                'section 6) AND a distinct BeamType per weapon AND a distinct DamageInfo row per weapon: every '
                'BeamType slot 1..30 and every DamageInfo slot 1..649 is taken (observations), so (b) still needs '
                '(c).',
            'c_spareRows': 'Borrowable only: %d DamageInfo ids and %d BeamTypes have no typed reference, but code '
                'immediates are not covered and a borrowed vanilla row is against the hybrid-row rule (spare twins are '
                'an interim, build-specific exception).' % (len(references['unreferencedDamageIds']),
                    len(references['unreferencedBeamTypes'])),
            'd_extension': 'IMPOSSIBLE without code changes: both tables are fixed arrays in game.dll .data indexed '
                'with no bound (BeamInfo 31 slots, DamageInfo 650 slots, all used); id 650 reads the default damage '
                'row\'s first 8 bytes as a pointer, BeamType 31 reads a zero. A Runtime-owned row needs a slot.'},
        'unproven': [
            'Live: that a Lua update runs between BeamFire and the next world update for beams (the projectile '
            'evidence and the shared submit / fire / process order make it STRONG, not proven); the module logs the '
            'entry state (ray query 0, not applied) of every write.',
            'Live: the damage of a modified pulse on a target (the static chain is complete to ProduceDamage).',
            'The protected sections (.vm_sec, .winlice) cannot be scanned for entry accesses.',
            'Multiplayer: each machine runs its own beam system from its own weapon fire; which machine\'s hit decides '
            'enemy damage is not established (the experiment is solo only).'],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'pins': len(pins), 'constants': len(constants), 'order': order, 'soleCallers': sole,
        'censusWriters': writers, 'censusReaders': readers, 'censusFunctions': len(census['functions']),
        'unreferencedDamageIds': len(references['unreferencedDamageIds']),
        'unreferencedBeamTypes': references['unreferencedBeamTypes'],
        'tridentBeamTypeReferences': references['tridentBeamTypeReferences'],
        'tridentDamageReferences': references['tridentDamageReferences']}, indent=1))


if __name__ == '__main__':
    main()
