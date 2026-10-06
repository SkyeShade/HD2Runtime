"""Native limb heal and velocity of the local player's avatar (research for hd2.actions.heal_limb / add_velocity).

Read-only: nothing writes, nothing touches a live process. Proves, on build F5FEE03DCFDB, from the unpacked game.dll
held by the retained mission snapshots:

1. RestoreZone 0x65B2D0(ignored, entity, zone name) restores ONE damage zone of an entity: it finds the entity's
   health record (health manager game+0x3326688), resolves the zone index by its name (0x921A80; -1 when the
   settings have no such zone, which RestoreZone does NOT check), sets that zone's health to the zone's settings
   health (zone +0xE8), clears the zone's 2-bit state (an injured limb becomes healthy), commits the new states
   through 0x925F10 (the same commit the game's heal uses) and, for an entity this machine owns, sends them to the
   other machines (0xBDF5E0). Main health is not touched. The game's own callers restore single zones (0x65A7C0,
   0x65AB40, 0xB72B80) or a list of zone names (0x65B040 and 0xB73320, reached from an ability handler 0x11B2DF0).
2. AddHealthFraction 0x91E920 (Runtime's existing hd2.actions.heal) also heals EVERY zone of an owned entity by the same
   fraction of each zone's health and clears the state of any zone that rises above 0, committed through 0x925F10:
   a partial heal of all limbs, never of one. RestoreHealth 0x91E500 (the stim / revive path) sets main health and
   every zone from a fraction and zeroes all zone states directly. No native function heals one zone partially.
3. SetVelocity 0x4A7550(ignored, entity, const float v[3]) sets an entity's MotionComponent velocity: the motion
   manager (game+0x3326558; entity hash at +0x48A0, descriptors +0x48B8, records +0x48C8 stride 0x84 with the
   velocity at +0x00, a second array +0x48D0 stride 0xA4 with the velocity at +0x0C and its length at +0x48). It does
   NOT check that the entity has a motion record (an unknown entity indexes record -1). The game's own callers: the
   Warp Pack zeroes the velocity after teleporting (0x88D790 SetPosition, 0x88D7B1 SetVelocity), and an avatar
   locomotion transition (0xA50890) launches the avatar with SetVelocity(5.8 m/s along a direction + 3.3 m/s up) and
   then sets the motion record's flag +0x0D (0x5A3D80). The jump pack adds its thrust straight into the same
   velocity (+0x00..+0x08) every frame, on the machine that owns the pack only (0x9B4BD0).
4. Snapshots: in every mission snapshot the local avatar has a motion record that names it, owned by this machine,
   and its live health settings carry the six zone names Runtime restores. In the "alive" capture the avatar was
   moving: its motion velocity is about 3.5 m/s (0.70, -3.36, -0.80), the second array's a slightly different value,
   so the record is the avatar's live movement velocity (ground locomotion drives it).

Requires the research-only package capstone.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import research_player_injury as injury  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/player-avatar-actions-F5FEE03DCFDB.json'
SNAPSHOTS = injury.SNAPSHOTS
G_HEALTH, G_MOTION, G_NETWORK = 0x3326688, 0x3326558, 0x346BF98
RESTORE_ZONE, SET_VELOCITY = 0x65B2D0, 0x4A7550
MOTION = {'capacity': 0x4880, 'hash': 0x48A0, 'descriptors': 0x48B8, 'records': 0x48C8, 'stride': 0x84,
    'velocity': 0x00, 'second': 0x48D0, 'secondStride': 0xA4}
ZONE_NAMES = {'head': 0x8C5570C9, 'body': 0xAA1DB0B0, 'arm_left': 0x1880288E, 'arm_right': 0xB6F2BAF5,
    'leg_left': 0x64A3FA1D, 'leg_right': 0x87B05FF4}
LAUNCH = {'horizontal': 5.8, 'up': 3.3}

GAME_PROOFS = {
    'restoreZone': [
        (0x65B2D0, 'mov qword ptr [rsp + 8], rbx', None, 'RestoreZone(ignored, u32 entity, u32 zone name)'),
        (0x65B2FD, 'cmp edx, dword ptr [rip + {rip}]', 0x3483C20, 'the invalid entity: no record'),
        (0x65B303, 'mov esi, r8d', None, 'esi = zone name (argument 3)'),
        (0x65B306, 'mov r15, qword ptr [rip + {rip}]', G_HEALTH, 'the health manager'),
        (0x65B30D, 'mov ebx, edx', None, 'ebx = entity (argument 2)'),
        (0x65B39A, 'mov rcx, r15', None, ''),
        (0x65B3A0, 'call 0x921a80', None, 'zone index by name (-1 when absent; not checked here)'),
        (0x65B3A5, 'mov r9d, eax', None, ''),
        (0x65B3AD, 'imul rcx, r9, 0x228', None, 'zone stride'),
        (0x65B3B4, 'mov edx, dword ptr [rcx + r14 + 0x2f0]', None, 'the zone\'s settings health (zone +0xE8)'),
        (0x65B3BC, 'mov dword ptr [rbp + r9*4 + 0xf8], edx', None, 'zone health = full'),
        (0x65B3FD, 'and qword ptr [r8], rax', None, 'the zone\'s 2-bit state cleared (in the state copy)'),
        (0x65B44E, 'call 0x925f10', None, 'zone states committed (as the heal commits them)'),
        (0x65B46A, 'test byte ptr [rax + 0x14], 1', None, 'an owned entity ...'),
        (0x65B490, 'call 0xbdf5e0', None, '... sends the new states'),
        (0x921B2D, 'add rax, 0x268', None, 'zone lookup: zone name (settings +0x208 + zone +0x60)'),
        (0x921B33, 'cmp dword ptr [rax], edi', None, 'the name matches'),
        (0x921B44, 'mov eax, 0xffffffff', None, 'no such zone: -1'),
        (0x65B1DD, 'call 0x921a80', None, 'a game caller (zone list) ...'),
        (0x65B1E7, 'call 0x65b2d0', None, '... restores each listed zone'),
        (0x11B2E9E, 'call 0x65b040', None, 'an ability-area handler restores its zone list'),
    ],
    'healAllZones': [
        (0x91EA17, 'test byte ptr [r12 + 0x14], 1', None, 'AddHealthFraction: owned entities only ...'),
        (0x91EBD6, 'lea r12, [r13 + 0xf8]', None, '... heal every zone'),
        (0x91EC22, 'mov dword ptr [r12], edx', None, 'zone health += fraction x zone health (clamped)'),
        (0x91EC26, 'test ecx, ecx', None, 'was at or below 0 ...'),
        (0x91EC2C, 'jle 0x91ec66', None, '... and is above 0 now'),
        (0x91EC4C, 'and qword ptr [rbp + rdx*8 + 0xf], rax', None, 'state cleared'),
        (0x91EC86, 'cmp esi, 0x26', None, '38 zones'),
        (0x91ECDF, 'call 0x925f10', None, 'committed'),
        (0x91E687, 'movups xmmword ptr [r14 + 0x20], xmm0', None, 'RestoreHealth zeroes every zone state'),
    ],
    'setVelocity': [
        (0x4A7550, 'mov qword ptr [rsp + 0x18], rbx', None, 'SetVelocity(ignored, u32 entity, const float v[3])'),
        (0x4A755A, 'cmp edx, dword ptr [rip + {rip}]', 0x3483C20, 'the invalid entity'),
        (0x4A7560, 'mov rbx, qword ptr [rip + {rip}]', G_MOTION, 'the motion manager'),
        (0x4A7578, 'mov r9d, dword ptr [rbx + 0x48a8]', None, 'motion hash capacity'),
        (0x4A7581, 'mov r10d, dword ptr [rbx + 0x48b0]', None, 'motion hash multiplier'),
        (0x4A759A, 'mov r11, qword ptr [rbx + 0x48a0]', None, 'motion hash buckets'),
        (0x4A75A1, 'mov edi, dword ptr [rbx + 0x48ac]', None, 'motion hash empty key'),
        (0x4A75D4, 'mov eax, 0xffffffff', None, 'no record: -1, used unchecked'),
        (0x4A75DE, 'mov rcx, qword ptr [rbx + 0x48c8]', None, 'motion records'),
        (0x4A75FC, 'imul rdx, r8, 0x84', None, 'record stride 0x84'),
        (0x4A7603, 'movsd qword ptr [rcx + rdx], xmm0', None, 'record +0x00: velocity x, y'),
        (0x4A7608, 'mov dword ptr [rcx + rdx + 8], eax', None, 'record +0x08: velocity z'),
        (0x4A75F5, 'imul rdi, r8, 0xa4', None, 'second array stride 0xA4'),
        (0x4A760C, 'mov rcx, qword ptr [rbx + 0x48d0]', None, 'second array'),
        (0x4A7613, 'movsd qword ptr [rcx + rdi + 0xc], xmm0', None, 'second +0x0C: velocity'),
        (0x4A7660, 'movss dword ptr [rbx + rdi + 0x48], xmm0', None, 'second +0x48: speed'),
        (0x5A666F, 'mov edi, dword ptr [rcx + 0x4880]', None, 'motion capacity (grow)'),
        (0x5A2CC3, 'mov rax, qword ptr [r14 + 0x48b8]', None, 'motion descriptors (SetPosition)'),
    ],
    'gameVelocityUse': [
        (0x88D790, 'call 0x5a2bb0', None, 'Warp Pack: SetPosition ...'),
        (0x88D7B1, 'call 0x4a7550', None, '... then SetVelocity (zero)'),
        (0xA511A8, 'movss xmm4, dword ptr [rip + {rip}]', 0x23C7318, 'avatar launch: 3.3 m/s up'),
        (0xA511B4, 'movss xmm3, dword ptr [rip + {rip}]', 0x23C74CC, 'avatar launch: 5.8 m/s along the direction'),
        (0xA5121A, 'call 0x4a7550', None, 'avatar launch: SetVelocity'),
        (0xA51226, 'call 0x5a3d80', None, 'then the motion record flag +0x0D = 1'),
        (0x9B4BD0, 'test byte ptr [rcx + 0x14], 1', None, 'jump pack: only the owner thrusts'),
        (0x9B4BDA, 'mov r11, qword ptr [rip + {rip}]', G_MOTION, 'jump pack: the motion manager'),
        (0x9B4C44, 'imul r13, rcx, 0x84', None, ''),
        (0x9B4C4B, 'add r13, qword ptr [r11 + 0x48c8]', None, 'jump pack: the motion record'),
        (0x9B5176, 'addss xmm0, dword ptr [r13]', None, 'jump pack: velocity += thrust x dt'),
        (0x9B5186, 'movss dword ptr [r13], xmm0', None, ''),
        (0x9B5190, 'movss dword ptr [r13 + 4], xmm3', None, ''),
        (0x9B5196, 'movss dword ptr [r13 + 8], xmm1', None, ''),
    ],
}


def hash_lookup(mem, header, key):
    raw = mem.read(header, 20)
    buckets, capacity, empty, multiplier = struct.unpack('<QIII', raw)
    if not capacity or capacity & (capacity - 1):
        return None
    table = mem.read(buckets, capacity * 8)
    start = (key * multiplier) & 0xFFFFFFFF
    for probe in range(capacity):
        k, value = struct.unpack_from('<II', table, ((start + probe) & (capacity - 1)) * 8)
        if k == key:
            return value
        if k == empty:
            return None
    return None


def shared_settings(mem, type_hash):
    """HealthComponentData of a type through the shared table (0x507430): network root +0xF12B78, 1002 slots."""
    table = mem.ptr(mem.ptr(mem.game + G_NETWORK) + 0xF12B78)
    start = type_hash % 1002
    for step in range(1002):
        k, v = struct.unpack('<QI', mem.read(table + ((start + step) % 1002) * 16, 12))
        if k == type_hash:
            return table + 0x3EA0 + v * 0x5650
        if k == 0:
            return None
    return None


def observe(name):
    mem = base.Mem(name)
    out = {'snapshot': name, 'localAvatar': None}
    avatar = injury.local_avatar(mem)
    motion = mem.ptr(mem.game + G_MOTION)
    out['motionCapacity'] = mem.u32(motion + MOTION['capacity'])
    if avatar is not None:
        manager = mem.ptr(mem.game + G_HEALTH)
        index = injury.health_lookup(mem, manager, avatar)
        descriptor = base.descriptor(mem, mem.ptr(mem.ptr(manager + 0x1048) + 8 * index))
        settings = shared_settings(mem, int(descriptor['type'], 16))
        names = [mem.u32(settings + 0x208 + z * 0x228 + 0x60) for z in range(38)]
        copy = hash_lookup(mem, manager + 0x1070, avatar)
        slot = hash_lookup(mem, motion + MOTION['hash'], avatar)
        mdesc = slot is not None and base.descriptor(mem, mem.ptr(mem.ptr(motion + MOTION['descriptors']) + 8 * slot))
        record = slot is not None and mem.read(mem.ptr(motion + MOTION['records']) + slot * MOTION['stride'], 12)
        second = slot is not None and mem.read(mem.ptr(motion + MOTION['second']) + slot * MOTION['secondStride']
            + 0x0C, 12)
        out['localAvatar'] = {'entity': avatar, 'type': descriptor['type'], 'owned': descriptor['authority'],
            'zoneNames': {key: value in names for key, value in ZONE_NAMES.items()},
            'zoneIndex': {key: names.index(value) for key, value in ZONE_NAMES.items() if value in names},
            'healthInstanceCopy': copy is not None,
            'motion': slot is not None and {'index': slot, 'belowCapacity': slot < out['motionCapacity'],
                'descriptorNamesAvatar': mdesc['entity'] == avatar, 'owned': mdesc['authority'],
                'velocity': [round(v, 4) for v in struct.unpack('<3f', record)],
                'secondVelocity': [round(v, 4) for v in struct.unpack('<3f', second)]}}
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
    if (round(struct.unpack_from('<f', data, 0x23C7318)[0], 4), round(struct.unpack_from('<f', data, 0x23C74CC)[0], 4)
            ) != (LAUNCH['up'], LAUNCH['horizontal']):
        raise ValueError('the avatar launch constants changed')
    restore_prologue, restore_asm = injury.prologue(image, RESTORE_ZONE, 8)
    velocity_prologue, velocity_asm = injury.prologue(image, SET_VELOCITY, 6)
    pins = [p for rows in proofs.values() for p in rows]
    relocation, observations = {}, []
    for name in SNAPSHOTS + list(injury.SHIP_SNAPSHOTS):
        relocation[name] = base.verify_pins_live(name, pins, [])
    for name in SNAPSHOTS:
        observations.append(observe(name))
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    for o in observations:
        a = o['localAvatar']
        if a is None:
            continue
        m = a['motion']
        if not (a['owned'] and all(a['zoneNames'].values()) and m and m['descriptorNamesAvatar'] and m['owned']
                and m['belowCapacity']):
            raise ValueError('the local avatar disagrees in ' + o['snapshot'])
    research = json.loads(injury.OUTPUT.read_text(encoding='utf-8'))
    zone_of = {item['limb']: item['zone'] for item in research['limbs']}
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'restoreZone': {'rva': RESTORE_ZONE, 'prologue': restore_prologue, 'asm': restore_asm,
            'signature': 'void RestoreZone(void *ignored, u32 entity, u32 zone_name)',
            'healthManager': G_HEALTH, 'zones': ZONE_NAMES, 'limbZones': zone_of,
            'effect': 'the zone\'s health = its settings health; its state cleared; committed through 0x925F10; '
                'sent to other machines for an owned entity; main health unchanged',
            'unchecked': ['a zone name the entity\'s settings do not have (index -1)',
                'an entity without a health record']},
        'healAllZones': {'rva': 0x91E920, 'effect': 'AddHealthFraction heals every zone by the fraction of its own '
            'health on an owned entity and clears the state of a zone that rises above 0'},
        'setVelocity': {'rva': SET_VELOCITY, 'prologue': velocity_prologue, 'asm': velocity_asm,
            'signature': 'void SetVelocity(void *ignored, u32 entity, const float v[3])', 'manager': G_MOTION,
            'layout': MOTION, 'gameLaunch': LAUNCH,
            'unchecked': ['an entity without a motion record (record -1)']},
        'proofs': proofs, 'pinnedBytesMismatchPerSnapshot': relocation, 'observations': observations,
        'confidence': {
            'restoreZone': 'CONFIRMED (code): one zone to full, its state cleared, committed like the heal\'s; the '
                'gameplay effect on an avatar (limp, sway gone) is not live-observed.',
            'noPartialZoneHeal': 'STRONG: no function heals one zone by an amount; AddHealthFraction heals every zone '
                'proportionally.',
            'setVelocity': 'CONFIRMED (code): the setter writes the motion velocity the jump pack integrates into.',
            'velocityEffect': 'UNKNOWN: whether ground locomotion overwrites an added velocity the next frame (the '
                'game\'s own launch pairs SetVelocity with a locomotion transition and the motion flag +0x0D).',
            'authority': 'STRONG: the jump pack thrusts and the heal commits only on the owner; RestoreZone sends the '
                'states for an owned entity; avatar movement is simulated by its owner (inferred).',
        },
        'unproven': ['What ground locomotion does with an added velocity (friction, overwrite).',
            'Whether a velocity change on the owner shows on other machines (movement replication not traced).',
            'What a ragdolled avatar does with SetVelocity.',
            'Which gameplay the game\'s own RestoreZone callers implement.'],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'pins': len(pins), 'observations': [o['localAvatar'] for o in observations]}, indent=1))


if __name__ == '__main__':
    main()
