"""Orbital Railcannon and Orbital Laser targeting: OrbitalAbilityComponent members by their readers. Read-only.

Question (0.30.4 user request): a third-party stat editor edits the Railcannon's search radius and tracking speed;
HD2Runtime exposes OrbitalAbility members on the Orbital Laser only. Which members steer the Railcannon (target search,
tracking, delay, shots) and the Laser, and which can be exposed?

Proven on build F5FEE03DCFDB from the pinned type library, the entity table, the retained snapshots and the
unprotected game.dll code (exact instruction pins):

1. Three OrbitalAbilityComponent records: the Orbital Laser's (record 0), the Orbital Railcannon Strike's (record 1),
   each owned by its stratagem's payload alone, and one unowned record. Table lookup 0x512820 (slot 308), by entity
   0x512E20; every reader below takes the record through it on every call (type data, no per-instance copy).
2. Creation (0x5F0660, one per strike): +460 is copied into the instance's remaining active time (+0x6C); the lifetime
   is +464 + +460 + the strike's start delay; the target re-search timer starts at +544; the shot countdown is the
   start delay + +540; a strike with a projectile type (+532, the Railcannon's 277) whose countdown is 0 fires at once.
3. Update (0x5F35B0, every frame): the lifetime ends the strike (0xFDC310); while +544 > 0 the target is searched
   again every +544 seconds; while +532 is set the shot countdown fires the projectile once when it reaches 0
   (0x5F5670); the beam closes on its target by a fraction min(1, distance / 10) x +468 x dt of the distance each
   frame (+468 read every frame, both branches of the +520 mode flag); with +520 = 0 (the Laser) the active time
   deals the damage ticks (0x5F26F0), with +520 = 1 (the Railcannon) the beam only tracks.
4. Target search (0x5F0FC0): +472 truncated to whole metres (cvttss2si) is the query radius around the strike (a
   radius below 1 m searches nothing), at most 512 candidates (0x8D6380). Called when the strike's spawn data is built
   (0x5F6230, the target goes into the spawn data) and at every re-search (the target is replicated, key 0x51B7584F).
5. The Railcannon fires once: the countdown crosses 0 once per strike; there is no shot-count member.

Member names are not published by any lead with a matching name length; the fields are named by what the code does.

Nothing here writes memory. Requires the research-only package capstone.
Output: research/orbital-targeting-F5FEE03DCFDB.json. `--check` compares with the committed output.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_entity_authoring as entity_research  # noqa: E402
import snapshot_regions  # noqa: E402
from scan import xref  # noqa: E402

OUTPUT = ROOT / 'research/orbital-targeting-F5FEE03DCFDB.json'
OA = 'OrbitalAbilityComponentData'
OWNERS = {'0xEC3575E7A93793BB': 'Orbital Laser', '0xAC129AA2DB5EABC9': 'Orbital Railcannon Strike'}
# OrbitalAbilityComponent members (offset, storage, hidden-name length, role from the readers).
MEMBERS = [
    (456, 'FP32', 13, 'start delay when +0 (u32) is non-zero (0 on every record: unused)'),
    (460, 'FP32', 8, 'active time: copied into the instance at creation'),
    (464, 'FP32', 11, 'lifetime tail: lifetime = +464 + +460 + start delay'),
    (468, 'FP32', 14, 'tracking rate: the beam closes min(1, d/10) x this x dt of the distance each frame'),
    (472, 'FP32', 13, 'target search radius (whole metres)'),
    (476, 'STRUCT', 18, 'DamageZoneInfo (Laser damage ticks; +480 = orbital.tick_interval)'),
    (520, 'UINT8', 28, 'mode flag: 0 damage ticks while active (Laser), 1 tracking only (Railcannon)'),
    (532, 'ENUM_UINT32', 15, 'ProjectileType fired by the shot countdown (Railcannon 277)'),
    (540, 'FP32', 22, 'shot delay: the countdown from the strike start to the shot'),
    (544, 'FP32', 23, 'target re-search interval (0 = the first target is kept)'),
]
FIELDS = {
    'Orbital Railcannon Strike': [
        ('orbital.search_radius', 472, 'metres', 1.0, 300.0, 'search',
         'The radius around the strike in which it picks its target (0x5F100C, truncated to whole metres; the query '
         'returns at most 512 candidates). 1 to 300 m (native 30; the Laser\'s is 50).'),
        ('orbital.movement_speed', 468, 'per second', 1.0, 1000.0, 'live',
         'How fast the targeting beam closes on its target: each frame it covers min(1, distance / 10) x this x dt of '
         'the remaining distance (0x5F4229). 1 to 1000 (native 90; above about 1 / dt it snaps).'),
        ('orbital.duration', 460, 'seconds', 1.5, 10.0, 'creation',
         'How long the targeting beam stays active (0x5F07C1). The strike lives this + 1 s (+464) after its start '
         'delay, and the shot must come before that: 1.5 to 10 s with orbital.fire_delay at most 2.4 s keeps it so.'),
        ('orbital.fire_delay', 540, 'seconds', 0.0, 2.4, 'creation',
         'Time from the strike\'s start to the shot (0x5F0A0C, the countdown 0x5F3817). 0 to 2.4 s (native 1.7), '
         'always below the shortest lifetime the duration range allows (1.5 + 1 s).'),
    ],
    'Orbital Laser': [
        ('orbital.retarget_interval', 544, 'seconds', 0.1, 60.0, 'live',
         'How often the laser looks for a new target (0x5F3656: only while positive; 0x5F3718 restarts it after each '
         'search). 0.1 to 60 s (native 1).'),
    ],
}

PINS = {
    'lookup': [
        (0x512836, 'mov r10, qword ptr [rax + 0xf12e18]', 'the OrbitalAbility table (slot 308)'),
        (0x51287C, 'imul rcx, rax, 0x228', 'record stride 552'),
        (0x512EEC, 'jmp 0x512820', 'by entity: the entity\'s type record'),
    ],
    'creation': [
        (0x5F070C, 'call 0x512e20', 'the strike\'s record'),
        (0x5F07C1, 'mov eax, dword ptr [r14 + 0x1cc]', '+460 ...'),
        (0x5F07CE, 'mov dword ptr [rdi + 0x6c], eax', '... is the instance\'s remaining active time'),
        (0x5F07C8, 'movss dword ptr [rdi + 0x70], xmm8', 'the start delay (0xA0AF50)'),
        (0x5F09E3, 'movss xmm0, dword ptr [r14 + 0x1d0]', 'lifetime = +464 ...'),
        (0x5F09EC, 'addss xmm0, dword ptr [rdi + 0x6c]', '... + the active time ...'),
        (0x5F09F5, 'addss xmm0, xmm8', '... + the start delay'),
        (0x5F09FA, 'movss dword ptr [rcx + r12*8], xmm0', 'the lifetime timer'),
        (0x5F0A00, 'mov eax, dword ptr [r14 + 0x220]', 'the re-search timer starts at +544'),
        (0x5F0A0C, 'addss xmm8, dword ptr [r14 + 0x21c]', 'the shot countdown: start delay + +540 ...'),
        (0x5F0A27, 'movss dword ptr [rdi + 0x3d0], xmm8', '... instance +0x3D0'),
        (0x5F0A30, 'cmp dword ptr [r14 + 0x214], 0', 'a strike with a projectile type (+532) ...'),
        (0x5F0A59, 'call 0x5f5670', '... whose countdown is 0 fires at once'),
    ],
    'update': [
        (0x5F361E, 'call 0x512e20', 'every frame, each strike\'s record'),
        (0x5F362B, 'subss xmm0, xmm6', 'the lifetime counts down'),
        (0x5F364C, 'call 0xfdc310', 'at 0 the strike entity is destroyed'),
        (0x5F3656, 'movss xmm0, dword ptr [rax + 0x220]', 'while +544 > 0 ...'),
        (0x5F36CD, 'call 0x5f0fc0', '... the target is searched again ...'),
        (0x5F3707, 'mov edx, 0x51b7584f', '... and replicated (key)'),
        (0x5F3713, 'call 0xfd97e0', '... (entity state write)'),
        (0x5F3718, 'mov eax, dword ptr [r14 + 0x220]', '... and the timer restarts at +544'),
        (0x5F380D, 'cmp dword ptr [r13 + 0x214], 0', 'a strike with a projectile type ...'),
        (0x5F382A, 'movss dword ptr [rdi + 0x3d0], xmm1', '... counts its shot down ...'),
        (0x5F3848, 'call 0x5f5670', '... and fires once when it crosses 0'),
        (0x5F387E, 'movss dword ptr [rdi + 0x6c], xmm0', 'the active time counts down'),
        (0x5F4098, 'cmp byte ptr [r13 + 0x208], 0', 'the mode flag (+520) picks the movement branch'),
        (0x5F4171, 'divss xmm4, dword ptr [rip + 0x1dd33db]', 'distance / 10 ...'),
        (0x5F4229, 'mulss xmm3, dword ptr [r13 + 0x1d4]', '... x +468 ...'),
        (0x5F4232, 'mulss xmm3, xmm15', '... x dt, clamped to 1: the fraction of the way the beam moves'),
        (0x5F43B6, 'mulss xmm3, dword ptr [r13 + 0x1d4]', '+468 (the other branch)'),
        (0x5F4450, 'mulss xmm1, dword ptr [r13 + 0x1d4]', '+468'),
        (0x5F4788, 'movss xmm0, dword ptr [r13 + 0x1d4]', '+468 (the beam height step)'),
        (0x5F4526, 'movss xmm0, dword ptr [rdi + 0x6c]', 'while the active time lasts ...'),
        (0x5F4563, 'cmp byte ptr [r13 + 0x208], r14b', '... a strike with mode flag 0 ...'),
        (0x5F460C, 'call 0x5f26f0', '... deals its damage ticks'),
    ],
    'search': [
        (0x5F1004, 'call 0x512e20', 'the strike\'s record'),
        (0x5F100C, 'cvttss2si rsi, dword ptr [rax + 0x1d8]', '+472 truncated to whole metres'),
        (0x5F1018, 'test esi, esi', '0 ...'),
        (0x5F101A, 'je 0x5f1fa2', '... searches nothing'),
        (0x5F109B, 'mov r8d, 0x200', 'at most 512 candidates'),
        (0x5F10A7, 'mov ecx, esi', 'the radius'),
        (0x5F10CF, 'call 0x8d6380', 'the spatial query'),
        (0x5F6394, 'call 0x5f0fc0', 'the strike\'s spawn data searches its first target'),
        (0x5F63E8, 'mov dword ptr [r14 + rax*8], 0x51b7584f', 'and carries it in the spawn data (key)'),
    ],
    'shot': [
        (0x5F5744, 'mov ecx, dword ptr [rax + 0x214]', 'the shot fires the record\'s projectile type (+532)'),
    ],
}
CONSTANTS = {0x23C7554: 10.0}

SNAPSHOT_LUA = r'''
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local b=require('hd2runtime/core/bytes')
local json=require('hd2runtime/primary_mapper/json')
local reader=Reader.new(source)
local roots=discover.locate(source,reader,profile,{entity=true})
local catalog=entities.capture(reader,roots.entity,profile,{'OrbitalAbilityComponentData'})
local want={['0xEC3575E7A93793BB']=true,['0xAC129AA2DB5EABC9']=true}
local out={records={}}
for _,c in ipairs(catalog.candidates)do
 if want[c.resourceHash]then
  local ok,r=pcall(catalog.record,c,'OrbitalAbilityComponentData')
  out.records[c.resourceHash]=ok and{hex=b.hex(r.bytes),record=r.identity.recordIndex,row=r.identity.indexRow,
   owners=r.identity.ownerCount}or{error=tostring(r)}
 end
end
return json.encode(out)
'''


def hexid(value: int) -> str:
    return '0x%016X' % value


def layout(native) -> list:
    members = {m['offset64']: m for m in native.typelib_module.layout(native.typelib, 'OrbitalAbilityComponent',
        structured=True)['members']}
    out = []
    for offset, storage, length, role in MEMBERS:
        member = members[offset]
        if member.get('storage') != storage or not str(member['name']).endswith('inferred_length=%d' % length):
            raise ValueError('OrbitalAbilityComponent +%d changed' % offset)
        out.append({'offset': offset, 'storage': storage, 'hiddenNameLength': length, 'role': role})
    return out


def value(raw: bytes, offset: int, storage: str):
    if storage == 'FP32':
        return round(struct.unpack_from('<f', raw, offset)[0], 6)
    if storage == 'UINT8':
        return raw[offset]
    if storage == 'STRUCT':
        return raw[offset:offset + 28].hex()
    return struct.unpack_from('<I', raw, offset)[0]


def build() -> dict:
    native = entity_research.Native()
    img = xref.CodeImage.from_snapshot()
    proofs = {group: [img.pin(rva, role, asm) for rva, asm, role in items] for group, items in PINS.items()}
    constants = {}
    for rva, expected in CONSTANTS.items():
        if img.f32(rva) != expected:
            raise ValueError('constant at %x changed' % rva)
        constants['0x%X' % rva] = expected
    members = layout(native)
    body, _, offset, size, count = native.table(OA)
    owners = native.owners(OA)
    records = []
    for index in range(count):
        raw = body[offset + index * size:offset + (index + 1) * size]
        own = [hexid(o) for o in owners.get(index, [])]
        records.append({'record': index, 'owners': own, 'stratagem': OWNERS.get(own[0]) if len(own) == 1 else None,
            'values': {str(m[0]): value(raw, m[0], m[1]) for m in MEMBERS}, 'raw': raw.hex()})
    by_name = {r['stratagem']: r for r in records if r['stratagem']}
    if set(by_name) != set(OWNERS.values()):
        raise ValueError('the OrbitalAbility owners changed')
    rail, laser = by_name['Orbital Railcannon Strike'], by_name['Orbital Laser']
    if (rail['values']['520'], laser['values']['520'], rail['values']['532'], laser['values']['532']) != (1, 0, 277, 0):
        raise ValueError('the mode flag or projectile type changed')
    fields = []
    for name, items in FIELDS.items():
        record = by_name[name]
        for field, member, unit, low, high, timing, note in items:
            native_value = record['values'][str(member)]
            if not low <= native_value <= high:
                raise ValueError('%s %s native %s outside its range' % (name, field, native_value))
            fields.append({'stratagem': name, 'field': field, 'offset': member, 'record': record['record'],
                'native': native_value, 'unit': unit, 'min': low, 'max': high, 'readTiming': timing, 'note': note})
    snapshots, identical = {}, True
    folder = build_profile.snapshot_directory()
    for path in sorted(folder.glob(build_profile.BUILD_ID + '-*.hd2snap')):
        snap = json.loads(snapshot_regions.run_lua(SNAPSHOT_LUA, snapshot=path))
        for key, live in snap['records'].items():
            pinned = next(r for r in records if r['owners'] == [key])
            same = live.get('hex', '').lower() == pinned['raw'] and live.get('record') == pinned['record'] \
                and live.get('owners') == 1
            live['identicalToPinned'] = same
            live.pop('hex', None)
            identical = identical and same
        snapshots[path.name] = snap['records']
    for record in records:
        record.pop('raw')
    return {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'writes': 0, 'protectionChanges': 0,
        'gameDll': {'sha256': img.sha256}, 'layout': members, 'proofs': proofs, 'constants': constants,
        'records': records, 'fields': fields, 'snapshots': snapshots,
        'checks': {'snapshotsIdenticalToPinned': identical, 'snapshots': len(snapshots)},
        'constraints': {
            'shotBeforeEnd': ('The shot fires at start delay + fire_delay; the strike ends at start delay + duration + '
                '+464 (1 s, never written). The ranges keep fire_delay (at most 2.4) below duration + 1 (at least '
                '2.5), so the shot always comes before the end.'),
            'searchRadius': 'Truncated to whole metres; a radius below 1 m searches nothing (the strike keeps the '
                'beacon position), so the range starts at 1.'},
        'multiplayer': ('A type record on every machine. The target is searched by the machine that builds the strike\'s '
            'spawn data (0x5F6230) and at each re-search, and is replicated (key 0x51B7584F); the tracking (+468) and the '
            'countdowns run on every machine from its own record. Every machine should run the same mod; which machine '
            'fires the Railcannon\'s shot (0x5F5670) is not traced.'),
        'notCovered': [
            'Target priority (which enemy is preferred): the search scores candidates by their own records (not the '
            'strike\'s); not exposed.',
            'The number of Railcannon shots: no member; the countdown fires once.',
            '+464 (the lifetime tail) and +456 / +0 (unused start delay path): not exposed.',
            'The Laser\'s existing orbital.duration / movement_speed / search_radius / tick_interval (beam attack) are '
            'unchanged; retarget_interval is added beside them.'],
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
    print(json.dumps([(f['stratagem'], f['field'], f['native']) for f in result['fields']]))


if __name__ == '__main__':
    main()
