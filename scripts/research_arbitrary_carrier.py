"""Arbitrary carrier research (research/docs/arbitrary-carrier-F5FEE03DCFDB.md): can ANY stratagem, the first target
being the Eagle Strafing Run, be the identity of a custom stratagem whose gameplay the Runtime supplies? Where does a
call's native gameplay get chosen, and what of it is shared, per player, or per call? Read-only, offline: the game.dll
image and the seven retained snapshots of build F5FEE03DCFDB, and research/offensive-stratagem-runtime. Nothing is
written; nothing in the proven Gas Barrage changes.

Proves [C] (pinned code) and observes [O] (snapshots):

1. The delivery kind. StratagemInfo +0x3C selects the execution family [O]: 0 every Eagle, 1 the orbital strikes (with
   the Laser and the Railcannon), 2 every hellpod (sentries, emplacements, mines, backpacks, support weapons,
   Resupply), 3 vehicles and exosuits, 5 the orbital barrages; 4, 6 and 7 mission types (7 Eagle Rearm). The payload
   list (+0x98, count +0xA0) names the entity resources a call spawns: an Eagle's one payload is the aircraft UNIT
   (Unit, Eagle, ProjectileWeapon, WeaponMagazine, Mount, Health ...); an orbital's is a fire-support entity
   (OrbitalShip, StratagemFiresupport, Bombardment or OrbitalAbility); a hellpod's is [the item, the pod
   0x73F8498BFFDCF415].
2. The beacon [C]. A thrown call is an entity of the beacon component (systems + 0x1380, updated by 0x6AB3E0 from
   0x571305). Each instance has a 0x40-byte data element (+0x0 the countdown, +0x4 the activation threshold, +0xC the
   STRATAGEM TYPE, +0x10 the position, +0x1C the drop position, +0x3C a flag) and a 0x8E8-byte state (+0x8E4 activated).
   Its init (0x6AE720) copies the type from the spawn parameters (+0x398) and registers every member in the entity's
   replicated state ({hash, kind, pointer}: the type 0xC2EB5C15, the countdown 0x6109F766 ...). The countdown is the
   call's ETA (0x6A5B70: row +0x54 through 0x879900, the delivery kind, the thrower's travel time; the threshold from
   row +0x60).
3. Activation [C]. Once, when the countdown crosses the threshold (state +0x8E4), the update passes the beacon's OWN
   type (+0xC) to the spawn dispatcher 0x6ABDB0. The dispatcher reads that type's row only then: no payload (+0xA0 0)
   spawns nothing; an Eagle (+0x3C 0) or a single payload spawns payload[0] directly; two payloads spawn payload[1]
   (the pod) carrying payload[0] (+0x3D8, the type at +0x3E4). Type 0 reads the all-zero default row (game+0x37CB470):
   nothing is spawned.
4. Eagle couplings outside the beacon [C, O]. The record build grants each row's linked type (+0xC8, at most +0xCC):
   every Eagle links Eagle Rearm (49); the post-call handler 0x66E6D0 has an Eagle branch (+0x3C 0) that checks the
   fleet (0x66E580: entries whose row links 49) for the rearm; after a rearm the Eagle entries carry the rearm's
   activation and end [O]. Uses come from the row only at the record build (0x879550); a converted slot keeps the
   token's.
5. Bombardment records [C]. 0x5043C0 resolves a bombardment handle {payload hash, entity}: the entity's PRIVATE copy
   (map +0x70, copies +0xB0, 192 bytes) if it has one, else the shared record by payload hash. A private copy is
   created only when a component delta is applied to that entity (0x856610 from the entity delta dispatcher 0x574280:
   the shared record copied, the delta applied, the copy slot and both maps written) and is removed with the instance
   (0x855950). The call-in ETA (0x6ADB40) builds a variant-applied copy of the record only to compute a time.

Output: research/arbitrary-carrier-F5FEE03DCFDB.json.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS, TABLE, RECORDS  # noqa: E402
from research_stratagem_slot_conversion import catalogue_roots  # noqa: E402

OUTPUT = ROOT / 'research/arbitrary-carrier-F5FEE03DCFDB.json'
OFFENSIVE = ROOT / 'research/offensive-stratagem-runtime-F5FEE03DCFDB.json'
DEFAULT_ROW = 0x37CB470
POD = 0x73F8498BFFDCF415
MISSION_SNAPSHOT = 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap'
REARM_SNAPSHOT = 'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap'
ROW_MEMBERS = {'delivery': 0x3C, 'uses': 0x50, 'spawnTime': 0x54, 'linger': 0x60, 'cooldown': 0x68,
    'cooldownType': 0x94, 'payloads': 0x98, 'payloadCount': 0xA0, 'linkedType': 0xC8, 'linkedMax': 0xCC}
DELIVERY = {0: 'eagle', 1: 'orbital strike', 2: 'hellpod', 3: 'vehicle', 4: 'mission (granted)', 5: 'orbital barrage',
    6: 'mission (special drop)', 7: 'eagle rearm'}

GAME = {
    'input': [
        (0xA904BB, 'call 0x671440', None, 'the matched type: the activation check'),
        (0xA9052E, 'call 0xa10820', None, 'the stratagem ball for the matched type'),
        (0xA90810, 'call 0x6a3c40', None, 'the call-in system'),
    ],
    'beacon': [
        (0x5712FB, 'lea rcx, [rdi + 0x1380]', None, 'the beacon component manager: systems + 0x1380 ...'),
        (0x571305, 'call 0x6ab3e0', None, '... updated every frame'),
        (0x6AE902, 'mov rax, qword ptr [r13 + 0x48]', None, 'beacon init: the spawn parameters ...'),
        (0x6AE90A, 'mov eax, dword ptr [rax + 0x398]', None, '... their stratagem type ...'),
        (0x6AE910, 'mov dword ptr [rdi + rcx + 0xc], eax', None, '... is the beacon element\'s +0xC'),
        (0x6AE928, 'mov dword ptr [r15 + rax*8], 0xc2eb5c15', None, 'the type in the replicated state (0xC2EB5C15)'),
        (0x6AE7D5, 'call 0x6a5b70', None, 'the countdown ...'),
        (0x6AE7EA, 'movss dword ptr [rdi + rcx], xmm0', None, '... is the element\'s +0x0'),
        (0x6AE7FF, 'mov dword ptr [r15 + rax*8], 0x6109f766', None, 'the countdown in the replicated state'),
        (0x6AE9FD, 'mov ecx, dword ptr [rax + 0x3c]', None, 'the type\'s delivery kind at init ...'),
        (0x6AEA00, 'cmp ecx, 3', None, '... 3 (vehicle) ...'),
        (0x6AEA05, 'cmp ecx, 6', None, '... or 6: a drop position computed now (row +0x78 bit 0, +0x7C)'),
    ],
    'countdown': [
        (0x6A5C69, 'call 0x879900', None, 'the ETA base (row +0x54) ...'),
        (0x6A5D1B, 'mov eax, dword ptr [rax + 0x3c]', None, '... the delivery kind ...'),
        (0x6A5D87, 'movss xmm2, dword ptr [rdi + 0x60]', None, '... the linger time (row +0x60) ...'),
        (0x6A5DAF, 'movss dword ptr [rcx + rax + 4], xmm1', None, '... the activation threshold (+0x4)'),
    ],
    'activation': [
        (0x6AB84A, 'mov eax, dword ptr [r12 + rdi + 0xc]', None, 'each beacon: its type'),
        (0x6ABB3C, 'movss dword ptr [rdi + rax], xmm0', None, 'the countdown minus the frame time'),
        (0x6ABB58, 'movss xmm0, dword ptr [r12 + rdi]', None, 'the countdown ...'),
        (0x6ABB5E, 'movss xmm1, dword ptr [r12 + rdi + 4]', None, '... and the threshold ...'),
        (0x6ABB65, 'comiss xmm1, xmm0', None, '... crossed:'),
        (0x6ABB77, 'cmp byte ptr [r13 + 0x8e4], 0', None, 'not yet activated ...'),
        (0x6ABB8D, 'mov byte ptr [r13 + 0x8e4], 1', None, '... activated once'),
        (0x6ABC14, 'mov ecx, dword ptr [r12 + rdi + 0xc]', None, 'the beacon\'s OWN type ...'),
        (0x6ABC72, 'call 0x6abdb0', None, '... to the spawn dispatcher'),
    ],
    'dispatcher': [
        (0x6ABE0E, 'lea r14, [rip + {rip}]', DEFAULT_ROW, 'type 0: the all-zero default row'),
        (0x6ABE19, 'cmp dword ptr [r14 + 0xa0], 0', None, 'no payload ...'),
        (0x6ABE21, 'je 0x6adb08', None, '... nothing is spawned'),
        (0x6ABE62, 'lea r14, [rip + {rip}]', TABLE, 'the StratagemInfo table ...'),
        (0x6ABE69, 'mov r14, qword ptr [r14 + r12*8]', None, '... the type\'s row, read at activation'),
        (0x6ABFEB, 'mov rdi, qword ptr [r14 + 0x98]', None, 'the payload list ...'),
        (0x6ABFF7, 'mov rdi, qword ptr [rdi]', None, '... payload[0]'),
        (0x6AC007, 'cmp dword ptr [r14 + 0x3c], r15d', None, 'an Eagle (delivery 0) spawns payload[0] itself'),
        (0x6AC011, 'mov rcx, qword ptr [r14 + 0x98]', None, 'else, with a second payload ...'),
        (0x6AC018, 'cmp qword ptr [rcx + 8], r15', None, '...'),
        (0x6AC03D, 'mov qword ptr [rsi + 0x3d8], rcx', None, '... payload[0] is the contents ...'),
        (0x6AC04B, 'mov dword ptr [rsi + 0x3e4], r12d', None, '... with the type ...'),
        (0x6AC052, 'cmp dword ptr [r14 + 0x3c], 6', None, '...'),
        (0x6AC05E, 'mov rdi, qword ptr [rdi + 8]', None, '... of payload[1], the entity spawned (the pod)'),
    ],
    'postCall': [
        (0x66E77C, 'mov r8d, dword ptr [rdi + r15*8 + 0x188]', None, 'a called entry\'s type'),
        (0x66EB2B, 'cmp dword ptr [rsi + 0x3c], 0', None, 'an Eagle (delivery 0) ...'),
        (0x66EB35, 'mov r8d, 0x31', None, '... with Eagle Rearm (49) ...'),
        (0x66EB41, 'call 0x670d50', None, '... in the record ...'),
        (0x66EB8A, 'call 0x66e580', None, '... checks the Eagle fleet for the rearm'),
        (0x66E696, 'cmp dword ptr [rax + 0xc8], 0x31', None, 'the fleet: entries whose row links Eagle Rearm'),
    ],
    'recordBuild': [
        (0x6AE4B1, 'mov r8d, dword ptr [rax + 0xc8]', None, 'the record build: each row\'s linked type ...'),
        (0x6AE4CE, 'mov ecx, dword ptr [rax + 0xcc]', None, '... at most this many ...'),
        (0x6AE4F7, 'call 0x879550', None, '... is granted with its initial uses'),
    ],
    'bombardmentRecords': [
        (0x504417, 'mov rdi, qword ptr [r11 + 0x70]', None, 'a handle\'s entity in the private-copy map ...'),
        (0x504456, 'cmp dword ptr [rcx], eax', None, '...'),
        (0x50446A, 'add rax, qword ptr [r11 + 0xb0]', None, '... its private copy (192 bytes) ...'),
        (0x50447D, 'jmp 0x503dc0', None, '... else the shared record by payload hash'),
        (0x5750F0, 'call 0x856610', None, 'the entity delta dispatcher applies a bombardment delta ...'),
        (0x8566F5, 'call 0x503dc0', None, '... copying the shared record ...'),
        (0x856796, 'call 0x515540', None, '... applying the delta ...'),
        (0x8567BB, 'lea rcx, [rbx + 0x70]', None, '... entity -> copy ...'),
        (0x8567C2, 'call 0x172f790', None, '...'),
        (0x8567CB, 'lea rcx, [rbx + 0x90]', None, '... copy -> entity ...'),
        (0x8567D4, 'call 0x172f790', None, '... a private copy exists from then on'),
        (0x855A60, 'lea r14, [rbx + 0x70]', None, 'the instance removed: its copy ...'),
        (0x855A74, 'call 0x172f8a0', None, '... removed with it'),
        (0x6ADD69, 'call 0x504180', None, 'the call-in ETA: a variant-applied record copy ...'),
        (0x6ADD8A, 'call 0x854100', None, '... only to compute a time'),
    ],
}

# The ownership and multiplayer class of every reference on the path ([C]/[O] as above; U where noted).
OWNERSHIP = [
    {'object': 'StratagemInfo row (presentation, code +0x40, delivery +0x3C, uses +0x50, ETA +0x54, cooldown +0x68, '
        'payload list +0x98, linked type +0xC8)', 'owner': 'shared global data (one static row per type, every player)',
        'redirect': 'row-global: every call of that type by anyone', 'multiplayer': 'unsafe'},
    {'object': 'mission record entry (type, uses, activation/end/arrival)', 'owner': 'per player (mission record; '
        'replicated as rpc_sync_stratagems)', 'redirect': 'per slot (the conversion, the fixed cooldown)',
        'multiplayer': 'unknown (replicated; the existing proofs are solo)'},
    {'object': 'call-in table entry (+8 type, +0x10 record key, +0x18 slot)', 'owner': 'per call, per player',
        'redirect': 'drives the HUD inbound state; not read by the spawn dispatcher', 'multiplayer': 'unknown'},
    {'object': 'beacon instance (+0xC type, +0x0 countdown, +0x4 threshold, +0x10/+0x1C positions)',
        'owner': 'spawned-instance state, one per throw; replicated entity state', 'redirect': 'per call: the type '
        'the dispatcher reads at activation', 'multiplayer': 'unknown (replicated; the spawning authority is not '
        'traced: presumably the host)'},
    {'object': 'payload entity resource (the Eagle aircraft unit, the orbital fire-support entity, the pod)',
        'owner': 'shared global data (entity settings by resource hash)', 'redirect': 'chosen by the row',
        'multiplayer': 'unsafe to modify'},
    {'object': 'Eagle aircraft components (Eagle, ProjectileWeapon, WeaponMagazine: projectiles 16, 27, 75)',
        'owner': 'shared global data per entity type', 'redirect': 'only by not spawning the aircraft',
        'multiplayer': 'unsafe to modify'},
    {'object': 'bombardment shared record (by payload hash)', 'owner': 'shared global data', 'redirect': 'the current '
        'carrier-local payload writes it (solo, an unused carrier)', 'multiplayer': 'unsafe'},
    {'object': 'bombardment private copy (by entity)', 'owner': 'spawned-instance state (one barrage)',
        'redirect': 'exists only if the entity was spawned with a delta', 'multiplayer': 'safe if it exists '
        '(instance only); unknown who runs the barrage'},
    {'object': 'projectile / explosion / status rows (shell 197 -> 82 -> 447, template 16)', 'owner': 'shared global '
        'data', 'redirect': 'referenced only', 'multiplayer': 'unsafe to modify'},
    {'object': 'Runtime-spawned projectiles (hd2.projectiles / spawn_projectile_row)', 'owner': 'per call, the local '
        'host', 'redirect': 'Runtime-supplied delivery', 'multiplayer': 'unknown (host only today)'},
]


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    names = {root['id']: name for name, root in catalogue_roots().items()}
    families = {}
    text = (ROOT / 'domains/stratagem_authoring.lua').read_text(encoding='utf-8')
    import re
    for m in re.finditer(r'\["name"\]="([^"]+)",\["family"\]="([^"]*)"', text):
        families[m.group(1)] = m.group(2)
    mem = base.Mem(MISSION_SNAPSHOT)
    g = mem.game
    if mem.read(g + DEFAULT_ROW, 400) != bytes(400):
        raise ValueError('the default row is not all zero')
    rows, by_delivery = [], defaultdict(list)
    for kind in range(1, 150):
        row = mem.ptr(g + TABLE + kind * 8)
        if not row:
            continue
        raw = mem.read(row, 400)
        stable = u32(raw, 4)
        name = names.get(stable)
        plist, count = struct.unpack_from('<Q', raw, 0x98)[0], u32(raw, 0xA0)
        payloads = ['0x%016X' % mem.u64(plist + 8 * i) for i in range(min(count, 4))]
        r = {'type': kind, 'id': stable, 'name': name, 'family': families.get(name), 'delivery': u32(raw, 0x3C),
            'uses': struct.unpack_from('<i', raw, 0x50)[0], 'spawnTime': struct.unpack_from('<f', raw, 0x54)[0],
            'cooldown': struct.unpack_from('<f', raw, 0x68)[0], 'cooldownType': u32(raw, 0x94),
            'payloads': payloads, 'linkedType': u32(raw, 0xC8), 'linkedMax': u32(raw, 0xCC)}
        rows.append(r)
        by_delivery[r['delivery']].append(r)
    mem.close()
    eagles = [r for r in rows if r['family'] == 'eagle']
    if not eagles or any(r['delivery'] != 0 or r['linkedType'] != 49 or len(r['payloads']) != 1 for r in eagles):
        raise ValueError('an Eagle is not delivery 0 with one payload linking Eagle Rearm')
    strafing = next(r for r in rows if r['name'] == 'Eagle Strafing Run')
    if (strafing['type'], strafing['payloads']) != (30, ['0x23A60681DD4383EC']):
        raise ValueError('the Eagle Strafing Run row changed: %r' % strafing)
    linked = sorted({(r['linkedType'], r['family']) for r in rows if r['linkedType']}, key=str)
    if [t for t, _ in linked] != [49] * len(linked):
        raise ValueError('a row other than an Eagle links a type: %r' % linked)
    pods = sorted({r['family'] for r in rows if len(r['payloads']) == 2 and r['payloads'][1] == '0x%016X' % POD
        and r['family']})
    delivery_families = {str(k): sorted({r['family'] or 'uncatalogued' for r in v}) for k, v in sorted(by_delivery.items())}
    empty = [{'type': r['type'], 'id': r['id'], 'delivery': r['delivery']} for r in rows if not r['payloads']]

    # Eagle Rearm on the Eagle entries [O]: after the rearm both Eagles carry its activation and end.
    mem = base.Mem(REARM_SNAPSHOT)
    g = mem.game
    state = mem.ptr(g + RECORDS) + 0x38
    entries = {}
    for k in range(mem.u32(state + 0x788)):
        raw = mem.read(state + 0x188 + k * 0x30, 0x30)
        entries[u32(raw, 0)] = struct.unpack_from('<QQQ', raw, 0x10)
    mem.close()
    rearm = {'rearm': entries.get(49), 'strafingRun': entries.get(30), 'rocketPods': entries.get(140)}
    if not (rearm['rearm'] and rearm['strafingRun'] and rearm['rearm'][:2] == rearm['strafingRun'][:2]
            == rearm['rocketPods'][:2]):
        raise ValueError('the Eagle entries do not carry the rearm\'s activation and end: %r' % rearm)

    offensive = json.loads(OFFENSIVE.read_text(encoding='utf-8'))
    components = {s['name']: [c['name'].replace('ComponentData', '') for p in s['payloadReports'] for c in p['components']]
        for s in offensive['stratagems']}
    strafing_projectiles = sorted({v for s in offensive['stratagems'] if s['name'] == 'Eagle Strafing Run'
        for p in s['payloadReports'] for c in p['components'] for ref in c['typedReferences']
        if ref['referenceClass'] == 'ProjectileType' for v in ref['values']})

    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'gameDll': {'sha256': base.PROFILE_DLL_SHA},
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation,
        'row': ROW_MEMBERS, 'deliveryKinds': {str(k): v for k, v in DELIVERY.items()},
        'deliveryFamilies': delivery_families, 'podFamilies': pods, 'pod': '0x%016X' % POD,
        'linkedTypes': [{'type': t, 'family': f} for t, f in linked], 'payloadless': empty,
        'defaultRow': '0x%X' % DEFAULT_ROW,
        'beacon': {'manager': 'systems + 0x1380 (systems = the game world + 0x40, from 0xAB5EC9 / 0xFDAF4F)',
            'element': {'stride': 0x40, 'countdown': 0x0, 'threshold': 0x4, 'type': 0xC, 'position': 0x10,
                'dropPosition': 0x1C, 'flag': 0x3C}, 'state': {'stride': 0x8E8, 'activated': 0x8E4},
            'arrays': {'entities': 0x60, 'state': 0x68, 'elements': 0x78, 'count': 0x38},
            'replicated': {'type': '0xC2EB5C15', 'countdown': '0x6109F766', 'threshold': '0x248FF28E',
                'position': '0x776786CE', 'dropPosition': '0xD5077FC6'}},
        'bombardment': {'privateMap': 0x70, 'privateCopies': 0xB0, 'copyMap': 0x90, 'copyCount': 0xA8,
            'copyCapacity': 0x78, 'copySize': 192},
        'strafingRun': {'row': strafing, 'components': components.get('Eagle Strafing Run'),
            'projectiles': strafing_projectiles},
        'orbitalComponents': components.get('Orbital 120mm HE Barrage'),
        'rearmObserved': {k: list(v) if v else None for k, v in rearm.items()},
        'ownership': OWNERSHIP}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; delivery families', delivery_families)


if __name__ == '__main__':
    main()
