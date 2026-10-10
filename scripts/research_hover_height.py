"""What limits how high the LIFT-860 Hover Pack flies (research only; build F5FEE03DCFDB).

Read-only. Nothing here writes game memory or edits the public API. Inputs: the game.dll image of a retained snapshot
(scan.xref), the pinned JumppackComponentData values (research/hoverpack-components-F5FEE03DCFDB.json) and the
component-table pins (domains/component_tables.lua).

A player report (0.30.4): "the changes to the backpack didn't seem to work (all I want is increase the height of the
flying)". Findings, each pinned below:

1. There is no height member. The hover branch of the flight code (0x9B4790, +153 set) reads no altitude, ground
   distance or ceiling: its only inputs are the record's speeds, accelerations, speed ranges and fuel rates, the
   avatar's motion velocity and the motion record's airborne timer.
2. The climb input. Each frame the vertical hover input is 1 ("climb") when hover.duration (+156) is greater than the
   avatar motion record's +0x64, or when the replicated sustain flag (state byte 1) is set; otherwise 0 ("hold").
   With hover.duration <= 0 the input is instead a held player input (action 0xF, the one the take-off code 0xA63790
   also reads; its name is not proven).
3. Motion record +0x64 is the airborne timer: the motion update (0x59CED0) adds dt to it every frame the avatar is
   not on walkable ground and resets it to 0 on walkable ground. hover.duration is therefore the climb window in
   seconds of airborne time, not the hover time (the hover ends when the fuel meter is full: recharge.time, fuel
   rates, +145).
4. The sustain flag latches: 0x9B5613 sets it when the sustain phase starts (speed >= jump.sustain_start_speed,
   forward probe clear) and only (de)activation (0x9B3504) clears it, so after a sustain the climb input stays on for
   the rest of the flight.
5. Gravity is not suspended while hovering: the same motion update adds (0, 0, -9.82) x dt to an airborne avatar's
   velocity (0x59D6C4 .. 0x59DBEB). The hover pushes toward climb target x hover.max_vertical_speed with at most
   a_v = lerp(hover.vertical_acceleration_low_speed, _high_speed by vz over 0..hover.vertical_speed_range_end).
   Vanilla a_v is 9.8 at vz <= 0, falling to 0 at 8 m/s: at most 9.8 against 9.82 gravity. The pack cannot climb by
   itself; it holds (a 0.02 m/s^2 sink) the height the activation reached. Raising hover.max_vertical_speed, or
   hover.duration, cannot make it climb: the lift never exceeds gravity. Steady climb speed with the climb input on:
   v = E x (a_low - g) / (a_low - a_high), E = hover.vertical_speed_range_end, capped at hover.max_vertical_speed
   (none while a_low <= g).
6. The record HD2Runtime writes is the record the flight code reads: the resolver (0x50D830) reads the type record
   from the entity-manager table slot 264 (+0xF12CB8), the slot core/component_tables.lua re-proves before every
   write (domains/component_tables.lua pins 0x50D315 / 0x50D31F).

  py scripts/research_hover_height.py          # write research/hover-height-F5FEE03DCFDB.json + docs md
  py scripts/research_hover_height.py --check  # fail if the committed outputs are stale
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from scan import report  # noqa: E402
from research_railgun_charge import check_pins  # noqa: E402

OUTPUT = ROOT / 'research/hover-height-F5FEE03DCFDB.json'
MARKDOWN = ROOT / 'research/docs/hover-height-F5FEE03DCFDB.md'
HOVER = ROOT / 'research/hoverpack-components-F5FEE03DCFDB.json'
GRAVITY_RVA = 0x328CC68
MOTION_MANAGER = 0x3326558

PINS = [
    # the climb input (flight code 0x9B4790, hover branch)
    (0x9B4B93, 'cmp byte ptr [r12 + 0x99], r14b', '+153: the hover branch', 'climb_input'),
    (0x9B4BDA, 'mov r11, qword ptr [rip', 'the motion manager ...', 'climb_input'),
    (0x9B4C44, 'imul r13, rcx, 0x84', '... the avatar motion record (stride 0x84) ...', 'climb_input'),
    (0x9B4C4B, 'add r13, qword ptr [r11 + 0x48c8]', '... from the motion records (+0x48C8)', 'climb_input'),
    (0x9B4CB2, 'movss xmm0, dword ptr [r12 + 0x9c]', 'hover.duration (+156) ...', 'climb_input'),
    (0x9B4CC8, 'comiss xmm0, xmm15', '... <= 0: the climb input is a held player input (0x9B4D0D) ...', 'climb_input'),
    (0x9B4CCE, 'comiss xmm0, dword ptr [r13 + 0x64]', '... > airborne timer: climb ...', 'climb_input'),
    (0x9B4CDF, 'cmp byte ptr [rax + rcx + 1], r14b', '... else climb while the replicated sustain flag is set',
        'climb_input'),
    (0x9B4D0D, 'movabs rcx, 0xf00000002', 'held-input mode: action 0xF (also read by take-off 0xA63D45)',
        'climb_input'),
    (0x9B4D26, 'movss xmm0, dword ptr [r9 + r10 + 0x1cc0]', '... climb while its value > 0', 'climb_input'),
    (0x9B4D49, 'movd xmm12, eax', 'the vertical input (0 or 1)', 'climb_input'),
    # the vertical controller
    (0x9B4E47, 'movss xmm13, dword ptr [r12 + 0xb4]', 'target vz = hover.max_vertical_speed ...', 'controller'),
    (0x9B4E69, 'mulss xmm13, xmm12', '... x the vertical input', 'controller'),
    (0x9B4E2F, 'movss xmm10, dword ptr [r12 + 0xa8]', 'a_v = lerp(+168 ...', 'controller'),
    (0x9B4E39, 'movss xmm0, dword ptr [r12 + 0xac]', '... +172 ...', 'controller'),
    (0x9B4E80, 'movss xmm2, dword ptr [r13 + 8]', '... by vz (motion velocity z) ...', 'controller'),
    (0x9B4E8A, 'movss xmm0, dword ptr [r12 + 0xc4]', '... over +192..+196, clamped to 0..1)', 'controller'),
    (0x9B4FAD, 'movss xmm1, dword ptr [r12 + 0xb4]', 'a_v = 0 when |vz| >= max_vertical_speed in the input '
        'direction', 'controller'),
    (0x9B50A3, 'subss xmm13, xmm4', 'dv = target - vz ...', 'controller'),
    (0x9B50FA, 'divss xmm13, xmm14', '... / dt ...', 'controller'),
    (0x9B5137, 'minss xmm1, xmm13', '... clamped to [-a_v, a_v] ...', 'controller'),
    (0x9B518C, 'addss xmm1, xmm4', '... vz += a x dt ...', 'controller'),
    (0x9B5196, 'movss dword ptr [r13 + 8], xmm1', '... into the motion velocity', 'controller'),
    (0x9B52F4, 'mov byte ptr [rax + r15 + 4], cl', 'replicated flag 4 = the vertical input', 'controller'),
    # the sustain flag latch
    (0x9B5613, 'mov byte ptr [rcx + rdx + 1], al', 'the sustain gate (0x9B4110) sets replicated flag 1 ...', 'latch'),
    (0x9B3504, 'mov byte ptr [r14 + rcx + 1], sil', '... (de)activation clears it', 'latch'),
    # the airborne timer (motion update 0x59CED0)
    (0x59CF15, 'mov r13, qword ptr [rax + 0x48c8]', 'motion update: the motion records ...', 'airborne_timer'),
    (0x59CF5B, 'imul r12, rcx, 0x84', '... stride 0x84', 'airborne_timer'),
    (0x59D685, 'movss xmm0, dword ptr [rax + 0x64]', 'airborne timer +0x64 ...', 'airborne_timer'),
    (0x59D6A8, 'addss xmm0, xmm10', '... += dt when not on walkable ground ...', 'airborne_timer'),
    (0x59D6AD, 'movss dword ptr [r15], xmm0', '... stored', 'airborne_timer'),
    (0x59D7D7, 'movss dword ptr [r15], xmm0', 'reset to 0 on walkable ground', 'airborne_timer'),
    # gravity
    (0x59D6C4, 'movss xmm13, dword ptr [rip', 'gravity z (-9.82) ...', 'gravity'),
    (0x59DB9D, 'mulss xmm13, xmm8', '... projected on the down axis while airborne ...', 'gravity'),
    (0x59DBCB, 'mulss xmm8, xmm10', '... x dt ...', 'gravity'),
    (0x59DBEB, 'movss dword ptr [r12 + r13 + 8], xmm8', '... added to the motion velocity z', 'gravity'),
    # the record HD2Runtime writes
    (0x50D31F, 'mov r10, qword ptr [rax + 0xf12cb8]', 'resolver: the JumppackComponentData type record table '
        '(entity-manager slot 264)', 'record'),
]
RIP_TARGETS = {0x9B4BDA: MOTION_MANAGER, 0x59D6C4: GRAVITY_RVA}
G = 9.82


def hover_values() -> dict:
    data = json.loads(HOVER.read_text(encoding='utf-8'))
    m, name = data['matrix'], 'LIFT-860 Hover Pack'
    return {'duration': m['156'][name], 'max_vertical_speed': m['176[1]'][name],
        'vertical_acceleration_low_speed': m['160[1].0'][name], 'vertical_acceleration_high_speed':
        m['160[1].4'][name], 'vertical_speed_range_start': m['184[1].0'][name],
        'vertical_speed_range_end': m['184[1].4'][name]}


def steady_climb(p: dict) -> float:
    """Climb speed the controller settles at with the climb input on (0 when the lift never beats gravity)."""
    low, high = p['vertical_acceleration_low_speed'], p['vertical_acceleration_high_speed']
    start, end = p['vertical_speed_range_start'], p['vertical_speed_range_end']
    if low <= G:
        return 0.0
    if high >= G:
        return p['max_vertical_speed']
    v = start + (end - start) * (low - G) / (low - high)
    return min(v, p['max_vertical_speed'])


def simulate(p: dict, seconds: float = 12.0, vz0: float = 0.0, dt: float = 1 / 60) -> dict:
    """The decoded vertical model, frame by frame, from an activation at vz0 with the airborne timer at 0 and no
    sustain phase. Returns the height gained when the climb window closes and at the end."""
    vz, z, t = vz0, 0.0, 0.0
    low, high = p['vertical_acceleration_low_speed'], p['vertical_acceleration_high_speed']
    start, end, cap = p['vertical_speed_range_start'], p['vertical_speed_range_end'], p['max_vertical_speed']
    at_window = None
    while t < seconds:
        climb = 1.0 if p['duration'] > t else 0.0
        target = cap * climb
        u = (vz - start) / (end - start)
        a = low + (high - low) * (0.0 if u < 0 else min(1.0, u))
        if (climb < 0) == (vz < 0):
            a *= 1.0 if cap > abs(vz) else 0.0
        need = (target - vz) / dt
        vz += max(-a, min(a, need)) * dt
        vz -= G * dt
        z += vz * dt
        t += dt
        if at_window is None and t >= p['duration']:
            at_window = z
    return {'heightAtWindowEnd': round(at_window if at_window is not None else z, 2), 'heightAt': round(z, 2),
        'seconds': seconds, 'steadyClimb': round(steady_climb(p), 3)}


SCENARIOS = [
    ('vanilla', {}),
    ('max_vertical_speed 10 -> 30', {'max_vertical_speed': 30.0}),
    ('duration 6 -> 12', {'duration': 12.0}),
    ('vertical_acceleration_low_speed 9.8 -> 15', {'vertical_acceleration_low_speed': 15.0}),
    ('vertical_acceleration_low_speed 9.8 -> 20', {'vertical_acceleration_low_speed': 20.0}),
    ('vertical_acceleration_low_speed 9.8 -> 20, duration 6 -> 10', {'vertical_acceleration_low_speed': 20.0,
        'duration': 10.0}),
    ('vertical_acceleration_low_speed 9.8 -> 20, vertical_speed_range_end 8 -> 16', {
        'vertical_acceleration_low_speed': 20.0, 'vertical_speed_range_end': 16.0}),
]


def build() -> dict:
    from scan import xref
    image = xref.CodeImage.from_snapshot('game.dll')
    pins = check_pins(image, PINS, RIP_TARGETS)
    gravity = image.f32(GRAVITY_RVA)
    if abs(gravity + G) > 1e-4:
        raise ValueError(f'gravity constant changed: {gravity}')
    tables = (ROOT / 'domains/component_tables.lua').read_text(encoding='utf-8')
    slot_pinned = 'the JumppackComponentData table from slot 264' in tables and '4c8b90b82cf100' in tables
    if not slot_pinned:
        raise ValueError('domains/component_tables.lua no longer pins the JumppackComponentData slot 264')
    base = hover_values()
    scenarios = []
    for label, change in SCENARIOS:
        p = dict(base, **change)
        scenarios.append({'label': label, 'values': change, **simulate(p)})
    return report.document('LIFT-860 Hover Pack: what limits the height', {'gameDll': image.describe(),
        'component': 'JumppackComponentData', 'record': 'LIFT-860 Hover Pack'}, [],
        hoverPackValues=base, gravity={'rva': GRAVITY_RVA, 'value': round(gravity, 4),
            'appliedWhileHovering': True},
        model={
            'heightMember': 'none: the hover branch reads no altitude, ground distance or ceiling',
            'climbInput': 'hover.duration > motion +0x64 (airborne seconds) or replicated sustain flag set -> 1, '
                'else 0; hover.duration <= 0 -> a held player input (action 0xF, unnamed) instead',
            'airborneTimer': 'motion record +0x64: += dt while not on walkable ground (0x59D6A8), 0 on walkable '
                'ground (0x59D7D7)',
            'sustainLatch': 'replicated flag 1 is set when the sustain phase starts (0x9B5613) and cleared only by '
                '(de)activation (0x9B3504): after a sustain the climb input stays on',
            'controller': 'vz += clamp((input x max_vertical_speed - vz) / dt, -a_v, a_v) x dt, a_v = '
                'lerp(+168, +172 by vz over +192..+196), a_v = 0 at |vz| >= max_vertical_speed in the input '
                'direction',
            'gravity': 'vz -= 9.82 x dt every airborne frame (motion update), also while hovering',
            'steadyClimb': 'v = E x (a_low - 9.82) / (a_low - a_high), capped at max_vertical_speed; none while '
                'a_low <= 9.82 (vanilla 9.8)',
            'hoverEnd': 'the pack shuts off when the fuel meter is full (recharge.time, hover.fuel_rate_*; +145), '
                'not at hover.duration',
        },
        recordIdentity={'resolver': '0x50D830', 'table': '[entity manager] + 0xF12CB8 = slot 264',
            'runtimeGuard': 'core/component_tables.lua re-proves slot 264 before every write '
                '(domains/component_tables.lua)', 'perInstanceCopy': 'manager +0xA0 only for entities in the '
                'resolved map; none in the retained snapshots (research/hoverpack-components)',
            'conclusion': 'the record HD2Runtime writes is the record the flight code reads'},
        whyEditsDidNothing=[
            'hover.max_vertical_speed: the climb target; vanilla never reaches even 0 m/s of climb because the lift '
            '(9.8) never exceeds gravity (9.82), so a higher target changes nothing.',
            'hover.duration: the climb window in airborne seconds, not the hover time; with vanilla lift the climb '
            'input cannot overcome gravity, so a longer window changes nothing.',
            'jump.vertical_launch_velocity: the Hover Pack never reads the launch thrust (hover-launch flag).',
        ],
        recipe={'climb': 'hover.vertical_acceleration_low_speed above 9.82 (20 -> about 4 m/s climb, 40 -> about '
                '6 m/s with range end 8)', 'longer': 'hover.duration (climb window, airborne seconds)',
            'faster': 'hover.vertical_speed_range_end (where the lift fades) and hover.max_vertical_speed (cap)',
            'fuel': 'climbing burns fuel: hover.fuel_rate_low_speed / _high_speed, recharge.time'},
        scenarios=scenarios,
        multiplayer='Per-type record: each machine flies its own avatar with its own record copy; a write changes '
            'the pack for players on the machine that runs the mod.',
        pins=pins,
        openQuestions=['Which player input action 0xF is (held-input mode at hover.duration <= 0); likely jump.',
            'How high the activation itself lifts the avatar (ability +80 / sustain phase); not simulated.',
            'Live confirmation of the climb with a lift above gravity (proof/RebalanceFixesProof, '
            'examples/projects/JumpHoverTest).'])


def markdown(doc: dict) -> str:
    m = doc['model']
    lines = ['# LIFT-860 Hover Pack: what limits the height', '',
        f"Build {doc['build']}. Generated by `scripts/research_hover_height.py` (research only). Evidence and pins: "
        '`research/hover-height-F5FEE03DCFDB.json`. Members: `research/docs/hoverpack-components-F5FEE03DCFDB.md`.',
        '', '## Findings', '']
    lines += [f'- **{key}**: {value}' for key, value in m.items()]
    lines += [f"- **record identity**: {doc['recordIdentity']['conclusion']} ({doc['recordIdentity']['table']}; "
        f"{doc['recordIdentity']['runtimeGuard']}).", f"- **multiplayer**: {doc['multiplayer']}", '',
        '## Why the reported edits did nothing', '']
    lines += [f'- {item}' for item in doc['whyEditsDidNothing']]
    lines += ['', '## Recipe', ''] + [f'- {k}: {v}' for k, v in doc['recipe'].items()]
    lines += ['', '## Decoded vertical model, simulated (activation at rest, no sustain phase)', '',
        report.markdown_table(['change', 'steady climb (m/s)', 'height when the window closes (m)',
            f"height after {doc['scenarios'][0]['seconds']:g} s (m)"],
        [[s['label'], s['steadyClimb'], s['heightAtWindowEnd'], s['heightAt']] for s in doc['scenarios']]), '',
        'Heights are relative to the activation point; the activation launch itself adds to them.', '',
        '## Pins', '', report.markdown_table(['rva', 'group', 'asm', 'role'],
        [[f"{p['rva']:#x}" if isinstance(p.get('rva'), int) else p.get('rva'), p['group'], p['asm'], p['role']]
            for p in doc['pins']]), '', '## Open questions', '']
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
        print('stale: ' + ', '.join(stale) if stale else 'up to date')
        return 1 if stale else 0
    OUTPUT.write_text(text, encoding='utf-8')
    MARKDOWN.write_text(md, encoding='utf-8')
    print('wrote', OUTPUT.relative_to(ROOT), 'and', MARKDOWN.relative_to(ROOT))
    for s in doc['scenarios']:
        print(s)
    return 0


if __name__ == '__main__':
    sys.exit(main())
