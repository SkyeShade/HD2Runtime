"""Trace backpack-fed support weapon ammunition to its native owner. Read-only.

Chain, proven for every WeaponLinkedAmmoComponent that draws from the backpack slot:

    call-in StratagemDefinition -> primary payload (hellpod rack)
    -> rack attaches the support weapon and its backpack
    -> weapon WeaponLinkedAmmoComponent {tag, ammo_mode, inventory_slot = Backpack}
    -> the backpack whose TagComponent carries that tag (the only entity that does)
    -> the backpack's DepositComponent {capacity, start_amount, refill_amount, refill_style = Ammo}

The weapon owns no WeaponMagazineComponent; the deposit is the ammunition store. Member identities are
checked against the pinned type library (storage, offset, hidden-name length) and enum names against
alias lengths; scraped wiki stats are fingerprints only. Live snapshot tables must equal the pinned
reference. Nothing here writes memory.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_entity_authoring as entity_research
from research_booster_authoring import TypeLibrary
import snapshot_regions

OUTPUT = ROOT / 'research/backpack-ammo-F5FEE03DCFDB.json'
SUPPORT_RESEARCH = ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json'
STRATAGEMS = ROOT / 'schemas/stratagem_authoring_catalog.json'
WIKI = ROOT / 'data/wiki_support_weapons.json'
LINKED, DEPOSIT, TAG, RACK = ('WeaponLinkedAmmoComponentData', 'DepositComponentData', 'TagComponentData',
    'HellpodRackComponentData')
RACK_SLOTS, RACK_STRIDE = 8, 64
# (offset, storage, hidden-name length, semantic name) — the type library must agree exactly.
DEPOSIT_MEMBERS = ((0, 'UINT32', 8, 'capacity'), (4, 'INT32', 12, 'start_amount'), (8, 'UINT32', 13, 'refill_amount'),
    (128, 'ENUM_UINT32', 12, 'refill_style'), (136, 'UINT64', 27, 'assisted_reload_weapon_path'))
LINKED_MEMBERS = ((0, 'ENUM_UINT64', None, 'tag'), (8, 'ENUM_UINT32', 9, 'ammo_mode'),
    (12, 'ENUM_UINT32', 14, 'inventory_slot'))


def hexid(value: int) -> str:
    return f'0x{value:016X}'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def check_members(native, type_name, expected):
    members = {m['offset64']: m for m in native.typelib_module.layout(native.typelib, type_name, structured=True)['members']}
    proven = []
    for offset, storage, length, name in expected:
        member = members[offset]
        inferred = int(str(member['name']).rsplit('=', 1)[1])
        if member['storage'] != storage or (length is not None and inferred != length):
            raise ValueError(f'{type_name}+{offset} is not {name}: {member}')
        proven.append({'offset': offset, 'member': name, 'storage': storage, 'nameLength': inferred})
    return proven, members


def enum_names(native, library, enum, prefix):
    """Enum value -> name, only where exactly one known name has the value's alias length."""
    lengths = library.lengths(enum)
    known = [line.strip() for line in (entity_research.FILEDIVER / 'hashes/dl_type_names.txt')
        .read_text(encoding='utf-8').splitlines() if line.startswith(prefix)]
    result = {}
    for value, length in lengths.items():
        fits = [name for name in known if len(name) == length]
        if len(fits) == 1 and sum(1 for other in lengths.values() if other == length) == 1:
            result[value] = fits[0][len(prefix):]
    return result, lengths


def build() -> dict:
    native = entity_research.Native()
    library = TypeLibrary(native.typelib, native.probe)
    deposit_members, _ = check_members(native, 'DepositComponent', DEPOSIT_MEMBERS)
    linked_members, linked_layout = check_members(native, 'WeaponLinkedAmmoComponent', LINKED_MEMBERS)
    tag_layout = native.typelib_module.layout(native.typelib, 'TagComponent', structured=True)['members']
    if linked_layout[0]['type_hash'] != tag_layout[0]['type_hash']:
        raise ValueError('linked ammo tag and TagComponent tags are different enum types')
    slots, slot_lengths = enum_names(native, library, 'InventorySlot', 'InventorySlot_')
    # DepositRefill (corroboration only; ownership does not depend on it). This build has six values with
    # alias lengths 18, 18, 19, 22, 29, 19: None/Ammo (18), Medic (19), Supplies (22), one newer value (29)
    # and Count (19). Values 0 and 1 share a length, so Ammo = 1 rests on Filediver's order None, Ammo.
    refill_lengths = library.lengths('DepositRefill')
    if [refill_lengths[v] for v in range(4)] != [len('DepositRefill_None'), len('DepositRefill_Ammo'),
            len('DepositRefill_Medic'), len('DepositRefill_Supplies')]:
        raise ValueError('DepositRefill layout changed')
    refills = {0: 'None', 1: 'Ammo', 2: 'Medic', 3: 'Supplies'}
    backpack_slot = next(value for value, name in slots.items() if name == 'Backpack')

    # Live snapshot tables equal the pinned reference for every relied-on component.
    _, live_entity = snapshot_regions.region_bytes('entity')
    live_equality = {}
    for name in (LINKED, DEPOSIT, TAG, RACK):
        frame, _, _, _, offset = native.probe.find_component(native.entities, name)
        live_equality[name] = live_entity[offset:offset + len(frame)] == native.entities[offset:offset + len(frame)]
        if not live_equality[name]:
            raise ValueError(name + ' differs live')

    tag_owners = native.owners(TAG)
    tags_by_value = {}
    for record, owners in tag_owners.items():
        raw = native.record(TAG, record)
        for value in set(struct.unpack_from('<64Q', raw, 0)) - {0}:
            tags_by_value.setdefault(value, set()).update(owners)
    racks = {}
    for record, owners in native.owners(RACK).items():
        raw = native.record(RACK, record)
        items = [struct.unpack_from('<Q', raw, slot * RACK_STRIDE)[0] for slot in range(RACK_SLOTS)]
        for owner in owners:
            racks[owner] = {'recordIndex': record, 'items': items}
    deposit_by_owner = {owner: record for record, owners in native.owners(DEPOSIT).items() for owner in owners}
    support = json.loads(SUPPORT_RESEARCH.read_text())['weapons']
    catalog_name = {int(h, 16): w['catalogIdentity'] for w in support for h in w['resourceHashes']}
    roots = json.loads(STRATAGEMS.read_text())['stratagems']
    wiki = {w['name']: w for w in json.loads(WIKI.read_text(encoding='utf-8'))['weapons']}

    weapons, other_linked = [], []
    for record, owners in sorted(native.owners(LINKED).items()):
        raw = native.record(LINKED, record)
        tag, mode, slot = struct.unpack_from('<QII', raw, 0)
        for weapon in owners:
            item = {'weaponResource': hexid(weapon), 'weaponPath': native.path(weapon),
                'linkedAmmo': {'recordIndex': record, 'ownerCount': len(owners), 'tag': hexid(tag),
                    'ammoMode': mode, 'inventorySlot': slots.get(slot, slot)}}
            if slot != backpack_slot or not tag:
                item['reason'] = 'Does not draw from a tagged backpack (vehicle or objective linked ammo).'
                other_linked.append(item)
                continue
            carriers = sorted(tags_by_value.get(tag, ()))
            if len(carriers) != 1:
                raise ValueError(f'{hexid(weapon)} linked ammo tag carried by {len(carriers)} entities')
            backpack = carriers[0]
            report = native.report(hexid(weapon))
            components = sorted(c['name'] for c in report['components'] if c.get('resolved'))
            delivering = [(rack, info) for rack, info in racks.items() if weapon in info['items'] and backpack in info['items']]
            if len(delivering) != 1:
                raise ValueError(f'{hexid(weapon)}: {len(delivering)} racks deliver weapon and backpack together')
            rack, rack_info = delivering[0]
            name = catalog_name[weapon]
            root = roots[name]['root']
            if int(root['payloads'][0], 16) != rack:
                raise ValueError(f'{name}: call-in primary payload is not the delivering rack')
            deposit_record = deposit_by_owner[backpack]
            deposit_owners = native.owners(DEPOSIT)[deposit_record]
            body = native.record(DEPOSIT, deposit_record)
            capacity, start, refill = struct.unpack_from('<IiI', body, 0)
            style = struct.unpack_from('<I', body, 128)[0]
            assisted = struct.unpack_from('<Q', body, 136)[0]
            deposit_component = native.component(hexid(backpack), DEPOSIT)
            linked_component = native.component(hexid(weapon), LINKED)
            tag_component = native.component(hexid(backpack), TAG)
            rack_component = native.component(hexid(rack), RACK)
            if struct.unpack_from('<Q', native.record(TAG, tag_component['record_index']), 0)[0] != tag:
                raise ValueError(f'{hexid(backpack)}: linked-ammo tag is not the first TagComponent tag')
            reload_component = native.component(hexid(weapon), 'WeaponReloadComponentData')
            stats = wiki[name]['normalizedFields']['weaponStats']

            def stat(key):
                value = stats.get(key)
                return value.get('value') if isinstance(value, dict) else value
            fingerprint = {'capacity': {'wiki': stat('capacity'), 'native': capacity},
                'fromSupply': {'wiki': stat('magsFromSupply'), 'native': refill},
                'fromAmmoBox': {'wiki': stat('magsFromAmmoBox'), 'native': None,
                    'note': 'Equals refill_amount / 2; applied by game code, not a stored member.'}}
            exact = fingerprint['capacity']['wiki'] == capacity and fingerprint['fromSupply']['wiki'] == refill
            weapons.append({**item, 'supportWeapon': name, 'backpackResource': hexid(backpack),
                'backpackPath': native.path(backpack), 'backpackEntityRow': native.entity_row(backpack),
                'weaponEntityRow': native.entity_row(weapon), 'weaponComponents': components,
                'linkedAmmoIdentity': {'recordIndex': linked_component['record_index'],
                    'indexRow': linked_component['index_row'], 'ownerCount': len(owners)},
                'backpackTag': {'recordIndex': tag_component['record_index'], 'indexRow': tag_component['index_row'],
                    'slot': 0, 'value': hexid(tag)},
                'weaponOwnsMagazine': 'WeaponMagazineComponentData' in components,
                'weaponReloadHasSharedDeposit': None if reload_component is None else
                    bool(native.record('WeaponReloadComponentData', reload_component['record_index'])[60]),
                'tagCarriers': [hexid(value) for value in carriers],
                'callIn': {'stratagem': name, 'rootId': root['id'], 'primaryPayload': hexid(rack)},
                'rack': {'resource': hexid(rack), 'recordIndex': rack_info['recordIndex'],
                    'indexRow': rack_component['index_row'],
                    'weaponSlot': rack_info['items'].index(weapon), 'backpackSlot': rack_info['items'].index(backpack),
                    'items': [hexid(value) for value in rack_info['items']]},
                'deposit': {'component': DEPOSIT, 'recordIndex': deposit_record,
                    'indexRow': deposit_component['index_row'], 'recordSize': len(body),
                    'ownerCount': len(deposit_owners), 'uniqueOwner': len(deposit_owners) == 1,
                    'ownerResources': [hexid(value) for value in deposit_owners], 'recordSha256': sha(body),
                    'values': {'0': capacity, '4': start, '8': refill},
                    'refillStyle': refills.get(style, style), 'assistedReloadWeapon': hexid(assisted) if assisted else None},
                'fingerprint': fingerprint, 'fingerprintExact': exact})
    return {'schemaVersion': 1, 'sourceSnapshot': snapshot_regions.SNAPSHOT.name,
        'pinnedReferences': {'entities': sha(native.entities), 'typelib': sha(native.typelib)},
        'liveEquality': live_equality,
        'typeLibrary': {'DepositComponent': deposit_members, 'WeaponLinkedAmmoComponent': linked_members,
            'tagEnumShared': True, 'inventorySlotBackpack': backpack_slot,
            'inventorySlotAliasLengths': slot_lengths, 'depositRefill': refills,
            'depositRefillAliasLengths': refill_lengths,
            'depositRefillBasis': 'Values 0 and 1 share an alias length; Ammo = 1 follows Filediver order and the '
                'medic (2) and supply (3) backpacks. Corroboration only.'},
        'model': ['call-in StratagemDefinition primary payload is a hellpod rack',
            'the rack attaches the support weapon and its backpack',
            'the weapon WeaponLinkedAmmoComponent draws from the Backpack inventory slot through a tag',
            'exactly one entity (the backpack) carries that tag in its TagComponent',
            'the backpack DepositComponent is the ammunition store; the weapon owns no WeaponMagazineComponent'],
        'backpackFedWeapons': weapons, 'otherLinkedAmmo': other_linked, 'writes': 0}


def main() -> None:
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n', newline='\n')
    for item in report['backpackFedWeapons']:
        print(item['supportWeapon'], item['backpackPath'], item['deposit']['values'], item['deposit']['refillStyle'],
            'exact' if item['fingerprintExact'] else 'MISMATCH', 'magazine' if item['weaponOwnsMagazine'] else 'no magazine')


if __name__ == '__main__':
    main()
