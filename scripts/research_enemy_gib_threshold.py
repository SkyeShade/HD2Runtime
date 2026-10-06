"""What makes an enemy burst into gibs ("splootch") on a big hit. Read-only research; nothing writes.

Re-derives, from the pinned datalibrary, the reference snapshot's unpacked game.dll image and the three retained
mission snapshots:

* The native decision, pinned as exact decoded instructions at exact RVAs:
    - HealthManager::ApplyDamage (0x9235F0) runs the gore evaluator only for a hit that killed the entity or one of
      its damage zones, never for Drown, and hands it the hit's final damage (after armor, zone multiplier, element
      and relation multipliers, child-zone split and the zone health cap) and the hit's push force;
    - the gore evaluator (0x9057D0) reads the victim's GoreComponent definition straight from the shared loaded
      GoreComponentData table, picks the gore group that owns the hit actor (or the class's whole-body group when
      no group owns it, when there is no actor, or when Electricity killed it), doubles the damage for Electricity,
      and destroys the group when damage >= group threshold (a negative threshold disables it). On the whole-body
      group that destruction is the splootch.
* The layout of GoreComponentData / GoreComponent / GoreGroupInfo (type library storage and hidden-name lengths), and
  every HealthComponent member that was a candidate, with whether the decision path reads it.
* Every enemy and structure class (research/enemy-authoring-F5FEE03DCFDB.json) with its gore anatomy: whole-body
  group and threshold, limb group thresholds, impulse scales, ownership, plus its health for ratio checks.
* Snapshot evidence: the loaded GoreComponentData table in three mission snapshots equals the datalibrary bytes, and
  the live gore manager's instances (which classes carried gore state in the mission).

Labels: CONFIRMED = proven by pinned code and data offline (no live gameplay observation); STRONG = code-backed with
one inferential step; PLAUSIBLE = consistent but not proven; UNKNOWN. Requires the research-only packages capstone.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

try:
    import capstone
    from capstone import x86
except ImportError as error:  # research dependency only
    raise SystemExit('research_enemy_gib_threshold requires capstone: ' + str(error))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import snapshot_image  # noqa: E402
from migration import build_view  # noqa: E402

HELPERS = ROOT.parent / 'StrongerOrbitalLaser/scripts/research'
OUTPUT = ROOT / 'research/enemy-gib-threshold-F5FEE03DCFDB.json'
ENEMY_RESEARCH = ROOT / 'research/enemy-authoring-F5FEE03DCFDB.json'
PROFILE_DLL_SHA = build_profile.ACTIVE['gameDllSha256']
MISSION_SNAPSHOTS = ('F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap')
TEXT = (0x1000, 0x1000 + 0x210FA93)

# -- native layout --------------------------------------------------------------------------------------------------
GORE_INDEX_ROWS, GORE_RECORDS, GORE_RECORD = 418, 209, 33488
GROUPS, GROUP_STRIDE = 38, 872
HEALTH_RECORD, ZONE_BASE, ZONE_STRIDE, DEFAULT_ZONE = 22096, 520, 552, 64
FLT_MAX = 3.4028234663852886e+38
# GoreComponent members: offset -> (storage, hidden-name length, role id). Role ids are descriptive, not native names.
GORE_MEMBERS = {
    0: ('STRUCT', 11, 'groups[38] (GoreGroupInfo, 872 bytes each)'),
    33136: ('STRUCT', 20, 'actorOverride[38] {u32 from, u32 to}: hit actor translation before the group lookup'),
    33440: ('STRUCT', 19, 'wholeBodyEffect (GoreEffect) spawned when the whole-body group is destroyed'),
    33456: ('STRUCT', 18, 'unknown GoreEffect'),
    33472: ('FP32', 30, 'fallbackImpulseScale: push force x direction scale when no group is selected'),
    33476: ('FP32', 27, 'unknown float (read by 0x901630 / 0x902050)'),
    33480: ('UINT8', 23, 'unknown flag (read at the end of group destruction, 0x904540)'),
    33484: ('FP32', 16, 'copied to the gore instance (+0xB20) when the whole-body group is destroyed'),
}
GROUP_MEMBERS = {
    0: ('FP32', 10, 'destroyThreshold: destroy the group when the hit damage >= this; negative = never'),
    4: ('FP32', 16, 'secondaryThreshold: run the non-destroying gore action (0x904860) when damage >= this'),
    8: ('FP32', 22, 'impulseScale: push force x hit direction x this = the gib impulse'),
    16: ('STRUCT', 21, 'GoreEffectPair[4] (played by 0x904860)'),
    144: ('STRUCT', 11, 'GoreEffectPair[4]'),
    272: ('STRUCT', 34, 'VisibilityMaskFlip'),
    304: ('STRUCT', 24, 'VisibilityMaskFlip'),
    336: ('UINT32', 16, 'unknown thin hash'),
    340: ('UINT32', 6, 'actors[8]: physics actors this group owns (group lookup, first list)'),
    372: ('UINT32', 14, 'unknown thin hash[8]'),
    404: ('STRUCT', 5, 'GoreLinkInfo[2] {u32 target, trigger OnGib/OnDismember/OnAny, effect Gib/Dismember, ...}'),
    476: ('UINT32', 19, 'unknown thin hash[4]'),
    492: ('UINT32', 12, 'aliasActors[4]: second lookup list; resolves to actors[GOID % count]'),
    512: ('STRUCT', 12, 'GibEntity[4] (gib piece entities)'),
    864: ('UINT8', 27, 'unknown flag (1 on almost every populated group)'),
    865: ('UINT8', 15, 'flag read by 0x904860'),
    866: ('UINT8', 10, 'wholeBody: the first group with this set is the whole-body (splootch) group'),
    867: ('UINT8', 15, 'flag read by 0x903C70'),
}
# HealthComponent members considered as the threshold, with what the code shows. (offset, storage, length, verdict)
HEALTH_CANDIDATES = [
    ('record', 0, 'INT32', 6, 'main health', 'Read for death (via the live record +0x14 seeded from it). Decides '
        'whether the hit kills (one gate), never compared with the hit damage for gore.'),
    ('record', 24, 'INT32', 12, 'constitution', 'Read at 0x9244F2: health may fall to -constitution before death. '
        'Only moves the death gate.'),
    ('record', 40, 'ENUM_INT32', 9, 'UnitSize (filediver: "used for systems such as the gib system")', 'Read once '
        'at health-instance creation (0x91D65B) to register the entity in a per-size list (sizes 0-3, 256 each) '
        'consumed by 0x71C030 / 0x71C130. Not read by ApplyDamage; the gore evaluator never calls a HealthComponent '
        'settings getter. Not the gib threshold.'),
    ('record', 44, 'FP32', 9, 'mass', 'Not read by ApplyDamage or the gore evaluator.'),
    ('record', 21916, 'FP32', 31, 'unknown float', 'Not read by ApplyDamage or the gore evaluator.'),
    ('record', 22016, 'FP32', 28, 'unknown float', 'Read at 0x92504B on the death transition as a time compare '
        '(seconds since an instance timestamp >= this), gated by +22012. A death-presentation timer, not a '
        'damage threshold.'),
    ('zone', 204, 'FP32', 29, 'projectile durable share', 'Shapes the hit damage before the event (durable mix).'),
    ('zone', 208, 'FP32', 33, 'child-zone damage share', 'Read at 0x923E1B: a share of the hit is split to the '
        'zone\'s child zones; the rest feeds the zone and the gore damage.'),
    ('zone', 212, 'FP32', 44, 'child-zone damage share once the zone is dead', 'Read at 0x923E92 instead of +208 '
        'when the zone is already dead.'),
    ('zone', 232, 'INT32', 6, 'zone health', 'Zone death (health <= -constitution) is one gate for gore.'),
    ('zone', 236, 'INT32', 12, 'zone constitution', 'Zone death floor and the cap amount.'),
    ('zone', 240, 'UINT8', 8, 'immortal', 'Clamps the zone to downed; no zone death, so no zone-death gore.'),
    ('zone', 248, 'FP32', 19, 'affects main health', 'Scales the hit into main health (death gate). When the dying '
        'zone\'s hit actor already carries gore state bit 1 (set by the secondary gore action 0x904860, tested by '
        '0x905620), the main-health share of that hit becomes 0.'),
    ('zone', 252, 'FP32', 29, 'max-health loss on zone death', 'Read at 0x924254: max health -= zone health x this '
        'when the zone dies. Not a gore input.'),
    ('zone', 328, 'FP32', 28, 'unknown float', 'Not read by ApplyDamage or the gore evaluator.'),
    ('zone', 340, 'UINT8', 40, 'main health affect capped by zone health', 'Read at 0x924472: the hit damage is '
        'capped at (zone health before the hit + zone constitution). The capped value is what the gore evaluator '
        'compares, so a capped limb or head zone can never reach a large threshold.'),
    ('zone', 436, 'FP32', 30, 'unknown float', 'Not read by ApplyDamage or the gore evaluator.'),
]

# -- pinned instructions: (rva, exact capstone text, RIP target or None, role) ---------------------------------------
PINS = {
    'goreManagerGlobal': [
        (0x568E4A, 'lea rax, [rbx + 0x7ff2f8]', None, 'gore manager = component world + 0x7FF2F8'),
        (0x568E51, 'mov qword ptr [rip + 0x2dbd678], rax', 0x33264D0, 'gore manager global'),
        (0x56E571, 'mov r9d, dword ptr [rdi + 0x956084]', None, 'debug print: gore max (world + 0x7FF2F8 + 0x156D8C)'),
        (0x56E57F, 'lea r8, [rip + 0x1cde3f2]', 0x224C978, '"gore" : { "max" : %u, "capacity" : 384 }'),
        (0x53EAAE, 'mov esi, dword ptr [rdi + 0x156d90]', None, 'add: live count'),
        (0x53EACA, 'cmp esi, dword ptr [rdi + 0x156d88]', None, 'add: capacity'),
        (0x53EAE4, 'imul rcx, rbx, 0xb28', None, 'gore instance stride 0xB28'),
        (0x53EAF1, 'add rcx, qword ptr [rdi + 0x156dc0]', None, 'gore instance array'),
        (0x53EAFD, 'mov rax, qword ptr [rdi + 0x156db8]', None, 'descriptor array'),
        (0x53EB1A, 'inc dword ptr [rdi + 0x156d90]', None, '++live count'),
    ],
    'goreDefinitionGetter_0x508590': [
        (0x508598, 'mov rcx, qword ptr [rcx]', None, 'key = descriptor +0 (entity resource hash)'),
        (0x5085B1, 'mov r11, qword ptr [rax + 0xf12ba8]', None, 'shared loaded GoreComponentData table'),
        (0x5085C9, 'imul eax, edx, 0x1a2', None, '418 index rows'),
        (0x508622, 'lea r9, [r11 + 0x1a20]', None, 'records follow 418 x 16-byte index rows'),
        (0x508629, 'imul rax, rcx, 0x82d0', None, 'record index * 33488 (no per-instance copy)'),
    ],
    'applyDamageGate_0x9235F0': [
        (0x923766, 'call 0x507920', None, 'HealthComponent settings of the target'),
        (0x92392E, 'mov edx, dword ptr [rdx + rax + 0x10]', None, 'per-kind acceptance mask (relation multiplier)'),
        (0x9239FA, 'cvttss2si r12, xmm0', None, 'damage = trunc(damage * relation * element multiplier)'),
        (0x923C68, 'lea rax, [rdi + 0x3d0]', None, 'zone actor list: find the zone that lists the hit actor'),
        (0x923C76, 'movss xmm11, dword ptr [rbp + 0xb08]', None, 'xmm11 = event +0x34 push force (arg 10)'),
        (0x923EBA, 'cvtsi2ss xmm0, r8', None, 'child-zone split: damage share per child zone'),
        (0x923EFA, 'mov r13d, dword ptr [rdi + 0x2f4]', None, 'zone constitution (zone +236)'),
        (0x923F0B, 'sub eax, dword ptr [rbp - 0x10]', None, 'zone health - damage'),
        (0x923F11, 'cmovg r13d, eax', None, 'clamped at -constitution'),
        (0x923F15, 'mov dword ptr [rdx + rcx*4 + 0xf8], r13d', None, 'live zone health'),
        (0x923F39, 'movss xmm8, dword ptr [rdi + 0x300]', None, 'zone affects-main-health share (zone +248)'),
        (0x9240A5, 'cmp byte ptr [r15 + 0x2f8], r13b', None, 'immortal zone (zone +240) clamps to downed'),
        (0x9240EF, 'sete byte ptr [rbp - 0x37]', None, 'zoneDied = new zone state == 2'),
        (0x9241D7, 'call 0x905620', None, 'dying zone\'s actor already has gore state bit 1?'),
        (0x9241EE, 'movaps xmm8, xmm10', None, '-> its main-health share becomes 0'),
        (0x9242A1, 'cmp byte ptr [rdi + 0x2fc], 0', None, 'zone causes death on death (zone +244)'),
        (0x9242AE, 'cmp byte ptr [rax + 0x55e4], 0', None, 'entity can die naturally (+21988)'),
        (0x9242B7, 'mov byte ptr [rbp - 0x7f], 1', None, 'zone death kills the entity'),
        (0x924472, 'cmp byte ptr [rdi + 0x35c], 0', None, 'zone +340: cap the hit at the zone\'s remaining pool'),
        (0x924486, 'add ecx, dword ptr [rdi + 0x2f4]', None, 'zone health before the hit + zone constitution'),
        (0x92448E, 'cmovb ecx, eax', None, 'damage = min(damage, that)'),
        (0x92449A, 'mov dword ptr [rbp + 0xaf8], eax', None, 'capped damage replaces the hit damage'),
        (0x923D0D, 'mov rdi, qword ptr [rbp - 0x10]', None, 'final hit damage'),
        (0x923D1A, 'cvtsi2ss xmm9, rax', None, 'xmm9 = float(final hit damage): the value gore compares'),
        (0x9244E6, 'mov ecx, dword ptr [rax + 0x14]', None, 'live main health'),
        (0x9244ED, 'sub ecx, edx', None, 'minus the main-health share of the hit'),
        (0x9244F2, 'mov eax, dword ptr [rax + 0x18]', None, 'HealthComponent constitution (+24)'),
        (0x9244F7, 'cmp ecx, eax', None, 'at or below -constitution ->'),
        (0x924591, 'mov byte ptr [rbp - 0x80], dl', None, 'died = 1'),
        (0x924B8A, 'mov byte ptr [rbp - 0x80], 1', None, 'a death-causing zone death also sets died'),
        (0x925086, 'mov r8, qword ptr [rip + 0x2a01443]', 0x33264D0, 'gore manager: does the target have gore?'),
        (0x9250F7, 'cmp dword ptr [rbp - 0x7c], 8', None, 'never for Drown (damage kind 8)'),
        (0x925101, 'cmp byte ptr [rbp - 0x80], 0', None, 'only if the entity died this hit ...'),
        (0x925107, 'cmp byte ptr [rbp - 0x37], 0', None, '... or a damage zone died this hit'),
        (0x92513A, 'mov r9d, dword ptr [rbp - 0x7c]', None, 'arg: damage kind'),
        (0x92513E, 'mov r8d, dword ptr [rbp + 0xb38]', None, 'arg: event +0x5C (hit class)'),
        (0x925145, 'mov rcx, qword ptr [rip + 0x2a01384]', 0x33264D0, 'this = gore manager'),
        (0x925184, 'cvttss2si r14, xmm11', None, 'arg: int(push force)'),
        (0x925189, 'cvttss2si r13, xmm9', None, 'arg: int(final hit damage)'),
        (0x9251A8, 'call 0x9057d0', None, 'GORE EVALUATOR'),
        (0x925334, 'mov ecx, 0xe57d84b', None, 'network message carrying the same gore inputs'),
        (0x925339, 'call 0xbde430', None, 'send'),
        (0x925387, 'call 0x925f10', None, 'after gore: HealthComponentDeath'),
        (0x925578, 'call 0xb96310', None, 'after gore: killed-entity dispatch (kill credit)'),
        (0x9256F4, 'call 0x91c240', None, 'after gore: SetLifeState (record +412 raised to 2)'),
    ],
    'goreEvaluator_0x9057D0': [
        (0x905808, 'mov r14d, dword ptr [rbp + 0x130]', None, 'push force'),
        (0x9058B9, 'cmp esi, 5', None, 'hit class 5 -> no gore'),
        (0x9058C2, 'mov rcx, qword ptr [rax]', None, 'gore instance state table'),
        (0x9058CE, 'cmp dword ptr [rcx + 0x5408], 0', None, 'no gore state -> no gore'),
        (0x9058DB, 'test esi, esi', None, 'hit class 0 -> no gore'),
        (0x9058E3, 'cmp r9d, 0xa', None, 'damage kind 10 (none) -> no gore'),
        (0x9058ED, 'cmp dword ptr [rbp + 0x120], 2', None, 'element 2 (Electricity)?'),
        (0x9058F6, 'mov eax, dword ptr [rbp + 0x128]', None, 'hit damage'),
        (0x905904, 'addss xmm0, xmm0', None, '-> doubled for the gore comparison'),
        (0x905935, 'mov eax, dword ptr [rbp + 0x128]', None, 'otherwise the hit damage as is'),
        (0x905942, 'call 0x508590', None, 'GoreComponent definition (shared table)'),
        (0x90595E, 'lea rdx, [rax + 0x8170]', None, 'actor override table (+33136)'),
        (0x905987, 'mov edi, dword ptr [r9 + rcx*8 + 0x8174]', None, 'translated hit actor'),
        (0x90598F, 'movzx r12d, byte ptr [rbp + 0x150]', None, 'died flag'),
        (0x9059BA, 'cmp dword ptr [rbp + 0x120], 2', None, 'Electricity ...'),
        (0x9059C3, 'test r12b, r12b', None, '... kill skips the per-actor group lookup'),
        (0x9059DF, 'call 0x903ba0', None, 'group that owns the hit actor'),
        (0x9059E8, 'cmp r9d, -1', None, 'none -> whole-body group'),
        (0x905A19, 'mov r8, qword ptr [rip + 0x2a21300]', 0x3326D20, 'no actor: avatars (Helldivers) test every group'),
        (0x905AE9, 'movss xmm0, dword ptr [r14]', None, 'avatar loop: group destroyThreshold'),
        (0x905B32, 'call 0x903c70', None, 'avatar loop: destroy group'),
        (0x905B39, 'comiss xmm6, dword ptr [rdx - 0x150]', None, 'avatar loop: secondaryThreshold'),
        (0x905BCA, 'cmp r11d, 4', None, 'explosion kind: separate x4 impulse accumulator'),
        (0x905BE7, 'movss xmm2, dword ptr [rdi + 0x82c0]', None, 'fallbackImpulseScale (+33472)'),
        (0x905C8D, 'movss xmm1, dword ptr [rip + 0x1ac177b]', 0x23C7410, '4.0 explosion impulse factor'),
        (0x905CF8, 'lea rax, [rdi + 0x362]', None, 'scan groups for the wholeBody flag (+866)'),
        (0x905D00, 'cmp byte ptr [rax], 0', None, 'first group with the flag'),
        (0x905D0E, 'cmp r9d, 0x26', None, '38 groups; none -> no gore at all'),
        (0x905D30, 'imul r14, rdx, 0x368', None, 'selected group = record + index * 872'),
        (0x905E33, 'mov eax, dword ptr [rbp - 0x78]', None, 'gore damage (doubled for Electricity)'),
        (0x905E39, 'movss xmm1, dword ptr [r14]', None, 'group destroyThreshold (+0)'),
        (0x905E41, 'comiss xmm1, xmm6', None, 'threshold >= 0 ...'),
        (0x905E49, 'jb 0x90622b', None, '(negative: never destroyed)'),
        (0x905E4F, 'comiss xmm0, xmm1', None, '... and damage >= threshold'),
        (0x905E52, 'jb 0x90622b', None, 'below: secondary path'),
        (0x905E58, 'cmp byte ptr [r14 + 0x362], 0', None, 'wholeBody group?'),
        (0x905E60, 'je 0x9061ee', None, 'no: destroy this group (sever)'),
        (0x905F84, 'lea r13, [rdi + 0x82a0]', None, 'yes: whole-body effect (+33440) at the body pose'),
        (0x9061E4, 'call 0x908220', None, 'whole-body destruction (the splootch)'),
        (0x906221, 'call 0x903c70', None, 'group destruction (sever)'),
        (0x90622B, 'comiss xmm0, dword ptr [r14 + 4]', None, 'damage >= secondaryThreshold (+4)'),
        (0x906236, 'cmp esi, 9', None, 'hit class 9 skips the secondary action'),
        (0x906250, 'call 0x904860', None, 'secondary (non-destroying) gore action'),
        (0x90628B, 'movss xmm2, dword ptr [r14 + 8]', None, 'group impulseScale (+8)'),
    ],
    'goreGroupLookup_0x903BA0': [
        (0x903BC2, 'add rbx, 0x154', None, 'group actors[8] (+340)'),
        (0x903BE7, 'cmp ecx, r11d', None, 'actor == hit actor'),
        (0x903BFC, 'lea rax, [rbx + 0x98]', None, 'aliasActors[4] (+492)'),
        (0x903C1B, 'add rbx, 0x368', None, 'next group (872)'),
        (0x903C22, 'cmp edi, 0x26', None, '38 groups'),
        (0x903C44, 'mov dword ptr [r9], edi', None, 'out: group index'),
    ],
    'groupDestruction': [
        (0x903CF2, 'mov eax, dword ptr [r12 + rdx*8 + 0xc]', None, 'per-actor gore state'),
        (0x903CF7, 'test al, 1', None, 'already destroyed -> nothing (one-shot)'),
        (0x903CFF, 'or eax, 1', None, 'mark destroyed'),
        (0x908281, 'mov ecx, dword ptr [rax + 0x82cc]', None, 'whole-body: GoreComponent +33484 ...'),
        (0x908287, 'mov dword ptr [rbx + 0xb20], ecx', None, '... -> gore instance +0xB20'),
        (0x9056D3, 'lea rcx, [r9 + 0x8170]', None, '0x905620: same actor override'),
        (0x9057B7, 'mov eax, dword ptr [r11 + rcx*8 + 0xc]', None, '0x905620: per-actor gore state'),
        (0x9057BC, 'shr eax, 1', None, '0x905620: bit 1 (set by the secondary action)'),
        (0x904B3B, 'or dword ptr [rbx + 4], 2', None, '0x904860 sets bit 1 (gored, not destroyed)'),
    ],
    'gateInputs': [
        (0x12A1616, 'mov dword ptr [rdx + 0xc], r9d', None, 'hit +0xC = caller-supplied hit class'),
        (0x12A2A91, 'xor esi, esi', None, 'explosion hit wrapper: esi = 0'),
        (0x12A2B22, 'lea r9d, [rsi + 1]', None, 'explosion hits: hit class 1'),
        (0x12A2B2B, 'lea r8d, [rsi + 4]', None, 'explosion hits: damage kind 4'),
        (0x12A243A, 'mov eax, dword ptr [rcx + 0x24]', None, 'DamageInfo +0x24 (push force)'),
        (0x12A244A, 'movss dword ptr [r14 + 0xb4], xmm0', None, '-> hit +0xB4'),
        (0x129CBAF, 'cvttss2si rax, dword ptr [rbx + 0xb4]', None, 'damage values: push force'),
        (0x129CBB8, 'mov dword ptr [rdi + 0x10], eax', None, '-> values +0x10'),
        (0x129E4B4, 'cvttss2si rax, xmm1', None, 'post-armor hit damage'),
        (0x129E4B9, 'mov dword ptr [r14 + r13 + 0x114c], eax', None, '-> event +0x2C'),
        (0x129E4CC, 'mov eax, dword ptr [rcx + 0x10]', None, 'values +0x10'),
        (0x129E4D4, 'movss dword ptr [r14 + r13 + 0x1154], xmm0', None, '-> event +0x34 (float)'),
        (0x129E53F, 'mov eax, dword ptr [r15 + 0xc]', None, 'hit +0xC'),
        (0x129E543, 'mov dword ptr [r14 + r13 + 0x117c], eax', None, '-> event +0x5C'),
        (0x12A8241, 'mov r9d, dword ptr [r14 + 8]', None, 'consumer: element -> ApplyDamage r9'),
        (0x12A826A, 'mov eax, dword ptr [r14 + 0x5c]', None, 'consumer: event +0x5C ...'),
        (0x12A826E, 'mov dword ptr [rsp + 0x78], eax', None, '... -> ApplyDamage arg 16'),
        (0x12A82B4, 'movss xmm0, dword ptr [r14 + 0x34]', None, 'consumer: push force ...'),
        (0x12A82BA, 'movss dword ptr [rsp + 0x48], xmm0', None, '... -> ApplyDamage arg 10'),
    ],
    'unitSizeIsNotGore': [
        (0x91D65B, 'movsxd rcx, dword ptr [rax + 0x28]', None, 'instance creation reads UnitSize (+40)'),
        (0x91D667, 'cmp ecx, 4', None, 'size 4 (Num) excluded'),
        (0x91D66C, 'imul rdx, rcx, 0x404', None, 'per-size entity list (256 + count)'),
        (0x91D68B, 'mov dword ptr [rdx + rcx*4], eax', None, 'entity appended'),
    ],
}
CONSTANTS = {0x23C7410: 4.0}
DECISION_FUNCTIONS = (0x9057D0, 0x903BA0, 0x508590)
ACTION_FUNCTIONS = (0x903C70, 0x904860, 0x908220)
HEALTH_SETTINGS_GETTERS = (0x507920, 0x507430)
EVALUATOR_CALLERS = {0x9235F0: 'HealthManager::ApplyDamage', 0x12A6EF0: 'DamageSystem::Drain',
    0x9085A0: 'unproven (gore replay?)', 0xB77460: 'unproven', 0xBA3B50: 'unproven',
    0xA283D0: 'forced: damage 0xFFFFFFFF, push 100, kind 4, died'}
ELEMENTS = ['None', 'Fire', 'Electricity', 'Acid', 'Bleed', 'Gas']  # filediver ElementType order

# The classes the question names, mapped to native classes. 'basis' says how the mapping is known.
COMPARISON = [
    ('Scavenger', 'scavenger_tier_1', 'native class; no wiki anatomy match'),
    ('Scavenger (base)', 'scavenger_base', 'native class; no wiki anatomy match'),
    ('Hunter', 'hunter_tier_1', 'wiki candidate Hunter'),
    ('Pouncer / Hunter tier 2', 'hunter_tier_2', 'wiki candidate Hunter; Pouncer not resolved'),
    ('Predator Hunter', 'hunter_tier_3', 'wiki name'),
    ('Warrior', 'warrior_tier_1', 'wiki candidate Warrior'),
    ('Warrior tier 2', 'warrior_tier_2', 'wiki candidates Bile Warrior / Warrior'),
    ('Hive Guard', 'warrior_plus', 'wiki name'),
    ('Brood Commander (likely)', 'warrior_big', 'PLAUSIBLE: no wiki anatomy match; 800 HP'),
    ('Alpha Commander (likely)', 'warrior_big_tier2', 'PLAUSIBLE: no wiki anatomy match; 1000 HP'),
    ('Stalker', 'stalker', 'wiki name'),
    ('Shrieker', 'shrieker', 'native class'),
    ('Bile Spewer (likely)', 'boomer', 'wiki candidates Bile Spewer / Nursing Spewer'),
    ('Nursing Spewer (likely)', 'boomer_nurser', 'wiki candidates Bile Spewer / Nursing Spewer'),
    ('Charger', 'charger', 'wiki name'),
    ('Charger Behemoth', 'charger_tier2', 'wiki candidate'),
    ('Bile Titan', 'strider', 'wiki name'),
    ('Trooper', 'conscript_tier_2', 'wiki candidates incl. Trooper'),
    ('Devastator', 'soldier', 'wiki candidate Devastator'),
    ('Heavy Devastator (likely)', 'soldier_mg', 'wiki candidate Devastator'),
    ('Hulk', 'lieutenant_base', 'wiki candidates Hulk *'),
    ('Berserker (likely)', 'berserker', 'native class'),
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def hexid(value: int) -> str:
    return f'0x{value:016X}'


def u32(raw, at): return struct.unpack_from('<I', raw, at)[0]
def i32(raw, at): return struct.unpack_from('<i', raw, at)[0]
def f32(raw, at): return struct.unpack_from('<f', raw, at)[0]


def num(value):
    return None if value is None else (int(value) if float(value).is_integer() else round(value, 6))


class Names:
    def __init__(self):
        sys.path.insert(0, str(HELPERS))
        from probe_components import resource_hash
        self.resource_hash = resource_hash
        fd = build_profile.FILEDIVER
        self.paths, self.thin = {}, {}
        for line in (fd / 'hashes/hashes.txt').read_text(encoding='utf-8', errors='ignore').splitlines():
            line = line.strip()
            if line and not line.startswith('//'):
                self.paths[resource_hash(line)] = line
        for line in (fd / 'hashes/thinhashes.txt').read_text(encoding='utf-8', errors='ignore').splitlines():
            line = line.strip()
            if line:
                self.thin.setdefault(resource_hash(line) >> 32, line)

    def name(self, value):
        return None if not value else self.thin.get(value, f'0x{value:08X}')


# -- layout ----------------------------------------------------------------------------------------------------------
def member_rows(library, type_ref):
    desc = library.layout(type_ref)
    rows = {}
    for m in desc['members']:
        offset = int(m['name'].split('=')[1].split(',')[0], 16)
        rows[m['offset64']] = {'offset': m['offset64'], 'size': m['size64'], 'storage': m['storage'],
            'atom': m['atom'], 'count': m['array_or_bits'], 'nameLength': library.name_length(offset),
            'typeHash': m['type_hash']}
    return desc, rows


def check_layout(library):
    outer, outer_rows = member_rows(library, 'GoreComponentData')
    index, records = outer_rows[0], outer_rows[GORE_INDEX_ROWS * 16]
    record, record_rows = member_rows(library, records['typeHash'])
    group, group_rows = member_rows(library, record_rows[0]['typeHash'])
    geometry = {'indexRows': index['count'], 'records': records['count'], 'recordSize': record['size64'],
        'groups': record_rows[0]['count'], 'groupStride': group['size64']}
    expected = {'indexRows': GORE_INDEX_ROWS, 'records': GORE_RECORDS, 'recordSize': GORE_RECORD, 'groups': GROUPS,
        'groupStride': GROUP_STRIDE}
    bad = [k for k, v in expected.items() if geometry[k] != v]
    for table, rows in ((GORE_MEMBERS, record_rows), (GROUP_MEMBERS, group_rows)):
        for offset, (storage, length, _) in table.items():
            row = rows.get(offset)
            if row is None or row['storage'] != storage or row['nameLength'] != length:
                bad.append(f'+{offset}')
    health, health_rows = member_rows(library, member_rows(library, 'HealthComponentData')[1][1002 * 16]['typeHash'])
    zone, zone_rows = member_rows(library, health_rows[DEFAULT_ZONE]['typeHash'])
    for scope, offset, storage, length, _, _ in HEALTH_CANDIDATES:
        row = (health_rows if scope == 'record' else zone_rows).get(offset)
        if row is None or row['storage'] != storage or row['nameLength'] != length:
            bad.append(f'{scope}+{offset}')
    if bad or health['size64'] != HEALTH_RECORD:
        raise ValueError(f'GoreComponent / HealthComponent layout changed: {bad} {geometry}')
    publish = lambda table, rows: [dict(rows[o], role=role) for o, (_, _, role) in sorted(table.items())]
    labels = {('record', o): f"{r['storage']} name {r['nameLength']}" for o, r in health_rows.items()}
    labels.update({('zone', o): f"{r['storage']} name {r['nameLength']}" for o, r in zone_rows.items()})
    return {'geometry': dict(geometry, indexRowSize=16, recordsOffset=GORE_INDEX_ROWS * 16,
                goreComponentTypeHash=f"0x{record['type_hash']:08X}", goreGroupTypeHash=f"0x{group['type_hash']:08X}"),
        'goreComponent': publish(GORE_MEMBERS, record_rows), 'goreGroupInfo': publish(GROUP_MEMBERS, group_rows),
        'unlistedGroupMembers': [r for o, r in sorted(group_rows.items()) if o not in GROUP_MEMBERS],
        'healthLabels': labels}


# -- code ------------------------------------------------------------------------------------------------------------
class Image:
    def __init__(self, data):
        self.data = data
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True

    def insn(self, rva):
        insn = next(self.md.disasm(self.data[rva:rva + 16], rva), None)
        if insn is None:
            raise ValueError(f'undecodable instruction at {rva:#x}')
        return insn

    def pin(self, rva, text, target, role):
        insn = self.insn(rva)
        got = insn.mnemonic + ' ' + insn.op_str
        rip = None
        for op in insn.operands:
            if op.type == x86.X86_OP_MEM and op.mem.base == x86.X86_REG_RIP:
                rip = insn.address + insn.size + op.mem.disp
        if got != text or rip != target:
            raise ValueError(f'pin drifted at {rva:#x}: {got!r} (rip {rip}) != {text!r} ({target})')
        return {'rva': f'0x{rva:X}', 'bytes': self.data[rva:rva + insn.size].hex(), 'asm': got,
            'ripTarget': None if target is None else f'0x{target:X}', 'role': role}

    def reachable(self, start, limit=20000):
        seen, work = {}, [start]
        while work and len(seen) < limit:
            a = work.pop()
            while a not in seen and TEXT[0] <= a < TEXT[1]:
                insn = next(self.md.disasm(self.data[a:a + 16], a, 1), None)
                if insn is None:
                    break
                seen[a] = insn
                if insn.mnemonic in ('ret', 'int3', 'ud2'):
                    break
                op = insn.operands[0] if insn.operands else None
                if insn.mnemonic == 'jmp':
                    if op is not None and op.type == x86.X86_OP_IMM:
                        work.append(op.imm)
                    break
                if insn.mnemonic.startswith('j') and op is not None and op.type == x86.X86_OP_IMM:
                    work.append(op.imm)
                a += insn.size
        return seen

    def direct_calls(self, start):
        return {i.operands[0].imm for i in self.reachable(start).values()
            if i.mnemonic == 'call' and i.operands and i.operands[0].type == x86.X86_OP_IMM}


def evaluator_isolation(image):
    """The decision (0x9057D0 up to the threshold compare, the group lookup 0x903BA0, the GoreComponent getter
    0x508590) never calls a HealthComponent settings getter, so no HealthComponent member can be the threshold it
    compares. The destruction actions run after the decision; their HealthComponent reads (within three call
    levels) are reported with the call chain."""
    decision_calls = {f: image.direct_calls(f) for f in DECISION_FUNCTIONS}
    bad = sorted(f'0x{f:X}' for f, calls in decision_calls.items() for g in HEALTH_SETTINGS_GETTERS if g in calls)
    if bad:
        raise ValueError(f'gore decision now calls a HealthComponent getter: {bad}')
    parent, reached, frontier, scanned = {}, set(ACTION_FUNCTIONS), set(ACTION_FUNCTIONS), set()
    for _ in range(3):
        following = set()
        for function in sorted(frontier - scanned):
            scanned.add(function)
            for call in sorted(image.direct_calls(function)):
                if call not in reached and call not in following:
                    parent[call] = function
                    following.add(call)
        frontier = following
        reached |= following
    chains = []
    for getter in HEALTH_SETTINGS_GETTERS:
        if getter in reached:
            chain = [getter]
            while chain[-1] in parent:
                chain.append(parent[chain[-1]])
            chains.append(' <- '.join(f'0x{x:X}' for x in chain))
    callers = {}
    for caller, role in EVALUATOR_CALLERS.items():
        if 0x9057D0 not in image.direct_calls(caller):
            raise ValueError(f'evaluator caller changed: {caller:#x}')
        callers[f'0x{caller:X}'] = role
    return {'decisionFunctions': {f'0x{f:X}': sorted(f'0x{c:X}' for c in calls) for f, calls in
            decision_calls.items()},
        'decisionCallsHealthSettingsGetter': False,
        'postDecisionHealthReads': {'callDepth': 3, 'chains': chains,
            'note': 'after the decision: the whole-body action walks HealthComponent zone actor lists (0x922390).'},
        'evaluatorCallers': callers}


def full_register(name):
    """Capstone sub-register name -> its 64-bit register (eax -> rax, r9d -> r9)."""
    legacy = {'al': 'rax', 'ah': 'rax', 'ax': 'rax', 'eax': 'rax', 'bl': 'rbx', 'bh': 'rbx', 'bx': 'rbx', 'ebx': 'rbx',
        'cl': 'rcx', 'ch': 'rcx', 'cx': 'rcx', 'ecx': 'rcx', 'dl': 'rdx', 'dh': 'rdx', 'dx': 'rdx', 'edx': 'rdx',
        'sil': 'rsi', 'si': 'rsi', 'esi': 'rsi', 'dil': 'rdi', 'di': 'rdi', 'edi': 'rdi'}
    match = re.fullmatch(r'(r\d+)[dwb]?', name)
    return legacy.get(name, match.group(1) if match else name)


def settings_references(image, labels):
    """Every HealthComponent definition member ApplyDamage references, by a forward register dataflow over its
    control-flow graph (meet = intersection): the definition pointer is kept at [rbp+0x18] (stored after the getter
    call at 0x923766) and a zone pointer (definition + i * 0x228) at [rbp+0x40] or built by `add reg, [rbp+0x18]`.
    A memory operand whose base or index register holds one of them on every path is a reference to that member."""
    insns = image.reachable(0x9235F0)
    successors = {}
    for address, insn in insns.items():
        out = []
        op = insn.operands[0] if insn.operands else None
        if insn.mnemonic.startswith('j') and op is not None and op.type == x86.X86_OP_IMM and op.imm in insns:
            out.append(op.imm)
        if insn.mnemonic not in ('jmp', 'ret', 'int3', 'ud2') and address + insn.size in insns:
            out.append(address + insn.size)
        successors[address] = out

    def transfer(insn, state):
        state = dict(state)
        _, written = insn.regs_access()
        for reg in written:
            state.pop(full_register(insn.reg_name(reg)), None)
        ops = insn.operands
        if len(ops) == 2 and ops[0].type == x86.X86_OP_REG and ops[1].type == x86.X86_OP_MEM                 and ops[1].mem.base == x86.X86_REG_RBP and ops[1].mem.index == 0:
            reg = insn.reg_name(ops[0].reg)
            if insn.mnemonic == 'mov' and ops[1].mem.disp == 0x18:
                state[reg] = 'definition'
            elif insn.mnemonic == 'mov' and ops[1].mem.disp == 0x40:
                state[reg] = 'zone'
            elif insn.mnemonic == 'add' and ops[1].mem.disp == 0x18:
                state[reg] = 'zone'
        return state

    entry = {0x9235F0: {}}
    work = [0x9235F0]
    while work:
        address = work.pop()
        state = transfer(insns[address], entry[address])
        for nxt in successors[address]:
            if nxt not in entry:
                entry[nxt] = state
                work.append(nxt)
            else:
                merged = {r: k for r, k in entry[nxt].items() if state.get(r) == k}
                if merged != entry[nxt]:
                    entry[nxt] = merged
                    work.append(nxt)
    refs = []
    for address in sorted(entry):
        insn, tracked = insns[address], entry[address]
        for op in insn.operands:
            if op.type != x86.X86_OP_MEM:
                continue
            kinds = {tracked[r] for r in (insn.reg_name(x) for x in (op.mem.base, op.mem.index) if x) if r in tracked}
            if not kinds:
                continue
            kind, disp = sorted(kinds)[0], op.mem.disp
            if kind == 'zone' or ZONE_BASE <= disp < ZONE_BASE + GROUPS * ZONE_STRIDE:
                scope, offset = 'zone', disp - ZONE_BASE
            elif DEFAULT_ZONE <= disp < ZONE_BASE:
                scope, offset = 'defaultZone', disp - DEFAULT_ZONE
            else:
                scope, offset = 'record', disp
            refs.append({'rva': f'0x{address:X}', 'asm': insn.mnemonic + ' ' + insn.op_str, 'scope': scope,
                'offset': offset})
    members = {}
    for ref in refs:
        key = (ref['scope'], ref['offset'])
        label = labels.get(('zone' if ref['scope'] == 'defaultZone' else ref['scope'], ref['offset']))
        entry = members.setdefault(key, {'scope': ref['scope'], 'offset': ref['offset'], 'member': label,
            'references': []})
        entry['references'].append(ref['rva'])
    out = []
    for scope, offset, _, _, label, _ in HEALTH_CANDIDATES:
        hits = sorted({r for (s, o), e in members.items() if o == offset and (s == scope or
            (scope == 'zone' and s == 'defaultZone')) for r in e['references']})
        out.append({'scope': scope, 'offset': offset, 'label': label, 'applyDamageReferences': hits})
    return {'function': '0x9235F0', 'instructions': len(insns), 'definitionPointer': '[rbp+0x18]',
        'zonePointer': '[rbp+0x40]', 'candidates': out,
        'allReferencedMembers': sorted(members.values(), key=lambda e: (e['scope'], e['offset']))}


# -- data ------------------------------------------------------------------------------------------------------------
def group_values(raw, index, names):
    base = index * GROUP_STRIDE
    actors = [names.name(v) for v in struct.unpack_from('<8I', raw, base + 340) if v]
    aliases = [names.name(v) for v in struct.unpack_from('<4I', raw, base + 492) if v]
    links = []
    for k in range(2):
        target, trigger, effect = struct.unpack_from('<III', raw, base + 404 + 36 * k)
        if target:
            links.append({'target': names.name(target), 'trigger': trigger, 'effect': effect})
    gibs = [hexid(struct.unpack_from('<Q', raw, base + 512 + 88 * k)[0]) for k in range(4)
        if struct.unpack_from('<Q', raw, base + 512 + 88 * k)[0]]
    return {'index': index, 'actors': actors, 'aliasActors': aliases,
        'destroyThreshold': num(f32(raw, base)), 'secondaryThreshold': num(f32(raw, base + 4)),
        'impulseScale': num(f32(raw, base + 8)), 'wholeBody': bool(raw[base + 866]),
        'flags': {'+864': raw[base + 864], '+865': raw[base + 865], '+866': raw[base + 866], '+867': raw[base + 867]},
        'links': links, 'gibEntities': gibs, 'recordOffset': base}


def populated(group):
    return bool(group['actors'] or group['aliasActors'] or group['gibEntities'] or group['wholeBody'])


def whole_body_guards(raw, index):
    """Bytes a write re-proves before touching the whole-body threshold: the group's actor list, its flags (+866 set)
    and, for every earlier group, a clear +866 (so the group is the FIRST whole-body group the evaluator picks)."""
    base = index * GROUP_STRIDE
    if raw[base + 866] != 1:
        raise ValueError('whole-body flag not set on the selected group')
    guards = [{'offset': base + 340, 'hex': raw[base + 340:base + 372].hex(), 'role': 'group actors[8] (+340)'},
        {'offset': base + 864, 'hex': raw[base + 864:base + 868].hex(), 'role': 'group flags +864..+867 (+866 = 1)'}]
    guards += [{'offset': g * GROUP_STRIDE + 866, 'hex': '00', 'role': f'group {g} is not whole-body'}
        for g in range(index)]
    return guards


def gore_anatomy(raw, names):
    groups = [group_values(raw, i, names) for i in range(GROUPS)]
    groups = [g for g in groups if populated(g)]
    whole = next((g for g in groups if g['wholeBody']), None)
    overrides = [{'from': names.name(a), 'to': names.name(b)} for a, b in struct.iter_unpack('<II',
        raw[33136:33136 + 304]) if a and a != b]
    limbs = [g for g in groups if not g['wholeBody']]
    enabled = [g['destroyThreshold'] for g in limbs if g['destroyThreshold'] >= 0]
    return {'wholeBodyGroup': None if whole is None else dict({k: whole[k] for k in ('index', 'actors',
            'destroyThreshold', 'secondaryThreshold', 'impulseScale', 'recordOffset')},
            guards=whole_body_guards(raw, whole['index'])),
        'wholeBodyThreshold': None if whole is None else whole['destroyThreshold'],
        'groups': groups, 'actorOverrides': overrides,
        'limbThresholds': {'enabled': sorted(set(enabled)), 'disabledGroups': sum(1 for g in limbs
            if g['destroyThreshold'] < 0)},
        'entity': {'fallbackImpulseScale': num(f32(raw, 33472)), 'float33476': num(f32(raw, 33476)),
            'flag33480': raw[33480], 'float33484': num(f32(raw, 33484))}}


def verdict(gore):
    if gore is None:
        return 'NO_GORE_COMPONENT'
    if gore['wholeBodyThreshold'] is None:
        return 'NO_WHOLE_BODY_GROUP'
    return 'WHOLE_BODY_DISABLED' if gore['wholeBodyThreshold'] < 0 else 'WHOLE_BODY_GIB'


def class_rows(view, names):
    enemies = json.loads(ENEMY_RESEARCH.read_text(encoding='utf-8'))
    gore_table, health_table = view.component('GoreComponentData'), view.component('HealthComponentData')
    rows = []
    for item in enemies['classes']:
        resource = int(item['resource'], 16)
        health_raw = health_table.records[item['health']['recordIndex']]
        entry = gore_table.owners.get(resource)
        gore = None
        if entry is not None:
            record, row = entry
            owners = gore_table.owners_of(record)
            gore = dict(gore_anatomy(gore_table.records[record], names), recordIndex=record, indexRow=row,
                ownerCount=len(owners), uniqueOwner=len(owners) == 1,
                coOwners=sorted(names.paths.get(o) or hexid(o) for o in owners if o != resource),
                recordSha256=sha(gore_table.records[record]))
        main = i32(health_raw, 0)
        caps = sorted({z['index'] for z in item['zones'] if z['mainHealthCapped']})
        row = {'className': item['className'], 'path': item['path'], 'resource': item['resource'],
            'faction': item['faction'], 'kind': item['kind'], 'wikiName': item['wikiName'],
            'wikiCandidates': item['wikiCandidates'], 'mainHealth': main, 'constitution': item['main']['constitution'],
            'unitSize': i32(health_raw, 40), 'mass': num(f32(health_raw, 44)),
            'zonesCappedByZoneHealth': caps, 'defaultZoneCapped': item['default']['mainHealthCapped'],
            'verdict': verdict(gore), 'gore': gore}
        if gore and gore['wholeBodyThreshold'] is not None and gore['wholeBodyThreshold'] >= 0 and main > 0:
            row['wholeBodyThresholdToMainHealth'] = round(gore['wholeBodyThreshold'] / main, 3)
        rows.append(row)
    return rows


def member_clusters(view):
    """How each scalar member varies across every GoreComponent record (classes and non-enemies alike)."""
    table = view.component('GoreComponentData')
    group_scalars = {0: 'f', 4: 'f', 8: 'f', 864: 'b', 865: 'b', 866: 'b', 867: 'b'}
    out = {'goreGroupInfo': {}, 'goreComponent': {}}
    for offset, kind in group_scalars.items():
        values = Counter()
        for raw in table.records:
            for g in range(GROUPS):
                at = g * GROUP_STRIDE + offset
                values[num(f32(raw, at)) if kind == 'f' else raw[at]] += 1
        out['goreGroupInfo'][f'+{offset}'] = {'role': GROUP_MEMBERS[offset][2], 'distinctValues': len(values),
            'mostCommon': [[v, n] for v, n in values.most_common(12)]}
    for offset, kind in ((33472, 'f'), (33476, 'f'), (33480, 'b'), (33484, 'f')):
        values = Counter(num(f32(raw, offset)) if kind == 'f' else raw[offset] for raw in table.records)
        out['goreComponent'][f'+{offset}'] = {'role': GORE_MEMBERS[offset][2], 'distinctValues': len(values),
            'values': [[v, n] for v, n in values.most_common()]}
    return out


def health_deltas(view):
    gore_type = view.component('GoreComponentData').type_index
    touched = [hexid(r) for r, d in view.deltas.items() if any(e['component'] == gore_type for e in d['entries'])]
    return {'goreComponentTypeIndex': gore_type, 'entityDeltasTouchingGore': touched}


# -- snapshots -------------------------------------------------------------------------------------------------------
class Heap:
    def __init__(self, snap):
        self.snap = snap

    def read(self, address, size):
        region = self.snap.region(address)
        if region is None or region['status'] != snapshot_image.CAPTURED or address + size > region['base'] + region['size']:
            return None
        self.snap.handle.seek(region['data_offset'] + address - region['base'])
        return self.snap.handle.read(size)

    def u32(self, address):
        raw = self.read(address, 4)
        return None if raw is None else struct.unpack('<I', raw)[0]

    def ptr(self, address):
        raw = self.read(address, 8)
        value = None if raw is None else struct.unpack('<Q', raw)[0]
        return value if value and 0x10000 <= value < 0x800000000000 else None


def snapshot_evidence(view, names):
    gore = view.component('GoreComponentData')
    out = []
    for name in MISSION_SNAPSHOTS:
        path = build_profile.snapshot_directory() / name
        snap = snapshot_image.Snapshot(path)
        try:
            if snap.game_dll_sha256.upper() != PROFILE_DLL_SHA.upper():
                raise ValueError(f'{name}: not the profile build')
            base = snap.modules['game.dll']['base']
            heap = Heap(snap)
            root = heap.ptr(base + 0x346BF98)
            table = heap.ptr(root + 0xF12BA8) if root else None
            loaded = heap.read(table, GORE_INDEX_ROWS * 16 + GORE_RECORDS * GORE_RECORD) if table else None
            records_equal = loaded is not None and all(loaded[GORE_INDEX_ROWS * 16 + i * GORE_RECORD:
                GORE_INDEX_ROWS * 16 + (i + 1) * GORE_RECORD] == gore.records[i] for i in range(GORE_RECORDS))
            owners = {}
            if loaded is not None:
                for row in range(GORE_INDEX_ROWS):
                    resource, record, _ = struct.unpack_from('<QII', loaded, row * 16)
                    if resource:
                        owners[resource] = record
            index_equal = owners == {r: rec for r, (rec, _) in gore.owners.items()}
            manager = heap.ptr(base + 0x33264D0)
            live = heap.u32(manager + 0x156D90) if manager else None
            capacity = heap.u32(manager + 0x156D88) if manager else None
            descriptors = heap.ptr(manager + 0x156DB8) if manager else None
            census = Counter()
            for i in range(live or 0):
                descriptor = heap.ptr(descriptors + 8 * i)
                raw = descriptor and heap.read(descriptor, 8)
                resource = struct.unpack('<Q', raw)[0] if raw else 0
                census[names.paths.get(resource) or hexid(resource)] += 1
            out.append({'snapshot': name, 'gameDllBase': f'0x{base:X}',
                'goreTableLoadedEqualsDatalibrary': {'indexOwners': index_equal, 'allRecords': records_equal},
                'goreManager': {'liveInstances': live, 'capacity': capacity,
                    'instancesByResource': [[p, n] for p, n in census.most_common()]}})
        finally:
            snap.close()
    if not all(s['goreTableLoadedEqualsDatalibrary']['indexOwners'] and
            s['goreTableLoadedEqualsDatalibrary']['allRecords'] for s in out):
        raise ValueError('loaded GoreComponentData differs from the datalibrary')
    return out


# -- report ----------------------------------------------------------------------------------------------------------
def comparison_table(rows):
    by_name = {r['className']: r for r in rows}
    table = []
    for label, cls, basis in COMPARISON:
        row = by_name.get(cls)
        if row is None:
            raise ValueError(f'comparison class missing: {cls}')
        gore = row['gore']
        whole = gore and gore['wholeBodyGroup']
        table.append({'label': label, 'className': cls, 'basis': basis, 'faction': row['faction'],
            'mainHealth': row['mainHealth'], 'unitSize': row['unitSize'], 'verdict': row['verdict'],
            'wholeBodyThreshold': row['gore'] and row['gore']['wholeBodyThreshold'],
            'wholeBodyActors': whole['actors'] if whole else None,
            'wholeBodyThresholdToMainHealth': row.get('wholeBodyThresholdToMainHealth'),
            'limbThresholds': gore['limbThresholds']['enabled'] if gore else None,
            'fallbackImpulseScale': gore['entity']['fallbackImpulseScale'] if gore else None,
            'goreRecord': gore['recordIndex'] if gore else None,
            'goreOwnerCount': gore['ownerCount'] if gore else None,
            'zonesCappedByZoneHealth': row['zonesCappedByZoneHealth']})
    return table


def build():
    names = Names()
    library = build_view.TypeLibrary((build_profile.datalibrary() / 'dl_library.dl_typelib').read_bytes())
    layout = check_layout(library)
    saved = build_view.COMPONENTS
    build_view.COMPONENTS = ('HealthComponentData', 'GoreComponentData')
    try:
        view = build_view.from_datalibrary(build_profile.datalibrary(), {})
    finally:
        build_view.COMPONENTS = saved
    if view.build['entitiesSha256'] != build_profile.ENTITY_SHA256 or \
            view.build['typelibSha256'] != build_profile.TYPELIB_SHA256:
        raise ValueError('pinned datalibrary changed')

    snap = snapshot_image.Snapshot(build_profile.SNAPSHOT)
    try:
        if snap.game_dll_sha256.upper() != PROFILE_DLL_SHA.upper():
            raise ValueError('reference snapshot game.dll is not the profile build')
        _, data = snap.module_image('game.dll')
    finally:
        snap.close()
    image = Image(data)
    code = {group: [image.pin(*pin) for pin in pins] for group, pins in PINS.items()}
    if any(abs(f32(data, rva) - value) > 1e-6 for rva, value in CONSTANTS.items()):
        raise ValueError('gore constants changed')
    isolation = evaluator_isolation(image)
    census = settings_references(image, layout['healthLabels'])

    rows = class_rows(view, names)
    verdicts = Counter((r['faction'], r['verdict']) for r in rows)
    whole_body = sorted(((r['className'], r['gore']['wholeBodyThreshold'], r['mainHealth']) for r in rows
        if r['verdict'] in ('WHOLE_BODY_GIB', 'WHOLE_BODY_DISABLED')), key=lambda x: x[0])
    ratios = sorted({r['wholeBodyThresholdToMainHealth'] for r in rows if 'wholeBodyThresholdToMainHealth' in r})
    table = comparison_table(rows)
    expect = {t['className']: t['wholeBodyThreshold'] for t in table}
    if (expect['scavenger_tier_1'], expect['hunter_tier_1'], expect['warrior_tier_1'], expect['warrior_plus'],
            expect['charger'], expect['strider'], expect['soldier']) != (400, 500, 750, -1, None, None, None):
        raise ValueError('whole-body thresholds changed; update the answer text')
    deltas = health_deltas(view)
    if deltas['entityDeltasTouchingGore']:
        raise ValueError('an entity delta now touches GoreComponentData')
    heap = snapshot_evidence(view, names)

    return {
        'schemaVersion': 1,
        'question': ('What makes an enemy instantly burst / gib ("splootch") on a sufficiently large hit, especially '
            'Terminids? Per-enemy threshold, overkill, ratio to max health, zone threshold, gib/dismember threshold, '
            'explosion force, a flag, or a native decision over several values?'),
        'source': {'build': build_profile.BUILD_ID, 'datalibrary': 'build profile ' + build_profile.BUILD_ID,
            'entitiesSha256': build_profile.ENTITY_SHA256, 'typelibSha256': build_profile.TYPELIB_SHA256,
            'referenceSnapshot': build_profile.SNAPSHOT_NAME, 'gameDllSha256': PROFILE_DLL_SHA,
            'unpackedImageSha256': sha(data), 'missionSnapshots': list(MISSION_SNAPSHOTS),
            'classes': ENEMY_RESEARCH.name, 'writes': 0},
        'answer': {
            'summary': ('A native decision with one configurable gate value per body-part group: the GoreComponent '
                '(not the HealthComponent) of each class holds up to 38 gore groups, each owning physics actors and '
                'a destroy threshold in damage units. When a hit kills the enemy or kills one of its damage zones, '
                'HealthManager::ApplyDamage hands that hit\'s final damage to the gore evaluator, which picks the '
                'group owning the hit actor (or the class\'s whole-body group when no group owns the actor, when the '
                'hit reports no actor, or when Electricity killed it), doubles the damage for '
                'Electricity, and destroys the group when damage >= threshold. A destroyed whole-body group is the '
                'splootch. It is an absolute per-class, per-group damage threshold on the killing hit: not overkill, '
                'not a ratio to max health, not explosion force (push force only scales the gib impulse).'),
            'formula': ('splootch = gore(class) and (diedThisHit or zoneDiedThisHit) and kind not in {Drown(8), '
                'none(10)} and hitClass not in {0, 5} and T >= 0 and D >= T, where G = the group owning the '
                'translated hit actor, or the first wholeBody group (+866) if none owns it / no actor / '
                'Electricity kill; T = G.destroyThreshold (+0); D = the hit\'s final damage (post armor factor, '
                'zone damage multiplier, durable mix, relation and element multipliers, minus the child-zone share, '
                'capped at the zone\'s remaining health + constitution when the zone has +340 set) x 2 if the '
                'element is Electricity. G.wholeBody -> whole-body destruction (0x908220, the splootch); otherwise '
                '-> sever G (0x903C70). Below T but D >= G.secondaryThreshold (+4) and hitClass != 9 -> the '
                'non-destroying gore action (0x904860). Gib impulse = push force x hit direction x G.impulseScale '
                '(+8) (or GoreComponent +33472 when no group was selected; x4 accumulator for explosions).'),
            'confidence': {
                'thresholdComparison': 'CONFIRMED (code): damage >= GoreGroupInfo +0 with +0 >= 0 gates group '
                    'destruction (0x905E39-0x905E52).',
                'gating': 'CONFIRMED (code): only on a hit that killed the entity or a damage zone; never Drown.',
                'wholeBodySelection': 'CONFIRMED (code): first group with +866 set when the actor has no group, '
                    'there is no actor, or an Electricity kill.',
                'electricityDoubles': 'CONFIRMED (code) that element 2 doubles the compared damage; element 2 = '
                    'Electricity is filediver\'s enum naming (STRONG).',
                'definitionIsSharedAndLive': 'CONFIRMED: read at hit time from the shared loaded GoreComponentData '
                    'table by resource hash (0x508590, no per-instance copy); the loaded table equals the datalibrary '
                    'in three mission snapshots.',
                'wholeBodyDestructionIsTheVisibleSplootch': 'STRONG: the +866 path spawns the GoreComponent '
                    'whole-body effect (+33440) at the body pose and runs 0x908220; not observed live.',
                'limbPathIsSever': 'STRONG: 0x903C70 marks the actor destroyed (one-shot) and processes links / '
                    'gib entities; visual not observed live.',
                'hitClassMeaning': 'PLAUSIBLE: event +0x5C is the caller\'s hit class (explosions pass 1); the values '
                    '0/5/9 match HitEffectDamageType None / IncendiarySmall / Blunt but the field is not proven to '
                    'be that enum.',
                'multiplayer': 'UNKNOWN: the host sends message 0x0E57D84B with the gore inputs and four other '
                    'callers run the evaluator; which peer decides what each player sees is not proven.',
            },
            'hypotheses': {
                'perEnemyDamageThreshold': 'YES, refined: per class AND per gore group (GoreGroupInfo +0), absolute '
                    'damage units. The whole-body group carries the splootch threshold.',
                'overkillThreshold': 'NO: the evaluator compares the hit\'s full final damage (xmm9 at 0x923D1A), '
                    'never damage minus remaining health.',
                'ratioOfHitToMaxHealth': 'NO: no health value enters the comparison; whole-body thresholds are 3x to '
                    '6.7x main health across classes (' + ', '.join(str(r) for r in ratios) + ').',
                'damageZoneSpecificThreshold': 'PARTLY: gore groups are keyed by physics actors like zones, but live '
                    'in the GoreComponent, not DamageableZoneInfo. The zone only shapes the damage (multiplier, '
                    'child split, cap +340) and the gate (zone death).',
                'gibDismemberThreshold': 'YES: GoreGroupInfo +0 (hidden name 10 characters) is the destroy '
                    'threshold of a group; on the whole-body group it is the splootch threshold.',
                'explosionForceThreshold': 'NO: push force (DamageInfo +0x24 -> event +0x34) only scales the gib '
                    'impulse (+8 / +33472). Explosions splootch because they deal large damage to the body; their '
                    'push force is never compared.',
                'statusOrFlag': 'PARTLY: the +866 whole-body flag selects the group; a negative threshold disables '
                    'it (Hive Guard); hit class 0/5 and Drown suppress gore.',
                'nativeDecisionOnMultipleValues': 'YES: see formula. The only per-class configurable input is the '
                    'group threshold (plus which group is whole-body); the rest is the hit.',
            },
        },
        'layout': {k: v for k, v in layout.items() if k != 'healthLabels'},
        'healthComponentCandidates': [{'scope': s, 'offset': o, 'storage': st, 'nameLength': n, 'label': label,
            'finding': finding} for s, o, st, n, label, finding in HEALTH_CANDIDATES],
        'code': code,
        'constants': {f'0x{rva:X}': value for rva, value in CONSTANTS.items()},
        'evaluatorIsolation': isolation,
        'applyDamageHealthReferences': census,
        'entityDeltas': deltas,
        'snapshots': heap,
        'memberClusters': member_clusters(view),
        'summary': {'classes': len(rows),
            'byFactionAndVerdict': [[f, v, n] for (f, v), n in sorted(verdicts.items())],
            'wholeBodyGroups': [{'className': c, 'threshold': t, 'mainHealth': h} for c, t, h in whole_body],
            'wholeBodyThresholdToMainHealthRatios': ratios},
        'comparison': table,
        'classes': rows,
        'exposure': {
            'decision': 'EXPOSED',
            'field': 'hd2.fields.gore.whole_body_gib_damage',
            'target': 'hd2.enemy(name) (path entity)',
            'semantics': ('Final damage (after armor, the zone multiplier, the durable mix, element and relation '
                'multipliers and the zone cap; Electricity counts double) of a hit that kills the enemy, or kills the '
                'damage zone it lands on, at or above which the enemy bursts into gibs. -1 disables bursting. '
                'Units: damage points. f32.'),
            'valueRule': '-1, or 0 < value <= 100000 (the largest vanilla DamageInfo damage is 10000)',
            'backing': ('the GoreComponentData record the class owns alone; offset = whole-body group index '
                'x 872 + 0; f32'),
            'eligible': ('Terminid classes with an enabled whole-body group, plus warrior_plus (Hive Guard, -1): '
                '23 classes'),
            'guards': ['GoreComponentData record index, index row and unique owner (re-proven live)',
                'target offset = whole-body group index x 872', 'group actors[8] (+340) unchanged',
                'group flags +864..+867 unchanged (+866 = 1)', 'every earlier group +866 = 0',
                'expected current value (third-party value = CONFLICT)'],
            'lifecycle': ('ACTIVE_DIRECT: read on every evaluated hit from the shared loaded table; affects enemies '
                'already alive'),
            'acknowledgement': 'allow_unverified_effect until the live test below passes',
            'runtime': ['schemas/current.lua (GoreComponentData, via scripts/import_fixtures.py)',
                'scripts/migration/build_view.py (GoreComponentData in COMPONENTS, extractor version 6)',
                'domains/enemy_writes.lua', 'scripts/generate_enemy_authoring.py', 'schemas/enemy_fields.json'],
            'validation': 'validation/enemy-gib-threshold-snapshot.json (scripts/validate_enemy_gib_threshold_snapshot.py)',
            'liveTestProject': 'examples/projects/GibThresholdTest',
            'notAuthored': ['per-limb sever thresholds (group identity per named limb is not cleanly provable)',
                'secondary (gored) thresholds', 'impulse scales'],
        },
        'liveTest': {
            'setup': ('Host a solo Terminid mission with Warriors (warrior_tier_1, 250 HP; whole-body threshold 750). '
                'Body hits only: the default zone (armor 1, durable share 0.2, Normal multiplier) has no cap. '
                'Predicted D for a killing body hit (weapon research, durable mix (1-0.2) x standard + 0.2 x durable, '
                'AP above armor -> factor 1): APW-1 = 405, EAT-17 projectile = 2000, ARC-3 = 220 raw x 2 '
                '(Electricity, DamageInfo element 2) = 440 (first arc target; the arc factor path is unverified). '
                'Finish wounded Warriors so the measured shot is the killing hit.'),
            'steps': [
                'Vanilla (750): APW-1 kill -> intact corpse; EAT-17 body kill -> burst; ARC-3 kill -> intact.',
                'Write 400: APW-1 kill (405) -> burst; ARC-3 kill (440) -> burst.',
                'Write 430: APW-1 kill (405) -> intact; ARC-3 kill (440) -> burst. Proves the Electricity doubling.',
                'Write 450: APW-1 -> intact; ARC-3 -> intact; EAT-17 -> burst. Proves an exact damage boundary.',
                'Write -1: EAT-17 and a 500 kg kill -> intact corpse (limbs may still sever by their own groups).',
                'Warriors alive before each write must follow the new value (shared table, read per hit).',
                'Controls in the same mission, untouched: Scavenger (400; durable 0) bursts on an APW-1 kill (450); Hive '
                'Guard (-1) never bursts.',
                'Revert to 750: vanilla behaviour returns without a restart.',
            ],
            'pass': ('Bursts appear exactly when the predicted killing-hit damage reaches the written value; if the '
                'ARC-3 boundary differs, record the observed boundary (the arc damage path, not the gate, is then '
                'the unknown).'),
        },
        'unproven': [
            'The visible result of 0x908220 / the +33440 effect is inferred from code; not yet seen live.',
            'Which physics actor a body hit reports (the whole-body groups list "boss"); hits on actors no group '
            'owns use the whole-body group anyway, so the threshold applies to them as well.',
            'event +0x5C / hit +0xC meaning (hit class): set by each hit builder caller; not proven to be '
            'HitEffectDamageType.',
            'Multiplayer: who evaluates gore for clients (message 0x0E57D84B and the other evaluator callers).',
            'A whole-body group can be selected on a zone death without the entity dying (no group owns the actor); '
            'whether 0x908220 then bursts a living enemy was not traced.',
            'GoreComponent +33476 / +33480 / +33484 and GoreGroupInfo +864 / +865 / +867 semantics.',
            'Whether explosion hits report a hit actor (event +0x0C; -1 means none) was not traced; body actors '
            'resolve to the whole-body group either way.',
            'Spewer acid bursts and Bile Titan deaths are scripted death explosions (DamageInfo AcidDeath rows, '
            'abilities), not this gore path: those classes have no whole-body gore group.',
        ],
    }


def main():
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(report['answer']['summary'])
    for row in report['comparison']:
        print(f"{row['label']:<28} {row['className']:<20} hp {row['mainHealth']:>5} {row['verdict']:<20} "
            f"whole-body {row['wholeBodyThreshold']} limbs {row['limbThresholds']}")


if __name__ == '__main__':
    main()
