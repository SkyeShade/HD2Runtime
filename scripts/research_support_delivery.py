"""A support stratagem's delivery: the hellpod a support beacon spawns and the exact weapon entities its rack holds
(research/docs/gas-eat-F5FEE03DCFDB.md, "Delivery" and "Capture"). Read-only, offline: the game.dll image and the
retained mission snapshots of build F5FEE03DCFDB. Nothing is written.

Proves:

1. The pod names its beacon and its type. At the activation the dispatcher fills its spawn context (+0x3D8 the first
   payload's resource, +0x3E4 the dispatched type, +0x3F8 the beacon entity) and the pod is created into the Transport
   component (game+0x3326518: handles +0x38 (entity handle records: +0 resource, +8 entity, +0x10 network id), 0x40-byte
   elements at +0x40, 0x18-byte blocks at +0x48). Its element +0x0 = the content resource (0x6D9835 / 0x6D983C), its
   block +0xC = the dispatched TYPE (0x6D98BE / 0x6D98C5) and its block +0x10 = the BEACON's network id (0x6DBF43 ..
   0x6DBF52: the beacon entity through 0xFD9AF0, entity -> network id).
2. The content spawn names the rack. About 0.5 s after the landing the authority creates the content (0xFDC140) and
   writes the created entity into element +0x8 and +0x24 (0x6D9321 .. 0x6D932B): for a support weapon, its rack.
3. The rack names its items. HellpodRack (game+0x3326A58: entity map keys +0x28 (8-byte slots: key, index), capacity
   +0x30, empty +0x34, multiplier +0x38; 0x2C-byte elements at +0x50): +0x28 = the stratagem type from the item context
   (0x938B9A / 0x938BA0); +0x8 + 4 x slot = the network id of the item spawned into that slot (0x935A93 / 0x935A97, in
   the same native call as element +0x8), 0x7FFF none. A slot's item leaving the rack is found by its network id
   (0x937574 .. 0x937587: the slots at +0x8, 4 bytes each) and the slot reset.
4. The EAT-17's own data: its row's payload list names its rack and the pod payload; its rack's item is the EAT-17
   launcher entity (resource 0x80932FA0ED6901D3).

So a Runtime that knows its beacon's network id finds its pod (block +0x10 and +0xC), then the rack (element +0x8),
then the exact launcher entities (the rack's slots, through the game's own network id map): no scan of anything else.

Output: research/support-delivery-F5FEE03DCFDB.json.
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
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/support-delivery-F5FEE03DCFDB.json'
SNAPSHOTS = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap']
TRANSPORT, RACK, TABLE = 0x3326518, 0x3326A58, 0x37CB600
LAYOUT = {
    'transport': {'global': TRANSPORT, 'count': 0x10, 'handles': 0x38, 'elements': 0x40, 'stride': 0x40,
        'blocks': 0x48, 'blockStride': 0x18, 'content': 0x0, 'contentEntity': 0x8, 'contentEntityCopy': 0x24,
        'type': 0xC, 'beaconNetwork': 0x10},
    'handle': {'resource': 0x0, 'entity': 0x8, 'network': 0x10},
    'rack': {'global': RACK, 'keys': 0x28, 'capacity': 0x30, 'empty': 0x34, 'multiplier': 0x38, 'handles': 0x40,
        'elements': 0x50, 'stride': 0x2C, 'present': 0x0, 'slotCount': 0x4, 'slots': 0x8, 'maxSlots': 8, 'type': 0x28,
        'noItem': 0x7FFF},
}
EAT = {'name': 'EAT-17 Expendable Anti-Tank', 'item': '0x80932FA0ED6901D3', 'rack': '0x0DC7A18342B62BEC',
    'projectile': 132, 'impactExplosion': 376}
PROJECTILE_TABLE, PROJECTILE_IMPACT = 0x37C7670, 0x90

PROOFS = {
    'pod': [
        (0x6D9835, 'mov rcx, qword ptr [r15 + 0x3d8]', None, 'the dispatch context +0x3D8: the content resource'),
        (0x6D983C, 'mov qword ptr [rsi], rcx', None, 'Transport element +0x0'),
        (0x6D98BE, 'mov eax, dword ptr [r15 + 0x3e4]', None, 'the dispatch context +0x3E4: the dispatched type'),
        (0x6D98C5, 'mov dword ptr [rcx + r14 + 0xc], eax', None, 'Transport block +0xC'),
        (0x6DBF3F, 'mov rax, qword ptr [r15 + 0x48]', None, 'the Transport blocks'),
        (0x6DBF43, 'mov ecx, dword ptr [rax + 0x3f8]', None, 'the dispatch context +0x3F8: the beacon entity'),
        (0x6DBF49, 'call 0xfd9af0', None, 'its network id'),
        (0x6DBF52, 'mov dword ptr [rbx + rcx + 0x10], eax', None, 'Transport block +0x10: the beacon\'s network id'),
    ],
    'content': [
        (0x6D9321, 'call 0xfdc140', None, 'the content spawn creates the content entity'),
        (0x6D9326, 'mov dword ptr [r12 + 8], esi', None, 'Transport element +0x8: the content entity'),
        (0x6D932B, 'mov dword ptr [r12 + 0x24], esi', None, 'and +0x24'),
    ],
    'rack': [
        (0x938A55, 'mov rsi, qword ptr [rip + {rip}]', RACK, 'the HellpodRack component'),
        (0x938A76, 'mov r10d, dword ptr [rsi + 0x30]', None, 'its entity map capacity'),
        (0x938A7C, 'mov r11d, dword ptr [rsi + 0x38]', None, 'its multiplier'),
        (0x938A80, 'imul r11d, eax', None, 'times the entity'),
        (0x938A95, 'mov rbx, qword ptr [rsi + 0x28]', None, 'its keys (8 bytes: entity, index)'),
        (0x938A99, 'mov edi, dword ptr [rsi + 0x34]', None, 'the empty key'),
        (0x938B9A, 'mov eax, dword ptr [rax + 0x398]', None, 'the item context\'s stratagem type ...'),
        (0x938BA0, 'mov dword ptr [rbx + rcx + 0x28], eax', None, '... into the rack element +0x28'),
        (0x935A93, 'mov rax, qword ptr [rsi + 0x50]', None, 'the rack elements'),
        (0x935A97, 'mov dword ptr [r12 + rax], ecx', None, 'a spawned item\'s network id into its slot'),
        (0x937574, 'imul rsi, rsi, 0x2c', None, 'a rack element is 0x2C bytes'),
        (0x937578, 'add rsi, 8', None, 'its slots at +0x8'),
        (0x93757C, 'add rsi, qword ptr [r14 + 0x50]', None, 'from the elements'),
        (0x937587, 'call 0xfd9ba0', None, 'a slot\'s network id -> its entity (an item leaving the rack)'),
        (0x937598, 'cmp ebp, 8', None, '8 slots'),
    ],
}


def observe(name: str) -> dict:
    mem = base.Mem(name)
    g = mem.game
    T, R = mem.ptr(g + TRANSPORT), mem.ptr(g + RACK)
    t, r = LAYOUT['transport'], LAYOUT['rack']
    out = {'snapshot': name, 'transport': mem.u32(T + t['count']), 'racks': mem.u32(R + 0x10), 'rackElements': []}
    for i in range(min(out['racks'] or 0, 64)):
        raw = mem.read(mem.ptr(R + r['elements']) + i * r['stride'], r['stride'])
        present, slots = raw[0], struct.unpack_from('<I', raw, r['slotCount'])[0]
        items = struct.unpack_from('<8I', raw, r['slots'])
        out['rackElements'].append({'present': present, 'slotCount': slots,
            'items': sum(1 for v in items if v != r['noItem']), 'type': struct.unpack_from('<I', raw, r['type'])[0]})
    # The EAT-17's payload list (+0x98 pointer, +0xA0 count): its rack and the pod payload.
    rows = {mem.u32(p + 4): (i, p) for i, p in ((i, mem.ptr(g + TABLE + 8 * i)) for i in range(1, 150)) if p}
    mem.close()
    return out


def eat_payload(name: str, stable_id: int) -> dict:
    mem = base.Mem(name)
    g = mem.game
    for i in range(1, 150):
        row = mem.ptr(g + TABLE + 8 * i)
        if row and mem.u32(row + 4) == stable_id:
            count, list_ = mem.u32(row + 0xA0), mem.ptr(row + 0x98)
            payload = ['0x%016X' % mem.u64(list_ + 8 * k) for k in range(min(count, 8))]
            # The rocket it fires (support weapon catalogue: ProjectileWeapon +0 = 132) and that row's impact explosion.
            rocket = mem.ptr(g + PROJECTILE_TABLE + 8 * EAT['projectile'])
            impact = mem.u32(rocket + PROJECTILE_IMPACT) if rocket and mem.u32(rocket) == EAT['projectile'] else None
            mem.close()
            return {'type': i, 'payload': payload, 'impact': impact}
    mem.close()
    raise ValueError('the EAT-17 row is not in %s' % name)


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
    authoring = (ROOT / 'domains/stratagem_authoring.lua').read_text(encoding='utf-8')
    marker = '["name"]="%s",' % EAT['name']
    at = authoring.index(marker)
    stable_id = int(authoring[at:at + 400].split('["root"]={["id"]=')[1].split(',')[0])
    eat = eat_payload(SNAPSHOTS[1], stable_id)
    if EAT['rack'] not in eat['payload']:
        raise ValueError('the EAT-17\'s payload list no longer names its rack: %r' % eat)
    if eat['impact'] != EAT['impactExplosion']:
        raise ValueError('the EAT-17 rocket\'s impact explosion is no longer %d: %r' % (EAT['impactExplosion'], eat))
    observations = [observe(name) for name in SNAPSHOTS]
    for o in observations:
        for e in o['rackElements']:
            if e['present'] == 1 and not (e['slotCount'] == 8 and 0 <= e['items'] <= 8):
                raise ValueError('an implausible rack in %s: %r' % (o['snapshot'], e))
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'layout': LAYOUT, 'eat17': dict(EAT, stableId=stable_id, type=eat['type'], payload=eat['payload']),
        'eat17Rocket': {'projectile': EAT['projectile'], 'impactExplosion': eat['impact'],
            'source': 'the support weapon catalogue (the EAT-17 ProjectileWeapon +0 = 132); its row +0x90 read in the '
                'mission snapshot'},
        'proofs': proofs, 'pinnedBytesMismatchPerSnapshot': relocation, 'observations': observations,
        'semantics': {
            'pod': 'Transport block +0x10 is the network id of the beacon whose activation created the pod, +0xC the '
                'type the dispatcher was given (a redirected beacon\'s delivery)',
            'rack': 'Transport element +0x8 (= +0x24) is the content entity once the authority spawned it (0 until '
                'then); a support weapon\'s content is its rack',
            'items': 'HellpodRack +0x8 + 4 x slot: the network id of the item spawned into that slot (0x7FFF none); a '
                'slot is reset when its item leaves the rack, so the items are read before the first pickup'},
        'unproven': ['A support -> support redirect live (the pod, the rack and both launchers usable).',
            'Whether picking an item up keeps its entity (the projectile pool names the wielded entity as the source).',
            'The rack slot count after type-keyed upgrades (effect 0x119): the Runtime reads the slots, never a count.',
            'Multiplayer: the content spawn runs on the authority (the host).'],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'pins': len(pins), 'eat17': report['eat17'],
        'observations': [(o['snapshot'][13:40], o['transport'], o['racks']) for o in observations]}, indent=1))


if __name__ == '__main__':
    main()
