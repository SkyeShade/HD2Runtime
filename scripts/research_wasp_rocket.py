"""How the StA-X3 W.A.S.P. Launcher (and every other ProjectileEntity weapon) fires its rocket. Read-only research.

Question (stats editor, 0.30.4): the W.A.S.P. shows no Projectile rows; research/active-projectile-sources classifies it
BLOCKED ("Another native selector owns the fired projectile: ProjectileEntity"). What does it fire, which values of
that rocket are editable safely, and can it be swapped?

Proven on build F5FEE03DCFDB from the pinned entity tables, the type library, the unpacked game.dll in the retained
snapshots (exact instruction pins) and the snapshots' live component tables:

1. The shot spawns an entity. The projectile fire path (0x6128B0) tests ProjectileWeapon +40 (ProjectileEntity, u64):
   when set, each shot runs 0x615940 once with the weapon's active projectile type (0x7456D0: the W.A.S.P. has no
   magazine pattern, so its ProjectileWeapon +0 = 43). 0x615940 takes the entity from +40 and, when the weapon's
   ProgrammableAmmo state is 1 (0x1787500), the type from +576 and the entity from +584 when they are non-zero. It
   writes the type into the spawn info (+0x424) the spawn context points at (+0x48) and spawns the entity by resource
   (0xFDC140).
2. The rocket is a SeekingMissile entity. Every ProjectileEntity / +584 entity of a player, support or vehicle weapon is
   a unit with a SeekingMissileComponent (except the P-34 Breacher's thrown charge). Its record is the entity's own
   (one owner each); exactly one ProjectileWeapon record names each missile, and no entity delta or game.dll constant
   does.
3. The missile carries a projectile row, it does not fly by one. The SeekingMissile spawn (0x641050) takes its type
   from SeekingMissile +176 (projectile_type_to_process, 0 on every weapon missile) or else the spawn info +0x424 (the
   shot's type), and, when +173 (processed by the projectile system) is set, registers one projectile of that type
   whose flight record +0x50 is the missile's unit (0x646030 -> 0x13A9830). A unit-driven projectile's position is the
   unit's every step and its velocity is recomputed from the displacement (research/projectile-homing): the row's
   velocity, drag and gravity do not move the missile. Its hit damage (+60) and impact explosion (+144) are the row's:
   the existing "Explosion - Primary impact" rows of the W.A.S.P. are row 43's impact explosion.
4. The flight is the SeekingMissile record, read live. The missile update (0x642760) resolves the type record through
   the table lookup (0x504690) on every update, with no per-instance copy: max_lifetime +64 ends the missile when its
   age reaches it (<= 0: no limit), the target speed is clamp(minimum_speed +72 + age x acceleration +80, up to
   preferred_speed +76), and the turn step blends +88 (at or beyond max_angle_to_target +84, degrees) and +92 (on
   target). starting_speed +68 is copied into the missile when it spawns (0x641143 -> 0x504720). +12 switches guidance
   on once the missile's clock passes it (only when > 0). Member names come from a lead (filediver) and are checked
   against the hidden-name lengths of the pinned type library; the turn members are named by what the code does.
5. Multiplayer. The movement loop has no authority test: every machine moves its own copy from its own record.

Nothing here writes memory. Requires the research-only packages capstone and numpy.
Output: research/wasp-rocket-F5FEE03DCFDB.json. `--check` compares with the committed output.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_entity_authoring as entity_research  # noqa: E402
import snapshot_regions  # noqa: E402
from scan import xref  # noqa: E402

OUTPUT = ROOT / 'research/wasp-rocket-F5FEE03DCFDB.json'
SOURCES = ROOT / 'research/active-projectile-sources-F5FEE03DCFDB.json'
FILEDIVER_LEAD = 'datalibrary/seeking_missile_component.go'
PW, SM = 'ProjectileWeaponComponentData', 'SeekingMissileComponentData'
ENTITY_MEMBER, FUNCTION_ENTITY_MEMBER, FUNCTION_TYPE_MEMBER = 40, 584, 576
LINKS = {ENTITY_MEMBER: 'ProjectileEntity', FUNCTION_ENTITY_MEMBER: 'function entity (ProgrammableAmmo state 1)'}

# SeekingMissileComponent members (offset, storage, lead name, hidden-name length the lead name must have).
MEMBERS = [
    (0, 'u32', 'targeting_mode', 14), (4, 'f32', None, 19), (8, 'u8', 'autoplay_starting_effects', 25),
    (12, 'f32', 'time_to_enable_guidance', 23), (16, 'f32', 'time_to_disable_guidance', 24),
    (28, 'f32', 'angle_lost_guidance', 19), (32, 'f32', 'movement_prediction_accuracy', 28),
    (56, 'f32', 'time_to_enable_movement', 23), (60, 'f32', 'time_to_enable_explosive', 24),
    (64, 'f32', 'max_lifetime', 12), (68, 'f32', 'starting_speed', 14), (72, 'f32', 'minimum_speed', 13),
    (76, 'f32', 'preferred_speed', 15), (80, 'f32', 'acceleration', 12), (84, 'f32', 'max_angle_to_target', 19),
    (88, 'f32', 'min_turn_speed', 14), (92, 'f32', 'max_turn_speed', 14), (96, 'f32', 'p_factor', 8),
    (100, 'f32', 'i_factor', 8), (104, 'f32', 'd_factor', 8), (108, 'f32', 'target_update_interval', 22),
    (168, 'f32', 'target_dot_minimum', 18), (172, 'u8', 'javelin_firing_mode', 19),
    (173, 'u8', 'movement_should_be_processed_by_projectile_system', 49),
    (176, 'u32', 'projectile_type_to_process', 26)]
# The exposed members: semantic field suffix, offset, unit, range, the native-value rule, and the code that reads it.
FIELDS = [
    ('max_lifetime', 64, 's', 0.1, 600.0, 'positive',
     'The missile ends when its age reaches this (0x643656: age +0x24 compared each update); 0 or less means no '
     'limit, which is not offered.'),
    ('starting_speed', 68, 'm/s', 0.0, 1000.0, None,
     'Copied into the missile as its current speed when it spawns (0x64114E -> instance +0x28/+0x30).'),
    ('minimum_speed', 72, 'm/s', 0.0, 1000.0, None,
     'Target speed = minimum_speed + age x acceleration, up to preferred_speed (0x6442B1..0x6442DE, every update).'),
    ('preferred_speed', 76, 'm/s', 0.0, 1000.0, None,
     'The target speed the missile accelerates to (0x6442D8 minss, every update).'),
    ('acceleration', 80, 'm/s2', 0.0, 10000.0, None,
     'How fast the target speed grows from minimum_speed to preferred_speed (0x6442C8, every update).'),
    ('max_angle_to_target', 84, 'degrees', 1.0, 180.0, None,
     'The angle to the target at which the turn step is turn_rate_at_max_angle; below it the step blends towards '
     'turn_rate_aligned (0x64428D: angle / (this x pi/180), clamped to 1).'),
    ('turn_rate_at_max_angle', 88, 'per second', 0.0, 1000.0, None,
     'Turn step at or beyond max_angle_to_target (0x6442FF); the step scales the rotation towards the target '
     '(0x644BB7). Lead name min_turn_speed.'),
    ('turn_rate_aligned', 92, 'per second', 0.0, 1000.0, None,
     'Turn step when the missile points at its target (0x6442FA). Lead name max_turn_speed.'),
    ('guidance_delay', 12, 's', 0.01, 60.0, 'positive',
     'Guidance switches on once the missile\'s clock passes this (0x642950 -> 0x645D90); 0 or less never switches it '
     'on by time, so only a positive native value is tunable. Lead name time_to_enable_guidance.'),
]

PINS = {
    'fireSpawnsEntity': [
        (0x61406C, 'call 0x7456d0', 'the shot\'s projectile type: the weapon\'s active projectile (no magazine pattern '
            '-> ProjectileWeapon +0)'),
        (0x614071, 'mov dword ptr [rbp - 0x68], eax', 'kept for the shot'),
        (0x6143CD, 'cmp qword ptr [rax + 0x28], 0', 'ProjectileWeapon +40 (ProjectileEntity) set ...'),
        (0x6143D2, 'je 0x614445', '... else the pellet loop of plain projectiles'),
        (0x6143F4, 'mov r8d, dword ptr [rbp - 0x68]', 'the type, passed to the shot'),
        (0x61443B, 'call 0x615940', 'one shot: the entity path'),
    ],
    'shot': [
        (0x615994, 'mov r12d, r8d', 'r12d = the shot\'s projectile type'),
        (0x615A3E, 'call 0x515100', 'the weapon\'s ProjectileWeapon (its built copy, else the table record)'),
        (0x615B15, 'mov rbx, qword ptr [r13 + 0x28]', 'rbx = ProjectileEntity (+40)'),
        (0x615B19, 'call 0x1787500', 'the ProgrammableAmmo function state'),
        (0x615B1E, 'cmp eax, 1', 'state 1 ...'),
        (0x615B23, 'mov eax, dword ptr [r13 + 0x240]', '... +576 (weapon_function_projectile_type)'),
        (0x615B2C, 'cmovne r12d, eax', 'replaces the type when non-zero'),
        (0x615B30, 'mov rax, qword ptr [r13 + 0x248]', '... +584 (the function entity)'),
        (0x615B3A, 'cmovne rbx, rax', 'replaces the entity when non-zero'),
        (0x615BBF, 'test rbx, rbx', 'an entity ...'),
        (0x615BC2, 'je 0x616502', '... else a projectile of the type is fired'),
        (0x61604F, 'mov dword ptr [rbp + 0x504], r12d', 'spawn info (rbp + 0xE0) + 0x424 := the type'),
        (0x6162A1, 'lea rax, [rbp + 0xe0]', 'the spawn info ...'),
        (0x6162F9, 'mov qword ptr [rbp + 0xc8], rax', '... is the spawn context (rbp + 0x80) + 0x48'),
        (0x616441, 'movups xmm0, xmmword ptr [rbp + 0xc0]', 'the context is copied to rbp + 0x20 (+0x48 kept)'),
        (0x6164C8, 'lea r9, [rbp + 0x20]', 'spawn context'),
        (0x6164CC, 'mov r8, rbx', 'the entity resource'),
        (0x6164D4, 'call 0xfdc140', 'spawns the entity'),
    ],
    'missileSpawn': [
        (0x641143, 'call 0x504720', 'the spawned unit\'s SeekingMissile record (table lookup, slot 196)'),
        (0x64114E, 'movss xmm0, dword ptr [rax + 0x44]', 'starting_speed (+68) ...'),
        (0x64116F, 'movss dword ptr [r13 + 0x28], xmm0', '... is the missile\'s current speed'),
        (0x6414D2, 'mov eax, dword ptr [rdi + 0xb0]', 'projectile_type_to_process (+176) ...'),
        (0x6414DA, 'jne 0x6414e6', '... when 0:'),
        (0x6414DC, 'mov rax, qword ptr [rcx + 0x48]', 'the spawn context\'s spawn info'),
        (0x6414E0, 'mov eax, dword ptr [rax + 0x424]', 'the shot\'s type'),
        (0x6414EB, 'mov dword ptr [r13 + 0x34], eax', 'the missile\'s projectile type'),
        (0x641D7A, 'cmp byte ptr [rax + 0xad], 0', 'processed by the projectile system (+173)'),
        (0x641DC9, 'mov eax, dword ptr [r13 + 0x34]', 'its type ...'),
        (0x641DFD, 'call 0x646030', '... registered as a projectile'),
        (0x646052, 'mov ebx, r8d', 'the missile\'s unit'),
        (0x64617C, 'lea r8, [rip + 0x31814ed]', 'ProjectileSettings by type'),
        (0x646241, 'mov dword ptr [rbp - 0x59], ebx', 'request + 0x28 := the unit'),
        (0x64625C, 'call 0x13a9830', 'projectile spawn'),
        (0x13A9DBE, 'mov edx, dword ptr [r13 + 0x28]', 'the request\'s unit ...'),
        (0x13A9DCE, 'mov dword ptr [r15 + rsi + 0x3090], ecx', '... is flight +0x50: a unit-driven projectile'),
    ],
    'missileUpdate': [
        (0x64283A, 'call 0x504690', 'every update: the SeekingMissile type record (no per-instance copy)'),
        (0x642950, 'movss xmm1, dword ptr [r13 + 0xc]', 'guidance off: +12 ...'),
        (0x642956, 'comiss xmm1, xmm13', '... only when > 0 ...'),
        (0x642962, 'comiss xmm0, xmm1', '... against the missile\'s clock'),
        (0x64299E, 'mov byte ptr [rdi + rbx*4], 1', 'guidance switched'),
        (0x6429AF, 'call 0x645d90', 'on (r8b = 1)'),
        (0x643471, 'call 0x504690', 'movement: the type record again'),
        (0x643646, 'addss xmm0, dword ptr [rdi + 0x24]', 'age += step'),
        (0x643656, 'movss xmm1, dword ptr [rsi + 0x40]', 'max_lifetime (+64) ...'),
        (0x64365B, 'comiss xmm1, xmm13', '... only when > 0 ...'),
        (0x643664, 'jb 0x6436ce', '... age reached: the missile ends'),
        (0x64428D, 'movss xmm1, dword ptr [rsi + 0x54]', 'max_angle_to_target (+84) ...'),
        (0x644292, 'mulss xmm1, dword ptr [rip + 0x1d823c6]', '... x pi/180 (degrees)'),
        (0x64429A, 'divss xmm0, xmm1', 'angle to the target / max angle (clamped to 1)'),
        (0x6442B1, 'movss xmm12, dword ptr [rsi + 0x48]', 'minimum_speed (+72)'),
        (0x6442B7, 'movss xmm15, dword ptr [rdi + 0x24]', 'age'),
        (0x6442C8, 'mulss xmm0, dword ptr [rsi + 0x50]', 'x acceleration (+80)'),
        (0x6442CD, 'addss xmm0, xmm12', '+ minimum_speed'),
        (0x6442D8, 'movss xmm12, dword ptr [rsi + 0x4c]', 'preferred_speed (+76) ...'),
        (0x6442DE, 'minss xmm12, xmm0', '... caps the target speed'),
        (0x6442FA, 'mulss xmm0, dword ptr [rsi + 0x5c]', '(1 - ratio) x +92'),
        (0x6442FF, 'mulss xmm14, dword ptr [rsi + 0x58]', 'ratio x +88'),
        (0x644305, 'addss xmm14, xmm0', 'the turn step'),
        (0x644BB7, 'mulss xmm15, xmm14', 'scales the rotation towards the target'),
    ],
}
CONSTANTS = {0x23C6660: 0.01745329238474369}


def hexid(value: int) -> str:
    return '0x%016X' % value


def name_lengths(native) -> dict:
    out = {}
    for m in native.typelib_module.layout(native.typelib, 'SeekingMissileComponent', structured=True)['members']:
        found = re.search(r'inferred_length=(\d+)', str(m.get('name')))
        out[m['offset64']] = {'length': int(found.group(1)) if found else None, 'size': m['size64'],
            'storage': m.get('storage')}
    return out


def value(raw: bytes, offset: int, storage: str):
    if storage == 'f32':
        return round(struct.unpack_from('<f', raw, offset)[0], 6)
    if storage == 'u8':
        return raw[offset]
    return struct.unpack_from('<I', raw, offset)[0]


def weapon_names() -> dict:
    names = {}
    for item in json.loads(SOURCES.read_text(encoding='utf-8'))['weapons']:
        names.setdefault(item['resource'], []).append({'name': item['weapon'], 'kind': item['kind']})
    return names


def references(native, resource: int) -> dict:
    """Every occurrence of the entity hash: component records (by member), deltas, game.dll."""
    data = native.entities
    needle = struct.pack('<Q', resource)
    records = []
    for name in (PW,):
        _, capacity, offset, size, count = native.table(name)
        body = native.table(name)[0]
        for record in range(count):
            raw = body[offset + record * size:offset + (record + 1) * size]
            for member in (ENTITY_MEMBER, FUNCTION_ENTITY_MEMBER):
                if struct.unpack_from('<Q', raw, member)[0] == resource:
                    records.append({'component': name, 'record': record, 'member': member})
    deltas = (build_profile.FILEDIVER / 'datalibrary/generated_entity_deltas.dl_bin').read_bytes()
    return {'projectileWeaponRecords': records, 'entityFileOccurrences': data.count(needle),
        'entityDeltaOccurrences': deltas.count(needle)}


def snapshot_records(resources: list[str]) -> dict:
    """The SeekingMissile records of the missiles through the production capture, in every retained snapshot."""
    wanted = '{' + ','.join('[%s]=true' % snapshot_regions._lua(r) for r in resources) + '}'
    body = r'''
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local b=require('hd2runtime/core/bytes')
local json=require('hd2runtime/primary_mapper/json')
local reader=Reader.new(source)
local roots=discover.locate(source,reader,profile,{entity=true})
local catalog=entities.capture(reader,roots.entity,profile,{'SeekingMissileComponentData'})
local want=''' + wanted + r'''
local out={refused=catalog.tables.SeekingMissileComponentData,records={}}
for _,c in ipairs(catalog.candidates)do
 if want[c.resourceHash]then
  local ok,r=pcall(catalog.record,c,'SeekingMissileComponentData')
  out.records[c.resourceHash]=ok and{hex=b.hex(r.bytes),record=r.identity.recordIndex,row=r.identity.indexRow,
   owners=r.identity.ownerCount}or{error=tostring(r)}
 end
end
return json.encode(out)
'''
    result = {}
    folder = build_profile.snapshot_directory()
    for path in sorted(folder.glob(build_profile.BUILD_ID + '-*.hd2snap')):
        result[path.name] = json.loads(snapshot_regions.run_lua(body, snapshot=path))
    return result


def build() -> dict:
    native = entity_research.Native()
    img = xref.CodeImage.from_snapshot()
    proofs = {group: [img.pin(rva, role, asm) for rva, asm, role in rows] for group, rows in PINS.items()}
    for rva, expected in CONSTANTS.items():
        if abs(img.f32(rva) - expected) > 1e-9:
            raise ValueError('constant at %x changed' % rva)
    lengths = name_lengths(native)
    members = []
    for offset, storage, lead, length in MEMBERS:
        have = lengths[offset]
        if have['length'] != length or (lead and len(lead) != length):
            raise ValueError('SeekingMissile +%d hidden name length %r, lead %r' % (offset, have['length'], lead))
        exposed = next((f[0] for f in FIELDS if f[1] == offset), None)
        members.append({'offset': offset, 'storage': storage, 'hiddenNameLength': length, 'leadName': lead,
            'field': exposed})
    names = weapon_names()
    pw_body, _, pw_offset, pw_size, pw_count = native.table(PW)
    owners = native.owners(PW)
    sm_owners = native.owners(SM)
    weapons, missiles = [], {}
    for record in range(pw_count):
        raw = pw_body[pw_offset + record * pw_size:pw_offset + (record + 1) * pw_size]
        links = {member: struct.unpack_from('<Q', raw, member)[0] for member in LINKS}
        if not any(links.values()):
            continue
        record_owners = owners.get(record, [])
        if len(record_owners) != 1:
            raise ValueError('ProjectileWeapon record %d with a spawned entity is shared' % record)
        owner = record_owners[0]
        component = native.component(hexid(owner), PW)
        entry = {'resource': hexid(owner), 'path': native.path(owner),
            'names': names.get(hexid(owner), []), 'projectileWeapon': {'recordIndex': record,
                'indexRow': component['index_row'], 'ownerCount': 1},
            'projectileType': struct.unpack_from('<I', raw, 0)[0],
            'functionProjectileType': struct.unpack_from('<I', raw, FUNCTION_TYPE_MEMBER)[0], 'spawns': []}
        for member, label in LINKS.items():
            resource = links[member]
            if not resource:
                continue
            key = hexid(resource)
            report = native.report(key)
            components = sorted(c['name'] for c in report['components'] if c['name'] and c['resolved'])
            sm = native.component(key, SM)
            carried = entry['functionProjectileType'] if member == FUNCTION_ENTITY_MEMBER and \
                entry['functionProjectileType'] else entry['projectileType']
            missile = {'resource': key, 'entityRow': native.entity_row(resource), 'components': components,
                'references': references(native, resource)}
            if sm:
                sm_raw = native.record(SM, sm['record_index'])
                values = {m[2] or ('+%d' % m[0]): value(sm_raw, m[0], m[1]) for m in MEMBERS}
                own = sm_owners.get(sm['record_index'], [])
                processed = sm_raw[173] == 1
                own_type = struct.unpack_from('<I', sm_raw, 176)[0]
                missile['seekingMissile'] = {'recordIndex': sm['record_index'], 'indexRow': sm['index_row'],
                    'ownerCount': len(own), 'owners': [hexid(x) for x in own], 'values': values,
                    'recordSha256': sm['record_sha256']}
                missile['projectileSystem'] = processed
                missile['projectileType'] = (own_type or carried) if processed else None
                missile['projectileTypeSource'] = (('SeekingMissile +176' if own_type else
                    ('spawn info +0x424 = ProjectileWeapon +576' if carried == entry['functionProjectileType']
                     and member == FUNCTION_ENTITY_MEMBER else 'spawn info +0x424 = the shot\'s type (ProjectileWeapon +0)'))
                    if processed else 'none: not processed by the projectile system (its own explosive)')
                refs = missile['references']
                missile['exposable'] = (len(own) == 1 and own[0] == resource and processed
                    and len(refs['projectileWeaponRecords']) == 1 and refs['entityDeltaOccurrences'] == 0)
            else:
                missile['seekingMissile'] = None
                missile['projectileSystem'] = False
                missile['exposable'] = False
            entry['spawns'].append(dict({'member': member, 'memberName': label}, **missile))
            missiles[key] = missile
        weapons.append(entry)
    weapons.sort(key=lambda w: (w['names'][0]['name'] if w['names'] else w['path'] or w['resource']))
    snapshots = snapshot_records(sorted(k for k, m in missiles.items() if m.get('seekingMissile')))
    identical = True
    for name, snap in snapshots.items():
        for key, missile in missiles.items():
            if not missile.get('seekingMissile'):
                continue
            live = snap['records'].get(key) or {}
            sm = missile['seekingMissile']
            pinned = native.record(SM, sm['recordIndex']).hex()
            same = live.get('hex', '').lower() == pinned and live.get('record') == sm['recordIndex'] \
                and live.get('owners') == 1
            live['identicalToPinned'] = same
            live.pop('hex', None)
            identical = identical and same
    exposed = [{'field': f[0], 'offset': f[1], 'unit': f[2], 'min': f[3], 'max': f[4], 'nativeRule': f[5],
        'consumer': f[6]} for f in FIELDS]
    wasp = next(w for w in weapons if any(n['name'] == 'StA-X3 W.A.S.P. Launcher' for n in w['names']))
    return {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'writes': 0, 'protectionChanges': 0,
        'gameDll': {'sha256': img.sha256}, 'lead': 'filediver ' + FILEDIVER_LEAD + ' (member names and comments); '
            'every name is checked against the pinned type library\'s hidden-name length and every exposed member '
            'against the code that reads it. Lead only.',
        'proofs': proofs, 'members': members, 'fields': exposed, 'weapons': weapons,
        'snapshots': snapshots,
        'checks': {'snapshotsIdenticalToPinned': identical, 'snapshots': len(snapshots),
            'everyWeaponRecordUnique': True,
            'missilesExposable': sorted(k for k, m in missiles.items() if m.get('exposable')),
            'waspProjectileType': wasp['projectileType'], 'waspFunctionProjectileType': wasp['functionProjectileType']},
        'lifecycle': {
            'flight': 'Type record, read through the table lookup on every missile update (0x64283A, 0x643471): a '
                'write changes missiles already in flight, from their next update.',
            'starting_speed': 'Read once when a missile spawns (0x64114E): a write changes the next missile.',
            'projectileRow': 'The carried projectile row (damage +60, impact explosion +144) is read when the missile '
                'hits, like any projectile row.'},
        'multiplayer': ('The missile is an entity the shooter spawns (0xFDC140); every machine runs the SeekingMissile '
            'update on its own copy (no authority test in the movement loop 0x643479..) from its own type record, so a '
            'player without the same edit draws the vanilla flight. Damage and explosion come from the carried '
            'projectile, whose impact the shooter decides (research/projectile-homing: impact handler 0xB9E0C0).'),
        'swap': {
            'entity': ('Not offered. ProjectileWeapon +40 / +584 is spawned by resource on the shooter and replicated as '
                'an entity: another missile needs its unit, effects and package resident on every machine, and a '
                'non-missile entity would be spawned as a shot. No package or replication proof exists.'),
            'row': ('Not offered. ProjectileWeapon +0 reaches the missile only through the shooter\'s spawn info '
                '(0x61604F -> 0x6414E0): it changes the hit row (damage, impact explosion), never the missile\'s '
                'flight or model, and how another machine\'s copy of the spawned missile gets its type is not traced.'),
            'functionProjectile': ('ProjectileWeapon +576 (330 on the W.A.S.P.) is carried by the +584 missile the same '
                'way; it stays a donor output for other weapons (projectile-donors) and is not swapped on the W.A.S.P.'),
        },
        'notCovered': [
            'Lock-on (time, range, cone): no SeekingMissile member; the W.A.S.P. owns no lock-on component of its own '
            '(ProjectileWeapon, WeaponAssistedReload, WeaponCustomization, WeaponData, WeaponMagazine, WeaponReload). '
            'Not traced.',
            'javelin_firing_mode (+172), targeting_mode (+0), p/i/d factors, target_update_interval, angle_lost_guidance: '
            'read by code, effect not traced: unexposed.',
            'The carried projectile row\'s direct-hit damage: the support catalogue resolves the W.A.S.P. primary branch '
            'only partially (wiki drag / gravity mismatch, they are unused by a unit-driven projectile); unchanged.'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    result = build()
    text = json.dumps(result, indent=1) + '\n'
    if args.check:
        if OUTPUT.read_text(encoding='utf-8') != text:
            raise SystemExit('stale: ' + str(OUTPUT))
        print('up to date')
        return
    OUTPUT.write_text(text, encoding='utf-8', newline='\n')
    print(json.dumps(result['checks'], indent=1))


if __name__ == '__main__':
    main()
