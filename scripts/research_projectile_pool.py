"""The projectile system's pool as Runtime reads it (read-only) for weapon projectile replacement
(docs/custom-projectile-rows.md#weapon-projectile-replacement).

Proves on build F5FEE03DCFDB, from the game.dll image and the four retained mission snapshots:

1. The spawn counter. SpawnProjectile (0x13A9830) reads system +0x30, stores it plus one and takes slot = counter &
   0x7FF of the 2048-slot pool (0x13A986A..0x13A98F4). It skips a slot only while an explosion of its previous
   projectile is still pending (hit record +0x80 or +0x7C, 0x13A991F / 0x13A9937), incrementing the counter again for
   each skip. So the slots spawned since a previous counter value c are (c .. counter - 1) & 0x7FF, and a projectile
   type without explosions is never skipped into.
2. What a slot holds (every member written by SpawnProjectile from its descriptor):
   * the type array +0xE5040 + slot*4: row +0 (0x13A9BB5);
   * the flight record +0x3040 + slot*0x70: +0x00 the position (descriptor +0x00, 0x13A9E3D / 0x13A9E4D), +0x0C the
     velocity = direction x speed (descriptor +0x08, 0x13A9E59..0x13A9E7F), +0x30 the distance travelled (zeroed at
     spawn, 0x13AA0BB; the update adds each step's length, 0x13AB80E / 0x13AB813), +0x34 the remaining lifetime
     (0x13AA13F; the update counts it down only while it is above 0, so 0 means no time limit, 0x13AB82D..0x13AB83C);
   * the source record +0x3B040 + slot*0x24: +0x0C the source entity (descriptor +0x18, 0x13AA4EA / 0x13AA4EE);
   * the hit record +0x4D040 + slot*0xC8: +0x00 the creditor peer (descriptor +0x20, 0x13AA78B / 0x13AA78F) and
     +0x08 the owner entity (descriptor +0x1C, 0x13AA784 / 0x13AA788).
   The update visits a slot only while its flags (+0x203C + slot*2) have bit 1 (0x13AB250). A finished projectile's
   records are left as they are until the slot is spawned into again.
3. In the mission snapshots the counter grows (0, 331, 768, 1005), and the newest slots hold finite positions, a
   non-zero velocity (near the stored speed; a projectile can also inherit its source's velocity, row +0xF0 bit 0), a
   distance travelled, the local peer as creditor and an owner and source entity.
4. The impact explosion is the projectile's OWN COPY (research/docs/gas-eat-F5FEE03DCFDB.md): SpawnProjectile copies
   row +0x90 into hit record +0x7C (0x13AA646 / 0x13AA64C), the only store to it (the census below). On impact the
   update reads that copy, never the row: with no arming distance the impact path calls the explosion step with the
   override flag 0 (0x13AED9B / 0x13AEDA7), which skips a projectile whose impact was already requested (+0xB9,
   0x13B070F), takes the explosion type from +0x7C (0x13B0736), marks +0xB9 (0x13B073D) and requests it with the
   projectile's own creditor (hit +0x00), owner (hit +0x08) and source (source record +0x0C), 0x13B09DC..0x13B0A00.
   The fuse path copies +0x7C into +0x80 (0x13AEDB4 / 0x13AEDC6); the other readers only test it against zero. A
   slot whose impact explosion is pending is never spawned into (0x13A9937). So one 4-byte write of +0x7C on a
   projectile in flight changes the explosion THAT projectile requests on impact, and nothing else: its row, its
   type, every other projectile and every shared definition stay as they are. The census proves every pool-relative
   access to +0x7C, +0x80 and +0xB9, and every store to a +0x7C member in the projectile system's code.

Output: research/projectile-pool-F5FEE03DCFDB.json.
"""
from __future__ import annotations

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

OUTPUT = ROOT / 'research/projectile-pool-F5FEE03DCFDB.json'
SNAPSHOTS = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
SYSTEM_GLOBAL, SESSION_GLOBAL, LOCAL_PEER = 0x347CEA8, 0x347CEF0, 0xB398
POOL = {'active': 0x28, 'counter': 0x30, 'slots': 2048, 'mask': 0x7FF,
    'flags': {'base': 0x203C, 'stride': 2, 'inFlight': 2},
    'types': {'base': 0xE5040, 'stride': 4},
    'flight': {'base': 0x3040, 'stride': 0x70, 'position': 0x00, 'velocity': 0x0C, 'speed': 0x2C, 'distance': 0x30,
        'lifetime': 0x34},
    'source': {'base': 0x3B040, 'stride': 0x24, 'entity': 0x0C},
    'hit': {'base': 0x4D040, 'stride': 0xC8, 'creditor': 0x00, 'owner': 0x08, 'impactExplosion': 0x7C,
        'expiryExplosion': 0x80, 'impactRequested': 0xB9},
    # The row members whose copies (hit record +0x7C, +0x80) make SpawnProjectile skip a slot while they are pending:
    # a carrier must have neither, so it is never skipped into.
    'explosions': {'impact': 0x90, 'expiry': 0x9C}}

PROOFS = {
    'counter': [
        (0x13A9854, 'cmp byte ptr [rcx + 0x28], 0', None, 'SpawnProjectile: nothing unless the system is active'),
        (0x13A986A, 'mov eax, dword ptr [rcx + 0x30]', None, 'the spawn counter'),
        (0x13A9885, 'mov r12d, eax', None, 'the slot'),
        (0x13A9890, 'lea edx, [rax + 1]', None, 'counter + 1'),
        (0x13A989B, 'and r12d, 0x7ff', None, 'slot = counter & 0x7FF (2048 slots)'),
        (0x13A98F4, 'mov dword ptr [rcx + 0x30], edx', None, 'stored back'),
        (0x13A991F, 'cmp dword ptr [r9 + rsi + 0x4d0c0], ebx', None, 'a slot is skipped only while its expiry '
            'explosion (hit record +0x80) is pending'),
        (0x13A9937, 'cmp dword ptr [r9 + rsi + 0x4d0bc], ebx', None, 'or its impact explosion (hit record +0x7C)'),
        (0x13A9941, 'mov r12d, edx', None, 'next slot'),
        (0x13A9949, 'and r12d, 0x7ff', None, 'slot = counter & 0x7FF'),
        (0x13A9950, 'mov dword ptr [rsi + 0x30], edx', None, 'the counter advances once more per skipped slot'),
    ],
    'slot': [
        (0x13A9BB5, 'mov dword ptr [rsi + r12*4 + 0xe5040], ecx', None, 'type array: row +0'),
        (0x13A9C34, 'imul r15, rdi, 0x70', None, 'flight record stride 0x70'),
        (0x13A9C49, 'mov word ptr [rsi + r12*2 + 0x203c], dx', None, 'slot flags'),
        (0x13A9E30, 'mov rax, qword ptr [r14]', None, 'descriptor +0x00: the position'),
        (0x13A9E3D, 'movsd qword ptr [r15 + rsi + 0x3040], xmm0', None, 'flight +0x00: position x, y'),
        (0x13A9E4D, 'mov dword ptr [r15 + rsi + 0x3048], eax', None, 'flight +0x08: position z'),
        (0x13A9E55, 'mov rax, qword ptr [r14 + 8]', None, 'descriptor +0x08: the direction'),
        (0x13A9E59, 'mulss xmm0, dword ptr [rax + 8]', None, 'times the speed'),
        (0x13A9E75, 'movsd qword ptr [r15 + rsi + 0x304c], xmm0', None, 'flight +0x0C: velocity x, y'),
        (0x13A9E7F, 'mov dword ptr [r15 + rsi + 0x3054], eax', None, 'flight +0x14: velocity z'),
        (0x13AA0BB, 'mov dword ptr [r15 + rsi + 0x3070], ebx', None, 'flight +0x30: distance travelled = 0'),
        (0x13AA0C3, 'movss dword ptr [r15 + rsi + 0x306c], xmm6', None, 'flight +0x2C: speed'),
        (0x13AA13F, 'movss dword ptr [r15 + rsi + 0x3074], xmm1', None, 'flight +0x34: lifetime'),
        (0x13AA4DF, 'lea rdx, [r12 + r12*8]', None, 'source record stride 0x24'),
        (0x13AA4EA, 'mov eax, dword ptr [r14 + 0x18]', None, 'descriptor +0x18: the source entity'),
        (0x13AA4EE, 'mov dword ptr [rsi + rdx*4 + 0x3b04c], eax', None, 'source record +0x0C'),
        (0x13AA603, 'lea rdi, [rsi + 0x4d040]', None, 'hit records'),
        (0x13AA60A, 'imul rax, rax, 0xc8', None, 'hit record stride 0xC8'),
        (0x13AA784, 'mov eax, dword ptr [r14 + 0x1c]', None, 'descriptor +0x1C: the owner entity'),
        (0x13AA788, 'mov dword ptr [rdi + 8], eax', None, 'hit record +0x08'),
        (0x13AA78B, 'mov rax, qword ptr [r14 + 0x20]', None, 'descriptor +0x20: the creditor peer'),
        (0x13AA78F, 'mov qword ptr [rdi], rax', None, 'hit record +0x00'),
        (0x13AA646, 'mov ecx, dword ptr [rax + 0x90]', None, 'row +0x90 impact explosion'),
        (0x13AA64C, 'mov dword ptr [rdi + 0x7c], ecx', None, 'hit record +0x7C (pending: the slot is skipped)'),
        (0x13AA653, 'mov ecx, dword ptr [rax + 0x9c]', None, 'row +0x9C expiry explosion'),
        (0x13AA659, 'mov dword ptr [rdi + 0x80], ecx', None, 'hit record +0x80 (pending: the slot is skipped)'),
    ],
    'update': [
        (0x13AB11C, 'xorps xmm12, xmm12', None, 'projectile update: xmm12 = 0'),
        (0x13AB120, 'mov rbx, rcx', None, 'rbx = the projectile system'),
        (0x13AB250, 'test byte ptr [rbx + rsi*2 + 0x203c], 2', None, 'a slot is updated only while flags bit 1 is set'),
        (0x13AB25E, 'imul r13, rsi, 0x70', None, 'its flight record'),
        (0x13AB262, 'lea rdi, [rbx + 0x3040]', None, 'flight records'),
        (0x13AB80E, 'addss xmm1, dword ptr [rdi + 0x30]', None, 'distance travelled + this step\'s length'),
        (0x13AB813, 'movss dword ptr [rdi + 0x30], xmm1', None, 'stored'),
        (0x13AB82D, 'movss xmm0, dword ptr [rdi + 0x34]', None, 'the lifetime'),
        (0x13AB832, 'comiss xmm0, xmm12', None, 'compared with 0'),
        (0x13AB836, 'jbe 0x13abb30', None, 'not above 0: no countdown (no time limit)'),
        (0x13AB83C, 'subss xmm0, xmm15', None, 'otherwise counted down by the step time'),
    ],
    'impact': [
        (0x13AED1D, 'mov ecx, dword ptr [r14 + 0x7c]', None, 'impact path: the projectile\'s own impact explosion copy'),
        (0x13AED9B, 'mov byte ptr [rsp + 0x28], 0', None, 'with no arming distance: the override flag 0 (the copy is used)'),
        (0x13AEDA7, 'call 0x13b06c0', None, 'the explosion step for this projectile'),
        (0x13AEDB4, 'mov eax, dword ptr [r14 + 0x7c]', None, 'the fuse path reads the copy'),
        (0x13AEDC6, 'mov dword ptr [r14 + 0x80], eax', None, 'and stores it as the pending expiry explosion'),
        (0x13B070F, 'cmp byte ptr [rdi + rcx + 0x4d0f9], 0', None, 'explosion step: once only (hit +0xB9 impact requested)'),
        (0x13B0736, 'mov esi, dword ptr [rdi + rcx + 0x4d0bc]', None, 'the explosion type = hit record +0x7C'),
        (0x13B073D, 'mov byte ptr [rdi + rcx + 0x4d0f9], 1', None, 'marks the impact requested'),
        (0x13B09DC, 'mov rax, qword ptr [rdi + rbx + 0x4d040]', None, 'the explosion\'s creditor = hit record +0x00'),
        (0x13B09E9, 'mov eax, dword ptr [rdi + rbx + 0x4d048]', None, 'its owner = hit record +0x08'),
        (0x13B09F8, 'mov r9d, dword ptr [rbx + rax*4 + 0x3b04c]', None, 'its source = source record +0x0C'),
        (0x13B0A00, 'call 0x13c0a80', None, 'RequestExplosion'),
    ],
}

# The census (proof 4): every pool-relative access to hit +0x7C, +0x80 and +0xB9 in game.dll, and every store to a
# non-stack +0x7C member in the projectile system's code (SpawnProjectile, the update, the explosion step).
CENSUS_RANGE = (0x13A8000, 0x13B2000)
CENSUS_POOL = {0x13A991F: 'read', 0x13A9937: 'read', 0x13AB6F4: 'read', 0x13ABA84: 'read', 0x13ABAD2: 'read',
    0x13ABB64: 'read', 0x13B070F: 'read', 0x13B0736: 'read', 0x13B073D: 'write +0xB9 (impact requested)'}
CENSUS_STORES = {0x13AA64C: 'SpawnProjectile: row +0x90 -> hit +0x7C'}


def observe(name: str) -> dict:
    mem = base.Mem(name)
    system = mem.ptr(mem.game + SYSTEM_GLOBAL)
    session = mem.ptr(mem.game + SESSION_GLOBAL)
    peer = mem.u64(session + LOCAL_PEER) if session else None
    active = mem.read(system + POOL['active'], 1)[0]
    counter = mem.u32(system + POOL['counter'])
    flags = struct.unpack('<2048H', mem.read(system + POOL['flags']['base'], 4096))
    types = struct.unpack('<2048I', mem.read(system + POOL['types']['base'], 8192))
    newest = []
    for back in range(1, min(counter, 8) + 1):
        slot = (counter - back) & POOL['mask']
        flight = mem.read(system + POOL['flight']['base'] + slot * POOL['flight']['stride'], 0x38)
        hit = mem.read(system + POOL['hit']['base'] + slot * POOL['hit']['stride'], 0x10)
        source = mem.read(system + POOL['source']['base'] + slot * POOL['source']['stride'], 0x10)
        position = struct.unpack_from('<3f', flight, 0)
        velocity = struct.unpack_from('<3f', flight, 0x0C)
        speed, distance, lifetime = struct.unpack_from('<3f', flight, 0x2C)
        creditor, owner = struct.unpack_from('<QI', hit, 0)
        newest.append({'slot': slot, 'type': types[slot], 'flags': flags[slot],
            'position': [round(v, 3) for v in position], 'velocity': round(math.sqrt(sum(v * v for v in velocity)), 3),
            'speed': round(speed, 3), 'distance': round(distance, 3), 'lifetime': round(lifetime, 3),
            'creditorIsLocalPeer': creditor == peer, 'owner': owner,
            'source': struct.unpack_from('<I', source, 0x0C)[0]})
    mem.close()
    return {'snapshot': name, 'active': active, 'counter': counter, 'inFlight': sum(1 for f in flags if f & 2),
        'newest': newest}


def main():
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
    pool_refs, stores = {}, {}
    for rva, size, mnemonic, operands in image.sweep():
        if '0x4d0bc]' in operands or '0x4d0c0]' in operands or '0x4d0f9]' in operands:
            pool_refs[rva] = mnemonic + ' ' + operands
        if CENSUS_RANGE[0] <= rva < CENSUS_RANGE[1] and '+ 0x7c]' in operands and 'rsp' not in operands:
            first = operands.split(',')[0]
            if '+ 0x7c]' in first and mnemonic not in ('cmp', 'test'):
                stores[rva] = mnemonic + ' ' + operands
    if sorted(pool_refs) != sorted(CENSUS_POOL) or sorted(stores) != sorted(CENSUS_STORES):
        raise ValueError('the impact explosion census changed: pool %r, stores %r' % (
            {('%X' % k): v for k, v in pool_refs.items()}, {('%X' % k): v for k, v in stores.items()}))
    census = {'range': list(CENSUS_RANGE),
        'pool': [{'rva': rva, 'asm': pool_refs[rva], 'role': CENSUS_POOL[rva]} for rva in sorted(pool_refs)],
        'stores': [{'rva': rva, 'asm': stores[rva], 'role': CENSUS_STORES[rva]} for rva in sorted(stores)]}

    observations = [observe(name) for name in SNAPSHOTS]
    counters = [o['counter'] for o in observations]
    if counters != sorted(counters) or counters[0] != 0:
        raise ValueError('the spawn counter does not grow from the mission start: %r' % counters)
    for observation in observations:
        for slot in observation['newest']:
            if not (0 < slot['type'] < 351 and all(math.isfinite(v) and abs(v) < 100000 for v in slot['position'])
                    and 0 < slot['velocity'] < 100000 and slot['distance'] >= 0
                    and slot['creditorIsLocalPeer'] and slot['owner'] and slot['source']):
                raise ValueError('an implausible newest slot in %s: %r' % (observation['snapshot'], slot))

    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'system': {'global': SYSTEM_GLOBAL}, 'session': {'global': SESSION_GLOBAL, 'localPeer': LOCAL_PEER},
        'pool': POOL,
        'semantics': {
            'counter': 'u32 spawn counter: +1 per spawned projectile and per skipped slot; 0 at mission start',
            'skip': 'a slot is skipped only while an explosion of its previous projectile is pending, so a type '
                'without impact and expiry explosions is never skipped into',
            'distance': 'f32 path length travelled since spawn (0 at spawn)',
            'lifetime': 'f32 remaining lifetime; 0 or less is never counted down (no time limit)',
            'finished': 'a finished projectile clears flags bit 1 and leaves its records until the slot is reused',
            'impact': 'hit record +0x7C is the projectile\'s own copy of its row\'s impact explosion, made at spawn and '
                'the only value the impact reads (u32 explosion type; 0 = none); +0xB9 is set once its impact explosion '
                'is requested'},
        'proofs': proofs, 'census': census, 'pinnedBytesMismatchPerSnapshot': relocation, 'observations': observations,
        'unproven': ['Whether the weapon update runs before or after the projectile update in a game update: the '
            'distance travelled lets Runtime go back to the spawn point either way.',
            'The meaning of the other slot flag bits.',
            'Whether a shot fired by another player is spawned in the host\'s pool.',
            'Multiplayer: a peer that receives the owner\'s impact message explodes its OWN copy\'s +0x7C (the '
                'handlers 0xB9E0C0 / 0xBBADE0, traced, not pinned): a +0x7C written on the host only is not seen by '
                'other machines.'],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'counters': counters, 'pins': len(pins),
        'newest': [(o['snapshot'][13:40], [(s['type'], s['owner'], s['source']) for s in o['newest'][:3]])
            for o in observations]}, indent=1))


if __name__ == '__main__':
    main()
