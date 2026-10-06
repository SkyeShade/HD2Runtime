"""Enemy spawn weights (docs/enemy-spawns.md): which enemy type a spawn picks, proven read-only on build F5FEE03DCFDB from
the game.dll image and the retained snapshots.

1. The rosters. game.dll keeps one static enemy roster per faction in its .data: rows of 0x80 bytes (row +0x00 the u32
   spawn group key, +0x08 the u64 enemy entity type, +0x10 the class, +0x30 ten f32 weights, one per difficulty
   1..10, +0x58 the subfaction tags). At mission setup the faction installer (0x94D340) stores the roster descriptor
   of the mission's faction in the AI manager (manager +0x660: Terminids 2 -> game+0x21CBD60, Illuminate 4 ->
   game+0x21CE910, Automatons 8 -> game+0x21CBCB0). Each descriptor is {rows, count}: 45 Terminid rows at
   game+0x32B6BA0, 46 Illuminate rows at game+0x32B8220, 61 Automaton rows at game+0x32B9920 (the per-faction lookup
   0x94BA40 scans exactly those extents).
2. The pick. PickEnemy (0x953150, manager, group key, roster) walks the roster's rows (0x9531F2..0x9531F6: row = rows +
   index*0x80), keeps the rows of that group (0x9531FA) whose subfaction tags are active (0x9531FE / 0x953209), reads
   each one's weight for the mission's difficulty (manager +0x518C4, 1..10: 0x953212..0x95321B), skips a weight of 0
   or less (0x953226 / 0x953229), sums them (0x953234), draws a uniform number below the sum from the game's PCG
   generator (0x95325E..0x953291) and walks the kept rows subtracting each weight until it runs out (0x9532B6..
   0x9532C6): an enemy type is picked with probability weight / sum of its group. Every spawn system that picks an
   enemy type calls it (the census: 14 call and tail-call sites).
3. A weight of 0 is never picked; scaling a type's weights by k scales its share within each group it is in (the
   group's other types keep their weights). The number of enemies a spawn makes is not decided here.
4. The weights also decide what loads: the mission's package selection (0xABCB30) takes the rows whose weight at the
   mission difficulty is above 0 (0xABD6AC) and loads their enemies' packages. So a weight may go to 0 at any time,
   and a positive weight may be scaled to another positive one at any time, but a weight must never go from 0 to
   positive while a mission (or its preparation) runs: that enemy's packages may not be loaded.
5. The rosters are static: byte-identical in every retained snapshot (aboard the ship and through a whole mission), and
   no instruction stores into them (the census of rip-relative and roster-indexed stores).

Output: research/enemy-spawn-weights-F5FEE03DCFDB.json.  py scripts/research_enemy_spawn_weights.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/enemy-spawn-weights-F5FEE03DCFDB.json'
ENTITIES = ROOT / 'domains/event_entities.lua'
SNAPSHOTS = ['F5FEE03DCFDB-20260926T222226Z.hd2snap',
    'F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
MANAGER_GLOBAL = 0x3326D10
MANAGER = {'roster': 0x660, 'faction': 0x518BC, 'difficulty': 0x518C4, 'tags': 0x518D4}
ROW = {'stride': 0x80, 'group': 0x00, 'entity': 0x08, 'class': 0x10, 'weights': 0x30, 'difficulties': 10, 'tags': 0x58}
FACTIONS = [
    {'name': 'terminids', 'faction': 2, 'descriptor': 0x21CBD60, 'rows': 0x32B6BA0, 'count': 45},
    {'name': 'illuminate', 'faction': 4, 'descriptor': 0x21CE910, 'rows': 0x32B8220, 'count': 46},
    {'name': 'automatons', 'faction': 8, 'descriptor': 0x21CBCB0, 'rows': 0x32B9920, 'count': 61},
]

PROOFS = {
    'installer': [
        (0x94D3D3, 'cmp ecx, 2', None, 'the mission faction: Terminids'),
        (0x94D3D8, 'cmp ecx, 4', None, 'Illuminate'),
        (0x94D3DD, 'cmp ecx, 8', None, 'Automatons'),
        (0x94D3E2, 'lea rax, [rip + {rip}]', 0x21CBCB0, 'the Automaton roster descriptor'),
        (0x94D3EB, 'lea rax, [rip + {rip}]', 0x21CE910, 'the Illuminate roster descriptor'),
        (0x94D3F4, 'lea rax, [rip + {rip}]', 0x21CBD60, 'the Terminid roster descriptor'),
        (0x94D3FB, 'mov qword ptr [r11 + 0x660], rax', None, 'stored as the AI manager\'s roster (+0x660)'),
    ],
    'lookup': [
        (0x94BA47, 'mov ecx, dword ptr [rax + 0x518bc]', None, 'per-faction lookup: the mission faction'),
        (0x94BA5A, 'lea r8, [rip + {rip}]', 0x32B6BA8, 'the Terminid rows (entity column)'),
        (0x94BA6C, 'sub r8, -0x80', None, 'row stride 0x80'),
        (0x94BA70, 'cmp ecx, 0x2d', None, '45 Terminid rows'),
        (0x94BB1D, 'lea r8, [rip + {rip}]', 0x32B9928, 'the Automaton rows'),
        (0x94BB2F, 'cmp ecx, 0x3d', None, '61 Automaton rows'),
        (0x94BB91, 'lea r8, [rip + {rip}]', 0x32B8228, 'the Illuminate rows'),
        (0x94BBA3, 'cmp ecx, 0x2e', None, '46 Illuminate rows'),
    ],
    'pick': [
        (0x953150, 'mov qword ptr [rsp + 0x10], rbx', None, 'PickEnemy(manager, group key, roster)'),
        (0x953176, 'mov r12, qword ptr [rcx + 0x660]', None, 'default: the manager\'s roster'),
        (0x953187, 'mov edi, dword ptr [r12 + 8]', None, 'its row count'),
        (0x9531F2, 'shl rdi, 7', None, 'row index x 0x80'),
        (0x9531F6, 'add rdi, qword ptr [r12]', None, '+ the rows'),
        (0x9531FA, 'cmp dword ptr [rdi], ebx', None, 'the row\'s group key is the requested group'),
        (0x9531FE, 'lea rdx, [rdi + 0x58]', None, 'its subfaction tags'),
        (0x953209, 'call 0x177e3c0', None, 'are active in this mission'),
        (0x953212, 'mov eax, dword ptr [r13 + 0x518c4]', None, 'the mission difficulty (1..10)'),
        (0x953219, 'dec eax', None, 'minus 1'),
        (0x95321B, 'movss xmm0, dword ptr [rdi + rax*4 + 0x30]', None, 'the row\'s weight for that difficulty'),
        (0x953226, 'comiss xmm0, xmm2', None, 'compared with 0'),
        (0x953229, 'jbe 0x953234', None, 'a weight of 0 or less is not a candidate'),
        (0x953234, 'addss xmm1, xmm0', None, 'the weights are summed'),
        (0x95325E, 'movabs rcx, 0x5851f42d4c957f2d', None, 'the game\'s PCG random step'),
        (0x953291, 'mulss xmm0, xmm1', None, 'a uniform number below the sum'),
        (0x95329A, 'mov r8d, dword ptr [r13 + 0x518c4]', None, 'the difficulty again'),
        (0x9532B6, 'shl rax, 5', None, 'candidate row x 32 (+ difficulty - 1) dwords'),
        (0x9532BD, 'subss xmm0, dword ptr [rdx + rax*4 + 0x30]', None, 'minus each candidate\'s weight in turn'),
        (0x9532C3, 'comiss xmm2, xmm0', None, 'until it runs out'),
        (0x9532C6, 'jae 0x95339b', None, 'that candidate is picked'),
    ],
}
PICK = 0x953150
PICK_CALLERS = [0x68401D, 0x7F761B, 0x7F7664, 0x802000, 0x85881D, 0x8694EA, 0x90E9CF, 0x90F315, 0x9533BA, 0x9533D8,
    0x95341B, 0x95346B, 0x9FE88E, 0x11C8CA7]
# Every reader of a weight with the roster's indexing (row = rows + index*0x80, + 0x30 + 4*(difficulty - 1)).
WEIGHT_READERS = {0x94C1E9: 'the group composition estimate', 0x94C26F: 'the group composition estimate',
    0x94C2E3: 'the group composition estimate', 0x95321B: 'PickEnemy', 0x9532BD: 'PickEnemy',
    0xABD6AC: 'the mission\'s enemy package selection: a row whose weight at the mission difficulty is above 0 '
        '(xmm6 = 0, 0xABD050) gets its enemy\'s packages loaded'}
# Matches of the same shape that are not roster reads.
NOT_ROSTER = {0x8E906A: '12-byte vector records (index x 3 dwords + 0x28/0x2C/0x30): not a roster'}


def entity_names() -> dict[int, dict]:
    text = ENTITIES.read_text(encoding='utf-8')
    out = {}
    for match in re.finditer(r'\["([0-9A-F]{16})"\]=\{([^{}]*)\}', text):
        body = match.group(2)
        item = {}
        for key in ('name', 'display', 'id', 'faction', 'kind'):
            found = re.search(r'\["%s"\]="([^"]*)"' % key, body)
            if found:
                item[key] = found.group(1)
        out[int(match.group(1), 16)] = item
    return out


def census(image) -> dict:
    """Stores into a roster (rip-relative), weight reads with the roster's indexing, and the calls of PickEnemy."""
    pattern = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')
    lo = min(f['rows'] for f in FACTIONS)
    hi = max(f['rows'] + f['count'] * ROW['stride'] for f in FACTIONS)
    stores, rip_refs, readers, calls, shl = [], [], {}, [], []
    for rva, size, mnemonic, operands in image.sweep():
        match = pattern.search(operands)
        if match:
            target = rva + size + int(match.group(2), 16) * (1 if match.group(1) == '+' else -1)
            if lo <= target < hi:
                rip_refs.append({'rva': rva, 'target': target, 'asm': mnemonic + ' ' + operands})
                if operands.split(',')[0].find('[') >= 0 and mnemonic not in ('cmp', 'test', 'lea'):
                    stores.append(rva)
        if mnemonic == 'shl' and operands.endswith(', 7'):
            shl.append(rva)
        shl = [s for s in shl if rva - s < 0x80]
        if shl and re.search(r'\*4 \+ 0x30\]', operands) and mnemonic in ('movss', 'subss', 'addss', 'mulss',
                'comiss', 'divss'):
            readers[rva] = mnemonic + ' ' + operands
        if mnemonic in ('call', 'jmp') and operands == hex(PICK):
            calls.append(rva)
        if mnemonic == 'shl' and operands.endswith(', 5'):
            shl.append(rva)
    if stores:
        raise ValueError('an instruction stores into a roster: %r' % [hex(s) for s in stores])
    for rva in NOT_ROSTER:
        readers.pop(rva, None)
    if sorted(readers) != sorted(WEIGHT_READERS):
        raise ValueError('the weight reader census changed: %r' % {('%X' % k): v for k, v in readers.items()})
    if calls != PICK_CALLERS:
        raise ValueError('the PickEnemy callers changed: %r' % [hex(c) for c in calls])
    return {'ripReferences': rip_refs, 'ripStores': [],
        'notRoster': [{'rva': rva, 'reason': why} for rva, why in sorted(NOT_ROSTER.items())],
        'weightReaders': [{'rva': rva, 'asm': readers[rva], 'role': WEIGHT_READERS[rva]} for rva in sorted(readers)],
        'pickCallers': calls}


def rosters(images: dict[str, bytes]) -> list[dict]:
    names = entity_names()
    reference = images[SNAPSHOTS[0]]
    out = []
    for faction in FACTIONS:
        pointer, count = struct.unpack_from('<QI', reference, faction['descriptor'])
        extent = reference[faction['rows']:faction['rows'] + faction['count'] * ROW['stride']]
        digests = {name: hashlib.sha256(img[faction['rows']:faction['rows'] + faction['count'] * ROW['stride']])
            .hexdigest().upper() for name, img in images.items()}
        if len(set(digests.values())) != 1:
            raise ValueError('the %s roster differs between snapshots: %r' % (faction['name'], digests))
        if count != faction['count']:
            raise ValueError('the %s descriptor counts %d rows' % (faction['name'], count))
        rows = []
        for index in range(faction['count']):
            row = extent[index * ROW['stride']:(index + 1) * ROW['stride']]
            group, = struct.unpack_from('<I', row, ROW['group'])
            entity, = struct.unpack_from('<Q', row, ROW['entity'])
            weights = list(struct.unpack_from('<10f', row, ROW['weights']))
            tags = [t for t in struct.unpack_from('<2I', row, ROW['tags']) if t]
            if not entity or any(not (0 <= w <= 1000) for w in weights):
                raise ValueError('an implausible %s row %d' % (faction['name'], index))
            info = names.get(entity, {})
            rows.append({'index': index, 'group': '%08X' % group, 'entity': '%016X' % entity,
                'name': info.get('display') or info.get('name'), 'id': info.get('id'), 'kind': info.get('kind'),
                'class': struct.unpack_from('<I', row, ROW['class'])[0],
                'weights': [round(w, 6) for w in weights], 'weightsHex': row[ROW['weights']:ROW['weights'] + 40].hex(),
                'tags': ['%08X' % t for t in tags], 'rowSha256': hashlib.sha256(row).hexdigest().upper()})
        out.append({'name': faction['name'], 'faction': faction['faction'], 'descriptor': faction['descriptor'],
            'rows': faction['rows'], 'count': faction['count'], 'sha256': digests[SNAPSHOTS[0]],
            'descriptorRowsPointsAt': 'rows', 'entries': rows})
    return out


def build() -> dict:
    images = {}
    for name in SNAPSHOTS:
        snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / name)
        if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
            raise ValueError('snapshot fingerprint differs from the pinned profile: ' + name)
        image_base, data = snap.module_image('game.dll')
        snap.close()
        for faction in FACTIONS:
            pointer, count = struct.unpack_from('<QI', data, faction['descriptor'])
            if pointer - image_base != faction['rows'] or count != faction['count']:
                raise ValueError('%s: the %s descriptor does not name its rows' % (name, faction['name']))
        images[name] = data
    reference = images[SNAPSHOTS[1]]
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[1])
    image_base, _ = snap.module_image('game.dll')
    snap.close()
    image = base.Image(reference, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS[1:]}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    mission = []
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        manager = mem.ptr(mem.game + MANAGER_GLOBAL)
        roster = mem.ptr(manager + MANAGER['roster']) if manager else None
        mission.append({'snapshot': name, 'faction': mem.u32(manager + MANAGER['faction']) if manager else None,
            'difficulty': mem.u32(manager + MANAGER['difficulty']) if manager else None,
            'roster': (roster - mem.game) if roster else None})
        mem.close()
    return {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'manager': {'global': MANAGER_GLOBAL, **MANAGER}, 'row': ROW,
        'factions': rosters(images),
        'semantics': {
            'weights': 'row +0x30: ten f32, the weight of this row in its spawn group at difficulty 1..10; PickEnemy '
                'picks a row of the group with probability weight / sum (0 or less: never)',
            'group': 'row +0x00: the u32 spawn group key PickEnemy is asked for',
            'tags': 'row +0x58: subfaction tags; a row with a tag is a candidate only while that subfaction is active',
            'static': 'the rosters are game.dll .data, byte-identical in every retained snapshot; nothing stores '
                'into them',
            'host': 'enemies are spawned by the mission host\'s AI: only the host\'s rosters decide picks',
            'packages': 'a mission loads the packages of the rows whose weight at its difficulty is above 0: a weight '
                'never goes from 0 to positive during a mission or its preparation'},
        'proofs': proofs, 'census': census(image), 'pinnedBytesMismatchPerSnapshot': relocation,
        'missionObservations': mission,
        'unproven': [
            'Live: a changed weight changes how often that enemy type spawns (the pick is proven, not observed).',
            'How many enemies a spawn makes (group sizes and budgets) is decided elsewhere and not changed by a weight.',
            'The meaning of the row members other than the group key, entity, class, weights and tags.',
            'The variant rows (descriptor +0x10, 0x30 bytes) that swap types by difficulty are read but not written.'],
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
        'rows': {f['name']: f['count'] for f in report['factions']},
        'pickCallers': len(report['census']['pickCallers']), 'missions': report['missionObservations']}, indent=1))


if __name__ == '__main__':
    main()
