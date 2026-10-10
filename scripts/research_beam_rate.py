"""What limits the shot interval of a pulsed (mode 6) beam weapon (EXPERIMENTAL multi-weapon beam swap, branch
exp/multi-beam). Live (2026-10-10, MultiBeamProof 0.3.0, owned table, solo): per-weapon rates were observed, but fast
rates were capped (Liberator 600 rpm and Reprimand 900 rpm, each with the Trident's 0.15 s pulse). Read-only, offline,
build F5FEE03DCFDB: the game.dll image of a retained snapshot (capstone), every retained snapshot.

The BeamWeapon update 0x83E200 (once per instance per world update, dt = the update's step: 0xAB5EC9 -> 0x571250 ->
0x5737B1) keeps two timers in the 0x70-byte instance I (I = [manager +0x60] + index x 0x70):

  I+0x60  shot timer   = 60 / record +104 at a pulse start (0x83EA90..0x83EAAA; 0 when the rate is <= 0)
  I+0x64  pulse timer  = record +112 at a pulse start (0x83EAB1, 0x83EAB4)
  I+1     discrete     = record +100 != 4 (post-create 0x546A48 / 0x546A4F); continuous beams skip the timers
  I+2     firing in the previous update (0x83F5D3: stored at the end of every update)
  I+0     a live beam  (0x83FC13 after BeamFire; 0 at the stop 0x83F4B9)

Per update, discrete beams (0x83EA53..0x83EAE6): both timers -= dt (the pulse timer twice when an unnamed flag of an
entity the update resolves is set, 0x83EA30..0x83EA48); request = trigger or I+0;
  not firing before (I+2 = 0): start a pulse only when the shot timer <= 0 (both timers re-set, not carried over);
  firing before (I+2 = 1): keep firing while the pulse timer > 0; else stop: 0x840550 and 0x13B81C0 (every live ring
  entry of the entity is killed, I+0 = 0), I+2 = 0.
A pulse can only start from 'not firing', i.e. the update AFTER the stop. With a steady step dt, k = max(1, ceil(P/dt))
updates of pulse, then the start needs one more update:

  n = max( ceil(60 / (R dt)), max(1, ceil(P / dt)) + 1 )      updates between pulse starts
  effective rpm = 60 / (n dt)

The Trident (R 300, P 0.15) at 60 fps: max(12, 10) = 12 -> 300 rpm. The Liberator at 600 rpm with P 0.15: max(6, 10)
= 10 -> 360 rpm; the Reprimand at 900: max(4, 10) -> 360 rpm (the live cap).

A pulse deals its damage at the hit phase after its first ray query (BeamFire in update N's component update; rays at
N+1's query phase; hits at N+1's hit phase, 0xAB5FCB), and the hit processing skips killed entries (0x13BB361). The
stop runs in N+1's component update, BEFORE that hit phase, when P <= dt: such a pulse never hits.

Output: research/beam-pulse-rate-F5FEE03DCFDB.json.   py -3 scripts/research_beam_rate.py
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import capstone
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_beam_damage import SNAPSHOTS  # noqa: E402
from scan import xref  # noqa: E402

OUTPUT = ROOT / 'research/beam-pulse-rate-F5FEE03DCFDB.json'
SIXTY = 0x23C7740           # f32 60.0, the rpm -> seconds constant of the shot timer
UPDATE, SHOT, BEAM_FIRE, STOP_ENTRIES, HITS = 0x83E200, 0x83F9D0, 0x13B8410, 0x13B81C0, 0x13BB240

# (rva, asm, rip target or None, role)
PROOFS = {
    'schedule': [
        (0xAB5EC9, 'call 0x571250', None, 'world update 0xAB5000: the entity component update (after the ray query '
         'phase 0xAB55AF, before the beam hit phase 0xAB5FCB)'),
        (0x5737A5, 'movaps xmm2, xmm6', None, '0x571250: the update\'s step dt ...'),
        (0x5737B1, 'call 0x83e200', None, '... to the BeamWeapon update, once per instance per world update'),
        (0x83E245, 'movaps xmm15, xmm2', None, 'the beam update keeps dt in xmm15'),
        (0x83E249, 'mov r15, qword ptr [rcx + 0x60]', None, 'the instance array ...'),
        (0x83E253, 'imul r13, rdx, 0x70', None, '... 0x70 bytes per instance'),
    ],
    'instanceInit': [
        (0x546A41, 'mov dword ptr [rbx + 0x60], 0', None, 'post-create: the shot timer starts at 0 (fires at once)'),
        (0x546A48, 'cmp dword ptr [rdi + 0x64], 4', None, 'post-create: record +100 (fire mode) != 4 ...'),
        (0x546A4F, 'mov byte ptr [rbx + 1], al', None, '... = I+1, the discrete flag (pulsed 6, charged 5)'),
    ],
    'request': [
        (0x83E846, 'cmp byte ptr [r15 + r13 + 1], 0', None, 'continuous beams (I+1 = 0) ...'),
        (0x83E853, 'je 0x83eae6', None, '... skip both timers'),
        (0x83E859, 'cmp byte ptr [rsp + 0x50], 0', None, 'the trigger request ...'),
        (0x83E864, 'cmp byte ptr [r15 + r13], 0', None, '... or a live beam (I+0) keeps the request up'),
        (0x83EA30, 'bt qword ptr [rcx + r8 + 0x547840], 0x24', None, 'an unnamed flag (bit 36) of an entity the '
         'update resolves ...'),
        (0x83EA43, 'subss xmm0, xmm15', None, '... runs the pulse timer at double speed'),
    ],
    'timers': [
        (0x83EA53, 'cmp byte ptr [r15 + r13 + 2], 0', None, 'I+2: firing in the previous update'),
        (0x83EA59, 'movss xmm1, dword ptr [r15 + r13 + 0x64]', None, 'pulse timer'),
        (0x83EA60, 'movss xmm0, dword ptr [r15 + r13 + 0x60]', None, 'shot timer'),
        (0x83EA67, 'subss xmm1, xmm15', None, 'pulse timer -= dt'),
        (0x83EA6C, 'subss xmm0, xmm15', None, 'shot timer -= dt (every update, firing or not)'),
        (0x83EA71, 'movss dword ptr [r15 + r13 + 0x64], xmm1', None, ''),
        (0x83EA78, 'movss dword ptr [r15 + r13 + 0x60], xmm0', None, ''),
        (0x83EA7F, 'jne 0x83ead7', None, 'firing before: the pulse branch'),
        (0x83EA85, 'comiss xmm13, xmm0', None, 'not firing before: start only when shot timer <= 0 ...'),
        (0x83EA89, 'jb 0x83ead0', None, '... else no shot this update'),
        (0x83EA90, 'mov eax, dword ptr [rcx + 0x68]', None, 'start: record +104 (fire rate, rpm) ...'),
        (0x83EA97, 'movss xmm1, dword ptr [rip + {rip}]', SIXTY, '... 60.0 ...'),
        (0x83EAA6, 'divss xmm1, xmm0', None, '... / rate ...'),
        (0x83EAAA, 'movss dword ptr [r15 + r13 + 0x60], xmm1', None, '... = the shot timer (SET, the overshoot of '
         'the last interval is dropped)'),
        (0x83EAB1, 'mov eax, dword ptr [rcx + 0x70]', None, 'start: record +112 ...'),
        (0x83EAB4, 'mov dword ptr [r15 + r13 + 0x64], eax', None, '... = the pulse timer'),
        (0x83EAD0, 'mov byte ptr [rsp + 0x50], 0', None, 'shot timer > 0: not firing'),
        (0x83EAD7, 'comiss xmm13, xmm1', None, 'firing before: pulse timer <= 0 ...'),
        (0x83EADE, 'cmovae eax, r14d', None, '... ends the pulse (firing = request and pulse timer > 0)'),
    ],
    'pulse': [
        (0x83EB44, 'mov ebx, dword ptr [rsp + 0x50]', None, 'firing this update?'),
        (0x83EB4A, 'je 0x83f48c', None, 'no: the stop path'),
        (0x83EE62, 'cmp byte ptr [r15 + r13 + 2], 0', None, 'yes: new beams only when NOT firing before ...'),
        (0x83EE6C, 'jne 0x83f263', None, '... else the running pulse is updated'),
        (0x83F05F, 'imul r15d, dword ptr [rax + 0x6c]', None, 'beams of the new pulse: x record +108, all in this '
         'update'),
        (0x83F0D3, 'call 0x83f9d0', None, 'the beam shot (discrete)'),
        (0x83F182, 'cmp byte ptr [rsp + 0x54], 0', None, 'more than one beam only with this flag'),
        (0x83F189, 'sub r15d, 1', None, 'the beam loop'),
        (0x83FC02, 'call 0x13b8410', None, 'the beam shot: BeamFire (a ring entry) ...'),
        (0x83FC13, 'mov byte ptr [r12], 1', None, '... I+0 = 1 (a live beam)'),
    ],
    'stop': [
        (0x83F48C, 'cmp byte ptr [r15 + r13 + 2], 0', None, 'not firing, but firing before: ...'),
        (0x83F4AC, 'call 0x840550', None, '... stop the beam ...'),
        (0x83F4B4, 'call 0x13b81c0', None, '... kill the entity\'s ring entries ...'),
        (0x83F4B9, 'mov byte ptr [r15 + r13], 0', None, '... I+0 = 0'),
        (0x83F5D3, 'mov byte ptr [r15 + r13 + 2], bl', None, 'I+2 = firing this update (the next update\'s '
         '"firing before")'),
        (0x13B8219, 'cmp byte ptr [rsi + rdi + 0x280], r14b', None, '0x13B81C0: every live entry (E+0x110) ...'),
        (0x13B8227, 'cmp dword ptr [rsi + rdi + 0x1d8], ebx', None, '... of this entity (E+0x68) ...'),
        (0x13B83B7, 'mov byte ptr [rsi + rdi + 0x280], r14b', None, '... is killed at once (E+0x110 = 0)'),
        (0x13BB361, 'cmp byte ptr [r14 + rsi + 0x280], 0', None, 'the hit phase skips killed entries'),
    ],
    'worldOrder': [
        (0xAB55AF, 'call 0x13f73f0', None, 'query phase: ray queries of every live beam entry'),
        (0xAB565C, 'mul dword ptr [r14 + 0x793a600]', None, 'the query batch is split into jobs right after it'),
        (0xAB5FCB, 'call 0x13bb240', None, 'beam hit phase, after the component update'),
    ],
}

# The instance timers: every access in .text. Functions that address BeamWeapon instances (the 0x70 idiom
# 'imul r, r, 0x70' then '[r + 0x60]' within five instructions) plus the update (which loads the array first).
TIMER_WRITERS_EXPECTED = {
    '0x83EA48': 'update: the flag\'s extra pulse decrement', '0x83EA71': 'update: pulse -= dt',
    '0x83EA78': 'update: shot -= dt', '0x83EAAA': 'update: shot := 60 / rate', '0x83EAB4': 'update: pulse := +112',
    '0x83EABF': 'update: shot := 0 (rate <= 0)', '0x83EAC9': 'update: pulse := +112 (rate <= 0)',
    '0x546A41': 'post-create: shot := 0', '0x83E1A1': 'post-create (second variant): shot := 0'}

# Accesses in those functions whose base is not a BeamWeapon instance (read from the code around them).
NOT_INSTANCE = {
    '0x75980F': 'the multiplier of a hash table ([r13 + 0x58] count, [r13 + 0x50] rows, [r13 + 0x5C] empty key)',
    '0x8C13DD': 'r15 = the result of the getter 0x5092B0 (another record: +0xD4, +0x3C, +0x70 read too)',
    '0x8C145C': 'r15 = the result of the getter 0x5092B0 (the record of another component)',
    '0x546A48': 'rdi = the BeamWeapon RECORD (+100 fire mode), not the instance',
    '0x83E1A8': 'rdi = the BeamWeapon RECORD (+100 fire mode), not the instance',
    '0x83F4BE': 'rsi = the BeamWeapon RECORD (+0x60, an event id at the stop)',
    '0x83F51D': 'rsi = the BeamWeapon RECORD (+0x60, an event id at the stop)'}


def instance_functions(image) -> list[int]:
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.skipdata = True
    recent, found = [], set()
    for rva, size, mnemonic, operands in md.disasm_lite(image.data[image.text[0]:image.text[1]], image.text[0]):
        recent.append((mnemonic, operands))
        recent = recent[-5:]
        if mnemonic in ('add', 'mov') and re.fullmatch(r'r\w+, qword ptr \[r\w+ \+ 0x60\]', operands) and any(
                m == 'imul' and o.endswith(', 0x70') for m, o in recent[:-1]):
            found.add(rva)
    return sorted(found)


def timer_census(image, code) -> dict:
    """Every 4-byte access to +0x60 / +0x64 in the beam instance functions (the update, the post-creates, every
    function with the instance idiom); 16-byte stores at +0x60 are the creates' zeroing of the whole 0x70 bytes."""
    roots = sorted({code.root(site) or site for site in instance_functions(image) + [UPDATE]})
    accesses = []
    for root in roots:
        for insn in code.function_insns(root):
            m = re.search(r'dword ptr \[(r\w+)(?: \+ (r\w+))? \+ (0x6[04])\]', insn.op_str)
            if not m or 'rsp' in insn.op_str or 'rbp' in insn.op_str:
                continue
            write = insn.op_str.startswith('dword ptr') and insn.mnemonic.startswith('mov')
            accesses.append({'rva': '0x%X' % insn.address, 'function': '0x%X' % root,
                             'asm': insn.mnemonic + ' ' + insn.op_str, 'write': write})
    return {'functions': ['0x%X' % r for r in roots], 'accesses': accesses}


# ------------------------------------------------------------------------------------ the model
def simulate(rate: float, pulse: float, fps: float, pulses: int = 40, doubled: bool = False) -> dict:
    """The update's state machine, float32 as the game computes it, a held trigger and a steady step 1 / fps. Returns
    the updates between pulse starts (steady state), the effective rpm and whether a pulse outlives its first hit
    phase (the update after it fired)."""
    f = numpy.float32
    dt = f(1.0) / f(fps)
    shot = f(0.0)
    pulse_timer = f(0.0)
    firing_before = False
    starts, update, first_stop = [], 0, None
    while len(starts) < pulses and update < 100000:
        shot = f(shot - dt)
        pulse_timer = f(pulse_timer - dt) if not doubled else f(f(pulse_timer - dt) - dt)
        if not firing_before:
            if shot <= 0:
                shot = f(60.0) / f(rate) if rate > 0 else f(0.0)
                pulse_timer = f(pulse)
                firing = True
                starts.append(update)
            else:
                firing = False
        else:
            firing = pulse_timer > 0
            if not firing and first_stop is None:
                first_stop = update - starts[-1]
        firing_before = firing
        update += 1
    gaps = [b - a for a, b in zip(starts, starts[1:])][5:]
    n = max(set(gaps), key=gaps.count)
    return {'updates': n, 'rpm': 60.0 / (n / fps), 'pulseUpdates': first_stop, 'hits': first_stop >= 2}


def simulate_jittered(rate: float, pulse: float, fps: float, jitter: float = 0.2, pulses: int = 400,
                      seed: int = 1) -> dict:
    """The same state machine with a varying step (1 / fps x (1 +- jitter / 2), uniform): the AVERAGE rate a player
    sees, and the share of pulses that outlive their first hit phase."""
    f = numpy.float32
    rng = numpy.random.default_rng(seed)
    shot = pulse_timer = f(0.0)
    firing_before, clock = False, 0.0
    starts, alive, hit = [], 0, []
    while len(starts) < pulses:
        dt = f((1.0 / fps) * (1.0 + jitter * (rng.random() - 0.5)))
        clock += float(dt)
        shot = f(shot - dt)
        pulse_timer = f(pulse_timer - dt)
        if not firing_before:
            firing = bool(shot <= 0)
            if firing:
                shot, pulse_timer, alive = f(60.0) / f(rate), f(pulse), 0
                starts.append(clock)
        else:
            alive += 1
            firing = bool(pulse_timer > 0)
            if not firing:
                hit.append(alive >= 2)
        firing_before = firing
    return {'rpm': 60.0 * (len(starts) - 1) / (starts[-1] - starts[0]), 'hitShare': sum(hit) / max(1, len(hit))}


def closed_form(rate: float, pulse: float, fps: float) -> int:
    dt = 1.0 / fps
    return max(math.ceil(60.0 / (rate * dt) - 1e-9), max(1, math.ceil(pulse / dt - 1e-9)) + 1)


def fitted_pulse(rate: float, donor: float = 0.15) -> float:
    """The configure() rule: keep the donor's pulse when it fits, else max(I / 2, I - 1 / 30) (I = 60 / rate)."""
    interval = 60.0 / rate
    return min(donor, max(interval / 2, interval - 1 / 30))


def model_table() -> list[dict]:
    rows = []
    for rate in (150, 300, 450, 600, 900, 1200, 1800):
        for pulse_kind in ('trident', 'fitted'):
            pulse = 0.15 if pulse_kind == 'trident' else fitted_pulse(rate)
            row = {'rate': rate, 'pulse': round(pulse, 4), 'pulseKind': pulse_kind}
            for fps in (30, 45, 60, 90, 120, 144, 240):
                sim = simulate(rate, pulse, fps)
                varying = simulate_jittered(rate, pulse, fps)
                row[str(fps)] = {'rpm': round(sim['rpm'], 1), 'updates': sim['updates'], 'hits': sim['hits'],
                                 'rpmVaryingStep': round(varying['rpm'], 1),
                                 'hitShareVaryingStep': round(varying['hitShare'], 3)}
            rows.append(row)
    return rows


def check_model() -> dict:
    """The closed form against the float32 simulation away from exact multiples, and the fitted pulse rule: it never
    caps the rate (the shot timer alone decides) at any frame rate >= 30 fps."""
    mismatches, capped = [], []
    for rate in range(60, 3001, 30):
        for fps in (30, 37, 45, 50, 60, 75, 90, 120, 144, 165, 240):
            for pulse in (0.0, 0.01, 0.05, 0.1, 0.15, 0.3):
                x, y = 60.0 * fps / rate, pulse * fps
                if abs(x - round(x)) < 1e-3 or abs(y - round(y)) < 1e-3:
                    continue                 # exact multiples: float32 rounding decides between n and n + 1
                if simulate(rate, pulse, fps, 20)['updates'] != closed_form(rate, pulse, fps):
                    mismatches.append((rate, fps, pulse))
            fitted = fitted_pulse(rate)
            shot_only = max(2, math.ceil(60.0 * fps / rate - 1e-9))
            if closed_form(rate, fitted, fps) > shot_only:
                capped.append((rate, fps, fitted))
    return {'closedFormMismatches': mismatches, 'fittedPulseCaps': capped}


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    sixty = numpy.frombuffer(data[SIXTY:SIXTY + 4], dtype='<f4')[0]
    if sixty != 60.0:
        raise ValueError('the rate constant is not 60.0: %r' % sixty)
    census = timer_census(image, xref.CodeImage(data, image_base))
    writers = {a['rva'] for a in census['accesses'] if a['write']}
    if writers != set(TIMER_WRITERS_EXPECTED):
        raise ValueError('another writer of the instance timers: %r' % sorted(writers))
    readers = sorted({a['function'] for a in census['accesses'] if not a['write']
                      and a['rva'] not in NOT_INSTANCE})
    if readers != ['0x83E200']:
        raise ValueError('another reader of the instance timers: %r' % readers)
    for a in census['accesses']:
        a['instance'] = a['rva'] not in NOT_INSTANCE
        if not a['instance']:
            a['why'] = NOT_INSTANCE[a['rva']]
    mismatch = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(mismatch.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % mismatch)
    checks = check_model()
    if checks['closedFormMismatches'] or checks['fittedPulseCaps']:
        raise ValueError('the model does not hold: %r' % {k: v[:10] for k, v in checks.items()})
    live = {'liberator600': simulate(600, 0.15, 60), 'reprimand900': simulate(900, 0.15, 60),
            'talon150': simulate(150, 0.15, 60), 'trident300': simulate(300, 0.15, 60)}
    report = {
        'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'gameDllSha256': base.PROFILE_DLL_SHA,
        'question': 'What limits the shot interval of a pulsed beam (the live cap of fast per-weapon rates)?',
        'follows': ['beam-table-relocation-F5FEE03DCFDB.md', 'beam-damage-per-weapon-F5FEE03DCFDB.md',
                    'las-beam-overhaul-comparison.md'],
        'liveEvidence': [{
            'date': '2026-10-10', 'source': 'user, solo', 'proof': 'MultiBeamProof 0.3.0 (owned table path)',
            'quote': 'It pretty much works, though fast fire rates are capped, I think due to the time the beams stay '
                     'in game before the next can fire.',
            'recorded': 'The owned table path worked in game, solo; per-weapon rates were observed; high rates were '
                        'capped (profile R: Liberator 600, Talon 150, Reprimand 900 rpm, each with the Trident\'s '
                        '2 beams and 0.15 s pulse).'}],
        'instance': {'size': 0x70, 'shotTimer': 0x60, 'pulseTimer': 0x64, 'discrete': 1, 'firingBefore': 2,
                     'liveBeam': 0},
        'record': {'fireMode': 100, 'fireRate': 104, 'pulseBeams': 108, 'pulseSeconds': 112},
        'proofs': proofs, 'rateConstant': {'rva': '0x%X' % SIXTY, 'value': 60.0},
        'timerCensus': census, 'timerWriters': TIMER_WRITERS_EXPECTED,
        'formula': {
            'updatesBetweenPulses': 'n = max(ceil(60 / (R dt)), max(1, ceil(P / dt)) + 1)',
            'effectiveRpm': '60 / (n dt)',
            'terms': {'R': 'record +104 (rpm)', 'P': 'record +112 (s)', 'dt': 'the world update step'},
            'why': 'The shot timer gates a start (it must be <= 0); a start is only possible from "not firing", and '
                   'the pulse ends in the update its timer reaches <= 0, so the next start is one update later. The '
                   'shot timer is SET at a start (60 / R), so each interval also rounds up to whole updates.',
            'fitsWhen': 'P <= 60 / R - dt: the pulse never decides the interval. P <= 60 / (2 R) fits at every '
                        'frame rate; P <= 60 / R - 1 / 30 at every frame rate >= 30 fps.',
            'hitsWhen': 'P > dt (the pulse is alive at the hit phase after its first ray query). STRONG: the '
                        'query batch runs as jobs between the query phase and the hit phase of the same update.',
            'hardCaps': ['n >= 2: at most one pulse every two updates (30 x fps rpm), whatever P.',
                         'A pulse that hits needs P > dt, so n >= 3: at most 20 x fps rpm (1200 rpm at 60 fps, '
                         '2400 at 120 fps).',
                         'Quantization: 60 / (n dt) for a whole n; at 60 fps the reachable rates are 3600 / n '
                         '(1200, 900, 720, 600, 514, 450, ...); at an exact multiple frame-time jitter decides '
                         'between n and n + 1.'],
            'beamsPerPulse': 'Record +108 is a factor of the beam-shot loop count at a pulse start (0x83F05F: x a '
                             'count at +0xD8 of a 0x3F0-byte per-entity record); the loop repeats only when '
                             '[rsp+0x54] is set (0x83F182; from 0x83E37F..0x83E39A, not traced further). Every '
                             'iteration runs in the SAME update: no time cost. The 64-entry ring is not a limit: a '
                             'new pulse needs the previous one stopped, which kills its entries.',
            'unnamedFlag': 'Bit 36 of [[game+0x3326D20] + 0x547840 + 0x78 x row] of an entity the update resolves '
                           '(edi, not traced) doubles the pulse '
                           'timer\'s speed (0x83EA30..0x83EA48). Not named; its setter is not traced.'},
        'liveCapExplained': live,
        'fittedPulseRule': 'configure(): P = min(the requested or donor pulse, max(60 / (2 R), 60 / R - 1 / 30)) '
                           'when no pulse_seconds is given; an explicit pulse is kept and a cap is warned.',
        'model': model_table(), 'modelChecks': checks,
        'modelNote': 'rpm / updates / hits: a steady step in float32 (at an exact multiple the rounding adds an '
                     'update); rpmVaryingStep / hitShareVaryingStep: the step varies +-10 percent per update.',
        'pinnedBytesMismatchPerSnapshot': mismatch,
        'unproven': [
            'Live: the fitted pulses at 600 / 900 / 1200 rpm (MultiBeamProof 0.3.1).',
            'That ray results are ready at the hit phase of the update that submitted them (STRONG): a pulse of one '
            'to two updates hits only then.',
            'That the world update runs once per rendered frame (the step dt is the frame time).',
            'The protected sections (.vm_sec, .winlice) cannot be scanned for timer accesses.'],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'pins': len(pins), 'snapshots': len(mismatch), 'timerWriters': sorted(writers),
                      'timerReaders': readers, 'live': live}, indent=1))


if __name__ == '__main__':
    main()
