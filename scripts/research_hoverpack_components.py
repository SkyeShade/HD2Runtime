"""LIFT-850 Jump Pack, LIFT-860 Hover Pack and related movement components tied to native code (research only).

Read-only. Nothing here writes game memory, runs in game, or edits the public API. Inputs: the pinned datalibrary
(scan.tables), the game.dll image from a retained snapshot (scan.xref), the retained snapshots, the entity-delta
table and the earlier equipment research (research/equipment-coverage-F5FEE03DCFDB.json).

Proven on build F5FEE03DCFDB (details, pins and per-member evidence in the JSON):

1. Owner and lifecycle. JumppackComponentData (JumppackComponent, 280 bytes, 4 records, 6 index rows) is owned by
   the Hover Pack (record 0), the Jump Pack (1) and the Dark Fluid vessel backpack (2); record 3 has no owner. Enemy
   jump-pack units (cyborg soldier/berserker) do not own it: they leap through Ability + Locomotion. The jumppack
   manager (game+0x3326BB8) resolves records through 0x50D830: a per-instance resolved copy (+0xA0, 0x118 stride)
   only for entities in its resolved map, else the loaded entity-file block at [entity manager +0xF12CB8]. That
   block equals the pinned file in the retained snapshots and no entity delta patches the component, so the flight
   code reads the shared type record live.
2. Activation (0x9B3420): replicated state bytes (+0x50: active, sustain, hover-launch, mode toggle, thrusting);
   +144 set (jump packs) starts the full recharge at once (0x9ED210 sets the cooldown to recharge.time); +72 is the
   activation ability. The hover pack (+144 = 0) instead fills its cooldown while hovering (point 5).
3. Jump flight (0x9B4790, per frame, dt). Launch window = +24 s (or +28 s when the replicated mode toggle, flipped
   by interaction 0x13 in 0x880440, is set) from the 76-byte per-instance state (+0x48). During the window, with
   t = elapsed / window, the velocity gains +0 x (1 - t^2) x dt, split between the horizontal travel direction
   (weight +32) and the unit's up axis (weight 1 - +32); downward velocity is cancelled first. A sustain phase may
   follow (0x9B4110: launch elapsed > +48 s, speed >= +52 m/s, a forward probe clear): +36 x (1 - t^2) over +40 s,
   horizontal weight +44, each axis change limited to |v| x dt x 2.5; it ends when speed drops below +56 m/s. Air
   control: input-direction acceleration +60 m/s^2 while horizontal speed < +176.x.
4. Take-off hop (0xA63790 -> 0xA63F20 -> 0x5A3E40): when the pack activates from the ground and +152 is 0, the
   character gets an upward impulse +212 m/s (+216 for stance state >= 4; result clamped to [0.75, 1.1] x the
   impulse) and, if moving, a forward impulse +208 m/s. With +152 set (hover pack) ability +80 plays instead.
5. Hover flight (same function, +153 set): target velocity = input x (+176.x horizontal, +176.y vertical); the
   velocity approaches it with bounded acceleration: horizontal lerp(+160.x, +160.y) and vertical lerp(+168,
   +172), each lerped by speed over +184/+188 and +192/+196 (vertical 9.8 -> 0 m/s^2 between 0 and 8 m/s). Hover
   "fuel" is the recharge meter: each frame the cooldown grows by (1 + lerp(+200, +204 by vertical speed)) x dt
   (0x9ED5D0, capped at recharge.time), and with +145 set the pack deactivates when the meter is exhausted. +154
   makes the hover pack also run the jump launch/sustain physics; +156 (hover.duration, 6 s) is compared with the
   character movement record +0x64 to gate the ascend input.
6. Presentation only: ready/not-ready indicator colours +120/+132, progress-bar material variable +116, ability
   ids +76..+108, surface effect +68, the hover pack's visual sway/spin block +220..+276 (animation variables
   translate_x/y, spin, hover_x/y).
7. Cross-family: DisplacementComponent (Warp Pack), HoverComponent (8 enemy flyers, wwise RTPCs hover_height /
   hover_speed_*), ThrusterGroupComponent (27 dropships/gunships/missiles), FakeGravityMotionComponent and
   LevitationAreaComponent share no struct type with JumppackComponent (only CApiVector2/3).

  py scripts/research_hoverpack_components.py          # write research/hoverpack-components-F5FEE03DCFDB.json + md
  py scripts/research_hoverpack_components.py --check  # fail if the committed outputs are stale

Requires capstone and numpy, the pinned datalibrary and the retained snapshots.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from scan import compare, report, tables  # noqa: E402
from scan.tables import decode, hexid  # noqa: E402
from research_railgun_charge import (canonical, check_pins, delta_targets, golib_leads, manager_map,  # noqa: E402
    pin_refs, snapshot_tables)

OUTPUT = ROOT / 'research/hoverpack-components-F5FEE03DCFDB.json'
MARKDOWN = ROOT / 'research/docs/hoverpack-components-F5FEE03DCFDB.md'
COMPONENT = 'JumppackComponentData'
RECORD_TYPE = 'JumppackComponent'
RECORD_SIZE = 280
LOADED_TABLE_OFFSET = 0xF12CB8
MANAGERS = {'jumppack': 0x3326BB8, 'hover': 0x33266E8, 'displacement': 0x3326AC8, 'recharge': 0x3326768,
    'thruster_group': 0x3326DB0, 'fake_gravity_motion': 0x3326DC8, 'levitation_area': 0x3326C80}
RELATED = ['DisplacementComponentData', 'HoverComponentData', 'ThrusterGroupComponentData',
    'FakeGravityMotionComponentData', 'LevitationAreaComponentData']
LABELS = {'hover_backpack': 'LIFT-860 Hover Pack', 'jumppack_backpack': 'LIFT-850 Jump Pack'}

PINS = [
    # manager, resolver, lifecycle
    (0x9B83AA, 'lea rdx, [rip', 'the manager names itself JumppackComponent (capacity growth)', 'manager'),
    (0x9B845B, 'imul rdx, rax, 0x118', 'per-instance resolved-copy array: 0x118 = the 280-byte record', 'manager'),
    (0x9B8475, 'mov qword ptr [r14 + 0xa0], rax', '... at manager +0xA0', 'manager'),
    (0x9B8535, 'imul rdx, rax, 0x4c', 'per-instance flight state: 76 bytes (+0x48)', 'manager'),
    (0x50D852, 'mov r11, qword ptr [rip', 'record resolver: the jumppack manager', 'resolver'),
    (0x50D8D2, 'imul rax, rax, 0x118', 'resolved copy when the entity has one ...', 'resolver'),
    (0x50D8D9, 'add rax, qword ptr [r11 + 0xa0]', '... from manager +0xA0', 'resolver'),
    (0x50D8EC, 'jmp 0x50d310', '... else the type record', 'resolver'),
    (0x50D31F, 'mov r10, qword ptr [rax + 0xf12cb8]', 'type record: the loaded entity-table block', 'resolver'),
    (0x50D38C, 'imul rax, rcx, 0x118', 'record index x 280 ...', 'resolver'),
    (0x50D393, 'add rax, 0x60', '... after the 6 index rows', 'resolver'),
    # activation
    (0x9B3528, 'cmp byte ptr [r13 + 0x99], sil', 'activation: hover-launch flag from +153 ...', 'activation'),
    (0x9B3531, 'cmp byte ptr [r13 + 0x9a], sil', '... and +154', 'activation'),
    (0x9B3684, 'cmp byte ptr [r13 + 0x90], sil', '+144: start the full recharge on activation ...', 'activation'),
    (0x9B3699, 'call 0x9ed210', '... (recharge manager: cooldown = recharge.time)', 'activation'),
    (0x9B369E, 'mov r8d, dword ptr [r13 + 0x48]', '+72: activation ability', 'activation'),
    (0x9B395B, 'movsd xmm0, qword ptr [r13 + 8]', '+8 (vector) and ...', 'activation'),
    (0x9B396C, 'movss xmm3, dword ptr [r13 + 4]', '... +4 (scalar) passed to the wielder (0x785020)', 'activation'),
    (0x9B397C, 'call 0x785020', 'weapon-wielder call with +4/+8 (meaning not decoded)', 'activation'),
    (0x880582, 'cmp byte ptr [rdx + rcx + 3], 0', 'interaction 0x13 toggles replicated flag 3 ...', 'activation'),
    (0x88059D, 'mov edx, 0x7da923b', '... (network key 0x07DA923B)', 'activation'),
    # recharge manager
    (0x9ED2A0, 'mov eax, dword ptr [rax]', 'recharge.time ...', 'recharge'),
    (0x9ED2A2, 'mov dword ptr [rcx + rdi*4], eax', '... becomes the cooldown (start recharge)', 'recharge'),
    (0x9ED659, 'addss xmm2, dword ptr [rbx + rdi*4]', 'hover fuel: cooldown + amount ...', 'recharge'),
    (0x9ED65E, 'minss xmm2, dword ptr [rax]', '... capped at recharge.time', 'recharge'),
    (0x9ED716, 'divss xmm1, dword ptr [rax]', 'ready fraction = 1 - cooldown / recharge.time', 'recharge'),
    # flight: per-instance timers (0x9B5EC0)
    (0x9B6530, 'mov word ptr [rsi], 1', 'activation seen: launch latch', 'timers'),
    (0x9B6540, 'movss xmm0, dword ptr [r15 + 0x1c]', '+28: launch window when the mode toggle is set ...', 'timers'),
    (0x9B6548, 'movss xmm0, dword ptr [r15 + 0x18]', '... +24: launch window ...', 'timers'),
    (0x9B654E, 'movss dword ptr [rsi + 0xc], xmm0', '... into state +0x0C', 'timers'),
    (0x9B655D, 'mov r8d, dword ptr [r15 + 0x54]', '+84: launch ability', 'timers'),
    (0x9B6584, 'mov r8d, dword ptr [r15 + 0x58]', '+88: launch event', 'timers'),
    (0x9B65BC, 'movss dword ptr [rsi + 4], xmm1', 'launch elapsed += dt (state +0x04)', 'timers'),
    (0x9B65CE, 'addss xmm0, dword ptr [rsi + 8]', 'sustain elapsed += dt (state +0x08)', 'timers'),
    (0x9B6634, 'mov r8d, dword ptr [r15 + 0x60]', '+96: ability when the launch window ends', 'timers'),
    (0x9B6668, 'mov r8d, dword ptr [r15 + 0x5c]', '+92: ability when the sustain phase starts', 'timers'),
    (0x9B64B5, 'mov r8d, dword ptr [r15 + 0x44]', '+68: surface impact effect', 'presentation'),
    # flight physics (0x9B4790)
    (0x9B4B93, 'cmp byte ptr [r12 + 0x99], r14b', '+153: hover flight model', 'hover'),
    (0x9B4CB2, 'movss xmm0, dword ptr [r12 + 0x9c]', '+156 hover.duration ...', 'hover'),
    (0x9B4CCE, 'comiss xmm0, dword ptr [r13 + 0x64]', '... against the movement record +0x64', 'hover'),
    (0x9B4E25, 'movss xmm5, dword ptr [r12 + 0xb0]', '+176.x: horizontal target speed', 'hover'),
    (0x9B4E47, 'movss xmm13, dword ptr [r12 + 0xb4]', '+180: vertical target speed (second max-speed element)', 'hover'),
    (0x9B4E51, 'movss xmm11, dword ptr [r12 + 0xa0]', '+160: horizontal acceleration (low speed)', 'hover'),
    (0x9B4F14, 'movss xmm3, dword ptr [r12 + 0xa4]', '+164: horizontal acceleration (high speed)', 'hover'),
    (0x9B4E2F, 'movss xmm10, dword ptr [r12 + 0xa8]', '+168: vertical acceleration (low speed)', 'hover'),
    (0x9B4E39, 'movss xmm0, dword ptr [r12 + 0xac]', '+172: vertical acceleration (high speed)', 'hover'),
    (0x9B4F26, 'movss xmm1, dword ptr [r12 + 0xb8]', '+184: horizontal speed range start', 'hover'),
    (0x9B4F34, 'movss xmm0, dword ptr [r12 + 0xbc]', '+188: horizontal speed range end', 'hover'),
    (0x9B4E72, 'movss xmm1, dword ptr [r12 + 0xc0]', '+192: vertical speed range start', 'hover'),
    (0x9B4E8A, 'movss xmm0, dword ptr [r12 + 0xc4]', '+196: vertical speed range end', 'hover'),
    (0x9B4FAD, 'movss xmm1, dword ptr [r12 + 0xb4]', 'no vertical acceleration at the vertical target speed', 'hover'),
    (0x9B50D3, 'subss xmm5, dword ptr [r12 + 0xc8]', 'fuel rate: +204 - +200 ...', 'hover'),
    (0x9B50BF, 'movss xmm5, dword ptr [r12 + 0xcc]', '... (+204) ...', 'hover'),
    (0x9B5116, 'addss xmm2, dword ptr [r12 + 0xc8]', '... lerp by vertical speed, + 1 ...', 'hover'),
    (0x9B5186, 'movss dword ptr [r13], xmm0', 'velocity x', 'hover'),
    (0x9B5196, 'movss dword ptr [r13 + 8], xmm1', 'velocity z', 'hover'),
    (0x9B519C, 'mulss xmm2, dword ptr [rax + 4]', '... x dt ...', 'hover'),
    (0x9B51A4, 'call 0x9ed5d0', '... added to the recharge cooldown (hover fuel)', 'hover'),
    (0x9B529E, 'cmp byte ptr [r12 + 0x91], r14b', '+145: deactivate when the meter is exhausted', 'hover'),
    (0x9B52AB, 'call 0x9ed680', 'ready fraction', 'hover'),
    (0x9B5319, 'cmp byte ptr [r12 + 0x9a], r14b', '+154: the hover pack also runs the jump phases', 'hover'),
    (0x9B53DA, 'movss xmm1, dword ptr [rdx + 4]', 'launch: elapsed ...', 'jump'),
    (0x9B53DF, 'movss xmm0, dword ptr [rdx + 0xc]', '... / window', 'jump'),
    (0x9B53F5, 'movss xmm11, dword ptr [r12 + 0x20]', '+32: horizontal share of the launch thrust', 'jump'),
    (0x9B5437, 'mulss xmm10, dword ptr [r12]', '+0 x (1 - t^2): launch thrust', 'jump'),
    (0x9B55AE, 'maxss xmm15, xmm7', 'launch: downward velocity cancelled', 'jump'),
    (0x9B55B3, 'movss dword ptr [rbx], xmm1', 'launch: velocity x += ...', 'jump'),
    (0x9B55E3, 'movss dword ptr [rbx + 8], xmm1', 'launch: velocity z += ...', 'jump'),
    (0x9B55FD, 'call 0x9b4110', 'sustain gate', 'jump'),
    (0x9B5657, 'movss xmm0, dword ptr [r12 + 0x28]', '+40: sustain duration', 'jump'),
    (0x9B5674, 'movss xmm10, dword ptr [r12 + 0x2c]', '+44: horizontal share of the sustain thrust', 'jump'),
    (0x9B56AB, 'mulss xmm9, dword ptr [r12 + 0x24]', '+36 x (1 - t^2): sustain thrust', 'jump'),
    (0x9B56E1, 'movss xmm1, dword ptr [r12 + 0x38]', '+56: sustain ends below this speed', 'jump'),
    (0x9B56FE, 'call 0x9b3420', '... (deactivate)', 'jump'),
    (0x9B57A6, 'movsd xmm2, qword ptr [rip', 'sustain: per-axis change limited to |v| x dt x 2.5', 'jump'),
    (0x9B59BA, 'movss xmm1, dword ptr [r12 + 0xb0]', 'air control: only below +176.x horizontal speed', 'jump'),
    (0x9B5C30, 'movss xmm0, dword ptr [r12 + 0x3c]', '+60: air-control acceleration', 'jump'),
    (0x9B4221, 'cmp byte ptr [rax + 0x9a], 0', 'sustain gate: active or +154', 'jump'),
    (0x9B4243, 'comiss xmm0, dword ptr [r15 + 0x30]', '+48: earliest sustain start (launch elapsed)', 'jump'),
    (0x9B437F, 'movss xmm0, dword ptr [r15 + 0x34]', '+52: minimum speed to start the sustain', 'jump'),
    # take-off hop
    (0xA63BD3, 'movzx esi, byte ptr [rax + 0x99]', 'take-off: hover flight model?', 'takeoff'),
    (0xA63E4A, 'cmp byte ptr [rdi + 0x98], r14b', '+152: skip the take-off hop ...', 'takeoff'),
    (0xA63EB9, 'call 0xa63f20', '... else the hop', 'takeoff'),
    (0xA63EC0, 'mov r8d, dword ptr [rdi + 0x50]', '+80: ability instead of the hop', 'takeoff'),
    (0xA64429, 'movss xmm7, dword ptr [rdi + 0xd8]', '+216: upward impulse, stance state >= 4', 'takeoff'),
    (0xA6455A, 'movss xmm7, dword ptr [rdi + 0xd4]', '+212: upward impulse', 'takeoff'),
    (0xA645CD, 'movss xmm8, dword ptr [rdi + 0xd0]', '+208: forward impulse when moving', 'takeoff'),
    (0xA645F2, 'call 0x5a3e40', 'character impulse', 'takeoff'),
    (0x5A3EF6, 'mulss xmm1, dword ptr [rip', 'impulse: vz >= 0.75 x up ...', 'takeoff'),
    (0x5A3F20, 'mulss xmm2, dword ptr [rip', '... and <= 1.1 x up', 'takeoff'),
    (0x5A401C, 'mulss xmm0, xmm9', 'forward impulse along the horizontal velocity', 'takeoff'),
    # presentation and other readers
    (0x9B45C0, 'mov r8d, dword ptr [r15 + 0x4c]', '+76: ability when the recharge is ready', 'presentation'),
    (0x9B45E6, 'cmp byte ptr [r15 + 0x90], 0', 'indicator colour choice (+144, active, ready) ...', 'presentation'),
    (0x9B460F, 'movsd xmm0, qword ptr [rax + r15]', '... +120 (ready) or +132 (not ready)', 'presentation'),
    (0x9B46FE, 'mov edx, dword ptr [r15 + 0x74]', '+116: material variable = recharge fraction', 'presentation'),
    (0x9B6E6F, 'mulss xmm7, dword ptr [r15 + 0x104]', '+260: visual sway spring', 'presentation'),
    (0x9B6EB0, 'comiss xmm0, dword ptr [r15 + 0xfc]', '+252: visual sway limit', 'presentation'),
    (0x9B6EB8, 'movss xmm0, dword ptr [r15 + 0x100]', '+256: visual sway scale', 'presentation'),
    (0x9B70AF, 'mulss xmm1, dword ptr [r15 + 0x114]', '+276: animation range (second element)', 'presentation'),
    (0x9B70BC, 'mulss xmm7, dword ptr [r15 + 0x110]', '+272: animation range', 'presentation'),
    (0x9B70E7, 'mov r8d, dword ptr [r15 + 0xe8]', '+232: animation variable (translate_x)', 'presentation'),
    (0x9B7104, 'mov r8d, dword ptr [r15 + 0xec]', '+236: animation variable (translate_y)', 'presentation'),
    (0x9B711E, 'mov r8d, dword ptr [r15 + 0xf4]', '+244: animation variable (hover_x)', 'presentation'),
    (0x9B713A, 'mov r8d, dword ptr [r15 + 0xf8]', '+248: animation variable (hover_y)', 'presentation'),
    (0x9B728B, 'mov r8d, dword ptr [r15 + 0xf0]', '+240: animation variable (spin)', 'presentation'),
    (0x9B7292, 'movss xmm0, dword ptr [r15 + 0xe4]', '+228: spin (third vector element)', 'presentation'),
    (0x830FDF, 'mulss xmm2, dword ptr [rax + 0x14]', '+20 scales two avatar movement values (0x68C0E0) ...', 'other'),
    (0x830FE4, 'mulss xmm5, dword ptr [rax + 0x14]', '... while the wearer\'s jump-pack flags are set', 'other'),
    (0x9B5DC9, 'cmp byte ptr [rax + 0x9b], sil', '+155: gate in 0x9B5D00 (meaning not decoded)', 'other'),
    (0x9B7601, 'movzx eax, byte ptr [rax + 0x40]', '+64: getter 0x9B7560 (callers not traced)', 'other'),
    # NPC hover audio
    (0x9626CA, 'lea rdx, [rip', 'HoverComponent: wwise RTPC hover_height', 'npc_hover'),
    (0x96270B, 'lea rdx, [rip', 'HoverComponent: wwise RTPC hover_speed_vertical', 'npc_hover'),
    (0x962780, 'lea rdx, [rip', 'HoverComponent: wwise RTPC hover_speed_horizontal', 'npc_hover'),
]
RIP_TARGETS = {0x9B83AA: 0x224D600, 0x50D852: 0x3326BB8, 0x9626CA: 0x224D0A0, 0x96270B: 0x224D0F8,
    0x962780: 0x224D0E0}

H = 'hover'
J = 'jump'
FIELDS = {
    '0': dict(nativeName='launch_thrust', nameSource='length_fitted_invented', unit='m/s^2', kind='gameplay',
        semantic='launch thrust: peak acceleration during the launch window, tapering as (1 - t^2); split between '
                 'travel direction (+32) and the up axis (1 - +32); downward velocity cancelled first',
        code=['jump'], existing='hd2.fields.jump.vertical_launch_velocity'),
    '4': dict(nativeName=None, unit=None, kind='unknown', semantic='scalar passed with +8 to a weapon-wielder call at '
        'activation (0x785020); meaning not decoded (20 in every record)', code=['activation']),
    '8[0]': dict(nativeName=None, unit=None, kind='unknown', semantic='vector with +4 to 0x785020', code=['activation']),
    '8[1]': dict(nativeName=None, unit=None, kind='unknown', semantic='vector with +4 to 0x785020', code=['activation']),
    '8[2]': dict(nativeName=None, unit=None, kind='unknown', semantic='vector with +4 to 0x785020', code=['activation']),
    '20': dict(nativeName=None, unit='multiplier', kind='unknown', semantic='multiplies two avatar movement values '
        '(manager game+0x3326598 via 0x68C0E0) while the wearer\'s jump-pack flags are set; 1.5 in every record',
        code=['other']),
    '24': dict(nativeName='jump_thrust_time', nameSource='length_fitted_invented', unit='seconds', kind='gameplay',
        semantic='launch window (thrust duration)', code=['timers']),
    '28': dict(nativeName='alt_jump_thrust_duration', nameSource='length_fitted_invented', unit='seconds',
        kind='gameplay', semantic='launch window while the replicated mode toggle (interaction 0x13) is set',
        code=['timers']),
    '32': dict(nativeName='launch_forward_ratio', nameSource='length_fitted_invented', unit='fraction',
        kind='gameplay', semantic='horizontal (travel-direction) share of the launch thrust; 1 - share goes up',
        code=['jump']),
    '36': dict(nativeName='sustain_thrust_force', nameSource='length_fitted_invented', unit='m/s^2',
        kind='gameplay', semantic='sustain-phase thrust peak, tapering as (1 - t^2) over +40', code=['jump']),
    '40': dict(nativeName='sustain_thrust_duration', nameSource='length_fitted_invented', unit='seconds',
        kind='gameplay', semantic='sustain-phase duration', code=['jump']),
    '44': dict(nativeName='sustain_thrust_forward_ratio', nameSource='length_fitted_invented', unit='fraction',
        kind='gameplay', semantic='horizontal share of the sustain thrust', code=['jump']),
    '48': dict(nativeName='sustain_min_launch_elapsed', nameSource='length_fitted_invented', unit='seconds',
        kind='gameplay', semantic='earliest sustain start (launch elapsed must exceed it)', code=['jump']),
    '52': dict(nativeName='minimum_sustain_velocity', nameSource='length_fitted_invented', unit='m/s',
        kind='gameplay', semantic='minimum speed to enter the sustain phase', code=['jump']),
    '56': dict(nativeName='sustain_minimum_speed', nameSource='length_fitted_invented', unit='m/s',
        kind='gameplay', semantic='the sustain phase ends (pack deactivates) below this speed', code=['jump']),
    '60': dict(nativeName='air_control_acceleration', nameSource='length_fitted_invented', unit='m/s^2',
        kind='gameplay', semantic='air-control acceleration along the input direction', code=['jump']),
    '64': dict(nativeName=None, unit='bool', kind='unknown', semantic='u8 returned by getter 0x9B7560 (0 in every '
        'record; callers not traced)', code=['other']),
    '68': dict(nativeName=None, unit='SurfaceImpactType', kind='presentation', semantic='surface impact effect '
        '(ground dust)', code=['presentation']),
    '72': dict(nativeName=None, unit='AbilityId', kind='presentation', semantic='ability at activation',
        code=['activation']),
    '76': dict(nativeName=None, unit='AbilityId', kind='presentation', semantic='ability when the recharge is ready',
        code=['presentation']),
    '80': dict(nativeName=None, unit='AbilityId', kind='presentation', semantic='ability at take-off when +152 '
        'skips the hop', code=['takeoff']),
    '84': dict(nativeName=None, unit='AbilityId', kind='presentation', semantic='ability at launch', code=['timers']),
    '88': dict(nativeName=None, unit='thin_hash', kind='presentation', semantic='launch event (0xFDD750)',
        code=['timers']),
    '92': dict(nativeName=None, unit='AbilityId', kind='presentation', semantic='ability when the sustain starts',
        code=['timers']),
    '96': dict(nativeName=None, unit='AbilityId', kind='presentation', semantic='ability when the launch window '
        'ends', code=['timers']),
    '116': dict(nativeName=None, unit='thin_hash', kind='presentation', semantic='material variable '
        '("progress_bar") set to the recharge fraction', code=['presentation']),
    **{f'120[{i}]': dict(nativeName=None, unit='rgb', kind='presentation', semantic='indicator colour when ready',
        code=['presentation']) for i in range(3)},
    **{f'132[{i}]': dict(nativeName=None, unit='rgb', kind='presentation', semantic='indicator colour when not '
        'ready', code=['presentation']) for i in range(3)},
    '144': dict(nativeName='recharge_on_activate', nameSource='length_fitted_invented', unit='bool',
        kind='gameplay', semantic='start the full recharge at activation (jump packs); 0 = the hover pack fills the '
        'cooldown while hovering', code=['activation', 'presentation']),
    '145': dict(nativeName='deactivate_when_empty', nameSource='length_fitted_invented', unit='bool',
        kind='gameplay', semantic='hover: deactivate when the recharge meter is exhausted', code=['hover']),
    '152': dict(nativeName='skip_takeoff_impulse_on_launch', nameSource='length_fitted_invented', unit='bool',
        kind='gameplay', semantic='skip the take-off hop (+208..+216) and play ability +80 instead',
        code=['takeoff']),
    '153': dict(nativeName='use_hover_mode', nameSource='length_fitted_invented', unit='bool', kind='switch',
        semantic='select the hover flight model', code=['hover', 'activation', 'takeoff']),
    '154': dict(nativeName='hover_jump_launch', nameSource='length_fitted_invented', unit='bool', kind='switch',
        semantic='in hover mode also run the jump launch/sustain phases', code=['hover', 'activation', 'jump']),
    '155': dict(nativeName=None, unit='bool', kind='unknown', semantic='gate in 0x9B5D00 (hover pack 1); meaning '
        'not decoded', code=['other']),
    '156': dict(nativeName=None, unit='seconds', kind='gameplay', semantic='hover duration (published 6 s); '
        'compared with the movement record +0x64 to gate the ascend input; -1 on jump packs', code=['hover'],
        existing='hd2.fields.hover.duration'),
    '160[0].0': dict(nativeName='accelerations', nameSource='length_fitted_invented (array member)', unit='m/s^2',
        kind='gameplay', semantic='hover horizontal acceleration at the low end of the horizontal speed range',
        code=['hover'], array='160'),
    '160[0].4': dict(nativeName='accelerations', nameSource='length_fitted_invented (array member)', unit='m/s^2',
        kind='gameplay', semantic='hover horizontal acceleration at the high end', code=['hover'], array='160'),
    '160[1].0': dict(nativeName='accelerations', nameSource='length_fitted_invented (array member)', unit='m/s^2',
        kind='gameplay', semantic='hover vertical acceleration at the low end of the vertical speed range (9.8)',
        code=['hover'], array='160'),
    '160[1].4': dict(nativeName='accelerations', nameSource='length_fitted_invented (array member)', unit='m/s^2',
        kind='gameplay', semantic='hover vertical acceleration at the high end (0)', code=['hover'], array='160'),
    '176[0]': dict(nativeName='max_speeds', nameSource='length_fitted_invented (vector member)', unit='m/s',
        kind='gameplay', semantic='hover horizontal target speed; jump packs: air control stops above it',
        code=['hover', 'jump'], array='176'),
    '176[1]': dict(nativeName='max_speeds', nameSource='length_fitted_invented (vector member)', unit='m/s',
        kind='gameplay', semantic='hover vertical target speed', code=['hover'], array='176'),
    '184[0].0': dict(nativeName='speed_range_for_acceleration_blending', nameSource='length_fitted_invented',
        unit='m/s', kind='gameplay', semantic='horizontal speed range start', code=['hover'], array='184'),
    '184[0].4': dict(nativeName='speed_range_for_acceleration_blending', nameSource='length_fitted_invented',
        unit='m/s', kind='gameplay', semantic='horizontal speed range end', code=['hover'], array='184'),
    '184[1].0': dict(nativeName='speed_range_for_acceleration_blending', nameSource='length_fitted_invented',
        unit='m/s', kind='gameplay', semantic='vertical speed range start', code=['hover'], array='184'),
    '184[1].4': dict(nativeName='speed_range_for_acceleration_blending', nameSource='length_fitted_invented',
        unit='m/s', kind='gameplay', semantic='vertical speed range end (8)', code=['hover'], array='184'),
    '200[0]': dict(nativeName='drain_rates', nameSource='length_fitted_invented (vector member)',
        unit='s/s', kind='gameplay', semantic='extra recharge fill per hover second at the low end of the '
        'vertical speed range (total rate 1 + value)', code=['hover'], array='200'),
    '200[1]': dict(nativeName='drain_rates', nameSource='length_fitted_invented (vector member)', unit='s/s',
        kind='gameplay', semantic='extra recharge fill per hover second at the high end', code=['hover'],
        array='200'),
    '208': dict(nativeName='takeoff_push_speed', nameSource='length_fitted_invented', unit='m/s', kind='gameplay',
        semantic='take-off forward impulse when moving', code=['takeoff']),
    '212': dict(nativeName='takeoff_speed', nameSource='length_fitted_invented', unit='m/s', kind='gameplay',
        semantic='take-off upward impulse', code=['takeoff']),
    '216': dict(nativeName='alt_takeoff_impulse', nameSource='length_fitted_invented', unit='m/s',
        kind='gameplay', semantic='take-off upward impulse for stance state >= 4', code=['takeoff']),
}
for _path in ('220[0]', '220[1]', '220[2]', '232', '236', '240', '244', '248', '252', '256', '260[0]', '260[1]',
              '260[2]', '272[0]', '272[1]', '100', '108'):
    FIELDS.setdefault(_path, dict(nativeName=None, unit=None, kind='presentation', semantic='hover pack visual '
        'sway/spin animation (animation variables, spring constants)' if not _path.startswith('10') else
        'hover-only ability id pair (not read by the traced flight code)', code=['presentation']))

PROPOSAL = [
    dict(id='hd2.fields.jump.vertical_launch_velocity', status='existing_correct_description', path='0', offset=0,
        storage='f32', unit='m/s^2', type='number', range='>= 0', write='type record, live',
        note='Keep the id (gameplay-proven on the LIFT-850). Correct the description: it is a thrust (acceleration) '
        'integrated over jump.launch_duration with a (1 - t^2) taper, and only (1 - jump.launch_forward_ratio) of '
        'it points up. Average gain ~ 2/3 x value x window (40 x 0.5 -> ~13 m/s, 60% up).'),
    dict(id='hd2.fields.hover.duration', status='existing', path='156', offset=156, storage='f32', unit='seconds',
        type='number', range='> 0 on the hover pack; -1 sentinel on jump packs (do not write there)',
        write='type record, live'),
    dict(id='hd2.fields.jump.launch_duration', status='new', path='24', offset=24, storage='f32', unit='seconds',
        type='number', range='0 < x <= 5 suggested (0 skips the launch phase)', write='type record, live'),
    dict(id='hd2.fields.jump.launch_forward_ratio', status='new', path='32', offset=32, storage='f32',
        unit='fraction', type='number', range='0..1', write='type record, live',
        note='The horizontal-influence member the earlier research could not find.'),
    dict(id='hd2.fields.jump.sustain_thrust', status='new', path='36', offset=36, storage='f32', unit='m/s^2',
        type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.jump.sustain_duration', status='new', path='40', offset=40, storage='f32',
        unit='seconds', type='number', range='>= 0 (0 disables the sustain phase)', write='type record, live'),
    dict(id='hd2.fields.jump.sustain_forward_ratio', status='new', path='44', offset=44, storage='f32',
        unit='fraction', type='number', range='0..1', write='type record, live'),
    dict(id='hd2.fields.jump.sustain_start_delay', status='new', path='48', offset=48, storage='f32',
        unit='seconds', type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.jump.sustain_start_speed', status='new', path='52', offset=52, storage='f32', unit='m/s',
        type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.jump.sustain_cutoff_speed', status='new', path='56', offset=56, storage='f32', unit='m/s',
        type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.jump.air_control_acceleration', status='new', path='60', offset=60, storage='f32',
        unit='m/s^2', type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.jump.air_control_max_speed', status='new', path='176[0]', offset=176, storage='f32',
        unit='m/s', type='number', range='>= 0 (0 = unlimited air control)', write='type record, live',
        note='Same member as hover.max_horizontal_speed: expose it once per pack with the pack\'s meaning.'),
    dict(id='hd2.fields.jump.takeoff_speed', status='new', path='212', offset=212, storage='f32', unit='m/s',
        type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.jump.takeoff_speed_alternate_stance', status='new', path='216', offset=216, storage='f32',
        unit='m/s', type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.jump.takeoff_forward_speed', status='new', path='208', offset=208, storage='f32',
        unit='m/s', type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.hover.max_horizontal_speed', status='new', path='176[0]', offset=176, storage='f32',
        unit='m/s', type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.hover.max_vertical_speed', status='new', path='176[1]', offset=180, storage='f32',
        unit='m/s', type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.hover.horizontal_acceleration', status='new', path='160[0].0+160[0].4', offset=160,
        storage='f32 x2', unit='m/s^2', type='number', range='>= 0', write='type record, live; write both ends '
        'to the same value (the native skips the lerp when they are equal)'),
    dict(id='hd2.fields.hover.vertical_acceleration_low_speed', status='new', path='160[1].0', offset=168,
        storage='f32', unit='m/s^2', type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.hover.vertical_acceleration_high_speed', status='new', path='160[1].4', offset=172,
        storage='f32', unit='m/s^2', type='number', range='>= 0', write='type record, live'),
    dict(id='hd2.fields.hover.vertical_speed_range_end', status='new', path='184[1].4', offset=196, storage='f32',
        unit='m/s', type='number', range='> vertical_speed_range_start (+192); never equal while the two vertical '
        'accelerations differ (0/0 division)', write='type record, live'),
    dict(id='hd2.fields.hover.fuel_rate_low_speed', status='new', path='200[0]', offset=200, storage='f32',
        unit='s/s', type='number', range='>= -1 (total fill rate = 1 + value)', write='type record, live'),
    dict(id='hd2.fields.hover.fuel_rate_high_speed', status='new', path='200[1]', offset=204, storage='f32',
        unit='s/s', type='number', range='>= -1', write='type record, live'),
]
NOT_PROMOTED = {
    '4': 'weapon-wielder call argument; meaning not decoded.', '8[0]': 'see +4', '8[1]': 'see +4', '8[2]': 'see +4',
    '148': 'no consumer found among the resolver callers; 0 in every record.',
    '20': 'avatar movement multiplier; the two values it scales were not identified.',
    '28': 'alternate launch window: the replicated toggle (interaction 0x13) is not identified in gameplay.',
    '64': 'getter only; no consumer traced.',
    '144': 'behaviour switch (recharge model); safe but changes the fuel model: promote after a live test.',
    '145': 'behaviour switch (hover only).', '152': 'behaviour switch (take-off).',
    '153': 'flight-model switch: the jump records hold no hover data; flipping it is a crash/desync risk.',
    '154': 'flight-model switch.', '155': 'meaning not decoded.',
    '184[0].0': 'horizontal speed range: the hover pack holds 0/0 with equal accelerations (inert).',
    '184[0].4': 'see +184', '184[1].0': 'vertical speed range start: expose only with +196 (lower risk to leave 0).',
}
PRESENTATION_REASON = 'presentation only (abilities, indicator, material variable, visual sway animation).'

LIVE_TESTS = [
    {'id': 'jump-forward', 'target': 'LIFT-850 Jump Pack', 'writes': {'jump.launch_forward_ratio': 0.95},
        'expect': 'A near-horizontal dash (vanilla 0.4): very low arc, long distance; standing still the launch is '
        'almost flat along the facing direction.'},
    {'id': 'jump-window', 'target': 'LIFT-850 Jump Pack', 'writes': {'jump.launch_duration': 2.0},
        'expect': 'Thrust lasts 2 s (vanilla 0.5 s): roughly 4x the height; the end-of-launch ability fires late.'},
    {'id': 'jump-sustain', 'target': 'LIFT-850 Jump Pack', 'writes': {'jump.sustain_duration': 4.0,
        'jump.sustain_thrust': 120.0}, 'expect': 'A long second boost after 1 s of flight (vanilla 1 s x 60).'},
    {'id': 'jump-air-control', 'target': 'LIFT-850 Jump Pack', 'writes': {'jump.air_control_acceleration': 40.0},
        'expect': 'Strong mid-air steering (vanilla 4 m/s^2).'},
    {'id': 'jump-takeoff', 'target': 'LIFT-850 Jump Pack', 'writes': {'jump.takeoff_speed': 12.0},
        'expect': 'A visible hop before the thrust (vanilla 2.8 m/s).'},
    {'id': 'hover-speed', 'target': 'LIFT-860 Hover Pack', 'writes': {'hover.max_horizontal_speed': 15.0,
        'hover.max_vertical_speed': 1.0}, 'expect': 'Fast horizontal drift (vanilla 3.5 m/s), slow climb '
        '(vanilla 10 m/s).'},
    {'id': 'hover-fuel', 'target': 'LIFT-860 Hover Pack', 'writes': {'hover.fuel_rate_low_speed': -0.9,
        'hover.fuel_rate_high_speed': -0.9}, 'expect': 'Hover lasts far longer before the meter empties (fill '
        'rate 0.1 s/s instead of 1..2.6 s/s); recharge after landing unchanged.'},
    {'id': 'hover-climb-accel', 'target': 'LIFT-860 Hover Pack', 'writes': {
        'hover.vertical_acceleration_low_speed': 40.0}, 'expect': 'Near-instant climb response (vanilla 9.8).'},
]
OPEN_QUESTIONS = [
    'The replicated mode toggle (flag 3, interaction 0x13) that selects +28: which player action sets it.',
    'hover.duration (+156) is compared with movement record +0x64; the timer semantics of +0x64 are not decoded.',
    'Stance state >= 4 for the alternate take-off impulse (+216): which stance values map to it.',
    '+4/+8 (wielder call 0x785020) and +20 (avatar modifier 0x68C0E0): consumers not decoded.',
    'Multiplayer: the flight update runs where the wearer is simulated; a host-only write likely affects only the '
    'host\'s pack (two-peer test needed).',
    'The Dark Fluid vessel record (2) and unowned record 3 are not player-delivered stratagem backpacks.',
]


def labels_for(t, component):
    """Record -> label from the owners' resource names and the earlier equipment research."""
    pods = json.loads((ROOT / 'research/pod-payloads-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    delivered = {}
    text = json.dumps(pods)
    for rack in _walk(pods):
        if isinstance(rack, dict) and rack.get('path') and rack.get('slots'):
            for slot in rack['slots']:
                if isinstance(slot, dict) and isinstance(slot.get('item'), str):
                    delivered.setdefault(slot['item'].upper().replace('0X', '0x'), rack['path'].rsplit('/', 1)[-1])
    del text
    out = []
    owners = component.owner_map()
    for record in range(component.count):
        resources = owners.get(record, [])
        names = []
        for resource in resources:
            leaf = t.label(resource)
            if leaf in LABELS:
                names.append(LABELS[leaf])
            elif hexid(resource) in delivered:
                names.append(f'{leaf} (delivered by {delivered[hexid(resource)]})')
            else:
                names.append(leaf)
        out.append({'record': record, 'owners': [hexid(r) for r in resources], 'ownerPaths': [t.name(r) for r in
            resources], 'label': ', '.join(names) if names else f'unowned record {record}'})
    return out


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def related_family(t, name: str) -> dict:
    component = t.component(name)
    owners = component.owner_map()
    entities = {t.label(r): r for record in range(component.count) for r in owners.get(record, [])[:1]}
    family = compare.Family(t, name, entities)
    described = family.describe(include_constant=False)
    struct_types = sorted({m.parent_type for m in component.members() if m.parent_type})
    return {'component': name, 'recordType': component.record_type, 'recordSize': component.record_size,
        'records': component.count, 'ownedRecords': len(owners),
        'owners': {record: [t.label(r) for r in rs] for record, rs in sorted(owners.items())},
        'nestedStructTypes': struct_types, 'varyingMembers': [{'path': m['path'], 'storage': m['storage'],
            'nameLength': m['nameLength'], 'values': m['values']} for m in described['members']][:60],
        'layoutFingerprint': described['layoutFingerprint']}


def build() -> dict:
    t = tables.pinned()
    component = t.component(COMPONENT)
    if component.record_type != RECORD_TYPE or component.record_size != RECORD_SIZE:
        raise ValueError('JumppackComponentData layout changed')
    members = component.members()
    records = labels_for(t, component)
    labels = [r['label'] for r in records]
    matrix = {m.path: [decode(m, component.raw(i)) for i in range(component.count)] for m in members}
    # flatten vectors into element paths so every scalar is addressable
    flat = {}
    for member in members:
        values = matrix[member.path]
        if member.atom == 'VECTOR':
            for index in range(member.count):
                flat[f'{member.path}[{index}]'] = (member, index, [v[index] for v in values])
        else:
            flat[member.path] = (member, None, values)

    from scan import xref
    image = xref.CodeImage.from_snapshot('game.dll')
    pins = check_pins(image, PINS, RIP_TARGETS)
    managers = manager_map(image)
    for name, rva in MANAGERS.items():
        if managers.get(name, {}).get('global') != rva:
            raise ValueError(f'{name} manager global changed')
    pin_by_group = {}
    for pin in pins:
        pin_by_group.setdefault(pin['group'], []).append(pin)

    loaded = snapshot_tables(component, LOADED_TABLE_OFFSET, MANAGERS['jumppack'])
    deltas = delta_targets(t, [COMPONENT, 'RechargeComponentData'] + RELATED)
    coverage = json.loads((ROOT / 'research/equipment-coverage-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    hover_decisions = coverage['hoverPack'].get('decisions', {})

    candidates = []
    for path, (member, element, values) in flat.items():
        spec = FIELDS.get(path)
        offset = member.offset + (4 * element if element is not None else 0)
        refs = pin_refs(pin_by_group, (spec or {}).get('code', []), offset)
        name = spec['nativeName'] if spec else None
        # vector/array elements share the parent's hidden name; fit is checked against the parent's length
        length = member.name_length
        if spec and spec.get('array'):
            parent = next(m for m in t.struct_members(RECORD_TYPE) if m['offset'] == int(spec['array']))
            length = parent['nameLength']
        fit = bool(name) and length is not None and len(name) == length
        varying = len({json.dumps(canonical(v)) for v in values}) > 1
        published, live = False, False
        if path == '156':
            published = abs(values[0] - 6.0) < 1e-6
        if path == '0':
            live = True   # gameplay-proven on the LIFT-850 (docs/backpack-authoring.md, JumpPackImprovements)
        evidence = {'codeRead': bool(refs), 'publishedExact': published, 'liveTest': live, 'nameLengthFit': fit,
            'differential': varying}
        if path in ('0', '156') and not fit:
            evidence['nameLengthFit'] = None
        notes = []
        if spec and str(spec.get('nameSource', '')).startswith('length_fitted'):
            notes.append('nativeName is a length-fitted descriptive label, not a recovered name')
        if spec and spec.get('existing'):
            notes.append(f"existing public id {spec['existing']}")
        conf_evidence = dict(evidence)
        if path in ('0', '156'):
            conf_evidence['nameLengthFit'] = True   # identity already proven by gameplay / published value
        cand = report.candidate(path, offset, member.storage, length, 'float' if member.atom == 'VECTOR'
            else member.kind, dict(zip(labels, (canonical(v) for v in values))), evidence, proposed=name,
            notes=notes, semantic=spec['semantic'] if spec else None, unit=spec['unit'] if spec else None,
            role=spec['kind'] if spec else 'unknown', nameSource=spec.get('nameSource') if spec else None,
            codeRefs=refs, semanticsFromCode=bool(spec and spec['kind'] in ('gameplay', 'switch') and refs),
            existingId=spec.get('existing') if spec else None)
        cand['confidence'] = report.confidence(conf_evidence)
        candidates.append(cand)

    related = [related_family(t, name) for name in RELATED]
    recharge = t.component('RechargeComponentData')
    recharge_rows = []
    for item in records:
        for owner in item['owners']:
            index = recharge.record_of(int(owner, 16))
            if index is not None:
                recharge_rows.append({'label': item['label'], 'record': index,
                    'time': canonical(decode(recharge.member(0), recharge.raw(index)))})
    presence = compare.presence(t, {t.label(r): r for r in t.find(
        r'jump_?pack|jetpack|hover_backpack|displacement_backpack')})

    rail = {r['label']: r['record'] for r in records}
    jump, hover = rail.get('LIFT-850 Jump Pack'), rail.get('LIFT-860 Hover Pack')
    summary = {'records': component.count, 'ownedRecords': len(component.owner_map()),
        'jumpPack': {k: canonical(flat[p][2][jump]) for k, p in (('launchThrust', '0'), ('launchWindow', '24'),
            ('launchForwardRatio', '32'), ('sustainThrust', '36'), ('sustainDuration', '40'),
            ('sustainForwardRatio', '44'), ('airControl', '60'), ('airControlMaxSpeed', '176[0]'),
            ('takeoffSpeed', '212'), ('takeoffForward', '208'))} if jump is not None else None,
        'hoverPack': {k: canonical(flat[p][2][hover]) for k, p in (('duration', '156'), ('maxHorizontal', '176[0]'),
            ('maxVertical', '176[1]'), ('horizontalAccel', '160[0].0'), ('verticalAccelLow', '160[1].0'),
            ('verticalAccelHigh', '160[1].4'), ('verticalRangeEnd', '184[1].4'), ('fuelLow', '200[0]'),
            ('fuelHigh', '200[1]'))} if hover is not None else None,
        'recharge': recharge_rows}

    model = {
        'jump': {'launch': 'v += [dir_h x r + up x (1 - r)] x thrust x (1 - t^2) x dt, t = elapsed / window; '
                           'downward velocity cancelled first',
            'sustain': 'after launch elapsed > +48 and speed >= +52 (forward probe clear): v += [dir_v x r2 + up x '
                       '(1 - r2)] x +36 x (1 - t^2) x dt over +40 s, each axis change <= |v_axis| x dt x 2.5; ends '
                       'below +56 m/s',
            'airControl': 'v += input_dir x +60 x dt while horizontal speed < +176.x',
            'takeoff': 'vz = clamp(max(vz, 0) + up, 0.75 up, 1.1 up), up = +212 (or +216 for stance >= 4); '
                       'v_h += dir x +208 when moving'},
        'hover': {'target': 'input x (+176.x, +176.x, +176.y)', 'acceleration': 'per axis |dv/dt| <= a, a_h = '
                  'lerp(+160, +164 by speed over +184..+188), a_v = lerp(+168, +172 by vz over +192..+196); no '
                  'climb acceleration at the vertical target speed',
            'fuel': 'cooldown += (1 + lerp(+200, +204 by vz over +192..+196)) x dt, capped at recharge.time; '
                    '+145: deactivate at an empty meter',
            'duration': '+156 vs movement record +0x64 (ascend gate)'},
        'perInstanceState': {'manager +0x48 (76 bytes)': {'+0x00': 'launch latch', '+0x01': 'sustain latch',
            '+0x04': 'launch elapsed (s)', '+0x08': 'sustain elapsed (s)', '+0x0C': 'launch window (s)',
            '+0x14..+0x44': 'visual sway state'}, 'manager +0x50 (5 bytes, replicated)': {'0': 'active',
            '1': 'sustain', '2': 'hover launch', '3': 'mode toggle', '4': 'thrusting'},
            'manager +0x40 (12 bytes)': 'replicated hover input vector'},
        'units': 'm, s, m/s, m/s^2; per-frame integration with dt',
    }
    lifecycle = {'resolver': '0x50D830', 'typeRecord': '[entity manager +0xF12CB8] = the loaded '
        'JumppackComponentData block', 'snapshots': loaded, 'entityDeltasTargeting': deltas,
        'conclusion': 'type record read live every frame (no per-instance copy is created by customization): a '
                      'write takes effect on the next frame, including mid-flight'}

    doc = report.document('Jump pack, hover pack and related movement components', {
        'component': COMPONENT, 'recordType': RECORD_TYPE, 'recordSize': RECORD_SIZE,
        'layoutFingerprint': t.fingerprint(COMPONENT), 'labels': labels, 'gameDll': image.describe()},
        candidates, summary=summary, records=records,
        matrix={path: dict(zip(labels, (canonical(v) for v in values))) for path, (_, _, values) in flat.items()},
        model=model, lifecycle=lifecycle,
        sharing={'owners': {r['label']: len(r['owners']) for r in records}, 'note': 'one owner per record; no '
            'shared record. RechargeComponentData is a separate component (recharge.time).'},
        priorEvidence={'equipmentCoverageDecisions': hover_decisions, 'backpackDoc': 'docs/backpack-authoring.md'},
        crossFamily={'related': related, 'presence': presence, 'enemyJumpPacks': 'cyborg soldier/berserker '
            'jump-pack units own Ability/IdleAbility/Locomotion only; their backpack props own no component'},
        code={'managers': {k: {'global': v['global'], 'assignSite': v['assignSite']} for k, v in managers.items()
                if k in MANAGERS},
            'jumppackAccessors': {f'{root:#x}': [f'{s:#x}' for s in sites] for root, sites in
                sorted(image.global_accessors(MANAGERS['jumppack']).items())},
            'hoverAccessors': {f'{root:#x}': len(sites) for root, sites in
                sorted(image.global_accessors(MANAGERS['hover']).items())},
            'functions': {'0x9B4790': 'flight physics (launch, sustain, air control, hover)', '0x9B5EC0': 'timers, '
                'abilities, visual sway', '0x9B3420': 'activate/deactivate', '0x9B4110': 'sustain gate',
                '0x9B4560': 'indicator and recharge material', '0xA63790': 'take-off (avatar state)', '0xA63F20':
                'take-off hop values', '0x5A3E40': 'character impulse', '0x50D830': 'record resolver',
                '0x9ED210/0x9ED5D0/0x9ED680': 'recharge manager: start, add, ready fraction', '0x880440': 'mode '
                'toggle (flag 3)', '0x9622D0': 'NPC HoverComponent audio RTPCs'},
            'pins': pins},
        promotionProposal={'families': ['hd2.fields.jump', 'hd2.fields.hover'], 'fields': PROPOSAL,
            'acknowledgement': 'allow_unverified_effect until a live test passes (native_consumer_proven offline); '
                'jump.vertical_launch_velocity stays gameplay_proven',
            'writeSemantics': 'patch the backpack\'s JumppackComponentData record (unique owner) through the existing '
                'hd2.backpack(...) chain; live next frame; expect/ensure guarded like jump.vertical_launch_velocity'},
        notPromoted=[{'path': path, 'reason': reason} for path, reason in NOT_PROMOTED.items()] +
            [{'path': path, 'reason': PRESENTATION_REASON} for path, spec in FIELDS.items()
                if spec['kind'] == 'presentation'],
        liveTests=LIVE_TESTS, openQuestions=OPEN_QUESTIONS)
    return doc


def markdown(doc: dict) -> str:
    lines = ['# Jump pack, hover pack and related movement components', '',
        f"Build {doc['build']}. Generated by `scripts/research_hoverpack_components.py` (research only; nothing is "
        'promoted here). Evidence, pins and matrices: `research/hoverpack-components-F5FEE03DCFDB.json`.', '',
        '## Summary', '']
    s = doc['summary']
    lines += [f"- LIFT-850 Jump Pack: {s['jumpPack']}", f"- LIFT-860 Hover Pack: {s['hoverPack']}",
        f"- Recharge (RechargeComponentData): {s['recharge']}", '']
    lines += ['## Flight model (native)', '']
    for section, items in doc['model'].items():
        if isinstance(items, dict):
            for key, value in items.items():
                lines.append(f'- {section}.{key}: {value}')
        else:
            lines.append(f'- {section}: {items}')
    lines += ['', f"Lifecycle: {doc['lifecycle']['conclusion']}. Entity deltas: "
        f"{doc['lifecycle']['entityDeltasTargeting']}. Loaded table equals file in "
        f"{sum(1 for x in doc['lifecycle']['snapshots'] if x.get('loadedTableEqualsFile'))} retained snapshots.", '',
        'Key functions: ' + ', '.join(f'`{k}` {v}' for k, v in doc['code']['functions'].items()) + '.', '']
    lines += ['## JumppackComponent members', '', report.markdown_table(['path', '+off', 'len', 'name (source)',
        'unit', 'role', 'confidence', 'meaning'], [[c['path'], c['offset'], c['nameLength'],
        f"{c['proposedName']} ({c.get('nameSource')})", c.get('unit'), c.get('role'), c['confidence'],
        c.get('semantic')] for c in doc['candidates']]), '',
        'Confidence follows `scripts/scan/report.py` mechanically; +0 and +156 count their earlier gameplay / '
        'published identity proof as the name evidence. Length-fitted names are descriptive labels, not recovered '
        'names.', '']
    labels = doc['scope']['labels']
    gameplay = [c['path'] for c in doc['candidates'] if c.get('role') in ('gameplay', 'switch')]
    lines += ['## Per-record matrix (gameplay members)', '', report.markdown_table(['path'] + labels,
        [[p] + [doc['matrix'][p][label] for label in labels] for p in gameplay]), '']
    lines += ['## Related families', '']
    for fam in doc['crossFamily']['related']:
        lines.append(f"- {fam['component']} ({fam['recordType']}, {fam['recordSize']} B, {fam['records']} records): "
            f"owners {list(fam['owners'].values())[:8]}; nested types {fam['nestedStructTypes']}; "
            f"{len(fam['varyingMembers'])} varying members.")
    lines.append(f"- Enemy jump packs: {doc['crossFamily']['enemyJumpPacks']}.")
    lines += ['', '## Promotion proposal', '', report.markdown_table(['id', 'status', '+off', 'unit', 'range',
        'note'], [[p['id'], p['status'], p['offset'], p['unit'], p['range'], p.get('note', '')]
        for p in doc['promotionProposal']['fields']]), '',
        f"Acknowledgement: {doc['promotionProposal']['acknowledgement']}.",
        f"Write semantics: {doc['promotionProposal']['writeSemantics']}.", '', '## Not promoted', '']
    lines += [f"- `{item['path']}`: {item['reason']}" for item in doc['notPromoted']]
    lines += ['', '## Live tests (strongly differentiated)', '']
    lines += [f"- **{t['id']}** ({t['target']}): {t['writes']} -> {t['expect']}" for t in doc['liveTests']]
    lines += ['', '## Open questions', ''] + [f'- {q}' for q in doc['openQuestions']]
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
