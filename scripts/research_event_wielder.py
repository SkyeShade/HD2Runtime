"""The weapon a player's avatar holds: the game's wielder and inventory records (research for player:equipped_weapon).

Read-only. Proves on build F5FEE03DCFDB, from game.dll code and every retained snapshot:

1. Wielder. The wielder manager (global game+0x3326420) maps an entity to its instance through the game's own hash
   (buckets +0x30, capacity +0x38, empty key +0x3C, multiplier +0x40; the bucket value at +4 is the instance). The
   instance's slot records live at ptr(+0x60) + instance * 0x1D0, five slots of 0x50 bytes whose first u32 is the
   held entity (0 = empty). wield(manager, wielder, slot, item, replicate) at 0x785DE0 writes it; unwield writes 0.
   Slot 0 is the item in hand.
2. Inventory. The inventory manager (global game+0x3326738, passed by the game's own callers of the weapon switch)
   maps the avatar to a 0x30-byte record (hash buckets +0x28, capacity +0x30, empty +0x34, multiplier +0x38; records
   ptr(+0x50)). +0x1C is the selected slot. The switch (0x9AAA50) reads and writes it, then wields the new item into
   slot 0 in the same call, so the selection and slot 0 never disagree between two frames. Selection 1 selects
   record +0x00 (primary) and 2 selects +0x04 (secondary), proven by the switch's jump table; 3 (+0x08) is most
   likely the support weapon, and 4 and 5 (+0x10) a held throwable, stratagem ball or carried item (inference).
3. Type. An entity's type is the u64 at +0 of its descriptor (entity manager global game+0x346BF98; entity map
   buckets +0xF1AEB0, capacity +0xF1AEB8, empty +0xF1AEBC, multiplier +0xF1AEC0; descriptor = manager + 0xF32F18 +
   24 * value, with the entity id at +8). A weapon's type is its resource.
4. Observations. In both mission snapshots before the death the local avatar (602) holds entity 605, an R-36 Eruptor
   (type B6AFF2195568767F), selection 1. Aboard the ship every slot is empty (selection 0). After reinforcement the
   new avatar holds an entity that the (non-atomic) capture recorded before the entity table saw it, with selection
   5. At the mission end transition no wielder or inventory record exists. Other wielders (turrets) hold themselves.
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

OUTPUT = ROOT / 'research/event-wielder-F5FEE03DCFDB.json'
SHIP = ['F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260927T155654Z.hd2snap',
    'F5FEE03DCFDB-20260927T160033Z.hd2snap']
MISSION = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
WIELDER, INVENTORY, ENTITIES = 0x3326420, 0x3326738, 0x346BF98
PLAYERS = 0x3326468
ERUPTOR = 'B6AFF2195568767F'
SELECTION = {1: 0x00, 2: 0x04, 3: 0x08, 4: 0x10, 5: 0x10, 6: 0x0C}

GAME_PROOFS = {
    'wielder': [
        (0x9AAF53, 'mov rcx, qword ptr [rip + {rip}]', WIELDER, 'the weapon switch loads the wielder manager'),
        (0x9AAF61, 'call 0x785de0', None, 'and wields the new item'),
        (0x785DF9, 'cmp edx, dword ptr [rip + {rip}]', None, 'wield: the invalid entity has no instance'),
        (0x785E10, 'mov r8d, dword ptr [rcx + 0x38]', None, 'wielder hash capacity +0x38'),
        (0x785E14, 'mov r10d, dword ptr [rcx + 0x40]', None, 'wielder hash multiplier +0x40'),
        (0x785E3A, 'mov r11, qword ptr [rcx + 0x30]', None, 'wielder hash buckets +0x30'),
        (0x785E43, 'mov r14d, dword ptr [rcx + 0x3c]', None, 'wielder hash empty key +0x3C'),
        (0x785E7F, 'mov r14d, dword ptr [r9 + 4]', None, 'bucket value = instance index'),
        (0x785E9B, 'mov rax, qword ptr [rbp + 0x60]', None, 'slot record array +0x60'),
        (0x785E9F, 'lea r10, [r12 + r12*4]', None, 'slot * 5'),
        (0x785EA3, 'imul r9, r14, 0x1d0', None, 'instance stride 0x1D0'),
        (0x785EAA, 'shl r10, 4', None, 'slot * 0x50'),
        (0x785EBA, 'mov dword ptr [r10 + rax], edi', None, 'the held entity at slot record +0'),
        (0x786B70, 'cmp dword ptr [rax], 0', None, 'an empty slot holds 0'),
        (0x786B7C, 'cmp r8d, 5', None, 'five slots'),
        (0x785836, 'mov dword ptr [rdx + rcx], eax', None, 'unwield clears the slot'),
    ],
    'inventory': [
        (0xA96062, 'mov rcx, qword ptr [rip + {rip}]', INVENTORY, 'a switch caller passes the inventory manager'),
        (0xA9606E, 'call 0x9aaa50', None, 'to the weapon switch'),
        (0x9AAA76, 'mov r9d, dword ptr [rcx + 0x30]', None, 'inventory hash capacity +0x30'),
        (0x9AAA7A, 'mov r10d, dword ptr [rcx + 0x38]', None, 'inventory hash multiplier +0x38'),
        (0x9AAA9D, 'mov r11, qword ptr [rcx + 0x28]', None, 'inventory hash buckets +0x28'),
        (0x9AAAA5, 'mov edi, dword ptr [rcx + 0x34]', None, 'inventory hash empty key +0x34'),
        (0x9AAAF3, 'lea rcx, [rax + rax*2]', None, 'record index * 3'),
        (0x9AAAF7, 'shl rcx, 4', None, 'record stride 0x30'),
        (0x9AAB0A, 'mov r15, qword ptr [r13 + 0x50]', None, 'inventory records +0x50'),
        (0x9AAB1E, 'mov edx, dword ptr [r15 + 0x1c]', None, 'the switch reads the selected slot +0x1C'),
        (0x9AAC0F, 'mov dword ptr [r15 + 0x1c], ebp', None, 'and writes the new selection'),
        (0x9AAC49, 'mov edi, dword ptr [rdx]', None, 'selection 1 -> record +0x00'),
        (0x9AAC4D, 'mov edi, dword ptr [rdx + 4]', None, 'selection 2 -> record +0x04'),
        (0x9AAC52, 'mov edi, dword ptr [rdx + 8]', None, 'selection 3 -> record +0x08'),
        (0x9AAC5C, 'mov edi, dword ptr [rdx + 0x10]', None, 'selections 4 and 5 -> record +0x10'),
    ],
    'entityTypes': [
        (0xFD9D50, 'mov r10, qword ptr [rip + {rip}]', ENTITIES, 'entity manager global (entity map)'),
        (0xFD9D68, 'mov r9d, dword ptr [r10 + 0xf1aeb8]', None, 'entity map capacity'),
        (0xFD9D6F, 'mov r11d, dword ptr [r10 + 0xf1aec0]', None, 'entity map multiplier'),
        (0xFD9D83, 'mov rbx, qword ptr [r10 + 0xf1aeb0]', None, 'entity map buckets'),
        (0xFD9D8A, 'mov edi, dword ptr [r10 + 0xf1aebc]', None, 'entity map empty key'),
        (0xFD9DD4, 'mov eax, dword ptr [rax + 4]', None, 'bucket value = descriptor index'),
        (0xFD9DDB, 'lea rax, [rax + 0x1e65e3]', None, 'descriptor = manager + 0xF32F18 + 24 * index'),
    ],
}


def probe(mem, buckets, capacity, empty, multiplier, key):
    """The game's open-addressed lookup: (key * multiplier + i) & (capacity - 1); stop at the empty key."""
    if key == 0 or capacity == 0 or capacity & (capacity - 1):
        return None
    for i in range(capacity):
        bucket = buckets + 8 * (((key * multiplier) + i) & 0xFFFFFFFF & (capacity - 1))
        found = mem.u32(bucket)
        if found == key:
            value = mem.u32(bucket + 4)
            return None if value == 0xFFFFFFFF else value
        if found == empty:
            return None
    return None


def entity_type(mem, entity):
    manager = mem.ptr(mem.game + ENTITIES)
    index = probe(mem, mem.ptr(manager + 0xF1AEB0), mem.u32(manager + 0xF1AEB8), mem.u32(manager + 0xF1AEBC),
        mem.u32(manager + 0xF1AEC0), entity)
    if index is None:
        return None
    kind, owner = struct.unpack('<QI', mem.read(manager + 0xF32F18 + 24 * index, 12))
    return '%016X' % kind if owner == entity else None


def observe(name, names):
    mem = base.Mem(name)
    players = mem.ptr(mem.game + PLAYERS)
    wielder, inventory = mem.ptr(mem.game + WIELDER), mem.ptr(mem.game + INVENTORY)
    out = {'snapshot': name, 'players': []}
    for index in range(mem.u32(players + 0x84)):
        avatar = mem.u32(players + 0x108 + 0x70 * index)
        instance = probe(mem, mem.ptr(wielder + 0x30), mem.u32(wielder + 0x38), mem.u32(wielder + 0x3C),
            mem.u32(wielder + 0x40), avatar)
        slots = None
        if instance is not None:
            base_slots = mem.ptr(wielder + 0x60) + instance * 0x1D0
            slots = [mem.u32(base_slots + 0x50 * slot) for slot in range(5)]
        record = probe(mem, mem.ptr(inventory + 0x28), mem.u32(inventory + 0x30), mem.u32(inventory + 0x34),
            mem.u32(inventory + 0x38), avatar)
        selection = items = None
        if record is not None:
            raw = mem.read(mem.ptr(inventory + 0x50) + record * 0x30, 0x30)
            selection = struct.unpack_from('<I', raw, 0x1C)[0]
            items = list(struct.unpack_from('<7I', raw, 0))
        held = slots[0] if slots else None
        kind = entity_type(mem, held) if held else None
        out['players'].append({'avatar': avatar, 'wielderInstance': instance, 'slots': slots,
            'inventoryRecord': record, 'selection': selection, 'items': items,
            'selectedItem': items[SELECTION[selection] // 4] if items and selection in SELECTION else None,
            'held': held, 'heldType': kind, 'heldName': names.get(kind) if kind else None})
    out['wielderCount'] = mem.u32(wielder + 0x18)
    mem.close()
    return out


def weapon_names():
    names = {}
    for path, key in ((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json', 'weapons'),
            (ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json', 'weapons')):
        document = json.loads(path.read_text(encoding='utf-8'))
        for weapon in document[key]:
            for resource in weapon.get('resources') or weapon.get('resourceHashes') or []:
                names.setdefault(resource.upper()[2:], weapon.get('name') or weapon.get('catalogIdentity'))
    return names


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / MISSION[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in GAME_PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SHIP + MISSION}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    names = weapon_names()
    observations = [observe(name, names) for name in SHIP + MISSION]
    by = {o['snapshot']: o for o in observations}
    for name in MISSION[:2]:
        local = by[name]['players'][0]
        if (local['heldType'], local['selection'], local['selectedItem']) != (ERUPTOR, 1, local['held']):
            raise ValueError('the R-36 Eruptor in hand is not observed in ' + name)
    for name in SHIP:
        if any(p['slots'] and p['slots'][0] for p in by[name]['players']) or any(
                p['selection'] not in (0, None) for p in by[name]['players']):
            raise ValueError('something is held aboard the ship in ' + name)
    reinforce = by[MISSION[2]]['players'][0]
    if reinforce['selection'] != 5 or reinforce['selectedItem'] != reinforce['held']:
        raise ValueError('the reinforced avatar\'s selection and slot 0 disagree')
    end = by[MISSION[3]]
    if end['wielderCount'] != 0:
        raise ValueError('wielder records remain at the mission end transition')
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'wielder': {'global': WIELDER, 'hash': 0x30, 'count': 0x18, 'slots': 0x60, 'stride': 0x1D0,
            'slotStride': 0x50, 'slotCount': 5, 'hand': 0},
        'inventory': {'global': INVENTORY, 'hash': 0x28, 'records': 0x50, 'stride': 0x30, 'selection': 0x1C,
            'selections': {'1': {'offset': 0x00, 'slot': 'primary', 'proven': True},
                '2': {'offset': 0x04, 'slot': 'secondary', 'proven': True},
                '3': {'offset': 0x08, 'slot': 'support', 'proven': False},
                '4': {'offset': 0x10, 'slot': 'held_item', 'proven': False},
                '5': {'offset': 0x10, 'slot': 'held_item', 'proven': False},
                '6': {'offset': 0x0C, 'slot': 'unknown', 'proven': False}}},
        'entityTypes': {'global': ENTITIES, 'map': 0xF1AEB0, 'descriptors': 0xF32F18, 'stride': 24, 'entity': 8},
        'proofs': proofs, 'pinnedBytesMismatchPerSnapshot': relocation, 'observations': observations,
        'findings': {
            'equipped': 'Slot 0 of the avatar\'s wielder instance is the entity in hand; its descriptor type is the '
                'weapon resource (R-36 Eruptor in both mission snapshots before the death).',
            'switch': 'The weapon switch writes the inventory selection and wields the new item in one call.',
            'death': 'A removed wielder unwields its slots; the new avatar after reinforcement has a fresh instance.',
            'others': 'Turrets and other wielders hold themselves in slot 0: only a player\'s avatar is read.'},
        'unproven': ['Selections 3 to 6 name the support weapon, held items and an unknown slot by inference.',
            'Remote players: the switch wields with replicate = 0 (each peer applies it locally, inference); Runtime '
                'reads only the local player.',
            'Which weapon earned a particular kill: the kill listener receives a source entity but no record keeps it.'],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps([{'snapshot': o['snapshot'][13:], 'players': [{k: p[k] for k in ('avatar', 'held', 'heldName',
        'selection')} for p in o['players']]} for o in observations], indent=1))


if __name__ == '__main__':
    main()
