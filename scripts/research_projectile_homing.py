"""Projectile homing (docs/projectile-homing.md): what Runtime may write to steer a shot in flight, proven read-only on
build F5FEE03DCFDB from the game.dll image and the four retained mission snapshots.

1. The update steers a projectile by its own velocity copy. The projectile update (0x13AB11C) visits a slot only while
   its flags (+0x203C + slot*2) have bit 1 (0x13AB250), takes its flight record (+0x3040 + slot*0x70, 0x13AB25E..
   0x13AB269) and, when flags bit 0 is clear (0x13AB2AE) and no unit drives it (flight +0x50 = 0, 0x13AB26C /
   0x13AB4A9), calls the ballistic integrator (0x13AB59A) with the flight record's +0x0C as the velocity and the record
   itself as the position (0x13AB55A / 0x13AB566).
2. The integrator (0x13AAE30) loads the velocity from that pointer once (0x13AAE7F..0x13AAE95), adds gravity and drag
   per substep, integrates the position from it (0x13AB019..0x13AB044) and stores the velocity back (0x13AB062..
   0x13AB06D). So a velocity written before the update is the velocity the projectile flies this step: the direction
   of a shot in flight is that one member, and nothing else of the projectile needs to change.
3. The hit test follows the integrated path: the update copies the position BEFORE the step into the step's hit-test
   segment (0x13AB48E..0x13AB4A2) and measures the step from that copy to the integrated end (0x13AB794..0x13AB813:
   the distance travelled grows by it). A steered projectile therefore hits what its new path meets.
4. The speed rule is a ratio: the update compares |velocity| / flight +0x2C (the spawn speed, 0x13AB6D5 / 0x13AB6DA)
   with a fraction; steering that keeps |velocity| leaves it untouched.
5. A UNIT-DRIVEN projectile (flight +0x50 names a unit) takes its position from that unit each step and recomputes its
   velocity from the displacement (0x13AB4BB..0x13AB552), overwriting any write: Runtime never steers one.
6. Flight +0x18 is carried step time: the update adds it to this step's time and clears it (0x13AB2C7 / 0x13AB2D1).
7. Who writes a velocity (the census: every pool-relative velocity store in game.dll, and the integrator's own):
   SpawnProjectile (the direction times the speed), the integrator, the unit-driven path, the hit path (a ricochet or
   pass-through sets the new direction) and the two network impact handlers. A write between two of the game's own is
   simply the velocity of the next step; the game's writers keep working (a ricochet still ricochets).
8. Multiplayer [traced]: each machine simulates its own copy of a shot. The network impact handler (0xB9E0C0, and
   0xBBADE0) finds the copy by the shot id the projectile system keeps per slot (+0x3C + slot*4, 0xB9E130..0xB9E144),
   sets its velocity from the message and explodes it at the message's position (the explosion step's position
   argument, 0xB9E156 / 0xB9E1C7), then ends it (0xB9E1D1). So the shooter's machine decides where its shot hits, and
   the other machines draw the hit there even though their copy flew straight (the Gas EAT's live 2026-10-04 result:
   the owning machine's explosion is the one that damages).

The snapshots are read for plausibility only: slots in flight have a finite velocity whose length does not exceed
their spawn speed by more than the inherited share, and their +0x50 is 0 (no unit-driven player shot is retained).

Output: research/projectile-homing-F5FEE03DCFDB.json.  py scripts/research_projectile_homing.py [--check]
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
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/projectile-homing-F5FEE03DCFDB.json'
POOL_RESEARCH = ROOT / 'research/projectile-pool-F5FEE03DCFDB.json'
SNAPSHOTS = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
SYSTEM_GLOBAL = 0x347CEA8
# Flight record members homing reads or relies on (the pool research names position, velocity, speed, distance and
# lifetime; these add the carried step time and the unit-driven member).
FLIGHT = {'position': 0x00, 'velocity': 0x0C, 'carriedTime': 0x18, 'speed': 0x2C, 'distance': 0x30, 'lifetime': 0x34,
    'unit': 0x50, 'read': 0x54}
FLAGS = {'inFlight': 2, 'noMotion': 1}
SHOT_IDS = {'base': 0x3C, 'stride': 4}

PROOFS = {
    'update': [
        (0x13AB250, 'test byte ptr [rbx + rsi*2 + 0x203c], 2', None, 'a slot is updated only while flags bit 1 is set'),
        (0x13AB25E, 'imul r13, rsi, 0x70', None, 'its flight record (stride 0x70)'),
        (0x13AB262, 'lea rdi, [rbx + 0x3040]', None, 'the flight records'),
        (0x13AB269, 'add rdi, r13', None, 'rdi = this slot\'s flight record'),
        (0x13AB26C, 'mov r12d, dword ptr [rdi + 0x50]', None, 'flight +0x50: the unit that drives it (0 = none)'),
        (0x13AB270, 'test r12d, r12d', None, 'no unit: ballistic flight'),
        (0x13AB2AE, 'test byte ptr [rbx + rsi*2 + 0x203c], 1', None, 'flags bit 0: no motion this update'),
        (0x13AB2B6, 'jne 0x13ab82d', None, 'skips the step (lifetime only)'),
        (0x13AB2C7, 'addss xmm9, dword ptr [rdi + 0x18]', None, 'flight +0x18: carried step time, added to this step'),
        (0x13AB2D1, 'mov dword ptr [rdi + 0x18], 0', None, 'and cleared'),
        (0x13AB48E, 'movsd xmm0, qword ptr [rdi]', None, 'the position before the step'),
        (0x13AB496, 'movsd qword ptr [rcx + rbx + 0xe7054], xmm0', None, 'copied as the hit-test segment start (x, y)'),
        (0x13AB4A2, 'mov dword ptr [rcx + rbx + 0xe705c], eax', None, 'and z'),
        (0x13AB4A9, 'test r12d, r12d', None, 'a unit-driven projectile'),
        (0x13AB4AC, 'je 0x13ab557', None, 'else the ballistic step'),
        (0x13AB4C2, 'mov ecx, dword ptr [rdi + 0x50]', None, 'unit-driven: the unit\'s position'),
        (0x13AB53F, 'movss dword ptr [rdi + 0xc], xmm2', None, 'unit-driven: the velocity is recomputed from the '
            'displacement (a write is overwritten)'),
        (0x13AB54E, 'movsd qword ptr [rdi], xmm4', None, 'unit-driven: the position is the unit\'s'),
        (0x13AB557, 'mov ecx, dword ptr [rdi + 0x48]', None, 'ballistic: the substep count'),
        (0x13AB55A, 'lea rdx, [rdi + 0xc]', None, 'the integrator\'s velocity = flight +0x0C'),
        (0x13AB566, 'mov r8, rdi', None, 'the integrator\'s position = flight +0x00'),
        (0x13AB59A, 'call 0x13aae30', None, 'the ballistic integrator'),
        (0x13AB6D5, 'divss xmm0, dword ptr [rdi + 0x2c]', None, '|velocity| / flight +0x2C (the spawn speed)'),
        (0x13AB6DA, 'comiss xmm8, xmm0', None, 'compared with a fraction (the speed rule is a ratio)'),
        (0x13AB7B5, 'subss xmm1, dword ptr [rax + rbx + 0xe7054]', None, 'the step: end minus the segment start'),
        (0x13AB80E, 'addss xmm1, dword ptr [rdi + 0x30]', None, 'distance travelled + the step\'s length'),
        (0x13AB813, 'movss dword ptr [rdi + 0x30], xmm1', None, 'stored'),
    ],
    'integrator': [
        (0x13AAE30, 'mov r11, rsp', None, 'the ballistic integrator'),
        (0x13AAE46, 'mov rdi, r8', None, 'rdi = the position'),
        (0x13AAE49, 'mov rbx, rdx', None, 'rbx = the velocity'),
        (0x13AAE7F, 'movss xmm11, dword ptr [rdx + 4]', None, 'velocity y, read once'),
        (0x13AAE8A, 'movss xmm12, dword ptr [rdx]', None, 'velocity x'),
        (0x13AAE95, 'movss xmm13, dword ptr [rdx + 8]', None, 'velocity z'),
        (0x13AB019, 'addss xmm0, dword ptr [rdi]', None, 'position x + the substep\'s displacement'),
        (0x13AB022, 'movss dword ptr [rdi], xmm0', None, 'stored'),
        (0x13AB02D, 'movss dword ptr [rdi + 4], xmm1', None, 'position y'),
        (0x13AB044, 'movss dword ptr [rdi + 8], xmm0', None, 'position z'),
        (0x13AB062, 'movss dword ptr [rbx], xmm12', None, 'velocity x stored back'),
        (0x13AB067, 'movss dword ptr [rbx + 4], xmm11', None, 'velocity y'),
        (0x13AB06D, 'movss dword ptr [rbx + 8], xmm13', None, 'velocity z'),
        (0x13AB073, 'sub rsi, 1', None, 'the next substep'),
    ],
    'network': [
        (0xB9E115, 'cmp dword ptr [rbp + rax*8 + 0x7210], 0x117', None, 'impact handler: each projectile system'),
        (0xB9E130, 'lea rax, [r14 + 0x3c]', None, 'the per-slot shot ids (+0x3C + slot*4)'),
        (0xB9E134, 'cmp dword ptr [rax], esi', None, 'the slot whose shot id is the message\'s'),
        (0xB9E13E, 'cmp ebx, 0x800', None, 'over the 2048 slots'),
        (0xB9E161, 'movsd qword ptr [rcx + r14 + 0x304c], xmm0', None, 'its velocity (x, y) from the message'),
        (0xB9E16B, 'mov dword ptr [rcx + r14 + 0x3054], eax', None, 'and z'),
        (0xB9E156, 'mov r8, r12', None, 'the explosion position: the message\'s'),
        (0xB9E1C7, 'call 0x13b06c0', None, 'the explosion step for that copy'),
        (0xB9E1D1, 'call 0x13a8700', None, 'then the copy ends'),
        (0xBBAF2E, 'movsd qword ptr [rcx + r14 + 0x304c], xmm10', None, 'second handler: velocity (x, y)'),
        (0xBBAF56, 'call 0x13b06c0', None, 'the explosion step'),
        (0xBBAF60, 'call 0x13a8700', None, 'the copy ends'),
    ],
}

# The census (proof 7): every pool-relative store to a flight record's velocity (+0x304C .. +0x3057 from the
# projectile system) in game.dll's .text, and every rdi/rbx-relative velocity store inside the update and the
# integrator.
CENSUS_STORES = {
    0x8A580C: 'velocity x, y (outside the projectile system; not traced)',
    0x8A5815: 'velocity z (outside the projectile system; not traced)',
    0xB9E161: 'network impact handler: the message velocity',
    0xB9E16B: 'network impact handler: the message velocity',
    0xBBAF2E: 'second network impact handler: the message velocity',
    0xBBAF38: 'second network impact handler: the message velocity',
    0x13A9C5B: 'SpawnProjectile: the slot\'s flight record cleared',
    0x13A9E75: 'SpawnProjectile: direction x speed',
    0x13A9E7F: 'SpawnProjectile: direction x speed',
    0x13A9EA3: 'SpawnProjectile: plus the spawn extra\'s velocity',
    0x13A9EBC: 'SpawnProjectile: plus the spawn extra\'s velocity',
    0x13A9ED5: 'SpawnProjectile: plus the spawn extra\'s velocity',
    0x13A9FA6: 'SpawnProjectile: plus the source\'s velocity (row +0xF0 bit 0)',
    0x13A9FBD: 'SpawnProjectile: plus the source\'s velocity (row +0xF0 bit 0)',
    0x13A9FC7: 'SpawnProjectile: plus the source\'s velocity (row +0xF0 bit 0)',
    0x13B05D0: 'hit path: the new direction (ricochet / pass-through)',
    0x13B05D9: 'hit path: the new direction (ricochet / pass-through)',
    0x13B10E0: 'hit path: the new direction (ricochet / pass-through)',
    0x13B110A: 'hit path: the new direction (ricochet / pass-through)',
}
LOCAL_STORES = {
    0x13AB53F: 'the update, unit-driven: from the displacement', 0x13AB544: 'the update, unit-driven',
    0x13AB549: 'the update, unit-driven',
    0x13AB062: 'the integrator', 0x13AB067: 'the integrator', 0x13AB06D: 'the integrator',
}
UPDATE_RANGE = (0x13AB11C, 0x13AC100)
INTEGRATOR_RANGE = (0x13AAE30, 0x13AB0DC)
VELOCITY_DISPLACEMENTS = ('+ 0x304c]', '+ 0x3050]', '+ 0x3054]')


def first_operand(operands: str) -> str:
    return operands.split(',')[0]


def census(image) -> dict:
    pool_stores, local_stores = {}, {}
    for rva, size, mnemonic, operands in image.sweep():
        destination = first_operand(operands)
        if mnemonic in ('cmp', 'test') or '[' not in destination:
            continue
        if any(d in destination for d in VELOCITY_DISPLACEMENTS) and 'rsp' not in destination \
                and 'rbp' not in destination and '*' not in destination and destination.count('+') == 2:
            pool_stores[rva] = mnemonic + ' ' + operands
        in_update = UPDATE_RANGE[0] <= rva < UPDATE_RANGE[1]
        in_integrator = INTEGRATOR_RANGE[0] <= rva < INTEGRATOR_RANGE[1]
        if in_update and destination in ('dword ptr [rdi + 0xc]', 'dword ptr [rdi + 0x10]', 'dword ptr [rdi + 0x14]',
                'qword ptr [rdi + 0xc]'):
            local_stores[rva] = mnemonic + ' ' + operands
        if in_integrator and destination in ('dword ptr [rbx]', 'dword ptr [rbx + 4]', 'dword ptr [rbx + 8]'):
            local_stores[rva] = mnemonic + ' ' + operands
    if sorted(pool_stores) != sorted(CENSUS_STORES) or sorted(local_stores) != sorted(LOCAL_STORES):
        raise ValueError('the velocity store census changed: pool %r, local %r' % (
            {('%X' % k): v for k, v in pool_stores.items()}, {('%X' % k): v for k, v in local_stores.items()}))
    return {'pool': [{'rva': rva, 'asm': pool_stores[rva], 'role': CENSUS_STORES[rva]} for rva in sorted(pool_stores)],
        'local': [{'rva': rva, 'asm': local_stores[rva], 'role': LOCAL_STORES[rva]} for rva in sorted(local_stores)],
        'updateRange': list(UPDATE_RANGE), 'integratorRange': list(INTEGRATOR_RANGE)}


def observe(name: str, pool: dict) -> dict:
    mem = base.Mem(name)
    system = mem.ptr(mem.game + SYSTEM_GLOBAL)
    counter = mem.u32(system + pool['counter'])
    flags = struct.unpack('<2048H', mem.read(system + pool['flags']['base'], 4096))
    flying, unit_driven, faster = 0, 0, 0
    largest = 0.0
    for slot in range(pool['slots']):
        if not flags[slot] & FLAGS['inFlight']:
            continue
        record = mem.read(system + pool['flight']['base'] + slot * pool['flight']['stride'], FLIGHT['read'])
        velocity = struct.unpack_from('<3f', record, FLIGHT['velocity'])
        speed = struct.unpack_from('<f', record, FLIGHT['speed'])[0]
        unit = struct.unpack_from('<I', record, FLIGHT['unit'])[0]
        length = math.sqrt(sum(v * v for v in velocity))
        if not all(math.isfinite(v) for v in velocity):
            raise ValueError('a non-finite velocity in %s slot %d' % (name, slot))
        flying += 1
        unit_driven += 1 if unit else 0
        if speed > 0 and length > speed * 1.5:
            faster += 1
        largest = max(largest, length)
    mem.close()
    return {'snapshot': name, 'counter': counter, 'inFlight': flying, 'unitDriven': unit_driven,
        'fasterThanSpawnSpeedTimes1_5': faster, 'largestSpeed': round(largest, 3)}


def build() -> dict:
    pool = json.loads(POOL_RESEARCH.read_text(encoding='utf-8'))['pool']
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    observations = [observe(name, pool) for name in SNAPSHOTS]
    return {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'pool': {'research': POOL_RESEARCH.name, 'flight': FLIGHT, 'flags': FLAGS, 'shotIds': SHOT_IDS},
        'semantics': {
            'velocity': 'flight +0x0C (3 x f32, m/s): the velocity the next ballistic step integrates; written before '
                'the update it is the direction the projectile flies that step',
            'unit': 'flight +0x50 (u32 unit id): non-zero = a unit drives the projectile (its velocity is recomputed '
                'from the unit each step; never steered)',
            'carriedTime': 'flight +0x18 (f32 s): step time carried into the next update, then cleared',
            'speed': 'flight +0x2C (f32 m/s): the spawn speed; the update ends a projectile whose |velocity| falls '
                'below a fraction of it, so steering keeps |velocity|',
            'noMotion': 'flags bit 0: the update skips the step (only the lifetime counts down)',
            'hitTest': 'each step is hit-tested from the position before it to the integrated position',
            'multiplayer': 'each machine flies its own copy; the shooter\'s impact message makes every other machine '
                'explode its copy at the shooter\'s impact position'},
        'proofs': proofs, 'census': census(image), 'pinnedBytesMismatchPerSnapshot': relocation,
        'observations': observations,
        'unproven': [
            'Live: a steered projectile flies and hits along its new path (the integrator and hit-test proofs say it '
                'must; nothing has been measured in game).',
            'Live multiplayer: another machine draws the shot flying straight and its impact where the shooter\'s '
                'copy hit (the impact handlers are traced, not observed).',
            'The velocity store at 0x8A580C (outside the projectile system) is not traced.',
            'What the ballistic substep count (flight +0x48) depends on.'],
        'writes': 0, 'protectionChanges': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    body = json.dumps(build(), indent=1) + '\n'
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != body:
            raise SystemExit('stale: ' + OUTPUT.relative_to(ROOT).as_posix())
        print('up to date')
        return
    OUTPUT.write_text(body, encoding='utf-8', newline='\n')
    report = json.loads(body)
    print(json.dumps({'pins': sum(len(v) for v in report['proofs'].values()),
        'census': {k: len(v) for k, v in report['census'].items() if isinstance(v, list)},
        'observations': report['observations']}, indent=1))


if __name__ == '__main__':
    main()
