"""Selectable weapon functions: rate-of-fire modes, input bindings, programmable ammunition and rounds feeds. Read-only.

Proves on build F5FEE03DCFDB, from the pinned type library, entity table and entity deltas, game.dll code and the
retained snapshots:

1. Rate of fire is three slots, not one value. ProjectileWeaponComponent +4 is a CApiVector3 whose hidden name has the
   length of rounds_per_minute (17); +16 is the three-slot zeroing_slots (13). Every weapon stores its rate in the
   middle slot (Y, +8: the existing weapon.fire_rate). Weapons whose WeaponData binds the ROF weapon function to an
   input also fill X and/or Z (MG-206 450/600/750, MG-43 630/760/900, M-105 700/850/1150, GL-28 160/240/320,
   AR-61 Tenderizer 0/600/850, VG-70 300/550/750).
2. The ROF selector is data-driven over those three slots (game.dll 0x617960): the projectile_weapon manager
   (global game+0x33266D8) keeps one 0x20-byte record per built weapon at +0x70 (zeroing slots and index, then the
   RPM slots at +0x10 and the current index at +0x1C). Each press sets index = (index + 1) mod 3 and skips a slot whose
   RPM is 0.0, at most three times; the chosen RPM is stored as the weapon's current RPM (+0x80, 12-byte entries, +4)
   and replicated (key 0x4CBCC2A2). A new record starts zeroed (0x551220) and is seeded at build; in every mission
   snapshot the records hold the settings' slots with index 1, so the default is the Y slot and the selector visits
   Y -> Z -> X. The storage is fixed: a fourth rate cannot exist, and a zero slot is an absent mode.
3. Input bindings. WeaponDataComponent +184 function_info {left (+184), right (+188)} binds a WeaponFunctionType to
   each weapon-function input. The weapon-function value getter (0x755BA0) reads the binding from the built weapon's
   weapon_data instance (0x3F0 bytes, +0x350 + 4 * input) and switches over the function type: ROF reads the
   projectile_weapon ROF index, Magazine the weapon_rounds record (manager game+0x3326CF0, capacity 64, 20-byte
   records, +4), Firemode and the 2-bit functions (ProgrammableAmmo = bits 2-3) the weapon_data state.
4. Programmable ammunition (0x615940, the projectile fire path): the caller passes the projectile type it fires; the
   fire path resolves the weapon's ProjectileWeaponComponentData (0x515100: a per-instance resolved copy when one
   exists, else the entity-table record through its 542-row hash index, 0x514C10) and, when the weapon's
   ProgrammableAmmo function state is 1, replaces the type with weapon_function_projectile_type (+576) if it is
   non-zero, and the spawned entity with +584 if that is non-zero. AC-8, GR-8 and RL-77 use exactly this to switch
   between two projectiles; P-33, P-92 and the W.A.S.P. spawn entities through it.
5. Rounds feeds. WeaponRoundsComponent +64 {primary_projectile_type, alternate_projectile_type} (hidden names 23 and
   25) are the two magazines' projectiles, +72 their capacities; the Magazine weapon function switches between them.
   On the SG-20 Halt both members are patched at every build by its default customization (slot 6 FLECHETTES -> +64,
   slot 7 Stun ALTERNATE -> +68), so both feeds exist on every built Halt.
6. No fire-rate, binding or function-projectile member is patched by an ammunition item; the only customization
   deltas that touch the rate slots overwrite all three (Recoil Spring Liberator 0/680/0, Recoil Spring Patriot,
   Laser. Blaster Focus and one unnamed item), and none touches function_info.

Requires the research-only package capstone.
Output: research/weapon-functions-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import research_weapon_fire_modes as fire_modes  # noqa: E402
import research_field_ownership as field_ownership  # noqa: E402
from research_magazine_attachments import DATALIB, DELTAS_SHA, customization_items, entity_deltas, sha  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/weapon-functions-F5FEE03DCFDB.json'
FIRE_MODES = ROOT / 'research/weapon-fire-modes-F5FEE03DCFDB.json'
SOURCES = ROOT / 'research/active-projectile-sources-F5FEE03DCFDB.json'
UNLOCK_LISTS = ROOT / 'research/attachment-unlock-lists-F5FEE03DCFDB.json'
MISSION = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
PROJECTILE_WEAPON, WEAPON_ROUNDS, WEAPON, BEAM_WEAPON = 0x33266D8, 0x3326CF0, 0x3326660, 0x3326A20

FUNCTION_NAMES = {0: 'none', 1: 'zeroing', 2: 'rate_of_fire', 3: 'fire_mode', 4: 'magazine', 5: 'light_mode',
    6: 'laser_guide', 7: 'muzzle_velocity', 8: 'programmable_ammo'}
# Names are published only where the type library alias length matches the reference name (values 9-12 do not).
NATIVE_FUNCTION_NAMES = {0: 'None', 1: 'Zeroing', 2: 'ROF', 3: 'Firemode', 4: 'Magazine', 5: 'LightMode',
    6: 'LaserGuide', 7: 'MuzzleVelocity', 8: 'ProgrammableAmmo'}
ROF, PROGRAMMABLE = 2, 8
# The rate slots of a wind-up weapon (WeaponWindUpComponentData). Proven: the ROF selector record and the ROF value
# reader are generic over every built projectile weapon (one projectile_weapon manager record each, seeded from the
# settings' three slots), and the wind-up routine (0x78A420, research/sentry-components) reads only its own wind-up
# settings (+0 wind-up time, +4 wind-down time, +12 barrel-spin multiplier). Not proven: that the wind-up trigger path
# fires at the selected rate slot once spun up (no built wind-up weapon is in a mission snapshot), and nothing is
# live-tested.
WIND_UP_UNVERIFIED = ('Wind-up weapon: the three rate slots, the ROF selector record (generic over every built '
    'projectile weapon) and the wind-up routine (its own +0/+4/+12 only) are proven, but that the wind-up trigger path '
    'fires at the selected rate slot is not, and editing, adding or selecting rates on a wind-up weapon has not been '
    'gameplay-tested.')
INPUTS = {'left': 184, 'right': 188}
SLOT_NAMES = ('x', 'y', 'z')
# The order the selector visits slots from the default (index 1): Y, Z, X.
SELECTOR_ORDER = (1, 2, 0)

LAYOUT = {
    ('ProjectileWeaponComponent', 0): ('proj_type', 15, 'ProjectileType'),
    ('ProjectileWeaponComponent', 4): ('rounds_per_minute', 17, 'CApiVector3'),
    ('ProjectileWeaponComponent', 16): ('zeroing_slots', 13, 'CApiVector3'),
    ('ProjectileWeaponComponent', 40): ('projectile_entity', 17, None),
    ('ProjectileWeaponComponent', 576): ('weapon_function_projectile_type', 31, 'ProjectileType'),
    ('ProjectileWeaponComponent', 584): ('weapon_function_projectile_entity', 33, None),
    ('WeaponDataComponent', 184): ('function_info', 13, 'WeaponFunctionInfo'),
    ('WeaponFunctionInfo', 0): ('left', 4, 'WeaponFunctionType'),
    ('WeaponFunctionInfo', 4): ('right', 5, 'WeaponFunctionType'),
    ('WeaponRoundsComponent', 64): ('ammo_type', 10, 'WeaponRoundsAmmoType'),
    ('WeaponRoundsComponent', 72): ('magazine_capacity', 17, 'CApiVector2'),
    ('WeaponRoundsAmmoType', 0): ('primary_projectile_type', 23, 'ProjectileType'),
    ('WeaponRoundsAmmoType', 4): ('alternate_projectile_type', 25, 'ProjectileType'),
}

GAME_PROOFS = {
    'managers': [
        (0x569344, 'lea rax, [rbx + 0xf0b3b8]', None, 'component world + 0xF0B3B8'),
        (0x56934B, 'mov qword ptr [rip + {rip}], rax', PROJECTILE_WEAPON, 'is the projectile_weapon manager global'),
        (0x56FF03, 'lea rcx, [rdi + 0xf0b3b8]', None, 'the world dump passes that manager'),
        (0x56FF16, 'call 0x619f70', None, 'to its printer'),
        (0x619F7D, 'lea r8, [rip + {rip}]', 0x22476A0, '"projectile_weapon" : { "max" : %u, "capacity" : 384 }'),
        (0x56882A, 'lea rax, [rbx + 0x757398]', None, 'component world + 0x757398'),
        (0x568831, 'mov qword ptr [rip + {rip}], rax', WEAPON_ROUNDS, 'is the weapon_rounds manager global'),
        (0x56C648, 'mov r9d, dword ptr [rdi + 0x7573a8]', None, 'the world dump prints its max (+0x10)'),
        (0x56C656, 'lea r8, [rip + {rip}]', 0x2249F50, '"weapon_rounds" : { "max" : %u, "capacity" : 64 }'),
        (0x568EAC, 'lea rax, [rbx + 0xe9fc38]', None, 'component world + 0xE9FC38'),
        (0x568EB3, 'mov qword ptr [rip + {rip}], rax', WEAPON, 'is the weapon manager global'),
        (0x56E754, 'mov r9d, dword ptr [rdi + 0xe9fc48]', None, 'the world dump prints its max (+0x10)'),
        (0x56E762, 'lea r8, [rip + {rip}]', 0x2249B30, '"weapon" : { "max" : %u, "capacity" : 384 }'),
        (0x56907A, 'lea rax, [rbx + 0xeb6758]', None, 'component world + 0xEB6758'),
        (0x569081, 'mov qword ptr [rip + {rip}], rax', BEAM_WEAPON, 'is the beam_weapon manager global'),
        (0x56F0A3, 'mov r9d, dword ptr [rdi + 0xeb6780]', None, 'the world dump prints its max (+0x28)'),
        (0x56F0B1, 'lea r8, [rip + {rip}]', 0x224B378, '"beam_weapon" : { "max" : %u, "capacity" : 128 }'),
    ],
    'rateOfFireSelector': [
        (0x617974, 'mov rbx, qword ptr [rip + {rip}]', PROJECTILE_WEAPON, 'the ROF cycle loads the projectile_weapon manager'),
        (0x6179E5, 'shl rdi, 5', None, 'ROF record stride 0x20'),
        (0x6179E9, 'add rdi, qword ptr [rbx + 0x70]', None, 'ROF records at manager +0x70'),
        (0x6179ED, 'mov ecx, dword ptr [rdi + 0x1c]', None, 'current ROF index at record +0x1C'),
        (0x6179F0, 'add ecx, 4', None, 'index + 4'),
        (0x6179E0, 'mov eax, 0xaaaaaaab', None, 'mod 3 (reciprocal): index = (index + 1) mod 3'),
        (0x617A01, 'mov dword ptr [rdi + 0x1c], r8d', None, 'stores the new index'),
        (0x617A05, 'movss xmm0, dword ptr [rdi + rcx*4 + 0x10]', None, 'reads that slot of the RPM Vec3 (record +0x10)'),
        (0x617A0B, 'ucomiss xmm0, xmm1', None, 'a slot whose RPM is 0.0'),
        (0x617A15, 'cmp r9d, 3', None, 'is skipped, at most three times'),
        (0x617A4F, 'movss xmm6, dword ptr [rdi + rbp*4 + 0x10]', None, 'the selected RPM'),
        (0x617AAD, 'mov rax, qword ptr [rbx + 0x80]', None, 'current-RPM entries at manager +0x80'),
        (0x617AC1, 'movss dword ptr [rax + rcx*4], xmm6', None, 'becomes the weapon current RPM (entry +4)'),
        (0x617ABC, 'mov edx, 0x4cbcc2a2', None, 'replication key of the current RPM'),
        (0x617ADC, 'call 0xfd97e0', None, 'replicated'),
    ],
    'instanceRecord': [
        (0x551234, 'mov rdi, qword ptr [rip + {rip}]', PROJECTILE_WEAPON, 'adding a projectile_weapon instance'),
        (0x55127B, 'add rax, qword ptr [rdi + 0x70]', None, 'its ROF record'),
        (0x55127F, 'movups xmmword ptr [rax], xmm0', None, 'is zeroed (zeroing slots and index)'),
        (0x551282, 'movups xmmword ptr [rax + 0x10], xmm0', None, 'and RPM slots and index'),
    ],
    'settingsResolution': [
        (0x515122, 'mov r11, qword ptr [rip + {rip}]', PROJECTILE_WEAPON, 'a weapon resolves its ProjectileWeaponComponentData'),
        (0x5151B2, 'imul rax, rax, 0x268', None, 'per-instance resolved copies (616 bytes)'),
        (0x5151B9, 'add rax, qword ptr [r11 + 0xd0]', None, 'at manager +0xD0 when the instance has one'),
        (0x5151CC, 'jmp 0x514c10', None, 'otherwise the entity-table record of its type'),
        (0x514C37, 'imul eax, edx, 0x21e', None, 'through the 542-row hash index (resource mod 542)'),
        (0x514C91, 'imul rax, rcx, 0x268', None, 'record * 616'),
        (0x514C98, 'add rax, 0x21e0', None, 'records follow the 542 x 16-byte index'),
    ],
    'programmableAmmo': [
        (0x615994, 'mov r12d, r8d', None, 'the projectile type the caller fires'),
        (0x615A3E, 'call 0x515100', None, 'resolves the weapon ProjectileWeaponComponentData'),
        (0x615A53, 'mov r13, rax', None, 'r13 = the resolved record'),
        (0x615AFD, 'mov edx, 8', None, 'WeaponFunctionType ProgrammableAmmo'),
        (0x615B19, 'call 0x1787500', None, 'current state of that weapon function'),
        (0x615B1E, 'cmp eax, 1', None, 'when it is on'),
        (0x615B23, 'mov eax, dword ptr [r13 + 0x240]', None, 'weapon_function_projectile_type (+576)'),
        (0x615B2C, 'cmovne r12d, eax', None, 'replaces the fired projectile when non-zero'),
        (0x615B30, 'mov rax, qword ptr [r13 + 0x248]', None, '+584'),
        (0x615B3A, 'cmovne rbx, rax', None, 'replaces the spawned entity when non-zero'),
    ],
    'weaponFunctionValue': [
        (0x755C23, 'imul r8, r9, 0xfc', None, 'weapon_data instance stride 0x3F0 (0xFC dwords)'),
        (0x755C32, 'mov r8d, dword ptr [rcx + r8*4 + 0x350]', None, 'the function bound to the queried input (+0x350)'),
        (0x755C3D, 'cmp r8d, 0xb', None, 'function types 1..12'),
        (0x755C51, 'mov r8d, dword ptr [rdi + rcx*4 + 0x755f58]', None, 'dispatch table'),
        (0x755C7D, 'mov rbx, qword ptr [rip + {rip}]', PROJECTILE_WEAPON, 'ROF: the projectile_weapon manager'),
        (0x755D37, 'mov eax, dword ptr [rcx + rax + 0x1c]', None, 'ROF: the ROF record index'),
        (0x755D48, 'mov eax, dword ptr [rax + rcx*4]', None, 'Firemode: the weapon_data current fire mode'),
        (0x755D50, 'mov rbx, qword ptr [rip + {rip}]', WEAPON_ROUNDS, 'Magazine: the weapon_rounds manager'),
        (0x755E03, 'lea rdx, [rcx + rcx*4]', None, 'Magazine: 20-byte weapon_rounds records'),
        (0x755E07, 'mov eax, dword ptr [rax + rdx*4 + 4]', None, 'Magazine: the selected magazine (+4)'),
        (0x755F04, 'shr eax, 2', None, 'ProgrammableAmmo: state bits 2-3'),
        (0x755F3A, 'and eax, 3', None, 'two-bit function state'),
    ],
}
JUMP_TABLE, JUMP_EXPECTED = 0x755F58, {2: 0x755C7D, 3: 0x755D40, 4: 0x755D50, 8: 0x755EF8}


def prove_layout(native):
    lib = native.typelib_module
    out = []
    for (struct_name, offset), (label, length, type_name) in LAYOUT.items():
        members = {m['offset64']: m for m in lib.layout(native.typelib, struct_name, structured=True)['members']}
        member = members[offset]
        if not member['name'].endswith('inferred_length=' + str(length)):
            raise ValueError(f'{struct_name} +{offset} ({label}) name length changed')
        if type_name and member['type_hash'] != native.probe.dl_hash(type_name):
            raise ValueError(f'{struct_name} +{offset} ({label}) is no longer {type_name}')
        out.append({'struct': struct_name, 'offset': offset, 'member': label, 'nameLength': length, 'type': type_name,
            'size': member['size64']})
    names = fire_modes.enum_names(native, 'WeaponFunctionType')
    for value, name in NATIVE_FUNCTION_NAMES.items():
        if names.get(value) != name:
            raise ValueError('WeaponFunctionType %d is no longer %s' % (value, name))
    return out


def game_proofs():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / MISSION[1])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in GAME_PROOFS.items()}
    table = [struct.unpack_from('<i', data, JUMP_TABLE + 4 * i)[0] for i in range(12)]
    for function, target in JUMP_EXPECTED.items():
        if table[function - 1] != target:
            raise ValueError('weapon-function dispatch for %d moved' % function)
    proofs['weaponFunctionDispatch'] = {'table': JUMP_TABLE, 'targets': {NATIVE_FUNCTION_NAMES.get(i + 1, str(i + 1)):
        '0x%X' % t for i, t in enumerate(table)}}
    return proofs, sha(data[base.TEXT[0]:base.TEXT[1]])


def observe(name, pw_types):
    """Every built projectile weapon's ROF record and current RPM, and every weapon_rounds selection."""
    mem = base.Mem(name)
    out = {'snapshot': name, 'rateOfFire': [], 'rounds': []}
    manager = mem.ptr(mem.game + PROJECTILE_WEAPON)
    count = mem.u32(manager + 0x38)
    records = mem.ptr(manager + 0x70)
    current = mem.ptr(manager + 0x80)
    entities = mem.ptr(manager + 0x68)
    for i in range(count or 0):
        descriptor = base.descriptor(mem, mem.ptr(entities + 8 * i))
        raw = mem.read(records + 0x20 * i, 0x20)
        zero = struct.unpack_from('<3fI', raw, 0)
        rof = struct.unpack_from('<3fI', raw, 0x10)
        now = struct.unpack_from('<f', mem.read(current + 12 * i + 4, 4))[0]
        kind = descriptor['type'] if descriptor else None
        settings = pw_types.get(int(kind, 16)) if kind else None
        row = {'entityType': kind, 'rpm': [round(v, 3) for v in rof[:3]], 'index': rof[3],
            'currentRpm': round(now, 3), 'zeroingSlots': [round(v, 3) for v in zero[:3]], 'zeroingIndex': zero[3]}
        if settings is not None:
            row['settingsRpm'] = settings
            row['matchesSettings'] = [round(v, 3) for v in rof[:3]] == settings
        out['rateOfFire'].append(row)
    rounds = mem.ptr(mem.game + WEAPON_ROUNDS)
    if rounds:
        count = mem.u32(rounds + 0x10)
        table = mem.ptr(rounds + 0x58)
        for i in range(count or 0):
            out['rounds'].append({'record': i, 'selectedMagazine': mem.u32(table + 20 * i + 4)})
    mem.close()
    return out


def records_by_resource(native, component):
    out = {}
    for record, resources in native.owners(component).items():
        for resource in resources:
            out.setdefault(resource, []).append(record)
    return out


def main():
    native = fire_modes.entity_research.Native()
    layout = prove_layout(native)
    proofs, text_sha = game_proofs()
    pins = [p for group in proofs.values() if isinstance(group, list) for p in group]
    relocation = {name: base.verify_pins_live(name, pins, []) for name in MISSION}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    deltas_file = (DATALIB / 'generated_entity_deltas.dl_bin').read_bytes()
    if sha(deltas_file) != DELTAS_SHA:
        raise ValueError('pinned entity delta table changed')
    deltas, _ = entity_deltas(deltas_file)
    items = customization_items((DATALIB / 'generated_weapon_customization_settings.dl_bin').read_bytes())
    by_add = {item['addPath']: item for item in items}
    by_id = {item['optionId']: item for item in items}
    names = field_ownership.component_names(native)
    unlock = {entry['weapon']: entry for entry in json.loads(UNLOCK_LISTS.read_text())['weapons'] if entry['weapon']}
    fire_rows = {(row['kind'], row['weapon']): row for row in json.loads(FIRE_MODES.read_text())['weapons']}
    sources = {row['weapon']: row for row in json.loads(SOURCES.read_text())['weapons']}

    def touching(path):
        """Delta entries of one customization item on the members this research owns."""
        found = []
        for entry in (deltas.get(path) or {}).get('entries', []):
            component, start, end = names.get(entry['component']), entry['offset'], entry['offset'] + entry['size']
            for (comp, lo, hi, member) in (('ProjectileWeaponComponentData', 4, 16, 'rounds_per_minute'),
                    ('ProjectileWeaponComponentData', 576, 592, 'weapon_function_projectile'),
                    ('WeaponDataComponentData', 184, 192, 'function_info'),
                    ('WeaponRoundsComponentData', 64, 72, 'ammo_type')):
                if component == comp and start < hi and end > lo:
                    found.append({'member': member, 'offset': start, 'size': entry['size'], 'bytes': entry['bytes'].hex()})
        return found

    rpm_patches = {}
    for path, delta in deltas.items():
        hit = [t for t in touching(path) if t['member'] == 'rounds_per_minute']
        if hit:
            item = by_add.get(path)
            rpm_patches[path] = {'item': item['debugName'] if item else None, 'slots': item['slots'] if item else None,
                'rpm': list(struct.unpack('<3f', bytes.fromhex(hit[0]['bytes'])[:12])) if hit[0]['size'] >= 12 else None,
                'offset': hit[0]['offset'], 'size': hit[0]['size']}
    binding_patches = sum(1 for path in deltas if any(t['member'] == 'function_info' for t in touching(path)))
    function_projectile_patches = sum(1 for path in deltas if any(t['member'] == 'weapon_function_projectile'
        for t in touching(path)))
    if binding_patches or function_projectile_patches:
        raise ValueError('a customization delta patches function_info or the function projectile; re-audit')

    pw_records = records_by_resource(native, 'ProjectileWeaponComponentData')
    wd_records = records_by_resource(native, 'WeaponDataComponentData')
    wr_records = records_by_resource(native, 'WeaponRoundsComponentData')
    mag_records = records_by_resource(native, 'WeaponMagazineComponentData')
    pw_owners = native.owners('ProjectileWeaponComponentData')
    wd_owners = native.owners('WeaponDataComponentData')
    pw_types = {}
    for resource, records in pw_records.items():
        if len(records) == 1:
            pw_types[resource] = [round(v, 3) for v in struct.unpack_from('<3f',
                native.record('ProjectileWeaponComponentData', records[0]), 4)]

    weapons = []
    for kind, name, resources, families, _ in fire_modes.weapons(native):
        fire = fire_rows.get((kind, name)) or {}
        roots = []
        for resource in resources:
            r = int(resource, 16)
            root = {'resource': resource}
            if len(pw_records.get(r, [])) == 1:
                body = native.record('ProjectileWeaponComponentData', pw_records[r][0])
                root['projectileWeapon'] = {'record': pw_records[r][0], 'owners': len(pw_owners[pw_records[r][0]]),
                    'projType': struct.unpack_from('<I', body, 0)[0],
                    'rpm': list(struct.unpack_from('<3f', body, 4)),
                    'projectileEntity': '%016X' % struct.unpack_from('<Q', body, 40)[0],
                    'functionProjectile': struct.unpack_from('<I', body, 576)[0],
                    'functionEntity': '%016X' % struct.unpack_from('<Q', body, 584)[0]}
            if len(wd_records.get(r, [])) == 1:
                body = native.record('WeaponDataComponentData', wd_records[r][0])
                left, right = struct.unpack_from('<2i', body, 184)
                root['weaponData'] = {'record': wd_records[r][0], 'owners': len(wd_owners[wd_records[r][0]]),
                    'left': left, 'right': right}
            if len(wr_records.get(r, [])) == 1:
                body = native.record('WeaponRoundsComponentData', wr_records[r][0])
                root['rounds'] = {'record': wr_records[r][0], 'primaryProjectile': struct.unpack_from('<I', body, 64)[0],
                    'alternateProjectile': struct.unpack_from('<I', body, 68)[0],
                    'capacities': [round(v, 3) for v in struct.unpack_from('<2f', body, 72)]}
            if len(mag_records.get(r, [])) == 1:
                body = native.record('WeaponMagazineComponentData', mag_records[r][0])
                root['magazinePattern'] = body[4:136] != bytes(132)
            custom = native.component(resource, 'WeaponCustomizationComponentData')
            defaults = []
            if custom:
                cbody = native.record('WeaponCustomizationComponentData', custom['record_index'])
                for at in range(0, 80, 8):
                    slot, option = struct.unpack_from('<II', cbody, at)
                    if option in by_id:
                        item = by_id[option]
                        defaults.append({'slot': slot, 'item': item['debugName'], 'addPath': '0x%016X' % item['addPath'],
                            'patches': touching(item['addPath'])})
            root['defaultCustomization'] = [d for d in defaults if d['patches']]
            roots.append(root)
        pw_roots = [r['projectileWeapon'] for r in roots if 'projectileWeapon' in r]
        wd_roots = [r['weaponData'] for r in roots if 'weaponData' in r]
        row = {'kind': kind, 'weapon': name, 'families': sorted(families), 'roots': len(roots),
            'fireModeState': fire.get('state'), 'fireModeReason': fire.get('reason')}
        # Roots must agree on the members this research owns (rate slots, entity and function projectile, bindings);
        # other members (the base projectile of an emplacement variant, for example) do not matter here.
        owned = ('rpm', 'projectileEntity', 'functionProjectile', 'functionEntity')
        shapes = {json.dumps({k: p[k] for k in owned}, sort_keys=True) for p in pw_roots}
        bind_shapes = {(w['left'], w['right']) for w in wd_roots}
        if not pw_roots or not wd_roots:
            row.update(fireRate={'state': 'absent', 'reason': 'The weapon owns no ProjectileWeaponComponentData rate slots.'},
                inputs=None, functionAmmo={'state': 'absent', 'reason': 'No projectile weapon component.'})
            if 'rounds' not in {k for r in roots for k in r}:
                row['feeds'] = None
            weapons.append(row)
            continue
        if len(shapes) != 1 or len(bind_shapes) != 1:
            row.update(fireRate={'state': 'blocked', 'reason': 'The weapon roots disagree on their rate or binding.'},
                inputs=None, functionAmmo={'state': 'blocked', 'reason': 'The weapon roots disagree.'})
            weapons.append(row)
            continue
        pw, (left, right) = pw_roots[0], next(iter(bind_shapes))
        unique = all(p['owners'] == 1 for p in pw_roots) and all(w['owners'] == 1 for w in wd_roots)
        inputs = {'left': FUNCTION_NAMES.get(left, left), 'right': FUNCTION_NAMES.get(right, right),
            'leftValue': left, 'rightValue': right}
        row['inputs'] = inputs
        free = [side for side in ('left', 'right') if inputs[side + 'Value'] == 0]
        rpm = pw['rpm']
        rof_bound = ROF in (left, right)
        # Customization that overwrites the rate slots: defaults (every build) and unlock-list options.
        default_rpm = [d for r in roots for d in r['defaultCustomization'] if any(p['member'] == 'rounds_per_minute'
            for p in d['patches'])]
        listed = unlock.get(name)
        equippable_rpm = sorted({rpm_patches[int(o['addPath'], 16)]['item'] for o in (listed or {}).get('options', [])
            if int(o['addPath'], 16) in rpm_patches and not any(d['addPath'] == '0x%016X' % int(o['addPath'], 16)
                for d in default_rpm)})
        writable_trigger = fire.get('state') in ('selectable', 'single_mode')
        # A wind-up projectile weapon (the M-1000 Maxigun): its trigger is ordinary apart from the wind-up, so its rate
        # slots are authored like any other weapon's, flagged windUp (allow_unverified_effect, WIND_UP_UNVERIFIED).
        # Its fire modes and function projectile stay blocked.
        wind_up = fire.get('state') == 'blocked' and (fire.get('windUp') or {}).get('stateWithoutWindUp') in (
            'selectable', 'single_mode')
        visited = [rpm[i] for i in SELECTOR_ORDER if rpm[i] != 0] if rof_bound else [rpm[1]]
        fire_rate = {'slots': dict(zip(SLOT_NAMES, rpm)), 'selectorBound': rof_bound,
            'selectorInput': next((side for side in ('left', 'right') if inputs[side + 'Value'] == ROF), None),
            'modes': visited, 'defaultRpm': rpm[1], 'dormantSlots': [] if rof_bound else
                [SLOT_NAMES[i] for i in (0, 2) if rpm[i] != 0],
            'overriddenByDefault': [d['item'] for d in default_rpm], 'overriddenWhenEquipped': equippable_rpm,
            'uniqueOwner': unique}
        if wind_up:
            fire_rate['windUp'] = {'reason': WIND_UP_UNVERIFIED}
        if default_rpm:
            fire_rate.update(state='blocked', reason='A default customization (' + ', '.join(d['item'] for d in default_rpm)
                + ') overwrites the rate slots at every build.')
        elif not writable_trigger and not wind_up:
            fire_rate.update(state='blocked', reason=fire.get('reason') or 'The trigger is not an ordinary projectile trigger.')
        elif not unique:
            fire_rate.update(state='blocked', reason='A rate or binding record is shared.')
        elif rpm[1] == 0:
            fire_rate.update(state='blocked', reason='The default (Y) rate slot is empty.')
        elif rof_bound:
            fire_rate.update(state='selectable', reason=None, maxModes=3)
        elif free:
            fire_rate.update(state='addable', reason=None, maxModes=3, bindableInputs=free)
        else:
            fire_rate.update(state='single_rate', reason='Both weapon-function inputs are bound, so no rate selector '
                'can be added; only the default rate (weapon.fire_rate) is authored.', maxModes=1)
        row['fireRate'] = fire_rate

        source = sources.get(name) or {}
        rounds_fed = 'rounds_feed' in families
        pattern = any(r.get('magazinePattern') for r in roots)
        entity = pw['projectileEntity'] != '0' * 16
        function = {'projectile': pw['functionProjectile'], 'entity': pw['functionEntity'] != '0' * 16,
            'selectorBound': PROGRAMMABLE in (left, right),
            'selectorInput': next((side for side in ('left', 'right') if inputs[side + 'Value'] == PROGRAMMABLE), None)}
        if function['selectorBound']:
            if function['entity'] or entity:
                function.update(state='native_blocked', reason='The programmable function spawns an entity '
                    '(+584 or +40), not a projectile reference.')
            elif pw['functionProjectile']:
                function.update(state='native', reason=None)
            else:
                function.update(state='native_blocked', reason='The programmable function is bound but has no projectile.')
        elif not writable_trigger:
            function.update(state='blocked', reason=fire.get('reason') or 'The trigger is not an ordinary projectile trigger.')
        elif rounds_fed:
            function.update(state='blocked', reason='Rounds-fed weapons select their projectile through their WeaponRounds '
                'magazines (the Magazine function); a second selector is not authored on them.')
        elif entity or pw['functionProjectile'] or function['entity']:
            function.update(state='blocked', reason='The weapon spawns an entity or already carries a function projectile.')
        elif pattern:
            function.update(state='blocked', reason='A magazine pattern selects the fired projectiles.')
        elif source.get('status') not in ('ACTIVE_DIRECT', 'INDIRECT'):
            function.update(state='blocked', reason='The active projectile source is ' + str(source.get('status'))
                + '; the fired projectile is not uniquely established.')
        elif not unique:
            function.update(state='blocked', reason='A ProjectileWeapon or WeaponData record is shared.')
        elif not free:
            function.update(state='blocked', reason='Both weapon-function inputs are bound.')
        else:
            function.update(state='addable', reason=None, bindableInputs=free)
        row['functionAmmo'] = function

        rounds = [r['rounds'] for r in roots if 'rounds' in r]
        if rounds:
            feed_defaults = {p['offset']: d['item'] for r in roots for d in r['defaultCustomization'] for p in d['patches']
                if p['member'] == 'ammo_type'}
            r0 = rounds[0]
            row['feeds'] = {'mechanism': 'rounds_magazine', 'selectorBound': 4 in (left, right),
                'selectorInput': next((side for side in ('left', 'right') if inputs[side + 'Value'] == 4), None),
                'primary': {'projectile': r0['primaryProjectile'], 'capacity': r0['capacities'][0],
                    'ownedBy': feed_defaults.get(64)},
                'alternate': {'projectile': r0['alternateProjectile'], 'capacity': r0['capacities'][1],
                    'ownedBy': feed_defaults.get(68)}}
        weapons.append(row)

    # Settings identity (group, row, record type) of every function and feed projectile, from the production resolver
    # on the retained snapshot: the reviewed source the runtime re-proves before writing or restoring a reference.
    import research_attack_outputs as attack_outputs
    types = sorted({w['functionAmmo']['projectile'] for w in weapons if (w.get('functionAmmo') or {}).get('projectile')}
        | {w['feeds'][feed]['projectile'] for w in weapons if w.get('feeds') for feed in ('primary', 'alternate')
            if w['feeds'][feed]['projectile']})
    resolved = attack_outputs.resolve_settings(types, [], [])['projectiles']
    for w in weapons:
        function = w.get('functionAmmo') or {}
        if function.get('projectile'):
            row = resolved.get(str(function['projectile']))
            function['settings'] = row and row['settings']
            function['compatibilityClass'] = row and attack_outputs.projectile_class(row)
        for feed in ('primary', 'alternate'):
            item = (w.get('feeds') or {}).get(feed)
            if item and item['projectile']:
                row = resolved.get(str(item['projectile']))
                item['settings'] = row and row['settings']
    observations = [observe(name, pw_types) for name in MISSION]
    seeded = [r for o in observations for r in o['rateOfFire'] if r.get('settingsRpm') is not None]
    if not seeded or not all(r['matchesSettings'] and r['index'] == 1 for r in seeded if any(r['rpm'])):
        raise ValueError('a built weapon ROF record differs from its settings or does not start on the Y slot')
    summary = {'weapons': len(weapons),
        'fireRate': dict(sorted(collections.Counter('%s:%s' % (w['kind'], w['fireRate']['state']) for w in weapons).items())),
        'functionAmmo': dict(sorted(collections.Counter('%s:%s' % (w['kind'], w['functionAmmo']['state'])
            for w in weapons).items())),
        'roundsFeeds': sum(1 for w in weapons if w.get('feeds')),
        'rateOfFirePatchingItems': sorted(v['item'] or '?' for v in rpm_patches.values()),
        'builtWeaponsObserved': len(seeded)}
    report = {'schemaVersion': 1, 'writes': 0, 'build': build_profile.BUILD_ID,
        'gameDllTextSha256': text_sha, 'typeLibrary': layout, 'proofs': proofs,
        'model': {
            'rateOfFire': 'ProjectileWeaponComponent +4 rounds_per_minute: three f32 slots X/Y/Z. Y (+8) is the default and '
                'the only rate of a weapon without a ROF selector. With WeaponFunctionType ROF bound to an input, each '
                'press moves to the next slot (Y -> Z -> X), skipping 0.0 slots. Fixed storage: three rates at most.',
            'inputs': 'WeaponDataComponent function_info {left +184, right +188}: the WeaponFunctionType on each '
                'weapon-function input; 0 = none. Read from the built weapon.',
            'programmableAmmo': 'With ProgrammableAmmo bound and switched on, every shot fires ProjectileWeapon +576 '
                'instead of the normal projectile (when +576 is non-zero).',
            'roundsFeeds': 'WeaponRounds +64 / +68: the primary and alternate magazine projectiles, +72 their capacities; '
                'the Magazine function switches between them.',
            'ownership': 'Every member is weapon data on the weapon entity record, copied into or read through the built '
                'weapon (projectile_weapon ROF record, weapon_data bindings); a weapon built after a write uses it.'},
        'rateOfFirePatches': sorted(rpm_patches.values(), key=lambda v: str(v['item'])),
        'observations': observations, 'summary': summary, 'weapons': weapons}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', newline='\n')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
